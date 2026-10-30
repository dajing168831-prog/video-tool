# 模型分离 L3：代码层（2026-10-26 起）

> 主人口径：「之前就叫你做好模型分离你说你都做到了，现在到处都还绑定在一起……
> 如果后期我们开发聚合平台这项目直接黄」
>
> 我承认：之前报的「模型分离」只做到 **L1 验收分离**（每家自己的尺子/测试文件），
> 我把 L1 当成了 L3 报给主人。本文记的是真正的 L3 —— **代码层**。

## 一、三层分离的定义（以后报「做完了」必须指明是哪一层）

| 层 | 内容 | 判据 |
|---|---|---|
| **L1 验收分离** | 每家自己的用例文件、自己的尺子；一轮只跑一家 | 跑 A 家的命令不会执行 B 家的断言 |
| **L2 规则分离** | 每家的规则各自回官方原文，不跨型号搬 | 每条规则能指到该家官方文档的行号 |
| **L3 代码分离** | 核心代码不认型号；加第 4 家 = 新建一个目录 + 登记一行 | `model_separation_check.py` 核心耦合数为 0（或只降不升） |

## 二、L3 的接口（已落地）

`app/services/models/base.py`

```python
Caps        # 能力参数：时长上下限/参考音频/提示词上限/分辨率表/asset:///画幅推断
ModelAdapter
  .caps          Caps
  .specs_for(m)  按具体型号取这家的参数表那一档
  .pic(n)        第 n 张参考图在提示词里怎么写（@图片1 / <Picture 1>）
  .vid()         参考视频怎么写
  .pre_compile() 编译前加工（H3 的中文自动翻英文挂这里，核心不知道）
  .gate()        出片前的可指认闸（每家读的描述字段都不一样）
  .compile()     编译成这家认的提示词
```

`app/services/models/__init__.py` —— 注册表：精确型号 → 注册的前缀 → 通道默认。
末尾 `from app.services.models import h3, volc20, volc25` 触发登记。

`app/services/models/volc20.py` / `volc25.py` / `h3.py` —— 每家一个文件，
声明 `PREFIXES` / `DEFAULT_ID`，`_compile` / `_gate` / `_pre_compile` 只调本家实现。

## 三、核心代码改成了什么（不再自己判断是哪家）

| 位置 | 改前 | 改后 |
|---|---|---|
| `edit_spec.compile_prompt` | 52 行 `if channel == "volc": _volc(...) else: _minimax(...)` | 3 行：`models.adapter_for(...).compile(...)` |
| `video_edit._prepare` 的闸 | `if ch == "volc": require_identifiable_volc25(...) else: require_identifiable_h3(...)` | `_ad.gate(...)` |
| 编译前加工 | 散在 `_prepare` 里判 H3 | `_ad.pre_compile(spec)` |
| `_spec_for` | `model_specs.minimax(m) if ch == "minimax" else model_specs.volc(m)` | `_ad.specs_for(m)` |
| 清晰度默认档 | `if ch == "volc": 按画幅推` | `_ad.caps.auto_res_from_frame` |
| 参考音频 | 判通道 | `_spec_for(...).get("ref_audio")` |
| 提示词上限 | 判通道 | `_spec_for(...).get("prompt_chars")` |
| `asset://` 拦截 | 判通道 | `_ad.caps.asset_id` |

## 四、怎么证明「只是搬家、行为没变」

`scripts/prompt_fingerprint.py` —— 对每家跑 **全部用例 × 14 组开关**，对每份提示词算 sha256：

```bash
python scripts/prompt_fingerprint.py --model volc20 --write D:/tmp/fp_before
# 改代码
python scripts/prompt_fingerprint.py --model volc20 --diff D:/tmp/fp_before
```

每一步重构后跑：**1471 条指纹逐字一致**（三家全部用例 + battery）。
指纹不一致 = 搬家把行为改了，当场回滚。

## 五、棘轮门禁

`scripts/model_separation_check.py` —— 扫核心文件（`video_edit.py` / `edit_spec.py` /
`clone_pipeline.py`）里的**家族分叉**和**型号字符串**，记录当前数，**只许降不许升**。

基线 `scripts/_model_separation_baseline.json`。谁在核心文件里新加一处 `if ch == "volc"`
立刻红。

