"""P10 验收：第一期 P1（服装按人 / 道具清单 / H3 说话人）+ 界面契约/签名稳定。

零模型调用、不联网、不花钱。每条都按官方出处判，出处写进注释：
  A. 服装按人   —— 官方 2.5 示例「视频中深色衣服的男子的服饰替换为 @图片2」
  B. 道具清单   —— 官方 2.5「修改·对象」+ 逐人点名句式
  C. 说话人映射 —— H3 base-en:127（说话人才给号、跨镜头不变）、ref-en:258（<Subject N> (Sx)）
  E. 界面契约   —— 入口真的在页面上、真的进请求体；🩸 E5 守「画面内文字不许被加回来」
  F. 签名稳定   —— 空的新字段不许改变资产指纹（否则历史出片全部失配重画）

🩸 2026-10-23：原 D 组（画面内文字）随能力下线整个删除 —— 主人拍板不做
广告语/字幕/气泡，后端代码与界面入口都已清掉。

跑法：python scripts/p10_check.py --model volc20|volc25|h3
"""
from __future__ import annotations

import json
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import edit_spec, video_edit  # noqa: E402

FRONT = ROOT.parent / "frontend" / "app" / "src"

rows: list[tuple[str, bool, str]] = []

# 🚦 必须点名型号（2026-10-26）：一轮只跑一家。空串 = 还没解析。
SEL = ""


def chk(name: str, ok, detail: str = "") -> None:
    rows.append((name, bool(ok), detail if not ok else ""))


def spec_of(**change) -> dict:
    return edit_spec.normalize({"change": change, "audio": "tts"})


INV = {"people": [
    {"id": "P1", "desc_zh": "穿红裙的女生", "desc_en": "the woman in a red dress",
     "main": True, "appearances": [{"start": 0.0, "end": 5.0}]},
    {"id": "P2", "desc_zh": "穿蓝衬衫的男生", "desc_en": "the man in a blue shirt",
     "main": False, "appearances": [{"start": 3.0, "end": 5.0}]},
    {"id": "P3", "desc_zh": "路过的老人", "desc_en": "an elderly passer-by",
     "main": False, "appearances": [{"start": 5.0, "end": 6.0}]},
]}
D = video_edit.desc_by_id(INV)


def volc(spec, slots, **kw):
    return edit_spec.compile_prompt("volc", spec, model="doubao-seedance-2-5",
                                    slots=slots, desc_by_id=D, **kw)


def h3(spec, slots, **kw):
    return edit_spec.compile_prompt("minimax", spec, model="MiniMax-H3",
                                    slots=slots, desc_by_id=D, **kw)


# ---------------------------------------------------------------------------
# A. 服装按人
# ---------------------------------------------------------------------------

