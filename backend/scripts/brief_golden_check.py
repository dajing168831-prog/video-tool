# -*- coding: utf-8 -*-
"""规格书金标准 —— `clone_brief.py` 是**两家共用**的文件，改它必须两家都验。

🩸 为什么单独一条（2026-11-01 主人：「两家混一起真的怕出错」）：
  `clone_brief` 出的是**事实层**（原片多长、换谁、哪段有台词、用户勾了什么），
  2.5 的 `clone_agent` 和 H3 的 `h3_agent` 都读同一份。写法层是分开的，但这一层共用。
  于是它一改，两家同时变 —— 只验一家 = 没验。
  这里的做法：把一批典型规格书的**两家输出逐字存成基线**，改共用层就 diff，
  多一行少一行立刻看得见；确认是有意的改动、**两家全门都绿**之后再 `--update`。

规矩（`docs/MODEL-SEPARATION.md` 同款口径）：
  1. 改 `clone_brief.py` → 跑 `python scripts/brief_golden_check.py`，红就说明规格书变了；
  2. 确认要变 → **`check_all --model volc25`** 和 **`--model h3`** 两侧都跑绿；
  3. 两边都绿了才 `--update` 重存基线。

零费用：全程本地拼字符串，不调任何模型。

用法：
  python scripts/brief_golden_check.py            # 比对
  python scripts/brief_golden_check.py --update   # 重存基线（两家全绿之后才做）
"""
from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path

BACK = Path(__file__).resolve().parents[1]
if str(BACK) not in sys.path:
    sys.path.insert(0, str(BACK))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import clone_brief as B  # noqa: E402
from app.services import edit_spec  # noqa: E402
from app.services import h3_agent as A3  # noqa: E402

GOLDEN = Path(__file__).resolve().parent / "_brief_golden.json"

REC = {
    "source": {"duration": 20.0, "width": 1080, "height": 1920, "fps": 30.0},
    "shots": [{"i": 0, "start": 0.0, "end": 10.0},
              {"i": 1, "start": 10.0, "end": 20.0}],
    "speech": {"lang": "zh", "segments": [
        {"start": 1.0, "end": 3.0, "text": "第一句台词"},
        {"start": 11.0, "end": 13.0, "text": "第二句台词"},
    ]},
}

INV = {"people": [
    {"id": "P1", "main": True,
     "desc_zh": "画面中央的年轻女性，棕色齐耳短发，米白色荷叶边吊带",
     "desc_en": "a young woman in the center, brown chin-length bob, off-white camisole",
     "appearances": [{"start": 0.0, "end": 20.0}]},
], "_meta": {}}

SPANS = [(0.0, 10.0), (10.0, 20.0)]

#: 每种情况 = 一份 spec（喂给 `edit_spec.normalize`，跟线上同一条路）。
CASES: list[tuple[str, dict, dict]] = [
    # 名字, 原始 spec, plan 附加键
    ("换人", {"change": {"person": True, "person_ids": ["P1"]}},
     {"slots": ["person"], "looks": {"person": {"en": "jet-black bun, apricot dress",
                                                "gender": "female"}}}),
    # 🩸 2026-11-01：`original`（保留原声）和 `tts`（我们合成配音）喂给模型的
    #   音频角色**必须说得不一样** —— 前者是「复用这条原声」，后者才是「按音色
    #   重说」。以前两种写成同一句，H3 的 agent 就照着写成 `voice-timbre
    #   reference`，模型于是自己重说一遍：声音不是原声、节奏也和原片对不上。
    #   没有这条用例时，「原声」分支在金标准里**一条都没覆盖**（空集恒真）。
    ("换人·原声", {"change": {"person": True, "person_ids": ["P1"]},
                "audio": "original"},
     {"slots": ["person"], "looks": {"person": {"en": "jet-black bun"}}}),
    ("换人+换装", {"change": {"person": True, "person_ids": ["P1"],
                             "wardrobe": True, "wardrobe_ids": ["P1"],
                             "wardrobe_desc_by_id": {"P1": "红色风衣"}}},
     {"slots": ["person", "wardrobe"],
      "looks": {"person": {"en": "jet-black bun", "gender": "female"}}}),
    ("换产品", {"change": {"product": True, "product_target": "蓝色碗"}},
     {"slots": ["product"]}),
    ("换场景", {"change": {"scene": True, "scene_desc": "海边木屋"}},
     {"slots": ["scene"]}),
    ("只换声音", {"change": {}}, {}),
    ("换人+风格", {"change": {"person": True, "person_ids": ["P1"], "style": "anime"}},
     {"slots": ["person"], "looks": {"person": {"en": "jet-black bun"}}}),
    ("换人+补充说明", {"change": {"person": True, "person_ids": ["P1"]},
                  "extra": "画面更亮一点，人物表情更放松"},
     {"slots": ["person"], "looks": {"person": {"en": "jet-black bun"}}}),
    ("换人+说话人", {"change": {"person": True, "person_ids": ["P1"],
                            "speaker_ids": ["P1"]}},
     {"slots": ["person"], "looks": {"person": {"en": "jet-black bun"}}}),
    ("换人+风格参考视频", {"change": {"person": True, "person_ids": ["P1"],
                                "style_video": True}},
     {"slots": ["person"], "looks": {"person": {"en": "jet-black bun"}}}),
    # 🩸 2026-11-01 主人：「人物那里是一定有参考图的，其他地方才有参考图或描述 2 选 1。」
    #   上面九种都是「有图」，这三是「只有文字」—— 没有图时就**没有图号可用**，
    #   规格书必须把这件事说出来，否则 agent 会去找一个不存在的 <Picture N> / @图片N。
    # `product_target` 是盘点自动给的**被换件定位词**，用户填的「换成什么」是
    # `product_desc`（`edit_spec:233` 注释、`:1769` 编译版）
    ("换产品·只给文字", {"change": {"product": True,
                              "product_target": "画面里的白碗",
                              "product_desc": "一个蓝色陶瓷碗"}},
     {"slots": []}),
    ("换场景·只给文字", {"change": {"scene": True, "scene_desc": "海边木屋"}},
     {"slots": []}),
    ("换装·只给文字", {"change": {"wardrobe": True, "wardrobe_ids": ["P1"],
                             "wardrobe_desc_by_id": {"P1": "红色风衣"}}},
     {"slots": []}),
]


