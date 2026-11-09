"""本地素材库（B2）+ 视频/音频入池（B1）—— 项目自己的素材池，带出处与许可。

出处：竞品 `src/lib/material-library.ts:1-77`（类型 / 分类 / 标签 / 匹配打分）、
      `src/lib/local-material-library.ts:1-243`（落盘·去重·元数据·列表）、
      `src/app/api/project/[id]/materials/route.ts:1-244`（上传 / 列表 / 改元数据 / 报错口径）。

抄的规则（逐条有出处）：
  · 80MB 单文件上限 + 多文件合计也 ≤80MB（`material-library.ts:2`、`route.ts:174-178`）
  · 只收 mp4/webm/mov/m4v + jpg/jpeg/png/webp（`material-library.ts:3-5`）
  · **内容寻址**：sha256 当文件名，重复上传返回 `duplicate=true` 不重写（`local-material-library.ts:215-222`）
  · 落盘先写临时文件，**校验通过才发布**，半截文件永不进池（`:148-243`）
  · 校验用真实探测（尺寸 / 时长 / 编码），**扩展名与真实格式不一致就拒**（`:193-213`）
  · 元数据存同目录 sidecar JSON：原名 / 标签 / 宽高 / 时长（`:26-69`）
  · 标签 ≤12 个、每个 ≤32 字、去重（`material-library.ts:52-62`）
  · 显示名去路径 / 去控制字符、≤240 字（`material-library.ts:38-50`）
  · 列表按更新时间倒序（`local-material-library.ts:115-118`）
  · 尾帧 `*.last.jpg` 不算素材（`:33-39`）

我们的差异（都因为数据模型不同，不是放宽）：
  1. **素材池按项目隔离**，与竞品一致；池目录 `data/drama/materials/<pid>/`。
  2. 额外允许在元数据里写**出处/作者/许可**（`author/license/source_url/provider`）——
     竞品这些字段挂在 stock 资产行上；我们没有 stock 表，用户自己导的素材也要能申报许可，
     否则 B5 授权清单只剩「自有素材」一行，等于没用。
  3. 单文件上传（我们的前端一次一个），竞品支持 1–12 个批量；批量只是循环，行为一致。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from app.services import media

#: 单文件上限（`material-library.ts:2`）
MAX_BYTES = 80 * 1024 * 1024
#: 一次最多传几个（`route.ts:162-170`）
MAX_FILES = 12
#: 标签 / 名字上限（`material-library.ts:52-62`、`:38-50`）
MAX_TAGS = 12
MAX_TAG_LEN = 32
MAX_NAME_LEN = 240

VIDEO_EXT = {"mp4", "webm", "mov", "m4v"}
IMAGE_EXT = {"jpg", "jpeg", "png", "webp"}
ACCEPT = ".mp4,.webm,.mov,.m4v,.jpg,.jpeg,.png,.webp"

#: sidecar 元数据后缀（竞品用 `.clipforge.json`；我们用中性名，不挂别人品牌）
META_SUFFIX = ".meta.json"
#: 名字里不许出现路径分隔与控制字符（`local-material-library.ts:27`）
_SAFE_NAME = re.compile(r"^[^/\\\x00-\x1f]+$")
#: 尾帧产物不算素材（`:33-39`）
_TAIL_FRAME = re.compile(r"\.(mp4|webm|mov|m4v)\.last\.jpg$", re.I)


class MaterialError(ValueError):
    """带错误码的素材错误 —— 路由按码翻成人话（口径见 `route.ts:39-102`）。"""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def extension(name: str) -> str:
    """取扩展名（小写、不带点）。`materialExtension`（`material-library.ts:21-25`）"""
    base = re.split(r"[\\/]", str(name or ""))[-1]
    return base.rsplit(".", 1)[-1].lower() if "." in base else ""


def classify(name: str) -> str | None:
    """视频 / 图片 / 不收（`material-library.ts:27-33`）"""
    ext = extension(name)
    if ext in VIDEO_EXT:
        return "video"
    if ext in IMAGE_EXT:
        return "image"
    return None


def display_name(value: str) -> str:
    """去路径 / 去控制字符 / 掐到 240 字（`material-library.ts:38-50`）"""
    base = re.split(r"[\\/]", str(value or ""))[-1]
    base = re.sub(r"[\x00-\x1f\x7f]", "", base).strip()
    return base[:MAX_NAME_LEN]


def clean_tags(value) -> list[str]:
    """标签清洗：≤12 个、每个 ≤32 字、去重保序（`material-library.ts:52-62`）"""
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_TAGS:
        raise MaterialError("INVALID_TAGS")
    out: list[str] = []
    for tag in value:
        if not isinstance(tag, str) or len(tag.strip()) > MAX_TAG_LEN:
            raise MaterialError("INVALID_TAGS")
        t = tag.strip()
        if t and t not in out:
            out.append(t)
    return out


def is_material_name(name: str) -> bool:
    """池里哪些文件算素材（`local-material-library.ts:33-39`）"""
    return bool(_SAFE_NAME.match(name or "")) and bool(classify(name)) and not _TAIL_FRAME.search(name)


# ---------------------------------------------------------------- 探测 / 校验

def _probe(path: Path) -> dict:
    """ffprobe 读宽高 / 时长 / 容器 / 视频编码；读不出返回 {}。"""
    exe = media.ffprobe_path()
    if not exe:
        # 没有 ffprobe 时不假装校验过 —— 由调用方按「探测不可用」处理
        return {}
    try:
        out = subprocess.run(
            [exe, "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", str(path)],
            capture_output=True, timeout=30,
        )
        if out.returncode != 0:
            return {}
        data = json.loads(out.stdout.decode("utf-8", "replace") or "{}")
    except Exception:
        return {}
    streams = data.get("streams") or []
    fmt = data.get("format") or {}
    v = next((s for s in streams if s.get("codec_type") == "video"), {})
    width = int(v.get("width") or 0)
    height = int(v.get("height") or 0)
    duration = 0.0
    for raw in (fmt.get("duration"), v.get("duration")):
        try:
            duration = float(raw)
            break
        except (TypeError, ValueError):
            continue
    return {
        "width": width,
        "height": height,
        "duration": duration,
        "format_name": str(fmt.get("format_name") or ""),
        "video_codec": str(v.get("codec_name") or ""),
    }


def _validate(ext: str, media_type: str, meta: dict) -> None:
    """真实格式必须与扩展名一致（`local-material-library.ts:200-213`）。"""
    if not meta:
        raise MaterialError("INVALID_MATERIAL")
    if not (meta["width"] > 0 and meta["height"] > 0):
        raise MaterialError("INVALID_MATERIAL")
    if media_type == "video" and not (meta["duration"] > 0):
        raise MaterialError("INVALID_MATERIAL")
    if media_type == "image":
        want = {"jpg": "mjpeg", "jpeg": "mjpeg", "png": "png", "webp": "webp"}.get(ext)
        if want and meta["video_codec"] != want:
            raise MaterialError("INVALID_MATERIAL")
    else:
        want = "webm" if ext == "webm" else "mov"
        if want not in [x for x in meta["format_name"].split(",") if x]:
            raise MaterialError("INVALID_MATERIAL")


# ---------------------------------------------------------------- 元数据

def _meta_path(d: Path, name: str) -> Path:
    return d / (name + META_SUFFIX)


def read_meta(d: Path, name: str) -> dict:
    """读 sidecar；不可信的一律当空（`local-material-library.ts:40-69`）。"""
    p = _meta_path(d, name)
    try:
        if not p.is_file() or p.stat().st_size > 16 * 1024:
            return {}
        body = json.loads(p.read_text("utf-8"))
    except Exception:
        return {}
    if not isinstance(body, dict):
        return {}
    out: dict = {}
    if isinstance(body.get("originalName"), str):
        out["original_name"] = display_name(body["originalName"])
    try:
        out["tags"] = clean_tags(body.get("tags") or [])
    except MaterialError:
        out["tags"] = []
    for key in ("width", "height", "durationSec"):
        v = body.get(key)
        if isinstance(v, (int, float)) and v > 0:
            out[key] = v
    # 我们自己加的出处字段：只认字符串，长度夹到 240
    for key in ("author", "license", "source_url", "provider"):
        v = body.get(key)
        if isinstance(v, str) and v.strip():
            out[key] = v.strip()[:MAX_NAME_LEN]
    return out


def _write_meta(d: Path, name: str, meta: dict) -> None:
    """原子写 sidecar（临时文件 + replace，`local-material-library.ts:138-144`）"""
    p = _meta_path(d, name)
    fd, tmp = tempfile.mkstemp(dir=str(d), prefix=".meta-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def read_one(d: Path, name: str) -> dict | None:
    """单个素材的完整信息；不合格返回 None。"""
    if not is_material_name(name):
        return None
    p = d / name
    try:
        st = p.stat()
    except OSError:
        return None
    if not p.is_file():
        return None
    meta = read_meta(d, name)
    row = {
        "name": name,
        "media_type": classify(name),
        "original_name": meta.get("original_name") or name,
        "tags": meta.get("tags") or [],
        "size_bytes": st.st_size,
        "updated_at": round(st.st_mtime * 1000),
    }
    for key in ("width", "height", "durationSec", "author", "license", "source_url", "provider"):
        if key in meta:
            row[key] = meta[key]
    return row


def list_materials(d: Path) -> list[dict]:
    """池里全部素材，按更新时间倒序（`local-material-library.ts:92-118`）"""
    try:
        entries = list(d.iterdir())
    except OSError:
        return []
    rows = []
    for p in entries:
        if not p.is_file() or not is_material_name(p.name):
            continue
        row = read_one(d, p.name)
        if row:
            rows.append(row)
    rows.sort(key=lambda r: (-r["updated_at"], r["name"]))
    return rows


def update_meta(d: Path, name: str, *, original_name: str | None = None, tags=None,
                provenance: dict | None = None) -> dict:
    """改原名 / 标签 / 出处；名字与标签都按竞品口径校验。"""
    cur = read_one(d, name)
    if not cur:
        raise MaterialError("MATERIAL_NOT_FOUND")
    meta = {
        "originalName": cur["original_name"],
        "tags": cur["tags"],
        "width": cur.get("width"),
        "height": cur.get("height"),
        "durationSec": cur.get("durationSec"),
    }
    if original_name is not None:
        cleaned = display_name(original_name)
        if not cleaned or cleaned != str(original_name).strip():
            raise MaterialError("INVALID_NAME")
        meta["originalName"] = cleaned
    if tags is not None:
        meta["tags"] = clean_tags(tags)
    for key in ("author", "license", "source_url", "provider"):
        if provenance and key in provenance:
            v = provenance.get(key)
            if v is None:
                meta.pop(key, None)
            elif isinstance(v, str):
                meta[key] = v.strip()[:MAX_NAME_LEN]
            else:
                raise MaterialError("INVALID_NAME")
    _write_meta(d, name, {k: v for k, v in meta.items() if v is not None})
    row = read_one(d, name)
    if not row:
        raise MaterialError("MATERIAL_NOT_FOUND")
    return row


def delete(d: Path, name: str) -> bool:
    """删素材连同 sidecar。只在池目录内动，且必须是合法素材名。"""
    if not is_material_name(name):
        return False
    p = d / name
    if not p.is_file():
        return False
    p.unlink()
    _meta_path(d, name).unlink(missing_ok=True)
    return True


# ---------------------------------------------------------------- 落盘

def store(d: Path, original_name: str, source, expected_bytes: int | None = None) -> dict:
    """收一个上传：临时文件 → 大小闸 → sha256 → 探测校验 → 发布。

    `source` 需要 `read(n)`（FastAPI 的 `UploadFile.file` 或普通文件对象）。
    返回 `{"material": {...}, "duplicate": bool}`。
    """
    disp = display_name(original_name)
    media_type = classify(disp)
    if not media_type:
        raise MaterialError("UNSUPPORTED_MATERIAL")
    if expected_bytes is not None and (expected_bytes < 1 or expected_bytes > MAX_BYTES):
        raise MaterialError("MATERIAL_SIZE")

    d.mkdir(parents=True, exist_ok=True)
    ext = extension(disp)
    if ext == "jpeg":
        ext = "jpg"
    fd, tmp = tempfile.mkstemp(dir=str(d), prefix=".part-", suffix="")
    received = 0
    h = hashlib.sha256()
    try:
        with os.fdopen(fd, "wb") as f:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                received += len(chunk)
                if received > MAX_BYTES:
                    raise MaterialError("MATERIAL_SIZE")
                h.update(chunk)
                f.write(chunk)
        if not received:
            raise MaterialError("INCOMPLETE_MATERIAL")
        if expected_bytes is not None and received != expected_bytes:
            raise MaterialError("INCOMPLETE_MATERIAL")
        tmp_path = Path(tmp)
        meta = _probe(tmp_path)
        _validate(ext, media_type, meta)
        name = f"sha256-{h.hexdigest()}.{ext}"
        dest = d / name
        duplicate = False
        try:
            os.link(tmp_path, dest)      # 原子发布；同名 = 同一份内容
        except FileExistsError:
            duplicate = True
        except OSError:
            # 文件系统不支持硬链接（某些网络盘）→ 退回复制；同名仍然按重复处理
            if dest.exists():
                duplicate = True
            else:
                dest.write_bytes(tmp_path.read_bytes())
        payload = {
            "originalName": disp,
            "tags": [],
            "width": meta["width"],
            "height": meta["height"],
        }
        if meta["duration"] > 0:
            payload["durationSec"] = meta["duration"]
        if not _meta_path(d, name).exists():
            _write_meta(d, name, payload)
        row = read_one(d, name)
        if not row:
            raise MaterialError("MATERIAL_NOT_FOUND")
        return {"material": row, "duplicate": duplicate}
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


# ---------------------------------------------------------------- 匹配（B4 的纯逻辑，供以后接）

def match_score(text: str, query: str) -> int:
    """英文整词 / 中文包含才算命中（`material-library.ts:64-77`）"""
    def tokens(s: str) -> list[str]:
        s = str(s or "").lower()
        parts = re.split(r"[^0-9a-z㐀-鿿]+", s)
        return [p for p in parts if len(p) >= 2]

    hay = tokens(text)
    wanted = set(tokens(query))
    score = 0
    for t in wanted:
        if any(h == t or ("㐀" <= t[0] <= "鿿" and t in h) for h in hay):
            score += 1
    return score


def auto_match(shots: list[dict], images: list[dict]) -> list[dict]:
    """给每个镜头挑一张素材图当参考画面（B4 自动配画面）。

    出处：竞品 `api/project/[id]/stock-fill/route.ts` —— 逐镜选一张、整次填充共享
    `usedIds` 做跨镜去重、选不中就走降级；它还有「诚实标注」(`stock-matcher.ts:38-50`
    的 `fallbackLevel`)。我们不联网搜库、没有降级阶梯，所以**能诚实标的就是命中词数**：
    返回 `score`，前端显示「命中 N 词」；**0 分不配**——绝不硬塞一张不相关的图冒充匹配。

    `shots` 每项需有 `id` / `description`（`framing` 可选）；
    `images` 每项需有 `name` / `original_name` / `tags`（素材库 `list_materials` 的形态）。
    """
    pool: list[tuple[str, str]] = []
    for row in images:
        text = " ".join([str(row.get("original_name") or ""),
                         " ".join(str(t) for t in (row.get("tags") or []))])
        pool.append((str(row.get("name") or ""), text))

    used: set[str] = set()
    out: list[dict] = []
    for s in shots:
        try:
            sid = int(s.get("id"))
        except (TypeError, ValueError):
            continue
        query = " ".join([str(s.get("description") or ""),
                          str(s.get("framing") or "")]).strip()
        if not query:
            continue
        best_name, best_score = "", 0
        for name, text in pool:
            if not name or name in used:
                continue
            # 🩸 方向要反着传：`match_score(text, query)` 里 text 是被搜的 hay、query 是 wanted。
            # 竞品是英文匹配，两边都按空格切词、对称；中文没有空格，镜头描述整句切出来是
            # 一个大 token（`咖啡店吧台，早晨阳光…` → 2 个 token），拿它当 wanted 永远命中不了
            # 素材的短标签。所以这里**素材的标签/名字当关键词**、去镜头描述里找子串
            # （中文子串匹配天然成立）；英文仍然逐词等价。
            score = match_score(query, text)
            if score > best_score:  # 同分保留先出现的（素材库按 mtime 倒序 = 新的优先）
                best_name, best_score = name, score
        if best_score <= 0:
            continue
        used.add(best_name)
        out.append({"shot_id": sid, "material": best_name, "score": best_score})
    return out


def probe_seconds(path: Path) -> float:
    """给界面显示用：视频时长（秒）。读不出返回 0。"""
    return _probe(path).get("duration") or 0.0
