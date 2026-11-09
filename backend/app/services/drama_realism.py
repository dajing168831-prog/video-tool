"""商品短剧 · 通用真实感层三档（能力表 C12）。

出处（逐字照抄，不改语气、不加词）：
  · 三档语义：clipforge `src/lib/motion-prompt.ts:53-70`（`MotionRealismTier`）
  · 各层素材：同文件 `:150-260` —— `CATEGORY_CONSTRAINTS`（品类材质保真）、
    `PHYSICAL_ACTION_LEXICON`（动作 + 材质反应）、`LIVING_BG`（活背景）、
    `FABRIC_HAIR_LAG`（发丝/衣料滞后）
  · 情绪过程：`src/lib/emotion-acting.ts:26-90` —— `SHOT_EMOTION` / `EMOTION_PROCESS`
  · 拼装顺序：`motion-prompt.ts:395-425`（动作 → 情绪 → 活背景 → 发丝 → … → 品类约束）

三档（与竞品逐档等价）：
  auto         品类材质约束 + 物理交互 + 活背景 + 发丝/衣料惯性 + 情绪过程
  constraints  **只**加品类材质约束（不加任何动作短语）
  off          一层都不加 —— 等于没接这个功能时的提示词形状

🩸 边界（别自己扩）：
  · 竞品的 `QUALITY_TAIL` / `SOUND_DIRECTION` / `REAL_FACE_CONSTRAINT` **不是**三档管的东西
    （它们在竞品里永远拼上）。我们这边已有自己的「画质与质感」「无bgm」段，
    所以这里**只**搬三档真正开合的那五层；否则 `off` 就不等于老形状了。
  · 竞品的 `social_proof` 我们没有对应拍（剧是五拍），所以 `delighted` 这一档不会命中 ——
    不硬造映射。

我们这边的判定口径（schema 与竞品不同，必须写清依据）：
  · 镜型 `shot_type`：竞品有 `asset.type` 字段，我们的分镜**没有** type
    （`output_storyboard.md` 的 8 个字段里只有 `purpose`）。
    于是按 `purpose` 归一到竞品六个镜型；归不出来的返回空串 —— **不做位置猜测**。
  · 商品镜 `productShot`：竞品 = `visualSource === "product_image" || type ∈ {product_reveal,demo,cta}`
    （`assets/page.tsx:88,573`）；我们直接读分镜自己的 `product: true` 字段。
  · 人物镜 `personShot`：竞品 = 这一镜绑了 `characterId`（`:576`）。
    我们分镜没有人物绑定，但 C7 硬性要求「每镜画面描述必须带该角色的外观锚」
    （`output_storyboard.md`「场景一致性」）→ 角色名出现在 `description` 里即算人物镜。
    没有角色表（如口播/话题片）→ 一律不算，宁缺勿塞。
  · 说话镜 `talking`：竞品 = `characterId && voiceover`（`:580`）；我们 = 人物镜 + 本镜有台词。
"""
from __future__ import annotations

#: 三档（顺序即界面顺序）
TIERS = ("auto", "constraints", "off")
DEFAULT_TIER = "auto"

#: 竞品六个镜型
SHOT_TYPES = ("hook", "pain_point", "product_reveal", "demo", "social_proof", "cta")

#: 品类（竞品 `ProductCategory`）
CATEGORIES = ("beauty", "food", "home", "fashion", "tech")

#: 品类材质保真（`motion-prompt.ts:150-178` 中文原文）
CATEGORY_CONSTRAINTS = {
    "beauty": "膏体与液体质地均匀顺滑，涂抹推开自然服帖不结块",
    "food": "食物色泽鲜亮自然、纹理清晰，形态完整不塌不散",
    "home": "部件开合顺畅到位，接缝与结构稳定不错位",
    "fashion": "面料垂坠自然、褶皱柔软真实，版型放松不僵硬",
    "tech": "金属与屏幕反光干净克制，接缝对齐，屏幕内容清晰稳定",
}

#: 动作 + 材质反应（`motion-prompt.ts:186-213` 中文原文）
PHYSICAL_ACTION_LEXICON = {
    "beauty": [
        "指腹蘸取膏体缓缓推开，质地在皮肤上自然延展服帖",
        "按压泵头挤出一滴，液体落在手背缓缓铺开",
        "拧开瓶盖，膏体表面平整光洁泛着柔光",
    ],
    "food": [
        "掰开的瞬间外层酥脆掉渣，断面组织分明",
        "热气从表面缓缓升起，酱汁沿边缘慢慢流下",
        "夹起时微微颤动，质地饱满有弹性",
    ],
    "home": [
        "开合部件顺滑归位，动作干净利落",
        "手掌按压表面，材质轻微回弹恢复原状",
        "水流冲过表面，水珠顺着材质纹理滑落",
    ],
    "fashion": [
        "转身时衣摆自然摆动后垂落回位",
        "手指捏起面料轻轻一放，褶皱缓缓回弹展开",
        "行走时面料随步伐轻微起伏",
    ],
    "tech": [
        "手指滑过屏幕，界面跟手流畅响应",
        "耳机放入充电仓，磁吸轻轻归位",
        "转动机身，金属边框上一道高光缓缓扫过",
    ],
}

