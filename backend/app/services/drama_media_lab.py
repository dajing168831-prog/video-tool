# -*- coding: utf-8 -*-
"""商品短剧 · B11 媒体解构实验室（一张图 / 一段视频 → 可复用的创作方向）。

出处：clipforge `src/app/api/media/analyze/route.ts:1-111`（上传限制、抽帧、视觉调用）、
`src/lib/media-analysis.ts:1-124`（分析提示词 + 漂移 JSON 的收敛钳制）。

我们的映射：
  · 竞品让前端把 `llmConfig`（含 Key）一起发上来；我们**只从服务端配置读 Key**
    （与 C4 同一条规矩：Key 不出服务端）。
  · 视频抽帧复用本地已有的 `drama_contact_sheet.generate`（竞品 `contact-sheet.ts` 的移植）。
  · 视觉通道 = DeepSeek 官方 `deepseek-flash`（原生读图）。上游原文只进日志，不回前端。
"""
from __future__ import annotations

import base64
import logging
from pathlib import Path

from app.core.config import settings
from app.services import deepseek_chat, drama_contact_sheet, drama_format

log = logging.getLogger(__name__)

#: 竞品 `route.ts:14-18`
IMAGE_MAX = 15 * 1024 * 1024
VIDEO_MAX = 80 * 1024 * 1024
MAX_VIDEO_SECONDS = 180
IMAGE_MIME = {"image/jpeg", "image/png", "image/webp"}
VIDEO_MIME = {"video/mp4", "video/webm", "video/quicktime"}
EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
}
#: 竞品 `media-analysis.ts:26`
MAX_TEXT = 600
MAX_ITEMS = 8


class MediaLabError(ValueError):
    """给界面看的原话（不含上游原文）。"""


def media_type_for(mime: str) -> str | None:
    if mime in IMAGE_MIME:
        return "image"
    if mime in VIDEO_MIME:
        return "video"
    return None


def _text(value, fallback: str = "") -> str:
    """竞品 `media-analysis.ts:28-30`：只收字符串、trim、截 600。"""
    return value.strip()[:MAX_TEXT] if isinstance(value, str) else fallback


def _text_list(value, max_items: int = MAX_ITEMS) -> list[str]:
    """竞品 `media-analysis.ts:32-38`：只收非空字符串、截 120、限量。"""
    if not isinstance(value, list):
        return []
    return [x.strip()[:120] for x in value
            if isinstance(x, str) and x.strip()][:max_items]


def parse_analysis(raw: str, media_type: str) -> dict:
    """把视觉模型飘移的 JSON 收成稳定契约（竞品 `media-analysis.ts:41-71`）。"""
    try:
        obj = drama_format.parse_json(raw)
    except drama_format.FormatError as e:
        raise MediaLabError(f"模型没按格式返回：{e}") from e
    style = obj.get("visualStyle") if isinstance(obj.get("visualStyle"), dict) else {}
    motion_raw = obj.get("motion") if isinstance(obj.get("motion"), dict) else {}
    result = {
        "media_type": media_type,
        "summary": _text(obj.get("summary")),
        "subjects": _text_list(obj.get("subjects")),
        "visual_style": {
            "lighting": _text(style.get("lighting")),
            "palette": _text(style.get("palette")),
            "composition": _text(style.get("composition")),
            "camera": _text(style.get("camera")),
        },
        "reusable_prompt": _text(obj.get("reusablePrompt")),
        "negative_prompt": _text(obj.get("negativePrompt")),
        "suggested_uses": _text_list(obj.get("suggestedUses"), 5),
    }
    if media_type == "video":
        result["motion"] = {
            "pacing": _text(motion_raw.get("pacing")),
            "camera_moves": _text_list(motion_raw.get("cameraMoves")),
            "scene_rhythm": _text(motion_raw.get("sceneRhythm")),
        }
    return result


