"""火山 Seedance 2.0 的提示词编译器（本文件只管 2.0）。

🩸 2026-10-26 模型分离 L3：从 `edit_spec.py` 原样搬来，**一个字符没改**。
2.0 走官方一段式（`sd2-pe:118`）+ 官方兜底包，2.5 走五段模板、H3 走六段英文 ——
三家结构互不相同，改一家不该碰另外两家的代码。

依赖方向是单向的：`volc20_compile` → `edit_spec`（共用工具）。
`edit_spec` **不许**在模块级 import 本文件。
"""
from __future__ import annotations

import re

from app.services.edit_spec import (  # noqa: F401  （共用的槽位常量与工具）
    PERSON_SLOTS,
    WARDROBE_SLOTS,
    _clauses,
    _CLOTH_HEAD,
    _feat_phrase,
    _head_noun,
    _inline,
    _keep_sentence,
    _multi,
    _others_unchanged,
    _pic,
    _present,
    _LANDMARK_RE,
    _split_feats,
    _PERSON_HEAD,
    _uniq_pos,
    _vid,
    _who,
)
from app.services.models.base import Dialect


def _landmark_phrase_20(desc: str) -> str:
    """只用**标志性特征**拼的指认短语；挑不出来返回 ""（不许硬编一个）。

    🩸 2026-10-26 22:xx：**取最短的那个标志分句**，不要全塞进去。
    真实盘点 `14ff242a` 的 P2 一个分句里就写了「穿白色西装套装、浅蓝色衬衫、
    灰色领带」，全带上就是 25 个字——越写越长正是要躲开的坑（官方 `:121`）。
    装饰性的「带深棕色饰带的」也先剥掉：认人只要「草帽」「礼帽」这几个字。
    """
    feats, head = _split_feats(desc)
    if not head:
        return ""
    got = []
    for f in feats:
        if not _LANDMARK_RE.search(f):
            continue
        f = re.sub(r"带[^、，,]{1,10}饰带的", "", f).strip()
        if f:
            got.append(f)
    if not got:
        return ""
    # 🩸 按**整个分句**取最短，不要按「、」切碎：`14ff242a` 的 P2 有个分句是
    # 「穿白色西装套装、浅蓝色衬衫、灰色领带」，切碎后最短的是「灰色领带」——
    # 一条领带认不出人；同一句里真正显眼的是「佩戴白色礼帽与黑墨镜」。
    return min(got, key=len) + "的" + head



def _disambiguate_20(own: str, desc: str, others_text: str,
                     cloth: bool = True) -> str:
    """`own` 在同画面**别人**的描述里也成立时，换成只属于他的特征短语。

    🩸 2026-10-29（D71）：真机盘点 `686dc484` 8 人场里有 4 位描述都以
    「黑人男性，」开头，区别全在后面（圆顶礼帽 / 反光墨镜 / 平顶贝雷帽 / 墨镜）。
    `_feat_phrase` 的「首段以人称名词收尾就原样返回」把他们全写成「黑人男性」，
    四条 `<主体N>` 定义一字不差 —— 盘点给得起信息，是编译器丢的。

    🩸 为什么以前没兜住：唯一性修正早就写在这里，但它用 `_split_feats(own)`
    取"这句用了哪些特征"，而 `_split_feats` 对**没有「的X」结尾**的描述返回
    **空列表**（它把最后一段当中心词，取不到就整段丢掉）——「黑人男性」正是
    这种形状 ⇒ `used == []` ⇒ `if used and …` 恒假 ⇒ 修正从没执行过一次。
    现在按「、」切 `own` 本身来判，不绕 `_split_feats`。
    """
    if not own or not others_text:
        return own
    used = [x for x in re.split(r"、", own) if x.strip()] or [own]
    if not all(f in others_text for f in used):
        return own
    # 🩸 自己切分句，**不用 `_split_feats`**：它对没有「的X」结尾的描述会把最后
    #   一段整个丢掉（`parts[:-1]`）——「黑人男性，戴红色帽子」这种两段描述
    #   正好只剩「黑人男性」，等于没取到特征（D71 第二次踩到的同一个坑）。
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

    # `cloth=False`（换人句的宾语）先不用服装 —— 写进去模型会照着改衣服、
    # 脸一帧不动（`_clauses` 里 2026-10-24 那次实测）。但**两人只差衣服**时
    # 还得退回服装：写出两句一模一样是**必然**换错，带一件衣服只是有风险。
    picks = _pick([f for f in flat if not f.startswith(_CLOTH_HEAD)]) if not cloth \
        else _pick(flat)
    if not picks:
        picks = _pick(flat)
    if not picks:
        return own
    # 描述里没有「的X」中心词时补「…的人物」：与 `_feat_phrase` 缺人称词时的
    # 兜底同一个写法（带特征的定义短语，不是裸「人物」）。
    return f"{picks[0]}的{head}" if head else f"{picks[0]}的人物"


def _collides_others(phrase: str, others_text: str) -> bool:
    """这句指认里的特征在**同画面别人**的描述里**全都**出现过 → 指不出是谁。

    `_disambiguate_20` 会尽量换一个只属于他的特征；换不出来时它原样返回，
    这时候就靠这里判「还是撞车」，让调用方退回方位档。
    """
    if not phrase or not others_text:
        return False
    used = [x for x in re.split(r"、", phrase) if x.strip()] or [phrase]
    # 🩸 末段常带「的男性/的人物」这类人称中心词（`_feat_phrase` 拼的），
    # 而别人的盘点描述里特征是**逗号分句**，不会原样带这个尾巴 ——
    # 不剥掉就永远比不中，撞车永远判不出来。
    used = [re.sub(r"的(男性|女性|男子|女子|男生|女生|人物|男孩|女孩|老人|少年|人)$",
                   "", x) for x in used]
    used = [x for x in used if x]
    return bool(used) and all(f in others_text for f in used)


def sd20_locator(per: dict | None, pool: list[dict] | None = None) -> str:
    """2.0 认人用的**唯一**函数：编译器写什么，闸就判什么，不许两套。

    三档（2026-10-30 主人拍板：方位由「优先」降为「兜底」）：
      ① 画面里只有 TA 一个 → 不写定位词（调用方早退，见 `_sd20_person_tags`）；
      ② **特征能唯一指认他** → 特征短语（官方 `:95` 的定义形状，
        如「短卷发男性」「东亚男性」）。判据 = 这句话里的特征在同画面
        **别人**的描述里不成立（`_collides_others`）；
      ③ 特征取不到、或跟别人撞成一句 → 才用盘点给的**方位**
        「画面中央的人物」（官方 `:153`）。

    🩸 2026-10-30 为什么换先后（主人：「方位优先你自己都说了是很多人，
    到底多少人才算多人」）：
      旧顺序的触发条件是「画面 ≥2 人」（`edit_spec._multi`），2 个人和 8 个人
      一条规则不分档 —— 于是 `ff561d97`（1 男 1 女，一眼能分）被写成
      「画面中央的人物」，而 `686dc`（8 人、三个方向都有人）反倒因为方位撞车
      掉到特征档。全库实测正好是反的：8 人那条 2/2 换上（best 0.547 / 0.645），
      2 人那条 2/2 只换衣服不换脸（0.228 / 0.239，share 0.0）。
      现在改按「特征能不能唯一指认」分，不再按人数拍一个阈值：
      特征能指认就不写方位（和官方 `:95` 的定义形状一致），
      指认不了才用方位 —— 10-27 主人「要换的人不一定在中间」的诉求仍然成立，
      因为那种场合本来就没法用特征指认。

    ③ 档最后做**唯一性**检查：这句话里的每个特征在**同画面别人**的描述里
    都出现过，说明它也能指别人（等于没指认），改用只属于他的那个特征。
    """
    desc = str((per or {}).get("desc_zh") or "")
    others_text = " ".join(
        re.sub(r"[\r\n\t]+", " ", str(p.get("desc_zh") or ""))
        for p in (pool or [])
        if p and _present(p)
        and str(p.get("id") or "") != str((per or {}).get("id") or ""))
    if pool:
        # ② 特征档：能唯一指认就到此为止，**不写方位**
        _f = (_feat_phrase(desc, cloth=False, sd20=True)
              or _feat_phrase(desc, cloth=True, sd20=True))
        if _f:
            _f = _disambiguate_20(_f, desc, others_text, cloth=False)
            if not _collides_others(_f, others_text):
                return _f
        # ③ 方位档：特征指认不了才用它
        _pos = _uniq_pos(per, pool)
        if _pos:
            return f"{_pos}的人物"
    own = _landmark_phrase_20(desc)
    if not own:
        own = (_feat_phrase(desc, cloth=False)
               or _feat_phrase(desc, cloth=True))
    # 🩸 2026-10-29（D71）：这段原来用 `_split_feats(own)` 取"这句用了哪些特征"，
    #   而它对没有「的X」结尾的描述返回空列表 ⇒ 唯一性修正从来没触发过。
    #   逻辑收进 `_disambiguate_20`，多人标签路径（`_orig_feat_20`）共用同一份。
    own = _disambiguate_20(own, desc, others_text)
    # 🩸 2026-10-27（主人：「参考视频里的人物写得太详细了」）：官方 `sd20-guide:91-95`
    # 要 **2–3 个**静态特征。`_landmark_phrase` 和 `_feat_phrase` 都只把逗号当
    # 分隔符，真实盘点却常把整条写成「留短黑发、佩戴黑框眼镜、穿藏蓝色外套、
    # 脚踩白鞋的男性」—— 全用顿号，于是整串被当成**一个分句**，原样放行，
    # 4–6 个特征全发出去。这里统一收口：超 3 个就换 `_feat_phrase`（同一把尺，
    # 它现在会按顿号拆开再封顶）。
    # 🩸 2026-11-04 深夜自己撤回：一度按 `cap=None` 整段搬，穷举 D12/D21 立刻红
    #   （官方 `sd20-guide:95`「2–3 个静态特征」，这条尺子本来就守着）。
    #   收口恢复。
    if own and len([x for x in re.split(r"、", own) if x.strip()]) > 2:
        _alt = _feat_phrase(desc, cloth=False) or _feat_phrase(desc, cloth=True)
        if _alt:
            own = _alt
    return own



def _orig_feat_20(people: list[dict] | None, i: int,
                  pool: list[dict] | None = None, cloth: bool = True) -> str:
    """原片里第 i 个人的**指认短语**（2.0 的一份）。

    🩸 2026-10-28 从 `edit_spec.py` 搬来（原本叫 `_sd20_orig_feat`，
    但 2.5 的换人句一直在借它 —— 两家的指认尺不许互借，各留一份）。

    三档（2026-10-30 主人拍板，与 `sd20_locator` 同一把尺、同一先后）：
      · **特征能唯一指认他** → `:95` 的特征短语（「短卷发男性」「东亚男性」）；
      · 特征取不到、或跟同画面别人撞成一句 → 方位在画面里**唯一**才用
        「画面中央的人物」（官方 `:153`）；
      · 两样都没有 → 空串（调用方跳过这个人）。

    出处：`sd20-guide:95`「2–3 个清晰、稳定的静态特征…确保唯一可识别性」；
    `sd2-pe:72` 把"多人未指明谁在左/右"列为关键歧义；`:153` 的写法是
    「@图片2 中的女生**位于画面左侧**」；`:164`「强方位约束」。

    🩸 先后翻过几次，每次都记在案：2026-10-24 只写方位 → 两人同标 center
    时谁也没指认（`3949eb3f` 整片没换）；10-26 17:xx 方位+特征叠加；
    10-26 22:xx 去掉方位只留特征（当时是**长特征串**塞进宾语，没换脸，
    现在 `_feat_phrase` 已封顶 2 个特征）；10-27 方位优先；
    10-30 方位降为兜底 —— 见 `sd20_locator` 里那条实测。
    """
    ppl = people or []
    per = ppl[i] if i < len(ppl) else None
    if not per or not _present(per):
        return ""
    desc = str(per.get("desc_zh") or "")
    # 🩸 2026-10-29（D71）：这句会和同画面别人撞成一句时，换成只属于他的特征
    #   （否则两个 `<主体N>` 的定义句一字不差，模型分不清谁是谁）。
    #   判定材料 = **同画面别人**的描述，不是全片。
    others = " ".join(
        re.sub(r"[\r\n\t]+", " ", str(p.get("desc_zh") or ""))
        for p in (pool if pool else ppl)
        if p and _present(p) and str(p.get("id") or "") != str(per.get("id") or ""))
    base = _feat_phrase(desc, cloth=cloth, sd20=True)
    if base:
        base = _disambiguate_20(base, desc, others, cloth=cloth)
        if not _collides_others(base, others):
            return base
    # 分母必须是**整个画面**（`pool`）：生产里 `people` 只含勾选的人，
    # 拿它数方位，每个方位天然"唯一"，两个人都在 center 时会照写「画面中央」。
    pos = _uniq_pos(per, pool if pool else ppl)
    if pos:
        return f"{pos}的人物"
    return ""


