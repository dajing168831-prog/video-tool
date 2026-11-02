"""逐镜分诊：每一镜到底该怎么处理。

2026-11-02 主人拍板：**去掉了「静止镜头重绘」这一档**。

为什么
------
以前这里按第三方 hypit 的一句定性话（`craft/video-direction.md`：
"A still can establish a person… only when a particular unfolding in time is
essential … use the source footage as a video reference"）分了三档
keep / still / video，并用我们自己标定的运动量阈值 1.2 决定走哪一档。

问题出在阈值是自造的：hypit 原文只讲原则、**没有任何数值或判定算法**，
1.2 是 2026-10-21 拿三组样本拍的。实测下来真实素材的运动量可以低到 0.28，
判成「静止」的那一镜走的是另一条链路（生图 + 图生视频），出来的造型和
走视频重制的镜头对不上 —— 2026-11-02 双人换人的 8s/9s 服装突变就是这么来的。

主人原话：「本来我们就是视频重置的啊」——换人/换装本来就是整段拿原片当
参考重制，不需要「静帧」这条省钱的岔路。

于是每一镜只有两种处置：

    keep   用户没勾 → **直接用原片像素**。这才是真正的 1:1，而且免费。
    video  勾了 → 原片这一段当视频参考，整段重制。

`regen_mode="shots"` 是历史值：2026-11-02 起在入口处归一成 `auto`，
不再有“整批走静帧重绘”的分支。
"""
from __future__ import annotations

# 视频参考单段下限（两家都是 4s）。判成 video 的镜头不够长时要把区间撑到这么长
MIN_SPAN = 4.0


def decide(shots: list[dict], picks: list[int] | None = None) -> dict[int, str]:
    """逐镜给出处置：keep / video。

    picks 为空＝所有镜头都要处理（用户想整条换）。给了就以它为准 ——
    没勾的镜头一律保留原片，这是用户最直接的控制手段。

    🩸 2026-11-02 删掉了原来「新配音 + 这一镜有台词 → 走静帧重绘」那条。
    那条的理由是「模型看到原片那张嘴在说原话，会照着搬」。这个风险现在由
    `video_edit._span_script` 解：改写器拿得到这一段的真实台词和相对秒数，
    视频重制时能按台词重演。两套机制留一套，不叠。
    """
    want = set(picks) if picks else None
    out: dict[int, str] = {}
    for s in shots or []:
        i = int(s["i"])
        out[i] = "keep" if (want is not None and i not in want) else "video"
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


def summary(disp: dict[int, str]) -> dict:
    """给前端/日志看的分诊结果。

    `still` 恒 0 是为了不破坏老客户端：它读这个字段做展示，突然没有这个键
    会变成 undefined。真正还会产生静帧的是 `regen_mode="shots"` 那条独立入口。
    """
    n = {"keep": 0, "still": 0, "video": 0}
    for d in disp.values():
        n[d] = n.get(d, 0) + 1
    return n
