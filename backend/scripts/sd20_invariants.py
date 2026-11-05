# -*- coding: utf-8 -*-
"""SD20 换人：**不变量**（对任意视频形态都必须成立）。

主人 2026-11-05：「真的成千上万个复刻视频上传上来以后一个一个的去修去适配吗？」
⇒ 不逐个修。把「什么样的输入都绝不能产出什么」写成判据，一次验全部形态。

每条都带出处；出处指不到的判据不许加（自造规则会被主人当场撤回）。
只读本地，不联网、不花钱、不出片。
"""
from __future__ import annotations

import re

# 裸用 @图片N 后紧接**动词或方位词** = 数字粘连歧义（SKILL.md:17 原文举例「@图片1跑向…」）。
# ⚠️ 「中」「的」「里」不算 —— `@图片1 中的女子` 正是原文给的**正确**隔断写法，
#    第一版把它们也列进来，300 组全判红（尺子把官方正确写法当成了违规）。
_BARE_AFTER = ("跑向", "走向", "冲向", "位于", "出现", "变成", "从", "向", "往")


def check(text: str, *, n_src: int, n_swap: int,
          ref_desc_missing: bool = False,
          audio: str = "original") -> list[str]:
    """返回违规列表；空列表 = 全部不变量成立。

    参数说明：
      n_src  盘点到的画面人数（0 = 没盘点）
      n_swap 本次要换的人数
      ref_desc_missing 是否≥1 张参考图缺外观描述（缺了就不该发 <主体N>）
    """
    bad: list[str] = []

    # I1 目标侧按换人数（60f82aab share 0.0 × 10-30 三次 / ef232fc6 通）
    has_tag = "<主体" in text
    if n_swap <= 1 and has_tag:
        bad.append("I1 单人换人却发了 <主体N>（60f82aab share 0.0；10-30 三次实测）")
    if n_swap >= 2 and not has_tag and not ref_desc_missing:
        bad.append("I1 多人换人却没有 <主体N> 绑定（514fae56 17%/0%；ef232fc6 有标签才通）")

    # I2 源对象必须可指认（SKILL.md:72 多人未指明方位=关键歧义；6c51196b 整片没换）
    if n_src >= 2:
        for seg in re.split(r"[；;]", text):
            m = re.search(r"将其中的(.+?)替换", seg)
            if m and m.group(1).strip() in ("人物", ""):
                bad.append("I2 画面多人却用裸「人物」点名（sd2-pe:72）")
                break

    # I3 编辑任务不得写「参考@视频N」（pg:48-51 会被误判成参考任务）
    if re.search(r"参考\s*@视频\d", text):
        bad.append("I3 出现「参考@视频N」（pg:48-51 明令禁止）")

    # I4 参考分句必须在「严格编辑」之前（pg:65-67 组合句式顺序）
    i_ref = text.find("的面部特征")
    i_edit = text.find("严格编辑")
    if i_ref != -1 and i_edit != -1 and i_ref > i_edit:
        bad.append("I4 参考分句排在「严格编辑」之后（pg:65-67）")

    # I5 约束包（sd2-pe:158-161 / :101 默认必挂）
    # 稳定包按 `sd2-pe:159` **完整版**判（2026-11-05 主人拍板「挂」）：
    #   「人物面部稳定不变形、五官清晰…」—— 压缩版「画面稳定无变形」不在判据里。
    for k in ("高清", "人物面部稳定不变形", "无字幕", "水印", "Logo"):
        if k not in text:
            bad.append(f"I5 缺约束包「{k}」（sd2-pe:158-161）")

    # I6 双胞胎兜底按人数（sd2-pe:162「多人/多主体场景必挂」）
    if n_src >= 2 and "双胞胎" not in text:
        bad.append("I6 多人画面缺双胞胎兜底（sd2-pe:162）")

    # I7 宾语不得以服装结尾（10-24 20:49 实测：读成「把衣服换成一个人」）
    for seg in re.split(r"[；;]", text):
        m = re.search(r"将其中的(.+?)替换", seg)
        if m and re.search(r"(身着|外穿|身穿|穿着|内搭)[^，,。]*$", m.group(1)):
            bad.append("I7 源宾语以服装结尾（10-24 20:49 实测句式 bug）")
            break

    # I8 宾语不得为空（10-26 20:01 实测：真发出去过「将其中的替换为」）
    if re.search(r"将其中的\s*替换", text):
        bad.append("I8 源宾语为空（10-26 20:01 实测）")

    # I9 @图片N 后接动词/方位词必须有名词隔断（SKILL.md:17）
    for m in re.finditer(r"@图片\d+(\S{0,3})", text):
        tail = m.group(1)
        if tail and not tail[0] in " ，,。；;的" and any(
                tail.startswith(w) for w in _BARE_AFTER):
            bad.append(f"I9 「{m.group(0)}」数字粘连（SKILL.md:17）")

    # I10 换人句必须存在（勾了换人却一个字没写 = 白花钱）
    if n_swap >= 1 and "替换为" not in text and "替换成" not in text \
            and "修改为" not in text:
        bad.append("I10 勾了换人但提示词里没有替换句")

    return bad
