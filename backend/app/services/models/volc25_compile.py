"""火山 Seedance 2.5 的提示词编译器（本文件只管 2.5）。

🩸 2026-10-26 模型分离 L3：从 `edit_spec.py` 原样搬来，**一个字符没改**。
2.0 的一段式（`sd2-pe:118`）与 2.5 的五段模板（`sd25-pe`）结构相反，
两家不共用拼装 —— 改 2.5 的规则不该碰 2.0 与 H3 的代码。

依赖方向是单向的：`volc25_compile` → `edit_spec`（共用工具）。
`edit_spec` **不许**在模块级 import 本文件（只在函数内按需 import）。
"""
from __future__ import annotations

import re

from app.services.edit_spec import (  # noqa: F401  （共用的槽位常量与工具）
    PERSON_SLOTS,
    WARDROBE_SLOTS,
    _CLOTH_HEAD,
    _LANDMARK_RE,
    _PERSON_HEAD,
    _clauses,
    _duty_role,
    _feat_phrase,
    _head_noun,
    _keep_sentence,
    _multi,
    _person_attr,
    _pic,
    _present,
    _split_feats,
    _uniq_pos,
    _vid,
    _who,
    _who_label,
)
from app.services.models.base import Dialect


def _wardrobe_subject_25(pid: str, people: list[dict] | None,
                         frame_people: list[dict] | None = None,
                         desc_by_id: dict | None = None) -> str:
    """**2.5 专用**：换装句里"这是谁的衣服" —— 返回指认短语（不含「的服装」）。

    🩸 2026-10-28 从 `edit_spec.py` 搬来（它是 2.5 的口径，躺在三家共读的文件里
    就是串味；分离门第三道 `phrase_scan` 抓的是字符串，抓不到函数名，得靠人搬）。

    🩸 2026-10-28（2.5 轮，当前产出实测）：2.5 的换装宾语以前只取 `_head_noun`，
    于是 `7536fdb5` 出「只把**的**服装换成@图片1…」（中心词为空），
    `2f1f26d8` 出两句一字不差的「只把**男性**的服装换成…」（两人都叫男性）。

    三档，**全部取 2.5 自己的官方材料**：
      · 方位唯一 → 「画面左侧的人物」——`sd25-guide:193` 的编辑示例就是
        「把视频 1 中**右侧**的亚洲女生改为图片 1 中的黑人女生」；
      · 撞车 / 没方位 → 外观特征短语 —— `sd25-guide:1203-1209` 双人同时换装的
        官方示例「视频中**深色衣服的男子**…**浅色衣服的男子**」用画面看得见的
        外观当称谓。`cloth=False`：正在被换掉的那套衣服不能当识别特征；
      · 都没有 → 空串，调用方退回「服装」。
    """
    _pool = frame_people or people or []
    per = next((x for x in _pool if str((x or {}).get("id") or "") == str(pid)),
               None)
    pos = _uniq_pos(per, _pool)
    if pos:
        return f"{pos}的人物"
    _d = _who(desc_by_id, pid, "zh") or ((per or {}).get("desc_zh") or "")
    _feat = _feat_phrase(_d, cloth=False)
    if _feat:
        return _feat
    # 🩸 2.5 自己的兜底（不是从 2.0 搬的）：盘点描述常常只写外观、不写
    # 「…的男性/的女子」这类中心词（真实盘点 `7536fdb5` P1：
    # 「穿橙色连帽拉链外套，左胸带有白色标识，短发，…」）。`_feat_phrase`
    # 在缺中心词时返回空 —— 那是 2.0 的口径。2.5 按 `sd25-guide:1203-1209` 的
    # 官方称谓结构「**深色衣服的男子**」补上类名词即可，特征本身没变。
    _parts, _ = _split_feats(_d)
    _keep = [x for x in _parts if not x.startswith(_CLOTH_HEAD)][:2]
    return ("、".join(_keep) + "的人物") if _keep else ""


def _disambiguate_25(own: str, desc: str, others_text: str,
                     cloth: bool = True) -> str:
    """`own` 在同画面**别人**那里也成立时，换成只属于这个人的特征短语。

    🩸 2026-10-29（D72）：真机盘点 `686dc484` 8 人场里有 4 位描述都以
    「黑人男性，」开头、区别全在后面（圆顶礼帽 / 反光墨镜 / 平顶贝雷帽 / 墨镜）。
    `_feat_label_25` 的「首段是人称名词就原样返回」让他们全叫「黑人男性」，
    四条 `<目标>` 分不清谁是谁。2.0 那边同一天修的（D71），这里是 2.5 自己的一份
    —— 两家认人尺各留各的，不互借。

    取特征的口径沿用 2.5 自己的 `_feat_label_25`：先按「、」摊平、再封顶 2 个；
    `cloth=False` 时服装整段丢掉（正被换掉的衣服不能当识别特征，
    见 `_wardrobe_subject_25` 的出处）。
    """
    if not own or not others_text:
        return own
    used = [x for x in re.split(r"、", own) if x.strip()] or [own]
    if not all(f in others_text for f in used):
        return own
    # 🩸 自己切分句，**不用 `_split_feats`**：它对没有「的X」结尾的描述会把
    #   最后一段整个丢掉（`parts[:-1]`），「黑人男性，戴红色帽子」这种两段描述
    #   正好只剩「黑人男性」—— 和 2.0 那次一模一样的坑。
    raw = re.sub(r"[\r\n\t]+", " ", desc or "").strip().rstrip("。．.")
    parts = [x.strip() for x in re.split(r"[，,；;]", raw) if x.strip()]
    head = ""
    if parts:
        m = re.search(r"的([^，；,;的]{1,4})$", parts[-1])
        if m and _PERSON_HEAD.search(m.group(1)):
            head = m.group(1)
            tail = parts[-1][:m.start()].strip()
            parts = parts[:-1] + ([tail] if tail else [])
    flat: list[str] = []
    for f in parts:
        flat.extend([x.strip() for x in re.split(r"、", f) if x.strip()])

    def _pick(xs: list[str]) -> list[str]:
        return ([f for f in xs if f not in others_text and _LANDMARK_RE.search(f)]
                or [f for f in xs if f not in others_text])[:1]

    # `cloth=False`（换装/换人句的指代）先不用服装；但两人**只差衣服**时退回
    # 服装 —— 两句一模一样是必然换错，带一件衣服只是有风险。
    picks = (_pick([f for f in flat if not f.startswith(_CLOTH_HEAD)])
             if not cloth else _pick(flat))
    if not picks:
        picks = _pick(flat)
    if not picks:
        return own
    # 缺人称词时补「…的人物」—— 与 `_feat_label_25` 同一种称谓结构
    # （`sd25-guide:1203-1209`「深色衣服的男子」那一套）。
    return f"{picks[0]}的{head}" if head else f"{picks[0]}的人物"


def _others_text_25(pool: list[dict] | None, pid: str) -> str:
    """同画面**别人**的描述拼成一段 —— 判"这个说法是不是大家都能套"用。"""
    return " ".join(
        re.sub(r"[\r\n\t]+", " ", str(p.get("desc_zh") or ""))
        for p in (pool or [])
        if p and _present(p) and str(p.get("id") or "") != str(pid or ""))


def _orig_feat_25(people: list[dict] | None, i: int,
                  pool: list[dict] | None = None, cloth: bool = True) -> str:
    """原片里第 i 个人的**指认短语**（2.5 的一份）。

    🩸 2026-10-28：以前 2.5 的换人句直接调 `edit_spec._sd20_orig_feat`
    —— 名字就写着 sd20，却是 2.5 的产出在用它。分离门两道门都看不见函数名。
    现在**各留一份**：改哪一家的指认尺都不会动到另一家。

    ⚠️ **当前实现与 2.0 逐字相同**（方位唯一 → 「画面左侧的人物」；撞车 →
    特征短语，`sd20=True` 那套）。这是为了本轮"搬迁不改产出"—— 34 条生产
    形状的产出逐字节比对过。2.5 该不该用不同的特征提取口径（它自己的
    `_wardrobe_subject_25` 已经有一套 `_split_feats` 兜底），要单独评估、
    单独出片验证，不在搬迁里顺手改。
    """
    ppl = people or []
    per = ppl[i] if i < len(ppl) else None
    if not per or not _present(per):
        return ""
    pos = _uniq_pos(per, pool if pool else ppl)
    if pos:
        return f"{pos}的人物"
    _desc = per.get("desc_zh") or ""
    _own = _feat_label_25(_desc, cloth=cloth)
    # 🩸 2026-10-29（D72）：这句会被同画面别人套用（「黑人男性」）时，
    #   换成只属于他的特征 —— 否则两个人的 `<目标>` 一字不差。
    return _disambiguate_25(_own, _desc,
                            _others_text_25(pool if pool else ppl,
                                            str(per.get("id") or "")),
                            cloth=cloth)


class _CL25(Dialect):
    """**2.5 自己的句式口径**（见 `base.Dialect` 的说明）。"""

    def orig_feat(self, people: list[dict], i: int,
                  pool: list[dict] | None = None, cloth: bool = True) -> str:
        return _orig_feat_25(people, i, pool=pool, cloth=cloth)

    def subj(self, obj: str) -> str:
        # 官方模板 `sd25-pe:561`「编辑@视频1，只把<原对象或区域>替换为<目标内容>」
        # 示例 `:584`「只把经过长椅前方的红色自行车和骑行者替换为…」
        # —— `<原对象>` 里**不带 @视频1**，@视频1 只在句首出现一次。
        return f"把{obj}"

    def wardrobe_verb(self) -> str:
        # 🩸 2026-10-28：动词 **替换为**。判据只有一条 —— 看**正式示例**怎么写，
        #   不看占位模板、更不看触发词清单（`sd25-guide:88` 那张表说的是
        #   「用户输入里出现哪些词会触发编辑」，管的是**输入识别**，不管产出句式）。
        #   官方 2.5 全部"改内容"的正式示例 5/5 都是「替换为」：
        #     · `sd25-pe:584`「只把经过长椅前方的红色自行车和骑行者**替换为**…」（模板的已填示例）
        #     · `sd25-pe:602`「…在完全相同的出现时机…**替换为**@图片1定义的<目标动态主体>」
        #     · `sd25-guide:1205`「将两人武打素版视频 @视频1 **替换为**冷兵器对决前的空手试探风」
        #     · `sd25-guide:1207`「场景**替换为**中世纪石堡平台…」
        #     · `sd25-guide:1209`「视频中深色衣服的男子的服饰**替换为** @图片2，
        #       视频中浅色衣服的男子**替换为** @图片3」← **唯一一条换装正式示例**
        #   「修改为」在 2.5 只出现在三处：占位模板 `:561`、触发词清单里的短 blurb
        #   (`sd25-guide:88`「把 @video1 的人物修改为 @image1」)、以及改台词内容
        #   (`sd25-guide:191`「修改为「你不要过来啊」」—— 那是换对白，不是换对象)。
        #   ⇒ 换装句跟换装示例走：替换为。
        return "替换为"

    def wardrobe_verb_text(self) -> str:
        """没传图、只有一句文字描述的换装（「只把X的服装…为米色风衣」）。

        2.0 的官方出处是 `sd20-guide:39`「将其中的<原特征>**修改为**<新特征>」，
        所以共用层默认仍是「修改为」；2.5 没有这条文字版示例，但它同一句里的
        换装句都用「替换为」（见上），一句话里不许两个动词 → 一起用「替换为」。
        """
        return "替换为"

    def wardrobe_subject(self, ctx: dict) -> tuple[str, bool]:
        pid = ctx["pid"]
        who = ctx.get("who") or ""
        if not who:
            return "服装", False
        _loc = _wardrobe_subject_25(pid, ctx.get("people"),
                                    ctx.get("frame_people"),
                                    ctx.get("desc_by_id"))
        return (f"{_loc}的服装" if _loc else "服装"), False

    # 🩸 2026-10-28（逐句溯源）：「**改成**」在 2.5 官方里不是编辑动词 ——
    #   `sd25-pe:271` 原话是「"转换、调整、修改、**改成**、重构"等动词本身
    #   不构成视频编辑」；能当编辑动作写的只有模板 `:561` 的「修改为」和所有
    #   已填示例的「替换为」（`:584` `sd25-guide:1205`）。风格句跟已填示例走。
    def style_ref(self, pic: str) -> str:
        return f"把整体画面风格替换为{pic}的色调、光影和质感"

    def style_video(self) -> str:
        return "把整体画面风格替换为@视频2的色调、光影和质感"

    def style_word_when_ref(self) -> bool:
        # 2.5 三选一：有风格参考图/视频就不发风格词。
        return False

    def style_word(self, word: str) -> str:
        # 2.5 走模板「**只把**<原对象>修改为<目标内容>」，风格也是一种编辑对象 ——
        # 句首加「把」，才能吃到 `_volc_25` 统一补的那个「只」。
        # 🩸 2026-10-28：动词同上，用「替换为」（`sd25-pe:271` 说「改成」不算编辑）。
        return f"把整体画面风格替换为{word}"


