# -*- coding: utf-8 -*-
"""SD20 换人：**随机形态穷举**（不问"这条视频怎么写"，问"任意视频会不会产出坏句"）。

随机生成 N 组输入（人数 / 位置唯一性 / 描述有无 / 附带改动 / 音频），
逐组编译 + 过 `sd20_invariants.check`。
✓ 全过 ⇒ 换人不靠人工逐条适配，靠不变量兜住。
✗ 有违规 ⇒ 违规出现在哪类形态，就修那一类，不修单条视频。

只读本地，不联网、不花钱、不出片。
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import edit_spec  # noqa: E402
import sd20_invariants as inv  # noqa: E402

MODEL = "doubao-seedance-2-0-mini-260615"
POS = ["left", "center", "right"]
DESCS = ["浅金色卷发、佩戴细框圆形眼镜的女人", "穿灰色布衫、短发的少年",
         "戴眼镜、穿藏青外套的中年男人", "长发、穿红色毛衣的年轻女人",
         "穿白衬衫的瘦高男人", "戴帽子的老年女人"]
LOOK = {"zh": "东亚女性、纯黑色顺直中长发、贴身款大U领短袖上衣"}

rng = random.Random(20261105)


def one_case():
    n_src = rng.randint(1, 6)
    n_swap = rng.randint(1, min(3, n_src))
    # 位置：唯一 or 撞车
    unique_pos = rng.random() < 0.6
    pos_pool = POS[:] if unique_pos else [rng.choice(POS)] * n_src
    if unique_pos:
        pos_pool = [POS[i % 3] for i in range(n_src)]
        rng.shuffle(pos_pool)
    # 每人描述：可能缺
    ppl = []
    for i in range(n_src):
        ppl.append({"id": f"P{i + 1}", "present": True, "position": pos_pool[i],
                    "desc_zh": DESCS[i] if rng.random() < 0.8 else ""})
    ids = [p["id"] for p in ppl[:n_swap]]
    ch = {"person": True, "person_ids": ids}
    slots = [edit_spec.PERSON_SLOTS[i] for i in range(n_swap)]
    looks = {s: LOOK for s in slots}
    ref_missing = False
    if rng.random() < 0.25:                       # 有的参考图没外观描述
        ref_missing = True
        looks[slots[-1]] = {}
    if rng.random() < 0.3:
        ch.update({"wardrobe": True, "wardrobe_ids": ids,
                   "wardrobe_desc": "米色风衣"})
        slots += [edit_spec.WARDROBE_SLOTS[i] for i in range(n_swap)]
        looks.update({edit_spec.WARDROBE_SLOTS[i]: {"zh": "米色风衣"}
                      for i in range(n_swap)})
    if rng.random() < 0.2:
        ch.update({"hair": True, "hair_ids": ids, "hair_desc": "低马尾"})
    if rng.random() < 0.2:
        ch.update({"scene": True, "scene_desc": "换成海边木屋"})
        slots.append("scene")
    if rng.random() < 0.2:
        ch.update({"product": True, "product_target": "桌上的白色花瓶",
                   "product_desc": "换成青瓷茶壶"})
        slots.append("product")
    audio = rng.choice(["original", "tts"])
    spec = edit_spec.normalize(ch)
    # ① 生产链路第一道闸：缺料（没图没描述）→ 拦截，不编译
    refs = {s: "asset://x" for s in slots if s.startswith(("person", "wardrobe"))}
    lack = edit_spec.missing_material(spec, refs, person_asset="",
                                      model=MODEL,
                                      wardrobe_per_person=True)
    if lack:
        return (n_src, n_swap), [], "", "blocked"
    # ② 生产链路第二道闸：画面多人却一个都没点选 → 拦截
    if not ids and n_src >= 2:
        return (n_src, n_swap), [], "", "blocked"
    # ③ 第三道闸（2026-11-05 新加，video_edit.py 同源）：画面多人、点选了，
    #    但目标既没唯一方位也没描述 → 编译器只会出「替换为另一个人」→ 拦截
    if n_src >= 2:
        cnt: dict[str, int] = {}
        for p in ppl:
            k = p["position"]
            cnt[k] = cnt.get(k, 0) + 1
        for p in ppl[:n_swap]:
            if not p["desc_zh"].strip() and cnt.get(p["position"], 0) > 1:
                return (n_src, n_swap), [], "", "blocked"
    kw = dict(model=MODEL, source_people=ppl, slots=slots, subject_looks=looks,
              # 🩸 真实调用（video_edit.py:1254）传的是**整个画面的人**，不是勾选的人。
              #   第一版漏了它 → 编译器以为画面只有勾选那几个 → 走单人路径 → 出「另一个人」。
              frame_people=ppl,
              desc_by_id={p["id"]: {"zh": p["desc_zh"]} for p in ppl if p["desc_zh"]})
    if audio == "tts":
        kw["audio_ref"] = True
        kw["shot_lines"] = [[{"speaker": ids[0], "text": "这是第一句。", "part": ""}]]
    try:
        text = edit_spec.compile_prompt("volc", spec, **kw)
    except Exception as e:  # noqa: BLE001
        return (n_src, n_swap), [f"编译异常 {type(e).__name__}: {str(e)[:60]}"], ""
    bad = inv.check(text, n_src=n_src, n_swap=n_swap,
                    ref_desc_missing=ref_missing, audio=audio)
    if bad:
        bad.append(f"  [ctx] slots={slots} ids={ids} "
                   f"desc={[p['desc_zh'][:6] for p in ppl]} "
                   f"looks={ {k: bool(v) for k, v in looks.items()} }")
    return (n_src, n_swap), bad, text, "compiled"


N = 300
fails = []
blocked = compiled = 0
for _ in range(N):
    shape, bad, text, status = one_case()
    if status == "blocked":
        blocked += 1
    else:
        compiled += 1
    if bad:
        fails.append((shape, bad, text))

print(f"随机形态 {N} 组 × 10 条不变量")
print(f"前置拦截 {blocked} 组（缺料/多人未点选，生产链路本就拒绝编译）")
print(f"真正编译 {compiled} 组 → 通过 {compiled - len(fails)}/{compiled}\n")
if fails:
    from collections import Counter
    print("违规条目分布：")
    for k, v in Counter(b[0][:3] for _, b, _ in fails for b in b).most_common():
        print(f"  {k}  ×{v}")
    print("\n违规形态分布（原片人数, 换人数）：")
    for k, v in Counter(f[0] for f in fails).most_common(10):
        print(f"  {k}  ×{v}")
    print("\n首 3 例全文：")
    for shape, bad, text in fails[:3]:
        print(f"\n--- {shape} ---")
        print("违规：", "；".join(bad))
        print(text)
else:
    print("✓ 任意形态都满足全部不变量 —— 换人不再需要逐条适配。")
