# 三模型分离（2026-10-26）

> 主人口径：火山 Seedance 2.0 / 火山 Seedance 2.5 / MiniMax H3 **三家平级**，
> 一轮只跑一家；任何验收入口必须点名型号，不点名就拒绝运行。
> 本文记录「分离到什么程度、怎么验的、还剩什么」。

## 一、分到哪一层

主人在 2026-10-26 拍板：**只拆入口**（`edit_spec.py` 仍是一个编译器，三家分区明确）。

| 层 | 处理 |
|---|---|
| 执行锁 | `.model-lock.json`（`scripts/_model_lock.py`）：型号锁 + `guard()` |
| 入口闸 | `scripts/_model_gate.py`：所有验收脚本 `main()` 第一行 `sel_or_exit()`，无 `--model` → exit 2；与锁不符 → exit 3（`--force` 放行并留痕）；只验一家的脚本用 `only="h3"`，点错型号 → exit 2；`--model X` 由闸门吃掉，不会再落到下游 argparse |
| 提示词用例 | 一个型号一个文件：`snap_cases_sd20.py` / `snap_cases_sd25.py` / `snap_cases_h3.py`（共用常量 `snap_cases_common.py`） |
| 编译器自检 | `test_edit_spec_common.py` + `test_edit_spec_sd20.py` / `_sd25.py` / `_h3.py`，入口 `test_edit_spec.py --model X` |
| 功能验收 | `p9`–`p15` 内的断言按型号条件化：选 A 只跑 A 那一半，成对探针的另一半在 B 的轮次里跑 |
| 共享层 | `model_specs.py`（三家参数表）、`test_model_specs.py` / `test_whole_wiring.py` / `test_video_edit_logic.py` 验的是**共享参数表与出片流水线**，断言本身不分模型；点名只作执行闸 |

## 二、动手改了哪些文件

| 文件 | 改法 |
|---|---|
| `scripts/prompt_snapshot.py` | `--model` 必填；CASES 从 1 个混装列表拆成 3 个型号文件 |
| `scripts/test_edit_spec.py` | 918 行 226 项拆成 4 个文件；入口 `--model` 必填 |
| `scripts/prompt_lint_check.py` | `--model` 必填；只扫点名型号的矩阵 + 该型号专项用例 |
| `scripts/prompt_model_standards_check.py` | `--model` 必填；`phase_positions` / `phase_scene_and_defs` 按型号分流 |
| `scripts/p9`–`p15_check.py` | 加闸；内部断言按型号条件化（2.0 / 2.5 / H3 / 共享） |
| `scripts/test_person_refs.py` | 加闸；2.0 派生段 / 2.5 段 / H3 段分开 |
| `scripts/test_model_specs.py`、`test_whole_wiring.py`、`test_video_edit_logic.py` | 加闸（共享层） |
| `scripts/audit_official.py`、`identifiability_check.py`、`work_p1_check.py`、`test_ark_edit_body.py`、`test_vision_plan.py` | 加闸 |
| 新增 | `scripts/_model_gate.py`、`scripts/snap_cases_common.py`、`scripts/snap_cases_sd20.py`、`snap_cases_sd25.py`、`snap_cases_h3.py`、`test_edit_spec_common.py`、`test_edit_spec_sd20.py`、`test_edit_spec_sd25.py`、`test_edit_spec_h3.py` |

**第二批**（同日补的）：剩下 **33 个** `test_*` / `*_check.py` 全部加闸 ——
`c6_check` `p16_check` `p17_check` `p4`–`p7_check` `test_ark_ingest` `test_audio_modes`
`test_auto_render` `test_clone_api` `test_contact_sheet` `test_gen_cache`
`test_h3_shot_source`(only=h3) `test_multi_version` `test_oss_sign` `test_pipeline`
`test_plan_preview` `test_pronounce` `test_providers_real` `test_qc` `test_refine_cuts`
`test_render` `test_retry` `test_separate` `test_shot_detect` `test_source_dedupe`
`test_speech_est` `test_subject_look`(only=h3) `test_task_resume` `test_triage`
`test_voice_catalog` `test_voice_clone` `work_p0_check`。备份 `D:/tmp/backup_20261026_split2/`。

## 三、判据守恒（拆分无损的证据）

| 判据 | 拆分前 | 2.0 | 2.5 | H3 |
|---|---|---|---|---|
| `prompt_snapshot` | 31 条，一次比三家 | 10/10 一致 | 13/13 一致 | 8/8 一致 |
| `test_edit_spec` | 226 项 | 130 | 81 | 98 |
| `prompt_lint_check` | 2666 | 744 | 830 | 1092 |
| `prompt_model_standards_check` | 85 | 46 | 17 | 22 |
| `test_whole_wiring` | — | 96 | 96 | 96 |
| `test_video_edit_logic` | — | 112 | 112 | 112 |
| `test_model_specs` | — | 65 | 65 | 65 |
| `p9` / `p10` / `p11` / `p12` / `p13` / `p14` / `p15` | 46 / 40 / 64 / 65 / 38 / 24 / 47 | 31 / 24 / 33 / 51 / 38 / 22 / 42 | 41 / 29 / 34 / 54 / 38 / 23 / 45 | 32 / 35 / 39 / 52 / 38 / 21 / 39 |

守恒校验：
- lint 三家相加 = **2666**（与拆分前逐字相同）
- standards 三家相加 = **85**
- edit_spec：共用 42 项三家各跑一次；专属 88 + 39 + 56 = 183 ⇒ 42 + 183 = 225，
  加上「连写句号」从 1 条跨三家拆成 2 条（+1）= **226**
- edit_spec 拆分用 `check(` 名字多重集合对比过：旧有新无 = 0（除两处**等价展开**：
  f-string 循环拆成两条、跨三家的连写句号拆成两家各一条）

## 四、用法

```bash
python scripts/_model_lock.py volc20          # 先锁到本轮型号
python scripts/test_edit_spec.py --model volc20
python scripts/prompt_snapshot.py --model volc20
python scripts/prompt_lint_check.py --model volc20
python scripts/prompt_model_standards_check.py --model volc20
```

不点名 → `⛔ 必须点名型号`，exit 2。
锁在别家时点名 → `⛔ 当前锁在 …`，exit 3（确实要跨型号才 `--force`）。

### 🩸 每轮必跑：分离门（2026-10-28 加）

```bash
python scripts/model_separation_check.py        # 不接收 --model：它比的就是"核心认不认识厂商"
```

**这条不属于任何一家，所以没有 `--model`** —— 它查的是核心 7 个文件里
有没有出现厂商字面量（`"volc"` / `"minimax"` / `doubao-seedance*` / `MiniMax-H*`）。
棘轮：只许降不许升，基线 `scripts/_model_separation_baseline.json` 现在是全 0。

🩸 **为什么必须每轮跑**：2026-10-27 调 2.0 那轮，为了做「换装逐个查」和
「保留句收口」，往共用层 `edit_spec.py` 写了两处 `startswith("doubao-seedance-2-0")`。
当轮的所有判据（`test_edit_spec` / `ruler_sd20` / `prompt_lint`）**全绿** ——
因为它们各自只看自己那家的产出，没人问"共用层认不认识型号名"。
门一直红到 2026-10-28 主人看见提示里混着三家名字才翻出来。
**本轮只跑本家的判据 ≠ 分离没破**，所以这条要跟每家的判据一起跑。


## 五、第二批的验证（三家各跑一轮，一次只跑一家）

| 批次 | 2.0 | 2.5 | H3 |
|---|---|---|---|
| 第一批 15 个（p9–p15 / specs / person_refs / wiring / edit_logic / ark_body / vision_plan / identifiability / audit） | 15/15 exit 0 | 15/15 exit 0 | 15/15 exit 0 |
| 第二批 26 个（另加 2 个 `only=h3` 的只在 H3 轮跑） | 21/26 | 21/26 | 23/28 |

第二批那 5 个红**三家完全同一组**，逐个用「加闸前的备份」跑过，**改动前就是这样**：

| 脚本 | 现象 | 归因 |
|---|---|---|
| `p4_check` / `p6_check` | `data/clone/89c228cc…/task.json` 不存在 | **夹具目录已不在本机**（不是加闸弄的；备份版同样红） |
| `test_ark_ingest` | 31/35，`seg2.mp4 … InputVideoSensitiveContentDetected` | 既有失败，与型号无关 |
| `test_gen_cache` | `fake_edit() got an unexpected keyword argument 'ref_videos'` | 测试的假实现落后于实现（测试没跟上，不是产品 bug） |
| `test_clone_api` | `the following arguments are required: sample` | 需要传样片参数，跑批没给 |

未跑（会碰真实接口/需要素材）：`test_pipeline`、`test_render`（要源视频）、
`test_providers_real`（**真调 ASR/TTS，花钱**）。

## 六、没做的

- **`edit_spec.py` 保留为共用工具层**（主人口径：只拆入口）。
  🩸 2026-10-28 更正：这段以前写「三家编译逻辑仍在一个编译器里，2.0 = `_volc`、
  2.5 = `_volc_25`、H3 = `_minimax`」—— **已经过时**，那三个函数早就搬到各家自己的模块
  （`volc20_compile._volc` / `volc25_compile._volc_25` / `h3_compile._minimax`），
  `edit_spec.py` 里现在 **0 个**这样的定义，只剩注释。它就剩共用工具
  （`_clauses` / `_keep_sentence` / `_duty_role` / `_person_attr` 这类）。
  仍留在共用层的只有「三家都要用的拼装件」，不是某一家的话语。
