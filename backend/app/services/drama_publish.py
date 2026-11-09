"""发布文案包（E10）—— 3 标题 + 话题标签 + 种草文案 + 评论区运营包。

出处：clipforge `src/lib/publish-pack.ts:1-290`，**逐字照抄**：
  · 品类/平台话题池 `:49-77`
  · 标题钩子池（中英各一套，按商品名确定性抽取）`:138-178`
  · 评论区运营包 `:186-220`（置顶自问自答 + 三条异议回复；**明令不许伪造顾客证言**）
  · 文案组装 `:222-272`（先裁主句再接 CTA，保证行动号召永不被截断）
  · AI 声明提示 `:279-290`
  · LLM 提示词 `:97-134`（中英两套，JSON 契约一致）

两处本地化（都是「接入」不是改规则）：
1. 品类/平台传中文（我们表单就是中文）→ 内部映射成竞品的英文 key。
2. 店铺链接复用 `drama_qr.build_shop_link`（同一支 UTM 组装，别造第二份）。

🩸 模板版是**零费用、确定性**的：同一商品永远出同一套标题；要更好的文案走 LLM 版。
🩸 评论区运营包**绝不生成假评论**（`notice` 是写死的，模型改不了）。
"""
from __future__ import annotations

import re

from app.services import drama_qr

#: 品类（竞品 `publish-pack.ts:49-56`）
CATEGORY_TAGS = {
    "beauty": ["好物分享", "美妆", "护肤", "变美", "平价好物", "种草"],
    "food": ["美食", "好吃推荐", "零食", "吃货日常", "干饭人", "种草"],
    "home": ["家居好物", "居家生活", "生活好物", "收纳", "好物推荐", "种草"],
    "fashion": ["穿搭", "时尚", "OOTD", "穿搭分享", "好物分享", "种草"],
    "digital": ["数码", "数码好物", "科技", "实用好物", "好物推荐", "种草"],
    "other": ["好物推荐", "种草", "好物分享", "值得买", "宝藏好物", "日常分享"],
}
CATEGORY_TAGS_EN = {
    "beauty": ["BeautyTok", "SkincareRoutine", "MakeupHacks", "BeautyFinds", "GlowUp", "TikTokMadeMeBuyIt"],
    "food": ["FoodTok", "FoodieFinds", "SnackHaul", "TikTokFood", "MustTry", "TikTokMadeMeBuyIt"],
    "home": ["HomeFinds", "HomeHacks", "CleanTok", "OrganizationTips", "CozyHome", "TikTokMadeMeBuyIt"],
    "fashion": ["OOTD", "FashionTok", "StyleInspo", "OutfitIdeas", "FashionFinds", "TikTokMadeMeBuyIt"],
    "digital": ["TechTok", "GadgetFinds", "TechReview", "CoolGadgets", "Innovation", "TikTokMadeMeBuyIt"],
    "other": ["TikTokMadeMeBuyIt", "MustHave", "ProductReview", "WorthIt", "TikTokFinds", "DailyFinds"],
}
#: 平台话题（竞品 `:69-77`）
PLATFORM_TAGS = {
    "douyin": ["抖音好物", "抖音电商"],
    "kuaishou": ["快手好物", "快手电商"],
    "xiaohongshu": ["小红书", "好物推荐"],
    "shipinhao": ["视频号", "视频号好物", "视频号小店"],
    "tiktok": ["TikTokMadeMeBuyIt", "TikTokShop"],
    "reels": ["Reels", "InstagramReels", "ReelsFinds"],
    "shorts": ["Shorts", "YouTubeShorts"],
}

#: 本地化映射：我们的中文表单值 → 竞品 key（只做 key 转换，素材一字不改）
CATEGORY_ALIASES = {
    "美妆护肤": "beauty", "beauty": "beauty",
    "食品零食": "food", "food": "food",
    "家居日用": "home", "home": "home",
    "服饰鞋包": "fashion", "fashion": "fashion",
    "数码3C": "digital", "数码": "digital", "digital": "digital",
    "其他": "other", "other": "other",
}
PLATFORM_ALIASES = {
    "抖音": "douyin", "douyin": "douyin",
    "快手": "kuaishou", "kuaishou": "kuaishou",
    "小红书": "xiaohongshu", "xiaohongshu": "xiaohongshu",
    "视频号": "shipinhao", "shipinhao": "shipinhao",
    "TikTok Shop": "tiktok", "tiktok": "tiktok", "TikTok": "tiktok",
    "reels": "reels", "Reels": "reels",
    "shorts": "shorts", "Shorts": "shorts",
}

