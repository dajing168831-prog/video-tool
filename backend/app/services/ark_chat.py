# -*- coding: utf-8 -*-
"""方舟**对话**入口（`chat/completions`）：型号白名单 + 一次调用。

⛔ 这里只有传输和型号名，**没有任何一家的提示词规则**。规则在各家的
`*_official` / `models/` 里，别往这儿塞。

⛔ 也不是生图/生视频那个客户端 —— 那个在 `ark.py`（`generate_image` / `edit_video` …）。
两个文件名字像、干的事完全不同：一个调对话模型，一个调生成模型。

🩸 为什么单独立一个文件（2026-10-30）：同一份白名单原来抄了**三份**
（`h3_direct` / `sd20_direct` / `prompt.py`），翻译成端点名的动作写在各自内部；
`h3_skill` 那一份漏了翻 → 真机
`404 InvalidEndpointOrModel.NotFound: The model or endpoint pro does not exist`。
**抄一份就埋一个 404**，所以三条路现在都从这里取。
"""
from __future__ import annotations

import httpx

CHAT_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"

#: 白名单键 → 方舟真实端点名。
#: 🩸 前端只许传**键**（直通端点名等于把计费口子开给浏览器）；
#: 发出去之前一律经 `resolve()` 翻。
MODELS = {
    "lite": "doubao-seed-2-1-lite-260915",
    "pro": "doubao-seed-2-1-pro-260915",
    "deepseek": "deepseek-v4-1-flash-261017",
}

#: 没指定型号时的默认值。**生成/修订/对话三条路共用这一个** ——
#: 原来 `prompt.py` 写 `lite`、`h3_direct` 写 `pro`，健康检查报的和实际用的不是一个。
DEFAULT_MODEL = "pro"


class ArkError(ValueError):
    """方舟调用失败。消息直接给顾客看，写人话。"""


def resolve(model: str) -> str:
    """白名单键 → 端点名。空串和不认识的键一律落到默认端点（不报错，别让顾客看见型号名）。"""
    return MODELS.get(model or "") or MODELS[DEFAULT_MODEL]


def post(body: dict, *, key: str, timeout: float = 300.0) -> dict:
    """一次 `chat/completions`，返回解析后的 JSON。

    失败分两种，都抛 `ArkError`：HTTP >=400、响应不是 JSON。
    各条路拿到后自己包成本家的错误类型（顾客看到的文案不一样）。
    """
    with httpx.Client(timeout=timeout) as c:
        r = c.post(CHAT_URL, json=body, headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"})
    if r.status_code >= 400:
        raise ArkError(f"生成接口 {r.status_code}：{r.text[:200]}")
    try:
        return r.json()
    except Exception as e:                                  # noqa: BLE001
        raise ArkError(f"生成响应结构异常：{e}") from e
