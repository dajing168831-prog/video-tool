"""话题起片（A6）—— 一句话主题 → 一条**没有商品**的内容向短视频脚本。

出处：竞品 `src/app/api/topic/script/route.ts:1-157`（一次性建项目 + 生成多条方案）
+ `src/lib/script-engine/prompts.ts:924-1100`（五种旁白风格指令、输出格式、批量要求）。

🩸 这是**另一个体裁**，不是带货短剧的一个开关：
   带货的 C1–C11（商品必须承担转折、C8 商品出镜过半……）在话题片上不成立。
   本文件独立一套规则，不复用 `BASE_SYS`、不注入品类模板、不走结构卡；
   提示词里明写「全程不得出现商品/价格/购买引导」（竞品 `prompts.ts:1073`）。

与竞品的四处不同（逐条有理由）：
  1. **时长下限**：竞品 15–40 秒、单镜可以 3 秒；我们出片接口单段最短 4 秒
     （火山 `min_sec=4`，`model_specs.py`），所以目标时长档改为 20/30/45/60，
     单镜 4–15 秒，否则生成的脚本根本进不了出片链路。
  2. **不要 searchTerms**：竞品每镜要英文检索词，是拿去素材库自动配画面的
     （`prompts.ts:918`）；我们走 AI 生成视频，没有素材库，这一栏收进来也没用处，
     只会让模型分心。改成要求「画面描述具体到能拍」。
  3. **不要求 3 秒钩子**：钩子的**内容**要求保留（第一镜必须是钩子），
     但时长跟着我们的 4 秒下限走。
  4. **落盘方式**：竞品写 scripts 表并删旧行；我们沿用本项目 A7 的版本栈
     （`doc["scripts"]` 保留历史，最多 12 版），不删旧稿。
"""
from __future__ import annotations

import re

#: 五种旁白风格（竞品 `prompts.ts:927-934` 的名称 + `:936-976` 的指令，逐字抽规则）
STYLES = {
    "knowledge": {
        "name": "知识科普",
        "directive": (
            "开头抛出一个反常识或让人好奇的问题/事实；中间用 3–5 个递进的小知识点把主题讲清楚，"
            "每个分镜一个点；语言准确但不掉书袋，多用「其实」「你可能不知道」等口语连接；"
            "结尾给一句可记住的总结金句。"
        ),
    },
    "story": {
        "name": "情感故事",
        "directive": (
            "用第一人称或第二人称叙事，开头是一个有代入感的瞬间；中间有情绪起伏"
            "（铺垫→转折→释然），让观众跟着走；画面以氛围、光影、生活细节为主，烘托情绪；"
            "结尾落到一句能引发共鸣的感悟。"
        ),
    },
    "lifestyle": {
        "name": "生活方式",
        "directive": (
            "像一段精致的生活 vlog 旁白，娓娓道来；展示一个具体的生活场景/流程/习惯的美好瞬间；"
            "画面注重质感与细节（手部动作、物件特写、自然光）；结尾是一句温柔的生活态度表达。"
        ),
    },
    "inspiration": {
        "name": "励志金句",
        "directive": (
            "节奏明快有力，每个分镜一句短而有冲击力的话；用对比、排比制造气势，"
            "画面大气（风光、奔跑、登顶、城市）；不空喊口号，结合具体画面让情绪落地；"
            "结尾一句点题的金句，适合被点赞收藏。"
        ),
    },
    "travel": {
        "name": "旅行风光",
        "directive": (
            "以目的地或风景为主角，旁白像一封写给某个地方的信；画面是地标、自然、人文细节的组合，"
            "节奏舒缓；旁白点出这个地方独特的氛围与值得去的理由；结尾留一句让人想出发的话。"
        ),
    },
}

