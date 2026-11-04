# -*- coding: utf-8 -*-
"""MiniMax H3 · **手写入口**三段式提示词（换人专用）。

## 为什么有这份文件（2026-11-03）

H3 官方有**两套体裁**（见 `docs/H3-SOURCES-MINDMAP.md` §6.5）：

| 体裁 | 官方格式 | 换人样例 |
|---|---|---|
| **手写入口**（本文件） | `参考素材说明 + 核心创意 + 画面过程说明` | ✅ **6 条**（`h3-manual:207-213` / `:185-192`） |
| Ref2VA 六段式（`h3_compile.py`） | `subject_definitions` … `<Subject N>` | ❌ **0 条**（`ex-lamb` 是口型重做，不是换人） |

原来复刻走的是六段式。六段式里唯一和换人沾边的只有 `ref-en:167` 一个标记名
`attribute_transfer`，**没有任何完整换人段落可抄** —— 那套写法只能靠推，
2026-10 ~ 11 月 26 次出片只有零星成功，根因就在这里。

本文件每个句式都必须能回指到 `manual-2026-10-28.md` 的行号，
**指不到出处的句子不许进正文**（`no-stacking-rules`）。

## 官方依据（全部在 `backend/data/official/h3/manual-2026-10-28.md`）

| 行 | 原文 | 用在哪 |
|---|---|---|
| `:244` | `完整提示词 = 参考素材说明 + 核心创意 + 画面过程说明` | 整体结构 |
| `:248` | `人物参考（锁定脸/形象）` / `视频编辑（对视频某个内容进行增删改）` / `音频复用（生成视频的音频直接复用参考音频素材）` | 素材用途句 |
| `:250` | 核心创意 = 主体 / 地点 / 事件 / 题材风格 | 核心创意段 |
| `:251` | 画面过程说明按时间轴分段 | （本版暂不写分段，见下） |
| `:192` | **多人替换官方样例**：`参考视频1进行动作模仿。固定机位全景镜头，正视频中三个穿西装的男人替换为三只高度写实的水豚。水豚必须严格遵循原视频的运动轨迹…保持原有的固定机位不变。确保水豚的毛发质感和光影与环境融合` | 替换句 / 保有句 |
| `:213` | `视频1中最后面的小孩换成 图1中的金毛狗，视频1中最左边小孩穿的卡其色外套改成图2中的牛仔外套` | 点名替换那几个人 |

🩸 **不许从 2.5 借句子**（主人 2026-11-03：「不是他的就不要串啊」）：
「其他人物、道具和背景保持原样」「唯一编辑母版」「色调和光线方向」都是别家的，
H3 手册里没有，一律不写。
"""
from __future__ import annotations

from app.services.edit_spec import PERSON_SLOTS, STYLES

#: 方位 → 中文指代。`position` 来自视觉盘点（`inventory.people[*].position`）。
_POS_ZH = {
    "left": "画面左侧",
    "center": "画面中央",
    "middle": "画面中央",
    "mid": "画面中央",
    "right": "画面右侧",
    "foreground": "画面前景",
    "background": "画面后方",
    # 上下分屏（2026-10-23 真实盘点 a47631b0 就是 28.4s 的上下对比片）：
    # 只认 left/center/right 的话两个人会一起判成「画面中央」，指代就废了。
    "top": "画面上方",
    "upper": "画面上方",
    "bottom": "画面下方",
    "lower": "画面下方",
    # 九宫格四角（`inventory.people[*].position` 用的就是 POS9 这套写法）。
    "top-left": "画面左上",
    "top-right": "画面右上",
    "bottom-left": "画面左下",
    "bottom-right": "画面右下",
}


#: 已经是「人」类中心词的结尾 —— 再补「的人」就成了「穿红裙的女生的**人**」。
#: 描述来自视觉盘点，形如「穿红裙的女生」「浅棕色短发男性」「戴帽子的男人」。
#:
#: 🩸 2026-11-04 想改它，**改完证明是白改，已还原**：原 `endswith` 和"看末4字"
#:   对 `data/clone/*/inventory` 的 33 条真实描述**判定完全相同** ——
#:   「留黑色长直发」两种都补「的人」、「留黑色短发的女性」两种都不补。
#:   一次真实输出都没变 → 这不是写死，是**本来就对**。
#:   （补出来的「画面左侧的留黑色长直发的人」读着啰嗦，但语法完整、模型看得懂。
#:    要改它得先看见它出过错，不能凭"读着别扭"就动。）
_PERSON_NOUNS = ("人", "性", "者", "生", "男", "女", "孩", "童", "娃", "士", "翁")


