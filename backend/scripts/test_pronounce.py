"""读音校正（Dual Text）自检 —— 纯字符串处理，不发网络请求。

判据：
  1. 字幕用原文，配音用改过的 —— 两侧不能混
  2. 长键优先：有 `小红书` 时不能让 `小` 先命中
  3. 单遍替换：替换出来的字不会二次命中（A→B、B→C 不许连锁）
  4. 脏输入被丢弃：空值/非字符串/键值相同/超长
  5. 只挑候选，不编念法（detect 不改原文）

运行：python scripts/test_pronounce.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import pronounce  # noqa: E402

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
    print("== 字幕与配音分离 ==")
    txt = "这款XHS同款只要¥19.9"
    m = {"XHS": "小红书", "¥19.9": "十九块九"}
    spoken = pronounce.apply(txt, m)
    check("念的那份被替换", spoken, "这款小红书同款只要十九块九")
    check("显示的那份原样", txt, "这款XHS同款只要¥19.9")

    print("== 长键优先 ==")
    check("长键先命中", pronounce.apply("我买了小红书同款", {"小": "X", "小红书": "红宝书"}),
          "我买了红宝书同款")

    print("== 单遍替换，不许连锁 ==")
    # A→B、B→C：如果连锁就会变成 C
    check("替换结果不再被替换", pronounce.apply("A", {"A": "B", "B": "C"}), "B")
    check("多个词各自生效", pronounce.apply("API 和 SQL", {"API": "A P I", "SQL": "sequel"}),
          "A P I 和 sequel")

    print("== 脏输入 ==")
    check("非 dict 直接忽略", pronounce.apply("原样", None), "原样")
    check("列表不认", pronounce.apply("原样", ["a", "b"]), "原样")
    check("空值丢弃", pronounce.clean({"A": "", "B": "  ", "C": "see"}), {"C": "see"})
    check("键值相同丢弃", pronounce.clean({"A": "A"}), {})
    check("非字符串丢弃", pronounce.clean({"A": 1, 2: "two", "B": "bee"}), {"B": "bee"})
    check("超长丢弃", pronounce.clean({"A" * 40: "x"}), {})
    check("条目数封顶", len(pronounce.clean({f"k{i}": f"v{i}" for i in range(80)})),
          pronounce.MAX_ENTRIES)

    print("== 候选检测（只挑，不编）==")
    check("英文词与缩写", pronounce.detect("用API调用video模型"), ["API", "video"])
    check("币种数字", pronounce.detect("只要¥19.9就行"), ["¥19.9"])
    check("纯中文没有候选", pronounce.detect("今天天气不错"), [])
    check("重复只出现一次", pronounce.detect("API 和 API"), ["API"])
    check("检测不改原文", pronounce.detect("API"), ["API"])

    print("== 端到端形状：字幕仍显示原文 ==")
    display, spoken2 = pronounce.display_vs_spoken("XHS 上买的", {"XHS": "小红书"})
    check("显示", display, "XHS 上买的")
    check("念法", spoken2, "小红书 上买的")

    print(f"\n{PASS}/{PASS + FAIL} 通过")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