#: 标题钩子池（竞品 `:138-159` 逐条）
TITLE_POOL_ZH = [
    {"needs_point": False, "render": lambda n, p: f"{n}也太好用了吧！后悔没早买"},
    {"needs_point": True, "render": lambda n, p: f"{n}｜{p}，谁用谁回购"},
    {"needs_point": False, "render": lambda n, p: f"三个理由让你入手{n}"},
    {"needs_point": False, "render": lambda n, p: f"谁懂啊！{n}真的绝了"},
    {"needs_point": False, "render": lambda n, p: f"别乱买了，{n}闭眼入不踩雷"},
    {"needs_point": False, "render": lambda n, p: f"{n}凭什么这么火？"},
    {"needs_point": False, "render": lambda n, p: f"用了{n}才知道之前白买了"},
    {"needs_point": False, "render": lambda n, p: f"姐妹们冲！{n}平价宝藏"},
    {"needs_point": True, "render": lambda n, p: f"{n}测评｜{p}"},
    {"needs_point": False, "render": lambda n, p: f"入手{n}前，先看这条"},
]
TITLE_POOL_EN = [
    {"needs_point": False, "render": lambda n, p: f"This {n} is a total game-changer 🤯"},
    {"needs_point": True, "render": lambda n, p: f"{n} — {p}, you'll want one"},
    {"needs_point": False, "render": lambda n, p: f"3 reasons to grab the {n}"},
    {"needs_point": False, "render": lambda n, p: f"I can't stop using this {n}"},
    {"needs_point": False, "render": lambda n, p: f"Why is everyone obsessed with {n}?"},
    {"needs_point": False, "render": lambda n, p: f"The {n} you won't regret buying"},
    {"needs_point": True, "render": lambda n, p: f"{n}: {p}"},
    {"needs_point": False, "render": lambda n, p: f"Don't buy another until you've seen this {n}"},
]


def _clip(text: str, limit: int) -> str:
    """按字符数裁剪（竞品 `:87-90`：CJK 算 1 个字符）。"""
    clean = str(text or "").strip()
    chars = list(clean)
    return clean if len(chars) <= limit else "".join(chars[:limit]).strip()


def first_selling_point(text: str | None, limit: int) -> str:
    """取第一条卖点（竞品 `:80-84`）：按中英标点/换行切，取第一个非空。"""
    if not text:
        return ""
    parts = re.split(r"[。.,，;；\n、]", str(text))
    hit = next((s.strip() for s in parts if s.strip()), "")
    return _clip(hit, limit)


def _hash_str(text: str) -> int:
    total = 0
    for ch in text:
        total = (total + ord(ch)) & 0xFFFFFFFF
    return total


def pick_titles(name: str, point: str, en: bool) -> list[str]:
    """确定性抽 3 条标题（竞品 `:169-178`）。没卖点时抽不到「需要卖点」的模板。"""
    pool = [t for t in (TITLE_POOL_EN if en else TITLE_POOL_ZH)
            if point or not t["needs_point"]]
    if not pool:
        return []
    start = _hash_str(name) % len(pool)
    out = []
    for i in range(3):
        text = pool[(start + i) % len(pool)]["render"](name, point)
        out.append(_clip(text, 60 if en else 22))
    return out


def build_comment_kit(product_name: str, selling_points: str | None,
                      locale: str = "zh") -> dict:
    """评论区运营包（竞品 `:186-220` 逐字）。

    🩸 只出「博主第一人称回复」；**不生成假顾客证言**（notice 写死，模型不能改）。
    """
    en = locale == "en"
    name = _clip((product_name or "").strip() or ("this find" if en else "这款好物"),
                 40 if en else 16)
    point = first_selling_point(selling_points, 40 if en else 12)
    if en:
        return {
            "pinned": (f"Most-asked question first: is the {name} actually worth it? "
                       f"I've been using it myself{(' — ' + point) if point else ''}, "
                       "ask me anything below 👇"),
            "objections": [
                {"q": "Too expensive / not worth it",
                 "a": "Break it down per use and it's less than a coffee — and you can return it if it's not for you."},
                {"q": "Does it really work?",
                 "a": f"Fair question — the video shows exactly how I use it{(' (' + point + ')') if point else ''}. Happy to post a follow-up after longer use."},
                {"q": "Still hesitating",
                 "a": "No rush — save this video, check the reviews, and grab it when you're ready."},
            ],
            "notice": ("Reply with your real experience only — fabricated customer testimonials "
                       "and seeded fake comments are an enforcement target on every platform."),
        }
    return {
        "pinned": f"评论区问得最多的先答：{name}到底值不值？我自己在用{('，' + point) if point else ''}，有问题评论区直接问👇",
        "objections": [
            {"q": "太贵了/不值", "a": "拆到每次使用算一下，比一杯奶茶还便宜；不合适也支持退，先看再定。"},
            {"q": "真的有用吗", "a": f"问得好——视频里就是我的真实用法{('（' + point + '）') if point else ''}，用久了我再来追评。"},
            {"q": "还在犹豫", "a": "不着急，先收藏这条，看看评价，想好了再入。"},
        ],
        "notice": "回复只写自己的真实体验——伪造顾客证言、预埋假评论是各平台重点打击项，别碰。",
    }


