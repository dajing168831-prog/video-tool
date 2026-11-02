# -*- coding: utf-8 -*-
"""复刻「逐段指令」的**端到端**判据：预览写进去的那一份，出片会不会真的发出去。

🩸 为什么单有这个文件（2026-10-31 主人原话：「那些接口都是摆设来的，都要我花钱
   测失败了你才会端到端设置好」）：
   `p31_check` 验的是接口行为（用桩），它绿了不代表**出片那一路**会读到这份文件。
   第一次真跑就是这么栽的：预览写入了 agent 版，出片算签名时多出几个字段 →
   对不上 → 静默回落成机器版，用户花了钱才发现没用上。
   所以这条判据**必须走真实入口**，而且不能在提交请求前就下结论。

做法（零模型调用、零花费）：
  ① 真实预览接口 `_preview_call(with_agent=True)` 写 prompts.json（只把
     DeepSeek 那一步换成桩）；
  ② 真实出片入口 `clone_pipeline.render()`，把适配器 `submit` 换成探针 ——
     在第 1 段真正发请求前拦下，拿到**实际会发出去的那句话**；
  ③ 判：发出去的是不是就是落盘的那一版（逐字相同），且不是代码编译版。

跑法： D:/venvs/video-tool/Scripts/python.exe scripts/p43_check.py --model volc25
"""
from __future__ import annotations

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

import app.services.models as M  # noqa: E402
import app.services.video_edit as VE  # noqa: E402
from app.api import clone as api  # noqa: E402
from app.services import clone_agent as A, clone_pipeline, clone_store as store  # noqa: E402

MARK = "【AGENT-版-探针】"
_n = _fail = 0


def chk(name: str, ok: bool, detail: str = "") -> None:
    global _n, _fail
    _n += 1
    if not ok:
        _fail += 1
    print(f"{'✅' if ok else '🔴'} {name}" + ("" if ok else f"  [{detail}]"))


def _sample() -> tuple[str, dict] | tuple[None, None]:
    root = BACK / "data" / "clone"
    if not root.is_dir():
        return None, None
    for d in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not d.is_dir() or not (d / "source.mp4").is_file():
            continue
        tasks = [x for x in [d / "task.json"] if x.is_file()]
        if not tasks:
            continue
        try:
            task = store.load(d.name)
        except Exception:  # noqa: BLE001
            continue
        if task and task.get("renders"):
            return d.name, task
    return None, None


def main() -> int:
    src_cid, _ = _sample()
    if not src_cid:
        print("⛔ data/clone 里没有带出片记录的任务，跳过（不算通过）")
        return 2
    cid = uuid.uuid4().hex
    shutil.copytree(store.task_dir(src_cid), store.task_dir(cid))
    task = store.load(cid)
    item = task["renders"][-1]
    captured: dict = {}
    real_adapter = M.adapter_for
    real_run = A._run_agent

    class _Wrap:
        def __init__(self, inner):
            self._inner = inner
            self.caps = inner.caps

        def __getattr__(self, k):
            return getattr(self._inner, k)

        def submit(self, ctx):
            captured["prompt"] = ctx.get("prompt") or ""
            raise RuntimeError("探针：不发请求")

    try:
        print(f"样本任务：{src_cid} → 临时 {cid}")
        # ① 真实预览接口写（只换掉 DeepSeek 那一步）
        A._run_agent = lambda brief, **_kw: [
            {"index": int(s["index"]), "prompt": MARK + "编辑@视频1，只改点名的人物。"}
            for s in brief["segments"]]

        flat = dict(item.get("edit") or {})
        flat = {**flat.pop("change", {}), **flat}
        body = api.RenderIn(
            script=item.get("script") or "",
            script_lines=item.get("script_lines") or None,
            edit=api.EditIn(**flat),
            regen_prompt=item.get("regen_prompt") or "",
            regen_shots=item.get("regen_shots") or None,
            regen_mode=item.get("regen_mode") or "auto",
            regen_channel=item.get("regen_channel") or "auto",
            regen_model=item.get("regen_model") or "",
            subject_asset=item.get("subject_asset") or "",
            allow_stretch=bool(item.get("allow_stretch")),
            lang=item.get("lang") or "",
            speech_rate=item.get("speech_rate"),
            pronounce=item.get("pronounce") or {},
            tts_voice=item.get("tts_voice") or "",
        )
        (store.task_dir(cid) / A.FILENAME).unlink(missing_ok=True)
        pv = api._preview_call(cid, task, body, with_agent=True, agent_force=True)
        segs = pv.get("segments") or []
        chk("① 预览写出了逐段指令（要有段可发）", bool(segs),
            f"blocked={pv.get('blocked')!r} change={pv.get('change')}")
        chk("① 写的是 agent 版", pv.get("prompt_source") == "agent",
            repr(pv.get("agent_error") or ""))
        chk("① 文件真的落盘", (store.task_dir(cid) / A.FILENAME).is_file())
        if not segs:
            return 1

        # ② 真实出片入口（模型那一步换成探针）
        A._run_agent = real_run
        M.adapter_for = lambda **kw: _Wrap(real_adapter(**kw))
        VE.models.adapter_for = M.adapter_for
        try:
            clone_pipeline.render(
                store.source_path(cid), task["recipe"],
                script=item.get("script") or "",
                workdir=store.render_dir(cid, uuid.uuid4().hex),
                script_lines=item.get("script_lines") or None,
                mask_bottom=False, progress=None,
                regen_prompt=item.get("regen_prompt") or "",
                    regen_shots=item.get("regen_shots") or None,
                regen_mode=item.get("regen_mode") or "auto",
                regen_channel=item.get("regen_channel") or "auto",
                cid=cid, regen_model=(item.get("regen_model") or "").strip(),
                subject_image=(store.subject_path(cid)
                               if store.subject_path(cid).exists() else None),
                subject_asset=(item.get("subject_asset") or "").strip(),
                edit_spec=item.get("edit"),
                refs={s: store.ref_path(cid, s) for s in store.REF_SLOTS
                      if store.ref_path(cid, s).exists()},
                pronounce=item.get("pronounce") or {},
                tts_voice=(item.get("tts_voice") or "").strip(),
                allow_stretch=bool(item.get("allow_stretch")),
                lang=(item.get("lang") or "").strip(),
                speech_rate=item.get("speech_rate"),
            )
        except Exception as e:  # noqa: BLE001
            print(f"   出片在探针处停下：{type(e).__name__}: {str(e)[:80]}")

        # ③ 判「实际要发出去的那句话」
        sent = captured.get("prompt") or ""
        stored = A.load(cid) or {}
        first = ((stored.get("segments") or [{}])[0].get("prompt") or "")
        chk("② 出片真的走到了发请求那一步", bool(sent))
        chk("③ 发出去的就是 agent 版（不是静默回落）", sent.startswith(MARK),
            repr(sent[:60]))
        chk("③ 与落盘那一版逐字相同",
            bool(first) and sent.strip() == first.strip(), repr(first[:40]))
    finally:
        A._run_agent = real_run
        M.adapter_for = real_adapter
        VE.models.adapter_for = real_adapter
        shutil.rmtree(store.task_dir(cid), ignore_errors=True)

    print(f"\n{_n - _fail}/{_n} 通过")
    return 1 if _fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
