"""商品短剧 · 出片后的 7 维质量合同 + 三档结论 + 五种处置。

结构来源：开源项目 **clipforge**（AGPL-3.0）`src/lib/generation-quality.ts`
的 `:123`（合同权重）/ `:269`（判分）/ `:281`（处置表）——**只抽做法、不复制代码**。

为什么要这一层：出片是**抽卡**，一条 5 秒要钱，但「这条能不能用」现在全靠主人
自己点开看。竞品把这件事写成合同：七维打分 → 三档结论 → 处置建议。
**建议永远是建议**（`:281` 原文「永远不自动执行」）——花钱的动作必须人点。

判据原样保留：

  · 权重（`:123`）：镜头对齐 24 / 画面质量 18 / 时序连贯 18（仅视频）/
    主体一致 10 或 20 / 动作落地 14 或 8 / 跨镜连贯 12 或 6 / 文字完整 10 或 4。
    **商品或人物关键镜**：主体权重升到 20 且**变成必过项**。
  · 判分（`:269`）：有 critical → reject；任一必过项 <60 → reject；总分 <65 → reject；
    总分 ≥82 且置信 ≥0.55 且所有必过项 ≥70 → accept；其余 review。
  · **模型缺某一维 → 记 50 分 / 置信 0.2 /「未可靠评估」**，不假装评过。
  · 处置（`:281`）五种：接受 / 人工看 / 换模型（同型号连续被拒 ≥2）/
    局部后期修（只有文字完整崩且总分 ≥65）/ 重生成。

我们自己补的一条（竞品没写，但不补会骗人）：
  **总分 = 权重加权平均，分母是「参与评分的权重和」**。竞品两套权重总和不一样
  （106 / 98），不归一化就没法用同一条 65/82 的线比。
"""
from __future__ import annotations

import json
import re

#: 七维（顺序 = 界面展示顺序；`temporal_coherence` 只对视频有意义）
DIMS = (
    ("shot_alignment", "镜头对齐"),
    ("visual_fidelity", "画面质量"),
    ("temporal_coherence", "时序连贯"),
    ("subject_fidelity", "主体一致"),
    ("action_binding", "动作落地"),
    ("continuity", "跨镜连贯"),
    ("text_integrity", "文字完整"),
)
LABEL = dict(DIMS)

#: 一镜的「崩」线（必过项 <60 直接 reject 也是这条线）
BROKEN = 60
#: reject / accept 的总分线（`:269`）
REJECT_TOTAL = 65
ACCEPT_TOTAL = 82
ACCEPT_CONFIDENCE = 0.55
REQUIRED_PASS = 70

#: 默认权重（`:123`）
WEIGHT_BASE = {
    "shot_alignment": 24,
    "visual_fidelity": 18,
    "temporal_coherence": 18,
    "subject_fidelity": 10,
    "action_binding": 14,
    "continuity": 12,
    "text_integrity": 10,
}
#: 商品/人物关键镜：主体权重升到 20，其余三项按竞品的第二套数值降下来
WEIGHT_KEY = {
    "shot_alignment": 24,
    "visual_fidelity": 18,
    "temporal_coherence": 18,
    "subject_fidelity": 20,
    "action_binding": 8,
    "continuity": 6,
    "text_integrity": 4,
}

#: 模型没给这一维时的记分（`:269` 最后一条）
MISSING = {"score": 50, "confidence": 0.2, "note": "模型没评这一维（未可靠评估）"}

#: 五种处置（`:281`）。`costs` = 会不会再花钱；`auto` 恒为 False。
ACTIONS = {
    "accept": {
        "key": "accept", "label": "接受这条",
        "why": "达到接受线：总分 ≥82、置信 ≥0.55、必过项都 ≥70。",
        "costs": False, "auto": False,
    },
    "review": {
        "key": "review", "label": "自己看一眼再定",
        "why": "没到接受线也没到驳回线 —— 机器判不了，人看一遍最省。",
        "costs": False, "auto": False,
    },
    "switch_model": {
        "key": "switch_model", "label": "换一个型号重出",
        "why": "同一型号已经连续被拒 ≥2 次：不是这次没抽好，是这个型号不适合这条。",
        "costs": True, "auto": False,
    },
    "local_fix": {
        "key": "local_fix", "label": "只修文字，不重出",
        "why": "只有「文字完整」这一维崩、总分仍 ≥65：画面本身可用，字幕/文字后期单独处理。",
        "costs": False, "auto": False,
    },
    "regenerate": {
        "key": "regenerate", "label": "用同型号重出这一段",
        "why": "画面本身不合格，只能重抽。",
        "costs": True, "auto": False,
    },
}


# ---------------------------------------------------------------- 输入清洗

def _score(value) -> int | None:
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return max(0, min(100, n))


def _confidence(value) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0.5          # 模型没说置信度：给中性值，别硬吹也别硬踩
    return max(0.0, min(1.0, f))


