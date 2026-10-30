# -*- coding: utf-8 -*-
"""H3 的**两条老路**：转换（粘现成稿 → 换官方语法）和修订（带截图 → 只改那几处）。

## 🔴 边界：本文件的规矩只管这两条路

对话出稿（`/prompt/chat`，target=h3）2026-10-30 已经改走 `h3_skill` —— 模型自己
`list_skills` → `read_skill` → 交付，**读哪份官方文件、走哪条格式，模型读完 SKILL.md 自己定**。

所以：

- 这里 `generate` / `revise` 把官方原文拼进 system（`h3_official.system_prompt`），
  是**这两条路专用**的做法，因为它们要「逐字守住一份已有的稿子」；
- **别把这里的护栏、字段、长度规矩套到 agent 那条路上去** —— 那条路的规则只在 skill
  包里，我们说一句都不算数；
- 反过来 `h3_skill` 也不 import 本文件（共用件在 `models/h3_common.py` 和 `ark_chat.py`）。

## 为什么不是"新旧关系"

两条路的输入不一样：转换/修订手里**已经有一份稿**，要的是保真；对话是从零写，
要的是体裁适配。它们**互不替代**，不是等着被淘汰的旧代码。

## 拆槽那套确实下线了

2026-10-29 主人一句话点破：「都已经调模型了，而且他们的能力包括你自己的能力你都不知道的吗？」
拆槽、闭集清洗、代码拼装都是替模型瞎操心，2026-10-30 连同 `/prompt/optimize` 一起删了
（存档 `docs/_archive/deleted-2026-10-30/`）。
"""
from __future__ import annotations

from app.services import ark_chat, h3_official
from app.services.models.h3_common import (
    MAX_CHARS, MAX_SOURCE_CHARS, guess_kind)


class DirectError(ValueError):
    """直出失败。消息直接给顾客看，写人话。"""


def user_message(text: str, *, duration: float, assets: list[dict],
                 ratio: str = "", hint: str = "") -> str:
    """顾客的稿 + 素材清单 + 片长画幅 + 上一轮的判红理由。"""
    parts = [f"【目标片长】{duration:g} 秒", f"【提示词总长硬上限】{MAX_CHARS} 字符"]
    if ratio:
        parts.append(f"【画幅】{ratio}")
    if assets:
        # 🩸 必须写清用途：同一张图当 `first_frame` 和当 `reference_image`，
        # 官方是**两种完全不同的模式**（`api-create:212-214` 还规定二者不可混用）。
        # 只给标签不说用途，模型会按参考图写，首帧那边就全错。
        lines = [f"{a['label']} —— {a.get('role_desc') or a.get('role') or '用途未说明'}"
                 f"；{a.get('note') or '（顾客没写是什么）'}" for a in assets]
        parts.append("【顾客真实上传的素材（只能用这些标签）】\n" + "\n".join(lines))
    else:
        parts.append("【素材】无（走文生视频，不要出现任何参考标签）")
    parts.append("【顾客提供的原文】\n" + text.strip())
    if hint.strip():
        parts.append("【上一轮被判红的地方 —— 逐条改掉再交】\n" + hint.strip())
    return "\n\n".join(parts)


def _post(body: dict, key: str) -> str:
    """一次方舟 chat/completions，只取正文。"""
    try:
        d = ark_chat.post(body, key=key)
    except ark_chat.ArkError as e:
        raise DirectError(str(e)) from e
    try:
        return (d["choices"][0]["message"]["content"] or "").strip()
    except Exception as e:                                  # noqa: BLE001
        raise DirectError(f"生成响应结构异常：{e}") from e


def _body(model: str, messages: list[dict]) -> dict:
    return {
        "model": ark_chat.resolve(model),
        "messages": messages,
        "temperature": 0.2,
        # 🩸 2026-10-30 主人：「是不是没给思考？直接按标准输出了？」
        # 对。`thinking: disabled` 是从**拆槽**那一步抄来的（填 JSON 简单，关了快 13 倍）。
        # 但这一环是**写一份 7000 字符的完整提示词**，关掉思考等于不推理直接吐 ——
        # 实测第一轮六段结构散（E1/E2/E8 红）、字数在 7681 / 8755 之间乱跳。
        "thinking": {"type": "enabled"},
    }


def _chat(sys_msg: str, user_msg: str, *, model: str, key: str,
          images: list[str] | None = None) -> str:
    """`images` 是 data URI 列表（`data:image/jpeg;base64,…`），走方舟的多模态 content。"""
    content: object = user_msg
    if images:
        content = [{"type": "text", "text": user_msg}]
        content += [{"type": "image_url", "image_url": {"url": u}} for u in images]
    return _post(_body(model, [{"role": "system", "content": sys_msg},
                               {"role": "user", "content": content}]), key)


