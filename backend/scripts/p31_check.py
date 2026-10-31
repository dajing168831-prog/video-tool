# -*- coding: utf-8 -*-
"""复刻「逐段指令接口」判据 —— GET/POST `/clone/{cid}/prompts` 接线。

**手动跑**（不进一键自检）：它要一份真实任务当样本（原片 + 盘点缓存才走得到分段）。
脚本自己在 `data/clone/` 里挑一份能用的任务，**复制成临时任务**跑，跑完删干净，
不写真实任务目录、不调模型（`_run_agent` 用桩）。

验的六件事：
  1. 空态：没落盘时 GET 返回 `exists=False`；
  2. POST 生成后：每段标 `prompt_source=agent`、顶层也是 agent、文件落盘；
  3. GET 能读回落盘的那份；
  4. 参数没变再点 → 命中缓存，**不调模型**（不重复花钱）；
  5. `force=true` → 真的重写；
  6. 生成失败 → 接口**如实报错**（不能悄悄返回机器版，让用户以为看到的是官方版）；
  7. 入参校验与 `/plan` 同口径（空文案 / 冻结型号都拒）。

用法： D:/venvs/video-tool/Scripts/python.exe scripts/p31_check.py --model volc25
"""
from __future__ import annotations

import asyncio
import shutil
import sys
import uuid
from pathlib import Path

BACK = Path(__file__).resolve().parents[1]
if str(BACK) not in sys.path:
    sys.path.insert(0, str(BACK))
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from _model_gate import sel_or_exit  # noqa: E402

sel_or_exit(only="volc25")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.api import clone as api  # noqa: E402
from app.services import clone_agent as A  # noqa: E402
from app.services import clone_store as store  # noqa: E402

_n = _fail = 0


def check(name, got, want) -> None:
    global _n, _fail
    _n += 1
    ok = got == want
    if not ok:
        _fail += 1
    print(f"{'✅' if ok else '🔴'} {name}" + ("" if ok else f"\n     实际 {got!r} / 期望 {want!r}"))


def _pick_sample() -> Path | None:
    """挑一份跑得动的最小样本：有原片、有 recipe、有盘点缓存。"""
    root = BACK / "data" / "clone"
    if not root.is_dir():
        return None
    for d in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not d.is_dir():
            continue
        if not (d / "source.mp4").is_file() or not (d / "task.json").is_file():
            continue
        if not any((d / "inventory").glob("*.json")):
            continue
        return d
    return None


def _good(brief: dict) -> str:
    """按这一单**实际**的素材编号拼一条合格指令（不引用不存在的图号）。"""
    has_pic = any(r.get("pic") for r in (brief.get("refs") or []))
    has_audio = any(r.get("slot") == "audio" for r in (brief.get("refs") or []))
    pic_part = ("@图片1用于新人物的外观，不采用图片中的背景与构图。" if has_pic else "")
    audio_part = ("替换后的人物按@音频1的音色与台词说话，口型时点与它对齐。"
                  if has_audio else "")
    return (
        "【编辑目标】编辑@视频1，只把画面中央的男性修改为新人物。"
        "【原视频职责】@视频1是唯一编辑母版，负责原始场景、机位、镜头运动、"
        "动作轨迹、遮挡关系和事件顺序。"
        f"【目标素材职责】{pic_part}"
        "【编辑对象与范围】只修改画面中央的男性，不修改背景、道具与其他人物。"
        "【时间线继承】目标人物继承原人物每次出现、运动、遮挡和离开的时点、"
        "持续时长、路径与速度变化。" + audio_part)


