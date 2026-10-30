# -*- coding: utf-8 -*-
"""H3 转换路由 —— 顾客提交什么素材，决定走哪个模式、用哪把尺子。

纯规则，零模型调用、零费用。**它一个字都不改提示词的写法** —— 只负责在动笔之前
把「模式」判死。模式错了后面全废：把两张角色设定图塞进 I2VA，16:9 会被吞成
adaptive、分镜被压、运镜语法坏掉（2026-10-29 实测，lite 6/14、pro 11/14）。

## 官方没有「怎么判模式」的文字，但边界是死的

| # | 事实 | 出处 |
|---|---|---|
| 1 | 0 图 → 文生视频；1 图 → 首帧**或**尾帧；2 图 → 首尾帧 | `h3-readme:84` |
| 2 | 参考入口：图 ≤9、视频 ≤3（单段 2–15s，总 ≤15s）、音频 ≤3（同上）、**混用总文件 ≤12** | `h3-readme:85`；`mm-docs:8271-8276` |
| 3 | **图生视频与多模态参考互斥**：出现 `reference_*` 就不能出现 `first_frame`/`last_frame`，反之亦然 | `api-create:212-214` |
| 4 | `role` 只有五个值；单图且不填 role 时默认按 `first_frame` | 同上 `:449-455` |
| 5 | 图片数量：首帧 ≤1、尾帧 ≤1、参考图 ≤9 | 同上 `:232` |
| 6 | 时长：`MiniMax-H3`/`-Highspeed`/`-Lite` 是 4–15；**`-Max` 是 5–15（不支持 4 秒）** | 同上 `:294-312` |
| 7 | 画幅：文生视频**必填且不能 adaptive**；图生视频（含首尾帧）**恒 adaptive**，传别的会被忽略；参考生视频可选、默认 adaptive，但 **`-Lite` 不支持 adaptive，必须显式指定** | 同上 `:316-337` |
| 8 | 三字段指南覆盖 T2VA / I2VA / FL2VA / L2VA；Ref2VA 另有六段式指南 | `ref-en:7`（"shared with the Video Prompt Writing Guide (T2VA / I2VA / FL2VA / L2VA)"） |

## 两处口径要先说清楚

1. **尺子条数不是草案里写的 B1–B28。** 实测 `ruler_h3_base` 是 **23 条**（编号 B1–B26，
   中间有断号）；`ruler_h3` 是 23 条（E1–E23）。写死条数只会自己骗自己，所以这里
   只记模块名，条数由脚本现读。
2. **「一张图不填 role 就必须问」是我们的产品规矩，不是官方规矩。** 官方说单图不填
   role 默认 `first_frame`（`:451`）。但从顾客角度，「这张图是当第一帧还是当人物参考」
   决定的是走哪个模式，猜错不是效果差一点而是整个模式跑错 —— 所以宁可多问一句。
"""
from __future__ import annotations

from dataclasses import dataclass

#: 官方 `role` 闭集（`api-create:449-455`）。`base_video` 是再生成接口专用，不在转换里。
ROLES = ("first_frame", "last_frame", "reference_image",
         "reference_video", "reference_audio")
FRAME_ROLES = ("first_frame", "last_frame")
REF_ROLES = ("reference_image", "reference_video", "reference_audio")

#: 官方画幅闭集（`api-create:337`）。
RATIOS = ("21:9", "16:9", "4:3", "1:1", "3:4", "9:16")

#: 时长下限按型号分（`api-create:294-312`）。上限都是 15。
VARIANTS = {
    "MiniMax-H3": (4, 15),
    "MiniMax-H3-Highspeed": (4, 15),
    "MiniMax-H3-Lite": (4, 15),
    "MiniMax-H3-Max": (5, 15),
}

