"""【冻结】旧版时间轴拼接 —— 只当 P2.5 验收的尺子，业务代码不许调用。

旧做法：每段先用 libx264 crf20 编一遍 → `-c copy` 拼成 timeline.mp4 →
再由 compose 编一遍。**每一帧压两次**，包括没改过的原片。
`app/services/assemble.py` 现在改成"滤镜里 trim+concat、只编一次"，
这个文件留着当参照物，用来证明新路径没有丢帧、没有变形、没有错位。
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from app.services.media import ffmpeg_path, ffprobe_path

log = logging.getLogger(__name__)

_FPS_FALLBACK = 30.0
_PAD_MAX = 0.12


class ShortClip(RuntimeError):
    def __init__(self, src: Path, need: float, have: float):
        self.src, self.need, self.have = src, need, have
        super().__init__(
            f"{src.name} 只有 {have:.2f}s，需要 {need:.2f}s（差 {need - have:.2f}s）")


def _run(args: list[str], cwd: Path, timeout: int = 1800) -> subprocess.CompletedProcess:
    ff = ffmpeg_path()
    if not ff:
        raise RuntimeError("找不到 ffmpeg，请设置 VT_FFMPEG")
    return subprocess.run(
        [ff, "-hide_banner", "-loglevel", "error", "-y", *args],
        cwd=str(cwd), capture_output=True, text=True, errors="ignore", timeout=timeout,
    )


def _probe_duration(path: Path) -> float:
    fp = ffprobe_path()
    if not fp:
        return 0.0
    p = subprocess.run(
        [fp, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1", str(path)],
        capture_output=True, text=True, errors="ignore", timeout=120)
    for line in p.stdout.splitlines():
        if line.startswith("duration="):
            try:
                return float(line.split("=", 1)[1])
            except ValueError:
                return 0.0
    return 0.0


def _normalize(src: Path, dest: Path, *, start: float = 0.0, dur: float,
               w: int, h: int, fps: float, max_pad: float = _PAD_MAX) -> None:
    avail = max(0.0, _probe_duration(src) - max(0.0, start))
    use = min(dur, avail) if avail > 0 else dur
    pad = max(0.0, dur - use)
    if pad > max_pad:
        raise ShortClip(src, need=dur, have=use)

    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h}:(iw-{w})/2:(ih-{h})/2,setsar=1,fps={fps},"
        f"setpts=PTS-STARTPTS"
    )
    if pad > 0.001:
        vf += f",tpad=stop_mode=clone:stop_duration={pad + 0.02:.3f}"
    args = ["-ss", f"{max(0.0, start):.3f}", "-i", str(src.resolve()),
            "-t", f"{dur:.3f}", "-an", "-vf", vf,
            "-c:v", "libx264", "-crf", "20", "-preset", "veryfast",
            "-pix_fmt", "yuv420p", str(dest.resolve())]
    proc = _run(args, cwd=dest.parent)
    if proc.returncode != 0 or not dest.exists():
        raise RuntimeError(f"片段规格化失败 {src.name}: {(proc.stderr or '')[-300:]}")


def build_intervals(
    video: Path,
    intervals: list[tuple[float, float, Path, float]],
    *,
    total: float,
    workdir: Path,
    width: int,
    height: int,
    fps: float = 0.0,
    notes: list[str] | None = None,
) -> Path:
    """旧版：按时间区间拼时间轴（两代压缩）。"""
    if total <= 0:
        raise RuntimeError("时间轴总长必须大于 0")
    workdir.mkdir(parents=True, exist_ok=True)
    fps = fps or _FPS_FALLBACK
    if fps < 12:
        fps = _FPS_FALLBACK

    resolved: list[tuple[float, float, Path, float]] = []
    for a, b, src, off in intervals:
        a, b = max(0.0, min(total, a)), max(0.0, min(total, b))
        if b - a <= 0.02:
            continue
        have = max(0.0, _probe_duration(Path(src)) - off)
        if have >= (b - a) - _PAD_MAX:
            resolved.append((a, b, Path(src), off))
            continue
        keep = max(0.0, have - _PAD_MAX)
        if keep > 0.4:
            resolved.append((a, a + keep, Path(src), off))
            msg = (f"{Path(src).name} 只有 {have:.2f}s，计划 {b - a:.2f}s，"
                   f"剩 {b - a - keep:.2f}s 改用原片")
        else:
            msg = f"{Path(src).name} 太短（{have:.2f}s），这一整段改用原片"
        log.warning("时间轴：%s", msg)
        if notes is not None:
            notes.append(msg)

    marks = {0.0, total}
    for a, b, _src, _off in resolved:
        marks.add(a)
        marks.add(b)
    marks = sorted(marks)

    pieces: list[Path] = []
    for x, y in zip(marks, marks[1:]):
        dur = y - x
        if dur <= 0.02:
            continue
        hit = None
        for a, b, src, off in resolved:
            if a - 1e-6 <= x and y <= b + 1e-6:
                hit = (src, off + (x - a))
                break
        n = len(pieces)
        dest = workdir / f"seg_{n:03d}.mp4"
        if hit is not None:
            src, src_start = hit
            _normalize(Path(src), dest, start=src_start, dur=dur,
                       w=width, h=height, fps=fps)
        else:
            _normalize(video, dest, start=x, dur=dur,
                       w=width, h=height, fps=fps)
        pieces.append(dest)

    if not pieces:
        raise RuntimeError("时间轴没有任何片段")

    lst = workdir / "pieces.txt"
    lst.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in pieces),
        encoding="utf-8",
    )
    out = workdir / "timeline.mp4"
    proc = _run(["-f", "concat", "-safe", "0", "-i", str(lst.resolve()),
                 "-c", "copy", str(out.resolve())], cwd=workdir)
    if proc.returncode != 0 or not out.exists():
        raise RuntimeError(f"拼接失败: {(proc.stderr or '')[-400:]}")
    log.info("时间轴拼好: %d 段，替换区间 %d 个", len(pieces), len(resolved))
    return out
