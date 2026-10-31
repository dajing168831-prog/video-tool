"""按镜头重排：把原片拆成 N 段，替换指定镜头，再拼回去。

为什么按镜头而不是整片替换：一条片子里总有该动的镜头（空镜、产品特写、
环境）和不该动的镜头（有人物动作的）。整片替换既贵又容易出戏，
按镜头替换才能做到"改多少、花多少钱"由用户决定。

产出是**无声**视频：时间轴拼好之后统一配 TTS 音轨，不在中间混音。
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from app.services.media import ffmpeg_path, ffprobe_path

log = logging.getLogger(__name__)

_FPS_FALLBACK = 30.0


def _run(args: list[str], cwd: Path, timeout: int = 1800) -> subprocess.CompletedProcess:
    ff = ffmpeg_path()
    if not ff:
        raise RuntimeError("找不到 ffmpeg，请设置 VT_FFMPEG")
    return subprocess.run(
        [ff, "-hide_banner", "-loglevel", "error", "-y", *args],
        cwd=str(cwd), capture_output=True, text=True, errors="ignore", timeout=timeout,
    )


class ShortClip(RuntimeError):
    """素材比需要的短，而且短得不能靠补帧糊过去。"""

    def __init__(self, src: Path, need: float, have: float):
        self.src, self.need, self.have = src, need, have
        super().__init__(
            f"{src.name} 只有 {have:.2f}s，需要 {need:.2f}s（差 {need - have:.2f}s）")


def _probe_duration(path: Path) -> float:
    fp = ffprobe_path()
    if not fp:
        return 0.0
    p = subprocess.run(
        [fp, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1", str(path)],
        capture_output=True, text=True, errors="ignore", timeout=120)
    for line in p.stdout.splitlines():
        if line.startswith("duration="):
            try:
                return float(line.split("=", 1)[1])
            except ValueError:
                return 0.0
    return 0.0


# 允许补的帧长：只够吸收"取整/帧对齐"的零头，不是拿来补时长的
_PAD_MAX = 0.12


def _normalize(src: Path, dest: Path, *, start: float = 0.0, dur: float,
               w: int, h: int, fps: float, max_pad: float = _PAD_MAX) -> None:
    """把一个片段压成统一规格：同尺寸、同帧率、同时长、无声。

    不统一的话 concat 会直接把音画对齐搞乱 —— 拼接要求所有片段参数一致。

    🩸 比例不一致时**放大后裁切**，不补黑边。模型的 `ratio=adaptive` 只会给
    "最接近的标准比例"：原片 576×1024（0.5625）拿回来是 496×864（0.5741），
    用 pad 补出来就是上下各十来行黑边（实测 10 + 12 行，成片里一条黑杠）。
    裁掉的是 2% 的边缘画面，比一条黑边好看得多。

    🩸 **不拿定格补时长**。参考项目的编辑计划明令禁止 tpad 定格复制 /
    静帧延长 / 重复帧补时长；coverage 不够只能用真实素材或删改剪辑解决。
    这里只给 ≤ `_PAD_MAX` 的零头补帧（取整误差），真的短了抛 `ShortClip`
    让上层换真实素材，而不是悄悄冻住画面。
    """
    avail = max(0.0, _probe_duration(src) - max(0.0, start))
    use = min(dur, avail) if avail > 0 else dur
    pad = max(0.0, dur - use)
    if pad > max_pad:
        raise ShortClip(src, need=dur, have=use)

    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h}:(iw-{w})/2:(ih-{h})/2,setsar=1,fps={fps},"
        # 每段的时间戳归零再拼 —— 否则 concat 会把上一段的偏移带进下一段
        f"setpts=PTS-STARTPTS"
    )
    if pad > 0.001:
        vf += f",tpad=stop_mode=clone:stop_duration={pad + 0.02:.3f}"
    args = ["-ss", f"{max(0.0, start):.3f}", "-i", str(src.resolve()),
            "-t", f"{dur:.3f}", "-an", "-vf", vf,
            "-c:v", "libx264", "-crf", "20", "-preset", "veryfast",
            "-pix_fmt", "yuv420p", str(dest.resolve())]
    proc = _run(args, cwd=dest.parent)
    if proc.returncode != 0 or not dest.exists():
        raise RuntimeError(f"片段规格化失败 {src.name}: {(proc.stderr or '')[-300:]}")


def _clip(src: Path, start: float, dur: float, *, label: str, kind: str,
          allow_freeze: bool = False) -> dict:
    """一段画面素材。素材不够长时按调用方给的口径处理。

    allow_freeze=False：短了就抛 ShortClip（换真实素材，不许冻）
    allow_freeze=True ：短多少就冻最后一帧补多少（静帧重绘那条路，本来就该冻）
    """
    have = max(0.0, _probe_duration(src) - max(0.0, start))
    freeze = 0.0
    if have + _PAD_MAX < dur:
        if not allow_freeze:
            raise ShortClip(src, need=dur, have=have)
        freeze = max(0.0, dur - have)
    return {"source": str(Path(src).resolve()), "start": round(start, 6),
            "end": round(start + dur, 6), "freeze": round(freeze, 6),
            "label": label, "kind": kind}


def _render_clips(clips: list[dict], out: Path, *, width: int, height: int,
                  fps: float, total: float) -> Path:
    """把 N 段素材编成一条时间轴 —— **只编码一次**。

    🩸 旧做法是每段先 `_normalize` 编码一遍（libx264 crf20），再用 `-c copy`
    拼成 timeline.mp4，最后由 compose 再编一遍 —— 每一帧都被压了两次，
    包括根本没改过的原片。这里把分段直接交给画面轨：滤镜里 trim+concat，
    出来就是最终画面，中间不落任何文件。
    """
    from app.services import tracks

    comp = tracks.Composition(
        visual=tracks.VisualTrack(
            clips=[tracks.VideoClip(source=Path(c["source"]), start=float(c["start"]),
                                   end=float(c["end"]), freeze=float(c.get("freeze") or 0),
                                   label=c.get("label") or "")
                   for c in clips],
            width=width, height=height, fps=fps),
        duration=total, fps=fps,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    return tracks.render(comp, out)


def plan_shots(
    video: Path,
    shots: list[dict],
    replace: dict[int, Path],
) -> list[dict]:
    """按镜头算时间轴：每镜要么用替换素材，要么用原片对应区间。纯计算。"""
    if not shots:
        raise RuntimeError("配方里没有镜头")
    clips: list[dict] = []
    for n, s in enumerate(shots):
        dur = max(0.2, float(s["end"]) - float(s["start"]))
        src = replace.get(int(s["i"]))
        if src is not None:
            # 这条路传进来的是**静帧重绘**的产物：整镜本来就是一张静的，
            # 尾巴补帧和原意一致，所以允许补满（视频参考那条路见 plan_intervals，
            # 那里素材短了必须换真实素材，不许冻）。
            clips.append(_clip(Path(src), 0.0, dur, label=f"shot{n}", kind="regen",
                               allow_freeze=True))
        else:
            clips.append(_clip(video, float(s["start"]), dur, label=f"shot{n}",
                               kind="source"))
    return clips


def build(
    video: Path,
    shots: list[dict],
    replace: dict[int, Path],
    *,
    workdir: Path,
    width: int,
    height: int,
    fps: float = 0.0,
) -> Path:
    """拼出新的时间轴（按镜头）。

    video:   原片
    shots:   recipe["shots"]，每个含 i / start / end
    replace: 镜头序号 -> 替换用的片段（通常是生成出来的视频）
    返回：无声的拼接结果
    """
    fps = fps or _FPS_FALLBACK
    if fps < 12:
        fps = _FPS_FALLBACK
    clips = plan_shots(video, shots, replace)
    total = sum(max(0.2, float(s["end"]) - float(s["start"])) for s in shots)
    out = _render_clips(clips, workdir / "timeline.mp4", width=width, height=height,
                        fps=fps, total=total)
    log.info("时间轴拼好: %d 段，其中替换 %d 段", len(clips), len(replace))
    return out


def plan_intervals(
    video: Path,
    intervals: list[tuple[float, float, Path, float]],
    *,
    total: float,
    notes: list[str] | None = None,
) -> list[dict]:
    """算出时间轴上每一段该用哪条素材 —— **纯计算，不落任何文件**。

    intervals: [(a, b, 素材, 素材里的起点)] —— 时间轴 [a,b) 用这条素材。
    没被任何区间覆盖的部分一律取原片。

    🩸 为什么不能按镜头拼：模型单次只收 15s，一镜 28.3s 的"一镜到底"必然
    被切成 15s + 13.3s 两段。按镜头收口时一个镜头只能放一条素材，
    另一段就被丢掉，时间轴上只能冻帧补足 —— 成片后半段不动、声音还在走
    （2026-10-21 实测：28.3s 片子在 14.97s 之后画面全冻）。
    """
    if total <= 0:
        raise RuntimeError("时间轴总长必须大于 0")

    # 先把区间裁到能真的取材的长度。
    # 🩸 素材比计划短时**不许冻帧**：能用多少用多少，剩下的回原片 ——
    # 参考项目的编辑计划只认「真实素材」或「删改剪辑」，定格填充是硬禁止。
    resolved: list[tuple[float, float, Path, float]] = []
    for a, b, src, off in intervals:
        a, b = max(0.0, min(total, a)), max(0.0, min(total, b))
        if b - a <= 0.02:
            continue
        have = max(0.0, _probe_duration(Path(src)) - off)
        if have >= (b - a) - _PAD_MAX:
            resolved.append((a, b, Path(src), off))
            continue
        keep = max(0.0, have - _PAD_MAX)
        if keep > 0.4:
            resolved.append((a, a + keep, Path(src), off))
            msg = (f"{Path(src).name} 只有 {have:.2f}s，计划 {b - a:.2f}s，"
                   f"剩 {b - a - keep:.2f}s 改用原片")
        else:
            msg = f"{Path(src).name} 太短（{have:.2f}s），这一整段改用原片"
        log.warning("时间轴：%s", msg)
        if notes is not None:
            notes.append(msg)

    # 所有边界切成基本区间：每段的起止（没被覆盖的部分取原片）
    marks = {0.0, total}
    for a, b, _src, _off in resolved:
        marks.add(a)
        marks.add(b)
    marks = sorted(marks)

    clips: list[dict] = []
    for x, y in zip(marks, marks[1:]):
        dur = y - x
        if dur <= 0.02:
            continue
        # 落在哪个替换区间里（重叠区间不该出现；真出现了以第一个为准）
        hit = None
        for a, b, src, off in resolved:
            if a - 1e-6 <= x and y <= b + 1e-6:
                hit = (src, off + (x - a))
                break
        n = len(clips)
        if hit is not None:
            src, src_start = hit
            clips.append(_clip(Path(src), src_start, dur, label=f"seg{n:03d}",
                               kind="regen"))
        else:
            clips.append(_clip(video, x, dur, label=f"seg{n:03d}", kind="source"))

    # 🩸 2026-10-31：段边界吸附到整数秒后，替换段会停在一个整数上（18.000），
    #   原片却到 18.033 —— 这 <0.12s 的零头按下面"未覆盖 → 取原片"处理，
    #   成片最后一帧就会闪回原片里的人（实测 render 5f5c5a72：主人一眼看到
    #   "最后一帧回到了原脸"）。零头就在 `_PAD_MAX` 这个"取整误差"口径内，
    #   所以并进前一段冻住最后一帧，**不回灌原片**。
    if (len(clips) >= 2 and clips[-1]["kind"] == "source"
            and clips[-1]["end"] - clips[-1]["start"] <= _PAD_MAX + 1e-6):
        tail = clips.pop()
        prev = clips[-1]
        prev["freeze"] = round(float(prev.get("freeze") or 0)
                               + (tail["end"] - tail["start"]), 6)
        log.info("片尾零头 %.3fs 并进前一段冻帧（不回灌原片）",
                 tail["end"] - tail["start"])
    if not clips:
        raise RuntimeError("时间轴没有任何片段")
    log.info("时间轴算好: %d 段，替换区间 %d 个", len(clips), len(resolved))
    return clips


def build_intervals(
    video: Path,
    intervals: list[tuple[float, float, Path, float]],
    *,
    total: float,
    workdir: Path,
    width: int,
    height: int,
    fps: float = 0.0,
    notes: list[str] | None = None,
) -> Path:
    """旧契约：算完直接编成一条无声时间轴（只编码一次）。"""
    fps = fps or _FPS_FALLBACK
    if fps < 12:
        fps = _FPS_FALLBACK
    clips = plan_intervals(video, intervals, total=total, notes=notes)
    return _render_clips(clips, workdir / "timeline.mp4", width=width,
                         height=height, fps=fps, total=total)


def pick_shots(shots: list[dict], ratio: float, limit: int) -> list[int]:
    """按比例均匀挑要替换的镜头。

    均匀挑而不是从头挑：开头几个镜头通常是钩子，全换掉反而更像另一条片子。
    """
    ratio = max(0.0, min(1.0, float(ratio)))
    n = len(shots)
    if ratio <= 0 or n == 0:
        return []
    k = min(limit, max(1, round(n * ratio)))
    if k >= n:
        return [int(s["i"]) for s in shots]
    # 均匀取 k 个下标（含首尾），避免挑出来挤在一边
    idx = sorted({round(i * (n - 1) / max(1, k - 1)) for i in range(k)})
    return [int(shots[i]["i"]) for i in idx]
