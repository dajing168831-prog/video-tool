"""G2 作品流 —— 跨项目成片墙 + 封面回填预算。

出处：clipforge `src/app/api/works/route.ts:1-84`：
  · 只列**出成功的**成片，按时间倒序，最多 200 条；
  · 每行带项目上下文 + 封面缩略图；封面列早于记录存在 → **按请求惰性回填**，
    每次最多 6 张（`BACKFILL_MAX`），抽首帧、最好努力，失败不拦列表；
  · 返回 `url` / `thumbnailUrl`，缩略图可为 null。

我们的映射：
  · 「出成功」= 盘上真有视频文件：合成片 > 拼接整片 > 最后一段（与 `_film_video` 同口径）；
  · 项目上下文 ← `product.name`（我们项目没有独立 name 字段）；
  · 时长 ← compose 计划的 `total_seconds`，否则 film 计划的，再否则累加段记录；
  · 发布时间 ← 这条视频文件的 mtime（我们没有 compositions 表的 createdAt，
    文件 mtime 是唯一真实时间，不编）；
  · 封面 ← `film.cover.file`（人做过的封面）优先；没有就回填首帧到 `film.poster`。

🩸 回填只写 `film.poster`，**不覆盖** `film.cover`（那是人压过字的封面）。
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from app.services.media import ffmpeg_path

#: 每次请求最多回填几张封面（竞品 `route.ts:8`）
BACKFILL_MAX = 6
#: 单次最多返回多少条（竞品 `route.ts:31`）
LIST_LIMIT = 200
#: 抽帧位置：第 1 秒（太靠前常是黑场/转场）
POSTER_AT = 1.0


class WorkError(Exception):
    """回填失败（只在内部吞掉，不影响列表）。"""


def _load_doc(p: Path) -> dict | None:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict) or not d.get("id") or not isinstance(d.get("product"), dict):
        return None
    # 数据目录里还会放 settings.json / metrics.json —— 靠上面的字段判定挡掉
    return d


def _video_of(doc: dict, films_dir: Path) -> tuple[Path | None, str]:
    """挑这条项目「最新能看的成片」：合成片 > 拼接整片 > 最后一段。"""
    pid = str(doc.get("id") or "")
    base = Path(films_dir) / pid

    comp = doc.get("compose") or {}
    name = str((comp.get("outputs") or {}).get("mp4") or "")
    if name:
        p = base / Path(name).name
        if p.exists() and p.is_file():
            return p, "合成成片"

    film = doc.get("film") or {}
    name = str(film.get("merged") or "")
    if name:
        p = base / Path(name).name
        if p.exists() and p.is_file():
            return p, "拼接整片"

    files = film.get("files") or {}
    done = [(int(k), v) for k, v in files.items()
            if isinstance(v, dict) and str(v.get("name") or "")
            and str(k).isdigit()]
    if not done:
        return None, ""
    no, rec = sorted(done, key=lambda x: x[0])[-1]
    p = base / Path(str(rec["name"])).name
    if p.exists() and p.is_file():
        return p, f"第 {no} 段"
    return None, ""


def _duration_of(doc: dict, video: Path | None) -> float:
    comp = (doc.get("compose") or {}).get("plan") or {}
    if comp.get("total_seconds"):
        return round(float(comp["total_seconds"]), 3)
    film_plan = (doc.get("film") or {}).get("plan") or {}
    if film_plan.get("total_seconds"):
        return round(float(film_plan["total_seconds"]), 3)
    files = (doc.get("film") or {}).get("files") or {}
    total = 0.0
    for rec in files.values():
        if isinstance(rec, dict):
            try:
                total += float(rec.get("seconds") or 0)
            except (TypeError, ValueError):
                pass
    return round(total, 3)


def _mtime_text(p: Path) -> str:
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(p.stat().st_mtime))
    except OSError:
        return ""


def _grab_poster(video: Path, out: Path) -> None:
    """抽第 1 秒一帧（`-ss` 放 `-i` 前 = 快速定位）。"""
    exe = ffmpeg_path()
    if not exe:
        raise WorkError("找不到 ffmpeg")
    cmd = [exe, "-nostdin", "-v", "error", "-y",
           "-ss", f"{POSTER_AT:.3f}", "-i", str(video),
           "-frames:v", "1", "-q:v", "3", str(out)]
    p = subprocess.run(cmd, capture_output=True, text=True, errors="ignore", timeout=120)
    if p.returncode != 0 or not out.exists() or out.stat().st_size == 0:
        raise WorkError((p.stderr or "抽帧失败")[:200])


def _file_url(pid: str, name: str) -> str:
    return f"/api/drama/files/films/{pid}/{name}"


def list_works(projects_dir: Path, films_dir: Path, *,
               backfill_max: int = BACKFILL_MAX, limit: int = LIST_LIMIT,
               save=None, now: str | None = None) -> dict:
    """跨项目成片墙。

    `save(doc)` 由 API 层传入（项目文档的落盘方式归 API 管），回填时才调用。
    返回 `{works, total, backfilled}` —— 多两个字段是为了**看得见**这次抽了几张。
    """
    projects_dir, films_dir = Path(projects_dir), Path(films_dir)
    rows: list[dict] = []
    if not projects_dir.exists():
        return {"works": [], "total": 0, "backfilled": 0}

    for p in projects_dir.glob("*.json"):
        doc = _load_doc(p)
        if not doc:
            continue
        pid = str(doc.get("id") or "")
        video, label = _video_of(doc, films_dir)
        if not video:
            continue
        film = doc.get("film") or {}
        cover = str((film.get("cover") or {}).get("file") or "")
        cover_p = films_dir / pid / Path(cover).name if cover else None
        thumb_name = cover if cover_p and cover_p.exists() else ""

        poster = str((film.get("poster") or {}).get("file") or "")
        poster_p = films_dir / pid / Path(poster).name if poster else None
        if not thumb_name and poster_p and poster_p.exists():
            thumb_name = poster

        rows.append({
            "id": f"{pid}:{video.name}",
            "projectId": pid,
            # 话题项目没有商品名 → 回落项目名/主题（与项目列表同口径）
            "projectName": str((doc.get("product") or {}).get("name")
                               or doc.get("name") or doc.get("topic") or ""),
            "productName": str((doc.get("product") or {}).get("name") or ""),
            "label": label,
            "duration": _duration_of(doc, video),
            "aspectRatio": "9:16",
            "createdAt": _mtime_text(video),
            "url": _file_url(pid, video.name),
            "thumbnailUrl": _file_url(pid, thumb_name) if thumb_name else None,
            "_doc": doc,      # 内部用，出口前删
            "_video": video,
            "_thumb": thumb_name,
        })

    rows.sort(key=lambda r: r.get("createdAt") or "", reverse=True)
    total = len(rows)
    rows = rows[:max(1, int(limit))]

    backfilled = 0
    for r in rows:
        if r["_thumb"] or backfilled >= max(0, int(backfill_max)):
            continue
        pid, video = r["projectId"], r["_video"]
        out = Path(films_dir) / pid / f"poster-{time.strftime('%Y%m%d-%H%M%S')}.jpg"
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            _grab_poster(video, out)
        except (WorkError, OSError, subprocess.SubprocessError):
            continue
        backfilled += 1
        doc = r["_doc"]
        doc["film"] = {**(doc.get("film") or {}),
                       "poster": {"file": out.name,
                                  "at": POSTER_AT,
                                  "at_time": now or time.strftime("%Y-%m-%d %H:%M:%S")}}
        if save:
            try:
                save(doc)
            except OSError:
                pass  # 封面持久化是最好努力，失败不影响这次列表
        r["thumbnailUrl"] = _file_url(pid, out.name)

    works = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
    return {"works": works, "total": total, "backfilled": backfilled}
