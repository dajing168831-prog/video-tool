# -*- coding: utf-8 -*-
"""原子要求表：把一把尺子的每条规则摊开成「要求 / 行号 / 正例 / 反例 / 可机械检」。

🩸 为什么要这张表：`RULES` 证明了「有判据」，`QUOTES` 证明了「有官方出处」——
但**没有一处**能回答「这条规则长什么样、什么样的产出算违反、判据真的抓得住吗」。
这张表把三件事绑在同一行上，缺哪一项一眼看见。

数据全部来自尺子文件本身（`RULES` / `QUOTES` / `PROBES`），不手抄、不另写样本：
- 要求 → `QUOTES[rid]`（官方原文逐字）
- 行号 → `RULES` 的 src 字段
- 反例 / 正例 → `PROBES` 里同一 rid 的 (坏样本, 好样本) 对的**差异片段**
- 可机械检 → 有判据函数 + 有成对探针；两者缺一标「未验证」

用法（只读，零网络零费用）：
    python scripts/ruler_atoms.py --model volc20
    python scripts/ruler_atoms.py --model volc25 --out docs/ATOM-volc25.md
"""
from __future__ import annotations

import argparse
import difflib
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

MODELS = {
    "volc20": ("ruler_sd20", "火山 Seedance 2.0"),
    "volc25": ("ruler_sd25", "火山 Seedance 2.5"),
    # 🔓 2026-11-03 接回机械版：改片尺子 `ruler_h3`（Ref2VA 六段式）。
    "h3": ("ruler_h3", "MiniMax H3"),
}


def say(*a):
    # 尺子模块 import 时会 reconfigure stdout，这里一律走 stderr
    print(*a, file=sys.stderr)


def _snippet(good: str, bad: str, width: int = 60) -> tuple[str, str]:
    """取 bad 与 good 的**第一处差异**，两边各带一点上下文。

    坏样本通常是 `good.replace(锚串, 坏串)`，所以差异块很干净；
    如果两者相同，说明锚串失效、这条探针根本没测到（假绿）。
    """
    sm = difflib.SequenceMatcher(None, good, bad, autojunk=False)
    ops = [o for o in sm.get_opcodes() if o[0] != "equal"]
    if not ops:
        return "（与正例完全相同 —— 探针锚串失效）", "（同上）"
    tag, i1, i2, j1, j2 = ops[0]
    g = good[max(0, i1 - width):min(len(good), i2 + width)]
    b = bad[max(0, j1 - width):min(len(bad), j2 + width)]
    return g, b


def _ctx_brief(ctx: dict) -> str:
    """把 ctx 里**真正决定判定**的那几个键压成一行，给表格看。"""
    if not ctx:
        return "—"
    out = []
    if ctx.get("materials"):
        out.append("materials=" + "/".join(sorted(str(x) for x in ctx["materials"])))
    if ctx.get("genre"):
        out.append(f"genre={ctx['genre']}")
    if ctx.get("people") is not None:
        out.append(f"people×{len(ctx['people'])}")
    if ctx.get("n_targets"):
        out.append(f"n_targets={ctx['n_targets']}")
    return " ".join(out) or "—"


def _cell(s: str, limit: int = 150) -> str:
    """表格单元格：去换行、截断、转义竖线。"""
    t = " ".join(str(s).split())
    if len(t) > limit:
        t = t[:limit] + "…"
    return t.replace("|", "\\|")


