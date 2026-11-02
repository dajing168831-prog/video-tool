> ## Documentation Index
> Fetch the complete documentation index at: https://platform.minimaxi.com/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# 本地运行与自托管部署 MiniMax 开放模型

> 为 MiniMax-M3、MiniMax-M2.7、MiniMax Music 3 和 MiniMax H3 选择本地运行或自托管路径。

MiniMax 提供语言、多模态理解、音乐生成和音视频生成模型的开放权重。本指南汇总官方部署基线，并链接到每个模型的端到端部署流程。

> [!NOTE]
>
> 本栏目以服务器或集群上的**自托管部署**为主，H3 页面还提供 ComfyUI 本地工作流路径。你需要自行准备硬件、运行推理环境、按需配置访问控制并实施内容安全措施。需要托管服务、弹性扩缩容或 MiniMax 平台完整能力时，请使用 [MiniMax API](https://platform.minimaxi.com/docs/guides/quickstart-preparation.md)。

## 选择模型

| 模型 | 任务 | 模型原生能力 | 本部署指南覆盖范围 | 参考配置 | 状态 |
| :- | :- | :- | :- | :- | :- |
| [MiniMax-M3](https://platform.minimaxi.com/docs/guides/local-deploy-m3.md) | Agent、Coding、长上下文和多模态理解 | 文本、图片和视频输入，文本输出 | SGLang OpenAI 兼容 Chat Completions；以模型页的已验证能力表为准 | 8 × B200、MXFP8 | Experimental |
| [MiniMax-M2.7](https://platform.minimaxi.com/docs/guides/local-deploy-m2-7.md) | Agent、软件工程和现有 M2.7 工作流 | 文本输入和输出、思考、工具调用 | SGLang OpenAI 兼容 Chat Completions | 4 × 高显存 NVIDIA GPU、TP 4；官方尚未发布统一最低显存 | Preview |
| [MiniMax Music 3](https://platform.minimaxi.com/docs/guides/local-deploy-music-3.md) | 根据歌词和音乐描述生成歌曲 | 歌词和音乐描述输入，立体声音频输出 | SGLang-Omni 非流式 Speech API | 1 × H200 参考样例；其他容量未验证 | Preview |
| [MiniMax H3](https://platform.minimaxi.com/docs/guides/local-deploy-h3.md) | 文本、关键帧或参考素材驱动的音视频生成 | 文本、图片、视频和音频条件，音视频输出 | ComfyUI 原生 T2V/I2V/R2V 工作流与 SGLang H3-Base API；不包含 H3-Context-IR 和完整 2K Workflow | ComfyUI `0.30.0+`，最低显存未公布；SGLang 参考配置为 8 × B200、Ulysses 8 | ComfyUI 原生支持 / SGLang Experimental |

状态表示本文档部署基线的成熟度，不表示模型本身的产品生命周期：

* **Stable**：使用固定版本的运行时，并提供可复现的参考命令。
* **Preview**：已有官方部署路径，但上游安装方式或部分能力仍在变化。
* **Experimental**：依赖预发布运行时，或部分硬件组合尚未完成端到端验证。

> [!WARNING]
>
> “开放权重”不代表所有模型采用相同许可证。部署、分发或商用前，请阅读对应模型页链接的完整 License 和 Acceptable Use Policy。推理框架支持不会额外授予模型使用权。

## 自托管部署的边界

自托管后，模型权重、输入数据和推理服务运行在你控制的基础设施上，同时也意味着：

* 你负责容量规划、扩缩容、监控、故障恢复和升级。
* 快速开始默认只监听本机；对外提供服务前，需要配置鉴权、TLS、网络隔离和远程媒体访问限制。
* 开放权重不包含 MiniMax 平台的托管文件、缓存、内容安全和平台专属工作流。
* 社区量化、转换权重和其他推理框架不属于本栏目已验证范围，除非模型页明确列出。

## 部署前准备

1. 阅读目标模型的 License、开放范围和已验证能力。
2. 按模型页准备指定的 GPU、主机内存、磁盘、驱动和 CUDA 环境。
3. 固定模型 revision、推理框架版本或镜像 digest，不要在生产环境跟随 `main`、`dev` 或 `latest` 漂移。
4. 准备 Hugging Face 缓存或离线权重；使用中国大陆镜像时，以模型页列出的官方入口为准。
5. 先完成健康检查和最小请求，再进行量化、并行、卸载或吞吐优化。

> [!TIP]
>
> 对应模型页提供 MiniMax 文档采用的参考基线。SGLang Cookbook 配置器可生成更多硬件、量化和拓扑组合，但生成结果可能处于 Unverified 状态；不要把其他硬件的参数直接套用到当前环境。

## 支持与验证范围

每个模型页都会标明模型 revision、运行时版本、参考硬件、已验证能力和最后验证日期。缺少官方实测的数据会明确写为“未提供”或“未验证”，不使用相邻模型或社区结果估算。
