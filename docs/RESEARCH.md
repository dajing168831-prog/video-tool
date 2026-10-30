# 技术调研（P0 · 2026-10-20）

> 目的：在写任何业务代码前，先确认「八家平台到底能不能解析、用谁的轮子、许可证能不能商用」。
> 本文件是选型的唯一依据，后续实现以此为准。

---

## 一、能力矩阵（本机实测）

样本来源：yt-dlp 各提取器内置 `_TESTS` 中的真实链接（开发者维护，最接近真实可用性）。

| 平台 | yt-dlp 裸跑 | 失败原因 | 结论 |
|---|---|---|---|
| B站 | ✅ 通过 | — | 直接可用，视频/音频/描述齐全 |
| 抖音 | ❌ | `Fresh cookies (not necessarily logged in) are needed` | 需要身份池 |
| TikTok | ❌ | `Unexpected response from webpage request` | 需要身份池/签名 |
| YouTube | ❌ | `Sign in to confirm you're not a bot` | **机房 IP 级封锁**，见「YouTube 专项」 |
| 小红书 | ❌ | `No video formats found` | 需要专门解析器 |
| Twitter | ⚠️ 样本无视频 | 测试推文本身不含视频，非解析器缺陷 | 待换样本复测 |
| 快手 | ❌ | yt-dlp 无提取器 | 必须用外部引擎 |

**核心结论：八家里 yt-dlp 裸跑只有 B站能过。自研签名不是可行路线。**

### 第三方 API 实测（抖音）

`POST https://video.zacao.top/api/parse` 不带 Key：

```json
{"code":200,"data":{"platform":"抖音","author":{"nickname":"杨超越"},
"source_video_url":"https://v26-webf.douyinvod.com/...","cover_url":"..."}}
```

✅ 抖音链路真实可用，可作为兜底适配器。免费额度：每 IP 30 次/小时。

### 本机自建引擎实测（2026-10-20 晚）

**最终引擎：`wujunwei928/parse-video-py`（MIT，纯 Python，零数据库）**

| 平台 | 结果 | 证据 |
|---|---|---|
| 抖音 | ✅ 通过 | 作者「杨超越」、标题「#杨超越 小小水手带你去远航❤️」、无水印视频地址 |
| 快手 | ✅ 通过 | 作者「小土豆」、标题「#快手三坑种草机招募 …」、无水印视频+封面（**首次偶发失败，重跑即成功，需重试机制**） |
| B站 | ✅ 通过 | 标题「《绝区零》菲欧妮EP \| 1% Battery Girl 低电量女孩」、视频地址 |
| 小红书 | ✅ 通过（自研 SSR 解析器） | 见下方「小红书专项」 |
| Twitter/X | ⏳ 待测 | 缺真实样例 |
| TikTok | ✅ 通过（多源 provider） | 详见下节 |
| YouTube | ❌ | 机房 IP 被登录层封锁（见 YouTube 专项） |
| Instagram | ✅ 通过 | yt-dlp，reel/p 两类样本，视频下载 + 后端代理 + Range 全过（样本本身无音轨，音频接口正确返回 400） |
| Twitter/X | ✅ 通过 | yt-dlp，端到端 **8/8**（4.8MB 视频 / 1分51秒，音频 935KB） |

### TikTok 专项调研（2026-10-20）

**结论：不需要 cookies，也不需要付费。**

| 尝试 | 结果 |
|---|---|
| yt-dlp 直连 | ❌ 需 cookies |
| 本机直接抓 tiktok.com 页面 | ❌ 被降级重定向（响应头 `x-redirect-reason: www.tiktok.com_allow`），返回 86KB 空壳，无 `playAddr` |
| f2（Apache-2.0，2.7k 星） | ❌ 安装后 CLI 崩溃（依赖冲突） |
| TikTok-Api（MIT，6.7k 星） | ❌ 需要 `ms_token`，本质是 cookies |
| videodl（3.1k 星） | ⚠️ 许可证不明，不可商用 |
| **tikwm 公开接口** | ✅ **拿到无水印流 + 音频直链 + 标题 + 作者 + 时长** |

**实现方式**：`backend/app/parsers/tiktok_provider.py`
- 多源注册表 `SOURCES`，主源失败自动切备用
- 免费源的真实风险：限流、随时关停、商用无保障 → 必须监控失败率，并保留替换为付费源的接口

**验收**：TikTok 全链路 8/8（视频 21.4MB / 2:30，音频 614KB / 2:30）

### 小红书专项调研（2026-10-20）

**结论：不需要登录 cookies，也不需要付费。自研 SSR 解析，全链路 8/8。**

