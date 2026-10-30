# -*- coding: utf-8 -*-
"""把**每一轮对话**落盘 —— 不然出了事只能靠截图回忆。

🩸 2026-10-30：主人跑完一轮，我这边什么都看不到。agent 这条路的 `trace` / `reads` /
`calls` / `tokens` 全在 HTTP 响应里，页面一刷新就没了，日志也只打在调试控制台。
结果"它到底读了哪几份 skill、问了几轮"只能靠**推理**。
**有落盘 = 证据；没落盘 = 猜。** 和 10-26 那次"钱花了、任务号取不回来"是同一类坑。

⛔ 只写文件，不做任何判断，也不影响交付：写失败只记一条 warning，
   绝不能因为记日志把顾客那一次请求搞挂。
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

log = logging.getLogger(__name__)

#: 跑完的记录放这儿（`backend/data/tmp` 已被 `.gitignore` 排除，不进仓库）。
RUNS = Path(__file__).resolve().parents[2] / "data" / "tmp" / "prompt_runs"

#: 单条消息最多记多少字（防止一次贴几万字把文件撑爆）。
_MAX_MSG = 4000


def _msgs(messages) -> list[dict]:
    out = []
    for m in messages or []:
        m = m or {}
        c = m.get("content")
        if not isinstance(c, str):
            c = json.dumps(c, ensure_ascii=False)[: _MAX_MSG]
        out.append({"role": m.get("role"), "content": c[:_MAX_MSG]})
    return out


def write(target: str, *, model: str, result, messages=None,
          fixed=None) -> Path | None:
    """写一份 `<时间>_<目标>_<毫秒>.json`。失败返回 None，不抛。

    `result` 是 `skill_agent.AgentResult`（属性访问，接口失败也不影响这里）。
    """
    try:
        RUNS.mkdir(parents=True, exist_ok=True)
        now = time.time()
        p = RUNS / (time.strftime("%Y%m%d-%H%M%S", time.localtime(now))
                    + f"_{target}_{int(now * 1000) % 1000:03d}.json")
        rec = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
            "target": target,
            "model": model,
            "action": result.action,
            "steps": result.steps,
            "calls": result.calls,
            "tokens": result.tokens,
            "truncated": result.truncated,
            "reads": list(result.reads or []),
            "trace": list(result.trace or []),
            "question": result.question,
            "note": result.note,
            "red": [list(r) for r in (result.red or [])],
            "prompt": result.prompt,
            "fixed": list(fixed or []),
            "messages": _msgs(messages),
        }
        p.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        return p
    except Exception as e:                                  # noqa: BLE001
        log.warning("这一轮的记录没写下来（不影响交付）：%s", e)
        return None
