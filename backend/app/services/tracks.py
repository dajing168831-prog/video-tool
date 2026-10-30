"""成片 = 两条轨道（画面 / 声音），一次 ffmpeg 执行出来。

为什么要有这一层
----------------
旧的 `compose.compose()` 是**一次性拼装**：一个函数里写死"画面 tpad → 遮罩 →
配音混底音 → 归一响度"，参数只能一个个加，加到最后没人说得清成片是
怎么拼出来的。更要紧的是：它只有一个"输入视频"，所以调用方必须先拿
`assemble.build()` 把镜头拼成 `timeline.mp4`，**再让 compose 编码一遍** ——
同一条画面被压了两次。

轨道模型把"成片由什么组成"变成数据：
  画面轨 = 一串片段（源文件 + 起止 + 定格 + 遮罩），可以来自不同文件；
  声音轨 = 一串片段（配音 / 底音 / 音效 + 增益 + 是否被压）。
两条轨道各自有指纹，所以"改了声音"和"改了某一段画面"能分开说，而不是笼统地
"整片重出"。

🩸 2026-10-23 主人拍板「也不烧字幕」：原第三条字幕轨删掉，成片不再有任何字幕。

取舍（写清楚，别当成能力吹）
--------------------------
- **不做逐段编码缓存**。把每段单独编码再拼接，等于多压一代，画质换速度，
  不划算。这里省下的是**模型调用**（画面素材不用重新生成），不是 CPU。
- **多片段时只编码一次**（在滤镜图里 trim + concat），不再经过中间文件。
  这是相对旧链路实打实的改进：少一代压缩。

与旧实现的等价性
----------------
`Composition.from_legacy()` 复刻旧 `compose()` 三种声音分支的拼法；
`scripts/track_p2_check.py` 用冻结的旧实现当尺子逐帧比对。
"""
from __future__ import annotations

import hashlib
import logging
import subprocess
from dataclasses import dataclass, field, replace
from pathlib import Path

from app.services.media import ffmpeg_path, ffprobe_path

log = logging.getLogger(__name__)

# 侧链压缩（ducking）参数：说话时把底音压下去，说完抬回来。
# 0.03 / 8 / 15 / 300 是旧链路实测出来的值，别随手改 —— 改了要重听。
DUCK_THRESHOLD = 0.03
DUCK_RATIO = 8
DUCK_ATTACK = 15
DUCK_RELEASE = 300
LOUDNESS = "loudnorm=I=-14:TP=-1.5:LRA=11"


# --------------------------------------------------------------------------
# 片段
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class VideoClip:
    """画面轨上的一段。

    source: 源文件
    start:  源内起点（秒）
    end:    源内终点；None = 到源尾
    freeze: 这一段放完之后把最后一帧冻住多久（秒）。旧链路的 `tpad` 就落在这里
    mask:   (x, y, w, h, alpha) 遮盖区域；只有画面轨有意义
    label:  给人看的名字（"shot_03" / "whole"），只进指纹与日志，不进滤镜
    """

    source: Path
    start: float = 0.0
    end: float | None = None
    freeze: float = 0.0
    mask: tuple[int, int, int, int, float] | None = None
    label: str = ""

    @property
    def is_whole(self) -> bool:
        """整条源、不裁 —— 编译时可以省掉 trim/setpts，与旧实现逐位一致。"""
        return abs(self.start) < 1e-9 and self.end is None


@dataclass(frozen=True)
class AudioClip:
    """声音轨上的一段。

    role: voice（新配音）/ bed（底音、氛围）/ sfx（点音效）
    gain: 增益倍数
    duck: 是否被 voice 压下去（底音该开，音效一般不开）
    """

    source: Path
    start: float = 0.0
    end: float | None = None
    role: str = "bed"
    gain: float = 1.0
    duck: bool = False
    label: str = ""

    @property
    def is_whole(self) -> bool:
        return abs(self.start) < 1e-9 and self.end is None


# --------------------------------------------------------------------------
# 轨道
# --------------------------------------------------------------------------


@dataclass
class VisualTrack:
    clips: list[VideoClip] = field(default_factory=list)
    # 给了尺寸/帧率就把每段规格化成同一规格（来自不同来源时必须给）
    width: int = 0
    height: int = 0
    fps: float = 0.0

    def __post_init__(self) -> None:
        if self.clips and any(not c.is_whole for c in self.clips) and not self.fps:
            # 不设帧率也能跑，但多段拼接的帧边界会跟着源帧率走；
            # 这里只提示，不阻断 —— 旧链路也是这么跑的
            log.debug("画面轨有裁切段但没有指定 fps，按源帧率拼接")

    @property
    def conform(self) -> bool:
        return bool(self.width and self.height and self.fps)


