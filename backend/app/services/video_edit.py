"""整片换主体（1:1 复刻）—— 双通道调度。

和 generate.py 的区别，一句话：

    generate.py  = 抽一帧 → 重画 → 图生视频。**动作只有首帧那一瞬**，
                   大动作的镜头做不出来，所以只能按比例挑镜头、其余保留原片。
    video_edit.py= 整段原片当参考/编辑对象，模型逐帧对着原片重画。
                   **动作、运镜、节奏、时长都跟原片走**，这才是 1:1。

两个通道，同一套接口，按素材自动选：

    火山 Seedance 2.5 (edit)   单段 4–30s，保真度最高，但**不收含真人人脸的参考视频**
    MiniMax H3 (ref2va)        单段 4–15s，原生带音轨，文档未禁真人脸

分段规则：**按原片的镜头切换点切**，不按固定秒数硬切。
这样拼接的接缝正好落在原片本来就有的切换上，看不出来多了一刀。
"""
from __future__ import annotations

import hashlib
import json
import math
import logging
import os
import re
import shutil
from pathlib import Path

from app.services import assemble, clone_store, error_report, models, scene
from app.services.media import ffmpeg_path

log = logging.getLogger(__name__)

# 单段上限不再写死：实际值查 `model_specs`（2.0 系列 15s / 2.5 30s / H3 15s）。
# 写死过 30s，换成 2.0 就会切出模型不收的段。


def _plan_adapter(plan: dict):
    """按 plan 里的型号/通道取适配器（出片流水线用）。"""
    return models.adapter_for(model=plan.get("model") or "",
                              channel=plan.get("ch") or "")


def _model_for(ch: str, model: str = "") -> str:
    """本次实际用哪个型号：界面选了就听界面的，没选才回落到配置默认。

    🩸 2026-10-26 L3：型号归属**问注册表**，核心不认识 `doubao` 这类前缀。
    型号必须和实际通道同族：界面选「自动通道」时，通道可能被素材类型改判，
    这时用户选的 MiniMax 型号就不能原样发给火山 —— 那是直接 400。
    """
    from app.core.config import settings
    from app.services import models

    m = (model or "").strip()
    if m:
        # 🩸 2026-10-31：2.0 的适配器已随复刻视频下架归档、不再注册 ⇒
        #   老前端/缓存传 2.0 的 ID 时 `family_of_model()` 认不出来，
        #   自然落到下面「不属于该通道」的分支，回落到 2.5。
        if models.family_of_model(m) == models.family_of(model="", channel=ch):
            return m
        log.warning("型号 %s 不属于通道 %s，改用该通道的默认型号", m, ch)
    # 🩸 没指定型号 = 用**配置里那条**，不是注册表里写死的兜底 ——
    # 生产的默认型号由 `VT_ARK_VIDEO_EDIT_MODEL` 决定，换型号不该改代码。
    ad = models.adapter_for(model="", channel=ch)
    return getattr(settings, ad.caps.default_model_setting, "") or ad.model_id


def _volc_hint(msg: str) -> str:
    """把火山的审核报错翻成「下一步点哪里」。

    🩸 必须按**错误码前缀**分，不能只看 PolicyViolation 四个字：
      InputVideo…PolicyViolation   输入视频被判可能涉及版权 → 换**输入**（参考片/参考图）
      OutputVideo…PolicyViolation  生成出来的视频被判可能涉及版权 → 官方原话是
                                   「请更换输入内容后重试」，换通道**不保证**解决
      …PrivacyInformation         输入视频含真人 → 换素材来源（asset://）
    官方错误码表（2026-10-21 存档 `doc_1299023.md:32/34`）里这两条是分开的两行。
    """
    low = msg.lower()
    # 🩸 2026-10-28 实测（任务 `cgt-20261028030449-2g9km`，
    #   `doubao-seedance-2-0-mini-260615` 编辑任务）：火山还有第三条码
    #   `OutputAudioSensitiveContentDetected.PolicyViolation` —— 判的是**模型
    #   生成出来的那条音轨**。以前它落进下面「泛 policyviolation」兜底，
    #   被说成「参考视频被判版权（InputVideo…）」并劝用户换素材/换通道，
    #   三条建议全是错的方向。
    #   · 为什么会有生成音轨：2.0 编辑任务为了对口型默认 `generate_audio=True`
    #     （`models/volc20.py:119` 的说明）；
    #   · 但它**不进成片**：合成时 `assemble._norm` 用 `-an` 丢掉模型音轨、
    #     换成自己的配音 ⇒ 这条错误只影响口型，不影响成片声音。
    if "outputaudiosensitivecontentdetected" in low:
        return (
            "｜注意：火山判的是**模型生成出来的那条音轨**可能涉及版权"
            "（OutputAudioSensitiveContentDetected.PolicyViolation），"
            "不是参考片、也不是画面。我们合成时本来就把模型音轨整条丢掉、"
            "换成自己的配音，所以成片的声音不受影响，这条只影响口型："
            "① 直接重试一次（生成内容有随机性，多数能过）；"
            "② 反复撞就关掉这几段的音频生成（`generate_audio=False`），口型会退化。"
        )
    if "outputvideosensitivecontentdetected" in low:
        if "copyright" in low or "policyviolation" in low:
            return (
                "｜注意：火山判的是**生成出来的这段视频**可能涉及版权"
                "（OutputVideoSensitiveContentDetected.PolicyViolation），不是参考片。"
                "官方给的解法是「更换输入内容后重试」，换通道只是换个审核口径、不保证过。"
                "可以试：① 改这一镜的提示词/参考图；② 这一镜改静帧或保留原片；"
                "③ 换通道/换型号再试一次。"
            )
        return (
            "｜火山判的是**生成出来的这段视频**可能含敏感信息"
            "（OutputVideoSensitiveContentDetected），官方建议更换输入内容后重试："
            "① 改这一镜的提示词/参考图；② 这一镜改静帧或保留原片。"
        )
    if "policyviolation" in low or "copyright" in low:
        return (
            "｜火山把这段参考视频判成「可能涉及版权」（InputVideoSensitiveContentDetected"
            ".PolicyViolation）。拿别人的成片当参考，火山这条路走不通，换输入才行："
            "① 通道改「MiniMax」，它收参考视频的口径跟火山不同，同一条片子可以先试；"
            "② 换画面方式改「逐镜分诊」，静态镜只喂一帧、不喂视频（动作镜仍会撞同一条规则）；"
            "③ 这一镜别改，保留原片。"
        )
    if ("privacyinformation" in low or "real person" in low
            or "真人" in msg or "人脸" in msg):
        return (
            "｜火山不收含真人人脸的参考素材。三条合规做法："
            "① 预置虚拟人像库的 asset://<id>；"
            "② 本人扫码授权、录入真人形象素材后拿 asset://<id>；"
            "③ 用本账号近 30 天由 Seedance/Seedream 生成的含人脸原始产物。"
            "或者把通道改成「MiniMax」。"
        )
    # 🩸 2026-10-25：只剩**不带后缀**的 `InputVideoSensitiveContentDetected`
    # （官方原话 "may contain sensitive information"，不说版权、不说真人）。
    # 以前这条落到 `return ""` → 界面上是一坨原始 JSON，主人只能猜。
    # 实测样本：`861efd72` 那条抖音双人舞蹈，`content[1]` = 我们切给模型的
    # **参考视频**（那段本身已经 `-an` 无音轨）⇒ 触发物在**画面**，不是音轨版权。
    # 这条是"任务创建阶段就被拒"：模型一次都没跑，改提示词不会有任何帮助。
    if "inputvideosensitivecontentdetected" in low:
        return (
            "｜火山在**创建任务时**就把这段参考视频判成「可能含敏感信息」"
            "（InputVideoSensitiveContentDetected，既不是版权、也不是真人脸），"
            "模型一次都没跑 —— **改提示词没有用**。能做的："
            "① 换一条内容更保守的原片；"
            "② 通道改「MiniMax」，审核口径不同，同一条片子可以先试；"
            "③ 这一镜改「保留原片」，只处理别的镜头。"
        )
    return ""


def _spec_for(ch: str, model: str = "") -> dict:
    """这次用的型号参数表 —— 问注册表要，核心不认识是哪一家。"""
    return models.adapter_for(model=model, channel=ch).specs_for(model)


def spec_label(ch: str, model: str = "") -> str:
    """给人看的型号名（结果页用）。认不出来就退回原始 model id。"""
    return _spec_for(ch, model).get("label") or model


def _resolution_for(ch: str, spec: dict, height: int, model: str = "",
                    width: int = 0) -> str:
    """清晰度按**具体型号**收口，不是按通道。

    2.0 Mini / 极速只有 480p/720p，H3-Max 只有 480P/768P；
    认不出来就退回该型号的默认档。
    """
    from app.services import edit_spec

    ms = _spec_for(ch, _model_for(ch, model))
    # 默认档怎么来，由这家自己声明（火山按原片画幅推；H3 用固定档）
    _ad = models.adapter_for(model=model, channel=ch)
    auto = (_ark_res(height, width) if _ad.caps.auto_res_from_frame
            else ms["default_resolution"])
    res = edit_spec.resolution_for(ch, spec, auto=auto)
    if res not in ms["resolutions"]:
        # 退到"该型号收得下的最高一档"，不是无条件退默认档。
        # 以前 2.5 选 4k 会掉到 720p（默认档），比用户要的矮两档。
        res = _nearest_res(ms["resolutions"], res)
        log.warning("%s 不收该档，改用最接近的 %s", ms["label"], res)
    return res


# 档位排序只用于"要的这一档型号不收时退哪一档"
_RES_RANK = {"480p": 480, "480P": 480, "720p": 720, "768P": 768,
             "1080p": 1080, "2K": 1440, "4k": 2160}


def _nearest_res(supported, want: str) -> str:
    """在型号支持的档位里，取**不超过**想要档位的最高一档；都不够低就取最低档。"""
    items = [(r, _RES_RANK.get(r, 0)) for r in supported]
    w = _RES_RANK.get(want, 0)
    below = [x for x in items if x[1] <= w]
    if below:
        return max(below, key=lambda x: x[1])[0]
    return min(items, key=lambda x: x[1])[0]


def _limit_for(ch: str, model: str = "") -> float:
    """单段上限按**具体型号**取，不按通道写死。

    2.0 系列（含 Mini / 极速）是 15s，只有 2.5 给到 30s；H3 也是 15s。
    写死 30 会让 2.0 的请求被模型直接拒掉。
    """
    return _spec_for(ch, _model_for(ch, model))["max_sec"]


def _min_for(ch: str, model: str = "") -> float:
    """单段下限同样按型号取：H3 收 4s，H3-Max 官方 5~15s，写死 4 会被拒。"""
    return _spec_for(ch, _model_for(ch, model))["min_sec"]


def _gen_duration(dur: float, model: str = "") -> int:
    """生成时长按**具体型号**收口（整数秒）。

    🩸 以前这里写死 `_min_for("minimax", …)`：只要调用它的那家换了，
    时长就会被 MiniMax 的区间收口。现在按型号问注册表，谁调就收谁的口径。
    """
    spec = models.adapter_for(model=model).specs_for(model)
    lo = int(spec["min_sec"])
    hi = int(spec["max_sec"])
    return int(max(lo, min(hi, math.ceil(dur))))


# 默认下限（认不出通道时用）。真正取值走 `_min_for(ch)`。
MIN_SEC = 4.0


class EditError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# 通道选择


def _volc_ready() -> bool:
    """火山要两样：key + 一个公网能拉到的地址（OSS 或本服务的签名链接）。"""
    from app.core.config import settings
    from app.services import oss

    if not (settings.ark_api_key or "").strip():
        return False
    return oss.available() or bool((settings.public_base_url or "").strip())


def _require_ready(ad, *, explicit: bool = False) -> None:
    """这条通道没配好就抛 —— 具体缺什么由**这家自己**说（`ready_error`）。"""
    if ad.ready():
        return
    raise EditError(ad.ready_error() or f"{ad.family} 通道未配置")


def pick_channel(requested: str = "auto", *, subject_kind: str = "none") -> str:
    """auto 的规则，写死在这里，别让上游各猜各的。

    subject_kind 决定首选哪条：
      - "asset"：用户给的是 `asset://` 素材 ID（虚拟人像库 / 已授权真人素材）。
        这正是火山给真人脸留的合规口子，所以**优先火山**。
      - "file" ：用户传的本地图片。多半是真人照片，火山不收，**优先 MiniMax**；
                 如果这张图不是真人（动漫/产品/动物），火山其实也能收，
                 用户可以手动强制走火山。
      - "none" ：没给图，**优先火山**（单段 30s、保真更好）。

    首选那条没配好就降级另一条；两条都没有就报错。
    """
    from app.services import models

    ads = models.adapters_by_family()
    req = (requested or "auto").strip().lower()
    if req in ads:
        _require_ready(ads[req], explicit=True)
        return req

    # `auto`：哪条先试由各家自己声明（`Caps.auto_prefer`），核心不写先后。
    order = sorted(ads, key=lambda f: ads[f].caps.auto_prefer.get(subject_kind, 99))
    for fam in order:
        if ads[fam].ready():
            return fam
    raise EditError(
        "换画面通道都没配好：" + "；".join(
            f"{fam} → {ads[fam].ready_error() or '缺凭据'}" for fam in order))


# ---------------------------------------------------------------------------
# 切段


def plan_chunks(shots: list[dict], total: float, limit: float,
                min_sec: float = MIN_SEC) -> list[tuple[float, float]]:
    """按镜头边界把片子切成长度不超过 limit 的若干段。

    不按固定秒数切：接缝落在镜头中间会多出一刀，落在原片的切换点上才看不出来。
    单个镜头本身就超长（长镜头）时才均分它 —— 这是唯一会凭空多刀的情况。
    """
    spans: list[tuple[float, float]] = []
    cur_s, cur_e = None, None
    for s in shots or []:
        a, b = float(s["start"]), float(s["end"])
        if b - a <= 0:
            continue
        if cur_s is None:
            cur_s, cur_e = a, b
            continue
        if b - cur_s <= limit:
            cur_e = b
        else:
            spans.append((cur_s, cur_e))
            cur_s, cur_e = a, b
    if cur_s is not None:
        spans.append((cur_s, cur_e))
    if not spans and total > 0:
        spans = [(0.0, min(total, limit))]

    # 单段超长 → 均分；末尾过短 → 并进前一段（不足模型下限就不接）
    out: list[tuple[float, float]] = []
    for a, b in spans:
        while b - a > limit:
            out.append((a, a + limit))
            a += limit
        out.append((a, b))
    merged: list[tuple[float, float]] = []
    for a, b in out:
        if merged and (b - a) < min_sec and (b - merged[-1][0]) <= limit:
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    return merged


def bounds_for(ch: str, model: str = "") -> tuple[float, float]:
    """该通道 + 型号收的单段区间（秒）。越界不是"效果差一点"，是请求直接被拒。"""
    return _min_for(ch, model), _limit_for(ch, model)


def snap_int_spans(
    spans: list[tuple[float, float]], *,
    min_sec: float = MIN_SEC, max_sec: float = 15.0,
) -> tuple[list[tuple[float, float]], bool]:
    """把段边界吸附到**整数秒** —— 只给 2.0 用。

    🩸 为什么必须整数：官方 2.0 `sd2-pe/references/trouble.md:325-331`（A-4
    「人物口型对不上」）的解法第二条是「生成视频的长度跟输入视频**严格一致**」。
    2.0 的输出时长只能是整数秒（`sd20.md:119`），输入段只要不是整数，模型就
    必然自己分配那点余量：实测 8.52s 的段发 `ceil`=9（多 0.48s）、9.513s 的段
    多 0.55s。口型就是在这里飘的 —— `D:/tmp/lip_drift_measure.py` 量出段 2
    滞后 −870ms、包络相关只有 0.244（是**节奏不同**，不是整体平移，事后挪
    音轨救不回来）。

    做法：内部切点四舍五入到整数秒、末端贴住整片的整数结尾，每段仍落在
    `[min_sec, max_sec]`。返回 `(新区间, 是否改动过)`。排不下就原样返回，
    交给调用方按原有规则报错 —— 这里**不猜**，也不偷偷改段数。

    ⚠️ 只改切点位置，不改"切几段"（除非末段短到只能并进前一段）。
    """
    pts = [(float(a), float(b)) for a, b in (spans or [])]
    if not pts:
        return [], False
    n = len(pts)
    lo_seg, hi_seg = int(min_sec), int(max_sec)
    start = int(round(pts[0][0]))
    # 末端取整片的整数结尾：2.0 不给非整数秒，多出来的 <1s 尾巴丢掉。
    end = int(math.floor(pts[-1][1] + 1e-6))
    if n == 1 or end - start < lo_seg:
        return pts, False
    cuts = [start]
    for i in range(1, n):
        want = int(round(pts[i][0]))
        rest = n - 1 - i                     # 这一刀后面还要分出几段
        lo = cuts[-1] + lo_seg
        hi = min(cuts[-1] + hi_seg, end - rest * lo_seg)
        if lo > hi:
            return pts, False                # 这个段的数排不下：原样交回
        cuts.append(min(max(want, lo), hi))
    cuts.append(end)
    # 末段短于下限：先把最后一刀往前挪（前段变长），挪不动就把末段并进前一段
    while len(cuts) >= 3 and cuts[-1] - cuts[-2] < lo_seg:
        moved = cuts[-1] - lo_seg
        if moved > cuts[-3] and moved - cuts[-3] <= hi_seg:
            cuts[-2] = moved
        elif cuts[-1] - cuts[-3] <= hi_seg:
            del cuts[-2]
        else:
            return pts, False
    if cuts[-1] - cuts[-2] < lo_seg:
        return pts, False
    out = [(float(cuts[i]), float(cuts[i + 1])) for i in range(len(cuts) - 1)]
    changed = (len(out) != n or any(
        abs(x[0] - y[0]) > 1e-6 or abs(x[1] - y[1]) > 1e-6
        for x, y in zip(pts, out)))
    return out, changed


def sd20_request_shape(*, videos: int, audios: int, images: int,
                       dur: float, prompt: str) -> tuple[bool, str, list[str]]:
    """一段 2.0 请求的**形状**：`(能不能发, 形状签名, 拦下来的理由)`。

    🩸 2026-10-31 第 1 步（主人批准）：一条复刻里，每一次生成请求的形状只有一种
    —— `1 张人物图 + 1 段原片 + 1 条音频 + 1 句提示词 + 整数时长`。
    出处不是我想的，是代码里那条实测记录：`_gen_spans` 里写死边界帧那段注释
    「`文字 + 1 条参考视频 + 1 张参考图` 是目前**唯一实测跑通过**的形状
    （2026-10-21 11:07，chunk_001 成功）」；加上官方 A-4 对时长严格一致的要求。

    这里**硬拦**的四项（都是"形状根本没被验证过"，不是效果好坏）：
      · 视频不是恰好 1 段编辑母版（多一段风格视频就是没验过的第二种形状）
      · 音频**超过** 1 条（母版自带音轨算 1 条，独立 `reference_audio` 也算 1 条）。
        0 条不拦：没拿到配音轨时提示词已经按"无音频"重编译，那是**已有的退化
        路径**（`test_whole_wiring.py` 第 312 行保护着它），不该被形状闸改掉。
      · 段长不是整数秒 / 不在 4–15 秒
      · 提示词为空（官方：2.0 靠提示词判定任务类型）
    参考图张数只**登记**不拦截：`1 张`是"换人"这一种模式的已验证形状，
    换背景/换产品/多人各有自己的槽位，不能拿换人的结论去砍它们。
    等这些模式各自实测过，再把它们的基线写进来。
    """
    bad: list[str] = []
    if videos != 1:
        bad.append(f"参考视频 {videos} 段（唯一形状是 1 段编辑母版；"
                   "风格参考请改用「风格参考图」槽位）")
    if audios > 1:
        bad.append(f"音频 {audios} 条（唯一形状最多 1 条：母版自带音轨，"
                   "或独立 reference_audio，二选一）")
    if abs(dur - round(dur)) > 1e-6:
        bad.append(f"段长 {dur:.3f}s 不是整数秒"
                   "（官方 A-4：生成长度要与输入严格一致）")
    if not (4 - 1e-6 <= dur <= 15 + 1e-6):
        bad.append(f"段长 {dur:.3f}s 不在 2.0 收的 4–15 秒")
    if not (prompt or "").strip():
        bad.append("提示词为空")
    sig = (f"1v+{images}i+{audios}a+{int(round(dur))}s"
           if abs(dur - round(dur)) < 1e-6 else f"1v+{images}i+{audios}a+{dur:.2f}s")
    return (not bad), sig, bad


