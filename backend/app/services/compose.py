"""成片合成 —— 对外还是这个函数，里面交给轨道模型。

`compose()` 的签名一个没动，因为出片链路（`clone_pipeline.encode`）和几个
测试脚本都在调它。真正的拼装逻辑搬到了 `app/services/tracks.py`：那边把成片
拆成画面轨 / 声音轨，每段带指纹；这边只负责把旧参数翻译成一条轨道
作品，然后执行。

🩸 2026-10-23 主人拍板「也不烧字幕」：字幕轨连同 `ass` 参数整个删掉。

想直接说"画面用这几段、声音用这两条"的调用方，绕开这里直接用 `tracks`。
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from app.services import tracks
from app.services.media import ffmpeg_path

log = logging.getLogger(__name__)


def compose(
    *,
    video: Path,
    out: Path,
    voice: Path | None = None,
    mask: tuple[int, int, int, int, float] | None = None,
    pad_to: float | None = None,
    target: float | None = None,
    fps: float = 0.0,
    bg_from: Path | None = None,
    bg_gain: float = 0.25,
    crf: int = 20,
    preset: str = "veryfast",
    clips: list[dict] | None = None,
    size: tuple[int, int, float] | None = None,
) -> Path:
    """合成一版成片（旧接口，转轨道模型执行）。

    video: 原片（或已重排过镜头的片）
    voice: 新配音；传 None 就保留 video 自己的音轨
    mask:  (x, y, w, h, alpha) —— 遮盖原片硬字幕的区域
    pad_to: 配音比画面长时，把最后一帧冻住补够（秒）
    target: 成片目标时长（秒）。给了就**按这个时长收口**：
            画面短了冻最后一帧、音轨短了补静音，绝不用 `-shortest`
            让较短的一路把成片截短。不给就取画面/配音/底音轨里最长的。
    fps:    目标帧率。给了且 target 也给了，就用 `-frames:v` 把帧数钉死
            （round(target × fps)），成片帧数不再依赖时间基的舍入。
    bg_from: 底音轨来源。`mix` 传**分离后**的背景轨（music+sfx 或 background），
             `original` 才传原片整轨 —— 传整轨等于把原对白留在新配音下面
    bg_gain: 底音轨音量倍数，默认 0.25（新配音为主，背景垫底）
    clips:  画面轨直接用这几段素材（`assemble.plan_intervals` 的产物），
            每项 {source, start, end, freeze, label}。传了就不再读 video 的完整时长——
            画面由这几段拼出来，且**只编码一次**，中间不落 timeline.mp4。
    size:   clips 的规格 (宽, 高, 帧率)。模型产出的片段尺寸不一定和原片一致，
            不统一就拼不起来。
    """
    comp = tracks.from_legacy(
        video=video, voice=voice, mask=mask, pad_to=pad_to,
        target=target, fps=fps, bg_from=bg_from, bg_gain=bg_gain,
        crf=crf, preset=preset,
    )
    if clips:
        w, h, f = size or (0, 0, 0.0)
        comp.replace_visual(
            [tracks.VideoClip(source=Path(c["source"]), start=float(c["start"]),
                              end=float(c["end"]), freeze=float(c.get("freeze") or 0),
                              label=c.get("label") or "")
             for c in clips],
            width=int(w), height=int(h), fps=float(f),
        )
    return tracks.render(comp, out)


def make_cover(video: Path, dest: Path, at: float = 0.5, width: int = 540) -> Path:
    """抽一帧当封面。"""
    ff = ffmpeg_path()
    if not ff:
        raise RuntimeError("找不到 ffmpeg，请设置 VT_FFMPEG")
    dest.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [ff, "-hide_banner", "-loglevel", "error", "-y",
         "-ss", f"{max(0.0, at):.3f}", "-i", str(video),
         "-frames:v", "1", "-vf", f"scale={width}:-2", str(dest)],
        capture_output=True, text=True, errors="ignore", timeout=60,
    )
    if proc.returncode != 0 or not dest.exists():
        raise RuntimeError(f"封面抽取失败: {(proc.stderr or '')[:200]}")
    return dest