- **没有拆共享层脚本**（`model_specs` / 出片流水线 / 视频剪辑逻辑）：
  这些断言验的就是「三家参数表 + 一条流水线」，拆开会让成对对比失去意义。
- `audit_official.py` / `work_p1_check.py` 需要真实历史数据，本轮只验证了闸门生效，未跑完整流程。

## 七、2026-10-28 回归：门红了两天没人看见（已修）

主人：「那之前让你做的分离呢？不是做得很彻底了吗？我发现现在还总在混，
而且我纠正你很多次了」。

跑 `model_separation_check.py` → **核心耦合 0 → 2**，两处都在 `edit_spec.py`：

| 位置 | 原来写的 | 现在 |
|---|---|---|
| `missing_material()` | `if slot == "wardrobe" and str(model).startswith(("doubao-seedance-2-0", "seedance-2-0"))` | `if slot == "wardrobe" and wardrobe_per_person:`（能力位，由调用方从 `adapter.caps` 取） |
| `_keep_sentence()` | `_is_sd20 = str(model).startswith(("doubao-seedance-2-0", …))` | `if point_edit:`（由**那家自己的编译器**传 `True`） |

新增 `Caps.wardrobe_check_per_person`（默认 `False`，`volc20.py` 里置 `True`）。
`edit_spec` 只认标记，不认识型号名；`_keep_sentence` 的 `model` 参数整个删掉
（它只被那一处判断用过）。

### 顺带查出的 3 条假绿断言（2.0）

`test_edit_spec_sd20.py` 里有 3 条断言锚的是**淘汰掉的旧保留句写法**
（「保持@视频1的…」）。2026-10-27 把 2.0 的保留句收口成官方「单点编辑」原句
（「保留原视频动作、位置、互动、镜头和背景。」）之后，这 3 条靠
**"编译时不传 model"** 这个非生产用法继续绿 —— 真实出片一定带 model，
所以它们**根本没在测真实产出**：

| 行 | 旧断言 | 现断言 |
|---|---|---|
| 「含保留句」 | `"保持@视频1的" in v` | `"保留原视频" in v` |
| 「保什么全关就不写保留句」 | `"保持@视频1的" not in _ko` | `"保留原视频" not in _ko` |
| 「补充说明在保留句之前」 | `ep.index("保持@视频1")` | `ep.index("保留原视频")` |
| 「没关的动作仍在保留句里」 | `"人物动作" in kp` | `"动作" in kp`（官方原句是「动作、位置、互动」） |

### 本轮判据（零模型调用）

| 门 | 结果 |
|---|---|
| `model_separation_check` | **0 → 0** ✅ ｜ `--selftest` 5/5 |
| `test_edit_spec --model volc20 --force` | 233/233 |
| `test_edit_spec --model volc25` | 159/159 |
| `test_edit_spec --model h3 --force` | 125/125 |
| `ruler_sd20 --calib --probes` | 红 0（552 条规则-示例判定） |
| `ruler_sd25 --calib --probes --sweep --current` | 红 0 · 57/57 · 破口 0 · 0 条红 |
| `ruler_h3 --calib --probes` | 红 0（46 条 · 探针 23/23） |
| `prompt_lint_check` | 2.0 744/744 · 2.5 830/830 |
| `test_whole_wiring --model volc25` | 104/104 |
| `test_separate --model volc25` | 35/35（顺带修了一条失效断言，见下） |
| `p15_check --model volc25` | 45/45 |
| `prompt_model_standards_check` | 17/17 |

`test_separate.py`「mix + 无音轨 → 仍保留『表情』」这条也是失效断言：
`KEEP_LABELS` 2026-10-26 就把「表情」撤了（2.0 官方只写「动作和运镜不变」），
`_keep_sentence` 从此不会输出「表情」二字 —— 改成断言「人物动作」。

### 结论

分离的**骨架**一直在（`models/` 一家一目录、`_model_gate` 闸门、`.model-lock.json`、
棘轮门）；破的是**有人（我）往共用层绕过去，而每轮只跑本家判据，门红了看不见**。
从本轮起 `model_separation_check.py` 与各家判据**同批跑**。

### 八、再往下一层：门还有两个盲区（2026-10-28 当天补上）

主人追问：「最主要会不会影响到你又犯傻，这才是最关键的」。
查下来答案是**会**，而且当天就查出两件：

#### 8.1 盲区一：跨家 import（厂商字面量正则看不见）

`volc20_compile._volc()` 里有一段：型号是 2.5 时**静默转调**
`volc25_compile._volc_25()`。函数名不带引号、不在 `VENDOR` 正则里 → 门一直是绿的。

真正危险的不是"跨家引用"这个形式，而是**它藏住了一次错误路由**：
2.5 的型号被送进 2.0 的编译器，悄悄跑 2.5 的代码、产出还是对的 ——
我改 2.0 的代码，实际执行的是 2.5 的，看不出任何异常。

**处置**：
1. 兜底改成**抛错**（走不到正常路径；真走到了就是路由错了，该炸出来）
2. 删掉兜底后立刻暴露了缝的**根因**：`model_specs.volc()` 用**子串**匹配
   （`"seedance-2-5" in m`，短名认），注册表用**前缀**匹配（只登记
   `doubao-seedance-2-5`）→ 短名落到"通道默认" = 2.0 的适配器。
   **两套识别口径，同一个型号在两个地方有两个家。**
   ⇒ `volc20/volc25` 的 `PREFIXES` 补齐短名（`seedance-2-0` / `seedance-2-5` / `seedance-2.5`）
3. `model_separation_check.py` 新增 **`cross_scan()`**：三家编译器之间不许互相 import。
   自证 5/5（两种真引用响、只依赖共用工具/注释/docstring 三种不响）
4. `model_registry_check.py` 新增 **R13**：同一型号的不同写法必须路由到同一家。
   自证：拿掉 `seedance-2-5` 前缀后，`adapter_for("seedance-2-5")` 果然变成
   `doubao-seedance-2-0-mini-260615` → 判据有鉴别力

#### 8.2 盲区二：我自己报事实不看代码

我在上一条汇报里写「`edit_spec.py` 里还有 `_volc` / `_volc_25` / `_minimax` 三个函数」
—— **是错的**。那是从本文件 §六 一句 2026-10-26 的**过时描述**里抄的，
没回代码核实（`grep "^def _volc"` 命中 0 个）。

这正好是主人问「会不会犯傻」的活样本：**文档会过时，代码不会**。
处置：§六 那句已改正，并写清"只剩共用工具、0 个分区编译函数"。

#### 8.3 这一层之后还剩什么（**2026-10-28 已全部堵死**）

| 当时还剩的 | 现在怎么样 |
|---|---|
| 适配器层共用同厂商平台常量（`volc25.py` 从 `volc20.py` 取分辨率档位 / 素材限制） | ✅ 搬到 `models/volc_common.py`，两家**平级**去取，谁也不 import 谁。门从"只拦编译器"扩到"各家所有模块之间"（家名从文件名自动推，加第 4 家不用改门） |
| `edit_spec` 里的共用函数被按一家改 | ✅ 不再是"靠纪律"：新增第三道门 `phrase_scan()` —— 共用 6 个文件的**字符串常量**里出现某家句式就红（tokenize 取非 docstring 常量，行尾注释不算）。自证 2/2 |
| 2.0 / 2.5 的 `_raw` 前缀靠人记得同步 | ✅ R13 改成**自动派生**（遍历 `all_adapters()` 的 `caps.raw["prefixes"]` + `model_id`）；新增 R14 对账 `model_specs`（子串口径）与注册表（前缀口径），14/14 |

## 九、`identifiability_check --model volc25` 报 9 组红 —— 查过了，不是分离问题

**结论：既有缺陷，两家同形，与本轮（分离加固）无关。**

取证方式（零费用、只读）：

| 证据 | 结果 |
|---|---|
| 同一夹具跑 2.0 分支（`--force`） | **同样 9 组红，一行不差** —— 不是 2.5 特有 |
| 本轮改过 `_clauses` 的换人分支吗 | 没有。改的是 `_lip_line`（口型）、`_keep_sentence`（保留句）、`PREFIXES`、import |
| 换人句的判定路径 | `_clauses` → `_sd20_orig_feat` / `_who_label`，2026-10-27 定死，本轮没碰 |

**根因（三条，缺一不可）**：

1. `_who_label()` 只有两档（方位唯一 → 「画面左侧的人物」；否则 `_head_noun` → 「人物」），
   **没有 `_feat_phrase` 外观档**。对「穿橙色连帽拉链外套，左胸带有白色标识，短发」
   实测 `_head_noun` 与 `_feat_phrase(cloth=False/True)` **全返回空**
   （`D:/tmp/clone_diag/feat_probe.py`）。
2. 描述空 ⇒ 2.5 编译器 `_tgt_lbl` 全是「人物」⇒ `_tgt_letters=True` ⇒ **整单退字母
   「目标人物A / B」**（`volc25_compile.py:370-374`）。
3. 闸 `require_identifiable_volc25` 只看 `_distinct(picked, "desc_zh")` ——
   描述互异就放行，不检查**编译器写不写得出来** ⇒ 闸放行 + 输出重复。

**这不是一行代码能修的**：退字母是 2026-10-26 拍过板的路线
（`PROMPT-TEST-LEDGER-SD25.md:79` 第 6 条，依据 `sd25-pe:224/227-228` 的字母形态）。
要改成"闸拦下不许出片"，是**推翻既有拍板**，得主人点头 —— 所以只记录、不动手。