```bash
python scripts/model_separation_check.py            # 对照基线
python scripts/model_separation_check.py --update   # 搬迁完成后更新
```

## 六、进度（2026-10-26）

| 步骤 | 内容 | 证据 | 三家回归 |
|---|---|---|---|
| Step1 | 注册表 + 三家适配器（薄封装） | 1471 条指纹逐字一致 | — |
| Step2 | `_prepare` 的 `pre_compile` / `gate` 走适配器 | 逐字一致 | 2.0 136/106/101 · 2.5 81/106/101 · H3 117/106/101 |
| Step3 | 删掉 `_compile_impl` 的 `if channel == "volc"`（52 行） | 逐字一致 | 同上 |
| Step4 | 能力分支下沉（`_spec_for` / 分辨率 / audio_ref / prompt_cap / asset） | 逐字一致 | 同上 + ruler 三家 sweep 破口 0 |
| Step5 | **H3 编译主体搬家**：`_LANG_TAG`/`_h3_line`/`_STYLES_EN`/`_KEEP_EN`/`_ucfirst`/`_minimax` → `h3_compile.py`（853 行） | 搬走的 823 非空行 **sha256 逐字一致** | H3 117/106/101 + ruler 13 组合红 0 |
| Step6 | **2.5 编译主体搬家**：`_volc_25`/`_scope_closure`/`_sd25_*` → `volc25_compile.py`（548 行） | 531 非空行 **sha256 逐字一致** | 2.5 81/106/101 + ruler 29 组合破口 0 |
| Step7 | **2.0 编译主体搬家**：`_volc`/`_SD20_*`/`_sd20_*`/兜底包 → `volc20_compile.py`（395 行） | 384 非空行 **sha256 逐字一致** | 2.0 136/106/101 + ruler 38 组合破口 0 |
| Step8 | `shot_plan_sentence` 三路拆分 → 各家 `_shot_plan()` | 三家回归 + 静态未定义名扫描 | 同上 |
| Step9 | `_pic`/`_vid` 走注册表（`Caps.pic_inline`）；`subject_gate` 的「建议切到哪个型号」改问注册表 | 同上 | 同上 |
| Step10 | `_model_for`（型号归属 + 配置默认）/ `pick_channel`（通道就绪与 auto 顺序）走注册表 | 回归 | 三家 |
| Step11 | 流水线能力开关：`shot_looks` / `align_8n1` / `drop_absent_people` / `boundary_pic` / `split_person_images`（**已无消费者**，2026-10-26 台账 D48 三家统一一人一张）/ `ensure_shot_source` | 回归 | 三家 |
| Step12 | **`adapter.submit(ctx)`**：两家请求形态整段下沉（火山公开 URL + `asset://` 入库 + 生成音轨；H3 本地直传） | 回归 + p12 行为判据 | 三家 |
| Step13 | `adapter.error_hint` / `ready` / `ready_error`：报错提示与「通道配好没」由各家自己说 | 回归 | 三家 |
| Step14 | **延长链整段下沉**：`extend_prompt` / `extend_submit` / `Caps.extend_seam` / `extend_transition` / `extend_ref_mode`（见九·补第 1 轮） | 回归 + p11 | 三家 |
| Step15 | 出片脏活：`display_name` / `boundary_by_edit_task` / `image_limits` / `video_limits` / `_gen_duration` 按型号（第 2 轮） | 回归 | 三家 |
| Step16 | 接口层：`resolutions` / `resolution_alias` / `regen_model_error` / `/health` 遍历注册表（第 3 轮） | 回归 + p11 E3 行为判据 | 三家 |

### Step12 的连带修复：`p12_check` 两条**文本判据**换成**行为判据**

原来：
```python
chk("火山请求体真的追加了参考视频", "ref_videos=([_public_url(style_clip, cid)]" in ve)
```
这是「`video_edit.py` 里有这句话」—— 代码一搬走就假红，而实际请求是对的。
现在：`mock` 掉 `ark.edit_video` / `minimax.reference_video`，真的调一次 `_submit`，
抓模型接口收到的 `ref_videos` 参数。多一条「两家都真的调到了自己的接口」。
🩸 判据要写「下一个使用者会怎么做」，不写「文件里有没有这句话」。

### Step10 的坑（我自己造的，当场修）

