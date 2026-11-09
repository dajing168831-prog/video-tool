"""商品短剧 · 视觉记忆六锚 + 生成前一致性硬闸。

结构来源：开源项目 **clipforge**（AGPL-3.0）`src/lib/production-system.ts:58-129`
的 `VisualBible` / `sanitizeVisualBible` / `checkPromptConsistency`，
**只抽做法、不复制代码**。六锚 = 人物 / 商品 / 服装 / 环境 / 光线 / 禁改。

判据原样保留（`:119-128`）：

  · 人物 + 商品 + 服装 = **必须出现**的锚，缺了 → `warn`（提示，不拦）；
  · `forbidden_changes` 里的词**出现在提示词里** → `fail`（**不发付费请求**）。
    这是硬闸：钱只花在确认过的那版提示词上。

我们怎么落地（和竞品的差别，都写在这里别猜）：

  · 竞品靠人在「项目记忆」里手填六锚；我们**能从已有产物抽的就抽**
    （人物 appearance、场景 location、商品名），抽出来的是**原文逐字**，
    不新写一句外观描述 —— 抽不到的第 4/5/6 项留空，等使用者自己填。
  · 只有前 3 项参与「必须出现」判定（和竞品一致）；环境/光线只作展示。
"""
from __future__ import annotations

import re

#: 六锚字段名（顺序 = 界面展示顺序）
FIELDS = (
    "character_anchors",
    "product_anchors",
    "wardrobe_anchors",
    "environment_anchors",
    "lighting_anchors",
    "forbidden_changes",
)

#: 参与「必须出现」判定的三项（clipforge `:121`）
REQUIRED = ("character_anchors", "product_anchors", "wardrobe_anchors")

#: 每条锚最长 / 最多几条（clipforge `cleanList` 的 120 / 12）
MAX_LEN = 120
MAX_ITEMS = 12


def empty() -> dict:
    return {k: [] for k in FIELDS}


def _clean_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        s = item.strip()[:MAX_LEN]
        if s and s not in out:
            out.append(s)
        if len(out) >= MAX_ITEMS:
            break
    return out


def sanitize(value) -> dict:
    """把前端/存档里的六个列表洗成可用形态 —— 只留字符串、去重、截断。"""
    raw = value if isinstance(value, dict) else {}
    return {k: _clean_list(raw.get(k)) for k in FIELDS}


def _atoms(text: str) -> list[str]:
    """把一句外观拆成**原子锚**（发型 / 年龄段 / 服装 / 随身细节）。

    🩸 为什么不能拿整句做子串匹配：九宫格提示词是模型按分镜重写的，
    真项目里出现的是「45岁寸头鬓角发白的老李穿深蓝polo衫」，和剧本里
    「寸头鬓角发白，45岁，深蓝polo衫」**词序和标点都不一样** ——
    整句查必然假红。拆成原子后，缺的是「深蓝polo衫」这种真正能判的点。
    """
    parts = []
    for piece in re.split(r"[，,、；;]", text or ""):
        s = piece.strip()
        if len(s) >= 2:  # 单个字（「男」「女」）没有鉴别力
            parts.append(s)
    return parts


def _product_atoms(name: str) -> list[str]:
    """把商品名拆成能判的原子：品牌 / 英文代号 / 品名 / 规格。

    🩸 2026-11-09 主人实测：商品名「[同仁堂（TRT）] 同仁乌鸡白凤丸 9g*10丸 1盒装」
    拿整串做子串匹配，模型写分镜时不会逐字复述这么长 —— 每段都报「缺锚」，是假红。
    拆开后只要**任意一个原子**出现在提示词里，就算这段提到了这件商品。
    """
    s = str(name or "").strip()
    if not s:
        return []
    parts = [p.strip() for p in re.split(r"[\s\[\]【】（）()、，,；;/|]+", s)]
    atoms = [p for p in parts if len(p) >= 2]   # 单字没有鉴别力
    return atoms or [s]


def derive(doc: dict) -> dict:
    """从**已有产物**抽锚，一律原文逐字，不新写描述。

    人物锚 = `characters[].appearance` 拆成原子（发型/年龄/服装/随身细节）
    商品锚 = 商品名（只作为「这段提示词要提到这件商品」的检查点）
    环境锚 = `scenes[].location`
    服装锚、光线锚、禁改 = 抽不到，留空（等使用者自己填）
    """
    script = doc.get("script_json") or {}
    chars = [c for c in (script.get("characters") or []) if isinstance(c, dict)]
    scenes = [s for s in (script.get("scenes") or []) if isinstance(s, dict)]
    prod = doc.get("product") or {}
    char_atoms: list[str] = []
    for c in chars:
        char_atoms.extend(_atoms(str(c.get("appearance") or "")))
    return sanitize({
        "character_anchors": char_atoms,
        "product_anchors": [str(prod.get("name") or "")],
        "wardrobe_anchors": [str(c.get("wardrobe") or "") for c in chars],
        "environment_anchors": [str(s.get("location") or "") for s in scenes],
        "lighting_anchors": [],
        "forbidden_changes": [],
    })


def effective(doc: dict) -> dict:
    """项目里存过就用存的（人改过的才算数），没存过就现抽。"""
    stored = doc.get("visual_bible")
    if isinstance(stored, dict) and any(stored.get(k) for k in FIELDS):
        return sanitize(stored)
    return derive(doc)


def check(prompt: str, bible: dict) -> list[dict]:
    """单条提示词过闸。返回 `[{kind, anchor, severity, field}]`。

    大小写不敏感（竞品也是 `toLowerCase()` 后做子串）——中文不受影响，
    英文锚点「Blue Box」和「blue box」不该算两种。
    """
    hay = (prompt or "").lower()
    issues: list[dict] = []
    for field in REQUIRED:
        for anchor in bible.get(field) or []:
            #: 🩸 商品锚：整串太长，模型不会逐字复述 —— 拆成原子，任一出现就算提到（见 `_product_atoms`）
            if field == "product_anchors":
                atoms = _product_atoms(anchor)
                #: 空锚点（商品名没填）不报 —— 空集恒假会把「没商品名」变成「缺锚」刷屏
                if atoms and not any(a.lower() in hay for a in atoms):
                    issues.append({"kind": "missing-anchor", "anchor": anchor,
                                   "severity": "warn", "field": field})
                continue
            if anchor.lower() not in hay:
                issues.append({"kind": "missing-anchor", "anchor": anchor,
                               "severity": "warn", "field": field})
    for anchor in bible.get("forbidden_changes") or []:
        if anchor and anchor.lower() in hay:
            issues.append({"kind": "forbidden-change", "anchor": anchor,
                           "severity": "fail", "field": "forbidden_changes"})
    return issues


def issues_for(prompts: list[str], bible: dict) -> list[dict]:
    """多条提示词一起过闸，同一问题只报一次（界面上不刷屏）。"""
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for p in prompts or []:
        for issue in check(p, bible):
            key = (issue["kind"], issue["anchor"])
            if key in seen:
                continue
            seen.add(key)
            out.append(issue)
    # fail 排前面：界面先看到真正会拦人的那条
    out.sort(key=lambda i: 0 if i["severity"] == "fail" else 1)
    return out


def blocking(prompts: list[str], bible: dict) -> dict | None:
    """第一条会拦付费请求的问题；没有就返回 None。"""
    for issue in issues_for(prompts, bible):
        if issue["severity"] == "fail":
            return issue
    return None


def block_message(issue: dict) -> str:
    return (f"视觉记忆禁止「{issue['anchor']}」出现/变化 —— "
            "先改提示词或改视觉锚点；本次没有提交、没有扣费")
