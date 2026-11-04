# -*- coding: utf-8 -*-
"""H3 换人：拿**真实盘点**跑，不是我手编的样例。

主人 2026-11-04：「换人这一块我发现你还是会写死」——`h3_matrix_check.py` 里的
1人/2人/3人、left/center/right 全是我挑的，验证不了"任意爆款"。

这里遍历 `data/clone/*/inventory/*.json` 的**每一份真盘点**，
对每种人数组合各编一遍，查指代是否都落得住。
"""
from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path

BACK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACK))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import edit_spec  # noqa: E402

MODEL = "MiniMax-H3"


def build(chg, ppl, frame, slots):
    spec = edit_spec.normalize(chg)
    return edit_spec.compile_prompt(
        "minimax", spec, model=MODEL,
        source_people=ppl, frame_people=frame, slots=slots,
        audio_ref=False,
        desc_by_id={p["id"]: {"zh": p.get("desc_zh") or "",
                              "en": p.get("desc_en") or ""} for p in frame})


def cases_for(ppl):
    """每种人数：全换 / 前1 / 前2 / 前3。"""
    n = len(ppl)
    out = [("全换", list(range(n)))]
    for k in (1, 2, 3):
        if k < n:
            out.append((f"前{k}", list(range(k))))
    if n >= 4:
        out.append(("末2", list(range(n - 2, n))))
    return out


bad = total = 0
rows = []
for d in sorted(glob.glob(str(BACK / "data/clone/*/"))):
    fs = glob.glob(os.path.join(d, "inventory", "*.json"))
    if not fs:
        continue
    inv = json.loads(Path(fs[0]).read_text(encoding="utf-8"))
    frame = [p for p in (inv.get("people") or []) if p.get("present", True) is not False]
    if not frame:
        continue
    tid = os.path.basename(d.rstrip("/\\"))[:8]
    for label, idxs in cases_for(frame):
        picked = [frame[i] for i in idxs]
        slots = ["person" if i == 0 else f"person{i+1}" for i in range(len(picked))]
        total += 1
        try:
            m = build({"change": {"person": True,
                                  "person_ids": [p["id"] for p in picked]}},
                      picked, frame, slots)
        except Exception as e:                                   # noqa: BLE001
            print(f"✗ {tid} {label}  抛异常 {type(e).__name__}: {e}")
            bad += 1
            continue

        errs = []
        # 1. 每个被换的人都要在图里有对应图号
        for i, _ in enumerate(picked, 1):
            if f"@图片{i}中的人物" not in m:
                errs.append(f"缺@图片{i}")
        # 2. 被换的人的指代词不能互相重复（撞车必须退回描述）
        # 只看【核心创意】这一节，别把别的段切进来
        refs = []
        head = m.split("【核心创意】")[1].split("【画面过程说明】")[0]
        for seg in head.replace("\n", "，").split("，"):
            if "换成@图片" in seg:
                refs.append(seg.replace("@视频1中", "").split("换成")[0].strip())
        if len(refs) != len(set(refs)):
            errs.append(f"指代重复 {refs}")
        # 3. 换人公式 `:192` 的两句必须在（不管几个人）。
        #    🩸 原先把「100% 不变」「不要重新生成一个新场景」当硬项 —— 那是 `:133`
        #    换场景的公式，2026-11-04 实测套到换人上脸一个都不换，已从换人路径删除。
        #   `:142` 的特征维度清单（脸、发型、体型比例、服装设计、材质细节）——
        #   换具体的人必须有，只写「换成@图片N中的人物」模型只换脸或只换衣。
        for w in ("运动轨迹", "光影与环境融合", "锁定脸/形象"):
            if w not in m:
                errs.append(f"缺「{w}」")
        # 换人路径不许带 `:133` 换场景那套
        for w in ("必须保持 100% 不变", "不要重新生成一个新场景"):
            if w in m:
                errs.append(f"串了换场景的「{w}」")
        # 4. 不许漏出原片人物的英文服装/围裙这类"描述原片"的词
        for w in ("aproned", "原片画面"):
            if w in m:
                errs.append(f"漏出「{w}」")

        if errs:
            print(f"✗ {tid} {label}({len(picked)}/{len(frame)}人)  {errs}")
            bad += 1
        else:
            rows.append((tid, label, len(picked), len(frame),
                         "、".join(refs)))

print("\n—— 指代抽样（看它到底怎么指人）——")
for r in rows[:14]:
    print(f"  {r[0]} {r[1]}({r[2]}/{r[3]}人): {r[4]}")
print(f"\n{total - bad}/{total} 真实组合通过")
sys.exit(1 if bad else 0)
