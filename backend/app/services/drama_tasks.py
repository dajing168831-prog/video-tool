"""C17 云端任务恢复 —— 扫「已提交但没取回」的付费任务，单独列、可领回。

出处：clipforge `api/ai/tasks/route.ts` + `lib/ai-tasks.ts`
  · `?projectId=&active=1` 只回 `submitted / processing / unknown` 三种；
  · 不带项目时跨项目列出**所有**在飞付费任务（「还有钱卡着吗」）；
  · 目的（issue #16）：任务号必须在平台确认的那一刻落盘 —— 轮询超时、崩溃、重启
    都不能把已经付过钱的任务弄丢；界面要把它们单独列出来，**提示别重复提交**。

我们的映射：
  · 任务源 = 项目文档里的 `film.running`（出片时**先登记再提交**，成功/失败才划掉；
    进程被杀 → 留在盘上 = 重启后看得见）。
  · 任务号源 = `<成片>.task.json`（`ark._save_tid` 写的 `{tid, sig}`）。
  · 状态只分两种，**不编 processing**：
      - `submitted`：盘上有任务号 → 可以去平台领回；
      - `unknown`：只登记了在飞、盘上没有任务号 → 不知道提交成功没有，先别重复提交。
  · 竞品的 `failed` 需要轮询平台才知道；我们不在列表接口里打平台（那会变成一次网络阻塞），
    由使用者点「领回」时才查。
"""
from __future__ import annotations

import json
from pathlib import Path

#: 仍需处理的两种状态（竞品的 active 集合去掉 processing —— 我们无法离线判定）
ACTIVE_STATUSES = ("submitted", "unknown")

#: 界面固定提示
ACTIVE_HINT = "这些是已经发出去的钱：先「领回」或去平台确认，**别重复提交**（会再付一次）。"


def state_path(films_dir: Path, pid: str, out_name: str) -> Path:
    """任务号文件的位置（与 `ark._save_tid` 的旧位置一致：`<成片>.task.json`）。"""
    return Path(films_dir) / pid / (Path(str(out_name)).name + ".task.json")


def read_state(path: Path) -> dict:
    """读任务号文件；缺失/坏 JSON 一律当空（不要因为一个坏文件让整个列表 500）。"""
    p = Path(path)
    try:
        d = json.loads(p.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def load_project(p: Path) -> dict | None:
    try:
        d = json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict) or not d.get("id") or not isinstance(d.get("product"), dict):
        return None
    return d


def scan(data_dir: Path, films_dir: Path, *, active: bool = True,
         limit: int = 200) -> dict:
    """跨项目扫在飞任务。返回 `{tasks, count, submitted, unknown, hint}`。"""
    data_dir, films_dir = Path(data_dir), Path(films_dir)
    rows: list[dict] = []
    if not data_dir.exists():
        return {"tasks": [], "count": 0, "submitted": 0, "unknown": 0, "hint": ACTIVE_HINT}

    for p in sorted(data_dir.glob("*.json")):
        doc = load_project(p)
        if not doc:
            continue
        pid = str(doc.get("id") or "")
        film = doc.get("film") or {}
        running = film.get("running") or {}
        files = film.get("files") or {}
        for no, info in sorted(running.items(), key=lambda kv: str(kv[0])):
            if not isinstance(info, dict):
                continue
            name = str(info.get("out") or "")
            tid = str(read_state(state_path(films_dir, pid, name)).get("tid") or "") if name else ""
            status = "submitted" if tid else "unknown"
            done_file = (files.get(str(no)) or {}).get("name") if isinstance(files, dict) else None
            row = {
                "pid": pid,
                "project_id": pid,
                "project_name": str((doc.get("product") or {}).get("name")
                                    or doc.get("name") or doc.get("topic") or ""),
                # 老字段：界面横幅以前按 `product` 读，保留别名不破旧版本
                "product": str((doc.get("product") or {}).get("name") or ""),
                "no": int(no) if str(no).isdigit() else no,
                "status": status,
                "at": str(info.get("at") or ""),
                "model": str(info.get("model") or ""),
                "seconds": info.get("seconds"),
                "out": name,
                "tid": tid,
                "can_resume": bool(tid),
                "state_file": state_path(films_dir, pid, name).name if name else "",
                # 盘上已经有同名成片：可能上次下载成功但没来得及记账 → 领回会补记账
                "out_exists": bool(name and (films_dir / pid / Path(name).name).exists()),
                # 文档里已经有这一段的成品记录：这条 running 是残留，可清除
                "recorded": bool(done_file),
            }
            rows.append(row)

    if active:
        rows = [r for r in rows if r["status"] in ACTIVE_STATUSES]
    rows.sort(key=lambda r: r.get("at") or "", reverse=True)
    total = len(rows)
    submitted = sum(1 for r in rows if r["status"] == "submitted")
    unknown = sum(1 for r in rows if r["status"] == "unknown")
    rows = rows[: max(1, int(limit))]
    return {
        "tasks": rows,
        "count": total,
        "submitted": submitted,
        "unknown": unknown,
        "hint": ACTIVE_HINT,
    }