def sd20_multi_locator(per: dict | None, pool: list[dict] | None = None) -> str:
    """多人换人时，编译器在「将其中的…」这一位**实际会写出什么**；空 = 写不出。

    与 `_person_tags_20` / `edit_spec._clauses` **同一个优先级**，不另立一套：
      ① 能定义成 `<主体N>`（`_orig_feat_20` 非空，方位唯一或特征短语两档）；
      ② 否则退回 `_head_noun`（`_clauses` 最后那条「描述本身带人物中心词」）。

    🩸 2026-10-29（D70）：出片前的闸原来只问「盘点描述互不互异」，那不是一把尺。
    现场：两个人描述是「第1号人物穿的独特服装」/「第2号人物穿的独特服装」、
    方位都是 `left` —— 描述**确实**互异，闸放行；可 `_orig_feat_20` 和
    `_head_noun` 都取不出人物短语（以服装开头、没有人物中心词），编译器只能
    各写一句「将其中的人物替换为…」，两句一字不差，模型分不清在换谁。
    闸该问的是**编译器写得出来吗**，不是「盘点里两段字一样吗」。
    """
    if not _present(per):
        return ""
    pid = str((per or {}).get("id") or "")
    ppl = list(pool or [])
    if not any(str((p or {}).get("id") or "") == pid for p in ppl):
        # 盘点里找不到这个人（老调用方只传勾选的人）：退化成"就他一个"，
        # 至少把特征短语那一档算出来，别因为找不到分母就一律判空。
        ppl = [per]
    i = next(k for k, p in enumerate(ppl) if str((p or {}).get("id") or "") == pid)
    # ① 标签定义里写的就是这句（`_person_tags_20` 用的同一个函数）；
    #    多个人拿到**同一句**时，那几句定义对模型来说没有区别 —— 照样算指认不了。
    feats = [_orig_feat_20(ppl, k, pool=ppl, cloth=True) for k in range(len(ppl))]
    if feats[i]:
        return feats[i]
    # ② 已经有 ≥2 个人定义成 `<主体N>` 时，这个人取不出短语 ⇒ 编译器**整句跳过**
    #    （`_clauses` 的兜底：宁可少换这一个，也不让模型拿「人物」去猜）。
    #    跳过的人写不出重复句，给他一个只属于他的记号，别和"写出裸人物"混为一谈。
    if sum(1 for f in feats if f) >= 2:
        return f"<跳过:{pid}>"
    # ③ 没有标签体系时的宾语：`_clauses` 依次试 `_orig_feat_20(cloth=False)`、
    #    唯一方位（已含在里面）、最后退回描述本身的人物中心词。
    f = _orig_feat_20(ppl, i, pool=ppl, cloth=False)
    if f:
        return f
    return _head_noun(_inline(str((per or {}).get("desc_zh") or "")))


class _CL20(Dialect):
    """**2.0 自己的句式口径**。共用层 `edit_spec._clauses` 只调这些方法，
    里面不再出现 `if edit_task` / `if 某型号`。

    🩸 2026-10-28：原来这些差异是 `_clauses` 里 13 处 `if edit_task:`
    —— 而 `edit_task` 在 2.0 永远 False、2.5 永远 True（`model_specs` 写死），
    等于型号开关伪装成任务开关。改一句 2.5 的句式，2.0 的产出也跟着变。
    """

    def subj(self, obj: str) -> str:
        # 官方 `sd2-pe:126`「严格编辑 @视频1，**将其中的**香水替换为…」
        return f"将其中的{obj}"

    def orig_feat(self, people: list[dict], i: int,
                  pool: list[dict] | None = None, cloth: bool = True) -> str:
        return _orig_feat_20(people, i, pool=pool, cloth=cloth)

    def feat_fallback(self, src: str) -> str:
        """`_head_noun` 之前先试封顶特征短语（产品线封顶 2）。
        见 `base.Dialect.feat_fallback` 的出处说明。"""
        return _feat_phrase(src, cloth=False, sd20=True)

    def wardrobe_verb(self) -> str:
        return "换成"

    def person_duty(self, *, pic: str, rtag: str, in_wardrobe: bool) -> str:
        """换人句后面追加的职责分句。**只有 2.0 有**：2.5 把它放进
        【目标素材职责】逐张说，不在编辑目标句里重复。

        出处与历史（2026-10-25 ~ 10-27，逐条踩出来的）：
          · 一个换的人只有一张图（台账 D48）⇒ 两项职责都指这张图。
            官方把「妆造」定义在第二张（全身照）上（`sd2-pe:139`），没有第二张
            就等于没写妆造，模型只换脸、衣服照原片。
          · 2026-10-26 曾把两个分句合成「面部特征与妆造均参考@图片1」—— **撤回**：
            `:121` 说的是描述要简洁，不是让改写 `:317` 的职责句；「与…均参考」
            这个动词短语官方原文没有。证据（同一素材 494b1c28）：合成句那次衣服
            换全了、脸只挪一半（原片主演 SFace 0.33 → 成片 0.55）；官方两句那次
            p90 0.617 / 达标帧 0.77。
          · 参考图侧有标签时写「参考@图片1的面部特征和妆造」（`sd20-guide:59-65`
            组合任务句式：参考<图片N>的[参考维度]），标签与图号的绑定由前一句
            定义句承担 —— 不再写成「参考@图片1中<主体1>…」，那是套娃
            （2026-11-04 深夜改，见函数末注释）。
          · 2026-10-27（人工审读真实组合）：勾了「换人 + 换装」时，
            「妆造参考@图片1中的人物」与「…的服装换成@图片2中的服装」**同句
            语义冲突**（官方 `sd20-guide:121` 点名）⇒ 这个人在换装名单里时，妆造句不写。
        """
        # 🩸🩸 2026-10-30（主人：「是提示词排顺序错误，还是某个关键词导致的用了
        #   别的模型关键词」）：**顺序错了**。官方 `guide.md:59-65`「组合任务」的
        #   推荐句式是
        #       「参考<图片/视频N>的[参考维度]，严格编辑<视频X>，[具体编辑内容]」
        #   ⇒ **参考分句必须在「严格编辑」之前**。
        #   以前这句是接在替换句尾巴上的（「…替换为<主体1>；<主体1>的面部特征
        #   参考@图片1，妆造参考@图片1」），排在编辑动作**之后**，顺序反了。
        #   现在独立成句、以「参考@图…」开头 —— 编译器顶层会把这类分句提到
        #   「严格编辑」前面（`_compile` 里的 `_lead`），而主体定义句仍排在
        #   它们之前（官方 `:110` 先定义再描述）。
        #   `参考维度` 取官方 `:139`/`:317` 的原词「面部特征」「妆造」，
        #   没有新造词。
        # 🩸🩸 2026-11-04 晚：**恢复本句**（当天上午清理时停用过，判断过头了）。
        #
        #   上午的理由是「`sd2-pe:139` 属路径 B 三段论，编辑任务走路径 A」。
        #   只对了一半：原文那个**两张图分工**（大头照+全身照）确实不适用，
        #   但「参考分句」本身不是路径 B 的块标题 —— 它是路径 A 公式里明写的槽：
        #   `SKILL.md:121`「[任务句式主体]，**[主体与素材绑定]**，[场景与简短动作]，
        #   [风格与约束包]」。删掉它 = 把公式第二个槽删了。
        #   本函数就是官方 `prompt-guide.md:317`（常见问题·**人脸参考不准确**）的
        #   解法原文：「<主体1> 的面部特征参考图片1（大头照），妆造参考图片2
        #   （全身照）」—— 我们只有一张图，两项职责都指这张。
        #
        #   真机证据（2026-11-04 本地 SFace 复算，零费用）：
        #     `de591f35` 同素材同参考图的历史 10 条成片 ——
        #       · 唯一带「锁定图中人物的脸」那版（H3 `c8455a93`）：person2 p90 0.611
        #       · 唯一带【目标素材职责】那版（2.5 `dad130d5/004b86ac`）：两人都换上了
        #       · **2.0 唯一那版（没有本句）**：person 0.071 / person2 0.0，
        #         连衣服都没动（成片把锅的金属把手抹掉了）
        #   三家能换上的版本里，都有一句「这张图供什么」；2.0 是唯一没有的。
        #
        #   官方顺序：`sd20-guide:59-65` 组合任务要求参考分句排在「严格编辑」之前。
        #   本句以「参考@图…」开头，编译器顶层 `_lead` 会把它提到前面。
        # 🩸 2026-11-04 深夜（主人：「怎么有点怪怪的？」）：**有标签时不能再套图号**。
        #   旧写法 `参考@图片1中<主体1>的面部特征和妆造`，而 `<主体1>` 刚被定义成
        #   「@图片1中…的人」⇒ 读起来是「@图片1中（@图片1中那个人）」，套娃，
        #   违反官方 `:121`「描述尽量简洁，避免冗余」。
        #   官方组合任务句式（`:59-65`）是「**参考<图片N>的[参考维度]**」，
        #   参考维度就是 `:317` 的原词「面部特征」「妆造」。
        # 🩸✅ 2026-11-04 20:58 **真机验证通过**（`de591f35` / `ef232fc6`，343 字，
        #   2 人全换，主人确认「通了」）—— **就是下面这个写法**，别再动：
        #       `参考@图片1的面部特征和妆造，参考@图片2的面部特征和妆造`
        #   🩸 记一笔：当晚我一度觉得「无主语」把它改成
        #   `<主体1>的面部特征和妆造参考@图片1`（353 字）—— **未出片、未验证**，
        #   已回滚。要再改这条，必须单独出片验，不许拿"语法更顺"当理由直接换。
        #   没标签时保持 2026-10-26 真机跑过的旧写法，不动。
        # 🩸🩸 2026-11-05 实测定案：**回滚到无主语版**。
        #   `20e6b5d0`（7.583s 预览）用「参考@图片1中人物的面部特征和妆造」出片：
        #   人换上了，但脸既不像原片也不像定妆照 —— 模型把「图片1中的人物」
        #   当成一个**泛指身份**（"图里那种人"），不是"这张脸的像素"。
        #   官方组合任务句式（`:59-65`）是「**参考<图片N>的[参考维度]**」，
        #   参考维度取 `:317` 的「面部特征」「妆造」—— 原句里没有"中人物的"。
        #   而且这一版从改出来到 20e6b5d0 之前**一次都没出过片**（见上面的记录），
        #   唯一通过过的就是「参考@图片1的面部特征和妆造」（`ef232fc6`，343 字）。
        _tail = "" if in_wardrobe else "和妆造"
        if rtag:
            return f"{rtag}的面部特征{_tail}参考{pic}"
        return f"参考{pic}的面部特征{_tail}"

    def keep_others(self, names: list[str]) -> str:
        # 🧹 2026-11-04 清理：原来引 **LAS `las_cn.md:385`**（`general` 模板）——
        #   LAS 是「视频编辑增强版算子」，不是 Seedance 原生提示词。
        #   但**这句话本身官方是支持的**，换成 2.0 自己的出处：
        #   `prompt-guide.md:41`「删除元素：点明需要删除的元素，**对于保持不变的
        #   元素，在提示词中加以强调，表现更佳**」。
        #   ⇒ 句子保留，出处改到 Seedance 2.0 官方指南。
        return _others_unchanged(names)

    def wardrobe_subject(self, ctx: dict) -> tuple[str, bool]:
        """换装句宾语 = 「谁的衣服」。2.0 有 `<主体N>` 标签体系，优先用标签。

        🩸 2026-10-25：这一句和换人句说的是同一个人，前面已给他绑 `<主体N>`，
        再喊一遍整段外观描述就违反官方 `sd20-guide:119`「持续使用同一标签」；
        而且那段描述写的是**旧衣服**，当宾语会被当成要保住的东西。
        🩸 2026-10-26 18:xx：只有一个标签体系 —— 原片侧 `<主体N>`。
        🩸 2026-10-28（当前产出实测）：**同一个人被叫成两个名字** ——
          前面刚写「将其中的<主体3>替换为<主体1>」，替换后画面里那个人就是
          `<主体1>`，可换装句仍写「<主体3>的服装」用的是替换前的身份。
          ⇒ 有图片侧标签时连前缀一起换掉（返回 `bare=True`）。
        🩸 2026-10-28：三档兜底一直没生效 —— 查的是 `people`（这次**勾选换人**
          的名单），换装名单和它是两张表。「只换装不换人」时 `people` 里没有
          换装目标 ⇒ 永远落到 `_head_noun`，两个男人拼出两句一模一样的
          「将其中的男性的服装换成…」（零成本矩阵 7/7 素材复现）。
          ⇒ 在**整个画面**里找这个人。
        """
        pid = ctx["pid"]
        people = ctx.get("people") or []
        frame_people = ctx.get("frame_people")
        who = ctx.get("who") or ""
        orig_tags = ctx.get("orig_tags") or {}
        ref_tag = ctx.get("ref_tag")
        # 🩸 2026-11-05 拆槽位：类别词由调用方给（默认「服装」）。
        #   换发型走**同一条模板**，只把 `<原特征>` 换成「发型」
        #   （`sd20-guide:39` + `:95` 把「发型」列为可选核心特征）。
        _noun = str(ctx.get("noun") or "服装")

        def _tag_of(i: int, per: dict | None) -> str:
            _pid = str((per or {}).get("id") or "")
            return orig_tags.get(_pid) or orig_tags.get(i, "")

        def _rtag_of(i: int) -> str:
            if isinstance(ref_tag, dict):
                return str(ref_tag.get(i) or "")
            return ref_tag or ""

        _wt = ""
        _img_tag = ""
        for _i, _per in enumerate(people):
            if str((_per or {}).get("id") or "") == str(pid):
                _wt = _tag_of(_i, _per)
                _img_tag = _rtag_of(_i)
                break
        if _img_tag:
            return f"{_img_tag}的{_noun}", True
        if _wt:
            return f"{_wt}的{_noun}", False
        _pool = frame_people or people
        _per_i = next((k for k, x in enumerate(_pool)
                       if str((x or {}).get("id") or "") == str(pid)), None)
        _loc = (_orig_feat_20(_pool, _per_i, pool=_pool, cloth=False)
                if _per_i is not None else "")
        if _loc:
            return f"{_loc}的{_noun}", False
        _hn = _head_noun(who) if who else ""
        return (f"{_hn}的{_noun}" if _hn else _noun), False

    def style_ref(self, pic: str) -> str:
        # 官方 `sd20-guide:59-65` 组合任务：「参考<素材N>的[参考维度]，严格编辑…」
        # `sd20-guide:56` 警告编辑任务勿用「参考<视频N>」—— 只有组合任务这个固定句式
        # 里才允许「参考」字样，且位置在前（拼接由 `_volc_20` 前置）。
        return (f"参考{pic}的色调、光影和质感，"
                "不采用其中的主体、构图和场景内容")

    def style_video(self) -> str:
        # 官方 `:26` 的参考维度原句「参考<视频N>中的<动作/运镜/风格/音效>」。
        return ("参考@视频2的色调、光影和质感，"
                "不采用其中的主体、构图、场景内容、运镜和节奏")

    def style_word_when_ref(self) -> bool:
        # 2.0 **叠加**：有风格图时恰恰最需要风格词（`sd20-guide:357-359`）。
        return True

    def style_word(self, word: str) -> str:
        # 官方 `sd20-guide:713`「**整体风格为** 3D 赛博朋克科幻动画风格」——
        # 2.0 把它当**风格约束词**，不是「把某物改成某物」的编辑动作。
        return f"整体风格为{word}"


