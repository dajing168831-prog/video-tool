# -*- coding: utf-8 -*-
"""复刻的**规格书**：把「原片事实 + 用户勾选」摊成一份结构化清单。

它**不写提示词**。写提示词的是 `clone_agent`（agent 读官方 skill 现写）。
这里只回答一件事：这一段里有什么、要改谁、参考图是几号。

🩸 为什么要有这一层（2026-10-31）：
  以前「这一段的编辑指令」由 `edit_spec.compile_prompt()` 用代码拼。拼出来的
  句子是对的，但**每一段都一样**——它只知道"换 P1"，不知道"这一段 P1 在
  画面左下角、正在转身、说第二句台词"。
  agent 要写出**这一段专属**的指令，就必须先拿到这些事实。事实归事实，
  怎么写由读官方 skill 的模型决定 —— 两层分开，谁也不替谁做主。
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def _change_of(spec: dict | None) -> dict:
    """勾选了什么。`edit_spec.normalize` 之后的结构，缺的键按"不改"算。"""
    s = spec or {}
    c = s.get("change") or {}
    return {
        "person": bool(c.get("person")),
        "product": bool(c.get("product")),
        "scene": bool(c.get("scene")),
        "wardrobe": bool(c.get("wardrobe")),
        # 🩸 2026-11-01 实测：`style` 在 `change` 里（`edit_spec.defaults`），
        #   原来这里写 `s.get("style")` 读的是**顶层** → 永远拿到空串，
        #   前端选「动漫 / 3D / 胶片」时规格书里一个字都没有，agent 只能按实拍写。
        "style": str(c.get("style") or ""),
        # 🩸 补充说明（`extra`）：代码编译版一直会拼进提示词
        #   （`edit_spec:1667/:1805`、`h3_compile:199`），规格书却没抄 → agent 版丢词。
        "extra": str(s.get("extra") or ""),
        # 🩸 谁在说话：代码编译版用它发 `<Subject N> (Sx)` 号
        #   （`h3_compile:739`、`volc25_compile:1061`），规格书一直没抄。
        #   漏了它，多说话人场景里号码只能靠猜（官方 `base-en:127`：不开口的人不发号）。
        "speaker_ids": [str(x) for x in (c.get("speaker_ids") or []) if str(x).strip()],
        # 🩸 风格参考**视频**（`style_video`）：它不进图片编号表（有自己的一套标号），
        #   `refs` 里也不会出现；不在这里说一句，agent 根本不知道还有第二个参考视频。
        "style_video": bool(c.get("style_video")),
        "person_ids": [str(x) for x in (c.get("person_ids") or []) if str(x).strip()],
        "wardrobe_ids": [str(x) for x in (c.get("wardrobe_ids") or []) if str(x).strip()],
        # 🩸 2026-11-01 主人：「人物那里是一定有参考图的，其他地方才有参考图或描述 2 选 1。」
        #   `product_target` 是**被换掉的那件东西**（定位词，盘点给的外观）；
        #   `product_desc` 才是**换成什么**。代码编译版一直按这个二分
        #   （`edit_spec:1766-1772`：有图 `换成图N里的产品` / 没图 `换成 product_desc`），
        #   规格书原来只抄了定位词、把"换成什么"整个丢了。
        "product_target": str(c.get("product_target") or ""),
        "product_desc": str(c.get("product_desc") or ""),
        "scene_desc": str(c.get("scene_desc") or ""),
        "wardrobe_desc": str(c.get("wardrobe_desc") or ""),
        "wardrobe_desc_by_id": dict(c.get("wardrobe_desc_by_id") or {}),
        "sound_changed": (s.get("audio") or "tts") != "original",
    }


def _src_id(x) -> str:
    """素材的身份指纹 —— **只用来算签名**，不展示给模型。

    🩸 换人图换了个人、内容却一样地"是 person 槽位"：只按槽位算签名，
    换图后签名不变 → 拿回上一张脸的旧指令。文件按 (名字, 大小, mtime) 认，
    `asset://` 直接用 ID。
    """
    s = str(x)
    if s.startswith(("asset://", "http://", "https://")):
        return s
    try:
        from pathlib import Path

        p = Path(s)
        if p.is_file():
            st = p.stat()
            return f"{p.name}:{st.st_size}:{int(st.st_mtime)}"
    except Exception:  # noqa: BLE001
        pass
    return s


def _refs_of(plan: dict) -> list[dict]:
    """这一段任务会发出去的素材，按**实际图号**列出来（顺序就是发出去的顺序）。

    `plan["slots"]` 是槽位名（person / product / scene …），`plan["ordered"]`
    是同一顺序的真实文件/asset。图号从 1 起 —— 火山 2.5 的写法是 `@图片1`。
    """
    slots = list(plan.get("slots") or [])
    ordered = list(plan.get("ordered") or [])
    out = [{"pic": 0, "slot": "source", "role": "原片（唯一编辑母版），提示词里写 @视频1"}]
    # 🩸 2026-10-31：音频参考原来**没列**，agent 不知道这段带了 @音频1 ——
    #   而 2.5 的编辑任务 `generate_audio=False`（`volc25.py:71`），成片音轨是
    #   我们自己合成的；模型只有拿到 @音频1 才会按它对齐口型时点
    #   （官方 `sd25-pe:623`「负责…口型时点…」）。漏掉这条 = 口型对不上。
    if plan.get("audio_ref"):
        # 🩸 2026-11-01：两种声音模式**不能写成同一句**。
        #   · `original` = 保留原声：喂进去的就是原片那条音轨，成片要**复用**它
        #     （H3 官方 `ref-en:118` 原句「<Audio 2> is the synchronized audio
        #     track of <Video 1> and is reused in the target video.」）。写成
        #     「按音色与台词说话」，模型会自己重说一遍 —— 声音不是原声，节奏也
        #     和原片不一致，口型跟着飘（2026-11-01 实测：agent 把它写成
        #     `voice-timbre reference`，retention 又写 `partially_copy`，
        #     定义和标记自相矛盾，违反 `ref-en:35`）。
        #   · `tts`/`mix` = 我们自己合成的配音：那时才是"按音色与台词说话"。
        _amode = str((plan.get("spec") or {}).get("audio") or "tts").strip().lower()
        if _amode == "original":
            _role = ("原片这一段的**同步音轨**，提示词里写 @音频1："
                     "成片**复用这条原声**（不是照着它重说一遍），口型跟着它走")
        else:
            _role = ("我们合成的配音，提示词里写 @音频1："
                     "替换后的人物按这条音频的音色与台词说话，口型时点对齐它")
        out.append({"pic": 0, "slot": "audio", "role": _role})
    for i, slot in enumerate(slots):
        if i >= len(ordered):
            break
        out.append({
            "pic": i + 1,
            "slot": str(slot),
            # 只进签名，`as_text` 不打印它
            "src": _src_id(ordered[i]),
            "role": {
                "person": "换人参考图：新人物长什么样，只认这张图",
                "person2": "第 2 个换人参考图",
                "person3": "第 3 个换人参考图",
                "product": "换产品参考图：新产品长什么样",
                "scene": "换场景参考图：新环境长什么样",
                "wardrobe": "换装参考图：新衣服长什么样",
                "style": "风格参考图",
                "style_ref": "风格参考图",
            }.get(str(slot), f"{slot} 参考图"),
        })
    return out


def _people_of(plan: dict) -> list[dict]:
    """原片盘点到的所有人（含没被选中的）。"""
    inv = plan.get("inventory") or {}
    out = []
    for p in (inv.get("people") or []):
        out.append({
            "id": str(p.get("id") or ""),
            "desc_zh": str(p.get("desc_zh") or ""),
            "desc_en": str(p.get("desc_en") or ""),
            # 出现的时间范围：让模型知道"这个人是从头到尾都在画面里的"，
            # 才会写「全片」。⚠️ 别拿它去治「最后一帧回原片」—— 那是拼接层
            # 的零头问题，已在 `assemble.plan_intervals` 修好（2026-10-31）。
            "appears": [[round(float(x.get("start") or 0), 2),
                         round(float(x.get("end") or 0), 2)]
                        for x in (p.get("appearances") or [])],
        })
    return out


def build(plan: dict, rec: dict, spans: list, cid: str = "") -> dict:
    """生成规格书。纯读，不调模型、不写盘。

    `plan` 来自 `video_edit.prepare`，`rec` 是原片分析结果，`spans` 是这次要
    处理的区间（`plan_spans` / `_auto_decision` 给的）。

    🩸 `cid` 用来取**已经盘点过的逐镜画面描述**（`vision_plan.describe_shots`，
    零额外费用）。没有它，两段的事实完全一样，agent 只能写出两段一样的指令 ——
    2026-10-31 第一次真跑就是这么暴露的。
    """
    from app.services import video_edit

    src = rec.get("source") or {}
    # 逐段画面内容：一条英文描述（盘点时那张图已经看过，直接取，不花钱）
    looks: list[str] = []
    if cid:
        try:
            from app.services import vision_plan as _vp

            looks = _vp.describe_shots(cid, [(float(a), float(b)) for a, b in spans])
        except Exception as e:  # noqa: BLE001
            log.warning("规格书：逐镜画面描述取不到（不影响其它字段）：%s", e)
    # 原片台词（ASR）：按句子中点落到哪一段
    speech = [x for x in ((rec.get("speech") or {}).get("segments") or [])
              if str(x.get("text") or "").strip()]
    spec = plan.get("spec") or {}
    change = _change_of(spec)
    acts = video_edit._span_plan(plan, spans) or {}
    shots = rec.get("shots") or []
    inv = plan.get("inventory") or {}
    from app.services import vision_plan as _vp

    # 🩸 台词**只能从配方里就有的 ASR 取**（`speech.segments`），不能读
    #   `rec["voice_lines"]`：出片时 `render` 会往浅拷贝里现塞它、还会
    #   `_assign_speakers` 往里写 `speaker`（`clone_pipeline.py:657`、
    #   `video_edit.py:1828`），而预览/生成时这两步都没发生 —— 两边算出的
    #   规格书不一样，签名就对不上，**agent 版被静默丢掉、出片发的是机器版**
    #   （2026-10-31 真跑：主人点了「用官方 skill 逐段重写」，`request_001.json`
    #   里发出去的仍是代码拼的句子）。
    #   判据：同一件事在预览和出片两个时刻必须由**同一份输入**算出来。
    stable_vl = [
        {"start": s.get("start"), "end": s.get("end"), "text": s.get("text")}
        for s in ((rec.get("speech") or {}).get("segments") or [])
        if str(s.get("text") or "").strip()
    ]
    rec = dict(rec, voice_lines=stable_vl)

    segments = []
    for n, sp in enumerate(spans, 1):
        a, b = float(sp[0]), float(sp[1])
        act, target = acts.get((a, b), ("", None))
        cuts = [round(float(s["start"]) - a, 3) for s in shots
                if a + 0.15 < float(s["start"]) < b - 0.15]
        people = []
        try:
            for p in (_vp.people_in(inv, a, b) or []):
                people.append({
                    "id": str(p.get("id") or ""),
                    "present": bool(p.get("present", True)),
                    "desc": str(p.get("desc_zh") or p.get("desc") or ""),
                })
        except Exception as e:  # noqa: BLE001
            log.warning("规格书：这一段的人物取不到（按空处理）：%s", e)
        lines = []
        try:
            # 🩸 `_span_lines` 返回的是**按镜分桶的二维列表**（外层=镜头，内层=台词），
            #   不是扁平的。第一版按一维遍历，拿到的每个元素都是 list，
            #   `.get()` 当场抛错被 except 吞掉 —— 台词整段消失且不报错。
            for bucket in (video_edit._span_lines(rec, a, b, cuts) or []):
                for ln in (bucket or []):
                    lines.append({
                        "who": str(ln.get("speaker") or ln.get("who") or ""),
                        "text": str(ln.get("text") or ""),
                        "part": str(ln.get("part") or ""),
                    })
        except Exception as e:  # noqa: BLE001
            log.warning("规格书：这一段的台词取不到（按空处理）：%s", e)
        # 原片这一段说了什么（ASR 原声），按句子中点归段
        src_lines = []
        for x in speech:
            mid = (float(x.get("start") or 0.0) + float(x.get("end") or 0.0)) / 2.0
            if a <= mid < b:
                src_lines.append({"text": str(x.get("text") or "").strip()})
        segments.append({
            "index": n,
            "start": round(a, 3),
            "end": round(b, 3),
            "duration": round(b - a, 3),
            "cuts": cuts,
            "action": act or "",
            "targets": [str(t.get("id") or "") for t in (target or [])],
            "people": people,
            "lines": lines,
            "source_lines": src_lines,
            "look": (looks[n - 1] if n - 1 < len(looks) else "") or "",
            "audio": bool(plan.get("audio_ref")),
        })

    return {
        "model": str(plan.get("model") or ""),
        "channel": str(plan.get("ch") or ""),
        "source": {
            "duration": round(float(src.get("duration") or 0.0), 3),
            "width": int(src.get("width") or 0),
            "height": int(src.get("height") or 0),
            "fps": round(float(src.get("fps") or 0.0), 2),
        },
        "change": change,
        "refs": _refs_of(plan),
        "people": _people_of(plan),
        "segments": segments,
        # 「保什么」不在界面上问（P5）：默认就是**除点名的以外全部保持原样**。
        "keep": "除上面点名的修改对象外，原片里其他人物、道具、背景、动作、"
                "镜头运动、遮挡关系和事件顺序全部保持原样",
    }


def _fmt_sec(x: float) -> str:
    return f"{x:.2f}".rstrip("0").rstrip(".")


def as_text(brief: dict, *, body_lang: str = "中文",
            pic: str = "@图片{n}", audio: str = "@音频1") -> str:
    """把规格书摊成给模型读的中文清单。

    🩸 只陈述**事实**：不说"你应该怎么写"。怎么写由官方 skill 决定 ——
    这里多写一句"建议用五段式"，就等于我替官方定规矩了。

    🩸 2026-11-01：三处**标号写法**做成参数，因为两家的官方写法不同：
      · 火山 2.5 的正文是中文，标号是 `@图片N` / `@音频1`（默认值，行为不变）；
      · H3 的六段式正文是英文，标号是 `<Picture N>` / `<Audio 1>`（`h3_agent` 传另一套）。
    事实本身不分成两套 —— 只有"怎么称呼这些素材"随家变。
    """
    src = brief.get("source") or {}
    c = brief.get("change") or {}
    lines: list[str] = []
    lines.append("# 这次复刻的规格书")
    lines.append("")
    lines.append("## 原片")
    lines.append(f"- 时长 {_fmt_sec(float(src.get('duration') or 0))} 秒，"
                 f"{src.get('width')}×{src.get('height')}，"
                 f"{_fmt_sec(float(src.get('fps') or 0))} fps")
    lines.append("")

    lines.append("## 要改什么")
    changed = []
    if c.get("person"):
        who = "、".join(c.get("person_ids") or []) or "画面主角"
        changed.append(f"- 换人：{who} → 换成对应的人物参考图里的人")
    # 🩸 2026-11-01 主人：「人物那里是一定有参考图的，其他地方才有参考图或描述 2 选 1。」
    #   这一段的每一句都要能回答**换成什么**：有图就说图，没图必须说文字。
    #   口径照代码编译版（`edit_spec:1766-1772`）：有图 `换成图N里的产品` /
    #   没图 `换成 product_desc`。原来一律写"换成产品参考图里的东西"，
    #   没传图的那一单就是在骗 agent 去找一张不存在的图。
    _have = {str(r.get("slot") or "") for r in (brief.get("refs") or [])}
    if c.get("product"):
        tgt = c.get("product_target")
        what = f"「{tgt}」" if tgt else "画面里的产品"
        to = ("换成产品参考图里的东西" if "product" in _have
              else f"换成{c.get('product_desc') or '（没写换成什么）'}")
        changed.append(f"- 换产品：{what} → {to}")
    if c.get("scene"):
        changed.append("- 换场景：" + ("换成场景参考图里的环境" if "scene" in _have
                                       else (c.get("scene_desc") or "（没写换成什么）")))
    if c.get("wardrobe"):
        per = c.get("wardrobe_desc_by_id") or {}
        if per:
            for pid, desc in per.items():
                changed.append(f"- 换装：{pid} → {desc}" if desc else f"- 换装：{pid}")
        elif c.get("wardrobe_desc"):
            changed.append(f"- 换装：{c.get('wardrobe_desc')}")
        elif "wardrobe" in _have:
            changed.append("- 换装：换成服装参考图里的衣服")
        else:
            changed.append("- 换装：（没写换成什么）")
    if c.get("style"):
        changed.append(f"- 整体风格：{c.get('style')}")
    if not changed:
        changed.append("- 画面不改，只换声音")
    lines.extend(changed)
    lines.append("")
    lines.append(f"## 要保留的\n- {brief.get('keep')}")
    lines.append("")

    # 🩸 补充说明是用户自己写的一句话，代码编译版一直照拼（`edit_spec:1667`），
    #   规格书漏抄就等于 agent 版把它吞了。原样放，不加解释、不扩写。
    _ex = str(c.get("extra") or "").strip()
    if _ex:
        lines.append("## 用户补充说明（原样照做，不要改写或扩写）")
        lines.append(f"- {_ex}")
        lines.append("")

    lines.append("## 素材与编号（提示词里按这个编号引用）")
    for r in (brief.get("refs") or []):
        slot = r.get("slot")
        if slot == "source":
            lines.append(f"- 原片 = {r['role']}")
        elif slot == "audio":
            lines.append(f"- {audio} = {r['role']}")
        elif r.get("pic"):
            lines.append(f"- {pic.format(n=r['pic'])} = {r['role']}")
    # 🩸 风格参考**视频**没有图片编号，`refs` 里也不会出现它。
    #   不在这里说一句，agent 只当原片是唯一的视频。
    if c.get("style_video"):
        lines.append("- 另有一个**风格参考视频**（不是原片，标号自成一套）："
                     "只参考它的风格、色调与质感，不复制它的画面内容")
    # 🩸 2026-11-01 主人：「人物那里是一定有参考图的，其他地方才有参考图或描述 2 选 1。」
    #   上面只列了**有图**的槽位。勾了产品/场景/服装但没传图时，原来这里一个字不说，
    #   agent 会以为它也有一张图，去找一个根本不存在的 <Picture N>（或 @图片N）。
    _by_text = [
        # `product_target` 是"被换掉的那件"（定位词），"换成什么"是 `product_desc`
        ("产品", c.get("product_desc"), "product"),
        ("场景", c.get("scene_desc"), "scene"),
        ("服装", c.get("wardrobe_desc") or "、".join(
            f"{k}：{v}" for k, v in (c.get("wardrobe_desc_by_id") or {}).items()),
         "wardrobe"),
    ]
    _only_text = [(lab, str(v or "").strip()) for lab, v, key in _by_text
                  if c.get(key) and key not in _have and str(v or "").strip()]
    if _only_text:
        lines.append("")
        lines.append("## 只有文字、**没有**参考图的（提示词里没有对应的图号）")
        for lab, v in _only_text:
            lines.append(f"- {lab}：{v} —— 按这段文字写，不要引用图号")
        lines.append("")
    # 人物是唯一**必须**有图的槽位；走到这里说明上游把图弄丢了，先说出来别让
    # agent 拿原片的人顶替（那等于把换人悄悄变成不换）。
    if c.get("person") and "person" not in _have:
        lines.append("## ⚠️ 勾了换人，但这一单没有人物参考图")
        lines.append("- 换人**必须有参考图**（产品/场景/服装才可以只给文字）。"
                     "没有图就不要写换人，照实说明画面里是谁。")
        lines.append("")
    lines.append("")

    # 🩸 谁在说话（`speaker_ids`）：**只陈述事实** —— 名单外的人不开门。
    #   怎么发号（`(Sx)` / `<Subject N>`）是写法层的事，由各家官方 skill 决定，这里不写。
    _spk = [str(x) for x in (c.get("speaker_ids") or []) if str(x).strip()]
    if _spk:
        lines.append("## 说话的人")
        lines.append(f"- {'、'.join(_spk)}：名单外的人在画面里不开口")
        lines.append("")

    ppl = brief.get("people") or []
    if ppl:
        lines.append("## 原片里盘点到的所有人（id 只是本单内部编号）")
        for p in ppl:
            d = p.get("desc_zh") or p.get("desc_en") or "（没有外观描述）"
            ap = p.get("appears") or []
            when = ("；出现在 " + "、".join(f"{_fmt_sec(s)}–{_fmt_sec(e)} 秒"
                                          for s, e in ap)) if ap else ""
            lines.append(f"- {p.get('id')}：{d}{when}")
        lines.append("")

    lines.append("## 分段（每一段写一条独立的编辑指令，编号一一对应）")
    for seg in (brief.get("segments") or []):
        lines.append("")
        lines.append(f"### 第 {seg['index']} 段："
                     f"{_fmt_sec(seg['start'])}–{_fmt_sec(seg['end'])} 秒"
                     f"（{_fmt_sec(seg['duration'])} 秒）")
        # 🩸 画面内容放**最前面**：它是"这一段和上一段有什么不同"的唯一依据。
        #   放在段落末尾时，agent 会跳过它，两段写成同一句话（2026-10-31 实测）。
        look = str(seg.get("look") or "").strip()
        if look:
            lines.append(f"- 这一段画面（盘点时已看过，英文原文，看懂就行，"
                         f"**写指令用{body_lang}**）：{look}")
        cuts = seg.get("cuts") or []
        nshot = len(cuts) + 1
        if cuts:
            lines.append(f"- 段内切点：{'、'.join(_fmt_sec(x) + ' 秒' for x in cuts)}"
                         f"（相对本段起点），共 {nshot} 个镜头")
        else:
            lines.append("- 段内只有一个连续镜头")
        act = seg.get("action") or ""
        if act == "keep":
            lines.append("- 这一段：盘点到的修改对象不在画面里 → **原样保留，不发模型**")
        elif act == "text":
            lines.append("- 这一段：只改文案/声音，画面不改")
        elif seg.get("targets"):
            lines.append(f"- 这一段要改的对象：{'、'.join(seg['targets'])}")
        else:
            lines.append("- 这一段：按上面的「要改什么」执行")
        ppl_in = [p for p in (seg.get("people") or []) if p.get("present", True)]
        if ppl_in:
            lines.append("- 这一段画面里出现的人：")
            for p in ppl_in:
                lines.append(f"  - {p.get('id')}：{p.get('desc') or '（无外观描述）'}")
        ln = seg.get("lines") or []
        if ln:
            lines.append("- 这一段的台词：")
            for x in ln:
                who = f"{x.get('who')}：" if x.get("who") else ""
                lines.append(f"  - {who}{x.get('text')}")
        # 🩸 原片原声台词（ASR）：**和上面「这一段的台词」同源**（同一份 ASR），
        #   有 `lines` 时再列一遍就是同一句话写两次，模型会当成两句。
        #   只在 `lines` 为空（没有逐句时间）时兜底列一次。
        sl = [] if ln else (seg.get("source_lines") or [])
        if sl:
            lines.append("- 原片这一段原声说了（ASR）：")
            for x in sl:
                lines.append(f"  - {x.get('text')}")
        lines.append(f"- 这一段{'带' if seg.get('audio') else '不带'}原片音轨")
    return "\n".join(lines)