def _strip_fence(s: str) -> str:
    t = (s or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


def _reds(prompt: str, judge) -> list:
    """交付前查三件事：空、超长、判据。返回问题列表（空 = 可以交）。

    🩸 长度是**接口硬限制**（`api-create:407`），不是建议 —— 超了顾客粘进去直接报错。
    """
    if not prompt:
        return [("空", "模型交回了空内容", "", "")]
    if len(prompt) > MAX_CHARS:
        return [("长", f"总长 {len(prompt)} 字符，超过官方上限 {MAX_CHARS}",
                 "api-create:407", "必须压到上限以内")]
    return judge(prompt) if judge is not None else []


def _deliver(send, *, judge, attempts: int) -> dict:
    """发一轮 → 查 → 有问题就带着**官方出处**回灌一次 → 交。

    `send(hint) -> 模型原始输出`。转换和修订共用这一段 —— 原来两份抄在一起，
    改一处必漏另一处（长度上限就是这么漏的：base 尺子有、ref 尺子没有）。
    """
    hint = ""
    tries: list[dict] = []
    for n in range(1, max(1, attempts) + 1):
        out = _strip_fence(send(hint))
        problems = _reds(out, judge)
        tries.append({"n": n, "chars": len(out),
                      "red": [f"{p[0]} {p[1]}" for p in problems]})
        if not problems or n >= attempts:
            got = {"prompt": out, "tries": tries, "hint": hint}
            if problems:
                got["red"] = problems
            return got
        # 回灌只喂「哪条规矩没过 + 官方出处」，不喂任何创作要求
        hint = "\n".join(f"- [{rid}] {name}（官方出处 {src_}）：{why}"
                         for rid, name, src_, why in problems)
    raise DirectError("生成没能完成")   # 到不了：循环里每次都有 return


def generate(text: str, *, kind: str, duration: float, assets: list[dict],
             ratio: str = "", model: str = "", judge=None,
             attempts: int = 2, chat=None) -> dict:
    """模型按官方原文直出成品提示词；`judge(prompt) -> [(编号, 名称, 出处, 说明)]` 判红回灌。

    `kind` = base（三字段）/ ref（六段式），由 `h3_convert_route` 判出来。
    `chat` 可注入桩函数（测试用，零花费）；不传就走方舟（**会花钱**）。
    """
    from app.core.config import settings

    src = (text or "").strip()
    if not src:
        raise DirectError("原稿是空的")
    if len(src) > MAX_SOURCE_CHARS:
        raise DirectError(f"原稿 {len(src)} 字，超过上限 {MAX_SOURCE_CHARS} 字")

    key = (settings.ark_api_key or "").strip()
    if not key and chat is None:
        raise DirectError("方舟未配置：请设置 VT_ARK_API_KEY")

    sys_msg = h3_official.system_prompt(kind, (
        "## 本产品的交付形态\n"
        "**直接交成品提示词**，不要 JSON、不要解释、不要 Markdown 代码块以外的任何包装。\n"
        "保真护栏（顾客粘的是现成稿时适用）：镜头数、镜头顺序、镜头内容、台词原话、"
        "画面内文字，一条都不许增删或翻译；原稿没写的不许补，没写幅度/速度就不写。"
    ))

    def send(hint: str) -> str:
        msg = user_message(src, duration=duration, assets=assets, ratio=ratio, hint=hint)
        return chat(sys_msg, msg) if chat else _chat(sys_msg, msg, model=model, key=key)

    return _deliver(send, judge=judge, attempts=attempts)


# ---------------------------------------------------------------- 修订（出了片，改几处）
#
# 🩸 2026-10-30 主人：「今天说的产出的视频效果不理想，切图回来反馈让他修改部分提示词。
# 你现在这样的输入和操作方式我感觉很落后」——
# 产品不该是「粘一段稿子进去换一份新的出来」，而该是**闭环**：
#   出片 → 看效果不对 → 切图回来 → 只说哪不对 → 只改那几处。
# 模型本来就能读图（`settings.vision_model`），这条路口一直是通的。

REVISE_GUARD = (
    "## 本产品的修订规则（**这是修订，不是重写**）\n"
    "顾客已经有一份能用的 H3 提示词，片子也出来了，只是有几处不对。他会给你截图和一句话说明。\n"
    "A. **先看图**，看清顾客说的是哪一个镜头、哪一处；图里能对上的细节以图为准；\n"
    "B. **只改反馈指出的地方**。没被指出来的镜头、台词、画面内文字、段落顺序，"
    "一个字都不许动 —— 逐字保留；\n"
    "C. 输出**完整的新提示词**（不是 diff、不是说明），顾客要能直接拿去用；\n"
    "D. 不要顺手优化别的地方，不要补顾客没说的内容；\n"
    "E. 改完如果字数变了，仍要守住官方总长上限。"
)


def revise(prompt: str, feedback: str, *, images: list[str],
           kind: str = "", duration: float = 5.0, model: str = "",
           judge=None, attempts: int = 2, chat=None) -> dict:
    """现有提示词 + 截图 + 一句话反馈 → 只改那几处的新提示词。

    `images` 是 data URI 列表。`chat` 可注入桩（零费用测试）。
    """
    from app.core.config import settings

    src = (prompt or "").strip()
    fb = (feedback or "").strip()
    if not src:
        raise DirectError("要修订的提示词是空的")
    if not fb and not images:
        raise DirectError("请说明哪里不对，或者传一张出了问题的截图")
    if len(src) > MAX_SOURCE_CHARS:
        raise DirectError(f"提示词 {len(src)} 字，超过上限 {MAX_SOURCE_CHARS} 字")

    key = (settings.ark_api_key or "").strip()
    if not key and chat is None:
        raise DirectError("方舟未配置：请设置 VT_ARK_API_KEY")

    k = kind or guess_kind(src)
    sys_msg = h3_official.system_prompt(k, REVISE_GUARD)

    msg = (f"【目标片长】{duration:g} 秒\n\n"
           f"【现有提示词（完整）】\n{src}\n\n"
           f"【顾客的反馈】\n{fb or '（顾客只给了截图，没说文字）'}")
    if images:
        msg += f"\n\n【出问题的画面截图】共 {len(images)} 张，见下。"

    def send(hint: str) -> str:
        use = msg + (f"\n\n【上一轮被判红的地方 —— 逐条改掉再交】\n{hint}" if hint else "")
        return (chat(sys_msg, use, images=images) if chat
                else _chat(sys_msg, use, model=model, key=key, images=images))

    got = _deliver(send, judge=judge, attempts=attempts)
    got["kind"] = k
    return got