## 十、2026-10-28 第三轮：把"混"从 28 处降到 0（方言注入 + 第四道门）

主人的话：「主要之前混得太多，所以我现在也无法帮你做判断了。我们现在只能真正的做到分离干净再分模型重跑测试。」

⇒ 不再问产品判断，先让分离真正干净。

### 10.1 真正的混在哪：不是厂商字面量，是**标识符**

前三道门全绿时，`edit_spec._clauses` 里还躺着 **13 处 `if edit_task:`**。
`edit_task` 名叫"任务类型"，但 `model_specs` 把它**写死**：2.0 永远 False、2.5 永远 True
—— 它就是型号开关伪装成任务开关。后果：改 2.5 的句式要在三家共读的文件里动手，
2.0 的产出跟着变。

扫描口径（跳过注释/docstring）：`edit_task` / `_sd20_*` / `_sd25_*` / `h3_*` / `_minimax*`。

| 文件 | 起始 | 现在 |
|---|---|---|
| `edit_spec.py` | 22 | **0** |
| `video_edit.py` | 6 | **0** |
| 其余共用文件 | 0 | 0 |
| **合计** | **28** | **0** |

### 10.2 做法：`Dialect` —— 各家把句式写进自己的模块

`models/base.py` 新增 `Dialect`：共用层只问"这家怎么说"，不再判断"是哪家"。

| 钩子 | 2.0 | 2.5 |
|---|---|---|
| `subj(obj)` | `将其中的X` | `把X` |
| `wardrobe_verb()` | `换成` | `修改为`（`guide:88` 的动词表里没有"换成"） |
| `person_duty()` | `；面部特征参考…，妆造参考…` | 空（走【目标素材职责】逐张说） |
| `keep_others()` | LAS 原句后半句 | 空 |
| `wardrobe_subject(ctx)` | `<主体N>` 优先 | 方位 → 外观短语 → 「服装」 |
| `orig_feat()` | 三档认人尺（`sd20=True`） | 一份独立副本（当前算法相同，待单独评估） |
| `style_ref` / `style_video` / `style_word` / `style_word_when_ref` | 参考句式 / 叠加 | 改成句式 / 三选一 |

`H3` 用 `NoDialect()` 占位（它走六段式，不经过 `_clauses`；真被调到就报错）。

配套搬迁（全部**纯文本搬运**，行为零变化）：
- `sd20_locator` / `_landmark_phrase` / `_ref_feat` / `_sd20_person_tags` → `volc20_compile.py`
- `_sd25_wardrobe_subject` → `volc25_compile.py`（改名 `_wardrobe_subject_25`）
- `h3_orig_locator` / `h3_english_spec` / `h3_english_extra` / `_h3_text_slots` / `require_english_extra` → `h3_compile.py`
- 闸要跟编译器用**同一把尺** ⇒ `sd20_locator` / `h3_orig_locator` 由**适配器**在 `gate()` 里注入，
  共用层 `video_edit` 不 import 任何一家

### 10.3 安全绳：34 条产出逐字节比对

工程没有 git，改完看不出动了谁。用 `prompt_snapshot.py --all --show` 把三家 34 条用例的
**编译全文**落盘（`D:/tmp/clone_diag/base_all_before.txt`），每搬一块就重导一次 `diff`：

```
搬迁前 → 搬迁后：34 条逐字节完全一致（做了 6 次，每次都一致）
```

### 10.4 第四道门：某家标识符

`model_separation_check.py` 新增 `branch_scan()` + `scan_idents()`：
共用 6 个文件的**代码行**里出现 `edit_task` / `_sd20_*` / `_sd25_*` / `h3_*` / `_minimax*` 就红。

自证（`--selftest` 尺子③）：坏样本 4 行真标识全中；docstring、注释、
`channel == "auto"`（用户选项，不是厂商名）都不算 → **4/4**。

现在三道自证：①厂商耦合 5/5 ②某家句式 2/2 ③某家标识符 4/4。

### 10.5 判据

| 门 | 结果 |
|---|---|
| `model_separation_check` | 四道门全绿 · 自证 5/5 + 2/2 + 4/4 |
| `model_registry_check` | 14/14 |
| `test_edit_spec` | 246 / 168 / 282（2026-10-29 实测；2.0 由 233 → 246 是 D53 修完后的数） |
| `test_video_edit_logic`（2026-10-29 起进必跑清单） | 84/84 · 共用层，对任何 `--model` 成立 |
| `ruler_sd20 / sd25 / h3 --current` | 红 0 |
| `ruler_sources --model X`（2026-10-28 新增） | 每家红 0（29 / 41 / 23 条规则的出处回原文核过，2026-10-29 数） |
| `ruler_atoms --model X`（2026-10-29 新增） | 原子表 29 / 41 / 23 条**全部可机械检**，分母自证三家都过 |
| `prompt_lint_check` | 744 / 830 / 1092 |
| `prompt_model_standards` · `p15` · `wiring` · `separate` | 17 / 45 / 104 / 35 |
| `prompt_provenance_check` | 全绿（11 处） |
| 34 条产出 | 逐字节不变 |

---

## 十一、2026-10-28 第四轮：资料层分离（主人：「资料也要做好分离，不然查资料又混回去了」）

前三轮分的是**代码**。这一轮分的是**资料**——官方文档和官方 skill。
理由是同一个：代码分干净了，但注释里写 `guide:95`，下一个读者（模型或人）
照样得先猜「这是哪家的第 95 行」。

### 11.1 病根（实测，不是设想）

改名之前，**裸 `guide:` 在工程里 190 处**，同一个词指向**两份不同文档**：

| 所在 | 处数 | 实际指 |
|---|---|---|
| 2.0 的文件 | 97 | `seedance-20-guide.md` |
| 2.5 的文件 | 46 | `seedance-25-guide.md` |
| **共用层** | 47 | **混着两家** |

共用层是最坏的：`vision_plan.py` 的 `guide:88` 指 2.5 的动词表，
`video_edit.py` 的 `guide:222` 指 2.0 的实战案例；
`audit_official.py` 同一个文件里 `guide:39/:56/:95/:121` 是 2.0、
`guide:189/:435` 是 2.5。

**为什么一直没人发现**：2.0 指南第 88 行是「## 1 定义主体」，
翻到那行也不会觉得错——只会觉得"官方没写这条"，然后按自己的理解改。

### 11.2 三步处置

1. **物理归拢** → `D:/tmp/official/{sd20,sd25,h3}/`
   每家一个目录，每家一张 `MANIFEST.json`（角色 / 缩写 / 行数 / sha256 / 出处）。
   原来的散落位置全部搬走；**13 份逐字节相同的副本**（`sd2pe_live.md`、
   `h3o/full/...`、`h3_doc_*.md`、`hf-VIDEO_PROMPT_*.md` 等）挪进
   `D:/tmp/clone_diag/quarantine_official_20261028/`（**没删**，附归档清单）。
   `D:/tmp/h3o/repo/` 是上游仓库克隆 = **出处本身**，不算我们的副本，不动。

2. **引注改名** → 190 处裸 `guide:` 全部改成 `sd20-guide:` / `sd25-guide:`。
   归属不是按文件名猜的，是三档证据定的：①行号越出 2.0 文档长度（硬）
   ②引用处「…」原文只在一份文档里出现（强）③文件家（弱，冲突则人工）。
   人工裁决 26 处，逐条写了理由。

3. **第五道门** `model_separation_check.py`：

   | 检查 | 判据 |
   |---|---|
   | `manifest_scan` | MANIFEST 里每份文件存在、sha256 与行数和磁盘一致 |
   | `docs_scan` | 代码里每处 `文档名:行号` 必须落在一家的 MANIFEST 词表里（裸 `guide:` 在这里现形） |
   | `dup_scan` | `official/` 之外不许有与正本逐字节相同的文件 |
   | `--selftest` 尺子④ | 坏样本 `guide` / `sd99-guide` 必须抓；`[:400]` / `ratio:1.5` / `http://host:8080` 不许算引注 |

   **词表只从 MANIFEST 读**，门不另存一份——两份清单迟早各说各话。

### 11.3 判据

| 门 | 结果 |
|---|---|
| `model_separation_check --selftest` | 5/5 + 2/2 + 4/4 + **2/2**（新尺子） |
| `model_separation_check` | 五道门全绿 |
| `prompt_snapshot --all --show` | 改动前后**逐字节一致**（34 条，diff 为空） |
| `test_edit_spec`（2.5） · `prompt_lint` · `prompt_model_standards` · `wiring` | 159 · 830 · 17 · 104 |
| `ruler_sd25 --current` | 红 0 |
| `prompt_provenance_check` | 全绿（11 处） |
| 硬编码资料路径 | 代码里 11 处路径常量（另 41 处路径字符串在注释/文档里）全部可解析，失效 0 |

### 11.4 顺手修掉的（改前就有，与本轮无关）

- `clone_pipeline.preview_render()` 用了 `models.adapter_for()` 但那个函数体内
  没 import `models` → `test_plan_preview` 直接 `NameError` 崩。
  是上一轮分离改动（同一段注释 `🩸 2026-10-28 分离门抓到过`）漏的 import。已补，29/29 通过。
- **2.5 快照基线陈旧 4 条**（`25 双人全换` / `25 双人全换+方位` /
  `25 双人·按人换装` / `25 单人·补充说明`）。用备份代码跑同一判据，
  **红的是同一批、长度一字不差** → 与本轮无关，是之前几轮改了产出没重新冻结。
  **没有擅自 freeze**，等结账。

### 11.5 规则（以后照这个写）

