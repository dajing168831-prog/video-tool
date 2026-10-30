# -*- coding: utf-8 -*-
"""模型分离门禁：核心代码里**不许再长出新的厂商耦合**。

背景（2026-10-26 主人拍板）：
「现在到处都还绑定在一起，如果后期我们开发聚合平台这项目直接黄」

🩸 2026-10-26 深夜修正：**第一版尺子是坏的**。它只认 `== "volc"` / `== "minimax"`
这种**等号比较**，而且只扫 3 个文件 —— 于是
    `if ch != "minimax"`            （不等号）
    `_min_for("minimax", model)`    （当参数传）
    `"volc": {...}`                 （当字典键）
    `channel in ("volc", "minimax")`（成员判断）
全都数不到，报出「核心耦合 34 → 0」。**那是假绿。**
现在改口径：**代码行里出现厂商字面量就算一处**，不管它是等号、不等号、参数、字典键
还是成员判断。文件也从 3 个扩到 7 个（把延长链和接口层算进来）。

为什么用**棘轮**（ratchet）而不是"必须为 0"：搬迁要分几轮做，一刀切会让门一直红，
红久了就没人看。所以记录当前数，**只许降不许升** —— 谁再加一处就立刻红。

用法：
    python scripts/model_separation_check.py            # 对照基线
    python scripts/model_separation_check.py --update   # 搬迁完成后更新基线
    python scripts/model_separation_check.py --selftest  # 自证尺子
零依赖、不联网、不花钱。
"""
from __future__ import annotations

import ast
import hashlib
import io
import json
import re
import shutil
import sys
import tempfile
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASELINE = ROOT / "scripts" / "_model_separation_baseline.json"

#: 核心文件：这些文件"不该知道有几家模型"。
#: 🩸 只扫编译器三个文件是不够的 —— 延长链（`extend.py`）和接口层
#: （`api/clone.py` / `api/routes.py`）才是加第 4 家最容易漏的地方。
CORE = [
    "app/services/video_edit.py",
    "app/services/edit_spec.py",
    "app/services/clone_pipeline.py",
    "app/services/extend.py",
    "app/services/clone_jobs.py",
    "app/api/clone.py",
    "app/api/routes.py",
]

#: 厂商字面量 / 厂商专属配置字段 / 具体型号 —— 出现任何一种都算"这个文件认识厂商"
VENDOR = re.compile(
    r"""['"](?:volc|minimax)['"]"""
    r"""|ark_video_edit_model|minimax_video_model|ark_video_model"""
    r"""|doubao-seedance|MiniMax-H\d|seedance-2-"""
)


def _text_lines(text: str) -> set[int]:
    """整行落在注释或多行字符串（docstring）里的行号 —— 这些不是代码。

    🩸 2026-10-26：以前只排除 `#` 开头的行，**docstring 里的说明文字被当成代码数**，
    于是「解释以前这里是 `if channel == "volc"`」这句说明本身也算一处耦合。
    判据要量代码，不量说明。
    """
    skip: set[int] = set()
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError):
        return skip

    # 多行字符串：中段和末行必然整行是文字
    for t in toks:
        if t.type == tokenize.STRING and t.end[0] > t.start[0]:
            skip.update(range(t.start[0] + 1, t.end[0] + 1))

    # 只看这一行的 token 组成：全是字符串/注释/空白标记 = 文字行
    per_line: dict[int, list[int]] = {}
    for t in toks:
        per_line.setdefault(t.start[0], []).append(t.type)
    allowed = {tokenize.STRING, tokenize.COMMENT, tokenize.NL,
               tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT,
               tokenize.ENCODING, tokenize.ENDMARKER}
    for ln, types_ in per_line.items():
        if all(ty in allowed for ty in types_):
            skip.add(ln)
    return skip


def count(text: str) -> int:
    skip = _text_lines(text)
    return sum(1 for i, ln in enumerate(text.splitlines(), 1)
               if i not in skip and VENDOR.search(ln))


def scan() -> dict:
    return {rel: count((ROOT / rel).read_text(encoding="utf-8"))
            for rel in CORE if (ROOT / rel).exists()}


_SELFTEST = '''"""说明文字里的 `if channel == "volc"` 不算（多行字符串中段）。

第二行也提到 `doubao-seedance-2-5-260628`，同样不算。
"""
import os


def a(x):
    # 注释里的 if ch == "minimax" 不算
    if channel == "volc":
        return 1
    if ch != "minimax":
        return 2
    return 3


def b():
    return _min_for("minimax", "MiniMax-H3")


LIMITS = {"volc": 1, "minimax": 2}
OK = channel in ("volc", "minimax")
'''
#: 真代码行：`channel == "volc"` / `ch != "minimax"` /
#: `_min_for("minimax", "MiniMax-H3")` / `LIMITS = {...}` / `OK = channel in (...)`
_WANT = 5


