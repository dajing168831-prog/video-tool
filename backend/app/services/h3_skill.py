# -*- coding: utf-8 -*-
"""H3 的「agent 读 skill 包」接入层 —— 与 `h3_direct` **平级，互不 import**。

## 和 `h3_direct` 的分工

| | `h3_direct`（转换 / 修订） | 本文件（对话出稿） |
|---|---|---|
| skill 怎么进模型 | 我们人工挑 base-en/ref-en 拼进 system | **模型自己 list_skills → read_skill** |
| 谁决定走 base 还是 ref | 我们先判 `conv_route` | 模型读完 SKILL.md 自己判 |
| 体裁（产品广告/3D动画/MV…） | 完全没有 | 9 个官方 skill 包全在目录里 |

两家共用的只有中立件：`ark_chat.py`（型号白名单 + 传输）、`models/h3_common.py`
（长度上限、格式分类、素材用途说明）。**共用的东西不放任何一家身上** ——
2026-10-30 之前这边 import 了 `h3_direct`，等于新路靠旧路活着，旧路一删新路就断。

## 🩸 只放产品层，一条 skill 内容都不放

2026-10-30 的教训：我们把官方规则复述进护栏，还复述漏了，模型就拿着那版残缺规则干活。
这里 system 里**只有**"怎么用工具、产品要什么形态"，写作规则全在 skill 包里。

🔴 **别把 `h3_direct` 的规矩搬过来**（那些是"守住一份已有稿子"用的）——
这条路的规则只在 skill 包里，说什么都不算数。
"""
from __future__ import annotations

from pathlib import Path

from app.services import ark_chat, skill_agent
from app.services.models import h3_base, h3_ref
from app.services.models.h3_common import guess_kind

ROOT = Path(__file__).resolve().parents[2] / "data" / "official" / "h3" / "skills"

#: 产品的输出形态与能力边界。**官方规则一律不在里面**。
SKILL_GUARD = """## 你怎么干活

顾客要一段视频的提示词。你不凭经验写，也不凭我记得的规则写 ——
**先用 list_skills 看有哪些官方 skill，挑对的那个，用 read_skill 读它的 SKILL.md，
然后严格按它写的流程走**。SKILL.md 让你读别的参考文件，就继续 read_skill。

它让你先确认信息，就用 ask_user 问（一次别超过 3 个问题）。
信息够了、或者顾客说"你决定/直接写"，就 deliver_prompt 交付。

不要凭自己的经验补规矩 —— 你没读到的东西，就是不该写的东西。

## 两个原件必须顾客给（我们的产品规矩，不是官方规定）

**台词原话**、**画面里出现的字** —— 这两样一个字都不许你编。
顾客没给，就不写台词、不写画面文字（或者按 SKILL.md 的办法处理）。

## 顾客传了图的时候

**先分清这是哪一种**（看对话历史）：

- 历史里还没有你交付过的提示词 → 这是**参考素材**（"这就是我主角"）。照图写准，
  不要说成"哪儿不对"，也不要去改根本不存在的上一稿。
- 历史里已经有你交付过的提示词 → 这是**成片截图**，他在指出哪儿不对。
  只改他指出的那几处，没被指到的句子一个字都不许动。

附件图按**上传顺序**编号：这一轮传的第 1 张就是 `<Picture 1>`，第 2 张 `<Picture 2>`，
顾客在出片时要按同样顺序传。

## 你做不到的事（能力边界，不是客气话）

- 你只写提示词。你不生成视频，不能说自己"已经出片"，也不能保证效果。
- 你读不到画布、读不到素材文件本身 —— skill 里提到要用 Hub 画布/工具生图/出片的步骤，
  **一个字都不要写进正文**：正文只能是能直接粘进 H3 的那份提示词，从第一个字段名开始。
  要交代的操作（先出锚图、比例多少、按什么顺序传图）写进 `note`，那是给顾客看的话。
  也不要说"我已经生成了"。
- 不确定的参数一律不写，不许估。

## 必须拒的

- 用真实存在的具体他人的脸（明星、网红、熟人照片）当主角或换脸对象
- 色情、暴力、涉及未成年人的性化内容
- 拿别人的成片逐帧复刻到能认出原作者的程度

拒绝只说一句"这个我做不了"，然后给一个能改的方向，不展开说教。"""


def system_prompt(fixed: list[str] | None = None) -> str:
    parts = [SKILL_GUARD]
    if fixed:
        parts.append("## 本次会话的固定条件\n" + "\n".join(fixed))
    return "\n\n".join(parts)


def judge(prompt: str) -> list[tuple]:
    """交付前过一遍官方尺子，**只返回红**。

    模式由成品自己判（有 `subject_definitions` 就是六段式）—— 模型走哪条路是它读完
    SKILL.md 自己定的，我们不去猜，看结果反推。
    """
    kind = guess_kind(prompt)
    if kind == "ref":
        rows = h3_ref.check(prompt,
                            h3_ref.ctx_for(prompt, edit_master=None, audio=None))
    else:
        rows = h3_base.check(prompt, {"mode": _mode_of(prompt)})
    return [(r[0], r[2], r[3], "；".join(r[4])) for r in rows if r[1] == "红"]


def _mode_of(prompt: str) -> str:
    """三字段下是哪种子模式。线索不足按 t2va（不带首尾帧指令）。"""
    p = prompt or ""
    if "<Picture 1>" in p and "<Picture 2>" in p:
        return "fl2va"
    if "<Picture 1>" in p:
        return "i2va"
    return "t2va"


def run(messages: list[dict], *, model: str = "", key: str = "",
        fixed: list[str] | None = None, post=None, on_step=None
        ) -> skill_agent.AgentResult:
    """跑一轮。`key` 不传就从配置取（和 `sd20_direct.chat_turn` 一个口径）。

    🩸 `model` 要**翻译成方舟的真实端点名**再发。前端传的是白名单里的键
    （`lite` / `pro` / `deepseek`），直通出去就是 `404 InvalidEndpointOrModel`。
    2026-10-30 真机第一次跑就撞上 —— 那时三条路各抄一份白名单，就这一份漏了翻。
    现在统一走 `ark_chat.resolve()`，**抄一份就埋一个 404**，所以只留一份。
    """
    model = ark_chat.resolve(model)
    if not key and post is None:
        from app.core.config import settings
        key = (settings.ark_api_key or "").strip()
        if not key:
            raise skill_agent.AgentError("方舟未配置：请设置 VT_ARK_API_KEY")
    return skill_agent.run(
        ROOT, system=system_prompt(fixed), messages=messages,
        model=model, key=key, judge=judge, post=post, on_step=on_step)
