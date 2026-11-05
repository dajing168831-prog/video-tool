"""先估时长、再选语速 —— 别等配音出来才发现长度差太多。

为什么要有这一步（hypit `creation/script-and-time.md`「Estimate before choosing
durations」）：新文案的长短决定它需要多少秒。等 TTS 出来再用 atempo 硬拉，
拉到 0.8–1.25 之外就会明显失真，拉不动的部分只能冻帧/截断，画面和声音就直接错位。

这里的估算和 hypit 的 `hypit estimate` 一样是**本地算的，不调模型、不花钱**：
  中文  一个汉字 ≈ 一个音节；英文按词折算音节；数字按位数
  标点  按停顿折算（同样字数，全是逗号的和全是句号的时长不一样）

`rate_for()` 把估算结果换算成豆包 TTS 的 `speech_rate`（正数=更快）。
先按估算把语速一次调到位，剩下的残差才交给 atempo —— 这样大部分情况下
atempo 都接近 1.0，配音不变调。
"""
from __future__ import annotations

import math
import re
import unicodedata

# 中文正常语速（speech_rate=0）每秒吐字。豆包 TTS 大致 4.5–5 字/秒，
# 取中位数 4.8；实测有系统偏差时用环境变量覆盖，别改这里。
ZH_CPS = 4.8
# 英文正常语速每秒音节
EN_SYL_PER_SEC = 3.6

# 其它语言的每秒音节数。
# 🩸 **官方没有给这张表**（豆包音色表只列音色，不列语速）—— 这是按各语言
# 正常语速的经验值，只用来**初选** `speech_rate`；剩下的残差由 `rate_for`
# 和后期 atempo 吸收（`rate_for` 会夹在 ±30%，atempo 再拉剩下的）。
# 出片后拿实测时长回来改这里的数，别在别处打补丁。
_SYL_PER_SEC = {
    "es": 5.0, "mx": 5.0, "pt": 4.8,
    "id": 4.5, "ms": 4.5, "tl": 4.5, "vi": 4.8,
    # 🩸 泰语 4.5 → 3.25（2026-10-25 实测，`D:/tmp/c6_validate2`）：
    # 豆包 `th_female_bv568_neutral_uranus_bigtts` 念 4 句泰语，实测量得
    # 16.37s，本表算出 11.82s —— **实测/估算 = 1.385**，偏低 38%。
    # 语速会被算小，等 atempo 顶到 1.25 才发现不够，那时画面已经冻帧了。
    # 样本只有 4 句 + 1 个音色，先按这个值；样本多了再校准。
    "th": 3.25, "ja": 7.0, "ko": 5.5,
    "ru": 4.5, "ar": 4.0,
    "de": 4.0, "fr": 4.0, "it": 4.0,
}

# 文字系统（用于数音节 + 自动判语言）
_KANA = re.compile(r"[぀-ヿ]")
_HANGUL = re.compile(r"[가-힯ᄀ-ᇿ]")
_THAI = re.compile(r"[฀-๿]")
_ARABIC = re.compile(r"[؀-ۿ]")
_CYRILLIC = re.compile(r"[Ѐ-ӿ]")
_CYR_VOWEL = re.compile(r"[аеёиоуыэюя]", re.I)


def _code(lang: str) -> str:
    """语言代码归一：`th-TH` / ` th ` 都认。"""
    return (lang or "zh").strip().lower().replace("_", "-").split("-", 1)[0] or "zh"


def _per_sec(lang: str, cps: float | None = None) -> float:
    """这种语言每秒几个音节（`cps` 显式给了就用它）。"""
    if cps and cps > 0:
        return cps
    code = _code(lang)
    if code == "zh":
        return ZH_CPS
    if code == "en":
        return EN_SYL_PER_SEC
    return _SYL_PER_SEC.get(code, EN_SYL_PER_SEC)


