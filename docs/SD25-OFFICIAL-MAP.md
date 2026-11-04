# Doubao Seedance 2.5 · 官方规则索引（每条规则 → 出处 → 我们代码）

> 配套 [SD25-SOURCES-MINDMAP.md](SD25-SOURCES-MINDMAP.md)（资料地图）使用。
> 本文只回答一件事：**我们代码里的每一条 2.5 规则，官方原文在哪、代码在哪、现在什么状态。**
>
> 🩸 规矩：本文每一行的「官方」都必须能回源逐字找到；自己的推断标「工程判断」，不许包装成官方。
> 官方正文在 `backend/data/official/sd25/`（`pull-2026-11-03/` = 2026-11-03 全量重拉版）。

---

## 一、型号与能力

| 规则 | 官方 | 代码 | 状态 |
|---|---|---|---|
| 2.5 只有一个模型 ID `doubao-seedance-2-5-260628` | `pull-2026-11-03/model-list.md:633`、`models.md`（主版本 260628，更新 2026-10-08） | [model_specs.py](../backend/app/services/model_specs.py) `SPECS` `volc25` 段（`:236` `edit_task_param=True`） | ✅ |
| 时长 4–30s；编辑任务只能 `-1` | `tutorial.md:36`、`:66`、`:2930`；`api-create.md:392`、`:509` | [ark.py](../backend/app/services/ark.py) `edit_body` `:529`（`spec["edit_duration"]`）、`model_specs.edit_duration` | ✅ |
| 编辑/延长/首尾帧 `ratio` 必须 `adaptive` | `tutorial.md:36`、`api-create.md:392`、`:469` | 同上 `edit_ratio` | ✅ |
| 编辑任务待编辑视频 `[4,30]s` | `tutorial.md:38`、`api-create.md:509` | `video_edit.fit_spans` / 分段逻辑；**实际发送时长**按 `caps.video_limits["max_sec"]=30.2` 收口（`_gen_spans` 的借尾巴条件） | ✅ 2026-11-03 修：官方写 30，**接口实测卡 30.2**（任务 `116928ec` 的 30.433s 段被 400：`content[1] ... must be ≤ 30.2 ... in r2v`）。段长 30 + 借 0.5 尾巴 → 8n+1 对齐成 913 帧 = 30.433s → 撞线 |
| 显式 `edit`/`extend` 前置校验；`auto` 走异步报错 | `tutorial.md:92` / `:100`；`api-create.md:381` | `ark.edit_body` 恒发 `omni_reference_task_type="edit"` | ✅ |
| 分辨率 480p/720p/1080p（无 4k）；1080p = 10bit H.265 | `api-create.md:411`、`tutorial.md:2858` | `model_specs` resolutions | ✅ |
| 输出按 **24fps** 计算；`duration` 返回 = 帧数/24 向下取整 | `api-create.md:502`、`:524` | 归一化以源 fps 重编码；未按 24 推算 | ⚠️ 工程判断 |
| `seed` 2.5 **不支持** | `api-create.md:591` | 未发送（正确） | ✅ |
| `output_format=mov` 更适合编辑/延长 | `api-create.md:561`、`:571`；`sd25-pe` 同口径 | `ark.edit_body` 对 2.5 恒发 `mov` | ✅ |
| 参考图 1–30 张、宽高比 [0.4,2.5]、边长 [300,6000]、≤30MB | `api-create.md:177` | `models/volc_common.py` `IMAGE_LIMITS` | ✅ |
| 参考视频 0–10、音频 0–10、总音频 ≤30s | `api-create.md:25`、`:328` | 上传/组装侧 | 待核 |
| 个人账号 180 RPM / 并发 3 | `tutorial.md:3094` | 无排队/限流器 | ❌ 未做 |
| 任务 ID 7 天、视频 URL 24 小时 | `tutorial.md:3087` | `_load_tid` 断点续取 | ✅ |

---

## 二、提示词（写词规则）

