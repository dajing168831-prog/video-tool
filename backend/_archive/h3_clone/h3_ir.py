"""H3 逐段提示词 —— 走**官方改写器** H3-Context-IR（2026-11-02）。

为什么不自己写六段式
--------------------
官方视频生成指南「全能参考生成」给的示例提示词就一句自然语言：

    人物参考视频1的动作，表演街舞，人物参考图1 图2            # `guides/video-generation`
    图2作为固定人物参考，保持黑色半扎长发、银色镂空发冠…一致。  # `guides/video-prompt`（亮点示例）

结构化提示词是**官方专门做了一个接口**来产出的
（`POST /v2/h3_context_ir`：「深度理解文本、图像、音频和视频等多模态上下文…生成结构化表达」，
「本接口只返回增强提示词，不创建视频」）。

以前我们让 DeepSeek 现写六段式（`h3_agent`），等于自己充当改写器：
同一个任务、同一张定妆照、同一条原片，四次跑出四份不同的词，三种不同的失败。
这里改成「一句自然语言 → 官方改写 → 提示词」，口径交给官方。

产出的提示词按**输入指纹落盘**（`data/clone/<cid>/ir/`）：同一素材重跑拿回同一份，
不再每跑一次就换一套词。

🩸 2026-11-03：改写器是**抽样**的，同一个输入也可能抽出一份不合格的词。以前
**命中缓存就无条件返回**（抽到什么就永久存什么），第一次抽坏，此后每次出片都用
那份坏的，用户点多少次"重跑"都拿回同一份 —— 这是"怎么调都调不好"的机制之一。
现在：产出先过 `_ir_defects()` 的**结构完整性检查**（有没有被截断、有没有少写段），
完整才写缓存；不完整就重抽（最多 `_IR_MAX_TRY` 次），全都不完整就返回最后一次
并记 WARNING，**不污染缓存**。旧缓存也要先过同一检查才认。

⛔ 这里**只做机械检查，不做质量判定**（2026-11-03 主人定）：一份六段齐全、
镜数对得上的产出，不代表它一定换得动人。质量由主人看片定，不由代码判。
"""
from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

from app.services import clone_store

log = logging.getLogger(__name__)

#: 槽位 → 中文称呼（官方示例用「人物参考图1」「音频1」这种说法）
_ZH = {"person": "人物", "product": "商品", "scene": "场景",
       "wardrobe": "服装", "style": "风格"}

def _zh(slot: str) -> str:
    for k, v in _ZH.items():
        if str(slot).startswith(k):
            return v
    return "参考"


#: 盘点的方位词 → 提示词里的中文方位（`inventory.people[].position`）
#: 🩸 2026-11-03：盘点 schema 给的是**九宫格 10 个值**（`vision_plan._POSITIONS`），
#:   这里以前只认 left/center/right（外加枚举里根本不存在的 middle/front/back）。
#:   其余 7 个值静默变成空串 → 整句退回「各替换一位」→ IR 根本不知道换画面里
#:   哪一位。双人换人时这就是"换错人 / 干脆不换"的直接来源之一。
_POS_ZH = {"left": "左边", "center": "中间", "middle": "中间",
           "right": "右边", "front": "前排", "back": "后排",
           "top-left": "左上角", "top": "画面偏上",
           "top-right": "右上角", "bottom-left": "左下角",
           "bottom": "画面偏下", "bottom-right": "右下角"}


def _pos_zh(position) -> str:
    """盘点方位 → 中文方位。认不出来的**返回空串**，让调用方退回泛称。"""
    return _POS_ZH.get(str(position or "").strip().lower(), "")


