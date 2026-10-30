"""语音识别：拿到"哪个字在什么时候说出来"。

这是整条复刻链的枢纽 —— 它跑两次：
  第一次：读原片，拿到原片的逐字时间轴（＝结构）
  第二次：读 TTS 生成的新音轨，拿到新文案的逐字时间轴（＝对齐）

为什么必须跑第二次：改写后的文案长短变了，TTS 出来的音频时长也就变了。
只有对"新音轨"再识别一次，逐句文案才能和新配音严丝合缝。

两个实现：
  VolcASR —— 火山大模型录音文件识别（show_utterances=true 才有字级时间戳）
  MockASR —— 占位，按给定窗口均分。只用于在没有 Key 时跑通链路。
"""
from __future__ import annotations

import base64
import logging
import subprocess
import uuid
from pathlib import Path

import httpx

log = logging.getLogger(__name__)


class ASRError(RuntimeError):
    pass


def _even_segments(windows: list[tuple[float, float]], text: str,
                   lang: str = "zh") -> dict:
    """把一段文字按给定窗口均分（占位用）。"""
    text = (text or "").strip()
    if not text or not windows:
        return {"has": False, "lang": lang, "segments": []}

    total = sum(max(0.05, e - s) for s, e in windows)
    segs = []
    idx = 0
    for s, e in windows:
        span = max(0.05, e - s)
        n = max(1, round(len(text) * span / total)) if total else 0
        chunk = text[idx: idx + n]
        idx += n
        if not chunk:
            continue
        step = span / len(chunk)
        segs.append({
            "start": round(s, 3),
            "end": round(e, 3),
            "text": chunk,
            "chars": [
                {"c": c, "s": round(s + i * step, 3),
                 "e": round(s + (i + 1) * step, 3)}
                for i, c in enumerate(chunk)
            ],
        })
    # 尾巴上的字并进最后一段，避免丢字
    if idx < len(text) and segs:
        segs[-1]["text"] += text[idx:]
    return {"has": bool(segs), "lang": lang, "segments": segs}


class MockASR:
    """没有 Key 时的占位实现。

    它不假装自己识别到了什么 —— 产出的时间轴是"按窗口均分"，
    只用来验证渲染链路，不能当识别结果用。
    """

    name = "mock"

    def transcribe(self, audio: Path, *, windows: list[tuple[float, float]] | None = None,
                   text: str = "", lang: str = "zh") -> dict:
        # 没给文稿就如实返回"没识别到" —— 编一段占位文字混进产品界面，
        # 用户会以为那是原片说的话。
        if not text:
            return {"has": False, "lang": lang, "segments": []}
        if not windows:
            from app.services import scene
            info = scene.probe(audio)
            windows = [(0.0, float(info.get("duration") or 3.0))]
        return _even_segments(windows, text, lang)