#: 目标时长档（竞品是自由数字 15–40；我们给档位，因为单镜 4 秒下限）
DURATIONS = (20, 30, 45, 60)
DEFAULT_STYLE = "knowledge"
DEFAULT_DURATION = 30
MIN_COUNT, MAX_COUNT = 1, 5
MIN_SHOTS, MAX_SHOTS = 5, 9
MIN_SHOT_SEC, MAX_SHOT_SEC = 4.0, 15.0

SYSTEM = """你是短视频旁白编剧。你只写内容向的旁白脚本，不做带货。

铁律（违反任何一条都算失败）：
- 每一句旁白都是人话，读出来像真人说，不是文案腔、不是朗诵腔。
- 画面描述必须是能拍出来的一帧：地点、人物动作、光线；不写情绪、比喻、氛围词。
- 不编事实：主题里没有的数据、日期、人物、事件一律不写。
- 只输出要求的 JSON，不要解释、不要 markdown 代码块围栏。
"""


def public_styles() -> list[dict]:
    return [{"id": k, "name": v["name"], "directive": v["directive"]} for k, v in STYLES.items()]


def prompt(topic: str, style: str = DEFAULT_STYLE, duration: int = DEFAULT_DURATION,
           count: int = 3) -> str:
    """拼用户提示词（结构照竞品 `prompts.ts:1026-1078`，规则见文件头四处不同）。"""
    st = STYLES.get(style) or STYLES[DEFAULT_STYLE]
    n = max(MIN_COUNT, min(MAX_COUNT, int(count or 3)))
    head = (
        "请围绕下面这一句话主题，写竖屏短视频的旁白脚本（内容向，不是带货片）：\n\n"
        f"【主题】\n{topic.strip()}\n\n"
        "【基本要求】\n"
        f"- 旁白风格：{st['name']}\n"
        f"- 目标总时长：{int(duration)} 秒\n"
        "- 画幅：9:16 竖屏\n"
        f"- 分镜数量：{MIN_SHOTS}–{MAX_SHOTS} 个\n"
        f"- 单镜时长：{MIN_SHOT_SEC:g}–{MAX_SHOT_SEC:g} 秒，全部镜头时长之和要贴近目标总时长\n"
        "- 第一个分镜是钩子，最后一个分镜收束，中间递进\n\n"
        "【硬规则】\n"
        "- 全程不得出现商品、品牌、卖点、价格、优惠、购买或下单引导 —— 这不是带货片\n"
        "- 不编事实：主题里没有的数据、日期、人物、事件一律不写\n\n"
        f"【旁白风格要求】\n{st['directive']}\n\n"
        "【画面要求】\n"
        "- 景别写 全景 / 中景 / 近景 / 特写 之一\n"
        "- 运镜写 固定 / 缓推 / 跟拍 / 快切 之一\n"
        "- 画面描述写「谁 · 在哪 · 做什么 · 什么光线」，一帧能拍出来\n\n"
    )
    if n > 1:
        body = (
            f"【批量要求】\n请给出 {n} 个**切入角度明显不同**的方案：\n"
            "- 每个方案的开头钩子、叙事顺序、画面选择都要不一样\n"
            "- 不要只换同义词，要换讲法（比如一个从问题切入、一个从场景切入、一个从结论切入）\n\n"
            "只输出一个 JSON 对象（不要 markdown 围栏），格式：\n"
            '{"scripts":[{"title":"10 字以内","totalDuration":30,"shots":['
            '{"id":1,"duration":4,"framing":"中景","camera":"固定",'
            '"description":"画面：谁在哪做什么、什么光线","dialogue":"这一镜的旁白"}]}]}\n\n'
        )
    else:
        body = (
            "只输出一个 JSON 对象（不要 markdown 围栏），格式：\n"
            '{"title":"10 字以内","totalDuration":30,"shots":['
            '{"id":1,"duration":4,"framing":"中景","camera":"固定",'
            '"description":"画面：谁在哪做什么、什么光线","dialogue":"这一镜的旁白"}]}\n\n'
        )
    return head + body + (
        "字段规则：\n"
        "- duration 是数字（不带单位），所有分镜之和与 totalDuration 相差不超过 20%\n"
        "- framing / camera 只能取上面列出的词\n"
        "- dialogue 与 description 都不能为空\n"
        "- 字符串里不要出现英文双引号，引号用「」"
    )


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def validate(variant: dict, target: int | None = None) -> list[str]:
    """单个方案的硬校验（结构照 `drama_format.validate_storyboard` 的口径）。"""
    errs: list[str] = []
    shots = variant.get("shots")
    if not isinstance(shots, list) or not (MIN_SHOTS <= len(shots) <= MAX_SHOTS):
        return [f"分镜要 {MIN_SHOTS}–{MAX_SHOTS} 个，实际 {len(shots) if isinstance(shots, list) else 0}"]
    total = 0.0
    for i, s in enumerate(shots, 1):
        if not isinstance(s, dict):
            errs.append(f"第 {i} 镜不是对象")
            continue
        d = _num(s.get("duration"))
        if d is None or not (MIN_SHOT_SEC <= d <= MAX_SHOT_SEC):
            errs.append(f"第 {i} 镜时长 {s.get('duration')} 不在 {MIN_SHOT_SEC:g}–{MAX_SHOT_SEC:g} 秒")
        else:
            total += d
        if not str(s.get("description") or "").strip():
            errs.append(f"第 {i} 镜缺画面描述")
        if not str(s.get("dialogue") or "").strip():
            errs.append(f"第 {i} 镜缺旁白")
        if str(s.get("framing") or "") not in ("全景", "中景", "近景", "特写"):
            errs.append(f"第 {i} 镜景别「{s.get('framing')}」不在 全景/中景/近景/特写 里")
        if str(s.get("camera") or "") not in ("固定", "缓推", "跟拍", "快切"):
            errs.append(f"第 {i} 镜运镜「{s.get('camera')}」不在 固定/缓推/跟拍/快切 里")
    want = _num(target) or _num(variant.get("totalDuration"))
    if want and total and not (want * 0.8 <= total <= want * 1.2):
        errs.append(f"分镜合计 {total:g} 秒，与目标 {want:g} 秒相差超过 20%")
    if not str(variant.get("title") or "").strip():
        errs.append("缺 title")
    return errs


