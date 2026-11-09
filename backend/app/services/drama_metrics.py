"""G4/G5 发布成效 —— 指标回填 + 风格/钩子成效聚合 + 反哺提示（纯函数 + 原子落盘）。

出处（逐条对照，不自己加指标）：
  · 聚合  clipforge `src/lib/performance-insights.ts:1-171`
          - `aggregateBy`：按 key 分组，`samples` / `avgViews` / `engagementRate`
            （赞+评+转）/ 播放 / `conversionRate`（成交/播放）/ `totalOrders`；
          - 排序：转化率降序，同分按样本数降序；
          - `topConvertingStyle/Hook`：样本数 ≥2 **且** 转化率 >0，否则 null（冷启动不硬报）；
          - `buildPerformanceHint`：把「最能卖的风格/钩子」写成一段中文指令，样本不足返回空串。
  · 路由  `src/app/api/project/[id]/metrics/route.ts`（GET 倒序 / POST 录入）
          `src/app/api/insights/styles/route.ts`（全站聚合）
  · 反哺  `src/app/api/llm/script/route.ts:93-124`
          —— 同品类优先，样本不够回落全局；读失败只跳过提示，**不阻断生成**。

我们的字段映射：
  · style      ← 项目选中的成片配方 `doc["template"]["template"]["styleType"]`
                （竞品取 scripts 表最新一版的 `styleType`；我们同一概念在配方里）；
                两边都没有 → `"custom"`（竞品同款兜底）
  · category   ← `doc["product"]["category"]`（竞品取 projects.productCategory）
  · hookId     只在录入时由人传（竞品也不猜），界面给 H1–H5 让选
  · 数值       `Math.max(0, Math.floor(Number(v) || 0))` —— 非法/负数一律 0

🩸 与竞品的差异：竞品有 `publishedAt` 时间戳列；我们同样存毫秒时间戳，
   但没有「按发布日过滤」的需求，所以只做倒序展示，不做时间窗口统计（不编功能）。
"""
from __future__ import annotations

import json
import math
import os
import time
import uuid
from pathlib import Path

#: 录入的五个数字字段（顺序 = 界面顺序）
NUM_FIELDS = ("views", "likes", "comments", "shares", "orders")
#: 冷启动门槛：至少两条样本才认「最能卖」（竞品 `topConvertingStyle(records, 2)`）
MIN_SAMPLES = 2
#: 备注最长（竞品 `route.ts:70` 的 `.slice(0, 500)`）
NOTE_MAX = 500


def _round_half_up(v: float) -> int:
    """JS `Math.round` 语义（0.5 向上），不是 Python 的银行家舍入。"""
    return int(math.floor(v + 0.5))


def _as_pct(rate: float) -> float:
    """竞品 `Math.round(rate * 1000) / 10`，保留一位小数。"""
    return math.floor(rate * 1000 + 0.5) / 10


def normalize_num(v) -> int:
    """`Math.max(0, Math.floor(Number(v) || 0))`。

    · 布尔 → 1/0（JS `Number(true)` = 1）
    · 数字字符串 → 数值（`"12"`）；带单位 `"12万"` → 0（JS 是 NaN → ||0）
    · None / 空串 / 非数字 → 0；负数 → 0
    """
    if isinstance(v, bool):
        return 1 if v else 0
    if v is None or v == "":
        return 0
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(f) or f < 0:
        return 0
    return int(math.floor(f))


def freeze_style(doc: dict) -> str:
    """录入时定格脚本风格（之后改配方也不污染历史统计）。"""
    tpl = (doc.get("template") or {}).get("template") or {}
    return str(tpl.get("styleType") or "").strip() or "custom"


def freeze_category(doc: dict) -> str | None:
    """品类同样定格；没填就 None（竞品 `project.productCategory ?? null`）。"""
    v = (doc.get("product") or {}).get("category")
    return str(v) if isinstance(v, str) else None


# ---------------------------------------------------------------------------
# 存储（一个 JSON 文件；原子写，避免半截文件把统计读坏）
# ---------------------------------------------------------------------------


def load(path: Path) -> list[dict]:
    """读全部记录。文件缺失/坏 JSON 一律当空列表（不要因为一条统计读不出来就 500）。"""
    p = Path(path)
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows = raw.get("metrics") if isinstance(raw, dict) else raw
    return [r for r in (rows or []) if isinstance(r, dict)]


