"""P16 验收：出片后身份核对（D1，SFace 同人判据）。

零模型调用、不花钱：人脸模型是本地 onnx，素材是工程里已有的参考图/成片。

  S1 可用性   —— 模型在就 available()=真；把路径指歪 → 假，且 check 返回 skipped 不抛错
  S2 同人自证 —— 同一张图自比 ≈1.0；**水平翻转**后仍 ≥0.363（尺子没装反）
  S3 异人对照 —— 25 张参考图两两比对，看分布能不能把人和人分开
  S4 四类判定 —— swapped / not_swapped / no_face / no_ref 各走一遍（桩）
                 🩸 关键回归：**一张幸运帧高于阈值、但整体都低** 必须仍判 not_swapped
  S5 抽样上限 —— max_sec / step 真的生效（桩计数，不是「大概」）
  S6 接线     —— 出片链路返回值有 identity；没换人不跑；预览不跑；结果页四种话都有

🩸 **尺子先自证**：S2 是正样本（定义上同人），S3 是分布（能不能分开）。
S4 里那条「幸运帧」用的是 2026-10-25 的真实翻车样本
（`2f1f26d8/0c656558`，`OPEN-DEFECTS.md` V25-2 先于本模块就记为「没换脸」）：
最高帧 0.475 > 0.363 但 p90 0.332 —— 判据若不改，这个已知坏样本会被报成「换上了」。

校准样本量：**1 好 + 1 坏**。p16 不宣称「准确率已验证」，只宣称
「逻辑对、已知坏样本不会假绿」。

跑法：python scripts/p16_check.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# 🚦 必须点名型号（2026-10-26）：一轮只跑一家
from _model_gate import sel_or_exit as _sel
SEL = _sel()

import numpy as np  # noqa: E402

from app.services import identity  # noqa: E402

FRONT = ROOT.parent / "frontend" / "app" / "src"
CLONES = ROOT / "data" / "clone"

rows: list[tuple[str, bool, str]] = []


def chk(name: str, ok, detail: str = "") -> None:
    rows.append((name, bool(ok), detail if not ok else ""))


def skip(name: str, why: str) -> None:
    rows.append((name, True, f"SKIP：{why}"))


TMP = Path(tempfile.mkdtemp(prefix="p16_", dir="D:/tmp"))

# ---------------------------------------------------------------------------
# S1 可用性（成对）
chk("S1 两个模型都在 → available() 为真", identity.available(),
    f"yunet={identity.YUNET.exists()} sface={identity.SFACE.exists()}")

_y, _s = identity.YUNET, identity.SFACE
identity.YUNET = TMP / "nope_yunet.onnx"
chk("S1 模型缺一个 → available() 为假（缺东西别硬跑）", not identity.available(), "")
_res = identity.check(TMP / "nope.mp4", {"person": TMP / "nope.jpg"})
chk("S1 模型缺了 check() 返回 skipped 而不是抛错",
    _res.get("skipped") and _res.get("people") == [], str(_res))
identity.YUNET = _y

# ---------------------------------------------------------------------------
# S2 同人自证（真素材）
subs = sorted(CLONES.glob("*/subject.jpg"))
usable = []
if identity.available():
    for p in subs:
        got = identity.ref_face(p)
        if got is not None:
            usable.append((p, got[0]))

if not usable:
    skip("S2 同人自证", "没有可用的参考图素材")
else:
    p0, f0 = usable[0]
    chk("S2 同一张图自比 ≈ 1.0", abs(identity._cos(f0, f0) - 1.0) < 1e-6,
        str(identity._cos(f0, f0)))

    import cv2  # noqa: PLC0415

    flip = TMP / "flip.jpg"
    cv2.imwrite(str(flip), cv2.flip(cv2.imread(str(p0)), 1))
    got = identity.ref_face(flip)
    if got is None:
        chk("S2 镜像后仍认得出脸（尺子没装反）", False, "翻转图认不出脸")
    else:
        mir = identity._cos(got[0], f0)
        chk("S2 镜像后仍判同人（≥0.363，尺子没装反）", mir >= identity.THRESHOLD,
            f"mirror={mir:.3f}")
        chk("S2 镜像不是 1.0（说明比的是脸不是像素）", mir < 0.999, f"mirror={mir:.3f}")

    # -----------------------------------------------------------------------
    # S3 异人对照（真素材分布）
    keys = [p.parent.name[:8] for p, _ in usable]
    feats = [f for _, f in usable]
    pairs = []
    for i in range(len(feats)):
        for j in range(i + 1, len(feats)):
            pairs.append(identity._cos(feats[i], feats[j]))
    pairs.sort()
    med = pairs[len(pairs) // 2]
    above = sum(1 for s in pairs if s >= identity.THRESHOLD)
    print(f"  [S3] 可认脸素材 {len(feats)} 张 / {len(pairs)} 对："
          f"最低 {pairs[0]:.3f} / 中位 {med:.3f} / 最高 {pairs[-1]:.3f}"
          f"；≥0.363 的 {above}/{len(pairs)}")
    chk("S3 不同素材之间多数判「不同人」（中位 < 0.363）", med < identity.THRESHOLD,
        f"中位={med:.3f}")
    chk("S3 尺子能分开（至少存在一对 < 0.363）", pairs[0] < identity.THRESHOLD,
        f"最低={pairs[0]:.3f}")
    if above:
        print(f"  [S3] 注意：{above} 对 ≥ 阈值（多为同一个人被多个任务复用），"
              "不属于误判")

# ---------------------------------------------------------------------------
# S4 四类判定（桩：绕开真实图片，只测判定逻辑）


class _FakeCap:
    """假视频：每帧第 0 个像素存帧号，供假识别器查相似度表。"""

    def __init__(self, path):
        self.n = 0
        self.total = 10_000
        self.released = False

    def isOpened(self):
        return True

    def get(self, _prop):
        return 10.0  # fps

    def _img(self):
        # 帧号 = 循环里的 n（read 前不递增），这样相似度表下标就是抽帧下标
        img = np.zeros((8, 8, 3), np.uint8)
        img[0, 0, 0] = self.n % 256
        return img

    def grab(self):
        self.n += 1
        return self.n < self.total

    def read(self):
        img = self._img()
        self.n += 1
        return (self.n < self.total, img)

    def release(self):
        self.released = True


class _FakeRec:
    SIMS: list[float] = []

    def alignCrop(self, img, _box):
        return img

    def feature(self, img):
        return np.array([self.SIMS[img[0, 0, 0] % len(self.SIMS)]])


def _boxes():
    return np.array([[0, 0, 8, 8, 2, 2, 6, 2, 4, 7, 0, 0, 0, 0, 1.0]], np.float32)


def run_stub(sims, *, ref_ok=True, faces=True, frames=40, **kw):
    """跑一遍 check，返回结果。"""
    import cv2  # noqa: PLC0415

    old = (identity._faces, identity._recognizer, identity.ref_face,
           identity._cos, cv2.VideoCapture)
    try:
        _FakeRec.SIMS = list(sims)
        identity._faces = lambda c, img: (_boxes() if faces else np.empty((0, 15)),
                                          None)
        identity._recognizer = lambda c: _FakeRec()
        identity.ref_face = (lambda p: (np.array([1.0]), 1)) if ref_ok else (
            lambda p: None)
        identity._cos = lambda a, b: float(a[0])
        cv2.VideoCapture = lambda p: _set_total(_FakeCap(p), frames)
        return identity.check(Path("stub.mp4"), {"person": Path(__file__)}, **kw)
    finally:
        (identity._faces, identity._recognizer, identity.ref_face,
         identity._cos, cv2.VideoCapture) = old


def _set_total(cap, frames):
    cap.total = frames
    return cap


# 全是高相似度 → 换上了
r = run_stub([0.8, 0.7, 0.75, 0.9])
chk("S4 普遍像参考图 → swapped",
    r["people"][0]["verdict"] == "swapped", str(r["people"][0]))

# 普遍低 → 没换上
r = run_stub([0.1, 0.2, 0.15, 0.25])
chk("S4 普遍不像 → not_swapped",
    r["people"][0]["verdict"] == "not_swapped", str(r["people"][0]))

# 🩸 关键回归：一帧幸运高、其余都低（真实翻车样本的形态）
sims = [0.12] * 36 + [0.475, 0.16, 0.14, 0.18]
r = run_stub(sims)
p = r["people"][0]
chk("S4 只有一帧高于阈值 → 仍判 not_swapped（最高值不能说了算）",
    p["verdict"] == "not_swapped" and p["best_sim"] >= identity.THRESHOLD,
    str(p))
chk("S4 判定用的是 p90（同一份数据 p90 必须低于阈值）",
    p["p90"] < identity.THRESHOLD, str(p))

# 没脸
r = run_stub([0.9], faces=False)
chk("S4 成片里没有脸 → no_face", r["people"][0]["verdict"] == "no_face",
    str(r["people"][0]))

# 参考图认不出
r = run_stub([0.9], ref_ok=False)
chk("S4 参考图认不出脸 → no_ref", r["people"][0]["verdict"] == "no_ref",
    str(r["people"][0]))

# 🩸 双人：一张脸只能算给一个人（2026-10-25 实测 `3f91496d` 只换成一个）
# 假数据：脸A 对 person=0.90、对 person2=0.45；脸B 对 person=0.30、对 person2=0.20。
# 取"全场最大"→ person2 拿到 0.45（>0.363，假绿）；一人一张地分 → 只有 0.20（对）。
def _run_two_targets():
    import cv2  # noqa: PLC0415

    table = {(0.0, 1.0): 0.90, (0.0, 2.0): 0.45,
             (1.0, 1.0): 0.30, (1.0, 2.0): 0.20}
    state = {"i": 0}

    def _feat(_self, _img):
        v = float(state["i"] % 2)
        state["i"] += 1
        return np.array([v])

    old = (identity._faces, identity._recognizer, identity.ref_face,
           identity._cos, cv2.VideoCapture, _FakeRec.feature)
    try:
        _FakeRec.feature = _feat
        identity._faces = lambda c, img: (
            np.array([[0, 0, 8, 8, 2, 2, 6, 2, 4, 7, 0, 0, 0, 0, 1.0]] * 2,
                     np.float32), None)
        identity._recognizer = lambda c: _FakeRec()
        identity.ref_face = lambda p: (
            np.array([1.0 if Path(p).name == "a.jpg" else 2.0]), 1)
        identity._cos = lambda e, f: table[(float(e[0]), float(f[0]))]
        cv2.VideoCapture = lambda p: _set_total(_FakeCap(p), 40)
        for _n in ("a.jpg", "b.jpg"):
            (TMP / _n).write_bytes(b"x")
        return identity.check(Path("stub.mp4"),
                              {"person": TMP / "a.jpg",
                               "person2": TMP / "b.jpg"})
    finally:
        (identity._faces, identity._recognizer, identity.ref_face,
         identity._cos, cv2.VideoCapture) = old[:5]
        _FakeRec.feature = old[5]


r2 = _run_two_targets()
_by = {x["slot"]: x for x in r2["people"]}
chk("S4 双人：换进去的那张脸算给本人（person=0.90）",
    _by["person"]["verdict"] == "swapped" and _by["person"]["p90"] == 0.9,
    str(_by.get("person")))
chk("S4 双人：另一张参考只能拿自己那张脸 → not_swapped（不许串脸假绿）",
    _by["person2"]["verdict"] == "not_swapped", str(_by.get("person2")))

# 没换人 → 不跑
r = identity.check(TMP / "x.mp4", {"wardrobe": TMP / "w.jpg"})
chk("S4 没给 person 槽位 → skipped（服装图不是人）",
    bool(r.get("skipped")) and r["people"] == [], str(r))

# ---------------------------------------------------------------------------
# S5 抽样上限 / 步长
r = run_stub([0.9], frames=10_000, step=0.4, max_sec=2.0)
# fps=10、step 0.4 → 每 4 帧取 1；2 秒 = 20 帧 → 取 5 帧
chk("S5 2 秒 / 步长 0.4 秒 → 只抽 5 帧（不是逐帧）",
    r["people"][0]["frames"] == 5, str(r["people"][0]["frames"]))

r = run_stub([0.9], frames=10_000)
chk("S5 默认 60 秒上限生效（最长片也只抽 ~150 帧）",
    r["people"][0]["frames"] <= 151, str(r["people"][0]["frames"]))

# ---------------------------------------------------------------------------
# S6 接线
cp = (ROOT / "app" / "services" / "clone_pipeline.py").read_text(
    encoding="utf-8", errors="ignore")
chk("S6 出片链路调了 identity.check", "identity.check(" in cp, "")
chk("S6 出片返回值带 identity 键", '"identity": id_res' in cp, "")
chk("S6 只在换过人时才跑", 'startswith("person")' in cp, "")
chk("S6 核对失败不阻断（except → skipped，不 raise）",
    "身份核对没跑成（不影响出片）" in cp, "")
_pv = (cp.split("def preview_render(")[1].split("\ndef ")[0]
       if "def preview_render(" in cp else "")
chk("S6 预览不跑（预览不出片，没有核对对象）",
    bool(_pv) and "identity.check(" not in _pv, "")

cj = (ROOT / "app" / "services" / "clone_jobs.py").read_text(
    encoding="utf-8", errors="ignore")
chk("S6 出片记录落盘 identity", 'item["identity"]' in cj, "")

api = (ROOT / "app" / "api" / "clone.py").read_text(encoding="utf-8",
                                                    errors="ignore")
chk("S6 详情接口下发 identity", '"identity": r.get("identity")' in api, "")
_exp = api.split("for r in (task.get(\"renders\") or [])")[0].rsplit("renders\": [", 1)
chk("S6 配方导出不夹带 identity（那是某一次产出的量具，不是配方）",
    len(_exp) == 2 and '"identity",' in _exp[1], "")

res = (FRONT / "pages" / "clone" / "result.vue").read_text(
    encoding="utf-8", errors="ignore")
chk("S6 结果页有身份提示这一行", "idNote" in res and "idBad" in res, "")
chk("S6 结果页四种话都写了（换上 / 没换上 / 没脸 / 参考图认不出）",
    all(k in res for k in ("已换上", "换脸可能没成功", "没找到人脸", "认不出人脸")), "")
chk("S6 核对不了的情况不标红（只有 not_swapped 才 warn）",
    "verdict === 'not_swapped'" in res, "")

# ---------------------------------------------------------------------------
# S7 真样本回归（1 好 + 1 坏，都是**先于本模块**就有独立结论的）
# 坏：`2f1f26d8/0c656558` person —— OPEN-DEFECTS V25-2「从头到尾没换脸」
# 好：同一条片的 person2 —— 同一份记录「单图全属性那位换成了」
_cid = next(iter(CLONES.glob("2f1f26d8*")), None)
_vid = (next(iter((_cid / "render").glob("0c656558*")), None) if _cid else None)
if _vid and (_vid / "out.mp4").exists() and identity.available():
    _refs = {"person": _cid / "subject.jpg",
             "person2": _cid / "ref_person2.jpg"}
    _r = identity.check(_vid / "out.mp4", _refs)
    by = {p["slot"]: p for p in _r["people"]}
    print(f"  [S7] 真样本：person(p90={by.get('person', {}).get('p90')}) "
          f"person2(p90={by.get('person2', {}).get('p90')})")
    chk("S7 已知没换上的那位 → not_swapped（不能报假绿）",
        by.get("person", {}).get("verdict") == "not_swapped", str(by.get("person")))
    chk("S7 已知换成了的那位 → swapped",
        by.get("person2", {}).get("verdict") == "swapped", str(by.get("person2")))
else:
    skip("S7 真样本回归", "样本成片不在本机")

# 🩸 第二组真样本（2026-10-25 `3f91496d/0011250c`）：双人换人**只换成一个**。
# 肉眼 + 逐脸比对：背景那位换成了（汉服女），前景自拍那位**一帧没换**。
# 旧算法取"全场最大"，把换进去那张脸算成了另一张参考的 0.46 → 两位都报 swapped。
_cid2 = next(iter(CLONES.glob("3f91496d*")), None)
_vid2 = (next(iter((_cid2 / "render").glob("0011250c*")), None) if _cid2 else None)
if _vid2 and (_vid2 / "out.mp4").exists() and identity.available():
    _r2 = identity.check(_vid2 / "out.mp4",
                         {"person": _cid2 / "subject.jpg",
                          "person2": _cid2 / "ref_person2.jpg"})
    by2 = {p["slot"]: p for p in _r2["people"]}
    print(f"  [S7b] 真样本：person(p90={by2.get('person', {}).get('p90')}) "
          f"person2(p90={by2.get('person2', {}).get('p90')})")
    chk("S7b 双人只换成一个 → 没换的那位必须 not_swapped（不许串脸假绿）",
        by2.get("person2", {}).get("verdict") == "not_swapped",
        str(by2.get("person2")))
    chk("S7b 换成了的那位仍判 swapped",
        by2.get("person", {}).get("verdict") == "swapped", str(by2.get("person")))
else:
    skip("S7b 双人真样本回归", "样本成片不在本机")

# ---------------------------------------------------------------------------
bad = [r for r in rows if not r[1]]
for name, ok, detail in rows:
    tag = "  ok   "
    if not ok:
        tag = "  FAIL "
    elif detail.startswith("SKIP"):
        tag = "  skip "
    print(tag + name + (f"  [{detail[:200]}]" if detail else ""))
print(f"\n{len(rows) - len(bad)}/{len(rows)} 通过（零模型调用）")
if bad:
    print("\n🩸 人核：上面的失败项要回原文确认再改，不许直接改断言。")
sys.exit(1 if bad else 0)
