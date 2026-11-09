"""「选了哪个型号，就按哪个型号的官方标准执行」——逐型号自检（零模型调用）。

为什么单独一条判据：2026-10-22 那次换人失败，根因不是素材也不是接口，
而是**一句提示词写法被所有型号共用**（把原片人物的衣服写进替换句），
结果 2.0 上只换了衣服、脸没换（SFace：与原片同人 49/56、与参考图 0/65）。
主人当天的口径：**顾客选了模型，就要按那个模型的标准去执行**。

本脚本把这件事变成可执行的判据：同一套规格分别编译给每个型号，
逐个断言「这个型号**必须**有什么」「**不许**有什么」。出处都写在注释里：
  - 2.0：sd2-pe（严格编辑句式 / 稳定包+水印兜底 / 双胞胎兜底 / 负向域）
  - 2.5：sd25-pe（编辑句式 / 「只把」范围限定 / 原则 8 不许自动加负向）
  - H3 ：h3-prompt-writing Ref2VA 六段式（<Subject N> / <Picture N>）
  - 请求体：2.5 才有 omni_reference_task_type=edit、duration=-1；
           2.0 无该字段、duration 给具体秒数（上限按型号）

跑法：python scripts/prompt_model_standards_check.py --model volc20|volc25|h3
"""
from __future__ import annotations

import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import ark, edit_spec  # noqa: E402

rows: list[tuple[str, bool, str]] = []
V20 = ["doubao-seedance-2-0-260128", "doubao-seedance-2-0-fast-260128",
       "doubao-seedance-2-0-mini-260615"]
V25 = "doubao-seedance-2-5-260628"
H3 = "MiniMax-H3"

SPEC = edit_spec.normalize({
    "change": {
        "person": True, "product": True, "scene": True, "wardrobe": True,
        "person_ids": ["P1"], "person_desc": "",
        "product_target": "蓝色马克杯", "product_target_en": "the blue mug",
        "scene_desc": "", "wardrobe_desc": "",
    },
    "audio": "tts",
})
PRODUCT = ["person", "product", "scene", "wardrobe"]
PEOPLE = [{"id": "P1", "desc_zh": "穿红裙的女生", "desc_en": "the woman in red",
           "present": True}]
DESC = {"P1": {"zh": "穿红裙的女生", "en": "the woman in red"}}


def chk(name: str, ok, detail: str = "") -> None:
    rows.append((name, bool(ok), detail if not ok else ""))


def prompt(model: str) -> str:
    ch = "minimax" if model.startswith("MiniMax") else "volc"
    return edit_spec.compile_prompt(
        ch, SPEC, model=model, source_people=PEOPLE, slots=PRODUCT,
        desc_by_id=DESC, audio_ref=True)


def body(model: str, *, duration: float = 8.0) -> dict:
    return ark.edit_body(
        "严格编辑@视频1，把@视频1中的人物修改为@图片1中的人物",
        video_url="https://x/a.mp4", ref_images=["asset://a1"],
        model=model, duration=duration)


