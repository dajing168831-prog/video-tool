# -*- coding: utf-8 -*-
"""DeepSeek **官方**对话入口（`api.deepseek.com`，OpenAI 兼容）。

⛔ 和 `ark_chat.py` 平级、互不 import，区别只有一处**花谁的钱**：
  · `ark_chat`   → 火山方舟托管的 `deepseek-v4-1-flash-261017`，走 `VT_ARK_API_KEY`
  · 本文件        → DeepSeek 官方 `deepseek-flash`，走 `VT_DEEPSEEK_API_KEY`

🩸 2026-11-01 主人：「要调 deepseek 官方的，不要火山的」。
   两条路都留着是因为**提示词优化那条线仍走火山**（它另有一套型号白名单），
   复刻的 agent 单独切过来。别把两家合成一个函数 —— 端点、key、计费全不同。

⛔ 没有 key 时由调用方报错，这里不做"回落火山"：
   回落了用户以为切了、实际没切，账单和效果都对不上。
"""
from __future__ import annotations

import httpx

from app.core.config import settings


class DeepSeekError(ValueError):
    """官方调用失败。消息直接给顾客看，写人话。"""


def endpoint() -> str:
    """`https://api.deepseek.com` → `.../chat/completions`（base 末尾带不带 / 都认）。"""
    base = (settings.deepseek_base or "https://api.deepseek.com").strip().rstrip("/")
    return f"{base}/chat/completions"


def configured() -> bool:
    return bool((settings.deepseek_api_key or "").strip())


def post(body: dict, *, key: str, timeout: float = 300.0) -> dict:
    """一次 `chat/completions`，返回解析后的 JSON。

    失败分两种，都抛 `DeepSeekError`：HTTP >= 400、响应不是 JSON。
    """
    with httpx.Client(timeout=timeout) as c:
        r = c.post(endpoint(), json=body, headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"})
    if r.status_code >= 400:
        raise DeepSeekError(f"DeepSeek 官方接口 {r.status_code}：{r.text[:200]}")
    try:
        return r.json()
    except Exception as e:                                  # noqa: BLE001
        raise DeepSeekError(f"DeepSeek 官方响应结构异常：{e}") from e
