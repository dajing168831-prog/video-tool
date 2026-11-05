# -*- coding: utf-8 -*-
"""SD20 复刻换人：**形态矩阵** —— 不是只验一条测试片，是把各种形态都编一遍看输出。

照着 `h3_matrix_check.py` 的做法（2026-11-04 主人：「能准确的灵活运用到任意一个爆款视频上」）。
依据：`docs/SD20-OFFICIAL-MAP.md` + `docs/SD20-CLONE-MATRIX.md`。

覆盖：原片人数 1–6 × 换人数 1–N × 改动组合（人/装/发/景/品）× 音频（原声/tts）。
只读本地，不联网、不花钱、不出片。

判据（每条带官方出处）：
  R1 换人句存在，目标宾语是 `@图片N中的人物`（1 人）或 `<主体N>`（≥2 人）
     —— `pg:941` 类比 + `pg:94` 多主体分别定义
  R2 换人目标 = 1 时**不得**出现 `<主体N>`（2026-10-30 三次真机 + 60f82aab share 0.0）
  R3 不得出现「参考@视频1」（`pg:48-51` 明令禁止，会被误判成参考任务）
  R4 单人宾语不得带服装/道具外观（`pg:95` 允许，但 2026-10-24 真机反证只换衣不换脸）
  R5 双胞胎兜底按人数挂（`pg:411` / `skill:162`）
  R6 画质 / 稳定 / 字幕 / 水印包（`skill:158-163`）
  R7 改动项必须真的出现在提示词里
"""
from __future__ import annotations

import itertools
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import edit_spec  # noqa: E402

MODEL = "doubao-seedance-2-0-mini-260615"
DESC = [("P1", "left", "浅金色卷发、佩戴细框圆形眼镜的女人"),
        ("P2", "center", "穿灰色布衫、短发的少年"),
        ("P3", "right", "戴眼镜、穿藏青外套的中年男人"),
        ("P4", "left", "长发、穿红色毛衣的年轻女人"),
        ("P5", "center", "穿白衬衫的瘦高男人"),
        ("P6", "right", "戴帽子的老年女人")]
LOOK = {"zh": "东亚女性、纯黑色顺直中长发、贴身款大U领短袖上衣"}
# 画面里「非人主体」这一维的取值（矩阵 §3.1）：真实样本 `60f82aab` 同款
OTHER = {"id": "O1", "kind": "白色带粉色棘刺的龙形生物",
         "desc_zh": "白色皮肤，头顶和背部有粉色棘刺",
         "desc_en": "white dragon-like creature with pink spines",
         "position": "right", "appearances": [{"start": 0.0, "end": 30.0}]}


def build(n_src: int, n_swap: int, flags: dict, audio: str = "original",
          has_other: bool = False):
    ppl = [{"id": d[0], "present": True, "position": d[1], "desc_zh": d[2]}
           for d in DESC[:n_src]]
    ids = [d[0] for d in DESC[:n_swap]]
    ch = {"person": True, "person_ids": ids, "audio": audio}
    slots = [edit_spec.PERSON_SLOTS[i] for i in range(n_swap)]
    if flags.get("wardrobe"):
        ch.update({"wardrobe": True, "wardrobe_ids": ids,
                   "wardrobe_desc": "米色风衣",
                   "wardrobe_desc_by_id": {i: "米色风衣" for i in ids}})
        slots += [edit_spec.WARDROBE_SLOTS[i] for i in range(n_swap)]
    if flags.get("hair"):
        ch.update({"hair": True, "hair_ids": ids, "hair_desc": "低马尾",
                   "hair_desc_by_id": {i: "低马尾" for i in ids}})
    if flags.get("scene"):
        ch.update({"scene": True, "scene_desc": "换成海边木屋"})
        slots.append("scene")
    if flags.get("product"):
        ch.update({"product": True, "product_target": "桌上的白色花瓶",
                   "product_desc": "换成青瓷茶壶"})
        slots.append("product")
    spec = edit_spec.normalize(ch)
    kw = dict(model=MODEL, source_people=ppl, slots=slots,
              subject_looks={s: LOOK for s in slots if s.startswith(("person", "wardrobe"))},
              desc_by_id={p["id"]: {"zh": p["desc_zh"]} for p in ppl},
              # 矩阵 §3.1 新增维度：画面里还有没有非人主体
              frame_others=([OTHER] if has_other else None))
    if audio in ("tts", "mix"):
        kw["audio_ref"] = True
        kw["shot_lines"] = [[{"speaker": ids[0], "text": "这是第一句。", "part": ""}]]
    try:
        return edit_spec.compile_prompt("volc", spec, **kw), ""
    except Exception as e:  # noqa: BLE001
        return "", f"{type(e).__name__}: {str(e)[:70]}"


