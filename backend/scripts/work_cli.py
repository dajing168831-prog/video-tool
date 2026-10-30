"""作品文档的命令行入口：build / check / plan。

    python scripts/work_cli.py build --cid <cid>
    python scripts/work_cli.py check --cid <cid>
    python scripts/work_cli.py plan  --cid <cid> --intent intent.json

三个命令都**不调模型、不花钱**：plan 只做本地判定（要哪些请求、哪些已有资产能复用）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import work  # noqa: E402


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=1))


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_build = sub.add_parser("build", help="从现有任务目录生成 work.json")
    p_build.add_argument("--cid", required=True)

    p_check = sub.add_parser("check", help="校验引用是否成立")
    p_check.add_argument("--cid", required=True)

    p_plan = sub.add_parser("plan", help="算出这次要哪些请求、能复用哪些")
    p_plan.add_argument("--cid", required=True)
    p_plan.add_argument("--intent", required=True, help="intent.json 路径")
    p_plan.add_argument("--stale", action="store_true", help="忽略 work.json，重新扫描产物")

    args = ap.parse_args()

    if args.cmd == "build":
        w = work.build(args.cid)
        p = work.save(args.cid, w)
        _print({"saved": str(p), "shots": len(w["evidence"]["shots"]),
                "assets": len(w["assets"]), "source_sha": w["source"]["sha256"][:16]})
        return 0

    if args.cmd == "check":
        w = work.load(args.cid) or work.build(args.cid)
        issues = work.check(args.cid, w)
        errs = [i for i in issues if i["level"] == "error"]
        _print({"errors": len(errs), "warnings": len(issues) - len(errs),
                "issues": issues})
        return 1 if errs else 0

    # plan
    intent = json.loads(Path(args.intent).read_text(encoding="utf-8"))
    w = None if args.stale else work.load(args.cid)
    _print(work.plan(args.cid, w, intent))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
