"""能力预检（C16）—— 出片前先把「这个型号到底吃不吃这套参数」摊开，别等付了钱才被拒。

出处：竞品 `src/lib/model-capabilities.ts`
  · 能力契约 `VideoModelCapabilities`（`:10-35`）
  · 置信度 `known | inferred | unknown`（`:8`）
  · 预检 `preflightVideoGeneration`（`:151-215`）：
      - 参数改写四类 `nearest-duration` / `mapped-resolution` / `adaptive-ratio` /
        `unsupported-last-frame`（`:59-64`）
      - 五类告警 `capabilities-unknown` / `native-audio-unavailable` /
        `reference-images-trimmed` / `reference-conditioning-unavailable` /
        `reference-audio-unavailable`（`:66-74`）
  · 分辨率选型 `providers/atlas-video-params.ts:295-320`（「盖得住的最小档，盖不住取最大档」）
  · 时长选型 `:279-289`（最近值，同距取小）—— 但见下面「与竞品不同的两处」。

与竞品不同的两处（都因为我们的参数源不同，不是简化）：
  1. 时长短不是枚举而是**区间**（`model_specs.SPECS` 的 `min_sec`/`max_sec`），
     所以改写码叫 `clamped-duration`、取夹取而不是「最近枚举值」。
  2. 能力字段里有几项我们没有对应实现，就报 **null**，不许猜 true：
     时间窗重拍 / 区域蒙版 / 时间轴关键帧（`temporalRetake` / `regionMask` /
     `multiKeyframes`）—— 竞品对已知型号一律报 false（它也没有原生实现，` :44-56`），
     我们照同一口径报 false；未知型号报 null。

模型能力从 `model_specs` 算，不另建一张表 —— 那边已经是按官方口径维护的。
"""
from __future__ import annotations

import re

from app.services import model_specs

#: 出片可选型号（`model_specs.MODELS["volc"]`）
KNOWN = {mid for mid, _ in model_specs.MODELS["volc"]}
_FAMILY = re.compile(r"seedance|doubao|minimax|h3", re.I)

#: 本产品出片只出竖屏（`drama.py:film_render` 的 `ratio="9:16"`）
RATIOS = ("9:16",)

CODES = ("clamped-duration", "mapped-resolution", "adaptive-ratio", "unsupported-last-frame")
WARNINGS = ("capabilities-unknown", "native-audio-unavailable", "reference-images-trimmed",
            "reference-conditioning-unavailable", "reference-audio-unavailable")


def parse_res_tier(value: str) -> int | None:
    """竞品 `atlas-video-params.ts:295-304`：`720p`→720、`2K`→1440、`4k`→2160。"""
    low = (value or "").strip().lower()
    m = re.match(r"^(\d+)\s*p", low)
    if m:
        return int(m.group(1))
    k = re.match(r"^(\d+)\s*k", low)
    if not k:
        return None
    n = int(k.group(1))
    return 1080 if n == 1 else 1440 if n == 2 else 2160 if n == 4 else None


def pick_resolution(allowed, want: str) -> str | None:
    """竞品 `:311-320`：盖得住的最小档；都盖不住取最大档。"""
    tiers = sorted(((v, parse_res_tier(v)) for v in allowed if parse_res_tier(v) is not None),
                   key=lambda x: (x[1], len(x[0])))
    if not tiers:
        return None
    need = parse_res_tier(want)
    if need is None:
        return None
    for v, tier in tiers:
        if tier >= need:
            return v
    return tiers[-1][0]


def pick_ratio(allowed, want: str) -> str | None:
    """竞品 `:327-342`：比例最近的一档；我们只有 9:16。"""
    if not allowed:
        return None
    target = None
    m = re.match(r"^(\d+):(\d+)$", (want or "").strip())
    if m:
        target = int(m.group(1)) / int(m.group(2))
    best, best_diff = None, float("inf")
    for v in allowed:
        mm = re.match(r"^(\d+):(\d+)$", v)
        if not mm or target is None:
            continue
        diff = abs(int(mm.group(1)) / int(mm.group(2)) - target)
        if diff < best_diff:
            best, best_diff = v, diff
    return best or allowed[0]


