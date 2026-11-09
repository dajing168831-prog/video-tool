"""免版权素材搜索（B3）—— 多源检索 + 许可硬过滤 + 下载入库。

出处（竞品 `C:/tmp/harvest/product-drama/clipforge/src/lib/providers/`）：
  · `stock-types.ts:9-20` 源清单（10 个）、`:22-58` 统一候选结构
  · `stock-types.ts:166-169` 下载上限 80MB / 请求超时 30s
  · `stock-types.ts:174-192` 朝向判定 + 按时长过滤
  · `stock-types.ts:194-215` 扩展名推断（**先看 content-type，再看 URL，最后按媒体类型兜底**）
  · `stock-types.ts:240-287` 下载：大小闸 + 先写 `.part` 再 rename（半截文件永不落地）
  · `stock-registry.ts:44-60` 有 Key 才参与（免 Key 源始终参与）
  · `stock-registry.ts:141-147` 结果缓存 5 分钟 / 64 条
  · `stock-registry.ts:149-193` 并发聚合（单个源失败不拖垮其他源）
  · `stock-registry.ts:200-228` 排序：媒体类型 → 本地 → 免 Key → 朝向 → 短边分辨率
  · `openverse.ts:117-164`、`wikimedia.ts:117-173`、`nasa.ts:14-92`、`archive.ts:20-99`
    四个免 Key 源；`pexels.ts:81-211`、`pixabay.ts:...`、`coverr.ts`、`jamendo.ts`、`freesound.ts` 五个要 Key 的源

许可硬过滤（照抄，不是我们加的）：
  · Openverse 检索带 `license_type=commercial`，排除 NC（`openverse.ts:130`）
  · Jamendo 服务端 `ccnc/ccnd/ccsa=false`，**客户端再逐条只认纯 CC-BY**
    （`jamendo.ts:45-47`；SA 也排掉 —— 同步进视频属于改编，SA 会传染给成片）
  · Freesound 只收 CC0 / CC-BY 两类，客户端再验一次（`freesound.ts:41-53`）
  · Archive 查询强制 `licenseurl:*publicdomain*`（`archive.ts:48`）
  · Wikimedia 视频只收 ≤720p 的 webm 转码，原片 .ogv 直接丢（`wikimedia.ts:72-92`）

我们的差异（都因为数据模型不同）：
  1. 下载落地**直接进素材库**（图/视频）或 **BGM 位**（音频），带 author/license/source_url/provider，
     B5 授权清单与发布门禁读的就是这两处，不需要另建 assets 表。
  2. 音频若不是 mp3/wav/aac/m4a（如 .ogg），用 ffmpeg 转 mp3 再进 BGM —— 否则 20MB 白名单会把它拒掉。
  3. 候选先落**进程内短期缓存**，导入时只传 `source + media_type + id`，不让前端传下载地址
     （防 SSRF，也防客户端篡改作者/许可进授权清单）。
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote, urlparse

import requests

#: 单个文件上限（`stock-types.ts:167`）
MAX_DOWNLOAD_BYTES = 80 * 1024 * 1024
#: 单次请求超时（`stock-types.ts:169`）
REQUEST_TIMEOUT = 30.0
#: 聚合结果缓存（`stock-registry.ts:141`）
CACHE_TTL_SECONDS = 5 * 60
CACHE_MAX = 64
#: 候选缓存：搜索 → 用户点「加入素材库」之间不重查（本机实现，竞品是把候选直接回给前端再下载）
PICK_TTL_SECONDS = 10 * 60

MEDIA_TYPES = ("video", "image", "audio")
ORIENTATIONS = ("portrait", "landscape", "square")

#: 源清单（`stock-types.ts:78-164`，顺序照抄：免 Key 在前）
SOURCES: list[dict] = [
    {
        "id": "openverse", "label": "Openverse", "keyless": True,
        "media_types": ["image", "audio"], "signup_url": "https://api.openverse.org/",
        "env_key": "OPENVERSE_TOKEN",
        "note": "免 Key，CC 授权图片 + 音乐/音效（没有视频）",
    },
    {
        "id": "wikimedia", "label": "Wikimedia Commons", "keyless": True,
        "media_types": ["image", "video", "audio"], "signup_url": "https://commons.wikimedia.org/",
        "env_key": "",
        "note": "免 Key，CC/公共领域图 + 视频 + 音频；唯一免 Key 的视频源，视频只收 ≤720p webm",
    },
    {
        "id": "pexels", "label": "Pexels", "keyless": False,
        "media_types": ["video", "image"], "signup_url": "https://www.pexels.com/api/",
        "env_key": "PEXELS_API_KEY",
        "note": "免费 Key，高质量可商用视频 + 图片",
    },
    {
        "id": "pixabay", "label": "Pixabay", "keyless": False,
        "media_types": ["video", "image"], "signup_url": "https://pixabay.com/api/docs/",
        "env_key": "PIXABAY_API_KEY",
        "note": "免费 Key，视频 + 图片，带货实拍主力补充源",
    },
    {
        "id": "coverr", "label": "Coverr", "keyless": False,
        "media_types": ["video"], "signup_url": "https://coverr.co/developers",
        "env_key": "COVERR_API_KEY",
        "note": "免费 Key，精选实拍视频，API 取用的内容要求署名 Coverr",
    },
    {
        "id": "jamendo", "label": "Jamendo 音乐", "keyless": False,
        "media_types": ["audio"], "signup_url": "https://devportal.jamendo.com/",
        "env_key": "JAMENDO_CLIENT_ID",
        "note": "免费 Key，CC 音乐；已强制过滤成纯 CC-BY（NC/ND/SA 全排掉）",
    },
    {
        "id": "freesound", "label": "Freesound 音效", "keyless": False,
        "media_types": ["audio"], "signup_url": "https://freesound.org/apiv2/apply/",
        "env_key": "FREESOUND_API_KEY",
        "note": "免费 Key，音效库；只收 CC0 / CC-BY，取 128k 预览直链",
    },
    {
        "id": "local", "label": "本地素材", "keyless": True,
        "media_types": ["video", "image"], "signup_url": "",
        "env_key": "",
        "note": "用项目里已上传的素材配画面，免网络免 Key",
    },
    {
        "id": "nasa", "label": "NASA 影像库", "keyless": True,
        "media_types": ["video", "image"], "signup_url": "",
        "env_key": "", "aggregate": False,
        "note": "免 Key，公共领域地球/太空/科学实拍；不参与默认聚合，要显式选",
    },
    {
        "id": "archive", "label": "Internet Archive", "keyless": True,
        "media_types": ["video", "image"], "signup_url": "",
        "env_key": "", "aggregate": False,
        "note": "免 Key，公共领域历史影片/纪录素材（强制 publicdomain）；不参与默认聚合",
    },
]

_BY_ID = {s["id"]: s for s in SOURCES}

def _host_is_public(hostname: str) -> bool:
    """防 SSRF：下载地址只许指向公网（内网 / 回环 / 链路本地一律拒）。

    不按源做域名白名单 —— Openverse 的图散布在 Flickr、博物馆等第三方站点，
    写死白名单会把正版素材挡在外面；候选本身只可能来自我们自己的检索结果
    （`remember` 只收服务端构造的候选），所以真正的风险是「被污染的响应指向内网」。
    """
    try:
        infos = socket.getaddrinfo(hostname, None)
    except OSError:
        return False
    if not infos:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(str(info[4][0]).split("%")[0])
        except ValueError:
            return False
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return False
    return True


class StockError(RuntimeError):
    """某个源检索失败（单源失败不影响聚合）。"""


# ---------------------------------------------------------------- 纯函数

def orientation_of(width: float, height: float) -> str:
    """朝向（`stock-types.ts:174-178`）"""
    if height > width:
        return "portrait"
    if width > height:
        return "landscape"
    return "square"


def filter_by_duration(candidates: list[dict], min_sec=None, max_sec=None) -> list[dict]:
    """按时长过滤；没有时长的（图片）不过滤（`stock-types.ts:181-192`）"""
    out = []
    for c in candidates:
        d = c.get("duration_sec")
        if d is None:
            out.append(c)
            continue
        if min_sec is not None and d < min_sec:
            continue
        if max_sec is not None and d > max_sec:
            continue
        out.append(c)
    return out


def infer_extension(url: str, content_type: str | None = None, media_type: str | None = None) -> str:
    """扩展名推断：content-type → URL 后缀 → 媒体类型兜底（`stock-types.ts:194-215`）"""
    ct_map = {
        "video/mp4": "mp4", "video/webm": "webm", "image/jpeg": "jpg", "image/png": "png",
        "image/webp": "webp", "audio/mpeg": "mp3", "audio/mp3": "mp3", "audio/ogg": "ogg",
        "audio/wav": "wav", "audio/x-wav": "wav", "audio/mp4": "m4a", "audio/aac": "aac",
    }
    ct = str(content_type or "").split(";")[0].strip().lower()
    if ct in ct_map:
        return ct_map[ct]
    m = re.search(r"\.([a-zA-Z0-9]{2,4})$", str(url or "").split("?")[0])
    if m:
        return m.group(1).lower()
    return {"image": "jpg", "audio": "mp3"}.get(media_type or "", "mp4")


def rank_candidates(candidates: list[dict], media_type: str, orientation: str | None = None) -> list[dict]:
    """聚合排序（`stock-registry.ts:200-228`）：类型对 → 本地 → 免 Key → 朝向 → 短边大"""
    keyless = {s["id"] for s in SOURCES if s.get("keyless")}

    def orient_match(c: dict) -> bool:
        if not (orientation and c.get("width") and c.get("height")):
            return False
        return orientation_of(c["width"], c["height"]) == orientation

    def key(c: dict):
        return (
            0 if c.get("media_type") == media_type else 1,
            0 if c.get("source") == "local" else 1,
            0 if c.get("source") in keyless else 1,
            0 if (orientation and orient_match(c)) else 1,
            -min(int(c.get("width") or 0), int(c.get("height") or 0)),
        )

    return sorted(candidates, key=key)


def source_key(source_id: str, keys: dict | None = None) -> str:
    """取该源的 Key：本次传的优先，其次环境变量（`stock-registry.ts:44-50`）"""
    meta = _BY_ID.get(source_id) or {}
    v = (keys or {}).get(source_id)
    if v:
        return str(v)
    env = meta.get("env_key") or ""
    return os.environ.get(env, "") if env else ""


def is_available(meta: dict, keys: dict | None = None) -> bool:
    """免 Key 源永远可用（`stock-registry.ts:53-55`）"""
    return bool(meta.get("keyless")) or bool(source_key(str(meta.get("id")), keys))


def list_sources(keys: dict | None = None) -> list[dict]:
    """给前端渲染源选择（`route.ts:33-46`）"""
    out = []
    for s in SOURCES:
        row = dict(s)
        row["available"] = is_available(s, keys)
        out.append(row)
    return out


def pick_candidate(candidates: list[dict], media_type: str | None = None) -> dict | None:
    """按媒体类型取第一条（导入时用）"""
    for c in candidates:
        if media_type and c.get("media_type") != media_type:
            continue
        if c.get("download_url"):
            return c
    return None


# ---------------------------------------------------------------- HTTP
# 🩸 用 requests 不用 httpx：Wikimedia 的机器人策略按 **TLS 指纹** 拦，同一 UA 下
# httpx(OpenSSL) 稳定 403、requests(urllib3) 稳定 200（2026-11-06 实测 6 组请求头）。
# 这不是换个 UA 能救的（curl 的 UA 塞进 httpx 也 403），所以 HTTP 层固定用 requests。

# Wikimedia 的图片/视频下载集群**要求 UA 带联系方式**，否则整段 IP 被 429（429 的是 UA 不是配额）。
# 可用环境变量 STOCK_USER_AGENT 换成自己的联系方式。
USER_AGENT = os.getenv("STOCK_USER_AGENT") or "video-tool/1.0 (+https://dajinggl.top; stock media search)"


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "*/*"})
    return s


def _get_json(url: str, *, headers: dict | None = None, params: dict | None = None):
    with _session() as ses:
        res = ses.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
        if res.status_code >= 400:
            raise StockError(f"{res.status_code}: {res.text[:200]}")
        return res.json()


def _candidate(source: str, media_type: str, ident, download_url: str, page_url: str = "",
               author: str = "", author_url: str = "", license: str = "",
               license_url: str = "", attribution_text: str = "",
               requires_attribution: bool = False, width=None, height=None,
               duration_sec=None, preview_image: str = "", title: str = "",
               tags: list | None = None) -> dict:
    """统一候选（`stock-types.ts:26-58`）"""
    return {
        "source": source, "media_type": media_type, "id": str(ident),
        "download_url": download_url, "page_url": page_url,
        "author": author or "Unknown", "author_url": author_url or page_url,
        "license": license, "license_url": license_url,
        "attribution_text": attribution_text,
        "requires_attribution": bool(requires_attribution),
        "width": int(width) if width else 0, "height": int(height) if height else 0,
        "duration_sec": float(duration_sec) if duration_sec else None,
        "preview_image": preview_image or "", "title": title or "",
        "tags": tags or [],
    }


# ---------------------------------------------------------------- 免 Key 源

def _openverse(query: str, media_type: str, per_page: int, token: str = "") -> list[dict]:
    """Openverse（`openverse.ts:117-164`）：图/音频，检索带 license_type=commercial 排掉 NC"""
    kind = "audio" if media_type == "audio" else "images"
    if media_type == "video":
        # 没有视频端点 → 退回图片（`stock-registry.ts:82-85`）
        kind = "images"
        media_type = "image"
    params = {"q": query.strip(), "page_size": str(per_page), "mature": "false",
              "license_type": "commercial"}
    headers = {"User-Agent": "video-tool/1.0 (stock media)"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = _get_json(f"https://api.openverse.org/v1/{kind}/", headers=headers, params=params)
    out = []
    for item in (data.get("results") or []):
        lic = str(item.get("license") or "")
        if kind == "images":
            url = item.get("url") or ""
            if not url:
                continue
            out.append(_candidate(
                "openverse", "image", item.get("id"), url,
                page_url=item.get("foreign_landing_url") or url,
                author=item.get("creator") or "Unknown",
                author_url=item.get("creator_url") or item.get("foreign_landing_url") or "https://openverse.org",
                license=f"{lic}-{item.get('license_version')}" if item.get("license_version") else lic,
                license_url=item.get("license_url") or "",
                attribution_text=item.get("attribution") or "",
                requires_attribution=lic.lower() not in ("cc0", "pdm"),
                width=item.get("width"), height=item.get("height"),
                preview_image=item.get("thumbnail") or "",
                title=item.get("title") or "",
            ))
        else:
            # 取码率最高的 alt_files（`openverse.ts:84-88`）
            alts = sorted(item.get("alt_files") or [],
                          key=lambda a: -(a.get("bit_rate") or 0))
            url = (alts[0].get("url") if alts else "") or item.get("url") or ""
            if not url:
                continue
            dur = item.get("duration")
            out.append(_candidate(
                "openverse", "audio", item.get("id"), url,
                page_url=item.get("foreign_landing_url") or url,
                author=item.get("creator") or "Unknown",
                author_url=item.get("creator_url") or item.get("foreign_landing_url") or "https://openverse.org",
                license=f"{lic}-{item.get('license_version')}" if item.get("license_version") else lic,
                license_url=item.get("license_url") or "",
                attribution_text=item.get("attribution") or "",
                requires_attribution=lic.lower() not in ("cc0", "pdm"),
                duration_sec=(dur / 1000.0) if dur else None,
                preview_image=item.get("thumbnail") or "",
                title=item.get("title") or "",
            ))
    return out


def _strip_html(value: str | None) -> str:
    """Commons 的 Artist/License 字段常带 <a> 标签（`wikimedia.ts:54-56`）"""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", "", str(value or ""))).strip()


def _wikimedia_pick_video(derivatives: list, fallback: str) -> str | None:
    """视频只要 ≤720p 的 webm 转码；没有就丢（`wikimedia.ts:72-92`）"""
    webm = [d for d in (derivatives or [])
            if d.get("src") and re.search(r"webm", f"{d.get('transcodekey') or ''} {d.get('type') or ''}", re.I)]

    def height(d: dict) -> int:
        if isinstance(d.get("height"), (int, float)):
            return int(d["height"])
        m = re.search(r"(\d+)p", str(d.get("transcodekey") or ""))
        return int(m.group(1)) if m else 0

    if not webm:
        return None
    webm.sort(key=height)
    ok = [d for d in webm if height(d) <= 720]
    return (ok[-1] if ok else webm[-1]).get("src") or None


def _wikimedia(query: str, media_type: str, per_page: int) -> list[dict]:
    """Wikimedia Commons（`wikimedia.ts:117-158`）"""
    filetype = {"video": "filetype:video", "audio": "filetype:audio"}.get(media_type, "filetype:bitmap")
    params = {
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": f"{query.strip()} {filetype}", "gsrnamespace": "6",
        "gsrlimit": str(per_page),
    }
    if media_type == "video":
        params.update({"prop": "videoinfo",
                       "viprop": "url|size|mime|extmetadata|user|derivatives",
                       "viurlwidth": "640"})
    else:
        params.update({"prop": "imageinfo",
                       "iiprop": "url|size|mime|extmetadata|user",
                       "iiurlwidth": "640"})
    headers = {"Api-User-Agent": "video-tool/1.0 (stock media search)"}
    data = _get_json("https://commons.wikimedia.org/w/api.php", headers=headers, params=params)
    pages = (data.get("query") or {}).get("pages") or {}
    out = []
    for page in (pages.values() if isinstance(pages, dict) else []):
        info = ((page.get("videoinfo") or [None])[0] or (page.get("imageinfo") or [None])[0] or {})
        url = info.get("url") or ""
        if not url:
            continue
        ext = info.get("extmetadata") or {}
        lic = _strip_html((ext.get("LicenseShortName") or {}).get("value")) or "Unknown"
        mime = str(info.get("mime") or "")
        is_audio = media_type == "audio" or mime.startswith("audio/")
        is_video = (not is_audio) and (media_type == "video" or mime.startswith("video/"))
        if is_video:
            dl = _wikimedia_pick_video(info.get("derivatives") or [], url)
            if not dl:
                continue  # 没有 webm 转码 → 丢掉（原片太大且格式不通用）
        else:
            dl = url
        page_url = f"https://commons.wikimedia.org/wiki/{quote(str(page.get('title') or ''))}"
        short = lic.lower()
        out.append(_candidate(
            "wikimedia", "audio" if is_audio else "video" if is_video else "image",
            page.get("pageid"), dl, page_url=page_url,
            author=_strip_html((ext.get("Artist") or {}).get("value")) or info.get("user") or "Unknown",
            author_url=page_url, license=lic,
            license_url=(ext.get("LicenseUrl") or {}).get("value") or "",
            requires_attribution=not ("public domain" in short or "pd-" in short or "cc0" in short),
            width=info.get("width"), height=info.get("height"),
            duration_sec=info.get("duration"),
            preview_image=info.get("thumburl") or "",
            title=re.sub(r"\.[a-z0-9]+$", "", re.sub(r"^File:", "", str(page.get("title") or "")), flags=re.I),
        ))
    return out


def _nasa_pick(urls: list, media_type: str) -> str | None:
    """NASA：video 取 medium/large/mobile/small 的 mp4，图取 large/medium/orig（`nasa.ts:15-28`）"""
    if media_type == "video":
        mp4 = [u for u in urls if str(u).lower().endswith(".mp4")]
        for tag in ("medium", "large", "mobile", "small"):
            hit = next((u for u in mp4 if f"~{tag}.mp4" in u), None)
            if hit:
                return hit.replace("http:", "https:")
        return (mp4[0].replace("http:", "https:") if mp4 else None)
    imgs = [u for u in urls if re.search(r"\.(jpe?g|png)$", u, re.I)]
    for tag in ("large", "medium", "orig"):
        hit = next((u for u in imgs if f"~{tag}." in u), None)
        if hit:
            return hit.replace("http:", "https:")
    return imgs[0].replace("http:", "https:") if imgs else None


def _nasa(query: str, media_type: str, per_page: int) -> list[dict]:
    """NASA 影像库（两步：检索 → collection.json 取文件，`nasa.ts:34-92`）"""
    per_page = max(1, min(12, per_page))
    data = _get_json("https://images-api.nasa.gov/search",
                     params={"q": query.strip(), "media_type": media_type})
    items = ((data.get("collection") or {}).get("items") or [])[:per_page]

    def one(raw):
        if not isinstance(raw, dict) or not isinstance(raw.get("href"), str):
            return None
        d = (raw.get("data") or [{}])[0] if raw.get("data") else {}
        link = (raw.get("links") or [{}])[0] if raw.get("links") else {}
        try:
            urls = _get_json(raw["href"])
        except Exception:
            return None
        if not isinstance(urls, list):
            return None
        dl = _nasa_pick(urls, media_type)
        if not dl:
            return None
        nasa_id = str(d.get("nasa_id") or "")
        center = str(d.get("center") or "")
        return _candidate(
            "nasa", media_type, nasa_id or dl, dl,
            page_url=f"https://images.nasa.gov/details-{nasa_id}" if nasa_id else "",
            author=f"NASA / {center}" if center else "NASA",
            author_url="https://www.nasa.gov", license="Public Domain (NASA)",
            requires_attribution=False,
            width=link.get("width"), height=link.get("height"),
            preview_image=link.get("href") or "",
            title=str(d.get("title") or ""),
        )

    with ThreadPoolExecutor(max_workers=min(6, max(1, len(items)))) as pool:
        results = list(pool.map(one, items))
    return [c for c in results if c]


def _archive_pick(files: list, media_type: str) -> dict | None:
    """Archive：视频取带宽高的 mp4/webm/m4v，图取非缩略图 jpg/png（`archive.ts:21-29`）"""
    named = [f for f in files if isinstance(f, dict) and f.get("name")]
    if media_type == "video":
        vids = [f for f in named if re.search(r"\.(mp4|webm|m4v)$", str(f["name"]), re.I)]
        return next((f for f in vids if f.get("width") and f.get("height")), vids[0] if vids else None)
    imgs = [f for f in named
            if re.search(r"\.(jpe?g|png)$", str(f["name"]), re.I)
            and not re.search(r"thumb|__ia_thumb", str(f["name"]), re.I)]
    return next((f for f in imgs if f.get("width") and f.get("height")), imgs[0] if imgs else None)


def _archive(query: str, media_type: str, per_page: int) -> list[dict]:
    """Internet Archive（强制 publicdomain，`archive.ts:44-92`）"""
    per_page = max(1, min(12, per_page))
    mt = "movies" if media_type == "video" else "image"
    q = f"({query.strip()}) AND mediatype:{mt} AND licenseurl:*publicdomain*"
    data = _get_json("https://archive.org/advancedsearch.php", params={
        "q": q, "fl[]": ["identifier", "title", "creator"],
        "rows": str(per_page), "output": "json",
    })
    docs = (data.get("response") or {}).get("docs") or []

    def one(doc):
        ident = str(doc.get("identifier") or "")
        if not ident:
            return None
        try:
            meta = _get_json(f"https://archive.org/metadata/{quote(ident)}")
        except Exception:
            return None
        f = _archive_pick(meta.get("files") or [], media_type)
        if not f or not f.get("name"):
            return None
        name = "/".join(quote(str(seg)) for seg in str(f["name"]).split("/"))
        creator = doc.get("creator")
        if isinstance(creator, list):
            creator = creator[0] if creator else ""
        title = doc.get("title")
        if isinstance(title, list):
            title = title[0] if title else ""
        return _candidate(
            "archive", media_type, ident,
            f"https://archive.org/download/{quote(ident)}/{name}",
            page_url=f"https://archive.org/details/{ident}",
            author=str(creator or "Internet Archive"),
            author_url=f"https://archive.org/details/{ident}",
            license="Public Domain", requires_attribution=False,
            width=f.get("width"), height=f.get("height"),
            preview_image=f"https://archive.org/services/img/{ident}",
            title=str(title or ""),
        )

    with ThreadPoolExecutor(max_workers=min(6, max(1, len(docs)))) as pool:
        results = list(pool.map(one, docs))
    return [c for c in results if c]


# ---------------------------------------------------------------- 有 Key 的源

def _pexels_pick(files: list, orientation: str, min_short: int = 720) -> dict | None:
    """Pexels：只留 mp4，先按朝向筛，再取短边 ≥720 里最小的（`pexels.ts:81-99`）"""
    mp4 = [f for f in files if f.get("file_type") == "video/mp4" and f.get("link")]
    if not mp4:
        return None
    matched = [f for f in mp4 if orientation_of(f.get("width") or 0, f.get("height") or 0) == orientation]
    pool = matched or mp4
    short = lambda f: min(f.get("width") or 0, f.get("height") or 0)
    qualified = [f for f in pool if short(f) >= min_short]
    if qualified:
        return min(qualified, key=lambda f: f.get("size") or 0)
    return max(pool, key=short)


def _pexels(query: str, media_type: str, per_page: int, key: str, orientation: str,
            min_sec=None, max_sec=None) -> list[dict]:
    """Pexels（`pexels.ts:162-211`）：Authorization 头不加 Bearer"""
    if not key:
        raise StockError("缺少 Pexels API Key")
    if media_type == "image":
        data = _get_json("https://api.pexels.com/v1/search",
                         headers={"Authorization": key},
                         params={"query": query.strip(), "per_page": str(per_page),
                                 "orientation": orientation})
        out = []
        for p in (data.get("photos") or []):
            src = p.get("src") or {}
            url = (src.get("portrait") if orientation == "portrait" else
                   src.get("landscape") if orientation == "landscape" else
                   src.get("large2x")) or src.get("large2x") or src.get("original") or ""
            if not url:
                continue
            out.append(_candidate(
                "pexels", "image", p.get("id"), url,
                page_url=p.get("url") or "", author=p.get("photographer") or "Pexels",
                author_url=p.get("photographer_url") or "https://www.pexels.com",
                license="Pexels", width=p.get("width"), height=p.get("height"),
                preview_image=src.get("tiny") or "", title=p.get("alt") or "",
            ))
        return out
    data = _get_json("https://api.pexels.com/videos/search",
                     headers={"Authorization": key},
                     params={"query": query.strip(), "per_page": str(per_page),
                             "orientation": orientation})
    out = []
    for v in (data.get("videos") or []):
        f = _pexels_pick(v.get("video_files") or [], orientation)
        if not f:
            continue
        user = v.get("user") or {}
        slug = str(v.get("url") or "").rstrip("/").split("/")[-1]
        title = " ".join(w for w in re.sub(r"-?\d+$", "", slug).split("-") if w)
        out.append(_candidate(
            "pexels", "video", v.get("id"), f.get("link") or "",
            page_url=v.get("url") or "", author=user.get("name") or "Pexels",
            author_url=user.get("url") or "https://www.pexels.com",
            license="Pexels", width=f.get("width"), height=f.get("height"),
            duration_sec=v.get("duration"), preview_image=v.get("image") or "",
            title=title,
        ))
    return filter_by_duration(out, min_sec, max_sec)


def _pixabay(query: str, media_type: str, per_page: int, key: str, orientation: str,
             min_sec=None, max_sec=None) -> list[dict]:
    """Pixabay（`pixabay.ts:139-204`）：per_page ≥3；视频端点没有朝向参数 → 客户端筛"""
    if not key:
        raise StockError("缺少 Pixabay API Key")
    per_page = max(3, min(200, per_page))
    if media_type == "image":
        pix_orient = {"portrait": "vertical", "landscape": "horizontal"}.get(orientation, "all")
        data = _get_json("https://pixabay.com/api/", params={
            "key": key, "q": query.strip(), "per_page": str(per_page),
            "image_type": "photo", "orientation": pix_orient, "safesearch": "true",
        })
        out = []
        for h in (data.get("hits") or []):
            out.append(_candidate(
                "pixabay", "image", h.get("id"), h.get("largeImageURL") or "",
                page_url=h.get("pageURL") or "", author=h.get("user") or "Pixabay",
                author_url=f"https://pixabay.com/users/{h.get('user')}-{h.get('user_id')}/",
                license="Pixabay Content License",
                requires_attribution=False,
                width=h.get("imageWidth"), height=h.get("imageHeight"),
                preview_image=h.get("webformatURL") or h.get("previewURL") or "",
                tags=[t.strip() for t in str(h.get("tags") or "").split(",") if t.strip()],
            ))
        return out
    data = _get_json("https://pixabay.com/api/videos/", params={
        "key": key, "q": query.strip(), "per_page": str(per_page), "safesearch": "true",
    })
    out = []
    for h in (data.get("hits") or []):
        vids = h.get("videos") or {}
        pool = [vids.get(k) for k in ("large", "medium", "small", "tiny")]
        pool = [f for f in pool if f and f.get("url") and (f.get("size") or 0) > 0]
        if not pool:
            continue
        short = lambda f: min(f.get("width") or 0, f.get("height") or 0)
        ok = [f for f in pool if short(f) >= 720]
        f = min(ok, key=lambda x: x.get("size") or 0) if ok else max(pool, key=short)
        url = f["url"] if "?" in f["url"] else f["url"] + "?download=1"
        out.append(_candidate(
            "pixabay", "video", h.get("id"), url,
            page_url=h.get("pageURL") or "", author=h.get("user") or "Pixabay",
            author_url=f"https://pixabay.com/users/{h.get('user')}-{h.get('user_id')}/",
            license="Pixabay Content License", requires_attribution=False,
            width=f.get("width"), height=f.get("height"),
            duration_sec=h.get("duration"), preview_image=f.get("thumbnail") or "",
            tags=[t.strip() for t in str(h.get("tags") or "").split(",") if t.strip()],
        ))
    out = [c for c in out
           if not orientation or orientation_of(c["width"] or 1, c["height"] or 1) == orientation]
    return filter_by_duration(out, min_sec, max_sec)


def _coverr(query: str, media_type: str, per_page: int, key: str,
            min_sec=None, max_sec=None) -> list[dict]:
    """Coverr（`coverr.ts:61-99`）：只要视频，API 取用要求署名"""
    if not key:
        raise StockError("缺少 Coverr API Key")
    data = _get_json("https://api.coverr.co/videos",
                     headers={"Authorization": f"Bearer {key}"},
                     params={"query": query.strip(), "page_size": str(per_page), "urls": "true"})
    out = []
    for v in (data.get("hits") or []):
        urls = v.get("urls") or {}
        dl = urls.get("mp4_download") or urls.get("mp4")
        if not dl:
            continue
        title = v.get("title") or v.get("id")
        out.append(_candidate(
            "coverr", "video", v.get("id"), dl,
            page_url=f"https://coverr.co/videos/{v.get('id')}",
            author="Coverr", author_url="https://coverr.co", license="Coverr",
            license_url="https://coverr.co/license", requires_attribution=True,
            attribution_text=f'Video: "{title}" by Coverr (coverr.co)',
            width=v.get("max_width"), height=v.get("max_height"),
            duration_sec=v.get("duration"),
            preview_image=v.get("poster") or v.get("thumbnail") or "",
            title=title or "", tags=v.get("tags") or [],
        ))
    return filter_by_duration(out, min_sec, max_sec)


def _jamendo_license_name(ccurl: str) -> str:
    m = re.search(r"licenses/([a-z-]+)/([\d.]+)", ccurl or "")
    return f"CC {m.group(1).upper()} {m.group(2)}" if m else "unknown"


def _jamendo(query: str, media_type: str, per_page: int, key: str,
             min_sec=None, max_sec=None) -> list[dict]:
    """Jamendo（`jamendo.ts:78-109`）：服务端排 NC/ND/SA，客户端只认纯 CC-BY"""
    if not key:
        raise StockError("缺少 Jamendo Client ID")
    data = _get_json("https://api.jamendo.com/v3.0/tracks/", params={
        "client_id": key, "format": "json", "limit": str(per_page), "search": query.strip(),
        "audioformat": "mp32", "include": "licenses",
        "ccnc": "false", "ccnd": "false", "ccsa": "false",
    })
    out = []
    for t in (data.get("results") or []):
        ccurl = str(t.get("license_ccurl") or "")
        if not re.search(r"creativecommons\.org/licenses/by/\d", ccurl):
            continue  # NC/ND/SA/未知一律丢
        dl = (t.get("audiodownload") if t.get("audiodownload_allowed") else "") or t.get("audio") or ""
        if not dl:
            continue
        lic = _jamendo_license_name(ccurl)
        out.append(_candidate(
            "jamendo", "audio", t.get("id"), dl,
            page_url=t.get("shareurl") or f"https://www.jamendo.com/track/{t.get('id')}",
            author=t.get("artist_name") or "Jamendo artist",
            author_url=f"https://www.jamendo.com/artist/{t.get('artist_id')}" if t.get("artist_id") else "https://www.jamendo.com",
            license=lic, license_url=ccurl, requires_attribution=True,
            attribution_text=f'Music: "{t.get("name")}" by {t.get("artist_name") or "unknown"} (Jamendo, {lic})',
            duration_sec=t.get("duration"), preview_image=t.get("image") or "",
            title=t.get("name") or "",
        ))
    return filter_by_duration(out, min_sec, max_sec)


def _freesound_license(url: str) -> tuple[str, bool, bool]:
    """Freesound 许可分类：CC0 免署名 / CC-BY 要署名 / 其他不安全（`freesound.ts:41-53`）"""
    u = url or ""
    if re.search(r"publicdomain/zero|/zero/|creativecommons\.org/publicdomain", u):
        return "CC0", True, False
    if re.search(r"licenses/by/\d", u):
        return "CC BY", True, True
    return "unknown", False, False


def _freesound(query: str, media_type: str, per_page: int, key: str,
               min_sec=None, max_sec=None) -> list[dict]:
    """Freesound（`freesound.ts:78-107`）：服务端只收 CC0/CC-BY，客户端再验"""
    if not key:
        raise StockError("缺少 Freesound API Key")
    data = _get_json("https://freesound.org/apiv2/search/text/", params={
        "query": query.strip(), "token": key, "page_size": str(per_page),
        "fields": "id,name,username,duration,license,previews,url,tags",
        "filter": 'license:("Attribution" OR "Creative Commons 0")',
    })
    out = []
    for s in (data.get("results") or []):
        name, safe, need_attr = _freesound_license(str(s.get("license") or ""))
        if not safe:
            continue
        previews = s.get("previews") or {}
        dl = previews.get("preview-hq-mp3") or previews.get("preview-lq-mp3") or ""
        if not dl:
            continue
        out.append(_candidate(
            "freesound", "audio", s.get("id"), dl,
            page_url=s.get("url") or f"https://freesound.org/s/{s.get('id')}/",
            author=s.get("username") or "Freesound user",
            author_url=f"https://freesound.org/people/{s.get('username')}/" if s.get("username") else "https://freesound.org",
            license=name, license_url=s.get("license") or "",
            requires_attribution=need_attr,
            attribution_text=(f'Sound: "{s.get("name")}" by {s.get("username") or "unknown"} '
                              f"(Freesound, CC BY)") if need_attr else "",
            duration_sec=s.get("duration"), title=s.get("name") or "",
            tags=s.get("tags") or [],
        ))
    return filter_by_duration(out, min_sec, max_sec)


# ---------------------------------------------------------------- 本地素材源

def _local(query: str, media_type: str, per_page: int, mat_dir: Path) -> list[dict]:
    """本地素材池当搜索源（`local-stock.ts:44-65`）：按名字+标签命中数排序"""
    from app.services import drama_materials

    if media_type == "audio":
        return []
    rows = drama_materials.list_materials(mat_dir) if mat_dir else []
    scored = []
    for row in rows:
        text = " ".join([str(row.get("original_name") or ""),
                         " ".join(str(t) for t in (row.get("tags") or []))])
        # 与 B4 同一个方向问题：素材名/标签当关键词，去 query 里找（中文子串天然成立）
        score = drama_materials.match_score(query, text)
        scored.append((0 if row.get("media_type") == media_type else 1, -score, row))
    scored.sort(key=lambda x: (x[0], x[1], x[2]["name"]))
    out = []
    for _, neg, row in scored[:per_page]:
        out.append(_candidate(
            "local", row.get("media_type") or "image", row["name"],
            str(mat_dir / row["name"]),  # 本地绝对路径：下载时直接复制，不走网络
            author=row.get("author") or "本地素材",
            license=row.get("license") or "本地/自有",
            width=row.get("width"), height=row.get("height"),
            duration_sec=row.get("durationSec"),
            title=str(row.get("original_name") or "").rsplit(".", 1)[0].replace("_", " "),
            tags=row.get("tags") or [],
        ))
    return out


# ---------------------------------------------------------------- 聚合

_cache: dict[str, tuple[float, dict]] = {}
_cache_lock = threading.Lock()


def _cache_key(query: str, opts: dict, ids: list[str]) -> str:
    return "|".join([opts.get("media_type") or "video", opts.get("orientation") or "",
                     str(opts.get("per_page") or ""), str(opts.get("min_sec") or ""),
                     str(opts.get("max_sec") or ""), ",".join(sorted(ids)),
                     query.strip().lower(), str(opts.get("mat_dir") or "")])


def _cache_get(key: str):
    with _cache_lock:
        hit = _cache.get(key)
        if not hit:
            return None
        exp, value = hit
        if exp < time.time():
            _cache.pop(key, None)
            return None
        return value


def _cache_set(key: str, value: dict) -> None:
    with _cache_lock:
        if len(_cache) >= CACHE_MAX:
            # 先清过期的，再不行就丢最早的一条
            now = time.time()
            for k in [k for k, (exp, _) in _cache.items() if exp < now]:
                _cache.pop(k, None)
            if len(_cache) >= CACHE_MAX:
                _cache.pop(next(iter(_cache)))
        _cache[key] = (time.time() + CACHE_TTL_SECONDS, value)


def search_source(source_id: str, query: str, *, media_type: str = "video",
                  per_page: int = 10, orientation: str | None = None,
                  min_sec=None, max_sec=None, keys: dict | None = None,
                  mat_dir: Path | None = None) -> list[dict]:
    """单源检索（`stock-registry.ts:63-126`）"""
    if not str(query or "").strip():
        raise StockError("检索词为空")
    meta = _BY_ID.get(source_id)
    if not meta:
        raise StockError("未知素材源")
    if not is_available(meta, keys):
        raise StockError(f"{meta['label']} 需要 API Key")
    if media_type not in (meta.get("media_types") or []):
        # Openverse 没有视频 → 退回图片（`stock-registry.ts:82-85`）
        if source_id == "openverse" and media_type == "video":
            media_type = "image"
        else:
            return []
    key = source_key(source_id, keys)
    orient = orientation or "portrait"

    if source_id == "openverse":
        return _openverse(query, media_type, per_page, key)
    if source_id == "wikimedia":
        return _wikimedia(query, media_type, per_page)
    if source_id == "nasa":
        return _nasa(query, media_type, per_page)
    if source_id == "archive":
        return _archive(query, media_type, per_page)
    if source_id == "local":
        return _local(query, media_type, per_page, mat_dir) if mat_dir else []
    if source_id == "pexels":
        return _pexels(query, media_type, per_page, key, orient, min_sec, max_sec)
    if source_id == "pixabay":
        return _pixabay(query, media_type, per_page, key, orient, min_sec, max_sec)
    if source_id == "coverr":
        return _coverr(query, media_type, per_page, key, min_sec, max_sec)
    if source_id == "jamendo":
        return _jamendo(query, media_type, per_page, key, min_sec, max_sec)
    if source_id == "freesound":
        return _freesound(query, media_type, per_page, key, min_sec, max_sec)
    return []


def search_all(query: str, *, media_type: str = "video", per_page: int = 10,
               orientation: str | None = None, min_sec=None, max_sec=None,
               keys: dict | None = None, mat_dir: Path | None = None) -> dict:
    """聚合检索：并发跑所有可用源，单源失败只记进 errored（`stock-registry.ts:149-193`）"""
    opts = {"media_type": media_type, "per_page": per_page, "orientation": orientation,
            "min_sec": min_sec, "max_sec": max_sec, "mat_dir": str(mat_dir or "")}
    usable, skipped = [], []
    for s in SOURCES:
        if s["id"] == "local" and not mat_dir:
            continue
        if s.get("aggregate") is False:
            continue  # NASA/Archive 不参与默认聚合（`stock-registry.ts:157`）
        supports = media_type in (s.get("media_types") or []) or (s["id"] == "openverse" and media_type == "video")
        if not supports:
            continue
        if not is_available(s, keys):
            skipped.append(s["id"])
            continue
        usable.append(s["id"])

    ck = _cache_key(query, opts, usable)
    cached = _cache_get(ck)
    if cached:
        return cached

    errored: list[str] = []

    def run(sid: str) -> list[dict]:
        try:
            return search_source(sid, query, media_type=media_type, per_page=per_page,
                                 orientation=orientation, min_sec=min_sec, max_sec=max_sec,
                                 keys=keys, mat_dir=mat_dir)
        except Exception:
            errored.append(sid)
            return []

    merged: list[dict] = []
    if usable:
        with ThreadPoolExecutor(max_workers=min(6, len(usable))) as pool:
            for part in pool.map(run, usable):
                merged.extend(part)

    result = {
        "candidates": rank_candidates(merged, media_type, orientation),
        "skipped_sources": skipped,
        "errored_sources": errored,
    }
    if result["candidates"]:
        _cache_set(ck, result)
    remember(result["candidates"])
    return result


# ---------------------------------------------------------------- 候选缓存（导入用）

_picks: dict[tuple[str, str, str], tuple[float, dict]] = {}
_picks_lock = threading.Lock()


def remember(candidates: list[dict]) -> None:
    """把刚搜到的候选记进短期缓存（导入时按 source/media_type/id 取回）。"""
    now = time.time()
    with _picks_lock:
        for c in candidates:
            _picks[(c["source"], c["media_type"], str(c["id"]))] = (now + PICK_TTL_SECONDS, c)
        expired = [k for k, (exp, _) in _picks.items() if exp < now]
        for k in expired:
            _picks.pop(k, None)


def recall(source_id: str, media_type: str, ident: str) -> dict | None:
    """取回刚才搜索过的候选（导入时只认这个，不认前端传的地址）"""
    with _picks_lock:
        hit = _picks.get((source_id, media_type, str(ident)))
        if not hit:
            return None
        exp, value = hit
        if exp < time.time():
            _picks.pop((source_id, media_type, str(ident)), None)
            return None
        return value


# ---------------------------------------------------------------- 下载

def download(candidate: dict, dest_dir: Path, base_name: str) -> tuple[Path, int]:
    """下载到 dest_dir（`stock-types.ts:240-287`）：超时 / 大小闸 / 先 .part 再 rename。

    本地素材源（绝对路径）直接复制，不走网络。
    返回 (落盘路径, 字节数)；失败抛 StockError。
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    url = str(candidate.get("download_url") or "")
    media_type = str(candidate.get("media_type") or "video")

    if candidate.get("source") == "local" and Path(url).is_file():
        src = Path(url)
        size = src.stat().st_size
        if size > MAX_DOWNLOAD_BYTES:
            raise StockError("素材体积超过 80MB")
        ext = infer_extension(src.name, None, media_type)
        dest = dest_dir / f"{_safe_base(base_name)}.{ext}"
        dest.write_bytes(src.read_bytes())
        return dest, size

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise StockError("下载地址不合法")
    if not parsed.hostname or not _host_is_public(parsed.hostname):
        raise StockError("下载地址指向内网，已拒绝")

    ext = infer_extension(url, None, media_type)
    dest = dest_dir / f"{_safe_base(base_name)}.{ext}"
    part = dest.with_suffix(dest.suffix + ".part")
    size = 0
    try:
        with _session() as ses:
            with ses.get(url, stream=True, timeout=REQUEST_TIMEOUT) as res:
                if res.status_code >= 400:
                    raise StockError(f"下载失败 {res.status_code}")
                declared = int(res.headers.get("content-length") or 0)
                if declared and declared > MAX_DOWNLOAD_BYTES:
                    raise StockError("素材体积超过 80MB")
                with part.open("wb") as fh:
                    for chunk in res.iter_content(1024 * 256):
                        size += len(chunk)
                        if size > MAX_DOWNLOAD_BYTES:
                            raise StockError("素材体积超过 80MB")
                        fh.write(chunk)
        if size == 0:
            raise StockError("下载到的文件是空的")
        os.replace(part, dest)
        return dest, size
    except StockError:
        part.unlink(missing_ok=True)
        raise
    except Exception as e:  # noqa: BLE001
        part.unlink(missing_ok=True)
        raise StockError(f"下载失败：{str(e)[:120]}") from e


