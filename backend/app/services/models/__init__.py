"""模型注册表 —— 核心只问"这个型号归谁管"，不问"这是哪一家"。

用法：

    from app.services import models
    ad = models.adapter_for(model="doubao-seedance-2-5-260628", channel="volc")
    ad.pre_compile(spec)                 # 编译前加工（H3 的中文翻译就在这里）
    ad.gate(inventory, slots, ids)       # 出片前的可指认闸
    prompt = ad.compile(spec, channel="volc", model=..., slots=slots)

**加一家模型 = 新建 `models/<家>.py` 并在文件末尾 `register(...)`** + 在下面
`import` 一行。核心（`video_edit` / `edit_spec`）一个字都不用改。
"""
from __future__ import annotations

import logging

from app.services.models.base import Caps, ModelAdapter  # noqa: F401

log = logging.getLogger(__name__)

_REGISTRY: dict[str, ModelAdapter] = {}


def register(ad: ModelAdapter) -> ModelAdapter:
    _REGISTRY[ad.model_id] = ad
    return ad


def all_adapters() -> list[ModelAdapter]:
    return list(_REGISTRY.values())


def family_of(model: str, channel: str = "") -> str:
    """这个型号属于哪一族（`volc` / `minimax`）。**不猜型号表，按注册的前缀判。**"""
    ad = adapter_for(model=model, channel=channel)
    return ad.family


def family_of_model(model: str) -> str | None:
    """**只按型号判**归属，判不出来返回 `None`（不回落通道默认）。

    🩸 和 `family_of` 的区别很重要：`family_of("乱填的型号", channel="volc")`
    会回落到火山，看着像"它属于火山"。要判断「用户选的型号能不能发给这条通道」
    必须用这个 —— `None` = 认不出，不能当同族。
    """
    m = (model or "").strip()
    if not m:
        return None
    if m in _REGISTRY:
        return _REGISTRY[m].family
    low = m.lower()
    for ad in _REGISTRY.values():
        if any(low.startswith(p) for p in ad.caps.raw.get("prefixes", ())):
            return ad.family
    return None


def adapters_by_family() -> dict[str, ModelAdapter]:
    """家族 → 该族的默认适配器（通道级操作由它代表，比如"这条通道配好了吗"）。"""
    out: dict[str, ModelAdapter] = {}
    for ad in _REGISTRY.values():
        out.setdefault(ad.family, ad)
    return out


def frozen_families() -> frozenset[str]:
    """当前产品线**不接**的家族（由适配器自己声明 `Caps.frozen`）。

    🩸 2026-10-31：复刻冻结 H3 时，这条名单原本写在 `app/api/clone.py` 里
    （`frozenset({"minimax"})`）—— 分离门当场报「核心文件里新增厂商耦合」。
    厂商名只能出现在 `models/<家>.py`；核心问注册表。
    """
    return frozenset(ad.family for ad in _REGISTRY.values() if ad.caps.frozen)


def adapter_for(model: str = "", channel: str = "") -> ModelAdapter:
    """按型号取适配器；型号为空就按通道取那一族的默认。

    🩸 顺序：**精确型号 → 注册的前缀 → 通道默认**。
    前缀由各家自己声明（`doubao-seedance-2-5` 归 2.5），核心不写任何型号字符串。
    🩸 型号和通道打架时（界面选 `auto`，通道被素材类型改判）以**通道**为准 ——
    把 MiniMax 的型号发给火山是直接 400。这里只做家族纠正，具体型号纠正
    仍在 `video_edit._model_for`（那里才知道落回哪个默认）。
    """
    m = (model or "").strip()
    if m and m in _REGISTRY:
        return _REGISTRY[m]
    low = m.lower()
    if m:
        for ad in _REGISTRY.values():
            if any(low.startswith(p) for p in ad.caps.raw.get("prefixes", ())):
                return ad
        log.warning("型号 %s 没有登记，按通道 %s 的默认走", m, channel or "?")
    fam = (channel or "").strip().lower()
    # 🩸 以前这里写死「minimax 走 H3、其余走火山」—— 加第 4 家时按通道取就会错。
    # 现在问注册表：谁声明了自己是这条通道的代表（`Caps.is_channel_default`）。
    if fam:
        for ad in _REGISTRY.values():
            if ad.family == fam and ad.caps.is_channel_default:
                return ad
        for ad in _REGISTRY.values():
            if ad.family == fam:
                return ad
        log.warning("通道 %s 没有登记，按火山默认走", channel)
    return _REGISTRY[_DEFAULT_VOLC]


# 🩸 2026-10-31：2.0 三档已下架（`model_specs.MODELS`），兜底必须指向还活着的型号。
#   这里只是「注册表里找不到时拿谁的适配器」的最后一道，选 2.5（火山唯一在售编辑档）。
_DEFAULT_VOLC = "doubao-seedance-2-5-260628"
_DEFAULT_MINIMAX = "MiniMax-H3"


# 各家的模块在末尾 `register()` 自己；放在这里是为了避免循环导入。
# 🩸 2026-10-31 曾按主人「复刻视频直接下架 2.0 模型」把 2.0 归档；
#   **2026-11-04 主人重新部署**：「模型全上，因为调试好不影响 2.0 模型的使用，
#   他们都是同一套提示词的」→ `volc20.py` / `volc20_compile.py` 已 `git mv` 回来，
#   三档（标准 / fast / mini）全上。
#   ⚠️ 提示词优化那条线始终走 `sd20_skill` → `volc20_pe`（独立规则校验），不经过注册表。
from app.services.models import h3, volc20, volc25  # noqa: E402,F401
