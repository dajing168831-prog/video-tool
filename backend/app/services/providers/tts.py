"""语音合成：把改写后的文案读成音轨。

两个实现，同一接口：
  SapiTTS —— 开发机用 Windows 自带中文音色，不需要任何 Key
  VolcTTS —— 生产，火山引擎（HTTP 接口，鉴权走 AK/SK）

选哪个由 settings.tts_provider 决定（默认 sapi，配了火山 Key 就切 volc）。
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

_PS1 = Path(__file__).with_name("sapi_speak.ps1")


class TTSError(RuntimeError):
    pass


def _write_text(text: str, path: Path) -> None:
    # 带 BOM，PowerShell 5.1 的 -Encoding UTF8 才稳
    path.write_text(text, encoding="utf-8-sig")


class SapiTTS:
    """Windows 系统音色。开发验证用，音质一般但完全离线。"""

    name = "sapi"

    def synth(self, text: str, out: Path, *, voice: str = "",
              rate: int = 0, dialect: str = "") -> Path:
        # 系统音色没有方言能力，`dialect` 收下不用 —— 签名要跟 VolcTTS 一致，
        # 调用方不该为"用哪个引擎"分支
        text = (text or "").strip()
        if not text:
            raise TTSError("要合成的文本是空的")
        out.parent.mkdir(parents=True, exist_ok=True)
        # SAPI 的 Rate 只有 -10~10，而豆包是 -50~50 —— 同一套调用方传过来的
        # 百分点必须在这里收口，否则 PowerShell 那边直接报参数越界
        rate = max(-10, min(10, int(rate) // 5))

        with tempfile.NamedTemporaryFile(
            "w", suffix=".txt", delete=False, encoding="utf-8-sig"
        ) as f:
            f.write(text)
            txt = Path(f.name)

        try:
            cmd = [
                "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(_PS1),
                "-TextFile", str(txt),
                "-OutFile", str(out),
                "-Rate", str(rate),
            ]
            if voice:
                cmd += ["-Voice", voice]
            proc = subprocess.run(
                cmd, capture_output=True, text=True, errors="ignore", timeout=180
            )
        finally:
            txt.unlink(missing_ok=True)

        if proc.returncode != 0 or not out.exists() or out.stat().st_size == 0:
            raise TTSError(f"SAPI 合成失败: {(proc.stderr or '')[-300:]}")
        return out


def resource_for(voice: str, default: str = "") -> str:
    """合成用哪个资源 ID。

    🩸 复刻音色（S_ 开头）必须走复刻资源。官方 SoundReplicaAPI-V3：
    「V3 大模型语音合成接口通过 X-Api-Resource-Id 选择版本效果：
      seed-icl-2.0 对应声音复刻 ICL 2.0 版本效果」。
    拿预设音色的 seed-tts-2.0 去念 S_xxx 会被拒。
    """
    from app.core.config import settings

    if (voice or "").startswith("S_"):
        return settings.volc_icl_resource
    return default or settings.volc_tts_resource


class VolcTTS:
    """豆包语音合成 2.0（生产）。

    接口：POST /api/v3/tts/unidirectional
    返回是 NDJSON：每行 {"code","message","data"}，data 是 base64 音频分片，
    最后一行 code=20000000 表示结束。把分片按序拼接就是完整音频。

    speech_rate 官方取值 -50~100（100 = 2.0 倍速）。
    出处：`data/official/voice/pull-2026-11-05/docs/2528925.md:172`（现行 HTTP 接口）。
    这里按官方的**接口上限**钳，不做产品层限制 —— 「超过 ±30 人声就假了」
    是产品判断，落在 `speech_est.MAX_RATE`，不归 provider 管。
    """

    name = "volc"
    ext = ".mp3"

    URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"

    def __init__(self, api_key: str = "", resource: str = "", speaker: str = "") -> None:
        from app.core.config import settings

        self.api_key = (api_key or settings.volc_api_key).strip()
        self.resource = (resource or settings.volc_tts_resource).strip()
        self.speaker = (speaker or settings.volc_tts_speaker).strip()
        self.uid = settings.volc_uid

    def synth(self, text: str, out: Path, *, voice: str = "",
              rate: int = 0, dialect: str = "", fidelity: bool = False) -> Path:
        text = (text or "").strip()
        if not text:
            raise TTSError("要合成的文本是空的")
        if not self.api_key:
            raise TTSError("豆包语音未配置：请设置 VT_VOLC_API_KEY")
        out.parent.mkdir(parents=True, exist_ok=True)

        params = {
            "text": text,
            "speaker": voice or self.speaker,
            "audio_params": {
                "format": "mp3",
                "sample_rate": 24000,
                "speech_rate": max(-50, min(100, int(rate))),
            },
        }
        # 🩸 方言（2026-10-27）：官方《语音合成 HTTP 接口》`explicit_dialect` 原文
        # `www.volcengine.com/docs/6561/2534913`，取值八个：
        #   beijing 北京 / dongbei 东北 / henan 河南 / shaanxi 陕西 /
        #   shanghai 上海 / sichuan 四川 / tianjin 天津 / yue 粤语
        # 原文补充：「使用该参数时，speaker 需要设置支持方言的音色」——
        # 我们音色表里带 `dialects` 的四个 2.0 音色正好对应这八种。
        # 传了不支持的组合火山会直接报参数错误，所以前端只在有方言的音色上给这个选项。
        if (dialect or "").strip():
            params["explicit_dialect"] = dialect.strip().lower()

        # 🩸 口音还原（2026-11-05）：官方《语音合成 HTTP 接口》`tone_fidelity` 原文
        # `data/official/voice/pull-2026-11-05/docs/2528925.md:16-21`：
        # ① 「开启还原模式，开启后模型将尽可能还原送入的上传的 prompt 音频音色和
        #     说话风格（情感、韵律、口音等）」—— 这是 8 种 explicit_dialect 之外的
        #     地方口音（广西、潮汕…）唯一能走的路，因为口音跟着上传原声走。
        # ② 「仅适用于豆包声音复刻大模型2.0音色」—— 预设音色传了会被拒，
        #     所以这里加 `S_` 判断，宁可不传也不让整条合成失败。
        # ③ 「仅支持合成和上传音频同语种的文本，不支持跨语种合成」—— 跨语种的
        #     拦截在调用方（clone_pipeline）做，provider 这层不知道上传音频是什么语种。
        if fidelity and (voice or self.speaker).startswith("S_"):
            params["tone_fidelity"] = True

        body = {"user": {"uid": self.uid}, "req_params": params}
        used = voice or self.speaker
        resource = resource_for(used, self.resource)
        headers = {
            "X-Api-Key": self.api_key,
            "X-Api-Resource-Id": resource,
            "X-Api-Request-Id": str(uuid.uuid4()),
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=180) as c:
                r = c.post(self.URL, headers=headers,
                           content=json.dumps(body, ensure_ascii=False).encode("utf-8"))
        except Exception as e:  # noqa: BLE001
            raise TTSError(f"合成请求失败: {e}") from e

        if r.status_code != 200:
            raise TTSError(f"合成失败 HTTP {r.status_code}: {r.text[:200]}")

        chunks: list[bytes] = []
        last_code = None
        for line in r.text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            code = d.get("code")
            if code not in (0, 20000000):
                raise TTSError(f"合成返回错误 {code}: {d.get('message')}")
            last_code = code
            data = d.get("data")
            if data:
                chunks.append(base64.b64decode(data))

        if not chunks:
            raise TTSError(f"合成没有返回音频（最后状态 {last_code}）")
        out.write_bytes(b"".join(chunks))
        return out


def get_tts(provider: str = "") -> SapiTTS | VolcTTS:
    from app.core.config import settings

    name = (provider or settings.tts_provider or "sapi").lower()
    if name == "volc":
        return VolcTTS()
    return SapiTTS()