_SAFE_BASE = re.compile(r"[^a-zA-Z0-9_-]")


def _safe_base(name: str) -> str:
    """文件名只留字母数字下划线短横（`stock-types.ts:249`）"""
    return (_SAFE_BASE.sub("_", str(name or ""))[:80] or "stock")


def transcode_audio(src: Path, dest: Path) -> None:
    """非 mp3/wav/aac/m4a 的音频（如 .ogg）转成 mp3 再进 BGM 位。"""
    from app.services import media

    exe = media.ffmpeg_path()
    if not exe:
        raise StockError("缺 ffmpeg，无法转换这段音频")
    proc = subprocess.run([exe, "-y", "-v", "error", "-i", str(src), "-vn",
                           "-c:a", "libmp3lame", "-b:a", "192k", str(dest)],
                          capture_output=True, timeout=300)
    if proc.returncode != 0 or not dest.is_file():
        raise StockError("音频转换失败")


def probe_audio_seconds(path: Path) -> float:
    """音频时长（秒），读不出返回 0。"""
    exe = None
    from app.services import media

    exe = media.ffprobe_path()
    if not exe:
        return 0.0
    try:
        out = subprocess.run([exe, "-v", "error", "-print_format", "json",
                              "-show_format", str(path)], capture_output=True, timeout=30)
        if out.returncode != 0:
            return 0.0
        data = json.loads(out.stdout.decode("utf-8", "replace") or "{}")
        return float((data.get("format") or {}).get("duration") or 0)
    except Exception:
        return 0.0
