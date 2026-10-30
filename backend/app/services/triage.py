"""逐镜分诊：每一镜到底该怎么处理。

为什么需要它
------------
hypit 的复刻文档里有一句关键的话（`skills/hypit/references/playbooks/craft/
video-direction.md`）：

    "The fact that a task is called a clone does not by itself make the whole
     reference video a generation input."

    "A still can establish a person, object, place or composition; prose can
     direct an action and its expressive purpose. When a particular unfolding in
     time is essential to the result … use the relevant source footage as a
     video reference."

翻成人话：**"复刻"不等于"把整条原片喂给模型"**。
一张静帧就能交代人/物/景，文字能交代动作；只有"这一段时间里发生了什么"本身
就是重点时（跳舞、打斗、运镜、表演节奏），才值得把原片片段当参考送进模型。

于是每一镜只有三种处置：

    keep   不用改 → **直接用原片像素**。这才是真正的 1:1，而且免费。
    still  要改，但这一镜基本是静的 → 抽中间帧重画 → 图生视频。便宜。
    video  动作/运镜是重点 → 原片这一段当视频参考重制。贵，但动作保得住。

整片重制 = 所有镜头都判成 video。那是兜底，不是默认 —— 它既贵，又把本来
不该动的地方也改了。
"""
from __future__ import annotations

import os

# 相邻帧差均值（0–255）超过这个值，认为"画面在动"。
# 实测（2026-10-21）：全静止画面 0.0，合成测试图 2.4，真实手持素材 7–20。
# 阈值故意压低：把"该动"的镜头误判成静态，模型会重画出一个对不上口型的脸，
# 代价远大于多送一段视频；反过来把静态镜判成动态只是多花点钱。
# 用 VT_TRIAGE_MOTION_MIN 可以在不改代码的前提下重新标定。
def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


MOTION_VIDEO_MIN = _env_float("VT_TRIAGE_MOTION_MIN", 1.2)

# 视频参考单段下限（两家都是 4s）。判成 video 的镜头不够长时要把区间撑到这么长
MIN_SPAN = 4.0

# 镜头时长里有多大比例压在台词上，才算"这一镜在说话"
SPEECH_OVERLAP = 0.5


def _speaks(shot: dict, spans) -> bool:
    """这一镜是不是"有人在说话"：和某段台词的时间重叠过半就算。"""
    st, en = float(shot["start"]), float(shot["end"])
    dur = max(0.01, en - st)
    for a, b in spans or ():
        overlap = min(float(b), en) - max(float(a), st)
        if overlap > 0 and overlap >= SPEECH_OVERLAP * dur:
            return True
    return False


def decide(shots: list[dict], picks: list[int] | None = None, *,
           threshold: float = MOTION_VIDEO_MIN,
           speech_spans=None, audio_mode: str = "tts",
           force_video: bool = False) -> dict[int, str]:
    """逐镜给出处置：keep / still / video。

    picks 为空＝所有镜头都要处理（用户想整条换）。给了就以它为准 ——
    没勾的镜头一律保留原片，这是用户最直接的控制手段。

    ⚠️ 光看运动量不够，还要看**声音怎么处理**（实测 2026-10-21）：

    口播镜头（真人对着镜头说话）的运动量实测 2.38，远高于阈值 —— 只看运动量
    会判成 video，也就是把原片这一段当视频参考送给模型。而模型看到的是
    **原片那张嘴在说原片那句话**，它会照着搬。若同时换成了全新配音，
    观众看到的就是"这张脸在说别的话、嘴型全错"。

    所以「全新配音 + 这一镜有台词」必须走 still（首帧重绘 → 图生视频）：
    连人带口型一起重新生成，观众没有"正确的原口型"可以对比，反而自然。

    保留原声（只有 original）时反过来 —— 原声还在，口型跟原片一致正是要的效果，
    这时照旧走 video，动作和口型都保得住。

    🩸 `mix` **不算**"保留原声"：它换的是全新配音，只把背景（分离后的
    music/sfx）留下。口型必须跟着新配音重做，否则就是"嘴在说原话"。
    """
    want = set(picks) if picks else None
    new_dub = (audio_mode or "tts").strip().lower() != "original"
    out: dict[int, str] = {}
    for s in shots or []:
        i = int(s["i"])
        if want is not None and i not in want:
            out[i] = "keep"
            continue
        if force_video:
            # 🩸 风格参考**视频**只有视频模型读得到：静帧重绘走的是图生图，
            # 参考视频根本发不出去。留着静帧 = 成片里一段套了风格、一段没套
            # （同一个片子两种观感，比全走视频重绘更难看）。所以整片强制走 video。
            out[i] = "video"
            continue
        motion = float(s.get("motion") or 0.0)
        if motion < threshold:
            out[i] = "still"
        elif new_dub and _speaks(s, speech_spans):
            out[i] = "still"
        else:
            out[i] = "video"
    return out


