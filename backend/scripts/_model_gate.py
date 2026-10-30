# -*- coding: utf-8 -*-
"""统一型号闸门：所有验收脚本必须 `--model volc20|volc25|h3`。

🩸 2026-10-26 主人要求「三个模型真正分离干净」：
  ① 入口不点名型号 → 直接拒绝运行（不再"默认跑三家"或"按锁猜"）；
  ② 点名了还必须与 `.model-lock.json` 一致（`--force` 放行，会打印留痕）。

用法（每个脚本 main() 第一行）：
    from _model_gate import sel_or_exit
    sel = sel_or_exit()
"""
from __future__ import annotations

import sys

import _model_lock


def _say(*args: object) -> None:
    """闸门在脚本可能还没 `sys.stdout.reconfigure` 之前就会说话 —— 自己兜住编码。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    print(*args)


def sel_or_exit(argv: list[str] | None = None, *, only: str | None = None,
                extra: tuple[str, ...] = ()) -> str:
    """返回点名型号。`only` = 本脚本只验这一家；`extra` = 额外接受的键（如 `still`）。"""
    explicit = argv is not None
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--model" not in argv:
        lock = _model_lock.current()
        _say("⛔ 必须点名型号：--model volc20|volc25|h3")
        _say(f"   当前锁：{_model_lock.MODELS.get(lock, lock) if lock else '（无）'}")
        raise SystemExit(2)
    i = argv.index("--model")
    name = argv[i + 1] if i + 1 < len(argv) else ""
    if name not in _model_lock.MODELS and name not in extra:
        _say("用法：--model volc20|volc25|h3" + (f"|{'|'.join(extra)}" if extra else ""))
        raise SystemExit(2)
    if only and name != only:
        _say(f"⛔ 本脚本只验 {_model_lock.MODELS.get(only, only)}；"
             f"本轮点名的是 {_model_lock.MODELS.get(name, name)}。")
        _say("   跨型号请等轮到它那一轮再来（不许拿别家的型号跑一遍报绿）。")
        raise SystemExit(2)
    if name not in extra:      # `still` 不是一家模型，不参与锁校验
        _model_lock.guard(name, argv)
    # 🩸 闸门吃掉了 `--model X` 就不许它再落到下游 argparse（否则 `unrecognized
    # arguments: --model` 把一条本来能过的验收判成红）。
    if not explicit:
        k = sys.argv.index("--model")
        del sys.argv[k:k + 2]
    # 🩸 2026-10-28：`--force` 同样要吃掉。`guard()` 只在**锁和点名的型号不一致**
    #   时才读它，可下游 argparse 根本不认识这个开关 —— 于是**逃生口一用就崩**：
    #   `identifiability_check.py --model volc20 --force` →
    #   `error: unrecognized arguments: --force`（实测）。锁本来就是拦错用的，
    #   逃生口失灵等于锁死。删掉它，脚本自己的参数表不用为闸门改。
    while "--force" in sys.argv:
        sys.argv.remove("--force")
    return name