def snap_for_plan(plan: dict, spans: list[tuple[float, float]], *,
                  min_sec: float | None = None,
                  max_sec: float | None = None) -> list[tuple[float, float]]:
    """这一单要不要把段边界吸到整数秒 —— **预览和出片唯一的入口**。

    🩸 2026-10-31（补）：第一条入口只改在 `plan_spans`（整片重制），漏了
    "逐镜分诊"（`clone_pipeline._auto_decision`）—— 那条自己算 spans，预览于是
    还显示 8.520s，而 `_gen_spans` 发请求时已经吸成 9s。**预览报的和实际送的
    对不上**，正好违反那条"预览和真跑共用一份决策"。
    ⇒ 凡是要产出"要送给模型的时间段"的地方，一律过这个函数，别各调各的。
    """
    ad = _plan_adapter(plan)
    if not ad.caps.int_output_sec:
        return spans
    lo = _min_for(plan.get("ch") or "", plan.get("model") or "") \
        if min_sec is None else min_sec
    hi = _limit_for(plan.get("ch") or "", plan.get("model") or "") \
        if max_sec is None else max_sec
    out, changed = snap_int_spans(spans, min_sec=lo, max_sec=hi)
    if changed:
        log.info("段边界吸附到整数秒（该型号输出只能整数秒）：%s",
                 "、".join(f"{a:.0f}–{b:.0f}s" for a, b in out))
    return out


# 风格参考视频（A9）：每段截多长送进去。
# 官方三家都要求**单段参考视频 ≥2s**；3s 够模型读出调性，又给母版留出余量。
STYLE_CLIP_SEC = 3.0
STYLE_CLIP_MIN_SEC = 2.0
# 贴着总时长上限不放：本机实测 `-c copy` 切「2.0 秒」实际出来 2.067 秒
# （关键帧对齐），平台按**实际时长**校验 → 13.0 + 2.0 = 15.0 这种刚好卡线的
# 组合随时会被判超限。留 0.1 秒余量，宁可少截一帧。
STYLE_TOTAL_MARGIN = 0.1


def style_video_budget(ch: str, model: str,
                       spans) -> tuple[float, str]:
    """风格参考视频每段能截多长：`(clip_sec, 拦下的话)`；拦住时 clip=0。

    硬约束是**参考视频总时长**（一次请求里所有视频加起来）：
      · Seedance 2.0 系列 ≤15s（`seedance-20-guide.md:987`）
      · Seedance 2.5    ≤30s（`seedance-25-guide.md:117`）
      · MiniMax H3      ≤15s（`mm-docs:8273`）
    而这一单里的母版片段本身就是参考视频，每段 4–15s（2.5 可到 30s）——
    ⇒ 2.0 / H3 要求每段 ≤12s 才放得下 2 秒的风格片段（2.5 ≤27s）。
    放不下就**一次都别发**：跑到第 4 段才被接口拒掉，前三段的钱已经花了。
    """
    from app.services import model_specs

    ms = _spec_for(ch, model)
    cap = float(ms.get("ref_video_total_sec") or 15.0)
    longest = max((float(b) - float(a) for a, b in (spans or [])), default=0.0)
    clip = min(STYLE_CLIP_SEC, cap - longest - STYLE_TOTAL_MARGIN)
    if clip < STYLE_CLIP_MIN_SEC:
        return 0.0, (
            f"{model} 的参考视频总时长上限是 {cap:.0f} 秒（官方口径），"
            f"这段原片最长的一段就占了 {longest:.1f} 秒，"
            f"再放风格片段就超了（风格片段最少 {STYLE_CLIP_MIN_SEC:.0f} 秒）。"
            "改用「风格参考图」，或换成 Seedance 2.5（上限 30 秒）。")
    return clip, ""


def fit_spans(spans: list[tuple[float, float]], limit: float,
              min_sec: float = MIN_SEC) -> list[tuple[float, float]]:
    """把区间调到模型真正收的范围 `[min_sec, limit]`。

    🩸 官方硬门槛（2026-10-21 抓自创建任务 API）：
       Seedance 2.5 编辑任务：待编辑视频 **4–30s**
       Seedance 2.0 系列：单个参考视频 2–15s（这里统一按 4s 收口）
       MiniMax：单个参考视频 2–15s
    自动分诊按镜头切出来的**尾巴**经常只有 1–2 秒，不处理就等于提交一次被拒一次。

    做法只有两种：往空档里撑，或者从邻段借 —— 借的前提是邻段借完还够 min_sec。
    实在凑不出来（整条片子都比下限短）就原样返回，让调用方报错，别假装成功。
    """
    if not spans:
        return []
    pts = [[float(a), float(b)] for a, b in spans if float(b) - float(a) > 0.05]
    if not pts:
        return []

    # ① 超长的先按上限切（长镜头/整片重制会碰到）
    cut: list[list[float]] = []
    for a, b in pts:
        while b - a > limit:
            cut.append([a, a + limit])
            a += limit
        cut.append([a, b])
    pts = cut

    strong = min_sec - 1e-6
    for _ in range(3):
        # ② 非末段太短：先吃两段之间的空档，不够再向后一段借
        for i in range(len(pts) - 1):
            a, b = pts[i]
            if b - a >= strong:
                continue
            need = min_sec - (b - a)
            na, nb = pts[i + 1]
            gap = max(0.0, na - b)
            if gap > 0:
                take = min(need, gap)
                b += take
                need -= take
            if need > 0:
                give = max(0.0, (nb - na) - min_sec)
                take = min(need, give)
                b += take
                pts[i + 1][0] = na + take
            pts[i][1] = b
        # ③ 末段太短：能整段并进前一段就并，否则吃掉空档 + 从前一段末尾借
        if len(pts) > 1 and pts[-1][1] - pts[-1][0] < strong:
            a, b = pts[-1]
            pa, pb = pts[-2]
            if b - pa <= limit:
                pts[-2][1] = b
                pts.pop()
            else:
                need = min_sec - (b - a)
                gap = max(0.0, a - pb)
                take = min(need, gap)
                a -= take
                need -= take
                if need > 0:
                    give = max(0.0, (pb - pa) - min_sec)
                    take = min(need, give)
                    a -= take
                    need -= take
                    pts[-2][1] = a
                pts[-1][0] = a
        # ④ 首段太短（整片只比下限多一点）：并进第二段
        if len(pts) > 1 and pts[0][1] - pts[0][0] < strong:
            if pts[1][1] - pts[0][0] <= limit:
                pts[1][0] = pts[0][0]
                pts.pop(0)
        if all(strong <= b - a <= limit + 1e-6 for a, b in pts):
            break

    bad = [(round(a, 2), round(b, 2)) for a, b in pts
           if not (strong <= b - a <= limit + 1e-6)]
    if bad:
        log.warning("这些区间仍不满足 [%s, %s] 秒，接口可能拒：%s", min_sec, limit, bad)
    return [(round(a, 3), round(b, 3)) for a, b in pts]


def split_longest(spans: list[tuple[float, float]], limit: float,
                  min_sec: float = MIN_SEC) -> list[tuple[float, float]]:
    """段长超过通道上限时再切一刀（火山 30s 的片子换到 MiniMax 15s 时会用到）。"""
    out: list[tuple[float, float]] = []
    for a, b in spans:
        while b - a > limit:
            out.append((a, a + limit))
            a += limit
        if b - a >= min_sec:
            out.append((a, b))
        elif out:
            out[-1] = (out[-1][0], b)
        elif b > a:
            out.append((a, b))
    return out


# ---------------------------------------------------------------------------
# 提示词：两家语法不同，各按各的标准写


def build_prompt(channel: str, user_prompt: str, *, subject_kind: str = "none") -> str:
    """把用户写的一句话，包成该通道认的语法。

    统一交给 `edit_spec.compile_prompt` —— 提示词规则只留一处，
    别在这种"老调用方"里再维护第二套标号和范围句（多人物就是栽在这里）。
    """
    from app.services import edit_spec

    p = (user_prompt or "").strip()
    spec = edit_spec.normalize({
        "person": subject_kind in ("asset", "file"),
        # 老调用方没有声音信息：按"保留原声"处理，免得凭空写一句改口型的指令
        "audio": "original",
        "extra": p,
    })
    return edit_spec.compile_prompt(channel, spec)


# 🩸 E6（2026-10-23）：`boundary_clause()` 已删除。
# 它给 2.0 追加的「与@图片N（上一段成片的最后一帧）…保持一致」出处是第三方 hypit，
# `sd2-pe` 全文没有这句；而且它**永远发不出去**（2.0 根本带不了边界帧，2.5/H3
# 各有官方写法）。详见 `_gen_spans` 里的说明与 `D:/tmp/h3run3/probe_e6.py`。


def _audio_track(spec: dict, video: Path, workdir: Path) -> Path | None:
    """口型参考该跟哪条音轨走。

    🩸 **2.0 / 2.5 / H3 三家**：三种声音模式都要喂（2026-10-23 主人拍板）
      · `tts` / `mix` → 喂我们自己合成的配音轨；
      · `original`    → 喂**原片整条音轨**（先抽出来落盘，再按段切给模型）。
    火山的编辑任务同样收 `reference_audio`，见 `volc-api:35`「参考音频
    （0-3 个）…支持…编辑视频」与 `sd20.md:550`「提供待编辑的视频、参考图片或音频」。
    以前 `original` 是 `return None`：模型只拿到静音的参考视频，提示词却写着
    「保持原片那套说话表演」—— 它没有任何可跟的东西，只能不张嘴。实测两条成片
    （28s / 30s）全程不对口型，见 docs/CLONE-VERIFY.md「口型」一节。

    ⚠️ 已知取舍：原声是整条混音（人声+音乐+环境声），不是干净的音色样本；
    官方两家的 音频参考 都写的是"音色/台词"，所以这是**为了拿到台词与口型时序**
    才把它当参考喂进去的，不是当音色样本用。

    ⚠️ 这里**不要**再写"原声音轨会撞 PolicyViolation" —— 那条因果没被证实过
    （§十九 已更正：第一次拦截是画面里的真人，且当时的"对照"换了通道）。

    配音轨（workdir/voice.wav）是在**原片时间轴**上按 atempo 归一的，
    视频侧不做重定时，所以同一个 [a,b] 区间在两条轴上指的是同一句话。
    """
    mode = (spec.get("audio") or "tts").strip().lower()
    if mode == "original":
        # 原声模式：把**原片整条音轨**提出来，之后按段切给模型当口型参考。
        # 🩸 以前这里直接 return None。后果：模型只拿到一段**无声的参考视频**，
        # 提示词却写着「The speech performance in <Video 1> is preserved」——
        # 它没有任何可跟的东西，只能不张嘴。实测两条成片（28s / 30s）人物全程
        # 不对口型。见 docs/CLONE-VERIFY.md「口型」一节。
        from app.services import scene

        wd = Path(workdir)
        dest = wd / "source_voice.wav"
        if dest.exists() and dest.stat().st_size > 0:
            return dest
        try:
            total = float(scene.probe(video).get("duration") or 0.0)
            if total <= 0:
                return None
            scene.cut_audio(video, 0.0, total, dest)
            if dest.exists() and dest.stat().st_size > 0:
                log.info("原声模式：已提取原片音轨 %.1fs 作为口型参考", total)
                return dest
        except Exception as e:  # noqa: BLE001
            log.warning("原片音轨提取失败，本段不喂音频：%s", e)
        return None
    # 🩸 配音轨在**出片目录**（clone_pipeline 写的 workdir/voice.wav），
    # 而 replace_whole 会把渲染物放进 workdir/whole/ —— 所以这里必须往上找一层，
    # 只看传进来的 workdir 会永远找不到（口型就白白退化成"不许写 <Audio 1>"）。
    wd = Path(workdir)
    for cand in (wd / "voice.wav", wd.parent / "voice.wav"):
        if cand.exists():
            return cand
    return None


def _seg_key(ch: str, phash: str, a: float, b: float, *, bf_mark: str = "",
             au_mark: str = "", audio_sig: str = "", who: str = "",
             ir_mark: str = "") -> str:
    """一段产物的输入指纹（缓存的唯一判据）。

    形状：`<通道>:<提示词哈希>:<起-止>[`:bf`][`:na`][`:<配音哈希>`][`:<换谁>`]`
      · `bf`   这一段带了上一段的尾帧（提示词里也加了对应那句）
      · `na`   这一段没喂音轨
      · 配音哈希  口型跟着这条配音走 —— 改一句词就得换键（见 `_gen_spans`）
      · 换谁   同一条片子换主角重跑，区间和提示词都可能没变，但人换了

    🩸 时间段固定在**第 3 段**：`work._parse_manifest_key` 靠形状找它，
    尾部这些可选标记随便加减都不影响解析。以前按"倒数第二段"取，一带标记就丢段。
    """
    return f"{ch}:{phash}:{a:.2f}-{b:.2f}{bf_mark}{au_mark}{audio_sig}{who}{ir_mark}"


def _seg_audio(track: Path | None, a: float, b: float, dest: Path) -> Path | None:
    """截这一段的音轨。拿不到、或者长度不在 [2,15]s 就不给 —— 硬塞会被接口拒掉。"""
    from app.services import scene

    if track is None:
        return None
    try:
        total = float(scene.probe(track).get("duration") or 0.0)
    except Exception as e:  # noqa: BLE001
        log.warning("探测音轨失败，本段不喂音频：%s", e)
        return None
    end = min(float(b), total) if total > 0 else float(b)
    dur = end - float(a)
    if dur < 2.0:
        log.info("本段音轨只有 %.2fs（下限 2s），不喂音频参考", dur)
        return None
    end = float(a) + min(dur, 15.0)       # 官方单段上限 15s
    try:
        return scene.cut_audio(track, float(a), end, dest)
    except Exception as e:  # noqa: BLE001
        log.warning("截口型参考音频失败，本段不喂音频：%s", e)
        return None


def boundary_allowed(channel: str, model: str) -> bool:
    """这条通道/型号能不能在换人图之外**再带一张边界帧**。

    ⚠️ 这条限制**没有平台依据**：官方 2.0 系列参考图 0–9 张。它只是因为
    「文字 + 1 条参考视频 + 1 张参考图」是目前唯一实测跑通过的形状（2026-10-21），
    先照着这个最小形状发；而要换的人本来就在这一段里，边界帧也和参考视频首帧
    重合，少带它不影响画面。等这次验证过了再单独测"带边界帧"这一个变量。
    2.5 有 `omni_reference_task_type` 把类型钉成 edit，照带。
    🩸 哪个型号受这条限制由 `Caps.boundary_by_edit_task` 声明，
    核心不再判"是不是 2.0 那条通道"。
    """
    ad = models.adapter_for(model=model, channel=channel)
    if not ad.caps.boundary_by_edit_task:
        return True
    return bool(ad.specs_for(model).get("edit_task_param"))


def _last_frame(piece: Path, dest: Path, *, width: int = 720) -> Path:
    """取一段成片的最后一帧，给下一段当边界参考。"""
    dur = float(scene.probe(piece).get("duration") or 0)
    return scene.extract_frame(piece, max(0.0, dur - 0.06), dest, width=width)


def refine_cuts(video: Path, spans, shots, *, window: float = 1.5,
                step: float = 0.25, min_sec: float = 0.0,
                max_sec: float = 0.0):
    """把"只能硬切"的切点挪到画面变化最小的时刻。

    按镜头边界切是最好的（接缝落在原片本来就有的切换上）。但**一镜到底**的片子
    没有切换点，只能硬切 —— 那就退一步：在目标时间附近扫一圈，挑画面变化最小的
    那一刻下刀，接缝最不容易被看出来。

    hypit 的说法是"按有意义的动作/运镜切"；没有动作边界时，最小变化点就是最接近
    "有意义"的选择。

    已经落在镜头边界 ±0.08s 内的切点一律不动 —— 那里本来就有一刀。

    🩸 `max_sec` 必须传：挪切点会把段拖长，2.0 / H3 单段只收 15s，
    一挪出 15.02s 就是整单被拒（钱还没花，但用户看到的是"这个型号不能用"）。
    """
    spans = list(spans or [])
    if len(spans) < 2:
        return spans

    bounds: list[float] = []
    for s in shots or []:
        try:
            bounds.append(float(s["start"]))
            bounds.append(float(s["end"]))
        except Exception:  # noqa: BLE001
            continue

    out = [[float(a), float(b)] for a, b in spans]
    k = max(1, int(round(window / step)))
    for i in range(len(out) - 1):
        t = out[i][1]
        if any(abs(t - b) <= 0.08 for b in bounds):
            continue
        lo = out[i][0] + max(min_sec, 0.0)
        hi = out[i + 1][1] - max(min_sec, 0.0)
        if max_sec and max_sec > 0:
            # 两边都不能被顶出型号上限
            lo = max(lo, out[i + 1][1] - max_sec)
            hi = min(hi, out[i][0] + max_sec)
        if lo > hi:
            continue
        cand = [round(t + j * step, 2) for j in range(-k, k + 1)]
        cand = [c for c in cand if lo - 1e-9 <= c <= hi + 1e-9]
        if len(cand) < 2:
            continue
        scored: list[tuple[float, float]] = []
        for c in cand:
            scored.append((c, scene.motion(video, max(0.0, c - 0.1), c + 0.1)))
        # 全是 0 = 量具没测出来（可能是 ffmpeg 失败），这时没有可比性，别乱挪
        if max(v for _, v in scored) <= 0.0:
            continue
        # 同样安静的地方，挑离原切点最近的 —— 段长尽量别被带偏
        best, best_v = min(scored, key=lambda x: (round(x[1], 3), abs(x[0] - t)))
        if abs(best - t) >= step / 2:
            log.info("切点 %.2f → %.2f（画面变化最小 %.2f）", t, best, best_v)
            out[i][1] = best
            out[i + 1][0] = best
    return [(a, b) for a, b in out]


# ---------------------------------------------------------------------------
# 主流程


def ref_plan(spec: dict, refs: dict, *, subject_asset: str = "",
             channel: str = "", model: str = "") -> list[tuple[str, object]]:
    """按 `SLOT_ORDER` 算出这次**真正发出去**的参考素材：[(槽位, Path | "asset:ID")]。

    🩸 **一个换的人 = 一张图**（2026-10-26 逐句回原文复核，台账 D48）：
      · 2.0 `sd2-pe:66`「角色图 **1–2**」= 一张合规；官方实战案例 `sd20-guide:222`
        就是「@图片 1：女主半身照」一张打全片；`sd20-guide:414`「人物参考图**优先
        使用单人独立照片**」。「大头照 + 全身照」只出现在 `sd20-guide:305`
        「人脸参考**不准确**」这一**问题章节**里，是补救增强，不是默认配置。
      · 2.5 官方全文没有"大头照/全身照"，写法是**一人一图、每张写全属性**
        （`sd25-pe:227`）；多图只用于**多视角**（`:456` 正面/左侧/右侧/背面）。
      · H3 也没有这条（`ref-en:48`「One subject **may** be defined by multiple
        reference assets」是**许可**不是**要求**）。
    ⇒ 这里**不派生任何第二张图**：用户传哪张就发哪张，原图永远不被裁掉、
    不被替换。脸能不能换住，取决于**顾客那张图里脸占得够不够大**（半身照），
    不是靠我们再裁一张大头照出来。
    🩸 2026-10-26 删掉的旧逻辑：曾按 `caps.split_person_images` 裁一张
    `subject_head.jpg` 排在原图前面 —— 那是把 2.0 的「人脸参考不准确」补救章
    当成了默认配置，逼顾客每次传两张；实测（10-26 12:22）两张也没换住脸
    （证据 `D:/tmp/facecmp/compare.jpg`）。**别再往回加。**
    """
    from app.services import edit_spec

    c = spec["change"]
    asset = (subject_asset or "").strip()
    base: list[tuple[str, object]] = []
    for slot in edit_spec.SLOT_ORDER:
        if not c.get(slot):
            continue
        if slot == "person" and asset:
            # 火山素材 ID 没有本地图 → 没有派生全身照
            base.append((slot, "asset:" + asset))
            continue
        src = refs.get(slot)
        if src is None:
            log.warning("槽位 %s 没有素材，跳过（提示词里也不给它编号）", slot)
            continue
        base.append((slot, Path(src)))

    out: list[tuple[str, object]] = []
    for slot, src in base:
        if isinstance(src, str):        # "asset:..."
            out.append((slot, src))
            continue
        # 一槽一张，用户传哪张发哪张 —— 详细依据见本函数开头。
        out.append((slot, Path(src)))
    return out


def _spec_for_hash(spec: dict) -> dict:
    """缓存键里序列化用的规格：空的多人物字段不参与哈希。

    🩸 和 `work._canon_change` 同一条理由：新加的 `person_ids / person2…person12`
    如果空着也算进哈希，历史出片的键会全部失配 —— 用户重跑同一规格却拿不到
    上一次的分段（白花钱）。空 = 没有这回事，不该改变指纹。
    """
    from app.services import edit_spec

    out = json.loads(json.dumps(spec))
    if isinstance(out.get("change"), dict):
        # 空的新字段不参与哈希（统一规则见 edit_spec.sig_change）
        out["change"] = edit_spec.sig_change(out["change"])
    # 🩸 bgm / sfx 是**纯后期参数**（C4）：它们不写提示词、不多传素材、不改
    # 送给模型的任何一个字 —— 只决定成片合成时怎么混音。所以不论取值，
    # 一律不进模型分段的哈希：否则「只想删个 BGM」会把整片重画一遍（白花钱）。
    for k in ("bgm", "sfx"):
        out.pop(k, None)
    return out


