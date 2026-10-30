"""临时任务存储：token → 目录（meta.json / video / audio）。

设计要点：
- 解析成功即落 meta.json，文件按需生成（抽音频较慢，不阻塞解析响应）
- 所有文件统一放 temp_dir，超时自动清理
"""
from __future__ import annotations

import json
import logging
import shutil
import time
import uuid
from dataclasses import asdict
from pathlib import Path

from app.core.config import settings
from app.parsers.base import MediaInfo

log = logging.getLogger(__name__)


def new_token() -> str:
    return uuid.uuid4().hex


def task_dir(token: str) -> Path:
    return settings.temp_dir / token


def save_meta(token: str, info: MediaInfo) -> Path:
    d = task_dir(token)
    d.mkdir(parents=True, exist_ok=True)
    p = d / "meta.json"
    data = asdict(info)
    data["is_video"] = info.is_video  # asdict 不取 property，前端要靠它区分视频/图集
    data["created_at"] = time.time()
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def load_meta(token: str) -> dict | None:
    # token 只允许十六进制，防止路径穿越
    if not token or not all(c in "0123456789abcdef" for c in token.lower()):
        return None
    p = task_dir(token) / "meta.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def video_path(token: str) -> Path:
    return task_dir(token) / "video.mp4"


def audio_path(token: str) -> Path:
    return task_dir(token) / "audio.m4a"


def cover_path(token: str) -> Path:
    return task_dir(token) / "cover.img"


def image_path(token: str, idx: int) -> Path:
    return task_dir(token) / f"image_{idx}.img"


def cleanup_expired() -> int:
    """删除超过 TTL 的任务目录，返回删除数。"""
    if not settings.temp_dir.exists():
        return 0
    now = time.time()
    removed = 0
    for d in settings.temp_dir.iterdir():
        if not d.is_dir():
            continue
        try:
            if now - d.stat().st_mtime > settings.temp_ttl:
                shutil.rmtree(d, ignore_errors=True)
                removed += 1
        except Exception:  # noqa: BLE001
            continue
    return removed
