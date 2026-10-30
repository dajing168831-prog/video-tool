# -*- coding: utf-8 -*-
"""H3 Ref2VA（六段式）**判据本体** —— 23 条规则 E1–E23。

官方依据：`D:/tmp/official/h3/ref-en.txt`（341 行，官方 skill
`h3-prompt-writing` 的 references/ref-en.txt）。

与 `h3_base.py`（三字段 B 系）**互不引用**：同一家模型，两种模式规则方向相反
（风格句 base 写在 `[Shot 1]` 之内 `base-en:78`，ref 写在之前 `ref-en:230`），
合并必然抄错一边。

🩸 这里只放**规则**。官方语料校准、正反样本探针、多变数扫描留在
`scripts/ruler_h3.py`（那些是测试代码，生产不调用）。

🩸 为什么要搬进来（2026-10-29）：`/prompt/convert` 的六段式那一路要
「产出先过尺子，有红就回灌重试」，而 `scripts/` 不在包里，生产 import 不到。
"""
from __future__ import annotations

import re

SECTIONS = ["subject_definitions", "summary", "retention_analysis",
            "detailed_description", "overall_soundscape", "non_diegetic_music"]
VISIBLE_MARKS = {"fully_preserved", "partially_preserved", "attribute_transfer",
                 "weak_reference"}
AUDIO_MARKS = {"fully_copy", "partially_copy", "reference", "weak_reference"}
TASK_TYPES = {"keyframe completion", "reference generation", "video editing",
              "video continuation", "audio reuse", "audio reference"}


# ---------------------------------------------------------------- 段落拆分
def fields(p: str) -> dict[str, str]:
    """按 `name:` 行把六段切开；返回 {段名: 正文}（缺的段不在字典里）。"""
    out: dict[str, str] = {}
    cur = None
    buf: list[str] = []
    for line in p.splitlines():
        m = re.match(r"^\s*([a-z_]+):\s*(.*)$", line)
        if m and m.group(1) in SECTIONS:
            if cur:
                out[cur] = "\n".join(buf).strip()
            cur, buf = m.group(1), [m.group(2)] if m.group(2) else []
        elif cur is not None:
            buf.append(line)
    if cur:
        out[cur] = "\n".join(buf).strip()
    return out


def genre_of(p: str) -> str:
    """只认 Ref2VA（六段式）；别的形态（base 三字段）这把尺子不管。"""
    return "ref2va" if "subject_definitions" in p else "other"


def _split_sentences(s: str) -> list[str]:
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+|\n", s) if x.strip()]


# ---------------------------------------------------------------- 规则
def e1_sections(p, ctx):
    """六段齐全且顺序正确（`ref-en:13-22`）。"""
    got = [s for s in SECTIONS if re.search(rf"^\s*{s}:", p, re.M)]
    bad = [s for s in SECTIONS if s not in got]
    if bad:
        return [f"缺段：{'、'.join(bad)}"]
    order = [re.search(rf"^\s*{s}:", p, re.M).start() for s in SECTIONS]
    if order != sorted(order):
        return ["六段顺序不对"]
    return []


def e2_task_prefix(p, ctx):
    """`summary` 必须以方括号任务类型前缀开头（`ref-en:126-128`）。"""
    s = (fields(p).get("summary") or "").strip()
    m = re.match(r"^\[([^\]]+)\]", s)
    if not m:
        return ["summary 没有 `[任务类型]` 前缀"]
    types = [t.strip() for t in m.group(1).split("+")]
    unk = [t for t in types if t not in TASK_TYPES]
    if unk:
        return [f"任务类型不在官方表里：{'、'.join(unk)}"]
    if len(types) != len(set(types)):
        return ["任务类型重复"]
    return []


def e3_edit_type(p, ctx):
    """编辑母版必须写 `video editing`；原声还在就要加 `audio reuse`（`ref-en:136-153`）。

    ctx["audio"]: "reuse"（原声保留）/ "reference"（只参考音色）/ None（不知道，跳过）。
    """
    if not ctx.get("edit_master"):
        return []
    s = (fields(p).get("summary") or "").strip()
    m = re.match(r"^\[([^\]]+)\]", s)
    if not m:
        return []
    types = {t.strip() for t in m.group(1).split("+")}
    bad = []
    if "video editing" not in types:
        bad.append("编辑母版却没写 `video editing`")
    a = ctx.get("audio")
    if a == "reuse" and "audio reuse" not in types:
        bad.append("原片音轨还在，却缺 `audio reuse`（ref-en:136「编辑源视频时，"
                   "原声仍可听见就要用 audio reuse」）")
    if a == "reference" and "audio reference" not in types:
        bad.append("只参考音色，却缺 `audio reference`")
    return bad


