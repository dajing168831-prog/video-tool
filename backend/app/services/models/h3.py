"""MiniMax H3（本文件只管 H3；火山的口径**不许**搬过来）。

官方差异：
  · 标签制 `<Subject N>` / `<Picture N>` / `<Video 1>` / `<Audio 1>`
  · 六段式正文，**正文必须是英文**（`ref-en:5`）→ 用户的中文自由文本在这里
    **自动翻成英文**（`pre_compile`），核心不知道有这回事
  · 只认本地文件，**不认火山 `asset://` 素材 ID**
  · 时长 5–15s（H3-Max 下限 5s），分辨率 768P / 2K
"""
from __future__ import annotations

from app.services import model_specs
from app.services.models import register
from app.services.models.base import Caps, ModelAdapter, NoDialect

PREFIXES = ("minimax",)
DEFAULT_ID = "MiniMax-H3"


def _compile(spec: dict, *, channel: str = "minimax", **kw) -> str:
    """MiniMax：共用准备 + 本家渲染。**不判断"是哪一家"** —— 那是注册表的事。"""
    from app.services import edit_spec
    from app.services.models import h3_compile
    c, idx, people = edit_spec.compile_context(
        spec, person_asset=kw.get("person_asset", ""),
        source_person=kw.get("source_person"),
        source_people=kw.get("source_people"), slots=kw.get("slots"))
    return h3_compile._minimax(
        spec, c, idx, people=people, frame_people=kw.get("frame_people"),
        audio_ref=bool(kw.get("audio_ref")), desc_by_id=kw.get("desc_by_id"),
        boundary_pic=int(kw.get("boundary_pic") or 0),
        shot_cuts=kw.get("shot_cuts"),
        subject_look=kw.get("subject_look") or {},
        subject_looks=kw.get("subject_looks") or {},
        shot_looks=kw.get("shot_looks"), shot_lines=kw.get("shot_lines"),
        style_video=bool(kw.get("style_video")))


def _gate(inventory=None, slots=None, person_ids=None, spec=None, **kw) -> None:
    from app.services import video_edit
    from app.services.models.h3_compile import h3_orig_locator
    video_edit.require_identifiable_h3(inventory, slots, locator=h3_orig_locator)


def _submit(ctx: dict) -> tuple:
    """把这一段发到 MiniMax —— 本地文件直传，没有公网 URL、没有素材入库。"""
    from app.services import minimax, video_edit

    seg, plan, dur = ctx["seg"], ctx["plan"], ctx["dur"]
    seg_prompt, seg_audio, style_clip = ctx["prompt"], ctx["audio"], ctx["style_clip"]
    refs_list = ctx["refs"]
    kind = ctx["ch"]

    # 这条快照是**复用判定**的唯一输入（见 `work._scan_assets`）：
    # 缺了它，这段资产只能记成"提示词未知"，永远不给复用。
    sent_video, sent_refs = f"file://{seg.name}", list(refs_list)
    video_edit._write_request(ctx["work"], ctx["n"], ch=kind, plan=plan, dur=dur,
                              prompt=seg_prompt, video_url="",
                              refs=refs_list, has_audio=bool(seg_audio),
                              ref_video=style_clip)
    minimax.reference_video(
        seg, prompt=seg_prompt, out=ctx["out"],
        ref_images=refs_list,
        ref_audio=seg_audio,
        # 风格参考视频（A9）：H3 收本地文件，自己上传
        ref_videos=([style_clip] if style_clip else None),
        duration=video_edit._gen_duration(dur, plan.get("model") or DEFAULT_ID),
        resolution=plan["resolution"],
        model=plan["model"],
    )
    return sent_video, sent_refs, {}


def _ready() -> bool:
    from app.services import minimax
    return minimax.available()


def _ready_error() -> str:
    from app.services import minimax
    if not minimax.available():
        return "MiniMax 通道未配置：请设置 VT_MINIMAX_API_KEY"
    return ""


def _pre_compile(spec: dict, **kw) -> None:
    """中文自由文本 → 英文（`ref-en:5` 六段正文必须英文）。

    🩸 挂在**这里**而不是核心：2.0 / 2.5 是中文原生提示词，一条规则都不许跨过来。
    """
    # 🩸 2026-10-28：翻译簇已从共用层 `video_edit` 搬进 H3 自己的编译器。
    from app.services.models import h3_compile
    h3_compile.h3_english_spec(spec)
    # 翻不了（接口挂 / 译文还是中文）→ 拦住，绝不把中文发出去
    h3_compile.require_english_extra(spec)