# 🗑️ 2026-11-04 深夜删除 `_REF_GROUP_ORDER = (2, 3, 4, 0, 1)`。
#   那个常量假设 `desc_zh` 永远按 `vision_plan._DESC_PROMPT` 的 ①②③④⑤
#   分五组，可视觉模型实际输出**组数不固定**：`de591f35` 的图片1 把
#   ①面部和②气质合成一组 ⇒ 下标 2 落到「服装」而不是「发型」，
#   于是「深棕黑色蓬松大波浪长卷发」整组被跳过。
#   按下标取组 = 在数据形状不稳时取错维度。现改成「按原顺序、每组 1 条、轮转取满
#   3 条」，见 `_ref_feat_20`。
#   （当天一度改成"整段搬完整描述"，穷举 D12/D21 立刻红 —— 官方 `:95` 的
#    「2–3 个」是硬线，已撤回。）


def _ref_feat_20(desc: str, others_text: str = "") -> str:
    """参考图里那个人的「2–3 个静态特征 + 人」短语（官方 `sd20-guide:95`）。

    🩸 2026-10-26（主人：「我刚才一直说你提示词有问题」）：参考图里的人一直
    **没有被定义成主体**，提示词里只有一句「替换为@图片1中的人物」——
    把"图里哪个人"甩给模型自己找，而前半句已经把原片三个人描述完了。
    官方 `:95` 给的写法是 `将<图片N>中的[主体核心特征]定义为<主体N>`，
    `:107` 要求之后**全程用同一标签**。这里把参考图的外观描述
    （`subject_desc.json` 的 `desc_zh`）裁成官方要的特征短语。

    官方原文只有三条，全部照办，不再自己加规则：
      · `guide.md:93`「使用 **2–3 个**清晰、稳定的静态特征」；
      · 同句「（如**服饰、发型**、外观、类别）」→ 取特征时先拿这两类
        （真实描述的头一组全是五官，两份参考图的五官句几乎逐字相同，
        拿它当定义不满足下一句）；
      · 同句「**确保唯一可识别性**」+ `:107`「避免指代混乱」
        → **另一张参考图也有的分句不进定义**。

    🩸🩸 2026-11-04（`de591f35` 真机：2 人全换、两张脸都没换）：
      那单发出去的两句是「将其中的**黑色长发**、外穿黑底带白色文字的人物…」
      /「将其中的**黑色长发**、手臂带有纹身的人物…」——都以「黑色长发」开头，
      定义句再各带一遍，模型分不出谁是 `<主体1>`。`others_text` 就是为了剔掉
      这类撞车分句而加的。
    """
    raw = re.sub(r"[\r\n\t]+", " ", (desc or "")).strip().rstrip("。．.")
    # 🩸 引号在 2.0 提示词里是**台词/文字**的句法（`sd20-guide:298` 台词用 `{}`；
    # 同一份指南要求「保持无字幕，避免生成任何文字或字幕」）。服饰上的印字
    # “HAIRVERS”只是外观特征，带上引号会被读成"要生成这段文字"——
    # `ruler_sd20` 的 R13 当场把它当台词报了黄。只去掉引号，不动字。
    raw = re.sub(r"[“”\"「」『』]", "", raw)
    if not raw:
        return ""
    others = others_text or ""
    # ① 按**我们自己的描述契约**分组（组间 `；`），**每组最多贡献 1 条**，
    #    取满 3 条即停。官方 `sd20-guide:95` 的两条硬要求都照办：
    #      · 「使用 **2–3 个**清晰、稳定的静态特征」——封顶 3；
    #      · 「（如**服饰、发型**、外观、类别）」——按组轮转，天然跨维度，
    #        不会像以前那样 3 条槽位全被服装占满。
    #    🩸 2026-11-04 深夜（主人：「那个长长的描述真的 2.0 导图里面的资料吗？」）：
    #    **不是**。当天一度改成"整段搬"，穷举 D12/描述形态 与 D21/真实盘点形状
    #    立刻红 —— 那条尺子守的就是官方「2–3 个」。已撤回，只留下真 bug 的修法。
    #
    #    🩸 原来的真 bug：按 `_REF_GROUP_ORDER = (2,3,4,0,1)` **按下标**挑组，
    #    而视觉模型输出的组数不固定（这张图把 ①面部②气质 合成了一组）⇒
    #    下标 2 落到「服装」而不是「发型」，**发型整组被跳过**。
    #    现在不按任何下标挑，按描述原顺序每组取 1 条 —— 组数怎么变都不会漏维度。
    groups = [g.strip(" ，,") for g in re.split(r"[；;]", raw) if g.strip(" ，,")]
    # 候选按组摊开，组内顺序不变；先剔「另一张图也有的分句」（官方 `:95`）。
    cand: list[list[str]] = []
    for g in groups:
        _c = []
        for x in re.split(r"[，,]", g):
            x = x.strip()
            if x and x not in others and x not in _c:
                _c.append(x)
        if _c:
            cand.append(_c)
    # 轮转取：第 1 轮每组取 1 条，不够 3 条再走第 2 轮 —— 这样既跨维度
    # （官方 `:95` 举例的服饰/发型/外观都能拿到），描述没分组时也照样取满 3 条。
    feats: list[str] = []
    rnd = 0
    while len(feats) < 3:
        _added = False
        for _c in cand:
            if rnd < len(_c):
                _added = True
                if _c[rnd] not in feats:
                    feats.append(_c[rnd])
                if len(feats) >= 3:
                    break
        if not _added:
            break
        rnd += 1
    if not feats:
        # 两张图一模一样时没有可区分的特征：退回原文第一句，不编造
        feats = [x.strip() for x in re.split(r"[，,]", groups[0]) if x.strip()][:1]
    if not feats:
        return ""
    if not _PERSON_HEAD.search(feats[-1]):
        feats[-1] = feats[-1] + "的人"
    return "、".join(feats)


def _ref_side_tags_20(idx: dict[str, int], channel: str,
                      people: list[dict] | None,
                      looks: dict | None) -> tuple[list[str], dict[int, str]]:
    """多主体换人：把**参考图里**的人各自定义成 `<主体N>`（官方 `sd20-guide:95/:107`）。

    🩸🩸 2026-11-04（`de591f35` 真机，主人：「你这个真的是有鸡毛用，什么也没变化」）：
      2 人全换，发出去的提示词是
        「严格编辑@视频1，视频全程将其中的黑色长发、外穿黑底带白色文字的人物
          替换为@图片1中的人物；将其中的黑色长发、手臂带有纹身的人物
          替换为@图片2中的人物。动作和运镜不变。…」
      ① 两条**源**宾语都以「黑色长发」开头（两张参考图也都有这一条）；
      ② **目标**侧全是「@图片N中的人物」—— 哪张图配哪个人，模型只能猜。
      成片两张脸都是原片演员，SFace 17% / 0%。
      官方三条都在说这件事：`:95`「将<图片N>中的[2–3 个静态特征]定义为<主体N>」、
      `:109`「当视频中存在多个主体时，需要**分别定义**，并使用标签区分」、
      `:119`「每次提到主体时，都应使用同一标签」。⇒ 目标宾语写 `<主体N>`。

    **只在 ≥2 个换人目标、且每张参考图都有外观描述时**才发：
      · 单人换人：官方 `20 单人` 的标准示例就写「@图片1中的人物」，多一句定义是添乱
        （也是 2026-10-30 停用定义句那条决定的适用面，本函数不碰它）；
      · 只要有一张描述缺失 → 整组不发：发半组标签等于给模型留一句悬空引用
        （官方 `:88` 定义主体的目的是「精准引用素材中的特定对象」）。
    编号从 `<主体1>` 起：原片侧标签 2026-10-30 起停用，不会与本表抢号；
    真要恢复原片侧标签，按旧的「图片侧先占号、原片侧接着编」规则改这里。

    返回 `(定义句列表, {people 下标: "<主体N>"})`；发不出时返回 `([], {})`。
    """
    looks = looks or {}
    ppl = people or []
    if not ppl or not looks:
        return [], {}
    targets: list[tuple[int, str]] = []
    for i, slot in enumerate(PERSON_SLOTS):
        if slot not in idx:
            continue
        # 下标对齐规则与 `edit_spec._clauses` 一致：`people[i]` 配 `PERSON_SLOTS[i]`
        if i >= len(ppl) or ppl[i] is None or not _present(ppl[i]):
            continue
        if not str(((looks.get(slot) or {}).get("zh") or "")).strip():
            return [], {}
        targets.append((i, slot))
    # 🩸🩸 2026-11-05 撤回（当天真机反证）：
    #   上午曾把门槛从「< 2」放宽到「0」，让**单人换人也发 `<主体N>` 定义句**。
    #   真机任务 `60f82aab` 出片后主人报「一点也没有改变」—— SFace 对成片
    #   实测 best 0.357 / p90 0.255 / **share 0.0**（一帧都没达到同人阈值 0.363）。
    #   这与 `_person_tags_20` 里 **2026-10-30 的三次真机实测**完全一致：
    #   定义句会把「这个人有哪些特征」喂给模型，替换时模型反而把这些特征**保留**
    #   在原片上（衣服换、脸不换）。当时的结论就是「一换一不发任何 `<主体N>`」。
    #   上午改动的依据只是矩阵的代码推断（18/87 格），没有真机证据 —— 撤回。
    #   恢复门槛后单人回到官方 `:126` 的「@图片N中的人物」写法。
    #   ⚠️ 2.0 换人「换不上」的根因**未解决**（无标签版历史 share 也仅 4–9%），
    #      另行排查；这一条只保证不再引入已被真机否定的写法。
    if len(targets) < 2:
        return [], {}
    texts = {i: str((looks.get(slot) or {}).get("zh") or "") for i, slot in targets}
    defs: list[str] = []
    tags: dict[int, str] = {}
    for n, (i, slot) in enumerate(targets, start=1):
        # 另一张参考图的描述：共有的分句不进定义（见 `_ref_feat_20` 的 11-04 注释）
        others = " ".join(t for k, t in texts.items() if k != i)
        feat = _ref_feat_20(texts[i], others)
        if not feat:
            return [], {}
        tag = f"<主体{n}>"
        tags[i] = tag
        defs.append(f"将{_pic(channel, idx[slot])}中{feat}定义为{tag}")
    return defs, tags


