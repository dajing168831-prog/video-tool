# -*- coding: utf-8 -*-
"""H3 创作模式（T2VA / I2VA / FL2VA / L2VA）的**判据本体** —— 22 条规则（B12 已于 2026-10-30 撤回，见 docs/_archive）。

与 `h3_compile.py`（手写入口三段式，改片）的判据（`ruler_h3_handwrite.py`）
互不引用：同一家模型，两种模式规则**方向相反**（风格句 base 写在 `[Shot 1]` 之内
`base-en:78`，ref 写在之前 `ref-en:230`），合并必然抄错一边。

官方依据：`data/official/h3/base-en.txt`（222 行，与官方 skill 同一份）。
规则编号 B1–B28 与 `docs/PROMPT-AUDIT-H3-BASE.md` 一一对齐。

🩸 这里只放**规则**。官方语料校准、正反样本探针、多变数扫描、全维度穷举
都留在 `scripts/ruler_h3_base.py`（那些是测试代码，生产不调用）。

🩸 为什么规则要进 `app/`（2026-10-29）：生产请求路径要"产出先过尺子，有红就重试"，
而 `scripts/` 不在包里，生产 import 不到。
"""
from __future__ import annotations

import re

from . import h3_base_compile as hbc


FIELDS = hbc.FIELDS
TEXT_LIMIT = hbc.TEXT_LIMIT

#: `base-en:78` 官方列举的常见风格（**闭集之外的写法不判红**，只判黄）。
STYLE_WORDS = ("cinematic", "live-action", "2d-animated", "3d cg",
               "claymation", "watercolor", "vintage film")

#: `base-en:92` 官方 5 种切镜动词。
CUT_VERBS = ("the camera cuts to", "the shot cuts to", "the shot transitions to",
             "the shot changes to", "the shot switches to")

#: `base-en:142` 连续性措辞（`<scenetrans>` 必须配一句）。
TRANS_WORDS = ("continues seamlessly across the cut", "continues uninterrupted",
               "carries over from the previous shot", "remains audible across")

_CJK = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")
_EMOJI = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF"
                    "\U00002B00-\U00002BFF\U0001F1E6-\U0001F1FF\uFE0F\u200D]")
_BULLET = re.compile(r"[•●▪◦‣∙]")
_TILDE_RUN = re.compile(r"[~～〜]{2,}")


# ---------------------------------------------------------------- 拆段
def fields(p: str) -> dict[str, str]:
    """按 `字段名:` 行把三字段切开；指令行（在字段之前）不会进来。"""
    out: dict[str, str] = {}
    cur = None
    buf: list[str] = []
    for line in p.splitlines():
        m = re.match(r"^\s*([a-z_]+):\s*(.*)$", line)
        if m and m.group(1) in FIELDS:
            if cur:
                out[cur] = "\n".join(buf).strip()
            cur, buf = m.group(1), [m.group(2)] if m.group(2) else []
        elif cur is not None:
            buf.append(line)
    if cur:
        out[cur] = "\n".join(buf).strip()
    return out


def desc_of(p: str) -> str:
    return fields(p).get("integrated_multimodal_description", "")


def _sentences(s: str) -> list[str]:
    """断句。🩸 `[Shot N]` 也当句子边界 —— 它前面常常没有句号
    （`…morning.</d> [Shot 2] At 00:05.000, the camera cuts to …`），
    不切开的话下一镜的切镜动词会粘到上一镜的运镜句里（2026-10-29 校准抓到 B12 假绿）。"""
    s = re.sub(r"(?=\[Shot \d+\])", "\n", s or "")
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+|\n", s) if x.strip()]


def _d_blocks(p: str) -> list[tuple[int, int, str]]:
    return [(m.start(), m.end(), m.group(1))
            for m in re.finditer(r"<d>(.*?)</d>", p, re.S)]


def _first_line(p: str) -> str:
    for line in p.splitlines():
        if line.strip():
            return line.strip()
    return ""


