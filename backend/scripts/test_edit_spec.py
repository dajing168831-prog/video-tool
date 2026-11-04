"""换画面结构化规格的纯逻辑自检入口（不发网络请求、不花钱）。

🩸 **必须点名型号**：`--model volc20|volc25|h3`。
一轮只跑一家 —— 以前 226 项三家混在一个文件里，改 2.0 的断言会顺手把别家
的运行结果一起改掉。现在：
  · 共用规则（默认值 / normalize / 编号 / 分辨率 / 静帧 / 混剪）→
    `test_edit_spec_common.py`
  · 2.0 → `test_edit_spec_sd20.py`
  · 2.5 → `test_edit_spec_sd25.py`
  · H3 → `test_edit_spec_h3.py`

运行：python scripts/test_edit_spec.py --model volc20
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import _model_lock  # noqa: E402

MODULES = {
    "volc20": "test_edit_spec_sd20",
    "volc25": "test_edit_spec_sd25",
    # 🔓 2026-11-03 接回机械版：`test_edit_spec_h3` 已搬回 `scripts/`。
    "h3": "test_edit_spec_h3",
}


def main() -> int:
    if "--model" not in sys.argv:
        lock = _model_lock.current()
        print("⛔ 必须点名型号：--model volc20|volc25|h3")
        print(f"   当前锁：{_model_lock.MODELS.get(lock, lock) if lock else '（无）'}")
        return 2
    i = sys.argv.index("--model")
    sel = sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
    if sel not in MODULES:
        print("用法：--model volc20|volc25|h3")
        return 2
    _model_lock.guard(sel)

    import importlib
    import test_edit_spec_common as common

    print(f"== 共用规则（三家都适用）==")
    common.run()
    mod = importlib.import_module(MODULES[sel])
    print(f"\n== {mod.LABEL} ==")
    mod.run()
    print(f"\n{common.PASS}/{common.PASS + common.FAIL} 通过  [{mod.LABEL}]")
    return 1 if common.FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