def _person_tags_20(c: dict, idx: dict[str, int], channel: str,
                      people: list[dict] | None = None,
                      frame_people: list[dict] | None = None,
                      ref_desc: str = "",
                      subject_looks: dict | None = None
                      ) -> tuple[list[str], dict[str, str], str]:
    """2.0 多人换人：把画面里的每个人都绑成一个 `<主体N>`。

    返回 `(定义句列表, {盘点id: <主体N>}, 参考图侧标签)`。前两项都指**原片侧**
    那个人；第三项（`ref_tag`）指**参考图里那个人**，没有描述时为 `""`。
    **按在场人数分档**（`_multi` 为假时返回空，单人路径逐字不动）：
      · 在场 < 2 人 → 不定义。单人没有指代歧义，官方 `:117` 的简单场景。
      · 在场 ≥ 2 人 → **画面里每个能指认的人都定义**（官方 `:107` 分别定义），
        参考图侧只在 ≥2 个换人目标时才另发标签（见函数内 18:xx 注释）。

    出处（全部 2.0 官方，`D:/tmp/official/sd20/guide.md`）：
      · `:88`「一张图片中往往存在多个主体，为了精准引用素材中的特定对象，
        **必须进行明确的主体定义**」；
      · `:107-110`「当视频中存在多个主体时，需要**分别定义**，并使用标签区分…
        后续描述中需持续使用对应标签，避免指代混乱」；
      · `:95` 定义要带 2–3 个清晰稳定的静态特征（见 `_orig_feat_20`）；
      · `:110` 的官方示例本身就是**先定义再描述**：
        「将视频1中的高个子男人定义为警察，将另一个矮个子男人定义为小偷。场景…」
        —— 所以绑定句放在 `严格编辑@视频1，` 之前是对的。

    编号：原片侧从 `<主体1>` 起（2026-10-30 起停用）；参考图侧由
    `_ref_side_tags_20` 发，编号也从 `<主体1>` 起（见该函数 11-04 注释）。
    """
    # 🩸🩸 2026-10-30 停用（主人：「是不是主体问题？有没有必要说主体」）：
    #   **一换一不发任何 `<主体N>` 定义**。
    #   依据：
    #     · 官方「编辑视频」章节（`sd20-guide:31-43`）的三条推荐句式**一条主体定义
    #       都没有**，只有「严格编辑<视频N>，将其中的<原特征>修改为<新特征>」；
    #     · 定义主体在 `sd20-guide:88-124`「进阶公式」，示例是**生成**任务
    #       （「高个子男人定义为警察，矮个子定义为小偷，两人在人群里追」）——
    #       那是"同时调度两个人演戏"，我们做的是"把 A 换成 B"，是两回事；
    #     · 定义句「将@视频1中短卷发男性定义为<主体2>」等于额外告诉模型
    #       「这个人有短卷发」，替换时模型会顺手把这个特征**保留**下来 ——
    #       正好抵消换脸。2026-10-26 三次实测都是这个现象（衣服换、脸不换）。
    #   ⇒ 宾语退回官方 `:126` 的图内对象「@图片N中的人物」，指认靠方位/发型
    #     短语直接写进「将其中的…」那位（`sd20_locator` 那一套仍在，是闸在用）。
    #   **只停用原片侧** —— 参考图侧照旧由下面 `_ref_side_tags_20` 发（见 11-04 注释）。
    #   保留整个函数体：以后要恢复标签体系，注释里有全部历史依据。
    _ref_defs, _ref_tags = _ref_side_tags_20(idx, channel, people, subject_looks)
    if not _ref_defs:
        return [], {}, ""
    return _ref_defs, {}, _ref_tags

    ppl = people or []
    # 🩸 「在场几个人」必须按**整个画面**数。生产形状（`video_edit._span_people`）
    # 里 `people` 只含这一刀勾选的人：只换两个人中的一个时它长度为 1，
    # 拿它数就永远进不了"多人"分支，标签和原片侧定义全都不发 ——
    # 2026-10-25 `probe_prod_shape.py` 实测拼出来仍是
    # 「将其中的画面中央的人物替换为@图片1中的人物」，D24/D25 全成了死代码。
    frame = frame_people if frame_people else ppl
    present = [i for i, p in enumerate(frame) if p and _present(p)]
    # 盘点 id → 勾选名单下标（两套下标不能混用）
    byid = {str((p or {}).get("id") or ""): i for i, p in enumerate(ppl) if p}
    targets: list[tuple[int, str]] = []
    for i, slot in enumerate(PERSON_SLOTS):
        if slot not in idx:
            continue
        per = ppl[i] if i < len(ppl) else None
        if per is not None and not _present(per):
            continue
        targets.append((i, slot))
    if not targets:
        return [], {}, ""
    # 🩸 2026-10-26 21:xx（主人：「还是换不上人脸啊！衣服是换了 —— 是否只换一个人的
    # 时候不需要主体？」）：**单目标不发任何 `<主体N>`。**
    # 依据是三条实测叠在一起：
    #   · 2026-10-24 三版 2.0：宾语里写了原片外观（衣服/道具）→ **衣服换了、脸没换**；
    #   · 2026-10-26 18:21：`<主体2>` 的定义句写满"藏蓝色带白色字母印花的外套"→
    #     成片 p90 0.297，同样衣服换、脸没换；
    #   · 2026-10-26 21:xx：参考图侧加了定义（`<主体1>`）**仍然是衣服换、脸没换**。
    # 结论：一换一的时候，那四个 `<主体N>` 只是给模型多了三段"要照着改的衣服描述"，
    # 官方 `:95` 要的"唯一可识别性"用**方位 + 发型/配饰**就够了（`:153`）。
    # 多目标仍然走标签（`<主体N>` 是 `:107` 分开定义的唯一办法）。
    #
    # 🩸 2026-10-26 22:xx **上面那条结论收回一半**（按实测重排了"描述长度"这个变量）：
    # 同一素材 `494b1c28`、同一张参考图 `12a547` 的四条真机——
    #   · 15:46 / 16:20「画面中央的留短黑发」+ **标签宾语**   → 人眼核：**换上了**
    #   · 16:42「留短黑发、佩戴黑框眼镜的男性」+ **标签宾语** → 人眼核：**换上了**
    #   · 19:43 一次定义 **4 个**主体、每条都带 20 字服装串 → 仍是原片演员
    #   · 20:13 / 20:20 把长特征串**直接塞进宾语** → 没换
    # ⇒ 真正致死的不是"有标签"，是**标签后面跟了多长的定义**。标签本身是短宾语
    #   （`<主体1>` 四个字），正是主人说的「越简单越好」。
    # ⇒ 一换一改为：**只给被换的那个人发一个标签**，宾语用它。
    #   定义句**不写方位**（主人：「就算你又来画面中间左边右边咯」—— 方位是盘点
    #   给的，说错就指错人），只用 `:95` 的静态特征；特征跟同画面里别人撞车时
    #   才把服装拿回来当唯一区分。
    if len(targets) == 1:
        # 🩸 **单人画面逐字不动**：`052dcbf0` 真机验过（0–11.2s 换人成功），
        # 那版就是「将其中的…人物替换为@图片1中的人物」、一个标签都不发。
        # 画面里只有一个人时没有指代歧义（官方 `:117` 的简单场景），
        # 给他写定义纯属多余。
        if len(present) < 2:
            return [], {}, ""
        ti = targets[0][0]
        per = ppl[ti] if ti < len(ppl) else None
        if per is None or not _present(per):
            return [], {}, ""
        # 认人只走 `sd20_locator` 一条路（闸也调它）：标志性特征优先，
        # 挑不出来才退回发型/配饰，再不行才带服装。
        own = sd20_locator(per, frame)
        if not own:
            return [], {}, ""
        pid = str(per.get("id") or "")
        # 🩸 2026-10-27：按官方 `20 双人只换一个` 标准示例，画面 ≥2 人时
        # **图片侧也定义**，编号在前（图片 1，视频 2）：
        #   「将@图片1中的人物定义为<主体1>，将@视频1中体型偏胖的男子定义为<主体2>。
        #     严格编辑@视频1，将其中的<主体2>替换为<主体1>；
        #     <主体1>的面部特征参考@图片1，妆造参考@图片1」
        # 单人画面在上面 `len(present) < 2` 已早退，不受影响（官方 `20 单人` 无标签）。
        ref_tags = {ti: "<主体1>"}
        defs = [
            f"将{_pic(channel, idx[targets[0][1]])}中的人物定义为<主体1>",
            f"将{_vid(channel)}中{own}定义为<主体2>",
        ]
        return defs, ({pid: "<主体2>"} if pid else {}), ref_tags
    # 🩸 2026-10-26 18:xx（主人：「多主体也要搞定」）：**判据从"几个换人目标"
    # 改成"画面里有几个人"**。
    #
    # 官方原文（`seedance-20-guide.md` §1 定义主体）：
    #   · `:88`「实际参考的素材，**一张图片中往往存在多个主体**，为了精准引用
    #     素材中的特定对象，**必须进行明确的主体定义**」；
    #   · `:107`「**当视频中存在多个主体时，需要分别定义，并使用标签区分**。
    #     标签应具备唯一性与稳定性，后续描述中需持续使用对应标签，避免指代混乱」；
    #   · `:110` 的示例就是**先分别定义、再描述**：「将视频1中的高个子男人定义为
    #     警察，将另一个矮个子男人定义为小偷。场景…」。
    # `sd2-pe:15` 同一件事：「多主体场景或需复用 → 先定义 `将 @图片N 中的
    # [2-3 个稳定静态特征] 定义为 <主体N>`，之后全程使用同一标签 `<主体N>` 指代」。
    #
    # ⇒ 「画面里几个人」才是官方说的多主体场景。以前按"几个换人目标"判，
    # 只换一个人的三人画面被当成简单场景（`:117`），一个标签都不发 ——
    # 模型要在三张脸里凭一句特征短语找目标，这就是 `sd2-pe:72` 说的"关键歧义"。
    #
    # 参考图侧仍只在 **≥2 个换人目标**时才发标签：官方 `:15` 的定义句要求
    # 「2–3 个稳定静态特征」，而用户上传的换人图我们**没有盘点结果**（盘点只跑
    # 参考视频），写不出特征就不该硬造一个定义句。参考侧一律走官方 `:14/:17`
    # 的**内联绑定**「`@图片N` + 名词隔断」——`@图片1中的人物`，这也是本工程
    # 唯一一次真机换人成功（`052dcbf0`）里用的写法。
    #
    # 🩸 所以定义句**只发原片侧**（盘点给了特征的人才定义）。以前参考侧写
    # 「将@图片1中的人物定义为<主体1>」——零静态特征，违反 `:15`/`:95`，
    # `ruler_sd20 --current` 的 R06 一直黄着。宁可不用标签，也不发一句假定义。
    # 多主体的判定：画面里 ≥2 人（官方 `:107`），或者要换的 ≥2 个人
    # （没有盘点时按目标数判 —— 两个目标本身就是两个主体）。
    if len(present) < 2 and len(targets) < 2:
        return [], {}, ""
    # 原片侧：画面里**每一个**能指认的人都给标签（官方 `:107` 分别定义），
    # 不只是被换的那几个 —— 只定义目标时，模型仍要在没被点名的几张脸里找他。
    # 指认短语为空（盘点没给描述也没给方位）的人跳过：定义不出来的不硬写。
    # `present` 为空（没有盘点）时退回勾选名单：两个目标自己就是两个人。
    # 先把原片侧每个人能指认的特征收齐（官方 `:95` 的 2–3 个静态特征），
    # 能不能发标签取决于下面 `orig`；编号要等参考图侧定下来再发。
    items: list[tuple[str, str]] = []
    for j in (present or [i for i, _ in targets]):
        feat = _orig_feat_20(frame, j, pool=frame)
        if not feat:
            continue
        # 🩸 按**盘点 id**回填（不是下标）：`frame` 比勾选名单长，两套下标会错位；
        # 而且没被换的那位也可能说话（`:605` 逐句点名），他同样要用同一个标签
        # （官方 `:119`「每次提到主体时，都应使用同一标签」）—— 按 id 才查得到。
        items.append((feat, str((frame[j] or {}).get("id") or "")))
    # 🩸 2026-10-26 21:xx：**参考图侧的 `<主体1>` 定义已撤掉**（`ref_tag` 恒为
    # 空串）。加它的那次真机（21:0x）**还是衣服换、脸不换**，而只换一个人的场景
    # 在此之上已经整段不发了（见上面 `len(targets) == 1` 的早退）——
    # 留着就是一条永远不会执行的假分支。
    # `ref_desc` 参数与 `_ref_feat` 保留：多目标真要按人定义参考图时用得上，
    # 但**必须先有实测证明有用**再接线（现在没有任何一次真机验过）。
    ref_tags: dict[int, str] = {}
    if not items:
        return [], {}, ref_tags
    defs: list[str] = []
    orig: dict[str, str] = {}
    # 🩸 2026-10-27：按**我们手里的 2.0 官方 12 条标准示例**补回图片侧主体定义。
    # 官方 `20 双人只换一个` / `20 双人全换` 两条都是这个形状：
    #   「将@图片1中的人物定义为<主体1>，将@视频1中体型偏胖的男子定义为<主体2>。
    #     严格编辑@视频1，将其中的<主体2>替换为<主体1>；<主体1>的面部特征参考@图片1…」
    # ⇒ ① 图片侧也要定义；② 替换宾语是 `<主体N>`；③ 「面部特征参考」的主语是标签。
    # 编号照官方：**图片侧先占号**（1..m），原片侧接着编（m+1..）。
    # 单人画面在上面已经早退，永远走不到这里（官方 `20 单人` 本来就不发标签）。
    for i, slot in enumerate(PERSON_SLOTS):
        if slot not in idx:
            continue
        per = people[i] if i < len(people) else None
        if per is not None and not _present(per):
            continue
        # 🩸 2026-10-27：原片那位**认不出来**（`_orig_feat_20` 空，典型是
        # 盘点给了「被衣物遮挡的人物」/「多名…民众」）时，替换句会被
        # `_clauses` 跳过 —— 那这里也**不许发参考图侧标签**，否则留下一句
        # 悬空定义：`<主体N>` 定义了却从没被引用。官方 `:88` 定义主体的
        # 目的是「精准引用素材中的特定对象」，只定义不引用等于平白多告诉
        # 模型「把这张图里的人塞进来」，正是凭空多一张脸的来源。
        if per is not None:
            _fi = next((k for k, f in enumerate(frame)
                        if f and str(f.get("id") or "") == str(per.get("id") or "")),
                       None)
            if _fi is not None and not _orig_feat_20(frame, _fi, pool=frame):
                continue
        tag = f"<主体{len(ref_tags) + 1}>"
        ref_tags[i] = tag
        defs.append(f"将{_pic(channel, idx[slot])}中的人物定义为{tag}")
    for k, (feat, pid) in enumerate(items, start=len(ref_tags) + 1):
        tag = f"<主体{k}>"
        defs.append(f"将{_vid(channel)}中{feat}定义为{tag}")
        if pid:
            orig[pid] = tag
    return defs, orig, ref_tags