def _look_feat(*cands: dict | None) -> str:
    """参考图的外观描述 → 一句可写进括注的特征。**优先中文**（正文是中文）。

    🩸 快照那边（`video_edit._look_text`）按「提示词里实际出现哪句」记账，
    所以这里写 zh，快照就会记 zh，两边对得上；写 en 会让 `used` 灯变暗。
    """
    for lk in cands:
        if not isinstance(lk, dict):
            continue
        txt = str(lk.get("zh") or lk.get("en") or "").strip()
        if txt:
            return txt.rstrip("。.")
    return ""


def _present(p: dict | None) -> bool:
    """盘点里这个人在不在场。缺席的人（分段后）不写进提示词。"""
    return bool(p) and p.get("present", True) is not False


def h3_orig_locator(per: dict | None, pool: list[dict] | None = None, **kw) -> str:
    """「原片里的这个人」怎么指代 —— **闸和产出共用同一套指代逻辑**。

    🩸 以前这道闸读英文描述（六段式要写 `<Subject N> is the person in <Video 1>`），
    换成手写入口后正文是中文，闸也必须读中文描述，否则闸和产出各说各话。
    """
    if not _present(per):
        return "画面中的人物"
    dup = _dup_positions([p for p in (pool or []) if _present(p)] + [per])
    return _who(per, unambiguous=_pos_of(per) not in dup)


def _pos_of(p: dict) -> str:
    return str(p.get("position") or "").strip().lower()


# 素材用途句：`人物参考（锁定脸/形象；<完整外观描述>）`。
#   🩸 2026-11-04 出片对照后的定论（台账 §62）：
#   - 描述要**完整**（脸；气质；发型；服装；身形）。试过只留「脸/气质/发型」
#     （`_face_only()`，v8 `9135cdd7`）→ **一个像素都没变**。模型靠服装、发型这些
#     大色块定位"要改哪里"，抽掉锚点它就不动手。
#   - 锁的词是 **`锁定脸/形象` 两个词**（`:248` 素材用途表原文）。只写「锁定…脸」
#     会让耳饰、气质、发型变成没有归属的噪音 —— 它们不是"脸"，是"形象"。
#     `:264`「锁这位女子的脸」是示例里的简称，不是完整用途名。
#   - 发型是肉眼判断换没换最灵敏的一项（主人：「看图看得发型是最容易看出换没换」），
#     这个判断用在**看图**上，不是用来删描述的。


def _who(p: dict, *, unambiguous: bool) -> str:
    """一个被替换对象的指代词。

    官方 `h3-manual:248`：「如果有多个角色，**需要能指代清楚**」。
    所以优先用方位；方位缺失或多个人撞同一个方位时，退回外貌描述。

    🩸 只用方位、不用「人物」二字打底 —— 官方 `:213`「最后面的小孩」「最左边小孩」
    就是方位指代，模型认这个。
    """
    pos = _POS_ZH.get(_pos_of(p))
    desc = str(p.get("desc_zh") or "").strip()
    if pos and unambiguous:
        return f"{pos}的人物"
    if desc:
        # 描述太长会稀释替换目标（`h3-manual:251`「尽量少写比喻句，多写看得见的画面」），
        # 截到第一个逗号，保留最好认的那一项外貌特征。
        head = desc.split("，")[0].split(",")[0].strip()
        if head:
            # 🩸 描述本身常以「人」类中心词收尾（「穿红裙的女生」「浅棕色短发男性」），
            #   再补「的人」就成了「穿红裙的女生的**人**」。
            tail = "" if head.endswith(_PERSON_NOUNS) else "的人"
            return f"{pos}的{head}{tail}" if pos else f"{head}{tail}"
    return f"{pos}的人物" if pos else "画面中的人物"


def _dup_positions(people: list[dict]) -> set[str]:
    """出现 ≥2 次（或缺失）的方位 —— 这些方位不能单独用来区分人。"""
    seen: dict[str, int] = {}
    for p in people:
        if not _present(p):
            continue
        seen[_pos_of(p)] = seen.get(_pos_of(p), 0) + 1
    return {k for k, n in seen.items() if n > 1 or not k}


# 🩸 2026-11-04 撤掉「人物、动作、台词、站位、机位、分镜、场景、光线、口型都按
#   @视频1原样」这一整句。两个原因，都有实证：
#   ① 语义自杀：句首「人物」和上一句「把…人物换成@图片N中的人物」直接对冲。真跑
#      `f35fadf` 的结果是**只换了衣服、脸一个字没动**（SFace 0.19 / 0.258，阈值
#      0.363；同一张参考图在上一次 `81633d37` 换到了 0.71）。
#   ② 句式不是 H3 的：`h3-manual:213`（精准换人物与细节）的官方结构是**一条改动
#      一句**——「视频1中最后面的小孩换成 图1中的金毛狗，视频1中最左边小孩穿的
#      卡其色外套改成图2中的牛仔外套」；`:192` 的保持写法只有三句（运动轨迹 /
#      固定机位 / 光影融合），**没有逐项列举**。项表里的「站位」在 H3 官方全库
#      出现 0 次（2.5 里 20 次），是纯外来词。
#   ⇒ 不再自造"其余保持"清单。要保什么，用 `:192` 那三句锁。


