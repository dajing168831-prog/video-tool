# -*- coding: utf-8 -*-
"""L3 的验收判据：**加第 4 家到底要不要改核心**。

做一个假的第 4 家适配器（`future-1`），只 `register()` 一下，然后看核心能不能认出它。
核心三个文件（`video_edit` / `edit_spec` / `clone_pipeline`）本轮**一行都没改**。

这不是"将来会好用"的承诺，是真的注册进去跑一遍：
  R1 注册后 `adapter_for("future-1-2027")` 认得出
  R2 `family_of_model` 判得出归属，不回落成火山
  R3 `pick_channel("future")` 认这条通道
  R4 `_model_for` 认这个型号（不跨族纠正）
  R5 卸载后注册表恢复原状（不能留垃圾）
  R6 核心文件里确实没有它的名字（否则"不改核心"是假的）

零依赖、不联网、不花钱。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import model_specs, models  # noqa: E402
from app.services.models.base import Caps, ModelAdapter, NoDialect  # noqa: E402

FAKE_ID = "future-1-2027"

ok = fail = 0


def chk(name: str, cond: bool, got: str = "") -> None:
    global ok, fail
    if cond:
        ok += 1
        print(f"  ok   {name}")
    else:
        fail += 1
        print(f"  FAIL {name}   {got}")


before = dict(models._REGISTRY)
fake = ModelAdapter(
    dialect=NoDialect(),
    caps=Caps(model_id=FAKE_ID, family="future", max_dur=99.0, min_dur=1.0,
              auto_prefer={"file": 0, "none": 0, "asset": 0},
              default_model_setting="",
              # 2026-10-26 L3 第三轮新下沉的三处能力：接缝 / 档位 / 延长提示词
              extend_seam=(2, 3), extend_ref_mode="",
              resolutions=("512P",), resolution_alias={"720p": "512P"}),
    specs_for=lambda m: {"label": "未来模型", "max_sec": 99.0, "min_sec": 1.0},
    pic=lambda n: f"[Frame {n}]",
    vid=lambda: "[Clip 1]",
    compile=lambda spec, **kw: "[future prompt]",
    ready=lambda: True,
    extend_prompt=lambda direction, content: f"[future extend {direction}] {content}",
    extend_submit=lambda **kw: None,
)
fake.caps.raw["prefixes"] = ("future-",)

try:
    models.register(fake)

    ad = models.adapter_for(model=FAKE_ID)
    chk("R1 注册后 core 认得出这个型号", ad is fake, str(getattr(ad, "model_id", ad)))

    chk("R2 family_of_model 判得出归属（不回落火山）",
        models.family_of_model(FAKE_ID) == "future",
        str(models.family_of_model(FAKE_ID)))

    chk("R3 pick_channel 认这条通道",
        "future" in models.adapters_by_family(),
        str(list(models.adapters_by_family())))

    from app.services import video_edit
    chk("R4 _model_for 不跨族纠错", video_edit._model_for("future", FAKE_ID) == FAKE_ID,
        video_edit._model_for("future", FAKE_ID))

    # 真的有提示词，不是空壳
    chk("R5 它的 compile 被调到（不是回落成别家）",
        ad.compile({}) == "[future prompt]", str(ad.compile({})))

    # ---- 2026-10-26 L3 第三轮新下沉的能力，也要由注册表驱动 ----
    from app.services import edit_spec, extend
    chk("R8 延长接缝帧数读它的 Caps（不是火山 6+1 / 不是不裁）",
        extend.seam_frames(FAKE_ID) == (2, 3), str(extend.seam_frames(FAKE_ID)))
    chk("R9 延长时长按它的参数表收口（不是别家的 15s）",
        extend.clamp_seconds(999, FAKE_ID) == 99, str(extend.clamp_seconds(999, FAKE_ID)))
    chk("R10 清晰度档位读它的 Caps（不是火山/H3 的枚举）",
        edit_spec.resolution_for("future", {"resolution": "512P"}, auto="auto") == "512P",
        edit_spec.resolution_for("future", {"resolution": "512P"}, auto="auto"))
    chk("R11 别名映射也读它的 Caps",
        edit_spec.resolution_for("future", {"resolution": "720p"}, auto="auto") == "512P",
        edit_spec.resolution_for("future", {"resolution": "720p"}, auto="auto"))
    chk("R12 延长提示词由它自己出（核心不回落成别家句式）",
        ad.extend_prompt("back", "x") == "[future extend back] x",
        str(ad.extend_prompt("back", "x")))
finally:
    models._REGISTRY.clear()
    models._REGISTRY.update(before)

chk("R6 卸载后注册表恢复原状",
    set(models._REGISTRY) == set(before), str(set(models._REGISTRY) ^ set(before)))

# 核心文件里不许出现这个假模型的名字 —— 出现 = "不改核心"是吹的
core_hits = []
for rel in ("app/services/video_edit.py", "app/services/edit_spec.py",
            "app/services/clone_pipeline.py"):
    t = (ROOT / rel).read_text(encoding="utf-8")
    if "future-1" in t.lower() or "future_1" in t.lower():
        core_hits.append(rel)
chk("R7 核心文件里没有它的名字（加一家真的不用改核心）",
    not core_hits, str(core_hits))

# 🩸 R13（2026-10-28）：**同一型号的不同写法必须路由到同一家**。
#
# 发现经过：`model_specs.volc()` 用**子串**匹配（`"seedance-2-5" in m`），
# 短名 `seedance-2-5` 它认成 2.5；而注册表用**前缀**匹配，只登记了
# `doubao-seedance-2-5`，短名匹配不上 → 落到"通道默认" = **2.0 的适配器**。
# 于是 2.0 编译器里塞了一段「如果型号是 2.5 就静默转调 2.5 编译器」的兜底，
# 把这条缝藏了起来 —— 两套识别口径，同一个型号在两个地方有两个家。
# 兜底已删（现在会抛错），两边前缀已统一；这条断言守住它不再分叉。
# 🩸 用**自动派生**的候选写法，不手写白名单 —— 手写的话加第 4 家又得记得补，
#   而「忘了补」正是这条判据要防的事。
_routes_bad = []
for _ad in models.all_adapters():
    _want = _ad.model_id
    # 这家认的每一种写法 + 它自己的 model_id，都必须路由回它自己
    for _c in list(_ad.caps.raw.get("prefixes", ())) + [_want]:
        _got = models.adapter_for(model=_c).model_id
        if _got != _want:
            _routes_bad.append(f"{_c} → {_got}（期望 {_want}）")
chk("R13 同一家的每一种写法都路由回自己",
    not _routes_bad, "; ".join(_routes_bad))

# 🩸 R14：**两套识别口径必须给出同一个答案**。
#
# `model_specs.volc()` 用**子串**匹配（`"seedance-2-5" in m`）—— 短名它认；
# 注册表 `adapter_for()` 用**前缀**匹配 —— 只登记了 `doubao-seedance-2-5`，
# 短名会落到"通道默认"（= 2.0 的适配器）。
# 2026-10-27 就是因为这条缝，2.0 编译器里塞了一段「型号是 2.5 就静默转调
# 2.5 编译器」的兜底，把错误路由藏了两个多月没人看见。
#
# 候选写法从 `model_specs.SPECS` 的键自动派生（那就是"我们能叫出名字的所有写法"），
# 所以新增一档只会让这条判据自动变严，不需要人来补表。
_spec_bad = []
for _key, _spec in model_specs.SPECS.items():
    if _key.startswith(("minimax", "h3")):
        continue      # 只比对火山两代；H3 走 `minimax()`，口径不同
    _want_etp = bool(_spec.get("edit_task_param"))
    _got_etp = bool(models.adapter_for(model=_key).caps.edit_task_param)
    if _got_etp != _want_etp:
        _spec_bad.append(
            f"{_key}: model_specs 说是 {'2.5' if _want_etp else '2.0'} 参数，"
            f"注册表路由到了 {'2.5' if _got_etp else '2.0'} 的适配器")
chk("R14 model_specs 与注册表对同一写法给出同一代（自动派生候选）",
    not _spec_bad, "; ".join(_spec_bad))

print(f"\n{ok}/{ok + fail} 通过")
raise SystemExit(0 if not fail else 1)