# ---------------------------------------------------------------- 规则
def b1_fields(p, ctx):
    """三个字段齐全且顺序固定（`base-en:36-44`、`h3-skill:23`）。"""
    got = [m.group(1) for m in re.finditer(r"^\s*([a-z_]+):", p, re.M)
           if m.group(1) in FIELDS]
    miss = [f for f in FIELDS if f not in got]
    bad = []
    if miss:
        bad.append(f"缺字段：{'、'.join(miss)}")
    seq = [f for f in FIELDS if f in got]
    if seq != got[:len(seq)]:
        bad.append(f"字段顺序不对：实际 {' → '.join(got)}")
    return bad


def b2_shot1(p, ctx):
    """`integrated_multimodal_description` 必须以 `[Shot 1]` 起头（`base-en:39`、`:81`）。"""
    d = desc_of(p).lstrip()
    if not d:
        return []                      # 缺整段由 B1 报，不重复
    if not d.startswith("[Shot 1]"):
        return [f"描述不是以 [Shot 1] 起头：{d[:60]}"]
    return []


def b3_english(p, ctx):
    """除 `<d>` 与英文双引号内，正文一律英文（`h3-skill:33`）。

    这条同时把 B23（画面文字）按住：中文只许出现在 `<d>` 或双引号里，
    别处出现中文 = 不是对白、又不是画面文字。
    """
    s = re.sub(r"<d>.*?</d>", "", p, flags=re.S)
    s = re.sub(r'"[^"\n]*"', "", s)
    hit = _CJK.search(s)
    if hit:
        i = hit.start()
        return [f"`<d>` 与双引号之外出现非英文：…{s[max(0, i - 25):i + 25]}…"]
    return []


def b4_length(p, ctx):
    """`text` ≤ 7000 字符（`api-create:407`）。"""
    return [f"正文 {len(p)} 字符，超过官方上限 {TEXT_LIMIT}"] if len(p) > TEXT_LIMIT else []


def b5_no_instr(p, ctx):
    """T2VA 没有指令行（`base-en:14`）。"""
    if (ctx or {}).get("mode") != "t2va":
        return []
    first = _first_line(p)
    if first.startswith("For the target video, at 0.00 seconds") \
            or first.startswith("How the reference pictures align"):
        return [f"T2VA 不该有指令行，但第一行是：{first[:60]}"]
    return []


def b6_i2va(p, ctx):
    """I2VA 指令行必须逐字（`base-en:16-20`）。"""
    if (ctx or {}).get("mode") != "i2va":
        return []
    want = hbc.instruction_line("i2va")
    got = _first_line(p)
    if got != want:
        return [f"I2VA 指令行不是官方那句\n        应为：{want}\n        实为：{got[:90]}"]
    return []


_FL2VA_RE = re.compile(
    r"^How the reference pictures align with the target video — "
    r"Picture 1 \(from Shot 1\) aligns with the 0\.00-second mark of the target "
    r"video; Picture 2 \(from Shot \d+\) aligns with the \d+\.\d{2}-second mark "
    r"of the target video\.$")
_L2VA_RE = re.compile(
    r"^How the reference pictures align with the target video — "
    r"<Picture 1> \(from \[Shot \d+\]\) aligns with the \d+\.\d{2}-second mark "
    r"of the target video\.$")


def b7_fl2va(p, ctx):
    """FL2VA 指令行形态（`base-en:22-26`）。"""
    if (ctx or {}).get("mode") != "fl2va":
        return []
    got = _first_line(p)
    return [] if _FL2VA_RE.match(got) else [f"FL2VA 指令行形态不对：{got[:90]}"]


def b8_l2va(p, ctx):
    """L2VA 指令行形态（`base-en:28-32`）。"""
    if (ctx or {}).get("mode") != "l2va":
        return []
    got = _first_line(p)
    return [] if _L2VA_RE.match(got) else [f"L2VA 指令行形态不对：{got[:90]}"]


