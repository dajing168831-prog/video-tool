"""端到端自测：分析 → 出片（不依赖火山，ASR 用占位、TTS 用系统音色）。

用法（在 backend/ 下）：
    python scripts/test_pipeline.py <源视频> <工作目录> [--seconds 20] [--script "新文案"]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import clone_pipeline, scene  # noqa: E402

DEFAULT_SCRIPT = (
    "这个东西我用了三个月。真的比想象中好用。"
    "第一它不占地方。第二它几乎不用充电。第三价格还不贵。"
    "想要的话点左下角。"
)


def main() -> None:
    # 🚦 必须点名型号（2026-10-26）：一轮只跑一家
    from _model_gate import sel_or_exit as _sel
    _sel()
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("workdir")
    ap.add_argument("--seconds", type=float, default=20.0)
    ap.add_argument("--script", default=DEFAULT_SCRIPT)
    args = ap.parse_args()

    src = Path(args.source)
    work = Path(args.workdir)
    work.mkdir(parents=True, exist_ok=True)

    clip = work / "clip.mp4"
    scene.cut_clip(src, 0.0, args.seconds, clip)
    print(f"[0] 切片 {args.seconds}s")

    t0 = time.time()
    rec = clone_pipeline.analyze(
        clip, workdir=work / "analyze",
        progress=lambda s, p: print(f"    analyze {s} {p}%"),
    )
    print(f"[1] 配方完成 {time.time() - t0:.1f}s  "
          f"shots={len(rec['shots'])} segs={len(rec['speech']['segments'])}")

    t1 = time.time()
    res = clone_pipeline.render(
        clip, rec, script=args.script, workdir=work / "render",
        progress=lambda s, p: print(f"    render  {s} {p}%"),
    )
    elapsed = time.time() - t1
    info = scene.probe(res["video"])
    print(f"[2] 出片完成 {elapsed:.1f}s")
    print(f"    成片 {res['video']}  {res['video'].stat().st_size/1024/1024:.2f} MB  "
          f"{info['duration']}s  {info['width']}x{info['height']}")
    print(f"    封面 {res['cover']}")
    print(f"    字幕 {len(res['segments'])} 段")


if __name__ == "__main__":
    main()
