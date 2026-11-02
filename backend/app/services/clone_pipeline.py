"""复刻流水线：参考片 → 结构配方 → 新文案 → 成片。

两段式设计（先分析、后出片）：
  analyze() 只读原片，产出的配方可以无限次复用 —— 出 10 个变体只分析一次，
  这是成本能压下来的根本原因。
  render() 拿配方 + 新文案出片。

时间轴怎么对齐（这一版的做法，写清楚免得以后误以为在做别的事）：
  逐段 TTS → 每段音频时长已知 → 新时间轴 = 这些时长累加。
  如果新总长和原片差得多，用 atempo 把配音拉回原片时长（0.8–1.25 倍以内）。
  超出这个区间会明显失真，此时应该改写文案长度，而不是硬拉。
  V2 的做法是反过来重排镜头（切+拼），不在这一版里。
"""
from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

from app.services import (
    clone_store,
    compose,
    edit_spec as edit_spec_mod,
    identity,
    oss,
    pronounce as pronounce_mod,
    qc,
    recipe as recipe_mod,
    scene,
    speech_est,
    voice_catalog,
)
from app.services.providers import separate as separate_mod
from app.services.media import ffmpeg_path

log = logging.getLogger(__name__)


def _subject_gate(spec, channel: str, model: str) -> dict | None:
    """按**实际会用的型号**判人数。

    🩸 不能直接拿 `regen_model` 判：界面选「默认」时它是空串，而配置默认是
    Seedance 2.5（8 人）—— 空串去查表会落到 2.0 那档，把 5–8 人误拦。
    解析口径必须和真正发请求时同一处（`video_edit._model_for`）。
    """
    if not spec:
        return None
    from app.services import models, video_edit

    # 认不出的通道落回**默认通道**（问注册表，不再写死两家）
    fam = (channel or "").strip().lower()
    if fam not in models.adapters_by_family():
        fam = models.adapter_for(channel="").caps.family
    ch = fam
    return edit_spec_mod.subject_gate(spec, video_edit._model_for(ch, model))



def _cache_dir(cid: str, kind: str) -> Path | None:
    """任务级生成缓存目录。cid 不合法（测试里常见）就退化成不缓存。"""
    if not cid:
        return None
    try:
        return clone_store.task_dir(cid) / "cache" / kind
    except Exception:  # noqa: BLE001
        return None


def _inventory_or_none(cid: str) -> dict | None:
    """视觉盘点：看清原片里有几个人、各在第几秒。

    只花一次钱（结果按原片哈希缓存在任务目录里）；任何失败都返回 None，
    由调用方退回"整片套用一句提示词"的老行为。
    """
    from app.services import vision_plan

    if not vision_plan.available():
        return None
    try:
        inv = vision_plan.inventory(cid)
    except Exception as e:  # noqa: BLE001
        log.warning("视觉盘点失败，按老行为继续：%s", e)
        return None
    log.info("视觉盘点：%d 个人 / %d 个产品 / %d 个场景",
             len(inv.get("people") or []), len(inv.get("products") or []),
             len(inv.get("scenes") or []))
    return inv


_PUNCT = "。！？!?；;\n"


def analyze(
    video: Path,
    *,
    url: str = "",
    asr=None,
    workdir: Path,
    progress=None,
) -> dict:
    """读原片，产出结构配方。progress(stage, pct) 用来推前端进度。"""
    from app.services.providers.asr import get_asr

    workdir.mkdir(parents=True, exist_ok=True)
    asr = asr or get_asr()

    _p(progress, "probe", 10)
    info = scene.probe(video)

    _p(progress, "shots", 30)
    shots = scene.detect_shots(video)

    # 逐镜运动量：逐镜分诊靠它判断"这一镜的时间信息是不是重点"。
    # 纯 ffmpeg，几十个镜头也就几秒，比多送一段给视频模型便宜几个数量级。
    _p(progress, "motion", 40)
    for s in shots[:60]:
        try:
            s.motion = scene.motion(video, s.start, s.end)  # type: ignore[attr-defined]
        except Exception as e:  # noqa: BLE001
            log.warning("运动量计算失败 shot=%s: %s", s.index, e)
            s.motion = 0.0  # type: ignore[attr-defined]

    _p(progress, "speech", 55)
    windows = [(s.start, s.end) for s in shots]
    speech = asr.transcribe(video, windows=windows)
    # ASR 的 lang 是**调用方传进去的默认值**，不是它认出来的（一直是 zh）。
    # 英文原片因此一直被当中文：配音用中文音色、语速按中文估。这里按识别原文再判一次。
    if speech.get("has"):
        try:
            from app.services import speech_est

            text = "".join(str(s.get("text") or "")
                           for s in (speech.get("segments") or []))
            speech["lang"] = speech_est.detect_lang(text, speech.get("lang") or "zh")
            log.info("配音语言判定：%s（识别 %d 字）", speech["lang"], len(text))
        except Exception as e:  # noqa: BLE001
            log.warning("语言判定失败，沿用 %s：%s", speech.get("lang"), e)

    _p(progress, "keyframes", 80)
    kf_dir = workdir / "keyframes"
    for s in shots[:12]:  # 只抽前 12 镜给诊断卡用，够看风格
        try:
            p = scene.extract_frame(video, s.start + min(0.3, s.duration / 2),
                                    kf_dir / f"kf_{s.index:03d}.jpg")
            s.keyframe = p.name  # type: ignore[attr-defined]
        except Exception as e:  # noqa: BLE001
            log.warning("抽帧失败 shot=%s: %s", s.index, e)

    rec = recipe_mod.build_recipe(url=url, probe=info, shots=shots, speech=speech)
    for item in rec["shots"]:
        item["keyframe"] = f"kf_{item['i']:03d}.jpg"

    _p(progress, "done", 100)
    return rec


def _speech_ratio(rec: dict) -> float:
    """有声时长 / 总时长。只用来判「原片到底有没有人声」——
    ≤2% 就不必调分离接口（整轨本来就是背景）；场景自 2026-10-25 起固定 Drama，
    不再按这个比例挑场景（那正是把歌判成口播的原因，见 OPEN-DEFECTS D15）。
    """
    total = float((rec.get("source") or {}).get("duration") or 0)
    segs = (rec.get("speech") or {}).get("segments") or []
    if total <= 0:
        return 0.0
    spoken = sum(
        max(0.0, float(s.get("end") or 0) - float(s.get("start") or 0))
        for s in segs if (s.get("text") or "").strip()
    )
    return min(1.0, spoken / total)


def _separate_tracks(video: Path, rec: dict, workdir: Path):
    """把原片音轨拆成 voice / music / sfx，落盘后返回 ({轨: 路径}, 失败原因)。

    这是 C4 和我之前 mix 共用的那一步。**只做分离，不做取舍** ——
    哪些轨要留、哪些要丢由 `_audio_bed` 按开关决定。
    """
    # 先看盘上有没有跑过：写提示词之前就可能已经分离过一次（见 `_speech_present`），
    # 这里再调一次就是重复付费。放在所有配置检查之前 —— 复用本地文件本来就不需要服务。
    cached = {}
    for key, name in (("voice", "voice.wav"), ("music", "music.wav"),
                      ("sfx", "sfx.wav"), ("background", "background.wav")):
        p = workdir / "sep" / name
        if p.exists() and p.stat().st_size > 0:
            cached[key] = p
    if cached:
        log.info("人声分离复用已有音轨：%s", sorted(cached))
        return cached, ""

    if not separate_mod.available():
        return None, "未配置 MEDIAKIT_API_KEY（火山 AI MediaKit）"
    ratio = _speech_ratio(rec)
    if ratio <= 0.02:
        # 原片压根没有人声，整轨本来就是背景，没必要花这笔钱
        return None, "empty"
    if not oss.available():
        return None, "未配置 OSS（分离只收公网 URL）"

    try:
        url = oss.upload(video, prefix="sep")
        scene_name = separate_mod.SCENE
        res = separate_mod.separate(url, scene=scene_name)
        out_dir = workdir / "sep"
        out_dir.mkdir(parents=True, exist_ok=True)
        got: dict = {}
        for key, name in (("voice", "voice.wav"), ("music", "music.wav"),
                          ("sfx", "sfx.wav"), ("background", "background.wav")):
            if res.get(key):
                got[key] = separate_mod.download(res[key], out_dir / name)
        if not (got.get("music") or got.get("sfx") or got.get("background")
                or got.get("voice")):
            return None, "分离完成但没有可用音轨"
        log.info("人声分离完成：%s（scene=%s，语音占比 %.0f%%）",
                 {k: True for k in got}, scene_name, ratio * 100)
        return got, ""
    except Exception as e:  # noqa: BLE001
        log.warning("人声分离失败：%s", e)
        return None, str(e)[:200]


# voice 轨比原轨低这么多 dB ⇒ 这条片子里没有可分离的「对白」。
# 依据（2026-10-25 真机，OPEN-DEFECTS D15）：真说话片 voice ≈ 原轨（差 0.3–0.6 dB）；
# 唱歌片 Drama 分离出的 voice 比原轨低 32 dB 以上。间距很宽，但**样本只有 2 条**，
# 所以这是"够用就行"的阈值，不宣称准确率。判不出来（拿不到音量）一律返回 None。
NO_VOICE_GAP_DB = 20.0


def _mean_db(path: Path) -> float | None:
    """整轨平均音量（dB）。拿不到就返回 None —— 判据宁可不用，也不许瞎猜。"""
    ff = ffmpeg_path()
    if not ff or not path.exists():
        return None
    p = subprocess.run([ff, "-hide_banner", "-i", str(path), "-af", "volumedetect",
                        "-f", "null", "-"], capture_output=True, text=True, errors="ignore")
    for line in (p.stderr or "").splitlines():
        if "mean_volume:" in line:
            try:
                return float(line.split("mean_volume:")[1].strip().replace("dB", ""))
            except ValueError:
                return None
    return None


def _should_probe_voice(spec: dict | None, audio_mode: str, script,
                        has_audio: bool) -> bool:
    """要不要在**写提示词之前**先花 2 分钱判"这条片子里有没有对白"。

    只有"台词可能来自 ASR"的单子才值得：
      · 没有 spec（只换画面/沿用原声）→ 不用；
      · original → 本来就不写台词（D10 闸门）；
      · 用户自己填了文案 → 台词是他写的，不是歌词。
    其余（tts/mix 且沿用原片文案）→ 要判。原片没音轨也没得判。
    """
    if not spec or not has_audio:
        return False
    if (audio_mode or "tts").strip().lower() == "original":
        return False
    return not (script or "").strip()


def _speech_present(video: Path, rec: dict, workdir: Path):
    """原片里到底有没有「人声对白」。返回 (True/False/None, sep, err)。

    为什么要问这一步：唱歌的片子也会被 ASR 转出歌词，那些字不是台词。
    拿分离出来的 voice 轨能量跟原轨比，是现在唯一有真机证据的判据（D15）。
    None = 判不了（没配置 / 分离失败 / 拿不到音量）→ 调用方按老行为继续，
    **绝不因为判不了就改变出片行为**。
    """
    sep, err = _separate_tracks(video, rec, workdir)
    if not sep or not sep.get("voice"):
        return None, sep, err or "分离没有返回 voice 轨"
    v = _mean_db(sep["voice"])
    o = _mean_db(video)
    if v is None or o is None:
        return None, sep, "拿不到音量"
    gap = o - v
    log.info("人声判定：voice %.1f dB / 原轨 %.1f dB（差 %.1f dB，阈值 %.0f）",
             v, o, gap, NO_VOICE_GAP_DB)
    return gap < NO_VOICE_GAP_DB, sep, ""


