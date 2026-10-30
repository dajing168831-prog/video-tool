"""换画面的结构化规格：把「换什么 / 保什么」拆成槽位，再编译成各家认的提示词。

为什么要这一层
--------------
一张参考图只回答"长什么样"，不回答"换成谁、在哪儿、穿什么、什么不能动"。
只给模型一段自由文本 + 一张图时，模型的行为完全由我们拼进去的固定句决定 ——
用户勾什么都改变不了结果。所以两侧都做成可选：

    换什么（change）  人物 / 产品 / 场景 / 服装造型 / 整体风格
    保什么（keep）    动作 / 运镜 / 剪辑节奏 / 背景 / 构图景别 / 光线

用户每勾一项，这里翻译成该通道认的一句提示词。两家语法不同，别串：

    火山     `@图片N` / `@视频N` / `@音频N`
             出处：Seedance 2.5 教程「提示词规则」——"使用 @图片1、@视频1、@音频1
             指代参考素材"；2.0 系列教程同样写"素材类型+序号"，序号 = content
             数组中同类素材的顺序，从 1 开始。
             ⚠️ 火山 2.0 明确"不支持使用 Asset ID 指代素材"——asset:// 只能当素材传，
             不能写进提示词当指代。

    MiniMax  `<Picture N>` / `<Video N>` / `<Subject N>` / `<Audio N>`
             出处：官方 skill `h3-prompt-writing`（github.com/MiniMax-AI/MiniMax-H3）
             的 Ref2VA 六段式。skill 明令：标号在所有段落里必须**完全一致**。
             ⚠️ 接口示例里还有"图1/视频1"的说法，那只是 API demo；做产品按 skill 走。

图片序号 = 实际传给模型的顺序，所以 SLOT_ORDER 必须和取素材的顺序一致，
否则用户写"换成图2里的产品"，模型拿到的是场景图。
"""
from __future__ import annotations

import re

# 人物槽：一个被换的人一槽，槽位顺序 = 盘点里勾选的先后顺序 = 提示词图号顺序。
# 槽位是"能装几个位置"，不是"允许换几个" —— 后者由型号判（`subject_gate`）：
#   2.0 / H3 = 4 人；2.5 = 稳定 8、硬上限 12（官方"可尝试 9-12 主体"）。
# 🩸 槽位开 16 个（比任何型号的上限都宽），是为了让"超了"能**明说**；
# 只开 12 个的话，用户传 13 个会被 normalize 悄悄截成 12，等于说一套做一套。
PERSON_SLOTS = ("person",) + tuple(f"person{i}" for i in range(2, 17))
MAX_PERSONS = len(PERSON_SLOTS)

# 服装按人：`wardrobe` = 换装名单里的第一个人，`wardrobe2` = 第二个人……
# 出处：Seedance 2.5 指南「视频中深色衣服的男子的服饰替换为 @图片2」——
# 官方就是**逐人点名 + 逐图绑定**，不是一句话全换。
WARDROBE_SLOTS = ("wardrobe",) + tuple(f"wardrobe{i}" for i in range(2, 17))
MAX_WARDROBE = len(WARDROBE_SLOTS)

# 参考图的固定顺序：提示词里的图号就是这条顺序里的第几号。
# 加槽位只能往后追加，不能插队 —— 插队会让所有历史提示词的编号错位。
# （图号只按"真的发出去的那些槽"编，空槽不进 idx，所以槽位表变长不影响历史提示词。）
# 风格参考图**追加在最后**：它是"整片观感"，和换谁/换什么没有先后关系，
# 排在末尾既不打扰历史图号，也不让用户上传的一张风格图顶掉产品/场景的图号。
SLOT_ORDER = PERSON_SLOTS + ("product", "scene") + WARDROBE_SLOTS + ("style_ref",)

_CN_DIGITS = "一二三四五六七八九十"


def _cn_num(n: int) -> str:
    """1→一，10→十，12→十二。只用到 20 以内。"""
    if 1 <= n <= 10:
        return _CN_DIGITS[n - 1]
    if 11 <= n <= 19:
        return "十" + _CN_DIGITS[n - 11]
    if n == 20:
        return "二十"
    return str(n)


SLOT_LABEL = {"person": "人物"}
SLOT_LABEL.update({f"person{i}": f"第{_cn_num(i)}个人"
                   for i in range(2, MAX_PERSONS + 1)})
SLOT_LABEL.update({"product": "产品", "scene": "场景", "wardrobe": "服装",
                   "style_ref": "风格参考"})
SLOT_LABEL.update({f"wardrobe{i}": f"服装（第{_cn_num(i)}个人）"
                   for i in range(2, MAX_WARDROBE + 1)})

# 整体风格：码值稳定，中文只用于编译提示词和前端展示
STYLES = {
    "live": "实拍",
    "anime": "动漫",
    "3d": "三维渲染",
    "film": "胶片质感",
    "sketch": "手绘插画",
}

# 🩸 2.0 专用：官方要求换风格时写**具体的风格锚定词**，不能只写媒介名。
#   出处：
#     · `seedance-20-guide.md:354`「在提示词中加入明确的风格约束词，
#       例如"2D日漫风格"、"3D国风漫画"」
#     · `sd2-pe:163`「风格锚定（动漫 / 非写实风格场景必挂）」
#   `anime` 直接用官方原词。`3d` 官方示例带"国风"，那是用户没选的审美，
#   不替用户加 —— 只补足"动画"这个媒介+风格限定（"三维渲染"是技术名）。
#   写实/胶片/手绘本来就是明确风格词，保持原样。
_STYLE_ANCHOR_20 = {
    "anime": "2D日漫风格",
    "3d": "3D动画风格",
    "sketch": "手绘插画风格",
}

# 保什么：键名稳定，中文进提示词
KEEP_LABELS = {
    # 🩸 2026-10-26 17:xx：原写「人物动作和**表情**」。官方 2.0 两处编辑示例
    # （`sd20-guide:941` / `sd2-pe:126`）逐字都是「**动作和运镜不变**」；「表情」在
    # 2.0 官方只出现在「描述镜头内容（主体动作与表情）」和「大头照要求无表情」，
    # **没有任何一处**要求"保持表情不变"。而换人恰恰要改脸 —— 把"表情"和动作
    # 绑在一起保住，等于给模型一个"这张脸别动"的指令。按「无官方出处 = 自造」
    # 撤回，只留官方那两个字。
    "motion": "人物动作",
    "camera": "运镜和机位",
    "rhythm": "剪辑节奏和时长",
    "background": "背景环境",
    "framing": "构图和景别",
    "lighting": "光线和色调",
}

# 声音模式
#   tts      全新配音，原片声音整条不要
#   mix      全新配音 + 原片的**非人声**部分（分离出来的 BGM/音效）
#   original 原音轨原样保留，不重新配音
# 🩸 `mix` 和 `tts` 一样属于「全新配音」—— 差别只在底音轨，不在口型。
AUDIO_MODES = ("tts", "mix", "original")

# 原片声音的后期处理（C4，2026-10-25）。**只走后期分离+混音，不进提示词**：
# 成片音轨由 `tracks.from_legacy` 用 `voice`(TTS) + `bg_from`(原片整轨/背景轨)
# 拼出来，模型产出的那一路音频不进合成 —— 写提示词也不会改到成片的声音。
#   bgm  keep    保留原片背景音乐（默认，不触发分离、不额外花钱）
#        drop    去掉背景音乐，**保留对白和环境音/音效**
#        replace 换成用户上传的音乐（循环/裁到片长）
#   sfx  keep    保留原片音效（默认）
#        add     再叠一段用户上传的音效
# `sd25-pe:635` 明确「只要求移除原背景音乐时，不需要虚构目标音频素材」——
# 所以 drop 不需要任何上传件，replace 才需要。
BGM_MODES = ("keep", "drop", "replace")
SFX_MODES = ("keep", "add")

def _res_caps(channel: str):
    """这条通道的清晰度档位与同义映射 —— 由该通道的代表适配器声明。

    🩸 2026-10-26 L3 第三轮：以前是两张写死的 `{"volc": …, "minimax": …}` 表。
    档位名是**大小写敏感**的（火山 480p / H3 480P），所以必须各回各家声明。
    """
    from app.services import models

    return models.adapter_for(channel=channel).caps


def known_resolutions() -> tuple[str, ...]:
    """注册表里所有家认的档位名合集（按注册顺序去重）。

    🩸 以前是写死的 `_RES_ALL`：加了第 4 家、它的档位名会**静默被丢掉**。
    """
    from app.services import models

    out: list[str] = []
    for ad in models.all_adapters():
        for r in ad.caps.resolutions:
            if r not in out:
                out.append(r)
    return tuple(out)


def defaults() -> dict:
    """全新一份规格。keep 全开 —— 默认行为是"只换我点名的，别的都别动"。"""
    return {
        "change": {
            "person": False,
            "product": False,
            "scene": False,
            "wardrobe": False,
            # 视觉盘点里选中的那些人（P1/P2…）；空 = 自动取主角。
            # `person_id` 是它的第一项，只为老客户端/老记录保留。
            "person_ids": [],
            "person_id": "",
            "person_desc": "",
            # 换装名单：第 i 个人 → `wardrobe` / `wardrobe{i+1}` 槽。
            # 空 + wardrobe=True = 老语义（一句话换全体，不指定谁）。
            "wardrobe_ids": [],
            # 谁在说话（H3 用）：只有名单里的人拿 (Sx) 号，不说话的**不给号**。
            # 出处：官方 skill base-en.txt:127。
            "speaker_ids": [],
            "product_desc": "",
            # 画面里**被换的是哪一件**（盘点给的外观，用户点选）。
            # 只写"产品"在有多件东西的画面里没有唯一解 —— 官方编辑句式要对象明确。
            "product_target": "",
            "product_target_en": "",
            "scene_desc": "",
            "wardrobe_desc": "",
            # 按人写的服装描述 `{人物 id: "米色风衣"}`（2026-10-27）。
            # 换装本来就有两条路：传一张服装图，或写一句换成什么（官方 `sd20-guide:39`
            # 的 `<新特征>`）。多人换装时一个字符串说不清谁换哪套，所以按人分开。
            # 前端 `diagnose.vue` 每个人一个输入框；空/缺键回落到 `wardrobe_desc`。
            "wardrobe_desc_by_id": {},
            "style": "",
            # 风格参考（A9）：图和视频**互斥**，同一时间只有一个来源。
            # 图走 `style_ref` 槽（进 SLOT_ORDER，占一个 @图片N）；
            # 视频不进图片顺序表 —— 它有自己的编号（@视频2 / <Video 2>）。
            "style_ref": False,
            "style_video": False,
        },
        "keep": {k: True for k in KEEP_LABELS},
        "audio": "tts",
        # 原片声音的后期处理（C4）：默认全保留 = 老行为，不触发分离
        "bgm": "keep",
        "sfx": "keep",
        # 尾帧锁定（B6）：重绘的镜头把结尾也锁回原片那一帧。
        # 只作用于静帧重绘的生成链 —— 编辑链发的是参考视频，与首尾帧互斥
        # （`volc-api:269`）。默认关 = 老行为。
        "lock_tail": False,
        # 🩸 无缝转场（B7）不进规格：2026-10-25 主人拍板只留在**延长链路**
        # （那一个接缝是真的），出片链路不接 —— 复刻要像原片，不该改原片剪辑点。
        # 🩸 2026-10-23 主人拍板「也不烧字幕」：`subtitle` 字段整个删除。
        "resolution": "auto",
        "extra": "",
    }


