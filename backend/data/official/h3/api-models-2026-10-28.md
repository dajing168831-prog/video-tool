# MiniMax 视频生成 V2 · 模型档位（官方原文快照）

> 抓取日期：**2026-10-28**
> 来源：`https://platform.minimaxi.com/docs/api-reference/video-generation-v2-create`
> 抓取方式：直连官方页面（SPA），去标签后逐字摘录 model / resolution / duration 三段。
> 🩸 为什么要这份：2026-10-22 抓的平台文档（`platform-docs.txt`）里 **0 次**出现
> `MiniMax-H3-Highspeed` / `MiniMax-H3-Lite` —— 这两档是之后新增的。旧快照不能证明现状。

## model（enum，必填）

> 模型名称。当前可用值：`MiniMax-H3`、`MiniMax-H3-Highspeed`、`MiniMax-H3-Lite`、`MiniMax-H3-Max`。

| 模型 | 官方说明（逐字） |
|---|---|
| `MiniMax-H3` | 适合高品质视频创作的版本。支持文生视频、图生视频（首帧 / 尾帧）与多模态参考生视频；分辨率 768P / 2K，时长 4~15 秒。 |
| `MiniMax-H3-Highspeed` | 兼顾生成质量与速度的版本。支持文生视频、图生视频（首帧 / 尾帧）与多模态参考生视频（参考图 / 参考视频 / 参考音频）；分辨率 768P，不支持 2K；时长 4~15 秒。 |
| `MiniMax-H3-Lite` | 轻量版本。支持文生视频、图生视频（首帧 / 尾帧）与多模态参考生视频（参考图 / 参考视频 / 参考音频）；分辨率 480P / 768P，不支持 2K；时长 4~15 秒。 |
| `MiniMax-H3-Max` | 极速生成版本。支持文生视频、图生视频（首帧 / 尾帧）与多模态参考生视频（参考图 / 参考视频 / 参考音频）；分辨率 480P / 768P，不支持 2K；时长 5~15 秒。 |

## resolution（enum，必填）

> 视频分辨率。不同模型支持的档位不同：
> · `MiniMax-H3`：768P、2K
> · `MiniMax-H3-Highspeed`：768P（不支持 2K）
> · `MiniMax-H3-Lite`：480P、768P（默认 768P，不支持 2K）
> · `MiniMax-H3-Max`：480P、768P（默认 768P，不支持 2K）
> 可用选项：480P, 768P, 2K

## duration（enum<integer>，必填）

> 生成视频时长（秒），必选，整数。不同模型可用值不同：
> · `MiniMax-H3` / `MiniMax-H3-Highspeed` / `MiniMax-H3-Lite`：4~15 秒
> · `MiniMax-H3-Max`：5~15 秒

## 档位速查（由上面三段推出，不加料）

| 模型 | 分辨率 | 默认 | 时长 |
|---|---|---|---|
| `MiniMax-H3` | 768P / 2K | 768P | 4–15s |
| `MiniMax-H3-Highspeed` | 768P | 768P | 4–15s |
| `MiniMax-H3-Lite` | 480P / 768P | 768P | 4–15s |
| `MiniMax-H3-Max` | 480P / 768P | 768P | 5–15s |
