# -*- coding: utf-8 -*-
"""火山 Seedance 2.5 的快照用例（**只放 2.5**，别家不许进这个文件）。"""
from __future__ import annotations

from snap_cases_common import LINES, M25, P1, P2, P1L, P2R

MODEL = "volc25"
LABEL = "火山 2.5"

# (名字, 通道, 型号, 勾选, 勾选的人, 槽位, 额外参数)
CASES: list[tuple] = [
    ("25 单人", "volc", M25, {"person": True, "person_ids": ["P1"]},
     [P1], ["person"], {}),
    # 🩸 2026-10-26 删掉「25 单人双图」：2.5 的 caps 里 `split_person_images=False`，
    # `person_body` 槽生产上永远不会出现 —— 留着等于给死分支冻结基线。
    ("25 双人只换一个", "volc", M25, {"person": True, "person_ids": ["P1"]},
     [P1, P2], ["person"], {}),
    ("25 双人全换", "volc", M25, {"person": True, "person_ids": ["P1", "P2"]},
     [P1, P2], ["person", "person2"], {}),
    ("25 双人全换+方位", "volc", M25,
     {"person": True, "person_ids": ["P1", "P2"]},
     [P1L, P2R], ["person", "person2"], {}),
    ("25 单人+产品", "volc", M25,
     {"person": True, "product": True, "person_ids": ["P1"]},
     [P1], ["person", "product"], {}),
    ("25 单人+切点", "volc", M25, {"person": True, "person_ids": ["P1"]},
     [P1], ["person"], {"shot_cuts": [3.0, 6.9]}),
    # 换背景两支都锁：混合那支曾在「人物保持原样」上自相矛盾（D28 修）
    ("25 单人+换背景", "volc", M25,
     {"person": True, "scene": True, "person_ids": ["P1"]},
     [P1], ["person", "scene"], {"frame_people": [P1]}),
    ("25 只换背景", "volc", M25, {"scene": True}, [], ["scene"], {}),
    # D30 锁：换装宾语只取主语短语 / 补充说明进编辑目标 / 风格参考两句
    ("25 双人·按人换装", "volc", M25,
     {"person": True, "wardrobe": True, "person_ids": ["P1", "P2"],
      "wardrobe_ids": ["P1", "P2"]},
     [P1, P2], ["person", "person2", "wardrobe", "wardrobe2"],
     {"frame_people": [P1, P2],
      "desc_by_id": {"P1": {"zh": P1["desc_zh"], "en": P1["desc_en"]},
                     "P2": {"zh": P2["desc_zh"], "en": P2["desc_en"]}}}),
    ("25 单人·补充说明", "volc", M25, {"person": True, "person_ids": ["P1"],
                                       "extra": "背景里加一只橘猫"},
     [P1], ["person"], {"frame_people": [P1]}),
    ("25 单人·风格参考图", "volc", M25,
     {"person": True, "style_ref": True, "person_ids": ["P1"]},
     [P1], ["person", "style_ref"], {"frame_people": [P1]}),
    ("25 单人+换配音", "volc", M25,
     {"person": True, "audio": "tts", "person_ids": ["P1"]},
     [P1], ["person"], {"audio_ref": True, "shot_lines": LINES}),
]