#: 2.5 的方言实例（`volc25.py` 登记进 adapter）
CL25 = _CL25()


#: 主标字母表。**必须覆盖 `PERSON_SLOTS` 的全部 16 个槽位。**
#: 🩸 2026-10-28 实测：原来写死 `'ABCDEFGH'`（8 个），勾到**第 9 个人**直接
#:   `IndexError: string index out of range` —— 整单 500，不是提示词质量问题而是崩溃。
#:   字母这个形式本身是官方的（`sd25-pe:227-230` 的 `<人物A>` / `<人物B>`）。
_WHO_LETTERS = "ABCDEFGHIJKLMNOP"


def _who_letter(k: int) -> str:
    """第 k 个目标人物的区分字母。超出字母表（按槽位数不该发生）退数字，绝不留空。"""
    return _WHO_LETTERS[k] if k < len(_WHO_LETTERS) else str(k + 1)


#: 用户「补充说明」里**明确要求改光线**的说法。
#: 官方 `sd25-pe:599`：「**保持清单只写与目标邻接、确实不能变化的区域**，避免过长
#: 清单稀释编辑目标。」用户已经在要求改光线，光线就属于"能变化"的区域，
#: 不能再写进「不修改…光线和色调」（`sd25-guide:278`「prompt 避免前后矛盾」）。
#: 🩸 这个逻辑代码里本来就有，只是输入源一直只有**素材类** ——
#:   风格图 / 风格视频 / 纯文字风格会跳过 `lighting`（见下方 `_keep_only`
#:   和 `edit_spec._keep_sentence` 的 `_style_src` 判断）；
#:   **用户手写的那句话从来没参与过判断**（2026-10-28 英文探针实测：
#:   `make the light warmer` 和「不修改…光线和色调」同在一份提示词里）。
_LIGHTING_WORDS = re.compile(
    r"(光线|色调|光影|亮度|曝光|色温|打光|补光|暖色|冷色|"
    # 口语说法（"画面更亮一些"里不会出现"光线"两个字）。
    # 🩸 只收带程度词/动词的组合：单字「亮」「暗」会命中「漂亮」「暗号」。
    r"更亮|变亮|提亮|调亮|压暗|变暗|调暗|更暗|"
    r"亮[一有]?[些点]|暗[一有]?[些点]|亮起来|暗下来"
    r"|light|bright|dark(?:er|ness)?|tone|exposure|contrast|color grade)", re.I)
#: 命中词前面有否定 → 这是"不要改"，不是"要改"。
_NEGATED_BEFORE = re.compile(
    r"(不要|不用|不必|无需|别|保持|维持|不变|不动|原样|"
    r"don't|do not|without|no change|keep)[^，。；\n]{0,20}$", re.I)


#: 🩸 2026-10-28（E13 收尾）：**引号前有没有"有人说了话"**。
#: `sd25-pe:141` 说「用户只给出带引号的**台词片段**…只把该片段作为可说出的原文」——
#: **前提是它是台词片段**。而官方 `:869` 的台词语法是
#: 「语言 + 可选地区变体 + 表达方式 + **说话人** + {台词}」，台词前面一定有说话人/说话动作。
#: ⇒ 只有引号前带说话标记的才转 `{}`；「把标题改成"限时优惠"」这种名词引用
#: 去掉引号就行，不能标成台词（否则模型会把「限时优惠」念出来）。
_SPEECH_BEFORE = re.compile(
    r"(?:说道|说|喊道|喊|问道|问|答道|答|念道|念|吼道|吼|骂道|骂|告诉|"
    r"said|says|say|asked|asks|shouted|yelled|told|whispered|replied)"
    r"[^，。；\n]{0,8}$", re.I)


def _extra_wants_light(extra: str) -> bool:
    """用户补充说明里是不是在**要求改光线/色调**。

    宁可判"没要求"（写保持句，画面更稳），也不要把「不要改光线」当成"要改"。
    """
    text = (extra or "").strip()
    if not text:
        return False
    for m in _LIGHTING_WORDS.finditer(text):
        head = text[max(0, m.start() - 24):m.start()]
        if _NEGATED_BEFORE.search(head):
            continue
        return True
    return False


#: 用户补充说明里**要在画面里新增东西**的说法。
#: 官方 `sd25-guide:88` 的编辑任务触发关键词表里就有「增加/加上」，示例是
#: 「@video1 中加一些小动物」；`sd25-pe:578` 进一步要求
#: 「增加或删除对象时说明数量、位置、出现时机和受影响范围」。
_ADD_WORDS = re.compile(
    r"(增加|加上|加一个|加一只|加一条|加个|添加|多加|再放|放入|摆上|"
    r"\badd\b|\badding\b|\binsert\b)", re.I)


def _extra_adds_object(extra: str) -> bool:
    """用户补充说明里是不是要**在画面里新增对象**。

    🩸 2026-10-28（读 28 组产出抓到的第二个自相矛盾）：`extra="背景里加一只橘猫"`
      时，同一份提示词里既写着「背景里加一只橘猫」，又写着
      「不修改@视频1的**背景环境**、构图和景别、光线和色调」。
    官方 `sd25-pe:599`「保持清单只写与目标邻接、**确实不能变化**的区域，
      避免过长清单稀释编辑目标」—— 用户要往画面里加东西，背景就不再是
      "确实不能变化"的区域，不能还写进保持句。

    宁可判"没要求"（照写保持句，画面更稳），也不要把「不要加」当成"要加"。
    """
    text = (extra or "").strip()
    if not text:
        return False
    for m in _ADD_WORDS.finditer(text):
        head = text[max(0, m.start() - 24):m.start()]
        if _NEGATED_BEFORE.search(head):
            continue
        return True
    return False


def _shot_plan(cuts: list[float]) -> str:
    """2.5 的「这一段有几个镜头」那句。

    🩸 2026-10-26 L3：原来在 `edit_spec.shot_plan_sentence` 里跟 2.0 和 H3 挤一个
    `if channel == "volc": … else: …`。三家口径完全不同，各写各的。

    出处《Seedance 2.5 提示词写作指南》：「转场镜头写清触发点与方式，尽可能把
    转场时间、方式都写明」+ 时间轴模板【00:00–00:01】。
    """
    if not cuts:
        return "全程一镜到底，不切镜、不跳切。"
    # 🩸 2.5 只认**整数秒**（同指南 :336「Seedance 2.5 响应整数秒的时间戳」）。
    # 以前按 2.0 的习惯写「第 2.50 秒」，那一位小数官方根本不解析。舍入后可能撞车
    # （2.4 和 2.6 都是第 2 秒）→ 去重，同一秒只报一次。
    # 切点落进第一秒内时写「第 1 秒」：0 秒是片子开头、不是切点。
    secs: list[int] = []
    for t in cuts:
        n = max(1, int(round(float(t))))
        if n not in secs:
            secs.append(n)
    where = "、".join(f"第 {n} 秒" for n in secs)
    # 🩸 2026-10-28（逐句溯源）：官方词是「**剪切点**与转场」「**转场风格**」
    #   （`sd25-guide:828`「在对应源时刻还原每一个**剪切点与转场**…保持精确的
    #   镜头顺序、剪切频率、**转场风格**」）。以前写「切点」（缩写，官方 0 命中）
    #   和「转场方式」（官方用「转场风格」）。「切镜」「景别」是官方词
    #   （`sd25-pe:337`「镜头采用<景别、机位、运镜或切镜>」）。
    return (f"{where}按{_vid('volc')}原有的剪切点与转场切镜，保持与原片相同的景别和"
            f"转场风格。")


# 官方「范围闭环」（sd25-pe「视频编辑模板」原句，2.0 的编辑要求也写「强调保留元素」）。
# 🩸 为什么必须有：一句「把人物替换为@图片1中的人物」在多人物画面里没有唯一解，
# 模型分不清要换哪一个、其余的人怎么办 —— 实测原片 5 人同框时会把所有脸都换掉。
# 官方给的解法不是「猜」，而是**把范围写死**：除明确修改对象外，其余一律保持原样。
def _scope_closure() -> str:
    """范围闭环 —— **官方逐字**，不许改写成变体。

    出处 `sd25-pe:552-555`：「每条视频编辑 Prompt 都必须包含以下两种范围闭环之一，
    不能省略范围闭环：- 局部修改：`除以上明确修改对象外，@视频1中其他可见人物、
    道具和背景元素保持原样，不参与替换或删除。`」

    🩸 2026-10-22 曾按"换背景时背景不该说保持原样"改成动态列举（少列被改的那类），
    理由是字面矛盾。**那是我自己发明的写法**：官方只有两种闭环，逐字，没有第三种。
    字面矛盾由前缀「**除以上明确修改对象外**」排掉；背景替换的正确落点是
    `sd25-pe:576`「背景替换时明确只修改主体轮廓之外的背景」——
    在【编辑目标】/【编辑对象与范围】里说，不在兜底句里删类别。
    """
    return ("除以上明确修改对象外，@视频1中其他可见人物、道具和背景元素"
            "保持原样，不参与替换或删除")

def _lip_line(spec: dict, audio_ref: bool) -> str:
    """换配音时的「按新的说话内容重做口型」句。空串 = 不该写。**2.5 专属。**

    🩸 出处只在 2.5：`sd2-pe` / `seedance-20-guide` / `volc-create` 里
       grep「口型」**0 次**；2.0 收参考音频是**能力**（`volc-api:35`），
       官方没给过这句写法。

    🩸 D3（2026-10-23）：**"选了换配音" ≠ "新声音真的发给了模型"**。
       没音轨时口型属于原片表演的一部分，交给「未提及的部分默认保持不变」；
       硬写只会让模型自己编一套台词（`_minimax` 那边 2026-10-21 实测翻车过）。
       `mix` 也是全新配音（新的人声 + 分离出来的背景），同样要重做口型。

    🩸 2026-10-28：这段原来在共用层 `edit_spec._keep_sentence` 里靠 `lip=` 开关控制
       —— 形式上是"开关"，实质仍是某家的句子躺在三家共读的文件里。搬到这里。
    """
    if audio_ref and (spec.get("audio") or "tts").strip().lower() != "original":
        # 🩸 2026-10-28（逐句溯源）：原句「…按新的说话内容重新生成，不要沿用原视频
        #   的口型」两半都是自造 —— 官方 2.5 只有两种说法，直接照搬：
        #     · `sd25-guide:929/:935/:1241`「**口型做出对应的精准改变**，其余均保持不变」
        #     · `sd25-guide:916`「要求逐字同步口型…**口型与台词精准同步**」
        return "口型做出对应的精准改变，与台词精准同步。"
    return ""


