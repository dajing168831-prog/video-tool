# H3 复刻执行链（2026-11-03 归档）

**主人原话**：「复刻爆款这边不打算再接入 H3 模型的了，该清理就清理吧」
（前一句是「复刻爆款H3下架……不要去动的H3模型优化提示词」）

## 为什么只归档这一半

H3 的代码分成两条互不相干的线：

| 线 | 入口 | 这次怎么办 |
|---|---|---|
| **复刻出片** | `/clone/*` → `models/h3.py` 适配器 | **归档（本目录）** |
| **提示词优化** | `/prompt/*` → `h3_base` / `h3_skill` / `h3_direct` | **原地保留，一行没动** |

判断依据是依赖关系，不是文件名：`app/api/prompt.py` 只 import
`h3_base` / `h3_base_compile` / `h3_common` / `h3_ref` / `h3_skill` / `h3_direct` /
`h3_convert_route`（全部留在 `app/services/`），**不 import 本目录任何一个文件**。

## 本目录的文件与依赖

```
h3_ir.py            H3-Context-IR 改写器（出片时逐段产提示词）
   └─ minimax.py    H3 API 客户端（reference_video / context_ir / upload_file）

h3_agent.py         逐段指令 agent（预览/对照用）；读 clone_brief
h3_compile.py       六段式编译器（Ref2VA 改片）
   └─ 被 ruler_h3.py（复刻的提示词尺子）用来校验

p46_check.py        复刻逐段指令判据（打 h3_agent）
p58_check.py        「先出一段」真跑（打 minimax.reference_video + h3_agent.cached）
ruler_h3.py         Ref2VA 六段式尺子（23 条 E1–E23）
snap_cases_h3.py    prompt_snapshot 的 H3 用例
test_edit_spec_h3.py  edit_spec 的 H3 自检
test_h3_shot_source.py  H3 逐镜画面描述来源判据
```

⚠️ **这些文件现在 import 不了**（它们互相依赖，且 `models/h3.py` 已经改成墓碑，
不再调用它们）。归档件是「留个全尸，将来要接回来照原样搬」，不是可运行的备份。

## 接回来要改哪些

1. 把本目录六个执行链模块 `git mv` 回原位：
   `h3_ir.py` / `h3_agent.py` / `minimax.py` → `app/services/`；
   `h3_compile.py` → `app/services/models/`。
2. 还原 `app/services/models/h3.py`（`git log -- app/services/models/h3.py`
   找 2026-11-03 之前的版本）。
3. `app/services/model_specs.py` 的 `MODELS` 把 `"minimax"` 四档填回去。
4. `scripts/` 的映射表把 `h3` 加回去：`check_all.RULER` / `prompt_snapshot.CASE_MODULES` /
   `test_edit_spec.MODELS` / `ruler_atoms.MODELS` / `recheck_real_prompts._MOD`。
5. `app/services/h3_convert_route.py` 的 `GUIDES["ref"]["ruler"]` 填回 `"ruler_h3"`。
6. 前端 `diagnose.vue` 的三大分支（谁在说话 / 通道提示 / 中文名映射）。

## 不要做什么

- **不要**顺手把这些模块里的规则搬进 `h3_base` / `h3_ref`（那是另一种模式，方向相反：
  改片 vs 创作）。`MODEL-SEPARATION.md` 有原始口径。
- **不要**因为归档就在 `model_specs.SPECS` 里删四档参数表 —— 提示词优化要查它。