#: 活背景池（`motion-prompt.ts:224-231` 中文原文）—— 只放一个元素，多了抢主体
LIVING_BG = [
    "背景里窗帘随气流轻轻晃动",
    "背景虚化处有人自然走过，不抢主体",
    "背景一盏灯的光斑有细微的明暗呼吸",
    "桌上一杯热饮冒着若有若无的热气",
    "窗外光线随云层缓慢变化",
    "背景绿植的叶片偶尔轻颤",
]

#: 发丝/衣料滞后（`motion-prompt.ts:234-237` 中文原文）
FABRIC_HAIR_LAG = "人物移动或转头时，头发与衣料带一点滞后的摆动再自然落回"

#: 镜型 → 情绪档（`emotion-acting.ts:26-34`）
SHOT_EMOTION = {
    "hook": "eager",
    "pain_point": "troubled",
    "product_reveal": "curious",
    "demo": "focused",
    "social_proof": "delighted",
    "cta": "confident",
}

#: 情绪过程池（`emotion-acting.ts:47-77` 中文原文）—— 触发 → 身体先反应 → 面部克制
EMOTION_PROCESS = {
    "eager": [
        "眼睛先亮起来，身体不自觉往前倾了一点",
        "呼吸略微加快，话比表情先到，嘴角才慢慢跟上",
    ],
    "troubled": [
        "眉心先皱了一下，视线落到别处，肩膀轻轻塌下来",
        "嘴唇抿住半秒，鼻腔里一声几乎听不见的叹气",
    ],
    "curious": [
        "头微微一偏，眼神先于身体凑近细看",
        "眉毛轻轻一挑，手上的动作放慢下来",
    ],
    "focused": [
        "视线锁在手上的动作，呼吸放缓，肩颈安定不动",
        "眼神专注跟着动作走，偶尔轻轻点一下头",
    ],
    "delighted": [
        "先是眼角放松下来，笑意才慢慢爬上嘴角",
        "肩膀松下来，整个人往后轻轻一靠",
    ],
    "confident": [
        "下巴微收，视线稳稳落在镜头上，不急不缓",
        "肩膀打开坐正，手掌向下轻轻一压",
    ],
}

#: 拿到物理交互短语的镜型（`motion-prompt.ts:216`）
PHYSICAL_ACTION_TYPES = ("demo", "product_reveal")

#: 五拍 → 竞品镜型。左列取自 `form_drama.md`「结构（五拍，不可省）」的表，
#: 右列取自 `motion-prompt.ts:107-120` 的默认运镜/动作语义（开场抓眼 / 痛点 / 商品揭示 /
#: 演示 / 行动号召）。
#: 🩸 **只映射语义真正对齐的三拍，不硬凑另外两拍**：
#:   · 冲突爆发 → 不映射。竞品 `hook` 的默认情绪是 `eager`（眼睛亮起来、身体前倾、嘴角跟上），
#:     而第一拍按 `form_drama.md` 定义是**吵架开场**，且它「第一句话就把矛盾炸出来」= 必有台词
#:     → 情绪层本来就轮不到（说话镜不加情绪过程）；硬映射只会在矛盾属性上打架。
#:   · 收束 → 不映射。竞品 `cta` 的 `confident`（下巴微收、稳看镜头）是**带货主播**的语气；
#:     我们的收束镜常落在**占下风的那个人**身上（「行吧。」），塞进去语义相反。
#:   · 这两拍本来也基本都有台词（talking → 不加情绪），所以不映射几乎不丢东西，
#:     但**杜绝了把兴奋/自信塞进挨骂镜头的可能**。
BEAT_TO_TYPE = {
    "矛盾升级": "pain_point",
    "商品登场": "product_reveal",
    "反转爽感": "demo",
}

#: 其它已在我们系统里出现的 purpose 词 → 镜型：
#:  · `hook｜` / `demo｜` / `cta｜` = 导入脚本自带的前缀（`drama_import.py:99`）
#:  · 钩子 / 演示 / 痛点 / 行动号召 = 六个镜型词的中文直译（分镜自由填写时最常见）
#:  · 话题片的「推进 / 收束」**故意不收**：推进是通用过渡镜、收束的语义见上面 BEAT_TO_TYPE 那段
PURPOSE_WORDS = {
    "hook": "hook",
    "pain_point": "pain_point",
    "product_reveal": "product_reveal",
    "demo": "demo",
    "social_proof": "social_proof",
    "cta": "cta",
    "钩子": "hook",
    "演示": "demo",
    "痛点": "pain_point",
    "行动号召": "cta",
}