def e4_edit_sentence(p, ctx):
    """编辑任务的 summary 在前缀之后必须以 `The target video is an edited version of <Video 1>.`
    起头（`ref-en:150-153` 原文）。"""
    if not ctx.get("edit_master"):
        return []
    s = (fields(p).get("summary") or "").strip()
    rest = re.sub(r"^\[[^\]]+\]\s*", "", s)
    if not rest.startswith("The target video is an edited version of <Video 1>."):
        return ["summary 缺少官方固定句 `The target video is an edited version of <Video 1>.`"]
    return []


def e5_shots(p, ctx):
    """`[Shot 1]` 不带时间戳；后续 `[Shot N] At MM:SS.mmm`（`ref-en:218`）。

    🩸 2026-10-30 真机跑出假红，两条一起修（改前，官方自己的示例都会被判红）：

    1. **扫全文 → 只扫 `detailed_description`**。`ref-en:218` 这条活在 §5
       "detailed_description / 5.1 Basic Format" 里；而 §4 的 `retention_analysis`
       官方示例就写着 `<Subject 4> (appears in [Shot 2], [Shot 3])`（`ref-en:325`）——
       那不是镜头标题，是出场标注。旧版扫全文，这些行一律判"缺时间戳"。
    2. **游标不再吞掉同一行后面的标号**。旧正则 `([^\\n]{0,40})` 是贪婪的，
       `[Shot 1], [Shot 2], [Shot 3]` 只匹配出 Shot 1 一格，后面的全被吃进 tail。

    3. **同一编号只看第一次出现**。我们自己的编译器把整段写成**一个自然段**，
       `[Shot N]` 就落在句子中间（不是行首）；同一编号还会在后面被回指
       （"carrying over from [Shot 2]"）。只有第一次出现才是"宣这个镜头"，
       拿它判时间戳；后面的都是回指，不该重复要求 `At`。
    """
    body = fields(p).get("detailed_description") or ""
    if not body:
        return []                      # 缺段由「六段齐全」那条管，别在这儿重复报
    first: dict[int, int] = {}         # 编号 → 第一次出现的结束位置
    for m in re.finditer(r"\[Shot (\d+)\]", body):
        first.setdefault(int(m.group(1)), m.end())
    if 1 not in first:
        return ["没有 `[Shot 1]`"]
    bad = []
    if re.match(r"\s*At\s", body[first[1]:first[1] + 40]):
        bad.append("[Shot 1] 不该带时间戳")
    for n in sorted(first):
        if n == 1:
            continue
        tail = body[first[n]:first[n] + 40]
        if not re.match(r"\s*At\s+\d{2}:\d{2}\.\d{3}", tail):
            bad.append(f"[Shot {n}] 缺 `At MM:SS.mmm`")
    return bad


def e6_marks(p, ctx):
    """`retention_analysis` 的关系标记必须用官方固定英文值（`ref-en:159-200`）。"""
    ret = fields(p).get("retention_analysis") or ""
    bad = []
    allowed = VISIBLE_MARKS | AUDIO_MARKS
    for line in ret.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^<(?:Subject|Picture|Video|Audio) \d+>[^:]*:\s*([A-Za-z_]+)", line)
        if not m:
            bad.append(f"这一行没有关系标记：{line[:40]}")
        elif m.group(1) not in allowed:
            bad.append(f"标记不在官方表里：{m.group(1)}")
    return bad


def e7_no_speaker_in_retention(p, ctx):
    """`retention_analysis` 里不许写 `(Sx)`（`ref-en:276`）。"""
    ret = fields(p).get("retention_analysis") or ""
    if re.search(r"\(S\d+\)", ret):
        return ["retention_analysis 里出现了 (Sx)"]
    return []


