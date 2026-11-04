# -*- coding: utf-8 -*-
"""H3 复刻：**形态矩阵** —— 不是只验一条测试片，是把各种形态都编一遍看输出。

主人 2026-11-04：「没有把所有东西都叠加到一个测试单片上吧？
能准确的灵活运用到任意一个爆款视频上改用到的吧？」

这里覆盖：镜数 × 人数 × 改动类型 × 音轨 × 续接。
只读本地，不联网、不花钱、不出片。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import edit_spec  # noqa: E402

MODEL = "MiniMax-H3"


def people(n, positions=None):
    spots = positions or (["left", "center", "right"] * 2)[:n]
    names = ["穿红裙的女生", "穿蓝衬衫的男生", "戴眼镜的老先生", "卷发的女生"]
    return [{"id": f"P{i+1}", "present": True, "position": spots[i],
             "desc_zh": names[i], "desc_en": f"person {i+1}"} for i in range(n)]


def build(chg, *, ppl=None, frame=None, audio_ref=False, slots_extra=(), **kw):
    ch = chg.get("change") or {}
    # 🩸 槽位必须**跟着改动走**：没勾换人就不该有 person 槽。
    #   上一版无条件给了 person 槽 → 只换场景也被编译成"换人"，
    #   矩阵当场抓出来（B1–B4/D1 全报"非换人却写了运动轨迹"）。
    ppl = ppl if ppl is not None else (people(1) if ch.get("person") else [])
    frame = frame if frame is not None else ppl
    slots = ["person" if i == 0 else f"person{i+1}" for i in range(len(ppl))]
    slots += list(slots_extra)
    spec = edit_spec.normalize(chg)
    return edit_spec.compile_prompt(
        "minimax", spec, model=MODEL,
        source_people=ppl, frame_people=frame, slots=slots,
        audio_ref=audio_ref,
        desc_by_id={p["id"]: {"zh": p["desc_zh"], "en": p["desc_en"]} for p in frame},
        **kw)


ONE = [{"start": 0.0, "end": 5.3, "en": "Medium full shot, two women dance."}]
TWO = [{"start": 0.0, "end": 2.8, "en": "Medium shot, a man walks."},
       {"start": 2.8, "end": 5.4, "en": "Close-up, a woman smiles."}]

CASES = [
    # ---- 换人 ----
    ("A1 单镜 · 1 人", {"change": {"person": True, "person_ids": ["P1"]}},
     dict(ppl=people(1), shot_cuts=[], shot_desc=ONE)),
    ("A2 单镜 · 2 人", {"change": {"person": True, "person_ids": ["P1", "P2"]}},
     dict(ppl=people(2), shot_cuts=[], shot_desc=ONE)),
    ("A3 多镜 · 2 人（有切镜点+两段景别）",
     {"change": {"person": True, "person_ids": ["P1", "P2"]}},
     dict(ppl=people(2), shot_cuts=[2.8], shot_desc=TWO)),
    ("A4 多镜 · 2 人（盘点只给一段景别）",
     {"change": {"person": True, "person_ids": ["P1", "P2"]}},
     dict(ppl=people(2), shot_cuts=[2.8], shot_desc=ONE)),
    ("A5 不知道切镜（shot_cuts=None）",
     {"change": {"person": True, "person_ids": ["P1"]}},
     dict(ppl=people(1), shot_cuts=None, shot_desc=ONE)),
    ("A6 盘点全空（无景别无切点）",
     {"change": {"person": True, "person_ids": ["P1"]}},
     dict(ppl=people(1), shot_cuts=None, shot_desc=[])),
    ("A7 3 人只换 2 个", {"change": {"person": True, "person_ids": ["P1", "P2"]}},
     dict(ppl=people(2), frame=people(3), shot_cuts=[], shot_desc=ONE)),
    ("A8 有音轨", {"change": {"person": True, "person_ids": ["P1"]}},
     dict(ppl=people(1), audio_ref=True, shot_cuts=[], shot_desc=ONE)),

    # ---- 非换人 ----
    ("B1 只换场景", {"change": {"scene": True, "scene_desc": "夜晚的竹林"}},
     dict(shot_cuts=[], shot_desc=ONE)),
    ("B2 只换场景（用图）", {"change": {"scene": True}},
     dict(shot_cuts=[], shot_desc=ONE, slots_extra=("scene",))),
    ("B3 只换产品", {"change": {"product": True, "product_target": "易拉罐",
                            "product_desc": "可口可乐"}},
     dict(shot_cuts=[], shot_desc=ONE)),
    ("B4 只改风格", {"change": {"style": "anime"}}, dict(shot_cuts=[], shot_desc=ONE)),

    # ---- 组合 ----
    ("C1 换人 + 换装", {"change": {"person": True, "person_ids": ["P1"],
                                "wardrobe": True, "wardrobe_ids": ["P1"],
                                "wardrobe_desc_by_id": {"P1": "牛仔外套"}}},
     dict(ppl=people(1), shot_cuts=[], shot_desc=ONE)),
    ("C2 换人 + 换场景", {"change": {"person": True, "person_ids": ["P1"],
                                 "scene": True, "scene_desc": "夜晚的竹林"}},
     dict(ppl=people(1), shot_cuts=[2.8], shot_desc=TWO)),
    ("C3 换人 + 换产品 + 风格", {"change": {"person": True, "person_ids": ["P1"],
                                       "product": True, "product_target": "杯子",
                                       "product_desc": "玻璃杯", "style": "film"}},
     dict(ppl=people(1), shot_cuts=[], shot_desc=ONE)),
    ("C4 换人 + 换场景 + 换装",
     {"change": {"person": True, "person_ids": ["P1"], "scene": True,
                 "scene_desc": "夜晚的竹林", "wardrobe": True,
                 "wardrobe_ids": ["P1"], "wardrobe_desc_by_id": {"P1": "牛仔外套"}}},
     dict(ppl=people(1), shot_cuts=[], shot_desc=ONE)),

    # ---- 边界 ----
    ("D1 什么都没改", {"change": {}}, dict(shot_cuts=[], shot_desc=ONE)),
    ("D2 首帧续接", {"change": {"person": True, "person_ids": ["P1"]}},
     dict(ppl=people(1), shot_cuts=[], shot_desc=ONE, boundary_pic=3)),
]

# 每条都要满足/不能出现的硬项 —— **按任务类型分开**，因为官方就是三套公式。
#   2026-11-04 实测：把 `:133`（换场景）的保留清单套到换人上，脸一个都不换。
#   → 换人只认 `:192` 的两句；保留清单只归换场景。
MUST = {
    # 换人：替换句 + 时间轴 + `:192` 的两句 + `:284` 的追加要求分组
    #   `:142` 的特征维度清单也在 —— 换具体的人必须列维度（`:208`/`:213` 那种
    #   只写替换句的是换通用物，狗长什么样模型自己知道）。
    #   `:284` 全例结尾有「【整体要求补充】」+ `▍` 分组（镜头/人物与动作/画面融合），
    #   这三组是**追加约束**，和上面三段并列（`:244` 的三段是正文）。
    #   `▍镜头` 只在多镜时有（单镜改成「全程一镜到底，不要切镜」），故不列进 MUST。
    "A": ["【核心创意】", "【画面过程说明】", "【整体要求补充】",
          "▍人物与动作（贯穿全片）",
          "运动轨迹", "光影与环境融合", "锁定脸/形象"],
    # 非换人：只锁核心段。换场景那套在下面按 `scene` 现场加（换产品/换风格不写保留清单）
    "B": ["【核心创意】"],
    # 组合：换人不分组（`:244` 三段）；换场景才由下面按 scene 现场加 `:133` 那套
    "C": ["【核心创意】"],
}
#: 换人路径**不许**出现的句子 —— 这些是 `:133` 换场景的公式，搬过来会把脸按住
PERSON_NEVER = ["必须保持 100% 不变", "不要重新生成一个新场景", "大小和透视"]
NEVER = ["原片画面", "固定机位", "唯一编辑母版", "其他人物、道具和背景保持原样",
         "subject_definitions", "retention_analysis", "非叙事性音乐"]

bad = 0
for name, chg, kw in CASES:
    slots_extra = kw.pop("slots_extra", ())
    try:
        m = build(chg, slots_extra=slots_extra, **kw)
    except Exception as e:                                   # noqa: BLE001
        print(f"✗ {name}  ← 抛异常 {type(e).__name__}: {e}")
        bad += 1
        continue

    tag = name[0]
    ch_ = chg.get("change") or {}
    miss = [w for w in MUST.get(tag, MUST["A"]) if w not in m]
    # 换场景才要求 `:133` 那套（融合五项 + 保留清单）
    if ch_.get("scene"):
        miss += [w for w in ("▍场景融合（贯穿全片）", "100% 不变")
                 if w not in m]
    # 盘点全空 = 没有任何时间轴数据 → 整段跳过是对的（`:248`「没有素材时整段跳过」），
    # 不许为了凑格式编空壳。
    if name.startswith("A6"):
        miss = [w for w in miss if w != "【画面过程说明】"]
    if name.startswith("D1"):
        # 什么都没改 = 上游本该拦下。这里只要求：不编改动句、不编保留清单。
        miss = []
        ch = chg.get("change") or {}
        if "换成" in m or "替换为" in m:
            leak = ["没有改动却写了改动句"]
    leak = [w for w in NEVER if w in m]
    # 空壳：有组名没内容
    hollow = [ln for ln in m.splitlines()
              if ln.startswith("▍") and m.split(ln)[-1].splitlines()[0].strip().startswith("▍")]
    # 换人时才该有的句子
    person_only = [w for w in ("运动轨迹", "人物替换", "替换后的人物") if w in m]
    if "person" not in (chg.get("change") or {}) and person_only:
        leak += [f"非换人却写了「{w}」" for w in person_only]
    # 🩸 换人路径**不许**带 `:133` 换场景那套（保留清单 / 透视匹配 / 禁止新场景）——
    #   2026-11-04 实测：带上之后两张脸一个都没换。
    #   但同时勾了换场景的，`:133` 那套是**该在**的（场景任务自己要用），不算串。
    if ch_.get("person") and not ch_.get("scene"):
        leak += [f"换人却串了换场景的「{w}」" for w in PERSON_NEVER if w in m]

    ok = not miss and not leak and not hollow
    print(f"{'✓' if ok else '✗'} {name}")
    if miss:
        print(f"    缺：{miss}")
    if leak:
        print(f"    多：{leak}")
    if hollow:
        print(f"    空壳标题：{hollow}")
    if not ok:
        bad += 1

print(f"\n{len(CASES) - bad}/{len(CASES)} 形态通过")
sys.exit(1 if bad else 0)
