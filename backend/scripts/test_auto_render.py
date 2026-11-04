"""逐镜分诊（auto）的端到端自检：真跑切段/切回/拼接/合成，只把两个模型调用换成假实现。

和 test_triage.py 的分工：
    test_triage.py      只验"怎么分诊"这条规则（纯函数 + 真 ffmpeg 算运动量）
    test_auto_render.py 验"分诊结果真的落到了成片上"—— 哪些镜头真的走了视频模型、
                        哪些走了静帧、哪些保了原片，邻居有没有被误替换

不花钱（不发任何网络请求）。

运行：python scripts/test_auto_render.py
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
from app.services import clone_pipeline, edit_spec, scene, video_edit  # noqa: E402
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


def make_video(path: Path, seconds: float, w: int = 360, h: int = 640,
               pattern: str = "color") -> Path:
    ff = ffmpeg_path()
    if pattern == "color":
        src = f"color=c=navy:s={w}x{h}:d={seconds}:r=25"
    else:
        src = f"testsrc2=size={w}x{h}:rate=25:duration={seconds}"
    p = subprocess.run(
        [ff, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", src,
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)],
        capture_output=True, text=True, errors="ignore",
    )
    if p.returncode != 0 or not path.exists():
        raise SystemExit("造测试视频失败: " + (p.stderr or "")[-400:])
    return path


class _FakeTTS:
    """本地假配音：造一段 2 秒正弦波，不发任何网络请求。"""

    ext = ".mp3"
    seen_voices: list[str] = []

    def __init__(self, workdir: Path):
        self.workdir = Path(workdir)

    def synth(self, text: str, out: Path, *, voice: str = "",
              rate: int = 0, dialect: str = "") -> None:
        # 签名要和真实供应商一致（voice/rate/dialect 是流水线会传的），
        # 否则改流水线时这里会先炸，掩盖真正的回归
        # 🩸 2026-10-28：`dialect` 是配音方言那期加的（`providers/tts.py:40/117`
        #   两个真供应商都收了），假夹具没跟上 → 整脚本 TypeError。同 2026-10-26
        #   `fake_regen` 少 `lock_tail` 那次，属于签名漂移，不是产品回归。
        out = Path(out)
        # 记下实际用的音色，供测试断言"界面选的音色有没有真的发到 TTS"
        _FakeTTS.seen_voices.append(voice)
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
             "-c:a", "libmp3lame", str(out)],
            check=True, capture_output=True,
        )


def test_span_intervals() -> None:
    """区间裁回镜头范围：撑出去的不能碰邻居，一镜被切开的两段都要留住。"""
    print("== 区间裁回：只收判成 video 的镜头 ==")
    work = Path(tempfile.mkdtemp(dir="D:/tmp", prefix="slice_"))
    try:
        from app.services import assemble

        clip = make_video(work / "span.mp4", 6.0, pattern="testsrc2")
        shots = [
            {"i": 0, "start": 0.0, "end": 2.0},
            {"i": 1, "start": 2.0, "end": 4.0},
            {"i": 2, "start": 4.0, "end": 6.0},
            {"i": 3, "start": 6.0, "end": 8.0},
        ]
        # 一段 2–8s 的结果：覆盖 1、2、3 三个镜头，但只有 1、3 该被替换
        got = clone_pipeline._span_intervals([clip], [(2.0, 8.0)], shots, only={1, 3})
        check("切出来的区间", [(a, b) for a, b, _p, _o in got],
              [(2.0, 4.0), (6.0, 8.0)])
        check("邻居镜头 2 没被替换", any(a < 6.0 and b > 4.0 for a, b, _p, _o in got), False)
        check("第 2 段的素材起点", got[1][3], 4.0)

        # 🩸 回归：一个 28.3s 的长镜头被模型切成 15s + 13.3s 两段
        # 旧实现有「重叠 ≥ 镜头一半」的门，13.3/28.3=47% 会被丢掉 → 后半段冻帧
        long_shot = [{"i": 0, "start": 0.0, "end": 28.3}]
        two = clone_pipeline._span_intervals(
            [clip, clip], [(0.0, 15.0), (15.0, 28.3)], long_shot, only={0})
        check("一镜两段都留住", len(two), 2)
        check("两段拼起来覆盖整镜", round(sum(b - a for a, b, _p, _o in two), 2), 28.3)

        # 🩸 参考重叠（尾巴太短时起点往回借，见 `triage._split_run`）：
        # 时间轴上不许重复排片，第三段从素材 0.4s 起（重叠的 0.4s 只是参考上下文）
        cut_shots = [{"i": 0, "start": 0.0, "end": 11.7},
                     {"i": 1, "start": 11.7, "end": 24.433},
                     {"i": 2, "start": 24.433, "end": 28.033}]
        ov = clone_pipeline._span_intervals(
            [clip, clip, clip],
            [(0.0, 11.7), (11.7, 24.433), (24.033, 28.033)],
            cut_shots, only={0, 1, 2})
        check("重叠参考不重复排片", [(a, b) for a, b, _p, _o in ov],
              [(0.0, 11.7), (11.7, 24.433), (24.433, 28.033)])
        check("第三段从素材 0.4s 起", round(ov[2][3], 3), 0.4)

        # 时间轴真拼一遍：不能有冻帧，且总长不掉
        src = make_video(work / "src.mp4", 6.0)
        tl = assemble.build_intervals(
            src, [(0.0, 4.0, clip, 0.0), (4.0, 6.0, clip, 4.0)],
            total=6.0, workdir=work / "tl", width=360, height=640, fps=25.0)
        check("时间轴时长", round(probe_duration(tl), 2), 6.0)

        # 端到端：一镜两段，第二段必须真的出现在轴上（旧实现这里会是冻帧）
        red = solid(work / "red.mp4", 3.0, "red")
        green = solid(work / "green.mp4", 3.0, "green")
        tl2 = assemble.build_intervals(
            src, [(0.0, 3.0, red, 0.0), (3.0, 6.0, green, 0.0)],
            total=6.0, workdir=work / "tl2", width=360, height=640, fps=25.0)
        r1 = pixel(tl2, 1.0)
        r2 = pixel(tl2, 4.5)
        check("1.0s 处是第一段（红）", r1[0] > 150 and r1[1] < 90, True)
        check("4.5s 处是第二段（绿）", r2[1] > 100 and r2[0] < 90, True)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def solid(path: Path, seconds: float, color: str) -> Path:
    ff = ffmpeg_path()
    p = subprocess.run(
        [ff, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
         "-i", f"color=c={color}:s=360x640:d={seconds}:r=25",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)],
        capture_output=True, text=True, errors="ignore")
    if p.returncode != 0:
        raise SystemExit("造纯色片失败: " + (p.stderr or "")[-300:])
    return path


def pixel(path: Path, at: float) -> tuple:
    """取某一时刻画面缩成 1×1 后的 RGB。"""
    ff = ffmpeg_path()
    p = subprocess.run(
        [ff, "-hide_banner", "-loglevel", "error", "-ss", f"{at:.2f}",
         "-i", str(path), "-frames:v", "1", "-vf", "scale=1:1",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True)
    b = p.stdout[:3]
    return tuple(b) if len(b) == 3 else (0, 0, 0)


def probe_duration(path: Path) -> float:
    from app.services.media import ffprobe_path

    p = subprocess.run(
        [ffprobe_path(), "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1", str(path)],
        capture_output=True, text=True, errors="ignore")
    for line in p.stdout.splitlines():
        if line.startswith("duration="):
            return float(line.split("=", 1)[1])
    return 0.0


def test_auto() -> int:
    work = Path(tempfile.mkdtemp(dir="D:/tmp", prefix="auto_render_"))
    try:
        return _run(work)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _run(work: Path) -> int:
    from app.services import ark, generate

    video = make_video(work / "src.mp4", 12.0)
    # 6 镜各 2s；运动量直接写死在配方里（分析阶段真实算出来的就是这一列）
    shots = []
    for i in range(6):
        shots.append({
            "i": i, "start": i * 2.0, "end": (i + 1) * 2.0, "dur": 2.0,
            "motion": 0.1 if i % 2 == 0 else 12.0,
        })
    rec = {
        "source": {"duration": 12.0, "width": 360, "height": 640, "fps": 25.0,
                   "has_audio": False},
        "shots": shots,
    }

    seen: dict = {"still": None, "spans": None, "plan_prompt": ""}

    def fake_spans(video_path, recipe, spans, *, cid, plan=None, workdir, progress=None, **_):
        seen["spans"] = list(spans)
        if plan:
            seen["plan_prompt"] = plan.get("prompt", "")
        workdir.mkdir(parents=True, exist_ok=True)
        out = []
        for n, (a, b) in enumerate(spans):
            p = workdir / f"span_{n}.mp4"
            make_video(p, max(0.5, b - a), pattern="testsrc2")
            out.append(p)
        return out

    # 🧊 2026-11-03 复刻下架 H3：`minimax.reference_video` 不再存在，元组去掉一项。
    real = (ark.edit_video, video_edit.replace_spans, video_edit._public_url,
            settings.ark_api_key, settings.public_base_url)
    video_edit.replace_spans = fake_spans
    video_edit._public_url = lambda seg, cid: "https://example.test/seg.mp4"
    object.__setattr__(settings, "ark_api_key", "k")
    object.__setattr__(settings, "public_base_url", "https://api.test")

    spec = edit_spec.normalize({
        "person": True, "person_desc": "白衬衫女孩",
        "audio": "original",
    })

    try:
        print("== auto：勾了的镜头一律走视频参考 ==")
        r = clone_pipeline.render(
            video, rec, script=None, workdir=work / "r1",
            mask_bottom=False, regen_mode="auto", regen_channel="volc",
            edit_spec=spec,
        )
        # 🩸 2026-11-02 删掉静帧档：低运动量的镜头也走视频参考
        check("不调静帧生成器", seen["still"], None)
        check("6 镜合成 1 段", len(seen["spans"] or []), 1)
        check("第一段从 0s 起", (seen["spans"] or [(0, 0)])[0][0], 0.0)
        check("6 镜全部替换", r["replaced_shots"], 6)
        check("分诊后不再报整片重制的通道", r["regen_channel"], "volc")
        # 这条规格只填了人物描述、没给人物图 → 提示词必须走**文字**分支，
        # 不许写出 @图片1（那张图根本没发出去，模型拿不到）
        check("没给图时用文字描述换人", "替换为白衬衫女孩" in seen["plan_prompt"], True)
        check("没给图时不许写 @图片1", "@图片1" in seen["plan_prompt"], False)
        # 🩸 2026-10-23 主人拍板「也不烧字幕」：成片不再产出任何字幕文件
        check("成片不带字幕文件", "ass" in r, False)
        dur = r["duration"]
        check("成片时长没跑偏", abs(dur - 12.0) < 0.8, True)
        check("成片不是空的", Path(r["video"]).stat().st_size > 10_000, True)

        img = work / "person.jpg"
        subprocess.run(
            [ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y",
             "-f", "lavfi", "-i", "color=c=red:s=400x600:d=1",
             "-frames:v", "1", str(img)], check=True)

        # 🩸 2026-11-02：老客户端的 "shots" 已归一到 auto —— 勾了哪几镜就重制哪几镜
        print("== 老客户端传 shots：归一化成自动分诊 ==")
        seen.update(still=None, spans=None)
        r1c = clone_pipeline.render(
            video, rec, script=None, workdir=work / "r1c",
            mask_bottom=False, regen_mode="shots", regen_shots=[0],
            edit_spec=spec, refs={"person": img},
        )
        check("不调静帧生成器", seen["still"], None)
        check("只勾 1 镜 → 1 段视频参考", len(seen["spans"] or []), 1)
        check("只替换选中的镜", r1c["replaced_shots"], 1)

        print("== auto：只勾动作镜，其余保原片 ==")
        seen.update(still=None, spans=None)
        r2 = clone_pipeline.render(
            video, rec, script=None, workdir=work / "r2",
            mask_bottom=False, regen_mode="auto", regen_channel="volc",
            edit_spec=spec, regen_shots=[1],
        )
        # 分诊不再产生静帧：一次调用就是一次计费，压根不该调它
        check("不调静帧生成器", seen["still"], None)
        check("只勾 1 镜 → 1 段视频参考", len(seen["spans"] or []), 1)
        check("只替换了 1 镜", r2["replaced_shots"], 1)
        check("其余 5 镜保原片", abs(r2["duration"] - 12.0) < 0.8, True)

        print("== auto：全新配音不改走法（仍是视频参考），时长闸照旧 ==")
        seen.update(still=None, spans=None)
        # 前 3 镜有台词（0–6s），后 3 镜是 B-roll；6 镜全都动得很厉害
        rec3 = {
            "source": dict(rec["source"]),
            "shots": [{"i": i, "start": i * 2.0, "end": (i + 1) * 2.0, "dur": 2.0,
                       "motion": 12.0} for i in range(6)],
            "speech": {"segments": [
                {"start": i * 2.0, "end": (i + 1) * 2.0, "text": f"第{i}句"}
                for i in range(3)
            ]},
        }
        spec_tts = edit_spec.normalize({
            "person": True, "person_desc": "白衬衫女孩", "audio": "tts",
        })
        # 🩸 成对探针：配音比画面短一半，**不拉伸就必须当场停下**，
        # 不许"先花钱把视频生成跑完，再冻帧凑时长"
        try:
            clone_pipeline.render(
                video, rec3, script=None, workdir=work / "r4-blocked",
                mask_bottom=False, regen_mode="auto", regen_channel="volc",
                edit_spec=spec_tts, tts=_FakeTTS(work / "tts-blocked"),
            )
            check("时长差太多时必须报错", "没报错", "报错")
        except RuntimeError as e:
            check("报错点在花钱之前", "可调范围" in str(e), True)

        r4 = clone_pipeline.render(
            video, rec3, script=None, workdir=work / "r4",
            mask_bottom=False, regen_mode="auto", regen_channel="volc",
            edit_spec=spec_tts, tts=_FakeTTS(work / "tts"),
            allow_stretch=True,
        )
        # 假配音固定 2s/句 × 3 句 = 6s，原片 12s → ratio = 2.0
        # → atempo 要的是「配音→原片」的倍率 = 1/ratio = 0.5，夹到下限 0.80
        # → 配音实际 7.5s（往下最多慢 20%，不会慢成 12s，剩下的靠尾段静音）。
        # 3 条台词按 7.5s 摊开：0–2.5 / 2.5–5.0 / 5.0–7.5（秒），
        # 与 2s 一镜求交（重叠过半才算"在说话"）⇒ 前 4 镜在说话，第 5 镜（8–10s）起没人说话。
        # 早先这里是按**原片 ASR**（0–6s）判的，换文案后就整段错位 —— 这就是本轮修的病。
        # 🩸 2026-11-02：口播镜头不再改走静帧；台词由改写器（`_span_script`）喂进去
        check("不调静帧生成器", seen["still"], None)
        check("6 镜合成 1 段视频参考", len(seen["spans"] or []), 1)
        check("视频参考从 0s 起", (seen["spans"] or [(0, 0)])[0][0], 0.0)
        check("6 镜都替换了", r4["replaced_shots"], 6)
        check("配音侧元数据有语速", r4["voice_meta"]["speech_rate"], -30)
        check("配音侧元数据有 atempo", r4["voice_meta"]["stretch"], 0.8)
        # 用户问"30 秒的片子能不能出"时，结果页就靠这条回答
        check("换画面侧回报了模式", r4["regen_meta"]["mode"], "auto")
        check("换画面侧回报了段数", r4["regen_meta"]["segments"], len(seen["spans"] or []) or 1)

        # 🩸 成对探针：选中的音色要一路发到 TTS；语言对不上要换成该语言的默认音色
        # 只验 voice_meta 不算数 —— 那只是回报，没证明真发到了供应商。
        print("== 配音：界面选的音色真的发到 TTS 了吗 ==")

        def _render_voice(tag: str, **kw):
            _FakeTTS.seen_voices.clear()
            r = clone_pipeline.render(
                video, rec3, script=None, workdir=work / tag,
                mask_bottom=False, regen_mode="auto", regen_channel="volc",
                edit_spec=spec_tts, tts=_FakeTTS(work / ("tts-" + tag)),
                allow_stretch=True, **kw,
            )
            return r, set(_FakeTTS.seen_voices)

        r5, used5 = _render_voice("r5", tts_voice="zh_female_vv_uranus_bigtts")
        check("选中的中文音色原样到了 TTS", used5, {"zh_female_vv_uranus_bigtts"})
        check("回报里也是这个音色", r5["voice_meta"]["voice"],
              "zh_female_vv_uranus_bigtts")

        r6, used6 = _render_voice(
            "r6", tts_voice="zh_female_vv_uranus_bigtts", lang="en")
        check("中文音色配英文台词 → 换英文默认音色", used6,
              {"en_female_dacey_uranus_bigtts"})
        check("换音色在结果里说明原因", bool(r6["voice_meta"]["voice_note"]), True)
        check("语言判定落在结果里", r6["voice_meta"]["lang"], "en")

        print("== auto：配方里没有运动量也照常走视频参考 ==")
        seen.update(still=None, spans=None)
        rec2 = {
            "source": dict(rec["source"]),
            "shots": [{"i": i, "start": i * 2.0, "end": (i + 1) * 2.0, "dur": 2.0}
                      for i in range(6)],
        }
        # 运动量已不参与分诊；保留一行实测只为报告
        m = scene.motion(video, 0.2, 1.8)
        print(f"       （纯色原片实测运动量 {m}）")
        r3 = clone_pipeline.render(
            video, rec2, script=None, workdir=work / "r3",
            mask_bottom=False, regen_mode="auto", regen_channel="volc",
            edit_spec=spec,
        )
        check("不调静帧生成器", seen["still"], None)
        check("没有运动量也照常出视频参考", len(seen["spans"] or []), 1)
        check("6 镜都替换", r3["replaced_shots"], 6)
    finally:
        ark.edit_video, video_edit.replace_spans, video_edit._public_url = real[:3]
        object.__setattr__(settings, "ark_api_key", real[3])
        object.__setattr__(settings, "public_base_url", real[4])

    return 0


def main() -> int:
    # 🚦 必须点名型号（2026-10-26）：一轮只跑一家
    from _model_gate import sel_or_exit as _sel
    _sel()
    test_span_intervals()
    test_auto()
    print(f"\n{PASS}/{PASS + FAIL} 通过")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
