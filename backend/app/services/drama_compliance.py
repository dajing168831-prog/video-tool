"""合规与发布门禁 —— 纯函数，零依赖、零费用。

四份东西，全部**逻辑逐字照抄**竞品，只有字段名换成本工程的：

| 本模块 | 出处 |
|---|---|
| 广告法四类风险词 | clipforge `src/lib/ad-compliance.ts:26-95` |
| 抖音 AI 带货三条 | `src/lib/ai-commerce-compliance.ts:36-131` |
| 发布前 8 项自检 | `src/lib/publish-readiness.ts:39-212` |
| 发布门禁（最差状态胜出） | `src/lib/release-gate.ts:46-316` |

🩸 **字段映射（竞品 → 我们）**，每一处都是同一个概念，不是新规则：
- `voiceover` → `dialogue`；`textOverlay.text` → `on_screen_text`（2026-11-08 起我们有这一列，由合成器叠加）
- `type: hook/product_reveal/demo/cta` → 第一镜 / `product: true` 的镜 / 台词里的号召词
- `visualSource === "product_image"` → `product: true`
- `shotId` → `id`

🩸 **一处故意不做**：竞品第 8 项「AIGC 显式角标」我们**默认不检查** ——
主人 2026-11-05 定过「默认不打 AI 水印，文案也不许写『（合规）』」。
函数留了 `aigc_label` 形参，默认 `None` = 不检查，谁要检查谁显式传 True/False。
"""
from __future__ import annotations

# --------------------------------------------------------------------------
# 一、广告法四类风险词（ad-compliance.ts:26-67 逐字）
# --------------------------------------------------------------------------

RULES: list[dict] = [
    {
        "category": "绝对化用语",
        "severity": "high",
        "suggestion": "《广告法》第9条禁用绝对化用语，改为「之一 / 较 / 更 / 深受喜爱」等相对表述",
        "terms": [
            "最佳", "最好", "最优", "最强", "最高级", "国家级", "世界级", "顶级", "顶尖", "极致",
            "100%", "百分百", "绝对", "万能", "史上最", "无敌", "销量第一", "全网第一", "排名第一",
            "行业第一", "独一无二", "领导品牌", "王牌", "首选品牌",
            "最低价", "全网最低", "全网最低价", "史上最低", "历史最低", "销量冠军", "第一品牌",
        ],
    },
    {
        "category": "医疗/虚假功效",
        "severity": "high",
        "suggestion": "普通商品不得宣称医疗 / 治疗 / 根治等功效，删除或改为真实体验描述",
        "terms": [
            "根治", "包治", "治愈", "药到病除", "立竿见影", "三天见效", "七天见效", "永不复发",
            "彻底根除", "疗效", "抗癌", "消炎", "杀菌", "处方药", "药妆", "医学级", "医疗级", "特效药",
        ],
    },
    {
        "category": "需认证宣称",
        "severity": "med",
        "suggestion": "「纯天然 / 有机 / 零添加」需权威认证或检测依据，无依据请删除",
        "terms": ["纯天然", "零添加", "无添加", "有机食品", "100%天然"],
    },
    {
        "category": "虚假紧迫",
        "severity": "med",
        "suggestion": "虚假限时限量属平台违规营销（限流+处罚）；若非真实可举证的活动请删除，真实活动请保留凭证",
        "terms": ["最后一天", "仅此一天", "错过不再有", "马上涨价", "明天恢复原价", "最后几件", "最后几单"],
    },
]


def check_ad(text: str) -> list[dict]:
    """扫一段文字，返回命中的广告法风险词（按词去重、长词优先、high 排前）。"""
    clean = str(text or "")
    if not clean:
        return []
    seen: set[str] = set()
    out: list[dict] = []
    for rule in RULES:
        for term in rule["terms"]:
            if term not in seen and term in clean:
                seen.add(term)
                out.append({"term": term, "category": rule["category"],
                            "severity": rule["severity"],
                            "suggestion": rule["suggestion"]})
    terms = [v["term"] for v in out]
    # 长词吃掉短词（「100%」被「100%天然」包含时只报后者），免得同一处给两条相反提示
    deduped = [v for v in out
               if not any(t != v["term"] and v["term"] in t for t in terms)]
    deduped.sort(key=lambda v: 0 if v["severity"] == "high" else 1)
    return deduped


