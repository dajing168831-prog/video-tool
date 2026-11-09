"""出镜人物库 —— 跨项目复用的人物（有图传图，没图生成四视图定妆照）。

出处：clipforge `src/components/presenter-manager.tsx:1-60`（人物库管理器）+
`src/lib/stores/project-store.ts` 的 `Character`（id/name/description/appearance/
voiceStyle/referenceImages）+ `src/lib/character-sheet.ts:3-10`（四视图身份板）。

和项目内 `doc.cast` 的关系：
  · 本文件 = **全局库**（跟项目无关，换片子照样能挑）
  · `doc.cast` = 某个项目**实际用了**的人物（出图/出片只认它）
  · 「从人物库绑进项目」= 把库里的图复制进项目目录再写 `doc.cast`（见 api 里的
    `cast_from_library`），所以下游（九宫格/整片/质检）完全不区分来源。

存储：`data/drama/presenters.json`（列表）+ `data/drama/presenters/<id>.jpg`（图）。
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path

DIR = Path(__file__).resolve().parents[2] / "data" / "drama" / "presenters"
# 🩸 索引必须放在 `presenters/` 子目录里，**不能**放 `data/drama/` 根下：
# 那个目录是「一个 json = 一个项目」的仓库（`list_projects` 直接 glob *.json），
# 放个 list 进去会让 `GET /api/drama/projects` 整个 500（实测 2026-11-07：
# `AttributeError: 'list' object has no attribute 'get'`）。
FILE = DIR / "index.json"
_LOCK = threading.Lock()

MAX_NAME = 24
MAX_TEXT = 400


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


def _clean(s: str, limit: int) -> str:
    return " ".join(str(s or "").split())[:limit]


def public(row: dict) -> dict:
    """界面用：不吐文件系统路径，只给 id/名字/图名/来源。"""
    return {
        "id": row.get("id"),
        "name": row.get("name") or "",
        "appearance": row.get("appearance") or "",
        "note": row.get("note") or "",
        "image": row.get("image") or "",
        "source": row.get("source") or "",
        "created": row.get("created") or "",
    }


def list_all() -> list[dict]:
    return [public(r) for r in _read()]


def get(pid: str) -> dict | None:
    for r in _read():
        if r.get("id") == pid:
            return r
    return None


def image_path(pid: str) -> Path | None:
    row = get(pid)
    if not row or not row.get("image"):
        return None
    p = DIR / row["image"]
    return p if p.exists() else None


def create(name: str, appearance: str = "", note: str = "") -> dict:
    name = _clean(name, MAX_NAME)
    if not name:
        raise ValueError("缺人物名")
    with _LOCK:
        rows = _read()
        # 同名视为同一个人：直接返回，避免库里全是「小张」
        for r in rows:
            if r.get("name") == name:
                return public(r)
        row = {
            "id": "pr_" + uuid.uuid4().hex[:10],
            "name": name,
            "appearance": _clean(appearance, MAX_TEXT),
            "note": _clean(note, MAX_TEXT),
            "image": "",
            "source": "",
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        rows.append(row)
        _write(rows)
    return public(row)


def set_image(pid: str, filename: str, source: str) -> dict:
    with _LOCK:
        rows = _read()
        for r in rows:
            if r.get("id") == pid:
                r["image"] = filename
                r["source"] = source
                _write(rows)
                return public(r)
    raise KeyError(pid)


def update(pid: str, fields: dict) -> dict:
    with _LOCK:
        rows = _read()
        for r in rows:
            if r.get("id") == pid:
                for k in ("name", "appearance", "note"):
                    if k in fields:
                        lim = MAX_NAME if k == "name" else MAX_TEXT
                        r[k] = _clean(fields[k], lim)
                _write(rows)
                return public(r)
    raise KeyError(pid)


def delete(pid: str) -> None:
    with _LOCK:
        rows = _read()
        keep = [r for r in rows if r.get("id") != pid]
        if len(keep) == len(rows):
            raise KeyError(pid)
        _write(keep)
    # 图片留着不删（可能已被项目引用），只是从库里摘掉
