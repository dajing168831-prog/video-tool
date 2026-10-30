"""「一任务多版本」的本地自检（不发请求、不花钱）。

多版本 = 同一个任务按 N 个开头方向**顺序**出 N 版。风险只有一个：
前一版还没跑完就提交下一版，会被任务锁挡回来（biz_code=7），
用户看到的是"第一版好、后面全失败"。

所以这里验两件事：
    1. 后端任务锁：同一任务同时只能跑一个渲染；不同任务互不影响；跑完能再提交。
    2. 前端确实在等：多版本循环里必须等到上一版 done/failed 才提交下一版。

运行：python scripts/test_multi_version.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import clone_jobs  # noqa: E402

PASS = FAIL = 0


def check(name: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {name}: {got}")
    else:
        FAIL += 1
        print(f"  FAIL {name}: got={got!r} want={want!r}")


def test_lock() -> None:
    print("== 任务锁：一任务同时只跑一版 ==")
    cid, other = "t_mv_aaaa", "t_mv_bbbb"
    ok1 = clone_jobs._claim(cid, "rid-1")
    check("第一版拿到锁", ok1, True)
    check("任务标记为忙", clone_jobs.is_busy(cid), True)
    ok2 = clone_jobs._claim(cid, "rid-2")
    check("第一版没跑完时第二版被挡", ok2, False)
    check("被挡后忙状态不变", clone_jobs.is_busy(cid), True)
    ok3 = clone_jobs._claim(other, "rid-3")
    check("别的任务不受影响", ok3, True)

    clone_jobs._release(cid)
    check("第一版跑完解锁", clone_jobs.is_busy(cid), False)
    ok4 = clone_jobs._claim(cid, "rid-2")
    check("解锁后第二版能提交", ok4, True)
    clone_jobs._release(cid)
    clone_jobs._release(other)
    check("全部释放后不残留", clone_jobs.is_busy(cid) or clone_jobs.is_busy(other), False)


def test_ui_waits() -> None:
    """前端多版本循环：提交下一版之前，必须等到上一版结束。"""
    print("== 前端：多版本是顺序跑，不是并发 ==")
    vue = (Path(__file__).resolve().parents[2]
           / "frontend" / "app" / "src" / "pages" / "clone" / "diagnose.vue")
    if not vue.exists():
        print(f"  skip：找不到 {vue}")
        return
    src = vue.read_text(encoding="utf-8")
    m = re.search(r"for \(let i = 0; i < dirs\.length; i \+= 1\) \{(.+?)\n          \}",
                  src, re.S)
    check("找得到多版本循环", bool(m), True)
    if not m:
        return
    body = m.group(1)
    check("循环里调了出片接口", "cloneRender(" in body, True)
    check("出片后等一下（waitRender）", "waitRender(" in body, True)
    if "cloneRender(" in body and "waitRender(" in body:
        check("waitRender 在 cloneRender 之后（顺序跑，不并发）",
              body.index("waitRender(") > body.index("cloneRender("), True)
        check("两行都是 await（真的等，不是发出去就不管）",
              "await cloneRender(" in body and "await this.waitRender(" in body, True)


def main() -> int:
    # 🚦 必须点名型号（2026-10-26）：一轮只跑一家
    from _model_gate import sel_or_exit as _sel
    _sel()
    test_lock()
    test_ui_waits()
    print(f"\n{PASS}/{PASS + FAIL} 通过")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
