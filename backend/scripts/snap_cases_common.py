# -*- coding: utf-8 -*-
"""快照用例的共享常量（只是测试数据，不含任何模型逻辑）。

三个型号各自的用例在 `snap_cases_sd20.py` / `snap_cases_sd25.py` /
`snap_cases_h3.py` 里，**一个型号一个文件**。人物/台词这类输入三家共用同一份，
放在这里，免得各写一份以后悄悄漂移。
"""
from __future__ import annotations

M20 = "doubao-seedance-2-0-mini-260615"
M25 = "doubao-seedance-2-5-260628"

P1 = {"id": "P1", "present": True, "position": "center",
      "desc_zh": "体型偏胖的男子，黑色头发束成发髻，身着浅青绿色古装",
      "desc_en": "a heavier-set man with hair in a topknot"}
P2 = {"id": "P2", "present": True, "position": "center",
      "desc_zh": "年轻女子，黑色长发梳成古装高髻，身着广袖古装",
      "desc_en": "a young woman with an elaborate updo"}
P1L = dict(P1, position="left")
P2R = dict(P2, position="right")

LINES = [[{"start": 0.4, "end": 1.8, "text": "这款真的很好用",
           "lang": "zh", "speaker": ""}]]
