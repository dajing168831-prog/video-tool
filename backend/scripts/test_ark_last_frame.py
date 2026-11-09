"""尾帧返回自检 —— 不发网络请求，只验字段解析 / 落盘路径 / 指纹兼容 / payload 组装。

官方出处（2026-11-写，抓自本仓 backend/data/official）：
    - 创建参数 `return_last_frame`（默认 false）：
      2.5 `sd25/api-create-task.md:707`；2.0 `sd20/pull-2026-11-04/api-create.md:612`
    - 任务成功后的 `content.last_frame_url`：
      2.5 `sd25/pull-2026-11-03/api-get.md:65`；2.0 `sd20/pull-2026-11-04/api-get.md:65`
    - 官方用法原文：以上一个生成视频的尾帧作为下一个视频任务的首帧，连续生成多段。

运行：python backend/scripts/test_ark_last_frame.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import ark  # noqa: E402
from app.services import retry as retry_mod  # noqa: E402

PASS = FAIL = 0


def check(name: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {name}: {got!r}")
    else:
        FAIL += 1
        print(f"  FAIL {name}: got={got!r} want={want!r}")


def main() -> int:
    print("== 1. 官方响应形状 ==")
    d25 = {
        "id": "cgt-x",
        "status": "succeeded",
        "content": {
            "video_url": "https://x.test/out.mp4",
            "last_frame_url": "https://x.test/last.jpg",
        },
    }
    check("2.5 dict 形状", ark._find_last_frame_url(d25), "https://x.test/last.jpg")

    d_nested = {
        "content": [
            {"type": "video_url", "video_url": {"url": "https://x.test/out.mp4"}},
            {"type": "image_url", "last_frame_url": {"url": "https://x.test/last2.jpg"}},
        ]
    }
    check("列表/嵌套形状", ark._find_last_frame_url(d_nested), "https://x.test/last2.jpg")
    check("没请求就没有", ark._find_last_frame_url({"content": {"video_url": "x"}}), "")
    check("非 http 不认", ark._find_last_frame_url({"last_frame_url": "data:image/jpeg;base64,AA"}), "")

    print("== 2. 落盘路径 ==")
    check("同名 .last.jpg",
          str(ark.last_frame_path(Path("a") / "chunk_001.mp4")),
          str(Path("a") / "chunk_001.last.jpg"))

    print("== 3. 指纹兼容（开关不进 body） ==")
    body = ark.omni_body("测试", ref_images=["https://x.test/p.jpg"],
                         model="doubao-seedance-2-5-260628")
    check("omni_body 不带开关", "return_last_frame" in body, False)
    check("同 body 同指纹", ark._task_sig(body), ark._task_sig(dict(body)))

    print("== 4. 真正发出的 payload ==")
    captured: dict = {}

    class FakeResp:
        status_code = 200
        text = '{"id":"cgt-1"}'

        def json(self):
            return {"id": "cgt-1"}

    orig_post = retry_mod.post
    orig_headers = ark._headers
    orig_load = ark._load_tid
    orig_save = ark._save_tid
    orig_poll = ark._poll_urls
    orig_dl = ark._download_urls
    retry_mod.post = lambda c, url, headers=None, json=None: (captured.update(payload=json) or FakeResp())
    ark._headers = lambda: {}
    ark._load_tid = lambda out, body: ""
    ark._save_tid = lambda *a, **k: None
    ark._poll_urls = lambda tid, **k: ("https://x.test/out.mp4", "https://x.test/last.jpg")
    ark._download_urls = lambda out, v, last, *, t0: out
    try:
        sent = ark.omni_body("测试", model="doubao-seedance-2-5-260628")
        ark._run_video_task(sent, Path("x.mp4"), timeout=1, poll=0,
                            tag="出片", want_last_frame=True)
        check("要求尾帧时 payload 带 true", captured["payload"].get("return_last_frame"), True)
        check("其余字段原样", captured["payload"]["model"], sent["model"])

        ark._run_video_task(sent, Path("x.mp4"), timeout=1, poll=0, tag="编辑")
        check("没要求时不带该字段", "return_last_frame" in captured["payload"], False)
    finally:
        retry_mod.post = orig_post
        ark._headers = orig_headers
        ark._load_tid = orig_load
        ark._save_tid = orig_save
        ark._poll_urls = orig_poll
        ark._download_urls = orig_dl

    print(f"\n{PASS}/{PASS + FAIL} 通过")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
