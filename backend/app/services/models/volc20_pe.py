# -*- coding: utf-8 -*-
"""Seedance 2.0 **写提示词**的尺子 —— 与 H3 的 `h3_base` / `h3_ref` 平级并列，互不引用。

🩸 这是「写提示词」这一层的判据，**不是出片层**的 `volc20.py`（那个管 API 编译）。
两者同属 2.0，但管的事不一样，别合并。

官方依据：
    · 官方 skill `sd2-pe`（`data/official/sd20/skill-sd2-pe.md`，226 行）
    · 官方指南（`data/official/sd20/guide.md`，1008 行）
    · 出片参数（`api-create-task.md`，本机副本 `D:/tmp/official/sd20/`）

每条规则的首个字段就是出处（`sd2-pe:219` = skill 第 219 行）。
**指不到出处的规则不许留在这里** —— 那是自造。

与 H3 的差别（每家按每家官方标准，不许互抄）：
    · 2.0 用「镜头1/镜头2」，**禁**绝对秒数；H3 反过来必须绝对时间戳
    · 2.0 必挂兜底包；H3 官方没有这个概念
    · 2.0 台词 `{}`；H3 是 `<d>[English]…</d>`
"""
from __future__ import annotations

import re


# ---------------------------------------------------------------- 工具

#: 绝对秒数：`0-3s` / `3～5秒` / `00:03` / `第 3 秒`
_ABS_SEC = re.compile(
    r"(?<![\d:])\d{1,2}(?:\.\d+)?\s*[-–~至]\s*\d{1,2}(?:\.\d+)?\s*(?:s\b|秒)"
    r"|(?<!\d)\d{1,2}:\d{2}(?!\d)"
    r"|第\s*\d+(?:\.\d+)?\s*秒"
)

#: 裸 Asset ID
_ASSET_ID = re.compile(r"\[\s*asset-[0-9a-zA-Z_-]+\s*\]")

#: 分镜标记
_SHOT = re.compile(r"镜头\s*([0-9一二三四五六七八九十]+)")

#: 切镜动词（官方多镜头能力的连接方式）
_CUT = re.compile(r"镜头切换|切镜|切到|切换到|切过")

#: 运镜词（1.0 pro 官方「镜头语言」章节的术语，见 sd10-camera/camera-terms.md）
_CAMERA = ("推", "拉", "摇", "移", "环绕", "跟随", "升", "降", "变焦")

#: 兜底包三件（sd2-pe:219「必须包含画质包 + 稳定包 + 水印 / Logo 兜底」）
_Q = re.compile(r"高清|4K|1080|8K|细节丰富|电影质感|画质|清晰")
_ST = re.compile(r"稳定|无变形|不变形|不崩|无闪烁|画面平滑")
_WM = re.compile(r"水印|Logo|logo|LOGO")

#: 字幕兜底（sd2-pe:160「非文字生成任务必挂」）
_NOSUB = re.compile(r"保持无字幕|避免生成任何文字|不生成字幕|无任何文字|不要出现文字")
#: 文字生成任务的特征（广告语 / 字幕内容 / 气泡 / 标题）—— 这类**不该**挂无字幕兜底
_TEXT_TASK = re.compile(r"文字内容|字幕内容|出现字幕|气泡|广告语|标题内容|写着[「\"“]")

#: 背景音乐符号 `（）`（sd2-pe:205）。只在正文提到音乐类词汇时才要求。
_MUSIC_WORD = re.compile(r"背景音乐|BGM|配乐|背景音")
_MUSIC_SYM = re.compile(r"（[^）]{0,60}(?:乐|音乐|BGM|旋律|鼓点|节奏)[^）]{0,60}）")
#: 音效符号 `<>`（sd2-pe:206），只认尖括号里带声音词的那种
_SFX_WORD = re.compile(r"音效")
_SFX_SYM = re.compile(r"<[^<>]{0,60}(?:声|响|音效|[Bb][Gg][Mm])[^<>]{0,60}>")