def instruction(slots: list[str], *, boundary_pic: int = 0,
                extra: str = "", looks: dict | None = None,
                cuts: list[float] | None = None,
                span_dur: float = 0.0,
                audio_mode: str = "",
                ppl: list | None = None,
                ppl_all: list | None = None,
                frame_n: int = 0,
                lines: list | None = None,
                changes: dict | None = None,
                people_desc: dict | None = None,
                style_video: bool = False) -> str:
    """写这一段要交给改写器（H3-Context-IR）的**一句自然语言**。

    🩸 2026-11-02：`h3-manual:244` 那条公式

        **完整提示词 = 参考素材说明 + 核心创意 + 画面过程说明**

    说的是**改写器的输出**该长什么样，不是它的输入。官方调 H3-Context-IR 时
    `text` 只有一句话（`scripts/readme/full-2k-ref2va-h3-context-ir.sh`：
    `"Character speaks: … Voice timbre follows reference audio 1."`）。
    以前这里把三个小标题原样拼成输入 = 把成品骨架当输入，改写器从「组织」
    变成「复述+扩写」。现在只去掉小标题，下面三段的内容照旧全给。

    · 参考素材说明（`h3-manual:248`）：写清每个素材的编号和用途。用途必须落在
      官方那张表里的词上 —— 我们这里是「人物参考（锁定脸/形象）」和
      「视频编辑（对视频某个内容进行增删改）」；官方还写「如果素材中有非常
      想要保持的特征，建议明确写出来」，所以人物那句**把五官原文写出来**
      （`looks` 传的就是定妆照自己的描述，不是我编的形容词）。
      🩸 2026-11-02 实测：不写五官时，改写器产出的 `<Subject 1>` 只有发簪和
      衣服、**零个五官词**，成片保住原片那张脸（SFace 0.09）；唯一换成功的
      那次，正文里有 `keeps the exact face from <Picture 1>: …` 整段五官。
    · 核心创意（`h3-manual:250`）：一句话锁定 主体 / 地点 / 事件 / 题材风格。
    · 画面过程说明（`h3-manual:251`）：按分镜/时间轴写这一段画面怎么走。

    🩸 2026-11-02：以前这里只写了「人物参考图1提供了人物的形象；视频1提供了
    动作、镜头、口型」—— 视频的用途被写成了**动作参考 + 运镜参考**，没有
    「视频编辑」。改写器因此不认「在原片上改」，全片唯一带场景的素材只剩定妆照
    → 成片背景跟着定妆照走。公式三段缺了两段（核心创意、画面过程说明）。
    """
    materials: list[str] = []
    person_pics: list[int] = []
    # 人物图号 → 它在 `materials` 里的下标（多角色时要回头改写那一句，见下面
    # 「能指代清楚」）。
    _mat_person: dict[int, int] = {}
    # 人物图号 → 这张定妆照自己的外观描述（`subject_desc*.json` 的原文）。
    _look_person: dict[int, str] = {}
    # 🩸 2026-11-03：非人物改动的槽位号也要记下来。以前这里只记人物，
    #   于是「换场景/换产品/换服装/换风格」在指令里**只有一句素材说明、
    #   没有一句"换成它"**，后面还跟着「地点…与视频1一致」「其余内容保持不变」——
    #   IR 收到的是自相矛盾的两句话，只能判成"不动"。
    product_pics: list[int] = []
    scene_pics: list[int] = []
    wardrobe_pics: list[int] = []
    style_pics: list[int] = []
    looks = looks or {}
    # 与人物槽位**同序**的盘点记录（`video_edit._span_people` 的产出）。
    # 只用来写方位；给不全就退回泛称，绝不因为缺方位少写一句。
    ppl = list(ppl or [])
    # 🩸 2026-11-03（主人）：**这一段画面里所有的人都点名**，不只点要换的那几个。
    #   只写「右边那位」时，同框有两个男人，IR 只能猜是哪一个（实测它写成
    #   "replaces the man"，定义里也只有 "the man in a black T-shirt"）。
    #   这里拿盘点的 方位+外观 把每个人钉死；来源是 2.1 那一次盘点，不是我编的。
    #   官方 `manual:213` 的写法就是「最后面的小孩」「最左边小孩穿的卡其色外套」
    #   —— 方位 + 可辨识特征，不是只有方位。
    ppl_all = list(ppl_all or [])
    for i, slot in enumerate(slots, 1):
        zh = _zh(slot)
        if zh == "人物":
            person_pics.append(i)
            # ⛔ 2026-11-03 当天曾以 `manual:213`（一句短示例）为由把外观描述整个删掉，
            #   当晚实测（出片 `91977d66`）证明删错了：提示词通篇没有一个五官词，
            #   成片只换了那位女性的裙子，**脸没换**，右边男士更是一处没动。
            #   官方 `manual:248` 同页写的是「如果素材中有非常想要保持的特征，
            #   **建议明确写出来**」+ 用途词表「人物参考 = **锁定脸**/形象」。
            #   外观文本来自定妆照自己的描述文件（`subject_desc*.json`），不是我编的；
            #   多人档把它写进素材说明，单人档保持原句不动（8/19 已经能成）。
            _mat_person[i] = len(materials)
            _look_person[i] = str((looks or {}).get(slot) or "").strip()
            materials.append(f"人物参考图{i}提供了人物的形象")
        elif zh == "商品":
            product_pics.append(i)
            materials.append(f"商品参考图{i}提供了商品的外观，锁定商品")
        elif zh == "场景":
            scene_pics.append(i)
            materials.append(f"场景参考图{i}提供了场景")
        elif zh == "服装":
            wardrobe_pics.append(i)
            materials.append(f"服装参考图{i}提供了服装")
        elif zh == "风格":
            style_pics.append(i)
            materials.append(f"风格参考图{i}提供了画面的风格和色调")

    # 非人物改动 = 「把视频1里的 X 换成什么」。换成的对象有两种来源：
    #   · 用户传了参考图 → 「…参考图N中的X」
    #   · 用户只写了描述（前端允许，`diagnose.vue` 的校验就是"传图**或**写一句"）
    #     → 用用户自己写的那句，**一个字不改**
    # 🩸 2026-11-03：以前这里只认槽位。用户只填描述不传图时槽位根本不存在
    #   （`ref_plan` 会跳过没图的槽），于是 IR 连"要改这个"都不知道，
    #   整段只收到「其余内容保持不变」—— 钱花了，什么都没变。
    _c = dict(changes or {})
    _people_desc = {str(k): str(v) for k, v in (people_desc or {}).items()}
    _num = lambda xs: "、".join(str(x) for x in xs)  # noqa: E731

    def _tgt(pics: list[int], pic_word: str, noun: str, desc: str) -> str:
        """换成的对象：有图写图号（描述作为补充），没图就用用户自己写的那句。"""
        if pics:
            s = f"{pic_word}{_num(pics)}中的{noun}"
            return f"{s}（{desc}）" if desc else s
        return desc

    _deltas: list[str] = []
    _has_product = bool(product_pics) or bool(_c.get("product"))
    _has_scene = bool(scene_pics) or bool(_c.get("scene"))
    _has_wardrobe = bool(wardrobe_pics) or bool(_c.get("wardrobe"))
    # 🩸 2026-11-03：`style_video` = 用户传了一段**风格参考视频**（不是风格图、
    #   也不是风格词）。以前这条路改写器完全看不见：`context_ir` 只收到原片那
    #   一段，句子还说「题材与风格都与视频1一致」—— 真矛盾。现在这段视频会一起
    #   发给改写器（content 顺序 = 原片在前，它就是**视频2**），句子也改口。
    _has_style = bool(style_pics) or bool(_c.get("style")) or bool(style_video)

    if _has_product:
        # 「画面里被换的是哪一件」——用户从盘点列表里点的那件（`product_target`）。
        # 有多件东西的画面里，只写"商品"没有唯一解。
        _pt = str(_c.get("product_target") or "").strip()
        _t = _tgt(product_pics, "商品参考图", "商品", str(_c.get("product_desc") or "").strip())
        if _t:
            _deltas.append(f"视频1画面中{_pt}换成{_t}" if _pt
                           else f"视频1中的商品换成{_t}")
    if _has_scene:
        _t = _tgt(scene_pics, "场景参考图", "场景", str(_c.get("scene_desc") or "").strip())
        if _t:
            _deltas.append(f"视频1中的场景换成{_t}")
    if _has_wardrobe:
        _by = {str(k): str(v).strip()
               for k, v in (_c.get("wardrobe_desc_by_id") or {}).items()
               if str(v).strip()}
        # 🩸 2026-11-03：**只认名单里的人**。前端取消勾选时不会删掉已经填好的
        #   那句描述（`diagnose.vue:2624-2636 pickWardrobe` 只动 `wardrobe_ids`），
        #   后端 `normalize` 也不按名单过滤这个字典（`edit_spec.py:277-286`）。
        #   不筛的话，用户把那个人**取消勾选**之后，句子照样写「她的服装换成…」
        #   —— 用户说不改的人被改了。老编译器没这个毛病（`:1211` 是按
        #   `wardrobe_ids` 遍历的），只有这里按字典键遍历。
        _wids = [str(x) for x in (_c.get("wardrobe_ids") or []) if str(x).strip()]
        if _wids:
            _by = {k: v for k, v in _by.items() if k in _wids}
        _all_w = str(_c.get("wardrobe_desc") or "").strip()
        _tw = _tgt(wardrobe_pics, "服装参考图", "服装", "")
        if _by:
            # 多人换装：谁换哪套是用户逐个人填的，一个一个写
            for _pid, _d in _by.items():
                _who = _people_desc.get(_pid, "")
                _tt = _tw or _d
                _deltas.append(f"{_who}的服装换成{_tt}" if _who
                               else f"视频1中一位人物的服装换成{_tt}")
        elif _tw or _all_w:
            _deltas.append(f"视频1中出镜人物的服装换成{_tw or _all_w}")
    if _has_style:
        # 优先级跟老编译器一致（`edit_spec.py:1326-1334`）：
        # 风格图 > 风格视频 > 风格词 —— 三者同时勾时，前者生效、后者被忽略。
        if style_pics:
            _deltas.append(f"画面的风格和色调改为风格参考图{_num(style_pics)}的风格")
        elif style_video:
            # 编号跟 content 顺序走：原片是视频1，风格片段排在它后面 = 视频2。
            # 「不复制它的画面内容」这句是必要的 —— 否则改写器会把风格片里的
            # 人和场景当成要复刻的素材（`clone_brief.py:355` 给 agent 的同一句）。
            _deltas.append("画面的风格、色调和质感参考视频2，"
                           "只取风格与色调，不复制视频2里的画面内容")
        elif str(_c.get("style") or "").strip():
            _deltas.append(f"画面的风格和色调改为{str(_c.get('style')).strip()}")
    # 边界帧＝上一段成片的最后一帧，这一段从它接着演。官方写法是
    # `<Picture N> is the first frame of [Shot 1]`（`ref-en:62`）——
    # 不告诉改写器这张图干什么用的，它会当成又一张人物图来定义。
    if boundary_pic > 0:
        materials.append(f"图{boundary_pic}是上一段成片的最后一帧，"
                         f"作为这一段的第一帧")
    # 🩸 2026-11-02（缺口一）：换人按**官方换人范例**的写法，不是「视频编辑」。
    #   官方范例 `h3-manual:192`：「参考视频1进行动作模仿。固定机位全景镜头，
    #   正视频中三个穿西装的男人**替换为**三只高度写实的水豚。水豚必须**严格
    #   遵循原视频的运动轨迹**……保持原有的固定机位不变。确保水豚的毛发质感
    #   和光影与环境融合」；同款 `h3-manual:189`「图1的人物**动作、表情与表演
    #   节奏严格参考**输入视频1」。两处用的都是「动作参考 + 替换成」。
    #   用途词表里对应的是「动作参考（锁定动作）」「运镜参考（锁定运镜）」
    #   （`h3-manual:248`）。
    #   保留标记的定性（`ref-en:167`）：`attribute_transfer` = 参考的特征
    #   **转移给另一个可识别主体** ← 换人；`partially_preserved`（`ref-en:166`）
    #   = 内容还在用、部分特征被改掉 ← 改。实测分界见 `H3-CHANGE-LEDGER.md` H16。
    #   场景/背景/光线仍要点名来自视频1：只写「动作、镜头、口型」那版实测
    #   场景被定妆照带走（同素材对照，只差这一句）。
    # 🩸 2026-11-02（缺口三）：音频也要写清用途。官方 `h3-manual:248` 的用途
    #   词表里有「音色参考（锁定音色）」「音频复用（生成视频的音频直接复用
    #   参考音频素材）」「音频部分复用」三档，同段还写「在音频复刻/部分复刻中…
    #   强烈建议补充具体歌词文本内容」。
    #   🩸 实测缺口：音频素材一直**传进了** IR（`prompt_for(audio=…)`），但
    #   `instruction()` 全文一个字都没提它 —— 用途全靠改写器自己猜。它猜成
    #   `fully_copy` 那次，同一份产出的 `non_diegetic_music` 直接是 `N/A`，
    #   原片要是有 BGM 就被判没了。
    #   两种模式的用途不同（`video_edit._audio_track`）：
    #     · `original` = 原片整条音轨 → 音频复用；
    #     · `tts` / `mix` = 我们自己合成的配音轨 → 音色参考，台词跟它走。
    #   编号按类型各算（`ref-en:110`「`<Video N>` and `<Audio N>` are numbered
    #   independently」），所以永远是「音频1」。
    _am = (audio_mode or "").strip().lower()
    if _am == "original":
        materials.append("音频1是视频1的原声轨，成片复用这条原声")
    elif _am:
        materials.append("音频1是成片的配音轨，人物台词按这条音频")
    # 🩸 2026-11-02（缺口二）：把**这一段原片的镜头切点**告诉改写器。
    #   官方要求 `detailed_description` 里每个 `[Shot N]` 以严格递增的切点时间
    #   开头（`base-en:86`「begin each one with a strictly increasing cut time」），
    #   视频编辑的描述详细度按源片复杂度缩放（`ref-en:242`）；官方三镜示例就是
    #   `[Shot 2] At 00:03.000`（`official/dfe52602.txt`）。
    #   🩸 实测缺口：`06386173` 的原片分诊算出 5 个镜头，IR 产出全文只有
    #   `[Shot 1]`、一个 `At 00:` 都没有 —— 切点一直只喂给火山/2.0 的编译器
    #   （`video_edit` 的 `cuts`），**从没进过 IR 的 text**。改写器不知道有几刀，
    #   就按一镜到底写。
    #   切点是**相对段起点**的秒数，与传给 IR 的那段切片同一条时间轴；空列表
    #   （单镜头）时一个字不加，行为与改前一致。
    _cuts = [float(c) for c in (cuts or [])]
    cuts_txt = ("这一段原片有 %d 个镜头，切点在 %s 秒；"
                % (len(_cuts) + 1, "、".join(f"{c:.2f}" for c in _cuts))
                if _cuts else "")
    # 🩸 2026-11-02（H21）：**这一段真实说过的台词，连秒数一起给**。
    #   官方 `h3-manual:248`：「在音频复刻/部分复刻中，如果对于人声对白内容…
    #   的保持有较高的要求，**强烈建议补充具体歌词文本内容**」——我们正是音频
    #   复用（`音频1是视频1的原声轨`），却一直只给音频不给字。
    #   `h3-manual:251`：「**注意台词的长短尽量和镜头长短对齐（这个得强调下，
    #   很多口型问题会来自于这个）**」——不给时间就只能让模型自己排。
    #   🩸 实测（`db253cfc` 2026-11-02）：第 2 段从半句中间切起（4.133s），
    #   改写器靠听音频把上一句「然后我就这一个样品」**补全后当成第 2 段第一句**
    #   → 模型照着又念了一遍，可这段音频里那句只剩尾巴 → 第 2 段嘴型全程对不上。
    #   文字全部来自原片 ASR（`recipe.speech.segments[].chars[]`），一个字不编。
    #   🩸 2026-11-03：每条可以带第 4 项「谁说的」（盘点人物的中文外观）。
    #   以前只给秒数和字，改写器只能听音频猜谁开口；它写出来的正文正是靠
    #   `(S1)/(S2)` 把台词绑到主体上的，猜错就等于让错的人动嘴。查不到说话人时
    #   第 4 项是空串 → 这句退回老格式，**不编人**。
    _ln: list[tuple[float, float, str, str, list]] = []
    for _it in (lines or []):
        _it = tuple(_it)
        if len(_it) < 3:
            continue
        _t = str(_it[2]).strip()
        if not _t:
            continue
        _who = str(_it[3]).strip() if len(_it) > 3 else ""
        # 🩸 2026-11-03：第 5 项 = 字级时间 [(字, 起, 止)]（相对本段起点），
        #   来自 ASR（`_span_script` 带出来的）。跨镜头时靠它在切点处切开台词。
        _ch = list(_it[4]) if len(_it) > 4 and _it[4] else []
        _ln.append((float(_it[0]), float(_it[1]), _t, _who, _ch))
    def _line_txt(s: float, e: float, t: str, w: str) -> str:
        return f"{s:.2f}–{e:.2f} {w}：{t}" if w else f"{s:.2f}–{e:.2f} {t}"

    # 🩸 2026-11-03（主人）：**台词按镜头归位**，不再平铺。
    #   依据（都是官方的）：
    #     · `manual:251`「如果一句台词跨shot，可以用**接着上个shot继续说**这样的
    #       描述表明是跨shot的台词对白」
    #     · `manual:255`「H3 能够响应跨shot（J-cut，L-cut）的台词响应，**只要明确
    #       写出一句台词跨了哪些shot就可以响应**」
    #     · `base-en:142` 跨切点要在连接点标 `<scenetrans>` 并说明音频跨切点继续
    #   🩸 实测翻车（`56b0bb23` 这一单）：平铺给三句，IR 自己分配镜头，把
    #   4.00–6.88 那句（属第 1 镜）写进了 `[Shot 2]`，与 1:1 复用的原声时间轴
    #   打架 —— 提示词说 8.73 秒后才说，音频 4 秒就在说，口型必错。
    #   这层对应关系是**算出来的**，不是判断：切点 + 台词秒数 → 落在哪个区间。
    #   无切点（单镜头）/ 无台词 → 逐字退回原来的平铺写法，行为不变。
    def _group_lines() -> str:
        if not _ln:
            return ""
        if not _cuts:
            return ("这一段原片里说了这些台词，秒数相对本段起点：%s；"
                    % "；".join(_line_txt(x[0], x[1], x[2], x[3]) for x in _ln))
        _n = len(_cuts) + 1
        _groups: list[list[str]] = [[] for _ in range(_n)]

        def _shot_of(t: float) -> int:
            k = 0
            for i, c in enumerate(_cuts):
                if t >= c - 1e-6:
                    k = i + 1
            return k

        for s, e, t, w, ch in _ln:
            k0 = _shot_of(s)
            k1 = _shot_of(e)
            if k0 == k1:
                _groups[k0].append(_line_txt(s, e, t, w))
                continue
            # 🩸 2026-11-03 **切过、已撤回**：按字级时间在切点处把台词切成两截。
            #   实测三次（同一单、同一批素材）：
            #     平铺 → 4.00–6.88 那句被 IR 写进 Shot 2 ❌
            #     按镜头归组 → 写进 Shot 1 ✅
            #     归组 + 切点切开 → 又写进 Shot 2 ❌
            #   两次唯一的变量就是"切开"，撤掉后指令逐字回到 `b3d6978179e8`
            #   （那一版 IR 归镜是对的，缓存还在）。字级时间仍由
            #   `_span_script` 带出来（第 5 项），要重启这条先拿对照再动。
            _groups[k0].append(_line_txt(s, e, t, w)
                               + "（这句跨过切点，接着上一个镜头继续说）")
        _parts: list[str] = []
        for i, g in enumerate(_groups):
            if not g:
                continue
            lo = 0.0 if i == 0 else _cuts[i - 1]
            hi = _cuts[i] if i < len(_cuts) else (float(span_dur) if span_dur else 0.0)
            _rng = (f"{lo:.2f}–{hi:.2f} 秒" if hi > 0 else f"{lo:.2f} 秒起")
            _parts.append(f"第 {i + 1} 个镜头（{_rng}）：" + "；".join(g))
        return ("这一段原片里说了这些台词，秒数相对本段起点，按镜头分：%s；"
                % "；".join(_parts))

    lines_txt = _group_lines()
    # ⛔ 2026-11-03 **试过、已撤回**：把 2.1 的逐镜画面描述整段塞进改写器输入。
    #
    #   为什么撤（官方 `manual-2026-10-28.md` 第 3 章「全能精准编辑与修改」）：
    #   · 3.1 角色与物体编辑（:211）范例就一句 ——「把视频中的猫换成狗」；
    #     :213「视频1中最后面的小孩换成图1中的金毛狗，视频1中最左边小孩穿的
    #     卡其色外套改成图2中的牛仔外套」；
    #   · 3.2 场景与视觉效果编辑（:221）——「视频1窗外的场景改成图1」。
    #   **第 3 章所有编辑范例都是一句话，没有一条把原片画面逐镜描述一遍。**
    #   3.4 说的「准确执行局部修改与细化要求，同时保持未编辑内容相对稳定」
    #   （:206）是**指令层面的能力**，不是靠复述原片换来的。
    #   而逐镜描述写的是原片画面（含原片人物长相）—— 塞进去恰恰可能反过来
    #   强化"保留原片那张脸"，与 §15「传得太全 → 重拍原片」同一类病。
    #   要重新启用，先拿 3.1 / 3.2 的官方体裁出一次对照片，别直接加回来。
    if person_pics:
        # 🩸 2026-11-02（H19）：双人换人不能只点名图1。
        #   实测 `1b3df54b` 11:48 那份：指令只写「替换为图1中的人物」，改写器
        #   就只定义 `<Subject 1>`，**`<Picture 2>` 发出去了却全文零引用**，
        #   正文出现「两个年轻男人」但谁也没定义。同素材 08:51 写「视频编辑」
        #   那版定义齐了 3 个 Subject（`<Picture 1><Picture 2>` 全用上）。
        #   官方依据 `ref-en:37`：每个要被单独跟踪的素材都要有自己的定义行，
        #   `<Picture N>` 只有在「仅作来源、不单独使用」时才并进别人的定义。
        #   官方换人范例本身就是复数对应 —— `h3-manual:192`「视频中三个穿西装
        #   的男人**替换为**三只高度写实的水豚」。
        pics = "、".join(f"图{i}" for i in person_pics)
        # 🩸 2026-11-02（H19 第二步）：**要不要写方位，看画面里有几个人**，
        #   不看上传了几张图。主人点的三种情形：
        #     · 原片本来就一个人（`frame_n <= 1`）→ 没有"哪一位"的问题，
        #       写「左边那位」反而是在给一个不存在的区分；
        #     · 原片多人、只换其中一位（图比人少）→ **必须**写清是哪一位，
        #       否则模型可能去换没勾的那个人；
        #     · 原片多人、全部替换（图数=人数）→ 逐张指派，且不能说
        #       「其余保持原样」（没有"其余"）。
        #   方位来自盘点 `inventory.people[].position`，不是现编的。
        #   🩸 2026-11-03：方位认不出来时用**盘点给的外观描述**兜底。
        #   两份消歧信息都来自 2.1 那一次盘点，不是我编的；官方 `ref-en:246`
        #   要的本来就是「特征 + 画面位置」两样。以前只认方位，而前端 chips
        #   显示的是 `desc_zh`（`vision_plan.summary` 里根本没有 position）——
        #   用户按"长相"挑人，IR 按"方位"换人，两边不是同一套线索。
        _pairs = []
        for k, i in enumerate(person_pics):
            pos = ""
            desc = ""
            if k < len(ppl):
                _p = ppl[k] or {}
                pos = _pos_zh(_p.get("position"))
                desc = str(_p.get("desc_zh") or "").strip()
            _pairs.append((i, pos, desc))

        def _who_of(pos: str, desc: str) -> str:
            """这一位在画面里怎么称呼：方位优先，没方位就用盘点给的长相。"""
            if pos:
                return f"{pos}那位"
            return f"原片里{desc}那位"
        # 🩸 2026-11-02：这里有两个**不同**的量，别再混着说（主人当场点破）：
        #     K = 这一段画面里有几个人（盘点事实）      → `frame_n`
        #     M = 这次要换几个人（发出去的人物图张数）  → `len(person_pics)`
        #   要不要写方位取决于 K，以及"能不能拿到方位"；
        #   写不写「其余保持原样」取决于 M 与 K 的大小。
        #   ⚠️ `K == 0` 是**盘点没给人数**，不等于"画面只有一个人" —— 两者必须分开：
        #      · K == 1  → 确实没第二个人可比，写方位是凭空造区分 → 不写
        #      · K >= 2  → 不写方位就是在猜换谁 → 有方位就写，没方位退回泛称
        #      · K == 0  → 缺数据；方位**是逐人的**，有就写（写了不会错），没有才泛称
        _k = int(frame_n or 0)
        _m = len(person_pics)
        _all_who = all(pos or desc for _, pos, desc in _pairs)
        _has_rest = 1 <= _k and _m < _k

        def _short(desc: str) -> str:
            """盘点的中文外观取**前两项**（发型/显著标记 或 发型/上衣）。

            官方范例指认人用的就是这种短名词短语（`manual:213`
            「最左边小孩穿的卡其色外套」），不是整段画像复述。
            """
            xs = [x.strip() for x in str(desc or "").replace("；", "，").split("，")]
            return "、".join([x for x in xs if x][:2])

        # 盘点上的人物 id → 图号（只对**要换**的人有）
        _pic_by_id: dict[str, int] = {}
        for _k2, _i2 in enumerate(person_pics):
            if _k2 < len(ppl):
                _pid2 = str((ppl[_k2] or {}).get("id") or "")
                if _pid2:
                    _pic_by_id[_pid2] = _i2

        # 🩸 2026-11-03（主人）：**多个角色必须"能指代清楚"** —— 官方 `manual:248`
        #   原文：「@图片1 提供了xx角色的形象（**如果有多个角色，需要能指代清楚**）」；
        #   同段用途词表写死「人物参考 = **锁定脸**/形象」。
        #   实测缺口（两张人物图）：素材说明是**逐字相同的两句话**
        #     「人物参考图1提供了人物的形象；人物参考图2提供了人物的形象」
        #   —— IR 无从知道图1对应画面里哪一位，产出的定义只剩
        #     `<Subject 1> is the character with long, wavy dark hair in <Picture 1>`
        #   **一个字都没说脸来自图**；官方模板 `ref-en:57` 是
        #     `<Subject 1> is the woman whose appearance comes from <Picture 1>
        #      and whose walking motion comes from <Video 1>.`
        #   人眼验收：多人图 **0/12**、单人图 8/19 —— 缺口只在"多角色"这一档，
        #   所以这一句只改多人的，单人那句一个字不动（避免动到已经能成的档）。
        if len(person_pics) >= 2:
            for _p in ppl_all:
                _pic3 = _pic_by_id.get(str(_p.get("id") or ""))
                _mi = _mat_person.get(_pic3) if _pic3 else None
                if _mi is None:
                    continue
                _pos3 = _pos_zh(_p.get("position"))
                # 🩸 **只写方位，绝不写原片那位的长相特征。**
                #   第一版写了「图1提供了视频1中左边黑色高马尾长发、额间有红色痣
                #   那位的形象」，实测 IR 原样吸收成
                #     `<Subject 1> is the long-haired woman with a red dot on her
                #      forehead from <Picture 1>`
                #   —— "额间红痣"是**原片那位**的特征（`inventory` 的 P1），
                #   图1本人是「深棕黑大波浪、无红痣」（`subject_desc.json`）。
                #   等于告诉模型"这张图就是原片那个人"，脸自然不换。
                #   官方 `manual:248` 说的是「@图片1 提供了**xx角色**的形象」——
                #   角色用方位指代就够了，原片那位的长相属于换人句，不属于这里。
                _ref3 = (f"{_pos3}这个角色" if _pos3 else "一位角色")
                _lk = _look_person.get(_pic3, "")
                _face = f"（{_lk}）" if _lk else ""
                materials[_mi] = (f"人物参考图{_pic3}提供了视频1中{_ref3}的形象"
                                  f"{_face}，锁定这张脸")

        _can_all = (len(ppl_all) >= 2 and len(_pic_by_id) == _m
                    and all((_pos_zh(_p.get("position"))
                             or _short(str(_p.get("desc_zh") or "")))
                            for _p in ppl_all)
                    and all(str(_p.get("id") or "") for _p in ppl_all))
        if _can_all:
            # 只写**要换的**那几位，不换的一个字不提 —— `manual:211/:213/:221`
            # 三条官方范例里，没被点到的人和物就是不动，官方从没写过"保持原样"。
            #
            # 🩸 2026-11-03 撤回「不换的也写『保持原样』」：实测 30 个出片记录里
            #   换成功的 6 条，`<Subject>` **全部来自 `<Picture N>`**，原片上没有任何
            #   人被定义成 Subject；写了"保持原样"的那几版，IR 会把它定义成
            #   `<Subject 3> … from <Video 1>`，等于告诉模型"原片的身份是主体"，
            #   最省力的解就是照原片重画。本单两次出片 SFace 0.146 / 0.164，
            #   对照成功样本 0.499 / 0.574 / 0.607 / 0.627 / 0.634。
            _parts = []
            for _p in ppl_all:
                _pic2 = _pic_by_id.get(str(_p.get("id") or ""))
                if not _pic2:
                    continue
                _pos2 = _pos_zh(_p.get("position"))
                _d2 = _short(str(_p.get("desc_zh") or ""))
                _ref = (f"{_pos2}{_d2}那位" if (_pos2 and _d2)
                        else (f"{_pos2}那位" if _pos2 else f"{_d2}那位"))
                _parts.append(f"视频1中{_ref}换成图{_pic2}中的人物")
            _repl = "；".join(_parts)
            _who = f"{pics}中的人物"
        elif _k != 1 and _all_who:
            # 🩸 2026-11-03：改成官方第 3 章编辑体裁的原句式 ——
            #   `manual:213`「视频1中最后面的小孩换成图1中的金毛狗」。
            #   以前写的是「视频1中的出镜人物替换为人物参考图中的人物：图1中的人物
            #   替换左边那位…」—— 主客体次序反了，而且"替换为/保持"这类词整句只占
            #   一个小从句，其余五句全在说"跟原片一样"，模型最省力的解就是重画原片。
            _assign = "，".join(f"视频1中{_who_of(pos, desc)}换成图{i}中的人物"
                                for i, pos, desc in _pairs)
            _repl = (_assign + ("，其余出镜人物保持原样" if _has_rest else ""))
            _who = f"{pics}中的人物"
        elif _k >= 2:
            # 方位和长相都缺就整句退回泛称 —— 半对半错比全不说更容易让模型认错人
            # 同一条官方句式（`manual:211/:213` 全是「换成」），差别只在
            # 认不出方位/长相时才退回泛称
            if _m == 1 and (_pairs[0][1] or _pairs[0][2]):
                _pick = (f"视频1中{_who_of(_pairs[0][1], _pairs[0][2])}"
                         f"换成{pics}中的人物")
            else:
                _pick = (f"视频1中其中一位换成{pics}中的人物" if _m == 1
                         else f"视频1中的出镜人物分别换成{pics}中的人物")
            _repl = _pick + ("，其余出镜人物保持原样" if _has_rest else "")
            _who = f"{pics}中的人物"
        else:
            # K == 1（确认只有一个人）或没有可用方位：不写方位
            _rel = ("视频1中的人物换成" if _m == 1
                    else "视频1中的出镜人物分别换成")
            _repl = f"{_rel}{pics}中的人物"
            _who = f"{pics}中的人物"
        # ⛔ **2026-11-03 已作废**（主人第三次指出）：下面这套五段结构出自
        #   `h3-manual:192` 的**第 2 章 2.2 动作参考**，是"照着参考片重新生成"的体裁；
        #   我们的任务是第 3 章**编辑**。保留注释只为说明当时为什么这么写，
        #   **代码已不再按它出句**（见下面 `materials.append` 处的说明）。
        # 🩸 2026-11-02（H20）：**照 `h3-manual:192` 的原句结构写，不用「锁定」句式**。
        #   官方换人范例五段：
        #     ①「参考视频1进行动作模仿」
        #     ②「视频中三个穿西装的男人**替换为**三只高度写实的水豚」
        #     ③「水豚必须**严格遵循原视频的运动轨迹**」
        #     ④「保持原有的固定机位不变」
        #     ⑤「确保水豚的毛发质感和光影与环境融合」
        #   H16 那版把它压成「视频1提供了动作参考和运镜参考，**锁定**动作和运镜」，
        #   实测产出把 `<Video 1>` 标成 `fully_preserved`（= 原片原样保留），
        #   于是成片只换了衣服发型、**脸没换**（SFace p90 0.171，阈值 0.363）。
        #   官方要的定性是 `attribute_transfer`（`ref-en:167`：特征转移给另一个
        #   可识别主体），而 `fully_preserved` 说的是"什么都没变"。
        # 🩸 2026-11-03：其余改动（换商品/场景/服装/风格）接在换人句后面。
        #   以前这些改动**一个字都进不来**，指令里只剩「其余内容保持不变」——
        #   用户勾了换场景、传了场景图，IR 收到的却是"什么都不改"。
        _more = ("；" + "；".join(_deltas)) if _deltas else ""
        # 🩸 2026-11-03（主人定的）：这一段原来跟了四句"要保持原样"——
        #   「图N必须严格遵循原视频的运动轨迹，保持原有的机位和分镜不变」
        #   「场景、背景、光线也来自视频1，光影与环境与原片融合」
        #   「主体是…，地点、事件、题材与风格都与视频1一致」
        #   「按视频1原样的分镜逐镜复刻，景别、构图、运镜、动作、口型都与视频1一致」
        #   数下来 **6 处"保持/一致/复刻"，0 处"换成"** —— 整句的主语变成了
        #   "复刻原片"，换人只是从句，模型最省力的解就是照原片重画（脸不换）。
        #   官方第 3 章编辑范例（`:211/:213/:221`）全是一句话，`保持` 只在
        #   3.4 `:206` 出现一次，而且是原则：「准确执行局部修改与细化要求，
        #   同时保持未编辑内容相对稳定」。这里就按那个口径收尾。
        # 🩸 2026-11-03（主人第三次指同一件事）：**换人也走第 3 章「编辑」体裁，
        #   不再写「参考视频1进行动作模仿」**。
        #   依据：`manual:192`（水豚那条）是**第 2 章 2.2 动作参考**——「参考视频1
        #   进行动作模仿…必须严格遵循原视频的运动轨迹…保持原有的固定机位不变」，
        #   那是"照着参考片重新生成一段"。我们的任务在原片上改一个人，
        #   属于第 3 章编辑（`:200-213`），官方范例全书都是
        #   「把视频中的猫换成狗」「视频1中最后面的小孩换成图1中的金毛狗」——
        #   **没有一句"动作模仿/保持机位"**：编辑体裁的默认语义就是"没说的不动"，
        #   运镜本来就在原片里，不需要（也不该）再由我们锁一遍。
        #   以前换人分支写动作模仿、非换人分支写「视频编辑」，同一段里两种体裁。
        # 🩸 2026-11-03：**必须说清"成片里出现的就是图里这个人本人"**。
        #   少了这句，IR 会把换人落成 `attribute_transfer`（官方 `ref-en:167`：
        #   「Referenced characteristics are transferred to **a different
        #   identifiable target subject**」= 主体仍是原片那位，图只提供特征），
        #   成片于是"原片的人留在原地、只被重画一遍"。实测原文（`e57ad5b6967f`）：
        #     <Subject 1>: attribute_transfer - <Subject 1>'s appearance … replace
        #     the woman with the high ponytail and yin-yang top in <Video 1>,
        #     while retaining her placement on the left and her actions.
        #   写法照抄我们自己换成功过的那条（`db253cfc`，SFace 0.574，retention 写
        #   `fully_preserved`）：`主体是图1中的人物` / `只替换出镜人物`。
        _self = (f"。成片里出现的就是{pics}中的人物本人"
                 + ("，只替换出镜人物" if not _deltas else ""))
        materials.append("视频1是被编辑的原片，视频编辑：在视频1上做改动："
                         f"{_repl}{_self}{_more}")
        _idea = ""
    else:
        materials.append("视频1是被编辑的原片，视频编辑：在视频1上做改动"
                         + ("：" + "；".join(_deltas) if _deltas else ""))
        _idea = ""

    # 🩸 2026-11-03：**核心创意句不能再无条件写「地点…与视频1一致」**。
    #   换场景/风格时它和上面的替换句直接打架（实跑证据：同一段里既写
    #   「场景替换为场景参考图1」又写「地点…与视频1一致」）。这里只保留
    #   **这次真没动**的那些维度；一个都没动时输出与改前逐字相同。
    #   ⚠️ 判"动没动"要用 `_has_*`（勾选/描述也算），不能只看槽位 ——
    #   只填描述不传图时槽位是空的，只看槽位会照样写出「地点与视频1一致」。
    _keep_dims: list[str] = []
    # 换人时整段不写这些 —— 由官方 `:206` 那句"保持相对稳定"统一收口（见上）
    if not person_pics:
        if not _has_product:
            _keep_dims.append("主体")
        if not _has_scene:
            _keep_dims.append("地点")
        _keep_dims.append("事件")
        if not _has_style:
            _keep_dims.append("题材与风格")
    if _keep_dims:
        _kept_txt = "、".join(_keep_dims) + "都与视频1一致"
        idea = (f"{_idea}，{_kept_txt}" if _idea else _kept_txt)
    else:
        idea = _idea

    if person_pics:
        # 官方 `manual:206` 原话：「准确执行局部修改与细化要求，**同时保持未编辑
        # 内容相对稳定**」。整段编辑提示词里"保持"只该出现这一次。
        process = (cuts_txt + lines_txt + "其余未编辑的内容保持相对稳定")
    else:
        process = (cuts_txt + lines_txt +
                   "按视频1原样的分镜逐镜复刻，其余内容保持不变")

    # 🩸 2026-11-02：**交给改写器的是自然语言，不是一份已经拼好的提示词**。
    #   官方调 H3-Context-IR 时 text 只有一句话
    #   （`scripts/readme/full-2k-ref2va-h3-context-ir.sh`：
    #    "Character speaks: … Voice timbre follows reference audio 1."）；
    #   而 `h3-manual:244` 那条「完整提示词 = 参考素材说明 + 核心创意 + 画面过程说明」
    #   说的是**改写器的输出**该长什么样，不是它的输入。
    #   以前把这三个小标题原样喂进去，改写器拿到一份"成品骨架"，任务从
    #   「组织」变成「复述+扩写」—— 实测 4 份正文里 3 份反复写
    #   original woman/man，脸没换（0.021 / 0.069 / −0.012）。
    #   ⚠️ 这一步**只去掉三个小标题**，内容一个词都没增删（单一变量）。
    # 换人时不写「核心创意句」（`idea` 为空）→ 别留一个空句号
    text = (f"{'；'.join(materials)}。{process}。" if not idea
            else f"{'；'.join(materials)}。{idea}。{process}。")
    # 用户自己填的补充说明：原样接在最后，交给改写器理解（它本身就是中文进、
    # 结构化英文出）。空就一个字不加。
    user = (extra or "").strip()
    return (f"{text}\n补充要求：{user}" if user else text).strip()


