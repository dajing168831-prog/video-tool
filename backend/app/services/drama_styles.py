"""D7 风格配方（style pack）—— 纯 JSON 的合成设置配方，可导出、可分享、可导入。

出处：clipforge `src/lib/style-packs.ts:1-132`（逐条照抄口径）：
  · `:55-91` 导入是**逐字段白名单 + 逐字段丢弃**：坏 JSON / 格式标记不对 / 没名字 → 整份作废（None）；
    单个字段不合格只丢这个字段，不让整份失败（前向兼容：不认识的字段直接忽略）
  · `:73-75` 音量夹进 0.05–0.4 并保留两位 —— 注意 JS 的 `Math.round` 是**四舍五入**，
    与 Python 的 `round()`（银行家舍入，0.185→0.18）不同，这里用 `floor(x*100+0.5)` 对齐
  · `:81` CTA 文案 trim 后截 60 字；`:86-88` 名字截 60、说明截 200、作者截 60
  · `:94-96` 导出是 2 空格缩进的 JSON（给人手改）
  · `:17` 格式标记

我们的差异（逐条写清，别让使用者以为「一样」）：
  1. **只支持 6 个字段**：captionPreset / bgmVolume / bgmDuck / quality / ctaText / productCard。
     竞品另外两个字段在这边**没有对应的能力**，导入时进 `dropped` 并原样告诉用户，不假装应用：
       · `bgm`（情绪档 upbeat/chill/energetic/emotional/none）—— 我们的 BGM 是用户上传的**具体曲子**
         或 B3 搜来的具体文件（`drama_audio.py` 只管音量/闪避），没有按情绪分类的曲库
       · `aspectRatio` —— 合成固定 9:16（`api/drama.py` `compose_run` 里
         `RESOLUTIONS["9:16"][prof["resolution"]]` 写死）
  2. **接受竞品的格式标记** `clipforge-style-pack@1`（自己加的，非照抄）：社区里流通的配方多半是那个标记，
     字段同名同义；导入后能用的照用、不能用的进 `dropped`。导出**只写我们自己的标记**
     `video-tool-style-pack@1`，免得别人以为我们全量兼容。
  3. 我们导出时会**多带** `compose.captions`（字幕总开关）—— 竞品配方没有这个维度，
     但我们的合成设置里有，导出时不带就丢信息。导入侧也认它（缺省不改）。
"""
from __future__ import annotations

import json
import math

STYLE_PACK_FORMAT = "video-tool-style-pack@1"
ACCEPTED_FORMATS = (STYLE_PACK_FORMAT, "clipforge-style-pack@1")

#: 竞品白名单（`style-packs.ts:42-44`）
BGM_VALUES = ("none", "upbeat", "chill", "energetic", "emotional")
QUALITY_VALUES = ("fast", "standard", "hd")
ASPECT_VALUES = ("9:16", "16:9", "1:1")

#: 我们真正能落到合成设置里的字段（`api/drama.py` 的 `ComposeIn`）
SUPPORTED_KEYS = ("captionPreset", "captions", "bgmVolume", "bgmDuck",
                  "quality", "ctaText", "productCard")
#: 竞品有、我们没有的字段：导入时原样报给用户，不静默吞
UNSUPPORTED_KEYS = ("bgm", "aspectRatio")

MIN_BGM_VOLUME = 0.05
MAX_BGM_VOLUME = 0.4
NAME_MAX = 60
DESC_MAX = 200
AUTHOR_MAX = 60
CTA_MAX = 60