| 尝试 | 结果 |
|---|---|
| 裸链接 `/explore/<id>`（无 xsec_token） | ❌ 302 → `/404?...error_code=300031`，`noteDetailMap` 0 条 |
| 文档里的示例 token（占位/过期） | ❌ 同上，300031 |
| **App 分享短链 `xhslink.com/o/xxx`** | ✅ 302 后带完整参数，`noteDetailMap` 1 条 |
| **App 分享短链 `xhslink.cn/o/xxx`** | ✅ 同上 |
| 移动 UA | ❌ 返回 SPA 空壳（`noteData` 空，无 noteDetailMap） |
| **PC UA** | ✅ SSR 注入完整笔记数据 |
| CDN 直链下载（默认 UA） | ❌ **403**，xhscdn 防盗链 |
| CDN 直链 + `Referer: https://www.xiaohongshu.com/` | ✅ 38.9MB 正常下载 |

**实现**：`backend/app/parsers/xhs_provider.py`
- 短链必须**原样保留全部 query 参数**（`xsec_token` / `xsec_source` / `source` / `xhsshare` / `app_platform`），302 后由平台自动补齐
- **PC UA 优先**，移动 UA 仅兜底（实测移动端 SSR 无数据）
- 数据路径：`__INITIAL_STATE__.note.firstNoteId` → `noteDetailMap[id].note`
- JSON 需清洗：`undefined→null`、`new Map→{}`、`new Set→[]`、`new Date→null`
- 字段：`title` / `desc` / `tagList[].name` / `user.nickname` / `imageList[].urlDefault` / `video.media.stream.h264[0].masterUrl`
- xhscdn 直链给的是 `http://`，**必须升级 https**，否则浏览器混合内容拦截
- 支持图集（`type=normal`，无 video 只有 imageList）

**产品侧注意**
- `xsec_token` **有时效**（平台机制），用户复制后要尽快解析；过期只能重新复制
- 裸链路/网页地址栏复制的长链大多缺 token → 前端文案要明确引导「用 App 分享→复制链接」
- 可选环境变量 `VT_XHS_COOKIE`（`a1=...; webId=...`，**匿名访客标识，不是登录账号**）用于高频场景提成功率

### YouTube 专项调研（2026-10-20）

**结论（实测）：本机出口 IP 被 YouTube 登录层封锁，免费方案已穷尽，必须换出口或走第三方。**

本机出口：`8.218.238.87`（香港 / 阿里云机房 IP）——机房 IP 是 YouTube 的重点风控对象。

| 尝试 | 结果 |
|---|---|
| yt-dlp 默认 | ❌ LOGIN_REQUIRED |
| yt-dlp `player_client` = tv / web / web_safari / mweb / ios / android / android_vr / web_embedded / tv_simply / web_creator / tv_embedded | ❌ 全部 LOGIN_REQUIRED |
| yt-dlp `--js-runtimes node`（启用 JS 挑战） | ❌ 无改善 |
| **BGUtil PO Token 服务**（GPL-3.0，已在本机编译运行，`127.0.0.1:4416`） | 服务本身 ✅ 能生成 token；**但播放仍 ❌**——官方说明「PO Token 不能绕过 IP 级登录限制，机房 IP 常见」 |
| Piped 公共实例（15 个） | 仅 2 个在线（private.coffee / ducks.party），**画质上限 360p**，且同样 10 个视频里只有 1 个能解析 |
| Invidious 公共实例（7 个） | ❌ 全部 403/超时/空响应 |
| Cobalt 公共实例（8 个） | ❌ 全部下线或要求 JWT 鉴权 |
| 第三方聚合 `video.zacao.top` | ❌ 502「链接不可访问」 |

**对照实验**：`dQw4w9WgXcQ` 稳定可用（10 条样本里唯一 1 条），其余全部 LOGIN_REQUIRED —— 不是限流，是这个特定视频恰好没被拦。

**免费路已穷尽（2026-10-20 全部实测，二轮补测）**

| 尝试 | 结果 |
|---|---|
| 本机 IPv6 出口 | 无 IPv6 |
| Invidious 9 + Piped 15 公共实例（用被封锁视频做判据） | 0 可用 |
| TLS 指纹伪装 `--impersonate chrome/safari/firefox` | ❌ 全部 LOGIN_REQUIRED |
| 直连 InnerTube `/youtubei/v1/player`（WEB / WEB_EMBEDDED / TVHTML5_SIMPLY / ANDROID_VR / IOS） | ❌ ERROR / LOGIN_REQUIRED |
| 抓 embed 页 `ytInitialPlayerResponse` | 页面不含（仅 SPA 壳） |
| **ytagent（MIT，宣称在阿里云香港机房 IP 成功）** 的同款配置 `visionos,android_vr` | ❌ 仍 LOGIN_REQUIRED，**该宣称在本机环境不成立** |
| 手工 visitorData + BGutil PO Token 绑定（`web.gvs` / `web.player` / `mweb.gvs`） | ❌ 全部被拒 |
| **免费公开代理池 7457 条随机抽 400 条实测** | **0/400 命中** |
| Cloudflare WARP | 多方资料：WARP 出口同属机房段，无效（未安装验证） |

