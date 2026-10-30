"""从零写：没有原片，台词 + 画面描述 → 成片。

和「复刻爆款」的区别只有一条：**没有结构可抄**。
复刻是"先读懂原片怎么剪的，再照着剪"；从零写是"你说怎么剪"。
所以这里不做分析、不建配方，直接把用户写的台词按行切开：

    一行台词 = 一个镜头
    画面描述可写 1 段（全片共用）或与台词等量的 N 段

每一步都是按钱的顺序排的，贵的放后面：

    1. 估时长（本地，0 元）—— 超长就先拦下，别等配音做完才发现
    2. 逐行配音（几分钱）
    3. **按真实配音时长复核一遍**（本地，0 元）—— 这一段念出来 18 秒、
       模型单段只收 15 秒，就在这里停，视频一次都不调
    4. 逐段生成画面（贵）
    5. 合成 + 字幕 + 质检（本地）

台词和画面都必须是用户写的：这一层不生成文案，也不替用户编分镜。
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from app.core.config import settings
from app.services import compose, qc, speech_est, subtitle_ass
from app.services import clone_pipeline

log = logging.getLogger(__name__)

RATIOS = ("9:16", "16:9", "1:1")
DEFAULT_RATIO = "9:16"


class ScratchError(RuntimeError):
    """能直接说给用户听的原因（没花钱或者只花了配音的钱）。"""


def split_lines(text: str) -> list[str]:
    """一行一个镜头；只写了一段就按**句末标点**断。

    这里不用复刻那条链的断句（`_split_script`）——它会把短句合并到一行字幕的长度，
    而在从零写里**一行就是一个镜头**，合并等于偷偷改了用户定的镜头数。
    """
    lines = [s.strip() for s in re.split(r"[\r\n]+", text or "") if s.strip()]
    if len(lines) > 1:
        return lines
    line = (text or "").strip()
    if not line:
        return []
    parts = [p.strip() for p in re.split(r"[。！？!?；;…]+", line) if p.strip()]
    return parts or [line]


def build_shots(script: str, descs: str) -> list[dict]:
    """台词行 ↔ 画面行。对不上就说清怎么对不上，不猜、不凑。"""
    texts = split_lines(script)
    if not texts:
        raise ScratchError("台词是空的：从零写至少得有一句要念的话")
    pics = [s.strip() for s in re.split(r"[\r\n]+", descs or "") if s.strip()]
    if not pics:
        raise ScratchError("画面是空的：每个镜头至少写一句要出现什么")
    if len(pics) == 1:
        pics = pics * len(texts)
    elif len(pics) != len(texts):
        raise ScratchError(
            f"画面写了 {len(pics)} 段，台词有 {len(texts)} 段。"
            f"要么画面只写 1 段（全片共用），要么写成 {len(texts)} 段。"
        )
    return [{"text": t, "desc": d, "i": i} for i, (t, d) in enumerate(zip(texts, pics))]


def bounds(channel: str, model: str) -> tuple[float, float]:
    from app.services import video_edit

    ch = channel if channel in ("volc", "minimax") else "volc"
    return video_edit.bounds_for(ch, model)


def plan(script: str, descs: str, *, lang: str = "zh",
         channel: str = "auto", model: str = "") -> dict:
    """出片前预览：**只在本地算，不调任何模型**。"""
    shots = build_shots(script, descs)
    lo, hi = bounds(channel, model)
    rows, blocked = [], []
    total = 0.0
    for s in shots:
        est = speech_est.estimate(s["text"], lang or "zh")
        total += max(est, lo)
        rows.append({"i": s["i"], "chars": len(s["text"]),
                     "est_seconds": round(est, 2),
                     "video_seconds": round(min(max(est, lo), hi), 2)})
        if est > hi:
            blocked.append(
                f"第 {s['i'] + 1} 行念出来约 {est:.1f} 秒，超过单段上限 {hi:.0f} 秒，请拆成两行"
            )
    rate = float(settings.price_video_per_sec or 0)
    return {
        "shots": rows,
        "count": len(rows),
        "est_seconds": round(total, 2),
        "video_calls": len(rows),
        "bounds": [lo, hi],
        "blocked": blocked[0] if blocked else "",
        "price": {
            "known": rate > 0,
            "amount": round(total * rate, 2) if rate > 0 else None,
            "rate": rate,
            "note": "按已配置单价估算，不承诺准确总价（配音时长是估算）",
        },
    }


# ---------------------------------------------------------------------------


def _probe(path: Path) -> dict:
    from app.services import scene

    return scene.probe(path)


def _gen_one(channel: str, model: str, prompt: str, out: Path, *,
             duration: int, ratio: str, resolution: str) -> Path:
    if channel == "minimax":
        from app.services import minimax

        return minimax.generate_video(
            [{"type": "text", "text": prompt}], out=out,
            duration=int(duration), resolution=resolution or "", ratio=ratio,
            model=model or "",
        )
    from app.services import ark

    return ark.generate_video(
        prompt, out=out, model=model or "", duration=int(duration),
        ratio=ratio, resolution=resolution or "720p",
    )


def render(*, script: str, descs: str, workdir: Path, ratio: str = DEFAULT_RATIO,
           resolution: str = "", channel: str = "auto", model: str = "",
           voice: str = "", lang: str = "", want_subtitle: bool = True,
           progress=None) -> dict:
    """真正出片。返回 {duration, segments, regen_meta, qc, voice_meta}。"""
    from app.services import voice_catalog
    from app.services.providers.tts import get_tts

    def p(stage: str, pct: int) -> None:
        if progress:
            progress(stage, pct)

    shots = build_shots(script, descs)
    lang = (lang or "").strip().lower() or speech_est.detect_lang(
        " ".join(s["text"] for s in shots))
    ch = channel if channel in ("volc", "minimax") else (
        "volc" if settings.ark_api_key else "minimax")
    lo, hi = bounds(ch, model)

    # 1) 先按估算拦一次：明显超长的行不必走到配音
    for s in shots:
        est = speech_est.estimate(s["text"], lang)
        if est > hi:
            raise ScratchError(
                f"第 {s['i'] + 1} 行念出来约 {est:.1f} 秒，超过单段上限 {hi:.0f} 秒，请拆成两行")

    # 2) 配音
    p("tts", 10)
    tts = get_tts()
    voice_dir = workdir / "voice"
    voice_dir.mkdir(parents=True, exist_ok=True)
    voice_id, voice_note = voice_catalog.resolve(voice, lang)
    ext = getattr(tts, "ext", ".mp3")
    voices: list[Path] = []
    for s in shots:
        f = voice_dir / f"v{s['i']:03d}{ext}"
        tts.synth(s["text"], f, voice=voice_id)
        voices.append(f)
        p("tts", 10 + int(20 * (s["i"] + 1) / len(shots)))

    durs = [float(_probe(v)["duration"]) for v in voices]

    # 3) 用真实配音时长复核 —— 这一步花钱之前停住
    for s, d in zip(shots, durs):
        if d > hi:
            raise ScratchError(
                f"第 {s['i'] + 1} 行配音实际 {d:.1f} 秒，超过单段上限 {hi:.0f} 秒，请拆成两行")

    # 4) 逐段生成画面
    clips_dir = workdir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    gen_secs = [min(max(d, lo), hi) for d in durs]
    size = (0, 0, 0.0)
    clips = []
    for s, d, sec in zip(shots, durs, gen_secs):
        n = s["i"]
        p("video", 30 + int(55 * n / len(shots)))
        out = _gen_one(ch, model, s["desc"], clips_dir / f"g{n:03d}.mp4",
                       duration=int(round(sec)), ratio=ratio, resolution=resolution)
        if not size[0]:
            info = _probe(out)
            w, h, fps = info["width"], info["height"], info["fps"]
            size = (w - (w % 2), h - (h % 2), fps or 30.0)
        # 生成的片子可能比这段台词长：时间轴上按台词长度截，多出来的丢掉
        clips.append({"source": str(out), "start": 0.0, "end": round(d, 3),
                      "freeze": 0.0, "label": f"shot{n}"})

    # 5) 音轨拼成一条 + 字幕时间轴
    p("align", 86)
    segs, cursor = [], 0.0
    for s, d in zip(shots, durs):
        segs.append({"start": round(cursor, 3), "end": round(cursor + d, 3),
                     "text": s["text"]})
        cursor += d
    total = round(cursor, 3)
    voice_all = _join_audio(voices, workdir / "voice.mp3", total)

    ass = None
    if want_subtitle:
        ass = subtitle_ass.build_ass(
            segs, workdir / "cap.ass", width=size[0], height=size[1],
            style={"component": "karaoke"},
        )

    p("compose", 92)
    out = workdir / "out.mp4"
    compose.compose(
        video=Path(clips[0]["source"]), out=out, ass=ass, voice=voice_all,
        mask=None, pad_to=0.0, target=total, fps=size[2],
        clips=clips, size=size,
    )
    try:
        qc_res = qc.inspect(out, expect_duration=total, expect_w=size[0],
                            expect_h=size[1], expect_fps=size[2])
    except Exception as e:  # noqa: BLE001
        qc_res = {"ok": False, "issues": [f"质检没跑成：{e}"], "warnings": [], "stats": {}}
    try:
        compose.make_cover(out, workdir / "cover.jpg", at=min(0.5, total / 2))
    except Exception as e:  # noqa: BLE001
        log.warning("抽封面失败（不影响成片）：%s", e)

    return {
        "duration": total,
        "segments": segs,
        "replaced_shots": len(clips),
        "regen_channel": ch,
        "regen_model": _model_label(ch, model),
        "regen_meta": {"mode": "scratch", "segments": len(clips),
                       "cuts_refined": 0, "boundary": False},
        "voice_meta": {"lang": lang, "voice": voice_id,
                       "voice_label": voice_catalog.label(voice_id),
                       "voice_note": voice_note, "speech_rate": 0,
                       "est_seconds": round(sum(speech_est.estimate(s["text"], lang)
                                                for s in shots), 2),
                       "voice_seconds": total, "stretch": 1.0},
        "qc": qc_res,
    }


def _model_label(ch: str, model: str) -> str:
    try:
        from app.services import video_edit

        return video_edit.spec_label(ch, model)
    except Exception:  # noqa: BLE001
        return model or ""


def _join_audio(parts: list[Path], out: Path, total: float) -> Path:
    """N 段配音接成一条音轨。用 ffmpeg concat，不重编。"""
    from app.services.media import ffmpeg_path

    ff = ffmpeg_path()
    if not ff:
        raise ScratchError("找不到 ffmpeg，请设置 VT_FFMPEG")
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in parts),
                   encoding="utf-8")
    import subprocess

    proc = subprocess.run(
        [ff, "-hide_banner", "-loglevel", "error", "-y", "-f", "concat",
         "-safe", "0", "-i", str(lst), "-c", "copy", str(out)],
        capture_output=True, text=True, errors="ignore", timeout=300,
    )
    if proc.returncode != 0:
        raise ScratchError(f"配音拼接失败：{(proc.stderr or '')[:200]}")
    return out
