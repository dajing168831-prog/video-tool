"""配音音色目录。

数据来自火山官方《豆包语音合成模型 2.0 音色列表》
（`docs.volcengine.com/docs/DoubaoVoice/Tonelist-1`，抓的是 SSR 直出的表格，
见 `app/data/voices.json` 里的 `source` 字段）。**不自己编音色 ID** ——
编一个不存在的 ID，用户点下去就是一次 403，还查不出为什么。

只收 `_uranus_bigtts`（对应 resource `seed-tts-2.0`，和 `VT_TTS_PROVIDER=volc`
用的资源一致）。声音复刻的 `S_` 开头音色是账号私有的，列不出来，但用户手填能过。
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)

_DATA = Path(__file__).resolve().parent.parent / "data" / "voices.json"

# 音色 ID 的语言前缀 → 给人看的语言名。顺序 = 界面上第二行的顺序：
# 东南亚（大鲸的主场）在前，日韩其次，欧西最后。
# 🩸 这张表**只列官方音色表里真实存在的前缀**（`app/data/voices.json` 里数出来的），
# 没有的语言不写进来 —— 写了就等于给用户一个选了会 403 的选项。
LANGS: dict[str, str] = {
    "id": "印尼语", "ms": "马来语", "th": "泰语", "vi": "越南语",
    "tl": "菲律宾语",
    "ja": "日语", "ko": "韩语",
    "es": "西班牙语", "mx": "西语（拉美）", "pt": "葡萄牙语",
    "ru": "俄语", "ar": "阿拉伯语",
    "de": "德语", "fr": "法语", "it": "意大利语",
}

# 同一门语言的不同地区音色互认（换语言不等于换口音）
_FAMILY = {"mx": "es"}

# 一级按钮上的两个常用语言（不进第二行）
_BASE_NAMES = {"zh": "中文", "en": "英文"}


def lang_name(code: str) -> str:
    """语言代码 → 中文名。查不到就原样返回代码，不编名字。"""
    c = _norm(code)
    return LANGS.get(c) or _BASE_NAMES.get(c) or c

# 中英文各给一个稳妥的默认：都是官方「通用场景」里的女声，
# 也是我们一路测下来在用的那条（小何），换默认值等于换所有人的出片听感
_FALLBACK = {
    "zh": "zh_female_xiaohe_uranus_bigtts",
    "en": "en_female_dacey_uranus_bigtts",
}


@lru_cache(maxsize=1)
def _all() -> list[dict]:
    try:
        raw = json.loads(_DATA.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        log.warning("音色目录读取失败，只用兜底音色：%s", e)
        return []
    return list(raw.get("voices") or [])


def _lang_of(voice_id: str) -> str:
    return (voice_id or "").split("_", 1)[0]


def _prefix(lang: str) -> str:
    """语言代码归一：`zh-CN` / `zh_CN` / ` zh ` 都认成 `zh`（不做家族合并）。"""
    v = (lang or "").strip().lower().replace("_", "-")
    return v.split("-", 1)[0] if v else ""


def _norm(lang: str) -> str:
    """语言代码归一 + 家族合并：`mx` 归到 `es`（同门语言，音色互认）。"""
    base = _prefix(lang)
    return _FAMILY.get(base, base) if base else ""


def list_for(lang: str = "") -> list[dict]:
    """按语言挑音色。lang 留空 = 全部。

    🩸 按**前缀精确匹配**。以前非 en 一律当 zh —— 于是 ja/ko/th/vi/id/ms/tl/es/pt…
    这 15 种语言的音色虽然在目录里，却永远列不出来（花名册里有、门口不给进）。
    不同语言用不同音色是硬要求：拿中文音色念泰语，出来的是"外国人学说泰语"。
    """
    lang = _prefix(lang)
    items = _all()
    if not lang:
        return items
    return [v for v in items if _prefix(_lang_of(v["id"])) == lang]


def languages() -> list[dict]:
    """可选语言 + 每种的音色数（给界面第二行用，前端不再维护第二份语言表）。"""
    items = _all()
    counts: dict[str, int] = {}
    for v in items:
        counts[_lang_of(v["id"])] = counts.get(_lang_of(v["id"]), 0) + 1
    out = [{"v": code, "t": name, "n": counts.get(code, 0)}
           for code, name in LANGS.items() if counts.get(code)]
    # 官方音色表以后新加的语言也要能出来（不至于因为没写进 LANGS 就消失）
    for code, n in counts.items():
        if code not in LANGS and code not in ("zh", "en"):
            out.append({"v": code, "t": code.upper(), "n": n})
    return out


def get(voice_id: str) -> dict | None:
    vid = (voice_id or "").strip()
    for v in _all():
        if v["id"] == vid:
            return v
    return None


# 泰语那批按情绪拆开的音色（`th_female_bv568_happy` 等）：当默认会让每句都带那情绪。
# `neutral` 不算——它本来就是中性。
_EMO = re.compile(r"_(happy|hate|angry|fear|sad|suprise|surprise)(_|$)")


def _rank(v: dict) -> tuple:
    """默认音色的排序键：通用场景 + 视频配音 > 只有通用 > 其它；同档里女声优先、
    不带情绪后缀优先。纯排序，不写死任何音色 ID。"""
    scene = set(v.get("scene") or [])
    bucket = 0 if ("通用场景" in scene and "视频配音" in scene) else (
        1 if "通用场景" in scene else 2)
    gender = 0 if v.get("gender") == "female" else 1
    emo = 1 if _EMO.search(v.get("id") or "") else 0
    # 情绪变体排最前：宁可要一个"只有通用场景"的中性音色，也不要每句都笑着念的
    return (emo, bucket, gender)


def default_for(lang: str = "zh") -> str:
    """该语言下的默认音色。目录里没有就回落到写死的那个。

    🩸 小语种**不能回落中文**：拿中文音色念泰语，出来是"外国人学说泰语"，
    而且用户看不出为什么。所以顺序是「写死的默认 → 该语言通用场景 → 该语言第一条」，
    只有该语言一条都没有时才退回 zh（那是数据出问题了）。
    """
    key = _prefix(lang) or "zh"
    items = list_for(key)
    # 写死的兜底优先：它是一路测下来在用的那条，改默认值等于改所有人的出片听感
    want = _FALLBACK.get(key)
    if want and any(v["id"] == want for v in items):
        return want
    if items:
        # 挑「通用场景 + 视频配音 + 不带情绪后缀」的那条：
        # 泰语表里 `th_female_bv568_happy/hate/…` 是按情绪拆的变体，拿 happy 当默认
        # 等于每句话都笑着念；角色扮演/有声阅读那些又偏戏。
        best = sorted(items, key=_rank)[0]
        return best["id"]
    return _FALLBACK.get(key, _FALLBACK["zh"])


def label(voice_id: str) -> str:
    """给人看的一行：`小何 2.0（女 · 通用场景）`。"""
    v = get(voice_id)
    if not v:
        return voice_id or ""
    bits = []
    if v.get("gender") == "female":
        bits.append("女")
    elif v.get("gender") == "male":
        bits.append("男")
    scene = [s for s in (v.get("scene") or []) if s != "通用场景"][:1]
    if scene:
        bits.append(scene[0])
    return f"{v['name']}（{' · '.join(bits)}）" if bits else v["name"]


def resolve(requested: str, lang: str = "zh") -> tuple[str, str]:
    """把用户传的音色收口成能发出去的 ID，并说清为什么。

    返回 (voice_id, note)。note 非空 = 发生了替换，要告诉用户。
    手填的 ID 目录里没有也放行 —— 声音复刻（`S_` 开头）本来就是账号私有的，
    列不出来不等于不能用；真用错了，火山会在合成时直接报，比我们猜要准。
    """
    vid = (requested or "").strip()
    if not vid:
        return default_for(lang), ""
    v = get(vid)
    if v is None:
        if vid.startswith("S_"):
            return vid, ""      # 声音复刻的私有音色，目录里本来就没有
        return default_for(lang), f"音色 {vid} 不在官方目录里，已换成默认音色"
    # 🩸 按**语言前缀**比对，不再只分「英文 / 非英文」：那样泰语音色配中文台词
    # 会被当成"一致"放过去（`want_en=False, is_en=False`），合成出来是怪口音。
    # `mx`（拉美西语）与 `es` 互认 —— 同一门语言的不同地区音色。
    want = _norm(lang) or "zh"
    got = _norm(_lang_of(vid))
    if want != got:
        return default_for(lang), (
            f"音色「{v['name']}」是{lang_name(got)}音色，"
            f"和当前配音语言（{lang_name(want)}）不一致，已换成默认音色"
        )
    return vid, ""


def summary() -> dict:
    items = _all()
    by: dict[str, int] = {}
    for v in items:
        by[_lang_of(v["id"])] = by.get(_lang_of(v["id"]), 0) + 1
    return {
        "total": len(items),
        "zh": by.get("zh", 0),
        "en": by.get("en", 0),
        "by_lang": by,
        "source": "https://docs.volcengine.com/docs/DoubaoVoice/Tonelist-1",
    }