def build_ai_declaration(locale: str = "zh") -> dict:
    """平台 AI 声明提示（竞品 `:279-290`）。

    🩸 我们**不默认打 AI 角标**（主人定过）；这里只提供「可选」文案，
       前端放在可选项里，不当成必做项、也不写「合规」二字。
    """
    if locale == "en":
        return {"notice": ("Optional: turn on the platform's \"AI-generated content\" toggle when "
                           "posting if you want to declare it."),
                "line": "Contains AI-generated content"}
    return {"notice": "可选：发布时若想主动声明，可勾选平台的「内容由 AI 生成」开关。",
            "line": "本视频含 AI 生成内容"}


def build_publish_pack(*, product_name: str, category: str = "",
                       selling_points: str = "", platform: str = "",
                       locale: str = "zh", shop_url: str = "",
                       affiliate_code: str = "") -> dict:
    """模板版发布包（竞品 `:222-272` 逐字）。零费用、确定性、不发网络请求。"""
    en = locale == "en"
    name = _clip((product_name or "").strip() or ("this find" if en else "这款好物"),
                 40 if en else 16)
    cat = CATEGORY_ALIASES.get((category or "").strip(), "other")
    point = first_selling_point(selling_points, 40 if en else 12)
    titles = pick_titles(name, point, en)

    platform_key = PLATFORM_ALIASES.get((platform or "").strip(), "")
    cat_tags = CATEGORY_TAGS_EN if en else CATEGORY_TAGS
    raw_name = (product_name or "").strip()
    if raw_name:
        stripped = re.sub(r"[^\w一-鿿]", "", raw_name)
        product_tag = f"#{_clip(stripped, 24 if en else 12)}"
    else:
        product_tag = ""
    tag_words = cat_tags.get(cat, cat_tags["other"]) + PLATFORM_TAGS.get(platform_key, [])
    hashtags: list[str] = []
    seen: set[str] = set()
    for tag in [product_tag, *(f"#{w}" for w in tag_words)]:
        if not tag or tag == "#" or tag in seen:
            continue
        seen.add(tag)
        hashtags.append(tag)
        if len(hashtags) >= 10:
            break

    cta = " — tap the link below to grab it 🛒" if en else "，点下方小黄车带走它～"
    lead = (f"Obsessed with {name}{(', ' + point) if point else ''}" if en
            else f"{name}真的绝了{('，' + point) if point else ''}")
    caption = _clip(lead, (130 if en else 40) - len(list(cta))) + cta

    shop_link = drama_qr.build_shop_link(
        shop_url, platform=platform_key or None, affiliate_code=affiliate_code)
    pack = {
        "titles": titles,
        "hashtags": hashtags,
        "caption": caption,
        "ai_declaration": build_ai_declaration(locale),
        "comment_kit": build_comment_kit(product_name, selling_points, locale),
    }
    if shop_link:
        pack["shop_link"] = shop_link
    return pack