def phase_a() -> None:
    s = spec_of(wardrobe=True, wardrobe_ids=["P2", "P1", "P2"])
    ch = s["change"]
    chk("A1 换装名单去重且保序", ch["wardrobe_ids"] == ["P2", "P1"], str(ch["wardrobe_ids"]))
    chk("A2 每人一个槽位：wardrobe / wardrobe2 打开，wardrobe3 不打开",
        ch["wardrobe"] and ch["wardrobe2"] and not ch["wardrobe3"])

    order = [x for x, _ in edit_spec.ref_order(s)]
    chk("A3 图号顺序：wardrobe → wardrobe2", order == ["wardrobe", "wardrobe2"], str(order))

    if SEL == "volc25":
        p = volc(s, ["wardrobe", "wardrobe2"])
        # 官方 `sd25-guide:1209`「视频中深色衣服的男子的服饰替换为 @图片2，
        # 视频中浅色衣服的男子替换为 @图片3」—— 逐人一句、各绑各的图、动词「替换为」。
        chk("A4 火山：逐人一句、各绑各的图（官方 2.5 逐人点名句式）",
            "穿蓝衬衫的男生的服装替换为@图片1中的服装" in p
            and "穿红裙的女生的服装替换为@图片2中的服装" in p, p[:200])

    if SEL == "h3":
        # 🔓 2026-11-03 换体裁：改成手写入口。逐人换装句按官方 `h3-manual:213`
        #   「最左边小孩穿的卡其色外套改成图2中的牛仔外套」的形状写。
        # 🩸 必须喂 `source_people`：手写入口要靠盘点把「谁」说清楚
        #   （生产里 `work.py` 一直传盘点；不传就等于盘点失败，那种情况由
        #   G5/G6 两道闸拦住，不该在这里假装成功）。
        ppl_a = [dict(INV["people"][0], present=True),
                 dict(INV["people"][1], present=True)]
        m = h3(s, ["wardrobe", "wardrobe2"], source_people=ppl_a)
        chk("A5 H3：逐人一句、各绑各的图",
            "穿蓝衬衫的男生的服装改为@图片1中的服装。" in m
            and "穿红裙的女生的服装改为@图片2中的服装。" in m, m[:300])
        chk("A5b 逐条拼接不产生重复标点（。。 / ，，）",
            "。。" not in m and "，。" not in m, m[:200])

        # 同一次里既有换人又有换装：换装句必须还指认同一个人
        both = spec_of(person=True, person_ids=["P1"], wardrobe=True, wardrobe_ids=["P1"])
        m2 = h3(both, ["person", "wardrobe"], source_people=ppl_a)
        chk("A6 H3：换装句与换人句指同一个原片人物",
            "穿红裙的女生的服装改为@图片2中的服装。" in m2
            and "穿红裙的女生换成@图片1中的人物，" in m2, m2[:400])

    if SEL == "volc25":
        # 选了人却没给那张图：不能默默跳过（用户明确要求换他）。
        # 前端 `diagnose.vue:2802-2812` 提交前逐人查：没图那位必须**自己**写一句
        # 「换成什么」（`wardrobe_desc_by_id`）；全局 `wardrobe_desc` 只服务
        # "不点名 = 换全体"（`wrote == 0` 那一支，见 A8），不给第 2 个人当兜底。
        p3 = volc(spec_of(wardrobe=True, wardrobe_ids=["P1", "P2"],
                          wardrobe_desc_by_id={"P2": "米色风衣"}), ["wardrobe"])
        chk("A7 选了两个人只给一张图 → 没图那位写文字句，不静默丢",
            "穿红裙的女生的服装替换为@图片1中的服装" in p3
            and "穿蓝衬衫的男生的服装替换为米色风衣" in p3, p3[:200])

        old = volc(spec_of(wardrobe=True, wardrobe_desc="米色风衣"), ["wardrobe"])
        chk("A8 名单为空 = 老语义（一句话换全体）",
            "服装替换为@图片1中的服装" in old, old[:120])



# ---------------------------------------------------------------------------
# B. 产品 = 点名"画面里哪一件"（不新开入口，在原「产品」槽里做指定）
# ---------------------------------------------------------------------------

def phase_b() -> None:
    s = spec_of(product=True, product_desc="白色陶瓷杯",
                product_target="画面里那只蓝色马克杯",
                product_target_en="blue mug")
    ch = s["change"]
    chk("B1 定位词原样收下（中英各一份）",
        ch["product_target"] == "画面里那只蓝色马克杯"
        and ch["product_target_en"] == "blue mug", str(ch["product_target"]))
    off = spec_of(product=False, product_target="蓝色马克杯")
    chk("B2 没勾「换产品」就把定位词清掉（别指到上一次那件）",
        off["change"]["product_target"] == "", str(off["change"]["product_target"]))

    if SEL == "volc25":
        p = volc(s, ["product"])
        chk("B3 火山：点名画面里哪一件（官方句式「把<原对象>替换为<目标>」）",
            "画面里那只蓝色马克杯替换为@图片1中的产品" in p, p[:160])

        p2 = volc(spec_of(product=True, product_desc="白色陶瓷杯"), ["product"])
        # 🩸 2026-10-23 改：官方 <原对象> 不带 @视频1（`sd25-pe:561`）。
        chk("B4 没点名时退回老句式（行为不变）",
            "只把产品替换为@图片1中的产品" in p2, p2[:160])

    if SEL == "h3":
        # 官方 `h3-manual:234`「将视频开头出现的易拉罐饮料替换为可口可乐」——
        # 定位词在前、目标在后。用户填的定位词自带「画面里那只」时不再叠
        # 「@视频1中的」，否则指代打两遍（「@视频1中的画面里那只…」）。
        m = h3(s, ["product"])
        chk("B5 H3：点名原片里哪一件（h3-manual:234）",
            "把画面里那只蓝色马克杯替换为白色陶瓷杯。" in m, m[:400])
        chk("B5b 定位词自带「画面」时不再叠 @视频1中的",
            "@视频1中的画面" not in m, m[:300])



