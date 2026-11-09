"""商品短剧 · 九宫格关键帧。

一次出 3×3 = 9 个关键帧，**同一组人、同一套衣服、同一个房间、同一束光**。
几何技巧：整图按 9:16 竖屏出，三等分后每格天然也是 9:16 —— 裁出来就能当参考图。

九格不是「一镜一格」：镜数可能 6 也可能 12。九宫格是**关键帧水库**，
镜头不足就补同一镜的次关键瞬间，镜头多了就按重要性合并。

规则边界：每格只能复述分镜/剧本里已有的元素，不许新增场景、人物、道具。
"""
from __future__ import annotations

from . import drama_prompt_lint

GRID = 3
CELLS = GRID * GRID

SYSTEM = """你是竖屏短剧的**关键帧规划师**。你只做一件事：把已有分镜拆成 9 个可画出来的静止画面。

## 输出

只输出一个 JSON 对象，不要解释、不要代码块围栏：

{{
  "cells": [
    {{"idx": 1, "from_shot": 1, "description": "这一格画面里有什么（谁·在哪·做什么·什么表情）", "product": true}}
  ],
  "consistency": "贯穿九格的统一设定（同一组人 / 同一套衣服 / 同一个房间 / 同一束光），一句话"
}}

## 铁律

1. `cells` **必须正好 9 个**，`idx` 从 1 到 9 连续，顺序 = 阅读顺序（左上 → 右下）。
2. `from_shot` 指向分镜里的镜头号，**必须真实存在**。
3. **不许新增任何元素**：场景、人物、道具、动作，只能来自分镜和剧本里已经写了的东西。
   分镜里没有的角色不许出现在格子里。
4. 每格必须是一帧静止画面，不写「镜头推近」「气氛紧张」这类过程或情绪词。
5. 镜头数少于 9 时，**优先给这几镜补第二格**：商品出现那一镜、反转那一镜、CTA 那一镜；
   补的是同一场景的另一个可画瞬间（例如「拿起」和「放下」），不是重复同一帧。
6. 镜头数多于 9 时，按重要性合并：开场冲突 / 商品登场 / 反转 / CTA 必留，中间的过渡镜可合并。
7. 全片至少 3 格 `product: true`（商品要在参考图里够多，出片才稳）。
8. 九格之间人物外观必须一致：用到角色时，描述里带上该角色的外观锚。
"""


def build_user(doc: dict, shots: list[dict] | None = None) -> str:
    """`shots` 给了就只规划这几镜（60 秒按段出板时，一段一块）；不给 = 全片一块。"""
    sb = doc.get("storyboard_json") or {}
    sc = doc.get("script_json") or {}
    if shots is None:
        shots = [s for s in (sb.get("shots") or []) if isinstance(s, dict)]
    chars = "\n".join(
        f"- {c.get('name')}：{c.get('appearance')}"
        for c in (sc.get("characters") or []) if isinstance(c, dict)
    ) or "（无）"
    rows = []
    for i, s in enumerate(shots, 1):
        rows.append(
            "[#{id}] {dur}s ｜ {fr} ｜ 商品：{prod}\n画面：{desc}\n台词：{line}".format(
                id=s.get("id", i),
                dur=s.get("duration"),
                fr=s.get("framing") or "—",
                prod="是" if s.get("product") else "否",
                desc=s.get("description") or "",
                line=s.get("dialogue") or "（无）",
            )
        )
    p = doc.get("product") or {}
    # 视频模式的「怎么拍」也要带上：不然分镜里没人物、关键帧却画了人（互相打架）
    mode = str(((doc.get("answers") or {}).get("mode")) or "").strip()
    rule = ""
    try:
        from app.services import drama_modes
        rule = drama_modes.rule(mode)
    except Exception:  # noqa: BLE001  纯计算模块，取不到就当没选
        rule = ""
    return (
        f"【商品】{p.get('name','')}\n\n"
        f"【角色外观锚】\n{chars}\n\n"
        f"【分镜 · 共 {len(shots)} 镜】\n" + "\n\n".join(rows)
        + (f"\n\n{rule}" if rule else "")
    )


