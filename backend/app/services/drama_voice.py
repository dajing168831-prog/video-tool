"""商品短剧 · 整片配音轨（D3 人声落地的前半截：先把 TTS 落成「按镜头一条」）。

为什么要有这一层：合成链里能不能做人声落地，前提是**每条台词有一个音频文件**，
而且要知道它属于哪一镜。竞品的做法是每镜一个 `audioPath`（`composer.ts:526-548`
`config.clips[].audioPath`），TTS 在剧本阶段就拼进 clip；我们的出片单元是「段」，
所以这里只做**按镜头**落盘 + 时长探测，混音交给 `drama_compose.build_graph`。

出处：
  · 每镜一条音轨、TTS 优先于原生音轨：`composer.ts:525-548`
  · 音色/语速：D1 的免费 Edge 音色表（`drama_tts.FREE_TTS_VOICES`）
  · 时长口径：以**实际合成文件**的 ffprobe 为准（`estimate_speech_seconds` 只用于没合成前的估算）

🩸 费用：免费 Edge 音色零 Key 零费用；付费四家不走这里（那条路要给各自的 Key，
`drama_tts.generate_speech` 已有试听口，整片配音不做付费分支 —— 别让一条广告片
在不知情的情况下按句计费）。
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from . import drama_tts

#: 一条配音最多几句话（保护提示词/磁盘；分镜本身远小于这个数）
MAX_LINES = 60
#: 单句最多多少字（与 D1 试听同口径 `MAX_PREVIEW_CHARS`）
MAX_CHARS = drama_tts.MAX_PREVIEW_CHARS


def track_dir(data_dir: Path, pid: str) -> Path:
    """配音文件落 `<data>/voice/<pid>/` —— 与 films / materials 平级，别塞进项目 json。"""
    return Path(data_dir) / "voice" / Path(pid).name


def lines_of(doc: dict) -> list[dict]:
    """分镜里有台词的镜头（按分镜顺序，一镜一条）。"""
    shots = ((doc.get("storyboard_json") or {}).get("shots") or [])
    out: list[dict] = []
    for s in shots:
        if not isinstance(s, dict):
            continue
        text = str(s.get("dialogue") or "").strip()
        if not text:
            continue
        try:
            sid = int(s.get("id"))
        except (TypeError, ValueError):
            continue
        out.append({"shot_id": sid, "text": text[:MAX_CHARS]})
        if len(out) >= MAX_LINES:
            break
    return out


def voice_of(doc: dict) -> str:
    """项目当前选中的音色（`doc["voice_track"]["voice"]`，没配过用默认免费音色）。"""
    v = str(((doc.get("voice_track") or {}).get("voice")) or "").strip()
    return v or drama_tts.DEFAULT_FREE_VOICE


def rate_of(doc: dict) -> str:
    r = str(((doc.get("voice_track") or {}).get("rate")) or "").strip()
    return r or "+0%"


async def build(doc: dict, *, data_dir: Path, voice: str = "", rate: str = "",
                synth=None) -> dict:
    """按当前分镜逐句合成，落盘后返回轨描述（**不写 doc**，由 API 层存）。

    `synth` 可注入（探针用假合成器；生产传空 = `drama_tts.generate_speech_free`）。
    """
    pid = str(doc.get("id") or "")
    if not pid:
        raise ValueError("项目没有 id")
    voice = (voice or voice_of(doc)).strip() or drama_tts.DEFAULT_FREE_VOICE
    rate = (rate or rate_of(doc)).strip() or "+0%"
    lines = lines_of(doc)
    if not lines:
        raise ValueError("分镜里没有台词，没有可配音的内容")

    out_dir = track_dir(data_dir, pid)
    out_dir.mkdir(parents=True, exist_ok=True)
    gen = synth or drama_tts.generate_speech_free
    items: list[dict] = []
    for ln in lines:
        res = await gen(ln["text"], voice=voice, rate=rate)
        audio = (res or {}).get("audio") if isinstance(res, dict) else res
        if not audio:
            raise drama_tts.TTSError(f"镜头 {ln['shot_id']} 没返回音频")
        name = f"{ln['shot_id']}.mp3"
        dst = out_dir / name
        tmp = dst.with_suffix(".tmp")
        tmp.write_bytes(audio)
        os.replace(tmp, dst)
        items.append({
            "shot_id": ln["shot_id"],
            "text": ln["text"],
            "file": name,
            "bytes": len(audio),
            "cached": bool((res or {}).get("cached")) if isinstance(res, dict) else False,
        })

    # 时长按**实际文件**测（合成时要拿它对槽位，估出来的数会在出口裁错）
    from . import drama_compose

    for it in items:
        info = drama_compose.probe(out_dir / it["file"])
        it["seconds"] = round(info["duration"], 3)
        it["has_audio"] = bool(info["has_audio"])
    bad = [it for it in items if not it["has_audio"] or it["seconds"] <= 0]
    if bad:
        raise drama_tts.TTSError(
            "这些镜头的配音文件读不出音频：" + "、".join(str(x["shot_id"]) for x in bad[:5]))

    return {
        "voice": voice,
        "rate": rate,
        "items": items,
        "count": len(items),
        "total_seconds": round(sum(it["seconds"] for it in items), 3),
        "built": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def usable(doc: dict, data_dir: Path) -> tuple[dict[int, dict], list[str]]:
    """项目里的配音轨 → `{shot_id: item}` + 问题清单。

    文件不在/读不出 → 记一条问题并从轨道里摘掉（合成时退回模型原生出声），
    由 plan 决定是 warning 还是 error。
    """
    pid = str(doc.get("id") or "")
    track = doc.get("voice_track") or {}
    root = track_dir(data_dir, pid)
    out: dict[int, dict] = {}
    problems: list[str] = []
    for it in (track.get("items") or []):
        if not isinstance(it, dict):
            continue
        try:
            sid = int(it.get("shot_id"))
        except (TypeError, ValueError):
            continue
        name = Path(str(it.get("file") or "")).name
        if not name:
            continue
        p = root / name
        if not p.exists():
            problems.append(f"镜头 {sid} 的配音文件不在了（{name}）")
            continue
        out[sid] = {**it, "file": name, "path": str(p)}
    return out, problems