`_model_for` 我把「没指定型号 → 读**配置**默认」改成了「读**注册表**默认」，
而生产配置 `VT_ARK_VIDEO_EDIT_MODEL` 指的是 2.5 → `test_video_edit_logic` 和
`test_whole_wiring` 立刻红了 8 条（`2.5 → 30s: got=15.0`）。
修：`Caps.default_model_setting` 声明该通道的默认读哪个配置字段，核心 `getattr` 取。
🩸 **「默认值」属于配置，不属于代码** —— 换型号不该改代码。

### 现在的结构

| 文件 | 行数 | 管什么 |
|---|---|---|
| `app/services/edit_spec.py` | 1571 | **共用骨架**：规格归一化、槽位/标号顺序、`compile_context`、`_clauses`、`_keep_sentence`、`still_prompt` 等 |
| `app/services/models/volc20_compile.py` | 447 | 2.0 一段式 + 官方兜底包 + 2.0 台词 |
| `app/services/models/volc25_compile.py` | 609 | 2.5 五段模板 + 范围闭环 + 2.5 台词 |
| `app/services/models/h3_compile.py` | 905 | H3 六段式英文 + 台词 + 逐镜结构 |
| `app/services/models/base.py` | 73 | `Caps` / `ModelAdapter` 接口 |
| `app/services/models/__init__.py` | 69 | 注册表 |

核心耦合：**34 → 0**（七个核心文件里**一处厂商字面量都没有**）。
分三轮清的，见「九·补」。

### 尺子自己也要自证

`model_separation_check.py` 出过两次毛病，两次都是**尺子瞎了还报绿**：

1. 只排除 `#` 开头的行 → **docstring 里的说明文字被当成代码数**。改用 `tokenize` 判
   「这一行的 token 是否全是字符串/注释」，并加 `--selftest`。
2. 只认 `== "volc"` 这种**等号比较**、只扫 3 个文件 → `!= "minimax"`、`_min_for("minimax",…)`、
   `"volc": {…}`、`in ("volc","minimax")` 全数不到，报出假的「34 → 0」。
   口径改成「代码行里出现厂商字面量就算一处」，扫 7 个文件，
   `--selftest` 要求**五种写法都数得到 + 三类假阳性不数**（5/5）。

⇒ 换尺子之后必须**先跑 `--selftest`**，再拿它的结果下结论。

## 七、搬迁记录（**已全部完成**）

### 7.1 `video_edit.py` 的 17 处 —— **已清零**

| 原来 | 改成 |
|---|---|
| `_model_for` 判 `startswith("doubao")` | `models.family_of_model()` |
| `pick_channel` 判 `req == "volc"` / 通道顺序写死 | `adapters_by_family()` + `Caps.auto_prefer` |
| `_volc_ready()` 两处 if（第二个是死代码） | `adapter.ready()` + `ready_error()` |
| `model_specs.minimax/volc` 分派 | `_spec_for()` |
| ~~双图拆分判 `edit_task_param`~~ | `Caps.split_person_images` / `max_ref_images` —— **前者已无消费者**（2026-10-26 D48：三家一人一张）；`max_ref_images` 的数量上限 2026-10-26 起由 `minimax.check_limits()` 真执行 |
| 逐镜描述判 `ch == "minimax"` | `Caps.shot_looks` |
| 8n+1 判 `ch == "volc" and edit_task_param` | `Caps.align_8n1` |
| 按段摘缺席人物判 `ch == "minimax"` | `Caps.drop_absent_people` |
| 边界帧判 `ch == "minimax" or _is25` | `Caps.boundary_pic` |
| **两家各写一大段发请求** | **`adapter.submit(ctx)`** |
| 报错提示判 `ch == "volc"` | `adapter.error_hint()` |
| 补盘点判 `plan.get("ch") == "minimax"` | `Caps.ensure_shot_source` |

### 7.2 `edit_spec.py` —— **已清零**

| 原来 | 改成 |
|---|---|
| `pic()` / `vid()` 的 `if channel == "volc" else` | `Caps.pic_inline` / `vid_inline` |
| `shot_plan_sentence` 的 `if channel == "volc"` | 各家自己的 `_shot_plan()`（已删掉共用那份） |

### 7.3 物理搬迁（2026-10-26）

