"""F8 结构指纹 —— 跨项目「是不是同一个模板」自检（纯函数，不调模型、不联网）。

出处：clipforge `src/lib/structure-fingerprint.ts:1-114`（逐条照抄）+ `api/insights/homogeneity/route.ts`：
  · `:51-63` 指纹 = 风格 / 开场机制 / 镜数 / 平均镜长 / 总时长；
  · `:73-82` 相似度加权：风格 0.35 · 开场 0.25 · 镜数 0.15（差 1 镜给 0.08）·
    平均镜长 0.15（相对差 ≤15%）· 总时长 0.10（相对差 ≤10%）；
  · `:48` 阈值 0.75；`:97` 判定 >0.5 risk、>0.25 warn，否则 ok；
  · `:85-96` 两两比较，`similarShare` = 越线对数 / 全部对数。

字段映射（我们这边没有竞品那套 `scripts` 表，逐个找到对应物）：
  · styleType ← 项目选中的成片配方 `doc["template"]["template"]["styleType"]`，
                没选配方时退 `doc["answers"]["form"]`（体裁）。两者都是现有真实字段
  · hookType  ← `doc["card_json"]["hook"]["type"]`（H1–H5，结构卡里就有）
  · shots     ← `doc["storyboard_json"]["shots"]`，时长取 `duration`
  · 只统计**有分镜**的项目（竞品同理：只算有脚本行的项目）

自己加的（非照抄）：判定文案是我们自己的措辞，竞品那份是「zh/en 双语对象」，
  我们只有中文界面，返一个字符串即可。
"""
from __future__ import annotations

import math

SIMILARITY_THRESHOLD = 0.75


def _round2(v: float) -> float:
    """对齐 JS `Math.round(x*100)/100`。"""
    return math.floor(v * 100 + 0.5) / 100


def _num(v) -> float:
    if isinstance(v, bool):
        return 0.0
    if isinstance(v, (int, float)) and math.isfinite(float(v)):
        return float(v)
    return 0.0


def fingerprint_of(doc: dict) -> dict:
    """把项目压成结构骨架（`structure-fingerprint.ts:51-63`）。"""
    doc = doc or {}
    shots = [s for s in (((doc.get("storyboard_json") or {}).get("shots")) or [])
             if isinstance(s, dict)]
    total = sum(_num(s.get("duration")) for s in shots)

    tpl = (doc.get("template") or {}).get("template") or {}
    style = str(tpl.get("styleType") or "").strip() \
        or str((doc.get("answers") or {}).get("form") or "").strip()
    hook = ((doc.get("card_json") or {}).get("hook")) or {}
    hook_type = str(hook.get("type") or "").strip()

    return {
        "project_id": str(doc.get("id") or ""),
        "project_name": str(doc.get("name") or ""),
        "style_type": style,
        "hook_type": hook_type,
        "shot_count": len(shots),
        "avg_shot_sec": (total / len(shots)) if shots else 0.0,
        "total_sec": total,
    }


def _near(a: float, b: float, ratio: float) -> bool:
    return a > 0 and b > 0 and abs(a - b) / max(a, b) <= ratio


def pair_similarity(a: dict, b: dict) -> float:
    """加权结构相似度（`structure-fingerprint.ts:73-82`，权重逐字照抄）。"""
    score = 0.0
    if a.get("style_type") and b.get("style_type") \
            and a["style_type"] == b["style_type"]:
        score += 0.35
    if a.get("hook_type") and b.get("hook_type") and a["hook_type"] == b["hook_type"]:
        score += 0.25
    ca, cb = int(a.get("shot_count") or 0), int(b.get("shot_count") or 0)
    if ca > 0 and ca == cb:
        score += 0.15
    elif abs(ca - cb) == 1:
        score += 0.08
    if _near(_num(a.get("avg_shot_sec")), _num(b.get("avg_shot_sec")), 0.15):
        score += 0.15
    if _near(_num(a.get("total_sec")), _num(b.get("total_sec")), 0.1):
        score += 0.1
    return _round2(score)


def homogeneity_report(items: list[dict]) -> dict:
    """两两比对 → 判定（`structure-fingerprint.ts:85-114`）。"""
    items = [i for i in items if isinstance(i, dict)]
    pairs: list[dict] = []
    total_pairs = 0
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            total_pairs += 1
            score = pair_similarity(items[i], items[j])
            if score >= SIMILARITY_THRESHOLD:
                pairs.append({"a": items[i], "b": items[j], "score": score})
    pairs.sort(key=lambda p: p["score"], reverse=True)

    share = (len(pairs) / total_pairs) if total_pairs else 0.0
    verdict = "risk" if share > 0.5 else "warn" if share > 0.25 else "ok"
    n = len(items)
    if verdict == "risk":
        msg = (f"最近 {n} 条里超过一半的配对结构高度相似——平台容易判成模板化批量产出，"
               f"下一批换开场钩子、镜数或节奏再发")
    elif verdict == "warn":
        msg = f"最近 {n} 条里有 {len(pairs)} 对结构相近，建议下一批换开场钩子或节奏"
    else:
        msg = f"最近 {n} 条的结构差异是健康的"

    return {
        "total": n,
        "similar_pairs": pairs,
        "similar_share": _round2(share),
        "verdict": verdict,
        "message": msg,
    }