def _audio_bed(video: Path, rec: dict, workdir: Path, spec: dict | None, *,
               total_sec: float, audio_files: dict | None = None,
               sep_pre: dict | None = None):
    """按 C4 的两个开关产出一条底音轨。返回 (bed, err)；err 非空 = 必须拦下。

    轨道取舍（`bgm` = keep/drop/replace，`sfx` = keep/add）：

      audio      bgm      取哪些轨
      ---------  -------  --------------------------------------------
      original   keep     不分离，原片整轨（老行为，零额外开销）
      original   drop     voice + sfx（**原对白必须留下**）
      mix        keep     music + sfx（老行为）
      mix        drop     sfx
      tts        *        原片轨一概不取
      任意       replace  丢掉原 music，混入用户上传的音乐
      任意       sfx=add  再叠一段用户上传的音效

    🩸 `bgm` 被点名要动、分离却跑不成时**不许静默退回原整轨** —— 用户以为
    BGM 已经删了，成片里还在响，这是"说一套做一套"。只有 `mix` 的老语义
    （用户没点名动 BGM）才允许退回，因为那时整轨也还凑合。
    """
    spec = spec or {}
    audio_mode = (spec.get("audio") or "tts").strip().lower()
    bgm = (spec.get("bgm") or "keep").strip().lower()
    sfx_mode = (spec.get("sfx") or "keep").strip().lower()
    files = audio_files or {}
    has_audio = bool((rec.get("source") or {}).get("has_audio"))
    # tts 模式原片声音一概不要，不值得为它花分离的钱
    need_sep = has_audio and (
        audio_mode == "mix"
        or (audio_mode == "original" and bgm != "keep")
    )

    parts: list[tuple[Path, float]] = []
    # `sep_pre` = 写提示词之前已经分离过的结果（只为判"有没有对白"跑的那次），
    # 这里直接复用，别再调一次接口付一次钱。
    sep = sep_pre
    sep_err = ""
    if need_sep and sep is None:
        sep, sep_err = _separate_tracks(video, rec, workdir)
        if sep is None and bgm != "keep" and sep_err != "empty":
            act = "去掉背景音乐" if bgm == "drop" else "换背景音乐"
            return None, (
                f"「{act}」需要先把原片的人声和背景音乐拆开，但分离服务没跑成"
                f"（{sep_err}）。现在出片只会有两种结果：背景音乐还在，"
                "或者连人声一起丢掉 —— 都不对。请改成「保留原片」，"
                "或先把分离服务配好。")

    if audio_mode == "original":
        if sep is None:
            # 没人声（整轨就是背景）或者分离失败：
            #   · bgm=keep → 还是原整轨（老行为）
            #   · bgm=drop/replace → 原轨整条不要（它就是那段背景音乐）
            if bgm == "keep" and has_audio:
                parts.append((video, 1.0))
        else:
            if sep.get("voice"):          # 原对白是内容，删 BGM 不能连它一起删
                parts.append((sep["voice"], 1.0))
            if sfx_mode in ("keep", "add") and sep.get("sfx"):
                parts.append((sep["sfx"], 1.0))
    elif audio_mode == "mix":
        if sep is None:
            parts.append((video, 1.0))    # 老行为：退回原片整轨
        else:
            if bgm == "keep":
                if sep.get("music"):
                    parts.append((sep["music"], 1.0))
                if sfx_mode in ("keep", "add") and sep.get("sfx"):
                    parts.append((sep["sfx"], 1.0))
            elif sfx_mode in ("keep", "add") and sep.get("sfx"):
                parts.append((sep["sfx"], 1.0))
            elif sep.get("background") and sfx_mode == "keep":
                parts.append((sep["background"], 1.0))
    # tts：原片轨道一概不取

    # 用户自己的素材
    out_dir = workdir / "sep"
    out_dir.mkdir(parents=True, exist_ok=True)
    if bgm == "replace" and files.get("bgm"):
        # 歌和原片几乎不可能一样长：循环/裁到成片时长，别半路没声或拖长成片
        try:
            fit = separate_mod.fit_loop(Path(files["bgm"]), out_dir / "bgm_fit.wav",
                                        total_sec)
            parts.append((fit, 1.0))
        except Exception as e:  # noqa: BLE001
            return None, f"背景音乐对齐到成片时长失败：{str(e)[:200]}"
    if sfx_mode == "add" and files.get("sfx"):
        # 音效按上传长度原样叠加，不循环 —— "加一段音效"不等于铺满全片
        parts.append((Path(files["sfx"]), 1.0))

    if not parts:
        return None, ""
    if len(parts) == 1:
        return parts[0][0], ""
    try:
        bed = separate_mod.merge([p for p, _ in parts], out_dir / "bed.wav",
                                 gains=[g for _, g in parts])
    except Exception as e:  # noqa: BLE001
        return None, f"底音轨混合失败：{str(e)[:200]}"
    log.info("底音轨=%s（audio=%s bgm=%s sfx=%s，%d 条源）",
             bed.name, audio_mode, bgm, sfx_mode, len(parts))
    return bed, ""


def _acts_or_empty(plan: dict, spans) -> dict:
    """预览用：盘点对不上时别抛错，按"没有分诊结果"处理。"""
    from app.services import video_edit

    try:
        return video_edit._span_plan(plan, spans)
    except Exception as e:  # noqa: BLE001
        log.warning("分段处理计划算不出（预览按无盘点处理）：%s", e)
        return {}


def _style_video_of(cid: str | None, spec) -> Path | None:
    """这一单有没有真的可用的风格参考视频（A9）。

    开关开着 + 文件在盘上，两个条件缺一不可：只有开关时提示词会写 @视频2，
    但那个素材根本没发出去 —— 模型只能自己编一段"风格"。
    """
    if not cid or not spec:
        return None
    if not ((spec.get("change") or {}).get("style_video")):
        return None
    from app.services import clone_store as store

    try:
        p = store.ref_video_path(cid, "style")
    except ValueError:
        return None
    return p if p.exists() else None


def _audio_files_of(cid: str | None) -> dict:
    """这一单盘上真实存在的 BGM / 音效文件（C4）。{kind: Path | None}。"""
    out: dict = {}
    if not cid:
        return out
    from app.services import clone_store as store

    for kind in store.REF_AUDIO_KINDS:
        try:
            p = store.ref_audio_path(cid, kind)
        except ValueError:
            continue
        out[kind] = p if p.exists() else None
    return out


def audio_preflight(spec: dict | None, audio_files: dict | None = None) -> str:
    """C4 出片前的零成本检查：要动背景音乐、但分离条件不成立 → 返回拦截话术。

    🩸 必须在这里拦：分离是在**模型跑完之后**的合成阶段做的。等那时候才发现
    没配分离服务，钱已经花掉了，片子还出不来。
    """
    if (spec or {}).get("bgm", "keep") == "keep":
        return ""
    if not separate_mod.available():
        return ("「去掉/更换背景音乐」需要先分离原片音轨，但火山 AI MediaKit 的 "
                "key 没配（MEDIAKIT_API_KEY）。现在出片会是原 BGM 还在。"
                "请改成「保留原片」，或先把分离服务配好。")
    if not oss.available():
        return ("「去掉/更换背景音乐」需要把人声分离出来，而分离只收公网 URL，"
                "但 OSS 没配。现在出片会是原 BGM 还在。请改成「保留原片」，"
                "或先把 OSS 配好。")
    if (spec or {}).get("bgm") == "replace" and not (audio_files or {}).get("bgm"):
        return ("选了「换成我上传的背景音乐」却没上传音乐文件："
                "没有文件时成片还是原片的背景音乐。")
    return ""


def _auto_decision(video: Path, rec: dict, *, spec, regen_prompt: str,
                   regen_shots: list[int] | None, regen_channel: str,
                   regen_model: str, subject_image: Path | None,
                   subject_asset: str, refs: dict | None, inventory: dict | None,
                   audio_mode: str, speech_spans: list[tuple[float, float]],
                   style_video: Path | None = None):
    """逐镜分诊的全部决策（纯本地：不调模型、不花钱）。

    render 和 preview_render 共用这一份 —— 预览和真跑要是各算各的，
    用户看到的数字就不可信了。
    """
    from app.services import triage, video_edit

    shots = rec.get("shots") or []
    src_total = float((rec.get("source") or {}).get("duration") or 0)
    plan = video_edit.prepare(
        rec, prompt=regen_prompt, spec=spec, refs=refs,
        subject_image=subject_image, subject_asset=subject_asset,
        channel=regen_channel, model=regen_model, inventory=inventory,
        style_video=style_video,
    )
    # 老配方没有运动量（分析那一版还没算）→ 现在补算，别一律当成静态
    for s in shots:
        if "motion" not in s or s.get("motion") is None:
            try:
                s["motion"] = scene.motion(video, float(s["start"]), float(s["end"]))
            except Exception as e:  # noqa: BLE001
                log.warning("补算运动量失败 shot=%s: %s", s.get("i"), e)
                s["motion"] = 0.0
    disp = triage.decide(shots, regen_shots,
                         speech_spans=speech_spans, audio_mode=audio_mode,
                         # 风格参考视频只能走视频重绘（静帧是图生图，读不到视频）
                         force_video=bool(
                             ((spec or {}).get("change") or {}).get("style_video")))
    still = triage.still_shots(disp)
    video_only = {i for i, m in disp.items() if m == "video"}
    span_min, span_max = video_edit.bounds_for(plan["ch"], plan["model"])
    spans = video_edit.fit_spans(
        triage.video_spans(shots, disp, limit=plan["limit"], total=src_total),
        span_max, min_sec=span_min)
    # 一镜到底这类没有镜头边界的片子，切点挪到画面变化最小处
    hard = list(spans)
    spans = video_edit.refine_cuts(video, spans, shots, min_sec=span_min,
                                   max_sec=span_max)
    # 🩸 2026-10-31：分诊这条路自己算 spans，不走 `plan_spans` —— 上一版把
    #   整数秒吸附只加在 `plan_spans`，预览于是还报 8.520s、真跑却发 9s。
    #   统一走 `snap_for_plan`（预览与真跑共用这一份决策）。
    spans = video_edit.snap_for_plan(plan, spans, min_sec=span_min,
                                     max_sec=span_max)
    regen_meta = {
        "mode": "auto", "segments": len(spans),
        "cuts_refined": sum(1 for x, y in zip(hard, spans)
                            if abs(x[1] - y[1]) > 1e-6),
        # 和整片重制同一条口径：只有真的会带边界帧才算（见 `_boundary_used`）
        # 预览不该因为盘点对不上而报错（真跑时 `_gen_spans` 会给出明确提示）
        "boundary": video_edit._boundary_used(
            plan, spans, _acts_or_empty(plan, spans), shots=shots),
        "label": video_edit.spec_label(plan["ch"], plan["model"]),
        "resolution": plan["resolution"],
    }
    log.info("逐镜分诊 %s；视频参考 %d 段", triage.summary(disp), len(spans))
    return {"plan": plan, "shots": shots, "disp": disp, "still": still,
            "video_only": video_only, "spans": spans, "hard": hard,
            "regen_meta": regen_meta}


