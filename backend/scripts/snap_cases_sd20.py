# -*- coding: utf-8 -*-
"""火山 Seedance 2.0 的快照用例（**只放 2.0**，别家不许进这个文件）。

形状一律是生产形状：`ppl` 只含勾选的人，`frame_people` 才是整个画面
（`video_edit._span_people` 就是这么传的）。
"""
from __future__ import annotations

from snap_cases_common import LINES, M20, P1, P1L, P2, P2R

MODEL = "volc20"
LABEL = "火山 2.0"


# 真实盘点原文（`data/clone/494b1c28…/inventory/dc4a7e41…json` 逐字抄的）
_R1 = {"id": "P1", "present": True, "position": "center",
       "desc_zh": "留短黑发，佩戴黑框眼镜，身穿藏蓝色带白色字母印花、红格纹连帽内衬的外套，"
                 "内搭黑色上衣的男性"}
_R2 = {"id": "P2", "present": True, "position": "right",
       "desc_zh": "留短黑发，身穿黑色短袖高领上衣，搭配深色长裤配腰带的男性"}


_R3 = {"id": "P3", "present": True, "position": "left",
       "desc_zh": "留短寸发型，身穿黑色长袖上衣的男性"}

# 参考图那个人（`subject_desc.json` 的 `desc_zh`，2026-10-26 那条真实素材逐字抄）
_LOOK = {"zh": "短款黑色直发，圆润脸型，胸前带有同色压印“HAIRVERS”字样的"
               "黑色圆领短袖T恤",
         "en": ""}


def _did(*ps):
    """生产形状里 `video_edit` **一定**传 `desc_by_id`（盘点结果）。
    🩸 2026-10-26：之前这几个用例没传，快照里「双人只换一个」**不含双胞胎兜底**，
    而生产形状含 —— 用例失真会让人把"基线绿"当成"生产对"。"""
    return {x["id"]: {"zh": x["desc_zh"], "en": ""} for x in ps}


