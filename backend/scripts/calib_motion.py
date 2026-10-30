"""在真实素材上量每镜运动量，给 VT_TRIAGE_MOTION_MIN 定档。

只读、零成本（纯 ffmpeg）。输出每镜的运动量和分位分布，
用来看默认阈值 1.2 在真实片子上到底切在哪。

运行：
  python scripts/calib_motion.py            # 扫 data/clone 下所有 source.mp4
  python scripts/calib_motion.py a.mp4 b.mp4
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import scene, triage  # noqa: E402


def pct(vals: list[float], q: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    i = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[i]


def scan(path: Path) -> list[dict]:
    d = scene.probe(path)
    # 别把 duration 当第二个位置参数传 —— 那是 threshold（默认 0.30）
    shots = scene.detect_shots(path)
    out = []
    for s in shots:
        try:
            m = scene.motion(path, s.start, s.end)
        except Exception as e:  # noqa: BLE001
            print(f"    ! {s.index}: {e}")
            m = 0.0
        out.append({"i": s.index, "start": s.start, "end": s.end,
                    "dur": round(s.end - s.start, 2), "motion": round(m, 2)})
    return out


def main(argv: list[str]) -> int:
    files = [Path(a) for a in argv] or sorted(Path("data/clone").glob("*/source.mp4"))
    if not files:
        print("没有素材")
        return 1
    allm: list[float] = []
    for f in files:
        if not f.exists():
            print(f"跳过（不存在）{f}")
            continue
        shots = scan(f)
        allm += [s["motion"] for s in shots]
        below = sum(1 for s in shots if s["motion"] < triage.MOTION_VIDEO_MIN)
        print(f"\n=== {f.parent.name[:8]} · {len(shots)} 镜 · "
              f"判静态 {below}/{len(shots)}（阈值 {triage.MOTION_VIDEO_MIN}）")
        for s in shots:
            tag = "still" if s["motion"] < triage.MOTION_VIDEO_MIN else "VIDEO"
            print(f"   镜{s['i']:>2}  {s['start']:7.2f}-{s['end']:7.2f} "
                  f"({s['dur']:5.2f}s)  motion={s['motion']:7.2f}  {tag}")

    if allm:
        print(f"\n=== 合计 {len(allm)} 镜 ===")
        for q, name in ((0.0, "最小"), (0.25, "25%"), (0.5, "中位"),
                        (0.75, "75%"), (0.9, "90%"), (1.0, "最大")):
            print(f"  {name:>4}: {pct(allm, q):7.2f}")
        for t in (0.5, 1.0, 1.2, 2.0, 3.0, 5.0):
            n = sum(1 for m in allm if m < t)
            print(f"  阈值 {t:>4} → {n}/{len(allm)} 镜判静态")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