def phase_20() -> None:
    for m in V20:
        p = prompt(m)
        tag = m.replace("doubao-seedance-", "")
        # 2.0 官方编辑句式：「严格编辑@视频N，将其中的<原特征>修改为<新特征>」。
        # 🩸 有音频参考时，官方**组合任务**公式（`seedance-20-guide.md:65`）要求
        # 在编辑句前面加「参考<…>的[参考维度]，」—— 参考维度取音频参考那一行
        # （同文件 :28「参考<音频N>中的音色」）。两种开头都合规。
        # 🩸 2026-10-30：官方 `sd20-guide:59-65` 的组合任务句式允许「参考@素材」
        #   分句排在「严格编辑」**之前**（参考维度：音频音色 / 图的面部特征与妆造）。
        #   要守的不变式是「编辑句以严格编辑@视频1起头」，而不是"整条提示词第一句"。
        chk(f"[{tag}] 2.0 编辑句以「严格编辑@视频1」起头（参考分句可在其前）",
            "严格编辑@视频1" in p, p[:60])
        # 2.0 官方「强制约束」：稳定包 + 水印/Logo 兜底
        chk(f"[{tag}] 2.0 挂稳定包+水印兜底", "不要生成水印" in p)
        # 🩸 D6（2026-10-23）：本夹具是**单人**换人。官方是
        # `sd2-pe:101`「多人场景**必挂**」、`:162`「多人 / 多主体场景必挂」——
        # 单人画面没有第二张脸可撞，不该挂。多人那条在下面单独验。
        chk(f"[{tag}] 2.0 单人换人不挂双胞胎兜底", "双胞胎" not in p)
        # 🩸 2026-10-23：「不要恢复原片人物的脸」出处是第三方 ReplicaPilot，
        # sd2-pe 里没有这条负向域 → 已删除。断言改成"不许回来"。
        chk(f"[{tag}] 2.0 不写第三方换人负向",
            "不要恢复原片人物的脸" not in p)
        # 2.5 专属的「只把」范围限定词，2.0 不该带
        chk(f"[{tag}] 2.0 不带 2.5 专属的「只把…」", "只把" not in p)
        common(tag, p)
        # D6 的另一半：**多人**换人必须挂（sd2-pe:101/:162）
        ppl2 = [{"id": "P1", "desc_zh": "穿红裙的女生", "desc_en": "the woman in red",
                 "present": True},
                {"id": "P2", "desc_zh": "穿蓝衬衫的男生", "desc_en": "the man in blue",
                 "present": True}]
        multi = edit_spec.normalize({"person": True, "person_ids": ["P1", "P2"]})
        pm = edit_spec.compile_prompt("volc", multi, model=m, source_people=ppl2,
                                      slots=["person", "person2"])
        chk(f"[{tag}] 2.0 多人换人挂双胞胎兜底", "双胞胎" in pm, pm[:120])
        # 请求体：2.0 无任务类型字段，duration 给具体秒数
        b = body(m)
        chk(f"[{tag}] 请求体没有 omni_reference_task_type",
            "omni_reference_task_type" not in b)
        chk(f"[{tag}] 请求体 duration 是具体秒数", isinstance(b.get("duration"), int)
            and b["duration"] >= 4, str(b.get("duration")))
        chk(f"[{tag}] 请求体 ratio=adaptive", b.get("ratio") == "adaptive")


def phase_25() -> None:
    p = prompt(V25)
    # 2.5 官方模板：sd25-pe:71 原则 2「模板优先」+ :559「视频编辑模板」五段，
    # 编辑句落在【编辑目标】段里，不是裸开头（2.0 才是一段式裸开头）。
    chk("2.5 以【编辑目标】开头（官方五段模板）", p.startswith("【编辑目标】"), p[:20])
    chk("2.5 编辑句在目标段里", "编辑@视频1，" in p.split("【原视频职责】")[0], p[:80])
    chk("2.5 补齐五段", all(k in p for k in (
        "【编辑目标】", "【原视频职责】", "【目标素材职责】",
        "【编辑对象与范围】", "【时间线继承】")), p[:200])
    chk("2.5 带「只把」范围限定词", "只把" in p)
    # 2.5 原则 8：不得自动加 2.0 那套稳定包/水印/分身/负向
    for bad, label in (("不要生成水印", "稳定包/水印兜底"),
                       ("双胞胎", "双胞胎兜底"),
                       ("不要恢复原片人物的脸", "换人负向")):
        chk(f"2.5 不自动加 2.0 的{label}", bad not in p)
    common("2.5", p)
    b = body(V25)
    chk("2.5 请求体有 omni_reference_task_type=edit",
        b.get("omni_reference_task_type") == "edit")
    chk("2.5 请求体 duration=-1（编辑任务官方硬要求）", b.get("duration") == -1)
    chk("2.5 请求体 ratio=adaptive", b.get("ratio") == "adaptive")


def phase_h3() -> None:
    """H3 复刻 = **手写入口三段式**（`h3-manual:244`）。

    🔓 2026-11-03 换体裁：旧断言锁的是 Ref2VA 六段式（`<Subject N> is the person
    in <Picture N>`）。官方换人样例 6 条**全在手册**、六段式里 0 条 —— 体裁换了，
    断言必须跟着换（`spec-must-match-genre`），否则守的就是一条不存在的规则。
    """
    p = prompt(H3)
    chk("H3 用官方「参考素材说明」段（h3-manual:244）",
        "【参考素材说明】" in p, p[:120])
    # 官方 `:248` 的标法就是 @图片N / @视频N / @音频N（手册示例逐字）。
    chk("H3 用官方 @图片N / @视频N 标法（h3-manual:248）",
        "@图片1" in p and "@视频1" in p, p[:160])
    chk("H3 不回流六段式标号（<Picture/<Subject）",
        "<Picture" not in p and "<Subject" not in p, p[:160])
    chk("H3 不写六段式字段名",
        "subject_definitions" not in p and "retention_analysis" not in p, p[:160])
    # 🩸 2026-11-04：改成 `h3-manual:284` 实际范例的冒号式 `@图片N：用途（…）`。
    chk("每张图都有用途句（h3-manual:248 + :284 冒号式）",
        all(f"@图片{i}：" in p for i in range(1, len(PRODUCT) + 1)), p[:200])
    # 「不是他的就不要串啊」：别家模板句不许混进来
    for w in ("唯一编辑母版", "其他人物、道具和背景保持原样", "色调和光线方向"):
        chk(f"H3 不串别家句「{w}」", w not in p, p[:160])