**判定：这不是代码问题，是 IP 类别问题。除住宅出口外无技术解。**

### ✅ 最终解法（2026-10-20 实测，主人提供马来西亚节点）

主人自带一条 Shadowsocks 节点：`74.82.222.153:14835`（吉隆坡，Light Cloud / AS395793）。

用本机 NekoBox 自带的 sing-box 核心起独立本地 SOCKS5（`127.0.0.1:10888`，不干扰现有 xray），实测：

| 视频 | 结果 |
|---|---|
| Despacito | ✅ |
| Me at the zoo | ✅ |
| 3Blue1Brown 神经网络 | ✅ |
| Gangnam Style | ✅ |

出口 IP `14.192.51.123`（吉隆坡）。**YouTube 不认它是机房段，4/4 全通。**

→ **不需要买住宅 IP，YouTube 方案成本归零。**

配置文件：`vendor/ss/config.json`（含节点密钥，勿外传）
启动：`nekobox_core.exe run -c config.json`

**⚠️ 但本机不能当生产服务器**：直连 / 香港节点 / 马来节点三条路径的海外带宽完全相同（105 KB/s），说明瓶颈是**本机国际出口被限速到 0.84Mbps**，与节点无关。服务必须部署到服务器上。

**付费方案真实价格（已核实页面，不是搜索摘要）**

| 方案 | 价格 | 流量 | 备注 |
|---|---|---|---|
| **IPWO 静态住宅** | **¥35 / IP / 30天** | **不限流量** | 195+ 国家，HTTP(S)/SOCKS5，国内站 |
| **RapidProxy 静态住宅** | **$5 / IP / 月** | **不限流量** | 页面明确「Start free trial」 |
| IPPeak 静态 ISP | ≈$3.6/IP/月 | 不限流量 | 需核实 |
| 按 GB 动态住宅 | $0.65–7/GB | 按量 | **不适合视频**：1000 条 1080p ≈ 200GB |

**结论：按 GB 计费对视频是灾难，必须选「不限流量的静态住宅 IP」**，¥35/月即封顶。

**零成本验证渠道（无需信用卡）**
- RapidProxy 页面明确「Start free trial」
- 1024Proxy 注册送约 200MB（CDK 兑换）
- Novproxy 新用户 300–500MB
- 各家客服均可单独申请测试 IP

**拿试用 IP 后**：`scripts/test_yt_proxy.py --proxy "http://user:pass@host:port"` 三条判据全过再买。

### 链式中转（2026-10-20 实测本机网络）

本机现状：**没有直连**。直连和走本地 Xray（`127.0.0.1:10808`）出口 IP 完全相同（`8.218.238.87`，阿里云香港），说明这台机的流量在网络层已被强制中转。

加入住宅 IP 后的链路：

```
后端进程 → 现有中转（香港）→ 住宅代理网关 → YouTube
           ↑ 已存在、零改动        ↑ 新增一跳，yt-dlp --proxy 自动走
```

两条必须守住的约束：
1. **解析和下载必须同一出口 IP**（YouTube 流地址绑定请求 IP）——已实现：proxy 存在 meta 里，下载复用
2. **中转带宽翻倍**（视频流量进出各过一次中转）——需确认中转机月流量额度

若未来生产环境在国内、住宅网关不可直连，用本地链式代理兜底，代码零改动：
```bash
gost -L socks5://127.0.0.1:1080 -F socks5://127.0.0.1:10808 -F http://user:pass@住宅网关:port
# 然后 VT_YOUTUBE_PROXY=socks5://127.0.0.1:1080
```

**代码已就绪（无需等采购）**
- `VT_YOUTUBE_PROXY` / `VT_PROXY` 环境变量，格式 `http://user:pass@host:port` 或 `socks5://...`
- 解析和下载走**同一出口**（YouTube 流地址绑定请求 IP，换 IP 必 403）
- 采购前先用 `scripts/test_yt_proxy.py --proxy "..."` 测三条判据，通了再买

**要用 YouTube，只有三条路**
1. **换出口 IP**：住宅代理（付费）或借一台境外 VPS 做出口；PO Token 服务已就位，换 IP 后大概率直接可用
2. **付费第三方解析 API**：对方自带住宅代理，按量计费
3. **暂时不支持**：产品文案明确标「YouTube 暂不可用」

