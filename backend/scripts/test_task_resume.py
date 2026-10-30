"""提交过的任务号必须落盘：进程被杀之后，还能把结果取回来。

2026-10-24 付过的代价：出片到 52% 时后端被重启，任务号只存在内存里 →
平台那边跑完也取不回来，只能重新提交、重新花钱。

判据成对（少任何一边都会退化成另一种坏）：
  1. 请求一模一样 + 上次的任务号还在 → **不重新提交**，直接取回结果
  2. 请求变了（换提示词/换参考图）→ 必须重新提交（不许拿旧结果冒充）
  3. 上次的任务在平台侧已失效（failed / expired）→ 必须重新提交
  4. 从没提交过 → 提交一次

不花钱（不走网络）。

运行：python scripts/test_task_resume.py
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import ark  # noqa: E402

PASS = FAIL = 0


def check(name: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {name}: {got}")
    else:
        FAIL += 1
        print(f"  FAIL {name}: got={got!r} want={want!r}")


class Resp:
    def __init__(self, status=200, payload=None, content=b"\0" * 4096):
        self.status_code = status
        self._payload = payload or {}
        self.text = json.dumps(self._payload)
        self.content = content

    def json(self):
        return self._payload


class Client:
    def __init__(self, hook):
        self.hook = hook

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, **kw):
        return self.hook("post", url, kw)

    def get(self, url, **kw):
        return self.hook("get", url, kw)


def main() -> int:
    # 🚦 必须点名型号（2026-10-26）：一轮只跑一家
    from _model_gate import sel_or_exit as _sel
    _sel()
    work = Path(tempfile.mkdtemp(dir="D:/tmp", prefix="task_resume_"))
    out = work / "chunk_001.mp4"
    body = {"model": "m", "content": [{"type": "text", "text": "p"}], "duration": 5}
    calls = {"post": 0, "get": 0, "poll": 0, "dead": set()}

    real_client, real_poll = ark.httpx.Client, ark._poll_video_url

    def hook(kind, url, kw):
        if kind == "post":
            calls["post"] += 1
            return Resp(200, {"id": f"tid-{calls['post']}"})
        calls["get"] += 1
        return Resp(200, {}, content=b"\1" * 4096)

    def fake_poll(tid, *, timeout, poll):
        calls["poll"] += 1
        if tid in calls["dead"]:
            e = ark.ArkError("任务已过期")
            e.detail = {"status": "expired", "task_id": tid}
            raise e
        return "https://example.test/v.mp4"

    try:
        ark.httpx.Client = lambda *a, **kw: Client(hook)
        ark._poll_video_url = fake_poll

        print("== 第一次：没提交过 → 提交一次 ==")
        ark._run_video_task(body, out, timeout=1, poll=0, tag="编辑")
        check("提交了一次", calls["post"], 1)
        check("任务号落盘了", ark._task_state(out, body).exists(), True)
        tid1 = json.loads(ark._task_state(out, body).read_text(encoding="utf-8"))["tid"]
        check("落的是这次的任务号", tid1, "tid-1")

        print("== 进程被杀：成片没了，任务号还在 → 直接取，不重提交 ==")
        out.unlink()
        calls["poll"] = 0
        ark._run_video_task(body, out, timeout=1, poll=0, tag="编辑")
        check("没有重新提交", calls["post"], 1)
        check("拿旧任务号去取了", calls["poll"], 1)
        check("成片取回来了", out.stat().st_size > 1000, True)

        print("== 请求变了 → 必须重新提交 ==")
        body2 = dict(body, duration=9)
        ark._run_video_task(body2, out, timeout=1, poll=0, tag="编辑")
        check("换了请求就重新提交", calls["post"], 2)
        tid2 = json.loads(ark._task_state(out, body2).read_text(encoding="utf-8"))["tid"]
        check("任务号跟着换", tid2, "tid-2")

        print("== 🩸 重启后重跑 = 新单（新 rid）· 同一请求 → 跨单认领，不重提交 ==")
        # 2026-10-26 的现场：18:21 提交、18:23 后端重启、18:25 平台生成成功，
        # 但任务号写在旧 rid 目录里 → 重跑开了新单，只能再花一遍钱。
        root = work / "clone" / "cid1"
        root.mkdir(parents=True, exist_ok=True)
        (root / "task.json").write_text("{}", encoding="utf-8")
        o1 = root / "render" / "r1" / "triage" / "gen" / "chunk_001.mp4"
        o1.parent.mkdir(parents=True, exist_ok=True)
        ark._save_tid(o1, "tid-x", body2)
        o2 = root / "render" / "r2" / "triage" / "gen" / "chunk_001.mp4"
        o2.parent.mkdir(parents=True, exist_ok=True)
        check("新单能认领同一个任务号", ark._load_tid(o2, body2), "tid-x")
        _post_before = calls["post"]
        ark._run_video_task(body2, o2, timeout=1, poll=0, tag="编辑")
        check("新单没有重新提交", calls["post"], _post_before)
        check("新单拿到了成片", o2.stat().st_size > 1000, True)

        print("== 成对：**别的克隆任务**同一请求 → 不许串号（各花各的钱）==")
        root2 = work / "clone" / "cid2"
        root2.mkdir(parents=True, exist_ok=True)
        (root2 / "task.json").write_text("{}", encoding="utf-8")
        o3 = root2 / "render" / "r1" / "triage" / "gen" / "chunk_001.mp4"
        o3.parent.mkdir(parents=True, exist_ok=True)
        check("换一单就不认旧号", ark._load_tid(o3, body2), "")

        print("== 旧任务在平台侧失效 → 重新提交 ==")
        calls["dead"].add("tid-2")
        out.unlink()
        ark._run_video_task(body2, out, timeout=1, poll=0, tag="编辑")
        check("失效后重新提交", calls["post"], 3)
        check("成片照样拿得到", out.stat().st_size > 1000, True)

        print("== 任务号读坏了 → 按没有处理，不许崩 ==")
        ark._task_state(out, body2).write_text("{坏掉的 json", encoding="utf-8")
        check("坏文件当成没有", ark._load_tid(out, body2), "")
    finally:
        ark.httpx.Client = real_client
        ark._poll_video_url = real_poll
        shutil.rmtree(work, ignore_errors=True)

    print(f"\n{PASS}/{PASS + FAIL} 通过")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
