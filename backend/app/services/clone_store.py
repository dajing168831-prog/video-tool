"""复刻任务的持久化。

任务目录：data/clone/<cid>/
  task.json      状态机 + 配方 + 出片记录
  source.mp4     参考片
  keyframes/     诊断卡用的关键帧
  render/<rid>/  成片与封面

为什么不放 temp_dir：temp 有 TTL 自动清理，而配方是"分析一次、出十片"的
复用件，被清掉就得重新花 ASR 的钱。

写盘一律 tmp + replace：轮询端随时在读，不能让它读到半个 json。
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import time
import uuid
from pathlib import Path

from app.core.config import settings
from app.services.edit_spec import SLOT_ORDER as _SLOT_ORDER

log = logging.getLogger(__name__)

_HEX = set("0123456789abcdef")


def new_id() -> str:
    return uuid.uuid4().hex


def valid(cid: str) -> bool:
    """id 只允许十六进制，防止路径穿越。"""
    return bool(cid) and len(cid) <= 64 and all(c in _HEX for c in cid.lower())


def task_dir(cid: str) -> Path:
    if not valid(cid):
        raise ValueError(f"非法任务 id: {cid!r}")
    return settings.clone_dir / cid


def source_path(cid: str) -> Path:
    return task_dir(cid) / "source.mp4"


def keyframe_dir(cid: str) -> Path:
    d = task_dir(cid) / "keyframes"
    d.mkdir(parents=True, exist_ok=True)
    return d


# 可上传参考图的槽位 = edit_spec.SLOT_ORDER（提示词里的图片编号就是这条顺序）。
# 加槽位只能往后追加：插队会让所有历史提示词的图片编号错位。
# 人物槽按"第几个被换的人"排（person = 第一个人），一个人一张图。
# 🩸 人数上限由 edit_spec.MAX_PERSONS 定（12），别再在这里写死三个。
REF_SLOTS = tuple(_SLOT_ORDER)


# 风格参考**视频**（A9）：不进 REF_SLOTS —— 那是图片顺序表，图号就是提示词里的
# @图片N。视频有自己的编号（@视频2 / <Video 2>），单独存一个文件。
REF_VIDEO_SLOTS = ("style",)


def ref_video_path(cid: str, slot: str = "style") -> Path:
    """风格参考视频。和风格参考图**互斥**（上传接口互相删除）。"""
    if slot not in REF_VIDEO_SLOTS:
        raise ValueError(f"未知的视频槽位: {slot!r}")
    return task_dir(cid) / f"ref_{slot}.mp4"


# 原片声音处理（C4）要用的两段用户音频：bgm = 换掉原片背景音乐的那首，
# sfx = 额外叠加的音效。都不是参考图/参考视频，不进任何编号表。
REF_AUDIO_KINDS = ("bgm", "sfx")
_AUDIO_EXT = (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus")


def ref_audio_path(cid: str, kind: str) -> Path:
    """用户上传的 BGM / 音效。扩展名按实际文件走，取目录里第一个匹配项。"""
    if kind not in REF_AUDIO_KINDS:
        raise ValueError(f"未知的音频类型: {kind!r}")
    d = task_dir(cid)
    for ext in _AUDIO_EXT:
        p = d / f"ref_{kind}{ext}"
        if p.exists():
            return p
    return d / f"ref_{kind}.mp3"


def ref_path(cid: str, slot: str) -> Path:
    """某个槽位的参考图。

    person 沿用历史文件名 subject.jpg —— 已经分析过的老任务不能因为改名就找不到图。
    每个槽位只留一张：多角度互相打架，模型反而抓不准。
    """
    if slot not in REF_SLOTS:
        raise ValueError(f"未知的素材槽位: {slot!r}")
    name = "subject.jpg" if slot == "person" else f"ref_{slot}.jpg"
    return task_dir(cid) / name


def subject_path(cid: str) -> Path:
    """换人物时用户上传的那张参考图（= ref_path(cid, "person")）。"""
    return ref_path(cid, "person")


def subject_desc_path(cid: str, slot: str = "person") -> Path:
    """**某一个**人物槽位的参考图外观描述（2–3 个稳定静态特征）。

    🩸 为什么要有：官方两家都要求主体**用具体特征定义**，不是只给个图号。
      · 火山《Seedance 2.0 提示词指南》§1「定义主体」：用 2–3 个清晰、稳定的
        静态特征（服饰、发型、外观、类别）描述，确保唯一可识别性。
      · MiniMax《H3 提示词指南》ref-en §5 示例：
        `<Subject 1> is the young woman in <Picture 1>, with long dark hair,
         a blue cardigan, and a thin silver necklace.`
    以前我们只写「@图片N中的人物」「with the face… shown there」——图号有了，
    特征一个没写。这份文件补的就是这一步。

    🩸 2026-11-01：**一人一份**。以前整个任务只有一个 `subject_desc.json`
    （= 第一个人的），编译器把它套到每一张人物参考图上 —— 第二个人（上传的
    真人男性照）被定义成「古装女性」，换人只能换错。现在按槽位分开存：
    `person` 沿用历史文件名（老任务不能因为改名就找不到），
    `person2` → `subject_desc_person2.json`，以此类推。
    """
    if slot == "person":
        return task_dir(cid) / "subject_desc.json"
    if slot not in REF_SLOTS:
        raise ValueError(f"未知的素材槽位: {slot!r}")
    return task_dir(cid) / f"subject_desc_{slot}.json"


def prompts_path(cid: str) -> Path:
    """agent 读官方 skill 现写的**逐段编辑指令**。

    🩸 两家（2.5 / H3）写**同一个文件**：出片只读一份，谁写的就是谁的。
    靠内容里的 `agent` 标记 + 签名区分 —— 签名带型号和 skill 指纹，
    换了家必不命中（`clone_agent.cached` / `h3_agent.cached` 各自判）。
    """
    return task_dir(cid) / "prompts.json"


def segment_dir(cid: str) -> Path:
    d = task_dir(cid) / "segments"
    d.mkdir(parents=True, exist_ok=True)
    return d


def render_dir(cid: str, rid: str) -> Path:
    if not valid(rid):
        raise ValueError(f"非法出片 id: {rid!r}")
    d = task_dir(cid) / "render" / rid
    d.mkdir(parents=True, exist_ok=True)
    return d


def save(task: dict) -> None:
    d = task_dir(task["id"])
    d.mkdir(parents=True, exist_ok=True)
    p = d / "task.json"
    tmp = d / f".task.{os.getpid()}.{time.time_ns()}.tmp"
    tmp.write_text(json.dumps(task, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def load(cid: str) -> dict | None:
    if not valid(cid):
        return None
    p = task_dir(cid) / "task.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def new_task(cid: str, *, meta: dict | None = None) -> dict:
    return {
        "id": cid,
        "created_at": time.time(),
        "state": "queued",          # queued | analyzing | analyzed | failed
        "stage": "",
        "pct": 0,
        "error": "",
        "meta": meta or {},
        "recipe": None,
        "renders": [],
    }


def find_recent_source(platform: str, title: str, author: str,
                       *, hours: float = 24) -> str | None:
    """同一条原片刚分析过 → 返回它的 cid，别再开一个新作品。

    判据用「平台 + 标题 + 作者」：同一个作品的不同分享链接（v.douyin.com/xxx
    每次转出来的短链都可能不同）解析出来的这三样是一样的。
    🩸 为什么必须去重：历史页按"作品"列，每次重贴链接都会多出一条 0 版的
    记录 —— 2026-10-22 实测用户只出片一次，历史里却出现两条。
    只认**分析成功且有配方**的任务，失败/进行中的不算。
    """
    platform = (platform or "").strip().lower()
    title = (title or "").strip()
    author = (author or "").strip()
    if not platform or not title:
        return None
    cutoff = time.time() - max(0.0, hours) * 3600
    # 排序键：**出过片的优先**，其次才是新的。
    # 🩸 只按时间挑会挑到"刚解析、一版都没出"的那条，用户重贴链接反而
    # 被带回空作品（2026-10-22 真实数据里就是这样：两条同片，新的一条 0 版）。
    best: tuple[tuple[int, float], str] | None = None
    root = settings.clone_dir
    if not root.exists():
        return None
    for d in root.iterdir():
        if not d.is_dir() or not valid(d.name):
            continue
        try:
            if d.stat().st_mtime < cutoff:
                continue
            t = load(d.name)
        except Exception:  # noqa: BLE001
            continue
        if not t or t.get("state") != "analyzed" or not t.get("recipe"):
            continue
        m = t.get("meta") or {}
        if (m.get("platform") or "").strip().lower() != platform:
            continue
        if (m.get("title") or "").strip() != title:
            continue
        if author and (m.get("author") or "").strip() != author:
            continue
        created = float(t.get("created_at") or 0)
        if created < cutoff:
            continue
        has_done = any((r or {}).get("state") == "done"
                       for r in (t.get("renders") or []))
        score = (1 if has_done else 0, created)
        if best is None or score > best[0]:
            best = (score, d.name)
    return best[1] if best else None


def public(task: dict) -> dict:
    """对外视图：去掉配方正文（逐字时间轴很长），只给摘要。"""
    from app.services import recipe as recipe_mod

    rec = task.get("recipe") or {}
    shots = [
        {"i": s["i"], "start": s["start"], "end": s["end"], "dur": s["dur"],
         # 运动量：前端据此标注"这一镜会被怎么处理"（静态重绘 / 视频重制）
         "motion": s.get("motion", 0.0)}
        for s in (rec.get("shots") or [])
    ]
    renders = []
    for r in task.get("renders") or []:
        renders.append({
            "id": r["id"],
            "state": r.get("state"),
            "pct": r.get("pct", 0),
            "stage": r.get("stage", ""),
            "script": r.get("script", ""),
            "error": r.get("error", ""),
            "duration": r.get("duration"),
            "replaced_shots": r.get("replaced_shots", 0),
            "created_at": r.get("created_at"),
            # 延长出来的版本要在版本切换里能认出来（标「延长 +Ns」而不是普通重制）
            "kind": r.get("kind") or "render",
            "extend": r.get("extend") or None,
            # 质检结论：作品库里要直接标"可发布 / 需复核"，不然用户得逐版点进去看
            "qc_ok": (r.get("qc") or {}).get("ok"),
        })
    return {
        "id": task["id"],
        # 作品库按创建时间排序、卡片上要显示时间（历史列表原本就有，这里补进对外视图）
        "created_at": task.get("created_at"),
        "state": task.get("state"),
        "stage": task.get("stage", ""),
        "pct": task.get("pct", 0),
        "error": task.get("error", ""),
        "meta": task.get("meta") or {},
        "summary": recipe_mod.summary(rec) if rec else None,
        # 原片文案原文：用户要在这上面改，没有它就等于让人凭空写
        "speech_text": _join_speech(rec),
        # 逐句台词 + 说话人：前端按行展示「谁说了哪句」、指定只重配谁
        "speech_lines": speech_lines(task),
        "shots": shots,
        "renders": renders,
        # 用户传过换人参考图没有 —— 前端据此决定显示"已上传"还是"去上传"
        "has_subject": subject_path(task["id"]).exists(),
        # 各槽位素材有没有 —— 前端据此显示缩略图/空态
        "refs": {s: ref_path(task["id"], s).exists() for s in REF_SLOTS},
        # 风格参考视频（A9）：和 `refs` 分开列，它不是图片槽（没有图号）
        "ref_videos": {s: ref_video_path(task["id"], s).exists()
                       for s in REF_VIDEO_SLOTS},
        # 原片声音处理用的音频（C4）：bgm 换曲、sfx 加音效
        "audio_refs": {k: ref_audio_path(task["id"], k).exists()
                       for k in REF_AUDIO_KINDS},
    }


def _join_speech(recipe: dict) -> str:
    segs = (recipe.get("speech") or {}).get("segments") or []
    return "".join((s.get("text") or "").strip() for s in segs)


def speech_lines(task: dict) -> list[dict]:
    """逐句台词 + 说话人，给前端按行展示「谁说了哪句」。

    🩸 2026-10-27：以前只给 `speech_text`（`_join_speech` 把全部分段拼成一坨），
    前端拿到的是一整段文字 —— **哪句是谁说的全丢了**，所以没法做"只重配其中
    一个人"。逐句数据一直都在 `recipe.speech.segments` 里，只是没往外给。

    每行：`{start, end, text, speaker, person}`——
      · `speaker` = 原片 ASR 给的声纹编号（`utterances[].additions.speaker`），
        没开出来就是空串；前端据此显示「说话人1 / 说话人2」。
      · `person` = 映射到盘点里的人物 id（`video_edit._assign_speakers`，
        声纹投票 + 单人镜头画面），判不出就是空串。
        前端看到 **`person` 全空** 就该说"这片分不出说话人，只能整体重配"，
        **不许假装分出来了**。

    🩸 盘点走 `vision_plan.cached_only()`：详情接口每次打开页面都调这里，
    走 `inventory()` 会**没缓存时当场花钱**。没有盘点就只给声纹编号。
    """
    rec = task.get("recipe") or {}
    segs = (rec.get("speech") or {}).get("segments") or []
    rows = [
        {"start": round(float(s.get("start") or 0.0), 3),
         "end": round(float(s.get("end") or 0.0), 3),
         "text": str(s.get("text") or "").strip(),
         "speaker": str(s.get("speaker") or "").strip(),
         "person": ""}
        for s in segs if str(s.get("text") or "").strip()
    ]
    if not rows:
        return []
    try:
        from app.services import vision_plan
        inv = vision_plan.cached_only(str(task.get("id") or ""))
    except Exception as e:  # noqa: BLE001
        logging.getLogger(__name__).warning("读盘点缓存失败，只给声纹编号：%s", e)
        inv = None
    if inv:
        from app.services import video_edit
        # `_assign_speakers` 读 `voice_lines[i]["asr_speaker"]`、写 `["speaker"]`；
        # 传副本，别把 `speaker`（声纹编号）字段名占用掉。
        work = [{"start": r["start"], "end": r["end"], "text": r["text"],
                 "asr_speaker": r["speaker"]} for r in rows]
        try:
            video_edit._assign_speakers({"voice_lines": work}, inv)
        except Exception as e:  # noqa: BLE001
            logging.getLogger(__name__).warning("推说话人失败：%s", e)
        else:
            for r, w in zip(rows, work):
                r["person"] = str(w.get("speaker") or "")
    return rows


def history(limit: int = 50) -> list[dict]:
    """按创建时间倒序列出任务（只扫 task.json，不碰视频）。"""
    if not settings.clone_dir.exists():
        return []
    items = []
    for d in settings.clone_dir.iterdir():
        if not d.is_dir():
            continue
        p = d / "task.json"
        if not p.exists():
            continue
        try:
            t = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        items.append(t)
    items.sort(key=lambda t: t.get("created_at", 0), reverse=True)
    return [public(t) for t in items[:limit]]


def cleanup_expired(ttl: float) -> int:
    """删除超过 ttl 秒的复刻任务目录。默认 ttl 由调用方给（比 temp 长得多）。"""
    if not settings.clone_dir.exists():
        return 0
    now = time.time()
    removed = 0
    for d in settings.clone_dir.iterdir():
        if not d.is_dir():
            continue
        try:
            if now - d.stat().st_mtime > ttl:
                shutil.rmtree(d, ignore_errors=True)
                removed += 1
        except Exception:  # noqa: BLE001
            continue
    return removed
