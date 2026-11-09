"""成片速览（E5）+ 审片小样 —— 一张 PNG 看完整条片。

出处：clipforge `src/lib/video-composer/contact-sheet.ts:1-338` +
`src/app/api/project/[id]/contact-sheet/route.ts:1-100`，**逻辑逐字照抄**：
  · 布局夹取（4–12 格、每格 120–320px、波形 80–200px）
  · smart 取样优先级：开场帧 → 真实切点（去重）→ 均匀回填
  · 切点缩略图红框 + 波形上的红刻度
  · 审片小样：短边 ≤720 + 烧时间码（`%{pts:hms}`）

**一处本地化**：我们不读 `.timeline.json` 旁路文件 —— 合成计划里
`compose.plan.boundaries` 就是权威切点（同一条链路算出来的），直接传进来。
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from app.services import drama_cover
from app.services.media import ffmpeg_path, ffprobe_path


def resolve_layout(*, frames=None, thumb_width=None, wave_height=None,
                   has_audio: bool) -> dict:
    """夹取布局参数（竞品 `contact-sheet.ts:31-37`）。"""
    try:
        f = int(frames) if frames is not None else 8
    except (TypeError, ValueError):
        f = 8
    try:
        tw = int(thumb_width) if thumb_width is not None else 180
    except (TypeError, ValueError):
        tw = 180
    try:
        wh = int(wave_height) if wave_height is not None else 120
    except (TypeError, ValueError):
        wh = 120
    frames_n = min(12, max(4, f))
    thumb = min(320, max(120, tw))
    wave = min(200, max(80, wh)) if has_audio else 0
    return {"frames": frames_n, "thumb_width": thumb, "wave_height": wave,
            "sheet_width": frames_n * thumb}


def build_even_filter(layout: dict, duration: float) -> tuple[str, str]:
    """均匀采样版（竞品 `contact-sheet.ts:45-57`）。`duration<=0` 时 1 帧/2s。"""
    rate = layout["frames"] / duration if duration > 0 else 0.5
    strip = (f"[0:v]fps={rate:.6f},scale={layout['thumb_width']}:-2,"
             f"tile={layout['frames']}x1[strip]")
    if layout["wave_height"] <= 0:
        return strip, "strip"
    wave = (f"[0:a]aformat=channel_layouts=mono,"
            f"showwavespic=s={layout['sheet_width']}x{layout['wave_height']}:"
            "colors=0x4ade80[wave]")
    return f"{strip};{wave};[strip][wave]vstack=inputs=2[sheet]", "sheet"


def parse_scene_times(log: str) -> list[float]:
    """从 showinfo 日志里抠切点时间（竞品 `contact-sheet.ts:62-69`）。"""
    times = [float(m) for m in re.findall(r"pts_time:\s*([0-9]+(?:\.[0-9]+)?)", log or "")]
    return sorted(set(times))


def plan_frame_times(*, duration: float, frames: int,
                     scene_times: list[float]) -> dict:
    """挑要采的帧（竞品 `contact-sheet.ts:92-121`）：开场 → 切点 → 均匀回填。

    视频太短/太均匀时**返回少于 frames 条**，绝不拿重复帧凑数。
    """
    if duration <= 0 or frames <= 0:
        return {"times": [], "cuts": []}
    min_gap = duration / frames / 2
    clamp_end = duration - 0.15
    kept: list[float] = []
    for t in sorted(scene_times):
        if t < 0.2 or t > clamp_end:
            continue
        if kept and t - kept[-1] < min_gap:
            continue
        kept.append(t)
    cut_slots = max(0, frames - 1)
    if len(kept) > cut_slots:
        denom = max(1, cut_slots - 1)
        cuts = [kept[round(i * (len(kept) - 1) / denom)] for i in range(cut_slots)]
    else:
        cuts = kept

    entries: list[dict] = [{"t": min(0.15, duration / 2), "cut": False}]
    entries += [{"t": t, "cut": True} for t in cuts]
    for k in range(frames):
        if len(entries) >= frames:
            break
        t = (k + 0.5) * duration / frames
        if t > clamp_end:
            continue
        if any(abs(e["t"] - t) < min_gap for e in entries):
            continue
        entries.append({"t": t, "cut": False})
    entries.sort(key=lambda e: e["t"])
    picked = entries[:frames]
    return {
        "times": [round(e["t"], 3) for e in picked],
        "cuts": [bool(e["cut"]) for e in picked],
    }


def build_smart_filter(layout: dict, plan: dict, *, has_audio: bool,
                       duration: float, all_cuts: list[float],
                       font_file: str | None = None) -> dict:
    """smart 版滤镜（竞品 `contact-sheet.ts:132-173`）。

    每个缩略图左上角压时间码；切点帧加红框；波形上按切点位置画红刻度。
    """
    n = len(plan["times"])
    sheet_width = n * layout["thumb_width"]
    font_size = max(14, round(layout["thumb_width"] * 0.11))
    chains: list[str] = []
    for i, t in enumerate(plan["times"]):
        label = drama_cover.build_drawtext(
            text=f"{t:.1f}s", font_size=font_size, font_color="white",
            box={"color": "black@0.55", "borderW": 4},
            x="6", y="6", font_file=font_file)
        outline = (",drawbox=x=0:y=0:w=iw:h=ih:color=0xf87171@0.9:t=4"
                   if plan["cuts"][i] else "")
        chains.append(
            f"[{i}:v]trim=end_frame=1,scale={layout['thumb_width']}:-2,"
            f"{label}{outline}[f{i}]")
    strip_inputs = "".join(f"[f{i}]" for i in range(n))
    # 单格时竞品用 `copy` 滤镜；`null` 在所有 ffmpeg 版本都稳
    strip = (f"{strip_inputs}hstack=inputs={n}[strip]" if n > 1
             else "[f0]null[strip]")
    if layout["wave_height"] <= 0 or not has_audio:
        return {"filter": ";".join(chains + [strip]), "out": "strip",
                "audio_index": None}
    audio_idx = n
    ticks = [
        f"drawbox=x={round(t / duration * sheet_width)}:y=0:w=2:"
        f"h={layout['wave_height']}:color=0xf87171@0.9:t=fill"
        for t in all_cuts if duration > 0 and 0 < t < duration]
    wave = (f"[{audio_idx}:a]aformat=channel_layouts=mono,"
            f"showwavespic=s={sheet_width}x{layout['wave_height']}:colors=0x4ade80"
            + ("," + ",".join(ticks) if ticks else "") + "[wave]")
    return {
        "filter": ";".join(chains + [strip, wave,
                                     "[strip][wave]vstack=inputs=2[sheet]"]),
        "out": "sheet", "audio_index": audio_idx,
    }


def probe_video(path: Path) -> dict:
    fp = ffprobe_path()
    if not fp:
        return {"duration": 0.0, "has_audio": False, "width": 0, "height": 0}
    try:
        p = subprocess.run(
            [fp, "-v", "error", "-show_entries", "format=duration",
             "-show_entries", "stream=codec_type,width,height",
             "-of", "json", str(path)],
            capture_output=True, text=True, errors="ignore", timeout=60)
        import json
        info = json.loads(p.stdout or "{}")
        streams = info.get("streams") or []
        video = next((s for s in streams if s.get("codec_type") == "video"), {})
        return {
            "duration": float((info.get("format") or {}).get("duration") or 0) or 0.0,
            "has_audio": any(s.get("codec_type") == "audio" for s in streams),
            "width": int(video.get("width") or 0),
            "height": int(video.get("height") or 0),
        }
    except Exception:  # noqa: BLE001
        return {"duration": 0.0, "has_audio": False, "width": 0, "height": 0}


def detect_scene_times(path: Path, threshold: float = 0.22) -> list[float]:
    """一次解码、只记场景分超过阈值的帧（竞品 `contact-sheet.ts:211-227`）。

    失败返回 [] —— smart 模式自动退化为均匀采样，不阻断。
    """
    ff = ffmpeg_path()
    if not ff:
        return []
    th = min(0.6, max(0.1, float(threshold or 0.22)))
    try:
        p = subprocess.run(
            [ff, "-hide_banner", "-i", str(path),
             "-vf", f"select='gt(scene,{th})',showinfo", "-an", "-f", "null", "-"],
            capture_output=True, text=True, errors="ignore", timeout=300)
        return parse_scene_times(p.stderr or "")
    except Exception:  # noqa: BLE001
        return []


def merge_cut_times(known: list[float], detected: list[float],
                    tol: float = 0.35) -> list[float]:
    """权威切点 + 检测到的切点合并（竞品 `contact-sheet.ts:235-238`）：

    已知切点全部保留；检测到的只在**不靠近**已知切点时才算新切点。
    """
    extra = [d for d in detected if not any(abs(d - k) <= tol for k in known)]
    return sorted([*(known or []), *extra])


def generate(video: Path, out: Path, *, frames=None, thumb_width=None,
             wave_height=None, mode: str = "smart", scene_threshold: float = 0.22,
             known_cuts: list[float] | None = None) -> dict:
    """生成速览 PNG，返回实际用的布局与取样计划。"""
    ff = ffmpeg_path()
    if not ff:
        raise RuntimeError("找不到 ffmpeg，请设置 VT_FFMPEG")
    video, out = Path(video), Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    info = probe_video(video)
    layout = resolve_layout(frames=frames, thumb_width=thumb_width,
                            wave_height=wave_height, has_audio=info["has_audio"])
    if mode == "smart" and info["duration"] > 0:
        detected = detect_scene_times(video, scene_threshold)
        cuts = merge_cut_times(list(known_cuts or []), detected)
        plan = plan_frame_times(duration=info["duration"],
                                frames=layout["frames"], scene_times=cuts)
        if plan["times"]:
            built = build_smart_filter(
                layout, plan, has_audio=info["has_audio"],
                duration=info["duration"], all_cuts=cuts,
                font_file=drama_cover.resolve_font())
            args: list[str] = [ff, "-hide_banner", "-loglevel", "error", "-y"]
            for t in plan["times"]:
                args += ["-ss", f"{t:.3f}", "-i", str(video)]
            if built["audio_index"] is not None:
                args += ["-i", str(video)]
            args += ["-filter_complex", built["filter"],
                     "-map", f"[{built['out']}]", "-frames:v", "1", str(out)]
            proc = subprocess.run(args, capture_output=True, text=True,
                                  errors="ignore", timeout=600)
            if proc.returncode != 0 or not out.exists():
                raise RuntimeError(f"速览生成失败：{(proc.stderr or '')[-400:]}")
            return {"layout": {**layout, "frames": len(plan["times"]),
                               "sheet_width": len(plan["times"]) * layout["thumb_width"]},
                    "mode": "smart", "frame_times": plan["times"], "cuts": cuts}

    filt, label = build_even_filter(layout, info["duration"])
    proc = subprocess.run(
        [ff, "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
         "-filter_complex", filt, "-map", f"[{label}]", "-frames:v", "1", str(out)],
        capture_output=True, text=True, errors="ignore", timeout=600)
    if proc.returncode != 0 or not out.exists():
        raise RuntimeError(f"速览生成失败：{(proc.stderr or '')[-400:]}")
    return {"layout": layout, "mode": "even", "frame_times": [], "cuts": []}


# ---------------------------------------------------------------------------
# 审片小样（短边 ≤720 + 烧时间码）
# ---------------------------------------------------------------------------


def proxy_scale_arg(width: int, height: int) -> str | None:
    if not (width > 0 and height > 0):
        return "scale=-2:720"
    if min(width, height) <= 720:
        return None
    return "scale=720:-2" if width <= height else "scale=-2:720"


def build_proxy_filter(width: int, height: int, font_file: str | None = None) -> str:
    """竞品 `contact-sheet.ts:310-317`：缩放 + 左上角烧 `%{pts:hms}`。

    🩸 这里构建的是**最终 execFile 形式**，不要再过 `unshell_filter`。
    """
    parts: list[str] = []
    scale = proxy_scale_arg(width, height)
    if scale:
        parts.append(scale)
    font = ""
    if font_file:
        p = font_file.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        font = f"fontfile='{p}':"
    parts.append(
        f"drawtext={font}text='%{{pts\\:hms}}':fontsize=28:fontcolor=white:"
        "box=1:boxcolor=black@0.5:boxborderw=6:x=10:y=10")
    return ",".join(parts)


def generate_proxy(video: Path, out: Path) -> Path:
    ff = ffmpeg_path()
    if not ff:
        raise RuntimeError("找不到 ffmpeg，请设置 VT_FFMPEG")
    video, out = Path(video), Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    info = probe_video(video)
    vf = build_proxy_filter(info["width"], info["height"], drama_cover.resolve_font())
    proc = subprocess.run(
        [ff, "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
         "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "27",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k",
         "-movflags", "+faststart", str(out)],
        capture_output=True, text=True, errors="ignore", timeout=900)
    if proc.returncode != 0 or not out.exists():
        raise RuntimeError(f"审片小样生成失败：{(proc.stderr or '')[-400:]}")
    return out