# ---------------------------------------------------------------------------
# C. 说话人映射（H3）
# ---------------------------------------------------------------------------

def phase_c() -> None:
    s = spec_of(person=True, person_ids=["P1", "P2"],
                speaker_ids=["P2", "P1", "P2"])
    chk("C1 说话人名单去重保序", s["change"]["speaker_ids"] == ["P2", "P1"],
        str(s["change"]["speaker_ids"]))

    # 只换衣服时也要能指定谁在说话（说话人不一定是被换的人）
    w = spec_of(wardrobe=True, wardrobe_ids=["P1"], speaker_ids=["P2"])
    chk("C2 说话人不要求在换人名单里（官方 base-en:127）",
        w["change"]["speaker_ids"] == ["P2"], str(w["change"]["speaker_ids"]))

    # C3 起全部是 H3 的断言：只在 H3 轮跑。
    if SEL != "h3":
        return
    ppl = [dict(INV["people"][0], present=True), dict(INV["people"][1], present=True)]
    m = h3(s, ["person", "person2"], audio_ref=True, source_people=ppl)

    # 🔓 2026-11-03 换体裁 + 主人拍板「**让模型沿用原声**」：
    # H3 复刻的音频走官方 `h3-manual:248` 的「音频复用（生成视频的音频直接复用
    # 参考音频素材）」—— 没有「把某一副音色绑到某个主体」这套写法。
    # 旧 C3–C9 验的是六段式 `<Audio 1> … for <Subject N> (Sx)`，手写入口手册里
    # 没有对应句式（`base-en:127` 的 (Sx) 只属于**三字段创作模式**，那是提示词优化
    # 那条线，`h3_base.py B17` 还在守）。所以这一组改成守「复用原声」+ 不许回流。
    # 🩸 2026-11-04 改断言：括号里改回 `:248` 用途表**原词**
    #   「音频复用（生成视频的音频直接复用**参考音频素材**）」。
    #   旧断言写的是「直接复用@音频1」—— 那是把官方原词里的"参考音频素材"
    #   换成了图号引用，`@音频1` 在整行开头已经出现过，等于同一处指代写两遍。
    chk("C3 有音频复用用途句（h3-manual:248 原词）",
        "@音频1：音频复用素材（生成视频的音频直接复用参考音频素材）" in m, m[:600])
    chk("C4 不写 (Sx) 说话人编号（手写入口没有这套）",
        "(S1)" not in m and "(S2)" not in m, m[:400])
    chk("C5 不写六段式 <Audio N> 标号", "<Audio 1>" not in m, m[:300])

    # 没传音轨（保留原声但不复用音频素材）：不许出现 @音频1
    m2 = h3(s, ["person", "person2"], audio_ref=False, source_people=ppl)
    chk("C6 没传音轨就不写 @音频1", "@音频1" not in m2, m2[:300])

    # 两个人各一张图、各有用途句（图号不串）
    chk("C7 两个人都换了 → 两张图各有用途句",
        m.count("：人物参考") == 2, m[:400])

    # 没传音轨时也不许冒出 (Sx) 编号
    m4 = m2
    chk("C8 没传音轨就不写 <Audio 1> / (Sx)",
        "<Audio 1>" not in m4 and "(S1)" not in m4, m4[:300])

    chk("C9 不往后瞎编说话人号（没有 (S3)）",
        "(S3)" not in m, m[:400])

    # ---------------------------------------------------------------- 镜头结构
    # 🩸 2026-11-04：官方 `:251`「按时间轴或故事线分段写…**以切镜 shot 作为时间戳
    #   的分段**」+ `:250`「**默认会切镜**」（不写切点模型自己编）+ `:266`「不要切镜」。
    #   实测 `de591f35`：源片 2 镜 → 成片 3 镜，多出来的 4.0s 切到了参考图的庭院。
    #   三种输入必须产出三种结果，缺一种就等于"不知道"被当成"一镜到底"。
    m5 = h3(s, ["person", "person2"], shot_cuts=[3.33], source_people=ppl)
    # 🩸 v7 `67285c2f` 是本任务目前最接近成功的一版（衣服/发型全换、背景全程留在
    #   厨房、脸部分帧换）→ 下面这些按 v7 的实际行为锁。v8 把用途句描述砍到只剩脸
    #   = **完全不换**，所以"少写"这条路已被证否。
    _one_shot = [{"start": 0.0, "end": 5.3, "en": "Medium full shot, two women dance."}]
    m5 = h3(s, ["person", "person2"], shot_cuts=[3.33], shot_desc=_one_shot,
            source_people=ppl)
    chk("C10 有切镜点 → 时间轴写景别 + 全片规则挂 ▍镜头（h3-manual:251）",
        "0-5.3 秒：Medium full shot。" in m5 and "▍镜头（贯穿全片）" in m5
        and "镜头节奏" in m5, m5[-300:])
    m6 = h3(s, ["person", "person2"], shot_cuts=[], source_people=ppl)
    chk("C11 确定一镜到底 → 写「不要切镜」（h3-manual:266）",
        "不要切镜" in m6, m6[-300:])
    m7 = h3(s, ["person", "person2"], shot_cuts=None, source_people=ppl)
    chk("C12 不知道有没有切镜 → 一个字不写（不许瞎猜）",
        "切镜" not in m7, m7[-300:])

    _one = [{"start": 0.0, "end": 5.3,
             "en": "Medium full shot, two aproned women dance, camera slowly pulls back."}]
    m8 = h3(s, ["person", "person2"], shot_cuts=[3.33], shot_desc=_one, source_people=ppl)
    # 只取景别：整句搬会带 `two aproned women` —— 那是原片的人，和「换成@图片N中的人物」
    # 正面打架（`74d65218` 实测整片照抄原片）。运镜也不取（样本里会误认内容）。
    chk("C13 单镜盘点 → 只写景别，不带人物也不带运镜",
        "0-5.3 秒：Medium full shot。" in m8
        and "aproned" not in m8 and "pulls back" not in m8, m8[-400:])
    _two = [{"start": 0.0, "end": 2.8, "en": "Medium shot, a man walks."},
            {"start": 2.8, "end": 5.4, "en": "Close-up, a woman smiles."}]
    m9 = h3(s, ["person", "person2"], shot_cuts=[2.8], shot_desc=_two, source_people=ppl)
    chk("C14 多镜盘点 → 按它自己的时间戳逐段写景别（h3-manual:260）",
        "0-2.8 秒：Medium shot。" in m9
        and "2.8-5.4 秒：切镜到Close-up，主体仍是@图片1、@图片2中的人物。" in m9
        and "a man walks" not in m9, m9[-500:])
    m10 = h3(s, ["person", "person2"], shot_cuts=[2.8], shot_desc=[], source_people=ppl)
    chk("C15 盘点没有镜头内容 → 不写空壳",
        "原片画面" not in m10 and "秒：" not in m10, m10[-300:])
    _one_cut = [{"start": 0.0, "end": 5.3, "en": "Medium full shot, two women dance."}]
    m11 = h3(s, ["person", "person2"], shot_cuts=[3.33], shot_desc=_one_cut,
             source_people=ppl)
    chk("C16 盘点只有 1 个 shot → 不补切点、不编第二镜景别",
        "0-5.3 秒：Medium full shot。" in m11
        and "切镜" not in m11, m11[-400:])
    # :284/:285 的分组写法：全片规则单列 `▍组名（贯穿全片）`，不混进时间轴。
    chk("C17 跨全片的规则单列【整体要求补充】+ ▍分组（h3-manual:284/:285）",
        "【整体要求补充】" in m11 and "▍" in m11 and "（贯穿全片）" in m11,
        m11[-500:])
