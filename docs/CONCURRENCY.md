# 并发、限流与容量（2026-10-21 更新）

> **结论先行：唯一的硬瓶颈是本机海外出口 ≈ 1 Mbps。**
> 国内 4 平台跑 190 Mbps，随便加人；海外 3 平台在 1 Mbps 下，一个 20MB 视频要 3 分钟，
> 两路并行就互相拖死。**海外平台能不能做，取决于服务器带宽，不取决于代码。**

> 2026-10-21 变更：YouTube 已下线，本文去掉住宅 IP / 代理相关章节。

---

## 一、今天实测（本机 = 香港阿里云 8.218.238.87）

### 1.1 出口带宽

| 目标 | 速度 | 换算 |
|---|---|---|
| Cloudflare（海外） | 120,087 B/s | **0.96 Mbps** |
| npmmirror（国内） | 8,897,879 B/s | 71 Mbps |
| B站 CDN（国内） | 23,793,477 B/s | **190 Mbps** |

**同一个脚本、同一分钟测的** → 瓶颈是这台机器的国际出口，不是某个源站。

### 1.2 真实业务下载（服务端 → 源站）

| 平台 | 文件 | 耗时 | 速度 |
|---|---|---|---|
| TikTok | 21.4 MB | **179 s** | 119,831 B/s（0.96 Mbps） |
| X | 3.4 MB | 32 s | 106,191 B/s（0.85 Mbps） |
| Instagram | 63.8 KB | 13 s | 4,903 B/s |
| B站 | 42.7 MB | **1.8 s** | 23.8 MB/s（190 Mbps） |

### 1.3 三路并发（同时点三个）

```
Bilibili: 42.7MB / 1.8s  = 190 Mbps   ← 国内链路不受影响
X:        3.4MB / 32s    = 0.85 Mbps  ← 单路就吃满出口
IG:       63.8KB / 13s   = 0.04 Mbps  ← 被挤到几乎没有
```

**结论：海外出口是共享的**，并发不会加速，只会互相分摊。两个海外任务同时跑 = 两个都慢。

### 1.4 换算成用户感受

| 视频大小 | 1 Mbps 下 | 10 Mbps | 50 Mbps |
|---|---|---|---|
| 5 MB（短视频） | 40 s | 4 s | 0.8 s |
| 20 MB（普通） | **160 s** | 16 s | 3.2 s |
| 100 MB（长视频） | 13 分钟 | 80 s | 16 s |

---

## 二、上游源码调研（一手依据，可复核）

> 之前这一节只有三行结论、没来源。下面是拉源码查到的确切位置。

### 2.1 MeTube（`alexta69/metube`，yt-dlp 官方推荐 Web UI）

| 事实 | 依据 |
|---|---|
| 并发默认 **3** | `app/main.py:110` → `'MAX_CONCURRENT_DOWNLOADS': '3'` |
| 用信号量控制 | `app/ytdl.py:1406` → `asyncio.Semaphore(self.config.MAX_CONCURRENT_DOWNLOADS)` |
| 线程池 = 2N+2 | `app/ytdl.py:1411` |
| 其余排队 | `README.md:57` |

**但要注意：它没有 HTTP 限流、没有队列上限、没有 URL 去重**（全仓库 grep 过）。
它是「自用 Web UI」定位，不解决多租户问题。**不能拿它当我们的限流参考。**

### 2.2 cobalt（`imputnet/cobalt`，公开实例，最接近我们的场景）

| 事实 | 依据 |
|---|---|
| 三层限流：session / api / tunnel | `api/src/core/api.js:68-112` |
| 默认窗口 60 s、次数 20 | `api/src/core/env.js:75-76` |
| **tunnel（流式下载）单独限：60 s / 40 次** | `api/src/core/env.js:78-79` |
| 超限返回 **429** | `api/src/core/api.js:75`、`:108` |
| 自动带 `RateLimit-*` 响应头 | `api/src/core/api.js:85`（`standardHeaders: 'draft-6'`） |
| 限流 key = **IP 哈希** | `api/src/core/api.js:80` → `hashHmac(getIP(req),'rate')` |
| 反代后取真实 IP | `api/src/core/api.js:112` → `trust proxy: ['loopback','uniqulocal']` |
| 流令牌 21 位、只接受本机访问 | `api/src/core/itunnel.js:8-15` |
| 流令牌有效期默认 **90 s** | `api/src/core/env.js:90` |

**两条直接可抄的设计**：
1. **流式下载端点必须单独限流**——它吃带宽，普通 API 不吃
2. **下载链接用短期令牌**（cobalt 90 秒），不用永久 URL

### 2.3 yt-dlp（本机 `d:\venvs\video-tool\...\yt_dlp\options.py`）

