"""2.5 分段一致性自检：一条 70 秒原片切成 3 段，逐段核对提示词。

🔴 **这是 2.5 专属文件**（一轮一个型号；单一型号断言只放该型号自己的文件）。

验的是**跨段**的东西 —— 单段夹具测不到：
  · 同一张参考图在每段里的图号是否稳定
  · 同一个人在不同段的指代（外观短语 / 字母）是否一致
  · 一句台词会不会在两段里重复出现
  · 段间首帧的图号对不对（2.5 `sd25-pe:709-717`）
  · 每段产出能不能过 `ruler_sd25` 的全部规则

不花钱：模型调用、公网 URL、素材库全部打桩，一个网络请求都不发。
运行：python scripts/test_spans_sd25.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.core.config import settings  # noqa: E402
from app.services import edit_spec, video_edit  # noqa: E402
from app.services.media import ffmpeg_path  # noqa: E402

PASS = FAIL = 0


def check(name: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {name}: {got}")
    else:
        FAIL += 1
        print(f"  FAIL {name}: got={got!r} want={want!r}")


def make_video(path: Path, seconds: float, w: int = 360, h: int = 640) -> Path:
    """带音轨的原片：2.5 的口型参考要靠它，台词句才会进提示词。"""
    ff = ffmpeg_path()
    p = subprocess.run(
        [ff, "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", f"color=c=navy:s={w}x{h}:d={seconds}:r=25",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
         "-shortest", str(path)],
        capture_output=True, text=True, errors="ignore",
    )
    if p.returncode != 0 or not path.exists():
        raise SystemExit("造测试视频失败: " + (p.stderr or "")[-400:])
    return path


def make_img(path: Path, color: str) -> Path:
    subprocess.run([ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", f"color=c={color}:s=400x600:d=1",
                    "-frames:v", "1", str(path)], check=True)
    return path


def main() -> int:
    from _model_gate import sel_or_exit
    sel_or_exit(only="volc25")

    work = Path(tempfile.mkdtemp(dir="D:/tmp", prefix="span25_"))
    try:
        return _run(work)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _run(work: Path) -> int:
    from app.services import ark, clone_store

    total = 70.0
    video = make_video(work / "src.mp4", total)
    # 7 镜各 10s → 2.5 单段上限 30s → 3 段（0-30 / 30-60 / 60-70），
    # 两个切点都正好落在镜头边界上（`_at_shot_cut` 会因此不带边界帧）
    rec = {
        "source": {"duration": total, "width": 360, "height": 640,
                   "fps": 25.0, "has_audio": True},
        "shots": [{"i": i, "start": i * 10.0, "end": (i + 1) * 10.0, "dur": 10.0}
                  for i in range(7)],
        # 逐句台词：故意跨段分布，其中一句**横跨 30s 切点**（29.0–32.0）
        "voice_lines": [
            {"start": 5.0, "end": 8.0, "text": "第一段第一句", "lang": "zh",
             "asr_speaker": "1"},
            {"start": 20.0, "end": 23.0, "text": "第一段第二句", "lang": "zh",
             "asr_speaker": "1"},
            {"start": 29.0, "end": 32.0, "text": "跨过切点的一句话", "lang": "zh",
             "asr_speaker": "2"},
            {"start": 45.0, "end": 48.0, "text": "第二段的话", "lang": "zh",
             "asr_speaker": "2"},
            # 🩸 第 3 段（60–70s）**故意一句台词都没有**：这一支要走
            #   "没定出说话人"的兜底（`_sd25_who` 的 pics 分支），而段里只剩
            #   一个人 —— 以前按全片槽位算成 2 个，于是并列→不点名，
            #   唯一候选被白白丢掉。
            {"start": 57.0, "end": 59.0, "text": "第二段最后一句", "lang": "zh",
             "asr_speaker": "2"},
        ],
    }
    # 盘点：P1 只在前 40 秒，P2 只在 35 秒之后 —— 三段各覆盖一种"谁在场"
    # `desc_zh` 是真实盘点的产出，也是 2.5 的可指认闸（`require_identifiable_volc25`）
    # 要求的"能区分这两张脸"的依据 —— 不给它，两组人会被直接拦下。
    inventory = {"people": [
        {"id": "P1", "main": True, "desc_zh": "白衬衫男人",
         "appearances": [{"start": 0.0, "end": 40.0}]},
        {"id": "P2", "main": False, "desc_zh": "黑衣服女人",
         "appearances": [{"start": 35.0, "end": 70.0}]},
    ]}

    p1 = make_img(work / "p1.jpg", "red")
    p2 = make_img(work / "p2.jpg", "green")
    # 🩸 台词只有 tts/mix 模式才写进提示词（`original` 模式声音就是原片的，
    #   提示词只写「@音频1…原样保留」，这是设计不是缺口 —— 下面单独出一条断言）。
    #   这条配音轨是 `clone_pipeline` 在出片目录写的，`_audio_track` 从
    #   `workdir` 或它上一级找，所以放在这里。
    (work / "r1").mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", f"sine=frequency=440:duration={total}",
                    str(work / "r1" / "voice.wav")], check=True)

    calls: list[dict] = []

    def fake_volc(prompt, *, video_url, out, ref_images=None, ref_audio=None,
                  resolution="", model="", **_):
        calls.append({"prompt": prompt,
                      "refs": [str(x) for x in (ref_images or [])],
                      "audio": str(ref_audio or ""),
                      "resolution": resolution, "model": model})
        shutil.copy(video, out)
        return out

    real = (ark.edit_video, video_edit._public_url, clone_store.task_dir,
            settings.ark_api_key)
    from app.services import ark_ingest as _ing
    real_ing = _ing.available
    video_edit._public_url = lambda seg, cid: "https://example.test/seg.mp4"
    ark.edit_video = fake_volc
    clone_store.task_dir = lambda cid: work / "tasks" / cid
    _ing.available = lambda: False
    object.__setattr__(settings, "ark_api_key", "k")
    try:
        spec = edit_spec.normalize({
            "person": True,
            "person_ids": ["P1", "P2"],
            "audio": "tts",        # 全新配音 → 台词要逐句写进 {}（`sd25-pe:869`）
            "resolution": "720p",
        })
        r = video_edit.replace_whole(
            video, rec, cid="c" * 32, spec=spec,
            refs={"person": p1, "person2": p2},
            channel="volc", model="", inventory=inventory,
            workdir=work / "r1",
        )
    finally:
        (ark.edit_video, video_edit._public_url, clone_store.task_dir,
         ) = real[:3]
        object.__setattr__(settings, "ark_api_key", real[3])
        _ing.available = real_ing

    print(f"段数 = {len(calls)}")
    dump = Path("D:/tmp/span25_segs")
    dump.mkdir(parents=True, exist_ok=True)
    for i, c in enumerate(calls, 1):
        (dump / f"seg{i}.txt").write_text(c["prompt"], encoding="utf-8")
        print(f"--- 第 {i} 段（{len(c['prompt'])} 字，全文见 {dump}/seg{i}.txt）---")
        print(c["prompt"])
        print()

    check("70s 按 30s 上限切成 3 段", r["chunks"], 3)
    # `r["model"]` 是对账用的真实 API 名（`doubao-seedance-2-5-260628`），
    # 不是注册表里的键 `seedance-2-5`
    check("用了 2.5", "seedance-2-5" in r["model"], True)
    if len(calls) != 3:
        print("段数不对，后面的跨段断言没有意义")
        return 1

    # --- 图号稳定：两个人每次都按同一顺序发出去 ---
    for i, c in enumerate(calls, 1):
        check(f"第 {i} 段人物图是第 1 张", c["refs"][0], str(p1))
        # 切点落在镜头边界 → 不带边界帧，参考图就是 2 张
        check(f"第 {i} 段参考图 2 张（切在镜头边界不带首帧）",
              len(c["refs"]), 2)
    check("三段的参考图顺序完全一致",
          [c["refs"] for c in calls], [calls[0]["refs"]] * 3)

    # --- 每段都过尺子（这是"真实分段链路上的产出"第一次进尺子）---
    import ruler_sd25

    for i, c in enumerate(calls, 1):
        bad = ruler_sd25.check(c["prompt"], ruler_sd25.ctx_for(
            c["prompt"], people=inventory["people"]))
        check(f"第 {i} 段过尺子无破口",
              [f"{rid}:{hits}" for rid, _sev, _nm, _src, hits in bad], [])

    # --- 人物指代：P1 只能出现在第 1、2 段；P2 只能在第 2、3 段 ---
    check("第 1 段换了 P1（@图片1）", "@图片1中的人物" in calls[0]["prompt"], True)
    check("第 1 段没写 P2（@图片2）", "@图片2中的人物" in calls[0]["prompt"], False)
    check("第 3 段换了 P2（@图片2）", "@图片2中的人物" in calls[2]["prompt"], True)
    check("第 3 段没写 P1（@图片1）", "@图片1中的人物" in calls[2]["prompt"], False)

    # --- 台词不重复：每句全文只出现在一段里（跨切那句除外，会被拆成两半）---
    def _hit_all(text: str) -> list[int]:
        return [i for i, c in enumerate(calls, 1) if text in c["prompt"]]

    check("「第一段第一句」只在第 1 段", _hit_all("第一段第一句"), [1])
    check("「第一段第二句」只在第 1 段", _hit_all("第一段第二句"), [1])
    check("「第二段的话」只在第 2 段", _hit_all("第二段的话"), [2])
    check("「第二段最后一句」只在第 2 段", _hit_all("第二段最后一句"), [2])
    # 第 3 段没有台词：音频职责句要落到**这一段唯一在场的人**（@图片2），
    # 不能因为全片还有另一个人就退化成不点名。
    check("第 3 段音频句点名 @图片2",
          "@图片2中的人物使用@音频1的音色与台词" in calls[2]["prompt"], True)
    # 跨 30s 切点那句被拆成前后两半（`_span_lines`），两段各拿一半，合起来是原句
    _cross = "".join("".join(
        w for w in ["跨过切点的一句话"] if w in c["prompt"]) or "" for c in calls)
    check("跨切那句被拆开而不是两段都写全",
          calls[0]["prompt"].count("跨过切点的一句话")
          + calls[1]["prompt"].count("跨过切点的一句话"), 0)

    # --- 称谓：P2 在第 2、3 段各被怎么称呼 ---
    import re

    def _who_for(prompt: str) -> list[str]:
        """抽出提示词里所有「…修改为@图片N中的人物」的称呼。"""
        out = []
        for m in re.finditer(r"[，。；\n]?(?:只)?把([^，。；\n]{1,40}?)"
                             r"(?:修改为|替换为)@图片(\d+)中的人物", prompt):
            out.append((m.group(1).strip(), m.group(2)))
        return out

    for i, c in enumerate(calls, 1):
        print(f"第 {i} 段指代: {_who_for(c['prompt'])}")

    # P2 在第 2、3 段都必须落到 @图片2；称谓词允许随在场人数变化
    # （官方 `sd25-pe:180` 允许多种称谓），但**图号不许变**
    for i in (2, 3):
        got = [w for w, n in _who_for(calls[i - 1]["prompt"]) if n == "2"]
        check(f"第 {i} 段 P2 有且只有一句换人句", len(got), 1)

    _forms()

    print()
    print(f"结果：{PASS} 通过 / {FAIL} 失败")
    return 0 if FAIL == 0 else 1


def _forms() -> None:
    """② 多段形态：段数 / 台词归属 —— 纯函数级，不造视频、不调模型。

    `_run` 那条走的是**一条 70s、3 段**的真实链路；这里把形状补满：
    2 段 / 4 段 / 5 段，一句台词跨两个切点、短句跨段、段内切点、边界归属。
    这些错都不会让请求失败，只会让成片"某句话念两遍"或"少半句"——
    人眼在 480p 上根本看不出来。
    """
    from app.services import video_edit as V

    print("\n== 多段形态：段数与台词归属 ==")

    # --- 段数：2.5 单段 4–30s，切完每段都必须落在里面 ---
    for total, want_n in ((40.0, 2), (70.0, 3), (100.0, 4), (130.0, 5)):
        sp = V.fit_spans([(0.0, total)], 30.0)
        check(f"{total:.0f}s → {want_n} 段", len(sp), want_n)
        check(f"{total:.0f}s 每段都在 4–30s",
              [x for x in sp
               if not (4.0 - 1e-6 <= x[1] - x[0] <= 30.0 + 1e-6)], [])

    spans = [(0.0, 30.0), (30.0, 60.0), (60.0, 100.0)]

    def _txt(rec, a, b, cuts=None) -> str:
        out = V._span_lines(rec, a, b, cuts or []) or []
        return "".join(x.get("text", "") for ln in out for x in ln)

    # --- 一句台词横跨**两个**切点：三段各拿一片，拼回必须逐字等于原句 ---
    long_text = "这一句台词故意写得很长用来横跨两个分段切点看看会不会丢字"
    rec_long = {"source": {"duration": 100.0}, "voice_lines": [
        {"start": 28.0, "end": 63.0, "text": long_text, "lang": "zh"}]}
    parts = [_txt(rec_long, a, b) for a, b in spans]
    check("跨两个切点：三段拼回逐字等于原句", "".join(parts), long_text)
    check("跨两个切点：没有任何一段拿到整句",
          [i for i, p in enumerate(parts, 1) if p == long_text], [])

    # --- ⚠️ 已知缺陷（**未修**，等主人拍板）：1–3 字短句跨段被写进相邻两段 ---
    #   段边界是**两个独立请求**，同一句各念一遍（2.0 是 `generate_audio=True`，
    #   口型也跟着那条重复的音轨走）。修法只能动**共用层** `_span_lines`
    #   （三型号都走这条路）→ 2026-10-28 主人要求「现在只做 2.5」，
    #   共用层改动已回滚。这条断言锁的是**当前已知行为**，修好那天会变红。
    rec_short = {"source": {"duration": 100.0}, "voice_lines": [
        {"start": 28.0, "end": 33.0, "text": "好啊呀", "lang": "zh"}]}
    got = [_txt(rec_short, a, b) for a, b in spans]
    check("（已知缺陷）3 字短句跨段目前两段都有", [g for g in got if g],
          ["好啊呀", "好啊呀"])

    rec_short2 = {"source": {"duration": 100.0}, "voice_lines": [
        {"start": 29.0, "end": 31.0, "text": "好的", "lang": "zh"}]}
    got2 = [_txt(rec_short2, a, b) for a, b in spans]
    check("（已知缺陷）2 字短句同样两段都有", [g for g in got2 if g],
          ["好的", "好的"])

    # --- 段内镜头切点：一句拆两镜，拼回等于原句 ---
    rec_in = {"source": {"duration": 100.0}, "voice_lines": [
        {"start": 8.0, "end": 16.0,
         "text": "这一句横跨段内的镜头切点", "lang": "zh"}]}
    out_in = V._span_lines(rec_in, 0.0, 30.0, [12.0, 20.0]) or []
    check("段内切点：拆成两镜（第 3 镜空）",
          [len(ln) for ln in out_in], [1, 1, 0])
    check("段内切点：两镜拼回等于原句",
          "".join(x["text"] for ln in out_in for x in ln),
          "这一句横跨段内的镜头切点")

    # --- 边界归属：正好从切点开始 / 完全在段外 / 零台词 / 片尾截断 ---
    rec_edge = {"source": {"duration": 100.0}, "voice_lines": [
        {"start": 30.0, "end": 35.0, "text": "从切点开始的一句台词", "lang": "zh"}]}
    check("正好从切点开始：前段没有", _txt(rec_edge, 0.0, 30.0), "")
    check("正好从切点开始：后段有", _txt(rec_edge, 30.0, 60.0),
          "从切点开始的一句台词")

    rec_out = {"source": {"duration": 100.0}, "voice_lines": [
        {"start": 40.0, "end": 45.0, "text": "只在第二段", "lang": "zh"}]}
    check("段外台词：第 1 段没有", _txt(rec_out, 0.0, 30.0), "")
    check("段外台词：第 2 段有", _txt(rec_out, 30.0, 60.0), "只在第二段")

    check("零台词 → None",
          V._span_lines({"source": {"duration": 100.0}}, 0.0, 30.0, []), None)

    rec_tail = {"source": {"duration": 100.0}, "voice_lines": [
        {"start": 98.0, "end": 100.0, "text": "被片尾截断的话", "lang": "zh"}]}
    out_tail = V._span_lines(rec_tail, 60.0, 100.0, []) or []
    check("片尾截断标 cutoff",
          [x.get("part") for x in out_tail[0]], ["cutoff"])

    # --- 跨段的 part 标记：出段标 start、进段标 end ---
    rec_cross = {"source": {"duration": 100.0}, "voice_lines": [
        {"start": 28.0, "end": 33.0, "text": "横跨切点的一句台词", "lang": "zh"}]}
    o_a = (V._span_lines(rec_cross, 0.0, 30.0, []) or [[]])[0]
    o_b = (V._span_lines(rec_cross, 30.0, 60.0, []) or [[]])[0]
    check("跨段前一刀标 start", [x.get("part") for x in o_a], ["start"])
    check("跨段后一刀标 end", [x.get("part") for x in o_b], ["end"])


if __name__ == "__main__":
    raise SystemExit(main())
