# -*- coding: utf-8 -*-
"""Seedance 2.5 提示词对话接口验收（**零模型调用、零费用**）。

被测对象：`app/api/prompt.py` 的 `target=sd25` 分支 + `sd25_skill` + `ruler_sd25`。

🩸 与 `p20_check.py` **各写各的，一条断言都不共用**：2.0 的素材上限是
图 9 / 视频 3 / 音频 3、必挂画质兜底；2.5 是图 30 / 视频 10 / 音频 10 / 合计 50、
**禁止**自动加兜底（`sd25-pe:77`）。拿一家的断言跑另一家，验的不是同一件事。

大模型一律换成桩 —— 这里验的是**接线**；真模型效果要花钱，得主人点头
（`real_accept_sd25.py`）。

运行：python scripts/p25_check.py --model volc25
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import logging  # noqa: E402

import _model_lock  # noqa: E402

logging.disable(logging.INFO)

RESULT: list[tuple[bool, str, str]] = []


def ok(name: str, detail: str = "") -> None:
    RESULT.append((True, name, detail))


def bad(name: str, detail: str) -> None:
    RESULT.append((False, name, detail))


def expect(cond: bool, name: str, detail: str = "") -> bool:
    (ok if cond else bad)(name, "" if cond else detail)
    return cond


def _tool_call(name: str, args: dict | None = None, cid: str = "c1") -> dict:
    import json
    return {"id": cid, "type": "function",
            "function": {"name": name, "arguments": json.dumps(args or {},
                                                                ensure_ascii=False)}}


def _resp(tool_calls=None, content: str = "", tokens: int = 100) -> dict:
    msg: dict = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return {"choices": [{"message": msg}], "usage": {"total_tokens": tokens}}


def stub(seq):
    """按调用顺序返回 seq；同时记下每次收到的完整 messages。"""
    state = {"i": 0, "sys": [], "msgs": []}

    def _post(messages, **kw):
        i = min(state["i"], len(seq) - 1)
        state["i"] += 1
        # 🩸 存**副本**：`skill_agent.run` 之后会往同一个 list 里 append 工具结果，
        #   存引用会让「第 1 次调用看到的 messages」变成最后的状态（判据会看错）。
        state["msgs"].append([dict(m) for m in messages])
        state["sys"].append(messages[0]["content"] if messages else "")
        return seq[i]

    _post.state = state
    return _post


def main() -> int:
    if "--model" not in sys.argv:
        print("⛔ 必须点名型号：--model volc25")
        return 2
    i = sys.argv.index("--model")
    if (sys.argv[i + 1] if i + 1 < len(sys.argv) else "") != "volc25":
        print("⛔ 本文件只装 Seedance 2.5 的断言：--model volc25")
        return 2
    _model_lock.guard("volc25")

    from fastapi.testclient import TestClient

    from app.core.config import settings
    from app.main import app
    from app.api import prompt as prompt_api
    from app.services import sd25_skill, skill_agent
    import ruler_sd25

    #: 官方语料直接问尺子要，**不在这里另抄一份** —— 抄一份就漂一份。
    GOOD = next(t for n, g, t, _c in ruler_sd25.official_cases()
                if n == "guide 视频参考图编辑案例")
    #: 同一句加一个 2.0 的兜底词 → C2 必红（2.5 禁止自动加画质包，`sd25-pe:77`）
    BAD = GOOD + "电影质感"

    client = TestClient(app)
    real_post = skill_agent._post
    old_key = settings.ark_api_key

    def restore() -> None:
        skill_agent._post = real_post
        object.__setattr__(settings, "ark_api_key", old_key)

    def post(seq, body):
        ch = stub(seq)
        skill_agent._post = ch
        return client.post("/api/prompt/chat", json=body).json(), ch

    try:
        object.__setattr__(settings, "ark_api_key", "stub")

        # ---------------------------------------------------------- 1 入口
        r, _ch = post([_resp([_tool_call("ask_user", {"question": "几秒？"})])],
                      {"messages": [{"role": "user", "content": "我想拍个短片"}]})
        expect(r.get("code") == 200 and "还没选" in (r.get("msg") or ""),
               "1a 不传 target → 明确要求先选，不替顾客默认", str(r)[:200])
        expect("Seedance 2.5" in (r.get("msg") or ""),
               "1b 提示里三个入口都点名（顾客才知道有 2.5 这条）", str(r.get("msg"))[:200])

        r, _ch = post([_resp([_tool_call("ask_user", {"question": "几秒？"})])],
                      {"messages": [{"role": "user", "content": "拍个短片"}],
                       "target": "sd2.5"})
        expect(r.get("code") == 200 and "还没选" in (r.get("msg") or ""),
               "1c target 写错（sd2.5）不当成 2.5 —— 三家各认各的键，不做模糊匹配",
               str(r)[:200])

        # ---------------------------------------------------------- 2 skill 包
        rows = skill_agent.list_skills(sd25_skill.ROOT)
        expect(len(rows) == 1 and rows[0]["path"] == "sd25-pe/SKILL.md",
               "2a 列出官方 skill：只有 sd25-pe 一个", str([x["path"] for x in rows]))
        expect(len(rows[0]["description"]) >= 100,
               "2b skill 的自我介绍是真的（不是 `|` 这种占位）",
               rows[0]["description"][:60])
        base = sd25_skill.ROOT / "sd25-pe"
        sk = (base / "SKILL.md").read_text(encoding="utf-8")
        expect(len(sk) > 20000 and "Seedance 2.5 Prompt Optimizer" in sk,
               "2c SKILL.md 正文在位（996 行，不是占位文件）", f"{len(sk)} 字符")
        expect("## 目的" in sk and "## 核心工作流" in sk and "## 视频编辑模板" in sk,
               "2d 官方流程段落在（模型照着走的那几节）", sk[:80])

        # ---------------------------------------------------------- 3 只能读包内
        fs = skill_agent.SkillFS(sd25_skill.ROOT)
        expect("Seedance 2.5 Prompt Optimizer" in fs.read("sd25-pe/SKILL.md"),
               "3a 能读 SKILL.md 正文", "")
        expect("错误" in fs.read("../../../app/main.py"),
               "3b 路径穿越被拦住（读不到包外）", fs.read("../../../app/main.py")[:100])
        expect("错误" in fs.read("sd25-pe/nope.md"),
               "3c 读不存在的文件给错误、不抛异常", "")

        # ---------------------------------------------------------- 4 system 必须干净
        # 🩸 `_sys` 必须取自**真的跑过 sd25** 的那次调用。原来用的是第 1 段
        #   「不传 target」的桩 —— 那次请求在入口就返回了，根本没进 `sd25_skill`，
        #   system 是空串，4a 的「不含官方词」恒真（空集不含任何东西）。
        _r, ch_sys = post([_resp([_tool_call("ask_user", {"question": "几秒？"})])],
                          {"messages": [{"role": "user", "content": "拍个短片"}],
                           "target": "sd25", "duration": 8})
        _sys = "".join(ch_sys.state["sys"])
        expect(len(_sys) > 200,
               "4-0 system 真的送到了（不然后面几条是对空串判绿）", f"{len(_sys)} 字符")
        for kw, why in (("参数分离", "原则 7「参数分离」是 SKILL.md 正文"),
                        ("动态主体替换", "示例是 SKILL.md 正文"),
                        ("范围闭环", "编辑范围要求是 SKILL.md 正文")):
            expect(kw not in _sys, f"4a system 里没有官方正文：{why}", kw)
        expect(len(_sys) < 8000,
               "4b system 只有产品层（<8000 字符）", f"{len(_sys)} 字符")
        expect("npx" in _sys and "跳过" in _sys,
               "4c 自升级那段给了明确出口（npx 执行不了 → 跳过），不让模型空转",
               _sys[:300])

        # ---------------------------------------------------------- 5 固定条件
        r, ch6 = post([_resp([_tool_call("ask_user", {"question": "几秒？"})])],
                      {"messages": [{"role": "user", "content": "拍个短片"}],
                       "target": "sd25", "duration": 10})
        sys4 = ch6.state["sys"][0]
        expect("目标片长：10 秒" in sys4 and "4–30" in sys4,
               "5a 片长按 **2.5 的 4–30 秒**写进固定条件（不是 2.0 的 4–15）",
               sys4[-400:])

        _r, ch6b = post([_resp([_tool_call("ask_user", {"question": "几秒？"})])],
                        {"messages": [{"role": "user", "content": "拍个短片"}],
                         "target": "sd25"})
        sys4b = ch6b.state["sys"][0]
        expect("片长还没定" in sys4b and "该问" in sys4b and "目标片长" not in sys4b,
               "5b 没定片长时交代它去问，不替顾客定死", sys4b[-400:])
        expect("向后延长" not in sys4b and "分段" not in sys4b,
               "5c 片长条件不复述官方能力说明（SKILL.md「长视频与时间段」自己写）",
               sys4b[-200:])

        r, _ch = post([_resp([_tool_call("ask_user", {"question": "几秒？"})])],
                      {"messages": [{"role": "user", "content": "拍个短片"}],
                       "target": "sd25", "duration": 99})
        expect(r.get("code") == 200 and "已按 30 秒处理" in " ".join(
                   (r.get("data") or {}).get("warnings") or []),
               "5d 片长超 30 → 夹到 30 并如实提示（不静默改）",
               str((r.get("data") or {}).get("warnings"))[:200])

        r, ch5 = post([_resp([_tool_call("ask_user", {"question": "几秒？"})])],
                      {"messages": [{"role": "user", "content": "拍个短片"}],
                       "target": "sd25", "duration": 8,
                       "assets": [{"kind": "image", "role": "reference_image"},
                                  {"kind": "video", "role": "reference_video"},
                                  {"kind": "audio", "role": "reference_audio"}]})
        sys5 = ch5.state["sys"][0]
        expect("@图片1" in sys5 and "@视频1" in sys5 and "@音频1" in sys5,
               "5e 素材按 2.5 语法编号（@图片N / @视频N / @音频N）", sys5[-400:])
        expect("<Picture 1>" not in sys5 and "<主体1>" not in sys5,
               "5f 不照抄 H3 的 <Picture N> / 2.0 的 <主体N>", sys5[-400:])

        # ---------------------------------------------------------- 6 ask / deliver
        r, _ch = post([_resp([_tool_call("ask_user", {
            "question": "这段想要几秒？\n- 4 秒\n- 10 秒"})])],
            {"messages": [{"role": "user", "content": "拍个短片"}],
             "target": "sd25", "duration": 8})
        d = r.get("data") or {}
        expect(d.get("action") == "ask" and d.get("target") == "sd25",
               "6a 模型调 ask_user → action=ask，且标明是哪一家",
               str(d)[:200])

        r, _ch = post([_resp([_tool_call("read_skill", {"path": "sd25-pe/SKILL.md"})]),
                       _resp([_tool_call("deliver_prompt",
                                         {"prompt": GOOD, "note": "补全：镜头语言"})])],
                      {"messages": [{"role": "user", "content": "把这段改个风格"}],
                       "target": "sd25", "duration": 8})
        d = r.get("data") or {}
        expect(d.get("action") == "write" and d.get("prompt") == GOOD,
               "6b 模型调 deliver_prompt → action=write", str(d.get("action")))
        expect(d.get("note") == "补全：镜头语言",
               "6c 披露说明单独带出来（不进正文）", repr(d.get("note")))
        expect("sd25-pe/SKILL.md" in (d.get("reads") or []),
               "6d 读过哪些文件有记录", str(d.get("reads")))
        expect(d.get("tokens") and d.get("calls"),
               "6e 调用次数/token 有记账", str(d)[:200])
        expect(d.get("genre") == "free" and d.get("rules", 0) >= 40,
               "6f 交付时回带体裁与尺子条数（前端要显示）",
               f"genre={d.get('genre')} rules={d.get('rules')}")

        # 🩸 2.0 真机抓到「把问题写成回复、不调工具」，2.5 稿子更长更容易犯。
        #   提醒机制是**每家自己开**的（`skill_agent.run(nudge=)`），不是全局默认。
        r, _ch = post([_resp(content="我想跟你确认几个细节：\n1. 片长？\n2. 画幅？"),
                       _resp([_tool_call("ask_user", {"question": "片长几秒？"})])],
                      {"messages": [{"role": "user", "content": "拍个短片"}],
                       "target": "sd25", "duration": 0})
        d = r.get("data") or {}
        expect(d.get("action") == "ask",
               "6g 模型不调工具直接说话 → 先提醒一次，不把问题当成品",
               f"{d.get('action')} / {(d.get('prompt') or '')[:80]}")

        r, _ch = post([_resp(content="这画面感很强，我直接写。"),
                       _resp(content="还是一段话，仍然不用工具。")],
                      {"messages": [{"role": "user", "content": "拍个短片"}],
                       "target": "sd25", "duration": 0})
        d = r.get("data") or {}
        expect(d.get("action") == "write" and any(
                   "工具协议" in w for w in (d.get("warnings") or [])),
               "6h 提醒过仍不用工具 → 当正文收，但要标出「没按协议交付」",
               str(d.get("warnings"))[:160])

        # ---------------------------------------------------------- 7 判据回灌
        r, ch7 = post([_resp([_tool_call("deliver_prompt", {"prompt": BAD})]),
                       _resp([_tool_call("deliver_prompt", {"prompt": GOOD})])],
                      {"messages": [{"role": "user", "content": "把这段改个风格"}],
                       "target": "sd25", "duration": 8})
        d = r.get("data") or {}
        expect(ch7.state["i"] == 2, "7a 首轮判红后回灌一次", f"实际调用 {ch7.state['i']} 次")
        expect(d.get("prompt") == GOOD and not d.get("red"),
               "7b 照着红改了才交付，红的条目没跟着走", str(d.get("red"))[:200])
        _tool_out = [m.get("content") or ""
                     for m in ch7.state["msgs"][1] if m.get("role") == "tool"]
        expect(any("C2" in x and "sd25-pe:" in x for x in _tool_out),
               "7c 回灌时把红条目的 id 和官方出处一起告诉模型",
               str(_tool_out)[:300])

        r, _ch = post([_resp([_tool_call("deliver_prompt", {"prompt": BAD})])],
                      {"messages": [{"role": "user", "content": "把这段改个风格"}],
                       "target": "sd25", "duration": 8})
        d = r.get("data") or {}
        expect(r.get("biz_code") == 2 and d.get("red"),
               "7d 改不动就如实报红（biz_code=2），不假装通过", str(d.get("red"))[:200])

        # ---------------------------------------------------------- 8 官方原件没被动过
        def sha(p: Path) -> str:
            return hashlib.sha256(p.read_bytes()).hexdigest()

        got_sha = sha(base / "SKILL.md")
        man_p = Path("D:/tmp/official/sd25/MANIFEST.json")
        if man_p.exists():
            import json as _json
            man = {f["path"]: f["sha256"]
                   for f in _json.loads(man_p.read_text(encoding="utf-8"))["files"]}
            expect(got_sha == man.get("skill-sd25-pe.md"),
                   "8a skill 与官方 MANIFEST 逐字一致（搬目录没改内容）", got_sha)
        else:
            expect(got_sha.startswith("ee04557b"),
                   "8a skill 的 sha256 与登记值一致（无本机资料目录，按指纹比）", got_sha)

        # ---------------------------------------------------------- 9 披露不进正文
        W_NOTE = "补全：镜头语言\n改动：把「参考」改成「替换」"
        r, _ch = post([_resp([_tool_call("deliver_prompt",
                                         {"prompt": GOOD, "note": W_NOTE})])],
                      {"messages": [{"role": "user", "content": "把这段改个风格"}],
                       "target": "sd25", "duration": 8})
        d = r.get("data") or {}
        pr = d.get("prompt") or ""
        expect("补全：" not in pr and "素材提示：" not in pr,
               "9a 披露段落没混进提示词（顾客复制带不走）", pr[:300])
        expect("补全：" in (d.get("note") or "") and "替换" in (d.get("note") or ""),
               "9b 披露原样透传给前端", repr(d.get("note"))[:300])

        r, _ch = post([_resp([_tool_call("deliver_prompt", {"prompt": GOOD})])],
                      {"messages": [{"role": "user", "content": "把这段改个风格"}],
                       "target": "sd25", "duration": 8})
        expect((r.get("data") or {}).get("note") == "",
               "9c 没有披露段时 note 是空串不是 None（前端 v-if 才稳）",
               repr((r.get("data") or {}).get("note")))

        # ---------------------------------------------------------- 10 素材上限（2.5 自己的数）
        def _assets(n_img: int, n_vid: int = 0, n_aud: int = 0) -> list:
            return ([{"kind": "image", "role": "reference_image"}] * n_img
                    + [{"kind": "video", "role": "reference_video"}] * n_vid
                    + [{"kind": "audio", "role": "reference_audio"}] * n_aud)

        r, _ch = post([_resp([_tool_call("ask_user", {"question": "几秒？"})])],
                      {"messages": [{"role": "user", "content": "拍个短片"}],
                       "target": "sd25", "assets": _assets(30)})
        expect(r.get("code") == 200,
               "10a 图 30 张**不拦**（2.0 的 9 张上限不许搬过来）", str(r)[:200])

        r, _ch = post([_resp([_tool_call("ask_user", {"question": "几秒？"})])],
                      {"messages": [{"role": "user", "content": "拍个短片"}],
                       "target": "sd25", "assets": _assets(31)})
        # 🩸 拦的时候要走**自己的**报错路（`提示词对话失败：…`），不是掉进兜底的
        #   `提示词对话异常：SkillError: …`（那还会在日志里甩一份 traceback）。
        #   原来 prompt.py 的 except 元组里只列了 h3 和 2.0 的 SkillError。
        expect(r.get("biz_code") != 0 and "上限" in (r.get("msg") or "")
               and (r.get("msg") or "").startswith("提示词对话失败"),
               "10b 图超 30 就拦，且走 2.5 自己的报错文案（不漏进异常兜底）",
               str(r.get("msg"))[:200])

        # 🩸 官方四档是 30 / 10 / 10 / 合计 50 —— 前三个**加起来正好 50**，
        #   所以「分项都没超、合计超了」这种样本构造不出来，写成断言就是假判据。
        #   能验的是这层关系本身：合计闸存在且和分项之和一致（改任一档都要一起改）。
        expect((30, 10, 10, 50) == (prompt_api.MAX_IMG_25, prompt_api.MAX_VID_25,
                                   prompt_api.MAX_AUD_25, prompt_api.MAX_ALL_25)
               and 30 + 10 + 10 == 50,
               "10c 四档与官方一致，且分项之和恰等于合计（合计闸结构上不可独立触发）",
               f"{prompt_api.MAX_IMG_25}/{prompt_api.MAX_VID_25}/"
               f"{prompt_api.MAX_AUD_25}/{prompt_api.MAX_ALL_25}")

        r, _ch = post([_resp([_tool_call("ask_user", {"question": "几秒？"})])],
                      {"messages": [{"role": "user", "content": "拍个短片"}],
                       "target": "sd25", "assets": _assets(29, 10, 10)})
        expect(r.get("code") == 200,
               "10d 合计正好 49 → 放行（边界不许少算）", str(r)[:200])

        # ---------------------------------------------------------- 11 带图（多模态）
        IMG = "data:image/jpeg;base64,AAAA"
        packed = sd25_skill.with_images([{"role": "user", "content": "这儿不对"}], [IMG])
        expect(isinstance(packed[-1]["content"], list)
               and packed[-1]["content"][1]["image_url"]["url"] == IMG,
               "11a 截图挂在最后一条 user 消息上（方舟多模态格式）",
               str(packed[-1]["content"])[:200])
        r, ch_img = post([_resp([_tool_call("ask_user", {"question": "改哪儿？"})])],
                         {"messages": [{"role": "user", "content": "这儿不对"}],
                          "target": "sd25", "duration": 8, "images": [IMG]})
        _last = ch_img.state["msgs"][0][-1]
        expect(isinstance(_last.get("content"), list)
               and any(x.get("image_url") for x in _last["content"]),
               "11b 图没在链路里被丢掉（`_clean` 保留多模态 content）",
               str(_last)[:300])

        # ---------------------------------------------------------- 12 尺子（体裁 + 成对）
        def ids(s: str) -> list:
            ctx = ruler_sd25.ctx_for(s, genre=sd25_skill._genre_of(s))
            return [x[0] for x in ruler_sd25.check(s, ctx) if x[1] == "红"]

        for tpl, want in (("【编辑目标】\n…", "tpl"),
                          ("【声音编辑范围】\n…", "tpl-audio"),
                          ("把这段向后延长 5 秒", "ext"),
                          ("把 @图片1 作为首帧", "frame"),
                          ("一个女孩在雨夜等车", "free")):
            expect(sd25_skill._genre_of(tpl) == want,
                   f"12a 体裁按官方标记判：{want}", sd25_skill._genre_of(tpl))
        expect(not ids(GOOD),
               "12b 官方 free 语料零红（正样本先试尺子）", str(ids(GOOD)))
        expect("C2" in ids(BAD) and "C2" not in ids(GOOD),
               "12c 成对：加 2.0 兜底词「电影质感」必红 C2，删掉不红",
               str(ids(BAD)))
        expect(len(ruler_sd25.RULES) >= 40,
               "12d 尺子条数从规则表取，不写死", str(len(ruler_sd25.RULES)))

    finally:
        restore()

    passed = sum(1 for r in RESULT if r[0])
    for good, name, detail in RESULT:
        print(("  ✅ " if good else "  ❌ ") + name + ("" if good else f"\n      {detail}"))
    print(f"\nSeedance 2.5 提示词接口：通过 {passed} / {len(RESULT)}，红 {len(RESULT) - passed}")
    return 0 if passed == len(RESULT) else 1


if __name__ == "__main__":
    sys.exit(main())