def _volc_25(spec: dict, c: dict, idx: dict[str, int], *,
             people: list[dict] | None = None,
             frame_people: list[dict] | None = None,
             audio_ref: bool = False,
             desc_by_id: dict[str, str] | None = None,
             shot_cuts: list[float] | None = None,
             boundary_pic: int = 0,
             shot_lines: list[list[dict]] | None = None,
             style_video: bool = False) -> str:
    """Seedance 2.5 —— 按官方「视频编辑模板」出五段。

    出处（sd25-pe）：
      · :71 原则 2「模板优先」——无论原 Prompt 是否完整，都要进入对应模板重新组织
      · :324「选择下文对应模板…所有 <占位符> 必须替换为具体内容」
      · :559-575「视频编辑模板」五段原文
    🩸 **2.5 和 2.0 的结构是相反的**：2.0 `sd2-pe:118` 明令编辑任务
       「**不要**强行拆成'主体定义 / 分镜 / 约束'等分块标题，直接组装为一段提示词」；
       2.5 则必须套模板分块。一套骨架通吃是错的。
    """
    # 🩸 2026-10-26（2.5 穷举 E8）：`<>` 在 2.5 里是**官方音效标记**
    # （`sd25-guide:872` / `sd25-pe:872`），官方 `:880` 还专门要求「同一符号不能
    # 承担两种职责」。用户自由文本里写了尖括号（比如产品名「杯子<红>」），
    # 原样拼进去会被当成音效。这里只清洗**用户输入的自由文本**，
    # 我们生成的主体标记一律是 `@图片N`（2.5 不用尖括号），不会被误伤。
    # 🩸 2026-10-28（2.5 全量穷举，228 种句子逐条人读）：同一个坑的另一半 ——
    #   `{}` 在 2.5 里是**台词标记**（`sd25-pe:867`「台词必须写进 `{}`」），
    #   E8 喂「杯子{大}<红>（限量）」时 `<>` 被切掉、`{大}` 却原样发出去，
    #   模型会把产品名当一句台词念。依据同一条：官方 `:880`「同一符号不能承担
    #   两种职责」⇒ 这两个符号都要从自由文本里清掉。
    # 🩸 2026-10-28（2.5 穷举 E12 用户补充说明矩阵）：`【】` 是**第三种**撞车 ——
    #   官方 `:867` 表里 `【】` 是**字幕**标记，而我们这个模板的五段标题
    #   （`sd25-pe:559-576`）也用 `【】`。用户写「加一只猫。【原视频职责】…」
    #   实测产出 `加一只猫。，【原视频职责】，这段是乱写的…` —— 【编辑目标】里
    #   多出一个同名段，`_sec()` 先命中伪造的那个 → 真段被跳过，T4 直接判
    #   「【原视频职责】没写唯一编辑母版」。依据同样落在 `:880`「同一符号不能
    #   承担两种职责」。⛔ 不动 `（）`：中文括号是日常标点，清掉会把正常句子打断，
    #   而 `()` 只是"音乐"提示，误留不会伪造结构。
    c = dict(c)
    spec = dict(spec)

    def _clean_free(s: str, *, quotes: str = "") -> str:
        """用户自由文本 → 不会伪造结构的形态。

        `quotes="strip"` 用于**服装描述**：那里的引号是"这个款式叫什么"，
        不是台词（`sd25-pe:141` 的引号片段=可说出的原文只适用于台词位），
        留裸引号会被尺子 P3 当成没包裹的台词，去掉引号内容照样读得通。
        """
        s = re.sub(r"[<>{}【】]", "", s)
        # 🩸 2026-10-28（同一轮人读）：多行自由文本会把一句切成两行 ——
        #   官方模板 `sd25-pe:559-576` 每一段都是**连续一行**，
        #   `第一行\n第二行` 拼进去就成了「…@图片1中的人物。第一行」/「第二行。」
        #   两个残句。换行折成逗号，仍读得通、不切断段。
        # ⚠️ 2026-10-28（E12 伪段标题）：前一句已经以句末标点收口时
        #   不要再补逗号 —— 实测产出「加一只猫。，原视频职责，…」，
        #   `。，` 连用是纯粹的标点垃圾。先吃掉句末标点后面的换行。
        s = re.sub(r"(?<=[。！？；，、])[ \t]*[\r\n]+[ \t]*", "", s)
        s = re.sub(r"(?:[ \t]*[\r\n]+[ \t]*)+", "，", s)
        if quotes == "strip":
            s = re.sub(r"[“”\"]", "", s)
        return s

    for _k in ("product_target", "scene_desc"):
        for _d in (c, spec):
            if isinstance(_d.get(_k), str):
                # 这两处都是**名词位**（画面里被换的是哪一件 / 换成什么背景），
                # 引号只是引用装饰，不是台词 —— 去掉内容不变，也免得尺子 P3
                # 把「只把桌上的"陶瓷杯"替换为…」当成没包裹的台词（实测假红）。
                _d[_k] = _clean_free(_d[_k], quotes="strip")
    for _d in (c, spec):
        if isinstance(_d.get("extra"), str):
            # 只有 `extra` 留引号：那里的引号片段后面要换成 `{}`（见下）。
            _d["extra"] = _clean_free(_d["extra"])
    for _d in (c, spec):
        if isinstance(_d.get("wardrobe_desc"), str):
            _d["wardrobe_desc"] = _clean_free(_d["wardrobe_desc"],
                                              quotes="strip")
    # 🩸 2026-10-28（E12 换装描述探针）：`wardrobe_desc_by_id` 是**每人一个**
    #   自由文本框（前端一人一个输入框），同样的符号一样会漏进正文 ——
    #   实测 `【原视频职责】乱写的内容` / `<刺耳的钟声>米色风衣` /
    #   `{米色风衣}` / 多行 全都原样出现在【编辑目标】里，多行那条甚至
    #   直接多出一个 `【编辑目标】` 行。这是浅拷贝，必须重建 dict。
    for _d in (c, spec):
        _w = _d.get("wardrobe_desc_by_id")
        if isinstance(_w, dict):
            _d["wardrobe_desc_by_id"] = {
                k: (_clean_free(v, quotes="strip") if isinstance(v, str) else v)
                for k, v in _w.items()}
    # 🩸 2026-10-28：**人物盘点描述**（`desc_zh`）。它不是用户手填的，来自视觉
    #   盘点/ASR，但一样是原文直填 —— 而且多人时会直接当**称谓**写进
    #   【编辑目标】（「只把<desc>替换为@图片1中的人物」）。实测
    #   `【编辑目标】穿白衬衫的男人` → 全文出现 **4 个** 【编辑目标】，
    #   整份提示词结构被伪造；`<白衬衫>` / `{白衬衫}` 分别变成音效/台词标记。
    #   ⛔ 不清 `（）`（身高体重之类常用括号），不清引号（后面走称谓，不是台词位）。
    def _clean_seq(seq):
        return [dict(x, desc_zh=_clean_free(x["desc_zh"], quotes="strip"))
                if isinstance(x, dict) and isinstance(x.get("desc_zh"), str)
                else x for x in (seq or [])]

    people = _clean_seq(people)
    frame_people = _clean_seq(frame_people)
    if desc_by_id:
        desc_by_id = {
            k: (dict(v, zh=_clean_free(v["zh"], quotes="strip"))
                if isinstance(v, dict) and isinstance(v.get("zh"), str) else v)
            for k, v in desc_by_id.items()}
    # 🩸 2026-10-28（E12）：用户把台词写在引号里。2.5 的台词标记是 `{}`
    #   （`sd25-pe:867` 的符号表），而 `sd25-pe:141` 明确「用户只给出带引号的
    #   台词片段…只把该片段作为**可说出的原文**」⇒ 引号片段就是台词原文，
    #   进 2.5 模板必须换成 `{}` 才念得出来；裸引号在最终 Prompt 里没有职责
    #   （`:867` 的表里只有 ()　<>　{}　【】 四种），留着只会让模型漏念。
    #   ⚠️ 取舍：引号里如果是**非台词**（如「把标题改成"限时优惠"」）也会被标成
    #   台词。这是官方口径的必然结果 —— `sd25-pe:867` 规定"要出现在画面上"的
    #   文字用 `【】`（字幕），而 `【】` 又是我们模板的段标题符号，只能清掉。
    #   宁可让它念出来，也不要留一个既不是台词、也不是字幕的裸引号。
    #   上限 60 字与尺子 `_QUOTED_LINE` 一致；先清 `{}` 再转换，不会套娃。
    _x = spec.get("extra")
    if isinstance(_x, str) and _x:
        def _repl_quote(m: re.Match) -> str:
            head = _x[max(0, m.start() - 16):m.start()]
            if _SPEECH_BEFORE.search(head):
                return "{" + m.group(1) + "}"      # 有人说了这话 → 台词
            return m.group(1)                      # 名词引用 → 只去掉引号

        spec["extra"] = re.sub(r"[“\"]([^“”\"\n]{1,60})[”\"]", _repl_quote, _x)
    # 🩸 2026-10-26（主人追问「查清楚了吗」）：**多人换人时每个目标必须能分开**。
    # 官方 `:224`「不同主体必须逐条绑定，例如 <人物A>对应@图片1 / <人物B>对应@图片2」；
    # `sd25-guide:174`「每个素材进行文本绑定…容易导致多人混淆或重复角色」；
    # `sd25-guide:432` 直接把「多人物角色错位」列为已知失败模式。
    # 🩸 **称谓用词按官方编辑示例走，不用字母**：`sd25-guide:1203-1209`（视频参考图编辑，
    # 双人同时换装）原文是「视频中深色衣服的男子的服饰替换为 @图片 2，视频中
    # 浅色衣服的男子替换为 @图片 3」—— 画面能看见的外观就是称谓。字母只在
    # **两个称谓也撞车**时才用，且必须由 `_clauses` 在【编辑目标】里同一句绑一次
    # （`orig_tags`），否则「目标人物A」全篇没有定义。
    multi = _multi(frame_people or people, desc_by_id)
    _frame_ppl = frame_people or people or []
    _tgt_slots = [s for s in PERSON_SLOTS if s in idx]
    # 🩸 2026-10-28（分段一致性实测）：**这一段里没出现的人**。
    #   分段编译时 `_span_people` 给缺席者打 `present=False`，但槽位和图号是
    #   全片固定的 ⇒ 图照发、职责行照写。实测产出（70s 三段 · 两人）：
    #     第 1 段「@图片2用于目标人物B的五官…」—— 这一段【编辑目标】只说换
    #     白衬衫男人，「目标人物B」在本段**没有任何定义**。
    #   官方 `sd25-pe:410`「素材数量多不代表全部素材都要进入 Prompt…把实际可用
    #   但未分配职责的素材放进 `【未采用素材】`，逐个列出未采用编号并禁止激活」，
    #   示例见 `:233`「@图片5、@图片6未参与本任务，不用于人物、场景、道具、动作或镜头」。
    #   ⇒ 缺席者：不给职责行，改列【未采用素材】。图仍然发（图号不能跟段重算）。
    _absent_slots = {s for k, s in enumerate(_tgt_slots)
                     if k < len(people or []) and not _present(people[k])}
    # 按人换装时会有多个 `wardrobe*` 槽位 —— 同一个病：两条职责行都叫「目标服装」。
    _wardrobe_slots = [s for s in idx if s.startswith("wardrobe")]
    _tgt_pos = [_uniq_pos(people[k] if k < len(people or []) else None, _frame_ppl)
                for k in range(len(_tgt_slots))]
    _tgt_lbl = [_who_label_25(
        people[k] if k < len(people or []) else None, _frame_ppl,
        str(((people[k] if k < len(people or []) else {}) or {}).get("desc_zh")
            # 🩸 2026-10-28（分段一致性实测）：**缺席者的描述要从全片盘点补**。
            #   `_span_people` 给不在这一段的人只留 `{"id", "present": False}`，
            #   desc_zh 是空的 ⇒ 称谓退成"人物" ⇒ `"人物" in _tgt_lbl` 成立
            #   ⇒ 整单退字母。实测第 1 段（只有白衬衫男人在场）写成
            #   「白衬衫男人（目标人物A）」，而这一段根本没有 B；
            #   第 3 段更离谱，单人写成「黑衣服女人（目标人物B）」。
            or (((desc_by_id or {}).get(
                str(((people[k] if k < len(people or []) else {}) or {})
                    .get("id") or "")) or {}).get("zh") or "")))
        for k in range(len(_tgt_slots))]
    _tgt_letters = False
    if not multi:
        # 单人画面：逐字不动（2026-10-24 起生产验过的形状）。
        _who_by_slot = {s: "目标人物" for s in _tgt_slots}
    elif len(_tgt_slots) <= 1:
        # 多人画面但只换一个：也逐字不动。
        _who_by_slot = {
            s: (f"目标人物（替换{_tgt_pos[k]}人物）" if _tgt_pos[k] else "目标人物")
            for k, s in enumerate(_tgt_slots)}
    elif len(set(_tgt_lbl)) == len(_tgt_lbl) and "人物" not in _tgt_lbl:
        # 两个目标各有能唯一指认的称谓（方位唯一 / 外观短语不同）→ 直接用，
        # 与【编辑目标】那句的宾语逐字相同。
        _who_by_slot = {s: _tgt_lbl[k] for k, s in enumerate(_tgt_slots)}
    else:
        # 连称谓都撞车 → **整单**退回字母，并把它绑进【编辑目标】。
        _tgt_letters = True
        _who_by_slot = {s: f"目标人物{_who_letter(k)}"
                        for k, s in enumerate(_tgt_slots)}
    _orig_tags: dict[int, str] = {}
    if _tgt_letters:
        for _k, _s in enumerate(_tgt_slots):
            _nm = _tgt_lbl[_k]
            _orig_tags[_k] = (f"目标人物{_who_letter(_k)}" if _nm == "人物"
                              else f"{_nm}（目标人物{_who_letter(_k)}）")
    v = _vid("volc")
    # 🩸 2026-10-28（逐句溯源）：`style_anchor=True` —— 风格词要写**具体风格锚定词**，
    #   不是媒介名。2.5 官方明说这条与 2.0 一致：`sd25-guide:966`「主体/运动/音频/
    #   **风格参考的使用方式与 Seedance 2.0 一致**」；2.0 的出处是
    #   `sd20-guide:354`「在提示词中加入明确的风格约束词，例如"2D日漫风格"」。
    #   以前 2.5 发的是「动漫」（`STYLES` 的媒介名），2.0 发的是「2D日漫风格」。
    parts = _clauses("volc", c, idx, dialect=CL25,
                     people=people, desc_by_id=desc_by_id,
                     frame_people=frame_people,
                     keep=spec["keep"], style_video=style_video,
                     style_anchor=True,
                     orig_tags=_orig_tags)
    # 2.5 编辑模板的限定词是「只把<原对象>修改为<目标内容>」（`sd25-pe:561`）。
    # 🩸 必须**每句**都带「只」：只给第一句加，第二句就是无限制的「把…」，
    # 限定词的作用域只覆盖了第一个对象。多个对象并列时官方模板的语义是
    # "只改这几个、其余不动"，不是"第一个只改、其余随便"。
    parts = [("只" + p) if p.startswith("把") else p for p in parts]
    # 🩸🩸 2026-10-28 撤回上一版：**动词不许改成「修改为」**。
    #   官方分布：`替换为` 7 次 / `修改为` 3 次；`修改为` 在 skill 里**只出现在
    #   `:561` 这条占位模板**，而所有真正填好的替换示例用的都是 `替换为`：
    #     · `:584`「只把…红色自行车和骑行者**替换为**@图片1中的深灰色电动巡逻车」
    #     · `:602`「…在完全相同的出现时机…**替换为**@图片1定义的<目标动态主体>」
    #     · `sd25-guide:1209`「深色衣服的男子的服饰**替换为**@图片2，浅色衣服的男子
    #       **替换为**@图片3」
    #   模板是**句式骨架**（<原对象>修改为<目标内容>），示例才是这个任务类型的
    #   实际操作词。换成「修改为」= 把"换掉"弱化成"改动"，直接影响成片。
    #   ⇒ 保持共用层的 `替换为`，与官方示例一致。
    body = "；".join(parts)
    extra = spec.get("extra") or ""
    # 🩸 2026-10-28（2.5 穷举 E8 抓到的当前产出）：
    #   · `extra="，，。。"` → 句尾多出「。，，。。」；
    #   · `extra="在背景里加一只橘猫，"×60` → 句尾「…橘猫，。」。
    # 都不是官方句式里的内容，纯粹是把用户输入的标点原样拼进去。
    # 模板 `sd25-pe:324` 要求所有占位符换成**具体内容** —— 只有标点等于没有内容，
    # 直接不发；有内容时把末尾标点收干净，由下面的句号统一收口。
    if extra.strip():
        extra = re.sub(r"[，,；;、\s]+$", "", extra.strip())
        if not re.search(r"[\w一-鿿]", extra):
            extra = ""
    # 🩸 2026-10-28：`extra` 拼进【编辑目标】之后会被清空（下面两支都 `extra = ""`），
    #   而【编辑对象与范围】还要用它判断正面句能不能说「只」。这里先留一个标记。
    _extra_given = bool(extra)
    if body:
        # 🩸 D30（2026-10-26，2.5 轮）：补充说明属于**编辑目标**，不是时间线。
        # 以前它吊在【时间线继承】的最后一行（「背景里加一只橘猫」紧跟在
        # 「镜头切换和事件顺序保持@视频1」后面），而官方模板 `sd25-pe:559-576`
        # 的【时间线继承】只有"继承…"和"保持…"两行，`sd25-pe:71` 还要求
        # 「模板优先 —— 无论原 Prompt 是否完整，都要进入对应模板重新组织」。
        # 2.0 那边的顺序注释也是「换什么 → 范围闭环 → 补充说明 → 保什么」。
        goal = f"编辑{v}，{body}" + (f"。{extra}" if extra else "")
        extra = ""
    else:
        # 🩸 没有任何明确修改对象时，创建任务 API 仍要求提示词里出现
        # 「编辑视频/增加/加上/删除/去掉/修改/替换/改成」之一，
        # 否则会被判成参考任务，任务启动后异步报错 TaskTypeMismatch（钱已经花了）。
        goal = f"编辑视频：{v}" + (f"，{extra}" if extra else "")
        extra = ""
    if not goal.endswith(("。", "！", "？")):
        goal += "。"

    # 🩸 2026-10-28（2.5 对齐官方声音编辑模板）：换配音时**声音也是被编辑的对象**，
    #   官方 `sd25-pe:620` 的【编辑目标】是
    #   `编辑@视频1，只对<全片或明确时间段>中的<说话人或声音类别>进行<移除、替换或调整>。`
    #   这一单同时改了画面，属于两套模板的并集；官方 `:324` 允许
    #   「选择下文对应模板，**只保留当前任务需要的段落**」。
    #   原声模式（`original`）不改声音，不写这一句。
    _amode = (spec.get("audio") or "tts").strip().lower()
    _edit_audio = bool(audio_ref) and _amode in ("tts", "mix")
    if _edit_audio:
        goal += f"编辑{v}，只对全片中的说话人进行替换。"

    blocks = [
        "【编辑目标】\n" + goal,
        # 🩸 2026-10-28：换配音时【原视频职责】用官方**声音编辑模板** `:623`
        #   （`@视频1是唯一编辑母版，负责原始画面、人物动作、口型时点、镜头、
        #   剪辑节奏、其他声音和事件顺序。`）—— 它是 `:564` 的超集
        #   （多出口型时点 / 剪辑节奏 / 其他声音），不会丢任何一条职责。
        "【原视频职责】\n" + (
            (f"{v}是唯一编辑母版，负责原始画面、人物动作、口型时点、镜头、"
             "剪辑节奏、其他声音和事件顺序。") if _edit_audio else
            (f"{v}是唯一编辑母版，负责原始场景、机位、镜头运动、动作轨迹、"
             "遮挡关系和事件顺序。")),
    ]

    # 【目标素材职责】每张真正发出去的参考图各一句
    # 🩸 多人时每行必须点名是**哪一位**。以前 `_duty_role` 对所有 person 槽位
    # 都返回「目标人物的外观」，5 个人就是 5 行一字不差（台账 D1b 实测）——
    # 模板要求填具体对象：`@图片1用于<目标主体…>的<外观…>`
    # （`sd25-pe:559-575`），示例填的是 `深灰色电动巡逻车的车身结构`（`:600`），
    # 不是"目标人物"。
    # 方位唯一性 / "在场几个人" 的分母 = **整个画面**（生产里 `people` 只含勾选的人）
    # —— 上面调用 `_clauses` 之前就算好了。
    duties = []
    # 音频职责单独成段（官方 `sd25-pe:625`【目标音频职责】），不与图片混排。
    audio_duties: list[str] = []
    # 🩸 按**真正发出去的槽位**遍历（`idx` 就是发出去的顺序），不是 SLOT_ORDER：
    # 勾了但没素材的槽位不会发出去，按 SLOT_ORDER 编号会写出一张不存在的图。
    # （2026-10-26：以前这里还提过 `person_body` 派生槽 —— 那套已删，台账 D48，
    #  一个人只发一张，每张图一句职责，`sd25-pe:568`。）
    _unused: list[str] = []
    for slot in idx:
        if slot in _absent_slots:
            # 这一段没这个人：图还在（图号不能跟着段重算），但不给职责 ——
            # 给了职责就是"这段要换他"，和【编辑目标】打架。改列【未采用素材】。
            _unused.append(_pic("volc", idx[slot]))
            continue
        if slot.startswith("person"):
            # 🩸 2.5 模板的占位符是「@图片N用于<**目标主体**>的<外观…>」
            # （`sd25-pe` §视频编辑模板·【目标素材职责】），主语必须是
            # **要生成的那个人**，不是原片那位。
            # 以前写成 `{方位}人物的外观` → 「@图片1用于画面中央人物的外观」，
            # 读起来是"图片1 就是画面中央（原来）那个人的样子"，
            # 于是模型只把另一张图的东西搬过去、脸不动
            # （2026-10-24 23:12 那条 2.5：SFace 成片~原片 0.86、
            #  成片~参考 0.24）。多人时仍要点名是哪一位，点名方式用
            # "替换<方位>人物的目标人物"，不让原片人物当主语。
            # 单人**不加**定位词：那句描述写的是原片的衣服，写进职责行
            # 会让模型照着换装（2026-10-22 实测：服装/发饰换了、脸还是原片那张）。
            # 一个人一个槽位、一张图（2026-10-26 D48）—— 不需要再剥 `_body` 后缀。
            base = slot
            # 🩸 称谓统一由 `_who_by_slot` 决定（见上方 D38 注释）：
            # 方位唯一 → 「目标人物（替换左侧人物）」；分不出来 → 「目标人物A/B」。
            who = _who_by_slot.get(base, "目标人物")
            role = f"{who}的{_person_attr(slot, idx)}"
        else:
            role = _duty_role(slot)
            if slot.startswith("wardrobe") and len(_wardrobe_slots) > 1:
                # 多件衣服各自一张图 —— 不给区分词就是两条一模一样的
                # 「目标服装的款式、颜色和材质」（同 `:224` 逐条绑定）。
                # 🩸 用**衣服的主人**当区分词，不用字母：官方 `sd25-pe:423`
                # 就是「<道具A>对应@图片3，**只属于<人物A>**」——归属写在句子里；
                # 而且【编辑目标】那句写的是「只把{主人描述}的服装换成@图片N」，
                # 两处必须同一个词，否则又是一个没定义的符号。
                _wk = _wardrobe_slots.index(slot)
                _owner = (_who_by_slot.get(_tgt_slots[_wk], "")
                          if _wk < len(_tgt_slots) else "")
                if not _owner:
                    # 🩸 2026-10-28（2.5 轮，当前产出实测：9/9 个多人盘点全红）：
                    # `_who_by_slot` 只按**换人槽位**建表。**只换装不换人**时
                    # `_tgt_slots` 是空的 ⇒ 两条职责行逐字相同：
                    #   「@图片1用于目标服装的款式、颜色和材质…」
                    #   「@图片2用于目标服装的款式、颜色和材质…」
                    # 分不出是谁的衣服，违反 `sd25-pe:224`「不同主体必须逐条
                    # 绑定」。换人名单比换装名单短（换 P1 的人 + 换 P1/P2 的衣）
                    # 时 `_wk` 越界，也是同一个病。
                    # ⇒ 退回【编辑目标】那句用的**同一个词**（`_head_noun`），
                    # 两处同词，不引入字母也不新造符号。
                    _wid = [str(x) for x in (c.get("wardrobe_ids") or [])
                            if str(x).strip()]
                    _pid = _wid[_wk] if _wk < len(_wid) else ""
                    _owner = (_wardrobe_subject_25(_pid, people, _frame_ppl,
                                                desc_by_id) if _pid else "")
                # 🩸 2026-10-28（主人第四次点到这句，前几次我都在判"结构不违规"）：
                #   直接 replace 拼出的是「体型偏胖的男子**的服装的**款式、颜色和材质」
                #   —— 两个"的"连着。官方模板 `sd25-pe:559-575` 只有**一层**
                #   `@图片N用于<目标主体>的<外观、结构或材质>`，示例 `:600` 填的是
                #   「深灰色电动巡逻车的**车身结构**」。这里 `<目标主体>` = 「X的服装」、
                #   `<材质…>` = 「款式、颜色和材质」，所以「服装」后面不能再留一个"的"。
                #   ⇒ 有主人时写成「X的服装款式、颜色和材质」（同官方示例构型）。
                #   共用层的 `_DUTY_ROLE["wardrobe"]` 三家都在读，**不动**。
                if _owner:
                    _tail = role[len("目标服装"):]          # "的款式、颜色和材质"
                    role = f"{_owner}的服装" + (
                        _tail[1:] if _tail.startswith("的") else _tail)
            if not role:
                continue
        if slot == "style_ref":
            # 风格图的排他集和人物/场景图不一样：风格图里**一定有主体**
            # （色调是从那个画面里读出来的），只排「无关背景、人物或构图」
            # 挡不住模型把图里的主体也搬过来。视频那条用的是
            # `sd25-pe:360` 的「不采用其中的主体、构图、场景内容」，
            # 图这一行跟它对齐；句式仍是 `sd25-pe:568` 的「用于…，不采用…」。
            duties.append(f"{_pic('volc', idx[slot])}用于{role}，"
                          "不采用其中的主体、构图和场景内容。")
            continue
        duties.append(f"{_pic('volc', idx[slot])}用于{role}，"
                      "不采用图片中的无关背景、人物或构图。")
    # 🩸 2026-10-26 清掉的死分支：这里曾按 `sd25-pe` §4「同一主体有多份参考时…
    # 声明它们共同定义同一实体」写一段两图分工声明。
    # 但 2.5 的 caps 里 `split_person_images=False`，**同一个人永远只有一张图**
    # ⇒ `_b not in idx` 恒成立，这段一次都走不到；注释里「我们发给模型的是同一个人
    # 两张图」也是错的。已整段删除。
    if c.get("style_video") and style_video:
        # 风格参考**视频**也有自己那一行职责（原则 3「素材逐份负责」`sd25-pe:73`）。
        # 句式照 `sd25-pe:360`「@视频1用于<动作、运镜或节奏>，不采用<…>」，
        # 这里只要风格那一项；运镜和节奏**明确不取** —— 编辑母版已经锁定它们。
        duties.append("@视频2用于整体画面的色调、光影和质感，"
                      "不采用其中的主体、构图、场景内容、运镜和节奏。")
    # 这一单里"真的说过话的人"（按台词顺序去重）。`_assign_speakers` 从
    # ASR 声纹编号 + 单人镜头推出来的，比"画面里所有被替换的人"具体得多。
    _spk_ids: list[str] = []
    for _grp in (shot_lines or []):
        for _x in (_grp or []):
            _p = str(_x.get("speaker") or "")
            if _p and _p not in _spk_ids:
                _spk_ids.append(_p)

    if audio_ref:
        # 🩸 `sd25-pe:361`「@音频1用于<角色或声音类型>的<音色、台词…>」——
        # **音频也是素材，也要有自己那一行职责**（原则 3「素材逐份负责」`:73`）。
        # 以前只写在【时间线继承】里，【目标素材职责】段等于没交代这份素材管什么。
        _amode = (spec.get("audio") or "tts").strip().lower()
        if _amode in ("tts", "mix"):
            _who_duty = _sd25_who(c, idx, desc_by_id, speakers=_spk_ids,
                                  absent_slots=_absent_slots, as_list=True)
            # 🩸 2026-10-28（读 28 组产出抓到的）：**每个说话人一行**。
            #   官方 `:876`「多名说话人**分别标注**，不要只在开头统一声明」——
            #   以前写成「@音频1用于 A、B 的音色与台词」，正是被禁止的那件事；
            #   `:361` 的模板 `@音频1用于<角色或声音类型>的<…>` 本身就是一个角色一行。
            #   定不出说话人时按 `:361` 的另一种写法退到「音色与台词」本身，不硬点名。
            # 🩸 2026-10-28（2.5 对齐官方声音编辑模板）：音频职责**不进**
            #   【目标素材职责】，官方给它单开一段【目标音频职责】（`:625-626`）：
            #   `@音频1用于<目标说话人或声音类别>的<音色、台词、环境声、音效或音乐>，
            #    不采用<无关声音>。`
            #   段尾按模板原文写「不采用无关声音」，不加「其中的」「内容」。
            # 🩸 2026-10-28（全量穷举产物逐份读）：定不出说话人时以前留空，
            #   产出「@音频1用于音色与台词，不采用无关声音。」—— 官方
            #   `sd25-pe:626` 的槽位是 `<目标说话人**或声音类别**>的<音色…>`，
            #   空着 = 占位符没填（`:324`「所有占位符必须替换为具体内容」）。
            #   退到官方给的另一个选项「说话人」（`:620` 同词）。
            for _w in (_who_duty or ["说话人"]):
                audio_duties.append(f"@音频1用于{_w}的音色与台词，不采用无关声音。")
        else:
            # 🩸 2026-10-28（逐句溯源）：官方无「原片音轨」一词，用 `sd25-guide:828`
            #   的「原始音频」。
            audio_duties.append(f"@音频1用于{v}的原始音频，不采用无关声音。")
    if duties and boundary_pic:
        # 🩸🩸 2026-10-28：**首帧图也是一份素材**，原来只在【时间线继承】里出现，
        #   【目标素材职责】段完全没有它 —— 违反官方 `:73`「素材逐份负责」，
        #   尺子 T5 直接判红「@图片N 没有职责行」。
        #   官方 `:709-717` 的写法是两件事：
        #     ① 首帧图单独一行「@图片N作为首帧。」+ 该首帧定义…（`:710-711`）；
        #     ② **其它每张参考图**后面都加「，不改变@图片N定义的首帧构图」（`:712-713`），
        #        否则模型有理由拿后来的参考图覆盖首帧指认的构图。
        # 🩸 2026-10-28：官方 `:712-713` 是「**其它**每张参考图…不改变@图片1定义的首帧构图」——
        #   首帧那张图自己**不加**这句。以前无条件给所有 @图片 加，首帧图同时
        #   又被当人物参考时（`slots=["person"], boundary_pic=1`）产出一句
        #   「@图片1用于…，不改变@图片1定义的首帧构图。」= 自己约束自己。
        _bp = f"@图片{boundary_pic}"
        _bp_tag = re.compile(rf"@图片{boundary_pic}(?!\d)")
        duties = [(_d.rstrip("。") + f"，不改变{_bp}定义的首帧构图。"
                   if _d.startswith("@图片") and not _bp_tag.match(_d) else _d)
                  for _d in duties]
        # 🩸 官方 `:709-714` 的顺序：`@图片N作为首帧。`+「该首帧定义…」在**最前**，
        #   之后才是其它参考图的职责行。以前 append 在末尾，顺序与模板相反。
        duties.insert(0,
                      f"{_bp}作为首帧。\n"
                      "该首帧定义视频开始时的构图、主体位置、姿态、道具状态、场景和镜头方向。")
    if duties:
        blocks.append("【目标素材职责】\n" + "\n".join(duties))
    if audio_duties:
        # 官方声音编辑模板 `sd25-pe:625-626` 的独立段。只有真的在编辑声音时才出现
        # （原声模式 audio_duties 里是「原片音轨，不采用无关声音」，也照官方段名）。
        blocks.append("【目标音频职责】\n" + "\n".join(audio_duties))
    if _unused:
        # 逐字照 `sd25-pe:233` 的示例句式，只换编号。
        blocks.append("【未采用素材】\n" + "、".join(_unused) +
                      "未参与本任务，不用于人物、场景、道具、动作或镜头。")

    # 【编辑对象与范围】
    # 🩸 必须把**这一单里真正要改的类别**列全：只写「只修改人物」而提示词里
    #    同时改了场景/产品，就是自相矛盾（模型会二选一）。
    scope_lines = []
    # 🩸 2026-10-28：人数按**这一段**算，不是全片。分段后每一段是独立请求，
    #   「全片目标对象数量为2」在只有一个人在的第 1 段里就是自相矛盾
    #   （实测段 1 只有白衬衫男人，却写「全片目标对象数量为2」）。
    _present_tgt = [s for s in _tgt_slots if s not in _absent_slots]
    n_person = len(_present_tgt)
    targets = []
    if c.get("person") and n_person:
        # 🩸 2026-10-26 18:xx（2.5 逐一过官方）：官方模板 `sd25-pe:568` 是
        # 「只修改**<明确对象和区域>**」，`:570` 后面紧跟的兜底句又写
        # 「除以上明确修改对象外，@视频1中其他可见人物…保持原样」。
        # 画面里有三个人、只换一个时，以前的「只修改@视频1中的人物」把**三个人
        # 都算成修改对象**，和兜底句自相矛盾（模型只能二选一）。
        # ⇒ 只换了一部分人时，点名到具体对象（称谓沿用 `_who_by_slot`，
        #   与【目标素材职责】/【时间线继承】同一套，D38）。
        _n_present = len([p for p in _frame_ppl
                          if p and _present(p)])
        if _n_present > n_person:
            targets.append("、".join(_who_by_slot[s] for s in _present_tgt))
        else:
            targets.append("人物")
    if c.get("product"):
        targets.append("产品")
    if c.get("scene"):
        targets.append("背景")
    if any(s in idx for s in WARDROBE_SLOTS):
        targets.append("服装")
    if targets == ["背景"]:
        # 🩸 官方 `sd25-pe:578`「**背景替换时明确只修改主体轮廓之外的背景**」。
        # 以前只写「只修改@视频1中的背景」，边界没交代 —— 模型会把人也一起
        # 重画进新背景里（`_scope_closure` 的兜底句救不了，那是兜底不是边界）。
        # 🩸 2026-10-28（E2 全幂集 96 条破口，全是这一支）：
        #   用户写了补充要求（比如「背景里加一只橘猫」）时，这一句的「只」和
        #   「人物保持原样」会把新增对象排除在外 —— 和【编辑目标】直接打架。
        #   官方 `sd25-guide:88` 把「增加/加上」列为一等编辑（示例
        #   「@video1 中加一些小动物」），`sd25-pe:578` 要求增删对象时说明
        #   数量/位置/出现时机/受影响范围，`sd25-pe:599` 又说保持清单只写
        #   **确实不能变化**的区域。⇒ 有补充要求时去掉「只」和「人物保持原样」，
        #   但保留「主体轮廓之外」这条官方要求的边界。判据 = `ruler_sd25.P7`。
        # 🩸 2026-10-28（逐句溯源）：去掉「，人物保持原样」—— 官方 `sd25-pe:578`
        #   只写「背景替换时明确**只修改主体轮廓之外的背景**」，没有这半句；
        #   「主体轮廓之外」已经把人物挡在外面了，再加一句是自造。
        scope_lines.append(
            f"{'修改' if _extra_given else '只修改'}{v}中主体轮廓之外的背景。")
    elif targets:
        # 🩸 2026-10-28（逐条读产出抓到的自相矛盾）：用户写了补充要求（`extra`）
        #   时，这个「只」会把它**排除在外** ——【编辑目标】里写着「…。背景里加
        #   一只橘猫。」，这里却写「只修改@视频1中的目标人物。」，两句话在教
        #   模型做相反的事。
        #   官方怎么处理「增加对象」：`sd25-guide:88` 的触发关键词表里就有「增加/加上」，
        #   示例是「@video1 中加一些小动物」；`sd25-guide:770`/`:782` 两条真实示例
        #   **都不写正面「只修改…」句**，只留「其他保持不变」；
        #   `sd25-pe:550` 也只要求「写完用户指定的替换、删除和保持对象后，增加兜底句」。
        #   `extra` 已经写在【编辑目标】里，正是 `:550` 说的「**以上明确修改对象**」，
        #   紧随其后的兜底句管得住它。
        #   ⇒ 有补充要求时**只去掉一个「只」**，不另造任何句子。
        _mt = f"{v}中的{'、'.join(targets)}"
        line = (f"修改{_mt}。" if _extra_given else f"只修改{_mt}。")
        # 🩸 2026-10-26（D28）：同时换人 + 换背景时以前走这一支，
        # 「主体轮廓之外」就整句丢了（`ruler_sd25 --sweep`「同时换场景」组抓到）。
        # 边界句跟着**这个改动面**走，不该因为别的改动一起出现就消失。
        if "背景" in targets:
            # 🩸 「人物保持原样」只属于**纯换背景**那一支：这里同时还在换人，
            #    再写一句「人物保持原样」就是自相矛盾（模型会二选一）。
            # 🩸 2026-10-28（逐句溯源）：官方原句是「**背景替换时**明确只修改
            #   **主体轮廓之外的背景**」（`sd25-pe:578`）。以前写「背景只修改
            #   主体轮廓之外的**部分**」——「部分」是自造，官方没有这个词。
            line += "背景替换时只修改主体轮廓之外的背景。"
        scope_lines.append(line)
    # 🩸 E3（2026-10-23）：官方 `sd25-pe:570` 是「全片目标**对象**数量」，不是"人物"。
    # 对象 = 这次被替换的主体：人物 + 产品（`:568`【目标素材职责】的「主体/背景/商品」里，
    # 商品也占一个对象）。背景是「区域」（`:568` 把"对象和区域"并列），
    # 服装是已有对象的属性、不产生新对象 —— 两者都不计。
    # 以前只数人物，只换产品时整句不写（官方 `:974` 验收清单把"目标数量"列为必含项）。
    n_obj = n_person + (1 if c.get("product") else 0)
    if n_obj:
        scope_lines.append(f"全片目标对象数量为{n_obj}。")
    # 🩸 D8 重开（2026-10-23）：官方 `sd25-pe:568` 的第三句「不修改<需要保持的内容>」
    # 一直是缺的。画面属性（背景 / 构图 / 光线）本来就该写在这里 ——
    # 官方【时间线继承】那两行只讲**时间线**（出现时机、运动、遮挡、切换、事件顺序），
    # 不讲画面属性。以前我们把「保持…构图和景别、光线和色调不变」塞在
    # 【时间线继承】，位置错，还和 E1 补的官方固定句重叠。
    # 换场景时 `normalize:266` 已把 keep.background 关掉，不会写出
    # 「换背景 + 不修改背景」的自相矛盾。
    # 🩸🩸 2026-10-28：**只要这一单在改整体风格，就不能再说"不修改光线和色调"**。
    #   2.5 官方自己的语料里，「风格」本来就把光影色调算在里面：
    #     · `sd25-pe:813`「<空间、材质、光线或视觉风格>」——光线和视觉风格并列同一组；
    #     · `sd25-guide:665`「风格：顶级3D国漫仙侠…**水墨仙气光影**」；
    #     · `sd25-guide:1144`「整体像素武侠美术风格，**色调统一**浅蓝底」。
    #   ⇒「只把整体画面风格改成动漫」配「不修改…光线和色调」直接打架
    #     （`sd25-guide:278`「prompt 避免前后矛盾」）。判据 = `ruler_sd25.P5`。
    #   三种风格来源都算：素材图 `style_ref`、素材视频 `style_video`、纯文字 `style`。
    #   🩸 这条**只写在 2.5 自己的编译器里**，不下去改共用函数 —— 别家的口径不掺。
    # 🩸 2026-10-28：用户要在画面里新增东西时，**背景不再是"确实不能变化"的区域**
    #   （`sd25-pe:599`），不能再写「不修改…背景环境」。实测 `extra="背景里加一只
    #   橘猫"` 会和保持句直接打架。
    _keep_only = [] if _extra_adds_object(spec.get("extra") or "") else ["background"]
    _keep_only.append("framing")
    if not (c.get("style_ref") or c.get("style_video") or c.get("style")) \
            and not _extra_wants_light(spec.get("extra") or ""):
        _keep_only.append("lighting")
    nochange = _keep_sentence("volc", spec, only=tuple(_keep_only), verb="不修改")
    if nochange:
        scope_lines.append(nochange)
    # 🩸 **无条件写**。`sd25-pe:552`「每条视频编辑 Prompt **都必须**包含以下两种
    # 范围闭环之一，不能省略范围闭环」—— 没有"这一单没什么可改的"这种豁免。
    # 以前挂了 `if parts`，只有补充要求（自由文本）时整段没有闭环。
    scope = _scope_closure()
    if scope:
        scope_lines.append(scope + "。")
    if scope_lines:
        blocks.append("【编辑对象与范围】\n" + "\n".join(scope_lines))

    # 【时间线继承】
    # 🩸 这一句**只在真的换人时写**（D4）。只换场景 / 产品 / 服装时画面里
    # 根本没有"目标人物"，写它就是捏一个不存在的东西，还会和「背景替换」
    # 的要求打架（模型两头听，画面一阵一阵往回翻）。
    # 官方模板 `sd25-pe:559-575` 的占位符是 `<目标对象>继承<原对象>…` ——
    # 这一单没有目标人物，就不该有这一分句。
    # 🩸 多人时这里必须**沿用同一套称谓**（官方模板 `:575` 是
    # `<目标对象>继承<原对象>…`；一个 Prompt 里冒出两个「目标人物」一个是称谓
    # 一个是泛指，等于前面白分）。单人 / 只换一个人时逐字不动。
    # 🩸 2026-10-28：只列**这一段真的要换的人**。缺席者已经被列进【未采用素材】，
    #   再在这里写「目标人物B继承…」就是同一段里自相矛盾（实测段 1 / 段 3）。
    # 🩸🩸 2026-10-28（读产出抓到的第三条）：官方模板 `:576` 是
    #   `<目标对象>继承<原对象>每次出现…` —— **两个槽位**，`:578` 又明写
    #   「主体替换时说明**原对象和目标对象**」；`:582-597` 的动态主体替换示例
    #   用「电动巡逻车」指新主体、用「**原**骑行者」指原脸。
    #   以前多人那支把**原脸的称谓**（体型偏胖的男子）填进了<目标对象>槽，
    #   <原对象>退成泛指的「原片中被替换的对应人物」——
    #   同一句里同一个词指两个人，模型分不清谁继承谁。
    #   ⇒ 目标对象 = `@图片N中的人物`（与【目标素材职责】同一套词，不换说法）；
    #     原对象 = 「原片中的<原脸称谓>」（官方示例的「原X」写法）；
    #     多人按 `:218`「一行只定义一个主体」**逐人一行**。
    _inherit_tail = "每次出现、运动、遮挡和离开的时点、持续时长、路径与速度变化。"
    if not (c.get("person") and n_person):
        inherit = ""
    elif multi and len(_present_tgt) > 1:
        inherit = "\n".join(
            (f"{_pic('volc', idx[s])}中的人物" if s in idx else "目标人物")
            + f"继承原片中的{_who_by_slot[s]}{_inherit_tail}"
            for s in _present_tgt)
    else:
        inherit = "目标人物继承原片人物" + _inherit_tail
    # 🩸 E1（2026-10-23）：官方 `sd25-pe:572-573` 的【时间线继承】是**两行**：
    #   ① <目标对象>继承<原对象>每次出现、运动、遮挡和离开的时点…（= inherit）
    #   ② 其他人物动作、镜头运动、镜头切换和事件顺序保持@视频1。
    # 以前只写 ①，② 从来没写 —— keep 全关且不换人时【时间线继承】整段为空，
    # 而官方模板里这一行是固定的、不是可选项。
    # 句首「其他」的语义就是"除点名要改的以外"，所以用户关掉的项不列进来
    # （关掉「运镜和机位」= 允许改运镜，就不能再说"镜头运动保持"）。
    # 🩸 motion 这一项用产品自己的定义「人物动作和表情」，不砍成官方原词的
    # 「人物动作」：keep 里 motion 本来就含表情，砍掉等于用户勾了却没要求。
    # 换配音时例外 —— 嘴部动作属于表情，保了就是把原片口型照搬（同 `_keep_sentence`）。
    _new_dub = bool(audio_ref) and (spec.get("audio") or "tts").strip().lower() != "original"
    # 🩸 2026-10-26 18:xx（2.5 逐一过官方 · 功能 5【时间线继承】）：
    # **按官方模板逐字写**。`sd25-pe:572-573` 的第二行是固定文本：
    #   「其他**人物动作、镜头运动、镜头切换和事件顺序**保持@视频1。」
    # 上一版偏离两处：① motion 加了「和表情」（模板里没有这个词）；
    # ② 最后一项用「、」连（模板是「和」）。都按官方改回来。
    # 之前「人物动作和表情」是为了让 keep.motion 的语义完整，但这一行是
    # **固定模板句**，不是自由描述；而且换人本来就该改脸，多保一层表情
    # 只会往"这张脸别动"上加码（与 2.0 同一结论，见 D52 §七）。
    _TL_ITEMS = (("motion", "人物动作"),
                 ("camera", "镜头运动"), ("rhythm", "镜头切换"))
    _tl = [name for k, name in _TL_ITEMS if spec["keep"].get(k)]
    _tl.append("事件顺序")   # 事件顺序没有开关，编辑任务恒保
    # 官方句式：前几项用「、」，最后一项前用「和」
    # 🩸 2026-10-28（逐句溯源）：只剩一项时**不带「其他」**。原句「其他事件顺序
    #   保持@视频1」里「其他」没有指代对象（用户把三个开关全关了，除事件顺序外
    #   没有别的可保），官方 `sd25-pe:575` 的「其他」是相对前面「点名要改的人」
    #   而言的，单项没有这层对照。
    timeline_keep = (f"{_tl[0]}保持{v}。" if len(_tl) == 1 else
                     f"其他{'、'.join(_tl[:-1])}和{_tl[-1]}保持{v}。")
    # 【时间线继承】只留**口型句**（换配音时的重做要求）。画面属性的保持句
    # 已挪到【编辑对象与范围】的官方第三句（见上面 nochange）。
    #
    lip = _lip_line(spec, audio_ref)
    audio_clause = ""
    mute_clause = ""
    voice_lines: list[str] = []
    if audio_ref:
        who = _sd25_who(c, idx, desc_by_id, speakers=_spk_ids,
                        absent_slots=_absent_slots)
        mode = (spec.get("audio") or "tts").strip().lower()
        if mode in ("tts", "mix"):
            # 🩸 台词内容必须**逐句写进提示词**。指南 `:907`「音频翻译语种混淆」
            # 的解法第一条就是「按角色提供完整的**目标语言台词及时间轴**」；
            # 以前只写"音色与台词"，模型只能自己编一套词。
            # 格式按 `sd25-pe:869`「说话人 + {台词}」，台词标记 `{}` 见 `:867`。
            # 逐句兜底只能用**没有歧义**的指代：用户勾了说话人，或画面里只有一个人。
            # 靠声纹推出来的"这一镜里有谁说过话"不能拿来套每一句 —— 那等于替
            # 每一句编一个说话人（官方 `:876` 要的是逐句分别标注）。
            # 🩸 2026-10-28（说话人探针）：以前判的是**换脸槽位数** ——
            #   画面里两个人、只换其中一个时它就是 1，于是"说话人未知"的台词
            #   被静默指派给**换了脸的那个人**（实测 `@图片1中的人物说{旁白一句}`）。
            #   `video_edit._assign_speakers` 的口径是「两个证据都没有的句子不标，
            #   编译器退回**不指名**」，官方 `:982` 也要求说话人与输入一致 ——
            #   输入里没说是谁说的，就不能替他指。改成看**画面在场人数**。
            _n_on_screen = len([x for x in _frame_ppl if _present(x)])
            _unambiguous = bool([x for x in (c.get("speaker_ids") or [])]) or \
                _n_on_screen <= 1
            voice_lines = _sd25_lines(
                shot_lines, who if _unambiguous else "",
                speaker_label=lambda pid: _sd25_speaker_label(
                    pid, c, idx, desc_by_id))
            if voice_lines:
                # 🩸 不再写「<谁>说以下台词」这种**开头统一声明**：官方 `:876`
                # 「多名说话人**分别标注**，不要只在开头统一声明」。说话人都写在
                # 每句台词上，这里只留口型要求（口型不归某个人）。
                # 🩸 2026-10-28（逐句溯源）：原句「台词见下…不得另说一套台词」
                #   两个半句都是自造，删掉。口型要求已由 `_lip_line` 那句
                #   （官方 `sd25-guide:929`「口型做出对应的精准改变」）统一说一次 ——
                #   这里再写一遍就是同一份提示词里两句几乎一样的话。
                audio_clause = ""
            else:
                # 这一段没有可用台词（比如根本没做语音识别）→ 不能写
                # 「说以下台词」再空着，那是残句，模型会自己补一套词。
                # 🩸 2026-10-28：`who` 为空时以前产出无主语的
                #   「使用@音频1的音色与台词，…」（全量穷举产物逐份读抓到）。
                #   同样退到官方 `:620` 的中性词「说话人」。
                # 口型那半句由 `_lip_line` 统一说一次，这里不重复。
                audio_clause = f"{who or '说话人'}使用@音频1的音色与台词。"
            # 🩸 `sd25-pe:875`「多人对话要逐阶段绑定说话人与音频，并写明
            # **其他人物自然闭口聆听**」。点了说话人、画面里还有别的被替换人物时
            # 必须写这句 —— 不写的话模型会让所有人一起动嘴。
            # 谁在说话，两个来源，推出来的优先：
            #   ① 每句台词上的 `speaker`（`video_edit._assign_speakers`：
            #      ASR 声纹编号 + 画面定人，全自动）；
            #   ② `speaker_ids`（界面里"谁在说话"那个控件）。
            # 🩸 **②在火山通道上目前用不上**：那个控件写死了
            #    `v-if="effChannel === 'minimax'"`（`diagnose.vue`），火山永远传空数组。
            #    留着当兜底 —— 哪天给火山也开控件，这里有现成的取值路径，
            #    不用再回来改一遍。别看到它就以为用户能勾。
            # 画面里同时有两个人说话（集合大小 >1）时不写"闭口"——那会自相矛盾。
            _sp_set = {str(x.get("speaker") or "")
                       for grp in (shot_lines or []) for x in (grp or [])
                       if str(x.get("speaker") or "")}
            _pids = [str(x) for x in (c.get("person_ids") or [])]
            _sids = ([_sp_set.pop()] if len(_sp_set) == 1
                     else [str(x) for x in (c.get("speaker_ids") or [])])
            _speak = {PERSON_SLOTS[_pids.index(p)] for p in _sids
                      if p in _pids and _pids.index(p) < len(PERSON_SLOTS)}
            # 🩸 2026-10-28（分段一致性实测）：缺席者已经列进【未采用素材】，
            #   再对他写「@图片2中的人物自然闭口聆听」就是让模型去找一个这段
            #   根本没有的人（实测段 1 产出原样如此）。
            _mute = [f"{_pic('volc', idx[s])}中的人物" for s in PERSON_SLOTS
                     if s in idx and s not in _speak and s not in _absent_slots]
            # 还有「没定出说话人」的句子时不许写"其余人闭口" —— 那句完全可能就是
            # 被点名闭口的人在说（2026-10-25 实测：一句点名、一句没定，闭口句就
            # 和没点名那句打架）。用户自己勾了说话人才是权威，那种情况照写。
            _unnamed = any(
                (x.get("text") or "").strip() and not str(x.get("speaker") or "")
                for grp in (shot_lines or []) for x in (grp or []))
            if _speak and _mute and (bool(c.get("speaker_ids")) or not _unnamed):
                mute_clause = f"{'、'.join(_mute)}自然闭口聆听。"
        else:
            # 🩸 2026-10-28（逐句溯源）：官方没有「原片音轨」这个词（2.5 全部文档
            #   0 命中），官方用的是「**原始音频**」（`sd25-guide:828`
            #   「…原始音频，以及 @视频1 的精确叙事顺序与时序」）。
            audio_clause = f"@音频1是{v}的原始音频，原样保留在成片中。"
    shot_clause = (_shot_plan(shot_cuts) if shot_cuts is not None else "")
    # 🩸 D7（2026-10-23）：边界帧句必须写进**五段模板之内**（【时间线继承】）。
    # 以前它是模板外追加的中文句（出处 hypit `craft/video-direction.md:51-58`，
    # 第三方），违反 `sd25-pe:71`「模板优先 —— 无论原 Prompt 是否完整，都要
    # 进入对应模板重新组织」。
    # 🩸 L2-2（2026-10-23）：句式换成官方「关键帧锚点」章（`sd25-pe:699-716`）。
    # 原来套的是 `sd25-pe:646`「## 向后延长」的「延长片段第一个画面直接承接
    # @视频1的尾帧：…」—— 那是**延长任务**模板，我们做的是**编辑任务**。
    # 官方 `:703`：固定首帧时**必须单独写出** `@图片N作为首帧。`，不得弱化为
    # 「仅作为首帧参考」「参考开场构图」，也不要和后续动作压在同一句；再另起
    # 一句补充该帧定义的构图、主体位置、姿态、道具状态、场景和镜头方向。
    # 下面两行逐字取自官方模板（`:710-716`，只把图片编号换成实际编号、
    # 去掉末尾占位符尖括号）。
    boundary_line = ""
    if boundary_pic:
        # 首帧那两句（`@图片N作为首帧。` + 该首帧定义…）已经写在
        # 【目标素材职责】里（见上面 `if duties and boundary_pic`）——
        # 官方 `:709-717` 里它们就属于职责段。这里只留时间线这一句，不重复。
        boundary_line = (
            f"画面从@图片{boundary_pic}定义的首帧自然开始。\n"
            "保持人物身份、道具归属、空间关系和视觉风格连续。")
    lines = [x for x in (inherit, timeline_keep, lip, shot_clause, audio_clause,
                         mute_clause, *voice_lines, boundary_line, extra) if x]
    blocks.append("【时间线继承】\n" + "\n".join(lines))

    # 🩸 2026-10-28（2.5 对齐官方声音编辑模板）：官方 `:631-632` 的【保持内容】是
    #   `保持@视频1中的<其他对白、口型时点、环境声、动作音效、画面、镜头和剪辑节奏>不变。`
    #   `<…>` 是**槽位**，`:324` 要求「所有占位符必须替换为具体内容」——
    #   所以按这一单真实的改动面填，不是照抄整串：
    #     · 画面 —— 这一单在换人，画面**要变**，不填；
    #     · 口型时点 —— 换了脸和音色，口型要重做，不填（与【时间线继承】的口型句一致）；
    #     · 镜头和剪辑节奏 —— 【时间线继承】的 `:575` 那句已经保了，不重复。
    #   只填 `:632` 槽位里还没被别处覆盖的三项。
    if _edit_audio:
        # 官方 `:628-629`【声音编辑范围】`只修改<明确的说话人、声音类别或时间段>。`
        # 填「说话人」—— 这一单改的就是说话人的音色与台词，BGM/环境声/动作音效
        # 归下一段的【保持内容】管。缺这段时产物没有交代"声音域里改什么"。
        blocks.append("【声音编辑范围】\n只修改@视频1中的说话人。")
        blocks.append("【保持内容】\n"
                      "保持@视频1中的其他对白、环境声和动作音效不变。")

    # 🩸 2026-10-29 主人拍板「直接禁止字幕」—— AI 重画以后字幕会写错字，
    #   与其让它画一串糊字，不如明说不加。
    #   **这是官方要求，不是我们自己加的**：官方 skill `sd25-pe:876`
    #   「不需要字幕时**同时写明画面不显示字幕**」；`:882` 无对白任务也要
    #   「画面不显示字幕或标牌」。指南 `:229` 的负向控制示例也是同一个意思
    #   （「不额外加入对白字幕」/「不要字幕」），官方示例 `:612`/`:637` 写的
    #   就是「没有旁白，画面不显示字幕、文字或标牌」。
    #   用「画面不显示字幕」而不是「不额外加入对白字幕」：后者听起来只禁对白字幕
    #   （片名/说明文字还能留），主人要的是全禁。
    #   🩸 不能用 2.0 那句「避免生成任何文字或字幕」—— 那是 2.0 兜底句，
    #     写进 2.5 会被 C2 判成兜底句漏进来（`ruler_sd25.c2_no_boilerplate`）。
    #   🩸 不加段标题：官方编辑类五段里没有「约束」段，硬造段名等于改结构。
    blocks.append("画面不显示字幕。")

    return "\n\n".join(blocks)

