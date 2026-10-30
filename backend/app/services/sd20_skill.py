# -*- coding: utf-8 -*-
"""Seedance 2.0 的「agent 读 skill 包」接入层 —— 与 `h3_skill` **平级，互不 import**。

2026-10-30 主人：「现在做 2.0 提示词优化，也是用 agents 调 2.0 skill，之前那些方案都不要了」。

## 换掉了什么

`sd20_direct` 把 `skill + guide + trouble + tips + 运镜表`（1684 行）拼进 system，
每次对话全付；读哪份由**我们**决定。现在改成模型自己 `list_skills → read_skill`：

| | 旧（`sd20_direct`，已删） | 本文件 |
|---|---|---|
| 谁决定读哪份 | 我们全塞进 system | 模型读完 SKILL.md 自己指路 |
| system 大小 | 16 万+ 字符，每次全付 | 只有产品层 |
| 输出协议 | `<<<ASK>>>` / `<<<PROMPT>>>` / `<<<NOTE>>>` 文本标记 | 工具调用（`ask_user` / `deliver_prompt`） |

## 🩸 只放产品层，一条写作规则都不放

官方规则全在 skill 包里（`data/official/sd20/skills/sd2-pe/`），
system 里**只有**"怎么用工具、产品要什么形态"。
把官方规则复述进护栏的教训见 `h3_skill` 顶部：复述漏了，模型就拿着残缺版干活。

## 2.0 的官方 skill 只有**一个**

H3 有 1 个通用 + 8 个体裁包；火山方舟官方只发布 `sd2-pe` 一个。
但它本身比 H3 的通用包厚得多：SKILL.md 225 行（H3 是 40 行）+ references 1459 行
（官方提示词指南 1007 行 H3 没有对等物）。**不分体裁 ≠ 不详细。**
"""
from __future__ import annotations

from pathlib import Path

from app.services import ark_chat, skill_agent
from app.services.models import volc20_pe

ROOT = Path(__file__).resolve().parents[2] / "data" / "official" / "sd20" / "skills"


class SkillError(ValueError):
    """2.0 提示词优化失败。消息直接给顾客看，写人话。"""

#: 产品的输出形态与工具用法。**官方写作规则一律不在里面** ——
#: 它们在 `data/official/sd20/skills/sd2-pe/` 里，模型自己读。
#:
#: 🩸 2026-10-31 主人：「agents 调模型里面本来就已经有执行标准了，我们自己又再要求一次？」
#:   原来这份 1300 字，把官方 SKILL.md 已经写死的又重抄一遍（`@图片N` 按上传顺序编号
#:   = Step 2.1；「一次别超过 3 个问题」= Step 0 的提问模板就是 3 问），
#:   还从**复刻视频项目**（已冻结）搬了「一个人一张图」进来 —— 两个项目不串。
#:   现在只留官方不可能知道的两件事：**有什么工具**、**prompt 与 note 怎么分**。
SKILL_GUARD = """## 你怎么干活

顾客要一段视频的提示词，用 Seedance 2.0 生成。

你不凭经验写 —— 先用 list_skills 看有哪些官方 skill，用 read_skill 读它的 SKILL.md，
然后按它写的流程走。SKILL.md 让你读别的参考文件，就继续 read_skill。

它让你确认信息，就用 ask_user 问。信息够了、或者顾客说"你决定/直接写"，
就用 deliver_prompt 交付：

- `prompt` —— 提示词正文，能直接粘进 2.0 的那一份。从第一句开始，不要标题、不要说明
- `note` —— 给顾客看的说明：你替他补了什么、改了什么。用人话，没有就留空

## 合规底线

真人明星、网红、熟人的脸不能拿来当主角或换脸对象；不做色情、暴力、涉及未成年人的性化内容。
碰到就一句话说做不了，再给一个能改的方向，不展开说教。"""


def system_prompt(fixed: list[str] | None = None) -> str:
    parts = [SKILL_GUARD]
    if fixed:
        parts.append("## 本次会话的固定条件\n" + "\n".join(fixed))
    return "\n\n".join(parts)


def judge(prompt: str) -> list[tuple]:
    """交付前过一遍 2.0 官方尺子，**只返回红**（黄是建议项，为它反复烧钱不值）。"""
    return [(r[0], r[2], r[3], "；".join(r[4]))
            for r in volc20_pe.check(prompt) if r[1] == "红"]


def with_images(history: list[dict], images: list[str] | None) -> list[dict]:
    """把本轮截图挂到**最后一条 user 消息**上（方舟多模态 content 格式）。

    🩸 顾客说「这儿不对」时传的是截图，文字往往只有一个字；图必须跟着
    那一轮走，不能另起一条消息 —— 否则模型会把它当成新的素材参考。
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
    """跑一轮。`key` 不传就从配置取（与 `h3_skill.run` 一个口径）。

    `model` 必须翻译成方舟的真实端点名再发 —— 前端传的是白名单里的键
    （`lite` / `pro` / `deepseek`），直通出去就是 `404 InvalidEndpointOrModel`。

    🩸 2026-10-31 真机抓到：模型把「我想跟你确认几个细节」写成一段回复，
    **没调 `ask_user`** —— 执行器原来直接当成品交付，顾客拿到问题当提示词，
    判据还 0 红。2.0 这条打开 `nudge`：先提醒它一次，提醒过还不用才当正文收。
    **H3 那条不打开**（`skill_agent.run` 里默认关），两家各管各的。
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