def selftest() -> int:
    """已知坏样本：5 行真耦合 + 三类假阳性（docstring 首行/中段/注释）。

    期望 = 5。抓少了 = 尺子瞎（第一版就是这样漏掉 `!=`/参数/字典键/成员判断）；
    抓多了 = 又在数说明文字。
    """
    got = count(_SELFTEST)
    print(f"自检①厂商耦合：真耦合 {got} 处（期望 {_WANT}）")
    print("     3 行是等号/不等号/函数入参，1 行字典键，1 行成员判断；docstring 与注释不许算进来")
    ok1 = got == _WANT
    print("✅ 尺子①能分开「代码」和「说明文字」，五种写法都数得到" if ok1
          else "❌ 尺子①失灵 —— 不许拿它的结果下结论")

    # 尺子②：共用层里的某家句式
    global COMMON_FILES
    tmp = Path(tempfile.mkdtemp())
    old_common = COMMON_FILES
    try:
        f = tmp / "bad_common.py"
        f.write_text(
            '"""说明文字里的【编辑目标】不算。"""\n'
            "X = 1  # 注释里的 <Subject N> 也不算\n"
            'PROMPT = "保留原视频动作、位置、互动、镜头和背景。"\n'
            'SEC = "【时间线继承】\\n{y}"\n',
            encoding="utf-8")
        COMMON_FILES = (str(f),)
        hit = phrase_scan()
        n_hit = len(hit.get(str(f), []))
        # 期望 2 行：一行 2.0 原句、一行 2.5 小节标题；docstring/注释各 0
        ok2 = n_hit == 2
        print(f"自检②某家句式：坏样本命中 {n_hit} 行（期望 2）")
        print("✅ 尺子②认得出「某家的句子躺在共用层」" if ok2
              else "❌ 尺子②失灵")
    finally:
        COMMON_FILES = old_common
        shutil.rmtree(tmp, ignore_errors=True)

    # 尺子③：某家的**标识符**（第四道门）
    _IDENTS = '''"""说明文字里的 edit_task 不算。"""
# 注释里的 _sd25_ 也不算
if edit_task:
    pass
_l = _sd20_orig_feat(p, 0)
_h = h3_orig_locator(p, pool)
_m = _minimax_ready()
_ok = channel == "auto"
'''
    hit3 = scan_idents(_IDENTS)
    ok3 = len(hit3) == 4
    print(f"自检③某家标识符：坏样本命中 {len(hit3)} 行（期望 4）")
    print("     4 行真标识（开关/某代函数/某家函数/某家开关）；"
          "docstring/注释/`channel == \"auto\"` 都不许算")
    print("✅ 尺子③认得出「某家的函数/开关住在共用层」" if ok3
          else "❌ 尺子③失灵")

    # 尺子④：资料引注（第五道门）
    # 坏样本：裸 guide / 不存在的家名；好样本：MANIFEST 里真有的缩写；
    # 干扰项：`str(e)[:400]`、`ratio:1.5`、`http://x:8080` 都不是引注。
    _CITES = (
        "# 官方 guide:95 说要用 2–3 个静态特征\n"      # ← 裸的，必须抓
        "# 官方 sd99-guide:12 也是这么写的\n"          # ← 不存在的家，必须抓
        "# 官方 sd20-guide:95 说的\n"                  # ← 合法
        "# 官方 sd25-guide:88 说的\n"                  # ← 合法
        "s = str(e)[:400]  # 截断，不是引注\n"
        "r = ratio:1.5 if x else 0\n"
        "u = 'http://host:8080/x'\n"
    )
    vocab, _c, _e = load_manifests()
    got4 = [n for _i, n in scan_cites(_CITES) if n not in vocab]
    ok4 = got4 == ["guide", "sd99-guide"]
    print(f"自检④资料引注：不合法 {got4}（期望 ['guide', 'sd99-guide']）")
    print("     两个坏样本必须抓；`[:400]` / `ratio:1.5` / `http://host:8080` 不算引注")
    print("✅ 尺子④认得出「引注没有主/指向不存在的家」" if ok4
          else "❌ 尺子④失灵（抓多了 = 在数代码；抓少了 = 裸 guide 会溜过去）")

    # 尺子⑤：资料路径必须住在 official/ 里
    _PATHS = (
        'A = "D:/tmp/seedance-20-guide.md"\n'          # ← 散在外面，必须抓
        "B = 'D:/tmp/official/sd20/guide.md'\n"        # ← 归位了，不许抓
        "C = D:/tmp/p4check\n"                          # ← 临时目录没有资料扩展名，不算
        "D = '/d/tmp/nomi.md'\n"                        # ← 又一个散的，必须抓
    )
    tmpf = Path(tempfile.mkdtemp())
    old_root = ROOT
    try:
        (tmpf / "app").mkdir()
        (tmpf / "scripts").mkdir()
        (tmpf / "app" / "x.py").write_text(_PATHS, encoding="utf-8")
        globals()["ROOT"] = tmpf
        got5 = sum(len(v) for v in path_scan().values())
    finally:
        globals()["ROOT"] = old_root
        shutil.rmtree(tmpf, ignore_errors=True)
    ok5 = got5 == 2
    print(f"自检⑤资料路径：散在外面的抓到 {got5} 处（期望 2）")
    print("     official/ 里的、以及不带资料扩展名的临时目录都不许算")
    print("✅ 尺子⑤认得出「资料被放在 official/ 外面」" if ok5 else "❌ 尺子⑤失灵")

    # 尺子⑥：一份文档覆盖两代 → 每家一份，必须逐字节相同
    tmp6 = Path(tempfile.mkdtemp())
    old_off = globals()["OFFICIAL"]
    try:
        for fam, body in (("sd20", "same\n"), ("sd25", "same\n")):
            d = tmp6 / fam
            d.mkdir()
            (d / "api.md").write_text(body, encoding="utf-8")
            (d / "MANIFEST.json").write_text(json.dumps({
                "family": fam,
                "files": [{"path": "api.md", "abbr": ["volc-api"], "lines": 1,
                           "sha256": hashlib.sha256(body.encode()).hexdigest(),
                           "shared_with": ["sd20", "sd25"]}]}), encoding="utf-8")
        globals()["OFFICIAL"] = tmp6
        v_ok, _c, e_ok = load_manifests(tmp6)
        # 坏样本：内容不同了
        (tmp6 / "sd25" / "api.md").write_text("different\n", encoding="utf-8")
        v_bad, _c2, e_bad = load_manifests(tmp6)
    finally:
        globals()["OFFICIAL"] = old_off
        shutil.rmtree(tmp6, ignore_errors=True)
    ok6 = (v_ok.get("volc-api") == "shared" and not e_ok) and bool(e_bad)
    print(f"自检⑥两代共用：同内容放行={v_ok.get('volc-api')!r}，"
          f"改坏一边报错={bool(e_bad)}（期望 shared / True）")
    print("     两家各一份不算混；**内容一旦不同立刻红**，这才是「两份真相」的判据")
    print("✅ 尺子⑥认得出「两家副本内容不一致」" if ok6 else "❌ 尺子⑥失灵")

    if ok1 and ok2 and ok3 and ok4 and ok5 and ok6:
        return 0
    print("❌ 有一把尺子失灵 —— 不许拿它的结果下结论")
    return 1


