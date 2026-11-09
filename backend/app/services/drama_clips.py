"""B8：按文字剪（关键词 ≤160 字 → 5–120 秒片段）。

出处（竞品 `src/lib/transcript-clips.ts` 全文 + `api/.../clips/route.ts:17-27`）：
  · `route.ts:17-27` 参数闸：关键词 ≤160 字、时长 5–120 秒、数量 1–12；**没转写完不给**（409）
  · `transcript-clips.ts:22-26` 归一化：NFKC + 小写 + **去掉所有空白**（中文没有词边界，只能整串比）
  · `:28-31` 拼文本：含中日韩字符就**不加空格**，英文按空格并去掉标点前的空格
  · `:33` 句末判定 `[.!?。！？；;…]["'”’）)]?$`
  · `:36-56` 把词切成 unit：句末 / 停顿 ≥0.8 秒 / 连续 ≥min(8, 目标秒数) / 超过 80 个词 → 强制断
  · `:58-84` 每个起点向后找「最接近目标时长」的短语边界；**跨 >3 秒静默不接**；长度到 1.35 倍目标就停
  · `:80-88` 前后各留 0.12 / 0.18 秒呼吸，但**夹在相邻词的边界内**（不会把下一句带进来）
  · `:96-99` 排序分 = 说话占比 − |实际−目标|/目标 + 句末 0.2 + 停顿 0.1
  · `:100-112` 去重叠：与已选片段重叠超过较短者 50% 就丢；最后按起点排序
  · `:86-89` 太短的不要（< min(3, 目标×0.4) 秒）

我们的差异：
  1. **数据源是段级 segments + 字级 chars**（火山返回），不是竞品那种扁平 `words`。
     这里先展平成词序列；没有字级时就退回「每段当一个词」（精度低但能用，并在结果里标出来）。
  2. 竞品这个接口**只给建议**，真正裁剪在 `transcript-render.ts`（多区间 trim+concat 重编码）。
     我们这条产品线没有时间线编辑器，所以**把「剪出来」做成一步**：单个区间 ffmpeg 重编码导出成 mp4，
     可以直接下载，或者接着「加进素材库」当某一镜的画面（接 B4 的素材当画面）。
"""
from __future__ import annotations

import re
import subprocess
import unicodedata
from pathlib import Path

from app.services import media

#: 关键词上限（`clips/route.ts:24`）
MAX_QUERY_CHARS = 160
#: 目标时长范围（`clips/route.ts:24`）
MIN_TARGET_SECONDS = 5
MAX_TARGET_SECONDS = 120
#: 候选数量范围（`clips/route.ts:24`）
MAX_LIMIT = 12
#: 路由层复用同一口径
MAX_CLIP_LIMIT = MAX_LIMIT
#: 句末标点（`transcript-clips.ts:33`）
_SENTENCE_END = re.compile(r"[.!?。！？；;…][\"'”’）)]?$")
_CJK = re.compile(r"[㐀-鿿぀-ヿ가-힯]")


class ClipError(RuntimeError):
    """能直接展示给用户的原因。"""


# ---------------------------------------------------------------- 文本

def searchable(text: str) -> str:
    """NFKC + 小写 + 去空白（`transcript-clips.ts:22-24`）"""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(text or "")).lower())


def joined_text(words: list[dict]) -> str:
    """含中日韩字符就不加空格（`transcript-clips.ts:28-31`）"""
    cjk = any(_CJK.search(str(w.get("text") or "")) for w in words)
    sep = "" if cjk else " "
    text = sep.join(str(w.get("text") or "") for w in words)
    return re.sub(r"\s+([,.!?;:])", r"\1", text)


def words_of(document: dict) -> tuple[list[dict], bool]:
    """转写文档 → 词序列。返回 (词表, 是否字级)。

    火山给的是 `segments[].chars[]`（每个字带起止）；没有字级时间就整段当一个词。
    """
    out: list[dict] = []
    for seg in (document.get("segments") or []):
        if not isinstance(seg, dict):
            continue
        chars = [c for c in (seg.get("chars") or []) if isinstance(c, dict) and str(c.get("c") or "").strip()]
        if chars:
            for c in chars:
                out.append({"text": str(c["c"]), "start": float(c.get("s") or 0),
                            "end": float(c.get("e") or 0)})
        else:
            text = str(seg.get("text") or "").strip()
            if text:
                out.append({"text": text, "start": float(seg.get("start") or 0),
                            "end": float(seg.get("end") or 0)})
    duration = float(document.get("duration") or 0)
    words = [w for w in out if w["start"] >= 0 and w["end"] > w["start"]
             and (not duration or w["end"] <= duration + 1e-6)]
    words.sort(key=lambda w: (w["start"], w["end"]))
    return words, bool(any((s.get("chars") for s in (document.get("segments") or [])
                            if isinstance(s, dict))))


# ---------------------------------------------------------------- 建议

