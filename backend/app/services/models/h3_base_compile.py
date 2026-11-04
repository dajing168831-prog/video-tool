# -*- coding: utf-8 -*-
"""MiniMax H3 创作模式（T2VA / I2VA / FL2VA / L2VA）提示词编译器。

**与 `h3_compile.py`（手写入口三段式，改已有视频）并列、互不引用。**
标准文档：`docs/PROMPT-AUDIT-H3-BASE.md`（规则 B1–B36）。

为什么必须两个文件（2026-10-29 主人拍板「要分开」）：

| 维度 | `h3_compile.py`（改片） | 本文件（创作） |
|---|---|---|
| 官方依据 | `ref-en.txt`（341 行） | `base-en.txt`（222 行） |
| 结构 | 手写入口三段（参考素材说明 + 正文） | 三字段 |
| 🩸 风格句位置 | `[Shot 1]` **之前**（`ref-en:230`） | `[Shot 1]` **之内**（`base-en:78`） |
| 参考标号 | `@图片N` / `@视频N` / `@音频N`（手册标法） | 只有 `<Picture N>`（帧锚） |
| 内容自由度 | 只能写「谁换成谁」 | T2VA 官方允许补细节（`base-en:172`） |

依赖方向单向：本文件可以 import `h3_compile` 的台词工具（官方 `ref-en:9` 明写
「shot / camera / speaker / dialogue / sound 的基本格式与 base 模式共用」），
**`h3_compile.py` 一个字都不许反过来引用本文件**。
"""
from __future__ import annotations

import re

from app.services.model_specs import minimax as _specs
# 台词工具放中立文件 `h3_common.py`（两种模式共用，官方 `ref-en:9`）。
# 🩸 2026-10-29：原来直接 import `h3_compile`，被 `model_separation_check` 的
#   跨家引用门判红 —— 它把 `h3_base_compile` 当家名 `h3_base` 的另一家。
#   门判得对：共用件就该放中立文件，谁也不许认另一家的编译器。
from app.services.models.h3_common import _h3_line, _ucfirst

# ---------------------------------------------------------------- 结构与字段
#: `base-en:36-44`：三个字段，顺序固定。
FIELDS = ("integrated_multimodal_description",
          "overall_soundscape",
          "non_diegetic_music")

#: `h3-skill:11-14` 的五种模式；Ref2VA 归 `h3_compile`，不在本文件。
MODES = ("t2va", "i2va", "fl2va", "l2va")

#: 首期只放这两种（`PROMPT-AUDIT-H3-BASE §八`）。另外两类规则照建，
#: 但入口不开 —— 开口子之前先把 `last_frame` 的发送链路做出来。
MODES_LIVE = ("t2va", "i2va")

#: `api-create:407`「单个 `text` 最多 7000 个字符」。
TEXT_LIMIT = 7000


# ---------------------------------------------------------------- 开头指令行
#: `base-en:16-20`：I2VA 恒用这一句，逐字。
_I2VA = ("For the target video, at 0.00 seconds into the target video, "
         "<Picture 1> (from [Shot 1]) is fully referenced.")

#: `base-en:22-26`。🩸 官方示例里 `Picture 1` / `Picture 2` **不带尖括号**
#: （`base-en:25`），与另外三条不一致 —— 照抄，不"修正"。
_FL2VA = ("How the reference pictures align with the target video — "
          "Picture 1 (from Shot 1) aligns with the 0.00-second mark of the "
          "target video; Picture 2 (from Shot {n}) aligns with the "
          "{dur:.2f}-second mark of the target video.")

#: `base-en:28-32`。
_L2VA = ("How the reference pictures align with the target video — "
         "<Picture 1> (from [Shot {n}]) aligns with the {dur:.2f}-second "
         "mark of the target video.")


def instruction_line(mode: str, *, n_shots: int = 1, duration: float = 5.0) -> str:
    """开头那一行（`base-en:12-34`）。

    T2VA **没有**这一行（`base-en:14`：`begins directly with the three core fields`）。
    """
    m = (mode or "").strip().lower()
    if m == "t2va":
        return ""
    if m == "i2va":
        return _I2VA
    if m == "fl2va":
        return _FL2VA.format(n=max(1, int(n_shots)), dur=float(duration))
    if m == "l2va":
        return _L2VA.format(n=max(1, int(n_shots)), dur=float(duration))
    raise ValueError(f"不认识的模式：{mode!r}（只认 {' / '.join(MODES)}）")


