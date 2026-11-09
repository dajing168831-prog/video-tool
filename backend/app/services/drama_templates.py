"""成片模板库（391 条）+ 定制 / 分享 / 打包 —— 「模板经济」的整套逻辑。

出处：clipforge `src/lib/ad-templates.ts`（`AD_TEMPLATES` 数据与全部纯函数）
+ `src/app/api/ad-template/generate/route.ts`（AI 定制提示词）
+ `src/app/api/ad-template/mine/route.ts`（我的模板 CRUD 语义）。
数据由 `scripts/import_clipforge_presets.py` 原样抽进 `app/data/ad_templates.json`
和 `app/data/template_signals.json`（**不是重打一遍**）。

一个模板 = 一份**成片配方**：画面形态 + 全局 Look + 每类分镜的运镜 + 合成参数
+ 一句给剧本模型的方向。选它不等于套死，每一层用户都能再改
（竞品 `ad-templates.ts:44-68` 的字段注释就是这个意思）。

三条这一份特有的判据，**照抄不改**：
  1. 关键词推荐是「格式专为这个特性而生」（+2）重于「类目沾边」（+3/−2），
     平局按策划顺序 —— 纯函数、可复现（`:5560-5588`）。
  2. 导入的模板永远不拒绝、只警告：广告法词表命中的是「配方文案」不是
     「已发布口播」，14/391 条自家模板都会被命中，词面拒绝全是假阳性；
     硬闸留在合成阶段扫真实口播（`:5749-5762`）。
  3. 分享/打包时 **剥掉 id**，id 由导入方自己生成（`:5780-5839`）。
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from . import drama_camera, drama_captions, drama_compliance, drama_looks

DATA = Path(__file__).resolve().parents[1] / "data"
TPL_FILE = DATA / "ad_templates.json"
SIG_FILE = DATA / "template_signals.json"

#: 模板分组 —— 按「成片长什么样」分，不按内部脚本风格分（`:24-38`）
GROUPS = [
    {"id": "product_show", "name": "商品展示"},
    {"id": "presenter", "name": "真人讲解"},
    {"id": "story", "name": "剧情叙事"},
    {"id": "lifestyle", "name": "生活种草"},
    {"id": "promo", "name": "促销转化"},
    {"id": "creative", "name": "创意视觉"},
]
GROUP_IDS = [g["id"] for g in GROUPS]

#: 商品类目（新项目类目词汇；不填 = 通用）（`:41-42`）
CATEGORIES = ["beauty", "food", "home", "fashion", "digital"]

#: 我们的建项表单存中文类目（`drama.py:CATEGORIES`），模板库用英文 id。
#: 这张表就是两者之间**唯一**的换算处，别在别处再写一套。
CATEGORY_MAP = {"美妆护肤": "beauty", "食品零食": "food", "家居日用": "home",
                "服饰鞋包": "fashion", "数码3C": "digital"}


def category_id(zh: str | None) -> str:
    """中文类目 → 模板库 id；认不出（含「其他」）返回空串 = 不按类目加权。"""
    return CATEGORY_MAP.get((zh or "").strip(), "")

#: AI 定制模板的固定 id（每个项目只有一个定制槽）（`:5593`）
CUSTOM_ID = "custom_ai"

# --- 校验词表（`:5595-5608`，逐字） ---
STYLE_VALUES = {"drama", "reversal", "interview", "story", "unboxing", "product_pov",
                "comparison", "talking_head", "pain-point", "scenario", "auto"}
VIDEO_MODES = {"product_closeup", "graphic_montage", "scene_demo", "live_presenter"}
BGM_VALUES = ["none", "upbeat", "chill", "energetic", "emotional"]
QUALITY_VALUES = ["fast", "standard", "hd"]
SHOT_TYPES = ["hook", "pain_point", "product_reveal", "demo", "social_proof", "cta"]
GROUP_BY_MODE = {
    "product_closeup": "product_show",
    "graphic_montage": "creative",
    "scene_demo": "lifestyle",
    "live_presenter": "presenter",
}

#: cameraPlan 不足 2 个时垫的默认四镜（`:5640`）
FALLBACK_CAMERA_PLAN = {"hook": "crash_push", "product_reveal": "orbit_slow",
                        "demo": "macro_glide", "cta": "push_then_hold"}

#: 分镜类型标签（剧本侧的运镜指令里用）（`:5704-5711`）
PLAN_TYPE_LABELS = {
    "hook": "钩子镜(hook)",
    "pain_point": "痛点镜(pain_point)",
    "product_reveal": "商品镜(product_reveal)",
    "demo": "演示镜(demo)",
    "social_proof": "背书镜(social_proof)",
    "cta": "转化镜(cta)",
}

#: 内联存储前缀（我自己/用户自建的模板只存在于库里，不能只存 id）（`:5676`）
STORED_PREFIX = "custom:"

# --- 分享格式（`:5763-5885`） ---
SHARE_KIND = "clipforge-ad-template"
PACK_KIND = "clipforge-ad-template-pack"
SHARE_VERSION = 1
PACK_MAX = 100

SHARE_ERRORS = {
    "invalid_json": "不是有效的 JSON 文本",
    "wrong_kind": "不是商品短剧模板分享文件",
    "unsupported_version": "模板文件版本比当前应用新，请先升级",
    "invalid_template": "模板内容无法解析",
}

#: 编辑器下拉词表 —— 直接来自校验那几个集合，编辑器永远开不出校验会拒的值（`:5876-5885`）
EDIT_VOCAB = {"bgm": BGM_VALUES, "quality": QUALITY_VALUES, "shotTypes": SHOT_TYPES}


@lru_cache(maxsize=1)
def _all() -> tuple[dict, ...]:
    return tuple(json.loads(TPL_FILE.read_text(encoding="utf-8")))


@lru_cache(maxsize=1)
def _signals() -> tuple[tuple[re.Pattern, list[str]], ...]:
    raw = json.loads(SIG_FILE.read_text(encoding="utf-8"))["signals"]
    return tuple((re.compile(s["pattern"], re.I if "i" in s.get("flags", "") else 0), s["ids"])
                 for s in raw)


def all_templates() -> list[dict]:
    return list(_all())


def count() -> int:
    return len(_all())


def get(tid: str | None) -> dict | None:
    if not tid:
        return None
    return next((t for t in _all() if t.get("id") == tid), None)


def list_templates(*, group: str | None = None, category: str | None = None,
                   query: str | None = None) -> list[dict]:
    """挑模板用的列表：分组过滤 + 关键词（双语名/卖点，忽略大小写）。

    选了商品类目时，类目对口的那批**整体前移**（稳定分区，各自内部保持策划顺序）
    —— 与竞品 `:5438-5453` 一致。
    """
    pool = ([t for t in _all() if t.get("group") == group]
            if group and group != "all" else list(_all()))
    q = (query or "").strip().lower()
    if q:
        def hit(t):
            name, tag = t.get("name") or {}, t.get("tagline") or {}
            return any(q in str(v).lower() for v in
                       (name.get("zh"), name.get("en"), tag.get("zh"), tag.get("en")) if v)
        pool = [t for t in pool if hit(t)]
    if not category:
        return pool
    yes = [t for t in pool if category in (t.get("goodFor") or [])]
    no = [t for t in pool if category not in (t.get("goodFor") or [])]
    return yes + no


def recommend(category: str = "", product_name: str = "", selling_points: str = "",
              limit: int = 4) -> list[dict]:
    """按具体商品推荐模板（`ad-templates.ts:5560-5588` 逐条照抄）。

    命中「专为这个特性而生」的关键词信号 +2/条，类目对口 +3、不对口 −2；
    只留正分，平局按策划顺序 —— 纯函数、可复现。
    空输入返回空列表（界面把这一行藏起来，不给假推荐）。
    """
    text = f"{product_name or ''} {selling_points or ''}".strip()
    if not text and not category:
        return []
    boosts: dict[str, int] = {}
    if text:
        for pattern, ids in _signals():
            if not pattern.search(text):
                continue
            for tid in ids:
                boosts[tid] = boosts.get(tid, 0) + 2
    scored = []
    for i, t in enumerate(_all()):
        score = boosts.get(t.get("id") or "", 0)
        if category and t.get("goodFor") is not None:
            score += 3 if category in (t.get("goodFor") or []) else -2
        if score > 0:
            scored.append((score, i, t))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [t for _, _, t in scored[:limit]]


# ==================== AI 定制配方（夹取，不失败） ====================

def _str(v, maxlen: int = 120) -> str:
    return v.strip()[:maxlen] if isinstance(v, str) else ""


def sanitize(raw) -> dict | None:
    """把 LLM 吐的模板对象夹成**保证合法**的配方（`ad-templates.ts:5610-5673`）。

    每个字段都对着真实词表校验，不合法就落安全默认 —— 模型的创意在合法处保留，
    管线永远收不到未知 id。只有「压根不是对象」才返回 None。
    """
    if not isinstance(raw, dict):
        return None
    name_raw = raw.get("name") if isinstance(raw.get("name"), dict) else {}
    tag_raw = raw.get("tagline") if isinstance(raw.get("tagline"), dict) else {}
    hint_raw = raw.get("scriptHint") if isinstance(raw.get("scriptHint"), dict) else {}

    video_mode = raw.get("videoMode") if raw.get("videoMode") in VIDEO_MODES else "product_closeup"
    group_raw = raw.get("group")
    group = group_raw if group_raw in GROUP_IDS else GROUP_BY_MODE[video_mode]

    plan: dict[str, str] = {}
    if isinstance(raw.get("cameraPlan"), dict):
        for k, v in raw["cameraPlan"].items():
            if k in SHOT_TYPES and isinstance(v, str) and drama_camera.valid(v):
                plan[k] = v
    if len(plan) < 2:
        plan.update(FALLBACK_CAMERA_PLAN)

    c = raw.get("compose") if isinstance(raw.get("compose"), dict) else {}
    compose = {
        "captionPreset": c.get("captionPreset") if drama_captions.valid(c.get("captionPreset")) else "standard",
        "bgm": c.get("bgm") if c.get("bgm") in BGM_VALUES else "upbeat",
        "bgmDuck": c.get("bgmDuck") if isinstance(c.get("bgmDuck"), bool) else True,
    }
    if c.get("quality") in QUALITY_VALUES:
        compose["quality"] = c["quality"]
    if isinstance(c.get("productCard"), bool):
        compose["productCard"] = c["productCard"]

    good_for = ([x for x in raw.get("goodFor") if x in CATEGORIES]
                if isinstance(raw.get("goodFor"), list) else [])

    out = {
        "id": CUSTOM_ID,
        "emoji": _str(raw.get("emoji"), 8) or "✨",
        "name": {"zh": _str(name_raw.get("zh"), 24) or "AI定制模板",
                 "en": _str(name_raw.get("en"), 48) or "AI Custom"},
        "tagline": {"zh": _str(tag_raw.get("zh"), 60) or "AI 按你的商品定制的成片配方",
                    "en": _str(tag_raw.get("en"), 120) or "An AI-tailored recipe for this product"},
        "group": group,
        "styleType": raw.get("styleType") if raw.get("styleType") in STYLE_VALUES else "pain-point",
        "videoMode": video_mode,
        "look": raw.get("look") if drama_looks.valid(raw.get("look")) else "daylight_clean",
        "cameraPlan": plan,
        "compose": compose,
        "scriptHint": {"zh": _str(hint_raw.get("zh"), 300) or "围绕商品核心卖点展开，节奏紧凑，画面与口播互补"},
    }
    if good_for:
        out["goodFor"] = good_for
    return out


# ==================== 存储（项目选中了哪个模板） ====================

def encode_stored(template: dict) -> str:
    """内置模板存 id；其他（AI 定制 / 我的模板）存内联 JSON。

    判据用**库查找**而不是 `custom_ai` 哨兵：我的模板 id 只在库里存在，
    纯存 id 解不回来（`ad-templates.ts:5678-5688`）。
    """
    tid = template.get("id") or ""
    return tid if get(tid) else STORED_PREFIX + json.dumps(template, ensure_ascii=False)


def decode_stored(raw: str | None) -> dict | None:
    if not raw:
        return None
    if raw.startswith(STORED_PREFIX):
        try:
            return sanitize(json.loads(raw[len(STORED_PREFIX):]))
        except Exception:
            return None
    return get(raw)


# ==================== 给剧本模型的方向块 ====================

def script_directive(template: dict) -> str:
    """模板的创作方向块，作为「自定义要求」追加进剧本提示词（`:5713-5735`）。

    只写进 `Shot.camera` 这一层，后面就照常走运镜引擎，不用额外接线，
    而且每一镜用户还能再改。
    """
    name = (template.get("name") or {}).get("zh") or ""
    hint = (template.get("scriptHint") or {}).get("zh") or ""
    lines = [f"【成片模板：{name}】{hint}。"]
    look = drama_looks.get(template.get("look"))
    if look:
        lines.append(f"画面光线与色调统一为「{(look.get('name') or {}).get('zh')}」："
                     f"{(look.get('image') or {}).get('zh')}。")
    plan = []
    for typ, pid in (template.get("cameraPlan") or {}).items():
        sentence = drama_camera.prompt_of(pid) if pid else ""
        if sentence:
            plan.append(f"{PLAN_TYPE_LABELS.get(typ, typ)} 的 camera 写「{sentence}」")
    if plan:
        lines.append(f"运镜编排（对应类型的分镜按此填写 camera 字段）：{'；'.join(plan)}。")
    return "".join(lines)


# ==================== 分享 / 打包 ====================

def _recipe(t: dict) -> dict:
    return {k: v for k, v in t.items() if k != "id"}


def compliance_terms(template: dict) -> list[str]:
    """配方文案里的广告法词面命中（名字/卖点/方向各一句）—— 只警告不拦。"""
    text = " \n ".join([(template.get("name") or {}).get("zh") or "",
                        (template.get("tagline") or {}).get("zh") or "",
                        (template.get("scriptHint") or {}).get("zh") or ""])
    return [v["term"] for v in drama_compliance.check_ad(text)]


def export_share(template: dict) -> str:
    return json.dumps({"kind": SHARE_KIND, "version": SHARE_VERSION,
                       "template": _recipe(template)}, ensure_ascii=False, indent=2)


def parse_share(raw: str) -> dict:
    """解析单条分享文件 → `{"template"?, "error"?, "warnings"?}`。"""
    try:
        parsed = json.loads(raw)
    except Exception:
        return {"error": "invalid_json"}
    if not isinstance(parsed, dict) or parsed.get("kind") != SHARE_KIND:
        return {"error": "wrong_kind"}
    if parsed.get("version") != SHARE_VERSION:
        return {"error": "unsupported_version"}
    template = sanitize(parsed.get("template"))
    if not template:
        return {"error": "invalid_template"}
    out = {"template": template}
    warnings = compliance_terms(template)
    if warnings:
        out["warnings"] = warnings
    return out


def export_pack(templates: list[dict]) -> str:
    return json.dumps({"kind": PACK_KIND, "version": SHARE_VERSION,
                       "templates": [_recipe(t) for t in templates]},
                      ensure_ascii=False, indent=2)


def parse_share_any(raw: str) -> dict:
    """同一个粘贴框吃两种文件（单条 / 打包）（`:5841-5874`）。

    打包逐条夹取；不是对象的条目直接丢；全丢光才报错。警告取并集。
    """
    try:
        parsed = json.loads(raw)
    except Exception:
        return {"error": "invalid_json"}
    if not isinstance(parsed, dict) or parsed.get("kind") not in (SHARE_KIND, PACK_KIND):
        return {"error": "wrong_kind"}
    if parsed.get("version") != SHARE_VERSION:
        return {"error": "unsupported_version"}
    entries = parsed.get("templates") if parsed.get("kind") == PACK_KIND else [parsed.get("template")]
    if not isinstance(entries, list):
        entries = []
    templates = [t for t in (sanitize(e) for e in entries[:PACK_MAX]) if t]
    if not templates:
        return {"error": "invalid_template"}
    out = {"templates": templates}
    warnings = list(dict.fromkeys(w for t in templates for w in compliance_terms(t)))
    if warnings:
        out["warnings"] = warnings
    return out


# ==================== 界面用的视图 ====================

def public(template: dict | None) -> dict | None:
    """补上人看得懂的名字（分组名 / 运镜名 / 类目名），前端不用自己查表。"""
    if not template:
        return None
    out = dict(template)
    out["group_name"] = next((g["name"] for g in GROUPS if g["id"] == template.get("group")), "")
    out["camera_names"] = {k: ((drama_camera.get(v) or {}).get("name") or {}).get("zh") or v
                           for k, v in (template.get("cameraPlan") or {}).items()}
    out["look_name"] = ((drama_looks.get(template.get("look")) or {}).get("name") or {}).get("zh") or ""
    return out


def groups_public() -> list[dict]:
    return [dict(g) for g in GROUPS]


# ==================== AI 定制（`/api/ad-template/generate` 的提示词，逐字） ====================

STYLE_GLOSS = {
    "pain-point": "痛点解决式",
    "scenario": "场景种草式",
    "comparison": "对比测评式",
    "story": "故事叙事式",
    "drama": "双人情景短剧",
    "reversal": "反转剧情",
    "interview": "街访/采访体",
    "unboxing": "开箱体验",
    "product_pov": "商品第一人称/画面主导",
    "talking_head": "达人口播",
}
VIDEO_MODE_GLOSS = {
    "product_closeup": "商品特写为主",
    "graphic_montage": "图文快闪拼贴",
    "scene_demo": "真实场景演示",
    "live_presenter": "真人出镜讲解",
}


def build_custom_prompt(product_name: str, category: str = "", selling_points: str = "") -> str:
    """给 LLM 的「定制模板」提示词（`ad-template/generate/route.ts:42-67` 逐字）。

    模型只从真实词表里**挑**，挑错了由 `sanitize` 夹回安全值 —— 不是靠提示词保证。
    """
    styles = "、".join(f"{k}({v})" for k, v in STYLE_GLOSS.items())
    modes = "、".join(f"{k}({v})" for k, v in VIDEO_MODE_GLOSS.items())
    looks = "、".join(f"{p['id']}({(p.get('name') or {}).get('zh')})"
                     for p in drama_looks.all_presets())
    cameras = "、".join(f"{p['id']}({(p.get('name') or {}).get('zh')})"
                       for p in drama_camera.all_presets())
    groups = "、".join(f"{g['id']}({g['name']})" for g in GROUPS)
    lines = [
        "为下面这个商品定制一款带货短视频「成片模板」配方，所有枚举字段只能从给定词表中选：",
        f"商品名称：{product_name}",
        f"商品类目：{category}" if category else "",
        f"核心卖点：{selling_points}" if selling_points else "",
        "",
        "词表：",
        f"- styleType（脚本风格）：{styles}",
        f"- videoMode（画面形态）：{modes}",
        f"- look（画面光线色调）：{looks}",
        f"- 运镜预设 id：{cameras}",
        f"- group（模板分组）：{groups}",
        "- captionPreset：standard、bold、minimal、karaoke；"
        "bgm：none、upbeat、chill、energetic、emotional；quality：fast、standard、hd",
        "- cameraPlan 的键（镜头类型）：hook、pain_point、product_reveal、demo、social_proof、cta"
        "（选 3-5 个，值为运镜预设 id）",
        "",
        "要求：配方要针对这个商品的品类特性与卖点定制（如食品重食欲光与微距、数码重冷调与结构展示），"
        "scriptHint 用一句中文写清创意方向与叙事结构，内容真实合规"
        "（不得使用绝对化用语与虚假承诺）。",
        "只输出一个 JSON 对象，不要任何其他文字，格式：",
        '{"name":{"zh":"模板名(≤8字)","en":"English name"},'
        '"tagline":{"zh":"一句话卖点","en":"one-line pitch"},"emoji":"一个emoji",'
        f'"group":"...","goodFor":["{category_id(category) or "beauty"}"],'
        '"styleType":"...","videoMode":"...","look":"...",'
        '"cameraPlan":{"hook":"...","product_reveal":"...","demo":"...","cta":"..."},'
        '"compose":{"captionPreset":"...","bgm":"...","bgmDuck":true,'
        '"quality":"standard","productCard":true},"scriptHint":{"zh":"创意方向一句话"}}',
    ]
    return "\n".join(x for x in lines if x)          # 竞品 `.filter(Boolean)` 的等价写法


CUSTOM_SYS = "你是资深电商短视频导演，只输出 JSON。"
