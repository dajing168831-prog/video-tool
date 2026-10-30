"""P9 验收：多人换人（一人一张参考图、一人一句提示词）。

零模型调用、不联网、不花钱。判的都是"下一个使用者会看到什么"：
  A. 规格：多选的人怎么存（去重 / 上限 / 老字段同步 / 取消勾选清空）
  B. 槽位：一人一槽，图号顺序稳定（person → person2 → product …）
  C. 提示词：几个人就几句、各绑各的图号；这一刀没出现的人不许写换人句；
     范围闭环句在；单人时仍然只有一句（不变式）
  D. 逐段分诊：两个人都在这段 → 换两个；只有一个人 → 只换他；都不在 → 留原片
  E. 界面契约：多选 chip / 各自上传 / 请求体带 person_ids / 参数真的传下去
  F. 素材：**一人一张原图**，不再派生大头照（2026-10-26 台账 D48；以前是「每人独立裁大头照」，已作废）

跑法：python scripts/p9_check.py --model volc20|volc25|h3
"""
from __future__ import annotations

import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import edit_spec, vision_plan, video_edit  # noqa: E402

FRONT = ROOT.parent / "frontend" / "app" / "src"

rows: list[tuple[str, bool, str]] = []

# 🚦 必须点名型号（2026-10-26）：一轮只跑一家。空串 = 还没解析。
SEL = ""


def chk(name: str, ok: bool, detail: str = "") -> None:
    rows.append((name, bool(ok), detail))


def spec_of(ids: list[str], **change) -> dict:
    raw = {"change": {"person": True, "person_ids": ids, **change}, "audio": "tts"}
    return edit_spec.normalize(raw)


INV = {
    "people": [
        {"id": "P1", "desc_zh": "穿红裙的女生", "desc_en": "the woman in a red dress",
         "main": True, "appearances": [{"start": 0.0, "end": 5.0}]},
        {"id": "P2", "desc_zh": "穿蓝衬衫的男生", "desc_en": "the man in a blue shirt",
         "main": False, "appearances": [{"start": 3.0, "end": 5.0}]},
    ]
}


# ---------------------------------------------------------------------------
# A. 规格归一化
# ---------------------------------------------------------------------------

def phase_a() -> None:
    s = spec_of(["P1", "P2", "P1"])
    chk("A1 多选去重且顺序不变", s["change"]["person_ids"] == ["P1", "P2"],
        str(s["change"]["person_ids"]))
    chk("A2 老字段 person_id = 第一个人", s["change"]["person_id"] == "P1")
    chk("A3 一人一槽：person2 打开", s["change"].get("person2") is True
        and s["change"].get("person3") is False)

    # 槽位容量 16（比任何型号上限都宽）：normalize 只受槽位限制，
    # "能换几个"由 subject_gate 按型号判 —— 别在这里再写一个 3。
    s4 = spec_of(["P1", "P2", "P3", "P4"])
    chk("A4 四选四全保留（不再截到 3 人）",
        s4["change"]["person_ids"] == ["P1", "P2", "P3", "P4"],
        str(s4["change"]["person_ids"]))
    chk("A4b 槽位容量 = MAX_PERSONS（16）",
        edit_spec.MAX_PERSONS == 16 and s4["change"]["person4"] is True)

    old = edit_spec.normalize({"change": {"person": True, "person_id": "P2"}})
    chk("A5 老客户端只传 person_id 也能用", old["change"]["person_ids"] == ["P2"])

    off = edit_spec.normalize({"change": {"person": False, "person_ids": ["P1"]}})
    chk("A6 取消勾选就清空名单（不会偷偷换人）", off["change"]["person_ids"] == []
        and off["change"].get("person2") is False)

    bad = edit_spec.normalize({"change": {"person": True,
                                          "person_ids": ["P1", "看起来像人名的字符串"]}})
    chk("A7 非法 id 被丢掉", bad["change"]["person_ids"] == ["P1"],
        str(bad["change"]["person_ids"]))


# ---------------------------------------------------------------------------
# B. 槽位与图号
# ---------------------------------------------------------------------------