def build_publish_prompt(*, product_name: str, category: str = "",
                         product_description: str = "", platform: str = "",
                         locale: str = "zh") -> str:
    """LLM 提示词（竞品 `:97-134` 逐字，JSON 契约一致）。"""
    if locale == "en":
        hint = f"Target platform: {platform}." if platform else "Target platform: TikTok / Reels / Shorts."
        return f"""You are a seasoned e-commerce short-video marketer. Write publishing copy for the product below, entirely in ENGLISH. {hint}
Product: {product_name}
{f'Category: {category}\n' if category else ''}{f'Selling points: {product_description}\n' if product_description else ''}
Output STRICT JSON only (no extra text):
{{
  "titles": ["3 catchy short titles with emotion/pain-point/number hooks, each <= 60 chars"],
  "hashtags": ["6-10 hashtags with #, TikTok-style; the FIRST must be a product-specific/branded hashtag (the product name, no spaces) for keyword-search discovery, the rest matching category and platform trends"],
  "caption": "one-line caption, conversational, with a clear call to action, <= 150 chars; lead with the main product keyword in the first ~30 characters for search discoverability",
  "commentKit": {{
    "pinned": "a pinned self-Q&A comment: raise THE question buyers hesitate on, answer it from the creator's first-person real experience, invite questions; <= 200 chars",
    "objections": [{{ "q": "recurring objection (price / does it work / hesitation)", "a": "friendly first-person reply, honest, no invented claims, <= 120 chars" }}]
  }}
}}
commentKit rules: comments are the video's second landing page. 2-3 objections. NEVER write fake customer testimonials or seeded "I bought it and love it" comments — first-person creator replies only."""
    hint = f"目标平台：{platform}。" if platform else "目标平台：抖音/快手/小红书。"
    return f"""你是资深电商带货短视频运营。请为以下商品生成发布文案。{hint}
商品名称：{product_name}
{f'品类：{category}\n' if category else ''}{f'卖点：{product_description}\n' if product_description else ''}
要求严格输出 JSON（不要多余文字）：
{{
  "titles": ["3 个吸睛短标题，含情绪/痛点/数字钩子，每个 ≤20 字"],
  "hashtags": ["6-10 个带 # 的话题标签；第 1 个必须是商品专属/品牌标签（商品名、不含空格），利于商品词搜索发现，其余贴合品类与平台热点"],
  "caption": "一句话种草文案，口语化，含行动号召，≤40 字；开头先点出商品核心关键词（利于平台搜索发现）",
  "commentKit": {{
    "pinned": "一条置顶自问自答评论：提出买家最犹豫的那个问题，用博主第一人称真实体验回答，并邀请提问；≤80 字",
    "objections": [{{ "q": "高频异议（价格贵/有没有用/还在犹豫）", "a": "第一人称友好回复，诚实不编造，≤50 字" }}]
  }}
}}
commentKit 规则：评论区是视频的第二落地页，异议给 2-3 条；绝不写伪造顾客证言或「已买真香」式预埋假评论——只写博主第一人称回复。"""


def sanitize_llm_pack(raw, *, product_name: str, category: str = "",
                      selling_points: str = "", locale: str = "zh") -> dict:
    """把模型吐的 JSON 夹成发布包（竞品 `llm/publish/route.ts:46-79` 同款口径）。

    · titles 最多 3；hashtags 原样；caption 转字符串；
    · commentKit 只保留「q/a 都非空」的条目（≤3），缺了就用模板兜底；
    · `notice` **永远用我们的**，不许模型改写合规措辞。
    """
    data = raw if isinstance(raw, dict) else {}
    fallback = build_comment_kit(product_name, selling_points, locale)
    kit = data.get("commentKit") if isinstance(data.get("commentKit"), dict) else {}
    # 🩸 先过滤再截 3 条（竞品 `route.ts:64-70` 就是 filter→slice）：先截会把
    # 模型吐的空条目算进名额，明明有 3 条能用的只剩 1 条。
    objections = []
    raw_objections = kit.get("objections") if isinstance(kit.get("objections"), list) else []
    for item in raw_objections:
        if not isinstance(item, dict):
            continue
        q, a = item.get("q"), item.get("a")
        if isinstance(q, str) and q.strip() and isinstance(a, str) and a.strip():
            objections.append({"q": q, "a": a})
    objections = objections[:3]
    titles = data.get("titles")
    hashtags = data.get("hashtags")
    return {
        "titles": [str(t) for t in titles[:3]] if isinstance(titles, list) else [],
        "hashtags": [str(t) for t in hashtags] if isinstance(hashtags, list) else [],
        "caption": str(data.get("caption") or ""),
        "ai_declaration": build_ai_declaration(locale),
        "comment_kit": {
            "pinned": (str(kit.get("pinned")).strip()
                       if isinstance(kit.get("pinned"), str) and kit["pinned"].strip()
                       else fallback["pinned"]),
            "objections": objections or fallback["objections"],
            "notice": fallback["notice"],
        },
    }
