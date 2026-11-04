# 模型列表

> 全部文档的索引见 [llms.txt](https://ark.volcengine.com/llms.txt)；在任一文档页面地址后追加 `.md` 可获取该页的 Markdown 版本。

方舟提供多种模型供您使用。您可浏览所有模型，比较它们的能力。

<span id="b4dabf9a"></span>
# 模型推荐

**[Doubao Seedance 2.5](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seedance-2-5)**
豆包高性能视频生成模型
4~30 秒视频生成，全模态参考输入

**[Doubao Seed Evolving](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-evolving)**
Seed 最新 Coding&Agent 模型
周级迭代，持续进化 Coding 与 Agent 能力

**[Doubao Seedream 5.0 pro](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seedream-5-0-pro)**
最新图像创作模型
编辑更可控、生产更落地、效果更自然

<span id="32e9e053"></span>
# 文本生成能力

教程: [文本生成](/docs/text-generation)、[深度思考](/docs/deep-thinking) |   API: [Responses API](/docs/create-model-responses-api)、[Chat API](/docs/chat-api)、[Messages API](/docs/messages-api)

> **注意**
>
> 本章节列出方舟平台所有支持文本生成能力的大语言模型。其中带"深度思考"能力标签的模型，默认调用即启用深度思考；如需仅执行文本生成任务，可通过调用参数关闭深度思考（Chat API 传入 `thinking.type=disabled`，Responses API 传入 `reasoning.effort=minimal`）后使用，参数详情参见[深度思考](/docs/deep-thinking)。未带"深度思考"能力标签的模型（如 doubao-seed-character-251128）本身不支持深度思考，直接调用即可。

<span id="5fd8d8b1"></span>
## 推荐模型

|模型 ID (Model ID) |**能力支持** |**长度限制（token）** |限流     | \
| | | |> 非刚性保障，受平台负载/调用方式影响，详见 [文档](/docs/traffic-burst-handling-best-practices#263ca129) |
|---|---|---|---|
|[doubao-seed-evolving](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-evolving) |深度思考 |上下文窗口: 1024k |最大 RPM: 500 | \
|> 快速迭代模型 |文本生成 |最大输入: 1024k |最大 TPM: 1000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 256k | | \
| |GUI 任务处理 |最大思维链: 256k | | \
| |工具调用 | | | \
| |结构化输出 | | |
|[doubao-seed-2-1-pro-260915](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-1-pro) |深度思考 |上下文窗口: 1024k |最大 RPM: 500 | \
| |文本生成 |最大输入: 1024k |最大 TPM: 1000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 256k | | \
| |GUI 任务处理 |最大思维链: 256k | | \
| |工具调用 | | | \
| |结构化输出 | | |
|[doubao-seed-2-1-lite-260915](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-1-lite) |深度思考 |上下文窗口: 1024k |最大 RPM: 30000 | \
| |文本生成 |最大输入: 1024k |最大 TPM: 5000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 256k | | \
| |GUI 任务处理 |最大思维链: 256k | | \
| |工具调用 | | | \
| |结构化输出 | | |
|[doubao-seed-2-1-turbo-260628](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-1-turbo) |深度思考 |上下文窗口: 256k |最大 RPM: 500 | \
| |文本生成 |最大输入: 256k |最大 TPM: 1000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 256k | | \
| |GUI 任务处理 |最大思维链: 256k | | \
| |工具调用 | | | \
| |结构化输出 | | |

<span id="af1b9bf4"></span>
## **其他模型**

|模型 ID (Model ID) |**能力支持** |**长度限制（token）** |限流     | \
| | | |> 非刚性保障，受平台负载/调用方式影响，详见 [文档](/docs/traffic-burst-handling-best-practices#263ca129) |
|---|---|---|---|
|[doubao-seed-2-1-pro-260628](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-1-pro) |深度思考 |上下文窗口: 256k |最大 RPM: 500 | \
| |文本生成 |最大输入: 256k |最大 TPM: 1000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 256k | | \
| |GUI 任务处理 |最大思维链: 256k | | \
| |工具调用 | | | \
| |结构化输出（推荐使用 `json_schema` 模式） | | |
|[doubao-seed-2-0-lite-260428](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-0-lite) [<span data-label="purple">LTS</span>](/docs/lts-mechanism#lts-model-list) |深度思考 |上下文窗口: 256k |最大 RPM: 30000 | \
| |文本生成 |最大输入: 224k |最大 TPM: 5000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 128k | | \
| |GUI 任务处理 |最大思维链: 128k | | \
| |工具调用 | | | \
| |结构化输出（推荐使用 `json_schema` 模式） | | |
|[doubao-seed-2-0-mini-260428](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-0-mini) [<span data-label="purple">LTS</span>](/docs/lts-mechanism#lts-model-list) |深度思考 |上下文窗口: 256k |最大 RPM: 30000 | \
| |文本生成 |最大输入: 224k |最大 TPM: 5000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 128k | | \
| |GUI 任务处理 |最大思维链: 128k | | \
| |工具调用 | | | \
| |结构化输出 | | |
|[doubao-seed-2-0-pro-260215](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-0-pro) `即将下线` |深度思考 |上下文窗口: 256k |最大 RPM: 30000 | \
| |文本生成 |最大输入: 224k |最大 TPM: 5000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 128k | | \
| |GUI 任务处理 |最大思维链: 128k | | \
| |工具调用 | | | \
| |结构化输出 | | |
|[doubao-seed-2-0-lite-260215](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-0-lite) `即将下线` |深度思考 |上下文窗口: 256k |最大 RPM: 30000 | \
| |文本生成 |最大输入: 224k |最大 TPM: 5000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 128k | | \
| |GUI 任务处理 |最大思维链: 128k | | \
| |工具调用 | | | \
| |结构化输出 | | |
|[doubao-seed-2-0-mini-260215](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-0-mini) `即将下线` |深度思考 |上下文窗口: 256k |最大 RPM: 30000 | \
| |文本生成 |最大输入: 224k |最大 TPM: 5000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 128k | | \
| |GUI 任务处理 |最大思维链: 128k | | \
| |工具调用 | | | \
| |结构化输出 | | |
|[doubao-seed-2-0-code-preview-260215](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-0-code) `即将下线` |深度思考 |上下文窗口: 256k |最大 RPM: 30000 | \
| |文本生成 |最大输入: 224k |最大 TPM: 5000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 128k | | \
| |工具调用 |最大思维链: 128k | |
|[doubao-seed-character-260628](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-character&_vtm_=a106466.b106468.0_0.0_0.0.1961_7630866813484467762&projectName=default) |深度思考 |上下文窗口: 128k |最大 RPM: 30000 | \
| |文本生成 |最大输入: 96k |最大 TPM: 5000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 32k | | \
| |工具调用 |最大思维链: 128k | | \
| |结构化输出（推荐使用 `json_schema` 模式） | | |
|[doubao-seed-character-251128](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-character) |文本生成 |上下文窗口: 128k |最大 RPM: 30000 | \
| |工具调用 |最大输入: 96k |最大 TPM: 5000000 | \
| | |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 32k | |
|[doubao-seed-translation-250915](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-translation) |文本生成 |上下文窗口: 4k |最大 RPM: 5000 | \
| |> 翻译增强 |最大输入: 1k |最大 TPM: 500000 | \
| | |[最大回答(默认 3k)](/docs/text-generation#3821b26a): 3k | | \
| | |最大思维链: - | |
|[glm-5-3-flash-260828](https://ark.volcengine.com/region:cn-beijing/model/detail?name=glm-5-3-flash) |深度思考 |上下文窗口: 1024k |最大 RPM: 500 | \
| |文本生成 |最大输入: 1024k |最大 TPM: 1000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 128k | | \
| |工具调用 |最大思维链: 128k | |
|[glm-5-2-260617](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=glm-5-2) |深度思考 |上下文窗口: 1024k |最大 RPM: 500 | \
| |文本生成 |最大输入: 1024k |最大 TPM: 1000000 | \
| |工具调用 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 128k | | \
| | |最大思维链: 128k | |
|[kimi-k3-1-pro-261024](https://ark.volcengine.com/region:cn-beijing/model/detail?name=kimi-k3-1-pro) |深度思考 |上下文窗口: 1024k |最大 RPM: 3000 | \
| |文本生成 |最大输入: 1024k |最大 TPM: 3000000 | \
| | | |最大并发（每 100 万 TPM）: 10 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 1024k | | \
| |工具调用 |最大思维链: 128k | | \
| |结构化输出 | | |
|[deepseek-v4-1-flash-261017](https://ark.volcengine.com/region:cn-beijing/model/detail?name=deepseek-v4-1-flash) |深度思考 |上下文窗口: 1024k |最大 RPM: 3000 | \
| |文本生成 |最大输入: 1024k |最大 TPM: 5000000 | \
| | | |最大并发（每 100 万 TPM）: 5 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 384k | | \
| |工具调用 |最大思维链: 384k | | \
| |结构化输出 | | |
|[deepseek-v4-1-flash-260910](https://ark.volcengine.com/region:cn-beijing/model/detail?name=deepseek-v4-1-flash) |深度思考 |上下文窗口: 1024k |最大 RPM: 3000 | \
| |文本生成 |最大输入: 1024k |最大 TPM: 5000000 | \
| | | |最大并发（每 100 万 TPM）: 5 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 384k | | \
| |工具调用 |最大思维链: 384k | | \
| |结构化输出 | | |
|[deepseek-v4-1-flash-economy-261017](https://ark.volcengine.com/region:cn-beijing/model/detail?name=deepseek-v4-1-flash-economy) |深度思考 |上下文窗口: 1024k |最大 RPM: 3000 | \
| |文本生成 |最大输入: 1024k |最大 TPM: 5000000 | \
| | | |最大并发（每 100 万 TPM）: 10 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 384k | | \
| |工具调用 |最大思维链: 384k | | \
| |结构化输出 | | |
|[deepseek-v4-pro-ga-260813](https://ark.volcengine.com/region:cn-beijing/model/detail?name=deepseek-v4-pro-ga) |深度思考 |上下文窗口: 1024k |最大 RPM: 500 | \
| |文本生成 |最大输入: 1024k |最大 TPM: 1000000 | \
| |工具调用 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 384k<br/>最大思维链: 128k | | \
| |结构化输出 | | |
|[deepseek-v4-flash-ga-260731](https://ark.volcengine.com/region:cn-beijing/model/detail?name=deepseek-v4-flash-ga) |深度思考 |上下文窗口: 1024k |最大 RPM: 500 | \
| |文本生成 |最大输入: 1024k |最大 TPM: 1000000 | \
| |工具调用 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 384k<br/>最大思维链: 128k | | \
| |结构化输出 | | |
|[deepseek-v4-pro-260425](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=deepseek-v4-pro) `即将下线` |深度思考 |上下文窗口: 1024k |最大 RPM: 15000 | \
| |文本生成 |最大输入: 1024k |最大 TPM: 1500000 | \
| |工具调用 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 384k | | \
| | |最大思维链: 128k | |

<span id="76df97c8"></span>
# 视觉理解能力

教程: [图片理解](/docs/image-understanding)、 [视频理解](/docs/video-understanding)、[文档理解](/docs/document-understanding) |   API: [Responses API](/docs/create-model-responses-api)、[Chat API](/docs/chat-api)
<span id="a33eb670"></span>
## 推荐模型

|模型 ID (Model ID) |**能力支持** |**长度限制（token）** |限流 |
|---|---|---|---|
|[doubao-seed-evolving](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-evolving) |深度思考 |上下文窗口: 1024k |最大 RPM: 500 | \
|> 快速迭代模型 |文本生成 |最大输入: 1024k |最大 TPM: 1000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 256k | | \
| |GUI 任务处理 |最大思维链: 256k | | \
| |工具调用 | | | \
| |结构化输出 | | |
|[doubao-seed-2-1-pro-260915](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-1-pro) |深度思考 |上下文窗口: 1024k |最大 RPM: 500 | \
| |文本生成 |最大输入: 1024k |最大 TPM: 1000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 256k | | \
| |GUI 任务处理 |最大思维链: 256k | | \
| |工具调用 | | | \
| |结构化输出 | | |
|[doubao-seed-2-1-lite-260915](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-1-lite) |深度思考 |上下文窗口: 1024k |最大 RPM: 30000 | \
| |文本生成 |最大输入: 1024k |最大 TPM: 5000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 256k | | \
| |GUI 任务处理 |最大思维链: 256k | | \
| |工具调用 | | | \
| |结构化输出 | | |
|[doubao-seed-2-1-turbo-260628](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-1-turbo) |深度思考 |上下文窗口: 256k |最大 RPM: 500 | \
| |文本生成 |最大输入: 256k |最大 TPM: 1000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 256k | | \
| |GUI 任务处理 |最大思维链: 256k | | \
| |工具调用 | | | \
| |结构化输出 | | |

<span id="d6041866"></span>
## **其他模型**

|模型 ID (Model ID) |**能力支持** |长度限制（token） |限流     | \
| | | |> 非刚性保障，受平台负载/调用方式影响，详见 [文档](/docs/traffic-burst-handling-best-practices#263ca129) |
|---|---|---|---|
|[doubao-seed-2-1-pro-260628](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-1-pro) |深度思考 |上下文窗口: 256k |最大 RPM: 500 | \
| |文本生成 |最大输入: 256k |最大 TPM: 1000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 256k | | \
| |GUI 任务处理 |最大思维链: 256k | | \
| |工具调用 | | | \
| |结构化输出（推荐使用 `json_schema` 模式） | | |
|[doubao-seed-2-0-lite-260428](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-0-lite) [<span data-label="purple">LTS</span>](/docs/lts-mechanism#lts-model-list) |深度思考 |上下文窗口: 256k |最大 RPM: 30000 | \
| |文本生成 |最大输入: 224k |最大 TPM: 5000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 128k | | \
| |GUI 任务处理 |最大思维链: 128k | | \
| |工具调用 | | | \
| |结构化输出（推荐使用 `json_schema` 模式） | | |
|[doubao-seed-2-0-mini-260428](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-0-mini) [<span data-label="purple">LTS</span>](/docs/lts-mechanism#lts-model-list) |深度思考 |上下文窗口: 256k |最大 RPM: 30000 | \
| |文本生成 |最大输入: 224k |最大 TPM: 5000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 128k | | \
| |GUI 任务处理 |最大思维链: 128k | | \
| |工具调用 | | | \
| |结构化输出 | | |
|[doubao-seed-2-0-pro-260215](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-0-pro) `即将下线` |深度思考 |上下文窗口: 256k |最大 RPM: 30000 | \
| |文本生成 |最大输入: 224k |最大 TPM: 5000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 128k | | \
| |视觉定位 |最大思维链: 128k | | \
| |GUI 任务处理 | | | \
| |工具调用 | | | \
| |结构化输出 | | |
|[doubao-seed-2-0-lite-260215](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-0-lite) `即将下线` |深度思考 |上下文窗口: 256k |最大 RPM: 30000 | \
| |文本生成 |最大输入: 224k |最大 TPM: 5000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 128k | | \
| |视觉定位 |最大思维链: 128k | | \
| |GUI 任务处理 | | | \
| |工具调用 | | | \
| |结构化输出 | | |
|[doubao-seed-2-0-mini-260215](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-0-mini) `即将下线` |深度思考 |上下文窗口: 256k |最大 RPM: 30000 | \
| |文本生成 |最大输入: 224k |最大 TPM: 5000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 128k | | \
| |视觉定位 |最大思维链: 128k | | \
| |GUI 任务处理 | | | \
| |工具调用 | | | \
| |结构化输出 | | |
|[doubao-seed-2-0-code-preview-260215](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-0-code) `即将下线` |深度思考 |上下文窗口: 256k |最大 RPM: 30000 | \
| |文本生成 |最大输入: 224k |最大 TPM: 5000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 128k | | \
| |视觉定位 |最大思维链: 128k | | \
| |工具调用 | | |
|[doubao-seed-character-260628](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-character&_vtm_=a106466.b106468.0_0.0_0.0.1961_7630866813484467762&projectName=default) |深度思考 |上下文窗口: 128k |最大 RPM: 30000 | \
| |文本生成 |最大输入: 96k |最大 TPM: 5000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 32k | | \
| |工具调用 |最大思维链: 128k | | \
| |结构化输出（推荐使用 `json_schema` 模式） | | |
|[glm-5-3-flash-260828](https://ark.volcengine.com/region:cn-beijing/model/detail?name=glm-5-3-flash) |深度思考 |上下文窗口: 1024k |最大 RPM: 500 | \
| |文本生成 |最大输入: 1024k |最大 TPM: 1000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 128k | | \
| |工具调用 |最大思维链: 128k | |
|[kimi-k3-1-pro-261024](https://ark.volcengine.com/region:cn-beijing/model/detail?name=kimi-k3-1-pro) |深度思考 |上下文窗口: 1024k |最大 RPM: 3000 | \
| |文本生成 |最大输入: 1024k |最大 TPM: 3000000 | \
| | | |最大并发（每 100 万 TPM）: 10 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 1024k | | \
| |工具调用 |最大思维链: 128k | | \
| |结构化输出 | | |
|[deepseek-v4-1-flash-261017](https://ark.volcengine.com/region:cn-beijing/model/detail?name=deepseek-v4-1-flash) |深度思考 |上下文窗口: 1024k |最大 RPM: 3000 | \
| |文本生成 |最大输入: 1024k |最大 TPM: 5000000 | \
| | | |最大并发（每 100 万 TPM）: 5 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 384k | | \
| |工具调用 |最大思维链: 384k | | \
| |结构化输出 | | |
|[deepseek-v4-1-flash-260910](https://ark.volcengine.com/region:cn-beijing/model/detail?name=deepseek-v4-1-flash) |深度思考 |上下文窗口: 1024k |最大 RPM: 3000 | \
| |文本生成 |最大输入: 1024k |最大 TPM: 5000000 | \
| | | |最大并发（每 100 万 TPM）: 5 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 384k | | \
| |工具调用 |最大思维链: 384k | | \
| |结构化输出 | | |
|[deepseek-v4-1-flash-economy-261017](https://ark.volcengine.com/region:cn-beijing/model/detail?name=deepseek-v4-1-flash-economy) |深度思考 |上下文窗口: 1024k |最大 RPM: 3000 | \
| |文本生成 |最大输入: 1024k |最大 TPM: 5000000 | \
| | | |最大并发（每 100 万 TPM）: 10 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 384k | | \
| |工具调用 |最大思维链: 384k | | \
| |结构化输出 | | |

<span id="9619c0ba"></span>
# 音频理解能力

教程: [音频理解](/docs/audio-understanding) |   API: [Responses API](/docs/create-model-responses-api)、[Chat API](/docs/chat-api)
<span id="7f07256a"></span>
## 推荐模型

|模型 ID (Model ID) |**能力支持** |**长度限制（token）** |限流     | \
| | | |> 非刚性保障，受平台负载/调用方式影响，详见 [文档](/docs/traffic-burst-handling-best-practices#263ca129) |
|---|---|---|---|
|[doubao-seed-2-1-lite-260915](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-1-lite) |深度思考 |上下文窗口: 1024k |最大 RPM: 30000 | \
| |文本生成 |最大输入: 1024k |最大 TPM: 5000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 256k | | \
| |工具调用 |最大思维链: 256k | | \
| |结构化输出 | | |
|[doubao-seed-2-0-lite-260428](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-0-lite) [<span data-label="purple">LTS</span>](/docs/lts-mechanism#lts-model-list) |深度思考 |上下文窗口: 256k |最大 RPM: 30000 | \
| |文本生成 |最大输入: 224k |最大 TPM: 5000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 128k | | \
| |工具调用 |最大思维链: 128k | | \
| |结构化输出（推荐使用 `json_schema` 模式） | | |
|[doubao-seed-2-0-mini-260428](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-0-mini) [<span data-label="purple">LTS</span>](/docs/lts-mechanism#lts-model-list) |深度思考 |上下文窗口: 256k |最大 RPM: 30000 | \
| |文本生成 |最大输入: 224k |最大 TPM: 5000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 128k | | \
| |工具调用 |最大思维链: 128k | | \
| |结构化输出 | | |

<span id="f2b7c91d"></span>
# 决策评估能力（beta）

教程: [决策评估（beta）](/docs/decision-model) |   API: [System One API（beta）](/docs/system-one-api)

<span id="c7a36e91"></span>
## 推荐模型

|模型 ID (Model ID) |**能力支持** |**长度限制（token）** |限流     | \
| | | |> 非刚性保障，受平台负载/调用方式影响，详见 [文档](/docs/traffic-burst-handling-best-practices#263ca129) |
|---|---|---|---|
|[doubao-seed-2-1-lite-260915](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-1-lite) |决策评估 |上下文窗口: 128k |最大 RPM: 30000 | \
| |多模态理解 | |最大 TPM: 5000000 |

<span id="42df3eb4"></span>
# GUI 任务处理能力

教程: [GUI Agent 能力](/docs/gui-task-processing) |   API: [Responses API](/docs/create-model-responses-api)、[Chat API](/docs/chat-api)

<span id="99f6f6b8"></span>
## 推荐模型

|模型 ID (Model ID) |**能力支持** |**长度限制（token）** |限流     | \
| | | |> 非刚性保障，受平台负载/调用方式影响，详见 [文档](/docs/traffic-burst-handling-best-practices#263ca129) |
|---|---|---|---|
|[doubao-seed-evolving](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-evolving) |深度思考 |上下文窗口: 1024k |最大 RPM: 500 | \
|> 快速迭代模型 |文本生成 |最大输入: 1024k |最大 TPM: 1000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 256k | | \
| |GUI 任务处理 |最大思维链: 256k | | \
| |工具调用 | | | \
| |结构化输出 | | |
|[doubao-seed-2-1-pro-260915](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-1-pro) |深度思考 |上下文窗口: 1024k |最大 RPM: 500 | \
| |文本生成 |最大输入: 1024k |最大 TPM: 1000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 256k | | \
| |GUI 任务处理 |最大思维链: 256k | | \
| |工具调用 | | | \
| |结构化输出 | | |
|[doubao-seed-2-1-lite-260915](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-1-lite) |深度思考 |上下文窗口: 1024k |最大 RPM: 30000 | \
| |文本生成 |最大输入: 1024k |最大 TPM: 5000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 256k | | \
| |GUI 任务处理 |最大思维链: 256k | | \
| |工具调用 | | | \
| |结构化输出 | | |
|[doubao-seed-2-1-turbo-260628](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-1-turbo) |深度思考 |上下文窗口: 256k |最大 RPM: 500 | \
| |文本生成 |最大输入: 256k |最大 TPM: 1000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 256k | | \
| |GUI 任务处理 |最大思维链: 256k | | \
| |工具调用 | | | \
| |结构化输出 | | |

<span id="4e7f2a3b"></span>
## 其他模型

|模型 ID (Model ID) |**能力支持** |长度限制（token） |限流     | \
| | | |> 非刚性保障，受平台负载/调用方式影响，详见 [文档](/docs/traffic-burst-handling-best-practices#263ca129) |
|---|---|---|---|
|[doubao-seed-2-1-pro-260628](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-1-pro) |深度思考 |上下文窗口: 256k |最大 RPM: 500 | \
| |文本生成 |最大输入: 256k |最大 TPM: 1000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 256k | | \
| |GUI 任务处理 |最大思维链: 256k | | \
| |工具调用 | | | \
| |结构化输出（推荐使用 `json_schema` 模式） | | |
|[doubao-seed-2-0-lite-260428](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-0-lite) [<span data-label="purple">LTS</span>](/docs/lts-mechanism#lts-model-list) |深度思考 |上下文窗口: 256k |最大 RPM: 30000 | \
| |文本生成 |最大输入: 224k |最大 TPM: 5000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 128k | | \
| |GUI 任务处理 |最大思维链: 128k | | \
| |工具调用 | | | \
| |结构化输出（推荐使用 `json_schema` 模式） | | |
|[doubao-seed-2-0-mini-260428](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-0-mini) [<span data-label="purple">LTS</span>](/docs/lts-mechanism#lts-model-list) |深度思考 |上下文窗口: 256k |最大 RPM: 30000 | \
| |文本生成 |最大输入: 224k |最大 TPM: 5000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 128k | | \
| |GUI 任务处理 |最大思维链: 128k | | \
| |工具调用 | | | \
| |结构化输出 | | |
|[doubao-seed-2-0-pro-260215](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-0-pro) `即将下线` |深度思考 |上下文窗口: 256k |最大 RPM: 30000 | \
| |文本生成 |最大输入: 224k |最大 TPM: 5000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 128k | | \
| |GUI 任务处理 |最大思维链: 128k | | \
| |工具调用 | | | \
| |结构化输出 | | |
|[doubao-seed-2-0-lite-260215](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-0-lite) `即将下线` |深度思考 |上下文窗口: 256k |最大 RPM: 30000 | \
| |文本生成 |最大输入: 224k |最大 TPM: 5000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 128k | | \
| |GUI 任务处理 |最大思维链: 128k | | \
| |工具调用 | | | \
| |结构化输出 | | |
|[doubao-seed-2-0-mini-260215](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-0-mini) `即将下线` |深度思考 |上下文窗口: 256k |最大 RPM: 30000 | \
| |文本生成 |最大输入: 224k |最大 TPM: 5000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 128k | | \
| |GUI 任务处理 |最大思维链: 128k | | \
| |工具调用 | | | \
| |结构化输出 | | |

<span id="f44ceef7"></span>
# 工具调用能力

|**模型 ID（Model ID）** |**函数调用** |**知识库** |**MCP** |**联网内容插件** |**图像处理** |**豆包助手** | \
| |[Responses API](/docs/create-model-responses-api) & [Chat API](/docs/chat-api) |[Responses API](/docs/create-model-responses-api) |[Responses API](/docs/create-model-responses-api) |[Responses API](/docs/create-model-responses-api) |[Responses API](/docs/create-model-responses-api) |[Responses API](/docs/create-model-responses-api) |
|---|---|---|---|---|---|---|
|[doubao-seed-evolving](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-evolving)<br/><span style="display: block; margin-top: 8px; padding-left: 8px; border-left: 3px solid #d0d7de; color: #6a737d;">快速迭代模型</span> |✓ |✓ |✓ |✓ |✓ |✓ |
|[doubao-seed-2-1-pro-260915](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-1-pro) |✓ |✓ |✓ |✓ |✓ |✓ |
|[doubao-seed-2-1-lite-260915](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-1-lite) |✓ |✓ |✓ |✓ |✓ |✓ |
|[doubao-seed-2-1-pro-260628](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-1-pro) |✓ |✓ |✓ |✓ |✓ |✓ |
|[doubao-seed-2-1-turbo-260628](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-1-turbo) |✓ |✓ |✓ |✓ |✓ |✓ |
|[doubao-seed-2-0-lite-260428](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-0-lite) [<span data-label="purple">LTS</span>](/docs/lts-mechanism#lts-model-list) |✓ |✓ |✓ |✓ |✓ |✓ |
|[doubao-seed-2-0-mini-260428](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-0-mini) [<span data-label="purple">LTS</span>](/docs/lts-mechanism#lts-model-list) |✓ |✓ |✓ |✓ |✓ |✓ |
|[doubao-seed-2-0-pro-260215](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-0-pro) `即将下线` |✓ |✓ |✓ |✓ |✓ |✓ |
|[doubao-seed-2-0-lite-260215](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-0-lite) `即将下线` |✓ |✓ |✓ |✓ |✓ |✓ |
|[doubao-seed-2-0-mini-260215](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-0-mini) `即将下线` |✓ |✓ |✓ |✓ |✓ |✓ |
|[doubao-seed-2-0-code-preview-260215](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-0-code) `即将下线` |✓ |✓ |✓ |✓ |✓ |✓ |
|[doubao-seed-character-260628](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-character&_vtm_=a106466.b106468.0_0.0_0.0.1961_7630866813484467762&projectName=default) |✓ |✓ |✓ |✓ |✓ |✓ |
|[doubao-seed-character-251128](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-character) |✓ |✗ |✗ |✗ |✗ |✗ |
|[glm-5-3-flash-260828](https://ark.volcengine.com/region:cn-beijing/model/detail?name=glm-5-3-flash) |✓ |✓ |✓ |✓ |✗ |✗ |
|[glm-5-2-260617](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=glm-5-2) |✓ |✓ |✓ |✓ |✗ |✗ |
|[kimi-k3-1-pro-261024](https://ark.volcengine.com/region:cn-beijing/model/detail?name=kimi-k3-1-pro) |✓ |✓ |✓ |✓ |✗ |✗ |
|[deepseek-v4-1-flash-261017](https://ark.volcengine.com/region:cn-beijing/model/detail?name=deepseek-v4-1-flash) |✓ |✓ |✓ |✓ |✗ |✗ |
|[deepseek-v4-1-flash-260910](https://ark.volcengine.com/region:cn-beijing/model/detail?name=deepseek-v4-1-flash) |✓ |✓ |✓ |✓ |✗ |✗ |
|[deepseek-v4-1-flash-economy-261017](https://ark.volcengine.com/region:cn-beijing/model/detail?name=deepseek-v4-1-flash-economy) |✓ |✓ |✓ |✓ |✗ |✗ |
|[deepseek-v4-pro-ga-260813](https://ark.volcengine.com/region:cn-beijing/model/detail?name=deepseek-v4-pro-ga) |✓ |✓ |✓ |✓ |✗ |✗ |
|[deepseek-v4-flash-ga-260731](https://ark.volcengine.com/region:cn-beijing/model/detail?name=deepseek-v4-flash-ga) |✓ |✓ |✓ |✓ |✗ |✗ |
|[deepseek-v4-pro-260425](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=deepseek-v4-pro) `即将下线` |✓ |✓ |✓ |✓ |✗ |✗ |

相关教程：
* [Function Calling（函数调用）](/docs/function-calling)
* [私域知识库搜索 Knowledge Search](/docs/knowledge-search)
* [云部署 MCP / Remote MCP](/docs/mcp-remote-mcp)
* [联网搜索工具](/docs/web-search)
* [图像处理 Image Process](/docs/image-process)
* [豆包助手 API](/docs/doubao-assistant)（Beta）
<span id="ed095742"></span>
# 上下文缓存能力

介绍: [上下文缓存](/docs/context-cache) | API: [Responses API](/docs/create-model-responses-api) 、[Chat API](/docs/chat-api)、[Messages API](/docs/messages-api)、[Batch API](/docs/create-batch-inference-job-api)
<span id="8a26d5c8"></span>
## 推荐模型

|模型ID（Model ID） |隐式缓存 |显式缓存 | |
|---|---|---|---|
|[doubao-seed-evolving](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-evolving) |[Responses API](/docs/create-model-responses-api) |[Responses API](/docs/create-model-responses-api) | | \
|> 快速迭代模型 |[Chat API](/docs/chat-api) |前缀缓存 | | \
| |[Messages API](/docs/messages-api) |Session缓存 | |
|[doubao-seed-2-1-pro-260915](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-1-pro) |[Responses API](/docs/create-model-responses-api) |[Responses API](/docs/create-model-responses-api) | | \
| |[Chat API](/docs/chat-api) |前缀缓存 | | \
| |[Messages API](/docs/messages-api) |Session缓存 | |
|[doubao-seed-2-1-lite-260915](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-1-lite) |[Responses API](/docs/create-model-responses-api) |[Responses API](/docs/create-model-responses-api) | | \
| |[Chat API](/docs/chat-api) |前缀缓存 | | \
| |[Messages API](/docs/messages-api) |Session缓存 | |
|[doubao-seed-2-1-turbo-260628](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-1-turbo) |[Responses API](/docs/create-model-responses-api) |[Responses API](/docs/create-model-responses-api) | | \
| |[Chat API](/docs/chat-api) |前缀缓存 | | \
| |[Messages API](/docs/messages-api) |Session缓存 | | \
| |[Batch API](/docs/create-batch-inference-job-api) | | |

<span id="45477f0f"></span>
## 其他模型

|模型ID（Model ID） |隐式缓存 |显式缓存 | |
|---|---|---|---|
|[doubao-seed-2-1-pro-260628](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-1-pro) |[Responses API](/docs/create-model-responses-api) |[Responses API](/docs/create-model-responses-api) | | \
| |[Chat API](/docs/chat-api) |前缀缓存 | | \
| |[Messages API](/docs/messages-api) |Session缓存 | |
|[doubao-seed-2-0-lite-260428](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-0-lite) [<span data-label="purple">LTS</span>](/docs/lts-mechanism#lts-model-list) |[Responses API](/docs/create-model-responses-api) |[Responses API](/docs/create-model-responses-api) | | \
| |[Chat API](/docs/chat-api) |前缀缓存 | | \
| | |Session缓存 | |
|[doubao-seed-2-0-mini-260428](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-0-mini) [<span data-label="purple">LTS</span>](/docs/lts-mechanism#lts-model-list) |[Responses API](/docs/create-model-responses-api) |[Responses API](/docs/create-model-responses-api) | | \
| |[Chat API](/docs/chat-api) |前缀缓存 | | \
| | |Session缓存 | |
|[doubao-seed-2-0-pro-260215](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-0-pro) `即将下线` |[Responses API](/docs/create-model-responses-api) |[Responses API](/docs/create-model-responses-api) | | \
| |[Chat API](/docs/chat-api) |前缀缓存 | | \
| |[Messages API](/docs/messages-api) |Session缓存 | | \
| |[Batch API](/docs/create-batch-inference-job-api) | | |
|[doubao-seed-2-0-lite-260215](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-0-lite) `即将下线` |[Responses API](/docs/create-model-responses-api) |[Responses API](/docs/create-model-responses-api) | | \
| |[Chat API](/docs/chat-api) |前缀缓存 | | \
| | |Session缓存 | |
|[doubao-seed-2-0-mini-260215](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-0-mini) `即将下线` |[Responses API](/docs/create-model-responses-api) |[Responses API](/docs/create-model-responses-api) | | \
| |[Chat API](/docs/chat-api) |前缀缓存 | | \
| | |Session缓存 | |
|[doubao-seed-2-0-code-preview-260215](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-0-code) `即将下线` |[Responses API](/docs/create-model-responses-api) |[Responses API](/docs/create-model-responses-api) | | \
| |[Chat API](/docs/chat-api) |前缀缓存 | | \
| | |Session缓存 | |
|[doubao-seed-character-260628](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-character&_vtm_=a106466.b106468.0_0.0_0.0.1961_7630866813484467762&projectName=default) |[Responses API](/docs/create-model-responses-api) |[Responses API](/docs/create-model-responses-api) | | \
| |[Chat API](/docs/chat-api) |前缀缓存 | | \
| |[Batch API](/docs/create-batch-inference-job-api) |Session缓存 | |
|[doubao-seed-character-251128](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-character) |[Responses API](/docs/create-model-responses-api) |[Responses API](/docs/create-model-responses-api) | | \
| |[Chat API](/docs/chat-api) |前缀缓存 | | \
| |[Batch API](/docs/create-batch-inference-job-api) |Session缓存 | |
|[glm-5-3-flash-260828](https://ark.volcengine.com/region:cn-beijing/model/detail?name=glm-5-3-flash) |[Responses API](/docs/create-model-responses-api) |[Responses API](/docs/create-model-responses-api) | | \
| |[Chat API](/docs/chat-api) |前缀缓存 | | \
| |[Messages API](/docs/messages-api) |Session缓存 | |
|[glm-5-2-260617](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=glm-5-2) |[Responses API](/docs/create-model-responses-api) |[Responses API](/docs/create-model-responses-api) | | \
| |[Chat API](/docs/chat-api) |前缀缓存 | | \
| |[Messages API](/docs/messages-api) |Session缓存 | |
|[kimi-k3-1-pro-261024](https://ark.volcengine.com/region:cn-beijing/model/detail?name=kimi-k3-1-pro) |[Responses API](/docs/create-model-responses-api) |– | | \
| |[Chat API](/docs/chat-api) | | | \
| |[Messages API](/docs/messages-api) | | |
|[deepseek-v4-1-flash-261017](https://ark.volcengine.com/region:cn-beijing/model/detail?name=deepseek-v4-1-flash) |[Responses API](/docs/create-model-responses-api) |[Responses API](/docs/create-model-responses-api) | | \
| |[Chat API](/docs/chat-api) |前缀缓存 | | \
| | |Session缓存 | |
|[deepseek-v4-1-flash-260910](https://ark.volcengine.com/region:cn-beijing/model/detail?name=deepseek-v4-1-flash) |[Responses API](/docs/create-model-responses-api) |[Responses API](/docs/create-model-responses-api) | | \
| |[Chat API](/docs/chat-api) |前缀缓存 | | \
| | |Session缓存 | |
|[deepseek-v4-1-flash-economy-261017](https://ark.volcengine.com/region:cn-beijing/model/detail?name=deepseek-v4-1-flash-economy) |[Responses API](/docs/create-model-responses-api) |[Responses API](/docs/create-model-responses-api) | | \
| |[Chat API](/docs/chat-api) |前缀缓存 | | \
| | |Session缓存 | |
|[deepseek-v4-pro-ga-260813](https://ark.volcengine.com/region:cn-beijing/model/detail?name=deepseek-v4-pro-ga) |[Responses API](/docs/create-model-responses-api) |[Responses API](/docs/create-model-responses-api) | | \
| |[Chat API](/docs/chat-api) |前缀缓存 | | \
| |[Messages API](/docs/messages-api) |Session缓存 | | \
| |[Batch API](/docs/create-batch-inference-job-api) | | |
|[deepseek-v4-flash-ga-260731](https://ark.volcengine.com/region:cn-beijing/model/detail?name=deepseek-v4-flash-ga) |[Responses API](/docs/create-model-responses-api) |[Responses API](/docs/create-model-responses-api) | | \
| |[Chat API](/docs/chat-api) |前缀缓存 | | \
| | |Session缓存 | |
|[deepseek-v4-pro-260425](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=deepseek-v4-pro) `即将下线` |[Responses API](/docs/create-model-responses-api) |[Responses API](/docs/create-model-responses-api) | | \
| |[Chat API](/docs/chat-api) |前缀缓存 | | \
| | |Session缓存 | |

<span id="86588b72"></span>
# 结构化输出能力（beta）

介绍: [结构化输出(beta)](/docs/structured-output-beta)  | API: [Responses API](/docs/create-model-responses-api)、[Chat API](/docs/chat-api)
<span id="79e2b6f0"></span>
## 推荐模型

|模型 ID (Model ID) |能力支持 |**长度限制（token）** |限流     | \
| | | |> 非刚性保障，受平台负载/调用方式影响，详见 [文档](/docs/traffic-burst-handling-best-practices#263ca129) |
|---|---|---|---|
|[doubao-seed-evolving](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-evolving) |深度思考 |上下文窗口: 1024k |最大 RPM: 500 | \
|> 快速迭代模型 |文本生成 |最大输入: 1024k |最大 TPM: 1000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 256k | | \
| |工具调用 |最大思维链: 256k | | \
| |结构化输出 | | |
|[doubao-seed-2-1-pro-260915](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-1-pro) |深度思考 |上下文窗口: 1024k |最大 RPM: 500 | \
| |文本生成 |最大输入: 1024k |最大 TPM: 1000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 256k | | \
| |工具调用 |最大思维链: 256k | | \
| |结构化输出 | | |
|[doubao-seed-2-1-lite-260915](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-1-lite) |深度思考 |上下文窗口: 1024k |最大 RPM: 30000 | \
| |文本生成 |最大输入: 1024k |最大 TPM: 5000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 256k | | \
| |工具调用 |最大思维链: 256k | | \
| |结构化输出 | | |
|[doubao-seed-2-1-turbo-260628](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-1-turbo) |深度思考 |上下文窗口: 256k |最大 RPM: 500 | \
| |文本生成 |最大输入: 256k |最大 TPM: 1000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 256k | | \
| |工具调用 |最大思维链: 256k | | \
| |结构化输出 | | |

<span id="b0d6f164"></span>
## 其他模型

|模型 ID (Model ID) |能力支持 |**长度限制（token）** |限流     | \
| | | |> 非刚性保障，受平台负载/调用方式影响，详见 [文档](/docs/traffic-burst-handling-best-practices#263ca129) |
|---|---|---|---|
|[doubao-seed-2-1-pro-260628](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-1-pro) |深度思考 |上下文窗口: 256k |最大 RPM: 500 | \
| |文本生成 |最大输入: 256k |最大 TPM: 1000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 256k | | \
| |工具调用 |最大思维链: 256k | | \
| |结构化输出（推荐使用 `json_schema` 模式） | | |
|[doubao-seed-2-0-lite-260428](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-0-lite) [<span data-label="purple">LTS</span>](/docs/lts-mechanism#lts-model-list) |深度思考 |上下文窗口: 256k |最大 RPM: 30000 | \
| |文本生成 |最大输入: 224k |最大 TPM: 5000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 128k | | \
| |工具调用 |最大思维链: 128k | | \
| |结构化输出（推荐使用 `json_schema` 模式） | | |
|[doubao-seed-2-0-mini-260428](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-0-mini) [<span data-label="purple">LTS</span>](/docs/lts-mechanism#lts-model-list) |深度思考 |上下文窗口: 256k |最大 RPM: 30000 | \
| |文本生成 |最大输入: 224k |最大 TPM: 5000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 128k | | \
| |工具调用 |最大思维链: 128k | | \
| |结构化输出 | | |
|[doubao-seed-2-0-pro-260215](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-0-pro) `即将下线` |深度思考 |上下文窗口: 256k |最大 RPM: 30000 | \
| |文本生成 |最大输入: 224k |最大 TPM: 5000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 128k | | \
| |工具调用 |最大思维链: 128k | | \
| |结构化输出 | | |
|[doubao-seed-2-0-lite-260215](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-0-lite) `即将下线` |深度思考 |上下文窗口: 256k |最大 RPM: 30000 | \
| |文本生成 |最大输入: 224k |最大 TPM: 5000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 128k | | \
| |工具调用 |最大思维链: 128k | | \
| |结构化输出 | | |
|[doubao-seed-2-0-mini-260215](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-2-0-mini) `即将下线` |深度思考 |上下文窗口: 256k |最大 RPM: 30000 | \
| |文本生成 |最大输入: 224k |最大 TPM: 5000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 128k | | \
| |工具调用 |最大思维链: 128k | | \
| |结构化输出 | | |
|[doubao-seed-character-260628](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed-character&_vtm_=a106466.b106468.0_0.0_0.0.1961_7630866813484467762&projectName=default) |深度思考 |上下文窗口: 128k |最大 RPM: 30000 | \
| |文本生成 |最大输入: 96k |最大 TPM: 5000000 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 32k | | \
| |工具调用 |最大思维链: 128k | | \
| |结构化输出（推荐使用 `json_schema` 模式） | | |
|[kimi-k3-1-pro-261024](https://ark.volcengine.com/region:cn-beijing/model/detail?name=kimi-k3-1-pro) |深度思考 |上下文窗口: 1024k |最大 RPM: 3000 | \
| |文本生成 |最大输入: 1024k |最大 TPM: 3000000 | \
| | | |最大并发（每 100 万 TPM）: 10 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 1024k | | \
| |工具调用 |最大思维链: 128k | | \
| |结构化输出 | | |
|[deepseek-v4-1-flash-261017](https://ark.volcengine.com/region:cn-beijing/model/detail?name=deepseek-v4-1-flash) |深度思考 |上下文窗口: 1024k |最大 RPM: 3000 | \
| |文本生成 |最大输入: 1024k |最大 TPM: 5000000 | \
| | | |最大并发（每 100 万 TPM）: 5 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 384k | | \
| |工具调用 |最大思维链: 384k | | \
| |结构化输出 | | |
|[deepseek-v4-1-flash-260910](https://ark.volcengine.com/region:cn-beijing/model/detail?name=deepseek-v4-1-flash) |深度思考 |上下文窗口: 1024k |最大 RPM: 3000 | \
| |文本生成 |最大输入: 1024k |最大 TPM: 5000000 | \
| | | |最大并发（每 100 万 TPM）: 5 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 384k | | \
| |工具调用 |最大思维链: 384k | | \
| |结构化输出 | | |
|[deepseek-v4-1-flash-economy-261017](https://ark.volcengine.com/region:cn-beijing/model/detail?name=deepseek-v4-1-flash-economy) |深度思考 |上下文窗口: 1024k |最大 RPM: 3000 | \
| |文本生成 |最大输入: 1024k |最大 TPM: 5000000 | \
| | | |最大并发（每 100 万 TPM）: 10 | \
| |多模态理解 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 384k | | \
| |工具调用 |最大思维链: 384k | | \
| |结构化输出 | | |
|[deepseek-v4-pro-ga-260813](https://ark.volcengine.com/region:cn-beijing/model/detail?name=deepseek-v4-pro-ga) |深度思考 |上下文窗口: 1024k |最大 RPM: 500 | \
| |文本生成 |最大输入: 1024k |最大 TPM: 1000000 | \
| |工具调用 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 384k<br/>最大思维链: 128k | | \
| |结构化输出 | | |
|[deepseek-v4-flash-ga-260731](https://ark.volcengine.com/region:cn-beijing/model/detail?name=deepseek-v4-flash-ga) |深度思考 |上下文窗口: 1024k |最大 RPM: 500 | \
| |文本生成 |最大输入: 1024k |最大 TPM: 1000000 | \
| |工具调用 |[最大回答(默认 4k)](/docs/text-generation#3821b26a): 384k<br/>最大思维链: 128k | | \
| |结构化输出 | | |
<span id="7571da3f"></span>
# 视频生成能力
教程: [Doubao Seedance 2.0 系列教程](/docs/seedance-2-0) | API: [Video Generation API](/docs/create-video-generation-task-api)
|**模型 ID（Model ID）** |**模型能力** |**输出视频格式** |在线推理限流     |离线推理限流 | \
| | | |> 非刚性保障，受平台负载/调用方式影响，详见 [文档](/docs/traffic-burst-handling-best-practices#263ca129) |> 非刚性保障，受平台负载/调用方式影响，详见 [文档](/docs/traffic-burst-handling-best-practices#263ca129) |
|---|---|---|---|---|
|[doubao-seedance-2-5-260628](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seedance-2-5) |* 全模态参考生视频  |* 分辨率:  |* 最大 RPM: |* 暂不支持 | \
| |   * 参考生视频  |   * 480p（8bit 位深）  |   * 企业用户: 600 | | \
| | |   * 720p（8bit 位深） | | | \
| | |   * 1080p（10bit 位深） | | | \
| |   * 编辑视频  |* 帧率: 24 fps  |   * 个人用户: 180 | | \
| |   * 延长视频  |* 时长: 4~30 秒  |* 最大并发: | | \
| |* 首尾帧生视频  |* 视频格式: mp4, mov  |   * 企业用户: 10 | | \
| |* 首帧生视频  | |   * 个人用户: 3 | | \
| |* 文生视频  | | | |
|[doubao-seedance-2-0-260128](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seedance-2-0&projectName=default) |* 全模态参考生视频  |* 分辨率:  |非 4k 分辨率：  |* 暂不支持 | \
| |   * 参考生视频  |   * 480p（8bit 位深） |* 最大 RPM: | | \
| | |   * 720p（8bit 位深） | | | \
| | |   * 1080p（8bit 位深） | | | \
| | |   * 4k（10bit 位深） | | | \
| |   * 编辑视频  |* 帧率: 24 fps  |   * 企业用户: 600 | | \
| |   * 延长视频  |* 时长: 4~15 秒  |   * 个人用户: 180 | | \
| |* 首尾帧生视频  |* 视频格式: mp4  |* 最大并发: | | \
| |* 首帧生视频  | |   * 企业用户: 10 | | \
| |* 文生视频  | |   * 个人用户: 3 | | \
| | | |   * 个人用户: 3 | | \
| | | | | | \
| | | |4k 分辨率： | | \
| | | |* 最大 RPM | | \
| | | |   * 企业用户：15 | | \
| | | |   * 个人用户：15 | | \
| | | |* 最大并发 | | \
| | | |   * 企业用户：1 | | \
| | | |   * 个人用户：1 | |
|[doubao-seedance-2-0-fast-260128](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seedance-2-0-fast) |* 全模态参考生视频  |* 分辨率:  |* 最大 RPM: |* 暂不支持 | \
| |   * 参考生视频  |   * 480p（8bit 位深）  |   * 企业用户: 600 | | \
| | |   * 720p（8bit 位深） | | | \
| |   * 编辑视频  |* 帧率: 24 fps  |   * 个人用户: 180 | | \
| |   * 延长视频  |* 时长: 4~15 秒  |* 最大并发: | | \
| |* 首尾帧生视频  |* 视频格式: mp4  |   * 企业用户: 10 | | \
| |* 首帧生视频  | |   * 个人用户: 3 | | \
| |* 文生视频  | | | |
|[doubao-seedance-2-0-mini-260615](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seedance-2-0-mini) |* 全模态参考生视频  |* 分辨率:  |* 最大 RPM: |* 暂不支持 | \
| |   * 参考生视频  |   * 480p（8bit 位深）  |   * 企业用户: 600 | | \
| | |   * 720p（8bit 位深） | | | \
| |   * 编辑视频  |* 帧率: 24 fps  |   * 个人用户: 180 | | \
| |   * 延长视频  |* 时长: 4~15 秒  |* 最大并发: | | \
| |* 首尾帧生视频  |* 视频格式: mp4  |   * 企业用户: 10 | | \
| |* 首帧生视频  | |   * 个人用户: 3 | | \
| |* 文生视频  | | | |
|[doubao-seedance-1-0-pro-250528](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seedance-1-0-pro&projectName=default) `即将下线` |* 首尾帧生视频  |分辨率:  |* 最大 RPM: 600 |* 最大 TPD: 5000亿 | \
| |* 首帧生视频  |480p, 720p, 1080p  |* 最大并发: 10 | | \
| |* 文生视频  |帧率: 24 fps  | | | \
| | |时长: 2~12 秒  | | | \
| | |视频格式: mp4  | | |
|[doubao-seedance-1-0-pro-fast-251015](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seedance-1-0-pro-fast&projectName=default) `即将下线` |* 首帧生视频  |分辨率:  |* 最大 RPM: 600 |* 最大 TPD: 5000亿 | \
| |* 文生视频  |480p, 720p, 1080p  |* 最大并发: 10 | | \
| | |帧率: 24 fps  | | | \
| | |时长: 2~12 秒  | | | \
| | |视频格式: mp4  | | |

<span id="9df4d9fd"></span>
# 图片生成能力

教程: [Doubao Seedream 4.0-5.0 教程](/docs/image-generation-tutorial) | API: [Image generation API](/docs/image-generation-api)

<span id="b8c9fd67"></span>
## 推荐模型

|模型 ID (Model ID) |**能力支持** |限流     | | \
| | |> 非刚性保障，受平台负载/调用方式影响，详见 [文档](/docs/traffic-burst-handling-best-practices#263ca129) | | \
| | |**最大 IPM** | | \
| | |张 / 分钟 | |
|---|---|---|---|
|[doubao-seedream-5-0-pro-260628](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seedream-5-0-pro) |图层拆分 |500 | | \
| |单图生成 | | | \
| |* 文生图 | | | \
| |* 单张图生图 | | | \
| |* 多参考图生图 | | |
|[doubao-seedream-5-0-flash-260915](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seedream-5-0-flash) |图层拆分 |500 | | \
| |单图生成 | | | \
| |* 文生图 | | | \
| |* 单张图生图 | | | \
| |* 多参考图生图 | | |
|[doubao-seedream-5-0-260128](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seedream-5-0) |单图生成 |500 | | \
|（同时支持：doubao-seedream-5-0-lite-260128）`即将下线` |* 文生图 | | | \
| |* 单张图生图 | | | \
| |* 多参考图生图 | | | \
| | | | | \
| |组图生成 | | | \
| |* 文生组图 | | | \
| |* 单张图生组图 | | | \
| |* 多参考图生组图 | | |
|[doubao-seedream-4-5-251128](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seedream-4-5) `即将下线` |单图生成 |500 | | \
| |* 文生图 | | | \
| |* 单张图生图 | | | \
| |* 多参考图生图 | | | \
| | | | | \
| |组图生成 | | | \
| |* 文生组图 | | | \
| |* 单张图生组图 | | | \
| |* 多参考图生组图 | | |
|[doubao-seedream-4-0-250828](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seedream-4-0) `即将下线` |单图生成 |500 | | \
| |* 文生图 | | | \
| |* 单张图生图 | | | \
| |* 多参考图生图 | | | \
| | | | | \
| |组图生成 | | | \
| |* 文生组图 | | | \
| |* 单张图生组图 | | | \
| |* 多参考图生组图 | | |

<span id="21b9a17a"></span>
# 3D生成能力

教程: [3D 生成](/docs/3d-generation)  | API: [3D生成 API](/docs/create-3d-generation-task-api)

|**模型 ID (Model ID)** |**能力支持** |**产物规格** |**限流**     |**免费额度** | \
| | | |> **非刚性保障，受平台负载/调用方式影响，详见 [文档](/docs/traffic-burst-handling-best-practices#263ca129)** |（token） |
|---|---|---|---|---|
|[doubao-seed3d-2-0-260328](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-seed3d-2-0) |图生3D |产物面数 |最大 RPM: 300 |200万 | \
| | | |最大并发: 5 | | \
| |* 生成带纹理和 PBR 材质的3D文件 |* 100000 | | | \
| | |* 500000 | | | \
| | |* 1000000 | | | \
| | | | | | \
| | |产物格式 | | | \
| | |* glb, obj, usd, usdz | | | \
| | | | | |
|[hyper3d-gen2-260112](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=hyper3d-gen2) |文生3D、图生3D |产物面数 |最大 RPM: 60 |15万 | \
| | | |最大并发: 3 | | \
| |* 白模 |* 三角面模型：[500, 1,000,000] | | | \
| |* 带纹理模型 |* 四边面模型：[1,000, 200,000] | | | \
| |* PBR 材质模型 | | | | \
| |* 带纹理 + PBR 材质模型 |产物格式 | | | \
| | |* glb, obj, stl, fbx, usdz | | | \
| | | | | |
|[hitem3d-2-0-251223](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=hitem3d-2-0) |图生3D |产物面数 |最大 RPM: 600 |50万 | \
| | | |最大并发: 30 | | \
| |* 标准白模 |* [100000, 2000000] | | | \
| |* 标准纹理模型 | | | | \
| |* 高精白模 |产物格式 | | | \
| |* 高精纹理模型 |* glb, obj, stl, fbx, usdz | | | \
| | | | | | \
| | |产物分辨率 | | | \
| | |* 1536、1536 pro | | | \
| | | | | |

<span id="0ee80bb9"></span>
# 向量化能力

教程: [向量化](/docs/vectorization) | API: [Embeddings Multimodal API](/docs/multimodal-vectorization-api)

|模型 ID (Model ID) |**能力支持** |**上下文窗口** |**最高向量维度** |限流     | \
| | | | |> 非刚性保障，受平台负载/调用方式影响，详见 [文档](/docs/traffic-burst-handling-best-practices#263ca129) |
|---|---|---|---|---|
|[doubao-embedding-vision-251215](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-embedding-vision) |多模态向量化 |128k |2048 |最大 RPM: 15000 | \
| |> 支持 视频、文本、图片输入 | |> 支持1024降维使用 |最大 TPM: 1200000 |
|[doubao-embedding-vision-250615](https://ark.volcengine.com/region:cn-beijing/model/detail?Id=doubao-embedding-vision) `即将下线` |多模态向量化 |128k |2048 |最大 RPM: 15000 | \
| |> 支持 视频、文本、图片输入 | |> 支持1024降维使用 |最大 TPM: 1200000 |
