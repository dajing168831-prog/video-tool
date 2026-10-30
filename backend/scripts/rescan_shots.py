"""按**当前**的切分尺子重新刻一个任务的镜头表（不重跑识别、不花钱）。

什么时候要跑：分析结果是按当时的 `scene.detect_shots` 刻好存进 `task.json` 的，
切分尺子升级后，老任务里的 `recipe.shots` 还是旧刻度 —— 直接出片会沿用旧镜头表
（例如漏掉 24.43 的软切，那一段照样横跨换场）。

它做的事：
  1. 备份 `task.json` 成 `task.json.bak-<时间戳>`（同目录，随时可回滚）
  2. `scene.detect_shots` 重新刻镜头 + 逐镜重算运动量（纯 ffmpeg，秒级）
  3. 前 12 镜抽关键帧（和 analyze 同口径，UI 上的诊断卡不会空）
  4. 只改 `recipe.shots`，字幕/节拍/口播文案一律不动

用法：
    python scripts/rescan_shots.py --cid <cid>
    python scripts/rescan_shots.py --all        # 所有已分析的任务
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.core.config import settings  # noqa: E402
from app.services import scene  # noqa: E402

log = logging.getLogger("rescan")


def rescan(task_dir: Path) -> tuple[list, list] | None:
    task_file = task_dir / "task.json"
    src = task_dir / "source.mp4"
    if not task_file.exists() or not src.exists():
        return None
    task = json.loads(task_file.read_text(encoding="utf-8"))
    rec = task.get("recipe") or {}
    old = [(round(float(s["start"]), 3), round(float(s["end"]), 3))
           for s in rec.get("shots") or []]

    shots = scene.detect_shots(src)
    items = []
    kf_dir = task_dir / "keyframes"
    for s in shots:
        entry = {"i": s.index, "start": round(s.start, 3), "end": round(s.end, 3),
                 "dur": s.duration}
        try:
            entry["motion"] = scene.motion(src, s.start, s.end)
        except Exception as e:  # noqa: BLE001
            log.warning("运动量计算失败 shot=%s: %s", s.index, e)
            entry["motion"] = 0.0
        entry["keyframe"] = f"kf_{s.index:03d}.jpg"
        entry["ocr"] = []
        if s.index < 12:
            try:
                scene.extract_frame(src, s.start + min(0.3, s.duration / 2),
                                    kf_dir / entry["keyframe"])
            except Exception as e:  # noqa: BLE001
                log.warning("抽帧失败 shot=%s: %s", s.index, e)
        items.append(entry)
    new = [(x["start"], x["end"]) for x in items]

    backup = task_dir / f"task.json.bak-{time.strftime('%Y%m%d%H%M%S')}"
    shutil.copy2(task_file, backup)
    rec["shots"] = items
    task["recipe"] = rec
    task_file.write_text(json.dumps(task, ensure_ascii=False), encoding="utf-8")
    return old, new


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--cid", default="")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    root = Path(settings.clone_dir)
    if args.all:
        dirs = sorted(p for p in root.iterdir() if (p / "source.mp4").exists())
    elif args.cid:
        dirs = [root / args.cid]
    else:
        print("给 --cid <任务号> 或 --all")
        return 2
    done = 0
    for d in dirs:
        got = rescan(d)
        if got is None:
            print(f"跳过 {d.name}（没有 task.json 或 source.mp4）")
            continue
        old, new = got
        done += 1
        print(f"\n{d.name}\n  旧镜头 {len(old)}：{old}\n  新镜头 {len(new)}：{new}")
    print(f"\n完成 {done} 个任务")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
