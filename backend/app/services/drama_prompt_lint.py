"""商品短剧 · 静态关键帧提示词卫生 lint（F7）。

逐字对照竞品 `src/lib/prompt-lint.ts:1-69`：

- `TEMPORAL_PATTERNS` / `keyframeStaticWarnings`（`:18-47`）—— 一帧静止画面里
  写出「先…然后…／逐渐／下一秒」这类**先后顺序**，图模型只能画出几个瞬间的糊在一起的
  中间态（手带拖影、双动作、脸在变形）。所以在**花钱出图之前**先把这些词标出来。
- `KEYFRAME_INSTANT_RULE` / `keyframeInstantLine`（`:50-69`）—— 关键帧统一追加一句
  「动作即将开始前一瞬的定格」，让图生视频那一遍还有动作可演，而不是从已经做完的姿势起手。
  按周围提示词的语言选中/英文（判据 = 有没有 CJK 字符）。

两条都是**只提示不拦**（竞品文件头 `:9-11`：warning-only by design）。
"""
from __future__ import annotations

import re

#: 出处 `prompt-lint.ts:18-29`，顺序与标签逐条照抄。
#: 刻意保守：单一瞬间的写法（「mid-pour」「动作定格」）不许命中 ——
#: 每条命中的都必须点了两个瞬间之间的先后。
TEMPORAL_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"先[是]?[^，。；]{0,12}(然后|再|接着|随后)"), "先…然后…"),
    (re.compile(r"然后|接着|随后|紧接着"), "然后/接着/随后"),
    (re.compile(r"逐渐|渐渐|慢慢地|缓缓地"), "逐渐/渐渐"),
    (re.compile(r"之后|片刻后|下一秒"), "之后/下一秒"),
    (re.compile(r"开始[^，。；]{0,6}(涂|抹|倒|拆|擦|喝|吃|走|说)"), "开始做某事"),
    (re.compile(r"\bthen\b", re.I), "then"),
    (re.compile(r"\b(starts?|begins?|beginning) to\b", re.I), "starts to"),
    (re.compile(r"\bgradually\b", re.I), "gradually"),
    (re.compile(r"\bafter (that|which)\b", re.I), "after that"),
    (re.compile(r"\bfollowed by\b", re.I), "followed by"),
)

#: 出处 `prompt-lint.ts:50-53`。
KEYFRAME_INSTANT_RULE = {
    "zh": "画面是动作即将开始前一瞬的定格：姿态里留着正要发生的势能，动作本身尚未完成",
    "en": "freeze the instant just before the action begins: the pose holds the potential energy "
          "of what is about to happen, the action itself not yet done",
}

#: 出处 `prompt-lint.ts:57-59`（CJK 判定，含假名/谚文，和竞品同一个区间）。
_CJK_RE = re.compile(r"[一-鿿぀-ヿ가-힯]")


def has_cjk(s: str) -> bool:
    return bool(_CJK_RE.search(s or ""))


def keyframe_static_warnings(prompt: str | None) -> list[str]:
    """扫一段**静止关键帧**提示词里表示先后顺序的词，返回命中的标签（去重、按提示词顺序）。"""
    text = (prompt or "").strip()
    if not text:
        return []
    hits: list[str] = []
    for pat, label in TEMPORAL_PATTERNS:
        if pat.search(text) and label not in hits:
            hits.append(label)
    return hits


def keyframe_instant_line(sample_text: str) -> str:
    """按提示词语言给「动作前一瞬」指令句；空文本按中文（竞品 `:67` 同）。"""
    return KEYFRAME_INSTANT_RULE["zh"] if (not sample_text or has_cjk(sample_text)) \
        else KEYFRAME_INSTANT_RULE["en"]