def shot_text(shot: dict) -> str:
    """一镜里所有会被观众看到/听到的字。"""
    s = shot or {}
    return " ".join([str(s.get("dialogue") or ""),
                     str(s.get("description") or ""),
                     str(s.get("text") or "")])


def check_shots(shots: list[dict]) -> list[dict]:
    """扫整张分镜表（台词 + 画面描述）→ 去重后的风险词。"""
    return check_ad(" \n ".join(shot_text(s) for s in (shots or [])))


# --------------------------------------------------------------------------
# 二、抖音 AI 带货三条（ai-commerce-compliance.ts:36-131 逐字）
# --------------------------------------------------------------------------

#: 读起来像「对比/开箱测评」的脚本风格（抖音禁止 AI 生成这类内容）
AI_REVIEW_STYLES = {"comparison", "unboxing", "对比测评", "开箱测评"}

#: 数字人被禁的五类目
DIGITAL_HUMAN_BANNED_CATEGORIES = [
    {"label": "医疗", "terms": ["医疗", "医用", "药品", "药物", "医院", "诊所", "治疗仪", "理疗"]},
    {"label": "金融理财", "terms": ["理财", "基金", "股票", "保险", "贷款", "信用卡", "投资课"]},
    {"label": "美容功效", "terms": ["美白", "祛斑", "祛痘", "抗皱", "淡纹", "丰胸", "减肥", "瘦身", "生发", "防脱"]},
    {"label": "保健功效", "terms": ["保健品", "增强免疫", "降血压", "降血糖", "降血脂", "补肾", "调理体质"]},
    {"label": "教培效果", "terms": ["提分", "包过", "保过", "速成班", "升学率"]},
]

#: AI 角色自称「我用过」—— 贴近「伪造商品使用效果」红线
PERSONAL_TESTIMONY_TERMS = [
    "亲测", "实测有效", "我用了一周", "我用了一个月", "用了三天",
    "本人使用", "自用推荐", "亲身体验",
]


def check_ai_commerce(*, style_type: str = "", has_ai_person: bool = False,
                      product_text: str = "", dialogue_text: str = "") -> list[dict]:
    """三条规则，全部 warn，不拦。"""
    out: list[dict] = []
    style = (style_type or "").strip()
    product_text = product_text or ""
    dialogue_text = dialogue_text or ""

    # 1. AI 生成的对比/开箱测评：平台禁这类内容形态，与有没有人出镜无关
    if style in AI_REVIEW_STYLES:
        out.append({
            "id": "ai_review_style",
            "zh": f"「{style}」风格在抖音有处置风险：平台规则不允许 AI 生成商品对比测评类内容。"
                  "功能保留可用——建议抖音改投口播种草/情景短剧风格，或将此风格用于其他平台",
        })

    # 2. 数字人 × 五类目
    if has_ai_person and product_text:
        for cat in DIGITAL_HUMAN_BANNED_CATEGORIES:
            hit = next((t for t in cat["terms"] if t in product_text), None)
            if hit:
                out.append({
                    "id": "digital_human_category",
                    "zh": f"商品疑似「{cat['label']}」类目（命中词「{hit}」）：抖音禁止数字人推介"
                          "医疗/金融/美容功效/保健功效/教培效果五类内容。建议改用无人物出镜的"
                          "商品实拍形态，或人工确认类目后再发布",
                })
                break  # 一个类目提示够了，别叠近似重复行

    # 3. AI 角色自称亲测
    if has_ai_person and dialogue_text:
        hit = next((t for t in PERSONAL_TESTIMONY_TERMS if t in dialogue_text), None)
        if hit:
            out.append({
                "id": "personal_testimony",
                "zh": f"AI 人物台词出现「{hit}」式亲测宣称：AI 角色虚构使用体验贴近平台"
                      "「伪造商品使用效果」红线。建议改为种草推荐表述（如「很多人反馈」「值得试试」）",
            })
    return out


# --------------------------------------------------------------------------
# 三、发布前自检（publish-readiness.ts:39-212 逐字）
# --------------------------------------------------------------------------

DUR_MIN = 15          # 太短促不了单
DUR_SWEET_HI = 45
DUR_MAX = 60          # 太长完播率掉
HOOK_MAX_SEC = 4      # 黄金 3 秒 + 1 秒容差
READ_CPS = 9          # 每秒最多念 9 个汉字，再快就读不完
PRODUCT_EARLY_SEC = 3
PRODUCT_LATE_SEC = 7

