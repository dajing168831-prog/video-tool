"""一键自检：把**这个型号**的全部验收脚本串起来跑，最后给一张总账。

为什么要它（2026-10-29）：那几天来回切型号逐个跑，翻出三条问题 ——
  · H3 `reuse_audio` 没看音轨（真缺陷）；
  · 2.5 `_lip_line` 断言查的是旧的自造词（测试陈旧）；
  · 2.0 `test_extend` 的假适配器少了 `ref_images`，两条用例半路崩，
    **后面 10 条断言压根没执行**（34 → 44），报告却只写「2 条问题」。
根因不是"改一次坏一次"，而是这些脚本**没有任何东西逼着它们跑**：
哪个型号出片有问题才想起来跑哪个，坏掉的就在那儿躺几周。

判据（写死，不许放宽）：
  · 退出码 0 = 通过；`rc=2` 且是型号闸说的话 = **跳过**（不归这一轮管）；
  · 其余一律算红，包括超时和崩溃；
  · **跳过的单独列出来**，绝不并进"通过"里充数（空集不算通过）。
  · 每个 FAIL 都打印它自己的最后几行 —— 总账只说"红了"，等于没说话。

用法：
    python scripts/check_all.py --model volc25          # 全套
    python scripts/check_all.py --model volc25 --fast   # 跳过穷举（慢的那几关）
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

# 型号闸拒绝时的固定话术（`_model_gate.sel_or_exit`）—— 命中才当"跳过"，
# 别的一律当红。写成两条是因为它分两个分支说。
_SKIP_HINTS = ("本脚本只验", "必须点名型号")

#: (标签, 脚本名, 参数, 要不要带 --model, 慢不慢)
#: 🩸 `--fast` 只砍最后一项 = True 的（穷举/全量扫描），其余照跑。
REGISTRY: list[tuple[str, str, tuple[str, ...], bool, bool]] = [
    # ---------------- 单元 / 逻辑 ----------------
    ("编辑规格·本型号", "test_edit_spec.py", (), True, False),
    ("音频模式", "test_audio_modes.py", (), True, False),
    ("型号档位表", "test_model_specs.py", (), True, False),
    ("多人参考图", "test_person_refs.py", (), True, False),
    ("多版本缓存", "test_multi_version.py", (), True, False),
    ("编辑逻辑", "test_video_edit_logic.py", (), True, False),
    # 🩸 2026-10-30：`_fit_segment` 此前零判据 → 480×836（差 1.6% 到像素下限）
    #   被"缩放不到 2%"的宽容条件放过，整条片子发不出去。这条现在守着它。
    ("参考片段像素门槛", "test_fit_segment.py", (), True, False),
    ("分诊", "test_triage.py", (), True, False),
    ("台词/转录", "test_transcript.py", (), True, False),
    ("切镜检测", "test_shot_detect.py", (), True, False),
    ("切点精修", "test_refine_cuts.py", (), True, False),
    ("语音时长估算", "test_speech_est.py", (), True, False),
    ("读音校正", "test_pronounce.py", (), True, False),
    ("质检", "test_qc.py", (), True, False),
    ("视觉盘点", "test_vision_plan.py", (), True, False),
    ("方案预览", "test_plan_preview.py", (), True, False),
    ("音色目录", "test_voice_catalog.py", (), True, False),
    ("素材去重", "test_source_dedupe.py", (), True, False),
    ("人像外观", "test_subject_look.py", (), True, False),
    # ---------------- 接线 / 分离 ----------------
    ("全链路接线", "test_whole_wiring.py", (), True, False),
    ("人声分离+混音", "test_separate.py", (), True, False),
    # ---------------- 延长（按型号挑一个）----------------
    # 🩸 2026-10-31：`test_extend.py`（2.0）随复刻视频下架归档，只剩 2.5 这一条。
    ("延长·2.5", "test_extend_sd25.py", (), True, False),
    ("参考图顺序·2.5", "test_ref_order_sd25.py", (), True, False),
    ("分段台词·2.5", "test_spans_sd25.py", (), True, False),
    ("镜头来源·H3", "test_h3_shot_source.py", (), True, False),
    # ---------------- 提示词闸 ----------------
    ("提示词逐字检查", "prompt_lint_check.py", (), True, False),
    ("提示词型号标准", "prompt_model_standards_check.py", (), True, False),
    ("引文出处登记", "prompt_provenance_check.py", (), True, False),
    ("可指认性穷举", "identifiability_check.py", (), True, False),
    ("型号注册表", "model_registry_check.py", (), True, False),
    ("模型分离门", "model_separation_check.py", (), False, False),
    # ---------------- p 系列（历史关卡，全留着防回退）----------------
    ("p4 静帧", "p4_check.py", (), True, False),
    ("p5 参数", "p5_check.py", (), True, False),
    ("p6 结构", "p6_check.py", (), True, False),
    ("p7 逻辑", "p7_check.py", (), True, False),
    ("p9 出片链", "p9_check.py", (), True, False),
    ("p10 十项", "p10_check.py", (), True, False),
    ("p11 十一项", "p11_check.py", (), True, False),
    ("p12 十二项", "p12_check.py", (), True, False),
    ("p13 十三项", "p13_check.py", (), True, False),
    ("p14 十四项", "p14_check.py", (), True, False),
    ("p15 十五项", "p15_check.py", (), True, False),
    ("p16 身份核对", "p16_check.py", (), True, False),
    ("c6 翻译", "c6_check.py", (), True, False),
    # ---------------- 尺子（按型号只跑自己那把）----------------
    ("尺子·探针自证", "{R}.py", ("--probes",), True, False),
    ("尺子·当前产出", "{R}.py", ("--current",), True, False),
    ("尺子·官方校准", "{R}.py", ("--calib",), True, False),
    ("尺子·多变数扫描", "{R}.py", ("--sweep",), True, False),
    ("尺子·多维穷举", "{R}.py", ("--exhaustive",), True, True),
]

#: 型号 → 尺子文件名（锁的叫法和文件名不是一套）
RULER = {"volc20": "ruler_sd20", "volc25": "ruler_sd25", "h3": "ruler_h3"}

#: 按型号追加的关卡 —— 同一家模型里有**多个功能**时，每个功能一套自己的尺子。
#: 🩸 H3 现在有两条完全不同的链路：`ruler_h3`（Ref2VA 六段式，改已有视频）
#: 和 `ruler_h3_base`（T2VA/I2VA 创作模式）。两者规则方向相反（风格句位置），
#: 所以两把尺子都要跑，不能只挂一把（`docs/PROMPT-AUDIT-H3-BASE.md §十`）。
#: `need_model=False`：这些尺子自己读型号锁，不接 `--model`。
EXTRA = {
    # Seedance 2.0 的「写提示词」是独立一层（与出片层的 ruler_sd20 不是一回事）：
    # 素材标签、时间写法、兜底包全和 H3 相反，断言只能放这家自己的文件里。
    "volc20": [
        ("提示词优化·2.0 接口层", "p20_check.py", (), True, False),
    ],
    # 2.5 的接口层自己一套：素材上限 30/10/10/50、**禁止**画质兜底、
    # 结构化五段 —— 每一条都和 2.0 相反，断言不能共用。
    "volc25": [
        ("提示词优化·2.5 接口层", "p25_check.py", (), True, False),
        # 复刻的逐段编辑指令只走 2.5（H3 已冻结，见 `model_specs.MODELS`）。
        # 零费用：全程 `post` 桩，不调模型、不出片。
        ("复刻·逐段指令", "p30_check.py", (), True, False),
    ],
    "h3": [
        ("尺子·创作模式自证", "ruler_h3_base.py", ("--probes",), False, False),
        ("尺子·创作模式校准", "ruler_h3_base.py", ("--calib",), False, False),
        ("尺子·创作模式产出", "ruler_h3_base.py", ("--current",), False, False),
        ("尺子·创作模式扫描", "ruler_h3_base.py", ("--sweep",), False, False),
        ("尺子·创作模式穷举", "ruler_h3_base.py", ("--exhaustive",), False, True),
        ("提示词优化·接口层", "p18_check.py", (), True, False),
        # p18 两块：C/R=生成转换修订（生产路），A=接口→agent 的接线
        # （p21 只测执行器、不经 HTTP，这条只有 p18 覆盖）。
        ("提示词优化·转换路由", "p19_check.py", (), True, False),
        # 2026-10-30：提示词优化改成 agent 自己读 skill 包（9 个体裁 skill）。
        # p18 验的是旧的「一次调用」那条路，这条验新的。
        ("提示词优化·agent 读 skill", "p21_check.py", (), True, False),
        ("p17 JPG采样", "p17_check.py", (), True, False),
        # 复刻的逐段指令：H3 自己那套（英文六段式）。零费用：全程 `post` 桩。
        # 和 2.5 的 p30 平级、不共用断言 —— 两套模板不通用。
        ("复刻·逐段指令·H3", "p46_check.py", (), True, False),
    ],
}

#: 明确**不**纳入的，连同原因 —— 不写出来就会被当成"已经验过"。
NOT_INCLUDED = [
    ("test_providers_real.py", "真打外部服务（联网/可能花钱），要主人放行"),
    ("test_clone_api.py", "要起 HTTP 服务 + 真实样本片"),
    ("test_ark_ingest.py", "要真实素材与 OSS 上传"),
    ("test_voice_clone.py", "要真 key"),
    ("work_p0_check.py", "要真实任务数据，空库直接 IndexError"),
    ("work_p1_check.py", "要真实任务数据，找不到任务就退出"),
    ("test_pipeline.py / test_render.py / test_auto_render.py / test_contact_sheet.py",
     "要样本片 + 长跑 ffmpeg，单独跑，不进一键自检"),
    ("real_accept_sd20.py / real_accept_sd25.py",
     "真打方舟、**花真钱**，要主人点头才跑（文件名故意不带 _check，防被一键自检扫进来）"),
]


def _run(script: str, args: tuple[str, ...], model: str | None,
         timeout: int) -> tuple[int, str]:
    cmd = [sys.executable, str(SCRIPTS / script), *args]
    if model:
        cmd += ["--model", model]
    # 🩸 子进程强制 UTF-8：好几个老脚本直接 print 中文，在 Windows 控制台默认
    #   GBK 下会变成一堆 `��`，总账里根本读不出红在哪一行。
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout,
                           env=env)
    except subprocess.TimeoutExpired:
        return 124, f"超时（>{timeout}s）"
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _reexec_in_venv() -> int | None:
    """解释器不对就换工程 venv 重跑；返回 None = 本来就是对的。

    🩸 2026-10-29：用系统 python 跑这里，`p5/p11–p15/台词/接线/c6` 九条会齐刷刷
    `ModuleNotFoundError: No module named 'fastapi'` —— 看起来像全线崩，其实是
    解释器不对。这种"环境假红"跟这几天清掉的假绿是一路货：**报告里一条红，
    就得有人花一轮去查**。让它自己换过去，别指望人记得用哪个 python。
    """
    try:
        import fastapi  # noqa: F401
        return None
    except Exception:  # noqa: BLE001
        pass
    if os.environ.get("CHECK_ALL_REEXEC"):
        return None                     # 换过还是不灵 → 别再套娃
    me = Path(sys.executable).resolve()
    for c in (os.environ.get("VIDEO_TOOL_PY"),
              "D:/venvs/video-tool/Scripts/python.exe",
              str(ROOT / ".venv" / "Scripts" / "python.exe")):
        if not c or not Path(c).exists():
            continue
        if Path(c).resolve() == me:
            continue
        # flush：子进程直接写同一个 fd，不刷的话这行会跑到总账中间去
        print(f"↪ 当前解释器没有 fastapi，换工程 venv 重跑：{c}\n", flush=True)
        env = dict(os.environ, CHECK_ALL_REEXEC="1")
        return subprocess.call([c, str(Path(__file__).resolve()),
                                *sys.argv[1:]], env=env)
    print("⛔ 当前解释器没装 fastapi，也没找到工程的 venv —— 不跑了（免得报 9 条假红）。")
    print("   用 venv 的 python 跑：D:/venvs/video-tool/Scripts/python.exe "
          "scripts/check_all.py --model volc20")
    return 2


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    rc = _reexec_in_venv()
    if rc is not None:
        return rc
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=["volc20", "volc25", "h3"])
    ap.add_argument("--fast", action="store_true", help="跳过穷举这类慢关卡")
    ap.add_argument("--timeout", type=int, default=600, help="单脚本超时秒数")
    a = ap.parse_args()

    # 🩸 先对锁：`_model_lock.guard` 在锁不符时 exit 3（不是 2），不先查的话
    #   这里会一口气报几十条红，看着像全线崩，其实只是锁没切。
    sys.path.insert(0, str(SCRIPTS))
    import _model_lock  # noqa: E402

    lock = _model_lock.current()
    if lock and lock != a.model:
        print(f"⛔ 当前锁在 **{_model_lock.MODELS.get(lock, lock)}**，"
              f"本轮点名 {_model_lock.MODELS.get(a.model, a.model)}。")
        print(f"   先切锁：python scripts/_model_lock.py {a.model}")
        return 2

    passed: list[str] = []
    skipped: list[tuple[str, str]] = []
    failed: list[tuple[str, int, str]] = []
    t_all = time.time()

    for label, tpl, args, need_model, slow in REGISTRY + EXTRA.get(a.model, []):
        if slow and a.fast:
            skipped.append((label, "--fast 跳过（穷举）"))
            continue
        script = tpl.format(R=RULER[a.model])
        if not (SCRIPTS / script).exists():
            skipped.append((label, f"脚本不存在：{script}"))
            continue
        t0 = time.time()
        rc, out = _run(script, args, a.model if need_model else None, a.timeout)
        dt = time.time() - t0
        last = [x for x in out.strip().splitlines() if x.strip()]
        tail = last[-1][:80] if last else ""
        if rc == 0:
            passed.append(f"{label}（{dt:.1f}s）")
            print(f"  ✅ {label:<18} {dt:>5.1f}s  {tail}")
        elif rc == 2 and any(h in out for h in _SKIP_HINTS):
            skipped.append((label, "型号闸：不归本轮"))
            print(f"  ⏭️  {label:<18}      不属于 {a.model}，跳过")
        else:
            failed.append((label, rc, out))
            print(f"  ❌ {label:<18} {dt:>5.1f}s  rc={rc}  {tail}")

    print("\n" + "=" * 78)
    print(f"总账（{a.model}，共 {time.time() - t_all:.1f}s）")
    print(f"  通过 {len(passed)} ｜ 跳过 {len(skipped)} ｜ **红 {len(failed)}**")
    if skipped:
        print("\n跳过（不算通过）：")
        for k, why in skipped:
            print(f"  · {k} —— {why}")
    if failed:
        print("\n红灯明细：")
        for k, rc, out in failed:
            lines = [x for x in out.strip().splitlines() if x.strip()]
            print(f"\n  ❌ {k}（rc={rc}）")
            for x in lines[-8:]:
                print(f"      {x[:150]}")
    print("\n未纳入一键自检的（原因）：")
    for k, why in NOT_INCLUDED:
        print(f"  · {k} —— {why}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
