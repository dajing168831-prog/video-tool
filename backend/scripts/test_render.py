"""渲染链路自测：切分 → 配方 → 字幕 → 合成（不依赖任何外部 API）。

用法（在 backend/ 下）：
    python scripts/test_render.py <源视频> <工作目录> [--seconds 20]

这一步只验"结构 + 字幕 + 合成"对不对，ASR/TTS 接上之前先跑这个。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import compose, recipe, scene  # noqa: E402

def main() -> None:
    # 🚦 必须点名型号（2026-10-26）：一轮只跑一家
    from _model_gate import sel_or_exit as _sel
    _sel()
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("workdir")
    ap.add_argument("--seconds", type=float, default=20.0)
    ap.add_argument("--threshold", type=float, default=0.30)
    args = ap.parse_args()

    src = Path(args.source)
    work = Path(args.workdir)
    work.mkdir(parents=True, exist_ok=True)

    clip = work / "clip.mp4"
    scene.cut_clip(src, 0.0, args.seconds, clip)
    print(f"[1] 切片 {args.seconds}s -> {clip}")

    info = scene.probe(clip)
    print(f"[2] probe {info['width']}x{info['height']} {info['duration']}s "
          f"audio={info['has_audio']}")

    shots = scene.detect_shots(clip, threshold=args.threshold)
    print(f"[3] 镜头 {len(shots)} 个: "
          + ", ".join(f"{s.start:.2f}-{s.end:.2f}" for s in shots[:8]))

    rec = recipe.build_recipe(url="", probe=info, shots=shots)
    print(f"[4] 配方 shots={len(rec['shots'])} beats={len(rec['beats'])} "
          f"rhythm={rec['rhythm']}")

    # 🩸 2026-10-23 主人拍板「也不烧字幕」：本条冒烟测试不再生成字幕文件，
    # 只验证「切片 → 合成（带遮罩）」这条链路。
    base = recipe.segments_for_caption(rec)
    print(f"[5] 文案段 {len(base)} 条")

    out = work / "out.mp4"
    compose.compose(
        video=clip, out=out,
        mask=(0, int(info["height"] * 0.80), info["width"],
              int(info["height"] * 0.20), 0.55),
    )
    print(f"[7] 成片 {out} ({out.stat().st_size / 1024 / 1024:.1f} MB)")

    cover = compose.make_cover(out, work / "cover.jpg", at=2.0)
    print(f"[8] 封面 {cover}")


if __name__ == "__main__":
    main()