def handwrite(spec: dict, c: dict, idx: dict[str, int],
              *, people: list[dict] | None = None,
              frame_people: list[dict] | None = None,
              audio_ref: bool = False,
              desc_by_id: dict[str, dict[str, str]] | None = None,
              style_video: bool = False,
              boundary_pic: int = 0,
              subject_look: dict | None = None,
              subject_looks: dict | None = None,
              shot_cuts: list[float] | None = None,
              shot_desc: list[dict] | None = None,
              **kw) -> str:
    """编出手写入口版提示词。**只处理换人**（`change.person`）。

    返回 = 【参考素材说明】+【核心创意】+【画面过程说明】（`h3-manual:244` 的三段公式）。
    🩸 `frame_people`（这一段的整个画面）**已不再使用** —— 参数留着是为了不惊动
      调用方 `models/h3.py`；"其余别动"的活儿现在全交给 `:192` 的两句保持句。
    """
    people = [p for p in (people or []) if _present(p)]
    dup = _dup_positions(people)
    blocks: list[str] = []

    # ---------------------------------------------------------------- 参考素材说明
    # 官方 `h3-manual:248`：写清素材编号 + 每个素材的用途。
    duties: list[str] = []
    _looks = subject_looks or {}
    for i, p in enumerate(people):
        slot = PERSON_SLOTS[i] if i < len(PERSON_SLOTS) else ""
        n = idx.get(slot) if slot else None
        if not n:
            continue
        # 官方 `h3-manual:284`（大字幕 MV · 完整范例）的**冒号式**：
        #   `@图片1：人物形象（脸、发型、服装轮廓、比例、气质、整体氛围）`
        #   括号里放"取哪些维度"；有具体特征就用特征顶替维度名。
        # 🩸 素材说明里**不写方位指代**：官方 `:264` 的「这位女子」指的是
        #   **参考图里**那个人。写成「锁定画面左侧的人物」会被读成"锁住原片那个人"，
        #   和核心创意的替换句对冲。方位只留给替换句，一处指代不写两遍。
        # 🩸 复刻 = **视频编辑**任务：画面由原片决定，参考图回答"换成谁"。
        #   前面那个「锁定图中人物的脸」是 `:248`「人物参考（锁定脸/形象）」/`:264`
        #   「锁这位女子的脸」的**动作**；括号后半段是 2.1 模型对该图的外观描述，
        #   依据 `:248`「如果素材中有非常想要保持的特征，**建议**明确写出来」。
        # ⚠️ 2026-11-04 曾把后半段整段删掉（理由"编辑任务不需要外观描述"），
        #   随即恢复 —— 因为 §46 那次单人真跑（0.415 过线）**是带着描述跑的**，
        #   删掉等于动了一个没验证过的变量。要删先单独跑一条验证再删。
        _look = _looks.get(slot) or subject_look or {}
        # 🩸 官方原词是「人物参考（**锁定脸/形象**）」——`脸` 和 `形象` 两个词。
        #   只写「锁定…脸」会把后面的耳饰、气质、发型变成没有归属的噪音
        #   （它们不是"脸"，是"形象"）。(`:248` 素材用途表; `:264` 的短版
        #   「锁这位女子的脸」是示例里的简称，不是完整用途名。)
        _zh = str(_look.get("zh") or "").strip()
        if _zh:
            duties.append(f"@图片{n}：人物参考（锁定脸/形象；{_zh}）。")
        else:
            duties.append(f"@图片{n}：人物参考（锁定脸/形象）。")
    if idx.get("product"):
        # 同一张表里的「物体参考（锁定物体）」，官方原词。
        duties.append(f"@图片{idx['product']}：物体参考（锁定物体）。")
    if idx.get("scene"):
        duties.append(f"@图片{idx['scene']}：场景参考（锁定场景）。")
    if idx.get("wardrobe"):
        # 官方 `h3-manual:248` 的用途表里**没有「服装参考」这一项**，别自己造词；
        # 服装归在「物体参考（锁定物体）」下，按 `:264` 官方示例的写法在后面补
        # 一句锁什么（「@图片1 是人物参考（锁这位女子的脸）」）。
        duties.append(f"@图片{idx['wardrobe']}：物体参考（锁定服装）。")
    if style_video:
        duties.append("@视频2：风格参考（锁定风格）。")
    if boundary_pic:
        # 分段续接：上一段的尾帧 = 本段的首帧。官方 `h3-manual:248` 用途表原词
        # 「关键帧（锁定帧，如果有首帧尾帧需求明确提出）」。
        duties.append(f"@图片{boundary_pic}：关键帧（锁定帧）。")

    # 🩸 没盘点、但有图号：官方 `h3-manual:248` 要求「写清每个素材的用途」，
    #   所以图照写用途句（只是说不出是谁），不能因为不知道是谁就整段不写。
    lone_person_pic = bool(idx.get("person")) and bool(c.get("person")) and not people
    if lone_person_pic:
        duties.insert(0, f"@图片{idx['person']}：人物参考（锁定脸/形象）。")

    # @视频1 的用途：官方 `:248`「视频编辑（对视频某个内容进行增删改）」。
    # 🩸 **恒写** —— 复刻这一路一定要给原片，原片也是一个素材，
    #   `:248` 要求「上传的每个素材都写清用途」，不能因为「没换人」就不交代它。
    # 🩸 用 `:248` 的原词「对视频某个内容进行增删改」。以前写的是「对**原片**中的
    #   人物进行替换」—— "原片"在 H3 手册里只以"原片段"出现过（指音轨），
    #   官方对素材的称呼是"@视频1"或"原视频"。
    duties.append("@视频1：视频编辑素材（对@视频1中的内容进行增删改）。")
    # 音频：`:248` 用途表「音频复用（生成视频的音频直接复用参考音频素材）」。
    # 🩸 主人 2026-11-04：「复刻视频本来就没让他生成新的音频」——**复刻默认没有音频
    #   素材**（`audio_ref=False`），这时一个字都不写。只有真传了外部音频
    #   （`audio_ref=True`）才需要交代它的用途，`:248` 要求「写清每个素材的用途」。
    #   以前是无条件写，等于在复刻里描述一件模型不需要决定的事。
    if audio_ref:
        duties.append("@音频1：音频复用素材（生成视频的音频直接复用参考音频素材）。")

    if duties:
        blocks.append("【参考素材说明】\n" + "\n".join(duties))

    # ------------------------------------------------- 核心创意 / 画面过程说明
    # 官方 `h3-manual:244`：「完整提示词 = 参考素材说明 + 核心创意 + 画面过程说明」。
    # 🩸 2026-11-04 之前这里是**一整段无标题自由文字**：替换句、范围句、三条约束、
    #   换装/产品/场景/风格，外加一张九项「其余按原样」清单，全揉在一起。模型分不清
    #   哪句是"要改"、哪句是"别动" —— 真跑 `f35fadf` 只换了衣服、脸一个字没动
    #   （SFace 0.19 / 0.258，阈值 0.363）。
    #   官方 `:213`（精准换人物与细节）的结构是**一条改动一句**；`【核心创意】` 只放
    #   "改什么"，"怎么动、怎么保"交给 `【画面过程说明】`（`:251`）。
    idea: list[str] = []      # 【核心创意】改什么
    process: list[str] = []   # 【画面过程说明】时间轴分段（`:251`）
    # 【整体要求补充】—— 贯穿全片的规则，**不和逐段时间轴混在一节**。
    #   依据是 `:284`（大字幕 MV）/ `:285`（手绘特效）两条**完整提示词模板**：
    #   它们都把跨全片的规则单列成 `▍分组名（贯穿全片）`，共 12 处。
    #   `:244` 的「三段公式」是简版骨架；任务复杂到有全局约束时，官方自己用四段。
    #   存 (分组名, 句子) —— 组装时同组连排，组名只写一次。
    overall: list[tuple[str, str]] = []

    # ⓪ 续接句 —— 官方 `h3-manual:266`「@图片1 是首帧参考图：…」的排布：
    #   先说从哪一帧开始，再说改什么。它属于时间轴的起点。
    if boundary_pic:
        process.append(f"画面从@图片{boundary_pic}定义的首帧自然开始。")

    # ⑨ 镜头结构 —— 数据先收好，**生成放到替换句之后**：`:260` 要求写"主体是之前
    #   的哪个角色"，得先知道换了哪几张图才能用图号指代。
    #   `:251` 原文：「按时间轴或故事线分段写…**以切镜 shot 作为时间戳的分段**」。
    #   `:250` 明写「**默认会切镜**」：不告诉模型切点，它自己编。
    #   `:254` 官方佐证：「**H3 对于切镜点遵从较强**」。
    #   🩸 实测（任务 `de591f35` · render `45749cef`）：
    #     源片 2 镜（`recipe.shots` 0–3.333 / 3.333–5.362）→ 成片 3 镜
    #     （0–2.17 / 2.17–4.0 / **4.0–5.37**）。多出来的那一刀，画面是参考图2
    #     的夜晚庭院 —— 模型没有切镜点，就自己切到参考图里去了。
    #   `shot_cuts is None` = 不知道（没传），**不要瞎猜**；空列表 = 确定一镜到底。
    #
    # ⑧ 景别 —— `:251`「每个 shot 内部写好**景别**」，`:260`「**切镜到什么景别**」。
    #   🩸 **只取景别**，不取整句、也不取运镜 —— 这是分清"哪些是哪些不是"的地方：
    #   · `shots[].en` 是给**提示词优化线**（`ref-en:7` 的 `detailed_description`）
    #     用的完整画面描述，里面**带人物外观**（`two aproned women`）。复刻里这句话
    #     和「换成@图片1中的人物」正面打架，原样搬进来必错。
    #   · `:251` 要三样：景别 / 内容 / 运镜。复刻里**内容不用写** —— 内容就是
    #     "换成谁"，已经在【核心创意】里了；写它就是拿原片的人去顶替参考图的人。
    #   · 运镜**不取**：实测 13 条样本里 `camera at frame center`（位置）、
    #     `camera to show the full pile of snacks`（内容）都被误认成运镜，
    #     宁可少说，不说错。
    #   · 景别取第一个逗号前 —— `vision_plan.py:211` 规定 en 的顺序就是
    #     「景别与构图 → 主体 → 动作 → 环境与光线 → 运镜」，13/13 样本全中。
    _scales: list[tuple[float, float, str]] = []
    for s in (shot_desc or []):
        sc = str(s.get("en") or "").strip().split(",")[0].strip()
        if sc:
            _scales.append((float(s.get("start") or 0), float(s.get("end") or 0), sc))
    _cuts: list[float] = []
    if shot_cuts is not None:
        _cuts = sorted({round(float(x), 2) for x in shot_cuts if float(x) > 0})

    swapped = False
    # 被换掉的图号 —— `:260`「具体主体是之前的哪个角色」要用它指代。
    # 用图号而不是外貌描述：描述会和「换成@图片N中的人物」打架（§50 踩过）。
    _swapped_n: list[int] = []
    # 换装覆盖判定 —— 和 `_wardrobe_pairs()` 同一套口径（有 ids 按 ids，否则全员）。
    # 被换装覆盖的人，服装由换装句决定，维度里不能再要求服装跟参考图走。
    _wd_ids = {str(x) for x in (c.get("wardrobe_ids") or [])}
    _wd_all = (not _wd_ids) and (
        bool(str(c.get("wardrobe_desc") or "").strip()) or bool(idx.get("wardrobe")))
    if people:
        # ① 替换句 —— 逐字照 `:213`「视频1中最后面的小孩换成 图1中的金毛狗，
        #    视频1中最左边小孩穿的卡其色外套改成图2中的牛仔外套」：**每个分句都重带
        #    `视频1中`**，一人一句，不合并。
        # ② 维度跟人绑定 —— 维度名出自 `:142`「请保持同一个角色**脸、发型、体型比例、
        #    服装设计、材质细节**…一致」。
        # 🩸 2026-11-04 实测（v7 `67285c2f`）：带维度句 → 衣服/发型全换了、背景全程
        #    留在厨房、脸部分帧换；v8 `9135cdd7` 把用途句描述砍到只剩脸 → **完全不换**。
        #    维度句是驱动"真的去改"的那一句，**不能删**。
        # 🩸 但两人合并成一句（「…与@图片1、@图片2保持一致」）会抹掉对应关系，
        #    必须一人一句、各绑各的图号。
        parts: list[str] = []
        for i, p in enumerate(people):
            slot = PERSON_SLOTS[i] if i < len(PERSON_SLOTS) else ""
            n = idx.get(slot) if slot else None
            if not n:
                continue
            _dims = ("脸、发型、体型比例和材质细节"
                     if (_wd_all or str(p.get("id") or "") in _wd_ids)
                     else "脸、发型、体型比例、服装设计和材质细节")
            parts.append(f"@视频1中{_who(p, unambiguous=_pos_of(p) not in dup)}"
                         f"换成@图片{n}中的人物，替换后该人物的{_dims}"
                         f"与@图片{n}保持一致")
            _swapped_n.append(n)
        if parts:
            idea.extend(f"{x}。" for x in parts)
            swapped = True
    else:
        # 没勾具体的人、只写了文字描述（`change.person_desc`）
        desc = str(c.get("person_desc") or "").strip()
        n = idx.get("person")
        if desc:
            idea.append(f"把@视频1中的人物换成{desc}。")
            swapped = True
        elif n and c.get("person"):
            # 有图、没盘点：必须用图号点名（`:213`），否则「把人物换掉」没有唯一解。
            idea.append(f"@视频1中的人物换成@图片{n}中的人物。")
            _swapped_n.append(n)
            _dims = ("脸、发型、体型比例和材质细节" if _wd_all
                     else "脸、发型、体型比例、服装设计和材质细节")
            idea.append(f"替换后的人物在{_dims}上与@图片{n}保持一致。")
            swapped = True

    # ⑩ 时间轴分段 —— 按盘点给的镜头数写，切片器单独报的切点**不进提示词**。
    #   `:251`「以切镜 shot 作为时间戳的分段」——盘点给了几个 shot 就写几段。
    #   标签用官方格式 `0-3 秒：全景`（`:251` 示例 / `:285` 完整案例），
    #   **不是**自造的「原片画面：」。
    _pics = "、".join(f"@图片{n}" for n in _swapped_n)
    if len(_scales) >= 2:
        for i, (a, b, sc) in enumerate(_scales[:12]):
            if i == 0:
                process.append(f"{a:g}-{b:g} 秒：{sc}。")
            else:
                _subj = f"，主体仍是{_pics}中的人物" if _pics else ""
                process.append(f"{a:g}-{b:g} 秒：切镜到{sc}{_subj}。")
    elif len(_scales) == 1:
        a, b, sc = _scales[0]
        process.append(f"{a:g}-{b:g} 秒：{sc}。")
        # 🩸 盘点只有 1 个 shot 时**不补切点句**（§58）。`de591f35` 的 3.33s 是切片器
        #   被舞蹈动作骗出来的，主人确认源片是一个镜头；写了"切镜"模型就会编新镜头
        #   → `93dbec8f`/`c8455a93` 第二镜整段搬来 @图片2 的庭院。
    elif _cuts:
        _where = "、".join(f"第 {c:g} 秒" for c in _cuts)
        process.append(f"在@视频1{_where}的切镜点切镜。")

    if shot_cuts is not None:
        if not _cuts:
            process.append("全程一镜到底，不要切镜。")
        else:
            overall.append(("镜头", "严格参考@视频1的镜头节奏和转场风格。"))

    # ② 换人专属的融合句 —— 全部进【整体要求补充】，这些是**贯穿全片**的规则，
    #   不是某一秒的画面内容（`:284`/`:285` 的官方分组法）。
    #   官方范例是 `:133`，**不是** `:192` 那两句就够。
    #
    # 🩸 2026-11-04 第二轮：之前我以为「官方只有 C11 `:213` 一条部分编辑案例，
    #   其余一个字不提，所以我们也别写」—— **那是只扫了第三章的结果**。
    #   全书通读后，1.8 节的 `:133` 是唯一一条「替换某个元素、其余保持」的
    #   完整范文；第三章总纲 `:206` 更是白纸黑字：
    #   「高精度指令控制：准确执行局部修改与细化要求，**同时保持未编辑内容相对稳定**」。
    #   → 明写"什么不能动"是官方要求。
    #   （早前撤回过「画面右下的人物保持原样」，那条**撤回是对的**：引的 `:212`
    #    是给"新增加进来的人"的要求。但"结论：什么都不写"同样不成立。）
    # ⚠️ 已知现象（无规则，别拿它推规则）：盘点 1 人全换 → 2 次成功；
    #   盘点 3 人只换 2 个 → 2 次失败。见 `docs/H3-CLONE-MATRIX.md` §10 空白表。
    #
    # 🩸 2026-11-04 第三轮：**保留清单和禁止项从这里搬走了**，见函数末尾 ——
    #   它们被 `if swapped:` 包着，只换场景 / 只换产品时一句话都不写。见下面 §⑪。
    if swapped:
        # ②-a 运动轨迹 —— `:192`（C07）：「水豚必须严格遵循原视频的运动轨迹」。
        #   官方用词是「**原视频**」，不是「原片」。
        #   🩸 同句的「保持原有的固定机位不变」**不搬**：那是 `:192` 贴它自己的源片
        #   说的（该案例第 2 句就写「固定机位全景镜头」）。复刻源片普遍有切镜，
        #   抄这句等于要求别切镜 —— 真跑出来两镜被压成一镜到底。`:250`「默认会切镜」。
        overall.append(("人物与动作",
                        "替换后的人物必须严格遵循原视频的运动轨迹。"))

        # 🩸 2026-11-04 第三轮实测：**` :133` 的融合/保留清单不许套到换人上**。
        #   真跑对照（同一任务、同一源片、同一参考图）：
        #     v4 `93dbec8f` = 只有 `:192` 两句  → 前半段两张脸**都换成了**
        #     v5 `f2825696` = 加了 `:133` 的保留清单 + 融合 + `:95` 禁止句
        #                     → **每一帧都判"没换"**（成片 vs 源片 sim 0.59–0.69）
        #   官方三种替换任务**各有一套公式**，不能混：
        #     `:213` 换人物  —— 只写替换句，「其余不提」
        #     `:192` 换主体  —— 运动轨迹 + 光影融合，两句
        #     `:133` 换场景  —— 融合五项 + 保留清单四项 + 「100% 不变」
        #   `:133` 那句「画面中其他物品…必须保持 100% 不变」在换人语境里会把
        #   **人也算进"其他物品"**，整片被按住不动。
        #   → 换人只留 `:192` 的两句（v4 实证过）；`:133` 全套搬到 ⑤ 换场景那边。

        # ②-d 收尾 —— `:133`「确保替换元素与原画面无缝融合」的换人版；
        #   外观维度取自 `:192`「水豚的毛发质感和光影与环境融合」。
        overall.append(("画面融合", "确保替换后的人物质感和光影与环境融合。"))


    # ④ 换装 —— `:213`「视频1中最左边小孩穿的卡其色外套改成图2中的牛仔外套」
    if c.get("wardrobe"):
        idea.extend(_wardrobe_pairs(c, people, idx))

    # ⑤ 换产品 —— `:234`「将视频开头出现的易拉罐饮料替换为可口可乐」
    if c.get("product"):
        target = str(c.get("product_target") or "").strip()
        desc = str(c.get("product_desc") or "").strip()
        n = idx.get("product")
        # 用户填的定位词常常自带「画面里那只」，再拼「@视频1中的」就成了
        # 「@视频1中的画面里那只」，指代打两遍。
        _loc = "" if target.startswith(("画面", "视频")) else "@视频1中的"
        if target and desc:
            idea.append(f"把{_loc}{target}替换为{desc}。")
        elif target and n:
            idea.append(f"把{_loc}{target}替换为@图片{n}中的物体。")
        elif desc:
            idea.append(f"把@视频1中的物体替换为{desc}。")

    # ⑥ 换场景 —— `:221`「视频1窗外的场景改成图1」/ `:219`「将视频1绿幕背景去除」
    _scene_changed = False
    if c.get("scene"):
        desc = str(c.get("scene_desc") or "").strip()
        n = idx.get("scene")
        if desc:
            idea.append(f"把@视频1中的背景场景替换为{desc}。")
            _scene_changed = True
        elif n:
            idea.append(f"把@视频1中的背景场景替换为@图片{n}中的场景。")
            _scene_changed = True

        # 场景融合 —— `:133` 的五项**正是换场景用的**（这是"替换桌面+背景"的原文）：
        #   「新办公桌的透视比例需与原镜头**完全匹配**，桌面材质需**自然承接**原视频的
        #     光影投射，边缘阴影与高光方向必须与原场景光源**严格一致**。背景…的景深
        #     虚化程度需与原视频焦点**对齐**，保持原有空间纵深感。」
        # 🩸 2026-11-04 主人：「我们也有换场景的哟！只是现在还没勾选呢」——
        #   之前把这五项当成"换桌面专用、换人用不上"整批丢掉，等于把**换场景**
        #   这条自己有的功能需要的例句也扔了。换成场景语汇逐项落：
        if _scene_changed:
            overall.append((
                "场景融合",
                "新背景的透视比例与原镜头完全匹配，边缘阴影与高光方向与原场景光源"
                "严格一致，景深虚化程度与原视频焦点对齐，保持原有空间纵深感。"))

    # ⑦ 风格 —— `:248`「风格参考（根据图片的风格，生成类似的风格内容）」
    # 🩸 `c["style"]` 是**枚举键**（`edit_spec.STYLES`：live/anime/3d/film/sketch），
    #   不是自由文本 —— `normalize` 会把不在表里的值清空（`edit_spec.py:305`）。
    if c.get("style") or c.get("style_ref"):
        n = idx.get("style_ref")
        label = STYLES.get(str(c.get("style") or ""), "")
        if n:
            idea.append(f"画面风格按@图片{n}的风格参考生成类似的风格内容。")
        elif label:
            idea.append(f"画面风格改为{label}。")

    # ⑧ 用户补充说明 —— `:248`「以及其他要求也可按需写明」
    # 🩸 `extra` 在 spec **顶层**，不在 `change` 里（`edit_spec.py:208/342`）。
    extra = str(spec.get("extra") or "").strip()
    if extra:
        process.append(extra)

    # ⑪ 保留清单 —— **只在换场景时写**，不是「任何改动都写」。
    #
    # 2026-11-04 同一个任务连跑两版，把这条的边界测出来了：
    #   v4 `93dbec8f`（只有 `:192` 两句）                → 前半段两张脸**都换成了**
    #   v5 `f2825696`（+ `:133` 保留清单 + `:95` 禁止句） → **每一帧都「没换」**
    # `:133` 的原文标题是「精准替换**场景背景**」—— 它的保留清单是给
    # 「桌面和背景换了、场上的人别动」写的。换人反过来：**人换了、背景别动**。
    # 同一句「画面中其他物品…必须保持 100% 不变」到了换人语境，模型会把人也
    # 算进「其他物品」，整片被按住不动。
    #
    # 官方三种替换任务**各有一套公式**，按任务归位、不互相搬：
    #   `:213` 换人物 —— 只写替换句，其余不提
    #   `:192` 换主体 —— 运动轨迹 + 光影融合，两句
    #   `:133` 换场景 —— 融合五项 + 保留清单四项 + 「100% 不变」
    #
    # `:95`「不要重新生成一个新场景」也删了：场景跑偏的真正成因是**缺切镜点**
    # （`45749cef` 没写切镜 → 成片 3 镜，多出来那镜跑到参考图2 的庭院）；
    # `:260` 的切镜句加上后 v4/v5 两版场景都对。`:95` 是 AR 特效案例
    # （在原片上加东西），「不要重新生成」在换人语境会被读成「整片别动」。
    if _scene_changed:
        # 保留清单 —— `:133` 逐项：
        #   「原视频的镜头运动轨迹、机械臂的完整运动时序与速度、画面中其他物品的
        #     相对位置与空间遮挡关系、以及整体光照氛围必须保持 100% 不变」
        #   「机械臂」→「人物动作」、「其他物品」→「其他元素」（不限定是人还是道具，
        #    只换 1 个角色、场上没有"其他人"时这句话也不落空）。
        #   「光照氛围」后面补「和色调」—— `:88` 的八项保持清单里多这一项
        #   （「动作、场景、**综合色**、镜头运动、时长与帧率」），色彩和光照是两个维度。
        #   🩸 `:88` 的「时长与帧率」**不搬**：时长由 API 参数（`_gen_duration`）控制，
        #     写进提示词模型看不见，等于没写。
        # 组名用「镜头与画面」而不是「人物与动作」：这条清单在**只换场景**时也要写，
        # 挂"人物"的组名会让人误以为它只对角色生效。
        overall.append(("镜头与画面",
                        "@视频1的镜头运动、场景中人物动作的时序与速度、画面中其他元素的"
                        "相对位置和空间遮挡关系、以及整体光照和色调必须保持 100% 不变。"))

    if idea:
        blocks.append("【核心创意】\n" + "\n".join(idea))
    if process:
        blocks.append("【画面过程说明】\n" + "\n".join(process))
    if overall:
        # `▍分组名（贯穿全片）` —— `:284`（大字幕 MV）/ `:285`（手绘特效）两条
        # **完整提示词模板**共用了 12 次的官方分组写法：跨全片的规则集中放，
        # 不和逐段时间轴混在一节。同组连排，组名只写一次。
        # 按组**归并**（不是"相邻同名合并"）：同一组的句子可能分几次追加，
        # 中间插进别的组时不能开第二个同名标题。dict 保插入序 → 组的先后不变。
        _groups: dict[str, list[str]] = {}
        for grp, line in overall:
            _groups.setdefault(grp, []).append(line)
        lines: list[str] = []
        for grp, items in _groups.items():
            lines.append(f"▍{grp}（贯穿全片）")
            lines.extend(items)
        blocks.append("【整体要求补充】\n" + "\n".join(lines))

    return "\n\n".join(blocks)