def render(
    video: Path,
    rec: dict,
    *,
    script: str | None,
    workdir: Path,
    script_lines: list[str] | None = None,
    # 🩸 只重配这几行（下标基于 `script_lines`）。None = 整片重配（老行为）。
    # 部分重配时：没点到的行保留**原片那个人的原声**，提示词里整句不写。
    dub_lines: list[int] | None = None,
    # 每行用哪个音色（键=行号字符串）。空 = 全部用 `tts_voice`。
    # 🩸 只作用于**合成**：2.0/2.5 请求都不让模型生成音频（`generate_audio=False`），
    # 成片音轨 100% 来自这里，所以两个人不同音色只需要在这里分开合成。
    dub_voices: dict[str, str] | None = None,
    # 方言（火山 `explicit_dialect`）：空 = 标准普通话。
    # 只有音色表里带 `dialects` 的那几个 2.0 音色才吃这个参数。
    tts_dialect: str = "",
    tts=None,
    # 默认关：见 `api/clone.py` 里 mask_bottom 的注释（实心黑边 + 盖不到字幕）
    mask_bottom: bool = False,
    progress=None,
    regen_prompt: str = "",
    regen_ratio: float = 0.0,
    regen_shots: list[int] | None = None,
    regen_mode: str = "shots",
    regen_channel: str = "auto",
    regen_model: str = "",
    subject_image: Path | None = None,
    subject_asset: str = "",
    edit_spec: dict | None = None,
    refs: dict | None = None,
    cid: str = "",
    pronounce: dict | None = None,
    tts_voice: str = "",
    allow_stretch: bool = False,
    lang: str = "",
    speech_rate: int | None = None,
    # 🩸 只出前 N 段（2026-11-01 主人：「超过 1 段不能先生成一段满意再继续吗」）。
    #   0 = 全部（老行为）。>0 时走独立预览分支：不拼接、不配音、不出成片，
    #   只把已生成的那几段交出来；继续出全部时同参数重跑，前面的段命中缓存
    #   不重复扣费（缓存键含每段最终提示词，见 `video_edit._gen_spans`）。
    max_segments: int = 0,
    # 🩸 2026-11-02 `force`：跳过逐段产物缓存，重新调模型（会再扣费）。
    #   默认 False —— 同一键永远复用；只有用户明确点「强制重跑」才置 True。
    #   原样透传到 `video_edit._gen_spans`，中间层不做任何判断。
    force: bool = False,
) -> dict:
    """拿配方和新文案出片。script 传 None 表示沿用原片文案。

    换画面有两种模式，机制完全不同，别混：
      shots（默认）：挑一部分镜头，逐镜"首帧重绘 + 图生视频"。便宜，
                     但大动作镜头做不出来，所以只换一部分 —— 这是 L2 混剪。
      whole        ：整条片子交给视频编辑/参考模型重画。动作、运镜、节奏
                     全跟原片走 —— 这是 L3 全重制，也就是 1:1。
    """
    from app.services.providers.tts import get_tts

    workdir.mkdir(parents=True, exist_ok=True)
    tts = tts or get_tts()
    # 浅拷贝：本次渲染要往配方里塞 `voice_lines`（逐句台词，供 H3 写 `<d>`），
    # 不能改调用方手里那份 —— 同一个 rec 还会被预览、重跑复用。
    rec = dict(rec)

    src_w = int(rec["source"]["width"]) or 1080
    src_h = int(rec["source"]["height"]) or 1920
    src_total = float(rec["source"]["duration"]) or 0.0

    spec = edit_spec_mod.normalize(edit_spec) if edit_spec is not None else None
    # 🩸 人数闸门：超过型号硬上限就别开跑（钱一花就回不来）。
    # 稳定线以上、硬上限以内只进 warnings —— 用户要自由创作度，不替他决定。
    gate = _subject_gate(spec, regen_channel, regen_model)
    if gate and gate["level"] == "block":
        raise ValueError(gate["message"])
    audio_mode = spec.get("audio", "tts") if spec else "tts"
    # C4：要删/换 BGM 却没分离条件 → 现在就说，别等模型钱花完
    _aud_err = audio_preflight(spec, _audio_files_of(cid))
    if _aud_err:
        raise ValueError(_aud_err)

    # 唱的还是说的：ASR 会把歌词也转成文字，那些字不是台词（OPEN-DEFECTS D15）。
    # 只有"台词可能来自 ASR"的单子才值得花这 2 分钱先去问一次：
    #   · original：本来就不写台词（D10 闸门），不用判；
    #   · 用户自己填了文案：台词是他写的，不用判；
    #   · 其余（tts/mix 且沿用原片文案）：判。判不出来就按老行为继续。
    sep_pre = None
    if _should_probe_voice(spec, audio_mode, script,
                           bool((rec.get("source") or {}).get("has_audio"))):
        _present, sep_pre, _why = _speech_present(video, rec, workdir)
        if _present is False:
            raise ValueError(
                "这条原片里分离不出人声（原片是歌或纯音乐），自动识别出来的文字是歌词，"
                "不能当台词用。请自己填写文案；或者把「声音」改成保留原片。")

    _p(progress, "split", 5)
    base = recipe_mod.segments_for_caption(rec)
    # 🩸 `script_lines`（C6 翻译结果）优先：这些行已经是目标语言的成品，
    # 再走一遍 `_split_script` 会按 14 字合并/硬切 —— 外语每行都带 TTS 头尾
    # 静音，实测总时长涨到原片的 1.68 倍（英语）/ 1.72 倍（泰语）。
    _sl = [str(t or "").strip() for t in (script_lines or []) if str(t or "").strip()]
    if _sl:
        texts = _sl
        log.info("使用逐行文案：%d 行（跳过自动切句）", len(_sl))
    else:
        texts = _split_script(script, len(base)) if script else [
            (s.get("text") or "") for s in base
        ]

    voice: Path | None = None
    voice_dur = src_total
    # 语言优先级：界面显式选的 > 分析阶段按识别原文判的 > zh
    lang = ((lang or "").strip().lower()
            or (rec.get("speech") or {}).get("lang") or "zh")
    # 音色：目录里有的按目录收口；手填的私有音色（S_…）原样放行。
    # 换掉时必须说清为什么，不然用户只会觉得"我选了没用"。
    voice_id, voice_note = voice_catalog.resolve(tts_voice, lang)
    if voice_note:
        log.warning("音色替换：%s", voice_note)
    # 哪几段在说话（秒 · **源片时间轴**）。分诊用：tts 换全新配音时，
    # 说话镜不能保留原片口型。默认取原片 ASR；重新配音后改用新文案的时间轴。
    speech_spans: list[tuple[float, float]] = []
    # 保留原声时根本没配音，别在结果页写"配音：小何 2.0"
    voiced = audio_mode != "original"
    voice_meta = {"speech_rate": 0, "est_seconds": 0.0,
                  "voice_seconds": 0.0, "stretch": 1.0,
                  "lang": lang,
                  "voice": voice_id if voiced else "",
                  "voice_label": voice_catalog.label(voice_id) if voiced else "",
                  "voice_note": voice_note if voiced else ""}
    if audio_mode == "original":
        # 只换画面（唱歌 / 跳舞 / 原口播）：声音是内容，不调 TTS。
        # 这类片子常常识别不出字（唱歌的咬字、纯跳舞根本没词），
        # 所以**有字才分句对齐，没字就按镜头段占位**，不拿这个卡出片。
        _p(progress, "align", 30)
        segs = [s for s in base if (s.get("text") or "").strip()]
        speech_spans = [
            (float(s["start"]), float(s["end"]))
            for s in (rec.get("speech") or {}).get("segments") or []
            if (s.get("text") or "").strip()
        ]
        log.info("声音模式=保留原音轨，跳过 TTS；原片识别到 %d 段文字", len(segs))
        # 原声模式：台词就是原片 ASR 的结果（源片时间轴，直接可用）
        # `asr_speaker` = 原片 ASR 给的说话人编号（`additions.speaker`），
        # 由 `video_edit._assign_speakers` 映射成盘点人物 id。原声模式下它最可靠：
        # 台词就是原片那几句，声纹聚类和画面是同一条片子。
        rec["voice_lines"] = [
            {"start": round(float(s["start"]), 3), "end": round(float(s["end"]), 3),
             "text": str(s.get("text") or "").strip(), "lang": lang,
             "asr_speaker": str(s.get("speaker") or "")}
            for s in (rec.get("speech") or {}).get("segments") or []
            if (s.get("text") or "").strip()
        ]
    else:
        _p(progress, "tts", 20)
        voice_dir = workdir / "voice"
        voice_dir.mkdir(parents=True, exist_ok=True)
        # 供应商产出什么容器就用什么后缀：火山直接给 mp3，别再绕一圈转码
        ext = getattr(tts, "ext", ".wav")
        # 读音校正只作用于"要念的那一份"（识别原文不改，逐句编辑仍看原文）
        spoken_texts = [pronounce_mod.apply(t, pronounce) for t in texts]
        # 先估时长、把语速一次调到位 —— 剩下的残差才交给 atempo。
        # 不估的话，文案一长 atempo 就顶在 1.25，画面只能冻帧。
        est = speech_est.estimate_all(spoken_texts, lang)
        # 用户在前台试听后手调过语速就听他的：估算是给初值，不是给他改主意。
        # 仍然夹在 ±MAX_RATE —— 再往上人声就变调了。
        if speech_rate is None:
            rate = speech_est.rate_for(est, src_total)
        else:
            rate = int(max(-speech_est.MAX_RATE,
                           min(speech_est.MAX_RATE, int(speech_rate))))
        log.info("文案估算 %.2fs / 原片 %.2fs → 语速 %+d%%%s",
                 est, src_total, rate, "（用户手调）" if speech_rate is not None else "")
        # 🩸 部分重配（2026-10-27）：只合成被点到的行，其余保留原声。
        # 行号基于 `texts`（= 过滤空串后的 `script_lines`）；越界的丢掉。
        # 全选 = 整片重配，走原来的路径。
        # 原片每句的时间段：新配音要放到这些位置上去。
        _spans = [(float(s.get("start") or 0.0), float(s.get("end") or 0.0))
                  for s in base if (s.get("text") or "").strip()]
        _dub = sorted({int(i) for i in (dub_lines or [])
                       if 0 <= int(i) < len(texts)})
        _partial = bool(_dub) and len(_dub) < len(texts)
        if _partial and len(_spans) != len(texts):
            # 对不上就没法把新配音放到正确位置 —— 宁可整片重配，也不配错人
            log.warning("部分重配不可用（原片 %d 句 ≠ 文案 %d 行），改回整片重配",
                        len(_spans), len(texts))
            _partial = False

        audios: list[Path] = []
        clips: dict[int, Path] = {}
        for i, t in enumerate(spoken_texts):
            if not (t or "").strip():
                continue
            if _partial and i not in _dub:
                continue
            p = voice_dir / f"seg_{i:03d}{ext}"
            # 🩸 这一行用谁的音色：按行号查 `dub_voices`，查不到用整片那个。
            # 逐段独立合成 → 两个人不同音色不需要拆音轨，也不需要 `@音频2`。
            _v = str((dub_voices or {}).get(str(i)) or "").strip()
            _vid = voice_id
            if _v:
                _vid, _vn = voice_catalog.resolve(_v, lang)
                if _vn:
                    log.warning("第 %d 行音色替换：%s", i + 1, _vn)
            tts.synth(t, p, voice=_vid, rate=rate,
                      dialect=(tts_dialect or "").strip().lower())
            audios.append(p)
            clips[i] = p

        if not audios:
            raise RuntimeError("没有可合成的文案")

        _p(progress, "align", 45)
        _base_spk = [str(s.get("speaker") or "")
                     for s in (rec.get("speech") or {}).get("segments") or []
                     if (s.get("text") or "").strip()]
        if _partial:
            # ---- 只重配其中几个人（2026-10-27）----
            # 音轨 = 原片打底（没点到的人还在说原话）+ 新配音盖住点到的那几句。
            voice = workdir / "voice.wav"
            _partial_voice(video, _spans, {i: clips[i] for i in _dub},
                           voice, workdir=workdir)
            voice_dur = float(scene.probe(voice).get("duration") or src_total)
            kept_texts = [texts[i] for i in _dub]
            speech_spans = [_spans[i] for i in _dub]
            segs = _build_segments(speech_spans, kept_texts)
            # 🩸 台词只写被重配的那几句（2.0 官方 `:31`「未提及的部分，默认保持不变」）。
            # 没点到的行**整句不出现** —— 写出来反而等于告诉模型"这句也要重念"。
            _same = len(_base_spk) == len(texts)
            rec["voice_lines"] = [
                {"start": round(float(_spans[i][0]), 3),
                 "end": round(float(_spans[i][1]), 3),
                 "text": texts[i], "lang": lang,
                 "asr_speaker": _base_spk[i] if _same else ""}
                for i in _dub]
            log.info("部分重配：只念第 %s 行（共 %d 行），其余保留原声",
                     "、".join(str(i + 1) for i in _dub), len(texts))
            voice_meta.update({
                "speech_rate": rate,
                "est_seconds": est,
                "voice_seconds": round(voice_dur, 3),
                "stretch": 1.0,
                "partial": {"lines": [i + 1 for i in _dub], "total": len(texts)},
            })
            new_total = voice_dur
            tempo = 1.0
        else:
            durs = [scene.probe(a)["duration"] for a in audios]
            new_total = sum(durs)
            ratio = (src_total / new_total) if new_total > 0 and src_total > 0 else 1.0

            # 语速已经调过还差得远 ⇒ 别再往下走了。视频生成是最贵的一段，
            # 拉不动的部分只能冻最后一帧/截断，硬出片等于花钱买个错位的成品。
            if abs(ratio - 1.0) > 0.25 and not allow_stretch:
                adv = speech_est.advise("".join(texts), src_total, lang)
                tip = (f"建议删掉约 {adv.get('trim_chars', 0)} 字"
                       if ratio < 1.0 else "建议再补几句，或换一条更长的原片")
                # 方向不同，后果也不同（依据 `compose.py`：成片时长取画面和配音里更长的那个，
                # 画面短了冻最后一帧、音轨短了补静音，**不用 -shortest**）：
                #   配音比画面短 → 画面照常走完，结尾留一段没人说话的静音；
                #   配音比画面长 → 画面在结尾冻住补够时长。
                tail = ("结尾会留一段没人说话的静音" if ratio > 1.0
                        else "结尾要冻住最后一帧")
                raise RuntimeError(
                    f"新文案配完是 {new_total:.1f}s，原片 {src_total:.1f}s"
                    f"（差 {abs(ratio - 1) * 100:.0f}%，可调范围 ±25%）。{tip}。"
                    f"确实要出片请打开「仍然出片」，{tail}。"
                )

            # 🩸 atempo 要的是「配音 → 原片」的倍率，不是 ratio。
            #   ratio = 原片/配音；atempo=T 的语义是「输出 = 输入 ÷ T」，
            #   所以把配音拉到原片长度要 T = 配音/原片 = 1/ratio。
            #   以前直接传 ratio，方向正好反了 —— 配音偏短就更加速、偏长就更减速，
            #   把误差放大一次。判据在别处，不靠这条注释：
            #   · `compose.py`：「画面短了冻最后一帧、音轨短了补静音，绝不用 -shortest」
            #   · `source_speech_spans`：「画面原速、配音原速，两条时间轴本来就是同一条」
            #   ⇒ 成片时长 = max(原片, 配音)，所以唯一要做的就是把配音往原片长度上拉。
            tempo = _clamp_tempo(1.0 / ratio) if ratio > 0 else 1.0
            log.info("原片 %.2fs / 新配音 %.2fs → atempo %.3f", src_total, new_total, tempo)

            voice = workdir / "voice.wav"
            _concat_audio(audios, voice, tempo=tempo, workdir=workdir)

            # 新时间轴按"最终音轨的真实时长"来缩放 —— 不能用原片时长：
            # atempo 被夹在 0.8–1.25，配音不会恰好等于原片长度。
            voice_dur = scene.probe(voice)["duration"] or new_total
            windows: list[tuple[float, float]] = []
            cursor = 0.0
            for d in durs:
                windows.append((cursor, cursor + d))
                cursor += d
            scale = (voice_dur / cursor) if cursor > 0 else 1.0
            windows = [(s * scale, e * scale) for s, e in windows]

            kept_texts = [t for t in texts if (t or "").strip()]
            segs = _build_segments(windows, kept_texts)
            # 新文案的说话区间映射回源片时间轴，供分诊判断"哪一镜在说话"。
            # 以前这里用的是原片 ASR —— 文案一变长，判断就整段偏掉。
            speech_spans = source_speech_spans(windows, src_total)
            # 🩸 台词的来源在这里就是**要念的那份文案**（用户填的 `script`，没填才用原片
            # ASR 分段），时间轴已映射回源片（`speech_spans`）—— H3 的 `<d>` 直接用这个。
            # 🩸 逐句说话人：tts 模式的台词是**要念的新文案**，ASR 没识别过它，
            # 声纹编号自然也没有。但新文案是按原片分段切出来的
            # （`_split_script(script, len(base))`），第 i 段对应原片第 i 段 ——
            # 原片那段的 `speaker` 就是这句的说话人。段数对不上时宁可不带，
            # 也不张冠李戴（`_assign_speakers` 会退回按画面推）。
            # ⚠️ 已知边界：这个对应只在"新文案还是同一段对话的改写"时成立。
            # 用户把对白结构整个改了（原片 A 说第 1 句，新文案让 B 说），
            # 按位置对应就会张冠李戴 —— 目前没有便宜的办法验证这一点，
            # 所以只有**原声模式**的声纹是可靠的（台词就是原片那几句）。
            _base_spk = [str(s.get("speaker") or "")
                         for s in (rec.get("speech") or {}).get("segments") or []
                         if (s.get("text") or "").strip()]
            _same = len(_base_spk) == len(kept_texts)
            rec["voice_lines"] = [
                {"start": round(float(sp[0]), 3), "end": round(float(sp[1]), 3),
                 "text": t, "lang": lang,
                 "asr_speaker": _base_spk[i] if _same else ""}
                for i, (sp, t) in enumerate(zip(speech_spans, kept_texts))
                if (t or "").strip()
            ]
            voice_meta.update({
                "speech_rate": rate,
                "est_seconds": est,
                "voice_seconds": round(voice_dur, 3),
                "stretch": round(tempo, 3),
            })

    # ---- 换画面 ----
    source_video = video
    # 画面轨的分段素材：给了就直接用它们出片（只编码一次，不落 timeline.mp4）；
    # 没给（整片重制 / 没换画面）就还是拿整条源。
    visual_clips = None
    replaced = 0
    # 成片结尾比原片短多少秒（0 = 不短）。只有「尾段模型少给」这一种情况会 >0，
    # 见 `_gen_spans` 里 `_TAIL_TOL` 那段：不冻帧、不回灌原片，成片跟着短。
    tail_cut = 0.0
    used_channel = ""
    used_model = ""
    # 换画面这一侧的自述：分了几段、几个切点被挪到画面最静处、段间有没有尾帧衔接。
    # 用户问得最多的一句是"30 秒的片子能不能出"，答案就写在这里。
    regen_meta: dict = {}
    # 规格里有勾了「换什么」或者写了补充说明，都算要换画面
    wants_change = bool((regen_prompt or "").strip())
    if spec and (edit_spec_mod.has_change(spec) or spec.get("extra")):
        wants_change = True
    mode = (regen_mode or "auto").strip().lower()

    # 静帧重绘要**真的把参考图发过去**：只发原片帧时，提示词说「换成另一个人」
    # 模型只能按文字凭空造脸（2026-10-21 实测：12s 那条换成了陌生脸）。
    # 顺序 = SLOT_ORDER，image 数组里图一是原片帧，图二起是各槽位图。
    # 🩸 混剪（shots）和智能重制（auto）都是"生图 + 图生视频"，两边共用这一份，
    #    以前只写进了 auto 分支 —— 混剪换人照样不发人物图。
    # 🩸 这里是**静帧重绘**：`ref_plan` 不传 `model`，一人一张（用户上传的那张）。
    # 🩸 2026-10-26 更正：整片重制**也不再按型号分叉** —— 三家官方原文复核后
    # 都是「一个换的人 = 一张图」（台账 D48；D46 的「2.0 拆两张」已作废）。
    # 别在这里再写一份派图规则。
    from app.services import video_edit as _ve

    slot_items = _ve.ref_plan(spec, refs or {}) if spec else []
    slot_refs: list[Path] = [Path(x) for _, x in slot_items
                             if not isinstance(x, str)]
    slot_names: list[str] = [s for s, _ in slot_items]

    # 换人物前先看清原片里有谁：一句"替换人物"在多人画面里没有唯一解。
    # 失败就当没有 —— 盘点绝不能把出片搞挂（见 vision_plan 的降级说明）。
    inventory = None
    chg_now = (spec.get("change") or {}) if spec else {}
    # 🩸 不只在"换人物"时要盘点：只换衣服/道具的人**不在**换人名单里，
    # 提示词得靠盘点给出的外观描述指认「是哪一位」。
    if wants_change and spec and (chg_now.get("person") or chg_now.get("wardrobe_ids")
                                  or chg_now.get("props")):
        inventory = _inventory_or_none(cid)

    if spec and slot_refs:
        # 静帧重绘的提示词要能点名"原片里哪一位"：多人同框时不点名等于没换
        ids = list((spec.get("change") or {}).get("person_ids") or [])
        # 多人换人但盘点没能区分 → 逐人那句会写成两句一样的「图一里的人物」。
        # 🩸 静帧有自己的一道闸（读 `desc_zh`），**不与视频侧共用**：
        # 视频侧的 H3 读 `desc_en`、2.5 还要查职责行，尺子维度不同。
        _ve.require_identifiable_still(inventory, slot_names)
        people = []
        if inventory and ids:
            by = {p.get("id"): p for p in (inventory.get("people") or [])}
            people = [dict(by[pid], present=True) if pid in by
                      else {"id": pid, "present": False} for pid in ids]
        shot_p = edit_spec_mod.still_prompt(
            spec, slot_names, regen_prompt, people=people,
            desc_by_id=_ve.desc_by_id(inventory))
        motion_p = edit_spec_mod.motion_prompt(spec)
    elif not spec:
        shot_p = regen_prompt
        motion_p = None
    else:
        shot_p = edit_spec_mod.shot_prompt(spec, regen_prompt)
        motion_p = None

    # 🩸 只出前 N 段（2026-11-01 主人：「超过 1 段不能先生成一段满意再继续吗」）：
    #   走**独立分支** —— 不拼接、不配音、不合成。缺段拼出来的片子是残的，
    #   用户会误以为是成片；这里只把已生成的那几段交出去。
    #   继续出全部时用同样参数重跑：前 N 段命中缓存不重复扣费（缓存键含每段
    #   最终提示词），只有没生成过的段真花钱。
    if max_segments and wants_change:
        from app.services import video_edit as _ve_prev

        _p(progress, "regen", 50)
        prev_path = None
        _ch_used = _md_used = ""
        _meta: dict = {"partial": True, "done_segments": 0, "total_segments": 0}
        if mode == "whole":
            _r = _ve_prev.replace_whole(
                video, rec, cid=cid, prompt=regen_prompt, spec=spec, refs=refs,
                subject_image=subject_image, subject_asset=subject_asset,
                channel=regen_channel, model=regen_model, inventory=inventory,
                style_video=_style_video_of(cid, spec),
                workdir=workdir, progress=progress, max_segments=max_segments,
                force=force)
            prev_path = _r.get("preview") or _r.get("video")
            _ch_used, _md_used = _r.get("channel", ""), _r.get("model", "")
            _meta.update({"mode": "whole",
                          "done_segments": int(_r.get("done_segments") or 0),
                          "total_segments": int(_r.get("total_segments") or 0),
                          "label": _r.get("label") or "",
                          "resolution": _r.get("resolution") or ""})
        else:
            _d = _auto_decision(
                video, rec, spec=spec, regen_prompt=regen_prompt,
                regen_shots=regen_shots, regen_channel=regen_channel,
                regen_model=regen_model, subject_image=subject_image,
                subject_asset=subject_asset, refs=refs, inventory=inventory,
                audio_mode=audio_mode, speech_spans=speech_spans,
                style_video=_style_video_of(cid, spec),
            )
            _plan, _spans = _d["plan"], _d["spans"]
            if not _spans:
                raise ValueError(
                    "这一单没有要走视频模型的段（全是静帧重绘），"
                    "「先出一段」用不上 —— 直接出全部就行")
            _clips = _ve_prev.replace_spans(
                video, rec, _spans, cid=cid, plan=_plan, inventory=inventory,
                workdir=workdir / "triage", progress=progress,
                max_segments=max_segments, force=force)
            prev_path = _clips[0] if _clips else None
            _ch_used, _md_used = _plan.get("ch", ""), _plan.get("model", "")
            _meta.update({"mode": "auto",
                          "done_segments": len(_clips),
                          "total_segments": len(_spans),
                          "label": _plan.get("label") or "",
                          "resolution": _plan.get("resolution") or ""})
        # 成片下载接口固定读 `workdir/out.mp4`（`api/clone.py` 的
        # `/render/{rid}/file/out`）。预览片段落到这个名字上，前端不用认识
        # "预览"这种新路径；继续出全部时再被真正的成片覆盖。
        if prev_path and Path(prev_path).exists():
            _out_prev = workdir / "out.mp4"
            if Path(prev_path) != _out_prev:
                import shutil as _sh_prev

                _out_prev.parent.mkdir(parents=True, exist_ok=True)
                _sh_prev.copyfile(prev_path, _out_prev)
            prev_path = _out_prev
        # 🩸 预览段也要有封面：`cover: None` 会让历史卡片那一版是**一片灰**
        #   （`p7_check` 3.1 实测红：缺封面 949c0b2f）。抽一帧而已，本机完成，不花钱。
        _cover_prev = None
        if prev_path:
            try:
                _cover_prev = compose.make_cover(
                    prev_path, workdir / "cover.jpg", at=0.5)
            except Exception as e:  # noqa: BLE001
                log.warning("预览段封面没抽出来（不影响看片）：%s", e)
        _p(progress, "done", 100)
        return {
            "video": prev_path, "preview": prev_path, "partial": True,
            "cover": _cover_prev, "voice": None,
            "duration": (scene.probe(prev_path)["duration"]
                         if prev_path else 0.0),
            "segments": [],
            "qc": {"ok": True, "skipped": "只出了前几段，没有成片可质检"},
            "identity": {"ok": True, "skipped": "预览段不核身份"},
            "contract": {"ok": True, "verdict": "skipped",
                         "items": [], "failed": []},
            "replaced_shots": int(_meta["done_segments"]),
            "regen_channel": _ch_used, "regen_model": _md_used,
            "voice_meta": {}, "regen_meta": _meta,
        }

    if wants_change:
        from app.services import assemble, generate, triage, video_edit

        inv_meta = {}
        if inventory:
            im = inventory.get("_meta") or {}
            inv_meta = {"people": len(inventory.get("people") or []),
                        "vision_model": im.get("model", ""),
                        "vision_cached": bool(im.get("cached"))}

        if mode == "whole":
            # 兜底：整条片子都交给视频编辑模型。最贵、改得最狠，只在自动分诊
            # 判不出来（比如全片都要大改）时才用
            _p(progress, "regen", 50)
            r = video_edit.replace_whole(
                video, rec, cid=cid, prompt=regen_prompt, spec=spec, refs=refs,
                subject_image=subject_image, subject_asset=subject_asset,
                channel=regen_channel, model=regen_model, inventory=inventory,
                style_video=_style_video_of(cid, spec),
                workdir=workdir, progress=progress, force=force,
            )
            source_video = r["video"]
            replaced = int(r.get("chunks") or 0)
            used_channel = str(r.get("channel") or "")
            used_model = str(r.get("model") or "")
            regen_meta = {"mode": "whole", "segments": replaced,
                          "cuts_refined": int(r.get("cuts_refined") or 0),
                          "boundary": bool(r.get("boundary")),
                          "kept": int(r.get("kept") or 0),
                          # 结果页照这两个显示"用的哪一款、哪一档"，别让用户回查日志
                          "label": r.get("label") or "",
                          "resolution": r.get("resolution") or "",
                          **inv_meta}
        elif mode == "auto":
            # 逐镜分诊：能保的原片像素就保，静态镜走静帧重绘，动作镜才喂视频模型
            src_w2 = int(rec["source"]["width"]) or 1080
            src_h2 = int(rec["source"]["height"]) or 1920
            d = _auto_decision(
                video, rec, spec=spec, regen_prompt=regen_prompt,
                regen_shots=regen_shots, regen_channel=regen_channel,
                regen_model=regen_model, subject_image=subject_image,
                subject_asset=subject_asset, refs=refs, inventory=inventory,
                audio_mode=audio_mode, speech_spans=speech_spans,
                style_video=_style_video_of(cid, spec),
            )
            plan = d["plan"]
            shots = d["shots"]
            still = d["still"]
            video_only = d["video_only"]
            spans = d["spans"]
            regen_meta = {**d["regen_meta"], **inv_meta}
            if not spans:
                # 这段没有调视频编辑模型，全是静帧重绘：别在结果页挂着 Seedance 型号
                regen_meta["label"] = "静帧重绘（生图 + 图生视频）"
                regen_meta["resolution"] = f"{src_w2}×{src_h2}"

            # 时间轴按**区间**拼，不按镜头拼：一镜可能被模型的上限切成好几段，
            # 按镜头收口只能塞下其中一段（见 _span_intervals 的说明）
            intervals: list[tuple[float, float, Path, float]] = []
            if still:
                _p(progress, "regen", 50)
                still_clips = generate.regen_shots(
                    video, rec, still, prompt=shot_p,
                    workdir=workdir / "still", progress=progress,
                    cache_dir=_cache_dir(cid, "still"),
                    ref_images=slot_refs, video_prompt=motion_p,
                    lock_tail=bool((spec or {}).get("lock_tail")),
                )
                by_i = {int(s["i"]): s for s in shots}
                for i, p in still_clips.items():
                    s = by_i.get(int(i))
                    if s is None:
                        continue
                    intervals.append((float(s["start"]), float(s["end"]),
                                      Path(p), 0.0))
            if spans:
                clips = video_edit.replace_spans(
                    video, rec, spans, cid=cid, plan=plan, inventory=inventory,
                    workdir=workdir / "triage", progress=progress, force=force,
                )
                intervals.extend(_span_intervals(clips, spans, shots, only=video_only))

            if intervals:
                tl_notes: list[str] = []
                # 决策落盘：日志重启就没了，这份留在出片目录里可以事后追溯
                # 「哪几段重制了、时间轴上是哪几条素材、邻居镜头有没有被误替换」
                try:
                    import json as _json
                    (workdir / "decisions.json").write_text(_json.dumps({
                        "mode": "auto",
                        "total": src_total,
                        "shots": len(shots),
                        "video_shots": sorted(video_only),
                        "still_shots": sorted(still),
                        "spans": [[round(a, 3), round(b, 3)] for a, b in spans],
                        "intervals": [[round(a, 3), round(b, 3), Path(p).name,
                                       round(o, 3)] for a, b, p, o in intervals],
                    }, ensure_ascii=False, indent=1), encoding="utf-8")
                except Exception as e:  # noqa: BLE001
                    log.warning("决策记录没写成（不影响出片）：%s", e)
                # 🩸 尾段模型少给（≤0.45 秒）时，`_gen_spans` 已经按实际长度出片。
                #   时间轴到这里就结束，**不拿原片补尾巴** —— 补了就是
                #   "最后一帧变回原脸"（2026-10-31 实测过的那个病）。
                #   成片跟着短，是主人 2026-10-31 拍板的口径。
                if intervals:
                    vis_end = max(float(h) for _, h, _, _ in intervals)
                    gap = float(src_total) - vis_end
                    if 0 < gap <= 0.45:
                        tail_cut = round(gap, 3)
                        tl_notes.append(
                            f"成片结尾比原片短 {tail_cut:.2f} 秒"
                            "（模型给的这一段就短这么多，没有拿原片回灌）")
                visual_clips = assemble.plan_intervals(
                    video, intervals, total=max(0.5, float(src_total) - tail_cut),
                    notes=tl_notes,
                )
                if tl_notes:
                    regen_meta["warnings"] = tl_notes
                replaced = len(intervals)
                used_channel = plan["ch"] if spans else "static"
                used_model = plan["model"] if spans else ""
        else:
            from app.core.config import settings

            picks = regen_shots or assemble.pick_shots(
                rec.get("shots") or [], regen_ratio, settings.clone_max_regen
            )
            if picks:
                _p(progress, "regen", 50)
                clips = generate.regen_shots(
                    video, rec, picks, prompt=shot_p,
                    workdir=workdir, progress=progress,
                    cache_dir=_cache_dir(cid, "still"),
                    ref_images=slot_refs, video_prompt=motion_p,
                    lock_tail=bool((spec or {}).get("lock_tail")),
                )
                if clips:
                    visual_clips = assemble.plan_shots(
                        video, rec.get("shots") or [], clips,
                    )
                    replaced = len(clips)
                    regen_meta = {"mode": "shots", "segments": len(clips),
                                  "cuts_refined": 0, "boundary": False}

    # 🩸 无缝转场（B7）**不接在出片链路上**（2026-10-25 主人拍板）：
    # 复刻的目标是像原片，而原片的硬切就是原片的剪法 —— 把剪辑点揉成过渡，
    # 片子反而不像了；重绘段 ↔ 原片段的接缝另有 B6 尾帧锁定覆盖（几乎零成本）。
    # 只剩延长链路那一个接缝真需要补（见 `extend.run`）。

    # 🩸 2026-10-23 主人拍板「也不烧字幕」：整条烧字幕链路已删，成片不带任何字幕。
    _p(progress, "compose", 88)
    mask = None
    if mask_bottom:
        h = int(src_h * 0.20)
        # 0.55 挡不住原片硬字幕：实测透过去还能读出来；
        # 0.85 仍留一层灰影，0.95 才读不出来
        mask = (0, src_h - h, src_w, h, 0.95)

    if tail_cut > 0:
        # 画面就止于 `src_total - tail_cut`：音轨**一起收口**，不冻帧补够
        # （冻帧等于拿静止画面顶时长，主人 2026-10-31 要的是"成片跟着短"）。
        src_total = max(0.5, float(src_total) - tail_cut)
        voice_dur = min(float(voice_dur), src_total)
    # 配音比画面长时，把最后一帧冻住补够，别让音轨被截断
    pad = max(0.0, voice_dur - src_total) if voice is not None else 0.0
    # 成片时长 = 画面和配音里更长的那个；画面短了 tpad、音轨短了 apad。
    # 绝不再用 `-shortest` —— 它会在另一路结束时静默截断，成片少半段才发现。
    target = max(src_total, voice_dur if voice is not None else 0.0)
    out_fps = float(rec["source"].get("fps") or 0)
    out_frames = int(round(target * out_fps)) if out_fps > 0 else 0
    # 底音轨只能从**原片**拿（重制后的画面里没有原声）。C4 起这一层统一由
    # `_audio_bed` 按 `audio` / `bgm` / `sfx` 三个开关决定接哪几条轨 ——
    # original 整轨、mix 的背景轨、删/换 BGM、叠音效都在里面收口。
    # 原片本身没有音轨时不接，否则 -map 一个不存在的流会直接失败。
    has_audio = bool(rec["source"].get("has_audio"))
    bg_from, _bed_err = _audio_bed(
        video, rec, workdir, spec, total_sec=target,
        audio_files=_audio_files_of(cid), sep_pre=sep_pre)
    if _bed_err:
        # 宁可不出片也不出错片：BGM 明明要求删掉却还在响，用户会再花一次钱。
        # 模型分段有缓存，重试时不会重复付费（`work` 复用 + `video_edit` 段缓存）。
        raise RuntimeError(_bed_err)
    if not has_audio:
        bg_from = None
    out = workdir / "out.mp4"
    compose.compose(
        video=source_video, out=out, voice=voice, mask=mask, pad_to=pad,
        target=target, fps=out_fps, bg_from=bg_from,
        clips=visual_clips,
        size=(src_w, src_h, out_fps or 30.0),
    )
    # 质量门：本地 ffmpeg 过一遍，零成本。出片是花钱的，别让主人用肉眼看第一遍。
    # 只记录不阻断 —— 钱已经花了，把片子交出去 + 把缺陷说清楚，比直接报错有用。
    try:
        # 硬合同是 target（画面/配音取长），不是原片时长：新配音比原片长时
        # 成片本来就该更长，拿原片当尺子会把正常片子判成缺陷。
        # 帧数和采样数都是合同量（画面按 -frames:v 钉死，音轨按帧域算采样数），
        # 所以质检用的是**等值**，不带容差。
        out_samples = (int(round(out_frames / out_fps * 48000))
                       if out_fps > 0 and out_frames else 0)
        qc_res = qc.inspect(out, expect_duration=target,
                            expect_w=src_w, expect_h=src_h,
                            expect_fps=out_fps, expect_frames=out_frames,
                            expect_samples=out_samples)
        if abs(target - src_total) > 0.3:
            qc_res.setdefault("warnings", []).append(
                f"成片 {target:.2f}s 与原片 {src_total:.2f}s 不同（由配音长度决定）")
    except Exception as e:  # noqa: BLE001
        qc_res = {"ok": False, "issues": [f"质检没跑成：{e}"],
                  "warnings": [], "stats": {}}
        log.warning("质检没跑成（不影响出片）：%s", e)
    # 身份核对（D1，台账 D 段·量具）：**换脸到底换上了没有**。
    # 2026-10-25 的教训 —— 2.5 双人换人那次，白衣服那位没换上，而人眼看 480p 截图判错了两次。
    # 只在真换了人时跑（没换人没有可比对象）；🩸 绝不阻断出片，失败一律 skipped。
    try:
        if any(str(k).startswith("person") for k in (refs or {})):
            id_res = identity.check(out, refs)
        else:
            id_res = {"ok": True, "skipped": "这次没换人，没有可比的对象", "people": []}
    except Exception as e:  # noqa: BLE001
        id_res = {"ok": True, "skipped": f"核对没跑成：{e}", "people": []}
        log.warning("身份核对没跑成（不影响出片）：%s", e)
    # 🩸 成品契约（第 3 步）：口型 / 段间身份 / 背景 —— 量的是**产品**，
    # 与上面那条「成片 vs 参考图」互补。前三项都不查代码，只读出片目录里的
    # `gen/` `piece_*` `decisions.json`。永不阻断出片。
    try:
        from app.services import contract

        contract_res = contract.measure(workdir=Path(workdir), video=Path(video),
                                        out=out)
    except Exception as e:  # noqa: BLE001
        contract_res = {"ok": True, "verdict": "skipped", "items": [], "why": str(e)}
        log.warning("成品契约没量成（不影响出片）：%s", e)
    cover = compose.make_cover(out, workdir / "cover.jpg", at=min(2.0, voice_dur / 3))

    _p(progress, "done", 100)
    return {
        "video": out,
        "cover": cover,
        "voice": voice,
        "duration": scene.probe(out)["duration"],
        "segments": segs,
        # 质检结果：ok / issues / warnings / stats（定格、音画时长差、总时长偏离）
        "qc": qc_res,
        # 身份核对：ok / skipped / people[{slot,best_sim,at,faces_seen,verdict}]
        # 判 swapped / not_swapped / no_face / no_ref —— 换脸到底换上了没有
        "identity": id_res,
        # 成品契约：口型滞后 / 段间身份 / 背景保住 —— 量产品，不量代码。
        # 结构 {ok, verdict: pass|fail|info|skipped, items[], failed[]}
        "contract": contract_res,
        "replaced_shots": replaced,
        "regen_channel": used_channel,
        "regen_model": used_model,
        # 配音这一侧的实测值：语速调了多少、估算多少、实际多少、atempo 用了多少。
        # 前端据此告诉用户"为什么这条片子的配音被拉过"。
        "voice_meta": voice_meta,
        # 换画面怎么拆的请求（几段 / 切点是否挪过 / 段间是否用尾帧衔接）
        "regen_meta": regen_meta,
    }