HOOK_SIGNAL = ("?", "？", "!", "！", "别再", "还在", "总是", "为什么", "怎么", "居然",
               "竟然", "没想到", "原来", "你知道", "千万别", "后悔", "踩雷", "谁懂", "绝了")
CTA_SIGNAL = ("小黄车", "下方", "点击", "购买", "带走", "链接", "加购", "抢", "下单",
              "橱窗", "入手", "戳", "领", "tap", "link", "buy", "shop", "cart", "grab")


def _cjk_len(s: str) -> int:
    return len("".join(str(s or "").split()))


def _has(s: str, needles) -> bool:
    low = str(s or "").lower()
    return any(n.lower() in low for n in needles)


def check_readiness(shots: list[dict], total_duration: float, *,
                    product_name: str = "", aigc_label: bool | None = None) -> dict:
    """跑发布前自检。`aigc_label=None` = 不检查（我们的默认：不打 AI 水印）。"""
    items: list[dict] = []

    def push(key: str, status: str, message: str) -> None:
        items.append({"key": key, "status": status, "message": message})

    # 1) 广告法风险词
    violations = check_shots(shots)
    if not violations:
        push("compliance", "pass", "无广告法风险词")
    else:
        words = " / ".join(dict.fromkeys(v["term"] for v in violations))[:120]
        push("compliance", "fail",
             f"{len(violations)} 处广告法风险词（{words}）——平台对绝对化/虚假功效易限流，建议先改")

    # 2) 开场钩子（第一镜）
    first = (shots or [{}])[0] if shots else {}
    first_text = str(first.get("dialogue") or "").strip()
    try:
        first_dur = float(first.get("duration") or 0)
    except (TypeError, ValueError):
        first_dur = 0.0
    if not first_text:
        push("hook", "fail", "缺开场钩子（第 1 镜要有人说话）")
    elif first_dur > HOOK_MAX_SEC:
        push("hook", "warn", f"开场钩子 {first_dur:g}s 偏长——黄金 3 秒内要抓住人")
    elif not _has(first_text, HOOK_SIGNAL):
        push("hook", "warn", "开场钩子偏平——加个疑问 / 痛点 / 数字会更抓人")
    else:
        push("hook", "pass", "开场钩子够短够冲")

    # 3) 时长甜区
    d = round(float(total_duration or 0))
    if d < DUR_MIN:
        push("duration", "warn", f"总时长 {d}s 偏短——信息可能不足以促单")
    elif d > DUR_MAX:
        push("duration", "warn", f"总时长 {d}s 偏长——完播率易掉，带货甜区约 21–45s")
    else:
        tail = "（偏上限）" if d > DUR_SWEET_HI else ""
        push("duration", "pass", f"总时长 {d}s 在带货甜区{tail}")

    # 4) 字幕读速
    dense = []
    for s in shots or []:
        try:
            dur = float(s.get("duration") or 0)
        except (TypeError, ValueError):
            dur = 0.0
        if dur > 0 and _cjk_len(s.get("dialogue")) / dur > READ_CPS:
            dense.append(str(s.get("id", "?")))
    if not dense:
        push("caption", "pass", "字幕节奏可读")
    else:
        push("caption", "warn",
             f"第 {'、'.join(dense)} 镜字幕过密、读不完——精简文案或加时长")

    # 5) 行动号召
    has_cta = any(_has(shot_text(s), CTA_SIGNAL) for s in (shots or []))
    if has_cta:
        push("cta", "pass", "有明确行动号召")
    else:
        push("cta", "warn", "缺明确行动号召（如「点下方小黄车」）——转化会打折")

    # 6) 带货三段式：钩子 → 展示/演示 → 号召
    missing = []
    if not first_text:
        missing.append("钩子")
    if not any(bool(s.get("product")) for s in (shots or [])):
        missing.append("展示/演示")
    if not has_cta:
        missing.append("号召")
    if not missing:
        push("structure", "pass", "带货三段式完整")
    else:
        push("structure", "warn",
             f"结构缺「{'、'.join(missing)}」——带货三段式：钩子 → 展示/演示 → 号召")

    # 7) 商品前 3 秒露出
    name = (product_name or "").strip()
    if name:
        elapsed = 0.0
        first_at: float | None = None
        for s in shots or []:
            shows = (bool(s.get("product")) or name in str(s.get("dialogue") or "")
                     or name in str(s.get("description") or ""))
            if shows:
                first_at = elapsed
                break
            try:
                elapsed += float(s.get("duration") or 0)
            except (TypeError, ValueError):
                pass
        if first_at is not None and first_at <= PRODUCT_EARLY_SEC:
            push("productEarly", "pass", "商品在前 3 秒内出现")
        elif first_at is not None and first_at <= PRODUCT_LATE_SEC:
            push("productEarly", "warn",
                 f"商品约 {round(first_at)}s 才出现——挂车视频应在前 3 秒露出商品")
        else:
            where = ("全程没有明确出现" if first_at is None
                     else f"约 {round(first_at)}s 才出现")
            push("productEarly", "fail",
                 f"商品{where}——平台把「先讲故事最后亮产品」的挂车视频判为骗完播限流，"
                 "请把商品放进开场镜头")

    # 8) AIGC 角标 —— 默认不查（主人定过：默认不打水印）。显式传了才判。
    if aigc_label is True:
        push("aigc", "pass", "已烧录 AIGC 显式角标（片头 ≥2 秒）")
    elif aigc_label is False:
        push("aigc", "warn",
             "未烧录 AIGC 显式角标——2026-07 平台新规要求片头/片尾 ≥2 秒 AI 标识"
             "（仅 AI 配音也算须标注），未标注有限流风险")

    n_pass = sum(1 for i in items if i["status"] == "pass")
    n_warn = sum(1 for i in items if i["status"] == "warn")
    n_fail = sum(1 for i in items if i["status"] == "fail")
    overall = "needsWork" if n_fail else ("risky" if n_warn else "ready")
    return {"items": items, "pass": n_pass, "warn": n_warn, "fail": n_fail,
            "overall": overall}


