"""音色目录自检：默认值、语言匹配、脏输入收口。

判据是**最终发给 TTS 的 voice id**，不是"目录里有没有这条"。
音色 ID 全部来自火山官方 2.0 音色表（`app/data/voices.json` 的 source 字段）。

运行：python scripts/test_voice_catalog.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import voice_catalog as vc  # noqa: E402

PASS = FAIL = 0


def check(name: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {name}: {got}")
    else:
        FAIL += 1
        print(f"  FAIL {name}: got={got!r} want={want!r}")


def main() -> int:
    # 🚦 必须点名型号（2026-10-26）：一轮只跑一家
    from _model_gate import sel_or_exit as _sel
    _sel()
    print("== 目录本身 ==")
    stats = vc.summary()
    check("目录非空", stats["total"] > 0, True)
    check("中文音色存在", stats["zh"] > 0, True)
    check("英文音色存在", stats["en"] > 0, True)
    check("每个 ID 都是 2.0 资源",
          all(v["id"].endswith("_uranus_bigtts") for v in vc.list_for()), True)

    print("== 默认音色 ==")
    zh = vc.default_for("zh")
    en = vc.default_for("en")
    check("中文默认在目录里", vc.get(zh) is not None, True)
    check("英文默认在目录里", vc.get(en) is not None, True)
    check("英文默认是英文音色", en.startswith("en_"), True)
    check("中文默认是中文音色", zh.startswith("zh_"), True)
    check("留空按中文", vc.default_for(""), zh)

    print("== 按语言过滤 ==")
    check("英文列表全是 en_",
          all(v["id"].startswith("en_") for v in vc.list_for("en")), True)
    check("中文列表全是 zh_",
          all(v["id"].startswith("zh_") for v in vc.list_for("zh")), True)

    # 🩸 小语种：以前 `list_for` 非 en 一律当 zh，15 种语言的音色永远列不出来。
    print("== 小语种（数据在、入口也要在）==")
    langs = {x["v"]: x for x in vc.languages()}
    check("第二行语言数 = 官方表里除中英外的语言数", len(langs), 15)
    for code in ("id", "ms", "th", "vi", "tl", "ja", "ko", "es", "pt", "ru", "ar", "de", "fr", "it"):
        items = vc.list_for(code)
        check(f"{code} 列表全是 {code}_",
              bool(items) and all(v["id"].startswith(code + "_") for v in items), True)
        d = vc.default_for(code)
        check(f"{code} 默认音色属于该语言", d.startswith(code + "_"), True)
    check("中文/英文不进第二行", ("zh" in langs) or ("en" in langs), False)
    check("语言计数与目录一致",
          {k: v["n"] for k, v in langs.items()},
          {k: n for k, n in vc.summary()["by_lang"].items() if k not in ("zh", "en")})

    print("== 跨语言收口 ==")
    got, note = vc.resolve("zh_female_vv_uranus_bigtts", "th")
    check("中文音色配泰语 → 换掉", got.startswith("th_"), True)
    check("说明里点出泰语", "泰语" in note, True)
    check("拉美西语音色配西语 → 放行（同族）",
          vc.resolve("es_female_bv084_uranus_bigtts", "mx"),
          ("es_female_bv084_uranus_bigtts", ""))
    check("默认音色不是情绪变体",
          any(x in vc.default_for("th") for x in ("happy", "angry", "sad", "fear")), False)

    print("== 脏输入收口 ==")
    check("空 → 默认", vc.resolve("", "zh"), (zh, ""))
    check("空格 → 默认", vc.resolve("   ", "zh"), (zh, ""))
    check("合法中文音色原样通过",
          vc.resolve("zh_female_vv_uranus_bigtts", "zh"),
          ("zh_female_vv_uranus_bigtts", ""))

    got, note = vc.resolve("zh_female_vv_uranus_bigtts", "en")
    check("中文音色配英文 → 换掉", got, en)
    check("换掉时说明原因", "不一致" in note, True)

    got, note = vc.resolve("不存在的音色", "zh")
    check("不存在的 ID → 默认", got, zh)
    check("并说明原因", "不在官方目录" in note, True)

    # 声音复刻的私有音色（S_ 开头）在目录里本来就没有，但账号上是能用的，
    # 不能因为"我们列不出来"就把它换掉
    check("私有复刻音色放行", vc.resolve("S_abcdef", "zh"), ("S_abcdef", ""))

    print("== 给人看的标签 ==")
    check("标签非空", bool(vc.label("zh_female_vv_uranus_bigtts")), True)
    check("未知 ID 原样显示", vc.label("S_abcdef"), "S_abcdef")

    print(f"\n{PASS}/{PASS + FAIL} 通过")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
