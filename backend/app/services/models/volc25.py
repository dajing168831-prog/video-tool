"""火山 Seedance 2.5（本文件只管 2.5；2.0 的口径**不许**搬过来）。

官方差异：
  · 同一套 `@图片N` 标号，但**编辑任务用外观称谓指人**（`sd25-guide:1203-1209`
    「视频中深色衣服的男子」），字母只出现在**生成类**模板
  · 编辑任务走 `edit_task_param`（官方编辑参数形态）
  · 时长 4–30s，参考图最多 30 张
  · **不挂**官方兜底包（2.0 挂）
"""
from __future__ import annotations

import re

from app.services import model_specs
from app.services.models import register
from app.services.models.base import Caps, ModelAdapter
from app.services.models.volc25_compile import CL25

# 🩸 2026-10-28：平台层共用件从 `volc_common` 取，**不再从 `volc20` 取**
#   —— 以前 import 2.0 的模块 = 2.5 认识 2.0（跨家引用，分离门看不见）。
#   两家现在平级，谁也不依赖谁。
from app.services.models.volc_common import (  # noqa: E402
    IMAGE_LIMITS as _VOLC_IMAGE_LIMITS,
    VIDEO_LIMITS as _VOLC_VIDEO_LIMITS,
    VOLC_RES_ALIAS as _VOLC_RES_ALIAS,
    VOLC_RESOLUTIONS as _VOLC_RESOLUTIONS,
    error_hint as _error_hint,
    ready as _ready,
    ready_error as _ready_error,
    submit as _submit_common,
)


#: 🩸 2026-10-28：**必须和 `model_specs.volc()` 认同一批写法**。
#:   `model_specs` 用子串匹配（`"seedance-2-5" in m`），短名 `seedance-2-5` 它认；
#:   而注册表用前缀匹配 —— 只有 `doubao-seedance-2-5` 时，短名会落到"通道默认"，
#:   也就是**2.0 的适配器**，再靠 2.0 编译器里那段静默兜底转回 2.5。
#:   两套口径不一致 = 一条藏在中间的缝：同一个型号在两个地方有两个家。
#:   兜底已删（改成抛错），这里把短名补上，让两边认同一批。
PREFIXES = ("doubao-seedance-2-5", "seedance-2-5", "seedance-2.5")
DEFAULT_ID = "doubao-seedance-2-5-260628"


def _compile(spec: dict, *, channel: str = "volc", **kw) -> str:
    """火山 2.5：共用准备 + 本家渲染。**不判断"是哪一家"** —— 那是注册表的事。"""
    from app.services import edit_spec
    from app.services.models import volc25_compile
    c, idx, people = edit_spec.compile_context(
        spec, person_asset=kw.get("person_asset", ""),
        source_person=kw.get("source_person"),
        source_people=kw.get("source_people"), slots=kw.get("slots"))
    return volc25_compile._volc_25(
        spec, c, idx, people=people,
        frame_people=kw.get("frame_people"),
        audio_ref=bool(kw.get("audio_ref")), desc_by_id=kw.get("desc_by_id"),
        shot_cuts=kw.get("shot_cuts"),
        boundary_pic=int(kw.get("boundary_pic") or 0),
        shot_lines=kw.get("shot_lines"), style_video=bool(kw.get("style_video")))


def _gate(inventory=None, slots=None, person_ids=None, spec=None, **kw) -> None:
    from app.services import video_edit
    video_edit.require_identifiable_volc25(inventory, slots, person_ids)


def _submit(ctx: dict) -> tuple:
    """2.5 发请求跟 2.0 共用同一段传输逻辑，**唯一差别**是不生成音轨。

    🩸 2026-10-28：那段传输逻辑本身已搬到平台层 `volc_common.submit()`，
    这里直接用它 —— 不再是「2.5 调 2.0」。"""
    return _submit_common(ctx, generate_audio=False)


# ---------------------------------------------------------------------------
# 视频延长（向前/向后）—— 官方「视频延长模板」六句（`sd25-pe:651-697`）