def normalize(raw: dict | None) -> dict:
    """把前端传来的任意形状收拾成 defaults() 的形状。

    不认识的值一律退回默认，不抛错 —— 前端多传一个字段不该让整单出片失败。
    """
    out = defaults()
    if not isinstance(raw, dict):
        return out

    change = raw.get("change") if isinstance(raw.get("change"), dict) else raw
    c = out["change"]
    for k in ("person", "product", "scene", "wardrobe"):
        if k in change:
            c[k] = bool(change[k])
        if f"{k}_desc" in change:
            c[f"{k}_desc"] = str(change[f"{k}_desc"] or "").strip()
    # 被换的是画面里哪一件产品（盘点给的外观描述，只当定位词）
    for k in ("product_target", "product_target_en"):
        if k in change:
            c[k] = str(change[k] or "").strip()[:80]
    # 没勾「换产品」就不该留着定位词，免得下次勾上时指到别的东西
    if not c["product"]:
        c["product_target"] = c["product_target_en"] = ""
    # 盘点里选中的人；只认 P1/P2 这种形状，别把任意字符串塞进去。
    # 多人 = `person_ids` 有多个；`person_id` 恒等于第一项（老客户端只传它）。
    ids: list[str] = []
    raw_ids = change.get("person_ids")
    if isinstance(raw_ids, (list, tuple)):
        for v in raw_ids:
            s = str(v or "").strip()
            if re.fullmatch(r"[A-Za-z]{0,3}\d{1,3}", s) and s not in ids:
                ids.append(s)
    if not ids:
        pid = str(change.get("person_id") or "").strip()
        if re.fullmatch(r"[A-Za-z]{0,3}\d{1,3}", pid):
            ids = [pid]
    # 没勾「换人物」就不该留着选人结果：否则取消勾选后重跑还在换人
    if not c["person"]:
        ids = []
    c["person_ids"] = ids[:MAX_PERSONS]
    c["person_id"] = c["person_ids"][0] if c["person_ids"] else ""
    # 每个被换的人各占一个槽位；勾了几个人就打开几个槽。
    # 🩸 从第二个人开始 —— "person" 是勾选框本身，不能被这里清掉
    # （只勾了「换人物」没指定是谁时，走"自动取主角"的老路）。
    for i, slot in enumerate(PERSON_SLOTS[1:], 1):
        c[slot] = i < len(c["person_ids"])

    def _id_list(val, cap: int) -> list[str]:
        """盘点 id 列表：只认 P1/P2 这种形状，去重、保序、截断。"""
        got: list[str] = []
        if isinstance(val, (list, tuple)):
            for v in val:
                s = str(v or "").strip()
                if re.fullmatch(r"[A-Za-z]{0,3}\d{1,3}", s) and s not in got:
                    got.append(s)
        return got[:cap]

    # ---- 换装名单（服装按人）----
    wid = _id_list(change.get("wardrobe_ids"), MAX_WARDROBE)
    if not c["wardrobe"]:
        wid = []
    c["wardrobe_ids"] = wid
    # 🩸 2026-10-27：按人写的服装描述。`normalize` 的 `{k}_desc` 循环只认四个
    # 固定键，这个字典不在里面 —— 不写这段就会被原样丢掉（实测：写了
    # `wardrobe_desc_by_id` 但提示词和闸门都看不见它）。
    _wdbi = change.get("wardrobe_desc_by_id")
    if isinstance(_wdbi, dict) and c["wardrobe"]:
        _got: dict[str, str] = {}
        for _k, _v in _wdbi.items():
            _ks = str(_k or "").strip()
            _vt = str(_v or "").strip()[:40]
            if _vt and re.fullmatch(r"[A-Za-z]{0,3}\d{1,3}", _ks):
                _got[_ks] = _vt
        c["wardrobe_desc_by_id"] = _got
    else:
        c["wardrobe_desc_by_id"] = {}
    for i, slot in enumerate(WARDROBE_SLOTS[1:], 1):
        c[slot] = i < len(wid)

    # ---- 谁在说话（说了才给 (Sx) 号；不说话的人不给号）----
    # 🩸 不要求说话人在 `person_ids` 里：只换衣服/道具时也可能要指定谁在说话，
    # 而且官方 base-en:127 明确写了"说话人不一定是已定义主体"时用稳定的声音描述 + (Sx)。
    c["speaker_ids"] = _id_list(change.get("speakers") or change.get("speaker_ids"),
                                MAX_PERSONS)

    # 🩸 2026-10-23 主人拍板：**画面内文字（广告语/字幕/气泡）整个能力不做**
    # —— 就算复刻的带货视频原片带字幕，也不复刻那些字幕（画面带字幕对 AI 天然不友好）。
    # 前端入口 2026-10-22 就已移除，这里把后端残留一并清掉。

    st = str(change.get("style") or "").strip()
    c["style"] = st if st in STYLES else ""
    # 风格参考（A9）：两个开关互斥 —— 图和视频同时为真时留视频。
    # 🩸 为什么互斥：风格只能有一个来源；两个来源打架时官方没有仲裁规则，
    # 模型会一半按图一半按片。上传接口那边已经互删，这里再兜一次
    # （老记录/手工调接口都可能带两个）。
    c["style_video"] = bool(change.get("style_video"))
    c["style_ref"] = bool(change.get("style_ref")) and not c["style_video"]

    keep = raw.get("keep")
    if isinstance(keep, dict):
        for k in KEEP_LABELS:
            if k in keep:
                out["keep"][k] = bool(keep[k])
    # 🩸 换场景和「保持背景」是互斥的两句话，不能同时发。
    # 同时发出去时提示词里会同时出现「the background of <Video 1> is replaced by
    # <Subject 3>」和「background environment … follow <Video 1>」—— 模型两头都听，
    # 成片背景每隔几秒就翻一次（2026-10-22 实测 e6bfd247：5.42s / 12.25s 两次
    # 硬切回原片背景，而原片本身一个切点都没有）。换场景时背景必须跟着换。
    if c["scene"]:
        out["keep"]["background"] = False

    au = str(raw.get("audio") or "").strip().lower()
    if au in AUDIO_MODES:
        out["audio"] = au

    # 原片声音的后期处理（C4）。只认白名单里的值，认不出就落回 keep ——
    # 前端多传一个字段不该让整单出片失败（与上面 audio 同一口径）。
    for key, modes in (("bgm", BGM_MODES), ("sfx", SFX_MODES)):
        val = str(raw.get(key) or "").strip().lower()
        if val in modes:
            out[key] = val

    # 尾帧锁定（B6）：前端可能传 true/"true"/1，一律布尔化
    if "lock_tail" in raw:
        out["lock_tail"] = bool(raw["lock_tail"])

    res = str(raw.get("resolution") or "").strip()
    if res in known_resolutions():
        out["resolution"] = res

    out["extra"] = str(raw.get("extra") or "").strip()
    return out


def subject_kind(spec: dict, *, person_asset: str = "") -> str:
    """决定通道走谁。只看人物槽位 —— 产品/场景图不涉及真人脸审核。

    asset  给了火山认可的肖像素材 ID
    file   传了一张本地人物图（多半是真人照）
    none   没换人，或者换的不是人
    """
    if (person_asset or "").strip():
        return "asset"
    if spec["change"].get("person"):
        return "file"
    return "none"


def has_change(spec: dict) -> bool:
    c = spec["change"]
    return bool(
        any(c.get(k) for k in ("person", "product", "scene", "wardrobe", "style",
                               "style_ref", "style_video"))
    )


def subject_gate(spec: dict | None, model: str = "") -> dict:
    """按型号的人的标准，量这次要换几个人。**不抛错**，由调用方决定拦还是提示。

    返回 `{count, stable, max, level, message, suggest_model}`：
        level = "ok"    没超稳定线
                "warn"  稳定线 < 人数 ≤ 硬上限 → 只提示（用户要自由创作度）
                "block" 超过硬上限 → 出片入口报错，并指向能接住的型号

    口径出处（`model_specs.SPECS`）：2.0 系列 = 4/4（官方"超过 4 人不稳"）；
    H3 = 4/4（与 2.0 对齐，官方没有人数口径）；2.5 = 8/12（官方"1-8 好，9-12 可尝试"）。
    """
    from app.services import model_specs

    c = ((spec or {}).get("change") or {})
    count = len([x for x in (c.get("person_ids") or []) if str(x).strip()]) \
        if c.get("person") else 0
    stable, cap = model_specs.subjects(model)
    out = {"count": count, "stable": stable, "max": cap,
           "level": "ok", "message": "", "suggest_model": ""}
    if count <= stable:
        return out
    if count <= cap:
        out["level"] = "warn"
        out["message"] = (f"这次要换 {count} 个人：{stable} 人以内最稳，"
                          f"{stable + 1}–{cap} 人稳定性下降，可能出现少人、多人或分身，"
                          f"不满意就得重跑")
        return out
    out["level"] = "block"
    # 🩸 2026-10-26 L3：以前这里写死「不是 2.5 就建议切到 doubao-seedance-2-5-260628」
    # —— 核心文件认识具体型号，加一家就得改这里。改成**问注册表**：
    # 谁的硬上限比你大，就建议切到谁；一家都没有（自己就是最宽的）就说分几条出。
    from app.services import models

    wider = sorted(
        (a for a in models.all_adapters()
         if model_specs.subjects(a.model_id)[1] > cap),
        key=lambda a: model_specs.subjects(a.model_id)[1], reverse=True)
    me = models.adapter_for(model=model)
    if wider:
        best = wider[0]
        b_stable, b_cap = model_specs.subjects(best.model_id)
        out["suggest_model"] = best.model_id
        out["message"] = (
            f"这个型号最多换 {cap} 个人。要换 {count} 个，"
            f"请把型号切到 {best.caps.raw.get('label') or best.model_id}"
            f"（{b_stable} 人以内稳，{b_stable + 1}–{b_cap} 人可尝试）")
    else:
        out["message"] = (
            f"{me.caps.raw.get('label') or me.model_id} 官方最多可尝试 {cap} 个主体；"
            f"要换 {count} 个，请分几条片子出")
    return out


def ref_order(spec: dict, *, person_asset: str = "") -> list[tuple[str, str]]:
    """按 SLOT_ORDER 列出这次真正要传给模型的参考素材。

    返回 [(槽位, "asset:<id>" | "file")] —— 调用侧据此决定是给 asset 还是读本地图。
    只列"用户勾了 + 素材存在"的槽位；勾了没素材的槽位不当参考图，只用文字描述。

    🩸 一个换的人只占一个槽位、只发一张图（2026-10-26，台账 D48）。
    以前这里有 `person_body` / `body_slots`，会追加一个 `<槽位>_body` 的伪槽位
    （派生出来的"全身照/大头照"）。三家官方原文复核后不成立、生产上也不再
    有第二张图 ⇒ 连参数一起删掉。依据见 `video_edit.ref_plan` 的说明。
    """
    out: list[tuple[str, str]] = []
    c = spec["change"]
    for slot in SLOT_ORDER:
        if not c.get(slot):
            continue
        if slot == "person" and (person_asset or "").strip():
            # 火山素材 ID 没有本地图
            out.append((slot, "asset:" + person_asset.strip()))
            continue
        out.append((slot, "file"))
    return out


def image_index(slots) -> dict[str, int]:
    """槽位 → 提示词里的图片序号（从 1 开始）。

    🩸 入参必须是**真正发出去的那些槽位**，不能是"用户勾了哪些"：
    勾了「换场景」却没给场景图时，素材会被跳过不发，编号一旦按勾选算，
    提示词就会写出一个不存在的 `@图片2`（模型拿不到那张图，只能瞎编）。
    """
    return {slot: i for i, slot in enumerate(slots, 1)}


# ---------------------------------------------------------------------------
# 编译


def sig_change(change: dict | None) -> dict:
    """签名里比"换什么"用的规范化摘要 —— 空的新字段一律不参与比较。

    🩸 每加一批字段就踩一次：`defaults()` 里新键即使空着也会进哈希，
    而历史出片记录里根本没有这些键 → 同一次输入被判成"输入变了"，
    面板从此永远显示 0 段可复用（白花钱重画）。空 = 没有这回事。
    """
    out = dict(change or {})
    for k in PERSON_SLOTS[1:] + WARDROBE_SLOTS[1:]:
        if not out.get(k):
            out.pop(k, None)
    # 只选了一个人 = 老表示法（person_id），列表本身没有额外信息
    if len(out.get("person_ids") or []) <= 1:
        out.pop("person_ids", None)
    for k in ("wardrobe_ids", "speaker_ids",
              "product_target", "product_target_en",
              # 风格参考（A9）同样是"新增字段"：老记录里没有这两个键，
              # 空着还进哈希就等于判"输入变了"，历史出片全部失配。
              "style_ref", "style_video",
              # 🩸 2026-10-27：逐人服装描述（`{人物id: "米色风衣"}`）也是同一类。
              #   它是**会改变成片**的字段（换哪套衣服全看它），不参与签名就会
              #   把"两人换了不同衣服"判成和上次一样 → 直接复用旧片、白改一场。
              #   P10 的 F1 就是拿老记录（没有这个键）比出来的。
              "wardrobe_desc_by_id"):
        if not out.get(k):
            out.pop(k, None)
    return out


def compile_prompt(channel: str, spec: dict, **kw) -> str:
    """把规格编译成提示词 —— 走**注册表**，核心不认识任何一家。

    🩸 2026-10-26（模型分离 L3）：以前这里是 `if channel == "volc": … else: …`，
    加一家就得改这个函数。现在按型号取适配器，各家实现在 `app/services/models/<家>/`。
    """
    from app.services import models

    return models.adapter_for(model=kw.get("model") or "", channel=channel) \
        .compile(spec, channel=channel, **kw)


def compile_context(spec: dict, *, person_asset: str = "",
                    source_person: dict | None = None,
                    source_people: list[dict] | None = None,
                    slots=None) -> tuple[dict, dict[str, int], list[dict]]:
    """编译前三家都要用的三样东西：改动面 / 图号索引 / 与槽位对齐的人物表。

    🩸 2026-10-26（模型分离 L3）：以前 `_compile_impl` 末尾还有
    `if channel == "volc": _volc(…) else: _minimax(…)` —— 加一家就得改这里。
    现在这一步只做**共性准备**，具体怎么编由各家适配器自己决定。
    """
    c = spec["change"]
    if slots is None:
        slots = [s for s, _ in ref_order(spec, person_asset=person_asset)]
    idx = image_index(slots)
    people = people_for_slots(c, source_person=source_person,
                              source_people=source_people)
    return c, idx, people


def people_for_slots(c: dict, *, source_person: dict | None = None,
                     source_people: list[dict] | None = None) -> list[dict]:
    """把盘点结果排成**与人物槽位一一对应**的列表：第 i 项 = 第 i 个槽位换的人。

    `source_people` 是调用方按 `person_ids` 顺序排好的（缺席的人传 present=False）；
    老调用方只有一个人（`source_person`），就当第一个槽位的人。
    空列表 = 这些槽位没有具体的人（按文字描述换）。
    """
    if source_people is not None:
        return list(source_people)
    if source_person:
        return [source_person]
    return []


def _present(p: dict | None) -> bool:
    """这个人在**这一刀**里出不出现。老调用方没有 present 字段 = 出现。"""
    return bool(p) and p.get("present", True) is not False


def _pic(channel: str, n: int) -> str:
    """中文句子里怎么指代第 n 张参考图 —— **问注册表，不自己分家**。

    🩸 2026-10-26 L3：以前是 `"@图片{n}" if channel == "volc" else "图{n}"`。
    每家在这两种书写场合的标号由各家自己声明（`Caps.pic_inline`），
    核心不知道有几家。
    """
    from app.services import models

    ad = models.adapter_for(channel=channel)
    return ad.caps.pic_inline.format(n) if ad.caps.pic_inline else ad.pic(n)


def _vid(channel: str) -> str:
    from app.services import models

    ad = models.adapter_for(channel=channel)
    return ad.caps.vid_inline or ad.vid()


def _inline(s: str) -> str:
    """把盘点给的描述收拾成"能嵌进句子中间"的短语。

    🩸 2026-10-22 实测（任务 a47631b0）：视觉盘点给的是整句
    「…holding a dark glass wine bottle.」/「…手持深色玻璃酒瓶。」，
    直接拼进模板就成了 `bottle. in <Video 1> is replaced by…`、`酒瓶。（这句…）`，
    英文句子断在中间、还出现 `..` / `。。`。所有内嵌位置统一走这里。
    """
    return (s or "").strip().rstrip("。．.！!？?；;，,、：:").strip()


# 🩸 群体描述 = 一群人，不是一个替换目标。盘点遇到人群/路人/背景人物时
# 会给这种描述（真实样本 `2ddd8959` 的 P3：「多名身着日常休闲服饰的普通民众」）。
# 词表与前端 `pages/clone/diagnose.vue` 的 `invPickable` 保持一致。
_GROUP_DESC = re.compile(
    r"多名|数名|几名|若干|一群|众人|人群|民众|路人|群众|背景人物|其他人")

