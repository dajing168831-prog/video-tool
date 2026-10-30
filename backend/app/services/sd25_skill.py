# -*- coding: utf-8 -*-
"""Seedance 2.5 的「agent 读 skill 包」接入层 —— 与 `sd20_skill` / `h3_skill` 平级并列。

## 和 2.0 的三处硬差别（读完全部 996 行才敢写）

| | 2.0 | 2.5 |
|---|---|---|
| 兜底包 | **必挂**画质/稳定/水印 | **禁止**自动加（`sd25-pe:77`） |
| 稿子形态 | 一段式或分段 | `【生成目标】【参考素材职责】…` 结构化 |
| 素材上限 | 图 9 / 视频 3 / 音频 3 | 图 30 / 视频 10 / 音频 10 / **合计 50** |

所以这里的护栏**只写官方不可能知道的三件事**：有什么工具、本环境没有命令行、提示词与说明怎么分。
写作规则一个字都不抄 —— 2.5 的 skill 有 996 行，抄一遍必漏。

## 🩸 skill 开头那段「触发前的自升级」

官方 `sd25-pe:28-44` 要求每次会话首次触发时执行：

    npx --yes skills@latest update sd25-pe -y

同一份 skill 的 `:996` 又写「**Output only**：本 Skill 输出文本，不要求文件写入、网络、
工具调用或二进制输出能力」。这段话和我们的运行环境一致 —— 我们是纯文本 agent，
没有命令行工具。所以护栏里明说「跳过那段」，别让模型对着一条它执行不了的命令空转。

🔴 官方原文**一个字都不改**（`data/official/sd25/skills/sd25-pe/SKILL.md` 与 MANIFEST
逐字一致，sha256 可查）。跳过规则放在护栏，不动素材。
"""
from __future__ import annotations

import sys
from pathlib import Path

from app.services import ark_chat, skill_agent

ROOT = Path(__file__).resolve().parents[2] / "data" / "official" / "sd25" / "skills"

#: 2.5 的提示词尺子住在 `scripts/ruler_sd25.py`（41 条，带官方锚句 + 成对探针）。
#: 🩸 **不另抄一份精简版**：重抄一遍就多一处漂移，而那份已经被 `--calib/--probes`
#: 校准过。2.0 的 `volc20_pe` 是当年另写的，不代表这条路也该另写。
_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.append(str(_SCRIPTS))

import ruler_sd25  # noqa: E402


class SkillError(ValueError):
    """2.5 提示词优化失败。消息直接给顾客看，写人话。"""


SKILL_GUARD = """## 你怎么干活

顾客要一段视频的提示词，用 Seedance 2.5 生成。

你不是凭经验写 —— 先用 list_skills 看有哪些官方 skill，用 read_skill 读它的 SKILL.md，
然后按它写的流程走。SKILL.md 让你读别的参考文件，就继续 read_skill。

它让你确认信息，就用 ask_user 问。信息够了、或者顾客说"你决定/直接写"，
就用 deliver_prompt 交付。

## 这个环境有几件事做不到

- **没有命令行、没有网络、没有文件写入。** SKILL.md 开头「触发前的自升级」那段
  让你跑一条 `npx ...` 命令 —— 这里执行不了，直接跳过，按当前版本往下走，
  也不要把它写进交付内容。
- **看不到没传给你的素材。** 顾客声明了但当前消息里没附带的素材，保留他的引用标签，
  按 SKILL.md 里「当前 Agent 无法读取」那套降级规则走，别假装看过。

## prompt 和 note 怎么分

- `prompt` —— 能直接提交的 Prompt 正文。SKILL.md 里的 `【生成目标】`、`【参考素材职责】`、
  `【事件脚本】`、`【保持一致】` 这些是正文自己的结构，**保留**；但不要加 Markdown 标题、
  代码围栏、或"以下是优化后的提示词"这类外层包装。
- `note` —— 给顾客看的说明。SKILL.md 允许在正文后追加的 `素材提示：`、`参数提示：`、
  `补充说明：` 放这里，不要放进 `prompt`。

## 合规底线

真人明星、网红、熟人的脸不能拿来当主角或换脸对象；不做色情、暴力、涉及未成年人的性化内容。
碰到就一句话说做不了，再给一个能改的方向，不展开说教。"""


def system_prompt(fixed: list[str] | None = None) -> str:
    parts = [SKILL_GUARD]
    if fixed:
        parts.append("## 本次会话的固定条件\n" + "\n".join(fixed))
    return "\n\n".join(parts)


def _genre_of(p: str) -> str:
    """这份稿子该跑尺子里的哪一体裁。

    判据全是**官方模板里的固定标记**（`sd25-pe:618` 的 `【声音编辑范围】`、
    `:560` 的 `【编辑目标】`、`:654` 的 `向后延长`、`:703` 的 `作为首帧。`），
    不是我们按语义猜的。
    """
    s = p or ""
    if "【声音编辑范围】" in s:
        return "tpl-audio"
    if "【编辑目标】" in s or "唯一编辑母版" in s:
        return "tpl"
    if "向后延长" in s or "向前延长" in s:
        return "ext"
    if "作为首帧" in s or "作为尾帧" in s:
        return "frame"
    return "free"


def judge(prompt: str) -> list[tuple]:
    """交付前过一遍 2.5 官方尺子，**只返回红**（黄是建议项，为它反复烧钱不值）。"""
    ctx = ruler_sd25.ctx_for(prompt, genre=_genre_of(prompt))
    return [(r[0], r[2], r[3], "；".join(r[4]))
            for r in ruler_sd25.check(prompt, ctx) if r[1] == "红"]


def with_images(history: list[dict], images: list[str] | None) -> list[dict]:
    """把本轮图挂到**最后一条 user 消息**上（方舟多模态 content 格式）。

    图必须跟着**那一轮**走，不能另起一条消息 —— 否则模型会把它当成新的素材参考。
    这条 2.5 自己一份，不与 2.0 共用。
    """
    hist = [dict(m) for m in history]
    if not images or not hist:
        return hist
    last = hist[-1]
    if last.get("role") != "user" or not isinstance(last.get("content"), str):
        return hist
    hist[-1] = {
        "role": "user",
        "content": ([{"type": "text", "text": last["content"]}]
                    + [{"type": "image_url", "image_url": {"url": u}} for u in images]),
    }
    return hist


def run(messages: list[dict], *, model: str = "", key: str = "",
        fixed: list[str] | None = None, images: list[str] | None = None,
        post=None, on_step=None
        ) -> skill_agent.AgentResult:
    """跑一轮。`key` 不传就从配置取（与另外两家一个口径）。

    🩸 打开 `nudge`：模型不调工具直接说话时先提醒它一次。2.0 真机抓到过
    「把六个问题当成品交出去，顾客看到的是提问，判据还 0 红」，2.5 的稿子更长、
    更容易直接说出来，同样需要这道兜底。
    """
    model = ark_chat.resolve(model)
    if not key and post is None:
        from app.core.config import settings
        key = (settings.ark_api_key or "").strip()
        if not key:
            raise skill_agent.AgentError("方舟未配置：请设置 VT_ARK_API_KEY")
    return skill_agent.run(
        ROOT, system=system_prompt(fixed), messages=with_images(messages, images),
        model=model, key=key, judge=judge, post=post, on_step=on_step, nudge=True)
