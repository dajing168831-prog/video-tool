"""「我的模板」落盘 —— 单机版，一个 JSON 文件。

对应竞品 `ad-template/mine` 路由的四条语义（GET/POST/PUT/DELETE），
存储从 Drizzle 表换成 `backend/data/drama/my_templates.json`（我们本来就是单用户）。

两条照抄的规矩：
  1. **写入永远先过 `sanitize` + 广告法警告** —— 客户端解析只是预览，不是闸门
     （`mine/route.ts:16-22`）。
  2. 导入/自建/编辑三种来源都记 `source`（ai / import / edit），列表里要能区分。
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path

from . import drama_templates as tpl

FILE = Path(__file__).resolve().parents[2] / "data" / "drama" / "my_templates.json"
_LOCK = threading.Lock()


def _read() -> list[dict]:
    if not FILE.exists():
        return []
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write(rows: list[dict]) -> None:
    FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, FILE)


def list_all() -> list[dict]:
    """最新在前（竞品 `orderBy(desc(createdAt))`）。

    同一秒内连存两条时 `created` 字符串相等 —— 用写入顺序兜底，
    否则「刚存的那条没在第一个」会被当成没存上。
    """
    rows = _read()
    order = sorted(enumerate(rows), key=lambda iv: ((iv[1].get("created") or ""), iv[0]), reverse=True)
    return [r for _, r in order]


def get(tid: str) -> dict | None:
    return next((r for r in _read() if r.get("id") == tid), None)


def add_many(templates: list[dict], source: str = "ai") -> list[dict]:
    """批量入库（单条保存与打包导入走同一条路）。id 在这里现生成。"""
    src = source if source in ("ai", "import", "edit") else "ai"
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    added = []
    with _LOCK:
        rows = _read()
        for t in templates:
            row = dict(t)
            row["id"] = uuid.uuid4().hex[:12]
            row["source"] = src
            row["created"] = now
            added.append(row)
            rows.append(row)
        _write(rows)
    return added


def update(tid: str, template: dict) -> dict | None:
    with _LOCK:
        rows = _read()
        for i, r in enumerate(rows):
            if r.get("id") != tid:
                continue
            merged = dict(template)
            merged["id"] = tid
            merged["source"] = r.get("source") or "edit"
            merged["created"] = r.get("created") or time.strftime("%Y-%m-%d %H:%M:%S")
            merged["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
            rows[i] = merged
            _write(rows)
            return merged
    return None


def delete(tid: str) -> bool:
    with _LOCK:
        rows = _read()
        left = [r for r in rows if r.get("id") != tid]
        if len(left) == len(rows):
            return False
        _write(left)
        return True


# ---- 两条入口都把输入先归一成「分享信封」，保证与导入走同一套校验 ----

def save_template(raw) -> dict:
    """保存一个（AI 定制结果 / 编辑器另存）。返回 {ok, template?, error?, warnings?}。"""
    envelope = json.dumps({"kind": tpl.SHARE_KIND, "version": tpl.SHARE_VERSION,
                           "template": raw}, ensure_ascii=False)
    return _save_envelope(envelope, source="ai")


def save_share(share_text: str, source: str = "import") -> dict:
    return _save_envelope(share_text, source=source)


def _save_envelope(text: str, *, source: str) -> dict:
    res = tpl.parse_share_any(text)
    if not res.get("templates"):
        code = res.get("error") or "invalid_template"
        return {"ok": False, "error": code, "message": tpl.SHARE_ERRORS.get(code, "模板内容无法解析")}
    rows = add_many(res["templates"], source=source)
    out = {"ok": True, "templates": rows, "template": rows[0]}
    if res.get("warnings"):
        out["warnings"] = res["warnings"]
    return out
