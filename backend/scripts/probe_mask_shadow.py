"""量成片底部遮罩区域的实际观感 —— 底 20% 到底有多黑、跟中部差多少。

主人问：「会不会导致那个地方有阴影？」
只看 alpha 数值（0.95）回答不了 —— 要拿出片看真实像素。

做法：抽若干帧，分别算 底 20% / 中间 20% / 顶 20% 的平均亮度（0-255），
再算底部的亮度标准差（标准差≈0 说明是纯色块，肉眼就是一条实心黑边）。

用法：python scripts/probe_mask_shadow.py <out.mp4> [抽帧数]
"""
from __future__ import annotations

import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import media, scene  # noqa: E402


def frames(video: Path, n: int, tmp: Path) -> list[Path]:
    exe = media.ffmpeg_path()
    dur = media.probe_duration(video) or 0.0
    out: list[Path] = []
    for i in range(n):
        t = dur * (i + 0.5) / n
        f = tmp / f"f{i:02d}.png"
        subprocess.run([exe, "-y", "-v", "error", "-ss", f"{t:.3f}",
                        "-i", str(video), "-frames:v", "1", str(f)],
                       check=False)
        if f.exists():
            out.append(f)
    return out


def bands(img) -> dict[str, tuple[float, float]]:
    """上/中/下各取 20% 高度，返回 (平均亮度, 标准差)。"""
    h = img.shape[0]
    step = max(1, int(h * 0.20))

    def stat(y0: int, y1: int) -> tuple[float, float]:
        part = img[y0:y1]
        gray = part.mean(axis=2)
        return float(gray.mean()), float(gray.std())

    return {
        "顶 20%": stat(0, step),
        "中 20%": stat(h // 2 - step // 2, h // 2 + step // 2),
        "底 20%": stat(h - step, h),
    }


def main() -> int:
    import cv2

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # 控制台是 GBK，中文/减号会炸
    except Exception:
        pass

    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    video = Path(sys.argv[1])
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    tmp = Path(tempfile.mkdtemp(dir="D:/tmp", prefix="maskshadow_"))
    print(f"片源 {video.name}")
    print(f"抽帧目录 {tmp}")

    fs = frames(video, n, tmp)
    if not fs:
        print("抽帧失败")
        return 1

    names = ["顶 20%", "中 20%", "底 20%"]
    rows: dict[str, list[tuple[float, float]]] = {k: [] for k in names}
    for f in fs:
        img = cv2.imread(str(f), cv2.IMREAD_COLOR)
        if img is None:
            continue
        for k, v in bands(img).items():
            rows[k].append(v)

    print(f"\n{'区域':<8}{'平均亮度':>10}{'标准差':>10}   （0=全黑, 255=全白）")
    for k in names:
        means = [r[0] for r in rows[k]]
        stds = [r[1] for r in rows[k]]
        print(f"{k:<8}{statistics.mean(means):>10.1f}{statistics.mean(stds):>10.1f}")

    bot = [r[0] for r in rows["底 20%"]]
    mid = [r[0] for r in rows["中 20%"]]
    d = statistics.mean(bot) - statistics.mean(mid)
    print(f"\n底部 − 中部 = {d:+.1f}")
    if d < -40:
        print("→ 底部明显比中部暗，肉眼是一条黑边")
    elif d < -15:
        print("→ 底部偏暗但不算黑块，可能有压暗感")
    else:
        print("→ 底部与中部亮度相当，看不出遮罩")
    print(f"\n帧文件留在 {tmp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