# ---------------------------------------------------------------------------
# E. 界面契约
# ---------------------------------------------------------------------------

def phase_e() -> None:
    vue = (FRONT / "pages" / "clone" / "diagnose.vue").read_text(encoding="utf-8")
    chk("E1 请求体带 wardrobe_ids / speaker_ids / product_target",
        all(k in vue for k in ("wardrobe_ids: []", "speaker_ids: []",
                               "product_target: ''")))
    chk("E2 换装逐人上传（每个人一个槽位）",
        "wardrobeRows" in vue and "wardrobe${i + 1}" in vue)
    # 🩸 主人 2026-10-22：「产品」那一行已经写着换商品/换道具，再开一个「道具」入口
    # 就是多此一举。改成在原入口里点名"换画面里哪一件"，并把重复入口删干净。
    chk("E3 没有重复的「道具 / 配饰」入口（在原「产品」槽里做指定）",
        "道具 / 配饰" not in vue and "pickProduct" in vue
        and "换画面里的哪一件" in vue)
    chk("E4 说话人入口只在 MiniMax 下出现",
        "effChannel === 'minimax'" in vue and "pickSpeaker" in vue)
    # 🩸 2026-10-23 主人拍板：画面内文字（广告语/字幕/气泡）整个能力下线，
    # 界面和后端都不再有它。这里守的是"别再被人加回来"。
    chk("E5 界面上没有「画面内文字」入口（能力已下线）",
        "画面内文字" not in vue and "on_screen_text" not in vue)

    # 后端真的收得下：接口的 edit 字段直接过 normalize，不需要额外白名单
    api = (ROOT / "app" / "api" / "clone.py").read_text(encoding="utf-8")
    chk("E6 接口层用 normalize 收规格（新字段不用另开白名单）",
        "edit_spec.normalize" in api)

    # 🩸 删行后槽位会顺移：必须能把受影响的图清掉，否则「第 3 件的包」顶到第 2 格
    chk("E7 有删参考图的接口（删行时清掉错位的图）",
        '@router.delete("/clone/{cid}/ref/{slot}")' in api)
    req = (FRONT / "api" / "request.js").read_text(encoding="utf-8")
    chk("E8 前端换装删人时调删除接口（图跟着人走，不许错位）",
        "cloneDeleteRef" in req and vue.count("clearRefSlots(") >= 2,
        str(vue.count("clearRefSlots(")))


