"""封面图：从成片里抽一帧，压一行大字标题。

出处：clipforge `src/lib/video-composer/cover.ts:1-105` + `composer.ts:20-165`
（`resolveChineseFontFile` / `escapeDrawText` / `buildDrawtext` / `wrapCaption` /
`unshellFilter`），**逻辑逐字照抄**。只有一处本地化：字体候选表加了 Windows 路径
（竞品只列了 macOS / Linux —— 那条不是判据，是平台事实）。

为什么标题要逐行画而不是一次画：封面字号是 width×9%，长标题一行会超出画面被裁掉
（竞品 `cover.ts:22-26` 的原话），所以先按宽度折行，再逐行居中堆叠。
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from app.services.media import ffmpeg_path, ffprobe_path

#: 行首禁则 —— 收尾标点不能出现在行首（竞品 `composer.ts:139`）
_NO_LINE_START = re.compile(r"[。！？；，、：…!?;,.、」』”’）)\]】%]")
#: CJK 判定（竞品 `composer.ts:115` 的原字符区间）
_CJK = re.compile("[\u2e80-\u9fff\uf900-\ufaff\uff00-\uffef\u3000-\u303f\uac00-\ud7af]")


def resolve_font() -> str | None:
    """找一个能画中文的字体文件。

    🩸 顺序照抄竞品：**项目自带字体优先**（放 `public/fonts/subtitle.ttf` 就一致）；
    后面那截补了 Windows 系统字体 —— 竞品原表只有 macOS/Linux，本机是 Windows。
    """
    here = Path(__file__).resolve().parents[2]
    cands = [
        here / "assets" / "fonts" / "subtitle.ttf",
        here / "assets" / "fonts" / "subtitle.otf",
        # Windows
        Path("C:/Windows/Fonts/msyh.ttc"),       # 微软雅黑
        Path("C:/Windows/Fonts/msyhbd.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),     # 黑体
        Path("C:/Windows/Fonts/simsun.ttc"),
        Path("C:/Windows/Fonts/Deng.ttf"),       # 等线
        # macOS
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/System/Library/Fonts/STHeiti Medium.ttc"),
        Path("/Library/Fonts/Arial Unicode.ttf"),
        # Linux
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
    ]
    env = os.environ.get("VT_FONT", "").strip()
    if env and Path(env).exists():
        return env
    for p in cands:
        if p.exists():
            return str(p)
    return None


def escape_path(p: str) -> str:
    """fontfile 的路径转义（竞品 `composer.ts:53-55`）。"""
    return p.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def escape_text(text: str) -> str:
    """drawtext 文本转义（竞品 `composer.ts:41-50`）。

    🩸 `%` **不转义**：drawtext 带 `expansion=none` 时 % 就是字面量；
    转成 `\\%` 会让 ffmpeg 8.0 报 `Stray %` 并把整块文字**静默画成空白**。
    带货文案里「省 50%」「50% off」多得很 —— 这条是竞品踩过的坑，照抄。
    """
    s = str(text or "")
    s = s.replace("\\", "\\\\\\\\")
    s = s.replace("'", "\u2019")
    s = s.replace(":", "\\\\:")
    s = s.replace("[", "\\\\[")
    s = s.replace("]", "\\\\]")
    return s


def unshell_filter(f: str) -> str:
    """把「防 shell 的双反斜杠」减半成 ffmpeg 直收形式（竞品 `composer.ts:827-829`）。

    我们用 argv 直接起进程、不过 shell，所以必须减半，否则 `\\:` 会原样进滤镜串。
    """
    return f.replace("\\\\", "\\")


def is_cjk(ch: str) -> bool:
    return bool(_CJK.match(ch))


def wrap_caption(text: str, font_size: int, frame_width: int) -> str:
    """按画面宽度折行（竞品 `composer.ts:127-165` 逐字）。

    宽度估算：中日韩字 ≈ 字号，拉丁字 ≈ 字号×0.55；拉丁按词断、中文按字断。
    """
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    if not clean:
        return clean
    max_width = frame_width * 0.86  # 两侧留白

    def char_w(ch: str) -> float:
        return font_size if is_cjk(ch) else font_size * 0.55

    def str_w(s: str) -> float:
        return sum(char_w(c) for c in s)

    lines: list[str] = []
    line = ""

    def hard_break(token: str) -> None:
        nonlocal line
        for ch in token:
            if line and str_w(line + ch) > max_width and not _NO_LINE_START.match(ch):
                lines.append(line)
                line = ""
            line += ch

    for token in clean.split(" "):
        if str_w(token) > max_width:
            hard_break(token)
            continue
        cand = f"{line} {token}" if line else token
        if line and str_w(cand) > max_width:
            lines.append(line)
            line = token
        else:
            line = cand
    if line:
        lines.append(line)
    return "\n".join(lines)


def build_drawtext(*, text: str, font_size: int, font_color: str = "white",
                   border_w: int | None = None, box: dict | None = None,
                   x: str = "0", y: str = "0",
                   font_file: str | None = None,
                   line_spacing: int | None = None,
                   enable: str | None = None) -> str:
    """一条 drawtext（竞品 `composer.ts:77-95`）。

    `line_spacing` / `enable` 是 D4 烧录字幕补的两个可选参数（竞品
    `composer.ts:672/697`）：多行字幕行距、以及只在某个时间窗出现。
    老调用方不传 = 与以前逐字一致。
    """
    parts: list[str] = []
    if font_file:
        parts.append(f"fontfile='{escape_path(font_file)}'")
    parts.append("expansion=none")
    parts.append(f"text='{escape_text(text)}'")
    parts.append(f"fontsize={font_size}")
    parts.append(f"fontcolor={font_color}")
    if border_w is not None:
        parts.append(f"borderw={border_w}")
    if box:
        parts.append("box=1")
        parts.append(f"boxcolor={box['color']}")
        parts.append(f"boxborderw={box['borderW']}")
    if line_spacing:
        parts.append(f"line_spacing={line_spacing}")
    parts.append(f"x={x}")
    parts.append(f"y={y}")
    if enable:
        parts.append(f"enable='{enable}'")
    return "drawtext=" + ":".join(parts)


def build_vf(title: str, width: int, *, position: str = "center",
             font_file: str | None = None) -> str:
    """封面标题滤镜（竞品 `cover.ts:34-62`）。

    字号 = 画面宽 × 9%；块高 = 行数 × 1.5 倍行高；
    `center` 居中、`upper` 约 20%、`lower` 约 78%。
    """
    font_size = round(width * 0.09)
    lines = wrap_caption(title, font_size, width).split("\n")
    line_h = round(font_size * 1.5)
    block_h = len(lines) * line_h
    if position == "lower":
        base = f"h*0.78-{round(block_h / 2)}"
    elif position == "upper":
        base = f"h*0.2-{round(block_h / 2)}"
    else:
        base = f"(h-{block_h})/2"
    parts = [
        build_drawtext(
            font_file=font_file,
            text=line or " ",
            font_size=font_size,
            font_color="white",
            border_w=max(2, round(width * 0.006)),
            box={"color": "black@0.5", "borderW": round(width * 0.015)},
            x="(w-text_w)/2",
            y=f"{base}+{i * line_h}",
        )
        for i, line in enumerate(lines)
    ]
    return unshell_filter(",".join(parts))


def probe_width(video: Path) -> int:
    """取画面宽，读不到就按 1080（竞品 `cover.ts:65-86`）。"""
    fp = ffprobe_path()
    if not fp:
        return 1080
    try:
        p = subprocess.run(
            [fp, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width", "-of", "default=nw=1:nk=1",
             str(video)],
            capture_output=True, text=True, errors="ignore", timeout=60)
        w = int((p.stdout or "").strip().splitlines()[0])
        return w if w > 0 else 1080
    except Exception:  # noqa: BLE001
        return 1080


def generate(video: Path, title: str, out: Path, *, at: float = 1.0,
             position: str = "center") -> Path:
    """抽一帧 + 压标题 → 封面图（竞品 `cover.ts:89-105`）。"""
    ff = ffmpeg_path()
    if not ff:
        raise RuntimeError("找不到 ffmpeg，请设置 VT_FFMPEG")
    video = Path(video)
    if not video.exists():
        raise RuntimeError("成片文件不存在")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    width = probe_width(video)
    vf = build_vf(title, width, position=position, font_file=resolve_font())
    t = max(0.0, float(at))
    p = subprocess.run(
        [ff, "-hide_banner", "-loglevel", "error", "-y",
         "-ss", f"{t:.3f}", "-i", str(video),
         "-frames:v", "1", "-vf", vf, str(out)],
        capture_output=True, text=True, errors="ignore", timeout=120)
    if p.returncode != 0 or not out.exists():
        raise RuntimeError(f"封面生成失败：{(p.stderr or '')[-200:]}")
    return out