def b9_instr_blank(p, ctx):
    """指令行必须是第一行，其后一个空行（`base-en:34`）。T2VA 无指令行。"""
    mode = (ctx or {}).get("mode")
    if mode == "t2va":
        return []
    lines = p.splitlines()
    if not lines or not lines[0].strip():
        return ["指令行不在第一行"]
    if len(lines) > 1 and lines[1].strip():
        return ["指令行后面没有空行（`base-en:34`：followed by one blank line）"]
    return []


def b10_shots(p, ctx):
    """`[Shot 1]` 无时间戳；后续 `At MM:SS.mmm`；编号连续、切点严格递增（`base-en:86`）。

    🩸 2026-10-29 校准抓到自己的假红：I2VA / L2VA 的**指令行里也写着 `(from [Shot 1])`**
    （`base-en:19`、`base-en:31`），那是帧锚来源，不是镜头标号。以前把整篇当扫描范围，
    Case 2 / Case 4 双双判红。**镜头标号只在描述字段之后数**。
    """
    i = p.find(FIELDS[0] + ":")
    body = p[i:] if i >= 0 else p
    marks = list(re.finditer(r"\[Shot (\d+)\](.{0,18})", body))
    if not marks:
        return ["一个 `[Shot N]` 都没有"]
    bad: list[str] = []
    times: list[float] = []
    for i, m in enumerate(marks):
        n = int(m.group(1))
        tail = m.group(2)
        if n != i + 1:
            bad.append(f"镜头编号不连续：第 {i + 1} 个标的是 [Shot {n}]")
        if i == 0:
            if re.match(r"\s*At\s", tail):
                bad.append("[Shot 1] 不该带时间戳")
            continue
        tm = re.match(r"\s*At (\d{2}):(\d{2}\.\d{3}),", tail)
        if not tm:
            bad.append(f"[Shot {n}] 没按 `At MM:SS.mmm,` 写时间戳：`[Shot {n}]{tail}`")
            continue
        times.append(int(tm.group(1)) * 60 + float(tm.group(2)))
    for a, b in zip(times, times[1:]):
        if b <= a:
            bad.append(f"切点没有严格递增：{a:.3f}s → {b:.3f}s")
    return bad


def b11_cut_verb(p, ctx):
    """切镜动词只用官方 5 种（`base-en:92`）。

    🩸 2026-10-29 校准抓到假绿：原来用 `([^.]{0,80})\\.` 卡长度，官方长句超过 80 字符
    → 一个都没匹配上 → 规则从来没跑过。改成"时间码之后到下一个句号"。

    🩸 2026-10-31 真机抓到假红：上面那个改法扫的是**所有** `MM:SS.mmm,`，于是镜头
    **内部**的事件时间码（`At 00:06.700, the first half … appears gently in …`）也被
    当成切点，报了 5 条「切镜动词不在官方 5 种里」—— 而那份稿的 4 处真切点全部是
    官方原句 `the camera cuts to`。官方 `base-en:86` 说的是「**begin each one** with a
    strictly increasing cut time」：`At MM:SS.mmm` 只属于**镜头开头**。只扫紧跟
    `[Shot N]` 的那一个。
    """
    bad = []
    for m in re.finditer(r"\[Shot \d+\]\s+At\s+\d{2}:\d{2}\.\d{3}[,，]?", p):
        head = p[m.end():m.end() + 300].split(".")[0]
        if not any(v in head.lower() for v in CUT_VERBS):
            bad.append(f"切镜动词不在官方 5 种里：…{head.strip()[:80]}")
    return bad


#: 官方 20 个运镜**表达名**（`base-en:98-111` 表格第一列，小写）。用词边界匹配，
#: 免得 `pov` 在 `poverty` 里被当成运镜词。

