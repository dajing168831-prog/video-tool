"""成片质量门 + 时间轴补时长禁令，自检脚本（全本地 ffmpeg，不联网不花钱）。

验的是：
  - 正常片过门
  - 定格片会被判缺陷（这正是"花完钱才发现后半段不动"的那类）
  - 音画时长差、总时长偏离会被判缺陷
  - 素材比计划短时 `_normalize` 抛 ShortClip，**不再偷偷冻帧**
  - `build_intervals` 素材短了改用原片补，并留下说明

运行：python scripts/test_qc.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import assemble, compose, qc  # noqa: E402
from app.services.media import ffmpeg_path, ffprobe_path  # noqa: E402

PASS = FAIL = 0


def check(name: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {name}: {got}")
    else:
        FAIL += 1
        print(f"  FAIL {name}: got={got!r} want={want!r}")


def make(path: Path, *, seconds: float, moving: bool = True,
         audio: float | None = None) -> Path:
    ff = ffmpeg_path()
    src = (f"testsrc2=size=360x640:rate=25:duration={seconds}" if moving
           else f"color=c=navy:s=360x640:d={seconds}:r=25")
    args = [ff, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", src]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={audio}"]
    args += ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
    if audio:
        args += ["-c:a", "aac", "-map", "0:v", "-map", "1:a"]
    args += [str(path)]
    p = subprocess.run(args, capture_output=True, text=True, errors="ignore")
    if p.returncode != 0:
        raise SystemExit("造测试片失败: " + (p.stderr or "")[-400:])
    return path


def dur(path: Path) -> float:
    p = subprocess.run(
        [ffprobe_path(), "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1", str(path)],
        capture_output=True, text=True, errors="ignore")
    for line in p.stdout.splitlines():
        if line.startswith("duration="):
            return float(line.split("=", 1)[1])
    return 0.0


def main() -> int:
    # 🚦 必须点名型号（2026-10-26）：一轮只跑一家
    from _model_gate import sel_or_exit as _sel
    _sel()
    work = Path(tempfile.mkdtemp(dir="D:/tmp", prefix="qc_"))
    try:
        return _run(work)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _run(work: Path) -> int:
    print("== 正常片过门 ==")
    good = make(work / "good.mp4", seconds=5.0, audio=5.0)
    r = qc.inspect(good, expect_duration=5.0, expect_w=360, expect_h=640)
    check("通过", r["ok"], True)
    check("没有缺陷", r["issues"], [])
    # 音频流也会打 avg_frame_rate=0/0，串到视频上就会把帧率读成 0
    check("帧率读的是视频流", r["stats"]["fps"], 25.0)

    print("== 定格片必须被判缺陷 ==")
    frozen = make(work / "frozen.mp4", seconds=6.0, moving=False)
    r2 = qc.inspect(frozen)
    check("不通过", r2["ok"], False)
    check("缺陷里提到定格", any("定格" in x for x in r2["issues"]), True)

    print("== 音画时长不一致 ==")
    av = make(work / "av.mp4", seconds=2.0, moving=True, audio=6.0)
    r3 = qc.inspect(av)
    check("音画不一致被抓到",
          any("音画时长" in x for x in r3["issues"]), True)

    print("== 总时长偏离预期 ==")
    r4 = qc.inspect(good, expect_duration=9.0)
    check("时长偏离被抓到",
          any("总时长" in x for x in r4["issues"]), True)

    print("== 合成按目标时长收口：配音短了不截画面 ==")
    v6 = make(work / "v6.mp4", seconds=6.0)
    a3 = make(work / "a3.mp4", seconds=3.0, moving=False, audio=3.0)
    out1 = work / "c1.mp4"
    compose.compose(video=v6, out=out1, voice=a3, target=6.0, fps=25.0)
    check("成片 6s（不是被配音截成 3s）", round(dur(out1), 1), 6.0)
    r5 = qc.inspect(out1, expect_duration=6.0, expect_fps=25.0,
                    expect_frames=150, expect_samples=288000)
    check("帧数合同通过", r5["ok"], True)
    check("帧数 = 6s×25fps", r5["stats"]["frames"], 150)
    check("采样合同 0 偏差", r5["stats"]["sample_delta"], 0)
    check("音轨补到 6s", round(r5["stats"]["audio_duration"], 1), 6.0)

    print("== 配音比画面长：画面补，成片按配音长度 ==")
    a8 = make(work / "a8.mp4", seconds=8.0, moving=False, audio=8.0)
    out2 = work / "c2.mp4"
    compose.compose(video=v6, out=out2, voice=a8, pad_to=2.0, target=8.0,
                    fps=25.0)
    check("成片 8s", round(dur(out2), 1), 8.0)
    r6 = qc.inspect(out2, expect_duration=8.0, expect_fps=25.0,
                    expect_frames=200, expect_samples=384000)
    check("帧数 = 8s×25fps", r6["stats"]["frames"], 200)
    check("采样合同 0 偏差", r6["stats"]["sample_delta"], 0)

    print("== 30fps + 配音 + 底音：合同照样精确 ==")
    v30 = work / "v30.mp4"
    # make() 固定 25fps，30fps 这条单独造
    ff = ffmpeg_path()
    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc2=size=360x640:rate=30:duration=6",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(v30)],
                   check=True)
    bg = make(work / "bg.mp4", seconds=12.0, moving=False, audio=12.0)
    out3 = work / "c3.mp4"
    compose.compose(video=v30, out=out3, voice=a3, bg_from=bg,
                    target=6.0, fps=30.0)
    r7 = qc.inspect(out3, expect_duration=6.0, expect_fps=30.0,
                    expect_frames=180, expect_samples=288000)
    check("30fps 帧数 = 180", r7["stats"]["frames"], 180)
    check("30fps 采样合同 0 偏差", r7["stats"]["sample_delta"], 0)
    check("30fps 过门", r7["ok"], True)

    print("== 采样合同能抓出偏差（探针自证） ==")
    r8 = qc.inspect(out3, expect_frames=180, expect_samples=288001)
    check("差 1 个采样就报缺陷", r8["ok"], False)

    print("== 素材短了：不许偷偷冻帧 ==")
    short = make(work / "short.mp4", seconds=1.0)
    try:
        assemble._normalize(short, work / "x.mp4", start=0.0, dur=3.0,
                            w=360, h=640, fps=25.0)
        check("抛 ShortClip", False, True)
    except assemble.ShortClip as e:
        check("抛 ShortClip", (round(e.have, 1), round(e.need, 1)), (1.0, 3.0))

    print("== 短素材自动改用原片补，总长不掉 ==")
    base = make(work / "base.mp4", seconds=6.0)
    notes: list[str] = []
    tl = assemble.build_intervals(
        base, [(0.0, 3.0, short, 0.0)], total=6.0,
        workdir=work / "tl", width=360, height=640, fps=25.0, notes=notes)
    check("总长保持 6s", round(dur(tl), 1), 6.0)
    check("留下了说明", len(notes), 1)
    check("说明里写的是用原片补", "原片" in notes[0], True)

    print(f"\n{PASS}/{PASS + FAIL} 通过")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