| 参数 | 默认 | 行号 |
|---|---|---|
| `--concurrent-fragments` | **1** | `options.py:1011-1014` |
| `--limit-rate` | 无（不限速） | `options.py:1016-1019` |
| `--retries` | **10** | `options.py:1023-1025` |

**`--limit-rate` 是我们最该用的**：给每个 yt-dlp 进程限速，避免单个任务吃满 1 Mbps 出口。

---

## 三、现有代码的 6 个并发缺陷

| # | 问题 | 后果 |
|---|---|---|
| 1 | **同步下载**：`/api/file/{token}/video` 在 HTTP 请求里等下载完成 | 海外平台 180s，小程序/浏览器早超时了 |
| 2 | **没有队列**：N 人同时点 = N 个下载抢 1 Mbps | 全员变慢（实测已发生） |
| 3 | **没有去重**：同视频 10 人点 = 下 10 次 | 带宽浪费 10 倍 |
| 4 | **没有取消**：客户端断开，下载继续跑 | 白烧带宽 |
| 5 | **没有进度**：前端只能转圈 | 3 分钟空白，用户以为死了 |
| 6 | **没有背压**：队列满了还继续接单 | 雪崩 |

---

## 四、目标架构

```
POST /api/parse
  → 解析元数据（国内 1-2s / 海外 2-4s）
  → 查重：同源 URL 已有任务则复用 token
  → 入队（上限 N）
  → 立即返回 {token, status: "queued"|"downloading"|"ready", position}

GET /api/task/{token}
  → {status, progress, speed, eta, error}

GET /api/file/{token}/video
  → ready：直接给文件（Range）
  → 未就绪：202 + 进度
```

组件：

- **下载队列 + 固定 worker 池**（MeTube 的 3 是对的起点）
- **同源去重**（key = 规范化源 URL）— 两者都没做，但我们必须做（显式落盘）
- **按 IP 限流**（cobalt 模式：60s / 20 次，429 + `RateLimit-*`）
- **流式端点单独限流**（cobalt tunnel 模式）
- **断连取消**（`request.is_disconnected()`）
- **磁盘配额 + TTL**（已有 TTL，缺容量上限）
- **yt-dlp `--limit-rate`**（按 worker 数分配出口带宽）

---

## 五、起步配置

```env
VT_MAX_CONCURRENT_DOWNLOADS=3     # 全局下载并发（MeTube 默认值）
VT_YTDLP_LIMIT_RATE=300K          # 每进程限速，3 路 ≈ 0.9 Mbps，正好吃满
VT_PER_IP_CONCURRENCY=3
VT_QUEUE_MAX=50                   # 超限 429
VT_RATE_LIMIT_PER_MIN=20          # 对齐 cobalt：60s / 20 次
VT_STREAM_RATE_LIMIT_PER_MIN=40   # 流式端点单独一档（cobalt tunnel）
VT_TASK_TTL=7200
VT_DISK_QUOTA=50GB
```

---

## 六、服务器的带宽要求（选型依据）

**国内 4 平台**：任何 10 Mbps 以上的机器都够（实测 190 Mbps，只用了零头）。

**海外 3 平台**，按「用户从点解析到能播放」的目标体验倒推：

| 目标 | 20MB 视频要多久 | 需要带宽 |
|---|---|---|
| 能忍 | 30 s | ≥ 6 Mbps |
| 舒服 | 10 s | ≥ 16 Mbps |
| 秒开 | 3 s | ≥ 55 Mbps |

按并发算（边下边转模式）：**每路 720p 用户 ≈ 2.5 Mbps**。

| 同时在线 | 需要海外带宽 |
|---|---|
| 5 人 | 13 Mbps |
| 20 人 | 50 Mbps |
| 50 人 | 125 Mbps |

**结论：海外平台要么买 ≥50 Mbps 的香港/新加坡机器，要么先只上国内 4 平台。**

---

## 七、多端差异（未实测，标注清楚）

| 端 | 已知约束 | 来源 |
|---|---|---|
| H5 | 无特殊限制，受浏览器内存约束（大文件 fetch 成 blob） | — |
| 微信小程序 | `downloadFile` 有单次大小上限、`request` 默认超时 60s、域名白名单 | **未实测**，需开发者工具验 |
| 抖音小程序 | 同上，另有平台审核限制 | **未实测** |

> 这三项我没找到可直接引用的一手官方原文（微信文档站是 SPA，抓不到正文），
> **不写具体数字**，等小程序实测时补。

---

## 八、还没验证的

1. 换一台大带宽服务器后，海外下载是否真能跑到线路极限（取决于机房到 TikTok/IG/X 的互联质量）
2. 香港机房 IP 对 IG/X 的**并发容忍度**（同时 3 路会不会被风控）
3. 微信/抖音小程序的下载大小与超时具体数值
4. 边下边转（streaming proxy）在当前架构下的改造成本