# ---------------------------------------------------------------------------


def preview_render(
    video: Path,
    rec: dict,
    *,
    script: str | None,
    script_lines: list[str] | None = None,
    regen_prompt: str = "",
    regen_ratio: float = 0.0,
    regen_shots: list[int] | None = None,
    regen_mode: str = "auto",
    regen_channel: str = "auto",
    regen_model: str = "",
    subject_image: Path | None = None,
    subject_asset: str = "",
    edit_spec: dict | None = None,
    refs: dict | None = None,
    pronounce: dict | None = None,
    tts_voice: str = "",
    allow_stretch: bool = False,
    lang: str = "",
    cid: str = "",
    speech_rate: int | None = None,
    with_agent: bool = False,
    agent_force: bool = False,
    max_segments: int = 0,
) -> dict:
    """出片前预览：**全本地计算，不调 TTS / 图 / 视频模型，不传 OSS，不花钱**。

    回答三个问题：
      1. 这次会动哪几段、调几次模型、生成多少秒；
      2. 成片按合同应该是多少帧 / 多少音频采样；
      3. 现在这个文案会不会被"长度差太多"拦下（先知道，别等到出片才报错）。

    和 `render` 共用 `_auto_decision`，所以段数/镜号不是另算一套。
    """
    from app.core.config import settings
    from app.services import assemble, video_edit

    src_total = float((rec.get("source") or {}).get("duration") or 0.0)
    fps = float((rec.get("source") or {}).get("fps") or 0.0)
    spec = edit_spec_mod.normalize(edit_spec) if edit_spec is not None else None
    # 人数闸门（按型号）：预览阶段就把"换太多人"说出来，别等出片才报错。
    gate = _subject_gate(spec, regen_channel, regen_model)
    audio_mode = (spec or {}).get("audio", "tts")
    lang = ((lang or "").strip().lower()
            or (rec.get("speech") or {}).get("lang") or "zh")
    voice_id, voice_note = voice_catalog.resolve(tts_voice, lang)

    base = recipe_mod.segments_for_caption(rec)
    # 和 `render` 同一条规则：给了逐行文案就直接用，不再自动切句
    _sl = [str(t or "").strip() for t in (script_lines or []) if str(t or "").strip()]
    if _sl:
        texts = _sl
    else:
        texts = _split_script(script, len(base)) if script else [
            (s.get("text") or "") for s in base
        ]

    warnings: list[str] = []
    blocked = ""
    # 人数闸门：超过型号硬上限直接判不通过；稳定线以上只提示，不挡人。
    if gate and gate["level"] == "block":
        blocked = gate["message"]
    elif gate and gate["level"] == "warn":
        warnings.append(gate["message"])
    speech_spans: list[tuple[float, float]] = []
    audio_missing = False
    if audio_mode == "original":
        voice_dur = src_total
        speech_spans = [
            (float(s["start"]), float(s["end"]))
            for s in (rec.get("speech") or {}).get("segments") or []
            if (s.get("text") or "").strip()
        ]
        audio_meta = {"mode": "original", "estimated": False,
                      "speech_rate": 0, "est_seconds": 0.0,
                      "voice_seconds": round(src_total, 3),
                      "chars": 0}
    else:
        kept = [t for t in texts if (t or "").strip()]
        spoken = [pronounce_mod.apply(t, pronounce) for t in kept]
        est = speech_est.estimate_all(spoken, lang)
        if speech_rate is None:
            rate = speech_est.rate_for(est, src_total)
        else:
            rate = int(max(-speech_est.MAX_RATE,
                           min(speech_est.MAX_RATE, int(speech_rate))))
        predicted = est / (1.0 + rate / 100.0) if est > 0 else 0.0
        ratio = (src_total / predicted) if predicted > 0 and src_total > 0 else 1.0
        if abs(ratio - 1.0) > 0.25 and not allow_stretch:
            adv = speech_est.advise("".join(texts), src_total, lang)
            tip = (f"建议删掉约 {adv.get('trim_chars', 0)} 字"
                   if ratio < 1.0 else "建议再补几句，或换一条更长的原片")
            blocked = (f"新文案配完约 {predicted:.1f}s，原片 {src_total:.1f}s"
                       f"（差 {abs(ratio - 1) * 100:.0f}%，可调范围 ±25%）。{tip}。"
                       "确实要出片请打开「仍然出片」。")
        # 预览用逐段估算排时间轴；真实 TTS 出来会有小幅偏差（结果页会报实测）
        durs = [speech_est.estimate(t, lang) / (1.0 + rate / 100.0) for t in spoken]
        new_total = sum(durs)
        scale = (src_total / new_total) if new_total > 0 and src_total > 0 else 1.0
        windows: list[tuple[float, float]] = []
        cursor = 0.0
        for d in durs:
            windows.append((cursor * scale, (cursor + d) * scale))
            cursor += d
        speech_spans = source_speech_spans(windows, src_total)
        voice_dur = predicted or src_total
        audio_meta = {"mode": audio_mode, "estimated": True,
                      "speech_rate": rate,
                      "est_seconds": round(est, 3),
                      "voice_seconds": round(voice_dur, 3),
                      "chars": sum(len(t) for t in kept)}
        if voice_note:
            warnings.append(voice_note)

    # 🩸 勾了槽位却既没素材也没描述 = 一定白跑：
    #   · 换人没图 → 「替换为他自己」；
    #   · 产品/场景/服装没图也没写 → 火山「另一个产品」（模型自己编），H3 干脆不写。
    no_material = ""
    if spec is not None:
        _refs_now = dict(refs or {})
        if subject_image is not None:
            _refs_now.setdefault("person", subject_image)
        # 🩸 换装「逐个查」是**某一家**的能力，由那家 `caps` 说了算 ——
        #   核心层 `edit_spec` 不许认识型号名（2026-10-28 分离门抓到过）。
        #   解析口径与真正发请求同一处（`_ve._model_for`）。
        from app.services import models, video_edit as _ve
        _m = _ve._model_for(regen_channel, regen_model)
        _ad = models.adapter_for(
            model=_m, channel="" if regen_channel == "auto" else regen_channel)
        no_material = edit_spec_mod.missing_material(
            spec, _refs_now, person_asset=subject_asset,
            style_video=_style_video_of(cid, spec) is not None,
            audio_files=_audio_files_of(cid),
            model=_m,
            wardrobe_per_person=_ad.caps.wardrobe_check_per_person) or ""
        if no_material:
            blocked = f"{blocked} {no_material}".strip() if blocked else no_material
        else:
            # C4：删/换 BGM 但分离条件不成立 —— 预览就要说出来（真跑时同一道闸）
            _aud_err = audio_preflight(spec, _audio_files_of(cid))
            if _aud_err:
                blocked = f"{blocked} {_aud_err}".strip() if blocked else _aud_err

    wants_change = bool((regen_prompt or "").strip())
    if spec and (edit_spec_mod.has_change(spec) or spec.get("extra")):
        wants_change = True
    mode = (regen_mode or "auto").strip().lower()

    plan = None
    spans: list[tuple[float, float]] = []
    change = {"mode": "none", "still_calls": 0, "still_seconds": 0.0,
              "video_calls": 0, "video_seconds": 0.0, "keep_shots": 0,
              "label": "", "resolution": "", "inventory_used": False}
    # 缺素材时不再往下算：`_prepare` 会直接抛错（那是真跑的同一道闸），
    # 预览要的是把「缺什么」说清楚，不是把一个必然失败的方案算一半。
    if wants_change and not no_material:
        # 预览**不做视觉盘点**：盘点要调视觉模型（花钱），出片前不该为预览再花一次。
        # 代价是不知道"某段里没目标人物可留原片"，所以视频段数按上限报。
        # 🩸 但**已经盘过的缓存要读**（纯读文件、零花费）：真跑时 `render` 会拿这份
        # 缓存去点名"原片里哪一位"，预览不读就会写出另一句提示词 ——
        # 2026-10-24 实测：预览说「其中的人物」，真跑发的是「画面中央的人物（…）」，
        # 用户在界面上看到的提示词根本不是要发出去的那句。
        inventory = None
        if cid:
            try:
                from app.services import work as _work

                inventory = _work._load_inventory(cid)
            except Exception as e:  # noqa: BLE001
                log.warning("预览读盘点缓存失败，按无盘点处理：%s", e)
        if mode == "auto":
            d = _auto_decision(
                video, rec, spec=spec, regen_prompt=regen_prompt,
                regen_shots=regen_shots, regen_channel=regen_channel,
                regen_model=regen_model, subject_image=subject_image,
                subject_asset=subject_asset, refs=refs, inventory=inventory,
                audio_mode=audio_mode, speech_spans=speech_spans,
                style_video=_style_video_of(cid, spec),
            )
            plan = d["plan"]
            spans = d["spans"]
            still = d["still"]
            by_i = {int(s["i"]): s for s in d["shots"]}
            change = {
                "mode": "auto",
                "still_calls": len(still),
                "still_seconds": round(sum(float(by_i[i]["end"]) - float(by_i[i]["start"])
                                           for i in still if i in by_i), 3),
                "video_calls": len(spans),
                "video_seconds": round(sum(b - a for a, b in spans), 3),
                "keep_shots": sum(1 for m in d["disp"].values() if m == "keep"),
                "label": d["regen_meta"].get("label", ""),
                "resolution": d["regen_meta"].get("resolution", ""),
                "spans": [[round(a, 3), round(b, 3)] for a, b in spans],
                "inventory_used": bool(inventory),
            }
        elif mode == "whole":
            plan = video_edit.prepare(
                rec, prompt=regen_prompt, spec=spec, refs=refs,
                subject_image=subject_image, subject_asset=subject_asset,
                channel=regen_channel, model=regen_model, inventory=inventory,
                # 风格参考视频（A9）：不传进来，预览的提示词就少一句 @视频2，
                # 和真跑发出去的不是同一句
                style_video=_style_video_of(cid, spec),
            )
            # 分段只算一遍：出片走的是同一个 plan_spans，预览不可能和实际送模型的段数飘开
            spans, _ = video_edit.plan_spans(video, rec, plan)
            change = {
                "mode": "whole", "still_calls": 0, "still_seconds": 0.0,
                "video_calls": len(spans),
                "video_seconds": round(sum(b - a for a, b in spans), 3),
                "keep_shots": 0,
                "label": video_edit.spec_label(plan["ch"], plan["model"]),
                "resolution": plan["resolution"],
                "spans": [[round(a, 3), round(b, 3)] for a, b in spans],
                "inventory_used": bool(inventory),
            }
        else:  # shots
            picks = regen_shots or assemble.pick_shots(
                rec.get("shots") or [], regen_ratio, settings.clone_max_regen)
            by_i = {int(s["i"]): s for s in (rec.get("shots") or [])}
            change = {
                "mode": "shots", "still_calls": len(picks),
                "still_seconds": round(sum(float(by_i[i]["end"]) - float(by_i[i]["start"])
                                           for i in picks if i in by_i), 3),
                "video_calls": 0, "video_seconds": 0.0,
                "keep_shots": max(0, len(by_i) - len(picks)),
                "label": "", "resolution": "", "inventory_used": False,
            }
        if change["video_calls"] or change["still_calls"]:
            warnings.append("预览未做视觉盘点：视频段数按上限报，实际可能更少")

    # 🩸 只出前 N 段（2026-11-01）：确认框报的数字必须等于**这一下真会生成的东西**。
    #   真跑走 `render` 的 `max_segments` 分支（只生成前 N 段、不拼接），
    #   预览以前不认这个参数 ⇒ 用户点「先出第 1 段」，弹窗还写「2 段 / 18.067 秒」。
    #   这里把 `spans` 截断到前 N 段：段数、秒数、逐段提示词、报价全部跟着变，
    #   整片的总量另存 `total_*`，界面可以写成「1 段（整片共 2 段）」。
    if max_segments and spans and len(spans) > max_segments:
        change["partial"] = True
        change["total_video_calls"] = int(change["video_calls"])
        change["total_video_seconds"] = float(change["video_seconds"])
        spans = spans[:max_segments]
        change["video_calls"] = len(spans)
        change["video_seconds"] = round(sum(b - a for a, b in spans), 3)
        change["spans"] = [[round(a, 3), round(b, 3)] for a, b in spans]

    # 风格参考视频（A9）的时长预算：预览就把「这些段放不下」说出来，
    # 别等点了出片才被拦。判据和真跑是同一个函数（`_gen_spans` 里也叫它）。
    if plan is not None and spans and plan.get("style_video"):
        _clip, _style_err = video_edit.style_video_budget(
            plan["ch"], plan["model"], spans)
        if _style_err:
            blocked = f"{blocked} {_style_err}".strip() if blocked else _style_err

    # 🩸 提示词建议字数（官方 `volc-api:175`：中文 ≤500 字 / 英文 ≤1000 词）。
    #   只是**建议**，超了照发不拦 —— 但要让用户在点出片**之前**知道，并拿到
    #   可执行的下一步（少选一点 / 分两条出）。数值和话术都在 `edit_spec.prompt_advice`
    #   里，这里只从**已经算好的** `plan` 里带出去（不重复编一遍提示词）。
    #   `auto` 和 `whole` 两条路的 `plan` 都出自 `video_edit.prepare`，那边已算好。
    #   🩸 单独一个字段，不塞 `warnings`：前端确认框只显示 `warnings[0]`
    #   （`diagnose.vue`），而超 500 字的场景恰好也最容易撞上人数提醒 —— 塞进去会被挡住。
    prompt_advice = str((plan or {}).get("prompt_advice") or "")

    # 每段「模型到底会收到什么」：完整提示词 + 有没有挂音频 + 起止时间。
    # 🩸 预览不返回这些，验证就只能靠花钱真跑 —— 那是最贵的调试方式。
    segments: list[dict] = []
    if plan is not None and spans:
        from app.services import scene as scene_mod, work as work_mod

        audio_on = bool(plan.get("audio_ref"))
        want_audio = audio_on
        # 原声模式要真有音轨可抽；没有音轨的原片，真跑时这一段也不喂
        if audio_on and audio_mode == "original":
            try:
                audio_on = bool(scene_mod.probe(video).get("has_audio"))
            except Exception as e:  # noqa: BLE001
                log.warning("预览探测原片音轨失败：%s", e)
                audio_on = False
        # 🩸 2026-10-31 修「预览 ≠ 实发」：以前这里传 `assume_present=True`，
        #   按"每个人都在画面里"补占位 —— 那是**预览不读盘点**时代的补丁。
        #   现在预览已经读了盘点缓存（见上），占位反而会盖掉「这一段这个人不在」
        #   的真实结论，写出真跑不会发的那句话。直接按同一套输入算。
        prompts = work_mod._video_prompts(plan, spans, rec.get("shots") or [],
                                          audio_ref=audio_on, rec=rec)
        # 🩸 2026-11-02：这一家的提示词由**官方改写器**在出片时产出
        #   （`Caps.prompt_for`）。预览没有切片后的原片/配音/边界帧，给不出那一份，
        #   所以下面这版只能标成"参考，不会发出" —— 绝不能让它看起来像要发的东西。
        from app.services import models as _models_p

        _ir_on = _models_p.adapter_for(
            model=plan.get("model") or "",
            channel=plan.get("ch") or "").caps.prompt_for is not None
        for (a, b), p in zip(spans, prompts):
            segments.append({
                "start": round(a, 3),
                "end": round(b, 3),
                "duration": round(b - a, 3),
                # 判据和 `video_edit._seg_audio` 一致：短于 2s 的那段不喂
                "audio": bool(audio_on and (min(b, src_total) - a) >= 2.0),
                "prompt": p,
                # 这段指令是 `code`（代码拼）/ `agent`（读官方 skill 现写）/
                # `ir`（出片时由官方改写器按真实素材生成，这里这版只是参考）。
                # 同一段文字不同来源效果不一样，界面必须能标出来。
                "prompt_source": ("ir" if _ir_on else "code"),
            })
        if _ir_on:
            warnings.append("这一家的逐段提示词由官方改写器在出片时生成："
                            "下面这版只是按规则算的参考，不会发出去；"
                            "真正发出去的词在渲染目录的 request_00N.json 里")
        if want_audio and not audio_on:
            warnings.append("原片没有音轨：这一段不会喂音频，口型只能靠原片表演")
        if plan.get("person_ids"):
            warnings.append("预览不做视觉盘点：换人句按「这个人在这段里出现」写，"
                            "真跑时还会带上盘点给的外观定位（长相以参考图为准，不变）")

    # 🩸 agent 版逐段指令（2026-10-31）：界面点「用官方 skill 重新生成」才走这条。
    #   默认关闭 —— `/clone/{cid}/plan` 是"零费用"的语义，不能偷偷调模型烧钱。
    #   生成完会落盘（`prompts.json`），出片路径读的是**同一份**（`clone_agent.cached`），
    #   所以这里生成过一次，出片不再花钱第二次、也不会发出另一版。
    agent_error = ""
    if with_agent and segments and plan is not None and spans:
        # 🩸 2026-11-01：**按型号分派** —— 2.5 和 H3 是两套不通用的官方模板
        #   （中文五段标记 vs 英文六段式），各挂在自己的适配器上。
        from app.services import models as _models

        _agent = _models.adapter_for(model=plan.get("model") or "",
                                     channel=plan.get("ch") or "").agent
        # 🩸 2026-11-02：这家的逐段提示词由**官方改写器**在出片时产出
        #   （H3-Context-IR，见 `h3_ir`）。改写器要看的是**切片后的原片段 +
        #   这一段的参考图 + 配音切片** —— 预览阶段这些还没切、也不该为了
        #   预览去切一遍（切法已经有两处，第三处必然漂）。所以这里老老实实说清：
        #   出片时由官方改写器写，不在这里现编一份假装那就是要发的。
        _writer = _models.adapter_for(
            model=plan.get("model") or "",
            channel=plan.get("ch") or "").caps.prompt_for
        if _writer is not None:
            agent_error = ("这一家的逐段提示词由官方改写器在出片时生成"
                           "（H3-Context-IR：一句自然语言 + 这一段真正的素材），"
                           "预览这里不给改写结果；出片后实际发出去的提示词在"
                           "渲染目录的 request_00N.json 里")
        elif not cid:
            agent_error = "缺少任务号，无法落盘逐段指令"
        elif _agent is None:
            agent_error = "这个型号没有 agent 版逐段指令，用代码编译的那一版"
        else:
            _ca = _agent()
            try:
                data = _ca.generate(cid, plan, rec, spans, force=agent_force)
                got = {int(s.get("index") or 0): str(s.get("prompt") or "").strip()
                       for s in (data.get("segments") or [])}
                for i, seg in enumerate(segments, 1):
                    if got.get(i):
                        seg["prompt"] = got[i]
                        seg["prompt_source"] = "agent"
                warnings.append("逐段指令已由官方 skill 生成并落盘，出片用的就是这一版")
            except Exception as e:  # noqa: BLE001
                agent_error = str(e)
                log.warning("逐段指令生成失败，仍用代码编译版：%s", e)

    # 只出前 N 段时交付的是**片段**（真跑那边也不拼接，见 `render`），
    # 合同就按这一段的时长算；整片的数字留在 `change.total_video_seconds`，
    # 界面用它说清"还差多少没出"。
    target = (float(change["video_seconds"]) if change.get("partial")
              else max(src_total, voice_dur))
    frames = int(round(target * fps)) if fps > 0 else 0
    samples = int(round(frames / fps * 48000)) if fps > 0 and frames else 0

    # 单价只在配置了的情况下算；没配就明确说"未配置"，绝不拿记忆里的价格凑数。
    # 口径照 hypit 的 `pricing`：按请求**分组**报，未知的价格必须继续可见，
    # 只要有一组未知就不给总额 —— 不能拿"已知那几组"的和冒充总价。
    pv = float(settings.price_video_per_sec or 0)
    pi = float(settings.price_image_per_call or 0)
    pt = float(settings.price_tts_per_1k_chars or 0)
    groups = []
    if change["video_seconds"] > 0:
        groups.append({"key": "video", "label": "视频模型",
                       "requests": int(change["video_calls"]), "unit": "秒",
                       "units": float(change["video_seconds"]), "rate": pv,
                       "rate_source": "VT_PRICE_VIDEO_PER_SEC",
                       "known": pv > 0})
    if change["still_calls"] > 0:
        groups.append({"key": "image", "label": "静帧重绘",
                       "requests": int(change["still_calls"]), "unit": "次",
                       "units": float(change["still_calls"]), "rate": pi,
                       "rate_source": "VT_PRICE_IMAGE_PER_CALL",
                       "known": pi > 0})
    if audio_mode != "original" and audio_meta["chars"] > 0:
        groups.append({"key": "tts", "label": "配音",
                       "requests": 1, "unit": "千字",
                       "units": round(audio_meta["chars"] / 1000.0, 4), "rate": pt,
                       "rate_source": "VT_PRICE_TTS_PER_1K_CHARS",
                       "known": pt > 0})
    unknown = [g["key"] for g in groups if not g["known"]]
    known = not unknown
    amount = sum(g["units"] * g["rate"] for g in groups) if known else None

    return {
        "ok": not blocked,
        "blocked": blocked,
        "audio": audio_meta,
        "change": change,
        # 逐段「发给模型的东西」—— 出片前逐字可看，别靠花钱试
        "segments": segments,
        # 这一版提示词是谁写的：`code` = 代码按规则拼，`agent` = 读官方 skill 现写。
        # 出片时只有**签名对得上**的 agent 版才会被采用（见 `clone_agent.cached`），
        # 界面据此说明"现在看到的就是要发出去的"。
        "prompt_source": ("agent" if any(s.get("prompt_source") == "agent"
                                         for s in segments) else "code"),
        "agent_error": agent_error,
        "contract": {
            "duration": round(target, 3),
            "fps": fps,
            "frames": frames,
            "audio_sample_rate": 48000,
            "audio_samples": samples,
            "source_duration": round(src_total, 3),
        },
        "price": {
            "known": known,
            "amount": round(amount, 2) if known else None,
            "currency": "CNY",
            "groups": groups,
            "unknown": unknown,
            # hypit `pricing` 的原话：读价格，不提交生成，也不保证总价准确。
            # 配音时长是估的，成片时长会变 —— 把这句话原样交给界面。
            "note": "按已配置单价估算，不承诺准确总价（配音时长是估算）",
        },
        "voice": {"id": voice_id if audio_mode != "original" else "",
                  "label": voice_catalog.label(voice_id) if audio_mode != "original" else "",
                  "lang": lang},
        # 人数判定原文（含 suggest_model）：界面据此弹"切到 2.5"，不用自己再算一遍
        "subject": gate or {},
        "warnings": warnings,
        # 提示词建议字数的提醒（官方「中文 ≤500 字 / 英文 ≤1000 词」）。
        # 空串 = 没超。**不阻断**，界面单独显示一行，别和 warnings 抢那一个位置。
        "prompt_advice": prompt_advice,
    }