def sig_of(path, seg=None) -> str:
    """素材指纹：**原片内容 + 区间**，不是切片文件的字节。

    🩸 2026-11-02：以前指纹用的是切片文件（`seg_00N.mp4`）的 sha —— 同一段
    原片每次重切都生成一个新文件，字节只要差一个字节（容器时间戳/元数据），
    指纹就变。于是「预调好、审过的那份提示词」出片时**永远命不中**，改写器
    每次重新抽一次（同输入两次判出过 `video editing` 和 `reference generation`）。
    改成「原片 sha + 区间」之后，重切不影响指纹，预调的结果能稳定复用。
    """
    if not path:
        return ""
    try:
        p = Path(path)
        src = f"{_file_sha(p)}:{p.name}"
    except OSError:
        return str(path)
    if seg:
        a, b = float(seg[0]), float(seg[1])
        return f"{src}|{a:.3f}-{b:.3f}"
    return src


def _file_sha(path: Path) -> str:
    """整文件 sha1（按 1MB 分块读；大视频不爆内存）。"""
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _sha(paths) -> str:
    h = hashlib.sha1()
    for p in paths:
        if not p:
            continue
        try:
            h.update(Path(p).read_bytes())
        except OSError:
            h.update(str(p).encode())
    return h.hexdigest()[:12]


