"""拿**当前编译器**重跑历史真机请求的输入，看同样的输入现在写出什么。

为什么不能直接审 `request_*.json`：
    那些是**当时**的产物。`ruler_*.py --history` 命中它们只能证明"当时出过错"，
    证明不了"现在还会不会错"。要回答后者，必须用现在的代码 + 当时的输入重编译。
    两者是互补的：`--history` 量历史，本脚本量"现在重编译后"。

输入从哪来（三者都在快照所在任务的目录里）：
    · `task.json` 的 `renders[<rid>].edit`  —— 当时用户点的规格
    · `inventory/*.json`                    —— 当时的视觉盘点
    · 任务目录下的 `subject.jpg` / `ref_*.jpg` —— 当时的参考图（本地留档的那份）
    · `triage/request_001.json`             —— 当时的型号与参考图数量（拿来自证）

尺子按 `--model` 选，**不共用**：
    · volc20 → `ruler_sd20`：RULES 五元组 + RULE_GENRES + genre_of
    · volc25 → `ruler_sd25`：`check()` + `ctx_for(..., "tpl", materials=)`
    · h3     → `ruler_h3`  ：`check()` + `ctx_for(..., edit_master=None, audio=None)`

判据：
    `·` = 历史就这么写的，`+` = 现在**新出现**，`-` = 历史有、现在没了，
    `!` = 输入不完整（图没留/型号不归本尺子管），这一条不进合计。

用法：python scripts/recheck_real_prompts.py --model volc25 [--verbose]
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def _load(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _hits(mod, name: str, text: str, people: list, n_pic: int) -> Counter:
    """按那家的尺子量一段提示词，返回 {规则ID: 命中条数}。"""
    c: Counter = Counter()
    if hasattr(mod, "check"):
        if name == "ruler_sd25":
            ctx = mod.ctx_for(text, people, "tpl",
                              materials={f"@图片{i + 1}" for i in range(n_pic)})
        elif name == "ruler_h3":
            # 🧊 2026-11-03 复刻下架 H3：这条尺子随编译器归档，映射里已没有它，
            #   分支留在这里只为兼容历史调用 —— 真进来会 import 失败，是预期的。
            # 历史请求看不出当时的音轨模式 → 与 `history()` 同口径，不猜
            ctx = mod.ctx_for(text, edit_master=None, audio=None)
        else:
            ctx = mod.ctx_for(text, people)
        try:
            for v in mod.check(text, ctx):
                c[v[0]] += 1
        except Exception as e:  # noqa: BLE001
            c[f"(尺子崩了){e}"] += 1
        return c
    # sd20：没有 check()，按它自己的循环来
    ctx = mod.ctx_for(text)
    for rid, _lv, _ti, _src, fn in mod.RULES:
        g = mod.RULE_GENRES.get(rid)
        if g and mod.genre_of(text) not in g:
            continue
        try:
            if fn(text, ctx) or []:
                c[rid] += 1
        except Exception:  # noqa: BLE001
            c[rid + "(崩)"] += 1
    return c


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=["volc20", "volc25", "h3"],
                    help="一轮只量一家；本文件不替你猜")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    from _model_lock import guard          # noqa: E402  分模型执行锁
    guard(a.model)
    # 锁的叫法（volc20/volc25）和文件名（ruler_sd20/ruler_sd25）不是一套
    # 🔓 2026-11-03 复刻换体裁：H3 的**历史请求全是 Ref2VA 六段式**，而现在的
    #   产出是手写入口三段式。拿新尺子量旧体裁 = 尺子量错东西（`spec-must-match-genre`），
    #   结果没有可比性。所以 h3 这一档**不再提供历史回测** —— 要看历史请去
    #   `_archive/h3_clone/ruler_h3_ref2va.py` 里跑。
    _MOD = {"volc20": "ruler_sd20", "volc25": "ruler_sd25"}
    if a.model not in _MOD:
        print(f"⛔ {a.model} 没有当前可用的尺子（H3 换体裁后历史请求不可比）")
        return 2
    mod_name = _MOD[a.model]
    mod = importlib.import_module(mod_name)

    from app.services import clone_store, models, video_edit  # noqa: E402

    root = Path(__file__).resolve().parents[1] / "data" / "clone"
    target = models.adapter_for(model={"volc20": "doubao-seedance-2-0-mini-260615",
                                       "volc25": "doubao-seedance-2-5-260628",
                                       "h3": "MiniMax-H3"}[a.model]).model_id
    rows = []
    for req in sorted(root.glob("*/render/*/triage/request_*.json")):
        raw = _load(req)
        if not raw or not str(raw.get("prompt") or "").strip():
            continue
        cid = req.parts[-5]
        rid = req.parts[-3]
        task = _load(root / cid / "task.json") or {}
        rend = next((x for x in task.get("renders") or [] if x.get("id") == rid), None)
        edit = (rend or {}).get("edit")
        out = {"cid": cid, "rid": rid, "old": raw.get("prompt"), "note": ""}
        if not edit:
            out["note"] = "task.json 里没有这条的规格"
            rows.append(out)
            continue
        inv_files = sorted((root / cid / "inventory").glob("*.json"))
        inv = _load(inv_files[0]) if len(inv_files) == 1 else None
        # 参考图按真实出片时那样从任务目录取（与 `clone.py:1230` 同一套）
        refs = {s: clone_store.ref_path(cid, s) for s in clone_store.REF_SLOTS
                if clone_store.ref_path(cid, s).exists()}
        subj = clone_store.subject_path(cid)
        ref_ids = [x for x in (raw.get("ref_images") or []) if isinstance(x, str)]
        try:
            prep = video_edit._prepare(
                rec={"source": {"width": 1080, "height": 1920}},
                spec=edit,
                refs=refs,
                subject_image=subj if subj.exists() else None,
                subject_asset=next((x.replace("asset://", "") for x in ref_ids
                                    if x.startswith("asset://")), ""),
                channel=raw.get("channel") or "auto",
                model=raw.get("model") or "",
                inventory=inv,
            )
        except Exception as e:  # noqa: BLE001
            out["note"] = f"现在被拦下：{type(e).__name__}: {e}"
            rows.append(out)
            continue
        out["new"] = prep["prompt"]
        out["model"] = prep["model"]
        # 🩸 `family` 只到厂商（volc/minimax），到不了型号；要比的是**适配器**：
        #   2.0 和 2.5 同属 volc，拿 family 判会把 2.5 当成 2.0 一起量。
        if models.adapter_for(model=prep["model"]).model_id != target:
            out["note"] = f"型号 {prep['model']} 不归本尺子管"
            rows.append(out)
            continue
        n_pic_new = sum(1 for s in prep["slots"] if not str(s).startswith("audio"))
        # 参考图张数变了要写出来，但**两边各按各的真实张数量**：
        #   老提示词当时发了几张，看 request 的 ref_images；新提示词发几张，看完 slots。
        #   拿新张数去量老提示词，会把"没提到 @图片2"当成"图传了却没提"的假红。
        if ref_ids and len(prep["ordered"]) != len(ref_ids):
            out["note"] = (f"参考图 {len(prep['ordered'])} 张 vs 当时 {len(ref_ids)} 张"
                           "（数量变了，两边各按各的量）")
        ppl = (inv or {}).get("people") or []
        out["h_old"] = _hits(mod, mod_name, out["old"], ppl,
                             len(ref_ids) or n_pic_new)
        out["h_new"] = _hits(mod, mod_name, out["new"], ppl, n_pic_new)
        out["counted"] = True
        rows.append(out)

    print(f"[{a.model}] 历史快照 {len(rows)} 份，用当前代码重编译\n")
    tot_old: Counter = Counter()
    tot_new: Counter = Counter()
    n_cnt = 0
    for r in rows:
        tag = f"{r['cid'][:8]}/{r['rid'][:8]}"
        if "h_new" not in r:
            print(f"—  {tag}  {r['note']}")
            continue
        if r["note"]:
            print(f"!  {tag}  {r['note']}")
        n_cnt += 1
        tot_old.update(r["h_old"])
        tot_new.update(r["h_new"])
        same = r["h_old"] == r["h_new"]
        if same and not a.verbose:
            continue
        print(f"·  {tag}  [{r.get('model')}]")
        for k in sorted(set(r["h_old"]) | set(r["h_new"])):
            o, n = r["h_old"].get(k, 0), r["h_new"].get(k, 0)
            print(f"     {'=' if o and n else ('-' if o else '+')}  {k}"
                  f"  {'历史也响，现在也响' if o and n else ('历史响，现在没了' if o else '**现在新出现**')}")
        if a.verbose:
            print("     历史: " + (r["old"] or "")[:220])
            print("     现在: " + (r["new"] or "")[:220])

    print(f"\n合计（可比的 {n_cnt}/{len(rows)} 份）")
    if not tot_old and not tot_new:
        print("  一份都没响")
    for k in sorted(set(tot_old) | set(tot_new)):
        print(f"  {k:<6} 历史 {tot_old.get(k, 0):>2} → 现在 {tot_new.get(k, 0):>2}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
