# -*- coding: utf-8 -*-
"""H3 的逐段编辑指令 —— agent 读 **H3 官方 skill** 现写，写完落盘。

⛔ 和 `clone_agent.py` **平级、互不 import**：
  · `clone_agent` 是火山 2.5 那套（中文正文 + 五段标记 `【编辑目标】…` +
    `@视频1` / `@图片N`），判据也只认那一套；
  · 本文件是 H3 那套（英文正文 + Ref2VA 六段式 + `<Subject N>` / `<Picture N>`）。
  两套模板**不通用**：把 2.5 的 SYSTEM 拿去写 H3，交出来的是一份中文五段式，
  发给 H3 只会出废片（2026-11-01 复核）。所以宁可各写一遍，也不互相借用。

写的规则**全部来自官方**（`data/official/h3/ref-en.txt`，与官方 skill 同一份，
sha1 一致）。这里不自己发明格式 —— 每条硬闸旁边都写着它出自哪一行。
"""
from __future__ import annotations

import functools
import hashlib
import json
import logging
import re
import time
from pathlib import Path

from app.services import clone_brief, skill_agent

log = logging.getLogger(__name__)

#: H3 官方 skill 包根目录（`h3-prompt-writing/` 就在它下面）
ROOT = Path(__file__).resolve().parents[2] / "data" / "official" / "h3" / "skills"

#: 落盘文件名：和 2.5 共用同一个文件（出片只读一份，谁写的就是谁的，
#: 签名里带型号 + skill 指纹，换家必不命中）
FILENAME = "prompts.json"

#: 本文件的身份标记，写进落盘数据里，`cached` 据此拒收别家写的文件
AGENT = "h3"


class CloneAgentError(RuntimeError):
    """agent 没交出合格的逐段指令。调用方据此回落代码编译。"""


SYSTEM = """## 你在做什么

你在做**复刻**：拿一部已经拍好的片子，改掉其中指定的东西，其余一律保持原样。
原片是**唯一编辑母版** —— 场景、机位、镜头运动、动作轨迹、遮挡关系、事件顺序
全部来自原片，你只写"改什么"。

## 你怎么干活

1. 先用 `list_skills` 看有哪些官方 skill，用 `read_skill` 读
   `h3-prompt-writing/SKILL.md`。
2. SKILL.md 会让你读 `references/ref-en.txt`（全参考模式 Ref2VA 的六段式写法），
   继续 `read_skill` 读完它，按它写的格式写。
3. 给**每一段**写一条完整的六段式提示词。
4. 全部写完，用 `deliver_segments` 一次交齐。

## 硬要求（每条都是官方原文，出处写在括号里）

- 六段齐全，顺序固定：`subject_definitions` → `summary` → `retention_analysis`
  → `detailed_description` → `overall_soundscape` → `non_diegetic_music`（`ref-en:13-22`）。
  每段标题单独一行，写成 `subject_definitions:` 这种带冒号的形态。
- **正文全部英文**；只有 `<d>` 里的台词/歌词和画面里可见的文字保留原语言（`ref-en:5`）。
- 标号只有四种，全程同义：`<Subject N>` / `<Picture N>` / `<Video N>` / `<Audio N>`
  （`ref-en:26-35`）。规格书里的「@图片N」= `<Picture N>`，「@音频1」= `<Audio 1>`，
  「原片」= `<Video 1>`。
- `summary` 第一行是方括号任务类型（`ref-en:123`）。复刻是在原片上直接改 →
  用 `video editing`（`ref-en:136`）；原片原声保留时再加 ` + audio reuse`（`ref-en:141`）。
- 复刻的 `summary` 在任务类型后面必须接这一句原话：
  `The target video is an edited version of <Video 1>.`（`ref-en:149-153`）。
- 每一个被引用的标号，都必须在 `subject_definitions` 里单独一行定义过（`ref-en:35`）；
  定义时写清它指什么、参考角色是什么、要跟随的主要特征（`ref-en:37`）。
- 图只用来定义人物/场景/服装/风格时，**不要**给 `<Picture N>` 单独开一行 ——
  在对应的 `<Subject N>` 定义里直接引用那张图就行（`ref-en:68`）。
  只有这张图本身就是某一镜的首帧/关键帧/尾帧/构图锚点时，才单独写 `<Picture N>`
  （`ref-en:62`）。
- `retention_analysis` 每条标号一行，关系标记只能用固定英文值（`ref-en:157-168`）：
  视觉 `fully_preserved` / `partially_preserved` / `attribute_transfer` / `weak_reference`；
  音频 `fully_copy` / `partially_copy` / `reference` / `weak_reference`（`ref-en:190-197`）。
  换人 = `attribute_transfer`（`ref-en:167`）。
- `detailed_description` 按镜次写：`[Shot 1]` 不带时间戳，后面用
  `[Shot N] At MM:SS.mmm, ...`（`ref-en:218`）。
  重要主体第一次清晰出现时，要写清它被参考的特征、在画面中的位置、当下的动作（`ref-en:246`）。
- 复刻任务的描述长度**跟着原片复杂度走**，不用凑生成任务的 350–500 词（`ref-en:242`）。

## 每一段写它自己那一段

- 规格书里每段开头「这一段画面」那一句，是这一段和其他段唯一的不同依据。
  两段写成几乎一样 = 这一单没做完。
- 段数只能等于规格书给的段数，编号一一对应，不多不少。

## 两个真跑翻过的坑

**① 口型/原声。** 这一段带原片音轨时，`detailed_description` 里要写明原声是怎么用的，
并且在 `retention_analysis` 给 `<Audio 1>` 单独一行（`ref-en:118` / `:232`）。
不要因为换人重新设计动作、口型时点、镜头或剪辑节奏。

**② 换人是全片的。** 全片始终只有一位替换后的人物，不出现第二个相同形象，
也不出现原人物的残留形象（`ref-en:167` 的 `attribute_transfer` 就是"特征转移到另一个目标"）。

## 合规底线

真人明星、网红、熟人的脸不能拿来当主角或换脸对象；不做色情、暴力、
涉及未成年人的性化内容。碰到就一句话说做不了，不硬写。"""