def _fp(text: str, dur, images, *, video=None, video_src: str = "",
        video_span=None, audio=None, audio_src: str = "",
        audio_span=None, style=None, style_src: str = "",
        style_span=None) -> str:
    """改写器输入的指纹（**唯一算法**，`prompt_sig` 与 `prompt_for` 共用）。

    🩸 2026-11-02：这两处以前各算各的。缓存键靠人工标记 `:irN` 兜底 ——
    只要忘了升版，改写器换了词、段缓存照样命中旧段（实测：07:05 预调的新词
    出片时一次都没被用上，三次渲染拿回同一个 476,680 字节的旧片）。
    现在键里带这个指纹，词一变键必变，不再靠人记得升版。
    """
    v_sig = sig_of(video_src, video_span) if video_src else _sha([video])
    a_sig = sig_of(audio_src, audio_span) if audio_src else _sha([audio])
    # 🩸 风格参考视频只在**有**的时候才进指纹：没风格视频的任务，指纹与以前
    #   逐字相同（不动已缓存的那些改写结果，不白花一次重抽的钱）。
    s_sig = (sig_of(style_src, style_span) if style_src
             else (_sha([style]) if style else ""))
    key = (f"{text}|{int(dur)}|{v_sig}|{_sha(list(images or []))}"
           f"|{a_sig}" + (f"|{s_sig}" if s_sig else ""))
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def prompt_sig(*, dur, images, slots: list[str],
               extra: str = "", boundary_pic: int = 0,
               video_src: str = "", video_span=None,
               audio_src: str = "", audio_span=None,
               looks: dict | None = None,
               cuts: list[float] | None = None,
               span_dur: float = 0.0,
               audio_mode: str = "",
               ppl: list | None = None,
               ppl_all: list | None = None,
               frame_n: int = 0,
               lines: list | None = None,
               changes: dict | None = None,
               people_desc: dict | None = None,
               style_src: str = "", style_span=None) -> str:
    """这一次改写器会拿到的**输入指纹**——不调接口、不花钱。

    出片核心要在「查段缓存之前」知道这份词会不会变，所以不能在这里花 ¥0.11；
    真正的文本由 `prompt_for` 产出（命中同一指纹，落盘复用）。

    """
    text = instruction(list(slots or []), looks=looks,
                       boundary_pic=int(boundary_pic or 0), extra=extra,
                       cuts=cuts, span_dur=span_dur,
                       audio_mode=audio_mode, ppl=ppl,
                       ppl_all=ppl_all,
                       frame_n=int(frame_n or 0), lines=lines,
                       changes=changes, people_desc=people_desc,
                       style_video=bool(style_src))
    return _fp(text, dur, images, video_src=video_src, video_span=video_span,
               audio_src=audio_src, audio_span=audio_span,
               style_src=style_src, style_span=style_span)


