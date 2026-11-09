"""H4 设置中心 —— 全局默认值 + 带版本号的迁移链（落 `data/drama/settings.json`）。

出处：clipforge `src/lib/stores/settings-store.ts:1-292`（`persist` + `version: 5` + `migrate`）。
竞品那边是浏览器 localStorage 的设置对象，5 个版本各对应一次线上事故
（`:139-158` 的注释逐版写了事故：失效模型名 / Pollinations 接口停用 / Windows localhost 解析 /
生产方案补齐 / Atlas 网关写错）。迁移函数本身是**纯函数**，可单测。

🩸 **五版事故史我们这边没有，不编。** 本工程的密钥一直走环境变量、没有持久化设置文件，
历史上不存在「旧版本写坏了值需要修」。所以这里落的是**机制**：
  · `SCHEMA_VERSION` 从 1 起；
  · `MIGRATIONS` 是「目标版本 → 迁移函数」的注册表，`migrate()` 按版本顺序跑；
  · 纪律（写进文件，不靠记）：**今后任何一次改默认值 / 改字段语义 / 改取值范围，
    必须 `SCHEMA_VERSION += 1` 并在这里登记一步，注释写清「哪次事故 / 日期」** ——
    与竞品同一条规矩，只是我们从 1 开始记。
能力表里 H4 记为「部分已做」就是这个原因：设置中心与迁移链在，五版历史不在。

我们的设置项（都对应真实存在的合成/配音参数，不做装饰性字段）：
  caption_preset / render_preset / transition / bgm_volume / bgm_duck / tts_voice
"""
from __future__ import annotations

import json
import math
import os
import re
import time
from pathlib import Path

SCHEMA_VERSION = 3

#: 成片三个全局默认（C12 真实感 / C9 接缝 / 分辨率）—— 新项目没单独存过就按这里来
FILM_RESOLUTIONS = ("720p", "1080p")
FILM_CHAINS = ("off", "tail")
FILM_REALISMS = ("auto", "constraints", "off")
#: 画面比例（三档照竞品 video 页；与 `drama_compose.RATIOS` 同一组值）
FILM_RATIOS = ("9:16", "16:9", "1:1")

DEFAULTS = {
    "caption_preset": "standard",
    "render_preset": "standard",
    "transition": "direct_concat",
    "bgm_volume": 0.18,
    "bgm_duck": True,
    "tts_voice": "zh-CN-XiaoxiaoNeural",
    "film_resolution": "720p",
    "film_ratio": "9:16",
    "film_chain": "off",
    "film_realism": "auto",
}
FIELDS = tuple(DEFAULTS)


def _v2_film_defaults(state: dict) -> dict:
    """v2（2026-11-06）：新增三个成片全局默认（分辨率 / 接缝 / 真实感）。

    旧设置文件没有这三个键 —— 别的项目要等用户自己去点，这里一次性补成默认值，
    让「没存过成片设置」的项目也能继承全局口径。缺什么补什么，已有的不动。
    """
    for k in ("film_resolution", "film_chain", "film_realism"):
        state.setdefault(k, DEFAULTS[k])
    return state


#: 目标版本 → 迁移函数。函数只改传进来的 dict，返回新 dict。
#: 加一步的模板（别删这段）：
#:     def _v3_fix_xxx(state: dict) -> dict: ...
#:     MIGRATIONS.append((3, _v3_fix_xxx))
#:     SCHEMA_VERSION = 3
def _v3_film_ratio(state: dict) -> dict:
    """v3（2026-11-07）：新增「画面比例」全局默认（主人问「生产那里没有选比例的吗」）。

    旧设置文件没有这个键 —— 补成 9:16，与改动前的行为逐字一致；
    已有值（手改过）不动。
    """
    state.setdefault("film_ratio", DEFAULTS["film_ratio"])
    return state


MIGRATIONS: list[tuple[int, object]] = [
    (2, _v2_film_defaults),
    (3, _v3_film_ratio),
]

MIN_BGM_VOLUME = 0.05
MAX_BGM_VOLUME = 0.4


class SettingsError(ValueError):
    """设置值不合法（人话）。"""


def _round2(v: float) -> float:
    """对齐前端/JS 的 `Math.round(x*100)/100`。"""
    return math.floor(v * 100 + 0.5) / 100


def _voice_ok(mod, voice: str) -> bool:
    """音色表是 `[{value,label},…]`，不是裸字符串列表。"""
    return any(str(x.get("value") or "") == voice for x in getattr(mod, "FREE_TTS_VOICES", []))


def default_state() -> dict:
    return {"version": SCHEMA_VERSION, **DEFAULTS}