def build(model: str) -> tuple[str, dict]:
    mod_name, label = MODELS[model]
    m = importlib.import_module(mod_name)

    rules = m.RULES
    quotes = getattr(m, "QUOTES", {})
    # 探针有两个来源：`PROBES`（纯文本对）和 `PROBES_CTX`（还要 ctx 才判）。
    # 🩸 2026-10-29：ctx 型探针原来内联在 `probes()` 函数体里，数据层面看不见 ——
    #   那时这张表只能报「缺探针」，而实际上有。现在两家尺子都已数据化。
    probes: dict[str, list[tuple[str, str, dict, dict]]] = {}
    for item in getattr(m, "PROBES", []):
        probes.setdefault(item[0], []).append(
            (item[1], item[2], {}, {}))
    for item in getattr(m, "PROBES_CTX", []):
        rid, bad, good, cb, cg = item[0], item[1], item[2], item[3], item[4]
        probes.setdefault(rid, []).append((bad, good, cb or {}, cg or {}))

    rows, missing_quote, missing_probe, dead_probe = [], [], [], []
    n_ok = 0
    for r in rules:
        rid, sev, name, src, fn = r[0], r[1], r[2], r[3], r[4]
        quote = quotes.get(rid, "")
        if not quote:
            missing_quote.append(rid)

        pair = probes.get(rid)
        # 探针的元素不一定是字符串（有的尺子用 None 表示"特殊处理"）——
        # 非字符串一律按"这条没有可比对的成对样本"处理，不许让生成器崩掉。
        pair = [p for p in (pair or []) if isinstance(p[0], str) and isinstance(p[1], str)]
        if not pair:
            missing_probe.append(rid)
            bad_cell = "—（无成对探针）"
            good_cell = "—"
            mech = "❌ 未验证"
        else:
            bad_t, good_t, cb, cg = pair[0]
            good_s, bad_s = _snippet(good_t, bad_t)
            if good_s.startswith("（与正例完全相同"):
                # 文本一样，那就看 ctx 差在哪（W1 就是这种：同文本两套 materials）
                kb, kg = _ctx_brief(cb), _ctx_brief(cg)
                if kb != kg:
                    bad_cell = f"`{_cell(bad_t)}` ⏟ctx: `{_cell(kb)}`"
                    good_cell = f"`{_cell(good_t)}` ⏟ctx: `{_cell(kg)}`"
                    mech = "✅"
                else:
                    dead_probe.append(rid)
                    mech = "❌ 探针失效"
                    bad_cell = "（与正例完全相同 —— 探针锚串失效）"
                    good_cell = "（同上）"
            else:
                mech = "✅"
                bad_cell = f"`{_cell(bad_s)}`"
                good_cell = f"`{_cell(good_s)}`"
        if not quote:
            mech = "❌ 无锚句"
        if mech == "✅":
            n_ok += 1

        rows.append(f"| **{rid}** | {sev} | {_cell(name, 40)} | "
                    f"`{_cell(quote, 120)}` | `{_cell(src, 44)}` | "
                    f"{bad_cell} | {good_cell} | {mech} |")

    ok = n_ok
    head = (f"# 原子要求表 · {label}\n\n"
            f"> 由 `scripts/ruler_atoms.py --model {model}` 从尺子文件生成，**不要手改**。\n"
            f"> 数据来源：`{mod_name}.py` 的 `RULES` / `QUOTES` / `PROBES`。\n\n"
            f"| 统计 | 数 |\n|---|---|\n"
            f"| 规则总数 | **{len(rules)}** |\n"
            f"| 有官方锚句 | {len(rules) - len(missing_quote)} |\n"
            f"| 有**成对**探针（反例+正例） | {len(rules) - len(missing_probe)} |\n"
            f"| 可机械检（锚句 + 成对探针都齐） | **{ok}** |\n"
            f"| 缺锚句 | {len(missing_quote)} {missing_quote or ''} |\n"
            f"| 缺探针 | {len(missing_probe)} {missing_probe or ''} |\n"
            f"| 探针锚串失效 | {len(dead_probe)} {dead_probe or ''} |\n\n"
            f"## 逐条\n\n"
            f"| 规则 | 级别 | 要求 | 官方原文（锚句） | 行号 | 反例（改坏后应判红） | "
            f"正例（应放行） | 可机械检 |\n"
            f"|---|---|---|---|---|---|---|---|\n")
    body = "\n".join(rows) + "\n"
    stats = {"n": len(rules), "ok": ok, "no_quote": missing_quote,
             "no_probe": missing_probe, "dead": dead_probe}
    return head + body, stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=list(MODELS))
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    text, st = build(a.model)
    out = Path(a.out) if a.out else Path(
        f"C:/tmp/video-tool/docs/ATOM-{a.model}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")

    say(f"原子要求表 → {out}")
    say(f"规则 {st['n']} 条：可机械检 {st['ok']} · 缺锚句 {len(st['no_quote'])} "
        f"· 缺探针 {len(st['no_probe'])} · 探针失效 {len(st['dead'])}")
    # 🩸 分母自证：表里的行数必须等于 RULES 条数，否则就是漏了一整类规则
    n_rows = text.count("\n| **")
    say(f"分母自证：表行 {n_rows} = RULES {st['n']} {'✅' if n_rows == st['n'] else '❌'}")
    return 0 if n_rows == st["n"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