# ---- 2.5 台词与说话人 ----
# 2.5 的台词也是 `{}`（`sd25-pe:867` 特殊字符表：音乐 `()`、音效 `<>`、
# **台词 `{}`**、字幕 `【】`），完整格式见 `:869`
# 「语言 + 可选的地区变体或口音 + 表达方式 + 说话人 + {台词}」。
# 🩸 台词内容必须写进去：指南 `:907`「音频翻译语种混淆」的解法第一条就是
# 「按角色提供完整的**目标语言台词及时间轴**」，只写"音色与台词"等于让模型自己编。
_SD25_LANG_LEAD = {
    # 🩸 2026-10-26（2.5 补标准）：英语这一项以前写的是 `in English`，夹在中文
    # 句子里成了「目标人物in English{…}」。官方 `sd25-pe:876` 的原话是
    # 「至少明确写"**使用英语**"」，其余 15 个语种也都是「用X语说道」——
    # 改成同构的「使用英语说道」，不是新增规则，是回到官方那句话。
    "ja": "用日语说道", "ko": "用韩语说道", "en": "使用英语说道",
    "th": "用泰语说道", "vi": "用越南语说道", "id": "用印尼语说道",
    "ms": "用马来语说道", "tl": "用菲律宾语说道", "es": "用西班牙语说道",
    "mx": "用西班牙语说道", "pt": "用葡萄牙语说道", "ru": "用俄语说道",
    "ar": "用阿拉伯语说道", "de": "用德语说道", "fr": "用法语说道",
    "it": "用意大利语说道",
}

