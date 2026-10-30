"""【冻结】旧版成片合成 —— 只当验收的尺子，任何业务代码都不许调用它。

这是轨道模型（`app/services/tracks.py`）替换掉的那一版原样拷贝。
`scripts/track_p2_check.py` 拿它当参照物逐帧比对；旧链路一旦完全下线，
这个文件随之删除。

原文档：遮盖旧字幕 → 烧新字幕 → 换音轨 → 出 mp4。

全 CPU，不依赖 GPU 或 Chromium。一条 30 秒 1080p 大约几十秒。

路径坑：ffmpeg 的 ass 滤镜会把 Windows 盘符里的冒号当成参数分隔符，
所以这里统一 cd 到工作目录、只传相对文件名。
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from app.services.media import ffmpeg_path, ffprobe_path

log = logging.getLogger(__name__)


def _run(args: list[str], cwd: Path, timeout: int = 900) -> subprocess.CompletedProcess:
    ff = ffmpeg_path()
    if not ff:
        raise RuntimeError("找不到 ffmpeg，请设置 VT_FFMPEG")
    return subprocess.run(
        [ff, "-hide_banner", "-loglevel", "error", "-y", *args],
        cwd=str(cwd), capture_output=True, text=True, errors="ignore", timeout=timeout,
    )


def _duration(path: Path | None) -> float:
    """读容器时长。读不到就当 0（调用方会退回"以画面为准"）。"""
    if path is None:
        return 0.0
    fp = ffprobe_path()
    if not fp:
        return 0.0
    p = subprocess.run(
        [fp, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, errors="ignore", timeout=60,
    )
    try:
        return max(0.0, float((p.stdout or "").strip().splitlines()[0]))
    except (ValueError, IndexError):
        return 0.0


def compose(
    *,
    video: Path,
    out: Path,
    ass: Path | None = None,
    voice: Path | None = None,
    mask: tuple[int, int, int, int, float] | None = None,
    pad_to: float | None = None,
    target: float | None = None,
    fps: float = 0.0,
    bg_from: Path | None = None,
    bg_gain: float = 0.25,
    crf: int = 20,
    preset: str = "veryfast",
) -> Path:
    """合成一版成片。

    video: 原片（或已重排过镜头的片）
    ass:   字幕文件；传 None 就不烧字幕
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
    """
    video = video.resolve()
    work = video.parent
    out = out.resolve()

    # 成片时长先定死，再拼。以前用 `-shortest`，配音短了就把画面截掉、
    # 配音长了就把画面截掉 —— 两种都是静默截断，成片出来才发现少了半段。
    # 现在：target = 画面/配音/底音轨里最长的，短的补、长的由调用方 tpad 补。
    pad_to = max(0.0, float(pad_to or 0.0))
    video_dur = _duration(video)
    voice_dur = _duration(voice)
    bg_dur = _duration(bg_from)
    if target is None or target <= 0:
        target = max(video_dur + pad_to, voice_dur, bg_dur)
    target = float(target)
    frames = int(round(target * fps)) if target > 0 and fps > 0 else 0
    # 成片长度以**帧数**为准：`-t` 只写 3 位小数会把 12.0333 截成 12.033，
    # 30fps/48000Hz 下正好少 16 个采样（实测 577584 ≠ 577600）。
    # 帧数算得出来的时候，时长就按 frames/fps 给到 6 位。
    cut = (frames / fps) if frames > 0 and fps > 0 else target

    # ffmpeg 里引用同目录资源时只写文件名；字幕在别处就临时拷过来
    # （Windows 盘符里的冒号会被 ass 滤镜当成参数分隔符）
    ass_name = None
    tmp_ass: Path | None = None
    if ass is not None:
        ass = ass.resolve()
        if ass.parent != work:
            tmp_ass = work / "_cap_tmp.ass"
            tmp_ass.write_bytes(ass.read_bytes())
            ass = tmp_ass
        ass_name = ass.name

    # 画面不够长就冻最后一帧补齐。pad_to 是调用方明确要补的（配音比画面长）；
    # extra 是 target 比"画面+pad_to"还长的情况（比如原声轨比画面长），
    # 不补的话成片会在画面结束时提前收口。
    extra_pad = max(0.0, target - (video_dur + pad_to))
    total_pad = pad_to + extra_pad

    vf: list[str] = []
    if total_pad > 0.05:
        # 冻住最后一帧补时长；必须排在 ass 之前，字幕才会盖到补出来的帧上
        vf.append(f"tpad=stop_mode=clone:stop_duration={total_pad:.3f}")
    if mask:
        x, y, w, h, alpha = mask
        vf.append(
            f"drawbox=x={x}:y={y}:w={w}:h={h}:color=black@{alpha}:t=fill"
        )
    if ass_name:
        # 字体目录显式给上，避免 libass 在 Windows 上找不到中文字体
        vf.append(f"ass=filename={ass_name}:fontsdir='C\\:/Windows/Fonts'")

    args: list[str] = ["-i", str(video)]
    if voice is not None:
        args += ["-i", str(voice.resolve())]
    if bg_from is not None:
        args += ["-i", str(bg_from.resolve())]

    # 输入下标：0=画面，1=新配音（有），2=底音轨（有）
    voice_idx = 1 if voice is not None else None
    bg_idx = (2 if voice is not None else 1) if bg_from is not None else None

    graphs: list[str] = []
    map_args: list[str] = []
    if vf:
        graphs.append(f"[0:v]{','.join(vf)}[v]")
        map_args += ["-map", "[v]"]
    else:
        map_args += ["-map", "0:v"]

    if voice_idx is not None and bg_idx is not None:
        # 新配音 + 背景轨，三层处理：
        #   ① 背景压到 bg_gain（默认 0.25）；
        #   ② 拿配音当 sidechain，说话时再把背景压下去（ducking），说完抬回来 ——
        #      不做这一步，背景会全程和配音抢中频，听着像"配音贴上去的"；
        #   ③ 混完统一响度到 -14 LUFS（平台通行值），避免一头大一头小。
        graphs.append(
            f"[{bg_idx}:a]volume={bg_gain:.3f}[a2];"
            f"[{voice_idx}:a]asplit=2[a1][sc];"
            f"[a2][sc]sidechaincompress="
            f"threshold=0.03:ratio=8:attack=15:release=300[ad];"
            f"[a1][ad]amix=inputs=2:duration=first:dropout_transition=0,"
            f"loudnorm=I=-14:TP=-1.5:LRA=11,apad[aout]"
        )
        map_args += ["-map", "[aout]"]
    elif voice_idx is not None:
        # 只有新配音：也要归一响度，否则不同音色出来的音量忽大忽小
        graphs.append(f"[{voice_idx}:a]loudnorm=I=-14:TP=-1.5:LRA=11,apad[aout]")
        map_args += ["-map", "[aout]"]
    elif bg_idx is not None:
        # 只有底音轨：同样补静音到 target，避免比画面短时被截断
        graphs.append(f"[{bg_idx}:a]apad[aout]")
        map_args += ["-map", "[aout]"]

    if graphs:
        args += ["-filter_complex", ";".join(graphs)]

    args += map_args
    if target > 0:
        # 成片按 target 收口：音轨已 apad、画面已 tpad，这里只负责停在同一处
        args += ["-t", f"{cut:.6f}"]
    if frames > 0:
        # 帧数钉死：成片时长与帧率不再互相打架，事后能按帧核对
        args += ["-frames:v", str(frames)]
    args += [
        "-c:v", "libx264", "-crf", str(crf), "-preset", preset,
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart",
        str(out),
    ]

    proc = _run(args, cwd=work)
    if tmp_ass is not None:
        tmp_ass.unlink(missing_ok=True)
    if proc.returncode != 0 or not out.exists():
        raise RuntimeError(f"合成失败: {(proc.stderr or '')[-600:]}")
    log.info("合成完成: %s (%.1f MB)", out, out.stat().st_size / 1024 / 1024)
    return out


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
