# -*- coding: utf-8 -*-
"""Seedance 2.0 提示词对话接口验收（**零模型调用、零费用**）。

被测对象：`app/api/prompt.py` 的 `target=sd20` 分支 + `sd20_direct` + `volc20_pe`。
大模型一律换成桩 —— 这里验的是**接线**：官方原文有没有真喂进去、两家有没有串、
判红会不会吞、素材标签按 2.0 语法还是照抄了 H3。

真模型效果不在本文件里验（那要花钱，得主人点头）。

运行：python scripts/p20_check.py --model volc20
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


def ok(name: str, detail: str = "") -> None:
    RESULT.append((True, name, detail))


def bad(name: str, detail: str) -> None:
    RESULT.append((False, name, detail))


def expect(cond: bool, name: str, detail: str = "") -> bool:
    (ok if cond else bad)(name, "" if cond else detail)
    return cond


#: 官方 skill 路径 A 示例（`skill-sd2-pe.md:123`），一字未改 —— 拿它当「合格稿」。
GOOD = ("参考 @图片1 中的<主体1>（短发女孩），生成她在 @图片2 的咖啡店里吃蛋糕的画面。"
        "暖色调电影质感，画面稳定无变形，保持无字幕，不要生成水印，不要生成 Logo。")

#: 同一句只加一个绝对秒数 → V1 必红
BAD = GOOD.replace("生成她在", "0-3s 生成她在")

ASK = "<<<ASK>>>\n这段想要几秒？\n- 4 秒\n- 6 秒\n- 8 秒"


def stub(seq):
    """按调用顺序返回 seq；同时记下每次收到的 system prompt。"""
    state = {"i": 0, "sys": [], "hist": [], "images": []}

    def _chat(sys_msg, history, *, model="", key="", images=None):
        i = min(state["i"], len(seq) - 1)
        state["i"] += 1
        state["sys"].append(sys_msg)
        state["hist"].append(history)
        state["images"].append(images)
        return seq[i]

    _chat.state = state
    return _chat


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
    from app.services import sd20_direct, sd20_official
    from app.services.models import volc20_pe

    client = TestClient(app)
    real_chat = sd20_direct._chat_multi
    old_key = settings.ark_api_key

    def restore() -> None:
        sd20_direct._chat_multi = real_chat
        object.__setattr__(settings, "ark_api_key", old_key)

    def post(seq, body):
        ch = stub(seq)
        sd20_direct._chat_multi = ch
        return client.post("/api/prompt/chat", json=body).json(), ch

    try:
        object.__setattr__(settings, "ark_api_key", "stub")

        # ---------------------------------------------------------- 1 入口
        r, _ch = post([ASK], {"messages": [{"role": "user", "content": "我想拍个短片"}]})
        expect(r.get("code") == 200 and "还没选" in (r.get("msg") or ""),
               "1a 不传 target → 明确要求先选，不替顾客默认",
               str(r)[:200])
        r, _ch = post([ASK], {"messages": [{"role": "user", "content": "x"}],
                              "target": "h3"})
        expect(r.get("code") == 200, "1b target=h3 仍走 H3 那条路不报错", str(r)[:200])

        # ---------------------------------------------------------- 2 官方原文真喂进去
        r, ch = post([ASK], {"messages": [{"role": "user", "content": "我想拍个短片"}],
                             "target": "sd20"})
        sys_msg = ch.state["sys"][0]
        expect(r.get("code") == 200 and (r.get("data") or {}).get("action") == "ask",
               "2a 一句话 → 先问，不硬写", str(r)[:300])
        expect("路径 A" in sys_msg and "路径 B" in sys_msg,
               "2b skill 全文在（输出路径 A/B 判断）", f"system {len(sys_msg)} 字符")
        expect("八大要素" in sys_msg or "进阶公式" in sys_msg,
               "2c guide 的进阶公式在", "")
        expect("推、拉、摇、移、环绕、跟随、升、降、变焦" in sys_msg,
               "2d 运镜词表（1.0 pro 官方章）在", "")
        expect("镜头1" in sys_msg and "0–3s" in sys_msg,
               "2e 2.0 的时间写法口径在（禁绝对秒数）", "")
        expect("<d>" not in sys_msg and "base-en" not in sys_msg,
               "2f 没有把 H3 的规则串进来", "")

        # ---------------------------------------------------------- 3 片长口径
        expect("4 / 5 / 6 / 8 / 10 / 15 秒" in sys_msg,
               "3a 片长未定 → 让模型按 4 秒起问", "")
        expect("延长" in sys_msg, "3b 2.0 官方有延长视频，允许讲", "")

        # ---------------------------------------------------------- 4 素材标签按 2.0 语法
        r, ch = post([GOOD], {
            "messages": [{"role": "user", "content": "写一个女孩吃蛋糕"}],
            "target": "sd20", "duration": 6,
            "assets": [{"kind": "image", "role": "reference_image",
                        "label": "<Picture 1>", "note": "女主"},
                       {"kind": "video", "role": "reference_video",
                        "label": "<Video 1>", "note": "运镜参考"}],
        })
        sys4 = ch.state["sys"][0]
        expect("@图片1" in sys4 and "@视频1" in sys4,
               "4a 素材标号用 2.0 的 @图片N / @视频N", sys4[-600:])
        expect("<Picture 1>" not in sys4,
               "4b 没有照抄 H3 的 <Picture N>", sys4[-600:])
        expect("目标片长：6 秒" in sys4, "4c 片长写进固定条件", "")

        r, _ch = post([GOOD], {
            "messages": [{"role": "user", "content": "x"}], "target": "sd20",
            "assets": [{"kind": "image", "role": "reference_image"}] * 10})
        expect(r.get("biz_code") != 0 and "上限" in (r.get("msg") or ""),
               "4d 图超过 9 张 → 拒绝（不写出 @图片12 这种收不到的编号）",
               str(r)[:200])

        # 附件图先占号、面板素材接着编（2026-10-30 主人：按上传顺序）
        r, ch = post([GOOD], {
            "messages": [{"role": "user", "content": "这是我的主角"}], "target": "sd20",
            "images": ["data:image/jpeg;base64,AAAA"], "duration": 6,
            "assets": [{"kind": "image", "role": "reference_image", "note": "服装"},
                       {"kind": "image", "role": "reference_image", "note": "场景"}]})
        sys4b = ch.state["sys"][0]
        expect("@图片1 … @图片1" in sys4b,
               "4e 附件图按上传顺序编成 @图片1…@图片N", sys4b[-500:])
        expect("@图片2 —— " in sys4b and "@图片3 —— " in sys4b,
               "4f 面板里的两张图接着编成 @图片2/@图片3（不跟附件撞号）", sys4b[-500:])

        r, _ch = post([GOOD], {
            "messages": [{"role": "user", "content": "x"}], "target": "sd20",
            "images": ["data:image/jpeg;base64,AAAA"] * 3,
            "assets": [{"kind": "image", "role": "reference_image"}] * 7})
        expect(r.get("biz_code") != 0 and "上限" in (r.get("msg") or ""),
               "4g 附件 3 张 + 面板 7 张 = 超 9 → 拒绝（合计算上限，不是各算各的）",
               str(r)[:200])

        # ---------------------------------------------------------- 5 判红→重试→透传
        r, ch = post([BAD, GOOD], {
            "messages": [{"role": "user", "content": "写一个女孩吃蛋糕"}],
            "target": "sd20", "duration": 6})
        d = r.get("data") or {}
        expect(ch.state["i"] == 2, "5a 首轮判红后重试一次", f"实际调用 {ch.state['i']} 次")
        expect(r.get("biz_code") == 0 and not d.get("red"),
               "5b 重试成功后红清空", str(d.get("red"))[:200])
        expect(any("V1" in (t.get("red") or [""])[0] for t in (d.get("tries") or [])
                   if t.get("red")),
               "5c 首轮红的是 V1（绝对秒数）", str(d.get("tries"))[:300])

        r, ch = post([BAD], {
            "messages": [{"role": "user", "content": "写一个女孩吃蛋糕"}],
            "target": "sd20", "duration": 6})
        d = r.get("data") or {}
        expect(r.get("biz_code") == 2 and d.get("red"),
               "5d 两轮都红 → biz_code=2，不吞", str(r)[:300])

        # ---------------------------------------------------------- 6 判据条数不硬编码
        expect(d.get("rules") == len(volc20_pe.RULES),
               "6a 返回的判据条数 = 尺子实际条数",
               f"返回 {d.get('rules')!r} / 实际 {len(volc20_pe.RULES)}")

        # ---------------------------------------------------------- 7 截图挂在最后一轮
        r, ch = post([GOOD], {
            "messages": [{"role": "user", "content": "这里不对"}],
            "target": "sd20",
            "images": ["data:image/jpeg;base64,AAAA"]})
        # 桩替换的是 `_chat_multi` 本身，所以这里分两段验：
        # ① 图片确实传到了 HTTP 层；② 挂载函数把图放对了位置。
        expect(ch.state["images"][0] == ["data:image/jpeg;base64,AAAA"],
               "7a 截图传到了请求层", str(ch.state["images"][0])[:200])
        deep = [{"role": "user", "content": "写个女孩吃蛋糕"},
                {"role": "assistant", "content": "这段要几秒？"},
                {"role": "user", "content": "这里不对"}]
        packed = sd20_direct._with_images(deep, ["data:image/jpeg;base64,AAAA"])
        last = packed[-1]
        expect(isinstance(last.get("content"), list) and
               any(p.get("type") == "image_url" for p in last["content"]),
               "7b 截图挂在本轮 user 消息上（不另起一条）", str(last)[:200])
        expect(isinstance(packed[0].get("content"), str)
               and isinstance(packed[1].get("content"), str),
               "7c 历史里更早的消息不被改成数组", str(packed[:2])[:200])
        expect(deep[-1]["content"] == "这里不对",
               "7d 不改调用方传进来的原列表（避免污染历史）", str(deep[-1])[:120])
        # 🩸 传图 = 一律当成"成片截图"是错的：顾客第一次传人物照是**素材**。
        # 之前护栏只写了「顾客传截图 = 片子已经出来了」，模型会把主角照当成废片。
        sys7 = ch.state["sys"][0]
        expect("传了 1 张图" in sys7,
               "7e 告诉模型这一轮有几张图（不让它瞎猜）", sys7[-500:])
        expect("不要一律当成截图" in sys7 and "历史里**还没有**你写出的提示词" in sys7,
               "7f 传图先问「是素材还是截图」，不一律当废片", sys7[-700:])

        # ---------------------------------------------------------- 8 两家不串
        expect(len({*sd20_official.digest().values()}) == 5,
               "8a skill / guide / trouble / tips / 运镜词表 五份各自不同",
               str(list(sd20_official.digest())))

        # 🩸 2026-10-30 主人：「你只喂了半个 skill」。8 份官方材料第一版只喂了 2 份，
        # 漏掉的 `trouble.md` 里有 guide/skill 里**一个字都没有**的写法规则。
        # 这两条就是「喂全了」的证据 —— 不是看代码里有没有这行，是看 system 里有没有这段话。
        sys_all = sd20_official.system_prompt()
        for kw, name in (("重要内容前置", "重要内容前置原则"),
                         ("时长：4秒", "参数规范（时长/比例写进提示词）"),
                         ("Asset ID来替代", "Asset 不能替代图1/视频1"),
                         ("杜绝双胞胎同款人物", "双胞胎的官方原句")):
            expect(kw in sys_all, f"8d trouble.md 的独有内容进 system：{name}", kw)
        expect("提示词 = 主体 + 运动" in sys_all,
               "8e 教程「提示词建议」章节进 system", "")
        dg = sd20_official.digest()
        # 本机资料目录在的话，**按 MANIFEST 逐条比**（不把 sha 写死第二遍）；
        # 服务器上没有那个目录，就退回登记值的指纹前缀 —— 写明降级，不装成全验过。
        man_p = Path(r"D:/tmp/official/sd20/MANIFEST.json")
        if man_p.exists():
            import json as _json
            man = {f["path"]: f["sha256"]
                   for f in _json.loads(man_p.read_text(encoding="utf-8"))["files"]}
            expect(dg["skill"] == man.get("skill-sd2-pe.md"),
                   "8b skill 的 sha256 与官方 MANIFEST 逐字一致", dg["skill"])
            expect(dg["guide"] == man.get("guide.md"),
                   "8c guide 的 sha256 与官方 MANIFEST 逐字一致", dg["guide"])
        else:
            expect(dg["skill"].startswith("8836cdb2"),
                   "8b skill 的 sha256 与登记值一致（无本机资料目录，按指纹比）",
                   dg["skill"])
            expect(dg["guide"].startswith("dd7fe63c"),
                   "8c guide 的 sha256 与登记值一致（无本机资料目录，按指纹比）",
                   dg["guide"])

        # ---------------------------------------------------------- 9 「优化问题」拆得干净
        # 官方 Step 4（`sd2-pe:186-190`）要求披露补全/改动，但它**不是提示词的一部分**。
        # 拆不出去 → 顾客一复制就把「我替你定了暖色调」粘进 2.0 的输入框。
        W_NOTE = GOOD + "\n<<<NOTE>>>\n补全：暖色调、画质包\n改动：把\"参考\"改成\"严格编辑\""
        r, _ch = post([W_NOTE], {
            "messages": [{"role": "user", "content": "写一个女孩吃蛋糕"}],
            "target": "sd20", "duration": 6})
        d = r.get("data") or {}
        pr = d.get("prompt") or ""
        expect(d.get("action") == "write" and "补全：" not in pr and "<<<NOTE>>>" not in pr,
               "9a 披露段落没混进提示词（顾客复制带不走）", pr[:300])
        expect("补全：" in (d.get("note") or "") and "严格编辑" in (d.get("note") or ""),
               "9b 披露原样透传给前端", repr(d.get("note"))[:300])
        r, _ch = post([GOOD], {
            "messages": [{"role": "user", "content": "写一个女孩吃蛋糕"}],
            "target": "sd20", "duration": 6})
        expect((r.get("data") or {}).get("note") == "",
               "9c 没有披露段时 note 是空串不是 None（前端 v-if 才稳）",
               repr((r.get("data") or {}).get("note")))

        # ---------------------------------------------------------- 10 特殊字符 / 场景兜底
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
                   f"10a {tag} 官方原文不触发 V8–V11（正样本试尺子）", str(ids(doc)))
        expect("V8" in ids(A_DOC + "背景音乐用轻快的钢琴曲。")
               and "V8" not in ids(A_DOC + "（背景中播放着轻快的钢琴曲）。"),
               "10b 背景音乐：没（）判、有（）不判", str(ids(A_DOC + "背景音乐用轻快的钢琴曲。")))
        expect("V8" not in ids(A_DOC),
               "10c 不误伤主体注解 <主体1>（短发女孩）", str(ids(A_DOC)))
        expect("V9" in ids(A_DOC + "加入音效。")
               and "V9" not in ids(A_DOC + "加入音效<远处传来狗叫声>。"),
               "10d 音效：没<>判、有<>不判", str(ids(A_DOC + "加入音效。")))
        no_sub = A_DOC.replace("保持无字幕，", "")
        expect("V10" in ids(no_sub) and "V10" not in ids(A_DOC),
               "10e 字幕兜底：删掉判、有则不判", str(ids(no_sub)))
        expect("V10" not in ids(no_sub + "画面底部出现字幕，字幕内容为“欢迎光临”"),
               "10f 文字生成任务不要求挂无字幕兜底", str(ids(no_sub)))
        no_twin = B_DOC.replace(
            "视频全程禁止出现外形、着装、配饰完全一致的人物，禁止生成同款分身、双胞胎效果。", "")
        expect("V11" in ids(no_twin) and "V11" not in ids(B_DOC),
               "10g 双胞胎兜底：多人场景删掉判、有则不判", str(ids(no_twin)))
        expect("V11" not in ids(A_DOC), "10h 单人场景不要求双胞胎兜底", str(ids(A_DOC)))
        REAL = ("写实纪录风格，一位身着迷彩外套的老人坐在土墙前缓慢说话。固定中景稳定拍摄，"
                "高清，细节丰富，电影质感；人物面部稳定不变形、动作连贯自然，无穿模无卡顿；"
                "保持无字幕，避免生成任何文字，不要生成水印，不要生成Logo。")
        expect(not ids(REAL), "10i 真机已产出的合格稿加了 4 条仍零问题", str(ids(REAL)))

    finally:
        restore()

    passed = sum(1 for r in RESULT if r[0])
    for good, name, detail in RESULT:
        print(("  ✅ " if good else "  ❌ ") + name + ("" if good else f"\n      {detail}"))
    print(f"\nSeedance 2.0 提示词接口：通过 {passed} / {len(RESULT)}，红 {len(RESULT) - passed}")
    return 0 if passed == len(RESULT) else 1


if __name__ == "__main__":
    sys.exit(main())