def _short_name(desc: str) -> str:
    """盘点描述 → 说话人位上能用的**短名词**（只 2.5 用）。

    🩸 2026-10-28（读 28 组产出抓到的断句）：整段描述自带逗号，塞进
      「X 说{台词}」和「@音频1用于 X 的<音色…>」会把句子切断。
      官方 `sd25-pe:876` 的说话人槽是「<一个名词短语>」。

    🩸 为什么不直接用共用的 `_head_noun`：它的人称词表里没有「女士」这一族
      （实测 `黑裙子女士` 被判成"不是人" → 返回空），而那是盘点里完全可用的
      指代。**它在 `edit_spec.py` 里，三家共用，按主人的规矩不许按一家的需要改它**
      —— 所以在 2.5 自己这儿兜一层：共用口径取不到，就退到第一个分句。
      两条都不成立才返回空，由调用方退回"不指名"。
    """
    s = _head_noun(desc)
    if s:
        return s
    head = re.split(r"[，；,;]", (desc or "").strip())[0].strip()
    return head if re.search(r"[一-鿿]{2,}", head) else ""


def _sd25_speaker_label(pid: str, c: dict, idx: dict[str, int],
                        desc_by_id: dict | None) -> str:
    """盘点人物 id → 提示词里的指代（尽量落到 `@图片N中的人物`）。

    落不到图号（这个人这次没有换脸图）时退回 `@视频1中<外观>` ——
    说的是**原片里的那个人**，不是新脸。宁可不指名，也不张冠李戴。
    """
    ids = [str(x) for x in (c.get("person_ids") or [])]
    if pid in ids:
        k = ids.index(pid)
        if k < len(PERSON_SLOTS) and PERSON_SLOTS[k] in idx:
            return f"{_pic('volc', idx[PERSON_SLOTS[k]])}中的人物"
    # 🩸 2026-10-28（读 28 组产出才发现的）：以前把**整段**盘点描述塞进说话人位，
    #   而描述自带逗号，`X 说{台词}` 直接断成三截：
    #     `@视频1中年轻女子，黑色长发梳成古装高髻，身着广袖古装说{别找我}`
    #   官方 `sd25-pe:876` 的说话人槽是「<一个名词短语>」，不是整段外观；
    #   取到第一个逗号为止后是「@视频1中年轻女子」，句子恢复通顺。
    #   与 `_head_noun` 同源 = 和【编辑目标】里的宾语是**同一个词**，模型不用跨段换算。
    d = _short_name(_who(desc_by_id, pid, "zh"))
    return f"{_vid('volc')}中{d}" if d else ""

