"""复刻任务的后台执行。

为什么用线程池而不是 Celery/Redis：分析/出片的耗时全在 ffmpeg 与外部 HTTP 上，
Python 侧只是等子进程，GIL 不构成瓶颈。多进程部署时再换 Redis 队列，
接口（submit_analyze / submit_render）保持不变即可。

一个任务同时只跑一件事：分析和出片抢同一个 source.mp4 和同一份配方，
并发跑只会互相踩。
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.core.config import settings
from app.services import clone_store as store
from app.services import clone_pipeline, error_report, scene

log = logging.getLogger(__name__)

_POOL = ThreadPoolExecutor(max_workers=max(1, settings.clone_workers),
                           thread_name_prefix="clone")
_BUSY: dict[str, str] = {}            # cid -> "analyze" | render id
_BUSY_LOCK = threading.Lock()


def is_busy(cid: str) -> bool:
    with _BUSY_LOCK:
        return cid in _BUSY


def _claim(cid: str, what: str) -> bool:
    with _BUSY_LOCK:
        if cid in _BUSY:
            return False
        _BUSY[cid] = what
        return True


def _release(cid: str) -> None:
    with _BUSY_LOCK:
        _BUSY.pop(cid, None)


# ---------------------------------------------------------------------------


def submit_analyze(cid: str, video: Path, *, url: str = "") -> bool:
    if not _claim(cid, "analyze"):
        return False
    _POOL.submit(_analyze, cid, video, url)
    return True


def submit_render(cid: str, rid: str, *, script: str | None,
                  mask_bottom: bool = False, regen_prompt: str = "",
                  regen_shots: list[int] | None = None,
                  regen_mode: str = "shots",
                  regen_channel: str = "auto",
                  edit_spec: dict | None = None,
                  max_segments: int = 0,
                  force: bool = False) -> bool:
    if not _claim(cid, rid):
        return False
    _POOL.submit(_render, cid, rid, script, mask_bottom,
                 regen_mode, regen_channel, edit_spec, max_segments, force)
    return True


def submit_extend(cid: str, rid: str, *, base_render_id: str = "",
                  direction: str = "back", seconds: int = 5, content: str = "",
                  model: str = "", resolution: str = "",
                  with_audio: bool | None = None,
                  with_transition: bool = False,
                  transition_desc: str = "",
                  ref_images: list[str] | None = None,
                  content_mode: str = "") -> bool:
    if not _claim(cid, rid):
        return False
    _POOL.submit(_extend, cid, rid, base_render_id, direction, seconds,
                 content, model, resolution, with_audio,
                 with_transition, transition_desc, list(ref_images or []),
                 content_mode)
    return True


def _touch(task: dict, stage: str, pct: int) -> None:
    task["stage"] = stage
    task["pct"] = int(pct)
    store.save(task)


def _analyze(cid: str, video: Path, url: str) -> None:
    t0 = time.time()
    task = store.load(cid) or store.new_task(cid)
    try:
        task["state"] = "analyzing"
        _touch(task, "probe", 5)

        def progress(stage: str, pct: int) -> None:
            _touch(task, stage, pct)

        rec = clone_pipeline.analyze(
            video, url=url, workdir=store.task_dir(cid), progress=progress
        )
        task["recipe"] = rec
        task["state"] = "analyzed"
        _touch(task, "done", 100)
        log.info("复刻分析完成 cid=%s 用时 %.1fs 镜头=%d",
                 cid, time.time() - t0, len(rec.get("shots") or []))
    except Exception as e:  # noqa: BLE001
        log.exception("复刻分析失败 cid=%s", cid)
        rec = error_report.dump(store.task_dir(cid), stage="analyze",
                                cid=cid, error=e)
        task["state"] = "failed"
        task["error"] = str(e)
        task["error_file"] = str(rec) if rec else ""
        task["stage"] = "failed"
        store.save(task)
    finally:
        _release(cid)


def _render(cid: str, rid: str, script: str | None, mask_bottom: bool,
            regen_shots: list[int] | None = None,
            regen_mode: str = "shots", regen_channel: str = "auto",
            edit_spec: dict | None = None, max_segments: int = 0,
            force: bool = False) -> None:
    t0 = time.time()
    task = store.load(cid)
    if not task or not task.get("recipe"):
        _release(cid)
        return
    rec = task["recipe"]
    item = _find_render(task, rid)
    if item is None:
        _release(cid)
        return
    workdir = store.render_dir(cid, rid)

    try:
        item["state"] = "rendering"
        item["pct"] = 5
        store.save(task)

        def progress(stage: str, pct: int) -> None:
            item["stage"] = stage
            item["pct"] = int(pct)
            store.save(task)

        res = clone_pipeline.render(
            store.source_path(cid), rec, script=script, workdir=workdir,
            script_lines=item.get("script_lines") or None,
            # 只重配这几行；None = 整片重配（老行为）
            dub_lines=item.get("dub_lines") or None,
            # 每行用哪个音色（行号 → 音色 ID）；空 = 全部用整片音色
            dub_voices=item.get("dub_voices") or None,
            # 方言代码（火山 explicit_dialect）；空 = 标准普通话
            tts_dialect=(item.get("tts_dialect") or "").strip(),
            mask_bottom=mask_bottom, progress=progress,
            regen_shots=regen_shots, regen_mode=regen_mode,
            regen_channel=regen_channel, cid=cid,
            regen_model=(item.get("regen_model") or "").strip(),
            subject_image=_subject_path(cid),
            subject_asset=(item.get("subject_asset") or "").strip(),
            edit_spec=item.get("edit") or edit_spec,
            refs=_refs(cid),
            pronounce=item.get("pronounce") or {},
            tts_voice=(item.get("tts_voice") or "").strip(),
            allow_stretch=bool(item.get("allow_stretch")),
            lang=(item.get("lang") or "").strip(),
            speech_rate=item.get("speech_rate"),
            max_segments=int(max_segments or 0),
            force=bool(force),
        )
        item["state"] = "done"
        item["pct"] = 100
        item["stage"] = "done"
        item["duration"] = res["duration"]
        item["segments"] = _slim(res["segments"])
        item["replaced_shots"] = res.get("replaced_shots", 0)
        item["regen_channel"] = res.get("regen_channel", "")
        item["regen_model"] = res.get("regen_model", "")
        # 配音侧实测：语速调了多少、估算多少、实际多少、atempo 用了多少
        item["voice_meta"] = res.get("voice_meta") or {}
        # 换画面怎么拆的请求：多少段、切点挪没挪、段间有没有尾帧衔接
        item["regen_meta"] = res.get("regen_meta") or {}
        # 🩸 只出了前几段（`max_segments`）：前端据此显示"这是片段、不是成片"，
        #   并给出「继续出全部」。不是失败，别让结果页报错。
        item["partial"] = bool(res.get("partial"))
        # 成片质量门（定格/音画时长差/总时长偏离），本地 ffmpeg 跑，零成本
        item["qc"] = res.get("qc") or {}
        # 身份核对（换脸到底换上了没有），本地 OpenCV 跑，零成本
        item["identity"] = res.get("identity") or {}
        store.save(task)
        log.info("复刻出片完成 cid=%s rid=%s 用时 %.1fs 时长 %.2fs",
                 cid, rid, time.time() - t0, res["duration"] or 0)
    except Exception as e:  # noqa: BLE001
        log.exception("复刻出片失败 cid=%s rid=%s", cid, rid)
        # 🩸 **不截断**：以前是 str(e)[:400]，正好把「火山错误码 / request id /
        # 下一步点哪里」切掉，界面上只剩半句，只能回头来问（2026-10-23 主人：
        # 「把报错数据写清楚！不然老是来来回回查」）。
        # 完整记录另存一个 json：段区间、模型、参考视频形式、素材库结果、
        # 原始响应、traceback 全在里面，一次看全。
        rec = error_report.dump(workdir, stage="render", cid=cid, rid=rid, error=e)
        item["state"] = "failed"
        item["error"] = str(e)
        item["error_file"] = str(rec) if rec else ""
        item["stage"] = "failed"
        store.save(task)
    finally:
        # 出片终态（成功或失败）都回收这一单的素材组：额度是 50 素材 + 50 组、
        # 全账号共享，不回收只够跑一两单。回收只删火山侧，本地登记表留痕。
        try:
            from app.services import ark_ingest

            if ark_ingest.available():
                ark_ingest.recycle_render(cid)
        except Exception as e:  # noqa: BLE001
            log.warning("素材组回收失败（不影响出片）：%s", e)
        _release(cid)


def _extend(cid: str, rid: str, base_render_id: str, direction: str,
            seconds: int, content: str, model: str, resolution: str,
            with_audio: bool | None, with_transition: bool = False,
            transition_desc: str = "", ref_slots: list[str] | None = None,
            content_mode: str = "") -> None:
    """延长：拿一条已有的片子，向前/向后接一段。

    产物写进新的一单（rid），所以延长出来的版本和原版**并存**，
    可以继续在结果页上看、下载、再延。
    """
    t0 = time.time()
    task = store.load(cid)
    if not task:
        _release(cid)
        return
    item = _find_render(task, rid)
    if item is None:
        _release(cid)
        return

    try:
        from app.services import extend as extend_mod

        base = (store.render_dir(cid, base_render_id) / "out.mp4"
                if base_render_id else store.source_path(cid))
        if not base.exists():
            raise RuntimeError("要延长的视频不存在（可能已被清理）")

        # 没点名型号 → 用**默认通道**的默认型号（读哪个配置字段由适配器声明）
        from app.services import models as _models

        model_id = (model or "").strip()
        if not model_id:
            _ad0 = _models.adapter_for(channel="")
            model_id = (getattr(settings, _ad0.caps.default_model_setting, "")
                        or _ad0.model_id)
        info = scene.probe(base)
        # 清晰度跟着待延长视频走，但收口到该型号真正收的档位
        # （2.0 极速 / Mini 最高 720p，原片 1080p 直接送会被 400）
        resolution = extend_mod.pick_resolution(
            model_id, int(info.get("width") or 0), int(info.get("height") or 0),
            resolution)
        audio = bool(info.get("has_audio")) if with_audio is None \
            else bool(with_audio)

        item["state"] = "rendering"
        item["pct"] = 5
        store.save(task)

        def progress(stage: str, pct: int) -> None:
            item["stage"] = stage
            item["pct"] = int(pct)
            store.save(task)

        # 🩸 参考图按**请求里给的顺序**取（第 N 张 = 提示词的 `@图片N`），
        #   不重排、不去重。槽位名不认识的、文件不在的直接报错 ——
        #   静默跳过会让用户写的 `@图片2` 指向别的图。
        refs: list[Path] = []
        for slot in (ref_slots or []):
            p = store.ref_path(cid, slot)
            if not p.exists():
                raise RuntimeError(f"参考素材「{slot}」没有上传，不能带进延长")
            refs.append(p)

        res = extend_mod.run(
            cid, rid, direction=direction, seconds=seconds, content=content,
            base=base, model=model_id, resolution=resolution,
            with_audio=audio, with_transition=with_transition,
            transition_desc=transition_desc, ref_images=refs,
            content_mode=content_mode, progress=progress,
        )
        item["state"] = "done"
        item["pct"] = 100
        item["stage"] = "done"
        item["duration"] = res["duration"]
        # 合并而不是覆盖：请求侧的方向/内容/基于哪一版要留着给前端显示
        item["extend"] = {**(item.get("extend") or {}), **res["extend"]}
        # 🩸 以前写死 "volc"：H3 的延长版本也会被记成火山 → 前端"再生成"按错通道走
        item["regen_channel"] = _models.adapter_for(model=model_id).caps.family
        item["regen_model"] = model_id
        store.save(task)
        log.info("延长完成 cid=%s rid=%s 方向=%s 用时 %.1fs 总时长 %.2fs",
                 cid, rid, direction, time.time() - t0, res["duration"] or 0)
    except Exception as e:  # noqa: BLE001
        log.exception("延长失败 cid=%s rid=%s", cid, rid)
        rec = error_report.dump(store.render_dir(cid, rid), stage="extend",
                                cid=cid, rid=rid, error=e)
        item["state"] = "failed"
        item["error"] = str(e)
        item["error_file"] = str(rec) if rec else ""
        item["stage"] = "failed"
        store.save(task)
    finally:
        _release(cid)


def _subject_path(cid: str) -> Path | None:
    """换人物用的参考图，没传就是 None（走纯文字换主体）。"""
    p = store.subject_path(cid)
    return p if p.exists() else None


def _refs(cid: str) -> dict:
    """各槽位实际存在的参考图。缺的槽位不传，提示词里也不会带它的编号。"""
    return {
        slot: store.ref_path(cid, slot)
        for slot in store.REF_SLOTS
        if store.ref_path(cid, slot).exists()
    }


def _slim(segs: list[dict]) -> list[dict]:
    """逐句文案段只留前端要用的字段（chars 逐字时间不下发，用不上还很大）。"""
    return [
        {"start": s["start"], "end": s["end"], "text": s["text"]}
        for s in segs
    ]


def _find_render(task: dict, rid: str) -> dict | None:
    for r in task.get("renders") or []:
        if r.get("id") == rid:
            return r
    return None


# ---------------------------------------------------------------------------


def recover() -> int:
    """进程重启后，把卡在 running 的任务标失败 —— 子进程已经没了，不可能自己好。"""
    if not settings.clone_dir.exists():
        return 0
    fixed = 0
    for d in settings.clone_dir.iterdir():
        if not d.is_dir() or not store.valid(d.name):
            continue
        task = store.load(d.name)
        if not task:
            continue
        changed = False
        if task.get("state") in ("queued", "analyzing"):
            task["state"] = "failed"
            task["error"] = "服务重启，分析中断，请重试"
            task["stage"] = "failed"
            changed = True
        for r in task.get("renders") or []:
            if r.get("state") in ("queued", "rendering"):
                r["state"] = "failed"
                r["error"] = "服务重启，出片中断，请重试"
                r["stage"] = "failed"
                changed = True
        if changed:
            store.save(task)
            fixed += 1
    return fixed