def phase_h3_boundary() -> None:
    """分段续接：上一段尾帧必须按官方**「关键帧」**写。

    依据：`h3-manual:248` 用途表「关键帧（锁定帧，如果有首帧尾帧需求明确提出）」；
    `:266` 示例「@图片1 是首帧参考图：…」。旧 Ref2VA 写法是
    `<Picture 5> is the first frame of the target video` —— 那套字段今天已经不存在了。
    """
    p = edit_spec.compile_prompt(
        "minimax", SPEC, model=H3, source_people=PEOPLE, slots=PRODUCT,
        desc_by_id=DESC, audio_ref=True, boundary_pic=5)
    chk("边界帧有用途句「关键帧」（h3-manual:248 + :284 冒号式）",
        "@图片5：关键帧（锁定帧）" in p, p[:300])
    chk("正文先说从这一帧开始（h3-manual:266 排布）",
        "画面从@图片5定义的首帧自然开始。" in p, p[:300])
    # 🩸 2026-11-04：正文拆成 `h3-manual:244` 的三段后，续接句属于
    #   `【画面过程说明】`（"画面怎么走"从第一帧开始）。判据跟着改成
    #   「在本段最前、且在两条保持句之前」，不再要求它跑到【核心创意】前面 ——
    #   那是旧的一段式排布，官方三段公式里没有这个顺序要求。
    chk("续接句在【画面过程说明】里、且排在本段最前",
        "【画面过程说明】" in p
        and p.index("【画面过程说明】")
        < p.index("画面从@图片5定义的首帧自然开始。")
        < p.index("替换后的人物必须严格遵循"), p[:300])
    # 反证：没有边界帧时不许凭空出现关键帧句
    p0 = prompt(H3)
    chk("没有边界帧就不写关键帧句",
        "关键帧" not in p0 and "首帧自然开始" not in p0, p0[:200])


