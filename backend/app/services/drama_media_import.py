"""B6：导入自有视频（1GB / 2 小时）—— 流式落盘 + probe 校验 + 独立索引。

出处（竞品 `src/app/api/project/[id]/media/route.ts` + `src/lib/media-validate.ts`）：
  · `route.ts:22-31`  项目 ID 安全校验 + 五个常量（1GB / 2 小时 / 五种扩展名 → MIME）
  · `route.ts:91-105` 先看 `x-file-name`（URL 解码 + basename + 去反斜杠 + 截 240 字），
                      再按扩展名白名单判类型，`content-length` 声明超限直接 413
  · `route.ts:107-124` **流式**落盘，边写边计数（`Transform` guard）—— 声明长度不可信，
                      实收超 1GB 立刻中断（错误码 `IMPORT_TOO_LARGE`）
  · `route.ts:126-131` 写完真实校验（`validateOrDelete`），失败删文件报 422；
                      再查时长，超 2 小时删文件报 413
  · `media-validate.ts:29-45` 视频校验口径 = 宽高都 > 0 且时长 > 0（拒 0 字节 / 错误页 / 截断头）
  · `route.ts:135-145` 落库：原名 / 路径 / MIME / 字节数 / 时长(ms) / 宽高 / 有无音轨 / status

我们的差异（都与「不和素材库混」有关）：
  1. **独立索引 `data/drama/media/<pid>/index.json`**，不进素材库（能力表 B6 那行写的就是这条）。
     素材库是「能当某一镜画面 / 参考图」的小素材；这里是**长视频原料**，给后面的转写（B7）
     和按文字剪（B8）用，混在一起会让素材池被 1GB 文件撑爆。
  2. 时长我们存**秒**（`drama_compose.probe` 的既有口径），竞品存毫秒 —— 只是单位不同。
  3. `status` 先落 `uploaded`；B7 转写时才会变 `transcribing / ready / failed`。
"""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import unquote

from app.services import drama_compose

#: 单文件上限 1GB（`route.ts:23`）
MAX_IMPORT_BYTES = 1024 * 1024 * 1024
#: 单文件最长 2 小时（`route.ts:24`）
MAX_IMPORT_SECONDS = 2 * 60 * 60
#: 支持的扩展名 → 规范 MIME（`route.ts:25-31`，逐条照抄）
SUPPORTED_EXTENSIONS = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".m4v": "video/x-m4v",
}
#: 项目 ID 安全校验（`route.ts:22`）
_SAFE_PID = re.compile(r"^[a-zA-Z0-9_-]+$")

_LOCK = threading.Lock()
INDEX_NAME = "index.json"


class ImportError_(ValueError):
    """带 HTTP 语义的导入错误（`status` 供路由层直接用）。"""

    def __init__(self, message: str, status: int = 400, code: str = ""):
        super().__init__(message)
        self.status = status
        self.code = code


# ---------------------------------------------------------------- 路径 / 索引

def media_dir(base: Path, pid: str) -> Path:
    """`data/drama/media/<pid>/` —— 与素材库 `materials/<pid>/` 同构。"""
    if not _SAFE_PID.match(pid or ""):
        raise ImportError_("无效的项目ID", 400, "BAD_PID")
    return base / pid


def _index_path(base: Path, pid: str) -> Path:
    return media_dir(base, pid) / INDEX_NAME


def _read_index(base: Path, pid: str) -> list[dict]:
    p = _index_path(base, pid)
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text("utf-8") or "{}")
    except (OSError, ValueError):
        return []
    rows = data.get("sources") if isinstance(data, dict) else data
    return [r for r in (rows or []) if isinstance(r, dict) and r.get("id")]


def _write_index(base: Path, pid: str, rows: list[dict]) -> None:
    d = media_dir(base, pid)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / (INDEX_NAME + ".tmp")
    tmp.write_text(json.dumps({"sources": rows}, ensure_ascii=False, indent=1), "utf-8")
    tmp.replace(d / INDEX_NAME)


# ---------------------------------------------------------------- 文件名 / 类型

def safe_original_name(header: str | None) -> str:
    """`x-file-name` → 安全的原名（`route.ts:35-44`：URL 解码 + basename + 去反斜杠 + 截 240）。"""
    if not header:
        return "video.mp4"
    try:
        raw = unquote(header)
    except Exception:  # noqa: BLE001
        raw = header
    name = raw.replace("\\", "/").split("/")[-1].strip()
    return name[:240] or "video.mp4"


def canonical_mime(name: str) -> str:
    """扩展名白名单 → MIME；不支持抛 415（`route.ts:95-97`）。"""
    ext = Path(name).suffix.lower()
    mime = SUPPORTED_EXTENSIONS.get(ext)
    if not mime:
        raise ImportError_("仅支持 MP4、MOV、WebM、MKV、M4V", 415, "UNSUPPORTED_EXTENSION")
    return mime


def check_declared_size(declared: int | None) -> None:
    """`content-length` 声明超限直接拒（`route.ts:98-101`）"""
    if declared and declared > MAX_IMPORT_BYTES:
        raise ImportError_("文件不能超过 1GB", 413, "IMPORT_TOO_LARGE")