#: 改写器是**抽样**的，同一输入也会抽出不同结果：不合格就重抽（每次约 ¥0.11）
_IR_MAX_TRY = 3

#: 六段式必须齐全（少一段 = 改写产出被截断）
_IR_SECTIONS = ("subject_definitions", "summary", "retention_analysis",
                "detailed_description", "overall_soundscape",
                "non_diegetic_music")


def _ir_defects(body: str, *, n_replace: int, n_shots: int) -> list[str]:
    """改写器产出的**结构完整性**检查：返回缺陷列表，空 = 完整。

    🩸 2026-11-03 主人定：「质量判定全撤，机械检查留着」。所以这里只查
      **这份产出有没有被截断 / 少写一段**，不判断它写得好不好：
      1. 六段齐全 —— 少段说明产出被截断（`ref-en` 的六段结构）
      2. `[Shot N]` 的**不同编号数** = 切点数 + 1 —— 少镜 = 后半段没写进去。
         注意要数"不同的 N"，不能数出现次数：`retention_analysis` 里
         `(appears in [Shot 1])` 会和正文重复计一次。

    ⛔ **判过、已撤掉的"质量"判据**（别再自己加回来）：
      · 要求 `attribute_transfer` —— 唯一真换成的那条（`db253cfc`，share 0.98）
        里是 0 条，这条会把好样本判死；
      · 要求 `non_diegetic_music` 必须是 N/A —— 属于"写得好不好"，
        不是结构完整性；
      · 要求正文出现 replace 关系 —— 同上，是内容判断不是结构判断。
    `n_replace` 参数保留只为调用方不用改签名。
    """
    d: list[str] = []
    for name in _IR_SECTIONS:
        if f"{name}:" not in body:
            d.append(f"缺段 {name}")
    shots = len(set(re.findall(r"\[Shot (\d+)\]", body)))
    if n_shots and shots != n_shots:
        d.append(f"[Shot N] {shots}≠{n_shots}")
    return d