- 引用官方资料一律写**带家名的缩写**：`sd20-guide:` / `sd25-guide:` /
  `sd2-pe:` / `sd25-pe:` / `ref-en:` / `base-en:`。
- **裸 `guide:` 不是任何一家的缩写**——两家都叫 guide 就是歧义。
- 想加新的官方资料：放进 `D:/tmp/official/<家>/` 并在那家 `MANIFEST.json`
  里登记 `abbr` + `sha256` + `lines`，否则第五道门红。

---

## 十二、2026-10-28 第五轮：剩下的官方资料全部归位 + 门加严

主人的话：「现在只要把所有东西都分离干净，以后再新开发项目就简单得多了，
不要再像这样什么都混一起」。

### 12.1 我提错过的方案（记下来别再犯）

第一版我建议建 `official/volc-shared/` 放「两代共用」的 API 文档。
主人当场否掉：**「你又两家合一起还不是一样混吗？」** —— 对。
共享目录就是一个新的第三类，任何说不清归属的东西都会往里丢，几个月后又是大杂烩。

### 12.2 正确的分法：每家各存一份完整原文

| | 之前那个病 | 现在这个做法 |
|---|---|---|
| 一个名字指什么 | `guide:` 指**两份内容不同**的文档 → 真歧义，翻错了看不出来 | 两边**逐字节相同**，翻哪份都对 |
| 谁去翻 | 得先猜「这是哪家的行号」 | 干活的人只开自己那家目录，从不跨家 |
| 会不会漂移 | 改一处忘一处，没人发现 | **门强制两份 sha 相同**，改一边立刻红 |

判据落在 `load_manifests()`：同一个缩写出现在多家时，
①`shared_with` 必须互相声明覆盖彼此；②**直接比磁盘上的两份文件**（不信清单里写的 sha）；
不满足就是 `guide` 那个病，红。

### 12.3 这一轮归位的

| 文档 | 实际覆盖 | 去向 |
|---|---|---|
| `volc_sd20_tutorial.md`（1949 行） | 2.0×64、2.5×1 | 只进 `sd20/tutorial.md` |
| `volc-create.md`（855 行） | 2.0×33 / 2.5×46 | `sd20/` + `sd25/api-create-task.md` 各一份 |
| `ark-skill-doc.md`（513 行） | 独立文档 | 两家各一份 `ark-doc-skill.md` |
| `volc_vg_tutorial.md`（2276 行） | 2.0×33 / 2.5×40 | 两家各一份 `video-gen-tutorial.md` |
| `mm_full.txt`（15185 行） | MiniMax 文档站合集 | `h3/platform-docs.txt` |
| `seedance-trouble.md`（383 行） | 2.0 官方 FAQ V1.7 | `sd20/trouble.md` |

归档（不删，在 `D:/tmp/clone_diag/quarantine_official_20261028/`）：
`ark_doc.txt`（与 `volc-create.md` 同一文档的旧抓取，互相覆盖 91%）、
`reshot-cn.md` / `nomi.md`（第三方旁证；像素下限 `407696` 官方原文 `volc-api:333` 就有，不需要留副本）。

引注改名 **78 处 / 24 个文件**：`volc-create.md:N` → `volc-api:N`、
`volc_sd20_tutorial.md` → `sd20-tutorial`、`volc_vg_tutorial.md` → `volc-vg-tutorial`、
`ark-skill-doc.md` → `volc-doc-skill`、`mm_full.txt` → `mm-docs`。

### 12.4 门加了两条硬规则

| 新增 | 判据 |
|---|---|
| **资料路径门** | 生产代码（`app/` + `scripts/`）里出现 `D:/tmp/**.md|txt|json`，**必须**在 `official/` 下面。散在外面就红 —— 这条防的是「以后新加资料又随手丢在 tmp 根目录」 |
| **共享一致性** | 同一缩写跨多家时，两份文件必须逐字节相同且互相声明，否则红 |

自证扩到**六把尺子**：①厂商耦合 5/5 ②某家句式 2/2 ③某家标识符 4/4
④资料引注 2/2 ⑤资料路径 2/2 ⑥两代共用 1/1。

### 12.5 判据

| 项 | 结果 |
|---|---|
| `model_separation_check` | **八项全绿**（四道代码门 + 资料清单 + 引注 + 路径 + 副本） |
| `--selftest` | 六把尺子 6/6 |
| 34 条产出 | 逐字节一致（本轮只动注释，再一次证明） |
| registry · edit_spec · lint · standards · wiring · plan_preview | 14 · 159 · 830 · 17 · 104 · 29 |
| `prompt_provenance_check` | 全绿（11 处） |

### 12.6 给以后的原则（这是主人真正要的那件事）

1. **一家一个目录**，`official/<家>/` + `MANIFEST.json`；不建共享目录。
2. 一份官方文档覆盖两代 → **每家各放一份，门锁死 sha 相同**。
3. 引用写**带家名的缩写**（`sd20-guide:` / `volc-api:` / `ref-en:`），裸名一律红。
4. 新资料必须进 `official/` 并登记，否则路径门红 —— **不登记就过不了门**。
5. 门从 `MANIFEST` 读词表，**门里不另存一份清单**；两份清单迟早各说各话。

---

## 十三、2026-10-30 第六轮：**写提示词**这一层也分了（Seedance 2.0 接入）

前面十二轮分的是**出片编译器**。这一轮分的是「顾客说想法 → 写成提示词」那条对话链路，
以前它只有 H3 一家（`h3_direct`）。

### 13.1 两家是并列，不是「H3 换个文案」

主人 2026-10-30 定的两条：

> 「所有模型没有默认和更强，都是平级处理」

> 「2.0 的 skill 是单文件 你先别这么急着下定论哦，查阅清楚先哦」

查实后：2.0 的官方材料是**两份**，不是一份 ——
`skill-sd2-pe.md`（226 行，目录 + 工作流 + 输出合同）把正文用超链接甩给
`guide.md`（1008 行）。**只喂 skill = 只给目录**，与 H3（`SKILL.md` + `references/*.txt`）
同一结构。

### 13.2 分到哪一层

| 层 | H3 | Seedance 2.0 |
|---|---|---|
| 资料加载 | `h3_official.py` | `sd20_official.py` |
| 对话与写作 | `h3_direct.py` | `sd20_direct.py` |
| 判据（尺子） | `models/h3_base.py` · `h3_ref.py` | `models/volc20_pe.py` |
| 接口 | `prompt.py` 的 `target=h3` 分支 | `prompt.py` 的 `target=sd20` 分支 |
| 验收 | `p18_check.py`（在 `EXTRA["h3"]`） | `p20_check.py`（在 `EXTRA["volc20"]`） |

两家**互不 import**。共用的只有产品自己的东西：`<<<ASK>>>` / `<<<PROMPT>>>` 标记、
历史清洗、重试机制 —— 那些是产品协议，不是模型的规则。

### 13.3 规则为什么不能共用（逐条有出处）

| | H3 | Seedance 2.0 |
|---|---|---|
| 语言 | 英文 | 中文 |
| 时间 | 必须绝对时间戳 `At 00:03.500…`（`base-en:86`） | **禁**绝对秒数，用「镜头1/镜头2」（`sd2-pe:144`） |
| 台词 | `<d>[English]…</d>` | `{台词}`（`sd2-pe:203-206`） |
| 素材指代 | `<Picture 1>` | `@图片N` / `<主体N>`（`sd2-pe:16`） |
| 缺失 | 不许编，必须问 | 八大要素**自动补全 + 透明披露**（`sd2-pe:89`） |
| 兜底包 | 无此概念 | **必挂**（`sd2-pe:219`） |
| 更长 | 能力边界外，不许提分段 | 官方有「延长视频」，可以讲（`sd20-guide:44`） |

### 13.4 资料层：多了一个目录

`official/sd10-camera/` —— 运镜术语表。原因是 `sd20-guide:191` 官方自己写的：

> 「模型对运镜词理解力很强，直接使用标准运镜术语即可，例如"中景、特写、全景、
> 缓慢推镜、平稳横移、固定镜头"。更多请参见 [镜头语言](/docs/seedance-1-0-pro-pro-fast)」

**2.0 的运镜词表在 1.0 pro 那份文档里**。2026-10-30 主人拍板「运镜词表要从 1.0 pro
那份文档搬」，所以它是 2.0 的**官方指定上游**，不是跨型号搬运。只收术语与规则原句，
**不收 1.0 的示例句**（那些会把 1.0 的长句写法带进来，与「镜头1/镜头2」冲突）。

### 13.5 查过、决定不做的

| 项 | 结论 | 依据 |
|---|---|---|
| guide 里 4 张 SVG 流程图 | **不收**，无正文丢失 | 下载 SVG 抽文字：全部内容只有「必需 / 建议」两组标注，skill 章节已有 |
| `trouble.md`（5.3k token） | **不喂** | 与 guide「常见问题」逐条对应，独有内容属出片链路 |
| guide 附录 37 条案例 | **喂** | 与 H3 连 Case 1-4 一起喂同一口径；且是「怎么指代/怎么编辑」的对照样本 |
| 裁节喂 | **不裁** | 裁节 = 替官方写摘要，H3 已栽过这个跟头 |

### 13.6 两件报给主人的事实

1. `sd2-pe:225`「人脸参考最佳实践：使用大头照 + 全身照」、`sd20-guide:270`
   「角色图 1-2 张（面部特写 / 全身）」与 D48（一人一张图）字面冲突。
   主人 2026-10-30 裁定：**这是出片环节的标准，我们只出提示词，不管**；
   产品侧靠「只问风格/主角/时长」自然覆盖，不另加压制条款。
