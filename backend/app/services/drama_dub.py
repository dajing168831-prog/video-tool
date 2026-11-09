"""D8 多语言译制（译词 → 重新配音 → 对轨）。

出处：
  · `api/project/[id]/dub/route.ts:1-84`：`POST` 要 `targetLang` + LLM 配置；
    没有脚本 404、脚本没分镜则拒；翻译后**新版本置为选中**，返回
    `{scriptId, version, targetLang, shots, recommendedVoice}`
  · `lib/script-engine/translate.ts:1-125`：
    - `LANG_NAMES` 13 种语言、`langName()`（支持 `en-US` 取前缀）
    - `defaultVoiceForLang()`：在免费音色表里找 `lang` 前缀匹配的第一个
    - `buildTranslatePrompt()`：逐行翻译、**不许合并或拆分、顺序与条数不变**、只回 JSON 数组
    - `parseTranslations()`：先剥 `<think>`，再取 ```json 围栏或第一对 `[]`，条数不符返回 null
    - `translateShots()`：只换台词，**description / stockKeywords 等画面字段原样保留**
      （同一批画面复用，只换音轨与字幕），并按译后文本重估每镜时长
  · `lib/script-import.ts:29-32`：`estimateDurationSec()` = CJK 5 字/秒、其它 14 字符/秒，夹 2–15 秒

我们的差异：
  1. 竞品把译制版存成 scripts 表的一个新版本并「置为选中」；我们是单份 `storyboard_json`，
     所以译制版存进 `project["dubs"][lang]`，**默认不动原分镜**，显式 `apply` 才写回，
     写回前把原分镜存 `dub_restore` 供一键还原（竞品有多版本表，不需要还原）。
  2. 我们字段叫 `dialogue`（竞品是 `voiceover`），其余照抄。
  3. 推荐音色直接用 D1 的免费 Edge 音色表 —— 译完可以零费用立刻重新配音。
"""
from __future__ import annotations

import json
import re
import time

#: 目标语言（`translate.ts:20-33` 原表）
LANG_NAMES = {
    "en": "English", "ja": "Japanese", "ko": "Korean", "es": "Spanish",
    "zh": "Chinese (Simplified)", "fr": "French", "de": "German",
    "pt": "Portuguese", "ru": "Russian", "id": "Indonesian", "th": "Thai",
    "vi": "Vietnamese", "ar": "Arabic",
}


def lang_name(code: str) -> str:
    c = (code or "").lower()
    return LANG_NAMES.get(c) or LANG_NAMES.get(c.split("-")[0], "") or code


def known_lang(code: str) -> bool:
    c = (code or "").lower()
    return c in LANG_NAMES or c.split("-")[0] in LANG_NAMES


def default_voice_for_lang(code: str) -> str | None:
    """目标语言 → 免费 Edge 音色（第一个 lang 前缀匹配的）；没有返回 None。"""
    from app.services.drama_tts import FREE_TTS_VOICES
    c = (code or "").lower().split("-")[0]
    if not c:
        return None
    for v in FREE_TTS_VOICES:
        if v["lang"].lower().startswith(c):
            return v["value"]
    return None


def build_translate_prompt(lines: list[str], target_lang: str) -> str:
    """逐行翻译提示词（`translate.ts:47-57` 原样）。"""
    target = lang_name(target_lang)
    numbered = "\n".join(f"{i + 1}. {v}" for i, v in enumerate(lines))
    return "\n".join([
        f"Translate the following {len(lines)} short-video narration lines into {target}.",
        "Keep each line punchy and natural for spoken voiceover. "
        "Do NOT merge or split lines; keep the same order and count.",
        f"Return ONLY a JSON array of {len(lines)} strings — "
        "no numbering, no markdown, no extra text.",
        "",
        numbered,
    ])


_THINK_RE = re.compile(r"<think\b[^>]*>[\s\S]*?</think\s*>", re.I)


def strip_think_blocks(text: str) -> str:
    """剥掉推理模型的 `<think>`（`translate.ts:63` 的 `stripThinkBlocks`）。"""
    return _THINK_RE.sub("", text or "")


