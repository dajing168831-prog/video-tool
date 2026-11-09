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


# ---------------------------------------------------------------- 深度质检
#
# 出处：clipforge `src/lib/video-composer/qc.ts:1-368`（2026-11-06 逐行读过）。
# **阈值逐字抄自 `QC_PARAMS`（qc.ts:67-79），判级逐字抄自 `evaluateQc`（:154-300）**，
# 一个数都不许自己调 —— 主人 2026-11-06：「竞品都有了直接抄就好了，需要你新增什么东西嘛」。
#
# 与上面 `inspect()` 的关系：`inspect()` 是复刻线在用的老门（定格/时长合同），
# 这里是**另一套**，老函数一行没动 —— 商品短剧走这条。
#
# 🩸 一处**故意照抄的差异**：竞品把「定格」定成只提醒不拦（`qc.ts:286` 原话
#   "a legitimately static shot can trip this, so it never fails the video"）。
#   带货片里静止展示商品是合法的，所以照抄「不拦」。
#   老 `inspect()` 里定格 ≥4s 算缺陷 —— 那是复刻线口径，两者不冲突。

DEEP = {
    "black_min_sec": 0.4,          # qc.ts:68  blackdetect=d=
    "black_pix_th": 0.1,           # qc.ts:69  blackdetect=pix_th=
    "black_fail_longest": 2.0,     # qc.ts:208 longest >= 2 → fail
    "black_fail_share": 0.1,       # qc.ts:208 share > 0.1 → fail
    "silence_noise_db": -50,       # qc.ts:70  silencedetect=n=
    "silence_min_sec": 2.5,        # qc.ts:71  silencedetect=d=
    "silence_fail_longest": 5.0,   # qc.ts:238
    "silence_fail_share": 0.4,     # qc.ts:238
    "freeze_noise_db": -60,        # qc.ts:72
    "freeze_min_sec": 4.0,         # qc.ts:73
    "loudness_target": -14.0,      # qc.ts:75
    "loudness_warn_delta": 4.0,    # qc.ts:76
    "loudness_fail_below": -30.0,  # qc.ts:77
    "true_peak_warn_above": -0.5,  # qc.ts:78
}

_BLACK_RE = re.compile(
    r"black_start:\s*(-?[\d.]+)\s+black_end:\s*(-?[\d.]+)"
    r"\s+black_duration:\s*(-?[\d.]+)")
_SIL_START_RE = re.compile(r"silence_start:\s*(-?[\d.]+)")
_SIL_END_RE = re.compile(
    r"silence_end:\s*(-?[\d.]+)(?:\s*\|\s*silence_duration:\s*(-?[\d.]+))?")
_FRZ_START_RE = re.compile(r"freeze_start:\s*(-?[\d.]+)")
_FRZ_END_RE = re.compile(r"freeze_end:\s*(-?[\d.]+)")
_FRZ_DUR_RE = re.compile(r"freeze_duration:\s*(-?[\d.]+)")
_LOUD_RE = re.compile(r"\bI:\s*(-?[\d.]+)\s*LUFS")
_PEAK_RE = re.compile(r"\bPeak:\s*(-?[\d.]+)\s*dBFS")


def _ffmpeg_stderr(args: list[str], timeout: int = 900) -> str:
    ff = ffmpeg_path()
    if not ff:
        raise RuntimeError("找不到 ffmpeg，请设置 VT_FFMPEG")
    p = subprocess.run([ff, "-hide_banner", "-nostats", *args],
                       capture_output=True, text=True, errors="ignore",
                       timeout=timeout)
    return p.stderr or ""


def parse_black(stderr: str) -> list[dict]:
    return [{"start": round(float(a), 2), "end": round(float(b), 2),
             "duration": round(float(c), 2)}
            for a, b, c in _BLACK_RE.findall(stderr)]


def parse_silence(stderr: str, total: float = 0.0) -> list[dict]:
    """`silence_start: 3.2` … `silence_end: 6.8 | silence_duration: 3.6`。

    🩸 静音拖到片尾时 ffmpeg **只打 start 不打 end** —— 按「总时长 - 起点」兜底，
    否则「后半段全哑」这种最严重的情况反而漏掉（同 `_freezes` 的坑，qc.ts:117 也这么处理）。
    """
    out: list[dict] = []
    pending: float | None = None
    for line in stderr.splitlines():
        m = _SIL_START_RE.search(line)
        if m:
            pending = float(m.group(1))
            continue
        m = _SIL_END_RE.search(line)
        if m:
            end = float(m.group(1))
            dur = float(m.group(2)) if m.group(2) else (
                max(0.0, end - pending) if pending is not None else 0.0)
            start = pending if pending is not None else max(0.0, end - dur)
            out.append({"start": round(start, 2), "end": round(end, 2),
                        "duration": round(dur, 2)})
            pending = None
    if pending is not None and total > 0:
        out.append({"start": round(pending, 2), "end": round(total, 2),
                    "duration": round(max(0.0, total - pending), 2)})
    return out


