"""模型参数分档的自检 —— 每家按每家的官方标准，不许一套通吃。

参数出处：厂商官方文档 + 官方 skill（2026-10-21 抓取）
    火山  https://www.volcengine.com/docs/82379/1520757
          官方 skill sd25-pe / sd2-pe（arkdocs.tos-cn-beijing.volces.com/skills/）
    MiniMax https://platform.minimaxi.com/docs/api-reference/video-generation-v2-create
本测试只验"代码有没有按官方表取参数"，不发任何网络请求。

运行：python scripts/test_model_specs.py --model volc20|volc25|h3
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.core.config import settings  # noqa: E402
from app.services import model_specs, video_edit  # noqa: E402

PASS = FAIL = 0


def check(name: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {name}: {got}")
    else:
        FAIL += 1
        print(f"  FAIL {name}: got={got!r} want={want!r}")


def main() -> int:
    # 🚦 必须点名型号（2026-10-26）：本脚本验的是**共享层/参数表**，
    # 断言本身不分模型，点名只作「一次只跑一家」的执行闸。
    from _model_gate import sel_or_exit
    sel_or_exit()

    # 🩸 2026-10-31：2.0 已从复刻视频下架（适配器/编译器归档、参数表删除），
    #   火山只剩 2.5 一档。下面同时守着「旧 2.0 型号不崩、回落 2.5」。
    print("== 火山：只剩 2.5 一档 ==")
    s25 = model_specs.volc("doubao-seedance-2-5-260628")
    s20 = model_specs.volc("doubao-seedance-2-0-260128")
    check("2.5 单段上限", s25["max_sec"], 30.0)
    check("2.5 参考图上限", s25["max_ref_images"], 30)
    check("2.5 支持 1080p", "1080p" in s25["resolutions"], True)
    check("2.5 不支持 4k", "4k" in s25["resolutions"], False)
    check("2.5 有任务类型参数", s25["edit_task_param"], True)
    check("2.5 编辑任务 duration 固定 -1", s25["edit_duration"], -1)
    check("2.5 禁止自动加兜底包", s25["auto_constraint"], False)
    check("2.0 参数表已移除", "seedance-2-0-mini" not in model_specs.SPECS, True)
    check("旧 2.0 型号回落 2.5 档", s20 is s25, True)

    print("== MiniMax：官方四档各是一档（`h3-models`）==")
    h3 = model_specs.minimax("MiniMax-H3")
    h3max = model_specs.minimax("MiniMax-H3-Max")
    h3hs = model_specs.minimax("MiniMax-H3-Highspeed")
    h3lite = model_specs.minimax("MiniMax-H3-Lite")
    # 🩸 2026-10-28：官方「当前可用值：MiniMax-H3、MiniMax-H3-Highspeed、
    #   MiniMax-H3-Lite、MiniMax-H3-Max」。以前只认两档，另两个名字会被当成
    #   基础 H3 ⇒ 放行 2K ⇒ 接口直接拒（两档官方都「不支持 2K」）。
    # 🩸 2026-11-01 主人贴的官方价目表：Highspeed 768P ¥0.40/s、480P ¥0.26/s
    #   —— 480P 是有的，旧断言只放 768P 等于把便宜档挡住了。
    check("Highspeed 480P/768P", h3hs["resolutions"], ("480P", "768P"))
    check("Highspeed 不收 2K", "2K" in h3hs["resolutions"], False)
    check("Highspeed 时长下限 4s", h3hs["min_sec"], 4.0)
    check("Lite 480P/768P", h3lite["resolutions"], ("480P", "768P"))
    check("Lite 不收 2K", "2K" in h3lite["resolutions"], False)
    check("Lite 默认 768P", h3lite["default_resolution"], "768P")
    check("Lite 时长下限 4s", h3lite["min_sec"], 4.0)
    # 四档必须是四张不同的表（回到"全落到基础 H3"就是这条红）
    check("四档互不共用", len({id(x) for x in (h3, h3hs, h3lite, h3max)}), 4)
    # `volc()` 那条旧分岔也必须走同一份路由（以前它自己写了一遍只认 -max）
    check("volc() 与 minimax() 同源：Lite",
          model_specs.volc("MiniMax-H3-Lite") is h3lite, True)
    check("volc() 与 minimax() 同源：Highspeed",
          model_specs.volc("MiniMax-H3-Highspeed") is h3hs, True)
    # 🧊 2026-11-01 冻住 H3：界面候选应为空。断言**跟着 `Caps.frozen` 走**，
    #   不写死某一态 —— 否则每次冻结/解冻都要回来改一次判据（以前就是这样漏的）。
    from app.services import models as _models
    _h3_frozen = "minimax" in _models.frozen_families()
    check("冻住 H3 → 界面不提供型号" if _h3_frozen else "复刻界面可选 H3 四档",
          [m for m, _ in model_specs.MODELS["minimax"]],
          [] if _h3_frozen else
          ["MiniMax-H3", "MiniMax-H3-Max", "MiniMax-H3-Highspeed", "MiniMax-H3-Lite"])
    check("H3 参数表仍在（冻结 ≠ 删除）",
          model_specs.minimax("MiniMax-H3")["max_sec"], 15.0)
    check("H3 时长下限 4s", h3["min_sec"], 4.0)
    check("H3-Max 时长下限 5s", h3max["min_sec"], 5.0)
    check("H3 默认 768P", h3["default_resolution"], "768P")
    # 官方：H3-Max「480P、768P（默认 768P，不支持 2K）」
    check("H3-Max 默认 768P", h3max["default_resolution"], "768P")
    check("H3-Max 不收 2K", "2K" in h3max["resolutions"], False)
    # 官方：H3 输出 768P / 2K —— 2K 是 H3 直接支持的 resolution 值
    check("H3 支持 2K", "2K" in h3["resolutions"], True)
    check("H3 提示词硬上限 7000", h3["prompt_chars"], 7000)
    # 🩸 mini**max** 本身含 "max"，用 in 判断会把 H3 误认成 H3-Max
    check("H3 没被误认成 Max", h3["label"], "MiniMax H3")
    check("H3 走的是 4s 下限", h3 is not h3max, True)
    # 官方 skill 自己就分两派：2.0 强制挂兜底包（已下架），2.5 明令禁止自动加
    check("H3 没有兜底包这套", h3["auto_constraint"], False)

    print("== 分诊/切段按当前配置的模型取上限 ==")
    real_v = settings.ark_video_edit_model
    real_m = settings.minimax_video_model
    try:
        for model, want in (
            ("doubao-seedance-2-5-260628", 30.0),
            # 旧 2.0 型号：参数表已随下架删除，按 2.5 的 30s 切（不能崩、不能回落成 0）
            ("doubao-seedance-2-0-mini-260615", 30.0),
        ):
            object.__setattr__(settings, "ark_video_edit_model", model)
            check(f"{model.split('-')[-2]}-{model.split('-')[-1]} 切段上限",
                  video_edit._limit_for("volc"), want)
        object.__setattr__(settings, "minimax_video_model", "MiniMax-H3")
        check("H3 切段上限", video_edit._limit_for("minimax"), 15.0)
        # 🩸 生成时长按**型号**收口：调用方点名型号（不再靠"默认是 H3"这种隐含约定）
        check("H3 生成时长下限 4s",
              video_edit._gen_duration(2.0, "MiniMax-H3"), 4)
        # 🩸 写死 max(4, …) 会把 4s 塞给 H3-Max，官方给的区间是 5~15s
        object.__setattr__(settings, "minimax_video_model", "MiniMax-H3-Max")
        check("H3-Max 切段下限 5s", video_edit._min_for("minimax"), 5.0)
        check("H3-Max 生成时长下限 5s",
              video_edit._gen_duration(3.0, "MiniMax-H3-Max"), 5)
        check("H3-Max 生成时长不超 15s",
              video_edit._gen_duration(28.0, "MiniMax-H3-Max"), 15)
    finally:
        object.__setattr__(settings, "ark_video_edit_model", real_v)
        object.__setattr__(settings, "minimax_video_model", real_m)

    print("== 分辨率按型号收口 ==")
    try:
        # 旧 2.0 型号 → 回落 2.5，1080p 该被接受（不再退回 720p）
        object.__setattr__(settings, "ark_video_edit_model", "doubao-seedance-2-0-mini-260615")
        check("旧 2.0 型号要 1080p → 按 2.5 接受",
              video_edit._resolution_for("volc", {"resolution": "1080p"}, 1920), "1080p")
        object.__setattr__(settings, "ark_video_edit_model", "doubao-seedance-2-5-260628")
        check("2.5 要 1080p → 接受",
              video_edit._resolution_for("volc", {"resolution": "1080p"}, 1920), "1080p")
        object.__setattr__(settings, "minimax_video_model", "MiniMax-H3-Max")
        check("H3-Max 要 2K → 退回 768P",
              video_edit._resolution_for("minimax", {"resolution": "2K"}, 2160), "768P")
        object.__setattr__(settings, "minimax_video_model", "MiniMax-H3")
        check("H3 默认 768P",
              video_edit._resolution_for("minimax", {"resolution": "auto"}, 1920), "768P")
    finally:
        object.__setattr__(settings, "ark_video_edit_model", real_v)
        object.__setattr__(settings, "minimax_video_model", real_m)

    print("== 界面选的型号优先于配置默认 ==")
    try:
        object.__setattr__(settings, "ark_video_edit_model", "doubao-seedance-2-5-260628")
        # 🩸 2026-10-31：2.0 已从复刻爆款下架（主人拍板），老前端/缓存把 Mini 的
        #   ID 传进来时，入口必须回落成 2.5 再切 —— 否则会按 15s 切出一堆短段，
        #   实际却发给 30s 上限的模型。
        check("显式选已下架的 2.0 Mini → 回落 2.5 的 30s 上限",
              video_edit._limit_for("volc", "doubao-seedance-2-0-mini-260615"), 30.0)
        check("不选型号 → 回落到配置的 2.5",
              video_edit._limit_for("volc"), 30.0)
        object.__setattr__(settings, "minimax_video_model", "MiniMax-H3")
        check("显式选 H3-Max → 走 5s 下限",
              video_edit._min_for("minimax", "MiniMax-H3-Max"), 5.0)
        # 🩸 通道被「自动」改判时，用户选的别家型号不能原样发出去
        check("火山通道收到 MiniMax 型号 → 回落配置型号",
              video_edit._model_for("volc", "MiniMax-H3-Max"), "doubao-seedance-2-5-260628")
        check("MiniMax 通道收到火山型号 → 回落配置型号",
              video_edit._model_for("minimax", "doubao-seedance-2-0-260128"), "MiniMax-H3")
        check("同族型号照用不误",
              video_edit._model_for("volc", "doubao-seedance-2-5-260628"), "doubao-seedance-2-5-260628")
        # 🩸 成对的上半：族别对、但已下架 ⇒ 必须回落（不能照用）
        check("同族但已下架的 2.0 型号 → 回落 2.5",
              video_edit._model_for("volc", "doubao-seedance-2-0-260128"), "doubao-seedance-2-5-260628")
    finally:
        object.__setattr__(settings, "ark_video_edit_model", real_v)
        object.__setattr__(settings, "minimax_video_model", real_m)

    print("== 自动清晰度按短边判、且封顶 1080p ==")
    # 720p/1080p 说的都是**短边**；只看 height 会把横屏 1920×1080 判成 720p
    check("竖屏 1080×1920", video_edit._ark_res(1920, 1080), "1080p")
    check("横屏 1920×1080", video_edit._ark_res(1080, 1920), "1080p")
    check("720p 竖屏", video_edit._ark_res(1280, 720), "720p")
    check("480p", video_edit._ark_res(480, 640), "480p")
    # 4k 只有 2.0 标准版支持；auto 自动跳上去既贵、2.5 还会被退回默认档
    check("4k 源自动档封顶 1080p", video_edit._ark_res(3840, 2160), "1080p")

    print("== 可选型号表自洽 ==")
    # 🩸 2026-10-31：原来 4 档（2.0 标准/极速/Mini + 2.5）—— 2.0 已从复刻视频下架，
    #   适配器/编译器归档、参数表一并删除，界面只剩 2.5。
    check("火山 1 个可选型号（只剩 2.5）", len(model_specs.MODELS["volc"]), 1)
    # 官方 V2「当前可用值」就是这四个（`h3-models`，2026-10-28 抓取）；
    # 冻住时按 0 断言，解冻后自动回到 4。
    check("MiniMax 候选四档" if not _h3_frozen else "冻住 H3 → MiniMax 候选为空",
          len(model_specs.MODELS["minimax"]), 0 if _h3_frozen else 4)
    for ch, items in model_specs.MODELS.items():
        # 🩸 空清单必须单独断言：下面那组检查对空列表**恒真**（0 == 0），
        #   不拦住就会把"一条候选都没有"报成"每个型号都有自己那一档"的假绿。
        if not items:
            # 🧊 冻结的家族可以是空的（入口下架 = 预期），没冻结的必须报红。
            want_empty = ch in _models.frozen_families()
            check(f"{ch} 候选为空（{'已冻结' if want_empty else '⚠️ 未冻结却也空'}）",
                  bool(items), not want_empty)
            continue
        pick = model_specs.volc if ch == "volc" else model_specs.minimax
        got = [id(pick(mid)) for mid, _ in items]
        # 每个选项都必须认得自己那一档：都落进同一个默认档 = 选项是摆设
        check(f"{ch} 每个型号各有一档", len(set(got)), len(items))
        for mid, label in items:
            s = pick(mid)
            check(f"{label} 有分辨率", bool(s["resolutions"]), True)
            check(f"{label} 有时长区间", s["min_sec"] < s["max_sec"], True)

    print(f"\n{PASS}/{PASS + FAIL} 通过")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
