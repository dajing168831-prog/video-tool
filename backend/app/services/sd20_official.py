# -*- coding: utf-8 -*-
"""Seedance 2.0 官方资料加载器 —— 与 `h3_official` 平级并列，互不 import。

🩸 2.0 的官方材料**不是一份**，四份（2026-10-30 主人点破「你只喂了半个 skill」后查实）：

    `skill-sd2-pe.md`（226 行）= 目录 + 核心工作流 + 输出合同
    `guide.md`（1008 行）      = 正文：基础/进阶公式、分镜时序、动作、运镜、
                                  画质风格约束、常见问题、附录 37 条案例
    `trouble.md`（383 行）     = 《参考生视频常见问题与处理指南》V1.7
                                  ⚠️ 第一版**漏喂了这一份**，而它有 guide/skill 里
                                  一个字都没有的东西：`1.4 参数规范`（时长/比例可以
                                  写进提示词、要写中文「秒」不能写 s）、
                                  `4.1 通用优化原则`（重要内容前置 / 明确约束 /
                                  主体明确指代 / 避免冗余 / 参考素材独立）、
                                  V-1~V-11 的逐条解法
    `tips-sd20.md`（38 行）    = 两份官方教程里的提示词章节逐字摘录
                                  （`tutorial.md:1845-1866`「提示词技巧/规则」、
                                   `video-gen-tutorial.md:1555-1564`「提示词建议」）

skill 里大量用超链接指 `guide.md`（例如「更多请参见 [镜头语言]」），
**只喂 skill = 只给了个目录**。这跟 H3（`SKILL.md` + `references/*.txt`）
是同一个结构，所以这里也照 H3 的做法：原文全喂，不写二手摘要。

另收 `sd10-camera/camera-terms.md`：`guide.md:191` 把 2.0 的运镜词表
**指到了 1.0 pro 那份文档**，2026-10-30 主人拍板「运镜词表要从 1.0 pro 那份
文档搬」。那份在 sd20 目录之外，所以单独一个目录存放，不混进 MANIFEST。
"""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

DIR = Path(__file__).resolve().parents[2] / "data" / "official" / "sd20"
CAMERA = (Path(__file__).resolve().parents[2] / "data" / "official"
          / "sd10-camera" / "camera-terms.md")


def _read(p: Path, what: str) -> str:
    if not p.exists():
        raise FileNotFoundError(
            f"2.0 官方原文缺失：{p}（{what}）—— 产品不能在没有原文的情况下替官方写摘要")
    return p.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def skill() -> str:
    """`skill-sd2-pe.md` 全文（含工作流 Step 0–4、输出路径 A/B、强制约束总览）。"""
    return _read(DIR / "skill-sd2-pe.md", "官方提示词 skill").strip()


@lru_cache(maxsize=1)
def guide() -> str:
    """`guide.md` 全文（公式 / 分镜时序 / 运镜 / 画质 / 常见问题 / 附录案例）。"""
    return _read(DIR / "guide.md", "官方提示词指南").strip()


@lru_cache(maxsize=1)
def trouble() -> str:
    """`trouble.md` 全文 —— 官方《参考生视频常见问题与处理指南》V1.7。

    这块**不能省**：`1.1 任务类型的推荐句式`、`1.2 主体定义`、`1.4 参数规范`、
    `4.1 通用优化原则`、V-1~V-11 逐条解法，guide/skill 里都没有。
    """
    return _read(DIR / "trouble.md", "官方常见问题与处理指南").strip()


@lru_cache(maxsize=1)
def tips() -> str:
    """两份官方教程里的提示词章节（逐字摘录，出处标在每段前面）。"""
    return _read(DIR / "tips-sd20.md", "官方教程的提示词章节").strip()


@lru_cache(maxsize=1)
def camera_terms() -> str:
    """运镜术语表 —— `guide.md:191` 官方指过去的 1.0 pro「镜头语言」原文。"""
    return _read(CAMERA, "官方指定的运镜术语上游").strip()


def system_prompt(extra: str = "") -> str:
    """官方原文（skill + guide + trouble + 教程章节 + 运镜词表）+ 本产品的形态要求。

    🩸 顺序有讲究：skill 是**目录 + 工作流骨架**，放最前；guide 是正文；
    trouble 和 tips 是对前两份的**补充和纠错**，紧跟着；运镜词表是工具表，最后。
    产品层的 `extra` 放最末尾，且不许重复官方已有的规则 —— 重复就是在暗示原文不可信。
    """
    parts = [skill(), guide(), trouble(), tips(), camera_terms()]
    if extra.strip():
        parts.append(extra.strip())
    return "\n\n".join(parts)


def digest() -> dict:
    """给自检用：各文件的 sha256。"""
    out = {}
    for name, p in (("skill", DIR / "skill-sd2-pe.md"),
                    ("guide", DIR / "guide.md"),
                    ("trouble", DIR / "trouble.md"),
                    ("tips", DIR / "tips-sd20.md"),
                    ("camera", CAMERA)):
        out[name] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out