# ---------------------------------------------------------------------------
# F. 签名稳定
# ---------------------------------------------------------------------------

def phase_f() -> None:
    old = {"person": True, "person_id": "P1", "person_desc": "",
           "product": False, "scene": False, "wardrobe": False,
           "product_desc": "", "scene_desc": "", "wardrobe_desc": "", "style": ""}
    new = edit_spec.normalize({"change": dict(old), "audio": "tts"})["change"]
    chk("F1 空的新字段不改变签名（老出片还能复用）",
        edit_spec.sig_change(old) == edit_spec.sig_change(new),
        f"{edit_spec.sig_change(old)} vs {edit_spec.sig_change(new)}")

    withv = edit_spec.normalize({"change": dict(old, wardrobe=True,
                                                wardrobe_ids=["P1"])})["change"]
    chk("F2 有新内容时签名必须变（不能假复用）",
        edit_spec.sig_change(old) != edit_spec.sig_change(withv))

    chk("F3 空 prop 槽位不进签名",
        "prop" not in edit_spec.sig_change(
            edit_spec.normalize({"change": dict(old)})["change"]))


# ---------------------------------------------------------------------------
# G. 只换衣服/道具也要逐段分诊（点名的人不在这一段 → 留原片，不白花钱）
# ---------------------------------------------------------------------------