# 人称中心词：指认短语必须以它收尾，否则写出来不是"一个人"（见 `_head_noun`）
_PERSON_HEAD = re.compile(
    r"(?:男性|女性|男子|女子|男孩|女孩|男生|女生|男人|女人|少年|少女|青年"
    r"|老人|老者|小孩|儿童|姑娘|小伙|主角|女主|男主|人|者)$")


def _head_noun(s: str) -> str:
    """盘点描述只取**主语短语**：第一个逗号/分号前的部分。

    🩸 2026-10-25：`_clauses` 的换人句要把"那个人"当宾语（「把<X>替换为@图片N」），
    而盘点描述是一条长句，以**衣服**收尾：
        「体型偏胖的男子，黑色头发束成发髻，佩戴浅色玉质发冠，身着…，内搭白色中衣」
    整段塞进宾语位就变成「…内搭白色中衣替换为@图片1中的人物」—— 读起来是
    把中衣换成一个人（2026-10-24 20:49 那条实测的原句就是"把手枪换成一个人"）。
    取到第一个逗号为止，剩下的正好是带中心词的短语（「体型偏胖的**男子**」）。
    没有逗号就原样返回，不硬截。
    """
    # 🩸 2026-10-26（D36 边界探测）：盘点描述偶尔带**换行**，原样拼进提示词
    # 会让它出现 ``\n``，直接被尺子 R03 判成"分块标题"（单段式被破坏）。
    # 这是**数据清洗**，不是规则变更 —— 换行进任何一家的提示词都是格式破坏，
    # 所以放在这里统一处理，不按型号分叉。
    raw = re.sub(r"[\r\n\t]+", " ", (s or "")).strip()
    s = raw
    for sep in ("，", "；", ";", ","):
        i = s.find(sep)
        if i > 0:
            s = s[:i]
    s = s.strip()
    # 🩸 2026-10-26（主人：「刚跑了一条还是一模一样」）：第一段**必须是人称名词
    # 收尾**才配当指认短语。现场 `494b1c28` 16:23 的盘点写的是
    #   「留短黑发，佩戴黑框眼镜，身穿藏蓝色…的男性」
    # 第一段是**发型**，于是拼出「将@视频1中画面中央的留短黑发定义为<主体2>」——
    # 宾语不是人；同片另外两人也留短黑发，模型没有唯一的替换对象
    # （成片只换了衣服、脸一帧没动：主角 vs 参考 0.17–0.34，vs 原片 0.69–0.85）。
    # 官方 `:95` 要的是「2–3 个清晰稳定的静态特征…确保唯一可识别性」，
    # 而发型恰恰是**要被替换掉的妆造**（见下面 `:_583` 那条禁令）。
    # 第一段不是人 ⇒ 退到整段最后一个「的X」，X 是短的人称名词才用（「…的男性」→「男性」）。
    # 还取不到就当空处理，由调用方退回只用方位，**绝不硬塞发型**。
    if not _PERSON_HEAD.search(s):
        m = re.search(r"的([^，；,;的]{1,4})$", raw)
        s = m.group(1) if (m and _PERSON_HEAD.search(m.group(1))) else ""
    # 描述只有标点（「，，，。。。」）时取出来的"主语短语"不是名词，
    # 写进句子就是「将@视频1中画面左侧的，，，。。。定义为…」。当空处理，
    # 由调用方退回只用方位（`sd20-guide:95` 要的是"可识别的静态特征"，标点不是）。
    if not re.search(r"[0-9A-Za-z一-鿿]", s):
        return ""
    return s


# 服装类分句的开头词（盘点描述里就这么写）。`cloth=False` 时丢掉这些分句 ——
# **只在"指认被替换的那个人"时用**，因为把衣服写进宾语，模型会照着改衣服
# （2026-10-24 三版实测 + 2026-10-26 18:21 那条，都是衣服换了、脸没换）。
_CLOTH_HEAD = ("身穿", "身着", "穿", "内搭", "搭配", "腰系", "腰挂", "脚穿",
               "披着", "围着", "颈围", "头戴")


def _feat_phrase(desc: str, cloth: bool = True, sd20: bool = False) -> str:
    """盘点描述 → 官方 `sd20-guide:95` 的「2–3 个静态特征 + 类别」短语。

    🩸 2026-10-26 18:xx（主人：「他指出了你后面想要的东西了吗？能指出不算我们编」）：
    以前只取**前两个分句**，把**服饰**整段丢掉 —— 真实盘点 `494b1c28`：
      盘点：「留短黑发，佩戴黑框眼镜，身穿藏蓝色带白色字母印花、红格纹连帽内衬的
              外套，内搭黑色上衣的男性」
      旧写法：「留短黑发、佩戴黑框眼镜的男性」（服饰全丢）
      另一个：「留短寸发型，身穿黑色长袖上衣的男性」→ 旧写法「留短寸发型的男性」
    `sd20-guide:95` 的核心特征清单第一项就是**服饰**，`:164` 强方位的例子也是
    「左侧角色**穿灰蓝色作训服**」。盘点已经给了，丢掉等于自己少写一半。
    现在把**末段里"的"之前的服饰**也算进来，总数封顶 3（官方「2–3 个」）。

    例：「留短寸发型，身穿黑色长袖上衣的男性」→「留短寸发型、身穿黑色长袖上衣的男性」
    第一段本身就以人称名词收尾时**原样返回**（「体型偏胖的男子」—— 已验证的写法，
    不为统一去动它）。取不到类别就返回空串，由调用方退回方位。
    """
    raw = re.sub(r"[\r\n\t]+", " ", (desc or "")).strip().rstrip("。．.")
    if not raw:
        return ""
    # 🩸 2026-10-27：**群体描述不是一个人**，不能当替换目标具名指认。
    # 真实盘点 `2ddd8959`：P3「多名身着日常休闲服饰的普通民众，部分手持手机拍摄」，
    # `face_visible=false`、`position=unknown`。加了通用中心词兜底后这句会变成
    # 「多名身着日常休闲服饰的普通民众的人物」—— 病句，且模型没法把"一群人"
    # 换成一张脸（官方 `:107` 要求指代唯一）。这里返回空，由调用方跳过。
    # 正则与前端 `diagnose.vue` 的 `invPickable` 同一套词表。
    # 🩸 **只在 `sd20=True` 时生效**（2026-10-27 主人：「现在让你调试 2.0 模型，
    # 其他模型还没轮到」）：2.5 走 `_clauses(edit_task=True)` + 自己的模板，
    # H3 走 `_landmark_phrase`，都不该被这一轮的 2.0 改动带着走。
    if sd20 and _GROUP_DESC.search(raw):
        return ""
    parts = [p.strip() for p in re.split(r"[，,；;]", raw) if p.strip()]
    if not parts:
        return ""
    if _PERSON_HEAD.search(parts[0]):
        # 🩸 2026-10-27：整句全用顿号、直呼「…的男性」时 `parts[0]` 就是**全串**，
        # 这里原样返回等于绕过下面 official `sd20-guide:91-95` 的 2–3 封顶
        # （实测 5 个特征全发）。只在不超 3 个时才原样放行。
        _segs = [x.strip() for x in re.split(r"、", parts[0]) if x.strip()]
        if len(_segs) <= 2:
            return parts[0]
        parts = _segs
    m = re.search(r"的([^，；,;的]{1,4})$", parts[-1])
    head = m.group(1) if (m and _PERSON_HEAD.search(m.group(1))) else ""
    # 末段扣掉「的X」之后剩下的那半句也是特征（通常是服饰），别整段扔了。
    # 🩸 2026-10-30：末段**没有人称中心词**时以前整段被扔掉 ——
    #   `['橙色连帽拉链外套', '左胸带有白色品牌标识']` 只取到第一段，
    #   拼出「橙色连帽拉链外套的人物」，官方 `:95` 要的「2–3 个静态特征」只剩 1 个。
    #   现在没有中心词时末段整段算一个特征（它有中心词时仍然是「的」前那半句）。
    if head and m:
        tail = parts[-1][:m.start()].strip()
    elif not head:
        tail = parts[-1]
    else:
        tail = ""
    feats = parts[:-1] + ([tail] if tail else [])
    if not cloth:
        # 只留**人和身上的配饰**（发型/眼镜/胡须…），服装分句整段丢掉
        _keep = [x for x in feats if not x.startswith(_CLOTH_HEAD)]
        feats = _keep or feats[:1]
    # 🩸 2026-10-27：封顶原本只数**逗号分句**，可盘点常把服饰写成
    # 「身穿藏蓝色带白色字母印花、红格纹连帽内衬的外套」—— 分句内部还有顿号，
    # 于是 4–6 个特征原样漏出（实测 `留短黑发、戴眼镜、穿蓝外套、绿长裤、白球鞋的男性`
    # 5 个全发），违反官方 `sd20-guide:91-95`「2–3 个清晰、稳定的静态特征」。
    # 先把顿号拆开再封顶，截的才是**特征数**。
    _flat: list[str] = []
    for _f in feats:
        _flat.extend([x.strip() for x in re.split(r"、", _f) if x.strip()])
    # 🩸 2026-10-27 主人拍板：取 **2 个**（不是官方上限 3）。
    # 官方 `sd20-guide:91-95` 写的是「2–3 个」，那是**上限口径**；真机数据是
    # 1 个特征 3/3 成功、3 个特征 0/2 失败（`OPEN-DEFECTS` §13.13），
    # 所以产品线收到 2 —— 这条是**我们比官方更严**，别把它当成官方规则。
    feats = _flat[:2]
    # 🩸 2026-10-27（人工审读真实盘点抓到的）：以前 `head` 取不到就**整段返回空**，
    # 上游 `_sd20_orig_feat` 于是当"这个人指认不出来"，整条替换句跳过 ——
    # **图白传**。真实数据 `7536fdb5`（6 人）：
    #   P1「穿橙色连帽拉链外套，左胸带有白色标识，短发，…」
    #   P6「穿黑色短袖上衣，寸头发型，耳部佩戴耳钉」
    #   两人 pos 都是 center（方位撞车 → 只能退回特征），两句都**没有**
    #   「的男性/的女子」这类人称中心词 ⇒ 双双返回空 ⇒ 6 张图只换了 4 个人，
    #   @图片1 一次没出现，用户看不到任何提示。
    # 特征本身有唯一性（橙色外套在一群黑衣人里只此一件），没理由因为缺个中心词丢掉。
    # ⇒ 缺人称词时补通用中心词「人物」：句子仍完整，指向仍唯一。
    # 注意和 2026-10-27 修掉的另一种「裸『人物』」区别：那是指**没有定义**、
    # 在一堆 `<主体N>` 里指谁都不知道的宾语；这里是**带 2 个特征**的定义短语。
    if not feats:
        return ""
    # 缺人称词时补「人物」同样**只给 2.0**（见上方 `sd20` 说明）。
    if not head and not sd20:
        return ""
    return "、".join(feats) + "的" + (head or "人物")


def _split_feats(d: str) -> tuple[list[str], str]:
    """盘点描述 → (特征分句列表, 人称中心词)。与 `_feat_phrase` 同一把尺。"""
    raw = re.sub(r"[\r\n\t]+", " ", (d or "")).strip().rstrip("。．.")
    parts = [x.strip() for x in re.split(r"[，,；;]", raw) if x.strip()]
    if not parts:
        return [], ""
    m = re.search(r"的([^，；,;的]{1,4})$", parts[-1])
    head = m.group(1) if (m and _PERSON_HEAD.search(m.group(1))) else ""
    feats = parts[:-1] + ([parts[-1][:m.start()].strip()] if (head and m) else [])
    return [x for x in feats if x], head


# 「标志性」= **二元、可数、有对比**的外观 —— 官方 `:95` 说的"稳定静态特征"里
# 真正能拿来认人的那一类。
# 🩸 2026-10-26 22:xx（主人：「应该是带有标志性的。如果全部是黑人而且都长得一样呢？
# 模型知道谁胖点瘦点？」）：体型 / 身高 / 年龄 / 肤色 是**相对判断**，视频模型没有
# 可靠度量，写进定义句等于没写。只有下面这些能当指认依据。
_LANDMARK_RE = re.compile(
    r"眼镜|墨镜|护目镜|帽|头盔|口罩|面罩|耳钉|耳环|耳坠|项链|吊坠|手链|手镯|戒指|"
    r"手表|围巾|领带|领结|纹身|刺青|胡须|胡子|络腮胡|寸头|卷发|马尾|辫子|发髻|"
    r"刘海|伤疤|疤痕|痣|背包|挎包|手杖|拐杖|"
    r"(白|金|黄|红|蓝|绿|紫|粉|银)发|"
    r"^(身穿|身着|穿着|穿|上身)?\s*(红|橙|黄|绿|蓝|紫|粉)")








def _who(desc_by_id: dict | None, pid: str, lang: str = "zh") -> str:
    """盘点 id → 这个人的外观描述（火山用中文、H3 用英文）。
    `desc_by_id` 的形状 = `{id: {"zh": ..., "en": ...}}`。"""
    d = (desc_by_id or {}).get(str(pid or "")) or {}
    return (d.get(lang) or "").strip() if isinstance(d, dict) else ""


# 🩸 多人换人的消歧手段，两家官方都是「方位 + 外观」：
#   · 火山 sd2-pe:72 把"多人未指明谁在左/右"列为**病灶**，
#     :153 给的写法是 `@图片2 中的女生位于画面左侧`；
#   · MiniMax ref-en:246「At the first clear appearance … describe its …
#     position in the frame」，:330 示例 `From the left, <Subject 4>, the
#     young man with short wavy brown hair…`。
# 方位来自盘点（`vision_plan` 的 `position` 字段），盘点没给就退回原写法。
# 九宫格。左右并排是 left/center/right，**上下分屏是 top/bottom** —— 只做左右的话，
# 上下分屏的两个人会一起判成 center（2026-10-23 真实盘点 a47631b0 实测）。
_POS_ZH = {
    "top-left": "画面左上", "top": "画面上方", "top-right": "画面右上",
    "left": "画面左侧", "center": "画面中央", "right": "画面右侧",
    "bottom-left": "画面左下", "bottom": "画面下方", "bottom-right": "画面右下",
}
_POS_EN = {
    "top-left": "in the upper left", "top": "in the upper part",
    "top-right": "in the upper right",
    "left": "on the left", "center": "in the center", "right": "on the right",
    "bottom-left": "in the lower left", "bottom": "in the lower part",
    "bottom-right": "in the lower right",
}


def _pos_zh(p: dict | None) -> str:
    return _POS_ZH.get(str((p or {}).get("position") or ""), "")