def _plan(raw: dict, extra: dict) -> dict:
    spec = edit_spec.normalize(raw)
    plan = {
        "ch": "minimax", "model": "MiniMax-H3", "spec": spec,
        "inventory": INV, "slots": list(extra.get("slots") or []),
        "ordered": [f"D:/tmp/case_{i}.jpg" for i in range(len(extra.get("slots") or []))],
        "audio_ref": True, "person_ids": (spec.get("change") or {}).get("person_ids") or [],
        "person_asset": "", "look": {}, "looks": dict(extra.get("looks") or {}),
    }
    return plan


def snapshot() -> dict:
    out = {}
    for name, raw, extra in CASES:
        plan = _plan(raw, extra)
        brief = B.build(plan, REC, SPANS)
        out[name] = {
            "sd25": B.as_text(brief),
            "h3": A3.brief_text(A3.as_brief(plan, REC, SPANS)),
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true", help="重存基线（先确认两家全门都绿）")
    args = ap.parse_args()

    now = snapshot()
    if args.update:
        GOLDEN.write_text(json.dumps(now, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"✅ 已重存基线：{GOLDEN.name}（{len(now)} 种情况 × 2 家）")
        print("   🩸 记住规矩：只在这条命令之前确认过 volc25 与 h3 两侧全门都绿。")
        return 0

    if not GOLDEN.is_file():
        print(f"🔴 基线不存在：{GOLDEN.name} —— 先跑 --update 生成（且要先两家全门绿）")
        return 1

    old = json.loads(GOLDEN.read_text(encoding="utf-8"))
    red = 0

    # 1) 情况数量对不上 = 有人加了/删了用例
    if set(old) != set(now):
        red += 1
        print(f"🔴 用例集变了：多 {sorted(set(now) - set(old))}，少 {sorted(set(old) - set(now))}")

    # 2) 逐字比对两家的输出
    for name in sorted(set(old) & set(now)):
        for who in ("sd25", "h3"):
            a = str(old[name].get(who) or "")
            b = str(now[name].get(who) or "")
            if a == b:
                continue
            red += 1
            d = list(difflib.unified_diff(a.splitlines(), b.splitlines(),
                                          fromfile=f"基线/{who}", tofile=f"现在/{who}",
                                          lineterm="", n=1))
            print(f"🔴 「{name}」的 {who} 规格书变了（{len(a)} → {len(b)} 字符）：")
            for ln in d[:14]:
                print("   " + ln)

    if red:
        print(f"\n{len(now)} 种情况 × 2 家，**{red} 处不一致**。")
        print("🩸 `clone_brief.py` 是两家共用的：确认是有意的改动后，")
        print("   先跑 check_all --model volc25 和 --model h3，两边都绿了再 --update。")
        return 1

    print(f"✅ 规格书与基线逐字一致（{len(now)} 种情况 × 2 家 = {len(now) * 2} 份）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
