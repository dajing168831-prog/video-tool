"""小红书解析（SSR 状态注入 + 双 UA 自适应）。

依据：media-parser/docs/parsers/xiaohongshu.md（MIT）的逆向方案
1. 用户在 App 分享的链接天然带 xsec_token / xsec_source，**必须原样保留**
2. App 短链优先 Mobile UA，PC 长链优先 PC UA，失败自动回退
3. 数据在 window.__INITIAL_STATE__（Nuxt SSR），需清洗 JS 表达式
4. 高频匿名抓取会被风控 302 到 /login —— 此时如实报错，不伪造成功

可选环境变量 VT_XHS_COOKIE（a1=...; webId=...）用于提高成功率。
"""
from __future__ import annotations

import json
import logging
import os
import re

import httpx

from app.core.config import settings
from app.parsers.base import MediaInfo, extract_tags, extract_url

log = logging.getLogger(__name__)

PC_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
    "Mobile/15E148 Safari/604.1"
)

_STATE_RE = re.compile(r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*</script>", re.S)


def _clean_js_json(raw: str) -> str:
    raw = re.sub(r"\bundefined\b", "null", raw)
    raw = re.sub(r"new\s+Map\s*\([^)]*\)", "{}", raw)
    raw = re.sub(r"new\s+Set\s*\([^)]*\)", "[]", raw)
    raw = re.sub(r"new\s+Date\s*\([^)]*\)", "null", raw)
    return raw


def _extract_state(html: str) -> dict | None:
    m = _STATE_RE.search(html)
    if not m:
        return None
    try:
        return json.loads(_clean_js_json(m.group(1)))
    except Exception as e:  # noqa: BLE001
        log.warning("小红书 INITIAL_STATE 解析失败: %s", e)
        return None


def _pick_note(state: dict) -> dict | None:
    note = state.get("note") or {}
    nid = note.get("firstNoteId")
    detail = note.get("noteDetailMap") or {}
    if nid and nid in detail:
        return (detail[nid] or {}).get("note")
    # 兜底：取第一条非空
    for v in detail.values():
        n = (v or {}).get("note")
        if n:
            return n
    return None


def _pick_stream_url(note: dict) -> str:
    video = note.get("video") or {}
    media = video.get("media") or {}
    stream = media.get("stream") or {}
    for codec in ("h264", "h265", "av1"):
        arr = stream.get(codec) or []
        for item in arr:
            u = item.get("masterUrl") or item.get("backupUrls", [None])[0]
            if u:
                return u
    # 部分版本字段不同
    for key in ("consumer", "originVideoKey"):
        if media.get(key):
            val = media[key]
            if isinstance(val, dict):
                v = val.get("originVideoKey") or val.get("masterUrl")
                if v:
                    return v
            elif isinstance(val, str):
                return val
    return ""


def _pick_images(note: dict) -> list[str]:
    out: list[str] = []
    for img in (note.get("imageList") or []):
        u = img.get("urlDefault") or img.get("url") or ""
        u = _https(u)
        if u and u not in out:
            out.append(u)
    return out


def _https(u: str) -> str:
    """xhscdn 直链常给 http，页面是 https，必须升级否则浏览器混合内容拦截。"""
    return u.replace("http://", "https://", 1) if u.startswith("http://") else u


def _clean_desc(desc: str) -> str:
    """去掉分享文案里的平台标记（如 `#ai[话题]#` 的 `[话题]`）。"""
    return re.sub(r"\[话题\]", "", desc or "").strip()


class XiaohongshuParser:
    platform = "xiaohongshu"

    def match(self, url: str) -> bool:
        return "xiaohongshu.com" in url or "xhslink.com" in url or "xhslink.cn" in url

    async def parse(self, url: str) -> MediaInfo:
        clean = extract_url(url) or url

        cookie = os.environ.get("VT_XHS_COOKIE", "").strip()
        headers_base = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        if cookie:
            headers_base["Cookie"] = cookie

        # 实测：PC UA 才有 SSR 笔记数据；移动 UA 返回空壳（noteDetailMap 为 0 条）。
        # 所以 PC 优先，移动仅作兜底。
        last_err: Exception | None = None
        note = None
        for ua in (PC_UA, MOBILE_UA):
            try:
                async with httpx.AsyncClient(
                    timeout=settings.http_timeout,
                    follow_redirects=True,
                    headers={**headers_base, "User-Agent": ua},
                ) as c:
                    r = await c.get(clean)
                final_url = str(r.url)
                if "/login" in final_url:
                    raise RuntimeError("被风控重定向到登录页（可配置 VT_XHS_COOKIE 提升成功率）")
                state = _extract_state(r.text)
                if not state:
                    raise RuntimeError("页面无 __INITIAL_STATE__")
                note = _pick_note(state)
                if note:
                    break
                err_code = re.search(r"error_code=(\d+)", final_url)
                raise RuntimeError(
                    f"页面无笔记数据（error_code={err_code.group(1) if err_code else '未知'}）"
                )
            except Exception as e:  # noqa: BLE001
                last_err = e
                log.warning("小红书 UA 尝试失败(%s): %s", ua[:30], str(e)[:160])

        if not note:
            raise RuntimeError(
                f"小红书解析失败：{last_err or '无笔记数据'}。"
                "请用小红书 App「分享→复制链接」的原始链接（裸链接/过期链接没有 xsec_token，必失败）"
            )

        title = note.get("title") or ""
        desc = _clean_desc(note.get("desc") or "")
        user = note.get("user") or {}
        video_url = _https(_pick_stream_url(note))
        images = _pick_images(note)

        if not video_url and not images:
            raise RuntimeError("小红书笔记既没有视频流也没有图片")

        # 平台自带 tagList 最准；没有再退回正则
        tags = [t.get("name") for t in (note.get("tagList") or []) if t.get("name")] \
            or extract_tags(title, desc)

        return MediaInfo(
            platform="xiaohongshu",
            title=title or desc[:60],
            desc=desc,
            tags=tags,
            author=user.get("nickname") or "",
            author_avatar=_https(user.get("avatar") or ""),
            cover=images[0] if images else "",
            video_url=video_url,
            images=images,
            extra={"note_id": note.get("noteId"), "type": note.get("type")},
        )
