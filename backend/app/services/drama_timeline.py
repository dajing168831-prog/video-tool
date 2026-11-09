"""B9：时间线导出（OTIO / CMX3600 EDL / CSV）。

出处（竞品 `src/lib/timeline-export.ts` 全文 + `api/.../timeline/route.ts`）：
  · `route.ts:19` 只认三种格式 `otio / edl / csv`，其余一律按 otio（:29）
  · `route.ts:38-40` **没有转写不给导**（409）；没有可保留的区间 → 422
  · `route.ts:56-77` 两个附带轨道：**节奏标记**（每句台词起点，映射到导出的成片时间）与
    **字幕轨**（源时间 → 成片时间，跨切点被切掉的句子自然消失）
  · `timeline-export.ts:44-58` 文件名净化（保留字母数字/点/下划线/短横，截 80；空则 `clipforge-edit`）
  · `:60-62` 帧号 = `round(秒 × 帧率)`；`:257-266` 帧率夹在 1–240、默认 30
  · `:268-281` 时间码 `HH:MM:SS:FF`（base 用 `round(帧率)`，非整数帧率按取整算）
  · `:283-322` **CMX3600 EDL**：`001  AX       AA/V C        源入 源出 记录入 记录出`；
    `AA/V` 表示有声、`V` 表示无声；每段附 `* FROM CLIP NAME` / `* TRANSCRIPT:` / `* CAPTION`；
    末尾 `* CLIPFORGE RHYTHM MARKERS` + `* BEAT`
  · `:324-330` **CSV**：12 列固定表头、`﻿` BOM、CRLF 换行（Excel 直接开不乱码）
  · `:205-255` **OTIO**：`Timeline.1 / Stack.1 / Track.1 / Clip.1 / ExternalReference.1 /
    Gap.1 / Marker.1 / RationalTime.1 / TimeRange.1`；素材按文件名相对引用（relink by file-name）

我们的差异：
  1. 竞品导的是「转写草稿删词后的保留区间」（mediaEdits 计划）；我们这条线没有删词编辑器，
     **保留区间来自 B8 已经剪出来的片段**（文件名带起止毫秒），也允许调用方直接传 `ranges`。
  2. 没有字幕校对，所以字幕轨永远是转写原文；节奏标记仍是每句起点。
  3. 🩸 成片（AI 段 + 素材段混排）的时间线导出**没做** —— 那是另一条链路（`drama_film.plan`），
     这一批只对齐竞品「按导入素材导出」这个入口。
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

#: 只认这三种（`route.ts:19`）
FORMATS = ("otio", "edl", "csv")
#: 默认帧率（`timeline-export.ts:258`）
DEFAULT_FRAME_RATE = 30.0
#: 文件名兜底（`timeline-export.ts:47`）
_FALLBACK_STEM = "clipforge-edit"


# ---------------------------------------------------------------- 区间

def normalize_ranges(ranges: list, duration: float) -> list[dict]:
    """排序 + 夹取 + 合并重叠/相邻（`timeline-export.ts` 用的 `normalizeTimeRanges` 同口径）。"""
    clean: list[dict] = []
    for r in ranges or []:
        if not isinstance(r, dict):
            continue
        try:
            start = max(0.0, min(float(r.get("start") or 0), duration))
            end = max(0.0, min(float(r.get("end") or 0), duration))
        except (TypeError, ValueError):
            continue
        if end - start >= 0.01:
            clean.append({"start": start, "end": end})
    clean.sort(key=lambda x: (x["start"], x["end"]))
    out: list[dict] = []
    for r in clean:
        if out and r["start"] <= out[-1]["end"] + 0.001:
            out[-1]["end"] = max(out[-1]["end"], r["end"])
        else:
            out.append(dict(r))
    return out


def output_duration(ranges: list[dict]) -> float:
    return round(sum(max(0.0, r["end"] - r["start"]) for r in ranges), 3)


# ---------------------------------------------------------------- 帧 / 时间码

def normalize_frame_rate(value) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return DEFAULT_FRAME_RATE
    if not (1 <= v <= 240):
        return DEFAULT_FRAME_RATE
    return round(v, 6)


def frame_value(seconds: float, rate: float) -> int:
    return max(0, int(round(float(seconds) * rate)))


def frames_to_timecode(total_frames: int, frame_rate: float) -> str:
    base = max(1, int(round(normalize_frame_rate(frame_rate))))
    remaining = max(0, int(round(total_frames)))
    hours, remaining = divmod(remaining, base * 3600)
    minutes, remaining = divmod(remaining, base * 60)
    seconds, frames = divmod(remaining, base)
    return ":".join(f"{p:02d}" for p in (hours, minutes, seconds, frames))


def seconds_to_timecode(seconds: float, frame_rate: float) -> str:
    return frames_to_timecode(frame_value(seconds, normalize_frame_rate(frame_rate)), frame_rate)


# ---------------------------------------------------------------- 名字

def safe_stem(value: str, strip_extension: bool = False) -> str:
    """文件名净化（`timeline-export.ts:44-51`）"""
    base = Path(str(value or "").replace("\\", "/")).name
    if strip_extension:
        base = re.sub(r"\.[^.]+$", "", base)
    base = re.sub(r"[^\w.\-]+", "-", base, flags=re.UNICODE).strip("-")[:80]
    return base or _FALLBACK_STEM


def safe_source_name(value: str) -> str:
    return (Path(str(value or "").replace("\\", "/")).name or "source.mp4")[:240]


# ---------------------------------------------------------------- 附带轨道归一化

def normalized_beat_markers(input_: dict, duration: float) -> list[dict]:
    seen = set()
    out: list[dict] = []
    for m in (input_.get("beat_markers") or []):
        if not isinstance(m, dict):
            continue
        try:
            t = min(max(float(m.get("time") or 0), 0.0), duration)
        except (TypeError, ValueError):
            continue
        label = re.sub(r"[\r\n]+", " ", str(m.get("label") or "")).strip()[:160]
        key = (round(t, 3), label)
        if key in seen:
            continue
        seen.add(key)
        row = {"time": round(t, 3)}
        try:
            row["source_time"] = max(0.0, float(m.get("source_time")))
        except (TypeError, ValueError):
            pass
        if label:
            row["label"] = label
        out.append(row)
    out.sort(key=lambda x: x["time"])
    return out


def normalized_caption_cues(input_: dict, duration: float) -> list[dict]:
    rows: list[dict] = []
    for c in (input_.get("caption_cues") or []):
        if not isinstance(c, dict):
            continue
        try:
            t = min(max(float(c.get("time") or 0), 0.0), duration)
            e = min(max(float(c.get("end_time") or 0), 0.0), duration)
        except (TypeError, ValueError):
            continue
        text = re.sub(r"[\r\n]+", " ", str(c.get("text") or "")).strip()[:2000]
        if e - t < 0.01 or not text:
            continue
        rows.append({"time": round(t, 3), "end_time": round(e, 3), "text": text})
    rows.sort(key=lambda x: (x["time"], x["end_time"]))
    # 后一条不能压到前一条（`timeline-export.ts:133`）
    out: list[dict] = []
    for c in rows:
        if out and c["time"] < out[-1]["end_time"] - 0.01:
            continue
        out.append(c)
    return out


# ---------------------------------------------------------------- OTIO

def _rational_time(seconds: float, rate: float) -> dict:
    return {"OTIO_SCHEMA": "RationalTime.1", "rate": rate,
            "value": frame_value(seconds, rate)}


def _time_range(start: float, duration: float, rate: float) -> dict:
    return {"OTIO_SCHEMA": "TimeRange.1", "duration": _rational_time(duration, rate),
            "start_time": _rational_time(start, rate)}


def _external_reference(name: str, source_duration: float, rate: float) -> dict:
    return {"OTIO_SCHEMA": "ExternalReference.1",
            "available_range": _time_range(0, source_duration, rate),
            "metadata": {"clipforge": {"pathMode": "relative", "relinkBy": "file-name"}},
            "target_url": name, "name": name}


def _otio_clip(r: dict, index: int, input_: dict, rate: float) -> dict:
    src = safe_source_name(input_.get("source_name") or "")
    notes = input_.get("clip_notes") or []
    return {
        "OTIO_SCHEMA": "Clip.1", "effects": [], "markers": [], "enabled": True,
        "media_reference": _external_reference(src, float(input_.get("source_duration") or 0), rate),
        "metadata": {"clipforge": {
            "sourceStartSeconds": r["start"], "sourceEndSeconds": r["end"],
            "revision": input_.get("revision"),
            "transcript": notes[index] if index < len(notes) else "",
        }},
        "name": f"Cut {index + 1:03d}",
        "source_range": _time_range(r["start"], r["end"] - r["start"], rate),
    }


def _otio_track(kind: str, ranges: list[dict], input_: dict, rate: float) -> dict:
    return {
        "OTIO_SCHEMA": "Track.1",
        "children": [_otio_clip(r, i, input_, rate) for i, r in enumerate(ranges)],
        "effects": [], "kind": kind, "markers": [], "enabled": True, "metadata": {},
        "name": "V1 · Source cuts" if kind == "Video" else "A1 · Source audio",
        "source_range": None,
    }


def _otio_caption_track(cues: list[dict], rate: float) -> dict:
    children: list[dict] = []
    cursor = 0.0
    for i, cue in enumerate(cues):
        if cue["time"] > cursor + 0.001:
            children.append({"OTIO_SCHEMA": "Gap.1",
                             "source_range": _time_range(0, cue["time"] - cursor, rate),
                             "name": "Caption gap"})
        children.append({
            "OTIO_SCHEMA": "Clip.1", "enabled": True, "effects": [], "markers": [],
            "media_reference": {"OTIO_SCHEMA": "GeneratorReference.1", "generator_kind": "Text",
                                "parameters": {"text": cue["text"]}},
            "metadata": {"clipforge": {"role": "caption", "sourceTime": cue["time"],
                                       "sourceEndTime": cue["end_time"]}},
            "name": f"Caption {i + 1:03d}",
            "source_range": _time_range(0, cue["end_time"] - cue["time"], rate),
        })
        cursor = cue["end_time"]
    return {"OTIO_SCHEMA": "Track.1", "children": children, "effects": [], "kind": "Video",
            "markers": [], "enabled": True,
            "metadata": {"clipforge": {"role": "captions", "editable": True}},
            "name": "C1 · Captions", "source_range": None}


def _otio_marker(m: dict, rate: float) -> dict:
    meta = {"kind": "beat"}
    if "source_time" in m:
        meta["sourceTimeSeconds"] = m["source_time"]
    return {"OTIO_SCHEMA": "Marker.1", "color": "YELLOW", "name": m.get("label") or "Beat",
            "marked_range": _time_range(m["time"], 0, rate), "metadata": {"clipforge": meta}}


def build_otio(input_: dict) -> str:
    rate = normalize_frame_rate(input_.get("frame_rate"))
    ranges = normalize_ranges(input_.get("keep_ranges") or [], float(input_.get("source_duration") or 0))
    if not ranges:  # 没有区间就没有成片时间轴，附带轨道一律清空（否则时间全被夹到 0）
        input_ = {**input_, "beat_markers": [], "caption_cues": []}
    duration = output_duration(ranges)
    beats = normalized_beat_markers(input_, duration)
    cues = normalized_caption_cues(input_, duration)
    tracks = [_otio_track("Video", ranges, input_, rate)]
    if input_.get("has_audio"):
        tracks.append(_otio_track("Audio", ranges, input_, rate))
    if cues:
        tracks.append(_otio_caption_track(cues, rate))
    doc = {
        "OTIO_SCHEMA": "Timeline.1",
        "metadata": {"clipforge": {
            "exportedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "pathMode": "relative",
            "sourceName": safe_source_name(input_.get("source_name") or ""),
            "revision": input_.get("revision"),
            "beatMarkers": beats,
            "captionCues": cues,
        }},
        "name": input_.get("project_name") or "ClipForge edit",
        "markers": [_otio_marker(m, rate) for m in beats],
        "tracks": {"OTIO_SCHEMA": "Stack.1", "children": tracks, "effects": [], "markers": [],
                   "enabled": True, "metadata": {}, "name": "tracks", "source_range": None},
    }
    return json.dumps(doc, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- EDL / CSV

def build_edl(input_: dict) -> str:
    rate = normalize_frame_rate(input_.get("frame_rate"))
    ranges = normalize_ranges(input_.get("keep_ranges") or [], float(input_.get("source_duration") or 0))
    if not ranges:
        input_ = {**input_, "beat_markers": [], "caption_cues": []}
    cues = normalized_caption_cues(input_, output_duration(ranges))
    notes = input_.get("clip_notes") or []
    source = safe_source_name(input_.get("source_name") or "")
    cursor = 0.0
    lines = [f"TITLE: {input_.get('project_name') or 'CLIPFORGE EDIT'}", "FCM: NON-DROP FRAME", ""]
    for i, r in enumerate(ranges):
        length = r["end"] - r["start"]
        channel = "AA/V" if input_.get("has_audio") else "V"
        lines.append(
            f"{i + 1:03d}  AX       {channel.ljust(4)} C        "
            f"{seconds_to_timecode(r['start'], rate)} {seconds_to_timecode(r['end'], rate)} "
            f"{seconds_to_timecode(cursor, rate)} {seconds_to_timecode(cursor + length, rate)}")
        lines.append(f"* FROM CLIP NAME: {source}")
        if i < len(notes) and notes[i]:
            lines.append(f"* TRANSCRIPT: {re.sub(r'[\r\n]+', ' ', str(notes[i]))}")
        for cue in cues:
            if cursor - 0.001 <= cue["time"] <= cursor + length + 0.001:
                lines.append(f"* CAPTION {seconds_to_timecode(cue['time'], rate)}-"
                             f"{seconds_to_timecode(cue['end_time'], rate)} · {cue['text']}")
        lines.append(f"* CLIPFORGE SOURCE: {r['start']:.3f} - {r['end']:.3f} seconds")
        lines.append("")
        cursor += length
    beats = normalized_beat_markers(input_, cursor)
    if beats:
        lines.append("* CLIPFORGE RHYTHM MARKERS")
        for m in beats:
            tail = f" · {m['label']}" if m.get("label") else ""
            lines.append(f"* BEAT {seconds_to_timecode(m['time'], rate)}{tail}")
    return "\n".join(lines)


def _csv_cell(value) -> str:
    text = str(value)
    return f'"{text.replace(chr(34), chr(34) * 2)}"' if re.search(r'[",\r\n]', text) else text


def build_csv(input_: dict) -> str:
    rate = normalize_frame_rate(input_.get("frame_rate"))
    ranges = normalize_ranges(input_.get("keep_ranges") or [], float(input_.get("source_duration") or 0))
    if not ranges:
        input_ = {**input_, "beat_markers": [], "caption_cues": []}
    total = output_duration(ranges)
    beats = normalized_beat_markers(input_, total)
    cues = normalized_caption_cues(input_, total)
    notes = input_.get("clip_notes") or []
    source = safe_source_name(input_.get("source_name") or "")
    rows: list[list] = [["Event", "Source", "Source In", "Source Out", "Record In", "Record Out",
                         "Duration Seconds", "Source In Seconds", "Source Out Seconds", "Transcript",
                         "Rhythm Markers", "Caption Cues"]]
    cursor = 0.0
    for i, r in enumerate(ranges):
        length = r["end"] - r["start"]
        rows.append([
            i + 1, source,
            seconds_to_timecode(r["start"], rate), seconds_to_timecode(r["end"], rate),
            seconds_to_timecode(cursor, rate), seconds_to_timecode(cursor + length, rate),
            f"{length:.3f}", f"{r['start']:.3f}", f"{r['end']:.3f}",
            notes[i] if i < len(notes) else "",
            "; ".join(f"{seconds_to_timecode(m['time'], rate)}"
                      + (f" {m['label']}" if m.get("label") else "")
                      for m in beats if cursor - 0.001 <= m["time"] <= cursor + length + 0.001),
            "; ".join(f"{seconds_to_timecode(c['time'], rate)}-"
                      f"{seconds_to_timecode(c['end_time'], rate)} {c['text']}"
                      for c in cues if cursor - 0.001 <= c["time"] <= cursor + length + 0.001),
        ])
        cursor += length
    body = "\r\n".join(",".join(_csv_cell(c) for c in row) for row in rows)
    return "﻿" + body


# ---------------------------------------------------------------- 探测 / 转写映射

def probe_frame_rate(path, ffprobe: str | None) -> float:
    """读视频帧率（`route.ts` 的 `probeMedia().frameRate`）；读不到按 30。"""
    if not ffprobe:
        return DEFAULT_FRAME_RATE
    try:
        p = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=r_frame_rate,avg_frame_rate",
             "-of", "json", str(path)],
            capture_output=True, text=True, errors="ignore", timeout=30,
        )
        streams = (json.loads(p.stdout or "{}").get("streams") or [])
        raw = str((streams[0] if streams else {}).get("r_frame_rate") or "") or \
            str((streams[0] if streams else {}).get("avg_frame_rate") or "")
        if "/" in raw:
            num, den = raw.split("/", 1)
            rate = float(num) / float(den) if float(den) else 0.0
        else:
            rate = float(raw or 0)
    except Exception:  # noqa: BLE001
        return DEFAULT_FRAME_RATE
    return normalize_frame_rate(rate)


def _join_words(words: list[str]) -> str:
    """中文之间不加空格（竞品 `route.ts` 的 `joinClipText` 同口径）。"""
    out = ""
    for w in words:
        if out and re.match(r"[A-Za-z0-9]", w[:1] or "") and re.match(r"[A-Za-z0-9]", out[-1:] or ""):
            out += " "
        out += w
    return out


def map_transcript(doc: dict, ranges: list[dict]) -> dict:
    """把转写结果映射到成片时间轴，产出 `clip_notes / caption_cues / beat_markers`。

    照 `route.ts:56-77`：源时间 → 成片时间；跨切点被切掉的句子自然消失。
    """
    segments = [s for s in ((doc or {}).get("segments") or []) if isinstance(s, dict)]
    notes: list[str] = []
    cues: list[dict] = []
    beats: list[dict] = []
    cursor = 0.0
    for r in ranges:
        length = r["end"] - r["start"]
        words: list[str] = []
        for seg in segments:
            try:
                ss, se = float(seg.get("start") or 0), float(seg.get("end") or 0)
            except (TypeError, ValueError):
                continue
            text = str(seg.get("text") or "").strip()
            if not text:
                continue
            # 整段落在区间内才算；跨切点的段按重合的字符算（字级优先）
            if se <= r["start"] + 0.001 or ss >= r["end"] - 0.001:
                continue
            chars = seg.get("chars") or []
            if chars:
                kept = [str(c.get("c") or "") for c in chars
                        if isinstance(c, dict)
                        and float(c.get("e") or 0) > r["start"] + 0.001
                        and float(c.get("s") or 0) < r["end"] - 0.001]
                piece = _join_words([c for c in kept if c])
            else:
                piece = text
            if piece:
                words.append(piece)
            # 句子起点落在区间内 → 字幕 + 节奏标记（源时间 → 成片时间）
            if r["start"] - 0.001 <= ss < r["end"] - 0.001 and piece:
                t = cursor + (ss - r["start"])
                e = cursor + (min(se, r["end"]) - r["start"])
                if e - t >= 0.01:
                    cues.append({"time": round(t, 3), "end_time": round(e, 3), "text": piece})
                    beats.append({"time": round(t, 3), "source_time": round(ss, 3),
                                  "label": piece[:16]})
        notes.append(_join_words(words))
        cursor += length
    return {"clip_notes": notes,
            "caption_cues": normalized_caption_cues({"caption_cues": cues}, cursor),
            "beat_markers": normalized_beat_markers({"beat_markers": beats}, cursor)}


# ---------------------------------------------------------------- 总入口

def export_timeline(fmt: str, input_: dict) -> dict:
    """返回 `{content, file_name, mime_type, clips, duration, frame_rate}`（`route.ts:80-96`）"""
    fmt = fmt if fmt in FORMATS else "otio"
    ranges = normalize_ranges(input_.get("keep_ranges") or [], float(input_.get("source_duration") or 0))
    project = str(input_.get("project_name") or "").strip()
    revision = input_.get("revision")
    stem = (safe_stem(project) if project else
            safe_stem(input_.get("source_name") or "", strip_extension=True)) + \
        (f"-r{int(revision)}" if revision else "-draft")
    common = {"clips": len(ranges), "duration": output_duration(ranges),
              "frame_rate": normalize_frame_rate(input_.get("frame_rate"))}
    if fmt == "edl":
        return {**common, "content": build_edl(input_), "file_name": f"{stem}.edl",
                "mime_type": "text/plain; charset=utf-8"}
    if fmt == "csv":
        return {**common, "content": build_csv(input_), "file_name": f"{stem}.csv",
                "mime_type": "text/csv; charset=utf-8"}
    return {**common, "content": build_otio(input_), "file_name": f"{stem}.otio",
            "mime_type": "application/vnd.otio+json; charset=utf-8"}