| 函数 | 行数 | 搬到 | 搬走后的证据 |
|---|---|---|---|
| `_minimax` + H3 专属表/工具 | 853 | `models/h3_compile.py` | 823 非空行 sha256 一致 |
| `_volc_25` + 2.5 台词/范围闭环 | 548 | `models/volc25_compile.py` | 531 非空行 sha256 一致 |
| `_volc`(2.0 主体) + 兜底包 + 2.0 台词 | 395 | `models/volc20_compile.py` | 384 非空行 sha256 一致 |

每搬一家都跑了：该家全量回归 + 另两家 `test_edit_spec`/`test_whole_wiring`（证明没被碰）。

### 7.4 还留在共用层的（**有理由**，不是欠账）

| 留在 `edit_spec.py` | 为什么 |
|---|---|
| `_sd20_person_tags` / `_sd20_orig_feat` | 共用 `_clauses` 在用（`_clauses` 是三家共用的句库） |
| `_h3_mmss` / `_en_clean` / `_en_only` / `_CJK_RE` | `h3_orig_locator`（video_edit 直接调）和共用工具在用 |
| `_person_attr` / `_duty_role` / `_PERSON_ATTR_*` | 2.5 和 H3 **两家都在用**，说的是同一件物理事实：**同一张参考图里要跟的五官、发型和服装**（不再分「大头照管五官 / 全身照管服装」—— 那套 2026-10-26 已删，台账 D48） |
| `h3_orig_locator` | `video_edit` 的可指认闸直接调，它内部用共用的称谓工具 |
| `_clauses` / `_keep_sentence` | 火山两家共用的句库（H3 不用） |

### 7.5 已知短板（要报给主人的）

1. **指纹覆盖严重不均**：`prompt_fingerprint` 的 1471 条里，2.0 占 **1387**、2.5 只有 **50**、
   H3 只有 **34**。说「1471 条逐字一致」时，实际只把 2.0 验得很厚。
   2.5 / H3 的强度来自各自的 `test_edit_spec`（81 / 117 项精确比字符串）和 `ruler_*_sweep`
   （29 / 13 组合），不是指纹。
2. **2.5 的双人称谓没有精确用例**：`test_edit_spec_sd25.py` 里搜不到「体型偏胖」「画面左侧」
   这类断言，所以「D38 改了称谓」这件事当时没有任何精确用例拦着，靠 `prompt_snapshot`
   才发现 —— 而快照又没在 D38 之后重新冻结，于是**基线从 D38 起就是过期的**，
   直到 2026-10-26 晚这轮才发现。已人审三条全文（方位优先 / 外观指认 / 衣服主人，符合 D38
   最终版）后 `--freeze`。

## 七·补、加第 4 家要做什么（这才是 L3 的验收标准）

1. 新建 `app/services/models/<新家>.py`，`register(ModelAdapter(...))`
2. 新建 `app/services/models/<新家>_compile.py`，写自己那份提示词
3. 在 `models/__init__.py` 末尾 import 一行

**核心七个文件（`video_edit` / `edit_spec` / `clone_pipeline` / `extend` /
`clone_jobs` / `api/clone` / `api/routes`）一个字都不用改。**
`model_separation_check.py` 的基线是 **0**，谁改动核心就会被拦下来。

### 这句话不是承诺，是**跑过的判据**：`scripts/model_registry_check.py`（**12/12**）

注册一个假的第 4 家 `future-1-2027`（**只在内存里存在几秒，`finally` 里注销**，
不连库不发请求不花钱，跑完就没），然后断言：

| # | 断言 |
|---|---|
| R1 | `adapter_for("future-1-2027")` 认得出它 |
| R2 | `family_of_model` 判得出归属，不回落成火山 |
| R3 | `pick_channel` 认这条通道 |
| R4 | `_model_for` 不跨族纠错 |
| R5 | 它的 `compile` 真的被调到（不是回落成别家） |
| R8 | 延长**接缝帧数**读它的 `Caps.extend_seam`（不是火山 6+1、也不是不裁） |
| R9 | 延长**时长**按它的参数表收口（不是别家的 15s） |
| R10 | **清晰度档位**读它的 `Caps.resolutions`（不是火山/H3 的枚举） |
| R11 | **档位别名映射**也读它的 `Caps` |
| R12 | 延长**提示词**由它自己出（核心不回落成别家句式） |
| R6 | 卸载后注册表恢复原状 |
| R7 | 核心文件里没有它的名字 |

