"""yt-dlp 通用解析器（Instagram / Twitter / YouTube）。

为什么走子进程而不是 import：
- yt-dlp 的提取器更新频繁，独立进程升级不影响后端
- 解析（-J 拿元数据）和下载（合并音视频）都交给它，我们只做协议适配

YouTube 注意：本机出口是机房 IP，YouTube 会返回 LOGIN_REQUIRED（见 docs/RESEARCH.md），
这不是代码问题，换出口 IP 后无需改代码。
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys

from app.core.config import settings
from app.parsers.base import MediaInfo, extract_tags

log = logging.getLogger(__name__)


def _base_cmd(proxy: str = "") -> list[str]:
    cmd = [sys.executable, "-m", "yt_dlp", "--no-warnings", "--no-playlist"]
    if proxy:
        cmd += ["--proxy", proxy]
    return cmd


# 把 yt-dlp 的英文报错翻成用户能懂的话
_ERROR_MAP: list[tuple[str, str]] = [
    ("Sign in to confirm you", "平台要求人机验证（服务器 IP 被识别为机房地址），暂时无法解析这个链接"),
    ("Private video", "这是私密视频，无法解析"),
    ("This video is unavailable", "视频已删除或不可用"),
    ("Video unavailable", "视频已删除或不可用"),
    ("No video could be found", "这条内容里没有视频"),
    ("Requested format is not available", "没有可下载的视频格式"),
    ("rate-limit", "请求太频繁，请稍后再试"),
]


def _friendly(msg: str) -> str:
    for key, zh in _ERROR_MAP:
        if key.lower() in msg.lower():
            return f"{zh}（原始信息：{msg[:120]}）"
    return msg[:300]


async def dump_json(url: str, proxy: str = "") -> dict:
    cmd = _base_cmd(proxy) + ["-J", "--skip-download", url]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await asyncio.wait_for(proc.communicate(), timeout=120)
    if proc.returncode != 0 or not out:
        msg = (err or b"").decode("utf-8", "ignore").strip().splitlines()
        raise RuntimeError(_friendly(msg[-1] if msg else "yt-dlp 解析失败"))
    return json.loads(out.decode("utf-8", "ignore"))


def _best_url(info: dict) -> str:
    """挑一个带音轨的直链（仅作预览提示；真正下载走 yt-dlp）。"""
    formats = info.get("formats") or []
    progressive = [
        f for f in formats
        if f.get("url")
        and f.get("vcodec") not in (None, "none")
        and f.get("acodec") not in (None, "none")
    ]
    if progressive:
        # 优先 720p 以内、mp4
        progressive.sort(key=lambda f: (
            0 if f.get("ext") == "mp4" else 1,
            0 if (f.get("height") or 0) <= 720 else 1,
            -(f.get("height") or 0),
        ))
        return progressive[0]["url"]
    for f in formats:
        if f.get("url"):
            return f["url"]
    return info.get("url") or ""


class YtdlpParser:
    def __init__(self, platform: str, hosts: tuple[str, ...]):
        self.platform = platform
        self.hosts = hosts

    def match(self, url: str) -> bool:
        return any(h in url for h in self.hosts)

    def _proxy(self) -> str:
        # YouTube 必须走住宅出口；**X（Twitter）也必须走代理** ——
        # 2026-10-29 开放 X 时才发现这里以前对所有非 youtube 平台一律返回空，
        # 于是就算配了 `VT_PROXY`，twitter 照样直连（国内必然超时 120s）。
        # Instagram 仍直连（省代理流量）。
        if self.platform == "youtube":
            return settings.youtube_proxy or settings.proxy
        if self.platform == "twitter":
            return settings.proxy
        return ""

    async def parse(self, url: str) -> MediaInfo:
        # 🩸 没配代理时 X 直连必然超时，而 `dump_json` 的超时是 120 秒、
        #   外层还会重试（`parse_retries=2`）→ 用户要干等 6 分钟才看到失败。
        #   本机实测 `curl https://x.com/` 10 秒超时。这里直接说清楚原因。
        if self.platform == "twitter" and not self._proxy():
            raise RuntimeError(
                "X（Twitter）需要代理出口才能访问，当前服务没有配置代理，"
                "暂时解析不了这个链接"
            )
        proxy = self._proxy()
        info = await dump_json(url, proxy)

        # 播放列表/轮播：取第一条
        if info.get("_type") == "playlist":
            entries = [e for e in (info.get("entries") or []) if e]
            if not entries:
                raise RuntimeError("没有找到可解析的内容")
            first = entries[0]
            # entries 里有时只有 id/url，需要再取一次
            if not first.get("formats") and not first.get("url"):
                info = await dump_json(first.get("webpage_url") or url)
            else:
                info = first

        video_url = _best_url(info)
        if not video_url:
            raise RuntimeError("这条内容里没有视频（可能是纯图片或已删除）")

        title = info.get("title") or ""
        desc = info.get("description") or ""
        return MediaInfo(
            platform=self.platform,
            title=title or desc[:60],
            desc=desc,
            tags=info.get("tags") or extract_tags(title, desc),
            author=info.get("uploader") or info.get("channel") or "",
            author_avatar=info.get("uploader_avatar") or "",
            cover=info.get("thumbnail") or "",
            video_url=video_url,
            duration=info.get("duration"),
            extra={
                "engine": "ytdlp",
                "source_url": info.get("webpage_url") or url,
                "extractor": info.get("extractor"),
                # 下载必须走同一出口：YouTube 的流地址绑定请求 IP
                "proxy": proxy,
            },
        )
