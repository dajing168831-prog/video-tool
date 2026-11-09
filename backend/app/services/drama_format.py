"""商品短剧 · 结构化产物解析与渲染。

剧本 / 分镜由模型以 JSON 输出（格式定义在 product-drama 的 SOURCE.md）。
这里负责：剥围栏 → 解析 → 校验 → 渲染成人类可读的 markdown（前端展示用）。

结构化本体保留给判官与出片使用，**渲染结果仅供阅读**。
"""
from __future__ import annotations

import json
import re

FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.S)


class FormatError(ValueError):
    """模型输出不是可用 JSON，或关键字段缺失。"""


def _strip(text: str) -> str:
    t = (text or "").strip()
    t = FENCE_RE.sub("", t).strip()
    if not t.startswith("{"):
        i, j = t.find("{"), t.rfind("}")
        if i >= 0 and j > i:
            t = t[i : j + 1]
    return t


def parse_json(text: str) -> dict:
    """把模型回复解析成 dict；失败抛 FormatError（带原文片段便于排查）。"""
    raw = _strip(text)
    if not raw:
        raise FormatError("模型没有返回内容")
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        snippet = raw[:240].replace("\n", " ")
        raise FormatError(f"模型没按 JSON 输出（{e.msg} @第{e.lineno}行）：{snippet}") from e
    if not isinstance(obj, dict):
        raise FormatError(f"顶层不是对象，而是 {type(obj).__name__}")
    return obj


# ---------- 校验 ----------
def validate_card(obj: dict) -> list[str]:
    errs: list[str] = []
    for k in ("logline", "why_product"):
        if not (obj.get(k) or "").strip():
            errs.append(f"缺 {k}")
    beats = obj.get("beats")
    if not isinstance(beats, list) or len(beats) != 5:
        errs.append(f"beats 必须正好 5 拍，实际 {len(beats) if isinstance(beats, list) else '非数组'}")
    else:
        for i, b in enumerate(beats, 1):
            if not isinstance(b, dict):
                errs.append(f"第 {i} 拍不是对象")
                continue
            if not (b.get("what") or "").strip():
                errs.append(f"第 {i} 拍缺 what")
    hook = obj.get("hook")
    if not isinstance(hook, dict) or not (hook.get("type") or "").strip():
        errs.append("缺 hook.type（H1–H5 选一个）")
    if isinstance(obj.get("duration"), (int, float)) and obj["duration"] > 20:
        if not (obj.get("renew_point") or "").strip():
            errs.append("片长 >20 秒但缺 renew_point（R2 中段续命）")
    return errs


def validate_script(obj: dict) -> list[str]:
    errs: list[str] = []
    chars = obj.get("characters")
    scenes = obj.get("scenes")
    # 空数组合法：开箱测评这类「第一人称不出脸」的形态本来就没有角色（C6）
    if not isinstance(chars, list):
        errs.append("缺 characters（角色表；没有人物就写空数组 []）")
    else:
        for i, c in enumerate(chars, 1):
            if not isinstance(c, dict) or not (c.get("name") or "").strip():
                errs.append(f"角色 {i} 缺 name")
                continue
            for k in ("appearance", "identity"):
                if not (c.get(k) or "").strip():
                    errs.append(f"角色「{c['name']}」缺 {k}")
    if not isinstance(scenes, list) or not scenes:
        errs.append("缺 scenes（分场）")
    else:
        for i, s in enumerate(scenes, 1):
            if not isinstance(s, dict) or not (s.get("what") or "").strip():
                errs.append(f"第 {i} 场缺 what")
    return errs


#: 台词前的「角色名：」前缀（`嬷嬷：跪好了。` / `A：…；B：…`）——估算语音时长时要先剥掉
_SPEAKER_PREFIX_RE = re.compile(r"(^|[；;])\s*[^：；\n]{1,10}：")
#: 覆盖率比对时忽略的标点（模型常把句号换感叹号、把「」写成""，那不算改台词）
_PUNCT_RE = re.compile(r"[\s，。、；：！？…—\-「」『』“”‘’\"'()（）《》<>·]")


def _norm_line(text: str) -> str:
    return _PUNCT_RE.sub("", str(text or ""))