def b13_amp_speed(p, ctx):
    """幅度只许 small/large，速度只许 slow/fast（`base-en:113-115`）。"""
    bad = []
    for m in re.finditer(r"with\s+([A-Za-z-]+)\s+amplitude", p):
        if m.group(1).lower() not in hbc.AMPLITUDE:
            bad.append(f"幅度词不在官方闭集：with {m.group(1)} amplitude")
    for m in re.finditer(r"at\s+([A-Za-z-]+)\s+speed", p):
        if m.group(1).lower() not in hbc.SPEED:
            bad.append(f"速度词不在官方闭集：at {m.group(1)} speed")
    return bad


#: 目标成分前面常见的限定词 —— 紧跟在这些词前面却没连接词，就是"粘上去"了。
_DET = r"(?:the|a|an|her|his|their|its|this|that)\b"


def b28_target_connector(p, ctx):
    """运镜句后接目标成分，必须有连接词（`base-en:120-124` 三句例句：toward / , revealing / as）。

    🩸 为什么加这条（2026-10-29）：三家真机对照跑了 15 份产出，其中 6 份写成
    `…at slow speed the man on the platform.` —— 连接词丢了，句子读不通，
    而当时的规则一条都没响（词表类只查词，不查**句子能不能读**）。
    """
    # `follows <目标>` 本身语法完整（目标就是宾语），不会缺连接词 → 排除
    verbs = sorted((v for v in hbc.camera_verbs() if v != "follows"),
                   key=len, reverse=True)
    mot = "|".join(re.escape(v) for v in verbs)
    mid = (r"(?:\s+with\s+(?:small|large)\s+amplitude"
           r"|\s+at\s+(?:slow|fast)\s+speed)*")
    pat = r"the camera\s+(?:%s)%s\s+(%s)" % (mot, mid, _DET)
    return [f"运镜后直接接名词、缺连接词（应 toward / as / 逗号）："
            f"…{p[max(0, m.start() - 12):m.end() + 18]}"
            for m in re.finditer(pat, p, flags=re.I)]


def b14_no_trailing_tags(p, ctx):
    """运镜不许当标签堆在句尾（`base-en:117`「rather than stacked as separate labels」）。"""
    pat = r"[,.;]\s*(%s)\b" % "|".join(re.escape(v) for v in
                                        sorted(hbc.CAMERA_PHRASES.values(),
                                               key=len, reverse=True))
    bad = []
    for m in re.finditer(pat, p):
        bad.append(f"运镜当成句尾标签了：…{p[max(0, m.start() - 20):m.start()]}[{m.group(1)}]")
    return bad


def b15_style_in_shot1(p, ctx):
    """风格写在 `[Shot 1]` 之内（`base-en:78`）。黄。

    ⚠️ 只认官方列举的那几个风格词（`base-en:78`）—— 认不出不判红，
    因为官方那句是"state the overall style"，不是"必须用这几个词"。
    """
    d = desc_of(p).lstrip()
    if not d.startswith("[Shot 1]"):
        return []
    head = d[:120].lower()
    if re.search(r"^\[shot 1\]\s*(no style|n/a)", head):
        return []
    if not any(w in head for w in STYLE_WORDS):
        return [f"[Shot 1] 开头没看到官方列举的风格词：{d[:70]}"]
    return []


def b17_speaker_ids(p, ctx):
    """`(Sx)` 从 1 开始、按出现顺序递增、不复用不跳号（`base-en:127`）。"""
    ids = []
    for m in re.finditer(r"\((S\d+(?:,\s*S\d+)*)\)", p):
        for x in m.group(1).split(","):
            ids.append(int(x.strip()[1:]))
    seen, nxt, bad = set(), 1, []
    for i in ids:
        if i in seen:
            continue
        if i != nxt:
            bad.append(f"说话人编号跳号/乱序：期望 S{nxt}，出现 S{i}")
        seen.add(i)
        nxt = max(nxt, i) + 1
    return bad