def stored_name(original: str) -> str:
    """落盘名：时间戳 + uuid，保留扩展名（`route.ts:109`）。"""
    ext = Path(original).suffix.lower()
    return f"{int(time.time() * 1000)}-{uuid.uuid4().hex}{ext}"


# ---------------------------------------------------------------- 校验

def probe_video(path: Path) -> dict:
    """时长 / 宽高 / 有无音轨（复用 `drama_compose.probe`，它的 0 值口径正好当失败判据）。"""
    info = drama_compose.probe(path)
    return {
        "duration": float(info.get("duration") or 0.0),
        "width": int(info.get("width") or 0),
        "height": int(info.get("height") or 0),
        "has_audio": bool(info.get("has_audio")),
    }


def validate_video(path: Path) -> dict:
    """真实解码校验 + 时长闸；不通过就删文件再抛（`media-validate.ts:29-45` + `route.ts:126-131`）。

    返回探测结果，避免调用方再探一次。
    """
    meta = probe_video(path)
    if meta["width"] <= 0 or meta["height"] <= 0 or meta["duration"] <= 0:
        path.unlink(missing_ok=True)
        raise ImportError_("视频无法解码或文件已损坏", 422, "INVALID_VIDEO")
    if meta["duration"] > MAX_IMPORT_SECONDS:
        path.unlink(missing_ok=True)
        raise ImportError_("单个视频最长支持 2 小时", 413, "IMPORT_TOO_LONG")
    return meta


# ---------------------------------------------------------------- 增删查

def list_sources(base: Path, pid: str) -> list[dict]:
    """按导入时间倒序（`route.ts:52` 的 `orderBy(desc(createdAt))`）。

    🩸 排序键必须是**毫秒**：竞品的 `createdAt` 是 timestamp，我们若只存「秒级字符串」，
    同一秒连导两条就会按插入顺序返回（新的一条排到后面）—— 实测踩到过。
    """
    rows = _read_index(base, pid)
    return sorted(rows, key=lambda r: (int(r.get("created_ms") or 0), str(r.get("created") or "")),
                  reverse=True)


_LAST_MS = 0


def _next_ms() -> int:
    """严格递增的毫秒时间戳。

    🩸 只用 `int(time.time()*1000)` 仍会撞：同一毫秒里连着加两条（探针、批量导入都会），
    排序键相同 → `sorted` 保持插入顺序 → 新的那条排到后面，列表就变成"旧的在前"。
    这里保证同进程内绝不重复（撞了就 +1ms），顺序才稳定。
    """
    global _LAST_MS
    ms = int(time.time() * 1000)
    _LAST_MS = ms if ms > _LAST_MS else _LAST_MS + 1
    return _LAST_MS


def add_source(base: Path, pid: str, *, original_name: str, file_name: str, mime: str,
               size_bytes: int, meta: dict) -> dict:
    """落一条索引（`route.ts:133-145`）。"""
    row = {
        "id": uuid.uuid4().hex,
        "original_name": original_name,
        "file": file_name,
        "mime": mime,
        "size_bytes": int(size_bytes),
        "duration": round(float(meta.get("duration") or 0), 3),
        "width": int(meta.get("width") or 0),
        "height": int(meta.get("height") or 0),
        "has_audio": bool(meta.get("has_audio")),
        "status": "uploaded",
        "created_ms": _next_ms(),
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with _LOCK:
        rows = _read_index(base, pid)
        rows.append(row)
        _write_index(base, pid, rows)
    return row


def update_source(base: Path, pid: str, mid: str, **fields) -> dict | None:
    """改一条索引的字段（转写状态/进度/摘要都走这里）。找不到返回 None。"""
    with _LOCK:
        rows = _read_index(base, pid)
        target = None
        for r in rows:
            if r.get("id") == mid:
                r.update(fields)
                target = dict(r)
                break
        if target is None:
            return None
        _write_index(base, pid, rows)
    return target


def find_source(base: Path, pid: str, mid: str) -> dict | None:
    return next((r for r in _read_index(base, pid) if r.get("id") == mid), None)


def delete_source(base: Path, pid: str, mid: str) -> dict | None:
    """删索引 + 删文件；返回被删的那条（不存在返回 None）。"""
    with _LOCK:
        rows = _read_index(base, pid)
        keep = [r for r in rows if r.get("id") != mid]
        if len(keep) == len(rows):
            return None
        gone = next(r for r in rows if r.get("id") == mid)
        _write_index(base, pid, keep)
    f = media_dir(base, pid) / str(gone.get("file") or "")
    if f.is_file():
        f.unlink(missing_ok=True)
    return gone


def source_file(base: Path, pid: str, mid: str) -> Path | None:
    row = find_source(base, pid, mid)
    if not row:
        return None
    p = media_dir(base, pid) / str(row.get("file") or "")
    return p if p.is_file() else None


def public_source(row: dict, pid: str) -> dict:
    """前端形态：加取文件的 url（`route.ts:66`）。"""
    out = dict(row)
    out["url"] = f"/api/drama/projects/{pid}/media/{row['id']}/file"
    return out