def check(text: str, n_swap: int, flags: dict, has_other: bool = False) -> dict:
    tgts = re.findall(r"替换为(<主体\d+>|@图片\d+中的人物)", text) or \
        re.findall(r"替换成(<主体\d+>|@图片\d+中的人物)", text)
    r1 = bool(tgts)
    r2 = not (n_swap == 1 and "<主体" in text)
    if n_swap == 1:
        r1 = r1 and all(t.startswith("@图片") for t in tgts)
    else:
        r1 = r1 and all(t.startswith("<主体") for t in tgts)
    r3 = "参考@视频1" not in text and "参考 @视频1" not in text
    # 单人宾语：取「其中的X」这一段，检查有没有服装/道具描述
    obj = re.search(r"将其中的(.+?)替换", text)
    r4 = True
    if n_swap == 1 and obj:
        o = obj.group(1)
        r4 = not re.search(r"身着|身穿|外穿|手持|持着|外套|衬衫|连衣裙", o)
    twin = "双胞胎" in text or "同款分身" in text
    r5 = twin if n_swap >= 2 else True      # 多人必挂；单人没有第二张脸
    r6 = all(k in text for k in ("高清", "画面稳定无变形", "无字幕", "水印", "Logo"))
    parts = []
    if flags.get("wardrobe"):
        parts.append("服装" in text)
    if flags.get("hair"):
        parts.append("发型" in text)
    if flags.get("scene"):
        parts.append("背景场景" in text or "海边木屋" in text)
    if flags.get("product"):
        parts.append("花瓶" in text or "青瓷茶壶" in text)
    r7 = all(parts) if parts else True
    # R8（矩阵 §3.1 新增）：画面里除了人还有别的主体时，源宾语必须点名那个人。
    # 官方 `skill:24` 的"改"句式是「将其中的<原特征>修改为<新特征>」——
    # `<原特征>` 位写裸「人物」= 没指认，画面里有两个主体时模型自己猜。
    r8 = True
    if has_other and n_swap == 1:
        r8 = bool(obj) and obj.group(1).strip() not in ("人物", "")
    return dict(tgts=tgts, obj=(obj.group(1) if obj else ""),
                R1=r1, R2=r2, R3=r3, R4=r4, R5=r5, R6=r6, R7=r7, R8=r8,
                ok=all([r1, r2, r3, r4, r5, r6, r7, r8]))


def main() -> int:
    rows = []
    COMBOS = [("none", {}), ("wear", {"wardrobe": True}),
              ("hair", {"hair": True}), ("scene", {"scene": True}),
              ("product", {"product": True})]
    for n_src, n_swap, (cname, flags), audio, has_other in itertools.product(
            (1, 2, 3, 4, 5, 6), (1, 2, 3), COMBOS, ("original", "tts"),
            (False, True)):
        if n_swap > n_src:
            continue
        text, err = build(n_src, n_swap, flags, audio, has_other=has_other)
        if err:
            rows.append(dict(n_src=n_src, n_swap=n_swap, combo=cname, audio=audio,
                             other=has_other, err=err, ok=False, tgts=[], obj="",
                             R1=0, R2=0, R3=0, R4=0, R5=0, R6=0, R7=0, R8=0))
            continue
        rows.append(dict(n_src=n_src, n_swap=n_swap, combo=cname, audio=audio,
                         other=has_other, err="",
                         **check(text, n_swap, flags, has_other=has_other)))

    bad = [r for r in rows if not r["ok"]]
    print(f"共 {len(rows)} 格\n")
    print("| 原片 | 换 | 附带 | 音频 | 非人主体 | 目标宾语 | 源宾语 | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['n_src']} | {r['n_swap']} | {r['combo']} | {r['audio']} | "
              f"{'有' if r['other'] else '无'} | "
              f"{'/'.join(r['tgts'])[:24] or '—'} | {r['obj'][:18] or '—'} | "
              f"{'✓' if r['R1'] else '✗'} | {'✓' if r['R2'] else '✗'} | "
              f"{'✓' if r['R3'] else '✗'} | {'✓' if r['R4'] else '✗'} | "
              f"{'✓' if r['R5'] else '✗'} | {'✓' if r['R6'] else '✗'} | "
              f"{'✓' if r['R7'] else '✗'} | {'✓' if r['R8'] else '✗'} |")
    print(f"\n合规 {len(rows) - len(bad)}/{len(rows)}")
    if bad:
        print("不合规分布：")
        from collections import Counter
        for k, v in Counter((r["n_swap"], r["combo"], r["audio"]) for r in bad).items():
            print("  ", k, v)
        for r in bad[:3]:
            if r["err"]:
                print("   示例错误:", r["n_src"], r["n_swap"], r["err"])
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