# --------------------------------------------------------------------------
# 四、发布门禁（release-gate.ts:46-316 逐字；最差状态胜出）
# --------------------------------------------------------------------------

def gate_from_readiness(report: dict | None) -> dict:
    if not report:
        return {"id": "readiness", "status": "fail",
                "message": "没有可检查的脚本——先生成并选择脚本", "problems": []}
    problems = [i["message"] for i in report.get("items", []) if i["status"] != "pass"]
    overall = report.get("overall")
    if overall == "needsWork":
        return {"id": "readiness", "status": "fail",
                "message": f"脚本发布就绪检查未过（{report.get('fail', 0)} 项需修复、"
                           f"{report.get('warn', 0)} 项有风险）",
                "problems": problems}
    if overall == "risky":
        return {"id": "readiness", "status": "warn",
                "message": f"脚本发布就绪检查有 {report.get('warn', 0)} 项风险提示",
                "problems": problems}
    return {"id": "readiness", "status": "pass",
            "message": "脚本发布就绪检查全部通过", "problems": []}


def gate_from_qc(qc: dict | None) -> dict:
    """成片技术质检 → 门禁项。`None` = 还没成片，本身就该拦。"""
    if not qc:
        return {"id": "qc", "status": "fail",
                "message": "还没有成片——先合成视频再过门禁", "problems": []}
    problems = [c.get("zh") or "" for c in qc.get("checks", [])
                if c.get("level") != "ok"]
    level = qc.get("level")
    if level == "fail":
        n = sum(1 for c in qc.get("checks", []) if c.get("level") == "fail")
        return {"id": "qc", "status": "fail",
                "message": f"成片质检不通过（{n} 项失败）", "problems": problems}
    if level == "warn":
        return {"id": "qc", "status": "warn",
                "message": f"成片质检有 {len(problems)} 项警告", "problems": problems}
    return {"id": "qc", "status": "pass", "message": "成片质检通过", "problems": []}