def phase_b() -> None:
    s = spec_of(["P1", "P2"], product=True, scene=True)
    # 一个换的人只占一个槽位、只发一张图（2026-10-26，台账 D48）
    order = [x for x, _ in edit_spec.ref_order(s)]
    chk("B1 图号顺序：两个人 → 产品 → 场景（每人一张）",
        order == ["person", "person2", "product", "scene"], str(order))

    idx = edit_spec.image_index(order)
    chk("B2 产品不会顶掉第二个人的图号", idx["product"] == 3 and idx["person2"] == 2,
        json.dumps(idx, ensure_ascii=False))

    only_second = edit_spec.ref_order(spec_of(["P2"]))
    chk("B3 只选一个人时只占一个槽位（不管选的是 P1 还是 P2）",
        only_second == [("person", "file")], str(only_second))

    s3 = spec_of(["P1"])
    kept = video_edit._person_ids_in_slots(s3, ["person", "product"])
    chk("B4 名单对齐真实发出的槽位", kept == ["P1"], str(kept))
    dropped = video_edit._person_ids_in_slots(
        spec_of(["P1", "P2"]), ["person", "product"])
    chk("B5 没传图的第二个人不参与分诊", dropped == ["P1"], str(dropped))


# ---------------------------------------------------------------------------
# C. 提示词
# ---------------------------------------------------------------------------

def phase_c() -> None:
    """提示词段：**只跑点名型号的那一半**（P9 不覆盖 2.0 的提示词写法）。"""
    s = spec_of(["P1", "P2"])
    people = [dict(INV["people"][0], present=True), dict(INV["people"][1], present=True)]
    slots = ["person", "person2"]

    if SEL == "h3":
        h3 = edit_spec.compile_prompt("minimax", s, model="MiniMax-H3",
                                      source_people=people, slots=slots)
        # 🩸 2026-10-24 更新断言：原片里被换的那个人也拿了编号（官方 `ref-en:88`
        # 「参考视频里被复用为可见内容的人仍归在 <Subject N> 下」），所以两个换人
        # 现在占 <Subject 1..4>：目标在第 1/3，原片那位在第 2/4。旧断言还按"一人一个编号"写。
        chk("C8 H3：两个目标主体各绑自己的参考图",
            "<Subject 1> is the person in <Picture 1>" in h3
            and "<Subject 3> is the person in <Picture 2>" in h3)
        chk("C9 H3：两条替换关系各绑各的主体、各自点名原片里的那个人",
            "person (the woman in a red dress) in <Video 1>, and is replaced by <Subject 1>" in h3
            and "person (the man in a blue shirt) in <Video 1>, and is replaced by <Subject 3>" in h3)
        return
    if SEL != "volc25":
        return

    volc = edit_spec.compile_prompt("volc", s, model="doubao-seedance-2-5",
                                    source_people=people, slots=slots)
    chk("C1 火山：两个人各一句「替换为@图片N」",
        volc.count("替换为@图片1中的人物") == 1
        and volc.count("替换为@图片2中的人物") == 1)
    chk("C2 火山：两个人都点名了原片里是哪一位",
        "穿红裙的女生" in volc and "穿蓝衬衫的男生" in volc)
    # 🩸 2026-10-23（D2）：「是替换后人物的唯一身份来源」出处是第三方
    # ReplicaPilot，两家官方说明书都没有 → 已删除。断言改成"不许回来"。
    chk("C3 火山：不写第三方来源的身份锁句", "唯一身份来源" not in volc)
    # 这一组只勾了两个人、没发场景图 → 职责段里不许出现场景那一行
    # （写了就等于提示词指着一张没发出去的图）。
    chk("C4 火山：没传场景图就不写场景职责",
        "用于目标场景的环境和结构" not in volc)
    chk("C5 火山：范围闭环句在（其余人物/道具保持原样）",
        volc.count("除以上明确修改对象外") == 1)

    # 这一刀只有 P1 出现：P2 不许写进去，但后面的图号也不能跟着跳
    half = [dict(INV["people"][0], present=True), {"id": "P2", "present": False}]
    slots3 = ["person", "person2", "product"]
    one = edit_spec.compile_prompt("volc", spec_of(["P1", "P2"], product=True),
                                   model="doubao-seedance-2-5",
                                   source_people=half, slots=slots3)
    chk("C6 缺席的人不写换人句", "穿蓝衬衫的男生" not in one
        and "替换为@图片2中的人物" not in one)
    chk("C7 缺席的人不影响后面图号（产品仍是@图片3）", "@图片3" in one)

    # 不变式：单人路径不许被多人改造带跑
    solo = edit_spec.compile_prompt("volc", spec_of(["P1"]),
                                    model="doubao-seedance-2-5",
                                    source_people=[INV["people"][0]], slots=["person"])
    chk("C10 单人仍然只有一句换人，且不写第三方身份锁",
        solo.count("替换为@图片1中的人物") == 1
        and "唯一身份来源" not in solo
        and "@图片2" not in solo)