# ---------------------------------------------------------------- 运镜词表
#: `base-en:98-111` 官方表格：**13 类 / 20 个具体词**。
#: ⚠️ 它叫「Available Expression」（可用表达），**不是白名单** —— 官方同一节还写着
#: `write camera movement as natural English`。所以这张表用来**生成**（把用户给的写法
#: 收口成官方词）和给 B14/B28 判**句子结构**，**不用来判"词不在表里就红"**。
#: （2026-10-30 撤回 B12，见 `docs/_archive/b12-withdrawn-2026-10-30.md`）
CAMERA_PHRASES = {
    "zoom in": "Zoom In", "zoom out": "Zoom Out",
    "push in": "Push In", "pull out": "Pull Out",
    "pan left": "Pan Left", "pan right": "Pan Right",
    "truck left": "Truck Left", "truck right": "Truck Right",
    "tilt up": "Tilt Up", "tilt down": "Tilt Down",
    "pedestal up": "Pedestal Up", "pedestal down": "Pedestal Down",
    "arc shot": "Arc Shot", "tracking shot": "Tracking Shot",
    "static shot": "Static Shot",
    "shake slightly": "Shake Slightly", "shake strongly": "Shake Strongly",
    "pov": "POV",
    "roll clockwise": "Roll Clockwise",
    "roll counterclockwise": "Roll Counterclockwise",
}

#: `base-en:92` 官方 5 种切镜动词（官方只在 Case 1 里用了 `the camera cuts to`）。
_CUT_VERBS = ("the camera cuts to", "the shot cuts to", "the shot transitions to",
              "the shot changes to", "the shot switches to")
_CUT_PREFIX = "the camera cuts to "


def _lower_first(s: str) -> str:
    """接在切镜动词后面的第一个词要小写（`…cuts to A close shot` 是错句）。"""
    if len(s) > 1 and s[0].isupper() and s[1].islower():
        return s[0].lower() + s[1:]
    return s


#: 幅度（`base-en:113-114`）与速度（`base-en:115`）—— 只许这两个值。
AMPLITUDE = {"small": "with small amplitude", "large": "with large amplitude"}
SPEED = {"slow": "at slow speed", "fast": "at fast speed"}

#: 运镜句的动词形态。
#:
#: 🩸 **这是工程推断，官方没有逐词给**：`base-en:98-111` 的表格是"名称 + 定义"，
#: 只给了 3 个完整句例（`:120-122`：`pushes in` / `pans right` / `holds a static shot`）。
#: 这里按那 3 句的形态，把另外 17 个词做同样的动词化 —— **只做语法变形，不改词**。
#: 依据不足的（`Arc Shot` / `Tracking Shot` / `POV`）取表格 Description 列的原话骨架。
_CAM_SENTENCE = {
    "Zoom In": "The camera zooms in",
    "Zoom Out": "The camera zooms out",
    "Push In": "The camera pushes in",
    "Pull Out": "The camera pulls out",
    "Pan Left": "The camera pans left",
    "Pan Right": "The camera pans right",
    "Truck Left": "The camera trucks left",
    "Truck Right": "The camera trucks right",
    "Tilt Up": "The camera tilts up",
    "Tilt Down": "The camera tilts down",
    "Pedestal Up": "The camera pedestals up",
    "Pedestal Down": "The camera pedestals down",
    # `base-en:106`：「The camera moves in an arc around the subject」
    "Arc Shot": "The camera moves in an arc",
    # `base-en:107`：「The camera follows a moving subject」
    "Tracking Shot": "The camera follows the subject",
    # `base-en:108` 例 `base-en:122`：「The camera holds a static shot」
    "Static Shot": "The camera holds a static shot",
    # `base-en:109`：「Slight / strong camera shake」
    "Shake Slightly": "The camera shakes slightly",
    "Shake Strongly": "The camera shakes strongly",
    # `base-en:110`：「The subject's point of view」
    "POV": "The camera adopts the subject's point of view",
    # `base-en:111`：「rolls clockwise / counterclockwise around the lens axis」
    "Roll Clockwise": "The camera rolls clockwise around the lens axis",
    "Roll Counterclockwise": "The camera rolls counterclockwise around the lens axis",
}


def camera_verbs() -> tuple[str, ...]:
    """官方 20 个运镜词的**动词形态**（小写、去掉 `The camera ` 前缀）——给尺子用。

    `follows` 单独补一条：Tracking Shot 带目标时写成 `The camera follows <目标>`
    （`base-en:107`「follows a moving subject」），目标替换掉默认的 `the subject`。
    这份动词表现在只给 **B28（运镜句要能读通）** 用 —— 不再用来判"词在不在表里"。
    """
    forms = [s.replace("The camera ", "", 1).lower() for s in _CAM_SENTENCE.values()]
    forms.append("follows")
    return tuple(forms)