def _uniq_pos(p: dict | None, pool: list[dict] | None) -> str:
    """这个人的方位（中文），**只有画面里该方位确实只有一个人时**才给。

    🩸 2026-10-26（D28）：2.5 用方位指认人（官方 `seedance-25-guide.md:193`
    「把视频 1 中**右侧**的亚洲女生改为图片 1 中的黑人女生」），前提是该方位
    只有一个人。两个人都在 `center` 时写「替换画面中央人物」谁也没指认
    —— 与 2.0 的 D24 同一个病，2.5 这边以前连撞车都不判。
    `pool` 必须是**整个画面**（生产里 `source_people` 只含勾选的人）。
    """
    raw = str((p or {}).get("position") or "")
    if not raw:
        return ""
    n = sum(1 for x in (pool or []) if x and _present(x)
            and str(x.get("position") or "") == raw)
    return _pos_zh(p) if n <= 1 else ""


def _who_label(p: dict | None, pool: list[dict] | None, desc: str) -> str:
    """多人时这个人在**正文里**该叫什么 —— 与 `_clauses` 换人句的宾语同一个词。

    🩸 2026-10-26（主人追问「你自己造模型能懂吗」）：2.5 官方给的**双人换装**
    编辑示例是「视频中**深色衣服的男子**的服饰替换为 @图片 2，视频中
    **浅色衣服的男子**替换为 @图片 3」（`sd25-guide:1203-1209`）—— 用画面能看见的
    外观指认，**不用字母**。以前职责段写「目标人物A/B」，可 A 在全篇没有任何
    一句定义过，模型得跨段两跳才知道 A 是谁。

    取词顺序与 `_clauses` 换人句逐条对齐（方位唯一 → 外观主语短语 → 「人物」），
    只让职责段抄同一个词，不改 `_clauses` 那一层。
    """
    raw = str((p or {}).get("position") or "")
    if raw:
        n = sum(1 for x in (pool or []) if x and _present(x)
                and str(x.get("position") or "") == raw)
        if n <= 1:
            return f"{_pos_zh(p)}的人物"
    h = _head_noun(desc or "")
    return h or "人物"


def _pos_en(p: dict | None) -> str:
    return _POS_EN.get(str((p or {}).get("position") or ""), "")


def _uniq_pos_en(p: dict | None, pool: list[dict] | None) -> str:
    """英文方位，**只有画面里该方位确实只有一个人时**才给（`_uniq_pos` 的英文版）。

    🩸 2026-10-26（D31）：H3 以前不管方位撞不撞都给 `the person in the center`，
    两个人同在 `center` 时定义行逐字相同 —— 官方 `ref-en:37` 要求每一行说清
    「这个标号指什么、要跟随的主要特征」，`:48` 也说同一素材可以出多个 subject，
    于是"两个 subject 写成同一句"等于谁也没指认。`pool` 必须是**整个画面**。
    """
    raw = str((p or {}).get("position") or "")
    if not raw:
        return ""
    n = sum(1 for x in (pool or []) if x and _present(x)
            and str(x.get("position") or "") == raw)
    return _pos_en(p) if n <= 1 else ""


def _multi(people: list[dict] | None, desc_by_id: dict | None) -> bool:
    """画面里是不是多于一个人 —— 只有多人时才需要方位/外观当定位词。

    🩸 两处编译器（`_clauses` 给火山、`_minimax` 给 H3）必须用**同一把尺**：
    以前只有 `_clauses` 算这个，H3 那边靠 `src_en` 是否为空隐式判断，
    两边口径不同就会出现"火山写了方位、H3 没写"。
    """
    return (len(desc_by_id or {}) > 1
            or len([p for p in (people or []) if p and _present(p)]) > 1)