#: 内置配方（名字与说明是我们自己的措辞；参数组合取竞品 `:103-132` 的四套思路）
BUILTIN_PACKS = [
    {
        "format": STYLE_PACK_FORMAT,
        "name": "带货重击",
        "description": "粗体大字字幕 + 旁白闪避 + 开片尾卡，节奏紧、转化优先",
        "author": "video-tool",
        "compose": {"captionPreset": "bold", "bgmDuck": True,
                    "productCard": True, "quality": "standard"},
    },
    {
        "format": STYLE_PACK_FORMAT,
        "name": "卡拉OK爆款",
        "description": "逐字高亮字幕 + 旁白闪避，适合口播和强节奏",
        "author": "video-tool",
        "compose": {"captionPreset": "karaoke", "bgmDuck": True, "quality": "standard"},
    },
    {
        "format": STYLE_PACK_FORMAT,
        "name": "纪实极简",
        "description": "极简字幕、不闪避、高清输出，生活流干净画面",
        "author": "video-tool",
        "compose": {"captionPreset": "minimal", "bgmDuck": False, "quality": "hd"},
    },
    {
        "format": STYLE_PACK_FORMAT,
        "name": "标准通用",
        "description": "默认底板字幕 + 标准画质，任何题材直接可用",
        "author": "video-tool",
        "compose": {"captionPreset": "standard", "quality": "standard"},
    },
]


def _round2(v: float) -> float:
    """对齐 JS `Math.round(x*100)/100`（四舍五入，不是银行家舍入）。"""
    return math.floor(v * 100 + 0.5) / 100


def _pick_enum(v, allowed) -> str | None:
    return v if isinstance(v, str) and v in allowed else None


def _clean_text(v, limit: int) -> str | None:
    if not isinstance(v, str):
        return None
    s = v.strip()
    return s[:limit] if s else None


def _caption_id(v) -> str | None:
    # 延迟导入：本模块要能在不加载 ffmpeg 相关依赖的纯逻辑探针里跑
    from app.services import drama_captions

    return v if isinstance(v, str) and drama_captions.valid(v) else None


def parse_style_pack(json_text: str) -> tuple[dict | None, list[str]]:
    """解析 + 逐字段净化（`style-packs.ts:55-91`）。返回 `(pack, dropped)`。

    整份作废的条件只有三个：不是合法 JSON / 不是对象 / 格式标记不认 / 没名字。
    `dropped` 列的是「输入里有、但这台机器应用不了」的字段名，交给界面原样提示。
    """
    try:
        raw = json.loads(json_text or "")
    except (TypeError, ValueError):
        return None, []
    if not isinstance(raw, dict):
        return None, []
    if raw.get("format") not in ACCEPTED_FORMATS:
        return None, []
    name = _clean_text(raw.get("name"), NAME_MAX)
    if not name:
        return None, []

    raw_c = raw.get("compose")
    c = raw_c if isinstance(raw_c, dict) else {}
    compose: dict = {}

    cap = _caption_id(c.get("captionPreset"))
    if cap:
        compose["captionPreset"] = cap
    if isinstance(c.get("captions"), bool):
        compose["captions"] = c["captions"]
    vol = c.get("bgmVolume")
    if isinstance(vol, (int, float)) and not isinstance(vol, bool) \
            and math.isfinite(float(vol)):
        compose["bgmVolume"] = _round2(min(MAX_BGM_VOLUME, max(MIN_BGM_VOLUME, float(vol))))
    if isinstance(c.get("bgmDuck"), bool):
        compose["bgmDuck"] = c["bgmDuck"]
    quality = _pick_enum(c.get("quality"), QUALITY_VALUES)
    if quality:
        compose["quality"] = quality
    cta = _clean_text(c.get("ctaText"), CTA_MAX)
    if cta:
        compose["ctaText"] = cta
    if isinstance(c.get("productCard"), bool):
        compose["productCard"] = c["productCard"]

    # 竞品有、我们没能力的字段，以及完全不认识的字段 —— 都原样报给用户，
    # 免得「传了就等于生效」的错觉
    dropped = [k for k in UNSUPPORTED_KEYS if k in c]
    if isinstance(raw_c, dict):
        for k in raw_c:
            if k not in SUPPORTED_KEYS and k not in UNSUPPORTED_KEYS and k not in dropped:
                dropped.append(k)

    pack = {"format": STYLE_PACK_FORMAT, "name": name}
    desc = _clean_text(raw.get("description"), DESC_MAX)
    if desc:
        pack["description"] = desc
    author = _clean_text(raw.get("author"), AUTHOR_MAX)
    if author:
        pack["author"] = author
    pack["compose"] = compose
    return pack, dropped