def e8_labels(p, ctx):
    """正文用到的标签必须在 `subject_definitions` 里定义或引用（`ref-en:27`、SKILL 输出规则
    「Avoid … unresolved reference labels」）。"""
    defs = fields(p).get("subject_definitions") or ""
    bad = []
    for kind in ("Subject", "Video", "Audio", "Picture"):
        for n in sorted({int(x) for x in re.findall(rf"<{kind} (\d+)>", p)}):
            if f"<{kind} {n}>" not in defs:
                bad.append(f"<{kind} {n}> 在正文里用到，但 definitions 里没有")
    return bad


def e9_unique_locator(p, ctx):
    """从同一 `<Video N>` 里指认的多个 subject，**定义行必须互不相同**。

    官方 `ref-en:37`：每行要说清「its label denotes、its reference role、the main
    features to follow」；`ref-en:48`：同一素材可以出多个 subject。两条合起来 ⇒
    两个人写成逐字相同的一句，等于谁也没指认（与 2.0/2.5 的方位撞车同源）。
    """
    defs = fields(p).get("subject_definitions") or ""
    seen: dict[str, list[str]] = {}
    for line in defs.splitlines():
        m = re.match(r"^\s*<(Subject \d+)> is the (.+?) in <Video \d+>", line.strip())
        if m:
            seen.setdefault(m.group(2).strip().lower(), []).append(m.group(1))
    bad = []
    for loc, subs in seen.items():
        if len(subs) > 1:
            bad.append(f"{'、'.join(subs)} 都写成「{loc}」——同一个人位，指认不了")
    return bad


def e10_dialogue_source(p, ctx):
    """`<d>` 必须有说话来源：`<Subject N> (Sx)` 或 `<Audio N>`（`ref-en:258-276`）。"""
    bad = []
    for m in re.finditer(r"<d>", p):
        head = p[max(0, m.start() - 240):m.start()]
        if not (re.search(r"\(S\d+\)", head) or re.search(r"<Audio \d+>", head)):
            bad.append("<d> 前面既没有 (Sx) 也没有 <Audio N> 作为来源")
            break
    return bad


def e11_dialogue_end(p, ctx):
    """`<d>` 内容必须以 `.` / `?` / `!` 收尾（`ref-en:270-276`）。"""
    bad = []
    for m in re.finditer(r"<d>(.*?)</d>", p, re.S):
        body = m.group(1).strip().rstrip("」』\"'）) ")
        if not body.endswith((".", "?", "!")):
            bad.append(f"台词结尾不是 . ? !：「{body[-20:]}」")
    return bad


def e14_audio_claim_needs_asset(p, ctx):
    """`summary` 里声明了音频关系，就必须真的定义 `<Audio N>` 并给它一行 retention。

    官方 `ref-en:33`：`<Audio N>` = 「An audio signal that is copied or referenced」；
    `:157`：`retention_analysis` 每个标号一行。声明 `audio reuse` 却没有音频标号，
    等于提示词指着一个**可能根本没传**的素材 —— 2026-10-21 实测代价：模型自己
    编了一套说话动作，成片音轨与原片相关系数 −0.11。
    """
    s = (fields(p).get("summary") or "").strip()
    m = re.match(r"^\[([^\]]+)\]", s)
    if not m:
        return []
    types = {t.strip() for t in m.group(1).split("+")}
    if not (types & {"audio reuse", "audio reference"}):
        return []
    defs = fields(p).get("subject_definitions") or ""
    ret = fields(p).get("retention_analysis") or ""
    bad = []
    if not re.search(r"<Audio \d+>", defs):
        bad.append("声明了音频关系，但 subject_definitions 里没有 <Audio N>")
    elif not re.search(r"^\s*<Audio \d+>[^:]*:", ret, re.M):
        bad.append("有 <Audio N> 定义，但 retention_analysis 里没有它那行")
    return bad


def e12_english_only(p, ctx):
    """除 `<d>` 外一律英文（`ref-en:5`「Write all six rewrite sections in English」）。

    官方留的例外是「画面里可见的文字」，我们这边永远不生成屏幕字（字幕一律不做），
    所以不走那个例外；哪天要往画面里写中文招牌，这条得跟着改。
    """
    strip = re.sub(r"<d>.*?</d>", "", p, flags=re.S)
    if re.search(r"[\u4e00-\u9fff]", strip):
        ch = re.search(r"[\u4e00-\u9fff].{0,10}", strip).group(0)
        return [f"<d> 之外出现中文：{ch}"]
    return []


