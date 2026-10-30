# 移交说明（给接手的工程师）

> 交接日期：2026-10-21
> 项目：视频解析工具（去水印 / 提取文案 / 提取音频）
> 当前范围：**国内 4 平台**（抖音 / 快手 / 小红书 / B站）+ H5 / 微信小程序 / 抖音小程序三端

---

## 一、交接包里有什么

```
video-tool/
├── backend/          # FastAPI 后端（1243 行）
├── frontend/app/     # uni-app 三端工程（Vue3 + Vite）
├── vendor/
│   └── parse-video-py/   # 抖音/快手/B站解析库（PyPI 上没有，必须随包分发）
├── docs/
│   ├── DELIVERY.md           # 跑法 + 验收步骤
│   ├── CONCURRENCY.md        # 并发缺陷、带宽实测、上限架构
│   ├── OVERSEAS-RESEARCH.md  # 海外平台调研（已暂停，留档）
│   └── HANDOVER.md           # 本文件
├── scripts/e2e_check.py      # 后端端到端验收（8 项）
├── tools/e2e/                # H5 自动化验收（puppeteer-core）
└── requirements.txt
```

**不含**：`node_modules/`、`dist/`、`data/`（运行期产物）、Python venv。

---

## 二、环境搭建（从零）

### 2.1 依赖

| 依赖 | 版本 | 说明 |
|---|---|---|
| Python | 3.12 | |
| ffmpeg | 任意较新版本 | **必须**，抽音频用；`VT_FFMPEG` 指过去，或放 PATH |
| Node.js | 18+ | 前端构建 |

### 2.2 后端

```bash
cd video-tool
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

> ⚠️ `parse-video-py` 不在 PyPI 上，`requirements.txt` 里用 `-e ./vendor/parse-video-py`
> 装的是**包内自带的源码**。别删 `vendor/`。

### 2.3 前端

```bash
cd frontend/app
npm install
```

---

## 三、跑起来

### 后端

```bash
cd video-tool/backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8911 --log-level warning
```

健康检查：`curl http://127.0.0.1:8911/api/health` → `{"code":200,"biz_code":0,...}`

配置项全走环境变量（见 `backend/app/core/config.py`），常用：

| 变量 | 默认 | 用途 |
|---|---|---|
| `VT_ENABLED_PLATFORMS` | `douyin,kuaishou,xiaohongshu,bilibili,tiktok` | 开放哪些平台 |
| `VT_FFMPEG` | 空（走 PATH） | ffmpeg 路径 |
| `VT_TEMP_TTL` | 7200 | 临时文件保留秒数 |
| `VT_MAX_VIDEO_BYTES` | 500MB | 单文件上限 |

### H5

```bash
cd frontend/app
npm run dev:h5      # http://127.0.0.1:5180
npm run build:h5    # 产物 dist/build/h5
```

### 小程序

```bash
npm run dev:mp-weixin    # 或 build:mp-weixin  → dist/dev(或 build)/mp-weixin
npm run dev:mp-toutiao
```

开发者工具导入产物目录 → **详情 → 本地设置 → 勾选「不校验合法域名」**。

### 接口地址

`frontend/app/src/config.js` 一处改全端：

```js
export const API_BASE = 'http://127.0.0.1:8911'   // 真机调试改局域网 IP，上线改 https 域名
export const ENABLED_PLATFORMS = ['douyin', 'kuaishou', 'xiaohongshu', 'bilibili']
```

⚠️ 前端和后端的 `ENABLED_PLATFORMS` / `VT_ENABLED_PLATFORMS` **必须同步改**。

---

## 四、当前状态

### 已验证 ✅

| 项 | 怎么验的 |
|---|---|
| 抖音 / 快手 / 小红书 / B站 解析 | 实测通过（小红书需 App 分享链接，带 `xsec_token`） |
| 视频代理播放 + Range | H5 实测 `readyState=4`，Range 返回 206 |
| 文案复制（标题+正文+话题） | H5 实测剪贴板内容正确 |
| 音频提取（AAC/m4a） | 后端 e2e 8/8 通过 |
| 封面 / 图集代理 | 实测（B站封面 403 问题已修） |
| 历史页 → 详情回看 | H5 实测 |
| 图集分支渲染 | 构造样本实测 |
| 三端编译 | `build:h5` / `build:mp-weixin` / `build:mp-toutiao` 全 DONE |
| **交付包自检** | 解压到全新目录 → `pip install -e ./vendor/parse-video-py` 成功 → `import app.main` 成功 → `GET /api/health` 返回 200，7 个解析器全部注册 |

