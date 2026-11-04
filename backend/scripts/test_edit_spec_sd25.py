"""火山 Seedance 2.5 的提示词自检（**只测 2.5**，别家的断言不许进这个文件）。

由 `test_edit_spec.py --model volc25` 调用；共用规则在 `test_edit_spec_common.py`。
不联网、不花钱。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import edit_spec  # noqa: E402
from test_edit_spec_common import (  # noqa: E402
    check, ex, only_face, p, p1, ppl2,
)

MODEL = "volc25"
LABEL = "火山 2.5"


def run() -> None:
    print("== 火山 2.5 提示词 ==")
    # 官方视频编辑模板（sd25-pe「视频编辑模板」/ sd2-pe「编辑视频」）：
    # 🩸 范围闭环是 **2.5 视频编辑模板**的结构件（sd25-pe:550/554）。
    # 2.0 不写：官方《Seedance 2.0 提示词指南》§「编辑视频」开头写明
    # 「未提及的部分，**默认保持不变**」——多写一句等于把默认行为改成新指令。
    _p25 = edit_spec.compile_prompt("volc", p, model="doubao-seedance-2-5-pro")
    check("2.5 有范围闭环", "其他可见人物、道具和背景元素保持原样" in _p25, True)
    # 🩸 2026-10-23 改：官方 <原对象> 不带 @视频1（`sd25-pe:561`/`:584`），
    # 原断言 `只把@视频1中的人物` 锁死了官方没有的前缀。
    # 🩸 2026-10-28：模板行 `sd25-pe:561` 的动词是「修改为」
    #   （`编辑@视频1，只把<原对象或区域>修改为<目标内容>。`）；「替换为」
    #   只出现在已填示例 `:584`。判据对齐模板原文。
    # 🩸 2026-10-28 撤回：官方已填示例全用「替换为」（`sd25-pe:584/:602`、
    #   `sd25-guide:1205-1209`），「修改为」只在占位模板 `:561` 里。守示例的词。
    check("2.5 用「只把」限定范围", "只把人物替换为" in _p25, True)
    check("2.5 不自动挂双胞胎兜底（原则 8）", "双胞胎" not in _p25, True)
    # 🩸 2026-10-29 主人拍板「直接禁止字幕」—— AI 重画以后字幕会写糊字、错别字，
    #   比没字幕更难看。**官方 skill `sd25-pe:876` 本来就要求**：「不需要字幕时
    #   同时写明画面不显示字幕」；`:882` 无对白任务也要写。
    #   但不放 `ruler_sd25.RULES`：指南那六条官方示例一条都没写这句，
    #   放进去 `--calib` 会把官方样例判红（实测 6/6 全红）——
    #   和 T2 降黄是同一个理由（官方明令必须 + 官方示例也遵守，才够当红规则）。
    #   守在这里的产出断言上。
    #   措辞必须是 2.5 自己的：2.0 那句「避免生成任何文字或字幕」会被 C2 判成兜底句。
    check("2.5 写明「画面不显示字幕」（官方 sd25-pe:876）",
          "画面不显示字幕" in _p25, True)
    check("2.5 不用 2.0 的字幕兜底措辞",
          "避免生成任何文字或字幕" not in _p25, True)
    # 🩸 2026-10-23 2.5 全维度排查（出处见 app/services/edit_spec.py 内注释）：
    #   · 台词用 `{}`（sd25-pe:867）、内容逐句写进去（sd25-guide:907）
    #   · @音频1 也要在【目标素材职责】里有自己一行（sd25-pe:361 / 原则 3）
    #   · 时间戳只写整数秒（sd25-guide:336）
    _lines = [[{"start": 0.4, "end": 1.8, "text": "我走了", "lang": "zh"}]]
    _t25 = edit_spec.compile_prompt(
        "volc", edit_spec.normalize({"change": {"person": True, "person_ids": ["P1"]},
                                     "audio": "tts"}),
        model="doubao-seedance-2-5-260628", slots=["person"],
        source_people=[{"id": "P1", "present": True,
                        "desc_zh": "穿红裙的女人"}],
        audio_ref=True, shot_lines=_lines, shot_cuts=[1.4, 2.6])
    check("2.5 台词用花括号写内容", "{我走了}" in _t25, True)
    check("2.5 @音频1 写进【目标素材职责】",
          "@音频1用于" in _t25.split("【编辑对象与范围】")[0], True)
    check("2.5 时间戳是整数秒",
          ("第 1 秒" in _t25 and "第 3 秒" in _t25 and "第 2.60 秒" not in _t25), True)
    # 不改配音（original / 无音轨）就不把台词写进提示词
    _t25_orig = edit_spec.compile_prompt(
        "volc", edit_spec.normalize({"change": {"person": True, "person_ids": ["P1"]},
                                     "audio": "original"}),
        model="doubao-seedance-2-5-260628", slots=["person"],
        audio_ref=True, shot_lines=_lines)
    check("2.5 保留原声不写台词内容", "{我走了}" not in _t25_orig, True)
    # 🩸 2026-10-28（coverage 97%，只剩 `volc25_compile.py` 六行没跑到）：
    #   台词跨切被拆成 `start`/`end` 两半，**分桶是按分段做的**
    #   （`video_edit.py:1721-1722`）—— 切点正好落在分段交界时，`end` 落到下一段，
    #   这一段只拿到 `start`。循环结束时必须把这半句补发出去，否则台词整个丢掉。
    #   下面三条锁的是**产出**（提示词里有几句台词），不是"代码有没有那一行"。
    _half = [[{"text": "只有开头的半句", "part": "start", "lang": "zh"}]]
    _h25 = edit_spec.compile_prompt(
        "volc", edit_spec.normalize({"change": {"person": True, "person_ids": ["P1"]},
                                     "audio": "tts"}),
        model="doubao-seedance-2-5-260628", slots=["person"],
        source_people=[{"id": "P1", "present": True, "desc_zh": "穿红裙的女人"}],
        audio_ref=True, shot_lines=_half)
    check("段尾只剩 start 半句 → 照样写进提示词（不许丢）",
          "{只有开头的半句}" in _h25, True)
    # 同一段里 `start` 后面又跟了一句**不带 part 的独立台词**：
    # 先把 pending 发出去，两句各自成句 —— 不能合并，也不能只留后一句。
    _brk = [[{"text": "前半句没说完", "part": "start", "lang": "zh"},
             {"text": "这是另一句完整的台词", "lang": "zh"}]]
    _b25 = edit_spec.compile_prompt(
        "volc", edit_spec.normalize({"change": {"person": True, "person_ids": ["P1"]},
                                     "audio": "tts"}),
        model="doubao-seedance-2-5-260628", slots=["person"],
        source_people=[{"id": "P1", "present": True, "desc_zh": "穿红裙的女人"}],
        audio_ref=True, shot_lines=_brk)
    check("start 被独立句打断 → 两句各自成句，不合并",
          ("{前半句没说完}" in _b25 and "{这是另一句完整的台词}" in _b25
           and "{前半句没说完这是另一句完整的台词}" not in _b25), True)
    # 空白台词（ASR 出的空行）：跳过它，别写出一个空的 `{}` ——
    # 模型看到一个空台词标记会自己补一套词。
    _blank = [[{"text": "   ", "lang": "zh"},
               {"text": "正常一句", "lang": "zh"}]]
    _k25 = edit_spec.compile_prompt(
        "volc", edit_spec.normalize({"change": {"person": True, "person_ids": ["P1"]},
                                     "audio": "tts"}),
        model="doubao-seedance-2-5-260628", slots=["person"],
        source_people=[{"id": "P1", "present": True, "desc_zh": "穿红裙的女人"}],
        audio_ref=True, shot_lines=_blank)
    check("空白台词跳过，不产生空的 {}",
          ("{}" not in _k25 and "{正常一句}" in _k25), True)
    # 背景替换的边界（sd25-pe:576「只修改主体轮廓之外的背景」）
    _t25_bg = edit_spec.compile_prompt(
        "volc", edit_spec.normalize({"change": {"scene": True, "scene_desc": "霓虹灯街道"}}),
        model="doubao-seedance-2-5-260628", slots=["scene"])
    check("2.5 背景替换写主体轮廓之外", "主体轮廓之外的背景" in _t25_bg, True)
    # 🩸 2026-10-26 18:xx（2.5 逐一过官方 · 功能 4【编辑对象与范围】）：
    # 官方 `sd25-pe:568`「只修改**<明确对象和区域>**」+ `:570` 兜底句
    # 「除以上明确修改对象外，@视频1中其他可见人物…保持原样」。
    # 画面三个人只换一个时，写「只修改@视频1中的人物」= 把三个人都算成修改对象，
    # 和兜底句自相矛盾。**成对**：只换一部分要点名；全换才写「人物」。
    _fr3 = [{"id": "P1", "present": True, "position": "center",
             "desc_zh": "留短黑发，佩戴黑框眼镜，身穿藏蓝色外套的男性"},
            {"id": "P2", "present": True, "position": "right",
             "desc_zh": "留短黑发，身穿黑色短袖高领上衣的男性"},
            {"id": "P3", "present": True, "position": "left",
             "desc_zh": "留短寸发型，身穿黑色长袖上衣的男性"}]
    _t25_part = edit_spec.compile_prompt(
        "volc", edit_spec.normalize({"change": {"person": True, "person_ids": ["P1"]}}),
        model="doubao-seedance-2-5-260628", slots=["person"],
        source_people=[_fr3[0]], frame_people=_fr3)
    check("2.5 三人只换一个 → 范围句点名到具体对象",
          "只修改@视频1中的目标人物（替换画面中央人物）" in _t25_part, True)
    _t25_all = edit_spec.compile_prompt(
        "volc", edit_spec.normalize({"change": {"person": True,
                                                "person_ids": ["P1", "P2"]}}),
        model="doubao-seedance-2-5-260628", slots=["person", "person2"],
        source_people=[_fr3[0], _fr3[1]], frame_people=[_fr3[0], _fr3[1]])
    check("2.5 画面里的人全换 → 仍写「人物」（不啰嗦）",
          "只修改@视频1中的人物。" in _t25_all, True)
    # 多人对话要写明其余人闭口（sd25-pe:875），不写模型会让所有人一起动嘴
    _t25_2p = edit_spec.compile_prompt(
        "volc", edit_spec.normalize(
            {"change": {"person": True, "person_ids": ["P1", "P2"],
                        "speaker_ids": ["P1"]}, "audio": "tts"}),
        model="doubao-seedance-2-5-260628", slots=["person", "person2"],
        audio_ref=True, shot_lines=_lines)
    check("2.5 只有一人说话时其余人闭口聆听",
          "自然闭口聆听" in _t25_2p and "@图片2中的人物自然闭口聆听" in _t25_2p, True)
    # 逐句说话人（由 video_edit._assign_speakers 按画面推断）：两人各说一句，
    # 必须分别指名（sd25-pe:875「多名说话人分别标注，不要只在开头统一声明」），
    # 而且**不能**写"其他人闭口聆听"——两个人都在说，那句话自相矛盾。
    _t25_two = edit_spec.compile_prompt(
        "volc", edit_spec.normalize(
            {"change": {"person": True, "person_ids": ["P1", "P2"]},
             "audio": "tts"}),
        model="doubao-seedance-2-5-260628", slots=["person", "person2"],
        audio_ref=True,
        shot_lines=[[{"start": 0.4, "end": 1.8, "text": "我走了",
                      "lang": "zh", "speaker": "P1"}],
                    [{"start": 2.5, "end": 4.0, "text": "别找我",
                      "lang": "zh", "speaker": "P2"}]])
    check("2.5 逐句按说话人指名 P1", "@图片1中的人物说{我走了}" in _t25_two, True)
    check("2.5 逐句按说话人指名 P2", "@图片2中的人物说{别找我}" in _t25_two, True)
    check("2.5 两人都说话时不写闭口聆听", "自然闭口聆听" in _t25_two, False)

    # 🩸 2026-10-25（D16）：判不出说话人时**不许把所有人并列成说话主体**。
    # 官方 `sd25-pe:876`「多名说话人**分别标注**，不要只在开头统一声明」；
    # 并列两个人物 = 编一个不存在的说话人，还会跟"其余人闭口"打架。
    _t25_unk = edit_spec.compile_prompt(
        "volc", edit_spec.normalize(
            {"change": {"person": True, "person_ids": ["P1", "P2"]},
             "audio": "tts"}),
        model="doubao-seedance-2-5-260628", slots=["person", "person2"],
        audio_ref=True,
        shot_lines=[[{"start": 0.4, "end": 1.8, "text": "我走了",
                      "lang": "zh", "speaker": ""}]])
    check("2.5 判不出说话人 → 不并列两个人物",
          "@图片1中的人物、@图片2中的人物" in _t25_unk, False)
    check("2.5 判不出说话人 → 不写开头统一声明", "说以下台词" in _t25_unk, False)
    check("2.5 判不出说话人 → 台词仍以 {} 写出", "{我走了}" in _t25_unk, True)
    check("2.5 判不出说话人 → 不写闭口聆听", "自然闭口聆听" in _t25_unk, False)
    # 🧨 2026-10-28（全量穷举产物逐份读）：以前这里断言的是
    #   「退到『音色与台词』」—— 那句实际是把官方槽位留空了
    #   （`sd25-pe:626` 是 `@音频1用于<目标说话人**或声音类别**>的<…>`），
    #   `:324` 要求所有占位符必须换成具体内容。
    #   正解 = 退到官方给的另一个选项「说话人」。
    check("2.5 判不出说话人 → 音频职责句退到「说话人」",
          "@音频1用于说话人的音色与台词" in _t25_unk, True)

    # 成对的另一半：画面里只有一个人时，他本来就该是说话人，必须照常点名
    # （别把上面那条修过头，把单人片也写成裸台词）
    _t25_one = edit_spec.compile_prompt(
        "volc", edit_spec.normalize(
            {"change": {"person": True, "person_ids": ["P1"]}, "audio": "tts"}),
        model="doubao-seedance-2-5-260628", slots=["person"],
        audio_ref=True,
        shot_lines=[[{"start": 0.4, "end": 1.8, "text": "我走了",
                      "lang": "zh", "speaker": ""}]])
    check("2.5 单人 + 没标说话人 → 仍然点名",
          "@图片1中的人物说{我走了}" in _t25_one, True)
    _p25cut = edit_spec.compile_prompt("volc", p, model="doubao-seedance-2-5-pro",
                                       shot_cuts=[3.0])
    # 🩸 2026-10-28：官方词是「剪切点与转场」「转场风格」（`sd25-guide:828`），
    #   以前锁的是缩写「切点切镜」。
    check("2.5 不受影响（切点走官方整秒模板）",
          "编辑范围为@视频1的每一个镜头" not in _p25cut
          and "按@视频1原有的剪切点与转场切镜" in _p25cut, True)

    keep_part = edit_spec.normalize({"person": True, "keep": {"camera": False}})
    # D3：2.5 也必须**音轨真的发出去**（audio_ref=True）才写口型句
    kp25 = edit_spec.compile_prompt("volc", keep_part, model="seedance-2-5",
                                    audio_ref=True)
    check("2.5 有音轨 → 要求重做口型", "口型" in kp25, True)
    # 重做口型时不能连"表情"一起保（保了等于让模型照搬原片口型）
    check("2.5 有音轨 → 不保表情", "人物动作和表情" not in kp25, True)
    kp25_na = edit_spec.compile_prompt("volc", keep_part, model="seedance-2-5")
    check("2.5 无音轨 → 不要求重做口型", "口型" not in kp25_na, True)
    # 🩸 2026-10-26 18:xx（2.5 逐一过官方 · 功能 5）：这条以前断言「保留表情」，
    # 那是产品自加的语义；官方 `sd25-pe:572-573` 的【时间线继承】第二行是
    # **固定模板文本**，逐字为「其他人物动作、镜头运动、镜头切换和事件顺序
    # 保持@视频1」——没有「表情」，最后一项用「和」。按官方原文改判据。
    # 注意 `keep_part` 里 camera 是关的 —— 断官方原句要用 keep 全开的形状
    _tl_all = edit_spec.compile_prompt(
        "volc", edit_spec.normalize({"person": True}), model="seedance-2-5")
    check("2.5 无音轨 → 时间线继承第二行逐字照官方模板",
          "其他人物动作、镜头运动、镜头切换和事件顺序保持@视频1。" in _tl_all, True)
    check("2.5 任何模式都不许自己加「表情」到保留句",
          all("表情" not in x for x in (kp25, kp25_na)), True)

    v_p = edit_spec.normalize({"person": True, "audio": "tts"})
    v25_aoff = edit_spec.compile_prompt("volc", v_p, model="seedance-2-5")
    v25_aon = edit_spec.compile_prompt("volc", v_p, model="seedance-2-5",
                                       audio_ref=True)
    check("2.5 不传音频就不写 @音频1", "@音频1" in v25_aoff, False)
    check("2.5 传了音频才写 @音频1", "@音频1" in v25_aon, True)
    # 🩸 2026-10-28：原判据锁的是我自造的「口型与@音频1逐字同步」；官方原话是
    #   `sd25-guide:929`「口型做出对应的精准改变」+ `:916`「口型与台词精准同步」。
    check("2.5 要求口型同步", "口型做出对应的精准改变" in v25_aon, True)
    # 换人 + 音频时，两条都要在（别把换人句挤掉）
    check("火山换人句仍在（官方原句「替换为@图片1中的人物」）",
          "@图片1中的人物" in v25_aon, True)

    # 官方两个 skill 在"兜底包"上口径相反：
    #   sd2-pe  强制约束：最终输出必须包含稳定包 + 水印/Logo 兜底
    #   sd25-pe 原则 8：不得自动添加用户未要求的画质包/稳定包/水印/Logo/字幕
    v25 = edit_spec.compile_prompt("volc", p, model="doubao-seedance-2-5-260628")
    check("2.5 不自动加兜底包", "不要生成水印" not in v25, True)
    check("2.5 也不挂画质包", "电影质感" not in v25, True)
    check("2.5 不挂字幕兜底（原则 8 不滥加约束）", "保持无字幕" not in v25, True)

    print("== 火山 2.5 编辑句式 ==")
    # 2.5 必须套官方五段模板（sd25-pe:71 原则 2「模板优先」），
    # 编辑句落在【编辑目标】段里，不再是裸开头。
    check("2.5 以【编辑目标】开头", v25.startswith("【编辑目标】"), True)
    check("2.5 编辑句在【编辑目标】段里",
          "编辑@视频1，" in v25.split("【原视频职责】")[0], True)
    check("2.5 有五段模板", all(k in v25 for k in (
        "【编辑目标】", "【原视频职责】", "【目标素材职责】",
        "【编辑对象与范围】", "【时间线继承】")), True)
    check("2.5 含编辑意图词",
          any(k in v25 for k in ("编辑视频", "增加", "加上", "删除", "去掉",
                                 "修改", "替换", "改成")), True)
    only_extra = edit_spec.normalize({"extra": "画面更亮一点"})
    oe = edit_spec.compile_prompt("volc", only_extra, model="doubao-seedance-2-5-260628")
    check("只写补充说明也带编辑意图词", "编辑视频" in oe, True)
    check("不会出现「编辑编辑」", "编辑编辑" in oe, False)
    check("2.5 不会出现连写句号", "。。" in v25 + oe, False)

    print("== 参考图外观描述（火山 2.5 不写）==")
    look = {"zh": "长黑发、蓝色开衫、细银项链",
            "en": "long dark hair, a blue cardigan, a thin silver necklace"}
    p25_yes = edit_spec.compile_prompt("volc", only_face, model="seedance-2-5",
                                       subject_look=look)
    check("火山 2.5 不写特征", look["zh"] not in p25_yes, True)

    print("== 台词语言标签（2.5）==")
    th_lines = [[{"start": 0.2, "end": 1.0, "text": "สวัสดีครับ", "lang": "th"}]]
    v25_th = edit_spec.compile_prompt("volc", only_face, model="seedance-2-5",
                                      slots=["person"], source_people=[p1],
                                      audio_ref=True, shot_cuts=[], shot_lines=th_lines)
    check("2.5：泰语台词写「用泰语说道」", "用泰语说道{สวัสดีครับ}" in v25_th, True)

    print("== 换人提示词结构（2.5）==")
    src_face = {"id": "P1", "desc_zh": "棕色盘发、身穿浅灰长裙的女性",
                "desc_en": "the woman in a grey dress"}
    p25 = edit_spec.compile_prompt("volc", only_face, model="seedance-2-5",
                                   source_person=src_face)
    check("2.5 不挂负向", "不要恢复原片人物的脸" in p25, False)

    # ------------------------------------------------------------------
    # 参考段帧数卡 8n+1（**2.5 编辑任务专属**，2.0 不要这条）
    # 官方《Seedance 2.5 提示词指南》`:696-703`「编辑前后时长不一致」：
    #   编辑任务的输出比原视频**短约 0.33 秒**；解法「将输入视频的帧数调整为
    #   **8n+1**（n 为正整数），输出时长即可与原视频保持一致」。
    # 实现在 `video_edit._align_8n1`，只有 `caps.align_8n1=True` 的型号才走。
    # 🩸 为什么这条以前没有门：算错了模型少吐的几帧会被 `_normalize` 裁掉/冻帧补上，
    #   **成片帧数合同照样达标** → `qc` 那一道门看不见它。
    # ------------------------------------------------------------------
    print("== 参考段 8n+1（2.5 编辑任务）==")
    from app.services import video_edit  # noqa: E402

    _fk = [video_edit._align_8n1(s, 30.0) for s in (4.0, 6.0, 7.5, 10.0, 30.0)]
    check("每个结果都满足 8n+1", [f % 8 for f in _fk], [1, 1, 1, 1, 1])
    check("和原始帧数差不超过 4 帧（30fps 约 0.13 秒）",
          max(abs(f - round(s * 30)) for f, s in zip(_fk, (4.0, 6.0, 7.5, 10.0, 30.0)))
          <= 4, True)
    # 成对反证：不卡 8n+1 的写法（四舍五入到整帧）**不满足**这条判据 ——
    # 证明上面那条不是恒真（6.0s@30fps = 180 帧，180 % 8 = 4）。
    check("反证：直接取整帧不满足 8n+1", round(6.0 * 30) % 8 == 1, False)
    # 边界：坏输入返回 0，不抛错
    check("fps/秒数为 0 或负数 → 返回 0",
          (video_edit._align_8n1(0, 30.0), video_edit._align_8n1(6.0, 0),
           video_edit._align_8n1(-1, 30.0)), (0, 0, 0))
    # 型号隔离：这条只给 2.5（2.0 的输出是整数秒，本来就没有"短 0.33 秒"这回事，
    # 给它打开反而会改段长）。**别家的 caps 断言不写在这个文件里**（台账 D43）：
    # 2.0 侧要不要加"不开 align_8n1"，等 2.0 轮在它自己的文件里加。
    from app.services import models  # noqa: E402
    check("2.5 打开 align_8n1",
          models.adapter_for(model="doubao-seedance-2-5-260628").caps.align_8n1, True)

    # ------------------------------------------------------------------
    # 人物槽位按「首次出场顺序」排（2.5 专属能力开关）
    # 官方《Doubao Seedance 2.5 提示词指南》「角色对应错误」
    # （`pull-2026-11-03/prompt-guide.md:429`）：
    #   「多人物视频中，角色与参考图片、音色或出场顺序发生错位……按人物
    #    **首次出场顺序**上传参考素材，并同步调整提示词中的图片、音频编号」。
    # 实现在 `video_edit.order_persons_by_appearance`，只有
    # `caps.order_by_appearance=True` 的型号才走。
    # ------------------------------------------------------------------
    print("== 人物按首次出场顺序排（2.5 编辑任务）==")
    from pathlib import Path as _P  # noqa: E402

    def _inv(p1_start: float, p2_start: float) -> dict:
        return {"people": [
            {"id": "P1", "position": "left",
             "appearances": [{"start": p1_start, "end": 9.0}]},
            {"id": "P2", "position": "right",
             "appearances": [{"start": p2_start, "end": 9.0}]},
        ]}

    _spec = edit_spec.normalize({"person": True, "person_ids": ["P1", "P2"]})
    _refs = {"person": _P("p1.jpg"), "person2": _P("p2.jpg")}

    # ① 勾选顺序和出场顺序相反 → 必须重排，**图跟着人走**
    _s2, _r2, _mv = video_edit.order_persons_by_appearance(
        _spec, _refs, _inv(5.0, 1.0))
    check("反序 → 重排成出场顺序", _s2["change"]["person_ids"], ["P2", "P1"])
    check("图跟着人走（P1 的图到第 2 槽）", str(_r2["person2"]), "p1.jpg")
    check("换位数 = 2", _mv, 2)

    # ② 本来就是对序 → 原样返回，不动
    _s3, _r3, _mv3 = video_edit.order_persons_by_appearance(
        _spec, _refs, _inv(1.0, 5.0))
    check("已是对序 → 不重排", (_mv3, _s3["change"]["person_ids"]), (0, ["P1", "P2"]))

    # ③ 带 asset://（火山真人素材）→ 不重排（ref_plan 只认 person 槽，
    #    重排会把素材绑到别人身上）
    _s4, _r4, _mv4 = video_edit.order_persons_by_appearance(
        _spec, _refs, _inv(5.0, 1.0), subject_asset="asset-123")
    check("带 asset → 不重排", (_mv4, _s4["change"]["person_ids"]), (0, ["P1", "P2"]))

    # ④ 盘点没有出场时间 → 不猜，保持原顺序
    _none = {"people": [{"id": "P1"}, {"id": "P2"}]}
    _s5, _r5, _mv5 = video_edit.order_persons_by_appearance(_spec, _refs, _none)
    check("没有出场时间 → 不猜", (_mv5, _s5["change"]["person_ids"]), (0, ["P1", "P2"]))

    # ⑤ 成对反证：不重排时 P2 的图仍在第 2 槽 —— 证明「图跟着人走」不是恒真
    check("反证：不重排时槽位没动",
          (str(_r5.get("person")), str(_r5.get("person2"))), ("p1.jpg", "p2.jpg"))

    check("2.5 打开 order_by_appearance",
          models.adapter_for(model="doubao-seedance-2-5-260628")
          .caps.order_by_appearance, True)

    # ------------------------------------------------------------------
    # 「一次只改一类」（默认关）—— 官方 2.5 指南「复杂任务效果不稳定」
    # （`pull-2026-11-03/prompt-guide.md:738`）：一次承担多项参考/编辑要求 =
    # 效果不稳定，要拆成多个简单任务。**这是用户开关，不是默认行为**。
    # ------------------------------------------------------------------
    print("== 一次只改一类（默认关）==")
    check("默认关", edit_spec.defaults()["one_change"], False)
    check("normalize 保留开关",
          edit_spec.normalize({"person": True, "one_change": True})["one_change"], True)
    check("分类：人物+场景", edit_spec.change_categories(
        edit_spec.normalize({"person": True, "scene": True})), ["person", "scene"])
    check("风格参考图也算「风格」", edit_spec.change_categories(
        edit_spec.normalize({"style_ref": True})), ["style"])
    # 🩸 `normalize` 只在 `wardrobe=True` 时才保留名单（`edit_spec.py:275`），
    # 光给 `wardrobe_ids` 会被清空 —— 断言要按前端真正发出来的形状喂。
    check("换装名单也算「服装」", edit_spec.change_categories(
        edit_spec.normalize({"wardrobe": True, "wardrobe_ids": ["P1"]})), ["wardrobe"])

    def _raise_kind(raw):
        """返回 'ok' 或 'EditError'，用来成对验鉴别力。"""
        try:
            video_edit.check_one_change(edit_spec.normalize(raw))
            return "ok"
        except video_edit.EditError:
            return "EditError"

    check("开关关 → 同时改两类也放行", _raise_kind(
        {"person": True, "scene": True}), "ok")
    check("开关开 + 只改一类 → 放行", _raise_kind(
        {"person": True, "one_change": True}), "ok")
    check("开关开 + 改两类 → 拦下", _raise_kind(
        {"person": True, "scene": True, "one_change": True}), "EditError")

    # ------------------------------------------------------------------
    # 2026-10-28（2.5 轮，当前产出实测抓到）：**只换装不换人**时，
    # 【编辑目标】和【目标素材职责】两条都没有主人称谓 ——
    #   「只把的服装换成@图片1中的服装」（中心词为空 → 病句）
    #   「只把男性的服装换成@图片1…；只把男性的服装换成@图片2…」（两句一字不差）
    # 修法：`edit_spec._sd25_wardrobe_subject` 三档（方位唯一 → 外观特征 →
    # 补类名词），全部取 2.5 自己的材料（`sd25-guide:193` 方位指认、
    # `sd25-guide:1203-1209` 用画面看得见的外观当称谓、`sd25-pe:224` 逐条绑定）。
    # ------------------------------------------------------------------
    print("== 只换装两人（2.5 的宾语指认）==")
    _W_PPL = [
        {"id": "P1", "present": True, "position": "left",
         "desc_zh": "穿豆绿色露肩短款连衣裙的东亚女性"},
        {"id": "P2", "present": True, "position": "right",
         "desc_zh": "穿白色西装套装的老年男性"},
    ]
    _W_SPEC = edit_spec.normalize({
        "wardrobe": True, "wardrobe_ids": ["P1", "P2"],
        "wardrobe_desc_by_id": {"P1": "米色风衣", "P2": "深蓝夹克"}})
    _wv = edit_spec.compile_prompt(
        "volc", _W_SPEC, model="doubao-seedance-2-5-260628",
        source_people=_W_PPL, frame_people=_W_PPL,
        slots=["wardrobe", "wardrobe2"],
        desc_by_id={"P1": {"zh": _W_PPL[0]["desc_zh"]},
                    "P2": {"zh": _W_PPL[1]["desc_zh"]}})
    _duty = [x for x in _wv.splitlines() if x.startswith("@图片") and "用于" in x]
    check("两条服装职责行都点名了主人", len(_duty), 2)
    check("两条职责行不相同（逐条绑定）", _duty[0] != _duty[1], True)
    check("职责行写的是主人的称谓，不是裸「目标服装」",
          all("目标服装" not in x for x in _duty), True)
    check("编辑目标用方位指认（sd25-guide:193）",
          "只把画面左侧的人物的服装替换为@图片1中的服装" in _wv, True)
    # 🩸 2.5 的编辑动词跟**正式示例**走：`sd25-guide:1209`（唯一换装示例）
    #   「…的服饰**替换为** @图片2」+ `sd25-pe:584`（模板已填示例）「…**替换为**…」。
    #   「换成」零示例（`sd25-guide:88` 里那 5 处「换成」全是「转换成/替换成/换成具象描述」，
    #   没有一处是编辑动词），所以判红。
    check("编辑动词用「替换为」，不用「换成」",
          ("替换为" in _wv and "换成" not in _wv), True)

    # 盘点描述没有「…的男性/的女子」这类中心词时，按 2.5 口径补类名词，
    # 不许留成「只把服装替换为…」的残句（真实盘点 `7536fdb5` P1）。
    _N_PPL = [
        {"id": "P1", "present": True, "position": "center",
         "desc_zh": "穿橙色连帽拉链外套，左胸带有白色标识，短发"},
        {"id": "P2", "present": True, "position": "center",
         "desc_zh": "穿黑色短袖上衣，寸头发型，耳部佩戴耳钉"},
    ]
    _nv = edit_spec.compile_prompt(
        "volc", edit_spec.normalize({
            "wardrobe": True, "wardrobe_ids": ["P1", "P2"],
            "wardrobe_desc_by_id": {"P1": "米色风衣", "P2": "深蓝夹克"}}),
        model="doubao-seedance-2-5-260628",
        source_people=_N_PPL, frame_people=_N_PPL,
        slots=["wardrobe", "wardrobe2"],
        desc_by_id={"P1": {"zh": _N_PPL[0]["desc_zh"]},
                    "P2": {"zh": _N_PPL[1]["desc_zh"]}})
    # 取到几个特征由 `_split_feats` 决定（它会把末段没有「的X」中心词的那半句
    # 丢掉，这是共用行为）；这里只锁"必须有一个能指认的短语 + 类名词"。
    check("方位撞车 + 描述没有中心词 → 仍能指认（补类名词）",
          re.search(r"只把左胸带有白色标识[^，；]*?的人物的服装替换为@图片1中的服装",
                    _nv) is not None, True)
    check("两人不再共用一个宾语", "只把服装替换为" not in _nv, True)

    # 🩸 2026-10-28（2.5 全量穷举 E8）：`<>` 是音效标记、`{}` 是台词标记
    #   （`sd25-pe:872` / `:867`），官方 `:880`「同一符号不能承担两种职责」。
    #   用户在产品名 / 补充说明里写这些符号时，必须从自由文本里清掉，
    #   否则模型会照着念产品名、或把补充说明当音效。
    _free = edit_spec.compile_prompt(
        "volc", edit_spec.normalize({
            "person": True, "person_ids": ["P1"], "product": True,
            "product_target": "杯子{大}<红>（限量）",
            "extra": "把{招牌}改成<木牌>"}),
        model="doubao-seedance-2-5-260628",
        source_people=_N_PPL[:1], frame_people=_N_PPL[:1],
        slots=["person", "product"], desc_by_id={})
    check("产品名里的 {} / <> 不落进提示词", re.search(r"[{}<>]", _free) is None,
          True)
    check("补充说明里的 {} / <> 也不落", "改成木牌" in _free, True)
    _ml = edit_spec.compile_prompt(
        "volc", edit_spec.normalize({
            "person": True, "person_ids": ["P1"], "extra": "第一行\n第二行"}),
        model="doubao-seedance-2-5-260628",
        source_people=_N_PPL[:1], frame_people=_N_PPL[:1],
        slots=["person"], desc_by_id={})
    check("补充说明换行不切断段落", "\n" not in _ml.split("【编辑目标】")[1]
          .split("【")[0].strip(), True)

    # 🩸🩸 2026-10-28（2.5 官方 `:243`「同一主体的多份参考互相冲突时，**先服从用户指定**」）：
    #   同时勾换人和换装时，服装归服装图（用户指定）管；人物图再说自己"用于…服装"
    #   = 同一个属性两个来源，模型只能自己猜一个。
    #   实测形状：`@图片1用于目标人物的五官、发型和服装` + `@图片2用于目标服装的款式…`
    #   570 组穷举里命中 **96 组**（2.5 这一轮规模最大的一条）。判据 = `ruler_sd25.P6`。
    _pw = edit_spec.compile_prompt(
        "volc", edit_spec.normalize({
            "person": True, "person_ids": ["P1"],
            "wardrobe": True, "wardrobe_ids": ["P1"],
            "wardrobe_desc_by_id": {"P1": "米色风衣"}}),
        model="doubao-seedance-2-5-260628",
        source_people=_N_PPL[:1], frame_people=_N_PPL[:1],
        slots=["person", "wardrobe"], desc_by_id={})
    check("换人+换装：人物职责行不再声称管服装",
          "目标人物的五官和发型" in _pw and "五官、发型和服装" not in _pw, True)
    # 🩸 成对：**没有**服装槽时必须继续全包（`sd25-pe:227`「只采用五官、发型和服装」）——
    #   否则就是把"消除冲突"做成"一律砍掉服装"，换人时衣服跟着乱变。
    _p0 = edit_spec.compile_prompt(
        "volc", edit_spec.normalize({"person": True, "person_ids": ["P1"]}),
        model="doubao-seedance-2-5-260628",
        source_people=_N_PPL[:1], frame_people=_N_PPL[:1],
        slots=["person"], desc_by_id={})
    check("只有人物图时仍写全属性（不是一刀切砍掉服装）",
          "五官、发型和服装" in _p0, True)

    # 🩸🩸 2026-10-28（`sd25-guide:278`「prompt 避免前后矛盾」）：
    #   2.5 官方语料里「风格」本来就含光影色调 —— `sd25-pe:813` 把「光线」和
    #   「视觉风格」并列同一组，`sd25-guide:665`「…水墨仙气光影」、`sd25-guide:1144`
    #   「整体像素武侠美术风格，色调统一浅蓝底」。
    #   ⇒「只把整体画面风格改成动漫」配「不修改…光线和色调」直接打架。
    #   三种风格来源都要管：素材图 / 素材视频 / 纯文字枚举。判据 = `ruler_sd25.P5`。
    for _k, _cv in (("纯文字风格", {"style": "anime"}),
                    ("风格参考图", {"style_ref": True}),
                    ("风格参考视频", {"style_video": True})):
        _sc = edit_spec.compile_prompt(
            "volc", edit_spec.normalize(dict({"person": True,
                                              "person_ids": ["P1"]}, **_cv)),
            model="doubao-seedance-2-5-260628",
            source_people=_N_PPL[:1], frame_people=_N_PPL[:1],
            slots=["person"], desc_by_id={}, style_video=True)
        check(f"{_k}：保持清单里不出现「光线」",
              "光线" not in _sc, True)
    # 🩸 成对：**不改风格**时必须照写「光线和色调」—— 否则就是把矛盾判据
    #   做成"永远不写光线"，改背景/改服装时画面色彩没人管了。
    check("不改风格时仍写「光线和色调」", "光线和色调" in _p0, True)

    # 🩸🩸 2026-10-28：字母表原来写死 `'ABCDEFGH'`（8 个），但 `PERSON_SLOTS`
    #   有 **16** 个槽位 —— 勾到第 9 个人直接 `IndexError`，整单 500 崩掉。
    #   这是崩溃级，不是提示词质量问题，穷举矩阵（最多 5 人）从来没碰到。
    for _n in (8, 9, 16):
        _ppl = [{"id": f"P{i+1}", "present": True,
                 "desc_zh": f"第{i+1}号人物穿的独特服装", "desc_en": f"p{i+1}",
                 "position": "left",          # 方位全撞车 → 必须走字母退路
                 "appearances": [{"start": 0.0, "end": 5.0}]}
                for i in range(_n)]
        _sl = list(edit_spec.PERSON_SLOTS[:_n])
        _sp = edit_spec.normalize({(f"person{i+1}" if i else "person"): True
                                   for i in range(_n)})
        try:
            _t = edit_spec.compile_prompt(
                "volc", _sp, model="doubao-seedance-2-5-260628", slots=_sl,
                source_people=_ppl,
                desc_by_id={p["id"]: {"zh": p["desc_zh"], "en": p["desc_en"]}
                            for p in _ppl})
            # 🩸 2026-10-28：只数【目标素材职责】段里的行。
            #   以前按「全文以 @图片 开头的行」数 —— 那时【时间线继承】只有一句
            #   泛指的「目标人物继承…」，不占 @图片。现在多人按官方 `:576` 模板
            #   写成 `<目标对象>继承<原对象>`，目标对象就是 `@图片N中的人物`
            #   （`:578`「主体替换时说明**原对象和目标对象**」），
            #   于是继承段也有 @图片 开头的行，把职责行计数撑成 2n。
            #   判据要的是「每个换的人都有职责行」，段一限定就准确了。
            _duty_sec = _t.split("【目标素材职责】")[1].split("【")[0]
            _rows = [x for x in _duty_sec.splitlines() if x.startswith("@图片")]
            check(f"{_n} 人同框（方位全撞车）不崩且职责行齐全",
                  len(_rows) == _n, True)
        except IndexError as e:
            check(f"{_n} 人同框（方位全撞车）不崩", f"IndexError: {e}", "不崩")
    # 字母必须两两不同（A…P 共 16 个），否则又回到"多条职责行逐字相同"
    _letters = [_t.splitlines()[i] for i in range(len(_t.splitlines()))
                if _t.splitlines()[i].startswith("@图片")]
    _who = [re.search(r"用于(目标人物.)的", x).group(1)
            for x in _letters if re.search(r"用于(目标人物.)的", x)]
    check("16 人的区分字母两两不同", len(set(_who)) == len(_who), True)

    # 🩸🩸 2026-10-28（官方 `sd25-pe:709-717`）：**首帧图也是一份素材**。
    #   原来它只在【时间线继承】出现，【目标素材职责】段根本没有它 —— 违反
    #   `:73`「素材逐份负责」，尺子 T5 判红「@图片N 没有职责行」。
    #   生产可达：分段相邻时 `video_edit.py:1935` 一定传 `boundary_pic`
    #   （`caps.boundary_pic = True`）—— 570 组穷举从没传过，所以一直没红。
    _bf = edit_spec.compile_prompt(
        "volc", edit_spec.normalize({"person": True, "person_ids": ["P1"]}),
        model="doubao-seedance-2-5-260628", slots=["person"],
        source_people=_N_PPL[:1], frame_people=_N_PPL[:1], desc_by_id={},
        boundary_pic=2)
    _bsec = _bf.split("【目标素材职责】")[1].split("【")[0]
    check("首帧图在【目标素材职责】里有自己那行",
          "@图片2作为首帧" in _bsec, True)
    check("其它参考图带「不改变@图片2定义的首帧构图」",
          "不改变@图片2定义的首帧构图" in _bsec, True)
    check("[时间线继承]写「画面从@图片2定义的首帧自然开始」",
          "画面从@图片2定义的首帧自然开始" in _bf, True)
    check("首帧句不在两段里重复", _bf.count("@图片2作为首帧"), 1)

    # 🩸🩸 2026-10-28：勾了换装但**没点名具体谁**（老客户端不传 `wardrobe_ids`，
    #   或 id 不在盘点里）时走的是 `_clauses` 的另一条兜底分支，它一直硬编码
    #   「换成」。2.5 的整句就**不含任何官方示例动词**（正式示例 5/5 = 「替换为」，
    #   见 `sd25-guide:1209` / `sd25-pe:584`）。点名那一支早就按型号分了，
    #   只有这条兜底漏着。穷举夹具总会自动填 `wardrobe_ids`，所以这形状
    #   从来没人走过 → E5 补用例。
    _wn = edit_spec.compile_prompt(
        "volc", edit_spec.normalize({"wardrobe": True}),
        model="doubao-seedance-2-5-260628", slots=["wardrobe"],
        source_people=_N_PPL[:1], frame_people=_N_PPL[:1], desc_by_id={})
    check("换装不点名时也用「替换为」不用「换成」",
          "替换为" in _wn and "换成" not in _wn, True)
    _wnd = edit_spec.compile_prompt(
        "volc", edit_spec.normalize({"wardrobe": True, "wardrobe_desc": "米色风衣"}),
        model="doubao-seedance-2-5-260628", slots=["wardrobe"],
        source_people=_N_PPL[:1], frame_people=_N_PPL[:1], desc_by_id={})
    check("换装不点名 + 有描述：动词仍是「替换为」",
          "替换为" in _wnd and "换成" not in _wnd, True)

    # ================= 英文任务全链路（2026-10-28）=================
    # 之前所有用例都是中文场景。官方 `:869` 的台词格式是
    # 「语言 + 可选的地区变体或口音 + 表达方式 + 说话人 + {台词}」，
    # `:876` 又要求「至少明确写"使用英语"」——英文任务走的是同一条模板。
    _en1 = [{"id": "P1", "present": True, "desc_zh": "白衬衫男人"}]
    _en2 = _en1 + [{"id": "P2", "present": True, "desc_zh": "黑衣服女人"}]

    def _en(people, slots, lines, extra=""):
        ch = {"person": True, "person_ids": [p["id"] for p in people],
              "audio": "tts"}
        spec = {"change": ch}
        if extra:
            # `extra` 在规格**顶层**（`spec["extra"]`），不在 `change` 里
            spec["extra"] = extra
        return edit_spec.compile_prompt(
            "volc", edit_spec.normalize(spec),
            model="doubao-seedance-2-5-260628", slots=slots,
            source_people=people, frame_people=people, audio_ref=True,
            shot_lines=lines)

    _e1 = _en(_en1, ["person"],
              [[{"start": 0.5, "end": 2.0, "text": "I am leaving now.",
                 "lang": "en"}]])
    check("英文台词带「使用英语说道」",
          "使用英语说道{I am leaving now.}" in _e1, True)
    # 双人逐句分说话人：`sd25-pe:876`「多名说话人分别标注」
    _e2 = _en(_en2, ["person", "person2"],
              [[{"start": 0.5, "end": 2.0, "text": "Where are you going?",
                 "lang": "en", "speaker": "P2"},
                {"start": 2.5, "end": 4.0, "text": "Far away.",
                 "lang": "en", "speaker": "P1"}]])
    check("双人英文台词逐句分说话人",
          ("@图片2中的人物使用英语说道{Where are you going?}" in _e2
           and "@图片1中的人物使用英语说道{Far away.}" in _e2), True)
    # 中英混杂：一句一个语种，不能整段套同一个
    _e3 = _en(_en1, ["person"],
              [[{"start": 0.5, "end": 1.8, "text": "先走一步", "lang": "zh"},
                {"start": 2.0, "end": 3.4, "text": "See you tomorrow",
                 "lang": "en"}]])
    check("中英混杂逐句判语言",
          ("@图片1中的人物说{先走一步}" in _e3
           and "使用英语说道{See you tomorrow}" in _e3), True)
    # 未知语种：退回「说」而不是编一个语言名
    _e4 = _en(_en1, ["person"],
              [[{"start": 0.5, "end": 2.0, "text": "Bonjour", "lang": "xx"}]])
    check("未知语种不编语言名", "@图片1中的人物说{Bonjour}" in _e4, True)
    # 🩸 `{}` 是台词标记（`:867`），内容里再有就是嵌套 —— `:880`「同一符号
    #   不能承担两种含义」。实测 `He said "run" {twice}` 会产出
    #   `{He said "run" {twice}}`，模型不知道台词在哪结束。
    _e5 = _en(_en1, ["person"],
              [[{"start": 0.5, "end": 2.0, "text": 'He said "run" {twice}',
                 "lang": "en"}]])
    check("台词里的花括号被清掉（不嵌套）",
          '{He said "run" twice}' in _e5 and "{" not in
          _e5.split('{He said "run" twice}')[1].split("}")[0], True)
    check("整段只剩一对台词花括号", _e5.count("{"), _e5.count("}"))
    # 英文补充说明：原样进【编辑目标】，且不破坏五段结构
    _e6 = _en(_en1, ["person"], None,
              extra="make the light warmer and add a gentle breeze")
    check("英文补充说明原样进入正文",
          "make the light warmer and add a gentle breeze" in _e6, True)
    check("加了英文补充说明后五段仍在",
          all(s in _e6 for s in ("【编辑目标】", "【原视频职责】",
                                 "【目标素材职责】", "【编辑对象与范围】",
                                 "【时间线继承】")), True)

    # 🩸🩸 2026-10-28：用户已经要求改光线，就不能再写「不修改…光线和色调」
    #   —— `sd25-pe:599`「**保持清单只写与目标邻接、确实不能变化的区域**，
    #   避免过长清单稀释编辑目标」+ `sd25-guide:278`「prompt 避免前后矛盾」。
    #   代码里本来就有这个逻辑（风格素材会跳过 `lighting`），
    #   只是**用户手写的那句话一直没参与判断**。
    def _keep_line(t: str) -> str:
        return next((x for x in t.split("\n") if "不修改" in x), "")

    _k1 = _en(_en1, ["person"], None, extra="make the light warmer")
    check("英文要求改光线 → 保持句里不再有「光线和色调」",
          "光线和色调" not in _keep_line(_k1), True)
    check("拿掉光线后保持句仍在（背景/构图没丢）",
          "背景环境" in _keep_line(_k1) and "构图和景别" in _keep_line(_k1), True)
    _k2 = _en(_en1, ["person"], None, extra="把光线调亮")
    check("中文（含口语「更亮一些」）同样生效",
          "光线和色调" not in _keep_line(_k2), True)
    # 成对：否定式是"不要改"，保持句必须留着 —— 判反了等于把保护拿掉
    _k3 = _en(_en1, ["person"], None, extra="不要改光线，保持原样")
    check("否定式「不要改光线」仍写保持句",
          "光线和色调" in _keep_line(_k3), True)
    _k4 = _en(_en1, ["person"], None, extra="她穿了一件漂亮的裙子")
    check("无关文本不会误伤（「漂亮」不含光线意图）",
          "光线和色调" in _keep_line(_k4), True)

    # 🩸🩸 2026-10-28（E12 用户补充说明矩阵）：`extra` 是唯一一段**不经开关、
    #   用户写什么就原样拼进正文**的文本，落点是【编辑目标】正句尾。以下四条
    #   都是穷举新产出时抓到的真实形态，不是设想。
    #
    # ① `【】` 双重身份：官方 `:867` 表里是**字幕**标记，我们模板 `:559-576`
    #    又用它当**段标题**（`:880`「同一符号不能承担两种职责」）。用户写
    #    「【原视频职责】」实测会伪造出一个同名段，`_sec()` 先命中伪造的那个
    #    → 真段被跳过 → 官方要求的「唯一编辑母版」判不出来。
    _x1 = _en(_en1, ["person"], None,
              extra="加一只猫。\n【原视频职责】\n这段是乱写的。")
    check("补充说明里的【】被清掉（不伪造段标题）",
          _x1.count("【原视频职责】"), 1)
    check("伪造段标题的字样不会残留方括号", "【这段" not in _x1, True)
    # ② 引号台词：`sd25-pe:141`「用户只给出带引号的台词片段…只把该片段作为
    #    **可说出的原文**」+ `:867` 表「台词 = `{}`」⇒ 引号片段必须换成 `{}`，
    #    裸引号在最终 Prompt 里没有职责，模型会漏念。
    _x2 = _en(_en1, ["person"], None, extra='He said "run" loudly')
    check("补充说明里的引号台词换成 {}", "He said {run} loudly" in _x2, True)
    _x3 = _en(_en1, ["person"], None, extra="他说“快跑”然后转身")
    check("中文弯引号同样换成 {}", "他说{快跑}然后转身" in _x3, True)
    #    🩸 只有**前面带说话标记**的引号才是台词（官方 `:869` 台词语法 =
    #    「…说话人 + {台词}」+ `:141`「带引号的**台词片段**」）。
    #    名词引用里的引号只去掉、不标台词 —— 否则「限时优惠」会被念出来。
    _x4 = _en(_en1, ["person"], None, extra='把标题改成"限时优惠"')
    check("非台词引号只去引号、不标台词",
          ("{限时优惠}" not in _x4 and "把标题改成限时优惠" in _x4), True)
    # ③ 用户自己打的花括号照样清（与引号转换不冲突：先清后转，不会套娃）
    _x5 = _en(_en1, ["person"], None, extra="加个{花括号}和<尖括号>")
    check("补充说明里手打的{}与<>都清掉",
          ("{花括号}" not in _x5 and "<尖括号>" not in _x5
           and _x5.count("{") == _x5.count("}")), True)
    # ④ 多行补充说明：换行折成逗号，但前一句已经以句末标点收口时不再补逗号
    #    （实测曾产出「加一只猫。，原视频职责」这种标点垃圾）。
    _x6 = _en(_en1, ["person"], None, extra="加一只猫。\n然后关灯。")
    check("换行后不出现「。，」连用", "。，" not in _x6, True)
    check("两句话都还在", ("加一只猫" in _x6 and "然后关灯" in _x6), True)

    # ⑤ 换装描述是**第二个**用户自由文本框（前端每人一个输入框），
    #    以前完全没清洗 —— 实测 `【原视频职责】乱写的内容` 会伪造段标题，
    #    多行那条甚至直接多出一个 `【编辑目标】` 行。
    def _wd(desc: str) -> str:
        ch = {"person": True, "person_ids": ["P1"], "wardrobe": True,
              "wardrobe_ids": ["P1"], "wardrobe_desc": desc,
              "wardrobe_desc_by_id": {"P1": desc}}
        return edit_spec.compile_prompt(
            "volc", edit_spec.normalize({"change": ch}),
            model="doubao-seedance-2-5-260628", slots=["person", "wardrobe"],
            source_people=_en1, frame_people=_en1)

    _w1 = _wd("【原视频职责】乱写的内容")
    check("换装描述里的【】被清掉（段标题只出现一次）",
          _w1.count("【原视频职责】"), 1)
    check("换装描述的内容还在", "乱写的内容" in _w1, True)
    _w2 = _wd("米色风衣\n【编辑目标】\n全部推翻")
    check("换装描述多行不伪造段", _w2.count("【编辑目标】"), 1)
    _w3 = _wd("<刺耳的钟声>米色风衣")
    check("换装描述里的<>被清掉", "<刺耳的钟声>" not in _w3, True)
    _w4 = _wd('"米色风衣"')
    check("换装描述里的引号被去掉（服装名不是台词）",
          ('"米色风衣"' not in _w4 and "米色风衣" in _w4), True)

    # ⑥ 还有三个**原文直填**的源：场景描述 / 产品目标 / 盘点人物描述。
    #    实测（`D:/tmp/clone_diag/probe25_inputs.py`、`probe25_desc2.py`）全部没清洗：
    #    场景和人物描述能伪造段标题，产品名的引号会被 P3 判成没包裹的台词。
    def _sc(desc: str) -> str:
        ch = {"person": True, "person_ids": ["P1"], "scene": True,
              "scene_desc": desc}
        return edit_spec.compile_prompt(
            "volc", edit_spec.normalize({"change": ch}),
            model="doubao-seedance-2-5-260628", slots=["person", "scene"],
            source_people=_en1, frame_people=_en1)

    _s1 = _sc("霓虹灯街道\n【编辑目标】\n全部推翻")
    check("场景描述多行不伪造段", _s1.count("【编辑目标】"), 1)
    _s2 = _sc("<钟声>空旷的教堂")
    check("场景描述里的<>被清掉", "<钟声>" not in _s2, True)
    _s3 = _sc("{霓虹灯街道}")
    check("场景描述里的{}被清掉", "{霓虹灯街道}" not in _s3, True)
    _s4 = _sc("霓虹灯街道，下着小雨")
    check("场景描述内容还在（清洗不许吃掉正文）", "下着小雨" in _s4, True)

    _p1 = edit_spec.compile_prompt(
        "volc", edit_spec.normalize({"change": {"product": True,
                                                "product_target": '桌上的"陶瓷杯"'}}),
        model="doubao-seedance-2-5-260628", slots=["product"],
        source_people=[], frame_people=_en1)
    check("产品目标里的引号被去掉", '桌上的"陶瓷杯"' not in _p1, True)
    check("产品目标内容还在", "陶瓷杯" in _p1, True)

    # 盘点描述：多人 + 方位撞车 → desc 就是【编辑目标】里的称谓
    _d2 = [{"id": "P1", "present": True, "position": "center",
            "desc_zh": "【编辑目标】穿白衬衫的男人",
            "appearances": [{"start": 0.0, "end": 5.0}]},
           {"id": "P2", "present": True, "position": "center",
            "desc_zh": "穿黑裙子的女人",
            "appearances": [{"start": 0.0, "end": 5.0}]}]
    _d3 = edit_spec.compile_prompt(
        "volc", edit_spec.normalize({"change": {"person": True,
                                                "person_ids": ["P1", "P2"]}}),
        model="doubao-seedance-2-5-260628", slots=["person", "person2"],
        source_people=_d2, frame_people=_d2,
        desc_by_id={"P1": {"zh": _d2[0]["desc_zh"], "en": ""},
                    "P2": {"zh": _d2[1]["desc_zh"], "en": ""}})
    check("盘点描述里的【】被清掉（段不重复）", _d3.count("【编辑目标】"), 1)
    check("盘点描述的内容还在", "穿白衬衫的男人" in _d3, True)

    # ⑦ 说话人未知时**不许指派给换了脸的那个人**。
    #    `video_edit._assign_speakers` 的口径：「两个证据都没有的句子不标，
    #    编译器退回**不指名**」；官方 `:982` 要求说话人与输入一致。
    #    🩸 以前判的是"换脸槽位数" —— 画面 2 人只换 1 个时它就是 1，
    #    于是未知说话人被静默挂到换脸的人嘴上（主角动嘴、配角的声音）。
    _spf = [{"id": "P1", "present": True, "position": "left",
             "desc_zh": "白衬衫男人", "appearances": [{"start": 0.0, "end": 5.0}]},
            {"id": "P2", "present": True, "position": "right",
             "desc_zh": "黑裙子女士", "appearances": [{"start": 0.0, "end": 5.0}]}]
    _spd = {x["id"]: {"zh": x["desc_zh"], "en": ""} for x in _spf}

    def _sp(picks, lines, on_screen=None):
        return edit_spec.compile_prompt(
            "volc", edit_spec.normalize({"change": {"person": True,
                                                    "person_ids": picks,
                                                    "audio": "tts"}}),
            model="doubao-seedance-2-5-260628",
            slots=["person"] + (["person2"] if len(picks) > 1 else []),
            source_people=[f for f in _spf if f["id"] in picks],
            frame_people=(on_screen if on_screen is not None else _spf),
            desc_by_id=_spd, audio_ref=True, shot_lines=lines)

    _ln_none = [[{"start": 0.5, "end": 2.0, "text": "旁白一句", "lang": "zh"}]]
    _ln_p2 = [[{"start": 0.5, "end": 2.0, "text": "别走", "lang": "zh",
                "speaker": "P2"}]]
    _ln_p9 = [[{"start": 0.5, "end": 2.0, "text": "我不存在", "lang": "zh",
                "speaker": "P9"}]]
    _v1 = _sp(["P1"], _ln_none)
    check("画面2人只换1个·说话人未知 → 台词不指名",
          ("@图片1中的人物说{旁白一句}" not in _v1 and "{旁白一句}" in _v1), True)
    _v2 = _sp(["P1"], _ln_none, on_screen=[_spf[0]])
    check("画面只有1人·说话人未知 → 仍用目标人物指代",
          "@图片1中的人物说{旁白一句}" in _v2, True)
    _v3 = _sp(["P1"], _ln_p2)
    check("说话人是没换的那个人 → 用 @视频1 里的外观指代",
          "@视频1中黑裙子女士说{别走}" in _v3, True)
    _v4 = _sp(["P1"], _ln_p9)
    check("说话人 ID 在盘点里不存在 → 不指名（不瞎认人）",
          ("@图片1中的人物说{我不存在}" not in _v4
           and "{我不存在}" in _v4), True)

    # ⑧ 2.5 单次最多 **30 张图**（`seedance-25-guide:116`「输入素材总上限：
    #    图片最多 30 张」），31 张必须在**花钱前**拦住。
    #    🩸 以前提示语无条件拼着「官方 2.0 系列是图 0-9」—— 2.5 的客户超 30 张时
    #    会看到「超出 30 张上限：官方 2.0 系列是图 0-9」，自相矛盾。
    _refs31 = {("person" if i == 0 else f"person{i + 1}"): "x.jpg"
               for i in range(16)}
    _refs31.update({("wardrobe" if i == 0 else f"wardrobe{i + 1}"): "y.jpg"
                    for i in range(15)})
    _refs30 = dict(list(_refs31.items())[:30])
    _cap_spec = edit_spec.normalize({"change": {"person": True,
                                                "person_ids": ["P1"],
                                                "wardrobe": True,
                                                "wardrobe_ids": ["P1"]}})
    _msg31 = edit_spec.missing_material(_cap_spec, _refs31,
                                        model="doubao-seedance-2-5-260628")
    check("2.5 超 30 张在出片前拦住", bool(_msg31), True)
    check("2.5 的超限提示不拿 2.0 的 9 张说明",
          "2.0 系列" not in (_msg31 or ""), True)
    check("2.5 正好 30 张放行",
          edit_spec.missing_material(_cap_spec, _refs30,
                                     model="doubao-seedance-2-5-260628"), None)

    # ⑨ 素材引用保真（`sd25-pe:906/:916`）：用户原文里已经写好的引用，
    #    **保留相同引用形式和编号**，不因素材读不到而删除/改号/翻译。
    import ruler_sd25  # 本文件在 scripts/ 下，同目录直接可导入
    for _ex, _want in (("参考@图片2的质感", "@图片2"),
                       ("把 @Image 1 的人换掉", "@Image 1"),
                       ("参考@图片5的质感", "@图片5")):   # 悬空引用也要原样留
        _sp = edit_spec.normalize({"change": {"person": True, "scene": True},
                                   "extra": _ex, "audio": "tts"})
        _out = edit_spec.compile_prompt("volc", _sp, model="doubao-seedance-2-5-260628",
                                        slots=["person", "scene"])
        check(f"用户写的 {_want} 原样保留", _want in _out, True)

    # 悬空引用**不该**被 T5 判「没有职责行」（官方要它原样留着、不做解释）。
    # `materials` 给了才启用这条豁免 —— 没给就照旧全查，别悄悄放宽。
    _dang = edit_spec.normalize({"change": {"person": True, "scene": True},
                                "extra": "参考@图片5的质感", "audio": "tts"})
    _dp = edit_spec.compile_prompt("volc", _dang, model="doubao-seedance-2-5-260628",
                                   slots=["person", "scene"])
    _red_strict = [v for v in ruler_sd25.check(
        _dp, ruler_sd25.ctx_for(_dp, None, "tpl")) if v[0] == "T5"]
    _red_mats = [v for v in ruler_sd25.check(
        _dp, ruler_sd25.ctx_for(_dp, None, "tpl",
                                materials={"@图片1", "@图片2"})) if v[0] == "T5"]
    check("悬空引用：不给 materials 时 T5 仍判红（成对的一半）", bool(_red_strict), True)
    check("悬空引用：给了 materials 后 T5 不判红（官方 :916 要求保留）",
          _red_mats, [])

    # ------------------------------------------------------------------
    # 从共用逻辑测试搬回来的 **2.5 单型号断言**（D43）
    # ------------------------------------------------------------------
    print("== 档位 / 清晰度 / 时长（2.5）==")
    from app.core.config import settings as _st
    from app.services import video_edit as _ve

    check("2.5 区间", _ve.bounds_for("volc", "doubao-seedance-2-5-260628"), (4.0, 30.0))
    _sp5 = edit_spec.defaults()
    _sp5["resolution"] = "4k"
    check("2.5 要 4k 退到 1080p（不是退默认 720p）",
          _ve._resolution_for("volc", _sp5, 1920, "doubao-seedance-2-5-260628",
                              width=1080), "1080p")
    _real5 = _st.ark_video_edit_model
    try:
        object.__setattr__(_st, "ark_video_edit_model", "doubao-seedance-2-5-260628")
        check("2.5 → 30s", _ve._limit_for("volc"), 30.0)
    finally:
        object.__setattr__(_st, "ark_video_edit_model", _real5)
    check("2.5 能带边界帧（可显式钉 edit 类型）", _ve.boundary_allowed(
        "volc", "doubao-seedance-2-5-260628"), True)