def camera_type(value: str) -> str:
    """把用户/模型给的任意写法收口成官方那 20 个词之一；认不出 → 空串。

    认不出**不抛错、也不猜**：调用方据此判断"这一镜有没有运镜"。
    ⚠️ 认不出 ≠ 模型写错了（B12 已撤回，"不在表里"不是判红依据）。
    """
    k = re.sub(r"[\s_\-]+", " ", (value or "").strip().lower()).strip()
    return CAMERA_PHRASES.get(k, "")


#: 官方 `base-en:111`：Static Shot = 机位与镜头都不动 → 幅度/速度对它没有意义。
_NO_MOTION = {"Static Shot"}

#: 运镜句后接目标成分时用的连接词，**取自官方两句例句**（`base-en:122-124`）：
#:   `pushes in … toward the folded letter in her hands.` → toward
#:   `holds a static shot as the runner exits the frame.`  → as
#: 其余运动类型沿用 `toward`（官方只给了 push in 一例，属工程推断，记在此处备查）。
_CONNECTOR = {"Static Shot": "as"}
_CONNECTOR_DEFAULT = "toward"


def camera_sentence(cam: dict | str | None, *, target: str = "") -> str:
    """运镜 → 官方写法的一句话（`base-en:117-123`：写成句内自然英文，不堆标签）。

    ```text
    The camera pushes in with small amplitude at slow speed toward the letter.
    The camera holds a static shot as the runner exits the frame.
    ```
    幅度/速度**只在给了才写**（`base-en:96`：中等幅度与常速通常省略）。

    🩸 2026-10-29 三家真机对照抓到：以前 target 是**直接粘**上去的，产出
    `…at slow speed the man on the platform.` —— 缺连接词，读不通，而 22 条
    尺子一条都没拦住（它们只查词表，不查句子合法性）。现改为按上表补连接词。
    """
    if not cam:
        return ""
    if isinstance(cam, str):
        cam = {"type": cam}
    t = camera_type(str(cam.get("type") or ""))
    if not t:
        return ""
    out = _CAM_SENTENCE[t]
    if t not in _NO_MOTION:
        amp = AMPLITUDE.get(str(cam.get("amplitude") or "").strip().lower(), "")
        spd = SPEED.get(str(cam.get("speed") or "").strip().lower(), "")
        if amp:
            out += " " + amp
        if spd:
            out += " " + spd
    tail = (target or str(cam.get("target") or "")).strip()
    if tail and t == "Tracking Shot":
        # 官方 `base-en:107`：「The camera follows a moving subject」—— 目标本身就是
        # `follows` 的宾语，再补 toward 会变成「follows the subject toward the runner」。
        out = "The camera follows " + tail
    elif tail:
        out += " " + _CONNECTOR.get(t, _CONNECTOR_DEFAULT) + " " + tail
    return _ucfirst(out.rstrip(". ") + ".")


# ---------------------------------------------------------------- 台词
def dialogue_line(item: dict, speaker_id: str = "") -> str:
    """一句台词 → 官方写法。

    普通对白直接复用 `h3_compile._h3_line`（官方 `ref-en:9` 两种模式共用）。
    **画外音**（`base-en:136-140`）官方要求固定短语 `says in an off-screen voiceover`
    且**紧跟**一句"画内人物嘴唇紧闭" —— 那边是改片的形状、拿不到这个信号，
    所以 `_h3_line` 里没有这条分支，这里在它外面补，**不加进共用文件**。

    🩸 `speaker_id` 由 `compile_prompt` 按**目标片实际发声顺序**发号（`base-en:127`）。
    2026-10-29 校准抓到：以前把编号留给调用方，自己编出来是
    `The baker says, <d>…</d>` —— **没有 (S1)**，尺子 B19 当场判红。
    官方原文：「Place the speaker's identifying phrase, **ID**, action, and delivery
    outside `<d>`」——编号是必须的，不是可选的。
    """
    text = str(item.get("text") or "").strip()
    if not text:
        return ""
    who = str(item.get("who") or "").strip()
    sid = (speaker_id or str(item.get("speaker") or "")).strip()
    if sid:
        who = f"{who} ({sid})" if who else f"A voice ({sid})"
    lang = str(item.get("lang") or "zh").strip() or "zh"
    base = _h3_line(text, who, lang)
    if not base:
        return ""
    if not item.get("voiceover"):
        return base
    # `_h3_line` 恒定输出 `"{speaker} says, <d>…</d>"`（`h3_compile.py:219`）。
    # 只替换那句固定短语，`<d>` 里一个字不动。
    line = base.replace(" says, ", " says in an off-screen voiceover: ", 1)
    if line == base:                           # 形态对不上 → 不许静默发出去
        raise ValueError("画外音改写失败：说话句形态不是 `… says, <d>…</d>`")
    # 官方要的是「写明画内人物嘴唇紧闭」，没规定代词；不知道性别就不写 his/her。
    return line + " while the character's lips remain completely closed."