#: 多人/多主体（sd2-pe:162「多人 / 多主体场景必挂」双胞胎兜底）
#: 🩸 光靠 `<主体2>` 抓不住 —— 官方路径 B 示例（`sd2-pe:176-184`）里舍友没编号，
#: 只写「舍友们…其中一人」。所以还要认复数指代。
_MULTI = re.compile(r"<主体[2-9]|<主体(?:二|三|四|五)")
_MULTI_WORD = re.compile(
    r"(?:两个|两位|两人|二人|三个|三位|三人|几名|几人|一群|多名|数名)"
    r"[^，。；]{0,6}(?:人|角色|主体|群众|队伍)"
    r"|(?:舍友|朋友|同学|同事|家人|路人|行人|顾客|客人们|观众|群众|邻居|队友)们"
    r"|[他她]们")
_TWIN = re.compile(r"双胞胎|分身|外形、着装、配饰完全一致|人物重复")


def _zh_len(s: str) -> int:
    """中文按字算，英文按 0.5 字折算 —— 用来对官方「中文 ≤500 字」那条。"""
    zh = sum(1 for c in s if "\u4e00" <= c <= "\u9fff")
    return zh + (len(s) - zh) // 2


# ---------------------------------------------------------------- 判据

def v1_no_abs_sec(p: str, ctx: dict) -> list[str]:
    hits = [m.group(0) for m in _ABS_SEC.finditer(p)]
    return [f"出现绝对秒数 {h}，2.0 要写「镜头1/镜头2」" for h in hits[:3]]


def v2_fallback(p: str, ctx: dict) -> list[str]:
    miss = []
    if not _Q.search(p):
        miss.append("画质包")
    if not _ST.search(p):
        miss.append("稳定包")
    if not _WM.search(p):
        miss.append("水印/Logo 兜底")
    return [f"缺兜底包：{'、'.join(miss)}"] if miss else []


def v3_asset_id(p: str, ctx: dict) -> list[str]:
    return [f"裸写 {m.group(0)}，要用 @图片N / <主体N> 桥接"
            for m in _ASSET_ID.finditer(p)][:3]


def v4_shot_marker(p: str, ctx: dict) -> list[str]:
    """有多处切镜却不写「镜头N」→ 观众/模型都对不上时序。"""
    if not _CUT.search(p):
        return []
    if _SHOT.search(p):
        return []
    # 只有一次切镜、且没写镜头号，仍算不规范（官方要求按镜头顺序组织）
    return ["写了切镜但没用「镜头1/镜头2」编号"]


def v5_one_camera(p: str, ctx: dict) -> list[str]:
    """单镜头只许 1 种运镜（sd2-pe:222「一镜一运镜」）。按「镜头N」分段查。"""
    segs = re.split(r"镜头\s*[0-9一二三四五六七八九十]+", p)
    out = []
    for i, seg in enumerate(segs):
        kinds = [c for c in _CAMERA if c in seg]
        # 「推」「拉」这类单字容易撞常用词，要求前后有「镜头/缓/慢/快/平稳」才认
        kinds = [c for c in kinds
                 if c not in ("推", "拉", "移", "升", "降") or
                 re.search(rf"(?:镜头|缓|慢|快|平稳|逐渐)[^。；]{{0,6}}{c}", seg)]
        if len(kinds) >= 2:
            out.append(f"第 {i} 段镜头里出现 {len(kinds)} 种运镜（{''.join(kinds)}），"
                       f"一镜只许 1 种")
    return out[:3]


def v6_dialogue_symbol(p: str, ctx: dict) -> list[str]:
    """台词要用 `{}`（sd2-pe:203-206）。写成「说：\"…\"」的按字幕模板走，不算台词。"""
    out = []
    for m in re.finditer(r"说\s*[：:]\s*[\"“「]", p):
        out.append(f"台词写成 {p[m.start():m.start() + 12]!r}，2.0 台词要用 {{}}")
    return out[:3]


