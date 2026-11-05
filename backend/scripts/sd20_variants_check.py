# -*- coding: utf-8 -*-
"""SD20 换人：**写法候选清单**（穷举「有哪些官方写法」，不是伪造组合）。

⚠️ 定位说明（2026-11-05）：
  形态穷举 = `sd20_matrix_check.py`（150 格，真实编译）。
  本脚本**不伪造组合** —— 写法变体大多在编译器里没有分支，文本后处理拼出来的
  是假组合（第一次写就撞上了：T2 与 T1 输出一模一样）。所以这里只做两件事：
    1. 打出每个场景**当前代码真实产出**的提示词；
    2. 列出官方给过、我们**还没用**的写法候选，逐条标出处与真机状态。

只读本地，不联网、不花钱、不出片。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import edit_spec  # noqa: E402

MODEL = "doubao-seedance-2-0-mini-260615"
DESC = [("P1", "left", "浅金色卷发、佩戴细框圆形眼镜的女人"),
        ("P2", "center", "穿灰色布衫、短发的少年"),
        ("P3", "right", "戴眼镜、穿藏青外套的中年男人")]
LOOK = {"zh": "东亚女性、纯黑色顺直中长发、贴身款大U领短袖上衣"}


def build(n_src, n_swap):
    ppl = [{"id": d[0], "present": True, "position": d[1], "desc_zh": d[2]}
           for d in DESC[:n_src]]
    ids = [d[0] for d in DESC[:n_swap]]
    return edit_spec.compile_prompt(
        "volc", edit_spec.normalize({"person": True, "person_ids": ids}),
        model=MODEL, source_people=ppl,
        slots=[edit_spec.PERSON_SLOTS[i] for i in range(n_swap)],
        subject_looks={edit_spec.PERSON_SLOTS[i]: LOOK for i in range(n_swap)},
        desc_by_id={p["id"]: {"zh": p["desc_zh"]} for p in ppl})


print("# 一、当前代码的真实产出\n")
for n_src, n_swap in [(1, 1), (2, 2), (3, 1), (3, 2)]:
    print(f"**原片 {n_src} 人 → 换 {n_swap} 人**\n")
    print("```")
    print(build(n_src, n_swap))
    print("```\n")

print("---\n")
print("# 二、官方给过、我们还没用的写法\n")
print("| # | 写法 | 官方原文/出处 | 用在哪一侧 | 真机状态 |")
print("|---|---|---|---|---|")
print("| N1 | `<主体N>@图片N` | `SKILL.md:14`「未提前定义：`<主体N>@图片N`，"
      "强调主体与素材的绑定关系。例：`张红@图片1`」 | 目标侧 | **从未用过** |")
print("| N2 | `人物A（对应图片N）` | `trouble.md:235` V-7 解法1「提及每一个人物时，"
      "尽量在名字后方标注对应图片，统一采用\"人物名称（对应图片X）\"的格式，"
      "且全程保持格式一致」 | 目标侧 | **从未用过** |")
print("| N3 | 方位点名源对象 | `SKILL.md:153`「`@图片2 中的女生位于画面左侧`」；"
      "`trouble.md:72` 把「多人未指明谁在左/右」列为必须打断的关键歧义 | 源侧 | "
      "代码里多人有方位，单人**从不写** |")
print("| N4 | 只写「面部特征」不写「妆造」 | `trouble.md:173`「面部特征参考 `@图片1`"
      "（大头照），妆造参考`@图片2`（全身照）」+ `:343`「人脸、服装、场景尽量分开"
      "作为独立参考图」 | 参考维度 | 代码写的是「面部特征**和妆造**」 |")
print("| N5 | 「每次出现主体，就提及一次」 | `trouble.md:78` 注意第 1 条 | 全局 | "
      "未专门检查 |")

print("\n---\n")
print("# 三、真机事实（不是推断）\n")
print("| 任务 | 形状 | 提示词特征 | 结果 |")
print("|---|---|---|---|")
print("| `514fae56` / `de591f35` | 2 人换 2，**无标签** | 目标全 `@图片N中的人物`；"
      "源宾语都含服装且都以「黑色长发」开头 | ❌ SFace 17% / 0% |")
print("| `ef232fc6` | 2 人换 2，**有标签 + 参考句** | `<主体1><主体2>` 定义句；"
      "源宾语含服装且互不相同 | ✅ 主人确认「通了」 |")
print("| `60f82aab` | 1 人换 1，**有标签** | 源宾语裸「人物」；单人发 `<主体1>` | "
      "❌ share 0.0 |")
print("\n> 两条 2 人真机的源宾语**都含服装**，差别只在标签 ⇒ 在这组对照里"
      "服装不是决定因素，目标侧的绑定才是。")
