# -*- coding: utf-8 -*-
"""参考片段的「像素门槛」：`_fit_segment` 必须把不达标的片段放大到过线。

🩸🩸 2026-10-30 真机 `6d26558d` 抓到的 400：
    原片 `480×836 = 401,280 px`，2.0 mini 的 r2v 下限是 **407,696**，
    只差 6,416 像素（1.6%）——不放大这条片子**永远发不出去**。
    报错原文：
    `the parameter video pixel count specified in the request must be
     greater than or equal to 407696 for model doubao-seedance-2-0-mini in r2v`

根因：`_fit_segment` 里那句 `abs(scale - 1.0) < 0.02` 本意是"缩放不到 2%
不值得重编码一遍"，却把**硬门槛**也一起放过了 —— 片段原样送进去，火山当场拒单。
像素门槛是硬性的，差 1% 也是 400。

本判据同时在补一个**空白**：`_fit_segment` 此前**一条判据都没有**
（`grep -rn _fit_segment scripts/` 为空），所以这个 bug 一直没人拦。

运行：python scripts/test_fit_segment.py --model volc20
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from _model_gate import sel_or_exit  # noqa: E402

from app.services import models, scene, video_edit  # noqa: E402
from app.services.media import ffmpeg_path  # noqa: E402

PASS = FAIL = 0


def check(name: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {name}: {got}")
    else:
        FAIL += 1
        print(f"  FAIL {name}: got={got!r} want={want!r}")


def _make(dest: Path, w: int, h: int, sec: float = 0.6) -> Path:
    """造一条 w×h 的纯色片（本机 CPU，不联网、不花钱）。"""
    ff = ffmpeg_path()
    if not ff:
        raise RuntimeError("找不到 ffmpeg")
    cmd = [ff, "-hide_banner", "-loglevel", "error", "-y",
           "-f", "lavfi", "-i", f"color=c=gray:s={w}x{h}:d={sec}:r=24",
           "-c:v", "libx264", "-crf", "28", "-preset", "ultrafast",
           "-pix_fmt", "yuv420p", "-an", str(dest)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode != 0 or not dest.exists():
        raise RuntimeError(f"造片失败：{(r.stderr or '')[:300]}")
    return dest


def _px(p: Path) -> int:
    i = scene.probe(p)
    return int(i.get("width") or 0) * int(i.get("height") or 0)


def main() -> int:
    sel = sel_or_exit()
    caps = models.adapter_for(channel="volc").caps
    lim = caps.video_limits
    lo = int(lim.get("min_px") or 0)
    hi = int(lim.get("max_px") or 0)

    print(f"[{sel}] 参考片段像素门槛（volc 通道：下限 {lo} / 上限 {hi}）")
    if not lo:
        # 这一家没有像素门槛（H3 的 min_px=0），判据不适用 —— 明说，不谎报通过。
        print(f"  跳过：通道 volc 未声明像素下限，本判据不适用")
        print(f"\n{PASS}/{PASS + FAIL} 通过")
        return 0 if not FAIL else 1

    tmp = Path(tempfile.mkdtemp(prefix="fitseg_", dir="D:/tmp"))

    # ---- ① 复现真机那个尺寸：480×836 = 401,280，差 1.6% ----
    small = _make(tmp / "small.mp4", 480, 836)
    px0 = _px(small)
    check("① 夹具本身不达标（先证有修复空间）", px0 < lo, True)

    # ---- ② 这个尺寸正好落在旧代码的"2% 宽容"盲区里（把 bug 钉死）----
    # 旧条件：abs(scale - 1) < 0.02 就当"差别太小"原样返回。
    ratio = (lo / px0) ** 0.5
    check("② 放大倍数 < 2%（旧代码正是因此漏掉它）", abs(ratio - 1.0) < 0.02, True)

    # ---- ③ 修复后必须重编码，且过线 ----
    out = video_edit._fit_segment(small, "volc")
    px1 = _px(out)
    check("③ 不达标 → 真的重编码出一份新文件", out != small, True)
    check("④ 重编码后过下限", px1 >= lo, True)
    check("⑤ 没过上限（别一头撞进上限）", (not hi) or px1 <= hi, True)
    # 取整各取偶数后会再掉一点，这里验"补齐"真的起作用
    check("⑥ 只差一点点也补够（不是刚过线就差 2 像素）", px1 - lo >= 0, True)

    # ---- ⑦ 反向：本来就达标的，必须原样返回（不白白掉一遍画质）----
    big = _make(tmp / "big.mp4", 720, 720)
    check("⑦ 达标夹具（先证它真的达标）", _px(big) >= lo, True)
    check("⑧ 达标片段原样返回、不重编码", video_edit._fit_segment(big, "volc") == big, True)

    # 上限那一侧没造夹具：volc 的上限 8,295,044 px ≈ 2880×2880，造一条真要跑很久，
    # 而这条路径的代码与下限同源（同一个 scale 计算），故不重复造。
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{PASS}/{PASS + FAIL} 通过")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