#: 延长「往后接什么」的四句预设。
#:
#: 🩸 原文出自 2.5 官方 `sd25-pe:528`：
#:   「只能延长**动作过程、反应、停顿或场景过渡**，例如让视线转移、呼吸变化、
#:     拿取过程和进入后的反应自然展开。**不得新增人物、主线事件或故事结果**，
#:     也不得用重复动作或空镜机械填满时间。」
#:   ⇒ 四个类别就是**官方列举本身**，这里只把类别写成一句能直接填进模板的话，
#:     **不新增任何剧情**（加剧情正好是官方禁止的那件事）。
#:   ⚠️ 只给 2.5：2.0 / H3 的延长没有这份列举，各自的入口继续用自由文本框。
EXTEND_MODES = {
    "action": "让画面里正在进行的动作过程自然展开",
    "reaction": "让人物对刚才发生的反应自然展开",
    "pause": "让画面自然停顿片刻",
    "scene": "让场景过渡自然完成",
}


def _clean_extend(content: str) -> str:
    """延长描述先过一遍台词与换行 —— **只 2.5**，2.0 的延长句式另一套不共用。

    🩸 官方 `sd25-pe:141`：「用户只给出带引号的台词片段…最终对白只能写成
      `{你一个外人}`」→ 裸引号不是台词标记，原样留着模型可能照着念错或不念。
      转换规则和主链路同一条（`volc25_compile._SPEECH_BEFORE`）：**引号前 16 字
      内要有说话动作**才转 `{}`，否则只是名词引用（「把标题改成"限时优惠"」），
      去掉引号就行，标成台词反而会被念出来。
    🩸 官方 `sd25-pe:867` 四个符号是**用户能合法写的**，一律原样留着、不清：
      `{}` 台词 · `<>` 音效 · `【】` 字幕 · `()` 音乐。
      （主链路清 `<>{}【】` 是因为那个框是"补充说明"；这里 `content` 是
      "续出来的这段里发生什么"，用户写字幕/音效是正当用法。）
    换行必须并掉：模板是 `随后，{content}。` 整句插入，带换行会把句子切断。
    """
    from app.services.models.volc25_compile import _SPEECH_BEFORE

    c = (content or "").strip()
    c = re.sub(r"(?:[ \t]*[\r\n]+[ \t]*)+", "，", c)

    def _repl(m: re.Match) -> str:
        head = c[max(0, m.start() - 16):m.start()]
        return ("{" + m.group(1) + "}") if _SPEECH_BEFORE.search(head) \
            else m.group(1)

    return re.sub(r"[“\"]([^“”\"\n]{1,60})[”\"]", _repl, c)


def _extend_prompt(direction: str, content: str) -> str:
    """Seedance 2.5 的延长提示词：官方模板原句。

    🩸 为什么 2.5 不能只用 2.0 那一句：官方 `:643` 写「同一主体始终只有
    一个连续实例，不得复制、分裂或生成第二个相同主体」，`:645` 再加一句
    「最终 Prompt **必须明确写出**上述单一实例和拓扑要求，**不能只在内部分析中
    检查后省略**」。只写触发句 = 把官方要求的那几句全省了。
    🩸 官方模板里的 `<主体姿态与朝向>` 这类是**槽位占位符**（`:324` 要求全部替换）。
    我们手上只有用户写的新内容，没有原片边界的逐项数值 —— 所以按官方句式保留
    "保持…连续" 这层通用表述、去掉尖括号占位符，不替用户编具体姿态/光线。
    🩸 2.0 **不走这里**：2.0 的延长句式是 `seedance-20-guide` 那一套，别混。
    """
    c = _clean_extend(content)
    if direction == "front":
        return "\n".join([
            "@视频1是需要向前延长的原视频。",
            f"向前延长@视频1。在原视频开始之前，{c}。",
            "延长片段的最后一个画面自然衔接@视频1的首帧：保持主体姿态与朝向、"
            "道具位置、背景与空间关系、机位与构图、光线、声音状态和运动趋势一致。",
            "延长过程中保持人物身份与服装、关键道具、背景布局、摄影轴线和"
            "原有声音环境连续。",
            "同一主体始终保持为同一个连续对象，不重复、不分裂；人物外形或"
            "物体部件数量保持稳定。",
            "只属于原视频后续的角色、道具或特效不得提前出现。",
        ])
    return "\n".join([
        "@视频1是需要向后延长的原视频。",
        f"向后延长@视频1。延长片段的第一个画面直接承接@视频1的尾帧：保持"
        "主体姿态与朝向、道具位置、背景与空间关系、机位与构图、光线、声音状态"
        "和运动趋势连续。",
        f"随后，{c}。",
        "延长过程中保持人物身份与服装、关键道具、背景布局、摄影轴线和"
        "原有声音环境连续。",
        "同一主体始终保持为同一个连续对象，不重复、不分裂；人物外形或"
        "物体部件数量保持稳定。",
    ])