def e13_style_before_shot(p, ctx):
    """`[Shot 1]` 之前要有 1–2 句风格定调（`ref-en:225-231`）。"""
    dd = fields(p).get("detailed_description") or ""
    i = dd.find("[Shot 1]")
    if i < 0:
        return []
    head = dd[:i].strip()
    if not head:
        return ["[Shot 1] 之前没有风格句"]
    n = len(_split_sentences(head))
    if n > 3:
        return [f"[Shot 1] 之前有 {n} 句（官方 1–2 句）"]
    return []


def e15_speaker_form(p, ctx):
    """说台词的必须是**已定义主体 / `<Audio N>` / 声音描述**，不能是 `<Video 1>`。

    官方 `ref-en:266`：「`<Subject N>` identifies the referenced subject, while
    `(Sx)` identifies the actual speaker… If the same subject speaks off-screen,
    keep the same form and mark it as `off-screen`. When the speaker does not
    correspond to a defined subject, use a stable voice description followed by
    `(Sx)`.」

    `<Video 1>` 是「被编辑的源片」这个素材，既不是主体也不是声音描述。拿它当
    说话人（`the person in <Video 1> (S1) says`）等于**声明一个没有定义行的人、
    还默认他在画内** —— 画外旁白就会被写成画内某人开口。
    两份官方样本里一次都没出现这种写法（全是 `<Subject N> (Sx)`）。
    """
    bad = []
    for m in re.finditer(r"the person in <Video \d+>\s*(\(S\d+\))", p):
        bad.append(f"说话人写成「the person in <Video 1> {m.group(1)}」"
                   f"——未定义的主体，且默认画内")
    for m in re.finditer(r"<Video \d+>\s*\(S\d+\)\s*(?:says|continues|replies)",
                         p):
        bad.append(f"拿「{m.group(0).strip()}」当说话人（<Video N> 是素材不是主体）")
    return bad


def e16_cut_order(p, ctx):
    """后续镜头的编号连续、切点时间**严格递增**（`base-en:86`）。

    原文：「Use sequential shot numbers for later shots, and begin each one with a
    strictly increasing cut time that falls within the video duration」。

    只判文本能判的部分：编号从 `[Shot 1]` 起连续，后面的时间码一个比一个大。
    **「落在时长内」判不了** —— 编辑任务的提示词里不写目标时长，段长在调用侧；
    那半条由 `video_edit` 生成 `cuts` 时按段区间裁剪（`0 < c < b - a`）保证。
    """
    # 🩸 只在 `detailed_description` 里数镜头：`retention_analysis` 的
    # `(appears in [Shot 1], [Shot 3])` 是**引用**不是镜头起点，扫全文会把
    # 引用当成第二遍镜头编号 → 假红「[Shot 1] 编号不连续」（2026-10-26 实测踩到）。
    body = fields(p).get("detailed_description") or ""
    seen: list[tuple[int, float | None]] = []
    for m in re.finditer(r"\[Shot (\d+)\](?:\s*At\s+(\d{2}):(\d{2})\.(\d{3}))?", body):
        sec = None
        if m.group(2) is not None:
            sec = int(m.group(2)) * 60 + int(m.group(3)) + int(m.group(4)) / 1000.0
        seen.append((int(m.group(1)), sec))
    if not seen:
        return []
    bad = []
    if seen[0][0] != 1:
        bad.append(f"第一镜是 [Shot {seen[0][0]}]，不是 [Shot 1]")
    prev: float | None = None
    for i, (n, sec) in enumerate(seen):
        if i and n != seen[i - 1][0] + 1:
            bad.append(f"[Shot {n}] 编号不连续（上一镜是 [Shot {seen[i - 1][0]}]）")
        if sec is not None:
            if prev is not None and sec <= prev:
                bad.append(f"[Shot {n}] 切点 {sec:.3f}s 没大于上一镜的 {prev:.3f}s")
            prev = sec
    return bad


