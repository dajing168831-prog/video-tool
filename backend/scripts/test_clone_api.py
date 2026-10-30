"""复刻 API 端到端自检（不依赖外网，用本机样本片）。

覆盖：
  1. 后台分析任务从 queued → analyzed
  2. 轮询接口的状态推进
  3. 出片任务从 queued → done
  4. 成片/封面/关键帧的下载接口都能返回真文件
  5. 历史列表能列出刚做的任务

用法：
  python scripts/test_clone_api.py "C:/tmp/clone-samples/source.mp4" [--port 8913]
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Windows 控制台默认 GBK，打勾符号会炸 —— 统一成 UTF-8，坏字符替换而不是中断
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

import httpx  # noqa: E402

from app.services import clone_jobs, clone_store as store  # noqa: E402

SCRIPT = (
    "这个东西我用了三个月。真的比想象中好用。"
    "第一它不占地方。第二它几乎不用充电。第三价格还不贵。想要的话点左下角。"
)


def seed(sample: Path) -> str:
    """把样本片放进一个新建的复刻任务里，然后提交分析。

    这一步模拟的是 POST /clone/analyze 下载完之后的那一段。
    """
    cid = store.new_id()
    task = store.new_task(cid, meta={
        "platform": "local", "title": sample.name, "author": "",
        "cover": "", "url": "", "token": "",
    })
    store.save(task)
    dest = store.source_path(cid)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(sample, dest)
    if not clone_jobs.submit_analyze(cid, dest, url=""):
        raise RuntimeError("提交分析失败")
    return cid


def poll(client: httpx.Client, url: str, pick, done: set[str], timeout: float):
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        r = client.get(url)
        r.raise_for_status()
        data = r.json()["data"]
        state = pick(data)
        if state != last:
            print(f"    {state:<10} pct={data.get('pct') or (data.get('renders') or [{}])[-1].get('pct')}")
            last = state
        if state in done:
            return data
        time.sleep(0.6)
    raise TimeoutError(f"{url} 超时，最后状态 {last}")


def main() -> int:
    # 🚦 必须点名型号（2026-10-26）：一轮只跑一家
    from _model_gate import sel_or_exit as _sel
    _sel()
    ap = argparse.ArgumentParser()
    ap.add_argument("sample")
    ap.add_argument("--port", type=int, default=8913)
    args = ap.parse_args()

    sample = Path(args.sample)
    if not sample.exists():
        print(f"样本不存在: {sample}")
        return 2

    base = f"http://127.0.0.1:{args.port}/api"
    client = httpx.Client(timeout=60)
    checks: list[tuple[str, bool, str]] = []

    print("[1] 提交分析")
    cid = seed(sample)
    print(f"    cid={cid}")

    print("[2] 轮询分析")
    detail = poll(client, f"{base}/clone/{cid}", lambda d: d["state"],
                  {"analyzed", "failed"}, 120)
    ok_analyze = detail["state"] == "analyzed"
    checks.append(("分析完成", ok_analyze, detail.get("error", "")))
    if not ok_analyze:
        return report(checks)

    s = detail["summary"]
    print(f"    时长 {s['duration']}s {s['width']}x{s['height']} 镜头 {s['shot_count']} "
          f"节奏 {s['rhythm'].get('cuts_per_10s')}/10s")
    checks.append(("诊断摘要有内容", s["shot_count"] > 0 and s["duration"] > 0,
                   f"shots={s['shot_count']}"))

    print("[3] 提交出片")
    r = client.post(f"{base}/clone/{cid}/render", json={"script": SCRIPT, "mask_bottom": True})
    body = r.json()
    if body["biz_code"] != 0:
        checks.append(("提交出片", False, body["msg"]))
        return report(checks)
    rid = body["data"]["render_id"]
    checks.append(("提交出片", True, rid))

    print("[4] 轮询出片")
    rdetail = poll(client, f"{base}/clone/{cid}/render/{rid}", lambda d: d["state"],
                   {"done", "failed"}, 300)
    ok_render = rdetail["state"] == "done"
    checks.append(("出片完成", ok_render, rdetail.get("error", "")))
    if not ok_render:
        return report(checks)
    print(f"    成片 {rdetail['duration']}s，字幕 {len(rdetail['segments'])} 段")

    print("[5] 下载接口")
    for name, url, min_bytes in [
        ("成片", f"{base}/clone/{cid}/render/{rid}/file/out", 100_000),
        ("封面", f"{base}/clone/{cid}/render/{rid}/file/cover", 1_000),
        ("关键帧", f"{base}/clone/{cid}/kf/kf_000.jpg", 1_000),
        ("参考片", f"{base}/clone/{cid}/file/source", 100_000),
    ]:
        rr = client.get(url)
        ok = rr.status_code == 200 and len(rr.content) >= min_bytes
        checks.append((f"下载{name}", ok, f"{rr.status_code} {len(rr.content)}B"))

    print("[6] 历史列表")
    h = client.get(f"{base}/clone/history").json()["data"]
    ok_hist = any(x["id"] == cid for x in h)
    checks.append(("历史里有这条", ok_hist, f"{len(h)} 条"))

    print("[7] 文案改一版再出一次（配方复用）")
    r2 = client.post(f"{base}/clone/{cid}/render",
                     json={"script": "换个说法试试。这条只改文案，不再重新分析原片。",
                           "mask_bottom": False}).json()
    ok_reuse = r2["biz_code"] == 0
    if ok_reuse:
        rid2 = r2["data"]["render_id"]
        d2 = poll(client, f"{base}/clone/{cid}/render/{rid2}", lambda d: d["state"],
                  {"done", "failed"}, 300)
        ok_reuse = d2["state"] == "done"
        checks.append(("配方复用出片", ok_reuse, d2.get("error", "")))
        ff = client.get(f"{base}/clone/{cid}/render/{rid2}/file/out")
        checks.append(("第二版成片可下载", ff.status_code == 200, f"{len(ff.content)}B"))
    else:
        checks.append(("配方复用出片", False, r2["msg"]))

    return report(checks)


def report(checks: list[tuple[str, bool, str]]) -> int:
    print("\n===== 结果 =====")
    passed = 0
    for name, ok, note in checks:
        print(f"{'✅' if ok else '❌'} {name}" + (f"  ({note})" if note else ""))
        passed += bool(ok)
    print(f"{passed}/{len(checks)} 通过")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
