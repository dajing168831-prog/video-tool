"""复刻功能 API。

流程分两段，和 pipeline 一样：
  POST /clone/analyze      贴链接 → 读结构 → 出配方（可复用）
  POST /clone/{cid}/render 配方 + 新文案 → 出片

两段都返回立即响应，真正的活在后台线程跑，前端轮询 GET /clone/{cid}。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.api.routes import PARSERS, ensure_video, fail, ok
from app.core.config import settings
from app.parsers.base import detect_platform, extract_url
from app.services import (
    clone_jobs,
    clone_pipeline,
    clone_store as store,
    edit_spec,
    media,
    models,
    pronounce as pronounce_mod,
    scene,
    signed_url,
    speech_est,
    storage,
    translate as translate_mod,
    video_edit,
    voice_catalog,
    work as work_mod,
)

log = logging.getLogger(__name__)
router = APIRouter()


def regen_model_error(model_id: str, ask_channel: str = "") -> str:
    """型号校验（出片 / 重生成 / 延长共用这一处口径）。**返回错误文案，空串 = 通过**。

    🩸 以前这段在三处各写一遍，靠 `in ("volc", "minimax")` 认通道、靠
    `model_specs.MODELS` 拼反查表 —— 加第 4 家三处都要改，而且两处写的是
    「文件里有没有这段字」，代码一改判据就假红。现在合成一处，问注册表。

    🧊 2026-10-31 复刻冻结 H3：冻结名单也**问注册表**（`models.frozen_families()`）。
    厂商名只能写在 `models/<家>.py` 的 `Caps.frozen` 里 —— 这里写一个
    `"minimax"` 字面量，分离门当场报「核心文件里新增厂商耦合」（已发生过一次）。
    """
    frozen = models.frozen_families()
    ask = (ask_channel or "").strip().lower()
    # 🩸 2026-11-01 解冻 H3 后，这里不再写「只支持 2.5」这种会过期的原因 ——
    #   文案只说明"不可用"，具体是哪一家由 `Caps.frozen` 决定。
    if ask in frozen:
        return "这条通道暂不可用"
    m = (model_id or "").strip()
    if not m:
        return ""
    fam = models.family_of_model(m)
    if fam is None:
        return "未知的模型"
    if fam in frozen:
        return "这个型号暂不可用"
    if ask in models.adapters_by_family() and fam != ask:
        return "所选模型不属于该通道"
    return ""


class AnalyzeIn(BaseModel):
    text: str = Field("", description="分享链接或整段分享文案")
    token: str = Field("", description="已解析过的任务 token（省一次下载）")


class EditIn(BaseModel):
    """换什么 + 声音 + 成片规格。

    🩸 「保什么」六个开关**不再对外**（P5）：它不是用户能回答的问题，
    而是提示词编译的固定部分（见 `edit_spec._keep_sentence`），默认全保。
    历史出片记录里的 `keep` 仍然被 `edit_spec.normalize` 接受（回放要用）。
    """

    # 换什么
    person: bool = False
    product: bool = False
    scene: bool = False
    wardrobe: bool = False
    # 视觉盘点里选中的人（P1/P2…）；留空 = 自动取主角。
    # 多人 = 传多个 id（最多 3 个，见 edit_spec.MAX_PERSONS）；`person_id` 是第一个，
    # 只为老客户端保留。
    person_ids: list[str] = Field(default_factory=list, description="选中的人，按槽位顺序")
    person_id: str = ""
    person_desc: str = ""
    product_desc: str = ""
    # 画面里**被换的是哪一件**（视觉盘点给的外观描述，只当定位词）
    product_target: str = ""
    product_target_en: str = ""
    scene_desc: str = ""
    wardrobe_desc: str = ""
    # 🩸 逐人换装描述（D55）：前端给**每个人**一个输入框，键 = 人的 id（P1/P2…）。
    #   和上面两处 `style_ref` 同一条规矩 —— **不声明就是静默丢键**：
    #   `normalize`（`edit_spec.py:281`）和三家编译器早就写好了读取逻辑，
    #   唯独这里没声明，于是线上这条数据从 2026-10-28 起一直进不来。
    #   ⚠️ 这是**共用请求模型**：三家编译器会同时开始收到这个字段（它们本来就该收到）。
    wardrobe_desc_by_id: dict[str, str] = Field(
        default_factory=dict, description="逐人换装描述：{人的 id: 描述}")
    # 换装名单：第 i 个人 → wardrobe / wardrobe2 …；空 = 老语义（全体一起换）
    wardrobe_ids: list[str] = Field(default_factory=list, description="要换装的人，按槽位顺序")
    # 🩸 2026-11-05 拆槽位（主人：「有排斥就拆槽位」）：换发型独立于换装。
    #   以前一律写成「…的服装修改为低马尾」—— `<原特征>` 用错词。
    #   官方 `sd20-guide:39`「将其中的<原特征>修改为<新特征>」的 `<原特征>`
    #   本来就是自由槽，`:95` 明确把「发型」列为可选核心特征之一。
    #   没有发型图片槽位：官方文件里没有任何"用图换发型"的句式。
    hair: bool = False
    hair_ids: list[str] = Field(default_factory=list, description="要换发型的人，按槽位顺序")
    hair_desc: str = ""
    hair_desc_by_id: dict[str, str] = Field(
        default_factory=dict, description="逐人发型描述：{人的 id: 描述}")
    # 谁在说话（MiniMax H3 用）：只有名单里的人拿 (Sx) 号
    speaker_ids: list[str] = Field(default_factory=list, description="说话人，按槽位顺序")
    style: str = Field("", description="live / anime / 3d / film / sketch，空=不改")
    # 🩸 风格参考（A9）：图和视频**互斥**，同一时间只有一个来源。
    # 🩸 这两行不是可有可无的"顺手补全"：pydantic 默认**丢掉未声明的键**，
    # `body.edit.model_dump()` 里没有它们的那些字段，前端传上来等于没传
    # （2026-10-25 实测：预览的提示词里没有一句 @视频2，而文件确实在）。
    style_ref: bool = Field(False, description="风格参考图（槽位 style_ref）")
    style_video: bool = Field(False, description="风格参考视频（和 style_ref 二选一）")
    # 声音：tts 全新配音 / mix 新配音叠原声 / original 只换画面保留原声（唱歌跳舞用这个）
    audio: str = Field("tts", description="tts / mix / original")
    # 🩸 原片声音的后期处理（C4）：同样**必须声明** —— 不声明就是静默丢键。
    # 这两项只影响合成阶段的混音，不进提示词、不进模型分段哈希。
    bgm: str = Field("keep", description="keep 保留原片背景音乐 / drop 删掉 / replace 换成上传的音乐")
    sfx: str = Field("keep", description="keep 保留原片音效 / add 再叠加一段上传的音效")
    # 🩸 无缝转场（B7）**不在出片规格里**：2026-10-25 主人拍板只留在延长链路
    # （`ExtendIn` 有自己的 transition 字段）。复刻要像原片，不该改原片剪辑点。
    # 🩸 2026-10-23 主人拍板「也不烧字幕」：`subtitle` 字段删除，成片不带任何字幕。
    # 成片规格
    resolution: str = Field("auto", description="auto / 480p / 720p / 1080p / 768P / 2K")
    extra: str = Field("", description="补充说明，原样拼进提示词")
    # 「一次只改一类」（2026-11-03）：**默认关**。打开后，同时勾了 ≥2 类改动
    # （人物/产品/场景/服装/风格）会在出片前被拦下。出处：官方 2.5 指南
    # 「复杂任务效果不稳定」→「将复杂任务拆解为多个简单任务」
    # （`data/official/sd25/pull-2026-11-03/prompt-guide.md:738`）。
    one_change: bool = Field(
        False, description="开启后每次只能改一类（人物/产品/场景/服装/风格），多类会被拦")


class RenderIn(BaseModel):
    script: str = Field(..., description="新文案")
    # 🩸 逐行文案（C6 多语种配音用）：翻译接口给的是**已经断好的行**，
    # 出片时必须原样用这些行，不能再过一遍 `_split_script` —— 它会把句子
    # 按 14 字合并/硬切，外语每行都带 TTS 头尾静音，实测总时长会涨到 1.68 倍。
    script_lines: list[str] | None = Field(
        None, description="逐行文案（翻译结果）；给了就不再按标点重新切句")
    # 🩸 只重配其中几个人（2026-10-27）：行号下标，指的是 `script_lines` 的哪几行。
    # 不传 / 空 = 整片都重配（老行为）。传了就是部分重配：
    #   · 音频：没点到的行保留**原片那个人的原声**，点到的行换新配音；
    #   · 提示词：没点到的行**整句不写**（2.0 官方 `:31` 未提及默认保持不变）。
    # 用行号不用人物 id：行号是这一单自己的事实，不受盘点/声纹判定影响。
    dub_lines: list[int] | None = Field(
        None, description="只重配这几行（script_lines 下标）；空=全部重配")
    # 🩸 每个人用自己的音色（2026-10-27）：行号 → 音色 ID。
    # 没传的行用整片那个 `tts_voice`。只影响**合成**，不进提示词。
    # 为什么不需要 `@音频2`：2.0 请求里 `generate_audio` 恒为 False（`ark.py:528`），
    # 模型不产出声音，成片音轨 100% 由我们自己合成 —— 音色只由这里决定。
    dub_voices: dict[str, str] | None = Field(
        None, description="每行用哪个音色（键=script_lines 下标）")
    # 🩸 方言（2026-10-27）：火山 `explicit_dialect`，官方取值八个
    # （beijing/dongbei/henan/shaanxi/shanghai/sichuan/tianjin/yue）。
    # 只有音色表里带 `dialects` 的 2.0 音色（Vivi/小何/云舟/小天）才吃这个参数。
    tts_dialect: str = Field("", description="方言代码，空=标准普通话")
    # 🩸 口音还原（2026-11-05）：火山 `tone_fidelity`，只对**复刻音色**（S_ 开头）生效。
    # 官方原文见 `providers/tts.py` synth() 里的注释（还原音色+情感+韵律+口音）。
    # 默认关 = 不改老客户端/老任务的出片效果；前端复刻面板里默认勾上。
    tts_fidelity: bool = Field(False, description="还原原片口音/韵律（仅复刻音色）")
    # 🩸 用户在试听里手调过的语速。不传 = 用估算自动算（老行为）。
    # 传了就必须用他的 —— 试听调好、出片又变回自动值，那功能就是假的。
    speech_rate: int | None = Field(
        None, ge=-30, le=30, description="语速 -30~30，正数=更快；空=按估算自动")
    # 🩸 2026-10-29 主人拍板改成**默认关**：遮罩是底 20% 的实心黑边
    #   （`drawbox` 无羽化，实测亮度 57→2.4、最亮像素 10/255），
    #   而且**无差别盖全片** —— AI 重绘段本来就被提示词禁了字幕，也跟着黑。
    #   更要命的是位置写死底 20%，跟真实字幕位置无关：拿一条真实成片量过，
    #   字幕在画面 61% 处，底部那条黑边什么都没盖住，纯自伤。
    #   前端「遮住原片底部字幕」开关保留，谁的原片字幕烦就手动开。
    mask_bottom: bool = Field(False, description="是否遮住原片底部硬字幕区域（默认关）")
    # 换画面：给了 regen_prompt 才会重绘镜头
    regen_prompt: str = Field("", description="把画面主体换成什么（原图当参考，构图不变）")
    regen_shots: list[int] | None = Field(None, description="指定要重绘的镜头序号（优先于比例）")
    # 换画面三种模式：
    #   auto  = 逐镜分诊（默认）：没勾的镜头保留原片像素，勾了的整段喂视频模型重制
    #           （2026-11-02 主人拍板删掉了「静态镜头走静帧重绘」那一档）
    #   shots = 按比例挑镜头、统一走静帧重绘（老行为的显式版本）
    #   whole = 整条片子交给视频编辑模型（兜底，最贵，改得最狠）
    # 🩸 P5：档位不再是用户的选择。对外只有一个默认 `auto`（每镜由系统定）；
    # `shots` / `whole` 是内部调度与老客户端的兼容值，不出现在界面上、不再当选项宣传。
    regen_mode: str = Field("auto", description="auto 逐镜分诊（默认）")
    regen_channel: str = Field("auto", description="auto / 具体通道（见 /health 的 channels）")
    regen_model: str = Field("", description="型号 ID；留空用该通道的默认型号")
    # 火山认可的肖像来源：虚拟人像库或已授权真人素材的 asset ID。
    # 有它就走火山（不受"禁止上传真人人脸"限制）；没有就用本地上传的图。
    subject_asset: str = Field("", description="asset://<id> 或纯 id")
    # 结构化规格：换什么 / 保什么 / 声音 / 成片规格。
    # 给了它就以它为准；没给则退回旧的 regen_prompt 单句模式。
    edit: EditIn | None = Field(None, description="换画面的结构化规格")
    # 读音校正：识别原文不动，只换送 TTS 那一份的念法（品牌名、缩写、价格）
    pronounce: dict[str, str] = Field(
        default_factory=dict, description="显示词 → 念法，例如 {\"XHS\":\"小红书\"}")
    tts_voice: str = Field("", description="音色 ID；留空用当前语言的默认音色")
    # 配音语言：影响音色默认值、语速估算和数字读法。留空 = 沿用分析阶段的判定
    # （分析时按识别原文判过一次，英文原片不会被当成中文配）。
    lang: str = Field("", description="zh / en；留空用分析阶段的判定")
    # 配音和画面长度差太多时，默认**不**硬出片。
    # 打开这个开关 = 用户明确接受"结尾补静音（配音短）/ 冻帧（配音长）"。
    allow_stretch: bool = Field(False, description="允许配音与画面强行对齐（结尾会补静音或冻帧）")
    # 🩸 只出前 N 段（2026-11-01 主人：「超过 1 段不能先生成一段满意再继续吗」）。
    #   0 / 不传 = 全部（老行为）。>0 = 只跑前 N 段、不拼接成片，先给用户看效果；
    #   确认后同样参数再出一次，前面的段命中缓存不重复扣费。
    max_segments: int = Field(0, ge=0, le=20,
                              description="只出前 N 段预览（0=全部）；继续出全部用同样的参数再调一次")
    # 🩸 2026-11-02 强制重跑：默认 False —— 同样的输入永远命中缓存（省钱，
    #   但模型是不确定的，失败了就再也抽不到第二次）。用户明确勾选才跳过
    #   逐段产物缓存、重新调模型（会再扣一次费）。
    force: bool = Field(False, description="跳过逐段缓存，强制重新生成（会重新扣费）")


class ExtendIn(BaseModel):
    """延长：在原片或某一版成片的前面/后面再接一段。

    官方把这件事拆成两步 —— 模型只产出"新的一段"，拼接由调用方做，
    所以这里要自己写清楚"延出来的这段里发生什么"，不然模型只能重复原片。
    """
    direction: str = Field("back", description="back 向后延长 / front 向前延长")
    seconds: int = Field(5, ge=2, le=30, description="延长多少秒（型号有上限，超了按上限收）")
    content: str = Field(..., description="延出来的这段里发生什么")
    base_render_id: str = Field("", description="基于哪一版成片；留空 = 基于原片")
    model: str = Field("", description="型号 ID；留空用默认编辑型号")
    resolution: str = Field("", description="留空按待延长视频的高度自动选 720p / 1080p")
    # 留空 = 原片有音轨就生成声音。延长段没声音、原片有声音，接起来会突然静音。
    with_audio: bool | None = Field(None, description="延长段是否生成声音")
    # 无缝转场（B7）：原片与新段之间的接缝用模型补一段过渡（每处多一条 4 秒生成）
    transition: bool = Field(False, description="接缝用模型补过渡")
    transition_desc: str = Field("", description="过渡怎么接，一句话（留空用官方骨架句）")
    # 🩸 参考图（2026-10-28）：官方 `sd25-guide:93` 延长示例「向后延长 @video1，
    #   @image1 的角色从天而降」—— 延长**可以**带图。这里给的是**任务里已有的
    #   素材槽位名**（person / product / scene / wardrobe…），顺序就是提示词里的
    #   `@图片1`、`@图片2`。只有声明了 `Caps.extend_ref_images` 的型号支持（2.5），
    #   别家传了会在 `extend.run` 当场报错，不会静默丢掉。
    ref_images: list[str] = Field(default_factory=list,
                                  description="带哪几张参考图（槽位名，顺序=图号）")
    # 预设续法（只有 2.5 有）：`action` / `reaction` / `pause` / `scene`。
    # 填了就不用写 content；真写了 content 以 content 为准。
    content_mode: str = Field("", description="预设续法（型号支持时可用）")


# ---------------------------------------------------------------------------
# 落片：把参考片放到复刻自己的目录里


async def _materialize(cid: str, meta: dict) -> Path:
    """把参考片落到 data/clone/<cid>/source.mp4。

    已经解析过的文件优先做硬链接（同一卷上是零拷贝，且不会因为解析任务
    过期清理而丢失）；跨卷或链接失败就退回复制。
    """
    dest = store.source_path(cid)
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)

    token = meta.get("token") or ""
    cached = storage.video_path(token) if token else None
    if cached and cached.exists():
        try:
            os.link(cached, dest)
            return dest
        except OSError:
            try:
                shutil.copy2(cached, dest)
                return dest
            except OSError as e:  # noqa: BLE001
                log.warning("参考片复制失败，改为重新下载: %s", e)

    part = dest.with_name(dest.name + ".part")
    try:
        await ensure_video(meta, part)
        part.replace(dest)
    finally:
        if part.exists():
            part.unlink(missing_ok=True)
    return dest


def _trim_if_long(cid: str, src: Path) -> tuple[Path, bool]:
    """默认**不截**：原片多长就分析多长。

    只有运维显式设了 `VT_CLONE_MAX_SECONDS > 0` 才截前 N 秒（防有人丢一整部电影进来）。
    """
    cap = float(settings.clone_max_seconds or 0)
    if cap <= 0:
        return src, False
    info = scene.probe(src)
    dur = float(info.get("duration") or 0)
    if dur <= cap:
        return src, False
    cut = store.task_dir(cid) / "source_cut.mp4"
    scene.cut_clip(src, 0, cap, cut)
    log.info("参考片 %.1fs 超过上限 %.0fs，截取前段", dur, cap)
    return cut, True


# ---------------------------------------------------------------------------


@router.get("/clone/history")
async def clone_history(limit: int = Query(50, ge=1, le=200)):
    return ok(store.history(limit))


class EstimateIn(BaseModel):
    text: str = Field("", description="新文案")
    cid: str = Field("", description="任务号；给了就用原片时长和语言做目标")
    target: float = Field(0.0, description="目标时长（秒）；给了 cid 时以原片为准")


@router.post("/clone/estimate")
async def clone_estimate(body: EstimateIn):
    """文案估时长 + 挑出要校正读音的词。

    纯本地计算，不花一分钱。前端在用户打字时调它，就能在**出片之前**告诉
    使用者"这条文案会念 18 秒，原片只有 12 秒"——而不是等配音做完才发现。

    注意本路由必须排在 `/clone/{cid}` 前面。
    """
    text = (body.text or "").strip()
    target = float(body.target or 0)
    lang = ""
    if body.cid:
        task = store.load(body.cid)
        if task and task.get("recipe"):
            rec = task["recipe"]
            target = float((rec.get("source") or {}).get("duration") or target)
            lang = ((rec.get("speech") or {}).get("lang") or "")

    out = {
        "candidates": pronounce_mod.detect(text),
        "target_seconds": round(target, 3),
    }
    out.update(speech_est.advise(text, target, lang or "zh"))
    return ok(out)


@router.get("/clone/models")
async def clone_models(channel: str = Query(
        "", description="具体通道名（见 /health 的 channels），留空返回全部")):
    """可选型号 + 每个型号各自收的清晰度档位。

    清晰度必须跟着型号走：不同型号能出的档位不一样（复刻现在只有 2.5：
    480p / 720p / 1080p）。前端如果写死一张档位表，就会出现「界面上能选、
    提交上去被降档或直接 400」—— 档位只能取这个接口给的。
    注意本路由必须排在 `/clone/{cid}` 前面，否则会被当成任务号。
    """
    from app.services import model_specs, models

    out = []
    for ch, items in model_specs.MODELS.items():
        if channel and channel != ch:
            continue
        # 取参数表、读默认型号都问**这条通道的代表适配器**（加第 4 家不用改这里）
        _ad = models.adapter_for(channel=ch)
        pick = _ad.specs_for
        default_id = (getattr(settings, _ad.caps.default_model_setting, "")
                      or _ad.model_id)
        for mid, label in items:
            s = pick(mid)
            out.append({
                "channel": ch,
                "id": mid,
                "label": label,
                "resolutions": list(s["resolutions"]),
                "default_resolution": s["default_resolution"],
                "min_sec": s["min_sec"],
                "max_sec": s["max_sec"],
                # 这个型号能换几个人：稳定线 / 硬上限。界面按它限制选人，
                # 超过稳定线先提示，超过硬上限引导切到能接住的型号。
                "stable_subjects": s.get("stable_subjects", 4),
                "max_subjects": s.get("max_subjects", 4),
                # 参考视频总时长上限（风格参考视频 A9 用）：界面据此提示
                # 「母版 + 风格片段装不装得下」，数字只有 model_specs 一份
                "ref_video_total_sec": s.get("ref_video_total_sec", 15),
                # 🩸 延长「往后接什么」的预设：**空 = 这家没有**，前端就继续用
                #    自由文本框。条目各在各家的适配器里（2.5 出自 `sd25-pe:528`），
                #    这里只做转发，不认识任何一家的文案。
                "extend_modes": dict(
                    models.adapter_for(model=mid, channel=ch).caps.extend_modes),
                "default": mid == default_id,
            })
    return ok(out)


@router.get("/clone/{cid}/recipe")
async def clone_recipe(cid: str):
    """导出配方：镜头表、逐句文案与时间、参数、以及每次出片用过的设置。

    干什么用：任务目录只留 3 天，但"这一版怎么切的、每镜多长、文案挂在哪一秒"
    是有价值的 —— 导出后随时能照着重做，也能拿去跟别人对。
    注意它是**配方**不是工程包：不含原片视频，重跑要重新给同一个链接或文件。
    """
    task = store.load(cid)
    if not task:
        return fail("任务不存在或已过期", biz_code=404)
    rec = task.get("recipe") or {}
    return ok({
        "version": 1,
        "kind": "clone-recipe",
        "exported_at": int(time.time()),
        "meta": task.get("meta") or {},
        "recipe": rec,
        # 出片记录里的参数（不含产物路径）：照着这些能复现同一版
        "renders": [
            {k: v for k, v in (r or {}).items()
             if k not in ("segments", "voice_meta", "regen_meta", "identity",
                          "contract", "state", "pct", "stage", "error",
                          "duration")}
            for r in (task.get("renders") or [])
        ],
    })


# 🩸 2026-10-23 主人拍板「也不烧字幕」：原 `GET /clone/caption/components`
# （字幕版式目录）随字幕功能一起删除。


@router.get("/clone/voices")
async def clone_voices(lang: str = Query("", description="语言代码（见返回的 languages），留空用任务的判定语言"),
                       cid: str = Query("", description="给了就按这个任务的判定语言过滤")):
    """可选配音音色（火山官方 2.0 列表）。

    音色 ID 全部来自官方音色表，不自己编 —— 编一个不存在的 ID，
    用户点下去就是一次合成失败，还看不出为什么。
    cid 用来拿分析阶段判定的语言：英文原片默认给英文音色。
    """
    from app.services import voice_catalog

    pick = (lang or "").strip().lower()
    if not pick and cid:
        task = store.load(cid)
        if task and task.get("recipe"):
            pick = ((task["recipe"].get("speech") or {}).get("lang") or "").lower()
    lang_eff = pick or "zh"
    default = voice_catalog.default_for(lang_eff)
    items = voice_catalog.list_for(lang_eff)
    # 默认音色排第一：90 条里翻起来很累，至少让人一眼看到"就用这个"
    items.sort(key=lambda v: 0 if v["id"] == default else 1)
    return ok({
        "lang": lang_eff,
        "default": default,
        # 可选语言由后端给（`app/data/voices.json` 里真实存在的前缀），
        # 前端不再维护第二份语言表 —— 两份表迟早会飘。
        "languages": voice_catalog.languages(),
        "stats": voice_catalog.summary(),
        "voices": items,
    })


@router.post("/clone/voices/train")
async def clone_voice_train(
    speaker_id: str = Form(..., description="控制台创建的音色槽位 ID，S_ 开头"),
    lang: str = Form("zh"),
    file: UploadFile = File(...),
):
    """用一段人声训练/更新复刻音色。

    训练会消耗一次复刻额度（官方：每个资源最多 15 次），所以先把素材转码、
    查大小，再提交 —— 别把额度浪费在一个坏文件上。
    """
    from app.services import voice_clone

    if not voice_clone.valid_speaker_id(speaker_id):
        return fail("音色槽位 ID 形状不对：应以 S_ 开头（在控制台「声音复刻」里创建）",
                    biz_code=8)
    suffix = Path(file.filename or "voice").suffix.lower() or ".wav"
    # 临时文件落任务盘（D 盘），别往系统盘漏
    settings.clone_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="voice_", suffix=suffix,
                                    dir=str(settings.clone_dir))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        data = await file.read()
        if not data:
            return fail("音频文件是空的", biz_code=9)
        if len(data) > voice_clone.MAX_BYTES:
            return fail(f"音频超过 10MB 上限（当前 {len(data) / 1024 / 1024:.1f}MB）",
                        biz_code=9)
        tmp.write_bytes(data)
        try:
            r = await asyncio.to_thread(voice_clone.train, speaker_id, tmp, lang)
        except voice_clone.VoiceCloneError as e:
            return fail(str(e)[:300], biz_code=8)
        return ok(r)
    finally:
        tmp.unlink(missing_ok=True)


@router.get("/clone/voices/train/{speaker_id}")
async def clone_voice_status(speaker_id: str):
    """查复刻训练状态；status=2/4 时可以直接拿去配音。"""
    from app.services import voice_clone

    try:
        return ok(await asyncio.to_thread(voice_clone.status, speaker_id))
    except voice_clone.VoiceCloneError as e:
        return fail(str(e)[:300], biz_code=8)


@router.post("/clone/analyze")
async def clone_analyze(body: AnalyzeIn):
    meta: dict | None = None
    if body.token:
        meta = storage.load_meta(body.token)
        if not meta:
            return fail("解析结果已过期，请重新粘贴链接", biz_code=404)
        meta.setdefault("token", body.token)
    else:
        url = extract_url(body.text or "")
        if not url:
            return fail("没有从文本里找到链接")
        platform = detect_platform(url)
        if not platform or platform not in PARSERS:
            return fail("不支持的平台或链接格式", biz_code=2)
        if platform not in settings.enabled_platforms:
            return fail(f"暂不支持 {platform}，请换其它平台链接", biz_code=2)
        try:
            info = await PARSERS[platform].parse(url)
        except Exception as e:  # noqa: BLE001
            log.exception("复刻解析失败")
            return fail(f"链接解析失败：{str(e)[:200]}", biz_code=3)
        if not info.is_video:
            return fail("该作品是图集，暂不支持复刻", biz_code=4)
        meta = info.__dict__.copy()
        meta["is_video"] = info.is_video

    if not meta.get("video_url") and (meta.get("extra") or {}).get("engine") != "ytdlp":
        return fail("该作品没有视频文件", biz_code=4)

    # 🩸 同一条原片刚解析过就复用那个作品：重贴一次链接不该在历史里多出一条
    # "0 版"的新作品（2026-10-22 主人实测：只出片一次，历史里却两条）。
    # 只认 24 小时内**分析成功且有配方**的；失败/进行中的不算。
    prev = store.find_recent_source(
        meta.get("platform") or "", meta.get("title") or "", meta.get("author") or "")
    if prev:
        log.info("同一原片 24 小时内已解析过，复用作品 %s", prev)
        return ok({"id": prev, "reused": True})

    cid = store.new_id()
    task = store.new_task(cid, meta={
        "platform": meta.get("platform"),
        "title": meta.get("title") or "",
        "author": meta.get("author") or "",
        "cover": meta.get("cover") or "",
        "url": meta.get("video_url") or "",
        "token": meta.get("token") or "",
    })
    store.save(task)

    try:
        src = await _materialize(cid, meta)
    except Exception as e:  # noqa: BLE001
        log.exception("参考片落盘失败 cid=%s", cid)
        task["state"] = "failed"
        task["error"] = f"参考片下载失败：{str(e)[:200]}"
        task["stage"] = "failed"
        store.save(task)
        return ok({"id": cid})

    try:
        src, truncated = _trim_if_long(cid, src)
        task["meta"]["truncated"] = truncated
        store.save(task)
    except Exception as e:  # noqa: BLE001
        log.exception("参考片处理失败 cid=%s", cid)
        task["state"] = "failed"
        task["error"] = f"参考片处理失败：{str(e)[:200]}"
        task["stage"] = "failed"
        store.save(task)
        return ok({"id": cid})

    clone_jobs.submit_analyze(cid, src, url=task["meta"].get("url", ""))
    return ok({"id": cid})


@router.post("/clone/upload")
async def clone_upload(file: UploadFile = File(...)):
    """上传本地视频开始复刻。

    和贴链接走的是同一条链路，只是"参考片"从下载变成上传。
    上传的视频通常本身就是作者自己的素材，没有平台叠加的水印。
    """
    cid = store.new_id()
    dest = store.source_path(cid)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")

    size = 0
    try:
        with part.open("wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > settings.max_video_bytes:
                    raise ValueError(
                        f"文件超过 {settings.max_video_bytes // 1024 // 1024}MB 上限"
                    )
                f.write(chunk)
        if size == 0:
            raise ValueError("文件是空的")
        part.replace(dest)
    except Exception as e:  # noqa: BLE001
        part.unlink(missing_ok=True)
        shutil.rmtree(store.task_dir(cid), ignore_errors=True)
        return fail(f"上传失败：{str(e)[:200]}", biz_code=9)

    try:
        info = scene.probe(dest)
        if not (info.get("width") and info.get("duration")):
            raise ValueError("这不是能识别的视频文件")
    except Exception as e:  # noqa: BLE001
        shutil.rmtree(store.task_dir(cid), ignore_errors=True)
        return fail(f"无法识别该文件：{str(e)[:120]}", biz_code=9)

    name = (file.filename or "上传视频").strip()
    task = store.new_task(cid, meta={
        "platform": "upload",
        "title": name,
        "author": "",
        "cover": "",
        "url": "",
        "token": "",
        "bytes": size,
    })
    store.save(task)

    try:
        src, truncated = _trim_if_long(cid, dest)
        task["meta"]["truncated"] = truncated
        store.save(task)
    except Exception as e:  # noqa: BLE001
        task["state"] = "failed"
        task["error"] = f"参考片处理失败：{str(e)[:200]}"
        task["stage"] = "failed"
        store.save(task)
        return ok({"id": cid})

    clone_jobs.submit_analyze(cid, src, url="")
    return ok({"id": cid, "bytes": size, "duration": info.get("duration")})


async def _save_ref(cid: str, slot: str, file: UploadFile):
    """落一张参考图到槽位。每个槽位只留一张 —— 多角度互相冲突，模型反而抓不准。"""
    task = store.load(cid)
    if not task:
        return fail("任务不存在或已过期", biz_code=404)
    if slot not in store.REF_SLOTS:
        return fail(f"未知的素材槽位：{slot}", biz_code=8)

    raw = await file.read()
    if not raw:
        return fail("文件是空的", biz_code=9)
    if len(raw) > 10 * 1024 * 1024:
        return fail("图片太大（上限 10MB）", biz_code=9)

    dest = store.ref_path(cid, slot)
    part = dest.with_name(dest.name + ".part")
    part.write_bytes(raw)
    try:
        info = scene.probe(part)
        if not (info.get("width") and info.get("height")):
            raise ValueError("不是能识别的图片")
    except Exception as e:  # noqa: BLE001
        part.unlink(missing_ok=True)
        return fail(f"无法识别该图片：{str(e)[:120]}", biz_code=9)
    # 官方 `sd25-guide:677`：非常规色度采样的 JPG，ffprobe 读得出宽高、
    # 我们照单放行，模型侧解码时才报 `invalid image: heic: decode failed` ——
    # 用户等了几分钟、钱也花了，才发现图根本进不去。**在上传这一步转正**。
    pix = str(info.get("pix_fmt") or "")
    if media.jpeg_needs_normalize(pix):
        fixed = part.with_name(part.name + ".fixed.jpg")
        if media.normalize_jpeg(part, fixed):
            fixed.replace(part)
            info = scene.probe(part)
            log.info("参考图采样格式 %s → 已转 yuvj420p（%s）", pix, slot)
        else:
            fixed.unlink(missing_ok=True)
            # 转不动就退回原样：宁可让模型侧报错，也不在这里吞掉用户的图
            log.warning("参考图采样格式 %s 转码失败，按原样保存（%s）", pix, slot)
    # 两家的硬门槛取交集：边长 300–5760px、宽高比 0.4–2.5。
    # 在这里挡住，比提交出片时被接口 400 掉好 —— 那时候用户已经等了几分钟
    w, h = int(info.get("width") or 0), int(info.get("height") or 0)
    if w and h:
        if not (300 <= w <= 5760 and 300 <= h <= 5760):
            part.unlink(missing_ok=True)
            return fail(f"图片边长 {w}×{h} 超出模型收的 300–5760 像素", biz_code=9)
        r = w / h
        if r < 0.4 or r > 2.5:
            part.unlink(missing_ok=True)
            return fail(f"图片宽高比 {r:.2f} 超出模型收的 0.4–2.5（约 2.5:1），请裁剪后再传",
                        biz_code=9)
    part.replace(dest)
    # 风格参考（A9）图 / 视频**互斥**：传了图就把视频删掉（理由见
    # `clone_style_video_upload`）。其它槽位不受影响。
    if slot == "style_ref":
        store.ref_video_path(cid, "style").unlink(missing_ok=True)
    task.setdefault("meta", {})["refs"] = {
        s: store.ref_path(cid, s).exists() for s in store.REF_SLOTS
    }
    task["meta"]["ref_videos"] = {
        "style": store.ref_video_path(cid, "style").exists()
    }
    task["meta"]["subject"] = task["meta"]["refs"]["person"]
    store.save(task)
    if slot in edit_spec.PERSON_SLOTS:
        # 官方两家都要求主体定义写具体特征（不是只给图号）：后台看一眼这张图，
        # 写下 2–3 个稳定静态特征，出片时写进提示词。失败不影响上传。
        # 🩸 一人一份：描述跟着**这个槽位**存，别让第二个人拿到第一个人的描述。
        _describe_person_async(cid, dest, slot)
    return ok({"slot": slot, "width": info.get("width"), "height": info.get("height")})


@router.post("/clone/{cid}/ref/{slot}")
async def clone_ref_upload(cid: str, slot: str, file: UploadFile = File(...)):
    """换人物/产品/场景/服装的参考图。slot = person | product | scene | wardrobe。"""
    return await _save_ref(cid, slot, file)


@router.delete("/clone/{cid}/ref/{slot}")
async def clone_ref_delete(cid: str, slot: str):
    """删掉某个槽位的参考图。

    🩸 换装/道具是"第 i 行 → 第 i 个槽位"，删掉中间一行时后面的图必须清掉重传：
    否则「第 3 件的包」会顶到第 2 格，静默把别人的东西换掉。
    """
    task = store.load(cid)
    if not task:
        return fail("任务不存在或已过期", biz_code=404)
    if slot not in store.REF_SLOTS:
        return fail(f"未知的素材槽位：{slot}", biz_code=8)
    p = store.ref_path(cid, slot)
    p.unlink(missing_ok=True)
    # 换了/删了参考图，旧的外观描述必须一起清 —— 否则下次拿旧描述去描述新人
    if slot in edit_spec.PERSON_SLOTS:
        store.subject_desc_path(cid, slot).unlink(missing_ok=True)
    task.setdefault("meta", {})["refs"] = {
        s: store.ref_path(cid, s).exists() for s in store.REF_SLOTS
    }
    task["meta"]["subject"] = task["meta"]["refs"]["person"]
    store.save(task)
    return ok({"slot": slot, "removed": True})


def _describe_person_async(cid: str, image: Path, slot: str = "person") -> None:
    """后台看一遍人物参考图，写下 2–3 个静态外观特征。

    🩸 **只有 MiniMax H3 会用这份描述**（火山 2.0 / 2.5 编辑任务的 `<新特征>`
    位官方示例只写图号，见 `edit_spec.compile_prompt` 的 docstring）。
    依据：H3 ref-en `:37` 正文要求 `subject_definitions` 解释
    "the main features to follow"；`:48-51` 的示例就是
    `<Subject 1> is …, with long dark hair, a blue cardigan, …`。
    这次调用失败不影响上传（`describe_person` 自己吞异常）。
    """
    import threading

    def run() -> None:
        try:
            from app.services import vision_plan

            vision_plan.describe_person(cid, image, slot)
        except Exception as e:  # noqa: BLE001
            log.warning("参考图外貌描述失败 cid=%s: %s", cid, e)

    threading.Thread(target=run, daemon=True).start()


@router.post("/clone/{cid}/subject")
async def clone_subject(cid: str, file: UploadFile = File(...)):
    """老接口：等价于 slot=person。保留给已发布的前端。"""
    return await _save_ref(cid, "person", file)


@router.get("/clone/{cid}/file/subject")
async def clone_subject_file(cid: str):
    p = store.subject_path(cid)
    if not p.exists():
        raise HTTPException(status_code=404, detail="没有上传换人参考图")
    return FileResponse(p, media_type="image/jpeg")


@router.get("/clone/{cid}/file/slot/{slot}")
async def clone_slot_file(cid: str, slot: str):
    if slot not in store.REF_SLOTS:
        raise HTTPException(status_code=400, detail="未知的素材槽位")
    p = store.ref_path(cid, slot)
    if not p.exists():
        raise HTTPException(status_code=404, detail="这个槽位还没有素材")
    return FileResponse(p, media_type="image/jpeg")


@router.get("/clone/{cid}/file/ref-video")
async def clone_ref_video_file(cid: str):
    """风格参考视频的预览（结果页/诊断页播放用）。"""
    p = store.ref_video_path(cid, "style")
    if not p.exists():
        raise HTTPException(status_code=404, detail="还没有上传风格参考视频")
    return FileResponse(p, media_type="video/mp4")


@router.post("/clone/{cid}/style-video")
async def clone_style_video_upload(cid: str, file: UploadFile = File(...)):
    """上传风格参考**视频**（A9）。

    🩸 和风格参考图**互斥**：传了这个就删掉那张图。风格只能有一个来源，
    两个来源打架时官方没有仲裁规则，模型会一半按图一半按片。
    官方门槛（三家取交集）：单段 2–15 秒、单文件 ≤50MB
    （`mm-docs:8273`；火山两家同口径）。总时长能不能再塞下这段母版，
    由 `video_edit.style_video_budget` 在出片前按型号算。
    """
    task = store.load(cid)
    if not task:
        return fail("任务不存在或已过期", biz_code=404)
    dest = store.ref_video_path(cid, "style")
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    size = 0
    try:
        with part.open("wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > 50 * 1024 * 1024:
                    raise ValueError("视频超过 50MB（三家参考视频的单文件上限）")
                f.write(chunk)
        if size == 0:
            raise ValueError("文件是空的")
        part.replace(dest)
    except Exception as e:  # noqa: BLE001
        part.unlink(missing_ok=True)
        return fail(f"上传失败：{str(e)[:200]}", biz_code=9)

    try:
        info = scene.probe(dest)
        dur = float(info.get("duration") or 0)
        if not (info.get("width") and dur):
            raise ValueError("这不是能识别的视频文件")
        # 上限 15s 是三家共同的最严值（火山 2.0/H3 单段 ≤15s）
        if not (2.0 <= dur <= 15.0):
            raise ValueError(f"参考视频单段要 2–15 秒（这段 {dur:.1f} 秒）")
    except Exception as e:  # noqa: BLE001
        dest.unlink(missing_ok=True)
        return fail(f"无法使用该视频：{str(e)[:160]}", biz_code=9)

    # 互斥的另一半：传了视频就把风格图删掉
    store.ref_path(cid, "style_ref").unlink(missing_ok=True)
    meta = task.setdefault("meta", {})
    meta["refs"] = {s: store.ref_path(cid, s).exists() for s in store.REF_SLOTS}
    meta["ref_videos"] = {"style": dest.exists()}
    store.save(task)
    return ok({"slot": "style", "duration": round(dur, 2), "bytes": size})


@router.delete("/clone/{cid}/style-video")
async def clone_style_video_delete(cid: str):
    task = store.load(cid)
    if not task:
        return fail("任务不存在或已过期", biz_code=404)
    p = store.ref_video_path(cid, "style")
    p.unlink(missing_ok=True)
    meta = task.setdefault("meta", {})
    meta["refs"] = {s: store.ref_path(cid, s).exists() for s in store.REF_SLOTS}
    meta["ref_videos"] = {"style": p.exists()}
    store.save(task)
    return ok({"slot": "style", "removed": True})


_AUDIO_MEDIA = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4",
                ".aac": "audio/aac", ".flac": "audio/flac", ".ogg": "audio/ogg",
                ".opus": "audio/opus"}


def audio_only_problem(info: dict) -> str:
    """纯音频校验。返回空串 = 合格，非空 = 拒绝原因。

    只查扩展名不够：把 mp4 改名成 .mp3 照样能传上来（2026-10-25 实测拦住了，
    ffprobe 读到 width 才认出是视频）。所以按**流**判，不按后缀判。
    """
    if not info.get("has_audio"):
        return "这个文件里没有音轨"
    if info.get("width"):
        return "这是带画面的视频；换背景音乐/加音效只收纯音频文件"
    return ""


@router.post("/clone/{cid}/audio/{kind}")
async def clone_audio_upload(cid: str, kind: str, file: UploadFile = File(...)):
    """上传「换成我上传的音乐」或「再加一段音效」用的音频（C4）。

    只影响后期混音，不进提示词、不占参考素材编号。
    门槛：必须是**纯音频**（带画面的 mp4 拒掉，那种应该走风格参考视频）、
    ≤20MB。时长不设限 —— BGM 会循环/裁到成片时长，音效按原样叠加。
    """
    if kind not in store.REF_AUDIO_KINDS:
        return fail(f"未知的音频类型：{kind}（只认 {'/'.join(store.REF_AUDIO_KINDS)}）",
                    biz_code=9)
    task = store.load(cid)
    if not task:
        return fail("任务不存在或已过期", biz_code=404)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _AUDIO_MEDIA:
        return fail(f"不支持的音频格式：{ext or '（没有扩展名）'}；"
                    "支持 mp3 / wav / m4a / aac / flac / ogg / opus", biz_code=9)

    dest = store.task_dir(cid) / f"ref_{kind}{ext}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    size = 0
    try:
        with part.open("wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > 20 * 1024 * 1024:
                    raise ValueError("音频超过 20MB")
                f.write(chunk)
        if size == 0:
            raise ValueError("文件是空的")
        part.replace(dest)
    except Exception as e:  # noqa: BLE001
        part.unlink(missing_ok=True)
        return fail(f"上传失败：{str(e)[:200]}", biz_code=9)

    try:
        info = scene.probe(dest)
        why = audio_only_problem(info)
        if why:
            raise ValueError(why)
        dur = float(info.get("duration") or 0)
    except Exception as e:  # noqa: BLE001
        dest.unlink(missing_ok=True)
        return fail(f"无法使用该音频：{str(e)[:160]}", biz_code=9)

    # 同一个 kind 换格式时，把旧格式的文件删掉（ref_bgm.mp3 → ref_bgm.wav）
    for other in store.task_dir(cid).glob(f"ref_{kind}.*"):
        if other != dest and other.suffix.lower() in _AUDIO_MEDIA:
            other.unlink(missing_ok=True)

    meta = task.setdefault("meta", {})
    meta["audio_refs"] = {k: store.ref_audio_path(cid, k).exists()
                          for k in store.REF_AUDIO_KINDS}
    store.save(task)
    return ok({"kind": kind, "duration": round(dur, 2), "bytes": size})


@router.delete("/clone/{cid}/audio/{kind}")
async def clone_audio_delete(cid: str, kind: str):
    if kind not in store.REF_AUDIO_KINDS:
        return fail(f"未知的音频类型：{kind}", biz_code=9)
    task = store.load(cid)
    if not task:
        return fail("任务不存在或已过期", biz_code=404)
    for p in store.task_dir(cid).glob(f"ref_{kind}.*"):
        if p.suffix.lower() in _AUDIO_MEDIA:
            p.unlink(missing_ok=True)
    meta = task.setdefault("meta", {})
    meta["audio_refs"] = {k: store.ref_audio_path(cid, k).exists()
                          for k in store.REF_AUDIO_KINDS}
    store.save(task)
    return ok({"kind": kind, "removed": True})


# ---------------------------------------------------------------------------
# 配音试听：音色 demo + 文案试听
#
# 为什么要试听：估算再准也只是估算，用户真正要判断的是"听起来对不对"。
# 两层，成本差一个量级：
#   · 音色 demo —— 固定演示句，**落盘到 data/voice_demo/ 全站共用**；
#     第一个人点过之后所有任务、所有用户都免费
#   · 文案试听 —— key = 文案 + 音色 + 语速，只改语速才重新合成
# 🩸 两者都真调 TTS、按字符计费，所以**必须先查缓存再合成**。

# 功能演示句（不是营销文案）：只说"这是这个音色的声音"，不承载任何卖点。
# 泰语避开 ค่ะ / ครับ —— 男女声用词不同，演示句要两种音色都能念。
_DEMO_TEXT = {
    "zh": "你好，这就是这个音色的声音。",
    "en": "Hi, this is how this voice sounds.",
    "ja": "こんにちは、この声のサンプルです。",
    "ko": "안녕하세요, 이 목소리의 샘플입니다.",
    "th": "สวัสดี นี่คือตัวอย่างเสียง",
    "vi": "Xin chào, đây là giọng đọc mẫu.",
    "id": "Halo, ini contoh suara untuk Anda.",
    "ms": "Halo, ini contoh suara untuk anda.",
    "tl": "Kumusta, ito ang sample ng boses na ito.",
    "es": "Hola, esta es una muestra de esta voz.",
    "mx": "Hola, esta es una muestra de esta voz.",
    "pt": "Olá, esta é uma amostra desta voz.",
    "ru": "Здравствуйте, это образец этого голоса.",
    "ar": "مرحباً، هذه عينة من هذا الصوت.",
    "de": "Hallo, das ist eine Hörprobe dieser Stimme.",
    "fr": "Bonjour, voici un aperçu de cette voix.",
    "it": "Ciao, questa è una prova di questa voce.",
}

_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.\-]{1,80}$")


def _voice_lang(voice: str) -> str:
    """音色 id 的语种前缀：en_female_dacey_uranus_bigtts → en。"""
    return (voice or "").split("_", 1)[0].lower()


def _audio_seconds(p: Path) -> float:
    try:
        return round(float(scene.probe(p).get("duration") or 0), 3)
    except Exception:  # noqa: BLE001
        return 0.0


def _demo_dir() -> Path:
    """音色 demo 是全站共享的，所以不放任务目录（任务 3 天就清理）。"""
    d = settings.clone_dir.parent / "voice_demo"
    d.mkdir(parents=True, exist_ok=True)
    return d


class VoiceDemoIn(BaseModel):
    voice: str = Field(..., description="音色 id（见 /clone/voices）")


@router.post("/clone/{cid}/voice-demo")
async def clone_voice_demo(cid: str, body: VoiceDemoIn):
    """音色试听：固定演示句合成一次后**全站缓存**。

    缓存键只有音色本身 —— 同一个音色在任何任务里听都是同一段，
    所以第一个人点过之后所有人都免费。
    """
    voice, _note = voice_catalog.resolve((body.voice or "").strip(),
                                         _voice_lang(body.voice) or "zh")
    # 收口后仍挡一次：音色 id 会进文件名，手填的 ID（S_ 复刻音色）放行但必须安全
    if not voice or not _SAFE_NAME.match(voice):
        return fail("音色 id 不合法", biz_code=6)
    from app.services.providers.tts import get_tts

    tts = get_tts()
    p = _demo_dir() / f"{voice}{getattr(tts, 'ext', '.wav')}"
    cached = p.exists() and p.stat().st_size > 0
    if not cached:
        text = _DEMO_TEXT.get(_voice_lang(voice)) or _DEMO_TEXT["en"]
        try:
            tts.synth(text, p, voice=voice, rate=0)
        except Exception as e:  # noqa: BLE001
            log.warning("音色 demo 合成失败 %s：%s", voice, e)
            p.unlink(missing_ok=True)
            return fail(f"合成失败：{e}", biz_code=8)
    return ok({"path": f"/api/clone/{cid}/file/voice-demo/{voice}{p.suffix}",
               "seconds": _audio_seconds(p), "cached": cached,
               "label": voice_catalog.label(voice)})


class VoicePreviewIn(BaseModel):
    text: str = Field(..., description="要试听的文案")
    voice: str = Field("", description="音色 id；空 = 该语种默认")
    rate: int = Field(0, description="语速 -30~30，正数=更快")
    lang: str = Field("", description="语种；空 = 从音色 id 前缀推")
    # 口音还原（火山 tone_fidelity）：只对复刻音色生效。
    # 试听必须能听到它 —— 否则用户开了开关，要等整条片出完才知道像不像。
    fidelity: bool = Field(False, description="还原原片口音/韵律（仅复刻音色）")


@router.post("/clone/{cid}/voice-preview")
async def clone_voice_preview(cid: str, body: VoicePreviewIn):
    """文案试听：**按 文案+音色+语速 缓存**，只改语速才重新合成。

    返回的 `seconds` 是**实测时长**，前端直接拿它跟原片比 —— 比估算靠谱。
    """
    task = store.load(cid)
    if not task:
        return fail("任务不存在或已过期", biz_code=404)
    text = (body.text or "").strip()
    if not text:
        return fail("没有要试听的文案", biz_code=6)
    if len(text) > 600:
        return fail("试听文案太长（上限 600 字），先试听其中一段", biz_code=6)
    from app.services.providers.tts import get_tts

    lang = (body.lang or "").strip().lower() or _voice_lang(body.voice)
    voice, _note = voice_catalog.resolve((body.voice or "").strip(), lang)
    rate = max(-speech_est.MAX_RATE, min(speech_est.MAX_RATE, int(body.rate or 0)))
    tts = get_tts()

    # 🩸 缓存键必须带还原开关：开了 fidelity 的声音和没开是两段不同的音频，
    # 共用键会让用户点开关后听到上一版的旧缓存，以为功能没生效。
    # 还原模式只对复刻音色生效，且官方不支持跨语种 —— 翻译过的台词不打开
    fid = (bool(body.fidelity) and voice.startswith("S_")
           and (not lang or lang.startswith("zh")))
    key = hashlib.sha1(
        f"{voice}|{rate}|{'f' if fid else ''}|{text}".encode("utf-8")).hexdigest()[:16]
    d = store.task_dir(cid) / "voice_preview"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{key}{getattr(tts, 'ext', '.wav')}"
    cached = p.exists() and p.stat().st_size > 0
    if not cached:
        try:
            tts.synth(text, p, voice=voice, rate=rate, fidelity=fid)
        except Exception as e:  # noqa: BLE001
            log.warning("文案试听合成失败 cid=%s：%s", cid, e)
            p.unlink(missing_ok=True)
            return fail(f"合成失败：{e}", biz_code=8)

    src_total = float((task.get("recipe") or {}).get("source", {}).get("duration")
                      or 0)
    sec = _audio_seconds(p)
    return ok({"path": f"/api/clone/{cid}/file/voice-preview/{key}{p.suffix}",
               "seconds": sec, "cached": cached,
               "voice": voice, "voice_label": voice_catalog.label(voice),
               "rate": rate,
               "source_seconds": round(src_total, 3),
               "diff_pct": (round((sec / src_total - 1) * 100, 1)
                            if src_total > 0 and sec > 0 else 0)})


@router.get("/clone/{cid}/file/voice-demo/{name}")
async def clone_voice_demo_file(cid: str, name: str):
    if not _SAFE_NAME.match(name):
        raise HTTPException(status_code=404, detail="文件名不合法")
    p = _demo_dir() / name
    if not p.exists():
        raise HTTPException(status_code=404, detail="还没生成过这段试听")
    return FileResponse(p, media_type=_AUDIO_MEDIA.get(p.suffix.lower(),
                                                       "audio/mpeg"))


@router.get("/clone/{cid}/file/voice-preview/{name}")
async def clone_voice_preview_file(cid: str, name: str):
    if not store.valid(cid) or not _SAFE_NAME.match(name):
        raise HTTPException(status_code=404, detail="文件不存在")
    p = store.task_dir(cid) / "voice_preview" / name
    if not p.exists():
        raise HTTPException(status_code=404, detail="还没生成过这段试听")
    return FileResponse(p, media_type=_AUDIO_MEDIA.get(p.suffix.lower(),
                                                       "audio/mpeg"))


@router.get("/clone/{cid}/file/audio/{kind}")
async def clone_audio_file(cid: str, kind: str):
    """BGM / 音效的试听。"""
    if kind not in store.REF_AUDIO_KINDS:
        raise HTTPException(status_code=404, detail="未知的音频类型")
    p = store.ref_audio_path(cid, kind)
    if not p.exists():
        raise HTTPException(status_code=404, detail="还没有上传这段音频")
    return FileResponse(p, media_type=_AUDIO_MEDIA.get(p.suffix.lower(),
                                                       "application/octet-stream"))


@router.get("/clone/{cid}/file/ref")
async def clone_ref_file(cid: str, exp: int = Query(0), sig: str = Query("")):
    """签名链接：给火山拉原片用（它只收公网 URL，不收 base64）。

    优先给截断后的版本 —— 分析用的是截断片，喂给模型的也应该是同一条。
    """
    if not signed_url.verify(cid, exp, sig):
        raise HTTPException(status_code=403, detail="链接无效或已过期")
    cut = store.task_dir(cid) / "source_cut.mp4"
    p = cut if cut.exists() else store.source_path(cid)
    if not p.exists():
        raise HTTPException(status_code=404, detail="参考片不存在")
    return FileResponse(p, media_type="video/mp4")


@router.get("/clone/{cid}/file/seg/{name}")
async def clone_seg_file(cid: str, name: str, exp: int = Query(0), sig: str = Query("")):
    """签名链接：按段给火山拉参考视频（超过单段上限时切出来的段）。"""
    if not (name.startswith("seg_") and name.endswith(".mp4")):
        raise HTTPException(status_code=400, detail="非法的段名")
    if not signed_url.verify(cid, exp, sig, seg=name):
        raise HTTPException(status_code=403, detail="链接无效或已过期")
    p = store.segment_dir(cid) / name
    if not p.exists():
        raise HTTPException(status_code=404, detail="片段不存在")
    return FileResponse(p, media_type="video/mp4")


@router.get("/clone/{cid}")
async def clone_detail(cid: str):
    task = store.load(cid)
    if not task:
        return fail("任务不存在或已过期", biz_code=404)
    data = store.public(task)
    return ok(data)


@router.get("/clone/{cid}/inventory")
def clone_inventory(cid: str,
                    refresh: bool = Query(False, description="强制重新识别（会再花一次钱）")):
    """视觉盘点：原片里有几个人、各在第几秒出现。

    结果按「原片哈希 + 帧率 + 型号」缓存在任务目录里，重复调用不再花钱。
    失败不报错、返回 ready=false —— 前端拿不到清单就当没有，出片照跑。
    """
    if not store.load(cid):
        return fail("任务不存在或已过期", biz_code=404)
    from app.services import vision_plan

    if not vision_plan.available():
        return ok({"ready": False, "reason": "视觉盘点未启用（未配置 VT_ARK_API_KEY）",
                   "people": [], "products": [], "scenes": []})
    try:
        inv = vision_plan.inventory(cid, refresh=refresh)
    except Exception as e:  # noqa: BLE001
        log.warning("视觉盘点失败：%s", e)
        return ok({"ready": False, "reason": str(e),
                   "people": [], "products": [], "scenes": []})
    return ok(vision_plan.summary(inv))


def _check_render_in(body: RenderIn) -> tuple[str, int]:
    """`/plan` 与 `/prompts` 共用的入参校验。返回 (错误文案, 业务码)，空串 = 通过。

    🩸 两条路必须同口径：`/prompts` 生成的提示词会**直接进出片**，
    它接受的参数比 `/plan` 宽，就等于留了一个绕开校验的口子。
    """
    regen_mode = (body.regen_mode or "auto").strip().lower()
    # 🩸 2026-11-02 静帧链路已删：老客户端的 "shots" 归一到 auto
    if regen_mode == "shots":
        regen_mode = "auto"
    if regen_mode not in ("auto", "whole"):
        return "未知的换画面模式", 8
    # 型号校验和出片接口同一条口径：填了就必须认得、且和通道同族
    _bad = regen_model_error((body.regen_model or "").strip(), body.regen_channel)
    if _bad:
        return _bad, 8
    spec = edit_spec.normalize(body.edit.model_dump()) if body.edit else None
    script = (body.script or "").strip()
    if not script and (spec or {}).get("audio", "tts") != "original":
        return "文案不能为空", 6
    if len(script) > 2000:
        return "文案太长（上限 2000 字）", 6
    return "", 0


def _preview_call(cid: str, task: dict, body: RenderIn, **extra) -> dict:
    """把 `RenderIn` 摊成 `preview_render` 的入参。两条接口共用这一处 ——
    段号、参考图编号、提示词必须出自同一条计算，不能各拼一套。"""
    subject = store.subject_path(cid)
    refs = {
        slot: store.ref_path(cid, slot)
        for slot in store.REF_SLOTS
        if store.ref_path(cid, slot).exists()
    }
    return clone_pipeline.preview_render(
        store.source_path(cid), task["recipe"],
        script=(body.script or "").strip() or None,
        script_lines=body.script_lines or None,
        regen_prompt=(body.regen_prompt or "").strip(),
        regen_shots=body.regen_shots or None,
        regen_mode=(body.regen_mode or "auto").strip().lower(),
        regen_channel=body.regen_channel,
        regen_model=(body.regen_model or "").strip(),
        subject_image=subject if subject.exists() else None,
        subject_asset=(body.subject_asset or "").strip(),
        edit_spec=edit_spec.normalize(body.edit.model_dump()) if body.edit else None,
        refs=refs,
        pronounce=pronounce_mod.clean(body.pronounce),
        tts_voice=(body.tts_voice or "").strip(),
        allow_stretch=bool(body.allow_stretch),
        lang=(body.lang or "").strip().lower(),
        speech_rate=body.speech_rate,
        cid=cid,
        **extra,
    )


@router.post("/clone/{cid}/plan")
async def clone_plan(cid: str, body: RenderIn):
    """出片前预览：**不调 TTS / 图 / 视频模型，不花钱**。

    返回这次会动几段、调几次模型、生成多少秒、成片合同（帧/采样），
    以及文案长度是否会被拦下。前端把这份数字放进"确认出片"弹窗，
    别让人点完才发现跑了一大片。
    """
    task = store.load(cid)
    if not task:
        return fail("任务不存在或已过期", biz_code=404)
    if not task.get("recipe"):
        return fail("原片还没分析完，请稍候", biz_code=5)
    _bad, _code = _check_render_in(body)
    if _bad:
        return fail(_bad, biz_code=_code)
    try:
        # 🩸 只出前 N 段时，预览必须按**前 N 段**报数（2026-11-01）：
        #   真跑那边 `render` 的 `max_segments` 分支只生成前 N 段、不拼接，
        #   预览不认这个参数就会出现"点了先出第 1 段，弹窗写 2 段 / 18.067 秒"。
        #   只在这一条路由上透传：`/prompts` 仍要写**全片**的逐段指令，
        #   否则只写 1 段、出全部时后面几段会回落成代码版。
        preview = _preview_call(cid, task, body,
                                max_segments=int(body.max_segments or 0))
    except Exception as e:  # noqa: BLE001
        log.warning("出片预览失败：%s", e)
        return fail(str(e), biz_code=8)
    return ok(preview)


@router.post("/clone/{cid}/prompts")
async def clone_prompts(cid: str, body: RenderIn, force: bool = False):
    """用官方 skill 现写这一单的**逐段编辑指令**，落盘，返回预览。

    🩸 这是**唯一会花钱的预览接口**（调用一次对话模型）。`/plan` 仍然零费用。
    写好后出片直接读落盘（`clone_agent.cached`），不会再花第二次；
    勾选 / 参考图 / 文案 / 型号任一变了，签名变，出片会自动回落到代码编译版 ——
    所以改完参数点一下这个接口，再出片。
    """
    task = store.load(cid)
    if not task:
        return fail("任务不存在或已过期", biz_code=404)
    if not task.get("recipe"):
        return fail("原片还没分析完，请稍候", biz_code=5)
    _bad, _code = _check_render_in(body)
    if _bad:
        return fail(_bad, biz_code=_code)
    try:
        preview = _preview_call(cid, task, body, with_agent=True, agent_force=force)
    except Exception as e:  # noqa: BLE001
        log.warning("逐段指令生成失败：%s", e)
        return fail(str(e), biz_code=8)
    # 明确失败就明确报错：用户点的是"用官方 skill 生成"，悄悄返回代码版 =
    # 让他以为看到的是官方版，然后拿去出片。
    if preview.get("agent_error"):
        return fail(str(preview["agent_error"]), biz_code=8)
    return ok(preview)


@router.get("/clone/{cid}/prompts")
async def clone_prompts_view(cid: str):
    """看这一单**当前落盘的**逐段指令（零费用，不调模型）。

    🩸 直接读文件，不问是哪一家写的：2.5 和 H3 写的是同一个 `prompts.json`，
    文件里自带 `agent` 标记和型号。界面要的是"现在盘上是什么"，不是"某一家的"。
    """
    data = None
    try:
        p = store.prompts_path(cid)
        if p.is_file():
            data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        log.warning("逐段指令读不出来：%s", e)
    if not isinstance(data, dict):
        return ok({"exists": False, "segments": [], "sig": ""})
    return ok({
        "exists": True,
        "sig": str(data.get("sig") or ""),
        "source": str(data.get("source") or ""),
        # 这份是谁按哪套模板写的（`sd25` 的五段式 / `h3` 的六段式）
        "agent": str(data.get("agent") or ""),
        "model": str(data.get("model") or ""),
        "created": int(data.get("created") or 0),
        "segments": data.get("segments") or [],
    })


@router.post("/clone/{cid}/reuse-plan")
async def clone_reuse_plan(cid: str, body: RenderIn):
    """这次出片**能复用几段、要重画几段、为什么** —— 零成本，不调任何模型。

    和 `/plan` 的分工：
      · `/plan` 回答"花多少钱、动多少秒"（报价）；
      · 这里回答"哪些不用再花钱"（复用清单）。
    两条走的是同一套决策还是不同函数，所以两边的段数必须对得上 —— 见
    `scripts/work_p0_check.py` 里"段数与出片预览一致"那条。
    """
    task = store.load(cid)
    if not task:
        return fail("任务不存在或已过期", biz_code=404)
    if not task.get("recipe"):
        return fail("原片还没分析完，请稍候", biz_code=5)
    # 冻结点也要在这条路上拦：`/plan` 和 `/render` 各有一道，这里不拦的话
    # 复用清单会照 minimax 算一遍，用户看到"能复用 0 段"才发现选不了。
    _bad = regen_model_error((body.regen_model or "").strip(), body.regen_channel)
    if _bad:
        return fail(_bad, biz_code=8)

    spec = edit_spec.normalize(body.edit.model_dump()) if body.edit else None
    intent = {
        "mode": (body.regen_mode or "auto").strip().lower(),
        "channel": (body.regen_channel or "auto").strip().lower(),
        "model": (body.regen_model or "").strip(),
        "edit": spec or {},
        "script": (body.script or "").strip(),
        # 音色也算输入：换了音色，配音就变了，口型段跟着要重做
        "voice": (body.tts_voice or "").strip(),
    }
    try:
        w = work_mod.build(cid)
        plan = work_mod.plan(cid, w, intent)
    except Exception as e:  # noqa: BLE001
        log.warning("复用计划算不出来：%s", e)
        return fail(str(e), biz_code=8)
    return ok(plan)


class TranslateIn(BaseModel):
    text: str = Field(..., description="中文文案（整段）")
    lang: str = Field(..., description="目标语种：en / th / vi / id / ms / tl …")


@router.post("/clone/{cid}/translate")
async def clone_translate(cid: str, body: TranslateIn):
    """把中文文案逐句翻成目标语种（C6 多语种配音）。

    **翻译是独立一步**：先出译文给用户看/改，再拿译文去出片 —— 不塞在出片里，
    否则每次改一个字都要重翻一遍，而且用户看不到译文写了什么。
    返回的 `lines` 可以直接作为 `script_lines` 传给出片/预览。
    """
    task = store.load(cid)
    if not task:
        return fail("任务不存在或已过期", biz_code=404)
    text = (body.text or "").strip()
    if not text:
        return fail("文案不能为空", biz_code=6)
    if len(text) > 2000:
        return fail("文案太长（上限 2000 字）", biz_code=6)
    lang = (body.lang or "").strip().lower()
    if lang not in translate_mod.LANG_NAME:
        return fail(f"不支持的语种：{lang or '（空）'}", biz_code=8)
    if lang == "zh":
        return fail("目标是中文，不用翻译", biz_code=8)

    # 只按句末标点断句，**不合并短句** —— 合并会把外语切成碎片，
    # 每片都带 TTS 头尾静音，实测总时长能涨到 1.68 倍（见 translate.py 注释）
    lines = translate_mod.split_sentences(text)
    if not lines:
        return fail("没断出句子", biz_code=6)
    rec = task.get("recipe") or {}
    src_total = float((rec.get("source") or {}).get("duration") or 0)
    try:
        res = translate_mod.translate_lines(lines, lang, src_total=src_total)
    except translate_mod.TranslateError as e:
        return fail(str(e), biz_code=8)
    except Exception as e:  # noqa: BLE001
        log.warning("翻译失败：%s", e)
        return fail(f"翻译失败：{e}", biz_code=8)
    res["source_total"] = round(src_total, 2)
    return ok(res)


@router.post("/clone/{cid}/render")
async def clone_render(cid: str, body: RenderIn):
    task = store.load(cid)
    if not task:
        return fail("任务不存在或已过期", biz_code=404)
    if not task.get("recipe"):
        return fail("原片还没分析完，请稍候", biz_code=5)
    script = (body.script or "").strip()
    if len(script) > 2000:
        return fail("文案太长（上限 2000 字）", biz_code=6)
    # 读音校正：只认"显示词 → 念法"的字符串对，脏条目直接丢掉；
    # 传了但一条有效的都没有 = 用户以为自己配了，其实没配，得当场说清楚
    # 空的右值 = 用户清空了某个词，属于正常操作；只有"填了内容却一条都不认"
    # 才是真错（比如传了超长或非字符串）
    pron = pronounce_mod.clean(body.pronounce)
    typed = any(isinstance(v, str) and v.strip()
                for v in (body.pronounce or {}).values())
    if typed and not pron:
        return fail("读音校正没有有效条目：左边填文案里原样的词，右边填它该怎么念", biz_code=8)
    if clone_jobs.is_busy(cid):
        return fail("该任务正在处理中，请稍候", biz_code=7)

    regen_prompt = (body.regen_prompt or "").strip()
    regen_shots = body.regen_shots or None
    regen_mode = (body.regen_mode or "auto").strip().lower()
    # 🩸 2026-11-02 静帧链路已删：老客户端的 "shots" 归一到 auto
    if regen_mode == "shots":
        regen_mode = "auto"
    if regen_mode not in ("auto", "whole"):
        return fail("未知的换画面模式", biz_code=8)

    asset = (body.subject_asset or "").strip()

    # 型号：留空 = 用该通道的默认型号（老前端不受影响）。
    # 填了就必须是本系统认得的，而且得和显式指定的通道同族 ——
    # 把 MiniMax 的型号发给火山，接口直接 400，报错还看不懂。
    regen_model = (body.regen_model or "").strip()
    _bad = regen_model_error(regen_model, body.regen_channel)
    if _bad:
        return fail(_bad, biz_code=8)

    spec = edit_spec.normalize(body.edit.model_dump()) if body.edit else None
    if spec is not None:
        # 🩸 换人物**只认素材**：本地照片或 asset://。以前允许用 person_desc
        # 顶，但前端填进 person_desc 的偏偏是**原片那个人**的描述（诊断页选人时
        # 自动带过来的），编译出来就是「把老爷爷替换为老爷爷」—— 2026-10-21
        # 那条 12s 火山片连人都没换，就是这么来的。
        c = spec["change"]
        if c.get("person") and not asset and not store.ref_path(cid, "person").exists():
            return fail("换了人物就得给素材：传一张人物照片，或者填火山资产 ID", biz_code=8)
        for slot, label in (("product", "产品"), ("scene", "场景"), ("wardrobe", "服装")):
            if c.get(slot) and not store.ref_path(cid, slot).exists() \
                    and not c.get(f"{slot}_desc"):
                return fail(f"换了{label}就得给素材：传一张{label}图，或者写一句描述", biz_code=8)

    has_change = bool(spec and (edit_spec.has_change(spec) or spec.get("extra")))
    wants_regen = bool(regen_prompt) or bool(regen_shots) or has_change
    if wants_regen:
        if not regen_prompt and not has_change:
            return fail("换画面要说明想换成什么", biz_code=8)
        if regen_mode in ("auto", "whole"):
            # 自动分诊和整片重制都可能用到视频模型，先把通道可用性挡在前面。
            # 首选谁取决于"人物素材从哪来"：asset:// 是火山认可的肖像来源，
            # 优先火山；本地上传的图多半是真人照，优先 MiniMax
            kind = (edit_spec.subject_kind(spec, person_asset=asset) if spec
                    else ("asset" if asset
                          else ("file" if store.subject_path(cid).exists() else "none")))
            try:
                video_edit.pick_channel(body.regen_channel, subject_kind=kind)
            except video_edit.EditError as e:
                return fail(str(e), biz_code=8)

    # 声音模式独立于换画面：只换文案也可以叠加原片 BGM
    audio_mode = (spec or {}).get("audio", "tts")
    if audio_mode == "original":
        # 唱歌 / 跳舞 / 原口播：声音就是内容，不重新配音。
        # 这时**不需要文案** —— 卡的是原片有没有音轨，而不是有没有识别出语音。
        if not (task.get("recipe") or {}).get("source", {}).get("has_audio"):
            return fail("原片没有音轨，保留原声没有意义", biz_code=8)
    elif not script:
        return fail("文案不能为空", biz_code=6)

    rid = store.new_id()
    import time as _t

    item = {
        "id": rid,
        "created_at": _t.time(),
        "state": "queued",
        "stage": "",
        "pct": 0,
        "script": script,
        # 逐行文案（翻译结果）：出片时原样用，不再自动切句
        "script_lines": [str(t or "").strip() for t in (body.script_lines or [])
                         if str(t or "").strip()],
        # 只重配这几行（下标基于上面的 `script_lines`）；None / 空 = 全部重配
        "dub_lines": (sorted({int(i) for i in body.dub_lines if int(i) >= 0})
                      if body.dub_lines else None),
        # 每行用哪个音色（键是字符串行号）；空 = 全部用整片那个音色
        "dub_voices": ({str(k): str(v).strip() for k, v in body.dub_voices.items()
                        if str(v).strip()} if body.dub_voices else {}),
        # 方言代码（火山 explicit_dialect）；空 = 标准普通话
        "tts_dialect": (body.tts_dialect or "").strip().lower(),
        # 口音还原（火山 tone_fidelity）；只对复刻音色生效
        "tts_fidelity": bool(body.tts_fidelity),
        "error": "",
        "duration": None,
        "regen_prompt": regen_prompt,
        "regen_shots": regen_shots or [],
        "regen_mode": regen_mode,
        "regen_channel": body.regen_channel,
        "regen_model": regen_model,
        "subject_asset": asset,
        "edit": spec,
        "pronounce": pron,
        "tts_voice": (body.tts_voice or "").strip(),
        "lang": (body.lang or "").strip().lower(),
        # 试听里手动调好的语速，出片必须沿用它 —— 否则前台调了半天，出片又变回自动值
        "speech_rate": body.speech_rate,
        "allow_stretch": bool(body.allow_stretch),
        # 只出前 N 段（预览）；0 = 全部。落进任务记录便于对账"这次是不是预览"
        "max_segments": int(body.max_segments or 0),
        # 这一次有没有跳过缓存强制重跑（对账用：「钱花在哪一次」）
        "force": bool(body.force),
        # 续出全部（`/continue`）要用同一套参数重建请求，遮罩开关也得留着
        "mask_bottom": bool(body.mask_bottom),
    }
    task.setdefault("renders", []).append(item)
    store.save(task)
    clone_jobs.submit_render(
        cid, rid, script=script, mask_bottom=body.mask_bottom,
        regen_prompt=regen_prompt if wants_regen else "",
        regen_shots=regen_shots,
        regen_mode=regen_mode,
        regen_channel=body.regen_channel,
        edit_spec=spec,
        max_segments=int(body.max_segments or 0),
        force=bool(body.force),
    )
    return ok({"id": cid, "render_id": rid})


@router.post("/clone/{cid}/render/{rid}/continue")
async def clone_render_continue(cid: str, rid: str):
    """把「只出前 N 段」的预览继续出完。

    🩸 同参数重跑全片：已经生成过的段命中缓存（键含这一段最终发出去的提示词），
    **不重复扣费**；只有没生成过的段真花钱。参数全部取自这一版任务记录 ——
    前端不用重新填，也不会因为表单状态丢了而出成另一个东西。
    """
    task = store.load(cid)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    src = next((x for x in (task.get("renders") or [])
                if x.get("id") == rid), None)
    if src is None:
        raise HTTPException(status_code=404, detail="这一版不存在")
    if not src.get("partial"):
        return fail("这一版本来就是完整成片，不用继续出", biz_code=8)

    # 只剔除**上一次的结果字段**，输入字段（型号、通道、规格、文案）原样带走
    _OUTPUT_ONLY = {"id", "created_at", "state", "stage", "pct", "error",
                    "error_file", "duration", "regen_meta", "qc", "identity",
                    "partial", "replaced_shots", "voice_meta", "segments"}
    import time as _t

    new_rid = store.new_id()
    item = {k: v for k, v in src.items() if k not in _OUTPUT_ONLY}
    item.update({"id": new_rid, "created_at": _t.time(), "state": "queued",
                 "stage": "", "pct": 0, "error": "", "duration": None,
                 "max_segments": 0, "partial": False})
    task.setdefault("renders", []).append(item)
    store.save(task)
    clone_jobs.submit_render(
        cid, new_rid, script=item.get("script"),
        mask_bottom=bool(item.get("mask_bottom")),
        regen_prompt=item.get("regen_prompt") or "",
        regen_shots=item.get("regen_shots") or None,
        regen_mode=item.get("regen_mode") or "auto",
        regen_channel=item.get("regen_channel") or "auto",
        edit_spec=item.get("edit"),
        max_segments=0,
    )
    return ok({"id": cid, "render_id": new_rid})


@router.post("/clone/{cid}/extend")
async def clone_extend(cid: str, body: ExtendIn):
    """视频延长：拿原片或某一版成片，向前/向后接一段，再拼成一条新的。

    不另开任务：产物就是这一单下的新版本（`renders[]` 里多一条），
    结果页的版本切换、下载、联系表全都照旧能用。
    """
    task = store.load(cid)
    if not task:
        return fail("任务不存在或已过期", biz_code=404)
    if not store.source_path(cid).exists():
        return fail("原片已不在，无法延长", biz_code=404)

    direction = (body.direction or "back").strip().lower()
    if direction not in ("front", "back"):
        return fail("未知的延长方向", biz_code=8)
    content = (body.content or "").strip()
    if not content:
        return fail("请说明延出来的这段里发生什么", biz_code=8)
    if len(content) > 500:
        return fail("延长描述太长（上限 500 字）", biz_code=8)

    base_render_id = (body.base_render_id or "").strip()
    if base_render_id:
        base_item = next((r for r in task.get("renders") or []
                          if r.get("id") == base_render_id), None)
        if base_item is None:
            return fail("要延长的这一版不存在", biz_code=404)
        if base_item.get("state") != "done":
            return fail("这一版还没出完，等它出完再延", biz_code=8)

    model_id = (body.model or "").strip()
    if model_id:
        _bad = regen_model_error(model_id)
        if _bad:
            return fail(_bad, biz_code=8)
        # 注册表里登记过的型号都能延长，只是口径各不相同（各在各家适配器里）：
        #   火山 = 显式延长任务（ratio=adaptive + 提示词「向后延长…」触发）
        #   H3   = 没有独立接口，靠提示词声明 [video continuation]
        # 没有 `extend_prompt` / `extend_submit` 的型号会在 `extend.run` 里当场报清楚。

    if clone_jobs.is_busy(cid):
        return fail("该任务正在处理中，请稍候", biz_code=7)

    rid = store.new_id()
    item = {
        "id": rid,
        "created_at": time.time(),
        "kind": "extend",
        "state": "queued",
        "stage": "",
        "pct": 0,
        # 版本列表里显示的是"这次做了什么"，不是原片文案
        "script": f"{'向前' if direction == 'front' else '向后'}延长 {body.seconds}s：{content}",
        "error": "",
        "duration": None,
        "extend": {
            "direction": direction,
            "seconds": int(body.seconds),
            "content": content,
            "base_render_id": base_render_id,
            # 带了哪几张图（顺序 = 提示词图号），结果页和排查都要看得到
            "ref_images": [str(x) for x in (body.ref_images or [])],
            "content_mode": (body.content_mode or "").strip(),
        },
    }
    task.setdefault("renders", []).append(item)
    store.save(task)
    started = clone_jobs.submit_extend(
        cid, rid, base_render_id=base_render_id, direction=direction,
        seconds=int(body.seconds), content=content, model=model_id,
        resolution=(body.resolution or "").strip(), with_audio=body.with_audio,
        with_transition=bool(body.transition),
        transition_desc=(body.transition_desc or "").strip(),
        ref_images=[str(x) for x in (body.ref_images or [])],
        content_mode=(body.content_mode or "").strip(),
    )
    if not started:
        task["renders"] = [r for r in task["renders"] if r.get("id") != rid]
        store.save(task)
        return fail("该任务正在处理中，请稍候", biz_code=7)
    return ok({"id": cid, "render_id": rid})


@router.get("/clone/{cid}/render/{rid}")
async def clone_render_detail(cid: str, rid: str):
    task = store.load(cid)
    if not task:
        return fail("任务不存在或已过期", biz_code=404)
    for r in task.get("renders") or []:
        if r.get("id") == rid:
            return ok({
                "id": r["id"], "state": r.get("state"), "stage": r.get("stage", ""),
                "pct": r.get("pct", 0), "script": r.get("script", ""),
                "error": r.get("error", ""), "duration": r.get("duration"),
                "segments": r.get("segments") or [],
                "replaced_shots": r.get("replaced_shots", 0),
                "regen_prompt": r.get("regen_prompt", ""),
                "regen_mode": r.get("regen_mode", "shots"),
                "regen_channel": r.get("regen_channel", ""),
                "regen_model": r.get("regen_model", ""),
                "edit": r.get("edit") or None,
                "audio": (r.get("edit") or {}).get("audio", "tts"),
                # 配音侧实测：语速加减了多少、估算/实际多少秒、atempo 用了多少。
                # 用户看到"配音被拉过"时，至少知道是哪一步造成的。
                "voice_meta": r.get("voice_meta") or {},
                # 换画面怎么拆的请求：多少段、切点有没有挪到画面最静处、
                # 段间有没有用上一段的尾帧衔接（"30 秒的片子能不能出"就看这里）
                "regen_meta": r.get("regen_meta") or {},
                # 成片质量门结果：ok / issues / warnings / stats
                "qc": r.get("qc") or {},
                # 身份核对：只报数（share / p90 / best_sim + note），不下结论
                "identity": r.get("identity") or {},
                # 成品契约：口型滞后 / 段间身份 / 背景保住（量产品，不量代码）
                "contract": r.get("contract") or {},
                # 延长出来的版本：方向、秒数、接缝处理了没有、基于哪一版
                "kind": r.get("kind") or "render",
                "extend": r.get("extend") or None,
            })
    return fail("出片记录不存在", biz_code=404)


# ---------------------------------------------------------------------------
# 文件


@router.get("/clone/{cid}/file/source")
async def clone_source_file(cid: str):
    p = store.source_path(cid)
    if not p.exists():
        cut = store.task_dir(cid) / "source_cut.mp4"
        p = cut if cut.exists() else p
    if not p.exists():
        raise HTTPException(status_code=404, detail="参考片不存在")
    return FileResponse(p, media_type="video/mp4")


@router.get("/clone/{cid}/kf/{name}")
async def clone_keyframe(cid: str, name: str):
    if not name.startswith("kf_") or not name.endswith(".jpg"):
        raise HTTPException(status_code=400, detail="非法的关键帧名")
    p = store.keyframe_dir(cid) / name
    if not p.exists():
        raise HTTPException(status_code=404, detail="关键帧不存在")
    return FileResponse(p, media_type="image/jpeg")


@router.get("/clone/{cid}/render/{rid}/file/{name}")
async def clone_render_file(cid: str, rid: str, name: str):
    d = store.render_dir(cid, rid)
    if name == "out":
        p, mime = d / "out.mp4", "video/mp4"
    elif name == "cover":
        p, mime = d / "cover.jpg", "image/jpeg"
    else:
        raise HTTPException(status_code=400, detail="未知文件")
    if not p.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(p, media_type=mime)


@router.get("/clone/{cid}/cover")
async def clone_source_cover(cid: str):
    """原片封面走本机代理：平台 CDN 有防盗链，小程序也不允许外链。"""
    task = store.load(cid)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    url = (task.get("meta") or {}).get("cover") or ""
    if not url:
        raise HTTPException(status_code=404, detail="该作品没有封面")
    d = store.task_dir(cid)
    p = d / "cover.img"
    if not p.exists():
        part = d / "cover.part"
        try:
            await media.download(url, part, max_bytes=20 * 1024 * 1024)
            part.replace(p)
        except Exception as e:  # noqa: BLE001
            log.warning("封面下载失败 %s: %s", cid, e)
            raise HTTPException(status_code=502, detail="封面下载失败") from e
        finally:
            part.unlink(missing_ok=True)
    return FileResponse(p, media_type="image/jpeg")


@router.get("/clone/{cid}/sheet")
async def clone_contact_sheet(cid: str, cols: int = Query(5, ge=2, le=10),
                              rows: int = Query(6, ge=2, le=10),
                              width: int = Query(240, ge=120, le=480),
                              refresh: bool = Query(False)):
    """整片联系表：带时间戳的网格图。

    本地 ffmpeg 算，不发任何外部请求。同一组参数缓存一张，refresh=1 才重算。
    """
    task = store.load(cid)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    src = store.source_path(cid)
    if not src.exists():
        raise HTTPException(status_code=404, detail="原片不存在")
    out = store.task_dir(cid) / f"sheet_{cols}x{rows}_{width}.jpg"
    if refresh or not out.exists():
        dur = float(((task.get("recipe") or {}).get("source") or {}).get("duration") or 0)
        try:
            await asyncio.to_thread(media.contact_sheet, src, out,
                                    cols=cols, rows=rows, width=width,
                                    duration=dur or None)
        except Exception as e:  # noqa: BLE001
            log.warning("联系表生成失败 %s: %s", cid, e)
            raise HTTPException(status_code=500,
                                detail=f"联系表生成失败：{str(e)[:120]}") from e
    return FileResponse(out, media_type="image/jpeg",
                        headers={"Cache-Control": "no-cache"})
