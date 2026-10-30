"""成片质量门：花完钱之后、交给你之前，先用本地 ffmpeg 把片子过一遍。

为什么要有这个：出片是付费的，肉眼发现问题等于又花一次钱。
参考项目的做法（青山后期工艺 §FINAL-FRAME-CADENCE-FREEZE、ArcReel 的
normalize+concat 合同）都是**机器先过门**，不靠人看。

这里只做三件最值钱的事，全部本地、零成本：
  1. 定格 / 重复帧 —— tpad 补时长、素材不够、模型给短了，都会在这里现形
  2. 音画时长差 —— 声音比画面长（或反过来）说明音轨没对齐
  3. 总时长偏离 —— 和原片对不上说明时间轴拼错了

输出直接进 task.json 的 renders[].qc，结果页可以照它提示。
"""
from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

from app.services.media import ffmpeg_path, ffprobe_path

log = logging.getLogger(__name__)

# 单次定格超过这个长度就当缺陷（一秒在成片里已经很明显）
_FREEZE_HARD = 4.0       # 秒：单段 ≥ 这个 → 缺陷
_FREEZE_SOFT = 1.0       # 秒：单段 ≥ 这个 → 记录
_FREEZE_TOTAL = 0.20     # 全片定格占比 ≥ 这个 → 缺陷
_DUR_TOL = 0.30          # 秒：没有帧/采样合同时，总时长对原片的粗容差


def _probe(path: Path) -> dict:
    """一次拿到时长/尺寸/帧率/有无音轨/音轨时长。"""
    fp = ffprobe_path()
    if not fp:
        raise RuntimeError("找不到 ffprobe，请设置 VT_FFMPEG")
    p = subprocess.run(
        [fp, "-v", "error", "-show_entries",
         "stream=codec_type,width,height,avg_frame_rate,duration,nb_frames"
         ",duration_ts,time_base:format=duration",
         "-of", "default=nw=1", str(path)],
        capture_output=True, text=True, errors="ignore", timeout=120,
    )
    out = {"duration": 0.0, "width": 0, "height": 0, "fps": 0.0,
           "frames": 0, "has_video": False, "has_audio": False,
           "audio_duration": 0.0, "audio_samples": 0,
           "audio_ts": 0, "audio_tb": (1.0, 48000.0)}
    kind = ""
    for line in p.stdout.splitlines():
        if line.startswith("codec_type="):
            kind = line.split("=", 1)[1]
            out["has_video"] |= kind == "video"
            out["has_audio"] |= kind == "audio"
        elif line.startswith("width="):
            out["width"] = int(line.split("=", 1)[1] or 0)
        elif line.startswith("height="):
            out["height"] = int(line.split("=", 1)[1] or 0)
        elif line.startswith("avg_frame_rate=") and kind == "video":
            # 🩸 音频流也会打 avg_frame_rate=0/0，不加 kind 判断会把视频的帧率冲成 0
            num, _, den = line.split("=", 1)[1].partition("/")
            try:
                d = float(den or 1)
                out["fps"] = round(float(num) / d, 3) if d else 0.0
            except ValueError:
                pass
        elif line.startswith("nb_frames=") and kind == "video":
            # 帧数对不上 = 拼接/收口没按合同走；读不到（N/A）就不硬判
            try:
                out["frames"] = max(0, int(line.split("=", 1)[1]))
            except ValueError:
                pass
        elif line.startswith("duration="):
            try:
                v = float(line.split("=", 1)[1])
            except ValueError:
                continue
            if kind == "audio":
                out["audio_duration"] = max(out["audio_duration"], v)
            else:
                out["duration"] = max(out["duration"], v)
        elif line.startswith("duration_ts=") and kind == "audio":
            # 采样数才是音频的真实长度：duration 是浮点秒，duration_ts 是整数采样。
            # 48kHz 的 mp4 里 time_base=1/48000，duration_ts 就是采样数本身。
            try:
                out["audio_ts"] = int(line.split("=", 1)[1])
            except ValueError:
                pass
        elif line.startswith("time_base=") and kind == "audio":
            num, _, den = line.split("=", 1)[1].partition("/")
            try:
                out["audio_tb"] = (float(num), float(den or 1))
            except ValueError:
                pass
    if out["audio_ts"]:
        n, d = out["audio_tb"]
        out["audio_samples"] = int(round(out["audio_ts"] * n / d * 48000))
    out.pop("audio_ts", None)
    out.pop("audio_tb", None)
    return out


def _freezes(path: Path) -> list[tuple[float, float]]:
    """返回 [(起点, 长度)] —— 完全静止的区间。"""
    ff = ffmpeg_path()
    if not ff:
        raise RuntimeError("找不到 ffmpeg，请设置 VT_FFMPEG")
    p = subprocess.run(
        [ff, "-hide_banner", "-nostats", "-i", str(path),
         "-vf", "freezedetect=n=0.001:d=0.5", "-map", "0:v", "-f", "null", "-"],
        capture_output=True, text=True, errors="ignore", timeout=900,
    )
    starts: list[float] = []
    durs: list[float] = []
    for line in (p.stderr or "").splitlines():
        m = re.search(r"freeze_start:\s*([0-9.]+)", line)
        if m:
            starts.append(float(m.group(1)))
            continue
        m = re.search(r"freeze_duration:\s*([0-9.]+)", line)
        if m:
            durs.append(float(m.group(1)))
    # 🩸 冻到片尾时 ffmpeg **只打 freeze_start，不打 duration**
    # （流结束时才补一行，很多时候直接没有）—— 按"总时长 - 起点"兜底，
    # 否则「后半段全冻」这种最严重的情况反而会被漏掉。
    total = _probe(path)["duration"]
    out = []
    for i, s in enumerate(starts):
        d = durs[i] if i < len(durs) else max(0.0, total - s)
        if d > 0:
            out.append((s, d))
    return out