def analysis_prompt(media_type: str, sample_context: str = "") -> str:
    """竞品 `media-analysis.ts:73-97` 原文（输出语言固定简体中文——我们的界面只有中文）。"""
    kind = "video contact sheet" if media_type == "video" else "image"
    ctx = f"\nSampling context: {sample_context}" if sample_context else ""
    return (
        "You are a senior commercial video art director. "
        f"Analyze the supplied {kind} and return ONLY one JSON object. "
        "Write all values in 简体中文.\n"
        f"{ctx}\n"
        "Do not identify real people. Describe observable visual facts, "
        "production techniques, and reusable creative direction.\n"
        "JSON schema:\n"
        "{\n"
        '  "summary": "concise content and creative-intent description",\n'
        '  "subjects": ["main subject or object"],\n'
        '  "visualStyle": {\n'
        '    "lighting": "light direction, quality and contrast",\n'
        '    "palette": "dominant colors and color relationship",\n'
        '    "composition": "framing, depth and visual hierarchy",\n'
        '    "camera": "shot size, lens feel and viewpoint"\n'
        "  },\n"
        '  "motion": {\n'
        '    "pacing": "video pace; empty string for an image",\n'
        '    "cameraMoves": ["observable or strongly implied movement"],\n'
        '    "sceneRhythm": "cut rhythm and progression; empty string for an image"\n'
        "  },\n"
        '  "reusablePrompt": "a production-ready generation prompt that recreates the '
        'visual language without copying names, logos, text or identity",\n'
        '  "negativePrompt": "failures and artifacts to avoid",\n'
        '  "suggestedUses": ["specific downstream creation use"]\n'
        "}"
    )


def data_uri(path: Path, mime: str) -> str:
    raw = Path(path).read_bytes()
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def analyze_visual(image_data_uri: str, media_type: str,
                   sample_context: str = "") -> dict:
    """一次视觉调用（竞品 `media-analysis.ts:100-124`）。

    Key/模型只从服务端配置读；上游错误原文只进日志。
    """
    key = (settings.deepseek_api_key or "").strip()
    if not key:
        raise MediaLabError("没有配置视觉模型（VT_DEEPSEEK_API_KEY）")
    body = {
        "model": settings.deepseek_model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": analysis_prompt(media_type, sample_context)},
                {"type": "image_url", "image_url": {"url": image_data_uri, "detail": "high"}},
            ],
        }],
        "temperature": 0.2,
        "max_tokens": 2500,
        "stream": False,
    }
    try:
        data = deepseek_chat.post(body, key=key)
    except deepseek_chat.DeepSeekError as e:
        log.warning("[drama] 媒体解构调用失败: %s", e)
        raise MediaLabError("视觉模型调用失败（看后端日志）") from e
    try:
        content = data["choices"][0]["message"]["content"] or ""
    except Exception as e:  # noqa: BLE001
        log.warning("[drama] 媒体解构返回结构异常: %s", str(data)[:300])
        raise MediaLabError("视觉模型返回结构不对（看后端日志）") from e
    return parse_analysis(content, media_type)


def analyze_file(path: Path, *, mime: str, size: int,
                 work_dir: Path) -> dict:
    """按 MIME 分流：图片直接读；视频先出速览图（8 帧），再连采样上下文一起分析。"""
    media_type = media_type_for(mime)
    if not media_type:
        raise MediaLabError("仅支持 JPG、PNG、WebP、MP4、WebM、MOV")
    if size > (IMAGE_MAX if media_type == "image" else VIDEO_MAX):
        raise MediaLabError("图片不能超过 15MB" if media_type == "image" else "视频不能超过 80MB")

    info = drama_contact_sheet.probe_video(Path(path))
    meta = {"width": info.get("width") or 0,
            "height": info.get("height") or 0,
            "size": size}
    visual_path, visual_mime = Path(path), mime
    sample_context = ""

    if media_type == "video":
        duration = float(info.get("duration") or 0)
        if duration <= 0:
            raise MediaLabError("无法读取视频，文件可能损坏")
        if duration > MAX_VIDEO_SECONDS:
            raise MediaLabError("视频最长支持 3 分钟")
        sheet_path = Path(work_dir) / "contact-sheet.png"
        #: 竞品 `route.ts:73`：8 帧 / 缩略 200 px / 波形高 100
        sheet = drama_contact_sheet.generate(Path(path), sheet_path, frames=8,
                                             thumb_width=200, wave_height=100)
        frame_times = sheet.get("frame_times") or []
        cuts = sheet.get("cuts") or []
        visual_path, visual_mime = sheet_path, "image/png"
        sample_context = (
            f"duration {duration:.1f}s; {len(cuts) + 1} detected shots; "
            f"representative frames at "
            f"{', '.join(f'{t}s' for t in frame_times) or 'even intervals'}")
        meta.update({"duration": duration,
                     "has_audio": bool(info.get("has_audio")),
                     "shot_count": len(cuts) + 1,
                     "frame_times": frame_times})

    result = analyze_visual(data_uri(visual_path, visual_mime), media_type, sample_context)
    result["metadata"] = meta
    return result