#: 2.0 的方言实例（`volc20.py` 登记进 adapter）
CL20 = _CL20()


def _shot_plan(cuts: list[float]) -> str:
    """2.0 编辑任务的「这一段有几个镜头」——**不写**。

    🩸 2026-10-26 L3：原来住在 `edit_spec.shot_plan_sentence`，跟 2.5 / H3 挤同一个
    `if channel == "volc": … else: …`。三家口径完全不同，各写各的。

    🩸 2.0 编辑任务不写镜头结构句（2026-10-23 回源更正）。
    「镜头 1 / 镜头 2 / 镜头 3」这个写法出自《Seedance 2.0 提示词指南》
    §「进阶公式 · 使用分镜时序」—— 那是**生成任务**（参考生视频）的章节。
    编辑任务在同一份指南里另有独立公式（:31-40）：
        「严格编辑<视频N>，将其中的<原特征>修改为<新特征>」
    并且开头就写明「**未提及的部分，默认保持不变**」（:33）。
    ⇒ 切点由 @视频N 自己带；多写一段"分成 7 个分镜"等于把"保持原镜头"
       改写成"重新排 7 个镜头"，正是把默认行为换成新指令。
    """
    return ""


# 2.0 官方强制兜底包 —— **逐字取 sd2-pe 原文**（:158 / :159 / :161）：
#   画质包   「高清，细节丰富，电影质感，色彩自然，光影柔和」
#   稳定包   「人物面部稳定不变形、五官清晰、动作连贯自然，不僵硬，无穿模无卡顿」
#   水印兜底 「不要生成水印；不要生成 Logo」
# sd2-pe:129 明写「路径 A 仍必须挂载默认必挂的兜底约束包（画质 / 稳定 / 水印 Logo）」，
# 编辑任务属于路径 A。以前这里只挂了稳定 + 水印、而且用的是我们自己概括的
# "画面稳定无变形"，缺了官方的画质包。
def _volc20_boilerplate(c: dict) -> str:
    """2.0 强制兜底包 —— 各句逐字取 sd2-pe 原文，顺序同官方示例（`:172`/`:184`）。

    :158 画质包 / :159 稳定包 / **:160 字幕兜底** / :161 水印 Logo 兜底。
    🩸 2026-10-23：画面内文字能力整个下线，所以 :160 的字幕兜底**恒挂**
      （官方限定词是"非文字生成任务"，我们现在只有这一种任务）。
    """
    # 🩸🩸 2026-10-27（对标官方 skill `sd2-pe`）：官方对路径 A 的原话是
    #   「路径 A 仍必须挂载默认必挂的兜底约束包（画质 / 稳定 / 水印 Logo），
    #     但**折叠在末尾用一两句串联即可，无需分块罗列**」，
    #   并且 3.2 表里给了压缩写法：「路径 A **可压缩为短句"高清电影质感"**」。
    # 我们之前把四条包用「；」分号**罗列**成五段（画质/稳定/字幕/水印/Logo），
    # 正是官方说"无需"的分块罗列，190 字里有一大半是它。
    # 官方「单点编辑」示例的实际落笔是：
    #   「…动作和运镜不变。画面稳定无变形，不要生成水印，不要生成 Logo。」
    # ⇒ 内容一个不少，改成折叠短句。
    # 🩸 2026-11-05：画质包必挂（`sd2-pe:219`「强制兜底：最终输出必须包含
    #   画质包 + 稳定包 + 水印 / Logo 兜底」），但「高清电影质感」是**写实**词。
    #   选了动漫 / 3D / 手绘时，它和前面的「整体风格为2D日漫风格」直接打架 ——
    #   官方 `prompt-guide.md:354`（风格漂移）要求用明确的风格约束词压住写实漂移，
    #   同一句里再给一个写实质感词等于把约束抵消掉。
    #   ⇒ 非写实风格下，画质项换成该风格的官方锚点词（`edit_spec._STYLE_ANCHOR_20`，
    #     `anime`/`3d`/`sketch` 三个都取自官方 `:354` 与 `sd2-pe:163` 的原词）。
    #     画质包仍在、约束不丢、语义不冲突。`live`（实拍）保持「高清电影质感」。
    from app.services.edit_spec import _STYLE_ANCHOR_20, STYLES

    _st = str((c or {}).get("style") or "").strip()
    _quality = "高清电影质感"
    if _st and _st != "live":
        _quality = _STYLE_ANCHOR_20.get(_st) or STYLES.get(_st) or _quality
    parts = [
        _quality,
        "画面稳定无变形",
        "保持无字幕，避免生成任何文字或字幕",
        "不要生成水印",
        "不要生成 Logo",
    ]
    return "，".join(parts)

# 2.0 官方「双胞胎兜底」（sd2-pe：多人/多主体场景**必挂**）。
# 2.5 明令禁止自动加这类通用负向约束（sd25-pe 原则 8 点名「分身」），所以只挂 2.0。
_VOLC_20_TWIN_GUARD = ("视频全程禁止出现外形、着装、配饰完全一致的人物，"
                       "禁止生成同款分身、双胞胎效果，同一画面中仅保留单个对应人物，"
                       "不出现人物重复复刻")

# ---- 2.0 台词（`{}`）----
# 官方 `seedance-20-guide.md:298`「特殊字符规范」：音乐 `（）`、音效 `<>`、
# **台词 `{}`**、字幕 `【】`。同页：小语种要标语种，「如：用日语说道{こんにちは}」。
# 🩸 这是 2.0 的标记法，和 H3 的 `<d>[Chinese] …</d>`（`ref-en:220`）**不是一套**，
# 不能互相借用。官方案例见 :230「其中一人笑着问 {考得怎么样呀，过了吗}」。
# 火山 2.0 的台词是中文句式，「用<语言>说道」把语言交代清楚（官方 `sd20-guide:531`
# 的句式是「使用@音频1的音色说{…}」，没说语言；小语种必须补，不然模型按中文念）。
_SD20_LANG_LEAD = {
    "ja": "用日语说道", "ko": "用韩语说道",
    "th": "用泰语说道", "vi": "用越南语说道", "id": "用印尼语说道",
    "ms": "用马来语说道", "tl": "用菲律宾语说道", "es": "用西班牙语说道",
    "mx": "用西班牙语说道", "pt": "用葡萄牙语说道", "ru": "用俄语说道",
    "ar": "用阿拉伯语说道", "de": "用德语说道", "fr": "用法语说道",
    "it": "用意大利语说道",
}

def _sd20_line(text: str, who: str, lang: str = "zh",
               audio_ref: bool = False) -> str:
    """2.0 的一句台词。音色句式取官方 `sd20-guide:531`「使用@音频1…的音色说」。

    🩸 2026-10-25：`who` 为空 = 判不出是谁在说（见 `_sd20_who`）。
    这时**不补一个「人物」当主语**，按官方两条走：
      · 有音频参考 → `:531`/skill `:196`「使用@音频1…的音色说{…}」（只写音色）；
      · 没有音频参考 → `:298` 的裸台词 `{…}`。
    补「人物」在双人画面里没有唯一解，等于又回到"谁都说"。
    """
    t = (text or "").strip()
    if not t:
        return ""
    voice = "使用@音频1的音色" if audio_ref else ""
    lead = _SD20_LANG_LEAD.get((lang or "zh").strip().lower(), "")
    # 🩸 2026-10-27：音色句和语种句是**两条官方句式**，并排时必须断开。
    # 以前直接拼成「使用@音频1的音色用泰语说道{…}」——「音色用泰语说道」
    # 读起来是音色在说话，两个指令糊成一句。官方各自的原句：
    #   · `sd20-guide:531`「使用@音频1的音色说」
    #   · `sd20-guide:298`「用日语说道{こんにちは}」
    # 加一个逗号就是两个完整句式并列，不增不减。
    _sep = "，" if (voice and lead) else ""
    if not who:
        if voice:
            return (f"{voice}{_sep}{lead}{{{t}}}" if lead
                    else f"{voice}说{{{t}}}")
        return f"{{{t}}}"
    if lead:
        return f"{who}{voice}{_sep}{lead}{{{t}}}"
    return f"{who}{voice}说{{{t}}}"

def _sd20_lines(shot_lines: list[list[dict]] | None, who: str,
                audio_ref: bool, speaker_label=None) -> list[str]:
    """逐镜台词 → 2.0 的句子列表（一段式，不分镜）。

    🩸 跨切点的台词在 `video_edit._span_lines` 里被拆成 `part="start"` /
    `part="end"` 两半（那是 H3 的 `<scenetrans>` 需要）。2.0 没有跨切标记，
    两半必须**拼回一句**——否则一份台词会变成两个 `{}`，等于让人说两遍。

    `speaker_label(pid)`（2026-10-25 补）：把这一句的说话人 id 翻成 2.0 的指代。
    以前整段只有一个 `who`，双人对话里所有台词挂同一个人 —— 官方 `:605` 的两人
    范例是**逐句点名**（「女性先说话，她说道"…"男性笑着回应"…"」），
    `:109/:119` 还要求「分别定义」「后续描述持续使用同一标签」。
    翻不出（没有 id / 盘点没给描述）就退回整段的 `who`；`who` 也是空时
    `_sd20_line` 会写成只带音色的句子，绝不并列两个人。
    """
    out: list[str] = []
    pending: dict | None = None

    def _w(x: dict) -> str:
        spk = str((x or {}).get("speaker") or "").strip()
        return (speaker_label(spk) if (spk and speaker_label) else "") or who

    for grp in (shot_lines or []):
        for x in (grp or []):
            t = (x.get("text") or "").strip()
            if not t:
                continue
            part = (x.get("part") or "").strip()
            if part == "start":
                pending = {"text": t, "lang": x.get("lang") or "zh", "who": _w(x)}
                continue
            if part == "end" and pending:
                t = pending["text"] + t
                lang = pending["lang"]
                # 跨切的两半是同一个人在说；前半没定出来才看后半
                w = pending["who"] or _w(x)
                pending = None
            else:
                lang = x.get("lang") or "zh"
                w = _w(x)
                if pending:  # 上一句只有前半、没有后半：先把它写出来，别吞掉
                    s = _sd20_line(pending["text"], pending["who"],
                                   pending["lang"], audio_ref)
                    if s:
                        out.append(s)
                    pending = None
            s = _sd20_line(t, w, lang, audio_ref)
            if s:
                out.append(s)
    if pending:
        s = _sd20_line(pending["text"], pending["who"], pending["lang"], audio_ref)
        if s:
            out.append(s)
    return out