def _span_intervals(
    clips: list[Path],
    spans: list[tuple[float, float]],
    shots: list[dict],
    *,
    only: set[int],
) -> list[tuple[float, float, Path, float]]:
    """把每段重制结果裁回**判成 video 的镜头范围**，返回时间区间。

    返回 [(起, 止, 素材, 素材里的起点)]，交给 `assemble.build_intervals` 拼。

    🩸 为什么按区间、不按镜头：模型单次只收 15s，一镜 28.3s 的"一镜到底"
    必然被切成 15s + 13.3s 两段。按镜头收口时一个镜头只能放一条素材，
    另一段就被丢掉、时间轴上冻帧补足 —— 成片后半段不动、声音还在走
    （2026-10-21 实测：28.3s 片子在 14.97s 之后画面全冻）。
    旧实现还多一道"重叠必须 ≥ 镜头一半"的门，13.3/28.3=47% 正好被它扔掉。

    `only` 是判成 video 的镜头号：区间为了凑够模型下限会往外撑，
    撑到邻居镜头身上时**不能把邻居也替换掉** —— 那些镜头是按"保留原片"
    或者"静帧重绘"处置的。

    `covered` 是"时间轴上已经排到哪"：段和段之间允许**参考重叠**（尾巴太短时
    起点往回借，见 `triage._split_run`），但时间轴上的画面不能重复 ——
    上一段已经排过的范围直接跳过。
    """
    from app.services import assemble as _asm

    out: list[tuple[float, float, Path, float]] = []
    covered = 0.0
    for (a, b), clip in zip(spans, clips):
        # 这一段素材**实际有多长**：2.5 的编辑任务会比输入短（官方最多约 0.3 秒），
        # 尾段没有多余原片可补时 `_gen_spans` 就按实际长度出片 —— 这里必须按
        # 素材的真实长度收口，否则时间轴会伸到素材之外，后面只能回灌原片
        # （那正是"最后一帧变回原脸"）。
        clip_dur = _asm._probe_duration(Path(clip))
        for s in shots:
            if int(s["i"]) not in only:
                continue
            lo = max(float(a), float(s["start"]), covered)
            hi = min(float(b), float(s["end"]),
                     float(a) + clip_dur if clip_dur > 0 else float(b))
            if hi - lo < 0.05:
                continue
            out.append((lo, hi, Path(clip), lo - float(a)))
            covered = hi
    return out