#: 两种产出格式 → 各自的尺子。**两把尺子互不引用**（`MODEL-SEPARATION.md`）。
GUIDES = {
    "base": {"fields": 3, "ruler": "ruler_h3_base",
             "name": "三字段（integrated_multimodal_description / "
                     "overall_soundscape / non_diegetic_music）"},
    "ref": {"fields": 6, "ruler": "ruler_h3",
            "name": "六段式（subject_definitions / summary / retention_analysis / "
                    "detailed_description / overall_soundscape / non_diegetic_music）"},
}

#: 官方素材上限（`h3-readme:85`、`mm-docs:8271-8276`、`api-create:232`）。
LIMITS = {
    "first_frame": 1, "last_frame": 1, "reference_image": 9,
    "reference_video": 3, "reference_audio": 3,
    "total_files": 12,          # 混用总文件数
    "video_sec_each": (2, 15),  # 单段
    "video_sec_total": 15,
    "audio_sec_each": (2, 15),
    "audio_sec_total": 15,
}


@dataclass(frozen=True)
class Asset:
    """一样顾客提交的素材。`role` 留空 = 顾客没说清它干什么用。"""
    kind: str                 # image / video / audio
    role: str = ""
    seconds: float = 0.0      # 视频/音频单段时长，图片不看

    def __post_init__(self) -> None:
        if self.kind not in ("image", "video", "audio"):
            raise ValueError(f"素材类型只认 image/video/audio，收到 {self.kind!r}")
        if self.role and self.role not in ROLES:
            raise ValueError(f"role 只认 {ROLES}，收到 {self.role!r}")


def normalize(assets: list[Asset]) -> tuple[list[Asset], list[str]]:
    """把官方只给了一种用法的素材补齐角色。图不补 —— 图的用法要靠问顾客。

    视频/音频在官方只有参考入口收（`api-create:208-209`、`:453-454`），
    所以「顾客传了一段视频」的意思只能是「参考视频」，不用问。
    """
    out: list[Asset] = []
    notes: list[str] = []
    for a in assets:
        if a.role:
            out.append(a)
        elif a.kind == "video":
            out.append(Asset(a.kind, "reference_video", a.seconds))
            notes.append("视频只有参考入口能收，已按「参考视频」处理")
        elif a.kind == "audio":
            out.append(Asset(a.kind, "reference_audio", a.seconds))
            notes.append("音频只有参考入口能收，已按「参考音频」处理")
        else:
            out.append(a)
    return out, notes


def _mode_assets(assets: list[Asset]) -> tuple[list[Asset], list[Asset], list[Asset]]:
    frames, refs, media = [], [], []
    for a in assets:
        if a.role in FRAME_ROLES:
            frames.append(a)
        elif a.role in REF_ROLES:
            refs.append(a)
        if a.kind in ("video", "audio"):
            media.append(a)
    return frames, refs, media


def _check_limits(assets: list[Asset], problems: list[str]) -> None:
    """数量与时长越界。**只报，不替顾客删素材** —— 删哪张是顾客的决定。"""
    seen: dict[str, int] = {}
    for a in assets:
        if a.role:
            seen[a.role] = seen.get(a.role, 0) + 1
    for role, cap in LIMITS.items():
        if role in ("total_files",) or not isinstance(cap, int):
            continue
        n = seen.get(role, 0)
        if n > cap:
            problems.append(f"{role} 传了 {n} 个，官方上限 {cap} 个")

    if len(assets) > LIMITS["total_files"]:
        problems.append(
            f"素材一共 {len(assets)} 个，混用上限 {LIMITS['total_files']} 个"
            "（官方 h3-readme:85）")

    for a in assets:
        if a.kind == "video":
            lo, hi = LIMITS["video_sec_each"]
        elif a.kind == "audio":
            lo, hi = LIMITS["audio_sec_each"]
        else:
            continue
        if a.seconds and not (lo <= a.seconds <= hi):
            problems.append(
                f"{a.kind} 有一段 {a.seconds:g} 秒，官方要求单段 {lo}–{hi} 秒")


