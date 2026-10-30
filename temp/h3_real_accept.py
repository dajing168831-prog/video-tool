# -*- coding: utf-8 -*-
"""H3 提示词优化 · 真机验收（**花真钱**，必须主人点头才跑；不进 check_all）。

一次跑四条，全部打**跑着的后端**（127.0.0.1:8911 → 方舟），不是本地桩：

| # | 走哪条路 | 验什么 |
|---|---|---|
| 1 | `/prompt/convert` | 别家写好的成稿 → H3 成品（粘现成稿那条路，**从没真跑过**） |
| 2 | `/prompt/revise` | 拿 1 的成品 + 一张真截图说哪不对 → 只改那几处 |
| 3 | `/prompt/chat` + 参考素材 | 六段式（ref）能不能真出来（**ref 那把尺子从没真机验过**） |
| 4 | `/prompt/chat` + 明确体裁 | 9 个体裁包里挑得对不对（读它 `reads` 里实际读了哪份） |

素材全部**照抄现成的**，一个字不改：
- 1 用的原稿 = 采集库 `视频-·-cinematic-narrative-short.md` 第一条（真·别家成稿）
- 2 用的截图 = 现有成片里抽的一帧（真·出问题的画面）

结果落 `D:/tmp/h3accept/`，控制台打一张表。
"""
from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import httpx

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API = "http://127.0.0.1:8911"
ROOT = Path("C:/tmp/video-tool")
OUT = Path("D:/tmp/h3accept")
OUT.mkdir(parents=True, exist_ok=True)

HARVEST = Path("C:/tmp/ai-drama-handbook/research/harvest/视频-·-cinematic-narrative-short.md")
FFMPEG = Path("C:/Users/Administrator/Desktop/Jianying6.01/6.0.1.11779/ffmpeg.exe")
VIDEO = ROOT / "backend/data/clone/686dc4843949472a8e05c5167968d747/render/722947d6159a410195de63666f17912e/out.mp4"

MODEL = "pro"          # 顾客会在前端选 pro；这里显式传，不用后端兜底
DUR = 5


def source_prompt() -> str:
    """采集库里第一条，**逐字**取（不许我自己改一个字）。"""
    txt = HARVEST.read_text(encoding="utf-8")
    m = re.search(r"```text\n(.*?)\n```", txt, re.S)
    if not m:
        raise SystemExit("采集库里没找到代码块")
    return m.group(1).replace("\\n", "\n").strip()


def shot(path: Path) -> str:
    """从现成成片里抽一帧当「出问题的截图」（data URI）。"""
    jpg = OUT / "frame.jpg"
    if not jpg.exists():
        subprocess.run([str(FFMPEG), "-y", "-ss", "1", "-i", str(path),
                        "-frames:v", "1", "-q:v", "3", str(jpg)],
                       capture_output=True, timeout=120)
    if not jpg.exists() or jpg.stat().st_size < 1000:
        raise SystemExit("抽帧失败")
    return "data:image/jpeg;base64," + base64.b64encode(jpg.read_bytes()).decode()