def e17_sound_sections(p, ctx):
    """两层声音的句数上限，配乐段不写抽象词（`base-en:154-162`）。

    `base-en:154`：「Use **1–4 English sentences** in one continuous paragraph」；
    `base-en:162`：「Use **1–3 English sentences**… do not use abstract mood words
    or explain the emotional function of the score」。

    `N/A` 是官方自己给的取值（`:154` 限用户明确要求全静音，`:162` 是无画外配乐），
    见到就跳过句数判定 —— 我们的参考切片本身 `-an` 无音轨，这两段按事实写 `N/A`。
    """
    f = fields(p)
    bad = []
    snd = (f.get("overall_soundscape") or "").strip()
    mus = (f.get("non_diegetic_music") or "").strip()
    if snd and snd != "N/A":
        n = len(_split_sentences(snd))
        if n > 4:
            bad.append(f"overall_soundscape 写了 {n} 句（官方 1–4 句）")
    if mus and mus != "N/A":
        n = len(_split_sentences(mus))
        if n > 3:
            bad.append(f"non_diegetic_music 写了 {n} 句（官方 1–3 句）")
        # 官方点名的抽象词只有 `SKILL.md:39` 那两个例子
        # （「Prefer concrete visual and audio details over abstract words like
        #   "cinematic" or "beautiful"」）—— 只判这两个，不自造词表。
        for w in ("cinematic", "beautiful"):
            if w in mus.lower():
                bad.append(f"non_diegetic_music 用了抽象词 `{w}`（SKILL.md:39）")
    return bad


def e18_abstract_in_description(p, ctx):
    """`h3-skill:39`：「Prefer **concrete** visual and audio details over abstract
    words like "cinematic" or "beautiful"」。

    🩸 2026-10-28：上游 SKILL.md 这一整节（`Tips for Better Results`，`:36-40`）
    是 10-22 之后新增的，本地旧副本（2177 字节）没有 —— 我们原来只在 E17 里
    查了 `non_diegetic_music` 一段。这句话管的是**所有描述**。
    只认官方点名的两个词，不自造词表（同 E17 的口径）。

    黄不红：官方是「更偏好具体」，不是禁用；而且这条最容易从
    **用户补充说明的译文**里漏进来（"电影感" → `cinematic`）。
    """
    f = fields(p)
    bad = []
    for key in ("subject_definitions", "summary", "detailed_description",
                "overall_soundscape"):
        t = (f.get(key) or "").lower()
        for w in ("cinematic", "beautiful"):
            if w in t:
                bad.append(f"{key} 用了抽象词 `{w}`（`h3-skill:39` 要求具体可观察细节）")
    return bad


#: `<d>` 里不许出现的装饰符号。🩸 尺子**自己写一份**，不复用编译器里的正则 ——
#: 两边共用一条正则，改动一处会让两边一起错，尺子就废了。
_DECOR_CH = re.compile(r"[~～〜]{2,}|[•●▪◦‣∙]")
_EMOJI_CH = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U00002B00-\U00002BFF"
    "\U0001F1E6-\U0001F1FF\uFE0F\u200D]")
_REPEAT_PUNCT = re.compile(r"([,.;:?!—])\1+")
_TAG_IN_D = re.compile(
    r"</?(?:d|Picture|Video|Audio|Subject|scenetrans|cutoff)\b[^<>]*>")


def e19_dialogue_decor(p, ctx):
    """`<d>` 里只放"要念出来的内容"（官方 `ref-en:274` 逐字）：

    「Standardize punctuation to the basic written marks …; **remove repeated
    tildes, emoji, bullets, and repeated or decorative punctuation**」。
    前半句（换基本标点）由 E11 的收尾要求兜着，后半句**之前一条判据都没有** ——
    emoji、项目符号、`～～～`、`——` 都会原样进 `<d>`。
    """
    bad = []
    for m in re.finditer(r"<d>(.*?)</d>", p, re.S):
        body = m.group(1)
        hit = []
        if _EMOJI_CH.search(body):
            hit.append("emoji")
        if _DECOR_CH.search(body):
            hit.append("项目符号或重复波浪号")
        if _REPEAT_PUNCT.search(body):
            hit.append("重复标点")
        if hit:
            bad.append(f"台词里有{'、'.join(hit)}：{body[:40]}")
    return bad


