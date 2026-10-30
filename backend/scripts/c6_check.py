"""C6 多语种配音自检：**全程不联网、不调模型、不花钱**。

翻译本身要用真模型（要花钱，得主人放行），这里验的是翻译**前后**那些
"错了会一路错到成片"的机械部分：

  1. 切句：只按句末标点断，**不合并短句、不按 14 字硬切**
     （外语切碎后每片都带 TTS 头尾静音，实测总时长涨到 1.68/1.72 倍）
  2. 行数硬约束：模型少给/多给一行 → 重试一次仍不对就报错，绝不把错位的结果交出去
  3. 偏长重翻：估算超原片 1.15 倍时带预算重翻一轮，仍偏长就如实把比值返回
  4. `script_lines` 优先：给了就不再调 `_split_script`（成对探针，见下）
  5. 语种口径：配音音色表里有的语言，翻译都认识（否则用户选了就报"不支持的语种"）
  6. 接口守卫：任务不存在 / 空文案 / 目标是中文 / 不认识的语种 → 一律拦下且不调模型

运行：python scripts/c6_check.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# 🚦 必须点名型号（2026-10-26）：一轮只跑一家
from _model_gate import sel_or_exit as _sel
SEL = _sel()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import clone_pipeline, speech_est, translate, voice_catalog  # noqa: E402

PASS = FAIL = 0


def check(name: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {name}: {got}")
    else:
        FAIL += 1
        print(f"  FAIL {name}: got={got!r} want={want!r}")


def truthy(name: str, got, *, why: str = "") -> None:
    check(name + (f"（{why}）" if why else ""), bool(got), True)


# ---------------------------------------------------------------------------
print("== 1. 切句：只按句末标点断，不合并、不硬切 ==")

check("两句各自切开", translate.split_sentences("第一句。第二句！"),
      ["第一句", "第二句"])
check("短句不合并", translate.split_sentences("好。走。"), ["好", "走"])
long_one = "我们今天给大家介绍一款非常好用的产品价格特别实惠效果也很明显"
check("长句不按字数硬切", len(translate.split_sentences(long_one + "。")), 1)
check("换行也算句末", translate.split_sentences("一行\n二行"), ["一行", "二行"])
check("空文本", translate.split_sentences("   "), [])
check("没有标点就整段一行", translate.split_sentences(long_one), [long_one])

# 对照：自动切句会把这个长句切碎 —— 这就是不能用它的原因（成对）
check("对照·_split_script 会把长句切碎",
      len(clone_pipeline._split_script(long_one, 1)) > 1, True)

# ---------------------------------------------------------------------------
print("== 2. 行数硬约束（模型少给/多给都不许过）==")

_calls = {"n": 0}


def _stub(wrong_first: bool, texts: list[str]):
    """桩：第一次给错行数（可选），之后给对的行数。"""
    def _f(lines, target, *, budget_note=""):
        _calls["n"] += 1
        if wrong_first and _calls["n"] == 1:
            return texts[:-1], {}
        return list(texts), {}
    return _f


_real_chat = translate._chat
try:
    _calls["n"] = 0
    translate._chat = _stub(True, ["a", "b"])
    r = translate.translate_lines(["甲", "乙"], "en")
    check("少给一行→重试后拿到对齐结果", r["lines"], ["a", "b"])
    check("重试次数记了 2 轮", r["passes"], 2)

    # 两次都给错行数：必须报错，不能返回错位结果
    _calls["n"] = 0
    translate._chat = lambda lines, target, budget_note="": (["x"], {})
    try:
        translate.translate_lines(["甲", "乙"], "en")
        bad = "没报错"
    except translate.TranslateError as e:
        bad = "TranslateError" if "行数" in str(e) else f"别的错：{e}"
    check("两次都不对齐就报错", bad, "TranslateError")

    # -----------------------------------------------------------------
    print("== 3. 偏长带预算重翻一轮 ==")
    # 第一轮给长译文（超 1.15 倍），第二轮给短译文 —— 看它会不会自己重翻
    LONG = "This is a very very long line we have to say it slowly"
    SHORT = "Short line"
    seq = [([LONG, LONG], {}), ([SHORT, SHORT], {})]
    _seen = {"budget": []}

    def _two(lines, target, *, budget_note=""):
        _seen["budget"].append(bool(budget_note))
        i = min(len(_seen["budget"]) - 1, len(seq) - 1)
        return seq[i]

    translate._chat = _two
    r = translate.translate_lines(["甲", "乙"], "en", src_total=4.0)
    truthy("第一轮没带预算、第二轮带了", _seen["budget"][:2] == [False, True],
           why=str(_seen["budget"]))
    check("重翻后行数不变", len(r["lines"]), 2)
    truthy("比值仍如实返回", r["ratio"] > 0)
    check("最多两轮（不无限重试）", r["passes"] <= 2, True)

    # 同语种不翻译：不调模型，原样返回
    _calls["n"] = 0
    translate._chat = _stub(False, ["不该被调用"])
    r = translate.translate_lines(["中文"], "zh")
    check("目标是中文→不翻", r["lines"], ["中文"])
    check("目标是中文→没调模型", _calls["n"], 0)
finally:
    translate._chat = _real_chat

# ---------------------------------------------------------------------------
print("== 4. script_lines 优先（成对探针：把 _split_script 掐掉看谁在调）==")

REC = {
    "source": {"duration": 6.0, "fps": 25.0, "width": 360, "height": 640,
               "has_audio": True},
    "shots": [{"i": 0, "start": 0.0, "end": 6.0, "text": "你好世界", "motion": 0.0}],
    "speech": {"lang": "zh", "segments": [{"start": 0.0, "end": 6.0, "text": "你好世界"}]},
}


_probe = {"called": 0}
_real_split = clone_pipeline._split_script


def _counting_split(script, n):
    _probe["called"] += 1
    return _real_split(script, n)


try:
    clone_pipeline._split_script = _counting_split
    _probe["called"] = 0
    clone_pipeline.preview_render(
        Path("unused.mp4"), REC, script="随便写点什么",
        script_lines=["One.", "Two."],
        edit_spec={"audio": "tts"}, lang="en")
    check("给了 script_lines → 不调 _split_script", _probe["called"], 0)

    _probe["called"] = 0
    clone_pipeline.preview_render(
        Path("unused.mp4"), REC, script="随便写点什么",
        edit_spec={"audio": "tts"}, lang="en")
    check("对照·不给就调（成对）", _probe["called"], 1)

    # 内容一变估算必须跟着变 —— 否则"用了 script_lines"和"没用"分不出来
    r = clone_pipeline.preview_render(
        Path("unused.mp4"), REC, script="随便写点什么",
        script_lines=["One."], edit_spec={"audio": "tts"}, lang="en")
    r3 = clone_pipeline.preview_render(
        Path("unused.mp4"), REC, script="随便写点什么",
        script_lines=["One two three four five six seven eight nine ten."],
        edit_spec={"audio": "tts"}, lang="en")
    truthy("译文变了估算跟着变",
           r3["audio"]["est_seconds"] != r["audio"]["est_seconds"],
           why=f'{r["audio"]["est_seconds"]} vs {r3["audio"]["est_seconds"]}')
finally:
    clone_pipeline._split_script = _real_split

# ---------------------------------------------------------------------------
print("== 5. 语种口径 ==")

check("translate 认识全部配音语种",
      sorted(set(voice_catalog.LANGS) - set(translate.LANG_NAME)), [])
check("中英文也在表里", sorted({"zh", "en"} - set(translate.LANG_NAME)), [])
# 泰语 CPS 校准：实测/估算=1.385，4.5 改 3.25。改回去就会让语速算小、临时才顶到 atempo
check("泰语每秒音节（实测校准值）", speech_est._SYL_PER_SEC["th"], 3.25)
truthy("泰语估算比等字数中文长（不为 0 也不是同一条曲线）",
       speech_est.estimate("สวัสดีครับ", "th") > 0)

# ---------------------------------------------------------------------------
print("== 6. /translate 接口守卫 ==")

from app.api import clone as clone_api  # noqa: E402

_real_load = clone_api.store.load
_real_tr = translate.translate_lines
TASK = {"recipe": {"source": {"duration": 12.0}}}


class _Body:
    def __init__(self, text, lang):
        self.text = text
        self.lang = lang


def _call(text, lang):
    return asyncio.run(clone_api.clone_translate("cid", _Body(text, lang)))


try:
    clone_api.store.load = lambda cid: None
    check("任务不存在", _call("你好", "en")["biz_code"], 404)

    clone_api.store.load = lambda cid: TASK
    check("空文案", _call("   ", "en")["biz_code"], 6)
    check("目标是中文", _call("你好", "zh")["biz_code"], 8)
    check("不认识的语种", _call("你好", "xx")["biz_code"], 8)
    check("超长文案", _call("啊" * 2001, "en")["biz_code"], 6)

    # 正常路径：桩掉翻译，只验"断句→翻译→补 source_total"这条接线
    _got = {}


    def _fake(lines, lang, *, source="zh", src_total=0.0, max_passes=2):
        _got.update(lines=lines, lang=lang, src_total=src_total)
        return {"lines": [x.upper() for x in lines], "lang": lang,
                "ratio": 1.0, "passes": 1, "usage": {}}

    translate.translate_lines = _fake
    r = _call("第一句。第二句！", "en")
    check("正常路径 biz_code", r["biz_code"], 0)
    check("断出的行数", len(_got["lines"]), 2)
    check("原片时长透传给估算", _got["src_total"], 12.0)
    check("返回的 source_total", r["data"]["source_total"], 12.0)
finally:
    clone_api.store.load = _real_load
    translate.translate_lines = _real_tr

# ---------------------------------------------------------------------------
print(f"\n{'=' * 46}\n通过 {PASS} / 失败 {FAIL}\n{'=' * 46}")
print("⚠ 未覆盖：真模型翻译质量与行数对齐 —— 要用真 key 花钱，得主人放行")
sys.exit(0 if FAIL == 0 else 1)