#: 各家编译器的**跨家引用**（2026-10-28 加）。
#:
#: 🩸 为什么单独立一条：上面那把尺子只认**厂商字面量**（`"volc"` /
#:   `doubao-seedance*` / `MiniMax-H*`）。而「2.0 的编译器 import 2.5 的编译器」
#:   这种串味**一个厂商字面量都没有** —— 函数名 `_volc_25` 不带引号、不在正则里，
#:   于是它一直躺在门的盲区里，绿得好好的。
#:
#: 真事：`volc20_compile._volc()` 里曾有一段「型号是 2.5 就转调
#:   `volc25_compile._volc_25()`」的兜底。后果不是报错，是**藏住错误路由** ——
#:   2.5 的型号被送进 2.0 的编译器时悄悄跑 2.5 的代码、产出还是对的，
#:   我改 2.0 的代码实际执行的是 2.5 的，看不出任何异常。已改成抛错。
#:
#: 判据只拦**编译器之间**的互相引用（那才是一家认另一家的提示词结构）。
#: 适配器层共用**同一厂商的平台常量**（`volc25.py` 从 `volc20.py` 取分辨率档位 /
#: 素材限制）不拦：那是火山接口的约定，不是某一代的提示词口径。
MODELS_DIR = ROOT / "app" / "services" / "models"

#: `models/` 下的共用件：两家都可以读它们，它们自己**不许**读任何一家。
SHARED_STEMS = {"__init__", "base", "volc_common", "h3_common"}