2. `model_specs.py` 里 2.0 的 `min_sec=4.0`，官方 `volc-api:325` 是 `[2,15]`。
   **写提示词这一层按 4 秒起问**（主人 2026-10-30 拍板「B 4秒」）；
   出片层保持原样未动。

### 13.7 判据

| 项 | 结果 |
|---|---|
| `p20_check.py` | **26 / 26**（含「不传 target 就拒绝」「没把 H3 规则串进来」「素材标签用 @图片N」） |
| 尺子自证（`D:/tmp/t_sd20_rules.py`） | 官方原句**零红**；6 个单变量坏样本**全红** |
| `model_separation_check` | 八项全绿（词表 28 条，含 `sd10-camera`） |
| `check_all --model volc20` | 通过 45 / 跳过 5 / **红 0** |
| `p18_check --model h3`（跨轮回归） | **96 / 96**，两家共用接口没把 H3 带崩 |
| 浏览器实点（`D:/tmp/e2e_prompt_page.py`） | **34 / 34**，含「没选就先弹选择」「换回 H3 仍出稿」 |
| 真模型 | **未跑**（要花钱，等主人放行） |

### 13.8 同日第二轮：把「优化问题」接上 + 尺子补齐官方强制项

**背景**：13.7 里那条「真人模型未跑」之后跑了真机三场景（3 次调用，主人 2026-10-30
批准），暴露出**根因级别的产品问题**，不是模型不听话：

> 我们的护栏（`CHAT_GUARD`）自己复述了一遍官方规则，还**复述漏了**
> （八大要素、路径 A/B、音频通道、特殊字符全没写在护栏里）。
> 而护栏写在 skill 原文**之后**，语气又比原文硬 → 模型按护栏办 = 拿到一版残缺规则。
> 护栏 2600 字，其中大部分是重复。

**修法（不是加规则，是把重复删掉）**：

| 改动 | 位置 | 说明 |
|---|---|---|
| 护栏削到 1528 字 | `sd20_direct.CHAT_GUARD` | 只留产品层：输出协议、片长口径、两个原件必须顾客给、拒什么、能力边界；开头明写「工作流以上面的官方原文为准」 |
| 加 `<<<NOTE>>>` | `sd20_direct` / `prompt.py` / `index.vue` | 官方 Step 4「优化问题」的落点；解析时从提示词里**剥出去**，顾客复制带不走；前端是默认收起的灰字块 |
| **传图不再一律当截图** | `sd20_direct` | 原护栏只写「顾客传截图 = 片子已经出来了」→ 顾客**第一次传主角照**会被模型当成废片去"改上一稿"，而上一稿根本不存在。改成按历史分流：没出过稿 = 参考素材（照图写准），出过稿 = 成片截图（只改被指到的） |
| **附件图按上传顺序编号** | `prompt.py` / `sd20_direct` / `index.vue` | 附件图占 `@图片1..@图片N`，素材面板里声明的图片**接着往后编**（不撞号）；上限按**合计**算（附件+面板 ≤ 9，`volc-api:35`）。前端缩略图左下角标编号，顾客照着这个顺序在 2.0 里传即可（主人 2026-10-30：「一般都会按照原来上传的顺序来执行操作」）。顾客自己给过名字就写 `<主体1>@图片1（小美）`（`sd2-pe:153` 的语法） |

**尺子（`volc20_pe`）从 7 条补到 11 条**，补的都是官方写明「强制」但我们没查的：

| 编号 | 级别 | 内容 | 出处 |
|---|---|---|---|
| V8 | 黄 | 背景音乐用 `（）` 包住 | `sd2-pe:205` |
| V9 | 黄 | 音效用 `<>` 包住 | `sd2-pe:206` |
| V10 | 黄 | 非文字生成任务挂字幕兜底 | `sd2-pe:160/:219` |
| V11 | 黄 | 多人场景挂双胞胎兜底 | `sd2-pe:162/:219` |

🩸 四条都**只在触发条件成立时才判**，不是无条件查：
V8 只在正文提到音乐时要求（否则会误伤官方自己的 `<主体1>（李武）` 注解写法）；
V9 只在提到「音效」时要求（否则「脚步声 / 远处话语声」这种自然描述会被误判，
官方路径 B 示例 `:178` 就是不加尖括号的）；V10 对文字生成任务豁免；
V11 除了 `<主体2>` 还认「舍友们 / 他们」这类复数指代 —— 官方路径 B 示例的舍友**没有编号**。

**判据（全部零费用）**：

| 项 | 结果 |
|---|---|
| `p20_check.py` | **44 / 44**（新增 4e-g 编号与合计算上限、7e-f 传图分流、9a-c 披露拆分与透传、10a-i 四条新尺子的成对正/坏样本） |
| 浏览器实点 | **40 / 40**（新增 5e-i：披露默认收起、点开可见、正文一个字不变；6c 附件缩略图标编号） |
| `check_all --model volc20` | 通过 45 / 跳过 5 / **红 0** |
| 真机离线复核 `D:/tmp/t_probe_replay.py` | **14 / 14**（用上午的真机原文重放，不花钱） |
| 真机（披露真的会输出吗） | **未跑**，要再花一次调用 |

**10a/10g 用「成对」写法**：正样本 = 官方路径 A/B 示例原文（不该被新判据判到），
坏样本 = 在正样本上只动一处（必判到）。只验一边等于对空对象恒真。

### 13.9 2026-10-30 第三轮：**8 份官方材料，第一版只喂了 2 份**

**主人一句话点破**：「你只喂了半个 skill，还有其他的细节都做足了没」。

穷举核对（8 份原件，`D:/tmp/official/sd20/`）：

| # | 文件 | 行数 | 处理 | 说明 |
|---|---|---|---|---|
| 1 | `skill-sd2-pe.md` | 226 | ✅ 全喂 | 工作流 Step 0–4 + 输出合同 |
| 2 | `guide.md` | 1008 | ✅ 全喂 | 正文 + 附录案例 |
| 3 | `trouble.md` | 383 | ✅ **本轮补喂** | 第一版漏了 |
| 4 | `tutorial.md` | 1949 | 🟡 摘 22 行 | 提示词技巧/规则章节；其余是 SDK 代码 + 5 条 API 示例 |
| 5 | `video-gen-tutorial.md` | 2276 | 🟡 摘 10 行 | 提示词建议章节；其余是 SDK 代码 + 9 条 API 示例 |
| 6 | `api-create-task.md` | 855 | ⚪ 不喂 | 出片参数表；写提示词只取两条（素材上限 图9/视频3/音频3、中文≤500字） |
| 7 | `ark-doc-skill.md` | 513 | ⚪ 不喂 | 讲「怎么安装 sd2-pe 这个 skill」，不含提示词内容 |
| 8 | `las_cn.md` | 622 | ⚪ 不喂 | LAS 视频编辑**算子**，出片后处理环节 |

新增 `tips-sd20.md`（38 行）= 上面 🟡 两处的**逐字摘录**，每段标出处行号，不写摘要。

**为什么 trouble.md 漏不得**（grep 实证，guide/skill 里一个字都没有）：

- `1.4 参数规范`：「时长和宽高比可以通过接口传，但为保最佳效果，可以在提示词最前面/最后面也加上，
  比如 **时长：4秒，比例：9:16**。⚠️ 要用中文的"秒"，不能写"s"」
- `4.1 通用优化原则` 五条：重要内容前置 / 明确约束指令 / 主体明确指代 / 避免冗余 / 参考素材独立
- `1.1 任务类型`：参考 / 编辑 / 延长三类任务的推荐句式，以及
  「编辑和延长任务中，提到视频时**不要**用"参考视频N"，直接 `<视频N>`，避免被认为是参考任务」
- `1.2 主体定义`：「Asset 库里的 `[asset-xxx]` 不能替代图1/视频1，模型对不上」
- V-1~V-11 逐条症状与解法（ID 漂移 / 字幕 / 水印 / 风格漂移 / 双胞胎 / 胡言乱语 / 尾音 / 发音…）

**system prompt 现在多大**：46,495 字符（skill 9,596 + guide 25,399 + trouble 9,446
+ tips 1,274 + 运镜 772），比之前多 1.07 万字符。

**判据**：`p20_check` **49 / 49**（新增 8a 五份 sha 互不相同、8d trouble 四条独有原文真在 system、
8e 教程章节真在 system）；分离门八项全绿（词表 29 个）；`check_all` 通过 45 / 跳过 5 / 红 0。

### 13.10 两处**官方自己前后不一致**（报给主人，不自行裁决）

| # | 冲突 | 出处 |
|---|---|---|
| 1 | **绝对秒数** | `skill:144/:223` 明写「**禁止**写绝对秒数（如 `0–3s`），2.0 对精确时间支持不稳定」；`trouble:1.3` 说「支持镜头顺序，对精确时间**支持不稳定**，建议不强制限时长」；**但 `tutorial.md` 官方示例本身写了 `2-4 秒：快速切镜` `4-6 秒：…`** |
| 2 | **参考标签语法** | `skill:137/:153` 用 `@图片N` 和 `<主体1>@图片1（名字）`；`guide` 附录案例用**裸** `图片1`；`trouble:1.2` 用 `<图片1>`；`tutorial` 「提示词规则」说「必须使用**素材类型+序号**格式，例如「图片 n」，指代 content 数组中第 n 个 image_url」 |