def desc_by_id(inventory: dict | None) -> dict[str, dict[str, str]]:
    """盘点 id → {"zh","en"} 外观描述。

    🩸 换装 / 道具 / 说话人的目标**不一定**在换人名单里（只换衣服不动脸），
    所以提示词编译不能只靠与人物槽位对齐的那张表，要一张全量表。
    火山写中文定位词、H3 写英文定位词 —— 两种都留着，编译时各取所需。
    """
    out: dict[str, dict[str, str]] = {}
    for p in ((inventory or {}).get("people") or []):
        pid = str(p.get("id") or "")
        if pid:
            out[pid] = {"zh": (p.get("desc_zh") or "").strip(),
                        "en": (p.get("desc_en") or "").strip()}
    return out


def _person_ids_in_slots(spec: dict, slots: list[str]) -> list[str]:
    """把 `person_ids` 对齐到**真的有图发出去**的人物槽位。

    第 i 个人 → 第 i 个槽位（person / person2 / person3）。槽位没进 `slots`
    （没传图）就把这个人从名单里去掉：分诊不能按一个没有素材的人去重画。
    """
    from app.services import edit_spec

    ids = list(spec["change"].get("person_ids") or [])
    return [pid for i, pid in enumerate(ids)
            if i < len(edit_spec.PERSON_SLOTS)
            and edit_spec.PERSON_SLOTS[i] in slots]


def _look_for(image: Path | None, slot: str = "person", *,
              compute: bool = False) -> dict:
    """读参考图的外观描述（上传时由 `vision_plan.describe_person` 生成）。

    🩸 官方两家都要求主体定义写**具体特征**，只给图号不够：
      · 火山《Seedance 2.0 提示词指南》§1：2–3 个清晰稳定的静态特征
      · MiniMax H3 ref-en §5 示例：`the young woman ... with long dark hair,
        a blue cardigan, and a thin silver necklace`
    老任务没有这份文件 → 返回空字典，提示词退回原来的写法。

    🩸 **描述必须认得出是哪张图**（`_image_sha1` = 描述时那张图的内容哈希）。
    看不见这个对应关系时，一句"上一位客户"的外观会被写进本次主体定义 ——
    提示词于是让模型"把原片那个人换成另一个人"，而出片里那个人根本没换。
    2026-10-23 19:42 那条 H3 就是带着一句和自己图对不上、却和原片人物很像的
    描述发出去的（"bun … mole … black collared top"）。宁可退回"shown there"
    的纯图号写法，也不许拿一句来源不明的描述去赌。
    """
    if image is None:
        return {}
    try:
        from app.services import clone_store

        p = clone_store.subject_desc_path(Path(image).parent.name, slot)
        data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        # 预览/计划这条路是「零费用」语义（`clone_pipeline` 的 `/plan`）：
        # 缺描述就在这里停手，**不许**偷偷调视觉模型。补算只在真出片时做
        # （调用方传 `compute=True`）。
        if not data and not compute:
            return {}
        # 🩸 2026-11-01 端到端漏洞（主人：「你重出的意义在哪里？我前端你没有做好
        #   端到端吗」）：`describe_person` 只在**上传那一刻**跑，老任务永远停在
        #   旧版本描述上 —— 前端点多少次「重新生成提示词」都拿不到新描述
        #   （实测：v2 描述里一个五官都没有，agent 只能写空话，还自己编了一句
        #   `calm, poised facial aura`）。在远端手动重算只是一次性掩盖。
        #   这里按版本号补算：只有过期才真花一次视觉调用（几厘），算完写回
        #   同一份缓存，之后一直命中。失败就按旧描述继续，不许挡住出片。
        try:
            from app.services import vision_plan

            # 🩸 2026-11-02：**没有描述**和"描述过期"是同一件事，一起补算。
            #   上传时的描述是**后台线程**算的（`api/clone.py`）：换一张新定妆照
            #   马上点出片，这份文件可能还没落盘 → 描述为空 → 改写器只能写
            #   `a refined face`，成片留下原片那张脸（v5 实测 p90 -0.013）。
            #   只有缺/过期才真花一次视觉调用（几厘），算完写回同一份缓存。
            stale = (not data) or (
                str(data.get("_v") or "") != str(vision_plan._DESC_VERSION))
            if stale:
                fresh = vision_plan.describe_person(Path(image).parent.name,
                                                    Path(image), slot)
                if (fresh or {}).get("desc_en") and fresh.get("_v"):
                    log.info("外观描述 %s → v%s 已补算（%s）",
                             data.get("_v") or "缺", fresh.get("_v"),
                             Path(image).parent.name[:12])
                    data = fresh
        except Exception as e:  # noqa: BLE001
            log.warning("外观描述补算失败，按无描述继续：%s", e)
        zh = str(data.get("desc_zh") or "").strip()
        en = str(data.get("desc_en") or "").strip()
        if not (zh or en):
            return {}
        want = str(data.get("_image_sha1") or "").strip()
        got = hashlib.sha1(Path(image).read_bytes()).hexdigest()
        if want != got:
            log.warning("参考图外观描述与当前图对不上（记的 %s / 实际 %s），"
                        "本次按无描述处理", want[:12] or "空", got[:12])
            return {}
        # 🩸 `gender` 只在描述里有时才带：H3 的主体定义要用它（官方 `base-en:129`
        # 把性别列为身份信息之一）。老描述没有这个字段 → 不凭空补。
        out = {"zh": zh, "en": en}
        g = str(data.get("gender") or "").strip()
        if g:
            out["gender"] = g
        return out
    except Exception as e:  # noqa: BLE001
        log.warning("读参考图外观描述失败（按无描述处理）：%s", e)
        return {}


def _prepare(
    *,
    rec: dict,
    prompt: str = "",
    spec: dict | None = None,
    refs: dict[str, Path] | None = None,
    subject_image: Path | None = None,
    subject_asset: str = "",
    channel: str = "auto",
    model: str = "",
    inventory: dict | None = None,
    style_video: Path | None = None,
    compute_looks: bool = False,
) -> dict:
    """把"要换成什么"整理成一次重制要用的全部上下文。

    整片重制和逐镜重制共用这一份：通道、提示词、参考图顺序、分辨率。
    两处各算各的，迟早会出现"整片走火山、逐镜走 MiniMax"这种对不上的情况。

    inventory 是视觉盘点结果：有它就能把"换人物"落到具体某个人、
    并且按段判断这一段里那个人到底在不在。
    """
    from app.services import edit_spec

    subject_asset = (subject_asset or "").strip()
    refs = {k: Path(v) for k, v in (refs or {}).items() if v is not None}
    if subject_image is not None:
        refs.setdefault("person", Path(subject_image))

    if spec is None:
        # 老调用方（只给一句 prompt）：还原成等价的规格，行为跟以前一致
        spec = edit_spec.defaults()
        spec["extra"] = (prompt or "").strip()
        if subject_asset or "person" in refs:
            spec["change"]["person"] = True
    spec = edit_spec.normalize(spec)

    # 只有用户勾了「换人物」才把人物图当参考 —— 传了图但没勾，说明他不想换人
    if not spec["change"]["person"]:
        subject_asset = ""

    if not edit_spec.has_change(spec) and not spec["extra"]:
        raise EditError("换画面必须说明换成什么：至少选一项「换什么」，或写一句补充说明")

    # 勾了槽位却既没素材也没描述：火山会自己编一个「另一个产品」换上去，
    # H3 干脆一个字都不写（花完钱画面没变）。出片前就拦，别让人用钱买一个不变。
    # 风格参考视频（A9）：只在开关打开且文件真的存在时才算"有素材"
    style_video = Path(style_video) if style_video else None
    if style_video is not None and not style_video.exists():
        log.warning("风格参考视频文件不存在，按没有处理：%s", style_video)
        style_video = None
    if not (spec.get("change") or {}).get("style_video"):
        style_video = None
    # 🩸 换装的「逐个查」（第 2、3 个人没图没描述也要拦）是**某一家**的能力，
    #   由那家的 `caps` 说了算 —— 核心层 `edit_spec` 不许认识型号名
    #   （2026-10-28 分离门抓到过：共用层写 `doubao-seedance-2-0` 算厂商耦合）。
    #   `adapter_for` 永不抛；`channel="auto"` 不传进去，免得刷"通道没登记"的警告。
    _ad = models.adapter_for(model=model,
                             channel="" if channel == "auto" else channel)
    _lack = edit_spec.missing_material(spec, refs, person_asset=subject_asset,
                                       style_video=style_video is not None,
                                       model=model,
                                       wardrobe_per_person=_ad.caps.wardrobe_check_per_person)
    if _lack:
        raise EditError(_lack)

    # 🩸 2026-10-27（主人拍板 A）：画面里有多个人、却一个人都没点选 —— 拦住。
    # 以前这种情况会发出「将其中的人物替换为@图片1中的人物」：5 个人的画面里
    # 模型不知道该换哪张脸（2026-10-25 那次整片一帧没换就是这个形态）。
    # 单人画面不拦 —— 官方 `20 单人` 本来就不点名，没有歧义。
    # 没有盘点也不拦：不知道有几个人，交给下游按老行为走。
    if (spec.get("change") or {}).get("person") \
            and not ((spec.get("change") or {}).get("person_ids") or []):
        _frame = (inventory or {}).get("people") or []
        if len(_frame) >= 2:
            raise EditError(
                f"画面里有 {len(_frame)} 个人，请先点选要换的是哪一位 —— "
                "不说清换谁，模型会换错人或者干脆不换")

    src = rec.get("source") or {}
    width = int(src.get("width") or 1080)
    height = int(src.get("height") or 1920)
    kind = edit_spec.subject_kind(spec, person_asset=subject_asset)
    ch = pick_channel(channel, subject_kind=kind)

    edit_model = _model_for(ch, model)
    # 要不要给模型喂一条**独立**音轨专门对口型。三家都接，规则完全相同：
    #   ① 全新配音（tts/mix）→ 喂我们自己合成的配音轨（干净、无版权）；
    #   ② 保留原声（original）→ 喂**原片整条音轨**（2026-10-23 主人拍板）。
    #      以前这里是不喂，模型拿到哑参考视频只能不张嘴（见 `_audio_track` 的说明）。

    _audio_mode = (spec.get("audio") or "tts").strip().lower()
    # 🩸 `original` 也算「要喂音轨」：原片音轨本身就是口型参考（见 `_audio_track`）。
    # 只有真的会传 `reference_audio` 时才允许提示词写 `<Audio 1>` / `@音频1`，
    # 所以这个判定必须和 `_audio_track()` 的出口保持一致。
    # 🩸 2026-10-23 回源更正：**火山 2.0 系列的编辑任务也支持参考音频**。
    # 以前这里对 2.0 恒关，依据是「2.0 编辑公式（指南 :31-40）里没有音频参考这一项」
    # —— 那是只看了推荐句式的列表，漏看了同页的能力说明：
    #   · `volc-api:35`「全模态参考生视频：参考图片（0-9 张）+ 参考视频（0-3 个）
    #     + **参考音频（0-3 个）**+ 文本提示词…**支持生成全新视频、编辑视频、延长视频**」
    #   · `sd20.md:550`（编辑视频章）「您可以提供待编辑的视频、**参考图片或音频**」
    #   · `sd20.md:146` 参考音频可继承「音色、音乐旋律、**对话内容**等核心信息」
    # ⇒ 2.0 / 2.5 / H3 三家编辑任务都喂，不再按型号关掉。
    audio_ref = bool(
        _audio_mode in ("tts", "mix", "original")
        and _spec_for(ch, edit_model).get("ref_audio")
    )

    # 参考图必须按 SLOT_ORDER 的顺序给：提示词里的图号就是这个顺序的第几号。
    # 🩸 先算出**真正发得出去**的槽位，再编译提示词 —— 顺序反了就会出现
    # "勾了换场景但没给场景图"时提示词指着 @图片2、实际只发了 1 张图。
    items = ref_plan(spec, refs, subject_asset=subject_asset,
                     channel=ch, model=edit_model)
    # `asset:` 只是 ref_plan 的内部标记：真正发给模型的 image 值就是素材 ID 本身
    ordered: list = [x.split(":", 1)[1] if isinstance(x, str) and x.startswith("asset:")
                     else x for _, x in items]
    slots: list[str] = [s for s, _ in items]
    # 多人换人但没有可区分的定位词 → 逐人指代会重复，出片只会换错脸。
    # 🩸 按**型号**取适配器，核心不认识任何一家（2026-10-26 模型分离 L3）。
    #   · `pre_compile`：H3 的正文必须英文，中文自由文本在这一步翻掉；2.0/2.5 是空操作
    #   · `gate`：每家读的描述字段和要查的层数都不同（2.0/2.5 读中文、H3 读英文、
    #     2.5 还多一层职责行），各在自己文件里写，**不共用一把尺**
    #   · `person_ids` 必须传：闸要按**实际勾选顺序**取人，否则"只勾第 2 个人"
    #     时会拿盘点里的第 1 个人去判
    _ad = models.adapter_for(model=edit_model, channel=ch)
    _ad.pre_compile(spec)
    _ad.gate(inventory=inventory, slots=slots,
             person_ids=(spec.get("change") or {}).get("person_ids"), spec=spec)

    look = _look_for(refs.get("person")) if spec["change"]["person"] else {}
    # 🩸 2026-11-01：外观描述必须跟着**它自己那张图**的槽位走。
    #   以前整个任务只有一份（= 第一个人的 `subject_desc.json`），H3 编译器
    #   把它套到每一张人物参考图上 —— 实测第二个人（上传的男性真人照）被定义成
    #   「古装女性、浅杏色深 V 薄纱长裙、红唇」，模型只会把那个人换错。
    #   现在按槽位各读各的；这个槽位没有描述就**不借别人的**，退回 `<Picture N>`
    #   纯图号写法（`h3_compile._minimax` 里那条 else 分支）。
    # 🩸 2026-11-02：**真出片这条路要允许补算**（`compute_looks=True`）。
    #   `describe_person` 是上传时的**后台线程**算的，换一张新定妆照马上点出片，
    #   这份文件可能还没落盘 → 该人的外观描述为空 → 改写器只写「图N中的人物」，
    #   零个五官词 → 那个人换不上（`902c4d0f` 实测：第 1 人有描述、第 2 人没有，
    #   SFace 0.336 / 0.178 双双没换）。
    #   官方 `h3-manual:248`：「如果素材中有非常想要保持的特征，**建议明确写出来**，
    #   这样可以让一致性更好」；`ref-en:314` 的主体定义示例本身就带特征。
    #   `/plan`、`/reuse-plan` 这些**零费用**语义的入口仍然不传（保持不偷偷调模型）。
    looks = {s: _look_for(refs.get(s), s, compute=compute_looks) for s in slots
             if s in edit_spec.PERSON_SLOTS and refs.get(s)
             } if spec["change"]["person"] else {}
    # 🩸 2026-10-27：整片重制这条路**一直没把「勾了谁」传给编译器**。
    # `_clauses` 里 `_tag_of(i, per)` 靠 `per["id"]` 去 `orig_tags` 查 `<主体N>`，
    # `per` 来自 `people`（= `people_for_slots(source_people)`）；这里不传
    # `source_people`，`people` 恒为空 → 每人那句都退化成「将其中的人物替换为
    # @图片N中的人物」。可上面 `_sd20_person_tags` 已经把画面里每个人都定义成
    # `<主体N>` 了 —— 定义了却不用，官方 `:107`「后续描述中需持续使用对应标签」
    # / `sd2-pe:15`「之后全程使用同一标签」两头都不占，模型只能猜"其中的人物"是谁。
    # 三条真实素材（a47631b0 / 2f1f26d8 / 3f91496d）勾两人时 3/3 复现。
    # 混剪那条路（`_span_prompt`）一直是传的，只有整片重制漏了。
    _pids = [str(x) for x in ((spec.get("change") or {}).get("person_ids") or [])]
    _by_id = {str(p.get("id")): p for p in (inventory or {}).get("people") or []}
    source_people = [_by_id[x] for x in _pids if x in _by_id]
    full_prompt = edit_spec.compile_prompt(
        ch, spec, person_asset=subject_asset, model=edit_model,
        audio_ref=audio_ref, slots=slots, subject_look=look,
        # 逐槽位的外观描述（第 i 个人只认第 i 张图的描述）
        subject_looks=looks,
        # 勾了谁（按勾选顺序，与槽位一一对应）；没勾名单就不传，保持老行为
        source_people=(source_people or None),
        # 🩸 整个画面的人（不是这次勾选的人）：2.0 判「在场是否 ≥2 人」和
        # 方位是否唯一都要用这个分母（见 `edit_spec._sd20_person_tags`）。
        frame_people=(inventory or {}).get("people") or [],
        desc_by_id=desc_by_id(inventory), style_video=style_video is not None)

    # 提示词硬上限（MiniMax 官方 7000 字符；火山官方只给"建议字数"，没有硬上限）。
    # 超了不是"效果差一点"，是请求直接被拒 —— 提前把数字打出来，别让用户猜。
    cap = _spec_for(ch, edit_model).get("prompt_chars")
    if cap and len(full_prompt) > cap:
        log.warning("提示词 %d 字符，超过 %s 的上限 %d，会被接口拒掉",
                    len(full_prompt), edit_model, cap)

    # asset:// 是火山家的素材 ID，MiniMax 只认文件。真发了会报"文件不存在"，
    # 用户根本看不出为什么 —— 在这儿挡住并说清怎么改
    # 「这家认不认 asset://」由适配器声明，核心不问是哪一家
    if not models.adapter_for(model=edit_model, channel=ch).caps.asset_id             and any(isinstance(x, str) for x in ordered):
        raise EditError(
            f"{_spec_for(ch, edit_model).get('label') or '该模型'} 不认火山素材 ID"
            "（asset://…）：改用火山通道，或者传一张本地人物图再走这条通道"
        )



    resolution = _resolution_for(ch, spec, height, edit_model, width=width)
    return {
        "ch": ch,
        "model": edit_model,
        "limit": _limit_for(ch, edit_model),
        "prompt": full_prompt,
        # 🩸 建议字数（官方 `volc-api:175`：中文 ≤500 字 / 英文 ≤1000 词）。
        #   是**建议不是硬限**，超了照发；只把数字和"怎么办"交给界面。
        #   空串 = 没超（或该型号没这条建议）。
        "prompt_advice": edit_spec.prompt_advice(full_prompt, edit_model),
        "ordered": ordered,
        "resolution": resolution,
        # 渲染时按段重编译提示词要用：规格本身、人物素材 ID、盘点结果
        "spec": spec,
        # 被换的人（按槽位顺序）：逐段分诊要按这个名单逐个判"在不在这一段里"。
        # 🩸 只留**真的有图发出去**的人：选了人却没传图时，后端不能拿文字硬编一句
        # "换成另一个人"（等于瞎换），也不能按没图的人去分段重画。
        "person_ids": _person_ids_in_slots(spec, slots),
        # 提示词里有没有写 <Audio 1>：真没拿到音轨时要按 False 重编译，不然提示词
        # 指着一个没传的素材（老坑：模型自己编一套说话动作，口型对不上）
        "audio_ref": audio_ref,
        "person_asset": subject_asset,
        # 真正发出去的参考图槽位（顺序 = image 数组顺序）。按段重编译提示词时必须
        # 传进去：不传就退回"按勾选算"，一旦有槽位被跳过（或摘掉换人项），
        # 后面所有图的编号会整体错位，提示词指着一张不相干的图。
        "slots": list(slots),
        "inventory": inventory if isinstance(inventory, dict) else None,
        # 风格参考视频（A9）：None = 没有。逐段生成时每段截一小段送进去。
        "style_video": style_video,
        # 参考图里那个人的外观（2–3 个静态特征）：按段重编译提示词时要用，
        # 不存下来每段都得重新读文件
        "look": look,
        # 逐槽位的同一份东西：{槽位: {zh, en}}。第 2 个人不能再借用第 1 个人的
        "looks": looks,
        # 🩸 缓存键必须带上**型号和分辨率**：不带的话，用户切到 2.0 重跑会命中
        # 2.5 的缓存，拿回旧片还以为是新模型出的 —— 比不缓存更糟。
        # 参考图也要算进去：换了一张人物图但提示词没变，键一样就会拿回旧脸。
        "phash": hashlib.sha256(
            "|".join([
                full_prompt,
                json.dumps(_spec_for_hash(spec), ensure_ascii=False, sort_keys=True),
                edit_model,
                resolution,
                "|".join(_ref_sig(x) for x in ordered),
                # 风格视频换了内容也得换缓存键（否则拿回上一次那版观感）
                _ref_sig(style_video) if style_video else "",
            ]).encode("utf-8")
        ).hexdigest()[:12],
    }