### 未验证 ⚠️

| 项 | 为什么没验 |
|---|---|
| **微信 / 抖音小程序真机** | 开发机没装开发者工具，需要接手方装 |
| **真实下载落盘（H5）** | headless Chrome 对任何下载都返回 canceled（连 1KB 同源文件也是），是测试环境限制 |
| **小程序的下载大小/超时上限** | 官方文档站是 SPA，没抓到可引用的原文，需实测 |
| 并发行为 | 见 CONCURRENCY.md，尚未做队列改造 |

---

## 五、待办（按优先级）

### P0 — 上线前必须

1. **小程序实测**：导入产物，跑一遍解析→播放→保存→复制文案
2. **并发改造**：队列 + 固定 worker、同源去重、按 IP 限流、进度接口
   - 现状：`/api/file/{token}/video` 是**同步等待下载完成**，多人同时请求会互相抢带宽
   - 具体方案与参考实现见 `docs/CONCURRENCY.md`
3. **部署**：Nginx 反代 443 → 8911、HTTPS 证书、小程序域名白名单

### P1 — 上线后

4. 登录（微信 code2session / 抖音 / H5 手机号）
5. 计费（次数包 / 会员）—— 新增表统一 `vt_` 前缀
6. 历史云端同步、过期清理策略

### 暂停中

7. 海外平台（TikTok / Instagram / X）：代码保留、已关闸。卡在带宽（本机实测海外出口仅 ~1 Mbps），
   重启方案见 `docs/OVERSEAS-RESEARCH.md`

---

## 六、必须甲方提供的

| 项 | 用途 |
|---|---|
| 已备案域名（建议用子域名，如 `api.xxx.com`） | 小程序强制的 HTTPS + 备案域名 |
| 微信小程序 AppID | 填 `frontend/app/src/manifest.json` 的 `mp-weixin.appid` |
| 抖音小程序 AppID | 填 `manifest.json` 的 `mp-toutiao.appid` |
| 服务器 | 国内平台不需要代理；香港/境内均可，国内 4 平台带宽要求很低（实测 190 Mbps 只用零头） |

---

## 七、已知坑（都踩过，别再踩）

1. **小红书必须用 App「分享 → 复制链接」**，裸链接缺 `xsec_token` 会失败，且链接有时效
2. **CDN Referer 按真实域名配**：B站图片在 `hdslb.com`（不含 "bilibili"）、快手在 `kwimgs.com`
   （不含 "kuaishou"）。匹配不到就不带 Referer，**不要兜底成抖音**
3. **`MediaInfo.is_video` 是 property**，`asdict()` 取不到，落盘 `meta.json` 时要手动补，
   否则刷新/从历史进来视频会被当成图集
4. **抖音 slidesinfo 高频会返回空**（表现为 `KeyError: 'videoInfoRes'`），已加指数退避 +
   同链接 5 分钟缓存
5. **封面/图集必须走服务器代理**（`/api/file/{token}/cover`、`/image/{i}`）：
   平台 CDN 有防盗链，小程序也过不了域名白名单
6. **H5 跨域下载不能用 `<a download>`**（浏览器会忽略），要 fetch → blob → objectURL，
   且 revoke 不能早于 60 秒
7. `backend/app/services/media.py:21` 有个**本机剪映的 ffmpeg 绝对路径兜底**，
   接手机器上没有这个路径，请设 `VT_FFMPEG` 或确保 ffmpeg 在 PATH

---

## 八、验收怎么做

### 后端（自动）

```bash
cd scripts
python e2e_check.py                       # 默认抖音样本
python e2e_check.py --text "<分享文案>"    # 指定链接
```

判据 8 项：服务健康 / 解析成功 / 文案非空 / 视频可下载 / 支持 Range / 音频可提取 / 视频有效 / 音频有效。

### H5（自动，需要本机 Chrome）

```bash
cd tools/e2e
npm install puppeteer-core
node flow.js "http://127.0.0.1:5180" "https://www.bilibili.com/video/BV1SknF6KE5g"
```

### 小程序（人工）

导入开发者工具，按 DELIVERY.md 第三节的 7 步走一遍。
