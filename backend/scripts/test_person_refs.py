"""人物参考图：**每个通道按自己的官方规则发图**，别拿一套打全平台。

三家统一：**顾客只传一张标准人物参考图**（2026-10-26 回原文复核，台账 D48）。
  · Seedance 2.0 —— `sd2-pe:66`「角色图 **1–2**（大头照 + 全身照）」= 一张合规；
    官方实战案例 `sd20-guide:222` 就是「@图片 1：女主半身照」一张打全片；
    `sd20-guide:414`「人物参考图**优先使用单人独立照片**」。
    「大头照 + 全身照」只出现在 `sd20-guide:305`「人脸参考**不准确**」这一**问题章节**
    （现象→根因→解决方案），是**补救增强**，不是默认配置。
  · Seedance 2.5 —— `sd25-pe` + `seedance-25-guide.md` **全文没有"大头照/全身照"**；
    它的写法是**一人一图、每张写全属性**（`sd25-pe:227`「只采用五官、发型和服装」，
    `:472` / `:948` 同形），多图只用于**多视角**（`:456` 正面/左侧/右侧/背面）。
    所以 2.5 = **一张**。
  · MiniMax H3 —— 官方也没有「大头照 + 全身照」这条，= 一张。
    🩸 `ref-en:48`「One subject **may** be defined by multiple reference assets」
    是**许可**不是**要求**；`:313` 官方示例用三张图定义同一只狗，也没规定分工。
    「大头照管脸 + 全身照管妆造」是 2.0 的规则，**不许搬过来**（2026-10-26 复核）。
  · 静帧重绘（图生图，不传型号）—— 同上，一张。

🩸 2026-10-25 实测（任务 `2f1f26d8` / 出片 `0c656558`，2.5，双人换人 + 换装）：
  · 两张拆分图那位（图片1 管五官和发型 / 图片2 管服装和配饰）：
    **从头到尾没换脸** —— SFace 与参考图 0.19–0.36、与原片 0.44–0.64（同人线 0.363）；
  · 一张全属性那位（`五官、发型和服装`）：0.37–0.62，**换成了**。
  ⇒ 把 2.0 的大头照分工搬进 2.5 就是这次的根因。

判据（成对给正反样本）：
  1. 三家都**只有一个槽位**，发的就是用户传的那张图本身（不裁、不派生）
  2. 提示词里的图号只在 1..N 之间，不出现没发出去的图
  3. 2.0 的面部与妆造都指同一张；2.5 写全属性「五官、发型和服装」（`:227`）
  4. 火山素材 ID → 没有本地图，也不追加别的
  5. 图号必须和实际发出去的一致

运行：python scripts/test_person_refs.py --model volc20|volc25|h3
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import edit_spec, video_edit  # noqa: E402

PASS = FAIL = 0
TMP = Path(tempfile.mkdtemp(prefix="personrefs_", dir="D:/tmp"))

V20 = "doubao-seedance-2-0-260128"
V25 = "doubao-seedance-2-5-260628"
H3 = "MiniMax-H3"


def check(name: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {name}: {got!r}")
    else:
        FAIL += 1
        print(f"  FAIL {name}: got={got!r} want={want!r}")


def check_true(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


def plan_for(spec: dict, refs: dict, *, channel: str = "volc",
             model: str = V20) -> tuple[list[str], list[object]]:
    items = video_edit.ref_plan(edit_spec.normalize(spec), refs,
                                channel=channel, model=model)
    return [s for s, _ in items], [p for _, p in items]


def prompt_for(ch: str, slots: list[str], *, model: str = V20,
               chg: dict | None = None) -> str:
    return edit_spec.compile_prompt(
        ch, edit_spec.normalize(chg or {"person": True}),
        model=model, slots=slots)


def main() -> int:
    from _model_gate import sel_or_exit
    sel = sel_or_exit()
    orig = TMP / "subject.jpg"
    orig.write_bytes(b"ORIGINAL")

    if sel == "volc20":
        # 🩸 2026-10-26 定案**一张**。回原文逐句核过（台账 D48）：
        # `sd2-pe:66`「角色图 **1–2**」、`sd20-guide:222` 官方案例就是「女主半身照」一张；
        # 「大头照 + 全身照」只在 `sd20-guide:305`「人脸参考**不准确**」这一**问题章节**
        # 里作为补救出现，不是默认配置（`sd20-guide:414` 还写明「优先使用单人独立照片」）。
        print("== 2.0：默认一张（顾客只传一张）==")
        slots, paths = plan_for({"person": True}, {"person": orig})
        check("2.0 只有一个槽位", slots, ["person"])
        check_true("发的就是原图（不自动裁大头照）", Path(paths[0]) == orig, str(paths[0]))
        p20 = prompt_for("volc", slots)
        # 🩸 2026-10-30：职责句改成**前置**的一整句「参考@图片N中…的面部特征和妆造」
        #   （官方 `sd20-guide:59-65` 组合任务句式：参考分句排在「严格编辑」之前）。
        check_true("2.0 一张图时面部与妆造都指图片1",
                   "参考@图片1中人物的面部特征和妆造" in p20, p20)
        check_true("2.0 不出现第二张人物图", "@图片2" not in p20, p20)

    if sel == "volc25":
        print("== 2.5：同一张图**不派生**，只发原图（官方无大头照这条）==")
        slots25, paths25 = plan_for({"person": True}, {"person": orig}, model=V25)
        check("2.5 只有一个槽位", slots25, ["person"])
        check_true("发的就是原图（没有 subject_head）", Path(paths25[0]) == orig,
                   str(paths25[0]))
        p25 = prompt_for("volc", slots25, model=V25)
        check_true("2.5 职责写全属性（`sd25-pe:227`）",
                   "@图片1用于目标人物的五官、发型和服装" in p25, p25)
        check_true("2.5 不出现第二张人物图", "@图片2" not in p25, p25)
        check_true("2.5 不用 2.0 的词「妆造」（全文 0 次）", "妆造" not in p25, p25)
        check_true("2.5 不写「面部特征参考」（那是 2.0 的句式）",
                   "面部特征参考" not in p25, p25)

    if sel == "h3":
        # 🩸 2026-10-26 复核：**H3 官方没有「大头照 + 全身照」这条**。
        # `ref-en:48`「One subject **may** be defined by multiple reference assets」
        # 是许可不是要求；`:313` 的官方示例用三张图定义同一只狗，也没规定分工。
        # 「大头照管脸 + 全身照管妆造」出自 Seedance 2.0
        # （`seedance-20-guide.md:316-317` / `sd2-pe:139`），**不能搬到 H3**。
        print("== H3：不派生（官方无「大头照 + 全身照」这条）==")
        slots_h3, paths_h3 = plan_for({"person": True}, {"person": orig},
                                      channel="minimax", model=H3)
        check("H3 只有一个槽位", slots_h3, ["person"])
        ph3s = prompt_for("minimax", slots_h3, model=H3)
        check_true("H3 只有 <Picture 1>", "<Picture 1>" in ph3s and "<Picture 2>" not in ph3s,
                   ph3s)

    print("== 静帧重绘（不传型号）：只发原图 ==")
    items_st = video_edit.ref_plan(edit_spec.normalize({"person": True}),
                                   {"person": orig})
    check("静帧路径只有一个槽位", [s for s, _ in items_st], ["person"])

    if sel == "volc20":
        # 🩸 原来的「自拍/证件照」和「裁脸失败」两段随派生逻辑一起删了 ——
        # 派生不存在的今天，那两个场景和普通上传走的是同一条路，
        # 留着只会让人以为还有别的分支（对空判据恒真）。
        print("== 火山素材 ID：没有本地图，也不追加 ==")
        items4 = video_edit.ref_plan(edit_spec.normalize({"person": True}),
                                     {"person": orig}, subject_asset="asset-9",
                                     channel="volc", model=V20)
        check("素材 ID 只有一个槽位", [s for s, _ in items4], ["person"])

    p2 = TMP / "ref_person2.jpg"
    p2.write_bytes(b"P2")

    if sel == "volc20":
        print("== 双人：每人一张（图号按人依次排）==")
        slots5, _ = plan_for({"person": True, "person2": True,
                              "person_ids": ["P1", "P2"]},
                             {"person": orig, "person2": p2})
        check("2.0：两人各一张", slots5, ["person", "person2"])
        pr5 = prompt_for("volc", slots5)

        # 🩸 判据按**效果**写，不锁字面（2026-10-25：多人改用官方 `<主体N>` 指代，
        # 原句「面部特征参考@图片1中的人物」变成「<主体1>的面部特征参考@图片1」）。
        # 关心的是"第 1 位的脸和妆造都指图片1、第 2 位都指图片2"。
        def _duty(prompt: str, face_pic: str) -> str:
            """取「指向 face_pic 的那一小句」（按 ； 切，别被别的分句干扰）。"""
            for seg in prompt.split("；"):
                if "面部特征" in seg and re.search(rf"参考{face_pic}(?!\d)", seg):
                    return seg
            return ""

        seg1 = _duty(pr5, "@图片1")
        check_true("第 1 位：面部与妆造都→图片1",
                   bool(re.search(r"参考@图片1中[^，]*的面部特征和妆造", seg1)), pr5)
        seg2 = _duty(pr5, "@图片2")
        check_true("第 2 位：面部与妆造都→图片2",
                   bool(re.search(r"参考@图片2中[^，]*的面部特征和妆造", seg2)), pr5)
        check_true("双人：不出现第三张图", "@图片3" not in pr5, pr5)

        # 🩸 2026-10-26 19:xx：原来这三条锁的是
        #   「将@图片1中的人物定义为<主体1>」+「替换为<主体1>」——
        # 那个定义句**零静态特征**，违反 `sd20-guide:95`（2–3 个清晰稳定的静态特征），
        # `ruler_sd20` 的 R06 一直黄着，18:xx 已从编译器里删掉。
        # 而且参考图没有盘点描述时，我们**写不出**特征 ⇒ 定义句本来就该缺席。
        # 「图没有归属」这个风险改由**图号**承担：每句换人句自带自己的 @图片N。
        check_true("双人：两句各绑各的图（不跨句查标签）",
                   ("替换为@图片1中的人物" in pr5
                    and "替换为@图片2中的人物" in pr5), pr5)
        check_true("双人：不出现悬空标签（有 <主体N> 必有定义）",
                   not re.search(r"<主体\d>", pr5) or "定义为<主体" in pr5, pr5)

        # 成对：单人**不许**冒出主体定义（单人无指代歧义，现状 2/2 已验证，不动）
        pr1 = prompt_for("volc", plan_for({"person": True, "person_ids": ["P1"]},
                                          {"person": orig})[0])
        check_true("单人：不写 <主体N> 定义", "定义为<主体" not in pr1, pr1)

        print("== 5 个人：一人一张，不再顶参考图上限 ==")
        many = {f"person{i}" if i > 1 else "person": TMP / f"p{i}.jpg" for i in range(1, 6)}
        for k, pth in many.items():
            pth.write_bytes(b"X")
        slots_cap, _ = plan_for(
            {k: True for k in many} | {"person_ids": ["P1", "P2", "P3", "P4", "P5"]},
            many)
        check_true("5 个人只占 5 个槽位（没有派生图）",
                   len(slots_cap) == 5, str(len(slots_cap)))

    if sel == "volc25":
        slots5b, _ = plan_for({"person": True, "person2": True,
                               "person_ids": ["P1", "P2"]},
                              {"person": orig, "person2": p2}, model=V25)
        check("2.5：两人各一张（没有派生槽）", slots5b, ["person", "person2"])

    print(f"\n{PASS}/{PASS + FAIL} 通过")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
