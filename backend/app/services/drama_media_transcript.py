"""B7：长视频转写（分块追加 + 检查点，中断可续）。

出处（竞品 `src/lib/transcript-checkpoint.ts` + `api/project/[id]/media/[mediaId]/transcript/route.ts`）：
  · `transcript-checkpoint.ts:11-12` **每块 5 分钟**（`ASR_CHUNK_SECONDS = 300`）、采样率 16k
  · `:31-46` checkpoint 摘要：`processedSeconds / duration / resumable / model / language`
  · `:61-104` 检查点清洗：**model / language 必须匹配**，否则整份作废（换了模型或语言，
              旧时间轴不能接着用）；字按 `processedSeconds + 0.25` 截断（半秒容差）
  · `:106-146` 追加分块的三条硬规则：
      ① 进度必须**推进**（`processedSeconds > previousEnd + 0.01`，否则「没前进」直接拒）
      ② 新块的字必须**落在窗口里**（`end > previousEnd - 0.05` 且 `start < processedSeconds + 0.25`），
         全落外面就是「块和进度对不上」
      ③ 拼完按 start 排序，同 start 同文本去重，再重新编号
  · `:148-162` 从检查点还原完整文档（字幕段落由字拼回）
  · `route.ts:38-58` start：带 `resume=false` 就丢掉旧检查点；进度 = processed/duration
  · `route.ts:110-124` cancel：有完整结果 → 回 ready，没有 → 回 uploaded
  · `route.ts:56-59`（`media/route.ts`）**中断判定**：`transcribing` 超过 3 分钟没心跳 = 已中断

我们的差异（写清楚，别当成抄错）：
  1. **ASR 在服务端跑**（火山 flash），不是浏览器本地模型 —— 所以没有 heartbeat / 前端推块，
     改成一个后台任务：逐块切音频 → 识别 → 立刻落检查点（每块 5 分钟一存，中断最多丢一块）。
  2. **切块用 ffmpeg 从原视频直接切**（`-ss/-t` + 16k 单声道），不整段解码到内存。
  3. 块内时间戳**加上块起点偏移**后再进检查点，并按块末端裁一下（不越界到下一块）。
"""
from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import time
from pathlib import Path

from app.services import media, transcript

log = logging.getLogger(__name__)

#: 每块 5 分钟（`transcript-checkpoint.ts:11`）
CHUNK_SECONDS = 300
#: 块长夹取范围（`transcript-checkpoint.ts:92`：30 ~ 300）
MIN_CHUNK_SECONDS = 30
#: 半秒容差（`transcript-checkpoint.ts:65/96` 的 `+ 0.25` / `- 0.05`）
_EPS_START = 0.25
_EPS_OVERLAP = 0.05
#: 火山并发上限（和 `transcript.py` 的 `_SEM` 同口径）
_SEM = asyncio.Semaphore(2)
#: 判「转写任务已中断」的静默窗口（`media/route.ts:56`：3 分钟）
STALE_SECONDS = 3 * 60


class TranscriptError(RuntimeError):
    """能直接展示给用户的原因。"""


# ---------------------------------------------------------------- 检查点

def checkpoint_path(folder: Path, mid: str) -> Path:
    return folder / "checkpoints" / f"{mid}.json"


def result_path(folder: Path, mid: str) -> Path:
    return folder / "transcripts" / f"{mid}.json"


def _read_json(p: Path) -> dict | None:
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text("utf-8") or "{}")
    except (OSError, ValueError):
        return None