def _sd20_who(c: dict, idx: dict[str, int],
              desc_by_id: dict[str, str] | None = None,
              orig_tags: dict[int, str] | None = None,
              ref_tag: dict | None = None,
              frame_people: list[dict] | None = None) -> str:
    """2.0 提示词里"说话人"怎么指代。**判不出唯一的人就返回空串**。

    🩸 2026-10-25 改（D11 ③）：以前判不出来时把**所有**人物图并列成一串
    「@图片1中的人物、@图片3中的人物」，于是台词句变成
    「@图片1中的人物、@图片3中的人物使用@音频1的音色说{…}」——
    把**两个不同的人**写成了同一个说话主体。2.0 官方没有任何一处这么写：
      · 指南 `:109`「多个主体…需要**分别定义**，并使用标签区分，避免指代混乱」；
      · 指南 `:605` 官方两人对话范例「**女性先说话，她说道**："…"**男性笑着回应**："…"」
        —— **每个说话人分别点名**；
      · 指南 `:594` 指认不到在场的人时用**声音**指认（「一个深沉、平静的男声说」）；
      · 官方 skill `:196`「使用 @音频1 低厚温润…的音色说」—— 只有音色、不点人名。
    ⇒ 判不出就返回空，由调用方按 `:196` 写**只带音色**的句子，绝不并列。

    能唯一确定时照旧返回指代：点了 `speaker_ids` 就只写那一位；
    画面里只有一个换人目标时就写那一位。
    """
    ids = [str(x) for x in (c.get("person_ids") or [])]
    sid = [str(x) for x in (c.get("speaker_ids") or [])]
    if len(sid) == 1:
        pid = sid[0]
        if pid in ids:
            k = ids.index(pid)
            if k < len(PERSON_SLOTS) and PERSON_SLOTS[k] in idx:
                slot = PERSON_SLOTS[k]
                # 🩸 有主体标签就**持续用同一个标签**（官方 `:119`「后续描述涉及到…
                # 持续使用"警察"指代」，`:110`「后续描述中需持续使用对应标签」）。
                # 不然同一份提示词里前半段叫 <主体1>、后半段叫 @图片1中的人物。
                # 标签来自**原片侧**定义（`_sd20_person_tags`），按盘点 id 查。
                # 🩸 2026-10-28：换过的人开口说话，点名用**图片侧**那个标签 ——
                # 前面刚写「将其中的<主体3>替换为<主体1>」，之后他就是 `<主体1>`，
                # 再让 `<主体3>` 说话等于把台词派给一张已经被换掉的脸
                # （官方 `:119` 持续使用同一标签、`:121` 避免语义冲突）。
                if ref_tag:
                    _t = ref_tag.get(k) if isinstance(ref_tag, dict) else ""
                    if _t:
                        return str(_t)
                if orig_tags and pid in orig_tags:
                    return orig_tags[pid]
                return f"{_pic('volc', idx[slot])}中的人物"
        # 🩸 2026-10-26：与 `_sd20_speaker_label` 同一个病，这里漏了一处 ——
        # 盘点描述是整段（逗号串到底、以**衣服**收尾），直接接动词就成了
        #   「@视频1中年轻女子，黑色长发梳成古装高髻，身着广袖古装说话时的口型…」
        # 读起来是"衣服在说话"（同 D24「把手枪换成一个人」那类）。取主语短语。
        d = _head_noun(_who(desc_by_id, pid, "zh"))
        if d:
            return f"{_vid('volc')}中{d}"
    # 🩸 多人时**每个** `@图片N` 后面都要补名词隔断（`sd2-pe:17`「裸用 @图片N
    # 紧接动词或方位词时易触发数字粘连歧义…应在 @图片N 后补名词隔断」）。
    pics = [(s, f"{_pic('volc', idx[s])}中的人物")
            for s in PERSON_SLOTS if s in idx]
    # 单人（或一张图都没有的局面）：没有歧义，照旧点名
    if len(pics) == 1:
        # 🩸 2026-10-28（当前产出实测）：「只有一张参考图」**不等于**「只有一个人在说」。
        #   双人画面、只换其中一个、台词又没标说话人时，这里以前把**每一句台词**
        #   都挂到被换的那个人身上（实测 `2f1f26d8`：
        #   「<主体2>说{不知道谁说的}。<主体2>说{也不知道}」），
        #   而画面里另一个人也在说话 —— 正是 `7536fdb5` 那次「所有人的台词挂到
        #   换上去那张脸」的同一个病，只是入口不同。
        #   官方 `:605` 要求逐句点名、`:594` 判不出就用声音指认；
        #   判不出就**返回空**，由调用方写只带音色的句子（`:531`/`:196`）。
        present = [x for x in (frame_people or []) if _present(x)]
        if len(present) >= 2:
            return ""
        slot, pic = pics[0]
        # 🩸 已经绑过 `<主体N>` 就**继续用标签**（官方 `:109`「后续描述中需持续
        # 使用对应标签，避免指代混乱」、`:119`「每次提到主体时，都应使用同一标签」）。
        # 以前这里不看标签 → 同一份提示词前半段叫 <主体1>、后半段改叫
        # 「@图片1中的人物」，同一个人出现两种指代。D29 修。
        # 🩸 2026-10-28：`orig_tags` 的键是**盘点 id**（`_sd20_person_tags` 返回
        #   `{盘点id: <主体N>}`），原来写的是 `k in orig_tags` —— 拿**槽位下标**
        #   去查**字符串键**，恒为假 ⇒ 上面那段「继续用同一个标签」从来没生效过。
        #   实测（双人画面只换一人、不点明说话人）：定义句写 `<主体2>`、编辑句换
        #   的也是 `<主体2>`，台词句却写成「@图片1中的人物说」—— 同一个人两种指代，
        #   正是官方 `:109` 要避免的。要查的是「这张图对应的那个人」的盘点 id
        #   （`person_ids[k]`，与 `_clauses` 里槽位↔人的对应关系同一套）。
        k = PERSON_SLOTS.index(slot)
        _ids_pic = [str(x) for x in (c.get("person_ids") or [])]
        if orig_tags and k < len(_ids_pic) and _ids_pic[k] in orig_tags:
            return orig_tags[_ids_pic[k]]
        return pic
    return ""

def _sd20_speaker_label(pid: str, c: dict, idx: dict[str, int],
                        desc_by_id: dict | None,
                        orig_tags: dict[int, str] | None = None,
                        frame_people: list[dict] | None = None,
                        ref_tag: dict | None = None) -> str:
    """说话人 id → 2.0 提示词里的指代（**逐句点名**用）。

    只回答"这一句是谁说的"，与 `_sd20_who`（整段统一的说话人）分工不同。
    出处（全部 2.0 官方）：
      · `:605` 两人范例逐句点名：「女性先说话，她说道"…"男性笑着回应"…"」；
      · `:109/:119`「需要分别定义，并使用标签区分…后续描述持续使用同一标签」
        —— 所以是换人目标时优先用已定义的 `<主体N>`；
      · `:594` 指认不到在场的人时用**声音**指认（「一个深沉、平静的男声说」）——
        我们拿不到声音描述，这一支返回空，由调用方退回只带音色的句子，不编造。
    """
    pid = str(pid or "").strip()
    if not pid:
        return ""
    ids = [str(x) for x in (c.get("person_ids") or [])]
    # 🩸 有定义过的标签就**一直用它**（官方 `:119`）——这一支管的是**没被换的**
    # 那个人说话（`_sd20_person_tags` 现在定义画面里每个人，所以他也有标签）。
    # 🩸 2026-10-28：**被换过的人说话时，点名用图片侧那个标签**。前面刚写
    #   「将其中的<主体3>替换为<主体1>」，之后这个人就是 `<主体1>`；
    #   再用 `<主体3>` 等于把话说给一张已经被换掉的脸（官方 `:119`
    #   「后续描述中需持续使用对应标签」、`:121`「避免语义冲突」）。
    if ref_tag:
        _ids = [str(x) for x in (c.get("person_ids") or [])]
        if pid in _ids:
            _t = ref_tag.get(_ids.index(pid)) if isinstance(ref_tag, dict) else ""
            if _t:
                return str(_t)
    if orig_tags and pid in orig_tags:
        return orig_tags[pid]
    if pid in ids:
        k = ids.index(pid)
        if k < len(PERSON_SLOTS) and PERSON_SLOTS[k] in idx:
            slot = PERSON_SLOTS[k]
            return f"{_pic('volc', idx[slot])}中的人物"
    # 🩸 2026-10-26：这里原来直接返回**整段**外观描述，于是第二个人说话的句子是
    #   「年轻女子，黑色长发梳成古装高髻，身着广袖古装使用@音频1的音色说{…}」
    # —— 逗号串到底、最后以衣服收尾再接动词，读起来是"衣服在说话"（与 D24 那次
    # 「把手枪换成一个人」同一类病）。取主语短语 + 标来源，写成
    #   「@视频1中年轻女子使用@音频1的音色说{…}」。
    # 出处：`sd20-guide:594` 指认在场的人用「谁在说」的名词短语；`sd20-guide:109` 多主体要
    # 明确指代；`sd2-pe:17`「裸接动词易歧义」的同一条思路（这里补的是来源+名词）。
    _dsc = _who(desc_by_id, pid, "zh")
    # 🩸 2026-10-28（当前产出实测）：**没被换的那个说话人**在单人换人场景里
    #   一个标签都没有（`_sd20_person_tags` 的单目标分支只定义两个人），
    #   于是退回 `_head_noun` —— 两个男人同框时产出
    #   「@视频1中**男性**使用@音频1的音色说{为什么}」，谁在说没有唯一解
    #   （`sd2-pe:72` 明写"多人未指明谁在左/右"是病灶）。
    #   ⇒ 先按**方位**指认（`sd20-guide:153` 的写法，方位来自盘点、唯一才用），
    #     再退回人称词、最后才用特征短语（`cloth=False`：旧衣服不进指认）。
    if frame_people:
        _k = next((i for i, p in enumerate(frame_people)
                   if str((p or {}).get("id") or "") == pid), None)
        if _k is not None:
            _loc = _orig_feat_20(frame_people, _k, pool=frame_people,
                                   cloth=False)
            if _loc:
                return f"{_vid('volc')}中{_loc}"
    d = _head_noun(_dsc)
    if not d:
        # 🩸 2026-10-27（全场景导出抓到的）：真实盘点里**几乎没人以人称词收尾**
        # （「穿黑色短袖高领上衣，深色短发，腰间系有带银色方形扣的黑色皮带，
        #   穿深色牛仔裤」），`_head_noun` 一律返回空 ⇒ 这句返回空 ⇒ 调用方退回
        # 整段统一的 `who`，**所有人说话都挂到被换上去的那张脸上**。
        # 实测 `7536fdb5` 6 个人 `_head_noun` 全空：
        #   `<主体2>说{你站住。}。@图片1中的人物说{为什么？}。`
        # 第二句的说话人其实是**另一个人**，字面上却指向 `<主体1>`。
        # ⇒ 与换人指认同一把尺：`_feat_phrase`（`cloth=False`：旧衣服不进指认）。
        d = _feat_phrase(_dsc, cloth=False, sd20=True)
    return f"{_vid('volc')}中{d}" if d else ""