| 规则 | 官方 | 代码 | 状态 |
|---|---|---|---|
| 编辑提示词必须含「编辑视频/增加/加上/删除/去掉/修改/替换/改成」之一 | `tutorial.md:67` | `volc25_compile._volc_25` 句式「把…替换为/换成」 | ✅（含「替换」） |
| 编辑任务用**外观称谓**指人，不用字母标号 | `prompt-guide.md:1209`（「视频中深色衣服的男子的服饰替换为 @图片 2」） | `volc25_compile._disambiguate_25` / `_who_label_25` | ✅ |
| 多人必须**按首次出场顺序**上传素材并同步编号 | `prompt-guide.md:429`（常见问题·角色对应错误） | 目前按**用户勾选顺序**排槽位 | ❌ **不一致** |
| 不自动加兜底包（画质/稳定/水印/双胞胎） | `skill-sd25-pe` 原则 8；`docs/OPEN-DEFECTS.md` C2 | `model_specs.auto_constraint=False` | ✅ |
| 复杂任务（多项参考+编辑）要拆步 | `prompt-guide.md:738` | 一次提交所有改动 | ❌ 未拆 |
| 编辑输出短 0.33–0.4s；正解 = 输入帧数 8n+1 | `prompt-guide.md:695`、`:703`；`api-create.md:494` | `_EXTRA=0.5` + `_TAIL_TOL=0.45`（兜底，非官方法） | ⚠️ 兜底可用，官方解未做 |

---

## 三、合规（真人脸 / 版权）

| 规则 | 官方 | 代码 | 状态 |
|---|---|---|---|
| 2.5 不收含真人人脸的参考图/视频 | `api-create.md:119`；`portrait-asset.md` | 出片前 `ark_ingest` 入库换 `asset://` | ✅ |
| 三种合规通道：信任模型产物 / 虚拟人像库 / 本人授权 | `portrait-asset.md`；`avatar-library.md`；`real-person-asset.md` | `ark_assets.py` / `ark_ingest.py` | ✅ 前两条；本人授权需控制面 AK/SK |
| 真人拦截错误码 = `InputImageSensitiveContentDetected.PrivacyInformation` | `error-codes.md:43` / `:44` | `video_edit._volc_hint` | ✅ |

---

## 四、错误与恢复

| 规则 | 官方 | 代码 | 状态 |
|---|---|---|---|
| `InvalidParameter.TaskTypeConstraint` = 参数与判定任务类型不兼容 | `error-codes.md:52` | `error_report` 分类 | 待核 |
| `InvalidParameter.TaskTypeMismatch` = 你说 edit、模型判 reference | `error-codes.md:53` | 同上 | 待核 |
| 429 = 限流（个人 180 RPM / 并发 3） | `tutorial.md:3094`、`error-codes.md` | `retry.py` 退避；无排队 | ⚠️ |
| 任务 ID 复用，进程重启不重提交 | — | `ark._load_tid` / `_save_tid` | ✅ |

---

## 五、样片（Draft）模式

| 事实 | 官方 | 我们 |
|---|---|---|
| `draft=true` 先出 480p 样片，按 480p 计费 | `tutorial.md:2711`、`:2726`；`api-create.md:621` | 未接 |
| 正式片基于 Draft 任务 ID 生成，**仅支持 1080p** | `tutorial.md:2776`、`:2781` | 未接 |
| 复用模型/提示词/素材/种子/音频/宽高比/时长 | `tutorial.md:2723`、`:2789` | — |

> 这是官方自带的「先验后出」，对"稳定"是最现成的手段；但**正式片只能 1080p**，
> 与我们"480p 廉价试片"的现状冲突，属于产品取舍，需主人拍板。

---

## 六、引用约定

- 引用官方一律写 **`文件:行号`**，文件用相对 `backend/data/official/sd25/` 的路径（或 `sd25-guide:` 缩写）。
- 旧副本 `guide.md` / `api-create-task.md` 仍保留：工程注释里已大量引用它们的行号，
  **行号以旧副本为准**；内容要看新版。
- 不确定「官方有没有写」时：先 `grep` 两份（新旧），再 `llms.txt` 穷举页清单，最后才下结论。
