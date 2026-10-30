"""先估时长再选语速 —— 纯本地计算，不发任何网络请求。

判据：
  1. 同样的字数，标点多的估得更长（停顿要算进去）
  2. 中文按字、英文按音节、数字按位数（不是一律当 1 个）
  3. 语速方向和豆包一致：估得比目标长 → 正数（更快）
  4. 语速有上限：不能为了凑时长把人声调成花栗鼠
  5. 残差超过 ±15% 要给出可执行建议（删几个字 / 补几个字）
  6. 新配音的说话区间能正确映射回源片时间轴

运行：python scripts/test_speech_est.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import speech_est  # noqa: E402
from app.services.clone_pipeline import source_speech_spans  # noqa: E402

PASS = FAIL = 0


def check(name: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {name}: {got}")
    else:
        FAIL += 1
        print(f"  FAIL {name}: got={got!r} want={want!r}")


def near(name: str, got: float, want: float, tol: float = 0.02) -> None:
    global PASS, FAIL
    if abs(got - want) <= tol:
        PASS += 1
        print(f"  ok   {name}: {got}")
    else:
        FAIL += 1
        print(f"  FAIL {name}: got={got!r} want≈{want!r}")


def main() -> int:
    # 🚦 必须点名型号（2026-10-26）：一轮只跑一家
    from _model_gate import sel_or_exit as _sel
    _sel()
    print("== 音节口径 ==")
    # 11 个汉字 = 11 个音节
    check("11 个汉字", speech_est.syllables("今天给大家推荐一个好物"), 11)
    # 英文按元音组：video=3、API=3、the=1
    check("video 三音节", speech_est.syllables("video"), 3)
    check("API 三个字母音节", speech_est.syllables("API"), 3)
    check("the 一音节", speech_est.syllables("the"), 1)
    # 中文里念数字是一位一位念的：2026 = 4 个音节
    check("中文数字按位数", speech_est.syllables("2026"), 4)
    # 英文里是数词：1999 ≈ 5 个音节（nineteen ninety-nine）
    check("英文数字按数词", speech_est.syllables("1999", "en"), 6)

    print("== 停顿要算进去 ==")
    a = speech_est.estimate("今天推荐这个好物很好用", "zh")
    b = speech_est.estimate("今天，推荐这个好物，很好用。", "zh")
    check("标点多的估得更长", b > a, True)
    near("11 字净时长 ≈ 2.29s", a, 11 / 4.8, 0.01)
    near("两个逗号一个句号 → +0.50s", b - a, 0.12 + 0.12 + 0.26, 0.01)

    print("== 语速方向（豆包：正数=更快）==")
    # 估 12s，目标 10s → 要快 20%
    check("估得长 → 正数", speech_est.rate_for(12, 10), 20)
    # 估 8s，目标 10s → 要慢 20%
    check("估得短 → 负数", speech_est.rate_for(8, 10), -20)
    check("正好 → 0", speech_est.rate_for(10, 10), 0)
    check("缺数不瞎调", speech_est.rate_for(0, 10), 0)
    check("目标为 0 不瞎调", speech_est.rate_for(10, 0), 0)
    # 估 30s 要压到 10s = 要快 200%，但语速最多 +30 —— 剩下的交给"改文案"
    check("语速封顶 +30", speech_est.rate_for(30, 10), 30)
    check("语速封底 -30", speech_est.rate_for(3, 30), -30)

    print("== 残差与建议 ==")
    near("估 12s / 目标 10s / +20% → 正好 1.0",
         speech_est.residual_ratio(12, 10, 20), 1.0, 0.001)
    # 16 个汉字 ≈ 3.33s，原片 3.3s —— 调不调语速都够用
    ok = speech_est.advise("今天给大家推荐一款很好用的面霜", 3.3)
    check("文案和原片差不多长 → ok", ok["verdict"], "ok")
    check("ok 时不用删字", ok["trim_chars"], 0)

    long_txt = "今天给大家推荐一款超级好用的面霜它真的非常滋润而且一点都不油腻用完皮肤特别舒服"
    syl = speech_est.syllables(long_txt)
    lg = speech_est.advise(long_txt, 3.0)
    check("长文案撞短原片 → long", lg["verdict"], "long")
    # 删字数必须是正数，而且不能"删到比原文还多"
    check("删字数 > 0", lg["trim_chars"] > 0, True)
    check("删字数 < 原文字数", lg["trim_chars"] < syl, True)

    sh = speech_est.advise("好用", 10.0)
    check("文案太短 → short", sh["verdict"], "short")
    check("short 要给出补多少字", sh.get("add_chars", 0) > 0, True)

    print("== 语言判定（ASR 的 lang 是默认值，不是它认出来的）==")
    check("纯中文", speech_est.detect_lang("今天给大家推荐一款好用的面霜"), "zh")
    check("纯英文", speech_est.detect_lang("This cream changed my skin in a week"), "en")
    # 中文里夹英文词很常见，不该被翻成英文
    check("中文夹英文词仍是中文",
          speech_est.detect_lang("这款精华用了 Vitamin C 和玻尿酸"), "zh")
    # 英文里出现一个中文品牌名也不该翻盘
    check("英文夹中文品牌仍是英文",
          speech_est.detect_lang("This is the new 花西子 lipstick from China"), "en")
    check("空文本用默认值", speech_est.detect_lang("", "zh"), "zh")
    check("只有数字用默认值", speech_est.detect_lang("2026", "en"), "en")
    # 🩸 只按**文字系统**判（官方音色表里 15 种小语种）：
    #   有独立文字的（日/韩/泰/阿/俄）能判，拉丁字母的（越/印尼/马来/菲/西/葡）不猜。
    check("假名 → 日语", speech_est.detect_lang("おはようございます、いい天気ですね"), "ja")
    check("Hangul → 韩语", speech_est.detect_lang("안녕하세요 반갑습니다"), "ko")
    check("泰文 → 泰语", speech_est.detect_lang("สวัสดีครับ ผมชื่อสมชาย"), "th")
    check("阿拉伯 → 阿语", speech_est.detect_lang("مرحبا كيف حالك اليوم"), "ar")
    check("西里尔 → 俄语", speech_est.detect_lang("Привет, как дела у тебя сегодня"), "ru")
    # 拉丁字母的小语种（越/印尼/马来/菲/西/葡）**文字上与英文无从区分**，
    # 现有口径按英文走（`en`）。这是已知限制，不是"判对了"——界面上必须让人手选。
    check("拉丁字母的小语种按英文走（已知限制）",
          speech_est.detect_lang("Saya pergi ke pasar membeli ikan", "id"), "en")

    print("== 小语种音节口径 ==")
    # 越南语带变音符号：`[A-Za-z]` 一个音节都数不到 → 估成 0 → 语速永远 0（等于没估）
    check("越南语数得到音节", speech_est.syllables("Tôi đi làm về nhà rồi", "vi") > 3, True)
    check("泰语数得到音节", speech_est.syllables("สวัสดีครับ", "th") > 1, True)
    check("日语一字一拍", speech_est.syllables("こんにちは", "ja"), 5.0)
    check("韩语一字一拍", speech_est.syllables("안녕하세요", "ko"), 5.0)
    check("俄语按元音数", speech_est.syllables("Привет", "ru"), 2.0)
    check("印尼语按拉丁口径数得到", speech_est.syllables("Saya pergi ke pasar", "id") > 3, True)
    check("西语音节数正常", speech_est.syllables("Hola, ¿cómo estás?", "es") >= 5, True)
    # 估算要真的随语言变：同一句话按泰语和按中文估，不能是同一个数
    check("不同语言估出的时长不同",
          speech_est.estimate("สวัสดีครับ", "th") != speech_est.estimate("สวัสดีครับ", "zh"), True)

    print("== 说话区间换算到源片时间轴 ==")
    # 🩸 画面不改速（从 0 秒原速播放），配音也从 0 秒开始播 —— 两条轴是同一根，
    # 所以这里**不做缩放**，只截到源片长度。缩放过：会把后半段静音算成有人说话。
    spans = source_speech_spans([(0.0, 2.0), (2.0, 5.0)], 20.0)
    check("原样保留", spans, [(0.0, 2.0), (2.0, 5.0)])
    check("空区间不产生 span", source_speech_spans([(1.0, 1.0)], 20.0), [])
    check("原片长度未知时返回空", source_speech_spans([(0.0, 2.0)], 0.0), [])
    # 区间不许越过源片末尾
    edge = source_speech_spans([(9.0, 12.0)], 10.0)
    check("终点被源片长度截住", edge[-1][1], 10.0)
    # 配音比画面短：只有前面那段在说话，后半段必须留空
    short = source_speech_spans([(0.0, 3.0)], 12.0)
    check("配音短 → 只有 0–3s 在说话", short, [(0.0, 3.0)])

    print("== 文案一变长，说话镜的判断就跟着变（本次修的那个 bug）==")
    # 判据直接用分诊自己那把尺子，不另写一份 —— 另写一份就是在测我自己的假设
    from app.services.triage import SPEECH_OVERLAP

    shot_dicts = [{"i": 0, "start": 0.0, "end": 5.0}, {"i": 1, "start": 5.0, "end": 10.0}]

    def talking(spans):
        hit = set()
        for s in shot_dicts:
            dur = s["end"] - s["start"]
            for a, b in spans:
                if min(b, s["end"]) - max(a, s["start"]) >= SPEECH_OVERLAP * dur:
                    hit.add(s["i"])
                    break
        return hit

    orig = [(0.0, 4.0)]                    # 原片 ASR：前 4 秒在说话
    new = source_speech_spans([(0.0, 9.0)], 10.0)   # 新配音：0–9s 都在说
    check("原片口径：只有第 1 镜算说话", talking(orig), {0})
    check("新文案口径：两镜都在说话", talking(new), {0, 1})

    print(f"\n{PASS}/{PASS + FAIL} 通过")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