DELIVER = {"type": "function", "function": {
    "name": "deliver_segments",
    "description": "交付全部段的 H3 六段式提示词。一次交齐，调用后本次任务结束。",
    "parameters": {"type": "object", "properties": {
        "segments": {
            "type": "array",
            "description": "每一段一条，顺序与规格书一致",
            "items": {"type": "object", "properties": {
                "index": {"type": "integer", "description": "第几段，从 1 开始"},
                "prompt": {"type": "string",
                           "description": "这一段的完整六段式提示词，从 subject_definitions: 开始"},
            }, "required": ["index", "prompt"]},
        }},
        "required": ["segments"]},
}}

TOOLS = [skill_agent.TOOLS[0], skill_agent.TOOLS[1], DELIVER]

#: 六个段标题（`ref-en:13-22` 的顺序）
_SECTIONS = ("subject_definitions:", "summary:", "retention_analysis:",
             "detailed_description:", "overall_soundscape:", "non_diegetic_music:")

#: 官方允许的标号种类（`ref-en:26-33`）
_LABEL = re.compile(r"<(Subject|Picture|Video|Audio)\s*(\d+)>")

#: 台词/歌词/画面文字：唯一允许保留原语言的地方（`ref-en:5`）
_DIALOGUE = re.compile(r"<d>.*?</d>", re.S)

#: 中文（含 Ext-B 起）—— 六段正文里出现就是不合格
_CJK = re.compile(r"[一-鿿]")

#: 官方允许的尖括号写法。除此之外的 `<…>` = 没替换的占位符。
_KNOWN_ANGLE = re.compile(
    r"</?(?:Subject|Picture|Video|Audio)\s*\d+>|<d>|</d>|<scenetrans>|<cutoff>")
_ANGLE = re.compile(r"<[^<>\n]{1,40}>")

