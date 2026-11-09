"""命名运镜库（22 条）+ 冲突判据 + 剧本侧词表块 —— 纯数据 / 纯函数。

出处：clipforge `src/lib/camera-presets.ts:1-370`（数据由
`scripts/import_clipforge_presets.py` 原样抽成 `app/data/camera_presets.json`）
+ `src/lib/motion-prompt.ts:297-311`（冲突判据三条正则，逐字抄）。

为什么要这个库：自由文本运镜是竞品自己承认的**头号质量瓶颈**
（`camera-presets.ts:4-7` 原话：`Shot.camera` 是 LLM 自由文本，全程只读）。
给每镜一条**已知不冲突、已知拍得出来**的运镜句子，比让模型现场编稳得多。
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data" / "camera_presets.json"

#: 冲突判据（`motion-prompt.ts:297-302`，逐字抄）
STATIC_CAMERA_RE = re.compile(r"固定|静止|锁定|不动|fixed|static|locked", re.I)
MOVING_CAMERA_RE = re.compile(
    r"环绕|环拍|推近|推进|拉远|拉近|横移|平移|摇镜|摇臂|甩镜|跟随|跟拍|升降|俯冲"
    r"|orbit|push[- ]?in|pull[- ]?back|dolly|pan|tilt|track|crane|zoom|whip", re.I)
SEQUENCE_RE = re.compile(
    r"先|后|然后|随后|接着|再|最后|结尾|开场|开头|then|after|before|finally|ending|start", re.I)

#: 剧本侧词表的分镜类型标签（`camera-presets.ts:333-340`，逐字抄）
GUIDE_INTENT_LABELS = [
    {"type": "hook", "label": "开场钩子", "framing": "极致特写~特写（等效85-135mm）", "mood": "急切抓人"},
    {"type": "pain_point", "label": "痛点共鸣", "framing": "近景~中景（等效35-50mm）", "mood": "代入困扰"},
    {"type": "product_reveal", "label": "商品展示", "framing": "特写~近景（等效85mm）", "mood": "惊喜聚焦"},
    {"type": "demo", "label": "使用演示", "framing": "中景切特写（等效50mm）", "mood": "专注可信"},
    {"type": "social_proof", "label": "氛围背书", "framing": "全景~中景（等效35mm）", "mood": "松弛日常"},
    {"type": "cta", "label": "收尾转化", "framing": "特写定住（等效85mm）", "mood": "笃定收束"},
]

#: 每类给几条例子（`camera-presets.ts:342`）
GUIDE_MAX_PER_TYPE = 3


@lru_cache(maxsize=1)
def _all() -> tuple[dict, ...]:
    return tuple(json.loads(DATA.read_text(encoding="utf-8")))


def all_presets() -> list[dict]:
    return list(_all())


def get(pid: str | None) -> dict | None:
    if not pid:
        return None
    for p in _all():
        if p.get("id") == pid:
            return p
    return None


def valid(pid: str | None) -> bool:
    return get(pid) is not None


def prompt_of(pid: str) -> str:
    """运镜句子（中文；我们全中文线，不跟竞品做中英切换）。"""
    p = get(pid)
    return str(((p or {}).get("prompt") or {}).get("zh") or "")


def recommended(shot_type: str) -> list[dict]:
    """这个分镜类型推荐哪些运镜（`goodFor` 命中，保持库内顺序）。"""
    return [p for p in _all() if shot_type in (p.get("goodFor") or [])]


def find_by_prompt(text: str | None) -> dict | None:
    """反查：这段 camera 文字是不是某个预设原句（界面判断「已应用预设」）。"""
    t = (text or "").strip()
    if not t:
        return None
    return next((p for p in _all()
                 if ((p.get("prompt") or {}).get("zh") == t
                     or (p.get("prompt") or {}).get("en") == t)), None)


def has_conflict(camera: str) -> bool:
    """「固定」+「在动」写在同一句、又没有「先…随后…」→ 判冲突（`motion-prompt.ts:310`）。"""
    return bool(STATIC_CAMERA_RE.search(camera or "")
                and MOVING_CAMERA_RE.search(camera or "")
                and not SEQUENCE_RE.search(camera or ""))


def mix(a_id: str, b_id: str) -> str | None:
    """两层叠加：`A，同时B`；撞冲突就返回 None（界面只列能叠的组合）。"""
    if not a_id or not b_id or a_id == b_id:
        return None
    a, b = prompt_of(a_id), prompt_of(b_id)
    if not a or not b:
        return None
    combined = f"{a}，同时{b}"
    return None if has_conflict(combined) else combined


def mixable(base_id: str) -> list[dict]:
    return [p for p in _all() if mix(base_id, p.get("id") or "")]


def guide() -> str:
    """给**剧本模型**的运镜词表块（`camera-presets.ts:358-370` 逐字）。"""
    lines = []
    for g in GUIDE_INTENT_LABELS:
        ex = " ｜ ".join(prompt_of(p["id"]) for p in recommended(g["type"])[:GUIDE_MAX_PER_TYPE])
        lines.append(f"  · {g['label']}（{g['framing']}，情绪{g['mood']}）：{ex}")
    return "\n".join([
        "中文镜头运动描述。优先从下列电商运镜词表中挑选最贴合分镜情绪的一条"
        "（可按画面微调用词），每镜保持单一明确的运动方向；不要把「固定镜头」与"
        "「环绕/推拉」写进同一句，除非用「先…随后…」表达先后顺序：",
        *lines,
    ])


def public() -> list[dict]:
    """给界面的列表（按分类分组，名称 + 句子 + 适用分镜类型）。"""
    return [{"id": p.get("id"),
             "name": (p.get("name") or {}).get("zh") or p.get("id"),
             "category": p.get("category"),
             "prompt": prompt_of(p.get("id") or ""),
             "good_for": p.get("goodFor") or []} for p in _all()]