def _p(cb, stage: str, pct: int) -> None:
    if cb:
        try:
            cb(stage, pct)
        except Exception:  # noqa: BLE001
            pass


def _clamp_tempo(ratio: float, lo: float = 0.80, hi: float = 1.25) -> float:
    return max(lo, min(hi, ratio))


_MAX_LINE = 14   # 一句文案最多这么多字，超了要断
_MIN_LINE = 4    # 尾巴少于这么多字就并回上一行，避免"一屏一个字"


def _split_script(script: str, n: int) -> list[str]:
    """按句子断文案，不按镜头数硬切。

    n（原片段数）只是提示：原片有 60 个镜头不代表新文案要切成 60 行。
    切分只依据文案本身 —— 句末标点＞逗号＞按字数硬切，
    段落数交给 TTS 后的真实时长去决定时间轴。
    """
    script = (script or "").strip()
    if not script:
        return [""] * max(1, n)

    # 1) 先按句末标点断
    sents = [s.strip() for s in re.split(f"[{_PUNCT}]+", script) if s.strip()]
    if not sents:
        sents = [script]

    # 2) 短句合并，攒到接近一行上限
    merged: list[str] = []
    buf = ""
    for s in sents:
        if buf and len(buf) + len(s) <= _MAX_LINE:
            buf += s
        else:
            if buf:
                merged.append(buf)
            buf = s
    if buf:
        merged.append(buf)

    # 3) 仍然超长的：先按逗号/顿号断，断不开再按字数切
    out: list[str] = []
    for s in merged:
        if len(s) <= _MAX_LINE:
            out.append(s)
            continue
        parts = [p.strip() for p in re.split("[，,、：:]+", s) if p.strip()]
        if len(parts) > 1 and max(len(p) for p in parts) <= _MAX_LINE:
            out.extend(parts)
        else:
            out.extend(s[i:i + _MAX_LINE] for i in range(0, len(s), _MAX_LINE))

    # 4) 尾巴太短并回上一行
    if len(out) > 1 and len(out[-1]) < _MIN_LINE:
        out[-2] += out.pop()
    return out


