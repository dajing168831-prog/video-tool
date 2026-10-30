# -*- coding: utf-8 -*-
"""Seedance 2.0 提示词对话接口验收（**零模型调用、零费用**）。

被测对象：`app/api/prompt.py` 的 `target=sd20` 分支 + `sd20_skill` + `volc20_pe`。

🩸 2026-10-30 换方案（主人：「也是用 agents 调 2.0 skill，之前那些方案都不要了」）：
2.0 跟 H3 一样，**模型自己 `list_skills → read_skill`**，我们不再把官方原文
（1684 行）拼进 system。所以本文件最重要的一条判据从「原文有没有喂进去」
反过来变成「**system 里有没有混进官方正文**」—— 混进去就等于又回到人工拼接那条老路。

大模型一律换成桩 —— 这里验的是**接线**，真模型效果要花钱，得主人点头。

运行：python scripts/p20_check.py --model volc20
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
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


#: 官方 skill 路径 A 示例（`sd2-pe/SKILL.md`），一字未改 —— 拿它当「合格稿」。
GOOD = ("参考 @图片1 中的<主体1>（短发女孩），生成她在 @图片2 的咖啡店里吃蛋糕的画面。"
        "暖色调电影质感，画面稳定无变形，保持无字幕，不要生成水印，不要生成 Logo。")

#: 同一句只加一个绝对秒数 → V1 必红
BAD = GOOD.replace("生成她在", "0-3s 生成她在")


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
        print("⛔ 必须点名型号：--model volc20")
        return 2
    i = sys.argv.index("--model")
    if (sys.argv[i + 1] if i + 1 < len(sys.argv) else "") != "volc20":
        print("⛔ 本文件只装 Seedance 2.0 的断言：--model volc20")
        return 2
    _model_lock.guard("volc20")

    from fastapi.testclient import TestClient

    from app.core.config import settings
    from app.main import app
    from app.services import sd20_skill, skill_agent
    from app.services.models import volc20_pe

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

        # ---------------------------------------------------------- 2 skill 包
        rows = skill_agent.list_skills(sd20_skill.ROOT)
        expect(len(rows) == 1 and rows[0]["path"] == "sd2-pe/SKILL.md",
               "2a 列出官方 skill：只有 sd2-pe 一个（火山方舟官方就发布这一个）",
               str([x["path"] for x in rows]))
        expect(len(rows[0]["description"]) >= 100,
               "2b skill 的自我介绍是真的（不是 `|` 这种占位）",
               rows[0]["description"][:60])
        base = sd20_skill.ROOT / "sd2-pe"
        for rel, need in (("references/guide.md", "进阶公式"),
                          ("references/trouble.md", "重要内容前置"),
                          ("references/tips.md", "提示词"),
                          ("references/camera-terms.md", "镜头")):
            p = base / rel
            txt = p.read_text(encoding="utf-8") if p.exists() else ""
            expect(p.exists() and len(txt) > 500 and need in txt,
                   f"2c 官方原文在位：{rel}（含「{need}」）", f"{p} {len(txt)}")

        # ---------------------------------------------------------- 3 只能读包内
        fs = skill_agent.SkillFS(sd20_skill.ROOT)
        txt = fs.read("sd2-pe/SKILL.md")
        expect("Seedance 2.0 Prompt Optimizer" in txt and len(txt) > 3000,
               "3a 能读 SKILL.md 正文", txt[:80])
        expect("错误" in fs.read("../../../app/main.py"),
               "3b 路径穿越被拦住（读不到包外）", fs.read("../../../app/main.py")[:100])
        expect("错误" in fs.read("sd2-pe/nope.md"),
               "3c 读不存在的文件给错误、不抛异常", "")

        # ---------------------------------------------------------- 4 system 必须干净
        # 🩸 换方案后最要紧的一条：官方正文**不许**再进 system。
        #   混进去 = 又回到「我们替模型决定读哪份」那条老路（它漏过 8 份里的 1 份）。
        _sys = "".join(_ch.state["sys"])
        for kw, why in (("路径 A", "输出路径 A/B 是 SKILL.md 正文"),
                        ("八大要素", "八大要素是 SKILL.md 正文"),
                        ("重要内容前置", "通用优化原则是 trouble.md 正文"),
                        ("推、拉、摇、移、环绕、跟随、升、降、变焦", "运镜表是 references 正文")):
            expect(kw not in _sys, f"4a system 里没有官方正文：{why}", kw)
        expect(len(_sys) < 8000,
               "4b system 只有产品层（<8000 字符；旧方案 16 万+）", f"{len(_sys)} 字符")

        # ---------------------------------------------------------- 5 固定条件
        r, ch6 = post([_resp([_tool_call("ask_user", {"question": "几秒？"})])],
                      {"messages": [{"role": "user", "content": "拍个短片"}],
                       "target": "sd20", "duration": 6})
        sys4 = ch6.state["sys"][0]
        expect("目标片长：6 秒" in sys4, "5a 片长写进固定条件", sys4[-400:])

        _r, ch6b = post([_resp([_tool_call("ask_user", {"question": "几秒？"})])],
                        {"messages": [{"role": "user", "content": "拍个短片"}],
                         "target": "sd20"})          # duration=0 = 还没定
        sys4b = ch6b.state["sys"][0]
        expect("片长还没定" in sys4b and "该问" in sys4b and "目标片长" not in sys4b,
               "5b 没定片长时交代它去问，不替顾客定死", sys4b[-400:])
        # 🩸 2026-10-31 主人：「官方本来就有执行标准，我们自己又再要求一次？」
        #   片长条件**只交代事实**（还没定 / 目标几秒），能力说明在 `guide.md:259`
        #   «视频延长 vs 分段拼接»，模型自己读得到。这里原来讲了一遍，还讲错过。
        expect("向后延长" not in sys4b and "分段" not in sys4b and "延长" not in sys4b,
               "5c 片长条件不复述官方能力说明（guide.md:259 已写，讲一遍就多一套标准）",
               f"sys 长度 {len(sys4b)}｜尾部 {sys4b[-200:]!r}")

        r, ch5 = post([_resp([_tool_call("ask_user", {"question": "几秒？"})])],
                      {"messages": [{"role": "user", "content": "拍个短片"}],
                       "target": "sd20",
                       "assets": [{"kind": "image", "role": "reference_image"},
                                  {"kind": "video", "role": "reference_video"}]})
        sys5 = ch5.state["sys"][0]
        expect("@图片1" in sys5 and "@视频1" in sys5,
               "5d 素材按 2.0 语法编号（@图片N / @视频N）", sys5[-400:])
        expect("<Picture 1>" not in sys5,
               "5e 不照抄 H3 的 <Picture N>", sys5[-400:])

        # ---------------------------------------------------------- 6 ask / deliver
        r, _ch = post([_resp([_tool_call("ask_user", {
            "question": "这段想要几秒？\n- 4 秒\n- 8 秒"})])],
            {"messages": [{"role": "user", "content": "拍个短片"}],
             "target": "sd20", "duration": 6})
        d = r.get("data") or {}
        expect(d.get("action") == "ask" and "几秒" in (d.get("question") or ""),
               "6a 模型调 ask_user → action=ask", str(d)[:200])

        r, _ch = post([_resp([_tool_call("read_skill", {"path": "sd2-pe/SKILL.md"})]),
                       _resp([_tool_call("deliver_prompt",
                                         {"prompt": GOOD, "note": "补全：暖色调、画质包"})])],
                      {"messages": [{"role": "user", "content": "写一个女孩吃蛋糕"}],
                       "target": "sd20", "duration": 6})
        d = r.get("data") or {}
        expect(d.get("action") == "write" and d.get("prompt") == GOOD,
               "6b 模型调 deliver_prompt → action=write", str(d.get("action")))
        expect(d.get("note") == "补全：暖色调、画质包",
               "6c 披露说明单独带出来（不进正文）", repr(d.get("note")))
        expect("sd2-pe/SKILL.md" in (d.get("reads") or []),
               "6d 读过哪些文件有记录", str(d.get("reads")))
        expect("SKILL" not in (d.get("prompt") or "").replace("SKILL.md", ""),
               "6e 读文件的痕迹没混进提示词", (d.get("prompt") or "")[:120])
        expect(d.get("tokens") and d.get("calls"),
               "6f 调用次数/token 有记账（前端进度和成本都靠它）", str(d)[:200])

        # 🩸 2026-10-31 真机抓到：模型把「我想跟你确认几个细节」写成一段回复，
        #   **没调 ask_user** —— 兜底把它当成品交付，顾客拿到六个问题当提示词，
        #   判据还 0 红（提问文本不触发任何规则）。工具协议是产品层的约定，
        #   模型没照做必须先提醒一次。
        r, _ch = post([_resp(content="我想跟你确认几个细节：\n1. 片长？\n2. 画幅？"),
                       _resp([_tool_call("ask_user", {"question": "片长几秒？"})])],
                      {"messages": [{"role": "user", "content": "拍个短片"}],
                       "target": "sd20", "duration": 0})
        d = r.get("data") or {}
        expect(d.get("action") == "ask",
               "6g 模型不调工具直接说话 → 先提醒一次，不把问题当成品",
               f"{d.get('action')} / {(d.get('prompt') or '')[:80]}")

        # 成对：提醒过还是不用工具 → 只能当正文收，但必须标出来（不静默）
        r, _ch = post([_resp(content="这画面感很强，我直接写。"),
                       _resp(content="还是一段话，仍然不用工具。")],
                      {"messages": [{"role": "user", "content": "拍个短片"}],
                       "target": "sd20", "duration": 0})
        d = r.get("data") or {}
        expect(d.get("action") == "write" and any(
                   "工具协议" in w for w in (d.get("warnings") or [])),
               "6h 提醒过仍不用工具 → 当正文收，但要标出「没按协议交付」",
               str(d.get("warnings"))[:160])

        # ---------------------------------------------------------- 7 判据回灌
        r, ch7 = post([_resp([_tool_call("deliver_prompt", {"prompt": BAD})]),
                       _resp([_tool_call("deliver_prompt", {"prompt": GOOD})])],
                      {"messages": [{"role": "user", "content": "写一个女孩吃蛋糕"}],
                       "target": "sd20", "duration": 6})
        d = r.get("data") or {}
        expect(ch7.state["i"] == 2, "7a 首轮判红后回灌一次", f"实际调用 {ch7.state['i']} 次")
        expect(d.get("prompt") == GOOD and not d.get("red"),
               "7b 照着红改了才交付，红的条目没跟着走", str(d.get("red"))[:200])
        _tool_out = [m.get("content") or ""
                     for m in ch7.state["msgs"][1] if m.get("role") == "tool"]
        expect(any("V1" in x and "sd2-pe:" in x for x in _tool_out),
               "7c 回灌时把红条目的 id 和官方出处一起告诉模型",
               str(_tool_out)[:300])

        # 连续两轮都红 → 如实交付并带 red（吞掉比报错更糟）
        r, _ch = post([_resp([_tool_call("deliver_prompt", {"prompt": BAD})])],
                      {"messages": [{"role": "user", "content": "写一个女孩吃蛋糕"}],
                       "target": "sd20", "duration": 6})
        d = r.get("data") or {}
        expect(r.get("biz_code") == 2 and d.get("red"),
               "7d 改不动就如实报红（biz_code=2），不假装通过", str(d.get("red"))[:200])

        # ---------------------------------------------------------- 8 官方原件没被动过
        def sha(p: Path) -> str:
            return hashlib.sha256(p.read_bytes()).hexdigest()

        dg = {"skill": sha(base / "SKILL.md"),
              "guide": sha(base / "references" / "guide.md")}
        man_p = Path("D:/tmp/official/sd20/MANIFEST.json")
        if man_p.exists():
            import json as _json
            man = {f["path"]: f["sha256"]
                   for f in _json.loads(man_p.read_text(encoding="utf-8"))["files"]}
            expect(dg["skill"] == man.get("skill-sd2-pe.md"),
                   "8a skill 与官方 MANIFEST 逐字一致（搬目录没改内容）", dg["skill"])
            expect(dg["guide"] == man.get("guide.md"),
                   "8b guide 与官方 MANIFEST 逐字一致（搬目录没改内容）", dg["guide"])
        else:
            expect(dg["skill"].startswith("8836cdb2"),
                   "8a skill 的 sha256 与登记值一致（无本机资料目录，按指纹比）", dg["skill"])
            expect(dg["guide"].startswith("dd7fe63c"),
                   "8b guide 的 sha256 与登记值一致（无本机资料目录，按指纹比）", dg["guide"])

        # ---------------------------------------------------------- 9 披露不进正文
        # 官方 Step 4 要求披露补全/改动，但它**不是提示词的一部分**。
        # 走工具参数 `note`，顾客复制正文时天然带不走。
        W_NOTE = "补全：暖色调、画质包\n改动：把\"参考\"改成\"严格编辑\""
        r, _ch = post([_resp([_tool_call("deliver_prompt",
                                         {"prompt": GOOD, "note": W_NOTE})])],
                      {"messages": [{"role": "user", "content": "写一个女孩吃蛋糕"}],
                       "target": "sd20", "duration": 6})
        d = r.get("data") or {}
        pr = d.get("prompt") or ""
        expect(d.get("action") == "write" and "补全：" not in pr
               and "<<<NOTE>>>" not in pr,
               "9a 披露段落没混进提示词（顾客复制带不走）", pr[:300])
        expect("补全：" in (d.get("note") or "") and "严格编辑" in (d.get("note") or ""),
               "9b 披露原样透传给前端", repr(d.get("note"))[:300])

        r, _ch = post([_resp([_tool_call("deliver_prompt", {"prompt": GOOD})])],
                      {"messages": [{"role": "user", "content": "写一个女孩吃蛋糕"}],
                       "target": "sd20", "duration": 6})
        expect((r.get("data") or {}).get("note") == "",
               "9c 没有披露段时 note 是空串不是 None（前端 v-if 才稳）",
               repr((r.get("data") or {}).get("note")))

        # ---------------------------------------------------------- 10 素材上限
        r, _ch = post([_resp([_tool_call("ask_user", {"question": "几秒？"})])],
                      {"messages": [{"role": "user", "content": "拍个短片"}],
                       "target": "sd20",
                       "assets": [{"kind": "image", "role": "reference_image"}] * 10})
        expect(r.get("biz_code") != 0 and "上限" in (r.get("msg") or ""),
               "10a 素材超过 2.0 官方上限（图 9）就拦，不写出收不到的编号",
               str(r)[:200])

        # ---------------------------------------------------------- 10b 带图（多模态）
        # 🩸 2.0 的截图跟着对话走（顾客说「这儿不对」时文字往往只有一个字）。
        #   这条链路以前只有 `sd20_direct._with_images` 支持，换到 `skill_agent`
        #   之后**共用件的 `_clean` 会把 list content 当空**丢掉 —— 图白传。
        #   这里从「拼装」到「真的发给模型」整条走一遍，看最后一轮的 content 是不是数组。
        IMG = "data:image/jpeg;base64,AAAA"
        packed = sd20_skill.with_images([{"role": "user", "content": "这儿不对"}], [IMG])
        expect(isinstance(packed[-1]["content"], list)
               and packed[-1]["content"][1]["image_url"]["url"] == IMG,
               "10b 截图挂在最后一条 user 消息上（方舟多模态格式）",
               str(packed[-1]["content"])[:200])
        r, ch_img = post([_resp([_tool_call("ask_user", {"question": "改哪儿？"})])],
                         {"messages": [{"role": "user", "content": "这儿不对"}],
                          "target": "sd20", "duration": 6, "images": [IMG]})
        _last = ch_img.state["msgs"][0][-1]
        expect(isinstance(_last.get("content"), list)
               and any(x.get("image_url") for x in _last["content"]),
               "10c 图没在链路里被丢掉（`_clean` 保留多模态 content）",
               str(_last)[:300])
        expect(ch_img.state["msgs"][0][0]["content"].startswith("## 你怎么干活"),
               "10d system 仍是产品层那套（图不改变 system）", "")

        # ---------------------------------------------------------- 11 尺子（原文搬）
        # 依据 `sd2-pe:201-208`「特殊字符规范（强制使用）」+ `:160/:162` 的字幕/双胞胎兜底。
        # 🩸 每条都**成对**：正样本（官方原文）不判 + 只动一处的坏样本必判。
        # 只验「正样本不红」= 对空对象恒真，等于没验。
        A_DOC = ("参考 @图片1 中的<主体1>（短发女孩），生成她坐在窗边咖啡店里专注吃蛋糕的画面，"
                 "暖黄色光线柔和洒落。高清电影质感，画面稳定无变形，保持无字幕，"
                 "不要生成水印，不要生成 Logo。")
        B_DOC = ("整体设定为现代女生宿舍傍晚文戏。<主体1> 的面部特征参考 @图片1（大头照）；"
                 "镜头 1：中景平稳跟拍，<主体1> 走到门口。"
                 "镜头 2：舍友们抬头看向她，其中一人笑着问 {考得怎么样呀，过了吗}。"
                 "全程高清电影质感，人物面部稳定不变形，保持无字幕，不要生成水印；"
                 "视频全程禁止出现外形、着装、配饰完全一致的人物，禁止生成同款分身、双胞胎效果。")

        def ids(s: str) -> list:
            return [r[0] for r in volc20_pe.check(s)]

        for tag, doc in (("路径A", A_DOC), ("路径B", B_DOC)):
            expect(not [x for x in ids(doc) if x in ("V8", "V9", "V10", "V11")],
                   f"11a {tag} 官方原文不触发 V8–V11（正样本试尺子）", str(ids(doc)))
        expect("V8" in ids(A_DOC + "背景音乐用轻快的钢琴曲。")
               and "V8" not in ids(A_DOC + "（背景中播放着轻快的钢琴曲）。"),
               "11b 背景音乐：没（）判、有（）不判", str(ids(A_DOC + "背景音乐用轻快的钢琴曲。")))
        expect("V8" not in ids(A_DOC),
               "11c 不误伤主体注解 <主体1>（短发女孩）", str(ids(A_DOC)))
        expect("V9" in ids(A_DOC + "加入音效。")
               and "V9" not in ids(A_DOC + "加入音效<远处传来狗叫声>。"),
               "11d 音效：没<>判、有<>不判", str(ids(A_DOC + "加入音效。")))
        no_sub = A_DOC.replace("保持无字幕，", "")
        expect("V10" in ids(no_sub) and "V10" not in ids(A_DOC),
               "11e 字幕兜底：删掉判、有则不判", str(ids(no_sub)))
        expect("V10" not in ids(no_sub + "画面底部出现字幕，字幕内容为“欢迎光临”"),
               "11f 文字生成任务不要求挂无字幕兜底", str(ids(no_sub)))
        no_twin = B_DOC.replace(
            "视频全程禁止出现外形、着装、配饰完全一致的人物，禁止生成同款分身、双胞胎效果。", "")
        expect("V11" in ids(no_twin) and "V11" not in ids(B_DOC),
               "11g 双胞胎兜底：多人场景删掉判、有则不判", str(ids(no_twin)))
        expect("V11" not in ids(A_DOC), "11h 单人场景不要求双胞胎兜底", str(ids(A_DOC)))
        REAL = ("写实纪录风格，一位身着迷彩外套的老人坐在土墙前缓慢说话。固定中景稳定拍摄，"
                "高清，细节丰富，电影质感；人物面部稳定不变形、动作连贯自然，无穿模无卡顿；"
                "保持无字幕，避免生成任何文字，不要生成水印，不要生成Logo。")
        expect(not ids(REAL), "11i 真机已产出的合格稿加了 4 条仍零问题", str(ids(REAL)))
        expect(len(volc20_pe.RULES) > 0, "11j 尺子条数从规则表取，不写死",
               str(len(volc20_pe.RULES)))

    finally:
        restore()

    passed = sum(1 for r in RESULT if r[0])
    for good, name, detail in RESULT:
        print(("  ✅ " if good else "  ❌ ") + name + ("" if good else f"\n      {detail}"))
    print(f"\nSeedance 2.0 提示词接口：通过 {passed} / {len(RESULT)}，红 {len(RESULT) - passed}")
    return 0 if passed == len(RESULT) else 1


if __name__ == "__main__":
    sys.exit(main())
