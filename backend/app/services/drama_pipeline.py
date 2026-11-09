"""商品短剧 · 一键流水线（判官 → 配画面 → 合成）。

出处：竞品 `lib/pipeline-stages.ts:10`（`PIPELINE_STAGES = ["judge","stock_fill","compose"]`）
与 `api/project/[id]/pipeline/route.ts:1-14`（服务端 hands-off，可断点续跑）。

我们与竞品一致的三点：
  1. 顺序就是这三段，**全部零生成费**（判官 / 配画面 / 本地 ffmpeg 合成，都不出片）；
  2. `from_stage` 支持从任一阶段续跑（`stagesFrom`：未知值回落全链，早跑安全、晚跑会漏）；
  3. 进度落在项目文档里（`doc["pipeline"]`），进程被杀后仍能看出跑到哪。

与竞品不同的一点（写清楚，免得以后又「掐头去尾」）：
  竞品用数据库表 `pipeline_runs` 记每次运行；我们是单文件项目 JSON，
  只保留**最近一次**运行记录（`doc["pipeline"]`）+ 进程内任务表（用于判断是否在跑）。
"""
from __future__ import annotations

import time

STAGES: tuple[str, ...] = ("judge", "stock_fill", "compose")

LABELS: dict[str, str] = {
    "judge": "判官团审稿",
    "stock_fill": "配画面",
    "compose": "合成",
}


def stages_from(value: object) -> list[str]:
    """从 `from` 开始要跑的阶段；不认识的值按全链（早跑安全）。"""
    v = str(value or "")
    idx = STAGES.index(v) if v in STAGES else 0
    return list(STAGES[idx:])


def new_run(stages: list[str]) -> dict:
    return {
        "status": "running",
        "stage": stages[0] if stages else "",
        "stages": list(stages),
        "started": time.strftime("%Y-%m-%d %H:%M:%S"),
        "finished": "",
        "results": {},
        "error": "",
    }


def is_running(run: dict | None) -> bool:
    return str((run or {}).get("status") or "") == "running"


def label(stage: str) -> str:
    return LABELS.get(stage, stage)
