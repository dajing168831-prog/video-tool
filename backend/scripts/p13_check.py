"""P13 验收：原片声音的后期处理（C4：删/换 BGM、加音效）。

零模型调用、不花钱。分离服务和 ffmpeg 全部用桩或本地合成音，**不产生任何费用**。

  S1  字段与签名   —— `EditIn` 必须声明（pydantic 会静默丢键）；不进模型分段哈希
  S2  归一化       —— 非法值落回 keep，不抛错
  S3  取轨矩阵     —— audio × bgm × sfx 六种组合逐条对齐设计表
  S4  原对白       —— original + drop 必须保留 voice 轨（删 BGM ≠ 删人声）
  S5  分离失败     —— 点名要动 BGM 时**不许**静默退回原整轨
  S6  换 BGM       —— 循环/裁到成片时长（真 ffmpeg，合成音源）
  S7  加音效       —— 叠加后仍在，且和原轨一起进 bed
  S8  出片前拦截   —— 分离条件不成立时 blocked（别等模型钱花完）
  S9  界面与接线   —— 两行入口、上传/删除 API、detail 回传 audio_refs

为什么只做后期、不写音频提示词（这条决定了整个设计的形状）：
  成片音轨由 `tracks.from_legacy` 用 voice(TTS) + bg_from 两条输入拼出来，
  模型产出的那一路音频**不进合成**。2.5 官方的「声音编辑」模板
  （`sd25-pe:614-635`）在我们链路里无处落地 —— 写了也不会改到成片的声音。
  删 BGM 合法且不需要目标素材，官方 `sd25-pe:635` 明说；后期分离会连音效
  一起丢掉（`V25:870` 官方自己写的），所以我们用三轨（voice/music/sfx）绕开。

跑法：python scripts/p13_check.py --model volc20|volc25|h3
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import clone_pipeline as cp  # noqa: E402
from app.services import edit_spec, scene, video_edit  # noqa: E402
from app.services.providers import separate as sep_mod  # noqa: E402

FRONT = ROOT.parent / "frontend" / "app" / "src"
DIAG = FRONT / "pages" / "clone" / "diagnose.vue"
REQ = FRONT / "api" / "request.js"

rows: list[tuple[str, bool, str]] = []

# 🚦 必须点名型号（2026-10-26）：一轮只跑一家。
from _model_gate import sel_or_exit as _sel_or_exit
SEL = _sel_or_exit()


def chk(name: str, ok, detail: str = "") -> None:
    rows.append((name, bool(ok), detail if not ok else ""))


TMP = Path(tempfile.mkdtemp(prefix="p13_", dir="D:/tmp"))


# ---------------------------------------------------------------------------
# 桩：分离器与混音器（不联网、不花钱）

def _mk(name: str) -> Path:
    p = TMP / name
    p.write_bytes(b"STUB")
    return p


VOICE = _mk("voice.wav")
MUSIC = _mk("music.wav")
SFX = _mk("sfx.wav")
SRC = _mk("source.mp4")
USER_BGM = _mk("user_bgm.mp3")
USER_SFX = _mk("user_sfx.wav")

_real_sep_tracks = cp._separate_tracks
_real_merge = sep_mod.merge
_real_fit = sep_mod.fit_loop
_real_avail = sep_mod.available

state: dict = {}


def stub_merge(paths, dest, gains=None):
    state["parts"] = [Path(p).name for p in paths]
    state["gains"] = gains
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"BED")
    return dest


def stub_fit(src, dest, seconds):
    state["fit"] = (Path(src).name, round(float(seconds), 2))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"FIT")
    return dest


def stub_sep(got, err=""):
    def _f(video, rec, workdir):
        return got, err
    return _f


def run_bed(audio: str, bgm: str, sfx: str, *, sep_fail: str | None = None,
            files: dict | None = None) -> tuple:
    """跑一次 `_audio_bed`，返回 (bed 名字或 None, err, 实际参与混合的源)。"""
    state.clear()
    if sep_fail is None:
        cp._separate_tracks = stub_sep(
            {"voice": VOICE, "music": MUSIC, "sfx": SFX})  # type: ignore
    else:
        cp._separate_tracks = stub_sep(None, sep_fail)  # type: ignore
    spec = edit_spec.normalize({"audio": audio, "bgm": bgm, "sfx": sfx})
    rec = {"source": {"has_audio": True}, "speech": {"segments": [{"text": "x"}]}}
    bed, e = cp._audio_bed(SRC, rec, TMP / "wk", spec, total_sec=10.0,
                           audio_files=files if files is not None
                           else {"bgm": USER_BGM, "sfx": USER_SFX})
    merged = state.get("parts") or ([Path(bed).name] if bed else [])
    return (Path(bed).name if bed else None), e, merged


sep_mod.merge = stub_merge          # type: ignore[assignment]
sep_mod.fit_loop = stub_fit        # type: ignore[assignment]

# ---------------------------------------------------------------------------
# S1 字段与签名

from app.api.clone import EditIn  # noqa: E402

md = EditIn(**{"bgm": "drop", "sfx": "add"}).model_dump()
chk("S1 EditIn 声明了 bgm/sfx（pydantic 会静默丢未声明键）",
    md.get("bgm") == "drop" and md.get("sfx") == "add", f"{md.get('bgm')}/{md.get('sfx')}")

sp = edit_spec.normalize({"person": True, "bgm": "drop", "sfx": "add"})
hashed = video_edit._spec_for_hash(sp)
chk("S1 bgm/sfx 不进模型分段哈希（否则「只删个 BGM」会把整片重画）",
    "bgm" not in hashed and "sfx" not in hashed, str(list(hashed)))

plain = video_edit._spec_for_hash(edit_spec.normalize({"person": True}))
chk("S1 默认规格的哈希里也没有这两个键（历史记录不失配）",
    "bgm" not in plain and "sfx" not in plain, str(list(plain)))

# ---------------------------------------------------------------------------
# S2 归一化

d = edit_spec.defaults()
chk("S2 默认是全保留（老行为，不触发分离）",
    d["bgm"] == "keep" and d["sfx"] == "keep", f"{d['bgm']}/{d['sfx']}")

bad = edit_spec.normalize({"bgm": "mute", "sfx": "kill"})
chk("S2 非法值落回 keep，不抛错",
    bad["bgm"] == "keep" and bad["sfx"] == "keep", f"{bad['bgm']}/{bad['sfx']}")

ok_all = edit_spec.normalize({"bgm": "REPLACE", "sfx": "ADD"})
chk("S2 大小写不敏感",
    ok_all["bgm"] == "replace" and ok_all["sfx"] == "add",
    f"{ok_all['bgm']}/{ok_all['sfx']}")

# ---------------------------------------------------------------------------
# S3 取轨矩阵

cases = [
    ("original", "keep", "keep", ["source.mp4"], "原声整轨（不分离）"),
    ("original", "drop", "keep", ["voice.wav", "sfx.wav"], "删 BGM：留对白+音效"),
    ("original", "drop", "add", ["voice.wav", "sfx.wav", "user_sfx.wav"], "删 BGM 再加音效"),
    ("mix", "keep", "keep", ["music.wav", "sfx.wav"], "mix 老行为"),
    ("mix", "drop", "keep", ["sfx.wav"], "mix 删 BGM"),
    ("tts", "keep", "keep", [], "tts 不要原片任何声音"),
    ("tts", "replace", "keep", ["bgm_fit.wav"], "tts 铺新 BGM"),
    ("mix", "replace", "keep", ["sfx.wav", "bgm_fit.wav"], "mix 换 BGM（音效还在）"),
]
for audio, bgm, sfx, want, label in cases:
    bed, err, got = run_bed(audio, bgm, sfx)
    chk(f"S3 {audio}/{bgm}/{sfx} → {label}", got == want and not err,
        f"got={got} want={want} err={err}")

bed, err, got = run_bed("tts", "keep", "keep")
chk("S3 tts 全保留 = 没有底音轨（bed 为 None）", bed is None and not err, str(bed))

# 分离到底有没有被触发：original+keep 不该调分离（省钱）
calls: list[int] = []
cp._separate_tracks = lambda v, r, w: (calls.append(1), (None, ""))[1]  # type: ignore
edit_spec_keep = edit_spec.normalize({"audio": "original", "bgm": "keep", "sfx": "keep"})
cp._audio_bed(SRC, {"source": {"has_audio": True}, "speech": {"segments": []}},
              TMP / "wk", edit_spec_keep, total_sec=10.0, audio_files={})
chk("S3 original+keep 不触发分离（零额外成本）", calls == [], f"calls={len(calls)}")

# ---------------------------------------------------------------------------
# S4 原对白必须留下

bed, err, got = run_bed("original", "drop", "keep")
chk("S4 original+drop 保留 voice 轨（删 BGM ≠ 删人声）", "voice.wav" in got, str(got))
chk("S4 original+drop 不含 music 轨", "music.wav" not in got, str(got))

bed, err, got = run_bed("mix", "drop", "keep")
chk("S5 mix+drop 不取 voice 轨（对白由新配音负责，取回来会两个人在说话）",
    "voice.wav" not in got, str(got))

# ---------------------------------------------------------------------------
# S5 分离失败：不许静默退回

bed, err, got = run_bed("original", "drop", "keep", sep_fail="接口 500")
chk("S5 删 BGM 但分离失败 → 必须报错（不许返回原整轨）", bool(err) and bed is None,
    f"bed={bed} err={err}")
chk("S5 报错文案说清了后果并给了退路",
    "分离" in (err or "") and "保留原片" in (err or ""), (err or "")[:120])

bed, err, got = run_bed("mix", "keep", "keep", sep_fail="接口 500")
chk("S5 mix 没点名动 BGM 时仍可退回原整轨（老行为）",
    not err and got == ["source.mp4"], f"bed={bed} err={err} got={got}")

# ---------------------------------------------------------------------------
# S6 换 BGM 的时长对齐（真 ffmpeg，本地合成音）

sep_mod.fit_loop = _real_fit  # 恢复真实现
ff = scene.ffmpeg_path()
src_wav = TMP / "tone.wav"
subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                "-i", "anullsrc=r=48000:cl=mono", "-t", "1.0", str(src_wav)],
               check=False)
fit_out = TMP / "fit.wav"
try:
    sep_mod.fit_loop(src_wav, fit_out, 3.0)
    got_dur = float(scene.probe(fit_out).get("duration") or 0)
except Exception as e:  # noqa: BLE001
    got_dur = -1
    print("  fit_loop 异常：", e)
chk("S6 1 秒的音源循环到 3 秒（成片有多长就铺多长）",
    abs(got_dur - 3.0) <= 0.15, f"duration={got_dur}")
sep_mod.fit_loop = stub_fit  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# S7 加音效

bed, err, got = run_bed("mix", "keep", "add")
chk("S7 加音效：新音效和原背景一起进 bed",
    "user_sfx.wav" in got and "music.wav" in got, str(got))
bed, err, got = run_bed("original", "keep", "add")
chk("S7 原声 + 加音效不需要分离（省一次分离费）",
    got == ["source.mp4", "user_sfx.wav"], str(got))

# ---------------------------------------------------------------------------
# S8 出片前拦截

_real_avail2 = sep_mod.available
sep_mod.available = lambda: False  # type: ignore[assignment]
err = cp.audio_preflight({"bgm": "drop"}, {})
chk("S8 没配分离服务 + 要删 BGM → 出片前就拦住", "MEDIAKIT" in err, err[:120])
err_keep = cp.audio_preflight({"bgm": "keep"}, {})
chk("S8 没配分离服务但不动 BGM → 不拦（老路径照跑）", err_keep == "", err_keep)
sep_mod.available = _real_avail2  # type: ignore[assignment]

err = cp.audio_preflight({"bgm": "replace"}, {"bgm": None})
chk("S8 选「换成我上传的」但没有文件 → 拦住", "上传" in err, err[:120])

miss = edit_spec.missing_material(edit_spec.normalize({"bgm": "replace"}), {},
                                  audio_files={})
chk("S8 缺 BGM 文件在 missing_material 也拦一道", "背景音乐" in miss, miss[:120])
miss_ok = edit_spec.missing_material(edit_spec.normalize({"bgm": "drop"}), {})
chk("S8 删 BGM 不需要素材（官方 `sd25-pe:635`）", miss_ok is None, str(miss_ok))

# ---------------------------------------------------------------------------
# S9 界面与接线

diag = DIAG.read_text(encoding="utf-8", errors="ignore")
req = REQ.read_text(encoding="utf-8", errors="ignore")
api = (ROOT / "app" / "api" / "clone.py").read_text(encoding="utf-8")
store = (ROOT / "app" / "services" / "clone_store.py").read_text(encoding="utf-8")

chk("S9 请求体里带两个字段", "bgm: 'keep'" in diag and "sfx: 'keep'" in diag, "")
chk("S9 界面有两行入口（BGM / 音效）",
    "bgmOpts" in diag and "sfxOpts" in diag, "")
chk("S9 上传/删除/试听三个端点都在",
    '"/clone/{cid}/audio/{kind}"' in api
    and "clone_audio_delete" in api and "clone_audio_file" in api, "")
chk("S9 前端有上传/删除调用", "cloneUploadAudio" in req and "cloneDeleteAudio" in req, "")
chk("S9 detail 回传 audio_refs（界面按文件显示已上传）",
    '"audio_refs"' in store, "")
from app.api.clone import audio_only_problem  # noqa: E402

chk("S9 纯音频（只有音轨、没有画面）→ 放行",
    audio_only_problem({"has_audio": True, "width": 0}) == "", "")
chk("S9 带音轨的视频 → 拒（判流不判后缀：mp4 改名成 .mp3 也拦得住）",
    "带画面的视频" in audio_only_problem({"has_audio": True, "width": 320}), "")
chk("S9 没有音轨的文件 → 拒",
    audio_only_problem({"has_audio": False, "width": 0}) != "", "")

# ---------------------------------------------------------------------------
cp._separate_tracks = _real_sep_tracks  # type: ignore[assignment]
sep_mod.merge = _real_merge            # type: ignore[assignment]
sep_mod.fit_loop = _real_fit           # type: ignore[assignment]
sep_mod.available = _real_avail        # type: ignore[assignment]

bad_rows = [r for r in rows if not r[1]]
for name, ok, detail in rows:
    print(("  ok   " if ok else "  FAIL ") + name
          + (f"  [{detail[:220]}]" if not ok else ""))
print(f"\n{len(rows) - len(bad_rows)}/{len(rows)} 通过（零模型调用）")
sys.exit(1 if bad_rows else 0)
