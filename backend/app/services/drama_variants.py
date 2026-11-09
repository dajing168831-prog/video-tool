"""变体矩阵（C15）—— 同一批素材，换合成参数出多条不一样的片子，**零生成费**。

出处：竞品 `src/lib/variation-plan.ts:1-115`（防同质化）
  · 为什么要有：文件头 `:8-14` —— 平台会按账号压「结构重复」的产出，
    「连着 5–7 条同一个结构」是**政策级风险**，不是口味问题。
  · 做法：每一条给一份不同的结构组合（钩子机制 / 风格 / 音色 / BGM 情绪 /
    字幕样式 / 时长抖动），用**确定性 PRNG**（mulberry32 `:55-65`）从不同起点
    轮转，相邻两条几乎每个维度都不同（`:84-113`）。
  · 用户锁死的维度不覆盖（`:86` `styleLocked`）—— 只轮转没锁的。

我们的差异（行对齐能力表 C15「同素材只重跑合成」）：
  · 竞品轮的是**生成阶段**的维度（钩子/风格/音色/时长），每换一条都要重新生成、要花钱；
    我们的 `film/render` 出片由主人点，变体矩阵**不能碰生成**。
  · 所以这里轮的是**合成阶段**能改且免费的四个维度：转场 / 字幕样式 / 渲染档 / BGM 开关。
    它们正是竞品 `variation-plan.ts` 里 BGM 与字幕两维的下沉版，目的同样是「别让一批
    片子长得一模一样」。
  · 渲染不重写：直接复用 `drama_compose` 的合成链路（同一份 ffmpeg 代码），只是换配置多跑几遍。
"""
from __future__ import annotations

from app.services import drama_captions, drama_compose

#: 转场只放**本地能做**的两档（`drama_compose.TRANSITIONS` 里 local=True 的那两个；
#: AI 转场要重出片段 = 花钱，变体矩阵不碰）
TRANSITION_POOL = ("direct_concat", "ffmpeg_fade")
#: 字幕：四档预设 + 关掉（竞品 `variation-plan.ts:108` 的 karaoke 轮换是同一用意）
CAPTION_POOL = tuple(drama_captions.ids()) + ("off",)
#: 渲染三档（`drama_compose.RENDER_PRESETS`）
RENDER_POOL = ("fast", "standard", "hd")
#: BGM 开关：有曲子才轮；没曲子这一维恒为关
BGM_POOL = (True, False)

#: 一次最多出几条（每条都要跑一遍 ffmpeg，别让人一次点出 20 条）
MAX_VARIANTS = 6


def mulberry32(seed: int):
    """竞品 `variation-plan.ts:55-65`（mulberry32，确定性小 PRNG）。"""
    a = int(seed) & 0xFFFFFFFF

    def nxt() -> float:
        nonlocal a
        a = (a + 0x6D2B79F5) & 0xFFFFFFFF
        t = a
        t = ((t ^ (t >> 15)) * (1 | t)) & 0xFFFFFFFF
        t = (t + (((t ^ (t >> 7)) * (61 | t)) & 0xFFFFFFFF)) & 0xFFFFFFFF
        t = t ^ (t >> 14)
        return (t & 0xFFFFFFFF) / 4294967296.0

    return nxt


def _label_caption(pid: str) -> str:
    if pid == "off":
        return "无字幕"
    p = drama_captions.get(pid) or {}
    return str(p.get("label") or p.get("name") or pid)


def describe(slot: dict) -> str:
    """竞品 `:118-133` 的一行摘要（中文）。"""
    cap = slot["config"]
    bits = [
        f"转场:{'淡入淡出' if cap['transition'] == 'ffmpeg_fade' else '直接拼接'}",
        f"字幕:{_label_caption(cap['caption_preset']) if cap['captions'] else '无字幕'}",
        f"渲染:{drama_compose.render_profile(cap['render_preset'])['label']}",
        f"BGM:{'开' if cap['bgm'] else '关'}",
    ]
    return " · ".join(bits)


def build(*, count: int = 3, seed: int = 1, has_bgm: bool = False,
          lock: dict | None = None) -> dict:
    """生成变体计划（纯计算）。

    `lock` = 用户锁死的维度（`transition` / `caption_preset` / `render_preset` / `bgm`），
    锁了的维度所有条目都用这个值，其余维度照竞品做法从随机起点轮转。
    """
    # 注意 count=0 是「一条都不要」的误传，不能当成缺省 3（`0 or 3` 会变 3）
    n = max(1, min(MAX_VARIANTS, int(3 if count is None else count)))
    seed = int(seed or 1)
    lock = dict(lock or {})
    rand = mulberry32(seed)

    caps_pool = CAPTION_POOL
    bgm_pool = BGM_POOL if has_bgm else (False,)
    # 竞品 `:87-91`：每个维度一个随机起点，相邻槽位顺着往下走（步长 1 与池长互质的情形最多）
    start = lambda pool: int(rand() * len(pool)) if pool else 0  # noqa: E731
    starts = {
        "transition": start(TRANSITION_POOL),
        "caption": start(caps_pool),
        "render": start(RENDER_POOL),
        "bgm": start(bgm_pool),
    }

    slots = []
    for i in range(n):
        def pick(pool, key, lock_key=None):
            lk = lock.get(lock_key or key)
            if lk is not None and lk != "" and lk in pool:
                return lk
            return pool[(starts[key] + i) % len(pool)]

        cap = pick(caps_pool, "caption", "caption_preset")
        cfg = {
            "transition": pick(TRANSITION_POOL, "transition"),
            "captions": cap != "off",
            "caption_preset": "standard" if cap == "off" else cap,
            "render_preset": pick(RENDER_POOL, "render", "render_preset"),
            "bgm": pick(bgm_pool, "bgm") if has_bgm else False,
        }
        slot = {"idx": i, "config": cfg}
        slot["summary"] = describe(slot)
        slots.append(slot)

    return {
        "seed": seed,
        "count": n,
        "has_bgm": bool(has_bgm),
        "locked": {k: v for k, v in lock.items() if v not in (None, "")},
        "pools": {
            "transition": list(TRANSITION_POOL),
            "caption": list(caps_pool),
            "render": list(RENDER_POOL),
            "bgm": [True, False] if has_bgm else [False],
        },
        "slots": slots,
    }