def phase_g() -> None:
    inv = {"people": [
        {"id": "P1", "desc_zh": "穿红裙的女生", "desc_en": "the woman in a red dress",
         "main": True, "appearances": [{"start": 0.0, "end": 3.0}]},
        {"id": "P2", "desc_zh": "穿蓝衬衫的男生", "desc_en": "the man in a blue shirt",
         "main": False, "appearances": [{"start": 6.0, "end": 9.0}]},
    ], "products": [], "scenes": []}
    spans = [(0.0, 3.0), (6.0, 9.0)]

    def plan_of(**change):
        sp = spec_of(**change)
        sp["audio"] = "original"   # 只有保留原声才允许整段留原片
        return {"spec": sp, "inventory": inv, "person_ids": [],
                "ch": "volc", "model": "doubao-seedance-2-5", "person_asset": "",
                "audio_ref": False, "prompt": "占位", "slots": ["wardrobe"]}

    acts = video_edit._span_plan(plan_of(wardrobe=True, wardrobe_ids=["P1"]), spans)
    chk("G1 只换 P1 的衣服：P1 那段要改，另一段留原片",
        acts[spans[0]][0] == "change" and acts[spans[1]][0] == "keep",
        str({k: v[0] for k, v in acts.items()}))

    acts2 = video_edit._span_plan(plan_of(wardrobe=True), spans)
    chk("G2 换装名单为空（全体一起换）→ 不分诊，整片套用同一句（空字典 = 老路径）",
        acts2 == {}, str(acts2))

    bad = plan_of(wardrobe=True, wardrobe_ids=["P9"])
    try:
        video_edit._span_plan(bad, spans)
        ok, msg = False, "没有报错"
    except video_edit.EditError as e:  # noqa: PERF203
        ok, msg = "P9" in str(e), str(e)[:60]
    chk("G5 点名的人盘点里没有 → 出片前拦住，不硬换", ok, msg)

    # 🩸 G6/G7（2026-10-26 D36）：盘点**一个人都没识别到**（people=[]）时——
    # 以前 `not inv.get("people")` 先 `return {}`，把"点名"整个挡在后面：
    # 点名换装 P1 会被降级成**全体换装**，点名换人靠「其中的人物」碰运气。
    # 现在点名优先：点名的必须拦住；**没点名的（全体换装）不许被误伤**。
    empty_inv = {"people": [], "products": [], "scenes": []}

    def plan_empty(**change):
        sp = spec_of(**change)
        sp["audio"] = "original"
        return {"spec": sp, "inventory": empty_inv, "person_ids": [],
                "ch": "volc", "model": "doubao-seedance-2-5", "person_asset": "",
                "audio_ref": False, "prompt": "占位", "slots": ["person"]}

    for label, change in (("点名换装 P1", dict(wardrobe=True, wardrobe_ids=["P1"])),
                          ("点名换人 P1", dict(person=True, person_ids=["P1"]))):
        try:
            video_edit._span_plan(plan_empty(**change), spans)
            chk(f"G6 盘点零人 + {label} → 出片前拦住", False,
                "没报错：点名会被降级成「全体/其中的人物」")
        except video_edit.EditError as e:
            chk(f"G6 盘点零人 + {label} → 出片前拦住", "P1" in str(e), str(e)[:60])

    acts3 = video_edit._span_plan(plan_empty(wardrobe=True), spans)
    chk("G7 盘点零人 + 换装**不点名**（全体）→ 仍走老路径，不许误伤",
        acts3 == {}, str(acts3))


# ---------------------------------------------------------------------------

def main() -> int:
    global SEL
    from _model_gate import sel_or_exit
    SEL = sel_or_exit()

    for fn in (phase_a, phase_b, phase_c, phase_e, phase_f, phase_g):
        fn()

    ok = sum(1 for _, v, _ in rows if v)
    for name, v, detail in rows:
        print(f"  {'ok  ' if v else 'FAIL'} {name}" + (f"  [{detail[:180]}]" if detail else ""))
    print(f"\n{ok}/{len(rows)} 通过（零模型调用）")
    return 0 if ok == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