def _strip_accents(text: str) -> str:
    """去掉变音符号：越南语 `Tiếng Việt` → `Tieng Viet`。

    🩸 `[A-Za-z]` 只认 ASCII —— 不去符号的话越南语/葡语/西语一个音节都数不到，
    时长估成 0，语速算出来永远是 0（等于没估）。
    """
    return "".join(ch for ch in unicodedata.normalize("NFKD", text)
                   if not unicodedata.combining(ch))

# 标点当停顿。数字是"额外加多少秒"，不是"换成几秒"。
_PAUSE = {
    "，": 0.12, ",": 0.12,
    "、": 0.10,
    "：": 0.12, ":": 0.12,
    "；": 0.16, ";": 0.16,
    "。": 0.26, "！": 0.26, "？": 0.26, "!": 0.26, "?": 0.26,
    "…": 0.30, "—": 0.10,
}

# 语速可调范围。豆包官方收 **-50~100**（出处 `docs/2528925.md:172`，现行 HTTP 接口：
# 100 代表 2.0 倍速），
# 但超过 ±30 已经很假了 —— 宁可让调用方知道"文案该改"，也别把人声调成花栗鼠。
# 所以这里的 30 是**产品判断**，不是接口上限；接口上限由 provider 自己钳（tts.py）。
MAX_RATE = 30

_HAN = re.compile(r"[㐀-鿿豈-﫿]")
_LATIN = re.compile(r"[A-Za-z][A-Za-z0-9'’\-]*")
_DIGITS = re.compile(r"\d+")
_VOWELS = re.compile(r"[aeiouy]+")


# 这两组元音连写时几乎都是一字一音节（video = vi-de-o、radio = ra-di-o），
# 而 ea/ie/ue 多半仍是一个音节（cream / piece），所以只拆这几个
_SPLIT = ("eo", "ia", "io", "ua", "uo", "oa")


def _latin_syllables(word: str) -> int:
    """英文按元音组数估音节（"video"=3、"the"=1）。

    全大写缩写是逐字母念的：API = A-P-I = 3 个音节，不能按元音组算（那只数到 2）。
    """
    if word.isupper() and 1 <= len(word) <= 5:
        return len(word)
    groups = _VOWELS.findall(word.lower())
    n = len(groups)
    for g in groups:
        if any(part in g for part in _SPLIT):
            n += 1
    return max(1, n)


def detect_lang(text: str, default: str = "zh") -> str:
    """从识别原文猜语言。

    为什么要猜：ASR 那边 `lang` 是调用方传进去的默认值（一直是 zh），
    不是它识别出来的。英文原片照样标成中文 ⇒ 配音用中文音色、按中文语速估时长。

    🩸 只猜**文字系统能区分**的：日（假名）/ 韩（Hangul）/ 泰 / 阿拉伯 / 俄（西里尔）。
    越南语、印尼语、马来语、菲律宾语、西/葡/德/法/意都是拉丁字母，**文字上看不出来**，
    猜了只会猜错 —— 一律回落 `default`，由用户在界面上手选。

    汉字 vs 拉丁的判据是**占比**，不是"有没有英文"：中文文案里夹几个英文词很常见，
    反过来英文里出现一个中文品牌名也不该翻盘。
    """
    text = text or ""
    # 有独立文字系统的先按文字判（顺序有意义：日文夹汉字，必须假名先认）
    for code, rx in (("ja", _KANA), ("ko", _HANGUL), ("th", _THAI),
                     ("ar", _ARABIC), ("ru", _CYRILLIC)):
        if rx.search(text):
            return code
    han = len(_HAN.findall(text))
    latin = sum(len(w) for w in _LATIN.findall(text))
    if han == 0 and latin == 0:
        return default
    if han == 0:
        return "en"
    if latin == 0:
        return "zh"
    return "en" if han / (han + latin) < 0.35 else "zh"