def _clean_issues(raw) -> list[dict]:
    out: list[dict] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        dim = str(item.get("dim") or "").strip()
        text = str(item.get("text") or item.get("note") or "").strip()[:200]
        sev = str(item.get("severity") or "minor").strip().lower()
        if sev not in ("critical", "major", "minor"):
            sev = "minor"
        if not text:
            continue
        out.append({"dim": dim if dim in LABEL else "", "severity": sev, "text": text})
    return out


# ---------------------------------------------------------------- 合同

def weigh(*, video: bool = True, key_shot: bool = False) -> dict:
    """这一镜适用的权重表。图片没有「时序连贯」这一维。"""
    table = dict(WEIGHT_KEY if key_shot else WEIGHT_BASE)
    if not video:
        table.pop("temporal_coherence", None)
    return table


def evaluate(raw, *, video: bool = True, key_shot: bool = False) -> dict:
    """把模型给的分（或一份人工填的分）算成合同结论。

    `raw` 形如 `{"dims": {"shot_alignment": 84, ...}, "confidence": {...}, "issues": [...]}`，
    也接受每一维直接给 `{"score": .., "confidence": .., "note": ..}`。
    缺的维按 `MISSING` 记 50 分 / 置信 0.2 —— **不假装评过**。
    """
    source = raw if isinstance(raw, dict) else {}
    given = source.get("dims") if isinstance(source.get("dims"), dict) else source
    conf_map = source.get("confidence") if isinstance(source.get("confidence"), dict) else {}
    weights = weigh(video=video, key_shot=key_shot)
    required = {"subject_fidelity"} if key_shot else set()

    rows: list[dict] = []
    num = 0.0
    den = 0.0
    cnum = 0.0
    for key, label in DIMS:
        if key not in weights:
            continue
        raw_val = given.get(key) if isinstance(given, dict) else None
        detail = raw_val if isinstance(raw_val, dict) else {"score": raw_val}
        score = _score(detail.get("score"))
        assessed = score is not None
        conf_given = detail.get("confidence", conf_map.get(key))
        if not assessed:
            score = MISSING["score"]
            # 没评过的维不许给中性置信：要低到不可能凑出 accept（`:269` 末条）
            conf = MISSING["confidence"] if conf_given is None else _confidence(conf_given)
        else:
            conf = _confidence(conf_given)
        note = str(detail.get("note") or ("" if assessed else MISSING["note"]))[:200]
        w = weights[key]
        rows.append({
            "key": key, "label": label, "score": score, "confidence": conf,
            "weight": w, "required": key in required, "assessed": assessed, "note": note,
        })
        num += score * w
        den += w
        cnum += conf * w

    total = int(round(num / den)) if den else 0
    confidence = round(cnum / den, 2) if den else 0.0
    issues = _clean_issues(source.get("issues"))

    reasons: list[str] = []
    critical = [i for i in issues if i["severity"] == "critical"]
    low_required = [r for r in rows if r["required"] and r["score"] < BROKEN]
    if critical:
        reasons.append(f"有 {len(critical)} 条 critical 问题")
    if low_required:
        reasons.append("必过项没到 60：" + "、".join(r["label"] for r in low_required))
    if total < REJECT_TOTAL:
        reasons.append(f"总分 {total} < {REJECT_TOTAL}")

    # 任何**评过的**维崩到 60 以下，都不许判 accept。
    # 出处：`:281` 第 4 行专门给「只有文字崩」留了处置 —— 那条只有在
    # 「文字崩 = 一定够不到 accept」时才可能发生，否则它永远被 accept 吃掉。
    broken = [r for r in rows if r["assessed"] and r["score"] < BROKEN]

    if reasons:
        verdict = "reject"
    elif (not broken and total >= ACCEPT_TOTAL and confidence >= ACCEPT_CONFIDENCE
          and all(r["score"] >= REQUIRED_PASS for r in rows if r["required"])):
        verdict = "accept"
    else:
        verdict = "review"
        if broken:
            reasons.append("有维崩了：" + "、".join(
                f"{r['label']} {r['score']}" for r in broken))
        if total < ACCEPT_TOTAL:
            reasons.append(f"总分 {total} 没到接受线 {ACCEPT_TOTAL}")
        if confidence < ACCEPT_CONFIDENCE:
            reasons.append(f"置信 {confidence} 没到 {ACCEPT_CONFIDENCE}")
        low_pass = [r for r in rows if r["required"] and r["score"] < REQUIRED_PASS]
        if low_pass:
            reasons.append("必过项没到 70：" + "、".join(r["label"] for r in low_pass))

    return {
        "dims": rows,
        "total": total,
        "confidence": confidence,
        "verdict": verdict,
        "reasons": reasons,
        "issues": issues,
        "key_shot": bool(key_shot),
        "video": bool(video),
    }


def broken_dims(result: dict) -> list[str]:
    """真正崩掉的维（只算评过的；没评不等于是坏的）。"""
    return [r["key"] for r in (result.get("dims") or [])
            if r.get("assessed") and r["score"] < BROKEN]


def only_text_broken(result: dict) -> bool:
    """只有「文字完整」崩塌、别的都还在 60 以上（`:281` 第 4 行）。"""
    return broken_dims(result) == ["text_integrity"]