#: 关系标记（`ref-en:161-168` 视觉 / `:190-197` 音频）
_VISUAL_MARKS = ("fully_preserved", "partially_preserved",
                 "attribute_transfer", "weak_reference")
_AUDIO_MARKS = ("fully_copy", "partially_copy", "reference", "weak_reference")


def check(brief: dict, segments: list[dict]) -> list[str]:
    """交付前的硬闸。返回红列表，空 = 合格。

    🩸 判据写的是**效果**：说的是"模型会不会把这段当成重新生成"、
    "发给 H3 的正文能不能被它读懂"，不是"文件里有没有这句话"。
    """
    red: list[str] = []
    want = [int(s["index"]) for s in (brief.get("segments") or [])]
    got = [int(s.get("index") or 0) for s in segments]
    if sorted(got) != sorted(want):
        red.append(f"段数对不上：规格书要 {want}，你交了 {got}")

    n_pic = sum(1 for r in (brief.get("refs") or []) if r.get("pic"))
    has_audio = any(r.get("slot") == "audio" for r in (brief.get("refs") or []))
    by_index = {int(s.get("index") or 0): str(s.get("prompt") or "") for s in segments}

    for i in want:
        p = by_index.get(i, "")
        if not p.strip():
            red.append(f"第 {i} 段是空的")
            continue

        # --- 六段齐全、顺序正确（ref-en:13-22）---
        pos = []
        missing = []
        for sec in _SECTIONS:
            m = re.search(rf"(?m)^{re.escape(sec)}", p)
            if m:
                pos.append(m.start())
            else:
                missing.append(sec.rstrip(":"))
        if missing:
            red.append(f"第 {i} 段缺段：{'、'.join(missing)}"
                       "（官方 Ref2VA 六段式要求六段齐全，缺了就退化成一句话生成）")
        elif pos != sorted(pos):
            red.append(f"第 {i} 段的六段顺序不对（官方顺序："
                       f"{' → '.join(s.rstrip(':') for s in _SECTIONS)}）")

        # --- 正文英文（ref-en:5）：台词和画面文字除外 ---
        body = _DIALOGUE.sub(" ", p)
        body = _KNOWN_ANGLE.sub(" ", body)
        cjk = _CJK.findall(body)
        if cjk:
            red.append(f"第 {i} 段正文里有中文（H3 六段式必须英文，官方 `ref-en:5`；"
                       f"只有 <d> 里的台词可以保留原语言）：{''.join(cjk[:8])}")

        # --- 任务类型 + 编辑母版（ref-en:123 / :136 / :149-153）---
        summ = _section(p, "summary")
        first = next((ln.strip() for ln in summ.splitlines() if ln.strip()), "")
        if not first.startswith("["):
            red.append(f"第 {i} 段的 summary 没有方括号任务类型（官方 `ref-en:123`）")
        elif "video editing" not in first.split("]")[0]:
            red.append(f"第 {i} 段任务类型没写 `video editing` —— 复刻是在原片上直接改"
                       "（官方 `ref-en:136`），写成别的就等于重新生成")
        if "The target video is an edited version of <Video 1>." not in summ:
            red.append(f"第 {i} 段 summary 缺官方那句话"
                       "`The target video is an edited version of <Video 1>.`"
                       "（`ref-en:149-153`：编辑任务必须这样开头）")
        if has_audio and "audio reuse" not in first.split("]")[0]:
            red.append(f"第 {i} 段这段带原片音轨，任务类型要加 ` + audio reuse`"
                       "（官方 `ref-en:141`）")

        # --- 标号必须有定义（ref-en:35）---
        defs = _section(p, "subject_definitions")
        used = {f"<{k} {n}>" for k, n in _LABEL.findall(p)}
        undefined = sorted(x for x in used if x not in defs)
        if undefined:
            red.append(f"第 {i} 段用了没定义的标号：{'、'.join(undefined[:4])}"
                       "（官方 `ref-en:35`：每个被引用的标号都要在 subject_definitions 里定义）")
        bad_pic = sorted({n for k, n in _LABEL.findall(p) if k == "Picture"
                          and not (1 <= int(n) <= n_pic)})
        if bad_pic:
            red.append(f"第 {i} 段引用了不存在的图号：<Picture {'>、<Picture '.join(bad_pic)}>"
                       f"（这次最多 <Picture {n_pic}>）")

        # --- retention 每个标号一行、标记合法（ref-en:157 / :190-197）---
        ret = _section(p, "retention_analysis")
        ret_lines = [ln.strip() for ln in ret.splitlines() if ln.strip()]
        for lab in sorted(used):
            kind = re.match(r"<(Subject|Picture|Video|Audio)", lab)
            if kind and kind.group(1) == "Picture":
                continue        # 图只作来源时不必单独成行（`ref-en:68`）
            if not any(ln.startswith(lab) for ln in ret_lines):
                red.append(f"第 {i} 段的 retention_analysis 缺 {lab} 那一行"
                           "（官方 `ref-en:157`：每个标号一行）")
        for ln in ret_lines:
            marks = _AUDIO_MARKS if ln.startswith("<Audio") else _VISUAL_MARKS
            if ln.startswith("<") and not any(m in ln for m in marks):
                red.append(f"第 {i} 段这一行的关系标记不是官方固定值：{ln[:50]}"
                           "（`ref-en:161-168` / `:190-197`）")
        if has_audio and "<Audio 1>" not in p:
            red.append(f"第 {i} 段这段带原片音轨，但提示词里没有 <Audio 1>"
                       "（原声是这段的一条参考，官方 `ref-en:118` / `:232`）")

        # --- 没替换的占位符 ---
        leftovers = [x for x in _ANGLE.findall(p) if not _KNOWN_ANGLE.fullmatch(x)]
        if leftovers:
            red.append(f"第 {i} 段还有没替换的占位符：{'、'.join(leftovers[:4])}")
    return red