def _clean_lenient(raw: dict) -> dict:
    """从磁盘读回来的值可能来自旧版本/手改：逐项校验，坏的**回落默认**而不是抛。"""
    out: dict = {}
    try:
        from app.services import drama_captions, drama_compose, drama_tts
    except Exception:  # noqa: BLE001 —— 纯逻辑探针在极简环境里也要能跑
        drama_captions = drama_compose = drama_tts = None

    cap = raw.get("caption_preset")
    if isinstance(cap, str) and (drama_captions is None or drama_captions.valid(cap)):
        out["caption_preset"] = cap
    rp = raw.get("render_preset")
    if isinstance(rp, str) and (drama_compose is None or rp in drama_compose.RENDER_PRESETS):
        out["render_preset"] = rp
    tr = raw.get("transition")
    if isinstance(tr, str) and (drama_compose is None or tr in drama_compose.TRANSITIONS):
        out["transition"] = tr
    vol = raw.get("bgm_volume")
    if isinstance(vol, (int, float)) and not isinstance(vol, bool) \
            and math.isfinite(float(vol)):
        out["bgm_volume"] = _round2(min(MAX_BGM_VOLUME, max(MIN_BGM_VOLUME, float(vol))))
    duck = raw.get("bgm_duck")
    if isinstance(duck, bool):
        out["bgm_duck"] = duck
    voice = raw.get("tts_voice")
    if isinstance(voice, str) and (drama_tts is None or _voice_ok(drama_tts, voice)):
        out["tts_voice"] = voice
    fr = raw.get("film_resolution")
    if fr in FILM_RESOLUTIONS:
        out["film_resolution"] = fr
    fa = raw.get("film_ratio")
    if fa in FILM_RATIOS:
        out["film_ratio"] = fa
    fc = raw.get("film_chain")
    if fc in FILM_CHAINS:
        out["film_chain"] = fc
    fz = raw.get("film_realism")
    if fz in FILM_REALISMS:
        out["film_realism"] = fz
    return out


def sanitize(patch: dict) -> dict:
    """用户主动改设置：**值不合法就报错**（比静默夹取更不容易让人以为生效了）。

    例外：`bgm_volume` 与竞品一致做夹取（0.05–0.4），因为滑块本来就允许越界一点。
    """
    if not isinstance(patch, dict) or not patch:
        raise SettingsError("没有要改的设置项")
    from app.services import drama_captions, drama_compose, drama_tts

    out: dict = {}
    for k, v in patch.items():
        if k not in DEFAULTS:
            raise SettingsError(f"不认识的设置项：{k}")
        if k == "caption_preset":
            if not isinstance(v, str) or not drama_captions.valid(v):
                raise SettingsError("字幕预设不认识")
            out[k] = v
        elif k == "render_preset":
            if not isinstance(v, str) or v not in drama_compose.RENDER_PRESETS:
                raise SettingsError("画质档不认识")
            out[k] = v
        elif k == "transition":
            if not isinstance(v, str) or v not in drama_compose.TRANSITIONS:
                raise SettingsError("转场不认识")
            out[k] = v
        elif k == "bgm_volume":
            if not isinstance(v, (int, float)) or isinstance(v, bool) \
                    or not math.isfinite(float(v)):
                raise SettingsError("BGM 音量要是数字")
            out[k] = _round2(min(MAX_BGM_VOLUME, max(MIN_BGM_VOLUME, float(v))))
        elif k == "bgm_duck":
            if not isinstance(v, bool):
                raise SettingsError("人声闪避只能是开/关")
            out[k] = v
        elif k == "tts_voice":
            if not isinstance(v, str) or not _voice_ok(drama_tts, v):
                raise SettingsError("配音音色不在免费音色表里")
            out[k] = v
        elif k == "film_resolution":
            if v not in FILM_RESOLUTIONS:
                raise SettingsError("成片分辨率只能是 720p / 1080p")
            out[k] = v
        elif k == "film_ratio":
            if v not in FILM_RATIOS:
                raise SettingsError("画面比例只能是 9:16 / 16:9 / 1:1")
            out[k] = v
        elif k == "film_chain":
            if v not in FILM_CHAINS:
                raise SettingsError("接缝默认只能是 关 / 续拍")
            out[k] = v
        elif k == "film_realism":
            if v not in FILM_REALISMS:
                raise SettingsError("真实感默认只能是 自动 / 仅约束 / 关")
            out[k] = v
    return out