@dataclass
class AudioTrack:
    clips: list[AudioClip] = field(default_factory=list)
    loudness: str | None = LOUDNESS   # None = 不做响度归一
    duck_threshold: float = DUCK_THRESHOLD
    duck_ratio: float = DUCK_RATIO
    duck_attack: float = DUCK_ATTACK
    duck_release: float = DUCK_RELEASE


# 🩸 2026-10-23 主人拍板「也不烧字幕」：原 CaptionTrack（.ass 字幕轨）整个删掉。
# 成片只有画面轨 + 声音轨两条。


# --------------------------------------------------------------------------
# 作品 = 两条轨道 + 收口参数
# --------------------------------------------------------------------------


@dataclass
class Composition:
    visual: VisualTrack
    audio: AudioTrack = field(default_factory=AudioTrack)
    duration: float = 0.0      # 成片目标时长（秒）；0 = 取最长的一路
    fps: float = 0.0           # 给了就按帧数钉死
    crf: int = 20
    preset: str = "veryfast"

    # ---- 收口 ----

    @property
    def cut(self) -> float:
        """成片实际停在哪一刻。

        有帧率时按 **帧数** 算：`-t` 只写 3 位小数会把 12.0333 截成 12.033，
        30fps/48000Hz 下正好少 16 个采样（实测 577584 ≠ 577600）。
        """
        if self.duration > 0 and self.fps > 0:
            return round(self.duration * self.fps) / self.fps
        return self.duration

    @property
    def frames(self) -> int:
        return int(round(self.duration * self.fps)) if self.duration > 0 and self.fps > 0 else 0

    # ---- 指纹 ----

    def digests(self) -> dict:
        """两条轨道各自的指纹 + 收口参数。

        用来回答"这次改的是哪条轨道"，而不是"整片变了"。
        """
        return {
            "visual": _digest([_clip_key(c) for c in self.visual.clips]
                              + [f"conform={self.visual.width}x{self.visual.height}"
                                 f"@{self.visual.fps}"]),
            "audio": _digest([_clip_key(c) + [c.role, f"{c.gain:.3f}", str(bool(c.duck))]
                              for c in self.audio.clips]
                             + [str(self.audio.loudness)]),
            "render": _digest([f"{self.cut:.6f}", str(self.frames),
                               str(self.crf), self.preset]),
        }

    def clip_digests(self) -> dict:
        """逐段的指纹 —— plan 用它点名"第几段失效"。"""
        return {
            "visual": [_digest(_clip_key(c)) for c in self.visual.clips],
            "audio": [_digest(_clip_key(c) + [c.role, f"{c.gain:.3f}", str(bool(c.duck))])
                      for c in self.audio.clips],
        }

    def changed(self, other: "Composition") -> list[str]:
        """相对另一份作品，哪几条轨道变了。"""
        a, b = self.digests(), other.digests()
        return [k for k in ("visual", "audio", "render") if a[k] != b[k]]

    def replace_visual(self, clips: list[VideoClip], *, width: int = 0,
                       height: int = 0, fps: float = 0.0) -> "Composition":
        """把画面轨换成 N 段真实素材 —— 不再经过中间文件。

        两样东西要从旧画面轨继承下来，否则会**静默丢功能**：
          · 尾巴定格（配音比画面长时要补）—— 挪到最后一段；
          · 遮罩（盖原片硬字幕）—— 挂到第一段上（编译时按整条画面处理）。
        """
        old = self.visual.clips
        tail = old[-1].freeze if old else 0.0
        mask = next((c.mask for c in old if c.mask), None)

        new = list(clips)
        if new and mask is not None:
            new[0] = replace(new[0], mask=mask)
        if new and tail > 0.001:
            new[-1] = replace(new[-1], freeze=new[-1].freeze + tail)
        self.visual = VisualTrack(clips=new, width=width, height=height, fps=fps)
        return self


# --------------------------------------------------------------------------
# 指纹工具
# --------------------------------------------------------------------------

_FILE_CACHE: dict[tuple[str, int, int], str] = {}