def _swap_marks(body: str, pics: list[int]) -> str:
    """换人时把**图片来源的那几个 Subject** 的保留标记校正成 `fully_preserved`。

    官方给的是一张对照表（`ref-en:163-168`）：

      | `fully_preserved`   | The defined role of the referenced content is **fully preserved** |
      | `attribute_transfer`| Referenced characteristics are transferred to **a different
                             identifiable target subject** |

    「把原片左边那位换成图1里的人」要的是**图1这个人本人在成片里出现**，
    属 `fully_preserved`；写成 `attribute_transfer` 等于告诉模型
    "原片那位留着，把图1的特征搬过去" —— 实测产出的原句就是：

      <Subject 1>: attribute_transfer - <Subject 1>'s appearance … replace the
      woman with the high ponytail and yin-yang top in <Video 1>, while retaining
      her placement on the left and her actions.

    成片于是"人还是原片的人，只被重画一遍"（SFace 0.146 / 0.164）。
    26 条出片记录里换成功的 7 条，Subject 行 6 条写的是 `fully_preserved`。

    只改**定义里引用了人物图的那几个 Subject**，商品/服装/场景不动。
    """
    if not pics:
        return body
    if "subject_definitions:" not in body or "retention_analysis:" not in body:
        return body
    head, rest = body.split("subject_definitions:", 1)
    sd, tail = rest.split("summary:", 1)
    want = {str(k) for k in pics}
    # 按 `<Subject N>` 切开，看紧跟它的那段定义引用了哪张图
    chunks = re.split(r"(<Subject\s+(\d+)>)", sd)
    marks: set[str] = set()
    i = 1
    while i + 2 <= len(chunks):
        num, seg = chunks[i + 1], chunks[i + 2]
        cite = set(re.findall(r"<Picture\s+(\d+)>", seg))
        if cite & want:
            marks.add(num)
        i += 3
    if not marks:
        return body
    ra, post = tail.split("retention_analysis:", 1)
    # 🩸 切的是 `post`（`retention_analysis:` **之后**那段），不是 `ra` ——
    #   写成 `ra` 就只改 summary，标记一个字都不动（第一版就是这么错的）。
    ret, tail2 = post.split("detailed_description:", 1)
    ret = re.sub(r"(<Subject\s+(\d+)>\s*\([^)]*\)\s*:\s*)(attribute_transfer)",
                 lambda m: m.group(1) + ("fully_preserved"
                                         if m.group(2) in marks else m.group(3)),
                 ret)
    return (f"{head}subject_definitions:{sd}summary:{ra}"
            f"retention_analysis:{ret}detailed_description:{tail2}")


