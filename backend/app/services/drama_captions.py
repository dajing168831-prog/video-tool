"""字幕样式预设（4 种）—— 纯数据。

出处：clipforge `src/lib/caption-presets.ts:1-59`（数据由
`scripts/import_clipforge_presets.py` 原样抽进 `app/data/caption_presets.json`）。

竞品文件头 `:3-7` 解释为什么是这四种：2026 那波 agent-skill 视频剪辑工具收敛到
「punchy 粗体 / 标准带框 / 极简」三种最常用，第四个 karaoke 是他们原有的逐字高亮。
我们全抄，四种都留着 —— 组件合成阶段（D 批）按 id 取这一份规格。

⚠️ 这一份只管**字幕长什么样**；时间轴切分在 `drama_subtitle.py`，两件事不要混。
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data" / "caption_presets.json"

#: 默认值，与竞品 composer 历史默认**逐字节等价**（选它等于什么都不改）
DEFAULT_ID = "standard"


@lru_cache(maxsize=1)
def _all() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


def all_presets() -> dict:
    return dict(_all())


def ids() -> list[str]:
    return list(_all().keys())


def get(pid: str | None) -> dict | None:
    return _all().get(pid) if pid else None


def valid(pid: str | None) -> bool:
    return bool(pid) and pid in _all()


def overrides(pid: str | None) -> dict:
    """drawtext 路要覆盖的字幕参数；karaoke 走 ASS 路，由调用方换实现（返回 {}）。"""
    p = get(pid)
    if not p or p.get("karaoke"):
        return {}
    return {"fontSizeRatio": p["fontSizeRatio"],
            "color": p["color"],
            "strokeWidth": p["strokeWidth"],
            "box": p["box"]}


def public() -> list[dict]:
    return [{"id": p["id"],
             "font_size_ratio": p["fontSizeRatio"],
             "color": p["color"],
             "stroke_width": p["strokeWidth"],
             "box": p["box"],
             "karaoke": bool(p.get("karaoke"))} for p in _all().values()]


# ---------------------------------------------------------------------------
# D4 烧录 —— 三档走 drawtext，karaoke 走 libass 的 ASS。
#
# 出处：
#   · drawtext 档：clipforge `video-composer/composer.ts:659-704`
#     （字号 = 画面宽 × preset.fontSizeRatio；描边 = preset.strokeWidth；
#       box 的 boxborderw = 字号 × 0.35；底边安全区见 `safe-zone.ts:26/35`）
#   · karaoke：clipforge `video-composer/karaoke.ts:1-257`（逐字 `{\k}` 高亮，
#     时长按字数比例分；含数字的单元放大 1.35 倍并换成强调色）
#
# 只有一个本地化：我们的时间轴来自**分镜台词**，不是 TTS 词边界
# （D1 还没接），所以 karaoke 用字数比例，不用 `buildKaraokeLineTextFromWords`。
# ---------------------------------------------------------------------------

#: 字幕底边离画面底部的比例（竞品 `safe-zone.ts:26/35`）
CAPTION_SAFE_BOTTOM_RATIO = 0.17
CAPTION_SAFE_BOTTOM_RATIO_NOCARD = 0.22

#: ASS 里的默认色（&HAABBGGRR）
_ASS_HIGHLIGHT = "&H0000F0FF"   # yellow
_ASS_UNSUNG = "&H00FFFFFF"      # white
_ASS_OUTLINE = "&H00202020"
_ASS_ACCENT = "&H000050FF"      # orange-red

_CJK_UNIT = re.compile("[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af]")
_TIMED = re.compile(r"[\w\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af]")


def is_karaoke(pid: str | None) -> bool:
    p = get(pid)
    return bool(p and p.get("karaoke"))


def font_name_for(path: str | None) -> str:
    """字体文件 → ASS 的 Fontname（libass 按名字找字体）。

    只列我们自己会挑到的那几个（`drama_cover.resolve_font()` 的候选表）；
    认不出就回落到 Noto Sans CJK SC —— 与竞品自带的 `subtitle.ttf` 同名。
    """
    name = Path(str(path or "")).name.lower()
    return {
        "msyh.ttc": "Microsoft YaHei",
        "msyhbd.ttc": "Microsoft YaHei",
        "simhei.ttf": "SimHei",
        "simsun.ttc": "SimSun",
        "deng.ttf": "DengXian",
        "subtitle.ttf": "Noto Sans CJK SC",
        "subtitle.otf": "Noto Sans CJK SC",
    }.get(name, "Noto Sans CJK SC")


def drawtext_chain(cues: list[dict], width: int, pid: str | None, *,
                   position: str = "bottom", has_card: bool = False,
                   font_file: str | None = None) -> str:
    """把字幕条编译成一条 drawtext 滤镜链（已减半反斜杠，可直接进 argv）。

    `cues` = `[{text, start, end}]`（秒，相对成片）。karaoke 预设不在这一档，
    调用方应改走 `karaoke_ass()`（这里返回 ""，不假装画了）。
    """
    from . import drama_cover

    p = get(pid)
    if not p or p.get("karaoke"):
        return ""
    font_size = max(12, round(width * float(p["fontSizeRatio"])))
    box = p.get("box")
    box_opt = None if box is False else {
        "color": (box or {}).get("color") or "black@0.45",
        # 竞品 composer.ts:669：boxborderw = 字号 × 0.35
        "borderW": round(font_size * 0.35),
    }
    ratio = (CAPTION_SAFE_BOTTOM_RATIO if has_card
             else CAPTION_SAFE_BOTTOM_RATIO_NOCARD)
    y = f"h*{1 - ratio:.2f}-text_h"
    if position == "top":
        y = "h*0.08"
    elif position == "center":
        y = "(h-text_h)/2"
    parts: list[str] = []
    for c in cues or []:
        text = str(c.get("text") or "").strip()
        if not text:
            continue
        wrapped = drama_cover.wrap_caption(text, font_size, width)
        parts.append(drama_cover.build_drawtext(
            text=wrapped, font_size=font_size,
            font_color=str(p.get("color") or "white"),
            border_w=int(p.get("strokeWidth") or 3),
            box=box_opt, x="(w-text_w)/2", y=y,
            line_spacing=round(font_size * 0.28),
            enable=f"between(t,{float(c['start']):.3f},{float(c['end']):.3f})",
            font_file=font_file,
        ))
    return drama_cover.unshell_filter(",".join(parts))


def _ass_time(sec: float) -> str:
    """秒 → ASS 时间 H:MM:SS.cc（先舍入到厘秒再拆，跨秒进位才正确，
    竞品 `karaoke.ts:62-72`）。"""
    cs = round(max(0.0, float(sec)) * 100)
    return f"{cs // 360000}:{(cs % 360000) // 6000:02d}:{(cs % 6000) // 100:02d}.{cs % 100:02d}"


def _ass_escape(text: str) -> str:
    return (str(text or "").replace("\\", "\\\\").replace("{", "\\{")
            .replace("}", "\\}").replace("\r\n", "\\N").replace("\n", "\\N"))


def split_units(text: str) -> list[str]:
    """逐字高亮单元：中日韩按字、拉丁按词（空格吸进前一个词尾，
    竞品 `karaoke.ts:83-109`）。"""
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    if not clean:
        return []
    units: list[str] = []
    latin = ""

    def flush() -> None:
        nonlocal latin
        if latin:
            units.append(latin)
            latin = ""

    for ch in clean:
        if _CJK_UNIT.match(ch):
            flush()
            units.append(ch)
        elif ch == " ":
            latin += " "
            flush()
        else:
            latin += ch
    flush()
    return [u for u in units if u]


def _inline_colour(ass_colour: str) -> str:
    hexpart = str(ass_colour or "").replace("&H", "").replace("&", "")
    bgr = hexpart[2:] if len(hexpart) >= 8 else hexpart
    return f"&H{bgr or 'FFFFFF'}&"


def _line_text(text: str, duration: float) -> str:
    units = split_units(text)
    if not units:
        return ""
    total = max(1, round(duration * 100))
    lens = [max(len(u.strip()), 1) for u in units]
    summed = sum(lens)
    used = 0
    out: list[str] = []
    for i, u in enumerate(units):
        k = (max(1, total - used) if i == len(units) - 1
             else max(1, round(lens[i] / summed * total)))
        used += k
        emph = bool(re.search(r"\d", u))
        fs = round(46 * 1.35) if emph else 46
        colour = _inline_colour(_ASS_ACCENT) if emph else _inline_colour(_ASS_HIGHLIGHT)
        out.append(f"{{\\k{k}\\fs{fs}\\1c{colour}}}{_ass_escape(u)}")
    return "".join(out)


def karaoke_ass(cues: list[dict], *, font_name: str, width: int = 1080,
                height: int = 1920) -> str:
    """逐字高亮 ASS（竞品 `karaoke.ts:218-257`）。

    `cues` = `[{text, start, end}]`；`\\k` 时长按字数比例铺满整句
    （我们没有 TTS 词边界，这是竞品在没有词数据时的同一套兜底）。
    """
    font_size = max(18, round(width * 0.0426))  # 竞品默认 46 @1080 宽
    outline = max(2, round(font_size * 0.07))
    margin_v = round(height * CAPTION_SAFE_BOTTOM_RATIO)
    header = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding",
        f"Style: K,{font_name},{font_size},{_ASS_HIGHLIGHT},{_ASS_UNSUNG},"
        f"{_ASS_OUTLINE},&H64000000,1,0,0,0,100,100,0,0,1,{outline},1,2,"
        f"60,60,{margin_v},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    events: list[str] = []
    for c in cues or []:
        text = str(c.get("text") or "").strip()
        start, end = float(c.get("start") or 0), float(c.get("end") or 0)
        if not text or end <= start:
            continue
        body = _line_text(text, max(0.2, end - start))
        events.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},K,,0,0,0,,{body}")
    return "\n".join(header + events) + "\n"