def _clauses(channel: str, c: dict, idx: dict[str, int], *,
             dialect,
             people: list[dict] | None = None,
             frame_people: list[dict] | None = None,
             desc_by_id: dict[str, str] | None = None,
             keep: dict | None = None,
             style_anchor: bool = False, style_video: bool = False,
             orig_tags: dict | None = None, ref_tag: dict | str | None = None,
             scope_all: bool = False) -> list[str]:
    """逐条把"换什么"翻成一句。没素材的槽位退化成纯文字描述。

    `people` 与人物槽位一一对应（第 i 人 → 第 i 个槽位）。每人一句、各用各的图号：
    多人画面里「把人物换掉」没有唯一解，必须逐个点名 + 逐个绑图。

    `orig_tags`（2.0 多人专属）：**盘点 id** → `<主体N>`，原片侧那个人的标签。
    有它时换人句的宾语就是标签（官方 `:119`「后续描述涉及到…持续使用同一
    标签」），方位/主语短语退回定义句里当指认特征。
    🩸 2.5 **只在两个目标的称谓都撞车时**才传（`_volc_25` 的 `_orig_tags`），
    值仍是普通名词（`目标人物A` 或 `体型偏胖的男子（目标人物A）`）——
    2.5 不用尖括号（官方 `:880`「同一符号承担两种职责」），所以这里不写 `<…>`。
    """
    out: list[str] = []
    v = _vid(channel)
    people = people or []

    # 🩸 `orig_tags` 两家**键不一样**：2.0 按盘点 id（`_sd20_person_tags`，
    # 因为没被换的那位也可能说话，得查得到），2.5 按目标序号（`_volc_25`）。
    # 先按 id 查、再按序号查，两套都不会漏。
    def _tag_of(i: int, per: dict | None) -> str:
        pid = str((per or {}).get("id") or "")
        t = (orig_tags or {})
        return t.get(pid) or t.get(i, "")  # type: ignore[arg-type]

    # 图片侧标签（官方 12 条示例里替换句的宾语）：按目标槽位序号取。
    # 老调用方传的是单个字符串，兼容。
    def _rtag_of(i: int) -> str:
        if isinstance(ref_tag, dict):
            return str(ref_tag.get(i) or "")
        return ref_tag or ""

    # 🩸 **原对象的指代方式两家里不一样**，不能共用一套：
    #   · 火山 2.0 `sd2-pe:126`「严格编辑 @视频1，**将其中的**香水替换为
    #     @图片1 中的面霜」→ 句子里不再重复 @视频1；
    #   · 火山 2.5 `sd25-pe:600` 示例「**只把**经过长椅前方的红色自行车和骑行者
    #     替换为 @图片1 中的深灰色电动巡逻车」→ 句子里要带原对象所在的视频。
    # 以前两边都写「把@视频1中…」，2.0 那句既不是官方句式、又多重复一次 @视频1。
    def _subj(obj: str) -> str:
        # 2.5 官方模板 `编辑@视频1，只把<原对象或区域>替换为<目标内容>`
        # （`sd25-pe:561`），示例 `只把经过长椅前方的红色自行车和骑行者替换为…`
        # （`:584`）—— **<原对象>里不带 @视频1**，@视频1 只在句首出现一次。
        # 2.0 官方是 `将其中的<原特征>替换为…`（`sd2-pe:126`）。
        # 🩸 以前 2.5 也写「把@视频1中…」，官方全文两处"只把"都没有这个前缀。
        return dialect.subj(obj)
    # 画面里是否**多于一个人**：只有多人时才需要"原片人物描述"当定位词。
    # 单人画面里那句描述反而会带偏 —— 它写的是**衣服**，模型会照着去换装。
    # 🩸 要按**盘点里的总人数**判，不能只看这次选了几个人：一条片子里有两个人、
    # 用户只换其中一个时，仍然得靠描述认出换的是哪一位，否则会换错人。
    # 🩸 有 `frame_people`（整个画面）时以它为准 —— 生产里 `people` 只含勾选的人。
    multi = _multi(frame_people or people, desc_by_id)

    # 方位出现次数：只有**唯一**的方位才能拿来指认是谁（见下面 `pos` 那段）。
    # 🩸 分母必须是**整个画面**（`frame_people`），不是这次勾选的人。
    # 生产形状里 `people` 只含被选中的人（`video_edit._span_people`），
    # 只换两人中的一个时 `people` 长度为 1 —— 拿它数方位，每个方位天然"唯一"，
    # 于是照写「画面中央的人物」，而画面里两个人都在 center，谁也没指认。
    # 2026-10-25 `probe_prod_shape.py` 实测：只换 P1 时拼出来的正是这句。
    present_pos: dict[str, int] = {}
    for _p in (frame_people or people or []):
        if _p and _present(_p):
            _k = str(_p.get("position") or "")
            if _k:
                present_pos[_k] = present_pos.get(_k, 0) + 1

    if c.get("person"):
        wrote = 0
        for i, slot in enumerate(PERSON_SLOTS):
            if slot not in idx:
                continue
            per = people[i] if i < len(people) else None
            # 这一刀里没出现的人不写换人句：写了模型会往画面里硬塞一张脸
            if per is not None and not _present(per):
                continue
            # 盘点给出的"原片里那个人"优先于用户手写的补充描述：
            # 前者是模型自己看画面得出的，和 @视频1 里的画面一一对应
            src = _inline((per or {}).get("desc_zh") or "")
            # 手写描述是老字段，多人时没有唯一解，只对第一个人有意义
            desc = (c.get("person_desc") or "") if i == 0 else ""
            pic = _pic(channel, idx[slot])
            # 🩸 火山编辑任务的 `<新特征>` 位**只写图号**，不写人物外观特征。
            # 两家官方编辑示例都没有特征：
            #   · 2.0 sd2-pe:126「将其中的香水替换为 @图片1 中的面霜」
            #   · 2.5 seedance-25-guide.md:88「把 @video1 的人物修改为 @image1」
            # 🩸 2026-10-26 18:xx：参考图侧**不再发标签**（`_sd20_person_tags`
            # 只定义原片侧的人）。原片侧那个 `<主体N>` 走 `orig_tags`。
            # 🩸 2026-10-26：替换宾语**一律用图内对象** `@图片N中的人物`，不再用
            # `<主体N>`。两家官方编辑示例的宾语都是图内对象：
            #   · `sd2-pe:126`「将其中的香水替换为 **@图片1 中的面霜**」
            #   · `sd20-guide:941`「将视频1中的香水替换成 **图片1中的面霜**」
            # `<主体N>`（`:105`）是**定义/绑定**用的（`:109` 要求多主体分别定义并用
            # 标签区分），不是给替换句省图号的。替换句里少了图号，模型要跨两句
            # 回查"<主体1>是谁"，而句末还挂着一句「妆造参考@图片1」——
            # 结果是**衣服照着图换了、脸留在原片演员身上**（2026-10-26 15:48 实测）。
            # 对照：单人路径（宾语一直是 `@图片1中的人物`）在同素材上 p90 0.615 /
            # 达标帧 0.74，是 1 图条件下最好的那条。
            # 🩸 替换宾语**一律**是图内对象 `@图片N中的人物`（官方 `:126`/`:17`
            # 的「图号 + 名词隔断」）。原片侧那个人的 `<主体N>` 是**被替换的对象**，
            # 放在 `将其中的…` 那位（见下面 `_otag`），不放在 `替换为…` 这侧。
            # 🩸 2026-10-26 19:xx：参考图里的人**已经有了定义**（`ref_tag`，
            # `_sd20_person_tags` 用盘点描述发出来的），替换宾语就用标签 ——
            # 官方 `:119`「后续描述涉及到…持续使用同一标签」、`:107`「使用标签
            # 区分…避免指代混乱」。没有定义时仍退回图内对象 `:126` 的写法。
            _rtag = _rtag_of(i)
            tgt = _rtag or f"{pic}中的人物"
            # 方位只在多人时写：单人画面里不需要区分，写错了反而把人钉死在某一侧。
            # 🩸 2026-10-25：**方位必须互不相同才能当识别符**。
            # 现场：`6c51196b/3949eb3f`（14.187s，古装片，男+女两个人都被盘点成
            # `position: "center"`）拼出来是「将其中的**画面中央的人物**替换为
            # @图片1中的人物」—— 画面里有两个人，这句谁也没指认。
            # 结果：整片一帧没换（六段逐段身份核对 p90 0.09–0.19，全 not_swapped；
            # 原片↔成片 SSIM 0.93–0.955，模型确实重画了，只是照原样画）。
            # 官方要的是**能指认**（`sd2-pe:72` 把"多人未指明谁在左/右"列为病灶，
            # `:153` 的写法是「@图片2 中的女生位于画面左侧」）—— 两个人同标 center
            # 时这句话不构成指认，等于没写。
            pos = ""
            if multi:
                _raw_pos = str((per or {}).get("position") or "")
                if _raw_pos and (present_pos.get(_raw_pos) or 0) <= 1:
                    pos = _pos_zh(per)
            # 🩸 **有方位就只写方位，不追原片外观**（2026-10-24 改）。
            # 原写法是 `{方位}{外观描述}`，拼出来是「画面中央留黑色长直发，
            # 身着浅黄绿色连衣裙，双手各持一把黑色手枪」—— 这段描述写的是
            # **衣服和道具**，模型照着它去改那两样，人脸原封不动：
            # 同一条片子的 2.0 三版（`732c9510` / `c97b934c` / `21053fc9`）
            # 全是这个提示词，出片与原片 SSIM 0.90、女主一帧没换。
            # 同一坑在 2026-10-22 单人那条已经踩过一次（只换衣服不换脸）。
            # 方位本身就能唯一指认（`_POS_ZH` 九个方位），不需要再补外观。
            # 🩸 宾语**永远以「人物」结尾**，不能把外观直接当宾语：
            #   2026-10-24 20:49 那版拼出来是
            #   「…身着浅黄绿色连衣裙，双手各持一把黑色手枪**替换为**@图片1中的人物」
            #   —— 这句话读起来是"把手枪换成一个人"，模型当然不换脸。
            # 🩸 但也**不把原片外观写进来**（`probe_sd20_spec` 的「双人换人：不写
            #   原片外观」这条判据，来自 2026-10-24 三版 2.0 的实测：写了外观那三版
            #   全都没换脸）。有方位就只用方位点名。
            # 🩸 2026-10-25：在场 ≥2 人时宾语改用**已定义过的标签**。官方 `:119`
            # 「后续描述涉及到…持续使用同一标签」/`:110`「后续描述中需持续使用
            # 对应标签」。以前同一句里三种指代轮着来（方位 / 主语短语 / 「人物」），
            # 模型分不清是不是同一个人。有标签就只用标签，没有才退回旧写法。
            _otag = _tag_of(i, per)
            # 🩸 2026-10-27：宾语指认走三档（与定义句同一把尺 `_sd20_orig_feat`）：
            # 方位在画面里唯一 → 「画面中央的人物」（官方 `:153`）；
            # 方位撞车/取不到 → 才用特征短语（官方 `:95`）。
            # 单一人的画面在上面 `multi` 就拦掉了，永远落到裸「人物」。
            # 以前两天里正反各翻过一次（只方位 / 只特征），原因与定案见
            # `_sd20_orig_feat` 的注释：方位是**盘点看画面给的**，不是我们猜的中心。
            # 🩸 2026-10-26 21:xx：指认宾语里的**服装分句去掉**（`cloth=False`）。
            # 「身穿藏蓝色带白色字母印花、红格纹连帽内衬的外套的男性」这种写法
            # 会让模型把注意力放在"改衣服"上 —— 2026-10-24 三版 + 2026-10-26 18:21
            # 两次全是**衣服换了、脸没换**。官方 `:153` 的指认手段是方位，
            # `:95` 的特征里"发型/外观"仍在，只是不把服装写进宾语。
            _feat_obj = (dialect.orig_feat(people, i, pool=frame_people or people,
                                           cloth=False)
                         if (multi and not _otag and src) else "")
            if _otag:
                obj = _otag
            elif _feat_obj:
                # `_feat_obj` 本身已经带了唯一方位（`_sd20_orig_feat` 里拼的
                # 「画面中央的留短黑发、佩戴黑框眼镜的男性」，官方 `:153` + `:95`）
                obj = _feat_obj
            elif pos:
                obj = f"{pos}的人物"
            elif src and multi and _head_noun(src):
                # 没方位只能靠描述认人（这段描述本身就带"的女生/的男生"这类中心词，
                # 句法上是人不是衣服）。
                # 🩸 2026-10-25：只取**主语短语**（第一个逗号前）。
                # 整段描述以衣服收尾（「…身着浅青绿色交领古装，内搭白色中衣」），
                # 直接当宾语会拼成「…内搭白色中衣替换为@图片1中的人物」——
                # 正是 2026-10-24 20:49 踩过的"把手枪换成一个人"那个句式 bug。
                # 🩸 2026-10-27 00:xx：`_head_noun` **会返回空串** —— 盘点描述以
                # 服装开头时（`穿橙色连帽拉链外套，左胸带有白色标识，短发…胡须`，
                # 首个逗号前没有人物名词），整句退化成
                # 「严格编辑@视频1，将其中的**替换为**@图片1中的人物」——
                # 宾语是空的，模型不知道要换谁。2026-10-26 20:01 / 20:07 两次
                # 出片**真的就是这么发出去的**（`triage/request_001.json` 原文），
                # 这两次的结果正是"没换脸 / 换成路人脸"。
                # ⇒ 取出空串时必须落到下面的 `人物` 兜底，不许把残句发出去。
                # 🩸 2026-10-30：`_head_noun` **只取第一个逗号前**，整句用顿号时
                #   那一段就是全串 —— 3–6 个特征原样进宾语，绕过官方 `:95` 的
                #   「2–3 个」和产品线的封顶 2（D12 当场抓到
                #   「戴黑色前进帽、穿蓝色外套、绿色卷边长裤的男性」3 个全发）。
                #   先过一遍 `_feat_phrase`（同一把尺、封顶 2），抽不出才退回它。
                obj = dialect.feat_fallback(src) or _head_noun(src)
            else:
                # 🩸 2026-10-27（真实盘点 `2ddd8959` 暴露）：**多人画面里连
                # 方位和特征都拿不到的人，不许退化成裸「人物」**。
                # 现场：盘点 P3 = 「多名身着日常休闲服饰的普通民众」、
                # `face_visible=false`、`position=unknown` —— 定义句那边
                # `_sd20_orig_feat` 返回空、整条被跳过（对的），但替换句这里
                # 仍然发了一句「将其中的人物替换为<主体3>」。同一份提示词里
                # 已经定义了 <主体4>/<主体5> 两个具名的人，这句「人物」指谁
                # 没有任何唯一解 —— 正是官方 `:107`「多主体…需要分别定义…
                # 避免指代混乱」要防的东西。
                # 跳过比写错好：用户勾了却认不出时，宁可少换这一个，
                # 也不要让模型拿这句话去猜（猜错就是画面里凭空多/少一张脸）。
                # 只在**别人写得出具名宾语**时才跳过：
                # 那种提示词里「人物」= 在另一个具名的人旁边指谁都不知道。
                # 一个人都认不出来（老调用方不传 `source_people`、盘点全缺）
                # 时，整份提示词本来就没有具名指认，裸「人物」是唯一写法 ——
                # 这时跳过会让图白传（D10「每张图都被引用」当场判红）。
                # 🩸 2026-10-30：条件原来是 `len(orig_tags) >= 2`（原片侧定义过
                #   ≥2 个 `<主体N>`）。定义句已停用（`_person_tags_20`），这个数
                #   恒为 0 ⇒ 群体项（`多名…普通民众`）不再被跳过，写出
                #   「将其中的人物替换为@图片3中的人物」（D16 当场报红）。
                #   改问**同一把尺**：名单里别人能不能被指认出来。
                _named_others = any(
                    (dialect.orig_feat(people, _k, pool=frame_people or people,
                                       cloth=False)
                     or _head_noun(_inline(str((_p or {}).get("desc_zh") or ""))))
                    for _k, _p in enumerate(people) if _k != i)
                if multi and _named_others:
                    continue
                # 官方 2.5 指南的换人原句就是「把 @video1 的人物修改为 @image1」；
                # sd2-pe 是「严格编辑 @视频N，将其中的<原特征>修改为<新特征>」。
                # 🩸 单人画面**不要**带原片人物描述：那段描述写的是衣服
                # （"身着…和服，腰间系…腰带"），模型会把它当成修改对象 ——
                # 2026-10-22 实测 25s 那条：服装/发饰换了，**脸还是原片那张**
                # （SFace 判定：与原片同人 49/56 帧，与参考图 0/65 帧）。
                obj = "人物"
            # 🩸 2026-10-26 20:xx（主人：「又说官方没写了是不是」）：**这条我删错了。**
            # 早上删「每一镜里的人物都替换为…」的理由是"官方 0 次提到每一镜"——
            # 拿"官方没写"当判据是偷懒：官方给的是**推荐句式**，不是白名单。
            # 官方真正写了的是"范围"这回事，而且有自己的词：
            #   · `:33`「在原视频基础上进行**局部或全局**修改。未提及的部分，默认保持不变」
            #     —— 不声明范围 = 切镜之后那些镜头属于"未提及"，原样返回；
            #   · `:409` 标题就叫「**添加全局约束指令**」，`:411` 的示例用词是
            #     「**视频全程**禁止出现…」；`:328`「人脸与参考图**全程**保持一致」。
            # ⇒ 用官方的「视频全程」，不用我自造的「每一镜」。
            # 只在原片**有切点**时挂（`scope_all`）：没有切点的片子，
            # `:40` 的「其中的」已经覆盖全片，多写一句是 `:121` 说的冗余。
            # 🩸 2026-10-27：**范围词一句只写一次**（`not wrote`）——
            # 以前写在每人的循环里，换两个人就写两遍
            # 「视频全程将其中的<主体1>…；视频全程将其中的<主体2>…」。
            # 官方 `:33`「局部或全局修改」里的"全局"是**整片都按这条改**，
            # 不是"整片重绘"；一次声明就管住后面所有换人分句，`:121` 也要求精简。
            _scope = "视频全程" if (scope_all and not wrote) else ""
            s = f"{_scope}{_subj(obj)}替换为{tgt}"
            # 🩸 这里以前还有一句「@图片N是替换后人物的唯一身份来源：脸、发型、
            # 肤色、年龄感、面部结构、可见造型都以它为准，与其他参考冲突时以它为准」。
            # 出处是 **ReplicaPilot / variants.js（第三方）**。2026-10-23 我按
            # "说明书里没有就不写"删掉了 —— **删错了**：官方有，只是不在编辑句式
            # 那两行，而在《Seedance 2.0 提示词指南》§「人脸参考不准确」
            # （`seedance-20-guide.md:317`）和 `sd2-pe:139/:225`：
            #   `<主体1> 的面部特征参考 @图片1（大头照），妆造参考 @图片2（全身照）`
            # 官方写的是「面部特征参考」，比第三方那句更具体。现在按官方原文补：
            # 只有一张图时只写面部特征（不编一个不存在的妆造图号）。
            # 🩸 只写官方给它的职责「妆造」，别加"体型"——2026-10-22 加了"体型"那版
            # 实测把主体放大 1.75×、景别从远景变中景，构图跟着跑。
            # 🩸 2.5 **不在这句后面追加**「面部特征参考…／妆造参考…」。
            # 官方 2.5 视频编辑模板（`sd25-pe` §视频编辑模板）的【编辑目标】
            # 只有一句：「编辑@视频1，只把<原对象或区域>修改为<目标内容>。」
            # 每张参考图负责什么，模板把它放在【目标素材职责】里**逐张**说
            # （同一节：「@图片1用于<目标主体>的<外观、结构或材质>」）。
            # 两处都写 = 同一件事说两遍；而且「**参考**」这个词把身份从
            # "替换"降成了"参考"，模型有理由只搬妆造、不动脸。
            # 2.0 **没有**职责块，这句必须留在句子里 —— 官方 `sd2-pe:139`
            # 原句就是「面部特征参考 @图片1（大头照），妆造参考 @图片2（全身照）」。
            # 「换人后跟一句职责」只有 2.0 有（2.5 把它放进【目标素材职责】逐张说）。
            # 两家各写各的，见 `volc20_compile._CL20.person_duty()`。
            _in_wardrobe = bool(c.get("wardrobe")) and str(
                per.get("id") if per else "") in {
                    str(x) for x in (c.get("wardrobe_ids") or [])}
            _duty = dialect.person_duty(pic=pic, rtag=_rtag,
                                        in_wardrobe=_in_wardrobe)
            out.append(s)
            # 🩸 2026-10-30：职责分句**独立成句**，不再接在替换句尾巴上 ——
            #   官方 `sd20-guide:59-65` 的组合任务句式要求参考分句排在「严格编辑」
            #   **之前**。2.0 的编译器会把以「参考@图…」开头的分句提到前面
            #   （`volc20_compile._compile` 的 `_lead`）。同一个图号只写一次。
            if _duty and _duty not in out:
                out.append(_duty)
            wrote += 1
        if not wrote:
            # 没参考图：目标只能是文字描述，别拿"原片里那个人"当目标
            src = _inline((people[0] or {}).get("desc_zh") or "") if people else ""
            desc = c.get("person_desc") or ""
            # 🩸 V20-2 / V25-1（2026-10-23 层 3 分通道跑出来的）：这里以前写
            # `f"把{v}中…"`，而 head 已经前置了 `@视频1，`，拼出来就是
            #   · 2.0「严格编辑@视频1，把@视频1中原片里的男生替换为…」
            #   · 2.5「编辑@视频1，只把@视频1中原片里的男生替换为…」
            # 官方模板（`sd2-pe:24` / `sd25-pe:561`）里 `@视频N` 只出现一次。
            # 其它分支早就改走 `_subj()` 了，只有这一处漏着。
            out.append(f"{_subj(src or '人物')}替换为{desc or '另一个人'}")

    if c.get("product"):
        # 换成什么 = 参考图；换画面里的哪一件 = `product_target`（盘点给的外观，
        # 用户在界面上点选）。官方编辑句式要求对象明确：「把<原对象>替换为<目标>」，
        # 只写"产品"在有多件东西的画面里没有唯一解。
        desc = c.get("product_desc") or ""
        tgt = (c.get("product_target") or "").strip()
        what = tgt or "产品"
        # 🩸 2026-10-27（LAS `las_cn.md:385`，`general` 模板官方原句）：
        #   「把桌面上的杯子改成参考图1中的产品，**其他人物、物体和背景保持不变**」
        # 这句是换物体场景缺的那一半：光说「换什么」，模型不知道**别的东西也别动**
        # （`sd20-guide:33` 虽然说了未提及默认不变，但 `:41` 明写「对于保持不变的元素，
        # 在提示词中加以强调，表现更佳」）。换商品最怕的就是背景跟着重绘、
        # 旁边的人变了个样。
        # 🩸 「其他…保持不变」里列哪些类别，看本次**动了什么**：动过的不许列。
        # 顺序照 LAS 原文「人物、物体和背景」；「物体」恒列（官方在换物体的句子里
        # 也这么写 —— 它指的是**被换那件以外**的东西）。「背景」在被换时不能列，
        # 否则同一段里「背景保持不变」紧跟着「把背景替换为…」。
        _keep_p = ["物体"]
        if not (c.get("person") or c.get("wardrobe")):
            _keep_p.insert(0, "人物")
        if not c.get("scene"):
            _keep_p.append("背景")
        if "product" in idx:
            s = f"{_subj(what)}替换为{_pic(channel, idx['product'])}中的产品"
            if desc:
                s += f"（{desc}）"
            s += dialect.keep_others(_keep_p)
        else:
            s = f"{_subj(what)}替换为{desc or '另一个产品'}"
            s += dialect.keep_others(_keep_p)
        out.append(s)

    if c.get("scene"):
        desc = c.get("scene_desc") or ""
        if "scene" in idx:
            s = f"{_subj('背景')}替换为{_pic(channel, idx['scene'])}中的场景"
            if desc:
                s += f"（{desc}）"
        else:
            s = f"{_subj('背景')}替换为{desc or '另一个场景'}"
        # 🩸 同 `product` 分支：LAS `las_cn.md:385` 官方原句的后半句。
        # ⚠️ 但**去掉「背景」**：这句前面的主体正是「背景」（「将其中的背景替换为…」），
        # 再说「背景保持不变」就是同一段提示词里自相矛盾（`sd20-guide:121`「避免语义冲突」）。
        # LAS 的 `general` 示例换的是杯子，背景不属于被换对象，所以它能写。
        _keep_s = ["物体"]
        if not (c.get("person") or c.get("wardrobe")):
            _keep_s.insert(0, "人物")
        s += dialect.keep_others(_keep_s)
        out.append(s)

    if c.get("wardrobe"):
        # 换装名单为空 = 老语义：一句话换掉画面里所有人的服装（单人片够用）
        wid = [x for x in (c.get("wardrobe_ids") or []) if str(x).strip()]
        desc = (c.get("wardrobe_desc") or "").strip()
        # 🩸 2026-10-27：按人写的服装描述（`{人物 id: "米色风衣"}`）。多人换装时
        # 一个 `wardrobe_desc` 说不清谁换哪套 —— 前端**每个人一个输入框**，
        # 收集到这个字典里。空/缺键时回落到全局 `wardrobe_desc`（老客户端）。
        _desc_by_pid = c.get("wardrobe_desc_by_id") or {}
        wrote = 0
        for i, pid in enumerate(wid):
            slot = WARDROBE_SLOTS[i] if i < len(WARDROBE_SLOTS) else ""
            who = _who(desc_by_id, pid, "zh")
            # 🩸 V20-1（2026-10-23）：who 为空时以前给「人物的服装」，和 2.0 的
            # 前缀「将其中的」拼成「其中的人物 的服装」（两个「的」）。官方模板
            # `sd2-pe:24` 的 `<原特征>` 本身就是一个名词（示例是「香水」）。
            # 2.5 的前缀是「只把」，读起来没这个问题，但改成「服装」对两家都更干净。
            _obj_w = f"{who}的服装" if who else "服装"
            # 🩸 2026-10-28：这两个变量**必须两家都有初值** —— 下面的拼装句
            # 无条件读 `_bare_subj`。只在 2.0 分支里定义的话，2.5
            # （`edit_task=True`）走到那一行就是 NameError（当场炸，整单出片失败）。
            # 换装句的宾语 =「谁的衣服」。**两家各写各的**（标签 vs 外观短语）：
            # `volc20_compile._CL20.wardrobe_subject()` /
            # `volc25_compile._CL25.wardrobe_subject()`。
            # 返回第二项 `_bare_subj` = 宾语本身已是图片侧标签，不能再套前缀。
            _obj_w, _bare_subj = dialect.wardrobe_subject({
                "pid": pid, "i": i, "people": people,
                "frame_people": frame_people, "desc_by_id": desc_by_id,
                "who": who, "c": c, "channel": channel,
                "orig_tags": orig_tags, "ref_tag": ref_tag,
            })
            # 这个人自己写的那句话优先；没有就回落到全局 `wardrobe_desc`
            # （老客户端只传一个字段，语义是"第一个人的那套"）。
            _d1 = str(_desc_by_pid.get(str(pid))
                      or _desc_by_pid.get(pid) or "").strip()
            if not _d1 and i == 0:
                _d1 = desc
            # `_bare_subj`：宾语本身就是图片侧标签（`<主体1>`），不能再套
            # 「将其中的」——那张脸不在 @视频1 里，说了等于让模型去视频里找它。
            if slot and slot in idx:
                # 官方 2.5 示例：「视频中深色衣服的男子的服饰替换为 @图片2」
                # 🩸 2026-10-28（2.5 轮）：2.5 的换装动词按**正式示例**取 ——
                # `sd25-guide:1209`（唯一的换装示例）「视频中深色衣服的男子的
                # **服饰替换为** @图片2」+ `sd25-pe:584`（模板的已填示例）
                # 「只把…红色自行车和骑行者**替换为**…」。
                # 触发关键词清单 `sd25-guide:88` 里没有「换成」—— 那张表管的是
                # **输入识别**，不是产出句式，不拿它当产出依据（只是顺带印证）。
                # 以前两个型号共用「换成」，2.5 的换装句整句不含任何官方示例动词。
                # 这里只改 2.5 这一支（`wardrobe_verb` 由方言给），2.0 的口径不动。
                _wf = dialect.wardrobe_verb()
                s = (f"{_obj_w}{_wf}" if _bare_subj
                     else f"{_subj(_obj_w)}{_wf}") + f"{_pic(channel, idx[slot])}中的服装"
                if _d1:
                    s += f"（{_d1}）"
            elif _d1:
                # 没传图但有文字描述 → 官方 `sd20-guide:39`「将其中的<原特征>
                # 修改为<新特征>」，`_d1` 就是那个"新特征"。
                # 🩸 2026-10-28：动词按型号取（`wardrobe_verb_text`）—— 2.0 用
                #   官方的「修改为」，2.5 与它同一句里的换装句统一成「替换为」
                #   （`sd25-guide:1209` 那条唯一的换装示例）。一句话里两个动词
                #   等于给模型两个说法。
                _wt = dialect.wardrobe_verb_text()
                s = (f"{_obj_w}{_wt}{_d1}" if _bare_subj
                     else f"{_subj(_obj_w)}{_wt}{_d1}")
            else:
                # 🩸 2026-10-27：点了这个人却**既没传图也没写描述**时，什么也不发。
                # 以前兜底写「修改为另一套服装」—— 那不是官方句式里的 `<新特征>`
                # （`sd20-guide:39`），等于告诉模型"随便换一套"，出片结果随机不可复现。
                # 前端会在提交前拦住（`diagnose.vue` 换装校验），这里是第二道。
                continue
            out.append(s)
            wrote += 1
        if not wrote:
            # 同 V20-1：没点名具体的人时直接说「服装」，别写成「人物的服装」
            # 让 2.0 拼出「其中的人物 的服装」。
            if "wardrobe" in idx:
                # 🩸 2026-10-28：这一支是「勾了换装但**没点名具体谁**」的兜底
                #   （`wrote == 0`）。上面点名那一支早就按型号分了动词
                #   （`:1709` `_wf = "修改为" if edit_task else "换成"`），
                #   这里却一直硬编码「换成」—— 2.5 的产出整句不含任何官方动词
                #   （`sd25-guide:88` 只收「修改/替换/改成」，没有「换成」），
                #   尺子 T3 直接判红。**按同一个 `edit_task` 分，不新造规则。**
                _wf2 = dialect.wardrobe_verb()
                s = f"{_subj('服装')}{_wf2}{_pic(channel, idx['wardrobe'])}中的服装"
                if desc:
                    s += f"（{desc}）"
            elif desc:
                s = f"{_subj('服装')}{dialect.wardrobe_verb_text()}{desc}"
            else:
                # 同 above：没有目标服装就不发空指令
                s = ""
            if s:
                out.append(s)

    # 风格参考（A9）：图 / 视频 二选一；**风格词在 2.0 与它们叠加**。
    # 🩸 2026-10-27（真实矩阵 + 前端文案对账）：以前这里是「图 > 视频 > 词」
    # 三选一，结果用户既选了「2D日漫风格」又传了风格图时，风格词**整句丢掉**。
    # 官方 `sd20-guide:357-359` 正好说的是这个场景：
    #   「期望生成 2D 或者 3D 动漫风格，但输入的参考图片的风格比较写实，并且
    #     提示词中**未强调视频风格**，生成的视频有概率漂移成真人写实风格。
    #     ⇒ 在提示词中加入明确的风格约束词，例如"2D日漫风格"、"3D国风漫画"。」
    # 即：**有风格图时恰恰最需要风格词**。前端文案也一直写「和上面的风格词
    # 叠加，参考图定观感」（`diagnose.vue` 风格参考区）—— 代码和界面原先对不上。
    # 2.5 不动（`edit_task` 仍保持三选一，那一支走模板，本轮不碰）。
    # 句式依据（都是火山官方，2.5 指南 `:966` 明说风格参考的用法与 2.0 一致）：
    #   · 图：`seedance-20-guide.md:228`「@图片 2 作为…**风格参考**」
    #   · 视频：`:26`「参考`<视频N>`中的`<动作/运镜/**风格**/音效>`」
    #   · 维度：`:204-206` 风格示例都是色调/光影/质感（赛博朋克冷蓝紫色调、复古胶片）
    # 🩸 只取观感、不取内容：不写这句，模型会把风格图里的主体和构图一起搬进成片。
    # 🩸🩸 2026-10-27 定性（主人：「你这样会导致自己都判断不准」）：这句
    # 「不采用其中的主体、构图和场景内容」**不是官方原文** —— 2.0 六份资料全文
    # 零命中，措辞取自 2.5 skill（`sd25-pe:568` 的【目标素材职责】模板）。
    # 它保留的唯一理由是上面那条**实测**，所以：**不许当官方规则引用**，
    # 也不许拿它去推别的型号。2.0 官方对风格参考只说「作为风格参考」（`sd20-guide:228`）。
    # 2.5（edit_task）走模板「只把<原对象>修改为<目标内容>」，所以只写"改成什么"，
    # "不采用什么"由【目标素材职责】那一行负责（模板要求职责逐份说）。
    # 🩸🩸 2026-10-27（主人：「你根本没有对标 2.0 官方」）——**句式改对了**。
    # 官方 `sd20-guide:59-65`「组合任务」规定的句式是：
    #   「参考`<图片/视频N>`的`[参考维度]`，**严格编辑**`<视频X>`，`[具体编辑内容]`」
    # 即参考分句必须在**严格编辑之前**；`sd20-guide:56` 还专门警告编辑任务
    # 「请勿使用"参考`<视频N>`"，以免被误判为参考任务」—— 只有组合任务这个
    # 固定句式里才允许「参考」字样，且位置在前。
    # 以前我们写的是「严格编辑@视频1，…；整体画面风格参考@图片2的…」：
    # 参考句挂在句尾、措辞也不是官方的「参考<素材N>的[维度]」⇒ 两条都不合。
    # 拼接由 `volc20_compile` 负责（把这条挑出来前置），这里只负责产出正确的句子。
    if c.get("style_ref") and "style_ref" in idx:
        pic = _pic(channel, idx["style_ref"])
        out.append(dialect.style_ref(pic))
    elif c.get("style_video") and style_video:
        out.append(dialect.style_video())
    # 有风格参考时还发不发风格词：2.0 叠加、2.5 三选一（各家自己的口径）。
    if c.get("style") and (dialect.style_word_when_ref()
                           or (not (c.get("style_ref") and "style_ref" in idx)
                               and not (c.get("style_video") and style_video))):
        word = STYLES[c["style"]]
        if style_anchor:
            # 🩸 2.0 风格必须写成**具体风格锚定词**，不能只写媒介/技术名：
            #   指南:354「在提示词中加入明确的风格约束词，例如"2D日漫风格"、"3D国风漫画"」；
            #   `sd2-pe:163`「动漫 / 非写实场景**必挂**风格锚定」。
            #   以前这里直接拼 STYLES 的中文（"动漫"/"三维渲染"），那是媒介词不是风格词，
            #   模型照样可能漂移成真人写实。
            word = _STYLE_ANCHOR_20.get(c["style"], word)
        # 🩸 不能走 `_subj()`（2.0 会给它套「将其中的…」）：风格不是视频里
        # 「其中的某个东西」，官方把它当**整条片子的风格约束词**挂在句尾 ——
        # `sd20-guide:359`「在提示词中加入明确的风格约束词，例如"2D日漫风格"」、
        # `sd20-guide:713`「整体风格为 3D 赛博朋克科幻动画风格」。
        # 同一个功能的风格参考图那一支本来就是独立陈述句（`:1037`），
        # 两支承同一句式，别一支说「整体画面风格参考…」另一支说「将其中的…改成…」。
        # 动作用「改成」（与本功能在 2.5 那一支的写法 `画面风格改成…` 对齐，
        # 也保住 `test_edit_spec`「只改风格也含改成」那条检查 —— 风格句是编辑指令，
        # 不是描述句）。丢掉的只是 `_subj()` 套上来的「将其中的」。
        # 🩸 2026-10-26（2.5 穷举 E2）：2.5 走模板「**只把**<原对象>修改为<目标内容>」
        # （`sd25-pe:561`），风格也是一种编辑对象 —— 句首加「把」，才能吃到
        # `_volc_25` 统一补的那个「只」。不加的话整句是「整体画面风格改成动漫」，
        # 没有限定词，模型有理由把整条片重画。2.0 保持原句式不动。
        # 🩸 2026-10-27：原来 2.0 也写「整体画面风格**改成**X」，理由记的是
        # 「与 2.5 那一支对齐」—— 又是跨型号搬运。2.0 官方自己有这句的写法：
        # `sd20-guide:713`「**整体风格为** 3D 赛博朋克科幻动画风格」；
        # `sd20-guide:359` 也把它定位成「风格**约束词**」，不是「把某物改成某物」的编辑动作。
        out.append(dialect.style_word(word))
    return out