# --------------------------------------------------------------- 出片前的闸
# 🩸 四家各一道，**不共用**（2026-10-23 主人拍板）：同一份盘点喂给四家，
# 各家编译器读的字段、要查的层数都不一样 ——
#   · 火山 2.0 / 2.5 / 静帧 → 只读 `desc_zh`（`edit_spec.py:599/:1024/:1731`）
#   · MiniMax H3            → 只读 `desc_en`（`edit_spec.py:1275`）
#   · 2.5 除了换人句，还有【目标素材职责】一层（`_volc_25`）
# 以前一个函数用 `desc_zh or desc_en` 统一放行：盘点只给英文时闸报绿，
# 火山却照样写出两句一样的指代 —— **闸绿、提示词废**。
# 依据：穷举判据 `scripts/identifiability_check.py`（192 组）—— 只有
# 「方位与外观同时区分不了」时才会写出重复指代；只要有一项不同就能区分。

def _n_person(slots: list[str]) -> int:
    from app.services import edit_spec
    return len([s for s in (slots or []) if s in edit_spec.PERSON_SLOTS])


def _picked(inventory: dict | None, slots: list[str],
            person_ids: list[str] | None = None) -> list[dict]:
    """勾选的槽位 → 盘点里对应的人。

    索引尺必须和编译器一致：`_clauses` / `_minimax`
    都是按 `PERSON_SLOTS` 的下标取 `people[i]`。闸若看全片所有人就会漏判
    —— 全片 5 人各有方位、勾的这 2 位却长得一样时，全量够数照样放行。
    这一刀里没出现的人不写句，也就别进判据。

    🩸 2026-10-25：给了 `person_ids` 就**按勾选顺序**取人，那是生产真正的顺序
    （`_span_people` 照 `plan.person_ids` 排）。以前只按盘点下标取，
    "只勾了第 2 个人"时会拿盘点里的第 1 个人去判 —— 判的不是同一个人。
    """
    from app.services import edit_spec
    people = (inventory or {}).get("people") or []
    ids = [str(x).strip() for x in (person_ids or []) if str(x).strip()]
    if ids:
        by = {str(p.get("id") or ""): p for p in people}
        return [by[i] for i in ids
                if i in by and edit_spec._present(by[i])][:len(
                    [s for s in (slots or []) if s in edit_spec.PERSON_SLOTS])]
    out: list[dict] = []
    for i, s in enumerate(edit_spec.PERSON_SLOTS):
        if s not in (slots or []) or i >= len(people):
            continue
        p = people[i]
        if not edit_spec._present(p):
            continue
        out.append(p)
    return out


def _distinct(people: list[dict], field: str) -> bool:
    """这 n 句能不能互不相同：方位 + **这一家自己读的那个**描述字段。

    两样都空的人算同一个定位词（编译器对他只会写「人物」/`the person`）。
    只看"有没有描述"会误伤：方位不同但没描述时明明能区分；
    反过来，用 `or` 混着两个字段看，会在只有一个字段有值时误放行。
    """
    locs = [(str((p or {}).get("position") or "").strip(),
             str((p or {}).get(field) or "").strip()) for p in people]
    return len(set(locs)) == len(locs)


def _coappear(a: dict, b: dict, *, min_overlap: float = 0.1) -> bool:
    """这两个人有没有**同框**过（时间轴上有交集）。"""
    for x in a.get("appearances") or []:
        for y in b.get("appearances") or []:
            lo = max(float(x.get("start") or 0), float(y.get("start") or 0))
            hi = min(float(x.get("end") or 0), float(y.get("end") or 0))
            if hi - lo >= min_overlap:
                return True
    return False


def _locatable(p: dict, mates: list[dict]) -> bool:
    """这个人能不能和同框的其他人区分开 —— 与编译器 `_sd20_orig_feat` 同一把尺。

    两样手段都能用：方位（在画面里唯一）或外观描述（非空且与别人不同）。
    🩸 判"方位唯一"时只看 `mates`（会和 TA 同框的人），不是全片所有人 ——
    从没同框的人不构成歧义。
    """
    pos = str(p.get("position") or "").strip()
    if pos and all(str(q.get("position") or "").strip() != pos for q in mates):
        return True
    zh = str(p.get("desc_zh") or "").strip()
    return bool(zh) and all(str(q.get("desc_zh") or "").strip() != zh for q in mates)


def _gate_single_frame(inventory: dict | None, slots: list[str],
                       person_ids: list[str] | None, model_label: str,
                       sentence_hint: str, locator=None) -> None:
    """只勾一个人时的可指认闸（2.0 / 2.5 / H3 共用同一把尺，措辞分开）。

    🩸 "勾 1 个"不等于"画面里只有 1 个"：两个人同框、只换其中一个时，
    提示词仍要说出换的是哪一位。这个人在同框的人里**既没有唯一方位、
    也没有能区分的描述**时，编译器只能写成 `sentence_hint` 那种没有指认的句子。

    `locator(per, pool) -> str`：型号**编译器实际会写出来的定位词**。
    不传 = 用默认的 `_locatable`（读 `desc_zh`）。
    🩸 2026-10-26：H3 的编译器读的是 `desc_en`，闸必须调**同一个函数**
    （`edit_spec.h3_orig_locator`）—— 闸看 zh、编译器看 en 会必然出现
    "闸放行但写不出定位词"的缝。
    """
    from app.services import edit_spec as _es20

    people = [p for p in ((inventory or {}).get("people") or [])
              if _es20._present(p)]
    picked = _picked(inventory, slots, person_ids)
    if not picked or len(people) < 2:
        return
    me = picked[0]
    mates = [q for q in people
             if str(q.get("id") or "") != str(me.get("id") or "")
             and _coappear(me, q)]
    if locator is not None:
        # 空定位词 = 编译器写不出指认；非空但和同框的人撞了 = 指认不了同一个人。
        me_loc = locator(me, people)
        if not mates or (me_loc and all(locator(q, people) != me_loc for q in mates)):
            return
    elif not mates or _locatable(me, mates):
        return
    raise EditError(
        "画面里有其他人和 TA 同时出现，但盘点没给出能区分这两个人的信息"
        "（方位和外观都取不到）。"
        f"{model_label} 的换人句只能写成{sentence_hint}，模型会换错人。"
        "请重新识别一次，或只换画面里那位能被单独指认的人。")


def require_identifiable_volc20(inventory: dict | None, slots: list[str],
                                person_ids: list[str] | None = None, *,
                                locator=None, locator_multi=None) -> None:
    """火山 2.0 —— 一段式，只有换人句一层。

    官方定位手段两样：方位（`sd2-pe:72` 把"多人未指明谁在左/右"列为病灶；
    `:153` 示例 `@图片2 中的女生位于画面左侧`）+ 外观（`:72` 同条）。
    编译器读 `desc_zh`（`edit_spec.py:599`）—— 拿 `desc_en` 放行等于没判。

    🩸 2026-10-25（D27）：**只勾一个人也要判**。以前 `n <= 1` 直接放行，
    但"勾 1 个"不等于"画面里只有 1 个人"：两个人同框、只换其中一个时，
    提示词仍要说出换的是哪一位。盘点对这个人**既没方位（或方位撞车）
    又没描述**时，编译器只能写「将其中的**人物**替换为…」—— 画面里两个人，
    这句谁也没指认（`ruler_sd20 --sweep` 的第 ⑧ 组现场抓到的）。
    """
    n = _n_person(slots)
    if n <= 1:
        # 🩸 2026-10-26 22:xx：闸必须调**编译器用的同一个函数**（`sd20_locator`）。
        # 以前闸读 `_locatable`（方位也算数），编译器却按特征写 —— 两边不是一把尺，
        # 会出现"闸放行、写出来的句子却指不到人"。
        # 🩸 2026-10-27：编译器改成三档（方位唯一 → 「画面中央的人物」；
        # 撞车才退回特征），闸跟着它走 —— 只认方位或只认特征都是旧口径。
        # 🩸 2026-10-28：`sd20_locator` 已搬进 `models/volc20_compile.py`
        #   （它是 2.0 的认人尺，不该躺在三家共读的文件里）。由 2.0 的适配器
        #   在 `gate()` 里把它传进来 —— 共用层不 import 任何一家。
        _gate_single_frame(inventory, slots, person_ids, "2.0",
                          "「将其中的…替换为…」", locator=locator)
        return
    picked = _picked(inventory, slots, person_ids)
    # 🩸 2026-10-29（D70）：多人时**不再问「描述互不互异」**，改问编译器那把尺 ——
    # 「每个人都能写出定位词吗，而且两两不同吗」。
    # 现场：两人描述是「第1号人物穿的独特服装」/「第2号人物穿的独特服装」、
    # 方位都是 left。描述互异 ⇒ 旧判据放行；可 `_orig_feat_20` / `_head_noun`
    # 都以「要有个人物中心词」为前提，这两段以服装开头、没有人物名词 ⇒ 都取空，
    # 编译器各写一句「将其中的人物替换为…」，两句一字不差（`OPEN-DEFECTS` D70）。
    # 闸和编译器必须是同一把尺（D27 定下的规矩），所以由 2.0 适配器把
    # `volc20_compile.sd20_multi_locator` 传进来；不传仍走旧判据（老调用方兼容）。
    if locator_multi is not None:
        from app.services import edit_spec

        pool = [p for p in ((inventory or {}).get("people") or [])
                if edit_spec._present(p)]
        locs = [locator_multi(p, pool) for p in picked]
        if len(picked) >= n and all(locs) and len(set(locs)) == len(locs):
            return
    elif len(picked) >= n and _distinct(picked, "desc_zh"):
        return
    raise EditError(
        "这次要换 2 个人以上，但盘点没能把画面里的人区分开。"
        "2.0 的换人句会写成两句一样的「将其中的…替换为…」，模型只能自己分派、换错脸。"
        "请重新识别一次，或只勾一个人物槽位。")


def require_identifiable_volc25(inventory: dict | None, slots: list[str],
                                person_ids: list[str] | None = None) -> None:
    """火山 2.5 —— 五段模板，要查**两层**。

    换人句（【编辑目标】）和【目标素材职责】用的是同一套定位词，但
    **是两处独立生成的文本**：2026-10-23 实测 5 个人写出 5 行一字不差的
    职责行，而当时换人句是好的。只查换人句会漏掉这一层。
    模板要求 `<原对象>` 具体（`sd25-pe:561`），不是"人物"。
    编译器读 `desc_zh`（`edit_spec.py:1024`）。
    """
    n = _n_person(slots)
    if n <= 1:
        # 🩸 2026-10-26（D28）：与 2.0 同一条洞 —— 只勾一个人也要判。
        _gate_single_frame(inventory, slots, person_ids, "2.5",
                          "「只把…替换为…」")
        return
    picked = _picked(inventory, slots, person_ids)
    if len(picked) >= n and _distinct(picked, "desc_zh"):
        return
    raise EditError(
        "这次要换 2 个人以上，但盘点没能把画面里的人区分开。"
        "2.5 的【编辑目标】和【目标素材职责】都会写成一样的指代，"
        "模型只能自己分派、换错脸。"
        "请重新识别一次，或只勾一个人物槽位。")


def require_identifiable_h3(inventory: dict | None, slots: list[str], *,
                             locator=None) -> None:
    """MiniMax H3 —— 六段式，读**英文**描述。

    `ref-en:246` 要求首次清晰出现时写 `position in the frame`；
    `:330` 示例 `From the left, <Subject 4>, the young man with short wavy
    brown hair…`。编译器读 `desc_en`（`edit_spec.py:2549`）——
    盘点只给中文描述时，H3 的 `changed` 句写不出定位。

    🩸 2026-10-26（D39）：**只勾一个人也要判** —— 与 2.0 的 D27、2.5 的 D28
    同一条洞。以前这里 `n <= 1` 直接返回，于是"画面 2 人、同方位、都没描述、
    只换其中一个"会编出 `<Subject 2> is the person in <Video 1>`（谁？），
    模型只能自己分派、换错脸。定位词直接调编译器的 `h3_orig_locator`，
    保证闸和产出是同一把尺。
    """
    from app.services import edit_spec as _es

    n = _n_person(slots)
    if n <= 1:
        _gate_single_frame(
            inventory, slots, None, "H3",
            # 🩸 2026-10-28：这里原来写的是 H3 的**原句** `<Subject N> is the
            #   person in <Video 1>` —— 只是错误消息里的反例，不是生成的提示词，
            #   但共用层出现某家原句就是串味（分离门的 `phrase_scan` 会红）。
            #   用户要的是"知道问题出在哪 + 怎么办"，不需要看别家的英文原句。
            "一句反过来指认的换人句（说不出是哪一位）",
            locator=locator)
        return
    picked = _picked(inventory, slots)
    if len(picked) >= n and _distinct(picked, "desc_en"):
        return
    raise EditError(
        "这次要换 2 个人以上，但盘点没能把画面里的人区分开（英文描述缺失也算）。"
        "H3 的 summary 会写成两句一样的 `The person in <Video 1> is replaced by…`，"
        "模型只能自己分派、换错脸。"
        "请重新识别一次，或只勾一个人物槽位。")













def _span_plan(plan: dict, spans: list[tuple[float, float]]) -> dict:
    """按段决定这一刀怎么处理：换人 / 只重画不换人 / 直接留原片。

    没有盘点结果时返回空字典 —— 调用方走老路径（整段套用同一句提示词）。
    """
    from app.services import vision_plan

    inv = plan.get("inventory")
    spec = plan.get("spec") or {}
    c = spec.get("change") or {}
    if not inv:
        return {}

    # 被换的人：多人时是名单，老记录只有 person_id（空 = 自动取主角）
    ids = [str(x).strip() for x in (c.get("person_ids") or []) if str(x).strip()]
    if not ids and str(c.get("person_id") or "").strip():
        ids = [str(c.get("person_id")).strip()]
    # 🩸 只换衣服时也要分诊：点名的那几个人**不在这段**，这段就没东西可改。
    # 不点名（名单为空 = 全体一起换）才退回整片套用同一句。
    wid = [str(x).strip() for x in (c.get("wardrobe_ids") or []) if str(x).strip()]
    watch = list(dict.fromkeys(ids + wid))
    # 名单空着但勾了「换人物」= 老语义（自动取主角），不能当成"没有目标"
    if not watch and not c.get("person"):
        return {}
    targets = {sp: vision_plan.targets_in(inv, sp[0], sp[1], watch or None)
               for sp in spans}
    if not any(targets.values()):
        # 🩸 2026-10-26（D36 补）：**点名优先于"盘点完全为空"**。
        # 以前这两块的顺序反了 —— `not inv.get("people")` 先 return {}，
        # 把下面的 `if watch: raise` 整个挡死。实测后果：
        #   · 点名换装 P1 + 盘点没识别到人 → 退回整片一句
        #     「将其中的**服装**换成…」，**P1 这个点名丢了，变成全体换装**；
        #   · 点名换人 P1 + 盘点没识别到人 → 同样放行，靠「其中的人物」碰运气。
        # 代码下面那句注释本来就写着"别猜、别硬套，直接让他重选"，只是够不着。
        if watch:
            # 用户明确选了人，盘点里却一个都没出现 —— 别猜、别硬套，直接让他重选。
            # 与换人/换装走同一条闸：点名的东西在盘点里找不到，就不许拿"全体"顶上。
            raise EditError(
                f"盘点结果里没有 {'、'.join(watch)}（可能换了片子或识别有误）："
                "重新识别一次，或换一个人选")
        if not inv.get("people"):
            # 盘点一个人都没识别到，且用户**没有点名**：不能据此把所有段都留原片
            # （等于没干活），退回老行为，让用户看到结果不对再调整。
            log.warning("盘点没识别到人物，退回整片套用同一句提示词")
            return {}
        log.info("这些分段里都没出现主角，按「不换人」处理")

    # 「整片都要动」的改动：有它就不能按"这一段没人"留原片。
    # 点名到人的换装/道具不算 —— 只影响那几个人出现的那几段。
    # 风格参考（A9）也是"整片都要动"：它改的是每一段的观感，
    # 留一段原片 = 成片里一段有风格、一段没有。
    other = any(c.get(k) for k in ("product", "scene", "style",
                                   "style_ref", "style_video")) \
        or bool(spec.get("extra")) \
        or bool(c.get("wardrobe") and not wid)
    # 🩸 只有**保留原声**时才允许整段留原片。
    # 全新配音（tts/mix）时原片的口型对不上新台词，这一段必须重画重做口型，
    # 哪怕不该换人 —— 否则观众看到的是"这张脸在说别的话"。
    keep_ok = (spec.get("audio") or "tts").strip().lower() == "original"
    out: dict[tuple[float, float], tuple[str, list]] = {}
    for sp, tgt in targets.items():
        if tgt:
            out[sp] = ("change", tgt)
        elif other or not keep_ok:
            # 目标不在这一段（或用户还改了产品/场景/风格，或要重做口型）：
            # 仍要重画，只是不写换人项
            out[sp] = ("text", None)
        else:
            # 保留原声、目标不在、也没有别的改动：原样保留，不花这一刀的钱
            out[sp] = ("keep", None)
    return out


def _at_shot_cut(rec: dict, t: float, tol: float = 0.08) -> bool:
    """这个切点是不是原片自己的镜头切换点。

    🩸 切在镜头切换上时**不能带边界帧**：上一段的尾帧是上一个场景的画面，
    拿它当"目标视频第一帧"等于把旧场景钉进新镜头里（和 2026-10-22 那次
    原片人物回灌是同一类病，只是方向相反）。
    """
    for s in rec.get("shots") or []:
        try:
            if abs(float(s["start"]) - float(t)) <= tol:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _boundary_used(plan: dict, spans: list[tuple[float, float]],
                   acts: dict, shots=None) -> bool:
    """真的有没有哪一段带了边界帧（结果页/对账照着它说话）。

    🩸 2026-11-02：**边界帧已整条停用**（见 `_gen_spans` 顶部那条），所以恒为
       `False`。函数名和签名留着，只为不动调用方。
      别把下面那套老判定复活 —— 它算的是"如果按老规则会不会带"，而发出去的
      请求里已经没有这张图了，照旧算就是**报一个没发生的事**。
    """
    return False


def _boundary_used__retired(plan: dict, spans: list[tuple[float, float]],
                            acts: dict, shots=None) -> bool:
    """（墓碑，保留原文备查，勿调用）"""
    if len(spans) < 2 or not boundary_allowed(plan["ch"], plan["model"]):
        return False
    rec = {"shots": list(shots or [])}
    for n in range(2, len(spans) + 1):
        prev_act = acts.get(tuple(spans[n - 2]), ("", None))[0]
        if prev_act == "keep":
            continue
        if abs(float(spans[n - 2][1]) - float(spans[n - 1][0])) >= 1e-3:
            continue
        if _at_shot_cut(rec, float(spans[n - 1][0])):
            continue
        return True
    return False


def _span_people(plan: dict, targets: list | None) -> list[dict]:
    """把这一刀命中的目标排成**与人物槽位一一对应**的名单。

    缺席的人显式标 `present=False`：提示词里不写他的换人句，但图号照旧保留
    （图还是发出去的，编号不能跟着"这一段不在"重算）。
    """
    ids = list(plan.get("person_ids") or [])
    targets = [t for t in (targets or []) if t]
    if not ids:
        # 老记录：只有一个"那个人"，没有名单
        return targets
    by = {t.get("id"): t for t in targets}
    return [dict(by[pid], present=True) if pid in by
            else {"id": pid, "present": False} for pid in ids]


def _shot_looks(cid: str, rec: dict) -> list[str]:
    """H3 专用：逐镜画面描述，**直接取盘点结果里那一次已经看过的内容**。

    出处：官方 `ref-en:7` 要求 `detailed_description` 逐镜写清构图、主体外观与
    位置、环境光线、动作、当前声音，**不许**写成参考关系列表；官方 README 的
    Ref2VA 完整案例也是逐镜写画面。
    🩸 不额外调模型：解析参考视频时整条片子已经送进 2.1 看过一遍，
    `vision_plan.inventory` 的 `shots` 就是那次的产出（2026-10-23 主人纠正）。
    🩸 失败一律返回 `[]` —— 提示词退回原来的关系句写法，绝不让用户出不了片。
    """
    try:
        from app.services import vision_plan

        shots = rec.get("shots") or []
        if not shots:
            return []
        spans = [(float(s["start"]), float(s["end"])) for s in shots]
        return vision_plan.describe_shots(cid, spans)
    except Exception as e:  # noqa: BLE001
        log.warning("逐镜画面描述不可用（提示词退回关系句写法）：%s", e)
        return []


