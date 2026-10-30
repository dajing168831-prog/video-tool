"""P2.5 零成本验收：画面轨直接吃分段素材，少一代压缩。

跑法：
    python scripts/track_p25_check.py [--cid <cid>]

验四件事（全本地 ffmpeg，不调模型）：

  1. **编码次数**：同样 N 段素材，旧路径要 N+2 次 ffmpeg（每段规格化 + concat +
     成片），新路径只要 **1 次**。这条是"少一代压缩"的机械证据。
  2. **不丢帧**：新路径的帧数/采样数/时长与旧路径逐项相等。
  3. **画质没崩**：新旧逐帧 PSNR 高但**有限**（两边都重新编码过，不可能 inf）。
  4. **继承不丢**：把画面轨换成真实分段后，遮罩与尾巴定格必须还在
     （`replace_visual` 丢这两样等于静默砍功能）。

外加一条：从真实任务的 `decisions.json` 重建区间，检查分段首尾相接、覆盖整条时间轴。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import assemble, clone_store, compose, tracks  # noqa: E402
from app.services.media import ffmpeg_path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import legacy_assemble  # noqa: E402
import legacy_compose  # noqa: E402
import track_p2_check as P2  # noqa: E402

PASS = FAIL = 0
_COUNT = {"on": False, "ffmpeg": 0, "args": []}


def check(name: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {name}: {got}")
    else:
        FAIL += 1
        print(f"  FAIL {name}: got={got!r} want={want!r}")


def check_true(name: str, cond: bool, detail="") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {name}{(' ' + detail) if detail else ''}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


_real_run = subprocess.run


def _counting_run(*a, **kw):
    if _COUNT["on"] and a and str(a[0][0]).lower().endswith("ffmpeg.exe"):
        _COUNT["ffmpeg"] += 1
        _COUNT["args"].append(list(a[0]))
    return _real_run(*a, **kw)


def count_render(fn):
    """跑一次渲染，数中间调了几次 ffmpeg。"""
    _COUNT.update({"on": True, "ffmpeg": 0, "args": []})
    try:
        fn()
    finally:
        _COUNT["on"] = False
    return _COUNT["ffmpeg"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cid", default="f01a92f793a24649982d30695f1b6d21")
    args = ap.parse_args()

    subprocess.run = _counting_run

    src = clone_store.source_path(args.cid).resolve()
    rd = P2.pick_render(args.cid)
    voice = rd / "voice.wav"
    ass = rd / "cap.ass"
    info = P2.probe(src)
    total, fps, w, h = info["duration"], info["fps"], info["w"], info["h"]
    work = Path(__import__("tempfile").mkdtemp(prefix="p25_", dir="D:/"))
    print(f"== 素材：{src.name} {total:.3f}s {w}x{h}@{fps}fps")
    print(f"== 验收目录：{work}")

    # 三段素材：都用原片自己的三段（等价于"每段都保持原样"），
    # 这样切点、帧数、内容都是已知的，能逐帧对。
    n1 = info["frames"] // 3
    b1, b2 = n1 / fps, (2 * n1) / fps
    intervals = [(0.0, b1, src, 0.0), (b1, b2, src, b1), (b2, total, src, b2)]

    # ---------------------------------------------------------------- 1. 编码次数
    print("\n== 1. 编码次数：同 3 段素材，旧 vs 新 ==")
    old_tl = work / "old_timeline.mp4"

    def _old_timeline():
        legacy_assemble.build_intervals(src, intervals, total=total,
                                        workdir=work / "old" / "timeline",
                                        width=w, height=h, fps=fps)

    def _new_timeline():
        clips = assemble.plan_intervals(src, intervals, total=total)
        assemble._render_clips(clips, work / "new_timeline.mp4", width=w, height=h,
                               fps=fps, total=total)

    n_old = count_render(lambda: (work / "old" / "timeline").mkdir(parents=True, exist_ok=True)
                         or _old_timeline())
    n_new = count_render(_new_timeline)
    print(f"  旧：{n_old} 次 ffmpeg（3 段规格化 + concat）")
    print(f"  新：{n_new} 次 ffmpeg（一次编完）")
    check("新路径只调 1 次 ffmpeg", n_new, 1)
    # 旧路径的 ffmpeg 次数 = 实际切出来的段数 + 1（concat）。
    # 段数不等于传入的区间数 —— 区间边界会把时间轴切成更多基本段，
    # 拿 len(intervals) 当分母是尺子没自证（第一版就报了个假红）。
    n_pieces = len(assemble.plan_intervals(src, intervals, total=total))
    check("旧路径每段各编一次再 concat", n_old, n_pieces + 1)

    old_tl = work / "old" / "timeline" / "timeline.mp4"
    new_tl = work / "new_timeline.mp4"
    po, pn = P2.probe(old_tl), P2.probe(new_tl)
    check("帧数一致", pn["frames"], po["frames"])
    check("时长一致", pn["duration"], po["duration"])

    # ---------------------------------------------------------------- 2. 画质
    print("\n== 2. 画质：新路径压得少，应该更接近原片 ==")
    p_old_src = P2.psnr(old_tl, src)
    p_new_src = P2.psnr(new_tl, src)
    check_true("新路径比旧路径更接近原片",
               p_new_src is not None and p_old_src is not None and p_new_src > p_old_src,
               f"新 {p_new_src:.2f} dB vs 旧 {p_old_src:.2f} dB")

    # ---------------------------------------------------------------- 3. 整片
    print("\n== 3. 整片：新旧两版都带配音+字幕出一次 ==")
    old_out = work / "old_out.mp4"
    new_out = work / "new_out.mp4"

    def _old_full():
        legacy_compose.compose(video=old_tl, out=old_out, ass=ass, voice=voice,
                               target=total, fps=fps)

    def _new_full():
        clips = assemble.plan_intervals(src, intervals, total=total)
        compose.compose(video=src, out=new_out, ass=ass, voice=voice,
                        target=total, fps=fps, clips=clips, size=(w, h, fps))

    c_old = count_render(_old_full)
    c_new = count_render(_new_full)
    print(f"  旧：整条链路共 {n_old + c_old} 次 ffmpeg（时间轴 {n_old} + 成片 {c_old}）")
    print(f"  新：{c_new} 次 ffmpeg（整条链路）")
    check("整条链路新路径只调 1 次 ffmpeg", c_new, 1)

    qo, qn = P2.probe(old_out), P2.probe(new_out)
    check("成片帧数一致", qn["frames"], qo["frames"])
    check("成片采样数一致", qn["samples"], qo["samples"])
    p_full = P2.psnr(new_out, old_out)
    # 这里**不能**要求 PSNR 很高：两边都重编过，谁也不该和谁逐位相同。
    # 真正要证明的是"新路径更接近原片"，那一条在 §2 用时间轴量过了。
    check_true("新旧成片 PSNR 有限且不崩（不是同一份拷贝）",
               25.0 <= (p_full or 0) < float("inf"), f"= {p_full:.2f} dB" if p_full else "= None")

    # ---------------------------------------------------------------- 4. 继承
    print("\n== 4. 换画面轨时，遮罩与尾巴定格不能被丢掉 ==")
    mask = (0, int(h * 0.8), w, int(h * 0.2), 0.95)
    comp = tracks.from_legacy(video=src, ass=ass, voice=voice, mask=mask,
                              target=total + 1.5, fps=fps)
    clips = [tracks.VideoClip(source=src, start=0.0, end=total, label="only")]
    comp.replace_visual(clips, width=w, height=h, fps=fps)
    graph = " ".join(tracks.compile_plan(comp).graphs)
    check_true("遮罩还在", "drawbox=" in graph)
    check_true("尾巴定格还在（配音更长时要补）", "tpad=stop_mode=clone" in graph)

    # ---------------------------------------------------------------- 5. 真实区间
    print("\n== 5. 真实任务的分段：首尾相接、覆盖整条时间轴 ==")
    real = Path("data/clone/89c228cc2a694aafb1f0cdf8ddae1e57/render/"
                "43be992047d241fbbefa17f4174948dd")
    dj = json.loads((real / "decisions.json").read_text(encoding="utf-8"))
    rsrc = clone_store.source_path("89c228cc2a694aafb1f0cdf8ddae1e57").resolve()
    by_name = {p.name: p for p in real.rglob("*.mp4")}
    rint = [(a, b, by_name.get(Path(name).name) or rsrc, off)
            for a, b, name, off in dj["intervals"]]
    rclips = assemble.plan_intervals(rsrc, rint, total=dj["total"])
    gaps = [round(rclips[i + 1]["start"] - rclips[i]["end"], 6)
            for i in range(len(rclips) - 1)]
    check("分段之间没有空洞/重叠", gaps, [0.0] * (len(rclips) - 1))
    check_true("第一段从 0 开始", abs(rclips[0]["start"]) < 1e-6)
    check_true("最后一段到时间轴末尾",
               abs(rclips[-1]["end"] - dj["total"]) < 1e-3,
               f"{rclips[-1]['end']} vs {dj['total']}")
    check("第一段用的就是我们手上的素材片段", Path(rclips[0]["source"]).name,
          "piece_001.mp4")

    print(f"\n{PASS}/{PASS + FAIL} 通过（零模型调用；产物在 {work}）")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