def b19_d_only_text(p, ctx):
    """`<d>` 外必须有说话来源；`<d>` 里只放语言标签 + 原词（`base-en:129`）。"""
    bad = []
    last = 0
    for st, en, inner in _d_blocks(p):
        before = p[last:st]
        seg = re.split(r"(?<=[.!?])\s+", before)[-1] if before else ""
        if not re.search(r"\(S\d+(?:,\s*S\d+)*\)|<Audio \d+>", seg):
            bad.append(f"`<d>` 前没有说话来源：…{before[-50:]}<d>{inner[:30]}</d>")
        if not re.match(r"\s*\[[A-Za-z]+\]", inner):
            bad.append(f"`<d>` 开头没有 [语言] 标签：{inner[:40]}")
        if re.search(r"</?(?:d|Picture|Video|Audio|Subject|scenetrans|cutoff)\b", inner):
            bad.append(f"`<d>` 里出现了标号（会提前闭合）：{inner[:40]}")
        last = en
    return bad


def b21_voiceover(p, ctx):
    """画外音固定句 + 紧跟"嘴唇紧闭"（`base-en:136-140`）。"""
    bad = []
    for m in re.finditer(r"says? in (?:an? )?off-screen voiceover|off-screen voiceover", p):
        tail = p[m.end():m.end() + 400]
        if "lips" not in tail or "closed" not in tail:
            bad.append("画外音后面没写「嘴唇紧闭」：…"
                       + p[max(0, m.start() - 40):m.end() + 60])
    if "off-screen voiceover" in p and "says in an off-screen voiceover" not in p:
        bad.append("画外音没用官方固定短语 `says in an off-screen voiceover`")
    return bad


def b22_continuity(p, ctx):
    """`<scenetrans>` 要配连续性措辞；`<cutoff>` 要说被片尾截断（`base-en:142`）。"""
    bad = []
    if "<scenetrans>" in p:
        seg = re.split(r"(?<=[.!?])\s+", p)
        for s in seg:
            if "<scenetrans>" in s and not any(w in s.lower() for w in TRANS_WORDS):
                bad.append(f"`<scenetrans>` 没配连续性措辞：{s[:80]}")
    if "<cutoff>" in p:
        seg = re.split(r"(?<=[.!?])\s+", p)
        for s in seg:
            if "<cutoff>" in s and not re.search(r"cut off|truncat|end of the video",
                                                 s.lower()):
                bad.append(f"`<cutoff>` 没说被片尾截断：{s[:80]}")
    return bad


def b24_soundscape(p, ctx):
    """`overall_soundscape` 1–4 句（`base-en:154`）。"""
    v = fields(p).get("overall_soundscape", "")
    if not v or v == "N/A":
        return []
    n = len(_sentences(v))
    return [f"overall_soundscape 写了 {n} 句，官方上限 4 句"] if n > 4 else []


def b25_music(p, ctx):
    """`non_diegetic_music` 1–3 句（`base-en:162`）。"""
    v = fields(p).get("non_diegetic_music", "")
    if not v or v == "N/A":
        return []
    n = len(_sentences(v))
    return [f"non_diegetic_music 写了 {n} 句，官方上限 3 句"] if n > 3 else []


def b26_na_rule(p, ctx):
    """`overall_soundscape` 只在用户明确要求全静音时才 N/A（`base-en:154`）。"""
    v = fields(p).get("overall_soundscape", "").strip()
    if v == "N/A" and not (ctx or {}).get("silence"):
        return ["overall_soundscape 写了 N/A —— 官方只在用户明确要求全静音时才允许"]
    return []