class VolcASR:
    """豆包录音文件识别 2.0（生产）。

    用 flash 接口而不是 submit+query：flash 支持把音频 base64 直接塞进请求体，
    不需要先传到公网可访问的地址。省掉一层 OSS，对我们这种"音频就在本机磁盘"
    的场景是决定性优势（submit 的 audio.url 必须是公网地址）。

    返回 utterances[].words[]，每个词带毫秒级 start_time / end_time。
    中文基本按单字切，直接就是我们要的"字级时间戳"。

    实测（2026-10-21）：已知文稿音频 2 句、23 个字，识别文本 100% 一致，
    每个字都有独立的起止时间。
    """

    name = "volc"
    ext = ".wav"

    FLASH = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash"
    MAX_BYTES = 500 * 1024 * 1024

    def __init__(self, api_key: str = "", resource: str = "") -> None:
        from app.core.config import settings

        self.api_key = (api_key or settings.volc_api_key).strip()
        self.resource = (resource or settings.volc_asr_resource).strip()

    # -- 音频准备 ---------------------------------------------------------

    def _to_wav(self, audio: Path) -> tuple[Path, bool]:
        """统一转 16k 单声道 wav。返回 (路径, 是否临时文件)。

        视频文件也能直接传进来 —— ffmpeg 用 -vn 丢掉画面只取音轨。
        """
        from app.services.media import ffmpeg_path

        tmp = audio.with_name(audio.stem + ".asr16k.wav")
        ff = ffmpeg_path()
        if not ff:
            raise ASRError("找不到 ffmpeg")
        proc = subprocess.run(
            [ff, "-hide_banner", "-loglevel", "error", "-y", "-i", str(audio),
             "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(tmp)],
            capture_output=True, text=True, errors="ignore", timeout=600,
        )
        if proc.returncode != 0 or not tmp.exists():
            raise ASRError(f"音频转码失败: {(proc.stderr or '')[-300:]}")
        return tmp, True

    # -- 主流程 -----------------------------------------------------------

    def transcribe(self, audio: Path, *, windows=None, text: str = "",
                   lang: str = "zh") -> dict:
        from app.core.config import settings

        if not self.api_key:
            raise ASRError("豆包语音未配置：请设置 VT_VOLC_API_KEY")

        wav, is_tmp = self._to_wav(Path(audio))
        try:
            size = wav.stat().st_size
            if size > self.MAX_BYTES:
                raise ASRError(f"音频 {size/1024/1024:.0f}MB 超过接口上限")
            payload = {
                "user": {"uid": settings.volc_uid},
                "audio": {
                    "format": "wav",
                    "data": base64.b64encode(wav.read_bytes()).decode(),
                },
                "request": {
                    "model_name": "bigmodel",
                    "show_utterances": True,   # 不给这个就没有 words 字级时间
                    # 🩸 2026-10-25：说话人分离要**单独开**。官方《大模型ASR-说话人分离
                    # 最佳实践》原文要求 `enable_speaker_info=true` **且**必须同时
                    # `show_utterances=true`，响应才会带说话人编号。
                    # 以前只传了 show_utterances，于是 117 段台词一个编号都没回来，
                    # `_assign_speakers` 只能靠"单人镜头"硬推，两人同框就判不出。
                    "enable_speaker_info": True,
                    "enable_punc": True,
                    "enable_itn": True,
                },
            }
            with httpx.Client(timeout=300) as c:
                r = c.post(self.FLASH, headers=self._headers(), json=payload)
        finally:
            if is_tmp:
                wav.unlink(missing_ok=True)

        code = r.headers.get("X-Api-Status-Code") or ""
        msg = r.headers.get("X-Api-Message") or ""
        if code == "20000003":          # 静音音频：没有检测到人声
            log.info("ASR 判定为静音音频")
            return {"has": False, "lang": lang, "segments": []}
        if r.status_code != 200 or code != "20000000":
            raise ASRError(f"识别失败 HTTP {r.status_code} [{code}] {msg} "
                           f"{r.text[:200]}")
        return _from_volc(r.json(), lang)

    def _headers(self) -> dict:
        return {
            "X-Api-Key": self.api_key,
            "X-Api-Resource-Id": self.resource,
            "X-Api-Request-Id": str(uuid.uuid4()),
            "Content-Type": "application/json",
        }


def _from_volc(d: dict, lang: str) -> dict:
    """火山响应 → 我们内部的 speech 结构（时间换成秒）。"""
    result = d.get("result") or {}
    utts = result.get("utterances") or []
    segs = []
    for u in utts:
        words = u.get("words") or []
        chars = [
            {
                "c": (w.get("text") or "").strip(),
                "s": round(float(w.get("start_time") or 0) / 1000, 3),
                "e": round(float(w.get("end_time") or 0) / 1000, 3),
            }
            for w in words
            if (w.get("text") or "").strip()
        ]
        text = (u.get("text") or "").strip()
        if not text and not chars:
            continue
        # 🩸 说话人编号在这里：`utterances[].additions.speaker`（官方返回示例
        # `"additions": {"channel_id": "1", "speaker": "1"}`）。
        # 来源是请求里的 `show_utterances` —— 官方参数表原文：「**启用输出分句、
        # 分词、说话人及语音停顿信息**，默认为 false」（《录音文件识别极速版HTTP》
        # 请求参数 `show_utterances`）。我们早就传了 true，只是一直没往上取。
        add = u.get("additions") or {}
        # 两种返回形态都要认：`additions.speaker`（我们现在见到的）和
        # 顶层 `speaker_id`（官方最佳实践示例里的写法）。只有一个时就用那个。
        _spk = str(add.get("speaker") or u.get("speaker_id") or "").strip()
        segs.append({
            "start": round(float(u.get("start_time") or 0) / 1000, 3),
            "end": round(float(u.get("end_time") or 0) / 1000, 3),
            "text": text,
            "chars": chars,
            "speaker": _spk,
        })
    # 说话人分离到底有没有生效，跑一次就能在日志里看见（不用另外花钱验证）
    _spk = {s["speaker"] for s in segs if s.get("speaker")}
    if _spk:
        log.info("ASR 说话人分离：%d 段台词，识别到 %d 个说话人（%s）",
                 len(segs), len(_spk), "/".join(sorted(_spk)))
    elif segs:
        log.info("ASR 未返回说话人编号（%d 段），逐句说话人走画面推断", len(segs))
    return {"has": bool(segs), "lang": lang, "segments": segs}


def get_asr(provider: str = ""):
    from app.core.config import settings

    name = (provider or settings.asr_provider or "mock").lower()
    if name == "volc":
        return VolcASR()
    return MockASR()