def gate_from_quality(rows: list[dict]) -> dict:
    """7 维语义验收 → 门禁项。人工拒绝 = fail；自动存疑/没评 = warn。"""
    if not rows:
        return {"id": "quality", "status": "pass",
                "message": "没有需要语义验收的 AI 生成镜头", "problems": []}
    rejected = [r for r in rows if r.get("humanDecision") == "rejected"]
    pending = [r for r in rows if not r.get("humanDecision") and not r.get("verdict")]
    flagged = [r for r in rows
               if not r.get("humanDecision") and r.get("verdict") in ("review", "reject")]
    problems = ([f"第 {r.get('shotId')} 段：人工已标记不采用" for r in rejected]
                + [f"第 {r.get('shotId')} 段：尚未运行镜头质量评估" for r in pending]
                + [f"第 {r.get('shotId')} 段：自动评估"
                   f"{(' ' + str(round(r['overall']))) if r.get('overall') is not None else ''}"
                   "，需人工确认" for r in flagged])
    if rejected:
        return {"id": "quality", "status": "fail",
                "message": f"{len(rejected)} 个当前镜头已被人工拒绝，请先切换或修复",
                "problems": problems}
    if pending or flagged:
        return {"id": "quality", "status": "warn",
                "message": f"{len(pending) + len(flagged)} 个 AI 镜头仍需质量确认",
                "problems": problems}
    return {"id": "quality", "status": "pass",
            "message": "当前 AI 镜头均已通过自动建议或人工验收", "problems": []}


def gate_from_credits(manifest: dict | None) -> dict:
    """素材授权清单 → 门禁项。

    🩸 我们和竞品不同：商品短剧的素材**全部是使用者自己上传的**（商品图 + 人物照），
    没有外部免版权素材，所以「无授权记录」在这里不是风险，不该报 warn 吓人。
    """
    if not manifest:
        return {"id": "credits", "status": "pass",
                "message": "素材均为你自己上传的（商品图/人物图），无外部版权素材",
                "problems": []}
    rows = list(manifest.get("items") or []) + ([manifest["bgm"]] if manifest.get("bgm") else [])
    review = [r for r in rows if r.get("risk") == "review"]
    problems = [f"{'BGM' if r.get('shotId', 0) < 0 else '第 %d 段' % (r.get('shotId', 0) + 1)}："
                f"{r.get('license') or '许可未知'} — {(r.get('note') or {}).get('zh', '')}"
                for r in review]
    need_attr = int((manifest.get("summary") or {}).get("needsAttribution") or 0)
    if need_attr:
        problems.append(f"{need_attr} 条署名行需随发布文案附上（见授权清单）")
    need_review = int((manifest.get("summary") or {}).get("needsReview") or 0)
    if need_review:
        return {"id": "credits", "status": "warn",
                "message": f"{need_review} 项素材许可需人工复核（NC/ND/未知）——投流前确认或替换",
                "problems": problems}
    if need_attr:
        return {"id": "credits", "status": "warn",
                "message": f"素材可商用，但 {need_attr} 条署名需随发布附上",
                "problems": problems}
    return {"id": "credits", "status": "pass",
            "message": "素材授权可商用，无需署名", "problems": problems}


def gate_from_ai_policy(warnings: list[dict]) -> dict:
    """AI 带货平台规则 → 门禁项。**永远只 warn，不 fail**（规则是判断题，人拍板）。"""
    if not warnings:
        return {"id": "aiPolicy", "status": "pass",
                "message": "AI 带货平台规则检查通过（测评形态/数字人类目/亲测宣称）",
                "problems": []}
    return {"id": "aiPolicy", "status": "warn",
            "message": f"AI 带货平台规则有 {len(warnings)} 项风险提示"
                       "（抖音 2026-07 规则，功能不受限，人工确认后发布）",
            "problems": [w.get("zh") or "" for w in warnings]}


def build_gate(items: list[dict]) -> dict:
    """合成最终报告 —— **最差状态胜出**。"""
    n_pass = sum(1 for i in items if i["status"] == "pass")
    n_warn = sum(1 for i in items if i["status"] == "warn")
    n_fail = sum(1 for i in items if i["status"] == "fail")
    status = "fail" if n_fail else ("warn" if n_warn else "pass")
    verdict = {
        "fail": "未过发布门禁——存在必须修复的问题，请勿直接发布/投流",
        "warn": "有条件通过——存在需人工确认的风险项，确认后再发布",
        "pass": "通过发布门禁——自动检查未发现拦截项",
    }[status]
    return {"status": status, "items": items,
            "summary": {"pass": n_pass, "warn": n_warn, "fail": n_fail},
            "verdict": verdict}
