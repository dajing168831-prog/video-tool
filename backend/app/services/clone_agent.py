# -*- coding: utf-8 -*-
"""复刻的逐段编辑指令 —— 由 agent 读官方 skill 现写，写完落盘。

和「提示词优化」那条线的分工（两条线平级，互不 import）：
  · 提示词优化（`sd25_skill`）：顾客要一段视频，agent 陪聊问清需求，交**一段**提示词；
  · 复刻（本文件）：原片已经拆好了，agent 只负责把每一段的事实**翻成编辑指令**，
    一次交**全部段**，不问顾客（该问的都问完了，答案在规格书里）。

🩸 为什么一次交全部段、不是每段调一次：
  段与段之间是同一批人、同一套衣服、同一个场景。分开调，第 2 段那几个人
  就和第 1 段不像了 —— 这正是"每个片段都不一样"必须靠一次看全片才能守住的。
  官方模板本身也要求写「全片目标对象数量」这种全局信息（`sd25-pe:548`）。
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

#: 官方 skill 包根目录（和提示词优化读的是同一份资料，但各走各的调用）
ROOT = Path(__file__).resolve().parents[2] / "data" / "official" / "sd25" / "skills"

#: 落盘文件名（放在任务目录下，跟 task.json / inventory 同级）
FILENAME = "prompts.json"


class CloneAgentError(RuntimeError):
    """agent 没交出合格的逐段指令。调用方据此回落代码编译。"""


SYSTEM = """## 你在做什么

你在做**复刻**：拿一部已经拍好的片子，改掉其中指定的东西，其余一律保持原样。

不是重新生成一条新视频。原片是**唯一编辑母版** —— 场景、机位、镜头运动、
动作轨迹、遮挡关系、事件顺序，全部来自原片，你只描述"改什么"。

## 你怎么干活

1. 先用 `list_skills` 看有哪些官方 skill，用 `read_skill` 读它的 `SKILL.md`。
2. SKILL.md 里让你读别的参考文件，就继续 `read_skill`。
3. 按它写的**视频编辑**那一节的模板，给**每一段**写一条编辑指令。
4. 全部写完，用 `deliver_segments` 一次交齐。

## 硬要求

- 顾客给的规格书是**事实**，不质疑、不补写：原片里没写的人不要凭空加。
- 每一段一条，编号与规格书一一对应。段数不许少、不许多。
- **每一段必须写它自己那一段的画面**（规格书每段开头「这一段画面」那一句），
  不能把上一段的说法原样搬到下一段。两段几乎一样 = 这一单没做完。
- 每一条都必须把原片定义为唯一编辑母版，并逐一交代原片里**每一类**可见主体
  （哪些被替换、哪些被删除、哪些保持原样）。漏掉一类 = 模型会自由发挥。
- 参考图按规格书给的编号引用（@图片1、@图片2…），不许引用不存在的编号。
- 不要写 Markdown 标题、代码围栏、"以下是优化后的提示词"这类包装。

## 两个真跑翻过的坑（2026-10-31，都有官方原文）

**① 口型对不上。** 规格书列了 `@音频1` 时，每一条都要写清：替换后的人物按
`@音频1` 的音色与台词说话，**口型时点与它对齐**；并且不得因为换人重新设计
人物动作、口型时点、镜头或剪辑节奏。
（官方 `sd25-pe:623`「@视频1是唯一编辑母版，负责原始画面、人物动作、口型时点、
镜头、剪辑节奏、其他声音和事件顺序」；`:616`「不得因为声音编辑重新设计…口型时点…」）

**② 换人是全片的。** 全片始终只有一位替换后的人物，不出现第二个相同形象，
也不出现原人物的残留形象。
（官方 `sd25-pe:570`「全片目标对象数量为<数量>」；`:593` 示例「全片始终只有一辆电动巡逻车」）

## 合规底线