def suggest(document: dict, *, query: str = "", target_seconds: float = 30,
            limit: int = 6) -> dict:
    """按关键词找片段（`transcript-clips.ts:36-115` 逐段照抄，注释里的行号对得上）。"""
    target = max(MIN_TARGET_SECONDS, min(MAX_TARGET_SECONDS, float(target_seconds or 30)))
    limit = max(1, min(MAX_LIMIT, int(limit or 6)))
    query = str(query or "").strip()[:MAX_QUERY_CHARS]
    needle = searchable(query)
    words, word_level = words_of(document)
    duration = float(document.get("duration") or 0) or (words[-1]["end"] if words else 0)
    if not words:
        raise ClipError("这份转写里没有可用的时间轴，先重新转写一次")

    # 切成 unit
    units: list[dict] = []
    first = 0
    span_cap = min(8.0, target)
    for i, w in enumerate(words):
        nxt = words[i + 1] if i + 1 < len(words) else None
        sentence = bool(_SENTENCE_END.search(w["text"]))
        pause = (nxt is None) or (nxt["start"] - w["end"] >= 0.8)
        if sentence or pause or (w["end"] - words[first]["start"] >= span_cap) or (i - first >= 80):
            units.append({"first": first, "last": i, "sentence": sentence, "pause": pause})
            first = i + 1
    if first < len(words):
        units.append({"first": first, "last": len(words) - 1, "sentence": False, "pause": True})

    ranked: list[dict] = []
    for i in range(len(units)):
        start_word = words[units[i]["first"]]
        best_end, best_distance = i, float("inf")
        for j in range(i, len(units)):
            if j > i and words[units[j]["first"]]["start"] - words[units[j - 1]["last"]]["end"] > 3:
                break
            length = words[units[j]["last"]]["end"] - start_word["start"]
            distance = abs(length - target)
            if distance < best_distance:
                best_distance, best_end = distance, j
            if length >= target * 1.35 or (j - i) >= 240:
                break
        final_unit = units[best_end]
        last_word = words[final_unit["last"]]
        clip_words = words[units[i]["first"]: final_unit["last"] + 1]
        text = joined_text(clip_words)
        if needle and needle not in searchable(text):
            continue
        if last_word["end"] - start_word["start"] < min(3.0, target * 0.4):
            continue

        prev = words[units[i]["first"] - 1] if units[i]["first"] > 0 else None
        nxt = words[final_unit["last"] + 1] if final_unit["last"] + 1 < len(words) else None
        start = max(0.0, start_word["start"] - 0.12, float(prev["end"]) if prev else 0.0)
        end = min(duration, last_word["end"] + 0.18,
                  float(nxt["start"]) if nxt else duration)
        if end - start < 0.5:
            continue

        speech, cursor = 0.0, start
        for w in clip_words:
            speech += max(0.0, min(end, w["end"]) - max(cursor, w["start"]))
            cursor = max(cursor, w["end"])
        clip_duration = end - start
        ratio = min(1.0, speech / clip_duration) if clip_duration else 0.0

        reasons = []
        if needle:
            reasons.append("query")
        if final_unit["sentence"]:
            reasons.append("sentence")
        if final_unit["pause"]:
            reasons.append("pause")
        rank = (ratio - abs(clip_duration - target) / target
                + (0.2 if final_unit["sentence"] else 0)
                + (0.1 if final_unit["pause"] else 0))
        ranked.append({
            "rank": rank,
            "clip": {
                "id": f"clip-{units[i]['first']}-{final_unit['last']}",
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": round(clip_duration, 3),
                "text": text,
                "word_count": len(clip_words),
                "speech_ratio": round(ratio, 3),
                "reasons": reasons,
            },
        })

    ranked.sort(key=lambda r: (-r["rank"], r["clip"]["start"]))
    picked: list[dict] = []
    for item in ranked:
        clip = item["clip"]
        if any(min(clip["end"], o["end"]) - max(clip["start"], o["start"]) > 0
               and (min(clip["end"], o["end"]) - max(clip["start"], o["start"]))
               / max(1e-6, min(clip["duration"], o["duration"])) > 0.5 for o in picked):
            continue
        picked.append(clip)
        if len(picked) >= limit:
            break
    picked.sort(key=lambda c: c["start"])
    return {"method": "local-transcript", "query": query, "target_seconds": target,
            "word_level": word_level, "candidates": picked}


# ---------------------------------------------------------------- 真裁出来

def cut(src: Path, out: Path, start: float, end: float) -> dict:
    """把 [start, end] 重编码导出成 mp4（单区间；竞品多区间版本见 `transcript-render.ts:50-87`）。

    重编码而不是 `-c copy`：关键帧不一定落在切点上，copy 会多出前面一段。
    """
    exe = media.ffmpeg_path()
    if not exe:
        raise ClipError("找不到 ffmpeg")
    start = max(0.0, float(start))
    span = max(0.1, float(end) - start)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [exe, "-hide_banner", "-loglevel", "error", "-y",
           "-ss", f"{start:.3f}", "-i", str(src), "-t", f"{span:.3f}",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, errors="ignore", timeout=900)
    except subprocess.TimeoutExpired as e:
        raise ClipError("裁剪超时（片段太长或磁盘太慢）") from e
    if proc.returncode != 0 or not out.exists() or out.stat().st_size == 0:
        raise ClipError(f"裁剪失败：{(proc.stderr or '')[-200:]}")
    info = media.probe_duration(out) or 0.0
    if info <= 0:
        out.unlink(missing_ok=True)
        raise ClipError("裁出来的文件读不出时长，已删掉")
    return {"file": out.name, "duration": round(float(info), 3),
            "size_bytes": out.stat().st_size}
