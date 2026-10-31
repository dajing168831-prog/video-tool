"""成品契约量具（第 3 步）：量**产品**，不量代码。

🩸 为什么有这个文件（2026-10-31 主人点破的那条）：
    `check_all` 挂着 46 道代码门，全绿的时候片子照样是废的 —— 因为
    「后台变了吗 / 口型对得上吗 / 两段之间还是同一个人吗」这三件事，
    一关都没问过。这个模块补的就是这三问。

量在三样东西上（都在出片目录里，不额外调模型、不花钱）：
    · `gen/chunk_00N.mp4`  模型真正生成的段
    · `piece_00N.mp4`      规格化回原时长的同一段
    · `decisions.json`     这一段对的是原片哪几秒

三项指标与判据（判据全部来自实测标定，不是拍脑袋）：

| 项 | 怎么算 | 判据 | 标定样本 |
|---|---|---|---|
| 口型滞后 | 原片该段音频 vs 生成段音频，20ms 窗的短时能量包络做互相关 | `\\|lag\\| ≤ 300ms` 且相关 ≥ 0.3 | 好 −70/−10/−20ms、相关 0.86–0.90；坏 −870ms、相关 0.244 |
| 段间身份 | 两段成片逐帧 SFace，取交叉 p90 | **只报数，不打勾** | 好 0.807 / 旧 0.736，但只有这一组，不够标定 |
| 背景保住 | **原片该段** 与 **模型输出** 的顶部 12% 灰度 SSIM | **只报数，不打勾** | 保住 0.843 / 被重画 0.538（2026-10-31 30 秒真机） |

🩸 **为什么后两项不打勾**：`reference-frame-must-self-prove` —— 参照系得能自证。
    一项指标只有一两个样本，标不出"好/坏"的分界；此时打勾就是造假红假绿。
    等样本够了再回来加判据，别现在编阈值。

🩸 绝不抛错：任何一项量不出来就记 `skipped`。钱已经花了，对账不该把出片搞挂
    （与 `qc` / `identity.check` 同一条口径）。
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

#: 音频包络参数：20ms 窗 / 10ms 跳（够分辨一个字的起落，又不怕抖动）
SR, WIN, HOP = 16000, 320, 160
#: 口型的通过线。标定：好 −70/−10/−20ms，坏 −870ms ⇒ 取两端中间偏严
LIP_LAG_PASS_MS = 300.0
#: 相关低于这条，滞后数就没有意义（说明是节奏不同，不是整体平移）
LIP_CORR_MIN = 0.30
#: 背景只看顶部：实测边框/底部方向相反（好段反而更低），只有顶部 12% 分得开
BG_TOP = 0.12
#: 每段最多抽多少帧做身份（0.5s 一帧；60 秒的段也够用）
ID_STEP = 0.5


# ---------------------------------------------------------------- 小工具

def _json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _ffmpeg() -> str | None:
    try:
        from app.services.media import ffmpeg_path

        return ffmpeg_path()
    except Exception:  # noqa: BLE001
        return None


def _pcm(path: Path, *, start: float = 0.0, dur: float = 0.0):
    """解码成 16k 单声道 float32；失败返回 None。"""
    import numpy as np

    ff = _ffmpeg()
    if not ff:
        return None
    cmd = [ff, "-v", "quiet"]
    if start > 0:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", str(path), "-vn"]
    if dur > 0:
        cmd += ["-t", f"{dur:.3f}"]
    cmd += ["-ac", "1", "-ar", str(SR), "-f", "s16le", "-"]
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=180)
    except Exception as e:  # noqa: BLE001
        log.warning("取音频失败 %s：%s", path.name, e)
        return None
    if not p.stdout:
        return None
    return np.frombuffer(p.stdout, dtype="<i2").astype("float32") / 32768.0


def _envelope(x):
    import numpy as np

    n = max(0, 1 + (len(x) - WIN) // HOP)
    if n <= 1:
        return np.zeros(1)
    idx = np.arange(WIN)[None, :] + HOP * np.arange(n)[:, None]
    e = np.sqrt((x[idx] ** 2).mean(axis=1))
    e = e - e.mean()
    s = e.std()
    return e / s if s > 1e-9 else e


def _lag_ms(a, b, max_ms: int = 2000) -> tuple[float, float]:
    """b 相对 a 的滞后（毫秒，正 = b 更晚）与峰值相关。"""
    import numpy as np

    if len(a) < 2 or len(b) < 2:
        return float("nan"), 0.0
    n = 1
    while n < len(a) + len(b):
        n *= 2
    fa, fb = np.fft.rfft(a, n), np.fft.rfft(b, n)
    cc = np.fft.irfft(fa * np.conj(fb), n)
    cc = np.concatenate([cc[-(len(b) - 1):], cc[:len(a)]])
    lags = np.arange(-(len(b) - 1), len(a))
    ms = lags * HOP * 1000.0 / SR
    keep = np.abs(ms) <= max_ms
    if not keep.any():
        return float("nan"), 0.0
    i = int(np.argmax(cc[keep]))
    return (float(ms[keep][i]),
            float(cc[keep][i] / (len(a) * len(b)) ** 0.5))


def _ssim(a, b) -> float:
    import cv2
    import numpy as np

    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    k = (11, 11)
    fa, fb = a.astype("float64"), b.astype("float64")
    mu_a, mu_b = cv2.GaussianBlur(fa, k, 1.5), cv2.GaussianBlur(fb, k, 1.5)
    va = cv2.GaussianBlur(fa ** 2, k, 1.5) - mu_a ** 2
    vb = cv2.GaussianBlur(fb ** 2, k, 1.5) - mu_b ** 2
    cab = cv2.GaussianBlur(fa * fb, k, 1.5) - mu_a * mu_b
    s = ((2 * mu_a * mu_b + c1) * (2 * cab + c2)) / (
        (mu_a ** 2 + mu_b ** 2 + c1) * (va + vb + c2))
    return float(s.mean())


def _band_ssim(a, b, top: float, bottom: float) -> float:
    """带状 SSIM，先在 ±6 像素内找最佳水平平移（避免轻微位移被当成"变了"）。"""
    import cv2
    import numpy as np

    h = a.shape[0]
    a2 = a[int(h * top):int(h * bottom), :]
    b2 = b[int(h * top):int(h * bottom), :]
    if a2.shape != b2.shape or a2.size == 0:
        return float("nan")
    best = -1.0
    for dx in range(-6, 7, 2):
        m = np.float32([[1, 0, dx], [0, 1, 0]])
        b3 = cv2.warpAffine(b2, m, (b2.shape[1], b2.shape[0]),
                            flags=cv2.INTER_LINEAR,
                            borderMode=cv2.BORDER_REPLICATE)
        best = max(best, _ssim(a2, b3))
    return best


def _frame(path: Path, t: float, dst: Path):
    import cv2

    ff = _ffmpeg()
    if not ff:
        return None
    try:
        subprocess.run([ff, "-v", "error", "-ss", f"{t:.3f}", "-i", str(path),
                        "-frames:v", "1", "-y", str(dst)],
                       capture_output=True, timeout=120)
    except Exception:  # noqa: BLE001
        return None
    img = cv2.imread(str(dst), cv2.IMREAD_GRAYSCALE)
    return img


# ---------------------------------------------------------------- 三项

def _lip_items(spans, gens, video: Path) -> list[dict]:
    out = []
    for n, (a, b) in enumerate(spans, 1):
        if n - 1 >= len(gens):
            break
        xa = _pcm(video, start=a, dur=b - a)
        xb = _pcm(gens[n - 1])
        if xa is None or xb is None or len(xa) == 0 or len(xb) == 0:
            out.append({"key": f"lip_{n}", "label": f"第{n}段口型",
                        "verdict": "skipped", "why": "取不到音频"})
            continue
        ea, eb = _envelope(xa), _envelope(xb)
        lag, corr = _lag_ms(ea, eb)
        if lag != lag:  # NaN
            out.append({"key": f"lip_{n}", "label": f"第{n}段口型",
                        "verdict": "skipped", "why": "取不到音频"})
            continue
        ok = abs(lag) <= LIP_LAG_PASS_MS and corr >= LIP_CORR_MIN
        out.append({
            "key": f"lip_{n}", "label": f"第{n}段口型",
            "lag_ms": round(lag), "corr": round(corr, 3),
            "pass_if": f"|滞后| ≤ {LIP_LAG_PASS_MS:.0f}ms 且相关 ≥ {LIP_CORR_MIN}",
            "verdict": "pass" if ok else "fail",
        })
    return out


def _seg_identity_items(gens) -> list[dict]:
    """段与段之间还是不是同一个人（只报数，不打勾 —— 标定样本不够）。"""
    try:
        from app.services import identity
        import cv2  # noqa: F401

        cy = identity._cv2()
        rec = identity._recognizer(cy)
    except Exception as e:  # noqa: BLE001
        return [{"key": "id_cross", "label": "段间身份", "verdict": "skipped",
                 "why": f"人脸模型不可用：{e}"}]

    def feats(video: Path):
        import numpy as np

        cap = cy.VideoCapture(str(video))
        if not cap.isOpened():
            return np.zeros((0, 128))
        fps = float(cap.get(cy.CAP_PROP_FPS) or 0) or 25.0
        stride = max(1, int(round(fps * ID_STEP)))
        got, n = [], 0
        while len(got) < 200:
            if n % stride:
                if not cap.grab():
                    break
                n += 1
                continue
            ok, img = cap.read()
            if not ok:
                break
            img = identity._shrink(cy, img)
            fs, err = identity._faces(cy, img)
            if not err and fs is not None and len(fs):
                best = max(fs, key=lambda f: float(f[2]) * float(f[3]))
                try:
                    got.append(rec.feature(rec.alignCrop(img, best)).flatten())
                except Exception:  # noqa: BLE001
                    pass
            n += 1
        cap.release()
        return np.vstack(got) if got else np.zeros((0, 128))

    import numpy as np

    pool = [feats(g) for g in gens]
    if sum(len(p) for p in pool) == 0:
        return [{"key": "id_cross", "label": "段间身份", "verdict": "skipped",
                 "why": "生成段里一帧都没检出人脸"}]
    if len(pool) < 2:
        return [{"key": "id_cross", "label": "段间身份", "verdict": "skipped",
                 "why": "只有一段，没有可比的另一边"}]
    vals = []
    for i in range(len(pool) - 1):
        if not len(pool[i]) or not len(pool[i + 1]):
            continue
        sims = [max(identity._cos(x, y) for y in pool[i + 1]) for x in pool[i]]
        vals.append(float(np.percentile(sims, 90)))
    if not vals:
        return [{"key": "id_cross", "label": "段间身份", "verdict": "skipped",
                 "why": "相邻段里有一段没人脸"}]
    return [{"key": "id_cross", "label": "段间身份",
             "p90": round(min(vals), 3),
             "note": "只报数；标定样本不够，暂不打勾",
             "verdict": "info"}]


def _bg_items(video: Path, spans, gens, tmpdir: Path) -> list[dict]:
    """背景保住没有：**原片该段** vs **模型输出**。

    🩸 2026-10-31 修：以前比的是 `piece` 与 `gen` —— 两个都是模型输出，等于
    自己跟自己比，恒报 0.92~0.96 的绿灯。30 秒真机（`0273fef0…`）实测：
        自己比 = 0.924 / 0.957 / 0.951（全绿）
        原片 vs 输出 = 0.843 / 0.538 / 0.648（段2、段3 背景被重画）
    """
    out = []
    for n in range(1, min(len(spans), len(gens)) + 1):
        a = _frame(video, float(spans[n - 1][0]) + 1.0,
                   tmpdir / f"ct_bg_src{n}.png")
        b = _frame(gens[n - 1], 1.0, tmpdir / f"ct_bg_gen{n}.png")
        if a is None or b is None:
            out.append({"key": f"bg_{n}", "label": f"第{n}段背景",
                        "verdict": "skipped", "why": "抽帧失败"})
            continue
        if a.shape != b.shape:
            import cv2

            b = cv2.resize(b, (a.shape[1], a.shape[0]))
        v = _band_ssim(a, b, 0.0, BG_TOP)
        out.append({"key": f"bg_{n}", "label": f"第{n}段背景",
                    "top_ssim": None if v != v else round(v, 3),
                    "note": "只报数；原片 vs 输出。真机 0.843 保住 / 0.538 重画",
                    "verdict": "info" if v == v else "skipped",
                    **({} if v == v else {"why": "算不出 SSIM"})})
    return out


# ---------------------------------------------------------------- 入口

def measure(*, workdir: Path, video: Path | None = None,
            out: Path | None = None) -> dict:
    """量一条成片的成品契约。永远返回 dict，绝不抛错。

    `workdir` = 出片目录（里面有 `gen/`、`piece_*.mp4`、`decisions.json`）。
    """
    workdir = Path(workdir)
    items: list[dict] = []
    try:
        # 🩸 分段产物和决策记录**不在同一个目录**：`gen/`、`piece_*` 在
        #   `triage/`（`clone_pipeline` 传给 `_gen_spans` 的 workdir），
        #   `decisions.json` 写在再上一层。以前按单一目录找 → 口型项被静默跳过。
        seg_root = workdir
        if not (seg_root / "gen").is_dir() and (workdir / "triage" / "gen").is_dir():
            seg_root = workdir / "triage"
        dec = (_json(workdir / "decisions.json")
               or _json(seg_root / "decisions.json")
               or _json(workdir.parent / "decisions.json") or {})
        spans = [(float(a), float(b)) for a, b in (dec.get("spans") or [])]
        gen_dir = seg_root / "gen"
        gens = sorted(gen_dir.glob("chunk_*.mp4")) if gen_dir.is_dir() else []

        if not gens:
            return {"ok": True, "verdict": "skipped",
                    "items": [], "why": "这次没有模型生成的段（全静帧 / 全保留原片）"}

        if spans and video is not None and Path(video).exists():
            try:
                items += _lip_items(spans, gens, Path(video))
            except Exception as e:  # noqa: BLE001
                log.warning("口型没量成：%s", e)
                items.append({"key": "lip", "label": "口型",
                              "verdict": "skipped", "why": str(e)})

        try:
            items += _seg_identity_items(gens)
        except Exception as e:  # noqa: BLE001
            log.warning("段间身份没量成：%s", e)
            items.append({"key": "id_cross", "label": "段间身份",
                          "verdict": "skipped", "why": str(e)})

        if spans and video is not None and Path(video).exists():
            try:
                items += _bg_items(Path(video), spans, gens, seg_root)
            except Exception as e:  # noqa: BLE001
                log.warning("背景没量成：%s", e)
                items.append({"key": "bg", "label": "背景",
                              "verdict": "skipped", "why": str(e)})
    except Exception as e:  # noqa: BLE001
        log.warning("成品契约整体没量成（不影响出片）：%s", e)
        return {"ok": True, "verdict": "skipped", "items": [], "why": str(e)}

    fails = [i for i in items if i.get("verdict") == "fail"]
    measured = [i for i in items if i.get("verdict") in ("pass", "fail")]
    return {
        # ok=False = 真的量出了不合格项（不是"没量成"）
        "ok": not fails,
        "verdict": ("fail" if fails else
                    "pass" if measured else "info"),
        "items": items,
        "failed": [i["label"] for i in fails],
    }