def _sayable(text: str) -> str:
    """剥掉角色名前缀后的纯台词（`嬷嬷：跪好了。` → `跪好了。`）。"""
    return _SPEAKER_PREFIX_RE.sub(r"\1", str(text or "")).strip()


def speech_seconds(text: str) -> float:
    """一句台词的语音时长。口径同配音（`drama_tts.estimate_speech_seconds`）。

    懒导入：`drama_tts` 顶层带 httpx，`drama_format` 是纯函数模块，不给它加依赖。
    导入不了就按 4.2 字/秒自己算（同一个数，见 `drama_tts.py:172`）。
    """
    t = _sayable(text)
    if not t:
        return 0.0
    try:
        from app.services.drama_tts import estimate_speech_seconds
        return float(estimate_speech_seconds(t))
    except Exception:  # noqa: BLE001
        cjk = len(re.findall(r"[㐀-鿿぀-ヿ가-힯]", t))
        latin = len(re.findall(r"[A-Za-z]+", t))
        return cjk / 4.2 + latin / 2.8


def validate_storyboard(obj: dict, want: float | None = None,
                        require_all_product: bool = False,
                        max_sec: float | None = None,
                        script_lines: list[str] | None = None) -> list[str]:
    """分镜校验。`want` = 目标片长（秒）；给了就要求合计时长对得上。

    🩸 2026-11-05 联调：片长 30s 却产出 13 镜（13×4s 最少也 52s），
    以前只查单镜 4–15s，**不查合计**，这种分镜能过校验，到出片规划才炸。
    单镜下限 4s 本身就限制了镜数，合计对不上说明镜数/时长算错了。

    🩸 2026-11-08（主人实测「剧本 8 句，出片只剩 3 句，看着一头雾水」）：
    分镜原来**允许随便丢台词、随便改台词**，只要时长对得上就算合格 ——
    于是剧本的 8 句被压成 3 句，连商品演示和收尾那句一起丢了，没人拦。
    现在补三条：
      · 台词覆盖率（`script_lines` 给了就必须逐句落到某个镜头上，同一条可以拆到多镜）
      · 台词念得完（全片台词秒数之和 ≤ 分镜合计时长）
      · 时长松紧线从 ±20% 放宽到 0.8–1.5 倍：**台词装不下就加时长，别删台词**
        （出片按型号自动分段，`model_specs` 里 2.5 单次 30 秒、其它型号 15 秒）
    """
    errs: list[str] = []
    shots = obj.get("shots")
    if not isinstance(shots, list) or not shots:
        return ["缺 shots（分镜）"]
    durs: list[float] = []
    for i, s in enumerate(shots, 1):
        if not isinstance(s, dict):
            errs.append(f"第 {i} 镜不是对象")
            continue
        sid = s.get("id", i)
        if not (s.get("description") or "").strip():
            errs.append(f"第 {sid} 镜缺 description")
        # 可选列：老分镜没有这一格也照常走（空 = 这一镜不上字）
        ost = s.get("on_screen_text")
        if ost is not None and not isinstance(ost, str):
            errs.append(f"第 {sid} 镜 on_screen_text 不是字符串")
        d = s.get("duration")
        top = float(max_sec) if max_sec else 15.0
        if not isinstance(d, (int, float)):
            errs.append(f"第 {sid} 镜 duration 不是数字")
        elif not (4 <= d <= top):
            errs.append(f"第 {sid} 镜 duration={d}s 不在 4–{top:g} 秒（C12）")
        else:
            durs.append(float(d))
    n_prod = sum(1 for s in shots if isinstance(s, dict) and s.get("product") is True)
    if require_all_product:
        # 「产品特写」模式要求商品 100% 出镜（drama_modes 的指令写死了这条）
        if n_prod < len(shots):
            errs.append(f"产品特写模式要求每镜都有商品，实际 {n_prod}/{len(shots)} 镜")
    elif n_prod * 2 < len(shots):
        errs.append(f"商品出镜 {n_prod}/{len(shots)} 镜，不足一半（C8）")
    if want and durs:
        total = sum(durs)
        lo, hi = want * 0.8, want * 1.5
        if total > hi:
            errs.append(
                f"分镜合计 {total:g} 秒，超过目标 {want:g} 秒的 1.5 倍（{hi:g} 秒）—— "
                f"台词太多或镜头太碎：删台词，或把片长调大再出"
            )
        elif total < lo:
            errs.append(
                f"分镜合计 {total:g} 秒，短于目标 {want:g} 秒的 0.8 倍（{lo:g} 秒）—— "
                f"镜头太少或时长写短了（单镜 4–{float(max_sec or 15):g} 秒）"
            )

    # 台词念得完：全片台词秒数之和不能超过分镜合计时长
    spoken = sum(speech_seconds(s.get("dialogue") or "") for s in shots
                 if isinstance(s, dict))
    if spoken and durs and spoken > sum(durs) + 0.2:
        errs.append(
            f"台词合计 {spoken:.1f} 秒，分镜合计只有 {sum(durs):g} 秒 —— 念不完。"
            f"加镜头/加时长，别删台词"
        )

    # 台词覆盖率：剧本每一句都要落到某个镜头上（可以拆到多镜，但不能丢、不能改写）
    if script_lines:
        full = [_norm_line(s.get("dialogue") or "") for s in shots if isinstance(s, dict)]
        joined = "".join(full)
        missing = [x for x in script_lines
                   if _norm_line(x) and _norm_line(x) not in joined]
        if missing:
            errs.append(
                "剧本里的台词没有全部落到镜头上，缺这 %d 句：%s —— "
                "每一句都必须逐字出现在某一镜的 dialogue 里（可以对拆到多镜、可以一镜两句，但不许删、不许改写）"
                % (len(missing), "／".join(f"「{x.strip()}」" for x in missing[:6]))
            )
    return errs