def parse_freeze(stderr: str, total: float = 0.0) -> list[dict]:
    """同 `_freezes()` 的坑：冻到片尾只有 start，没有 duration。"""
    out: list[dict] = []
    started: list[float] = []
    ends: list[float] = []
    durs: list[float] = []
    for line in stderr.splitlines():
        m = _FRZ_START_RE.search(line)
        if m:
            started.append(float(m.group(1)))
            continue
        m = _FRZ_END_RE.search(line)
        if m:
            ends.append(float(m.group(1)))
            continue
        m = _FRZ_DUR_RE.search(line)
        if m:
            durs.append(float(m.group(1)))
    for i, s in enumerate(started):
        if i < len(durs):
            d = durs[i]
            e = ends[i] if i < len(ends) else s + d
        elif i < len(ends):
            e = ends[i]
            d = max(0.0, e - s)
        else:
            d = max(0.0, total - s) if total > 0 else 0.0
            e = s + d
        if d > 0:
            out.append({"start": round(s, 2), "end": round(e, 2),
                        "duration": round(d, 2)})
    return out


def parse_loudness(stderr: str) -> tuple[float | None, float | None]:
    """`ebur128` 收尾汇总：取**最后一个** I / Peak（多段时最后一行才是全片）。"""
    loud = _LOUD_RE.findall(stderr)
    peak = _PEAK_RE.findall(stderr)
    return (float(loud[-1]) if loud else None,
            float(peak[-1]) if peak else None)


def _video_signals(path: Path, total: float) -> dict:
    err = _ffmpeg_stderr([
        "-i", str(path),
        "-vf", f"blackdetect=d={DEEP['black_min_sec']}:pix_th={DEEP['black_pix_th']},"
               f"freezedetect=n={DEEP['freeze_noise_db']}dB:d={DEEP['freeze_min_sec']}",
        "-map", "0:v", "-f", "null", "-",
    ])
    return {"black": parse_black(err), "freeze": parse_freeze(err, total)}


def _audio_signals(path: Path, total: float) -> dict:
    err = _ffmpeg_stderr([
        "-i", str(path),
        "-af", f"silencedetect=n={DEEP['silence_noise_db']}dB:d={DEEP['silence_min_sec']},"
               "ebur128=framelog=quiet",
        "-map", "0:a", "-f", "null", "-",
    ])
    loud, peak = parse_loudness(err)
    return {"silence": parse_silence(err, total), "loudness": loud, "true_peak": peak}