def _sd25_lines(shot_lines: list[list[dict]] | None, who: str,
                speaker_label=None) -> list[str]:
    """逐镜台词 → 2.5 的句子列表。跨切被拆成 start/end 的两半要拼回一句。

    `speaker_label(pid)`：某一句带了 `speaker`（画面推断出来的说话人 id）时，
    用那个人的指代代替统一的 `who` —— `sd25-pe:875`「多名说话人**分别标注**，
    不要只在开头统一声明」。判不出说话人（两人同框）时句子没有 `speaker`，
    就还是统一指代。
    """
    out: list[str] = []
    pending: dict | None = None

    def emit(text: str, lang: str, sp: str = "") -> None:
        t = (text or "").strip()
        if not t:
            return
        # 🩸 2026-10-28（英文全链路探针）：`{}` 是 2.5 的**台词标记**
        #   （`sd25-pe:867` 的特殊字符表）。台词内容里再出现 `{}` 就成了嵌套 ——
        #   实测 `He said "run" {twice}` 产出 `{He said "run" {twice}}`，
        #   模型不知道台词在哪结束。`sd25-pe:880`「同一符号不能承担两种含义」。
        #   ASR/用户文案里出现花括号本身就不是要念的内容，直接清掉。
        t = re.sub(r"[{}]", "", t).strip()
        if not t:
            return
        one = who
        if sp and speaker_label:
            _w = speaker_label(sp)
            if _w:
                one = _w
        lead = _SD25_LANG_LEAD.get((lang or "zh").strip().lower(), "")
        if not one:
            # 定不出说话人 → 只写台词标记本身（官方 `:873` 的 `{}`），不编主语。
            out.append(f"{lead}{{{t}}}" if lead else f"{{{t}}}")
            return
        out.append(f"{one}{lead}{{{t}}}" if lead else f"{one}说{{{t}}}")

    for grp in (shot_lines or []):
        for x in (grp or []):
            t = (x.get("text") or "").strip()
            if not t:
                continue
            part = (x.get("part") or "").strip()
            sp = str(x.get("speaker") or "")
            if part == "start":
                pending = {"text": t, "lang": x.get("lang") or "zh",
                           "speaker": sp}
                continue
            if part == "end" and pending:
                t = pending["text"] + t
                lang = pending["lang"]
                sp = sp or pending.get("speaker") or ""
                pending = None
            else:
                lang = x.get("lang") or "zh"
                if pending:
                    emit(pending["text"], pending["lang"],
                         pending.get("speaker") or "")
                    pending = None
            emit(t, lang, sp)
    if pending:
        emit(pending["text"], pending["lang"], pending.get("speaker") or "")
    return out

