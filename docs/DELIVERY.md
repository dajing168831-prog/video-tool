# 视频解析工具 — 交付说明

> ℹ️ 本文是**开发机视角**的说明，里面的绝对路径（`C:/tmp/...`、`/d/venvs/...`）只在原开发机有效。
> **接手部署请看 `HANDOVER.md`**，那里是从零搭建的步骤。

> **当前开放范围：抖音 / 快手 / 小红书 / B站（国内 4 平台）**
> 海外 3 平台（TikTok / Instagram / X）代码保留但已关闸 —— 实测本机海外出口只有 ~1 Mbps，
> 一个 20MB 视频要 3 分钟，必须换大带宽机器再开。详见 CONCURRENCY.md。

> 状态：H5 全链路已跑通（解析 → 播放 → 复制文案 → 下载）；微信/抖音小程序已编译出产物，待开发者工具实测。
> 日期：2026-10-21

## 一、目录

```
C:/tmp/video-tool/
├── backend/                 # FastAPI 后端（解析 + 文件代理 + 抽音频）
│   ├── app/parsers/         # 7 个平台解析器（YouTube 已下线）
│   ├── app/services/        # 下载 / 抽音频 / 临时存储
│   └── data/temp/<token>/   # 每个任务一个目录：meta.json / video.mp4 / audio.m4a / cover.img
├── frontend/app/            # uni-app（Vue3 + Vite）一套代码编三端
│   └── dist/build/          # mp-weixin / mp-toutiao 产物
├── tools/e2e/               # 自动化验收脚本（puppeteer-core + 本机 Chrome）
└── vendor/                  # 本地依赖（sing-box 桥接配置、BGUtil POT 源码）
```

## 二、跑起来

### 后端

```bash
cd C:/tmp/video-tool/backend
/d/venvs/video-tool/Scripts/python.exe -m uvicorn app.main:app \
  --host 0.0.0.0 --port 8911 --log-level warning
```

- 监听 `0.0.0.0` 是为了真机调试（手机连 `192.168.1.10:8911`）。
- **不需要任何代理**：国内 4 平台 + TikTok（2026-10-23 开放，内部测试）。
- **平台开关**：`VT_ENABLED_PLATFORMS`（逗号分隔），默认 `douyin,kuaishou,xiaohongshu,bilibili,tiktok`。
  再开 instagram/twitter 改成 `...,instagram,twitter` 即可，
  前端同步改 `src/config.js` 的 `ENABLED_PLATFORMS`（两边必须一致）。
- 健康检查：`GET /api/health` → `{"code":200,"biz_code":0,...}`

### H5

```bash
cd C:/tmp/video-tool/frontend/app
npm install          # 首次
npm run dev:h5       # 开发，http://127.0.0.1:5180
npm run build:h5     # 产物在 dist/build/h5
```

### 微信小程序

```bash
npm run dev:mp-weixin    # 或 build:mp-weixin
```

微信开发者工具 → 导入 `dist/dev/mp-weixin`（或 `dist/build/mp-weixin`）→ **详情 → 本地设置 → 勾选「不校验合法域名、HTTPS 证书」**。
`src/manifest.json` 里 `mp-weixin.appid` 现在是 `touristappid`，换成真实 AppID 即可。

### 抖音小程序

```bash
npm run dev:mp-toutiao   # 或 build:mp-toutiao
```

抖音开发者工具 → 导入 `dist/dev/mp-toutiao` → 同样关掉域名校验。
`src/manifest.json` 里 `mp-toutiao.appid` 为空，需要主人的 AppID。

### 接口地址

`src/config.js` 一处改全端：

```js
export const API_BASE = 'http://127.0.0.1:8911'   // H5/工具
// 真机调试改成 'http://192.168.1.10:8911'
// 上线改成 'https://你的域名'
```

## 三、验收步骤（三端各跑一遍）

1. 首页点「粘贴」→ 输入框出现链接
2. 点「开始解析」→ 1~5 秒跳到结果页
3. 视频能播（封面先出来，点播放）
4. 点「复制文案」→ 提示已复制，粘贴出来是标题 + 正文 + 话题
5. 点「保存视频」→ 直接下载 mp4 / 存进相册
6. 点「保存音频」→ 下载 m4a
7. 返回首页 → 底部「历史」→ 列表有封面/标题/时间 → 点开能回到详情

自动化验收（H5）：

```bash
cd C:/tmp/video-tool/tools/e2e
node flow.js "http://127.0.0.1:5180" "https://www.bilibili.com/video/BV1SknF6KE5g"
```

## 四、已知限制

| 项 | 说明 |
|---|---|
| 抖音高频失败 | 抖音 slidesinfo 接口对短时重复请求会返回空，已加 3 次指数退避 + 5 分钟同链接缓存；仍失败就等十几秒再试 |
| 小红书 | 必须用 App「分享 → 复制链接」，裸链接缺 `xsec_token` 会失败；链接有时效 |
| YouTube | **已下线**（按业务决策）。它按 IP 类别判定，机房 IP 必须配住宅出口，成本不划算 |
| TikTok / IG / X | 代码保留但**已关闸**。机房 IP 下能通（2026-10-21 实测），但本机海外出口仅 ~1 Mbps，20MB 视频要 3 分钟，换大带宽机器前不开放 |
| Instagram 静音视频 | 无音轨的视频点「保存音频」会提示「该视频没有音轨」 |
| 小程序域名 | 上线前必须：备案域名 + HTTPS + 微信/抖音后台配 `request`/`downloadFile`/`video` 合法域名 |
| 并发 | 当前无队列，同一台机器同时解析多个大视频会互相抢带宽（见 CONCURRENCY.md） |

## 五、下一批（未开工）

登录（微信 code2session / 抖音 / H5 手机号）→ 计费（次数包 / 会员，表统一 `vt_` 前缀）→ 历史云端同步 → 并发队列与去重 → 进度接口。