# ---------------------------------------------------------------------------
# 视频延长（向前/向后）—— H3 没有独立延长接口，靠提示词声明任务类型

def _extend_prompt(direction: str, content: str) -> str:
    """H3 的续写提示词：不是火山那套句式，是官方六段式 + `[video continuation]`。

    依据（工程内 `data/official/h3/ref-en.txt`，与官方 skill 同一份，sha1 一致）：
    - `:137` 任务类型 `video continuation` = "New content continues, extends, resumes,
      or transitions from an existing source video"；
    - `:32/:81` `<Video N>` 的用途原文含 "continuation starting point"、示例
      "Continuing from the end of an original video"；
    - `:130-141` summary 首行必须是方括号任务类型；
    - `:161-168` retention 只用四个固定值；`:207`「不要把新增的动作/背景/剧情
      当成参考保真度下降」→ 续写源片那条写 `fully_preserved`。
    🩸 别把火山的「向后延长@视频1，生成…」搬过来：H3 没有独立延长接口，
    任务类型只能靠提示词声明（项目内 `docs/CLONE-CHANNELS.md` §17 已核）。
    """
    content = (content or "").strip()
    back = direction != "front"
    if back:
        defs = ("<Video 1> is the source video being continued: the target video "
                "starts from its final frame and carries on from there.")
        summary = (f"[video continuation] The target video continues <Video 1> from "
                   f"its final frame: {content}.")
        ret = ("<Video 1> (continuation starting point): fully_preserved - the framing, "
               "subject identity, wardrobe, lighting and screen direction at the final "
               "frame of <Video 1> carry over into the opening of the target video.")
        shot = (f"[Shot 1] The video opens exactly on the last frame of <Video 1>, with "
                f"the same subject, wardrobe, framing, lighting and screen direction, "
                f"and then: {content}. The action develops continuously forward.")
    else:
        defs = ("<Video 1> is the source video the target video leads into: the target "
                "video ends on its first frame.")
        summary = (f"[video continuation] The target video is the new segment "
                   f"immediately before <Video 1> and ends where <Video 1> begins: "
                   f"{content}.")
        ret = ("<Video 1> (continuation end point): fully_preserved - the framing, "
               "subject identity, wardrobe, lighting and screen direction of the first "
               "frame of <Video 1> are reached by the final frame of the target video.")
        shot = (f"[Shot 1] The video shows {content}, and ends exactly on the first "
                f"frame of <Video 1> with the same subject, wardrobe, framing, "
                f"lighting and screen direction. The action develops continuously "
                f"toward that point.")
    return "\n".join([
        "subject_definitions:", defs,
        "", "summary:", summary,
        "", "retention_analysis:", ret,
        "", "detailed_description:", shot,
        "", "overall_soundscape:",
        # 官方 `ref-en:284`：声景段只写环境音与物理音；续写没有音频素材，
        # 只能让它顺接源片的声音环境（不凭空加配乐）。
        "Ambience and physical sounds continue the setting of <Video 1> "
        "throughout the target video.",
        "", "non_diegetic_music:", "N/A",
    ])


def _extend_submit(*, prompt, ref_src, seg, model, resolution, seconds,
                   with_audio, cid, ref_images=()) -> None:
    """H3 续写：本地文件直传，没有公网 URL、没有像素下限。

    🩸 时长/体积上限已经在 `prep_ref` 里截过了（`Caps.extend_ref_mode="clip"`），
    这里只管发。

    🩸 `ref_images` 只是**统一签名**：H3 的续写没有图片通道，真传了非空会在
      `extend.run` 被闸拦下。
    """
    from app.services import minimax

    minimax.reference_video(
        ref_src, prompt=prompt, out=seg, duration=seconds,
        resolution=resolution, model=model,
    )


#: H3 收的清晰度档位（**大写 P**，官方枚举就是这么写的：480P / 768P / 2K）
H3_RESOLUTIONS = ("480P", "768P", "2K")
#: 用户从火山切过来时带来的档位名 → H3 这几档叫什么
H3_RES_ALIAS = {"480p": "480P", "720p": "768P", "1080p": "2K", "4k": "2K"}