def _file_key(path: Path | None) -> str:
    if path is None:
        return "-"
    p = Path(path)
    try:
        st = p.stat()
    except OSError:
        return f"{p.as_posix()}:missing"
    key = (p.as_posix(), st.st_size, int(st.st_mtime))
    hit = _FILE_CACHE.get(key)
    if hit:
        return f"{p.name}:{hit}"
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    digest = h.hexdigest()[:16]
    _FILE_CACHE[key] = digest
    return f"{p.name}:{digest}"


def _clip_key(c: VideoClip | AudioClip) -> list[str]:
    end = "-" if c.end is None else f"{c.end:.3f}"
    out = [_file_key(c.source), f"{c.start:.3f}-{end}"]
    if isinstance(c, VideoClip):
        out += [f"frz={c.freeze:.3f}", f"mask={c.mask}"]
    return out


def _digest(parts) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(repr(p).encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:16]


# --------------------------------------------------------------------------
# 编译：轨道 → ffmpeg 参数
# --------------------------------------------------------------------------


@dataclass
class _Plan:
    args: list[str]
    graphs: list[str]
    maps: list[str]
    workdir: Path


def _probe_duration(path: Path | None) -> float:
    if path is None:
        return 0.0
    fp = ffprobe_path()
    if not fp:
        return 0.0
    p = subprocess.run(
        [fp, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, errors="ignore", timeout=60,
    )
    try:
        return max(0.0, float((p.stdout or "").strip().splitlines()[0]))
    except (ValueError, IndexError):
        return 0.0


def _clip_chain(c: VideoClip, track: VisualTrack) -> list[str]:
    """一段画面要做的滤镜。整条源什么都不做 —— 与旧实现逐位一致。

    🩸 裁切只在滤镜里做（`trim`），**不在输入上加 `-ss/-t`**：两处都裁会把
    已经偏移过的流再裁一遍，成品只剩碎片（实测 3 段拼出 16 秒）。`trim` 按
    帧时间戳切，相邻两段在同一个切点上不会重复也不会丢帧；输入侧的 `-ss`
    是按"最近的关键帧 + 解码丢弃"实现的，边界上容易多出一帧。
    """
    chain: list[str] = []
    if not c.is_whole:
        end = "" if c.end is None else f":end={c.end:.6f}"
        chain.append(f"trim=start={c.start:.6f}{end}")
        # 时间戳归零 —— 不归零的话拼接会把上一段的偏移带进下一段
        chain.append("setpts=PTS-STARTPTS")
    if track.conform:
        w, h, fps = track.width, track.height, track.fps
        chain.append(f"scale={w}:{h}:force_original_aspect_ratio=increase")
        # 比例不一致时放大后裁切，不补黑边（补边会在成片里留一条黑杠）
        chain.append(f"crop={w}:{h}:(iw-{w})/2:(ih-{h})/2")
        chain.append("setsar=1")
        if fps:
            chain.append(f"fps={fps:g}")
    if c.freeze > 0.001:
        chain.append(f"tpad=stop_mode=clone:stop_duration={c.freeze:.3f}")
    return chain


def _visual_stage(track: VisualTrack) -> tuple[list[str], str, list[str]]:
    """画面轨 → (前置滤镜段, 主输入标签, 还没挂上的滤镜链)。

    单段时把后缀滤镜（遮原片字幕的遮罩）并进同一条链，编译出来与旧实现逐字相同；
    多段时先在滤镜图里 trim+concat，再挂后缀。
    """
    clips = track.clips
    if len(clips) == 1:
        return [], "[0:v]", _clip_chain(clips[0], track)

    segs: list[str] = []
    labels: list[str] = []
    for i, c in enumerate(clips):
        chain = _clip_chain(c, track)
        if chain:
            segs.append(f"[{i}:v]{','.join(chain)}[v{i}]")
            labels.append(f"[v{i}]")
        else:
            labels.append(f"[{i}:v]")
    segs.append(f"{''.join(labels)}concat=n={len(clips)}:v=1:a=0[vcat]")
    return segs, "[vcat]", []


def _mix_group(segs: list[str], refs: list[str], label: str) -> str | None:
    """多轨先合成一条；单轨原样返回（旧实现里也是直接用原流）。"""
    if not refs:
        return None
    if len(refs) == 1:
        return refs[0]
    segs.append(f"{''.join(refs)}amix=inputs={len(refs)}:"
                f"duration=longest:dropout_transition=0[{label}]")
    return f"[{label}]"


def _audio_graph(track: AudioTrack, base: int) -> tuple[list[str], list[str], str | None]:
    """声音轨 → (滤镜段, 额外输入参数, 输出标签)。

    编译结果与旧 `compose()` 的三种声音分支逐字一致：
      配音+底音 → volume → asplit → sidechaincompress → amix → 响度 → apad
      只有配音   → 响度 → apad
      只有底音   → apad（不归一响度：原声的温度是内容的一部分）
    """
    if not track.clips:
        return [], [], None

    inputs: list[str] = []
    segs: list[str] = []
    voices: list[str] = []
    ducked: list[str] = []
    dry: list[str] = []

    for k, c in enumerate(track.clips):
        idx = base + k
        src = str(Path(c.source).resolve())
        if c.is_whole:
            inputs += ["-i", src]
        else:
            inputs += ["-ss", f"{c.start:.3f}"]
            if c.end is not None:
                inputs += ["-t", f"{max(0.0, c.end - c.start):.3f}"]
            inputs += ["-i", src]

        chain: list[str] = []
        if not c.is_whole:
            chain.append("asetpts=PTS-STARTPTS")
        if abs(c.gain - 1.0) > 1e-6:
            chain.append(f"volume={c.gain:.3f}")
        if chain:
            # 标签按**输入序号**取，不按列表序号：底音是输入 2 就叫 [a2]，
            # 与旧实现逐字一致；配音用 [p*] 前缀，避开侧链的 [a1]/[sc]
            lab = f"p{idx}" if c.role == "voice" else f"a{idx}"
            segs.append(f"[{idx}:a]{','.join(chain)}[{lab}]")
            ref = f"[{lab}]"
        else:
            ref = f"[{idx}:a]"

        if c.role == "voice":
            voices.append(ref)
        elif c.duck:
            ducked.append(ref)
        else:
            dry.append(ref)

    voice_ref = _mix_group(segs, voices, "avoice")
    bed_ref = _mix_group(segs, ducked, "abed")

    if voice_ref is not None and bed_ref is not None:
        # 说话时把底音压下去（ducking），说完抬回来 —— 不压的话底音会全程
        # 和配音抢中频，听着像"配音贴上去的"
        segs.append(f"{voice_ref}asplit=2[a1][sc]")
        segs.append(
            f"{bed_ref}[sc]sidechaincompress=threshold={track.duck_threshold:g}:"
            f"ratio={track.duck_ratio:g}:attack={track.duck_attack:g}:"
            f"release={track.duck_release:g}[ad]"
        )
        refs: list[str] = ["[a1]", "[ad]"]
        first = "[a1]"
    elif voice_ref is not None:
        refs = [voice_ref]
        first = voice_ref
    else:
        # 没有配音就无从"压"：标了 duck 的底音直接并进主混
        refs = ducked + dry
        if not refs:
            return segs, inputs, None
        first = refs[0]

    if voice_ref is not None:
        refs += dry
    elif bed_ref is not None:
        refs = [bed_ref] + dry

    if len(refs) > 1:
        tail = "amix=inputs=%d:duration=first:dropout_transition=0" % len(refs)
        if track.loudness:
            tail += f",{track.loudness}"
        segs.append(f"{''.join(refs)}{tail},apad[aout]")
    else:
        head = f"{track.loudness}," if track.loudness else ""
        segs.append(f"{first}{head}apad[aout]")

    return segs, inputs, "[aout]"


def compile_plan(comp: Composition) -> _Plan:
    """把作品编译成 ffmpeg 参数。纯函数，不跑进程。"""
    if not comp.visual.clips:
        raise ValueError("画面轨是空的")

    workdir = Path(comp.visual.clips[0].source).resolve().parent
    args: list[str] = []
    graphs: list[str] = []
    maps: list[str] = []

    # 画面输入：只开文件，裁切全交给滤镜里的 trim（见 `_clip_chain`）
    for c in comp.visual.clips:
        args += ["-i", str(Path(c.source).resolve())]

    pre, v_base, v_chain = _visual_stage(comp.visual)

    # 遮原片自带的硬字幕（不复刻字幕，但别人的字还留在画面里，盖掉更干净）
    mask = next((c.mask for c in comp.visual.clips if c.mask), None)
    if mask:
        x, y, w, h, alpha = mask
        v_chain.append(f"drawbox=x={x}:y={y}:w={w}:h={h}:color=black@{alpha}:t=fill")

    graphs += pre
    if v_chain:
        graphs.append(f"{v_base}{','.join(v_chain)}[v]")
        maps += ["-map", "[v]"]
    elif v_base == "[0:v]":
        maps += ["-map", "0:v"]
    else:
        maps += ["-map", v_base]

    a_segs, a_inputs, a_out = _audio_graph(comp.audio, len(comp.visual.clips))
    if a_out:
        args += a_inputs
        graphs += a_segs
        maps += ["-map", a_out]

    if graphs:
        args += ["-filter_complex", ";".join(graphs)]

    args += maps

    if comp.duration > 0:
        args += ["-t", f"{comp.cut:.6f}"]
    if comp.frames > 0:
        args += ["-frames:v", str(comp.frames)]

    return _Plan(args=args, graphs=graphs, maps=maps, workdir=workdir)


def render(comp: Composition, out: Path) -> Path:
    """执行一版成片。全 CPU。"""
    out = Path(out).resolve()
    plan = compile_plan(comp)
    ff = ffmpeg_path()
    if not ff:
        raise RuntimeError("找不到 ffmpeg，请设置 VT_FFMPEG")

    args = [
        "-hide_banner", "-loglevel", "error", "-y",
        *plan.args,
        "-c:v", "libx264", "-crf", str(comp.crf), "-preset", comp.preset,
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart",
        str(out),
    ]
    proc = subprocess.run([ff, *args], cwd=str(plan.workdir),
                          capture_output=True, text=True, errors="ignore", timeout=900)
    if proc.returncode != 0 or not out.exists():
        raise RuntimeError(f"合成失败: {(proc.stderr or '')[-600:]}")
    log.info("合成完成: %s (%.1f MB)", out, out.stat().st_size / 1024 / 1024)
    return out


# --------------------------------------------------------------------------
# 旧接口的形状（让 compose.compose 一行就能搬过来）
# --------------------------------------------------------------------------


def from_legacy(
    *,
    video: Path,
    voice: Path | None = None,
    mask: tuple[int, int, int, int, float] | None = None,
    pad_to: float | None = None,
    target: float | None = None,
    fps: float = 0.0,
    bg_from: Path | None = None,
    bg_gain: float = 0.25,
    crf: int = 20,
    preset: str = "veryfast",
) -> Composition:
    """按旧 `compose()` 的参数形状拼一份作品。

    `pad_to` 是"配音比画面长时冻最后一帧补够"，落到画面最后一段的 `freeze`；
    `extra_pad`（target 比"画面+pad_to"还长）也并进同一个定格里 —— 旧实现
    就是这么算的，分开写两边会飘。
    """
    video = Path(video).resolve()
    pad_to = max(0.0, float(pad_to or 0.0))
    video_dur = _probe_duration(video)
    voice_dur = _probe_duration(voice)
    bg_dur = _probe_duration(bg_from)
    if target is None or target <= 0:
        target = max(video_dur + pad_to, voice_dur, bg_dur)
    target = float(target)

    extra = max(0.0, target - (video_dur + pad_to))
    freeze = pad_to + extra
    if freeze <= 0.05:
        freeze = 0.0

    visual = VisualTrack(clips=[VideoClip(source=video, freeze=freeze, mask=mask,
                                          label="whole")])

    audio_clips: list[AudioClip] = []
    if voice is not None:
        audio_clips.append(AudioClip(source=Path(voice).resolve(), role="voice",
                                     label="voice"))
    if bg_from is not None:
        # 底音只能从原片拿：`original` 整轨接回，`mix` 用分离后的背景轨。
        # 没有新配音时底音就是内容本身 —— 增益必须留在 1.0，
        # 否则等于把原声调小了还叫"保留原声"。
        audio_clips.append(AudioClip(
            source=Path(bg_from).resolve(), role="bed",
            gain=(float(bg_gain) if voice is not None else 1.0),
            duck=True, label="bed"))

    return Composition(
        visual=visual,
        # 没有新配音就不做响度归一：原声的响度是内容的一部分
        audio=AudioTrack(clips=audio_clips,
                         loudness=(LOUDNESS if voice is not None else None)),
        duration=target, fps=float(fps or 0.0), crf=crf, preset=preset,
    )