def _join_changed(changed: list[str]) -> str:
    """把逐条改动连成一句：去重句尾的句号，别拼出「unchanged..」/「unchanged.;」。"""
    return "; ".join(x.strip().rstrip(".;。") for x in changed if x.strip())


def _others_unchanged(names: list[str]) -> str:
    """「，其他人物、物体和背景保持不变」—— 只列本次**没动**的类别。

    🩸 2026-10-27：LAS `las_cn.md:385` 的 `general` 示例原文是
      「把桌面上的杯子改成参考图1中的产品，**其他人物、物体和背景保持不变**」，
      那一组**只改了物体**。我们把同一句搬到「同时换人 + 换产品」时，同一段
      提示词里就出现「将其中的**人物**替换为@图片1中的人物」+
      「其他**人物**、物体和背景保持不变」—— 自相矛盾（`sd20-guide:121` 明写
      「各描述之间避免冗余和语义冲突」）。所以列什么由本次改了什么决定。
    """
    if not names:
        return ""
    body = ("、".join(names[:-1]) + "和" + names[-1]) if len(names) > 1 else names[0]
    return f"，其他{body}保持不变"


# 槽位 → 它在规格里的描述字段。人物的描述字段不在表里：换人只认图/资产 ID
# （见 `missing_material` 的说明）。
_DESC_OF = {"product": "product_desc", "scene": "scene_desc",
            "wardrobe": "wardrobe_desc"}
_SLOT_CN = {"person": "人物", "product": "产品", "scene": "场景",
            "wardrobe": "服装造型"}