def common(tag: str, p: str) -> None:
    """所有型号共同的标准（官方两份指南都写了）。"""
    _is25 = tag.startswith("2.5") or tag.startswith("2-5")
    # 官方：编辑任务直接写 <视频N>，别写「参考<视频N>」否则被判成参考任务
    chk(f"[{tag}] 不写「参考@视频1」（会被判成参考任务）",
        "参考@视频1" not in p and "参考视频1" not in p)
    # 🩸 原对象怎么指代，两家官方句式**不一样**（2026-10-23）：
    #   · 2.0 `sd2-pe:126`「严格编辑 @视频1，**将其中的**香水替换为 @图片1 中的面霜」
    #   · 2.5 `sd25-pe:600`「**只把**经过长椅前方的红色自行车和骑行者替换为 @图片1 中的…」
    # 以前两边共用一个「把@视频1中…」，2.0 那句既不是官方写法、又多重复一次 @视频1。
    if _is25:
        # 🩸 2026-10-23 改：官方 <原对象> **不带** @视频1（`sd25-pe:561` 模板
        # `编辑@视频1，只把<原对象或区域>替换为<目标内容>`、`:584` 示例）。
        # 原断言写的是「把@视频1中的人物…」，把官方没有的前缀锁成了标准 ——
        # 这条判据过期，不是产品回退。
        # 🩸 2026-10-28 撤回：「修改为」只在占位模板 `:561`，官方所有已填
        #   替换示例都是「替换为」（`:584` `:602` `sd25-guide:1205-1209`）。
        chk(f"[{tag}] 换人句用 2.5 句式（只把X替换为…）",
            "只把人物替换为@图片1中的人物" in p, p[:120])
        chk(f"[{tag}] 不带 2.0 的「将其中的」", "将其中的" not in p, p[:120])
        chk(f"[{tag}] 原对象前不带 @视频1", "把@视频1中" not in p, p[:120])
    else:
        # 🩸 2026-10-30 撤回同一轮的两次尝试，回到官方 `sd2-pe:126` 原句式：
        #   ① 「完整替换 + 使用目标人物的脸、发型、体型、服装和配饰」——
        #      出处是 `las_cn.md:405`，那是 **LAS 算子**的 `user_prompt`（服务端
        #      还要再做 VLM/关键帧重绘/提示词组装），不是 Seedance 原生提示词；
        #      原生提示词里没有这个示例。搬过来属于跨链路。
        #   ② 本次真机（`6d26558d` / `ff561d97`）加了它仍然是 not_swapped。
        chk(f"[{tag}] 换人句用 2.0 句式（将其中的X…）",
            "将其中的人物替换为@图片1中的人物" in p, p[:120])
        # 🩸 2026-11-04 晚：**恢复**（当天上午随句停用，判断过头了）。
        #   职责句（面部特征/妆造）必须以「参考@图…」开头、排在「严格编辑」之前
        #   （官方 `sd20-guide:59-65` 组合任务句式）。
        #   句子的出处见 `volc20_compile.person_duty` 的注释：
        #   `prompt-guide.md:317` 原句 + `SKILL.md:121` 路径 A 公式的
        #   「[主体与素材绑定]」槽。
        # 🩸 2026-11-05 晚：断言同步到实现（见 `volc20_compile.person_duty`
        #   注释里的实测定案）—— 带「中人物的」那版 `20e6b5d0` 出片人换了但脸
        #   不像任何人，已回滚；`ef232fc6`（343 字，2 人全换，主人确认「通了」）
        #   与官方 `sd20-guide:59-65`「参考<图片N>的[参考维度]」都是无「中」写法。
        chk(f"[{tag}] 图职责句前置成「参考@图片N的面部特征和妆造」",
            "参考@图片1的面部特征和妆造" in p, p[:160])
        _pre = p.split("严格编辑@视频1")[0] if "严格编辑@视频1" in p else p
        chk(f"[{tag}] 所有「参考@图N」都在「严格编辑」之前",
            "参考@图片1的面部特征和妆造" in _pre, p[:160])
        chk(f"[{tag}] 不带 2.5 的「把@视频1中…」",
            "把@视频1中的人物" not in p, p[:120])
    # 🩸 单人画面不许把原片人物的衣服写进替换句（2026-10-22 只换衣服的根因）
    chk(f"[{tag}] 单人画面不把原片衣服写进替换句",
        "穿红裙的女生" not in p, p[:160])
    # 🩸 范围闭环是 **2.5 视频编辑模板**的结构件（sd25-pe:550/554）。
    # 2.0 **不写**：官方《Seedance 2.0 提示词指南》§「编辑视频」
    # 「未提及的部分，默认保持不变」——默认行为不用再声明一遍。
    if _is25:
        chk(f"[{tag}] 有范围闭环句（2.5 模板件）", "除以上明确修改对象外" in p)
    else:
        chk(f"[{tag}] 不写范围闭环（官方默认保持不变）",
            "除以上明确修改对象外" not in p)


def phase_scene_and_defs(sel: str) -> None:
    """换场景 vs 保持背景（互斥）、每张参考图都要有定义、定位词不许重复冠词。

    这些断言全部落在 H3 的六段式上（`compile_prompt("minimax", …)`），只在 H3 轮跑。
    """
    if sel != "h3":
        return
    # 🩸 2026-10-22 实测 e6bfd247：change.scene=true 时 keep.background 仍是 true，
    # 提示词里同时出现「background replaced by <Subject 3>」和「background environment
    # … follow <Video 1>」→ 成片背景在 5.42s / 12.25s 两次硬切回原片（原片本身无切点）。
    s = edit_spec.normalize({"change": {"scene": True},
                             "keep": {"background": True}})
    chk("换场景时强制关掉「保持背景」", s["keep"]["background"] is False)
    p = edit_spec.compile_prompt("minimax", s, model=H3, slots=["scene"])
    chk("换场景后提示词不再说背景照原片",
        "背景保持原样" not in p and "background environment" not in p, p[:200])
    # 手写入口没有单独的「保留句」，换场景就只写一句换背景
    # （官方 `h3-manual:221`「视频1窗外的场景改成图1」），不许再补别家的闭环句。
    chk("换场景句有落点（h3-manual:221）",
        "背景场景替换为" in p, p[:200])
    chk("换场景不串别家的范围闭环句",
        "除以上明确修改对象外" not in p and "people and props remain unchanged" not in p,
        p[:200])
    s2 = edit_spec.normalize({"change": {"scene": False}})
    chk("不换场景时背景照旧保持", s2["keep"]["background"] is True)

    # 每张参考图都要有用途句（官方 `h3-manual:248`「写清每个素材的用途」）。
    # 🩸 号不能写死：从槽位表反查（全换时服装是第 4 张）。
    p3 = prompt(H3)
    _want_pic = edit_spec.image_index(PRODUCT)["wardrobe"]
    chk("服装图有用途句",
        f"@图片{_want_pic}：物体参考（锁定服装）" in p3, p3[:400])

    # 产品定位词用中文 `product_target`（手写入口是中文正文，不拼英文定位词）
    s4 = edit_spec.normalize({"change": {"product": True,
                                         "product_target": "蓝色马克杯"}})
    p4 = edit_spec.compile_prompt("minimax", s4, model=H3, slots=["product"])
    chk("产品定位词不会出现 the the", "the the" not in p4, p4[:200])
    chk("定位词仍然保留", "蓝色马克杯" in p4, p4[:200])


