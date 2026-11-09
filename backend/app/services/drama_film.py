"""商品短剧 · 分镜 → 出片提示词 / 出片计划（**纯计算，不发请求、不花钱**）。

结构来源：开源项目 **clipforge**（AGPL-3.0）的 `src/lib/storyboard-film.ts`
里的 `buildStoryboardFilmPrompt` / `referenceQuotaCheck` / `filmDurationFit`。
**只抽结构，不复制其代码**；句子顺序按它验证过的组织方式重写，
画面内容 100% 照抄分镜字段（description / framing / camera / dialogue），不自造一个词。

它的做法（本模块照此实现）：

  一次调用生成整片 —— 每镜的关键帧按顺序作为 @图片1..N，
  提示词逐行写时间码，模型在这些时间点硬切：

      [0.0-3.2秒] 镜头1（中景，画面以 @图片1 为基准）：她伸手拿起瓶身。运镜：缓推。台词（逐字说出）：{这也太快了吧}

  台词用 2.5 官方的 `{}` 语法（表示"要念出来"），与画面描述在 token 层分开。

三条前置闸（都来自它的实现，且都是**花钱前**能判的）：

  1. 单镜时长必须落在模型区间；
  2. 总时长超过模型单次上限 → 必须分段切，否则会**静默截尾**；
  3. 参考图张数超过模型上限 → 上游**必然**拒，白花钱。
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

from . import drama_looks, drama_realism

#: Seedance 2.5 单次生成上限（官方 `duration` = [4,30]）
FILM_CAP_SEC = 30.0
#: 兜底参考图上限（真正上限按型号取：2.5 = 30 张、2.0/H3 = 9 张）。
#: 取 9 是因为九宫格最多就 9 格；**别拿它当型号上限用**。
MAX_REFS = 9
#: 单镜可承载区间（product-drama 硬约束 C12 = 4–15s）
SHOT_MIN_SEC = 4.0
SHOT_MAX_SEC = 15.0

#: 台词密度上限 —— 判据抄自 clipforge `storyboard-film.ts:204-205`（**不是代码**）：
#: 脚本引擎本来就按 ~3 字/秒写，5 字/秒（中文）/ 2.6 词/秒（英文）是「物理上念不完」
#: 的线，只抓明显塞爆的镜头，不拿它去卡正常文案。
_ZH_CPS_MAX = 5.0
_EN_WPS_MAX = 2.6
_CJK = re.compile(r"[㐀-鿿぀-ヿ가-힯]")
_SPEAKABLE = re.compile(r"[^\W_]", re.UNICODE)  # 字母/数字/汉字，标点不计


def dialogue_warnings(shots: list[dict], names: list[str] | None = None) -> list[str]:
    """出片前算「这句台词在这个镜头里念得完吗」。**只在花钱前提醒，不阻断。**

    🩸 2026-11-08 加一条「一镜几个人说话」：一镜塞两个人的对白，4 秒里要先后
    说完本来就挤，模型还容易让两人一起开口（主人实测就是这样）。
    拆成两镜最稳，一镜一人一句。
    """
    out: list[str] = []
    for s in shots:
        line = str(s.get("dialogue") or "").strip()
        sec = float(s.get("duration") or 0)
        if not line or sec <= 0:
            continue
        parts = split_dialogue(line, names)
        if len(parts) > 1:
            who = "、".join(w or "?" for w, _ in parts)
            out.append(
                f"镜头 {s.get('id', '?')} 一镜里 {len(parts)} 个人说话（{who}）"
                f"，{_sec(sec)} 秒要按顺序说完 —— 建议拆成 {len(parts)} 镜，一镜一人一句"
            )
        if _CJK.search(line):
            n, limit, unit = len(_SPEAKABLE.findall(line)), math.ceil(sec * _ZH_CPS_MAX), "字"
        else:
            n, limit, unit = len(line.split()), math.ceil(sec * _EN_WPS_MAX), "词"
        if n > limit:
            out.append(f"镜头 {s.get('id', '?')} 台词 {n} {unit}，{_sec(sec)} 秒最多念 "
                       f"{limit} {unit} —— 会说不完/被截断，删字或加时长")
    return out


def price_estimate(seconds: float) -> dict:
    """花费估算。**没配单价就明说未知，绝不拿记忆里的价格凑数** —— 口径同
    `clone_pipeline` 的 `price` 块（`VT_PRICE_VIDEO_PER_SEC`，配置里写着「不填就
    显示未配置单价」）。"""
    from app.core.config import settings

    rate = float(getattr(settings, "price_video_per_sec", 0) or 0)
    if rate <= 0:
        return {"known": False, "amount": None, "currency": "CNY", "rate": 0,
                "seconds": round(seconds, 3),
                "note": "没配置单价（VT_PRICE_VIDEO_PER_SEC）—— 平台账单出来前不知道要花多少"}
    return {"known": True, "amount": round(rate * seconds, 2), "currency": "CNY",
            "rate": rate, "seconds": round(seconds, 3),
            "note": "按已配置单价 × 生成秒数估算，不承诺等于平台账单"}


def _plan_hash(segments: list[dict], model: str, resolution: str,
               ratio: str = "9:16",
               cast_images: list[str] | None = None,
               shot_mats: list[str] | None = None,
               clips: list[dict] | None = None) -> str:
    """确认卡锁的就是这份指纹 —— **只哈希「真正发给模型的东西」**：提示词、
    每段秒数、参考图张数、型号、分辨率档，以及**人物参考图 / 每镜参考画面的文件名**
    （换一张图，提示词一个字不变、画面却全变，必须算进指纹）。

    出处：clipforge `script/page.tsx:578`「dryRun must return the identical
    prompt (script edited in between → abort and re-preview)」—— 拿旧确认去付
    新提示词的钱，是这套流程里最贵的错。
    """
    payload = {
        "model": model,
        "resolution": resolution,
        # 换画幅 = 整片重裁（提示词里的画幅句也会变），必须进指纹
        "ratio": ratio,
        "cast": list(cast_images or []),
        "shot_mats": list(shot_mats or []),
        # 素材当画面：换一段素材，提示词一个字不变、成片全变 —— 必须进指纹
        "clips": [[int(c.get("shot_id") or 0), str(c.get("material") or ""),
                   round(float(c.get("seconds") or 0), 3)] for c in (clips or [])],
        "segments": [[int(s["no"]), round(float(s["seconds"]), 3),
                      int(s.get("prod_count") or 0), bool(s.get("board")),
                      str(s.get("prompt") or "")]
                     for s in segments],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def recheck(doc: dict, plan_hash: str, *, model: str, cap: float = FILM_CAP_SEC,
            max_refs: int = MAX_REFS,
            resolution: str = "720p", ratio: str = "9:16", chain: str = "off",
            realism: str = "auto") -> tuple[dict, str]:
    """付费前的二次 dryRun —— 返回 `(重算的计划, 错误)`；错误非空就**中止，不花钱**。

    🩸 这里重算用的是**现在的**文档，不是界面看过的那份存档：中间改过脚本/型号/
    时长，指纹就对不上，旧确认不能拿去付新提示词的钱（clipforge
    `script/page.tsx:578`）。返回的 `fresh` 才是应该真正发出去的那一版。
    """
    if not plan_hash:
        return {}, "缺 plan_hash —— 先在界面上看一眼这一版提示词和花费，确认后再出片"
    fresh = plan(doc, cap=cap, max_refs=max_refs, model=model, resolution=resolution,
                 ratio=ratio, chain=chain, realism=realism)
    if fresh.get("plan_hash") != plan_hash:
        return fresh, ("计划和你看的那一版不一样了（脚本/型号/时长改过）—— "
                       "重新规划并确认后再出片；本次没有提交、没有扣费")
    if fresh.get("errors"):
        return fresh, "出片计划有硬问题，先解决：" + "；".join(fresh["errors"][:3])
    return fresh, ""


#: 提示词里的画幅说法（2.0 系列要写进正文；2.5 不写，接口带参数）
RATIO_WORDS = {
    "9:16": "竖屏 9:16",
    "16:9": "横屏 16:9",
    "1:1": "方形 1:1",
}


def _sec(v: float) -> str:
    """秒数格式化：整数不带小数点，小数保留一位。"""
    return f"{v:g}"


def _norm(shots: list[dict]) -> list[dict]:
    """给每个镜头补一个整数 id —— 后面所有映射都按 id 走，不再靠临时下标。"""
    out = []
    for i, s in enumerate(shots, 1):
        if not isinstance(s, dict):
            continue
        try:
            sid = int(s.get("id") or i)
        except (TypeError, ValueError):
            sid = i
        out.append({**s, "id": sid})
    return out


def boards(doc: dict) -> list[dict]:
    """分镜板列表：≤30 秒一块；60 秒按出片段数一块一块出（2026-11-08）。

    老项目没有 `grid.boards` → 把 `grid` 本身当唯一一块板，行为与改动前一致。
    """
    g = doc.get("grid") or {}
    bs = g.get("boards")
    if isinstance(bs, list):
        out = [b for b in bs if isinstance(b, dict)]
        if out:
            return out
    return [g] if g else []


def _cell_map(board: dict) -> dict[int, int]:
    """**单块板**：镜头号 → 格号（1..9，对应 `cell_files` 的下标 +1）。

    一个镜头被画了多格时取**第一格**（那一格就是这一镜的画面基准）。
    """
    out: dict[int, int] = {}
    for c in ((board or {}).get("cells") or []):
        if not isinstance(c, dict):
            continue
        try:
            shot = int(c.get("from_shot"))
            idx = int(c.get("idx"))
        except (TypeError, ValueError):
            continue
        if 1 <= idx <= MAX_REFS and shot not in out:
            out[shot] = idx
    return out


def board_for(bs: list[dict], group: list[dict]) -> dict:
    """本段该带哪块板：覆盖本段镜头最多的一块（没人覆盖就用第一块）。

    🩸 60 秒片有两块板，格号在各自板上从 1 数起 —— 跨板合并不成立，
    必须按段选板，否则「第 7 格」可能指到另一块板的第 7 格。
    """
    if not bs:
        return {}
    ids = set()
    for i, s in enumerate(group, 1):
        try:
            ids.add(int(s.get("id") or i))
        except (TypeError, ValueError):
            ids.add(i)
    best, best_n = bs[0], -1
    for b in bs:
        n = len(ids & set(_cell_map(b)))
        if n > best_n:
            best, best_n = b, n
    return best


def _cell_of_shot(doc: dict, board: dict | None = None) -> dict[int, int]:
    """镜头号 → 格号。给了 `board` 就只看那块板；没给就是全片合并（老用法）。"""
    if board is not None:
        return _cell_map(board)
    out: dict[int, int] = {}
    for b in boards(doc):
        for k, v in _cell_map(b).items():
            out.setdefault(k, v)
    return out


def split_segments(shots: list[dict], cap: float = FILM_CAP_SEC) -> list[list[dict]]:
    """按模型单次上限把镜头切成若干段 —— **切点只能落在镜头边界**。

    贪心装箱：能塞进当前段就塞，塞不下就新开一段。
    单镜就超过 cap 的镜头直接报错（不该发生，C12 已限制到 15s）。
    """
    segs: list[list[dict]] = []
    cur: list[dict] = []
    cur_sec = 0.0
    for s in shots:
        d = float(s.get("duration") or 0)
        if d > cap:
            raise ValueError(f"镜头 {s.get('id')} 时长 {d:g}s 超过单次上限 {cap:g}s")
        if cur and cur_sec + d > cap + 1e-6:
            segs.append(cur)
            cur, cur_sec = [], 0.0
        cur.append(s)
        cur_sec += d
    if cur:
        segs.append(cur)
    return segs


def split_dialogue(line: str, names: list[str] | None = None) -> list[tuple[str, str]]:
    """把一镜的台词拆成 `[(说话人, 这句台词)]`，说话人拆不出来时给 `""`。

    🩸 2026-11-08：主人报「两个人一起说话，分不清谁在说」。盘上项目 7 镜里
    **4 镜的 dialogue 是两个人对白**（`掌柜：手拿开。镖师：我就要一盆凉水。`），
    而提示词只写「台词（逐字说出）：{原样}」——模型没有顺序也没有说话人，
    只能让画面上两个人一起开口。竞品同样要求逐句标说话人
    （clipforge `storyboard-film.ts:287-320`：多角色时每句写「，由XXX说出」）。

    `names` 只收剧本角色名：只有名字出现在句首或标点之后才算说话人，
    否则「掌柜的」这种呼语会被误判。
    """
    line = (line or "").strip()
    if not line:
        return []
    names = [n for n in dict.fromkeys(names or []) if n]
    if not names:
        return [("", line)]
    pat = re.compile("(" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
                     + r")\s*[：:]")
    marks: list[tuple[int, int, str]] = []
    for m in pat.finditer(line):
        pre = line[:m.start()].rstrip()
        if pre and pre[-1] not in "，,。；;、！？!?：:":
            continue
        marks.append((m.start(), m.end(), m.group(1)))
    if not marks:
        return [("", line)]
    out: list[tuple[str, str]] = []
    head = line[:marks[0][0]].strip(" ，,。；;、")
    for i, (_s, e, name) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(line)
        text = line[e:end].strip(" ，,。；;、\n")
        if i == 0 and head:
            text = f"{head}{text}" if text else head
        if text:
            out.append((name, text))
    return out


def _lines(shots: list[dict], cell_of: dict[int, int],
           mat_of: dict[int, int] | None = None, *,
           realism: str = "auto", category: str = "",
           characters: list | None = None) -> list[str]:
    """逐镜一行：`[起-止秒] 镜头N（景别，构图按分镜板第K格）：画面。运镜：xx。台词：{…}`

    `cell_of` = 镜头号 → **分镜板格号**（1–9，左上到右下）。
    🩸 2026-11-06：视频模型**只收整张板**（1 张），不再逐格上传裁出来的小图 ——
    所以这里只能按**格号**指构图，不能再写 `@图片N`（那套是按上传顺序编号的）。

    `mat_of` = **本段第几个镜头** → 该镜参考画面的 `@图片N` 编号（B4）。
    这里必须是段内序号：`镜头N` 本来就是本段序号，用全局镜头 id 会指错行。
    """
    out: list[str] = []
    cursor = 0.0
    for i, s in enumerate(shots, 1):
        d = float(s.get("duration") or 0)
        a, b = cursor, cursor + d
        cursor = b
        try:
            sid = int(s.get("id") or i)
        except (TypeError, ValueError):
            sid = i
        n = cell_of.get(sid)
        anchor = f"构图按分镜板第{n}格" if n else "画面按描述构建"
        ref = (mat_of or {}).get(i)
        if ref:
            # B4：这一镜有素材参考画面 —— 只借场景与道具，不借人脸（身份只认人物参考图）
            anchor += f"，场景与道具以 @图片{ref} 为准"
        fr = str(s.get("framing") or "").strip()
        head = f"[{_sec(a)}-{_sec(b)}秒] 镜头{i}（{fr + '，' if fr else ''}{anchor}）"
        desc = str(s.get("description") or "").strip().rstrip("。")
        cam = str(s.get("camera") or "").strip()
        cam_part = f"运镜：{cam}。" if cam else ""
        line = str(s.get("dialogue") or "").strip()
        # 台词用 2.5 官方 {} 语法；没有台词就明说"别出声"，否则模型会自己加对白。
        # 🩸 一镜里有两个人说话时必须**点名＋给顺序**，否则模型让两人一起开口
        # （主人 2026-11-08 报「两个人一起说话，分不清谁在说」）。
        names = [str(c.get("name") or "").strip()
                 for c in (characters or []) if isinstance(c, dict)]
        speaker = str(s.get("speaker") or "").strip()
        parts = split_dialogue(line, names) if line else []
        if not line:
            spoken = "（无台词，只保留环境音与动作声）"
        elif len(parts) == 1:
            who = parts[0][0] or speaker or (names[0] if len(names) == 1 else "")
            spoken = (f"台词（逐字说出，由「{who}」一人说出）：{{{parts[0][1]}}}"
                      if who else f"台词（逐字说出）：{{{parts[0][1]}}}")
        else:
            seq = "；".join(
                f"第 {k} 句由「{w or speaker or '画面对应的人'}」说：{{{txt}}}"
                for k, (w, txt) in enumerate(parts, 1))
            spoken = ("台词（按顺序、一人一句，同一时刻只允许一个人开口，"
                      f"禁止两人同时说话或齐声）：{seq}")
        # C12 真实感层：按用户选的档位逐镜追加（off 档返回空 = 提示词与老形状逐字一致）。
        # seed 用**段内 0 基下标**，与竞品 `beatSeed = assets.findIndex(...)` 同口径。
        real = drama_realism.extra_lines(
            s, index=i - 1, tier=realism, category=category, characters=characters)
        real_part = ("；".join(real) + "。") if real else ""
        out.append(f"{head}：{desc}。{cam_part}{real_part}{spoken}")
    return out


def product_pics(doc: dict) -> list[str]:
    """商品实拍图的文件名（使用者上传的顺序，**不重排**）。"""
    return [str(x) for x in ((doc.get("product") or {}).get("images") or []) if str(x).strip()]


def cast_pics(doc: dict) -> list[dict]:
    """人物参考图（`doc["cast"]`，按使用者上传的顺序）。

    广告分镜的口径：**分镜板只管构图，脸由人物参考图锁**
    （`D:/skills/commercial-storyboard/SOURCE.md:267/531/585`）。
    没传图的角色不进这个列表 —— 没图就按文字外观描述走，不假装有锚。
    """
    out: list[dict] = []
    for c in (doc.get("cast") or []):
        if isinstance(c, dict) and str(c.get("name") or "").strip() \
                and str(c.get("image") or "").strip():
            out.append({"name": str(c["name"]).strip(),
                        "image": str(c["image"]).strip()})
    return out


#: 每镜参考画面（B4）只收图片 —— 视频文件不能走参考图通道（火山参考图只收图）
MAT_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def shot_materials(doc: dict) -> dict[int, str]:
    """镜头 id → 素材库文件名（**一镜一张**）。

    出处：竞品 `api/project/[id]/stock-fill/route.ts` —— 每镜只落实一张已选素材
    （assets 表里 `selected` 每镜一条），并在整次填充里跨镜去重。
    我们照同一口径，不提供「一镜多张参考画面」（那样提示词里一镜指多图，语义会散）。

    `doc["shot_materials"]` 由 `PUT /projects/{id}/shot-materials` 写入；
    这里只做形状校验：id 不是整数、名字为空、不是图片、同一镜重复绑定 → 丢掉（先写为准）。
    文件是否真的存在由出片前的上传环节判（那里能报出人话）。
    """
    out: dict[int, str] = {}
    for it in (doc.get("shot_materials") or []):
        if not isinstance(it, dict):
            continue
        try:
            sid = int(it.get("shot_id"))
        except (TypeError, ValueError):
            continue
        name = str(it.get("material") or "").strip()
        if not name or Path(name).suffix.lower() not in MAT_IMAGE_EXT:
            continue
        if sid in out:
            continue
        out[sid] = Path(name).name
    return out


#: 「素材当这一镜的画面」只收视频（B6/B8 的下游；图片走 `shot_materials` 的参考图通道）
CLIP_VIDEO_EXT = {".mp4", ".webm", ".mov", ".m4v"}


def shot_clips(doc: dict) -> dict[int, str]:
    """镜头 id → 素材库视频文件名（**一镜一段**）。

    与 `shot_materials` 的区别（两条不同能力，别混）：
      · `shot_materials` = 图片，只当**场景参考**，画面仍由 AI 生成；
      · `shot_clips`     = 视频，**就是这一镜的画面**，从 AI 出片里拿掉、合成时插进时间线。

    出处：竞品 `api/project/[id]/stock-fill/route.ts` 把 stock 资产落到 shot 上、
    `video-composer/composer.ts:500-535` 按镜头时长铺素材（变速/补帧）。
    `doc["shot_clips"]` 由 `PUT /projects/{id}/shot-clips` 写入。
    """
    out: dict[int, str] = {}
    for it in (doc.get("shot_clips") or []):
        if not isinstance(it, dict):
            continue
        try:
            sid = int(it.get("shot_id"))
        except (TypeError, ValueError):
            continue
        name = str(it.get("material") or "").strip()
        if not name or Path(name).suffix.lower() not in CLIP_VIDEO_EXT:
            continue
        if sid in out:
            continue
        out[sid] = Path(name).name
    return out


def model_profile(model: str) -> dict:
    """按型号取提示词口径 —— **2.0 和 2.5 在官方标准里是相反的，不能共用一套**。

    · `param_free`（2.5）：画幅、总时长、分辨率、帧率、声音开关**不写进提示词**，
      由接口参数给（`sd25-pe.md:76` 原则 7「参数分离」）。判据同 `ark.omni_body`：
      `edit_duration == -1` 那档就是 2.5。
    · `fallback_pack`（2.0）：**必须**挂画质包 + 稳定包 + 水印/Logo 兜底，
      多人场景再挂双胞胎兜底（`sd20/skills/sd2-pe/SKILL.md:219`）。
      2.5 反过来，明令不得自动添加（`sd25-pe.md:77` 原则 8）。
    """
    from app.services import model_specs

    spec = model_specs.volc(model) if (model or "").strip() else {}
    return {
        "param_free": spec.get("edit_duration") == -1,
        "fallback_pack": bool(spec.get("auto_constraint")),
    }


_IMG_N_RE = re.compile(r"@图片(\d+)")
#: `build_prompt` 声明多张商品图时写的是**区间**「@图片2 至 @图片5」。
#: 🩸 2026-11-08：对账原来只抓单点，区间只抓到首尾两个号 → 商品图 ≥3 张时
#: 必报「声明 [1,2,5,6,7]，实际上传 7 张」的**假红**（实测 4 张商品图 + 2 个人物）。
#: 先把区间展开成逐个号，再做 1..N 的对账。
_IMG_RANGE_RE = re.compile(r"@图片(\d+)\s*至\s*@图片(\d+)")


def ref_numbers(prompt: str) -> list[int]:
    """提示词里声明用到的全部图号（区间按逐个号展开，去重升序）。"""
    text = prompt or ""
    nums: set[int] = set()
    for a, b in _IMG_RANGE_RE.findall(text):
        lo, hi = int(a), int(b)
        nums |= set(range(lo, hi + 1)) if lo <= hi else {lo, hi}
    for m in _IMG_N_RE.findall(_IMG_RANGE_RE.sub(" ", text)):
        nums.add(int(m))
    return sorted(nums)


def check_refs(prompt: str, uploaded: int) -> list[str]:
    """**素材对应声明**与实际上传顺序是否一致（不一致 = 锁错图，钱白花）。

    出处：clipforge `storyboard-film.ts:265` 提示词结构第 2 步是「素材对应声明」，
    理由写明「上传顺序 → 角色映射是参考图变多后的第一稳定因素」。
    我们已经在 `build_prompt` 里声明了 @图片N；这里是**对账**：
    声明里出现的图号必须正好是 1..uploaded，一个不多一个不少。
    """
    nums = ref_numbers(prompt)
    if uploaded <= 0:
        return [] if not nums else [f"提示词声明了图 {nums}，但这次一张图都不上传"]
    if not nums:
        return [f"提示词没有声明任何 @图片N，但会上传 {uploaded} 张图"]
    want = list(range(1, uploaded + 1))
    if nums != want:
        return [f"提示词声明的图号是 {nums}，实际上传 {uploaded} 张（应为 1–{uploaded}）"]
    return []


def build_prompt(doc: dict, shots: list[dict], *, cast: list[str] | None = None,
                 prod_pics: int = 0, model: str = "", board_pic: bool = False,
                 look: str = "", tail_ref: int = 0, genre: str = "",
                 shot_mats: list[dict] | None = None,
                 realism: str = "auto", ratio: str = "9:16",
                 cell_of: dict | None = None,
                 seg_no: int = 0, seg_total: int = 0) -> str:
    """把一组镜头拼成一段完整的出片提示词。

    `board_pic=True` = 本段最前面放**整张分镜板**（@图片1）。
    `prod_pics` = 商品实拍图张数（排在板后面，@图片2 起）。
    顺序必须和 `film/render` 的上传顺序逐字一致，否则模型锁错图。
    `model` 决定两处口径（见 `model_profile`）：2.5 不写参数、不挂兜底包；
    2.0 挂兜底包。空字符串 = 老行为（参数写进提示词、不挂包）。

    🩸 2026-11-06：**视频模型只收「整张板 + 商品图」，不再逐格上传裁出来的小图。**
    出处：广告分镜套件 `SOURCE.md:341`「分镜板图是例外——**整张传，别拆成单格**」，
    理由写明「2.0 参考图上限只有 9 张，拆开必超」。
    对标 clipforge 走的是另一条：它把九宫格**裁成 N 张逐镜喂**（
    `storyboard-film/route.ts:41-43`），所以它一镜一格、硬卡 9 镜。
    我们照广告分镜：板只有 1 张，各镜按「分镜板第 K 格」指构图。
    """
    total = sum(float(s.get("duration") or 0) for s in shots)
    chars = [c for c in ((doc.get("script_json") or {}).get("characters") or [])
             if isinstance(c, dict) and str(c.get("name") or "").strip()]
    cell_of = _cell_of_shot(doc) if cell_of is None else cell_of
    n_prod = max(0, int(prod_pics))
    base = 1 if board_pic else 0
    prod_first = 1 + base

    prof = model_profile(model)
    # 话题片（A6）不是带货片：体裁词换掉，且不写商品一致性（`content_type=topic`）
    kind = "短视频" if genre == "topic" else "带货短视频"
    blocks: list[str] = []
    if prof["param_free"]:
        # 2.5 原则 7：画幅/总时长不写进提示词，接口已经带了 ratio 和 duration
        blocks.append(
            f"UGC 手机实拍感{kind}，共 {len(shots)} 个镜头，"
            "严格按下面的时间段硬切，一次生成整片。"
        )
    else:
        # 2.0 系列要把画幅写进正文（接口也带 ratio，但正文说了模型更稳）。
        # 文案跟界面选的画面比例走，否则选 16:9 却写着「竖屏 9:16」= 自相矛盾。
        blocks.append(
            f"{RATIO_WORDS.get(ratio, RATIO_WORDS['9:16'])} UGC 手机实拍感{kind}，"
            f"总时长约 {_sec(total)} 秒，"
            f"共 {len(shots)} 个镜头，严格按下面的时间段硬切，一次生成整片。"
        )

    # 🩸 2026-11-08：长片是**分段独立生成**的（`plan()` 按镜头边界切段，每段一次
    # `omni_video`，`chain=off` 时连尾帧都不带）。原来的提示词只有一句「同一支视频」，
    # 段与段之间**一个字都没说**，模型每段都重新起镜 → 主人看到「34 秒剧情不连贯」。
    # 这里把本段在整片里的位置写进去，段间用文字锁住「接着上一段」。
    if seg_total > 1 and seg_no > 0:
        if seg_no <= 1:
            where = "本段是整片的**第 1 段**（共 {n} 段）：开场直接入戏，"
            where = where.format(n=seg_total) + "不要黑场、不要片头字卡。"
        elif seg_no >= seg_total:
            where = (f"本段是整片的**最后一段**（第 {seg_no} 段，共 {seg_total} 段）："
                     "第一镜必须紧接上一段最后一镜——同一场景、同一机位方向、"
                     "同一人物的位置与服装，动作从中途接着走，不要重新起镜、"
                     "不要换景别、不要重新构图；收尾停在最后一个动作上，不要拖尾。")
        else:
            where = (f"本段是整片的**第 {seg_no} 段**（共 {seg_total} 段），"
                     "两头都要接得上：第一镜紧接上一段最后一镜（同一场景、同一机位方向、"
                     "同一人物的位置与服装，动作从中途接着走，不要重新起镜、不要换景别），"
                     "最后一镜要给下一段留出可接的结尾画面。")
        blocks.append(where)

    # 素材对应（官方：先声明上传顺序 → 用途的映射，参考图一多这是第一稳定因素）
    head_bits: list[str] = []
    if board_pic:
        head_bits.append(
            "@图片1 是分镜板（整张九宫格分镜图），按从左到右、从上到下的顺序读；"
            "它定义全片的镜头顺序与大致构图，只借构图与主体位置，"
            "不复制板上画的文字、编号与格线"
        )
    # 商品名写进「素材对应」：一是让模型知道这是哪件商品，二是让视觉锚点
    # （`drama_bible` 的商品锚 = 商品名）能在提示词里被真正检查到。
    # 名字来自使用者填的商品资料，不是我们编的描述。
    pname = str((doc.get("product") or {}).get("name") or "").strip()
    prod_what = f"「{pname}」" if pname else "该商品"
    if n_prod == 1:
        head_bits.append(
            f"@图片{prod_first} 是{prod_what}的实拍图，商品外观、材质、颜色、logo 以此为准")
    elif n_prod > 1:
        head_bits.append(
            f"@图片{prod_first} 至 @图片{prod_first + n_prod - 1} 是{prod_what}的多角度实拍图，"
            f"商品外观、材质、颜色、logo 以此为准（几张图是同一件商品，不是不同款式）"
        )
    cast = [str(n).strip() for n in (cast or []) if str(n).strip()]
    if cast:
        cast_first = prod_first + n_prod
        who = "，".join(f"@图片{cast_first + i} 是「{n}」的人物参考图"
                        for i, n in enumerate(cast))
        head_bits.append(
            f"{who}（人物的脸、发型、服装只以参考图为准；"
            "分镜板只提供构图与机位，不要把板上的脸当成人物身份）"
        )

    # B4 每镜参考画面：排在人物参考图**之后、尾帧之前**（与 `film/render` 上传顺序一致）。
    # 编号由调用方算好（`plan` 里 mat_first 起顺延），这里只负责声明用途。
    for m in (shot_mats or []):
        head_bits.append(
            f"@图片{int(m['ref'])} 是本段镜头{int(m['no'])}的场景参考画面"
            "（场景、陈设、道具样式以它为准；参考图里的人物不算角色，"
            "人脸与服装只认人物参考图；不要复制它的文字与边框）"
        )

    if board_pic:
        head_bits.append("各镜的构图按分镜板对应格取，格号从左到右、从上到下数（1–9）")
    else:
        head_bits.append("本片不带构图参考图，画面全部按分镜描述构建。")
    blocks.append("素材对应：" + "；".join(head_bits))

    if chars:
        # 🩸 变量别叫 `cast`：上面 `cast` 是**人物参考图的名字列表**，
        # 这里一旦重名，下面「有没有参考图」的判断就永远为真（已踩过一次）。
        cast_desc = "；".join(f"{c.get('name')}（{c.get('appearance') or ''}）" for c in chars)
        blocks.append(
            f"人物设定（下文提到角色一律用角色名指代，外观以此为准；"
            f"台词与画面中的左/右一律指画面方向）：{cast_desc}。"
        )

    blocks.append(
        "全局一致性：所有镜头是同一支视频——同一人物、同一发型与同一身衣服、"
        "同一场景与光线方向"
        + ("。" if genre == "topic" else "；商品外观在所有镜头中保持完全一致。")
    )

    if cast:
        blocks.append(
            "人物参考图只作身份参考，不作为任何分镜画面；人物需自然融入各分镜自身的场景与光线，"
            "不得把参考图的背景、分格或边框带进任何镜头画面。"
        )

    blocks.append(
        "有台词的镜头：台词由该镜点名的那一个人说出来，原声逐字说出，口型与语速对齐，"
        "语气像日常聊天而不是播音腔；一镜里有两句对白时按写的先后说——"
        "一个人说完另一个人才开口，同一时刻只有一个人在说话，不许两人同时开口、不许齐声；"
        "轮到谁说话，画面与口型就给谁；没被点到说话的人闭着嘴听；"
        "无台词的镜头不要出现说话声。"
    )
    if prof["fallback_pack"]:
        # 2.0 强制兜底包（`sd2-pe/SKILL.md:219`）。画质包用手机实拍口径，
        # 不用官方默认的「电影质感」—— 本产品体裁就是手机带货实拍，换掉会变体裁。
        blocks.append(
            "画质与质感：真实手机直出质感，色彩自然未调色、带混合色温；"
            "人物肤质自然真实、保留毛孔细节不磨皮；构图带轻微手持感。"
        )
        if chars:
            blocks.append(
                "稳定包：人物面部稳定不变形、五官清晰、动作连贯自然，"
                "不僵硬，无穿模无卡顿。"
            )
    elif not prof["param_free"]:
        # 认不出型号时保持原样（不替未知型号做取舍）
        blocks.append(
            "画质与质感：真实手机直出质感，色彩自然未调色、带混合色温；"
            "人物肤质自然真实、保留毛孔细节不磨皮；构图带轻微手持感。"
        )
    if prof["fallback_pack"]:
        blocks.append("画面中不出现任何字幕、文字、编号或水印。不要字幕；不要生成水印；不要生成 Logo。")
    elif not prof["param_free"]:
        blocks.append("画面中不出现任何字幕、文字、编号或水印。不要字幕。")
    # 2.5 原则 8 明令不得自动挂字幕/水印/Logo 兜底 → 上面两句都不加
    if prof["fallback_pack"] and len(chars) >= 2:
        blocks.append(
            "视频全程禁止出现外形、着装、配饰完全一致的人物，禁止生成同款分身、双胞胎效果，"
            "同一画面中仅保留单个对应人物，不出现人物重复复刻。"
        )
    blocks.append("无bgm，只生成台词人声、环境音与动作音。")
    if tail_ref:
        # 续拍（C9）：官方给的用法是「上一段尾帧作为下一段首帧」（`ark.py:1018-1021`
        # 抄的就是这句）。严格的首帧模式与全模态参考**互斥**（`api-create-task.md:269`），
        # 二选一会丢掉分镜板/商品图；所以这里走**间接版**：尾帧当参考图 @图片N 挂上，
        # 提示词把它指成首帧（能力表 C9 附录-1 写的就是这条）。
        blocks.append(
            f"本段是续拍：@图片{tail_ref} 是上一段视频的真实最后一帧。"
            "本段第一帧必须与它严格连续——同一场景、同一机位、同一人物位置与服装，"
            "动作从这一帧接着往下走，不要重新起镜、不要换景别、不要重新构图。"
        )
    # 没有上传板时不能写「第 K 格」—— 模型手里没有那张板，会指向不存在的东西
    blocks.append(
        "分镜（括号里的格号是分镜板上的位置，构图以那格为准；人物与商品以外观为准）："
        if board_pic else "分镜："
    )
    mat_of = {int(m["no"]): int(m["ref"]) for m in (shot_mats or [])}
    # C12：品类只认建项表单的类目（唯一换算处 = drama_category_templates.resolve）
    category = drama_realism.get_category((doc.get("product") or {}).get("category"))
    blocks.extend(_lines(shots, cell_of if board_pic else {}, mat_of,
                         realism=realism, category=category, characters=chars))
    # 全局 Look（竞品 `look-presets.ts:15-18`）：
    #   · opener 只有 `real` 组有，**前置在最前**（他们实测：前置的「相机身份」短语
    #     比中段画质词更能把模型推向手机实拍分布）
    #   · motion 是短光锚，**加在最后**（动效提示词要镜头主导，长风格块会稀释动作）
    # 没选模板 = 两段都空 = 提示词与此前逐字一致。
    head = drama_looks.motion_prefix(look)
    tail = drama_looks.motion_suffix(look)
    text = "\n".join(b for b in blocks if b)
    if tail:
        text = f"{text}\n{tail}"
    return f"{head}\n{text}" if head else text


def plan(doc: dict, *, cap: float = FILM_CAP_SEC, max_refs: int = MAX_REFS,
         model: str = "", resolution: str = "720p", ratio: str = "9:16",
         chain: str = "off", realism: str = "auto") -> dict:
    """出片计划 —— **纯计算**。前端拿它显示"要花多少、发什么"，主人确认后才真提交。

    返回：
      segments  每段 {seconds, shots[], prompt, refs[]}
      warnings  能出但不理想的情况（没关键帧的镜头、要分段、参考图贴上限）
      errors    不能出的硬问题（时长为 0、超上限、参考图超限）
    """
    sb = doc.get("storyboard_json") or {}
    shots = _norm(sb.get("shots") or [])
    warnings: list[str] = []
    errors: list[str] = []
    # 接缝（C9）：off = 各段独立；tail = 第 2 段起把上一段真实尾帧当参考图锁首帧。
    # `pin`（钉下一镜关键帧当尾帧）我们不做 —— 每条片子只有一张分镜板、没有逐镜关键帧文件。
    if chain not in ("off", "tail"):
        chain = "off"
    # 体裁：话题片没有商品，出片提示词不能写「带货 / 商品一致」（A6）
    genre = str(doc.get("content_type") or "")
    # C12 真实感档：认不出的写法回 auto（竞品 `motion-prompt.ts:398` 同口径）
    realism = drama_realism.normalize_tier(realism)

    if not shots:
        errors.append("没有分镜，先出分镜")
        return {"segments": [], "warnings": warnings, "errors": errors}

    # ① 单镜时长
    for i, s in enumerate(shots, 1):
        d = float(s.get("duration") or 0)
        if d <= 0:
            errors.append(f"镜头 {s.get('id', i)} 没写时长")
        elif d < SHOT_MIN_SEC:
            warnings.append(f"镜头 {s.get('id', i)} 只有 {d:g}s，模型单次下限 {SHOT_MIN_SEC:g}s，会被拉长")
        elif d > SHOT_MAX_SEC:
            errors.append(f"镜头 {s.get('id', i)} 时长 {d:g}s 超过 {SHOT_MAX_SEC:g}s（C12）")

    # ② 构图基准：分镜板。**一张板只有 9 格**，60 秒最多 15 镜 → 按出片段各带一块板
    # （2026-11-08）。老项目只有一块板，这段行为与改动前逐字一致。
    bs = boards(doc)
    board_ok = [b for b in bs if str(b.get("image") or "").strip()]
    if board_ok:
        if len(board_ok) > 1:
            warnings.append(f"本片有 {len(board_ok)} 块分镜板，每段只带自己那块（格号按本段那块板数）")
        else:
            warnings.append("每段都带同一张分镜板（跨段共享构图锚，不额外花钱）")
        covered: set[int] = set()
        for b in board_ok:
            covered |= set(_cell_map(b))
        missing = [s["id"] for s in shots if s["id"] not in covered]
        if missing:
            warnings.append(
                f"{len(missing)} 个镜头在分镜板上没有对应格"
                f"（{', '.join(str(x) for x in missing[:9])}）——这些镜头只能按文字描述出"
            )
    elif genre != "topic":
        # 话题片本来就不出分镜板（九宫格要求 ≥3 个商品格），这条提醒对它没意义
        warnings.append("还没出分镜板图 —— 出片只能按文字描述，人物一致性会掉")
    used: set[int] = set()
    for b in board_ok:
        used |= set(_cell_map(b))

    # ③ 参考图张数 + 分段
    prod = product_pics(doc)
    n_prod = len(prod)
    if n_prod:
        warnings.append(f"每段会带上 {n_prod} 张商品实拍图（锁商品外观，不额外花钱）")
    cast = cast_pics(doc)
    n_cast = len(cast)
    if n_cast:
        warnings.append(
            f"每段会带上 {n_cast} 张人物参考图（{', '.join(c['name'] for c in cast)}）"
            "—— 脸、发型、服装以这组图为准，分镜板只管构图"
        )
    # 谁还没图：不拦，但把名字点出来（clipforge `script/page.tsx:603-627` 是「发现没图就现生」，
    # 我们出片是逐段确认、没有偷偷花钱的口子，所以改成**先提醒、由人点**）
    have = {c["name"] for c in cast}
    naked = [str(c.get("name") or "").strip()
             for c in ((doc.get("script_json") or {}).get("characters") or [])
             if isinstance(c, dict) and str(c.get("name") or "").strip()
             and str(c.get("name") or "").strip() not in have]
    if naked:
        warnings.append(
            f"{'、'.join(naked)} 还没有人物参考图 —— 这一段只能靠文字锁人，"
            "要稳就在「人物参考图」里给这几位传张照片或生成定妆照"
        )

    # B4：每镜参考画面（素材库图片，一镜一张）—— 按镜头 id 绑定，plan 重算不受影响
    mat_by_shot = shot_materials(doc)
    if mat_by_shot:
        known = {s["id"] for s in shots}
        stale = sorted(set(mat_by_shot) - known)
        if stale:
            warnings.append(
                f"{len(stale)} 个镜头配的参考画面绑到了不存在的镜头"
                f"（{', '.join(str(x) for x in stale[:9])}）—— 已忽略，重新绑一次"
            )
        n_mat_all = len([1 for sid in mat_by_shot if sid in known])
        if n_mat_all:
            warnings.append(
                f"{n_mat_all} 个镜头配了素材参考画面（只借场景与陈设，人脸仍以人物参考图为准，不额外花钱）"
            )

    # B6/B8：素材当画面的镜头 → **不进 AI 组**（AI 一次生成整段，中间挖掉一镜做不到），
    # 素材镜天然是段边界。按它把镜头序列切成若干 AI run，run 内再按单次上限装段。
    # 出处：竞品每镜独立取素材或生成（`composer.ts:500-535` 按镜头铺素材），我们的出片单元
    # 是「段」不是「镜」，所以只能用「素材镜切开段」来对齐同一语义。
    clip_by_shot = shot_clips(doc)
    if clip_by_shot:
        known = {s["id"] for s in shots}
        stale = sorted(set(clip_by_shot) - known)
        if stale:
            warnings.append(
                f"{len(stale)} 个镜头配的画面素材绑到了不存在的镜头"
                f"（{', '.join(str(x) for x in stale[:9])}）—— 已忽略，重新绑一次"
            )
        talking = [s["id"] for s in shots
                   if s["id"] in clip_by_shot and str(s.get("dialogue") or "").strip()]
        if talking:
            warnings.append(
                f"镜头 {', '.join(str(x) for x in talking[:9])} 配了实拍素材："
                "这几镜的台词不会出现在成片里（素材里没有这句话），字幕也不会烧"
            )
    units: list[dict] = []
    run: list[dict] = []
    for s in shots:
        name = clip_by_shot.get(s["id"])
        if name:
            if run:
                units.append({"kind": "ai", "shots": run})
                run = []
            units.append({"kind": "clip", "shot": s, "material": name})
        else:
            run.append(s)
    if run:
        units.append({"kind": "ai", "shots": run})

    segments: list[dict] = []
    clips: list[dict] = []
    timeline: list[dict] = []
    groups: list[list[dict]] = []
    try:
        for u in units:
            if u["kind"] == "clip":
                clips.append({
                    "shot_id": u["shot"]["id"],
                    "material": u["material"],
                    "seconds": round(float(u["shot"].get("duration") or 0), 3),
                })
                timeline.append({"kind": "clip", "shot_id": u["shot"]["id"],
                                 "material": u["material"],
                                 "seconds": round(float(u["shot"].get("duration") or 0), 3)})
                continue
            for group in split_segments(u["shots"], cap):
                timeline.append({"kind": "ai", "no": len(groups) + 1})
                groups.append(group)
    except ValueError as e:
        errors.append(str(e))
        return {"segments": [], "warnings": warnings, "errors": errors}

    if len(groups) > 1:
        warnings.append(
            f"AI 部分按镜头边界切成 {len(groups)} 段，出完按时间线顺序拼接"
            + (f"（另有 {len(clips)} 段实拍素材，不用出片）" if clips else "")
        )
    for gi, group in enumerate(groups, 1):
        secs = sum(float(s.get("duration") or 0) for s in group)
        # 本段用到的格号 —— **只是给人看的**（提示词按「分镜板第 K 格」指构图），
        # 不再作为独立参考图上传（广告分镜 SOURCE.md:341：整张传、别拆格）。
        # 本段带哪块板：60 秒有两块板时，段内所有镜头都在这块板上（格号也从这块数）
        seg_board = board_for(board_ok, group) if board_ok else {}
        board_pic = str(seg_board.get("image") or "").strip()
        cell_g = _cell_map(seg_board) if board_pic else {}
        cells = sorted({cell_g.get(s["id"]) for s in group if cell_g.get(s["id"])})
        n_board = 1 if board_pic else 0
        total_refs = n_board + n_prod + n_cast
        # B4 每镜参考画面：排在人物参考图之后，编号紧接 total_refs 顺延；
        # 顺序必须和 `film/render` 的上传顺序逐字一致（板 → 商品 → 人物 → 每镜画面 → 尾帧）。
        seg_mats: list[dict] = []
        for i, s in enumerate(group, 1):
            name = mat_by_shot.get(s["id"])
            if name:
                seg_mats.append({"no": i, "shot_id": s["id"], "material": name,
                                 "ref": total_refs + len(seg_mats) + 1})
        n_mat = len(seg_mats)
        # 续拍：本段末尾追加「上一段尾帧」一张（上传顺序 = 板上传完再尾帧，编号顺延）
        tail_ref = total_refs + n_mat + 1 if (chain == "tail" and gi > 1) else 0
        n_refs_used = total_refs + n_mat + (1 if tail_ref else 0)
        if n_refs_used > max_refs:
            errors.append(
                f"第 {gi} 段要 {n_prod} 张商品图 + {n_cast} 张人物参考图"
                f"{' + 1 张分镜板' if n_board else ''}"
                f"{f' + {n_mat} 张每镜参考画面' if n_mat else ''}"
                f"{' + 1 张上一段尾帧' if tail_ref else ''} = {n_refs_used} 张，"
                f"超过模型上限 {max_refs} 张 —— 删几张图或换支持更多参考图的型号"
            )
        segments.append({
            "no": gi,
            "seconds": round(secs, 3),
            "shot_ids": [s.get("id") for s in group],
            # 本段涉及的格号（1..9），界面上显示用；不上传
            "cells": cells,
            # 上传顺序：分镜板 → 商品图 → 人物参考图 → 每镜参考画面（与提示词编号同源）
            "board": bool(board_pic),
            # 本段用的是第几块板（1 起；单板片恒为 1）
            "board_no": int(seg_board.get("no") or 0),
            "prod_count": n_prod,
            "cast_count": n_cast,
            # 本段每镜参考画面：{no 段内镜号, shot_id, material 素材库文件名, ref 图片编号}
            "materials": seg_mats,
            "mat_count": n_mat,
            # 本段会带上谁的人物图（评分时要拿它当参考图对比，别再回头猜）
            "cast": [c["name"] for c in cast],
            # 本段实际上传的图张数（板 + 商品 + 人物 + 续拍尾帧）；出片前拿它对账声明
            "ref_count": n_refs_used,
            # 续拍尾帧的图片编号（0 = 本段不接上一段）
            "tail_ref": tail_ref,
            "prompt": build_prompt(doc, group, prod_pics=n_prod, model=model,
                                   board_pic=bool(board_pic), cell_of=cell_g,
                                   cast=[c["name"] for c in cast],
                                   look=drama_looks.look_of_doc(doc),
                                   tail_ref=tail_ref, genre=genre,
                                   shot_mats=seg_mats, realism=realism,
                                   ratio=ratio,
                                   seg_no=gi, seg_total=len(groups)),
        })

    if chain == "tail":
        warnings.append(
            "续拍模式：第 2 段起会把上一段的**真实尾帧**当参考图锁首帧（@图片N）—— "
            "必须按顺序出片；只重跑后面某段时，用的是盘上那一段已有的尾帧"
        )

    total = sum(float(s.get("duration") or 0) for s in shots)
    # 视觉记忆六锚 + 生成前一致性检查（clipforge `production-system.ts:119`）：
    # 缺锚只在界面上提示；「禁改」命中的一律 fail，付费接口看到 fail 直接拒。
    from app.services import drama_bible

    bible = drama_bible.effective(doc)
    bible_issues = drama_bible.issues_for([s["prompt"] for s in segments], bible)
    return {
        "segments": segments,
        # 素材当画面的镜头（不用出片，合成时按 `timeline` 的顺序插进时间线）
        "clips": clips,
        "timeline": timeline,
        "warnings": warnings,
        "errors": errors,
        "bible": bible,
        "bible_issues": bible_issues,
        "total_seconds": round(total, 3),
        "shot_count": len(shots),
        "ref_count": len(used),
        "prod_refs": prod,
        "cast_refs": cast,
        "board_ref": board_ok[0].get("image") if board_ok else "",
        # 本片共几块板（60 秒按段各一块；≤30 秒恒为 1）
        "board_count": len(board_ok),
        "cap_seconds": cap,
        "max_refs": max_refs,
        "model": model,
        "resolution": resolution,
        "ratio": ratio,
        "chain": chain,
        # C12 实际生效的真实感档（提示词已按它拼；档位进指纹靠 prompt 本身，不必单列）
        "realism": realism,
        # 付费前的确认凭证：界面上看到的就是这一版；出片时按同一算法重算，
        # 对不上就中止（一分钱不花）。
        "plan_hash": _plan_hash(
            segments, model, resolution, ratio,
            [c["image"] for c in cast],
            # 换一张同编号的素材图时提示词一个字不变 —— 素材文件名必须进指纹
            [f"{sid}:{mat_by_shot[sid]}" for sid in sorted(mat_by_shot)
             if sid in {s["id"] for s in shots}],
            clips,
        ),
        # 花费估算 + 台词密度，都摆进确认卡（没有单价就显示「未配置」，不猜）
        "price": price_estimate(total),
        "dialogue_warnings": dialogue_warnings(shots, [
            str(c.get("name") or "").strip()
            for c in ((doc.get("script_json") or {}).get("characters") or [])
            if isinstance(c, dict) and str(c.get("name") or "").strip()
        ]),
    }


def dump(obj: dict) -> str:
    """给前端/日志看的稳定 JSON（中文不转义）。"""
    return json.dumps(obj, ensure_ascii=False, indent=2)
