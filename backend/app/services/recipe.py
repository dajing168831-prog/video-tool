"""结构配方（Recipe）—— 复刻功能的唯一自研件。

一条参考片读完之后，我们保留的不是"画面"，是"结构"：
  - 什么时候说了什么（逐字时间轴）
  - 什么时候切了镜（节奏）
  - 开头三秒靠什么抓人（钩子）

有了逐字时间轴，改一句台词时配音能按新字的时长重新分配 —— 这就是
"改文案、配音自动重排"的机制本身，不是后期拼出来的效果。
🩸 2026-10-23 主人拍板「也不烧字幕」：配方里不再有字幕样式（caption_style）。

schema 一旦发布就只增不改字段；version 用来兼容老配方。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SCHEMA_VERSION = 1

# 🩸 2026-10-23 主人拍板「也不烧字幕」：`DEFAULT_CAPTION_STYLE` 随字幕功能一起删除。


@dataclass
class Char:
    """一个字（中文按字，英文按词）及其时间。"""

    c: str
    s: float
    e: float


def _round(v: float, n: int = 3) -> float:
    return round(float(v), n)


def build_recipe(
    *,
    url: str = "",
    probe: dict,
    shots: list[Any],
    speech: dict | None = None,
    ocr: dict[int, list[str]] | None = None,
) -> dict:
    """把证据拼成配方。

    shots: scene.Shot 列表
    speech: {"has": bool, "lang": str, "segments": [{start,end,text,chars:[...]}]}
    ocr: 可选，镜头序号 -> 画面上的文字
    """
    ocr = ocr or {}
    speech = speech or {"has": False, "lang": "zh", "segments": []}

    shot_items = [
        {
            "i": s.index,
            "start": _round(s.start),
            "end": _round(s.end),
            "dur": _round(s.end - s.start),
            "keyframe": getattr(s, "keyframe", "") or "",   # 抽帧后由上层回填
            # 运动量：逐镜分诊用（低＝静态，可以只靠一张静帧重画）
            "motion": _round(getattr(s, "motion", 0.0) or 0.0, 2),
            "ocr": ocr.get(s.index, []),
        }
        for s in shots
    ]

    beats = [{"at": _round(s.start), "type": "cut"} for s in shots if s.index > 0]

    total = float(probe.get("duration") or 0)
    cuts_per_10s = _round(len(beats) / (total / 10), 2) if total > 0 else 0.0
    avg_shot = _round(total / max(1, len(shots)))

    return {
        "version": SCHEMA_VERSION,
        "source": {
            "url": url,
            "duration": _round(total),
            "width": int(probe.get("width") or 0),
            "height": int(probe.get("height") or 0),
            "fps": float(probe.get("fps") or 0),
            "has_audio": bool(probe.get("has_audio")),
        },
        "speech": speech,
        "shots": shot_items,
        "beats": beats,
        "rhythm": {"cuts_per_10s": cuts_per_10s, "avg_shot": avg_shot},
        "hook": _find_hook(speech, total),
    }


def _find_hook(speech: dict, total: float) -> dict:
    """开头 3 秒说了什么 —— 爆款的钩子几乎都在这里。"""
    segs = speech.get("segments") or []
    for seg in segs:
        if float(seg.get("start", 0)) < 3.0 and (seg.get("text") or "").strip():
            return {
                "at": _round(seg.get("start", 0)),
                "duration": _round(min(3.0, float(seg.get("end", 3.0)))),
                "text": seg["text"].strip(),
                "why": "",
            }
    return {"at": 0.0, "duration": _round(min(3.0, total)), "text": "", "why": ""}


def summary(recipe: dict) -> dict:
    """给前端"原片诊断卡"用的摘要（不把整份配方发给客户端）。"""
    speech = recipe.get("speech") or {}
    segs = speech.get("segments") or []
    chars = sum(len(s.get("chars") or []) for s in segs)
    return {
        "duration": recipe["source"]["duration"],
        "width": recipe["source"]["width"],
        "height": recipe["source"]["height"],
        "ratio": _ratio(recipe["source"]["width"], recipe["source"]["height"]),
        "has_speech": bool(speech.get("has")),
        "lang": speech.get("lang", "zh"),
        "segment_count": len(segs),
        "char_count": chars,
        "shot_count": len(recipe.get("shots") or []),
        "rhythm": recipe.get("rhythm", {}),
        "hook": recipe.get("hook", {}),
    }


def _ratio(w: int, h: int) -> str:
    if not w or not h:
        return ""
    for label, (rw, rh) in {
        "9:16": (9, 16), "16:9": (16, 9), "3:4": (3, 4), "1:1": (1, 1), "4:3": (4, 3),
    }.items():
        if abs(w / h - rw / rh) < 0.03:
            return label
    return f"{w}:{h}"


def segments_for_caption(recipe: dict) -> list[dict]:
    """取逐句文案段；没有语音时按镜头生成空段（供渲染占位验证）。"""
    segs = (recipe.get("speech") or {}).get("segments") or []
    if segs:
        return segs
    return [
        {"start": s["start"], "end": s["end"], "text": "", "chars": []}
        for s in recipe.get("shots") or []
    ]
