# -*- coding: utf-8 -*-
"""官方 skill 原文加载器 —— 产品调 agent 时喂**原文**，不是二手摘要。

官方 skill `h3-prompt-writing` 的 workflow 一共三句（`SKILL.md:9-14`）：

    ① 判模式 T2VA / I2VA / FL2VA / L2VA / Ref2VA
    ② base 模式读 `references/base-en.txt`，照它的最终结构写
    ③ 全参考模式读 `references/ref-en.txt`，照它的六段式写

产品以前把这两份原文**手抄成十几条约束**塞进 system prompt，等于替官方写了
一份会漂的摘要。2026-10-29 主人一句话点破：

    「你装在我本地！！！起到的作用和效果是我想要的吗？」

—— 装在本机只让我自己聊天时能调，**产品里的顾客一点都碰不到**。
所以要起作用，原文必须进工程、必须进每次调用的 system prompt。

🩸 为什么复制进 `data/official/h3/` 而不是直接读 `D:/tmp/official/`：
   产品要部署到服务器，本机资料目录在那边不存在。
   「两份会漂」由 `scripts/p19_check.py` 的 SHA 判据兜住 ——
   工程内这份必须与 `D:/tmp/official/h3/MANIFEST.json` 登记的 sha256 一致。
"""
from __future__ import annotations

import hashlib
import re
from functools import lru_cache
from pathlib import Path

DIR = Path(__file__).resolve().parents[2] / "data" / "official" / "h3"

#: 模式 → 对应的官方 reference 文件（`SKILL.md:12-13` 指定的那两份）。
GUIDE_FILES = {"base": "base-en.txt", "ref": "ref-en.txt"}


def _read(name: str) -> str:
    p = DIR / name
    if not p.exists():
        raise FileNotFoundError(
            f"官方 skill 原文缺失：{p} —— 产品不能在没有原文的情况下替官方写摘要")
    return p.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def skill() -> str:
    """`SKILL.md` 正文（去掉 YAML frontmatter，那是给 agent 框架看的，不是写作规则）。"""
    txt = _read("SKILL.md")
    return re.sub(r"^---\n.*?\n---\n", "", txt, count=1, flags=re.S).strip()


@lru_cache(maxsize=2)
def guide(kind: str) -> str:
    """`kind` = base（三字段）/ ref（六段式）。返回官方 reference 全文。"""
    if kind not in GUIDE_FILES:
        raise ValueError(f"只认 {tuple(GUIDE_FILES)}，收到 {kind!r}")
    return _read(GUIDE_FILES[kind]).strip()


def system_prompt(kind: str, extra: str = "") -> str:
    """官方原文（SKILL.md + 对应 reference）+ 本产品的输出形态要求。

    `extra` 是**我们自己的**要求（比如"按这个 JSON schema 交结构化结果"），
    必须放在官方原文之后，且不许重复官方已有的规则 —— 重复就是在暗示原文不可信。
    """
    parts = [skill()]
    if kind == "ref":
        # 🩸 `ref-en:213-218` 原话：「The basic format follows the Video Prompt Writing
        # Guide (T2VA / I2VA / FL2VA / L2VA)」—— 六段式的**镜头写法**沿用三字段那份，
        # 运镜 20 词、切点句式、`(Sx)` + `<d>` 全在 `base-en` 里，`ref-en` 自己不重复。
        # 只传 ref-en 的话，agent 就看不到运镜闭集（实测：`Zoom In` 不在 prompt 里）。
        parts.append(guide("base"))
    parts.append(guide(kind))
    if extra.strip():
        parts.append(extra.strip())
    return "\n\n".join(parts)


def digest(kind: str = "") -> dict:
    """给自检用：各文件的 sha256。`kind` 留空 = 三份都算。"""
    names = (GUIDE_FILES[kind],) if kind else ("SKILL.md", *GUIDE_FILES.values())
    return {n: hashlib.sha256((DIR / n).read_bytes()).hexdigest() for n in names}
