"""同一原片重复解析 → 复用已有作品（零模型调用）。

背景：2026-10-22 主人只出片一次，历史里却出现两条同一作品 ——
第二条是同一条链接被再解析了一次（17:15 与 17:27 各一次 POST /clone/analyze）。
去重规则必须同时满足两件事，缺一个就会把人带错：
  ① 认得出同一条原片（平台 + 标题 + 作者）
  ② **出过片的优先** —— 否则会把用户带回"刚解析、一版都没出"的空作品

跑法：python scripts/test_source_dedupe.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings  # noqa: E402
from app.services import clone_store as store  # noqa: E402

rows: list[tuple[str, bool, str]] = []


def chk(name: str, ok, detail: str = "") -> None:
    rows.append((name, bool(ok), detail if not ok else ""))


def make(root: Path, cid: str, *, created: float, state: str = "analyzed",
         recipe: bool = True, renders: list | None = None,
         title: str = "下雨天的庭院", author: str = "某个作者",
         platform: str = "douyin") -> None:
    d = root / cid
    d.mkdir(parents=True, exist_ok=True)
    task = {
        "id": cid,
        "created_at": created,
        "state": state,
        "meta": {"platform": platform, "title": title, "author": author},
        "recipe": ({"shots": []} if recipe else None),
        "renders": renders or [],
    }
    (d / "task.json").write_text(__import__("json").dumps(task, ensure_ascii=False),
                                 encoding="utf-8")


def main() -> int:
    # 🚦 必须点名型号（2026-10-26）：一轮只跑一家
    from _model_gate import sel_or_exit as _sel
    _sel()
    tmp = Path(tempfile.mkdtemp(prefix="dedupe_", dir="D:/tmp"))
    old = settings.clone_dir
    try:
        object.__setattr__(settings, "clone_dir", tmp)  # frozen dataclass
        now = time.time()
        # 17:15 那条：出过一版
        make(tmp, "a" * 32, created=now - 800,
             renders=[{"id": "r1", "state": "done"}])
        # 17:27 那条：同片、更新，但一版都没出
        make(tmp, "b" * 32, created=now - 100, renders=[])
        # 别片 / 失败 / 没配方
        make(tmp, "c" * 32, created=now - 50, title="另一条片子")
        make(tmp, "d" * 32, created=now - 40, state="failed", title="失败那条")
        make(tmp, "e" * 32, created=now - 30, recipe=False, title="没配方那条")

        hit = store.find_recent_source("douyin", "下雨天的庭院", "某个作者")
        chk("同一条原片 → 认得出（平台+标题+作者）", hit is not None, str(hit))
        chk("出过片的那条优先，不被'刚解析的更新作品'顶掉",
            hit == "a" * 32, str(hit))
        chk("标题不同 → 不算同一片",
            store.find_recent_source("douyin", "完全不同的标题", "某个作者") is None)
        chk("平台不同 → 不算同一片",
            store.find_recent_source("kuaishou", "下雨天的庭院", "某个作者") is None)
        chk("平台/标题为空 → 不去重（防误伤）",
            store.find_recent_source("", "下雨天的庭院", "某个作者") is None
            and store.find_recent_source("douyin", "", "某个作者") is None)
        # 失败 / 没配方的不能当"已解析"复用
        chk("失败的、没配方的任务不会被复用",
            store.find_recent_source("douyin", "失败那条", "某个作者") is None
            and store.find_recent_source("douyin", "没配方那条", "某个作者") is None)
        # 超出时间窗（24h）也不算
        make(tmp, "f" * 32, created=now - 26 * 3600, title="昨天那条",
             renders=[{"id": "r9", "state": "done"}])
        chk("超过 24 小时 → 重新解析（不无限复用旧片）",
            store.find_recent_source("douyin", "昨天那条", "某个作者") is None)
    finally:
        object.__setattr__(settings, "clone_dir", old)
        shutil.rmtree(tmp, ignore_errors=True)

    ok = sum(1 for _, v, _ in rows if v)
    for name, v, detail in rows:
        print(f"  {'ok  ' if v else 'FAIL'} {name}" + (f"  [{detail}]" if detail else ""))
    print(f"\n{ok}/{len(rows)} 通过（零模型调用）")
    return 0 if ok == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
