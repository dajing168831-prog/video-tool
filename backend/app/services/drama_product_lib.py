"""A3 商品库（跨项目复用商品卡）。

出处：竞品 `web/lib/db/schema.ts` 的 `products` 表 + `app/products/page.tsx`（「商品」一级页，
一个商品卡可被多个项目复用，不再每个项目重填一遍品类/卖点/受众）。

我们的差异：
  1. 竞品是数据库表 + 外键；我们是文件库 —— `data/drama/products/index.json` 存卡片，
     `data/drama/products/<id>/` 存这一张卡自己的商品图副本（跨项目复用不能引用别的项目目录）。
  2. 竞品有独立的商品编辑页；我们这一批只做「从项目存进库 / 从库应用到项目」，
     字段编辑仍回项目里改（零重复入口）。
  3. 存/取图片都**复制**而不是移动 —— 商品库与项目各自持有文件，删一边不影响另一边。
"""
from __future__ import annotations

import json
import re
import shutil
import time
import uuid
from pathlib import Path

MAX_IMAGES = 5
_SAFE_ID = re.compile(r"^[a-zA-Z0-9_-]+$")
#: 商品卡里会跨项目复用的字段（竞品 products 表同口径）
FIELDS = ("name", "points", "facts", "audience", "category", "price", "platform")


def _index_path(base: Path) -> Path:
    return Path(base) / "index.json"


def read_index(base: Path) -> list[dict]:
    p = _index_path(base)
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text("utf-8"))
    except (OSError, ValueError):
        return []
    return [r for r in (data if isinstance(data, list) else data.get("items") or [])
            if isinstance(r, dict) and r.get("id")]


def write_index(base: Path, rows: list[dict]) -> None:
    base = Path(base)
    base.mkdir(parents=True, exist_ok=True)
    tmp = _index_path(base).with_suffix(".tmp")
    tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), "utf-8")
    tmp.replace(_index_path(base))


def list_all(base: Path) -> list[dict]:
    """按更新时间倒序。"""
    return sorted(read_index(base), key=lambda r: str(r.get("updated") or ""), reverse=True)


def find(base: Path, pid: str) -> dict | None:
    if not _SAFE_ID.match(pid or ""):
        return None
    return next((r for r in read_index(base) if r["id"] == pid), None)


def _copy_images(src_dir: Path, dst_dir: Path, names: list[str]) -> list[str]:
    out: list[str] = []
    if not names:
        return out
    dst_dir.mkdir(parents=True, exist_ok=True)
    for name in names[:MAX_IMAGES]:
        src = src_dir / Path(str(name)).name
        if not src.is_file():
            continue
        dst = dst_dir / f"{uuid.uuid4().hex[:8]}-{src.name}"
        try:
            shutil.copy2(src, dst)
        except OSError:
            continue
        out.append(dst.name)
    return out


def _card_fields(product: dict, name: str | None) -> dict:
    card = {k: product.get(k) for k in FIELDS}
    card["name"] = (name or card.get("name") or "").strip()[:80]
    for k in ("points",):
        if not isinstance(card.get(k), list):
            card[k] = []
    for k in ("facts", "audience", "category", "price", "platform"):
        card[k] = str(card.get(k) or "")[:2000]
    return card


def create_from_project(base: Path, doc: dict, images_dir: Path, *,
                        name: str | None = None) -> dict:
    """把当前项目的商品信息存成一张商品卡（图片复制一份进商品库）。"""
    product = doc.get("product") or {}
    card = _card_fields(product, name)
    if not card["name"]:
        raise ValueError("商品名还没填，先填商品名再存")
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    pid = f"pr{time.strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:4]}"
    folder = Path(base) / pid
    images = _copy_images(Path(images_dir), folder,
                          [str(x) for x in (product.get("images") or [])])
    row = {"id": pid, **card, "images": images,
           "from_project": doc.get("id") or "", "created": now, "updated": now}
    rows = read_index(base)
    rows.insert(0, row)
    write_index(base, rows)
    return row


def create_blank(base: Path, *, name: str, points: list | None = None,
                 facts: str = "", audience: str = "", category: str = "",
                 price: str = "", platform: str = "") -> dict:
    """直接建一张商品卡（不依赖项目）。

    竞品 /products 的「添加商品」走这里；我们的老路 `create_from_project`
    仍然保留（从项目存进库）。图片先空着，之后用 `add_image` 一张张补。
    """
    name = (name or "").strip()[:80]
    if not name:
        raise ValueError("商品名不能空")
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    pid = f"pr{time.strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:4]}"
    pts = [str(x).strip()[:200] for x in (points or []) if str(x).strip()][:20]
    row = {
        "id": pid, "name": name, "points": pts,
        "facts": str(facts or "")[:2000], "audience": str(audience or "")[:2000],
        "category": str(category or "")[:2000], "price": str(price or "")[:2000],
        "platform": str(platform or "")[:2000],
        "images": [], "from_project": "", "created": now, "updated": now,
    }
    rows = read_index(base)
    rows.insert(0, row)
    write_index(base, rows)
    return row


def add_image(base: Path, pid: str, fname: str) -> dict | None:
    """把一张已经落进卡目录的图登记到卡上（超过 MAX_IMAGES 抛 ValueError）。"""
    rows = read_index(base)
    for r in rows:
        if r["id"] != pid:
            continue
        images = [str(x) for x in (r.get("images") or [])]
        if len(images) >= MAX_IMAGES:
            raise ValueError(f"最多 {MAX_IMAGES} 张商品图，先删一张再传")
        images.append(Path(str(fname)).name)
        r["images"] = images
        r["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        write_index(base, rows)
        return r
    return None


def drop_image(base: Path, pid: str, fname: str) -> dict | None:
    """删卡上的一张图（连文件一起删）。"""
    rows = read_index(base)
    for r in rows:
        if r["id"] != pid:
            continue
        images = [str(x) for x in (r.get("images") or [])]
        keep = [x for x in images if Path(x).name != Path(str(fname)).name]
        if len(keep) == len(images):
            return None
        r["images"] = keep
        r["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        write_index(base, rows)
        (Path(base) / pid / Path(str(fname)).name).unlink(missing_ok=True)
        return r
    return None


def update_card(base: Path, pid: str, fields: dict) -> dict | None:
    """改名/改字段（只认 FIELDS 里的键）。"""
    rows = read_index(base)
    for r in rows:
        if r["id"] != pid:
            continue
        for k in FIELDS:
            if k in fields and fields[k] is not None:
                r[k] = fields[k] if k == "points" else str(fields[k])[:2000]
        r["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        write_index(base, rows)
        return r
    return None


def apply_to_project(base: Path, pid: str, images_dir: Path) -> dict | None:
    """把商品卡写回项目：字段照抄，图片复制进项目目录（不删项目原有图片）。"""
    row = find(base, pid)
    if not row:
        return None
    folder = Path(base) / pid
    copied = _copy_images(folder, Path(images_dir), [str(x) for x in (row.get("images") or [])])
    product = {k: row.get(k) for k in FIELDS}
    product["images"] = copied
    return {"product": product, "images": copied}


def remove(base: Path, pid: str) -> bool:
    """删卡（连同它自己的图片副本）。项目里的图片不受影响。"""
    rows = read_index(base)
    keep = [r for r in rows if r["id"] != pid]
    if len(keep) == len(rows):
        return False
    write_index(base, keep)
    folder = Path(base) / pid
    if folder.is_dir():
        shutil.rmtree(folder, ignore_errors=True)
    return True