# ---------- 渲染 ----------
def _cell(v) -> str:
    return str(v if v is not None else "").replace("|", "｜").replace("\n", " ").strip()


#: C13 四禁（SOURCE.md RULES 表）里能用字面抓到的几类。
#: 只抓**确定**的写法，抓不准就不报 —— 提示不是判决，别拿假红刷屏。
_BAN_PATTERNS = (
    ("内心戏", re.compile(r"(想起|回忆起|犹豫|心想|暗自|心里想|决定要|忍不住想)")),
    ("否定式动作", re.compile(r"(没接住|没看|不理|不回|没有回头|没说|不看|不动)")),
    ("精确双人交互", re.compile(r"(击掌|碰杯|对抛|击拳|握手特写|互殴|拥抱特写)")),
    ("多步动作链", re.compile(r"(然后|接着|随后|紧接着)")),
    ("不可画的气氛", re.compile(r"(气氛紧张|氛围感|节奏加快|充满张力|情绪拉满)")),
)
#: 画面里「写字」的写法：SOURCE.md 产出 3 要求字一律进 on_screen_text 后期叠。
#: 只抓明确在说「画面上有字」的词，抓不准不报（避免把「印着产地」这种包装描述全算成错）。
_ONSCREEN_PAT = re.compile(
    r"(落字|大字|字卡|字幕|屏幕字|屏幕显示|画面显示|弹出.{0,4}字|写着|印着|标着|计时器红字)")
#: S1 用：商品动作词。同一动作在相邻两个商品镜里各拍一遍 = 穿帮。
_PROD_VERBS = ("拆", "打开", "拧", "撕", "倒", "挤", "喷", "掏出", "拿出", "举起", "递给")