def _span_prompt(plan: dict, targets: list | None, *, drop_person: bool,
                 audio_ref: bool | None = None,
                 boundary_pic: int = 0,
                 slots: list[str] | None = None,
                 shot_cuts: list[float] | None = None,
                 shot_looks: list[str] | None = None,
                 shot_lines: list[list[dict]] | None = None,
                 frame_people: list[dict] | None = None) -> str:
    """按段重编译提示词：把盘点到的"那个人"写进去，或把换人项摘掉。

    `audio_ref` 传 None = 跟着 plan 走（默认要喂音轨）；传 False = 这一段没有音轨，
    提示词里就不能出现 `<Audio 1>`。
    """
    from app.services import edit_spec

    if audio_ref is None:
        audio_ref = bool(plan.get("audio_ref"))
    # 老调用方传的是单个 target（dict），统一成名单
    if isinstance(targets, dict):
        targets = [targets]
    spec = plan.get("spec")
    # `slots` 默认与 plan 一致；H3 会按段摘掉缺席人物的图（见 `_gen_spans`），
    # 那时必须用**这一段的真实槽位**重编译，否则图号整体错位。
    slots = list(slots if slots is not None else (plan.get("slots") or []))
    same_slots = slots == list(plan.get("slots") or [])
    # 镜头结构句（这一段是不是一个连续镜头）必须进提示词，所以带 `shot_cuts` 的
    # 调用一律重编译，不能走"原样返回 plan['prompt']"的捷径（见 `shot_plan_sentence`）。
    if not spec:
        if shot_cuts is None:
            return plan["prompt"]
        return (plan["prompt"] + " " + edit_spec.shot_plan_sentence(
            plan["ch"], shot_cuts, model=plan.get("model") or "")).strip()
    if (not targets and not drop_person and not boundary_pic
            and same_slots and shot_cuts is None and shot_looks is None
            and shot_lines is None
            and audio_ref == bool(plan.get("audio_ref"))):
        return plan["prompt"]
    spec = json.loads(json.dumps(spec))  # 深拷贝：别把 plan 里的规格改掉
    if drop_person:
        spec["change"]["person"] = False
    # 🩸 `slots` 必须带过去：这一段真正发出去的参考图就是这几张，
    # 编号必须按**实际发出去的顺序**算（火山/没摘人物时 = plan 原样）。
    return edit_spec.compile_prompt(
        plan["ch"], spec, person_asset=plan.get("person_asset") or "",
        model=plan["model"], source_people=_span_people(plan, targets),
        # 🩸 这一段的**整个画面**（含没有被勾选换掉的人）：2.0 判"在场 ≥2 人"
        # 和方位是否唯一都用它当分母。`source_people` 只含勾选的人，
        # 只换两个人中的一个时那张表长度为 1，拿它数永远进不了多人分支。
        frame_people=(frame_people if frame_people is not None
                      else (plan.get("inventory") or {}).get("people") or []),
        audio_ref=audio_ref, slots=slots,
        subject_look=plan.get("look") or {},
        subject_looks=plan.get("looks") or {},
        desc_by_id=desc_by_id(plan.get("inventory")),
        boundary_pic=boundary_pic, shot_cuts=shot_cuts,
        shot_looks=shot_looks, shot_lines=shot_lines,
        # 风格参考视频（A9）：这一段真的会发出去才写 @视频2 / <Video 2>
        style_video=bool(plan.get("style_video")))


def _assign_speakers(rec: dict, inventory: dict | None) -> None:
    """给每句台词标上说话人（盘点人物 id），**只能靠画面推**。

    两个证据源，按可靠度用：

    **① 声学（官方给的，最直接）**：句子的 `asr_speaker` 来自
    `utterances[].additions.speaker`。官方《录音文件识别极速版HTTP》请求参数
    `show_utterances` 原文是「**启用输出分句、分词、说话人**及语音停顿信息」——
    我们一直传着 true，只是 `_from_volc` 没把它取上来。同一编号的句子是同一个
    嗓音说出来的，**同框对白也能分**（画面帮不上忙，声纹帮得上）。

    **② 画面（用来把声学编号落到人身上）**：句子的时间段里，盘点结果中只有
    一个人在场 → 这句就是他说的 → 于是「声纹 1 = P2」这类对应关系有了。
    正反打 / 单人镜头里这条很准；两人同框的句子不投这一票，避免把两个人的
    嗓音混成一个。

    先投票定「声纹 → 人物」，再用它回填**画面判不出来**的句子（同框对白、
    画外音）。两个证据都没有的句子不标，编译器退回"不指名"的老行为。

    结果被三个编译器读：`x["speaker"]`（盘点人物 id）由各自的 `speaker_label`
    翻成提示词里的指代 ——
    · 2.5：`_volc_25` → `_sd25_lines`；
    · 2.0：`volc20_compile._sd20_lines` → `_sd20_speaker_label`（2026-10-27 核实，
      以前这里写着"只有 2.5 读"，是过时注释）；
    · H3：仍走界面手勾的 `speaker_ids`（`edit_spec` 的 H3 分支），**没接**这里的推断。

    🩸 只影响**提示词点名**（谁动嘴），不影响音频：tts/mix 模式下整条新音轨是
    **一个音色**（`clone_pipeline` 的 `voice_id` 全局一个），没有按人分轨。
    """
    lines = rec.get("voice_lines") or []
    people = [p for p in ((inventory or {}).get("people") or [])
              if p.get("id") and (p.get("appearances") or [])]
    if not lines:
        return

    def who_in_window(ln: dict) -> str:
        """这句的时间里，画面只有一个人 → 返回他；0 个或多个 → 空串。"""
        if not people:
            return ""
        s = float(ln.get("start") or 0.0)
        e = float(ln.get("end") or 0.0)
        span = e - s
        if span <= 0.05:
            return ""
        hit: list[str] = []
        for p in people:
            for ap in p.get("appearances") or []:
                ov = min(e, float(ap.get("end") or 0.0)) - \
                    max(s, float(ap.get("start") or 0.0))
                if ov > 0.4 * span:      # 覆盖这句的四成以上才算"在场"
                    hit.append(str(p["id"]))
                    break
        return hit[0] if len(hit) == 1 else ""

    # 第 1 轮：声纹 → 人物 投票（只投画面能唯一定人的句子）
    votes: dict[str, dict[str, int]] = {}
    for ln in lines:
        spk = str(ln.get("asr_speaker") or "").strip()
        pid = who_in_window(ln)
        if spk and pid:
            votes.setdefault(spk, {})
            votes[spk][pid] = votes[spk].get(pid, 0) + 1
    # 票多的先认；一个人已经被别人占了就不再分配（声纹与人物应当一一对应）
    mapping: dict[str, str] = {}
    for spk in sorted(votes, key=lambda k: -max(votes[k].values())):
        pid, _n = max(votes[spk].items(), key=lambda kv: kv[1])
        if pid in mapping.values():
            continue
        mapping[spk] = pid

    # 第 2 轮：逐句定人 —— 画面能定就用画面（直接证据），否则查声纹映射
    for ln in lines:
        spk = str(ln.get("asr_speaker") or "").strip()
        pid = who_in_window(ln) or mapping.get(spk, "")
        if pid:
            ln["speaker"] = pid


def _span_lines(rec: dict, a: float, b: float,
                cuts: list[float]) -> list[list[dict]] | None:
    """这一段里每一镜各说了什么（源片时间轴上的 `rec["voice_lines"]`）。

    🩸 官方 `base-en:142` / `ref-en:221`：
      · **一句台词跨过切点** → 拆成前后两半，两段的连接点各标 `<scenetrans>`，
        并写明声音跨切连续（以前整句塞进中点所在那一镜，另一镜不知道有人说话，
        嘴型差半句）；
      · **语音被视频结尾截断** → `<cutoff>`（只在最后一段判，分段边界不算）。
    返回长度 = `len(cuts) + 1`；这段没台词返回 None。
    """
    vl = [x for x in (rec.get("voice_lines") or [])
          if str(x.get("text") or "").strip()]
    if not vl:
        return None
    n_shot = len(cuts) + 1
    buckets: list[list[dict]] = [[] for _ in range(n_shot)]
    bnds = [float(a)] + [float(a) + float(c) for c in cuts]
    total_v = float((rec.get("source") or {}).get("duration") or 0.0)
    for ln in vl:
        s0 = float(ln.get("start") or 0.0)
        e0 = float(ln.get("end") or 0.0)
        if e0 <= float(a) + 1e-6 or s0 >= float(b) - 1e-6:
            continue
        text = str(ln.get("text") or "").strip()
        # 🩸 2026-10-28（2.5 分段一致性实测）：**段边界也是切点**。
        #   以前只按段内切点拆（下面的 `crossing`），一句横跨 30s 分段的台词
        #   会被整句塞进**两段** —— 两个独立请求各念一遍同一句。
        #   官方 `base-en:142` / `ref-en:221`：一句台词跨过切点 → 拆成前后两半，
        #   两段连接点各标 `<scenetrans>` 并写明声音跨切连续。
        #   段边界这一刀按**时间比例**切字（和 `crossing` 同一套算法）。
        _head = s0 < float(a) - 1e-6      # 这句从上一段延续进来
        _tail = e0 > float(b) + 1e-6      # 这句延续到下一段
        _span_part = ""
        if (_head or _tail) and len(text) >= 4:
            _lo = ((float(a) - s0) / max(1e-6, e0 - s0)) if _head else 0.0
            _hi = ((float(b) - s0) / max(1e-6, e0 - s0)) if _tail else 1.0
            _i0 = max(0, min(len(text) - 1, int(round(len(text) * _lo))))
            _i1 = max(_i0 + 1, min(len(text), int(round(len(text) * _hi))))
            text = text[_i0:_i1].strip()
            # 跨三段（两头都裁）时先按"从上一段延续"标，否则按"延续到下一段"标
            _span_part = "end" if _head else "start"
            if not text:
                continue
        crossing = [] if _span_part else [
            j for j in range(1, n_shot)
            if s0 + 0.05 < bnds[j] < e0 - 0.05]
        if crossing and len(text) >= 4:
            t_cut = bnds[crossing[0]]
            frac = (t_cut - s0) / max(1e-6, e0 - s0)
            n_char = max(1, min(len(text) - 1, int(round(len(text) * frac))))
            head, tail = text[:n_char].strip(), text[n_char:].strip()
            if head and tail:
                j = crossing[0]
                buckets[j - 1].append({**ln, "text": head, "part": "start"})
                buckets[j].append({**ln, "text": tail, "part": "end"})
                continue
        mid = (s0 + e0) / 2.0
        k = 0
        for j, t0 in enumerate(bnds):
            if mid >= t0:
                k = j
        item = dict(ln)
        if _span_part:
            item["text"] = text
            item["part"] = _span_part
        elif (total_v > 0 and float(b) >= total_v - 0.05
                and e0 >= total_v - 0.15):
            item["part"] = "cutoff"
        buckets[min(k, n_shot - 1)].append(item)
    return buckets if any(buckets) else None


def _span_script(rec: dict, a: float, b: float) -> list[tuple[float, float, str]]:
    """这一段**真实说过**的台词，秒数换成「相对本段起点」。喂给 H3 改写器用。

    🩸 2026-11-02（H21）：官方 `h3-manual:248`「在音频复刻/部分复刻中，如果对于
      人声对白内容…的保持有较高的要求，**强烈建议补充具体歌词文本内容**」；
      `h3-manual:251`「**注意台词的长短尽量和镜头长短对齐（这个得强调下，很多
      口型问题会来自于这个）**」。我们走的就是原声复用，却一直只给音频不给字。
    🩸 实测翻车（`db253cfc`）：第 2 段从半句中间（4.133s）切起，改写器靠听音频
      把上一句「然后我就这一个样品」补全后当成第 2 段第一句，模型照着又念了一遍
      —— 这段音频里那句只剩尾巴 → 第 2 段嘴型全程错位。
    · 归属按**字的中点**：跨界那个字归真正念它的那一段，不两段都算
      （按「起点落在段内」会把跨界的字白送上一段，第 2 段开头又冒一个残字）。
    · 没有字级时间（老任务 / 没识别出字）就按整句时间**按比例**裁 —— 与
      `_span_lines` 同一套算法，不另立标准。
    · 全部来自原片 ASR，**一个字不编**。
    """
    out: list[tuple[float, float, str]] = []
    # 🩸 台词以 `voice_lines` 为准：原声模式下它就是 ASR 结果；**重新配音（tts/mix）
    #   模式下 `speech` 仍是原片 ASR，而画面要念的是新文案** —— 拿 `speech` 会喂错词。
    #   字级时间只有 ASR 那份有，所以按「文字完全一致」才借用，避免串到原片台词上。
    segs = (rec.get("speech") or {}).get("segments") or []
    chars_of = {str(s.get("text") or "").strip(): (s.get("chars") or [])
                for s in segs}
    lines = (rec.get("voice_lines") or []) or segs
    for s in lines:
        chars = s.get("chars") or chars_of.get(str(s.get("text") or "").strip()) or []
        if chars:
            keep = [c for c in chars
                    if a <= (float(c.get("s") or 0.0) + float(c.get("e") or 0.0)) / 2 < b]
            if not keep:
                continue
            txt = "".join(str(c.get("c") or "") for c in keep).strip()
            s0 = max(float(a), float(keep[0].get("s") or a))
            e0 = min(float(b), float(keep[-1].get("e") or b))
        else:
            s0 = float(s.get("start") or 0.0)
            e0 = float(s.get("end") or 0.0)
            txt = str(s.get("text") or "").strip()
            if not txt or e0 <= a or s0 >= b:
                continue
            lo = (a - s0) / max(1e-6, e0 - s0) if s0 < a else 0.0
            hi = (b - s0) / max(1e-6, e0 - s0) if e0 > b else 1.0
            i0 = max(0, min(len(txt) - 1, int(round(len(txt) * lo))))
            i1 = max(i0 + 1, min(len(txt), int(round(len(txt) * hi))))
            txt = txt[i0:i1].strip()
            s0, e0 = max(s0, float(a)), min(e0, float(b))
        if txt:
            out.append((round(s0 - a, 2), round(e0 - a, 2), txt))
    return out


