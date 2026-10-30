# -*- coding: utf-8 -*-
"""提示词对话历史 —— **存在后端**，换机器、换浏览器、清了缓存都还在。

🩸 2026-10-30 主人：「点了新对话，旧对话回不去了」。第一版只存在浏览器本地
（`localStorage`），换台机器就没了 —— 所以搬到后端：一个对话一个文件
`backend/data/prompt_sessions/<sid>.json`。

⛔ **只存文字**。截图是 data URI，几张就几十 MB；只记张数（`shots`），
   恢复时前端会标一句"这轮传过 N 张截图，历史里没留"。
⛔ 会话 id 由前端生成（`s<时间戳>`），服务端当**不透明名字**用 ——
   只做文件名安全校验，不解析它的含义。
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "data" / "prompt_sessions"

#: 会话 id 只认这些字符（前端生成的是 `s<毫秒>`），其余一律拒 —— 防路径穿越。
_SID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

#: 单个会话最大字节数。正常一份几 KB，超过这个量说明前端把图塞进来了。
MAX_BYTES = 800_000


class SessionError(ValueError):
    """给顾客看的错。"""


def _path(sid: str) -> Path:
    if not _SID.match(sid or ""):
        raise SessionError("对话编号不对")
    return ROOT / f"{sid}.json"


def save(sid: str, *, title: str = "", target: str = "", turns: int = 0,
         last_prompt: str = "", msgs=None) -> dict:
    """整份覆盖写（前端每次拿到新内容就整份推上来，不做增量合并）。"""
    p = _path(sid)
    row = {
        "id": sid,
        "title": (title or "").strip()[:60] or "未命名对话",
        "target": target or "",
        "turns": int(turns or 0),
        "last_prompt": last_prompt or "",
        "msgs": msgs or [],
        "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "updated_ts": time.time(),
    }
    blob = json.dumps(row, ensure_ascii=False)
    if len(blob.encode("utf-8")) > MAX_BYTES:
        raise SessionError("这个对话太大了，存不下（历史只存文字，不存截图）")
    ROOT.mkdir(parents=True, exist_ok=True)
    p.write_text(blob, encoding="utf-8")
    return {k: row[k] for k in ("id", "title", "target", "turns", "updated")}


def load(sid: str) -> dict | None:
    p = _path(sid)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def index() -> list[dict]:
    """列表页只要摘要，不带 msgs —— 免得一进页面就把几十份对话全拉下来。"""
    rows = []
    if not ROOT.is_dir():
        return rows
    for p in ROOT.glob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        rows.append({k: d.get(k) for k in ("id", "title", "target", "turns", "updated")}
                    | {"ts": d.get("updated_ts") or 0})
    rows.sort(key=lambda r: r.get("ts") or 0, reverse=True)
    return rows


def delete(sid: str) -> bool:
    p = _path(sid)
    if not p.is_file():
        return False
    p.unlink()
    return True


def append_turn(sid: str, *, user_text: str = "", ai: dict | None = None,
                target: str = "") -> dict | None:
    """把**一轮**追加进会话 —— 后端自己写，不依赖浏览器还开着。

    🩸 2026-10-30 主人：「我不在那个页面也会把之前的提问输出完整」。
    所以这轮的结果由**跑请求的那个线程**直接落盘：顾客点新对话、关页面、
    换台机器，回来「历史」里都是完整的。
    """
    try:
        row = load(sid) or {"id": sid, "title": "", "target": "", "turns": 0,
                            "last_prompt": "", "msgs": [],
                            "updated": "", "updated_ts": 0}
        msgs = list(row.get("msgs") or [])
        if user_text:
            # 前端每轮也会整份推一次，那一份里**已经含这一问** —— 尾条一样就别再加，
            # 否则顾客离开页面再回来会看到同一句话问了两遍。
            last = msgs[-1] if msgs else None
            dup = (isinstance(last, dict) and last.get("role") == "user"
                   and (last.get("text") or "").strip() == user_text.strip())
            if not dup:
                msgs.append({"role": "user", "text": user_text, "shots": 0,
                             "data": None, "error": ""})
                row["turns"] = int(row.get("turns") or 0) + 1
            if not row.get("title"):
                row["title"] = user_text.strip()[:60] or "未命名对话"
        if ai:
            msgs.append({"role": "ai", "text": "", "shots": 0,
                         "data": ai, "error": ai.get("error") or ""})
            if ai.get("prompt"):
                row["last_prompt"] = ai["prompt"]
            if not row.get("title"):
                row["title"] = "未命名对话"
        return save(sid, title=row.get("title") or "", target=target or row.get("target") or "",
                    turns=int(row.get("turns") or 0),
                    last_prompt=row.get("last_prompt") or "", msgs=msgs)
    except (SessionError, OSError, ValueError):
        # 记不下来不许把顾客那一次请求搞挂
        return None