def missing_material(spec: dict, refs=None, *, person_asset: str = "",
                     style_video: bool = False,
                     audio_files: dict | None = None,
                     model: str = "",
                     wardrobe_per_person: bool = False) -> str | None:
    """勾了槽位却既没素材也没描述 → 返回一句能照做的话；None = 没问题。

    🩸 不拦的后果实测有两种（2026-10-23 逐个槽位编译过 18 组）：
      · 火山 → 写出「替换为**另一个**产品 / 另一个场景 / 另一套服装」
        —— 模型自己编一个换上去，用户拿到的不是他要的；
      · H3   → 产品/场景**提示词里一个字都不写**，花完钱画面完全没变。
    `docs/CLONE-CHANNELS.md:520` 早就写了「提交前会挡掉勾了槽位但既没素材也没描述」，
    但代码里一直只有人物那一条。

    人物不在这张表里：它没有可用的描述字段（`person_desc` 编译时根本不参与，
    见 `_clauses` 人物分支）。换人必须给图或火山资产 ID —— 文字锁不住一张脸。
    """
    c = spec["change"]
    refs = refs or {}
    # 人物单独一句话术（和界面上那条一致）：它没有可用的描述字段，
    # 所以「换人没图」必须说清后果，不能只说"缺素材"。
    if c.get("person") and "person" not in refs and not (person_asset or "").strip():
        # 老接口调方可能只给文字（person_desc）：留着不拦，界面已经不给入口
        if not (c.get("person_desc") or "").strip():
            return ("换了人物就得给一张人物照片（或 asset:// 素材 ID）：没有图时，"
                    "提示词里没有「换成谁」，模型只会把原片的人原样再画一遍。")
    lack: list[str] = []
    for slot, desc_key in _DESC_OF.items():
        if not c.get(slot):
            continue
        # 🩸 2026-10-28：这里以前写 `str(model or "").startswith(("doubao-seedance-2-0", …))`
        #   —— 共用层出现型号名，分离门数成厂商耦合（基线 0，被这条顶到 2）。
        #   现在由调用方传 `wardrobe_per_person`（取自 `adapter.caps`），
        #   核心只认标记，**不认识有几家模型**。
        if slot == "wardrobe" and wardrobe_per_person:
            # ⚠️ **只有开了这个能力位的型号才逐个查**（2026-10-27 主人：「现在让你调试
            # 2.0 模型，其他模型还没轮到」）。2.5 / H3 先保持老行为（只查 `wardrobe`
            # 一个槽位），它们的问题等轮到它们那一轮再改 —— 「一轮一个型号」的硬边界。
            # 🩸 2026-10-27：换装要**逐个**查。名单里的每个人各有自己的槽位
            # （`wardrobe` / `wardrobe2` …）和自己的那句描述（`wardrobe_desc_by_id`）。
            # 以前只查 `wardrobe` 一个槽位：第 1 个人有图就整体放行，
            # 第 2、3 个人没图没描述的会被编译器静默跳过 —— 图白传，用户看不出来。
            wid = [x for x in (c.get("wardrobe_ids") or []) if str(x).strip()]
            _by = c.get("wardrobe_desc_by_id") or {}
            _gd = (c.get("wardrobe_desc") or "").strip()
            if not wid:
                if "wardrobe" not in refs and not _gd:
                    lack.append(_SLOT_CN["wardrobe"])
            else:
                _miss = 0
                for _i, _pid in enumerate(wid):
                    _sl = "wardrobe" if _i == 0 else f"wardrobe{_i + 1}"
                    _d = str(_by.get(str(_pid)) or _by.get(_pid) or "").strip()
                    if not _d and _i == 0:
                        _d = _gd
                    if _sl not in refs and not _d:
                        _miss += 1
                if _miss:
                    lack.append(_SLOT_CN["wardrobe"])
            continue
        if slot in refs:
            continue
        if (c.get(desc_key) or "").strip():
            continue
        lack.append(_SLOT_CN[slot])
    if lack:
        return (f"勾了「{'、'.join(lack)}」却没给素材："
                "传一张图，或写一句换成什么。两者都没有，这一段出了也不会变。")
    # 风格参考（A9）：只开了开关没传素材，提示词会**静默忽略**它，用户花完钱
    # 才发现风格没变。风格没有"写一句话代替"的退路 —— 它就是要素材本身。
    if c.get("style_ref") and "style_ref" not in refs:
        return ("勾了「风格参考图」却没上传图片：风格参考必须给一张图，"
                "否则提示词里不会出现这份素材，成片风格不会变。")
    if c.get("style_video") and not style_video:
        return ("勾了「风格参考视频」却没上传视频：风格参考必须给一段片，"
                "否则提示词里不会出现这份素材，成片风格不会变。")
    # 原片声音处理（C4）：这两个开关都**必须**有素材才成立 ——
    # `drop` 不需要（官方 `sd25-pe:635`：删背景音乐不用虚构目标素材），
    # 但"换成我上传的"/"再加一段"没文件就是空话，出片后用户会以为已经生效。
    af = audio_files or {}
    if (spec.get("bgm") or "keep") == "replace" and not af.get("bgm"):
        return ("选了「换成我上传的背景音乐」却没上传音乐文件："
                "没有文件时这一项不会生效，成片还是原片的背景音乐。")
    if (spec.get("sfx") or "keep") == "add" and not af.get("sfx"):
        return ("选了「再加一段音效」却没上传音效文件："
                "没有文件时这一项不会生效，成片听不到新音效。")
    # 🩸 参考图**张数**上限（2026-10-28）：官方 `volc-api:35`
    #   「2.0 系列 = 图 0-9 + 视频 0-3 + 音频 0-3」⇒ 图片最多 9 张。
    #   以前每项改动各自查素材、没人查**总数**：4 人换人 + 4 人换装 + 产品 + 场景
    #   + 风格图 = 11 张，每一项都在自己的规则内，合起来超了 2 张 → 请求被拒。
    #   10 个人换装（不勾换人，人数闸管不到）更是直接 10 张。
    #   `refs` 是「槽位名 → 路径」的字典，长度就是真正会发出去的图片数。
    if model and refs:
        try:
            from app.services import models as _models
            _spec = _models.adapter_for(model=model).specs_for(model) or {}
        except Exception:  # noqa: BLE001
            _spec = {}
        _cap = int(_spec.get("max_ref_images") or 0)
        _n = len(refs)
        if _cap and _n > _cap:
            # 🩸 2026-10-28：那句「官方 2.0 系列是图 0-9」以前**无条件**拼在后面 ——
            #   2.5 的客户超 30 张时，会看到「超出该型号的 30 张上限：官方 2.0 系列
            #   是图 0-9」，自相矛盾。2.5 的上限出处是 `seedance-25-guide:116`
            #   「输入素材总上限：图片最多 30 张」，不是同一条。
            _why = ("官方 2.0 系列是「图 0-9 + 视频 0-3 + 音频 0-3」。"
                    if _cap == 9 else "")
            return (f"这次要发 {_n} 张参考图，超出该型号的 {_cap} 张上限。"
                    f"{_why}请少选几个人/几件东西，或分几条片子出。")
    return None


def _keep_sentence(channel: str, spec: dict, *, only=None,
                   verb: str = "保持") -> str:
    """保留句（**只有通用句式**）。`only` = 只取这几项（2.5 把画面属性和
    时间属性分到两段用）；`verb="不修改"` = 官方 `sd25-pe:568` 第三句
    「不修改<需要保持的内容>」的句式。

    🩸 某家有**自己的**保留句写法 → 写在 `models/<家>_compile.py` 里，
    **不许在这里加分支**。本函数的职责只有「按 `KEEP_LABELS` 拼一句通用句」，
    不认识任何一家。已经搬走的两位：
      · 2.0 官方「单点编辑」三种原句 → `volc20_compile._keep_point_edit()`
      · 「按新配音重做口型」→ `volc25_compile`（2.5 专属，见下）
    """
    # 🩸 风格参考（A9）改的就是**色调/光影/质感**（2.0 指南 `:204-206` 的三个维度）——
    # 同一段提示词里再说「光线和色调不变」就是自相矛盾，模型两头听。
    # 这一条只在有风格参考时生效，枚举风格词照旧（词是"改成什么"，不是参考素材）。
    _chg = spec.get("change") or {}
    _style_src = bool(_chg.get("style_ref") or _chg.get("style_video"))
    keep = []
    for k, v in spec["keep"].items():
        if not v:
            continue
        if only is not None and k not in only:
            continue
        if _style_src and k == "lighting":
            continue
        keep.append(KEEP_LABELS[k])
    # 🩸🩸 2026-10-28：这里以前还夹着两样**某家的东西**，都已搬走：
    #   ① `point_edit` 分支 —— 2.0 官方「单点编辑」三种句式
    #      → `volc20_compile._keep_point_edit()`
    #   ② 「按新配音重做口型」那句 —— 只在 2.5 官方有（`sd2-pe` /
    #      `seedance-20-guide` / `volc-create` grep「口型」0 次）
    #      → `volc25_compile` 自己拼
    #   形式上是"开关"，实质仍是某家的句子躺在三家共读的文件里；
    #   加第 4 家时这里又得加分支 —— 正是当初说"加一家要改 10 处"的形状。
    #   **本函数现在只剩一个判断**：`verb` 决定用哪个动词。
    if verb == "不修改":
        return f"不修改{_vid(channel)}的{'、'.join(keep)}。" if keep else ""
    return f"保持{_vid(channel)}的{'、'.join(keep)}不变。" if keep else ""


# 🩸 这里以前还有一条 `_VOLC_20_FACE_GUARD`（「不要出现脸部漂移或身份混合，
# 不要恢复原片人物的脸，不要出现僵硬表情或呆滞眼神」），出处是
# **ReplicaPilot（第三方项目）**，不是火山官方说明书。sd2-pe 里没有这条负向域。
# 2026-10-23 按"说明书里没有就不写"删除。


# 🩸 官方 `h3_ref-en.txt:3`：「**Write all six rewrite sections in English.**
# Preserve the original language only for dialogue and lyrics inside `<d>` and for
# text visibly present in the scene.」
# 用户在界面上填的产品/场景/服装描述是**中文**，直接拼进 `<Subject N>` 定义就是
# 在英文正文里塞中文句子（实测产出 `described as: 蓝色陶瓷杯.`）。
# 有参考图时图本身就是外观来源，描述可以不写；只有"给了描述但没给图"时才不得不写。
_CJK_RE = re.compile(r"[一-鿿]")


def _en_only(s: str) -> bool:
    """这段文字能不能进 H3 的英文六段（含中日韩字符就不行）。"""
    return bool((s or "").strip()) and not _CJK_RE.search(s)


def _en_clean(s: str) -> str:
    """**系统自己写**进英文六段的字段（盘点 desc_en、原片定位词）—— 含中日韩字符
    就整段丢掉。官方 `ref-en:3` 只允许 `<d>` 和画面文字保留原语言。

    🩸 `vision_plan.normalize` 的兜底是 `desc_en or desc_zh`：盘点没给英文时，
    `desc_en` 里装的是中文。那条兜底值直接拼进 `<Subject N>` 就是中文正文。
    丢掉只少一个定语，句子仍然成立（"the product" / "the person on the left"）。
    """
    return (s or "").strip() if _en_only(s) else ""


def _h3_mmss(t: float) -> str:
    """秒 → 官方时间码 `MM:SS.mmm`（`ref-en:218`，例 00:09.000）。"""
    m, s = divmod(max(0.0, float(t)), 60.0)
    return f"{int(m):02d}:{s:06.3f}"


# 【目标素材职责】每张参考图"负责什么、不采用什么" —— sd25-pe:568 模板原文：
#   `@图片1用于<目标主体、背景或商品>的<外观、结构或材质>，不采用<无关背景、人物或构图>。`
# 🩸 这是 2.5 编辑模板里**唯一明说"这张图管什么"的位置**。缺了它，模型只知道
#   "有一张图"，不知道它是不是那个人的外观来源。
_DUTY_ROLE = {
    "product": "目标产品的外观、结构和材质",
    "scene": "目标场景的环境和结构",
    "wardrobe": "目标服装的款式、颜色和材质",
    # 风格参考图（A9）：模板占位符允许 <目标主体、背景或商品>，风格图给它
    # "整片观感"这个对象；维度照 2.0 指南 `:204-206` 的风格示例（色调/光影/质感）。
    "style_ref": "整体画面的色调、光影和质感",
}

# 🩸 人物素材的属性词按 **2.5 自己的口径**写：五官、发型、服装、配饰
#   （`sd25-pe:184`「人物素材默认只写五官、发型、服装、配饰和可直接观察的姿态」；
#    示例 `:227`「只采用五官、发型和服装」、`:388/:666/:948`「…的五官、短发和…围裙」）。
#   2.5 全文 **一次都没出现「妆造」**（0 次）—— 那是 2.0 的口径
#   （`sd2-pe:139`「面部特征参考@图片1，妆造参考@图片2」），不许搬进 2.5 模板。
_PERSON_ATTR_ONLY = "五官、发型和服装"  # 2.5 只有一张人物图，它得全包（`:227`）


def _person_attr(slot: str, idx: dict[str, int]) -> str:
    """这张人物参考图在【目标素材职责】里负责哪几样。

    🩸 **2.5 一律写全属性「五官、发型和服装」**（`sd25-pe:227` 原句
    「只采用五官、发型和服装」，`:472` / `:948` 同形）。
    2.5 全文没有"大头照/全身照"，也没有"这张管脸、那张管衣服"的写法；
    它的多图规则是**多视角**（`:456` 正面/左侧/右侧/背面）。
    我们以前把 2.0 的大头照分工搬进 2.5 —— 2026-10-25 实测双人换人：
    被拆成"五官和发型 / 服装和配饰"两张的那个人**从头到尾没换脸**，
    只发一张、写全属性的那个人换成了。
    2026-10-26 清理：`split_person_images=False` ⇒ `person_body` 永不出现，
    原来的「有第二张就分工」分支是死代码，连同两个常量一起删掉。

    🩸🩸 2026-10-28：上面那句「一律写全属性」**只在没有独立服装槽时成立**。
    用户同时勾了换人和换装，服装就归服装图管（用户指定），人物图再说自己
    「用于…服装」= 同一个属性两个来源，模型只能自己挑一个猜。实测形状：
        @图片1用于目标人物的五官、发型和服装      ← 人物图
        @图片2用于目标服装的款式、颜色和材质      ← 服装图
    官方 `sd25-pe:243`：「同一主体的多份参考互相冲突时，**先服从用户指定**」。
    570 组穷举里这个形状命中 96 组（2.5 一轮里规模最大的一条）。
    判据 = `ruler_sd25.P6`。
    """
    if any(str(k).startswith("wardrobe") for k in (idx or {})):
        return "五官和发型"
    return _PERSON_ATTR_ONLY


