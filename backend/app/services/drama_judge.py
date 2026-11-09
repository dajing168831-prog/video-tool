"""商品短剧 · 判官层。

一次 LLM 调用跑五个判官（节奏 / 口语 / 创意 / 结构 / 画面），逐镜给意见。

核心洞察：**模型会把坏脚本渲染得和好脚本一样漂亮**。钱花在出片之前，
先让判官把脚本撕一遍——这是整条链路里最便宜的止损点。

三档采纳
    invariant  违反硬约束或合规红线，必须改
    default    明显扣分，默认改
    taste      口味偏好，只展示给人看
输出不合法 / 镜头不存在 / 数字丢失 ⇒ 一律降级或丢弃，绝不硬塞进分镜。
"""
from __future__ import annotations

import re

JUDGES = ("pace", "voice", "idea", "structure", "visual")
TIERS = ("invariant", "default", "taste")
TIER_RANK = {"invariant": 0, "default": 1, "taste": 2}

JUDGE_BRIEF = """| 判官 | 只审这一件事 | 典型问题 |
|---|---|---|
| pace 节奏 | 时长分配与注意力曲线 | 前 3 秒没钩子；中段连续两镜没有新信息；高潮来得太早或太晚 |
| voice 口语 | 台词像不像真人说的 | 书面腔、旁白腔、口号腔；一句话里塞两个意思；念产品参数 |
| idea 创意 | 反转是不是被写烂了 | 卖惨式反转；靠夸张音效撑的反差；换个品类照样成立的万能剧情 |
| structure 结构 | 五拍是否齐、留人规则是否落实 | 商品登场后局面没变（C3）；CTA 只有一次（R3）；续命点缺失（R2）；硬促无依据（R4） |
| visual 画面 | 这一镜能不能真的画出来 | 内心戏；精确双人交互；否定式动作；一拍多步动作链；只写气氛不写画面（C13/C14） |"""

SYSTEM = """你是短剧剧本的判官团，五个判官同时审同一份分镜。

{judge_brief}

## 输出

只输出一个 JSON 对象，不要解释、不要代码块围栏：

{{
  "verdicts": [
    {{
      "judge": "pace",
      "score": 1,
      "note": "一句话总评",
      "issues": [
        {{
          "shot_id": 2,
          "field": "dialogue",
          "problem": "问题是什么（引用原句或描述现象）",
          "fix": "怎么改（一句话说清改法）",
          "new_text": "改后的完整内容（dialogue/description/framing 必填，见铁律 7）；无法直接替换时留空字符串",
          "tier": "invariant"
        }}
      ]
    }}
  ],
  "summary": "全片一句话结论"
}}

## 铁律

1. 五个判官都要出现，顺序固定 pace / voice / idea / structure / visual。
2. `score` 是 1–5 的整数，5 最好。
3. 每条 issue 必须指向具体镜头 `shot_id`；**全片性问题用 0**。
4. **提不出问题就给空数组**，不许为凑数硬找。宁可五个判官全空，也不要编。
5. `field` 只能是：`dialogue` / `description` / `duration` / `structure` / `framing` / `product`。
6. `tier` 判定：
   - `invariant` —— 违反 C1–C14 任一条，或违反 R4（无依据的硬促）
   - `default` —— 不违规，但明显削弱成片效果
   - `taste` —— 纯粹个人口味，换个导演就可能不这么拍
   **拿不准就用 taste。**
7. `new_text` 是「这条意见机器能不能执行」的分界线，**能改就必须给出改后的整句**：
   - `field` 是 `dialogue` / `description` / `framing` 时，只要「改写」就能解决，
     **必须**给完整替换内容（台词给改后的整句台词、画面给改后的整段 description、
     景别给新的景别词）。应用时是**整格替换**，所以必须是能直接用的完整内容，不是片段。
   - `field` 是 `framing` 时，`new_text` **只填景别词**（全景 / 中景 / 近景 / 特写 /
     中景转近景）；运镜、光线、质感这类问题一律写进 `description` 的改写里，别塞进景别。
   - 只有「这一镜得整段重写」「结构/时长/商品设置问题」「要跟人商量的」才留空字符串。
   - 留空 = 这条只能人工处理，界面不会给「应用」按钮 —— 所以别拿留空偷懒。
8. 改写台词时，原台词里的**数字必须原样保留**（价格、数量、规格、折扣）。
"""


# ---------- 数字保真 ----------
_NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def numbers(text: str) -> set[str]:
    return set(_NUM_RE.findall(text or ""))


def keeps_numbers(old: str, new: str) -> bool:
    """改写后的台词必须覆盖原句里的每一个数字。"""
    return numbers(old).issubset(numbers(new))