#: 参考图门槛（官方「传入单张图片要求」）：边长 [256,5760]、宽高比 [0.4,2.5]、≤30MB
_H3_IMAGE_LIMITS = {"side": (256, 5760), "ratio": (0.4, 2.5),
                    "max_bytes": 30 * 1024 * 1024}
#: 参考视频门槛（官方「输入媒体限制」）：边长 [256,5760]、宽高比 [0.4,2.5]、
#: 帧率 [23.976,60]、单文件 ≤50MB。**它没给总像素区间**，所以 min_px/max_px 是 0。
#: 🩸 帧率写成 24.0 会把 23.976 的片子无谓重编码一遍（每重编码一次掉一次画质）。
_H3_VIDEO_LIMITS = {"min_px": 0, "max_px": 0, "side": (256, 5760),
                    "ratio": (0.4, 2.5), "fps": (23.976, 60.0),
                    "max_bytes": 50 * 1024 * 1024}

_raw = dict(model_specs.minimax(DEFAULT_ID))
_raw["prefixes"] = PREFIXES


def _agent_module():
    """本家「逐段指令」agent：H3 的英文六段式（`h3_agent`），**不是** 2.5 那套。

    🩸 两套模板不通用（中文五段标记 vs 英文六段式），所以各挂各的。
    """
    from app.services import h3_agent

    return h3_agent

adapter = register(ModelAdapter(
    # H3 走六段式，不经过 `edit_spec._clauses` —— 占位即可（真被调到就报错）。
    dialect=NoDialect(),
    caps=Caps(model_id=DEFAULT_ID, family="minimax",
              max_dur=float(_raw.get("max_sec") or 15),
              min_dur=float(_raw.get("min_sec") or 4),
              ref_audio=bool(_raw.get("ref_audio")),
              # 🔓 2026-11-01 解冻：主人跑完 2.5 对照后要求恢复 H3。
              #   冻结机制保留（`models.frozen_families()` 由各家的 `Caps.frozen`
              #   声明），但这里不再声明冻结。
              frozen=False,
              edit_task_param=False,
              default_resolution=str(_raw.get("default_resolution") or "768P"),
              asset_id=False, auto_res_from_frame=False,
              # 中文编辑目标句里的标号（六段式正文用 `pic()` 的 `<Picture N>`）
              pic_inline="图{}", vid_inline="视频1",
              is_channel_default=True,
              shot_looks=True,               # 逐镜画面描述（六段式 detailed_description）
              drop_absent_people=True,       # 官方：每张发出去的图都要有定义
              boundary_pic=True,             # 边界帧走提示词内定义（ref-en:62）
              ensure_shot_source=True,       # 缺逐镜描述先补盘点再重算提示词
              max_ref_images=int(_raw.get("max_ref_images") or 0),
              auto_prefer={"file": 0, "none": 1, "asset": 1},
              default_model_setting="minimax_video_model",
              display_name="MiniMax H3",
              # 输入媒体门槛（官方「输入媒体限制」/「传入单张图片要求」）：
              # 图片 边长 [256,5760]、宽高比 [0.4,2.5]、单张 ≤30MB；
              # 视频 边长 [256,5760]、宽高比 [0.4,2.5]、帧率 [23.976,60]、
              #      单文件 ≤50MB（它没给总像素区间）
              image_limits=_H3_IMAGE_LIMITS, video_limits=_H3_VIDEO_LIMITS,
              resolutions=H3_RESOLUTIONS, resolution_alias=H3_RES_ALIAS,
              # 延长：官方没给任何接缝计帧规则（也没有保真度承诺）→ 不裁
              extend_seam=(0, 0), extend_transition=False,
              # H3 官方输入限制（`data/official/h3/ref-en.txt` / `CLONE-CHANNELS.md` §17）：
              # 参考视频 ≤3 段、**单段 [2,15]s、总时长 ≤15s**、单文件 ≤50MB。
              extend_ref_mode="clip",
              extend_ref_max_sec=15.0, extend_ref_max_mb=50.0,
              raw=_raw),
    specs_for=lambda m: model_specs.minimax(m or DEFAULT_ID),
    pic=lambda n: f"<Picture {n}>",
    vid=lambda: "<Video 1>",
    compile=_compile,
    gate=_gate,
    pre_compile=_pre_compile,
    submit=_submit,
    ready=_ready,
    ready_error=_ready_error,
    agent=_agent_module,
    extend_prompt=_extend_prompt,
    extend_submit=_extend_submit,
))
