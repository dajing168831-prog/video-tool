"""H2 文件服务 —— 通用静态文件出口（防穿越 / Range / 流式 / 长缓存）。

出处：clipforge `src/app/api/files/[...path]/route.ts`、`src/app/api/output/[...path]/route.ts`、
`src/lib/http-range.ts`、`src/lib/file-response-stream.ts`（逐条对照）：
  · 防穿越：**先把每段 URL 解码，再拼、再 normalize，最后必须仍在根目录内**
    （`files/route.ts:25-32`）——只挡字面量 `..` 不够，`..%2f` 这类编码会在解码后变成真分隔符
  · Range：只认单区间三种写法 `bytes=start-end` / `bytes=start-` / `bytes=-suffix`；
    越界/倒序/零长 → 416 + `Content-Range: bytes */size`（`http-range.ts:11-52`）
  · 缓存：素材图/视频 `max-age=31536000`（一年，内容寻址式文件名），成片输出 `max-age=3600`
  · 流式：不整文件读进内存（`file-response-stream.ts`）

我们的差异（逐条说清）：
  1. **Range 由 Starlette 的 FileResponse 原生实现**（1.9：单区间 206、越界 416、多区间 multipart），
     所以这里不重写解析器 —— 只把「根目录校验」和「响应头」收成一个函数。
     🩸 与竞品一处行为差异：**多区间请求**竞品返回 416，Starlette 返回 `multipart/byteranges` 206。
     这是更完整的行为，不改成更差的那个。
  2. 路由收口成一条 `GET /drama/files/{kind}/{path:path}`，`kind` 走白名单映射到数据目录；
     竞品是 `/api/files`（uploads）与 `/api/output`（成片）两条。我们目录更多（图/片/BGM/素材/商品/长视频），
     用 kind 区分比复制六条路由好维护。
  3. `?download=1` 时加 `Content-Disposition: attachment`（竞品 `output/route.ts:57`）。
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote

#: 扩展名 → MIME（竞品两张表取并集，再补上我们真用到的类型）
MIME = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "webp": "image/webp", "gif": "image/gif", "bmp": "image/bmp",
    "mp4": "video/mp4", "webm": "video/webm", "mov": "video/quicktime",
    "mkv": "video/x-matroska", "m4v": "video/x-m4v", "mp3": "audio/mpeg",
    "wav": "audio/wav", "m4a": "audio/mp4", "aac": "audio/aac",
    "ogg": "audio/ogg", "json": "application/json; charset=utf-8",
    "srt": "text/plain; charset=utf-8", "vtt": "text/vtt; charset=utf-8",
    "ass": "text/plain; charset=utf-8", "txt": "text/plain; charset=utf-8",
}

CACHE_FOREVER = "public, max-age=31536000"
CACHE_SHORT = "public, max-age=3600"


class FileError(ValueError):
    """路径不合法 / 文件不存在（人话，API 层直接回）。"""


def mime_of(path: str | Path) -> str:
    ext = str(path).rsplit(".", 1)[-1].lower() if "." in str(path) else ""
    return MIME.get(ext, "application/octet-stream")


def safe_segments(raw: list[str]) -> list[str]:
    """先把每段解码，再挡掉解码后才现形的穿越写法（`files/route.ts:25-32`）。

    `path:path` 转换器拿到的是**未解码**的分段，所以 `..%2f..%2fetc` 进来还是一段；
    解码后它会变成 `../../etc`，带上了分隔符 —— 必须在这一步拦掉，
    不能等拼完再 `normalize`（那时已经多出层级了）。
    """
    out: list[str] = []
    for seg in raw:
        if not isinstance(seg, str) or not seg:
            raise FileError("非法路径")
        dec = unquote(seg)
        if not dec or dec in (".", "..") or "/" in dec or "\\" in dec:
            raise FileError("非法路径")
        if "\x00" in dec:
            raise FileError("非法路径")
        out.append(dec)
    return out


def resolve_under(root: Path, raw: list[str]) -> Path:
    """拼到根下并确认**仍在根内**；不存在/不是文件都按 404 处理（不泄露目录结构）。"""
    segs = safe_segments(raw)
    base = Path(root).resolve()
    p = (base.joinpath(*segs)).resolve()
    # `is_relative_to` 同时挡住符号链接指到根外的情况（resolve 之后比）
    if p != base and not p.is_relative_to(base):
        raise FileError("非法路径")
    if not p.exists() or not p.is_file():
        raise FileError("文件不存在")
    return p


def parse_range(raw: str | None, size: int):
    """竞品 `http-range.ts:11-52` 的等价实现（供纯逻辑探针验口径；路由仍用 Starlette）。

    返回 `None`（无 Range，回 200）/ `"unsatisfiable"`（回 416）/ `(start, end)` 闭区间。
    """
    if not raw:
        return None
    s = raw.strip()
    if not s.lower().startswith("bytes="):
        return "unsatisfiable"
    spec = s.split("=", 1)[1].strip()
    if "," in spec:
        return "unsatisfiable"
    if "-" not in spec:
        return "unsatisfiable"
    a, b = spec.split("-", 1)
    a, b = a.strip(), b.strip()
    if not a and not b:
        return "unsatisfiable"
    if size <= 0:
        return "unsatisfiable"
    if not a:
        try:
            n = int(b)
        except ValueError:
            return "unsatisfiable"
        if n <= 0:
            return "unsatisfiable"
        return (max(0, size - n), size - 1)
    try:
        start = int(a)
        end = int(b) if b else size - 1
    except ValueError:
        return "unsatisfiable"
    if start >= size or start > end:
        return "unsatisfiable"
    return (start, min(end, size - 1))
