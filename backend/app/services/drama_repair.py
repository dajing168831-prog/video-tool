"""商品短剧 · 窗口精准修复 —— 只重做坏掉的那几秒，再本地拼回原段。

做法来源：开源项目 **clipforge**（AGPL-3.0）的
`src/lib/video-repair-plan.ts` + `src/lib/video-repair-render.ts`，
**只抽结构、不复制代码**：

  1. 在**花钱前**把窗口、生成时长、花费、指纹算清楚（本模块 `plan`）；
  2. 远端只生成一个**替换片段**（我们走官方「图生视频-首尾帧」：
     `sd25/api-create-task.md:27`，首尾两张图从原段窗口两端抽出来，
     保证接缝两边画面一致）；
  3. 本地裁切拼接：前段 + 替换段 + 后段，**原音轨整条保留**（`-map 0:a:0`）；
  4. 原段文件不动，修复版另存一份，`prev` 记着旧名字，随时能切回
     （clipforge `video-repair-finalize.ts`「原版本仍可切回」）。

为什么不用参考视频编辑：Seedance 2.5 的「全模态参考」与「首尾帧」是
**互斥**场景（`api-create-task.md:269`），而修复最要紧的是接缝严格一致，
官方原话就是「若需严格保障首尾帧和指定图片一致，**优先使用图生视频-首尾帧**」
（`:271`）。所以这条路径走首尾帧，不带任何参考图。
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import subprocess
import tempfile
from pathlib import Path

from app.services.media import ffmpeg_path
from app.services.scene import probe

log = logging.getLogger(__name__)

#: 窗口最短 0.5s（clipforge `deriveRepairWindow` 的下限）
MIN_WINDOW_SEC = 0.5


def derive_window(duration: float, start: float = 0,
                  end: float = 0) -> tuple[float, float, str]:
    """把用户给的（或空着的）区间夹进片长内，返回 `(start, end, 说明)`。

    空区间 = 从片头起 5 秒（clipforge `deriveRepairWindow` 同款兜底）；
    两边都给了就夹紧；不足 0.5 秒的区间会补到 0.5 秒 —— 太短的窗口
    拼回去必然跳帧。
    """
    dur = max(MIN_WINDOW_SEC, float(duration or 0))
    if not (float(start or 0) > 0 or float(end or 0) > 0):
        return 0.0, round(min(dur, 5.0), 3), "没给区间，默认从片头起 5 秒"
    s = max(0.0, min(float(start or 0), dur - MIN_WINDOW_SEC))
    e = min(dur, float(end or 0))
    if e - s < MIN_WINDOW_SEC:
        e = min(dur, s + MIN_WINDOW_SEC)
        if e - s < MIN_WINDOW_SEC:
            s = max(0.0, e - MIN_WINDOW_SEC)
    return round(s, 3), round(e, 3), ""


def billed_duration(repair_sec: float, *, min_sec: float, max_sec: float) -> float:
    """模型实际要生成多少秒（按整数秒向上取，并夹进型号区间）。

    🩸 模型按**生成时长**计费，不是按替换区间计费：窗口 2.5s 也要生成
    4s（2.5/2.0 的下限都是 4s）。这个数字必须原样显示在确认卡上。
    """
    want = max(MIN_WINDOW_SEC, float(repair_sec or 0))
    seconds = max(float(min_sec or 4), float(math.ceil(want)))
    return round(min(seconds, float(max_sec or seconds)), 3)


def repair_prompt(segment_prompt: str, start: float, end: float, note: str = "") -> str:
    """修复用的提示词 = **窗口指令 + 原段提示词原文**（不自造画面描述）。

    窗口指令照 clipforge `video-repair-plan.ts:171` 的组织方式重写；
    画面内容仍然只来自原分镜那一段提示词，`note` 是使用者自己填的修正说明。
    """
    head = (f"只重做原镜头第 {start:.2f}–{end:.2f} 秒这一段，其余不动；"
            "首帧和尾帧与给出的两张图完全一致，前后构图、人物、商品、服装、光线保持连续。")
    body = (segment_prompt or "").strip()
    tail = f"需要修正：{note.strip()}" if (note or "").strip() else ""
    return "\n".join(x for x in (head, body, tail) if x)


def plan(source: Path, segment_prompt: str, *, start: float = 0, end: float = 0,
         note: str = "", model: str, min_sec: float = 4.0, max_sec: float = 15.0,
         resolution: str = "720p", price_per_sec: float = 0) -> dict:
    """预览（**纯计算 + 一次 ffprobe，不花钱**）。"""
    info = probe(source)
    dur = float(info.get("duration") or 0)
    if dur <= 0:
        raise ValueError("原段读不出时长，不能修复")
    s, e, note_window = derive_window(dur, start, end)
    repair_sec = round(e - s, 3)
    billed = billed_duration(repair_sec, min_sec=min_sec, max_sec=max_sec)
    prompt = repair_prompt(segment_prompt, s, e, note)
    source_id = _source_id(source, dur)
    rate = float(price_per_sec or 0)
    summary = {
        "version": 1,
        "kind": "drama-repair",
        "source": source_id,
        "window": {"start": s, "end": e},
        "generated_seconds": billed,
        "model": model,
        "resolution": resolution,
        "prompt": prompt,
    }
    return {
        **summary,
        "source_name": source.name,
        "source_seconds": round(dur, 3),
        "repair_seconds": repair_sec,
        "note": note_window,
        "plan_hash": _hash(summary),
        "price": _price(billed, rate),
    }


def verify(source: Path, segment_prompt: str, plan_hash: str, **kw) -> tuple[dict, str]:
    """付费前二次 dryRun：按**现在的**原段和参数重算，指纹对不上就中止。"""
    if not plan_hash:
        return {}, "缺 plan_hash —— 先预演一次，看清区间和花费再修"
    fresh = plan(source, segment_prompt, **kw)
    if fresh["plan_hash"] != plan_hash:
        return fresh, ("修复计划和你看的那一版不一样了（原段/区间/参数改过）—— "
                       "重新预演并确认后再修；本次没有提交、没有扣费")
    return fresh, ""


def render(source: Path, out: Path, *, start: float, end: float, prompt: str,
           model: str, billed: float, resolution: str,
           timeout: float = 900, poll: float = 4.0) -> Path:
    """生成替换片段 → 本地拼回原段。**这一步花钱**，调用方必须已过指纹闸。"""
    from app.services import ark

    info = probe(source)
    dur = float(info.get("duration") or 0)
    width = max(2, int(info.get("width") or 0) // 2 * 2)
    height = max(2, int(info.get("height") or 0) // 2 * 2)
    fps = float(info.get("fps") or 30) or 30
    if dur <= 0 or width <= 0 or height <= 0:
        raise ValueError("原段读不出画面参数，不能修复")

    with tempfile.TemporaryDirectory(prefix="drama-repair-") as td:
        tmp = Path(td)
        first = tmp / "first.jpg"
        last = tmp / "last.jpg"
        _grab_frame(source, start, first)
        _grab_frame(source, max(start, end - 0.05), last)
        raw = tmp / "replacement.mp4"
        ark.generate_video(prompt, out=raw, model=model, first_frame=first,
                           last_frame=last, duration=int(round(billed)),
                           ratio="adaptive", resolution=resolution,
                           timeout=timeout, poll=poll)
        if not raw.exists() or raw.stat().st_size == 0:
            raise ValueError("替换片段没落盘，原段保持不变")
        _splice(source, raw, out, start=start, end=end,
                repair_sec=round(end - start, 3), duration=dur,
                width=width, height=height, fps=fps,
                has_audio=bool(info.get("has_audio")))
    return out


def _source_id(source: Path, duration: float) -> str:
    """原段身份：文件名 + 大小 + 时长。文件名带时间戳，重出不会撞名。"""
    try:
        size = source.stat().st_size
    except OSError:
        size = 0
    return f"{source.name}|{size}|{round(duration, 3)}"


def _hash(summary: dict) -> str:
    raw = json.dumps(summary, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _price(seconds: float, rate: float) -> dict:
    if rate <= 0:
        return {"known": False, "amount": None, "currency": "CNY", "rate": 0,
                "seconds": seconds,
                "note": "没配置单价（VT_PRICE_VIDEO_PER_SEC）—— 平台账单出来前不知道要花多少"}
    return {"known": True, "amount": round(rate * seconds, 2), "currency": "CNY",
            "rate": rate, "seconds": seconds,
            "note": "按已配置单价 × 生成秒数估算，不承诺等于平台账单"}


def _ffmpeg() -> str:
    exe = ffmpeg_path()
    if not exe:
        raise RuntimeError("找不到 ffmpeg，请设置 VT_FFMPEG")
    return exe


def _grab_frame(source: Path, at: float, out: Path) -> None:
    """从原段抽一帧（`-ss` 放 `-i` 前 = 快速定位，现代 ffmpeg 会补解到准确帧）。"""
    cmd = [_ffmpeg(), "-nostdin", "-v", "error", "-y",
           "-ss", f"{max(0.0, at):.3f}", "-i", str(source),
           "-frames:v", "1", "-q:v", "2", str(out)]
    p = subprocess.run(cmd, capture_output=True, text=True, errors="ignore",
                       timeout=120)
    if p.returncode != 0 or not out.exists() or out.stat().st_size == 0:
        raise RuntimeError(f"抽帧失败（{at:.2f}s）：{(p.stderr or '')[:200]}")


def build_filter(start: float, end: float, repair_sec: float, duration: float,
                 width: int, height: int, fps: float) -> str:
    """拼接滤镜图。判据来自 clipforge `video-repair-render.ts:47-58`：

    - 每段先归一（fps / 缩放补边 / setsar / yuv420p），否则 concat 会报流不匹配；
    - 替换段先 `tpad=stop_mode=clone` 再裁到**精确**区间长 —— 生成时长比区间短时
      用最后一帧顶住，绝不靠"大概齐"；
    - 前段/后段按真实时间码切，接缝落在原时间轴上。
    """
    w, h = max(2, width // 2 * 2), max(2, height // 2 * 2)
    rate = max(1.0, min(120.0, float(fps or 30)))

    def norm(inp: str) -> str:
        return (f"{inp},fps={rate:.3f},"
                f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p")

    filters: list[str] = []
    segs: list[str] = []
    if start > 0.02:
        filters.append(norm(f"[0:v]trim=start=0:end={start:.3f},setpts=PTS-STARTPTS")
                       + "[vbefore]")
        segs.append("[vbefore]")
    filters.append(
        norm(f"[1:v]tpad=stop_mode=clone:stop_duration={repair_sec:.3f},"
             f"trim=start=0:end={repair_sec:.3f},setpts=PTS-STARTPTS")
        + "[vrepair]")
    segs.append("[vrepair]")
    if end < duration - 0.02:
        filters.append(norm(f"[0:v]trim=start={end:.3f}:end={duration:.3f},"
                            "setpts=PTS-STARTPTS") + "[vafter]")
        segs.append("[vafter]")
    if len(segs) > 1:
        filters.append(f"{''.join(segs)}concat=n={len(segs)}:v=1:a=0[vout]")
    else:
        filters.append(f"{segs[0]}null[vout]")
    return ";\n".join(filters)


def _splice(source: Path, replacement: Path, out: Path, *, start: float, end: float,
            repair_sec: float, duration: float, width: int, height: int, fps: float,
            has_audio: bool) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    graph = build_filter(start, end, repair_sec, duration, width, height, fps)
    cmd = [_ffmpeg(), "-nostdin", "-v", "error", "-y",
           "-i", str(source), "-i", str(replacement),
           # 🩸 本机 ffmpeg 9 已经把 `-filter_complex_script` 去掉了
           # （`ffmpeg -h full` 只剩 `-filter_complex`）—— 图直接当参数传，
           # 不落临时脚本，别再照抄老版本的写法。
           "-filter_complex", graph,
           "-map", "[vout]", "-map", "0:a:0?"]
    if has_audio:
        # 原音轨整条保留：只换画面，声音不动 —— 修复不该改听感
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            "-t", f"{duration:.3f}", str(out)]
    p = subprocess.run(cmd, capture_output=True, text=True, errors="ignore",
                       timeout=900)
    if p.returncode != 0 or not out.exists() or out.stat().st_size == 0:
        raise RuntimeError(f"拼接失败：{(p.stderr or '')[:300]}")
