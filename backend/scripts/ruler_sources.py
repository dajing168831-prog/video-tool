# -*- coding: utf-8 -*-
"""尺子的出处判据：**每条规则记的行号，那一行真的写着东西吗**。

为什么要有这一把：2026-10-28 把三家 58 条规则的 `src` 逐条回原文核，
**10 条对不上**（17%）—— 3 条点进去是标题/空行，2 条根本没有文档出处。
而在此之前没有任何东西会报错：写错行号，尺子照样全绿，出片照样花钱。

判据（全部零网络、零费用）：

    甲 **锚句**：每条规则必须在 `QUOTES` 里有一句**从官方原文逐字复制**的摘录
    乙 锚句必须能在出处文件里逐字找到（找不到 = 改写/翻译过，红）
    丙 锚句找到的行必须落在 RULES 声明的行号范围内（落在别处 = 行号错，红，报真实行号）
    丁 出处文件必须登记在 DOCS 里，且文件存在；行号不得越界
    戊 单行引用的那一行不能是空行 / 标题 / 结构行；范围引用至少一行合格
    己 出处段解析不出行号的（`2026-10-26 真机原文` / `real:494b1c28`）→ 黄

🩸 2026-10-29 为什么加甲–丙：只判「行号指向正文」挡不住「行号对、说的不是这条规则」。
实测 H3 `E5` 我先记 213（标题）→ 改 215（正文，但讲的是 T2VA 指南）→ 真正在 **218**；
`E8` 记 27（空行）→ 改 28（**表格表头**）→ 真正在 **26**。
两次都是「正文行」，旧判据全放行。**锚句一绑，这两处立刻红。**

用法：
    python scripts/ruler_sources.py --model h3
    python scripts/ruler_sources.py --model volc20 --force

退出码：0 = 无红；1 = 有红；2 = 没点名型号。
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _model_gate import sel_or_exit  # noqa: E402

BACK = Path(__file__).resolve().parents[1]

# 出处里的短名 → 官方原文快照。键必须与 RULES 的 src 字段逐字一致。
DOCS: dict[str, dict[str, Path]] = {
    "volc20": {
        "sd20-guide": Path("D:/tmp/official/sd20/guide.md"),
        "sd2-pe": Path("D:/tmp/official/sd20/skill-sd2-pe.md"),
        # 🩸 2026-10-29：从 `D:/tmp/clone_diag/` 收进官方目录并登记 MANIFEST
        #   （分离门：生产代码不许引用 official/ 之外的资料）。
        "las_cn.md": Path("D:/tmp/official/sd20/las_cn.md"),
    },
    "volc25": {
        "sd25-pe": Path("D:/tmp/official/sd25/skill-sd25-pe.md"),
        "sd25-guide": Path("D:/tmp/official/sd25/guide.md"),
    },
    "h3": {
        "ref-en": Path("D:/tmp/official/h3/ref-en.txt"),
        "base-en": Path("D:/tmp/official/h3/base-en.txt"),
        "h3-skill": Path("D:/tmp/official/h3/h3-prompt-writing-SKILL.md"),
        # 🩸 2026-10-30：`text` ≤7000 是 **API 硬限制**（不分 base/ref）。
        #   base 尺子早就有 B4 指这条，ref 尺子一条都没有 → 9,927 字符的成品被判绿。
        "api-create": Path("D:/tmp/official/h3/api-create-2026-10-28.md"),
    },
}

RULER_FILE = {
    "volc20": BACK / "scripts" / "ruler_sd20.py",
    "volc25": BACK / "scripts" / "ruler_sd25.py",
    # 🩸 2026-10-29：h3 的规则本体搬到了 `app/services/models/h3_ref.py`
    #   （生产 `/prompt/convert` 要 import，`scripts/` 不在包里，见 `h3_base.py:17`）。
    #   下面用 AST 读 **字面量**，`import` 进来的东西它扫不到 —— 所以指向真身。
    "h3": BACK / "app" / "services" / "models" / "h3_ref.py",
}

# 🩸 2026-10-29：规则表**用 AST 读，不用正则**。
#   原来用正则 `("([ERT]\d+)" ...)`，前缀写死成 E/R/T，**整批漏掉了 2.5 的
#   C/K/G/P/F/W 系列**（我自己以为 9 条，实际 41 条）。
#   正则漏抓是静默的 —— 所以这里改成读语法树：`RULES` 有几个元素就读几个，
#   并且把「元素总数」和「字段解析成功数」一起返回，**不相等就报红**。
def load_rules(src_file: Path) -> tuple[list[tuple], int]:
    """返回 (规则列表, `RULES` 字面量里的元素总数)。两数不等 = 有元素没解析出来。"""
    tree = ast.parse(src_file.read_text(encoding="utf-8"))
    for node in tree.body:
        if (isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "RULES"
                        for t in node.targets)
                and isinstance(node.value, (ast.List, ast.Tuple))):
            total = len(node.value.elts)
            rows = []
            for elt in node.value.elts:
                if not isinstance(elt, (ast.Tuple, ast.List)) or len(elt.elts) < 4:
                    continue
                vals = []
                for e in elt.elts[:4]:
                    if isinstance(e, ast.Constant) and isinstance(e.value, str):
                        vals.append(e.value)
                    else:
                        break
                if len(vals) == 4:
                    rows.append(tuple(vals))
            return rows, total
    return [], 0

# 出处段里的文档引用：`名字:N` / `名字:N-M` / `名字:N/:M` / `名字:N,M`
REF_PAT = re.compile(
    r"([A-Za-z0-9_\-]+\.?[A-Za-z0-9_\-]*)\s*:\s*(\d+)"
    r"(\s*-\s*\d+)?((?:\s*[/,]\s*:?\s*\d+)*)")
EXTRA_PAT = re.compile(r"[/,]\s*:?\s*(\d+)")

SEP = "·"


def is_body(t: str) -> bool:
    """这一行是不是「正文」——标题、纯加粗、分割线、围栏、表格分隔行都不算。"""
    s = t.strip()
    if not s:
        return False
    if s.startswith("#"):
        return False
    if re.fullmatch(r"\*\*[^*]{1,40}\*\*", s):
        return False
    if re.fullmatch(r"-{3,}|\*{3,}", s):
        return False
    if re.fullmatch(r"\|[\s\-:|]+\|", s):
        return False
    if s.startswith("```"):
        return False
    return len(s) >= 8


def parse_seg(seg: str) -> list[tuple[str, int, int]]:
    """一段出处 → [(键, 起始行, 结束行)]。"""
    out = []
    for m in REF_PAT.finditer(seg):
        key, a = m.group(1), int(m.group(2))
        end = a
        if m.group(3):
            end = int(m.group(3).replace("-", "").strip())
        out.append((key, a, max(a, end)))
        for extra in EXTRA_PAT.findall(m.group(4) or ""):
            out.append((key, int(extra), int(extra)))
    return out


def load_quotes(src_file: Path) -> dict[str, str]:
    """从尺子源码里取 `QUOTES` 字面量。没有就返回空表（调用方据此报红）。"""
    tree = ast.parse(src_file.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "QUOTES" for t in node.targets):
            try:
                got = ast.literal_eval(node.value)
            except ValueError:
                return {}
            return {str(k): str(v) for k, v in got.items()}
    return {}


def check_quote(quote: str, key: str, a: int, b: int,
                docs: dict[str, Path]) -> tuple[str, str]:
    """锚句必须逐字出现在 `key:a-b` 里。返回 (`绿`|`红`, 说明)。"""
    p = docs.get(key)
    if p is None or not p.exists():
        return "红", f"锚句无处可查：出处文件 {key} 未登记或不存在"
    lines = p.read_text(encoding="utf-8", errors="replace").split("\n")
    hits = [i + 1 for i, t in enumerate(lines) if quote in t]
    if not hits:
        return "红", (f"锚句在 {key} 里**找不到**（改写/翻译过？）：{quote!r}")
    inside = [n for n in hits if a <= n <= b]
    if inside:
        return "绿", ""
    span = f"{a}" if a == b else f"{a}-{b}"
    return "红", (f"锚句确实在 {key}，但在第 {hits[0]} 行，"
                  f"不是记的 {key}:{span}")


def judge(key: str, a: int, b: int, docs: dict[str, Path]) -> tuple[str, str]:
    """返回 (`绿`|`黄`|`红`, 说明)。"""
    p = docs.get(key)
    if p is None:
        return "红", f"出处文件未登记：{key}"
    if not p.exists():
        return "红", f"原文文件不存在：{p}"
    lines = p.read_text(encoding="utf-8", errors="replace").split("\n")
    if a > len(lines):
        return "红", f"{key}:{a} 越界（文件只有 {len(lines)} 行）"
    seg = lines[a - 1:min(b, len(lines))]
    if not any(x.strip() for x in seg):
        return "红", f"{key}:{a} 是空行"
    body = [x for x in seg if is_body(x)]
    if not body:
        return "红", f"{key}:{a} 是标题/结构行：{seg[0].strip()[:40]!r}"
    return "绿", ""


def main() -> int:
    model = sel_or_exit()
    docs = DOCS[model]
    src_file = RULER_FILE[model]
    rules, n_elts = load_rules(src_file)

    quotes = load_quotes(src_file)
    n_green = n_yellow = n_red = 0
    rows: list[str] = []
    for rid, sev, name, srcs in rules:
        name = " ".join(name.split())
        verdicts: list[tuple[str, str]] = []

        # ── 甲/乙/丙：锚句（2026-10-29 主线）
        all_refs = [r for raw in srcs.split(SEP) for r in parse_seg(raw.strip())]
        q = quotes.get(rid, "")
        if not q:
            verdicts.append(("红", "缺锚句 —— QUOTES 里没有这条规则（许写行号不许不写原文）"))
        elif not all_refs:
            verdicts.append(("红", "记的出处解析不出行号，锚句无处比对"))
        else:
            why = ""
            for key, a, b in all_refs:
                mark, why = check_quote(q, key, a, b, docs)
                if mark == "绿":
                    break
            else:
                verdicts.append(("红", why))

        # ── 丁/戊/己：出处本身是否可点开
        for raw in srcs.split(SEP):
            seg = raw.strip()
            if not seg:
                continue
            refs = parse_seg(seg)
            if not refs:
                verdicts.append(("黄", f"{seg} —— 解析不出行号（非文档出处）"))
                continue
            for key, a, b in refs:
                mark, why = judge(key, a, b, docs)
                if mark != "绿":
                    verdicts.append((mark, why))

        red = [v for v in verdicts if v[0] == "红"]
        yel = [v for v in verdicts if v[0] == "黄"]
        if red:
            n_red += 1
        elif yel:
            n_yellow += 1
        else:
            n_green += 1
        if red or yel:
            rows.append(f"\n[{rid}][{sev}] {name}")
            rows.append(f"  记的出处：{srcs}")
            for mark, why in red + yel:
                rows.append(f"   {'红' if mark == '红' else '黄'} {why}")

    print("\n".join(rows))
    total = len(rules)

    # ── 自证：**我扫全了吗**。这是我 2026-10-29 漏掉 32 条的根因 ——
    #    判据只报「某条规则错」，报不了「它自己漏扫了规则」。
    if n_elts != total:
        print(f"\n⛔ 分母对不上：`RULES` 字面量里有 **{n_elts}** 条，"
              f"只解析出 **{total}** 条 —— 有元素的字段结构不对（缺 4 个字符串字段），"
              f"判据扫不全 → 本型号判红。")
        return 1

    print(f"\n出处判据（{model}）：规则 {total} 条 —— "
          f"绿 {n_green} / 黄 {n_yellow} / 红 {n_red}")
    print(f"（{n_green + n_yellow + n_red}/{total} 条规则判过 —— 不许拿空集充数）")
    print(f"分母自证：`RULES` 字面量 {n_elts} 条 = 判据扫到 {total} 条 ✅")
    if not quotes:
        print(f"⛔ 这个型号没有 QUOTES 表：锚句判据未生效，"
              f"上面只跑了「行号可点开」，**不构成出处核验 → 本型号判红**。")
        return 1
    print(f"锚句判据：{len(quotes)}/{total} 条规则有锚句；"
          f"缺 {total - len(quotes)} 条。")
    return 0 if n_red == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