def _section(prompt: str, name: str) -> str:
    """取某一段的正文（从它的标题行到下一个标题行之前）。"""
    names = [s for s in _SECTIONS if re.search(rf"(?m)^{re.escape(s)}", prompt)]
    m = re.search(rf"(?m)^{re.escape(name + ':')}", prompt)
    if not m:
        return ""
    rest = prompt[m.end():]
    nxt = len(rest)
    for other in names:
        mm = re.search(rf"(?m)^{re.escape(other)}", rest)
        if mm and mm.start() < nxt:
            nxt = mm.start()
    return rest[:nxt]


@functools.lru_cache(maxsize=1)
def _skill_sha_cached() -> str:
    h = hashlib.sha1()
    if ROOT.is_dir():
        for p in sorted(ROOT.rglob("*")):
            if p.is_file():
                h.update(str(p.relative_to(ROOT)).encode("utf-8"))
                h.update(p.read_bytes())
    return h.hexdigest()[:12]


def signature(brief: dict) -> str:
    """输入签名：规格书 + 型号 + skill 版本 + 本 agent 的身份。

    🩸 带 `AGENT` 前缀：2.5 和 H3 写同一个 `prompts.json`，签名必须互不相认 ——
    否则换了型号还能命中上一家写的文件，把中文五段式发给 H3。
    """
    raw = json.dumps(brief, ensure_ascii=False, sort_keys=True)
    h = hashlib.sha1(AGENT.encode("utf-8"))
    h.update(raw.encode("utf-8"))
    h.update(str(brief.get("model") or "").encode("utf-8"))
    h.update(_skill_sha_cached().encode("utf-8"))
    # 🩸 SYSTEM 也是"规则"的一部分：改了 SYSTEM 却还命中旧缓存，
    #   等于新规矩根本没生效（改完 SYSTEM 必须重写一次）。
    h.update(hashlib.sha1(SYSTEM.encode("utf-8")).hexdigest().encode("utf-8"))
    return h.hexdigest()[:16]


def _path(cid: str) -> Path:
    from app.services import clone_store as store

    return store.prompts_path(cid)