def lint_storyboard(obj: dict) -> list[str]:
    """分镜「可生成性」提示（**不拦**，只标出来给人看）。

    判据出处：`SOURCE.md` RULES 表 C13（四禁）与 OUTPUT_STORYBOARD 的
    「剪辑三硬规则」S1/S2。S3（景别由信息决定）机器判不了，不做。
    """
    shots = [s for s in (obj.get("shots") or []) if isinstance(s, dict)]
    out: list[str] = []
    for s in shots:
        sid = s.get("id")
        desc = str(s.get("description") or "")
        for name, pat in _BAN_PATTERNS:
            hit = pat.search(desc)
            if not hit:
                continue
            if name == "多步动作链" and len(pat.findall(desc)) < 2:
                continue      # 只出现一次「然后」不算链
            out.append(f"第 {sid} 镜像「{name}」（{hit.group(1)}）：模型大概率拍不出来，换成可见的一步")
        # 画面里要出现的字 → 应该进 on_screen_text 由后期叠（SOURCE.md 产出 3）
        if not str(s.get("on_screen_text") or "").strip():
            hit = _ONSCREEN_PAT.search(desc)
            if hit:
                out.append(f"第 {sid} 镜画面里写了字（{hit.group(1)}），但 on_screen_text 是空的："
                           "把字挪到 on_screen_text，画面只拍物的样子")
    for a, b in zip(shots, shots[1:]):
        fa = (str(a.get("framing") or "").strip(), str(a.get("camera") or "").strip())
        fb = (str(b.get("framing") or "").strip(), str(b.get("camera") or "").strip())
        if fa[0] and fa[0] == fb[0] and fa[1] and fa[1] == fb[1]:
            out.append(f"第 {a.get('id')}、{b.get('id')} 镜景别和运镜都一样"
                       f"（{fa[0]}·{fa[1]}）：相邻两镜至少变一项（S2）")
        if a.get("product") and b.get("product"):
            pa = [v for v in _PROD_VERBS if v in str(a.get("description") or "")]
            pb = [v for v in _PROD_VERBS if v in str(b.get("description") or "")]
            same = sorted(set(pa) & set(pb))
            if same:
                out.append(f"第 {a.get('id')}、{b.get('id')} 镜都对商品做「{'、'.join(same)}」："
                           "关键动作只留一个主落实镜（S1）")
    return out


def render_card(o: dict) -> str:
    conf = o.get("conflict") or {}
    hook = o.get("hook") or {}
    cta = o.get("cta") or {}
    beats = [b for b in (o.get("beats") or []) if isinstance(b, dict)]
    out = [
        "【结构卡】",
        f"形态：{_cell(o.get('form')) or '情景短剧'}",
        f"片长：{_cell(o.get('duration'))} 秒 ｜ 场数：{_cell(o.get('scene_count'))}"
        f" ｜ 角色：{_cell(o.get('character_count'))} 人",
        f"商品角色：{_cell(o.get('role'))}",
        "",
        f"一句话故事：{_cell(o.get('logline'))}",
        "",
    ]
    # 对立面不一定是两个人（2026-11-08）：反转剧场 = 观众预期 ↔ 商品打脸的事实。
    # 写死「占上风/落败」会把每种形态都往两人对峙上带。
    if _cell(conf.get("side_a")) or _cell(conf.get("side_b")):
        out += [
            f"对立面：{_cell(conf.get('side_a')) or '—'} ↔ {_cell(conf.get('side_b')) or '—'}"
            f"—— 争的是 {_cell(conf.get('stake'))}",
            "",
        ]
    out += [
        f"开头策略：{_cell(hook.get('type'))}",
        f"  → 第一帧：{_cell(hook.get('first_frame'))}",
        "",
        "五拍落点：",
    ]
    for b in beats:
        out.append(f"  {_cell(b.get('no'))} {_cell(b.get('name'))}（{_cell(b.get('time'))}）：{_cell(b.get('what'))}")
    out.append("")
    if (o.get("renew_point") or "").strip():
        out += [f"中段续命点：{_cell(o.get('renew_point'))}"]
    out += [
        f"CTA 落点：约 70% → {_cell(cta.get('mid'))} ｜ 最后一镜 → {_cell(cta.get('final'))}",
        f"商品登场的理由：{_cell(o.get('why_product'))}",
    ]
    return "\n".join(out).rstrip()


def validate_card_custom(obj: dict) -> list[str]:
    """自定义形态的结构卡校验 —— **另一套，跟十种老形态互不影响**。

    主人 2026-11-07：「之前的规则我们不改动，但是我们新增一个自定义呀！」
    → 老的 `validate_card`（正好 5 拍 + 双人冲突）一个字不动；
    这里只要求故事讲得通：一句话故事、至少 3 拍、每拍有画面、商品非它不可。
    拍数 / 有没有对手 / 有没有 CTA，全交给顾客那段要求。
    """
    errs: list[str] = []
    if not (obj.get("logline") or "").strip():
        errs.append("缺 logline（一句话故事）")
    beats = obj.get("beats")
    if not isinstance(beats, list) or len(beats) < 3:
        errs.append(f"beats 至少 3 拍，实际 {len(beats) if isinstance(beats, list) else '非数组'}")
    else:
        for i, b in enumerate(beats, 1):
            if not isinstance(b, dict):
                errs.append(f"第 {i} 拍不是对象")
            elif not (b.get("what") or "").strip():
                errs.append(f"第 {i} 拍缺 what")
    if not (obj.get("why_product") or "").strip():
        errs.append("缺 why_product（为什么非这个商品不可）")
    return errs


