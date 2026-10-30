"""出片后身份核对（D1）：换脸到底换上了没有。

**这是量具，不是官方能力**（台账 D 段）。纯本地 OpenCV，零联网、零费用。

判据：SFace 余弦相似度，**0.363 = 同人**（OpenCV 官方推荐值；台账记
「已在 `32711d24` 验过」）。

🩸 为什么需要它（2026-10-25 的教训）：2.5 双人换人那次，白衣服那位从头到尾
没换成功，而**我看 480p 截图判错了两次**（先说两个都换了）。人眼在小图上不可靠，
这条是纯计算 —— 每次出片自动跑一遍，当场告诉主人「这张脸换上了没有」。

四类判定（`verdict`），判的是**逐帧相似度的 p90**（不是最高值）：
  swapped       p90 ≥ 0.363 → 换上了
  not_swapped   p90 < 0.363 → **换脸可能没成功**
  no_face       成片里一帧都没检测到脸 → 核对不了
  no_ref        参考图里认不出人脸（服装图 / 远景 / 侧脸）→ 核对不了

🩸 **为什么不用最高值**：一条 16 秒的片子抽 40 多帧，最高值等于让一张幸运帧
说了算。已知没换上的那条（`2f1f26d8/0c656558`，`OPEN-DEFECTS.md` V25-2 先于本
模块就记录为「从头到尾没换脸」）最高帧 0.404 > 0.363 → 会报「换上了」；
同一位置的 p90 是 0.298，落在阈值下。同一条片子里换成的那位 p90 0.622。
校准样本 = 1 好 + 1 坏（`p16_check` 会把这两个数一起打出来，不藏）。

🩸 只核 `person*` 槽位：`wardrobe` 是服装图、`product`/`scene` 不是人，
拿它们去比相似度只会制造假红。
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

log = logging.getLogger("identity")

# OpenCV 官方推荐的同人阈值（余弦）
THRESHOLD = 0.363
# 抽样步长与上限：60 秒片子最多 150 帧检测，30 秒片子约 2–3 秒跑完
STEP = 0.4
MAX_SEC = 60.0
# 检测前把画面缩到长边 1080：开销跟像素成正比（4K 直跑 52 秒）。
# 🩸 为什么不缩到 640：缩得越狠、脸越糊，**没换上的脸也会被抬到阈值以上**
# （实测已知没换的样本 p90 640→0.362 / 1080→0.298）。准确性优先，1080 够快。
DETECT_SIDE = 1080

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "data" / "models"
YUNET = MODELS / "face_detection_yunet_2023mar.onnx"
SFACE = MODELS / "sface.onnx"

_PERSON_SLOT = re.compile(r"^person(\d+)?$")


def _cv2():
    """延迟导入：没装 opencv 的环境不该因为这条核对起不来。"""
    import cv2  # noqa: PLC0415

    return cv2


def available() -> bool:
    try:
        _cv2()
    except Exception:  # noqa: BLE001
        return False
    return YUNET.exists() and SFACE.exists()


def _skip(why: str) -> dict:
    return {"ok": True, "skipped": why, "people": []}


def _detector(cv2, w: int, h: int):
    d = cv2.FaceDetectorYN.create(str(YUNET), "", (w, h), 0.6, 0.3, 50)
    d.setInputSize((w, h))
    return d


def _recognizer(cv2):
    return cv2.FaceRecognizerSF.create(str(SFACE), "")


def _shrink(cv2, img, max_side: int = DETECT_SIDE):
    """检测前缩到长边 1080 —— 人脸检测的开销跟画面像素成正比。

    4K 帧上直接跑 YuNet 慢到离谱（实测一条 4K 成片 52 秒）；1080 之后人脸
    仍有足够的像素，够检测够对齐（SFace 输入本来就是 112×112）。
    """
    h, w = img.shape[:2]
    m = max(h, w)
    if m <= max_side:
        return img
    k = max_side / float(m)
    return cv2.resize(img, (max(1, int(round(w * k))), max(1, int(round(h * k)))),
                      interpolation=cv2.INTER_AREA)


def _faces(cv2, img):
    """检测一帧里所有人脸。返回 (faces, None) 或 (None, 原因)。"""
    try:
        d = _detector(cv2, img.shape[1], img.shape[0])
        _, fs = d.detect(img)
        return ([] if fs is None else fs), None
    except Exception as e:  # noqa: BLE001
        return None, f"人脸检测失败：{e}"


def _cos(a, b) -> float:
    import numpy as np  # noqa: PLC0415

    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na <= 0 or nb <= 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def ref_face(path: Path):
    """参考图里**面积最大**那张脸的特征。

    用户可能传合影或全身照 —— 最大的那张通常就是他要换的人。
    认不出脸返回 None（由调用方判 `no_ref`）。
    """
    if not available():
        return None
    try:
        cv2 = _cv2()
        img = cv2.imread(str(path))
        if img is None:
            return None
        img = _shrink(cv2, img)
        fs, err = _faces(cv2, img)
        # 🩸 不能用 `not fs` 判空：yuNet 返回的是 numpy 数组，
        # `if array` 会抛「truth value of an array is ambiguous」，被下面的
        # except 吞掉 → **每张图都被判成认不出脸**（探针实测 25/25 全 None）。
        if err or fs is None or len(fs) == 0:
            return None
        best = max(fs, key=lambda f: float(f[2]) * float(f[3]))
        rec = _recognizer(cv2)
        return (rec.feature(rec.alignCrop(img, best)).flatten(), len(fs))
    except Exception as e:  # noqa: BLE001
        log.warning("参考图人脸提取失败（%s）：%s", Path(path).name, e)
        return None


def check(video: Path, refs: dict | None, *, step: float = STEP,
          max_sec: float = MAX_SEC) -> dict:
    """扫一遍成片，看每个被换的人有没有出现在画面里。

    🩸 **绝不抛错**：核对失败一律返回 `skipped`。钱已经花了，对账这一步
    不该成为出片失败的原因（与 `qc` 同一条口径）。
    """
    if not available():
        return _skip("人脸模型没装齐（data/models 里缺 yunet / sface）")

    persons = {k: v for k, v in (refs or {}).items()
               if _PERSON_SLOT.match(str(k)) and v and Path(v).exists()}
    if not persons:
        return _skip("这次没换人，没有可比的对象")

    try:
        cv2 = _cv2()
    except Exception as e:  # noqa: BLE001
        return _skip(f"opencv 不可用：{e}")

    # 先把参考图的人脸算出来；一个都认不出就没必要扫片子了
    targets = []
    for slot, p in persons.items():
        got = ref_face(Path(p))
        if got is None:
            targets.append({"slot": slot, "feat": None, "ref_faces": 0})
        else:
            targets.append({"slot": slot, "feat": got[0], "ref_faces": got[1]})
    if not any(t["feat"] is not None for t in targets):
        return {"ok": True, "skipped": "参考图里认不出人脸（服装图/远景/侧脸）",
                "people": [{"slot": t["slot"], "verdict": "no_ref",
                            "ref_faces": t["ref_faces"]} for t in targets]}

    try:
        cap = cv2.VideoCapture(str(video))
        if not cap.isOpened():
            return _skip("成片打不开（可能已被清理）")
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0) or 25.0
        # 每 step 秒一帧；上限 max_sec 秒
        stride = max(1, int(round(fps * max(0.1, float(step)))))
        limit = int(round(max(0.0, float(max_sec)) * fps))
        rec = _recognizer(cv2)
        # 每人每题：每一采样帧「最像参考图的那张脸」的相似度
        best = {t["slot"]: -1.0 for t in targets}
        at = {t["slot"]: 0.0 for t in targets}
        per_frame = {t["slot"]: [] for t in targets}
        n = 0
        while n < limit:
            # 🩸 不用抽的帧只 grab 不 retrieve：`read()` = grab + **解码整帧**。
            # 逐帧解码一条 60 秒 1080p 要 70 秒（实测 `394fdd58/b1566009` 72.5s），
            # 而这里每 0.4 秒才用一帧 —— 跳过解码省掉 99% 的开销。
            if n % stride:
                if not cap.grab():
                    break
                n += 1
                continue
            ok, img = cap.read()
            if not ok:
                break
            img = _shrink(cv2, img)
            fs, err = _faces(cv2, img)
            if err:
                # 单帧检测失败不中断（后面还有几百帧），累计到日志就够
                log.debug("第 %d 帧检测失败：%s", n, err)
                fs = []
            t_sec = n / fps
            # 这一帧里每张脸的特征先算一次，再跟每个目标比
            embs = []
            for f in (fs if fs is not None else []):
                try:
                    embs.append(rec.feature(rec.alignCrop(img, f)).flatten())
                except Exception:  # noqa: BLE001
                    continue
            if not embs:
                n += 1
                continue
            if len(targets) == 1:
                t = targets[0]
                if t["feat"] is None:
                    n += 1
                    continue
                sim = max(_cos(e, t["feat"]) for e in embs)
                per_frame[t["slot"]].append(round(sim, 3))
                if sim > best[t["slot"]]:
                    best[t["slot"]] = sim
                    at[t["slot"]] = t_sec
                n += 1
                continue
            # 🩸 多人：**一张脸只能算给一个人**（按相似度贪心配对）。
            # 2026-10-25 实测（`3f91496d` 双人换人，只换成功一个）：
            # 换进去的那张脸对**另一张参考图**也有 0.375–0.423 的相似度，
            # 而没换的那位（原片本人）对两张参考都只有 0.10–0.23。
            # 取"全场最大"会把别人的脸算成你的 → 没换的人被报成 swapped（假绿）。
            # 同一个人的两张参考本来就该抢同一张脸，所以必须一人一张地分。
            pairs = []
            for ti, t in enumerate(targets):
                if t["feat"] is None:
                    continue
                for ei, e in enumerate(embs):
                    pairs.append((_cos(e, t["feat"]), ti, ei))
            pairs.sort(reverse=True)
            used_t: set[int] = set()
            used_e: set[int] = set()
            for sim, ti, ei in pairs:
                if ti in used_t or ei in used_e:
                    continue
                used_t.add(ti)
                used_e.add(ei)
                slot = targets[ti]["slot"]
                per_frame[slot].append(round(sim, 3))
                if sim > best[slot]:
                    best[slot] = sim
                    at[slot] = t_sec
            n += 1
        cap.release()
    except Exception as e:  # noqa: BLE001
        log.warning("身份核对没跑成（不影响出片）：%s", e)
        return _skip(f"核对没跑成：{e}")

    people = []
    for t in targets:
        slot = t["slot"]
        vals = per_frame[slot]
        if t["feat"] is None:
            people.append({"slot": slot, "ref_faces": t["ref_faces"],
                           "best_sim": None, "p90": None, "share": None,
                           "at": None, "frames": 0, "verdict": "no_ref"})
            continue
        if not vals:
            people.append({"slot": slot, "ref_faces": t["ref_faces"],
                           "best_sim": None, "p90": None, "share": None,
                           "at": None, "frames": 0, "verdict": "no_face"})
            continue
        # 🩸 判据用 **p90 而不是最高值**：最高值只看一张幸运帧 —— 已知没换上的
        # 那条（`2f1f26d8/0c656558`，OPEN-DEFECTS V25-2）最高帧 0.404 > 0.363，
        # 会报「换上了」；p90 是 0.298，落在阈值下；换成了的那位 p90 0.622。
        # p90 同时扛得住「这个人只在片子里出现一小段」。
        srt = sorted(vals)
        p90 = srt[min(len(srt) - 1, int(round(0.9 * (len(srt) - 1))))]
        share = sum(1 for v in vals if v >= THRESHOLD) / float(len(vals))
        sim = best[slot]
        people.append({"slot": slot, "ref_faces": t["ref_faces"],
                       "best_sim": round(sim, 3),
                       "p90": round(p90, 3),
                       "share": round(share, 3),
                       "at": round(at[slot], 1),
                       "frames": len(vals),
                       "verdict": "swapped" if p90 >= THRESHOLD else "not_swapped"})

    bad = [p for p in people if p["verdict"] == "not_swapped"]
    return {
        # ok=False 表示「发现了问题」：有参考图的人没在成片里出现
        "ok": not bad,
        "skipped": "",
        "threshold": THRESHOLD,
        "people": people,
    }
