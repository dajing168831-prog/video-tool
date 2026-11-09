"""D1 配音（TTS）+ D3 人声落地。

出处：
  · `src/lib/edge-tts.ts:1-261`（免费 Edge 朗读 WebSocket，零 Key，带字级 WordBoundary）
  · `src/lib/tts.ts:1-408`（付费四家：OpenAI 兼容 / Atlas Cloud / MiniMax T2A v2 / fal.ai）
  · `src/lib/tts-cache.ts:1-131`（内容寻址缓存：同文本同音色不重复计费）
  · `src/lib/voice-markup.ts:1-29`（`[pause]` 换气标记：只有免费 Edge 渲染成 350ms 停顿，别处一律剥掉）
  · `src/lib/tts-presets.ts:1-192`（四家默认 baseUrl / model / 音色）
  · `src/lib/tts-voices.ts:1-30`（11 个免费音色）
  · `src/lib/video-composer/voice-ground.ts:1-35`（D3：TTS 轨去「播音腔」滤镜链 + 房间底噪）

我们的差异：
  1. 成片走 Seedance 原生出声，还没有 TTS 轨接进合成 → `voice_ground_chain()` / `room_tone_source()`
     这一批只提供纯函数与判据，**合成链未接线**（接线点写在本文件末尾）。
  2. 付费四家结构照抄，但本机没有对应 Key，探针只做假响应回放，**未真联网验证**。
  3. 免费 Edge 真联网跑过（探针 `probe_drama_tts_live.py`），拿不到就照报。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import tempfile
import time
from pathlib import Path

import httpx

# ---------------------------------------------------------------- 常量

#: 预览接口最多 200 字（`api/tts/free/route.ts`）
MAX_PREVIEW_CHARS = 200
#: 小于这个字节数的"音频"几乎肯定不是音频，不进缓存（`tts-cache.ts:27`）
MIN_CACHE_BYTES = 100

#: 免费音色（`tts-voices.ts:12-25` 原表）
FREE_TTS_VOICES = [
    {"value": "zh-CN-XiaoxiaoNeural", "label": "晓晓 · 温柔女声", "gender": "female", "lang": "zh-CN"},
    {"value": "zh-CN-XiaoyiNeural", "label": "晓伊 · 活泼女声", "gender": "female", "lang": "zh-CN"},
    {"value": "zh-CN-YunxiNeural", "label": "云希 · 阳光男声", "gender": "male", "lang": "zh-CN"},
    {"value": "zh-CN-YunyangNeural", "label": "云扬 · 专业播报男声", "gender": "male", "lang": "zh-CN"},
    {"value": "zh-CN-YunjianNeural", "label": "云健 · 沉稳解说男声", "gender": "male", "lang": "zh-CN"},
    {"value": "en-US-AriaNeural", "label": "Aria · US English (female)", "gender": "female", "lang": "en-US"},
    {"value": "en-US-GuyNeural", "label": "Guy · US English (male)", "gender": "male", "lang": "en-US"},
    {"value": "en-GB-SoniaNeural", "label": "Sonia · UK English (female)", "gender": "female", "lang": "en-GB"},
    {"value": "ja-JP-NanamiNeural", "label": "Nanami · 日本語 (female)", "gender": "female", "lang": "ja-JP"},
    {"value": "ko-KR-SunHiNeural", "label": "SunHi · 한국어 (female)", "gender": "female", "lang": "ko-KR"},
    {"value": "es-ES-ElviraNeural", "label": "Elvira · Español (female)", "gender": "female", "lang": "es-ES"},
]
DEFAULT_FREE_VOICE = "zh-CN-XiaoxiaoNeural"

#: 付费四家（`tts-presets.ts:56-160`）
TTS_PROVIDERS = [
    {
        "value": "openai", "label": "OpenAI 兼容 (/audio/speech)",
        "baseUrl": "https://api.siliconflow.cn/v1",
        "defaultModel": "FunAudioLLM/CosyVoice2-0.5B",
        "models": [], "defaultVoice": "FunAudioLLM/CosyVoice2-0.5B:alex",
        "voices": [], "keySource": "tts", "editableBaseUrl": True,
        "hint": "兼容 OpenAI tts-1、硅基流动 CosyVoice、火山方舟等所有 /audio/speech 端点。",
    },
    {
        "value": "atlas", "label": "Atlas Cloud (xAI TTS)",
        "baseUrl": "https://api.atlascloud.ai/api/v1",
        "defaultModel": "xai/tts-v1",
        "models": [{"value": "xai/tts-v1", "label": "xAI TTS v1（多语高保真）"}],
        "defaultVoice": "eve",
        "voices": [
            {"value": "eve", "label": "Eve · 多语女声（默认）"},
            {"value": "leo", "label": "Leo · 多语男声"},
            {"value": "rex", "label": "Rex · 多语男声"},
            {"value": "ara", "label": "Ara · 多语女声"},
            {"value": "sal", "label": "Sal · 多语男声"},
        ],
        "keySource": "atlas-cloud",
        "hint": "复用「AI 平台」里 Atlas Cloud 的 Key（与生图/生视频同一个）。",
    },
    {
        "value": "minimax", "label": "MiniMax 海螺 (T2A v2)",
        "baseUrl": "https://api.minimax.chat/v1",
        "defaultModel": "speech-2.6-hd",
        "models": [
            {"value": "speech-2.6-hd", "label": "speech-2.6-hd（高保真）"},
            {"value": "speech-2.6-turbo", "label": "speech-2.6-turbo（快速）"},
            {"value": "speech-2.5-hd", "label": "speech-2.5-hd"},
        ],
        "defaultVoice": "female-tianmei",
        "voices": [
            {"value": "female-tianmei", "label": "甜美女声（默认）"},
            {"value": "female-shaonv", "label": "少女音"},
            {"value": "female-yujie", "label": "御姐音"},
            {"value": "female-chengshu", "label": "成熟女声"},
            {"value": "presenter_female", "label": "女主持人"},
            {"value": "presenter_male", "label": "男主持人"},
            {"value": "male-qn-qingse", "label": "青涩青年（男）"},
            {"value": "male-qn-jingying", "label": "精英青年（男）"},
            {"value": "audiobook_female_1", "label": "有声书女声"},
        ],
        "keySource": "tts", "needsGroupId": True, "editableBaseUrl": True,
        "hint": "海螺开放平台的 API Key + GroupId。国际版改 baseUrl 为 https://api.minimax.io/v1（可不填 GroupId）。",
    },
    {
        "value": "falai", "label": "fal.ai (MiniMax Speech-02)",
        "baseUrl": "https://queue.fal.run",
        "defaultModel": "fal-ai/minimax/speech-02-hd",
        "models": [
            {"value": "fal-ai/minimax/speech-02-hd", "label": "MiniMax Speech-02 HD"},
            {"value": "fal-ai/minimax/speech-02-turbo", "label": "MiniMax Speech-02 Turbo"},
        ],
        "defaultVoice": "Wise_Woman",
        "voices": [
            {"value": "Wise_Woman", "label": "睿智女声（默认）"},
            {"value": "Calm_Woman", "label": "沉稳女声"},
            {"value": "Lively_Girl", "label": "活力女声"},
            {"value": "Sweet_Girl_2", "label": "甜美女声"},
            {"value": "Friendly_Person", "label": "亲和声线"},
            {"value": "Deep_Voice_Man", "label": "低沉男声"},
            {"value": "Casual_Guy", "label": "随性男声"},
            {"value": "Patient_Man", "label": "沉稳男声"},
        ],
        "keySource": "fal-ai",
        "hint": "复用「AI 平台」里 fal.ai 的 Key（FAL_KEY）。",
    },
]
DEFAULT_TTS_PROVIDER = "openai"
#: MiniMax 官方情绪枚举（`tts.ts:45`）—— 未知值绝不上送（会 400）
MINIMAX_EMOTIONS = {"happy", "sad", "angry", "fearful", "disgusted", "surprised", "neutral"}
#: 只对这些模型送 `instructions`（`tts.ts:48`）
OPENAI_INSTRUCTION_MODELS = re.compile(r"gpt-4o-mini-tts", re.I)


class TTSError(ValueError):
    """配音失败（人话 message）。"""


# ---------------------------------------------------------------- 文本处理

PAUSE_MARK_RE = re.compile(r"\[pause\]", re.I)


def strip_pause_marks(text: str) -> str:
    """去掉 `[pause]` 换气标记（`voice-markup.ts:22-24`）。"""
    return re.sub(r" {2,}", " ", PAUSE_MARK_RE.sub("", text or "")).strip()


def has_pause_marks(text: str) -> bool:
    return bool(PAUSE_MARK_RE.search(text or ""))


def escape_ssml(text: str) -> str:
    """SSML 转义（`edge-tts.ts:55-62`）—— 防注入。"""
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&apos;"))


def estimate_speech_seconds(text: str) -> float:
    """粗估语速时长（`tts.ts:145-166`）：中文 ~4.2 字/秒、英文 ~2.8 词/秒、标点 0.2 秒，故意多估 15%。"""
    clean = re.sub(r"\s+", " ", text or "").strip()
    if not clean:
        return 0.0
    cjk = pauses = 0
    latin: list[str] = []
    for ch in clean:
        if re.match(r"[⺀-鿿　-〿぀-ヿ가-힯]", ch):
            cjk += 1
        elif re.match(r"[。！？；，、：…!?;,.]", ch):
            pauses += 1
        else:
            latin.append(ch)
    latin_words = len([w for w in "".join(latin).split() if w])
    sec = cjk / 4.2 + latin_words / 2.8 + pauses * 0.2
    return max(1.0, sec * 1.15)


# ---------------------------------------------------------------- 缓存

def tts_cache_key(parts: dict) -> str:
    """稳定的内容地址（`tts-cache.ts:43-55`）：键排序、空值丢弃、sha1。"""
    entries = sorted([[k, v] for k, v in (parts or {}).items()
                      if v is not None and v != ""])
    return hashlib.sha1(json.dumps(entries, ensure_ascii=False).encode("utf-8")).hexdigest()


def cache_path(cache_dir: Path, key: str) -> Path | None:
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", key or ""):
        return None
    return Path(cache_dir) / f"{key}.mp3"


def read_cache(cache_dir: Path, key: str) -> bytes | None:
    p = cache_path(cache_dir, key)
    if not p or not p.is_file():
        return None
    try:
        data = p.read_bytes()
    except OSError:
        return None
    return data if len(data) >= MIN_CACHE_BYTES else None


def write_cache(cache_dir: Path, key: str, data: bytes) -> None:
    """写入失败一律吞掉（缓存不能影响生成）；先写临时名再 rename（`tts-cache.ts:112-120`）。"""
    if not data or len(data) < MIN_CACHE_BYTES:
        return
    p = cache_path(cache_dir, key)
    if not p:
        return
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
        try:
            with open(fd, "wb") as fh:
                fh.write(data)
            Path(tmp).replace(p)
        finally:
            Path(tmp).unlink(missing_ok=True)
    except OSError:
        return


# ---------------------------------------------------------------- 重试 / 熔断

def is_retryable_tts_error(err: BaseException) -> bool:
    """确定性拒绝（401/403/400/422/404/402）不重试，网络抖动/408/429/5xx 才重试（`tts.ts:78-89`）。"""
    msg = str(err or "")
    m = re.search(r"\b(4\d{2}|5\d{2})\b", msg)
    if m:
        s = int(m.group(1))
        return s in (408, 429) or s >= 500
    return True


class CircuitBreaker:
    """连续 2 次失败 → 开门 30 秒（`tts.ts:56-64`）。"""

    def __init__(self, threshold: int = 2, cooldown: float = 30.0):
        self.threshold = threshold
        self.cooldown = cooldown
        self.failures = 0
        self.opened_at = 0.0

    def is_open(self) -> bool:
        if not self.opened_at:
            return False
        if time.monotonic() - self.opened_at >= self.cooldown:
            self.opened_at = 0.0
            self.failures = 0
            return False
        return True

    def record_success(self) -> None:
        self.failures = 0
        self.opened_at = 0.0

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold:
            self.opened_at = time.monotonic()


_BREAKERS: dict[str, CircuitBreaker] = {}


def breaker_for(provider: str) -> CircuitBreaker:
    b = _BREAKERS.get(provider)
    if not b:
        b = CircuitBreaker()
        _BREAKERS[provider] = b
    return b


def reset_breakers() -> None:
    _BREAKERS.clear()


# ---------------------------------------------------------------- 免费 Edge

def parse_word_boundary_frame(payload: str) -> list[dict]:
    """解析 `Path:audio.metadata`（`edge-tts.ts:101-122`）：100ns ticks → 秒。"""
    try:
        parsed = json.loads(payload or "{}")
    except (TypeError, ValueError):
        return []
    out: list[dict] = []
    for m in parsed.get("Metadata") or []:
        if m.get("Type") != "WordBoundary":
            continue
        data = m.get("Data") or {}
        text = ((data.get("text") or {}).get("Text")) or ""
        offset, dur = data.get("Offset"), data.get("Duration")
        if not text or not isinstance(offset, (int, float)) or not isinstance(dur, (int, float)):
            continue
        out.append({"text": text, "startSec": offset / 1e7, "endSec": (offset + dur) / 1e7})
    return out


async def _synth_edge_once(text: str, voice: str, rate: str, pitch: str,
                           timeout_ms: int) -> tuple[bytes, list[dict]]:
    """一轮 Edge 合成，返回 (mp3 字节, 字级时间戳)。

    🩸 **2026-11-06 实测：手写 WebSocket 一律 403**。原因不是版本号，而是微软把
    `Sec-MS-GEC` 换成了 **v2 令牌**（`<16位hex>-<64位hex>`，内部是改过的 SHA256 + CS64，
    见 `edge_tts 7.3.1` 的 `drm.py::generate_sec_ms_gec_v2`）—— 旧版 `sha256(ticks+token)`
    再怎么改版本号都没用。
    所以这里用 MIT 许可的 `edge-tts` 库做连接（它维护令牌算法与时钟偏差校正），
    我们只负责把流事件拼成 mp3 + 字级时间戳。
    """
    import edge_tts

    chunks: list[bytes] = []
    words: list[dict] = []

    async def _run() -> None:
        comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch,
                                   boundary="WordBoundary")
        async for ch in comm.stream():
            kind = ch.get("type")
            if kind == "audio":
                chunks.append(ch.get("data") or b"")
            elif kind == "WordBoundary":
                offset = ch.get("offset")
                duration = ch.get("duration")
                label = ch.get("text") or ""
                if label and isinstance(offset, (int, float)) and isinstance(duration, (int, float)):
                    words.append({"text": label, "startSec": offset / 1e7,
                                  "endSec": (offset + duration) / 1e7})

    try:
        await asyncio.wait_for(_run(), timeout=timeout_ms / 1000)
    except asyncio.TimeoutError as e:
        raise TTSError("Edge TTS 超时") from e
    except TTSError:
        raise
    except Exception as e:  # noqa: BLE001
        raise TTSError(f"Edge TTS 连接失败（可能是网络或令牌版本过期）：{e}") from e
    if not chunks:
        raise TTSError("Edge TTS 未返回音频")
    return b"".join(chunks), words


async def generate_speech_free(text: str, *, voice: str = DEFAULT_FREE_VOICE,
                               rate: str = "+0%", pitch: str = "+0Hz",
                               timeout_ms: int = 20000,
                               cache_dir: Path | None = None) -> dict:
    """免费 Edge 合成，返回 `{audio, words, cached}`；失败内部重试 1 次（`edge-tts.ts:147-166`）。"""
    clean = (text or "").strip()
    if not clean:
        raise TTSError("配音文本为空")
    key = tts_cache_key({"provider": "edge", "voice": voice, "rate": rate,
                         "pitch": pitch, "text": clean})
    if cache_dir:
        hit = read_cache(cache_dir, key)
        if hit:
            return {"audio": hit, "words": [], "cached": True}
    last: BaseException | None = None
    for _ in range(2):
        try:
            audio, words = await _synth_edge_once(clean, voice, rate, pitch, timeout_ms)
            if cache_dir:
                write_cache(cache_dir, key, audio)
            return {"audio": audio, "words": words, "cached": False}
        except BaseException as e:  # noqa: BLE001
            last = e
    raise last or TTSError("Edge TTS 失败")


# ---------------------------------------------------------------- 付费

def clip_err(text: str, limit: int = 200) -> str:
    """错误体截断并**显式标注**（`tts.ts:181`）。"""
    return text if len(text) <= limit else text[:limit] + "…(已截断)"


def audio_to_bytes(raw: str) -> bytes:
    """URL / data URI / hex / base64 统一成 bytes（`tts.ts:184-198`）。"""
    s = (raw or "").strip()
    if re.match(r"^https?://", s, re.I):
        r = httpx.get(s, timeout=30.0)
        if r.status_code >= 400:
            raise TTSError(f"下载音频失败: {r.status_code}")
        return r.content
    if s.startswith("data:"):
        comma = s.find(",")
        if comma == -1:
            raise TTSError("音频 data URI 格式错误（缺少逗号分隔符）")
        import base64
        return base64.b64decode(s[comma + 1:])
    if re.fullmatch(r"[0-9a-fA-F]+", s) and len(s) % 2 == 0:
        return bytes.fromhex(s)
    import base64
    return base64.b64decode(s)


def _clamp(n: float, lo: float, hi: float) -> float:
    return min(max(n, lo), hi)


async def _openai_speech(text: str, cfg: dict, client: httpx.AsyncClient) -> bytes:
    base = str(cfg.get("baseUrl") or "").rstrip("/")
    payload = {
        "model": cfg.get("model"), "input": text,
        "voice": cfg.get("voice"), "response_format": "mp3",
    }
    if cfg.get("speed") is not None:
        payload["speed"] = cfg["speed"]
    if cfg.get("instruction") and OPENAI_INSTRUCTION_MODELS.search(str(cfg.get("model") or "")):
        payload["instructions"] = cfg["instruction"]
    r = await client.post(f"{base}/audio/speech", json=payload,
                          headers={"Authorization": f"Bearer {cfg.get('apiKey')}"})
    if r.status_code >= 400:
        raise TTSError(f"TTS 请求失败: {r.status_code} {r.reason_phrase} - "
                       f"{clip_err(r.text)}")
    return r.content


async def _atlas_speech(text: str, cfg: dict, client: httpx.AsyncClient) -> bytes:
    base = str(cfg.get("baseUrl") or "https://api.atlascloud.ai/api/v1").rstrip("/")
    headers = {"Authorization": f"Bearer {cfg.get('apiKey')}"}
    body = {"model": cfg.get("model") or "xai/tts-v1", "text": text,
            "language": "auto", "voice_id": cfg.get("voice") or "eve", "codec": "mp3"}
    if cfg.get("speed") is not None:
        body["speed"] = _clamp(float(cfg["speed"]), 0.7, 1.5)
    r = await client.post(f"{base}/model/generateAudio", json=body, headers=headers)
    if r.status_code >= 400:
        raise TTSError(f"Atlas TTS 提交失败: {r.status_code} - {clip_err(r.text)}")
    data = r.json()
    task_id = (data.get("data") or {}).get("id") or data.get("id")
    if not task_id:
        raise TTSError("Atlas TTS 未返回任务 id")
    for _ in range(60):
        await asyncio.sleep(1)
        try:
            pr = await client.get(f"{base}/model/prediction/{task_id}", headers=headers)
        except httpx.HTTPError:
            continue
        if pr.status_code >= 400:
            continue
        try:
            raw = pr.json()
        except ValueError:
            continue
        p = raw.get("data") or raw
        status = str(p.get("status") or "").lower()
        if status in ("completed", "succeeded"):
            outputs = p.get("outputs") or []
            out = p.get("output")
            audio = (outputs[0] if outputs else
                     (out if isinstance(out, str) else
                      ((out or {}).get("url") or (out or {}).get("audio"))) or p.get("audio"))
            if not audio:
                raise TTSError("Atlas TTS 完成但未返回音频")
            return audio_to_bytes(audio)
        if status in ("failed", "error"):
            raise TTSError(f"Atlas TTS 失败: {p.get('error') or status}")
    raise TTSError("Atlas TTS 轮询超时")


async def _minimax_speech(text: str, cfg: dict, client: httpx.AsyncClient) -> bytes:
    base = str(cfg.get("baseUrl") or "https://api.minimax.chat/v1").rstrip("/")
    url = f"{base}/t2a_v2"
    if cfg.get("groupId"):
        from urllib.parse import quote
        url += f"?GroupId={quote(str(cfg['groupId']))}"
    voice_setting = {
        "voice_id": cfg.get("voice") or "female-tianmei",
        "speed": _clamp(float(cfg.get("speed") or 1), 0.5, 2),
        "vol": 1, "pitch": 0,
    }
    emotion = cfg.get("emotion")
    if emotion and emotion in MINIMAX_EMOTIONS:
        voice_setting["emotion"] = emotion
    r = await client.post(url, json={
        "model": cfg.get("model") or "speech-2.6-hd", "text": text, "stream": False,
        "output_format": "hex", "language_boost": "auto",
        "voice_setting": voice_setting,
        "audio_setting": {"sample_rate": 32000, "bitrate": 128000,
                          "format": "mp3", "channel": 1},
    }, headers={"Authorization": f"Bearer {cfg.get('apiKey')}"})
    if r.status_code >= 400:
        raise TTSError(f"MiniMax TTS 请求失败: {r.status_code} - {clip_err(r.text)}")
    try:
        j = r.json()
    except ValueError as e:
        raise TTSError(f"MiniMax TTS 响应解析失败（非合法 JSON）: {e}") from e
    base_resp = j.get("base_resp") or {}
    code = base_resp.get("status_code")
    if code is not None and code != 0:
        raise TTSError(f"MiniMax TTS 失败: {base_resp.get('status_msg') or '未知错误'} (code={code})")
    hex_audio = (j.get("data") or {}).get("audio")
    if not hex_audio:
        raise TTSError("MiniMax TTS 未返回音频（检查 Key / GroupId / 音色 id）")
    return bytes.fromhex(hex_audio)


async def _fal_speech(text: str, cfg: dict, client: httpx.AsyncClient) -> bytes:
    base = str(cfg.get("baseUrl") or "https://queue.fal.run").rstrip("/")
    model = cfg.get("model") or "fal-ai/minimax/speech-02-hd"
    headers = {"Authorization": f"Key {cfg.get('apiKey')}"}
    r = await client.post(f"{base}/{model}", headers=headers, json={
        "text": text, "output_format": "url",
        "voice_setting": {"voice_id": cfg.get("voice") or "Wise_Woman",
                          "speed": _clamp(float(cfg.get("speed") or 1), 0.5, 2),
                          "vol": 1, "pitch": 0},
        "audio_setting": {"sample_rate": 32000, "bitrate": 128000,
                          "format": "mp3", "channel": 1},
    })
    if r.status_code >= 400:
        raise TTSError(f"fal TTS 提交失败: {r.status_code} - {clip_err(r.text)}")
    sj = r.json()
    request_id = sj.get("request_id")
    if not request_id:
        raise TTSError("fal TTS 未返回 request_id")
    status_url = sj.get("status_url") or f"{base}/{model}/requests/{request_id}/status"
    result_url = sj.get("response_url") or f"{base}/{model}/requests/{request_id}"
    for _ in range(60):
        await asyncio.sleep(1)
        try:
            st = await client.get(status_url, headers=headers)
            if st.status_code >= 400:
                continue
            status = str(st.json().get("status") or "").upper()
        except (httpx.HTTPError, ValueError):
            continue
        if status == "COMPLETED":
            rr = await client.get(result_url, headers=headers)
            if rr.status_code >= 400:
                raise TTSError(f"fal TTS 取结果失败: {rr.status_code}")
            audio_url = ((rr.json() or {}).get("audio") or {}).get("url")
            if not audio_url:
                raise TTSError("fal TTS 完成但未返回音频 URL")
            return audio_to_bytes(audio_url)
        if status in ("FAILED", "ERROR"):
            raise TTSError("fal TTS 任务失败")
    raise TTSError("fal TTS 轮询超时")


async def _dispatch(provider: str, text: str, cfg: dict, client: httpx.AsyncClient) -> bytes:
    if provider == "atlas":
        return await _atlas_speech(text, cfg, client)
    if provider == "minimax":
        return await _minimax_speech(text, cfg, client)
    if provider == "falai":
        return await _fal_speech(text, cfg, client)
    return await _openai_speech(text, cfg, client)


# ---------------------------------------------------------------- 统一入口

async def generate_speech(text: str, config: dict, *,
                          cache_dir: Path | None = None) -> bytes:
    """付费配音统一入口：缓存 → 熔断 → 重试（仅瞬时错误）→ 写缓存（`tts.ts:110-143`）。"""
    clean = strip_pause_marks((text or "").strip())
    if not clean:
        raise TTSError("配音文本为空")
    provider = str(config.get("provider") or DEFAULT_TTS_PROVIDER)
    key = tts_cache_key({
        "provider": provider, "baseUrl": config.get("baseUrl"),
        "model": config.get("model"), "voice": config.get("voice"),
        "speed": config.get("speed"),
        "emotion": config.get("emotion"), "instruction": config.get("instruction"),
        "text": clean,
    })
    if cache_dir:
        hit = read_cache(cache_dir, key)
        if hit:
            return hit
    breaker = breaker_for(provider)
    if breaker.is_open():
        raise TTSError(f"配音服务({provider})连续失败已暂时熔断——请检查对应平台 Key/服务，"
                       "约 30 秒后自动重试")
    last: BaseException | None = None
    async with httpx.AsyncClient(timeout=60.0) as client:
        for attempt in range(3):
            try:
                data = await _dispatch(provider, clean, config, client)
                breaker.record_success()
                if cache_dir:
                    write_cache(cache_dir, key, data)
                return data
            except BaseException as e:  # noqa: BLE001
                last = e
                if not is_retryable_tts_error(e) or attempt == 2:
                    breaker.record_failure()
                    raise
                await asyncio.sleep(1)
    breaker.record_failure()
    raise last or TTSError("TTS 失败")


def resolve_tts_config(tts: dict | None, providers: dict | None = None) -> dict:
    """平台选择 + 复用 AI 平台 Key → 完整配置（`tts-presets.ts:163-181`）。"""
    tts = tts or {}
    providers = providers or {}
    pid = str(tts.get("provider") or DEFAULT_TTS_PROVIDER)
    meta = next((p for p in TTS_PROVIDERS if p["value"] == pid), TTS_PROVIDERS[0])
    base = (str(tts.get("baseUrl") or "").strip() if meta.get("editableBaseUrl")
            else meta["baseUrl"]) or meta["baseUrl"]
    key_source = meta.get("keySource") or "tts"
    api_key = (str(tts.get("apiKey") or "") if key_source == "tts"
               else str((providers.get(key_source) or {}).get("apiKey") or ""))
    out = {
        "provider": meta["value"], "baseUrl": base, "apiKey": api_key,
        "model": tts.get("model") or meta["defaultModel"],
        "voice": tts.get("voice") or meta["defaultVoice"],
    }
    if tts.get("speed") is not None:
        out["speed"] = tts["speed"]
    if meta["value"] == "minimax" and tts.get("groupId"):
        out["groupId"] = tts["groupId"]
    return out


def is_paid_tts_ready(tts: dict | None, providers: dict | None = None) -> bool:
    if not (tts or {}).get("enabled"):
        return False
    c = resolve_tts_config(tts, providers)
    return bool(c["apiKey"] and c["baseUrl"] and c["model"] and c["voice"])


# ---------------------------------------------------------------- D3 人声落地

def voice_ground_chain() -> str:
    """TTS 轨去「播音腔」滤镜链（`voice-ground.ts:19-22`）。

    🩸 **只许用在 TTS 文件上** —— 模型原生出声自带房间感，过这条链等于二次劣化。
    """
    return ("highpass=f=90,lowpass=f=9500,"
            "acompressor=threshold=-18dB:ratio=3:attack=20:release=250:makeup=2,"
            "aexciter=amount=2:drive=8.5:freq=6000")


def room_tone_source(amplitude: float = 0.008) -> str:
    """房间底噪源（`voice-ground.ts:29-35`）：棕噪 + 低通，垫在整条时间线下。"""
    return (f"anoisesrc=colour=brown:r=44100:amplitude={amplitude},"
            "lowpass=f=400,aformat=sample_rates=44100:channel_layouts=stereo")


# 接线点（还没接，写在这里免得下次重新找）：
#   backend/app/services/drama_compose.py 的滤镜链里，TTS 音轨在 `aresample` 之后、
#   `apad/atrim` 之前插 `voice_ground_chain()`；成片音频混音阶段把 `room_tone_source()`
#   作为一条 amix 输入垫底。当前成片走 Seedance 原生出声，没有 TTS 轨 → 未接线。