def deep_inspect(path: Path, *, expect_duration: float | None = None,
                 expect_w: int = 0, expect_h: int = 0) -> dict:
    """成片技术质检（黑屏 / 长静音 / 响度漂移 / 削波 / 冻结 / 流完整性 / 时长 / 分辨率）。

    返回三态：`level = ok | warn | fail`，`checks` 逐项给结论，
    **最差状态胜出**（同 `release-gate` 的合并口径）。本地 ffmpeg，零费用。
    """
    path = Path(path)
    if not path.exists():
        return {"level": "fail", "ok": False, "checks": [
            {"id": "file", "level": "fail", "zh": "成片文件不存在"}], "stats": {}}

    info = _probe(path)
    total = info["duration"]
    checks: list[dict] = []

    def add(cid: str, level: str, zh: str, **data) -> None:
        item = {"id": cid, "level": level, "zh": zh}
        if data:
            item["data"] = data
        checks.append(item)

    # 1. 流完整性（qc.ts:163-167）
    if not info["has_video"]:
        add("video-stream", "fail", "成片缺少视频流")
        return {"level": "fail", "ok": False, "checks": checks,
                "stats": {"duration": round(total, 3)}}
    add("video-stream", "ok", f"视频流正常（{info['width']}×{info['height']}）")
    if not info["has_audio"]:
        add("audio-stream", "fail", "成片缺少音频流（台词/环境音丢失）")
    else:
        add("audio-stream", "ok", "音频流正常")

    # 2. 时长（qc.ts:170-187）
    if total < 1:
        add("duration", "fail", f"成片时长异常（{total:.2f} 秒）")
    elif expect_duration and expect_duration > 0:
        drift = abs(total - expect_duration)
        tol = max(2.0, expect_duration * 0.15)
        if drift > tol:
            add("duration", "warn",
                f"时长偏差较大：实际 {total:.1f} 秒，预期 {expect_duration:.1f} 秒",
                duration=round(total, 2), expected=round(expect_duration, 2))
        else:
            add("duration", "ok", f"时长正常（{total:.1f} 秒）")
    else:
        add("duration", "ok", f"时长 {total:.1f} 秒")

    # 3. 分辨率（qc.ts:190-201）
    if expect_w and expect_h:
        if (info["width"], info["height"]) != (expect_w, expect_h):
            add("resolution", "warn",
                f"分辨率不符：实际 {info['width']}×{info['height']}，"
                f"预期 {expect_w}×{expect_h}")
        else:
            add("resolution", "ok", "分辨率符合预期")

    # 4. 黑屏（qc.ts:203-225）
    try:
        vs = _video_signals(path, total)
    except Exception as e:  # noqa: BLE001
        vs = {"black": [], "freeze": []}
        add("black", "warn", f"黑屏检测没跑成：{e}")
        add("freeze", "warn", f"定格检测没跑成：{e}")
    else:
        black = vs["black"]
        btotal = sum(b["duration"] for b in black)
        longest = max((b["duration"] for b in black), default=0.0)
        share = btotal / total if total else 0.0
        if longest >= DEEP["black_fail_longest"] or share > DEEP["black_fail_share"]:
            add("black", "fail",
                f"检测到明显黑屏：{len(black)} 段，共 {btotal:.1f} 秒",
                segments=black, totalSec=round(btotal, 2))
        elif black:
            add("black", "warn",
                f"检测到短暂黑屏 {len(black)} 段（共 {btotal:.1f} 秒）",
                segments=black, totalSec=round(btotal, 2))
        else:
            add("black", "ok", "无黑屏")

        # 6. 定格 —— 只提醒不拦（qc.ts:286）
        frozen = [f for f in vs["freeze"] if f["duration"] >= DEEP["freeze_min_sec"]]
        if frozen:
            longest_f = max(f["duration"] for f in frozen)
            add("freeze", "warn",
                f"画面静止 {len(frozen)} 段（最长 {longest_f:.1f} 秒）",
                segments=frozen)
        else:
            add("freeze", "ok", "无定格")

    # 5. 静音 / 响度（qc.ts:227-284）
    if info["has_audio"]:
        try:
            aus = _audio_signals(path, total)
        except Exception as e:  # noqa: BLE001
            add("silence", "warn", f"静音检测没跑成：{e}")
        else:
            sil = aus["silence"]
            stotal = sum(s["duration"] for s in sil)
            longest_s = max((s["duration"] for s in sil), default=0.0)
            share_s = stotal / total if total else 0.0
            if longest_s >= DEEP["silence_fail_longest"] or share_s > DEEP["silence_fail_share"]:
                add("silence", "fail",
                    f"检测到长静音：最长 {longest_s:.1f} 秒（共 {stotal:.1f} 秒）",
                    segments=sil, totalSec=round(stotal, 2))
            elif sil:
                add("silence", "warn",
                    f"检测到静音 {len(sil)} 段（共 {stotal:.1f} 秒）",
                    segments=sil, totalSec=round(stotal, 2))
            else:
                add("silence", "ok", "无异常静音")

            loud = aus["loudness"]
            if loud is None:
                add("loudness", "warn", "响度测不出来（容器/编码不支持 ebur128）")
            elif loud < DEEP["loudness_fail_below"]:
                add("loudness", "fail",
                    f"音量过低（{loud:.1f} LUFS），接近无声", loudness=round(loud, 1))
            elif abs(loud - DEEP["loudness_target"]) > DEEP["loudness_warn_delta"]:
                add("loudness", "warn",
                    f"响度偏离标准：{loud:.1f} LUFS（目标 "
                    f"{DEEP['loudness_target']:.0f} LUFS）", loudness=round(loud, 1))
            else:
                add("loudness", "ok", f"响度正常（{loud:.1f} LUFS）")

            peak = aus["true_peak"]
            if peak is not None and peak > DEEP["true_peak_warn_above"]:
                add("true-peak", "warn",
                    f"峰值电平过高（{peak:.1f} dBFS），可能削波",
                    truePeak=round(peak, 1))

    levels = {c["level"] for c in checks}
    level = "fail" if "fail" in levels else ("warn" if "warn" in levels else "ok")
    log.info("深度质检 %s：%s（%d 项）", path.name, level, len(checks))
    return {"level": level, "ok": level != "fail", "checks": checks,
            "stats": {"duration": round(total, 3),
                      "width": info["width"], "height": info["height"],
                      "fps": info["fps"], "has_audio": info["has_audio"]}}
