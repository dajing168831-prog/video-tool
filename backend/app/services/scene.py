"""镜头切分与画面证据（纯 ffmpeg，不引入额外依赖）。

为什么不用 PySceneDetect：本项目已经强依赖 ffmpeg，ffmpeg 的 scene 滤镜
能在同一次解码里给出切点，省掉 opencv/torch 一整套依赖。
判据见 docs/CLONE-VERIFY.md：与人工标注的切点对比（漏检 / 误检）。

产出的是"证据"，不是结论 —— 上层 recipe 才负责解释它。
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.media import ffmpeg_path, ffprobe_path

log = logging.getLogger(__name__)


@dataclass
class Shot:
    index: int
    start: float
    end: float
    # 逐镜运动量（相邻帧差均值）。由 analyze 阶段回填，供逐镜分诊用
    motion: float = 0.0
    keyframe: str = ""

    @property
    def duration(self) -> float:
        return round(self.end - self.start, 3)


def _run(cmd: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, capture_output=True, text=True, errors="ignore", timeout=timeout
    )


def probe(path: Path) -> dict:
    """读容器与流信息。优先 ffprobe(JSON)，没有就退回 ffmpeg -i 解析。"""
    exe = ffprobe_path()
    if exe:
        proc = _run([
            exe, "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", str(path),
        ], timeout=60)
        if proc.returncode == 0 and proc.stdout.strip():
            try:
                data = json.loads(proc.stdout)
                return _parse_probe_json(data)
            except Exception as e:  # noqa: BLE001
                log.warning("ffprobe JSON 解析失败: %s", e)

    # 退回：ffmpeg -i 的 stderr
    ff = ffmpeg_path()
    if not ff:
        raise RuntimeError("找不到 ffmpeg，请设置 VT_FFMPEG")
    proc = _run([ff, "-hide_banner", "-i", str(path)], timeout=60)
    return _parse_ffmpeg_stderr(proc.stderr or "")


def _parse_probe_json(data: dict) -> dict:
    fmt = data.get("format") or {}
    video = next(
        (s for s in data.get("streams", []) if s.get("codec_type") == "video"), {}
    )
    has_audio = any(s.get("codec_type") == "audio" for s in data.get("streams", []))
    fps = 0.0
    rate = video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1"
    try:
        num, den = rate.split("/")
        fps = round(float(num) / float(den), 3) if float(den) else 0.0
    except Exception:  # noqa: BLE001
        fps = 0.0
    return {
        "duration": round(float(fmt.get("duration") or 0), 3),
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "fps": fps,
        "has_audio": has_audio,
        "size_bytes": int(fmt.get("size") or 0),
        "codec": video.get("codec_name") or "",
        # 🩸 图片上传要用：官方 `sd25-guide:677` 的翻车案例是「非常规、非对称的
        # 色度采样（Y 2x2 / Cb 1x1 / Cr 2x1）」的 JPG —— ffprobe 能读出宽高、
        # 我们放行，模型侧却解码失败。**上传时看得见采样格式，才挡得住**。
        "pix_fmt": video.get("pix_fmt") or "",
    }


def _parse_ffmpeg_stderr(text: str) -> dict:
    import re

    dur_m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    duration = 0.0
    if dur_m:
        duration = (
            int(dur_m.group(1)) * 3600
            + int(dur_m.group(2)) * 60
            + float(dur_m.group(3))
        )
    w = re.search(r"(\d{2,5})x(\d{2,5})", text)
    # 回退路径也要能拿到采样格式：`Video: mjpeg, yuvj420p(pc, bt470bg/...)`
    pf = re.search(r"Video:\s*[^,\n]+,\s*([a-z][a-z0-9_]*)\s*[\(\s,]", text)
    return {
        "duration": round(duration, 3),
        "width": int(w.group(1)) if w else 0,
        "height": int(w.group(2)) if w else 0,
        "fps": 0.0,
        "has_audio": "Audio:" in text,
        "size_bytes": 0,
        "codec": "",
        "pix_fmt": pf.group(1) if pf else "",
    }


# 软切的判据（见 `_hist_cuts`）：
#   隔 k 帧（k=2 ≈ 0.07s）的 HSV 直方图相关性掉到 0.90 以下，且平均亮度变化 > 15
# 实测标定（2026-10-22，任务 a47631b0 的 28.03s 原片）：
#   11.70 硬切 corr=0.47 diff=64｜24.43 软切 corr=0.87 diff=41
#   9–11s 频闪（同一场景反复闪白）corr 最低 0.98 —— 亮度大跳但色相分布不变，
#   所以**相关性**才是区分"换场景"和"闪一下"的那把尺
HIST_K = 2
HIST_CORR = 0.90
HIST_DIFF = 15.0
HIST_WIDTH = 120
# 闪光帧（整帧被闪白）：亮度明显偏离前后邻帧。这类帧两边都不许拿来比 ——
# 闪光会让直方图瞬间失真，只看相关性的话"闪一下"和"换场"长得一样。
# 判据 = 该帧平均亮度偏离 ±RAD 帧中位数超过 GATE（实测合成 1 帧/2 帧闪白都能滤掉）
HIST_FLASH_RAD = 4
HIST_FLASH_GATE = 20.0


def _frame_times(path: Path) -> list[float]:
    """每一帧的**真实时间戳**（秒，按解码顺序）。读不到返回空列表。

    🩸 2026-10-26 的失败根因：`_hist_cuts` 以前拿 `帧序号 / avg_frame_rate`
    当时间。上传的片子常带着**和实际帧序列不符的 avg_frame_rate** ——
    实测一单：`avg=21660/907=23.881`，实际 60fps / 15.117s / 907 帧，
    于是最后一帧的"时间"算成 37.94s，软切点被报到 23.994s（真实约 9.55s）。
    越界切点进了镜头表 → 出片按 19.89s 抽帧 → 片长只有 15.12s，
    **一帧都抽不到** → 整单失败（10-25 22:54 / 10-26 02:10 各一次）。
    PTS 是流里自带的，不依赖容器报的 fps。
    """
    exe = ffprobe_path()
    if not exe:
        return []
    proc = _run([exe, "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "frame=pts_time", "-of", "csv=p=0",
                 str(path)], timeout=180)
    out: list[float] = []
    for line in (proc.stdout or "").splitlines():
        line = line.strip().rstrip(",")
        if not line or line == "N/A":
            continue
        try:
            out.append(float(line))
        except ValueError:
            continue
    return out


def _hist_cuts(path: Path, *, k: int = HIST_K, corr_thr: float = HIST_CORR,
               diff_thr: float = HIST_DIFF, width: int = HIST_WIDTH) -> list[float]:
    """找 ffmpeg 的 scene 分数抓不到的**软切**（淡入淡出、同色系换场）。

    🩸 为什么要这条线（2026-10-22 实测 a47631b0）：ffmpeg 的 scene 分数在
    11.70 的硬切上是 0.473，但在 24.43 的软切上只有 0.120 —— 比同一段里
    9–11s 频闪的 0.174 还低。**调阈值救不了**，只能换一把尺。

    ffmpeg 的 scene 分数看的是相邻帧的像素变化，频闪和换景在它眼里一样大；
    色相/饱和度直方图则不同：频闪只是亮度跳，颜色分布没变（实测 corr ≥ 0.98），
    换场景连调色板一起换（24.43 corr=0.87）。

    k 帧延迟而不是相邻帧：软切是一两帧的过渡，拆开看每一步都不大，
    隔 k 帧比总变化才看得出来；而频闪隔 k 帧又回到同一画面，反而更稳。
    闪光帧本身（亮度偏离邻帧中位数 > 20）两边都不参与比较 —— 否则一次
    整帧闪白就会被当成换场（实测：2 帧闪白在 k=2 时正好横跨两个端点）。

    纯 ffmpeg 解码 + numpy 算直方图（逐帧流式读，不把整片塞进内存）。
    依赖拿不到时返回空列表 —— 这条线只是补充，不能因为环境缺库把分析搞挂。
    片头 RAD 帧内（≈0.13s）不下判断：闪光判据需要前后各 RAD 帧的上下文。
    """
    try:
        import numpy as np
    except Exception as e:  # noqa: BLE001
        log.warning("没有 numpy，跳过软切探测：%s", e)
        return []
    ff = ffmpeg_path()
    if not ff:
        return []
    try:
        info = probe(path)
    except Exception as e:  # noqa: BLE001
        log.warning("软切探测读不到视频信息：%s", e)
        return []
    fps = float(info.get("fps") or 0.0)
    total = float(info.get("duration") or 0.0)
    src_w, src_h = int(info.get("width") or 0), int(info.get("height") or 0)
    if fps <= 0 or total <= 0 or src_w <= 0 or src_h <= 0:
        return []
    # 每帧的真实时间戳（容器 average fps 不可信时唯一的正确来源，见 `_frame_times`）
    times = _frame_times(path)
    w = width
    h = max(2, round(src_h * w / src_w))
    h -= h % 2
    cmd = [
        ff, "-hide_banner", "-loglevel", "error", "-i", str(path), "-an",
        # 🩸 `-fps_mode passthrough` 必须加（2026-10-26）：rawvideo 输出默认按
        #   输出的 r_frame_rate 做 CFR，实测一个 361 帧 / 23.88fps 的片子被
        #   **补成 907 帧（60fps）**——帧序号和 PTS 表对不上，时间全错位。
        #   普通 CFR 片子这条是空操作（输入输出帧率相同），不影响原有判据。
        "-fps_mode", "passthrough",
        "-vf", f"scale={w}:{h}:flags=area",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ]
    frame_bytes = w * h * 3
    # 要判"第 i-4 帧"这一对，得看到它之后 4 帧 → 缓冲里留 2*RAD+k+1 帧，
    # 内存和片长无关（120 宽的小帧，13 帧 ≈ 1MB）
    span = 2 * HIST_FLASH_RAD + k + 1
    buf: list[tuple[float, Any, float, Any, float]] = []
    hits: list[tuple[float, float, float]] = []
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        i = 0
        while True:
            raw = proc.stdout.read(frame_bytes)
            if not raw or len(raw) < frame_bytes:
                break
            fr = np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 3).astype(np.float32)
            r, g, b = fr[..., 0], fr[..., 1], fr[..., 2]
            mx = fr.max(axis=2)
            mn = fr.min(axis=2)
            d = mx - mn
            hue = np.zeros_like(mx)
            m = (d > 0) & (mx == r)
            hue[m] = ((g[m] - b[m]) / d[m]) % 6
            m = (d > 0) & (mx == g)
            hue[m] = ((b[m] - r[m]) / d[m]) + 2
            m = (d > 0) & (mx == b)
            hue[m] = ((r[m] - g[m]) / d[m]) + 4
            idx = ((hue * 30.0) / 180 * 32).astype(np.int32).clip(0, 31) * 32 \
                + (np.where(mx > 0, d / np.maximum(mx, 1) * 255, 0) / 256 * 32) \
                .astype(np.int32).clip(0, 31)
            hist = np.bincount(idx.reshape(-1), minlength=1024).astype(np.float32)
            hist /= float(hist.sum()) or 1.0
            hist -= hist.mean()
            gray = fr.mean(axis=2)
            # 🩸 时间只认 PTS；读不到才退回 `帧序号 / fps`（再夹进片长，绝不越界）
            t_i = times[i] if i < len(times) else i / fps
            buf.append((min(t_i, total), hist, float(np.sqrt((hist ** 2).sum())),
                        gray.astype(np.uint8), float(gray.mean())))
            if len(buf) > span:
                buf.pop(0)
            if len(buf) < span:
                i += 1
                continue
            # 被比较的一对：buf[-1-RAD] 和它前面 k 帧
            x, xk = span - 1 - HIST_FLASH_RAD, span - 1 - HIST_FLASH_RAD - k

            def flash(p: int) -> bool:
                """这一帧是不是"闪一下又回去"：亮度离开前后两侧，而两侧彼此一致。

                🩸 不能只跟"全窗口中位数"比：叠化/换场的那几帧亮度本来就在移动，
                拿中位数一比就全被当成闪光，软切反而检测不到了（实测把一个
                亮度差 40 的叠化样本整段滤掉）。前后两侧分别取中位数，
                再要求"两侧彼此接近"，才能把"闪一下又回来"和"换过去就不回来了"分开。
                """
                lo, hi = max(0, p - HIST_FLASH_RAD), min(span, p + HIST_FLASH_RAD)
                before = [buf[j][4] for j in range(lo, p)]
                after = [buf[j][4] for j in range(p + 1, hi + 1)]
                if not before or not after:
                    return False
                b, a = float(np.median(before)), float(np.median(after))
                return (abs(buf[p][4] - b) > HIST_FLASH_GATE
                        and abs(buf[p][4] - a) > HIST_FLASH_GATE
                        and abs(b - a) <= HIST_FLASH_GATE / 2)

            if not flash(x) and not flash(xk):
                den = buf[x][2] * buf[xk][2]
                if den > 0:
                    corr = float((buf[x][1] * buf[xk][1]).sum() / den)
                    ga, gb = buf[x][3].astype(np.int16), buf[xk][3].astype(np.int16)
                    diff = float(np.abs(ga - gb).mean())
                    if corr < corr_thr and diff > diff_thr:
                        hits.append((buf[x][0], corr, diff))
            i += 1
    finally:
        try:
            proc.stdout.close()
        except Exception:  # noqa: BLE001
            pass
        proc.kill()
        proc.wait()
    # 同一个过渡会连着好几帧都低 → 合并成一刀，留变化最大的那帧
    merged: list[list[float]] = []
    for t, c, d in hits:
        if merged and t - merged[-1][0] < 0.4:
            if d > merged[-1][2]:
                merged[-1] = [t, c, d]
            continue
        merged.append([t, c, d])
    return [round(t, 3) for t, _, _ in merged]


def detect_shots(path: Path, threshold: float = 0.30,
                 min_shot: float = 0.5) -> list[Shot]:
    """找切点，返回闭合的镜头区间。

    两把尺合起来用：
      - ffmpeg 的 scene 分数（阈值 0.3）：抓硬切，一直是主力
      - 色相直方图（见 `_hist_cuts`）：补软切 —— 🩸 2026-10-22 实测漏掉的
        24.43 软切就是这条线补回来的：那一段横跨换场，模型在里面自己编了
        4 个不存在的切点（15.83/18.37/21.37/25.37），人物和背景全飘

    threshold 越低越敏感（0.3 是短视频的常用起点）；
    min_shot 之下的小片段会被合并，避免花字闪动被当成切镜。
    """
    ff = ffmpeg_path()
    if not ff:
        raise RuntimeError("找不到 ffmpeg，请设置 VT_FFMPEG")

    info = probe(path)
    total = float(info.get("duration") or 0)
    if total <= 0:
        raise RuntimeError("读不到视频时长")

    proc = _run([
        ff, "-hide_banner", "-nostats", "-i", str(path), "-an",
        "-filter:v", f"select='gt(scene,{threshold})',metadata=print:file=-",
        "-f", "null", "-",
    ], timeout=600)

    cuts: list[float] = []
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("frame:") and "pts_time:" in line:
            try:
                t = float(line.split("pts_time:")[1].split()[0])
            except Exception:  # noqa: BLE001
                continue
            if 0.05 < t < total - 0.05:
                cuts.append(round(t, 3))
    proc_err = (proc.stderr or "").strip()
    if proc.returncode != 0 and not cuts:
        log.warning("切分失败: %s", proc_err[-300:])

    # 软切补漏（ffmpeg 的 scene 分数对"同色系换场"几乎无感，见 `_hist_cuts`）；
    # 两条线的切点直接取并集，靠下面的 min_shot 合并同一刀
    # 🩸 软切同样要过"在片长内"这道闸：硬切那侧一直有 `0.05 < t < total - 0.05`，
    #   软切以前直接并进去。越界一个，镜头表就会出现 `start > end` 的倒挂条目，
    #   出片按那个时间去抽帧必然抽不到（2026-10-25 22:54 / 10-26 02:10 两单）。
    soft = [t for t in _hist_cuts(path) if 0.05 < t < total - 0.05]
    if soft:
        log.info("直方图补到软切：%s", [round(t, 2) for t in soft])

    # 去重 + 合并过短片段
    cuts = sorted(set(cuts) | set(soft))
    bounds = [0.0]
    for t in cuts:
        if t - bounds[-1] >= min_shot:
            bounds.append(t)
    if total - bounds[-1] < min_shot and len(bounds) > 1:
        bounds.pop()
    bounds.append(total)

    shots = [
        Shot(index=i, start=bounds[i], end=bounds[i + 1])
        for i in range(len(bounds) - 1)
    ]
    if not shots:
        shots = [Shot(index=0, start=0.0, end=total)]
    return shots


def extract_frame(path: Path, at: float, dest: Path, width: int = 480) -> Path:
    """抽某一时刻的一帧，缩到 width 宽（给模型看用，不必原分辨率）。"""
    ff = ffmpeg_path()
    if not ff:
        raise RuntimeError("找不到 ffmpeg，请设置 VT_FFMPEG")
    dest.parent.mkdir(parents=True, exist_ok=True)
    proc = _run([
        ff, "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{max(0.0, at):.3f}", "-i", str(path),
        "-frames:v", "1", "-vf", f"scale={width}:-2",
        str(dest),
    ], timeout=60)
    if proc.returncode != 0 or not dest.exists():
        raise RuntimeError(f"抽帧失败 @{at}s: {(proc.stderr or '')[:200]}")
    return dest


def cut_clip(path: Path, start: float, end: float, dest: Path,
             *, audio: bool = True, exact: bool = False,
             frames: int = 0) -> Path:
    """切一段出来。

    `exact=False`（默认）= `-c copy`，无损、快。**只有当 start 落在关键帧上
    （或 start=0）时时间轴才是干净的**，所以它只适合"自己还要再编码"的场合
    （截母片、测试）；正文见下方 `exact=True` 的说明。

    `exact=True` = 重编码。🩸 凡是**要送去平台校验**的片段必须走这条：
    `-c copy` 的起点若不在关键帧，ffmpeg 会从**前一个关键帧**开始复制，把中间
    那几秒塞成"discard + 负 PTS"的包 —— 文件头写的时长是 5.5s，包里却有 9s 的帧
    （实测：270 包 / 105 个负 PTS）。ffmpeg 自己会跳过这些包，但平台校验不过，
    火山异步回 `InvalidParameter: Bad Request`，而"从 0 起切"的第 1 段就正常。
    重编码后：首包 PTS=0、包数 = 时长 × 帧率，干净。

    audio=False 连音轨一起丢掉：送去做参考的片段不需要声音（成片音轨取自原片），
    少一条音轨就少一个审核面。

    `frames>0` = 把输出**卡成正好这么多帧**（必须配 `exact=True`）。
    🩸 官方《Seedance 2.5 指南》`:698-703`「编辑前后时长不一致」：
    编辑任务的输出比原视频短约 0.33 秒；解法是把输入视频的**帧数调成 8n+1**，
    输出时长就与输入一致。所以调用方按 `8n+1` 算好帧数传进来。
    `-to` 松一格（+0.2s）保证源帧够数，再由 `-frames:v` 截死 —— 只靠 `-to`
    切不出精确帧数（关键帧/时长取整都会差几帧）。
    """
    ff = ffmpeg_path()
    if not ff:
        raise RuntimeError("找不到 ffmpeg，请设置 VT_FFMPEG")
    dest.parent.mkdir(parents=True, exist_ok=True)
    end_to = (end + 0.2) if frames else end
    head = [ff, "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{start:.3f}", "-to", f"{end_to:.3f}", "-i", str(path)]
    if exact:
        cmd = head + ["-c:v", "libx264", "-crf", "20", "-preset", "veryfast",
                      "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k"]
        timeout = 300
    else:
        cmd = head + ["-c", "copy"]
        timeout = 120
    if frames:
        if not exact:
            raise ValueError("frames 只能配 exact=True（-c copy 切不出精确帧数）")
        cmd += ["-frames:v", str(int(frames))]
    if not audio:
        cmd.append("-an")
    proc = _run(cmd + [str(dest)], timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"切片失败: {(proc.stderr or '')[:200]}")
    return dest


def cut_audio(path: Path, start: float, end: float, dest: Path,
              *, sample_rate: int = 44100) -> Path:
    """截一段音轨成 16bit 单声道 wav —— 给"口型参考"用。

    和 `cut_clip` 的差别：这里必须**重编码**。`-c copy` 切 mp4 里的 AAC 会在
    关键帧外产生几百毫秒的偏移和补静音，拿去给视频模型对口型就是错的起点。

    为什么单声道 + 16bit：两家（MiniMax / 火山）的参考音频都只要求 wav/mp3，
    单声道足够对口型，体积还小一半 —— 上传有 15MB 上限。
    """
    ff = ffmpeg_path()
    if not ff:
        raise RuntimeError("找不到 ffmpeg，请设置 VT_FFMPEG")
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ff, "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{max(0.0, start):.3f}", "-to", f"{max(0.0, end):.3f}",
        "-i", str(path),
        "-vn", "-ac", "1", "-ar", str(sample_rate), "-c:a", "pcm_s16le",
        str(dest),
    ]
    proc = _run(cmd, timeout=120)
    if proc.returncode != 0 or not dest.exists():
        raise RuntimeError(f"切音频失败: {(proc.stderr or '')[:200]}")
    return dest


def motion(path: Path, start: float, end: float, *, width: int = 160) -> float:
    """这一段画面有多"能动"：相邻帧差的平均亮度（0–255）。

    纯 ffmpeg 算，不用 GPU / numpy：
      scale 到小图（快且不受分辨率影响）→ tblend 求相邻帧差 → signalstats 取 YAVG 均值

    用途是逐镜分诊：值低＝静态（口播特写、产品静物），一张静帧就够；
    值高＝动作/运镜是这一镜的重点，必须把原片片段交给视频模型，否则动作就丢了。
    """
    ff = ffmpeg_path()
    if not ff:
        return 0.0
    dur = max(0.2, float(end) - float(start))
    cmd = [
        ff, "-hide_banner", "-loglevel", "error",
        "-ss", f"{float(start):.3f}", "-t", f"{dur:.3f}", "-i", str(path),
        "-vf", (f"scale={width}:-2,tblend=all_mode=difference,"
                f"signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-"),
        "-an", "-f", "null", "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              errors="ignore", timeout=180)
    except Exception as e:  # noqa: BLE001
        log.warning("运动量计算失败 %s-%s: %s", start, end, e)
        return 0.0
    vals = [float(m.group(1)) for m in re.finditer(r"YAVG=([\d.]+)", proc.stdout or "")]
    return round(sum(vals) / len(vals), 2) if vals else 0.0
