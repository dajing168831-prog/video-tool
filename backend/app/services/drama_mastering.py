"""母版处理（E8）—— 只做本地精修：接缝连续性体检 + 响度归一 + 去闪烁。

出处：clipforge `src/lib/video-mastering.ts:1-302`，**逐值照抄**：
  · 接缝取样与连续性打分 `:79-112`（切点前后各取 0.08s 首帧，比 YUV 均值/饱和度）
  · 响度测量 `:114-133`（loudnorm 打印的 JSON）
  · 切点来源 `:143-160`：优先 `<成片>.timeline.json` 的 boundaries，没有就用场景检测
  · 渲染参数 `:235-271`（deflicker CRF18 / 响度两遍法的 measured_* 直给 / `-t` 锁时长）
  · 非破坏式：源成片**永不覆盖**，每次产出新文件（竞品 `:273-302` 同款）

🩸 两处本地化（都写在代码旁）：
1. 取样标记键用 `pd.sample`（竞品是自家品牌 `clipforge.sample`），只是内部标记。
2. **GB 45438 隐式标注（AIGC 文件元数据）默认不写** —— 竞品 `renderMastering` 无条件写
   三个 metadata 字段；主人定过「AI 标记默认不打」（见 `drama_compliance.py:18-20`），
   这里保留实现、默认关，要写显式传 `aigc_meta=True`。

🩸 这不是「自动修好」：分析只报「哪里接缝跳得厉害」，修不修由人定；
   `recommendations.deflicker` 恒为 False（竞品同款：闪烁要看片子，不能机器拍板）。
"""
from __future__ import annotations

import json
import math
import re
import subprocess
from pathlib import Path

from app.services.media import ffmpeg_path, ffprobe_path
from app.services import drama_contact_sheet

#: 最多分析多少个切点（竞品 `video-mastering.ts:13`）
MAX_BOUNDARIES = 40
#: 切点前后各取多长（竞品 `:163`）
SAMPLE_OFFSET = 0.08
#: 目标响度（竞品 `:196` / `:256`）
LOUDNESS_I, LOUDNESS_TP, LOUDNESS_LRA = -14.0, -1.5, 11.0
#: 默认服务提供者名（本地化：竞品写死 ClipForge）
DEFAULT_PROVIDER = "ProductDrama"


class MasteringError(RuntimeError):
    pass


def _finite(value) -> float | None:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return num if math.isfinite(num) else None


def parse_signal_stats(log: str) -> dict[int, dict]:
    """从 ffmpeg 日志里抠每个取样帧的 YUV 均值 / 饱和度（竞品 `:79-94`）。"""
    result: dict[int, dict] = {}
    blocks = re.split(r"(?=frame:\d+\s+pts:)", str(log or ""))
    for block in blocks:
        m = re.search(r"pd\.sample=(\d+)", block)
        if not m:
            continue

        def read(key: str) -> float | None:
            got = re.search(rf"lavfi\.signalstats\.{key}=(-?[\d.]+)", block)
            return _finite(got.group(1)) if got else None

        y, u, v, sat = read("YAVG"), read("UAVG"), read("VAVG"), read("SATAVG")
        if None in (y, u, v, sat):
            continue
        result[int(m.group(1))] = {"y": y, "u": u, "v": v, "saturation": sat}
    return result


def score_boundary(at: float, before: dict, after: dict) -> dict:
    """接缝连续性打分（竞品 `:96-112` 逐字）。

    归一化到 0–100；≥52 strong（明显跳）、≥28 review（该看一眼）、否则 ok。
    """
    luma = abs(after["y"] - before["y"]) / 2.55
    chroma = math.hypot(after["u"] - before["u"], after["v"] - before["v"]) / 3.606
    sat = abs(after["saturation"] - before["saturation"]) / 1.81
    score = round(min(100, luma * 1.2 + chroma * 0.65 + sat * 0.25))
    level = "strong" if score >= 52 else "review" if score >= 28 else "ok"
    return {
        "at": round(at * 1000) / 1000,
        "before": before, "after": after,
        "luma_delta": round(luma * 10) / 10,
        "chroma_delta": round(chroma * 10) / 10,
        "saturation_delta": round(sat * 10) / 10,
        "score": score, "level": level,
    }


def parse_loudnorm_measurement(log: str) -> dict | None:
    """从 loudnorm 的 JSON 打印里取测量值（竞品 `:114-133`：从后往前找完整的 {…}）。"""
    source = str(log or "")
    start = source.rfind("{")
    while start >= 0:
        end = source.find("}", start)
        if end >= 0:
            try:
                raw = json.loads(source[start:end + 1])
                keys = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
                vals = [_finite(raw.get(k)) for k in keys]
                if all(v is not None for v in vals):
                    return {"input_i": vals[0], "input_tp": vals[1],
                            "input_lra": vals[2], "input_thresh": vals[3],
                            "target_offset": vals[4]}
            except (ValueError, TypeError):
                pass
        start = source.rfind("{", 0, start)
    return None