真人明星、网红、熟人的脸不能拿来当主角或换脸对象；不做色情、暴力、
涉及未成年人的性化内容。碰到就一句话说做不了，不硬写。"""


DELIVER = {"type": "function", "function": {
    "name": "deliver_segments",
    "description": "交付全部段的编辑指令。一次交齐，调用后本次任务结束。",
    "parameters": {"type": "object", "properties": {
        "segments": {
            "type": "array",
            "description": "每一段一条，顺序与规格书一致",
            "items": {"type": "object", "properties": {
                "index": {"type": "integer", "description": "第几段，从 1 开始"},
                "prompt": {"type": "string",
                           "description": "这一段的完整编辑指令正文，从第一句开始"},
            }, "required": ["index", "prompt"]},
        }},
        "required": ["segments"]},
}}

TOOLS = [skill_agent.TOOLS[0], skill_agent.TOOLS[1], DELIVER]

#: 官方「视频编辑模板」的五个段标记（`SKILL.md:544`）。缺任何一段 = 退化成
#: 「重新生成」，那正是复刻最怕的事，所以这五条当硬闸。
_REQUIRED_MARKS = ("【编辑目标】", "【原视频职责】", "【目标素材职责】",
                   "【编辑对象与范围】", "【时间线继承】")

_PLACEHOLDER = re.compile(r"<[^<>\n]{1,40}>")
_PIC = re.compile(r"@图片\s*(\d+)")


def check(brief: dict, segments: list[dict]) -> list[str]:
    """交付前的硬闸。返回红列表，空 = 合格。

    🩸 每条规则的出处都写在旁边。判据写的是**效果**（模型会不会退化），
    不是"文件里有没有这段字"。
    """
    red: list[str] = []
    want = [int(s["index"]) for s in (brief.get("segments") or [])]
    got = [int(s.get("index") or 0) for s in segments]
    if sorted(got) != sorted(want):
        red.append(f"段数对不上：规格书要 {want}，你交了 {got}")
    n_pic = sum(1 for r in (brief.get("refs") or []) if r.get("pic"))
    # 这段带了原片人声 ⇒ 提示词必须交代 @音频1 的口型对齐。
    # 🩸 2.5 的编辑任务 `generate_audio=False`（`volc25.py:71`），成片音轨是我们
    #   自己合成的；模型只有拿到 @音频1 才会按它排口型时点。漏这句 = 口型对不上
    #   （2026-10-31 真跑翻过）。
    has_audio = any(r.get("slot") == "audio" for r in (brief.get("refs") or []))
    by_index = {int(s.get("index") or 0): str(s.get("prompt") or "")
                for s in segments}
    for i in want:
        p = by_index.get(i, "")
        if not p.strip():
            red.append(f"第 {i} 段是空的")
            continue
        if has_audio and "@音频1" not in p:
            red.append(f"第 {i} 段没写 @音频1（这段带原片人声；不写口型时点就"
                       "会和合成音轨对不上）")
        missing = [m for m in _REQUIRED_MARKS if m not in p]
        if missing:
            red.append(f"第 {i} 段缺段标记：{'、'.join(missing)}"
                       "（官方视频编辑模板要求五段齐全，缺了就退化成重新生成）")
        if "@视频1" not in p:
            red.append(f"第 {i} 段没有把原片指定为唯一编辑母版（要出现 @视频1）")
        ph = _PLACEHOLDER.findall(p)
        if ph:
            red.append(f"第 {i} 段还有没替换的占位符：{'、'.join(ph[:4])}")
        bad = [x for x in _PIC.findall(p) if not (1 <= int(x) <= n_pic)]
        if bad:
            red.append(f"第 {i} 段引用了不存在的图号：@图片{'、@图片'.join(bad)}"
                       f"（这次最多 @图片{n_pic}）")
    return red


@functools.lru_cache(maxsize=1)
def _skill_sha_cached() -> str:
    h = hashlib.sha1()
    if ROOT.is_dir():
        for p in sorted(ROOT.rglob("*")):
            if p.is_file():
                h.update(str(p.relative_to(ROOT)).encode("utf-8"))
                h.update(p.read_bytes())
    return h.hexdigest()[:12]


def _skill_sha() -> str:
    """官方 skill 的版本指纹：skill 一变，旧指令就不再可信，缓存自动失效。

    🩸 进程内缓存：`_gen_spans` 每段都要调一次 `cached()`，不缓存的话
    每段都要把整个 skill 包读一遍（几十毫秒 × 段数）。skill 是只读资料，
    运行期不会变 —— 换了 skill 重启进程即可，语义不变。
    """
    return _skill_sha_cached()


def signature(brief: dict) -> str:
    """输入签名：规格书 + 型号 + skill 版本。三者任一变了就重写。"""
    raw = json.dumps(brief, ensure_ascii=False, sort_keys=True)
    h = hashlib.sha1(raw.encode("utf-8"))
    h.update(str(brief.get("model") or "").encode("utf-8"))
    h.update(_skill_sha().encode("utf-8"))
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


def _run_agent(brief: dict, *, post=None, on_step=None) -> list[dict]:
    """跑一轮 agent，拿回逐段指令。`post` 可注入桩（零费用测）。"""
    from app.core.config import settings
    from app.services import deepseek_chat

    # 🩸 2026-11-01 主人拍板：复刻的 agent 走 **DeepSeek 官方**
    #   （`api.deepseek.com`，模型 `deepseek-flash`），**不再是**方舟托管的
    #   `deepseek-v4-1-flash-261017` —— 那条花的是火山账户的钱。
    #   端点 / 型号 / 密钥全在 `deepseek_chat` 与 `Settings` 里：
    #   `VT_DEEPSEEK_API_KEY` + `VT_DEEPSEEK_MODEL`。
    #   🩸 没有 key 直接报错，**不静默回落火山**：回落了用户以为切了，其实没切。
    model = settings.deepseek_model
    key = (settings.deepseek_api_key or "").strip()
    if not key and post is None:
        raise CloneAgentError(
            "DeepSeek 官方未配置：请设置环境变量 VT_DEEPSEEK_API_KEY"
            "（方舟的 ark key 不能用在这条路上）")

    def _post_official(msgs: list[dict]) -> dict:
        """官方端点的一轮请求。结构照 `skill_agent._post`，只换传输。"""
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
            # 🩸 连续两次都不合格 → **不收**。这五条是硬闸：缺【时间线继承】的
            #   东西交出去，模型就不是在改片而是在重新生成 —— 宁可回落代码编译，
            #   也不能把废指令发给模型烧钱（`waste-clip-means-my-prompt-is-wrong`）。
            holder["failed"] = red
            res.action = "write"
            step("fail", f"连续 {tries} 次不合格，放弃交付")
            return "不合格：" + "；".join(red[:3]), True
        holder["segments"] = clean
        holder["red"] = red
        res.action = "write"
        res.payload["segments"] = clean
        step("deliver", f"交付 {len(clean)} 段")
        return "已交付", True

    res = skill_agent.run(
        ROOT, system=SYSTEM,
        messages=[{"role": "user", "content": clone_brief.as_text(brief)}],
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

    🩸 只有签名对得上才算命中 —— 换了勾选 / 参考图 / 文案 / 型号 / skill 版本，
    任何一项变了都重新生成。**出片路径只读这里，不现场跑 agent**：
    出片是用户已经点了"开始"的动作，不能因为 agent 慢或挂了把人卡在那儿。
    """
    data = load(cid)
    # 🩸 拒收别家写的文件：`h3_agent` 写同一个文件名，标记是 `h3`。
    #   老文件没有这个字段（当时只有一家）→ 按本家处理。
    if not data or str(data.get("agent") or "") not in ("", "sd25"):
        return None
    try:
        brief = clone_brief.build(plan, rec, spans, cid=cid)
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
    """生成（或复用）这一单的逐段编辑指令，并落盘。

    返回 `{"sig", "source", "model", "segments":[{index,prompt}], ...}`。
    **失败会抛 `CloneAgentError`** —— 由调用方决定回落还是报错（Phase A 里
    预览用它做并排对比，出片仍未接线）。
    """
    # 🩸 2026-11-01：本文件只管**火山 2.5 那套模板**（中文正文 + 五段标记 +
    #   `@视频1` / `@图片N`）。H3 有自己的一套（`h3_agent`，英文六段式 +
    #   `<Picture N>`），两套不通用 —— 由适配器的 `agent` 字段分派，
    #   别把 H3 的规格书送进这里。

    # 🩸 `cid` 必须传：规格书里的「这一段在做什么」来自盘点缓存，
    #   不传就只能拿到"谁在场"，两段会写成一样（2026-10-31 实测）。
    brief = clone_brief.build(plan, rec, spans, cid=cid)
    sig = signature(brief)
    if not force:
        old = load(cid)
        if old and old.get("sig") == sig:
            log.info("逐段指令命中缓存（%s）", sig)
            return old
    segs = _run_agent(brief, post=post, on_step=on_step)
    data = {
        # 这份是谁按哪套模板写的（`h3_agent` 写 `h3`）。两家共用一个落盘文件，
        # 界面和排查都要能一眼分清。
        "agent": "sd25",
        "sig": sig,
        "source": "agent",
        "model": str(brief.get("model") or ""),
        "created": int(time.time()),
        "brief": brief,
        "segments": segs,
    }
    save(cid, data)
    log.info("逐段指令已落盘：%s（%d 段）", sig, len(segs))
    return data
