"""读音校正（Dual Text）—— 显示用一套字，念出来用另一套。

出处：hypit `creation/script-and-time.md`「Write the intended pronunciation」。
识别原文要保留原样（品牌名、缩写就该显示成 `XHS` / `¥19.9`），但配音得知道
它该念成「小红书」还是「X-H-S」、价格是「十九块九」还是「十九点九元」。
**这件事模型猜不出来，只能由使用者指定。**

只做映射，不 invent：
  - `detect()` 只负责把文案里"可能需要校正"的词挑出来给界面列；
  - 念法一律由人填。没填的词原样交给 TTS（豆包读中文数字本来就不差）。
"""
from __future__ import annotations

import re

# 可以被当作"需要校正"的候选：英文词/缩写、带币种的数字
_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9&.\-']*|[¥￥$]\s?\d[\d.,]*")

MAX_ENTRIES = 50
MAX_LEN = 32


def detect(text: str) -> list[str]:
    """挑出文案里可能需要指定念法的词，按出现顺序去重。"""
    seen: list[str] = []
    for m in _TOKEN.findall(text or ""):
        t = m.strip()
        if t and t not in seen:
            seen.append(t)
    return seen


def clean(mapping) -> dict[str, str]:
    """收掉空值/超长/非法条目，返回一份干净的映射。

    键或值不是字符串的一律丢弃 —— 前端传 `{a: null}` 这类东西进来时
    不能让它在流水线里变成 "None" 念出来。
    """
    if not isinstance(mapping, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in mapping.items():
        if not isinstance(k, str) or not isinstance(v, str):
            continue
        k, v = k.strip(), v.strip()
        if not k or not v or k == v:
            continue
        if len(k) > MAX_LEN or len(v) > MAX_LEN:
            continue
        out[k] = v
        if len(out) >= MAX_ENTRIES:
            break
    return out


def apply(text: str, mapping) -> str:
    """把念法替换进要合成的那一份文本（识别原文不动）。

    长键优先，避免 `API` 先被 `AP` 截胡；单遍替换，替换出来的字不会二次命中。
    """
    text = text or ""
    m = clean(mapping)
    if not m or not text:
        return text
    keys = sorted(m, key=len, reverse=True)
    pat = re.compile("|".join(re.escape(k) for k in keys))
    return pat.sub(lambda mo: m[mo.group(0)], text)


def display_vs_spoken(text: str, mapping) -> tuple[str, str]:
    """返回 (显示的，念的)。前端预览用。"""
    text = text or ""
    return text, apply(text, mapping)