我们现在的口径：**V1 按 skill 判红**（绝对秒数一律不允许），**标签一律用 `@图片N`**（skill 口径）。
理由：我们交付的提示词是给顾客在 2.0 网页输入框用的，skill 是官方为「写提示词」这个动作出的规范；
guide 附录和 tutorial 那两处是 API 调用视角的写法。

### 13.11 2026-10-30 第七轮：H3 改成 **agent 自己读 skill 包**（`<<<ASK>>>` 文本协议退役）

**主人点破的三件事**，逐条对应这轮的改动：

| 主人原话 | 查实的结果 | 改法 |
|---|---|---|
| 「你还记得我们这个项目具体是做什么的吗？花钱调 agents 的能力用来干嘛？」 | 我们把官方文档**人工摘抄**进 system，摘漏了自己也不知道 | 官方 skill 包**原样搬进工程**，模型自己 `list_skills` → `read_skill` |
| 「你先从头到尾看完 H3 的一整套 skill 了吗？」 | **没有** —— 只看过 9 个包里最小的那个（`h3-prompt-writing` 40 行） | 9 个包 36 个文件全搬（md5 36/36 一致，源 `MiniMax-H3-d21241f0`）|
| 「如果存在后台直接让 agents 调取指定模型的 skill 完整包然后执行对话模式会怎样？」 | 可行 —— 真机跑了两轮（3 次调用 / 25 秒；6 次调用 / 51,457 token / 102 秒），模型**自己跨 skill** 编排 | 全面转 agent |

**H3 的 9 个 skill 包**（`backend/data/official/h3/skills/`，合计 1,926 行 SKILL.md）：

| 包 | 行数 | 性质 |
|---|---|---|
| `h3-prompt-writing` | 40 | 纯格式规范（原来只有它被用上） |
| `3d-animation-short-generator` | 249 | 带 Start Gate 的完整生产流 |
| `brand-promo-generator` | 189 | 同上 |
| `co-op-game-intro-generator` | 54 | 同上 |
| `handdrawn-live-generator` | 87 | 同上 |
| `minimalist-product-ad-generator` | 398 | 同上 |
| `music-video-subtitle-generator` | 205 | 同上 |
| `paper-collage-generator` | 273 | 同上 |
| `papercraft-stop-motion-generator` | 471 | 同上 |

8 个体裁包的 `compatibility` 写着 `Requires the MiniMax Hub agent (canvas workspace)` —— **不能原样搬**，
但方法论可学；护栏里明写「你读不到画布，skill 里提到画布/生图/出片的步骤，改成给顾客可执行的提示词」。

**此前那份判断是错的**：我 2026-10-30 上午 grep 了 `suggest` / `confirm` / `ambiguous`
在 `SKILL.md` + `base-en` + `ref-en` 里出现 **0 次**，就下结论「H3 的 skill 只有格式规范」——
那只覆盖了 9 个包里的 1 个。

#### 分层（两家平级，互不 import）

| | 文件 | 干什么 |
|---|---|---|
| 通用 | `app/services/skill_agent.py` | 列目录 / 读文件 / 跑循环 / 过判据。**不含任何一家内容** |
| H3 | `app/services/h3_skill.py` | `ROOT` 指向 H3 的 skill 包 + 产品层护栏（923 字符） |
| 旧 H3 | `app/services/h3_direct.py` | **回滚路**，接口不再调用；`_chat` 仍被生成/转换/修订三条老路用 |

**输出协议从文本标记换成工具**：`<<<ASK>>>` / `<<<PROMPT>>>` 退役，改用
`list_skills` / `read_skill` / `ask_user` / `deliver_prompt` 四个函数。理由：文本标记漏过一次
（官方 Step 4 的披露段模型没写），工具是结构化的。

**护栏里一条 skill 正文都不留**（`p21` 6a/6b 断言）：system 923 字符，对比 2.0 的 46,495 字符。
规则全在包里，模型没读到的东西就是不该写的东西。

#### 判据

| 脚本 | 结果 | 覆盖 |
|---|---|---|
| `p21_check.py`（新，39 条，零费用） | **39 / 39** | skill 包列举/读取/防穿越、ask 即停、交付、判红只回灌一次、步数/token/读取上限、system 无 skill 正文、**model 键→端点名**、**交付形态 + 7000 字符上限（10a–10d）** |
| `p18_check.py`（56 条） | **56 / 56** | C/R = 生成转换修订（生产路）；**A 段 = 接口→agent 接线**（p21 不经 HTTP，只有这里覆盖） |
| `check_all.py --model h3`（全量含穷举） | **通过 54 / 跳过 4 / 红 0**（112 秒） | 分离门八项全绿（比上轮少 1 项：拆槽层自检随 `/prompt/optimize` 一起删） |

#### 同日清理：`h3_direct.chat_turn` 连它自己的测试一起删

主人 2026-10-30 晚一句：「实在不行我们就删除这些垃圾代码」→「删」。

| 删掉的 | 行数 | 为什么是垃圾 |
|---|---|---|
| `h3_direct` 的 `chat_turn` / `_chat_multi` / `_clean_history` / `ASK_TAG` / `PROMPT_TAG` / `MAX_ASK_ROUNDS` / `CHAT_GUARD` | **192 行**（471 → 279） | 接口改走 agent 后**零调用方**；`<<<ASK>>>` 文本协议只在 `sd20_direct` 还有一套，p20 全覆盖 |
| `p18` 的 L 段（我自己上一轮写的 22 条） | 约 120 行 | 给死代码上保险，属于自造 |

删前三条举证：① 等价副本 = `docs/_archive/h3_direct_chat_turn.txt`（逐字带原行号 + 回滚说明）；
② 全工程 grep 0 引用；③ 主人点名「删」。

`h3_direct` 剩下的 279 行**全部还在生产路径上**（`generate` / `revise` / `_chat` /
`guess_kind` / `ROLE_DESC`），别误删。

#### 同日第二刀：`/prompt/optimize` 整条链 + 首页三张入口卡

主人：「删吧，你都说这么清楚了！还有你刚才说的死代码！都删了再花钱跑一次」。

| 删掉的 | 量 | 为什么 |
|---|---|---|
| `/prompt/optimize` 路由 + `_optimize` + `OptimizeIn` + `_reds` + `MAX_TRIES` | prompt.py 653 → 566 行 | 前端 `promptOptimize()` 定义了但**没有页面调用**；它就是 2026-10-29 已被推翻的拆槽方案 |
| `app/services/h3_base_slots.py` | 整份 359 行 | 只服务 `/prompt/optimize` |
| `scripts/test_h3_base_slots.py` | 整份 459 行 | 被测对象已删 |
| `p18` 的 46 条 optimize 断言、`p19` 的 K4、`check_all` 的「拆槽层自检」 | 46 + 1 + 1 项 | 同上 |
| 前端 `promptOptimize()`、首页三张入口卡 `QUICKS` | 33 + 46 行 | 主人指名的「这些示例」 |

存档：`docs/_archive/deleted-2026-10-30/`（prompt.py 删块、两个整份文件、index.vue 的 QUICKS 五段）。

#### 🩸 这一刀切多了：p18 的 C 段（转换）被误删

**怎么发生的**：删 optimize 那 46 条时，我把锚点选成「`# 2 正常一次过`」到「`修订`」——
中间隔着的整个 **C 段（转换，C1–C10 + `BASE_OUT`/`REF_OUT` 常量）** 被一起切掉了。
脚本没存档切口，工程又不是 git 仓库，**当场没有任何副本**。

**怎么救的**：从会话记录 `b109763f-….jsonl` 里把 C3–C10 的原文逐字捞回来（正好当初
Read 过 300–375 行）；C1 尾部与 C2 按 `_convert` 的实际行为重建。p18 现在是 56 条（原 75 −
optimize 46 + 找回 27）。

**教训**：删一段代码前，**起止锚点必须夹住且只夹住那一段**；改完立刻 `ast.parse` + 跑一遍，
不要等到三处都删完才跑。

#### 🩸 这趟真机跑出来的真缺陷：E5 判据说假红

同一晚第二次真机（删完再跑）：8 次调用 / 73,605 token / 233.6 秒，正文 6,340 字符，
但**留了 1 条红**：`E5 [Shot 3] 缺 At MM:SS.mmm` ×3、`[Shot 4]` ×2。

查下来是**尺子的问题，不是模型的问题**（`ref-en:218` 只说 §5 的镜头标题要带时间戳）：

| 毛病 | 后果 |
|---|---|
| 扫**全文**而不是 `detailed_description` | 官方自己 §4 的示例 `<Subject 4> (appears in [Shot 2], [Shot 3])`（`ref-en:325`）会被判"缺时间戳" |
| tail 正则 `([^\n]{0,40})` **贪婪** | `[Shot 1], [Shot 2], [Shot 3]` 只匹配出 Shot 1，后面的被吞进 tail |

修法：① 只扫 `detailed_description`；② 同一编号**只看第一次出现**（后面都是回指）；
③ 中段缩到 40 字符窗口，不再吞行。留下成对探针 `ruler_h3.py` 的 E5 两条
（坏样本要响、带官方标注的好样本不许响）。

修完：探针 **24/24**、`--current` **0 条红**（改前误伤 8 条产品产出）、`--calib` 0 条红。
**那趟真机产出的 E5 是假红，提示词本身是合规的。**

#### 钱

真机验证两次，均主人批准：3 次调用 12,077 token / 25.1 秒；6 次调用 51,457 token / 102.3 秒。
单轮上限写死 `MAX_STEPS=12` / `MAX_TOKENS=80_000` / `MAX_READS=30`（实测一个完整产品广告流程约 5.1 万 token）。

