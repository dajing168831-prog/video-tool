"""切点微调的自检：切点会不会被挪到画面变化最小的地方。

造一条"14.5–15.5 秒有一段闪烁、前后都是静止画面"的片子：
  - 硬切在 15.0（正闪烁中间）→ 必须被挪出去
  - 原始切点本来就落在镜头边界 → 不许动（那里本来就有一刀）
  - 整片静止（量具给不出差异）→ 不许乱动

运行：python scripts/test_refine_cuts.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import scene, video_edit  # noqa: E402
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


def make_video(path: Path, seconds: float, flash: tuple[float, float] | None,
               w: int = 360, h: int = 640) -> Path:
    """静态底色；flash 区间叠一条 testsrc2 制造高运动量。"""
    ff = ffmpeg_path()
    cmd = [ff, "-hide_banner", "-loglevel", "error", "-y",
           "-f", "lavfi", "-i", f"color=c=navy:s={w}x{h}:d={seconds}:r=25"]
    if flash:
        a, b = flash
        cmd += ["-f", "lavfi", "-i",
                f"testsrc2=s={w}x{h}:d={seconds}:r=25",
                "-filter_complex",
                f"[0:v][1:v]overlay=enable='between(t,{a},{b})'[v]",
                "-map", "[v]"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)]
    p = subprocess.run(cmd, capture_output=True, text=True, errors="ignore")
    if p.returncode != 0 or not path.exists():
        raise SystemExit("造测试视频失败: " + (p.stderr or "")[-400:])
    return path


def make_voiced(path: Path, seconds: float, w: int = 360, h: int = 640) -> Path:
    """带音轨的静态片，用来验 cut_clip(audio=False)。"""
    ff = ffmpeg_path()
    cmd = [ff, "-hide_banner", "-loglevel", "error", "-y",
           "-f", "lavfi", "-i", f"color=c=navy:s={w}x{h}:d={seconds}:r=25",
           "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
           str(path)]
    p = subprocess.run(cmd, capture_output=True, text=True, errors="ignore")
    if p.returncode != 0 or not path.exists():
        raise SystemExit("造带音轨测试视频失败: " + (p.stderr or "")[-400:])
    return path


def main() -> int:
    # 🚦 必须点名型号（2026-10-26）：一轮只跑一家
    from _model_gate import sel_or_exit as _sel
    _sel()
    work = Path(tempfile.mkdtemp(dir="D:/tmp", prefix="refine_cuts_"))
    try:
        return _run(work)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _run(work: Path) -> int:
    flash = make_video(work / "flash.mp4", 30.0, (14.5, 15.5))
    still = make_video(work / "still.mp4", 30.0, None)

    print("== 量具先自证 ==")
    inside = scene.motion(flash, 14.9, 15.1)
    outside = scene.motion(flash, 10.0, 10.2)
    check("闪烁区间测得有变化", inside > 0, True)
    check("静止区间明显更低", outside < inside, True)

    print("== 硬切的切点会被挪开 ==")
    one_shot = [{"i": 0, "start": 0.0, "end": 30.0, "dur": 30.0}]
    moved = video_edit.refine_cuts(flash, [(0.0, 15.0), (15.0, 30.0)], one_shot)
    cut = moved[0][1]
    print(f"     切点 15.00 → {cut:.2f}")
    check("还是两段", len(moved), 2)
    check("接缝两侧对齐", moved[1][0], moved[0][1])
    check("切点挪了", abs(cut - 15.0) >= 0.5, True)
    check("挪出闪烁区间", 14.4 <= cut <= 15.6, False)
    check("挪过去的地方真的更安静",
          scene.motion(flash, cut - 0.1, cut + 0.1) < inside, True)
    check("首尾没被带走", (moved[0][0], moved[-1][1]), (0.0, 30.0))

    print("== 落在镜头边界上的切点不许动 ==")
    two_shot = [{"i": 0, "start": 0.0, "end": 15.0, "dur": 15.0},
                {"i": 1, "start": 15.0, "end": 30.0, "dur": 15.0}]
    kept = video_edit.refine_cuts(flash, [(0.0, 15.0), (15.0, 30.0)], two_shot)
    check("镜头边界上的切点原样保留", kept, [(0.0, 15.0), (15.0, 30.0)])

    print("== 量具给不出差异时不许乱动 ==")
    same = video_edit.refine_cuts(still, [(0.0, 15.0), (15.0, 30.0)], one_shot)
    check("整片静止 → 切点不动", same, [(0.0, 15.0), (15.0, 30.0)])

    print("== 最短段长兜底 ==")
    tight = video_edit.refine_cuts(
        flash, [(0.0, 2.0), (2.0, 30.0)], one_shot, window=1.5, step=0.25,
        min_sec=1.0)
    check("首段不许被压到 1s 以下", tight[0][1] - tight[0][0] >= 1.0, True)
    check("两段仍然相接", tight[1][0], tight[0][1])

    print("== 挪切点不许把段顶出型号上限 ==")
    # 2.0/H3 单段只收 15s：切点 15.0 正好在闪烁里，但往两边挪都会超 15s
    capped = video_edit.refine_cuts(flash, [(0.0, 15.0), (15.0, 30.0)], one_shot,
                                    min_sec=4.0, max_sec=15.0)
    check("两段都不超过 15s", all(b - a <= 15.0 + 1e-6 for a, b in capped), True)
    check("凑不出合规候选就不动", capped, [(0.0, 15.0), (15.0, 30.0)])
    # 上限放宽到 30s（2.5）时才允许挪
    roomy = video_edit.refine_cuts(flash, [(0.0, 15.0), (15.0, 30.0)], one_shot,
                                   min_sec=4.0, max_sec=30.0)
    check("上限够大时照常挪", abs(roomy[0][1] - 15.0) >= 0.5, True)
    check("放宽后也不超上限", all(b - a <= 30.0 + 1e-6 for a, b in roomy), True)

    print("== 参考片切段：音轨可去掉、画面不动 ==")
    voiced = make_voiced(work / "voiced.mp4", 4.0)
    keep_a = scene.cut_clip(voiced, 0.0, 2.0, work / "cut_a.mp4")
    mute_a = scene.cut_clip(voiced, 0.0, 2.0, work / "cut_b.mp4", audio=False)
    pa, pb = scene.probe(keep_a), scene.probe(mute_a)
    check("原片有音轨", scene.probe(voiced)["has_audio"], True)
    check("默认切段保留音轨", pa["has_audio"], True)
    check("参考片切段去掉音轨", pb["has_audio"], False)
    check("去音轨不改分辨率", (pb["width"], pb["height"]), (pa["width"], pa["height"]))
    check("去音轨不改时长", round(pb["duration"], 1), round(pa["duration"], 1))

    print("== 从中间切：必须帧精确（平台校验收不了前置包）==")
    # 造一条关键帧很稀的片子（-g 200 ≈ 每 8s 一个关键帧），从 9.0s 起切：
    # 前一个关键帧在 8.0s → `-c copy` 会把 8.0–9.0s 那一秒塞成负 PTS 的
    # "discard" 包（文件头写 5.0s，包里却有 6s 的帧）。火山对这种片子当场收任务、
    # 7 秒后异步回 InvalidParameter —— 所以这一条必须成对验：
    #   对照组（copy）**必须**能测出前置包，否则说明探针本身失效。
    sparse = work / "sparse.mp4"
    ff = ffmpeg_path()
    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "color=c=navy:s=360x640:d=20:r=25",
                    "-c:v", "libx264", "-g", "200", "-keyint_min", "200",
                    "-sc_threshold", "0", "-pix_fmt", "yuv420p", str(sparse)],
                   check=True, timeout=120)

    def timeline(p: Path) -> tuple[int, int, float]:
        """(包数, 负 PTS 包数, 首包 PTS)。"""
        ffp = str(Path(ff).with_name("ffprobe.exe"))
        q = subprocess.run([ffp, "-v", "error", "-select_streams", "v:0",
                            "-show_entries", "packet=pts_time", "-of", "csv=p=0",
                            str(p)], capture_output=True, text=True, errors="ignore")
        ts = []
        for ln in q.stdout.strip().splitlines():
            try:
                ts.append(float(ln.split(",")[0]))
            except ValueError:
                continue
        return len(ts), sum(1 for t in ts if t < 0), (ts[0] if ts else 0.0)

    copy_cut = scene.cut_clip(sparse, 9.0, 14.0, work / "copy_cut.mp4",
                              audio=False)
    exact_cut = scene.cut_clip(sparse, 9.0, 14.0, work / "exact_cut.mp4",
                               audio=False, exact=True)
    n_c, neg_c, _ = timeline(copy_cut)
    n_e, neg_e, first_e = timeline(exact_cut)
    check("对照：copy 切法带前置包（探针有效）", neg_c > 0, True)
    check("对照：copy 切法包数多于时长", n_c > 5 * 25, True)
    check("exact 切法没有负 PTS 包", neg_e, 0)
    check("exact 切法首包 PTS 为 0", first_e, 0.0)
    check("exact 切法包数 = 5s × 25", n_e, 125)
    check("exact 切法时长对得上", round(scene.probe(exact_cut)["duration"], 1), 5.0)

    print("== 单段无需处理 ==")
    check("只有一段直接返回", video_edit.refine_cuts(flash, [(0.0, 30.0)], one_shot),
          [(0.0, 30.0)])

    print(f"\n{PASS}/{PASS + FAIL} 通过")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