#: 盘点方位 → 英文里指认原片那个人的说法（A 骨架里这半句就靠位置认人）
_POS_EN = {"left": "on the left", "right": "on the right",
           "center": "in the center", "middle": "in the center",
           "front": "in the foreground", "back": "in the background",
           "top-left": "in the upper left", "top": "in the upper part",
           "top-right": "in the upper right",
           "bottom-left": "in the lower left", "bottom": "in the lower part",
           "bottom-right": "in the lower right"}

_VID1_LINE = ("<Video 1> is the source video for the target video edit, providing the "
              "original shot structure, camera movement, on-screen action, cuts and "
              "timing. It is not a source for target identity, clothing, environment, "
              "watermark, logos, or text.")
_AUD1_LINE = ("<Audio 1> is the complete synchronized audio of <Video 1>, reused as the "
              "target video's final soundtrack.")


def _lev(a: str, b: str) -> int:
    """编辑距离（只用来判"是不是同一句话"）。长度差超过 2 直接返回 99。"""
    if abs(len(a) - len(b)) > 2:
        return 99
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[-1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _shots(body: str) -> str:
    """按官方 `base-en.txt:86-90` 校正 `[Shot N]` 的时间写法（机械校正，不改内容）。

    原文：「Do not add a timestamp to the first shot… begin each one with a
    strictly increasing cut time」，示例是 `[Shot 2] At 00:03.500`。

    · 改写器给 `[Shot 1]` 也加了 `At 00:00.000,` → 官方明写第一镜**不要**时间戳，删掉
    · 改写器写成 `At 08.730`（缺"分:"）→ 补成 `At 00:08.730`
    """
    body = re.sub(r"(\[Shot\s+1\])\s*At\s+\d{1,2}:\d{2}\.\d{1,3}[,，]?\s*([a-z])",
                  lambda m: f"{m.group(1)} {m.group(2).upper()}", body)
    body = re.sub(r"\[Shot\s+(\d+)\]\s*At\s+(\d{1,2})\.(\d{1,3})",
                  lambda m: f"[Shot {m.group(1)}] At 00:{int(m.group(2)):02d}."
                            f"{m.group(3)}", body)
    return body


def _restore_lines(body: str, lines) -> str:
    """把 `<d>[Chinese] …</d>` 的台词还原成 ASR 原文。

    依据 `manual-2026-10-28.md:248`：「在音频复刻/部分复刻中，如果对于人声对白
    内容…的保持有较高的要求，**强烈建议补充具体歌词文本内容**」——我们给的**就是
    原文**，改写器自作主张改一个字，成片口型就跟着念错。
    实测 `cfb9c0ed9e77`：ASR 是「先把今天的水缸**叼**满再说」，
    改写器写成「水缸**挑**满再说」（它按"讲得通"改的，原台词是僵尸设定）。

    只在"最接近的那句差 ≤2 个字"时才还原，差得远就不动（可能它重排了分句）。
    """
    texts = [str(x[2]).strip() for x in (lines or [])
             if len(x) > 2 and str(x[2]).strip()]
    if not texts:
        return body

    def fix(m):
        inner = m.group(2).strip()
        if inner in texts:
            return m.group(0)
        best = min(texts, key=lambda t: _lev(inner, t))
        if 0 < _lev(inner, best) <= 2:
            return f"{m.group(1)}{best}{m.group(3)}"
        return m.group(0)

    return re.sub(r"(<d>\[Chinese\]\s*)(.*?)(\s*</d>)", fix, body)


def _skeleton(body: str, pairs: list[tuple[int, str]], *, has_audio: bool,
              lines=None) -> str:
    """把改写器产出补齐成**别人跑通的那套骨架**（三处，都是照抄，不是自造）。

    出处：
      · `github.com/lshhhhhhh/ai-school-op` `docs/02-人物替换.md` —— 73 个单元、
        118 个 H3 版本、人工逐镜验收；63 份通过的提示词在 `prompts/`。
        它的每个 Subject 都是**两截**：
        `… is the girl whose appearance comes from <Picture 1>, with …, **and whose
        position, pose and motion come from the tanned short-haired girl in
        <Video 1>**.` —— 我们只有前截。
        它的 summary 前缀固定带 `reference generation`，`<Video 1>` 单列在第一行。
      · `github.com/siyuan-liu31/minimax-h3-video-studio`
        `skills/h3-dance-replication/references/prompt-pattern.md` —— `<Video 1>` 的定义
        里带**排除句**：`It is not a source for target identity, clothing, environment,
        watermark, logos, or text.`
      · 官方 `ref-en:37`：每个要单独跟踪的条目都占一行。

    `pairs` = [(图号, 中文方位)]，只处理**引用了人物图**的那几个 Subject。
    重复调用安全（已经有半句的不再加）。
    """
    if not pairs:
        return body
    if "subject_definitions:" not in body or "summary:" not in body:
        return body
    head, rest = body.split("subject_definitions:", 1)
    sd, tail = rest.split("summary:", 1)

    # ① `<Video 1>` / `<Audio 1>` 各占一行（官方 ref-en:37；A/B 两套骨架都这么写）
    # 🩸 2026-11-03：改写器会把 `<Video 1> is …` **夹在 Subject 段落中间**。
    #   实测 `8d73580c278a` 的原文：
    #     `<Subject 2> is the man wearing glasses from <Picture 2>. <Video 1> is
    #      the source video being edited, and whose position, pose and motion come
    #      from the performer on the right in <Video 1>.`
    #   —— 后半句本该属于 `<Subject 2>`，却挂到了 `<Video 1>` 头上，Subject 2
    #   于是**没有位置/动作来源**。先把这种行内定义整句剔掉，再按官方单列一行。
    # 连官方标准行里的第二句排除句一起删，重复调用才不会越拼越长。
    #   行尾只吃空格/制表符，不吃换行 —— 否则会把 `summary:` 粘到上一行。
    sd = re.sub(r"<Video 1>\s+is\s[^.]*\.(?:\s*It is not a source[^.]*\.)?[ \t]*", "", sd)
    sd = re.sub(r"<Audio 1>\s+is\s[^.]*\.[ \t]*", "", sd)
    # 清掉删定义后留下的空行，否则重复调用会越堆越多（幂等）。
    sd = sd.lstrip("\n")
    lead = "\n" + _VID1_LINE + "\n"
    if has_audio:
        lead += _AUD1_LINE + "\n"
    lead += "\n"

    # ② 人物 Subject 补「位置/姿势/动作来自原片哪个人」那半句
    want = {int(pic): _POS_EN.get(str(pos or "").strip().lower(), "")
            for pic, pos in pairs}
    chunks = re.split(r"(<Subject\s+(\d+)>)", sd)
    out: list[str] = [chunks[0]]
    i = 1
    while i + 2 <= len(chunks):
        label, num, seg = chunks[i], chunks[i + 1], chunks[i + 2]
        cite = [int(x) for x in re.findall(r"<Picture\s+(\d+)>", seg)]
        where = next((want[c] for c in cite if want.get(c)), "")
        if where and "position, pose and motion come from" not in seg:
            # 半句只能挂在**这位 Subject 自己的定义**末尾：段里若已经出现了下一条
            # `<Video N>` / `<Audio N>` 定义，就在那儿断开，别把半句挂到别的条目头上。
            _m2 = re.search(r"<(?:Video|Audio)\s+\d+>", seg)
            _cut = _m2.start() if _m2 else len(seg)
            _keep, _rest2 = seg[:_cut], seg[_cut:]
            t = _keep.rstrip()
            # 保留原来的行尾空白：两段定义可能挤在同一行，吃掉空格会粘成
            # `<Video 1>.<Subject 2>`。
            tail_ws = _keep[len(t):]
            dot = "." if t.endswith(".") else ""
            if dot:
                t = t[:-1]
            seg = (f"{t}, and whose position, pose and motion come from the "
                   f"performer {where} in <Video 1>.{tail_ws}{_rest2}")
        # ⚠️ 只拼 `label` 和 `seg`：`num` 是 `(\d+)` 那个捕获组，数字已经在
        #    `label` 里了，拼进去会变成 `<Subject 1>1`。
        out.extend([label, seg])
        i += 3
    # `re.split` 每命中一个 Subject 产出 3 段（前文 + 标签 + 编号），
    # 所以循环走完就已经把整段拼全了，末尾不能再补一次（补了就重复最后一段）。
    sd = lead + "".join(out)

    # ③ summary 任务类型补 `reference generation`（官方 `ref-en:134`：
    #    图片给"角色"提供生成依据就是这个类型）
    tail = re.sub(r"\[video editing\+? ?\+? ?audio reuse\]",
                  "[video editing + reference generation + audio reuse]", tail, count=1)
    tail = re.sub(r"\[video editing\]",
                  "[video editing + reference generation]", tail, count=1)
    body = f"{head}subject_definitions:{sd}summary:{tail}"
    return _restore_lines(_shots(body), lines)


def prompt_for(cid: str, n: int, *, video: Path, images: list,
               slots: list[str], audio: Path | None, dur: int,
               extra: str = "", boundary_pic: int = 0,
               video_src: str = "", video_span=None,
               audio_src: str = "", audio_span=None,
               looks: dict | None = None,
               cuts: list[float] | None = None,
               span_dur: float = 0.0,
               audio_mode: str = "",
               ppl: list | None = None,
               ppl_all: list | None = None,
               frame_n: int = 0,
               lines: list | None = None,
               changes: dict | None = None,
               people_desc: dict | None = None,
               style_video: Path | None = None,
               style_src: str = "", style_span=None) -> str:
    """这一段最终发给模型的提示词（官方改写器产出，**验收通过才缓存**）。

    · 缓存命中且过验收 = 一分钱不花、拿回**上次那份**合格的词
    · 缓存命中但不合格 = 丢掉重抽（旧版本抽坏的那份不再永远生效）
    · 缓存未命中 = 调 `minimax.context_ir`，**过验收才落盘**；不过就重抽，
      最多 `_IR_MAX_TRY` 次；全不过则返回最后一次并记 WARNING（不写缓存）

    `video_src` / `video_span` 给了就按「原片内容 + 区间」算指纹（见 `sig_of`）——
    切片重切不再让指纹漂移，预调好的那份出片时能稳定命中。
    """
    from app.services import minimax

    # ⚠️ 临时实验开关（2026-11-03 晚，主人指定「试试」）：任务目录里放了
    #   `direct_prompt.txt` 就直接把它当这一段最终提示词发给 H3，**不经改写器**。
    #   用途只有一个：验证「中文直发 + `<Picture N>` 标号」这条路。
    #   为什么需要：`@图片1` 是网页端手写入口的写法（`manual:248`），API 直发时
    #   没有任何依据说明它会被识别；API 侧的引用标号在 `ref-en.txt:60-80`
    #   （`<Picture N>` / `<Video N>` / `<Audio N>`）。
    #   🩸 用完请删掉这个文件，否则这一单之后每次出片都会走它。
    if cid:
        _dp = Path(clone_store.task_dir(cid)) / "direct_prompt.txt"
        if _dp.is_file():
            _body = _dp.read_text(encoding="utf-8").strip()
            if _body:
                log.warning("⚠️ 命中直发提示词 %s（%d 字，不经改写器）",
                            _dp, len(_body))
                return _body

    text = instruction(list(slots or []), looks=looks,
                       boundary_pic=int(boundary_pic or 0), extra=extra,
                       cuts=cuts, span_dur=span_dur,
                       audio_mode=audio_mode, ppl=ppl,
                       ppl_all=ppl_all,
                       frame_n=int(frame_n or 0), lines=lines,
                       changes=changes, people_desc=people_desc,
                       style_video=style_video is not None)
    fp = _fp(text, dur, images, video=video, video_src=video_src,
             video_span=video_span, audio=audio, audio_src=audio_src,
             audio_span=audio_span, style=style_video,
             style_src=style_src, style_span=style_span)
    d = Path(clone_store.task_dir(cid)) / "ir"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"seg_{n:03d}_{fp}.txt"

    _slots = list(slots or [])
    n_replace = sum(1 for s in _slots if str(s).startswith("person"))
    n_shots = (len(cuts) + 1) if cuts else 1
    #: 人物参考图在 content 里的**图号**（= 槽位顺序），换人标记只校准这几个
    _pics = [i + 1 for i, s in enumerate(_slots) if str(s).startswith("person")]
    _pairs = [(pic, str((ppl[k] or {}).get("position") or ""))
              for k, pic in enumerate(_pics) if k < len(ppl or [])]

    def _shape(b: str) -> str:
        return _skeleton(_swap_marks(b, _pics), _pairs,
                         has_audio=audio is not None, lines=lines)

    if f.exists():
        body = _shape(f.read_text(encoding="utf-8").strip())
        if body:
            bad = _ir_defects(body, n_replace=n_replace, n_shots=n_shots)
            if not bad:
                log.info("第 %d 段的提示词命中官方改写缓存（%s）", n, fp)
                return body
            log.warning("第 %d 段的旧缓存不合格（%s），丢弃重抽", n, "；".join(bad))

    last = ""
    for attempt in range(1, _IR_MAX_TRY + 1):
        # 🩸 顺序即编号：原片先、风格片段后 → 改写器看到的是「视频1 = 原片，
        #   视频2 = 风格参考」，和出片请求里的编号一致（`minimax.reference_video`
        #   也是先原片后 ref_videos）。官方 IR 收视频 ≤3 段、单段 [2,15]s、
        #   **总时长 ≤15s**（`data/official/h3/pull-2026-11-02/api_v2-h3-context-ir.md:234-249`），
        #   而 `video_edit.style_video_budget` 早已按 15s 预算截好风格片段。
        body = minimax.context_ir(
            text=text, images=list(images or []),
            videos=[video] + ([style_video] if style_video is not None else []),
            audios=([audio] if audio is not None else None),
            duration=int(dur))
        body = _shape(body)
        bad = _ir_defects(body, n_replace=n_replace, n_shots=n_shots)
        (d / f"seg_{n:03d}_{fp}.try{attempt}.txt").write_text(body, encoding="utf-8")
        last = body
        if not bad:
            f.write_text(body, encoding="utf-8")
            (d / f"seg_{n:03d}_{fp}.in.txt").write_text(text, encoding="utf-8")
            log.info("第 %d 段的提示词已由 H3-Context-IR 产出（第 %d 次，%d 字，%s）",
                     n, attempt, len(body), fp)
            return body
        log.warning("第 %d 段第 %d 次产出不合格（%s）", n, attempt, "；".join(bad))
    log.warning("第 %d 段改写 %d 次都不合格，用最后一次（%d 字，%s）—— 不写缓存",
                n, _IR_MAX_TRY, len(last), fp)
    return last