def save(path: Path, rows: list[dict]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    body = {"metrics": rows,
            "updated": time.strftime("%Y-%m-%d %H:%M:%S")}
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def _next_ms(rows: list[dict]) -> int:
    """严格递增的毫秒时间戳：同毫秒连录两条时，后一条仍在前面。"""
    ms = int(time.time() * 1000)
    last = max((int(r.get("created_ms") or 0) for r in rows), default=0)
    return ms if ms > last else last + 1


def build_record(*, project_id: str, doc: dict, body: dict,
                 now_ms: int | None = None, rows: list[dict] | None = None) -> dict:
    """一条录入记录（字段口径逐条对齐竞品 `metrics/route.ts:52-77`）。"""
    rows = rows or []
    style = str(body.get("style") or "").strip() or freeze_style(doc)
    cat = body.get("category")
    category = cat if isinstance(cat, str) else freeze_category(doc)
    hook = str(body.get("hookId") or "").strip() or None
    platform = body.get("platform") if isinstance(body.get("platform"), str) else None
    note = body.get("note")
    note = note[:NOTE_MAX] if isinstance(note, str) else None

    published = body.get("publishedAt")
    if published:
        try:
            published_ms = int(float(published))
        except (TypeError, ValueError):
            published_ms = 0
        published_ms = published_ms or (now_ms if now_ms is not None else int(time.time() * 1000))
    else:
        published_ms = None

    rec = {
        "id": uuid.uuid4().hex,
        "project_id": project_id,
        "style": style,
        "hookId": hook,
        "category": category,
        "platform": platform,
        "created_ms": now_ms if now_ms is not None else _next_ms(rows),
        "published_at": published_ms,
        "note": note,
    }
    for k in NUM_FIELDS:
        rec[k] = normalize_num(body.get(k))
    return rec


def add(path: Path, record: dict) -> dict:
    rows = load(path)
    rows.append(record)
    save(path, rows)
    return record


def list_for(path: Path, project_id: str) -> list[dict]:
    """某个项目的记录，新的在前（竞品 `orderBy(desc(createdAt))`）。"""
    rows = [r for r in load(path) if str(r.get("project_id") or "") == project_id]
    rows.sort(key=lambda r: int(r.get("created_ms") or 0), reverse=True)
    return rows


# ---------------------------------------------------------------------------
# 聚合（`performance-insights.ts` 逐条）
# ---------------------------------------------------------------------------


def _num(v) -> float:
    if isinstance(v, bool):
        return float(v)
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    return f if math.isfinite(f) else 0.0


def _aggregate_by(records: list[dict], key: str) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for r in records or []:
        if not isinstance(r, dict):
            continue
        k = str(r.get(key) or "").strip()
        if not k:
            continue
        groups.setdefault(k, []).append(r)

    out: list[dict] = []
    for k, rs in groups.items():
        samples = len(rs)
        views = sum(_num(r.get("views")) for r in rs)
        eng = sum(_num(r.get("likes")) + _num(r.get("comments")) + _num(r.get("shares"))
                  for r in rs)
        orders = sum(_num(r.get("orders")) for r in rs)
        out.append({
            "key": k,
            "samples": samples,
            "avgViews": _round_half_up(views / samples) if samples else 0,
            "engagementRate": (eng / views) if views > 0 else 0.0,
            "conversionRate": (orders / views) if views > 0 else 0.0,
            "totalOrders": int(orders),
        })
    # Python 的 sort 是稳定排序 —— 同分同样本时保留首次出现顺序，和 JS 一致
    out.sort(key=lambda x: (-x["conversionRate"], -x["samples"]))
    return out


def aggregate_by_style(records: list[dict]) -> list[dict]:
    return [{"style": x.pop("key"), **x} for x in _aggregate_by(records, "style")]


def aggregate_by_hook(records: list[dict]) -> list[dict]:
    return [{"hookId": x.pop("key"), **x} for x in _aggregate_by(records, "hookId")]


def top_converting_style(records: list[dict], min_samples: int = MIN_SAMPLES) -> dict | None:
    ranked = [i for i in aggregate_by_style(records)
              if i["samples"] >= min_samples and i["conversionRate"] > 0]
    return ranked[0] if ranked else None


def top_converting_hook(records: list[dict], min_samples: int = MIN_SAMPLES) -> dict | None:
    ranked = [i for i in aggregate_by_hook(records)
              if i["samples"] >= min_samples and i["conversionRate"] > 0]
    return ranked[0] if ranked else None


def build_performance_hint(top_style: dict | None, top_hook: dict | None,
                           style_label=None, hook_label=None) -> str:
    """`buildPerformanceHint` 的中文原文（样本不足返回空串 = 什么都不注入）。"""
    sl = style_label or (lambda s: s)
    hl = hook_label or (lambda h: h)
    lines: list[str] = []
    if top_style:
        lines.append(
            f"- 转化最高的脚本风格是「{sl(top_style['style'])}」"
            f"（近 {top_style['samples']} 条实测，转化率约 "
            f"{_as_pct(top_style['conversionRate']):g}%）——本次优先采用或明显倾斜该风格。")
    if top_hook:
        lines.append(
            f"- 转化最高的开场钩子机制是「{hl(top_hook['hookId'])}」"
            f"（近 {top_hook['samples']} 条实测，转化率约 "
            f"{_as_pct(top_hook['conversionRate']):g}%）——开场三秒优先采用该机制。")
    if not lines:
        return ""
    return "【历史转化数据反馈（来自你已发布视频的真实成效，务必参考）】\n" + "\n".join(lines)


def scoped_records(records: list[dict], category: str | None) -> list[dict]:
    """同品类切片（竞品 `script/route.ts:113`）；品类为空时给空列表。"""
    c = (category or "").strip()
    if not c:
        return []
    return [r for r in records if str(r.get("category") or "") == c]


def hint_for_category(records: list[dict], category: str | None) -> str:
    """同品类优先，样本不够回落全局；两边都不够 → 空串（竞品同款顺序）。"""
    scoped = scoped_records(records, category)
    top_style = top_converting_style(scoped) or top_converting_style(records)
    top_hook = top_converting_hook(scoped) or top_converting_hook(records)
    return build_performance_hint(top_style, top_hook)


def insights_payload(records: list[dict]) -> dict:
    """`/api/insights/styles` 的返回体（字段名照竞品）。"""
    return {
        "insights": aggregate_by_style(records),
        "hookInsights": aggregate_by_hook(records),
        "total": len(records),
    }