RULES = [
    ("B1", "红", "三字段齐全且顺序固定", "base-en:36-44", b1_fields),
    ("B2", "红", "描述以 [Shot 1] 起头", "base-en:39", b2_shot1),
    ("B3", "红", "除 <d> 与双引号外写英文", "h3-skill:33", b3_english),
    ("B4", "红", "正文 ≤7000 字符", "api-create:407", b4_length),
    ("B5", "红", "T2VA 没有指令行", "base-en:14", b5_no_instr),
    ("B6", "红", "I2VA 指令行逐字", "base-en:16-20", b6_i2va),
    ("B7", "红", "FL2VA 指令行形态", "base-en:22-26", b7_fl2va),
    ("B8", "红", "L2VA 指令行形态", "base-en:28-32", b8_l2va),
    ("B9", "红", "指令行是第一行且后跟空行", "base-en:34", b9_instr_blank),
    ("B10", "红", "[Shot 1] 无时间戳、后续 At MM:SS.mmm 递增", "base-en:86", b10_shots),
    ("B11", "红", "切镜动词用官方 5 种", "base-en:92", b11_cut_verb),
    ("B13", "红", "幅度/速度只用官方词", "base-en:113-115", b13_amp_speed),
    ("B14", "红", "运镜不堆成句尾标签", "base-en:117", b14_no_trailing_tags),
    ("B28", "红", "运镜后接目标成分必须有连接词", "base-en:120-124", b28_target_connector),
    ("B15", "黄", "风格写在 [Shot 1] 之内", "base-en:78", b15_style_in_shot1),
    ("B17", "红", "(Sx) 从 1 起、按顺序、不跳号", "base-en:127", b17_speaker_ids),
    ("B19", "红", "<d> 外有说话来源、<d> 内只有标签+原词", "base-en:129", b19_d_only_text),
    ("B21", "红", "画外音固定句 + 嘴唇紧闭", "base-en:136-140", b21_voiceover),
    ("B22", "红", "scenetrans/cutoff 配对应措辞", "base-en:142", b22_continuity),
    ("B24", "黄", "soundscape 不超过 4 句", "base-en:154", b24_soundscape),
    ("B25", "黄", "music 不超过 3 句", "base-en:162", b25_music),
    ("B26", "黄", "soundscape 不滥用 N/A", "base-en:154", b26_na_rule),
]


# ================================================================ 原文锚句
QUOTES = {
    "B1": "Use `integrated_multimodal_description`, `overall_soundscape`, and `non_diegetic_music` in the order",
    "B2": "At the beginning of `[Shot 1]`, state the overall style and initial composition",
    "B3": "Write all six rewrite sections in English",   # 见下方注
    "B4": "最多 7000 个字符",
    "B5": "has no image-alignment instruction and begins directly with the three core fields",
    "B6": "is fully referenced",
    "B7": "How the reference pictures align with the target video",
    "B8": "aligns with the S.SS-second mark of the target video",
    "B9": "The instruction must be the first line of the final prompt, followed by one blank line",
    "B10": "Do not add a timestamp to the first shot.",
    "B11": "For ordinary cuts, use `the camera cuts to`",
    "B13": "Amplitude defines the range of compositional change",
    "B14": "rather than stacked as separate labels at the end of a sentence",
    "B15": "state the overall style and initial composition",
    "B17": "A speaker keeps the same ID across shots",
    "B19": "Inside `<d>`, include only the language tag and the actual user-provided spoken content",
    "B21": "says in an off-screen voiceover",
    "B22": "Use `<scenetrans>` at the connecting points in both parts",
    "B24": "Use 1–4 English sentences in one continuous paragraph",
    "B25": "Use 1–3 English sentences to describe background music",
    "B26": "Use `N/A` only when the user explicitly requests complete silence",
}


def check(p: str, ctx: dict | None = None) -> list[tuple[str, str, str, str, list[str]]]:
    out = []
    for rid, sev, name, src, fn in RULES:
        try:
            issues = fn(p, ctx or {})
        except Exception as e:                    # 尺子自己崩了要看见，不许静默
            issues = [f"判据异常：{e}"]
        if issues:
            out.append((rid, sev, name, src, issues))
    return out