#: 🩸 2026-10-28（E17）：盘点描述里的**敬称**族（女士/先生/小姐/太太…）。
#: 共用层 `edit_spec._head_noun` 的词表里没有这一族 —— 「女性/女子/姑娘」有，
#: 「女士/先生」没有，于是「黑裙子女士」提不出中心词 ⇒ 称谓退「人物」⇒
#: 两个目标都这样时整单退字母（正文里的 A/B 从来没有定义过，
#: 官方 `sd25-guide:1203-1209` 要的是用**外观**指认）。
#: ⚠️ **只补在 2.5 自己的编译器里**：那份词表 2.0 也读（`volc20_compile.py:237/337`），
#: 2.5 发现的缺口不往回改共用层 —— 两家输出不同，尺子也不能串。
_SD25_HEAD_EXTRA = re.compile(
    r"(?:女士|先生|小姐|太太|大叔|阿姨|大爷|大妈|老头|老太|男童|女童)$")


def _feat_label_25(desc: str, cloth: bool = True) -> str:
    """盘点描述 → 「特征A、特征B的人物」；取不到特征返回空串。

    🩸 为什么 2.5 自己写一份，不用共用层 `_feat_phrase`：
      · 那份的「缺人称词就补『人物』」是 2026-10-27 只给 2.0 开的能力
        （`sd20=True`），2.5 传进去要借用 2.0 的开关名，读起来像"2.5 当 2.0 处理"。
      · 它有个真实缺口：**单分句描述整句被丢掉**（`feats = parts[:-1]`）——
        「穿红色外套」这种一句到底的描述返回空。2.0 现在的产出已经验收过，
        不能为了 2.5 往回改它。
    口径与官方一致：`sd25-guide:1203-1209` 的双人换装示例就是
    「视频中**深色衣服的男子**的服饰替换为 @图片 2」——用画面看得见的外观指认。
    封顶 2 个特征（与 2.0 同口径，不是官方上限 3，见 `OPEN-DEFECTS` §13.13）。
    """
    raw = re.sub(r"[\r\n\t]+", " ", (desc or "")).strip().rstrip("。．.")
    if not raw:
        return ""
    # 群体描述不是一个人（与前端 `diagnose.vue` 的 `invPickable` 同一套词表）
    if re.search(r"多名|数名|几名|若干|一群|众人|人群|民众|路人|群众|背景人物|其他人", raw):
        return ""
    parts = [x.strip() for x in re.split(r"[，,；;]", raw) if x.strip()]
    if not parts:
        return ""
    if _PERSON_HEAD.search(parts[0]):
        return parts[0]          # 「东亚女性」这种已经是完整称谓，原样用
    # 末段是「…的男性」时，中心词单独拿出来，前面那半句仍是特征
    m = re.search(r"的([^，；,;的]{1,4})$", parts[-1])
    head = m.group(1) if (m and _PERSON_HEAD.search(m.group(1))) else ""
    if head:
        tail = parts[-1][:m.start()].strip()
        feats = parts[:-1] + ([tail] if tail else [])
    else:
        feats = parts            # 单分句也留（共用层这里会整句丢掉）
    flat: list[str] = []
    for f in feats:
        flat.extend([x.strip() for x in re.split(r"、", f) if x.strip()])
    if not cloth:
        # 换人句的**宾语**不能带服装：实测（2026-10-24）写进去模型会照着改衣服、
        # 脸一帧不动。服装只留在称谓/定义侧（`cloth=True`）。
        keep = [x for x in flat if not x.startswith(_CLOTH_HEAD)]
        flat = keep or flat[:1]
    flat = flat[:2]
    if not flat:
        return ""
    return "、".join(flat) + "的" + (head or "人物")