# ---------------------------------------------------------------------------
# D. 逐段分诊
# ---------------------------------------------------------------------------

def phase_d() -> None:
    s = spec_of(["P1", "P2"])
    plan = {"spec": spec_of(["P1", "P2"], product=True), "inventory": INV,
            "person_ids": ["P1", "P2"],
            "ch": "volc", "model": "doubao-seedance-2-5", "person_asset": "",
            "audio_ref": False, "prompt": "占位",
            "slots": ["person", "person2", "product"]}
    # 保留原声才有"这一刀干脆不动"这个选项（要重做口型时每段都必须重画）
    s_orig = spec_of(["P1", "P2"])
    s_orig["audio"] = "original"
    plan_orig = dict(plan, spec=s_orig)
    spans = [(0.0, 3.0), (3.0, 5.0), (6.0, 10.0)]
    acts = video_edit._span_plan(plan_orig, spans)

    a0 = acts[spans[0]]
    a1 = acts[spans[1]]
    a2 = acts[spans[2]]
    chk("D1 只有 P1 的段 → 只换 P1",
        a0[0] == "change" and [t["id"] for t in a0[1]] == ["P1"], str(a0[0]))
    chk("D2 两个人都在的段 → 换两个",
        a1[0] == "change" and sorted(t["id"] for t in a1[1]) == ["P1", "P2"])
    chk("D3 一个都不在的段（保留原声）→ 直接留原片", a2[0] == "keep", str(a2[0]))

    p0 = video_edit._span_prompt(plan, a0[1], drop_person=False)
    chk("D4 这一段的提示词只写 P1，P2 的图号不重算",
        "穿红裙的女生" in p0 and "穿蓝衬衫的男生" not in p0 and "@图片3" in p0)

    acts2 = video_edit._span_plan(plan, spans)
    chk("D5 要重做口型时，没人物的段也得重画（不能留原片口型）",
        acts2[spans[2]][0] == "text", str(acts2[spans[2]][0]))

    bad = dict(plan, spec=spec_of(["P9"]), person_ids=["P9"])
    try:
        video_edit._span_plan(bad, spans)
        ok, msg = False, "没有报错"
    except video_edit.EditError as e:  # noqa: PERF203
        ok, msg = "P9" in str(e), str(e)[:60]
    chk("D6 盘点里没有的人 → 出片前拦住，不硬换", ok, msg)


# ---------------------------------------------------------------------------
# E. 界面契约
# ---------------------------------------------------------------------------