def _write_json(p: Path, data: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    tmp.replace(p)


def load_checkpoint(folder: Path, mid: str) -> dict | None:
    """读检查点原文（清洗交给 `sanitize_checkpoint`）。"""
    return _read_json(checkpoint_path(folder, mid))


def load_result(folder: Path, mid: str) -> dict | None:
    """读已完成的转写全文。"""
    return _read_json(result_path(folder, mid))


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _num(v, default: float = 0.0) -> float:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return default
    return n if n == n and n not in (float("inf"), float("-inf")) else default


def _clean_segments(segs: list[dict], duration: float) -> list[dict]:
    """只留结构对、时间在片内的段；按 start 排序。"""
    out: list[dict] = []
    for s in segs or []:
        if not isinstance(s, dict):
            continue
        text = str(s.get("text") or "").strip()
        if not text:
            continue
        st = _clamp(_num(s.get("start")), 0.0, duration)
        en = _clamp(_num(s.get("end"), st), st, duration)
        row = {"start": round(st, 3), "end": round(en, 3), "text": text}
        chars = []
        for c in (s.get("chars") or []):
            if not isinstance(c, dict):
                continue
            ch = str(c.get("c") or "")
            if not ch:
                continue
            cs = _clamp(_num(c.get("s"), st), st, en)
            ce = _clamp(_num(c.get("e"), cs), cs, en)
            chars.append({"c": ch, "s": round(cs, 3), "e": round(ce, 3)})
        if chars:
            row["chars"] = chars
        spk = str(s.get("speaker") or "").strip()
        if spk:
            row["speaker"] = spk
        out.append(row)
    return sorted(out, key=lambda r: (r["start"], r["end"]))


def sanitize_checkpoint(raw: dict | None, duration: float, *, model: str,
                        language: str) -> dict | None:
    """检查点清洗（`transcript-checkpoint.ts:61-104`）。

    **model / language 对不上就整份作废** —— 换了模型或语言，旧时间轴不能接着用。
    """
    if not isinstance(raw, dict) or duration <= 0:
        return None
    if str(raw.get("model") or "") != model:
        return None
    if str(raw.get("language") or "") != language:
        return None
    processed = _clamp(_num(raw.get("processed_seconds")), 0.0, duration)
    if processed <= 0:
        return None
    segs = [s for s in (raw.get("segments") or []) if isinstance(s, dict)
            and _num(s.get("start")) < processed + _EPS_START]
    segs = _clean_segments(segs, duration)
    return {
        "version": 1,
        "model": model,
        "language": language,
        "duration": round(duration, 3),
        "processed_seconds": round(processed, 3),
        "chunk_seconds": int(_clamp(int(_num(raw.get("chunk_seconds"), CHUNK_SECONDS)),
                                    MIN_CHUNK_SECONDS, CHUNK_SECONDS)),
        "segments": segs,
        "text_parts": [str(t).strip() for t in (raw.get("text_parts") or [])
                       if str(t or "").strip()][:2000],
        "created_at": str(raw.get("created_at") or time.strftime("%Y-%m-%d %H:%M:%S")),
    }


def append_chunk(checkpoint: dict | None, chunk_segments: list[dict], *,
                 processed_seconds: float, duration: float, model: str,
                 language: str, chunk_seconds: int = CHUNK_SECONDS) -> dict:
    """追加一块（`transcript-checkpoint.ts:106-146` 的三条硬规则）。"""
    processed = _clamp(_num(processed_seconds), 0.0, duration)
    previous_end = _num((checkpoint or {}).get("processed_seconds"))
    if processed <= previous_end + 0.01:
        raise TranscriptError("转写分块没有前进（进度必须递增）")

    clean = _clean_segments(chunk_segments, duration)
    fresh = [s for s in clean
             if s["end"] > previous_end - _EPS_OVERLAP and s["start"] < processed + _EPS_START]
    if clean and not fresh:
        raise TranscriptError("转写分块与当前进度对不上（整块落在窗口外）")

    prev = [s for s in ((checkpoint or {}).get("segments") or []) if isinstance(s, dict)]
    merged = _clean_segments(prev + fresh, duration)
    # 同文本且起点挨着，只留一条。
    # 🩸 竞品用的是**字级** start，容差 0.001 秒就够（`transcript-checkpoint.ts:134-136`）；
    # 我们是**句级**段，同一个重叠区在两块里识别出来的起点能差几百毫秒 —— 容差按
    # 「块重叠 + 半秒」放宽到 0.5 秒。判重仍要求**文本完全相同**，所以真正的重复台词
    # （同一句话隔很远说两遍）不会被误删。
    dedup: list[dict] = []
    for s in merged:
        if (dedup and s["text"] == dedup[-1]["text"]
                and abs(s["start"] - dedup[-1]["start"]) <= 0.5):
            continue
        dedup.append(s)

    text_parts = list((checkpoint or {}).get("text_parts") or [])
    text_parts.append(transcript.build_text(fresh))
    return {
        "version": 1,
        "model": model,
        "language": language,
        "duration": round(duration, 3),
        "processed_seconds": round(processed, 3),
        "chunk_seconds": int(_clamp(int(chunk_seconds), MIN_CHUNK_SECONDS, CHUNK_SECONDS)),
        "segments": dedup,
        "text_parts": [t for t in text_parts if str(t or "").strip()][:2000],
        "created_at": str((checkpoint or {}).get("created_at")
                          or time.strftime("%Y-%m-%d %H:%M:%S")),
    }


def summarize(checkpoint: dict | None) -> dict | None:
    """`transcript-checkpoint.ts:31-46`"""
    if not checkpoint:
        return None
    processed = _num(checkpoint.get("processed_seconds"))
    duration = _num(checkpoint.get("duration"))
    return {
        "processed_seconds": round(processed, 3),
        "duration": round(duration, 3),
        "resumable": 0 < processed < duration,
        "model": checkpoint.get("model") or "",
        "language": checkpoint.get("language") or "",
    }


def document_from_checkpoint(checkpoint: dict) -> dict:
    """检查点 → 完整文档（`transcript-checkpoint.ts:148-162`）"""
    segs = _clean_segments(checkpoint.get("segments") or [], _num(checkpoint.get("duration")))
    text = transcript.build_text(segs) or " ".join(checkpoint.get("text_parts") or []).strip()
    return {
        "text": text,
        "segments": segs,
        "chars": len([c for c in text if not c.isspace()]),
        "lang": checkpoint.get("language") or "zh",
        "duration": round(_num(checkpoint.get("duration")), 2),
        "model": checkpoint.get("model") or "",
        "made_at": time.time(),
    }


# ---------------------------------------------------------------- 音频切块

def extract_chunk(src: Path, start: float, duration: float, out: Path) -> bool:
    """从原视频切一块 16k 单声道 wav（`-vn` 丢画面）。返回是否成功。"""
    exe = media.ffmpeg_path()
    if not exe:
        raise TranscriptError("找不到 ffmpeg")
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [exe, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{max(0.0, start):.3f}"]
    if duration > 0:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-i", str(src), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(out)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, errors="ignore", timeout=900)
    except subprocess.TimeoutExpired as e:
        raise TranscriptError("切音频超时（文件太大或磁盘太慢）") from e
    if proc.returncode != 0 or not out.exists() or out.stat().st_size == 0:
        raise TranscriptError(f"切音频失败：{(proc.stderr or '')[-200:]}")
    return True


def shift_segments(segs: list[dict], offset: float, end_limit: float) -> list[dict]:
    """块内时间 + 偏移，并裁到块末端（不让它越界到下一块）。"""
    out: list[dict] = []
    for s in segs or []:
        if not isinstance(s, dict):
            continue
        st = _num(s.get("start")) + offset
        if st >= end_limit:
            continue
        en = min(_num(s.get("end"), _num(s.get("start"))) + offset, end_limit)
        row = dict(s, start=round(st, 3), end=round(max(st, en), 3))
        chars = []
        for c in (s.get("chars") or []):
            if not isinstance(c, dict):
                continue
            cs = _num(c.get("s"), _num(s.get("start"))) + offset
            if cs >= end_limit:
                continue
            chars.append(dict(c, s=round(cs, 3),
                              e=round(min(_num(c.get("e"), cs - offset) + offset, end_limit), 3)))
        if chars:
            row["chars"] = chars
        out.append(row)
    return out


# ---------------------------------------------------------------- 主流程

def _asr_for(language: str):
    from app.services.providers.asr import get_asr

    return get_asr()


async def run_transcription(src: Path, folder: Path, mid: str, *, duration: float,
                            language: str = "zh", model: str = "volc",
                            resume: bool = True, chunk_seconds: int = CHUNK_SECONDS,
                            on_step=None) -> dict:
    """逐块转写到完；每块落一次检查点。返回最终文档。

    `on_step(processed, total)` 给接口层更新进度用（也用于防「看起来卡死」）。
    """
    chunk_seconds = int(_clamp(int(chunk_seconds), MIN_CHUNK_SECONDS, CHUNK_SECONDS))
    ckpt_file = checkpoint_path(folder, mid)
    ckpt = sanitize_checkpoint(_read_json(ckpt_file), duration,
                               model=model, language=language) if resume else None
    if not resume:
        ckpt_file.unlink(missing_ok=True)

    tmp_dir = folder / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    asr = _asr_for(language)
    try:
        while True:
            processed = _num((ckpt or {}).get("processed_seconds"))
            if processed >= duration - 0.05:
                break
            span = min(chunk_seconds, duration - processed)
            chunk_file = tmp_dir / f"{mid}-{int(processed)}.wav"
            try:
                await asyncio.to_thread(extract_chunk, src, processed, span, chunk_file)
                async with _SEM:
                    res = await asyncio.to_thread(asr.transcribe, chunk_file, lang=language)
            finally:
                chunk_file.unlink(missing_ok=True)
            segs = shift_segments(res.get("segments") or [], processed, processed + span)
            ckpt = append_chunk(ckpt, segs, processed_seconds=processed + span,
                                duration=duration, model=model, language=language,
                                chunk_seconds=chunk_seconds)
            _write_json(ckpt_file, ckpt)
            if on_step:
                on_step(ckpt["processed_seconds"], duration)
    finally:
        try:
            tmp_dir.rmdir()
        except OSError:
            pass

    doc = document_from_checkpoint(ckpt)
    if not doc["segments"]:
        raise TranscriptError("没检测到人声（可能是纯音乐或静音视频）")
    _write_json(result_path(folder, mid), doc)
    ckpt_file.unlink(missing_ok=True)
    return doc