def _model_imports(text: str) -> list[tuple[int, str]]:
    """这个文件 import 了哪些 `models.*` 子模块 → [(行号, 子模块名)]。

    用 `ast` 而不是正则：注释和 docstring 里提到别家不算，
    但**真 import** 一定抓得到（正则版本会被 `# 以前这里转调 volc25_compile` 这种说明骗到）。
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "app.services.models":
                out += [(node.lineno, a.name) for a in node.names]
            elif mod.startswith("app.services.models."):
                out.append((node.lineno, mod.split(".")[3]))
            elif node.level == 1 and mod:              # from .volc20 import …
                out.append((node.lineno, mod.split(".")[0]))
            elif node.level == 1 and not mod:          # from . import volc25_compile
                out += [(node.lineno, a.name) for a in node.names]
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("app.services.models."):
                    out.append((node.lineno, a.name.split(".")[3]))
    return out


def cross_scan() -> dict[str, list[str]]:
    """各家模块之间不许互相 import。返回 {文件: [命中]}，空 = 干净。

    🩸 2026-10-28：口径**从「三家编译器之间」扩到「各家所有模块之间」**。
       最初只拦编译器，是因为当时只发现了 `volc20_compile → volc25_compile` 那一处。
       实际 `volc25.py` 一直在从 `volc20.py` 取平台常量（素材门槛 / 清晰度档位 /
       提交函数）—— 同样是「2.5 认识 2.0」，只是名字不带厂商字面量，没人提。
       现在平台共用件一律放 `volc_common.py`，两家**平级**去取。
       家名从文件名自动推（`volc20` / `volc20_compile` 同属一家），
       所以加第 4 家**不用改这个函数**。
    """
    if not MODELS_DIR.exists():
        return {}
    fams: dict[str, list[Path]] = {}
    for p in sorted(MODELS_DIR.glob("*.py")):
        stem = p.stem
        if stem in SHARED_STEMS:
            continue
        fams.setdefault(stem.removesuffix("_compile"), []).append(p)
    bad: dict[str, list[str]] = {}
    for fam, paths in fams.items():
        others = tuple(q.stem for f2, ps in fams.items() if f2 != fam
                       for q in ps)
        for p in paths:
            hits = [f"{ln}: import {name}"
                    for ln, name in _model_imports(p.read_text(encoding="utf-8"))
                    if name in others]
            if hits:
                key = str(p.relative_to(ROOT)).replace("\\", "/")
                bad[key] = hits
    return bad


#: 共用层 = 两家以上都会读的文件。这些文件里**不许出现任何一家的提示词句式**。
COMMON_FILES = (
    "app/services/edit_spec.py",
    "app/services/video_edit.py",
    "app/services/clone_pipeline.py",
    "app/services/extend.py",
    "app/services/clone_jobs.py",
    "app/services/clone_store.py",
)

#: 各家**提示词句式**的特征词（官方原句 / 官方小节标题 / 官方标号语法）。
#:
#: 🩸 2026-10-28 加这条的原因：前两道门都只能抓"看得见的耦合"——
#:   ① 厂商字面量正则：抓 `startswith("doubao-seedance-2-0")`
#:   ② 跨家 import：抓 `from .volc25_compile import …`
#:   但它们都抓不到**一句 2.0 的官方原句躺在共用层**：`保留原视频动作、位置、互动…`
#:   一个厂商名都没有，却是 2.0 的写法；2.5 读到的就是串味。
#:   这类东西我已经放过三次（「保留原视频」/「按新配音重做口型」/ 2.0 单点编辑三种原句），
#:   三次都是靠人工读产出才发现。**能被人工发现四次，就该变成判据。**
FAMILY_PHRASES = (
    # 火山 2.0
    "严格编辑", "保留原视频", "保持无字幕", "不要生成水印", "不要生成 Logo",
    # 火山 2.5（五段模板的小节标题）
    "【编辑目标】", "【原视频职责】", "【目标素材职责】", "【编辑对象与范围】",
    "【时间线继承】", "【保持内容】", "【未采用素材】",
    "按新的说话内容重新生成",
    # MiniMax H3
    "<Subject", "<Picture", "Write all six rewrite sections",
)


def _string_literals(text: str) -> list[tuple[int, str]]:
    """文件里所有**非 docstring 的字符串常量** → [(行号, 内容)]。

    🩸 为什么不用"整行文本"来查：行尾注释会被算进来。
       `X = 1  # 说明里提到 <Subject N>` 这种行，代码本身一个句式都没有，
       但按行文本查会报红 —— 尺子第一步自证就撞到了（期望 2 命中 3）。
       ⇒ 只看**真的会拼进提示词的字符串常量**（含 f-string 的中间段）。
       docstring 用 `_text_lines` 排掉（它是说明，不是产出）。
    """
    skip = _text_lines(text)
    str_types = {tokenize.STRING}
    # Python 3.12 起 f-string 被拆成 FSTRING_START/MIDDLE/END，文字在 MIDDLE 里
    if hasattr(tokenize, "FSTRING_MIDDLE"):
        str_types.add(tokenize.FSTRING_MIDDLE)
    out: list[tuple[int, str]] = []
    try:
        for t in tokenize.generate_tokens(io.StringIO(text).readline):
            if t.type in str_types and t.start[0] not in skip:
                out.append((t.start[0], t.string))
    except tokenize.TokenError:
        return out
    return out


def phrase_scan() -> dict[str, list[str]]:
    """共用层的**字符串常量**里有没有某家的提示词句式。空 = 干净。"""
    bad: dict[str, list[str]] = {}
    for rel in COMMON_FILES:
        p = ROOT / rel
        if not p.exists():
            continue
        hits = []
        for ln, s in _string_literals(p.read_text(encoding="utf-8")):
            for ph in FAMILY_PHRASES:
                if ph in s:
                    hits.append(f"{ln}: {ph} ← {s.strip()[:50]}")
                    break
        if hits:
            bad[rel] = hits
    return bad


#: 共用层不许出现的**某家标识符**（2026-10-28 加，第四道门）。
#:
#: 🩸 前三道门都看不见这一类：
#:   ① 厂商字面量正则只认 `"volc"` 这种**带引号**的字符串；
#:   ② 跨家 import 只认 `from .volc25_compile import …`；
#:   ③ 句式扫描只认会拼进提示词的**字符串常量**。
#: 而「2.0 的认人尺 `sd20_locator` 躺在共用层、三家一起读」一个引号都没有，
#: 三道门全是绿的。真事：`_clauses` 里 13 处 `if edit_task:` ——
#: `edit_task` 名叫"任务类型"，实际 2.0 永远 False、2.5 永远 True（`model_specs`
#: 写死），**是型号开关伪装成任务开关**；改 2.5 的句式，2.0 的产出跟着变。
#:
#: 口径 = 代码行里出现下列标识任一个：
#:   · `edit_task`（当年的伪装开关）
#:   · `_sd20_*` / `_sd25_*`（某一代的专属函数）
#:   · `h3_*` / `_minimax*`（某一家的专属函数）
#: ⚠️ `channel == "auto"` 不算：那是**用户选项**，不是厂商名。
FAMILY_IDENTS = re.compile(
    r"\bedit_task\b(?!s)"
    r"|\b_sd2[05][\w]*"
    r"|\bh3_\w+"
    r"|\b_minimax\w*"
)


def scan_idents(text: str) -> list[str]:
    """一段代码里命中「某家标识符」的行。`_text_lines` 排掉注释与 docstring。"""
    skip = _text_lines(text)
    return [f"{i}: {ln.strip()[:70]}"
            for i, ln in enumerate(text.splitlines(), 1)
            if i not in skip and FAMILY_IDENTS.search(ln)]


def branch_scan() -> dict[str, list[str]]:
    """共用层代码行里的「某家标识符」。空 = 干净。"""
    bad: dict[str, list[str]] = {}
    for rel in COMMON_FILES:
        p = ROOT / rel
        if not p.exists():
            continue
        hits = scan_idents(p.read_text(encoding="utf-8"))
        if hits:
            bad[rel] = hits
    return bad


# ===========================================================================
# 第五道门：**资料引用**（2026-10-28 加）
# ---------------------------------------------------------------------------
# 主人原话：「确实资料也要做好分离，不然查资料又混回去了」。
#
# 前四道门管「代码里有没有某家的东西」；这一道管**引注**：注释里的
# `xxx:123` 是给下一个读者（模型或人）照着翻原文用的。同一个缩写若指向
# 两份不同的官方文档，翻到的就是**别家的标准**，而且不会当场报错。
#
# 🩸 这不是设想。改名前实测：裸的 guide 缩写带行号在工程里 190 处 ——
#   2.0 的 117 处、2.5 的 47 处、共用层 26 处。共用层里 `vision_plan.py` 的
#   那条指 2.5 的动词表，`video_edit.py` 的那条指 2.0 的实战案例。
#   同一个词、同一类文件、两份文档；翻错了也看不出（2.0 指南第 88 行是
#   「## 1 定义主体」，看着挺正常）。
#
# 判据**不自带词表** —— 词表只从 `D:/tmp/official/<家>/MANIFEST.json` 读。
# 门和资料各维护一份清单，迟早各说各话。

OFFICIAL = Path("D:/tmp/official")

#: 像「文档名:行号」的前缀，必须含这些词之一才算引注。
#: 不含的话 `ratio:1.5`、`str(e)[:400]` 会被误判 —— 那是代码不是出处。
DOCISH_PARTS = {"guide", "pe", "ref", "skill", "manual", "doc", "docs",
                "official", "h3", "sd2", "sd20", "sd25", "base", "en", "cn"}
CITE = re.compile(r"(?<![-A-Za-z0-9_])([a-z][a-z0-9]*(?:-[a-z0-9]+)*):(\d{1,4})(?![\d.])")


def load_manifests(root: Path | None = None) -> tuple[dict, list, list]:
    """读三家的 MANIFEST → (词表{缩写: 家}, 正本清单[(家, 路径, sha, 行数)], 错误)。

    🩸 2026-10-28：官方文档**一份覆盖两代**是常态（`volc-api` 同时写 2.0 和 2.5 的
    参数规则）。处置不是搞「共享目录」（那是把两家又合一起、迟早变大杂烩），
    而是**每家目录各存一份完整原文**，靠这条判据锁死：
        两份必须逐字节相同，且两家都要声明 `shared_with` 覆盖彼此。
    这样「同一个词指两份**内容相同**的文档」= 不歧义；
    而以前那个病是「`guide` 一个词指两份**内容不同**的文档」= 真歧义。
    """
    root = root or OFFICIAL
    owners: dict[str, list[tuple[str, str, tuple]]] = {}
    canon: list[tuple[str, Path, str, int]] = []
    errs: list[str] = []
    if not root.exists():
        return {}, canon, [f"官方资料目录不存在：{root}"]
    for man_path in sorted(root.glob("*/MANIFEST.json")):
        try:
            man = json.loads(man_path.read_text(encoding="utf-8"))
        except Exception as e:
            errs.append(f"{man_path} 读不了：{e}")
            continue
        fam = man.get("family") or man_path.parent.name
        for it in man.get("files") or []:
            p = man_path.parent / str(it.get("path") or "")
            sha = str(it.get("sha256") or "")
            shared = tuple(sorted(it.get("shared_with") or ()))
            for ab in it.get("abbr") or []:
                owners.setdefault(ab, []).append((fam, sha, shared, p))
            canon.append((fam, p, sha, int(it.get("lines") or 0)))

    vocab: dict[str, str] = {}
    for ab, ow in owners.items():
        fams = {f for f, *_ in ow}
        if len(fams) == 1:
            vocab[ab] = next(iter(fams))
            continue
        shas = {s for _f, s, _w, _p in ow}
        shares = {w for _f, _s, w, _p in ow}
        # 不信清单里写的 sha —— **直接比磁盘上的文件**。
        # 现实里最常发生的是「改了文件、忘了同步另一边」，清单上的 sha 还是对的。
        disk = set()
        for _f, _s, _w, p in ow:
            try:
                disk.add(hashlib.sha256(p.read_bytes()).hexdigest())
            except OSError:
                disk.add("<读不到>")
        if len(shas) != 1 or len(disk) != 1:
            errs.append(f"缩写 `{ab}` 属于多家且内容不同 —— 这就是 `guide` 那个病："
                        f"{sorted(fams)}（清单 sha {len(shas)} 种 / 磁盘 {len(disk)} 种）")
        elif len(shares) != 1 or set(next(iter(shares))) != fams:
            errs.append(f"缩写 `{ab}` 跨 {sorted(fams)}，但 `shared_with` 没互相声明")
        else:
            vocab[ab] = "shared"
    return vocab, canon, errs


def scan_cites(text: str) -> list[tuple[int, str]]:
    """这文件里所有「文档名:行号」引注 → [(行号, 文档名)]。注释/正文都算。"""
    out = []
    for i, ln in enumerate(text.splitlines(), 1):
        for m in CITE.finditer(ln):
            name = m.group(1)
            if set(name.split("-")) & DOCISH_PARTS:
                out.append((i, name))
    return out


def docs_scan() -> dict[str, list[str]]:
    """引注用的缩写必须能在 MANIFEST 里找到主。裸 `guide:` 这里就会被抓。"""
    vocab, _canon, errs = load_manifests()
    bad: dict[str, list[str]] = {}
    files = sorted((ROOT / "app").rglob("*.py")) + sorted((ROOT / "scripts").glob("*.py"))
    for p in files:
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        # 尺子自己的自检样本里**必须**有裸缩写，否则测不出它抓不抓得住。
        # 这个文件豁免；它的引注不服务于「查资料」。
        if rel == "scripts/model_separation_check.py":
            continue
        hits = [f"{i}: `{n}:` 不在任何一家的 MANIFEST 里"
                for i, n in scan_cites(p.read_text(encoding="utf-8", errors="replace"))
                if n not in vocab]
        if hits:
            bad[rel] = hits
    for e in errs:
        bad.setdefault("<MANIFEST>", []).append(e)
    return bad


#: 生产代码里出现的「本机资料路径」。除了 official/ 里的，一律算没归位。
LOCAL_DOC = re.compile(r"""["'`]?(?:D:/tmp|/d/tmp)/([A-Za-z0-9_./\-]+\.(?:md|txt|json))""")


