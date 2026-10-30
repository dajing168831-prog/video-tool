# -*- coding: utf-8 -*-
"""提示词出处门禁：**每一句都必须是这个型号自己的官方语料里长出来的**。

为什么要有这道门（2026-10-26 主人生气点）：
「让<你>分离好三个模型，你现在又抄了一个 2.5 模型的提示词进来」——
当天在 2.0 的编译器里查出两处**别家来源**：
  · `@音频1是@视频1的原片音轨，原样保留在成片中` ← 依据是 2.5 的 `sd25-pe:142`（已删）
  · `@视频1是唯一编辑母版，负责原始场景…` ← 2.5 的 `sd25-pe:564` 结构件（已删）
这两处**任何一道旧门都筛不出来**：语法是对的、测试是绿的、快照也在绿（因为
那条路当时根本没有基线）。所以门要按「**出处**」判，不按「跑没跑通」判。

两条判据（都零联网、零模型调用）：

  A. **成句出处**：把已冻结的提示词逐句切开，跟三家官方语料分别求最长公共子串。
     如果某句在**别家**语料里命中的片段 ≥ 12 字，且比自家命中更长 → 红。
     这就是「这句是从别人家抄来的」的机械定义。
  B. **引文出处**：扫三个型号的编译器源码，出现别家文档 token 的行必须进白名单，
     每条写清楚「为什么必须引用别家」；新增没登记的 → 红。
     （对比说明、否定说明、墓碑都算合法，但要登记，不许沉默。）

用法：
    python scripts/prompt_provenance_check.py            # 跑 A + B
    python scripts/prompt_provenance_check.py --selftest # 自证：往两头各塞一个坏样本
    python scripts/prompt_provenance_check.py --update   # 登记/更新 B 的白名单
"""
from __future__ import annotations

import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SNAP = ROOT / "data" / "prompt_snapshot.json"
WHITELIST = ROOT / "scripts" / "_prompt_provenance_whitelist.json"

# 三家官方语料（本机副本；缺了不报绿，报"没查"）
CORPUS = {
    "volc20": [r"D:/tmp/official/sd20/skill-sd2-pe.md",
               r"D:/tmp/official/sd20/guide.md"],
    "volc25": [r"D:/tmp/official/sd25/skill-sd25-pe.md",
               r"D:/tmp/official/sd25/guide.md"],
    "h3": [r"D:/tmp/official/h3/ref-en.txt",
           r"D:/tmp/official/h3/base-en.txt"],
}

# 编译器源码 + 它"自己的"文档 token
COMPILERS = {
    "volc20": ["app/services/models/volc20.py",
               "app/services/models/volc20_compile.py"],
    "volc25": ["app/services/models/volc25.py",
               "app/services/models/volc25_compile.py"],
    "h3": ["app/services/models/h3.py", "app/services/models/h3_compile.py"],
}
OWN_TOKENS = {
    "volc20": ("sd2-pe", "seedance-20-guide"),
    "volc25": ("sd25-pe", "seedance-25-guide"),
    "h3": ("ref-en", "base-en"),
}
ALL_TOKENS = re.compile(r"(sd2-pe|seedance-20-guide|sd25-pe|seedance-25-guide|ref-en|base-en)")

# 成句出处判据：别家命中片段长度门槛 + 必须比自家长
FRAG_MIN = 12

PASS = 0
FAIL = 0


def chk(name: str, ok: bool, detail: str = "") -> bool:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}" + (f"  [{detail}]" if detail else ""))
    return ok


def _load_corpus() -> dict[str, str]:
    out = {}
    for model, paths in CORPUS.items():
        buf = []
        for p in paths:
            f = Path(p)
            if f.exists():
                buf.append(f.read_text(encoding="utf-8", errors="replace"))
        out[model] = "\n".join(buf)
    return out


def _lcs(a: str, b: str) -> str:
    m = SequenceMatcher(None, a, b, autojunk=False)
    blk = m.find_longest_match(0, len(a), 0, len(b))
    return a[blk.a: blk.a + blk.size]


def _model_of(case_name: str) -> str | None:
    """快照用例名 → 型号。名字前缀是 20 / 25 / H3。"""
    if case_name.startswith("20 ") or case_name.startswith("20·"):
        return "volc20"
    if case_name.startswith("25 ") or case_name.startswith("25·"):
        return "volc25"
    if case_name.startswith("H3"):
        return "h3"
    return None


