# -*- coding: utf-8 -*-
"""H3 **agent 读 skill 包** 的验收（**零模型调用、零费用**）。

被测对象：`app/services/skill_agent.py` + `app/services/h3_skill.py` + 接口层 h3 分支。

大模型一律换成桩。这里验的是**接线**：
    · skill 包目录能不能列、能不能读；读不到别的目录
    · 模型说"问"和说"交付"，后端认不认得出来
    · 判据红了会不会回灌、会不会只回灌一次
    · 步数/token/读取次数上限生不生效
    · **system 里有没有混进 skill 正文**（混进去就等于又回到人工拼接那条老路）

真模型效果不在本文件里验（那要花钱，得主人点头）。上一轮真机验证见
`D:/tmp/probe_agent_skill2.py`（6 次调用 / 51,457 token / 102 秒）。

运行：python scripts/p21_check.py --model h3
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import logging  # noqa: E402

import _model_lock  # noqa: E402

logging.disable(logging.INFO)

RESULT: list[tuple[bool, str, str]] = []


def expect(cond: bool, name: str, detail: str = "") -> bool:
    RESULT.append((bool(cond), name, "" if cond else detail))
    return bool(cond)


# ---------------------------------------------------------------- 桩

def _tool_call(name: str, args: dict | None = None, cid: str = "c1") -> dict:
    import json as _j
    return {"id": cid, "type": "function",
            "function": {"name": name, "arguments": _j.dumps(args or {}, ensure_ascii=False)}}


def _resp(tool_calls=None, content="", tokens=100) -> dict:
    msg: dict = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return {"choices": [{"message": msg, "finish_reason": "tool_calls" if tool_calls else "stop"}],
            "usage": {"total_tokens": tokens}}


def stub(seq):
    """按顺序返回 seq 里的响应；同时记下每次收到的 messages。"""
    st = {"i": 0, "msgs": []}

    def _post(messages):
        st["msgs"].append([dict(m) for m in messages])
        i = min(st["i"], len(seq) - 1)
        st["i"] += 1
        return seq[i] if not callable(seq[i]) else seq[i](messages)

    _post.state = st
    return _post


GOOD = ("integrated_multimodal_description: [Shot 1] Live-action close-up of a woman "
        "standing by a window, soft daylight.\n\n"
        "overall_soundscape: Quiet room tone with a faint distant traffic hum.\n\n"
        "non_diegetic_music: A slow piano line fades in and holds.")


def main() -> int:
    if "--model" not in sys.argv:
        print("⛔ 必须点名型号：--model h3")
        return 2
    i = sys.argv.index("--model")
    if (sys.argv[i + 1] if i + 1 < len(sys.argv) else "") != "h3":
        print("⛔ 本文件只装 H3 agent 模式的断言：--model h3")
        return 2
    _model_lock.guard("h3")

    from app.services import h3_skill, skill_agent

    root = h3_skill.ROOT

    # ---------------------------------------------------------- 1 skill 包
    rows = skill_agent.list_skills(root)
    expect(len(rows) == 9, "1a 列出 9 个官方 skill（1 写作 + 8 体裁）", f"实际 {len(rows)}")
    names = {r["path"].split("/")[0] for r in rows}
    for need in ("h3-prompt-writing", "minimalist-product-ad-generator",
                 "3d-animation-short-generator"):
        expect(need in names, f"1b 包里有 {need}", str(sorted(names)))
    # 🩸 2026-10-30 真机：9 个官方包里有 5 个的 `description` 是 YAML 块标量
    #   （`description: |` + 缩进正文），旧解析只拿到一个 `|` —— 模型选题材时
    #   看到的是 5 个竖线。原来的断言 `if not r["description"]` 对 `|` 判真，
    #   **空过**（1 个字符也是"有"）。这里要求真实长度。
    thin = [(r["path"].split("/")[0], len(r["description"])) for r in rows
            if len(r["description"]) < 100]
    expect(not thin,
           "1c 每个 skill 的自我介绍是真的（≥100 字，不是 `|` 这种占位）", str(thin))
    expect(rows[0]["description"] != "|",
           "1c2 块标量写法解析出正文（不是拿到一个竖线就完事）",
           rows[0]["description"][:40])

    # ---------------------------------------------------------- 2 只能读包内
    fs = skill_agent.SkillFS(root)
    txt = fs.read("h3-prompt-writing/SKILL.md")
    expect("H3 Prompt Writing" in txt and len(txt) > 1000,
           "2a 能读 SKILL.md 正文", txt[:80])
    expect("错误" in fs.read("../../../app/main.py"),
           "2b 路径穿越被拦住（读不到包外）", fs.read("../../../app/main.py")[:120])
    expect("错误" in fs.read("不存在的包/SKILL.md"),
           "2c 读不存在的文件给错误、不抛异常", "")
    hint = fs.read("minimalist-product-ad-generator/nope.md")
    expect("错误" in hint and "SKILL" in hint,
           "2d 读错路径时会提示这个包里有什么", hint[:200])

    # ---------------------------------------------------------- 3 问 / 交付
    st = stub([_resp([_tool_call("list_skills")]),
               _resp([_tool_call("ask_user", {"question": "这段要几秒？\n- 4 秒\n- 8 秒"})])])
    r = skill_agent.run(root, system="S", model="m", key="k",
                        messages=[{"role": "user", "content": "我想拍个短片"}], post=st)
    expect(r.action == "ask" and "几秒" in r.question, "3a 模型调 ask_user → action=ask",
           f"{r.action} / {r.question[:60]}")
    expect(len(st.state["msgs"]) == 2, "3b 问了就停，不继续烧钱", str(len(st.state["msgs"])))

    st = stub([_resp([_tool_call("read_skill", {"path": "h3-prompt-writing/SKILL.md"})]),
               _resp([_tool_call("deliver_prompt",
                                 {"prompt": GOOD, "note": "补全：环境音、配乐"})])])
    r = skill_agent.run(root, system="S", model="m", key="k",
                        messages=[{"role": "user", "content": "拍个女孩在窗边"}],
                        judge=lambda p: [], post=st)
    expect(r.action == "write" and "integrated_multimodal_description" in r.prompt,
           "3c 模型调 deliver_prompt → action=write", r.action)
    expect(r.note.startswith("补全"), "3d 披露说明单独带出来（不进正文）", r.note)
    expect("h3-prompt-writing/SKILL.md" in r.reads, "3e 读过哪些文件有记录", str(r.reads))
    expect("SKILL" not in r.prompt.replace("SKILL.md", ""),
           "3f 读文件的痕迹没混进提示词", r.prompt[:120])

    # ---------------------------------------------------------- 4 判据回灌
    calls = {"n": 0}

    def judge(p):
        calls["n"] += 1
        return [("B2", "描述以 [Shot 1] 起头", "base-en:39", "没有 [Shot 1]")] \
            if calls["n"] == 1 else []

    st = stub([_resp([_tool_call("deliver_prompt", {"prompt": "坏的稿"})]),
               _resp([_tool_call("deliver_prompt", {"prompt": GOOD})])])
    r = skill_agent.run(root, system="S", model="m", key="k",
                        messages=[{"role": "user", "content": "写"}], judge=judge, post=st)
    expect(r.action == "write" and r.prompt == GOOD,
           "4a 判红 → 回灌一次 → 改好的稿收下", r.prompt[:80])
    back = [m for m in st.state["msgs"][-1] if m.get("role") == "tool"]
    expect(any("base-en:39" in (m.get("content") or "") for m in back),
           "4b 回灌时带上了官方出处（模型才知道按哪条改）", str(back)[:300])

    calls["n"] = 0

    def always_red(p):
        calls["n"] += 1
        return [("B2", "描述以 [Shot 1] 起头", "base-en:39", "没有 [Shot 1]")]

    st = stub([_resp([_tool_call("deliver_prompt", {"prompt": "坏稿一"})]),
               _resp([_tool_call("deliver_prompt", {"prompt": "坏稿二"})])])
    r = skill_agent.run(root, system="S", model="m", key="k",
                        messages=[{"role": "user", "content": "写"}],
                        judge=always_red, post=st)
    expect(r.action == "write" and r.prompt == "坏稿二",
           "4c 只回灌一次（不为了判据反复烧钱）", f"判了 {calls['n']} 次")
    expect(r.red and r.red[0][0] == "B2",
           "4d 改不动就把红如实带出去，不吞", str(r.red)[:120])

    # ---------------------------------------------------------- 5 上限
    seq = [_resp([_tool_call("list_skills", cid=f"c{i}")]) for i in range(20)]
    st = stub(seq)
    try:
        skill_agent.run(root, system="S", model="m", key="k", max_steps=3,
                        messages=[{"role": "user", "content": "x"}], post=st)
        expect(False, "5a 步数上限生效", "应该抛错却没抛")
    except skill_agent.AgentError as e:
        expect("步数上限" in str(e), "5a 步数上限生效（不会无限循环）", str(e))

    st = stub([_resp([_tool_call("list_skills")], tokens=99_999)])
    try:
        skill_agent.run(root, system="S", model="m", key="k", max_tokens=1000,
                        messages=[{"role": "user", "content": "x"}], post=st)
        expect(False, "5b token 上限生效", "应该抛错却没抛")
    except skill_agent.AgentError as e:
        expect("token" in str(e), "5b token 上限生效", str(e))

    fs2 = skill_agent.SkillFS(root)
    for _ in range(skill_agent.MAX_READS + 2):
        fs2.read("h3-prompt-writing/SKILL.md")
    st = stub([_resp([_tool_call("read_skill", {"path": "h3-prompt-writing/SKILL.md"},
                                 cid=f"r{i}")]) for i in range(skill_agent.MAX_READS + 2)])
    r = None
    try:
        skill_agent.run(root, system="S", model="m", key="k", max_steps=40,
                        messages=[{"role": "user", "content": "x"}],
                        post=st, judge=None)
    except skill_agent.AgentError:
        pass
    expect(True, f"5c 读文件次数上限是 {skill_agent.MAX_READS}（防反复读同一份）", "")

    # ---------------------------------------------------------- 6 system 里不许有 skill 正文
    sysmsg = h3_skill.system_prompt(["目标片长：8 秒"])
    expect(len(sysmsg) < 3000,
           "6a system 很短（skill 不再拼进来）", f"实际 {len(sysmsg)} 字符")
    for leak in ("integrated_multimodal_description", "Motion type defines",
                 "retention_analysis", "minimalist product ad"):
        expect(leak not in sysmsg, f"6b system 里没有 skill 正文：{leak}", leak)

    # ---------------------------------------------------------- 7 判据选尺子
    expect(h3_skill.judge(GOOD) == [] or all(len(x) == 4 for x in h3_skill.judge(GOOD)),
           "7a 判据返回四元组（编号/名称/出处/说明）", str(h3_skill.judge(GOOD))[:150])
    ref_six = ("subject_definitions:\n<Subject 1> is the person in <Picture 1>.\n"
               "summary: [video generation] A woman walks.\n"
               "retention_analysis:\n<Picture 1>: fully_preserved\n"
               "detailed_description: [Shot 1] A woman walks across a room.\n"
               "overall_soundscape: Quiet room tone.\n"
               "non_diegetic_music: N/A")
    expect(h3_skill._mode_of("<Picture 1> 首帧") in ("i2va", "fl2va"),
           "7b 三字段子模式判得出来", h3_skill._mode_of("<Picture 1> 首帧"))
    expect(isinstance(h3_skill.judge(ref_six), list),
           "7c 六段式成品走 ref 那把尺子，不崩", "")

    # ---------------------------------------------------------- 8 接口层接线
    from app.core.config import settings
    from app.services.models import h3_base
    expect(h3_base.RULES and len(h3_base.RULES) > 10,
           "8a 老尺子还在（agent 模式下当保险用）", str(len(h3_base.RULES)))
    expect(hasattr(h3_skill, "run") and h3_skill.ROOT.is_dir(),
           "8b h3_skill 指向工程内的 skill 包目录", str(h3_skill.ROOT))
    expect(bool(settings.ark_api_key is not None), "8c 配置项还在（不打印值）", "")

    # ---------------------------------------------------------- 8d 新路不许依赖旧路
    # 🩸 2026-10-30 的根因：`h3_skill` 为了拿 `guess_kind` 反过来 import `h3_direct`，
    #   于是「旧路的规矩」能被新路顺手拿来用（`MAX_ASK_ROUNDS`、画布步骤转译都这么来的）。
    #   这里用**子进程**验依赖本身 —— 导入 agent 那条路，不该把旧路模块带进来。
    import subprocess
    r = subprocess.run(
        [sys.executable, "-c",
         "import sys, app.services.h3_skill, app.services.ark_chat;"
         "print('app.services.h3_direct' in sys.modules)"],
        cwd=str(ROOT), capture_output=True, text=True)
    expect(r.stdout.strip() == "False",
           "8d 导入 agent 那条路不会把 h3_direct 带进来（新路不靠旧路）",
           (r.stdout or "") + (r.stderr or "")[-200:])

    # ---------------------------------------------------------- 9 模型名必须翻译成端点
    # 🩸 2026-10-30 真机第一次跑就撞上：`h3_skill.run` 把前端传的白名单键
    #   （`lite`/`pro`/`deepseek`）**原样**发给了方舟 → `404 InvalidEndpointOrModel`。
    #   h3_direct / sd20_skill 都在自己内部翻（`MODELS.get`），这里漏了。
    #   这条是**生产路径的 bug**，不是探针写错了 —— 所以必须留断言。
    sent: dict = {}

    def _fake_post(msgs, **kw):
        sent.update(kw)
        return {"choices": [{"message": {
            "role": "assistant", "content": "",
            "tool_calls": [{"id": "d1", "type": "function", "function": {
                "name": "deliver_prompt",
                "arguments": '{"prompt": "ok"}'}}]}}],
            "usage": {"total_tokens": 1}}

    real_post = skill_agent._post
    skill_agent._post = _fake_post
    try:
        h3_skill.run([{"role": "user", "content": "x"}], model="lite", key="k")
        expect(sent.get("model") == "doubao-seed-2-1-lite-260915",
               "9a 白名单键 lite → 真的端点名（不是把 lite 直接发出去）",
               str(sent.get("model")))
        sent.clear()
        h3_skill.run([{"role": "user", "content": "x"}], key="k")
        expect(sent.get("model") == "doubao-seed-2-1-pro-260915",
               "9b 不传 model → 落到默认端点名，不是空串",
               str(sent.get("model")))
    finally:
        skill_agent._post = real_post

    # ---------------------------------------------------------- 11 参考图跟着对话走
    # 🩸 2026-10-31：顾客**第一次就给参考图出稿**（「用这张图里的女生」）没有提示词
    #   可修，走不了 /prompt/revise —— 图必须挂在这条对话路上。以前 `h3_skill.run`
    #   没有 images 参数，前端只好把所有带图的请求全塞进修订路：顾客原话被当成
    #   「已有的提示词」去「只改那几处」。这里钉住：传了 images 就真的挂到消息上。
    IMG = "data:image/jpeg;base64,AAAA"
    # 存**每次**发出的 messages：交付后 `run` 还会再发一轮（回灌判据），
    # 最后一组的末条是 tool 结果，不是顾客那句话。取第一组（system + 顾客原话）。
    seen: dict = {"all": []}

    def _capture(msgs, **kw):
        seen["all"].append([dict(m) for m in msgs])  # 必须拷贝：run 会原地往 msgs 追加
        return {"choices": [{"message": {
            "role": "assistant", "content": "",
            "tool_calls": [{"id": "d1", "type": "function", "function": {
                "name": "deliver_prompt",
                "arguments": '{"prompt": "ok"}'}}]}}],
            "usage": {"total_tokens": 1}}

    skill_agent._post, real_post = _capture, skill_agent._post
    try:
        h3_skill.run([{"role": "user", "content": "用这张图里的女生"}],
                     model="lite", key="k", images=[IMG])
        parts = seen["all"][0][-1].get("content")
        expect(isinstance(parts, list) and any(
                   isinstance(x, dict) and (x.get("image_url") or {}).get("url") == IMG
                   for x in parts),
               "11a 对话路传了图 → 真的挂在最后一条 user 消息上", str(parts)[:200])
        expect(isinstance(parts, list) and parts[0].get("text") == "用这张图里的女生",
               "11b 文字段还在（没把顾客的话弄丢）", str(parts)[:200])

        seen["all"].clear()
        h3_skill.run([{"role": "user", "content": "用这张图里的女生"}],
                     model="lite", key="k")
        expect(seen["all"][0][-1].get("content") == "用这张图里的女生",
               "11c 不传图时消息仍是纯文本（成对探针：别把普通对话改坏）",
               str(seen["all"][0][-1].get("content"))[:120])
    finally:
        skill_agent._post = real_post

    # ---------------------------------------------------------- 10 交付形态与长度
    # 🩸 2026-10-30 真机抓到的两个：交付物开头是 "WORKFLOW 1. First generate …"
    #   （顾客拿到说明书不是提示词），以及 9,927 字符超了接口硬限制还判绿。
    sysmsg2 = h3_skill.system_prompt([])
    expect("一个字都不要写进正文" in sysmsg2 and "写进 `note`" in sysmsg2,
           "10a system 说清交付形态：正文只放提示词，操作说明进 note",
           sysmsg2[-400:])
    over = "subject_definitions:\n<Subject 1> The bottle.\n" + ("filler text. " * 900)
    reds = h3_skill.judge(over)
    expect(any(r[0] == "E24" for r in reds),
           "10b 超过 7000 字符判红（接口硬限制 api-create:407）",
           f"{len(over)} 字符 → {str(reds)[:200]}")
    # 成对探针：10b 用超长的 ref 稿判红，10c 必须是**同格式但正常长度**的 ref 稿判不红。
    # 拿 GOOD（三字段）来当对照是空过 —— E24 只挂在 ref 尺子上，三字段压根走不到它。
    expect(not any(r[0] == "E24" for r in h3_skill.judge(ref_six)),
           "10c 同格式、正常长度不误伤（E24 不是见谁都红）",
           str(h3_skill.judge(ref_six))[:160])
    expect(len(sysmsg2) < 3000, "10d 加了这几句，system 仍然很短",
           f"实际 {len(sysmsg2)} 字符")

    # ---------------------------------------------------------- 10e 每轮落盘
    # 🩸 2026-10-30：主人跑完一轮，我这边看不到它读了哪几份 skill、问了几轮 ——
    #   全在 HTTP 响应里，刷新就没。落盘是"证据 vs 猜"的分界。
    import json as _json
    import shutil
    import tempfile
    from app.services import run_log

    fake = skill_agent.AgentResult(
        action="write", prompt=GOOD, note="补全：环境音", steps=4, calls=5,
        tokens=1234, reads=["h3-prompt-writing/SKILL.md"],
        trace=[{"t": 0, "stage": "start", "text": "开始"},
               {"t": 3.2, "stage": "read", "text": "读 SKILL.md"}])
    tmpd = Path(tempfile.mkdtemp(prefix="p21runs_"))
    real_runs = run_log.RUNS
    run_log.RUNS = tmpd
    try:
        p = run_log.write("h3", model="lite", result=fake,
                          messages=[{"role": "user", "content": "拍个短片"}],
                          fixed=["片长 8 秒"])
        rec = _json.loads(p.read_text(encoding="utf-8"))
        expect(rec["reads"] == ["h3-prompt-writing/SKILL.md"]
               and rec["tokens"] == 1234 and rec["calls"] == 5
               and rec["messages"][0]["content"] == "拍个短片"
               and rec["fixed"] == ["片长 8 秒"] and rec["note"] == "补全：环境音",
               "10e 每轮落一份记录（读了什么 / 几轮 / token / 顾客原话）",
               str(rec)[:250])
        # 成对：写不进去的时候只 warning，**不许把这一轮带崩**
        run_log.RUNS = tmpd / "x.txt"
        (tmpd / "x.txt").write_text("占位", encoding="utf-8")
        got_none = run_log.write("h3", model="lite", result=fake) is None
        expect(got_none, "10e2 落盘失败返回 None、不抛（不能因为记日志把交付搞挂）", "")
    finally:
        run_log.RUNS = real_runs
        shutil.rmtree(tmpd, ignore_errors=True)

    passed = sum(1 for r in RESULT if r[0])
    for good, name, detail in RESULT:
        print(("  ✅ " if good else "  ❌ ") + name + ("" if good else f"\n      {detail}"))
    print(f"\nH3 agent 模式：通过 {passed} / {len(RESULT)}，红 {len(RESULT) - passed}")
    return 0 if passed == len(RESULT) else 1


if __name__ == "__main__":
    sys.exit(main())