def _who_label_25(p, pool, desc: str) -> str:
    """2.5 的称谓：先走共用层，**只有它提不出人**时才用 2.5 自己的兜底。

    共用层已经把方位、外观短语、「人物」三档排好了；这里只加两档，
    不改前三档的任何行为。

    🩸 2026-10-28（2.5 调试轮）：**真实盘点 30 条里有 6 条（20%）描述没有
    「男子/女子」这类中心词** —— 全是「穿黑色长袖上衣，短发，体型壮实」这种写法。
    共用层 `_who_label` 对这种描述只能返回「人物」，多人时全部撞车 → 整单退字母。
    而官方 2.5 的编辑示例本身就是**用外观指认**：
    `sd25-guide:1203-1209`「视频中**深色衣服的男子**的服饰替换为 @图片2」。
    ⇒ 补一档：缺中心词时把特征拼成「X、Y的人物」。
    `_feat_phrase` 里这条能力 2026-10-27 先给 2.0 开了（`sd20=True`），2.5 当时
    **故意没跟**（分模型改动不串轮），现在轮到 2.5 补上。
    """
    lab = _who_label(p, pool, desc)
    if lab and lab != "人物":
        out = lab
    else:
        head = re.split(r"[，；,;]", (desc or "").strip())[0].strip()
        out = (head if (head and _SD25_HEAD_EXTRA.search(head))
               # 外观档：缺中心词也要能指认（缺了就是"图白传"，2.5 侧同一批真实数据）
               else (_feat_label_25(desc or "") or lab))
    # 🩸 2026-10-29（D72）：**称谓会被别人套用**时换成只属于他的特征。
    #   真机 `686dc484` 8 人场里 4 位都以「黑人男性，」开头，共用层 `_who_label`
    #   走 `_head_noun` 直接给「黑人男性」→ 四人同名 → 整单退字母，写出
    #   「只把黑人男性（目标人物A）替换为@图片1…」「…（目标人物B）…」——
    #   字母只是换个叫法，**画面里到底是哪个人照样没有答案**。
    #   方位档（「画面左侧的人物」）本来就唯一，不参与去歧义。
    if out.startswith("画面") or out == "人物":
        return out
    return _disambiguate_25(
        out, desc or "",
        _others_text_25(pool, str((p or {}).get("id") or "")))


def _sd25_who(c: dict, idx: dict[str, int],
              desc_by_id: dict[str, str] | None = None,
              speakers: list[str] | None = None,
              absent_slots: set[str] | None = None,
              as_list: bool = False):
    """2.5 提示词里的"说话人"指代。点了 `speaker_ids` 就只写点名的那些人。

    🩸 `sd25-pe:875`「多人对话要**逐阶段绑定说话人**与音频」、
    `:218`「禁止把多个主体和多个素材压缩在同一句范围映射中」。
    以前不看 `speaker_ids`，双人画面一律把两个人一起写成说话人 ——
    模型分不清谁该张嘴（2.0 那侧同样的坑已经踩过）。

    🩸 `speaker_ids` 这一支**在火山通道上目前用不上**（界面控件只对 H3 显示，
    见 `_volc_25` 里的说明）；火山现在走逐句 `speaker`（自动推断）。
    这里的取值路径保留，是为了将来给火山开控件时不用重写。
    """
    ids = [str(x) for x in (c.get("person_ids") or [])]
    sid = [str(x) for x in (c.get("speaker_ids") or [])]

    def lab(pid: str) -> str:
        if pid in ids:
            k = ids.index(pid)
            if k < len(PERSON_SLOTS) and PERSON_SLOTS[k] in idx:
                return f"{_pic('volc', idx[PERSON_SLOTS[k]])}中的人物"
        # 同上：说话人只要**一个名词短语**（`sd25-pe:876`），不要整段外观。
        d = _short_name(_who(desc_by_id, pid, "zh"))
        return f"{_vid('volc')}中{d}" if d else ""

    named = [x for x in (lab(p) for p in sid) if x]
    if named:
        return named if as_list else "、".join(named)
    # 界面没勾时，用**这一单里真的说过话的人**（`_assign_speakers` 从声纹编号 +
    # 单人镜头推出来的），而不是画面里所有被替换的人。
    derived = [x for x in (lab(p) for p in (speakers or [])) if x]
    if derived:
        return derived if as_list else "、".join(derived)
    # 🩸 2026-10-28（分段一致性实测）：缺席者不算"画面里的人"。
    #   以前用的是全片槽位 → 段里只有一个人、这段又没定出说话人时，
    #   `len(pics)==2` 会走"两人并列 → 不点名"那一支，白白丢掉唯一候选。
    pics = [f"{_pic('volc', idx[s])}中的人物" for s in PERSON_SLOTS
            if s in idx and s not in (absent_slots or set())]
    # 画面里只有一个人：他本来就该是说话人，直接点名，没有歧义。
    if len(pics) <= 1:
        one = pics[0] if pics else "人物"
        return [one] if as_list else one
    # 🩸 画面里两个人、又定不出谁在说 → **不点名**，绝不并列。
    # 并列 = 编一个不存在的说话人，还会和「其余人自然闭口聆听」直接打架
    # （2026-10-25 实测就是这么输出的）。官方 `sd25-pe:876`「多名说话人
    # **分别标注**，不要只在开头统一声明」—— 并列恰恰是"统一声明"的反面。
    return [] if as_list else ""
