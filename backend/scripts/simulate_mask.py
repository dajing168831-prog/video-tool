"""把成片按出片时的同一套遮罩参数压一遍，量「底部黑条」到底长什么样。

主人问：「遮住底部会不会留下阴影？」
alpha=0.95 只是参数，观感得看像素 —— 这里拿真实成片抽一帧，
用与 `clone_pipeline.py:1038-1042` 逐字相同的 drawbox 参数复现，
分别量原帧 / 遮罩帧的底部亮度，并把两张图落盘供人眼核对。

用法：python scripts/simulate_mask.py <out.mp4> [秒]
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import media, scene  # noqa: E402


def stat(img) -> tuple[float, float]:
    gray = img.mean(axis=2)
    return float(gray.mean()), float(gray.std())


def bands(img, name: str) -> None:
    h = img.shape[0]
    step = max(1, int(h * 0.20))
    print(f"  {name}")
    for label, y0, y1 in (("顶 20%", 0, step),
                          ("中 20%", h // 2 - step // 2, h // 2 + step // 2),
                          ("底 20%", h - step, h)):
        m, s = stat(img[y0:y1])
        print(f"    {label:<8} 平均 {m:>6.1f}   标准差 {s:>6.1f}")


def main() -> int:
    import cv2

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    video = Path(sys.argv[1])
    at = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0

    info = scene.probe(video)
    w, h = int(info.get("width") or 0), int(info.get("height") or 0)
    if not w or not h:
        print("读不到分辨率")
        return 1

    tmp = Path(tempfile.mkdtemp(dir="D:/tmp", prefix="masksim_"))
    exe = media.ffmpeg_path()

    raw = tmp / "raw.png"
    subprocess.run([exe, "-y", "-v", "error", "-ss", f"{at:.3f}",
                    "-i", str(video), "-frames:v", "1", str(raw)], check=False)
    if not raw.exists():
        print("抽帧失败")
        return 1

    # 与 clone_pipeline 逐字相同：底 20% 高、black@0.95 实心填充
    mh = int(h * 0.20)
    box = f"drawbox=x=0:y={h - mh}:w={w}:h={mh}:color=black@0.95:t=fill"
    masked = tmp / "masked.png"
    subprocess.run([exe, "-y", "-v", "error", "-i", str(raw),
                    "-vf", box, str(masked)], check=False)

    a = cv2.imread(str(raw), cv2.IMREAD_COLOR)
    b = cv2.imread(str(masked), cv2.IMREAD_COLOR)
    if a is None or b is None:
        print("读图失败")
        return 1

    print(f"片源 {video.name}  {w}x{h}  第 {at:.2f} 秒")
    print(f"遮罩 {box}")
    print(f"\n原帧：")
    bands(a, "(未遮)")
    print(f"\n遮罩后：")
    bands(b, "(已遮)")

    gray_a = a[h - mh:].mean()
    gray_b = b[h - mh:].mean()
    print(f"\n底部区域：{gray_a:.1f} → {gray_b:.1f}"
          f"（降到 {100.0 * gray_b / max(gray_a, 1e-6):.0f}%）")
    mn = b[h - mh:].mean(axis=2)
    print(f"遮罩内像素：最亮 {mn.max():.0f} / 最暗 {mn.min():.0f}"
          f"（不是同一数值=还能看见画面，同一数值=纯色块）")
    print(f"\n对比图：\n  {raw}\n  {masked}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
