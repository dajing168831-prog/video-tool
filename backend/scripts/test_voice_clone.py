"""声音复刻的本地自检（不发网络请求、不花钱、不消耗复刻额度）。

覆盖：槽位 ID 形状、音频转码（24k 单声道 wav）、10MB 上限、合成资源选择。
运行：python scripts/test_voice_clone.py
"""
from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.core.config import settings  # noqa: E402
from app.services import media, voice_clone  # noqa: E402
from app.services.providers import tts as tts_mod  # noqa: E402

PASS = FAIL = 0


def check(name: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {name}: {got}")
    else:
        FAIL += 1
        print(f"  FAIL {name}: got={got!r} want={want!r}")


def _audio_info(path: Path) -> str:
    p = subprocess.run([media.ffmpeg_path(), "-hide_banner", "-i", str(path)],
                       capture_output=True, text=True, errors="ignore", timeout=30)
    m = re.search(r"Audio:.*?, (\d+) Hz, ([^,]+)", p.stderr or "")
    return f"{m.group(1)}Hz {m.group(2).strip()}" if m else ""


def main() -> int:
    # 🚦 必须点名型号（2026-10-26）：一轮只跑一家
    from _model_gate import sel_or_exit as _sel
    _sel()
    print("== 音色槽位 ID ==")
    check("S_123456 合法", voice_clone.valid_speaker_id("S_123456"), True)
    check("没有前缀不合法", voice_clone.valid_speaker_id("123456"), False)
    check("空的不合法", voice_clone.valid_speaker_id(""), False)
    check("路径穿越不合法", voice_clone.valid_speaker_id("S_../../x"), False)
    check("太长不合法", voice_clone.valid_speaker_id("S_" + "a" * 80), False)

    work = Path(tempfile.mkdtemp(dir="D:/tmp", prefix="vclone_"))
    try:
        src = work / "voice.wav"
        subprocess.run(
            [media.ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y",
             "-f", "lavfi", "-i", "sine=frequency=220:duration=3",
             "-ar", "44100", "-ac", "2", str(src)],
            check=True,
        )
        print("== 音频转码 ==")
        raw, fmt, dur = voice_clone.prepare_audio(src)
        check("统一发 wav", fmt, "wav")
        check("转出来不是空的", len(raw) > 1000, True)
        check("时长读出来了", round(dur, 1), 3.0)
        # 官方推荐 24kHz 单声道；转码后必须真的是这个规格
        probe = work / "out.wav"
        probe.write_bytes(raw)
        check("24kHz 单声道", _audio_info(probe), "24000Hz mono")

        print("== 上限 ==")
        big = work / "big.wav"
        big.write_bytes(b"\0" * (voice_clone.MAX_BYTES + 1))
        try:
            voice_clone.prepare_audio(big)
            check("超过 10MB 被拦", False, True)
        except voice_clone.VoiceCloneError:
            check("超过 10MB 被拦", True, True)

        print("== 合成资源 ==")
        # 🩸 复刻音色用 ICL 资源，预设音色用默认资源（官方 SoundReplicaAPI-V3）
        check("S_ 音色走 ICL 资源",
              tts_mod.resource_for("S_abcdef"), settings.volc_icl_resource)
        check("预设音色走默认资源",
              tts_mod.resource_for("zh_female_xiaohe_uranus_bigtts"),
              settings.volc_tts_resource)

        # 🩸 请求体/请求头逐字段对官方 —— 不真发请求，只截下真正要发的东西。
        # 训练一次就是一次复刻额度（官方每资源 15 次），发错字段 = 白烧一次。
        print("== 真正发出去的请求（截获，不联网）==")
        seen: list[dict] = []

        class _Resp:
            status_code = 200

            def __init__(self, payload):
                self._p = payload

            def json(self):
                return self._p

            @property
            def text(self):
                return str(self._p)

        class _Client:
            def __init__(self, *a, **kw):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def post(self, url, headers=None, content=None, **kw):
                seen.append({"url": url, "headers": headers or {},
                             "body": json.loads((content or b"{}").decode("utf-8"))})
                if url.endswith("get_voice"):
                    return _Resp({"status": 2, "speaker_status": [
                        {"demo_audio": "https://x.test/demo.mp3"}]})
                return _Resp({"status": 1})

        real_client = voice_clone.httpx.Client
        voice_clone.httpx.Client = _Client
        object.__setattr__(settings, "volc_api_key", "test-key")
        try:
            r = voice_clone.train("S_123456", src, lang="zh")
            req = seen[-1]
            check("训练地址是官方 v3 voice_clone",
                  req["url"], "https://openspeech.bytedance.com/api/v3/tts/voice_clone")
            check("带 X-Api-Key", req["headers"].get("X-Api-Key"), "test-key")
            check("带 X-Api-Request-Id", bool(req["headers"].get("X-Api-Request-Id")), True)
            check("训练不带 X-Api-Resource-Id（官方 V3 没有这个头）",
                  "X-Api-Resource-Id" in req["headers"], False)
            check("speaker_id 原样发", req["body"].get("speaker_id"), "S_123456")
            check("音频格式 wav", req["body"]["audio"].get("format"), "wav")
            check("音频是 base64 且能还原出 wav",
                  base64.b64decode(req["body"]["audio"]["data"])[:4], b"RIFF")
            check("中文 language=0", req["body"].get("language"), 0)
            check("训练回报带状态文案", r["status_text"], "Training")

            st = voice_clone.status("S_123456")
            req2 = seen[-1]
            check("查询地址是官方 v3 get_voice",
                  req2["url"], "https://openspeech.bytedance.com/api/v3/tts/get_voice")
            check("查询体只带 speaker_id", req2["body"], {"speaker_id": "S_123456"})
            check("status=2 视为可用", st["ready"], True)
            check("带回试听音频", st["demo_audio"], "https://x.test/demo.mp3")
        finally:
            voice_clone.httpx.Client = real_client
    finally:
        shutil.rmtree(work, ignore_errors=True)

    print(f"\n{PASS}/{PASS + FAIL} 通过")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