def recommend(result: dict, *, streak: int = 0) -> dict:
    """给一条处置建议 + 同级的其他选择。**永远要人点**。"""
    verdict = (result or {}).get("verdict")
    total = int((result or {}).get("total") or 0)
    if verdict == "accept":
        return dict(ACTIONS["accept"])
    if int(streak or 0) >= 2:
        return dict(ACTIONS["switch_model"])
    # 文字崩但画面能用 → 修文字，不重出（这条要先于 review：
    # 只崩文字通常总分还在 65 以上，会落进 review，等人工看一眼就白花了）
    if only_text_broken(result) and total >= REJECT_TOTAL:
        return dict(ACTIONS["local_fix"])
    if verdict != "reject":
        return dict(ACTIONS["review"])
    return dict(ACTIONS["regenerate"])


def options(result: dict) -> list[dict]:
    """界面上列给人挑的全部处置（建议的那条会被标出来）。"""
    keys = ["accept", "review", "local_fix", "regenerate", "switch_model"]
    return [dict(ACTIONS[k]) for k in keys]


# ---------------------------------------------------------------- 模型侧

def build_prompt(shot: dict, *, video: bool = True, key_shot: bool = False,
                 n_frames: int = 0, refs: list[str] | None = None) -> str:
    """给视觉模型的评分指令。**只描述要评什么**，不替模型写结论。

    `n_frames` / `refs` 说明图的位置：前面几张是成片抽帧，后面几张是参考图。
    出处：clipforge `quality/route.ts:148-171` —— 它把
    `[原关键帧, 商品图, 人物图, 上一镜尾帧]` 一起递给评分模型，
    否则「主体一致」这一维只能靠模型猜商品和人物本来长什么样。
    """
    shot = shot or {}
    refs = [str(x) for x in (refs or []) if str(x).strip()]
    lines = [
        "你在给一条已经生成好的商品短剧片段打分。下面给你这一镜的**原始设定**"
        "和从成片里按时间均匀抽出的画面帧。",
        "",
    ]
    if n_frames or refs:
        order = f"前 {n_frames} 张是成片按时间均匀抽出的帧" if n_frames else ""
        if refs:
            order += ("；后面依次是参考图："
                      + "、".join(f"{i + 1}.{n}" for i, n in enumerate(refs))
                      + "（评「主体一致」时拿成片里的对象和这些参考图对比）")
        lines += [order.strip("；"), ""]
    lines += [
        f"这一镜的设定：{(shot.get('description') or '（没有文字设定）')[:400]}",
        f"景别：{shot.get('framing') or '未写'}；运镜：{shot.get('camera') or '未写'}",
        f"台词：{(shot.get('dialogue') or '无')[:200]}",
        "",
        "请按下面每一维给 0–100 的整数分，并给 0–1 的置信度（你不确定的维就把置信度写低）；"
        "某一维你判断不了就**不要编分**，直接不给这一维。",
        "",
    ]
    for key, label in DIMS:
        if key == "temporal_coherence" and not video:
            continue
        lines.append(f"- {key}（{label}）：{_dim_brief(key)}")
    if key_shot:
        lines.append("")
        lines.append("这是商品/人物关键镜：subject_fidelity 是这次的重点。")
    lines += [
        "",
        "只输出 JSON，不要解释、不要代码块：",
        '{"dims": {"shot_alignment": {"score": 0, "confidence": 0.0, "note": ""}, ...},'
        ' "issues": [{"dim": "shot_alignment", "severity": "critical|major|minor", "text": ""}]}',
        "issues 只写你**真的看见了**的问题；没看见就空数组。",
    ]
    return "\n".join(lines)


def _dim_brief(key: str) -> str:
    return {
        "shot_alignment": "画面是不是真的拍成了上面这段设定（动作、景别、道具对不对）",
        "visual_fidelity": "画面本身的干净程度（糊、糊边、畸变、穿帮、糊成一团）",
        "temporal_coherence": "画面在时间上连不连贯（闪烁、跳变、物体凭空出现或消失）",
        "subject_fidelity": "商品和人物的外观是否和参考图一致（形状、颜色、脸、服装）",
        "action_binding": "设定里的动作有没有真的落到画面上（不是只有摆拍）",
        "continuity": "和相邻镜头的衔接（同一人、同一场景、同一光向）",
        "text_integrity": "画面里出现的文字（包装上的字、字幕、标识）有没有变形、错字、乱码",
    }[key]


_THINK_RE = re.compile(r"<think.*?</think>", re.S | re.I)
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.S | re.I)


def parse(raw_text: str) -> dict:
    """把模型输出洗成 `evaluate` 能吃的字典。解析不出来就抛 ValueError。"""
    text = _THINK_RE.sub("", raw_text or "")
    fence = _FENCE_RE.search(text)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("模型没给 JSON")
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        raise ValueError(f"模型给的 JSON 解析不了：{e}") from e
    if not isinstance(data, dict):
        raise ValueError("模型给的不是一个对象")
    return data