def render_card_custom(o: dict) -> str:
    """自定义形态的结构卡渲染：**有什么渲染什么**。

    老卡那行「side_a（占上风）↔ side_b（落败）—— 争的是 …」是给对峙戏的，
    这里不拼它：顾客可能根本没有对手（物品视角 / 一段旅程 / 一个人的独白）。
    """
    beats = [b for b in (o.get("beats") or []) if isinstance(b, dict)]
    out = ["【结构卡 · 自定义】", "形态：自定义"]
    if _cell(o.get("role")):
        out.append(f"商品角色：{_cell(o.get('role'))}")
    out += ["", f"一句话故事：{_cell(o.get('logline'))}"]
    if _cell(o.get("first_frame")):
        out += ["", f"第一帧：{_cell(o.get('first_frame'))}"]
    out += ["", "拍子："]
    for b in beats:
        out.append(f"  {_cell(b.get('no'))} {_cell(b.get('name'))}"
                   f"（{_cell(b.get('time'))}）：{_cell(b.get('what'))}")
    if _cell(o.get("why_product")):
        out += ["", f"商品为什么非它不可：{_cell(o.get('why_product'))}"]
    return "\n".join(out).rstrip()


def render_script(o: dict) -> str:
    out = [f"# {_cell(o.get('title')) or '剧本'}", ""]
    logline = _cell(o.get("logline"))
    hook = _cell(o.get("hook"))
    if logline or hook:
        out.append(f"> {logline}" + (f"　｜　开头策略：**{hook}**" if hook else ""))
        out.append("")
    out += ["## 角色表", ""]
    for c in o.get("characters") or []:
        if not isinstance(c, dict):
            continue
        out.append(f"**【{_cell(c.get('name'))}】**　{_cell(c.get('identity'))}")
        for label, k in (("立场", "stance"), ("外观锚", "appearance"), ("弱点", "weakness")):
            v = _cell(c.get(k))
            if v:
                out.append(f"- {label}：{v}")
        out.append("")
    out += ["## 分场", ""]
    for s in o.get("scenes") or []:
        if not isinstance(s, dict):
            continue
        present = " / ".join(str(x) for x in (s.get("present") or []))
        head = f"### 第 {s.get('no', '?')} 场"
        for label, k in (("时间", "time"), ("地点", "location")):
            v = _cell(s.get(k))
            if v:
                head += f"　｜　{label}：{v}"
        if present:
            head += f"　｜　在场：{present}"
        out += [head, "", _cell(s.get("what"))]
        for ln in s.get("lines") or []:
            if isinstance(ln, dict) and (ln.get("text") or "").strip():
                out.append(f"- {_cell(ln.get('who'))}：「{_cell(ln.get('text'))}」")
        out.append(f"商品出镜：{'是' if s.get('product') else '否'}"
                   + (f"　｜　为什么不能删：{_cell(s.get('why'))}" if s.get("why") else ""))
        out.append("")
    return "\n".join(out).rstrip()


def render_storyboard(o: dict) -> str:
    rows = ["| # | 时长 | 景别 | 运镜 | 画面 | 台词 | 商品 | 为什么 |",
            "|---|---|---|---|---|---|---|---|"]
    for i, s in enumerate(o.get("shots") or [], 1):
        if not isinstance(s, dict):
            continue
        d = s.get("duration")
        dur = f"{d}s" if isinstance(d, (int, float)) else _cell(d)
        rows.append(
            "| {id} | {dur} | {fr} | {cam} | {desc} | {line} | {prod} | {why} |".format(
                id=_cell(s.get("id", i)),
                dur=dur,
                fr=_cell(s.get("framing")),
                cam=_cell(s.get("camera")),
                desc=_cell(s.get("description")),
                line=_cell(s.get("dialogue")),
                prod="是" if s.get("product") else "否",
                why=_cell(s.get("purpose")),
            )
        )
    total = sum(s.get("duration") or 0 for s in (o.get("shots") or [])
                if isinstance(s, dict) and isinstance(s.get("duration"), (int, float)))
    return "\n".join(rows) + f"\n\n合计 **{total:g} 秒** · {len(o.get('shots') or [])} 镜"
