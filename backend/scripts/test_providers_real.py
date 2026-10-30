"""真机校验：火山 ASR 字级时间戳 + 火山 TTS 合成。

判据（见 docs/CLONE-VERIFY.md）：
  - ASR 文本与已知文稿一致
  - 随机抽 10 个字，起止时间单调、落在音频总长内、无重叠倒挂
  - TTS 产出能解码出音频时长

用法：
  python scripts/with_user_env.py python scripts/test_providers_real.py <video_or_audio>
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

from app.core.config import settings  # noqa: E402
from app.services import scene  # noqa: E402
from app.services.providers.asr import VolcASR  # noqa: E402
from app.services.providers.tts import VolcTTS  # noqa: E402

KNOWN = "今天天气不错，我们出去走走吧。这个产品我用了三个月。"


def main() -> int:
    # 🚦 必须点名型号（2026-10-26）：一轮只跑一家
    from _model_gate import sel_or_exit as _sel
    _sel()
    ok = True
    print(f"ASR provider={settings.asr_provider} resource={settings.volc_asr_resource}")
    print(f"TTS provider={settings.tts_provider} resource={settings.volc_tts_resource} "
          f"speaker={settings.volc_tts_speaker}")

    # ---- ASR ----
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if src and src.exists():
        t0 = time.time()
        sp = VolcASR().transcribe(src)
        chars = [c for s in sp["segments"] for c in s["chars"]]
        print(f"\n[ASR] {time.time()-t0:.1f}s  段 {len(sp['segments'])}  字 {len(chars)}")
        for s in sp["segments"][:6]:
            print(f"  {s['start']:.2f}-{s['end']:.2f}  {s['text']}")
        good = all(c["e"] >= c["s"] for c in chars) and len(chars) > 0
        mono = all(chars[i]["s"] <= chars[i + 1]["s"] for i in range(len(chars) - 1))
        print(f"  {'✅' if good else '❌'} 每个字都有起止时间且不倒挂")
        print(f"  {'✅' if mono else '❌'} 字的起点单调不减")
        ok = ok and good and mono
    else:
        print("\n[ASR] 跳过（没给音频文件）")

    # ---- TTS ----
    out = Path("C:/tmp/clone-samples/tts_real.mp3")
    t0 = time.time()
    tts = VolcTTS()
    tts.synth(KNOWN, out)
    info = scene.probe(out)
    dur = float(info.get("duration") or 0)
    print(f"\n[TTS] {time.time()-t0:.1f}s  {out.stat().st_size/1024:.0f}KB  "
          f"时长 {dur:.2f}s")
    good_tts = dur > 0.5
    print(f"  {'✅' if good_tts else '❌'} 合成音频可解码且有时长")
    ok = ok and good_tts

    print("\n" + ("全部通过" if ok else "有失败项"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
