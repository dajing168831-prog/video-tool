"""镜头重绘：原片某一镜 → 新画面。

两步，缺一不可：
  1) 图生图：抽这一镜的中间帧当参考，让模型在**保持构图、景别、光线**的前提下
     换掉画面主体。直接文生图会得到一张和原片毫无关系的图，接回去就是跳帧。
  2) 图生视频：把新静帧当首帧，生成和原镜头等长的片段。

成本与风险：
  - 每个镜头两次调用（一次图、一次视频），按镜头计费
  - 有人物大动作的镜头不适合这种方式（首帧定死，动作出不来），
    这类镜头应该保留原片 —— 所以默认只替换一部分
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import shutil
from pathlib import Path

from app.services import ark, scene

log = logging.getLogger(__name__)


def _ratio(w: int, h: int) -> str:
    if not w or not h:
        return "16:9"
    r = w / h
    for label, v in (("16:9", 16 / 9), ("9:16", 9 / 16), ("1:1", 1.0),
                     ("3:4", 3 / 4), ("4:3", 4 / 3)):
        if abs(r - v) < 0.03:
            return label
    return "16:9" if r > 1 else "9:16"


def _manifest(workdir: Path) -> dict:
    p = workdir / "regen" / "manifest.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save_manifest(workdir: Path, data: dict) -> None:
    p = workdir / "regen" / "manifest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def _cache_get(cache_dir: Path | None, key: str, dest: Path) -> bool:
    """任务级缓存命中就把文件复制过来。缓存坏了只当没命中，不影响出片。"""
    if cache_dir is None:
        return False
    try:
        p = Path(cache_dir) / (hashlib.sha1(key.encode("utf-8")).hexdigest()[:16] + ".mp4")
        if p.exists() and p.stat().st_size > 1024:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, dest)
            return True
    except Exception as e:  # noqa: BLE001
        log.warning("读静帧缓存失败（按未命中继续）：%s", e)
    return False


def _cache_put(cache_dir: Path | None, key: str, src: Path) -> None:
    if cache_dir is None:
        return
    try:
        p = Path(cache_dir) / (hashlib.sha1(key.encode("utf-8")).hexdigest()[:16] + ".mp4")
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(f".{p.name}.{os.getpid()}.tmp")
        shutil.copyfile(src, tmp)
        # 原子落位：exists() 就代表写完了，并发时不会读到半个文件
        os.replace(tmp, p)
    except Exception as e:  # noqa: BLE001
        log.warning("写静帧缓存失败（不影响这次出片）：%s", e)


def seek_time(start: float | None, end: float | None,
              total: float = 0.0) -> float:
    """这一镜该在源片的第几秒抽帧 —— **一定落在片长内**。

    🩸 2026-10-25/26 两单出片失败：配方里的镜头表带着越界条目
    （`start 15.787 / end 23.994`、`start 23.994 / end 15.117`），
    按中点 19.89s 去抽一个只有 15.12s 的片子 —— ffmpeg 一帧都不出，
    `extract_frame` 抛错，整单作废。成因见 `scene._frame_times` 的注释。
    这里只做**兜底**：正常配方本来就在范围内，触发就说明上游有病，日志会喊。
    """
    s = float(start or 0.0)
    e = float(end or 0.0)
    t = s + max(0.5, e - s) / 2.0
    # 余量 0.2s：实测 `total - 0.05` 仍然取不到帧（末帧 PTS 15.0667 < 片长 15.117，
    # 按 15.067 去 seek 一帧都没有），留出一帧以上的余量才稳。
    if total > 0 and t > total - 0.2:
        return max(0.0, total - 0.2)
    return t


def regen_shots(
    video: Path,
    recipe: dict,
    picks: list[int],
    *,
    prompt: str,
    workdir: Path,
    progress=None,
    cache_dir: Path | None = None,
    ref_images: list[Path] | None = None,
    video_prompt: str | None = None,
    lock_tail: bool = False,
) -> dict[int, Path]:
    """按镜头序号重画。返回 {镜头序号: 片段路径}。

    同一个提示词重复跑不会再花钱：产物按 镜头序号 + 提示词哈希 + 画幅/时长 缓存。
    `cache_dir` 由调用方给**任务级**目录（`data/clone/<cid>/cache/still/`）。
    🩸 出片目录里的 manifest 每次点「出片」都会新建，跨次点击永远命中不了 ——
    缓存必须挂在任务下，否则界面上那句"重跑不重复扣费"就是假话。
    🩸 2026-10-24 曾被误删过一次（以为它导致"重跑没变化"）。真实原因是提示词
    没改：键里就有提示词哈希，提示词一改必然重新生成。已恢复。

    `lock_tail` = 尾帧锁定（B6）：每镜额外抽**本镜末帧**、同一提示词重绘一张，
    作为「图生视频-首尾帧」的尾帧（`volc-api:221-243`），让这一镜的出口
    接回原片那一帧 —— 否则结尾由模型自由发挥，接缝跳变。
    代价：**每镜多一次图生图**（尾帧也要重绘，直接拿原片末帧反而把画面拉回原片风格）。
    """
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("要重绘就必须给提示词：说明画面主体换成什么")
    if not picks:
        return {}

    src = recipe["source"]
    w = int(src.get("width") or 1080)
    h = int(src.get("height") or 1920)
    ratio = _ratio(w, h)
    shots = {int(s["i"]): s for s in recipe.get("shots") or []}

    regen_dir = workdir / "regen"
    (regen_dir / "frames").mkdir(parents=True, exist_ok=True)
    (regen_dir / "images").mkdir(parents=True, exist_ok=True)
    (regen_dir / "clips").mkdir(parents=True, exist_ok=True)
    manifest = _manifest(workdir)
    # 🩸 缓存键必须带上参考图：换了人物图但提示词没变（同一个「图二」），
    # 只按 prompt 做键会把旧脸的结果拿回来。
    refs = [Path(x) for x in (ref_images or [])]
    refsig = "|".join(f"{p.name}:{p.stat().st_size}:{p.stat().st_mtime_ns}"
                      for p in refs if p.exists())
    phash = hashlib.sha256((prompt + "#" + refsig).encode("utf-8")).hexdigest()[:12]
    vprompt = (video_prompt or prompt).strip()

    out: dict[int, Path] = {}
    # 🩸 兜底：镜头表可能来自**修好之前**生成的配方（旧任务重跑就是这种），
    #   里面可能带越界/倒挂的 start·end（成因见 `scene._frame_times` 的注释）。
    #   按那个时间去抽帧必然一帧都抽不到，会把整单带崩 —— 这里把取样时间夹进片长，
    #   并大声记一条日志。新分析出来的镜头表都在范围内，这条不会触发。
    vid_total = 0.0
    try:
        vid_total = float(scene.probe(video).get("duration") or 0.0)
    except Exception as e:  # noqa: BLE001
        log.warning("读不到源片时长，跳过越界保护：%s", e)

    def _seek(s: dict) -> float:
        t = seek_time(s.get("start"), s.get("end"), vid_total)
        if vid_total > 0 and t >= vid_total - 0.05:
            log.warning("镜头 %s 的取样时间超出片长 %.3fs，夹到末帧", s.get("i"),
                        vid_total)
        return t

    total = len(picks)
    for n, i in enumerate(picks, 1):
        s = shots.get(i)
        if not s:
            log.warning("镜头 %s 不在配方里，跳过", i)
            continue
        dur = max(0.5, float(s["end"]) - float(s["start"]))
        clip = regen_dir / "clips" / f"shot_{i:03d}.mp4"
        # 🩸 开了又关必须换键：不换就会命中上一次（带尾帧）的结果，用户以为开关没生效。
        # 默认关时键**与改动前逐字一致**，历史缓存照样命中。
        key = f"{i}:{phash}:{w}x{h}:{dur:.2f}" + ("|lt" if lock_tail else "")

        rec = manifest.get(str(i)) or {}
        if rec.get("key") == key and clip.exists():
            log.info("镜头 %s 命中本目录缓存，不重复生成", i)
            out[i] = clip
            continue
        if _cache_get(cache_dir, key, clip):
            log.info("镜头 %s 命中任务缓存（同提示词重跑），不重复扣费", i)
            manifest[str(i)] = {"key": key, "prompt": prompt, "dur": dur}
            _save_manifest(workdir, manifest)
            out[i] = clip
            continue

        _p(progress, f"抽帧 {n}/{total}", 60)
        frame = regen_dir / "frames" / f"shot_{i:03d}.jpg"
        scene.extract_frame(video, _seek(s), frame, width=1280)

        _p(progress, f"重绘 {n}/{total}", 65)
        img = ark.generate_image(
            prompt, ref_image=frame, ref_images=refs,
            out=regen_dir / "images" / f"shot_{i:03d}.jpg",
        )

        tail_img = None
        if lock_tail:
            # 🩸 抽 end - 0.05 不是 end：切点那一帧正好是**下一镜的第一帧**，
            # 抽准了就把别人的画面当了这镜的尾帧。
            tail_frame = regen_dir / "frames" / f"shot_{i:03d}_tail.jpg"
            scene.extract_frame(video, float(s["end"]) - 0.05, tail_frame, width=1280)
            # 尾帧也必须重绘：直接拿原片末帧当尾帧，会把这一镜往原片风格拉回去。
            tail_img = ark.generate_image(
                prompt, ref_image=tail_frame, ref_images=refs,
                out=regen_dir / "images" / f"shot_{i:03d}_tail.jpg",
            )

        _p(progress, f"生成片段 {n}/{total}", 70)
        # 视频时长按整数秒；1.0-pro-fast 下限是 2 秒，多余的在拼接时裁掉
        vdur = max(2, min(10, int(math.ceil(dur))))
        ark.generate_video(vprompt, first_frame=img, last_frame=tail_img, out=clip,
                           duration=vdur, ratio=ratio, resolution="720p")

        manifest[str(i)] = {"key": key, "prompt": prompt,
                            "video_prompt": vprompt if vprompt != prompt else "",
                            "dur": dur}
        _save_manifest(workdir, manifest)
        _cache_put(cache_dir, key, clip)
        out[i] = clip

    _p(progress, "重绘完成", 75)
    return out


def _p(cb, stage: str, pct: int) -> None:
    if cb:
        try:
            cb(stage, pct)
        except Exception:  # noqa: BLE001
            pass
