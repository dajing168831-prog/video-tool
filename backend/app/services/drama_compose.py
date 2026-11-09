"""商品短剧 · 成片合成（D 批）—— 本地 ffmpeg，**零生成费**。

这一层管的是「各段都出好了之后，怎么把它们做成一条能发的片」：
转场 / 渲染三档 / 字幕烧录 / BGM 混音 / 片尾 CTA / 成片速览 / 预览 GIF。
**不调任何生成模型、不花钱**；每一处参数都标明抄自竞品哪一行。

出处对照：
  · 合成主图：clipforge `src/app/api/project/[id]/compose/route.ts:1-613`
  · 滤镜实现：`src/lib/video-composer/composer.ts:456-704`（拼接 / 转场 / 混音 / 字幕）
  · 时间轴：  `src/lib/video-composer/timeline.ts:1-184`（淡入淡出会让后续整体前移，字幕要跟着夹）
  · 转场策略：`src/lib/video-composer/transitions.ts:1-127`
  · 渲染三档：`src/lib/compose-presets.ts:1-78`
  · BGM 策略：`src/lib/audio-mix.ts:1-18`
  · 尾卡：    `src/lib/video-composer/end-card.ts:1-121`（QR/商品图 + CTA，压最后 N 秒）
  · 速览 / GIF：`video-composer/contact-sheet.ts` / `gif-preview.ts`

🩸 只做「各段已经出好」之后的加工。出片（花钱）仍然由主人在 `film/render` 点。
🩸 我们没有 TTS 词边界（D1 未接），所以字幕时间轴 = **分镜计划时长 × 该段实际时长比例**，
   与成片是「比例对齐」而不是「帧级对轴」。这一点必须让使用者看见（plan.warnings）。
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from app.services import (drama_audio, drama_captions, drama_cover, drama_film,
                          drama_motion, drama_tts, drama_voice)
from app.services.media import ffmpeg_path, ffprobe_path

#: 淡入淡出时长 —— 视频 xfade / 音频 acrossfade / 字幕时间轴必须共用同一个数
#: （竞品 `composer.ts:409-410`；三处不一致就会声画飘）
FADE_DURATION = 0.5

#: 素材片段「变速压槽」区间（竞品 `composer.ts:413/418` 逐字）：
#: 源片略长/略短于镜头槽位时用 setpts 拉伸，保住首尾两端、消灭冻帧尾巴；
#: 超出这个区间再变速观感就变成糖浆慢放/快进，退回 tpad 冻帧补齐。
SPEEDFIT_MAX_RATIO = 1.35
SPEEDFIT_MIN_RATIO = 0.7

#: 成片目标尺寸。9:16 两档照竞品 `composer.ts:398-402` 逐值搬；
#: 16:9 / 1:1 是同两档分辨率下的等比尺寸（短边对齐：720 / 1080），
#: 由出片页的「画面比例」选，`doc.film.ratio` 决定走哪一行。
#: 1:1 的 720p 取 960×960：与 720×1280 面积相同（921,600），码率口径一致。
RESOLUTIONS = {
    "9:16": {"720p": (720, 1280), "1080p": (1080, 1920)},
    "16:9": {"720p": (1280, 720), "1080p": (1920, 1080)},
    "1:1": {"720p": (960, 960), "1080p": (1080, 1080)},
}

#: 界面给的画面比例（照竞品 `project/[id]/video/page.tsx` 的三档）
RATIOS = ("9:16", "16:9", "1:1")

#: 每段统一规格（竞品 `composer.ts:407`）。不统一会在 xfade 报
#: "Error reinitializing filters"。
SEGMENT_NORM = "format=yuv420p,setsar=1,fps=30,settb=AVTB"

#: 渲染三档（竞品 `compose-presets.ts:16-26`，**逐值照抄**）
RENDER_PRESETS = {
    "fast": {"id": "fast", "label": "快速", "resolution": "720p",
             "video_preset": "veryfast", "crf": 26,
             "note": "最快、文件最小，适合先看效果"},
    "standard": {"id": "standard", "label": "标准", "resolution": "1080p",
                 "video_preset": "medium", "crf": 20,
                 "note": "日常发布推荐"},
    "hd": {"id": "hd", "label": "高清", "resolution": "1080p",
           "video_preset": "slow", "crf": 17,
           "note": "画质最好、最慢"},
}
DEFAULT_RENDER_PRESET = "standard"

#: x264 preset 白名单（竞品 `compose-presets.ts:30-32`）：用户传的值不许直接进命令
VALID_X264_PRESETS = {
    "ultrafast", "superfast", "veryfast", "faster", "fast", "medium",
    "slow", "slower", "veryslow",
}

#: 转场四档（竞品 `transitions.ts:22-100`）
TRANSITIONS = {
    "ai_start_end": {
        "id": "ai_start_end", "label": "AI 智能过渡",
        "desc": "取前段末帧 + 后段首帧，用 AI 生成转场镜头",
        "local": False,
        "note": "要按接缝顺序重出片段（花钱），本地合成只能按硬切输出",
    },
    "ai_reference": {
        "id": "ai_reference", "label": "AI 参考过渡",
        "desc": "生成下一段时把前段末帧当参考图，自动衔接",
        "local": False,
        "note": "同上：属于生成阶段，已出好的片段本地接不了",
    },
    "direct_concat": {
        "id": "direct_concat", "label": "直接拼接",
        "desc": "硬切，无转场效果",
        "local": True, "note": "",
    },
    "ffmpeg_fade": {
        "id": "ffmpeg_fade", "label": "淡入淡出",
        "desc": f"ffmpeg 交叉淡化 {FADE_DURATION:g}s（保底方案）",
        "local": True, "note": "",
    },
}
DEFAULT_TRANSITION = "direct_concat"


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------


def render_profile(preset: str | None) -> dict:
    """按 id 取渲染档；非法值回落默认档（竞品 `compose-presets.ts:41-43`）。

    白名单在出口再卡一次（`safe_encode`）—— 外部传进来的字符串永远不进命令。
    """
    return dict(RENDER_PRESETS.get(str(preset or ""), RENDER_PRESETS[DEFAULT_RENDER_PRESET]))


def safe_encode(profile: dict) -> tuple[str, int]:
    """x264 preset / crf 的最后一道夹取（竞品 `compose-presets.ts:74-78`）。"""
    preset = str(profile.get("video_preset") or "medium")
    if preset not in VALID_X264_PRESETS:
        preset = "medium"
    try:
        crf = int(profile.get("crf", 20))
    except (TypeError, ValueError):
        crf = 18
    return preset, min(51, max(0, crf))


def transition_info(mode: str | None) -> dict:
    return dict(TRANSITIONS.get(str(mode or ""), TRANSITIONS[DEFAULT_TRANSITION]))


def transitions_public() -> list[dict]:
    return [{k: v for k, v in t.items() if k != "id"} | {"id": t["id"]}
            for t in TRANSITIONS.values()]


def normalize_config(raw: dict | None) -> dict:
    """把界面/请求里的设置夹成一份能直接执行的配置。

    非法值一律**回落默认**而不是报错（界面可能拿着旧版本值）；
    真正会改变成片外观的非法项（比如不存在的字幕预设）在 plan 里单独 warn。
    """
    raw = raw or {}
    mode = str(raw.get("transition") or DEFAULT_TRANSITION)
    if mode not in TRANSITIONS:
        mode = DEFAULT_TRANSITION

    cap = raw.get("caption_preset")
    cap = str(cap) if cap else ""
    if cap and not drama_captions.valid(cap):
        cap = ""
    if not cap:
        cap = drama_captions.DEFAULT_ID

    end = raw.get("end_card") or {}
    try:
        seconds = float(end.get("seconds") or 3)
    except (TypeError, ValueError):
        seconds = 3.0
    try:
        qr_ratio = float(end.get("qr_ratio") or 0.34)
    except (TypeError, ValueError):
        qr_ratio = 0.34
    try:
        fade_out = float(raw.get("bgm_fade_out") if raw.get("bgm_fade_out") is not None
                         else drama_audio.DEFAULT_FADE_OUT)
    except (TypeError, ValueError):
        fade_out = drama_audio.DEFAULT_FADE_OUT
    try:
        intro_skip = float(raw.get("bgm_intro_skip") or 0)
    except (TypeError, ValueError):
        intro_skip = 0.0

    return {
        "transition": mode,
        "render_preset": render_profile(raw.get("render_preset"))["id"],
        "captions": raw.get("captions") is not False,
        "caption_preset": cap,
        # D3 人声落地：默认开（竞品 `composer.ts:526-531`「quality features default into
        # every chain」），显式关掉才回到「干声」老形状
        "voice_ground": raw.get("voice_ground") is not False,
        "bgm": {
            # 音量在这里先夹一次；真正的 has_voice 要到 probe 后才知道，
            # duck 的最终值在 plan 里按实际对白轨再算（`drama_audio.resolve_mix`）
            "volume": drama_audio.normalize_volume(raw.get("bgm_volume")),
            "duck": raw.get("bgm_duck") is not False,
            "fade_out": min(10.0, max(0.0, fade_out)),
            "intro_skip": max(0.0, intro_skip),
        },
        "end_card": {
            "enabled": end.get("enabled") is True,
            "text": str(end.get("text") or "").strip()[:80],
            "seconds": min(10.0, max(1.0, seconds)),
            "image": str(end.get("image") or "").strip(),
            "qr_ratio": min(0.6, max(0.15, qr_ratio)),
        },
    }


# ---------------------------------------------------------------------------
# 探测
# ---------------------------------------------------------------------------


def probe(path: Path) -> dict:
    """ffprobe：时长 / 有没有音轨 / 画面尺寸。失败返回 0 值，不抛。"""
    fp = ffprobe_path()
    if not fp:
        return {"duration": 0.0, "has_audio": False, "width": 0, "height": 0}
    try:
        p = subprocess.run(
            [fp, "-v", "error",
             "-show_entries", "format=duration",
             "-show_entries", "stream=codec_type,width,height",
             "-of", "json", str(path)],
            capture_output=True, text=True, errors="ignore", timeout=60,
        )
        info = json.loads(p.stdout or "{}")
        streams = info.get("streams") or []
        video = next((s for s in streams if s.get("codec_type") == "video"), {})
        try:
            duration = float((info.get("format") or {}).get("duration") or 0)
        except (TypeError, ValueError):
            duration = 0.0
        return {
            "duration": max(0.0, duration),
            "has_audio": any(s.get("codec_type") == "audio" for s in streams),
            "width": int(video.get("width") or 0),
            "height": int(video.get("height") or 0),
        }
    except Exception:  # noqa: BLE001
        return {"duration": 0.0, "has_audio": False, "width": 0, "height": 0}


# ---------------------------------------------------------------------------
# 计划（纯计算 + 只读探测）
# ---------------------------------------------------------------------------


def _shots(doc: dict) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for i, s in enumerate(((doc.get("storyboard_json") or {}).get("shots") or []), 1):
        if not isinstance(s, dict):
            continue
        try:
            sid = int(s.get("id") or i)
        except (TypeError, ValueError):
            sid = i
        out[sid] = {**s, "id": sid}
    return out


def _freecut_timeline(doc: dict, data_root: Path, pid: str,
                      warnings: list[str], errors: list[str]) -> list[dict]:
    """免费快剪的时间线：**每镜一张画面，不需要出片计划**。

    出处：竞品 `api/project/[id]/compose/route.ts:340-406`
    （`assetByShot.get(shotId) ?? productImages[0]` → 视频原样用 / 静图配运镜）。
    优先级从高到低：
      1. 这一镜绑了素材视频（`shot_clips`）→ 当视频段，原声保留；
      2. 这一镜绑了参考图（`shot_materials`）→ 当静图段；
      3. 商品实拍图（`product.images`）→ 兜底，**所有没有画面的镜共用第一张**；
      4. 都没有 → 报错，不硬编造画面。
    """
    shots = _shots(doc)
    clips = drama_film.shot_clips(doc)
    mats = drama_film.shot_materials(doc)
    prod = [Path(str(x)).name for x in drama_film.product_pics(doc) if str(x).strip()]
    mat_dir = data_root / "materials" / pid
    img_dir = data_root / "images" / pid
    # 商品图兜底只挑**盘上真有**的第一张
    fallback = next((p for p in prod if (img_dir / p).exists()), "")
    rows: list[dict] = []
    used_fallback = 0
    for sid in sorted(shots):
        shot = shots[sid]
        try:
            seconds = float(shot.get("duration") or 0)
        except (TypeError, ValueError):
            seconds = 0.0
        if seconds <= 0:
            errors.append(f"镜头 {sid} 没写时长，快剪排不了")
            continue
        motion = drama_motion.motion_for_shot(shot)

        name = clips.get(sid) or ""
        if name and (mat_dir / name).exists():
            rows.append({"kind": "clip", "shot_id": sid, "material": name,
                         "seconds": seconds})
            continue
        # 🩸 有台词的镜头是**人物戏**（谁在对谁说话）—— 免费素材库配不到这种画面，
        # 实测「两人小饭馆喝酒」按 `plastic stool` 绑到的是一排空红塑料凳。
        # 有商品图时这类镜头直接用商品图，比一张毫不相干的空镜强。
        if fallback and str(shot.get("dialogue") or "").strip():
            rows.append({"kind": "image", "shot_id": sid, "material": fallback,
                         "source": "images", "seconds": seconds, "motion": motion})
            used_fallback += 1
            continue
        name = mats.get(sid) or ""
        if name and (mat_dir / name).exists():
            rows.append({"kind": "image", "shot_id": sid, "material": name,
                         "source": "materials", "seconds": seconds, "motion": motion})
            continue
        if fallback:
            rows.append({"kind": "image", "shot_id": sid, "material": fallback,
                         "source": "images", "seconds": seconds, "motion": motion})
            used_fallback += 1
            continue
        errors.append(f"镜头 {sid} 没有任何可用画面（没素材、也没商品图）—— 先在素材页配画面")

    if used_fallback and rows:
        warnings.append(
            f"{used_fallback} 个镜头没有专属素材，用商品图兜底 —— 想更好看就回素材页给这几镜配画面")
    if not rows and not errors:
        errors.append("没有分镜，快剪没有画面可排")
    return rows


def _config_hash(*, segments: list[dict], cfg: dict, bgm: dict | None,
                 voice: list | None = None) -> str:
    payload = {
        # D3：配音轨进指纹 —— 换音色/重录一句，成片的声音就变了，旧确认不能复用
        "voice": list(voice or []),
        # 素材段没有出片段号（no=0 会撞），所以把 kind / shot_id / 变速比一起算进指纹
        "segments": [[str(s.get("kind") or "ai"), int(s.get("no") or 0),
                      int(s.get("shot_id") or 0), s["file"],
                      round(float(s["actual_seconds"]), 3),
                      round(float(s.get("speed") or 1.0), 4),
                      bool(s["has_audio"]),
                      # 运镜变了画面就变了（静图段唯一决定观感的参数）
                      str(s.get("motion") or "")] for s in segments],
        "cfg": cfg,
        "bgm": {k: bgm.get(k) for k in ("file", "volume", "duck", "fade_out", "intro_skip")}
        if bgm else None,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def plan(doc: dict, *, film_dir: Path, config: dict | None = None,
         bgm_file: str = "", end_card_image: str = "", freecut: bool = False) -> dict:
    """规划合成（**不跑 ffmpeg 编码、不花钱**）。

    `bgm_file` / `end_card_image` 是已经落到项目目录里的**文件名**，由 API 层解析；
    这里只负责判断在不在、算时间轴、列警告。

    `freecut=True` = **免费快剪**（竞品 `pipeline-runner.ts:104-140` 的 compose 阶段）：
    不要求先有出片计划，每镜用自己的素材视频 → 参考图 → 商品图兜底，全程不调视频模型。
    """
    cfg = normalize_config(config)
    film = doc.get("film") or {}
    files = film.get("files") or {}
    plan_segs = (film.get("plan") or {}).get("segments") or []
    # 时间线（B6/B8）：AI 段与「素材当画面」的素材段按顺序混排；老数据没有 timeline
    # 就退回「只有 AI 段」的旧口径（向后兼容，不改旧项目的行为）。
    timeline = (film.get("plan") or {}).get("timeline") or []
    warnings: list[str] = []
    errors: list[str] = []

    data_root = film_dir.parent.parent
    pid = str(doc.get("id") or "")

    if freecut:
        # 免费快剪**永远按素材重排**：它卖的就是「不出片也能成片」，
        # 混进 AI 出片段反而会让「免费」名不副实。
        timeline = _freecut_timeline(doc, data_root, pid, warnings, errors)
        plan_segs = []
    elif not plan_segs and not timeline:
        errors.append("还没有出片计划，先规划出片")
        return {"ok": False, "segments": [], "boundaries": [], "warnings": warnings,
                "errors": errors, "config": cfg}

    by_no = {int(s.get("no") or 0): s for s in plan_segs}
    if timeline:
        order: list[dict] = []
        for item in timeline:
            if not isinstance(item, dict):
                continue
            if item.get("kind") == "clip":
                order.append({"kind": "clip", **item})
            elif item.get("kind") == "image":
                order.append({"kind": "image", **item})
            else:
                order.append({"kind": "ai", "seg": by_no.get(int(item.get("no") or 0))})
    else:
        order = [{"kind": "ai", "seg": s} for s in plan_segs]

    segments: list[dict] = []
    for it in order:
        if it["kind"] == "clip":
            name = Path(str(it.get("material") or "")).name
            src = data_root / "materials" / pid / name if name else None
            sid = int(it.get("shot_id") or 0)
            if not name or not src or not src.exists():
                errors.append(f"镜头 {sid} 的画面素材不在了（{name or '空'}）—— 回素材库重选一段")
                continue
            info = probe(src)
            if info["duration"] <= 0:
                errors.append(f"镜头 {sid} 的画面素材读不出时长（文件可能损坏）")
                continue
            planned = float(it.get("seconds") or 0)
            if planned <= 0:
                errors.append(f"镜头 {sid} 没写时长，素材段无法对齐")
                continue
            # 竞品 `composer.ts:506-521`：**只有无声素材才变速压槽**；有原生音轨的永不变速
            # （setpts 会让音画不同步）；超区间不做糖浆慢放/快进，退回 tpad 冻帧补齐。
            speed = 1.0
            if not info["has_audio"] and info["duration"] > 0:
                ratio = info["duration"] / planned
                if (1.001 < ratio <= SPEEDFIT_MAX_RATIO) or (SPEEDFIT_MIN_RATIO <= ratio < 0.999):
                    speed = ratio
                elif ratio > SPEEDFIT_MAX_RATIO:
                    warnings.append(
                        f"镜头 {sid} 的素材 {info['duration']:.1f}s 比这一镜 {planned:g}s 长太多，"
                        "只截前面一段，不加速")
                elif ratio < SPEEDFIT_MIN_RATIO:
                    warnings.append(
                        f"镜头 {sid} 的素材只有 {info['duration']:.1f}s，比这一镜 {planned:g}s 短 —— "
                        "末尾会定格补足（拍长一点更好）")
            segments.append({
                "no": 0,
                "kind": "clip",
                "shot_id": sid,
                "file": src.name,
                "path": str(src),
                "planned_seconds": round(planned, 3),
                "actual_seconds": round(planned, 3),
                "source_seconds": round(info["duration"], 3),
                "speed": round(speed, 4),
                "has_audio": bool(info["has_audio"]),
                "width": info["width"], "height": info["height"],
                # 素材里没有这句台词 → 不烧字幕（`_build_cues` 按 shot_ids 取台词）
                "shot_ids": [],
            })
            continue

        if it["kind"] == "image":
            # 静图段（免费快剪）：商品图 / 参考图循环成画面，运镜由 `drama_motion` 给。
            # 出处：竞品 `compose/route.ts:346-406`（素材优先级 → 商品图兜底 → motion）
            name = Path(str(it.get("material") or "")).name
            base = data_root / ("images" if it.get("source") == "images" else "materials") / pid
            src = base / name if name else None
            sid = int(it.get("shot_id") or 0)
            if not name or not src or not src.exists():
                errors.append(f"镜头 {sid} 的画面图不在了（{name or '空'}）—— 回素材库重选一张")
                continue
            planned = float(it.get("seconds") or 0)
            if planned <= 0:
                errors.append(f"镜头 {sid} 没写时长，静图段无法对齐")
                continue
            info = probe(src)
            if info["width"] <= 0 or info["height"] <= 0:
                errors.append(f"镜头 {sid} 的画面图读不出来（{name}）—— 文件可能坏了")
                continue
            segments.append({
                "no": 0,
                "kind": "image",
                "shot_id": sid,
                "file": src.name,
                "path": str(src),
                "planned_seconds": round(planned, 3),
                "actual_seconds": round(planned, 3),
                "speed": 1.0,
                "has_audio": False,
                "width": info["width"], "height": info["height"],
                "motion": str(it.get("motion") or drama_motion.motion_for_shot({})),
                # 静图段知道自己演的是哪一镜 → 字幕/配音能按镜对上
                "shot_ids": [sid],
            })
            continue

        s = it.get("seg") or {}
        no = int(s.get("no") or 0)
        rec = files.get(str(no)) or {}
        name = str(rec.get("name") or "")
        p = film_dir / Path(name).name if name else None
        if not name or not p or not p.exists():
            errors.append(f"第 {no} 段还没出（或文件不在了）—— 先出完再合成")
            continue
        info = probe(p)
        if info["duration"] <= 0:
            errors.append(f"第 {no} 段的视频读不出时长（文件可能损坏）")
            continue
        planned = float(s.get("seconds") or 0)
        segments.append({
            "no": no,
            "kind": "ai",
            "file": p.name,
            "path": str(p),
            "planned_seconds": round(planned, 3),
            "actual_seconds": round(info["duration"], 3),
            "has_audio": bool(info["has_audio"]),
            "width": info["width"], "height": info["height"],
            "shot_ids": [int(x) for x in (s.get("shot_ids") or [])],
        })
        if planned > 0 and abs(info["duration"] - planned) > 0.6:
            warnings.append(
                f"第 {no} 段实际 {info['duration']:.1f}s，计划 {planned:g}s —— "
                "字幕时间轴按实际时长等比缩放，可能有一点偏移")

    if not segments and not errors:
        errors.append("时间线上没有任何片段，先规划出片")
    if errors:
        return {"ok": False, "segments": segments, "boundaries": [],
                "warnings": warnings, "errors": errors, "config": cfg}

    tr = transition_info(cfg["transition"])
    if not tr["local"]:
        # 不偷偷降级：选 AI 档却硬切，成片上会留下没做过的转场
        warnings.append(
            f"转场选了「{tr['label']}」：这一档属于出片阶段，已出好的片段这里只能硬切。"
            "要真做，得按接缝顺序重出片段（花钱）")

    # D3 配音轨（人声落地前半截）：按镜头把 TTS 文件落到「段内第几秒、多长槽位」。
    # 有配音的段，音轨由配音替掉模型原生声（竞品 `composer.ts:525-548` 同口径）。
    voice_by_shot, vprobs = drama_voice.usable(doc, data_root)
    track = doc.get("voice_track") or {}
    for msg in vprobs:
        warnings.append(msg)
    if track and not voice_by_shot:
        warnings.append(
            "配音轨文件全不见了 —— 本次合成退回模型原生出声；要在成片里用 TTS，重新生成一次配音")
    shots_by_id = _shots(doc)
    any_tts = False
    for s in segments:
        slots: list[dict] = []
        planned = float(s["planned_seconds"] or 0)
        actual = float(s["actual_seconds"] or 0)
        scale = (actual / planned) if planned > 0 else 1.0
        for sid in s["shot_ids"]:
            shot = shots_by_id.get(sid) or {}
            try:
                d = float(shot.get("duration") or 0)
            except (TypeError, ValueError):
                d = 0.0
            slot = round(d * scale, 3)
            it = voice_by_shot.get(sid)
            if it:
                over = float(it.get("seconds") or 0) - slot
                if slot > 0 and over > 0.05:
                    warnings.append(
                        f"镜头 {sid} 的配音 {float(it['seconds']):.1f}s 比这一镜 {slot:.1f}s 长 —— "
                        "会在这镜结束处截断（台词说短一点，或给这一镜多留时间）")
                slots.append({"shot_id": sid, "slot": slot, "path": it["path"],
                              "file": it["file"],
                              "seconds": round(float(it.get("seconds") or 0), 3)})
            else:
                slots.append({"shot_id": sid, "slot": slot, "path": "", "file": "",
                              "seconds": 0.0})
        if any(x["path"] for x in slots):
            # 段内每一镜都留一个槽（没配音的补静音）—— 音轨长度必须与画面逐镜对齐
            s["voice_plan"] = slots
            s["voice_items"] = [x for x in slots if x["path"]]
            # 这一段的音轨改由配音出（原生声被替掉）→ 下游「有没有人声」一律按有算
            s["has_audio"] = True
            any_tts = True
    if track and not any_tts:
        warnings.append("配音轨里没有一句落在这次的时间线上 —— 本次合成不会用到它")

    # 音频：有没有对白轨决定能不能做闪避
    has_voice = any(s["has_audio"] for s in segments)
    bgm_path = None
    bgm: dict | None = None
    # `film_dir` = `<DATA>/films/<pid>` → 数据根是上两级
    data_root = film_dir.parent.parent
    if bgm_file:
        p = data_root / "bgm" / str(doc.get("id") or "") / Path(bgm_file).name
        if not p.exists():
            warnings.append("BGM 文件不在了，本次不加背景乐")
        else:
            info = probe(p)
            if not info["has_audio"]:
                warnings.append("BGM 文件里没有音频流，本次不加背景乐")
            else:
                mix = drama_audio.resolve_mix(cfg["bgm"]["volume"], cfg["bgm"]["duck"],
                                              has_voice=has_voice)
                bgm_path = p
                bgm = {"file": p.name, "path": str(p),
                       "volume": mix["volume"], "duck": mix["duck"],
                       "fade_out": cfg["bgm"]["fade_out"],
                       "intro_skip": cfg["bgm"]["intro_skip"],
                       "has_voice": has_voice}
    if cfg["bgm"]["duck"] and not has_voice:
        warnings.append("这几段没有对白轨，闪避没有可压的对象 —— 本次按不闪避混音")
    if not has_voice and not bgm:
        warnings.append("所有片段都没有音轨，成片会没有声音")

    # 时间轴：淡入淡出会让后一段提前 FADE_DURATION 开始（竞品 `timeline.ts:110-125`）
    fade = cfg["transition"] == "ffmpeg_fade"
    starts: list[float] = []
    acc = 0.0
    for i, s in enumerate(segments):
        if i and fade:
            acc = max(0.0, acc - FADE_DURATION)
        starts.append(round(acc, 3))
        acc += float(s["actual_seconds"])
    total = round(acc, 3)
    boundaries = [starts[i] for i in range(1, len(starts))]

    # 字幕条：段内按「分镜计划时长 × 实际/计划」铺，跨段前夹到下一段起点
    cues = _build_cues(doc, segments, starts, total)
    # 画面上叠的字（卖点/价格）：模型不再把字画进画面，改由这里按镜叠。
    # 走同一套时间轴与夹边界逻辑，只是取的字段不同、位置在画面上方。
    overs = _build_cues(doc, segments, starts, total, field="on_screen_text")
    if cfg["captions"] and not cues:
        warnings.append("分镜里没有台词，这次不会烧字幕（没有字幕可烧）")
    if cfg["captions"] and drama_captions.is_karaoke(cfg["caption_preset"]):
        warnings.append("卡拉OK逐字高亮：没有 TTS 词边界，高亮节奏按字数比例估算")

    # 尾卡
    end = dict(cfg["end_card"])
    end_image = None
    if end["enabled"]:
        if end["image"]:
            p = data_root / "images" / str(doc.get("id") or "") / Path(end["image"]).name
            if p.exists():
                end_image = p
            else:
                warnings.append("片尾卡的图片不在了，这次只画文字 CTA")
        if not end["text"] and not end_image:
            warnings.append("片尾卡开着，但既没有图片也没有文案 —— 什么都不会加")
        end["start"] = round(max(0.0, total - end["seconds"]), 3)

    prof = render_profile(cfg["render_preset"])
    # 画面比例由出片那一步定（`doc.film.ratio`），合成跟着它裁画布；
    # 老项目没有这个键 → 仍是 9:16，行为与改动前逐字一致。
    ratio = str(film.get("ratio") or "9:16")
    if ratio not in RESOLUTIONS:
        errors.append(f"不支持的画面比例：{ratio}（可选：{'、'.join(RATIOS)}）")
        ratio = "9:16"
    if prof["resolution"] not in RESOLUTIONS[ratio]:
        errors.append(f"不支持的渲染档：{prof['id']}")

    out = {
        "ok": not errors,
        "segments": segments,
        "starts": starts,
        "boundaries": boundaries,
        "total_seconds": total,
        "fade_seconds": FADE_DURATION if fade else 0.0,
        "config": cfg,
        "transition": tr,
        "render": prof,
        "ratio": ratio,
        "bgm": bgm,
        "end_card": end if end["enabled"] else None,
        "end_card_image": end_image.name if end_image else "",
        # 绝对路径 —— 合成时 cwd 不是数据目录，只给文件名会找错
        "end_card_image_path": str(end_image) if end_image else "",
        "caption": {
            "enabled": bool(cfg["captions"]),
            "preset": cfg["caption_preset"],
            "karaoke": drama_captions.is_karaoke(cfg["caption_preset"]),
            "count": len(cues),
            "cues": cues,
        },
        # 画面上叠的字：**不受字幕开关影响**（字幕关了，卖点字仍要上）
        "overlay": {
            "preset": "bold",
            "count": len(overs),
            "cues": overs,
        },
        # D3 配音轨：界面要能说清「这次成片用的是谁的配音、几句、有没有问题」
        "voice": {
            "enabled": any_tts,
            "grounded": bool(cfg["voice_ground"] and any_tts),
            "voice": str(track.get("voice") or ""),
            "count": sum(len(s.get("voice_items") or []) for s in segments),
            "problems": list(vprobs),
        },
        "warnings": warnings,
        "errors": errors,
    }
    out["plan_hash"] = _config_hash(
        segments=segments, cfg=cfg, bgm=bgm,
        voice=[f"{it['shot_id']}:{it['file']}:{round(float(it['seconds']), 3)}"
               for s in segments for it in (s.get("voice_items") or [])])
    return out


def _build_cues(doc: dict, segments: list[dict], starts: list[float],
                total: float, field: str = "dialogue") -> list[dict]:
    """分镜某一列文字 → 成片时间轴上的文字条。

    `field="dialogue"` 是台词字幕；`field="on_screen_text"` 是画面上要叠的卖点/价格字
    （模型不再把字画进画面，改由这里后期叠 —— 见 SOURCE.md 产出 3）。
    · 段内：`分镜计划时长` 按 `实际段长 / 计划段长` 等比缩放；
    · 跨段：下一条字幕不得越过下一段的**实际起点**（淡入淡出会把它提前），
      夹完后短于 0.05s 的丢弃 —— 与竞品 `timeline.ts:78-88` 的夹法一致。
    """
    shots = _shots(doc)
    cues: list[dict] = []
    for seg, start in zip(segments, starts):
        planned = float(seg["planned_seconds"] or 0)
        actual = float(seg["actual_seconds"] or 0)
        scale = (actual / planned) if planned > 0 else 1.0
        cursor = 0.0
        for sid in seg["shot_ids"]:
            shot = shots.get(sid)
            if not shot:
                continue
            try:
                d = float(shot.get("duration") or 0)
            except (TypeError, ValueError):
                d = 0.0
            text = str(shot.get(field) or "").strip()
            if text and d > 0:
                cues.append({
                    "shot": sid,
                    "text": text,
                    "start": round(start + cursor * scale, 3),
                    "end": round(start + (cursor + d) * scale, 3),
                })
            cursor += d

    # 夹到下一段起点
    edges = sorted(starts[1:] + [total])
    kept: list[dict] = []
    for c in cues:
        edge = next((e for e in edges if e > c["start"]), total)
        if c["end"] > edge:
            c["end"] = round(max(c["start"], edge), 3)
        if c["end"] - c["start"] >= 0.05:
            kept.append(c)
    return kept


# ---------------------------------------------------------------------------
# 滤镜图（纯字符串，可单测；真正执行在 render）
# ---------------------------------------------------------------------------


def _ass_path_escape(p: str) -> str:
    """`subtitles=` 的路径转义（竞品 `composer.ts:53-55`）。"""
    return p.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def build_graph(p: dict, *, out_size: tuple[int, int],
                ass_path: str = "", font_path: str = "") -> dict:
    """把一份 plan 编译成 ffmpeg 输入/滤镜/映射。不跑进程。

    返回 `{inputs, filter, maps, audio_index, duration}`。
    `inputs` 是除片段以外的额外输入项（每个是已经拆好的 argv 片段列表）。
    """
    width, height = out_size
    segs = p["segments"]
    cfg = p["config"]
    total = float(p["total_seconds"])
    fade = cfg["transition"] == "ffmpeg_fade"

    inputs: list[list[str]] = [[s["path"]] for s in segs]
    parts: list[str] = []

    # 画面：统一规格 → 拼接 / 交叉淡化
    for i, s in enumerate(segs):
        d = float(s["actual_seconds"])
        if s.get("kind") == "image":
            # 静图段：**逐字照竞品 `composer.ts:498`** —— 先在 2 倍画布上留边缩放，
            # 取单帧，再让 zoompan 按运镜铺满整段，最后降采样回目标画布。
            # 2 倍画布是为了运镜时不出锯齿（竞品同款 supersample）。
            w2, h2 = width * 2, height * 2
            motion = drama_motion.motion_filter(
                str(s.get("motion") or ""), w2, h2, d)
            parts.append(
                f"[{i}:v]scale={w2}:{h2}:force_original_aspect_ratio=decrease,"
                f"pad={w2}:{h2}:(ow-iw)/2:(oh-ih)/2,"
                f"trim=end_frame=1,setpts=PTS-STARTPTS,{motion},"
                f"scale={width}:{height}:flags=lanczos,"
                f"tpad=stop_mode=clone:stop_duration={d:.6f},"
                f"trim=duration={d:.6f},setpts=PTS-STARTPTS,{SEGMENT_NORM}[v{i}]")
            continue
        # 素材段的两种适配（竞品 `composer.ts:506-521`）：
        #  · speed != 1 → setpts 拉伸到槽位（保住首尾两端，不靠裁尾）
        #  · 拉伸后/不变速仍不够长 → tpad 冻最后一帧补足，再 trim 到精确槽位
        # 没变速、不是素材段时，这两段拼进去是空串 → 滤镜与改动前逐字一致。
        speed = float(s.get("speed") or 1.0)
        use_speed = 0.01 < speed < 99 and abs(speed - 1.0) > 0.0005
        fit = f"setpts=PTS/{speed:.4f}," if use_speed else ""
        pad = (f"tpad=stop_mode=clone:stop_duration={d:.6f},"
               if s.get("kind") == "clip" else "")
        parts.append(
            f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height}:(iw-{width})/2:(ih-{height})/2,"
            f"setsar=1,fps=30,settb=AVTB,"
            f"{fit}{pad}trim=duration={d:.6f},setpts=PTS-STARTPTS,{SEGMENT_NORM}[v{i}]")

    cur = "v0"
    acc = float(segs[0]["actual_seconds"])
    for i in range(1, len(segs)):
        d = float(segs[i]["actual_seconds"])
        nxt = f"x{i}"
        if fade:
            offset = max(0.0, acc - FADE_DURATION)
            parts.append(
                f"[{cur}][v{i}]xfade=transition=fade:duration={FADE_DURATION:g}:"
                f"offset={offset:.6f}[{nxt}]")
            acc = max(0.0, acc + d - FADE_DURATION)
        else:
            parts.append(f"[{cur}][v{i}]concat=n=2:v=1:a=0[{nxt}]")
            acc += d
        cur = nxt
    v_cur = f"[{cur}]"

    # 声音：每段音轨（没有就补静音）→ 与画面同步地拼
    any_audio = any(s["has_audio"] for s in segs)
    ground = bool(cfg.get("voice_ground", True))
    a_cur = ""
    if any_audio:
        for i, s in enumerate(segs):
            d = float(s["actual_seconds"])
            vplan = s.get("voice_plan") or []
            if vplan:
                # D3 人声落地：这一段的音轨**由 TTS 拼出来**，替掉模型原生声
                # （竞品 `composer.ts:525-548`：TTS voice-over > native audio > silence）。
                # 每镜一个槽：有配音的过「去播音腔」链（`voice-ground.ts:19-22`），
                # 没配音的补等长静音 —— 音轨与画面逐镜对齐，不靠累加猜。
                labels: list[str] = []
                for j, sl in enumerate(vplan):
                    lab = f"tts{i}_{j}"
                    slot = float(sl.get("slot") or 0)
                    if sl.get("path"):
                        idx = len(inputs)
                        inputs.append([sl["path"]])
                        chain = f"{drama_tts.voice_ground_chain()}," if ground else ""
                        parts.append(
                            f"[{idx}:a]aresample=44100,{chain}"
                            f"aformat=sample_fmts=fltp:channel_layouts=stereo,"
                            f"apad,atrim=duration={slot:.6f},asetpts=PTS-STARTPTS[{lab}]")
                    else:
                        parts.append(
                            f"anullsrc=r=44100:cl=stereo,atrim=duration={slot:.6f},"
                            f"asetpts=PTS-STARTPTS[{lab}]")
                    labels.append(lab)
                cur_l = labels[0]
                for k in range(1, len(labels)):
                    nxt_l = f"ttsc{i}_{k}"
                    parts.append(f"[{cur_l}][{labels[k]}]concat=n=2:v=0:a=1[{nxt_l}]")
                    cur_l = nxt_l
                # 槽位合计可能与段实际时长差几十毫秒 → 统一补齐/截到段长
                parts.append(
                    f"[{cur_l}]apad,atrim=duration={d:.6f},asetpts=PTS-STARTPTS[a{i}]")
            elif s["has_audio"]:
                parts.append(
                    f"[{i}:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                    f"apad,atrim=duration={d:.6f},asetpts=PTS-STARTPTS[a{i}]")
            else:
                parts.append(
                    f"anullsrc=r=44100:cl=stereo,atrim=duration={d:.6f},"
                    f"asetpts=PTS-STARTPTS[a{i}]")
        a_cur = "a0"
        for i in range(1, len(segs)):
            nxt = f"acs{i}"
            if fade:
                parts.append(f"[{a_cur}][a{i}]acrossfade=d={FADE_DURATION:g}[{nxt}]")
            else:
                parts.append(f"[{a_cur}][a{i}]concat=n=2:v=0:a=1[{nxt}]")
            a_cur = nxt

    # D3 房间底噪：整条时间线垫一层棕噪（`voice-ground.ts:29-35`）—— 句间空白不许掉到
    # 数字零，那是 TTS 最响的破绽。有 TTS 用 0.008；只有模型原生声时 0.004（原生片段
    # 自带房间感，底噪只负责把跨切的空间统一起来）。
    # 顺序照竞品：先接音轨 → 垫底噪 → 再叠 BGM（`composer.ts:608-613` → `:617`）。
    any_tts_graph = any(s.get("voice_plan") for s in segs)
    if ground and a_cur:
        parts.append(f"{drama_tts.room_tone_source(0.008 if any_tts_graph else 0.004)}[roomtone]")
        parts.append(f"[{a_cur}][roomtone]amix=inputs=2:duration=first:"
                     "dropout_transition=0:normalize=0[voice_grounded]")
        a_cur = "voice_grounded"

    # BGM：垫底 + 可选闪避（竞品 `composer.ts:617-649`）
    bgm = p.get("bgm")
    if bgm:
        idx = len(inputs)
        inputs.append([bgm["path"]])
        intro = (f"atrim=start={bgm['intro_skip']:.3f},asetpts=PTS-STARTPTS,"
                 if bgm["intro_skip"] > 0 else "")
        fade_out = float(bgm["fade_out"])
        fade_arg = (f",afade=t=out:st={max(0.0, total - fade_out):.3f}:d={fade_out:.3f}"
                    if fade_out > 0 else "")
        parts.append(
            f"[{idx}:a]{intro}aloop=loop=-1:size=2e9,"
            f"volume={float(bgm['volume']):.3f}{fade_arg}[bgm_vol]")
        if a_cur:
            if bgm["duck"]:
                parts.append(f"[{a_cur}]asplit=2[nar_mix][nar_key]")
                parts.append(
                    "[bgm_vol][nar_key]sidechaincompress=threshold=0.03:ratio=8:"
                    "attack=20:release=400[bgm_duck]")
                parts.append(
                    "[nar_mix][bgm_duck]amix=inputs=2:duration=first:"
                    "dropout_transition=0:normalize=0[aout]")
            else:
                parts.append(
                    f"[{a_cur}][bgm_vol]amix=inputs=2:duration=first:"
                    "dropout_transition=0:normalize=0[aout]")
        else:
            parts.append("[bgm_vol]anull[aout]")
        a_cur = "aout"

    # 字幕（竞品 `composer.ts:651-704`）
    cap = p.get("caption") or {}
    if cap.get("enabled") and cap.get("cues"):
        if ass_path:
            # 🩸 实测（本机 ffmpeg）：`subtitles=` 的 Windows 盘符路径**必须加单引号**，
            # 裸写 `C\:/…` 会被滤镜解析器在冒号处截断 → `Invalid argument`。
            # 竞品不带引号能跑是它的 ffmpeg 版本差异，不是通用写法。
            fontsdir = (f":fontsdir='{_ass_path_escape(str(Path(font_path).parent))}'"
                        if font_path else "")
            parts.append(
                f"{v_cur}subtitles='{_ass_path_escape(ass_path)}'{fontsdir}[vcap]")
            v_cur = "[vcap]"
        else:
            # 尾卡只在最后几秒出现，不影响全片字幕的安全边距 → 一律按无卡片（0.22）
            chain = drama_captions.drawtext_chain(
                cap["cues"], width, cap.get("preset"),
                position="bottom", has_card=False,
                font_file=font_path or None)
            if chain:
                parts.append(f"{v_cur}{chain}[vcap]")
                v_cur = "[vcap]"

    # 画面上叠的字（卖点/价格）：走 drawtext，位置固定在画面上方（h*0.08），
    # 与底部字幕错开。karaoke 预设返回空串 —— 这里固定用 bold，不受字幕预设影响。
    ov = p.get("overlay") or {}
    if ov.get("cues"):
        chain = drama_captions.drawtext_chain(
            ov["cues"], width, ov.get("preset") or "bold",
            position="top", has_card=False,
            font_file=font_path or None)
        if chain:
            parts.append(f"{v_cur}{chain}[vover]")
            v_cur = "[vover]"

    # 尾卡：图片（QR/商品图）+ 可选 CTA，只在最后 N 秒出现（竞品 `end-card.ts:33-63`）
    end = p.get("end_card")
    if end:
        start = float(end.get("start") or max(0.0, total - float(end["seconds"])))
        enable = f"gte(t,{start:.3f})"
        card_img = p.get("end_card_image_path") or p.get("end_card_image")
        if card_img:
            idx = len(inputs)
            inputs.append(["-loop", "1", "-t", f"{total:.3f}", card_img])
            qr_w = max(1, round(width * float(end["qr_ratio"])))
            parts.append(f"[{idx}:v]scale={qr_w}:{qr_w}[qr]")
            parts.append(
                f"{v_cur}[qr]overlay=x=(main_w-overlay_w)/2:"
                f"y=(main_h-overlay_h)/2:enable='{enable}'[vend]")
            v_cur = "[vend]"
        if end.get("text"):
            font_size = round(width * 0.05)
            y = (f"(h-{max(1, round(width * float(end['qr_ratio'])))}"
                 f")/2-{round(font_size * 2)}"
                 if p.get("end_card_image") else "h*0.62")
            cta = drama_cover.build_drawtext(
                text=end["text"], font_size=font_size, font_color="white",
                border_w=max(2, round(width * 0.005)),
                box={"color": "black@0.5", "borderW": round(width * 0.02)},
                x="(w-text_w)/2", y=y, enable=enable, font_file=font_path or None)
            parts.append(f"{v_cur}{cta}[vcta]")
            v_cur = "[vcta]"

    filter_complex = drama_cover.unshell_filter(";".join(parts))
    maps = ["-map", v_cur]
    if a_cur:
        maps += ["-map", f"[{a_cur}]"]
    return {
        "inputs": inputs,
        "filter": filter_complex,
        "maps": maps,
        "duration": total,
        # 有没有声音输出 —— 决定要不要 `-c:a`；以前靠猜 map 标签，太脆
        "has_audio": bool(a_cur),
    }


def render(p: dict, out: Path, *, ass_text: str = "", font_path: str = "") -> Path:
    """按 plan 跑一次本地合成。**零生成费**，但仍是「出片」—— 由主人点。"""
    if p.get("errors"):
        raise RuntimeError("；".join(p["errors"][:3]))
    if not p.get("segments"):
        raise RuntimeError("没有可合成的片段")
    ff = ffmpeg_path()
    if not ff:
        raise RuntimeError("找不到 ffmpeg，请设置 VT_FFMPEG")
    cap = p.get("caption") or {}
    # 🩸 本机 ffmpeg 的 fontconfig 默认配置是坏的（实测 `Fontconfig error: Cannot
    # load default config file`）→ drawtext / libass 都必须吃显式字体文件，
    # 否则整个成片直接失败。这不是「字幕可选」的问题，是画不出来。
    if cap.get("enabled") and cap.get("cues") and not font_path:
        raise RuntimeError("找不到中文字体文件（VT_FONT 或系统字体）—— 字幕画不出来，先配字体")

    out = Path(out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    prof = render_profile((p.get("config") or {}).get("render_preset"))
    # 画布尺寸跟计划的 ratio 走（plan 阶段已校验合法）；缺省 9:16 保持旧行为
    width, height = RESOLUTIONS[p.get("ratio") or "9:16"][prof["resolution"]]

    ass_path = ""
    if ass_text:
        ass_path = str(out.with_suffix(".ass"))
        Path(ass_path).write_text(ass_text, encoding="utf-8")

    graph = build_graph(p, out_size=(width, height),
                        ass_path=ass_path, font_path=font_path)

    # 片段 / BGM 都是绝对路径；尾卡图片项已经是带 -loop/-t 的 argv 片段
    args: list[str] = ["-hide_banner", "-loglevel", "error", "-y"]
    for item in graph["inputs"]:
        if len(item) == 1:
            args += ["-i", str(Path(item[0]).resolve())]
        else:
            args += [*item[:-1], "-i", str(Path(item[-1]).resolve())]
    args += ["-filter_complex", graph["filter"]]
    args += graph["maps"]
    args += ["-t", f"{float(graph['duration']):.6f}"]
    preset, crf = safe_encode(prof)
    args += ["-c:v", "libx264", "-preset", preset, "-crf", str(crf),
             "-pix_fmt", "yuv420p"]
    if graph["has_audio"]:
        args += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
    else:
        args += ["-an"]
    args += ["-movflags", "+faststart", str(out)]

    proc = subprocess.run([ff, *args], capture_output=True, text=True,
                          errors="ignore", timeout=1800)
    if proc.returncode != 0 or not out.exists():
        raise RuntimeError(f"合成失败：{(proc.stderr or '')[-600:]}")
    return out