def _build_segments(windows: list[tuple[float, float]], texts: list[str]) -> list[dict]:
    """按窗口和文本生成逐句文案段，字在窗口内按字长加权分配。"""
    segs = []
    for (s, e), t in zip(windows, texts):
        t = (t or "").strip()
        if not t:
            continue
        span = max(0.05, e - s)
        step = span / len(t)
        segs.append({
            "start": round(s, 3),
            "end": round(e, 3),
            "text": t,
            "chars": [
                {"c": c, "s": round(s + i * step, 3), "e": round(s + (i + 1) * step, 3)}
                for i, c in enumerate(t)
            ],
        })
    return segs


def source_speech_spans(windows,
                        src_total: float) -> list[tuple[float, float]]:
    """把新配音的说话区间换算成**源片时间轴**上的区间。

    🩸 这里**不做任何缩放**：合成的画面从 0 秒原速播放，配音也从 0 秒开始播，
    两条时间轴本来就是同一条（compose 不改视频 speed，只在末尾冻帧补时长）。
    新配音比画面短就只是后半段没人说话，不是"被拉伸铺满全片"。
    早期版本按 src_total/voice_dur 缩放，前提就不成立 —— 会把后半段静音
    也算成有人在说话。

    唯一要做的是截到源片长度，避免区间越过片尾。
    """
    if src_total <= 0:
        return []
    out: list[tuple[float, float]] = []
    for s, e in windows or []:
        a = max(0.0, float(s))
        b = min(float(src_total), float(e))
        if b - a > 0.05:
            out.append((round(a, 3), round(b, 3)))
    return out


