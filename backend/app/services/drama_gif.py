"""预览 GIF（E6）—— 把成片的一小段做成可嵌入的循环 GIF。

出处：clipforge `src/lib/video-composer/gif-preview.ts:1-50` +
`src/app/api/project/[id]/preview-gif/route.ts`，**逐字照抄**：
一次过 split → palettegen(128 色) → paletteuse(dither=bayer)，
时长夹 1–10s、宽夹 120–720、帧率夹 5–20（GIF 小才发得出去）。
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from app.services.media import ffmpeg_path


def build_gif_vf(width: int, fps: int) -> str:
    """竞品 `gif-preview.ts:19-21`。"""
    return (f"fps={fps},scale={width}:-1:flags=lanczos,split[s0][s1];"
            "[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer")


def generate(video: Path, out: Path, *, start: float = 0.0, duration: float = 4.0,
             width: int = 360, fps: int = 12) -> Path:
    ff = ffmpeg_path()
    if not ff:
        raise RuntimeError("找不到 ffmpeg，请设置 VT_FFMPEG")
    video, out = Path(video), Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        start_s = max(0.0, float(start))
    except (TypeError, ValueError):
        start_s = 0.0
    try:
        dur = min(10.0, max(1.0, float(duration)))
    except (TypeError, ValueError):
        dur = 4.0
    try:
        w = min(720, max(120, int(width)))
    except (TypeError, ValueError):
        w = 360
    try:
        f = min(20, max(5, int(fps)))
    except (TypeError, ValueError):
        f = 12
    proc = subprocess.run(
        [ff, "-hide_banner", "-loglevel", "error", "-y",
         "-ss", f"{start_s:.3f}", "-t", f"{dur:.3f}", "-i", str(video),
         "-vf", build_gif_vf(w, f), "-loop", "0", str(out)],
        capture_output=True, text=True, errors="ignore", timeout=600)
    if proc.returncode != 0 or not out.exists():
        raise RuntimeError(f"GIF 生成失败：{(proc.stderr or '')[-400:]}")
    return out