def validate(obj: dict, shots: list[dict]) -> list[str]:
    errs: list[str] = []
    cells = obj.get("cells")
    if not isinstance(cells, list):
        return ["缺 cells"]
    if len(cells) != CELLS:
        errs.append(f"cells 必须 {CELLS} 个，实际 {len(cells)}")
    valid_ids = {s.get("id", i) for i, s in enumerate(shots, 1) if isinstance(s, dict)}
    for i, c in enumerate(cells, 1):
        if not isinstance(c, dict):
            errs.append(f"第 {i} 格不是对象")
            continue
        if not (c.get("description") or "").strip():
            errs.append(f"第 {i} 格缺 description")
        fs = c.get("from_shot")
        if fs not in valid_ids:
            errs.append(f"第 {i} 格 from_shot={fs} 不存在")
    if len(cells) == CELLS:
        n = sum(1 for c in cells if isinstance(c, dict) and c.get("product") is True)
        if n < 3:
            errs.append(f"商品格只有 {n} 个，至少要 3 个")
    return errs


def normalize(obj: dict) -> dict:
    cells = []
    for i, c in enumerate(obj.get("cells") or [], 1):
        if not isinstance(c, dict):
            continue
        cells.append(
            {
                "idx": i,
                "from_shot": c.get("from_shot"),
                "description": str(c.get("description") or "").strip(),
                "product": c.get("product") is True,
            }
        )
    return {
        "cells": cells,
        "consistency": str(obj.get("consistency") or "").strip(),
    }


def ref_lines(cast: list[str], has_product: bool, product_name: str = "") -> list[str]:
    """参考图按**位置**声明用途（顺序 = 上传顺序：人物… → 商品）。

    出处：clipforge `src/lib/storyboard-grid.ts:54-69`（`refs.characterSheet` /
    `refs.productImage` 分支）——它写明「images 数组顺序是 [定妆照?, 商品图?]，
    所以提示词按位置指代」，并在人物那句里点死三件事：
    脸/发型/体型/服装以它为准、定妆照本身不是分镜画面、不许把它的影棚背景和四格分格带进任何一格。
    """
    out: list[str] = []
    n = 0
    for name in cast or []:
        n += 1
        out.append(
            f"第 {n} 张参考图是「{name}」的人物参考图——九格中这个人物的脸型、发型、体型与服装"
            "必须与其完全一致（它只作人物参考，不作为分镜画面）。"
            "人物要自然融入各格自身的场景与光线，不得把参考图的背景、分格或边框带进任何一格。"
        )
    if has_product:
        n += 1
        what = f"「{product_name}」的" if product_name.strip() else ""
        out.append(f"第 {n} 张参考图是{what}商品实拍图——九格中的商品外观、配色与包装必须与其完全一致。")
    return out


def prompt(grid: dict, *, cast: list[str] | None = None, has_product: bool = False,
           look: str = "", cast_desc: str = "", product_name: str = "") -> str:
    """把九格规划拼成一段出图提示词。全部来自分镜，不自造风格词。

    `cast` / `has_product` = **这次真的会上传的**参考图；和上传顺序同源，
    没传就不声明（声明了却没有图，模型会自己瞎猜一张脸）。
    `cast_desc` = 角色名＋剧本里的外观原文（`drama_film.build_prompt` 同款）。
    🩸 2026-11-08：原来只按「第 N 张参考图」指代，提示词里**一句外观都没有**，
    视觉锚点检查必然全红（实测 5 条缺锚全来自角色外观）。补上这段既让锚点真的进得去，
    也让模型在参考图之外多一份可读依据。
    """
    cells = grid.get("cells") or []
    consistency = grid.get("consistency") or ""
    lines = [
        "一张 3 行 3 列的九宫格画面，竖屏 9:16。三等分之后，每一格本身也是 9:16 竖屏。",
        "九格画的是同一部短剧的连续画面，人和环境必须完全一致，格与格之间没有分割线以外的装饰。",
    ]
    refs = ref_lines(list(cast or []), has_product, product_name)
    if refs:
        lines.extend(refs)
    if (cast_desc or "").strip():
        lines.append(
            "人物设定（九格提到角色一律用角色名指代，外观以此为准，"
            f"并与人物参考图一致）：{cast_desc.strip()}。")
    if consistency:
        lines.append(f"统一设定：{consistency}。")
    lines.append("")
    for c in cells:
        lines.append(f"第 {c['idx']} 格：{c['description']}")
    lines.append("")
    lines.append("每一格都是一帧静止画面，画面里出现的人物、服装、房间、光线在九格之间保持连续。")
    # 全局 Look（竞品 `look-presets.ts:15-18` 的 `image` 段，加在出图提示词后面）：
    # 一条片子每一镜的光线必须是同一个，否则接起来像拼的。没选模板 = 不加，行为不变。
    from . import drama_looks

    look_line = drama_looks.image_suffix(look)
    if look_line:
        lines.append(f"光线与色调：{look_line}")
    # F7 关键帧「动作前一瞬」指令（竞品 `prompt-lint.ts:66` / `assets/page.tsx:765`
    # 的 `frameSuffix`）：一帧只定格动作开始前的那一瞬，图生视频才有动作可演。
    lines.append(drama_prompt_lint.keyframe_instant_line("\n".join(lines)))
    return "\n".join(lines)


