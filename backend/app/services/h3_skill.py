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

#: 产品的输出形态与工具用法。**官方写作规则一律不在里面** ——
#: 它们在 `data/official/h3/skills/` 里，模型自己读。
#:
#: 🩸 2026-10-31 主人：「agents 调模型里面本来就已经有执行标准了，我们自己又再要求一次？」
#:   原来这份 132 行，把官方已经写死的重抄了一遍，还抄漏过：
#:   · 「台词/画面文字一个字不许编」→ 官方有，而且更严：
#:     `h3-prompt-writing/references/base-en.txt:129`「only the language tag and the
#:     **actual user-provided** spoken content，**preserve every original word and
#:     punctuation mark verbatim; do not translate or rewrite**」；
#:     `ref-en.txt:274` 还规定听不清写 `[unclear]`，不许猜、不许改写；
#:     `ref-en.txt:217`「Preserve the original language of dialogue, lyrics, and visible text」
#:   · 「`<Picture N>` 按上传顺序编号」→ `ref-en.txt:110`「每个序号只表示它**在自己类别内**
#:     的顺序」，`:35`「标签一旦分配，全程含义一致」
#:   现在只留官方不可能知道的三件事：**有什么工具**、**prompt 与 note 怎么分**、
#:   **compatibility 里的「需要 Hub 画布」该怎么理解**。
SKILL_GUARD = """## 你怎么干活

顾客要一段视频的提示词。你不凭经验写 —— 先用 list_skills 看有哪些官方 skill，
挑对的那个，用 read_skill 读它的 SKILL.md，然后按它写的流程走。
SKILL.md 让你读别的参考文件，就继续 read_skill。

它让你确认信息，就用 ask_user 问。信息够了、或者顾客说"你决定/直接写"，
就用 deliver_prompt 交付：

- `prompt` —— 提示词正文，能直接粘进 H3 的那一份。从第一个字段名开始，不要标题、不要说明
- `note` —— 给顾客看的说明：你替他补了什么、改了什么。用人话，没有就留空

## 你只写提示词

- 你不生成视频，不能说自己"已经出片"，也不能保证效果。
- 你读不到画布 —— skill 里让你在画布上生图、点按钮、出片的步骤，**一个字都不要写进正文**：
  正文只能是能直接粘进 H3 的那份提示词。要交代的操作（先出锚图、比例多少、按什么顺序
  传图）写进 `note`。
- 体裁包的 `compatibility` 会写「需要 Hub 画布」—— 那说的是**画布上那几步工具**我们做不了，
  **不是整个 skill 不适用**：它怎么问顾客、怎么排镜头、这个题材要注意什么，照样按它来。
  别因为这一句就退回去只读 `h3-prompt-writing` 写个通用提示词。

## 合规底线

真人明星、网红、熟人的脸不能拿来当主角或换脸对象；不做色情、暴力、涉及未成年人的性化内容；
不把别人的成片逐帧复刻到能认出原作者。碰到就一句话说做不了，再给一个能改的方向。"""


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
    """三字段下是哪种子模式。线索不足按 t2va（不带首尾帧指令）。

    🩸 2026-10-31 先加过「也认 `@图片1`」，随后**撤回**：查 H3 全部 56 条 run_log，
    输入 `@图片` 0 次、产出 `@图片` 0 次；真机让顾客写 `@图片1`，模型读完 ref-en
    也自己转成了 `<Picture 1>`。这条修复对应的场景不存在 —— 留着就是给猜的场景
    加代码。
    """
    p = prompt or ""
    if "<Picture 1>" in p and "<Picture 2>" in p:
        return "fl2va"
    if "<Picture 1>" in p:
        return "i2va"
    return "t2va"


def with_images(history: list[dict], images: list[str] | None) -> list[dict]:
    """把本轮图挂到**最后一条 user 消息**上（方舟多模态 content 格式）。

    🩸 2026-10-31：顾客**第一次就给参考图出稿**（「用这张图里的女生」）时
    还没有提示词可修，走不了 `/prompt/revise`，图只能跟着这条对话走。
    以前 `run` 没有 images 参数，传了图会被静默丢掉。

    图必须挂在**那一轮**上，不能另起一条消息 —— 否则模型会把它当成新的
    素材参考。这条 H3 自己一份，不与 2.0 共用。
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
    """跑一轮。`key` 不传就从配置取（和 `sd20_skill.run` 一个口径）。

    🩸 `model` 要**翻译成方舟的真实端点名**再发。前端传的是白名单里的键
    （`lite` / `pro` / `deepseek`），直通出去就是 `404 InvalidEndpointOrModel`。
    2026-10-30 真机第一次跑就撞上 —— 那时三条路各抄一份白名单，就这一份漏了翻。
    现在统一走 `ark_chat.resolve()`，**抄一份就埋一个 404**，所以只留一份。

    🩸 2026-10-31：加 `images`。顾客**第一次就给参考图**出稿（「用这张图里的
    女生」）没有提示词可修，走不了 `/prompt/revise`，只能在这条对话路里看图。
    以前这条签名没有 images，前端只好把所有带图的请求全塞进修订路 —— 顾客的
    原话被当成「已有的提示词」去改。挂图用本文件自己的 `with_images`。
    """
    model = ark_chat.resolve(model)
    if not key and post is None:
        from app.core.config import settings
        key = (settings.ark_api_key or "").strip()
        if not key:
            raise skill_agent.AgentError("方舟未配置：请设置 VT_ARK_API_KEY")
    return skill_agent.run(
        ROOT, system=system_prompt(fixed),
        messages=with_images(messages, images),
        model=model, key=key, judge=judge, post=post, on_step=on_step)
