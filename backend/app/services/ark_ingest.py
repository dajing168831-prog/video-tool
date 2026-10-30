"""把素材送进火山素材库换 `asset://`，并管住 50 素材 / 50 组的额度。

分工：
    ark_assets   —— 只会"签名 + 调接口"（一个动作一个函数）
    ark_ingest   —— 决定**哪些要入库**、**入到哪个组**、**什么时候回收**
    face_check   —— 只要"有没有脸"

三条判据（都是被 400 教出来的）：
    1. 图：检出脸才入库；门店/场景/道具直接传 base64，不占额度
    2. 视频：不判脸、一律入库 —— 判脸要下载整段视频，太慢，而且这类视频几乎必然含真人
    3. 额度不够就先按 LRU 腾地方；出片终态后把这一单的组删掉

回收只删火山侧（DeleteAssetGroup 连带素材），本地登记表保留记录标 recycled，可追溯。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from pathlib import Path

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]          # backend/
REG_PATH = ROOT / "data" / "ark_assets.json"
_lock = threading.RLock()
_STALE_CHECK_EVERY = 3600.0                          # recycle_stale 的节流（秒）
_last_stale_check = 0.0


# ---------------------------------------------------------------------------
# 本地登记表


def _load() -> dict:
    try:
        d = json.loads(REG_PATH.read_text(encoding="utf-8"))
        if isinstance(d, dict):
            d.setdefault("groups", {})
            d.setdefault("assets", {})
            d.setdefault("last_stale_check", 0.0)
            return d
    except Exception:  # noqa: BLE001
        pass
    return {"groups": {}, "assets": {}, "last_stale_check": 0.0}


def _save(d: dict) -> None:
    REG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = REG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, REG_PATH)


def _sha1_file(path: Path) -> str:
    h = hashlib.sha1()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def available() -> bool:
    from app.services import ark_assets

    return ark_assets.available()


def active_counts(d: dict) -> tuple[int, int]:
    """(在用素材数, 在用组数)。"""
    groups = [g for g in d.get("groups", {}).values() if not g.get("recycled")]
    assets = [a for a in d.get("assets", {}).values() if not a.get("recycled")]
    return len(assets), len(groups)


# ---------------------------------------------------------------------------
# 回收


def _drop_group(d: dict, gid: str, why: str) -> int:
    """删火山侧的组（连带素材），本地标 recycled。返回本次释放的素材数。"""
    from app.services import ark_assets

    g = d["groups"].get(gid) or {}
    if g.get("recycled"):
        return 0
    try:
        ark_assets.delete_group(gid)
    except Exception as e:  # noqa: BLE001
        log.warning("删素材组 %s 失败（%s）：%s", gid, why, e)
        return 0
    g["recycled"] = True
    g["recycled_at"] = time.time()
    g["recycled_why"] = why
    n = 0
    for aid, a in d["assets"].items():
        if a.get("group") == gid and not a.get("recycled"):
            a["recycled"] = True
            n += 1
    log.info("素材库回收组 %s（%s，%d 个素材）", gid, why, n)
    return n


def _make_room(d: dict, need: int, cid: str) -> None:
    """额度不够时按 LRU 腾位置（绝不动本单自己的组）。"""
    from app.core.config import settings

    cap = max(1, int(settings.ark_asset_max))
    while True:
        assets, groups = active_counts(d)
        if assets + need <= cap and groups + 1 <= cap:
            return
        cand = [(g.get("last_used") or g.get("created") or 0, gid)
                for gid, g in d["groups"].items()
                if not g.get("recycled") and g.get("cid") != cid]
        if not cand:
            return
        cand.sort()
        _drop_group(d, cand[0][1], "LRU 腾位置")
        _save(d)


def recycle_stale(force: bool = False) -> int:
    """出片前顺手回收长期没用的组（1 小时节流）。"""
    global _last_stale_check
    from app.core.config import settings

    now = time.time()
    if not force and now - _last_stale_check < _STALE_CHECK_EVERY:
        return 0
    _last_stale_check = now
    with _lock:
        d = _load()
        cutoff = now - max(1.0, float(settings.ark_asset_stale_h)) * 3600
        n = 0
        for gid, g in list(d["groups"].items()):
            if g.get("recycled"):
                continue
            if (g.get("last_used") or g.get("created") or 0) < cutoff:
                n += _drop_group(d, gid, "超过闲置时限")
        d["last_stale_check"] = now
        _save(d)
        return n


def recycle_render(cid: str) -> int:
    """出片终态后：把这一单建的组全删掉（火山侧），本地标 recycled。"""
    with _lock:
        d = _load()
        n = 0
        for gid, g in d["groups"].items():
            if not g.get("recycled") and g.get("cid") == cid:
                n += _drop_group(d, gid, "出片结束")
        _save(d)
        return n


# ---------------------------------------------------------------------------
# 入库


def _group_for(d: dict, cid: str) -> str:
    from app.services import ark_assets

    for gid, g in d["groups"].items():
        if g.get("cid") == cid and not g.get("recycled"):
            g["last_used"] = time.time()
            return gid
    gid = ark_assets.create_group(f"clone-{cid[:8]}-{int(time.time())}")
    d["groups"][gid] = {"cid": cid, "created": time.time(),
                        "last_used": time.time(), "recycled": False,
                        "assets": []}
    _save(d)
    log.info("素材库新建组 %s（cid=%s）", gid, cid[:8])
    return gid


def _find_cached(d: dict, cid: str, sha: str, kind: str) -> str:
    for aid, a in d["assets"].items():
        if (not a.get("recycled") and a.get("cid") == cid
                and a.get("sha1") == sha and a.get("kind") == kind
                and a.get("status") == "Active"):
            a["last_used"] = time.time()
            return aid
    return ""


def _ingest(path: Path, cid: str, kind: str, url: str = "",
            *, report: dict | None = None) -> str:
    """拿公网 URL（没给就先传 OSS）→ CreateAsset → 等 Active → asset://<id>。

    🩸 2026-10-25：失败原因必须回传给调用方（`report`）。以前这里 `return ""`
    就把异常吞了，上游 `prepare_video` 的 report 是空的 → error.json 写成
    「素材库=ok（已入素材库或不适用）」**假绿**：实测 `861efd72` 那条视频入库
    明明被审核拒了（`InputVideoSensitiveContentDetected`），证据文件却说 ok，
    害得只能翻日志才看见真相。
    """
    from app.services import ark_assets, oss

    def _why(msg: str) -> str:
        if report is not None:
            report["failed"] = msg
        return ""

    path = Path(path)
    if not path.exists():
        return _why("文件不存在")
    sha = _sha1_file(path)
    with _lock:
        d = _load()
        cached = _find_cached(d, cid, sha, kind)
        if cached:
            _save(d)
            return f"asset://{cached}"

    url = url or oss.upload(path)
    if not url:
        log.warning("入库前上传 OSS 失败：%s", path.name)
        return _why("上传 OSS 失败，拿不到公网 URL")

    with _lock:
        d = _load()
        _make_room(d, 1, cid)
        gid = _group_for(d, cid)
        _save(d)

    try:
        aid = ark_assets.create_asset(gid, url, kind=kind, name=path.stem)
        ark_assets.wait_active(aid)
    except Exception as e:  # noqa: BLE001
        log.warning("素材入库失败（%s）：%s", path.name, e)
        return _why(str(e))

    with _lock:
        d = _load()
        d["assets"][aid] = {
            "cid": cid, "group": gid, "kind": kind, "sha1": sha,
            "url": url, "status": "Active", "recycled": False,
            "created": time.time(), "last_used": time.time(),
        }
        g = d["groups"].get(gid)
        if g is not None:
            g.setdefault("assets", []).append(aid)
            g["last_used"] = time.time()
        _save(d)
    log.info("素材就绪 %s（%s）", aid, path.name)
    return f"asset://{aid}"


def _video_fits(path: Path) -> tuple[bool, str]:
    """入库前的时长闸门。

    时长区间 **1.8–30.2 秒** 是 2026-10-21 用火山自己的接口逐档实测出来的
    （1s 回 `DurationTooShort`、31s 回 `DurationTooLong`、15/16/20/30s 全 Active）。
    🩸 网上流传的「2–15 秒」出自第三方镜像文档，**是错的**，别拿它当官方数据。

    大小/分辨率/帧率那几条同样出自第三方镜像，**没在官方文档核实过**，
    而且实测 720×1280@30 以外也没撞到过 → 这里只记日志、不拦，
    免得用一条查无实据的规则把正常素材挡在门外。真要拦也是火山自己报错。
    """
    from app.services import media

    try:
        size = path.stat().st_size
    except OSError:
        return False, "读不到文件"
    if size > 50 * 1024 * 1024:
        log.info("视频 %.1fMB 偏大（镜像文档说上限 50MB，未核实）",
                 size / 1048576)

    dur = media.probe_duration(path)
    if dur is not None and not (1.7 <= dur <= 30.3):
        return False, f"{dur:.1f}s 超出实测区间 1.8–30.2s"
    return True, ""


def prepare_video(path: Path, cid: str, url: str = "",
                  *, report: dict | None = None) -> str:
    """参考视频：不判脸、直接入库。失败返回 ""（调用方退回公网 URL）。

    url 由调用方给的话就不再传一次 OSS —— 视频动辄二三十 MB，
    同一段传两遍纯属白等。

    `report` 由调用方传一个空 dict 进来：失败时把**原因**填进去，供上层落盘。
    🩸 2026-10-23：素材库的拒绝理由（比如版权 PolicyViolation）以前只写进一行
    log.warning，出片失败后要翻日志才知道 —— 现在跟着 error.json 一起走。
    """
    if not available():
        if report is not None:
            report["skip"] = "素材库未配置（AK/SK 缺失）"
        return ""
    path = Path(path)
    if not path.exists():
        if report is not None:
            report["skip"] = "文件不存在"
        return ""
    ok, why = _video_fits(path)
    if not ok:
        log.info("视频不入库（%s）：%s —— 退回公网 URL", path.name, why)
        if report is not None:
            report["skip"] = why
        return ""
    try:
        recycle_stale()
        return _ingest(path, cid, "video", url=url, report=report)
    except Exception as e:  # noqa: BLE001
        log.warning("视频入库异常，退回 URL：%s", e)
        if report is not None:
            report["failed"] = str(e)
        return ""


def prepare_image(path: Path, cid: str) -> str:
    """参考图：检出脸才入库；没脸返回 ""（调用方直接传 base64，不占额度）。"""
    if not available():
        return ""
    from app.services import face_check

    try:
        if not face_check.has_face(path):
            return ""
    except Exception as e:  # noqa: BLE001
        log.warning("人脸判断失败，按有脸处理：%s", e)
    try:
        return _ingest(Path(path), cid, "image")
    except Exception as e:  # noqa: BLE001
        log.warning("图片入库异常，退回 base64：%s", e)
        return ""
