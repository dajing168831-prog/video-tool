"""商品短剧 API —— 商品 + 三问 → 结构卡 → 剧本 → 分镜 → 自检。

独立子项目：规则来自 `D:/skills/product-drama/references/`（由该工程 SOURCE.md 渲染），
这里只做编排与调用，**不复制、不改写那边的规则**。

LLM：DeepSeek 官方（`settings.deepseek_api_key` / `settings.deepseek_model`），
和 `clone_agent` 同一条通道；不回落方舟。
"""
from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import random
import re
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

from app.api.routes import fail, ok
from app.core.config import settings
from app.services import (
    ark, deepseek_chat, drama_audio, drama_camera, drama_captions, drama_cards,
    drama_category_templates, drama_compose, drama_contact_sheet, drama_cover,
    drama_credits, drama_dub, drama_film, drama_format, drama_import, drama_materials,
    drama_files, drama_fingerprint, drama_settings, drama_styles, drama_trends,
    drama_batch, drama_metrics, drama_probe, drama_tasks, drama_works,
    drama_media_lab,
    drama_preflight, drama_stock, drama_stock_fill, drama_timeline, drama_topic, drama_tts, drama_variants,
    drama_clips, drama_gif, drama_grid, drama_judge, drama_looks, drama_mastering,
    drama_media_import, drama_media_transcript, drama_modes, drama_voice, drama_pipeline,
    drama_native_feel, drama_platform, drama_product_ingest, drama_product_lib, drama_publish, drama_qr,
    drama_script_templates, drama_template_store, drama_templates,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/drama", tags=["drama"])

DATA = Path(__file__).resolve().parents[2] / "data" / "drama"
#: G4/G5 发布成效落这一份（跨项目聚合都读它）
METRICS_FILE = DATA / "metrics.json"
REFS = Path(os.getenv("PD_REFS", "D:/skills/product-drama/references"))

STAGES = ("card", "script", "storyboard", "check")

BASE_SYS = """你是短剧编剧。你只写故事，不做洞察、不写模型提示词、不做成片。

铁律（违反任何一条都算失败）：
- 不编产品事实：产品资料里没有的卖点、参数、认证，一律不写、不推测。
- 卖点只通过冲突、欲望、破功体现，任何角色都不许念参数。
- 开场 3 秒必须是拍得出来的具体画面动作冲突，不能是气氛或旁白。
- 商品必须承担转折作用；撤掉商品这场戏还能成立，就重写。
- 台词口语短句，像真人拌嘴；禁止书面腔、旁白腔、口号腔。
- 只输出要求的正文，不要解释、不要 markdown 代码块围栏。

以下是结构规则与硬约束：

{rules}
"""


# ---------- 输入模型 ----------
#: 对标 clipforge 的固定选项（`src/lib/i18n/messages/newProject.ts`）。
#: 后端只存字符串、不校验枚举 —— 选项清单由前端渲染，后端硬校验只会两边打架。
CATEGORIES = ("美妆护肤", "食品零食", "家居日用", "服饰鞋包", "数码3C", "其他")
PRICES = ("50元以下", "50-200元", "200-500元", "500元以上")
AUDIENCES = ("学生党", "上班族", "宝妈", "精致白领", "中年群体", "男性用户",
             "健身人群", "数码爱好者")
PLATFORMS = ("抖音", "快手", "小红书", "TikTok Shop")
#: 视频模式 = **镜头怎么拍**（不是发布渠道）。指令正文在 `services/drama_modes.py`，
#: 剧本 / 分镜 / 九宫格三处共用同一份（别在这里复制一遍）。
MODES = drama_modes.MODES
#: 商品图上限 —— 对标「最多 5 张」
MAX_PRODUCT_PICS = 5


class ProductIn(BaseModel):
    name: str = Field(..., min_length=1)
    points: list[str] = Field(default_factory=list)
    facts: str = ""
    audience: str = ""
    category: str = ""
    price: str = ""
    platform: str = ""
    #: 顾客粘的商品链接（2026-11-08）。抓不到内容也留着 —— 发布文案的 UTM 链接
    #: 和结尾二维码都要靠它（竞品同样存 `shopUrl`，见 ingest/product/route.ts）。
    url: str = ""
    #: 已上传商品图的文件名（上限 `MAX_PRODUCT_PICS`）
    images: list[str] = Field(default_factory=list)


class AnswersIn(BaseModel):
    #: 做片路线：`A` 快速出片 / `B` 创意故事（先挑故事世界）。
    #: 🩸 2026-11-08：这一格原来**缺了** —— 小程序选「创意故事」传上来，Pydantic
    #: 直接丢掉，项目里根本没有这条记录（实测某项目 `answers` 有 world 没有 line），
    #: 重开项目就退回 A 线，后端也无从知道这是创意故事。
    line: str = ""
    form: str = ""          # 空 = 让模型自选形态（不再默认情景短剧）
    #: 自定义形态的自由要求（形态选「自定义」时用；竞品 `customRequirements`）
    form_note: str = ""
    duration: int = 30
    role: str = "转折道具"
    mode: str = ""
    # 出镜人物：空 = 让模型从内置素人库里挑或自创；填名字 = 固定用这一位
    presenter: str = ""
    #: 批量作业的反同质化轮换：指定开场策略（H1–H5），空 = 让模型自选
    #: （竞品 `batch/page.tsx:346` 的 `preferredHookId`）
    preferred_hook: str = ""
    #: 故事世界（2026-11-07 新增）：空 = 不走这一步，老流程原样
    #: 路线：`煽情` / `荒诞`；世界必须是顾客从候选中挑的那一个
    route: str = ""
    world: str = ""
    world_from: str = ""
    #: L1 品类拟人 / L2 关系裂变 / L3 错位投放（见 `docs/ABSURD-WORLD.md`）
    world_law: str = ""


class NewProjectIn(BaseModel):
    product: ProductIn
    answers: AnswersIn


# ---------- 规则读取 ----------
def _ref(name: str) -> str:
    p = REFS / name
    if not p.exists():
        return ""
    t = p.read_text(encoding="utf-8")
    if t.startswith("> 生成物"):
        t = t.split("\n\n", 1)[-1]
    return t.strip()


#: 形态 → 规则文件。十种形态各自一份（`D:/skills/product-drama/references/form_*.md`），
#: 由 SOURCE.md 的 `<!--SECTION:FORM_*-->` 节渲染。空/未知一律回落到情景短剧。
FORM_FILES = {
    "情景短剧": "form_drama.md",
    "反转剧场": "form_reversal.md",
    "街头采访": "form_interview.md",
    "达人口播": "form_talking_head.md",
    "开箱测评": "form_unboxing.md",
    "对比测评": "form_comparison.md",
    "剧情故事": "form_story.md",
    "痛点种草": "form_pain_point.md",
    "场景安利": "form_scene.md",
    "物品拟人": "form_product_pov.md",
}
FORMS = tuple(FORM_FILES)


def _creative_line(doc: dict) -> bool:
    """这条片是不是「创意故事」那条线（B 线）。

    🩸 2026-11-08：主人选「创意故事」后仍被十形态模板框住。根因是 B 线当初
    只做了「把故事世界带进提示词」，形态规则照旧注入（`docs/ABSURD-WORLD.md`
    第一行就写着「不改十种形态、五拍骨架」）——那条线只走了一半。
    现在 B 线直接走「自定义形态」通道：不注入 form_*.md、不要求五拍和钩子编号。

    旧项目推断：`line` 这一格是 2026-11-08 才补的，之前建的项目没有它；
    `world` 只有 B 线会产生 → 有 `world` 没 `line` 一律按 B 线算。
    """
    a = doc.get("answers") or {}
    line = str(a.get("line") or "").strip().upper()
    if line == "B":
        return True
    if not line and str(a.get("world") or "").strip():
        return True
    return False


def _form_of(doc: dict) -> str:
    """项目用的形态。

    🩸 2026-11-07 实测：默认写死「情景短剧」→ 每条片都是同一个骨架
    （同事嘲笑穿着 → 掏产品打脸），换措辞不换故事。现在的先后顺序：
      · 创意故事（`_creative_line`）→ **「自定义」**，优先级最高：
        顾客选的是"世界决定故事"，十形态的拍子一条都不该套上来；
      · 白名单里的形态 → 原样；
      · `form_note` 有内容 → 「自定义」（按顾客自己的要求写，照竞品 `styleType="custom"`，
        出处 `script-engine/prompts.ts:750-752`）；
      · 都为空 → 返回空串 = **让模型自选**，并明确要求不要默认情景短剧。
    """
    if _creative_line(doc):
        return "自定义"
    a = doc.get("answers") or {}
    form = str(a.get("form") or "").strip()
    if form in FORM_FILES:
        return form
    if str(a.get("form_note") or "").strip():
        return "自定义"
    return ""


def _rules(form: str = "") -> str:
    name = FORM_FILES.get(form) or ""
    return "\n\n---\n\n".join(
        x for x in ((_ref(name) if name else ""), _ref("rules.md")) if x)


def _system(form: str = "") -> str:
    r = _rules(form)
    if not r:
        raise DramaError(f"读不到规则文件：{REFS}（检查 product-drama 工程是否存在）")
    return BASE_SYS.format(rules=r)


# ---------- 调用 ----------
class DramaError(ValueError):
    pass


def _chat(user: str, *, temperature: float = 0.8, system: str | None = None,
          form: str = "") -> str:
    key = (settings.deepseek_api_key or "").strip()
    if not key:
        raise DramaError("没有配置 VT_DEEPSEEK_API_KEY，无法生成")
    body = {
        "model": settings.deepseek_model,
        "messages": [
            {"role": "system", "content": system or _system(form)},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "stream": False,
    }
    try:
        data = deepseek_chat.post(body, key=key)
    except deepseek_chat.DeepSeekError as e:
        raise DramaError(str(e)) from e
    try:
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        raise DramaError(f"模型返回格式不对：{str(data)[:200]}") from e


# ---------- 存储 ----------
def _dir() -> Path:
    DATA.mkdir(parents=True, exist_ok=True)
    return DATA


#: H3 项目号格式（竞品 `api/upload/route.ts:41-44` 对 `projectId` 的同一条正则意图）。
#: 项目号由我们自己生成（`uuid4().hex[:12]`），只可能是字母数字；带 `/`、`..`、
#: 扩展名的一律当「不存在」，别让它拼进路径。
_PID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def _path(pid: str) -> Path:
    if not _PID_RE.match(pid or ""):
        raise KeyError(pid)
    return _dir() / f"{pid}.json"


def _save(doc: dict) -> None:
    doc["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _path(doc["id"]).write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def _load(pid: str) -> dict:
    p = _path(pid)
    if not p.exists():
        raise KeyError(pid)
    return json.loads(p.read_text(encoding="utf-8"))


def _stage(d: dict) -> str:
    for k, name in (("check", "已自检"), ("storyboard", "分镜"), ("script", "剧本"), ("card", "结构卡")):
        if d.get(k):
            return name
    return "新建"


# ---------- 提示词 ----------
def _brief(doc: dict) -> str:
    p, a = doc["product"], doc["answers"]
    pts = "\n".join(f"- {x}" for x in p.get("points") or []) or "（未给卖点）"
    # 对标 clipforge 的「更多商品信息」：都填了才写进去，没填就不占篇幅
    extra = "｜".join(
        f"{k}：{p.get(key)}" for k, key in
        (("品类", "category"), ("价格带", "price"), ("投放平台", "platform"))
        if (p.get(key) or "").strip()
    )
    return (
        f"【商品】{p.get('name','')}\n"
        f"【卖点】\n{pts}\n"
        f"【原始资料】\n{(p.get('facts') or '').strip() or '（无）'}\n"
        f"【目标人群】{(p.get('audience') or '').strip() or '（未给）'}\n"
        + (f"【其它】{extra}\n" if extra else "")
        # 空形态别写成「形态：」留个空格——模型会当成没填就回去照抄示例
        + f"\n形态：{_form_of(doc) or '未指定（你按商品自己挑）'}"
        + f"｜片长：{a.get('duration')}s｜商品角色：{a.get('role')}"
        # 视频模式不是一句话标签，是一整套「怎么拍」的硬要求（见 drama_modes）
        + (f"\n\n{drama_modes.rule(a.get('mode'))}"
           if drama_modes.rule(a.get("mode")) else "")
    )


def _gen_json(doc: dict, stage: str, user: str, validate) -> tuple[str, dict]:
    """要求模型输出 JSON，解析 + 校验；失败**带着失败原因**重来一次。

    🩸 2026-11-05 端到端联调抓到的：以前重试只是把温度调低**重掷一次**，
    模型看不到自己错在哪（实测分镜连着两版都栽在同一条 C8 上）。
    现在把上一版的具体不合格项回灌进提示词，让它按条目改。
    """
    last = ""
    for attempt, temp in enumerate((0.7, 0.2), 1):
        ask = user
        if last:
            ask = (
                f"{user}\n\n【上一版为什么不能用】\n{last}\n"
                "逐条改对，然后**完整**重新输出一遍 JSON（不要只给改动部分）。"
            )
        text = _chat(ask, temperature=temp, form=_form_of(doc))
        try:
            obj = drama_format.parse_json(text)
        except drama_format.FormatError as e:
            last = str(e)
            log.warning("[drama] %s 第%d次解析失败: %s", stage, attempt, last)
            continue
        errs = validate(obj)
        if errs:
            last = "产出不合格：" + "；".join(errs[:6])
            log.warning("[drama] %s 第%d次校验失败: %s", stage, attempt, last)
            continue
        # 自定义形态走**另一套**结构卡（老十种形态的字一个字不动）
        custom = stage == "card" and _form_of(doc) == "自定义"
        render = {
            "card": drama_format.render_card_custom if custom else drama_format.render_card,
            "script": drama_format.render_script,
            "storyboard": drama_format.render_storyboard,
        }[stage]
        return render(obj), obj
    raise DramaError(last or "模型没给出可用产出")


def _template_block(doc: dict) -> str:
    """项目选中的成片模板 → 给模型的创作方向块（竞品 `adTemplateScriptDirective`）。"""
    tpl = ((doc.get("template") or {}).get("template")) or {}
    return drama_templates.script_directive(tpl) if tpl else ""


def _performance_hint(doc: dict) -> str:
    """G4/G5 数据飞轮的读取端：把历史发布成效写成一段生成指令。

    竞品 `llm/script/route.ts:93-124`：同品类优先，样本不够回落全局；
    **读失败只跳过提示，不阻断生成**（冷启动时这里恒为 `""`）。
    """
    try:
        rows = drama_metrics.load(METRICS_FILE)
        if not rows:
            return ""
        return drama_metrics.hint_for_category(
            rows, (doc.get("product") or {}).get("category"))
    except Exception as e:  # noqa: BLE001
        log.warning("[drama] 读取历史转化数据失败（已跳过反馈）: %s", e)
        return ""


#: 开头策略五选一（`D:/skills/product-drama/references/hook.md:7-13` 原表）
#: 批量作业用它把同一批商品的开场轮换开（竞品 `script-engine/hook-patterns.ts:231-252`）。
_HOOK_CARDS = {
    "H1": ("画面冲击", "第一帧有肉眼可辨的对比或动态（质地、爆开、脏→净、前后差）"),
    "H2": ("反常识提问", "抛出一个观众想亲自验证的问题"),
    "H3": ("反差错位", "价格 / 效果 / 身份三者之一发生错位"),
    "H4": ("明确利益", "直接说看完能得到什么（省钱 / 变好 / 避坑）"),
    "H5": ("情绪戳点", "戳中焦虑、快乐或后悔之一"),
}


def _hook_block(doc: dict) -> str:
    """批量轮换指定的开场策略（空 = 不加这段，提示词与以前逐字一致）。"""
    code = str((doc.get("answers") or {}).get("preferred_hook") or "").strip().upper()
    got = _HOOK_CARDS.get(code)
    if not got:
        return ""
    name, condition = got
    return (
        "【本次开场策略（反同质化轮换指定）】\n"
        f"开头【必须】用 {code}「{name}」这一条：{condition}。\n"
        "不要换成其它策略；第一帧就要成立，不许用气氛、旁白、logo 开场。"
    )


def _form_block(doc: dict) -> str:
    """形态要求：结构卡和剧本**两个阶段都必须带**。

    🩸 2026-11-07 实测三组（空形态×2 + 自定义）：三张结构卡全是「形态：情景短剧」，
    五拍全是「冲突爆发/矛盾升级/商品登场/反转爽感/收束」，自定义要求里的
    「从啤酒自己视角讲」一个字没体现。根因是两个：
      ① 这段以前只加在剧本阶段 —— 结构卡才是定骨架的地方，卡定了剧本改不动；
      ② 结构卡规格 `output_card.md` 的 JSON 示例把 form 和五拍名字写成了固定值
         → 模型照抄示例（已同步改规格：name 按形态自己起）。
    """
    form = _form_of(doc)
    note = str((doc.get("answers") or {}).get("form_note") or "").strip()
    if form == "自定义" and note:
        return (
            "【本次形态：自定义（按顾客要求来，不要套固定套路）】\n"
            f"{note}\n"
            "这段话优先级最高：拍数、有没有对手、视角、节奏都按它来，"
            "跟下面的片长 / 商品角色冲突时也按它。\n"
            "结构卡里的 form 写「自定义」，拍子自己起名，"
            "**不许套用十种固定形态的骨架**。"
        )
    if form == "自定义":
        # 创意故事（B 线）：顾客没写形态要求，故事方向由**故事世界**给。
        # 以前这里会掉到下面的白名单分支，生成「按系统提示里『自定义』这一份的
        # 五拍结构来」——那份形态表根本不存在，等于让模型自由发挥又不敢说。
        return (
            "【本次形态：创意故事（不套任何十形态模板）】\n"
            "故事方向只看【本次故事世界】：场景、人物身份、说话方式都从世界长出来。"
            "拍数自己定（**至少 3 拍**），每拍拍名自己起，不要求正好 5 拍；\n"
            "**不许套用**情景短剧/反转剧场等任何一份形态骨架，不要写「双方冲突 / "
            "占上风 / 落败」这类对峙设定，也不要求 H1–H5 开头策略编号。\n"
            "结构卡里的 form 写「自定义」。"
        )
    if not form:
        return (
            "【本次形态：自选】\n"
            "从情景短剧 / 反转剧场 / 街头采访 / 达人口播 / 开箱测评 / 对比测评 / "
            "剧情故事 / 痛点种草 / 场景安利 / 物品拟人 里挑最贴合这个商品的，"
            "**不要默认用情景短剧**。\n"
            "结构卡里的 form 写你挑的那个名字；五拍按该形态自己起名，"
            "**不许套用示例里的「冲突爆发/矛盾升级/商品登场/反转爽感/收束」**。"
        )
    # 🩸 2026-11-08：选了白名单形态时这段原来**返回空串**，于是结构卡只剩
    # `output_card.md` 里那张写死「双方冲突 + 五个固定拍名」的示例可以照抄 ——
    # 不管顾客选反转剧场 / 痛点种草 / 物品拟人，出来的都是同一副两人对峙骨架
    # （主人实测：「趣味性一点也没变，还是双人在对峙」）。系统提示里本来就有该形态的
    # 五拍结构表（`form_*.md`），这里要把「按它来」说出口。
    return (
        f"【本次形态：{form}】\n"
        f"结构卡和剧本都按系统提示里「{form}」这一份的五拍结构来："
        "`beats` 的 `name` 用该形态自己的拍名，不是示例里那五个；"
        "`conflict` 写这条片的对立面——**不一定是两个人**"
        "（例：反转剧场 = 观众预期 ↔ 商品打脸的事实；痛点种草 = 老办法 ↔ 商品），"
        "`character_count` 按该形态定（达人口播/开箱测评可以 1 人，物品拟人可以 0 人）。\n"
        "禁止把这条片写成情景短剧那种「两个人抢一样东西」的对峙，"
        "除非形态本身就是情景短剧或剧情故事。"
    )


def _world_block(doc: dict) -> str:
    """顾客从候选里挑中的「故事世界」（2026-11-07 新增）。

    只在顾客**真的挑过**之后才注入（`answers.world` 非空）；空 = 老流程一个字不改。
    出处：`docs/ABSURD-WORLD.md`（33 条实测样本 + 泰国广告公开研究）。
    """
    a = doc.get("answers") or {}
    world = str(a.get("world") or "").strip()
    if not world:
        return ""
    law = str(a.get("world_law") or "").strip()
    route = str(a.get("route") or "").strip()
    src = str(a.get("world_from") or "").strip()
    out = (f"【路线：{route}】\n" if route else "") + f"【本次故事世界（顾客已选定）】\n{world}\n\n"
    out += (
        "这个世界优先级最高：**整条片都必须发生在这个世界里**——场景、人物身份、"
        "说话方式、道具都按它来。不许退回日常现实场景，也不许把商品拎出来单独介绍。"
    )
    if src:
        out += f"\n世界来路：{src}（{law or '未标注法则'}）——这是它成立的原因，不是装饰，写戏时要守住这个点。"
    return out


def _script_lines(doc: dict) -> list[str]:
    """剧本里逐条台词（分镜覆盖率校验用）。

    导入稿（`/import-script`）没有 `lines` → 返回空数组 = 不查覆盖，
    否则每条导入稿都会被判「台词全丢」。
    """
    out: list[str] = []
    for sc in ((doc.get("script_json") or {}).get("scenes") or []):
        if not isinstance(sc, dict):
            continue
        for ln in (sc.get("lines") or []):
            if isinstance(ln, dict):
                t = str(ln.get("text") or "").strip()
                if t:
                    out.append(t)
    return out


def _dialogue_budget(doc: dict, want: float, max_sec: float) -> str:
    """把「这部片能装多少台词」算成数字写进提示词（2026-11-08）。

    🩸 实测：不写这段，模型第 1 版排出 34 秒（超 1.5 倍被拒），第 2 版收住时长却
    丢了 1 句（覆盖率被拒），两次都不合格 → 什么都没存，界面上看着像「点了没反应」。
    预算写在提示词里，它一次就能排对，不用靠两次失败去试。
    """
    lines = _script_lines(doc)
    if not lines or not want:
        return ""
    speech = sum(drama_format.speech_seconds(x) for x in lines)
    lo, hi = want * 0.8, want * 1.5
    max_shots = max(1, int(hi // 4))
    need_two = max(0, len(lines) - max_shots)
    out = (
        f"【台词预算（算好的，照着排）】\n"
        f"剧本 {len(lines)} 句，合计约 {speech:.1f} 秒（中文 4.2 字/秒）。\n"
        f"目标片长 {want:g} 秒：分镜合计必须落在 {lo:g}–{hi:g} 秒之间，"
        f"单镜 4–{max_sec:g} 秒。\n"
    )
    if need_two > 0:
        out += (
            f"{speech:.1f} 秒的台词要放进 {hi:g} 秒以内 → 至少 {need_two} 个镜头得写两句"
            f"（格式「A：…；B：…」，这种镜 ≥5 秒），或者把台词拆到更多镜头上，"
            f"但**不许删、不许改写**。\n"
        )
    if speech > hi:
        out += (
            f"⚠ 台词本身就超过 {hi:g} 秒了：这份剧本按这个片长排不进去，"
            f"先把台词写短或把片长调大，别硬压。\n"
        )
    out += "剧本每一句都必须逐字出现在某一镜的 dialogue 里。\n"
    #: 🩸 2026-11-09 主人：「本来有些镜头可以把话说完，却每次都把时间延长」。
    #: 根因是单镜最少 4 秒（模型硬限制）+ 合计不能短于 0.8 倍目标 → 台词少时只能拉长单镜。
    #: 这里只给方向：宁可多排几个短镜，别把一个镜拉长凑数。
    out += (
        "节奏：优先 4–5 秒一个镜头、多排几个，"
        "**不要为了凑总长把某一镜拉长** —— 话早说完了镜头还在空转，看起来就是拖。"
    )
    return out


def _film_spec(doc: dict) -> tuple[str, dict]:
    """项目当前要用的出片型号 + 官方规格。

    还没规划过出片 → 用设置里的全局默认（和 `/film/plan` 同一口径）。
    单次上限**按型号取**（2.5 = 30 秒，其它 = 15 秒），别拿常数盖住。
    """
    from app.services import model_specs

    mid = str((doc.get("film") or {}).get("model") or settings.ark_video_film_model)
    return mid, model_specs.volc(mid)


def _invalidate_film_plan(doc: dict) -> bool:
    """出片确认卡作废 —— **只丢 plan，盘上已出的片子一个不删**。

    计划锁的是「这一版提示词 + 这一组参考图」的指纹。分镜、分镜板、人物参考图
    一变，提示词里的 `@图片N` 编号与内容就全变；旧确认不能再拿去付新提示词的钱。

    🩸 2026-11-08 主人实测：重新出了九宫格板，出片计划还是旧的那版（板当
    `@图片1` 之前算的），点「开始出片」被指纹拦下，报「计划和你看的那一版
    不一样了」。指纹闸本身是对的，错在**板变了没让它作废** —— 所以这里跟
    `/import-script`「分镜一变，下游全过期」同一口径。
    """
    film = doc.get("film")
    if not isinstance(film, dict) or not film.get("plan"):
        return False
    film.pop("plan", None)
    return True


def _segment_note(doc: dict, sb: dict) -> list[str]:
    """本片会切成几段出片（按型号单次上限装箱，切点只在镜头边界）。

    只在**多于一段**时才报：一段是常态，不该天天挂个提示；多段意味着多跑一次
    生成、片子里多一个硬切，主人得看得见（钱按秒算不变）。
    """
    mid, spec = _film_spec(doc)
    cap = float(spec.get("max_sec") or 15)
    shots = [s for s in (sb.get("shots") or []) if isinstance(s, dict)]
    if not shots:
        return []
    try:
        segs = drama_film.split_segments(shots, cap)
    except ValueError as e:
        return [f"分段失败：{e}"]
    if len(segs) <= 1:
        return []
    total = sum(float(s.get("duration") or 0) for s in shots)
    label = str(spec.get("label") or mid)
    return [
        f"本片 {total:g} 秒，{label} 单次上限 {cap:g} 秒 → 要切成 {len(segs)} 段出"
        f"（多跑 {len(segs) - 1} 次生成、多 {len(segs) - 1} 个硬切；"
        f"切点落在镜头边界，成片不受影响；换 2.5 可一次出完）"
    ]


def _gen(doc: dict, stage: str) -> tuple[str, dict | None]:
    brief = _brief(doc)
    # 成片配方只在「写剧本 / 写分镜」两阶段注入 —— 结构卡是剧情骨架，用不上运镜与光线
    tpl_block = _template_block(doc) if stage in ("script", "storyboard") else ""
    if tpl_block:
        brief = f"{brief}\n\n【成片配方】\n{tpl_block}"
    if stage == "card":
        # 自定义形态 = 另一条路：用独立的卡规格 + 独立校验，
        # 五拍 / 双方冲突 / 钩子编号这些老规矩一律不上来（主人 2026-11-07 定）。
        custom = _form_of(doc) == "自定义"
        hook_block = "" if custom else _hook_block(doc)
        form_block = _form_block(doc)
        world_block = _world_block(doc)
        #: 🩸 2026-11-09 实测 65 组定下来的一件事：剧本写成流水账，
        #: 根子不在剧本层，在卡里没有「代价」—— 输入只说「他做了什么」，
        #: 模型就老实写「他做了 X，成功了」，谁都没损失。
        #: 问「谁跟他作对」会塌缩成对手戏（女儿红 6 场里 5 场是阿凯 vs 二叔）；
        #: 问「哪里不好办」八成还是答一个人；只有问「损失什么**具体的**东西」，
        #: 8 个品类才全落到处境上（68 块打车费 / 五千押金 / 自理区单间 / 那盆兰花），
        #: 且反派自己消失了（口红那组的陈妍不再出现）。
        #: 这是一个问题，不是一条规则：不查答案、不重试、不规定形态 ——
        #: 模型每次自己答，答案跟着商品和场景走。
        cost_block = (
            "在写卡之前先想清楚：这事要是搞砸了，他会损失什么具体的**东西**？"
        ) if custom else ""
        return _gen_json(
            doc,
            "card",
            (f"{world_block}\n\n" if world_block else "")
            + (f"{form_block}\n\n" if form_block else "")
            + f"{brief}\n\n" + (f"{hook_block}\n\n" if hook_block else "")
            + (f"{cost_block}\n\n" if cost_block else "")
            + "只输出一个 JSON 对象，严格照下面的格式：\n\n"
            + _ref("output_card_custom.md" if custom else "output_card.md"),
            drama_format.validate_card_custom if custom else drama_format.validate_card,
        )
    if stage == "script":
        # 内置素人主播库（竞品 `presenters.ts:167`）：给了库，角色外观才有可挑的起点；
        # 不出人的模式（产品特写/图文混剪）不注入，免得模型硬塞一个人进来。
        from app.services import drama_presets

        cast_block = drama_presets.prompt_block(
            str((doc.get("answers") or {}).get("presenter") or ""),
            str((doc.get("answers") or {}).get("mode") or ""))
        # 品类指令 + 参考案例（竞品 `script-engine/prompts.ts:821-843`，只注入剧本阶段）。
        # 认不出类目返回空串 —— 竞品回落 beauty 是防崩溃，我们不照抄（见服务文件说明）。
        cat_block = drama_category_templates.script_block(
            str((doc.get("product") or {}).get("category") or ""),
            str((doc.get("answers") or {}).get("script_template") or ""))
        # G4/G5 反哺：已发布视频的真实成效（转化最好的风格/钩子）→ 给模型参考。
        # 冷启动无样本时是空串，什么都不加（竞品 `script/route.ts:118-121`）。
        perf_block = _performance_hint(doc)
        # 🩸 开场钩子原来只在「结构卡」阶段注入 → 单独建项目永远让模型自选，
        # 实测两个项目开场都是 H1（剧本单一的主因之一）。剧本阶段也必须带着走。
        # 创意故事/自定义不套形态 → 也不要求 H1–H5（钩子编号是形态那套的东西）。
        hook_block = "" if _form_of(doc) == "自定义" else _hook_block(doc)
        # 形态要求：自定义按顾客写；没选就让模型挑，并明令不许默认情景短剧
        #（与结构卡同一段文案，见 `_form_block` —— 两处分开写会漂移）
        form_block = _form_block(doc)
        # 故事世界：结构卡阶段定下的那个世界，剧本必须还在里面（不然写着写着回现实了）
        world_block = _world_block(doc)
        return _gen_json(
            doc,
            "script",
            (f"{world_block}\n\n" if world_block else "")
            + (f"{form_block}\n\n" if form_block else "")
            + f"{brief}\n\n" + (f"{hook_block}\n\n" if hook_block else "")
            + (f"{cat_block}\n\n" if cat_block else "")
            + (f"{perf_block}\n\n" if perf_block else "")
            + f"【已确认的结构卡】\n{doc['card']}\n\n"
            f"只输出一个 JSON 对象，严格照下面的格式：\n\n{_ref('output_script.md')}"
            + (f"\n\n{cast_block}" if cast_block else ""),
            drama_format.validate_script,
        )
    if stage == "storyboard":
        # 故事世界必须带到分镜（2026-11-08 修）：只在结构卡/剧本注入时，
        # 镜头描述会回落到通用「两人中景对峙」——世界写了三十七个刀客，7 镜里只有两个人。
        # 空 = 老流程一个字不改（A 线不受影响）。
        world_block = _world_block(doc)
        # 单镜上限**按型号取**（2.5 = 30 秒，其它 = 15 秒）+ 剧本台词逐句覆盖率
        _mid, _spec = _film_spec(doc)
        _max_sec = float(_spec.get("max_sec") or 15)
        _lines = _script_lines(doc)
        _want = float((doc.get("answers") or {}).get("duration") or 0)
        _budget = _dialogue_budget(doc, _want, _max_sec)
        return _gen_json(
            doc,
            "storyboard",
            (f"{world_block}\n\n" if world_block else "")
            + f"{brief}\n\n【结构卡】\n{doc['card']}\n\n【剧本】\n{doc['script']}\n\n"
            + (f"{_budget}\n\n" if _budget else "")
            + f"只输出一个 JSON 对象，严格照下面的格式：\n\n{_ref('output_storyboard.md')}\n\n"
            # 运镜词表（竞品 `prompts.ts:590` 把同一句话嵌在 camera 字段定义里）：
            # 自由文本运镜是他们自己认的头号质量瓶颈，给一条已知拍得出来的句子更稳
            f"【camera 字段写法】\n{drama_camera.guide()}"
            # 参考结构（竞品 `prompts.ts:875-877`）：节奏按老片走，内容按新商品重写
            + str((doc.get("ref_template") or {}).get("block") or ""),
            # 片长要传进去：单镜 4–15s，30s 的片子最多 7 镜，不查合计就会发出 13 镜
            # 「产品特写」另要求商品 100% 出镜 —— 指令写了就得有校验兜着
            lambda o: drama_format.validate_storyboard(
                o,
                want=float((doc.get("answers") or {}).get("duration") or 0) or None,
                require_all_product=(
                    (doc.get("answers") or {}).get("mode") == drama_modes.PRODUCT_CLOSEUP),
                # 2026-11-08：剧本的每一句台词都必须落到镜头上（缺一句退回重写），
                # 单镜上限也按型号取 —— 别拿 15 秒去卡 2.5 的 30 秒
                max_sec=_max_sec,
                script_lines=_lines,
            ),
        )
    if stage == "check":
        # 创意故事/自定义不套十形态：清单里绑死形态的三条按「不适用」处理，
        # 不然「缺 H1–H5 编号」会被判成不合格，逼模型回去套模板。
        custom_note = (
            "\n\n【本次形态：创意故事/自定义】第 11 条（开头策略 H1–H5）、"
            "第 13 条（中段续命）、第 14 条（CTA 双落位）按「不适用」处理；"
            "其余各条照常逐条过。"
            if _form_of(doc) == "自定义" else ""
        )
        return _chat(
            f"{brief}\n\n【结构卡】\n{doc['card']}\n\n【剧本】\n{doc['script']}\n\n"
            f"【分镜表】\n{doc['storyboard']}\n\n"
            f"逐条自检。每条给：通过 / 不通过 + 一句理由 + 不通过时给改法。\n\n"
            f"{_ref('check.md')}{custom_note}\n\n最后一行写：结论：可交付 / 不可交付。",
            temperature=0.2,
            form=_form_of(doc),
        ), None
    raise DramaError(f"未知阶段 {stage}")


# ---------- 路由 ----------
@router.get("/health")
def health():
    """一站式自诊断：报障时截这一张图就够了。

    出处：clipforge `api/health/route.ts:9-64`（原话：用户报障时只需截一张图，
    不用再来回追问日志）。**只读、不含任何密钥内容** —— 只报「配没配」的布尔值。
    """
    import platform
    import shutil
    import sys

    from app.services import media

    problems: list[str] = []

    # 1. 数据目录真的能写（Windows 上 os.access 不可靠，所以真写一次再删）
    data = _dir()
    writable = False
    try:
        probe = data / ".health-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        writable = True
    except Exception as e:  # noqa: BLE001
        problems.append(f"数据目录不可写：{str(e)[:120]}")

    try:
        projects = sum(1 for p in data.iterdir() if p.is_dir())
    except Exception:  # noqa: BLE001
        projects = 0

    # 2. ffmpeg / ffprobe（本地出图、质检、封面、拼接全靠它）
    ff = media.ffmpeg_path()
    fp = media.ffprobe_path()
    ff_ver = ""
    if ff:
        try:
            p = subprocess.run([ff, "-version"], capture_output=True,
                               text=True, errors="ignore", timeout=15)
            ff_ver = (p.stdout or "").splitlines()[0][:80]
        except Exception:  # noqa: BLE001
            ff_ver = ""
    if not ff:
        problems.append("找不到 ffmpeg（设 VT_FFMPEG 或装进 PATH）")
    if not fp:
        problems.append("找不到 ffprobe")

    # 3. 磁盘余量（出片素材最容易撑爆 C 盘）
    free_gb = None
    try:
        free_gb = round(shutil.disk_usage(str(data)).free / 1024 ** 3, 1)
        if free_gb < 2:
            problems.append(f"磁盘只剩 {free_gb} GB")
    except Exception:  # noqa: BLE001
        pass

    llm_ok = bool((settings.deepseek_api_key or "").strip())
    ark_ok = bool((getattr(settings, "ark_api_key", "") or "").strip())
    if not llm_ok:
        problems.append("DeepSeek Key 没配：剧本/分镜/判官都用不了")

    if not _ref("rules.md"):
        problems.append(f"规则文件缺失：{REFS}")

    return ok({
        "ok": not problems,
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "problems": problems,
        "runtime": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "pid": os.getpid(),
        },
        "paths": {
            "data": str(data),
            "writable": writable,
            "projects": projects,
        },
        "ffmpeg": {"path": str(ff or ""), "exists": bool(ff), "version": ff_ver},
        "ffprobe": {"path": str(fp or ""), "exists": bool(fp)},
        "disk_free_gb": free_gb,
        # 老字段保留，前端已按这个读
        "llm": llm_ok,
        "ark": ark_ok,
        "model": settings.deepseek_model,
        "refs": str(REFS),
        "refs_ok": bool(_ref("rules.md")),
    })


@router.get("/tasks")
def tasks(active: int = 1):
    """跨项目「还有钱卡着吗」：已提交未取回的任务单独列（C17）。

    出处：clipforge `api/ai/tasks/route.ts`（`?active=1` 只回还需处理的；
    不带项目时跨项目查全部在飞付费任务）。分类口径见 `services/drama_tasks.py`：
    `submitted` = 盘上有任务号（可领回）；`unknown` = 只登记了在飞、没有任务号。

    🩸 这些是**已经发出去的钱**：界面固定提示「别重复提交」——
    重复提交 = 又付一次（`ark.py:709-719` 的教训）。
    """
    return ok(drama_tasks.scan(_dir(), FILM_DIR, active=bool(active)))


@router.post("/projects/{pid}/tasks/{no}/resume")
def task_resume(pid: str, no: int):
    """领回**已提交**的云端任务：只查询 + 下载，**绝不重新提交**（零新费用）。

    由使用者在界面上点。平台还在跑 → 原样回报，过会儿再点；
    成功 → 下载成片并把这一段的记录补进项目；失败/失效 → 如实回报，不替你重出。
    """
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    film = doc.get("film") or {}
    running = dict(film.get("running") or {})
    info = running.get(str(no))
    if not isinstance(info, dict):
        return fail(f"第 {no} 段没有在飞任务登记")
    files = dict(film.get("files") or {})
    if (files.get(str(no)) or {}).get("name"):
        return fail(f"第 {no} 段已经有成品了，不必领回")

    out_name = str(info.get("out") or "")
    if not out_name:
        return fail("这条登记里没有成片文件名，查不到任务号")
    tid = str(drama_tasks.read_state(
        drama_tasks.state_path(FILM_DIR, pid, out_name)).get("tid") or "")
    if not tid:
        return fail("这条没有落盘任务号 —— 不知道平台那边收没收到。"
                    "先去出片平台的「任务/历史」里确认，别重复提交（会再付一次）")

    out = FILM_DIR / pid / Path(out_name).name
    try:
        got = ark.retrieve_task(tid, out)
    except ark.ArkError as e:
        log.warning("[drama] 领回任务 %s 失败: %s", tid, e)
        return fail(f"领回失败：{str(e)[:300]}")

    st = str(got.get("status") or "")
    if st == "succeeded":
        files[str(no)] = {"name": out.name, "seconds": info.get("seconds")}
        running.pop(str(no), None)
        doc["film"] = {**film, "files": files, "running": running}
        _save(doc)
        return ok({"status": "succeeded", "tid": tid, "file": out.name, "doc": doc})
    if st in ("failed", "cancelled", "expired"):
        return ok({"status": st, "tid": tid,
                   "message": "平台侧已结束/失效 —— 这段需要重出。先「清除登记」再重出，"
                              "别对同一笔重复提交"})
    return ok({"status": st or "processing", "tid": tid,
               "message": "平台还在跑，过一会儿再点一次「领回」"})


@router.get("/probe")
def probe_providers():
    """C4 可探测的通道清单（只回是否配置，绝不回 Key）。"""
    return ok({"providers": drama_probe.provider_rows(settings),
               "timeout": drama_probe.PROBE_TIMEOUT})


class ProbeIn(BaseModel):
    name: str = ""
    names: list[str] = Field(default_factory=list)


@router.post("/probe")
def run_probe(body: ProbeIn = ProbeIn()):
    """C4 服务端连通性探针：12 秒超时，上游原文只进日志、不回前端。

    不传名称 = 测全部登记通道；不支持的通道回 `unsupported` + 原因，不做假探针。
    """
    names = list(body.names) or ([body.name] if body.name else [])
    results = drama_probe.probe_all(names, settings)
    return ok({"results": results, "total": len(results)})


@router.post("/projects/{pid}/tasks/clear")
def task_clear(pid: str, no: int = 0):
    """把一条「在飞」登记划掉 —— 只在**确认平台那边已经收尾**之后点。

    为什么要有：进程被杀时这条会留在盘上（那是好事，提醒别重复提交）；
    但收回来了它不会自动消失，得给人一个明确的「这笔清了」动作。
    """
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    film = doc.get("film") or {}
    running = dict(film.get("running") or {})
    if not running:
        return fail("没有在飞的任务")
    if no:
        if str(no) not in running:
            return fail(f"第 {no} 段没有在飞任务")
        running.pop(str(no), None)
    else:
        running = {}
    doc["film"] = {**film, "running": running}
    _save(doc)
    return ok(doc)


@router.get("/options")
def options():
    """新建表单的全部选项 —— 前端不写死，改一处两边一起变。

    对标 clipforge 的「三步」表单（商品来源 → 商品信息 → 视频配置）。
    """
    from app.services import drama_presets, model_specs

    # 出片型号：单次时长 / 参考图上限**逐档列出**——2.5 和 2.0 不是一套尺，
    # 界面上要让使用者看见差别（2.5：30s / 30 张；2.0：15s / 9 张）。
    film_models = []
    for mid, label in model_specs.MODELS["volc"]:
        spec = model_specs.volc(mid)
        film_models.append(
            {
                "id": mid,
                "label": label,
                "max_sec": int(float(spec.get("max_sec") or 15)),
                "max_refs": int(spec.get("max_ref_images") or drama_film.MAX_REFS),
                # 清晰度档位**按型号列**（2.5：480p/720p/1080p；2.0：多一个 4k；
                # fast/mini 只到 720p）—— 界面只显示这个型号真吃得下的档
                "resolutions": list(spec.get("resolutions") or ()),
                "default_resolution": str(spec.get("default_resolution") or "720p"),
            }
        )
    return ok(
        {
            "categories": list(CATEGORIES),
            # 品类脚本模板（竞品 `templates/index.ts`）：每个类目下可挑的叙事套路
            "script_templates": drama_category_templates.list_categories(),
            "prices": list(PRICES),
            "audiences": list(AUDIENCES),
            "platforms": list(PLATFORMS),
            "modes": list(MODES),
            # 十种形态（`references/form_*.md`，竞品 `script-engine/prompts.ts:44-80` 的中文口径）
            "forms": list(FORMS),
            # 开场钩子五选一（`references/hook.md:7-13`）。空 = 让模型自选。
            # 前端渲染成一行 chips；选了就进 `answers.preferred_hook`，剧本/结构卡两阶段都注入。
            "hooks": [{"code": k, "name": v[0], "condition": v[1]}
                      for k, v in _HOOK_CARDS.items()],
            "durations": [15, 30, 60],
            "roles": ["转折道具", "欲望对象", "身份符号"],
            # 内置素人主播库（竞品 `presenters.ts:57-106`）：空 = 让剧本模型自选或自创
            "presenters": drama_presets.public(),
            "max_pics": MAX_PRODUCT_PICS,
            "accepts": sorted(_IMG_EXT),
            "film_models": film_models,
            "default_film_model": settings.ark_video_film_model,
        }
    )


# ---------- 预设库（Look / 运镜 / 字幕）与成片模板 ----------
# 出处：clipforge `src/lib/look-presets.ts` / `camera-presets.ts` / `caption-presets.ts`
# / `ad-templates.ts`。数据在 `app/data/*.json`，由导入脚本原样抽出，不是重打一遍。

@router.get("/presets")
def presets():
    """三张预设表一次给全（界面的运镜选择器 / Look 选择器 / 字幕样式都要用）。"""
    return ok({
        "looks": drama_looks.public(),
        "cameras": drama_camera.public(),
        "captions": drama_captions.public(),
        "camera_guide": drama_camera.guide(),
    })


@router.get("/templates")
def templates(group: str = "all", category: str = "", q: str = ""):
    """模板库列表。`category` 收中文类目（我们的建项表单就是中文），内部换算成模板的类目 id。"""
    cat = drama_templates.category_id(category)
    rows = drama_templates.list_templates(group=group or "all", category=cat, query=q)
    return ok({
        "total": drama_templates.count(),
        "shown": len(rows),
        "groups": drama_templates.groups_public(),
        "templates": rows,
    })


@router.get("/templates/recommend")
def templates_recommend(category: str = "", name: str = "", points: str = "", limit: int = 4):
    """按具体商品推荐（关键词信号 +2、类目对口 +3 / 不对口 −2）。空输入返回空列表。"""
    rows = drama_templates.recommend(
        category=drama_templates.category_id(category),
        product_name=name, selling_points=points,
        limit=max(1, min(12, limit)),
    )
    return ok(rows)


# ---- 我的模板（自建 / 导入 / 编辑）——必须在 /templates/{tid} 之前声明 ----

@router.get("/templates/mine")
def templates_mine():
    return ok(drama_template_store.list_all())


class MineIn(BaseModel):
    """二选一：`share` = 导入的分享文件原文；`template` = AI 定制结果 / 编辑器另存。"""
    share: str | None = None
    template: dict | None = None
    source: str | None = None


@router.post("/templates/mine")
def templates_mine_save(body: MineIn):
    if body.share:
        res = drama_template_store.save_share(body.share, source="import")
    elif body.template:
        res = drama_template_store.save_template(body.template)
    else:
        return fail("要么给 share（导入文件），要么给 template（保存配方）")
    if not res.get("ok"):
        return fail(res.get("message") or "模板内容无法解析")
    return ok(res)


@router.put("/templates/mine")
def templates_mine_update(body: MineIn):
    if not body.template or not body.template.get("_id"):
        return fail("缺少要改的模板")
    tid = str(body.template.pop("_id"))
    clean = drama_templates.sanitize(body.template)
    if not clean:
        return fail("模板内容无法解析")
    row = drama_template_store.update(tid, clean)
    if not row:
        return fail("模板不存在")
    out = {"template": row}
    warn = drama_templates.compliance_terms(clean)
    if warn:
        out["warnings"] = warn
    return ok(out)


@router.delete("/templates/mine")
def templates_mine_delete(id: str = ""):
    if not id:
        return fail("缺少模板 ID")
    return ok({"ok": drama_template_store.delete(id)})


# ---- AI 定制（连不上模型时不假装成功） ----

class CustomIn(BaseModel):
    name: str = ""
    category: str = ""
    points: str = ""


@router.post("/templates/custom")
def templates_custom(body: CustomIn):
    """让模型按商品定制一款配方；模型只许从真实词表里挑，挑错由 sanitize 夹回安全值。

    出处：`ad-template/generate/route.ts:69-115`。
    """
    name = (body.name or "").strip()
    if not name:
        return fail("请先填写商品名称")
    prompt = drama_templates.build_custom_prompt(
        name, (body.category or "").strip(), (body.points or "")[:500].strip())
    text = _chat(prompt, temperature=0.8, system=drama_templates.CUSTOM_SYS)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return fail("AI 未返回有效的模板配方，请重试")
    try:
        obj = json.loads(text[start:end + 1])
    except Exception:
        return fail("AI 返回的配方无法解析，请重试")
    tpl = drama_templates.sanitize(obj)
    if not tpl:
        return fail("AI 返回的配方无法解析，请重试")
    return ok({"template": tpl})


@router.get("/templates/{tid}")
def template_one(tid: str):
    tpl = drama_templates.get(tid)
    if not tpl:
        return fail("模板不存在")
    return ok(drama_templates.public(tpl))


# ---- 项目选中哪个模板（竞品存在 localStorage，我们存项目文档里） ----

class ApplyTemplateIn(BaseModel):
    template: dict | None = None
    mine_id: str | None = None


@router.post("/projects/{pid}/template")
def apply_template(pid: str, body: ApplyTemplateIn):
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    if body.mine_id:
        tpl = drama_template_store.get(body.mine_id)
        if not tpl:
            return fail("模板不存在")
    else:
        # 内置模板按 id 原样认（本身就是合法配方，存 id 就行、别夹成 custom_ai）；
        # AI 定制 / 别人传来的配方才过 sanitize —— 与竞品 `getAdTemplate` / `sanitize` 的分工一致
        if not isinstance(body.template, dict):
            return fail("模板内容无法解析")
        tpl = drama_templates.get(body.template.get("id")) or drama_templates.sanitize(body.template)
    if not tpl:
        return fail("模板内容无法解析")
    doc["template"] = {"template": tpl,
                       "stored": drama_templates.encode_stored(tpl),
                       "applied": False}
    _save(doc)
    return ok({"template": drama_templates.public(tpl)})


@router.delete("/projects/{pid}/template")
def clear_template(pid: str):
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    doc.pop("template", None)
    _save(doc)
    return ok({"ok": True})


# ---- 剧本结构模板（把自己跑通的分镜节奏存下来，换商品复用） ----
# 出处：clipforge `stores/template-store.ts` + `script/page.tsx:281-293`
# + `new/page.tsx:580-587`。**与上面的成片模板平级**，两套互不依赖。

@router.get("/script-templates")
def script_templates():
    return ok([drama_script_templates.public(r) for r in drama_script_templates.list_all()])


@router.delete("/script-templates/{tid}")
def script_template_delete(tid: str):
    return ok({"ok": drama_script_templates.delete(tid)})


class ScriptTplIn(BaseModel):
    name: str = ""


@router.post("/projects/{pid}/script-template")
def script_template_save(pid: str, body: ScriptTplIn):
    """把项目当前**已定的分镜**存成结构模板。没有分镜就没得存 —— 不存空壳。"""
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    shots = ((doc.get("storyboard_json") or {}).get("shots")) or []
    if not shots:
        return fail("这个项目还没有分镜，存不了")
    row = drama_script_templates.add(
        name=body.name or (doc.get("product") or {}).get("name") or "未命名结构",
        shots=shots,
        style_type=str((doc.get("answers") or {}).get("mode") or ""),
        source_project_id=pid,
    )
    if not row:
        return fail("分镜内容不完整，存不了")
    doc["script_template_id"] = row["id"]
    _save(doc)
    return ok(drama_script_templates.public(row))


class RefTplIn(BaseModel):
    id: str = ""


@router.post("/projects/{pid}/ref-template")
def ref_template_set(pid: str, body: RefTplIn):
    """选定一条结构模板作为这个项目的参考；传空 id = 取消。

    把**解析好的那一段**存进项目 —— 模板以后被删掉，这个项目也不会坏
    （竞品也是在创建时把 `referenceStructure` 拷过去的）。
    """
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    if not body.id:
        doc.pop("ref_template", None)
        _save(doc)
        return ok({"ok": True})
    row = drama_script_templates.get(body.id)
    if not row:
        return fail("结构模板不存在")
    doc["ref_template"] = {"id": row["id"], "name": row["name"],
                           "block": drama_script_templates.prompt_block(row)}
    _save(doc)
    drama_script_templates.bump(row["id"])
    return ok({"id": row["id"], "name": row["name"]})


@router.get("/projects")
def list_projects():
    rows = []
    for p in sorted(_dir().glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        # 这个目录约定「一个 json = 一个项目」。万一混进别的形状（实测 2026-11-07：
        # 人物库索引被放成 list 放进来，`d.get` 直接把整个列表接口打成 500），
        # 跳过它而不是让整页崩 —— 列表少一条 ≠ 所有页面都打不开。
        if not isinstance(d, dict):
            continue
        film = d.get("film") or {}
        files = film.get("files") or {}
        # 「已完成」= 至少出过一段成片（整片拼好也算）—— 别的都还在路上
        done = bool(film.get("merged")) or any(
            (v or {}).get("name") for v in files.values())
        rows.append(
            {
                "id": d.get("id"),
                # 话题项目没有商品名 → 回落主题/项目名（不然列表里是一片空白）
                "name": (d.get("product") or {}).get("name") or d.get("topic") or d.get("name") or "",
                "content_type": d.get("content_type") or "product",
                "stage": _stage(d),
                "done": done,
                "updated": d.get("updated"),
            }
        )
    return ok(rows)


def _clean_product_url(prod: dict) -> dict:
    """顾客粘的链接常常是整段分享文案 → 存项目前抠成纯链接（2026-11-08）。

    宁缺勿脏：抠不出来就留空。脏链接会让发布文案的 UTM 和结尾二维码全指错。
    """
    raw = str(prod.get("url") or "").strip()
    if not raw:
        return prod
    try:
        prod["url"] = drama_product_ingest.check_public_url(raw)
    except drama_product_ingest.IngestError:
        prod["url"] = ""
    return prod


@router.post("/projects")
def create(body: NewProjectIn):
    a = body.answers
    # 空 = 让模型自选；「自定义」= 按 form_note 写（两者都不在十种白名单里）
    if a.form and a.form != "自定义" and a.form not in FORMS:
        return fail("形态只能是：" + " / ".join(FORMS) + " / 自定义 / 留空让模型挑")
    if a.form == "自定义" and not (a.form_note or "").strip():
        return fail("选了「自定义」就把你想要的剧情/结构写一句")
    if a.duration not in (15, 30, 60):
        return fail("片长只能是 15 / 30 / 60 秒")
    if a.role not in ("转折道具", "欲望对象", "身份符号"):
        return fail("商品角色只能是 转折道具 / 欲望对象 / 身份符号")
    if a.route and a.route not in ("荒诞", "煽情"):
        return fail("路线只能是 荒诞 / 煽情 / 留空")

    imgs = [Path(x).name for x in (body.product.images or [])]
    if len(imgs) > MAX_PRODUCT_PICS:
        return fail(f"最多 {MAX_PRODUCT_PICS} 张商品图")

    pid = uuid.uuid4().hex[:12]
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    doc = {
        "id": pid,
        "created": now,
        "updated": now,
        "product": {**_clean_product_url(body.product.model_dump()), "images": imgs},
        "answers": a.model_dump(),
        "card": "",
        "card_confirmed": False,
        "script": "",
        "storyboard": "",
        "check": "",
    }
    # 暂存区 → 项目目录。暂存里找不到就退回「已在该项目目录」（老项目补图 / 重传）
    if imgs:
        owner = IMAGES_DIR / pid
        owner.mkdir(parents=True, exist_ok=True)
        kept: list[str] = []
        for name in imgs:
            src = STAGING_DIR / name
            if not src.exists():
                src = owner / name
            if not src.exists():
                continue
            dst = owner / name
            if src != dst:
                src.replace(dst)
            kept.append(name)
        doc["product"]["images"] = kept
    _save(doc)
    return ok(doc)


class ProductPatch(BaseModel):
    """改商品信息（对标表单里所有非必填项都能事后改）。只改传了的字段。"""
    name: str | None = None
    points: list[str] | None = None
    facts: str | None = None
    audience: str | None = None
    category: str | None = None
    price: str | None = None
    platform: str | None = None
    mode: str | None = None
    presenter: str | None = None


@router.patch("/projects/{pid}/product")
def patch_product(pid: str, body: ProductPatch):
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    for k, v in body.model_dump(exclude_none=True).items():
        if k in ("mode", "presenter"):
            doc["answers"][k] = v
        else:
            doc["product"][k] = v
    if not str(doc["product"].get("name") or "").strip():
        return fail("商品名称不能为空")
    _save(doc)
    return ok(doc)


class BibleIn(BaseModel):
    """视觉记忆六锚。只传要改的字段；传空数组 = 清掉该类锚点。"""
    character_anchors: list[str] | None = None
    product_anchors: list[str] | None = None
    wardrobe_anchors: list[str] | None = None
    environment_anchors: list[str] | None = None
    lighting_anchors: list[str] | None = None
    forbidden_changes: list[str] | None = None


@router.patch("/projects/{pid}/bible")
def patch_bible(pid: str, body: BibleIn):
    """保存视觉锚点。存过之后以人为准；没存过就按已有产物现抽（`drama_bible.derive`）。"""
    from app.services import drama_bible

    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    base = drama_bible.effective(doc)
    patch = body.model_dump(exclude_none=True)
    merged = {**base, **patch}
    doc["visual_bible"] = drama_bible.sanitize(merged)
    _save(doc)
    return ok(doc)


@router.get("/projects/{pid}")
def get_one(pid: str):
    from app.services import drama_bible

    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    # 前端要能直接看到「现在生效的六锚」：没存过的是从剧本/商品资料现抽的
    doc["visual_bible"] = drama_bible.effective(doc)
    # 模板也补上中文名（分组 / 运镜 / 光线）—— 存的是原配方，名字每次现算
    tpl = (doc.get("template") or {}).get("template")
    if tpl:
        doc["template"]["template"] = drama_templates.public(tpl)
    # 上游改过、下游没重做 → 一次性摆给前端（2026-11-08 修 D1/D2）
    doc.update(_stale_flags(doc))
    return ok(doc)


@router.delete("/projects/{pid}")
def delete_project(pid: str):
    """删掉一个项目及其产物（商品图 / 关键帧 / 成片）。

    只在界面上**二次确认**之后才会打到这里；删了不可恢复，所以前端必须问一次。
    """
    import shutil

    p = _path(pid)
    if not p.exists():
        return fail("项目不存在")
    p.unlink(missing_ok=True)
    for d in (IMAGES_DIR, FILM_DIR, GRID_DIR):
        shutil.rmtree(d / pid, ignore_errors=True)
    _recycle_assets(pid, "项目被删")
    return ok({"id": pid})


# ---------- 故事世界（2026-11-07 新增，插在「建项目」和「出结构卡」之间） ----------
#: 为什么加这一步：原来的流程是「选十种形态 → 直接出五拍卡」，所以每条片都是
#: 「两个人吵架、第三拍掏商品」。实测 33 条爆款短剧带货 + 泰国广告公开研究后，
#: 真正的差别不在结构，在「故事发生在哪个世界」。详见 `docs/ABSURD-WORLD.md`。
WORLD_SYSTEM = (
    "你是短视频创意策划，长年为电商做剧情广告。你只负责想「故事发生在哪个世界」，"
    "不写剧本、不写台词、不写分镜。"
)

#: L3 的类型池（2026-11-08 实测定案，见 docs/ABSURD-WORLD.md）
#: 程序每次随机指定**一个具体类型**，不让模型自己挑 —— 实测里让模型挑必然塌缩：
#: 自己挑会滑向丧尸/武侠/宫廷；给它一个族让它挑，族内又塌缩（现实类型剧 6 条里 5 条豪门争产）。
#: 强制指定唯一类型后 48 组无一硬凑，最不搭的组合（木偶戏×剃须刀、星际×口红、
#: 丧葬民俗×猫粮、宫廷×拖把）反而出了最好的点子。
#: 已剔除：末日丧尸（4 次实测全是「末日里只有它还有用」同一套）、重生/穿越
#: （那是叙事装置不是世界，模型会滑回现代场景，来路变牵强）。
_L3_GENRES = {
    "古装传奇": ["宫廷", "仙侠", "武侠", "志怪", "民国"],
    "类型影视": ["悬疑片", "恐怖片", "西部片", "犯罪片", "欧美文艺片"],
    "民间怪谈": ["丧葬民俗", "乡村怪谈", "都市传说", "庙宇", "老宅"],
    "非写实": ["皮影戏", "木偶戏", "定格动画", "默片", "二维动画"],
    "未来科技": ["赛博朋克", "星际", "科幻", "人工智能", "虚拟现实"],
    "现实类型剧": ["豪门争产", "家庭伦理", "职场剧", "校园剧", "都市情感"],
}


def _pick_l3() -> tuple[str, str]:
    """随机挑一个（族, 具体类型）。顾客点「换一批」就会换到别的类型。"""
    family = random.choice(list(_L3_GENRES))
    return family, random.choice(_L3_GENRES[family])


def _random_block(family: str, genre: str) -> str:
    """顾客没挑类型：程序给一个类型当代起点。

    2026-11-08 实测：完全不给，模型会自己塌缩到丧尸/武侠/宫廷。
    🩸 2026-11-09 主人：「全部是你写的你撤掉他呀！」—— 「必须是这个、不许换」
    也撤了，现在只是给个起点。
    """
    return f"**这次可以从【{genre}】（{family}）这个类型想起。**\n"


def _picked_block(genre: str) -> str:
    """顾客自己挑了类型：三个候选都往这个类型里写。

    🩸 2026-11-09 主人：「全部是你写的你撤掉他呀！」
    原来这里我写了三条路子（拟人 / 关系 / 错位），那是我的框架，撤了。
    现在只把顾客的选择原样交给模型。
    """
    return f"**顾客要拍的片子类型是【{genre}】。**\n"


#: 🩸 2026-11-09 主人：「全部是你写的你撤掉他呀！」
#: 原来这段塞了：三律方法（L1/L2/L3）、八个爆款样本、六条硬要求、多样性判据。
#: 全是我自己编的框架 —— 撤了。现在只留：商品 + 顾客选的类型 + 一句任务 + JSON 格式。
#: 🩸 2026-11-09 主人：「问题是你把这一层漏了，所以要先从源头解决」。
#: 原来问的是「找 3 个它绝对不该在的**世界**」，字段又叫 `world`、说明写「一句话世界」
#: —— 模型必然只交回环境设定：「一个全年灼热的武侠西域世界，却让雪地靴成为转折道具」，
#: 通篇没有一个人、没有一件事。后面出卡时模型只能顺着补，补出来自然是
#: 「介绍这个世界 + 商品登场」。
#: 改成问「**场合**」、把人和他的麻烦写进同一句，产出就变成一场戏：
#: 「雪山断崖独木桥头，一个被仇家追杀的刀客停住了脚，追兵的火把已经照到他后背」。
#:
#: 三个版本实测（同一批 6 个商品、同样的类型）：
#:   · 只写人事 → 商品掉出去 4/18（拖把三条全跟拖把无关）
#:   · 加「这件东西怎么**被卷进来**」→ 商品回来 18/18，但 10/18 连结局一起写完
#:     （口红那条从军训涂口红一路写到「教官把她从病号名单上划掉」）
#:   · 换「怎么**添乱**」→ 商品 18/18、组内分化 6/6、写死结局只剩 1/18
#: 完整链路再跑 6 组（候选→卡→剧本）：6/6 有戏，且 6/6 的结尾都是下游自己补的
#: —— 候选停在「一桌人谁也不动筷」「大姐低头正好看见那片蓝光」，不替后面写答案。
#: 措辞钉这一版：**添乱**，不是**卷进来**。
_ABSURD_ASK = """{brief}

给这个商品找 3 个「它绝对不该出现的场合」，每个用一句话说清：什么地方，那儿有谁，他正被什么事难住，这件东西在这儿怎么添乱。

{genre_block}

只输出一个 JSON 对象：
{{"candidates":[{{"site":"场所（3-8 字）","axis":"冲突轴（3-12 字）","era":"时代/语境（3-8 字）","world":"一句话：什么地方，谁在那儿，他正被什么事难住，这件东西在这儿怎么添乱","world_from":"从商品的哪一点长出来的","pitch":"这条片大概会是什么样"}}]}}"""

_MOVING_ASK = """{brief}

**先做一轮用户调研，再从调研里挑能演成戏的处境。** 不许跳过调研直接编故事。

## 第一步 · 调研（内部用，不进成片）

按这个商品的品类和目标人群，回答三件事：
1. **购买时刻**：他们具体在什么场景下会想到要买它？（越具体越好，不要「想变美」这种）
2. **买完的现实**：买完之后真实发生的三类情况——后悔的、被人注意到的、被家里人质疑的
3. **他们的话**：写 8 条这个人群可能说出口的原话，口语、短、带情绪（这是**假设**，不是真实评论）

## 第二步 · 挑 3 个能演成戏的处境

从上面挑 3 个，每个必须：
- 是**具体的一幕**：谁、在哪、因为这件东西发生了什么
- 能拍出来：有动作、有物件、有冲突，不是「一个人很感动」
- 三个必须明显不同

## 禁止

- 不许卖惨
- 不许编造功效、数据、认证
- 不许把这一步的产出说成「真实用户反馈」——它是调研假设，只用来帮你写戏

只输出一个 JSON 对象：
{{"research":{{"moments":["购买时刻1","购买时刻2"],"realities":["买完现实1"],"quotes":["原话1"]}},
 "candidates":[{{"law":"S1","site":"场所（3-8 字）","axis":"冲突轴（3-12 字）","era":"时代/语境（3-8 字，例：古装宫廷 / 现代都市 / 民国）","world":"这个处境发生在哪、谁在里面、发生了什么","world_from":"来自商品的哪一点","pitch":"这条片大概会是什么样"}}]}}"""

#: 🩸 2026-11-09 主人：「全部是你写的你撤掉他呀！」
#: 原来这里躺着 `_DIVERSITY_REQ`（三条岔开的方向参考）和 `_world_diversity_note`
#: （撞车写日志）—— 都是我自造的框架，全删。
#: 模型给什么就是什么；顾客不喜欢就换一批 / 挑别的。


def _world_candidates(doc: dict, route: str, genre: str = "") -> dict:
    """按路线出 3 个候选。

    荒诞：素材来自商品本身，不需要任何外部数据。
    煽情：先让模型做一轮用户调研（购买时刻 / 买完的现实 / 假设用户原话），
          再从调研里挑 3 个能演成戏的处境。**调研产出只是假设，不对外声称是真实评论。**
    不联网、不碰截流、不触发任何平台风控。

    🩸 2026-11-09：「全部是你写的你撤掉他呀！」—— 三律分工 / 爆款清单 / 硬要求 /
    多样性判据全部撤掉，现在只把商品和顾客的选择交给模型。
    """
    picked = False
    if route == "荒诞":
        #: 顾客挑过类型 = 三条都往那一类写；没挑 = 程序给一个类型当起点
        if genre:
            block = _picked_block(genre)
            picked = True
        else:
            family, genre = _pick_l3()
            block = _random_block(family, genre)
            picked = False
        ask = _ABSURD_ASK.format(brief=_brief(doc), genre_block=block)
    else:
        family, genre = "", ""
        ask = _MOVING_ASK.format(brief=_brief(doc))
    # 唯一的重试理由 = 产出解析不了 / 不到 2 条（这是真坏，不是口味不同）
    last = ""
    out: list[dict] = []
    research = {}
    for attempt, temp in enumerate((0.9, 0.6), 1):
        ask_now = ask if not last else (
            f"{ask}\n\n【上一版为什么不能用】\n{last}\n"
            "逐条改对，然后**完整**重新输出一遍 JSON（不要只给改动部分）。")
        text = _chat(ask_now, temperature=temp, system=WORLD_SYSTEM)
        try:
            obj = drama_format.parse_json(text)
        except drama_format.FormatError as e:
            last = str(e)
            log.warning("[drama] 世界候选第%d次解析失败: %s", attempt, last)
            continue
        rows = obj.get("candidates")
        if not isinstance(rows, list) or len(rows) < 2:
            last = "候选少于 2 条"
            continue
        built = []
        for r in rows[:3]:
            if not isinstance(r, dict):
                continue
            w = str(r.get("world") or "").strip()
            src = str(r.get("world_from") or "").strip()
            if not w or not src:
                continue
            law = str(r.get("law") or "").strip()
            built.append({
                "route": route,
                "law": law,
                #: 顾客挑的类型（三条都填）；随机模式下只有 L3 有（排查用）
                "genre": genre if (picked or law.upper() == "L3") else "",
                #: 差异化判据（2026-11-08）：场所 / 冲突轴 / 时代语境，三条必须各不相同
                #: 🩸 era 是 2026-11-08 晚补的：只查 site/axis 时，三条可以全是古装宫廷
                #: （太庙/合卺殿/宫墙根）—— 场所和冲突轴都不同，但看上去还是同一个味。
                "site": str(r.get("site") or "").strip(),
                "axis": str(r.get("axis") or "").strip(),
                "era": str(r.get("era") or "").strip(),
                "world": w,
                "world_from": src,
                "pitch": str(r.get("pitch") or "").strip(),
            })
        out = built
        research = obj.get("research") if isinstance(obj.get("research"), dict) else {}
        break
    if not out:
        raise DramaError(f"世界候选没合格：{last or '模型没给出可用产出'}")
    return {"candidates": out, "research": research}


@router.get("/world-genres")
def world_genres():
    """顾客能挑的短剧类型（2026-11-08）。前端照这个渲染选择器，别自己再存一份。"""
    return ok({"groups": [{"name": k, "items": v} for k, v in _L3_GENRES.items()]})


class WorldsIn(BaseModel):
    #: 空 = 两条路线各出 3 个
    route: str = ""
    #: 顾客挑的短剧类型（`GET /world-genres` 里的词）。非空 = 只在这个类型里出
    genre: str = ""


class PickWorldIn(BaseModel):
    world: str = Field(..., min_length=1)
    world_from: str = ""
    world_law: str = ""
    route: str = ""


@router.post("/projects/{pid}/worlds")
def worlds(pid: str, body: WorldsIn = WorldsIn()):
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    route = (body.route or "").strip()
    genre = (body.genre or "").strip()
    if route and route not in ("荒诞", "煽情"):
        return fail("路线只能是 荒诞 / 煽情 / 留空")
    if genre:
        if genre not in {g for gs in _L3_GENRES.values() for g in gs}:
            return fail("没有这个短剧类型")
        #: 类型只作用于「错位投放」那条，所以强制走荒诞路线
        route = "荒诞"
    routes = [route] if route else ["荒诞", "煽情"]
    rows: list[dict] = []
    research: dict = doc.get("world_research") or {}
    for r in routes:
        try:
            got = _world_candidates(doc, r, genre if r == "荒诞" else "")
        except DramaError as e:
            log.warning("[drama] 世界候选(%s)失败: %s", r, e)
            if len(routes) == 1:
                return fail(str(e))
            continue
        rows.extend(got["candidates"])
        if got.get("research"):
            research[r] = got["research"]
    if not rows:
        return fail("没生成出可用的世界候选")
    doc["world_candidates"] = rows
    # 调研结果单独存：煽情路线的「假设用户原话」只在本项目内部用，
    # 不展示成真实评论、不进成片（2026-11-07 定）。
    doc["world_research"] = research
    _save(doc)
    return ok({"candidates": rows, "research": research})


@router.post("/projects/{pid}/world")
def pick_world(pid: str, body: PickWorldIn):
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    w = body.world.strip()
    if not w:
        return fail("世界不能为空")
    law = (body.world_law or "").strip()
    if law and law not in ("L1", "L2", "L3", "S1", "S2", "S3"):
        return fail("联想法则只能是 L1 / L2 / L3 / S1 / S2 / S3")
    a = doc.setdefault("answers", {})
    a["world"] = w
    a["world_from"] = (body.world_from or "").strip()
    a["world_law"] = law
    a["route"] = (body.route or "").strip()
    _save(doc)
    return ok({"world": w, "world_law": law, "route": a["route"]})


@router.post("/projects/{pid}/generate")
def generate(pid: str, stage: str):
    if stage not in STAGES:
        return fail(f"stage 只能是 {' / '.join(STAGES)}")
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")

    if (doc.get("content_type") or "") == "topic":
        # 话题片是另一个体裁：没有商品、不走结构卡，混进带货流水线只会产出一堆无意义校验
        return fail("话题项目不走带货流水线（结构卡/剧本/分镜），要换稿请回话题页重新生成")
    if stage in ("script", "storyboard", "check") and not doc.get("card"):
        return fail("先出结构卡")
    if stage == "script" and not doc.get("card_confirmed"):
        return fail("结构卡还没确认，不写剧本")
    if stage in ("storyboard", "check") and not doc.get("script"):
        return fail("先写剧本")
    if stage == "check" and not doc.get("storyboard"):
        return fail("先出分镜")

    try:
        text, obj = _gen(doc, stage)
    except DramaError as e:
        log.warning("[drama] %s 生成失败: %s", stage, e)
        return fail(str(e))
    doc[stage] = text
    if obj is not None:
        doc[f"{stage}_json"] = obj
        if stage == "script":
            # A7：每生成一稿存一版（竞品存在 scripts 表，`llm/script/route.ts:226-245`）
            _remember_script(doc, text, obj, "ai")
        if stage == "storyboard":
            # 可生成性提示（C13 四禁 + S1/S2）：**不拦**，只摆出来给人改判官用
            doc["storyboard_lints"] = drama_format.lint_storyboard(obj)
            # 记下这版分镜是照哪一版剧本写的（切版本时前端要提示过期）
            doc["storyboard_script_id"] = _current_script_id(doc)
            # 🩸 2026-11-08：**分镜一变，审过这一版的判官和自检全部作废。**
            # 原来这里只写 lints，旧自检照样挂在界面上说「16 条全过、可交付」——
            # 主人实测那条片子：自检报告审的是台词全的那一版，出片用的是后来重生、
            # 只剩 3 句台词的分镜，结果片子看不懂而界面一路绿灯。
            # 口径和 `/import-script` 一致：分镜变 → 下游清空（不删盘上任何文件）。
            doc.pop("judge", None)
            doc.pop("grid", None)
            # 分镜变了 → 出片确认卡同样作废（段数/提示词/台词都可能变）
            _invalidate_film_plan(doc)
            doc["check"] = ""
            # 出片按型号单次上限自动分段；多段不影响成片，但要让人看得见
            doc["storyboard_lints"] = list(doc["storyboard_lints"]) + _segment_note(doc, obj)
    if stage == "card":
        doc["card_confirmed"] = False
        # 🩸 2026-11-07 实测缺口：顾客不选形态时，模型在结构卡里挑的那个**没写回项目**
        # → 剧本/分镜/自检阶段的 `_form_of` 仍是空，`_rules('')` 只加载 rules.md，
        # 该形态的 `form_*.md` 永远不会进来（三个探针项目 answers.form 全是 ''）。
        # 只认白名单词：卡里写「自定义」不写回 —— 没有 form_note 时 `_form_of`
        # 也不认它，写进去只会把「模型自选」标成「顾客自定义」。
        picked = str((obj or {}).get("form") or "").strip()
        if picked in FORM_FILES and not str((doc.get("answers") or {}).get("form") or "").strip():
            doc["answers"]["form"] = picked

    # D1（2026-11-08）：重出上游后，下游必须"看得见过期"。
    # 原来 generate(card) 只把 card_confirmed 置 false，剧本/分镜原封不动挂着 ——
    # 顾客重出卡再出片，用的还是旧卡写的剧本和分镜（三文鱼项目实测就是这个状态）。
    # 不删数据（顾客可能只想改卡里一句），只记 revision，由 `get_one` 暴露给前端提示重做。
    if stage == "card":
        doc["card_rev"] = int(doc.get("card_rev") or 0) + 1
    else:
        rev = int(doc.get("card_rev") or 0)
        if stage == "script":
            doc["script_card_rev"] = rev
        elif stage == "storyboard":
            doc["storyboard_card_rev"] = rev
    _save(doc)
    return ok(doc)


@router.post("/projects/{pid}/confirm")
def confirm(pid: str):
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    if not doc.get("card"):
        return fail("还没有结构卡")
    doc["card_confirmed"] = True
    _save(doc)
    return ok(doc)


@router.post("/projects/{pid}/reset")
def reset(pid: str, stage: str):
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    if stage not in STAGES:
        return fail(f"stage 只能是 {' / '.join(STAGES)}")
    for k in STAGES[STAGES.index(stage):]:
        doc[k] = ""
        doc.pop(f"{k}_json", None)
        if k == "storyboard":
            doc.pop("judge", None)   # 分镜一变，判官意见就过期
            doc.pop("grid", None)    # 关键帧同理
            _invalidate_film_plan(doc)  # 出片确认卡同理（别拿旧确认去付新提示词）
    if stage == "card":
        doc["card_confirmed"] = False
    _save(doc)
    return ok(doc)


# ---------- 话题起片（A6，竞品 `api/topic/script/route.ts` + `prompts.ts:924-1100`） ----------
class TopicIn(BaseModel):
    topic: str = ""
    narration_style: str = "knowledge"
    duration: int = drama_topic.DEFAULT_DURATION
    count: int = 3
    project_id: str = ""


@router.get("/topic/options")
def topic_options():
    """话题起片的选项（不花钱）。"""
    return ok({
        "styles": drama_topic.public_styles(),
        "durations": list(drama_topic.DURATIONS),
        "default_style": drama_topic.DEFAULT_STYLE,
        "default_duration": drama_topic.DEFAULT_DURATION,
        "min_count": drama_topic.MIN_COUNT,
        "max_count": drama_topic.MAX_COUNT,
        "min_shots": drama_topic.MIN_SHOTS,
        "max_shots": drama_topic.MAX_SHOTS,
    })


def _topic_variants(topic: str, style: str, duration: int, count: int) -> list[dict]:
    """调模型写话题脚本；不合格带着原因重试一次（同 `_gen_json` 的回路）。"""
    user = drama_topic.prompt(topic, style, duration, count)
    last = ""
    for temp in (0.7, 0.3):
        ask = user
        if last:
            ask = (user + "\n\n【上一版为什么不能用】\n" + last
                   + "\n逐条改对，然后**完整**重新输出一遍 JSON。")
        raw = _chat(ask, temperature=temp, system=drama_topic.SYSTEM)
        try:
            obj = drama_format.parse_json(raw)
        except drama_format.FormatError as e:
            last = str(e)
            continue
        variants = drama_topic.split_variants(obj, count)
        if not variants:
            last = "产出里没有 scripts/shots"
            continue
        errs = []
        for v in variants:
            errs += drama_topic.validate(v, target=duration)
        if errs:
            last = "产出不合格：" + "；".join(errs[:8])
            continue
        return variants
    raise DramaError(last or "模型没给出可用的话题脚本")


@router.post("/topic")
def create_topic(body: TopicIn):
    """一句话主题 → 建项目 + 写 N 版内容向脚本（**花一次模型调用**，由使用者点）。

    话题项目与带货项目**平级并存**，不互相覆盖：拿带货项目 id 来跑会被拒
    （竞品 `topic/script/route.ts:72-79` 的 409）。
    """
    topic = (body.topic or "").strip()
    if len(topic) < 2:
        return fail("请填写一句话主题")
    if body.duration not in drama_topic.DURATIONS:
        return fail(f"片长只能是 {' / '.join(str(x) for x in drama_topic.DURATIONS)} 秒")
    count = max(drama_topic.MIN_COUNT, min(drama_topic.MAX_COUNT, int(body.count or 3)))
    style = body.narration_style if body.narration_style in drama_topic.STYLES else drama_topic.DEFAULT_STYLE

    if body.project_id:
        try:
            doc = _load(body.project_id)
        except KeyError:
            return fail("项目不存在")
        if doc.get("content_type") != "topic":
            return fail("该项目是带货项目，请新建主题项目而不是覆盖它")
    else:
        doc = {
            "id": uuid.uuid4().hex[:8],
            "name": drama_topic.name_of(topic),
            "content_type": "topic",
            "topic": topic,
            "product": {},                       # 话题片没有商品
            "answers": {"form": "话题", "duration": body.duration},
            "card": "", "card_confirmed": False,
            "script": "", "storyboard": "", "check": "",
        }

    try:
        variants = _topic_variants(topic, style, body.duration, count)
    except DramaError as e:
        log.warning("[drama] topic 生成失败: %s", e)
        return fail(str(e))

    doc["narration_style"] = style
    doc["topic"] = topic
    doc["name"] = drama_topic.name_of(topic)
    first_id = ""
    for v in variants:
        shots = drama_topic.to_shots(v)
        text = drama_format.render_storyboard({"shots": shots})
        row = _remember_script(doc, text,
                               {"shots": shots, "characters": [], "scenes": [],
                                "title": str(v.get("title") or "").strip(),
                                "content_type": "topic"},
                               "topic", str(v.get("title") or "").strip())
        first_id = first_id or row["id"]
    # 默认选第一条（竞品 `:118` `selected: i === 0`）
    _select_script(doc, first_id)
    cur = next((r for r in doc["scripts"] if r.get("id") == first_id), None) or {}
    shots = (cur.get("json") or {}).get("shots") or []
    doc["storyboard_json"] = {"shots": shots}
    doc["storyboard"] = drama_format.render_storyboard({"shots": shots})
    doc["storyboard_lints"] = drama_format.lint_storyboard({"shots": shots})
    doc["storyboard_script_id"] = first_id
    _save(doc)
    return ok({"project": doc, "count": len(variants),
               "scripts": [_public_script(r) for r in doc.get("scripts") or []]})


# ---------- 能力预检（C16，竞品 `model-capabilities.ts`） ----------
class PreflightIn(BaseModel):
    model: str = ""
    duration: float | None = None
    resolution: str = "720p"
    aspect_ratio: str = "9:16"
    chain_mode: str = "off"
    audio_enabled: bool = False
    reference_image_count: int = 0
    reference_audio_count: int = 0


@router.get("/model-capabilities")
def model_capabilities():
    """可选出片型号的能力摘要（不花钱、不调模型）。"""
    return ok({"models": drama_preflight.catalog()})


@router.post("/preflight")
def preflight(body: PreflightIn):
    """出片前预检：会怎么改参数 + 会踩什么坑。纯计算，不发起任何生成。"""
    return ok(drama_preflight.preflight(
        body.model, duration=body.duration, resolution=body.resolution,
        aspect_ratio=body.aspect_ratio, chain_mode=body.chain_mode,
        audio_enabled=body.audio_enabled,
        reference_image_count=body.reference_image_count,
        reference_audio_count=body.reference_audio_count))


# ---------- 多版脚本（A7）+ 手写脚本导入（A8） ----------
#: 每个项目留几版。竞品每次重生成**先删光旧版本**（`llm/script/route.ts:226`），
#: 只有「一次生成多稿」时才有多版；我们一次生成一稿，照抄删除会让多版管理永远只有 1 条，
#: 所以改成**保留历史**（A7 的功能就是版本管理，删了就没得管）。
MAX_SCRIPT_VERSIONS = 12


def _script_title(obj: dict | None, text: str, source: str, version: int) -> str:
    """版本标题：优先剧本第一场的 what（竞品用首镜口播 `import-script/route.ts:52-55`）。"""
    for sc in (obj or {}).get("scenes") or []:
        what = str((sc or {}).get("what") or "").strip()
        if what:
            return what[:30]
    head = re.split(r"[。！？!?\n]+", (text or "").strip())[0].strip()
    return (head or ("导入脚本" if source == "import" else f"第 {version} 版"))[:30]


def _remember_script(doc: dict, text: str, obj: dict | None, source: str,
                     title: str = "") -> dict:
    """存一版并置为当前；超上限先丢最老的未选中版本。"""
    rows = doc.setdefault("scripts", [])
    for r in rows:
        r["selected"] = False
    version = max([int(r.get("version") or 0) for r in rows] or [0]) + 1
    row = {
        "id": uuid.uuid4().hex[:8],
        "version": version,
        "title": (title.strip() or _script_title(obj, text, source, version))[:30],
        "source": source,          # ai / import
        "text": text,
        "json": obj or {},
        "selected": True,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    rows.append(row)
    if len(rows) > MAX_SCRIPT_VERSIONS:
        spare = [r for r in rows if not r.get("selected")] or rows
        drop = {r["id"] for r in spare[:len(rows) - MAX_SCRIPT_VERSIONS]}
        rows = [r for r in rows if r["id"] not in drop]
    doc["scripts"] = rows
    doc["script"] = text
    doc["script_json"] = obj or {}
    return row


def _select_script(doc: dict, sid: str) -> bool:
    for r in doc.get("scripts") or []:
        if r.get("id") == sid:
            for x in doc["scripts"]:
                x["selected"] = x["id"] == sid
            doc["script"] = r.get("text") or ""
            doc["script_json"] = r.get("json") or {}
            return True
    return False


def _current_script_id(doc: dict) -> str:
    for r in doc.get("scripts") or []:
        if r.get("selected"):
            return str(r.get("id") or "")
    return ""


def _cast_stale(doc: dict) -> list[dict]:
    """定妆图是照哪一版剧本做的（D2，2026-11-08）。

    原来 `cast_pics` 只按名字取图 —— 重出结构卡后角色从「红头巾掌柜」变成
    「光头掌柜」，那张旧脸照样被拿去出片。这里**不判图对不对**（顾客可能就是
    想要这张脸），只判「剧本换过没有」「角色还在不在」，交给前端提示重做。
    老项目没有 script_id = 未知，不报，免得一屏全红。
    """
    cur = _current_script_id(doc)
    names = {
        str(c.get("name") or "").strip()
        for c in ((doc.get("script_json") or {}).get("characters") or [])
        if isinstance(c, dict)
    }
    out: list[dict] = []
    for c in doc.get("cast") or []:
        if not isinstance(c, dict):
            continue
        name = str(c.get("name") or "").strip()
        if not name or not str(c.get("image") or "").strip():
            continue
        sid = str(c.get("script_id") or "")
        if names and name not in names:
            out.append({"name": name, "why": "角色已不在当前剧本里"})
        elif sid and cur and sid != cur:
            out.append({"name": name, "why": "剧本版本已变，脸可能对不上"})
    return out


def _stale_flags(doc: dict) -> dict:
    """上游改过、下游没重做 —— 一次性算给前端（D1/D2，2026-11-08）。

    🩸 抽成函数是为了让接口和探针跑**同一段**判定逻辑：
    写在 `get_one` 里就只能靠读代码确认，探针测的是复制品。
    """
    rev = int(doc.get("card_rev") or 0)
    # 🩸 缺失的 rev 必须归一成 0：老项目 `script_card_rev` 是 None，
    # 直接和 0 比会得到「过期」，一打开就一片红。
    return {
        "script_stale": bool(doc.get("script"))
        and int(doc.get("script_card_rev") or 0) != rev,
        "storyboard_stale_card": bool(doc.get("storyboard"))
        and int(doc.get("storyboard_card_rev") or 0) != rev,
        "cast_stale": _cast_stale(doc),
    }


def _public_script(r: dict) -> dict:
    return {
        "id": r.get("id"),
        "version": r.get("version"),
        "title": r.get("title") or "",
        "source": r.get("source") or "ai",
        "selected": bool(r.get("selected")),
        "created": r.get("created") or "",
        "preview": (r.get("text") or "").replace("\n", " ")[:60],
    }


@router.get("/projects/{pid}/scripts")
def list_scripts(pid: str):
    """竞品 `project/[id]/scripts/route.ts:14-27`：按创建倒序列出全部版本。"""
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    rows = sorted(doc.get("scripts") or [], key=lambda r: int(r.get("version") or 0), reverse=True)
    return ok({
        "scripts": [_public_script(r) for r in rows],
        "selected": _current_script_id(doc),
        # 分镜是照着某一版写的；切了版本却没重出分镜时，前端要能提示
        "storyboard_stale": bool(doc.get("storyboard"))
        and doc.get("storyboard_script_id") != _current_script_id(doc),
    })


@router.post("/projects/{pid}/scripts/{sid}/select")
def select_script(pid: str, sid: str):
    """竞品 PATCH `{ selectedScriptId }`（`scripts/route.ts:79-95`）。"""
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    if not _select_script(doc, sid):
        return fail("脚本版本不存在")
    # 话题片的分镜就存在版本里（没有单独的「按剧本再写分镜」环节），
    # 切版本时连分镜一起换，否则会出现「剧本换了、分镜还是上一版」的自相矛盾。
    if doc.get("content_type") == "topic":
        row = next((r for r in doc.get("scripts") or [] if r.get("id") == sid), {})
        shots = (row.get("json") or {}).get("shots") or []
        if shots:
            doc["storyboard_json"] = {"shots": shots}
            doc["storyboard"] = drama_format.render_storyboard({"shots": shots})
            doc["storyboard_lints"] = drama_format.lint_storyboard({"shots": shots})
            doc["storyboard_script_id"] = sid
    _save(doc)
    return ok({"project": doc, "storyboard_stale": bool(doc.get("storyboard"))
               and doc.get("storyboard_script_id") != sid})


@router.delete("/projects/{pid}/scripts/{sid}")
def delete_script(pid: str, sid: str):
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    rows = doc.get("scripts") or []
    hit = [r for r in rows if r.get("id") == sid]
    if not hit:
        return fail("脚本版本不存在")
    was_selected = bool(hit[0].get("selected"))
    rows = [r for r in rows if r.get("id") != sid]
    doc["scripts"] = rows
    if was_selected:
        if rows:
            newest = max(rows, key=lambda r: int(r.get("version") or 0))
            _select_script(doc, newest["id"])
        else:
            doc["script"] = ""
            doc["script_json"] = {}
    _save(doc)
    return ok(doc)


class ScriptImportIn(BaseModel):
    script: str = ""
    title: str = ""


@router.post("/projects/{pid}/import-script")
def import_script(pid: str, body: ScriptImportIn):
    """手写稿 → 一句一镜 → 直接有分镜（跳过剧本生成）。

    出处：竞品 `import-script/route.ts:33-70`；切分口径见 `services/drama_import.py`。
    """
    text = (body.script or "").strip()
    if len(text) < 2:
        return fail("请提供脚本文案")
    res = drama_import.plan(text)
    if not res["shots"]:
        return fail("脚本无法切分出分镜（缺少有效文案）")
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")

    row = _remember_script(doc, text, {"characters": [], "scenes": [], "source": "import"},
                           "import", body.title)
    sb = {"shots": res["shots"]}
    doc["storyboard"] = drama_format.render_storyboard(sb)
    doc["storyboard_json"] = sb
    doc["storyboard_lints"] = drama_format.lint_storyboard(sb)
    doc["storyboard_script_id"] = row["id"]
    # 分镜一变，下游全过期（和 /reset 同一口径）
    for k in ("judge", "grid", "film"):
        doc.pop(k, None)
    doc["check"] = ""
    doc.pop("check_json", None)
    _save(doc)
    return ok({"project": doc, "count": res["count"], "total_seconds": res["total_seconds"],
               "script": _public_script(row)})


# ---------- 判官 ----------
JUDGE_SYS = drama_judge.SYSTEM.format(judge_brief=drama_judge.JUDGE_BRIEF)


class ApplyIn(BaseModel):
    keys: list[str] = Field(default_factory=list)  # "镜号:字段"，留空 = 应用全部可直接替换的


@router.post("/projects/{pid}/judge")
def judge(pid: str):
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    shots = (doc.get("storyboard_json") or {}).get("shots") or []
    if not shots:
        return fail("先出分镜，判官才有东西可审")

    try:
        raw = _chat(drama_judge.build_user(doc), temperature=0.2, system=JUDGE_SYS)
    except DramaError as e:
        log.warning("[drama] judge 调用失败: %s", e)
        return fail(str(e))

    try:
        obj = drama_format.parse_json(raw)
    except drama_format.FormatError as e:
        return fail(str(e))

    doc["judge"] = drama_judge.sanitize(obj, shots)
    _save(doc)
    return ok(doc)


def _judge_apply_keys(doc: dict, keys: list[str]) -> tuple[list[str], list[str], str]:
    """把判官的改写落到分镜上。

    判官应用端点（用户手点）和「免费快剪」流水线（弱句自动改写）共用这一份，
    出处：竞品 `pipeline-runner.ts:77-97` + `script-judge.ts:289-296`
    （只自动应用 tier != taste 的台词/画面描述改写，口味档留给用户自己选）。
    返回 `(applied, skipped, error)`；error 非空表示校验不过、**改动已丢弃**。
    """
    verdicts = (doc.get("judge") or {}).get("verdicts") or []
    # 🩸 在**副本**上改：校验不过时要整批丢弃，而流水线那一步跑完会无条件 `_save(doc)`，
    # 原地改会让「被丢弃的改动」照样落盘（实测 2026-11-07）。
    sb = copy.deepcopy(doc.get("storyboard_json") or {})
    shots = sb.get("shots") or []
    by_id = {str(s.get("id", i)): s for i, s in enumerate(shots, 1)}

    lookup: dict[str, str] = {}
    for v in verdicts:
        for it in v.get("issues") or []:
            if it.get("new_text"):
                lookup[f"{it['shot_id']}:{it['field']}"] = it["new_text"]

    applied, skipped = [], []
    for k in keys:
        text = lookup.get(k)
        if not text:
            skipped.append(f"{k} 没有可直接替换的内容")
            continue
        sid, _, field = k.partition(":")
        shot = by_id.get(sid)
        if not shot:
            skipped.append(f"{k} 镜头不存在")
            continue
        if field not in ("dialogue", "description", "framing"):
            skipped.append(f"{k} 字段 {field} 不能直接替换")
            continue
        shot[field] = text
        applied.append(k)

    if not applied:
        return applied, skipped, ""
    # 单镜上限按型号取；**不传 script_lines**：判官改写本来就允许换措辞，
    # 拿「和剧本逐字一致」去卡应用，等于把这条功能关掉
    errs = drama_format.validate_storyboard(
        sb, want=float((doc.get("answers") or {}).get("duration") or 0) or None,
        require_all_product=(
            (doc.get("answers") or {}).get("mode") == drama_modes.PRODUCT_CLOSEUP),
        max_sec=float(_film_spec(doc)[1].get("max_sec") or 15))
    if errs:
        return [], skipped, "改完后不合格，已丢弃本次改动：" + "；".join(errs[:4])
    doc["storyboard"] = drama_format.render_storyboard(sb)
    doc["storyboard_json"] = sb
    doc["storyboard_lints"] = drama_format.lint_storyboard(sb)
    # 台词/画面被改过 → 之前那份自检审的是改之前的分镜，作废重跑
    # （判官不动：它刚把能应用的都用掉了，剩下的条目描述的还是没改的镜头）
    doc["check"] = ""
    doc["judge_applied"] = applied
    # 已应用的条目从判官结果里撤掉，避免重复展示
    done = set(applied)
    vd = doc.get("judge") or {}
    for v in vd.get("verdicts") or []:
        v["issues"] = [
            i for i in (v.get("issues") or [])
            if f"{i.get('shot_id')}:{i.get('field')}" not in done
        ]
    c = vd.get("counts")
    if c:
        flat = [i for v in vd.get("verdicts") or [] for i in v.get("issues") or []]
        for t in ("invariant", "default", "taste"):
            c[t] = sum(1 for i in flat if i.get("tier") == t)
    return applied, skipped, ""


@router.post("/projects/{pid}/judge/apply")
def judge_apply(pid: str, body: ApplyIn):
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    verdicts = (doc.get("judge") or {}).get("verdicts") or []
    if not verdicts:
        return fail("先跑判官")

    lookup = {f"{it['shot_id']}:{it['field']}"
              for v in verdicts for it in (v.get("issues") or []) if it.get("new_text")}
    keys = body.keys or sorted(lookup)
    applied, skipped, err = _judge_apply_keys(doc, keys)
    if err:
        return fail(err)
    if applied:
        _save(doc)
    return ok({"applied": applied, "skipped": skipped, "doc": doc})


# ---------- 九宫格关键帧 ----------
GRID_SYS = drama_grid.SYSTEM
GRID_DIR = DATA / "grids"


def _grid_groups(doc: dict) -> list[list[dict]]:
    """要出 AI 的镜头按**出片同一套规则**切段（实拍素材的镜不占段）。

    60 秒 → 2 段 → 2 块板，每块 ≤9 格，和 `drama_film.plan` 的段边界逐字一致。
    """
    shots = drama_film._norm((doc.get("storyboard_json") or {}).get("shots") or [])
    clips = drama_film.shot_clips(doc)
    groups: list[list[dict]] = []
    run: list[dict] = []
    for s in shots:
        if clips.get(s["id"]):
            if run:
                groups.append(run)
                run = []
        else:
            run.append(s)
    if run:
        groups.append(run)
    # 🩸 单次上限按**型号**取，不许拿 `FILM_CAP_SEC`（写死 30）—— 那个数只有 2.5 成立：
    # 2.0 / H3 系列单次 15 秒，20 秒的片子出片会切 2 段，而九宫格这里只分 1 块，
    # 板子和出片段边界就对不上（「每段一块板」直接失效）。2026-11-08 修。
    cap = float(_film_spec(doc)[1].get("max_sec") or 15)
    out: list[list[dict]] = []
    for g in groups:
        try:
            out.extend(drama_film.split_segments(g, cap))
        except ValueError:
            out.append(g)
    return out or [shots]


def _grid_board(doc: dict, no: int = 1) -> dict:
    """第几块板（1 起）。老项目没有 boards 列表 → 就是顶层那一块。"""
    g = doc.get("grid") or {}
    bs = g.get("boards")
    if isinstance(bs, list) and bs:
        if 1 <= no <= len(bs):
            return bs[no - 1]
        return bs[0]
    return g


def _sync_grid(doc: dict) -> None:
    """第一块板同步回顶层 —— 老界面/老代码只读 `grid.image` / `grid.cells`。"""
    g = doc.get("grid") or {}
    bs = g.get("boards")
    if isinstance(bs, list) and bs:
        for k, v in bs[0].items():
            if k != "boards":
                g[k] = v


def _grid_plan_one(doc: dict, shots: list[dict]) -> dict:
    user = drama_grid.build_user(doc, shots)
    last = ""
    for temp in (0.5, 0.2):
        raw = _chat(user, temperature=temp, system=GRID_SYS)
        try:
            obj = drama_format.parse_json(raw)
        except drama_format.FormatError as e:
            last = str(e)
            continue
        errs = drama_grid.validate(obj, shots)
        if errs:
            last = "规划不合格：" + "；".join(errs[:4])
            continue
        g = drama_grid.normalize(obj)
        cast = [c["name"] for c in drama_film.cast_pics(doc)]
        has_prod = bool(drama_film.product_pics(doc))
        # 角色外观原文进提示词：九宫格靠参考图锁人，但一句外观都不写时
        # 视觉锚点检查必然全红（2026-11-08 实测 5 条缺锚全是这个原因）。
        # 只写**这一段镜头里出现过**的角色：60 秒分多块板时，别的段的人不该被画进来。
        chars_all = [c for c in ((doc.get("script_json") or {}).get("characters") or [])
                     if isinstance(c, dict) and str(c.get("name") or "").strip()]
        hay = "".join(str(s.get("description") or "") for s in shots)
        chars_here = [c for c in chars_all if str(c.get("name")) in hay] or chars_all
        cast_desc = "；".join(f"{c.get('name')}（{c.get('appearance')}）" for c in chars_here)
        g["cast_here"] = [str(c.get("name")) for c in chars_here]
        g["prompt"] = drama_grid.prompt(g, cast=cast, has_product=has_prod,
                                        look=drama_looks.look_of_doc(doc),
                                        cast_desc=cast_desc,
                                        product_name=str((doc.get("product") or {}).get("name") or ""))
        g["cast_refs"] = cast
        g["product_ref"] = has_prod
        # 锚点只查**这块板上真出现的角色**：全量锚点里别段角色的原子在这里本来就不该有，
        # 拿全量去查 = 自造假红（2026-11-08 实测 5 条缺锚全是这么来的）
        from app.services import drama_bible as _bible

        _full = _bible.effective(doc)
        _keep: list[str] = []
        for _c in chars_here:
            _keep.extend(_bible._atoms(str(_c.get("appearance") or "")))
        _bb = dict(_full)
        _bb["character_anchors"] = _keep
        _bb["wardrobe_anchors"] = [str(_c.get("wardrobe") or "") for _c in chars_here
                                   if str(_c.get("wardrobe") or "").strip()]
        g["bible_issues"] = _bible.issues_for([g["prompt"]], _bb)
        # F7：逐格标出「一帧画不出先后」的描述（只提示，不拦出图）
        g["cell_lints"] = drama_grid.lint_cells(g)
        return g
    raise DramaError(last or "九宫格规划失败")


def _grid_plan(doc: dict) -> dict:
    """按出片段数规划板：≤30 秒一块；60 秒两块（一张板只有 9 格，盖不住 15 镜）。"""
    groups = _grid_groups(doc)
    boards: list[dict] = []
    for i, g in enumerate(groups, 1):
        b = _grid_plan_one(doc, g)
        b["no"] = i
        b["shot_ids"] = [s.get("id") for s in g]
        boards.append(b)
    out = {**boards[0], "boards": boards}
    # 一块板时把 boards 也存上：渲染/取图统一按 boards 走，不必分支
    return out


@router.post("/projects/{pid}/grid/plan")
def grid_plan(pid: str):
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    if not (doc.get("storyboard_json") or {}).get("shots"):
        return fail("先出分镜，才能规划关键帧")
    try:
        doc["grid"] = _grid_plan(doc)
    except DramaError as e:
        log.warning("[drama] grid plan 失败: %s", e)
        return fail(str(e))
    # 九宫格也过一致性检查：这一张就是全片构图的锚，画错人物等于下游全错。
    # 缺锚只提示（warn），禁改命中才会在出图那一步被拦。
    from app.services import drama_bible

    bible = drama_bible.effective(doc)
    for b in (doc["grid"].get("boards") or [doc["grid"]]):
        # `_grid_plan_one` 已按「本板出现的角色」算过；这里只补没算的那几块
        if "bible_issues" not in b:
            b["bible_issues"] = drama_bible.issues_for([b.get("prompt") or ""], bible)
    _sync_grid(doc)
    _save(doc)
    return ok(doc)


@router.post("/projects/{pid}/grid/render")
def grid_render(pid: str, size: str = "1152x2048", board: int = 1):
    """出九宫格整图 **（花钱）**，由使用者在界面上点。

    尺寸依据（火山官方《图片生成 API》，2026-11-05 抓取原文）：
    Doubao Seedream 5.0 pro / flash 图片生成场景——
      · 方式 1 档位 → 9:16 映射：1K 800x1424 / 1.5K 1152x2048 / 2K 1584x2816
      · 方式 2 直接给宽高，总像素 [921600, 4624220]、宽高比 [1/16, 16]
    这里走方式 2 并写死 1152x2048：确定是 9:16（档位方式是「模型判断」不保证），
    2,359,296 像素在合法区间内，官方注明 1.5K 与 1K 同价。
    """
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    g = _grid_board(doc, board)
    if not (g.get("prompt") or "").strip():
        return fail("先规划九宫格")
    # 一致性硬闸：九宫格是付费出图，禁改词在这版提示词里 → 不提交、不扣费
    from app.services import drama_bible

    hit = drama_bible.blocking([g.get("prompt") or ""], drama_bible.effective(doc))
    if hit:
        return fail(drama_bible.block_message(hit))

    out_dir = GRID_DIR / pid
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    tag = f"grid-{stamp}" + (f"-b{int(g.get('no') or board)}" if board > 1 else "")
    img = out_dir / f"{tag}.jpg"
    # 规划那一版声明了哪几张，这次就必须传哪几张 —— 中间换过人物图/商品图就重规划（不花钱）
    cast_now = [c["name"] for c in drama_film.cast_pics(doc)]
    prod_now = drama_film.product_pics(doc)
    if list(g.get("cast_refs") or []) != cast_now or bool(g.get("product_ref")) != bool(prod_now):
        return fail("人物图或商品图和规划那一版不一样了 —— 先重新规划九宫格（不花钱），再出图")
    refs: list[Path] = []
    # 能力预检：图片模型收几张参考图是**官方写死的**（5.0 pro/flash 2–10、lite/4.x 2–14），
    # 超了服务端直接拒 —— 在花钱之前先拦。出处见 `model_specs.IMAGE_REF_LIMITS` 注释。
    from app.services import model_specs as _ms

    will = len(cast_now) + (1 if prod_now else 0)
    limit = _ms.image_ref_limit(settings.ark_image_model)
    if will > limit:
        return fail(f"这张图要带 {will} 张参考图，超过图片模型上限 {limit} 张"
                    f"（{'、'.join(cast_now)} + 商品图）—— 去掉几个角色或换模型")
    # 参考图顺序必须和提示词里的「第 N 张参考图」逐张一致：人物… → 商品（首图）。
    # 出处：clipforge `storyboard-grid/route.ts:108` `[characterSheetUrl, productImageUrl]`
    # —— 九格的人物和商品靠参考图锁，不靠文字描述（同图同像素才叫一致）。
    for c in drama_film.cast_pics(doc):
        p = IMAGES_DIR / pid / Path(c["image"]).name
        if not p.exists():
            return fail(f"人物参考图「{c['name']}」不见了，重新上传")
        refs.append(p)
    prod = drama_film.product_pics(doc)
    if prod:
        p = IMAGES_DIR / pid / Path(prod[0]).name
        if not p.exists():
            return fail(f"商品图 {prod[0]} 不见了，重新上传")
        refs.append(p)
    try:
        ark.generate_image(g["prompt"], out=img, ref_images=refs or None, size=size)
    except ark.ArkError as e:
        log.warning("[drama] grid render 失败: %s", e)
        return fail(str(e))

    # 🩸 新板一落盘，出片确认卡就作废：提示词里板占 `@图片1`，后面所有参考图编号
    # 都跟着挪一位，旧计划发出去的已经不是这版画面了（2026-11-08 主人被指纹拦下）。
    _invalidate_film_plan(doc)

    cells = []
    try:
        cells = drama_grid.crop_all(img, out_dir, prefix=f"cell-{stamp}" + (f"-b{int(g.get('no') or board)}" if board > 1 else ""))
    except ValueError as e:
        # 比例不对就不裁，留着整图给人看，把原因说清楚
        log.warning("[drama] 九宫格比例不对: %s", e)
        g["image"] = img.name
        g["cell_files"] = []
        g["crop_error"] = str(e)
        _sync_grid(doc)
        _save(doc)
        return fail(f"图出了，但{str(e)}")

    g["image"] = img.name
    g["cell_files"] = [p.name for p in cells]
    g.pop("crop_error", None)
    _sync_grid(doc)
    _save(doc)
    return ok(doc)


@router.get("/projects/{pid}/grid/file")
def grid_file(pid: str, board: int = 1):
    try:
        doc = _load(pid)
    except KeyError:
        raise HTTPException(status_code=404, detail="项目不存在")
    name = _grid_board(doc, board).get("image")
    p = GRID_DIR / pid / name if name else None
    if not p or not p.exists():
        raise HTTPException(status_code=404, detail="还没有九宫格图")
    return FileResponse(p, media_type="image/jpeg")


@router.get("/projects/{pid}/grid/file/{idx}")
def grid_cell_file(pid: str, idx: int, board: int = 1):
    try:
        doc = _load(pid)
    except KeyError:
        raise HTTPException(status_code=404, detail="项目不存在")
    files = _grid_board(doc, board).get("cell_files") or []
    if not (1 <= idx <= len(files)):
        raise HTTPException(status_code=404, detail="没有这一格")
    p = GRID_DIR / pid / files[idx - 1]
    if not p.exists():
        raise HTTPException(status_code=404, detail="这一格文件不在了")
    return FileResponse(p, media_type="image/jpeg")


IMAGES_DIR = DATA / "images"
#: 新建表单的项目还不存在，图先落这里，创建时搬进 `IMAGES_DIR/<pid>/`
STAGING_DIR = DATA / "staging"
_IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}
#: H3 扩展名 ↔ MIME 双查（竞品 `api/upload/route.ts:8-26`：`file.type` 与扩展名各查一遍）。
#: 浏览器/uni.uploadFile 会给准确类型；没有类型（空 / octet-stream）时按扩展名放行，
#: 免得 RPA、curl 这类客户端一律被挡 —— 只看扩展名正是**没有双查**的那种情况。
_IMG_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
             ".webp": "image/webp"}
_GENERIC_MIME = {"", "application/octet-stream", "binary/octet-stream"}


async def _save_upload(file: UploadFile, out_dir: Path) -> str:
    """落盘一张图，返回文件名。类型与扩展名双查；超 10MB / 空文件都拒。"""
    ext = Path(Path(file.filename or "img.jpg").name).suffix.lower()
    if ext not in _IMG_EXT:
        raise ValueError("只收 JPG / PNG / WebP")
    ctype = (file.content_type or "").split(";", 1)[0].strip().lower()
    if ctype not in _GENERIC_MIME and ctype != _IMG_MIME[ext]:
        raise ValueError(f"文件类型（{ctype}）与扩展名（{ext}）不符")
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}{ext}"
    dest = out_dir / fname
    size = 0
    try:
        with dest.open("wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > 10 * 1024 * 1024:
                    raise ValueError("单张超过 10MB")
                f.write(chunk)
        if size == 0:
            raise ValueError("文件是空的")
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    return fname


@router.post("/uploads")
async def stage_upload(file: UploadFile = File(...)):
    """**新建表单**上传商品图 —— 项目还没建，先落暂存区。

    返回 `{name}`，前端把它塞进 `product.images`；点「创建」时后端把暂存区的图
    搬进项目目录（见 `create`）。这样对标的「先传图再填信息」才做得出来。
    """
    try:
        name = await _save_upload(file, STAGING_DIR)
    except Exception as e:  # noqa: BLE001
        return fail(f"上传失败：{str(e)[:120]}")
    return ok({"name": name})


@router.get("/uploads/{name}")
def staged_file(name: str):
    """新建表单里预览**还没建项目**时上传的图。"""
    p = STAGING_DIR / Path(name).name
    if not p.exists():
        return fail("图不存在")
    return FileResponse(p)


_OG = re.compile(r"<meta[^>]+(?:property|name)=[\"']([^\"']+)[\"'][^>]*content=[\"']([^\"']*)[\"']", re.I)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


def _meta(html: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in _OG.findall(html):
        out.setdefault(k.strip().lower(), v.strip())
    m = _TITLE.search(html)
    if m and "title" not in out:
        out["title"] = re.sub(r"\s+", " ", m.group(1)).strip()
    return out


class ImportIn(BaseModel):
    url: str = ""


@router.post("/import-url")
def import_url(body: ImportIn):
    """粘一个商品链接 → 抓标题 / 价格 / 描述 / 商品图（A2：JSON-LD → OG → Twitter → <title>）。

    解析在 `services/drama_product_ingest.py`（照 `product-ingest.ts:1-186`），这里只负责下载图片到暂存。
    抓不到就直说抓不到，**不带任何臆测内容**（C10：不许编产品事实）。
    """
    import httpx
    from urllib.parse import urljoin, urlparse

    try:
        u = drama_product_ingest.check_public_url(body.url or "")
    except drama_product_ingest.IngestError as e:
        return fail(str(e))
    host = urlparse(u).hostname or u

    def _get(c, url):
        """DNS 瞬断重试一次（2026-11-08：同一条链接，顾客那边报 11001，这边连跑 4 次都通）。"""
        try:
            return c.get(url)
        except Exception as e:  # noqa: BLE001
            if "getaddrinfo failed" not in str(e) and "Name or service not known" not in str(e):
                raise
            time.sleep(0.4)
            return c.get(url)

    final = u
    title = desc = ""
    price = None
    imgs: list[str] = []
    names: list[str] = []
    source = ""
    try:
        with httpx.Client(timeout=15, follow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0"}) as c:
            r = _get(c, u)
            r.raise_for_status()
            html = r.text[:2_000_000]
            final = str(r.url)
            info = drama_product_ingest.parse_product_from_html(html, final)
            title, desc, price = info["title"], info["description"], info["price_text"]
            # 「京东验证」这类风控页标题不是商品名 —— 当没抓到，交给分享文案兜底
            if drama_product_ingest.is_placeholder_title(title):
                title = ""
            source = info["source"]
            imgs = list(info["images"])
            # 抖音分享短链跳转后的地址里带商品 JSON（标题/价格/主图），白捡的别浪费
            share_json = drama_product_ingest.from_share_redirect(final)
            if share_json:
                if not title:
                    title = share_json.get("title") or ""
                if not price:
                    price = share_json.get("price_text") or ""
                if share_json.get("image") and share_json["image"] not in imgs:
                    imgs.insert(0, share_json["image"])
                if title and source == "title":
                    source = "share_json"
            # 页内 <img> 兜底：只取前 5 个（竞品没这段；抓不到 JSON-LD/OG 的站点需要）
            if len(imgs) < 3:
                for src in re.findall(r"<img[^>]+src=[\"']([^\"']+)[\"']", html, re.I)[:40]:
                    full = urljoin(final, src)
                    if full not in imgs and not full.startswith("data:"):
                        imgs.append(full)
                    if len(imgs) >= 5:
                        break

            for src in imgs[:MAX_PRODUCT_PICS]:
                try:
                    rr = c.get(urljoin(final, src))
                    ctype = (rr.headers.get("content-type") or "").split(";")[0]
                    ext = {"image/jpeg": ".jpg", "image/png": ".png",
                           "image/webp": ".webp"}.get(ctype)
                    if not ext or len(rr.content) < 2048 or len(rr.content) > 10 * 1024 * 1024:
                        continue
                    STAGING_DIR.mkdir(parents=True, exist_ok=True)
                    fname = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}{ext}"
                    (STAGING_DIR / fname).write_bytes(rr.content)
                    names.append(fname)
                except Exception:  # noqa: BLE001
                    continue
    except Exception as e:  # noqa: BLE001
        # 2026-11-08 主人原话「不会每一条都要我重新发送给你来请求解析吧？」——
        # 失败必须自带线索：把**尝试的域名**写进报错，同时落一条后端日志，
        # 下次不用再问顾客粘了什么。
        raw = str(e)[:120]
        # 抓不动但顾客粘的是 App 分享文案 → 标题就在文本里，直接用，别让人白粘一次
        share = drama_product_ingest.extract_share_title(body.url or "")
        if share:
            logging.getLogger(__name__).warning(
                "import-url 抓不到页面，用分享文案里的商品名 url=%s host=%s title=%s",
                body.url, host, share)
            return ok({"url": u, "title": share[:200], "description": "",
                       "price_text": "", "source": "share_text", "images": []})
        logging.getLogger(__name__).warning(
            "import-url 失败 url=%s host=%s err=%s", body.url, host, raw)
        if "getaddrinfo failed" in raw or "Name or service not known" in raw:
            return fail(f"解析不到「{host}」这个域名，检查链接有没有写错")
        if "Invalid IDNA hostname" in raw:
            return fail(f"链接里的域名「{host}」格式不对，检查一下")
        if "timed out" in raw.lower() or "timeout" in raw.lower():
            return fail(f"「{host}」15 秒没响应，稍后再试")
        code_ = getattr(getattr(e, "response", None), "status_code", 0)
        if code_:
            return fail(f"「{host}」返回 {code_}，这个页面抓不到商品信息")
        return fail(f"抓取失败：{raw}")

    # 页面抓到了但一个商品字段都没有（淘宝/天猫空壳页、抖音风控页）→ 用分享文案里的商品名
    if not title and not desc and not names:
        share = drama_product_ingest.extract_share_title(body.url or "")
        if share:
            title, source = share, "share_text"

    return ok({
        "url": final, "title": title[:200], "description": desc[:1000],
        "price_text": price or "", "source": source, "images": names,
    })


@router.post("/projects/{pid}/images")
async def upload_image(pid: str, file: UploadFile = File(...)):
    """给**已存在**的项目补商品图（对标 clipforge：最多 5 张，JPG/PNG/WebP）。

    用途是出片时当 `reference_image` 锁商品外观 —— 商品在整片里长得一样，
    靠的就是这几张。文件名记进 `product.images`，顺序 = 上传顺序。
    """
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    have = doc["product"].get("images") or []
    if len(have) >= MAX_PRODUCT_PICS:
        return fail(f"最多 {MAX_PRODUCT_PICS} 张商品图，先删一张再传")
    try:
        fname = await _save_upload(file, IMAGES_DIR / pid)
    except Exception as e:  # noqa: BLE001
        return fail(f"上传失败：{str(e)[:120]}")
    doc["product"]["images"] = have + [fname]
    _save(doc)
    return ok(doc)


@router.delete("/projects/{pid}/images/{name}")
def delete_image(pid: str, name: str):
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    name = Path(name).name
    imgs = [x for x in (doc["product"].get("images") or []) if x != name]
    doc["product"]["images"] = imgs
    _save(doc)
    (IMAGES_DIR / pid / name).unlink(missing_ok=True)
    return ok(doc)


@router.get("/projects/{pid}/images/{name}")
def image_file(pid: str, name: str):
    p = IMAGES_DIR / pid / Path(name).name
    if not p.exists():
        return fail("图不存在")
    return FileResponse(p)


# ---------- 出镜人物库（跨项目复用；有图传图 / 没图生成） ----------
# 出处：clipforge `components/presenter-manager.tsx` + `lib/character-sheet.ts:3-10`。
# 与 `doc.cast` 的分工：库是全局的，项目只认 `doc.cast`；绑定时把图复制进项目目录。
class PresenterIn(BaseModel):
    name: str = Field(..., min_length=1)
    appearance: str = ""
    note: str = ""


class PresenterPatchIn(BaseModel):
    name: str | None = None
    appearance: str | None = None
    note: str | None = None


class CastFromLibraryIn(BaseModel):
    presenter_id: str
    name: str = ""


def _presenters():
    from app.services import drama_presenters

    return drama_presenters


@router.get("/presenters")
def presenters_list():
    return ok({"presenters": _presenters().list_all()})


@router.post("/presenters")
def presenters_create(body: PresenterIn):
    try:
        return ok(_presenters().create(body.name, body.appearance, body.note))
    except ValueError as e:
        return fail(str(e))


@router.patch("/presenters/{prid}")
def presenters_update(prid: str, body: PresenterPatchIn):
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        return ok(_presenters().update(prid, fields))
    except KeyError:
        return fail("人物不存在")


@router.delete("/presenters/{prid}")
def presenters_delete(prid: str):
    try:
        _presenters().delete(prid)
    except KeyError:
        return fail("人物不存在")
    return ok({"deleted": prid})


@router.get("/presenters/{prid}/file")
def presenters_file(prid: str):
    p = _presenters().image_path(prid)
    if not p:
        return fail("这个人物还没有图")
    return FileResponse(p, media_type="image/jpeg", filename=p.name)


@router.post("/presenters/{prid}/photo")
async def presenters_photo(prid: str, file: UploadFile = File(...)):
    """有图就传图（锁真人脸）。"""
    svc = _presenters()
    if not svc.get(prid):
        return fail("人物不存在")
    svc.DIR.mkdir(parents=True, exist_ok=True)
    try:
        fname = await _save_upload(file, svc.DIR)
    except Exception as e:  # noqa: BLE001
        return fail(f"上传失败：{str(e)[:120]}")
    return ok(svc.set_image(prid, fname, "upload"))


@router.post("/presenters/{prid}/sheet")
def presenters_sheet(prid: str):
    """没图就在这里生成 2×2 四视图定妆照（**花钱**，由主人点）。"""
    from app.services import drama_sheet

    svc = _presenters()
    row = svc.get(prid)
    if not row:
        return fail("人物不存在")
    appearance = str(row.get("appearance") or "").strip()
    if not appearance:
        return fail("先写外观（发型 / 服装 / 年龄段），定妆照得照着它画")
    svc.DIR.mkdir(parents=True, exist_ok=True)
    out = svc.DIR / f"{prid}.jpg"
    prompt = drama_sheet.build_prompt(appearance, row.get("name") or "")
    try:
        ark.generate_image(prompt, out=out, size=drama_sheet.SHEET_SIZE)
    except ark.ArkError as e:
        log.warning("[drama] 人物库定妆照生成失败 %s: %s", prid, e)
        return fail(f"定妆照生成失败：{str(e)[:160]}")
    return ok(svc.set_image(prid, out.name, "sheet"))


@router.post("/projects/{pid}/cast/from-library")
def cast_from_library(pid: str, body: CastFromLibraryIn):
    """把人物库里的人绑进这个项目的 cast（复制图片进项目目录，下游不区分来源）。"""
    import shutil

    svc = _presenters()
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    row = svc.get(body.presenter_id)
    if not row:
        return fail("人物库里没有这个人")
    src = svc.image_path(body.presenter_id)
    if not src:
        return fail("这个人物还没有定妆图（先传图或生成）")
    name = (body.name or row.get("name") or "").strip()
    if not name:
        return fail("缺角色名")
    out_dir = IMAGES_DIR / pid
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"castlib-{body.presenter_id}{src.suffix}"
    shutil.copy2(src, dst)
    cast = [c for c in (doc.get("cast") or []) if isinstance(c, dict)]
    old = next((c for c in cast if str(c.get("name") or "").strip() == name), None)
    src_kind = row.get("source") or "library"
    sid = _current_script_id(doc)   # D2：记下这张脸是照哪一版剧本配的
    if old:
        old["image"] = dst.name
        old["source"] = src_kind
        old["script_id"] = sid
    else:
        cast.append({"name": name, "image": dst.name, "source": src_kind, "script_id": sid})
    doc["cast"] = cast
    _save(doc)
    return ok(doc)


@router.post("/projects/{pid}/cast")
async def upload_cast(pid: str, name: str, file: UploadFile = File(...)):
    """给某个角色传一张**人物参考图**（脸 / 发型 / 服装的锚）。

    出处：广告分镜 `SOURCE.md:267`「分镜板只管构图，脸不归它管」、
    `:585`「任何情况下都不许把脸指回分镜板」。同一角色再传 = 替换这张。
    """
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    name = (name or "").strip()
    if not name:
        return fail("缺角色名")
    chars = [str(c.get("name") or "").strip()
             for c in ((doc.get("script_json") or {}).get("characters") or [])
             if isinstance(c, dict) and str(c.get("name") or "").strip()]
    if not chars:
        return fail("先出剧本，才知道有哪些角色")
    if name not in chars:
        return fail(f"剧本里没有「{name}」这个角色（可选：{'、'.join(chars)}）")
    try:
        fname = await _save_upload(file, IMAGES_DIR / pid)
    except Exception as e:  # noqa: BLE001
        return fail(f"上传失败：{str(e)[:120]}")
    cast = [c for c in (doc.get("cast") or []) if isinstance(c, dict)]
    old = next((c for c in cast if str(c.get("name") or "").strip() == name), None)
    sid = _current_script_id(doc)   # D2：记下这张脸是照哪一版剧本配的
    if old:
        old["image"] = fname  # 换图：旧文件留在盘上，不删（宁可多个文件，不可删错）
        old["source"] = "upload"
        old["script_id"] = sid
    else:
        cast.append({"name": name, "image": fname, "source": "upload", "script_id": sid})
    doc["cast"] = cast
    _save(doc)
    return ok(doc)


@router.post("/projects/{pid}/cast/sheet")
def gen_cast_sheet(pid: str, name: str):
    """给某个角色**生成** 2×2 四视图定妆照（**花钱**，由主人点）。

    和 `upload_cast` 一件事的两种做法，都留着：
      · 上传 = 用真人照片锁脸（我们的路，竞品没有）；
      · 生成 = 照外观文字画出同一时刻的四个机位（竞品的路，
        `character-sheet.ts:3-10` 说这是「每批生成都换一张脸」的解药）。
    生成出来的照样是一个文件，下游（九宫格/整片/质检）不区分来源。
    """
    from app.services import drama_sheet

    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    name = (name or "").strip()
    if not name:
        return fail("缺角色名")
    chars = [c for c in ((doc.get("script_json") or {}).get("characters") or [])
             if isinstance(c, dict)]
    ch = next((c for c in chars if str(c.get("name") or "").strip() == name), None)
    if ch is None:
        names = [str(c.get("name") or "").strip() for c in chars if str(c.get("name") or "").strip()]
        return fail(f"剧本里没有「{name}」这个角色（可选：{'、'.join(names) or '无'}）")
    appearance = str(ch.get("appearance") or "").strip()
    if not appearance:
        return fail(f"「{name}」还没写外观（发型/服装/年龄），定妆照得照着它画")

    out_dir = IMAGES_DIR / pid
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = out_dir / f"sheet-{stamp}-{len(doc.get('cast') or []) + 1}.jpg"
    prompt = drama_sheet.build_prompt(appearance, name)
    try:
        ark.generate_image(prompt, out=out, size=drama_sheet.SHEET_SIZE)
    except ark.ArkError as e:
        log.warning("[drama] 定妆照生成失败 %s: %s", name, e)
        return fail(f"定妆照生成失败：{str(e)[:160]}")

    cast = [c for c in (doc.get("cast") or []) if isinstance(c, dict)]
    old = next((c for c in cast if str(c.get("name") or "").strip() == name), None)
    sid = _current_script_id(doc)   # D2：记下这张脸是照哪一版剧本配的
    if old:
        old["image"] = out.name          # 旧文件留在盘上，不删
        old["source"] = "sheet"
        old["script_id"] = sid
    else:
        cast.append({"name": name, "image": out.name, "source": "sheet", "script_id": sid})
    doc["cast"] = cast
    doc["cast_sheet_prompt"] = {**(doc.get("cast_sheet_prompt") or {}), name: prompt}
    _save(doc)
    return ok(doc)


@router.delete("/projects/{pid}/cast/{name}")
def delete_cast(pid: str, name: str):
    """删掉某个角色的人物参考图（主人在界面上点了「删」= 明确要删，文件和指针一起清）。"""
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    name = (name or "").strip()
    cast = [c for c in (doc.get("cast") or []) if isinstance(c, dict)]
    keep, hit = [], None
    for c in cast:
        if str(c.get("name") or "").strip() == name:
            hit = c
        else:
            keep.append(c)
    if not hit:
        return fail(f"「{name}」还没有人物参考图")
    doc["cast"] = keep
    _save(doc)
    img = str(hit.get("image") or "")
    if img:
        (IMAGES_DIR / pid / Path(img).name).unlink(missing_ok=True)
    return ok(doc)


FILM_DIR = DATA / "films"


@router.post("/projects/{pid}/film/plan")
def film_plan(pid: str, model: str = "", resolution: str = "", ratio: str = "",
              chain: str = "", realism: str = ""):
    """出片计划（**不花钱**）。

    把分镜 + 九宫格关键帧算成一个出片方案：每段发什么提示词、带哪几张参考图、
    多少秒。前端拿它给使用者看，确认了才点 `film/render`。

    `model` 决定三件事 —— 各家自己一套尺，不许共用：
      ① 单次时长上限（2.5 = 30s；2.0 系列 = 15s）→ 决定切几段；
      ② 参考图张数（2.5 = 30 张；2.0 = 9 张）→ 决定一段能带几张图；
      ③ 提示词口径（2.5 不写参数、不挂兜底包；2.0 必挂兜底包）。
    """
    from app.services import model_specs

    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    if not (doc.get("storyboard_json") or {}).get("shots"):
        return fail("先出分镜，才能规划出片")

    allowed = {mid for mid, _ in model_specs.MODELS["volc"]}
    if model and model not in allowed:
        return fail(f"不支持的出片型号：{model}（可选：{'、'.join(sorted(allowed))}）")

    # 没显式指定 → 走设置中心的全局默认（H4：`film_resolution / film_chain / film_realism`）。
    # 设置文件不存在时 `load` 返回 DEFAULTS，与改动前逐字一致（720p / off / auto）。
    gst, _ = drama_settings.load(SETTINGS_FILE)
    resolution = resolution or str(gst.get("film_resolution") or "720p")
    # 画面比例：只认这三档（竞品 video 页同样的三档）；空/不认 → 竖屏
    from app.services import drama_compose

    ratio = str(ratio or gst.get("film_ratio") or "9:16")
    if ratio not in drama_compose.RATIOS:
        return fail("画面比例只能选：" + " / ".join(drama_compose.RATIOS))
    chain = chain or str(gst.get("film_chain") or "off")
    realism = realism or str(gst.get("film_realism") or "auto")

    mid = model or settings.ark_video_film_model
    spec = model_specs.volc(mid)
    cap = float(spec.get("max_sec") or 15)
    # 🩸 参考图上限**按型号取**，不许拿一个常数盖住：
    #   2.5 = 图片 0–30 张（`api-create.md:25`）、2.0 系列 = 0–9 张（`:30`）。
    #   以前写死 `min(9, spec)`，把 2.5 的 30 张也压成 9 —— 九宫格 9 格 + 5 张商品图
    #   正好 14 张，2.5 明明能吃下却判 we 超限。
    refs = int(spec.get("max_ref_images") or drama_film.MAX_REFS)
    try:
        p = drama_film.plan(doc, cap=cap, max_refs=refs, model=mid,
                            resolution=resolution, ratio=ratio,
                            chain=chain, realism=realism)
    except Exception as e:  # noqa: BLE001
        log.warning("[drama] film plan 失败: %s", e)
        return fail(f"出片规划失败：{e}")
    old_film = doc.get("film") or {}
    doc["film"] = {
        "plan": p, "model": mid, "chain": p.get("chain") or "off",
        # 分辨率也要存：出片时按它重算，否则界面选 1080p、出片回 720p，指纹必然对不上
        "resolution": resolution,
        # 画面比例同理：出片与合成（画布尺寸）都按它走，别在出片时又回落到 9:16
        "ratio": ratio,
        # C12 真实感档存进项目 —— 出片时按它重算，档位一变指纹就对不上（不花钱中止）
        "realism": str(p.get("realism") or "auto"),
        "files": old_film.get("files") or {},
        # 连续被拒次数按型号记，规划一次不许清 —— 它判的是「这个型号不行」
        "rejects": old_film.get("rejects") or {},
        # 在飞登记也不许被重规划清掉 —— 那是**已经付出去的钱**
        "running": old_film.get("running") or {},
    }
    # 画幅/清晰度变了 → 之前的**合成计划**作废（它锁着旧画布与旧切点）。
    # 只清 plan，`outputs`（已合成的片子）和 BGM 等保留；不清会让视频页拿着
    # 旧计划直接合成，出来的片子还是老画幅。
    if (str(old_film.get("ratio") or "9:16"), str(old_film.get("resolution") or "")) \
            != (ratio, resolution):
        comp = doc.get("compose") or {}
        if comp.get("plan"):
            comp["plan"] = None
            doc["compose"] = comp
    _save(doc)
    return ok(doc)


def _recycle_assets(pid: str, why: str) -> None:
    """回收这一单在火山素材库建的组（best-effort，**绝不影响主流程**）。

    额度全账号 50 素材 / 50 组，不回收跑两单就满。只在**终态**回收：
    整片拼好、或项目被删；分段出片期间留着，后续段还能复用缓存（sha1）。
    回收只删火山侧，本地登记表标 recycled 留痕（同复刻线 `ark_ingest.recycle_render`）。
    """
    try:
        from app.services import ark_ingest

        if ark_ingest.available():
            ark_ingest.recycle_render(pid)
    except Exception as e:  # noqa: BLE001
        log.warning("[drama] 素材组回收失败（%s，不影响主流程）：%s", why, e)


def _ref_url(path: Path, pid: str) -> str:
    """出片参考图地址：**含真人脸的必须先入素材库换 `asset://`**。

    火山 Seedance 不收直接上传的真人脸参考图，提交即 400
    `InputImageSensitiveContentDetected.PrivacyInformation`（官方错误码
    `backend/data/official/sd20/pull-2026-11-04/error-codes.md:43`）。
    定妆图 / 带模特或真人的商品图 / 写实九宫格，都会踩这一条。
    判脸用本地 YuNet（零费用）；有脸或判不了 → 入库（同复刻线 `ark_ingest`）。
    """
    from app.services import drama_refs
    from app.services.video_edit import _public_url

    return drama_refs.resolve(path, pid, public_url=lambda p: _public_url(p, pid))


@router.post("/projects/{pid}/film/render")
def film_render(pid: str, no: int = 0, resolution: str = "",
                plan_hash: str = ""):
    """出片（**花钱**），由使用者在界面上点。

    `no=0` 出全部段（按顺序），`no=k` 只重跑第 k 段 —— 一段废了不用整片重来。

    `plan_hash` = 界面确认卡上那一版计划的指纹（`film/plan` 返回的 `plan_hash`）。
    🩸 这里会拿**现在的**文档重算一遍计划再核对指纹：中间改过脚本/型号/时长
    → 直接中止，**一分钱不花**。出处：clipforge `storyboard-film/route.ts:110`
    的 dryRun 分支 + `script/page.tsx:578`「dryRun must return the identical
    prompt（script edited in between → abort and re-preview）」。

    参考图顺序 = 提示词里的 `@图片N` 编号：按格号升序上传，绝不重排。
    """
    from app.services import drama_refs, model_specs
    from app.services.video_edit import _public_url

    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")

    film = doc.get("film") or {}
    plan = film.get("plan") or {}
    segs = plan.get("segments") or []
    if not segs:
        return fail("先规划出片（film/plan）")
    if plan.get("errors"):
        return fail("出片计划有硬问题，先解决：" + "；".join(plan["errors"][:3]))
    # 二次 dryRun：参数取值必须和 `film_plan` 完全一致，否则指纹天然对不上
    mid = film.get("model") or settings.ark_video_film_model
    spec = model_specs.volc(mid)
    chain = str(film.get("chain") or "off")
    realism = str(film.get("realism") or "auto")
    # 分辨率沿用规划时那一档（老项目没存过 → 走全局默认，再不行 720p）
    resolution = resolution or str(film.get("resolution") or "720p")
    # 画面比例同样沿用规划那一档；老项目没这个键 = 9:16（改动前的行为）
    ratio = str(film.get("ratio") or "9:16")
    fresh, err = drama_film.recheck(
        doc, plan_hash, model=mid,
        cap=float(spec.get("max_sec") or 15),
        max_refs=int(spec.get("max_ref_images") or drama_film.MAX_REFS),
        resolution=resolution, ratio=ratio, chain=chain, realism=realism)
    if err:
        return fail(err)
    # 视觉记忆硬闸（clipforge `production-system.ts:119-129`）：禁改词命中 → 拒。
    # 缺锚只是 warn，不拦——它提示「这段提示词没提到人物/商品」，由人判断。
    hit = next((i for i in (fresh.get("bible_issues") or [])
                if i.get("severity") == "fail"), None)
    if hit:
        from app.services import drama_bible

        return fail(drama_bible.block_message(hit))
    # 用重算出来的这一版去出片（就是指纹覆盖的那一版），不用可能过期的存档
    segs = fresh.get("segments") or []

    out_dir = FILM_DIR / pid
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    files = dict(film.get("files") or {})

    picked = [s for s in segs if no <= 0 or int(s.get("no") or 0) == no]
    if not picked:
        return fail(f"没有第 {no} 段")

    prod_files = drama_film.product_pics(doc)
    for seg in picked:
        gi = int(seg.get("no") or 1)
        # 分镜板整张传（不拆格），顺序必须是 @图片1。
        # 60 秒分两块板时，每段只带**自己那块**（`board_no`），格号也是按这块板数的。
        board_name = str(
            (_grid_board(doc, int(seg.get("board_no") or 1)).get("image"))
            or (doc.get("grid") or {}).get("image") or "").strip()
        board_path = GRID_DIR / pid / Path(board_name).name if board_name else None
        urls: list[str] = []
        if seg.get("board"):
            if not board_path or not board_path.exists():
                return fail("分镜板图不见了，先重新出九宫格")
            try:
                urls.append(_ref_url(board_path, pid))
            except drama_refs.RefBlocked as e:
                return fail(str(e))
        # 商品图排第二（@图片1..K，有板时顺延到 2 起）—— 提示词编号就是这么算的，顺序不许动
        for name in prod_files:
            p = IMAGES_DIR / pid / Path(name).name
            if not p.exists():
                return fail(f"商品图 {name} 不见了，重新上传")
            try:
                urls.append(_ref_url(p, pid))
            except drama_refs.RefBlocked as e:
                return fail(str(e))
        # 人物参考图排最后（@图片N..）—— 顺序必须和 `build_prompt` 的编号一致：
        # 板 → 商品 → 人物。广告分镜口径：板只管构图，脸由人物参考图锁
        # （SOURCE.md:267；`:585`「任何情况下都不许把脸指回分镜板」）。
        for c in drama_film.cast_pics(doc):
            p = IMAGES_DIR / pid / Path(c["image"]).name
            if not p.exists():
                return fail(f"人物参考图「{c['name']}」不见了，重新上传")
            try:
                urls.append(_ref_url(p, pid))
            except drama_refs.RefBlocked as e:
                return fail(str(e))
        # B4 每镜参考画面：排在人物参考图之后、续拍尾帧之前（顺序必须与 `build_prompt`
        # 的编号逐字一致：板 → 商品 → 人物 → 每镜画面 → 尾帧）。素材库只收得到图片。
        for m in (seg.get("materials") or []):
            mp = _mat_dir(pid) / Path(str(m.get("material") or "")).name
            if mp.suffix.lower() not in drama_film.MAT_IMAGE_EXT:
                return fail(f"镜头 {m.get('shot_id')} 的参考画面不是图片（{mp.name}），只能选图片")
            if not mp.exists():
                return fail(
                    f"镜头 {m.get('shot_id')} 配的参考画面不在了（{mp.name}），回素材库重新选一张"
                )
            try:
                urls.append(_ref_url(mp, pid))
            except drama_refs.RefBlocked as e:
                return fail(str(e))
        # 续拍（C9）：把上一段的**真实尾帧**排在最后一张，编号顺延到 prompt 里写的 @图片N。
        # 平台尾帧只保 24 小时（`ark.py:382-390`），我们出片时当场落盘，所以盘上有。
        tail_ref = int(seg.get("tail_ref") or 0)
        if tail_ref:
            prev = files.get(str(gi - 1)) or {}
            prev_name = str((prev or {}).get("name") or "")
            if not prev_name:
                return fail(f"续拍要先出第 {gi - 1} 段——本段要用它的真实尾帧锁首帧")
            tail_path = ark.last_frame_path(FILM_DIR / pid / Path(prev_name).name)
            if not tail_path.exists():
                return fail(f"第 {gi - 1} 段没有落盘尾帧（平台只保 24 小时），先重跑第 {gi - 1} 段")
            try:
                urls.append(_ref_url(tail_path, pid))
            except drama_refs.RefBlocked as e:
                return fail(str(e))
            if len(urls) != tail_ref:
                return fail(f"续拍尾帧编号对不上（应为 @图片{tail_ref}，实际第 {len(urls)} 张），先别花钱")
        # 🩸 不再逐格上传裁出来的关键帧：视频模型只收「整张板 + 商品图」。
        # 一镜一格逐张喂是对标 clipforge 的走法（它一镜一格、硬卡 9 镜）；
        # 我们跟广告分镜：板 1 张、格号在提示词里指（SOURCE.md:341）。

        # 素材对应对账：声明里的 @图片N 必须和实际上传逐张对上（错一张 = 锁错图）
        bad_refs = drama_film.check_refs(seg["prompt"], len(urls))
        if bad_refs:
            return fail("素材对应不一致，先别花钱：" + "；".join(bad_refs))

        out = out_dir / f"seg-{gi:02d}-{stamp}.mp4"
        # 在飞登记：这一笔钱已经发出去了（clipforge `ai/tasks?active=1`
        # 「还有钱卡着吗」视图的数据源）。进程被杀 → 这条留在盘上，重启后看得见。
        running = dict((doc.get("film") or {}).get("running") or {})
        running[str(gi)] = {
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "model": film.get("model") or settings.ark_video_film_model,
            "seconds": seg.get("seconds"),
            "out": out.name,
        }
        doc["film"] = {**doc["film"], "running": running}
        _save(doc)
        try:
            ark.omni_video(
                seg["prompt"], out=out, ref_images=urls or None,
                model=film.get("model") or settings.ark_video_film_model,
                resolution=resolution, duration=int(round(float(seg["seconds"]))),
                ratio=ratio, generate_audio=True,
            )
        except ark.ArkError as e:
            log.warning("[drama] film render 第 %d 段失败: %s", gi, e)
            files[str(gi)] = {"name": None, "error": str(e)}
            running.pop(str(gi), None)
            doc["film"] = {**doc["film"], "files": files, "running": running}
            _save(doc)
            return fail(f"第 {gi} 段出片失败：{e}")

        files[str(gi)] = {"name": out.name, "seconds": seg.get("seconds")}
        running.pop(str(gi), None)
        doc["film"] = {**doc["film"], "files": files, "running": running}
        _save(doc)

    return ok(doc)


@router.post("/projects/{pid}/film/{no}/quality")
def film_quality(pid: str, no: int):
    """给**已经出好的**一段打 7 维分（clipforge `generation-quality.ts:123/269/281`）。

    花钱的地方要说清：这里会调**一次视觉模型**（抽 6 帧一起发），费很小但不是 0，
    所以只在主人点了「评这段」时才走。结论只是**建议** —— 换型号/重出/修文字
    都由人再点一次，本接口不会替你改型号、更不会替你重出。
    """
    from app.services import drama_qc, drama_quality

    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    film = doc.get("film") or {}
    files = dict(film.get("files") or {})
    ent = dict(files.get(str(no)) or {})
    name = str(ent.get("name") or "")
    if not name:
        return fail(f"第 {no} 段还没出片，没有可评的东西")
    video = FILM_DIR / pid / Path(name).name
    if not video.exists():
        return fail(f"第 {no} 段的成片文件不见了（{name}）")

    seg = next((s for s in ((film.get("plan") or {}).get("segments") or [])
                if int(s.get("no") or 0) == int(no)), {})
    ids = set(seg.get("shot_ids") or [])
    shots = [s for s in ((doc.get("storyboard_json") or {}).get("shots") or [])
             if isinstance(s, dict) and s.get("id") in ids]
    shot = dict(shots[0]) if len(shots) == 1 else (
        {"description": "；".join(str(s.get("description") or "") for s in shots),
         "product": any(s.get("product") for s in shots)} if shots else {})
    key_shot = bool(shot.get("product"))

    # 评分时一并给参考图：商品图 + 这一段出现的人物图（不给就只能靠模型猜）
    refs: list[tuple[str, Path]] = []
    prod = drama_film.product_pics(doc)
    for name in prod[:2]:
        p = IMAGES_DIR / pid / Path(name).name
        if p.exists():
            refs.append((f"商品实拍图：{str((doc.get('product') or {}).get('name') or '商品')}", p))
    cast_all = {c["name"]: c["image"] for c in drama_film.cast_pics(doc)}
    for seg_name in (seg.get("cast") or []):
        img = cast_all.get(seg_name)
        if not img:
            continue
        p = IMAGES_DIR / pid / Path(img).name
        if p.exists():
            refs.append((f"人物参考图：{seg_name}", p))
    try:
        got = drama_qc.assess(video, shot=shot, frames_dir=IMAGES_DIR / pid,
                              tag=f"qc{int(no):02d}", key_shot=key_shot, refs=refs)
    except ValueError as e:
        return fail(f"评分模型没给出能用的结果：{e}")
    except Exception as e:  # noqa: BLE001
        log.warning("[drama] quality 第 %d 段失败: %s", no, e)
        return fail(f"第 {no} 段评分失败：{str(e)[:160]}")

    result = drama_quality.evaluate(got["raw"], video=True, key_shot=key_shot)
    mid = str(film.get("model") or "")
    rejects = dict(film.get("rejects") or {})
    streak = int(rejects.get(mid) or 0)
    if result["verdict"] == "reject":
        streak += 1
        rejects[mid] = streak
    else:
        rejects[mid] = 0
    action = drama_quality.recommend(result, streak=streak)
    ent["quality"] = {
        **result,
        "action": action,
        "options": drama_quality.options(result),
        "frames": got["frames"],
        "model": got["model"],
        "streak": streak,
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    files[str(no)] = ent
    doc["film"] = {**film, "files": files, "rejects": rejects}
    _save(doc)
    return ok(doc)


@router.post("/projects/{pid}/qc")
def film_qc(pid: str, target: str = "all", expect_seconds: float = 0):
    """成片技术质检：黑屏 / 长静音 / 响度漂移 / 削波 / 定格 / 流完整性 / 时长 / 分辨率。

    出处：clipforge `api/project/[id]/qc/route.ts` + `lib/video-composer/qc.ts`（阈值逐字抄）。
    **本地 ffmpeg，零费用**，不碰合成管线 —— 只看已经落盘的 mp4。
    `target=all` 看拼好的整片；`target=1..n` 看单段。
    """
    from app.services import qc as tech_qc

    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")

    film = doc.get("film") or {}
    files = film.get("files") or {}
    segs = (film.get("plan") or {}).get("segments") or []

    if target == "all":
        name = str(film.get("merged") or "")
        if name:
            path = FILM_DIR / pid / Path(name).name
            expect = sum(float(s.get("duration") or 0) for s in segs)
            label = "整片"
        elif len(segs) == 1:
            rec = files.get(str(segs[0].get("no"))) or {}
            name = str(rec.get("name") or "")
            if not name:
                return fail("还没有出片")
            path = FILM_DIR / pid / Path(name).name
            expect = float(segs[0].get("duration") or 0)
            label = "第 1 段"
        elif len(segs) > 1:
            return fail("还没拼成整片 —— 先「拼接」再质检，或用 target=1..n 逐段查")
        else:
            return fail("还没有出片")
    else:
        try:
            no = int(target)
        except ValueError:
            return fail("target 只能是 all 或段号")
        rec = files.get(str(no)) or {}
        name = str(rec.get("name") or "")
        if not name:
            return fail(f"第 {no} 段还没出片")
        path = FILM_DIR / pid / Path(name).name
        seg = next((s for s in segs if int(s.get("no") or 0) == no), {})
        expect = float(seg.get("duration") or 0)
        label = f"第 {no} 段"

    if not path.exists():
        return fail(f"{label}的成片文件不在了")

    if expect_seconds > 0:
        expect = expect_seconds

    try:
        report = tech_qc.deep_inspect(path, expect_duration=expect or None)
    except Exception as e:  # noqa: BLE001
        log.warning("[drama] tech qc 第 %s 段失败: %s", target, e)
        return fail(f"质检没跑成：{str(e)[:200]}")

    tech = dict(film.get("tech_qc") or {})
    tech[target] = {**report, "label": label, "file": path.name,
                    "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    doc["film"] = {**film, "tech_qc": tech}
    _save(doc)
    return ok(doc)


def _repair_source(doc: dict, pid: str, no: int):
    """找到「第 no 段」已出的成片 + 这一段原来的分镜提示词。"""
    film = doc.get("film") or {}
    ent = (film.get("files") or {}).get(str(no)) or {}
    name = str(ent.get("name") or "")
    if not name:
        return None, {}, f"第 {no} 段还没出片，没有可修复的成片"
    p = FILM_DIR / pid / Path(name).name
    if not p.exists():
        return None, {}, f"第 {no} 段的成片文件不见了（{name}）"
    seg = next((s for s in ((film.get("plan") or {}).get("segments") or [])
                if int(s.get("no") or 0) == int(no)), {})
    return p, seg, ""


def _repair_spec(doc: dict):
    """修复用的型号尺：和出片同一把尺（min/max 秒数按型号取）。"""
    from app.services import model_specs

    film = doc.get("film") or {}
    mid = film.get("model") or settings.ark_video_film_model
    spec = model_specs.volc(mid)
    return mid, float(spec.get("min_sec") or 4), float(spec.get("max_sec") or 15)


@router.post("/projects/{pid}/film/repair/plan")
def film_repair_plan(pid: str, no: int, start: float = 0, end: float = 0,
                     note: str = "", resolution: str = "720p"):
    """窗口精准修复 · 预演（**不花钱**）。

    只算：替换区间、模型实际生成时长、花费、提示词、指纹。区间留空 =
    从片头起 5 秒；给了就夹进片长内。
    """
    from app.services import drama_repair

    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    src, seg, err = _repair_source(doc, pid, no)
    if err:
        return fail(err)
    mid, min_sec, max_sec = _repair_spec(doc)
    try:
        p = drama_repair.plan(
            src, seg.get("prompt") or "", start=start, end=end, note=note,
            model=mid, min_sec=min_sec, max_sec=max_sec,
            resolution=resolution,
            price_per_sec=float(settings.price_video_per_sec or 0))
    except Exception as e:  # noqa: BLE001
        return fail(f"修复预演失败：{e}")
    # 一致性硬闸：修复走的也是付费接口，同样按视觉记忆检查（fail 会拦）
    from app.services import drama_bible

    bible = drama_bible.effective(doc)
    p["bible"] = bible
    p["bible_issues"] = drama_bible.check(p["prompt"], bible)
    return ok(p)


@router.post("/projects/{pid}/film/repair/render")
def film_repair_render(pid: str, no: int, plan_hash: str, start: float = 0,
                       end: float = 0, note: str = "",
                       resolution: str = "720p"):
    """窗口精准修复 · 执行（**花钱**）。

    先过指纹闸（和出片同一个道理：改过参数就不许拿旧确认付钱），
    远端只生成一个替换片段，本地拼回原段；**原段文件不动**，
    修复版另存，`prev` 记着旧名字，能随时切回。
    """
    from app.services import drama_repair

    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    src, seg, err = _repair_source(doc, pid, no)
    if err:
        return fail(err)
    mid, min_sec, max_sec = _repair_spec(doc)
    fresh, err = drama_repair.verify(
        src, seg.get("prompt") or "", plan_hash, start=start, end=end, note=note,
        model=mid, min_sec=min_sec, max_sec=max_sec, resolution=resolution,
        price_per_sec=float(settings.price_video_per_sec or 0))
    if err:
        return fail(err)
    # 视觉记忆硬闸：禁改词出现在修复提示词里 → 拒，不提交不扣费
    from app.services import drama_bible

    hit = drama_bible.blocking([fresh["prompt"]], drama_bible.effective(doc))
    if hit:
        return fail(drama_bible.block_message(hit))

    film = doc.get("film") or {}
    files = dict(film.get("files") or {})
    ent = dict(files.get(str(no)) or {})
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_name = f"seg-{int(no):02d}-repair-{stamp}.mp4"
    out = FILM_DIR / pid / out_name
    try:
        drama_repair.render(
            src, out,
            start=fresh["window"]["start"], end=fresh["window"]["end"],
            prompt=fresh["prompt"], model=mid,
            billed=float(fresh["generated_seconds"]), resolution=resolution)
    except Exception as e:  # noqa: BLE001
        log.warning("[drama] 第 %d 段窗口修复失败: %s", no, e)
        return fail(f"第 {no} 段修复失败（原段保持不变）：{e}")

    ent.update({
        "name": out_name,
        "prev": list(ent.get("prev") or []) + [str(ent.get("name") or "")],
        "repair": {
            "window": fresh["window"],
            "generated_seconds": fresh["generated_seconds"],
            "model": mid,
            "resolution": resolution,
            "plan_hash": plan_hash,
            "note": note,
        },
    })
    files[str(no)] = ent
    doc["film"] = {**film, "files": files}
    _save(doc)
    return ok(doc)


@router.post("/projects/{pid}/film/repair/revert")
def film_repair_revert(pid: str, no: int):
    """切回修复前的原段（**纯本地，不花钱**）。"""
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    film = doc.get("film") or {}
    files = dict(film.get("files") or {})
    ent = dict(files.get(str(no)) or {})
    prev = list(ent.get("prev") or [])
    if not prev:
        return fail(f"第 {no} 段没有修复前的版本可切回")
    old = prev.pop()
    if not (FILM_DIR / pid / Path(old).name).exists():
        return fail(f"修复前的文件不见了（{old}）")
    ent["name"] = old
    ent["prev"] = prev
    ent.pop("repair", None)
    files[str(no)] = ent
    doc["film"] = {**film, "files": files}
    _save(doc)
    return ok(doc)


@router.post("/projects/{pid}/film/concat")
def film_concat(pid: str):
    """把已出的各段按顺序拼成整片（**本地 ffmpeg，不花钱**）。

    分段是模型单次上限逼出来的，不是我们的选择 —— 使用者要的是一条能发的片。
    """
    from app.services import assemble

    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")

    film = doc.get("film") or {}
    files = film.get("files") or {}
    segs = (film.get("plan") or {}).get("segments") or []
    parts: list[Path] = []
    for s in segs:
        rec = files.get(str(s.get("no"))) or {}
        name = rec.get("name")
        p = FILM_DIR / pid / name if name else None
        if not p or not p.exists():
            return fail(f"第 {s.get('no')} 段还没出，先出完再拼")
        parts.append(p)
    if not parts:
        return fail("还没有成片")
    if len(parts) == 1:
        return fail("只有一段，不用拼")

    out_dir = FILM_DIR / pid
    lst = out_dir / "parts.txt"
    lst.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in parts), encoding="utf-8")
    out = out_dir / f"film-{time.strftime('%Y%m%d-%H%M%S')}.mp4"
    try:
        proc = assemble._run(
            ["-f", "concat", "-safe", "0", "-i", str(lst.resolve()),
             "-c", "copy", str(out.resolve())],
            cwd=out_dir,
        )
    except Exception as e:  # noqa: BLE001
        return fail(f"拼接失败：{str(e)[:160]}")
    if proc.returncode != 0 or not out.exists():
        return fail(f"拼接失败：{(proc.stderr or '')[-200:]}")
    lst.unlink(missing_ok=True)

    doc["film"] = {**film, "merged": out.name}
    _save(doc)
    # 整片拼好 = 这一单的终态：回收火山素材组（额度全账号共享，不回收跑两单就满）
    _recycle_assets(pid, "整片拼好")
    return ok(doc)


@router.get("/projects/{pid}/film/file/{no}")
def film_file(pid: str, no: str):
    """取成片：`no=all` 取拼好的整片，`no=1..n` 取单段。"""
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    if no == "all":
        name = (doc.get("film") or {}).get("merged") or ""
        p = FILM_DIR / pid / name if name else None
        if not p or not p.exists():
            return fail("还没拼成整片")
        return FileResponse(p, media_type="video/mp4", filename=name)
    rec = ((doc.get("film") or {}).get("files") or {}).get(str(no)) or {}
    name = rec.get("name")
    p = FILM_DIR / pid / name if name else None
    if not p or not p.exists():
        return fail("这一段还没出")
    return FileResponse(p, media_type="video/mp4", filename=name)


@router.post("/projects/{pid}/readiness")
def readiness(pid: str, aigc_label: str = ""):
    """发布前自检（**纯计算，零费用**）：广告法风险词 / 钩子 / 时长 / 字幕读速 /
    行动号召 / 带货三段式 / 商品前 3 秒。

    出处：clipforge `lib/publish-readiness.ts:39-212`。`aigc_label` 传空 = 不检查
    （主人定过：默认不打 AI 水印）。
    """
    from app.services import drama_compliance

    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")

    shots = ((doc.get("storyboard_json") or {}).get("shots")) or []
    if not shots:
        return fail("还没有分镜，先出分镜再自检")

    total = _total_seconds(shots)
    flag = None
    if aigc_label in ("0", "false", "False"):
        flag = False
    elif aigc_label in ("1", "true", "True"):
        flag = True

    report = drama_compliance.check_readiness(
        shots, total,
        product_name=str((doc.get("product") or {}).get("name") or ""),
        aigc_label=flag)
    doc["readiness"] = {**report, "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    _save(doc)
    return ok(doc)


def _total_seconds(shots: list[dict]) -> float:
    """分镜总时长。手改过的文档里 `duration` 可能是 "6s" 这种串 —— 算不出来就当 0，
    不许因为一条脏数据把整页自检打挂。"""
    total = 0.0
    for s in shots or []:
        try:
            total += float(s.get("duration") or 0)
        except (TypeError, ValueError):
            continue
    return total


def _gate_rows(doc: dict) -> list[dict]:
    """把 7 维评分结果转成门禁行。没评过的段 = pending（warn，不拦）。"""
    film = doc.get("film") or {}
    segs = (film.get("plan") or {}).get("segments") or []
    files = film.get("files") or {}
    rows: list[dict] = []
    for seg in segs:
        no = seg.get("no")
        ent = files.get(str(no)) or {}
        if not ent.get("name"):
            continue
        q = ent.get("quality") or {}
        rows.append({
            "shotId": no,
            "verdict": q.get("verdict") or None,
            "humanDecision": q.get("human") or None,
            "overall": q.get("total"),
        })
    return rows


@router.post("/projects/{pid}/gate")
def release_gate(pid: str):
    """发布门禁：把脚本自检 / 成片质检 / 7 维语义验收 / AI 带货规则合成一个结论。

    出处：clipforge `api/project/[id]/gate/route.ts` + `lib/release-gate.ts`
    （**最差状态胜出**）。纯计算 + 本地 ffmpeg，零模型调用。
    """
    from app.services import drama_compliance

    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")

    shots = ((doc.get("storyboard_json") or {}).get("shots")) or []
    total = _total_seconds(shots)
    # 没分镜就别硬算：门禁项里如实说「没有可检查的脚本」（clipforge
    # `release-gate.ts:46-57` 对 `null` 的处理就是这个）
    rd = (drama_compliance.check_readiness(
        shots, total,
        product_name=str((doc.get("product") or {}).get("name") or ""))
        if shots else None)

    # 成片质检：优先用已经跑过的技术报告，没跑过就现跑一次（本地、不花钱）
    film = doc.get("film") or {}
    tech = (film.get("tech_qc") or {}).get("all") or {}
    if not tech:
        per = film.get("tech_qc") or {}
        tech = next(iter(per.values()), {}) if per else {}
    if not tech:
        try:
            got = film_qc(pid, target="all")
            if got.get("biz_code") == 0 and got.get("data"):
                doc = got["data"]
                film = doc.get("film") or {}
                tech = (film.get("tech_qc") or {}).get("all") or {}
        except Exception as e:  # noqa: BLE001
            log.info("[drama] gate 现跑质检失败（当作没有成片）: %s", e)
            tech = {}

    cast = ((doc.get("script_json") or {}).get("characters")) or []
    has_person = bool(cast) or str((doc.get("answers") or {}).get("mode") or "") == "真人出镜"
    ai_policy = drama_compliance.check_ai_commerce(
        style_type=str((doc.get("answers") or {}).get("form") or ""),
        has_ai_person=has_person,
        product_text=" ".join([
            str((doc.get("product") or {}).get("name") or ""),
            str((doc.get("product") or {}).get("category") or ""),
            str((doc.get("product") or {}).get("points") or ""),
        ]),
        dialogue_text=" ".join(str(s.get("dialogue") or "") for s in shots),
    )

    items = [
        drama_compliance.gate_from_readiness(rd),
        drama_compliance.gate_from_qc(tech or None),
        drama_compliance.gate_from_quality(_gate_rows(doc)),
        drama_compliance.gate_from_credits(_credits_manifest(doc)),
        drama_compliance.gate_from_ai_policy(ai_policy),
    ]
    report = drama_compliance.build_gate(items)
    doc["gate"] = {**report, "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    _save(doc)
    return ok(doc)


@router.post("/projects/{pid}/cover")
def film_cover(pid: str, title: str = "", at: float = 1.0,
               position: str = "center"):
    """从成片抽一帧、压一行大字标题 → 封面图（**本地 ffmpeg，零费用**）。

    出处：clipforge `api/project/[id]/cover/route.ts` + `lib/video-composer/cover.ts`。
    只从**出成功的**成片里抽帧 —— 失败的段不参与，免得把坏帧当封面。
    """
    from app.services import drama_cover

    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")

    film = doc.get("film") or {}
    files = film.get("files") or {}
    segs = (film.get("plan") or {}).get("segments") or []

    name = str(film.get("merged") or "")
    if name:
        video = FILM_DIR / pid / Path(name).name
    else:
        done = [s for s in segs
                if str((files.get(str(s.get("no"))) or {}).get("name") or "")]
        if not done:
            return fail("还没出片，先出片再生成封面")
        last = done[-1]
        video = FILM_DIR / pid / Path(str(files[str(last.get("no"))]["name"])).name

    if not video.exists():
        return fail("成片文件不在了")

    pos = (position or "center").lower()
    if pos not in ("center", "upper", "lower"):
        return fail("position 只支持 center / upper / lower")

    head = (title or "").strip() or str(
        (doc.get("product") or {}).get("name") or "").strip()
    if not head:
        return fail("没有标题可压，传一个 title 或先填商品名")

    out = (FILM_DIR / pid /
           f"cover-{time.strftime('%Y%m%d-%H%M%S')}.jpg")
    try:
        drama_cover.generate(video, head, out, at=at, position=pos)
    except Exception as e:  # noqa: BLE001
        log.warning("[drama] cover 失败: %s", e)
        return fail(f"封面生成失败：{str(e)[:200]}")

    doc["film"] = {**film, "cover": {
        "file": out.name, "title": head, "at": round(float(at), 2),
        "position": pos, "at_time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }}
    _save(doc)
    return ok(doc)


@router.get("/projects/{pid}/cover/file")
def film_cover_file(pid: str):
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    name = str((doc.get("film") or {}).get("cover", {}).get("file") or "")
    p = FILM_DIR / pid / Path(name).name if name else None
    if not p or not p.exists():
        return fail("还没生成封面")
    return FileResponse(p, media_type="image/jpeg", filename=p.name)


@router.get("/projects/{pid}/subtitle")
def export_subtitle(pid: str, format: str = "srt", gap_ms: int = 0):
    """导出字幕 SRT / VTT（**本地纯计算，零费用**）。

    出处：clipforge `api/project/[id]/subtitle/route.ts` + `lib/subtitle-export.ts`。
    时轴按分镜计划时长累加 —— 这是**可编辑草稿**，不是帧级对轴成品。
    """
    from app.services import drama_subtitle

    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")

    shots = ((doc.get("storyboard_json") or {}).get("shots")) or []
    if not shots:
        return fail("还没有分镜，导不出字幕")

    fmt = (format or "srt").lower()
    if fmt not in ("srt", "vtt"):
        return fail("format 只支持 srt 或 vtt")

    text = drama_subtitle.from_shots(shots, fmt, gap_ms=gap_ms)
    if not text.strip() or text.strip() == "WEBVTT":
        return fail("分镜里没有台词，导不出来字幕")

    # 文件名带商品名（中文走 RFC 5987 编码，否则浏览器拿到乱码）
    name = f"{str(doc.get('product', {}).get('name') or pid)[:40]}.{fmt}"
    quoted = quote(name, safe="")
    return PlainTextResponse(
        text,
        media_type=("text/vtt; charset=utf-8" if fmt == "vtt"
                    else "text/plain; charset=utf-8"),
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}"},
    )


@router.get("/projects/{pid}/export", response_class=PlainTextResponse)
def export_md(pid: str):
    try:
        doc = _load(pid)
    except KeyError:
        return PlainTextResponse("项目不存在", status_code=404)
    p, a = doc["product"], doc["answers"]
    return PlainTextResponse(
        "\n".join(
            [
                f"# {p.get('name','')} · 商品短剧",
                "",
                f"- 形态：{a.get('form')}｜片长：{a.get('duration')}s｜商品角色：{a.get('role')}",
                f"- 生成时间：{doc.get('updated')}",
                "",
                "## 结构卡", "", doc.get("card", ""),
                "", "## 剧本", "", doc.get("script", ""),
                "", "## 分镜表", "", doc.get("storyboard", ""),
                "", "## 自检", "", doc.get("check", ""),
            ]
        ),
        media_type="text/markdown; charset=utf-8",
    )
# ===========================================================================
# D 组合成与音频（2026-11-06 第四批）—— 全部本地 ffmpeg，零生成费
#
# 出处：clipforge `api/project/[id]/compose/route.ts` / `bgm/route.ts` /
# `contact-sheet/route.ts` / `preview-gif/route.ts`；滤镜与参数见
# `services/drama_compose.py` 头部的逐行对照。
# 🩸 本组接口**不调用任何生成模型**；`/compose` 只是把已经出好的段拼成一条片。
# ===========================================================================

#: BGM 落盘位置：`backend/data/drama/bgm/<pid>/bgm.<ext>`（与 films 平级）
BGM_DIR = DATA / "bgm"


class ComposeIn(BaseModel):
    """合成设置。字段名与前端一一对应；全部有默认值，空 body 也能跑。"""

    transition: str = "direct_concat"
    render_preset: str = "standard"
    captions: bool = True
    caption_preset: str = "standard"
    bgm_volume: float | None = None
    bgm_duck: bool = True
    bgm_fade_out: float = 3.0
    bgm_intro_skip: float = 0.0
    end_card: bool = False
    end_card_text: str = ""
    end_card_seconds: float = 3.0
    end_card_image: str = ""
    end_card_qr_ratio: float = 0.34
    plan_hash: str = ""


def _compose_cfg(body: ComposeIn) -> dict:
    return {
        "transition": body.transition,
        "render_preset": body.render_preset,
        "captions": body.captions,
        "caption_preset": body.caption_preset,
        "bgm_volume": body.bgm_volume,
        "bgm_duck": body.bgm_duck,
        "bgm_fade_out": body.bgm_fade_out,
        "bgm_intro_skip": body.bgm_intro_skip,
        "end_card": {
            "enabled": body.end_card,
            "text": body.end_card_text,
            "seconds": body.end_card_seconds,
            "image": body.end_card_image,
            "qr_ratio": body.end_card_qr_ratio,
        },
    }


def _compose_state(doc: dict) -> dict:
    return dict(doc.get("compose") or {})


def _bgm_name(doc: dict) -> str:
    return str((_compose_state(doc).get("bgm") or {}).get("file") or "")


def _film_video(doc: dict):
    """取「最新一条能看的成片」：优先合成片，其次拼接整片，再次最后一段。"""
    pid = str(doc.get("id") or "")
    comp = _compose_state(doc)
    name = str((comp.get("outputs") or {}).get("mp4") or "")
    if name:
        p = FILM_DIR / pid / Path(name).name
        if p.exists():
            return p
    film = doc.get("film") or {}
    name = str(film.get("merged") or "")
    if name:
        p = FILM_DIR / pid / Path(name).name
        if p.exists():
            return p
    files = film.get("files") or {}
    segs = (film.get("plan") or {}).get("segments") or []
    for s in reversed(segs):
        rec = files.get(str(s.get("no"))) or {}
        if rec.get("name"):
            p = FILM_DIR / pid / Path(str(rec["name"])).name
            if p.exists():
                return p
    return None


@router.get("/compose/options")
def compose_options():
    """合成可选项一次给全（转场四档 / 渲染三档 / 字幕四档 + 默认值）。"""
    return ok({
        "transitions": drama_compose.transitions_public(),
        "renders": [dict(v) for v in drama_compose.RENDER_PRESETS.values()],
        "captions": drama_captions.public(),
        "defaults": {
            "transition": drama_compose.DEFAULT_TRANSITION,
            "render_preset": drama_compose.DEFAULT_RENDER_PRESET,
            "caption_preset": drama_captions.DEFAULT_ID,
            "bgm_volume": drama_audio.DEFAULT_BGM_VOLUME,
            "bgm_fade_out": drama_audio.DEFAULT_FADE_OUT,
            "end_card_seconds": 3.0,
            "end_card_qr_ratio": 0.34,
        },
    })


@router.post("/projects/{pid}/bgm")
async def upload_bgm(pid: str, file: UploadFile = File(...)):
    """上传背景音乐（D2）。mp3/wav/aac/m4a，≤20MB，落 `data/drama/bgm/<pid>/`。

    只存一份：换文件时删掉旧的（同名不同扩展都清），避免混音拿错曲。
    """
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    if not drama_audio.ext_ok(file.filename, file.content_type):
        return fail("只收 mp3 / wav / aac / m4a 音频")
    ext = Path(Path(file.filename or "bgm.mp3").name).suffix.lower() or ".mp3"
    out_dir = BGM_DIR / pid
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"bgm{ext}"
    size = 0
    try:
        with dest.open("wb") as fh:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > drama_audio.MAX_BYTES:
                    raise ValueError("音频超过 20MB")
                fh.write(chunk)
        if size == 0:
            raise ValueError("文件是空的")
    except Exception as e:  # noqa: BLE001
        dest.unlink(missing_ok=True)
        return fail(f"上传失败：{str(e)[:120]}")
    for old in out_dir.glob("bgm.*"):
        if old != dest:
            old.unlink(missing_ok=True)

    comp = _compose_state(doc)
    comp["bgm"] = {"file": dest.name, "bytes": size,
                   "volume": drama_audio.DEFAULT_BGM_VOLUME,
                   "duck": True,
                   "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    comp.pop("plan", None)  # 曲一换，旧计划作废
    doc["compose"] = comp
    _save(doc)
    return ok(doc)


@router.delete("/projects/{pid}/bgm")
def delete_bgm(pid: str):
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    out_dir = BGM_DIR / pid
    for old in out_dir.glob("bgm.*"):
        old.unlink(missing_ok=True)
    comp = _compose_state(doc)
    comp.pop("bgm", None)
    comp.pop("plan", None)
    doc["compose"] = comp
    _save(doc)
    return ok(doc)


@router.get("/projects/{pid}/bgm/file")
def bgm_file(pid: str):
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    name = _bgm_name(doc)
    p = BGM_DIR / pid / Path(name).name if name else None
    if not p or not p.exists():
        return fail("还没传 BGM")
    return FileResponse(p, filename=p.name)


@router.post("/projects/{pid}/compose/plan")
def compose_plan(pid: str, body: ComposeIn = ComposeIn()):
    """合成规划（**零费用、不编码**）：算时间轴 / 字幕条 / 切点 / 警告。

    和出片计划一样，界面看到的就是 `compose` 会照着做的那一版
    （`plan_hash` 在 `compose` 时重算核对，对不上不渲染）。
    """
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    p = drama_compose.plan(
        doc, film_dir=FILM_DIR / pid, config=_compose_cfg(body),
        bgm_file=_bgm_name(doc), end_card_image=body.end_card_image)
    comp = _compose_state(doc)
    comp["plan"] = p
    comp["options"] = _compose_cfg(body)
    doc["compose"] = comp
    _save(doc)
    return ok(doc)


@router.post("/projects/{pid}/compose")
def compose_run(pid: str, body: ComposeIn = ComposeIn()):
    """执行合成（**本地 ffmpeg，零生成费**），由使用者在界面上点。

    先按**现在的**文档重算一遍计划并核对 `plan_hash`：
    中间换过段/改过设置 → 直接中止，不产出与确认卡不一致的片子。
    """
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    fresh = drama_compose.plan(
        doc, film_dir=FILM_DIR / pid, config=_compose_cfg(body),
        bgm_file=_bgm_name(doc), end_card_image=body.end_card_image)
    if fresh.get("errors"):
        return fail("合成计划有硬问题，先解决：" + "；".join(fresh["errors"][:3]))
    if body.plan_hash and fresh.get("plan_hash") != body.plan_hash:
        return fail("计划和你看的那一版不一样了（片段或设置改过）—— "
                    "重新规划并确认后再合成；本次没有产出")

    font = drama_cover.resolve_font()
    prof = drama_compose.render_profile(
        (fresh.get("config") or {}).get("render_preset"))
    # 画布尺寸跟计划的画面比例走（`doc.film.ratio`，缺省 9:16）
    width, height = drama_compose.RESOLUTIONS[
        fresh.get("ratio") or "9:16"][prof["resolution"]]
    cap = fresh.get("caption") or {}
    ass_text = ""
    if cap.get("enabled") and cap.get("cues") and cap.get("karaoke"):
        ass_text = drama_captions.karaoke_ass(
            cap["cues"], font_name=drama_captions.font_name_for(font),
            width=width, height=height)

    out_dir = FILM_DIR / pid
    # 🩸 同一秒内连点两次不能写同一个文件（否则历史里两条指向同一个 mp4，
    # 后一次把前一次覆盖掉）；撞名就加 -2 / -3…
    stem = f"compose-{time.strftime('%Y%m%d-%H%M%S')}"
    out = out_dir / f"{stem}.mp4"
    n = 2
    while out.exists():
        out = out_dir / f"{stem}-{n}.mp4"
        n += 1
    try:
        drama_compose.render(fresh, out, ass_text=ass_text, font_path=font or "")
    except Exception as e:  # noqa: BLE001
        log.warning("[drama] compose 失败: %s", e)
        return fail(f"合成失败：{str(e)[:300]}")

    comp = _compose_state(doc)
    outputs = dict(comp.get("outputs") or {})
    outputs["mp4"] = out.name
    comp["plan"] = fresh
    comp["outputs"] = outputs
    comp["at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    # 合成历史：每次合成都是一个新时间戳文件（不覆盖旧的），这里记一条好回看。
    # 竞品 export 页的「历史成片」就是这一列（`export/page.tsx:522-550`）。
    hist = [h for h in (comp.get("history") or []) if isinstance(h, dict)]
    hist.insert(0, {
        "mp4": out.name,
        "at": comp["at"],
        "label": "常规合成",
        "seconds": fresh.get("total_seconds"),
        "ratio": fresh.get("ratio"),
        "resolution": prof.get("resolution"),
    })
    comp["history"] = hist[:20]
    doc["compose"] = comp
    _save(doc)
    return ok(doc)


@router.get("/projects/{pid}/compose/file")
def compose_file(pid: str, name: str = ""):
    """成片文件：不带 `name` 给最新一版；带 `name` 给历史里的某一版。

    🩸 `name` 只认 `compose-<8位日期>-<6位时间>.mp4` 这种本服务自己起的名字，
    并且只用 `Path(name).name` 取基名 —— 杜绝 `../` 之类的路径穿越。
    """
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    if name:
        base = Path(name).name
        if not re.fullmatch(r"compose-\d{8}-\d{6}(-\d+)?\.mp4", base):
            return fail("版本文件名不合法")
        p = FILM_DIR / pid / base
    else:
        cur = str((_compose_state(doc).get("outputs") or {}).get("mp4") or "")
        p = FILM_DIR / pid / Path(cur).name if cur else None
    if not p or not p.exists():
        return fail("还没合成")
    return FileResponse(p, media_type="video/mp4", filename=p.name)


# ---------- 变体矩阵（C15，竞品 `lib/variation-plan.ts`） ----------
class VariantPlanIn(BaseModel):
    count: int = 3
    seed: int = 1
    lock: dict = Field(default_factory=dict)


def _variants_plan(pid: str, body: VariantPlanIn) -> dict:
    doc = _load(pid)
    # BGM 是否可用只看**已登记**的那一条（上传时会写进 `doc["compose"]["bgm"]`）；
    # 光有文件没登记，合成链路也不会拿它当 BGM。
    has_bgm = bool(_bgm_name(doc))
    return drama_variants.build(count=body.count, seed=body.seed,
                                has_bgm=has_bgm, lock=body.lock)


@router.post("/projects/{pid}/variants/plan")
def variants_plan(pid: str, body: VariantPlanIn = VariantPlanIn()):
    """变体计划（不合成、不花钱）：每条换一组合成参数。"""
    try:
        plan = _variants_plan(pid, body)
    except KeyError:
        return fail("项目不存在")
    return ok(plan)


@router.post("/projects/{pid}/variants/render")
def variants_render(pid: str, body: VariantPlanIn = VariantPlanIn()):
    """按变体计划逐条合成（**本地 ffmpeg，零生成费**）。

    复用 `/compose` 的同一条渲染链路，只是换配置跑多遍；跑完把 `doc["compose"]`
    恢复成进来时的样子 —— 变体是旁支，不许顶掉主合成的那一版。
    """
    try:
        plan = _variants_plan(pid, body)
    except KeyError:
        return fail("项目不存在")
    before = (_load(pid).get("compose") or None)
    bgm_entry = (before or {}).get("bgm")
    rows = []
    for slot in plan["slots"]:
        cfg = slot["config"]
        # BGM 这一维靠「合成本次要不要挂曲子」实现：合成链路只认 doc 里登记的那条，
        # 所以按本条槽位临时挂上/摘掉，跑完再恢复（变体是旁支，不写回主状态）。
        cur = _compose_state(_load(pid))
        if cfg.get("bgm") and bgm_entry:
            cur["bgm"] = bgm_entry
        else:
            cur.pop("bgm", None)
        doc_tmp = _load(pid)
        doc_tmp["compose"] = cur
        _save(doc_tmp)
        r = compose_run(pid, ComposeIn(**{k: cfg[k] for k in
                                          ("transition", "render_preset", "captions",
                                           "caption_preset")}))
        if r.get("biz_code") != 0:
            rows.append({**slot, "error": str(r.get("msg") or "合成失败")})
            break
        doc = _load(pid)
        name = str(((doc.get("compose") or {}).get("outputs") or {}).get("mp4") or "")
        src = FILM_DIR / pid / Path(name).name if name else None
        if not src or not src.exists():
            rows.append({**slot, "error": "合成了但找不到产物"})
            break
        dst = src.with_name(f"variant-{slot['idx'] + 1}-{src.name}")
        src.rename(dst)
        rows.append({**slot, "file": dst.name, "at": time.strftime("%Y-%m-%d %H:%M:%S")})

    doc = _load(pid)
    if before is None:
        doc.pop("compose", None)
    else:
        doc["compose"] = before
    doc["variants"] = {"seed": plan["seed"], "count": plan["count"],
                       "at": time.strftime("%Y-%m-%d %H:%M:%S"), "slots": rows}
    _save(doc)
    if any(x.get("error") for x in rows):
        return fail("；".join(str(x["error"]) for x in rows if x.get("error")))
    return ok({"project": doc, "variants": rows})


@router.get("/projects/{pid}/variants/{idx}/file")
def variants_file(pid: str, idx: int):
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    hit = next((x for x in (doc.get("variants") or {}).get("slots") or []
                if int(x.get("idx") or 0) == idx - 1), None)
    if not hit or not hit.get("file"):
        return fail("这一条变体还没合成")
    p = FILM_DIR / pid / Path(hit["file"]).name
    if not p.exists():
        return fail("变体成片不见了")
    return FileResponse(p, media_type="video/mp4", filename=p.name)


@router.post("/projects/{pid}/contact-sheet")
def contact_sheet(pid: str, mode: str = "smart", frames: int = 8,
                  thumb_width: int = 180, wave_height: int = 120,
                  scene_threshold: float = 0.22, proxy: bool = False):
    """成片速览（E5）：按真实切点取样 + 波形 + 时间码；可选审片小样。

    切点来源 = `compose.plan.boundaries`（同一条链算出来的权威值），
    不是靠逐帧猜场景 —— 交叉淡化在逐帧检测里本来就看不出来。
    """
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    video = _film_video(doc)
    if not video:
        return fail("还没有成片，先出片/合成")
    known = [float(x) for x in ((_compose_state(doc).get("plan") or {})
                                .get("boundaries") or []) if isinstance(x, (int, float))]
    out_dir = FILM_DIR / pid
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = out_dir / f"sheet-{stamp}.png"
    try:
        result = drama_contact_sheet.generate(
            video, out, frames=frames, thumb_width=thumb_width,
            wave_height=wave_height, mode=("even" if mode == "even" else "smart"),
            scene_threshold=scene_threshold, known_cuts=known)
    except Exception as e:  # noqa: BLE001
        log.warning("[drama] 速览失败: %s", e)
        return fail(f"速览生成失败：{str(e)[:200]}")

    comp = _compose_state(doc)
    outputs = dict(comp.get("outputs") or {})
    outputs["sheet"] = out.name
    if proxy:
        p = out_dir / f"proxy-{stamp}.mp4"
        try:
            drama_contact_sheet.generate_proxy(video, p)
            outputs["proxy"] = p.name
        except Exception as e:  # noqa: BLE001
            log.warning("[drama] 审片小样失败: %s", e)
    comp["outputs"] = outputs
    comp["sheet"] = {**result, "source": video.name,
                     "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    doc["compose"] = comp
    _save(doc)
    return ok(doc)


@router.get("/projects/{pid}/contact-sheet/file")
def contact_sheet_file(pid: str):
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    name = str((_compose_state(doc).get("outputs") or {}).get("sheet") or "")
    p = FILM_DIR / pid / Path(name).name if name else None
    if not p or not p.exists():
        return fail("还没生成速览")
    return FileResponse(p, media_type="image/png", filename=p.name)


@router.post("/projects/{pid}/preview-gif")
def preview_gif(pid: str, start: float = 0.0, duration: float = 4.0,
                width: int = 360, fps: int = 12):
    """预览 GIF（E6）：成片的一小段 → 128 色循环 GIF（本地，零费用）。"""
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    video = _film_video(doc)
    if not video:
        return fail("还没有成片，先出片/合成")
    out = FILM_DIR / pid / f"preview-{time.strftime('%Y%m%d-%H%M%S')}.gif"
    try:
        drama_gif.generate(video, out, start=start, duration=duration,
                           width=width, fps=fps)
    except Exception as e:  # noqa: BLE001
        log.warning("[drama] GIF 失败: %s", e)
        return fail(f"GIF 生成失败：{str(e)[:200]}")
    comp = _compose_state(doc)
    outputs = dict(comp.get("outputs") or {})
    outputs["gif"] = out.name
    comp["outputs"] = outputs
    doc["compose"] = comp
    _save(doc)
    return ok(doc)


@router.get("/projects/{pid}/preview-gif/file")
def preview_gif_file(pid: str):
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    name = str((_compose_state(doc).get("outputs") or {}).get("gif") or "")
    p = FILM_DIR / pid / Path(name).name if name else None
    if not p or not p.exists():
        return fail("还没生成 GIF")
    return FileResponse(p, media_type="image/gif", filename=p.name)


# ===========================================================================
# E 组 · 发行物料（发布文案 / 图文卡 / 二维码 / 多平台导出 / 原生感 / 母版）
# ---------------------------------------------------------------------------
# 全部本地 ffmpeg（发布文案除外，模型版要一次调用），**零生成费**。
# 出处：clipforge `src/lib/publish-pack.ts` / `shop-qr.ts` / `platform-specs.ts` /
# `platform-export.ts` / `native-feel.ts` / `video-mastering.ts`（逐字对照见各服务头）。
# ===========================================================================

MEDIA_DIR = DATA / "media"


def _media(pid: str) -> Path:
    d = MEDIA_DIR / pid
    d.mkdir(parents=True, exist_ok=True)
    return d


def _materials(doc: dict) -> dict:
    return dict(doc.get("materials") or {})


def _stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def _save_material(doc: dict, key: str, value: dict) -> dict:
    mats = _materials(doc)
    mats[key] = {**value, "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    doc["materials"] = mats
    _save(doc)
    return doc


def _material_file(doc: dict, key: str, field: str = "file") -> Path | None:
    name = str((_materials(doc).get(key) or {}).get(field) or "")
    if not name:
        return None
    p = _media(str(doc.get("id"))) / Path(name).name
    return p if p.exists() else None


class ExportIn(BaseModel):
    platform: str = "douyin"
    framing: dict | None = None
    preview: bool = False
    preview_time: float = 0.0


class QrIn(BaseModel):
    url: str = ""
    platform: str = ""
    size: int = 512
    #: 是否打算把这张码**烧进成片** —— 竞品把闸门放在 end-card 路线，
    #: 我们的片尾卡在合成里，所以同一个闸门放在「有烧录意图」这个开关上。
    burn: bool = False
    force: bool = False


class CarouselIn(BaseModel):
    width: int = 1080
    height: int = 1440
    theme: str = "night"


class NativeIn(BaseModel):
    strength: str = "subtle"
    seed: int = 0
    grain: bool = True
    vignette: bool = False
    halation: bool = False
    phone_compress: bool = False


class MasterIn(BaseModel):
    action: str = "analyze"
    normalize_audio: bool = False
    deflicker: bool = False


class PublishIn(BaseModel):
    platform: str = ""
    locale: str = "zh"
    shop_url: str = ""
    affiliate_code: str = ""


class PublishLlmIn(PublishIn):
    pass


@router.get("/platforms")
def platforms():
    """平台规格 + 二维码政策 + 构图三档（E4/E3 的选项表）。"""
    return ok({
        "platforms": drama_platform.platforms_public(),
        "framing_modes": [
            {"id": "blur", "label": "模糊填充", "desc": "比例不符时两侧虚化铺底（默认）"},
            {"id": "fit", "label": "完整适配", "desc": "整幅缩进画面，两侧黑边"},
            {"id": "crop", "label": "裁切填满", "desc": "裁掉多余部分铺满，可定位"},
        ],
        "default_framing": dict(drama_platform.DEFAULT_FRAMING),
        "native_strengths": [
            {"id": "subtle", "label": "轻微", "desc": "几乎看不出的手持漂移"},
            {"id": "medium", "label": "中等", "desc": "明显手持感"},
            {"id": "strong", "label": "强", "desc": "边走边拍（带轻微旋转）"},
        ],
        "card_themes": list(drama_cards.CARD_THEMES.keys()),
        "max_cards": drama_cards.MAX_CARDS,
    })


# ---------------------------------------------------------------- 多平台导出
@router.post("/projects/{pid}/export-platform")
def export_platform(pid: str, body: ExportIn):
    """按平台比例/码率重构图（E4）。preview=true 只出单帧预览，不产片。"""
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    spec = drama_platform.get_platform_spec(body.platform)
    if not spec:
        return fail("不支持的平台")
    try:
        framing = drama_platform.parse_framing(body.framing)
    except drama_platform.FramingError as e:
        return fail(str(e))
    video = _film_video(doc)
    if not video:
        return fail("还没有成片，请先出片/合成")
    try:
        if body.preview:
            frame = drama_platform.preview_frame(video, spec, framing,
                                                 at=body.preview_time)
            return ok({"preview": frame, "platform": body.platform,
                       "framing": framing, "size": f"{spec['w']}x{spec['h']}"})
        name = f"export-{body.platform}-{_stamp()}.mp4"
        out = _media(pid) / name
        report = drama_platform.render_export(video, out, spec, framing)
    except Exception as e:  # noqa: BLE001
        log.warning("[drama] 平台导出失败: %s", e)
        return fail(f"导出失败：{str(e)[:200]}")
    doc = _save_material(doc, "export", {
        "file": name, "platform": body.platform,
        "platform_name": spec["name"], "framing": framing, "report": report,
    })
    return ok({"project": doc, "report": report, "file": name})


@router.get("/projects/{pid}/export-platform/file")
def export_platform_file(pid: str):
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    p = _material_file(doc, "export")
    if not p:
        return fail("还没有导出过多平台版本")
    return FileResponse(p, media_type="video/mp4", filename=p.name)


# ---------------------------------------------------------------- 二维码
@router.post("/projects/{pid}/shop-qr")
def shop_qr(pid: str, body: QrIn):
    """店铺二维码（E3）。返回 UTM 后的链接 + 平台政策；burn=true 时抖音默认拒。"""
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    # 没传就用建项目时粘的那条（提示语一直这么写，但从来没真兜底过）
    url = (body.url or str((doc.get("product") or {}).get("url") or "")).strip()
    if not url:
        return fail("请先填商品链接（或用项目里的商品链接）")
    policy = drama_platform.get_off_site_qr_policy(body.platform or None)
    if body.burn and policy["level"] == "block" and not body.force:
        return fail(f"{policy['zh']}（确认自担风险可传 force=true）")
    name = f"qr-{_stamp()}.png"
    try:
        link = drama_qr.generate(url, _media(pid) / name,
                                 platform=body.platform or None, size=body.size)
    except drama_qr.QrError as e:
        return fail(str(e))
    except Exception as e:  # noqa: BLE001
        log.warning("[drama] 二维码生成失败: %s", e)
        return fail(f"二维码生成失败：{str(e)[:200]}")
    doc = _save_material(doc, "qr", {
        "file": name, "link": link, "platform": body.platform or "",
        "policy": policy,
    })
    return ok({"project": doc, "file": name, "link": link, "policy": policy})


@router.get("/projects/{pid}/shop-qr/file")
def shop_qr_file(pid: str):
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    p = _material_file(doc, "qr")
    if not p:
        return fail("还没有生成过二维码")
    return FileResponse(p, media_type="image/png", filename=p.name)


# ---------------------------------------------------------------- 图文卡
@router.post("/projects/{pid}/carousel")
def carousel(pid: str, body: CarouselIn):
    """小红书图文卡（E2）：标题卡 + 每镜台词一卡。读的是当前分镜台词。"""
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    shots = ((doc.get("storyboard_json") or {}).get("shots") or [])
    lines = [str(s.get("dialogue") or "") for s in shots]
    if not any(x.strip() for x in lines):
        return fail("分镜里没有台词，生成不了卡片")
    title = str((doc.get("product") or {}).get("name") or doc.get("name") or "图文")
    prefix = f"card-{_stamp()}"
    try:
        paths = drama_cards.generate_carousel(
            title=title, lines=lines, out_dir=_media(pid), prefix=prefix,
            width=body.width, height=body.height, theme=body.theme)
    except Exception as e:  # noqa: BLE001
        log.warning("[drama] 图文卡生成失败: %s", e)
        return fail(f"卡片生成失败：{str(e)[:200]}")
    names = [p.name for p in paths]
    doc = _save_material(doc, "cards", {
        "files": names, "theme": body.theme,
        "width": body.width, "height": body.height,
    })
    return ok({"project": doc, "files": names, "count": len(names)})


@router.get("/projects/{pid}/carousel/file/{idx}")
def carousel_file(pid: str, idx: int):
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    names = (_materials(doc).get("cards") or {}).get("files") or []
    if idx < 0 or idx >= len(names):
        return fail("这张卡不在列表里")
    p = _media(pid) / Path(names[idx]).name
    if not p.exists():
        return fail("卡片文件不见了")
    return FileResponse(p, media_type="image/png", filename=p.name)


# ---------------------------------------------------------------- 原生感
@router.post("/projects/{pid}/native-feel")
def native_feel(pid: str, body: NativeIn):
    """原生感后期（E7）：手持漂移 + 颗粒 + 去精致调色。只重编码画面，音频直通。"""
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    video = _film_video(doc)
    if not video:
        return fail("还没有成片，请先出片/合成")
    name = f"native-{_stamp()}.mp4"
    try:
        drama_native_feel.apply(
            video, _media(pid) / name, strength=body.strength, seed=body.seed,
            grain=body.grain, vignette=body.vignette, halation=body.halation,
            phone_compress=body.phone_compress)
    except Exception as e:  # noqa: BLE001
        log.warning("[drama] 原生感失败: %s", e)
        return fail(f"原生感处理失败：{str(e)[:200]}")
    doc = _save_material(doc, "native", {
        "file": name, "strength": body.strength, "seed": body.seed,
        "grain": body.grain, "vignette": body.vignette,
        "halation": body.halation, "phone_compress": body.phone_compress,
    })
    return ok(doc)


@router.get("/projects/{pid}/native-feel/file")
def native_feel_file(pid: str):
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    p = _material_file(doc, "native")
    if not p:
        return fail("还没有做过原生感处理")
    return FileResponse(p, media_type="video/mp4", filename=p.name)


# ---------------------------------------------------------------- 母版精修
@router.post("/projects/{pid}/mastering")
def mastering(pid: str, body: MasterIn):
    """母版处理（E8）。action=analyze 只体检；action=render 才产新片（源片不动）。"""
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    video = _film_video(doc)
    if not video:
        return fail("还没有成片，请先出片/合成")
    try:
        analysis = drama_mastering.analyze(video)
    except Exception as e:  # noqa: BLE001
        log.warning("[drama] 母版分析失败: %s", e)
        return fail(f"体检失败：{str(e)[:200]}")
    if body.action != "render":
        return ok({"analysis": analysis, "options": {
            "normalize_audio": analysis["recommendations"]["normalize_audio"],
            "deflicker": False}})
    normalize = bool(body.normalize_audio)
    if normalize and not (analysis["has_audio"] and analysis["loudness"]):
        normalize = False
    if not normalize and not body.deflicker:
        return fail("当前成片没有可执行的所选精修项")
    name = f"master-{_stamp()}.mp4"
    try:
        drama_mastering.render(video, _media(pid) / name, analysis,
                               normalize_audio=normalize, deflicker=body.deflicker,
                               content_id=pid)
    except Exception as e:  # noqa: BLE001
        log.warning("[drama] 母版精修失败: %s", e)
        return fail(f"精修失败：{str(e)[:200]}")
    options = {"normalize_audio": normalize, "deflicker": body.deflicker}
    doc = _save_material(doc, "master", {
        "file": name, "analysis": analysis, "options": options})
    return ok({"project": doc, "analysis": analysis, "options": options})


@router.get("/projects/{pid}/mastering/file")
def mastering_file(pid: str):
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    p = _material_file(doc, "master")
    if not p:
        return fail("还没有精修过")
    return FileResponse(p, media_type="video/mp4", filename=p.name)


# ---------------------------------------------------------------- 发布文案
def _publish_inputs(doc: dict, body: PublishIn) -> dict:
    product = doc.get("product") or {}
    answers = doc.get("answers") or {}
    points = product.get("points") or []
    if isinstance(points, list) and points:
        selling = "；".join(str(x) for x in points)
    else:
        selling = str(product.get("facts") or "")
    return {
        "product_name": str(product.get("name") or doc.get("name") or "").strip(),
        "category": str(product.get("category") or ""),
        "selling_points": selling,
        "platform": body.platform or str(product.get("platform") or answers.get("platform") or ""),
        "locale": "en" if body.locale == "en" else "zh",
        # 没单独传店铺链接就用建项目时粘的那条（抓不到商品信息 ≠ 这条链接没用）
        "shop_url": body.shop_url or str(product.get("url") or "").strip(),
        "affiliate_code": body.affiliate_code,
    }


@router.post("/projects/{pid}/publish-pack")
def publish_pack(pid: str, body: PublishIn):
    """发布文案模板版（E10 · 零费用、确定性）。商品名都没有就拒，不糊弄。"""
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    args = _publish_inputs(doc, body)
    if not args["product_name"]:
        return fail("项目还没有商品名")
    pack = drama_publish.build_publish_pack(**args)
    doc["publish"] = {"pack": pack, "source": "template",
                      "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    _save(doc)
    return ok({"project": doc, "pack": pack, "source": "template"})


@router.post("/projects/{pid}/publish")
def publish_llm(pid: str, body: PublishLlmIn):
    """发布文案模型版（E10 · 花一次调用）。模型吐的 JSON 由 sanitize 夹取。"""
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    args = _publish_inputs(doc, body)
    if not args["product_name"]:
        return fail("项目还没有商品名")
    prompt = drama_publish.build_publish_prompt(
        product_name=args["product_name"], category=args["category"],
        product_description=args["selling_points"], platform=args["platform"],
        locale=args["locale"])
    try:
        text = _chat(prompt, temperature=0.9,
                     system="你只输出 JSON，不输出任何解释。")
    except DramaError as e:
        return fail(str(e))
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return fail("AI 未返回有效的发布文案，请重试")
    try:
        parsed = json.loads(text[start:end + 1])
    except Exception as e:  # noqa: BLE001
        log.warning("[drama] 发布文案解析失败: %s", e)
        return fail("AI 返回的文案不是合法 JSON，请重试")
    pack = drama_publish.sanitize_llm_pack(
        parsed, product_name=args["product_name"], category=args["category"],
        selling_points=args["selling_points"], locale=args["locale"])
    if args["shop_url"]:
        link = drama_qr.build_shop_link(args["shop_url"], platform=args["platform"] or None,
                                        affiliate_code=args["affiliate_code"])
        if link:
            pack["shop_link"] = link
    doc["publish"] = {"pack": pack, "source": "llm",
                      "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    _save(doc)
    return ok({"project": doc, "pack": pack, "source": "llm"})


# ---------------------------------------------------------------- 素材库（B2 / B1）

#: 素材池根目录：`data/drama/materials/<pid>/`（与商品图 `images/<pid>/` 同构）
MATERIALS_DIR = DATA / "materials"
_MAT_MIME = {
    ".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
}


def _mat_dir(pid: str) -> Path:
    return MATERIALS_DIR / pid


def _mat_public(row: dict, pid: str) -> dict:
    """前端拿的形态：加一个取文件的 url（竞品 `route.ts:25-28`）。"""
    out = dict(row)
    out["url"] = f"/api/drama/projects/{pid}/materials/{row['name']}/file"
    return out


def _mat_error(code: str) -> dict:
    """错误码 → 人话（口径照 `route.ts:39-102`）"""
    return fail({
        "MATERIAL_SIZE": "文件不能为空或超过 80MB",
        "UNSUPPORTED_MATERIAL": "仅支持 MP4、WebM、MOV、M4V、JPG、PNG、WebP",
        "INVALID_MATERIAL": "文件无法读取，或真实格式与扩展名不一致",
        "INCOMPLETE_MATERIAL": "文件未传完，请重试",
        "INVALID_TAGS": "最多 12 个标签，每个不超过 32 个字符",
        "INVALID_NAME": "请输入不含路径的素材名称，最长 240 个字符",
        "MATERIAL_NOT_FOUND": "素材不存在",
    }.get(code, "素材操作失败，请重试"))


@router.get("/projects/{pid}/materials")
def list_materials(pid: str):
    """池里全部素材（按更新时间倒序）。"""
    try:
        _load(pid)
    except KeyError:
        return fail("项目不存在")
    rows = [_mat_public(r, pid) for r in drama_materials.list_materials(_mat_dir(pid))]
    return ok({"materials": rows, "accept": drama_materials.ACCEPT,
               "max_bytes": drama_materials.MAX_BYTES,
               "max_files": drama_materials.MAX_FILES})


@router.post("/projects/{pid}/materials")
async def upload_material(pid: str, file: UploadFile = File(...), tags: str = Form("")):
    """收一个素材：内容寻址落盘 + 真格式校验 + 重复去重。

    `tags` 用逗号分隔（可选）；不带就空着，后面用 PATCH 改。
    """
    try:
        _load(pid)
    except KeyError:
        return fail("项目不存在")
    parsed = [t for t in (tags or "").split(",") if t.strip()] if tags else []
    try:
        result = drama_materials.store(
            _mat_dir(pid), file.filename or "material",
            file.file, getattr(file, "size", None))
    except drama_materials.MaterialError as e:
        return _mat_error(e.code)
    except Exception as e:  # noqa: BLE001
        log.warning("[drama] 素材上传失败: %s", e)
        return _mat_error("")
    if parsed:
        try:
            result["material"] = drama_materials.update_meta(
                _mat_dir(pid), result["material"]["name"], tags=parsed)
        except drama_materials.MaterialError as e:
            return _mat_error(e.code)
    return ok({"material": _mat_public(result["material"], pid),
               "duplicate": result["duplicate"]})


class MaterialMetaIn(BaseModel):
    original_name: str | None = None
    tags: list[str] | None = None
    author: str | None = None
    license: str | None = None
    source_url: str | None = None
    provider: str | None = None


@router.patch("/projects/{pid}/materials/{name}")
def patch_material(pid: str, name: str, body: MaterialMetaIn):
    """改原名 / 标签 / 出处（出处是给授权清单用的）。"""
    try:
        _load(pid)
    except KeyError:
        return fail("项目不存在")
    provenance = {}
    for key in ("author", "license", "source_url", "provider"):
        v = getattr(body, key)
        if v is not None:
            provenance[key] = v
    try:
        row = drama_materials.update_meta(
            _mat_dir(pid), name, original_name=body.original_name,
            tags=body.tags, provenance=provenance or None)
    except drama_materials.MaterialError as e:
        return _mat_error(e.code)
    return ok({"material": _mat_public(row, pid)})


@router.delete("/projects/{pid}/materials/{name}")
def delete_material(pid: str, name: str):
    try:
        _load(pid)
    except KeyError:
        return fail("项目不存在")
    if not drama_materials.delete(_mat_dir(pid), name):
        return _mat_error("MATERIAL_NOT_FOUND")
    return ok({"deleted": name})


@router.get("/projects/{pid}/materials/{name}/file")
def material_file(pid: str, name: str):
    """取素材原文件。只认池里的合法素材名，别的一律 404。"""
    if not drama_materials.is_material_name(name):
        raise HTTPException(status_code=404, detail="not found")
    p = _mat_dir(pid) / name
    if not p.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(p, media_type=_MAT_MIME.get(p.suffix.lower(), "application/octet-stream"),
                        filename=name)


# ---------------------------------------------------------------- 免版权素材搜索（B3）
# 竞品 `src/app/api/stock/search/route.ts:33-196`：检索 → 可选下载落库。
# 我们：候选先回前端预览；点「加入素材库」时按 source+media_type+id 从短期缓存取回
# （不让前端传下载地址 —— 防 SSRF，也防作者/许可被客户端篡改进授权清单）。


class StockSearchIn(BaseModel):
    query: str = ""
    source: str = "all"
    media_type: str = "video"
    orientation: str = "portrait"
    per_page: int = 10
    min_sec: float | None = None
    max_sec: float | None = None


class StockImportIn(BaseModel):
    source: str
    media_type: str
    id: str


@router.get("/stock/sources")
def stock_sources():
    """能用的素材源 + 哪些要 Key（前端渲染源选择用）。"""
    return ok({"sources": drama_stock.list_sources()})


@router.post("/projects/{pid}/stock/search")
def stock_search(pid: str, body: StockSearchIn):
    """多源检索（不下载、不花钱）。带项目 id 时「本地素材」也参与。"""
    try:
        _load(pid)
    except KeyError:
        return fail("项目不存在")
    media_type = body.media_type if body.media_type in drama_stock.MEDIA_TYPES else "video"
    orientation = body.orientation if body.orientation in drama_stock.ORIENTATIONS else "portrait"
    per_page = max(1, min(30, int(body.per_page or 10)))
    query = (body.query or "").strip()
    if not query:
        return fail("请输入检索词（英文召回更好）")
    source = (body.source or "all").strip()
    mat_dir = _mat_dir(pid)

    if source == "all":
        res = drama_stock.search_all(query, media_type=media_type, per_page=per_page,
                                     orientation=orientation, min_sec=body.min_sec,
                                     max_sec=body.max_sec, mat_dir=mat_dir)
        return ok({"candidates": res["candidates"],
                   "skipped_sources": res["skipped_sources"],
                   "errored_sources": res["errored_sources"],
                   "sources": drama_stock.list_sources()})
    if source not in {s["id"] for s in drama_stock.SOURCES}:
        return fail("未知素材源")
    try:
        candidates = drama_stock.search_source(
            source, query, media_type=media_type, per_page=per_page,
            orientation=orientation, min_sec=body.min_sec, max_sec=body.max_sec,
            mat_dir=mat_dir)
    except drama_stock.StockError as e:
        return fail(str(e))
    drama_stock.remember(candidates)
    return ok({"candidates": candidates, "skipped_sources": [], "errored_sources": [],
               "sources": drama_stock.list_sources()})


_STOCK_AUDIO_OK = {".mp3", ".wav", ".aac", ".m4a"}


@router.post("/projects/{pid}/stock/import")
def stock_import(pid: str, body: StockImportIn):
    """把搜到的素材下载进来：图/视频进素材库（带出处），音频进 BGM 位（带署名）。"""
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    media_type = body.media_type if body.media_type in drama_stock.MEDIA_TYPES else ""
    if not media_type:
        return fail("未知媒体类型")
    cand = drama_stock.recall(body.source, media_type, str(body.id))
    if not cand:
        return fail("这条素材的候选已过期，请重新搜索后再选（候选只留 10 分钟）")

    pid_str = str(doc.get("id") or pid)
    mat_dir = _mat_dir(pid_str)

    if media_type != "audio":
        # 图 / 视频：下载 + 校验 + 内容寻址入库（与自动配画面共用同一条路）
        try:
            row, duplicate = drama_stock_fill.store_candidate(mat_dir, cand)
        except drama_materials.MaterialError as e:
            return _mat_error(e.code)
        except drama_stock.StockError as e:
            return fail(str(e))
        except Exception as e:  # noqa: BLE001
            log.warning("[drama] 素材导入失败: %s", e)
            return fail(f"素材导入失败：{str(e)[:120]}")
        return ok({"kind": "material", "material": _mat_public(row, pid_str),
                   "duplicate": duplicate})

    incoming = mat_dir / ".incoming"
    base = f"{drama_stock._safe_base(cand.get('source') or 'stock')}-{drama_stock._safe_base(cand.get('id') or '')}"
    try:
        path, size = drama_stock.download(cand, incoming, base)
    except drama_stock.StockError as e:
        return fail(str(e))

    title = re.sub(r"[\\/]", "-", str(cand.get("title") or "").strip())[:120] or base
    try:
        if size > drama_audio.MAX_BYTES:
            return fail("这段音频超过 20MB，不能当 BGM")
        out_dir = BGM_DIR / pid_str
        out_dir.mkdir(parents=True, exist_ok=True)
        ext = path.suffix.lower()
        if ext in _STOCK_AUDIO_OK:
            dest = out_dir / f"bgm{ext}"
            os.replace(path, dest)
        else:
            dest = out_dir / "bgm.mp3"
            drama_stock.transcode_audio(path, dest)
        for old in out_dir.glob("bgm.*"):
            if old != dest:
                old.unlink(missing_ok=True)
        comp = _compose_state(doc)
        comp["bgm"] = {
            "file": dest.name, "bytes": dest.stat().st_size,
            "volume": drama_audio.DEFAULT_BGM_VOLUME, "duck": True,
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "title": title,
            "credit": {"author": str(cand.get("author") or "")[:240],
                       "license": str(cand.get("license") or "")[:240],
                       "source_url": str(cand.get("page_url") or "")[:240]},
        }
        comp.pop("plan", None)  # 曲一换，旧计划作废
        doc["compose"] = comp
        _save(doc)
        return ok({"kind": "bgm", "bgm": comp["bgm"], "project": doc})
    except drama_stock.StockError as e:
        return fail(str(e))
    except Exception as e:  # noqa: BLE001
        log.warning("[drama] 音频导入失败: %s", e)
        return fail(f"音频导入失败：{str(e)[:120]}")
    finally:
        path.unlink(missing_ok=True)
        try:
            incoming.rmdir()  # 下载暂存目录用完就收（非空就留着，下一单继续用）
        except OSError:
            pass


class StockFillIn(BaseModel):
    media_type: str = "image"      # image = 参考画面（默认）；video = 当这一镜的画面（段数会变多）
    source: str = "all"
    force: bool = False            # 已配过的镜头也重配
    per_page: int = 8
    allow_universal: bool = False  # 通用兜底词搜到的也绑（默认只报告）
    max_shots: int = 0             # 只配前 N 镜（调试/省钱用）


@router.post("/projects/{pid}/stock/auto-fill")
def stock_auto_fill(pid: str, body: StockFillIn = StockFillIn()):
    """逐镜自动配画面：联网搜库 → 降级阶梯 → 下载入库 → 绑定。

    默认配**图片参考画面**（不改出片段数）；`media_type="video"` 才配实拍画面。
    """
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    shots = ((doc.get("storyboard_json") or {}).get("shots") or [])
    if not shots:
        return fail("还没有分镜，先出分镜再自动配画面")
    media_type = body.media_type if body.media_type in ("image", "video") else ""
    if not media_type:
        return fail("media_type 只能是 image 或 video")
    try:
        result = drama_stock_fill.auto_fill(
            doc, _mat_dir(str(doc.get("id") or pid)),
            media_type=media_type, source=body.source, force=bool(body.force),
            per_page=max(1, min(30, int(body.per_page or 8))),
            allow_universal=bool(body.allow_universal),
            max_shots=max(0, int(body.max_shots or 0)))
    except Exception as e:  # noqa: BLE001
        log.warning("[drama] 自动配画面失败: %s", e)
        return fail(f"自动配画面失败：{str(e)[:120]}")
    if result["filled"]:
        _save(doc)
    return ok({**result, "project": doc})


# ---------------------------------------------------------------- 授权清单（B5）

class BgmCreditIn(BaseModel):
    author: str = ""
    license: str = ""
    source_url: str = ""


@router.post("/projects/{pid}/bgm/credit")
def set_bgm_credit(pid: str, body: BgmCreditIn):
    """登记 BGM 出处（贴进去的曲子要能证明可商用）。"""
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    comp = _compose_state(doc)
    bgm = comp.get("bgm") or {}
    if not bgm.get("file"):
        return fail("还没有 BGM，先传一首")
    bgm["credit"] = {"author": body.author.strip(), "license": body.license.strip(),
                     "source_url": body.source_url.strip()}
    comp["bgm"] = bgm
    doc["compose"] = comp
    _save(doc)
    return ok(doc)


def _credits_manifest(doc: dict) -> dict:
    """素材库 + BGM + AI 出片段 → 授权清单（发布门禁与导出共用同一份）。"""
    pid = str(doc.get("id") or "")
    assets: list[dict] = []
    for row in drama_materials.list_materials(_mat_dir(pid)):
        declared = any(row.get(k) for k in ("license", "author", "source_url"))
        assets.append({
            "shot_id": None,
            "type": "stock" if declared else "own",
            "name": row["name"],
            "provider": row.get("provider") or "local",
            "author": row.get("author") or "",
            "license": row.get("license") or "",
            "source_url": row.get("source_url") or "",
        })
    plan = (doc.get("film") or {}).get("plan") or {}
    model = str((doc.get("film") or {}).get("model") or "")
    for seg in plan.get("segments") or []:
        assets.append({"shot_id": int(seg.get("no") or 0) - 1, "type": "ai",
                       "name": f"segment-{seg.get('no')}.mp4", "provider": model})
    bgm = (_compose_state(doc).get("bgm") or {})
    bgm_credit = bgm.get("credit") or {}
    declared = any(str(bgm_credit.get(k) or "").strip()
                   for k in ("author", "license", "source_url"))
    # 🩸 与竞品不同：我们的 BGM 是**使用者自己传的文件**（竞品是 stock 曲库下载，带 sidecar 出处）。
    # 没申报出处 = 自有音频，判 ok；只有申报了（比如从 CC 曲库下的）才按许可分级。
    bgm_arg = None
    if bgm.get("file"):
        if declared:
            bgm_arg = {"author": bgm_credit.get("author"), "license": bgm_credit.get("license"),
                       "source_url": bgm_credit.get("source_url")}
        else:
            assets.append({"shot_id": -1, "type": "own", "name": str(bgm.get("file") or "bgm"),
                           "provider": "local"})
    return drama_credits.build_manifest(
        str(doc.get("name") or doc.get("id") or ""), assets, bgm=bgm_arg)


@router.get("/projects/{pid}/credits")
def get_credits(pid: str, format: str = "json"):
    """授权清单：素材库 + BGM + AI 出片段。

    `format=md` 直接给可复制的 Markdown 报告（投流审核/归档用）。
    """
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    manifest = _credits_manifest(doc)
    if str(format).lower() in ("md", "markdown"):
        return PlainTextResponse(drama_credits.render_markdown(manifest),
                                 media_type="text/markdown; charset=utf-8")
    return ok({"manifest": manifest, "markdown": drama_credits.render_markdown(manifest)})


# ---------------------------------------------------------------- B4 每镜参考画面
# 能力表 B4「自动配画面」。竞品把素材**当画面**塞进分镜（`stock-fill/route.ts`）；
# 我们的画面是 AI 生成的，所以对齐成**某镜的参考画面**：素材只锁场景与陈设，
# 人脸仍以人物参考图为准（提示词里的措辞在 `drama_film.build_prompt`，此处不复制）。

def _shot_ids(doc: dict) -> set[int]:
    """分镜里实际存在的镜头 id（口径同 `drama_film._norm`）。"""
    out: set[int] = set()
    for i, s in enumerate(((doc.get("storyboard_json") or {}).get("shots") or []), 1):
        if not isinstance(s, dict):
            continue
        try:
            out.add(int(s.get("id") or i))
        except (TypeError, ValueError):
            out.add(i)
    return out


def _shot_mat_items(doc: dict) -> list[dict]:
    """绑定表 + 原文名 + 是否还在素材库（前端直接用）。"""
    pid = str(doc.get("id") or "")
    lib = {r["name"]: r for r in drama_materials.list_materials(_mat_dir(pid))}
    items = []
    for sid, name in sorted(drama_film.shot_materials(doc).items()):
        row = lib.get(name) or {}
        items.append({
            "shot_id": sid,
            "material": name,
            "original_name": row.get("original_name") or name,
            "url": f"/api/drama/projects/{pid}/materials/{name}/file",
            "missing": not bool(row),
        })
    return items


def _shot_mat_images(doc: dict) -> list[dict]:
    """可以当参考画面的素材：只有图片（视频素材走不了参考图通道）。"""
    pid = str(doc.get("id") or "")
    return [_mat_public(r, pid) for r in drama_materials.list_materials(_mat_dir(pid))
            if r.get("media_type") == "image"]


@router.get("/projects/{pid}/shot-materials")
def get_shot_materials(pid: str):
    """每镜参考画面：已绑的 + 可选图片。"""
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    return ok({"items": _shot_mat_items(doc), "images": _shot_mat_images(doc)})


class ShotMatIn(BaseModel):
    shot_id: int
    material: str


class ShotMatsIn(BaseModel):
    items: list[ShotMatIn] = []


@router.put("/projects/{pid}/shot-materials")
def put_shot_materials(pid: str, body: ShotMatsIn):
    """整表保存：前端删一条 = 提交时不含它。一镜一张，前端不用做增删接口。"""
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    shots = _shot_ids(doc)
    lib = {r["name"]: r for r in drama_materials.list_materials(_mat_dir(pid))}
    items: list[dict] = []
    seen: set[int] = set()
    for it in body.items:
        if it.shot_id not in shots:
            return fail(f"镜头 {it.shot_id} 不在当前分镜里 —— 先重出分镜再配画面")
        if it.shot_id in seen:
            return fail(f"镜头 {it.shot_id} 配了两张参考画面 —— 一镜只能配一张")
        name = Path(it.material).name
        row = lib.get(name)
        if not row:
            return fail(f"素材库里没有「{name}」—— 先上传")
        if row.get("media_type") != "image":
            return fail(f"「{row.get('original_name') or name}」不是图片 —— 参考画面只能选图片")
        seen.add(it.shot_id)
        items.append({"shot_id": it.shot_id, "material": name})
    doc["shot_materials"] = items
    _save(doc)
    return ok({"items": _shot_mat_items(doc)})


@router.post("/projects/{pid}/shot-materials/auto")
def auto_shot_materials(pid: str):
    """逐镜自动配一张（B4）。只补**还没配**的镜头，不覆盖手选；
    命中 0 个词的镜头**不配**——不拿不相关的图冒充匹配。
    返回里 `scores` 是命中词数（诚实标注：我们自己没有竞品的「降级阶梯」，能标的只有这个）。
    """
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    shots = [s for s in ((doc.get("storyboard_json") or {}).get("shots") or [])
             if isinstance(s, dict)]
    if not shots:
        return fail("没有分镜，先出分镜")
    have = drama_film.shot_materials(doc)
    lib_rows = [r for r in drama_materials.list_materials(_mat_dir(pid))
                if r.get("media_type") == "image"]
    if not lib_rows:
        return fail("素材库里还没有图片 —— 先上传几张场景/道具图")

    taken = set(have.values())
    free = [r for r in lib_rows if r["name"] not in taken]
    todo = []
    for i, s in enumerate(shots, 1):
        try:
            sid = int(s.get("id") or i)
        except (TypeError, ValueError):
            sid = i
        if sid not in have:
            todo.append({**s, "id": sid})

    picks = drama_materials.auto_match(todo, free)
    merged = [{"shot_id": sid, "material": name} for sid, name in have.items()]
    merged += [{"shot_id": p["shot_id"], "material": p["material"]} for p in picks]
    merged.sort(key=lambda x: x["shot_id"])
    doc["shot_materials"] = merged
    _save(doc)
    return ok({
        "items": _shot_mat_items(doc),
        "added": len(picks),
        "skipped": len(todo) - len(picks),
        "scores": {str(p["shot_id"]): p["score"] for p in picks},
    })


# ---------------------------------------------------------------- B6/B8 素材当画面
# 与上一段（B4 参考图）是**两条不同能力**：那边是图片、只借场景；这边是视频、
# **就是这一镜的画面** —— 该镜从 AI 出片里拿掉，合成时按 `film.plan.timeline` 插进时间线。
# 出处：竞品 `stock-fill/route.ts`（资产落到 shot）+ `composer.ts:500-535`（按镜头铺素材）。

def _shot_dialogue(doc: dict) -> dict[int, str]:
    out: dict[int, str] = {}
    for i, s in enumerate(((doc.get("storyboard_json") or {}).get("shots") or []), 1):
        if not isinstance(s, dict):
            continue
        try:
            sid = int(s.get("id") or i)
        except (TypeError, ValueError):
            sid = i
        out[sid] = str(s.get("dialogue") or "").strip()
    return out


def _clip_items(doc: dict) -> list[dict]:
    """绑定表 + 原文名 + 时长 + 这一镜的台词（前端要提示「台词会丢」）。"""
    pid = str(doc.get("id") or "")
    lib = {r["name"]: r for r in drama_materials.list_materials(_mat_dir(pid))}
    lines = _shot_dialogue(doc)
    items = []
    for sid, name in sorted(drama_film.shot_clips(doc).items()):
        row = lib.get(name) or {}
        items.append({
            "shot_id": sid,
            "material": name,
            "original_name": row.get("original_name") or name,
            "seconds": row.get("durationSec") or 0,
            "dialogue": lines.get(sid) or "",
            "url": f"/api/drama/projects/{pid}/materials/{name}/file",
            "missing": not bool(row),
        })
    return items


def _clip_videos(doc: dict) -> list[dict]:
    pid = str(doc.get("id") or "")
    return [_mat_public(r, pid) for r in drama_materials.list_materials(_mat_dir(pid))
            if r.get("media_type") == "video"]


@router.get("/projects/{pid}/shot-clips")
def get_shot_clips(pid: str):
    """素材当画面：已绑的 + 可选视频。"""
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    return ok({"items": _clip_items(doc), "videos": _clip_videos(doc)})


class ShotClipIn(BaseModel):
    shot_id: int
    material: str


class ShotClipsIn(BaseModel):
    items: list[ShotClipIn] = []


@router.put("/projects/{pid}/shot-clips")
def put_shot_clips(pid: str, body: ShotClipsIn):
    """整表保存：一镜一段，删一条 = 提交时不含它。"""
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    shots = _shot_ids(doc)
    lib = {r["name"]: r for r in drama_materials.list_materials(_mat_dir(pid))}
    items: list[dict] = []
    seen: set[int] = set()
    for it in body.items:
        if it.shot_id not in shots:
            return fail(f"镜头 {it.shot_id} 不在当前分镜里 —— 先重出分镜再配画面")
        if it.shot_id in seen:
            return fail(f"镜头 {it.shot_id} 配了两段画面素材 —— 一镜只能配一段")
        name = Path(it.material).name
        row = lib.get(name)
        if not row:
            return fail(f"素材库里没有「{name}」—— 先上传")
        if row.get("media_type") != "video":
            return fail(f"「{row.get('original_name') or name}」不是视频 —— "
                        "当画面素材只能选视频；图片请用「配参考画面」")
        if float(row.get("durationSec") or 0) <= 0:
            return fail(f"「{row.get('original_name') or name}」读不出时长，先删掉重传一次")
        seen.add(it.shot_id)
        items.append({"shot_id": it.shot_id, "material": name})
    doc["shot_clips"] = items
    _save(doc)
    return ok({"items": _clip_items(doc)})


# ---------------------------------------------------------------- 长视频导入（B6）

#: 长视频原料区：`data/drama/media/<pid>/`（**不进素材库** —— 见服务文件头第 1 条）
MEDIA_DIR = DATA / "media"


def _media_error(e: Exception) -> dict:
    """导入错误 → 人话（`media_import.ImportError_` 自带 message；其它异常兜底）。"""
    msg = str(e) or "视频导入失败"
    return fail(msg if msg.startswith(("文件", "视频", "单个", "仅支持", "没有", "无效"))
                else f"视频导入失败：{msg[:120]}")


@router.get("/projects/{pid}/media")
def list_media(pid: str):
    """已导入的长视频原料（按导入时间倒序）。"""
    try:
        _load(pid)
    except KeyError:
        return fail("项目不存在")
    rows = [drama_media_import.public_source(r, pid)
            for r in drama_media_import.list_sources(MEDIA_DIR, pid)]
    return ok({"sources": rows,
               "limits": {"max_bytes": drama_media_import.MAX_IMPORT_BYTES,
                          "max_seconds": drama_media_import.MAX_IMPORT_SECONDS,
                          "accept": sorted(drama_media_import.SUPPORTED_EXTENSIONS)}})


async def _import_media_multipart(pid: str, request: Request):
    """小程序端专用：`uni.uploadFile` 只能发 multipart，落盘后走同一套校验。

    Starlette 的 `request.form()` 会把文件写进 spooled 临时文件（>1MB 自动落盘），
    不是全内存；之后整块拷到目标目录。1GB 视频的代价是多一次磁盘拷贝。
    """
    try:
        form = await request.form()
        up = form.get("file")
        if up is None or not hasattr(up, "file"):
            return fail("没有收到视频文件")
        original = drama_media_import.safe_original_name(
            request.headers.get("x-file-name") or getattr(up, "filename", "") or "")
        mime = drama_media_import.canonical_mime(original)
    except drama_media_import.ImportError_ as e:
        return _media_error(e)
    except Exception as e:  # noqa: BLE001
        log.warning("[drama] multipart 解析失败: %s", e)
        return fail("解析上传失败，请重试")

    folder = drama_media_import.media_dir(MEDIA_DIR, pid)
    folder.mkdir(parents=True, exist_ok=True)
    stored = drama_media_import.stored_name(original)
    dest = folder / stored

    def _pipe() -> int:
        size = 0
        up.file.seek(0)  # Starlette 解析完已复位，这里再保险一次
        with dest.open("xb") as fh:
            while True:
                chunk = up.file.read(1 << 20)
                if not chunk:
                    break
                size += len(chunk)
                if size > drama_media_import.MAX_IMPORT_BYTES:
                    raise drama_media_import.ImportError_("文件不能超过 1GB", 413, "IMPORT_TOO_LARGE")
                fh.write(chunk)
        return size

    try:
        size = await asyncio.to_thread(_pipe)
        if size == 0:
            raise drama_media_import.ImportError_("没有收到视频文件", 400, "EMPTY_BODY")
        meta = await asyncio.to_thread(drama_media_import.validate_video, dest)
    except drama_media_import.ImportError_ as e:
        dest.unlink(missing_ok=True)
        return _media_error(e)
    except Exception as e:  # noqa: BLE001
        dest.unlink(missing_ok=True)
        log.warning("[drama] 长视频导入（multipart）失败: %s", e)
        return _media_error(e)

    row = drama_media_import.add_source(MEDIA_DIR, pid, original_name=original, file_name=stored,
                                        mime=mime, size_bytes=size, meta=meta)
    return ok({"source": drama_media_import.public_source(row, pid)})


@router.post("/projects/{pid}/media/import")
async def import_media(pid: str, request: Request):
    """收一个长视频。两种 body 都认：

    - 原始 body（H5，`application/octet-stream`）→ 流式，边写边计数
    - multipart（小程序 `uni.uploadFile`）→ 落 spooled 临时文件后整块拷贝

    `x-file-name` 带原名（URL 编码）。超过 1GB 立刻中断并删文件；
    写完真实探测（宽高 + 时长），不合格删文件 —— 坏的绝不能留在盘上（`media-validate.ts:52-58`）。
    """
    try:
        _load(pid)
    except KeyError:
        return fail("项目不存在")

    if (request.headers.get("content-type") or "").lower().startswith("multipart/form-data"):
        return await _import_media_multipart(pid, request)

    try:
        original = drama_media_import.safe_original_name(request.headers.get("x-file-name"))
        mime = drama_media_import.canonical_mime(original)
        declared = request.headers.get("content-length")
        drama_media_import.check_declared_size(int(declared) if declared and declared.isdigit() else None)
    except drama_media_import.ImportError_ as e:
        return _media_error(e)

    folder = drama_media_import.media_dir(MEDIA_DIR, pid)
    folder.mkdir(parents=True, exist_ok=True)
    stored = drama_media_import.stored_name(original)
    dest = folder / stored
    size = 0
    try:
        with dest.open("xb") as fh:
            async for chunk in request.stream():
                if not chunk:
                    continue
                size += len(chunk)
                if size > drama_media_import.MAX_IMPORT_BYTES:
                    raise drama_media_import.ImportError_("文件不能超过 1GB", 413, "IMPORT_TOO_LARGE")
                fh.write(chunk)
        if size == 0:
            raise drama_media_import.ImportError_("没有收到视频文件", 400, "EMPTY_BODY")
        meta = await asyncio.to_thread(drama_media_import.validate_video, dest)
    except drama_media_import.ImportError_ as e:
        dest.unlink(missing_ok=True)
        return _media_error(e)
    except Exception as e:  # noqa: BLE001
        dest.unlink(missing_ok=True)
        log.warning("[drama] 长视频导入失败: %s", e)
        return _media_error(e)

    row = drama_media_import.add_source(MEDIA_DIR, pid, original_name=original, file_name=stored,
                                        mime=mime, size_bytes=size, meta=meta)
    return ok({"source": drama_media_import.public_source(row, pid)})


@router.get("/projects/{pid}/media/{mid}/file")
def media_file(pid: str, mid: str):
    """取/播原视频（FileResponse 自带 Range 支持，前端可以直接拖动进度）。"""
    try:
        _load(pid)
    except KeyError:
        return fail("项目不存在")
    p = drama_media_import.source_file(MEDIA_DIR, pid, mid)
    if not p:
        return fail("视频不存在")
    row = drama_media_import.find_source(MEDIA_DIR, pid, mid) or {}
    return FileResponse(p, media_type=str(row.get("mime") or "application/octet-stream"))


@router.delete("/projects/{pid}/media/{mid}")
def delete_media(pid: str, mid: str):
    """删掉一条导入的视频（文件 + 索引一起删）。"""
    try:
        _load(pid)
    except KeyError:
        return fail("项目不存在")
    gone = drama_media_import.delete_source(MEDIA_DIR, pid, mid)
    if not gone:
        return fail("视频不存在")
    return ok({"deleted": gone["id"]})


# ---------------------------------------------------------------- 长视频转写（B7）

#: 正在跑的转写任务：key = (pid, mid)。进程重启即丢 —— 检查点在盘上，可以直接续。
_TRANSCRIBE_JOBS: dict[tuple[str, str], "asyncio.Task"] = {}


class MediaTranscriptIn(BaseModel):
    action: str = "start"          # start | cancel
    language: str = "zh"
    resume: bool = True


def _media_folder(pid: str) -> Path:
    return drama_media_import.media_dir(MEDIA_DIR, pid)


def _transcript_public(pid: str, mid: str, row: dict) -> dict:
    """前端形态：状态 + 进度 + 摘要；ready 时连全文一起给。"""
    out = {
        "media_id": mid,
        "status": row.get("status") or "uploaded",
        "progress": int(row.get("progress") or 0),
        "has_audio": bool(row.get("has_audio")),
        "summary": row.get("transcript_summary"),
        "error": row.get("error") or "",
        "checkpoint": drama_media_transcript.summarize(
            drama_media_transcript.sanitize_checkpoint(
                drama_media_transcript.load_checkpoint(_media_folder(pid), mid),
                float(row.get("duration") or 0),
                model=str(row.get("transcript_model") or "volc"),
                language=str(row.get("transcript_language") or "zh"))),
    }
    if out["status"] == "ready":
        out["transcript"] = drama_media_transcript.load_result(
            _media_folder(pid), mid) or {}
    return out


async def _run_transcribe_job(pid: str, mid: str) -> None:
    row = drama_media_import.find_source(MEDIA_DIR, pid, mid) or {}
    src = drama_media_import.source_file(MEDIA_DIR, pid, mid)
    folder = _media_folder(pid)
    duration = float(row.get("duration") or 0)
    language = str(row.get("transcript_language") or "zh")
    model = "volc"
    try:
        if not src:
            raise drama_media_transcript.TranscriptError("视频文件不见了，重新导入一次")
        if not row.get("has_audio"):
            raise drama_media_transcript.TranscriptError("这个视频没有可转写的音轨")

        def on_step(done: float, total: float) -> None:
            pct = max(1, min(99, round(done / total * 100))) if total else 0
            drama_media_import.update_source(MEDIA_DIR, pid, mid, progress=pct)

        doc = await drama_media_transcript.run_transcription(
            src, folder, mid, duration=duration, language=language, model=model,
            resume=True, on_step=on_step)
        drama_media_import.update_source(
            MEDIA_DIR, pid, mid, status="ready", progress=100, error="",
            transcript_summary={"chars": doc["chars"], "segments": len(doc["segments"]),
                                "duration": doc["duration"]})
    except asyncio.CancelledError:
        # 取消：有完整结果回 ready，没有回 uploaded（`transcript/route.ts:110-124`）
        has = drama_media_transcript.result_path(folder, mid).is_file()
        drama_media_import.update_source(
            MEDIA_DIR, pid, mid, status="ready" if has else "uploaded",
            progress=100 if has else 0, error="")
        raise
    except Exception as e:  # noqa: BLE001
        log.warning("[drama] 转写失败 %s/%s: %s", pid, mid, e)
        msg = str(e) if isinstance(e, drama_media_transcript.TranscriptError) else str(e)[:200]
        drama_media_import.update_source(MEDIA_DIR, pid, mid, status="failed", error=msg or "转写失败")
    finally:
        _TRANSCRIBE_JOBS.pop((pid, mid), None)


@router.get("/projects/{pid}/media/{mid}/transcript")
def get_media_transcript(pid: str, mid: str):
    """转写状态 / 进度 / 全文（前端轮询这个）。"""
    try:
        _load(pid)
    except KeyError:
        return fail("项目不存在")
    row = drama_media_import.find_source(MEDIA_DIR, pid, mid)
    if not row:
        return fail("视频不存在")
    # 中断判定（`media/route.ts:56-59`）：状态还是 transcribing 但没有活任务 → 已中断
    if row.get("status") == "transcribing" and (pid, mid) not in _TRANSCRIBE_JOBS:
        row = drama_media_import.update_source(
            MEDIA_DIR, pid, mid, status="failed",
            error="转写已中断，可直接重新开始") or row
    return ok({"source": drama_media_import.public_source(row, pid),
               "transcript": _transcript_public(pid, mid, row)})


@router.post("/projects/{pid}/media/{mid}/transcript")
async def start_media_transcript(pid: str, mid: str, body: MediaTranscriptIn):
    """开始 / 取消转写。

    - `action="start"`：没在跑就起一个后台任务；`resume=false` 丢掉旧检查点从头来
    - `action="cancel"`：取消后台任务（检查点留着，下次还能续）
    """
    try:
        _load(pid)
    except KeyError:
        return fail("项目不存在")
    row = drama_media_import.find_source(MEDIA_DIR, pid, mid)
    if not row:
        return fail("视频不存在")
    job = _TRANSCRIBE_JOBS.get((pid, mid))

    if body.action == "cancel":
        if job and not job.done():
            job.cancel()
            return ok({"cancelled": True})
        return fail("这个视频当前没有在转写")

    if body.action != "start":
        return fail("不支持的转写操作（只能是 start / cancel）")
    if not row.get("has_audio"):
        return fail("这个视频没有可转写的音轨")
    if not drama_media_import.source_file(MEDIA_DIR, pid, mid):
        return fail("视频文件不见了，重新导入一次")
    if job and not job.done():
        job.cancel()
    if not body.resume:
        drama_media_transcript.checkpoint_path(_media_folder(pid), mid).unlink(missing_ok=True)

    language = (body.language or "zh")[:24] or "zh"
    row = drama_media_import.update_source(
        MEDIA_DIR, pid, mid, status="transcribing", progress=0, error="",
        transcript_model="volc", transcript_language=language) or row
    task = asyncio.create_task(_run_transcribe_job(pid, mid))
    _TRANSCRIBE_JOBS[(pid, mid)] = task
    return ok({"source": drama_media_import.public_source(row, pid),
               "transcript": _transcript_public(pid, mid, row)})


# ---------------------------------------------------------------- 按文字剪（B8）

class ClipCutIn(BaseModel):
    start: float
    end: float


def _transcript_doc(pid: str, mid: str) -> dict:
    return drama_media_transcript.load_result(_media_folder(pid), mid) or {}


@router.get("/projects/{pid}/media/{mid}/clips")
def suggest_media_clips(pid: str, mid: str, query: str = "", target_seconds: float = 30,
                        limit: int = 6):
    """按关键词找片段（纯本地算，不调模型、不花钱）。

    参数闸照 `clips/route.ts:24`：关键词 ≤160 字、时长 5–120 秒、数量 1–12；
    **没转写完不给**（`clips/route.ts:30-31`）。
    """
    try:
        _load(pid)
    except KeyError:
        return fail("项目不存在")
    row = drama_media_import.find_source(MEDIA_DIR, pid, mid)
    if not row:
        return fail("视频不存在")
    if len(query or "") > drama_clips.MAX_QUERY_CHARS:
        return fail(f"关键词最多 {drama_clips.MAX_QUERY_CHARS} 字")
    if not (drama_clips.MIN_TARGET_SECONDS <= float(target_seconds or 0)
            <= drama_clips.MAX_TARGET_SECONDS):
        return fail("片段时长要在 5–120 秒之间")
    if not (1 <= int(limit or 0) <= drama_clips.MAX_CLIP_LIMIT):
        return fail(f"候选数量要在 1–{drama_clips.MAX_CLIP_LIMIT} 个之间")
    if row.get("status") != "ready":
        return fail("这个视频还没转写完成，先点「转写」")
    doc = _transcript_doc(pid, mid)
    if not doc:
        return fail("找不到转写结果，先重新转写一次")
    try:
        res = drama_clips.suggest(doc, query=query, target_seconds=target_seconds, limit=limit)
    except drama_clips.ClipError as e:
        return fail(str(e))
    return ok(res)


@router.post("/projects/{pid}/media/{mid}/clips/cut")
def cut_media_clip(pid: str, mid: str, body: ClipCutIn):
    """把一段区间真剪出来（本地 ffmpeg 重编码，零生成费）。"""
    try:
        _load(pid)
    except KeyError:
        return fail("项目不存在")
    row = drama_media_import.find_source(MEDIA_DIR, pid, mid)
    src = drama_media_import.source_file(MEDIA_DIR, pid, mid)
    if not row or not src:
        return fail("视频不存在")
    total = float(row.get("duration") or 0)
    start, end = float(body.start or 0), float(body.end or 0)
    if end <= start:
        return fail("结束时间要在开始之后")
    if start < 0 or (total and end > total + 0.05):
        return fail("切的区间超出这条视频")
    span = end - start
    if not (0.5 <= span <= 180):
        return fail("片段时长要在 0.5–180 秒之间")
    name = f"{mid}-{int(round(start * 1000))}-{int(round(end * 1000))}.mp4"
    out = _media_folder(pid) / "clips" / name
    try:
        info = drama_clips.cut(src, out, start, end)
    except drama_clips.ClipError as e:
        return fail(str(e))
    return ok({**info, "name": name, "start": round(start, 3), "end": round(end, 3),
               "url": f"/api/drama/projects/{pid}/media/{mid}/clips/{name}/file"})


@router.get("/projects/{pid}/media/{mid}/clips/{name}/file")
def media_clip_file(pid: str, mid: str, name: str):
    """播放 / 下载剪出来的片段。"""
    try:
        _load(pid)
    except KeyError:
        return fail("项目不存在")
    safe = Path(name).name
    if not safe.lower().endswith(".mp4"):
        return fail("片段不存在")
    p = _media_folder(pid) / "clips" / safe
    if not p.is_file():
        return fail("片段不存在")
    return FileResponse(p, media_type="video/mp4", filename=safe)


# ---------------------------------------------------------------------------
# B9 时间线导出（OTIO / EDL / CSV）
# ---------------------------------------------------------------------------


class TimelineExportIn(BaseModel):
    format: str = "otio"
    #: 不传 → 用这条视频**已经剪出来的片段**（`clips/<mid>-<起ms>-<止ms>.mp4`）
    ranges: list[dict] = Field(default_factory=list)
    revision: int | None = None
    #: True = 直接返回 JSON（前端可预览），False = 作为附件下载
    inline: bool = False


def _existing_clip_ranges(pid: str, mid: str) -> list[dict]:
    """从 B8 剪出来的片段文件名里还原保留区间。"""
    folder = _media_folder(pid) / "clips"
    if not folder.is_dir():
        return []
    pat = re.compile(rf"^{re.escape(mid)}-(\d+)-(\d+)\.mp4$", re.IGNORECASE)
    out: list[dict] = []
    for p in folder.iterdir():
        m = pat.match(p.name)
        if m and p.is_file():
            out.append({"start": int(m.group(1)) / 1000.0, "end": int(m.group(2)) / 1000.0})
    return out


@router.post("/projects/{pid}/media/{mid}/timeline")
def export_media_timeline(pid: str, mid: str, body: TimelineExportIn):
    """导出剪辑时间线：OTIO（DaVinci/FCP）/ CMX3600 EDL（Premiere）/ CSV（Excel）。

    出处 `api/.../timeline/route.ts:19`：只认 otio/edl/csv；没有转写不给导（:38-40）；
    区间为空 → 422（:40-42）。我们多一条兜底：不传区间就用 B8 已剪好的片段。
    """
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    row = drama_media_import.find_source(MEDIA_DIR, pid, mid)
    src = drama_media_import.source_file(MEDIA_DIR, pid, mid)
    if not row or not src:
        return fail("视频不存在")
    fmt = (body.format or "otio").strip().lower()
    if fmt not in drama_timeline.FORMATS:
        return fail("只支持 otio / edl / csv 三种格式")
    transcript = _transcript_doc(pid, mid)
    if not (transcript.get("segments") or transcript.get("text")):
        return fail("这条视频还没有转写结果，先点「转写」再导出时间线")
    total = float(row.get("duration") or 0)
    ranges = drama_timeline.normalize_ranges(
        body.ranges or _existing_clip_ranges(pid, mid), total)
    if not ranges:
        return fail("还没有可导出的片段：先「按文字剪」剪出至少一段，或者手动给区间")
    mapped = drama_timeline.map_transcript(transcript, ranges)
    payload = {
        "keep_ranges": ranges,
        "source_name": row.get("original_name") or src.name,
        "source_duration": total,
        "has_audio": bool(row.get("has_audio")),
        "frame_rate": drama_timeline.probe_frame_rate(src, drama_compose.ffprobe_path()),
        "project_name": doc.get("name") or "",
        "revision": body.revision,
        **mapped,
    }
    res = drama_timeline.export_timeline(fmt, payload)
    if body.inline:
        return ok(res)
    headers = {
        "Content-Disposition":
            f"attachment; filename=\"{res['file_name'].encode('ascii', 'ignore').decode() or 'timeline'}'; "
            f"filename*=UTF-8''{quote(res['file_name'])}",
        "X-Product-Drama-Clips": str(res["clips"]),
        "X-Product-Drama-Frame-Rate": str(res["frame_rate"]),
    }
    return PlainTextResponse(res["content"], media_type=res["mime_type"], headers=headers)


# ---------------------------------------------------------------------------
# D1 配音（免费 Edge TTS + 付费四家）/ D3 人声落地
# ---------------------------------------------------------------------------

#: 试听音频缓存（内容寻址，同一句同音色不重复打微软/厂商）
TTS_CACHE = DATA / "cache" / "tts"

_VOICE_RE = re.compile(r"^[A-Za-z0-9-]{1,40}$")
_RATE_RE = re.compile(r"^[+-]?\d{1,3}%$")
_PITCH_RE = re.compile(r"^[+-]?\d{1,3}(Hz|st|%)$")


class TTSFreeIn(BaseModel):
    text: str = "你好，这是免费配音的试听效果。"
    voice: str = ""
    rate: str = ""
    pitch: str = ""


class TTSPreviewIn(BaseModel):
    text: str = ""
    ttsConfig: dict = Field(default_factory=dict)
    providers: dict = Field(default_factory=dict)


@router.get("/tts/free")
def tts_free_voices():
    """免费音色表（零 Key，`api/tts/free/route.ts` GET）。"""
    return ok({"voices": drama_tts.FREE_TTS_VOICES,
               "default": drama_tts.DEFAULT_FREE_VOICE,
               "max_chars": drama_tts.MAX_PREVIEW_CHARS})


@router.get("/tts/providers")
def tts_providers():
    """付费四家的默认 baseUrl / model / 音色（`tts-presets.ts`）。"""
    return ok({"providers": drama_tts.TTS_PROVIDERS,
               "default": drama_tts.DEFAULT_TTS_PROVIDER})


@router.post("/tts/free")
async def tts_free_preview(body: TTSFreeIn):
    """免费试听：微软 Edge 朗读，返回 mp3 字节（不用 Key）。

    校验照 `api/tts/free/route.ts`：音色只允许 `[A-Za-z0-9-]`、语速只允许 `±N%`、
    非法值**回落默认而不是报错**（同时挡掉 SSML 注入）。
    """
    text = (body.text or "").strip()[:drama_tts.MAX_PREVIEW_CHARS]
    if not text:
        return fail("配音文本为空")
    voice = body.voice if _VOICE_RE.match(body.voice or "") else drama_tts.DEFAULT_FREE_VOICE
    rate = body.rate if _RATE_RE.match(body.rate or "") else "+0%"
    pitch = body.pitch if _PITCH_RE.match(body.pitch or "") else "+0Hz"
    try:
        res = await drama_tts.generate_speech_free(
            text, voice=voice, rate=rate, pitch=pitch, cache_dir=TTS_CACHE)
    except drama_tts.TTSError as e:
        return fail(str(e))
    return Response(content=res["audio"], media_type="audio/mpeg",
                    headers={"Cache-Control": "no-store",
                             "X-TTS-Cached": "1" if res["cached"] else "0",
                             "X-TTS-Words": str(len(res["words"]))})


@router.post("/tts/preview")
async def tts_paid_preview(body: TTSPreviewIn):
    """付费试听：任一平台合成 mp3（`api/tts/route.ts`）。缺 Key 直接说清缺什么。"""
    text = (body.text or "").strip()
    if not text:
        return fail("缺少配音文本")
    cfg = drama_tts.resolve_tts_config(body.ttsConfig, body.providers)
    if not (cfg.get("baseUrl") and cfg.get("apiKey") and cfg.get("model") and cfg.get("voice")):
        return fail("请先在设置中配置 TTS（baseUrl、apiKey、model、voice）")
    try:
        audio = await drama_tts.generate_speech(text, cfg, cache_dir=TTS_CACHE)
    except drama_tts.TTSError as e:
        return fail(str(e))
    return Response(content=audio, media_type="audio/mpeg",
                    headers={"Cache-Control": "no-store"})


@router.get("/tts/ground")
def tts_ground():
    """D3 人声落地的两条滤镜串 —— 已接进合成链（`drama_compose.build_graph`）。"""
    return ok({"voice_ground_chain": drama_tts.voice_ground_chain(),
               "room_tone_source": drama_tts.room_tone_source(),
               "wired": True,
               "where": "合成：有配音的段逐镜拼 TTS 并过去播音腔链，整条时间线垫房间底噪"})


class VoiceBuildIn(BaseModel):
    voice: str = ""
    rate: str = ""


@router.get("/projects/{pid}/voice")
def voice_get(pid: str):
    """D3 配音轨现状：已经生成了哪几句、什么音色、文件还在不在。"""
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    track = doc.get("voice_track") or {}
    lines = drama_voice.lines_of(doc)
    items, problems = drama_voice.usable(doc, DATA)
    return ok({
        "track": track,
        "count": len(items),
        "lines": len(lines),
        "problems": problems,
        "voices": drama_tts.FREE_TTS_VOICES,
        "default": drama_tts.DEFAULT_FREE_VOICE,
        "voice": drama_voice.voice_of(doc),
        "rate": drama_voice.rate_of(doc),
    })


@router.post("/projects/{pid}/voice/build")
async def voice_build(pid: str, body: VoiceBuildIn):
    """给整片配音（免费 Edge 音色，零 Key 零费用）—— **由使用者点**，不自动跑。

    每句台词一条 mp3，落 `<data>/voice/<pid>/<镜头号>.mp3`；重新生成会覆盖同名文件。
    合成时由 `drama_compose` 按镜头槽位拼进成片（人声落地：去播音腔 + 房间底噪）。
    """
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    if not ((doc.get("storyboard_json") or {}).get("shots") or []):
        return fail("先出分镜，才能配音")
    voice = body.voice if _VOICE_RE.match(body.voice or "") else drama_voice.voice_of(doc)
    rate = body.rate if _RATE_RE.match(body.rate or "") else drama_voice.rate_of(doc)
    try:
        track = await drama_voice.build(doc, data_dir=DATA, voice=voice, rate=rate)
    except ValueError as e:
        return fail(str(e))
    except drama_tts.TTSError as e:
        return fail(f"配音失败：{e}")
    doc["voice_track"] = track
    _save(doc)
    return ok(doc)


@router.delete("/projects/{pid}/voice")
def voice_delete(pid: str):
    """删掉配音轨的登记（文件留在盘上，重生成会覆盖）—— 合成退回模型原生出声。"""
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    doc.pop("voice_track", None)
    _save(doc)
    return ok(doc)


# ---------------------------------------------------------------------------
# D8 多语言译制（译词 → 重新配音 → 对轨）
# ---------------------------------------------------------------------------


class DubIn(BaseModel):
    target_lang: str
    title: str = ""
    #: 译完直接写回分镜（写回前会把原分镜存进 dub_restore，可一键还原）
    apply: bool = False


def _story_shots(doc: dict) -> list[dict]:
    return [s for s in ((doc.get("storyboard_json") or {}).get("shots") or [])
            if isinstance(s, dict)]


@router.get("/dub/langs")
def dub_langs():
    """支持的目标语言 + 每种语言推荐的免费配音音色（`translate.ts:20-45`）。"""
    langs = [{"code": code, "name": name, "voice": drama_dub.default_voice_for_lang(code)}
             for code, name in drama_dub.LANG_NAMES.items()]
    return ok({"langs": langs, "default": "en"})


@router.post("/projects/{pid}/dub")
def dub_project(pid: str, body: DubIn):
    """把当前分镜的台词译成目标语言，存档（可选直接应用）。

    出处 `api/project/[id]/dub/route.ts:24-84`：要目标语言、没分镜不给、译完返回推荐音色。
    """
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    target = (body.target_lang or "").strip().lower()
    if not target:
        return fail("请指定要译成的语言（如 en / ja / ko / es）")
    if not drama_dub.known_lang(target):
        return fail(f"不支持的目标语言：{target}")
    shots = _story_shots(doc)
    if not shots:
        return fail("这个项目还没有分镜，先出分镜再译制")
    try:
        translated = drama_dub.translate_shots(shots, target)
    except drama_dub.DubError as e:
        return fail(str(e))
    record = drama_dub.make_record(
        target, translated, title=body.title,
        source_title=str(doc.get("name") or ""))
    dubs = dict(doc.get("dubs") or {})
    record["version"] = int((dubs.get(record["lang"]) or {}).get("version") or 0) + 1
    dubs[record["lang"]] = record
    doc["dubs"] = dubs
    if body.apply:
        doc["dub_restore"] = {"lang": record["lang"], "shots": shots,
                              "created": time.strftime("%Y-%m-%d %H:%M:%S")}
        doc.setdefault("storyboard_json", {})["shots"] = translated
    _save(doc)
    return ok({**record, "applied": bool(body.apply)})


@router.get("/projects/{pid}/dubs")
def list_dubs(pid: str):
    """已译版本列表（不返回全文，列表够用）。"""
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    rows = []
    for lang, r in (doc.get("dubs") or {}).items():
        rows.append({"lang": lang, "lang_name": r.get("lang_name"), "title": r.get("title"),
                     "version": r.get("version"), "created": r.get("created"),
                     "recommended_voice": r.get("recommended_voice"),
                     "summary": r.get("summary") or {}})
    rows.sort(key=lambda x: str(x.get("created") or ""), reverse=True)
    restore = doc.get("dub_restore") or {}
    return ok({"dubs": rows,
               "can_restore": bool(restore),
               "restore_lang": restore.get("lang") or ""})


@router.post("/projects/{pid}/dubs/{lang}/apply")
def apply_dub(pid: str, lang: str):
    """把某个已译版本写回分镜（写回前备份原分镜）。"""
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    rec = (doc.get("dubs") or {}).get((lang or "").lower())
    if not rec:
        return fail("这个语言还没有译制版本")
    shots = rec.get("shots") or []
    if not shots:
        return fail("这个译制版本没有分镜内容")
    current = _story_shots(doc)
    if current:
        doc["dub_restore"] = {"lang": rec.get("lang"), "shots": current,
                              "created": time.strftime("%Y-%m-%d %H:%M:%S")}
    doc.setdefault("storyboard_json", {})["shots"] = shots
    _save(doc)
    return ok({"applied": rec.get("lang"), "summary": rec.get("summary") or {}})


@router.post("/projects/{pid}/dubs/restore")
def restore_dub(pid: str):
    """还原到应用译制版之前的分镜（只能还原一次）。"""
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    backup = doc.get("dub_restore") or {}
    shots = backup.get("shots") or []
    if not shots:
        return fail("没有可还原的原分镜")
    doc.setdefault("storyboard_json", {})["shots"] = shots
    doc.pop("dub_restore", None)
    _save(doc)
    return ok({"restored": len(shots)})


# ---------------------------------------------------------------------------
# A3 商品库（跨项目复用商品卡）
# ---------------------------------------------------------------------------

PRODUCTS_DIR = DATA / "products"


class ProductSaveIn(BaseModel):
    project_id: str
    name: str = ""


class ProductApplyIn(BaseModel):
    project_id: str


class ProductPatchIn(BaseModel):
    name: str | None = None
    category: str | None = None
    price: str | None = None
    platform: str | None = None
    audience: str | None = None
    facts: str | None = None
    points: list[str] | None = None


@router.get("/products")
def list_products():
    """商品库列表（按更新时间倒序）。"""
    rows = drama_product_lib.list_all(PRODUCTS_DIR)
    return ok({"products": rows, "max_images": drama_product_lib.MAX_IMAGES})


class ProductCreateIn(BaseModel):
    """直接建卡（不经过项目）：竞品 /products 的「添加商品」。"""
    name: str
    points: list[str] = Field(default_factory=list)
    facts: str = ""
    audience: str = ""
    category: str = ""
    price: str = ""
    platform: str = ""


@router.post("/products/create")
def create_product_card(body: ProductCreateIn):
    """不用项目也能建一张商品卡（竞品 `app/products/page.tsx` 的「添加商品」）。

    图片先空着：建完再用 `POST /products/{prid}/images` 一张张传。
    """
    try:
        row = drama_product_lib.create_blank(
            PRODUCTS_DIR, name=body.name, points=body.points, facts=body.facts,
            audience=body.audience, category=body.category, price=body.price,
            platform=body.platform)
    except ValueError as e:
        return fail(str(e))
    return ok(row)


@router.post("/products/{prid}/images")
async def upload_product_image(prid: str, file: UploadFile = File(...)):
    """给商品卡补一张图（最多 5 张；图存在卡自己的目录里）。"""
    if not drama_product_lib.find(PRODUCTS_DIR, prid):
        return fail("商品不存在")
    folder = PRODUCTS_DIR / prid
    try:
        fname = await _save_upload(file, folder)
        row = drama_product_lib.add_image(PRODUCTS_DIR, prid, fname)
    except ValueError as e:
        return fail(str(e))
    except Exception as e:  # noqa: BLE001
        return fail(f"上传失败：{str(e)[:120]}")
    if not row:
        return fail("商品不存在")
    return ok(row)


@router.delete("/products/{prid}/images/{name}")
def delete_product_image(prid: str, name: str):
    """删商品卡上的一张图（文件一起删）。"""
    row = drama_product_lib.drop_image(PRODUCTS_DIR, prid, Path(name).name)
    if not row:
        return fail("这张图不在卡上")
    return ok(row)


@router.post("/products")
def save_product(body: ProductSaveIn):
    """把某个项目的商品信息存进商品库（图片复制一份，项目删了也不影响）。"""
    try:
        doc = _load(body.project_id)
    except KeyError:
        return fail("项目不存在")
    try:
        row = drama_product_lib.create_from_project(
            PRODUCTS_DIR, doc, IMAGES_DIR / body.project_id, name=body.name or None)
    except ValueError as e:
        return fail(str(e))
    return ok(row)


@router.patch("/products/{prid}")
def patch_product(prid: str, body: ProductPatchIn):
    """改商品卡字段（改名 / 品类 / 价格 / 平台 / 受众 / 事实 / 卖点）。"""
    fields = body.model_dump(exclude_none=True)
    if not fields:
        return fail("没有要改的字段")
    row = drama_product_lib.update_card(PRODUCTS_DIR, prid, fields)
    if not row:
        return fail("商品不存在")
    return ok(row)


@router.post("/products/{prid}/apply")
def apply_product(prid: str, body: ProductApplyIn):
    """把商品卡写回某个项目：字段照抄、图片复制进项目目录（不动原有图片）。"""
    try:
        doc = _load(body.project_id)
    except KeyError:
        return fail("项目不存在")
    res = drama_product_lib.apply_to_project(PRODUCTS_DIR, prid, IMAGES_DIR / body.project_id)
    if not res:
        return fail("商品不存在")
    doc["product"] = {**(doc.get("product") or {}), **res["product"]}
    _save(doc)
    return ok({"product": doc["product"], "added_images": len(res["images"])})


@router.delete("/products/{prid}")
def delete_product(prid: str):
    """删商品卡（连同它自己的图片副本；项目里的图不受影响）。"""
    if not drama_product_lib.remove(PRODUCTS_DIR, prid):
        return fail("商品不存在")
    return ok({"deleted": prid})


@router.get("/products/{prid}/images/{name}")
def product_image(prid: str, name: str):
    """商品卡里的图片（预览用）。"""
    safe = Path(name).name
    p = PRODUCTS_DIR / prid / safe
    if not drama_product_lib.find(PRODUCTS_DIR, prid) or not p.is_file():
        return fail("图片不存在")
    return FileResponse(p, filename=safe)


# ===========================================================================
# D7 风格配方 + F8 结构指纹（2026-11-06 第十九批）—— 纯本地，零费用
#
# 出处：clipforge `src/lib/style-packs.ts:1-132` / `src/lib/structure-fingerprint.ts:1-114` /
# `src/app/api/insights/homogeneity/route.ts`；逐条对照写在两个 service 的文件头。
# 🩸 本组接口**不调用任何模型**，也不渲染：只读写设置与纯函数计算。
# ===========================================================================

STYLE_PACK_MAX_BYTES = 64 * 1024


class StylePackIn(BaseModel):
    """导入配方：直接给 JSON 文本（界面上粘贴或选文件读出来的内容）。"""

    text: str = ""


def _project_display_name(doc: dict) -> str:
    """列表里的显示名口径（与 `list_projects` 一致：商品名 → 话题 → 项目名）。"""
    return str((doc.get("product") or {}).get("name") or doc.get("topic")
               or doc.get("name") or "")


@router.get("/style-packs")
def style_packs():
    """可用配方：4 个内置 + 格式标记（前端把内置的 compose 原样展示，不需要自己的副本）。"""
    return ok({"format": drama_styles.STYLE_PACK_FORMAT,
               "builtin": drama_styles.BUILTIN_PACKS,
               "max_bytes": STYLE_PACK_MAX_BYTES})


@router.post("/style-packs/parse")
def parse_style_pack(body: StylePackIn):
    """先解析给用户看（不落盘）：能认出几个字段、哪些字段这边用不了。"""
    if len(body.text.encode("utf-8")) > STYLE_PACK_MAX_BYTES:
        return fail(f"配方超过 {STYLE_PACK_MAX_BYTES // 1024}KB，不像一份配方")
    pack, dropped = drama_styles.parse_style_pack(body.text)
    if not pack:
        return fail("这不是一份能认的配方（要 JSON，带 format 和 name）")
    return ok({"pack": pack, "dropped": dropped,
               "compose": drama_styles.pack_to_compose(pack)})


@router.get("/projects/{pid}/style-pack")
def export_style_pack(pid: str):
    """把项目当前合成设置导出成配方文本（没存过设置就按默认值导）。"""
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    options = (doc.get("compose") or {}).get("options") or {}
    if not options:
        options = {
            "caption_preset": drama_captions.DEFAULT_ID,
            "captions": True,
            "bgm_volume": drama_audio.DEFAULT_BGM_VOLUME,
            "bgm_duck": True,
            "render_preset": drama_compose.DEFAULT_RENDER_PRESET,
            "end_card": {"enabled": False},
        }
    name = (_project_display_name(doc) or "当前项目") + " 配方"
    pack = drama_styles.compose_to_pack(options, name=name, author="video-tool")
    text = drama_styles.serialize_style_pack(pack)
    return ok({"pack": pack, "text": text,
               "file_name": f"{(doc.get('name') or 'style')[:20]}-style-pack.json"})


@router.post("/projects/{pid}/style-pack")
def import_style_pack(pid: str, body: StylePackIn):
    """导入配方：**只覆盖配方里带了的那几项**，其余合成设置保持原样。

    🩸 不动已出的片段、不改分镜，也不自动合成 —— 只是把设置写进项目，
    用户仍要在合成面板里重新规划并自己点合成。
    """
    if len(body.text.encode("utf-8")) > STYLE_PACK_MAX_BYTES:
        return fail(f"配方超过 {STYLE_PACK_MAX_BYTES // 1024}KB，不像一份配方")
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    pack, dropped = drama_styles.parse_style_pack(body.text)
    if not pack:
        return fail("这不是一份能认的配方（要 JSON，带 format 和 name）")
    patch = drama_styles.pack_to_compose(pack)
    if not patch:
        return fail("这份配方里没有这边能用的合成设置")
    comp = dict(doc.get("compose") or {})
    comp["options"] = drama_styles.merge_into_options(comp.get("options"), patch)
    # 配方来源留档：出片前能看出「这套设置是从哪份配方来的」
    comp["style_pack"] = {"name": pack.get("name"), "author": pack.get("author") or "",
                          "dropped": dropped,
                          "applied": time.strftime("%Y-%m-%d %H:%M:%S")}
    doc["compose"] = comp
    _save(doc)
    return ok({"project": doc, "pack": pack, "dropped": dropped,
               "options": comp["options"]})


@router.get("/insights/homogeneity")
def homogeneity(limit: str = "8"):
    """跨项目结构指纹自检（`api/insights/homogeneity/route.ts`）。

    取最近 N 个**有分镜**的项目，两两比结构相似度；少于 2 条直接给 ok + 空结果。
    """
    try:
        n = int(limit)
    except (TypeError, ValueError):
        n = 8
    n = max(2, min(20, n))

    fps = []
    for p in sorted(_dir().glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        if len(fps) >= n:
            break
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict):  # 目录里混进非项目 json —— 跳过，别把接口打成 500
            continue
        if not ((d.get("storyboard_json") or {}).get("shots")):
            continue
        fp = drama_fingerprint.fingerprint_of(d)
        fp["project_name"] = _project_display_name(d)
        fps.append(fp)
    if len(fps) < 2:
        return ok({"total": len(fps), "similar_pairs": [], "similar_share": 0,
                   "verdict": "ok", "message": None})
    return ok(drama_fingerprint.homogeneity_report(fps))


# ===========================================================================
# H2 文件服务 + H4 设置中心（2026-11-06 第二十批）—— 纯本地，零费用
#
# 出处：clipforge `api/files/[...path]/route.ts`（防穿越 + Range + 一年缓存）/
# `api/output/[...path]/route.ts`（下载 + 一小时缓存）/ `lib/stores/settings-store.ts`（版本迁移链）。
# 逐条对照写在两个 service 的文件头。
# ===========================================================================

#: 对外可读的目录白名单（kind → 目录）。**不在表里的一律 404**，不暴露目录结构。
FILES_ROOTS = {
    "images": IMAGES_DIR,
    "films": FILM_DIR,
    "bgm": BGM_DIR,
    "media": MEDIA_DIR,
    "materials": MATERIALS_DIR,
    "products": PRODUCTS_DIR,
    "grids": GRID_DIR,
}

#: 成片/关键帧会重新生成，缓存短；素材与商品图是内容寻址式文件名，可以长缓存
FILES_SHORT_CACHE = ("films", "grids")


@router.get("/files/{kind}/{path:path}")
def serve_data_file(kind: str, path: str, download: str = ""):
    """通用文件出口：防穿越 + Range（Starlette 原生 206/416）+ 流式 + 缓存头。

    🩸 这里是**二进制**出口，出错回真 HTTP 状态（403/404），不回 JSON 信封 ——
    `<video>` / `<img>` 不认 `{"biz_code":1}`，回 200 会让播放器把错误当视频数据。
    """
    root = FILES_ROOTS.get(kind)
    if root is None:
        raise HTTPException(404, "这类目录不对外")
    try:
        f = drama_files.resolve_under(root, path.split("/"))
    except drama_files.FileError as e:
        msg = str(e)
        raise HTTPException(403 if "非法" in msg else 404, msg)
    headers = {
        "Cache-Control": (drama_files.CACHE_SHORT if kind in FILES_SHORT_CACHE
                          else drama_files.CACHE_FOREVER),
    }
    if download:
        # 中文文件名按 RFC 5987 编码，别塞进引号里（会乱码或被浏览器截断）
        headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(f.name)}"
    return FileResponse(f, media_type=drama_files.mime_of(f), headers=headers)


SETTINGS_FILE = DATA / "settings.json"


def _key_rows() -> list[dict]:
    """设置的「密钥状态」区：只回是否配置 + 掩码，**绝不回整串**。

    🩸 只放**本产品真的会读**的 Key：
    - `volc_tts` 这个名字是历史名，商品短剧这边它只用于 **B7 转写**
      （`drama_media_transcript.py:291` → `providers/asr.py:110`）；配音走免费 Edge，
      火山 TTS 没接进这条线。
    - **不放 MiniMax**：MiniMax 的 Key 是 H3 视频线（`services/minimax.py`）在用；
      本产品的付费配音走**项目级** `tts.apiKey`（`drama_tts.py:599`），不读这把环境变量。
      以前照竞品 `tts.ts` 的付费四家把它列在这里，会让人以为本产品的配音通道是海螺。
    """
    rows = [
        ("deepseek", "DeepSeek（写结构卡/剧本/分镜）", settings.deepseek_api_key),
        ("ark", "火山方舟（出图/出片）", settings.ark_api_key),
        ("volc_tts", "豆包语音（转写）", settings.volc_api_key),
        ("mediakit", "AI MediaKit（人声分离）", settings.mediakit_api_key),
    ]
    return [{"name": n, "label": lbl, "configured": bool(k), "masked": drama_settings.mask_key(k)}
            for n, lbl, k in rows]


def _settings_options() -> dict:
    return {
        "caption_preset": [{"id": p["id"], "label": p["id"]} for p in drama_captions.public()],
        "render_preset": [{"id": v["id"], "label": v.get("label") or v["id"]}
                          for v in drama_compose.RENDER_PRESETS.values()],
        "transition": [{"id": v["id"], "label": v.get("label") or v["id"]}
                       for v in drama_compose.TRANSITIONS.values()],
        "tts_voice": [{"id": v["value"], "label": v["label"]}
                      for v in drama_tts.FREE_TTS_VOICES],
        # 成片全局默认（C12 真实感 / C9 接缝 / 分辨率 / 画面比例）
        "film_resolution": [{"id": v, "label": v} for v in drama_settings.FILM_RESOLUTIONS],
        "film_ratio": [{"id": "9:16", "label": "竖屏 9:16"},
                       {"id": "16:9", "label": "横屏 16:9"},
                       {"id": "1:1", "label": "方形 1:1"}],
        "film_chain": [{"id": "off", "label": "各段独立"},
                       {"id": "tail", "label": "续拍（接上一段尾帧）"}],
        "film_realism": [{"id": "auto", "label": "自动（全层）"},
                         {"id": "constraints", "label": "仅约束"},
                         {"id": "off", "label": "关"}],
    }


class SettingsIn(BaseModel):
    """整份设置提交（不传的项保持不变）。"""

    settings: dict = Field(default_factory=dict)


@router.get("/settings")
def get_settings():
    """设置中心：全局默认值 + 版本号 + 密钥状态（掩码）。"""
    st, applied = drama_settings.load(SETTINGS_FILE)
    return ok({"settings": st, "version": drama_settings.SCHEMA_VERSION,
               "applied": applied, "fields": list(drama_settings.FIELDS),
               "keys": _key_rows(), "options": _settings_options(),
               "file": str(SETTINGS_FILE.name)})


@router.patch("/settings")
def patch_settings(body: SettingsIn):
    """改全局默认值（只改传进来的项）。非法值报人话，不静默夹取（音量除外）。"""
    try:
        patch = drama_settings.sanitize(body.settings)
    except drama_settings.SettingsError as e:
        return fail(str(e))
    st, _ = drama_settings.load(SETTINGS_FILE)
    st.update(patch)
    saved = drama_settings.save(SETTINGS_FILE, st)
    return ok({"settings": saved, "changed": list(patch)})


@router.post("/settings/reset")
def reset_settings():
    """恢复默认（只影响全局默认值，不动任何项目里存过的设置）。"""
    st = drama_settings.save(SETTINGS_FILE, drama_settings.default_state())
    return ok({"settings": st})


class SettingsImportIn(BaseModel):
    """旧版设置（竞品 zustand persist 的 `{state,version}` 或裸对象，也收 JSON 字符串）。"""

    legacy: object = None


@router.post("/settings/import")
def import_settings(body: SettingsImportIn):
    """H4 旧版设置迁移：跑竞品那五版修复 + 把语义对得上的项搬进来。

    🩸 只搬 `film_realism` / `film_chain` / `film_resolution` / `tts_voice` 四个；
    其余逐项列进 `dropped`（说清为什么不搬），**不假装搬成功了**。
    """
    raw = body.legacy
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return fail("不是合法 JSON —— 把旧设置整段（含 { }）贴进来")
    if not isinstance(raw, dict) or not raw:
        return fail("没有可迁移的设置对象")
    try:
        rep = drama_settings.import_legacy(raw)
    except Exception as e:  # noqa: BLE001
        log.warning("[drama] settings import 失败: %s", e)
        return fail(f"迁移失败：{e}")
    mapped = rep.get("settings") or {}
    st, _ = drama_settings.load(SETTINGS_FILE)
    st.update(mapped)
    saved = drama_settings.save(SETTINGS_FILE, st)
    return ok({"settings": saved, "mapped": mapped, "fixed": rep.get("fixed") or [],
               "dropped": rep.get("dropped") or [],
               "source_version": rep.get("source_version") or 0})


# ===========================================================================
# G3 趋势话题（2026-11-06 第二十一批）—— 零 Key，10 分钟缓存
#
# 出处：clipforge `src/lib/trends.ts:1-323` / `api/trends/route.ts`；
# 解析规则逐条对照写在 `services/drama_trends.py` 文件头。
# ===========================================================================


@router.get("/trends")
def trends(source: str = "", geo: str = "", limit: str = "20", persona: str = ""):
    """今天该发什么：`?source=cn`（默认）走抖音→头条；给 `geo` 走 Google Trends。

    上游挂了返回空列表 + `error` 人话，不回 500 —— 这是锦上添花的入口。
    """
    return ok(drama_trends.build_trends(source=source, geo=geo, limit=limit, persona=persona))


# ===========================================================================
# G2 作品流 + G4 发布指标回填 + G5 风格成效（2026-11-06 第二十二批）
#
# 出处：clipforge `api/works/route.ts`（跨项目成片墙 + 封面回填预算）、
#       `api/project/[id]/metrics/route.ts`（录入/倒序列表）、
#       `api/insights/styles/route.ts` + `lib/performance-insights.ts`（聚合与反哺）。
# 细节逐条写在 `services/drama_works.py` / `services/drama_metrics.py` 文件头。
# ===========================================================================

#: 与竞品 `metrics/route.ts:8` 同口径：只收字母/数字/连字符，挡路径注入
_SAFE_PID = re.compile(r"^[a-zA-Z0-9\-]+$")


class MetricIn(BaseModel):
    """一条发布数据。数字字段故意收 `Any`：界面传的是字符串，规则由服务层归一。"""

    style: str = ""
    hookId: str = ""
    category: Any = None
    platform: Any = None
    views: Any = 0
    likes: Any = 0
    comments: Any = 0
    shares: Any = 0
    orders: Any = 0
    note: Any = None
    publishedAt: Any = None


@router.get("/works")
def works():
    """跨项目成片墙：所有出成功过的片子，按时间倒序 + 封面（缺的按预算回填）。"""
    try:
        return ok(drama_works.list_works(DATA, FILM_DIR, save=_save))
    except Exception as e:  # noqa: BLE001
        log.warning("[drama] 作品流失败: %s", e)
        return fail(f"获取作品流失败：{str(e)[:200]}")


@router.get("/projects/{pid}/metrics")
def list_metrics(pid: str):
    """这个项目录过的发布数据，新的在前。"""
    if not _SAFE_PID.match(pid or ""):
        return fail("无效的项目ID")
    try:
        _load(pid)
    except KeyError:
        return fail("项目不存在")
    return ok({"metrics": drama_metrics.list_for(METRICS_FILE, pid)})


@router.post("/projects/{pid}/metrics")
def add_metric(pid: str, body: MetricIn = MetricIn()):
    """录入一条发布数据：风格/品类在这里**定格**，之后改配方也不污染历史统计。"""
    if not _SAFE_PID.match(pid or ""):
        return fail("无效的项目ID")
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    rows = drama_metrics.load(METRICS_FILE)
    rec = drama_metrics.build_record(project_id=pid, doc=doc,
                                     body=body.model_dump(), rows=rows)
    drama_metrics.add(METRICS_FILE, rec)
    return ok({"metric": rec})


@router.get("/insights/styles")
def style_insights():
    """全站风格/钩子成效：按转化率降序（成交/播放）。"""
    return ok(drama_metrics.insights_payload(drama_metrics.load(METRICS_FILE)))


# ===========================================================================
# B11 媒体解构实验室
#   出处：clipforge `api/media/analyze/route.ts` + `lib/media-analysis.ts`，
#   细节在 `services/drama_media_lab.py` 文件头。
# ===========================================================================


@router.post("/media/analyze")
async def media_analyze(file: UploadFile = File(...)):
    """一张图 / 一段视频 → 内容摘要、画面风格、可复用提示词、适用场景。

    零出片零生成费；只有一次视觉模型调用。Key 只从服务端配置读。
    """
    import shutil
    import tempfile

    ctype = (file.content_type or "").lower().split(";")[0].strip()
    if not ctype:
        guess = Path(file.filename or "").suffix.lower()
        ctype = next((m for m, ext in drama_media_lab.EXTENSIONS.items() if ext == guess), "")
    media_type = drama_media_lab.media_type_for(ctype)
    if not media_type:
        return fail("仅支持 JPG、PNG、WebP、MP4、WebM、MOV")

    limit = (drama_media_lab.IMAGE_MAX if media_type == "image"
             else drama_media_lab.VIDEO_MAX)
    work = Path(tempfile.mkdtemp(prefix="drama-media-", dir="D:/tmp"))
    try:
        ext = drama_media_lab.EXTENSIONS.get(ctype) or Path(file.filename or "").suffix or ".bin"
        src = work / f"source{ext}"
        size = 0
        with src.open("wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > limit:
                    return fail("图片不能超过 15MB" if media_type == "image"
                                else "视频不能超过 80MB")
                f.write(chunk)
        if size == 0:
            return fail("文件是空的")
        result = drama_media_lab.analyze_file(src, mime=ctype, size=size, work_dir=work)
    except drama_media_lab.MediaLabError as e:
        return fail(str(e))
    except Exception as e:  # noqa: BLE001
        log.warning("[drama] 媒体解构失败: %s", e)
        return fail(f"媒体解构失败：{str(e)[:200]}")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return ok(result)


class MediaInsightIn(BaseModel):
    """把解构结果存进项目（竞品 `production.mediaInsight` 的等价物）。"""
    mediaInsight: dict = Field(default_factory=dict)


@router.patch("/projects/{pid}/production")
def save_media_insight(pid: str, body: MediaInsightIn = MediaInsightIn()):
    """存「媒体解构」结论：类型 / 摘要 / 主体标签 / 可复用提示词。"""
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    src = body.mediaInsight or {}
    mt = src.get("mediaType")
    tags = src.get("tags")
    if not isinstance(tags, list):
        tags = []
    insight = {
        "media_type": mt if mt in ("image", "video") else "",
        "summary": str(src.get("summary") or "").strip()[:600],
        "tags": [x.strip()[:120] for x in tags if isinstance(x, str) and x.strip()][:8],
        "reusable_prompt": str(src.get("reusablePrompt") or "").strip()[:600],
        "saved": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if not insight["summary"] and not insight["reusable_prompt"]:
        return fail("解构结果还是空的，先分析一条素材")
    doc["media_insight"] = insight
    _save(doc)
    return ok({"media_insight": insight})


# ===========================================================================
# G1 批量作业（多商品排队，作业/条目落盘）
#   出处：clipforge `api/batch/route.ts` + `app/batch/page.tsx`，
#   语义与差异在 `services/drama_batch.py` 文件头。
# ===========================================================================


class BatchItemIn(BaseModel):
    product_id: str = ""
    product_name: str = ""
    variation: str | None = None


class BatchCreateIn(BaseModel):
    config: dict = Field(default_factory=dict)
    items: list[BatchItemIn] = Field(default_factory=list)


class BatchPatchIn(BaseModel):
    job_id: str = ""
    status: str = ""
    item_id: str = ""
    patch: dict = Field(default_factory=dict)


class BatchPlanIn(BaseModel):
    count: int = 0
    seed: int = 1
    rotate_voice: bool = True


def _batch() -> tuple[Path, dict]:
    path = drama_batch.store_path(_dir())
    return path, drama_batch.load(path)


@router.get("/batch")
def batch_get(job_id: str = "", active: int = 0):
    """`?job_id=` 指定作业；`active=1` 最新在飞；都不传 = 最新一个。"""
    _, state = _batch()
    got = drama_batch.get(state, job_id=job_id, active=bool(active))
    return ok({**got, "summary": drama_batch.summary(got.get("job"))})


@router.post("/batch")
def batch_create(body: BatchCreateIn):
    """建批量作业。同一时间只留一个在飞：旧的 running 会被结算成 cancelled。"""
    path, state = _batch()
    try:
        res = drama_batch.create_job(state, body.config, [i.model_dump() for i in body.items])
    except drama_batch.BatchError as e:
        return fail(str(e))
    drama_batch.save(path, state)
    return ok(res)


@router.patch("/batch")
def batch_patch(body: BatchPatchIn):
    """条目写回（状态 / 项目 / 合成 id / 错误）或作业结算（running/done/cancelled）。"""
    path, state = _batch()
    try:
        res = drama_batch.patch(state, body.model_dump())
    except drama_batch.BatchError as e:
        return fail(str(e))
    drama_batch.save(path, state)
    return ok(res)


@router.post("/batch/plan")
def batch_plan(body: BatchPlanIn = BatchPlanIn()):
    """反同质化轮换计划：每条商品一个槽位（钩子 / 音色 / 字幕），同 seed 可复现。"""
    slots = drama_batch.build_plan(body.count, seed=body.seed,
                                   rotate_voice=body.rotate_voice)
    for s in slots:
        s["summary"] = drama_batch.describe_slot(s)
    return ok({"slots": slots, "count": len(slots)})


# ---------------------------------------------------------------- 一键流水线（判官 → 配画面 → 合成）
#
# 出处：竞品 `lib/pipeline-stages.ts:10`（PIPELINE_STAGES）+ `api/project/[id]/pipeline/route.ts:1-14`
# （服务端 hands-off + 断点续跑）。三段都不出片：
#   judge      一次文本模型调用（判官团）
#   stock_fill 免费素材库检索 + 下载（零 Key 源）
#   compose    本地 ffmpeg 合成（零生成费）
# 🩸 判官那一步要走 DeepSeek，是**文本费**，不是视频生成费；界面文案按「不出片」说。

_PIPELINE_JOBS: dict[str, "asyncio.Task"] = {}


class PipelineIn(BaseModel):
    from_stage: str = "judge"      # judge | stock_fill | compose
    media_type: str = "image"      # stock_fill 用
    allow_universal: bool = False
    force: bool = False
    per_page: int = 8
    max_shots: int = 0


def _pipeline_stage_judge(doc: dict) -> dict:
    shots = (doc.get("storyboard_json") or {}).get("shots") or []
    if not shots:
        raise RuntimeError("还没有分镜，判官没东西可审")
    raw = _chat(drama_judge.build_user(doc), temperature=0.2, system=JUDGE_SYS)
    obj = drama_format.parse_json(raw)
    report = drama_judge.sanitize(obj, shots)
    doc["judge"] = report
    n = len(report.get("verdicts") or [])

    # 弱句自动改写（竞品 `pipeline-runner.ts:77-97`）：只应用 invariant/default 两档，
    # taste（口味）档留给主人自己挑 —— 「改不改这句」是审美判断，不该由机器替主人定。
    keys = []
    for v in report.get("verdicts") or []:
        for it in v.get("issues") or []:
            if it.get("tier") == "taste":
                continue
            if str(it.get("field") or "") not in ("dialogue", "description"):
                continue
            if it.get("new_text"):
                keys.append(f"{it['shot_id']}:{it['field']}")
    applied, _skipped, err = _judge_apply_keys(doc, keys)
    if err:
        return {"summary": f"判官出报告：{n} 条；改写没通过校验，已丢弃（{err[:60]}）"}
    return {"summary": f"判官出报告：{n} 条，弱句改写 {len(applied)} 处"}


def _pipeline_stage_stock(doc: dict, body: PipelineIn) -> dict:
    shots = (doc.get("storyboard_json") or {}).get("shots") or []
    if not shots:
        raise RuntimeError("还没有分镜，配不了画面")
    media_type = body.media_type if body.media_type in ("image", "video") else "image"
    res = drama_stock_fill.auto_fill(
        doc, _mat_dir(str(doc.get("id") or "")),
        media_type=media_type, source="", force=bool(body.force),
        per_page=max(1, min(30, int(body.per_page or 8))),
        allow_universal=bool(body.allow_universal),
        max_shots=max(0, int(body.max_shots or 0)))
    return {"summary": f"配画面：{res.get('filled', 0)}/{res.get('total', 0)} 镜",
            "filled": res.get("filled", 0), "total": res.get("total", 0)}


async def _pipeline_stage_compose(pid: str, doc: dict) -> dict:
    """免费快剪的合成阶段（**不调视频模型**）。

    出处：竞品 `pipeline-runner.ts:104-140` + `compose/route.ts:340-406`
    —— 画面来自素材/商品图，配音用免费音色，全程 ¥0。

    🩸 这里以前接的是「AI 出片之后的合成器」（要求先有出片计划），所以在脚本页
    一点就报「还没有出片计划」。快剪的语义就是**不出片也能成片**，所以固定
    `freecut=True`，并在合成前把缺的配音补上（免费 Edge 音色）。
    """
    # ① 免费配音：有台词但还没有可用配音 → 现配（逐句落盘，零 Key）
    voice_note = ""
    try:
        lines = drama_voice.lines_of(doc)
        items, _ = drama_voice.usable(doc, DATA)
        if lines and not items:
            track = await drama_voice.build(
                doc, data_dir=DATA,
                voice=drama_voice.voice_of(doc), rate=drama_voice.rate_of(doc))
            doc["voice_track"] = track
            _save(doc)
            voice_note = f"，配音 {len((track or {}).get('items') or [])} 句"
        elif items:
            voice_note = f"，用已有配音 {len(items)} 句"
    except Exception as e:  # noqa: BLE001
        # 配音是增强项：配不出来也要把画面合成出来，把原因写在结果里
        log.warning("[drama] 快剪配音失败（继续合成）: %s", e)
        voice_note = f"，配音没配成（{str(e)[:60]}）"

    comp = _compose_state(doc)
    cfg = ((comp.get("plan") or {}).get("config")) or _compose_cfg(ComposeIn())
    fresh = drama_compose.plan(
        doc, film_dir=FILM_DIR / pid, config=cfg,
        bgm_file=_bgm_name(doc),
        end_card_image=str((cfg.get("end_card") or {}).get("image") or ""),
        freecut=True)
    if fresh.get("errors"):
        raise RuntimeError("快剪合成有硬问题：" + "；".join(fresh["errors"][:3]))

    font = drama_cover.resolve_font()
    prof = drama_compose.render_profile((fresh.get("config") or {}).get("render_preset"))
    width, height = drama_compose.RESOLUTIONS[
        fresh.get("ratio") or "9:16"][prof["resolution"]]
    cap = fresh.get("caption") or {}
    ass_text = ""
    if cap.get("enabled") and cap.get("cues") and cap.get("karaoke"):
        ass_text = drama_captions.karaoke_ass(
            cap["cues"], font_name=drama_captions.font_name_for(font),
            width=width, height=height)

    out_dir = FILM_DIR / pid
    out_dir.mkdir(parents=True, exist_ok=True)
    # 🩸 与 `compose_run` 同一条规矩：同一秒内连点两次不能写同一个文件
    # （否则后一次把前一次覆盖，导出页历史两条指向同一个 mp4）。
    stem = f"compose-{time.strftime('%Y%m%d-%H%M%S')}"
    out = out_dir / f"{stem}.mp4"
    n = 2
    while out.exists():
        out = out_dir / f"{stem}-{n}.mp4"
        n += 1
    # ffmpeg 是阻塞调用 → 丢线程，别把整个服务卡住（连轮询都排不上）
    await asyncio.to_thread(drama_compose.render, fresh, out,
                            ass_text=ass_text, font_path=font or "")

    comp["plan"] = fresh
    outputs = dict(comp.get("outputs") or {})
    outputs["mp4"] = out.name
    comp["outputs"] = outputs
    comp["at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    comp["freecut"] = True
    # 快剪也是「一次合成」，导出页的「历史成片」要能回看它 —— 与 `compose_run`
    # 共用同一列，不能让快剪成片在历史里消失。
    hist = [h for h in (comp.get("history") or []) if isinstance(h, dict)]
    hist.insert(0, {"mp4": out.name, "at": comp["at"], "label": "素材混剪",
                    "seconds": fresh.get("total_seconds"), "ratio": fresh.get("ratio"),
                    "resolution": prof.get("resolution")})
    comp["history"] = hist[:20]
    doc["compose"] = comp
    return {"summary": "快剪成片完成：" + out.name + voice_note}


async def _pipeline_run_job(pid: str, stages: list[str], body: PipelineIn) -> None:
    for st in stages:
        try:
            doc = _load(pid)
            run = dict(doc.get("pipeline") or {})
            run["stage"] = st
            run["status"] = "running"
            doc["pipeline"] = run
            _save(doc)

            await asyncio.sleep(0)
            # 三段都是阻塞调用（LLM / 联网下载 / ffmpeg）→ 丢到线程里跑，
            # 否则整个服务在合成期间会卡住（连轮询都排不上）
            if st == "judge":
                res = await asyncio.to_thread(_pipeline_stage_judge, doc)
            elif st == "stock_fill":
                res = await asyncio.to_thread(_pipeline_stage_stock, doc, body)
            else:
                # 快剪的合成阶段是 async（要先补免费配音），内部自己把 ffmpeg 丢线程
                res = await _pipeline_stage_compose(pid, doc)

            run = dict(doc.get("pipeline") or {})
            results = dict(run.get("results") or {})
            results[st] = {**res, "at": time.strftime("%Y-%m-%d %H:%M:%S")}
            run["results"] = results
            doc["pipeline"] = run
            _save(doc)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("[drama] pipeline 在 %s 失败: %s", st, e)
            try:
                doc = _load(pid)
                run = dict(doc.get("pipeline") or {})
                run["status"] = "failed"
                run["error"] = f"{drama_pipeline.label(st)}失败：{str(e)[:200]}"
                run["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
                doc["pipeline"] = run
                _save(doc)
            except Exception:  # noqa: BLE001
                pass
            break

    try:
        doc = _load(pid)
        run = dict(doc.get("pipeline") or {})
        if run.get("status") == "running":
            run["status"] = "done"
            run["stage"] = ""
            run["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
            doc["pipeline"] = run
            _save(doc)
    except Exception:  # noqa: BLE001
        pass
    finally:
        _PIPELINE_JOBS.pop(pid, None)


@router.post("/projects/{pid}/pipeline")
async def pipeline_start(pid: str, body: PipelineIn = PipelineIn()):
    """从 `from_stage` 开始跑免费链（判官 → 配画面 → 合成），后台执行、进度落盘。

    🩸 不出片：这三段都不调用视频模型；要出片仍由使用者一段一段点。
    """
    try:
        _load(pid)
    except KeyError:
        return fail("项目不存在")

    job = _PIPELINE_JOBS.get(pid)
    if job and not job.done():
        return fail("这条流水线已经在跑了，等它跑完再看")

    stages = drama_pipeline.stages_from(body.from_stage)
    doc = _load(pid)
    doc["pipeline"] = drama_pipeline.new_run(stages)
    _save(doc)

    _PIPELINE_JOBS[pid] = asyncio.create_task(_pipeline_run_job(pid, stages, body))
    return ok(doc["pipeline"])


@router.get("/projects/{pid}/pipeline")
def pipeline_state(pid: str):
    """流水线状态（前端轮询这个）。跑着但进程里没任务 = 中断了，如实回报。"""
    try:
        doc = _load(pid)
    except KeyError:
        return fail("项目不存在")
    run = dict(doc.get("pipeline") or {})
    if not run:
        return ok({"status": "idle", "stages": [], "results": {}})
    if drama_pipeline.is_running(run) and pid not in _PIPELINE_JOBS:
        run["status"] = "interrupted"
        run["error"] = "上次跑到一半进程没了 —— 可以选一个阶段续跑"
    return ok(run)


@router.get("/task-center")
def task_center():
    """任务中心：进行中 / 需要处理 / 最近完成（竞品 TaskCenter 的三档口径）。

    - 付费出片（已发出去的钱）→ `paid`
    - 流水线（判官/配画面/合成）→ `running` / `attention` / `recent`
    - 批量作业 → `batch`
    """
    paid = drama_tasks.scan(_dir(), FILM_DIR, active=True)

    rows: list[dict] = []
    for p in sorted(_dir().glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(d, dict):  # 目录里混进非项目 json —— 跳过，别把接口打成 500
            continue
        run = d.get("pipeline") or {}
        status = str(run.get("status") or "")
        if status in ("", "idle"):
            continue
        rows.append({
            "project_id": d.get("id"),
            "project": (d.get("product") or {}).get("name") or d.get("topic") or "",
            "status": status,
            "stage": run.get("stage") or "",
            "stage_label": drama_pipeline.label(run.get("stage") or "") if run.get("stage") else "",
            "error": run.get("error") or "",
            "finished": run.get("finished") or "",
        })

    running = [r for r in rows if r["status"] in ("running", "interrupted")]
    attention = [r for r in rows if r["status"] == "failed"]
    recent = [r for r in rows if r["status"] == "done"][:5]

    _, state = _batch()
    try:
        job = drama_batch.get(state).get("job") or {}
    except Exception:  # noqa: BLE001
        job = {}

    return ok({
        "paid": paid,
        "running": running,
        "attention": attention,
        "recent": recent,
        "batch": drama_batch.summary(job) if job else {},
    })