def _gen_spans(
    plan: dict,
    video: Path,
    spans: list[tuple[float, float]],
    *,
    rec: dict,
    cid: str,
    workdir: Path,
    progress=None,
    label: str = "重制",
    base_pct: int = 52,
    span_pct: int = 20,
    max_segments: int = 0,
    force: bool = False,
) -> list[Path]:
    """按区间逐段重制，返回**实际生成了的**片段（可能比 spans 少）。

    缓存键 = 通道 + 提示词哈希 + 区间，同参数重跑不重复扣费。

    🩸 `max_segments`（2026-11-01 主人要求「先生成一段满意再继续」）：
    只跑前 N 段就停，返回的 list 比 spans 短 —— 调用方据此判定"这是预览，
    不能拼接成片"。默认 0 = 全跑（老行为）。
    继续出全部时不用另外记状态：缓存键含每段的最终提示词，前 N 段原样
    命中缓存、不重复扣费，只有没生成过的段才真花钱。
    """
    from app.services import ark, clone_store as store, edit_spec, minimax

    if not spans:
        raise EditError("没有可处理的片段")

    ch = plan["ch"]
    ad = models.adapter_for(model=plan.get("model") or "", channel=ch)
    # 逐句说话人（画面推断）。改的是副本，不写回任务记录。
    rec = dict(rec)
    rec["voice_lines"] = [dict(x) for x in (rec.get("voice_lines") or [])]
    _assign_speakers(rec, plan.get("inventory"))
    # 🩸 2026-10-31：这一单若已经在预览里由 agent 按官方 skill 写过逐段指令
    #   （`data/clone/<cid>/prompts.json`，签名对得上），出片就用那份，
    #   **不现场跑 agent** —— 用户已经点了"开始"，不能因为 agent 慢或挂了卡住。
    #   签名对不上（换了勾选/参考图/型号/skill）→ 当作没有，走下面的代码编译。
    _agent_segs: dict[int, str] = {}
    try:
        # 🩸 2026-11-01：按型号分派 —— 2.5 与 H3 各有一套 agent（模板不通用）。
        #   适配器上没有 `agent` = 这家没有 agent 版，直接走代码编译。
        _agent = ad.agent
        if _agent is not None:
            _agent_segs = _agent().cached(cid, plan, rec, spans) or {}
        if _agent_segs:
            log.info("第 %d 段提示词采用 agent 版本（官方 skill 现写）", len(_agent_segs))
    except Exception as e:  # noqa: BLE001
        log.warning("读取 agent 逐段指令失败（改用代码编译）：%s", e)
    # 🩸 逐镜画面描述（H3 的 `detailed_description`，官方 `ref-en:7` +
    #    README 的 Ref2VA 完整案例）。由视觉模型读关键帧生成、按内容哈希缓存；
    #    失败返回 [] → 提示词退回关系句写法，不挡出片。
    #    只给要这份描述的家算：别家不用，算了纯烧钱。
    shot_looks: list[str] = _shot_looks(cid, rec) if ad.caps.shot_looks else []
    # 开跑前把每段都过一遍 —— 跑到第 5 段才发现 2 秒的尾巴不收，
    # 前 4 段的钱已经花了。宁可一次都别发。
    lo, hi = bounds_for(ch, plan["model"])
    # 🩸 2.0 专属：先吸附到整数秒，再校验（校验的必须是**真正要发**的区间）。
    #   幂等：`plan_spans` 已经吸过一次，这里再吸不会变 —— 但"只换开头"这类
    #   由用户手选区间的入口不经过 `plan_spans`，必须在这一层兜住。
    spans = snap_for_plan(plan, spans, min_sec=lo, max_sec=hi)
    bad = [(round(a, 2), round(b - a, 2)) for a, b in spans
           if not (lo - 1e-6 <= (b - a) <= hi + 1e-6)]
    if bad:
        raise EditError(
            f"{plan['model']} 只收 {lo:.0f}–{hi:.0f} 秒的片段，这些不行："
            + "、".join(f"{a}s 起 {d}s" for a, d in bad)
            + "（原片太短或镜头太碎：换一个型号，或改用「只换开头」）"
        )
    work = workdir
    (work / "gen").mkdir(parents=True, exist_ok=True)
    # 风格参考视频（A9）：**开跑前**算清每段放不放得下，放不下一次都别发。
    style_src = plan.get("style_video")
    style_clip: Path | None = None
    if style_src is not None:
        clip_sec, style_err = style_video_budget(ch, plan["model"], spans)
        if style_err:
            raise EditError(style_err)
        style_clip = work / "style_ref.mp4"
        try:
            # 🩸 exact=True + audio=False：这段要送平台校验（`scene.cut_clip`
            # docstring 那条 `-c copy` 负 PTS 的坑），而且实测 copy 切「2.0 秒」
            # 出来是 2.067 秒；重编码才是干净的 2.0。风格参考不需要声音，
            # 丢掉音轨少一个审核面。
            scene.cut_clip(Path(style_src), 0.0, clip_sec, style_clip,
                           exact=True, audio=False)
            log.info("风格参考视频截段 %.1fs → %s", clip_sec, style_clip.name)
        except Exception as e:  # noqa: BLE001
            # 截不出来就当没有：风格视频是"锦上添花"，不能把整条出片搞挂。
            # 🩸 但提示词必须跟着改口：plan 里还留着 style_video 的话，
            # 每段会写「@视频2用于…」，而请求里根本没有第二条视频。
            log.warning("风格参考视频截段失败，按无风格视频处理：%s", e)
            style_clip = None
            plan = dict(plan)
            plan["style_video"] = None
            from app.services import edit_spec as _es

            plan["prompt"] = _es.compile_prompt(
                ch, plan["spec"], person_asset=plan.get("person_asset") or "",
                model=plan["model"], audio_ref=bool(plan.get("audio_ref")),
                slots=plan.get("slots") or [],
                subject_look=plan.get("look") or {},
                subject_looks=plan.get("looks") or {},
                frame_people=(plan.get("inventory") or {}).get("people") or [],
                desc_by_id=desc_by_id(plan.get("inventory")))
    # 口型参考音轨：整条片只有一条，先取一次。拿不到就把提示词里的 <Audio 1> 全撤掉
    audio_track = _audio_track(plan.get("spec") or {}, video, work) \
        if plan.get("audio_ref") else None
    if plan.get("audio_ref") and audio_track is None:
        log.warning("口型参考音轨不可用（%s 模式），提示词按无音频重编译",
                    (plan.get("spec") or {}).get("audio"))
    # 🩸 2026-10-31 口型对不上（官方 `sd2-pe/references/trouble.md` A-4，
    #   `:157` 汇总行 / `:323-330` 正文）：
    #   官方原话「生成视频中的音频会与原本的参考音频有较大区别……最终导致口型
    #   对不上」，解法是「将音频转成**黑屏的视频**（⚠️ 关键步骤：这是一致性较高
    #   的保障），并且生成视频的长度跟输入视频**严格一致**」。
    #   我们原来把原声拆成 `audio_url`（`reference_audio`）单独送 —— 那正是 A-4
    #   说的会跑偏的形态：模型只把它当音色样本、自己另说一套，成片再贴回原声，
    #   于是段越长飘得越远（实测 段1 ±0.2s / 段2 最差 0.9s）。
    #   黑屏视频在本工程塞不下：官方 `guide.md:987`「最多支持 3 段视频输入，
    #   **总时长不得超过 15 秒**」，而母版自己就占了 8.5 秒。
    #   所以取同一原理的等价形态 —— **让编辑母版自带原声**：音频以"视频里的一条
    #   轨道"进模型，而不是当独立音频素材。
    #   只对 2.0 生效：2.5 的音频口径是「参考音频承载台词/音色」（`sd25-pe`），
    #   两代官方文档不同，不许互相搬。
    _amode = str((plan.get("spec") or {}).get("audio") or "tts").strip().lower()
    # 🩸 2026-11-01 根因：这里原来是 `not edit_task_param`，注释写「只对 2.0 生效」。
    #   2.0 下架后 2.5 被 `edit_task_param=True` 挡掉，**只剩 H3 走进来** ——
    #   而 H3 正是官方明说「参考视频里有声音 ≠ 有音频参考」的那家
    #   （`ref-en:112`：An ordinary reference video does not create `<Audio N>`
    #   merely because the file contains sound.）。H3 走母版 ⇒ `seg_audio=None`
    #   ⇒ 请求里一条音频都没有，提示词却写着 `<Audio 1>` 是口型参考
    #   ⇒ 模型没有可跟的东西，嘴型必错（真实快照 `audio=false` 实锤）。
    #   改成显式能力声明：没有模型声明 `audio_from_master` 就一律单独送音频。
    #: 🩸 2026-11-02 台账审计：这个开关原来读的是**参数表字典**
    #: （`_spec_for(...).get("audio_from_master")`），可 `model_specs` 里根本没人
    #: 声明过这个键 —— 而能力声明实际写在 `Caps` 上（`models/base.py`）。
    #: 声明一处、读另一处 = 永远 False，等于没接线。现在统一读 `ad.caps`。
    _master_audio = bool(
        _amode == "original" and audio_track is not None
        and getattr(ad.caps, "audio_from_master", False))
    # 🩸 配音（tts/mix）改一句词，画面里的口型就变了；可区间、提示词、型号、参考图
    # 全都没变 —— 键不带**音频内容**就会命中上一次的段，观众看到"新台词配旧口型"。
    # 这正是 P1 写下的边界：露脸说话 = 改词必须重新表演。
    # 只对真喂了音轨的段生效；保留原声（`:na`）的键与历史一致，不白花一次钱。
    audio_sig = ""
    if audio_track is not None:
        try:
            audio_sig = ":" + hashlib.sha1(audio_track.read_bytes()).hexdigest()[:6]
        except OSError as e:  # noqa: BLE001
            log.warning("配音音轨读不出内容，本段按「音频可能变了」处理：%s", e)
            audio_sig = ":?"
    # 切段放在任务目录下（不是出片目录）：火山要按段给公网 URL，
    # 签名端点按文件名取，所以切段必须是稳定可寻址的
    seg_dir = store.task_dir(cid) / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)

    src = rec.get("source") or {}
    width = int(src.get("width") or 1080)
    height = int(src.get("height") or 1920)
    fps = float(src.get("fps") or 30)

    # 🩸 参考段的帧数卡成 8n+1（见 `_align_8n1`），只有 2.5 的编辑任务要。
    # 2.0 不加：它的输出时长是整数秒，本来就没有"比输入短 0.33 秒"这回事。
    _cut_8n1 = bool(ad.caps.align_8n1)

    manifest = _manifest(work)
    # 进度里写出**具体型号**：用户跑完要对账"我测的到底是哪一款"
    shown = (_spec_for(ch, plan["model"]).get("label")
             or models.adapter_for(model=plan["model"], channel=ch).caps.display_name
             or ch)
    _p(progress, f"{label}：共 {len(spans)} 段（{shown}）", base_pct)

    # 有盘点结果时，逐段判断"这一刀换谁 / 不换 / 直接留原片"
    span_acts = _span_plan(plan, spans)

    # 🩸 2.5 编辑任务的输出比输入**短**：官方 `sd25-pe:316`「输出时长受输入帧
    #   处理影响，可能与原视频存在最大约 0.3 秒的差异」；实测 2026-10-31
    #   （30fps 源片 25.633s 进去 → 回来 609 帧 @24fps = 25.375s，短 0.26s）。
    #   两种补法，都**不冻帧、不回灌原片**：
    #     · 中间段：往后多切 `_EXTRA` 秒原片一起送，出来再裁回本段长度（无损）；
    #     · 尾段：后面没有素材可多切了 ⇒ 成片跟着短（主人 2026-10-31 拍板），
    #       缺口 ≤ `_TAIL_TOL` 才收，超了照旧抛 `ShortClip` 让人换素材。
    _src_total = float((rec.get("source") or {}).get("duration") or 0.0)
    _EXTRA = 0.5        # 中间段往后多切多少原片（秒）
    _TAIL_TOL = 0.45    # 尾段允许比这一段短多少（秒）

    pieces: list[Path] = []
    # 上一段是"重画过的"还是"直接留原片"：只有重画过的才需要边界帧。
    # 🩸 上一段保留原片时，原片本身在这条缝上是连续的 —— 再拿它的尾帧当
    # "目标视频第一帧"，等于要求新人物从**原片那张脸**开始，和第 2 段开头
    # 回灌原片是同一类病（2026-10-22）。
    prev_generated = False
    for n, (a, b) in enumerate(spans, 1):
        if max_segments and n > max_segments:
            log.info("只出前 %d 段（本单共 %d 段）：第 %d 段起本次不生成",
                     max_segments, len(spans), n)
            break
        # `need` = 这一段**成片**必须有的长度；`dur` = 实际送进模型的参考段长度。
        # 中间段送长一点（往后借 `_EXTRA` 秒原片），模型少给的那 0.3 秒就吃掉借款；
        # 尾段借不到，按 `need` 送，少给多少最后按实际长度收口。
        need = max(0.5, b - a)
        tail_slack = 0.0
        if _src_total > 0 and b + _EXTRA <= _src_total - 1e-3:
            tail_slack = _EXTRA
        cut_b = b + tail_slack
        dur = max(0.5, cut_b - a)
        seg = seg_dir / f"seg_{n:03d}.mp4"
        gen = work / "gen" / f"chunk_{n:03d}.mp4"
        act, target = span_acts.get((a, b), ("", None))
        if act == "keep":
            # 这一刀里要换的人根本没出现，也没有别的改动 —— 保留原片，
            # 既不会换错人，也省掉这一刀的钱
            scene.cut_clip(video, a, b, gen)
            manifest[seg.name] = f"orig:{a:.2f}-{b:.2f}"
            _save_manifest(work, manifest)
            log.info("第 %d 段盘点无目标人物，保留原片", n)
            pieces.append(_normalize(gen, work / f"piece_{n:03d}.mp4", need,
                                     width, height, fps))
            prev_generated = False
            continue
        # 缓存清单按**原始段名**记：段被重编码后会变成 seg_xxx_fit.mp4，
        # 用重编码后的名字记键，下次就永远命中不了
        # 连续段要把上一段成片的尾帧当参考带过去（见下方 bf），
        # 提示词也跟着变 —— 键里必须带上这个标记，否则会命中不含边界帧的旧缓存
        # 🩸 官方要求「请求里的每一张参考图都要在 subject_definitions 里定义」
        # （H3 `ref-en.txt:35`）。这一刀里没出现的人，图发过去却没写定义 —— 模型可以
        # 把那张脸当可用主体塞进画面（和边界帧回灌同一类病）。所以这家按段摘掉
        # 缺席人物的图并整体重编号；火山保持已验证的「图号稳定」写法不动
        # （`Caps.drop_absent_people` 就是这件事的开关）。
        span_slots = list(plan.get("slots") or [])
        refs_list = list(plan["ordered"])
        if ad.caps.drop_absent_people and plan.get("inventory"):
            ppl = _span_people(plan, target)
            drop = {edit_spec.PERSON_SLOTS[i] for i, p in enumerate(ppl)
                    if not p.get("present", True)}
            if drop:
                keep_i = [i for i, s in enumerate(span_slots) if s not in drop]
                span_slots = [span_slots[i] for i in keep_i]
                refs_list = [refs_list[i] for i in keep_i]
                log.info("第 %d 段：摘掉这一段没出现的人的参考图（%s）", n,
                         "、".join(sorted(drop)))
        # 🩸 2026-11-02（H19）：原片里人比图多时（3 人只勾 2 位），必须写清
        #   **哪张图替换哪一位**，否则改写器只认图1、或换到没勾的那个人身上。
        #   方位来自盘点（`inventory.people[].position`），不是现编的。
        #   顺序与人物槽位一致 ⇒ 与 `instruction()` 里的 `person_pics` 一一对应。
        ir_ppl: list[dict] = []
        ir_frame_n = 0
        if plan.get("inventory"):
            _all = _span_people(plan, target)
            _idx = {s: i for i, s in enumerate(edit_spec.PERSON_SLOTS)}
            ir_ppl = [_all[_idx[s]] for s in span_slots
                      if s in _idx and _idx[s] < len(_all)]
            # 🩸 这一段**画面里一共有几个人**（不是勾了几个）：决定要不要写
            #   「替换左边那位」。原片本来就一个人时写方位 = 给一个不存在的区分。
            try:
                from app.services import vision_plan as _vp
                ir_frame_n = len(_vp.people_in(plan["inventory"], a, cut_b))
            except Exception:  # noqa: BLE001
                ir_frame_n = 0
        # 🩸 2026-11-02（H21）：这一段真实说过的台词（相对秒数）也要给改写器。
        #   不给就只能靠它听音频 —— 从半句中间切起时它会把上一句补全写进来，
        #   模型照着又念一遍（`db253cfc` 第 2 段实测）。文字来自原片 ASR。
        #   ⚠️ 用 `b` 不用 `cut_b`：`cut_b` 是参考片多切的 0.5 秒尾巴，成片和
        #   音频都只到 `b`；按 `cut_b` 算会把下一段开头的话算进来。
        ir_lines = _span_script(rec, a, b)
        bf_mark = ""
        # 🩸 `:mau` = 母版自带原声（A-4 那条修法）。必须进缓存键：提示词/区间/参考图
        #   都没变的情况下，母版从"无声"变成"带音轨"是一次真实输入变化，不换键就会
        #   命中上一次的旧段 —— 改动等于没做。
        au_mark = (":mau" if _master_audio else
                   "" if not plan.get("audio_ref") or audio_track else ":na")
        # 🩸 2026-11-02 主人拍板：**边界帧整条停用，任何一段都不再带**。
        #   理由（主人原话，代码事实也对得上）：
        #   · 第 2 段的参考视频就是从原片 [a, cut_b] 切出来单独上传的
        #     （见上面 `scene.cut_clip` + `h3._submit`），它的第一帧天然就是
        #     切点那一帧的原片画面 —— 接缝的信息本来就在参考视频里；
        #   · 中间段还会往后多借 `_EXTRA = 0.5` 秒，接缝那半秒**两次生成都看过原片**。
        #   ⇒ 再叠一张"上一段成片的尾帧"，是整条链上**唯一一个非原片来源的输入**：
        #     它把上一次生成产生的偏差当成下一次的现实。
        #   ⚠️ 它本来也没有官方出处：火山官方只要求「延长时承接**原视频**尾帧」
        #     （`sd25-pe:649/695`），H3 只在 `ref-en:65` 规定"一张图当首帧时怎么写"。
        #     我们这套来自第三方 hypit（原句 2026-10-23 已删，机制一直留到现在）。
        #   `_last_frame` / `boundary_allowed` 已无调用点（墓碑留着，别复活）。
        bf = None
        bf_pic = 0
        # 盘点到了这一段要换的人 → 把"那个人"写进这一段的提示词；
        # 目标不在但有别的改动 → 只摘掉换人项，其余照做
        # 音轨没拿到 → 这一段按"没有 <Audio 1>"重编译（否则提示词指着一个没传的素材）
        # 这一段内部有几刀（相对段起点的秒数）。两家官方都要求把镜头结构写进提示词：
        #   · MiniMax《H3 使用手册》第四章：「默认会切镜」，想一镜到底要显式写；
        #   · 火山《Seedance 2.5 指南》：「转场镜头写清触发点与方式」。
        # 不写 → 模型在 15s 的块里自己决定切几次、切到哪，跨场景的块就并成两个画面
        # （任务 a47631b0 实测：13.5s 两格同脸、21.5–25s 下半格消失）。
        cuts = _clean_cuts(
            [float(s["start"]) - a for s in (rec.get("shots") or [])
             if a + 0.15 < float(s["start"]) < b - 0.15], b - a)
        # 这一段的镜头各自带一句视觉描述（`ref-en:7`）。段内的镜头 = 与本段
        # 时间区间有交集的镜头；数量必须等于 `len(cuts) + 1`，对不上就整段
        # 不用（宁可退回关系句，也不能让镜头号和描述错位）。
        seg_looks: list[str] | None = None
        if shot_looks:
            _ids = [int(s["i"]) for s in (rec.get("shots") or [])
                    if float(s["end"]) > a + 1e-6 and float(s["start"]) < b - 1e-6]
            if len(_ids) == len(cuts) + 1 and all(
                    0 <= i < len(shot_looks) for i in _ids):
                seg_looks = [shot_looks[i] for i in _ids]
        # 🩸 官方 `ref-en:220/274`、`base-en:129`：这一段的台词要写进 `<d>`。
        # `rec["voice_lines"]` 是**源片时间轴**上的逐句台词 —— tts/mix 来自用户填的
        # 新文案，original 来自原片 ASR；都是确定文本。按句子中点落到哪一镜分桶。
        seg_lines = _span_lines(rec, float(a), float(b), cuts)
        # 这一段画面里**出现了哪些人**（含没有被勾选换掉的人）：
        # 2.0 判「在场 ≥2 人」和方位是否唯一都要拿它当分母，
        # 只用勾选名单会在"只换其中一个"时判成单人（见 `_sd20_person_tags`）。
        frame_ppl = None
        if plan.get("inventory"):
            from app.services import vision_plan as _vp

            frame_ppl = _vp.people_in(plan.get("inventory"), a, b)
        seg_prompt = _span_prompt(plan, target, drop_person=(act == "text"),
                                  audio_ref=bool(audio_track),
                                  boundary_pic=bf_pic, slots=span_slots,
                                  shot_cuts=cuts, shot_looks=seg_looks,
                                  shot_lines=seg_lines,
                                  frame_people=frame_ppl)
        # agent 版本优先（签名已在上面对过）。段号 n 从 1 起，与 prompts.json 一致。
        # 缓存键用的是**编译后的提示词**，所以换成 agent 版后旧缓存自然失效。
        if _agent_segs.get(n):
            seg_prompt = _agent_segs[n]
        # 🩸 2026-11-02：边界帧停用后，这里不再往参考图里追加任何东西。
        #   缓存键里的 `:bf3` 标记也随之消失 —— 旧段带边界帧、新段不带，
        #   是两种真实不同的输入，不能共用缓存。
        bf_mark = ""

        # 参考图先按该通道的官方硬门槛收口（边长/体积），再发。
        # 6000px 的原图直接发会在上传后被拒；重编码是本机 CPU，不花钱。
        refs_list = [x if isinstance(x, str) else _fit_image(Path(x), ch)
                     for x in refs_list]

        # 这一段换的是谁必须进缓存键：同一条片子换主角重跑，
        # 提示词变了但区间没变，键不带主体就会拿回旧的段
        who = ""
        if target:
            # 多人时这一段换的是**一组人**，名单里任何一个变了键都得变
            who = ":" + hashlib.sha1(
                "|".join(f"{t.get('id')}|{t.get('desc_zh')}|{t.get('desc_en')}"
                         for t in target).encode("utf-8")).hexdigest()[:6]
        # 口型参考切片要在**算缓存键之前**拿到：改写器的指令里有一句
        # 「音频1是视频1的同步音轨…」，有没有这条音频决定指令内容，也决定指纹。
        # 以前这段在"缓存没命中"分支里才算，指纹根本拿不到。
        seg_audio = (None if _master_audio else
                     _seg_audio(audio_track, a, b,
                                work / "audio" / f"seg_{n:03d}.wav"))
        # 🩸 2026-11-02：**改写器的输入指纹必须进段缓存键**。
        #   以前键里只有代码编译版提示词（下一行的 `seg_prompt`），改写器产出的
        #   那份词是在缓存判定**之后**才生成的 —— 它变了，键却不变。
        #   全靠人工标记 `:irN` 兜着；我漏升一次，07:05 预调的新词出片时
        #   一次都没被用上，三次渲染拿回同一个 476,680 字节的旧片。
        #   现在：指令/素材/区间/时长任何一项变了，指纹就变 → 必然重新生成。
        # 🩸 2026-11-02：**想保持的特征要写进改写器的输入**（官方 `h3-manual:248`
        #   「如果素材中有非常想要保持的特征，建议明确写出来」）。以前这里不传，
        #   改写器产出的 `<Subject 1>` 只有发簪和衣服、零个五官词 → 成片保住原片
        #   那张脸（SFace 0.09）。文本来自定妆照自己的描述文件，不是现编的。
        ir_looks = {s: _look_ir((plan.get("looks") or {}).get(s))
                    for s in span_slots}
        ir_sig = ""
        if ad.caps.prompt_sig is not None:
            ir_sig = ad.caps.prompt_sig(
                slots=span_slots,
                dur=_gen_duration(dur, plan.get("model") or ""),
                images=refs_list, boundary_pic=bf_pic,
                extra=str((plan.get("spec") or {}).get("extra") or ""),
                looks=ir_looks,
                # 🩸 2026-11-02（缺口二）：段内切点进改写器输入，也进指纹 ——
                #   改写器不知道有几刀就按一镜到底写（原片 5 镜 → 产出只有
                #   `[Shot 1]`）。切点是相对段起点的秒数，与切片同一条时间轴。
                cuts=cuts,
                # 🩸 2026-11-02（缺口三）：音频用途也要进改写器输入、也进指纹。
                #   没有音轨可传时给空串 —— 提示词里就不该出现「音频1」。
                # ⚠️ 默认值必须是 `tts`，与 `_audio_track()` 的
                #   `spec.get("audio") or "tts"` 一致 —— 否则 spec 不写 audio
                #   时音轨照样传了，提示词却一个字不提。
                audio_mode=((plan.get("spec") or {}).get("audio") or "tts")
                if audio_track else "",
                # 🩸 2026-11-02（H19）：方位要进指纹 —— 换了勾选的人，
                #   词就变，缓存键必须跟着变，否则拿回上一次的旧词。
                ppl=ir_ppl, frame_n=ir_frame_n,
                # 🩸 2026-11-02（H21）：台词也进指纹 —— 改了文案/切点导致台词
                #   分布变了，就必须换键，否则拿回上一版的旧词。
                lines=ir_lines,
                video_src=str(video), video_span=(a, cut_b),
                audio_src=(str(audio_track) if audio_track else ""),
                audio_span=(a, b))
        # 🩸 键必须带**这一段最终发出去的提示词**。只带 plan 级 phash 时，改了提示词
        # 编译逻辑（例如这次加的镜头结构句）键不变 → 命中旧缓存 → 改动等于没做。
        seg_hash = hashlib.sha1(
            f"{plan['phash']}|{seg_prompt}".encode("utf-8")).hexdigest()[:12]
        # 改写器的指纹进键（见上面 `ir_sig`）。没有 `prompt_sig` 的机器
        # 退回人工版本标记 `:ir8` —— 那是老机制，只给还没接指纹的模型留着。
        # 历史：`:ir2`–`:ir8` 是 2026-11-02 逐轮人工升的版本号；每次改指令都要
        # 记得升，漏一次就命中旧段（实测三次渲染拿回同一段）。现在由 `ir_sig`
        # 自动覆盖，**别再手升版本号**。
        ir_mark = (f":ir:{ir_sig}" if ir_sig
                   else ":ir8" if ad.caps.prompt_for is not None else "")
        key = _seg_key(ch, seg_hash, a, b, bf_mark=bf_mark,
                       au_mark=au_mark, audio_sig=audio_sig, who=who,
                       ir_mark=ir_mark)

        # 🩸 2026-11-02「强制重跑」（`force`）：同一个键默认永远命中缓存 ——
        #   这既能省钱，也意味着**失败了就再也抽不到第二次**（模型本来就不确定）。
        #   用户明确点了"强制重跑"才跳过两级缓存，重新调模型（会再扣一次费）。
        if not force and manifest.get(seg.name) == key and gen.exists():
            log.info("第 %d 段命中本目录缓存，不重复生成", n)
        elif not force and _cache_get(cid, key, gen):
            # 🩸 缓存键里**有这一段最终发出去的提示词**（见上面 seg_hash）。
            # 提示词一改，键就变 → 必然重新生成；键没变，说明这次要的就是
            # 一模一样的那段，复用是省钱而不是挡路。
            # 2026-10-24 曾把这条缓存删掉（误以为它导致"重跑没变化"），当天
            # 实测反证：同一提示词真跑了一遍，成片与上一版 SSIM 0.95 ——
            # 钱花了，结果照样一样。已恢复。
            log.info("第 %d 段命中任务缓存（同提示词重跑），不重复扣费", n)
            manifest[f"seg_{n:03d}.mp4"] = key
            _save_manifest(work, manifest)
        else:
            # 参考片带不带音轨：默认不带（成片音轨取自原片，少一条音轨少一个审核面）；
            # **原声模式的 2.0 要带** —— 见上面 `_master_audio` 与官方 A-4。
            # 🩸 但**别**把"不带音轨"写成"已验证避开版权"：那次因果没被证实（§十九）。
            # 🩸 `exact=True`：这一段要送去平台校验，必须帧精确重编码。`-c copy`
            # 从中间切会带出前面几秒的"discard + 负 PTS"包（见 scene.cut_clip）——
            # 火山当场收了任务，7 秒后异步判 `InvalidParameter`，就是它。
            _cut_kw = {}
            if _cut_8n1:
                _nf = _align_8n1(dur, fps)
                if _nf:
                    _cut_kw["frames"] = _nf
            scene.cut_clip(video, a, cut_b, seg, audio=_master_audio,
                           exact=True, **_cut_kw)
            # 像素/帧率/文件大小三项不过关就是同步 400，先在本机收拾干净
            seg = _fit_segment(seg, ch, frames=_cut_kw.get("frames", 0),
                               keep_audio=_master_audio)
            _p(progress, f"{label} {n}/{len(spans)}（{shown}）",
               base_pct + int(span_pct * (n - 1) / max(1, len(spans))))
            # 口型参考：这一段的配音切片。两家走同一套 —— 只有 tts/mix 才有
            # （audio_track 在 original 模式下就是 None），拿到 2 秒以内或截失败也不喂。
            # 🩸 原声模式的 2.0 不再单独送 `audio_url`：同一条音轨已经挂在母版上了，
            #   再送一份等于又回到 A-4 说的"当音色样本"那条路（见 `_master_audio`）。
            # 口型切片已在算缓存键之前取好（见上面 `seg_audio`）；这里不再重切。
            # 🩸 2026-11-02：H3 的逐段提示词改由**官方改写器**产出
            #   （一句自然语言 + 这一段真正的素材 → `POST /v2/h3_context_ir`）。
            #   放在这里而不是 `/prompts`：改写器看的必须是**这次真正要发的东西**
            #   —— 切片后的原片段、按段摘过缺席者的参考图、这一段的配音切片。
            #   结果按输入指纹落盘，同一素材重跑拿回同一份词（不抽卡）。
            if ad.caps.prompt_for is not None:
                seg_prompt = ad.caps.prompt_for(
                    cid, n, video=seg, images=refs_list, slots=span_slots,
                    audio=seg_audio,
                    dur=_gen_duration(dur, plan.get("model") or ""),
                    extra=str((plan.get("spec") or {}).get("extra") or ""),
                    # 边界帧在 refs_list 里的号：改写器得知道那张图是"第一帧"，
                    # 否则会当成又一张人物图来定义（`ref-en:62` 的写法）
                    boundary_pic=bf_pic,
                    # 🩸 2026-11-02：五官**不是**我编的句子，是定妆照自己的描述
                    #   文件（`subject_desc.json`），官方 `h3-manual:248` 明写
                    #   「想保持的特征建议明确写出来」。撤掉它那次实测 SFace 0.09。
                    looks=ir_looks,
                    # 🩸 2026-11-02（缺口二）：段内切点必须进改写器的输入。
                    #   官方 `base-en:86` 要求每个 `[Shot N]` 以严格递增的切点
                    #   时间开头；不告诉它有几刀，它就按一镜到底写（原片 5 镜
                    #   → 产出只有 `[Shot 1]`）。切点是相对段起点的秒数。
                    cuts=cuts,
                    # 🩸 2026-11-02（缺口三）：音频用途必须写进改写器的输入
                    #   （`h3-manual:248` 的「音频复用」「音色参考」两档）。
                    #   没有音轨可传 → 空串，提示词里不提音频。
                    # ⚠️ 默认 `tts`，与 `_audio_track()` 的
                    #   `spec.get("audio") or "tts"` 对齐。
                    audio_mode=((plan.get("spec") or {}).get("audio") or "tts")
                    if seg_audio is not None else "",
                    # 🩸 2026-11-02（H19）：多人换人时写明「哪张图替换哪一位」，
                    #   方位来自盘点，与人物槽位同序。
                    ppl=ir_ppl, frame_n=ir_frame_n,
                    # 🩸 2026-11-02（H21）：这一段真实说过的台词（相对秒数）。
                    #   不给就只能靠改写器听音频，从半句中间切起时它会把上一句
                    #   补全当成这一段的第一句（`db253cfc` 第 2 段实测翻车）。
                    lines=ir_lines,
                    # 🩸 缓存键要「原片 + 区间」，不是切片文件字节：同一段每次
                    #   重切都会生成新文件，字节差一点指纹就变，预调好、审过的
                    #   那份出片时永远命不中（改写器于是重抽一次）。这里只把
                    #   原始路径和区间交出去，怎么算指纹是适配器自己的事。
                    video_src=str(video), video_span=(a, cut_b),
                    audio_src=(str(audio_track) if audio_track else ""),
                    audio_span=(a, b))
                # 🩸 2026-11-02 **退回过度干预**：这里原来还传了两样东西 ——
                #   `looks=_span_looks(...)`（把参考图长相算成英文塞进句子）和
                #   `audio_mode`（按原声/配音换不同措辞）。加上"直接修改/不重新生成"
                #   "成片里只有图1的人"，一共 4 条规则，等于用中文预写六段式。
                #   现在全撤：只告诉改写器"每份素材管什么"，其余让它自己组织。
                #   顺带省掉 `_span_looks` 里那次花钱的 `describe_person` 调用。
            # 🩸 2026-10-31 第 1 步：一段 2.0 请求**发之前**先过形状闸。
            #   一条复刻里每一次生成请求的形状只有一种（1 张人物图 + 1 段原片
            #   + 1 条音频 + 1 句提示词 + 整数时长）。偏离的形状一次都没被验证过，
            #   发出去就是"这条片子为什么和上次不一样" —— 本机报错，不花钱。
            _shape_sig = ""
            if ad.caps.shape_guard:
                _ok, _shape_sig, _bad = sd20_request_shape(
                    videos=2 if style_clip else 1,
                    audios=1 if (seg_audio is not None or _master_audio) else 0,
                    images=len(refs_list), dur=dur, prompt=seg_prompt)
                if len(refs_list) != 1 and not _bad:
                    # 只登记不拦：换背景/换产品/多人各有自己的槽位，
                    # 拿"换人已验证 1 张"去砍它们就是拿 A 体裁量 B 体裁。
                    log.warning("第 %d 段形状偏离换人基线：参考图 %d 张（只登记）",
                                n, len(refs_list))
                if not _ok:
                    raise EditError(
                        f"第 {n} 段不符合 2.0 的唯一请求形状（"
                        f"{_shape_sig}）：" + "；".join(_bad))
            # 出错时要写进证据文件的「真正发出去的东西」：try 里赋值，except 里读。
            sent_video = ""
            sent_refs: list = []
            sent_ingest: dict = {}
            try:
                ctx = {
                    "seg": seg, "prompt": seg_prompt, "out": gen,
                    "refs": refs_list, "audio": seg_audio,
                    "style_clip": style_clip, "cid": cid, "work": work,
                    "n": n, "plan": plan, "dur": dur, "ch": ch,
                    "ingest": sent_ingest,
                    # 请求形状签名 + 音频是不是挂在母版上 —— 落进 request_xxx.json，
                    # 出事时不用再猜"这一段到底发了什么"
                    "shape": _shape_sig, "master_audio": _master_audio,
                }
                # 🩸 2026-10-26 L3：两家的请求形态完全不同（火山公开 URL + asset:// 入库
                # + 生成音轨；H3 本地文件直传），整段下沉到各家 `submit()`。
                sent_video, sent_refs, sent_ingest = ad.submit(ctx)
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                # 审核类报错别只甩原始 JSON：按错误码说清是哪一类、下一步点哪里。
                # 追加什么由**这家自己**决定（火山有审核码要翻译，别家不追加）。
                msg += ad.error_hint(msg)
                # 🩸 把这次失败**全部有用的东西**写进一个 json：哪一段、多长、
                # 用哪个模型/分辨率、参考视频走的是 asset:// 还是公网 URL、
                # 素材库是不是先拒过、火山的 code / request id、当时的提示词。
                # 界面上再带一小段摘要，不用回头翻 uvicorn 日志（会被重启覆盖）。
                detail = getattr(e, "detail", None) or {}
                rec = error_report.dump(
                    work, stage=f"seg_{n:03d}",
                    cid=cid, channel=ch, model=plan.get("model"),
                    resolution=plan.get("resolution"),
                    segment=n, span=[round(a, 3), round(b, 3)],
                    duration=round(dur, 3),
                    video=sent_video or "（未发出）",
                    video_form=("asset" if str(sent_video).startswith("asset://")
                                else "url" if str(sent_video).startswith("http")
                                else "file" if sent_video else "-"),
                    video_ingest=sent_ingest or "ok（已入素材库或不适用）",
                    refs=[str(x)[:160] for x in (sent_refs or refs_list)],
                    has_audio=bool(seg_audio), prompt=seg_prompt,
                    error=e)
                form = ("asset" if str(sent_video).startswith("asset://")
                        else "公网URL" if str(sent_video).startswith("http")
                        else "本地文件" if sent_video else "-")
                raise EditError(
                    f"第 {n} 段生成失败：{msg}" + error_report.brief(
                        rec, 段=n, 区间=f"{a:.2f}-{b:.2f}s", 时长=f"{dur:.2f}s",
                        模型=plan.get("model"), 分辨率=plan.get("resolution"),
                        参考视频=form,
                        素材库=(sent_ingest.get("failed") or sent_ingest.get("skip")
                              or "已入库"),
                        错误码=detail.get("code") or "",
                        请求ID=detail.get("request_id") or "")
                ) from e
            manifest[f"seg_{n:03d}.mp4"] = key
            _save_manifest(work, manifest)
            _cache_put(cid, key, gen)

        # 这一段成片要多长：默认就是本段长度；**尾段**模型少给时按实际长度收口
        # （主人 2026-10-31 拍板：成片跟着短，不冻帧、不回灌原片）。
        piece_dur = need
        if tail_slack <= 0:
            have = assemble._probe_duration(gen) if gen.exists() else 0.0
            if 0 < have < need:
                if need - have > _TAIL_TOL:
                    # 差太多就不是"平台固定少给 0.3 秒"了，别偷偷出个短片
                    raise assemble.ShortClip(gen, need=need, have=have)
                piece_dur = have
                log.warning(
                    "第 %d 段模型只给了 %.3fs（需要 %.3fs，差 %.3fs）："
                    "按实际长度收口，成片结尾跟着短 %.3fs",
                    n, have, need, need - have, need - have)
        pieces.append(_normalize(gen, work / f"piece_{n:03d}.mp4", piece_dur,
                                 width, height, fps))
        prev_generated = True
    return pieces


