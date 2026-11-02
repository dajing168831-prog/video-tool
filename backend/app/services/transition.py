"""两段视频补全间隙（B7 无缝转场）。

一句话：**把时间轴上相邻两段之间的硬接缝，换成一模型生成的过渡段。**

官方出处：
  - 2.5 能力清单 `seedance-25-guide.md:69`「视频无缝转场 - 输入两段视频，
    模型生成补全间隙实现无缝转场」
  - 官方句式 `seedance-25-guide.md:1337`
  - 2.0 叫「轨道补齐」（`seedance-20-guide.md:988-1000`），≤3 段 / 总时长 ≤15s
  - 它属于**全模态参考生视频**，`volc-api:458` 说 `reference` 任务
    `ratio`/`duration` 无特殊限制；`duration` 下限 **4 秒**（`:588`）

🩸 **只接在延长链路**（2026-10-25 主人拍板）：原片 + AI 续写段之间那一个接缝
是真问题（官方 `seedance-20-guide.md:368-382` 专门讲这个坑），成本=多一条 4 秒。
**出片链路不接** —— 复刻要像原片，而原片的硬切就是原片的剪法，把剪辑点揉成
过渡反而不像；重绘段 ↔ 原片段的接缝另有 B6 尾帧锁定覆盖。
下面「时间轴」那一组（`split_by_marks` / `shot_marks` / `patch`）因此**没有调用方**，
留着是为了以后真要接时不重写，不许当成已上线能力。

三个硬约束（每一条都决定了形状）：
  1. **总时长必须不变**：接缝两侧各让出 `HALF` 秒、中间插 `SEAM_SECONDS`。
     成片配音轨（`tracks.from_legacy`）是独立一条，总长不变就不用重新对齐。
  2. **过渡段最短 4 秒**（官方下限），所以一个接缝吃掉前后各 2 秒；某一段
     让完不够 `MIN_KEEP` 秒时，这一端**不补**并记账，不硬凑。
  3. **不出音频**（`generate_audio=False`）：成片声音来自 TTS / 原片，
     模型生成的那条会被丢掉 —— 白花钱。
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

log = logging.getLogger("transition")

# 官方 `volc-api:588`：2.5 参考任务 duration ∈ [4,30]，2.0 系列 [4,15]
SEAM_SECONDS = 4.0
HALF = SEAM_SECONDS / 2.0
# 一段被让出 HALF 之后至少要剩这么多，否则这一端不补
MIN_KEEP = 0.5
_EPS = 0.02


def seam_prompt(desc: str = "") -> str:
    """接缝提示词。

    🩸 **骨架照抄官方示例**（`seedance-25-guide.md:1337`），只换槽位 ——
    「将【视频 1】和【视频 2】衔接起来，……，无缝自然地衔接转场到【视频 2】，
    整个场景也对应变化，同时不要改变上传的两个视频。」
    `desc` 留空时退化成同一句的裁剪版，不另写一套说法。
    """
    d = (desc or "").strip().rstrip("。，,.")
    if d:
        return (f"将@视频1和@视频2衔接起来，{d}，无缝自然地衔接转场到@视频2。"
                f"整个场景也对应变化，同时不要改变上传的两个视频。")
    return ("将@视频1和@视频2衔接起来，无缝自然地衔接转场到@视频2，"
            "同时不要改变上传的两个视频。")


# ---------------------------------------------------------------------------
# 时间轴：切分与接缝

def clip_dur(c: dict) -> float:
    return float(c["end"]) - float(c["start"])


def split_by_marks(clips: list[dict], marks) -> list[dict]:
    """把每个片段按时间轴上的切点（`marks`）切成更小的片段。

    源文件不变，只改 `start`/`end`；**总时长守恒**。
    `marks` 是时间轴上的秒数（镜头边界等），落在片段边界上或片段外的一律忽略。
    """
    ms = sorted({round(float(m), 6) for m in (marks or [])})
    out: list[dict] = []
    t = 0.0
    for c in clips:
        dur = clip_dur(c)
        if dur <= _EPS:
            continue
        cuts = [m for m in ms if t + _EPS < m < t + dur - _EPS]
        base_start = float(c["start"])
        prev = t
        for m in cuts + [t + dur]:
            seg = m - prev
            if seg <= _EPS:
                prev = m
                continue
            out.append({**c,
                        "source": str(c["source"]),
                        "start": round(base_start + (prev - t), 6),
                        "end": round(base_start + (m - t), 6),
                        # 冻帧只可能挂在原片段的末尾，切开以后不再成立
                        "freeze": 0.0})
            prev = m
        t += dur
    return out


def shot_marks(shots: list[dict] | None) -> list[float]:
    """原片镜头边界（时间轴秒数）。"""
    out: list[float] = []
    for s in shots or []:
        for k in ("start", "end"):
            try:
                out.append(round(float(s[k]), 6))
            except (KeyError, TypeError, ValueError):
                continue
    return out


# ---------------------------------------------------------------------------
# 单个接缝

def _seam_key(prev: Path, prev_end: float, nxt: Path,
              nxt_start: float, prompt: str, model: str) -> str:
    """接缝缓存键：素材指纹 + 取用位置 + 提示词 + 型号。

    素材用（文件名, 大小, mtime）而不是内容哈希 —— 和原来的 `generate.regen_shots`（已删）
    的参考图指纹同一口径：同一份素材没被改写就是同一段画面。
    """
    def sig(p: Path) -> str:
        p = Path(p)
        try:
            st = p.stat()
            return f"{p.name}:{st.st_size}:{st.st_mtime_ns}"
        except OSError:
            return f"{p.name}:0:0"

    raw = "|".join([sig(prev), f"{prev_end:.3f}", sig(nxt), f"{nxt_start:.3f}",
                    prompt, model, f"{SEAM_SECONDS:.3f}"])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _cache_hit(cache_dir: Path | None, key: str, dest: Path) -> bool:
    if cache_dir is None:
        return False
    p = Path(cache_dir) / f"{key}.mp4"
    try:
        if p.exists() and p.stat().st_size > 1024:
            dest.parent.mkdir(parents=True, exist_ok=True)
            import shutil

            shutil.copyfile(p, dest)
            return True
    except OSError as e:
        log.warning("读接缝缓存失败（按未命中继续）：%s", e)
    return False


def _cache_put(cache_dir: Path | None, key: str, src: Path) -> None:
    if cache_dir is None:
        return
    try:
        import os
        import shutil

        p = Path(cache_dir) / f"{key}.mp4"
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(f".{p.name}.{os.getpid()}.tmp")
        shutil.copyfile(src, tmp)
        os.replace(tmp, p)
    except OSError as e:
        log.warning("写接缝缓存失败（不影响这次出片）：%s", e)


def _fit_duration(src: Path, dest: Path, seconds: float) -> Path:
    """把过渡段卡成正好 `seconds` 秒。

    模型给的是整数秒 duration，实际帧数不一定严丝合缝：
      长了 → 裁掉（看不出来）
      短了 → 冻最后几帧补齐（过渡段本身就短，冻几帧比时间轴错位强得多）
    """
    import subprocess

    from app.services.media import ffmpeg_path
    from app.services.scene import probe

    ff = ffmpeg_path()
    if not ff:
        raise RuntimeError("找不到 ffmpeg，请设置 VT_FFMPEG")
    have = float((probe(src) or {}).get("duration") or 0)
    dest.parent.mkdir(parents=True, exist_ok=True)
    vf = (f"tpad=stop_mode=clone:stop_duration={max(0.0, seconds - have) + 0.2:.3f},"
          f"trim=duration={seconds:.3f},setpts=PTS-STARTPTS")
    # 🩸 不写 `-frames:v N`：那要把秒数乘一个假定帧率，源是 25/60fps 时会截错。
    # `trim=duration` 按 PTS 裁，什么帧率都对。
    cmd = [ff, "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
           "-vf", vf, "-c:v", "libx264", "-crf", "20", "-preset", "veryfast",
           "-pix_fmt", "yuv420p", "-an", str(dest)]
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          errors="ignore", timeout=600)
    if proc.returncode != 0 or not dest.exists():
        raise RuntimeError(f"过渡段定长失败：{(proc.stderr or '')[-300:]}")
    return dest


def replace_seam_in_file(src: Path, *, seam_at: float, seam: Path,
                         dest: Path) -> Path:
    """把**已经拼好的一条片子**在 `seam_at` 处的画面换成过渡段。

    给延长链路用：`extend.stitch` 已经把两段连成一条（带音轨），这里只替换
    接缝前后各 `HALF` 秒的**画面**，音轨整条沿用原文件 —— 总时长不变，
    声音不需要重新对齐。
    """
    import subprocess

    from app.services.media import ffmpeg_path
    from app.services.scene import probe

    ff = ffmpeg_path()
    if not ff:
        raise RuntimeError("找不到 ffmpeg，请设置 VT_FFMPEG")
    info = probe(src) or {}
    total = float(info.get("duration") or 0)
    if total <= 0:
        raise ValueError("无法读取待替换视频的时长")
    a = max(0.0, float(seam_at) - HALF)
    b = min(total, float(seam_at) + HALF)
    if a <= 0.0 or b >= total - 0.05:
        raise ValueError("接缝太靠近片头/片尾，替换会吃掉整段")

    fc = (
        f"[0:v]trim=start=0:end={a:.6f},setpts=PTS-STARTPTS[v0];"
        f"[1:v]setpts=PTS-STARTPTS[v1];"
        f"[0:v]trim=start={b:.6f}:end={total:.6f},setpts=PTS-STARTPTS[v2];"
        f"[v0][v1][v2]concat=n=3:v=1:a=0[v]"
    )
    cmd = [ff, "-hide_banner", "-loglevel", "error", "-y",
           "-i", str(src), "-i", str(seam),
           "-filter_complex", fc, "-map", "[v]"]
    if info.get("has_audio"):
        cmd += ["-map", "0:a", "-c:a", "copy"]
    cmd += ["-c:v", "libx264", "-crf", "20", "-preset", "veryfast",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dest)]
    dest.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          errors="ignore", timeout=1800)
    if proc.returncode != 0 or not dest.exists():
        raise RuntimeError(f"接缝画面替换失败：{(proc.stderr or '')[-300:]}")
    return dest


def make_seam(prev: Path, prev_end: float, nxt: Path, nxt_start: float,
              *, workdir: Path, model: str = "", desc: str = "",
              resolution: str = "720p",
              cache_dir: Path | None = None) -> Path:
    """给一个接缝生成过渡段（长度 = `SEAM_SECONDS`）。"""
    from app.services import ark, oss, scene

    prompt = seam_prompt(desc)
    key = _seam_key(Path(prev), prev_end, Path(nxt), nxt_start, prompt, model)
    work = Path(workdir) / "seam" / key
    work.mkdir(parents=True, exist_ok=True)
    dest = work / f"seam_{key}.mp4"

    if _cache_hit(cache_dir, key, dest):
        log.info("接缝 %s 命中缓存，不重复扣费", key)
        return dest

    # 接缝两侧各切 HALF 秒送去做参考。**必须 exact=True**：`-c copy` 的起点
    # 若不在关键帧会带出负 PTS 前置包，平台校验直接拒（见 `scene.cut_clip`）。
    a = scene.cut_clip(Path(prev), max(0.0, prev_end - HALF), prev_end,
                       work / "a.mp4", exact=True, audio=False)
    b = scene.cut_clip(Path(nxt), nxt_start, nxt_start + HALF,
                       work / "b.mp4", exact=True, audio=False)

    # 参考视频只收公网 URL（base64 不收）
    ua = oss.upload(a, prefix="seam")
    ub = oss.upload(b, prefix="seam")

    raw = ark.transition_video(
        prompt, video_a=ua, video_b=ub, out=work / "raw.mp4",
        model=model, resolution=resolution,
        duration=int(round(SEAM_SECONDS)),
    )
    out = _fit_duration(raw, dest, SEAM_SECONDS)
    _cache_put(cache_dir, key, out)
    log.info("接缝 %s 过渡段就绪（%s + %s）", key, Path(prev).name, Path(nxt).name)
    return out


# ---------------------------------------------------------------------------
# 整条时间轴

def patch(clips: list[dict], *, workdir: Path, model: str = "",
          desc: str = "", resolution: str = "720p",
          max_seams: int = 20, cache_dir: Path | None = None,
          progress=None) -> tuple[list[dict], dict]:
    """给相邻片段之间的每个接缝生成过渡段。

    返回 (新 clips, 记账)。新 clips 的**总时长与原 clips 相同**：
    前段 `end -= HALF`、后段 `start += HALF`、中间插一段 `SEAM_SECONDS`。

    🩸 某一段让出 HALF 后剩不到 `MIN_KEEP` 时，这一端**不补**并写进
    `skipped` —— 宁可这处还是硬接，也不许把一段压成 0.2 秒的闪帧。
    """
    items = list(clips or [])
    total_seams = max(0, len(items) - 1)
    info: dict = {"total": total_seams, "patched": 0, "skipped": [],
                  "seconds": SEAM_SECONDS, "limit": int(max_seams)}
    if total_seams == 0:
        return items, info

    out: list[dict] = []
    for i, c in enumerate(items):
        cur = dict(c)
        out.append(cur)
        if i + 1 >= len(items):
            break
        nxt = items[i + 1]
        seam_t = round(sum(clip_dur(x) for x in items[:i + 1]), 6)

        # 已经补够上限：剩下的接缝原样留着（记账，不静默吞掉）
        if info["patched"] >= int(max_seams):
            info["skipped"].append({"at": seam_t, "why": "超过上限"})
            continue
        if clip_dur(cur) - HALF < MIN_KEEP:
            info["skipped"].append({"at": seam_t, "why": "前段太短"})
            continue
        if clip_dur(nxt) - HALF < MIN_KEEP:
            info["skipped"].append({"at": seam_t, "why": "后段太短"})
            continue

        n = info["patched"] + 1
        if callable(progress):
            # 进度回调只用来刷状态，它自己出错不该把出片带崩（与 `_p` 同口径）
            try:
                progress(f"补接缝 {n}/{total_seams}", 80)
            except Exception:  # noqa: BLE001
                pass
        try:
            path = make_seam(
                Path(cur["source"]), float(cur["end"]),
                Path(nxt["source"]), float(nxt["start"]),
                workdir=workdir, model=model, desc=desc,
                resolution=resolution, cache_dir=cache_dir,
            )
        except Exception as e:  # noqa: BLE001
            # 🩸 单处失败不拖垮整片：这处退回硬接，把原因写进记账。
            # 该接缝的缓存没写成，重跑时会再试一次（不会重复付费的部分已缓存）。
            log.warning("接缝 %.2fs 补全失败（这一处保持硬接）：%s", seam_t, e)
            info["skipped"].append({"at": seam_t, "why": f"生成失败：{e}"})
            continue

        cur["end"] = round(float(cur["end"]) - HALF, 6)
        out.append({
            "source": str(Path(path).resolve()),
            "start": 0.0,
            "end": round(SEAM_SECONDS, 6),
            "freeze": 0.0,
            "label": f"seam{n:02d}",
            "kind": "seam",
        })
        nxt2 = dict(nxt)
        nxt2["start"] = round(float(nxt["start"]) + HALF, 6)
        nxt2["freeze"] = 0.0
        items[i + 1] = nxt2
        info["patched"] += 1

    return out, info
