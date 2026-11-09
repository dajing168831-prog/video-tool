"""字幕导出（SRT / WebVTT）—— 纯函数，零依赖、零费用。

出处：clipforge `src/lib/subtitle-export.ts:1-101`，**逻辑逐字照抄**，只换字段名：
竞品叫 `voiceover`，我们的分镜叫 `dialogue`（台词）。

为什么要这份文件：我们成片里的字幕是**烧录**的，改不了；创作者需要可编辑的
.srt/.vtt 去二剪、传平台原生字幕、做校对与多语言译制。

🩸 时轴是**按分镜计划时长累加**的，不是从成片里读出来的（竞品原话 :8-10）。
所以毫秒级漂移是预期的 —— 这份是**可编辑草稿**，不是帧级对轴成品。
"""
from __future__ import annotations

#: 没有时长时给一条最小可见时长，避免 0 长度字幕（clipforge `subtitle-export.ts:21`）
MIN_CUE_MS = 500


def shots_to_cues(shots: list[dict], *, gap_ms: int = 0) -> list[dict]:
    """按分镜顺序累加时长 → 字幕条。

    没台词的分镜**不产生字幕，但时长照样推进游标**，否则后面每条都会提前
    （clipforge `subtitle-export.ts:29-33` 的原话）。
    """
    gap_ms = max(0, int(gap_ms or 0))
    cues: list[dict] = []
    cursor = 0
    index = 0
    for shot in shots or []:
        try:
            dur_ms = max(0, round(float(shot.get("duration") or 0) * 1000))
        except (TypeError, ValueError):
            dur_ms = 0
        text = str(shot.get("dialogue") or "").strip()
        if text:
            start = cursor
            # 字幕长度跟随分镜时长，短镜头**不补齐到 500ms**，免得和下一句重叠
            cue_len = dur_ms if dur_ms > 0 else MIN_CUE_MS
            end = max(start + cue_len - gap_ms, start + 1)
            index += 1
            cues.append({"index": index, "startMs": start, "endMs": end, "text": text})
        cursor += dur_ms
    return cues


def _clock(ms: float, sep: str) -> str:
    t = max(0, round(ms))
    h = t // 3_600_000
    m = (t % 3_600_000) // 60_000
    s = (t % 60_000) // 1000
    millis = t % 1000
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{millis:03d}"


def format_srt_time(ms: float) -> str:
    return _clock(ms, ",")


def format_vtt_time(ms: float) -> str:
    return _clock(ms, ".")


def build_srt(cues: list[dict]) -> str:
    body = "\n\n".join(
        f"{c['index']}\n{format_srt_time(c['startMs'])} --> "
        f"{format_srt_time(c['endMs'])}\n{c['text']}"
        for c in cues)
    return body + ("\n" if cues else "")


def build_vtt(cues: list[dict]) -> str:
    body = "\n\n".join(
        f"{c['index']}\n{format_vtt_time(c['startMs'])} --> "
        f"{format_vtt_time(c['endMs'])}\n{c['text']}"
        for c in cues)
    return f"WEBVTT\n\n{body}" + ("\n" if cues else "")


def from_shots(shots: list[dict], fmt: str = "srt", *, gap_ms: int = 0) -> str:
    """一站式：分镜 → 字幕文本。`fmt` 只认 srt / vtt。"""
    cues = shots_to_cues(shots, gap_ms=gap_ms)
    return build_vtt(cues) if (fmt or "").lower() == "vtt" else build_srt(cues)