def _duty_role(slot: str) -> str:
    if slot in _DUTY_ROLE:
        return _DUTY_ROLE[slot]
    if slot.startswith("wardrobe"):
        return _DUTY_ROLE["wardrobe"]
    return ""




def shot_prompt(spec: dict, fallback: str = "") -> str:
    """混剪模式用的提示词：逐帧重画，没有「视频1」可指代，所以不写素材标号。"""
    c = spec["change"]
    bits: list[str] = []
    if c.get("person"):
        bits.append(f"把画面主体换成{c.get('person_desc') or '另一个人'}")
    if c.get("product"):
        tgt = (c.get("product_target") or "").strip()
        bits.append(f"把画面里的{tgt or '产品'}换成{c.get('product_desc') or '另一个产品'}")
    if c.get("scene"):
        bits.append(f"把背景换成{c.get('scene_desc') or '另一个场景'}")
    if c.get("wardrobe"):
        # 摘要给人看：按人的描述拼起来，比"另一套服装"说得清
        _wb = [str(v).strip() for v in (c.get("wardrobe_desc_by_id") or {}).values()
               if str(v).strip()]
        _ws = "、".join(_wb) or (c.get("wardrobe_desc") or "")
        bits.append(f"服装改成{_ws or '另一套服装'}")
    if c.get("style"):
        bits.append(f"画面风格改成{STYLES[c['style']]}")
    if spec.get("extra"):
        bits.append(spec["extra"])
    if not bits and fallback:
        bits.append(fallback)
    # 🩸 ST-1（2026-10-23 层 3 分通道跑出来的）：混剪是**逐帧重画**，单帧没有
    # 运镜 / 剪辑节奏 / 时长这些时间维度，「人物动作」同理（动作是时间维度的，
    # 一帧要保的是**姿态和表情**）。规则与 `still_prompt` 完全一致 ——
    # D5（2026-10-23）给静帧改过这一段，**漏了这里**，于是混剪还在写
    # 「保持人物动作和表情、运镜和机位、剪辑节奏和时长…不变」。
    _VIDEO_ONLY = ("camera", "rhythm")
    keep = []
    for k, v in spec["keep"].items():
        if not v or k in _VIDEO_ONLY:
            continue
        if k == "background" and c.get("scene"):
            continue          # 换场景时不能要求保持背景（那是被点名要换的）
        keep.append("人物姿态和表情" if k == "motion" else KEEP_LABELS[k])
    head = "；".join(bits)
    tail = f"保持{'、'.join(keep)}不变" if keep else ""
    return "。".join(x for x in (head, tail) if x).strip()


_CN_NUM = "一二三四五六七八九十"


def pic_cn(n: int) -> str:
    """图片序号的中文写法（官方图片 API 用「图一/图二」指代参考图）。"""
    if 1 <= n <= 10:
        return _CN_NUM[n - 1]
    if 11 <= n <= 19:
        return "十" + _CN_NUM[n - 11]
    if n == 20:
        return "二十"
    return str(n)


def still_prompt(spec: dict, slots: list[str], fallback: str = "",
                 people: list[dict] | None = None,
                 desc_by_id: dict | None = None) -> str:
    """静帧重绘（图生图）的提示词：图一 = 原片帧，图二起 = 各槽位参考图。

    出处：官方图片生成 API 的 `image` 可传数组，提示词用「图一/图二」指代，
    并给每张图一个角色（官方示例：「保持图一人物的脸部特征和姿态，
    让图一人物穿上图二的蓝色外套」）。
    `slots` 必须是**真的发出去的槽位**，顺序与 image 数组一致。
    """
    c = spec["change"]
    idx = {slot: i + 2 for i, slot in enumerate(slots)}
    bits: list[str] = []
    # 风格参考（A9）改的就是色调/光影 —— 同一句里再说"光线不变"是自相矛盾
    hold = "保持图一的构图、景别" + ("" if c.get("style_ref") else "、光线")
    if not c.get("scene"):
        hold += "和背景"
    hold += "不变"
    if c.get("person"):
        people = people or []
        multi = _multi(people, desc_by_id)
        wrote = 0
        for i, ps in enumerate(PERSON_SLOTS):
            n = idx.get(ps)
            if not n:
                continue
            per = (people[i] if i < len(people) else {}) or {}
            # 🩸 单人画面**不写**方位、也**不写**原片人物描述：那句描述写的是
            # 原片的衣服，写进去模型会照着保留（2026-10-22 实测 SFace 49/56：
            # 衣服换了、脸还是原片那张）。官方 Seedream 示例同理 ——
            # `保持图一人物的脸部特征和姿态，让图一人物穿上图二的蓝色外套`，
            # 用的是"图一人物"这种纯指代，不带外观。
            src = str(per.get("desc_zh") or "").strip() if multi else ""
            # 🩸 静帧重绘的多人消歧：方位 + 外观（盘点 `position` 字段），
            # 官方 Seedream 多人融合示例也是靠它们定位（图一的男生穿上图二的西装）。
            pos = _pos_zh(per) if multi else ""
            who = (f"图一里{pos}的{src}" if pos and src
                   else f"图一里{pos}的人" if pos
                   else f"图一里{src}" if src else "图一里的人物")
            # 第一个人沿用老句式（"保持图一…，把图一里的人物…"），后面的人不重复前置句
            head = (f"{hold}，把{who}换成图{pic_cn(n)}里的人" if wrote == 0
                    else f"把{who}换成图{pic_cn(n)}里的人")
            # 🩸 官方口径（Seedream 5.0 lite 模型卡 `:9` / 使用提示 `:73`）：
            #   参考图要写明两件事 —— ① 指明参考对象（从它提取并保留什么）
            #   ② 描述生成画面。官方示例原句：
            #   `图二：人物定妆参考图，参考图中的人物形象，保持人物特征不变。`
            # 以前这里写的是「图N是替换后人物的**唯一身份来源**：脸、发型、肤色、
            # 年龄感、面部结构都以它为准」—— 出处是 **ReplicaPilot（第三方项目）**，
            # Seedream 官方文档里没有这个说法（"唯一来源/冲突时以它为准"都没有）。
            # ② 已由 `head`（把图一里的人物换成图N里的人）承担，这里只补 ①。
            line = (f"{head}；图{pic_cn(n)}是人物参考图，"
                    f"参考图中的人物形象，保持人物特征不变")
            # 一个换的人只有一张图（2026-10-26，台账 D48）—— 以前这里会再追加
            # 一句「妆造参考图为图N」（N = 派生出来的第二张），那张图已不存在。
            bits.append(line)
            wrote += 1
        if not wrote:
            bits.append(f"把画面主体换成{c.get('person_desc') or '另一个人'}")
    if c.get("product"):
        n = idx.get("product")
        tgt = (c.get("product_target") or "").strip()
        what = f"图一里的{tgt}" if tgt else "图一里的产品"
        if n:
            bits.append(f"把{what}换成图{pic_cn(n)}里的产品")
        else:
            bits.append(f"把{what}换成{c.get('product_desc') or '另一个产品'}")
    if c.get("scene"):
        n = idx.get("scene")
        if n:
            bits.append(f"把图一的背景换成图{pic_cn(n)}里的场景")
        else:
            bits.append(f"把背景换成{c.get('scene_desc') or '另一个场景'}")
    if c.get("wardrobe"):
        wdesc = (c.get("wardrobe_desc") or "").strip()
        wid = [str(x) for x in (c.get("wardrobe_ids") or []) if str(x).strip()]
        if wid:
            # 逐人换装：没点名的人不能跟着换（"图一里的人物"会让模型换错人）
            for i, pid in enumerate(wid):
                slot = WARDROBE_SLOTS[i] if i < len(WARDROBE_SLOTS) else ""
                n = idx.get(slot) if slot else None
                who = _who(desc_by_id, pid, "zh")
                head = f"图一里{who}" if who else "图一里的目标人物"
                if n:
                    bits.append(f"把{head}的服装换成图{pic_cn(n)}里的服装")
                else:
                    bits.append(f"把{head}的服装改成{wdesc or '另一套服装'}")
        else:
            n = idx.get("wardrobe")
            if n:
                bits.append(f"把图一里人物的服装换成图{pic_cn(n)}里的服装")
            else:
                bits.append(f"服装改成{wdesc or '另一套服装'}")

    if c.get("style_ref") and "style_ref" in idx:
        # 风格参考图（A9）：静帧是图生图，图进得去，照图写。
        # ⚠️ 风格**视频**到不了这里 —— `triage.decide(force_video=True)` 已经把
        # 整片强制走视频重绘，静帧分支不会拿视频冒充。
        _n = idx["style_ref"]
        bits.append(f"画面风格参考图{pic_cn(_n)}的色调、光影和质感，"
                    f"不采用图{pic_cn(_n)}里的主体和构图")
    elif c.get("style"):
        bits.append(f"画面风格改成{STYLES[c['style']]}")
    if spec.get("extra"):
        bits.append(spec["extra"])
    if not bits and fallback:
        bits.append(fallback)
    # 🩸 D5（2026-10-23）：静帧是**一张图**，不是视频。
    #   ① 「运镜和机位」「剪辑节奏和时长」在单帧上没有对应物 —— 写进去模型只能瞎猜；
    #      「人物动作」同理（动作是时间维度的），单帧要保的是**姿态和表情**。
    #   ② `hold`（换人那句的前半段）已经写过「构图、景别、光线、背景」，
    #      尾部再写一遍就是同段重复 —— 用两句话说同一件事，模型会当成两个要求。
    #   ③ 换场景时不能再要求保持背景（那是被点名要换的东西）。
    _VIDEO_ONLY = ("camera", "rhythm")
    _IN_HOLD = ("framing", "lighting", "background")
    keep = []
    for k, v in spec["keep"].items():
        if not v or k in _VIDEO_ONLY:
            continue
        if k == "background" and c.get("scene"):
            continue
        # `hold` 只在换人时出现（它挂在换人那句前面）
        if c.get("person") and k in _IN_HOLD:
            continue
        # 风格参考改的就是色调/光影 —— 尾句再说"光线和色调不变"会打架
        if k == "lighting" and (c.get("style_ref") or c.get("style_video")):
            continue
        keep.append("人物姿态和表情" if k == "motion" else KEEP_LABELS[k])
    tail = f"保持{'、'.join(keep)}不变" if keep else ""
    return "。".join(x for x in ("；".join(bits), tail) if x).strip()


def motion_prompt(spec: dict) -> str:
    """静帧重绘第二步（首帧 → 视频）的提示词。

    换什么已经在生图那一步做完了，这一步只让画面动起来。再写一遍
    「换成另一个人」会让模型在动的时候把第一帧的脸改掉。
    """
    keep = [KEEP_LABELS[k] for k, v in spec["keep"].items() if v]
    head = "以首帧为准，保持首帧里人物的长相、发型、服装和背景不变"
    tail = f"保持{'、'.join(keep)}" if keep else ""
    extra = (spec.get("extra") or "").strip()
    return "。".join(x for x in (head, tail, extra) if x)


def resolution_for(channel: str, spec: dict, *, auto: str) -> str:
    """用户选的清晰度 → 该通道的档位名。认不出来才退回 auto。

    ⚠️ 这里只做"通道级"归一；**具体型号还收不收这一档**由调用方用
    `model_specs` 兜底 —— 2.0 Mini 只有 480p/720p，H3-Max 只有 480P/768P。
    """
    caps = _res_caps(channel)
    want = (spec.get("resolution") or "auto").strip()
    if want in caps.resolutions:
        return want
    alias = caps.resolution_alias.get(want)
    return alias or auto


def audio_mode(spec: dict) -> str:
    return spec.get("audio") or "tts"


def prompt_advice(prompt: str, model: str = "") -> str:
    """提示词**建议字数**（不是硬上限 —— 超了照发，只提醒）。

    出处 `/d/tmp/volc-api:175` 原话：
      「**提示词字数建议**：中文提示词不超过 500 字，英文提示词不超过 1000 词。
        字数过多**易**导致信息分散，模型可能忽略细节、仅关注重点，
        进而造成视频缺失部分元素。」
    ⇒ 是「建议」+「易导致」，不是「必须」。`prompt_chars` 那边才是硬上限
      （2.0 官方没给 = None；H3 是 7000 字符）。

    🩸 不自动压缩（2026-10-28 主人拍板 A）：超 500 的场景恰好是「4 人全换 +
      全换装」这种最容易翻车的多人场景，这时候再削主体定义句（官方 `:109`
      要求「分别定义」）是拿指代清楚换字数 —— 得不偿失。只提示 + 给可执行的下一步。

    数值从 `prompt_advised` 字段解析，不写死：官方改数字只改规格表。
    """
    p = (prompt or "").strip()
    if not p or not model:
        return ""
    try:
        from app.services import models as _models
        _sp = _models.adapter_for(model=model).specs_for(model)
    except Exception:  # noqa: BLE001
        _sp = {}
    # 🩸 **硬上限**（H3 7000 字符，`model_specs` 的 `prompt_chars`）：超了不是
    #   "效果差一点"，是**请求直接被拒**。以前只在服务端 `log.warning` 一句，
    #   用户在界面上什么都看不到，只等到一次莫名的失败。
    #   这里跟建议字数走同一个返回通道（`prompt_advice`），让界面能说人话。
    _cap = _sp.get("prompt_chars")
    if _cap and len(p) > int(_cap):
        return (f"提示词 {len(p)} 字符，超过 {_sp.get('label') or model} 的硬上限 "
                f"{int(_cap)} 字符：**这样发出去会被接口直接拒掉**。"
                "可以减少人数/物件，或把长台词拆到两条片子里出。")
    adv = str(_sp.get("prompt_advised") or "")
    m = re.search(r"中文\s*≤\s*(\d+)\s*字.*?英文\s*≤\s*(\d+)\s*词", adv)
    if not m:
        return ""
    cap_zh, cap_en = int(m.group(1)), int(m.group(2))
    n_zh = len(re.findall(r"[一-鿿]", p))
    n_en = len(re.findall(r"[A-Za-z]+", p))
    if n_zh <= cap_zh and n_en <= cap_en:
        return ""
    return (f"提示词 {n_zh} 个汉字 / {n_en} 个英文词，官方建议中文 ≤{cap_zh} 字、"
            f"英文 ≤{cap_en} 词：字数过多容易信息分散，模型可能忽略部分细节。"
            "可以少选一两个人（或一两件东西），或分两条片子出。")