def _wardrobe_pairs(c: dict, people: list[dict], idx: dict[str, int]) -> list[str]:
    """换装句。官方 `h3-manual:213`：「最左边小孩穿的卡其色外套改成图2中的牛仔外套」。

    `wardrobe_ids` 第 i 项 → 第 i 个人 → `WARDROBE_SLOTS[i]` 那张图。
    """
    from app.services.edit_spec import WARDROBE_SLOTS

    by_id = {str(p.get("id") or ""): p for p in people}
    pairs = [str(x) for x in (c.get("wardrobe_ids") or [])]
    per = c.get("wardrobe_desc_by_id") or {}
    fallback = str(c.get("wardrobe_desc") or "").strip()
    out: list[str] = []
    if pairs:
        for i, pid in enumerate(pairs):
            p = by_id.get(pid)
            if not p:
                continue
            slot = WARDROBE_SLOTS[i] if i < len(WARDROBE_SLOTS) else ""
            n = idx.get(slot) if slot else None
            desc = str(per.get(pid) or fallback).strip()
            who = _who(p, unambiguous=True)
            if desc:
                out.append(f"{who}的服装改为{desc}。")
            elif n:
                out.append(f"{who}的服装改为@图片{n}中的服装。")
    elif fallback:
        out.append(f"@视频1中人物的服装改为{fallback}。")
    else:
        n = idx.get("wardrobe")
        if n:
            out.append(f"@视频1中人物的服装改为@图片{n}中的服装。")
    return out


# 🗑️ `_kept_people()` 2026-11-04 删除：它产出的「画面右侧的人物保持原样。」这句
#   在 H3 官方手册里没有出处（`:213` 精准换人只点名"换谁"，不说"其余别动"），
#   而且和 `@视频1中…换成@图片N中的人物` 一起出现时，模型会把"保持"读成全局默认。
#   现在只靠 `:192` 的两句保有/融合句锁，不再点名谁别动。