def serialize_style_pack(pack: dict) -> str:
    """导出为可分享的 JSON 文本（2 空格缩进，`style-packs.ts:94-96`）。"""
    body = {
        "format": STYLE_PACK_FORMAT,
        "name": str(pack.get("name") or "未命名配方")[:NAME_MAX],
    }
    desc = _clean_text(pack.get("description"), DESC_MAX)
    if desc:
        body["description"] = desc
    author = _clean_text(pack.get("author"), AUTHOR_MAX)
    if author:
        body["author"] = author
    body["compose"] = dict(pack.get("compose") or {})
    return json.dumps(body, ensure_ascii=False, indent=2)


def pack_to_compose(pack: dict) -> dict:
    """配方 → 我们 `ComposeIn` 的字段名（只出**配方里确实有**的字段，方便做「只覆盖这几项」）。"""
    c = pack.get("compose") or {}
    out: dict = {}
    if "captionPreset" in c:
        out["caption_preset"] = c["captionPreset"]
    if "captions" in c:
        out["captions"] = bool(c["captions"])
    if "bgmVolume" in c:
        out["bgm_volume"] = c["bgmVolume"]
    if "bgmDuck" in c:
        out["bgm_duck"] = bool(c["bgmDuck"])
    if "quality" in c:
        out["render_preset"] = c["quality"]
    if "ctaText" in c:
        out["end_card_text"] = c["ctaText"]
    if "productCard" in c:
        out["end_card"] = bool(c["productCard"])
    return out


def compose_to_pack(options: dict | None, *, name: str = "当前设置",
                    description: str = "", author: str = "") -> dict:
    """把项目里存的合成设置（`compose.options`，`ComposeIn` 的扁平静态）转回配方。"""
    o = options or {}
    c: dict = {}
    cap = _caption_id(o.get("caption_preset"))
    if cap:
        c["captionPreset"] = cap
    if isinstance(o.get("captions"), bool):
        c["captions"] = o["captions"]
    vol = o.get("bgm_volume")
    if isinstance(vol, (int, float)) and not isinstance(vol, bool) and math.isfinite(float(vol)):
        c["bgmVolume"] = _round2(min(MAX_BGM_VOLUME, max(MIN_BGM_VOLUME, float(vol))))
    if isinstance(o.get("bgm_duck"), bool):
        c["bgmDuck"] = o["bgm_duck"]
    quality = _pick_enum(o.get("render_preset"), QUALITY_VALUES)
    if quality:
        c["quality"] = quality
    end = o.get("end_card") if isinstance(o.get("end_card"), dict) else {}
    if end.get("enabled") is not None:
        c["productCard"] = bool(end.get("enabled"))
    cta = _clean_text(o.get("end_card_text") or end.get("text"), CTA_MAX)
    if cta:
        c["ctaText"] = cta
    return {"format": STYLE_PACK_FORMAT, "name": name,
            "description": description, "author": author, "compose": c}


def merge_into_options(options: dict | None, patch: dict) -> dict:
    """把配方生成的覆盖项并进项目已存的合成设置（`end_card` 是嵌套对象，要合并不替换）。"""
    base = dict(options or {})
    end = dict(base.get("end_card") or {})
    for k, v in patch.items():
        if k == "end_card":
            end["enabled"] = bool(v)
        elif k == "end_card_text":
            # 只写进嵌套的 end_card.text —— 与 `compose_plan` 落盘的形状保持一致
            end["text"] = str(v)
        else:
            base[k] = v
    if end:
        base["end_card"] = end
    return base