### Instagram / Twitter 引擎（2026-10-20）

统一用 `backend/app/parsers/ytdlp_provider.py`（子进程调 yt-dlp）：
- **解析**：`yt-dlp -J` 拿元数据（`-J` 输出 JSON，自建字段映射）
- **下载**：`media.ytdlp_download()` 用 yt-dlp 完成分轨合并 + 平台签名，产出 mp4
- meta 里记 `extra.engine = "ytdlp"` 和 `extra.source_url`，`/api/file/...` 按引擎分流

| 平台 | 结果 |
|---|---|
| Instagram | ✅ reel/p 可解析；视频无音轨时音频接口返回 400「该视频没有音轨」而不是 500 |
| Twitter/X | ✅ 端到端 8/8 |
| YouTube | ❌ 机房 IP 封锁（解析层已做中文提示） |

**已落地但当前用不上**：`vendor/bgutil-src`（PO Token 服务，Node，`node build/main.js --host 127.0.0.1 --port 4416`）+ `bgutil-ytdlp-pot-provider==2.0.2` 插件。换出口 IP 后无需改代码。

**被否掉的方案**：`Evil0ctal/Douyin_TikTok_Download_API`
- 依赖 **TimescaleDB**，而 TimescaleDB 官方不支持 Windows
- 迁移脚本、保留策略、维护 worker 深度依赖，改造成本高
- 结论：**只能在 Linux/Docker 上跑，本机开发不可用**（交付时仍可作为生产端备选）

---

## 二、GitHub 选型（按许可证可用性排序）

| 项目 | 星 | 语言 | 许可证 | 覆盖 | 可用性 |
|---|---|---|---|---|---|
| Evil0ctal/Douyin_TikTok_Download_API | 20.8k | Python | **Apache-2.0** | 抖音 + TikTok | ✅ 可商用、可自部署 |
| putyy/res-downloader | 20.7k | Go | **Apache-2.0** | 视频号/抖音/快手/小红书/直播 | ✅ 可商用 |
| wujunwei928/parse-video | 1.1k | Go | **MIT** | 抖音/快手/微视/西瓜等 | ✅ 可商用 |
| JoeanAmier/XHS-Downloader | 13k | Python | GPL-3.0 | 小红书 | ⚠️ 有传染性，只能独立进程调用 |
| CharlesPikachu/videodl | 3.1k | Python | NOASSERTION | 抖音/快手/小红书/B站/TikTok/YouTube | ⚠️ 只能参考，不能直接用 |
| 3441293738/creatorhub | 2.4k | Python | 无 | 抖音/小红书/快手 | ❌ 不可商用 |
| yt-dlp | — | Python | Unlicense（公有领域） | B站/YouTube/IG/Twitter | ✅ B站已验证 |

### 选定组合

```
抖音 / TikTok  → Evil0ctal（Apache-2.0）   [自建引擎]
快手            → wujunwei928/parse-video（MIT）或第三方 API 兜底
B站             → yt-dlp（已验证）
YouTube / IG / Twitter → yt-dlp + cookies
小红书          → XHS-Downloader 独立进程（GPL 隔离）或第三方 API
```

---

## 三、Evil0ctal 部署事实（已核实源码与 compose）

- 版本 5.1.5，Python ≥3.12 <3.14
- 依赖：FastAPI + SQLAlchemy async + **PostgreSQL（pg17）** + **Redis**
- 自动获取抖音身份（cookies）需要 `browser-rpc` 边车（CloakBrowser + Chromium，约 300MB/页）
- **不装 browser-rpc 也可以**：手工导入 cookies 到身份池
- CLI `dtk` 直接连 Postgres，不经过 REST API
- **不支持 SQLite**，无轻量模式

### 本机验证结论

- `wreq`（抖音签名依赖）在 Windows 有 wheel，✅ 装得上
- 因此**不需要 Docker**，用本机 Python + 本地 PostgreSQL + 本地 Redis 即可跑
- C 盘仅剩 4G → 所有服务与依赖一律装 D 盘

---

## 四、风险清单

| 风险 | 影响 | 对策 |
|---|---|---|
| 平台改签名 | 解析当天失效 | 健康哨兵 + 自动降级第三方 API |
| cookies 过期 | 单平台失效 | 身份池 + 定期校验 |
| 带宽成本 | 视频经服务器转发 | 网页端给直链，小程序端才走代理 |
| 第三方 API 涨价/停服 | 兜底失效 | 只做兜底，主链路自建 |
| GPL 传染 | 商用合规 | GPL 项目只做独立进程，不链代码 |