def prepare(rec: dict, *, prompt: str = "", spec: dict | None = None,
            refs: dict[str, Path] | None = None,
            subject_image: Path | None = None, subject_asset: str = "",
            channel: str = "auto", model: str = "",
            inventory: dict | None = None,
            style_video: Path | None = None,
            compute_looks: bool = False) -> dict:
    """给外部（逐镜分诊）用的公开入口：先算好通道和提示词，再决定切几段。

    `compute_looks=True` 只在**真出片**那条路传：外观描述缺失时当场补算一次
    （几厘钱），否则该人物在提示词里只剩一个图号、换不上脸。
    """
    return _prepare(rec=rec, prompt=prompt, spec=spec, refs=refs,
                    subject_image=subject_image, subject_asset=subject_asset,
                    channel=channel, model=model, inventory=inventory,
                    style_video=style_video, compute_looks=compute_looks)


def plan_spans(video: Path, rec: dict,
               plan: dict) -> tuple[list[tuple[float, float]], int]:
    """整片重制要切哪几段 —— **只算，不提交任何生成**。

    预览（`clone_pipeline.preview_render`）和出片（`replace_whole`）都调这一个函数，
    这样"预览报几段、几秒"和"实际送模型的是哪几段"不可能飘。参照 hypit：`plan` 和
    `build` 读同一张图，plan 不请求在线 Provider。

    返回 (spans, 被挪动的切点数)。挪切点 = 硬切出来的边界挪到画面最静处。
    """
    total = float((rec.get("source") or {}).get("duration") or 0)
    limit = plan["limit"]
    floor = _min_for(plan["ch"], plan["model"])
    spans = split_longest(plan_chunks(rec.get("shots") or [], total, limit,
                                      min_sec=floor), limit, min_sec=floor)
    # 切完可能留下 1–2 秒的尾巴（模型不收），统一收到 [floor, limit]
    spans = fit_spans(spans, limit, min_sec=floor)
    # 硬切出来的切点（一镜到底没有镜头边界可用）挪到画面变化最小的时刻
    hard = list(spans)
    spans = refine_cuts(video, spans, rec.get("shots") or [], min_sec=floor,
                        max_sec=limit)
    moved = sum(1 for x, y in zip(hard, spans) if abs(x[1] - y[1]) > 1e-6)
    # 🩸 2.0 专属：切点最后吸附到整数秒（官方 A-4「生成长度与输入严格一致」）。
    #   放在 refine_cuts **之后** —— refine 是按画面动静挪切点的，挪完再取整。
    #   在这里做（而不是只在出片时做），是为了让预览报的段和真正送模型的段
    #   不可能飘（本函数开头那条原则）。2.5 / H3 不受影响。
    spans = snap_for_plan(plan, spans, min_sec=floor, max_sec=limit)
    return spans, moved


def _ensure_shot_source(cid: str, video: Path, inventory: dict | None, *,
                        wanted: bool) -> tuple[dict | None, bool]:
    """正文要逐镜画面描述的那几家（`Caps.ensure_shot_source`），缺料时补一次。

    🩸 **只在缺料时补一次，且只在那几家补。** 2.0 / 2.5 的提示词不读 `shots`，
    补了对它们没有任何影响 —— 所以这条判定挂在**能力参数**上，不是挂在"通道名"上。
    （以前这里是 `if ch != "minimax"`，和调用方的 `caps.ensure_shot_source`
    是两条独立判断，加第 4 家就会自相矛盾。）
    补的判断依据是"当前 schema 版本的缓存文件在不在"：补过一次就会留下它，
    下次不会再花钱；模型即使没给出逐镜描述也不会反复重跑。
    失败一律退回原盘点，绝不挡出片。
    """
    if not wanted:
        return inventory, False
    if (inventory or {}).get("shots"):
        return inventory, False
    try:
        from app.services import vision_plan

        if vision_plan.cache_path_current(cid, video).exists():
            # 新版口径已经看过这条片子，只是它没给出逐镜描述 —— 不重复花钱
            return inventory, False
        log.info("H3 缺逐镜画面描述，补一次盘点（同一份源片，不额外上传）")
        return vision_plan.inventory(cid, video, refresh=True), True
    except Exception as e:  # noqa: BLE001
        log.warning("补盘点失败，H3 正文退回关系句写法：%s", e)
        return inventory, False


def replace_spans(
    video: Path,
    rec: dict,
    spans: list[tuple[float, float]],
    *,
    cid: str,
    prompt: str = "",
    spec: dict | None = None,
    refs: dict[str, Path] | None = None,
    subject_image: Path | None = None,
    subject_asset: str = "",
    channel: str = "auto",
    model: str = "",
    plan: dict | None = None,
    inventory: dict | None = None,
    style_video: Path | None = None,
    workdir: Path,
    progress=None,
    max_segments: int = 0,
    force: bool = False,
) -> list[Path]:
    """按给定区间重制，返回**实际生成了的**片段（`max_segments`>0 时可能比 spans 短）。

    和 replace_whole 的区别只有一个：**只送该送的那几段**。
    整片重制把原片整条喂给模型，既贵又改动了本来不该动的地方。
    plan 已经算过就直接用，免得把通道和提示词算两遍。
    """
    if not cid:
        raise EditError("缺少任务号，无法生成原片临时链接")
    plan = plan or prepare(rec=rec, prompt=prompt, spec=spec, refs=refs,
                           subject_image=subject_image,
                           subject_asset=subject_asset, channel=channel,
                           model=model, inventory=inventory,
                           style_video=style_video,
                           # 真出片：缺外观描述就当场补算（`/plan` 那条路不传）
                           compute_looks=True)
    # H3 缺逐镜描述时补一次盘点，并用新盘点把提示词重算一遍 ——
    # 提示词里的每个人的描述和正文的逐镜描述必须出自同一份盘点。
    if _plan_adapter(plan).caps.ensure_shot_source:
        inv2, refilled = _ensure_shot_source(cid, video, inventory, wanted=True)
        if refilled:
            plan = _prepare(rec=rec, prompt=prompt, spec=spec, refs=refs,
                            subject_image=subject_image,
                            subject_asset=subject_asset, channel=channel,
                            model=model, inventory=inv2,
                            style_video=style_video,
                            compute_looks=True)
    return _gen_spans(plan, video, spans, rec=rec, cid=cid, workdir=workdir,
                      progress=progress, label="重制", base_pct=52, span_pct=18,
                      max_segments=max_segments, force=force)


def replace_whole(
    video: Path,
    rec: dict,
    *,
    cid: str,
    prompt: str = "",
    spec: dict | None = None,
    refs: dict[str, Path] | None = None,
    subject_image: Path | None = None,
    subject_asset: str = "",
    channel: str = "auto",
    model: str = "",
    inventory: dict | None = None,
    style_video: Path | None = None,
    workdir: Path,
    progress=None,
    max_segments: int = 0,
    force: bool = False,
) -> dict:
    """整片重制。返回 {video, channel, chunks, seconds[, partial, preview]}。

    🩸 `max_segments`>0 = 只出前 N 段（主人要的「先出一段看看」）：
    这时**不拼接成片**（缺段拼出来的片子是残的），返回里带
    `partial=True` 和 `preview`（第一段的路径），调用方据此走预览分支。

    spec  是结构化规格（edit_spec）：换什么 + 保什么，编译成提示词。
    refs  是各槽位的本机参考图 {person|product|scene: Path}；
          person 也可以用 subject_asset（火山认可的肖像素材）代替。
    prompt 是旧接口的"补充说明"，没有 spec 时按老规矩包成换人/编辑提示词。
    """
    if not cid:
        raise EditError("缺少任务号，无法生成原片临时链接")
    plan = _prepare(rec=rec, prompt=prompt, spec=spec, refs=refs,
                    subject_image=subject_image, subject_asset=subject_asset,
                    channel=channel, model=model, inventory=inventory,
                    style_video=style_video,
                    # 真出片：缺外观描述就当场补算（`/plan` 那条路不传）
                    compute_looks=True)
    # 同 `replace_spans`：H3 缺逐镜描述就先补盘点，再按新盘点重算提示词
    if _plan_adapter(plan).caps.ensure_shot_source:
        inv2, refilled = _ensure_shot_source(cid, video, inventory, wanted=True)
        if refilled:
            plan = _prepare(rec=rec, prompt=prompt, spec=spec, refs=refs,
                            subject_image=subject_image,
                            subject_asset=subject_asset, channel=channel,
                            model=model, inventory=inv2,
                            style_video=style_video,
                            compute_looks=True)

    total = float((rec.get("source") or {}).get("duration") or 0)
    spans, moved = plan_spans(video, rec, plan)

    # 盘点判定"这一段不用换"的刀数：对账时要能看出"哪些段其实没花钱"
    acts = _span_plan(plan, spans)
    kept = sum(1 for act, _ in acts.values() if act == "keep")
    work = workdir / "whole"
    pieces = _gen_spans(plan, video, spans, rec=rec, cid=cid, workdir=work,
                        progress=progress, label="画面重制",
                        max_segments=max_segments, force=force)
    if kept:
        _p(progress, f"{kept} 段盘点无目标人物，保留原片未重画", 74)
    # 🩸 只跑了前几段时**绝不拼接**：缺段拼出来的片子时长和内容都是残的，
    #   用户会误以为这就是成片。返回 preview 让他先看这一段。
    if max_segments and len(pieces) < len(spans):
        _p(progress, f"已出前 {len(pieces)} 段（共 {len(spans)} 段），先看这一段", 75)
        return {"video": pieces[0] if pieces else None,
                "preview": pieces[0] if pieces else None,
                "partial": True,
                "done_segments": len(pieces), "total_segments": len(spans),
                "channel": plan["ch"], "model": plan["model"],
                "label": spec_label(plan["ch"], plan["model"]),
                "resolution": plan["resolution"],
                "chunks": len(spans), "seconds": total,
                "cuts_refined": moved,
                "boundary": _boundary_used(plan, spans, acts,
                                           shots=rec.get("shots") or []),
                "kept": kept}
    out = work / "whole.mp4"
    _concat(pieces, out, work)
    _p(progress, "画面重制完成", 75)
    return {"video": out, "channel": plan["ch"], "model": plan["model"],
            # 用户对账第一句就是"我测的到底是哪一款、哪一档清晰度"——
            # 结果页要能原样显示，别让人回来看日志
            "label": spec_label(plan["ch"], plan["model"]),
            "resolution": plan["resolution"],
            "chunks": len(spans), "seconds": total,
            # 分段怎么来的：几段、几个切点被挪到画面最静处、段间有没有尾帧衔接、
            # 有几段因为"盘点里没这个人"而直接留了原片（省钱，也要能对账）
            # 🩸 boundary 必须按**实际有没有带**报，不能只看"分了几段"：
            # 结果页会照着它写"段间用尾帧衔接"，多段但没带就是骗用户。
            "cuts_refined": moved,
            "boundary": _boundary_used(plan, spans, acts,
                                       shots=rec.get("shots") or []),
            "kept": kept}