def thin_times(times: list[float], limit: int = MAX_BOUNDARIES) -> tuple[list[float], bool]:
    """均匀抽稀到 limit 个（竞品 `:135-141`）。返回 (时间点, 是否截断)。"""
    if len(times) <= limit:
        return times, False
    picked = [times[round(i * (len(times) - 1) / (limit - 1))] for i in range(limit)]
    return picked, True


def read_boundary_times(video: Path, duration: float) -> dict:
    """切点来源：`<成片>.timeline.json` 优先，否则场景检测（竞品 `:143-160`）。"""
    def clean(rows) -> list[float]:
        seen = {
            round(float(v) * 1000) / 1000
            for v in rows
            if isinstance(v, (int, float)) and not isinstance(v, bool)
            and math.isfinite(float(v)) and 0.15 < float(v) < duration - 0.15
        }
        return sorted(seen)

    sidecar = Path(str(video) + ".timeline.json")
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        if isinstance(data.get("boundaries"), list):
            picked, truncated = thin_times(clean(data["boundaries"]))
            if picked:
                return {"times": picked, "source": "timeline", "truncated": truncated}
    except (OSError, ValueError):
        pass
    detected = clean(drama_contact_sheet.detect_scene_times(Path(video)))
    picked, truncated = thin_times(detected)
    return {"times": picked, "source": "scene" if picked else "none",
            "truncated": truncated}


def build_boundary_signal_filter(times: list[float], duration: float) -> str:
    """切点前后各取一帧并打标记（竞品 `:162-172`）。

    🩸 `select=eq(n\\,0)` 的反斜杠不能省 —— 逗号会被当成滤镜参数分隔符。
    """
    samples = []
    for at in times:
        samples.append(max(0.0, at - SAMPLE_OFFSET))
        samples.append(min(duration - 0.04, at + SAMPLE_OFFSET))
    if not samples:
        return ""
    inputs = "".join(f"[s{i}]" for i in range(len(samples)))
    chains = []
    for i, at in enumerate(samples):
        start = max(0.0, at)
        end = min(duration, at + SAMPLE_OFFSET)
        chains.append(
            f"[s{i}]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS,"
            f"select=eq(n\\,0),signalstats,"
            f"metadata=mode=add:key=pd.sample:value={i},metadata=mode=print[o{i}]"
        )
    return f"[0:v]split={len(samples)}{inputs};" + ";".join(chains)


def analyze_boundaries(video: Path, times: list[float], duration: float) -> list[dict]:
    if not times:
        return []
    ff = ffmpeg_path()
    if not ff:
        raise MasteringError("找不到 ffmpeg，请设置 VT_FFMPEG")
    members = times * 2
    maps: list[str] = []
    for i in range(len(members)):
        maps += ["-map", f"[o{i}]"]
    p = subprocess.run(
        [ff, "-hide_banner", "-nostats", "-i", str(video),
         "-filter_complex", build_boundary_signal_filter(times, duration),
         *maps, "-an", "-f", "null", "-"],
        capture_output=True, text=True, errors="ignore", timeout=1800,
    )
    stats = parse_signal_stats(f"{p.stdout or ''}\n{p.stderr or ''}")
    out = []
    for i, at in enumerate(times):
        before, after = stats.get(i * 2), stats.get(i * 2 + 1)
        if before and after:
            out.append(score_boundary(at, before, after))
    return out


def measure_loudness(video: Path) -> dict | None:
    ff = ffmpeg_path()
    if not ff:
        raise MasteringError("找不到 ffmpeg，请设置 VT_FFMPEG")
    p = subprocess.run(
        [ff, "-hide_banner", "-nostats", "-i", str(video), "-map", "0:a:0",
         "-af", f"loudnorm=I={LOUDNESS_I:g}:TP={LOUDNESS_TP:g}:LRA={LOUDNESS_LRA:g}:print_format=json",
         "-f", "null", "-"],
        capture_output=True, text=True, errors="ignore", timeout=1800,
    )
    return parse_loudnorm_measurement(f"{p.stdout or ''}\n{p.stderr or ''}")


