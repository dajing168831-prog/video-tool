"""接口重试的自检：该重试的重试，不该重试的一次都不许多发。

判据是**实际发了几次请求**，不是"代码里有没有 retry 这个词"：
  - 429 / 503 → 退避后重试，最终拿到 200
  - 400 / 401 / 403 → 一次就抛（重试一百次结果一样，纯耽误时间）
  - 网络异常 → **不重试**（请求可能已经被对方收下，重发 = 花两次钱）

运行：python scripts/test_retry.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import retry  # noqa: E402

PASS = FAIL = 0


def check(name: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {name}: {got}")
    else:
        FAIL += 1
        print(f"  FAIL {name}: got={got!r} want={want!r}")


class _Resp:
    def __init__(self, status: int):
        self.status_code = status
        self.text = f"status {status}"


class _Client:
    """按脚本依次返回；脚本用光就一直返回最后一个。"""

    def __init__(self, script, *, raise_at: int | None = None):
        self.script = list(script)
        self.calls = 0
        self.raise_at = raise_at

    def post(self, url, **kw):
        self.calls += 1
        if self.raise_at is not None and self.calls == self.raise_at:
            raise ConnectionError("boom")
        st = self.script[min(self.calls - 1, len(self.script) - 1)]
        return _Resp(st)


def main() -> int:
    # 🚦 必须点名型号（2026-10-26）：一轮只跑一家
    from _model_gate import sel_or_exit as _sel
    _sel()
    real_sleep = retry.time.sleep
    # 退避真睡 30 秒太慢；这里只关心"重试了几次"
    retry.time.sleep = lambda s: None
    try:
        print("== 429 会重试 ==")
        c = _Client([429, 429, 200])
        r = retry.post(c, "https://x")
        check("最终拿到 200", r.status_code, 200)
        check("发了 3 次", c.calls, 3)

        print("== 503 会重试 ==")
        c = _Client([503, 200])
        check("最终 200", retry.post(c, "https://x").status_code, 200)
        check("发了 2 次", c.calls, 2)

        print("== 400 不重试 ==")
        c = _Client([400])
        check("原样返回 400", retry.post(c, "https://x").status_code, 400)
        check("只发 1 次", c.calls, 1)

        print("== 401 不重试 ==")
        c = _Client([401])
        retry.post(c, "https://x")
        check("只发 1 次", c.calls, 1)

        print("== 网络异常不重试 ==")
        c = _Client([200], raise_at=1)
        try:
            retry.post(c, "https://x")
            check("异常被抛出来", "没抛", "抛")
        except ConnectionError:
            check("异常被抛出来", "抛", "抛")
        check("只发 1 次（不盲目重发）", c.calls, 1)

        print("== 一直 429 也有尽头 ==")
        c = _Client([429])
        r = retry.post(c, "https://x")
        check("返回最后一次响应", r.status_code, 429)
        check("次数封顶", c.calls, len(retry._BACKOFF) + 1)
    finally:
        retry.time.sleep = real_sleep

    print(f"\n{PASS}/{PASS + FAIL} 通过")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