#### 真机跑**工程里的** `h3_skill.run`（2026-10-30 晚，主人「跑」）

前两次跑的是我手写的探针循环，**不是同一份代码**。这一轮直接调生产执行器，两轮对话：

| 轮 | 调用 | token | 干了什么 |
|---|---|---|---|
| 1 | 3 | 14,251 | `list_skills` 看到 9 个包 → 自己挑中 `minimalist-product-ad-generator` → 读 SKILL.md（32,235 字符）→ 按 Start Gate 问 3 组 |
| 2 | 5 | 61,599 | **跨 skill**：同一包 → 转 `h3-prompt-writing/SKILL.md`（2,619）→ `references/ref-en.txt`（23,552）→ **判据判到 1 条红 → 回灌重试** → 交付 6,320 字符六段式 |
| 合计 | 8 | **75,850** | 252 秒。成品带 `<Picture 1..3>` 按上传顺序、note 里说明「已修正：把 [Shot N] 只留在 detailed_description 里」 |

**这一跑抓到一个生产 bug**（这也是为什么值得花钱跑真机）：

```
AgentError: 生成接口 404 {"code":"InvalidEndpointOrModel.NotFound",
                          "message":"The model or endpoint pro does not exist"}
```

`h3_skill.run` 把前端传的**白名单键**（`lite` / `pro` / `deepseek`）原样发给了方舟。
`h3_direct.generate:110` 和 `sd20_direct:67` 都在自己内部翻（`MODELS.get(model)`），
agent 这条路漏了 —— **接口层每一轮都会 404，不是探针写错**。

修法：`model = h3_direct.MODELS.get(model) or h3_direct.MODELS[h3_direct.DEFAULT_MODEL]`。
留断言 `p21:9a/9b`（白名单键→端点名、不传→默认端点名），并做过反证：
把旧写法放回去，9a **会红**（会发出 `'lite'`）。

#### 真机第三跑：顾客答一半就说「你决定」（2026-10-30 深夜，主人「那就测」）

**为什么单测这个**：删 `chat_turn` 时一起丢了 `MAX_ASK_ROUNDS`，我一度建议补回去（怕模型无限问）。
主人一句「你不是说 agent 直接调 skill 就可以了吗？以前我们自己加的规则都不需要了？是你没测过所以你不敢确定是吗？」
—— 对，我没测过。官方的 `h3-prompt-writing/SKILL.md` 第 20/51/82/124 行本来就写了什么时候该问、什么时候该写；
我们要验的是**真模型会不会照它做**，而不是我们替它加一条上限。

`D:/tmp/probe_ask_loop.py`，直接调工程里的 `h3_skill.run`，模拟顾客回一句「你定就行」，看它问几轮：

| 轮 | 调用 | 干了什么 |
|---|---|---|
| 1 | 5 | `list_skills` → 挑 `minimalist-product-ad-generator` → 读 SKILL.md → `ask_user` 问 3 组（片长/调性/产品卖点） |
| 2（顾客说"你决定"） | 4 | 读 `h3-prompt-writing/SKILL.md` → `references/ref-en.txt` → 判据回灌 1 次 → `deliver_prompt` |
| 合计 | **9** | **92,805 token / 271.5 秒 / 2 轮就写** |

结论：**「问几轮没有上限」不是缺陷** —— 官方 skill 自己有 Start Gate，模型问到信息够就写。
**因此不补 `MAX_ASK_ROUNDS`**（补了就是自造规则，还会挡住正常的多轮澄清）。

这一跑同时抓到两个真缺陷（都不是模型的问题）：

| # | 现象 | 根因 | 修法 |
|---|---|---|---|
| 1 | 交付正文 **9,927 字符**，接口硬上限 7,000，判据却**全绿** | `h3_base` 有 `B4`（`api-create:407`），`h3_ref` **一条长度规则都没有**；这次成品被判成 ref 模式 | `h3_ref` 加 `E24`（`api-create:407`，「`text` 最多 7000 个字符」），锚句已过 `ruler_sources` |
| 2 | 正文开头是 `WORKFLOW 1. First generate the three anchor images…` —— 顾客拿到的是**操作说明**不是提示词 | 我写的护栏说「画布步骤改成给顾客可执行的提示词」，模型照做了，写进了正文 | 护栏改成：**画布/生图/出片的步骤一个字都不要写进正文**，正文从第一个字段名开始；操作交代写进 `note` |

新增断言 `p21:10a–10d`（成对：超长 ref 稿必须判红 / 同格式正常长度不误伤；护栏措辞；system 仍 <3000）。

**这一跑之后**：`p21` 39/39、`p18` 56/56、`ruler_h3 --probes` 25/25、`--calib` 0 红、`--current` 0 红、
`ruler_sources` 24/24 锚句全绿、`check_all --model h3` 通过 54 / 跳过 4 / 红 0。

**费用**：本跑 9 次调用 / 92,805 token / 271.5 秒。今天四次真机合计
**26 次调用 / 232,189 token**（3×12,077 + 6×51,457 + 8×75,850 + 9×92,805），全部主人批准。

#### 前端

H5 页加了秒数计数：`正在写 · 已 18 秒`，25 秒后补一句「模型在读官方 skill 包，这是正常的」。
原因：一轮 5–12 次调用、实测 25～102 秒，请求是一次性返回没有流，60 秒不动顾客会当卡死关页面。

#### 同日晚：结构清理（主人：「说白了还是自身代码不够干净导致的」）

三处**同一件事写了两遍以上**的地方，是"旧代码污染判断"的物理来源 ——
我记不清哪份是真的，就拉最熟的那份用。全部合并：

| 脏在哪 | 原来 | 现在 |
|---|---|---|
| 型号白名单 + 传输 | **三份**：`h3_direct` / `sd20_direct` / `prompt.py` 各抄一遍；翻译动作在各自内部，`h3_skill` 那份漏了 → 真机 404 | `ark_chat.py` 一份：`MODELS` / `DEFAULT_MODEL` / `resolve()` / `post()` / `ArkError` |
| H3 共用件长在旧模块上 | `h3_skill` 为了拿 `guess_kind` **反过来 import `h3_direct`**，而它自己的注释写着"平级互不 import" —— 新路靠旧路活着 | `MAX_CHARS` / `MAX_SOURCE_CHARS` / `ROLE_DESC` / `guess_kind` 搬进 `models/h3_common.py`（本来的中立件），两条路真的互不 import |
| 转换 / 修订的重试循环 | `generate` 和 `revise` 各抄一遍（空/超长/判据/回灌/记录），改一处必漏另一处 | 合并成 `_deliver(send, …)` + `_reds()`，两份各剩一个 `send()` |
| 幽灵出处 | `h3-create:407` —— 这个键**在 `ruler_sources.DOCS` 里根本不存在**（文档早改名 `api-create`），14 处（含两处**运行时**拼给模型/顾客的字符串） | 全部 `api-create`，逐条核过行号在 `api-create-2026-10-28.md` 里仍对得上 |
| 两个 `MAX_TEXT` | `h3_direct.MAX_TEXT=20000`（原稿上限）与 `prompt.py.MAX_TEXT=4000`（一次能打多少字）**同名不同义** | 前者改名 `MAX_SOURCE_CHARS` |
| 两个默认型号 | `prompt.py` 报 `lite`、实际生成用 `pro` —— 健康检查说的和做的不是一个 | 统一 `ark_chat.DEFAULT_MODEL = "pro"`（前端不读这个字段，已核） |

**两条边界写进了文件顶部**（不是为了好看，是为了下次我不再拿旧规矩套新路）：
- `h3_direct.py`：「本文件的规矩只管转换/修订，**别把这里的护栏、字段、长度规矩套到 agent 那条路**」
- `h3_skill.py`：「**别把 `h3_direct` 的规矩搬过来**，这条路的规则只在 skill 包里」

**回归**：`p18` 56/56 · `p19` 32/32 · `p21` 39/39 · `p14` 21/21 ·
`test_task_resume` 15/15 · `test_gen_cache` 14/14 · `test_ark_edit_body` 42/42 ·
`check_all --model h3` 通过 54 / 跳过 4 / 红 0。

**未跑**：`p20`（Seedance 2.0 对话链路）—— 本轮型号锁在 h3，按"一轮一家"没切锁。
`sd20_direct.py` 动过（白名单与 `_post` 改走 `ark_chat`），**下次 volc20 轮第一件事跑 p20**。

### 13.13 2026-10-30 第八轮：**顾客离开页面，这一轮照样跑完、照样留得下**

**主人原话**：「我刚才点了一下新对话，历史那里不会继续输出！我希望的是我不在那个页面也会把之前的提问输出完整」。

**原来错在哪**（两条，都在同一处）：
1. 结果只写回**浏览器里那个组件对象**（`send()` 里的 `ai`）。顾客一点「新对话」，`reset()` 把
   `msgs` 清空，那个对象虽然还会被填，但已经不在页面上 —— 几十秒的计算白跑。
2. `finally` 里的 `stash()` 用的是**当时**的 `this.sid`，切走之后它 stash 的是新对话，
   旧的那份连存档机会都没有。
3. 补一处：`loading` 是共用的一个布尔。上一轮回来会把**新一轮**的转圈和秒数清掉
   （原来只有串行使用所以看不出来，现在两轮能同时在跑）。

**怎么修的**（前后端各一半，缺一半就不成立）：