def analyze(video: Path) -> dict:
    """体检（不产片）。返回分析 JSON（字段名对齐竞品 `MasteringAnalysis`）。"""
    video = Path(video)
    if not video.exists():
        raise MasteringError("成片文件不存在")
    info = drama_contact_sheet.probe_video(video)
    if info["duration"] <= 0 or info["width"] <= 0 or info["height"] <= 0:
        raise MasteringError("成片无法读取，不能执行连续性分析")
    boundary = read_boundary_times(video, info["duration"])
    boundaries = analyze_boundaries(video, boundary["times"], info["duration"])
    loudness = measure_loudness(video) if info["has_audio"] else None
    review = sum(1 for b in boundaries if b["level"] == "review")
    strong = sum(1 for b in boundaries if b["level"] == "strong")
    normalize = bool(loudness and (
        abs(loudness["input_i"] - LOUDNESS_I) > 0.8 or loudness["input_tp"] > LOUDNESS_TP + 0.1))
    return {
        "version": 1,
        "duration": round(info["duration"] * 1000) / 1000,
        "has_audio": info["has_audio"],
        "boundary_source": boundary["source"],
        "boundaries": boundaries,
        "loudness": loudness,
        "summary": {
            "total": len(boundaries), "review": review, "strong": strong,
            "max_score": max((b["score"] for b in boundaries), default=0),
            "truncated": boundary["truncated"],
        },
        "recommendations": {"normalize_audio": normalize, "deflicker": False},
    }


def build_aigc_metadata_args(content_id: str, provider: str = DEFAULT_PROVIDER) -> list[str]:
    """GB 45438 隐式标注三件套（竞品 `compliance-metadata.ts:40-56`）。

    🩸 **默认不调用**（见文件头第 2 条）；要写由调用方显式传 `aigc_meta=True`。
    """
    clean = re.sub(r'["$\\`\r\n]', "", str(provider or "")).strip() or DEFAULT_PROVIDER
    cid = (re.sub(r'["$\\`\r\n]', "", str(content_id or "")).strip() or "unknown")[:64]
    triple = f"AIGC=1; 内容=AI生成合成; 服务提供者={clean}; 内容制作编号={cid}"
    return ["-metadata", f"comment={triple}",
            "-metadata", f"copyright=AI-generated content by {clean}",
            "-metadata", f"description=本视频含AI生成合成内容（服务提供者:{clean} 编号:{cid}）"]


def build_mastering_args(video: Path, out: Path, analysis: dict, *,
                         normalize_audio: bool, deflicker: bool,
                         content_id: str = "", aigc_meta: bool = False) -> list[str]:
    """精修命令（竞品 `:235-271`）。两项都不选 → 报错，不许空跑一遍重编码。"""
    ff = ffmpeg_path()
    if not ff:
        raise MasteringError("找不到 ffmpeg，请设置 VT_FFMPEG")
    has_audio = bool(analysis.get("has_audio"))
    loud = analysis.get("loudness") or {}
    normalize = bool(normalize_audio and has_audio and loud)
    if not normalize and not deflicker:
        raise MasteringError("请至少选择一项本地精修操作")

    args = [ff, "-nostdin", "-v", "error", "-y", "-i", str(video),
            "-map", "0:v:0", *(["-map", "0:a:0"] if has_audio else [])]
    if deflicker:
        args += ["-vf", "deflicker=size=5:mode=median,format=yuv420p",
                 "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                 "-pix_fmt", "yuv420p"]
    else:
        args += ["-c:v", "copy"]
    if has_audio:
        if normalize:
            def fixed(v: float) -> str:
                return f"{max(-99.0, min(99.0, float(v))):.2f}"
            args += ["-af",
                     (f"loudnorm=I={LOUDNESS_I:g}:TP={LOUDNESS_TP:g}:LRA={LOUDNESS_LRA:g}"
                      f":measured_I={fixed(loud['input_i'])}"
                      f":measured_LRA={fixed(loud['input_lra'])}"
                      f":measured_TP={fixed(loud['input_tp'])}"
                      f":measured_thresh={fixed(loud['input_thresh'])}"
                      f":offset={fixed(loud['target_offset'])}"
                      ":linear=true:print_format=summary"),
                     "-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
        else:
            args += ["-c:a", "copy"]
    args += ["-map_metadata", "0", "-movflags", "+faststart"]
    if aigc_meta:
        args += build_aigc_metadata_args(content_id or "unknown")
    args += ["-t", f"{float(analysis.get('duration') or 0):.3f}", str(out)]
    return args


def render(video: Path, out: Path, analysis: dict, *, normalize_audio: bool,
           deflicker: bool, content_id: str = "", aigc_meta: bool = False) -> Path:
    """非破坏式精修：源文件不动，产出新 mp4（竞品 `:273-302`）。"""
    video, out = Path(video), Path(out)
    if not video.exists():
        raise MasteringError("成片文件不存在")
    out.parent.mkdir(parents=True, exist_ok=True)
    if float(analysis.get("duration") or 0) <= 0:
        raise MasteringError("分析结果没有时长，不能渲染")
    args = build_mastering_args(video, out, analysis,
                                normalize_audio=normalize_audio,
                                deflicker=deflicker,
                                content_id=content_id, aigc_meta=aigc_meta)
    p = subprocess.run(args, capture_output=True, text=True, errors="ignore", timeout=1800)
    if p.returncode != 0 or not out.exists():
        out.unlink(missing_ok=True)
        raise MasteringError(f"本地精修失败：{(p.stderr or '')[-200:]}")
    return out