🩸 **第一次跑是 5/7**：R4 红 —— `adapter_for` 的通道回落**写死了 minimax/volc**，
加第 4 家按通道取必错。修法：`Caps.is_channel_default` + 遍历注册表。
⇒ **「加一家不用改核心」在这条修之前是句空话**，修完才成立。
R7 那次的红是我自己的判据假阳性（`from __future__ import annotations`）。

🩸 **R8–R12 是第三轮才加的**：第一轮做出来时只有 7 条，而延长链/档位/媒体门槛
那几处照样写死厂商 —— 判据没覆盖到的地方，就等于没做。

## 八、不许做的事

- **不许为了降耦合数而合并/删除分支**：搬走和删掉是两件事，删掉会改行为。
- **不许把「我判它等价」当证据**：等价证据只有指纹逐字一致 + 三家回归。
- **不许一轮跑两家**：迁移期间任何验证命令只跑当前锁定的那一家。

## 九、🩸 更正：第七节那句「核心耦合 34 → 0」是**假绿**（2026-10-26 深夜）

主人问「现在我需要知道的东西又是什么没修好还是没分离好的？」——我重验了一遍尺子，发现：

**第一版 `model_separation_check.py` 只认「等号比较」**（`ch == "minimax"` 这类），
而且只扫 3 个文件。下面这些写法一处都数不到：

```python
if ch != "minimax":                          # 不等号
lo = int(_min_for("minimax", model))         # 当参数传
LABEL = {"volc": "...", "minimax": "..."}    # 当字典键
ch = channel if channel in ("volc", "minimax") else "volc"   # 成员判断
```

→ 于是报出「34 → 0」。**数字是真的，尺子是瞎的。**

### 修复后的真实口径（`--selftest` 5/5：五种写法都数得到）

「代码行里出现厂商字面量 / 厂商专属配置字段 / 具体型号」= 一处。文件从 3 个扩到 **7 个**
（把延长链和接口层算进来）。

| 文件 | 处数 | 加第 4 家会怎样 |
|---|---|---|
| `app/services/video_edit.py` | 9 | `_gen_duration` 按 **MiniMax** 收时长（第 4 家被错收）；`_IMAGE_LIMITS/_VIDEO_LIMITS.get(ch)` 返回 `None` → **媒体限制校验被静默跳过**；`_ensure_h3_shot_source` 的 `if ch != "minimax"` 会盖住 `Caps.ensure_shot_source` |
| `app/services/extend.py` | 5 | **最严重**：它自己有一份 `family()`，`else` 分支返回 `"volc"` → 第 4 家**静默走火山的延长提示词和请求路径** |
| `app/api/clone.py` | 5 | `model_specs.volc if ch=="volc" else minimax` → 第 4 家拿 MiniMax 的参数表；`regen_channel in ("volc","minimax")` → 第 4 家被拒 |
| `app/services/edit_spec.py` | 4 | `_RESOLUTIONS.get(ch, ())` → 空元组 → 清晰度**静默退回 auto**；`normalize` 的 `_RES_ALL` 是写死的合集 → 第 4 家的档位名被**静默丢掉** |
| `app/services/clone_jobs.py` | 2 | `regen_channel = "volc"` 写死 |
| `app/api/routes.py` | 2 | 通道就绪表写死两家（应问 `adapter.ready()`） |
| `app/services/clone_pipeline.py` | 1 | `channel in ("volc","minimax") else "volc"` → 第 4 家被当成火山 |

**合计 28 处。** 编译链（三家编译器）+ 适配器接口确实分开了；
**出片流水线的脏活、延长链、接口层、分辨率/媒体限制表 还认识到厂商名。**

基线已按新口径重建为 **28**（棘轮：只许降不许升）。

## 九·补、第三轮之后：28 → 0（2026-10-26 深夜，主人「开始跑」）

按「静默出错最狠 → 最容易」分三轮清完，每轮都是**一轮只跑一家**。

### 第 1 轮：`extend.py` 整条延长链（5 → 0）

