"""视觉盘点的纯逻辑自检（不发网络请求、不花钱）。

覆盖：JSON 解析、结果归一化、缓存命中、lite→pro 降级、
按段取人、按段决策（换/不换/留原片）、两套通道提示词。
运行：python scripts/test_vision_plan.py --model volc20|volc25|h3
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.core.config import settings  # noqa: E402
from app.services import clone_store, edit_spec, video_edit, vision_plan  # noqa: E402

PASS = FAIL = 0


def check(name: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {name}: {got}")
    else:
        FAIL += 1
        print(f"  FAIL {name}: got={got!r} want={want!r}")


RAW = {
    "duration_s": 30,
    "people": [
        {"id": "P1", "desc_zh": "穿红裙的长发女生", "desc_en": "the long-haired woman in a red dress",
         "appearances": [{"start": 0, "end": 10.5}], "main": True, "face_visible": True},
        {"id": "P2", "desc_zh": "戴帽子的男生", "desc_en": "the young man in a cap",
         "appearances": [{"start": 12, "end": 20}], "main": False, "face_visible": True},
    ],
    "products": [], "scenes": [], "notes": "",
}


def main() -> int:
    # 🚦 必须点名型号（2026-10-26）：一次只跑一家。
    from _model_gate import sel_or_exit
    sel_or_exit()

    tmp = Path(tempfile.mkdtemp(prefix="vptest_"))
    clone_store.task_dir = lambda cid: tmp / cid  # type: ignore[assignment]
    video = tmp / "src.mp4"
    video.write_bytes(b"fake-video-bytes")

    object.__setattr__(settings, "ark_api_key", "test-key")
    object.__setattr__(settings, "vision_enabled", True)
    object.__setattr__(settings, "vision_model", "doubao-seed-2-1-lite-260915")
    object.__setattr__(settings, "vision_model_fallback", "doubao-seed-2-1-pro-260915")
    object.__setattr__(settings, "vision_fps", 1.0)

    print("== 解析 ==")
    check("去掉 ```json 围栏", vision_plan.parse("```json\n" + __import__("json").dumps(RAW) + "\n```")["people"][0]["id"], "P1")
    check("前后有废话也能取出来",
          vision_plan.parse("好的，结果如下：" + __import__("json").dumps(RAW) + " 以上")["people"][1]["id"], "P2")
    try:
        vision_plan.parse("这不是 JSON")
        check("非 JSON 要报错", "没报错", "应当抛 VisionError")
    except vision_plan.VisionError:
        check("非 JSON 要报错", "VisionError", "VisionError")

    # 官方《Seedance 2.5 指南》:429-435「按人物**首次出场顺序**上传参考素材」。
    # schema 的「按首次出现排序」只是给模型的提示，这里机械重排 + 重编 id
    # （数组下标 = 人物槽位 = @图片N）。
    _out_of_order = vision_plan.normalize({
        "duration_s": 20,
        "people": [
            {"id": "P1", "desc_zh": "后出场的人", "desc_en": "late",
             "position": "right", "appearances": [{"start": 8, "end": 12}],
             "main": True, "face_visible": True},
            {"id": "P2", "desc_zh": "先出场的人", "desc_en": "early",
             "position": "left", "appearances": [{"start": 0.5, "end": 3}],
             "main": False, "face_visible": True},
        ],
        "products": [], "scenes": [], "shots": [], "notes": ""})
    check("按首次出场顺序重排", _out_of_order["people"][0]["desc_zh"], "先出场的人")
    check("重排后 id 重编成 P1", _out_of_order["people"][0]["id"], "P1")
    check("main 跟着人走、不跟着 id",
          _out_of_order["people"][1]["main"], True)

    print("== 归一化 ==")
    messy = vision_plan.normalize({
        "duration_s": 10,
        "people": [
            {"id": "", "desc_zh": "甲", "desc_en": "", "appearances": [
                {"start": -3, "end": 4}, {"start": 8, "end": 99}]},
            {"desc_zh": "乙", "appearances": [{"start": 5, "end": 5}]},
        ],
        "products": [{"desc_zh": "咖啡杯"}],
        "scenes": [],
        "notes": None,
    })
    check("没 id 自动编号", messy["people"][0]["id"], "P1")
    check("秒数夹回 [0, 时长]", messy["people"][0]["appearances"],
          [{"start": 0.0, "end": 4.0}, {"start": 8.0, "end": 10.0}])
    check("零长度出现段被丢掉（整条人没了）", len(messy["people"]), 1)
    check("没有 main 时自动选最长的那条", messy["people"][0]["main"], True)
    check("desc_en 缺失用中文兜底", messy["people"][0]["desc_en"], "甲")
    check("产品中文兜底", messy["products"][0]["desc_en"], "咖啡杯")
    two_main = vision_plan.normalize({
        "duration_s": 10,
        "people": [
            {"id": "P1", "desc_zh": "甲", "desc_en": "a", "appearances": [{"start": 0, "end": 2}], "main": True},
            {"id": "P2", "desc_zh": "乙", "desc_en": "b", "appearances": [{"start": 0, "end": 8}], "main": True},
        ], "products": [], "scenes": [], "notes": "",
    })
    check("多个 main 只留一个", [p["id"] for p in two_main["people"] if p["main"]], ["P2"])

    print("== 缓存 ==")
    calls: list[str] = []

    def fake_call(p, *, model, fps, timeout=240):
        calls.append(model)
        return vision_plan.normalize(RAW)

    vision_plan._call = fake_call  # type: ignore[assignment]
    inv1 = vision_plan.inventory("c1", video)
    inv2 = vision_plan.inventory("c1", video)
    check("第一次调用模型", len(calls), 1)
    check("第二次命中缓存不调模型", len(calls), 1)
    check("缓存结果标记 cached", inv2["_meta"]["cached"], True)
    check("缓存结果内容一致", inv2["people"], inv1["people"])
    vision_plan.inventory("c1", video, fps=2.0)
    check("改 fps 不命中旧缓存", len(calls), 2)
    vision_plan.inventory("c1", video, refresh=True)
    check("刷新强制再调一次", len(calls), 3)

    print("== 降级 ==")
    calls.clear()

    def fail_lite(p, *, model, fps, timeout=240):
        calls.append(model)
        if model == "doubao-seed-2-1-lite-260915":
            raise vision_plan.VisionError("lite 不支持视频")
        return vision_plan.normalize(RAW)

    vision_plan._call = fail_lite  # type: ignore[assignment]
    inv3 = vision_plan.inventory("c2", video)
    check("lite 失败自动换 pro", calls, ["doubao-seed-2-1-lite-260915",
                                        "doubao-seed-2-1-pro-260915"])
    check("降级后记录实际型号", inv3["_meta"]["model"], "doubao-seed-2-1-pro-260915")

    print("== 按段取人 ==")
    inv = vision_plan.normalize(RAW)
    check("0–5 秒是 P1", [p["id"] for p in vision_plan.people_in(inv, 0, 5)], ["P1"])
    check("11–13 秒是 P2", [p["id"] for p in vision_plan.people_in(inv, 11, 13)], ["P2"])
    check("21–30 秒没人", vision_plan.people_in(inv, 21, 30), [])
    check("默认取主角", vision_plan.target_in(inv, 0, 5)["id"], "P1")
    check("指定 P2：该段没有 → None", vision_plan.target_in(inv, 0, 5, person_id="P2"), None)
    check("指定 P2：该段有 → P2", vision_plan.target_in(inv, 12, 15, person_id="P2")["id"], "P2")

    print("== 按段决策 ==")
    # 保留原声：目标不在的段才能整段留原片
    spec_orig = edit_spec.normalize({"person": True, "person_id": "P1",
                                     "audio": "original"})
    plan = {"inventory": inv, "spec": spec_orig, "ch": "volc",
            "model": "doubao-seedance-2-5-260628", "prompt": "老提示词",
            "person_asset": ""}
    acts = video_edit._span_plan(plan, [(0.0, 5.0), (12.0, 15.0), (21.0, 30.0)])
    check("有目标 → change", acts[(0.0, 5.0)][0], "change")
    check("没目标且无其他改动 → keep 原片", acts[(21.0, 30.0)][0], "keep")
    check("换了人但该段没他 → keep", acts[(12.0, 15.0)][0], "keep")

    # 全新配音：口型必须重做，哪怕这一段不换人，也不能留原片
    spec_tts = edit_spec.normalize({"person": True, "person_id": "P1"})
    acts_tts = video_edit._span_plan(dict(plan, spec=spec_tts),
                                     [(0.0, 5.0), (21.0, 30.0)])
    check("全新配音 + 目标不在 → 仍重画（重做口型）", acts_tts[(21.0, 30.0)][0], "text")
    check("全新配音 + 有目标 → 换人", acts_tts[(0.0, 5.0)][0], "change")

    spec_extra = edit_spec.normalize({"person": True, "person_id": "P1",
                                      "extra": "画面更亮一点"})
    plan2 = dict(plan, spec=spec_extra)
    acts2 = video_edit._span_plan(plan2, [(0.0, 5.0), (21.0, 30.0)])
    check("还有别的改动 → 该段只摘掉换人", acts2[(21.0, 30.0)][0], "text")
    check("没有盘点 → 老行为", video_edit._span_plan({"spec": spec_orig}, [(0.0, 5.0)]), {})

    # 明确选了盘点里不存在的人：不许猜，直接报错（钱还没花）
    spec_bad = edit_spec.normalize({"person": True, "person_id": "P9"})
    try:
        video_edit._span_plan(dict(plan, spec=spec_bad), [(0.0, 5.0)])
        check("选错人要在花钱前报错", "没报错", "EditError")
    except video_edit.EditError:
        check("选错人要在花钱前报错", "EditError", "EditError")

    print("== 提示词 ==")
    p_target = video_edit._span_prompt(plan, [inv["people"][0]], drop_person=False)
    check("火山把'那个人'写进提示词", "穿红裙的长发女生" in p_target, True)
    check("火山仍带编辑意图词", "替换为" in p_target, True)
    check("火山仍带范围闭环", "其他可见人物、道具和背景元素保持原样" in p_target, True)
    p_drop = video_edit._span_prompt(plan, None, drop_person=True)
    check("摘掉换人后不再有替换句", "替换为" in p_drop, False)
    check("摘掉换人后仍指原片", "@视频1" in p_drop, True)

    # 🧊 2026-11-03 复刻下架 H3：这一段原本验 H3 编译器的六段式输出
    #   （主体锚 <Picture N>、attribute_transfer、fully_preserved 边界）。
    #   编译器连同 `models/h3.py` 的执行项一起归档到 `backend/_archive/h3_clone/`，
    #   产品里已经没有这条链路可验 —— 断言随被测对象一起下线，不是丢了判据。
    #   要恢复请按 `_archive/h3_clone/README.md` 的 6 步接回来，再把这 9 条补回。

    print("== 定妆描述要写的维度 ==")
    # 🩸 2026-11-04 主人：「完整度要和成功版一样，主要就是怕有鞋子的镜头没换上」。
    #   实测 35 份 `subject_desc*.json` 只有 3 份写了鞋（其中就有唯一换脸成功那次
    #   `cb7a6ea1`）—— 不是没写就没事，是模型有时写有时不写。鞋属于 outfit 维度：
    #   `co-op-game-intro-generator/SKILL.md:34` 的 outfit dimensions 含 brown boots，
    #   `3d-animation-short-generator/SKILL.md:147` 把 shoes 列进重要标注项。
    check("描述提问里点名要写鞋", "鞋也要写" in vision_plan._DESC_ASK, True)
    check("描述版本号已升（老描述作废重算）", vision_plan._DESC_VERSION >= 5, True)

    print("== person_id 校验 ==")
    check("P2 保留", edit_spec.normalize({"person": True, "person_id": "P2"})["change"]["person_id"], "P2")
    check("怪字符串丢掉", edit_spec.normalize({"person": True, "person_id": "把所有人"})["change"]["person_id"], "")

    print(f"\n{PASS}/{PASS + FAIL} 通过")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
