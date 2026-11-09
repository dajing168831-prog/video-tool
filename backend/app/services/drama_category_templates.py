"""品类脚本模板 —— 按商品品类给剧本模型一套「这个品类怎么讲故事」的硬要求 + 参考案例。

出处（竞品逐行对照）：
  · 数据：`src/lib/script-engine/templates/{beauty,food,home,fashion,tech}.ts`
    —— 22 条模板（每条 name/description/suitableFor/shotStructure/example）+ 5 条品类指令。
    由 `temp/_extract_category_templates.py` 原样抽成 `app/data/category_templates.json`，
    **不是重打一遍**（和 `ad_templates.json` 同一口径）。
  · 选类目：`templates/index.ts:23-29` 的 `categoryNameMap`；
  · 注入位置：`script-engine/prompts.ts:821-822`（品类指令）、`838-843`（参考案例，
    固定取 `templates[0]` = `:755`）、`OUTPUT_FORMAT_PROMPT` 之前。
  · 只注入**剧本**阶段 —— `prompts.ts` 里分镜提示词不调 `getTemplatesByCategory`。

和其他三套模板的区别（别合并）：
  · 成片模板 `drama_templates.py`   = 391 条**画面配方**（运镜/光线/合成）
  · 剧本模板 `drama_script_templates.py` = **你自己**存下来的镜头节奏
  · 品类模板（本文件）            = 竞品内置的**品类叙事套路 + 品类创作指令**
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from app.services.drama_templates import CATEGORY_MAP

FILE = Path(__file__).resolve().parents[1] / "data" / "category_templates.json"

#: 竞品的类目 id 和模板库（`ad_templates`）只差一个：数码 那边叫 digital、这边叫 tech
_KEY_FIX = {"digital": "tech"}

_LOCK = threading.Lock()
_CACHE: dict | None = None


def _load() -> dict:
    global _CACHE
    with _LOCK:
        if _CACHE is None:
            try:
                _CACHE = json.loads(FILE.read_text(encoding="utf-8"))
            except Exception:
                _CACHE = {"categories": {}}
        return _CACHE


def resolve(zh: str | None) -> str:
    """建项表单的中文类目 → 本文件的类目 key；认不出（含「其他」）返回空串。

    换算只走 `drama_templates.CATEGORY_MAP`（那边写明「唯一换算处」），这里只补
    digital→tech 的差名。竞品对未知类目是**回落 beauty**（`index.ts:41` 注释说是
    "to avoid crashes"，防崩溃用的，不是产品意图）—— 我们不照抄：给「其他」的
    商品塞美妆指令只会把剧本带偏，所以认不出就**不注入**。
    """
    key = CATEGORY_MAP.get((zh or "").strip(), "")
    return _KEY_FIX.get(key, key)


def get(zh: str | None) -> dict | None:
    key = resolve(zh)
    if not key:
        return None
    item = (_load().get("categories") or {}).get(key)
    return item if isinstance(item, dict) and item.get("templates") else None


def list_categories() -> list[dict]:
    """给前端选项用：每个类目有什么模板可挑。"""
    out = []
    for key, item in (_load().get("categories") or {}).items():
        out.append({
            "id": key,
            "name": item.get("name") or key,
            "templates": [t.get("name") for t in item.get("templates") or []],
        })
    return out


def find(zh: str | None, name: str | None) -> dict | None:
    """按名字挑模板（前端传上来的），挑不到 → None（调用方回落到第一条）。"""
    item = get(zh)
    if not item or not (name or "").strip():
        return None
    want = name.strip()
    for t in item["templates"]:
        if t.get("name") == want:
            return t
    return None


def default_template(zh: str | None) -> dict | None:
    """竞品固定取第一条（`prompts.ts:755`）；用户没挑时照此默认。"""
    item = get(zh)
    return item["templates"][0] if item else None


def reference_block(tpl: dict | None) -> str:
    """参考案例块 —— 标题与「不要照搬」那句照 `prompts.ts:841-843`。"""
    if not tpl:
        return ""
    return (
        "【参考脚本案例（仅供参考风格和节奏，不要照搬内容）】\n"
        f"模板名称：{tpl.get('name')}\n"
        f"参考示例：\n{tpl.get('example')}"
    )


def script_block(zh: str | None, template_name: str | None = None) -> str:
    """剧本阶段的品类块 = 品类指令 + 参考案例；认不出类目返回空串（不注入）。

    🩸 2026-11-09 主人：「世界候选那样，把剧本这套模板也撤干净」。
    以前顾客没点名模板时**回落到该类目第一条参考案例** —— 每条片都照着同一份案例写，
    这是剧本雷同的来源之一。现在只有顾客明确选了模板才注入，没选就什么都不加。
    """
    item = get(zh)
    if not item:
        return ""
    tpl = find(zh, template_name) if template_name else None
    if not tpl:
        return ""
    parts = [(item.get("directive") or "").strip(), reference_block(tpl)]
    return "\n\n".join(p for p in parts if p)