def e20_no_tag_in_dialogue(p, ctx):
    """台词里不许出现我们自己的标号（`ref-en:220` 的 `<d>[Language] …</d>` 语法）。

    抄进一个 `</d>`，`<d>` 就会**提前闭合**、后半句跑到标签外面；抄进
    `<Picture 2>` 则会指着一个 `subject_definitions` 里并不存在的素材
    （E8 只查"用到的标号有没有定义"，它管的是**正文**里的引用）。
    """
    bad = []
    # 🩸 抄进 `</d>` 的情况**看不进 body**：非贪婪匹配到那个 `</d>` 就截断了，
    #   body 里干干净净，只有**标签数量**对不上（实测 `…我来了</d>.</d>` → 1/2）。
    if p.count("<d>") != p.count("</d>"):
        bad.append(f"`<d>` 与 `</d>` 数量不等（{p.count('<d>')}/{p.count('</d>')}）"
                   "：标签提前闭合，后半句会跑到标签外面")
    for m in re.finditer(r"<d>(.*?)</d>", p, re.S):
        t = _TAG_IN_D.search(m.group(1))
        if t:
            bad.append(f"台词里出现标号 {t.group(0)}：{m.group(1)[:40]}")
    return bad


def e21_dialogue_language_tag(p, ctx):
    """`<d>` 开头必须有 `[语言]` 标签（`base-en:129` 逐字：
    "Inside `<d>`, include only the **language tag** and the actual user-provided
    spoken content"）。

    🩸 2026-10-29 变异测试盲区：整条 `[Chinese]` 被删掉，尺子全绿。
    语言标签是官方规定的 `<d>` 内容**组成部分**，不是装饰 —— 丢了它，模型对这
    句该用哪种语言没有任何约束（H3 的坑正是"英语台词被念成中文"）。
    `[unclear]` 也是合法的方括号标签（`ref-en:274`），同样通过。
    """
    bad = []
    for m in re.finditer(r"<d>(.*?)</d>", p, re.S):
        body = m.group(1).strip()
        if not re.match(r"\[[^\[\]]{1,20}\]", body):
            bad.append(f"台词开头没有 [语言] 标签：「{body[:24]}」")
    return bad


def e22_transfer_not_self(p, ctx):
    """`attribute_transfer` 不能自指：属性不能从 A 转给 A。

    `ref-en:167` 逐字："Referenced characteristics are transferred to a
    **different** identifiable target subject" —— "different" 是明文。
    自指的句子等于说「把 <Subject 2> 的脸换成 <Subject 2> 的脸」，
    模型没有可换的来源，实际会自己编一张脸。

    🩸 2026-10-29 变异测试盲区：把属性来源的编号从 `<Subject 1>` 写成
    `<Subject 2>`（与"被替换对象"同号），尺子全绿。
    """
    bad = []
    for line in p.split("\n"):
        if "attribute_transfer" not in line:
            continue
        tgt = re.search(r"where <Subject (\d+)> appears?", line)
        if not tgt:
            continue
        n = tgt.group(1)
        for mm in re.finditer(r"of <Subject (\d+)>", line):
            if mm.group(1) != n:
                continue
            # `replace those of <Subject N>` 是"被替换的那一边"，本来就该同号。
            # 切片只到 `of` 之前，所以比的是 `replace those\s*$`（不是带 `of` 的整串）。
            if re.search(r"replace those\s*$", line[max(0, mm.start() - 20):mm.start()]):
                continue
            bad.append(f"attribute_transfer 自指：属性来源和被替换对象都是 "
                       f"<Subject {n}>（`:167` 要求 different）")
            break
    return bad


def e23_says_separator(p, ctx):
    """`(Sx)` 说话句与 `<d>` 之间要有分隔标点（`,` 或 `:`）。

    ⚠️ 依据性质：官方**没有**明文规定必须加标点 —— 这是**示例形态一致性**：
    `base-en:132/133/139` 用 `says:`，`ref-en:263/331` 用 `says,`，
    4/4 都有分隔标点。所以判「黄」（建议级），不是"官方禁止"。

    🩸 2026-10-29 变异测试盲区：`says, <d>` 的逗号被删成 `says <d>`，尺子全绿。
    """
    bad = []
    for m in re.finditer(r"\(S\d+(?:,\s*S\d+)*\)[^<>\n]{1,180}?<d>", p):
        seg = m.group(0)
        before = seg[:seg.index("<d>")]
        if not re.search(r"[,:]\s*$", before):
            bad.append(f"说话句与 <d> 之间没有 `,`/`:`：「…{before[-30:]}<d>」")
    return bad


