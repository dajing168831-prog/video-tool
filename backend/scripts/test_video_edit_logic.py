"""双通道换画面的纯逻辑自检（不发网络请求、不花钱）。

覆盖：分段规划、通道选择、参数表、签名链接 —— **全是共用层**。
🔴 **本文件不许写任何单一型号的断言**（2026-10-26 主人拍板，见台账 D43）：
H3 的自动翻译已搬去 `test_edit_spec_h3.py`，
2.0 的可指认闸已搬去 `test_edit_spec_sd20.py`。
**本文件的绿灯，不能当作任何一家"已验收"的证据。**
`--model` 在这里只作"一轮只做一家"的轮次点名，**不筛内容**。

运行：python scripts/test_video_edit_logic.py --model volc20|volc25|h3
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.core.config import settings  # noqa: E402
from app.services import signed_url, video_edit  # noqa: E402

PASS = FAIL = 0


def check(name: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {name}: {got}")
    else:
        FAIL += 1
        print(f"  FAIL {name}: got={got!r} want={want!r}")


def shots_of(total: float, n: int) -> list[dict]:
    step = total / n
    return [
        {"i": i, "start": round(i * step, 3), "end": round((i + 1) * step, 3),
         "dur": round(step, 3)}
        for i in range(n)
    ]


def main() -> int:
    # 🚦 必须点名型号（2026-10-26）：本脚本验的是**共享层/参数表**，
    # 断言本身不分模型，点名只作「一次只跑一家」的执行闸。
    from _model_gate import sel_or_exit
    sel_or_exit()

    print("== plan_chunks ==")
    sh60 = shots_of(60, 20)                       # 20 镜 × 3s
    c30 = video_edit.plan_chunks(sh60, 60, 30)
    c15 = video_edit.plan_chunks(sh60, 60, 15)
    check("60s 火山上限30s 段数", len(c30), 2)
    check("60s MiniMax上限15s 段数", len(c15), 4)
    check("段首尾对齐", [round(a, 1) for a, _ in c30], [0.0, 30.0])
    check("段末到片尾", round(c30[-1][1], 1), 60.0)

    # 单镜头 40s 的长镜头：超过 30s 必须被均分
    long_shot = [{"i": 0, "start": 0.0, "end": 40.0, "dur": 40.0}]
    c_long = video_edit.plan_chunks(long_shot, 40, 30)
    check("40s 单镜在30s上限下段数", len(c_long), 2)
    check("长镜均分后总覆盖", round(c_long[-1][1], 1), 40.0)

    print("== split_longest ==")
    seg = video_edit.split_longest([(0.0, 30.0)], 15)
    check("30s 段在15s上限下切成", len(seg), 2)
    seg2 = video_edit.split_longest([(0.0, 18.0)], 15)   # 切口留 3s，过短要并回
    check("18s 切完不足4s 并回", len(seg2), 1)

    print("== fit_spans：每段都必须落在模型收的 [min,max] 内 ==")
    # 官方硬门槛：2.5 编辑任务待编辑视频 4–30s；2.0/MiniMax 2–15s。
    # 尾巴只有 1–2 秒时接口直接拒，等于白跑一趟 —— 这里必须一条都不留。
    def lens(sp):
        return [round(b - a, 2) for a, b in sp]

    sp = video_edit.fit_spans([(0.0, 30.0), (30.0, 32.0)], 30, min_sec=4)
    check("30+2 → 两段且都≥4", all(4 <= n <= 30 for n in lens(sp)), True)
    check("30+2 总长不变", round(sum(lens(sp)), 2), 32.0)

    sp = video_edit.fit_spans([(0.0, 2.0), (2.0, 10.0)], 15, min_sec=4)
    check("首段 2s 向后借到 4s", lens(sp)[0], 4.0)
    check("借完第二段仍≥4", lens(sp)[1] >= 4, True)

    sp = video_edit.fit_spans([(0.0, 15.0), (20.0, 22.0)], 15, min_sec=4)
    check("隔空的两段：吃空档不动前段", lens(sp), [15.0, 4.0])
    check("吃空档不改起点", sp[1][0], 18.0)

    sp = video_edit.fit_spans([(0.0, 12.0), (12.0, 13.5)], 15, min_sec=4)
    check("13.5 够短 → 并进前段", lens(sp), [13.5])
    sp = video_edit.fit_spans([(0.0, 40.0), (40.0, 41.0)], 15, min_sec=4)
    check("前段已满 15 时只能借", all(4 <= n <= 15 for n in lens(sp)), True)

    sp = video_edit.fit_spans([(0.0, 70.0)], 30, min_sec=4)
    check("70s 长片三段", lens(sp), [30.0, 30.0, 10.0])

    # （单型号断言已按 D43 搬回各自的型号文件：
    #   H3 → test_edit_spec_h3.py｜2.0 → test_edit_spec_sd20.py｜2.5 → test_edit_spec_sd25.py）

    # （单型号断言已按 D43 搬回各自的型号文件：
    #   H3 → test_edit_spec_h3.py｜2.0 → test_edit_spec_sd20.py｜2.5 → test_edit_spec_sd25.py）

    # （单型号断言已按 D43 搬回各自的型号文件：
    #   H3 → test_edit_spec_h3.py｜2.0 → test_edit_spec_sd20.py｜2.5 → test_edit_spec_sd25.py）

    print("== 通道选择 ==")
    # 用 monkeypatch 控制配置，避免依赖真实 key
    real_ark = settings.ark_api_key
    real_mm = settings.minimax_api_key
    real_base = settings.public_base_url
    try:
        object.__setattr__(settings, "ark_api_key", "k")
        object.__setattr__(settings, "minimax_api_key", "k")
        object.__setattr__(settings, "public_base_url", "https://x.test")
        # 🩸 2026-11-03 复刻下架 H3：`pick_channel` 的 auto 现在跳过 `Caps.frozen`
        #   的家族。判据按注册表动态断言，不写死某一态（同 ff78059 的做法）。
        from app.services import models as _models

        _mm_frozen = "minimax" in _models.frozen_families()
        check("auto 无参考图 → 火山", video_edit.pick_channel("auto", subject_kind="none"), "volc")
        check("auto 本地人物图 → " + ("火山（H3 已冻结）" if _mm_frozen else "MiniMax"),
              video_edit.pick_channel("auto", subject_kind="file"),
              "volc" if _mm_frozen else "minimax")
        check("auto asset:// 素材 → 火山（官方合规口子）",
              video_edit.pick_channel("auto", subject_kind="asset"), "volc")

    # （单型号断言已按 D43 搬回各自的型号文件：
    #   H3 → test_edit_spec_h3.py｜2.0 → test_edit_spec_sd20.py｜2.5 → test_edit_spec_sd25.py）

        object.__setattr__(settings, "minimax_api_key", "")
        check("MiniMax 没配 → 降级火山", video_edit.pick_channel("auto", subject_kind="file"), "volc")
        # 🩸 本机环境里真配了 OSS 凭据，光清 public_base_url 火山仍然"就绪" ——
        # 要把 OSS 也一起按没配处理，才算真的"两条都不全"
        from app.services import oss

        real_oss_avail = oss.available
        oss.available = lambda: False
        object.__setattr__(settings, "public_base_url", "")
        try:
            video_edit.pick_channel("auto", subject_kind="none")
            check("两条都不全 → 报错", "no-error", "EditError")
        except video_edit.EditError:
            check("两条都不全 → 报错", "EditError", "EditError")
        finally:
            oss.available = real_oss_avail
    finally:
        object.__setattr__(settings, "ark_api_key", real_ark)
        object.__setattr__(settings, "minimax_api_key", real_mm)
        object.__setattr__(settings, "public_base_url", real_base)

    print("== 签名链接 ==")
    object.__setattr__(settings, "public_base_url", "https://api.test")
    url = signed_url.make("a" * 32, ttl=600)
    exp = int(url.split("exp=")[1].split("&")[0])
    sig = url.split("sig=")[1]
    check("正常验签通过", signed_url.verify("a" * 32, exp, sig), True)
    check("改 cid 验签失败", signed_url.verify("b" * 32, exp, sig), False)
    check("改 sig 验签失败", signed_url.verify("a" * 32, exp, "x" * 24), False)
    check("过期验签失败", signed_url.verify("a" * 32, 1, sig), False)
    surl = signed_url.make("a" * 32, ttl=600, seg="seg_001.mp4")
    sexp = int(surl.split("exp=")[1].split("&")[0])
    ssig = surl.split("sig=")[1]
    check("段链接带段名", "file/seg/seg_001.mp4" in surl, True)
    check("段验签通过", signed_url.verify("a" * 32, sexp, ssig, seg="seg_001.mp4"), True)
    check("段名被改验签失败", signed_url.verify("a" * 32, sexp, ssig, seg="seg_002.mp4"), False)
    object.__setattr__(settings, "public_base_url", "")

    print("== 火山审核报错的分流 ==")
    # 两个码长得像、解法相反：版权要换输入，真人脸要换素材来源
    copyright_msg = ('创建编辑任务失败 HTTP 400: {"error":{"code":'
                     '"InputVideoSensitiveContentDetected.PolicyViolation","message":'
                     '"The request failed because the input video \'content[1]\' may be '
                     'related to copyright restrictions."}}')
    face_msg = ('{"error":{"code":"InputVideoSensitiveContentDetected.PrivacyInformation",'
                '"message":"The request failed because the input video may contain '
                'real person."}}')
    c_hint = video_edit._volc_hint(copyright_msg)
    f_hint = video_edit._volc_hint(face_msg)
    check("版权码 → 提到版权", "版权" in c_hint, True)
    check("版权码 → 不提人脸授权", "asset://" in c_hint, False)
    check("版权码 → 指到 MiniMax", "MiniMax" in c_hint, True)
    check("真人码 → 指到 asset", "asset://" in f_hint, True)
    check("真人码 → 不误报版权", "版权" in f_hint, False)
    check("无关报错 → 不瞎加提示", video_edit._volc_hint("超时"), "")

    # 🩸 输出侧和输入侧是两行不同的官方错误码，解法也不同：
    # Output 判的是"生成出来的视频"，官方建议换输入内容，换通道不保证
    out_msg = ('{"error":{"code":"OutputVideoSensitiveContentDetected.PolicyViolation",'
               '"message":"The request failed because the output video may be related '
               'to copyright restrictions. Request id: 0217925..."}}')
    o_hint = video_edit._volc_hint(out_msg)
    check("输出侧 → 说的是生成出来的视频", "生成出来的这段视频" in o_hint, True)
    check("输出侧 → 不冒充输入侧码", "InputVideoSensitiveContentDetected" in o_hint, False)
    check("输出侧 → 不承诺换通道能解决", "不保证" in o_hint, True)
    out_sens = ('{"error":{"code":"OutputVideoSensitiveContentDetected",'
                '"message":"The request failed because the output video may contain '
                'sensitive information."}}')
    check("输出敏感 → 也按输出侧说", "生成出来的这段视频" in video_edit._volc_hint(out_sens), True)

    # 🩸 2026-10-28 实测任务 `cgt-20261028030449-2g9km`：**输出音频**是第三条码，
    #   以前落到泛 policyviolation 兜底 → 被说成「参考视频被判版权」。
    aud_msg = ('{"error":{"code":"OutputAudioSensitiveContentDetected.PolicyViolation",'
               '"message":"The request failed because the output audio may be related '
               'to copyright restrictions. Request id: 0217931..."}}')
    a_hint = video_edit._volc_hint(aud_msg)
    check("输出音频码 → 说的是生成出来的音轨", "模型生成出来的那条音轨" in a_hint, True)
    check("输出音频码 → 不冒充输入侧", "InputVideoSensitiveContentDetected" not in a_hint,
          True)
    check("输出音频码 → 说明不影响成片声音", "声音不受影响" in a_hint, True)
    check("输出音频码 → 建议先重试", "重试" in a_hint, True)

    # 🩸 2026-10-25 实测（`861efd72`）：不带后缀的输入敏感码，以前落到「无提示」，
    # 界面上只剩一坨原始 JSON。它既不是版权、也不是真人脸，且**模型一次没跑**。
    in_sens = ('创建编辑任务失败 HTTP 400: {"error":{"code":'
               '"InputVideoSensitiveContentDetected","message":"The request failed '
               'because the input video \'content[1]\' may contain sensitive '
               'information. Request id: 0217928779..."}}')
    i_hint = video_edit._volc_hint(in_sens)
    check("输入敏感（无后缀）→ 给出人话提示", bool(i_hint), True)
    check("输入敏感 → 说明模型没跑、改提示词没用", "改提示词没有用" in i_hint, True)
    check("输入敏感 → 不误报版权", "版权" in i_hint.replace("既不是版权", ""), False)
    check("输入敏感 → 不误报真人脸", "asset://" in i_hint, False)
    check("隐私码仍走真人分支（不被新分支抢走）",
          "asset://" in video_edit._volc_hint(face_msg), True)

    # （单型号断言已按 D43 搬回各自的型号文件：
    #   H3 → test_edit_spec_h3.py｜2.0 → test_edit_spec_sd20.py｜2.5 → test_edit_spec_sd25.py）

    print("== 边界帧整条停用：任何情况下都不带 ==")
    # 🩸 2026-11-02 主人拍板删除。第 2 段的参考视频就是从原片切出来单独上传的
    # （`cut_clip`），接缝信息本来就在模型手里；再叠一张"上一段成片的尾帧"，
    # 是整条链上唯一一个非原片来源的输入。老逻辑改名 `_boundary_used__retired`
    # 留墓碑，`_boundary_used` 恒 False —— 判的就是**发出去的请求里有没有这张图**，
    # 照旧算老规则等于报一个没发生的事。
    _plan = {"ch": "minimax", "model": "MiniMax-H3"}
    _spans = [(0.0, 10.0), (10.0, 20.0), (20.0, 30.0)]
    check("两段都重画 → 不带", video_edit._boundary_used(
        _plan, _spans[:2], {_spans[0]: ("change", [{"id": "P1"}])}), False)
    check("上一段留原片 → 不带", video_edit._boundary_used(
        _plan, _spans[:2], {_spans[0]: ("keep", None)}), False)
    check("中间隔开（不紧挨）→ 不带", video_edit._boundary_used(
        _plan, [(0.0, 10.0), (12.0, 22.0)], {_spans[0]: ("change", [{"id": "P1"}])}),
        False)
    # （单型号断言已按 D43 搬回各自的型号文件：
    #   H3 → test_edit_spec_h3.py｜2.0 → test_edit_spec_sd20.py｜2.5 → test_edit_spec_sd25.py）
    check("只有一段 → 不带", video_edit._boundary_used(
        _plan, _spans[:1], {}), False)
    check("中间段重画 → 第 3 段也不带", video_edit._boundary_used(
        _plan, _spans, {_spans[0]: ("keep", None),
                        _spans[1]: ("change", [{"id": "P1"}])}), False)

    print("== 口型参考音轨：挑哪条 / 截多长 ==")
    import tempfile

    from app.services import scene

    work = Path(tempfile.mkdtemp(dir="D:/tmp", prefix="veaudio_"))
    # 用一段纯音生成真音轨（-f lavfi，不需要任何素材）
    ff = scene.ffmpeg_path()
    src_wav = work / "voice.wav"
    import subprocess

    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", "sine=frequency=440:duration=6", "-ac", "1", str(src_wav)],
                   check=True, timeout=60)
    track = video_edit._audio_track({"audio": "tts"}, work / "x.mp4", work)
    check("全新配音取配音轨", track, src_wav)
    orig = video_edit._audio_track({"audio": "original"}, work / "x.mp4", work)
    # 原声是整条混音（人声+音乐+环境声），不是干净的音色样本 → 不当参考喂
    check("保留原声一律不喂音频", orig, None)
    seg = video_edit._seg_audio(src_wav, 0.0, 4.0, work / "a1.wav")
    check("截得出这一段", seg is not None and seg.exists(), True)
    check("截出来是 4 秒", round(scene.probe(seg)["duration"], 1), 4.0)
    check("不足 2 秒不喂", video_edit._seg_audio(src_wav, 0.0, 1.2, work / "a2.wav"), None)
    check("沿用时间轴超出音轨长度就截到末尾",
          video_edit._seg_audio(src_wav, 3.0, 99.0, work / "a3.wav") is not None, True)
    check("没有音轨就不喂", video_edit._seg_audio(None, 0.0, 4.0, work / "a4.wav"), None)

    print("== 比例不一致时不许补黑边（模型 adaptive 只会给最接近的标准比例）==")
    # 原片 576×1024(0.5625)，2.0 的 adaptive 给回来是 496×864(0.5741)。
    # 旧写法 scale=decrease + pad 会补出上下各十来行黑边（实测 10/12 行）。
    # 这里用纯白底片：任何黑边都会把首/末行的平均亮度打到 0。
    odd = work / "odd.mp4"
    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "color=c=white:s=496x864:d=2:r=24",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(odd)],
                   check=True, timeout=60)
    check("对照：素材比例确实和原片不一致", scene.probe(odd)["width"], 496)
    norm = video_edit._normalize(odd, work / "odd_norm.mp4", 2.0, 576, 1024, 30.0)
    W, H = 576, 1024
    q = subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-ss", "1",
                        "-i", str(norm), "-vframes", "1", "-vf", "format=gray",
                        "-f", "rawvideo", "-"], capture_output=True)
    buf = q.stdout
    check("规格化后尺寸对", (len(buf), ), (W * H,))
    if len(buf) >= W * H:
        rows = [sum(buf[y * W:(y + 1) * W]) / W for y in range(H)]
        check("顶部没有黑边", round(min(rows[:20])), 255)
        check("底部没有黑边", round(min(rows[-20:])), 255)

    print("== 参考图按官方硬门槛收口 ==")
    # 官方：火山边长 [300,6000]、H3 [256,5760]，宽高比都 [0.4,2.5]，单张 ≤30MB
    def make_img(path, w, h):
        subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "lavfi", "-i", f"color=c=gray:s={w}x{h}:d=1",
                        "-frames:v", "1", str(path)], check=True, timeout=180)
        return path

    # （单型号断言已按 D43 搬回各自的型号文件：
    #   H3 → test_edit_spec_h3.py｜2.0 → test_edit_spec_sd20.py｜2.5 → test_edit_spec_sd25.py）

    tiny = make_img(work / "tiny.png", 100, 200)
    try:
        video_edit._fit_image(tiny, "volc")
        check("短边不足要报错（放大不会长细节）", "no-error", "EditError")
    except video_edit.EditError:
        check("短边不足要报错（放大不会长细节）", "EditError", "EditError")

    narrow = make_img(work / "narrow.png", 100, 1000)
    try:
        video_edit._fit_image(narrow, "volc")
        check("宽高比超范围要报错", "no-error", "EditError")
    except video_edit.EditError:
        check("宽高比超范围要报错", "EditError", "EditError")

    print("== 逐句说话人：只能靠画面推（同框/画外音一律不标）==")
    inv = {"people": [
        {"id": "P1", "appearances": [{"start": 0, "end": 3},
                                    {"start": 8, "end": 11}]},
        {"id": "P2", "appearances": [{"start": 4, "end": 7},
                                    {"start": 9, "end": 12}]},
    ]}
    rec = {"voice_lines": [
        {"start": 0.5, "end": 2.0, "text": "只有我在"},      # 画面只有 P1
        {"start": 4.5, "end": 6.0, "text": "换我说"},        # 画面只有 P2
        {"start": 9.2, "end": 10.4, "text": "两人都在"},      # P1+P2 同框
        {"start": 20.0, "end": 21.0, "text": "画外音"},       # 谁都不在画面里
    ]}
    video_edit._assign_speakers(rec, inv)
    got = [x.get("speaker") or "" for x in rec["voice_lines"]]
    check("单人区间标说话人", got[0], "P1")
    check("另一人单人区间标对人", got[1], "P2")
    check("两人同框不瞎标", got[2], "")
    check("没人出现的区间（画外音）不标", got[3], "")
    # 没有盘点结果时一个字都不该动（声学编号也落不到人身上）
    rec2 = {"voice_lines": [{"start": 0.5, "end": 2.0, "text": "x",
                             "asr_speaker": "1"}]}
    video_edit._assign_speakers(rec2, None)
    check("没盘点就不标", "speaker" in rec2["voice_lines"][0], False)

    # 🩸 声学编号把"同框对白"也分得开：前两句在单人镜头里定下「声纹 1=P2、
    # 声纹 2=P1」，第 3 句两人同框（画面判不出），靠声纹仍然归对人。
    rec3 = {"voice_lines": [
        {"start": 0.5, "end": 2.0, "text": "甲", "asr_speaker": "2"},   # 只有 P1
        {"start": 4.5, "end": 6.0, "text": "乙", "asr_speaker": "1"},   # 只有 P2
        {"start": 9.2, "end": 10.4, "text": "同框 A", "asr_speaker": "1"},
        {"start": 9.6, "end": 10.9, "text": "同框 B", "asr_speaker": "2"},
    ]}
    video_edit._assign_speakers(rec3, inv)
    got3 = [x.get("speaker") or "" for x in rec3["voice_lines"]]
    check("单人镜头定声纹→人物", (got3[0], got3[1]), ("P1", "P2"))
    check("同框第 1 句靠声纹归对", got3[2], "P2")
    check("同框第 2 句靠声纹归对", got3[3], "P1")

    # 🩸 2026-11-03 第三路证据：盘点的 `people[].speaks`（2.1 看视频时记下谁在动嘴）。
    #   专治上面那种"三人全程同框、声纹也没锚点"的片子：动嘴的人唯一就能定人。
    inv_s = {"people": [
        {"id": "P1", "appearances": [{"start": 0, "end": 12}],
         "speaks": [{"start": 0.5, "end": 2.0}, {"start": 9.2, "end": 10.4}]},
        {"id": "P2", "appearances": [{"start": 0, "end": 12}],
         "speaks": [{"start": 4.5, "end": 6.0}]},
    ]}
    rec5 = {"voice_lines": [
        {"start": 0.5, "end": 2.0, "text": "同框甲", "asr_speaker": "1"},
        {"start": 4.5, "end": 6.0, "text": "同框乙", "asr_speaker": "2"},
        {"start": 9.2, "end": 10.4, "text": "同框丙", "asr_speaker": "1"},
    ]}
    video_edit._assign_speakers(rec5, inv_s)
    got5 = [x.get("speaker") or "" for x in rec5["voice_lines"]]
    check("全程同框时靠「谁在动嘴」定人", got5, ["P1", "P2", "P1"])
    # 两个人同时在动嘴 → 弃权（和"两人同框不瞎标"同一条原则）
    inv_two = {"people": [
        {"id": "P1", "appearances": [{"start": 0, "end": 12}],
         "speaks": [{"start": 0.5, "end": 2.0}]},
        {"id": "P2", "appearances": [{"start": 0, "end": 12}],
         "speaks": [{"start": 0.8, "end": 2.2}]},
    ]}
    rec6 = {"voice_lines": [{"start": 0.5, "end": 2.0, "text": "抢话",
                             "asr_speaker": "1"}]}
    video_edit._assign_speakers(rec6, inv_two)
    check("两个人同时在动嘴就不标", rec6["voice_lines"][0].get("speaker", ""), "")
    # 老盘点没有 `speaks` 字段 → 行为与今天完全一样（不许因为加字段而改变老结果）
    inv_old = {"people": [{k: v for k, v in p.items() if k != "speaks"}
                          for p in inv_s["people"]]}
    rec7 = {"voice_lines": [{"start": 0.5, "end": 2.0, "text": "老盘点",
                             "asr_speaker": "1"}]}
    video_edit._assign_speakers(rec7, inv_old)
    check("老盘点（无 speaks）不标", rec7["voice_lines"][0].get("speaker", ""), "")

    # 声纹编号对不上号时（新文案换了人念）不瞎标：画面判不出 → 空
    rec4 = {"voice_lines": [
        {"start": 9.2, "end": 10.4, "text": "同框", "asr_speaker": "9"}]}
    video_edit._assign_speakers(rec4, inv)
    check("没见过的声纹编号不瞎标", rec4["voice_lines"][0].get("speaker", ""), "")

    print("== ASR 说话人编号：从 utterances[].additions.speaker 取 ==")
    # 官方《录音文件识别极速版HTTP》请求参数 show_utterances：「启用输出分句、
    # 分词、说话人及语音停顿信息」；返回示例里是
    # `"additions": {"channel_id": "1", "speaker": "1"}`。
    from app.services.providers import asr as asr_mod
    resp = {"result": {"utterances": [
        {"additions": {"channel_id": "1", "speaker": "1"},
         "start_time": 480, "end_time": 5880, "text": "你好",
         "words": [{"text": "你", "start_time": 480, "end_time": 600}]},
        {"start_time": 6000, "end_time": 8000, "text": "再见",
         "words": [{"text": "再", "start_time": 6000, "end_time": 6100}]},
    ]}}
    parsed = asr_mod._from_volc(resp, "zh")
    check("带出 additions.speaker", parsed["segments"][0]["speaker"], "1")
    check("没有 additions 也不报错", parsed["segments"][1]["speaker"], "")
    check("毫秒照旧换算成秒", parsed["segments"][0]["start"], 0.48)

    print("== 段内切点：严格递增、落在段内（三家共用）==")
    # 官方 H3 `base-en:86`：「a strictly increasing cut time that falls within the
    # video duration」。2.0/2.5 的指南也要求把镜头结构写进提示词 —— 这条在
    # `video_edit._clean_cuts` 里，三家都走同一个函数，所以是共用层断言。
    cc = video_edit._clean_cuts
    check("乱序输入 → 排序后递增", cc([6.0, 2.0, 4.0], 10.0), [2.0, 4.0, 6.0])
    check("重复切点只留一个", cc([3.0, 3.0, 5.0], 10.0), [3.0, 5.0])
    check("越界（≥段长 / ≤0）丢掉", cc([0.0, -1.0, 10.0, 12.0, 3.0], 10.0), [3.0])
    check("空输入 → 空输出", cc([], 10.0), [])
    check("None 不抛错", cc(None, 10.0), [])
    # 成对：正常形状必须**原样保留**（别把好数据也洗掉）
    check("正常形状原样保留", cc([3.0, 6.9], 12.0), [3.0, 6.9])

    print(f"\n{PASS}/{PASS + FAIL} 通过")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
