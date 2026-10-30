"""P14 验收：尾帧锁定（B6，火山「图生视频-首尾帧」）。

零模型调用、不花钱：HTTP / 下载 / 抽帧 / 生图 / 生视频全部用桩，只用本地临时文件。

  S1 请求体    —— 尾帧排在首帧之后；只给首帧时请求里没有尾帧
  S2 只有尾帧  —— 报错（官方只有「首帧」「首尾帧」两种，没有单独尾帧）
  S3 宽高比    —— 2.5 首尾帧强制 adaptive；2.0 保持用户值；不带尾帧的 2.5 不动
  S4 缓存键    —— 尾帧开关不同 → 键不同；关着时与改动前逐字一致
  S5 末帧时刻  —— 抽 end-0.05 而不是 end（切点那一帧是下一镜的画面）
  S6 编辑路径  —— 参考视频任务里没有任何首帧/尾帧（官方三种场景互斥）
  S7 接线      —— EditIn / normalize / clone_pipeline / 前端开关

官方出处（`docs/volc-api`，本地抓的官方文档）：
  :27/:37/:221/:237/:241/:243  首尾帧 = 首帧图 + 尾帧图 + 提示词，role=first_frame/last_frame
  :247                         宽高比不一致 → 以首帧为主，尾帧自动裁剪
  :269                         首帧 / 首尾帧 / 全模态参考 **三种互斥**
  :505                         2.5 首尾帧默认且仅支持 adaptive

跑法：python scripts/p14_check.py --model volc20|volc25|h3
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import ark, edit_spec, generate, scene, video_edit  # noqa: E402
from app.services import retry  # noqa: E402

FRONT = ROOT.parent / "frontend" / "app" / "src"

# 2.5 / 2.0 的型号 id（`model_specs.SPECS` 里的官方名）
M25 = "doubao-seedance-2-5-260628"
M20 = "doubao-seedance-2-0-260128"

rows: list[tuple[str, bool, str]] = []

# 🚦 必须点名型号（2026-10-26）：一轮只跑一家。
from _model_gate import sel_or_exit as _sel_or_exit
SEL = _sel_or_exit()


def chk(name: str, ok, detail: str = "") -> None:
    rows.append((name, bool(ok), detail if not ok else ""))


TMP = Path(tempfile.mkdtemp(prefix="p14_", dir="D:/tmp"))


def _mk(name: str, data: bytes = b"STUB") -> Path:
    p = TMP / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


A = _mk("first.jpg", b"FIRST")
B = _mk("last.jpg", b"LAST")
SRC = _mk("src.mp4", b"SRC")

# ---------------------------------------------------------------------------
# 桩：截请求体、不下载、不真发图（`_data_uri` 只回文件名，便于核对顺序）

_bodies: list[dict] = []


class _Resp:
    status_code = 200
    text = ""

    def json(self):
        return {"id": "stub-tid"}


def _fake_post(c, url, *, headers=None, json=None, **kw):  # noqa: A002
    _bodies.append(json or {})
    return _Resp()


_real = {
    "post": retry.post,
    "dl": ark._download_video,
    "load": ark._load_tid,
    "uri": ark._data_uri,
    "save": ark._save_tid,
}
retry.post = _fake_post
ark._download_video = lambda tid, out, *, timeout, poll: (
    Path(out).write_bytes(b"VIDEO") or Path(out))
ark._load_tid = lambda out, body: ""
ark._save_tid = lambda out, tid, body: None
ark._data_uri = lambda p, *a, **k: f"data:image/jpeg;base64,{Path(p).name}"


def call_video(**kw) -> dict:
    _bodies.clear()
    out = TMP / f"o{len(_bodies)}_{abs(hash(tuple(sorted(kw)))) % 9999}.mp4"
    ark.generate_video("同一个人走过", out=out, **kw)
    return _bodies[-1] if _bodies else {}


def img_roles(body: dict) -> list[str]:
    return [c.get("role") for c in (body.get("content") or [])
            if c.get("type") == "image_url"]


def img_urls(body: dict) -> list[str]:
    return [str((c.get("image_url") or {}).get("url") or "")
            for c in (body.get("content") or []) if c.get("type") == "image_url"]


# ---------------------------------------------------------------------------
# S1 请求体：两张图都发，顺序「先首后尾」

b = call_video(first_frame=A, last_frame=B, model=M20, duration=5, ratio="9:16")
chk("S1 首尾帧都发出，尾帧排在首帧之后",
    img_roles(b) == ["first_frame", "last_frame"], str(img_roles(b)))
urls = img_urls(b)
chk("S1 首帧图/尾帧图各自对上文件（没串位）",
    len(urls) == 2 and urls[0].endswith("first.jpg") and urls[1].endswith("last.jpg"),
    str(urls))

b1 = call_video(first_frame=A, model=M20, ratio="9:16")
chk("S1 只给首帧 → 请求里没有 last_frame（老行为不变）",
    img_roles(b1) == ["first_frame"], str(img_roles(b1)))

# ---------------------------------------------------------------------------
# S2 只给尾帧 → 报错

err = ""
try:
    ark.generate_video("同一人", out=TMP / "o_bad.mp4", last_frame=B, model=M20)
except ark.ArkError as e:  # noqa: PERF203
    err = str(e)
chk("S2 只给尾帧不给首帧 → 报错（官方没有单独的尾帧场景）",
    bool(err) and "首帧" in err, err[:120])

# ---------------------------------------------------------------------------
# S3 宽高比：2.5 只认 adaptive，2.0 保持用户值

if SEL == "volc25":
    b25 = call_video(first_frame=A, last_frame=B, model=M25, ratio="9:16")
    chk("S3 2.5 + 9:16 + 尾帧 → 强制 adaptive（`volc-api:505`）",
        b25.get("ratio") == "adaptive", str(b25.get("ratio")))
    b25n = call_video(first_frame=A, model=M25, ratio="9:16")
    chk("S3 2.5 但不带尾帧 → 不动宽高比（自适应规则只属于首尾帧）",
        b25n.get("ratio") == "9:16", str(b25n.get("ratio")))
elif SEL == "volc20":
    b20 = call_video(first_frame=A, last_frame=B, model=M20, ratio="9:16")
    chk("S3 2.0 + 9:16 + 尾帧 → 保持 9:16（不误伤，官方允许指定）",
        b20.get("ratio") == "9:16", str(b20.get("ratio")))

# ---------------------------------------------------------------------------
# S4/S5 生成链：缓存键 + 末帧时刻

REC = {
    "source": {"width": 1080, "height": 1920},
    "shots": [{"i": 1, "start": 10.0, "end": 14.0}],
}

_frames: list[float] = []
_vids: list[dict] = []
_keys: list[str] = []

_real_ef = scene.extract_frame
_real_gi = ark.generate_image
_real_put = generate._cache_put


def _fake_ef(video, t, out, width=None, **kw):
    _frames.append(round(float(t), 3))
    o = Path(out)
    o.parent.mkdir(parents=True, exist_ok=True)
    o.write_bytes(b"JPG")
    return o


def _fake_gi(prompt, *, out=None, **kw):
    o = Path(out)
    o.parent.mkdir(parents=True, exist_ok=True)
    o.write_bytes(b"JPG")
    return o


def _fake_gv(prompt, *, out=None, first_frame=None, last_frame=None, **kw):
    _vids.append({"first": Path(first_frame).name if first_frame else "",
                  "last": Path(last_frame).name if last_frame else ""})
    o = Path(out)
    o.parent.mkdir(parents=True, exist_ok=True)
    o.write_bytes(b"MP4" * 200)
    return o


scene.extract_frame = _fake_ef
ark.generate_image = _fake_gi
ark.generate_video = _fake_gv
generate._cache_put = lambda cache_dir, key, src: _keys.append(key)


def run(lock_tail: bool, tag: str) -> str:
    _frames.clear()
    _vids.clear()
    _keys.clear()
    generate.regen_shots(
        SRC, REC, [1], prompt="换成同一个人", workdir=TMP / f"w_{tag}",
        cache_dir=TMP / f"c_{tag}", lock_tail=lock_tail,
    )
    return _keys[-1] if _keys else ""


key_off = run(False, "off")
off_frames = list(_frames)
off_last = _vids[-1]["last"] if _vids else "?"

key_on = run(True, "on")
on_frames = list(_frames)
on_last = _vids[-1]["last"] if _vids else "?"
on_first = _vids[-1]["first"] if _vids else "?"

chk("S4 关着时缓存键与改动前逐字一致（历史缓存仍能命中）",
    bool(key_off) and "|lt" not in key_off, key_off)
chk("S4 开着时换键（开了又关不会拿回上一次带尾帧的结果）",
    bool(key_on) and key_on == key_off + "|lt", f"{key_off} vs {key_on}")

# 关：只抽首帧、不发尾帧
chk("S5 关着时每镜只抽 1 帧（不多花钱生图）", len(off_frames) == 1, str(off_frames))
chk("S5 关着时请求里没有尾帧", off_last == "", str(off_last))
chk("S5 开着时每镜抽 2 帧：中点 + 末帧", on_frames == [12.0, 13.95], str(on_frames))
chk("S5 末帧时刻 = end-0.05 且仍在本镜区间内（不拿下一镜的画面）",
    bool(on_frames) and abs(on_frames[-1] - (14.0 - 0.05)) < 1e-6
    and 10.0 <= on_frames[-1] < 14.0, str(on_frames))
chk("S5 尾帧经重绘后作为 last_frame 发给模型（不是原片末帧）",
    on_last == "shot_001_tail.jpg", str(on_last))
chk("S5 首帧仍是首帧（顺序没被打乱）",
    on_first == "shot_001.jpg", str(on_first))

# 规格哈希：关着不能进哈希，开着必须进
h_off = video_edit._spec_for_hash(edit_spec.normalize({}))
h_on = video_edit._spec_for_hash(edit_spec.normalize({"lock_tail": True}))
chk("S4 关着时 lock_tail 不进模型分段哈希（历史出片不失配）",
    "lock_tail" not in h_off, str(list(h_off)))
chk("S4 开着时进哈希（真改了请求，就必须重画）",
    h_on.get("lock_tail") is True, str(h_on.get("lock_tail")))

# ---------------------------------------------------------------------------
# S6 编辑路径：参考视频与首尾帧互斥

eb = ark.edit_body("把第一个人换成@图片1的人", video_url="https://example.com/a.mp4",
                   model=M20)
e_roles = [c.get("role") for c in (eb.get("content") or [])]
chk("S6 编辑任务（参考视频）里没有任何首帧/尾帧（官方三种场景互斥）",
    "first_frame" not in e_roles and "last_frame" not in e_roles, str(e_roles))

# ---------------------------------------------------------------------------
# S7 接线

from app.api.clone import EditIn  # noqa: E402

md = EditIn(**{"lock_tail": True}).model_dump()
chk("S7 EditIn 声明了 lock_tail（不声明 = pydantic 静默丢键）",
    md.get("lock_tail") is True, str(md.get("lock_tail")))
chk("S7 EditIn 默认关（老客户端不带这个键）",
    EditIn().model_dump().get("lock_tail") is False, "")

chk("S7 normalize 认 \"true\" 字符串", edit_spec.normalize({"lock_tail": "true"})["lock_tail"] is True, "")
chk("S7 normalize 默认关", edit_spec.normalize({})["lock_tail"] is False, "")

cp_src = (ROOT / "app" / "services" / "clone_pipeline.py").read_text(
    encoding="utf-8", errors="ignore")
n_wire = cp_src.count('lock_tail=bool((spec or {}).get("lock_tail"))')
chk("S7 两处 regen_shots 都传了 lock_tail（逐镜分诊 + 老镜头档）",
    n_wire >= 2, f"命中 {n_wire} 处")

diag = (FRONT / "pages" / "clone" / "diagnose.vue").read_text(
    encoding="utf-8", errors="ignore")
chk("S7 界面有开关（含费用提示）",
    "lock_tail" in diag and "onLockTail" in diag and "费用会涨" in diag, "")

# ---------------------------------------------------------------------------
# 还原桩
retry.post = _real["post"]           # type: ignore[assignment]
ark._download_video = _real["dl"]    # type: ignore[assignment]
ark._load_tid = _real["load"]        # type: ignore[assignment]
ark._data_uri = _real["uri"]         # type: ignore[assignment]
ark._save_tid = _real["save"]        # type: ignore[assignment]
scene.extract_frame = _real_ef       # type: ignore[assignment]
ark.generate_image = _real_gi        # type: ignore[assignment]
generate._cache_put = _real_put      # type: ignore[assignment]

bad = [r for r in rows if not r[1]]
for name, ok, detail in rows:
    print(("  ok   " if ok else "  FAIL ") + name
          + (f"  [{detail[:220]}]" if not ok else ""))
print(f"\n{len(rows) - len(bad)}/{len(rows)} 通过（零模型调用）")
sys.exit(1 if bad else 0)
