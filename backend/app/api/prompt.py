"""提示词优化 API —— 把顾客的一句话/一段现成提示词，变成指定模型的官方格式提示词。

四条路，一家一个实现，**互不替代**：

| 路 | 入口 | 谁干活 |
|---|---|---|
| 对话出稿 | `/prompt/chat`（target=h3） | `h3_skill` → 模型自己读官方 skill 包 |
| 对话出稿 | `/prompt/chat`（target=sd20） | `sd20_direct` → 2.0 官方材料拼进 system |
| 转换 | `/prompt/convert` | `h3_direct.generate` → 摘现成稿，只换语法 |
| 修订 | `/prompt/revise` | `h3_direct.revise` → 带截图只改那几处 |

🩸 这里原本还有 `/prompt/optimize`（拆槽 → 收口 → 编译 → 自检 四步），
2026-10-30 主人一句「死代码！都删了」下掉了：拆槽方案 2026-10-29 就已经被推翻
（`h3_direct` 顶部写明），代码却还挂着、还有 46 条断言天天跑绿。存档见
`docs/_archive/deleted-2026-10-30/`。

四条路都在返回之前过判据：红的条目带着**官方出处**回灌重试一次；
还红就如实返回并点名哪条不对 —— 吞掉比报错更糟。
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.routes import fail, ok
from app.core.config import settings
from app.services import ark_chat
from app.services import h3_convert_route as conv_route
from app.services import h3_direct
from app.services import h3_skill
from app.services import sd20_direct
from app.services import skill_agent
from app.services.models import h3_base as rules
from app.services.models.h3_common import MAX_SOURCE_CHARS, ROLE_DESC, guess_kind
from app.services.models import h3_base_compile as hbc
from app.services.models import h3_ref
from app.services.models import volc20_pe

log = logging.getLogger(__name__)
router = APIRouter()

KINDS = ("rewrite", "idea")

#: 可选的理解模型（只影响"想/写"这一步，不影响出片）。
#: 🩸 白名单只有一份，在 `ark_chat.py`。这里**不再抄一份** ——
#: 原来三份各抄一遍翻译逻辑，`h3_skill` 那份漏翻 → 真机 404。
#: 默认型号也是同一个（原来这里写 lite、实际用的是 pro，健康检查报的和做的不一致）。

#: 官方 API 的片长范围（`h3-api`：整数 4–15）。
DUR_MIN, DUR_MAX = 4, 15

#: 顾客一次能粘多少字。超过这个量基本是整篇脚本，不是一句提示词。
MAX_TEXT = 4000

@router.get("/prompt/health")
async def prompt_health():
    """给前端探活用：模型配好没有、闭集有多大。不花钱、不联网。"""
    return ok({
        "model": ark_chat.MODELS[ark_chat.DEFAULT_MODEL],
        "models": [{"key": k, "id": v} for k, v in ark_chat.MODELS.items()],
        "ark_configured": bool((settings.ark_api_key or "").strip()),
        "kinds": list(KINDS),
        "ratios": list(hbc.RATIOS),
        "rules": len(rules.RULES),
        "max_text": MAX_TEXT,
        "duration_range": [DUR_MIN, DUR_MAX],
        # 转换那一路（別家稿 → H3）：素材怎么填、能粘多少字、支持哪些型号
        "convert": {
            "max_text": MAX_SOURCE_CHARS,
            "variants": {k: list(v) for k, v in conv_route.VARIANTS.items()},
            "roles": list(conv_route.ROLES),
            "asset_kinds": ["image", "video", "audio"],
            "formats": {k: v["name"] for k, v in conv_route.GUIDES.items()},
        },
    })


# ---------------------------------------------------------------- 转换（别家稿 → H3）
#
# 跟 `/prompt/chat` 是**两件事**：那边是"顾客只有想法/一句话"，这边是
# "顾客手里已经有一份别家模型写好的提示词，要原样搬成 H3 的语法"。
# 所以这边**一个字都不创作**：镜头数、台词、画面文字一条不许动。

class ConvertAssetIn(BaseModel):
    kind: str = Field("image", description="素材类型：image / video / audio")
    role: str = Field("", description="first_frame / last_frame / reference_image / "
                                     "reference_video / reference_audio；留空 = 顾客没说清")
    seconds: float = Field(0.0, description="视频/音频单段时长，图片不看")
    label: str = Field("", description="六段式要用的标签，如 <Picture 1>")
    note: str = Field("", description="这份素材是什么、在片子里起什么作用")


class ConvertIn(BaseModel):
    text: str = Field(..., description="别家模型写的视频提示词原文")
    duration: float = Field(5.0, description="目标片长，官方 4–15 秒（Max 是 5–15）")
    model: str = Field("", description="理解模型：lite / pro / deepseek，留空 = pro")
    variant: str = Field("MiniMax-H3", description="目标 H3 型号，决定时长下限")
    assets: list[ConvertAssetIn] = Field(
        default_factory=list, description="顾客这次要用的素材；一样不传 = 文生视频")


def _judge_rows(prompt: str, guide: str, mode: str) -> list[tuple]:
    """按路由判出来的格式选尺子，只返回红。**两把尺子互不引用**。

    返回 `(编号, 名称, 官方出处, 说明)` —— 回灌时要把出处一起喂回去，
    模型才知道该按官方哪一条改。
    """
    if guide == "ref":
        rows = h3_ref.check(prompt, h3_ref.ctx_for(prompt, edit_master=None, audio=None))
    else:
        rows = rules.check(prompt, {"mode": mode})
    return [(r[0], r[2], r[3], "；".join(r[4])) for r in rows if r[1] == "红"]


def _convert(body: ConvertIn) -> dict:
    """同步实现（在 thread 里跑）。零创作：只拆结构、只拼装。"""
    text = (body.text or "").strip()
    if not text:
        raise h3_direct.DirectError("原稿是空的")
    if len(text) > MAX_SOURCE_CHARS:
        raise h3_direct.DirectError(
            f"原稿 {len(text)} 字，超过上限 {MAX_SOURCE_CHARS} 字")

    try:
        assets = [conv_route.Asset(a.kind, a.role, a.seconds) for a in body.assets]
    except ValueError as e:
        raise h3_direct.DirectError(str(e)) from e

    r = conv_route.route(assets, model=body.variant)
    if r["problems"]:
        # 素材本身不合官方规矩（互斥/超量），删哪张是顾客的决定，不替顾客改
        raise h3_direct.DirectError("；".join(r["problems"]))
    if r["questions"] or not r["mode"]:
        raise h3_direct.DirectError(
            "模式判不了，得先问顾客：" + ("；".join(r["questions"]) or "素材组合没覆盖"))

    # 片长按型号夹到官方范围，夹了要如实说（跟 optimize 同一口径）
    lo, hi = r["duration"]
    dur = float(body.duration)
    clamp_note = ""
    if dur < lo or dur > hi:
        fixed = float(max(lo, min(hi, dur)))
        clamp_note = f"片长 {dur:g} 秒超出 {body.variant} 的范围（{lo}–{hi}），已按 {fixed:g} 秒转"
        dur = fixed

    # 理解模型的键名（lite/pro/deepseek）—— 不许前端传任意 model 名，直通方舟等于开计费口子
    key = body.model or ark_chat.DEFAULT_MODEL
    mid = ark_chat.resolve(key)

    # 🩸 模型按官方 skill **直出成品**，不再拆槽、不再用代码拼装（2026-10-29 主人：
    # 「都已经调模型了……如果要在前端+后端帮顾客实现这件事我们又要怎样做」）。
    # 代码只留判模式 + 喂原文 + 尺子验收；判红就把红的条目和官方出处喂回去重试一次。
    # 用途要带给模型（首帧 vs 参考图是两种模式）。视频/音频顾客没填用途时，
    # `normalize` 会补成 reference_*，这里按补齐后的角色取说明，别用原值。
    _norm, _ = conv_route.normalize(assets)
    pairs = [{"label": b.label, "note": b.note,
              "role_desc": ROLE_DESC.get(n.role, "")}
             for b, n in zip(body.assets, _norm)]
    got = h3_direct.generate(
        text, kind=r["guide"], duration=dur, assets=pairs, model=key,
        judge=lambda p: _judge_rows(p, r["guide"], r["mode"]))

    prompt = got["prompt"]
    yellow = ([x[0] for x in h3_ref.check(
        prompt, h3_ref.ctx_for(prompt, edit_master=None, audio=None)) if x[1] == "黄"]
        if r["guide"] == "ref"
        else [x[0] for x in rules.check(prompt, {"mode": r["mode"]}) if x[1] == "黄"])
    return {
        "prompt": prompt,
        "mode": r["mode"],
        "format": r["format"],
        "ruler": r["ruler"],
        "chars": len(prompt),
        "duration": dur,
        "ratio": r["ratio"],
        "assets_note": r["notes"],
        "warnings": ([clamp_note] if clamp_note else []),
        "tries": got["tries"],
        # 前端那句「通过官方判据 N 条」直接读这个数 —— 硬编码会随规则增加变谎
        "rules": len(h3_ref.RULES) if r["guide"] == "ref" else len(rules.RULES),
        # 最后一轮还没过的红条目；一轮就过的就是空
        "red": [f"{x[0]} {x[1]}：{x[3]}" for x in (got.get("red") or [])],
        "yellow": yellow,
        "model": mid,
    }


@router.post("/prompt/convert")
async def convert(body: ConvertIn):
    if body.model and body.model not in ark_chat.MODELS:
        return fail(f"模型只认 {tuple(ark_chat.MODELS)}")
    if body.variant not in conv_route.VARIANTS:
        return fail(f"H3 型号只认 {tuple(conv_route.VARIANTS)}")
    if not (settings.ark_api_key or "").strip():
        return fail("方舟未配置：请设置 VT_ARK_API_KEY")

    try:
        data = await asyncio.to_thread(_convert, body)
    except h3_direct.DirectError as e:
        return fail(f"提示词转换失败：{e}")
    except Exception as e:                             # noqa: BLE001
        log.exception("提示词转换异常")
        return fail(f"提示词转换异常：{type(e).__name__}: {e}")

    if data["red"]:
        return ok(data, biz_code=2,
                  msg=f"已返回，但仍有一条判据没过：{data['red'][0]}")
    return ok(data)


# ---------------------------------------------------------------- 修订（出了片，改几处）
#
# 🩸 2026-10-30 主人：「产出的视频效果不理想，切图回来反馈让他修改部分提示词。
# 你现在这样的输入和操作方式我感觉很落后」。
# 这一条就是那个闭环：**现有提示词 + 截图 + 一句话反馈 → 只改那几处**。
# 模型能读图（方舟多模态），所以图直接进 content，不落盘、不留存。

#: 一次最多几张截图。切图反馈一般 1–3 张，多了模型也抓不住重点。
MAX_SHOTS = 4
#: 单张截图的 data URI 上限（约 2MB 原图）。前端会按 compressed 传。
MAX_IMAGE_CHARS = 3_000_000


class ReviseIn(BaseModel):
    prompt: str = Field(..., description="已经能用的那份 H3 提示词")
    feedback: str = Field("", description="哪儿不对，一句话说清（第几镜、什么现象）")
    images: list[str] = Field(default_factory=list,
                              description="出问题画面的截图，data URI（data:image/jpeg;base64,…）")
    duration: float = Field(5.0, description="目标片长，官方 4–15 秒")
    model: str = Field("", description="理解模型：lite / pro / deepseek，留空 = pro")


def _revise(body: ReviseIn) -> dict:
    prompt = (body.prompt or "").strip()
    fb = (body.feedback or "").strip()
    imgs = [str(x).strip() for x in (body.images or []) if str(x).strip()]
    if not prompt:
        raise h3_direct.DirectError("要修订的提示词是空的")
    if not fb and not imgs:
        raise h3_direct.DirectError("请说明哪里不对，或者传一张出了问题的截图")
    if len(imgs) > MAX_SHOTS:
        raise h3_direct.DirectError(f"截图最多 {MAX_SHOTS} 张，一次改太多模型抓不住重点")
    for u in imgs:
        # 只收 data URI：不收外链（防 SSRF，也别让顾客的图经过第三方）
        if not u.startswith("data:image/"):
            raise h3_direct.DirectError("截图必须是图片数据（data:image/…）")
        if len(u) > MAX_IMAGE_CHARS:
            raise h3_direct.DirectError("单张截图太大，请压缩后再传（前端选『压缩图』）")

    kind = guess_kind(prompt)
    lo, hi = conv_route.VARIANTS["MiniMax-H3"]
    dur = float(body.duration)
    note = ""
    if dur < lo or dur > hi:
        fixed = float(max(lo, min(hi, dur)))
        note = f"片长 {dur:g} 秒超出范围（{lo}–{hi}），已按 {fixed:g} 秒修订"
        dur = fixed

    key = body.model or ark_chat.DEFAULT_MODEL
    got = h3_direct.revise(prompt, fb, images=imgs, kind=kind, duration=dur,
                           model=key, judge=lambda p: _judge_rows(p, kind, ""))

    out = got["prompt"]
    yellow = ([x[0] for x in h3_ref.check(
        out, h3_ref.ctx_for(out, edit_master=None, audio=None)) if x[1] == "黄"]
        if kind == "ref"
        else [x[0] for x in rules.check(out, {"mode": _mode_of(out)}) if x[1] == "黄"])
    return {
        "prompt": out,
        "kind": kind,
        "format": conv_route.GUIDES[kind]["name"],
        "ruler": conv_route.GUIDES[kind]["ruler"],
        "chars": len(out),
        "duration": dur,
        "warnings": ([note] if note else []),
        "tries": got["tries"],
        "rules": len(h3_ref.RULES) if kind == "ref" else len(rules.RULES),
        "red": [f"{x[0]} {x[1]}：{x[3]}" for x in (got.get("red") or [])],
        "yellow": yellow,
        "model": ark_chat.resolve(key),
    }


def _mode_of(prompt: str) -> str:
    """三字段下是哪种子模式（决定 B 系判据跑哪几条）。看得出就判，看不出按 t2va。"""
    p = prompt or ""
    if "<Picture 1>" in p and "<Picture 2>" in p:
        return "fl2va"
    if "<Picture 1>" in p:
        return "i2va"
    return "t2va"


# ---------------------------------------------------------------- 多轮（先问后写）
#
# 🩸 2026-10-30 主人：「不可能一上来就说提示词，可以是需要短暂交流然后得到自己
# 想要的东西，然后才开始模型调 skill 去产出提示词。」
# 「说想法」这条路从「一问一答出稿」改成「聊一两轮再出稿」。
# 粘现成稿 / 传截图改稿两条不接历史，各走各的。

#: 历史最多带多少条。聊到十几轮还在聊，多半是跑偏了，再往前带也没用。
MAX_HISTORY = 20


class ChatIn(BaseModel):
    messages: list[dict] = Field(
        default_factory=list,
        description="完整对话历史 [{role: 'user'|'assistant', content}]，前端持有")
    duration: float = Field(
        0.0, description="目标片长，官方 4–15 秒；**0 = 还没定，由模型在对话里问**")
    model: str = Field("", description="理解模型：lite / pro / deepseek，留空 = pro")
    target: str = Field(
        "", description="写给哪家模型：h3 / sd20。**没有默认，必须顾客自己选** —— "
                        "两家平级，不排强弱（2026-10-30 主人定）")
    assets: list[ConvertAssetIn] = Field(
        default_factory=list, description="顾客声明的参考素材；一样不传 = 文生视频")
    images: list[str] = Field(
        default_factory=list,
        description="本轮截图（data URI）。sd20 走对话就能带图；"
                    "h3 的传图走 /prompt/revise")


#: 2.0 的素材用途说明。与 H3 那份各写各的：H3 是 `<Picture 1>`，2.0 是 `@图片1`，
#: 首帧/尾帧在两家也是不同的任务形态。
ROLE_DESC_SD20 = {
    "first_frame": "作为片子的第一帧（2.0 图生视频-首帧）",
    "last_frame": "作为片子的最后一帧（2.0 图生视频-尾帧）",
    "reference_image": "当参考图，锁定人/风格/场景",
    "reference_video": "参考它的动作/运镜/节奏",
    "reference_audio": "参考它的音色/配乐/音效",
}

#: 2.0 单段时长 —— 工程口径 **4–15 秒**（2026-10-30 主人拍板取 4 作下限）。
SD20_LO, SD20_HI = 4.0, 15.0

#: 一轮对话最多带几张附件图（多模态输入上限，不是 2.0 的素材上限）。
IMAGE_CAP = 4


def _chat_turn_sd20(body: ChatIn, msgs: list[dict]) -> dict:
    """Seedance 2.0 那一支。与 H3 分支平级并列，素材规则/判据/时长各按各家。"""
    dur = float(body.duration or 0)          # 0 = 还没定，交给模型在对话里问
    note = ""
    if dur:
        if dur < SD20_LO or dur > SD20_HI:
            dur = float(max(SD20_LO, min(SD20_HI, dur)))
            note = f"片长超出范围（{SD20_LO:g}–{SD20_HI:g} 秒），已按 {dur:g} 秒处理"

    # 🩸 编号顺序 = **顾客上传的顺序**（2026-10-30 主人：「一般都会按照原来上传的
    # 顺序来执行操作」）。所以本轮传的附件图先占 @图片1..@图片N，
    # 素材面板里声明的图片素材接着往下编 —— 两套不会撞号。
    imgs = [u for u in (body.images or []) if u][:IMAGE_CAP]

    # 2.0 的标签自己按类型顺序编（`@图片1` / `@视频1` / `@音频1`），
    # 不信前端传的 H3 标签 —— 两家语法不同，照搬会写出模型认不出的编号。
    seen = {"image": len(imgs), "video": 0, "audio": 0}
    pairs = []
    for a in body.assets:
        if a.kind not in seen:
            raise sd20_direct.DirectError(f"素材类型只认 image/video/audio，收到 {a.kind!r}")
        seen[a.kind] += 1
        pairs.append({
            "label": {"image": "@图片", "video": "@视频", "audio": "@音频"}[a.kind]
                     + str(seen[a.kind]),
            "role": a.role,
            "role_desc": ROLE_DESC_SD20.get(a.role, ""),
            "note": a.note,
        })
    # 官方上限（`volc-api:35`）：2.0 = 图 0-9 + 视频 0-3 + 音频 0-3。
    # 超了就不写 —— 写出 `@图片12` 这种编号，2.0 那边根本收不到。
    over = [f"{k} {seen[k]} 样" for k, cap in
            (("image", 9), ("video", 3), ("audio", 3)) if seen[k] > cap]
    if over:
        raise sd20_direct.DirectError(
            f"素材超过 2.0 官方上限（图 9 / 视频 3 / 音频 3）：{'、'.join(over)}")

    key = body.model or ark_chat.DEFAULT_MODEL
    got = sd20_direct.chat_turn(
        msgs, duration=dur, assets=pairs, model=key, images=imgs,
        judge=lambda p: [(r[0], r[2], r[3], "；".join(r[4]))
                         for r in volc20_pe.check(p) if r[1] == "红"])

    out = {
        "target": "sd20",
        "action": got["action"],
        "format": "2.0 中文提示词",
        "tries": got["tries"],
        "asked": got.get("asked", 0),
        "warnings": ([note] if note else []),
        "model": ark_chat.resolve(key),
    }
    if got["action"] == "ask":
        out["question"] = got["question"]
        return out

    prompt = got["prompt"]
    rows = volc20_pe.check(prompt)
    out.update({
        "prompt": prompt,
        # 官方 Step 4 的「优化问题」—— 给顾客看的披露，**不属于提示词正文**
        "note": got.get("note") or "",
        "chars": len(prompt),
        "duration": dur,
        "rules": len(volc20_pe.RULES),
        "red": [f"{x[0]} {x[1]}：{x[3]}" for x in (got.get("red") or [])],
        "yellow": [x[0] for x in rows if x[1] == "黄"],
    })
    return out


def _chat_turn(body: ChatIn) -> dict:
    msgs = [m for m in (body.messages or []) if isinstance(m, dict)]
    if not msgs:
        raise h3_direct.DirectError("没有收到任何对话内容")
    msgs = msgs[-MAX_HISTORY:]

    # 🩸 两家平级，没有默认（2026-10-30 主人：「所有模型没有默认和更强」）。
    target = (body.target or "").strip().lower()
    if target == "sd20":
        return _chat_turn_sd20(body, msgs)
    if target != "h3":
        raise h3_direct.DirectError("还没选写给哪个模型 —— 先选 H3 或 Seedance 2.0 再发")

    try:
        assets = [conv_route.Asset(a.kind, a.role, a.seconds) for a in body.assets]
    except ValueError as e:
        raise h3_direct.DirectError(str(e)) from e

    r = conv_route.route(assets, model="MiniMax-H3")
    if r["problems"]:
        # 素材组合本身不合官方规矩，删哪张是顾客的决定，不替他改
        raise h3_direct.DirectError("；".join(r["problems"]))
    guide = r["guide"] or "base"
    mode = r["mode"] or "t2va"

    # duration = 0 → 还没定，交给模型在对话里问（模型知道官方单段 4–15 秒）
    lo, hi = r["duration"]
    dur = float(body.duration or 0)
    note = ""
    if dur:
        if dur < lo or dur > hi:
            dur = float(max(lo, min(hi, dur)))
            note = f"片长超出范围（{lo}–{hi}），已按 {dur:g} 秒处理"

    _norm, _ = conv_route.normalize(assets)
    pairs = [{"label": b.label, "note": b.note,
              "role_desc": ROLE_DESC.get(n.role, "")}
             for b, n in zip(body.assets, _norm)]

    key = body.model or ark_chat.DEFAULT_MODEL

    # 🩸 2026-10-30 主人拍板 A：H3 这一支改成 **agent 自己读 skill 包**。
    # 不再由我们判 base/ref 拼 system —— 读哪份、走哪条路，模型读完 SKILL.md 自己定。
    # `conv_route` 留着只做一件事：**素材组合合不合官方规矩**（不合格要让人删图）。
    fixed = [_fixed_duration(dur, lo, hi)]
    if pairs:
        fixed.append("顾客声明的参考素材（标签就用这套）：\n" + "\n".join(
            f"{a['label']} —— {a.get('role_desc') or a.get('note') or '用途未说明'}"
            for a in pairs))
    else:
        fixed.append("顾客没有声明参考素材。如果这一轮他传了图，那些图就是素材，"
                     "按上传顺序是 <Picture 1>/<Picture 2> …")
    if body.images:
        fixed.append(f"顾客这一轮传了 {len(body.images)} 张图（挂在这条消息上）。")

    try:
        got = h3_skill.run(msgs, model=key, fixed=fixed)
    except skill_agent.AgentError as e:
        raise h3_direct.DirectError(str(e)) from e

    out = {
        "target": "h3",
        "action": got.action,
        "kind": guess_kind(got.prompt) if got.prompt else "",
        "format": "官方 skill 直出",
        "ruler": "官方尺子（交付前自动过一遍）",
        "tries": got.steps,
        "asked": sum(1 for m in msgs if (m or {}).get("role") == "assistant"),
        "warnings": ([note] if note else []) + ([got.truncated] if got.truncated else []),
        "model": ark_chat.resolve(key),
        # 前端进度：每一步读了什么、问了什么。100 秒的等待没这个就是卡死。
        "trace": got.trace,
        "reads": got.reads,
        "calls": got.calls,
        "tokens": got.tokens,
    }
    if got.action == "ask":
        out["question"] = got.question
        return out

    prompt = got.prompt
    kind = guess_kind(prompt)
    yellow = ([x[0] for x in h3_ref.check(
        prompt, h3_ref.ctx_for(prompt, edit_master=None, audio=None)) if x[1] == "黄"]
        if kind == "ref"
        else [x[0] for x in rules.check(prompt, {"mode": _mode_of(prompt)})
              if x[1] == "黄"])
    out.update({
        "prompt": prompt,
        "note": got.note,
        "chars": len(prompt),
        "duration": dur,
        "rules": len(h3_ref.RULES) if kind == "ref" else len(rules.RULES),
        "red": [f"{x[0]} {x[1]}：{x[3]}" for x in got.red],
        "yellow": yellow,
    })
    return out


def _fixed_duration(dur: float, lo: float, hi: float) -> str:
    """片长写进固定条件。0 = 还没定，让模型该问的时候自己问。"""
    if dur:
        return f"目标片长：{dur:g} 秒（H3 单段 {lo:g}–{hi:g} 秒）"
    return (f"片长还没定 —— 该问的时候问顾客，选项给：4 / 5 / 6 / 8 / 10 / 15 秒。"
            f"官方单段最长 {hi:g} 秒。顾客要更长的，只说明「这一段最长 {hi:g} 秒」，"
            f"不要提分段、拼接、续写之类的做法 —— 那不是 H3 的能力。")


@router.post("/prompt/chat")
async def chat_turn(body: ChatIn):
    if body.model and body.model not in ark_chat.MODELS:
        return fail(f"模型只认 {tuple(ark_chat.MODELS)}")
    if not (settings.ark_api_key or "").strip():
        return fail("方舟未配置：请设置 VT_ARK_API_KEY")

    try:
        data = await asyncio.to_thread(_chat_turn, body)
    except (h3_direct.DirectError, sd20_direct.DirectError) as e:
        return fail(f"提示词对话失败：{e}")
    except Exception as e:                             # noqa: BLE001
        log.exception("提示词对话异常")
        return fail(f"提示词对话异常：{type(e).__name__}: {e}")

    if data.get("red"):
        return ok(data, biz_code=2,
                  msg=f"已写好，但仍有一条判据没过：{data['red'][0]}")
    return ok(data)


@router.post("/prompt/revise")
async def revise(body: ReviseIn):
    if body.model and body.model not in ark_chat.MODELS:
        return fail(f"模型只认 {tuple(ark_chat.MODELS)}")
    if not (settings.ark_api_key or "").strip():
        return fail("方舟未配置：请设置 VT_ARK_API_KEY")

    try:
        data = await asyncio.to_thread(_revise, body)
    except h3_direct.DirectError as e:
        return fail(f"修订失败：{e}")
    except Exception as e:                             # noqa: BLE001
        log.exception("提示词修订异常")
        return fail(f"提示词修订异常：{type(e).__name__}: {e}")

    if data["red"]:
        return ok(data, biz_code=2,
                  msg=f"已改好，但仍有一条判据没过：{data['red'][0]}")
    return ok(data)