def syllables(text: str, lang: str = "zh") -> float:
    """按语言口径数音节。

    中文汉字=1、英文按元音组、数字按位数折算（老口径不变）；小语种各按各的文字：
      · 拉丁字母系（西/葡/印尼/马来/菲/越）→ 去变音符号后按英文元音组数
      · 日（假名逐字）/ 韩（Hangul 逐字）→ 一字一拍
      · 泰 → 字符数 ÷ 3（无空格，且带声调符号）· 俄 → 西里尔元音字母数
      · 阿 → 字符数 ÷ 2.5（阿语不写短元音，字母数远小于音节数）
    """
    text = text or ""
    code = _code(lang)
    zh = code == "zh"
    n = 0.0
    n += len(_HAN.findall(text))
    if code == "ja":
        n += len(_KANA.findall(text))
    elif code == "ko":
        n += len(_HANGUL.findall(text))
    elif code == "th":
        n += len(_THAI.findall(text)) / 3.0
    elif code == "ar":
        n += len(_ARABIC.findall(text)) / 2.5
    elif code == "ru":
        n += len(_CYR_VOWEL.findall(text))
    for w in _LATIN.findall(_strip_accents(text)):
        n += _latin_syllables(w)
    for d in _DIGITS.findall(text):
        # 中文念数字是一位一位念（2026 → 二零二六，4 个音节）；
        # 其它语言念成数词（1999 → nineteen ninety-nine，约 5 个音节）
        n += len(d) if zh else max(1.0, round(len(d) * 1.5))
    return n


def pauses(text: str) -> float:
    return sum(_PAUSE.get(ch, 0.0) for ch in (text or ""))


def estimate(text: str, lang: str = "zh", *, cps: float | None = None) -> float:
    """估这段字念完要几秒（speech_rate=0）。空文本返回 0。"""
    if not (text or "").strip():
        return 0.0
    syl = syllables(text, lang)
    return round(syl / _per_sec(lang, cps) + pauses(text), 3)


def estimate_all(texts, lang: str = "zh", *, cps: float | None = None) -> float:
    return round(sum(estimate(t, lang, cps=cps) for t in texts or []), 3)


def rate_for(est: float, target: float, *, max_rate: int = MAX_RATE) -> int:
    """要念成 target 秒，语速该调多少个百分点。

    est 比 target 长 → 要更快 → 正数（豆包：正数=更快）。
    返回整数百分点，夹在 ±max_rate。任一边缺数就返回 0（不调）。
    """
    if est <= 0 or target <= 0:
        return 0
    pct = (est / target - 1.0) * 100.0
    return int(max(-max_rate, min(max_rate, round(pct))))


def residual_ratio(est: float, target: float, rate: int) -> float:
    """按这个语速念完之后，实际时长 / 目标时长的残差比（1.0 = 正好）。"""
    if target <= 0:
        return 1.0
    sped = est / (1.0 + rate / 100.0)
    return sped / target


def advise(text: str, target: float, lang: str = "zh", *,
           cps: float | None = None, max_rate: int = MAX_RATE) -> dict:
    """给一句可执行的建议：估多久、语速调多少、还差多少、要删/加几个字。

    verdict：
      ok    调完语速就能落在 ±15% 内，可以直接出片
      long  调完还是太长 → 文案要删字（trim_chars）
      short 调完还是太短 → 文案要加字，或者接受冻帧补时长
    """
    est = estimate(text, lang, cps=cps)
    rate = rate_for(est, target, max_rate=max_rate)
    resid = residual_ratio(est, target, rate)
    out = {
        "est_seconds": est,
        "target_seconds": round(float(target or 0), 3),
        "speech_rate": rate,
        "ratio": round(resid, 3),
        "verdict": "ok",
        "trim_chars": 0,
    }
    if not text or not text.strip() or target <= 0:
        return out

    per_sec = _per_sec(lang, cps)
    if resid > 1.15:
        out["verdict"] = "long"
        # 要念到 target 秒，最多能留多少音节
        keep = max(1.0, target * (1.0 + rate / 100.0) * per_sec)
        out["trim_chars"] = int(max(1, math.ceil(syllables(text, lang) - keep)))
    elif resid < 0.85:
        out["verdict"] = "short"
        need = target * (1.0 + rate / 100.0) * per_sec - syllables(text, lang)
        out["add_chars"] = int(max(1, math.ceil(need)))
    return out