# ---------- 输入整理 ----------
def _shots_brief(shots: list[dict]) -> str:
    rows = []
    for i, s in enumerate(shots, 1):
        if not isinstance(s, dict):
            continue
        rows.append(
            "[#{id}] {dur}s ｜ {fr} ｜ {cam} ｜ 商品：{prod}\n"
            "画面：{desc}\n"
            "台词：{line}\n"
            "用途：{why}".format(
                id=s.get("id", i),
                dur=s.get("duration"),
                fr=s.get("framing") or "—",
                cam=s.get("camera") or "—",
                prod="是" if s.get("product") else "否",
                desc=s.get("description") or "",
                line=s.get("dialogue") or "（无）",
                why=s.get("purpose") or "",
            )
        )
    return "\n\n".join(rows)


def build_user(doc: dict) -> str:
    p = doc.get("product") or {}
    a = doc.get("answers") or {}
    sb = doc.get("storyboard_json") or {}
    sc = doc.get("script_json") or {}
    shots = sb.get("shots") or []
    total = sum(s.get("duration") or 0 for s in shots
                if isinstance(s, dict) and isinstance(s.get("duration"), (int, float)))
    chars = "\n".join(
        f"- {c.get('name')}：{c.get('identity')}｜外观锚 {c.get('appearance')}"
        for c in (sc.get("characters") or []) if isinstance(c, dict)
    ) or "（无）"
    pts = "\n".join(f"- {x}" for x in (p.get("points") or [])) or "（未给）"
    return (
        f"【商品】{p.get('name','')}\n【卖点】\n{pts}\n"
        f"【目标人群】{p.get('audience') or '（未给）'}\n"
        f"片长设定：{a.get('duration')}s ｜ 商品角色：{a.get('role')}\n\n"
        f"【结构卡】\n{doc.get('card','')}\n\n"
        f"【角色】\n{chars}\n\n"
        f"【分镜 · 共 {len(shots)} 镜 · 合计 {total:g} 秒】\n{_shots_brief(shots)}"
    )


# ---------- 结果整理 ----------
def sanitize(obj: dict, shots: list[dict]) -> tuple[dict, list[str]]:
    """校验判官输出：三档归一、镜头存在性、数字保真。返回 (结果, 丢弃记录)。"""
    ids = {s.get("id", i) for i, s in enumerate(shots, 1) if isinstance(s, dict)}
    by_id = {s.get("id", i): s for i, s in enumerate(shots, 1) if isinstance(s, dict)}

    out, dropped = [], []
    seen = set()
    for v in obj.get("verdicts") or []:
        if not isinstance(v, dict):
            continue
        judge = str(v.get("judge") or "").strip().lower()
        if judge not in JUDGES:
            dropped.append(f"未知判官「{v.get('judge')}」")
            continue
        seen.add(judge)
        issues = []
        for it in v.get("issues") or []:
            if not isinstance(it, dict):
                continue
            try:
                sid = int(it.get("shot_id"))
            except (TypeError, ValueError):
                dropped.append(f"{judge}：shot_id 不是整数")
                continue
            if sid != 0 and sid not in ids:
                dropped.append(f"{judge}：镜头 #{sid} 不存在")
                continue
            tier = str(it.get("tier") or "").strip().lower()
            if tier not in TIERS:
                tier = "taste"

            new_text = str(it.get("new_text") or "").strip()
            if new_text and sid in by_id:
                old = ""
                if str(it.get("field")) == "dialogue":
                    old = by_id[sid].get("dialogue") or ""
                if old and not keeps_numbers(old, new_text):
                    dropped.append(
                        f"{judge}：#{sid} 改写丢失数字（原 {sorted(numbers(old))} → 新 {sorted(numbers(new_text))}）"
                    )
                    new_text = ""
                    tier = "taste"

            issues.append(
                {
                    "shot_id": sid,
                    "field": str(it.get("field") or ""),
                    "problem": str(it.get("problem") or "").strip(),
                    "fix": str(it.get("fix") or "").strip(),
                    "new_text": new_text,
                    "tier": tier,
                }
            )

        try:
            score = int(v.get("score"))
        except (TypeError, ValueError):
            score = 0
        out.append(
            {
                "judge": judge,
                "score": max(0, min(5, score)),
                "note": str(v.get("note") or "").strip(),
                "issues": issues,
            }
        )

    for j in JUDGES:
        if j not in seen:
            out.append({"judge": j, "score": 0, "note": "判官未返回结果", "issues": []})

    out.sort(key=lambda x: JUDGES.index(x["judge"]))
    for v in out:
        v["issues"].sort(key=lambda i: (TIER_RANK.get(i["tier"], 2), i["shot_id"]))

    return {
        "verdicts": out,
        "summary": str(obj.get("summary") or "").strip(),
        "counts": {
            "invariant": sum(1 for v in out for i in v["issues"] if i["tier"] == "invariant"),
            "default": sum(1 for v in out for i in v["issues"] if i["tier"] == "default"),
            "taste": sum(1 for v in out for i in v["issues"] if i["tier"] == "taste"),
            "dropped": len(dropped),
        },
        "dropped": dropped,
    }
