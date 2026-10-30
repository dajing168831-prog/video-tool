"""多语种配音：把用户写的中文文案逐句翻成目标语言（C6）。

**为什么要翻译，而不是只换音色**：选外语只换音色的话，提示词里会变成
`<d>[Thai] 你好</d>` —— 让泰语音色念中文。台词内容必须是目标语言原文。

**为什么不用机器翻译 API / 豆包翻译专用模型**（2026-10-25 查证）：
  · 火山机器翻译 API：官方《产品计费》写明要先「由销售人员进行签约」才能开通，
    短期用不上；而且它只翻不听指令，控不了长度。
  · `doubao-seed-translation`：专用接口，`system` 位是 JSON 配置
    （source/target），不是自由文本指令 —— 同样控不了长度（官方文档没找到，
    依据是第三方封装实现，标为未核实）。
  · 因此走**方舟通用模型**（`settings.vision_model`，视觉盘点已在用同一把 Key），
    它能听指令、能用 `json_schema` 锁住"行数一致、只输出译文"。

**行数为什么必须锁死**：配音是逐行合成的，行数一变，时间轴就对不上原片，
后面 `speech_spans` / 口型重画全跟着错。

**切句为什么不能用 `_split_script`**（2026-10-25 实测）：
中文按 14 字硬切，60 字变 10 行，每行 TTS 都有头尾静音 → 实测
英语 23.28s / 泰语 23.86s，而原片只有 13.88s（1.68 / 1.72 倍），直接撞出片闸门。
按**自然句**（4 行）重测：英语 1.05、泰语 1.18，再叠 +30% 语速 → 0.85 / 0.92。
⇒ 这里只按句末标点断句，**不做短句合并**。
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache

import httpx

log = logging.getLogger(__name__)

CHAT_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"

# 句末标点 = 管线里 `_split_script` 用的那一组（`clone_pipeline._PUNCT`）。
_SENT = re.compile(r"[。！？!?；;\n]+")

LANG_NAME = {
    "zh": "中文", "en": "英语", "ja": "日语", "ko": "韩语",
    "th": "泰语", "vi": "越南语", "id": "印尼语", "ms": "马来语",
    "tl": "菲律宾语", "es": "西班牙语", "mx": "西班牙语（拉美）",
    "pt": "葡萄牙语", "ru": "俄语", "ar": "阿拉伯语",
    "de": "德语", "fr": "法语", "it": "意大利语",
}

_SYS = (
    "你是专业的短视频本地化译者。把用户给的中文逐行翻译成目标语言。\n"
    "硬性要求：\n"
    "1. 输出行数与输入行数**完全一致**，一行对一行，不合并、不拆分、不增不减；\n"
    "2. 只输出译文本身：不加序号、引号、解释、注释或括号说明；\n"
    "3. 数字、价格、型号、品牌名**原样保留**，不翻译、不换算；\n"
    "4. 口语化、适合短视频口播，不要书面语；\n"
    "5. 每行都要能单独读通：结合整段语境翻译，但只写属于这一行的内容。"
)

_SCHEMA = {
    "type": "object",
    "properties": {"translations": {"type": "array", "items": {"type": "string"}}},
    "required": ["translations"],
}


class TranslateError(RuntimeError):
    pass


def split_sentences(text: str) -> list[str]:
    """只按句末标点断句，**不合并短句**（合并会把外语切成碎片，见模块注释）。"""
    parts = [s.strip() for s in _SENT.split(text or "") if s.strip()]
    return parts or ([text.strip()] if (text or "").strip() else [])


def _chat(lines: list[str], target: str, *, budget_note: str = "") -> tuple[list[str], dict]:
    from app.core.config import settings

    key = (settings.ark_api_key or "").strip()
    if not key:
        raise TranslateError("方舟未配置：请设置 VT_ARK_API_KEY")
    sys_msg = _SYS + (("\n6. " + budget_note) if budget_note else "")
    body = {
        "model": settings.vision_model,
        "messages": [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": json.dumps(
                {"source_language": "中文",
                 "target_language": LANG_NAME.get(target, target),
                 "lines": lines}, ensure_ascii=False)},
        ],
        # 方舟支持 json_schema 强约束：字段名和类型由接口保证，不靠提示词祈求
        "response_format": {"type": "json_schema",
                            "json_schema": {"name": "translation", "schema": _SCHEMA}},
        "temperature": 0.1,
        # 🩸 翻译不需要"思考"（2026-10-25 实测，同一段 8 行）：
        #   不关：81.9 秒 / 6340 tokens（其中 5629 是 reasoning）
        #   关掉：**4.5 秒 / 699 tokens** —— 快 18 倍、省 89%
        # 不关的后果不只是慢：文案 10 行以上必然撞 120s 超时，用户只看到"翻译失败"。
        "thinking": {"type": "disabled"},
    }
    try:
        with httpx.Client(timeout=120) as c:
            r = c.post(CHAT_URL, json=body, headers={
                "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    except httpx.HTTPError as e:
        raise TranslateError(f"翻译请求失败：{e}") from e
    if r.status_code >= 400:
        raise TranslateError(f"翻译接口 {r.status_code}：{r.text[:300]}")
    try:
        j = r.json()
        txt = j["choices"][0]["message"]["content"]
    except Exception as e:  # noqa: BLE001
        raise TranslateError(f"翻译响应结构异常：{e}") from e
    txt = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", (txt or "").strip())
    try:
        out = json.loads(txt).get("translations") or []
    except Exception as e:  # noqa: BLE001
        raise TranslateError(f"翻译结果不是合法 JSON：{e}") from e
    return [str(x or "").strip() for x in out], (j.get("usage") or {})


@lru_cache(maxsize=256)
def _translate_one(text: str, target: str) -> str:
    out, usage = _chat([text], target)
    if len(out) != 1:
        raise TranslateError(f"翻译行数对不上（{len(out)}/1）")
    log.info("单句翻译 %s → %s｜usage=%s", (text or "")[:30], target,
             {k: usage.get(k) for k in ("prompt_tokens", "completion_tokens")
              if usage.get(k) is not None})
    return (out[0] or "").strip()


def translate_text(text: str, target: str = "en") -> str:
    """把**一句自由文本**翻成目标语言（H3 的「补充说明」用这个）。

    和 `translate_lines` 的区别：不切句、不估时长、不做"压长短"重翻 ——
    补充说明是给模型看的一句话，不是要念出来的台词，长度不受配音时长约束。

    🩸 思考模式在 `_chat` 里已经写死关闭（关掉 4.5 秒 / 699 tokens，
    不关 81.9 秒 / 6340 tokens）。**这条路径只许走 `_chat`，不许另写请求**，
    否则那行 `thinking: disabled` 就白写了。

    🩸 进程内缓存 256 条：同一句补充说明会在**预览 → 出片 → 逐段重编译**里
    反复用到，翻一次就够，不重复花钱。
    """
    t = (text or "").strip()
    if not t:
        return ""
    tgt = (target or "en").strip().lower()
    if tgt in ("", "zh"):
        return t
    try:
        return _translate_one(t, tgt)
    except TranslateError:
        raise
    except Exception as e:  # noqa: BLE001
        raise TranslateError(f"翻译失败：{e}") from e


def translate_text_cache_clear() -> None:
    _translate_one.cache_clear()


def translate_lines(lines: list[str], target: str, *, source: str = "zh",
                    src_total: float = 0.0, max_passes: int = 2) -> dict:
    """逐行翻译，行数不变；总时长超预算时最多再压一轮。

    `src_total` > 0 时按 `speech_est` 估总时长，比值 > 1.15 就带预算重翻一次
    （不无限重试：模型压不动就是压不动，把比值如实返回给界面）。
    返回 `{lines, lang, ratio, passes, usage}`。
    """
    from app.services import speech_est

    src = [t for t in (lines or []) if (t or "").strip()]
    if not src:
        raise TranslateError("没有要翻译的文案")
    tgt = (target or "").strip().lower()
    if not tgt or tgt == (source or "zh").strip().lower():
        # 同语种不翻：直接原样返回（读读音校正那边照常处理）
        return {"lines": src, "lang": tgt or source, "ratio": 1.0,
                "passes": 0, "usage": {}}

    usage: dict = {}
    out, usage = _chat(src, tgt)
    passes = 1
    if len(out) != len(src):
        # 行数错位是硬错 —— 宁可再要一次，也不把错位的结果交出去
        log.warning("翻译行数不一致 %d/%d，重试一次", len(out), len(src))
        out, u2 = _chat(src, tgt)
        usage = u2 or usage
        passes += 1
        if len(out) != len(src):
            raise TranslateError(
                f"翻译行数对不上（{len(out)}/{len(src)}），已重试一次仍不一致")

    ratio = 1.0
    if src_total > 0:
        est = speech_est.estimate_all(out, tgt)
        ratio = est / src_total
        # 🩸 1.15 是实测定的：英语自然句 1.05、泰语 1.18（还要叠 +30% 语速）。
        # 超过就带预算重翻一轮，把"能省的虚词省掉"，而不是等到出片时才发现。
        while ratio > 1.15 and passes < max_passes:
            over = int(round((ratio - 1.0) * 100))
            note = (f"上一版译文比原句长 {over}%。请**更短**：能省的虚词、语气词一律省略，"
                    f"保留信息点和口语节奏，行数不变。")
            log.info("译文偏长 %.2f 倍，带预算重翻（第 %d 轮）", ratio, passes + 1)
            out2, u3 = _chat(src, tgt, budget_note=note)
            usage = u3 or usage
            passes += 1
            if len(out2) != len(src):
                break
            out = out2
            ratio = speech_est.estimate_all(out, tgt) / src_total

    return {"lines": out, "lang": tgt, "ratio": round(ratio, 4),
            "passes": passes, "usage": usage}