def _partial_voice(video: Path, spans: list[tuple[float, float]],
                   clips: dict[int, Path], out: Path, *, workdir: Path) -> Path:
    """**只重配其中几个人**：原片音轨打底，被点到的几句换成新配音。

    为什么要打底而不是只拼新配音：没被点到的那些人说的话还在原片里，
    只拼新配音等于把他们的声音删了。做法是
      ① 原片音轨在**被重配的区间**里静音（其余原样，含背景音）；
      ② 每段新配音先 `atempo` 拉到原片那一段的时长，再 `adelay` 放到原位置；
      ③ 两条混在一起（`normalize=0`，不做音量平均，否则原声会被压低）。

    🩸 单段对齐而不是整条缩放：整条 atempo 会把"没重配的人"的原声一起拉伸，
    听起来变速。只有新配音该被拉。

    `spans[i]` = 第 i 行在原片上的 (start, end)；`clips` 只含被重配的行。
    零模型调用，纯本地 ffmpeg。
    """
    ff = ffmpeg_path()
    if not ff:
        raise RuntimeError("找不到 ffmpeg")
    if not clips:
        raise RuntimeError("没有要重配的行")

    # 每段拉到原片这一段的时长（夹在 atempo 的安全区间 0.8–1.25）
    idx = sorted(clips)
    ins: list[str] = []
    filters: list[str] = []
    for n, i in enumerate(idx, start=1):
        a, b = spans[i]
        want = max(0.2, float(b) - float(a))
        got = float(scene.probe(clips[i]).get("duration") or 0.0)
        tempo = (got / want) if got > 0 else 1.0
        tempo = max(0.8, min(1.25, tempo))
        delay = int(round(float(a) * 1000))
        filters.append(
            f"[{n}:a]aformat=channel_layouts=mono,atempo={tempo:.4f},"
            f"adelay={delay}|{delay}[s{n}]")
        ins += ["-i", str(clips[i])]

    # 原片在每段区间静音
    mutes = ",".join(f"volume=enable='between(t,{spans[i][0]:.3f},"
                     f"{spans[i][1]:.3f})':volume=0" for i in idx)
    tail = "".join(f"[s{n}]" for n in range(1, len(idx) + 1))
    # 🩸 每一条 filter 后面必须跟 `;` —— 少了就是 `[s1][base]` 粘在一起，
    # ffmpeg 报 "garbage after a filter"（2026-10-27 实测踩到）
    fc = "".join([f"[0:a]aformat=channel_layouts=mono,{mutes}[base];"]
                 + [f + ";" for f in filters]
                 + [f"[base]{tail}amix=inputs={len(idx) + 1}:duration=first:"
                    "dropout_transition=0:normalize=0[out]"])

    proc = subprocess.run(
        [ff, "-hide_banner", "-loglevel", "error", "-y", "-i", str(video), *ins,
         "-filter_complex", fc, "-map", "[out]", "-ar", "48000", "-ac", "1",
         str(out)],
        capture_output=True, text=True, errors="ignore", timeout=600,
    )
    if proc.returncode != 0 or not out.exists() or out.stat().st_size == 0:
        raise RuntimeError(f"部分重配混音失败: {(proc.stderr or '')[-400:]}")
    return out


def _concat_audio(parts: list[Path], out: Path, *, tempo: float, workdir: Path) -> Path:
    """把逐段配音拼成一条，并按 tempo 调整到目标时长。"""
    ff = ffmpeg_path()
    if not ff:
        raise RuntimeError("找不到 ffmpeg")

    lst = workdir / "voice_list.txt"
    lst.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in parts),
        encoding="utf-8",
    )
    chain = f"atempo={tempo:.4f}" if abs(tempo - 1.0) > 0.01 else "anull"
    proc = subprocess.run(
        [ff, "-hide_banner", "-loglevel", "error", "-y",
         "-f", "concat", "-safe", "0", "-i", str(lst),
         # 统一 48k：成片音轨也按 48k 收口，音画合同按同一采样率核对
         "-filter:a", chain, "-ar", "48000", "-ac", "1", str(out)],
        capture_output=True, text=True, errors="ignore", timeout=300,
    )
    if proc.returncode != 0 or not out.exists():
        raise RuntimeError(f"配音拼接失败: {(proc.stderr or '')[-400:]}")
    return out