def phase_positions(sel: str) -> None:
    """多人换人：方位必须按**各家官方写法**写出来（D1，2026-10-23）。

    出处：
      · 火山 `sd2-pe:72` 把"多人未指明谁在左/右"列为病灶，`:153` 写法
        `@图片2 中的女生位于画面左侧`；
      · MiniMax `ref-en:246`「describe its … position in the frame」，
        `:330` 示例 `From the left, <Subject 4>, the young man with …`；
      · 静帧重绘（Seedream）多人融合示例靠外观/位置定位。
    🩸 方位来自盘点 `position` 字段；单人画面**不许写**（会把人钉死在某一侧）。
    """
    s = edit_spec.normalize({"person": True, "person2": True})
    slots = ["person", "person2"]
    ppl = [{"id": "P1", "present": True, "position": "left",
            "desc_zh": "穿蓝衣的男人", "desc_en": "the man in a blue shirt"},
           {"id": "P2", "present": True, "position": "right",
            "desc_zh": "戴帽子的女人", "desc_en": "the woman in a hat"}]
    d = {p["id"]: {"zh": p["desc_zh"], "en": p["desc_en"]} for p in ppl}

    if sel == "volc20":
        p20 = edit_spec.compile_prompt("volc", s, model=V20[0], slots=slots,
                                       source_people=ppl, desc_by_id=d)
        # 🩸 2026-11-05 主人拍板：`<原特征>` = **方位 + 类别词**（官方 `SD20-skill:153`）。
        # 方位唯一时写方位 + 人称词，**不写外观**（外观会被模型照着画回去）。
        chk("2.0 方位唯一 → 方位+类别词、不写外观（sd2-pe:153）",
            "画面左侧的男人" in p20 and "画面右侧的女人" in p20
            and "穿蓝衣" not in p20 and "戴帽子" not in p20, p20[:160])
        # 兜底档：描述一模一样 ⇒ 特征指认不了，方位**必须**写（官方 `:153`）
        same20 = "留短黑发的男性"
        ppl20 = [dict(p, desc_zh=same20) for p in ppl]
        d20 = {p["id"]: {"zh": same20, "en": p["desc_en"]} for p in ppl20}
        p20b = edit_spec.compile_prompt("volc", s, model=V20[0], slots=slots,
                                        source_people=ppl20, desc_by_id=d20)
        chk("2.0 特征不可分 → 方位兜底（sd2-pe:153）",
            "画面左侧" in p20b and "画面右侧" in p20b, p20b[:160])
    elif sel == "volc25":
        p25 = edit_spec.compile_prompt("volc", s, model=V25, slots=slots,
                                       source_people=ppl, desc_by_id=d)
        chk("2.5 多人写方位（<原对象>要具体）",
            "画面左侧" in p25 and "画面右侧" in p25, p25[:160])
    else:
        ph3 = edit_spec.compile_prompt("minimax", s, model=H3, slots=slots,
                                       source_people=ppl, desc_by_id=d)
        # 官方 `h3-manual:248`「如果有多个角色，**需要能指代清楚**」；
        # `:213` 官方的指代写法就是方位（「最左边小孩」），所以中文正文用「画面左侧」。
        chk("H3 多人写方位（h3-manual:248 / :213）",
            "画面左侧的人物" in ph3 and "画面右侧的人物" in ph3, ph3[:200])
    # 🩸 上下分屏：只做 left/center/right 时两个人会一起判成 center
    # （2026-10-23 真实盘点 a47631b0 就是 28.4s 的上下分屏对比片）。
    tb = [{"id": "P1", "present": True, "position": "top",
           "desc_zh": "浅棕色短发男性", "desc_en": "man with light brown hair"},
          {"id": "P2", "present": True, "position": "bottom",
           "desc_zh": "浅银白短发男性", "desc_en": "man with silver-white hair"}]
    dtb = {x["id"]: {"zh": x["desc_zh"], "en": x["desc_en"]} for x in tb}
    if sel == "volc20":
        ptb = edit_spec.compile_prompt("volc", s, model=V20[0], slots=slots,
                                       source_people=tb, desc_by_id=dtb)
        # 特征可分（浅棕短发 / 浅银白短发）⇒ 用特征、不写方位（2026-10-30 方位降兜底）
        chk("上下分屏：2.0 方位唯一 → 方位+类别词、不写外观",
            "画面上方的男性" in ptb and "画面下方的男性" in ptb
            and "浅棕色短发" not in ptb and "浅银白短发" not in ptb, ptb[:160])
        # 兜底档：两人描述一样 ⇒ 只剩方位能分，必须写画面上方/下方
        same_tb = "短发男性"
        tb2 = [dict(p, desc_zh=same_tb) for p in tb]
        dtb2 = {x["id"]: {"zh": same_tb, "en": x["desc_en"]} for x in tb2}
        ptb2 = edit_spec.compile_prompt("volc", s, model=V20[0], slots=slots,
                                        source_people=tb2, desc_by_id=dtb2)
        chk("上下分屏：2.0 特征不可分 → 方位兜底写画面上方/下方",
            "画面上方" in ptb2 and "画面下方" in ptb2, ptb2[:160])
    elif sel == "h3":
        htb = edit_spec.compile_prompt("minimax", s, model=H3, slots=slots,
                                       source_people=tb, desc_by_id=dtb)
        # 官方 `h3-manual:248` 同样要求指代清楚；top/bottom 盘点要落成中文方位
        # （只做 left/center/right 时两人会一起判成 center，2026-10-23 实测 a47631b0）。
        chk("上下分屏：H3 写画面上方/下方",
            "画面上方的人物" in htb and "画面下方的人物" in htb, htb[:220])

    if sel == "volc20":
        # 单人画面写方位 = 把人钉死在某一侧 → 不许写
        one = [{"id": "P1", "present": True, "position": "left",
                "desc_zh": "穿蓝衣的男人"}]
        p1 = edit_spec.compile_prompt(
            "volc", edit_spec.normalize({"person": True}), model=V20[0],
            slots=["person"], source_people=one, desc_by_id={"P1": {"zh": "穿蓝衣的男人"}})
        chk("单人画面不写方位", "画面左侧" not in p1, p1[:120])
    elif sel == "h3":
        # 盘点没给方位（老任务 / 识别失败）→ 退回原写法，不许崩
        pn = edit_spec.compile_prompt("minimax", s, model=H3, slots=slots,
                                      source_people=[{"id": "P1", "present": True}])
        chk("盘点没给方位 → 退回外貌/泛称，不硬写方位",
            "画面左侧" not in pn and "画面右侧" not in pn
            and "画面上方" not in pn and "画面下方" not in pn, pn[:160])


def main() -> int:
    import _model_lock

    # 🩸 必须点名型号（2026-10-26）：一轮只跑一家。
    if "--model" not in sys.argv:
        lock = _model_lock.current()
        print("⛔ 必须点名型号：--model volc20|volc25|h3")
        print(f"   当前锁：{_model_lock.MODELS.get(lock, lock) if lock else '（无）'}")
        return 2
    i = sys.argv.index("--model")
    sel = sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
    if sel not in _model_lock.MODELS:
        print("用法：--model volc20|volc25|h3")
        return 2
    _model_lock.guard(sel)
    if sel == "volc20":
        phase_20()
    elif sel == "volc25":
        phase_25()
    else:
        phase_h3()
        phase_h3_boundary()
        phase_scene_and_defs(sel)
    phase_positions(sel)
    ok = sum(1 for _, v, _ in rows if v)
    for name, v, detail in rows:
        print(f"  {'ok  ' if v else 'FAIL'} {name}" + (f"  [{detail[:160]}]" if detail else ""))
    print(f"\n{ok}/{len(rows)} 通过（零模型调用）")
    return 0 if ok == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