def path_scan() -> dict[str, list[str]]:
    """资料必须住在 `official/<家>/`。散在别处 = 以后一定会有人翻到旧的那份。

    🩸 为什么这条比"登记缩写"更狠：缩写靠人写对，路径靠人放对。
    只查代码（`app/` + `scripts/`），`docs/` 是历史记录不算。
    """
    bad: dict[str, list[str]] = {}
    files = sorted((ROOT / "app").rglob("*.py")) + sorted((ROOT / "scripts").glob("*.py"))
    for p in files:
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        # 同尺子④：自检样本里必须写散落的路径才测得出，本文件豁免。
        if rel == "scripts/model_separation_check.py":
            continue
        hits = []
        for i, ln in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for m in LOCAL_DOC.finditer(ln):
                if m.group(1).startswith("official/"):
                    continue
                hits.append(f"{i}: {m.group(0).strip(chr(34)+chr(39)+chr(96))}")
        if hits:
            bad[rel] = hits
    return bad


def manifest_scan() -> list[str]:
    """MANIFEST 说的和磁盘上的必须一致 —— 资料被换了没人知道，比没写更糟。"""
    _vocab, canon, errs = load_manifests()
    bad = list(errs)
    for fam, p, sha, lines in canon:
        if not p.exists():
            bad.append(f"[{fam}] 清单里的文件不存在：{p}")
            continue
        got = hashlib.sha256(p.read_bytes()).hexdigest()
        if sha and got != sha:
            bad.append(f"[{fam}] {p.name} 内容变过（sha256 不符）—— 改过就更新 MANIFEST")
        n = len(p.read_text(encoding="utf-8", errors="replace").splitlines())
        if lines and n != lines:
            bad.append(f"[{fam}] {p.name} 行数 {lines} → {n}，引注行号会整体漂移")
    return bad


