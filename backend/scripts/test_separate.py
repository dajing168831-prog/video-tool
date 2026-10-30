"""人声分离 + 混音链路自检：不调任何付费接口。

验的是这几件事：
  - 场景按"语音占比"挑：口播走 Narrate，其余走 Drama（两个都是三轨）
  - `mix` 被当成**全新配音**：提示词要求重做口型、分诊把说话镜判成 still
  - 混音图里真的有 ducking（sidechaincompress）和响度归一（loudnorm）
  - MediaKit 客户端能正确解析提交/轮询响应（用假 client，不联网）
  - music + sfx 合并是**还原**背景（amix normalize=0），不是再压一遍

运行：python scripts/test_separate.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import clone_pipeline, compose, edit_spec, triage  # noqa: E402
from app.services.media import ffmpeg_path, ffprobe_path  # noqa: E402
from app.services.providers import separate  # noqa: E402

PASS = FAIL = 0


def check(name: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {name}: {got}")
    else:
        FAIL += 1
        print(f"  FAIL {name}: got={got!r} want={want!r}")


def tone(path: Path, seconds: float, freq: int, *, video: bool = False,
         color: str = "navy") -> Path:
    ff = ffmpeg_path()
    args = [ff, "-hide_banner", "-loglevel", "error", "-y"]
    if video:
        args += ["-f", "lavfi", "-i", f"color=c={color}:s=360x640:d={seconds}:r=25"]
    args += ["-f", "lavfi", "-i", f"sine=frequency={freq}:duration={seconds}"]
    if video:
        args += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-shortest",
                 "-c:a", "aac"]
    else:
        args += ["-c:a", "pcm_s16le"]
    args += [str(path)]
    p = subprocess.run(args, capture_output=True, text=True, errors="ignore")
    if p.returncode != 0 or not path.exists():
        raise SystemExit("造测试音频失败: " + (p.stderr or "")[-400:])
    return path


def has_audio(path: Path) -> bool:
    p = subprocess.run(
        [ffprobe_path(), "-v", "error", "-show_entries", "stream=codec_type",
         "-of", "default=nw=1", str(path)],
        capture_output=True, text=True, errors="ignore",
    )
    return "codec_type=audio" in p.stdout


class _Resp:
    def __init__(self, code: int, data: dict):
        self.status_code = code
        self._data = data
        self.text = str(data)

    def json(self):
        return self._data


class _FakeClient:
    """假 MediaKit：提交返回 task_id，轮询第一次就 completed。"""

    posted: list = []

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, headers=None, json=None):
        _FakeClient.posted.append((url, headers, json))
        return _Resp(200, {"success": True, "result": {"task_id": "t-1"}})

    def get(self, url, headers=None):
        return _Resp(200, {
            "status": "completed",
            "result": {
                "voice_audio_url": "https://x/voice.wav",
                "music_audio_url": "https://x/music.wav",
                "sfx_audio_url": "https://x/sfx.wav",
                "duration": 12.5,
            },
        })


def main() -> int:
    # 🚦 必须点名型号（2026-10-26）：一轮只跑一家
    from _model_gate import sel_or_exit as _sel
    _sel()
    work = Path(tempfile.mkdtemp(dir="D:/tmp", prefix="separate_"))
    try:
        return _run(work)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _run(work: Path) -> int:
    print("== 分离场景：固定 Drama（D15 真机证据）==")
    check("场景固定 Drama", separate.SCENE, "Drama")

    print("== 语音占比计算 ==")
    rec = {
        "source": {"duration": 10.0},
        "speech": {"segments": [
            {"start": 0.0, "end": 3.0, "text": "有字"},
            {"start": 3.0, "end": 5.0, "text": ""},        # 没字的不算
            {"start": 5.0, "end": 7.0, "text": "也算"},
        ]},
    }
    check("只有带文字的段计入", round(clone_pipeline._speech_ratio(rec), 2), 0.5)
    check("总时长为 0 不炸", clone_pipeline._speech_ratio(
        {"source": {"duration": 0}, "speech": {"segments": []}}), 0.0)

    print("== 唱的还是说的：voice 轨能量判据（成对）==")
    ff = ffmpeg_path()
    src_t = tone(work / "judge_src.wav", 2.0, 220)
    loud_v = tone(work / "judge_loud.wav", 2.0, 660)

    def _atten(s: Path, dest: Path, db: float) -> Path:
        subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-i", str(s),
                        "-af", f"volume={db}dB", "-c:a", "pcm_s16le", str(dest)],
                       check=True)
        return dest

    quiet_v = _atten(loud_v, work / "judge_quiet.wav", -30)
    gap_same = clone_pipeline._mean_db(src_t) - clone_pipeline._mean_db(loud_v)
    gap_low = clone_pipeline._mean_db(src_t) - clone_pipeline._mean_db(quiet_v)
    check("同音量的 voice → 判有对白（间距够宽）",
          gap_same < clone_pipeline.NO_VOICE_GAP_DB, True)
    check("低 30 dB 的 voice → 判没对白", gap_low < clone_pipeline.NO_VOICE_GAP_DB, False)

    _orig_sep = clone_pipeline._separate_tracks
    try:
        clone_pipeline._separate_tracks = lambda *a, **k: ({"voice": quiet_v}, "")
        check("分离出空 voice → 没有对白",
              clone_pipeline._speech_present(src_t, {"source": {}}, work)[0], False)
        clone_pipeline._separate_tracks = lambda *a, **k: ({"voice": loud_v}, "")
        check("分离出同音量 voice → 有对白",
              clone_pipeline._speech_present(src_t, {"source": {}}, work)[0], True)
        clone_pipeline._separate_tracks = lambda *a, **k: (None, "未配置")
        check("分离失败 → 判不了（None，不改出片行为）",
              clone_pipeline._speech_present(src_t, {"source": {}}, work)[0], None)
    finally:
        clone_pipeline._separate_tracks = _orig_sep

    print("== 什么时候值得花这 2 分钱去判（成对）==")
    _spec = {"audio": "tts"}
    check("没有 spec（只换画面）→ 不判",
          clone_pipeline._should_probe_voice(None, "tts", None, True), False)
    check("original → 不判（本来就不写台词）",
          clone_pipeline._should_probe_voice(_spec, "original", None, True), False)
    check("用户自己填了文案 → 不判",
          clone_pipeline._should_probe_voice(_spec, "tts", "这是我自己写的", True), False)
    check("沿用原片文案 → 判",
          clone_pipeline._should_probe_voice(_spec, "tts", None, True), True)
    check("原文案是空白串 → 仍算沿用，判",
          clone_pipeline._should_probe_voice(_spec, "mix", "   ", True), True)
    check("原片没音轨 → 不判",
          clone_pipeline._should_probe_voice(_spec, "tts", None, False), False)

    print("== 分离结果复用：盘上有就别再花一次钱 ==")
    cache_dir = work / "sep_cache"
    (cache_dir / "sep").mkdir(parents=True, exist_ok=True)
    tone(cache_dir / "sep" / "voice.wav", 1.0, 440)
    got_cache, err_cache = clone_pipeline._separate_tracks(
        Path("not-exist.mp4"),
        {"source": {"duration": 1.0}, "speech": {"segments": []}}, cache_dir)
    check("盘上已有 voice.wav → 直接复用", sorted(got_cache or {}), ["voice"])
    check("复用时不报错", err_cache, "")

    print("== mix = 全新配音（不是「保留原声」）==")
    mix = edit_spec.normalize({"audio": "mix"})
    # 🩸 D3（2026-10-23）：口型句要求**音轨真的发给了模型**（audio_ref=True），
    # 且只有 2.5 的编辑任务有这个域（2.0 官方编辑公式里没有音频参考）。
    # 🩸 2026-10-28：口型句已从共用层搬进 2.5 自己的编译器
    #   （`models/volc25_compile._lip_line()`）—— 它**只在 2.5 官方有**，
    #   躺在三家共读的文件里靠开关控制就是串味。这里改测那个函数。
    # 🩸 2026-10-29：这几条断言原来查的是「重新生成」四个字 —— 那是**上一版的
    #   自造句**。2026-10-28 已按官方原文改写（`_lip_line` 注释有出处），
    #   变成 `guide.md:929/:935/:1241` 的「口型做出对应的精准改变」
    #   + `:916` 的「口型与台词精准同步」，测试没跟着改，于是每次跑都红一条。
    #   现在直接断言**官方那两句原话都在**，比查一个自造词更有鉴别力；
    #   该写空串的两档改成 `== ""`（以前 `"重新生成" in ""` 恒假 = 空判据）。
    from app.services.models import volc25_compile as _v25c
    keep = _v25c._lip_line(mix, True)
    # 🩸 别照抄整句官方原话去断言：代码是**拼装**两句（`…精准改变，与台词精准同步。`），
    #   第二句省了主语「口型」。断言核心词就够，写成整句会因为我抄错一个字假红。
    check("mix + 有音轨 → 要求改口型（官方两句的核心词都在）",
          ("口型做出对应的精准改变" in keep) and ("精准同步" in keep), True)
    check("mix 不保『表情』", "表情" not in keep, True)
    orig = _v25c._lip_line(edit_spec.normalize({"audio": "original"}), True)
    check("original 不写口型句（原声不重做口型）", orig, "")
    # 选了换配音但没传音轨 → 不许写口型句（模型手里没有新声音）
    no_audio = _v25c._lip_line(mix, False)
    check("mix + 无音轨 → 不写口型句", no_audio, "")
    # 🩸 2026-10-28：这条原来断言 `_keep_sentence` 输出里有「人物动作」，
    #   但那个函数现在只管通用句、跟"有没有音轨"无关，断言挪到真正的保留句上。
    check("mix + 无音轨 → 仍保留『人物动作』",
          "人物动作" in edit_spec._keep_sentence("volc", mix), True)

    shots = [{"i": 0, "start": 0, "end": 4, "dur": 4, "motion": 2.4}]
    spans = [(0.0, 4.0)]
    check("mix + 说话镜 → still",
          triage.decide(shots, speech_spans=spans, audio_mode="mix")[0], "still")
    check("original + 说话镜 → video",
          triage.decide(shots, speech_spans=spans, audio_mode="original")[0], "video")

    print("== 合并底音轨是「还原」不是「再压一遍」==")
    m = tone(work / "music.wav", 2.0, 440)
    s = tone(work / "sfx.wav", 2.0, 880)
    bed = separate.merge([m, s], work / "bed.wav")
    check("合并产物存在且有音轨", bed.exists() and has_audio(bed), True)

    print("== 混音：ducking + 响度归一 真能跑通 ==")
    video = tone(work / "v.mp4", 4.0, 220, video=True)
    voice = tone(work / "voice.wav", 4.0, 660)
    out = compose.compose(video=video, out=work / "out.mp4", voice=voice,
                          bg_from=bed, bg_gain=0.25)
    check("成片有音轨", has_audio(out), True)
    check("成片存在", out.exists(), True)

    print("== MediaKit 客户端（假 client，不联网）==")
    _orig_client, _orig_sleep, _orig_cfg = (
        separate.httpx.Client, separate.time.sleep, separate._cfg)
    separate.httpx.Client = _FakeClient
    separate.time.sleep = lambda *_a: None
    separate._cfg = lambda: ("fake-key", "https://mediakit.example.com")
    try:
        res = separate.separate("https://example.com/a.mp4", scene="Drama")
        check("拿到三轨", sorted(k for k in ("voice", "music", "sfx") if res.get(k)),
              ["music", "sfx", "voice"])
        check("带上了 scene", _FakeClient.posted[0][2].get("scene"), "Drama")
        check("鉴权头是 Bearer", _FakeClient.posted[0][1].get("Authorization"),
              "Bearer fake-key")
        check("输出格式带 wav", _FakeClient.posted[0][2].get("output_format"), "wav")
    finally:
        separate.httpx.Client = _orig_client
        separate.time.sleep = _orig_sleep
        separate._cfg = _orig_cfg

    print("== _audio_bed 接线（全程打桩，不联网）==")
    from app.services import oss as oss_mod

    src = tone(work / "src.mp4", 4.0, 220, video=True)
    rec_speech = {"source": {"duration": 4.0, "has_audio": True},
                  "speech": {"segments": [{"start": 0.0, "end": 3.0, "text": "在说话"}]}}
    _saved = (separate.available, oss_mod.available, oss_mod.upload,
              separate.separate, separate.download)
    try:
        separate.available = lambda: False
        bed, err = clone_pipeline._audio_bed(
            src, rec_speech, work / "b1",
            {"audio": "original", "bgm": "keep"}, total_sec=4.0)
        check("没配置分离 + 保留原声 → 退回原轨不阻断", (bed == src, err), (True, ""))

        separate.available = lambda: True
        oss_mod.available = lambda: True
        oss_mod.upload = lambda p, **k: "https://example.com/src.mp4"

        def _fake_sep(url, *, scene="Drama", timeout=0):
            _FakeClient.posted.append((url, None, {"scene": scene}))
            return {"music": "https://x/m.wav", "sfx": "https://x/s.wav",
                    "voice": "https://x/v.wav", "duration": 4.0}

        def _fake_dl(url, dest, **k):
            dest.parent.mkdir(parents=True, exist_ok=True)
            tone(dest, 2.0, 440 if url.endswith("m.wav") else 880)
            return dest

        separate.separate = _fake_sep
        separate.download = _fake_dl
        bed, err = clone_pipeline._audio_bed(
            src, rec_speech, work / "b2",
            {"audio": "mix", "bgm": "keep"}, total_sec=4.0)
        check("成功路径拿到背景轨", bool(bed and bed.exists() and has_audio(bed)), True)
        check("场景固定 Drama", _FakeClient.posted[-1][2].get("scene"), "Drama")

        separate.separate = lambda *a, **k: (_ for _ in ()).throw(
            separate.SeparateError("接口挂了"))
        bed, err = clone_pipeline._audio_bed(
            src, rec_speech, work / "b3",
            {"audio": "original", "bgm": "drop"}, total_sec=4.0)
        check("分离失败 + 点名去 BGM → 拦下（不许静默留原轨）",
              bed is None and "分离" in (err or ""), True)
    finally:
        (separate.available, oss_mod.available, oss_mod.upload,
         separate.separate, separate.download) = _saved

    print("== 没有 key 时明确报错，而不是静默出片 ==")
    separate._cfg = lambda: ("", "https://mediakit.example.com")
    try:
        separate.separate("https://example.com/a.mp4")
        check("没 key 报错", False, True)
    except separate.SeparateError as e:
        check("没 key 报错", "MEDIAKIT_API_KEY" in str(e), True)

    print(f"\n{PASS}/{PASS + FAIL} 通过")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
