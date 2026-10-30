"""parse-video-py 适配器：覆盖抖音 / 快手 / 小红书 / B站 / 微博 / Twitter 等。

选它的原因（见 docs/RESEARCH.md）：
- MIT 许可、纯 Python、零数据库
- 本机实测抖音 / 快手 / B站 全部通过

已知问题及对策：
- 快手偶发解析失败 → 带重试
- 小红书需要 cookies → 失败时如实报错，不伪造成功
"""
from __future__ import annotations

import asyncio
import logging

from app.core.config import settings
from app.parsers.base import MediaInfo, extract_tags, extract_url

log = logging.getLogger(__name__)

# 该引擎覆盖、且我们对外开放的平台
SUPPORTED_PLATFORMS = {
    "douyin",
    "kuaishou",
    "xiaohongshu",
    "bilibili",
    "twitter",
}


class PvpParser:
    platform = "pvp"

    def match(self, url: str) -> bool:
        from app.parsers.base import detect_platform

        return detect_platform(url) in SUPPORTED_PLATFORMS

    async def parse(self, url: str) -> MediaInfo:
        from parse_video_py import parse_video_share_url

        from app.parsers.base import detect_platform

        clean_url = extract_url(url) or url
        platform = detect_platform(clean_url) or "unknown"

        last_err: Exception | None = None
        attempts = settings.parse_retries + 1
        for i in range(attempts):
            try:
                raw = await asyncio.wait_for(
                    parse_video_share_url(clean_url), timeout=settings.http_timeout
                )
                if raw is None:
                    raise RuntimeError("解析器返回空结果")
                return self._to_media(raw, platform)
            except Exception as e:  # noqa: BLE001
                last_err = e
                log.warning(
                    "解析失败 platform=%s attempt=%d/%d err=%s",
                    platform, i + 1, attempts, str(e)[:200],
                )
                if i < attempts - 1:
                    # 指数退避：抖音 slidesinfo 对高频请求敏感，线性退避常有整段失败
                    await asyncio.sleep(settings.parse_retry_delay * (2 ** i))

        raise RuntimeError(f"{platform} 解析失败：{last_err}") from last_err

    @staticmethod
    def _to_media(raw, platform: str) -> MediaInfo:
        author = getattr(raw, "author", None)
        title = getattr(raw, "title", "") or ""
        images = [getattr(i, "url", "") for i in (getattr(raw, "images", None) or [])]
        images = [u for u in images if u]

        desc = title  # 该引擎的 title 通常就是完整文案
        return MediaInfo(
            platform=platform,
            title=title,
            desc=desc,
            tags=extract_tags(title),
            author=getattr(author, "name", "") or "",
            author_avatar=getattr(author, "avatar", "") or "",
            cover=getattr(raw, "cover_url", "") or "",
            video_url=getattr(raw, "video_url", "") or "",
            images=images,
            # 上游给的是秒；拿不到就留 None，由 ffprobe 在落盘后补
            duration=(float(getattr(raw, "duration", 0) or 0) or None),
        )