# (名字, 通道, 型号, 勾选, 勾选的人, 槽位, 额外参数)
CASES: list[tuple] = [
    ("20 单人", "volc", M20, {"person": True, "person_ids": ["P1"]},
     [P1], ["person"], {"frame_people": [P1]}),
    # 🩸 2026-10-26 删掉「20 单人双图」：一个换的人只有一张图（台账 D48），
    # `person_body` 槽生产上永远不出现 —— 留着等于给死分支冻结基线。
    ("20 双人只换一个（同方位）", "volc", M20,
     {"person": True, "person_ids": ["P1"]}, [P1], ["person"],
     {"frame_people": [P1, P2], "desc_by_id": _did(P1, P2)}),
    ("20 双人只换一个（方位唯一）", "volc", M20,
     {"person": True, "person_ids": ["P1"]}, [P1L], ["person"],
     {"frame_people": [P1L, P2R], "desc_by_id": _did(P1, P2)}),
    # 🩸 2026-10-26 18:xx：**真实盘点形状**（`494b1c28` 原文）。上面的用例描述
    # 都以人称名词收尾（「体型偏胖的男子，…」），`_feat_phrase` 直接原样返回，
    # **根本走不到"服饰在后面的分句里"这条路** —— 快照 12/12 在截断 bug 修掉前
    # 后一个字节都没变，等于这条路没人守。留一条真实的。
    ("20 双人只换一个（真实盘点·服饰在后段）", "volc", M20,
     {"person": True, "person_ids": ["P1"]}, [_R1], ["person"],
     {"frame_people": [_R1, _R2], "desc_by_id": _did(_R1, _R2)}),
    # 🩸 2026-10-26 19:xx：参考图里的人以前**从来没有被定义成主体** ——
    # 上面所有用例的 `ppl` 都只有盘点结果，没有 `subject_look`，所以这条
    # 修复在 13/13 全绿的快照里一个字节都看不出来。补两条（多人 / 单人各一），
    # 把「将@图片1中<特征>定义为<主体1>…将其中的<主体2>替换为<主体1>」冻住。
    ("20 三人·只换一个·带素材描述", "volc", M20,
     {"person": True, "person_ids": ["P1"]}, [_R1], ["person"],
     {"frame_people": [_R1, _R2, _R3], "desc_by_id": _did(_R1, _R2, _R3),
      "subject_look": _LOOK}),
    ("20 单人·带素材描述", "volc", M20,
     {"person": True, "person_ids": ["P1"]}, [P1], ["person"],
     {"frame_people": [P1], "subject_look": _LOOK}),
    ("20 双人全换", "volc", M20,
     {"person": True, "person_ids": ["P1", "P2"]}, [P1, P2],
     ["person", "person2"],
     {"frame_people": [P1, P2], "desc_by_id": _did(P1, P2)}),
    ("20 单人+产品", "volc", M20,
     {"person": True, "product": True, "person_ids": ["P1"]},
     [P1], ["person", "product"], {"frame_people": [P1]}),
    ("20 单人+切点", "volc", M20, {"person": True, "person_ids": ["P1"]},
     [P1], ["person"], {"frame_people": [P1], "shot_cuts": [3.0, 6.9]}),
    ("20 双人+换装", "volc", M20,
     {"person": True, "wardrobe": True, "person_ids": ["P1"],
      "wardrobe_ids": ["P1"]},
     [P1], ["person", "wardrobe"],
     {"frame_people": [P1, P2], "desc_by_id": _did(P1, P2)}),
    # 以下两条锁 D29 的两处修正（都在「多人画面」下才触发）
    ("20 双人·换配音（说话人没点名→只带音色）", "volc", M20,
     {"person": True, "audio": "tts", "person_ids": ["P1"]},
     [P1], ["person"],
     {"frame_people": [P1, P2], "audio_ref": True, "shot_lines": LINES,
      "desc_by_id": _did(P1, P2)}),
    ("20 双人·风格枚举词（动漫）", "volc", M20,
     {"person": True, "style": "anime", "person_ids": ["P1"]},
     [P1], ["person"],
     {"frame_people": [P1, P2], "desc_by_id": _did(P1, P2)}),
    # 🩸 锁 2026-10-26 的 R24 修复：第二个人（没被换的那位）说话时，指代必须是
    # 「@视频1中年轻女子」这种名词短语，不许把整段外观接动词 —— 修之前会拼成
    # 「年轻女子，黑色长发梳成古装高髻，身着广袖古装使用@音频1的音色说{别找我}」。
    # 🩸 2026-10-26 补两条**原声模式**：15:48 那条真机失败就跑在这条路上，
    # 而它此前**没有任何快照基线** —— 我删掉「@音频1是@视频1的原片音轨，
    # 原样保留在成片中」这句时，快照 10/10 一条都没响，等于这条路没人守。
    # 现在把「保留原声时一个字都不提音轨」冻下来（2.0 依据：`:31` 未提及默认不变）。
    ("20 单人·原声（不提音轨）", "volc", M20,
     {"person": True, "audio": "original", "person_ids": ["P1"]},
     [P1], ["person"], {"frame_people": [P1], "audio_ref": True}),
    ("20 双人·原声（不提音轨）", "volc", M20,
     {"person": True, "audio": "original", "person_ids": ["P1"]},
     [P1], ["person"],
     {"frame_people": [P1, P2], "audio_ref": True, "desc_by_id": _did(P1, P2)}),
    ("20 双人·两句各说一句（第二人是没换的那位）", "volc", M20,
     {"person": True, "audio": "tts", "person_ids": ["P1"]},
     [P1], ["person"],
     {"frame_people": [P1, P2], "audio_ref": True,
      # 🩸 必须带 `desc_by_id`：生产 `video_edit` 一定传盘点描述，缺了它第二个
      # 说话人翻不出来，会退回整段的 `who`（等于张冠李戴），那不是生产形状。
      "desc_by_id": {x["id"]: {"zh": x["desc_zh"], "en": ""} for x in (P1, P2)},
      "shot_lines": [[{"start": 0.5, "end": 1.5, "text": "我走了", "lang": "zh",
                       "speaker": "P1"},
                      {"start": 2.0, "end": 3.2, "text": "别找我", "lang": "zh",
                       "speaker": "P2"}]]}),
]
