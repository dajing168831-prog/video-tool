"""TikTok 解析（不需要 cookies）。

背景（见 docs/RESEARCH.md）：
- 本机直连 tiktok.com 会被降级重定向（x-redirect-reason: www.tiktok.com_allow），
  页面里没有 playAddr，纯自研不可行
- 公开解析接口（如 tikwm）可以拿到无水印流，免费但有速率限制
- 因此这里做成「多源 provider」：主源失败自动切备用源

新增数据源只需实现 _fetch_xxx 并在 SOURCES 里注册。
"""
from __future__ import annotations

import logging
from typing import Awaitable, Callable

import httpx

from app.core.config import settings
from app.parsers.base import MediaInfo, extract_tags, extract_url

log = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)


async def _fetch_tikwm(url: str) -> dict:
    """主源：tikwm 公开接口。返回统一中间结构。"""
    async with httpx.AsyncClient(
        timeout=settings.http_timeout, follow_redirects=True, headers={"User-Agent": _UA}
    ) as c:
        r = await c.get("https://www.tikwm.com/api/", params={"url": url})
        r.raise_for_status()
        body = r.json()
    if body.get("code") != 0:
        raise RuntimeError(f"tikwm: {body.get('msg')}")
    d = body.get("data") or {}
    play = d.get("play") or ""
    if play and play.startswith("/"):
        play = "https://www.tikwm.com" + play
    music = d.get("music") or ""
    if music and music.startswith("/"):
        music = "https://www.tikwm.com" + music
    author = d.get("author") or {}
    return {
        "title": d.get("title") or "",
        "video_url": play,
        "audio_url": music,
        "cover": d.get("cover") or "",
        "duration": d.get("duration"),
        "author": author.get("nickname") or author.get("unique_id") or "",
        "author_avatar": author.get("avatar") or "",
        "source": "tikwm",
    }


# 数据源注册表：按顺序尝试
SOURCES: list[tuple[str, Callable[[str], Awaitable[dict]]]] = [
    ("tikwm", _fetch_tikwm),
]


class TikTokParser:
    platform = "tiktok"

    def match(self, url: str) -> bool:
        return "tiktok.com" in url or "tiktokv.com" in url

    async def parse(self, url: str) -> MediaInfo:
        clean = extract_url(url) or url
        last_err: Exception | None = None
        for name, fetch in SOURCES:
            try:
                d = await fetch(clean)
                if not d.get("video_url"):
                    raise RuntimeError("数据源没有返回视频地址")
                title = d.get("title") or ""
                return MediaInfo(
                    platform="tiktok",
                    title=title,
                    desc=title,
                    tags=extract_tags(title),
                    author=d.get("author") or "",
                    author_avatar=d.get("author_avatar") or "",
                    cover=d.get("cover") or "",
                    video_url=d.get("video_url") or "",
                    duration=d.get("duration"),
                    extra={"source": d.get("source"), "audio_url": d.get("audio_url")},
                )
            except Exception as e:  # noqa: BLE001
                last_err = e
                log.warning("TikTok 数据源 %s 失败: %s", name, str(e)[:200])
        raise RuntimeError(f"TikTok 解析失败（所有数据源）：{last_err}") from last_err
