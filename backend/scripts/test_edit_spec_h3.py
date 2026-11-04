# -*- coding: utf-8 -*-
"""MiniMax H3 的提示词自检 —— **手写入口三段式**（2026-11-03 换体裁）。

由 `test_edit_spec.py --model h3` 调用；共用规则在 `test_edit_spec_common.py`。
不联网、不花钱。

🩸 **为什么整份重写**：旧版判的是 Ref2VA 六段式（`subject_definitions` …），
而官方**换人样例 6 条全在手册**（`h3-manual:207-213` / `:185-192`），
六段式里**一条都没有**。体裁换了，断言必须跟着换（`spec-must-match-genre`）。
旧版归档在 `_archive/h3_clone/test_edit_spec_h3_ref2va.py`。

每条断言后面标官方行号，判据不是"我觉得对"，是"官方这么写"。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import edit_spec  # noqa: E402
from test_edit_spec_common import check  # noqa: E402

MODEL = "MiniMax-H3"
LABEL = "MiniMax H3（手写入口）"


def _people(n: int, positions: list[str] | None = None) -> list[dict]:
    spots = positions or ["left", "right", "center"][:n]
    names = ["穿红裙的女生", "穿蓝衬衫的男生", "戴眼镜的老先生"]
    return [{"id": f"P{i + 1}", "present": True, "position": spots[i],
             "desc_zh": names[i % len(names)],
             "desc_en": f"person {i + 1}"} for i in range(n)]


def _build(chg: dict, *, people=None, frame=None, slots_extra=(),
           audio_ref=False) -> str:
    """编一条手写入口提示词。`people` = 被换的，`frame` = 整个画面的人。"""
    people = people if people is not None else _people(1)
    frame = frame if frame is not None else people
    slots = ["person" if i == 0 else f"person{i + 1}" for i in range(len(people))]
    slots += list(slots_extra)
    spec = edit_spec.normalize(chg)
    return edit_spec.compile_prompt(
        "minimax", spec, model=MODEL,
        source_people=people, frame_people=frame, slots=slots,
        audio_ref=audio_ref,
        desc_by_id={p["id"]: {"zh": p["desc_zh"], "en": p["desc_en"]}
                    for p in frame})


def run() -> None:
    print("== MiniMax H3（手写入口）==")

    # ---------------------------------------------------------------- 结构
    # 官方 `h3-manual:244`：完整提示词 = 参考素材说明 + 核心创意 + 画面过程说明
    one = _build({"change": {"person": True, "person_ids": ["P1"]}}, audio_ref=True)
    check("有【参考素材说明】段（h3-manual:244）", "【参考素材说明】" in one, True)

    # 官方 `h3-manual:248`：写清每个素材的用途
    check("用官方词「人物参考」（h3-manual:248 + :284 冒号式）", "：人物参考" in one, True)
    check("用官方词「视频编辑」（h3-manual:248 + :284 冒号式）", "：视频编辑素材" in one, True)
    check("用官方词「音频复用」（h3-manual:248 + :284 冒号式）", "：音频复用素材" in one, True)

    # 官方 `h3-manual:213`：视频1中最后面的小孩换成 图1中的金毛狗
    check("点名「谁换成谁」（h3-manual:213）", "@图片1中的人物" in one, True)
    check("有替换动词「换成」（h3-manual:213 原词）",
          "换成@图片1中的人物" in one, True)

    # 官方 `:142`：「使用图2作为严格的角色身份参考。请保持同一个角色**脸、发型、
    #   体型比例、服装设计、材质细节**…一致」——换**具体的人**时必须列维度。
    #   对照 `:208`/`:213`/`:192`：那三条换成的是**通用物**（狗/水豚/书），
    #   「狗」自带长相，所以只写替换句就够；人不自带，不列维度模型只会换脸或换衣。
    # 🩸 **核心创意只点名「谁换成谁」，不写维度清单**（`:213` 编辑案例的原形）。
    #   `:142` 那套「脸、发型、体型比例、服装设计、材质细节…一致」出自乙游男主 PV
    #   （**创作**任务）。维度和特征在【参考素材说明】里用 `:248`「锁定脸/形象」
    #   + 描述说一次就够了；两处都写 = 一具体一抽象，模型照具体的执行，
    #   于是"换人"变成"换衣服"。
    check("维度句在、且绑定本人图号（h3-manual:142）",
          "脸、发型、体型比例、服装设计和材质细节与@图片1保持一致" in one, True)
    check("维度不合并成多图一句（否则对应关系丢失）",
          "与@图片1、@图片2保持一致" not in one, True)
    # 🩸 这句必须指向**参考图**。v5 把 `:133` 的保留清单指向**原片**（「必须保持
    #   100% 不变」），实测把脸按死、一帧不换。方向反了就前功尽弃。
    check("维度清单指向参考图、不指向原片",
          "与@视频1" not in one and "与原视频" not in one, True)

    # 官方 `h3-manual:192` 逐字：「必须严格遵循原视频的运动轨迹」
    check("逐字保有句「运动轨迹」（h3-manual:192）", "运动轨迹" in one, True)
    # 🩸 2026-11-04 反转：`:192` 那句「保持原有的固定机位不变」是贴着**它自己的源片**
    #   说的（该案例源片就是固定机位）。复刻源片普遍有切镜 → 抄这句等于禁止切镜，
    #   真跑把两镜压成一镜到底。现在锁「不许有」。
    check("不写「固定机位」（切镜源片会因此不切镜）", "固定机位" in one, False)
    check("逐字融合句（h3-manual:192）", "质感和光影与环境融合" in one, True)

    # ---------------------------------------------------------------- 音轨
    no_audio = _build({"change": {"person": True, "person_ids": ["P1"]}},
                      audio_ref=False)
    check("无音轨时不写 @音频1", "@音频1" in no_audio, False)

    # ---------------------------------------------------------------- 多人
    two = _build({"change": {"person": True, "person_ids": ["P1", "P2"]}},
                 people=_people(2), audio_ref=True)
    check("双人：两张图都有用途", two.count("：人物参考"), 2)

    # 用户只换左右两人 —— 两条**不同**的规则，别混为一谈（2026-11-04 分清的）：
    #   ① 「**不点名**某个没被换的人」（不说"画面右下的女生保持原样"）—— 仍然成立。
    #      `:213` 只点名要改的；而且点名一个没被换的人，模型反而可能去动它。
    #   ② 「写**保留清单**」（镜头运动 / 动作时序 / 其他元素位置 / 光照 100% 不变）
    #      —— `:133` 原文就是这么写的，`:206` 总纲「保持未编辑内容相对稳定」。
    #      这两条不冲突：②不指名任何具体的人，只说"除了被替换的，其余维度别漂"。
    # 🩸 以前误以为「官方没写别动 → 什么都不写」，那是只扫了第三章漏了 1.8 的 `:133`。
    three = _people(3)
    pair = _build({"change": {"person": True, "person_ids": ["P1", "P2"]}},
                  people=[three[0], three[1]], frame=three, audio_ref=True)
    check("不点名某个没换的人（h3-manual:213 无此句式）",
          "保持原样" not in pair and "都按@视频1原样" not in pair, True)

    # 🩸 2026-11-04 实测**反转**（真跑对照，同一任务同一素材）：
    #     v4 `93dbec8f` = 只有 `:192` 两句          → 前半段两张脸**都换成了**
    #     v5 `f2825696` = 加了 `:133` 保留清单等     → **每一帧都"没换"**
    #   `:133` 的标题是「精准替换**场景背景**」，那套是换背景的公式（背景换、人别动）。
    #   换人反过来（人换、背景别动），强行搬过去会把人也按住。
    #   → 换人路径现在锁「这些句子**不许有**」。
    for w in ("必须保持 100% 不变", "大小和透视", "不要重新生成一个新场景",
              "景深虚化", "空间纵深感", "自然承接原视频的光影投射",
              "高光方向与原场景光源严格一致"):
        check(f"换人不串换场景公式「{w}」", w in pair, False)

    # 🩸 2026-11-04 实测：盘点只给 1 个 shot、切片器却报切点时，**不许补「切镜」句**。
    #   `93dbec8f` / `c8455a93` 带了这句 → 第二镜整段搬来 @图片2 的夜晚庭院。
    #   主人肉眼确认源片确实是一个镜头（`camera slowly pulls back`），切片器被骗。
    #   `:251`「以切镜 shot 作为时间戳的分段」→ 盘点一个 shot 就不分段。
    _one_spec = edit_spec.normalize({"change": {"person": True, "person_ids": ["P1"]}})
    _one_ppl = _people(1)
    _one_m = edit_spec.compile_prompt(
        "minimax", _one_spec, model=MODEL,
        source_people=_one_ppl, frame_people=_one_ppl, slots=["person"],
        audio_ref=False,
        desc_by_id={p["id"]: {"zh": p["desc_zh"], "en": p["desc_en"]}
                    for p in _one_ppl},
        shot_cuts=[3.33],
        shot_desc=[{"start": 0.0, "end": 5.3, "en": "Medium full shot."}])
    check("盘点 1 个 shot → 不补切点（否则第二镜搬参考图场景）",
          "切镜" not in _one_m, True)

    # 🩸 官方原词是「人物参考（**锁定脸/形象**）」——`脸` 和 `形象` **两个词**
    #   （`:248` 素材用途表）。只写「锁定…脸」会让后面的耳饰、气质、发型变成
    #   没有归属的噪音（它们不是"脸"，是"形象"）。描述照 `:248`「如果素材中有
    #   非常想要保持的特征，建议明确写出来」完整保留。
    _look = {"person": {"zh": "鹅蛋脸，柔长眼型；气质明艳；深棕黑色蓬松大波浪长卷发；"
                              "单肩露肤修身收腰高开叉层叠薄纱拖尾礼服；身形高挑纤瘦修长",
                        "en": ""}}
    _lo = edit_spec.compile_prompt(
        "minimax", edit_spec.normalize({"change": {"person": True, "person_ids": ["P1"]}}),
        model=MODEL, source_people=_people(1), frame_people=_people(1),
        slots=["person"], audio_ref=False,
        desc_by_id={p["id"]: {"zh": p["desc_zh"], "en": p["desc_en"]}
                    for p in _people(1)},
        subject_looks=_look)
    check("用途句用官方原词「锁定脸/形象」（h3-manual:248）",
          "锁定脸/形象" in _lo, True)
    check("用途句保留完整特征（h3-manual:248 建议明确写出来）",
          "礼服" in _lo and "长卷发" in _lo, True)

    # 换场景时 `:133` 那套**必须回来**（这才是它原本的用途）
    sc = _build({"change": {"scene": True, "scene_desc": "夜晚的竹林"}}, people=[])
    check("换场景 → 融合五项在（h3-manual:133）",
          "景深虚化程度与原视频焦点对齐" in sc, True)
    check("换场景 → 保留清单在（h3-manual:133）", "必须保持 100% 不变" in sc, True)

    # 方位撞车 → 必须退回外貌指代，不能两个都写「画面左侧」
    dup = _build({"change": {"person": True, "person_ids": ["P1", "P2"]}},
                 people=_people(2, ["left", "left"]), audio_ref=True)
    check("同方位时退回外貌指代", dup.count("画面左侧的人物"), 0)

    # ---------------------------------------------------------------- 不串味
    for w in ("唯一编辑母版", "其他人物、道具和背景保持原样",
              "subject_definitions", "retention_analysis"):
        check(f"不串「{w}」", w in one, False)

    # ---------------------------------------------------------------- 其他改动类
    # 换装：官方 `h3-manual:213`「最左边小孩穿的卡其色外套改成图2中的牛仔外套」
    wd = _build({"change": {"person": True, "person_ids": ["P1"],
                            "wardrobe": True, "wardrobe_ids": ["P1"],
                            "wardrobe_desc_by_id": {"P1": "牛仔外套"}}})
    check("换装有落点", "牛仔外套" in wd, True)
    # 勾了换装的人，服装由换装句决定 —— 维度清单里再要求服装跟参考图走，
    # 两句会正面打架（`_wardrobe_pairs()` 说改成牛仔外套，清单说跟@图片1一致）。
    check("换装的人维度清单去掉「服装设计」",
          "服装设计和材质细节" in wd, False)

    # 换产品：官方 `h3-manual:234`「将…易拉罐饮料替换为可口可乐」
    pd = _build({"change": {"product": True, "product_target": "易拉罐",
                            "product_desc": "可口可乐"}})
    check("换产品有落点", "可口可乐" in pd, True)

    # 换场景：官方 `h3-manual:221`「视频1窗外的场景改成图1」
    sc = _build({"change": {"scene": True, "scene_desc": "带百叶窗的办公室工位"}})
    check("换场景有落点", "百叶窗" in sc, True)

    # 风格：官方 `h3-manual:248`「风格参考（根据图片的风格…）」
    # 🩸 `style` 是枚举键不是自由文本（`edit_spec.STYLES`），传别的会被 normalize 清空。
    st = _build({"change": {"style": "anime"}})
    check("换风格有落点", "动漫" in st, True)

    # 补充说明：官方 `h3-manual:248`「以及其他要求也可按需写明」
    # 🩸 `extra` 在 spec **顶层**，不在 `change` 里（`edit_spec.py:208/342`）
    #   —— 塞进 change 里会被 normalize 丢掉，那是用例喂错形状，不是产品 bug。
    ex1 = _build({"person": True, "person_ids": ["P1"],
                  "extra": "画面不显示字幕。"})
    check("补充说明有落点", "不显示字幕" in ex1, True)

    # ---------------------------------------------------------------- 上限
    # 官方 `h3-manual:41`：提示词 ≤7000 字符
    check("不超过 7000 字符（h3-manual:41）", len(one) <= 7000, True)