def video_spans(shots: list[dict], disp: dict[int, str], *, limit: float,
                total: float, min_sec: float = MIN_SPAN) -> list[tuple[float, float]]:
    """把连续判成 video 的镜头合并成 4–limit 秒的区间。

    为什么要合并：单镜常常不到 4 秒，两家视频模型都不收；而把相邻的
    同样要重制的镜头串起来，既够长又不会多切一刀。
    """
    ordered = sorted(shots or [], key=lambda s: float(s["start"]))
    runs: list[list[dict]] = []
    cur: list[dict] = []
    for s in ordered:
        if disp.get(int(s["i"])) == "video":
            cur.append(s)
        elif cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)

    spans: list[tuple[float, float]] = []
    for run in runs:
        a, b = float(run[0]["start"]), float(run[-1]["end"])
        a, b = _widen(a, b, min_sec, total)
        spans.extend(_split_run(run, a, b, limit, min_sec))
    return spans


def _split_run(run: list[dict], a: float, b: float, limit: float,
               min_sec: float) -> list[tuple[float, float]]:
    """把一段过长的 video 区间切开，**优先切在原片的镜头边界上**。

    🩸 2026-10-22 实测（任务 a47631b0，MiniMax H3 双人换人）：
    原片 0–11.7 是走廊两个主角、11.7 硬切到楼梯空镜（换了一批人）。
    旧实现按 15s 硬切 → 第一段 0–15s **横跨这个切点**，模型把整条参考片当
    一个连续镜头，切点处把 <Subject 1> 塞进空楼梯、还让路人变成了主角
    （第 13.5s 本该是 <Subject 2>）。按镜头边界切就没有这个问题。

    切点只能落在 [a+min_sec, a+limit] 里，且尾巴不能短于模型下限——
    两边都不满足时就均分这一段（长镜头没有别的选择）。

    🩸 2026-10-22 同一任务的第二刀（24.433 软切，见 `scene._hist_cuts`）：
    按边界切完只剩 3.6s 的尾巴，低于 4s 下限。旧写法退回"均分"→ 切点回到
    19.867，结果最后一段 19.867–28.033 **又横跨了 24.433**，等于白切。
    正确做法是**保住边界**，把最后一段的起点往回借到 `b-min_sec`（和上一段
    重叠 0.4s）：重叠的只是喂给模型的参考上下文，出片时 `_span_intervals`
    按镜头边界裁回来，时间轴上不会重复（见 `_widen` 同一套道理）。
    """
    starts = sorted({round(float(s["start"]), 3) for s in run or []})
    on_boundary = set(starts)
    out: list[tuple[float, float]] = []
    while b - a > limit + 1e-6:
        cand = [x for x in starts if a + min_sec - 1e-6 <= x <= a + limit + 1e-6]
        # 优先取最靠后的镜头边界：段越接近上限，段数越少
        cut = max(cand) if cand else a + limit
        if b - cut < min_sec - 1e-6 and cut not in on_boundary:
            # 尾巴太短、且这个切点本来就不是镜头边界 → 均分；
            # 均分后两段都一定 ≥ min_sec（因为 b-a > limit ≥ 2*min_sec）
            cut = a + (b - a) / 2.0
        out.append((round(a, 3), round(cut, 3)))
        a = cut
    if b - a > 0.2:
        if (out and b - a < min_sec - 1e-6
                and round(a, 3) in on_boundary):
            # 尾巴短，但它的起点是原片的镜头边界 → 保住这一刀，起点往回借。
            # 只有起点在镜头边界上才能这么借：`_span_intervals` 按镜头裁回时
            # 这一段只覆盖新镜头，和上一段不会抢同一段画面。
            a = round(b - min_sec, 3)
        out.append((round(a, 3), round(b, 3)))
    return out


def _widen(a: float, b: float, min_sec: float, total: float) -> tuple[float, float]:
    """不够 min_sec 就把区间往外撑，优先往后，再往前。

    撑出来的部分只是给模型的"上下文"，出片后会按镜头切回来，不会顶掉邻居的镜头。
    """
    if b - a >= min_sec:
        return a, b
    need = min_sec - (b - a)
    back = min(need, max(0.0, total - b))
    b += back
    need -= back
    if need > 0:
        a -= min(need, max(0.0, a))
    return a, b


def still_shots(disp: dict[int, str]) -> list[int]:
    return sorted(i for i, d in disp.items() if d == "still")


def summary(disp: dict[int, str]) -> dict:
    """给前端/日志看的分诊结果。"""
    n = {"keep": 0, "still": 0, "video": 0}
    for d in disp.values():
        n[d] = n.get(d, 0) + 1
    return n