def split_variants(obj: dict, count: int) -> list[dict]:
    """兼容两种返回：`{"scripts":[...]}` 或单个方案对象（模型偷懒时）。"""
    if isinstance(obj.get("scripts"), list):
        return [x for x in obj["scripts"] if isinstance(x, dict)][:count]
    if isinstance(obj.get("shots"), list):
        return [obj]
    return []


def to_shots(variant: dict) -> list[dict]:
    """转成我们分镜的字段（下游 film/grid 全按这套字段走）。"""
    n = len(variant.get("shots") or [])
    out = []
    for i, s in enumerate(variant.get("shots") or [], 1):
        if not isinstance(s, dict):
            continue
        if i == 1:
            purpose = "钩子"
        elif i == n:
            purpose = "收束"
        else:
            purpose = "推进"
        out.append({
            "id": i,
            "duration": _num(s.get("duration")) or MIN_SHOT_SEC,
            "framing": str(s.get("framing") or "中景"),
            "camera": str(s.get("camera") or "固定"),
            "description": str(s.get("description") or "").strip(),
            "dialogue": str(s.get("dialogue") or "").strip(),
            "product": False,          # 话题片没有商品（C8 在本体裁不适用）
            "purpose": purpose,
        })
    return out


def name_of(topic: str) -> str:
    """竞品 `topic/script/route.ts:50-53`：一句话 → 项目名，超 20 字截断加省略号。"""
    t = re.sub(r"\s+", " ", (topic or "").strip())
    return f"{t[:20]}…" if len(t) > 20 else t