# ---------------------------------------------------------------- 组装
def _mmss(t: float) -> str:
    from app.services.edit_spec import _h3_mmss
    return _h3_mmss(t)


def _sentences(s: str) -> int:
    return len([x for x in re.split(r"(?<=[.!?])\s+|\n", (s or "").strip()) if x.strip()])


def compile_prompt(spec: dict) -> str:
    """创作规格 → 官方三字段提示词正文。

    规格形状（Step 3 的槽位抽取按这个填）：

    ```python
    {
      "mode": "t2va" | "i2va",          # 首期只这两种
      "duration": 5,                     # 整数秒
      "style": "Live-action, cinematic", # 放 [Shot 1] 之内（B15）
      "shots": [
        {"cut": None,                    # 第 1 镜不带；后续必须是秒数
         # 第 1 镜：完整句子（官方 `base-en:175`「a medium-wide shot frames …」）
         # 第 2 镜起：**名词短语**，因为编译器会在前面加 `the camera cuts to `
         #   （官方 `base-en:175` 示例就是 `…cuts to a close-up of steam rising…`）。
         #   写成"a close shot frames X"会和 cuts to 打架（`cuts to a close shot frames X`）。
         "body": "a medium-wide shot frames …",   # 画面与动作（用户的话）
         "camera": {"type": "Push In", "amplitude": "small",
                    "speed": "slow", "target": "toward the letter"},
         "dialogue": [{"who": "the baker", "lang": "zh",
                       "text": "第一炉好了。", "voiceover": False}]}
      ],
      "soundscape": "…",                 # 1–4 句
      "music": "…",                      # 1–3 句；空 → N/A
      "silence": False,                  # True = 用户明确要求全静音，才允许 soundscape 写 N/A
    }
    ```
    """
    if not isinstance(spec, dict):
        raise ValueError("创作规格必须是字典")
    mode = str(spec.get("mode") or "").strip().lower()
    if mode not in MODES:
        raise ValueError(f"不认识的模式：{mode!r}（只认 {' / '.join(MODES)}）")
    shots = spec.get("shots")
    if not isinstance(shots, list) or not shots:
        raise ValueError("至少要有一个镜头（`shots` 为空）")

    style = str(spec.get("style") or "").strip().rstrip(",")
    parts: list[str] = []
    # 说话人编号（`base-en:127`）：按**目标片实际发声顺序**一次性分配、全程复用；
    # 不发声的角色不给号。同一个人跨镜再说话要沿用同一个号。
    spk: dict[str, int] = {}
    for i, sh in enumerate(shots, 1):
        if not isinstance(sh, dict):
            raise ValueError(f"第 {i} 镜不是字典")
        body = str(sh.get("body") or "").strip()
        if not body and not sh.get("camera"):
            raise ValueError(f"第 {i} 镜既没有画面描述也没有运镜")
        if i == 1:
            head = "[Shot 1]"
            if style:
                body = f"{style}, {body}" if body else style
        else:
            cut = sh.get("cut")
            if cut is None:
                raise ValueError(f"第 {i} 镜缺切点秒数（`cut`）；`base-en:86` 要求逐镜递增")
            head = f"[Shot {i}] At {_mmss(float(cut))},"
            # 🩸 2026-10-29 穷举抓到：以前直接写 `[Shot 2] At 00:03.000, a close shot …`
            #   —— **没有切镜动词**。官方 `base-en:92` 给了 5 种固定动词，示例
            #   （`base-en:175`）是 `At 00:05.000, the camera cuts to a close-up of …`。
            #   用户已经写了动词就不重复加。
            if not any(v in body.lower()[:80] for v in _CUT_VERBS):
                body = _CUT_PREFIX + _lower_first(body)
        cs = camera_sentence(sh.get("camera"))
        # 🩸 2026-10-29 亲眼读产出抓到：`body` 没写句号时，后面接运镜会粘成
        #   「…before sunrise The camera pushes in…」—— 两句挤成一句；
        #   最后一镜没有后续子句时又会「…still water」（整段不收尾）。
        #   只补终止符，**不动 body 里一个字**。
        if body and body[-1] not in ".!?":
            body += "."
        clauses = [body] if body else []
        if cs:
            clauses.append(cs)
        for d in (sh.get("dialogue") or []):
            item = d if isinstance(d, dict) else {"text": str(d)}
            key = (str(item.get("who") or "").strip() or
                   f"voice{len(spk) + 1}")
            if key not in spk:
                spk[key] = len(spk) + 1
            line = dialogue_line(item, f"S{spk[key]}")
            if line:
                clauses.append(line)
        parts.append(f"{head} " + " ".join(clauses))

    desc = " ".join(parts).strip()
    sound = str(spec.get("soundscape") or "").strip()
    music = str(spec.get("music") or "").strip()

    text = (f"{FIELDS[0]}: {desc}\n\n"
            f"{FIELDS[1]}: {sound or 'N/A'}\n\n"
            f"{FIELDS[2]}: {music or 'N/A'}")
    instr = instruction_line(mode,
                            n_shots=len(shots),
                            duration=float(spec.get("duration") or 0) or _last_cut(shots))
    if instr:
        text = f"{instr}\n\n{text}"
    return text


