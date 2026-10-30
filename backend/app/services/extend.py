"""视频延长（向前/向后）：官方能力 + 本地接缝处理。

官方口径（本机 `D:/tmp/official/sd25/guide.md`）：
- 2.5 指南「有锁定：编辑/首尾帧/延长」表 —— 延长任务**锁定宽高比**
  （`ratio` 必须 `adaptive`）、**时长由用户定**；`content.role` 用
  reference_video / reference_image / reference_audio；提示词里出现
  「向前/向后延长、延续、续写」之一即触发。
- 2.0 指南 §延长视频 —— 句式「向前/向后延长<视频N>，生成…」；
  并明确别写「参考<视频N>」，否则会被判成参考任务。
- 2.0 指南 §「延长视频衔接处跳变」—— 拼接前段末尾删 6 帧、后段开头删 1 帧；
  2.5 指南的案例则明确「第 15s 附近没有拼接痕迹」→ 2.5 不裁。

模型只返回**新延出来的那一段**（官方示例把「输出」和「拼接后的视频」分开给），
拼接在本地做 —— 这也是官方给的用法。
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from app.services import clone_store as store, media, models, scene

log = logging.getLogger(__name__)

# 官方时长区间：2.0 系列单段 [4,15]s、2.5 单段 [4,30]s。延长段至少 2s 才有意义。
MIN_SEC = 2


def seam_frames(model: str) -> tuple[int, int]:
    """(前一段末尾裁几帧, 后一段开头裁几帧)。

    🩸 依据：2.0 指南 §「延长视频衔接处跳变」—— 前段末尾**删 6 帧**、
    后段开头**删 1 帧**；而 2.5 指南明确拼接处无痕迹，不裁（裁了反而掉内容）；
    H3 官方没给任何接缝计帧规则 → 也不裁（按 6+1 硬裁只是白吃内容）。
    三家各自声明在 `Caps.extend_seam`，核心只读不判。
    """
    return tuple(models.adapter_for(model=model).caps.extend_seam)


def clamp_seconds(seconds: int, model: str) -> int:
    spec = models.adapter_for(model=model).specs_for(model)
    lo = max(MIN_SEC, int(round(float(spec.get("min_sec") or MIN_SEC))))
    hi = int(spec.get("max_sec") or 15)
    return max(lo, min(int(seconds or 0), hi))


def pick_resolution(model: str, width: int, height: int, wanted: str = "") -> str:
    """延长段用哪一档清晰度：跟着待延长视频走，但必须落在该型号收的档位里。

    延长段和原片尺寸不一致会让接缝更明显，所以默认按待延长视频的短边选档；
    但 2.0 极速 / Mini 最高只到 720p —— 原片 1080p 时直接送 1080p 会被 400，
    这一步把它收回到该型号自己的默认档（不会再出现"界面能选、提交就报错"）。
    """
    spec = models.adapter_for(model=model).specs_for(model)
    # 🩸 档位是**大小写敏感**的：火山是 480p/720p/1080p，H3 是 768P/2K。
    # 统一小写会让 H3 收到 "768p"（官方枚举里没有这个值）→ 400。
    allowed = [str(x) for x in (spec.get("resolutions") or [])]
    canon = {a.lower(): a for a in allowed}
    res = (wanted or "").strip()
    if not res:
        # 720p/1080p 说的是**短边**（竖屏 1080×1920 也是 1080p）
        short = min(int(width or 0), int(height or 0))
        res = "1080p" if short >= 1080 else "720p"
    if allowed and res.lower() not in canon:
        res = str(spec.get("default_resolution") or allowed[-1])
    elif allowed:
        res = canon[res.lower()]
    return res


def normalize_ref(src: Path, out: Path, *, min_px: int, max_px: int) -> Path:
    """待延长的视频若像素不够，等比放大到刚好达标再送。

    🩸 2026-10-24 实测：一条 836×480（401,280 px）的成片去延长，2.5 直接 400 拒单 ——
    差 6,416 像素（1.6%）。放大 1.6% 肉眼不可见，但不放大这条片子就永远延不了。
    已经达标就**原样返回**，不重编码（不白掉一遍画质）。

    上下限由 `Caps.extend_ref_min_px / max_px` 给（各家数字不一样，核心不写死）。
    """
    info = scene.probe(src)
    w = int(info.get("width") or 0)
    h = int(info.get("height") or 0)
    if w <= 0 or h <= 0:
        raise ValueError(f"读不出待延长视频的画面尺寸：{src}")
    px = w * h
    if min_px <= px <= max_px:
        return src

    if px > max_px:
        # 太大极少见，等比缩到上限以下（短边保持偶数）
        k = (max_px / px) ** 0.5
    else:
        k = (min_px / px) ** 0.5
    nw = max(2, int(round(w * k)) // 2 * 2)
    nh = max(2, int(round(h * k)) // 2 * 2)
    # 取整后可能又掉到线下，按高度补齐宽度（保持宽高比到 0.1% 以内）
    if nw * nh < min_px:
        nw = max(nw, int(-(-min_px // nh)) + 1)
        nw += nw % 2

    ff = media.ffmpeg_path()
    if not ff:
        raise RuntimeError("找不到 ffmpeg，请设置 VT_FFMPEG")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ff, "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
           "-vf", f"scale={nw}:{nh}:flags=lanczos",
           "-c:v", "libx264", "-preset", "medium", "-crf", "18",
           "-pix_fmt", "yuv420p"]
    if info.get("has_audio"):
        cmd += ["-c:a", "aac", "-b:a", "128k"]
    else:
        cmd += ["-an"]
    cmd.append(str(out))
    r = _run(cmd, timeout=600)
    if r.returncode != 0 or not out.exists():
        raise RuntimeError(f"待延长视频放大失败：{(r.stderr or '').strip()[:300]}")
    log.info("待延长视频 %dx%d(%d px) 不足下限，已放大到 %dx%d(%d px)",
             w, h, px, nw, nh, nw * nh)
    return out


def clip_ref(src: Path, out: Path, direction: str, *,
             max_sec: float, max_mb: float) -> Path:
    """把要续写的源片截成该型号收得下的那一段。

    接续点永远在"送进去那一段"的端点，所以向后延截**尾巴**、向前延截**开头** ——
    截中间会让模型的续写起点和成片接缝对不上。
    已经 ≤max_sec 且 ≤max_mb 就原样返回，不重编码。
    """
    info = scene.probe(src)
    dur = float(info.get("duration") or 0)
    if dur <= 0:
        raise ValueError("读不出待延长视频的时长")
    size_mb = Path(src).stat().st_size / (1024 * 1024)
    if dur <= max_sec and size_mb <= max_mb:
        return src

    if dur <= max_sec:
        start, length = 0.0, dur
    elif direction == "front":
        start, length = 0.0, max_sec
    else:
        start, length = max(0.0, dur - max_sec), max_sec

    ff = media.ffmpeg_path()
    if not ff:
        raise RuntimeError("找不到 ffmpeg，请设置 VT_FFMPEG")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ff, "-hide_banner", "-loglevel", "error", "-y",
           "-ss", f"{start:.3f}", "-t", f"{length:.3f}", "-i", str(src),
           "-c:v", "libx264", "-preset", "medium", "-crf", "18",
           "-pix_fmt", "yuv420p"]
    cmd += (["-c:a", "aac", "-b:a", "128k"]
            if info.get("has_audio") else ["-an"])
    cmd.append(str(out))
    r = _run(cmd, timeout=600)
    if r.returncode != 0 or not out.exists():
        raise RuntimeError(f"参考片截取失败：{(r.stderr or '').strip()[:300]}")
    log.info("参考片截取 %.1fs→%.1fs（起点 %.1fs）", dur, length, start)
    return out


def prep_ref(src: Path, out: Path, direction: str, model: str) -> Path:
    """把待延长的源片收进**该型号**收得下的形状。

    两条口径各自成立、不许互相搬：
      · `pixel_floor`：总像素有硬下限，不够就等比放大（火山 2.0 / 2.5）；
      · `clip`：单段时长/体积有上限，超了就截（H3）。
    🩸 哪个型号走哪条，由 `Caps.extend_ref_mode` 声明，核心不判断"这是哪一家"。
    """
    caps = models.adapter_for(model=model).caps
    if caps.extend_ref_mode == "pixel_floor":
        return normalize_ref(src, out, min_px=caps.extend_ref_min_px,
                             max_px=caps.extend_ref_max_px)
    if caps.extend_ref_mode == "clip":
        return clip_ref(src, out, direction, max_sec=caps.extend_ref_max_sec,
                        max_mb=caps.extend_ref_max_mb)
    return src


def _run(cmd: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True,
                          errors="ignore", timeout=timeout)


def stitch(prev: Path, nxt: Path, out: Path, *, model: str) -> dict:
    """把前一段和延出来的一段拼成一条，顺带处理接缝。

    两段的尺寸/帧率可能不一致（模型按待延长视频锁定比例，但编码参数不一定一样），
    统一到前一段的规格再拼。缺音轨的那一段补等长静音，别让 concat 吃掉整条音轨。
    """
    ff = media.ffmpeg_path()
    if not ff:
        raise RuntimeError("找不到 ffmpeg，请设置 VT_FFMPEG")

    a, b = scene.probe(prev), scene.probe(nxt)
    if not (a.get("width") and a.get("height")):
        raise ValueError("无法读取待延长视频的画面尺寸")
    width = int(a["width"]) // 2 * 2
    height = int(a["height"]) // 2 * 2
    fps = float(a.get("fps") or 0) or float(b.get("fps") or 0) or 30.0

    cut_a, cut_b = seam_frames(model)
    a_dur = float(a.get("duration") or 0)
    b_dur = float(b.get("duration") or 0)
    if a_dur <= 0 or b_dur <= 0:
        raise ValueError("无法读取待拼接视频的时长")

    # 前一段末尾裁 cut_a 帧；后一段开头裁 cut_b 帧
    a_end = max(0.2, a_dur - cut_a / fps) if cut_a else a_dur
    b_start = min(max(0.0, cut_b / fps), max(0.0, b_dur - 0.5)) if cut_b else 0.0
    a_len = max(0.2, a_end)
    b_len = max(0.2, b_dur - b_start)

    def vchain(i: int, start: float, end: float) -> str:
        return (f"[{i}:v]trim=start={start:.6f}:end={end:.6f},"
                f"setpts=PTS-STARTPTS,"
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,"
                f"fps={fps:.3f}[v{i}]")

    def achain(i: int, start: float, end: float, has: bool, length: float) -> str:
        if has:
            return (f"[{i}:a]atrim=start={start:.6f}:end={end:.6f},"
                    f"asetpts=PTS-STARTPTS,aresample=48000[a{i}]")
        return (f"anullsrc=channel_layout=stereo:sample_rate=48000,"
                f"atrim=duration={length:.6f},asetpts=PTS-STARTPTS[a{i}]")

    parts = [
        vchain(0, 0.0, a_end),
        vchain(1, b_start, b_dur),
        achain(0, 0.0, a_end, bool(a.get("has_audio")), a_len),
        achain(1, b_start, b_dur, bool(b.get("has_audio")), b_len),
        "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]",
    ]
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = _run([
        ff, "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(prev), "-i", str(nxt),
        "-filter_complex", ";".join(parts),
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-crf", "20", "-preset", "veryfast",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", str(out),
    ])
    if proc.returncode != 0 or not out.exists():
        raise RuntimeError(f"拼接失败：{(proc.stderr or '')[-300:]}")
    log.info("延长拼接完成 %s（前段裁 %d 帧 / 后段裁 %d 帧）", out.name, cut_a, cut_b)
    return {"cut_prev_frames": cut_a, "cut_next_frames": cut_b,
            "prev_seconds": round(a_len, 3), "next_seconds": round(b_len, 3)}


def run(cid: str, rid: str, *, direction: str, seconds: int, content: str,
        base: Path, model: str, resolution: str, with_audio: bool,
        with_transition: bool = False, transition_desc: str = "",
        ref_images: list[Path] | None = None, content_mode: str = "",
        progress=None) -> dict:
    """执行一次延长，产物写进 render_dir(cid, rid)/out.mp4。

    `base` = 待延长的视频（原片或某一次成片）。返回给任务记录用的摘要。

    🩸 `ref_images`（2026-10-28）：延长**可以**带参考图 —— 官方 `sd25-guide:93` 的
      延长示例是「向后延长 @video1，**@image1 的角色从天而降**」。顺序就是
      提示词里的 `@图片N`（第 N 张 = 列表第 N 项），这里不排序、不去重。
      哪家支持由 `Caps.extend_ref_images` 声明：2.5 声明，2.0 / H3 收到就报错
      —— **不静默丢掉**（丢了等于用户写了 @图片1、实际什么都没发）。
    """
    def tick(stage: str, pct: int) -> None:
        if progress:
            progress(stage, pct)

    workdir = store.render_dir(cid, rid)
    direction = "front" if direction == "front" else "back"
    seconds = clamp_seconds(seconds, model)
    ad = models.adapter_for(model=model)

    # 🩸 预设续法（2026-10-28）：只有声明了 `Caps.extend_modes` 的型号（目前只有 2.5）
    #   才有。用户点一句「让动作自然走完」就不用自己写内容 —— 会写的人照旧写内容，
    #   **自己写的内容优先**（`content` 非空时 mode 整个忽略）。
    #   条目本身出自 2.5 自己的官方列举，这里只是从适配器取，核心不认识任何一家。
    mode = (content_mode or "").strip()
    if not (content or "").strip():
        modes = ad.caps.extend_modes or {}
        if mode and mode in modes:
            content = modes[mode]
        elif mode:
            raise RuntimeError(
                f"{ad.caps.display_name or ad.model_id} 没有「{mode}」这种续法")

    # 🩸 空内容必须在**花钱之前**拦住。三家的句式都是「…延长@视频1，生成<内容>」，
    #    `content` 空 ⇒ 发出去的是残句「向后延长@视频1，生成」，模型不知道要生成
    #    什么，钱照扣。前端 `result.vue` 有拦，但接口是公开的，不能只靠前端。
    if not (content or "").strip():
        raise RuntimeError("延长要写一句「续出来的这段里发生什么」")
    # 三套提示词各在各家（`extend_prompt`），核心只调；没实现就当场说清楚，
    # 绝不回落成别家的句式（回落了就是"静默走错厂商"）。
    if ad.extend_prompt is None or ad.extend_submit is None:
        raise RuntimeError(
            f"{ad.caps.display_name or ad.model_id} 这个型号没有接延长能力"
            "（适配器缺 `extend_prompt` / `extend_submit`）")
    refs = [Path(x) for x in (ref_images or []) if x is not None]
    if refs and not ad.caps.extend_ref_images:
        raise RuntimeError(
            f"{ad.caps.display_name or ad.model_id} 的延长不支持带参考图 —— "
            "取消勾选参考素材，或换成火山 Seedance 2.5")
    prompt = ad.extend_prompt(direction, content)

    tick("延长中", 20)
    seg = workdir / f"extend_{direction}.mp4"

    # 🩸 送进去的源片必须先收进该型号的硬门槛（像素下限 / 时长上限）：
    #    836×480 这种 480p 成片差 1.6% 就会被 400 拒单。
    #    送到模型的是收拾过的那份，**拼接仍用原片**（`base`），成片分辨率不受影响。
    ref_src = prep_ref(base, workdir / f"extend_ref_{direction}.mp4", direction, model)
    ad.extend_submit(prompt=prompt, ref_src=ref_src, seg=seg, model=model,
                     resolution=resolution, seconds=seconds,
                     with_audio=bool(with_audio), cid=cid, ref_images=refs)
    tick("拼接中", 75)

    # 时间顺序：向后延长 = 原片在前；向前延长 = 新段在前
    if direction == "front":
        seam = stitch(seg, base, workdir / "out.mp4", model=model)
    else:
        seam = stitch(base, seg, workdir / "out.mp4", model=model)

    # B7 无缝转场：把接缝前后各 `HALF` 秒的**画面**换成模型生成的过渡段。
    # 直接拿拼好的成片在接缝两侧各切 2 秒当素材 —— 坐标最简单，且天然就是
    # 观众真正会看到的那两段画面。音轨整条沿用，总时长不变。
    # 有没有「两段视频补全」能力由 `Caps.extend_transition` 声明（H3 没有）。
    seam_tr: dict = {}
    if with_transition:
        if not ad.caps.extend_transition:
            seam_tr = {"transition": False,
                       "transition_error":
                           f"{ad.caps.display_name or ad.model_id} 没有「两段视频补全」能力"}
        else:
            try:
                from app.core.config import settings as _st
                from app.services import transition as _tr

                at = float(seam.get("prev_seconds") or 0)
                clip = _tr.make_seam(
                    workdir / "out.mp4", at, workdir / "out.mp4", at,
                    workdir=workdir, model=_st.clone_seam_model,
                    desc=transition_desc,
                    cache_dir=store.task_dir(cid) / "cache" / "seam",
                )
                _tr.replace_seam_in_file(
                    workdir / "out.mp4", seam_at=at, seam=clip,
                    dest=workdir / "out_seam.mp4")
                (workdir / "out_seam.mp4").replace(workdir / "out.mp4")
                seam_tr = {"transition": True, "seam_at": round(at, 3)}
            except Exception as e:  # noqa: BLE001
                # 补不上就交硬接的成片：钱已经花了，别让整条延长作废
                log.warning("接缝转场没做成（保留硬接的成片）：%s", e)
                seam_tr = {"transition": False, "transition_error": str(e)[:200]}

    total = float(scene.probe(workdir / "out.mp4").get("duration") or 0)
    try:
        from app.services import compose

        compose.make_cover(workdir / "out.mp4", workdir / "cover.jpg",
                           at=min(0.5, max(0.0, total / 2)))
    except Exception as e:  # noqa: BLE001
        log.warning("延长成片封面生成失败（不影响成片）：%s", e)

    tick("done", 100)
    return {
        "kind": "extend",
        "duration": round(total, 3),
        "extend": {
            "direction": direction,
            "seconds": seconds,
            "prompt": prompt,
            "model": model,
            "channel": ad.caps.family,
            "with_audio": bool(with_audio),
            **seam,
            **seam_tr,
        },
    }
