"""剧本结构模板 —— 把一条跑通的片子的分镜节奏存下来，下次用别的商品重写。

出处：clipforge `src/lib/stores/template-store.ts:1-66`（`ScriptTemplate` 与三条
store 方法）+ `src/app/project/[id]/script/page.tsx:281-293`（存为模板的载荷）
+ `src/app/project/new/page.tsx:580-587`（模板 → `referenceStructure` 的序列化）
+ `src/lib/script-engine/prompts.ts:875-877`（注入提示词的那一段，逐字）。

⚠️ **和「成片模板」不是一回事**，两者平级、互不依赖：
  · 成片模板（`drama_templates.py`）= 竞品 391 条**配方**，管画面形态/光线/运镜/合成
  · 剧本模板（本文件）= **你自己的**片子跑通后存下的**镜头节奏**，管分镜数量与时长分配
竞品也是两套（ad-templates vs template-store），别合并。

字段映射（我们的分镜没有竞品的 `type`，有 `purpose`/`product`）：
  竞品 `1. [hook] 3s 环绕 口播参考：「…」`
  我们 `1. 3s 近景 固定｜口播参考：「…」｜作用：…`
  表达的是同一件事：这一镜多长、怎么拍、说什么、为什么在这。
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path

FILE = Path(__file__).resolve().parents[2] / "data" / "drama" / "script_templates.json"
_LOCK = threading.Lock()

#: 一条模板最多存几镜（保护提示词，别让一个 60 镜的怪物把上下文吃光）
MAX_SHOTS = 40
#: 存模板时每镜保留的字段
SHOT_KEYS = ("id", "duration", "framing", "camera", "description", "dialogue", "product", "purpose")


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


def _clean(shots) -> list[dict]:
    out = []
    for s in (shots or [])[:MAX_SHOTS]:
        if not isinstance(s, dict):
            continue
        row = {k: s.get(k) for k in SHOT_KEYS if k in s}
        try:
            row["duration"] = round(float(row.get("duration") or 0), 1)
        except (TypeError, ValueError):
            row["duration"] = 0.0
        if row["duration"] <= 0 or not str(row.get("description") or "").strip():
            continue
        out.append(row)
    return out


def list_all() -> list[dict]:
    """最新在前；同一秒内按写入顺序倒序。"""
    rows = _read()
    order = sorted(enumerate(rows), key=lambda iv: ((iv[1].get("created") or ""), iv[0]), reverse=True)
    return [r for _, r in order]


def get(tid: str | None) -> dict | None:
    if not tid:
        return None
    return next((r for r in _read() if r.get("id") == tid), None)


def add(*, name: str, shots, style_type: str = "", source_project_id: str = "") -> dict | None:
    """存一条。分镜洗完是空的就不存（存个空模板等于骗人）。"""
    clean = _clean(shots)
    if not clean:
        return None
    row = {
        "id": uuid.uuid4().hex[:12],
        "name": (name or "").strip()[:24] or "未命名结构",
        "style_type": style_type or "",
        "shots": clean,
        "total_duration": round(sum(s["duration"] for s in clean), 1),
        "source_project_id": source_project_id or "",
        "use_count": 0,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with _LOCK:
        rows = _read()
        rows.append(row)
        _write(rows)
    return row


def bump(tid: str) -> dict | None:
    """用过一次就 +1（竞品 `incrementUseCount`）。不存在不报错，返回 None。"""
    with _LOCK:
        rows = _read()
        for i, r in enumerate(rows):
            if r.get("id") == tid:
                rows[i]["use_count"] = int(r.get("use_count") or 0) + 1
                _write(rows)
                return rows[i]
    return None


def delete(tid: str) -> bool:
    with _LOCK:
        rows = _read()
        left = [r for r in rows if r.get("id") != tid]
        if len(left) == len(rows):
            return False
        _write(left)
        return True


def _dur(v) -> str:
    """时长写成 4s / 4.5s —— 竞品是 JS 数字直接拼串（`4` 不会写成 `4.0`）。"""
    try:
        d = round(float(v or 0), 1)
    except (TypeError, ValueError):
        d = 0.0
    return f"{int(d)}" if d == int(d) else f"{d}"


def reference_structure(template: dict) -> str:
    """模板 → 逐镜参考行（竞品 `new/page.tsx:580-587` 的等价写法）。"""
    lines = []
    for i, s in enumerate((template or {}).get("shots") or []):
        bits = [f"{_dur(s.get('duration'))}s"]
        if s.get("framing"):
            bits.append(str(s["framing"]))
        if s.get("camera"):
            bits.append(str(s["camera"]))
        line = f"{i + 1}. {' '.join(bits)}｜口播参考：「{s.get('dialogue') or ''}」"
        if s.get("purpose"):
            line += f"｜作用：{s['purpose']}"
        lines.append(line)
    return "\n".join(lines)


def prompt_block(template: dict) -> str:
    """注入分镜提示词的那一段（`prompts.ts:875-877` 逐字，只把「脚本」换成「分镜」）。"""
    body = reference_structure(template)
    if not body:
        return ""
    return ("\n\n【参考爆款结构】\n"
            "请参考以下经过验证的高转化分镜结构（镜头类型、节奏、转化逻辑），"
            "用本商品重新创作分镜（不要照搬文案，要贴合本商品卖点）：\n"
            f"{body}\n")


def public(row: dict) -> dict:
    """界面用：不把整份分镜都吐出来，给个数和总时长就够列表展示。"""
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "style_type": row.get("style_type"),
        "shots_count": len(row.get("shots") or []),
        "total_duration": row.get("total_duration"),
        "source_project_id": row.get("source_project_id"),
        "use_count": int(row.get("use_count") or 0),
        "created": row.get("created"),
    }
