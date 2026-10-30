# -*- coding: utf-8 -*-
"""「提示词优化」接口层验收（**零模型调用、零费用**）。

被测对象：`app/api/prompt.py`（四步链路的路由壳）。
大模型一律换成桩 —— 这里验的是**接线**：参数校验、判据重试、错误不吞。

🩸 2026-10-30 主人一句「删」：`h3_direct.chat_turn`（一次调用 + `<<<ASK>>>` 文本协议）
那条路没人调用了，192 行连它自己的 22 条断一起删掉，存档在
`docs/_archive/h3_direct_chat_turn.txt`。本文件现在只剩两块：

| 块 | 测什么 | 桩打在哪 |
|---|---|---|
| C / R 段 | 生成·转换·修订（**生产路径**，仍由 `h3_direct` 提供） | `h3_direct._chat` |
| A 段 | **生产路径** 接口 → `skill_agent`（p21 只测执行器，不经 HTTP） | `skill_agent._post` |

两条路径都要验：C/R 是「粘现成稿 / 改几处」，A 是「一句话聊出稿」。二者不互相覆盖。

真模型效果不在本文件里验（那要花钱，得主人点头）。

运行：python scripts/p18_check.py --model h3
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import logging  # noqa: E402

import _model_lock  # noqa: E402

# TestClient 会刷一屏 `HTTP Request: POST …`，把结论行埋掉（一键自检取末行做摘要）。
logging.disable(logging.INFO)

RESULT: list[tuple[bool, str, str]] = []

#: 正文写中文 → B3 必红（官方要求正文英文）。8a 拿它证明「判据不是空跑」。
BAD = {
    "style": "Live-action",
    "shots": [{"body": "一个女人站在地铁站台上。"}],
    "soundscape": "远处列车的声音。",
    "music": "",
}


def ok(name: str, detail: str = "") -> None:
    RESULT.append((True, name, detail))


def bad(name: str, detail: str) -> None:
    RESULT.append((False, name, detail))


def expect(cond: bool, name: str, detail: str = "") -> bool:
    (ok if cond else bad)(name, "" if cond else detail)
    return cond


def main() -> int:
    if "--model" not in sys.argv:
        print("⛔ 必须点名型号：--model h3")
        return 2
    i = sys.argv.index("--model")
    if (sys.argv[i + 1] if i + 1 < len(sys.argv) else "") != "h3":
        print("⛔ 本文件只装 H3 的断言：--model h3")
        return 2
    _model_lock.guard("h3")

    from fastapi.testclient import TestClient

    from app.core.config import settings
    from app.main import app
    from app.services.models import h3_base as rules

    client = TestClient(app)
    old_key = settings.ark_api_key

    def restore():
        object.__setattr__(settings, "ark_api_key", old_key)

    try:
        # 1 健康探针（不联网）
        r = client.get("/api/prompt/health").json()
        expect(r["code"] == 200 and r["data"]["rules"] == len(rules.RULES),
               "1a /prompt/health 返回规则条数", str(r)[:200])
        expect("ark_configured" in r["data"], "1b health 带 key 配置状态",
               str(r["data"])[:200])

        # 判模式、喂原文、尺子验收（判红回灌一次）。
        # 桩打在 `h3_direct._chat`（发请求那一层），`generate` 的判红回灌逻辑照跑。
        from app.services import h3_direct

        BASE_OUT = (
            "integrated_multimodal_description: [Shot 1] A woman stands alone on a "
            "subway platform. The camera holds a static shot.\n\n"
            "overall_soundscape: Distant train rumble.\n\n"
            "non_diegetic_music: N/A")
        REF_OUT = (
            "subject_definitions:\n<Picture 1> The woman's appearance reference.\n\n"
            "summary:\n[reference generation] A woman waits on a platform, "
            "using <Picture 1> for her appearance.\n\n"
            "retention_analysis:\n<Picture 1> ([Shot 1]): fully_preserved - "
            "her appearance is kept identical.\n\n"
            "detailed_description:\n[Shot 1] The woman stands on the platform. "
            "The camera holds a static shot.\n\n"
            "overall_soundscape:\nDistant train rumble.\n\n"
            "non_diegetic_music:\nN/A")
        # 六段正文写中文 → E12 必红（官方 ref-en:12 要求六段英文）
        REF_BAD = REF_OUT.replace(
            "[reference generation] A woman waits on a platform, using <Picture 1> "
            "for her appearance.", "[reference generation] 一个女人在站台等车。")

        seen: list[dict] = []
        real_chat = h3_direct._chat

        def fake_chat(sys_msg, user_msg, *, model="", key=""):
            seen.append({"sys": sys_msg, "user": user_msg})
            return REF_OUT if "<Picture 1>" in user_msg else BASE_OUT

        h3_direct._chat = fake_chat
        try:
            # C1 没素材 → 文生视频，走三字段
            r = client.post("/api/prompt/convert",
                            json={"text": "一份别家的稿"}).json()
            d = r.get("data") or {}
            expect(d.get("mode") == "t2va" and d.get("format", "").startswith("三字段"),
                   "C1 没素材 → t2va + 三字段", str(r)[:300])
            expect("integrated_multimodal_description" in (d.get("prompt") or ""),
                   "C1b 三字段齐全（文生视频格式）", (d.get("prompt") or "")[:160])

            # C2 带参考图 → 六段式，标签和用途必须真的传给模型
            r = client.post("/api/prompt/convert", json={
                "text": "一份别家的稿",
                "assets": [{"kind": "image", "role": "reference_image",
                            "label": "<Picture 1>", "note": "女主"}]}).json()
            d = r.get("data") or {}
            expect(r["biz_code"] == 0 and "subject_definitions" in (d.get("prompt") or ""),
                   "C2 带参考图 → 六段式", str(r)[:300])
            expect("<Picture 1>" in seen[-1]["user"] and "女主" in seen[-1]["user"],
                   "C2b 素材标签和用途真的传给了模型", seen[-1]["user"][-300:])

            r = client.post("/api/prompt/convert", json={
                "text": "一份别家的稿",
                "assets": [{"kind": "image"}]}).json()
            expect(r["biz_code"] != 0 and "问顾客" in r["msg"],
                   "C3 图没标用途 → 拒绝并说明要问顾客", str(r)[:300])

            # C4 帧和参考互斥（官方 api-create:212-214）
            r = client.post("/api/prompt/convert", json={
                "text": "一份别家的稿",
                "assets": [{"kind": "image", "role": "first_frame"},
                           {"kind": "image", "role": "reference_image"}]}).json()
            expect(r["biz_code"] != 0 and "不可混用" in r["msg"],
                   "C4 首帧+参考图互斥 → 拒绝", str(r)[:300])

            # C5 参考图超官方上限 9 张
            r = client.post("/api/prompt/convert", json={
                "text": "一份别家的稿",
                "assets": [{"kind": "image", "role": "reference_image",
                            "label": f"<Picture {i}>"} for i in range(1, 11)]}).json()
            expect(r["biz_code"] != 0 and "上限" in r["msg"],
                   "C5 参考图 10 张 → 拒绝", str(r)[:300])

            # C6 素材类型/角色闭集（前端不能传任意值）
            r = client.post("/api/prompt/convert", json={
                "text": "稿", "assets": [{"kind": "hologram"}]}).json()
            expect(r["biz_code"] != 0, "C6 未知素材类型 → 拒绝", str(r)[:200])
            r = client.post("/api/prompt/convert",
                            json={"text": "稿", "variant": "MiniMax-X9"}).json()
            expect(r["biz_code"] != 0, "C6b 未知 H3 型号 → 拒绝", str(r)[:200])

            # C7 片长按型号夹紧并说明（Max 是 5–15，普通是 4–15）
            r = client.post("/api/prompt/convert",
                            json={"text": "稿", "duration": 20}).json()
            d = r.get("data") or {}
            expect(d.get("duration") == 15, "C7a 超上限夹到 15", str(d.get("duration")))
            expect(any("超出" in w for w in (d.get("warnings") or [])),
                   "C7b 夹紧要如实说明", str(d.get("warnings"))[:200])
            r = client.post("/api/prompt/convert",
                            json={"text": "稿", "variant": "MiniMax-H3-Max",
                                  "duration": 4}).json()
            expect((r.get("data") or {}).get("duration") == 5,
                   "C7c Max 的下限是 5 秒（官方 api-create:294-312）",
                   str((r.get("data") or {}).get("duration")))

            # C8 判红 → 把「哪条没过 + 官方出处」喂回去重试一次
            _n0 = len(seen)

            def fake_bad_then_good(sys_msg, user_msg, *, model="", key=""):
                seen.append({"sys": sys_msg, "user": user_msg})
                return REF_BAD if len(seen) - 1 == _n0 else REF_OUT

            h3_direct._chat = fake_bad_then_good
            r = client.post("/api/prompt/convert", json={
                "text": "稿",
                "assets": [{"kind": "image", "role": "reference_image",
                            "label": "<Picture 1>", "note": "女主"}]}).json()
            d = r.get("data") or {}
            expect(len(seen) - _n0 == 2, "C8 判红后重试了一次",
                   f"实际调用 {len(seen) - _n0} 次")
            expect("E12" in seen[-1]["user"] and "官方出处" in seen[-1]["user"],
                   "C8b 回灌带上了判据编号和官方出处",
                   seen[-1]["user"][-260:])
            expect(not d.get("red") and r["biz_code"] == 0,
                   "C8c 重试成功后红清空、biz_code=0", str(d.get("red"))[:200])

            # C9 两轮都红 → 不吞：biz_code=2 + 点名哪条
            h3_direct._chat = lambda *a, **k: REF_BAD
            r = client.post("/api/prompt/convert", json={
                "text": "稿",
                "assets": [{"kind": "image", "role": "reference_image",
                            "label": "<Picture 1>", "note": "女主"}]}).json()
            expect(r["biz_code"] == 2, "C9 两轮都红 → biz_code=2", str(r)[:300])
            expect(bool((r.get("data") or {}).get("red")), "C9b 红条目如实返回",
                   str((r.get("data") or {}).get("red"))[:200])
            expect("判据没过" in r["msg"], "C9c msg 点名没过", r["msg"])


            r = client.post("/api/prompt/convert", json={
                "text": "一份别家的稿",
                "assets": [{"kind": "image"}]}).json()
            expect(r["biz_code"] != 0 and "问顾客" in r["msg"],
                   "C3 图没标用途 → 拒绝并说明要问顾客", str(r)[:300])

            # C4 帧和参考互斥（官方 api-create:212-214）
            r = client.post("/api/prompt/convert", json={
                "text": "一份别家的稿",
                "assets": [{"kind": "image", "role": "first_frame"},
                           {"kind": "image", "role": "reference_image"}]}).json()
            expect(r["biz_code"] != 0 and "不可混用" in r["msg"],
                   "C4 首帧+参考图互斥 → 拒绝", str(r)[:300])

            # C5 参考图超官方上限 9 张
            r = client.post("/api/prompt/convert", json={
                "text": "一份别家的稿",
                "assets": [{"kind": "image", "role": "reference_image",
                            "label": f"<Picture {i}>"} for i in range(1, 11)]}).json()
            expect(r["biz_code"] != 0 and "上限" in r["msg"],
                   "C5 参考图 10 张 → 拒绝", str(r)[:300])

            # C6 素材类型/角色闭集（前端不能传任意值）
            r = client.post("/api/prompt/convert", json={
                "text": "稿", "assets": [{"kind": "hologram"}]}).json()
            expect(r["biz_code"] != 0, "C6 未知素材类型 → 拒绝", str(r)[:200])
            r = client.post("/api/prompt/convert",
                            json={"text": "稿", "variant": "MiniMax-X9"}).json()
            expect(r["biz_code"] != 0, "C6b 未知 H3 型号 → 拒绝", str(r)[:200])

            # C7 片长按型号夹紧并说明（Max 是 5–15，普通是 4–15）
            r = client.post("/api/prompt/convert",
                            json={"text": "稿", "duration": 20}).json()
            d = r.get("data") or {}
            expect(d.get("duration") == 15, "C7a 超上限夹到 15", str(d.get("duration")))
            expect(any("超出" in w for w in (d.get("warnings") or [])),
                   "C7b 夹紧要如实说明", str(d.get("warnings"))[:200])
            r = client.post("/api/prompt/convert",
                            json={"text": "稿", "variant": "MiniMax-H3-Max",
                                  "duration": 4}).json()
            expect((r.get("data") or {}).get("duration") == 5,
                   "C7c Max 的下限是 5 秒（官方 api-create:294-312）",
                   str((r.get("data") or {}).get("duration")))

            # C8 判红 → 把「哪条没过 + 官方出处」喂回去重试一次
            _n0 = len(seen)

            def fake_bad_then_good(sys_msg, user_msg, *, model="", key=""):
                seen.append({"sys": sys_msg, "user": user_msg})
                return REF_BAD if len(seen) - 1 == _n0 else REF_OUT

            h3_direct._chat = fake_bad_then_good
            r = client.post("/api/prompt/convert", json={
                "text": "稿",
                "assets": [{"kind": "image", "role": "reference_image",
                            "label": "<Picture 1>", "note": "女主"}]}).json()
            d = r.get("data") or {}
            expect(len(seen) - _n0 == 2, "C8 判红后重试了一次",
                   f"实际调用 {len(seen) - _n0} 次")
            expect("E12" in seen[-1]["user"] and "官方出处" in seen[-1]["user"],
                   "C8b 回灌带上了判据编号和官方出处",
                   seen[-1]["user"][-260:])
            expect(not d.get("red") and r["biz_code"] == 0,
                   "C8c 重试成功后红清空、biz_code=0", str(d.get("red"))[:200])

            # C9 两轮都红 → 不吞：biz_code=2 + 点名哪条
            h3_direct._chat = lambda *a, **k: REF_BAD
            r = client.post("/api/prompt/convert", json={
                "text": "稿",
                "assets": [{"kind": "image", "role": "reference_image",
                            "label": "<Picture 1>", "note": "女主"}]}).json()
            expect(r["biz_code"] == 2, "C9 两轮都红 → biz_code=2", str(r)[:300])
            expect(bool((r.get("data") or {}).get("red")), "C9b 红条目如实返回",
                   str((r.get("data") or {}).get("red"))[:200])
            expect("判据没过" in r["msg"], "C9c msg 点名没过", r["msg"])


        # ------------------------------------------------ 修订（出了片，改几处）
            # 🩸 2026-10-30 主人：「产出的视频效果不理想，切图回来反馈让他修改部分提示词。
            # 你现在这样的输入和操作方式我感觉很落后」。
            # 闭环：现有提示词 + 截图 + 一句话 → 只改那几处。图必须真的进模型。
            rseen: list[dict] = []

            def fake_revise(sys_msg, user_msg, *, model="", key="", images=None):
                rseen.append({"sys": sys_msg, "user": user_msg,
                              "images": list(images or [])})
                return REF_OUT

            h3_direct._chat = fake_revise
            IMG = "data:image/jpeg;base64,/9j/AAAA"

            # R1 有提示词 + 有反馈 → 出新版，且 system 里带修订规则 + 官方原文
            r = client.post("/api/prompt/revise", json={
                "prompt": REF_OUT, "feedback": "第 1 镜她的手多了一只"}).json()
            d = r.get("data") or {}
            expect(r["biz_code"] == 0 and d.get("kind") == "ref",
                   "R1 六段式提示词 → 认出是 ref 格式", str(r)[:300])
            expect("只改反馈指出的地方" in rseen[-1]["sys"]
                   and "Identify the input mode" in rseen[-1]["sys"],
                   "R1b system = 官方原文 + 修订规则（只改那几处）",
                   rseen[-1]["sys"][:200])
            expect("她的手多了一只" in rseen[-1]["user"]
                   and REF_OUT[:40] in rseen[-1]["user"],
                   "R1c 现有提示词和反馈都传给了模型",
                   rseen[-1]["user"][:260])
            # 🩸 2026-10-30 修订**不另定片长**：那份稿自己有「00:xx」时间码。
            # 成对验：默认（不传）不带片长；老调用方显式传了才带。
            expect("目标片长" not in rseen[-1]["user"],
                   "R1d 不传片长 → 指令里没有「目标片长」（不替顾客定）",
                   rseen[-1]["user"][:120])
            client.post("/api/prompt/revise", json={
                "prompt": REF_OUT, "feedback": "x", "duration": 8}).json()
            expect("目标片长】8 秒" in rseen[-1]["user"],
                   "R1e 显式传 8 → 仍然带上（老调用方不断）",
                   rseen[-1]["user"][:120])

            # R2 截图真的进了多模态 content
            r = client.post("/api/prompt/revise", json={
                "prompt": REF_OUT, "feedback": "手不对", "images": [IMG]}).json()
            expect(r["biz_code"] == 0, "R2 带截图能修订", str(r)[:200])
            expect(rseen[-1]["images"] == [IMG],
                   "R2b 截图传到了发请求那一层（不是只写进文字）",
                   str(rseen[-1]["images"])[:120])

            # R3 三字段提示词 → 认出 base
            r = client.post("/api/prompt/revise", json={
                "prompt": BASE_OUT, "feedback": "运镜太快"}).json()
            expect((r.get("data") or {}).get("kind") == "base",
                   "R3 三字段提示词 → 认出是 base 格式",
                   str((r.get("data") or {}).get("kind")))

            # R4 入参校验
            for body, name in (
                ({"prompt": "  ", "feedback": "x"}, "R4a 空提示词"),
                ({"prompt": REF_OUT}, "R4b 没反馈也没截图"),
                ({"prompt": REF_OUT, "feedback": "x",
                  "images": ["https://evil.example.com/a.jpg"]}, "R4c 外链截图（防 SSRF）"),
                ({"prompt": REF_OUT, "feedback": "x", "images": [IMG] * 5}, "R4d 截图超过 4 张"),
            ):
                r = client.post("/api/prompt/revise", json=body).json()
                expect(r["biz_code"] != 0, name + " → 拒绝", str(r)[:200])

            # R5 判红 → 不吞
            h3_direct._chat = lambda *a, **k: REF_BAD
            r = client.post("/api/prompt/revise", json={
                "prompt": REF_OUT, "feedback": "x"}).json()
            expect(r["biz_code"] == 2 and bool((r.get("data") or {}).get("red")),
                   "R5 修订产出判红 → biz_code=2 并点名",
                   str((r.get("data") or {}).get("red"))[:200])
            h3_direct._chat = fake_chat

            # ------------------------------------------------ 生产路径：接口 → agent
            # 🩸 上面那节验的是回滚路。**这一节验接口真的走到 agent** —— p21 直接测
            # 执行器、不经过 HTTP，所以「接口接没接上」只有这里覆盖。
            from app.services import skill_agent as _sa

            real_post = _sa._post
            seen_sys: list[str] = []

            def _fake_post(msgs, **k):
                if not seen_sys:
                    seen_sys.append(msgs[0]["content"])
                return {"choices": [{"message": {
                    "role": "assistant", "content": "",
                    "tool_calls": [{"id": "t1", "type": "function", "function": {
                        "name": "ask_user",
                        "arguments": '{"question": "这段要几秒？\\n- 4 秒\\n- 8 秒"}'}}]}}],
                    "usage": {"total_tokens": 10}}

            _sa._post = _fake_post
            try:
                r = client.post("/api/prompt/chat", json={
                    "target": "h3",
                    "messages": [{"role": "user", "content": "我想拍个短片"}]}).json()
                d = r.get("data") or {}
                expect(r["biz_code"] == 0 and d.get("action") == "ask"
                       and "几秒" in (d.get("question") or ""),
                       "A1 接口 h3 分支真的走 agent（ask_user → action=ask）",
                       str(r)[:300])
                expect(bool(d.get("trace")) and (d.get("calls") or 0) >= 1,
                       "A2 每步进度带到接口（前端 100 秒没反馈=以为卡死）",
                       str(d.get("trace"))[:200])
                expect("片长还没定" in (seen_sys[0] if seen_sys else ""),
                       "A3 固定条件（片长未定）进了 agent 的 system",
                       (seen_sys[0] if seen_sys else "")[-300:])
                expect("Identify the input mode" not in (seen_sys[0] if seen_sys else ""),
                       "A4 官方原文不再拼进 system（模型自己去读）",
                       (seen_sys[0] if seen_sys else "")[:200])

                seen_sys.clear()
                r = client.post("/api/prompt/chat", json={
                    "target": "h3", "duration": 5,
                    "messages": [{"role": "user", "content": "我想拍个短片"}]}).json()
                expect(r["biz_code"] == 0 and "目标片长：5 秒" in (
                    seen_sys[0] if seen_sys else ""),
                       "A5 定了片长 → 固定条件写进 system",
                       (seen_sys[0] if seen_sys else "")[-300:])
            finally:
                _sa._post = real_post

            # Q9 入参校验（桩不用打，走不到模型）
            for body, name in (
                ({"messages": [], "target": "h3"}, "Q9a 空对话"),
                ({"messages": [{"role": "assistant", "content": "我在自言自语"}],
                  "target": "h3"}, "Q9b 最后一条是 assistant"),
                ({"messages": [{"role": "user", "content": "x"}], "model": "gpt-4",
                  "target": "h3"}, "Q9c 模型名不在白名单"),
            ):
                r = client.post("/api/prompt/chat", json=body).json()
                expect(r["biz_code"] != 0, name + " → 拒绝", str(r)[:200])

            # Q10 未配 key → 拒绝，不发请求
            object.__setattr__(settings, "ark_api_key", "")
            r = client.post("/api/prompt/chat", json={
                "target": "h3",
                "messages": [{"role": "user", "content": "x"}]}).json()
            expect(r["biz_code"] != 0 and "方舟未配置" in r["msg"],
                   "Q10 未配 key → 拒绝并说清原因", str(r)[:200])
            object.__setattr__(settings, "ark_api_key", "stub")

            # C10 未配 key → 拒绝，不发请求
            h3_direct._chat = fake_chat
            object.__setattr__(settings, "ark_api_key", "")
            r = client.post("/api/prompt/convert", json={"text": "稿"}).json()
            expect(r["biz_code"] != 0 and "方舟未配置" in r["msg"],
                   "C10 未配 key → 拒绝并说清原因", str(r)[:200])
        finally:
            h3_direct._chat = real_chat
        object.__setattr__(settings, "ark_api_key", "stub")
        # 8 判据自证用的坏样本确实会红（否则第 3 条测的是空气）
        from app.services.models import h3_base_compile as hbc
        p_bad = hbc.compile({**{"mode": "t2va", "duration": 5, "ratio": "16:9"},
                             **BAD})["text"]
        reds = [x for x in rules.check(p_bad, {"mode": "t2va"}) if x[1] == "红"]
        expect(bool(reds), "8a 桩坏样本确实被判红（第 3 条不是空跑）",
               str(reds)[:200])

        # ------------------------------------------------------ S 对话历史（存后端）
        # 🩸 2026-10-30「点了新对话，旧对话回不去了」→ 历史搬后端。
        import shutil as _sh
        import tempfile
        from app.services import prompt_sessions as _ps
        _tmp = Path(tempfile.mkdtemp(prefix="p18sess_"))
        _real_root = _ps.ROOT
        _ps.ROOT = _tmp
        try:
            r = client.put("/api/prompt/sessions/sabc123", json={
                "title": "做个 3D 动画", "target": "h3", "turns": 2,
                "last_prompt": "integrated…",
                "msgs": [{"role": "user", "text": "做个3D动画"}]}).json()
            expect(r["biz_code"] == 0 and r["data"]["title"] == "做个 3D 动画",
                   "S1 存一份对话", str(r)[:200])
            r = client.get("/api/prompt/sessions").json()
            expect([x["id"] for x in r["data"]] == ["sabc123"],
                   "S2 列表能看到（摘要）", str(r["data"])[:200])
            r = client.get("/api/prompt/sessions/sabc123").json()
            expect(r["data"]["msgs"][0]["text"] == "做个3D动画",
                   "S3 点开能拿回原话", str(r["data"])[:200])
            r = client.delete("/api/prompt/sessions/sabc123").json()
            expect(r["data"]["deleted"] is True and not _ps.index(),
                   "S4 删掉之后列表就空", str(r)[:200])
            # 成对：非法编号必须拒（否则等于把服务器目录开给浏览器）
            r = client.get("/api/prompt/sessions/a.b").json()
            expect(r.get("biz_code", -1) != 0,
                   "S5 会话编号带 . 被拒（先过白名单再拼路径）", str(r)[:200])
            r = client.get("/api/prompt/sessions/..%2F..%2Fetc")
            expect(r.status_code != 200 or r.json().get("biz_code", -1) != 0,
                   "S5b 路径穿越拿不到数据（路由层或校验层拦住）",
                   f"{r.status_code} {r.text[:120]}")

            # ------------------------------------------------ S6+ 离开页面也跑完、也留得下
            # 🩸 2026-10-30 主人：「我不在那个页面也会把之前的提问输出完整」。
            # 这条不是在验模型，是在验**活和请求解耦**：没人收结果，它也得自己落盘。
            import asyncio
            import time
            from app.api import prompt as _api

            def _slow(b):
                time.sleep(0.15)
                return {"action": "write", "prompt": "A woman walks in. " * 4,
                        "red": [], "yellow": [], "chars": 76, "rules": 20,
                        "format": "官方 skill 直出", "note": ""}

            body = _api.ChatIn(messages=[{"role": "user", "content": "做个3D动画，四镜"}],
                               target="h3", sid="sdet1")

            async def _leave():
                """顾客刚发就关页面：等待者被取消，活照跑完。"""
                fut = _api._detach(
                    lambda b: _api._run(_slow, b, user_text="做个3D动画，四镜",
                                        target="h3"), body)
                try:
                    await asyncio.wait_for(_api._wait(fut), timeout=0.02)
                    return "没取消掉（桩太快？）"
                except asyncio.TimeoutError:
                    pass
                await asyncio.wait_for(asyncio.wrap_future(fut), timeout=5)
                return ""

            why = asyncio.run(_leave())
            row = _ps.load("sdet1") or {}
            msgs = row.get("msgs") or []
            expect(not why and [m["role"] for m in msgs] == ["user", "ai"],
                   "S6 顾客中途离开，这一轮仍然落盘（问 + 答都在）",
                   f"{why} {msgs}"[:300])
            expect(bool(msgs) and msgs[-1]["data"].get("prompt", "").startswith("A woman walks"),
                   "S6b 落盘的是**完整成品**，不是半截", str(msgs[-1:])[:300])
            expect(row.get("title") == "做个3D动画，四镜" and row.get("turns") == 1,
                   "S6c 标题/轮数由后端自己记（前端不在也能起名）", str(row)[:300])

            # 成对：前端那一份**先落地过**（尾条已经是这一问）→ 不许再记一遍。
            # 这是真会发生的顺序：顾客点「新对话」时前端 stash 会整份推上去，
            # 而后端那条请求还在跑，回来再把同一问写一次就成了问两遍。
            _ps.save("srace", title="", target="h3", turns=1,
                     msgs=[{"role": "user", "text": "第二问", "shots": 0,
                            "data": None, "error": ""}])
            _ps.append_turn("srace", user_text="第二问",
                            ai={"action": "write", "prompt": "p2"}, target="h3")
            again = (_ps.load("srace") or {}).get("msgs") or []
            expect([m["role"] for m in again] == ["user", "ai"],
                   "S6d 前端推过的那一问不重复记（否则回来看到问两遍）",
                   str([m["role"] for m in again]))

            # 成对：失败也要留痕 —— 不然顾客回来只看到自己那句话，以为没发出去
            def _boom(b):
                raise RuntimeError("方舟 500")

            async def _fail():
                fut = _api._detach(
                    lambda b: _api._run(_boom, b, user_text="再写一个", target="h3"), body)
                try:
                    await asyncio.wrap_future(fut)
                except RuntimeError:
                    return True
                return False

            raised = asyncio.run(_fail())
            tail = (_ps.load("sdet1") or {}).get("msgs") or []
            expect(raised and tail[-1]["role"] == "ai" and "方舟 500" in (tail[-1].get("error") or ""),
                   "S7 跑失败也写一条 error（顾客回来知道是失败了，不是没发）",
                   str(tail[-1:])[:300])

            # 成对：不带 sid 的老请求照常工作，不许因为记不下来就报错
            fut = _api._detach(lambda b: _api._run(_slow, b, user_text="", target="h3"),
                               _api.ChatIn(messages=[], target="h3"))
            got = fut.result(timeout=5)
            expect(got.get("chars") == 76 and (_ps.load("sdet1") or {}).get("turns") == 2,
                   "S8 不带 sid 不写历史、也不报错（老调用方不受影响）",
                   f"{got} {(_ps.load('sdet1') or {}).get('turns')}")
        finally:
            _ps.ROOT = _real_root
            _sh.rmtree(_tmp, ignore_errors=True)
    finally:
        restore()

    passed = sum(1 for r in RESULT if r[0])
    for good, name, detail in RESULT:
        print(("  ✅ " if good else "  ❌ ") + name)
        if not good and detail:
            print("       " + detail)
    print(f"\n接口层验收：通过 {passed} / {len(RESULT)}，红 {len(RESULT) - passed}")
    return 0 if passed == len(RESULT) else 1


if __name__ == "__main__":
    sys.exit(main())
