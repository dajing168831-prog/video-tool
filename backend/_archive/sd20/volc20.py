"""火山 Seedance 2.0（本文件只管 2.0；2.5 的口径**不许**搬过来）。

官方差异（各按各家，见 `docs/MODEL-SEPARATION.md`）：
  · 标号语法 `@图片N` / `@视频1`（`sd2-pe`）
  · 编辑任务**不写**人物外观特征（官方示例的 `<新特征>` 位只有图号）
  · 时长 4–15s（fast 只到 720p）
  · **挂官方兜底包**（2.5 不挂）
"""
from __future__ import annotations

import logging

from app.services import model_specs
from app.services.models import register
from app.services.models.base import Caps, ModelAdapter
from app.services.models.volc20_compile import CL20

log = logging.getLogger(__name__)

#: 认这几档型号（小写前缀）。核心不认识这些字符串 —— 只有本文件认识自己。
#: 🩸 2026-10-28：短名也要认 —— `model_specs.volc()` 用子串匹配，`seedance-2-0`
#:   它当成 2.0；注册表只有 `doubao-…` 时会把短名落到"通道默认"，两边口径不一致。
PREFIXES = ("doubao-seedance-2-0", "seedance-2-0", "seedance-2.0")
DEFAULT_ID = "doubao-seedance-2-0-mini-260615"

# 🩸 2026-10-28：以下这些是**火山平台层**的共用件（素材门槛 / 清晰度档位 /
#   提交链路 / 没配好时的报错），2.0 和 2.5 都要用。它们搬到了
#   `models/volc_common.py` —— 以前写在本文件里、由 `volc25.py` 反过来 import，
#   等于 2.5 认识 2.0（跨家引用，分离门的盲区）。
#   这里保留同名别名，注册表那一块不用改。
from app.services.models.volc_common import (  # noqa: E402
    IMAGE_LIMITS,
    VIDEO_LIMITS,
    VOLC_RES_ALIAS,
    VOLC_RESOLUTIONS,
    error_hint as _error_hint,
    ready as _ready,
    ready_error as _ready_error,
    submit as _submit,
)


# ---------------------------------------------------------------------------
# 视频延长（向前/向后）—— 2.0 的官方句式，2.5 的口径**不许**搬过来

def _extend_prompt(direction: str, content: str) -> str:
    """官方推荐句式：「向后延长@视频1，生成…」/「向前延长@视频1，生成…」。

    内容由使用者写 —— 我们不替人编剧情，只把他的描述套进官方句式。
    """
    content = (content or "").strip()
    if direction == "front":
        return f"向前延长@视频1，生成{content}"
    return f"向后延长@视频1，生成{content}"


def _extend_submit(*, prompt, ref_src, seg, model, resolution, seconds,
                   with_audio, cid, ref_images=()) -> None:
    """火山延长请求（2.0）：只收公网 URL，复用出片那条链路。

    🩸 `ref_images` 只是**统一签名**：2.0 的延长不带参考图（官方 2.0 延长句式
      里没有图），真传了非空会在 `extend.run` 被闸拦下，走不到这里。
    """
    from app.services import ark
    from app.services.video_edit import _public_url

    ark.extend_video(
        prompt, video_url=_public_url(ref_src, cid), out=seg, model=model,
        resolution=resolution, duration=seconds,
        generate_audio=bool(with_audio),
    )


def _compile(spec: dict, *, channel: str = "volc", **kw) -> str:
    """火山 2.0：共用准备 + 本家渲染。**不判断"是哪一家"** —— 那是注册表的事。"""
    from app.services import edit_spec
    from app.services.models import volc20_compile
    c, idx, people = edit_spec.compile_context(
        spec, person_asset=kw.get("person_asset", ""),
        source_person=kw.get("source_person"),
        source_people=kw.get("source_people"), slots=kw.get("slots"))
    return volc20_compile._volc(
        spec, c, idx, model=kw.get("model", ""), people=people,
        frame_people=kw.get("frame_people"),
        audio_ref=bool(kw.get("audio_ref")), desc_by_id=kw.get("desc_by_id"),
        shot_cuts=kw.get("shot_cuts"),
        boundary_pic=int(kw.get("boundary_pic") or 0),
        shot_lines=kw.get("shot_lines"), style_video=bool(kw.get("style_video")),
        # 🩸 参考图里那个人的外观描述（`subject_desc.json`）。以前这里没转发，
        # 编译器拿不到 ⇒ 参考侧永远只有一句「@图片1中的人物」，官方 `:95`
        # 要的 2–3 个静态特征一个都没有。
        subject_look=kw.get("subject_look"))