def lint_cells(grid: dict) -> list[str]:
    """F7：逐格标出「一帧画不出先后」的描述（只提示不拦）。

    竞品把这条警告挂在素材卡上（`assets/page.tsx:1578-1580`，扫的是
    `asset.prompt || asset.description`）；我们一格就是一张关键帧，所以扫每格的
    `description`，并且带上格号 —— 不然九格看完不知道要改哪一格。
    """
    out: list[str] = []
    for c in grid.get("cells") or []:
        if not isinstance(c, dict):
            continue
        labels = drama_prompt_lint.keyframe_static_warnings(c.get("description") or "")
        if labels:
            out.append(
                f"第 {c.get('idx')} 格含「{'、'.join(labels)}」：一帧静止画面画不出先后，"
                "改成一个瞬间的动作"
            )
    return out


#: 裁格时每边内缩的比例。出处：clipforge `src/lib/storyboard-grid.ts:99-103`
#: `computeGridCells(..., insetRatio = 0.02)` —— 原注释「生成的九宫格从来没有
#: 像素级的分隔缝，所以要内缩一点，把缝的残渣切掉，而不是留成边框」。
#: 不内缩的话，每张关键帧边上都会带一条白线，再当 @图片N 喂回去。
CELL_INSET = 0.02


def cell_boxes(w: int, h: int, inset: float = CELL_INSET) -> list[tuple[int, int, int, int]]:
    """整图 → 9 个裁剪框（按 3×3 等分，每边内缩 `inset`，左上到右下）。"""
    cw, ch = w / GRID, h / GRID
    dx, dy = int(cw * inset), int(ch * inset)
    cw, ch = int(cw) - dx * 2, int(ch) - dy * 2
    out = []
    for r in range(GRID):
        for c in range(GRID):
            out.append((int(c * w / GRID) + dx, int(r * h / GRID) + dy, cw, ch))
    return out


def _image_size(probe: str, src) -> tuple[int, int]:
    import subprocess

    r = subprocess.run(
        [probe, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(src)],
        capture_output=True, text=True, errors="ignore", timeout=60,
    )
    parts = (r.stdout or "").strip().split(",")
    if len(parts) < 2 or not parts[0].isdigit():
        raise ValueError(f"读不出图片尺寸：{(r.stderr or r.stdout)[:200]}")
    return int(parts[0]), int(parts[1])


def crop_all(src, out_dir, prefix: str = "cell") -> list:
    """本地裁图（免费，走 ffmpeg，不引新依赖）。返回裁出来的文件路径列表。"""
    import subprocess
    from pathlib import Path

    from app.services import media

    ffmpeg = media.ffmpeg_path()
    probe = media.ffprobe_path()
    if not ffmpeg or not probe:
        raise RuntimeError("找不到 ffmpeg/ffprobe，无法裁图")

    src = Path(src)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    w, h = _image_size(probe, src)
    ratio = w / h if h else 0
    if abs(ratio - 9 / 16) > 0.02:
        raise ValueError(
            f"整图 {w}×{h} 不是 9:16（实际 {ratio:.3f}）——"
            "三等分会裁出变形的格子，请按 9:16 重出（如 1152×2048）"
        )
    files = []
    for i, (x, y, cw, ch) in enumerate(cell_boxes(w, h), 1):
        p = out_dir / f"{prefix}-{i}.jpg"
        r = subprocess.run(
            [ffmpeg, "-y", "-v", "error", "-i", str(src),
             "-vf", f"crop={cw}:{ch}:{x}:{y}", "-q:v", "2", str(p)],
            capture_output=True, text=True, errors="ignore", timeout=120,
        )
        if r.returncode != 0 or not p.exists():
            raise RuntimeError(f"裁第 {i} 格失败：{(r.stderr or '')[-200:]}")
        files.append(p)
    return files