def _keep_point_edit(spec: dict) -> str:
    """2.0 的保留句：官方「单点编辑」原句。**只属于 2.0，别家不许引用。**

    🩸 2026-10-28：这段原来长在三家共读的 `edit_spec._keep_sentence()` 里，
       靠一个 `point_edit` 开关控制 —— 形式上是"开关"，实质仍是
       **2.0 的官方句式躺在共用文件里**，加第 4 家时那里又多一个 elif
       （正是当初说"加一家要改 10 处"的那种形状）。搬回 2.0 自己的编译器：
       共用层只负责算"该保哪些项"，**怎么写成一句话由各家自己定**。

    出处（**只引 Seedance 2.0 自己的官方文件**，逐字，不混写）：

    ① ~~风格迁移~~ —— **2026-11-04 清理时删除**。原引 LAS `las_cn.md:432`
       （`style_transfer/general` 模板），那是「视频编辑增强版算子」的
       `user_prompt`，不是 Seedance 原生提示词，导图 15 篇里也没有它。
       2.0 官方对风格只讲两件事：`:33`「未提及的部分，默认保持不变」、
       `:357`「提示词中未强调视频风格，有概率漂移成真人写实」——
       ⇒ 该强调**目标风格**，不补一串保留项。`keep_others` 那句另引 `:41`。

    ② ~~有人物的编辑~~ —— **2026-11-04 清理时删除**（出处 `las_cn.md:405` 属
       LAS「视频编辑增强版算子」，不是 Seedance 原生提示词；详见下方代码注释
       与 `docs/SD20-RULE-CLEANUP.md` 病灶 B）。

    ③ **所有编辑**（换人 / 换装 / 换物体 / 换背景）—— `sd2-pe:126` 单点编辑原句
       与 `sd20-guide:941` 逐字一致：
       「动作和运镜不变」。

    三种都仍按 keep 开关取子集（关掉还照写 = 说一套做一套）。
    """
    _kp = spec.get("keep") or {}
    _chg = spec.get("change") or {}
    # 🧹 2026-11-04 清理（`docs/SD20-RULE-CLEANUP.md`）：这行原引 **LAS
    #   `las_cn.md:432`** `style_transfer/general` 的模板句 —— LAS 是
    #   「视频编辑增强版算子」，不是 Seedance 原生提示词，导图 15 篇里也没有它。
    #   Seedance 2.0 官方对风格迁移只讲两件事：
    #     · `prompt-guide.md:33`「未提及的部分，**默认保持不变**」→ 不写也保持不变；
    #     · `prompt-guide.md:357`「提示词中**未强调视频风格**，生成的视频有概率
    #       漂移成真人写实风格」→ 该强调的是**目标风格**，不是补一串保留项。
    #   ⇒ 整句删除，风格目标由 `change.style_words` 那一路写死。
    if _chg.get("style_ref") or _chg.get("style_video"):
        return ""
    # 🧹 2026-11-04 清理（`docs/SD20-RULE-CLEANUP.md` 病灶 B）：换人/换装分支**已删**，
    #   统一落到下面的 2.0 原生写法（`sd2-pe:126`「动作和运镜不变」，`sd20-guide:941` 逐字一致）。
    #
    #   删掉的那句是「保留原视频动作、位置、互动、镜头和背景」，出处
    #   `las_cn.md:405` —— **LAS「视频编辑增强版 2.0 算子」**（服务端还要再做
    #   VLM / 关键帧重绘 / 提示词组装），不是 Seedance 原生 API 的提示词。
    #   `las_cn.md` 甚至不在 `SD20-SOURCES-MINDMAP.md` 的 15 篇里。
    #   同一段文字的前半句（「完整替换 + 使用目标人物的脸…」）已在
    #   2026-10-30 由 `scripts/prompt_model_standards_check.py:215` 撤回，
    #   **后半句却还留在这里** —— 一处撤回、一处没撤，本身就该清。
    #
    #   而且它和本编译器的另一条规则**自相矛盾**：`_volc` 里写着
    #   「2.0 不写范围闭环，因为 `sd20-guide:33` 已把『未提及的部分』定义成默认不变」，
    #   这里却把"要变的那些"又列了一遍。
    #
    #   🔁 退路：LAS 原句与 2026-10-27 的实测记录都在 git 历史里。
    _bits = []
    if _kp.get("motion"):
        _bits.append("动作")
    if _kp.get("camera"):
        _bits.append("运镜")
    return ("和".join(_bits) + "不变。") if _bits else ""