def main() -> int:
    sample = _pick_sample()
    if sample is None:
        print("⛔ data/clone 里没有可用的样本任务（要有 source.mp4 + task.json + inventory）")
        return 2

    cid = uuid.uuid4().hex
    dst = store.task_dir(cid)
    shutil.copytree(sample, dst)
    # 样本任务可能已经生成过逐段指令（真人跑过一单就有了）。副本里先清掉，
    # 否则「空态」那两条测的是别人留下的文件，不是这个接口的行为。
    (dst / A.FILENAME).unlink(missing_ok=True)

    def stub(brief, **_kw):
        return [{"index": int(s["index"]), "prompt": _good(brief)}
                for s in brief["segments"]]

    real = A._run_agent
    A._run_agent = stub
    try:
        print(f"样本任务：{sample.name} → 临时 {cid}")
        print("\n== ① 空态 ==")
        check("一开始没有 prompts.json", A.load(cid), None)
        v0 = asyncio.run(api.clone_prompts_view(cid))
        check("GET 空态 exists=False", v0["data"]["exists"], False)

        print("\n== ② 生成 → 落盘 → 读回 ==")
        body = api.RenderIn(
            script="这是我们新写的一版文案。",
            edit=api.EditIn(person=True, person_ids=["P1"]),
            # 样本片可能整条都是静态镜：auto 分诊会把画面全给静帧重绘，
            # 没有视频段可交。用 whole（整条交给视频模型）才走得到逐段指令。
            regen_mode="whole",
            regen_channel="volc",
            regen_model="doubao-seedance-2-5-260628",
            allow_stretch=True,
        )
        r = asyncio.run(api.clone_prompts(cid, body, False))
        check("POST 成功（biz_code=0）", r["biz_code"], 0)
        d = r["data"]
        segs = d["segments"]
        if not segs:
            print("   blocked:", d.get("blocked"), "change:", d.get("change"))
        check("有段要发给模型", len(segs) > 0, True)
        check("每段标成 agent 写的",
              all(s.get("prompt_source") == "agent" for s in segs), True)
        check("顶层 prompt_source = agent", d.get("prompt_source"), "agent")
        check("落盘文件出现", (dst / A.FILENAME).is_file(), True)
        view = asyncio.run(api.clone_prompts_view(cid))
        check("GET 读回落盘的段数", len(view["data"]["segments"]), len(segs))

        print("\n== ③ 缓存与强制重写 ==")
        calls = {"n": 0}

        def counting(brief, **kw):
            calls["n"] += 1
            return stub(brief, **kw)

        A._run_agent = counting
        asyncio.run(api.clone_prompts(cid, body, False))
        check("同参数再点 → 命中缓存，不调模型", calls["n"], 0)
        asyncio.run(api.clone_prompts(cid, body, True))
        check("force=true → 真的重写", calls["n"], 1)

        print("\n== ④ 失败要如实报 ==")
        # 🩸 换掉 `_run_agent` 等于绕过 `check` 硬闸（硬闸的鉴别力在 p30_check 验）。
        #   这里验的是**接口层**：生成抛错时必须报错，不能悄悄给机器版。
        real_generate = A.generate

        def boom(*_a, **_kw):
            raise A.CloneAgentError("逐段指令没通过校验（测试桩）")

        A.generate = boom
        try:
            r2 = asyncio.run(api.clone_prompts(cid, body, True))
        finally:
            A.generate = real_generate
        check("生成失败 → 接口如实报错", r2["biz_code"], 8)

        print("\n== ⑤ 入参校验与 /plan 同口径 ==")
        r3 = asyncio.run(api.clone_prompts(
            cid, api.RenderIn(script="", edit=api.EditIn(person=True)), False))
        check("空文案 → 拒绝", r3["biz_code"], 6)
        r4 = asyncio.run(api.clone_prompts(
            cid, api.RenderIn(script="一句话文案", regen_model="MiniMax-H3"), False))
        check("冻结型号 → 拒绝", r4["biz_code"], 8)
    finally:
        A._run_agent = real
        shutil.rmtree(dst, ignore_errors=True)

    print(f"\n{_n - _fail}/{_n} 通过")
    return 1 if _fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