def _last_cut(shots: list) -> float:
    """没给时长时，退到最后一个切点（只用于 FL2VA/L2VA 指令行的 S.SS）。"""
    cuts = [float(s.get("cut")) for s in shots
            if isinstance(s, dict) and s.get("cut") is not None]
    return (max(cuts) if cuts else 0.0) + 1.0


# ---------------------------------------------------------------- 请求参数
RATIOS = ("adaptive", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16")


def request_params(spec: dict, *, model: str = "MiniMax-H3") -> dict:
    """编译器出的提示词要配哪几个请求参数（`api-create:281-352`）。

    这几条是**顾客拿去粘贴时必须照填的**，写错就提交失败，所以在这里一次算好：

    · `duration` 整数秒，按型号档位夹紧（`api-create:294`）
    · `ratio`：T2VA **必填且不能 adaptive**；I2VA 恒 adaptive（`api-create:316`）
    · `resolution` 落在该型号支持的档位里（`api-create:281-292`）
    """
    s = _specs(model)
    mode = str(spec.get("mode") or "").strip().lower()
    dur = int(round(float(spec.get("duration") or s["min_sec"])))
    lo, hi = int(s["min_sec"]), int(s["max_sec"])
    dur = max(lo, min(hi, dur))

    res = str(spec.get("resolution") or "").strip()
    if res not in s["resolutions"]:
        res = s["default_resolution"]

    ratio = str(spec.get("ratio") or "").strip()
    if mode == "t2va":
        # 🩸 `api-create:316`：文生视频 `ratio` **必填**，且**不能为 adaptive**。
        if ratio == "adaptive" or ratio not in RATIOS:
            ratio = "16:9"          # 官方枚举里的中性默认，调用方可覆盖
    elif mode == "i2va":
        # 图生视频宽高比由图片决定，传别的会被忽略 → 只发官方认可的唯一值。
        ratio = "adaptive"

    # `api-create:316`：`MiniMax-H3-Lite` 暂不支持 adaptive。I2VA + Lite = 无解，
    # 交给调用方换型号；这里如实报出来，不静默改成别的比例（那会悄悄裁图）。
    warn = []
    if "-lite" in str(model).lower() and ratio == "adaptive":
        warn.append("MiniMax-H3-Lite 不支持 adaptive 宽高比；图生视频请换别的档位")

    return {"model": model, "resolution": res, "duration": dur,
            "ratio": ratio, "_warnings": warn}


def compile(spec: dict, *, model: str = "MiniMax-H3") -> dict:
    """一次出全套：正文 + 请求参数 + 提醒。"""
    text = compile_prompt(spec)
    params = request_params(spec, model=model)
    warn = list(params.pop("_warnings") or [])
    if len(text) > TEXT_LIMIT:
        warn.append(f"正文 {len(text)} 字符，超过官方上限 {TEXT_LIMIT}（`api-create:407`）")
    if not str(spec.get("soundscape") or "").strip() and not spec.get("silence"):
        warn.append("`overall_soundscape` 是 N/A —— 官方只在用户明确要求全静音时才用 N/A")
    if not str(spec.get("music") or "").strip():
        pass  # 没有画外配乐写 N/A 是正常形状（`base-en:162`），不算问题
    return {"text": text, "params": params, "warnings": warn}
