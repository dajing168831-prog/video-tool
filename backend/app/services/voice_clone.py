"""火山声音复刻（V3）：训练音色 / 查状态。

接口出处（官方文档 `SoundReplicaAPI-V3`，2026-10-21 抓取）：
  https://docs.volcengine.com/docs/DoubaoVoice/SoundReplicaAPI-V3
  - 训练：POST https://openspeech.bytedance.com/api/v3/tts/voice_clone
  - 查询：POST https://openspeech.bytedance.com/api/v3/tts/get_voice
  请求头：X-Api-Key + X-Api-Request-Id（新版控制台；旧版是 X-Api-App-Key +
          X-Api-Access-Key，本项目统一用新版）
  请求体：{"speaker_id": "S_xxx", "audio": {"data": "<base64>", "format": "wav"},
           "language": 0}
  状态：0 NotFound / 1 Training / 2 Success / 3 Failed / 4 Active（2/4 可合成）

⚠️ speaker_id 是**控制台里开通的音色槽位**（S_ 开头），API 不能凭空创建。
⚠️ 训练会消耗复刻额度（官方：每个资源最多 15 次），所以先把素材转成
   24kHz 单声道 WAV 再发 —— 官方推荐 wav，避免格式问题白烧一次额度。
"""
from __future__ import annotations

import base64
import json
import logging
import subprocess
import tempfile
import uuid
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

BASE = "https://openspeech.bytedance.com/api/v3/tts"
TRAIN = f"{BASE}/voice_clone"
STATUS = f"{BASE}/get_voice"

# 官方：language 字段的枚举值
LANG = {"zh": 0, "en": 1, "ja": 2, "es": 3, "id": 4, "pt": 5,
        "de": 6, "fr": 7, "ko": 8}

# 官方：音频 ≤10MB；推荐 10–30 秒
MAX_BYTES = 10 * 1024 * 1024
REC_SEC = (10.0, 30.0)

_STATUS_TEXT = {0: "NotFound", 1: "Training", 2: "Success",
                3: "Failed", 4: "Active"}


class VoiceCloneError(RuntimeError):
    pass


def _key() -> str:
    from app.core.config import settings

    k = (settings.volc_api_key or "").strip()
    if not k:
        raise VoiceCloneError("豆包语音未配置：请设置 VT_VOLC_API_KEY")
    return k


def _headers() -> dict:
    # 官方 V3 鉴权头只有这两个（训练/查询都没有 X-Api-Resource-Id）
    return {
        "Content-Type": "application/json",
        "X-Api-Key": _key(),
        "X-Api-Request-Id": str(uuid.uuid4()),
    }


def valid_speaker_id(speaker_id: str) -> bool:
    """音色槽位 ID：官方示例是 S_xxxxxxx。

    只做形状校验（S_ 开头 + 字母数字），不猜长度 —— 长度是控制台决定的。
    """
    s = (speaker_id or "").strip()
    return bool(s.startswith("S_") and 6 <= len(s) <= 64
                and all(c.isalnum() or c == "_" for c in s))


def prepare_audio(src: Path) -> tuple[bytes, str, float]:
    """转成官方推荐的 24kHz 单声道 WAV，返回 (字节, 格式, 秒数)。"""
    from app.services.media import ffmpeg_path, probe_duration

    p = Path(src)
    if not p.exists():
        raise VoiceCloneError("音频文件不存在")
    if p.stat().st_size <= 0:
        raise VoiceCloneError("音频文件是空的")
    if p.stat().st_size > MAX_BYTES:
        raise VoiceCloneError(f"音频超过 10MB 上限：{p.stat().st_size / 1024 / 1024:.1f}MB")
    dur = float(probe_duration(p) or 0)
    ff = ffmpeg_path()
    if not ff:
        # 没有 ffmpeg：原样发（格式按扩展名），官方也收 mp3/m4a/ogg/aac
        fmt = p.suffix.lower().lstrip(".") or "wav"
        return p.read_bytes(), fmt, dur
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False,
                                     dir=str(p.parent)) as f:
        tmp = Path(f.name)
    try:
        proc = subprocess.run(
            [ff, "-hide_banner", "-loglevel", "error", "-y", "-i", str(p),
             "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", str(tmp)],
            capture_output=True, text=True, errors="ignore", timeout=180,
        )
        if proc.returncode != 0 or not tmp.exists() or tmp.stat().st_size <= 0:
            raise VoiceCloneError(f"音频转码失败：{(proc.stderr or '')[-200:]}")
        if tmp.stat().st_size > MAX_BYTES:
            raise VoiceCloneError("转码后仍超过 10MB，请剪短一点")
        return tmp.read_bytes(), "wav", dur
    finally:
        tmp.unlink(missing_ok=True)