| 半边 | 改了什么 | 位置 |
|---|---|---|
| 后端 | 三条路（chat / convert / revise）从 `asyncio.to_thread` 改成**独立线程池** `_POOL`，等待用 `asyncio.shield` 包住 —— **取消只作用于等待者，活照跑** | `app/api/prompt.py` `_detach` / `_wait` |
| 后端 | 跑完**先落盘再返回**：`_run()` 不管成败都把这一轮写进会话文件（失败记一条 `error`，顾客回来知道是失败了，不是没发） | 同上 `_run` / `_card` |
| 后端 | 幂等：前端那一份可能**先整份推过**（尾条已经是这一问），尾条一样就不再记，否则回来看到问两遍 | `prompt_sessions.append_turn` |
| 前端 | 三条请求都带 `sid`；结果回来时若 `this.sid !== sid0`（顾客走了）就**什么都不写**，尤其不许污染新对话的 `lastPrompt` | `index.vue` `route()` / `send()` |
| 前端 | `finally` 只在「还是同一份」时才 `stash()`；`loading` 时**不许整份推后端**（后端正在同一个文件里追加，两边同时写谁后落地谁说了算） | 同上 |
| 前端 | 「历史」常驻（原来 `v-if="sessions.length"`，空对话里会消失 —— 恰恰是最需要它的时候）＋ 每次打开都跟后端对一次，且**不抹掉本地还没推上去的那份** | `openHist()` |
| 前端 | 恢复历史时 `blocks` 由 `question` 现拆（后端只存模型原话），`lastPrompt` 兼容后端的 `last_prompt` | `openSession()` |

**判据（都实跑）**：
- `p18` **68/68** 全绿，新增 5 条：S6（等待者被取消，问 + 答仍然落盘）· S6b（落盘的是完整成品不是半截）·
  S6c（标题/轮数后端自己定）· S6d（前端推过的那一问不重复记）· S7（跑失败也写 `error`）· S8（不带 sid 的老调用方不受影响）
- **浏览器 E2E** `tools/e2e/prompt-leave.js`（桩后端，零费用）：发出去 0.6 秒就点「新对话」→
  ①新对话干净 ②请求带了 sid ③空对话里历史按钮还在、点开能看见那一份 ④切回去是完整成品。
  **四条全绿。** 🩸 第一次跑栽在「点了看不见的元素」：底部 tabbar 里也有一条文字是「历史」，尺寸 0，
  点它等于点 (0,0) —— 桩里现在只认 `width>0 && height>0` 的。
- `p21` 43/43 · `check_all --model h3` 通过 54 / 跳过 4 / 红 0 · `npm run build:h5` DONE

**没验的**：真实后端重启后的那一轮（重启归主人）；以及「两个标签页同时聊同一个 sid」（没做跨标签同步，本次不提）。

#### 13.13 补记：**真正让历史变空的是前端那一句过滤**（2026-10-30 当天第二次）

主人打开历史看到的是「只有自己说的话，AI 那几条全是空的」。查后端存的原文：
`s1793342148783.json` = **3 条 user、0 条 ai**。根因不在后端，在这一行：

```js
// 旧：没有实质内容就不存
const keep = this.msgs.filter((m) => !m.loading && (m.text || (m.images || []).length))
```

AI 那一条的 `text` **永远是空字符串**（内容在 `data.prompt` / `data.question` 里），
所以这条过滤**每一轮都把答案当垃圾扔掉**。历史里于是只剩顾客自己说的话。

而且它比"只是没存"更糟：前端每轮结束还会**整份 PUT 上去**，
**把后端 `append_turn` 刚写好的完整记录又覆盖成残缺版** —— 服务端明明做对了，
被客户端一推就没了。这也是为什么「后端加了落盘」当时看起来没起作用。

**改法**：判「有没有实质内容」按角色分开 —— AI 看 `data || error`，顾客看 `text || images`。

**判据**：`tools/e2e/prompt-history.js`（桩后端**只存前端推上来的那份、不帮忙补**，
所以能过就只能是前端自己留住了）：
①页面上有答案 ②历史里答案完整 ③说明默认展开 ④没有空白 AI 气泡 —— **四条全绿**；
桩的日志直接打出 `[PUT] … msgs=2 其中 ai=1`（旧版这里是 `ai=0`）。

**代价**：主人那两次对话的答案**取不回来** —— 它们从来没被写到任何地方
（本地过滤扔了、后端被覆盖了）。如实告知，不编。

> ⚠️ **更正（同一天，我报错过一次）**：我先说「`run_log` 那几条是测试桩不是真跑」——
> 那是**只看了文件大小和 tokens 就下的结论**，没打开看 `messages`。实际里面就有主人那三轮
> 真跑（14:37:58 / 14:38:46 / 14:41:07，16.3K / 13.6K / 27.9K tokens）。
> 教训：判「是不是真跑」要读 `messages` 里的原话，不能看字节数猜。

#### 13.14 理解模型**没有默认**（2026-10-30，主人：「顾客前端选什么就选什么」）

**原来错在哪**：前端 `data.model = 'lite'` **预选**好了 —— 顾客一次都没选过，
跑的就是 lite。上一轮「默认统一 pro」那个改动（`ark_chat.DEFAULT_MODEL`）**从来没生效**，
因为前端每次都显式传自己的预选值。主人那三轮真跑 `run_log` 里 `model=lite` 就是证据。

**改法**：模型跟「写给哪家」一个规矩 ——
- 初始为空，界面显示「选一下」（带 `opt-need` 高亮）
- 第一次发送前弹选择框，**取消了就不发**（`canSend` 不背这个锅，`send()` 里拦）
- 选过记本机（`vt_prompt_model`），下次不再打断 —— 记住的是**顾客的选择**，不是我们给的默认
- 后端的 `DEFAULT_MODEL='pro'` 保留，但只给**调用方完全没传**的脚本/测试兜底，产品上走不到

**判据**：`tools/e2e/prompt-model.js`（桩后端）
①新浏览器打开是「选一下」②不选就发 → 弹框且**请求没发出去**③Pro 在选项里
④发出去的请求 `model=pro` ⑤刷新后还记得 —— **五条全绿**。
另外 `prompt-history.js` / `prompt-leave.js` 跟着补了选模型那步，重跑仍全绿。

### 13.15 2026-10-30 第九轮：**转换这条路从产品上摘掉，粘稿改走对话路**

主人一句「不下线等着继续拦？」——**摘了。**

**为什么摘**（同一份 2,918 字、8 镜的别家成稿，同一天真机对照）：

| | 代码路 `/prompt/convert` | 对话路（带一句「内容一个字都别改」） |
|---|---|---|
| 耗时 | 292 s | 126 s |
| 原稿 31 句保住 | 22 句（71%） | **27 句（87%）** |
| 原稿没有、自己加的句子 | 28 句（含 **5 句自创运镜**） | 5 句（全是三字段名/切镜/声音段这类格式必需） |
| 片长 | 写死 5 秒，界面改不了 | 它自己问，顾客也能定 |

代码路那 5 句自创运镜（原稿一个运镜字都没有）：

```
The camera remains in a static shot, keeping the dog in shallow focus beyond the girl's shoulder.
The camera trucks left with small amplitude at slow speed to keep her and the dog in frame.
The camera remains in a static shot as the ball slows and stops directly in front of the dog's trembling paws.
The camera tracks the dog as he runs out and returns.
The camera remains in a static shot with shallow depth of field, keeping her smiling face …
```

「只搬运不改写」的工具往里加内容 = 方向反了。而且当天判它红的那条规则（B12）也是我自造的，已撤。

**裸粘稿会怎样（这条决定了改法）**：

| 怎么发 | 原稿句保住 | 自己加运镜 | 判红 |
|---|---|---|---|
| 只粘稿，一句话不说 | 21/31（**68%**） | 有 | 1 条 |
| 粘稿 + 「帮我换成 H3 能用的格式。内容一个字都别改，人物、动作、画面这些都照原样。」 | 27/31（**87%**） | 没有 | 0 条 |

所以不能只把路口扒掉 —— **得把「我是要转换、不是要重写」这句带过去**。

**改法**（`frontend/app/src/pages/prompt/index.vue`）：

- `send()` 里：写给 H3 + 没截图 + 不是在改上一稿 + 像一份现成稿（`isScript()`）
  → 在顾客那条消息**前面加一句** `SCRIPT_ASK`。**看得见、能删、不是偷偷加的**。
- `route()` 里删掉 `promptConvert` 那条分支；粘稿和一句话想法一样走 `/prompt/chat`，`duration` 传 0。
- `promptConvert` 的 import 去掉。**后端 `/api/prompt/convert` 接口留着**（`p18` 还在测它），
  但产品上已经走不到 —— 要删是另一件事。

**判据**：`tools/e2e/prompt-paste.js`（桩后端，不打真模型）——
①走的是 `chat` 不是 `convert` ②发出去的话里带着「内容一个字都别改」
③原稿正文一字不少一起发了 ④`duration=0`（不是写死 5）⑤顾客那条气泡里看得到这句 —— **五条全绿**。
回归：`prompt-leave` 4/4 · `prompt-history` 4/4 · `prompt-model` 5/5，全绿。

**还留着的**：修订（`/prompt/revise`）仍然传 `duration=5`。它改的是已有时间码的成品，
危害比转换小得多，**没动**（要改得先真机验，不能顺手改）。

**E2E 踩坑**：发送按钮用坐标点不到（`.send` 的中心点落在了别的层上，点了没反应），
`page.mouse.click` 和 `page.click('.send')` 都无效，**只能 `document.querySelector('.send').click()`**；
往 textarea 里塞长文本也不能直接改 `value`，得 `page.type`（真敲才进 uni 的双向绑定）。
