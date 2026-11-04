# -*- coding: utf-8 -*-
"""提示词快照锁：**三家各锁一批**，防止改一家把别家带歪。

🩸 为什么要有这个：`edit_spec.py` 是三个厂商共用的编译器，改一处很容易碰到
别家。工程没有 git，改完看不出"我到底动了谁"。这里把 2.0 / 2.5 / H3 在固定
一批形态下的编译结果算成 sha256，跟冻结文件比对，**一个字节变了就红**。

🩸 2.0 的用例必须按**生产形状**写：`source_people` 只含勾选的人，
`frame_people` 才是整个画面（`video_edit._span_people` 就是这么传的）。
拿整个盘点当 `source_people` 测出来的东西，生产里根本走不到。

用法（🩸 必须点名型号；用例已按型号分文件 `snap_cases_*.py`）：
    python scripts/prompt_snapshot.py --model volc20            # 比对（不写文件）
    python scripts/prompt_snapshot.py --model volc20 --freeze   # 人审过 diff 后再冻结
    python scripts/prompt_snapshot.py --model h3 --show         # 打出该型号全文
    python scripts/prompt_snapshot.py --all                     # 显式三家一起比

基线：`backend/data/prompt_snapshot.json`（本机数据，不进代码库）。
判据：退出码 0 = 全部一致；1 = 有差异（会列出是哪几条）；2 = 基线不存在。
"""
from __future__ import annotations

import hashlib
import importlib
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BACK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACK))
from app.services import edit_spec  # noqa: E402

SNAP = BACK / "data" / "prompt_snapshot.json"

# 🩸 一个型号一个用例文件（`snap_cases_*.py`）。本文件不再混着三家的清单：
# 跑哪一家就只 import 哪一个 —— 在 2.0 轮里物理上碰不到 2.5/H3 的用例。
CASE_MODULES = {
    "volc20": "snap_cases_sd20",
    "volc25": "snap_cases_sd25",
    # 🔓 2026-11-03 接回机械版：`snap_cases_h3` 已搬回 `scripts/`。
    "h3": "snap_cases_h3",
}


def load_cases(sel: str) -> list[tuple]:
    """`sel` = 型号键；`all` = 三家全要（只有 `--all` 会走到）。"""
    keys = list(CASE_MODULES) if sel == "all" else [sel]
    out: list[tuple] = []
    for k in keys:
        out.extend(importlib.import_module(CASE_MODULES[k]).CASES)
    return out


def compile_case(case) -> str:
    name, ch, model, chg, ppl, slots, extra = case
    kw = dict(source_people=ppl, slots=slots)
    # 🩸 `desc_by_id` 由**用例自己**传（写在 `extra` 里）。全局补会改到别的
    # 型号的锁定文本 —— 分模型执行期间不许一个改动波及两家。
    kw.update(extra)
    return edit_spec.compile_prompt(ch, edit_spec.normalize(chg),
                                    model=model, **kw)


def _model_of(name: str) -> str:
    if name.startswith("20 "):
        return "volc20"
    if name.startswith("25 "):
        return "volc25"
    return "h3"


def build(cases=None) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for case in (CASES if cases is None else cases):
        name = case[0]
        text = compile_case(case)
        out[name] = {
            "sha": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "len": len(text),
        }
    return out


def main() -> int:
    import _model_lock

    freeze = "--freeze" in sys.argv
    show = "--show" in sys.argv
    # 🩸 必须点名型号（2026-10-26，主人第四次提醒之后）：
    # 以前不点名就「按锁走」或「三家全跑」，等于"只看一家"全靠记性。
    # 现在没有 `--model` 又没有 `--all` 就直接拒绝运行。
    lock = _model_lock.current()
    if "--all" in sys.argv:
        sel = "all"
    elif "--model" in sys.argv:
        i = sys.argv.index("--model")
        sel = sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
        if sel not in CASE_MODULES and sel != "all":
            print("用法：--model volc20|volc25|h3（或 --all 显式三家）")
            return 2
    else:
        print("⛔ 必须点名型号：--model volc20|volc25|h3")
        print(f"   当前锁：{_model_lock.MODELS.get(lock, lock) if lock else '（无）'}")
        print("   确实要三家一起比：--all（会留痕）")
        return 2
    if lock and sel != lock and sel != "all" and "--force" not in sys.argv:
        print(f"⛔ 当前锁在 {_model_lock.MODELS.get(lock, lock)}；"
              f"本轮不许比 {_model_lock.MODELS.get(sel, sel)}。"
              f"（要跨型号加 --force 或 --all）")
        return 3
    cases = load_cases(sel)
    cur = build(cases)
    print(f"本次只比 {_model_lock.MODELS.get(sel, '三家')}：{len(cases)} 条")
    if show:
        for case in cases:
            print("=" * 78)
            print(case[0])
            print(compile_case(case))
            print()
        return 0
    if freeze:
        SNAP.parent.mkdir(parents=True, exist_ok=True)
        # 🩸 冻结**只更新本次选中的型号**，别家的锁定文本原样保留。
        old: dict = {}
        if SNAP.exists():
            try:
                old = json.loads(SNAP.read_text(encoding="utf-8"))
            except Exception:
                old = {}
        # 🩸 2026-10-26：本型号里**已从用例表删掉**的条目要一起清掉。
        # 以前只 `old.update(cur)`，删一条用例后基线里那条永远留着，
        # 比对时报「基线里有、当前没跑」→ 门永远红，逼人手工改基线 JSON。
        dropped = [n for n in old
                   if (sel == "all" or _model_of(n) == sel) and n not in cur]
        for n in dropped:
            old.pop(n, None)
        old.update(cur)
        SNAP.write_text(json.dumps(old, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        print(f"已冻结 {len(cur)} 条（{_model_lock.MODELS.get(sel, '三家')}）"
              f"→ {SNAP}；基线共 {len(old)} 条"
              + (f"；清掉已删用例 {len(dropped)} 条：{'、'.join(dropped)}"
                 if dropped else ""))
        return 0
    if not SNAP.exists():
        print(f"!! 基线不存在：{SNAP}\n   先人审 `--show` 的全文本，再 --freeze")
        return 2
    base = json.loads(SNAP.read_text(encoding="utf-8"))
    bad = [n for n in cur if base.get(n, {}).get("sha") != cur[n]["sha"]]
    # 只看**本次选中的型号**：别的型号这轮根本没算，不算"缺失"
    missing = [n for n in base
               if (sel == "all" or _model_of(n) == sel) and n not in cur]
    print(f"快照比对：{len(cur) - len(bad)}/{len(cur)} 一致")
    for n in bad:
        b = base.get(n, {})
        print(f"!! {n}: {b.get('sha', '?')[:12]} → {cur[n]['sha'][:12]}"
              f"  (len {b.get('len', '?')} → {cur[n]['len']})")
    for n in missing:
        print(f"!! 基线里有、当前没跑：{n}")
    if bad or missing:
        print("\n🩸 有条目与基线不一致 —— 先 `--show` 人审全文，"
              "确认是预期改动（不是波及别家）再 `--freeze`。")
        return 1
    print(f"ok {_model_lock.MODELS.get(sel, '三家')} 逐字未变")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
