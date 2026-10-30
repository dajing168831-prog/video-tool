"""语义时间：把台词锚到**词**上，改词后自己重排，而不是从头按秒重切。

为什么要有这一层
----------------
现在改一句台词，整套时间轴是按"平均分给 N 段"重算的：改一个字，后面的段
全都跟着漂。原片里每个字本来就有精确时间（ASR 的 `chars: [{c,s,e}]`），
只是我们一直没用来做对齐。

这里的做法：
  1. 把原片的字级时间摊平成一条**源时间轴**；
  2. 新台词与原文做字符级比对（SequenceMatcher）；
  3. 没改的字**继承原时间**，改动的字在前后锚点之间按字数分配；
  4. 新台词按句子切段后，每段的窗口 = 段内第一个字到最后一个字的时间。

所以"改一句"只会动那一句，别的句子时间不变 —— 这是它和"平均分"的本质区别。

设计选择：**锚定保持**（不是全局推挤）
--------------------------------------
新写的字被安排在"前一个锚点结束 → 后一个锚点开始"之间，**不推动后面的句子**。
因为我们的成片是"在固定时长的原片上重新配音"：如果加几个字就把后面全推后，
片尾会溢出、整条时间轴都要重算。锚定保持让改动的影响范围停在它所在的那一句。

代价：新句子字数暴增时会被压进原来的空隙里。真正念出来的节奏由 TTS 实测决定，
这里的投影只用来回答两件事：**这句落在哪个镜头**、**哪些镜头要重画**。

边界
----
- 只算时间，不判断画质、不调模型、不花钱。
- 字级时间来自 ASR；没有字级时间时退回"按段均分"，并标记 `estimated`。
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

# 中英文标点：对齐前统一去掉 —— ASR 返回的字通常不带标点，带着比必然对不齐
_PUNCT = "，。！？；：、,.!?;:\"'“”‘’（）()[]【】…—-~～ \t\n\r"


def _norm(s: str) -> str:
    """只保留"要念出来的字"，用于对齐。"""
    return "".join(ch for ch in (s or "") if ch not in _PUNCT)


def source_chars(work: dict) -> list[dict]:
    """把原片的字级时间摊平成一条轴：[{c, s, e, seg}]。"""
    out: list[dict] = []
    for n, seg in enumerate((work.get("evidence") or {}).get("speech", {}).get("segments") or []):
        for ch in seg.get("chars") or []:
            c = str(ch.get("c") or "")
            if not c:
                continue
            out.append({"c": c, "s": float(ch.get("s") or 0), "e": float(ch.get("e") or 0),
                        "seg": n})
    return out


def source_text(work: dict) -> str:
    return "".join(ch["c"] for ch in source_chars(work))


def _split_script(script: str, n: int) -> list[str]:
    """按句子切新台词。

    🩸 直接复用出片链路的切分函数：预览、plan、真跑必须用同一套切法，
    否则"plan 说 3 段、真跑切 4 段"这种事会立刻发生。
    """
    from app.services.clone_pipeline import _split_script as split

    return split(script, n)


def _char_duration(work: dict, lang: str) -> float:
    """单个字大约占多久：优先用原片实测，没有就按语音估时。"""
    chars = source_chars(work)
    if len(chars) >= 4:
        span = sum(max(0.0, ch["e"] - ch["s"]) for ch in chars)
        if span > 0:
            return span / len(chars)
    try:
        from app.services import speech_est

        est = speech_est.estimate("一二三四五六七八九十", lang or "zh")
        return max(0.05, est / 10.0)
    except Exception:  # noqa: BLE001
        return 0.2


def _times(work: dict, script: str | None, lang: str = ""):
    """算新串每个字的时间。

    返回 (times, new_norm, new_text, 源语音段数, 有没有字级时间)。
    `times[i]` 对应 `new_norm[i]`，形如 {s, e, matched}。
    """
    src_segs = (work.get("evidence") or {}).get("speech", {}).get("segments") or []
    if not src_segs:
        # 没有语音：无从对齐，按原片时长均分
        return [], "", "", 0, False

    # 🩸 ASR 的 `chars` 是**词**（"So" / "what"），不是单字；还带标点。
    # 对齐前先摊成逐字，标点丢掉 —— 不摊平会出现"索引对得上、时间对不上"。
    chars: list[dict] = []
    for ch in source_chars(work):
        for c in _norm(ch["c"]):
            chars.append({"c": c, "s": ch["s"], "e": ch["e"]})
    old_norm = "".join(ch["c"] for ch in chars)
    new_text = (script or "").strip() or "".join(str(s.get("text") or "") for s in src_segs)
    new_norm = _norm(new_text)

    # 1) 新串每个字的时间：能对齐的继承，对齐不到的按前后锚点插值
    times: list[dict] = [{"s": None, "e": None, "matched": False} for _ in new_norm]
    sm = SequenceMatcher(None, old_norm, new_norm, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                times[j1 + k] = {"s": chars[i1 + k]["s"], "e": chars[i1 + k]["e"],
                                 "matched": True}

    # 2) 插值：把未对齐的字铺在相邻锚点之间
    default_d = _char_duration(work, lang)
    i = 0
    while i < len(times):
        if times[i]["s"] is not None:
            i += 1
            continue
        j = i
        while j < len(times) and times[j]["s"] is None:
            j += 1
        prev_e = None
        for k in range(i - 1, -1, -1):
            if times[k]["e"] is not None:
                prev_e = times[k]["e"]
                break
        next_s = None
        for k in range(j, len(times)):
            if times[k]["s"] is not None:
                next_s = times[k]["s"]
                break
        n = j - i
        if prev_e is not None and next_s is not None and next_s > prev_e:
            step = (next_s - prev_e) / n
            for k in range(n):
                times[i + k] = {"s": prev_e + step * k, "e": prev_e + step * (k + 1),
                                "matched": False}
        else:
            base = prev_e if prev_e is not None else (next_s if next_s is not None else 0.0)
            for k in range(n):
                times[i + k] = {"s": base + default_d * k, "e": base + default_d * (k + 1),
                                "matched": False}
        i = j

    return times, new_norm, new_text, len(src_segs), bool(chars)


def align_times(work: dict, script: str | None, *, lang: str = "") -> list[dict]:
    """逐字时间（验收和调试用）：[{c, s, e, matched}]。"""
    times, new_norm, _text, _n, _has = _times(work, script, lang)
    return [{"c": c, **t} for c, t in zip(new_norm, times)]


def project(work: dict, script: str | None, *, lang: str = "") -> dict:
    """把一份新台词投影到原片时间轴上。

    返回：
      segments: [{i, text, start, end, changed}]
      changed_segments: [i, ...]
      estimated: 没有字级时间时为 True（整段退回均分）
    """
    times, new_norm, new_text, n_src, has_chars = _times(work, script, lang)
    if not n_src:
        return {"segments": [], "changed_segments": [], "estimated": True}

    # 3) 按句切段，再把每段映射回新串里的字位置
    parts = _split_script(new_text, max(1, n_src))
    segs: list[dict] = []
    cursor = 0
    for n, text in enumerate(parts):
        key = _norm(text)
        if not key:
            continue
        pos = new_norm.find(key, cursor)
        if pos < 0:                     # 切分与原文对不上：整段当作新写的
            pos = cursor
        idx = range(pos, min(pos + len(key), len(times)))
        if not idx:
            continue
        s = min(times[k]["s"] for k in idx)
        e = max(times[k]["e"] for k in idx)
        changed = any(not times[k]["matched"] for k in idx)
        segs.append({"i": n, "text": text, "start": round(s, 3), "end": round(e, 3),
                     "changed": changed})
        cursor = pos + len(key)

    return {
        "segments": segs,
        "changed_segments": [s["i"] for s in segs if s["changed"]],
        "estimated": not has_chars,
    }


def text_for_span(work: dict, script: str | None, span, *, lang: str = "") -> str:
    """这一段（源时间区间）里，新台词说了哪些字 —— 用来判"这段要不要重画"。

    🩸 没有字级时间时**不能**按投影切区间：投影会挤在片子开头，后面的段
    一律拿到空串，看起来像"这段没台词" → 改了词照样复用 → 新台词对着旧口型。
    这种时候退回**整份新台词**当这一段的内容：同一份台词仍然复用，
    台词一动所有跟嘴型的段全部失效。宁可多花一次，不赌。
    """
    proj = project(work, script, lang=lang)
    if proj.get("estimated"):
        return _norm(script or "")
    a, b = float(span[0]), float(span[1])
    return "".join(s["text"] for s in proj["segments"]
                   if float(s["end"]) > a + 1e-3 and float(s["start"]) < b - 1e-3)


def speaking(work: dict, span) -> bool:
    """这一段里原片有没有人声（字级时间优先，没有就退回语音段）。"""
    a, b = float(span[0]), float(span[1])
    for ch in source_chars(work):
        if ch["e"] > a + 1e-3 and ch["s"] < b - 1e-3:
            return True
    for seg in (work.get("evidence") or {}).get("speech", {}).get("segments") or []:
        if float(seg.get("end", 0)) > a + 1e-3 and float(seg.get("start", 0)) < b - 1e-3:
            return True
    return False


def face_in(inventory: dict | None, span) -> bool:
    """这一段里有没有"露脸的人"。没有盘点结果时按"有"处理（保守）。"""
    if not isinstance(inventory, dict) or not inventory.get("people"):
        return True
    a, b = float(span[0]), float(span[1])
    for p in inventory.get("people") or []:
        if not p.get("face_visible"):
            continue
        for ap in p.get("appearances") or []:
            if float(ap.get("end", 0)) > a + 1e-3 and float(ap.get("start", 0)) < b - 1e-3:
                return True
    return False


def lip_dependent(work: dict, span, inventory: dict | None) -> bool:
    """这一段的画面是不是"跟着嘴型走"。

    是 → 改了词必须重画（口型对不上新台词）；
    否 → 改词只换音频，画面可以复用。
    """
    return speaking(work, span) and face_in(inventory, span)
