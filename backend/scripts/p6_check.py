"""P6 验收：成片页「改这段 → 只重出这段」（零模型调用、不花钱）。

产品上的一句话：**成片出来以后，哪句不满意就点它，只把那一小截重做。**

这条链有三段，任何一段断了用户都会"又跑了一条全片"：
  1. 成片页把「哪一段」带出去（cid / rid / 时间区间）；
  2. 诊断页把"这一段之外的镜头"排除掉，并把上一版文案带回来；
  3. 出片接口真的只收这几镜 —— 且**非法镜号不能静默变成全片**（那是钱）。

跑法：python scripts/p6_check.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.core.config import settings  # noqa: E402
from app.services import clone_store, edit_spec, media, work  # noqa: E402

FRONT = ROOT.parent / "frontend" / "app" / "src"

#: 🩸 任务目录有 TTL（默认 3 天），`main.py` 启动和定时器都会清理过期任务。
#: 以前这里写死一条真跑过的 cid → 过几天就整组 FileNotFoundError（看着像代码坏了）。
#: 改成每次挑**最新、而且真有分镜**的那条。
#:
#: 🩸 2026-10-29：光"挑最新"不够 —— 本机存量任务的 `recipe.shots` 全是 0 条，
#: 于是 3.x 整组长期 skipped。而 3.x 验的正是**「非法镜号会不会静默变成全片」**
#: （那是钱）。一条永远跑不起来的判据 = 没验。改成：没有真任务就**现场造一条**
#: 自测任务（借一条原片做硬链接夹具，3 个镜头），跑完立刻删掉，不污染作品列表。
CID = ""

SELF_CID = "a" * 32


def _pick_cid() -> str:
    """挑一条**真有分镜**的任务。

    🩸 分镜在 `recipe.shots` 里，不在 task 顶层 —— 以前这里查 `task.get("shots")`
    永远是空，于是 3.x 整组长期 skipped，「非法镜号不能变成全片」这条判据等于没验
    （2026-10-29 修）。
    优先镜头数 ≥3 的：3.4 要拿"换一个镜头"自证，只有一镜的任务证不了。
    """
    best: tuple[bool, float, str] | None = None
    root = settings.clone_dir
    if not root.exists():
        return ""
    for d in root.iterdir():
        p = d / "task.json"
        if not d.is_dir() or not p.is_file():
            continue
        try:
            task = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        shots = (task.get("recipe") or {}).get("shots") or []
        # 坏数据（end <= start）会让区间算成负数 —— 不拿它当尺子
        shots = [s for s in shots
                 if float(s.get("end") or 0) > float(s.get("start") or 0)]
        if not shots:
            continue
        at = float(task.get("created_at") or 0.0)
        key = (len(shots) >= 3, at, d.name)
        if best is None or key[:2] > best[:2]:
            best = key
    return best[2] if best else ""


def _build_fixture() -> tuple[str, str]:
    """现场造一条带 3 个分镜的最小任务（零模型调用、零联网、零花费）。

    原片用**硬链接**借（同卷零拷贝），借不到才复制。返回 (cid, 失败原因)。
    """
    root = settings.clone_dir
    root.mkdir(parents=True, exist_ok=True)
    d = clone_store.task_dir(SELF_CID)
    d.mkdir(parents=True, exist_ok=True)
    dst = clone_store.source_path(SELF_CID)
    if not dst.exists():
        cands = [p for p in root.glob("*/source.mp4")
                 if p.resolve() != dst.resolve()]
        if not cands:
            return "", "本机一条 source.mp4 都没有，借不到夹具原片"
        src = min(cands, key=lambda p: p.stat().st_size)
        try:
            os.link(src, dst)
        except OSError:
            shutil.copy2(src, dst)
    total = media.probe_duration(dst) or 0.0
    if total < 6.0:
        return "", f"借来的原片只有 {total:.1f}s，切不出 3 个镜头"
    step = round(total / 3, 1)
    bounds = [0.0, step, round(step * 2, 1), round(total, 2)]
    shots = [
        {"i": i, "start": bounds[i], "end": bounds[i + 1],
         "dur": round(bounds[i + 1] - bounds[i], 2),
         # 直接给运动量：缺值会触发「补算」，那条路要抽帧读视频，夹具越简单越好
         "motion": 0.0, "keyframe": ""}
        for i in range(3)
    ]
    task = clone_store.new_task(SELF_CID, meta={"title": "p6 自测夹具"})
    task.update({
        "state": "analyzed", "stage": "done", "pct": 100,
        # created_at 压到 0：夹具绝不能顶掉用户的真作品
        "created_at": 0.0,
        "recipe": {
            "source": {"duration": total, "width": 0, "height": 0,
                       "fps": 0.0, "has_audio": False},
            "shots": shots,
            "speech": {"lang": "zh", "segments": []},
        },
    })
    clone_store.save(task)
    return SELF_CID, ""


def _drop_fixture() -> None:
    """删掉夹具目录。只认死那个 id —— 路径不对就什么都不做。"""
    d = settings.clone_dir / SELF_CID
    if d.name != SELF_CID or not d.is_dir():
        return
    shutil.rmtree(d, ignore_errors=True)

rows: list[tuple[str, bool, str]] = []


def chk(name: str, ok: bool, detail: str = "") -> None:
    rows.append((name, bool(ok), detail))


def skip(name: str, why: str = "") -> None:
    """跑不了就如实记 skipped —— **不许记成 PASS**（空集恒真的假绿）。"""
    rows.append((name, None, f"skipped：{why}"))


def _report() -> int:
    ok = sum(1 for _n, o, _d in rows if o is True)
    skipped = sum(1 for _n, o, _d in rows if o is None)
    for n, o, d in rows:
        tag = "PASS" if o is True else ("SKIP" if o is None else "FAIL")
        print(f"{tag}  {n}" + (f"  [{d}]" if d else ""))
    ran = len(rows) - skipped
    print(f"\n{ok}/{ran} 通过" + (f"，{skipped} 条 skipped（未验证，不算通过）"
                                  if skipped else ""))
    return 0 if ok == ran else 1


def flat_edit(rec: dict) -> dict:
    e = rec.get("edit") or {}
    return edit_spec.normalize({**(e.get("change") or {}), "audio": e.get("audio"),
                                "resolution": e.get("resolution"),
                                "extra": e.get("extra", "")})


def main() -> int:
    # 🚦 必须点名型号（2026-10-26）：一轮只跑一家
    from _model_gate import sel_or_exit as _sel
    _sel()
    res = (FRONT / "pages" / "clone" / "result.vue").read_text(encoding="utf-8")
    diag = (FRONT / "pages" / "clone" / "diagnose.vue").read_text(encoding="utf-8")

    # ---- 1. 成片页带得出去 ------------------------------------------------
    chk("1.1 成片页每一句都有「改这段」", "改这段" in res and "editSeg" in res,
        "字幕时间轴逐句一个入口")
    url = re.search(r"diagnose\?cid=\$\{this\.cid\}&rid=\$\{this\.rid\}&only=", res)
    chk("1.2 跳转带上 cid / rid / 时间区间", bool(url),
        "rid 用来取上一版文案，only 用来限定范围")

    # ---- 2. 诊断页收得住 --------------------------------------------------
    chk("2.1 诊断页解析 only 区间", "q.only" in diag and "/^([\\d.]+)-([\\d.]+)$/" in diag,
        "12.30-15.00 → [12.3, 15.0]")
    chk("2.2 不重叠的镜头被排除", "excludedShots" in diag and "applyOnly" in diag,
        "只把重叠镜头送去重画")
    chk("2.3 上一版文案从 rid 取回", "fromRid" in diag and "r.script" in diag,
        "不从原片 ASR 重来")

    # ---- 3. 后端真的只收这几镜 -------------------------------------------
    global CID
    CID = _pick_cid()
    if not CID:
        CID, err = _build_fixture()
        if not CID:
            why = f"没有带分镜的存量任务，夹具也造不出来（{err}）"
            print(f"⏭  {why} → 3.x 整组 skipped（1.x/2.x 只查产物源码，不受影响）")
            for name in ("3.1 限定一个镜头 → 要处理的秒数变少",
                         "3.2 非法镜号不会静默变成全片",
                         "3.3 空数组仍按「不限」处理",
                         "3.4 尺子自证：换镜头 → 范围跟着变"):
                skip(name, why)
            return _report()
        print("🔧 存量任务没有分镜 → 现场造了一条 3 镜自测任务（零花费）")
    try:
        return _section3()
    finally:
        if CID == SELF_CID:
            _drop_fixture()


def _section3() -> int:
    """3.x 的主体。夹具是临时造出来的，所以单独一个函数好在 finally 里删。"""
    w = work.build(CID)
    # 用「换场景」而不是「换人物」验范围：换人物要先有视觉盘点结果，
    # 没盘点时会先抛"盘点里没有 P1"，把这条判据挡在后面（那就是假红）。
    spec = edit_spec.normalize({"change": {"scene": True, "scene_desc": "黄昏的海边"},
                                "audio": "original"})
    base = {"mode": "auto", "channel": "auto", "model": "", "script": "", "edit": spec}

    def units(shots):
        return work._desired_units(CID, w, {**base, "shots": shots})

    full = units(None)
    one = units([0])
    sec = lambda us: round(sum(b - a for u in us for a, b in [u["span"]]), 2)
    chk("3.1 限定一个镜头 → 要处理的秒数变少",
        sec(one) < sec(full) and len(one) >= 1,
        f"整条 {sec(full)}s → 只第0镜 {sec(one)}s")

    bad = units([99])
    chk("3.2 非法镜号不会静默变成全片（那是钱）",
        len(bad) == 0, f"非法镜号 → {len(bad)} 段")

    empty = units([])
    chk("3.3 空数组仍按「不限」处理（老客户端的语义不变）",
        sec(empty) == sec(full), f"{sec(empty)}s vs {sec(full)}s")

    # 尺子自证：换一个镜头，范围必须跟着变，否则"限定"是假的。
    # 🩸 比**区间**不比秒数：最短时长会把不同镜头都补到同一个长度（4.0s vs 4.0s），
    # 只看秒数会把"限定失效"判成通过。
    # 🩸 镜号取**真实存在的最后一个**，不写死 2：写死 2 时，只有 1–2 镜的任务
    # 会拿"非法镜号 → 0 段"去跟 [0] 比，空集也能判绿，这条自证就假了。
    ids = sorted(int(s["i"]) for s in w["evidence"]["shots"])
    last = ids[-1] if ids else None
    other = units([last]) if last is not None and last != 0 else []
    span0 = [u["span"] for u in one]
    spanN = [u["span"] for u in other]
    chk("3.4 尺子自证：换镜头 → 范围跟着变",
        bool(spanN) and spanN != span0, f"第0镜 {span0} / 第{last}镜 {spanN}")

    return _report()


if __name__ == "__main__":
    sys.exit(main())