def e24_length(p, ctx):
    """`text` ≤ 7000 字符（`api-create:407` 「`text` 最多 7000 个字符」）。

    这是**接口硬限制**，不是风格建议：超了 H3 的 API 直接拒，顾客粘进去才报错。
    `models/h3_common.MAX_CHARS` 是同一个数（转换/修订两条路在代码里查），
    agent 这条路只能靠尺子 —— 所以这条判据就是它的等价物。
    """
    if len(p) > 7000:
        return [f"正文 {len(p)} 字符，超过官方上限 7000"]
    return []


RULES = [
    ("E1", "红", "六段齐全且顺序正确", "ref-en:13-22", e1_sections),
    ("E2", "红", "summary 有官方任务类型前缀", "ref-en:126-128", e2_task_prefix),
    ("E3", "红", "编辑母版写 video editing（原声在则加 audio reuse）",
     "ref-en:136-153", e3_edit_type),
    ("E4", "红", "summary 用官方编辑固定句", "ref-en:150-153", e4_edit_sentence),
    # 🩸 2026-10-29 出处核对（锚句判据）：原记 213 是标题，我第一次改成 215，
    #    那是「The basic format follows…」—— 正文行但不相干，旧判据放行了。
    #    真正要求在 **218**。
    ("E5", "红", "[Shot 1] 无时间戳、后续带 At MM:SS.mmm", "ref-en:218", e5_shots),
    ("E6", "红", "retention 关系标记用官方固定值", "ref-en:159-200", e6_marks),
    # 🩸 2026-10-28 出处核对：原记 `ref-en:276` 讲的是「只参考音色时不带原台词」，
    #    与 (Sx) 无关。真正要求（`Do not write (Sx) in retention_analysis`）在 **278**。
    ("E7", "红", "retention 里不写 (Sx)", "ref-en:278", e7_no_speaker_in_retention),
    # 🩸 2026-10-29 出处核对（锚句判据）：原记 27 是空行，我第一次改成 28，
    #    那是表格表头 `| Label | Meaning |` —— 旧判据也放行了。真正的定义句在 **26**。
    ("E8", "红", "用到的标签都在 definitions 里", "ref-en:26", e8_labels),
    # 🩸 2026-10-28 出处核对：原记 `ref-en:37,48` —— 37 行「Give each item its own line」
    #    支持本规则；**48 行说的是相反方向**（一个参考素材可以提供多个 subject），已删。
    ("E9", "红", "同一 <Video N> 的多个 subject 不能写成同一句", "ref-en:37", e9_unique_locator),
    ("E10", "红", "<d> 必须有说话来源", "ref-en:258-276", e10_dialogue_source),
    ("E11", "红", "<d> 结尾用 . ? !", "ref-en:270-276", e11_dialogue_end),
    ("E12", "红", "除 <d> 外写英文", "ref-en:5", e12_english_only),
    ("E13", "黄", "[Shot 1] 前有 1–2 句风格", "ref-en:225-231", e13_style_before_shot),
    # 🩸 2026-10-29 锚句核对：原记 `ref-en:33`（`<Audio N>` 的定义）撑不起这条规则；
    #    真正的「每个 reference label 用一行」在 **157**（156 是空行 —— 我第一遍又记错了，
    #    锚句判据当场报「记的 156 是空行、锚句在 157」）。
    ("E14", "红", "声明音频关系就要有 <Audio N> 及其 retention 行",
     "ref-en:33 · ref-en:157", e14_audio_claim_needs_asset),
    ("E15", "红", "说话人是已定义主体/声音描述，不是 <Video N>",
     "ref-en:266", e15_speaker_form),
    ("E16", "红", "镜头编号连续、切点严格递增", "base-en:86", e16_cut_order),
    ("E17", "黄", "两层声音句数不超、配乐段不用抽象词",
     "base-en:154-162", e17_sound_sections),
    ("E18", "黄", "画面描述不用官方点名的抽象词（cinematic / beautiful）",
     "h3-skill:39", e18_abstract_in_description),
    ("E19", "红", "<d> 里没有 emoji / 项目符号 / 重复波浪号 / 重复标点",
     "ref-en:274", e19_dialogue_decor),
    # 🩸 2026-10-29 锚句核对：原记 `ref-en:220`（「给发声源稳定 ID」）撑不起这条规则。
    #    真正出处是 `base-en:129`「`<d>` 里**只放**语言标签和用户原话」——
    #    我们自己的 `<Subject N>` / `<Picture N>` 属于"只放"之外，会提前闭合 `<d>`。
    ("E20", "红", "<d> 里没有我们自己的标号（防提前闭合）",
     "base-en:129", e20_no_tag_in_dialogue),
    # 🩸 2026-10-29 变异测试（`D:/tmp/_mutation_h3.py` 14 抓 11）挖出的三条盲区。
    ("E21", "红", "<d> 开头有 [语言] 标签", "base-en:129",
     e21_dialogue_language_tag),
    ("E22", "红", "attribute_transfer 不自指（来源≠目标）", "ref-en:167",
     e22_transfer_not_self),
    ("E23", "黄", "说话句与 <d> 之间有 , 或 :（示例形态）", "ref-en:263",
     e23_says_separator),
    # 🩸 2026-10-30 真机漏出来的：agent 交付 9,927 字符，判据 0 条红。
    #   `text` ≤7000 是**接口硬限制**（`api-create:407`），base 尺子有 B4 管这条，
    #   ref 尺子一条都没有 → 超长成品会被 API 直接拒，顾客拿到手才发现。
    ("E24", "红", "正文 ≤7000 字符（接口硬限制）", "api-create:407", e24_length),
]