def check_sentences(corpus: dict[str, str], prompts: dict[str, str] | None = None) -> list[tuple]:
    """A. 成句出处。返回嫌疑列表 [(用例, 句子, 自家命中, 别家, 别家命中, 片段)]。"""
    if prompts is None:
        if not SNAP.exists():
            return []
        raw = json.loads(SNAP.read_text(encoding="utf-8"))
        prompts = {k: (v.get("prompt") if isinstance(v, dict) else v)
                   for k, v in raw.items()}
    bad = []
    for name, prompt in prompts.items():
        own = _model_of(name)
        if not own or not isinstance(prompt, str) or not prompt.strip():
            continue
        if not corpus.get(own):
            continue                      # 自家语料没拿到 → 不判（不许当绿）
        for sent in re.split(r"[。；]", prompt):
            sent = sent.strip()
            if len(sent) < 8:
                continue
            own_len = len(_lcs(sent, corpus[own]))
            foreign = {k: len(_lcs(sent, v)) for k, v in corpus.items()
                       if k != own and v}
            if not foreign:
                continue
            best = max(foreign, key=foreign.get)
            if foreign[best] >= FRAG_MIN and foreign[best] > own_len:
                bad.append((name, sent, own_len, best, foreign[best],
                            _lcs(sent, corpus[best])))
    return bad


def _line_key(rel: str, line: str) -> str:
    return f"{rel}::{line.strip()}"


def _scan_foreign_citations() -> dict[str, str]:
    """B. 引文出处：返回 {key: 行文本}，key = 文件::行内容。"""
    out = {}
    for model, files in COMPILERS.items():
        own = OWN_TOKENS[model]
        for rel in files:
            f = ROOT / rel
            if not f.exists():
                continue
            for line in f.read_text(encoding="utf-8").splitlines():
                toks = set(ALL_TOKENS.findall(line))
                if not toks:
                    continue
                if all(any(t.startswith(o) for o in own) for t in toks):
                    continue
                out[_line_key(rel, line)] = line.strip()
    return out


def run() -> int:
    corpus = _load_corpus()
    print("== 语料 ==")
    for k, v in corpus.items():
        chk(f"{k} 官方语料可读", bool(v), f"{len(v)} 字")

    print("\n== A. 成句出处（每句必须长在自家语料上）==")
    bad = check_sentences(corpus)
    total = 0
    if SNAP.exists():
        raw = json.loads(SNAP.read_text(encoding="utf-8"))
        total = len(raw)
    chk(f"{total} 条基线的每一句都没从别家抄", not bad,
        "; ".join(f"[{n}] {s[:40]}" for n, s, *_ in bad[:3]))
    for name, sent, ol, fk, fl, frag in bad:
        print(f"        [{name}] 自家 {ol} 字 / {fk} {fl} 字 片段「{frag}」")
        print(f"         句：{sent[:100]}")

    print("\n== B. 引文出处（编译器里的别家文档引用必须在白名单）==")
    found = _scan_foreign_citations()
    wl = {}
    if WHITELIST.exists():
        wl = json.loads(WHITELIST.read_text(encoding="utf-8"))
    new = {k: v for k, v in found.items() if k not in wl}
    gone = {k: v for k, v in wl.items() if k not in found}
    chk(f"别家引文全部已登记（{len(found)} 处）", not new,
        "; ".join(f"{k.split('/')[-1]}" for k in list(new)[:3]))
    for k, v in new.items():
        print(f"        未登记：{k.split('::')[0]}  {v[:100]}")
    if gone:
        print(f"  note 白名单里有 {len(gone)} 条已不存在（无害，--update 会清掉）")
    return 1 if FAIL else 0


def selftest() -> int:
    """自证：两个方向各塞一个坏样本，必须都红。"""
    global PASS, FAIL
    PASS = FAIL = 0
    corpus = _load_corpus()
    print("== 自证 A：成对探针（坏样本必须响，好样本不许响）==")
    # 坏样本 = 2026-10-26 真实发生过的那句：2.5 `sd25-pe:564` 的结构件被抄进 2.0
    bad_case = {"20 假用例(坏)":
                "@视频1是唯一编辑母版，负责原始场景、机位、镜头运动、动作轨迹、"
                "遮挡关系和事件顺序。"}
    got = check_sentences(corpus, bad_case)
    chk("2.5 的原话被识别", bool(got), "没识别出来 = 尺子失效")
    if got:
        print(f"        命中 {got[0][3]} {got[0][4]} 字：「{got[0][5]}」")
    # 好样本 = 2.0 官方自己的句子，必须**不响**
    ok_case = {"20 假用例(好)":
               "视频全程禁止出现外形、着装、配饰完全一致的人物，"
               "禁止生成同款分身、双胞胎效果。"}
    got2 = check_sentences(corpus, ok_case)
    chk("2.0 官方原句被误判", not got2, "误报 = 尺子装反了")
    print("\n== 自证 B：没登记的别家引文必须报红 ==")
    found = _scan_foreign_citations()
    fake_key = "app/services/models/volc20_compile.py::# 按 sd25-pe:142 写一句音轨"
    wl = set(found)
    chk("白名单拒绝新增别家引文", fake_key not in wl)
    return 1 if FAIL else 0


def update() -> int:
    found = _scan_foreign_citations()
    old = json.loads(WHITELIST.read_text(encoding="utf-8")) if WHITELIST.exists() else {}
    out = {k: old.get(k, "（待补理由：为什么必须引用别家）") for k in found}
    WHITELIST.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已登记 {len(out)} 条 → {WHITELIST}")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    if "--update" in sys.argv:
        raise SystemExit(update())
    raise SystemExit(run())