def _gate(inventory=None, slots=None, person_ids=None, spec=None, **kw) -> None:
    from app.services import video_edit
    # 🩸 2026-10-28：闸要跟编译器用**同一把尺**，而 `sd20_locator` 已搬进
    #   `volc20_compile.py`（2.0 的认人尺）。由本文件把它传进去 ——
    #   共用层 `video_edit` 不 import 任何一家。
    # 🩸 2026-10-29（D70）：多人时编译器写的是「将其中的<主体N>/<特征短语>」，
    #   以前闸却只看「盘点描述互不互异」—— 两段描述不同、但都取不出人物短语时
    #   （以服装开头、没有人物中心词），编译器各写一句「其中的人物」，闸照放行。
    #   `sd20_multi_locator` 和编译器同一条优先级，把它一并传进去。
    from app.services.models.volc20_compile import (sd20_locator,
                                                   sd20_multi_locator)
    video_edit.require_identifiable_volc20(inventory, slots, person_ids,
                                           locator=sd20_locator,
                                           locator_multi=sd20_multi_locator)


_raw = dict(model_specs.volc(DEFAULT_ID))
_raw["prefixes"] = PREFIXES

adapter = register(ModelAdapter(
    dialect=CL20,
    caps=Caps(model_id=DEFAULT_ID, family="volc",
              max_dur=float(_raw.get("max_sec") or 15),
              min_dur=float(_raw.get("min_sec") or 4),
              ref_audio=bool(_raw.get("ref_audio")),
              edit_task_param=False,
              default_resolution=str(_raw.get("default_resolution") or "720p"),
              # 🩸 2026-10-31：2.0 已从复刻爆款下架，**不再是火山通道代表**
              #   （代表 = 2.5）。适配器本身照旧注册 —— 提示词优化那条线要按
              #   型号取 2.0 的真实参数（`prompt_advice` 的 500 字建议靠它）。
              is_channel_default=False,
              asset_id=True, auto_res_from_frame=True,
              # 🩸 2026-10-26：**默认一张**。回原文逐句核过（台账 D48）：
              #   · `sd2-pe:66`「角色图 **1–2**（大头照 + 全身照）」→ 一张合规；
              #   · `sd20-guide:222` 官方实战案例就是「@图片 1：女主半身照」一张打全片；
              #   · `sd20-guide:305` 整节标题是「人脸参考**不准确**」——是**问题章节**，
              #     `:316` 的「额外准备一张」是补救增强，不是默认配置；
              #   · `sd20-guide:414`「人物参考图**优先使用单人独立照片**」。
              # 之前把它当默认，等于逼顾客每次传两张，而且实测（10-26 12:22）
              # 两张也没换住脸。产品口径：顾客只传一张，脸要占得够大（半身照）。
              split_person_images=False,
              max_ref_images=int(_raw.get("max_ref_images") or 0),
              auto_prefer={"asset": 0, "none": 0, "file": 1},
              default_model_setting="ark_video_edit_model",
              display_name="火山 Seedance",
              boundary_by_edit_task=True,    # 2.0 只有能钉死编辑任务类型才带边界帧
              # 换装缺素材**逐个查**（2026-10-27 那轮的口径，收在这里 ——
              # 核心层 `edit_spec` 不许认识型号名，分离门 2026-10-28 抓到的）
              wardrobe_check_per_person=True,
              resolutions=VOLC_RESOLUTIONS, resolution_alias=VOLC_RES_ALIAS,
              image_limits=IMAGE_LIMITS, video_limits=VIDEO_LIMITS,
              # 延长：2.0 指南 §「延长视频衔接处跳变」→ 前段末删 6 帧、后段头删 1 帧
              extend_seam=(6, 1), extend_transition=True,
              # 方舟对**参考视频**的总像素下限/上限（不是成片分辨率，是喂给模型那段）。
              # 出处（三条，2026-10-24 实报错复核）：
              #   · 接口报错原文：`the parameter video pixel count specified in the
              #     request must be greater than or equal to 407696 …`
              #   · 官方 API 文档 `volc-api:333`「总像素数 [614×664=407696,
              #     3326×2494=8295044]」
              #   · 第三方旁证也同数（ReShot 产品页、一篇动作参考裁决笔记）——
              #     官方原文已有，就不留它们的本机副本了（2026-10-28 归档）。
              extend_ref_mode="pixel_floor",
              extend_ref_min_px=407696, extend_ref_max_px=8295044,
              raw=_raw),
    specs_for=lambda m: model_specs.volc(m or DEFAULT_ID),
    pic=lambda n: f"@图片{n}",
    vid=lambda: "@视频1",
    compile=_compile,
    gate=_gate,
    submit=_submit,
    error_hint=_error_hint,
    ready=_ready,
    ready_error=_ready_error,
    extend_prompt=_extend_prompt,
    extend_submit=_extend_submit,
))
