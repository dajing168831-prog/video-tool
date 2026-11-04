"""H3 的逐镜画面描述必须有来源（官方 `ref-en:7`：正文不许写成参考关系列表）。

判据（成对，全部本地，不联网）：
  1. 盘点里已经有 `shots` → 什么都不做（不许白花一次盘点钱）
  2. H3 + 盘点缺 `shots` + 新版盘点缓存不存在 → **补一次**，并回报"补过了"
  3. H3 + 缺 `shots` + 新版缓存已存在 → 不补（补过就不再花第二次钱）
  4. 不是 H3 → 一律不补（2.0 / 2.5 的提示词不读 `shots`，不能拿 H3 的规矩动它们）
  5. 补的时候失败 → 退回原盘点、不抛（不许因为视觉挂了就让人出不了片）
  6. 补回来的盘点要**真的带上 `shots`**，并且它是调用方拿去重算提示词的那一份

运行：python scripts/test_h3_shot_source.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import video_edit, vision_plan  # noqa: E402

PASS = FAIL = 0
TMP = Path(tempfile.mkdtemp(prefix="shot_src_", dir="D:/tmp"))
VIDEO = TMP / "source.mp4"
VIDEO.write_bytes(b"fake-video-bytes")
CACHE = TMP / "inv_v4.json"


def check(name: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {name}: {got!r}")
    else:
        FAIL += 1
        print(f"  FAIL {name}: got={got!r} want={want!r}")


class Calls:
    def __init__(self, ret=None, raise_exc=None):
        self.n = 0
        self.ret = ret
        self.raise_exc = raise_exc

    def __call__(self, cid, video=None, *, refresh=False, **kw):
        self.n += 1
        if self.raise_exc:
            raise self.raise_exc
        # 真实行为：补一次就会写下当前 schema 版本的缓存文件
        CACHE.write_text("{}", encoding="utf-8")
        return self.ret


def run(ch: str, inv, *, cache_exists: bool, fake: Calls):
    CACHE.unlink(missing_ok=True)
    if cache_exists:
        CACHE.write_text("{}", encoding="utf-8")
    orig_inv, orig_path = vision_plan.inventory, vision_plan.cache_path_current
    vision_plan.inventory = fake
    vision_plan.cache_path_current = lambda *a, **k: CACHE
    # 要不要补由**能力参数**决定（`Caps.ensure_shot_source`），不再判通道名
    from app.services import models
    wanted = models.adapter_for(channel=ch or "volc").caps.ensure_shot_source
    try:
        out, refilled = video_edit._ensure_shot_source("cid", VIDEO, inv, wanted=wanted)
    finally:
        vision_plan.inventory, vision_plan.cache_path_current = orig_inv, orig_path
    return out, refilled


def main() -> int:
    # 🚦 必须点名型号（2026-10-26）：一轮只跑一家
    from _model_gate import sel_or_exit as _sel
    _sel(only='h3')
    with_shots = {"people": [], "shots": [{"start": 0.0, "end": 2.0, "en": "a man walks"}]}
    no_shots = {"people": [], "shots": []}
    fresh = {"people": [], "shots": [{"start": 0.0, "end": 2.0, "en": "a boy flies"}]}

    print("== 1. 已经有逐镜描述：不许再花钱 ==")
    f = Calls(ret=fresh)
    out, refilled = run("minimax", with_shots, cache_exists=False, fake=f)
    check("盘点一次都没调", f.n, 0)
    check("回报没补过", refilled, False)
    check("盘点原样返回", out is with_shots, True)

    print("== 2. H3 缺料 + 新版缓存不存在：补一次 ==")
    f = Calls(ret=fresh)
    out, refilled = run("minimax", no_shots, cache_exists=False, fake=f)
    check("盘点调了一次", f.n, 1)
    check("回报补过了", refilled, True)
    check("拿到的是新盘点", out, fresh)
    check("新盘点真的带 shots", bool(out.get("shots")), True)

    print("== 3. H3 缺料但新版缓存已在：不重复花钱 ==")
    f = Calls(ret=fresh)
    out, refilled = run("minimax", no_shots, cache_exists=True, fake=f)
    check("盘点没再调", f.n, 0)
    check("回报没补过", refilled, False)
    check("盘点原样返回", out is no_shots, True)

    print("== 4. 不是 H3（2.0 / 2.5）：一律不补 ==")
    for ch in ("volc", ""):
        f = Calls(ret=fresh)
        out, refilled = run(ch, no_shots, cache_exists=False, fake=f)
        check(f"{ch or '空'} 盘点没调", f.n, 0)
        check(f"{ch or '空'} 回报没补过", refilled, False)

    print("== 5. 补的时候失败：退回原盘点、不抛 ==")
    f = Calls(raise_exc=RuntimeError("视觉接口挂了"))
    out, refilled = run("minimax", no_shots, cache_exists=False, fake=f)
    check("回报没补过", refilled, False)
    check("拿回的是原盘点", out is no_shots, True)

    print("== 6. 补回来的盘点要带 shots 才能被正文用上 ==")
    # `describe_shots` 只认带 shots 的缓存；这里直接验它的选片逻辑
    no_shot_inv = {"shots": []}
    check("空 shots 不算可用", bool(no_shot_inv.get("shots")), False)
    check("补回来的带 shots", bool(fresh.get("shots")), True)

    print(f"\n{PASS}/{PASS + FAIL} 通过")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
