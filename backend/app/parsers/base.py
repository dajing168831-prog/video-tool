"""解析器统一契约。

所有平台解析器都实现 BaseParser，业务层只依赖 MediaInfo。
换引擎（自研 / 外部服务 / 第三方 API）时，只要实现这个接口，上层零改动。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class MediaInfo:
    """一次解析的标准产物。"""

    platform: str                 # douyin / kuaishou / bilibili / xiaohongshu / tiktok ...
    title: str = ""               # 标题
    desc: str = ""                # 描述正文
    tags: list[str] = field(default_factory=list)  # #话题
    author: str = ""              # 作者昵称
    author_avatar: str = ""       # 作者头像
    cover: str = ""               # 封面 URL
    video_url: str = ""           # 无水印原片直链
    images: list[str] = field(default_factory=list)  # 图集（与 video_url 二选一）
    duration: float | None = None  # 秒，解析时拿不到由 ffprobe 补
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_video(self) -> bool:
        return bool(self.video_url)

    @property
    def is_image_post(self) -> bool:
        return not self.video_url and bool(self.images)


class BaseParser(Protocol):
    """解析器协议。"""

    platform: str

    def match(self, url: str) -> bool:
        ...

    async def parse(self, url: str) -> MediaInfo:
        ...


# ---------------------------------------------------------------------------
# 平台识别
# ---------------------------------------------------------------------------
PLATFORM_PATTERNS: list[tuple[str, str]] = [
    ("douyin", r"(douyin\.com|iesdouyin\.com|v\.douyin\.com)"),
    ("kuaishou", r"(kuaishou\.com|chenzhongtech\.com|v\.kuaishou\.com)"),
    ("xiaohongshu", r"(xiaohongshu\.com|xhslink\.com|xhslink\.cn)"),
    ("bilibili", r"(bilibili\.com|b23\.tv)"),
    # tiktokv.com：App 内分享会带这个域名；TikTokParser.match 本来就认它，
    # 这里漏掉就会在「平台识别」就被判不支持，永远走不到解析器。
    ("tiktok", r"(tiktok\.com|tiktokv\.com)"),
    ("youtube", r"(youtube\.com|youtu\.be)"),
    ("instagram", r"instagram\.com"),
    ("twitter", r"(twitter\.com|x\.com)"),
]

_URL_RE = re.compile(r"https?://[^\s一-鿿\"'<>]+")
_TAG_RE = re.compile(r"#([^\s#]{1,40})")


def extract_url(text: str) -> str | None:
    """从分享文案中抽出第一个 URL。"""
    text = (text or "").strip()
    if not text:
        return None
    m = _URL_RE.search(text)
    return m.group(0).rstrip("，。,、！!？?）)】]") if m else None


def detect_platform(url: str) -> str | None:
    for name, pat in PLATFORM_PATTERNS:
        if re.search(pat, url, re.I):
            return name
    return None


def extract_tags(*texts: str) -> list[str]:
    seen: list[str] = []
    for t in texts:
        for tag in _TAG_RE.findall(t or ""):
            if tag not in seen:
                seen.append(tag)
    return seen