def load(cid: str) -> dict | None:
    p = _path(cid)
    if not p.is_file():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        log.warning("prompts.json 读不出来（当成没有）：%s", e)
        return None
    return d if isinstance(d, dict) else None


def save(cid: str, data: dict) -> None:
    p = _path(cid)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def as_brief(plan: dict, rec: dict, spans: list, cid: str | None = None) -> dict:
    """H3 看的规格书：事实同一份，标号换成 H3 的写法。

    🩸 额外带一份**换人参考图里那个人实际长什么样**（`target_looks`）。
    H3 的 `subject_definitions` 必须写"要跟随的主要特征"（`ref-en:37`），
    规格书里只有**原片**那些人的外观 —— 不给目标的样子，agent 只能瞎写
    （2026-11-01 实测：把上传的男性照片写成 "female warrior"）。
    这份只进 H3 的规格书，2.5 那份一个字段都不动（`clone_brief` 不认识它）。
    """
    brief = clone_brief.build(plan, rec, spans, cid=cid)
    looks = plan.get("looks") or {}
    if not looks:
        return brief
    pic_of = {r["slot"]: r.get("pic")
              for r in (brief.get("refs") or []) if r.get("pic")}
    rows = []
    for slot, lk in looks.items():
        en = str((lk or {}).get("en") or "").strip()
        if en and slot in pic_of:
            g = str((lk or {}).get("gender") or "").strip()
            rows.append({"pic": pic_of[slot], "en": en, "gender": g})
    if not rows:
        return brief
    out = dict(brief)
    out["target_looks"] = sorted(rows, key=lambda r: r["pic"])
    return out


def brief_text(brief: dict) -> str:
    """规格书 → 给 agent 读的清单（H3 版：正文英文、标号 `<Picture N>`）。"""
    text = clone_brief.as_text(brief, body_lang="英文",
                               pic="<Picture {n}>", audio="<Audio 1>")
    tl = brief.get("target_looks") or []
    if tl:
        lines = ["", "## 换人参考图里那个人**实际长什么样**（英文原文，写 "
                     "subject_definitions 用）",
                 "（这是看图写下来的，和图上那个人一致；用它写 "
                 "`<Subject N>` 要跟随的特征，别自己编。括号里是**这个人的性别**："
                 "写了男性/女性就按它写主语；写「看不出」就用中性说法"
                 "（the person / they），**不要**沿用原片那个人物的性别）"]
        for r in tl:
            g = str(r.get("gender") or "").strip()
            # 🩸 性别只说**图上那个人**（官方把它列为身份信息 `base-en:129`）。
            #   没把握就明说"看不出来"，让 agent 写中性说法，别沿用原片人物的性别。
            # 老描述没有这个字段（`g == ""`）→ **不加标签**，别把"没问过"说成"看不出"
            tag = {"male": "（男性）", "female": "（女性）",
                   "unspecified": "（性别看不出）"}.get(g, "")
            lines.append(f"- <Picture {r['pic']}>{tag}：{r['en']}")
        text = text + "\n" + "\n".join(lines)
    return text