def call(path: str, body: dict, tag: str, timeout: float = 600.0) -> dict:
    t0 = time.time()
    r = httpx.post(API + path, json=body, timeout=timeout)
    ms = (time.time() - t0) * 1000
    env = r.json()
    (OUT / f"{tag}.json").write_text(json.dumps(
        {"ms": round(ms), "status": r.status_code, "body": body, "resp": env},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  · {tag}  HTTP {r.status_code}  {ms/1000:.1f}s  biz_code={env.get('biz_code')}")
    return env


def say(tag: str, ok: bool, note: str = "") -> None:
    print(f"  {'✅' if ok else '❌'} {tag}" + (f"  {note}" if note else ""))


def reds(d: dict) -> list:
    r = d.get("red") or []
    return [(x if isinstance(x, str) else str(x))[:60] for x in r]


def main() -> int:
    src = source_prompt()
    print(f"原稿（采集库逐字）：{len(src)} 字")
    img = shot(VIDEO)
    print(f"截图：{len(img)//1024} KB\n")

    fails = 0

    # ---------------------------------------------------------------- 1 转换
    print("【1】转换：别家成稿 → H3")
    e1 = call("/api/prompt/convert", {
        "text": src, "duration": DUR, "model": MODEL,
        "target": "h3", "assets": [],
    }, "1-convert")
    d1 = e1.get("data") or {}
    p1 = d1.get("prompt") or ""
    ok1 = e1.get("code") == 200 and bool(p1)
    say("1a 出了成品", ok1, f"{len(p1)} 字")
    say("1b 判据全过", not reds(d1), str(reds(d1)))
    say("1c 三字段齐全（文生视频格式）",
        "integrated_multimodal_description" in p1 and "overall_soundscape" in p1, "")
    fails += (not ok1) + bool(reds(d1))
    print()

    # ---------------------------------------------------------------- 2 修订
    print("【2】修订：拿 1 的成品 + 一张真截图说哪不对")
    e2 = call("/api/prompt/revise", {
        "prompt": p1, "feedback": "人物脸太假了，像塑料，别的地方不用动",
        "images": [img], "duration": DUR, "model": MODEL, "target": "h3",
    }, "2-revise")
    d2 = e2.get("data") or {}
    p2 = d2.get("prompt") or ""
    ok2 = e2.get("code") == 200 and bool(p2)
    say("2a 出了修订稿", ok2, f"{len(p2)} 字")
    say("2b 判据全过", not reds(d2), str(reds(d2)))
    say("2c 结构没被改散（仍是三字段）",
        "integrated_multimodal_description" in p2, "")
    fails += (not ok2) + bool(reds(d2))
    print()

    # ---------------------------------------------------------------- 3 六段式
    print("【3】六段式：带参考素材走 ref 格式")
    msgs = [{"role": "user", "content": "用这张参考图里的女生，做一个她在地铁站台等车的镜头，电影感。"}]
    fixed = [{"kind": "image", "role": "reference_image", "seconds": 0,
              "label": "", "note": "主角外观参考"}]
    e3 = call("/api/prompt/chat", {
        "messages": msgs, "duration": 8, "model": MODEL, "target": "h3",
        "assets": fixed, "images": [], "sid": "",
    }, "3-ref-t1")
    d3 = e3.get("data") or {}
    if d3.get("action") == "ask":
        print("    它先问了 —— 追一轮把参数补齐")
        msgs = msgs + [{"role": "assistant", "content": d3.get("question") or ""},
                       {"role": "user", "content": "8 秒，16:9，你自己定，直接给我成品。"}]
        e3 = call("/api/prompt/chat", {
            "messages": msgs, "duration": 8, "model": MODEL, "target": "h3",
            "assets": fixed, "images": [], "sid": "",
        }, "3-ref-t2")
        d3 = e3.get("data") or {}
    p3 = d3.get("prompt") or ""
    say("3a 交付了成品", d3.get("action") == "write" and bool(p3), f"{len(p3)} 字")
    say("3b 真是六段式（有 subject_definitions）", "subject_definitions" in p3, "")
    say("3c kind=ref（尺子用的是 ref 那把）", d3.get("kind") == "ref", str(d3.get("kind")))
    say("3d 判据全过", not reds(d3), str(reds(d3)))
    say("3e 读了哪几份 skill", True, str(d3.get("reads")))
    fails += (not p3) + bool(reds(d3)) + (d3.get("kind") != "ref")
    print()

    # ---------------------------------------------------------------- 4 体裁挑选
    print("【4】体裁挑选：明确要纸艺定格动画")
    m4 = [{"role": "user", "content": "做一个纸艺剪纸风格、定格动画质感的 8 秒小短片，"
                                     "讲一只猫跳上桌子的动作过程。不要真人也不要三维动画。"}]
    e4 = call("/api/prompt/chat", {
        "messages": m4, "duration": 8, "model": MODEL, "target": "h3",
        "assets": [], "images": [], "sid": "",
    }, "4-genre-t1")
    d4 = e4.get("data") or {}
    if d4.get("action") == "ask":
        print("    它先问了 —— 追一轮")
        m4 = m4 + [{"role": "assistant", "content": d4.get("question") or ""},
                   {"role": "user", "content": "8 秒，16:9，故事你自己定，直接给我成品。"}]
        e4 = call("/api/prompt/chat", {
            "messages": m4, "duration": 8, "model": MODEL, "target": "h3",
            "assets": [], "images": [], "sid": "",
        }, "4-genre-t2")
        d4 = e4.get("data") or {}
    p4 = d4.get("prompt") or ""
    reads4 = d4.get("reads") or []
    hit = any("papercraft" in r for r in reads4)
    say("4a 交付了成品", d4.get("action") == "write" and bool(p4), f"{len(p4)} 字")
    say("4b 挑对了体裁包（读了 papercraft-stop-motion-explainer）", hit, str(reads4))
    say("4c 判据全过", not reds(d4), str(reds(d4)))
    say("4d 成品里没有三维/真人跑偏", "C4D" not in p4 and "Pixar" not in p4,
        p4[:120])
    fails += (not p4) + (not hit) + bool(reds(d4))
    print()

    print("=" * 60)
    print(f"真机验收：红 {fails} ｜ 明细在 {OUT}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
