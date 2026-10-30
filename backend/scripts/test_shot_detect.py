"""镜头切分的自检：硬切要抓到、**软切**也要抓到、闪白不许当成切点。

背景（2026-10-22 实测，任务 a47631b0 的 28.03s 双人片）：
  - 11.70 是硬切，ffmpeg 的 scene 分数 0.473 → 老实现抓得到
  - 24.43 是软切，ffmpeg 的 scene 分数只有 0.120（比同一段 9–11s 频闪的
    0.174 还低）→ 老实现**漏了**，模型在那一段自己编了 4 个不存在的切点
  - 所以加了 `scene._hist_cuts`（色相直方图）补软切；闪光帧用亮度门控排掉

这里用的都是**合成的、真值已知**的片子，成对验尺子：
  1. 对照：硬切必须被抓到（证明整条链没坏）
  2. 软切：合成片的 ffmpeg scene 分数 < 0.30（先自证"老尺子确实看不见"），
     而 detect_shots 必须找到这一刀
  3. 闪光：1 帧 / 2 帧整帧闪白都不许产生切点（先自证片子里真的闪了）
  4. 静止单镜：不许凭空产生切点

运行：python scripts/test_shot_detect.py
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import scene  # noqa: E402
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


def _run(args: list[str]) -> subprocess.CompletedProcess:
    p = subprocess.run([ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y"] + args,
                       capture_output=True, text=True, errors="ignore")
    if p.returncode != 0:
        raise SystemExit("造测试视频失败: " + (p.stderr or "")[-400:])
    return p


def make_soft_cut(path: Path) -> Path:
    """两个不同场景，中间 0.2s 叠化（5 帧）—— ffmpeg 的 scene 分数看不见。

    🩸 别用 `gradients` 造这个样本：它有随机种子，同一条命令两次跑出来的
    直方图不一样，样本本身不稳定（实测同一段代码一次检出、一次漏检）。
    smptebars / smptehdbars 是固定图案，帧帧可复现。
    """
    a = "smptebars=s=360x640:d=3.2:r=25"
    b = "smptehdbars=s=360x640:d=3.2:r=25"
    _run(["-f", "lavfi", "-i", a, "-f", "lavfi", "-i", b,
          "-filter_complex", "[0:v][1:v]xfade=transition=dissolve:duration=0.2:offset=3[v]",
          "-map", "[v]", "-pix_fmt", "yuv420p", "-c:v", "libx264", str(path)])
    return path


def make_hard_cut(path: Path) -> Path:
    """对照组：一亮一暗直接切（老尺子必须能看见）。"""
    a = "color=c=0x101820:s=360x640:d=3:r=25"
    b = "color=c=0xd8c8a0:s=360x640:d=3:r=25"
    _run(["-f", "lavfi", "-i", a, "-f", "lavfi", "-i", b, "-filter_complex",
          "[0:v][1:v]concat=n=2:v=1:a=0[v]", "-map", "[v]",
          "-pix_fmt", "yuv420p", "-c:v", "libx264", str(path)])
    return path


def make_flash(path: Path, burst: int) -> Path:
    """同一画面每 0.4s 整帧闪白 burst 帧（模拟现场闪光灯/频闪）。"""
    g = "gradients=s=360x640:d=6:r=25:c0=0x101820:c1=0x304860:type=linear"
    w = "color=c=white@0.3:s=360x640:d=6:r=25,format=rgba"
    expr = (r"eq(mod(trunc(t*25)\,10)\,0)" if burst == 1
            else r"lt(mod(trunc(t*25)\,10)\,%d)" % burst)
    _run(["-f", "lavfi", "-i", g, "-f", "lavfi", "-i", w, "-filter_complex",
          f"[0:v][1:v]overlay=enable='{expr}'[v]", "-map", "[v]",
          "-pix_fmt", "yuv420p", "-c:v", "libx264", str(path)])
    return path


def make_still(path: Path) -> Path:
    _run(["-f", "lavfi", "-i",
          "gradients=s=360x640:d=4:r=25:c0=0x101820:c1=0x304860:type=linear",
          "-pix_fmt", "yuv420p", "-c:v", "libx264", str(path)])
    return path


def scene_scores(path: Path) -> list[tuple[float, float]]:
    """ffmpeg 自己的 scene 分数（老尺子的读数，用来给软切样本自证）。"""
    p = subprocess.run([
        ffmpeg_path(), "-hide_banner", "-nostats", "-i", str(path), "-an",
        "-filter:v", "select='gt(scene,0.0)',metadata=print:file=-",
        "-f", "null", "-",
    ], capture_output=True, text=True, errors="ignore")
    out: list[tuple[float, float]] = []
    t = None
    for line in (p.stdout or "").splitlines():
        m = re.search(r"pts_time:([0-9.]+)", line)
        if m:
            t = float(m.group(1))
        m2 = re.search(r"lavfi\.scene_score=([0-9.]+)", line)
        if m2 and t is not None:
            out.append((t, float(m2.group(1))))
    return out


def brightness_spread(path: Path, width: int = 64) -> float:
    """整片逐帧平均亮度的极差 —— 用来证明"闪光样本里真的闪了"。"""
    info = scene.probe(path)
    h = max(2, round(info["height"] * width / max(1, info["width"])))
    h -= h % 2
    raw = subprocess.run([
        ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-i", str(path), "-an",
        "-vf", f"scale={width}:{h}:flags=area", "-f", "rawvideo", "-pix_fmt", "gray", "-",
    ], capture_output=True).stdout
    fb = width * h
    means = [sum(raw[i:i + fb]) / fb for i in range(0, len(raw) - fb + 1, fb)]
    return round(max(means) - min(means), 1) if means else 0.0


def cuts_of(path: Path) -> list[float]:
    return [round(s.start, 2) for s in scene.detect_shots(path)[1:]]


def near(cuts: list[float], t: float, tol: float = 0.2) -> bool:
    return any(abs(c - t) <= tol for c in cuts)


def main() -> int:
    # 🚦 必须点名型号（2026-10-26）：一轮只跑一家
    from _model_gate import sel_or_exit as _sel
    _sel()
    work = Path(tempfile.mkdtemp(dir="D:/tmp", prefix="shot_detect_"))
    try:
        return _run_all(work)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _run_all(work: Path) -> int:
    print("== 对照：硬切必须抓到 ==")
    hard = make_hard_cut(work / "hard.mp4")
    hard_cuts = cuts_of(hard)
    check("硬切处有一刀", near(hard_cuts, 3.0), True)
    check("多出来的刀", hard_cuts, [3.0])

    print("== 软切：老尺子看不见，新尺子必须看见 ==")
    soft = make_soft_cut(work / "soft.mp4")
    top = max(s for _, s in scene_scores(soft))
    check("样本自证：ffmpeg scene 分数远低于阈值 0.30", round(top, 3) < 0.30, True)
    print(f"       （实测最高 scene 分数 {top:.3f}）")
    soft_hist = scene._hist_cuts(soft)
    check("直方图找到软切", near(soft_hist, 3.2), True)
    check("detect_shots 也把它算进镜头表", near(cuts_of(soft), 3.2), True)

    print("== 闪光：整帧闪白不许算切点 ==")
    for burst in (1, 2):
        flash = make_flash(work / f"flash{burst}.mp4", burst)
        spread = brightness_spread(flash)
        check(f"{burst} 帧闪：样本自证确实闪了（亮度极差 > 40）", spread > 40, True)
        print(f"       （实测亮度极差 {spread}）")
        check(f"{burst} 帧闪：直方图不给切点", scene._hist_cuts(flash), [])
        # ⚠️ 只验直方图这条线。ffmpeg 自己的 scene 分数对"整帧闪白"照样会报警
        # （合成样本每 0.8s 报一刀），那是**原有行为**、不在这次修补范围：
        # 实测原片（a47631b0 的 9–11s 频闪）scene 分数最高 0.174 < 阈值 0.30，
        # 真实素材里没触发过。真要收口得给 scene 那条线也加闪光门控，另开一条修。

    print("== 静止单镜：不许凭空给切点 ==")
    still = make_still(work / "still.mp4")
    check("没有切点", cuts_of(still), [])

    print("== 时间基准：镜头表必须落在片长内、不许倒挂 ==")
    # 🩸 2026-10-26 的出片失败（10-25 22:54、10-26 02:10 各一次）：软切时间以前拿
    #   「帧序号 ÷ avg_frame_rate」算，而 rawvideo 输出默认按输出帧率做 CFR ——
    #   实测一单 361 帧 / 23.88fps 的片子被补成 **907 帧**，切点算到 23.99s，
    #   可片子只有 15.12s ⇒ 镜头表出现 `start 23.994 / end 15.117` 的倒挂条目，
    #   出片按 19.89s 抽帧 → 一帧都抽不到 → 整单失败。
    #   现在：时间只认 PTS（`_frame_times`），解码走 `-fps_mode passthrough`，
    #   软切也过「在片长内」这道闸（硬切那侧一直有）。
    for name, path in (("硬切", hard), ("软切", soft), ("静止", still)):
        info = scene.probe(path)
        total = float(info["duration"])
        ts = scene._frame_times(path)
        check(f"{name}：读到逐帧 PTS", len(ts) > 0, True)
        check(f"{name}：PTS 单调不倒退",
              all(b >= a for a, b in zip(ts, ts[1:])), True)
        check(f"{name}：PTS 不越界", round(max(ts), 3) <= total + 0.05, True)
        shots = scene.detect_shots(path)
        check(f"{name}：镜头表不倒挂不越界",
              all(s.end > s.start and s.end <= total + 0.05 for s in shots), True)

    print("== 越界镜头兜底：旧配方重跑不许再崩 ==")
    # 真出事的那份配方（10-26 02:10 那单，片长 15.117s）原样拿来量
    from app.services import generate
    TOTAL = 15.117
    for name, (s, e) in {"越界（15.787→23.994）": (15.787, 23.994),
                         "倒挂（23.994→15.117）": (23.994, 15.117)}.items():
        t = generate.seek_time(s, e, TOTAL)
        # 留 0.2s 余量：末帧 PTS 比片长早，`total-0.05` 实测仍然抽不到帧
        check(f"{name}：取样时间被夹进片长", t <= TOTAL - 0.2 + 1e-6, True)
    check("正常镜头不被夹",
          round(generate.seek_time(3.057, 8.835, TOTAL), 3), 5.946)

    print(f"\n{PASS}/{PASS + FAIL} 通过")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