| 原来 | 改成 |
|---|---|
| 自己写了一份 `family(model)`，`else` 返回 `"volc"` | 删掉，问 `models.adapter_for(model=model)` |
| 三份延长提示词写在核心里 | `adapter.extend_prompt(direction, content)`，各家自己写 |
| `if fam == "minimax": minimax.reference_video(...) else: ark.extend_video(...)` | `adapter.extend_submit(...)` |
| `normalize_ref`（火山像素下限）/ `clip_for_h3`（H3 截 15s）二选一写死 | `Caps.extend_ref_mode`（`pixel_floor` / `clip`），`prep_ref()` 按能力参数收 |
| `seam_frames` 里判 `edit_task_param` | `Caps.extend_seam`（2.0 = `(6,1)`，2.5/H3 = `(0,0)`） |
| `if fam != "volc"` 挡接缝转场 | `Caps.extend_transition` |
| `clamp_seconds` / `pick_resolution` 读 `model_specs.volc(model)` | 读 `adapter.specs_for(model)` |

### 第 2 轮：`video_edit.py` 出片脏活（9 → 0）

| 原来 | 改成 |
|---|---|
| `_gen_duration` 写死 `_min_for("minimax", …)` | 按型号问 `adapter.specs_for(model)` 的 `min_sec/max_sec` |
| `LABEL = {"volc": …, "minimax": …}` | `Caps.display_name` |
| `boundary_allowed` 写 `if channel != "volc"` | `Caps.boundary_by_edit_task` |
| `_IMAGE_LIMITS` / `_VIDEO_LIMITS` 两张按通道键的表 | `Caps.image_limits` / `video_limits`（数字回各家） |
| `_ensure_h3_shot_source` 内层 `if ch != "minimax"` | 改成 `_ensure_shot_source(..., wanted=Caps.ensure_shot_source)` |

🩸 补盘点那条原来是**两条独立判断**：调用方看 `Caps.ensure_shot_source`，
函数里又看通道名。加第 4 家时两条会打架 —— 现在只认能力参数。

### 第 3 轮：接口层（14 → 0）

| 原来 | 改成 |
|---|---|
| `edit_spec._RESOLUTIONS` / `_ALIAS` 按通道键 | `Caps.resolutions` / `resolution_alias`；`known_resolutions()` 由注册表拼 |
| `clone_pipeline` `channel in ("volc","minimax") else "volc"` | 认不出就落**默认通道**（问注册表） |
| `clone_jobs` 写死 `regen_channel = "volc"` | 按型号问 `adapter.caps.family`（🩸 顺手修掉 H3 延长被记成火山的 bug） |
| `clone_jobs` 默认型号读 `settings.ark_video_edit_model` | 读适配器声明的 `default_model_setting` |
| `api/clone.py` 三处各写一遍型号校验 | 合成 `regen_model_error()` 一处，问注册表 |
| `api/routes.py` `/health` 写死两家 + 各读各的 key | 遍历注册表调 `adapter.ready()` |

**结果：7 个核心文件 28 处 → 0 处，基线压到 0（硬地板）。**

### 判据自己也在这一轮被修了两条

1. `p11_check` 的 E3 原来 grep `known = {mid for items in model_specs.MODELS.values()` ——
   我重构掉这段，它立刻假红。**判据写「文件里有没有这句话」就是会这样烂掉。**
   改成真调 `clone.regen_model_error()` 五条成对探针（认得的放行 / 乱填的拒 /
   跨通道点名拒 / `auto` 放行）。
2. `p6_check` 写死一条真实 cid → 任务 TTL（3 天）清掉后整组 `FileNotFoundError`。
   改成每次挑最新、真有分镜的那条；一条都没有就**如实记 SKIP**
   （"5/5 通过，4 条 skipped（未验证，不算通过）"），不记成功。

### 这一轮的证据

| 证据 | 结果 |
|---|---|
| 三份提示词指纹（对 L3 开始前的基线 `D:/tmp/fp_base_20261026/`） | 2.0 **1387** · 2.5 **50** · H3 **34**，**全部逐字一致** |
| `model_registry_check`（假第 4 家） | **12/12**（新增 R8–R12：接缝 / 时长 / 档位 / 别名 / 延长提示词都由注册表驱动） |
| `model_separation_check --selftest` | **5/5**（等号/不等号/入参/字典键/成员判断五种写法 + 三类假阳性） |
| 静态未定义名扫描（闭包感知，先用已知坏样本验过） | 改过的 **12/12** 文件全部有名可解 |
| 三家 rulers | 2.0 38 组合破口 0 · 2.5 29 组合破口 0 · H3 13 组合红 0 |