def v7_length(p: str, ctx: dict) -> list[str]:
    n = _zh_len(p)
    return [f"正文约 {n} 字，官方建议中文 ≤500 字"] if n > 500 else []


def v8_music_symbol(p: str, ctx: dict) -> list[str]:
    """背景音乐要用 `（）` 包住（sd2-pe:205「特殊字符规范（强制使用）」）。

    🩸 只在正文**提到音乐**时才要求 —— 没音乐就不该有括号，
    否则正常主体注解 `<主体1>（李武）`（sd2-pe:153 官方自己的写法）会被误判。
    """
    if not _MUSIC_WORD.search(p) or _MUSIC_SYM.search(p):
        return []
    return ["提到了背景音乐/配乐，但没用（）包住 —— 2.0 规定音乐写在全角括号里"]


def v9_sfx_symbol(p: str, ctx: dict) -> list[str]:
    """音效用 `<>` 包住（sd2-pe:206）。同理只在提到「音效」时要求。"""
    if not _SFX_WORD.search(p) or _SFX_SYM.search(p):
        return []
    return ["提到了音效，但没用<>包住 —— 2.0 规定音效写在尖括号里"]


def v10_subtitle_fallback(p: str, ctx: dict) -> list[str]:
    """字幕兜底：非文字生成任务必挂（sd2-pe:160 + :219「按场景再挂载」）。

    文字生成任务（广告语 / 字幕 / 气泡）例外 —— 那种任务本来就要出字。
    """
    if _TEXT_TASK.search(p) or _NOSUB.search(p):
        return []
    return ["缺字幕兜底（「保持无字幕，避免生成任何文字」）—— 非文字生成任务官方要求必挂"]


def v11_twin_fallback(p: str, ctx: dict) -> list[str]:
    """双胞胎兜底：多人 / 多主体场景必挂（sd2-pe:162）。"""
    if not (_MULTI.search(p) or _MULTI_WORD.search(p)) or _TWIN.search(p):
        return []
    return ["多人场景但没挂双胞胎兜底 —— 官方要求写「禁止生成同款分身、双胞胎效果」"]


RULES = [
    ("V1", "红", "不写绝对秒数，用镜头编号", "sd2-pe:144/:223", v1_no_abs_sec),
    ("V2", "红", "兜底包齐全（画质+稳定+水印/Logo）", "sd2-pe:219", v2_fallback),
    ("V3", "红", "不裸写 Asset ID", "sd2-pe:220", v3_asset_id),
    ("V4", "红", "有切镜就要有镜头编号", "sd2-pe:144", v4_shot_marker),
    ("V5", "黄", "一镜只用一个运镜", "sd2-pe:222", v5_one_camera),
    ("V6", "红", "台词用 {} 包住", "sd2-pe:203-206", v6_dialogue_symbol),
    ("V7", "黄", "正文中文 ≤500 字", "api-create:175", v7_length),
    ("V8", "黄", "背景音乐用（）包住", "sd2-pe:205", v8_music_symbol),
    ("V9", "黄", "音效用<>包住", "sd2-pe:206", v9_sfx_symbol),
    ("V10", "黄", "非文字任务挂字幕兜底", "sd2-pe:160/:219", v10_subtitle_fallback),
    ("V11", "黄", "多人场景挂双胞胎兜底", "sd2-pe:162/:219", v11_twin_fallback),
]


def check(p: str, ctx: dict | None = None) -> list[tuple[str, str, str, str, list[str]]]:
    out = []
    for rid, sev, name, src, fn in RULES:
        try:
            issues = fn(p, ctx or {})
        except Exception as e:                    # 尺子自己崩了要看见，不许静默
            issues = [f"判据异常：{e}"]
        if issues:
            out.append((rid, sev, name, src, issues))
    return out