def phase_e() -> None:
    vue = (FRONT / "pages" / "clone" / "diagnose.vue").read_text(encoding="utf-8")
    chk("E1 chip 是多选（按名单判断，不是单选比较）",
        "pickedIds.indexOf(p.id) >= 0" in vue and ":class=\"{ on: edit.person_id === p.id }\"" not in vue)
    chk("E2 请求体带 person_ids", "person_ids: []" in vue and "edit: { ...this.edit }" in vue)
    chk("E3 第 2/3 个人各有自己的上传行",
        "extraPeople" in vue and "person${i + 2}" in vue)
    chk("E4 人数上限跟着型号走（不再写死 3 人）",
        "ids.length < cap" in vue and "subjectLimit.max" in vue)
    chk("E5 选了人却没传图 → 提交前拦住", "还没传图" in vue)
    chk("E6 后端接口收 person_ids", "person_ids: list[str]" in
        (ROOT / "app" / "api" / "clone.py").read_text(encoding="utf-8"))
    chk("E7 素材槽位 = edit_spec.SLOT_ORDER（含 person12）",
        "REF_SLOTS = tuple(_SLOT_ORDER)" in
        (ROOT / "app" / "services" / "clone_store.py").read_text(encoding="utf-8")
        and "person12" in edit_spec.SLOT_ORDER)
    chk("E8 超上限给「切到 2.5」的出口", "subjectSwitch" in vue and "切到" in vue)

    # 人物**一人一张**：发出去的就是用户上传的原图，不再派生大头照
    # （2026-10-26 回原文复核 + 实测，台账 D48）。这条防回退：有人再把
    # 「裁大头照排在第一张」加回来，这里立刻红。
    ve = (ROOT / "app" / "services" / "video_edit.py").read_text(encoding="utf-8")
    chk("F1 一人一张：原图直接发，不再裁大头照",
        "out.append((slot, Path(src)))" in ve
        and "_body" not in ve and "head_shot(" not in ve)

    # 型号人数口径（每条都要有官方原文出处，见 model_specs 注释）
    from app.services import model_specs
    if SEL == "volc20":
        chk("F2 2.0 系列 = 4/4（官方：超过 4 人不稳）",
            model_specs.subjects("doubao-seedance-2-0-mini-260615") == (4, 4))
        g = edit_spec.subject_gate(spec_of(["P1", "P2", "P3", "P4", "P5"]),
                                   "doubao-seedance-2-0-mini-260615")
        chk("F5 2.0 选第 5 人 → 拦，并指向 2.5",
            g["level"] == "block" and g["suggest_model"] == "doubao-seedance-2-5-260628")
    elif SEL == "h3":
        chk("F3 H3 = 4/4（与 2.0 对齐）",
            model_specs.subjects("MiniMax-H3") == (4, 4)
            and model_specs.subjects("MiniMax-H3-Max") == (4, 4))
    elif SEL == "volc25":
        chk("F4 2.5 = 8/12（官方：1-8 好，9-12 可尝试）",
            model_specs.subjects("doubao-seedance-2-5-260628") == (8, 12))
        g2 = edit_spec.subject_gate(spec_of([f"P{i}" for i in range(1, 10)]),
                                    "doubao-seedance-2-5-260628")
        chk("F6 2.5 选 9 人 → 只警告（不拦）", g2["level"] == "warn" and g2["message"])
        g3 = edit_spec.subject_gate(spec_of([f"P{i}" for i in range(1, 14)]),
                                    "doubao-seedance-2-5-260628")
        chk("F7 2.5 选 13 人 → 拦（官方可尝试上限 12）", g3["level"] == "block")
    chk("F8 预览把人数判定交给界面", '"subject": gate or {}' in
        (ROOT / "app" / "services" / "clone_pipeline.py").read_text(encoding="utf-8"))

    # 🩸 界面选「默认」时 regen_model 是空串，必须按配置默认型号判人
    # （配置默认 = 2.5，8 人），不能拿空串掉到 2.0 那档把 5–8 人误拦。
    if SEL == "volc25":
        from app.core.config import settings
        from app.services import clone_pipeline
        want = model_specs.subjects(settings.ark_video_edit_model)[0]
        g4 = clone_pipeline._subject_gate(spec_of(["P1", "P2", "P3", "P4", "P5"]),
                                          "volc", "")
        chk(f"F9 选「默认」按配置默认型号判（{settings.ark_video_edit_model} → {want} 人）",
            g4["count"] == 5 and g4["stable"] == want)


# ---------------------------------------------------------------------------

def main() -> int:
    global SEL
    from _model_gate import sel_or_exit
    SEL = sel_or_exit()

    phase_a()
    phase_b()
    phase_c()
    phase_d()
    phase_e()

    ok = sum(1 for _, v, _ in rows if v)
    for name, v, detail in rows:
        mark = "ok  " if v else "FAIL"
        print(f"  {mark} {name}" + (f"  [{detail}]" if detail and not v else ""))
    print(f"\n{ok}/{len(rows)} 通过")
    return 0 if ok == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
