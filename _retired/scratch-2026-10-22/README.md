# 已下线的「从零写」功能（2026-10-22）

**为什么下线**：主人对照自家大鲸ai 的现有功能清单后确认——「从零写」（台词 + 画面 → 整条成片）
与面板的「生成面板」＋「商业广告分镜 7 步」重复，没有差异价值。

**这个目录里有什么**：
- `scratch.py` —— 后端服务（切镜 / 配音 / 逐镜生成 / 拼接 / 质检）
- `scratch.vue` —— 前端页面
- `p8_check.py` —— 验收脚本（当时 16/16 全绿，全程零模型调用）

**从项目里摘掉的其他位置**（按当时的写法恢复即可）：

1. `backend/app/api/clone.py` —— `class ScratchIn` + `POST /clone/scratch/plan` + `POST /clone/scratch`
2. `backend/app/services/clone_jobs.py` —— `submit_scratch()` + `_scratch()`
3. `backend/app/services/clone_store.py` —— `public()` 里的 `"kind"` 字段（原为 `task.get("kind") or "clone"`）
4. `frontend/app/src/pages.json` —— `pages/clone/scratch` 页面注册
5. `frontend/app/src/pages/clone/index.vue` —— 「从零写」入口卡 + `scratch()` 方法
6. `frontend/app/src/api/request.js` —— `cloneScratchPlan()` / `cloneScratch()`
7. `frontend/app/src/pages/history/history.vue` —— 「再写一条」分支 + `openScratch()`
8. `frontend/app/src/pages/clone/progress.vue` —— `LABEL.video = '生成画面'`

**要恢复**：把三个文件放回原位，再按上面 8 条加回引用；`p8_check.py` 应当仍是 16/16。