def _extend_submit(*, prompt, ref_src, seg, model, resolution, seconds,
                   with_audio, cid, ref_images=()) -> None:
    """2.5 的延长请求（火山只收公网 URL）。

    🩸 2026-10-28：**2.5 能带参考图，2.0 不能** —— 官方 `sd25-guide:93` 的延长示例是
      「向后延长 @video1，**@image1 的角色从天而降**」，参考图按 `reference_image`
      追加在待延长视频之后，`@图片N` 就是第 N 张。所以这里**不再复用 2.0 的提交**
      （那支没有图片通道），自己发；图片顺序由调用方按勾选顺序给，绝不重排。
    """
    from app.services import ark
    from app.services.video_edit import _public_url

    imgs = list(ref_images or [])
    ark.extend_video(
        prompt, video_url=_public_url(ref_src, cid), out=seg, model=model,
        resolution=resolution, duration=seconds,
        generate_audio=bool(with_audio),
        ref_images=(imgs or None),
    )


_raw = dict(model_specs.volc(DEFAULT_ID))
_raw["prefixes"] = PREFIXES

def _agent_module():
    """本家「逐段指令」agent（`clone_agent` 就是 2.5 官方视频编辑模板那套）。"""
    from app.services import clone_agent

    return clone_agent


adapter = register(ModelAdapter(
    dialect=CL25,
    caps=Caps(model_id=DEFAULT_ID, family="volc",
              max_dur=float(_raw.get("max_sec") or 30),
              min_dur=float(_raw.get("min_sec") or 4),
              ref_audio=bool(_raw.get("ref_audio")),
              edit_task_param=True,
              default_resolution=str(_raw.get("default_resolution") or "720p"),
              asset_id=True, auto_res_from_frame=True,
              align_8n1=True,                # 参考段帧数卡 8n+1（2.5 编辑任务）
              boundary_pic=True,             # 边界帧走【时间线继承】模板内定义
              # 2.5 官方全文「大头照」「全身照」各 **0 次**（2026-10-26 grep 实测），
              # 写法是「一人一图、每张写全属性」（`sd25-pe:227`）⇒ 一个人只发一张。
              split_person_images=False,
              max_ref_images=int(_raw.get("max_ref_images") or 0),
              auto_prefer={"asset": 0, "none": 0, "file": 1},
              # 🩸 2026-10-31：2.0 下架后，2.5 是火山唯一在售的编辑档，
              #   由它担任通道代表（`adapter_for(channel="volc")` 的兜底 caps）。
              is_channel_default=True,
              default_model_setting="ark_video_edit_model",
              display_name="火山 Seedance 2.5",
              boundary_by_edit_task=True,    # 2.5 有 {edit_task_param} → 照带
              image_limits=_VOLC_IMAGE_LIMITS, video_limits=_VOLC_VIDEO_LIMITS,
              resolutions=_VOLC_RESOLUTIONS, resolution_alias=_VOLC_RES_ALIAS,
              # 延长：2.5 指南明确拼接处无痕迹 → 不裁（裁了反而掉内容）
              extend_seam=(0, 0), extend_transition=True,
              # 延长能带参考图（官方 `sd25-guide:93` 延长示例带 `@image1`）
              extend_ref_images=True,
              # 延长「往后接什么」的四句预设（`sd25-pe:528` 的四个类别）
              extend_modes=dict(EXTEND_MODES),
              # 参考视频像素门槛与 2.0 同源（方舟对 r2v 的统一限制）
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
    agent=_agent_module,
    extend_prompt=_extend_prompt,
    extend_submit=_extend_submit,
))
