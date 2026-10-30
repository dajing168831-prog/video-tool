"""对外 API（响应信封严格对齐现有系统：{code, biz_code, msg, data}）。"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.core.config import settings
from app.parsers.base import detect_platform, extract_url
from app.parsers.pvp_adapter import PvpParser
from app.parsers.tiktok_provider import TikTokParser
from app.parsers.xhs_provider import XiaohongshuParser
from app.parsers.ytdlp_provider import YtdlpParser
from app.services import media, storage, transcript
from app.services.providers import separate

log = logging.getLogger(__name__)
router = APIRouter()


def ok(data=None, biz_code: int = 0, msg: str = "成功") -> dict:
    return {"code": 200, "biz_code": biz_code, "msg": msg, "data": data}


def fail(msg: str, biz_code: int = 1, code: int = 200) -> dict:
    # HTTP 层保持 200，业务错误走 biz_code（对齐现有系统口径）
    return {"code": code, "biz_code": biz_code, "msg": msg, "data": None}


class ParseIn(BaseModel):
    text: str = Field(..., description="分享链接或整段分享文案")


# 同一链接短时复用：平台接口对高频请求敏感（抖音会整段拒绝），文件也省得重下
_PARSE_CACHE: dict[str, tuple[float, str]] = {}
_PARSE_TTL = 300.0
_PARSE_CACHE_MAX = 500


def _remember(url: str, token: str) -> None:
    _PARSE_CACHE[url] = (time.time(), token)
    if len(_PARSE_CACHE) > _PARSE_CACHE_MAX:
        now = time.time()
        for k, (ts, _) in list(_PARSE_CACHE.items()):
            if now - ts > _PARSE_TTL:
                _PARSE_CACHE.pop(k, None)
        while len(_PARSE_CACHE) > _PARSE_CACHE_MAX:
            _PARSE_CACHE.pop(next(iter(_PARSE_CACHE)))


def _public(meta: dict, token: str) -> dict:
    """对外字段白名单（meta 里还有 created_at / extra 等内部信息）。"""
    return {
        "token": token,
        "platform": meta.get("platform"),
        "title": meta.get("title"),
        "desc": meta.get("desc"),
        "tags": meta.get("tags") or [],
        "author": meta.get("author"),
        "author_avatar": meta.get("author_avatar"),
        "cover": meta.get("cover"),
        "video_url": meta.get("video_url"),
        "images": meta.get("images") or [],
        "duration": meta.get("duration"),
        "is_video": bool(meta.get("is_video")),
    }


_pvp = PvpParser()
_tiktok = TikTokParser()
_xhs = XiaohongshuParser()
_yt_ig = YtdlpParser("instagram", ("instagram.com", "instagr.am"))
_yt_tw = YtdlpParser("twitter", ("twitter.com", "x.com"))

# 平台 → 解析器。换引擎只改这一张表。
# 2026-10-21 主人拍板砍掉 YouTube：它按 IP 类别判定，机房 IP 必须配住宅出口；
# 不做了以后整套服务不再依赖住宅代理。
PARSERS = {
    "tiktok": _tiktok,
    "douyin": _pvp,
    "kuaishou": _pvp,
    "xiaohongshu": _xhs,
    "bilibili": _pvp,
    "instagram": _yt_ig,
    "twitter": _yt_tw,
}


async def ensure_video(meta: dict, dest) -> None:
    """生成视频文件：yt-dlp 引擎交给 yt-dlp，其它平台走直链下载。

    dest 由调用方决定 —— 解析页放 temp，复刻页放自己的产物目录。
    """
    if Path(dest).exists():
        return
    extra = meta.get("extra", {}) or {}
    if extra.get("engine") == "ytdlp":
        await media.ytdlp_download(extra["source_url"], dest, proxy=extra.get("proxy", ""))
        return
    src = meta.get("video_url") or ""
    if not src:
        raise HTTPException(status_code=400, detail="该作品没有视频文件（可能是图集）")
    await media.download(src, dest)


_MAX_IMAGE_BYTES = 20 * 1024 * 1024


async def _ensure_image(url: str, dest) -> None:
    """封面/图集下载到本地。先写 .part 再改名，避免并发读到半个文件。"""
    if dest.exists():
        return
    part = dest.with_name(dest.name + ".part")
    try:
        await media.download(url, part, max_bytes=_MAX_IMAGE_BYTES)
        part.replace(dest)
    finally:
        if part.exists():
            part.unlink(missing_ok=True)


def _sniff_image_type(p) -> str:
    try:
        head = p.open("rb").read(12)
    except Exception:  # noqa: BLE001
        return "application/octet-stream"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG"):
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(b"GIF8"):
        return "image/gif"
    return "image/jpeg"


@router.get("/health")
async def health():
    """健康检查同时报每条换画面通道是否就绪 —— 排查"为什么走了另一条"看这里。

    🩸 2026-10-26 L3 第三轮：通道清单和"配好没"都**问注册表**
    （`adapter.ready()`），不再在这里写死两家、也不再在这里读各家 key。
    加第 4 家只会在 `channels` 里自动多一行。
    """
    from app.services import models, oss

    return ok({
        "status": "up",
        "ffmpeg": bool(media.ffmpeg_path()),
        "channels": {
            **{fam: ad.ready()
               for fam, ad in models.adapters_by_family().items()},
            "oss": oss.available(),
            # 人声分离（mix 留背景音用）：key 和 OSS 都要有才跑得通
            "separate": separate.available() and oss.available(),
        },
        # 同时能跑几条出片：多人联调时"点了没反应"多半是排在这条线后面
        "workers": settings.clone_workers,
    })


@router.post("/parse")
async def parse(body: ParseIn):
    url = extract_url(body.text)
    if not url:
        return fail("没有从文本里找到链接")
    platform = detect_platform(url)
    if not platform:
        return fail("不支持的平台或链接格式")
    if platform not in settings.enabled_platforms:
        labels = {
            "tiktok": "TikTok", "instagram": "Instagram", "twitter": "X",
            "youtube": "YouTube",
        }
        return fail(f"暂不支持 {labels.get(platform, platform)}，请换其它平台链接", biz_code=2)

    hit = _PARSE_CACHE.get(url)
    if hit and time.time() - hit[0] < _PARSE_TTL:
        cached = storage.load_meta(hit[1])
        if cached:
            return ok(_public(cached, hit[1]))

    parser = PARSERS.get(platform)
    if parser is None or not parser.match(url):
        if platform == "youtube":
            return fail("暂不支持 YouTube，请换其它平台链接", biz_code=2)
        return fail(f"{platform} 暂不支持", biz_code=2)

    try:
        info = await parser.parse(url)
    except Exception as e:  # noqa: BLE001
        log.exception("parse failed")
        return fail(str(e)[:300], biz_code=3)

    token = storage.new_token()
    storage.save_meta(token, info)
    storage.cleanup_expired()
    _remember(url, token)

    return ok(_public(storage.load_meta(token) or {}, token))


@router.get("/task/{token}")
async def task(token: str):
    meta = storage.load_meta(token)
    if not meta:
        return fail("任务不存在或已过期", biz_code=404)
    return ok(meta)


@router.get("/task/{token}/transcript")
async def peek_transcript(token: str):
    """只读缓存：这个任务转过就返回，没转过 `data=None`（**不触发付费识别**）。"""
    meta = storage.load_meta(token)
    if not meta:
        return fail("任务不存在或已过期", biz_code=404)
    return ok(transcript.load(token))


@router.post("/task/{token}/transcript")
async def make_transcript(token: str, refresh: bool = Query(False)):
    """提取口播文案（语音转写）。

    🩸 **付费动作**：只在用户点「提取口播文案」时调用，解析阶段绝不自动跑。
    结果落盘，同一 token 再点直接读缓存；只有 `refresh=1` 才重新识别。
    """
    meta = storage.load_meta(token)
    if not meta:
        return fail("任务不存在或已过期", biz_code=404)
    try:
        data = await transcript.get_or_make(token, meta, refresh=refresh)
    except transcript.TranscriptError as e:
        return fail(str(e), biz_code=400)
    except Exception as e:  # noqa: BLE001
        log.exception("transcript failed")
        return fail(f"提取失败：{e}", biz_code=502)
    return ok(data)


@router.get("/file/{token}/video")
async def get_video(token: str, download: bool = Query(False)):
    meta = storage.load_meta(token)
    if not meta:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    p = storage.video_path(token)
    if not p.exists():
        try:
            await ensure_video(meta, p)
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            log.exception("download failed")
            raise HTTPException(status_code=502, detail=f"下载失败：{e}") from e
    filename = f"{meta.get('title') or 'video'}.mp4"
    return FileResponse(
        p,
        media_type="video/mp4",
        filename=filename if download else None,
    )


@router.get("/file/{token}/audio")
async def get_audio(token: str, download: bool = Query(False)):
    meta = storage.load_meta(token)
    if not meta:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    a = storage.audio_path(token)
    if not a.exists():
        v = storage.video_path(token)
        if not v.exists():
            try:
                await ensure_video(meta, v)
            except HTTPException:
                raise
            except Exception as e:  # noqa: BLE001
                raise HTTPException(status_code=502, detail=f"下载失败：{e}") from e
        ok_audio = await media.extract_audio(v, a)
        if not ok_audio:
            raise HTTPException(status_code=400, detail="该视频没有音轨（静音视频），无法提取音频")
    filename = f"{meta.get('title') or 'audio'}.m4a"
    return FileResponse(
        a,
        media_type="audio/mp4",
        filename=filename if download else None,
    )


@router.get("/file/{token}/cover")
async def get_cover(token: str):
    """封面走本机代理：平台 CDN 有防盗链，小程序也不能加载外链。"""
    meta = storage.load_meta(token)
    if not meta:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    url = meta.get("cover") or ""
    if not url:
        raise HTTPException(status_code=404, detail="该作品没有封面")
    p = storage.cover_path(token)
    if not p.exists():
        try:
            await _ensure_image(url, p)
        except Exception as e:  # noqa: BLE001
            log.warning("封面下载失败 %s: %s", token, e)
            raise HTTPException(status_code=502, detail="封面下载失败") from e
    return FileResponse(p, media_type=_sniff_image_type(p))


@router.get("/file/{token}/image/{idx}")
async def get_image(token: str, idx: int):
    meta = storage.load_meta(token)
    if not meta:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    images = meta.get("images") or []
    if idx < 0 or idx >= len(images):
        raise HTTPException(status_code=404, detail="图片不存在")
    p = storage.image_path(token, idx)
    if not p.exists():
        try:
            await _ensure_image(images[idx], p)
        except Exception as e:  # noqa: BLE001
            log.warning("图片下载失败 %s[%s]: %s", token, idx, e)
            raise HTTPException(status_code=502, detail="图片下载失败") from e
    return FileResponse(p, media_type=_sniff_image_type(p))