def _run_agent(brief: dict, *, post=None, on_step=None) -> list[dict]:
    """跑一轮 agent，拿回逐段指令。`post` 可注入桩（零费用测）。"""
    from app.core.config import settings
    from app.services import deepseek_chat

    # 和 2.5 那条一样走 **DeepSeek 官方**（`api.deepseek.com`），独立的 key。
    # 没有 key 直接报错，不静默回落火山 —— 回落了用户以为切了其实没切。
    model = settings.deepseek_model
    key = (settings.deepseek_api_key or "").strip()
    if not key and post is None:
        raise CloneAgentError(
            "DeepSeek 官方未配置：请设置环境变量 VT_DEEPSEEK_API_KEY"
            "（方舟的 ark key 不能用在这条路上）")

    def _post_official(msgs: list[dict]) -> dict:
        body = {"model": model, "messages": msgs, "tools": TOOLS,
                "tool_choice": "auto", "temperature": 0.2}
        try:
            return deepseek_chat.post(body, key=key)
        except deepseek_chat.DeepSeekError as e:
            raise CloneAgentError(str(e)) from e

    holder: dict = {}

    def on_tool(name: str, args: dict, res, step):
        if name != "deliver_segments":
            return None
        segs = args.get("segments")
        if not isinstance(segs, list) or not segs:
            return "错误：segments 不能为空，每一段一条", False
        clean = []
        for x in segs:
            if not isinstance(x, dict):
                continue
            clean.append({"index": int(x.get("index") or 0),
                          "prompt": str(x.get("prompt") or "").strip()})
        red = check(brief, clean)
        if red:
            tries = int(holder.get("tries") or 0) + 1
            holder["tries"] = tries
            if tries <= 2:
                step("judge", f"判到 {len(red)} 条红（第 {tries} 次），回灌重试")
                return ("\n".join(f"- {r}" for r in red)
                        + "\n\n请按上面的问题改一遍，再调 deliver_segments 交齐。"), False
            # 连续两次不合格 → 不收。宁可回落代码编译，也不把废提示词发给模型烧钱。
            holder["failed"] = red
            res.action = "write"
            step("fail", f"连续 {tries} 次不合格，放弃交付")
            return "不合格：" + "；".join(red[:3]), True
        holder["segments"] = clean
        res.action = "write"
        res.payload["segments"] = clean
        step("deliver", f"交付 {len(clean)} 段")
        return "已交付", True

    res = skill_agent.run(
        ROOT, system=SYSTEM,
        messages=[{"role": "user", "content": brief_text(brief)}],
        model=model, key=key, post=post or _post_official, on_step=on_step,
        tools=TOOLS, on_tool=on_tool, nudge=True)

    if holder.get("failed"):
        raise CloneAgentError(
            "逐段指令没通过校验（" + "；".join(holder["failed"][:3]) + "），本次不再重试")
    segs = holder.get("segments") or []
    if not segs:
        raise CloneAgentError(res.truncated or "模型没有交出逐段指令")
    return segs


def cached(cid: str, plan: dict, rec: dict, spans: list) -> dict[int, str] | None:
    """落盘里有没有**这次输入**对应的逐段指令。返回 `{段号: 提示词}`，没有就 None。

    🩸 拒收别家写的文件：`agent` 标记不是 `h3` 就当没有。只有签名也对得上才用。
    出片路径只读这里，不现场跑 agent。
    """
    data = load(cid)
    if not data or str(data.get("agent") or "") != AGENT:
        return None
    try:
        brief = as_brief(plan, rec, spans, cid=cid)
        if data.get("sig") != signature(brief):
            return None
    except Exception as e:  # noqa: BLE001
        log.warning("逐段指令的签名算不出来（按没有处理）：%s", e)
        return None
    out: dict[int, str] = {}
    for s in (data.get("segments") or []):
        try:
            i = int(s.get("index") or 0)
        except (TypeError, ValueError):
            continue
        p = str(s.get("prompt") or "").strip()
        if i > 0 and p:
            out[i] = p
    return out or None


def generate(cid: str, plan: dict, rec: dict, spans: list, *,
             force: bool = False, post=None, on_step=None) -> dict:
    """生成（或复用）这一单的 H3 逐段提示词，并落盘。

    **失败会抛 `CloneAgentError`** —— 由调用方决定回落还是报错。
    """
    brief = as_brief(plan, rec, spans, cid=cid)
    sig = signature(brief)
    if not force:
        old = load(cid)
        if old and old.get("agent") == AGENT and old.get("sig") == sig:
            log.info("H3 逐段指令命中缓存（%s）", sig)
            return old
    segs = _run_agent(brief, post=post, on_step=on_step)
    data = {
        "agent": AGENT,
        "sig": sig,
        "source": "agent",
        "model": str(brief.get("model") or ""),
        "created": int(time.time()),
        "brief": brief,
        "segments": segs,
    }
    save(cid, data)
    log.info("H3 逐段指令已落盘：%s（%d 段）", sig, len(segs))
    return data
