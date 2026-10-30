# -*- coding: utf-8 -*-
"""把**一家模型**所有编译路径的产出做逐字指纹 —— 纯搬家类改动的硬证据。

为什么要它：重构前后"尺子没红"只说明规则判据没变，**不等于产出逐字没变**
（尺子没覆盖到的措辞照样可能被悄悄改）。搬家前后指纹必须完全一致。

用法（一次只点名一家）：
    python scripts/prompt_fingerprint.py --model volc20 --write D:/tmp/refactor_baseline
    python scripts/prompt_fingerprint.py --model volc20 --diff  D:/tmp/refactor_baseline

零模型调用、不联网、不花钱。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _prompt_of(row) -> str:
    """用例元组里挑出"编译出来的提示词"。

    三家的约定一致：`(名字, 提示词, …)`。**空提示词也是有效结果**
    （比如某些形状本来就编译不出内容），不能当成"找不到"跳过 —— 跳过就等于
    把这类用例从指纹里悄悄删掉。
    """
    if len(row) > 1 and isinstance(row[1], str):
        return row[1]
    strs = [x for x in row[1:] if isinstance(x, str)]
    return max(strs, key=len) if strs else ""


def _h3_sweep_prompts():
    """H3 的 `sweep_cases()` 给的是参数，不是成品 —— 按 `sweep()` 同样的方式编译。"""
    import ruler_h3 as R
    from app.services import edit_spec

    out = []
    for name, chg, n, pos, picks, kw in R.sweep_cases():
        frame = R._people(n, pos)
        picked = [dict(frame[i]) for i in picks]
        slots = ["person" if k == 0 else f"person{k + 1}"
                 for k in range(len(picks))]
        slots += list(kw.pop("_slots_extra", []))
        text = edit_spec.compile_prompt(
            "minimax", edit_spec.normalize(chg), model=R.H3_MODEL,
            source_people=picked,
            desc_by_id={p["id"]: {"zh": p["desc_zh"], "en": p["desc_en"]}
                        for p in frame}, slots=slots, **kw)
        out.append((f"sweep/{name}", text))
    return out


#: 三家都编译一遍的**同一组输入**（只是数据，不含任何一家的规则）。
#: 尺子自己的用例只管到各自扫过的形状；这块补的是"开关面"，
#: 尤其是 `_minimax`(750 行) / `_volc_25`(420 行) 这两块大的。
_BATTERY = [
    ("单人·换人", {"person": True, "person_ids": ["P1"]}, [0], {}),
    ("双人·全换", {"person": True, "person_ids": ["P1", "P2"]}, [0, 1], {}),
    ("双人·只换第1个", {"person": True, "person_ids": ["P1"]}, [0], {}),
    ("换产品", {"person": True, "person_ids": ["P1"], "product": True}, [0], {}),
    ("换产品·指定哪件", {"person": True, "person_ids": ["P1"], "product": True,
                        "product_target": "桌上的瓶子"}, [0], {}),
    ("换场景", {"person": True, "person_ids": ["P1"], "scene": True}, [0], {}),
    ("换装", {"person": True, "person_ids": ["P1"], "wardrobe": True,
             "wardrobe_ids": ["P1"]}, [0], {}),
    ("风格枚举词", {"person": True, "person_ids": ["P1"], "style": "anime"},
     [0], {}),
    ("补充说明", {"person": True, "person_ids": ["P1"],
                 "extra": "背景里加一只橘猫"}, [0], {}),
    ("keep 全关", {"person": True, "person_ids": ["P1"],
                   "keep": {k: False for k in ("motion", "camera", "rhythm",
                                               "background", "framing", "lighting")}},
     [0], {}),
    ("配音 tts", {"person": True, "person_ids": ["P1"], "audio": "tts"}, [0],
     {"audio_ref": True,
      "shot_lines": [[{"start": 0.5, "end": 1.8, "text": "我来了",
                       "lang": "zh", "speaker": "P1"}]]}),
    ("原声保留", {"person": True, "person_ids": ["P1"], "audio": "original"},
     [0], {"audio_ref": True}),
    ("1 切点", {"person": True, "person_ids": ["P1"]}, [0],
     {"shot_cuts": [3.0]}),
    ("首帧延续", {"person": True, "person_ids": ["P1"]}, [0],
     {"boundary_pic": 2}),
]


#: 锁名 → 真实型号 ID。🩸 别拿锁名当型号去编译：`model="volc25"` 认不出来，
#: 会被当成 2.0 编（0 报错，指纹照样"一致"——那是假绿）。
_REAL_ID = {"volc20": "doubao-seedance-2-0-mini-260615",
            "volc25": "doubao-seedance-2-5-260628",
            "h3": "MiniMax-H3"}


def _battery(model: str) -> list[tuple[str, str]]:
    import ruler_h3 as R          # 只借用它的夹具（造盘点/人物的纯数据）
    from app.services import edit_spec

    real = _REAL_ID[model]
    ch = "minimax" if model == "h3" else "volc"
    frame = R._people(2, "unique")
    picked_all = [dict(frame[0]), dict(frame[1])]
    desc = {p["id"]: {"zh": p["desc_zh"], "en": p["desc_en"]} for p in frame}
    out = []
    for name, chg, picks, kw in _BATTERY:
        picked = [picked_all[i] for i in picks]
        slots = ["person" if k == 0 else f"person{k + 1}"
                 for k in range(len(picked))]
        text = edit_spec.compile_prompt(
            ch, edit_spec.normalize(chg), model=real, source_people=picked,
            frame_people=frame, desc_by_id=desc, slots=slots, **kw)
        out.append((f"battery/{name}", text))
    return out


def collect(model: str) -> list[tuple[str, str]]:
    if model == "volc20":
        import ruler_sd20 as R
        groups = [("current", R.current_cases()), ("sweep", R.sweep_cases()),
                  ("d1", R._d1_cases()), ("d2", R._d2_cases()),
                  ("d3", R._d3_cases()), ("d4", R._d4_cases()),
                  ("d5", R._d5_cases()), ("d6", R._d6_cases()),
                  ("d7", R._d7_cases())]
        return ([(f"{g}/{r[0]}", _prompt_of(r))
                 for g, rows in groups for r in rows] + _battery(model))
    if model == "volc25":
        import ruler_sd25 as R
        groups = [("current", R.current_cases()), ("sweep", R.sweep_cases())]
        return ([(f"{g}/{r[0]}", _prompt_of(r))
                 for g, rows in groups for r in rows] + _battery(model))
    if model == "h3":
        import ruler_h3 as R
        out = [(f"current/{r[0]}", _prompt_of(r)) for r in R.current_cases()]
        out += _h3_sweep_prompts()
        out += _battery(model)
        return out
    raise SystemExit(f"未知型号：{model}")


def fingerprints(model: str) -> dict[str, str]:
    fp = {}
    for name, text in collect(model):
        if name in fp:
            raise SystemExit(f"用例重名，指纹会互相覆盖：{name}")
        fp[name] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return fp


def main() -> int:
    from _model_lock import guard
    guard(sys.argv[sys.argv.index("--model") + 1] if "--model" in sys.argv else "")
    model = sys.argv[sys.argv.index("--model") + 1]
    base = Path(sys.argv[sys.argv.index("--write") + 1]) if "--write" in sys.argv \
        else Path(sys.argv[sys.argv.index("--diff") + 1]) if "--diff" in sys.argv \
        else None
    if base is None:
        raise SystemExit("要给 --write 或 --diff 一个目录")

    fp = fingerprints(model)
    path = base / f"{model}.json"
    if "--write" in sys.argv:
        base.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(fp, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{model}：{len(fp)} 条指纹 → {path}")
        return 0

    if not path.exists():
        raise SystemExit(f"没有基线：{path}")
    old = json.loads(path.read_text(encoding="utf-8"))
    gone = sorted(set(old) - set(fp))
    new = sorted(set(fp) - set(old))
    changed = sorted(k for k in set(old) & set(fp) if old[k] != fp[k])
    print(f"{model}：基线 {len(old)} 条 / 现在 {len(fp)} 条")
    if not (gone or new or changed):
        print("✅ 逐字一致（0 处变化）")
        return 0
    print(f"❌ 不一致：改了 {len(changed)} / 少了 {len(gone)} / 多了 {len(new)}")
    for k in changed[:10]:
        print(f"   改了：{k}")
    for k in gone[:10]:
        print(f"   少了：{k}")
    for k in new[:10]:
        print(f"   多了：{k}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