def _post(url: str, body: dict) -> dict:
    with httpx.Client(timeout=180) as c:
        r = c.post(url, headers=_headers(),
                   content=json.dumps(body, ensure_ascii=False).encode("utf-8"))
    if r.status_code != 200:
        raise VoiceCloneError(
            f"声音复刻接口 HTTP {r.status_code}: {r.text[:300]}")
    try:
        data = r.json()
    except Exception:  # noqa: BLE001
        return {}
    code = data.get("code")
    if code is not None and code not in (0, 20000000, 3000):
        msg = data.get("message") or data.get("msg") or ""
        raise VoiceCloneError(f"声音复刻接口返回 {code}: {msg}"[:300])
    return data


def train(speaker_id: str, audio: Path, lang: str = "zh") -> dict:
    """用一段人声训练/更新音色。返回 {status, seconds, warning}。"""
    sid = (speaker_id or "").strip()
    if not valid_speaker_id(sid):
        raise VoiceCloneError("音色槽位 ID 形状不对：应以 S_ 开头（控制台里创建的音色槽位）")
    raw, fmt, dur = prepare_audio(Path(audio))
    # 🩸 官方 `language` 只定义了 9 种（`LANG`）。泰语/越南语/马来语/菲律宾语/俄语/
    # 阿语/意大利语**不在其中** —— 以前 `LANG.get(lang, 0)` 会把它们静默按中文提交，
    # 训练出来的音色念泰语是一口中文腔。宁可当场报不支持，也不静默降级。
    code = (lang or "zh").strip().lower().split("-", 1)[0]
    if code not in LANG:
        raise VoiceCloneError(
            f"声音复刻不支持「{code}」：官方只收 "
            f"{'/'.join(LANG)} 共 {len(LANG)} 种语言。这条配音请从官方音色里选。")
    body = {
        "speaker_id": sid,
        "audio": {"data": base64.b64encode(raw).decode(), "format": fmt},
        "language": LANG[code],
        "extra_params": {"voice_clone_denoise_model_id": ""},
    }
    data = _post(TRAIN, body)
    warning = ""
    if dur and not (REC_SEC[0] <= dur <= REC_SEC[1]):
        warning = (f"这段音频 {dur:.1f} 秒，官方推荐 10–30 秒；"
                   "太短/太长可能影响相似度")
    log.info("声音复刻训练已提交 speaker=%s %.1fs", sid, dur)
    return {"speaker_id": sid, "status": data.get("status"),
            "status_text": _STATUS_TEXT.get(data.get("status"), "已提交"),
            "seconds": round(dur, 1), "warning": warning}


def status(speaker_id: str) -> dict:
    """查训练状态。status 为 2/4 时可以直接拿去合成。"""
    sid = (speaker_id or "").strip()
    if not valid_speaker_id(sid):
        raise VoiceCloneError("音色槽位 ID 形状不对：应以 S_ 开头")
    data = _post(STATUS, {"speaker_id": sid})
    st = data.get("status")
    demos = [x.get("demo_audio") for x in (data.get("speaker_status") or [])
             if x.get("demo_audio")]
    return {
        "speaker_id": sid,
        "status": st,
        "status_text": _STATUS_TEXT.get(st, "Unknown"),
        "ready": st in (2, 4),
        "available_training_times": data.get("available_training_times"),
        "demo_audio": demos[0] if demos else "",
    }