def _public_url(seg: Path, cid: str) -> str:
    """火山只收公网 URL。优先走 OSS（和大鲸同一条链路），没配 OSS 才退回签名链接。

    OSS 是正路：素材本来就要落到公网，签名链接还得反过来要求本服务有域名。
    """
    from app.services import oss, signed_url

    if oss.available():
        return oss.upload(seg)
    url = signed_url.make(cid, seg=seg.name)
    if not url:
        raise EditError(
            "火山通道需要公网地址：请配 VT_OSS_ACCESS_KEY_ID / VT_OSS_ACCESS_KEY_SECRET，"
            "或给本服务配 VT_PUBLIC_BASE_URL"
        )
    return url


def _ark_res(height: int, width: int = 0) -> str:
    """自动档（"跟原片"）挑哪个分辨率。

    按**短边**挑 —— 720p/1080p 说的都是短边；只按 height 判断会把横屏
    1920×1080 判成 720p（横屏视频 height 是短边，竖屏才是长边）。

    🩸 封顶 1080p，不自动上 4k：
       - 4k 只有 2.0 标准版支持（官方：RPM 15 / 并发 1），价格也高一个档
       - 输出是 10bit H.265，部分手机播不了
       - 2.5 根本没有 4k，自动跳上去会被退回默认档，等于白降两档
    真要 4k，用户在清晰度里显式选（只有 2.0 标准版会列出这一档）。
    """
    short = min(width, height) if width else height
    if short >= 1000:
        return "1080p"
    if short >= 700:
        return "720p"
    return "480p"


# ---------------------------------------------------------------------------
# 参考视频的硬门槛（官方给的数字，越界＝提交即被拒，钱白花）
#
# 🩸 2026-10-26 L3 第三轮：两张表不再写在核心 —— 数字各回各家
# （`volc20.IMAGE_LIMITS` / `h3._H3_IMAGE_LIMITS` 等，由 `Caps` 带出来）。
# 核心只负责"按门槛校验"，不负责知道门槛是多少。


def _fit_image(src: Path, ch: str) -> Path:
    """参考图先收进厂商官方硬门槛再发；本来就在范围内就原样返回。

    超了是**同步 400**（不是效果差一点）。宽高比改不了，只能如实报错；
    边长/体积可以本机重编码，不花钱。
    """
    lim = models.adapter_for(channel=ch).caps.image_limits
    if not lim or not src.exists():
        return src
    try:
        info = scene.probe(src)
    except Exception as e:  # noqa: BLE001
        log.warning("参考图探测失败，原样送：%s", e)
        return src
    w, h = int(info.get("width") or 0), int(info.get("height") or 0)
    if not (w and h):
        return src
    lo, hi = lim["side"]
    rl, rh = lim["ratio"]
    r = w / h
    if r < rl or r > rh:
        raise EditError(
            f"参考图宽高比 {r:.2f} 超出 {ch} 收的 {rl}–{rh}，请先裁成正常比例再试"
        )
    if min(w, h) < lo:
        # 官方下限是"必须够"，放大只是插值，不会长出新细节 —— 换人靠的就是这张脸，
        # 与其放大后花一次钱出一张糊的，不如提前说清楚。
        raise EditError(
            f"参考图太小（{w}×{h}）：{ch} 要求短边 ≥{lo}px，请换一张清晰的照片"
        )
    scale = 1.0
    if max(w, h) > hi:
        scale = hi / max(w, h)
    size = src.stat().st_size
    if abs(scale - 1.0) < 0.01 and size <= lim["max_bytes"]:
        return src

    nw = max(2, int(round(w * scale)) // 2 * 2)
    nh = max(2, int(round(h * scale)) // 2 * 2)
    dest = src.with_name(src.stem + "_fit.jpg")
    for q in (3, 8, 15):
        args = ["-i", str(src), "-vf", f"scale={nw}:{nh}:flags=lanczos",
                "-q:v", str(q), "-frames:v", "1", str(dest)]
        proc = assemble._run(args, cwd=src.parent)
        if proc.returncode != 0 or not dest.exists():
            log.warning("参考图重编码失败，原样送：%s", (proc.stderr or "")[-200:])
            return src
        if dest.stat().st_size <= lim["max_bytes"]:
            break
    else:
        raise EditError(f"参考图压到 {nw}×{nh} 仍超过 {lim['max_bytes'] // 1024 // 1024}MB")
    log.info("参考图超范围，已重编码 %dx%d → %dx%d（%.1fMB）",
             w, h, nw, nh, dest.stat().st_size / 1024 / 1024)
    return dest




def _clean_cuts(cuts, span: float) -> list[float]:
    """段内切点：排序、去重、丢掉越界，保证**严格递增**（官方 `base-en:86`）。

    原文：「Use sequential shot numbers for later shots, and begin each one with a
    **strictly increasing** cut time that falls within the video duration」。

    `cuts` 是**相对段起点**的秒数，正常来自按时间排好的 `shots`，本来就递增；
    这里只做一道防御：重复 / 倒退 / 越界（`<=0` 或 `>=span`）的那一刀直接丢掉。
    丢一个切点只是少切一刀（调用侧 `seg_looks` 的数量校验会跟着失效 → 退回关系句），
    但把乱序时间码写进提示词会让**镜头号和时间线整体错位**，比少切一刀糟得多。
    """
    out: list[float] = []
    for c in sorted(round(float(x), 3) for x in (cuts or [])):
        if 0 < c < span and (not out or c > out[-1]):
            out.append(c)
    return out


def _align_8n1(seconds: float, fps: float) -> int:
    """段长 → 最近的 **8n+1** 帧数（给 Seedance 2.5 的编辑任务当输入）。

    出处：官方《Seedance 2.5 提示词写作指南》`:696-703`「编辑前后时长不一致」
    ——「视频编辑任务的输出比原视频短约 0.33 秒」；「解决方案 2. 保持编辑任务时，
    将输入视频的帧数调整为 **8n+1**（n 为正整数），输出时长即可与原视频保持一致」。
    同篇 `:719` 的例子：输入 161 帧（6 秒 17 帧）→ 输出同为 161 帧，时长一致。

    误差上限 3.5 帧（30fps 下约 0.12 秒），比原来的 0.33 秒小一个量级；
    多/少的那几帧照旧由 `_normalize` 按原段长裁掉或冻帧补上。
    """
    if fps <= 0 or seconds <= 0:
        return 0
    n_frames = max(1, int(round(seconds * fps)))
    n = max(1, int(round((n_frames - 1) / 8.0)))
    return 8 * n + 1


def _fit_segment(seg: Path, ch: str, frames: int = 0,
                 keep_audio: bool = False) -> Path:
    """把要送进模型的片段压到厂商收的范围内；本来就在范围内就原样返回。

    这三项不过关都是**同步 400**：像素太少/太多、帧率超范围、文件超大小。
    重编码只是本机 CPU，不花钱 —— 比提交一次被拒划算得多。
    """
    lim = models.adapter_for(channel=ch).caps.video_limits
    if not lim:
        return seg
    try:
        info = scene.probe(seg)
    except Exception as e:  # noqa: BLE001
        log.warning("片段探测失败，原样送：%s", e)
        return seg

    w, h = int(info.get("width") or 0), int(info.get("height") or 0)
    fps = float(info.get("fps") or 0)
    size = seg.stat().st_size if seg.exists() else 0
    if not (w and h):
        return seg

    lo_side, hi_side = lim["side"]
    lo_r, hi_r = lim["ratio"]
    scale, new_fps = 1.0, fps
    px = w * h
    if lim["min_px"] and px < lim["min_px"]:
        scale = max(scale, (lim["min_px"] * 1.02 / px) ** 0.5)
    if lim["max_px"] and px > lim["max_px"]:
        scale = min(scale, (lim["max_px"] * 0.98 / px) ** 0.5)
    if min(w, h) * scale < lo_side:
        scale = max(scale, lo_side / min(w, h))
    if max(w, h) * scale > hi_side:
        scale = min(scale, hi_side / max(w, h))
    r = w / h
    if r < lo_r or r > hi_r:
        # 宽高比是改不了的（改了画面就变形），只能如实报错
        raise EditError(
            f"参考片段宽高比 {r:.2f} 超出 {ch} 收的 {lo_r}–{hi_r}，"
            f"请先把原片裁成正常比例再试"
        )
    if fps and (fps < lim["fps"][0] or fps > lim["fps"][1]):
        new_fps = min(max(fps, lim["fps"][0]), lim["fps"][1])

    # 🩸🩸 2026-10-30（真机 `6d26558d` 报 400 抓到）：像素门槛是**硬性**的，
    #   差 1.6% 也是 400。现场：原片 `480×836 = 401,280 px`，2.0 mini 的 r2v
    #   下限是 407,696，只差 6,416 像素（1.6%）。
    #   下面那句 `abs(scale-1.0) < 0.02` 本意是"缩放不到 2% 不值得重编码一遍"，
    #   但它把**硬门槛**也一起放过了 → 片段原样送进去 → 火山当场拒单：
    #   `video pixel count … must be greater than or equal to 407696`。
    #   ⇒ 像素不在区间内时**必须**重编码，不许走"差别太小"那条捷径。
    px_out_of_range = bool(
        (lim["min_px"] and px < lim["min_px"])
        or (lim["max_px"] and px > lim["max_px"]))
    too_big = size > lim["max_bytes"]
    if (not px_out_of_range and abs(scale - 1.0) < 0.02
            and abs(new_fps - fps) < 0.01 and not too_big):
        return seg

    dest = seg.with_name(seg.stem + "_fit.mp4")
    nw = max(2, int(round(w * scale)) // 2 * 2)
    nh = max(2, int(round(h * scale)) // 2 * 2)
    # 🩸 宽高各自取偶数后会再掉回线下一点，按高度补宽度直到过线
    #   （与 `extend.normalize_ref` 同一套补齐做法，别各写各的）。
    if lim["min_px"] and nw * nh < lim["min_px"]:
        nw = max(nw, int(-(-lim["min_px"] // nh)) + 1)
        nw += nw % 2
    # assemble._run 自己会补 ffmpeg 路径和 -y，这里不要再写一遍
    # 🩸 `keep_audio=True`（原声模式的 2.0，见 `_master_audio`）：这段音轨是给模型
    #   对口型用的，`-an` 会把它悄悄丢了 —— 而这一步只在**超规格**时才触发，
    #   表现就是"小片子的口型修好了、480×836 那种反而没好"，极难查。
    args = ["-i", str(seg),
            "-vf", f"scale={nw}:{nh}:flags=lanczos",
            *(["-c:a", "aac", "-b:a", "128k"] if keep_audio else ["-an"]),
            "-c:v", "libx264", "-crf", "20", "-preset", "veryfast",
            "-pix_fmt", "yuv420p"]
    if new_fps and abs(new_fps - fps) > 0.01:
        args += ["-r", f"{new_fps:g}"]
    if frames:
        # 改帧率会把 8n+1 打乱（帧数 = 新帧率 × 时长），这里再卡一次。
        # ⚠️ 这一段**平时用不上**：`_fit_segment` 只有在段超规格（像素/帧率/体积）
        # 时才重编码，正常段在这里早就 return 了（`abs(scale-1)<0.02` 那行）。
        # 留着是因为一旦改帧率，少了它 8n+1 就被悄悄破掉，出片会短 0.33 秒
        # 而且没人看得出为什么。
        args += ["-frames:v", str(int(frames))]
    if too_big:
        # 按"目标大小留 20% 余量"反推码率，别让重编码完还是超
        dur = float(info.get("duration") or 0) or 1.0
        kbps = max(400, int(lim["max_bytes"] * 0.8 * 8 / dur / 1000))
        args += ["-b:v", f"{kbps}k", "-maxrate", f"{kbps}k", "-bufsize", f"{kbps*2}k"]
    args.append(str(dest))
    proc = assemble._run(args, cwd=seg.parent)
    if proc.returncode != 0 or not dest.exists():
        log.warning("参考片段重编码失败，原样送：%s", (proc.stderr or "")[-200:])
        return seg
    log.info("参考片段超范围，已重编码 %dx%d@%.0f → %dx%d@%.0f（%.1fMB）",
             w, h, fps, nw, nh, new_fps or fps, dest.stat().st_size / 1024 / 1024)
    return dest


def _manifest(work: Path) -> dict:
    p = work / "manifest.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save_manifest(work: Path, data: dict) -> None:
    p = work / "manifest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def _write_request(work: Path, n: int, *, ch: str, plan: dict, dur: float,
                   prompt: str, video_url: str, refs: list, has_audio: bool,
                   ref_video: Path | None = None, shape: str = "",
                   master_audio: bool = False) -> None:
    """把**真正发出去的请求**落盘（`request_<段号>.json`）。

    两个用途，都不能省：
      ① 出事时不用猜 —— 以前只看得到 `refs=2` 一行汇总；
      ② 复用判定 —— `work._scan_assets` 拿它当资产签名里的通道/型号/分辨率/
         提示词。没这份快照的段，只能记成"提示词未知"，永远不给复用。
    写失败只告警：它是可观测性，不是出片的正确性依赖。

    🩸 **还要记下"身份锚点是什么"**：参考图的内容哈希 + 提示词里有没有用外观描述。
    两次换脸复盘都卡在同一处 —— 参考图在出片后被换成另一张，磁盘上只剩文件名，
    谁也说不清当时到底送的是哪张图、那句描述是不是它的。记下哈希，
    下次对一眼就知道是"这张图本来就没换成功"还是"送错图了"。
    """
    try:
        ref_names, ref_sha = [], []
        for x in refs:
            if isinstance(x, str):
                ref_names.append(x)
                ref_sha.append(x if x.startswith("asset:") else "")
                continue
            ref_names.append(Path(x).name)
            try:
                ref_sha.append(hashlib.sha1(Path(x).read_bytes()).hexdigest()[:16])
            except Exception:  # noqa: BLE001
                ref_sha.append("")
        look = plan.get("look") or {}
        (work / f"request_{n:03d}.json").write_text(
            json.dumps({
                "channel": ch, "model": plan["model"],
                "resolution": plan["resolution"], "duration": dur,
                "prompt": prompt,
                "video_url": video_url,
                "ref_images": ref_names,
                "ref_sha1": ref_sha,
                # 身份锚点：这句描述是不是真的写进了提示词、写的是哪一段
                "subject_look": {
                    # 只认「真出现在最终提示词里」，不认「准备过」。
                    # 🩸 2026-10-30：原来写 `(en or zh) in prompt` —— 有英文就只查英文，
                    # 中文提示词里永远查不到 ⇒ **这盏灯恒为 false**（我照着它下过错误结论）。
                    "used": _look_used(look, prompt),
                    # 🩸 2026-11-01：以前写死 `zh or en` —— H3 正文是英文，实际发出去的
                    # 是 en，快照却记着 zh，回头对账时"记下的那句"根本不是发出去那句。
                    # 现在按**正文里实际出现的那句**认（见 `_look_text`）。
                    "text": _look_text(look, prompt),
                    # 逐槽位各记各的：第 2 个人发的是他自己那句，不再和第一个混在一起
                    "by_slot": {
                        s: {"used": _look_used(v, prompt),
                            "text": _look_text(v, prompt)}
                        for s, v in (plan.get("looks") or {}).items()
                    },
                },
                "audio": bool(has_audio),
                # 音频在这段里的**载具**：母版自带音轨 / 独立 reference_audio。
                # 2.0 的形状闸要求恰好一条，这里记清楚是哪一条。
                "audio_in_master": bool(master_audio),
                # 请求形状签名（`sd20_request_shape` 的产物）：1v+1i+1a+8s
                "shape": shape,
                # 风格参考视频（A9）：送的是哪一段、内容哈希多少
                "ref_video": Path(ref_video).name if ref_video else "",
                "ref_video_sha1": (_ref_sig(ref_video)[5:] if ref_video else ""),
            }, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        log.warning("请求快照写入失败：%s", e)


def _look_ir(look) -> str:
    """交给官方改写器的外观描述：**优先中文**（改写器的输入是中文），没有退回英文。

    🩸 2026-11-02：官方 `h3-manual:248`「如果素材中有非常想要保持的特征，建议
    明确写出来」。这份文本是定妆照自己的描述文件里存的，不是在这里现编的；
    不传它，改写器产出的 `<Subject 1>` 只有发型和衣服、零个五官词，成片不换脸。
    """
    if not isinstance(look, dict):
        return str(look or "").strip()
    return str(look.get("zh") or look.get("en") or "").strip()


def _look_text(look: dict, prompt: str) -> str:
    """这次**真正发出去**的是哪一句外观描述。

    🩸 2026-11-01：快照以前写死 `zh or en`，可 H3 的六段正文必须是英文 ——
    实际发出去的是 `en`，快照却记着 `zh`。"当时送的是哪一句"对不上账，
    复盘时会把一句正确的话当成错的（今天就是这么误判过一次）。
    判法**不写死厂商**：提示词里出现哪句就记哪句；都没出现（没被采用）时，
    按正文自身的语言选 —— 中文正文发 zh、英文正文发 en。
    """
    zh = str((look or {}).get("zh") or "").strip()
    en = str((look or {}).get("en") or "").strip()
    txt = prompt or ""
    if en and en in txt:
        return en[:300]
    if zh and zh in txt:
        return zh[:300]
    if zh and en:
        return (en if not re.search(r"[一-鿿]", txt) else zh)[:300]
    return (zh or en)[:300]


def _look_used(look: dict, prompt: str) -> bool:
    """参考图那个人的外观描述**到底有没有真的进提示词**（不是"读到过"）。

    🩸 2026-10-30（主人：「为什么只换了衣服没换脸！」）：原来写的是
    `(en or zh) in prompt` —— 有英文时只查英文，而提示词是中文，
    **永远查不到 ⇒ 恒 false**，我照着这盏坏灯下过一次错误结论（"描述被丢了"）。
    现在中英都查；2.0 定义句用的是从 zh 抽出来的**短特征短语**（子串），
    所以那句也得查一遍，否则描述真写进去了它还报 false。
    """
    zh = str((look or {}).get("zh") or "").strip()
    en = str((look or {}).get("en") or "").strip()
    probes = [x for x in (zh, en) if x]
    if zh:
        try:
            from app.services.edit_spec import _feat_phrase

            p = _feat_phrase(zh, cloth=False, sd20=True)
            if p:
                probes.append(p)
        except Exception:  # noqa: BLE001
            pass
    txt = prompt or ""
    return any(x in txt for x in probes)


def _ref_sig(x) -> str:
    """参考图指纹：素材 ID 直接进键，文件按内容哈希（同名换图也能区分）。"""
    if isinstance(x, str):
        return f"asset:{x}"
    try:
        h = hashlib.sha1(Path(x).read_bytes()).hexdigest()[:12]
        return f"file:{h}"
    except Exception:  # noqa: BLE001
        return f"file:{x}"


def _cache_file(cid: str, key: str) -> Path:
    """任务级生成缓存的文件名（`data/clone/<cid>/cache/whole/`）。

    🩸 为什么不能只靠出片目录里的 manifest：每次点「出片」都会新建一个
    `render/<rid>/`，清单跟着新目录走 → 跨次点击永远命中不了，
    界面上那句「同一提示词重跑不重复扣费」就成了假话。缓存必须挂在**任务**下。
    """
    return (clone_store.task_dir(cid) / "cache" / "whole"
            / (hashlib.sha1(key.encode("utf-8")).hexdigest()[:16] + ".mp4"))


def _cache_get(cid: str, key: str, dest: Path) -> bool:
    try:
        p = _cache_file(cid, key)
        if p.exists() and p.stat().st_size > 1024:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, dest)
            return True
    except Exception as e:  # noqa: BLE001
        # 缓存是省钱手段，不是正确性依赖：读不到就当没命中，别把出片搞挂
        log.warning("读生成缓存失败（按未命中继续）：%s", e)
    return False


def _cache_put(cid: str, key: str, src: Path) -> None:
    try:
        p = _cache_file(cid, key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(f".{p.name}.{os.getpid()}.tmp")
        shutil.copyfile(src, tmp)
        # 原子落位：exists() 就代表写完了，并发时不会读到半个文件
        os.replace(tmp, p)
    except Exception as e:  # noqa: BLE001
        log.warning("写生成缓存失败（不影响这次出片）：%s", e)


def _normalize(src: Path, dest: Path, dur: float, w: int, h: int, fps: float) -> Path:
    """规格化到统一尺寸/帧率/时长，后面 concat 才能 -c copy。"""
    assemble._normalize(src, dest, start=0.0, dur=max(0.2, dur), w=w, h=h,
                        fps=fps or 30.0)
    return dest


def _concat(pieces: list[Path], out: Path, work: Path) -> Path:
    lst = work / "pieces.txt"
    lst.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in pieces),
        encoding="utf-8",
    )
    proc = assemble._run(
        ["-f", "concat", "-safe", "0", "-i", str(lst.resolve()),
         "-c", "copy", str(out.resolve())],
        cwd=work,
    )
    if proc.returncode != 0 or not out.exists():
        raise EditError(f"拼接失败: {(proc.stderr or '')[-400:]}")
    return out


def _p(cb, stage: str, pct: int) -> None:
    if cb:
        try:
            cb(stage, pct)
        except Exception:  # noqa: BLE001
            pass
