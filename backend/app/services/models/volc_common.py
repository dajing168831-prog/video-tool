# -*- coding: utf-8 -*-
"""火山**平台层**共用件：2.0 和 2.5 都从这里取，谁也不依赖谁。

⚠️ 这里只放**火山接口的约定**：
  · 素材门槛（图片/视频的边长、比例、体积、像素）
  · 清晰度档位（火山收哪几个名字、别的通道转过来怎么映射）
  · 提交链路（公网 URL + `asset://` 入库 + 请求落盘）
  · 没配好时**分开说**是缺 key 还是缺公网地址

**不放任何一代的提示词口径**。2.0 的「保留原视频动作、位置、互动、镜头和背景。」
在 `volc20_compile._keep_point_edit()`；2.5 的五段模板在 `volc25_compile`。
写在这里的一句提示词 = 两家都会读到 = 串味。

🩸 2026-10-28 建这个文件的原因：
   这些原来全写在 `volc20.py` 里，`volc25.py` 反过来 import 它 ——
   **2.5 认识 2.0**。分离门抓不到：`IMAGE_LIMITS` / `_submit` 这些名字
   不带厂商字面量，正则看不见。
   搬到中间层之后两家平级；以后加第 3 代火山型号，也是从这里取，不用碰别人。
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

#: 参考图官方硬门槛（2026-10-21 抓自火山 1520757 / H3 创建任务接口）：
#: 边长 [300,6000] px、宽高比 [0.4,2.5]、单张 ≤30MB
IMAGE_LIMITS = {"side": (300, 6000), "ratio": (0.4, 2.5),
                "max_bytes": 30 * 1024 * 1024}
#: 参考视频官方硬门槛：总像素 [407696, 8295044]、边长 [300,6000]、
#: 宽高比 [0.4,2.5]、帧率 [24,60]、单文件 ≤200MB
#: 🩸 `max_sec` = 30.2：**送进去的参考视频**（r2v 的 `content[1]`）时长上限。
#:   2026-11-03 真跑实测（任务 `116928ec`）：切了 30.433s 的段直接 400 —
#:   「the parameter video duration (seconds) specified in the request must be
#:   less than or equal to **30.2** for model doubao-seedance-2-5 in r2v」。
#:   同一数值也是素材库入库闸（`ark_ingest._video_fits` 的 1.8–30.2，
#:   2026-10-21 逐档实测），两处是同一条平台限制。
#:   2.0 的段 ≤15s（`max_sec`），永远碰不到这条。
VIDEO_LIMITS = {"min_px": 407696, "max_px": 8295044, "side": (300, 6000),
                "ratio": (0.4, 2.5), "fps": (24.0, 60.0),
                "max_bytes": 200 * 1024 * 1024, "max_sec": 30.2}

#: 火山收的清晰度档位（**小写 p**，官方枚举就是这么写的）
VOLC_RESOLUTIONS = ("480p", "720p", "1080p", "4k")
#: 用户从另一家切过来时带来的档位名 → 火山这几档叫什么
VOLC_RES_ALIAS = {"768P": "720p", "2K": "1080p", "480P": "480p", "4K": "4k"}


def ready() -> bool:
    from app.services import video_edit
    return video_edit._volc_ready()


def ready_error() -> str:
    """火山没配好时，**分开说**是缺 key 还是缺公网地址。

    🩸 以前这两句写成两个 `if not _volc_ready()`，第一句永远先命中 →
    缺 OSS 的用户看到的是「请设置 VT_ARK_API_KEY」，照着改改不对。
    """
    from app.core.config import settings
    from app.services import oss

    if not (settings.ark_api_key or "").strip():
        return "火山通道未配置：请设置 VT_ARK_API_KEY"
    if not (oss.available() or (settings.public_base_url or "").strip()):
        return ("火山通道需要公网可访问的原片地址：请配 VT_OSS_ACCESS_KEY_ID / "
                "VT_OSS_ACCESS_KEY_SECRET（推荐），或配 VT_PUBLIC_BASE_URL")
    return ""


def error_hint(msg: str) -> str:
    from app.services import video_edit
    return video_edit._volc_hint(msg)


def submit(ctx: dict, *, generate_audio: bool = True) -> tuple:
    """把这一段发到火山 —— 公开 URL + `asset://` 入库。

    `generate_audio` 是**两代唯一不同的地方**：2.0 编辑任务要对口型必须生成音轨，
    2.5 保持原值不动（单独排查过）。2.5 那边只包一层传 `False`，不复制整段。
    """
    from pathlib import Path

    from app.services import ark, video_edit

    seg, cid, work, n = ctx["seg"], ctx["cid"], ctx["work"], ctx["n"]
    plan, dur = ctx["plan"], ctx["dur"]
    seg_prompt, seg_audio, style_clip = ctx["prompt"], ctx["audio"], ctx["style_clip"]
    refs_list, sent_ingest = ctx["refs"], ctx["ingest"]

    video_url = video_edit._public_url(seg, cid)
    refs_use = refs_list
    # 素材库：含真人的图/视频先入库换 asset://，否则火山逐次做人脸拦截
    # （400 PrivacyInformation）。AK/SK 没配就原样送，行为跟以前一致。
    try:
        from app.services import ark_ingest
        if ark_ingest.available():
            ing_v = ark_ingest.prepare_video(
                seg, cid, url=video_url, report=sent_ingest)
            if ing_v:
                video_url = ing_v
            refs_use = [
                (ark_ingest.prepare_image(Path(x), cid) or x)
                if not isinstance(x, str) else x
                for x in refs_list
            ]
    except Exception as e:  # noqa: BLE001
        log.warning("素材入库异常，本段退回直传：%s", e)
        sent_ingest["error"] = str(e)
    sent_video, sent_refs = video_url, list(refs_use)
    # 🩸 把**真正发出去的请求**落盘：以前只能看到 `refs=2` 一行汇总，
    # 出问题时要靠猜（2026-10-22 那次「原样返回」就是猜了一轮）。免费、不发网络。
    video_edit._write_request(work, n, ch="volc", plan=plan, dur=dur,
                              prompt=seg_prompt, video_url=video_url,
                              refs=refs_use, has_audio=bool(seg_audio),
                              ref_video=style_clip,
                              # 形状签名由 `_gen_spans` 在发请求前算好；
                              # 2.5 不跑那道闸，ctx 里没有这个键 → 空串。
                              shape=str(ctx.get("shape") or ""),
                              master_audio=bool(ctx.get("master_audio")))
    ark.edit_video(
        seg_prompt, video_url=video_url, out=ctx["out"],
        ref_images=refs_use,
        ref_audio=seg_audio,
        # 风格参考视频（A9）：火山只收公网 URL
        ref_videos=([video_edit._public_url(style_clip, cid)]
                    if style_clip else None),
        resolution=plan["resolution"],
        # 段长由 ark.edit_body 按型号改写：2.5 的编辑任务只能是 -1，
        # 2.0 则取**向上取整的整数秒**（输出时长 4~15s，`sd20.md:119`）
        duration=dur,
        model=plan["model"],
        # 🩸 2.0 编辑任务要对口型，就必须让模型**生成音轨**：
        #   `sd20-trouble` A-4「生成视频中的音频会与原本的参考音频有较大
        #   区别…最终导致口型对不上」⇒ 口型跟着**生成出来的那条音轨**走；
        #   `generate_audio=false` 输出的是无声视频（`volc-api:626`）。
        #   成片音轨仍然全部后期贴（`assemble._norm` 用 `-an` 丢掉模型音轨），
        #   这里只为拿口型。
        generate_audio=generate_audio,
    )
    return sent_video, sent_refs, sent_ingest