#: 会藏「第二份官方资料」的目录（发现副本 = 迟早改一处忘一处）
DUP_ROOTS = ["D:/tmp", "D:/tmp/.agents", "D:/tmp/.claude", "D:/tmp/h3o"]

#: 上游仓库的克隆**不算**我们的副本 —— 那是出处本身，动了等于改人家的东西。
VENDOR_DIRS = (Path("D:/tmp/h3o/repo"),)


def dup_scan() -> list[str]:
    """official/ 之外不许有和正本逐字节相同的文件。"""
    _vocab, canon, _errs = load_manifests()
    by_size: dict[int, list[tuple[Path, str]]] = {}
    for _fam, p, sha, _n in canon:
        if p.exists() and sha:
            by_size.setdefault(p.stat().st_size, []).append((p, sha))
    hits = []
    for root in DUP_ROOTS:
        r = Path(root)
        if not r.is_dir():
            continue
        it = r.rglob("*") if r.name != "tmp" else r.glob("*")
        for p in it:
            try:
                if not p.is_file() or p.suffix.lower() not in (".md", ".txt", ".json"):
                    continue
                if OFFICIAL in p.parents:
                    continue
                if any(v in p.parents or v == p.parent for v in VENDOR_DIRS):
                    continue
                cand = by_size.get(p.stat().st_size)
                if not cand:
                    continue
                h = hashlib.sha256(p.read_bytes()).hexdigest()
            except OSError:
                continue
            for cp, sha in cand:
                if h == sha:
                    hits.append(f"{p}  与正本 {cp} 逐字节相同 → 该挪走/删掉（会有第二份真相）")
    return hits


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()

    cur = scan()
    if "--update" in sys.argv:
        BASELINE.write_text(json.dumps(cur, ensure_ascii=False, indent=1),
                            encoding="utf-8")
        print(f"基线已更新：{BASELINE}")
        for k, v in cur.items():
            print(f"  {k:<34} {v:>3}")
        print(f"\n合计 {sum(cur.values())} 处")
        return 0

    if not BASELINE.exists():
        raise SystemExit(f"没有基线：{BASELINE}（先跑 --update 记录当前数）")
    old = json.loads(BASELINE.read_text(encoding="utf-8"))

    worse = []
    total_old = total_new = 0
    for rel, n in cur.items():
        o = int(old.get(rel) or 0)
        total_old += o
        total_new += n
        flag = "  ← 变多了！" if n > o else ""
        print(f"{rel:<36} {o:>3} → {n:<3}{flag}")
        if n > o:
            worse.append(rel)

    print(f"\n核心厂商耦合合计：{total_old} → {total_new}")

    # 🩸 跨家引用（厂商字面量那个正则看不见的那一半）
    cross = cross_scan()
    if cross:
        print("\n❌ 各家编译器之间互相引用 —— 一家认了另一家的提示词结构：")
        for rel, hits in cross.items():
            for h in hits:
                print(f"   · {rel}  {h}")
        print("   每家只能依赖 `edit_spec` 的共用工具，不许 import 别家的编译器。")
        return 1
    print("✅ 各家的模块之间零互相引用（平台共用件走 `volc_common`）")

    # 🩸 共用层里不许躺着某家的提示词句式
    phrases = phrase_scan()
    if phrases:
        print("\n❌ 共用层里出现了某家的提示词句式 —— 别家读到的就是串味：")
        for rel, hits in phrases.items():
            for h in hits:
                print(f"   · {rel}  {h}")
        print("   把它搬进 `app/services/models/<家>_compile.py`，"
              "共用层只留不分家的通用句。")
        return 1
    print("✅ 共用层里没有某家的提示词句式")

    # 🩸 第四道门：某家的**标识符**（函数名/开关名）住在共用层。
    # 前三道门只认字符串和 import，认不出这种「没引号的耦合」。
    branches = branch_scan()
    if branches:
        print("\n❌ 共用层里出现了某家的标识符 —— 改那一家会带动别家的产出：")
        for rel, hits in branches.items():
            for h in hits[:6]:
                print(f"   · {rel}  {h}")
        print("   搬进那一家自己的模块；跨家差异走 `models/base.Dialect` 注入。")
        return 1
    print("✅ 共用层里没有某家的标识符（跨家差异全走 Dialect 注入）")

    # 🩸 第五道门：资料引用。四项都要过，缺一项就是真红了（不是棘轮）。
    man_bad = manifest_scan()
    if man_bad:
        print("\n❌ 官方资料清单和磁盘对不上 —— 引注会指向不存在/已变的地方：")
        for h in man_bad:
            print(f"   · {h}")
        return 1
    print("✅ 三家 MANIFEST 与磁盘逐份一致（sha256 + 行数）")

    cite_bad = docs_scan()
    if cite_bad:
        print("\n❌ 有引注落不到任何一家的清单上（裸 `guide:` 就在这里现形）：")
        for rel, hits in cite_bad.items():
            for h in hits[:6]:
                print(f"   · {rel}  {h}")
        print("   写成 `sd20-guide:123` / `sd25-guide:123` / `sd2-pe:123` …；"
              "缩写只能在 MANIFEST 里出现。")
        return 1
    _vocab, _canon, _ = load_manifests()
    print(f"✅ 每处引注都落在某家的清单上（词表 {len(_vocab)} 个，全部来自 MANIFEST）")

    stray = path_scan()
    if stray:
        print("\n❌ 生产代码还在引用 official/ 之外的本机资料文件：")
        for rel, hits in stray.items():
            for h in hits[:6]:
                print(f"   · {rel}  {h}")
        print("   把它们放进 `D:/tmp/official/<家>/` 并在那家 MANIFEST 登记。")
        return 1
    print("✅ 生产代码只引用 official/ 里的资料")

    dups = dup_scan()
    if dups:
        print("\n❌ official/ 之外还有官方资料的正本副本：")
        for h in dups[:10]:
            print(f"   · {h}")
        print("   两份真相 = 改一份忘一份；查资料时挑到旧的那份也不报错。")
        return 1
    print("✅ official/ 之外没有第二份官方资料")

    if worse:
        print("❌ 核心文件里新增了厂商耦合 —— 加一家的成本又变贵了：")
        for rel in worse:
            print(f"   · {rel}")
        print("   请把这段放进 `app/services/models/<家>/`，核心只调适配器。")
        return 1
    if total_new:
        print(f"✅ 没有新增耦合（还剩 {total_new} 处搬迁欠账）")
    else:
        print("✅ 核心代码一处厂商耦合都没有")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