def capabilities(model: str) -> dict:
    """单个型号的能力表（字段名照竞品 `VideoModelCapabilities`）。"""
    mid = (model or "").strip()
    known = mid in KNOWN
    confidence = "known" if known else ("inferred" if _FAMILY.search(mid) else "unknown")
    spec = model_specs.volc(mid)          # 认不出时它就是会回落到 2.5（接口本来也这么走）
    is_minimax = "minimax" in mid.lower() or mid.lower().startswith("h3")
    return {
        "model": mid,
        "label": spec.get("label") or "",
        "confidence": confidence,
        "textToVideo": True,
        "imageToVideo": True,
        "referenceImages": int(spec.get("max_ref_images") or 0) > 0,
        "referenceVideo": int(spec.get("max_ref_videos") or 0) > 0,
        "referenceAudio": bool(spec.get("ref_audio")),
        # 尾帧：火山官方「首尾帧」我们已在 `ark.py:225-260` 接上；
        # MiniMax 通道没有 first_frame 参数（`minimax.py` 无该字段）→ 不支持。
        "lastFrame": not is_minimax,
        # 原生音轨：火山出片 `generate_audio=True`；H3 自成声轨（`model_specs` 注释）
        "nativeAudio": True,
        # 编辑任务：SPECS 的 `edit_task_param` 就是「这个档认不认编辑任务」
        "videoEdit": bool(spec.get("edit_task_param")),
        # 原生时间窗重拍 / 区域蒙版 / 时间轴关键帧：两家接口都没有 → 已知型号报 false
        "temporalRetake": False,
        "regionMask": False,
        "multiKeyframes": False,
        # 参考视频能引导动作，所以表演参考 = 参考视频能力
        "performanceReference": int(spec.get("max_ref_videos") or 0) > 0,
        "durationRange": [float(spec.get("min_sec") or 0), float(spec.get("max_sec") or 0)],
        "resolutionValues": list(spec.get("resolutions") or ()),
        "aspectRatioValues": list(RATIOS),
        "maxReferenceImages": int(spec.get("max_ref_images") or 0),
        "maxReferenceVideos": int(spec.get("max_ref_videos") or 0),
        "maxReferenceAudio": int(spec.get("max_ref_audio") or 0),
    }


def preflight(model: str, *, duration: float | None = None, resolution: str = "720p",
              aspect_ratio: str = "9:16", chain_mode: str = "off",
              audio_enabled: bool = False, reference_image_count: int = 0,
              reference_audio_count: int = 0) -> dict:
    """出片前预检：返回会怎么改 + 会踩什么坑（**不改任何东西**，纯计算）。"""
    caps = capabilities(model)
    adjustments: list[dict] = []
    warnings: list[str] = []

    if caps["confidence"] == "unknown":
        warnings.append("capabilities-unknown")

    lo, hi = caps["durationRange"]
    if duration is not None and hi > 0:
        eff = min(hi, max(lo, float(duration)))
        if abs(eff - float(duration)) > 1e-6:
            adjustments.append({"field": "duration", "requested": duration,
                                "effective": eff, "code": "clamped-duration"})

    values = caps["resolutionValues"]
    if values:
        eff_res = pick_resolution(values, resolution)
        if eff_res and eff_res.lower() != (resolution or "").lower():
            adjustments.append({"field": "resolution", "requested": resolution,
                                "effective": eff_res, "code": "mapped-resolution"})

    eff_ratio = pick_ratio(caps["aspectRatioValues"], aspect_ratio)
    if eff_ratio and eff_ratio != (aspect_ratio or "").strip():
        adjustments.append({"field": "aspectRatio", "requested": aspect_ratio,
                            "effective": eff_ratio, "code": "adaptive-ratio"})

    if chain_mode not in ("off", "") and not caps["lastFrame"]:
        adjustments.append({"field": "chainMode", "requested": chain_mode,
                            "effective": "off", "code": "unsupported-last-frame"})

    if audio_enabled and not caps["nativeAudio"]:
        warnings.append("native-audio-unavailable")
    if reference_image_count > 0 and not caps["referenceImages"]:
        warnings.append("reference-conditioning-unavailable")
    if reference_audio_count > 0 and not caps["referenceAudio"]:
        warnings.append("reference-audio-unavailable")
    if (caps["maxReferenceImages"] and reference_image_count > caps["maxReferenceImages"]):
        warnings.append("reference-images-trimmed")

    return {"capabilities": caps, "adjustments": adjustments, "warnings": warnings}


def catalog() -> list[dict]:
    """给前端下拉用：每个可选型号一行摘要（不调模型）。"""
    out = []
    for mid, label in model_specs.MODELS["volc"]:
        c = capabilities(mid)
        out.append({
            "id": mid, "label": label,
            "min_sec": c["durationRange"][0], "max_sec": c["durationRange"][1],
            "resolutions": c["resolutionValues"],
            "max_ref_images": c["maxReferenceImages"],
            "last_frame": c["lastFrame"], "native_audio": c["nativeAudio"],
        })
    return out
