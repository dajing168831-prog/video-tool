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
不再每跑一次就换一套词。要换词只能改输入，不能靠重跑抽卡。
"""
from __future__ import annotations

import hashlib
import logging
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
_POS_ZH = {"left": "左边", "center": "中间", "middle": "中间",
           "right": "右边", "front": "前排", "back": "后排"}


def _pos_zh(position) -> str:
    """盘点方位 → 中文方位。认不出来的**返回空串**，让调用方退回泛称。"""
    return _POS_ZH.get(str(position or "").strip().lower(), "")


def instruction(slots: list[str], *, boundary_pic: int = 0,
                extra: str = "", looks: dict | None = None,
                cuts: list[float] | None = None,
                audio_mode: str = "",
                ppl: list | None = None,
                frame_n: int = 0,
                lines: list | None = None) -> str:
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
    looks = looks or {}
    # 与人物槽位**同序**的盘点记录（`video_edit._span_people` 的产出）。
    # 只用来写方位；给不全就退回泛称，绝不因为缺方位少写一句。
    ppl = list(ppl or [])
    for i, slot in enumerate(slots, 1):
        zh = _zh(slot)
        if zh == "人物":
            person_pics.append(i)
            # 官方 `h3-manual:248`：想保持的特征要**明确写出来**。这份文本来自
            # 定妆照自己的描述（`subject_desc.json`），不是在这里现编的。
            feat = str(looks.get(slot) or "").strip()
            line = f"人物参考图{i}提供了人物的形象，锁定脸和长相"
            if feat:
                line += f"：{feat}"
            materials.append(line)
        elif zh == "商品":
            materials.append(f"商品参考图{i}提供了商品的外观，锁定商品")
        elif zh == "场景":
            materials.append(f"场景参考图{i}提供了场景")
        elif zh == "服装":
            materials.append(f"服装参考图{i}提供了服装")
        elif zh == "风格":
            materials.append(f"风格参考图{i}提供了画面的风格和色调")
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
    _ln = [(float(s), float(e), str(t).strip())
           for s, e, t in (lines or []) if str(t).strip()]
    lines_txt = ("这一段原片里说了这些台词，秒数相对本段起点：%s；"
                 % "；".join(f"{s:.2f}–{e:.2f} {t}" for s, e, t in _ln)
                 if _ln else "")
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
        _pairs = []
        for k, i in enumerate(person_pics):
            pos = ""
            if k < len(ppl):
                pos = _pos_zh((ppl[k] or {}).get("position"))
            _pairs.append((i, pos))
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
        _all_pos = all(pos for _, pos in _pairs)
        _has_rest = 1 <= _k and _m < _k
        if _k != 1 and _all_pos:
            _assign = "，".join(f"图{i}中的人物替换{pos}那位"
                                for i, pos in _pairs)
            _repl = (f"视频1中的出镜人物替换为人物参考图中的人物：{_assign}"
                     + ("，其余出镜人物保持原样" if _has_rest else ""))
            _who = f"{pics}中的人物"
        elif _k >= 2:
            # 方位缺一个就整句退回泛称 —— 半对半错比全不说更容易让模型认错人
            _pick = (f"{pics} 替换其中一位" if _m == 1
                     else f"{pics} 各替换一位")
            _repl = ("视频1中的出镜人物替换为人物参考图中的人物："
                     + _pick + ("，其余出镜人物保持原样" if _has_rest else ""))
            _who = f"{pics}中的人物"
        else:
            # K == 1（确认只有一个人）或没有可用方位：不写方位
            _rel = ("视频1中的人物替换为" if _m == 1
                    else "视频1中的出镜人物分别替换为")
            _repl = f"{_rel}{pics}中的人物"
            _who = f"{pics}中的人物"
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
        materials.append(
            f"参考视频1进行动作模仿；{_repl}；{_who}必须严格遵循原视频的运动轨迹，"
            f"保持原有的机位和分镜不变；场景、背景、光线也来自视频1，"
            f"光影与环境与原片融合")
        idea = (f"主体是{pics}中的人物，"
                "地点、事件、题材与风格都与视频1一致")
        process = (cuts_txt + lines_txt +
                   "按视频1原样的分镜逐镜复刻，景别、构图、运镜、动作、"
                   "口型都与视频1一致，只替换出镜人物")
    else:
        materials.append("视频1是被编辑的原片，视频编辑：在视频1上做改动")
        idea = "主体、地点、事件、题材与风格都与视频1一致"
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
    text = f"{'；'.join(materials)}。{idea}。{process}。"
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
        audio_span=None) -> str:
    """改写器输入的指纹（**唯一算法**，`prompt_sig` 与 `prompt_for` 共用）。

    🩸 2026-11-02：这两处以前各算各的。缓存键靠人工标记 `:irN` 兜底 ——
    只要忘了升版，改写器换了词、段缓存照样命中旧段（实测：07:05 预调的新词
    出片时一次都没被用上，三次渲染拿回同一个 476,680 字节的旧片）。
    现在键里带这个指纹，词一变键必变，不再靠人记得升版。
    """
    v_sig = sig_of(video_src, video_span) if video_src else _sha([video])
    a_sig = sig_of(audio_src, audio_span) if audio_src else _sha([audio])
    return hashlib.sha1(
        f"{text}|{int(dur)}|{v_sig}|{_sha(list(images or []))}"
        f"|{a_sig}".encode("utf-8")).hexdigest()[:12]


def prompt_sig(*, dur, images, slots: list[str],
               extra: str = "", boundary_pic: int = 0,
               video_src: str = "", video_span=None,
               audio_src: str = "", audio_span=None,
               looks: dict | None = None,
               cuts: list[float] | None = None,
               audio_mode: str = "",
               ppl: list | None = None,
               frame_n: int = 0,
               lines: list | None = None) -> str:
    """这一次改写器会拿到的**输入指纹**——不调接口、不花钱。

    出片核心要在「查段缓存之前」知道这份词会不会变，所以不能在这里花 ¥0.11；
    真正的文本由 `prompt_for` 产出（命中同一指纹，落盘复用）。
    """
    text = instruction(list(slots or []), looks=looks,
                       boundary_pic=int(boundary_pic or 0), extra=extra,
                       cuts=cuts, audio_mode=audio_mode, ppl=ppl,
                       frame_n=int(frame_n or 0), lines=lines)
    return _fp(text, dur, images, video_src=video_src, video_span=video_span,
               audio_src=audio_src, audio_span=audio_span)


def prompt_for(cid: str, n: int, *, video: Path, images: list,
               slots: list[str], audio: Path | None, dur: int,
               extra: str = "", boundary_pic: int = 0,
               video_src: str = "", video_span=None,
               audio_src: str = "", audio_span=None,
               looks: dict | None = None,
               cuts: list[float] | None = None,
               audio_mode: str = "",
               ppl: list | None = None,
               frame_n: int = 0,
               lines: list | None = None) -> str:
    """这一段最终发给模型的提示词（官方改写器产出，按输入指纹缓存）。

    · 缓存命中 = 一分钱不花、拿回**上次那份**词（重跑不会换措辞）
    · 缓存未命中 = 调一次 `minimax.context_ir`，结果落盘

    `video_src` / `video_span` 给了就按「原片内容 + 区间」算指纹（见 `sig_of`）——
    切片重切不再让指纹漂移，预调好的那份出片时能稳定命中。
    """
    from app.services import minimax

    text = instruction(list(slots or []), looks=looks,
                       boundary_pic=int(boundary_pic or 0), extra=extra,
                       cuts=cuts, audio_mode=audio_mode, ppl=ppl,
                       frame_n=int(frame_n or 0), lines=lines)
    fp = _fp(text, dur, images, video=video, video_src=video_src,
             video_span=video_span, audio=audio, audio_src=audio_src,
             audio_span=audio_span)
    d = Path(clone_store.task_dir(cid)) / "ir"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"seg_{n:03d}_{fp}.txt"
    if f.exists():
        body = f.read_text(encoding="utf-8").strip()
        if body:
            log.info("第 %d 段的提示词命中官方改写缓存（%s）", n, fp)
            return body
    body = minimax.context_ir(
        text=text, images=list(images or []), videos=[video],
        audios=([audio] if audio is not None else None),
        duration=int(dur))
    f.write_text(body, encoding="utf-8")
    (d / f"seg_{n:03d}_{fp}.in.txt").write_text(text, encoding="utf-8")
    log.info("第 %d 段的提示词已由 H3-Context-IR 产出（%d 字，%s）",
             n, len(body), fp)
    return body
