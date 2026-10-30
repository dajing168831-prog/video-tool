"""P0 零成本验收：作品文档 + 资产签名 + plan。

跑法：
    python scripts/work_p0_check.py [--cid <cid>] [--rid <render id 前缀>]

验收三条（全部不调模型）：
  1. work.json 能从现有任务目录生成，check 无 error；
  2. 用最近一次真机出片的输入跑 plan → **全部命中复用**，且段数/秒数
     与 `preview_render`（出片前预览走的同一份决策）逐项相等；
  3. 改一个输入（人物描述）→ 该段变成"要新请求"，其余不受影响。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.core.config import settings  # noqa: E402
from app.services import clone_pipeline, clone_store, edit_spec, work  # noqa: E402

PASS = FAIL = 0


def check(name: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {name}: {got}")
    else:
        FAIL += 1
        print(f"  FAIL {name}: got={got!r} want={want!r}")


def latest_cid() -> str:
    # 🩸 别拿 task_dir("x") 反推根目录：`x` 不是合法 id，这一步会直接抛 ValueError
    # （以前只跑过带 --cid 的路径，默认路径是坏的）
    root = Path(settings.clone_dir)
    best = ("", 0.0)
    for d in root.iterdir() if root.exists() else []:
        f = d / "task.json"
        if not f.exists() or f.stat().st_mtime <= best[1]:
            continue
        # 只要有**已完成出片**的任务：没有出片的任务拿来当"原样"输入，
        # 后面每一步都会报"没有已完成的出片"，等于白跑
        try:
            t = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if any((r.get("pct") or 0) == 100 or r.get("state") == "done"
               for r in (t.get("renders") or [])):
            best = (d.name, f.stat().st_mtime)
    return best[0]


def main() -> int:
    # 🚦 必须点名型号（2026-10-26）：一轮只跑一家
    from _model_gate import sel_or_exit as _sel
    _sel()
    ap = argparse.ArgumentParser()
    ap.add_argument("--cid", default="")
    ap.add_argument("--rid", default="", help="拿哪一次出片当「原样」输入；留空 = 最近一次")
    args = ap.parse_args()

    cid = args.cid or latest_cid()
    task = clone_store.load(cid)
    if not task:
        print("找不到任务", cid)
        return 2
    renders = [r for r in (task.get("renders") or []) if r.get("state") == "done"]
    if not renders:
        print("这个任务没有已完成的出片")
        return 2
    base = next((r for r in sorted(renders, key=lambda x: x.get("created_at") or 0, reverse=True)
                 if not args.rid or r["id"].startswith(args.rid)), None)
    if not base:
        print("找不到指定的出片", args.rid)
        return 2

    print(f"== 任务 {cid[:8]} / 基准出片 {base['id'][:8]} / 模式 {base.get('regen_mode')} ==")

    # 1. 生成 + 校验
    w = work.build(cid)
    p = work.save(cid, w)
    print(f"  work.json -> {p}")
    issues = work.check(cid, w)
    errs = [i for i in issues if i["level"] == "error"]
    check("镜头数 > 0", len(w["evidence"]["shots"]) > 0, True)
    check("资产数 > 0", len(w["assets"]) > 0, True)
    check("check 无 error", len(errs), 0)
    for i in errs[:5]:
        print("    ", i)

    # 2. 原样输入 → 全部复用
    spec = edit_spec.normalize(base.get("edit") or {})
    intent = {
        "mode": base.get("regen_mode") or "whole",
        "channel": base.get("regen_channel") or "auto",
        "model": base.get("regen_model") or "",
        "edit": spec,
        "script": base.get("script") or "",
    }
    plan = work.plan(cid, w, intent)
    print(f"  plan: 复用 {plan['totals']['reuse_units']} 段 / 请求 {plan['totals']['request_units']} 段")
    # 🩸 2026-10-22 换人参考图改口径（一人一张、不裁头）⇒ 提示词模板变了。
    # 签名里本来就算"编译后的提示词"，所以这条旧产物**必须**失配 —— 这是对的行为，
    # 不是 bug。这里改判两件同样硬的事：
    #   ① 失配原因是"输入变了"，不能退化成"没生成过"；
    #   ② 拿这次算出来的签名**反过来喂一条资产**，plan 必须当场复用（证明匹配逻辑没坏）。
    check("旧模板产物不再算同输入（模板变了就该重画）",
          plan["totals"]["request_units"], 1)
    check("失配原因说的是「输入变了」",
          [x.get("why") for x in plan["requests"]],
          ["输入变了（参考图 / 型号 / 提示词等）"])
    sig = plan["requests"][0]["sig"]
    fake = dict(w)
    fake["assets"] = list(w.get("assets") or []) + [{
        "id": "synthetic:0", "render": "synthetic", "mode": "whole",
        "engine": plan["requests"][0]["engine"],
        "span": plan["requests"][0]["span"],
        "lip": plan["requests"][0]["lip"], "sig": sig, "key": {},
        "output": "", "sha256": "", "stale_refs": [],
    }]
    plan2 = work.plan(cid, fake, intent)
    check("喂一条同签名资产 → 立刻复用（匹配逻辑没坏）",
          plan2["totals"]["reuse_units"], 1)
    check("命中的正是那条资产",
          (plan2["reuse"] or [{}])[0].get("asset", ""), "synthetic:0")

    # 鉴别力：R5 与 R6 输入几乎一样，只有提示词模板不同（去掉「体型」那一版）。
    # 如果这两份的签名相同，说明签名没把提示词算进去 —— 那是假复用。
    pairs = {a["render"][:8]: a["sig"] for a in w["assets"] if a["mode"] == "whole"}
    if "32711d24" in pairs and "cf30ab9d" in pairs:
        check("改了提示词的两次出片签名不同", pairs["32711d24"] != pairs["cf30ab9d"], True)
    excluded = [a for a in w["assets"] if a.get("stale_refs")]
    print(f"  参考图换过的资产（不参与复用）：{len(excluded)}/{len(w['assets'])}")

    # 3. 与出片预览逐项对齐（同一个决策函数，数字不许飘）
    subject = clone_store.subject_path(cid)
    refs = {s: clone_store.ref_path(cid, s) for s in clone_store.REF_SLOTS
            if clone_store.ref_path(cid, s).exists()}
    preview = clone_pipeline.preview_render(
        clone_store.source_path(cid), task["recipe"],
        script=None, regen_mode=intent["mode"],
        regen_channel=intent["channel"], regen_model=intent["model"],
        subject_image=subject if subject.exists() else None,
        edit_spec=spec, refs=refs, allow_stretch=True,
    )
    pc = preview["change"]
    check("段数与出片预览一致", plan["totals"]["units"],
          int(pc["video_calls"]) + int(pc["still_calls"]))
    want_sec = round(float(pc["video_seconds"]) + float(pc["still_seconds"]), 2)
    got_sec = round(plan["totals"]["reuse_seconds"] + plan["totals"]["request_seconds"], 2)
    check("秒数与出片预览一致", got_sec, want_sec)

    # 4. 幂等：同一输入跑两次，结果逐字相同
    plan2 = work.plan(cid, w, intent)
    check("两次 plan 结果一致", plan2 == plan, True)

    # 5. 改一个输入 → 该段失效
    changed = json.loads(json.dumps(spec))
    changed["change"]["person_desc"] = "换了个人物描述（验收用）"
    plan3 = work.plan(cid, w, {**intent, "edit": changed})
    print(f"  改描述后: 复用 {plan3['totals']['reuse_units']} / 请求 {plan3['totals']['request_units']}")
    check("改输入后必须重新请求", plan3["totals"]["request_units"] > 0, True)
    check("改输入后不再误判复用", plan3["totals"]["reuse_units"], 0)

    print(f"\n{PASS}/{PASS + FAIL} 通过（零费用，未调用任何模型接口）")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