def inspect(path: Path, *, expect_duration: float | None = None,
            expect_w: int = 0, expect_h: int = 0,
            expect_fps: float = 0.0, expect_frames: int = 0,
            expect_samples: int = 0) -> dict:
    """过一遍质量门。

    `expect_frames` / `expect_samples` 是「合同」：给了就用**等值**核对，
    不带容差。时长是我们自己用 ffmpeg 构造出来的（帧数 `-frames:v` 钉死、
    音轨按帧域算采样数），所以对不上就是真的错了 —— 参照 hypit
    `AudioProgramPlan` 的 `sampleFrames === clockFrameSampleBoundary(...)`。
    只有没有合同可比时（`expect_samples=0`）才退回 0.3 秒的粗判。

    返回 {"ok": bool, "issues": [...], "warnings": [...], "stats": {...}}
    —— `issues` 非空就是这条片子**不该直接发**。
    """
    path = Path(path)
    issues: list[str] = []
    warnings: list[str] = []
    stats: dict = {}

    if not path.exists():
        return {"ok": False, "issues": ["成片文件不存在"], "warnings": [],
                "stats": {}}

    info = _probe(path)
    stats.update({
        "duration": round(info["duration"], 3),
        "audio_duration": round(info["audio_duration"], 3),
        "width": info["width"], "height": info["height"], "fps": info["fps"],
        "frames": info["frames"],
    })

    if not info["has_video"]:
        issues.append("没有视频流")
        return {"ok": False, "issues": issues, "warnings": warnings, "stats": stats}

    if expect_duration and expect_duration > 0:
        delta = abs(info["duration"] - expect_duration)
        stats["duration_delta"] = round(delta, 3)
        if delta > _DUR_TOL:
            issues.append(
                f"总时长 {info['duration']:.2f}s 与预期 {expect_duration:.2f}s "
                f"差 {delta:.2f}s")

    # 帧数合同：duration 是容器时间基，帧数才是画面真的有多少张。
    # 容器读不到 nb_frames（N/A）时只提醒，不硬判。
    if expect_frames and expect_frames > 0:
        stats["expected_frames"] = int(expect_frames)
        if info["frames"] > 0:
            fd = info["frames"] - expect_frames
            stats["frame_delta"] = fd
            if fd != 0:
                issues.append(
                    f"帧数 {info['frames']} 与约定 {expect_frames} 差 {fd} 帧")
        else:
            warnings.append("容器没报帧数，帧数合同没核对")

    if expect_w and expect_h and (info["width"], info["height"]) != (expect_w, expect_h):
        warnings.append(
            f"尺寸 {info['width']}x{info['height']} 与预期 {expect_w}x{expect_h} 不一致")

    if info["has_audio"]:
        ad = abs(info["audio_duration"] - info["duration"])
        stats["av_delta"] = round(ad, 3)
        stats["audio_samples"] = info["audio_samples"]

    if expect_samples and expect_samples > 0:
        # 采样合同：音频长度是**算出来的**（帧数 ÷ 帧率 × 48000），不是估的。
        # 差一个采样都说明补/裁没落在帧边界上。
        stats["expected_samples"] = int(expect_samples)
        if info["audio_samples"] > 0:
            sd = info["audio_samples"] - expect_samples
            stats["sample_delta"] = sd
            if sd != 0:
                issues.append(
                    f"音频采样 {info['audio_samples']} 与约定 {expect_samples} "
                    f"差 {sd} 个采样（{sd / 48000:.4f}s）")
        else:
            warnings.append("容器没报音频采样数，采样合同没核对")
    elif info["has_audio"] and info["audio_duration"] > 0:
        # 没有采样合同时的粗判（老记录/外部文件）：只看音画是否差出 0.3 秒
        if stats.get("av_delta", 0.0) > _DUR_TOL:
            issues.append(
                f"音画时长不一致：画面 {info['duration']:.2f}s / "
                f"声音 {info['audio_duration']:.2f}s（差 {stats['av_delta']:.2f}s）")

    # 定格：显式的 tpad 痕迹、素材不够、模型给短了，全在这里现形
    try:
        fr = _freezes(path)
    except Exception as e:  # noqa: BLE001
        warnings.append(f"定格检测没跑成：{e}")
        fr = []
    stats["freezes"] = [[round(a, 2), round(b, 2)] for a, b in fr]
    total_frozen = sum(d for _, d in fr)
    stats["frozen_ratio"] = round(total_frozen / info["duration"], 3) if info["duration"] else 0.0
    for a, d in fr:
        if d >= _FREEZE_HARD:
            issues.append(f"{a:.2f}s 起画面定格 {d:.2f}s（超过 {_FREEZE_HARD:.0f}s）")
        elif d >= _FREEZE_SOFT:
            warnings.append(f"{a:.2f}s 起画面定格 {d:.2f}s")
    if info["duration"] and total_frozen / info["duration"] >= _FREEZE_TOTAL:
        issues.append(
            f"全片定格占比 {total_frozen / info['duration']:.0%}，超过 "
            f"{_FREEZE_TOTAL:.0%}")

    ok = not issues
    log.info("质检 %s：%s；%d 缺陷 / %d 提醒",
             path.name, "通过" if ok else "不通过", len(issues), len(warnings))
    return {"ok": ok, "issues": issues, "warnings": warnings, "stats": stats}