def parse_translations(text: str, expected_count: int) -> list[str] | None:
    """从模型输出里取等长字符串数组；条数不符或格式不对返回 None（`translate.ts:60-79`）。"""
    if not text:
        return None
    text = strip_think_blocks(text)
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.I)
    raw = fenced.group(1) if fenced else text
    start, end = raw.find("["), raw.rfind("]")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        arr = json.loads(raw[start:end + 1])
    except (TypeError, ValueError):
        return None
    if not isinstance(arr, list) or len(arr) != expected_count:
        return None
    if not all(isinstance(x, str) for x in arr):
        return None
    return [x.strip() for x in arr]


_CJK_RE = re.compile(r"[⺀-鿿぀-ヿ가-힯豈-﫿]")


def estimate_duration_sec(text: str) -> int:
    """按字数估每镜时长（`script-import.ts:29-32`）：CJK 5 字/秒、其它 14 字符/秒，夹 2–15 秒。"""
    body = text or ""
    cps = 5 if _CJK_RE.search(body) else 14
    return min(15, max(2, round(len(body) / cps)))


class DubError(ValueError):
    """译制失败（给顾客看的人话）。"""


def _default_chat(prompt: str) -> str:
    """默认走 DeepSeek 官方（和剧本生成同一条通道）。"""
    from app.core.config import settings
    from app.services import deepseek_chat

    key = (settings.deepseek_api_key or "").strip()
    if not key:
        raise DubError("没有配置 VT_DEEPSEEK_API_KEY，无法翻译")
    try:
        data = deepseek_chat.post({
            "model": settings.deepseek_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "stream": False,
        }, key=key)
    except deepseek_chat.DeepSeekError as e:
        raise DubError(str(e)) from e
    try:
        return data["choices"][0]["message"]["content"]
    except Exception as e:  # noqa: BLE001
        raise DubError(f"翻译模型返回格式不对：{str(data)[:200]}") from e


def translate_lines(lines: list[str], target_lang: str, chat=None) -> list[str]:
    """批量翻译台词，返回等长数组；解析失败抛 `DubError`（`translate.ts:84-103`）。"""
    if not lines:
        return []
    if not known_lang(target_lang):
        raise DubError(f"不支持的目标语言：{target_lang}")
    text = (chat or _default_chat)(build_translate_prompt(lines, target_lang))
    out = parse_translations(text, len(lines))
    if not out:
        raise DubError("翻译结果解析失败（模型未返回等长 JSON 数组），可换模型或重试")
    return out


def translate_shots(shots: list[dict], target_lang: str, chat=None) -> list[dict]:
    """整份分镜译制：只换 `dialogue`，画面字段原样保留，重估 `duration`（`translate.ts:110-124`）。"""
    if not shots:
        return []
    lines = [str(s.get("dialogue") or "") for s in shots]
    translated = translate_lines(lines, target_lang, chat)
    out: list[dict] = []
    for i, s in enumerate(shots):
        line = translated[i] if translated[i] else lines[i]
        shot = dict(s)
        shot["dialogue"] = line
        shot["duration"] = estimate_duration_sec(line or lines[i])
        out.append(shot)
    return out


def dub_summary(shots: list[dict]) -> dict:
    return {"shots": len(shots),
            "duration": round(sum(float(s.get("duration") or 0) for s in shots), 2),
            "lines": sum(1 for s in shots if str(s.get("dialogue") or "").strip())}


def make_record(target_lang: str, shots: list[dict], *, title: str = "",
                source_title: str = "") -> dict:
    """一次译制的存档结构（竞品是新版本行，我们是 dubs[lang]）。"""
    name = lang_name(target_lang)
    return {
        "lang": (target_lang or "").lower(),
        "lang_name": name,
        "title": (title or f"[{name}] {source_title or '译制版'}")[:80],
        "recommended_voice": default_voice_for_lang(target_lang),
        "shots": shots,
        "summary": dub_summary(shots),
        "version": 1,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
