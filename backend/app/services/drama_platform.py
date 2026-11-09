"""多平台导出（E4）+ 站外二维码风险把关（E3 的策略层）。

出处：clipforge `src/lib/platform-specs.ts:1-105`（平台表 / 码率上限 / 二维码三档政策）、
`src/lib/video-framing.ts:1-52`（blur/fit/crop 三档构图）、
`src/lib/export-guard.ts:1-140`（VBV 码率预算 / 帧率封顶 / 实测报告）、
`src/lib/platform-export.ts:1-90`（导出与单帧预览），**逐值照抄**。

为什么要有这一层：成片是 9:16 竖屏，发小红书要 3:4、发 Reels 要压到 5 Mbps ——
平台转码是「先糊再加噪」，**在本地按目标规格出好，比交给平台压要好**。
这一层全是本地 ffmpeg，零生成费。

🩸 码率上限是**社区实测/官方推荐**（竞品注释写的是 2026-07 记录），不是平台硬限 ——
   它是编码目标，不是判据；报告里如实说「平台仍可能重新编码」，不许写成保证。
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.media import ffmpeg_path, ffprobe_path

#: 平台规格（竞品 `platform-specs.ts:24-37` 逐值）
PLATFORM_SPECS: dict[str, dict] = {
    "douyin": {"name": "抖音", "w": 1080, "h": 1920, "ratio": "9:16",
               "max_video_kbps": 6000, "max_fps": 60},
    "kuaishou": {"name": "快手", "w": 1080, "h": 1920, "ratio": "9:16",
                 "max_video_kbps": 8000, "max_fps": 60},
    "xiaohongshu": {"name": "小红书", "w": 1080, "h": 1440, "ratio": "3:4",
                    "max_video_kbps": 8000, "max_fps": 60},
    "shipinhao": {"name": "视频号", "w": 1080, "h": 1920, "ratio": "9:16",
                  "max_video_kbps": 8000, "max_fps": 60},
    "tiktok": {"name": "TikTok Shop", "w": 1080, "h": 1920, "ratio": "9:16",
               "max_video_kbps": 8000, "max_fps": 60},
    "reels": {"name": "Instagram Reels", "w": 1080, "h": 1920, "ratio": "9:16",
              "max_video_kbps": 5000, "max_fps": 60},
    "shorts": {"name": "YouTube Shorts", "w": 1080, "h": 1920, "ratio": "9:16",
               "max_video_kbps": 8000, "max_fps": 60},
}

#: 站外导流（二维码）政策（竞品 `platform-specs.ts:59-105` 逐字）
QR_BLOCK_DOUYIN = {
    "level": "block",
    "zh": ("抖音 2026-07 起严打站外导流：成片内出现二维码/联系方式，首违关闭橱窗 7 天，"
           "二违永久收回带货权限并冻结佣金。默认拒绝烧录，确认自担风险可用 force 强制"),
    "en": ("Douyin's 2026-07 enforcement treats any in-video QR/contact info as off-site diversion: "
           "1st offense closes the shop window for 7 days, 2nd permanently revokes commerce rights "
           "and freezes commissions. Refused by default; pass force to proceed at your own risk"),
}
QR_WARN_DOMESTIC = {
    "level": "warn",
    "zh": ("国内平台普遍处罚站外导流，成片内二维码有限流/处罚风险，"
           "建议仅在私域分发（微信群/朋友圈）使用带码版本"),
    "en": ("Chinese platforms generally punish off-site diversion; an in-video QR risks "
           "throttling/penalties. Use the QR version only for private-channel distribution "
           "(WeChat groups/Moments)"),
}
QR_OK = {
    "level": "ok",
    "zh": "该平台无站外导流处罚风险记录",
    "en": "No known off-site-diversion enforcement on this platform",
}

OFFSITE_QR_POLICIES: dict[str, dict] = {
    "douyin": QR_BLOCK_DOUYIN,
    "kuaishou": QR_WARN_DOMESTIC,
    "xiaohongshu": QR_WARN_DOMESTIC,
    "shipinhao": QR_WARN_DOMESTIC,
    "tiktok": QR_OK,
    "reels": QR_OK,
    "shorts": QR_OK,
}

#: 构图三档（竞品 `video-framing.ts:3-6`）
FRAMING_MODES = ("blur", "fit", "crop")
DEFAULT_FRAMING = {"mode": "blur", "positionX": 0.5, "positionY": 0.5}

#: 音频 + 容器开销预留（竞品 `export-guard.ts:6`）
NON_VIDEO_OVERHEAD_KBPS = 200


class FramingError(ValueError):
    """构图参数不合法（竞品抛 RangeError）。"""


def get_platform_spec(platform: str) -> dict | None:
    return PLATFORM_SPECS.get(platform)


def platforms_public() -> list[dict]:
    """给前端/接口看的平台清单（顺序稳定，前端不用自己排）。"""
    return [{"id": k, **v, "qr_policy": get_off_site_qr_policy(k)["level"]}
            for k, v in PLATFORM_SPECS.items()]


def get_off_site_qr_policy(platform: str | None) -> dict:
    """二维码烧录政策（竞品 `platform-specs.ts:94-105`）。

    未传平台 → **warn 不是 ok**：片子可能发到国内平台，得把风险说出来而不是沉默。
    """
    if not platform:
        return {
            "level": "warn",
            "zh": ("未指定目标平台：若发抖音等国内平台，成片内二维码属站外导流"
                   "（抖音首违关橱窗 7 天）。发国内平台请传 platform 以便按平台把关"),
            "en": ("No target platform given: on Chinese platforms an in-video QR counts as "
                   "off-site diversion (Douyin: 1st offense closes the shop window for 7 days). "
                   "Pass platform so the risk can be gated per platform"),
        }
    return OFFSITE_QR_POLICIES.get(platform, QR_WARN_DOMESTIC)


# ---------------------------------------------------------------------------
# 构图（竞品 `video-framing.ts:19-52`）
# ---------------------------------------------------------------------------
def parse_framing(value=None) -> dict:
    """校验构图参数。非 crop 模式坐标强制回 0.5（竞品同款）。"""
    if value is None:
        return dict(DEFAULT_FRAMING)
    if not isinstance(value, dict):
        raise FramingError("构图参数无效")
    mode = value.get("mode", "blur")
    if mode not in FRAMING_MODES:
        raise FramingError("构图模式只能是 blur / fit / crop")

    def coordinate(raw):
        if raw is None:
            return 0.5
        if not isinstance(raw, (int, float)) or isinstance(raw, bool):
            raise FramingError("构图位置必须是 0 到 1 之间的数字")
        num = float(raw)
        if num != num or num in (float("inf"), float("-inf")) or not 0 <= num <= 1:
            raise FramingError("构图位置必须是 0 到 1 之间的数字")
        return round(num * 10000) / 10000

    x = coordinate(value.get("positionX"))
    y = coordinate(value.get("positionY"))
    return {"mode": mode,
            "positionX": x if mode == "crop" else 0.5,
            "positionY": y if mode == "crop" else 0.5}


def build_framing_filter(width: int, height: int, framing=None) -> str:
    """构图滤镜（竞品 `video-framing.ts:33-52` 逐字）。

    先按显示宽高比归一化非方形像素，保证预览/裁切/输出比例一致。
    """
    for n in (width, height):
        if not isinstance(n, int) or n < 2 or n > 8192 or n % 2:
            raise FramingError("输出尺寸无效（需为 2–8192 的偶数）")
    f = parse_framing(framing)
    base = "[0:v:0]scale=trunc(iw*sar/2)*2:ih,setsar=1"
    fit = f"scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2"
    fill = f"scale={width}:{height}:force_original_aspect_ratio=increase:force_divisible_by=2"
    if f["mode"] == "crop":
        return (f"{base},{fill},crop={width}:{height}:"
                f"x='(iw-ow)*{f['positionX']}':y='(ih-oh)*{f['positionY']}',"
                "setsar=1,format=yuv420p[vout]")
    if f["mode"] == "fit":
        return (f"{base},{fit},pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
                "setsar=1,format=yuv420p[vout]")
    return (f"{base},split=2[background][foreground];"
            f"[background]{fill},crop={width}:{height},boxblur=24:4[bg];"
            f"[foreground]{fit}[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,"
            "setsar=1,format=yuv420p[vout]")


# ---------------------------------------------------------------------------
# 码率预算与实测（竞品 `export-guard.ts:37-140`）
# ---------------------------------------------------------------------------
def parse_frame_rate(raw: str | None) -> float:
    if not raw:
        return 0.0
    text = str(raw).strip()
    if "/" in text:
        a, _, b = text.partition("/")
        try:
            num, den = float(a), float(b)
        except ValueError:
            return 0.0
        return num / den if den else 0.0
    try:
        num = float(text)
    except ValueError:
        return 0.0
    return num if num > 0 else 0.0


def vbv_args(max_video_kbps: int) -> list[str]:
    """VBV 封顶：视频峰值码率压在（总线上限 − 音频/容器开销）之下。"""
    video_cap = max(1000, int(round(max_video_kbps)) - NON_VIDEO_OVERHEAD_KBPS)
    return ["-maxrate", f"{video_cap}k", "-bufsize", f"{video_cap * 2}k"]


def fps_cap_args(source_fps: float, max_fps: int) -> list[str]:
    """只在源帧率真的超上限时才加 `-r`（竞品注释：无条件加会糊命令）。"""
    if source_fps > 0 and max_fps > 0 and source_fps > max_fps + 0.01:
        return ["-r", str(max_fps)]
    return []


def build_bitrate_report(stats: dict, spec: dict) -> dict:
    """实测码率 vs 平台目标线（竞品 `export-guard.ts:94-137` 逐字口径）。"""
    measured = stats.get("total_kbps") or stats.get("video_kbps") or 0
    cap = int(spec["max_video_kbps"])
    within = bool(measured > 0 and measured <= cap)
    usage = round(measured / cap * 100) if measured > 0 and cap > 0 else 0
    size = f"{stats.get('width', 0)}x{stats.get('height', 0)}"
    fps_text = f"{round(stats.get('fps', 0.0) * 100) / 100}fps" if stats.get("fps") else ""
    if within:
        zh = f"实测码率 {measured} kbps ≤ 编码目标 {cap} kbps（占 {usage}%）；平台仍可能重新编码"
    elif measured > 0:
        zh = f"实测码率 {measured} kbps 超出编码目标 {cap} kbps，上传后可能被平台二次压缩变糊"
    else:
        zh = f"无法读取输出码率，未能确认是否在编码目标 {cap} kbps 内"
    if fps_text:
        zh += f"（{size}·{fps_text}）"
    return {"measured_kbps": measured, "cap_kbps": cap, "within_cap": within,
            "usage_pct": usage, "fps": stats.get("fps", 0.0), "size": size,
            "message": zh}


def probe_encode_stats(path: Path) -> dict:
    """读编码相关指标（码率/帧率/尺寸/时长）。读不到就返回 0，不抛。"""
    fp = ffprobe_path()
    empty = {"total_kbps": 0, "video_kbps": 0, "fps": 0.0,
             "width": 0, "height": 0, "duration": 0.0}
    if not fp:
        return empty
    try:
        p = subprocess.run(
            [fp, "-v", "error",
             "-show_entries",
             "stream=codec_type,width,height,bit_rate,r_frame_rate:format=duration,bit_rate,size",
             "-of", "json", str(path)],
            capture_output=True, text=True, errors="ignore", timeout=60,
        )
        info = json.loads(p.stdout or "{}")
    except Exception:  # noqa: BLE001
        return empty
    streams = info.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    fmt = info.get("format") or {}
    try:
        duration = float(fmt.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    total = int(round(int(fmt.get("bit_rate") or 0) / 1000)) if fmt.get("bit_rate") else 0
    if not total and duration > 0:
        size = int(fmt.get("size") or 0)
        if size > 0:
            total = int(round(size * 8 / duration / 1000))
    return {
        "total_kbps": total,
        "video_kbps": int(round(int(video.get("bit_rate") or 0) / 1000)) if video.get("bit_rate") else 0,
        "fps": parse_frame_rate(video.get("r_frame_rate")),
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "duration": max(0.0, duration),
    }


# ---------------------------------------------------------------------------
# 导出 / 预览（竞品 `platform-export.ts:13-90`）
# ---------------------------------------------------------------------------
def build_export_args(source: Path, out: Path, spec: dict, framing: dict,
                      source_fps: float) -> list[str]:
    ff = ffmpeg_path()
    if not ff:
        raise RuntimeError("找不到 ffmpeg，请设置 VT_FFMPEG")
    return [ff, "-nostdin", "-v", "error", "-y", "-i", str(source),
            "-filter_complex", build_framing_filter(spec["w"], spec["h"], framing),
            "-map", "[vout]", "-map", "0:a:0?", "-map_metadata", "0",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            *vbv_args(spec["max_video_kbps"]), *fps_cap_args(source_fps, spec["max_fps"]),
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            "-c:a", "aac", "-b:a", "192k", str(out)]


def render_export(source: Path, out: Path, spec: dict, framing=None) -> dict:
    """按平台规格重构图并重编码，返回实测报告。

    🩸 先写 `.partial.mp4` 再改名：中途挂了不会留下一个「看起来能播」的半成品
    （竞品 `platform-export.ts:62-84` 同款做法）。
    """
    ff = ffmpeg_path()
    if not ff:
        raise RuntimeError("找不到 ffmpeg，请设置 VT_FFMPEG")
    source, out = Path(source), Path(out)
    if not source.exists():
        raise RuntimeError("成片文件不存在")
    out.parent.mkdir(parents=True, exist_ok=True)
    partial = out.with_name(out.stem + ".partial.mp4")
    src_stats = probe_encode_stats(source)
    args = build_export_args(source, partial, spec, parse_framing(framing),
                             src_stats["fps"])
    p = subprocess.run(args, capture_output=True, text=True, errors="ignore", timeout=1800)
    if p.returncode != 0 or not partial.exists():
        partial.unlink(missing_ok=True)
        raise RuntimeError(f"平台导出失败：{(p.stderr or '')[-200:]}")
    stats = probe_encode_stats(partial)
    same_size = (stats["width"] == spec["w"] and stats["height"] == spec["h"])
    dur_ok = (src_stats["duration"] <= 0 or stats["duration"] <= 0
              or abs(stats["duration"] - src_stats["duration"])
              <= max(0.5, src_stats["duration"] * 0.01))
    if not same_size or not dur_ok:
        partial.unlink(missing_ok=True)
        raise RuntimeError("导出的规格校验没过（尺寸或时长不对），已丢弃产物")
    partial.replace(out)
    return build_bitrate_report(stats, spec)


def preview_frame(source: Path, spec: dict, framing=None, at: float = 0.0) -> str:
    """单帧构图预览（竞品 `platform-export.ts:34-47`）：同一套滤镜，最后缩成 360 宽小图。

    返回 `data:image/jpeg;base64,...` —— 前端直接 <img :src>，不落临时文件。
    """
    import base64

    ff = ffmpeg_path()
    if not ff:
        raise RuntimeError("找不到 ffmpeg，请设置 VT_FFMPEG")
    source = Path(source)
    if not source.exists():
        raise RuntimeError("成片文件不存在")
    filt = build_framing_filter(spec["w"], spec["h"], framing) + ";[vout]scale=360:-2[preview]"
    t = max(0.0, float(at or 0))
    p = subprocess.run(
        [ff, "-nostdin", "-v", "error", "-ss", f"{t:.3f}", "-i", str(source),
         "-filter_complex", filt, "-map", "[preview]", "-frames:v", "1", "-an",
         "-f", "image2pipe", "-c:v", "mjpeg", "-q:v", "3", "pipe:1"],
        capture_output=True, timeout=120,
    )
    if p.returncode != 0 or not p.stdout:
        raise RuntimeError(f"预览帧生成失败：{(p.stderr or b'')[-200:]!r}")
    return "data:image/jpeg;base64," + base64.b64encode(p.stdout).decode("ascii")
