# -*- coding: utf-8 -*-
"""商品短剧 · G1 批量作业（多商品一次排队，作业/条目落盘）。

出处：clipforge `src/app/api/batch/route.ts:1-125`（batch_jobs / batch_job_items 两张表）、
`src/app/batch/page.tsx:184-451`（执行器：并发 3、逐阶段写回、刷新后续跑）、
`src/lib/variation-plan.ts:1-115`（反同质化轮换计划）。

我们**没有数据库**，用一份 JSON（`<data>/batch/jobs.json`）等价落盘，语义逐条对齐：
  · 同一时间只有**一个在飞作业**：新建作业时把仍标 running 的旧作业结算成 cancelled
    （竞品 `route.ts:31-32`）。
  · 条目状态只用竞品那五个：pending / generating / composing / done / failed
    （`route.ts:70`）；作业状态 running / done / cancelled（`route.ts:86`）。
  · 条目错误截 500（`route.ts:79`）。
  · 每阶段的写回都是 best-effort：写失败**不许**打断整批（竞品 `page.tsx:229-237`）。

**与竞品的差异（诚实记账，别当已做）**：
  · 竞品执行器在**浏览器**里跑（页面关了就停，靠落盘续跑）；我们的执行器也在前端，
    但最后一步只到「分镜就绪」——出片要主人自己点（我们的硬规矩：出片只归主人）。
  · 轮换维度：钩子 H1–H5 / 免费中文音色 / 卡拉OK字幕隔条开。竞品的 BGM 情绪档、
    风格轮换、时长抖动我们没有对应物（合成 BGM 只收上传文件；剧本风格由模板/结构卡定；
    片长只支持 15/30/60），不编。
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

from app.services import drama_tts

#: 竞品 `route.ts:70` 原表
ITEM_STATUSES = ("pending", "generating", "composing", "done", "failed")
#: 竞品 `route.ts:86` 原表
JOB_STATUSES = ("running", "done", "cancelled")
MAX_ERROR = 500

#: 我们结构卡的五个开头策略（`D:/skills/product-drama/references/hook.md:7-13` 原表）
HOOKS = (
    ("H1", "画面冲击"),
    ("H2", "反常识提问"),
    ("H3", "反差错位"),
    ("H4", "明确利益"),
    ("H5", "情绪戳点"),
)
#: 竞品只轮中文免费音色（`variation-plan.ts:72`）
ZH_VOICES = [v for v in drama_tts.FREE_TTS_VOICES if v.get("lang") == "zh-CN"]


class BatchError(ValueError):
    """参数不合法（给界面看的原话）。"""


# ---------------------------------------------------------------------------
# 存储
# ---------------------------------------------------------------------------


def store_path(data_dir: Path) -> Path:
    """放在子目录里：`/projects` 只扫 `*.json`，不能让作业文件冒充项目。"""
    return Path(data_dir) / "batch" / "jobs.json"


def load(path: Path) -> dict:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"jobs": []}
    jobs = raw.get("jobs") if isinstance(raw, dict) else None
    return {"jobs": jobs if isinstance(jobs, list) else []}


def save(path: Path, state: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def _now_ms() -> int:
    return int(time.time() * 1000)


# ---------------------------------------------------------------------------
# 反同质化计划（`variation-plan.ts:66-115`）
# ---------------------------------------------------------------------------


def _i32(v: int) -> int:
    """JS 位运算的 int32 语义（`x | 0` 那种）。"""
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v >= 0x80000000 else v


def _imul(a: int, b: int) -> int:
    """JS `Math.imul`：32 位有符号乘法，溢出取低 32 位。"""
    return _i32((a & 0xFFFFFFFF) * (b & 0xFFFFFFFF))


def _mulberry32(seed: int):
    """竞品 `variation-plan.ts:44-53` 同款 PRNG（对拍见 `temp/probe_drama_batch.py`）。"""
    a = seed & 0xFFFFFFFF

    def rnd() -> float:
        nonlocal a
        a = _i32(a + 0x6D2B79F5)
        t = _imul(a ^ ((a & 0xFFFFFFFF) >> 15), 1 | a)
        old = t
        t = _i32(t + _imul(old ^ ((old & 0xFFFFFFFF) >> 7), 61 | old)) ^ old
        return (((t & 0xFFFFFFFF) ^ ((t & 0xFFFFFFFF) >> 14)) & 0xFFFFFFFF) / 4294967296

    return rnd


def build_plan(count: int, *, seed: int = 1, rotate_voice: bool = True) -> list[dict]:
    """把 `count` 条排成互不雷同的槽位；同一 seed 结果可复现。

    维度与竞品一致的部分：钩子、音色、字幕（卡拉OK 隔条开）、「第 4 条起有变化」的节奏。
    缺的维度见文件头（不编）。
    """
    if count <= 0:
        return []
    rnd = _mulberry32(seed or 1)
    start = lambda n: int(rnd() * n)  # noqa: E731
    hook_start = start(len(HOOKS))
    voice_start = start(max(1, len(ZH_VOICES)))

    slots: list[dict] = []
    for i in range(count):
        hook_id, hook_name = HOOKS[(hook_start + i) % len(HOOKS)]
        slot = {
            "index": i,
            "hook_id": hook_id,
            "hook_name": hook_name,
            # 竞品 `variation-plan.ts:93`：隔条开卡拉OK
            "karaoke": i % 2 == 1,
        }
        if rotate_voice and ZH_VOICES:
            v = ZH_VOICES[(voice_start + i) % len(ZH_VOICES)]
            slot["voice"] = v["value"]
            slot["voice_label"] = v["label"]
        slots.append(slot)
    return slots


def describe_slot(slot: dict) -> str:
    """一行给界面看（竞品 `variation-plan.ts:106-115` 的字段顺序）。"""
    bits = [f"钩子:{slot.get('hook_name') or slot.get('hook_id') or '—'}"]
    if slot.get("voice_label"):
        bits.append("音色:" + str(slot["voice_label"]).split(" ·")[0])
    bits.append("卡拉OK字幕" if slot.get("karaoke") else "短句卡字幕")
    return " · ".join(bits)


# ---------------------------------------------------------------------------
# 作业 / 条目
# ---------------------------------------------------------------------------


def _norm_item(raw) -> dict | None:
    """竞品 `route.ts:25-27`：productId / productName 必须都是字符串，其余一个不留。"""
    if not isinstance(raw, dict):
        return None
    pid, name = raw.get("product_id"), raw.get("product_name")
    if not isinstance(pid, str) or not isinstance(name, str) or not pid or not name:
        return None
    variation = raw.get("variation")
    return {
        "id": uuid.uuid4().hex[:12],
        "product_id": pid,
        "product_name": name,
        "variation": variation if isinstance(variation, str) else None,
        "status": "pending",
        "project_id": None,
        "composition_id": None,
        "error": None,
        "updated_ms": _now_ms(),
    }


def create_job(state: dict, config: dict | None, items: list) -> dict:
    """新建作业。返回 `{job_id, items:[{id, product_id}]}`（竞品 `route.ts:19-55`）。"""
    rows = [r for r in (_norm_item(x) for x in (items or [])) if r]
    if not rows:
        raise BatchError("缺少批量条目")
    now = _now_ms()
    # 竞品 `route.ts:31-32`：同一时间只留一个在飞作业
    for job in state["jobs"]:
        if job.get("status") == "running":
            job["status"] = "cancelled"
            job["updated_ms"] = now
    job = {
        "id": uuid.uuid4().hex[:12],
        "status": "running",
        "total": len(rows),
        "config": config if isinstance(config, dict) else {},
        "created_ms": now,
        "updated_ms": now,
        "items": rows,
    }
    state["jobs"].insert(0, job)
    return {"job_id": job["id"],
            "items": [{"id": r["id"], "product_id": r["product_id"]} for r in rows]}


def _find_job(state: dict, job_id: str) -> dict | None:
    return next((j for j in state["jobs"] if j.get("id") == job_id), None)


def patch(state: dict, body: dict) -> dict:
    """条目写回 / 作业结算（竞品 `route.ts:58-101` 两条分支）。"""
    item_id = body.get("item_id")
    # 空串 = 没传（Pydantic 默认 ""），不是「id 为空的条目」
    if isinstance(item_id, str) and item_id:
        p = body.get("patch") if isinstance(body.get("patch"), dict) else {}
        row = next((r for j in state["jobs"] for r in j.get("items") or []
                    if r.get("id") == item_id), None)
        if not row:
            raise BatchError("批量条目不存在")
        st = p.get("status")
        if isinstance(st, str) and st in ITEM_STATUSES:
            row["status"] = st
        if isinstance(p.get("project_id"), str):
            row["project_id"] = p["project_id"]
        if isinstance(p.get("composition_id"), str):
            row["composition_id"] = p["composition_id"]
        if isinstance(p.get("error"), str):
            row["error"] = p["error"][:MAX_ERROR]
        row["updated_ms"] = _now_ms()
        return {"ok": True}

    job_id, status = body.get("job_id"), body.get("status")
    if isinstance(job_id, str) and isinstance(status, str) and status in JOB_STATUSES:
        job = _find_job(state, job_id)
        if not job:
            raise BatchError("批量作业不存在")
        job["status"] = status
        job["updated_ms"] = _now_ms()
        return {"ok": True}
    raise BatchError("无效的更新请求")


def get(state: dict, *, job_id: str = "", active: bool = False) -> dict:
    """`?jobId=` → 指定作业；`?active=1` → 最新 running；否则最新一个（`route.ts:104-117`）。"""
    job = None
    if job_id:
        job = _find_job(state, job_id)
    elif active:
        job = next((j for j in state["jobs"] if j.get("status") == "running"), None)
    elif state["jobs"]:
        job = state["jobs"][0]
    if not job:
        return {"job": None, "items": []}
    return {"job": job, "items": list(job.get("items") or [])}


def summary(job: dict | None) -> dict:
    """给界面的一行计数（不改变原结构，纯派生）。"""
    items = list((job or {}).get("items") or [])
    counts = {k: sum(1 for r in items if r.get("status") == k) for k in ITEM_STATUSES}
    return {"total": len(items), **counts,
            "done_or_failed": counts["done"] + counts["failed"]}