def _volc(spec: dict, c: dict, idx: dict[str, int], *, model: str = "",
          people: list[dict] | None = None,
          frame_people: list[dict] | None = None,
          frame_others: list[dict] | None = None,
          audio_ref: bool = False,
          desc_by_id: dict[str, str] | None = None,
          shot_cuts: list[float] | None = None,
          boundary_pic: int = 0,
          shot_lines: list[list[dict]] | None = None,
          style_video: bool = False,
          subject_look: dict | None = None,
          subject_looks: dict | None = None) -> str:
    from app.services import model_specs

    ms = model_specs.volc(model)
    # 🩸 2.5 必须走官方五段模板，2.0 必须走一段式（sd2-pe:118）——
    #    两家结构相反，不能共用同一套拼装。
    if ms.get("edit_task_param"):
        # 🩸 2026-10-28：这里以前**静默转调** 2.5 的编译器
        #   （`from . import volc25_compile; return volc25_compile._volc_25(...)`）。
        #   两个问题：
        #   ① 跨家引用 —— 2.0 的模块认识 2.5 的模块。分离门抓不到（函数名不是
        #     厂商字面量），等于在门的盲区里；
        #   ② 更危险的是它**藏住了一次错误路由**：2.5 的型号被送进 2.0 的编译器时
        #     悄悄跑 2.5 的代码、产出还是对的 —— 我改 2.0 的代码，实际执行的是 2.5 的，
        #     看不出任何异常。
        #   正常路径由注册表按型号直接进 `volc25.py`，走不到这里。
        #   真走到了 = 路由错了，**要炸出来**，不许静默兜。
        raise RuntimeError(
            f"型号 {model!r} 是 2.5 的编辑任务，不许进 2.0 的编译器"
            "（两家提示词结构相反，不能互相兜底）。"
            "请检查 `app.services.models.adapter_for()` 的路由是否正确。")
    # 🩸 2.0 多主体场景：把画面里每个人绑成 `<主体N>`（官方 `sd20-guide:107` 分别定义）。
    # 单人画面返回空，走原来的写法。
    defs: list[str] = []
    orig_tags: dict[int, str] = {}
    # 图片侧标签表（目标槽位序号 → `<主体N>`）；单人画面为空表，走内联写法
    ref_tag: dict = {}
    if not ms.get("edit_task_param"):
        defs, orig_tags, ref_tag = _person_tags_20(
            c, idx, "volc", people, frame_people=frame_people,
            ref_desc=str((subject_look or {}).get("zh") or ""),
            subject_looks=subject_looks)
    parts = _clauses("volc", c, idx, dialect=CL20,
                     people=people, desc_by_id=desc_by_id,
                     frame_people=frame_people,
                     # 🩸 矩阵 §3.1：画面里的**非人主体**（龙/宠物/机器人）。
                     # 有它的时候单人换人句的源宾语必须点名（`skill:24` 的 `<原特征>`），
                     # 裸「人物」在"人 + 龙"的画面里没有唯一解。
                     frame_others=frame_others,
                     keep=spec["keep"],
                     style_anchor=not ms.get("edit_task_param"),
                     style_video=style_video,
                     orig_tags=orig_tags, ref_tag=ref_tag,
                     # 🩸 段内有切点时才声明"视频全程"（官方 `:33` 局部或全局、
                     # `:409` 全局约束、`:411` 的用词「视频全程」）。
                     # `052dcbf0`（13.885s 单人换人，段内 4 个切点）实测：
                     # 不声明范围 → 0–11.2s 换了、切镜后两镜原样返回
                     # （尾段 p90 0.288 / not_swapped）。
                     scope_all=bool(shot_cuts))
    # 🩸🩸 2026-10-27（主人：「你根本没有对标 2.0 官方」）：
    # 官方 `sd20-guide:59-65` 的**组合任务**句式是：
    #   「参考`<图片/视频N>`的`[参考维度]`，严格编辑`<视频X>`，`[具体编辑内容]`」
    # ⇒ 参考分句必须在「严格编辑」**之前**。以前风格参考句被塞在 body 末尾，
    # 拼出来是「严格编辑@视频1，…；参考@图片2的色调…」——顺序反了。
    # `sd20-guide:56` 还专门写着：编辑任务「请勿使用"参考<视频N>"，以免被误判为
    # 参考任务」；只有这个固定组合句式里才允许「参考」字样，且**必须在前**。
    # 音频那一支早就是这么做的（见下面 `head = "参考@音频1中的音色，" + head`），
    # 风格这一支漏了 —— 现在补齐，两条走同一个位置。
    # 只挑真正以「参考<素材N>的…」开头的分句；风格**约束词**（`整体风格为X`，
    # 官方 `:713` 示例本身就在句末）留在原处不动。
    # 参考分句两种形状都要前置（官方 `:59-65`「参考…，严格编辑…」）：
    #   ① 「参考@图片N的…」（无标签 / 风格 / 音频）
    #   ② 「<主体N>的面部特征…参考@图片N」（有标签的职责句）
    _is_ref = r"^(?:参考[@图]|<主体\s*\d+>[^。；]*参考[@图])"
    _lead = [x for x in parts if re.match(_is_ref, x)]
    if _lead:
        parts = [x for x in parts if not re.match(_is_ref, x)]
    body = "；".join(parts)
    # 官方编辑句式，两家 skill 各给一句，正好按型号分：
    #   2.0  sd2-pe「严格编辑 @视频N，将其中的<原特征>修改为<新特征>」
    #   2.5  sd25-pe「编辑@视频1，只把<…>替换为<…>」
    # 2.5 还有一条硬要求（创建任务 API「视频编辑」）：提示词里**必须**出现
    # 「编辑视频/增加/加上/删除/去掉/修改/替换/改成」之一，否则会被判成
    # 参考任务，任务启动后异步报错 TaskTypeMismatch —— 钱已经花了才失败。
    if body:
        lead = "编辑" if ms["edit_task_param"] else "严格编辑"
        # 2.5 官方模板是「编辑@视频1，只把<原对象>修改为<目标>」——「只」是范围限定词
        if ms["edit_task_param"] and body.startswith("把"):
            body = "只" + body
        head = lead + _vid("volc") + "，" + body
    else:
        # 🩸 2026-10-27（主人：「你这是跨型号搬运」）：原来这里写的是
        # `"编辑视频：" + @视频1` —— 「编辑视频」这个**判词前缀是 2.5 的硬要求**
        # （`volc-api:442` 的 `omni_reference_task_type`，不写会被判成参考任务、
        # 异步报 TaskTypeMismatch）。2.0 没有这个参数、也没有这个报错
        # （2.0 教程全文零命中），搬过来纯属多一句话。
        # 2.0 走官方 `:39` 的编辑句式起头即可。
        # 🩸 2026-11-04：**后面还有补充说明时用逗号连**，不另起一句。
        #   官方所有编辑句式都是逗号连接（`prompt-guide.md:38`
        #   「严格编辑<视频N>，将其中的<原特征>修改为<新特征>」）；
        #   以前拼出来是「严格编辑@视频1。画面更亮一点。」—— 断成两句。
        #   尾逗号由下面的 join 识别（以「，」结尾的段不补句号）。
        head = "严格编辑" + _vid("volc")
    # 🩸 有音频参考时按官方**组合任务**句式起头（`seedance-20-guide.md:65`）：
    #   「参考<图片/视频N>的[参考维度]，严格编辑<视频X>，[具体编辑内容]」
    #   参考维度取官方音频参考那一行（同文件 :28「参考<音频N>中的音色」）。
    #   不写这句，@音频1 在提示词里没有任何落点 —— 素材白传，模型不知道拿它干什么。
    # （这里已经是 2.0 分支：2.5 在函数开头就转给 `_volc_25` 了。）
    # 🩸 2026-10-25：**原声保留时不写音色**，与 2.5 同一条闸门（`_volc_25` 的
    # 【目标素材职责】在 original 下写的是「@音频1用于@视频1的原片音轨」，
    # 只有 tts/mix 才写「音色与台词」）。2.0 以前无条件写，结果同一句提示词里
    # 一边说「原片音轨原样保留」、一边让两个人物「使用@音频1的音色说」五句词。
    _amode = (spec.get("audio") or "tts").strip().lower()
    if audio_ref and _amode != "original":
        head = "参考@音频1中的音色，" + head
    # 风格参考分句：同样按官方 `:63` 组合任务句式前置（见上面 `_lead` 的注释）。
    # 多个参考维度可以并列：「参考@音频1中的音色，参考@图片2的色调、光影和质感，
    # 严格编辑@视频1，…」。
    if _lead:
        head = "，".join(_lead) + "，" + head
    # 🩸 2026-10-27（主人：「你这是跨型号搬运」）：这条兜底原本是**2.5 的判词要求**
    # —— 2.5 的 API 在提示词里找不到「编辑视频/增加/加上/删除/去掉/修改/替换/改成」
    # 之一时，会判成参考任务并在**任务创建之后**异步报 TaskTypeMismatch（钱已花）。
    # 2.0 没有 `omni_reference_task_type` 参数、教程全文零命中 ⇒ 2.0 不需要这层兜底。
    # 它唯一的作用是「只填补充说明」时补一个前缀，而那正是 2.0 该用 `:39` 起头的地方
    # （上面 else 分支已经写成「严格编辑@视频1」）。
    # 🩸 换人必须点明「每一镜」——2026-10-25 实测 `052dcbf0`（13.885s 单人换人）：
    # 整段一次生成、段内有 4 个原片切点（3.0 / 6.9 / 11.333 / 12.933，第二场从
    # 11.333s 起），而提示词只写「将其中的人物替换为@图片1中的人物」。
    # 结果 0–11.2s 换了，切镜之后的两镜原样返回（身份核对：尾段 p90 0.288、
    # 同人占比 0.0 → not_swapped；整段 p90 0.741 把这一段平均掉了）。
    # 官方依据（都是 2.0 的《提示词指南》）：
    #   · `:31`「在原视频基础上进行**局部或全局**修改」+ `:33`「**未提及的部分，
    #     默认保持不变**」⇒ 不说范围，切镜后那两镜就是"未提及"，原样返回；
    #   · `:40` 修改元素的官方句式就是「严格编辑<视频N>，**将其中的**<原特征>
    #     修改为<新特征>」——"其中的"覆盖整条 @视频N，不是只覆盖开头一镜。
    # 🩸 但**不写「分成 N 个分镜 / 镜头1 镜头2」**：那是 `:125-129`「使用分镜时序」
    # 给**生成任务**的写法。编辑任务里写镜头结构等于把「保持原镜头」改写成
    # 「重新排 N 个镜头」（`shot_plan_sentence` 里 2026-10-23 的回源结论）。
    # 这里只补**编辑范围**，一个镜头结构字都不加。
    # 只在**单人换人**时挂：多人换人各有各的 `<主体N>`，写「每一镜里的人物」
    # 会把没被选中的那个人也一起换掉。
    # 还有一条闸门：这一刀里**没出现**那个人时，`_clauses` 不写换人句（`_present`），
    # 这里也不能补范围句 —— 否则句子说"每一镜都替换"，而编辑目标压根没写。
    _p0 = people[0] if people else None
    # 🩸 2026-10-26 删除「编辑范围为@视频1的每一个镜头：每一镜里的人物都替换为
    # @图片1中的人物，切镜之后的新场景镜头同样替换」——
    # 官方三份 2.0 文件里「每一个镜头 / 每一镜」**0 次**（只有 `:382` 讲续写时
    # 以转场切镜时刻结尾）。官方 `:24` 的编辑句式本身写的是「将其中的<原特征>
    # 修改为<新特征>」——**「其中的」已经覆盖整条 @视频N**，不需要另加范围句。
    # 留着它等于每句都在替模型解释官方公式，属于自造。
    # 顺序：换什么 → 范围闭环 → 补充说明 → 保什么（保留句放最后，模型最容易照着执行）
    extra = spec.get("extra") or ""
    # 🩸 2.0 不写「按新配音重做口型」：官方三份文件 grep「口型」0 次（见 edit_spec）。
    # 🩸 2026-10-28：保留句的「单点编辑」原句**整体搬到这里**（`_keep_point_edit`）——
    #   它只属于 2.0，之前躺在共用层靠开关控制，加第 4 家时那里又是一个 elif。
    tail = _keep_point_edit(spec)
    # 有明确修改对象时，必须写清"其余的不动"（官方视频编辑模板的硬要求）
    # 🩸 2.0 **不写范围闭环句**（2026-10-23 回源更正）。
    # 官方《Seedance 2.0 提示词指南》§「编辑视频」开头就写明：
    #   「在原视频基础上进行局部或全局修改。**未提及的部分，默认保持不变**。」
    # ⇒ "其他人/物/背景不动"本来就是默认行为，多写一句等于把默认行为
    #    改写成一条新指令。sd2-pe 全文也没有"除以上…保持原样"这种句子
    #    （那是 2.5 视频编辑模板的「范围闭环」，见 `_volc_25`）。
    # 多人场景要指定"换哪一个"，用官方 §1「定义主体」的 `<主体N>` 标签区分。
    scope = ""
    # 口型参考音频。要说清这条音频归谁，不是只说"有声音"。
    # 🩸 2.0 的音频域官方原文（2026-10-23 回源更正，以前这里判成"2.0 没有音频域"是错的）：
    #   · 能力：`volc-api:35` 参考音频（0-3 个）**支持编辑视频**；
    #     `sd20.md:550`「您可以提供待编辑的视频、**参考图片或音频**」
    #   · 能带什么：`sd20.md:146`「参考音频的**音色**、音乐旋律、**对话内容**等核心信息」
    #   · 句式：`seedance-20-guide.md:65` 组合任务「参考<…>的[参考维度]，
    #     严格编辑<视频X>，[具体编辑内容]」；音色句同文件 :531「使用@音频1…的音色说」
    #   ⇒ 2.0 一样写音色与口型，只是台词用 `{}`（:298），不是 H3 的 `<d>`。
    # 🩸 换配音 vs 保留原声必须分叉（**2.0 自己的口径**）：
    #   · 保留原声 → `:31` 编辑视频「未提及的部分，默认保持不变」⇒ 不写音色、不写台词；
    #   · 换配音 → 要写"用@音频1的音色说{…}"（`:531`），台词才存在。
    #   以前两种模式写同一套，结果原声模式下同一句提示词既说"音轨原样保留"
    #   又让两个人"用这条音轨的音色说"五句词（D10）。
    who = _sd20_who(c, idx, desc_by_id, orig_tags, ref_tag=ref_tag,
                    frame_people=frame_people)
    audio_clause = ""
    if audio_ref:
        mode = (spec.get("audio") or "tts").strip().lower()
        if mode in ("tts", "mix"):
            # 换配音/换台词：新音轨就是成片里那一句，必须逐字对齐。
            # 🩸 2026-10-25：**判不出说话人时不写这句**（`who` 为空）。
            # 理由全部在 2.0：
            #   · 官方指南全文没有"口型与音频逐字同步"这种句子（grep 0 处）——
            #     这句是从 2.5 的视频音频编辑模板搬来的，两家规则不通用；
            #   · 2.0 官方让口型跟着台词走的办法是**逐句点名说话人**
            #     （`:605`「女性先说话，她说道…男性笑着回应…」）；
            #   · 判不出人时只能并列两个人（就是 D11 ③ 那个 bug），
            #     而并列既没有官方出处，也等于告诉模型"两个人都说这一句"。
            # 台词句本身已按 `:531` 写成「使用@音频1的音色说{…}」，口型跟着它走。
            # 🩸 2026-10-26 删除：「<主体1>说话时的口型与@音频1逐字同步，
            # 不得另说一套台词」—— 上面这段注释自己就写着官方 0 处，它是从 2.5
            # 的视频音频编辑模板搬来的。2.0 让口型跟着台词走的官方办法是**逐句
            # 点名说话人**（`:605`）+ `使用@音频1的音色说{…}`（`:531`），
            # 台词句本身已经这么写了，不需要再加一句口型指令。
            audio_clause = ""
        else:
            # 🩸 2026-10-26 清掉一句**从 2.5 搬来的**话（主人：三个模型要分离干净）。
            # 原来写「@音频1是@视频1的原片音轨，原样保留在成片中」，出处是
            # `sd25-pe:142`（2.5 要求逐条写明每个音频的用途）—— 那是 2.5 的规矩。
            # **2.0 自己的口径正相反**：`:31`「未提及的部分，默认保持不变」
            # ⇒ 保留原声时**什么都不写**，写了反而等于多给一条指令。
            # 所以这里留空。要改的话，出处必须是 2.0 的文件。
            audio_clause = ""
    # 台词：`{}` 格式（`seedance-20-guide.md:298`）。没有台词就是空串。
    # 🩸 2026-10-25：**原声保留不写台词**（与 2.5 一致，见 `_volc_25` 的
    # `if mode in ("tts","mix")`）。原声模式下这条句子的副作用实测可见：
    # `3f91496d` 双人换人，5 句台词全挂成「@图片1中的人物、@图片3中的人物…说{…}」
    # —— 两个**不同**的人被并列在同一个说话主体里（2.0 官方 `sd2-pe:138` 的
    # 「@图片1中的[…]、@图片2中的[…]」本来就是"同一个主体"的写法），
    # 而同一句提示词另一头写着「@音频1是原片音轨，原样保留在成片中」。
    # 🩸 逐句点名（2026-10-25）：2.0 官方 `:605` 的两人范例是每句各点各的
    # （「女性先说话，她说道…男性笑着回应…」），`:109/:119` 还要求标签唯一稳定。
    # 以前整段只有一个 `who`：双人对话里所有台词挂同一个人（或全都不带说话人），
    # 模型只能猜谁动嘴。
    def _sd20_lab(pid: str) -> str:
        return _sd20_speaker_label(pid, c, idx, desc_by_id, orig_tags,
                                   frame_people=frame_people, ref_tag=ref_tag)

    lines_clause = ("" if _amode == "original" else
                    "".join(f"{s}。" for s in _sd20_lines(
                        shot_lines, who, audio_ref, speaker_label=_sd20_lab)))
    # 🩸 2.0 和 2.5 在这条上官方口径**相反**：
    #    sd2-pe  强制：必须挂稳定包 + 水印/Logo 兜底；多人/多主体**必挂**双胞胎兜底
    #    sd25-pe 原则 8：不得自动添加用户未要求的画质包/稳定包/水印/Logo/字幕/分身
    # 认不出模型时按 2.0 挂（model_specs 的保守默认也是 2.0）。
    guards: list[str] = []
    if ms.get("auto_constraint"):
        # 🩸 D6（2026-10-23）：双胞胎兜底只在**多人 / 多主体**时挂。
        # 官方 `sd2-pe:101`「多人场景**必挂**双胞胎兜底」、
        # `:162`「双胞胎兜底（**多人 / 多主体**场景必挂）」。
        # 这句防的是"同一张脸在画面里出现两次"，单人画面没有第二张脸可撞。
        # 以前只要 `c.get("person")` 就挂，单人换人也带上一串没要求的话。
        if c.get("person") and _multi(people, desc_by_id):
            guards.append(_VOLC_20_TWIN_GUARD)
        # sd2-pe:219「强制兜底：最终输出必须包含画质包 + 稳定包 + 水印 / Logo 兜底」
        guards.append(_volc20_boilerplate(c))
    # 镜头结构（这一段是一个连续镜头，还是内部有原片的切点）—— 两家官方都要求写明，
    # 不写火山按"参考任务"自由切、H3 更是「默认会切镜」。见 `shot_plan_sentence`。
    shot_clause = (_shot_plan(shot_cuts) if shot_cuts is not None else "")
    # 🩸 2026-10-26 删掉「@视频1是唯一编辑母版，负责原始场景、机位、镜头运动、
    # 动作轨迹、遮挡关系和事件顺序」这句 —— 它的出处是 **2.5** 的 `sd25-pe:564`
    # 「视频编辑模板」结构件。2.0 的路径 A 没有这句话：
    # 2.0 靠 `:24`「严格编辑 @视频N，将其中的<原特征>修改为<新特征>」+
    # `:31`「未提及的部分，默认保持不变」表达同一件事，不需要另起一句结构件。
    # 三个模型各用各的骨架，**别家的模板句一句都不许搬**（主人 2026-10-26）。
    master = ""
    # 🩸 主体绑定句放在最前（官方 `:110` 的示例就是先定义再描述：
    #   「将视频1中的高个子男人定义为警察，将另一个矮个子男人定义为小偷。场景设定为…」）。
    # 放在 `严格编辑@视频1，` 后面的话会读成"编辑把X定义成Y"，语义是错的。
    bind = ("，".join(defs) + "。") if defs else ""
    # 各句自己可能已经带句号（保留句就是这样），再拼一个就会出现「。。」
    # 🩸 2026-11-04：**只有「补充说明」跟在空的编辑句后面才用逗号连**
    #   （官方 `prompt-guide.md:38`「严格编辑<视频N>，将其中的…」是逗号连接）。
    #   兜底包 / 保留句仍然独立成句 —— 它们不是编辑动作的一部分。
    _bare = "严格编辑" + _vid("volc")
    _segs = [(x, k) for x, k in (
        (head, 0), (master, 0), (shot_clause, 0), (scope, 0),
        (audio_clause, 0), (lines_clause, 0), (extra, 2),
        (tail, 0), *[(g, 0) for g in guards]) if x]
    # 🩸 2026-11-05：`bind` 自带句号，下面每段拼接又补一个「。」→ 出「。。」。
    #   先把 bind 尾句号去掉，交由拼接统一收尾（官方对提示词的标点没有专门规定，
    #   但重复句号属于书写错误，`prompt-guide.md` 全文没有「。。」这种写法）。
    out = bind.rstrip("。")
    for _x, _k in _segs:
        _x = _x.rstrip("。")
        if not out:
            out = _x
        elif _k == 2 and out == _bare:
            out += "，" + _x      # 补充说明接在空编辑句后面，同一句
        else:
            out += "。" + _x
    return out.strip()