def route(assets: list[Asset], *, model: str = "MiniMax-H3") -> dict:
    """判模式。**判不了就不判** —— 返回 `mode=""` 和要问顾客的问题。

    返回：
        mode         t2va / i2va / l2va / fl2va / r2va；判不了是空串
        guide        base / ref
        ruler        ruler_h3_base / ruler_h3（尺子模块名，条数由脚本现读）
        ratio        画幅规矩：必填吗、能不能 adaptive
        duration     (下限, 上限)，按型号
        questions    必须先问顾客才能定模式的问题
        problems     素材本身不合官方规矩，得顾客改
    """
    if model not in VARIANTS:
        raise ValueError(f"型号只认 {tuple(VARIANTS)}，收到 {model!r}")

    lo, hi = VARIANTS[model]
    problems: list[str] = []
    questions: list[str] = []

    assets, notes = normalize(assets)
    frames, refs, media = _mode_assets(assets)
    _check_limits(assets, problems)

    # ① 混用：官方的硬边界（`:212-214`）。不是"建议"，是"不可混用"。
    if frames and (refs or media):
        problems.append(
            "素材里既有首/尾帧又有参考素材，官方明写这两类**不可混用**"
            "（api-create:212-214）—— 要么帧，要么参考，得二选一")

    # ② 没标角色的图：模式判不了，必须问（产品规矩，见文件头第 2 条）
    for a in assets:
        if a.kind == "image" and not a.role:
            questions.append(
                "这张图是当片子的第一帧/最后一帧，还是只当人物、风格、场景的参考？")

    mode = ""
    if problems:
        mode = ""                      # 素材本身不合法，不给模式
    elif questions:
        mode = ""                      # 意图不清，等顾客答
    elif refs or media:
        # 视频/音频只存在于参考入口（`:208-209`），有它们就一定是参考模式
        mode = "r2va"
    elif len(frames) == 2:
        mode = "fl2va"
    elif len(frames) == 1:
        mode = "i2va" if frames[0].role == "first_frame" else "l2va"
    elif not assets:
        mode = "t2va"
    else:
        # 兜底：走到这里说明有组合没覆盖到，宁可让顾客重选，也不猜
        questions.append("这几样素材的组合我判不出该走哪个模式，请确认它们的用途")

    guide = "ref" if mode == "r2va" else "base" if mode else ""
    return {
        "mode": mode,
        "guide": guide,
        "ruler": GUIDES[guide]["ruler"] if guide else "",
        "format": GUIDES[guide]["name"] if guide else "",
        "ratio": _ratio_rule(mode, model),
        "duration": (lo, hi),
        "model": model,
        "limits": dict(LIMITS),
        "questions": questions,
        "problems": problems,
        "notes": notes,
    }


def _ratio_rule(mode: str, model: str) -> dict:
    """画幅规矩按模式分（`api-create:316-337`）。返回给人看的一句话 + 机器可用的字段。"""
    if mode == "t2va":
        return {"required": True, "adaptive": False, "allowed": list(RATIOS),
                "note": "文生视频必填画幅，且不能用 adaptive"}
    if mode in ("i2va", "l2va", "fl2va"):
        return {"required": False, "adaptive": True, "allowed": ["adaptive"],
                "note": "图生视频的画幅由输入图决定，恒为 adaptive，填别的会被忽略"}
    if mode == "r2va":
        if model == "MiniMax-H3-Lite":
            return {"required": True, "adaptive": False, "allowed": list(RATIOS),
                    "note": "参考生视频默认 adaptive，但 H3-Lite 不支持 adaptive，必须显式指定"}
        return {"required": False, "adaptive": True,
                "allowed": ["adaptive", *RATIOS],
                "note": "参考生视频画幅可选，默认 adaptive，也可以显式指定"}
    return {"required": False, "adaptive": True, "allowed": list(RATIOS),
            "note": "模式还没定，画幅规矩定不下来"}
