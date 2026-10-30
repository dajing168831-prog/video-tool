"""口播文案：把「这支视频里到底说了什么」转成文字。

和结果页上方那个「作品文案」不是一回事 —— 那个是平台给的标题/简介/话题，
这个是**音轨里的逐句语音**，也就是用户真正想抄走的东西。

三条纪律：
  1. **按需生成**：用户点一下才跑，解析时不自动调（ASR 按音频时长计费）。
  2. **一次就够**：结果落 `transcript.json`，同一个 token 再点直接读缓存。
  3. **失败要说人话**：静音视频 / 图集 / 超长 / 没配 key，各给各的话，
     绝不返回一段空文本冒充成功。
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

from app.core.config import settings
from app.services import media, storage

log = logging.getLogger(__name__)

#: 超过这个时长不转（接口是**整段同步**识别，越长越容易超时，也越贵）
MAX_SEC = 30 * 60
#: 同时最多跑几条（火山对并发有上限，别把别人的请求挤爆）
_SEM = asyncio.Semaphore(2)


class TranscriptError(RuntimeError):
    """能直接展示给用户的原因（不是内部异常）。"""


def path(token: str) -> Path:
    return storage.task_dir(token) / "transcript.json"


def load(token: str) -> dict | None:
    p = path(token)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def save(token: str, data: dict) -> None:
    p = path(token)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def build_text(segments: list[dict], *, gap: float = 1.2) -> str:
    """逐句 → 段落文本。

    停顿 ≥ `gap` 秒另起一段（口播里的换段几乎都长这样）；
    否则直接接上（火山已经开了标点，句末自带 `。，？`，不用我们补）。
    """
    out: list[str] = []
    prev_end = None
    for seg in segments or []:
        t = (seg.get("text") or "").strip()
        if not t:
            continue
        s, e = float(seg.get("start") or 0), float(seg.get("end") or 0)
        if out and prev_end is not None and s - prev_end >= gap:
            out.append("\n")
        out.append(t)
        prev_end = e
    return "".join(out).strip()


async def _audio_for(token: str, meta: dict) -> Path:
    """拿到本地音轨（没有就抽一条）。静音视频在这里判死。"""
    a = storage.audio_path(token)
    if a.exists():
        return a
    v = storage.video_path(token)
    if not v.exists():
        from fastapi import HTTPException

        from app.api.routes import ensure_video  # 延迟导入：routes 会 import 本模块

        try:
            await ensure_video(meta, v)
        except HTTPException as e:
            # 下载失败/任务过期之类，原样翻成人话给用户看，别抛一个 500
            raise TranscriptError(str(e.detail or "视频下载失败")) from e
    if not await media.extract_audio(v, a):
        raise TranscriptError("这支视频没有音轨（静音），没有可转写的内容")
    return a


async def get_or_make(token: str, meta: dict, *, refresh: bool = False,
                      asr=None) -> dict:
    """取（或生成）口播文案。缓存优先，`refresh=True` 才重跑。"""
    if not refresh:
        cached = load(token)
        if cached:
            return {**cached, "cached": True}

    if not meta.get("is_video"):
        raise TranscriptError("图集没有音频，提取不了口播文案")

    dur = float(meta.get("duration") or 0)
    if dur and dur > MAX_SEC:
        raise TranscriptError(
            f"视频 {dur / 60:.0f} 分钟，超过 {MAX_SEC // 60} 分钟上限；"
            "可以先保存视频，再分段提取")

    audio = await _audio_for(token, meta)

    from app.services.providers.asr import ASRError, get_asr

    provider = asr or get_asr()
    try:
        async with _SEM:
            res = await asyncio.wait_for(
                asyncio.to_thread(provider.transcribe, audio), timeout=900)
    except asyncio.TimeoutError as e:
        raise TranscriptError("转写超时（音频较长），请稍后重试") from e
    except ASRError as e:
        raise TranscriptError(str(e)) from e

    if not res.get("has"):
        raise TranscriptError("没检测到人声（可能是纯音乐或静音视频）")

    segments = [{"start": round(float(s.get("start") or 0), 2),
                 "end": round(float(s.get("end") or 0), 2),
                 "text": (s.get("text") or "").strip()}
                for s in (res.get("segments") or []) if (s.get("text") or "").strip()]
    text = build_text(segments)
    if not text:
        raise TranscriptError("识别结果为空，请稍后重试")

    data = {
        "text": text,
        "segments": segments,
        # 字数：中文按字、英文按词，给前端显示"多少字"，别把标点算进去
        "chars": len([c for c in text if not c.isspace()]),
        "lang": res.get("lang") or "zh",
        "duration": round(dur, 2),
        "made_at": time.time(),
    }
    save(token, data)
    return {**data, "cached": False}