def normalize_tier(tier: str | None) -> str:
    """认不出的档位一律回 `auto`（竞品 `motion-prompt.ts:398` 同口径）。"""
    t = str(tier or "").strip().lower()
    return t if t in TIERS else DEFAULT_TIER


def get_category(zh_name: str | None) -> str:
    """建项表单的中文类目 → 竞品品类 key；认不出返回空串（不回落 beauty）。

    换算只走 `drama_category_templates.resolve`（那边是**唯一换算处**）。
    """
    from app.services import drama_category_templates

    key = drama_category_templates.resolve(zh_name)
    return key if key in CATEGORY_CONSTRAINTS else ""


def shot_type(shot: dict) -> str:
    """本镜的竞品镜型；归不出来返回空串（**不按位置猜**）。

    优先认分镜自带 `type` 字段（以后若补上就直接生效），否则读 `purpose`。
    """
    if not isinstance(shot, dict):
        return ""
    raw = str(shot.get("type") or "").strip().lower()
    if raw in SHOT_TYPES:
        return raw
    purpose = str(shot.get("purpose") or "").strip()
    if not purpose:
        return ""
    # 导入脚本是 `hook｜钩子：用这句开场抓住人` 这种前缀
    head = purpose.split("｜", 1)[0].strip().lower()
    if head in SHOT_TYPES:
        return head
    # 五拍名 / 话题片词：全串里出现就算（purpose 常写成「冲突爆发（第一拍）」）
    for word, t in BEAT_TO_TYPE.items():
        if word in purpose:
            return t
    for word, t in PURPOSE_WORDS.items():
        if word in purpose:
            return t
    return ""


def person_on_camera(shot: dict, characters: list | None) -> bool:
    """角色名出现在本镜画面描述里 = 这一镜有真人出镜。

    依据：分镜格式硬性要求「每镜画面描述必须带该角色的外观锚」
    （`output_storyboard.md`「场景一致性」C7）。没有角色表 → 一律不算。
    """
    if not isinstance(shot, dict):
        return False
    names = []
    for c in (characters or []):
        name = str((c.get("name") if isinstance(c, dict) else c) or "").strip()
        if name:
            names.append(name)
    if not names:
        return False
    desc = str(shot.get("description") or "")
    return any(n in desc for n in names)


def is_talking(shot: dict, person: bool) -> bool:
    """人物镜 + 本镜有台词 = 说话镜（竞品 `characterId && voiceover`，`:580`）。"""
    return bool(person) and bool(str((shot or {}).get("dialogue") or "").strip())


def _pick(pool: list, seed: int):
    """确定性取一条（`motion-prompt.ts:255-258` 同一个取模契约）。"""
    n = len(pool)
    return pool[((int(seed) % n) + n) % n] if n else ""


def extra_lines(shot: dict, *, index: int = 0, tier: str = "auto",
                category: str = "", characters: list | None = None) -> list[str]:
    """本镜要追加的真实感句（按竞品拼装顺序）。

    `index` = 镜头在**本段**里的 0 基下标（竞品 `beatSeed = assets.findIndex(...)`）——
    同一条片子里相邻镜头不重复同一句，靠的就是它。
    `category` = 中文类目或竞品品类 key 都收（中文走 `drama_category_templates.resolve`）。
    """
    t = normalize_tier(tier)
    if t == "off" or not isinstance(shot, dict):
        return []
    cat = category if category in CATEGORY_CONSTRAINTS else get_category(category)
    stype = shot_type(shot)
    person = person_on_camera(shot, characters)
    talking = is_talking(shot, person)
    product = bool(shot.get("product"))
    seed = int(index)
    full = t == "auto"

    out: list[str] = []
    # ① 物理交互：只有演示/揭示镜拿到「动作 + 材质反应」，且要有已知品类
    if full and cat and stype in PHYSICAL_ACTION_TYPES:
        out.append(_pick(PHYSICAL_ACTION_LEXICON[cat], seed))
    # ② 情绪过程：非说话的人物镜 —— 说话镜已经有自己的表演指令
    if full and person and not talking:
        emo = SHOT_EMOTION.get(stype)
        if emo:
            out.append(_pick(EMOTION_PROCESS[emo], seed))
    # ③ 活背景：人物镜或演示镜（背景全静止一眼假）
    if full and (person or stype == "demo"):
        out.append(_pick(LIVING_BG, seed))
    # ④ 发丝/衣料惯性：只有人物镜
    if full and person:
        out.append(FABRIC_HAIR_LAG)
    # ⑤ 品类材质保真：商品镜都挂（constraints 档只挂这一条）
    if cat and product:
        out.append(CATEGORY_CONSTRAINTS[cat])
    return out