# ================================================================ 原文锚句
# 🩸 2026-10-29 主人：「是不是又没抓到官方出处，你现在要做这个是整个项目的判断核心」。
# 行号会漂、内容会错 —— 光记行号挡不住「行号对但说的不是这条规则」。
# 这里给每条规则绑一句**从官方原文逐字复制**的锚句，由 `ruler_sources.py` 机器校验：
#   ① 每条规则必须有锚句（缺 = 红）
#   ② 锚句必须能在出处文件里**逐字**找到（找不到 = 红）
#   ③ 找到的行必须落在 RULES 声明的行号范围内（落在别处 = 红，并报真实行号）
# ⛔ 不许改写、不许翻译、不许省略中间 —— 复制粘贴。锚句本身写错，判据会报红。
QUOTES = {
    "E1": "A complete rewrite output consists of six sections in the following order",
    "E2": "[video editing + reference generation + audio reuse]",
    "E3": "An existing source video is directly modified",
    "E4": "The target video is an edited version of <Video 1>.",
    "E5": "marks the opening shot and has no timestamp",
    "E6": "These markers are fixed English values in the output format",
    "E7": "Do not write `(Sx)` in `retention_analysis`",
    "E8": "Full-reference rewrites use four types of labels",
    "E9": "Give each item its own line",
    "E10": "When a referenced subject physically speaks, retain both the visual reference label and the speaker ID",
    "E11": "End complete statements, questions, and exclamations with",
    "E12": "Write all six rewrite sections in English.",
    "E13": "Established in one or two English sentences before",
    "E14": "Use one line for each reference label",
    "E15": "use a stable voice description followed by",
    "E16": "Do not add a timestamp to the first shot.",
    "E17": "Use 1–4 English sentences in one continuous paragraph",
    "E18": "Prefer concrete visual and audio details over abstract words",
    "E19": "remove repeated tildes, emoji, bullets, and repeated or decorative punctuation",
    "E20": "Inside `<d>`, include only the language tag and the actual user-provided spoken content",
    # E21 与 E20 同源（`base-en:129`），取该行的后半截做锚句，便于分开核对。
    "E21": "include only the language tag and the actual user-provided spoken content",
    "E22": "Referenced characteristics are transferred to a different identifiable target subject",
    # ⚠️ 这是**示例**锚句（示范"说话句 + 逗号 + `<d>`"的官方写法），不是规则原文。
    "E23": "turns toward the woman and says, <d>[English]",
    "E24": "`text` 最多 7000 个字符。",
}


def check(p: str, ctx: dict) -> list[tuple[str, str, str, str, list[str]]]:
    out = []
    for rid, sev, name, src, fn in RULES:
        try:
            issues = fn(p, ctx)
        except Exception as e:                      # 尺子自己崩了要看见，不许静默
            issues = [f"判据异常：{e}"]
        if issues:
            out.append((rid, sev, name, src, issues))
    return out


def ctx_for(p: str, *, edit_master: bool = False, audio: str | None = None) -> dict:
    return {"edit_master": edit_master, "audio": audio}
