"""小红书图文卡（E2）—— 标题卡 + 每镜旁白一卡，3:4。

出处：clipforge `src/lib/video-composer/carousel.ts:1-137`（**逐字照抄**）：
  · `buildCardVf`    `:32-52`  每行一条 drawtext 才能真居中（单条多行是左对齐）
  · `CARD_THEMES`    `:55-61`  五种渐变主题
  · `generateCard`   `:69-97`  lavfi `gradients` 打底 + drawtext
  · `generateCarousel` `:106-137` 标题卡字号 width×8.5%，内容卡前加序号，最多 12 张
折行 / 转义 / 反斜杠减半全部复用 `drama_cover`（竞品也是复用 composer 的同几支函数）。
本地 ffmpeg，零生成费。
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from app.services import drama_cover
from app.services.media import ffmpeg_path

#: 主题（竞品 `carousel.ts:55-61` 逐值）
CARD_THEMES = {
    "night": {"gradient": ("0x0b0b12", "0x2a1248"), "font_color": "white"},
    "warm": {"gradient": ("0x2a0e05", "0x6b2810"), "font_color": "white"},
    "mint": {"gradient": ("0x07231a", "0x0f4a32"), "font_color": "white"},
    "mono": {"gradient": ("0x111111", "0x2b2b2b"), "font_color": "white"},
    "rose": {"gradient": ("0x2a0a1a", "0x6b1040"), "font_color": "white"},
}
DEFAULT_THEME = "night"

#: 一场图文最多几张（竞品 `carousel.ts:100`：小红书最多 ~18 张，保守封 12）
MAX_CARDS = 12
#: 默认 3:4（竞品 `carousel/route.ts:28-29`）
DEFAULT_WIDTH, DEFAULT_HEIGHT = 1080, 1440
MIN_SIDE, MAX_SIDE = 320, 1920


def resolve_card_theme(name: str | None) -> dict:
    """主题名 → 颜色；不认识的一律回落 night（竞品 `carousel.ts:64-66`）。"""
    return CARD_THEMES.get((name or "").lower(), CARD_THEMES[DEFAULT_THEME])


def build_card_vf(*, text: str, width: int, font_file: str | None = None,
                  font_size: int | None = None,
                  font_color: str = "white") -> str:
    """一张卡的 drawtext 链（竞品 `carousel.ts:32-52` 逐字）。

    字号默认 width×5.5%；行高 1.5 倍；整块垂直居中、每行水平居中。
    """
    size = font_size or round(width * 0.055)
    lines = drama_cover.wrap_caption(text, size, width).split("\n")
    line_h = round(size * 1.5)
    block_h = len(lines) * line_h
    parts = [
        drama_cover.build_drawtext(
            font_file=font_file,
            text=line or " ",
            font_size=size,
            font_color=font_color,
            border_w=max(2, round(width * 0.004)),
            x="(w-text_w)/2",
            y=f"(h-{block_h})/2+{i * line_h}",
        )
        for i, line in enumerate(lines)
    ]
    return drama_cover.unshell_filter(",".join(parts))


def generate_card(*, text: str, out: Path, width: int, height: int,
                  font_file: str | None = None, font_size: int | None = None,
                  font_color: str = "white",
                  gradient: tuple[str, str] = ("0x0b0b12", "0x2a1248")) -> Path:
    """渐变底 + 文字 → PNG（竞品 `carousel.ts:69-97`）。"""
    ff = ffmpeg_path()
    if not ff:
        raise RuntimeError("找不到 ffmpeg，请设置 VT_FFMPEG")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    c0, c1 = gradient
    vf = build_card_vf(text=text, width=width, font_file=font_file,
                       font_size=font_size, font_color=font_color)
    src = (f"gradients=s={width}x{height}:c0={c0}:c1={c1}"
           f":x0=0:y0=0:x1={width}:y1={height}")
    p = subprocess.run(
        [ff, "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", src,
         "-vf", vf, "-frames:v", "1", str(out)],
        capture_output=True, text=True, errors="ignore", timeout=120,
    )
    if p.returncode != 0 or not out.exists():
        raise RuntimeError(f"卡片生成失败：{(p.stderr or '')[-200:]}")
    return out


def generate_carousel(*, title: str, lines: list[str], out_dir: Path,
                      prefix: str, width: int = DEFAULT_WIDTH,
                      height: int = DEFAULT_HEIGHT, theme: str | None = None,
                      font_file: str | None = None) -> list[Path]:
    """标题卡 + 每句旁白一卡（竞品 `carousel.ts:106-137`）。

    🩸 `lines` 传的是**已经取好的旁白文本**（空行由调用方或这里过滤）。
    标题卡字号 width×8.5%；内容卡前加 `N. ` 序号，最多 `MAX_CARDS` 张。
    """
    width = min(MAX_SIDE, max(MIN_SIDE, int(width or DEFAULT_WIDTH)))
    height = min(MAX_SIDE, max(MIN_SIDE, int(height or DEFAULT_HEIGHT)))
    font = font_file or drama_cover.resolve_font()
    if not font:
        raise RuntimeError("找不到中文字体（VT_FONT 或系统字体），卡片画不出字")
    colors = resolve_card_theme(theme)
    out_dir = Path(out_dir)
    paths: list[Path] = []

    title_path = out_dir / f"{prefix}-0.png"
    generate_card(text=title or "图文", out=title_path, width=width, height=height,
                  font_file=font, font_size=round(width * 0.085),
                  font_color=colors["font_color"], gradient=colors["gradient"])
    paths.append(title_path)

    idx = 1
    for text in lines:
        if idx > MAX_CARDS:
            break
        clean = (text or "").strip()
        if not clean:
            continue
        p = out_dir / f"{prefix}-{idx}.png"
        generate_card(text=f"{idx}. {clean}", out=p, width=width, height=height,
                      font_file=font, font_color=colors["font_color"],
                      gradient=colors["gradient"])
        paths.append(p)
        idx += 1
    return paths
