# -*- coding: utf-8 -*-
"""分模型执行锁 —— 一轮只跑一个型号，工具层面把门。

为什么要有它（2026-10-26，主人第三次提醒之后）
-----------------------------------------------
主人反复讲「**一个一个模型分开来执行**」，但工具全是跨型号的：
`prompt_snapshot` 一份用例锁着 2.0/2.5/H3 三家，`ruler_sd20`/`ruler_sd25`
各自能跑；于是我每轮都会"顺手确认一下别家没被波及"，最后变成在 2.5 轮里
改到 2.0 的锁定文本 —— 规则写在脑子里，靠自觉，必然复发。

锁文件：`backend/.model-lock.json`，形如 `{"model": "volc25"}`。
- `ruler_sd20.py` / `ruler_sd25.py` 启动先 `guard()`：型号不是当前锁 → **直接退出**。
- `prompt_snapshot.py` 默认只看锁住的那一家，冻结也只写这一家。
- 确实要跨型号（例如主人点名）时加 `--force` / `--all`，并在输出里留痕。

用法：
    python scripts/_model_lock.py show          # 看当前锁
    python scripts/_model_lock.py volc25        # 锁到 2.5
    python scripts/_model_lock.py clear         # 解锁（三家随便跑）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACK = Path(__file__).resolve().parents[1]
LOCK = BACK / ".model-lock.json"

# 🩸 三家**平级**，没有主力型号（主人 2026-10-26 明确纠正）：
# 2.0 / 2.5 / H3 都是用户的入口，各按各的官方标准，轮流一轮一轮过。
MODELS = {
    "volc20": "火山 2.0",
    "volc25": "火山 2.5",
    "h3": "MiniMax H3",
}
_ALIAS = {"minimax": "h3"}


def current() -> str:
    """当前锁住的型号；空串 = 没锁。"""
    try:
        return str(json.loads(LOCK.read_text(encoding="utf-8")).get("model") or "")
    except Exception:
        return ""


def set_model(name: str) -> None:
    LOCK.write_text(json.dumps({"model": name}, ensure_ascii=False), encoding="utf-8")


def _say(*args: object) -> None:
    """挡住编码：被拒绝的脚本可能还没把 stdout 切成 utf-8。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    print(*args)


def guard(name: str, argv: list[str] | None = None) -> None:
    """型号与锁不符就退出。`--force` 放行（会在输出里留一行痕）。"""
    argv = list(sys.argv[1:] if argv is None else argv)
    lock = current()
    if not lock or lock == name:
        return
    if "--force" in argv:
        _say(f"⚠️ --force：当前锁是 {MODELS.get(lock, lock)}，本次强跑 "
             f"{MODELS.get(name, name)}")
        return
    _say(f"⛔ 当前锁在 **{MODELS.get(lock, lock)}**（.model-lock.json），"
         f"本轮不许跑 {MODELS.get(name, name)}。")
    _say(f"   换型号：python scripts/_model_lock.py {name}")
    _say("   确实要跨型号：加 --force")
    raise SystemExit(3)


def main() -> int:
    a = sys.argv[1:]
    if not a or a[0] == "show":
        lock = current()
        print(f"当前锁：{MODELS.get(lock, lock) if lock else '（无，三家都能跑）'}")
        return 0
    if a[0] == "clear":
        LOCK.unlink(missing_ok=True)
        print("已解锁")
        return 0
    if a[0] in _ALIAS:
        a[0] = _ALIAS[a[0]]
    if a[0] in MODELS:
        set_model(a[0])
        print(f"已锁到 {MODELS[a[0]]}（{a[0]}）")
        return 0
    print(f"用法：python scripts/_model_lock.py [show|clear|{'|'.join(MODELS)}]")
    return 2


if __name__ == "__main__":
    sys.exit(main())
