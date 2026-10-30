# -*- coding: utf-8 -*-
"""MiniMax H3 的快照用例（**只放 H3**，别家不许进这个文件）。"""
from __future__ import annotations

from snap_cases_common import LINES, P1, P2, P1L, P2R

MODEL = "h3"
LABEL = "MiniMax H3"

# (名字, 通道, 型号, 勾选, 勾选的人, 槽位, 额外参数)
CASES: list[tuple] = [
    ("H3 单人", "minimax", "", {"person": True, "person_ids": ["P1"]},
     [P1], ["person"], {}),
    # 🩸 2026-10-26 删掉「H3 单人双图」：H3 的 caps 里 `split_person_images=False`，
    # `person_body` 槽生产上永远不会出现 —— 留着它等于给一个走不到的分支冻结基线。
    ("H3 双人只换一个", "minimax", "", {"person": True, "person_ids": ["P1"]},
     [P1, P2], ["person"], {}),
    ("H3 双人全换", "minimax", "",
     {"person": True, "person_ids": ["P1", "P2"]},
     [P1, P2], ["person", "person2"], {}),
    ("H3 双人全换+方位", "minimax", "",
     {"person": True, "person_ids": ["P1", "P2"]},
     [P1L, P2R], ["person", "person2"], {}),
    ("H3 单人+切点", "minimax", "", {"person": True, "person_ids": ["P1"]},
     [P1], ["person"], {"shot_cuts": [3.0, 6.9]}),
    ("H3 单人+换配音", "minimax", "",
     {"person": True, "audio": "tts", "person_ids": ["P1"]},
     [P1], ["person"], {"audio_ref": True, "shot_lines": LINES}),
    # 🩸 D31：原声保留（`audio: original` + 音轨真喂了）必须挂 `audio reuse`
    # （`ref-en:145`；音轨喂没喂看 `video_edit._audio_track`）
    ("H3 单人+原声保留", "minimax", "",
     {"person": True, "audio": "original", "person_ids": ["P1"]},
     [P1], ["person"], {"audio_ref": True}),
]