def migrate(raw: dict | None) -> tuple[dict, list[str]]:
    """按版本链迁移 + 逐项校验。返回 `(state, applied)`，`applied` 是本次跑过的版本号。"""
    src = raw if isinstance(raw, dict) else {}
    try:
        ver = int(src.get("version") or 1)
    except (TypeError, ValueError):
        ver = 1
    state = {**DEFAULTS, **_clean_lenient(src)}
    applied: list[str] = []
    for target, fn in sorted(MIGRATIONS, key=lambda x: x[0]):
        if ver < int(target):
            state = fn(state) or state
            applied.append(f"v{int(target)}")
    state["version"] = SCHEMA_VERSION
    return state, applied


def load(path: Path) -> tuple[dict, list[str]]:
    """读设置文件；缺失/坏 JSON 都回落默认（并让调用方看到 `applied` 为空）。"""
    p = Path(path)
    if not p.exists():
        return default_state(), []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default_state(), []
    return migrate(raw)


def save(path: Path, state: dict) -> dict:
    """原子写入（临时文件 + rename），避免半截文件把设置读坏。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    body = {**state, "version": SCHEMA_VERSION,
            "updated": time.strftime("%Y-%m-%d %H:%M:%S")}
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)
    return body


# ---------------------------------------------------------------------------
# 旧版设置迁移（H4 的「五版」）
# ---------------------------------------------------------------------------
#
# 出处：clipforge `src/lib/stores/settings-store.ts:139-205`（`migrateSettings`）+
# `:270-278`（`version: 5` 每一版的注记）。那五版是**竞品的线上事故史**，我们这边没有
# （本工程密钥一直走环境变量）。这里把五条修复做成**可执行的导入迁移**：
# 用户从旧版（或竞品）把设置搬过来时，逐条把这些「装完看着正常、一生成就报错」的坏值修好。
#
# 🩸 每条都只在 baseUrl 命中对应官方端点时改写 —— 用户自建代理上的同名模型不许动
#    （`settings-store.ts:160` 原话「avoid collateral damage on self-hosted proxies」）。
LEGACY_MODEL_FIXES = (
    # v1：旧预设填过不存在的模型 ID；「测试连接」只验 Key 不验模型名，直到生成才报
    # Model Not Exist（issue #12）
    (r"api\.deepseek\.com", "deepseek-v3.2", "deepseek-v4-flash"),
    (r"volces\.com", "doubao-seed-2.0-pro", "doubao-seed-2-0-pro-260215"),
    (r"api\.atlascloud\.ai", "deepseek-ai/deepseek-v3.2", "deepseek-ai/deepseek-v4-pro"),
)
#: v2：Pollinations 免 Key 文本接口已停用（只回 402/502，issue #19）
POLLINATIONS_OLD_HOST = "text.pollinations.ai"
POLLINATIONS_BASE = "https://gen.pollinations.ai/v1"
#: v5：Atlas 的素材网关 `/api/v1` 被误写进 LLM 槽位 → 写脚本必 404（issue #24）
ATLAS_MEDIA_BASE_RE = re.compile(r"^https?://api\.atlascloud\.ai/api/v1/?$", re.I)
ATLAS_LLM_BASE = "https://api.atlascloud.ai/v1"
#: v4：旧设置没有生产方案 → 迁到兼顾质量与成本的 balanced
PRODUCTION_PROFILES = ("rapid", "balanced", "cinematic")
#: v3：Windows 上 localhost 先解析 ::1，而 Ollama 只监听 127.0.0.1（issue #19 追问）
OLLAMA_LOCALHOST_RE = re.compile(r"^(https?://)localhost(:11434\b)", re.I)


def _unwrap_legacy(raw) -> dict:
    """竞品是 zustand `persist` 的 `{state: {...}, version: n}`；也收裸对象。"""
    if not isinstance(raw, dict):
        return {}
    inner = raw.get("state")
    if isinstance(inner, dict):
        return inner
    return raw


def migrate_legacy(raw) -> dict:
    """跑竞品那五版修复。返回 `{state, fixed, source_version}`（纯函数，幂等）。"""
    src = _unwrap_legacy(raw)
    state = json.loads(json.dumps(src, ensure_ascii=False)) if src else {}
    fixed: list[str] = []
    try:
        ver = int((raw or {}).get("version") or 0) if isinstance(raw, dict) else 0
    except (TypeError, ValueError):
        ver = 0

    llm = state.get("llm")
    if isinstance(llm, dict) and isinstance(llm.get("baseUrl"), str):
        base = llm["baseUrl"]
        # v1：只在命中对应官方端点时改写模型名
        for host_re, old, new in LEGACY_MODEL_FIXES:
            if not re.search(host_re, base, re.I):
                continue
            if llm.get("model") == old:
                llm["model"] = new
                fixed.append(f"v1 模型名 {old} → {new}")
            if llm.get("visionModel") == old:
                llm["visionModel"] = new
                fixed.append(f"v1 看图模型 {old} → {new}")
        # v2：Pollinations 旧端点 → 新端点，并清掉占位 Key（新端点必须真 Key）
        if POLLINATIONS_OLD_HOST in base:
            llm["baseUrl"] = POLLINATIONS_BASE
            fixed.append("v2 Pollinations 停用接口 → 新端点")
            if llm.get("apiKey") == "pollinations":
                llm["apiKey"] = ""
                fixed.append("v2 清掉 Pollinations 占位 Key")
        # v3：localhost:11434 → 127.0.0.1:11434（同机同端口，无副作用）
        m = OLLAMA_LOCALHOST_RE.match(llm["baseUrl"])
        if m:
            llm["baseUrl"] = OLLAMA_LOCALHOST_RE.sub(r"\g<1>127.0.0.1\g<2>", llm["baseUrl"])
            fixed.append("v3 Ollama localhost → 127.0.0.1")
        # v5：Atlas 素材网关 → 聊天网关（顺序在 v2/v3 之后，避免互相覆盖）
        if ATLAS_MEDIA_BASE_RE.match(llm["baseUrl"]):
            llm["baseUrl"] = ATLAS_LLM_BASE
            fixed.append("v5 Atlas 素材网关 → 聊天网关")

    # v4：生产方案认不出 → balanced
    prof = state.get("activeProductionProfile")
    if prof is not None and prof not in PRODUCTION_PROFILES:
        state["activeProductionProfile"] = "balanced"
        fixed.append("v4 生产方案 → balanced")

    return {"state": state, "fixed": fixed, "source_version": ver}


def import_legacy(raw) -> dict:
    """旧设置 → 我们能用的那几个全局默认 + 一份人话报告。

    只搬**语义对得上**的项，其余如实列进 `dropped`（不假装搬成功了）：
      · `motionRealism` → `film_realism`（三档同名，C12）
      · `chainMode` → `film_chain`（`pin` 我们没有这条通道 → 落 `off`）
      · `defaultResolution` → `film_resolution`
      · `tts_voice` → 只有恰好是本产品免费音色表里的值才收（竞品存的是各家平台音色 id）
    """
    res = migrate_legacy(raw)
    state = res["state"]
    mapped: dict = {}
    dropped: list[str] = []

    realism = state.get("motionRealism")
    if realism in FILM_REALISMS:
        mapped["film_realism"] = realism
    elif realism is not None:
        dropped.append(f"motionRealism={realism}（认不出的真实感档）")

    chain = state.get("chainMode")
    if chain in FILM_CHAINS:
        mapped["film_chain"] = chain
    elif chain == "pin":
        mapped["film_chain"] = "off"
        dropped.append("chainMode=pin（钉下一镜关键帧这条通道我们没有 → 落 off）")
    elif chain is not None:
        dropped.append(f"chainMode={chain}（认不出的接缝档）")

    reso = state.get("defaultResolution")
    if reso in FILM_RESOLUTIONS:
        mapped["film_resolution"] = reso
    elif reso is not None:
        dropped.append(f"defaultResolution={reso}（只支持 720p / 1080p）")

    voice = state.get("tts_voice") or ((state.get("tts") or {}).get("voice")
                                       if isinstance(state.get("tts"), dict) else None)
    if isinstance(voice, str) and voice:
        try:
            from app.services import drama_tts

            if _voice_ok(drama_tts, voice):
                mapped["tts_voice"] = voice
            else:
                dropped.append(f"配音音色 {voice}（不是本产品免费音色表里的 id）")
        except Exception:  # noqa: BLE001
            dropped.append(f"配音音色 {voice}（音色表不可用，先不收）")

    for k in ("providers", "llm", "customModels", "imageParams", "videoParams",
              "defaultImageModel", "defaultVideoModel", "defaultAspectRatio",
              "spendCapUsd", "motionIntensity", "visualLook", "uiMode", "locale",
              "localeSource", "activeProductionProfile", "tts"):
        if k in state:
            dropped.append(f"{k}（本产品不走这项配置）")

    return {
        "settings": mapped,
        "fixed": res["fixed"],
        "dropped": dropped,
        "source_version": res["source_version"],
    }


def mask_key(value: str) -> str:
    """密钥只回掩码（前 4 + 后 4），绝不把整串发给前端。"""
    s = (value or "").strip()
    if not s:
        return ""
    if len(s) <= 8:
        return "已配置"
    return f"{s[:4]}…{s[-4:]}"
