###### 豆包语音

豆包语音

- 文档首页
根据具体场景选择合适的语音合成大模型API。

| 接口 | 推荐场景 | 接口功能 | 文档链接 |
|---|---|---|---|
| wss://openspeech.bytedance.com/api/v3/tts/bidirection | WebSocket协议，实时交互场景，支持文本实时流式输入，流式输出音频。 | 语音合成、声音复刻、混音 | V3 WebSocket双向流式文档 |
| wss://openspeech.bytedance.com/api/v3/tts/unidirectional/stream | WebSocket协议，一次性输入合成文本，流式输出音频。 | 语音合成、声音复刻、混音 | V3 WebSocket单向流式文档 |
| https://openspeech.bytedance.com/api/v3/tts/unidirectional | HTTP Chunked协议，一次性输入全部合成文本，流式输出音频。 | 语音合成、声音复刻、混音 | V3 HTTP Chunked单向流式文档 |
| https://openspeech.bytedance.com/api/v3/tts/unidirectional/sse | HTTP SSE协议，一次性输入全部合成文本，流式输出音频。 | 语音合成、声音复刻、混音 | V3 Server Sent Events（SSE）单向流式文档 |

单向流式API为用户提供文本转语音的能力，支持多语种、多方言，同时支持http协议流式输出。

## 1.1最佳实践 #

- 客户端读取服务端流式返回的json数据，从中取出对应的音频数据；
- 音频数据返回的是base64格式，需要解析后拼接到字节数组即可组装音频进行播放；
- 可以使用对应编程语言的连接复用组件，避免重复建立tcp连接（火山服务端keep-alive时间为1分钟），例如python的session组件：
## 2.1 请求Request #

### 请求路径 #

- 服务对应的请求路径：https://openspeech.bytedance.com/api/v3/tts/unidirectional
### 鉴权Request Headers #

使用新版控制台时，推荐采用以下更简化的鉴权方式。

若使用旧版控制台，鉴权方式如下。建议尽快切换至新版，以体验更便捷的鉴权流程。

| Key | 说明 | 参数类型 | 是否必须 | Value示例 |
|---|---|---|---|---|
| X-Api-App-Id | 使用火山引擎控制台获取的APP ID，可参考 控制台使用FAQ-Q1（旧版控制台使用，新版控制台只需要X-Api-Key即可） | string | 必须 | “123456789” |
| X-Api-Access-Key | 使用火山引擎控制台获取的Access Token，可参考 控制台使用FAQ-Q1（旧版控制台使用，新版控制台只需要X-Api-Key即可） | string | 必须 | “your-access-key” |
| X-Api-Resource-Id | 表示调用服务的资源信息 ID，可以用来选择不同的模型版本效果，也决定了计费方式。 | string | 必须 | 豆包语音合成大模型 语音合成接口通过 X-Api-Resource-Id 参数来选择不同的版本效果：seed-tts-2.0仅支持调用"豆包语音合成模型2.0"的音色seed-tts-1.0 / seed-tts-1.0-concurr仅支持调用"豆包语音合成模型1.0"的音色同时，X-Api-Resource-Id 也决定了计费方式：seed-tts-2.0：对应计费商品为 “语音合成2.0字符版“seed-tts-1.0：对应计费商品为“语音合成1.0字符版”seed-tts-1.0-concurr：对应计费商品为“语音合成1.0并发版“豆包声音复刻大模型 语音合成接口通过 X-Api-Resource-Id 参数来选择不同的版本效果：seed-icl-2.0：对应声音复刻2.0 版本效果seed-icl-1.0 / seed-icl-1.0-concurr：对应声音复刻1.0 版本效果同时，X-Api-Resource-Id 也决定了计费方式：seed-icl-2.0：对应计费商品为“声音复刻2.0 字符版”seed-icl-1.0：对应计费商品为“声音复刻1.0 字符版”seed-icl-1.0-concurr：对应计费商品为“声音复刻1.0 并发版” |
| X-Api-Request-Id | 标识客户端请求ID，uuid随机字符串 | string | 可选 | “67ee89ba-7050-4c04-a3d7-ac61a63499b3” |

### 额外Request Headers #

### Response Headers #

## 2.2 请求Body #

单音色请求参数示例：

mix请求参数示例：

## 2.3 响应Response #

- 音频响应数据，其中data对应合成音频base64音频数据：
- 文本响应数据，其中sentence对应合成文本数据（包含时间戳）：
示例json：

- 合成音频结束对应的成功响应： 其中usage字段默认不存在，仅在header中插入需要返回用量的标记后会新增。
- 其中usage字段默认不存在，仅在header中插入需要返回用量的标记后会新增。
## 2.4 时间戳相关说明 #

|   | TTS1.0ICL1.0 | TTS2.0ICL2.0 |
|---|---|---|
| 事件交互区别 | 合成有多个子句会多次返回TTSSentenceStart和TTSSentenceEnd。开启字幕后字幕跟随TTSSentenceEnd返回。 | 合成有多个子句，仅返回一次TTSSentenceStart和TTSSentenceEnd。 开启字幕后会多次返回TTSSubtitle。 |
| 返回时机 | 一个子句的时间戳返回之后才会开始返回下一句音频。 | 在一句音频合成之后，不会立即返回该句的字幕。 合成进度不会被字幕识别阻塞，当一句的字幕识别完成后立即返回。 可能一个子句的字幕返回的时候，已经返回下一句的音频帧给调用方了。 |
| 句子返回格式 | 字幕信息是基于tn打轴说明text字段对应于：原文words内文本字段对应于：tn第一句：{ "phonemes": [ ], "text": "2019年1月8日，软件2.0版本于格萨拉彝族乡应时而生。发布会当日，一场瑞雪将天地映衬得纯净无瑕。", "words": [ { "confidence": 0.8766515, "endTime": 0.295, "startTime": 0.155, "word": "二" }, { "confidence": 0.95224416, "endTime": 0.425, "startTime": 0.295, "word": "零" }, { "confidence": 0.9108828, "endTime": 0.575, "startTime": 0.425, "word": "一" }, { "confidence": 0.9609025, "endTime": 0.755, "startTime": 0.575, "word": "九" }, { "confidence": 0.96244556, "endTime": 1.005, "startTime": 0.755, "word": "年" }, { "confidence": 0.85796577, "endTime": 1.155, "startTime": 1.005, "word": "一" }, { "confidence": 0.8460129, "endTime": 1.275, "startTime": 1.155, "word": "月" }, { "confidence": 0.90833753, "endTime": 1.505, "startTime": 1.275, "word": "八" }, { "confidence": 0.9403977, "endTime": 1.935, "startTime": 1.505, "word": "日，" }, ... { "confidence": 0.9415791, "endTime": 10.505, "startTime": 10.355, "word": "无" }, { "confidence": 0.903162, "endTime": 10.895, // 第一句结束时间 "startTime": 10.505, "word": "瑕。" } ] } 第二句：{ "phonemes": [ ], "text": "这仿佛一则自然寓言：我们致力于在不断的版本迭代中，为您带来如雪后初霁般清晰、焕然一新的体验。", "words": [ { "confidence": 0.8970245, "endTime": 11.6953745, "startTime": 11.535375, // 第二句开始时间，是相对整个session的位置 "word": "这" }, { "confidence": 0.86508185, "endTime": 11.875375, "startTime": 11.6953745, "word": "仿" }, { "confidence": 0.73354065, "endTime": 12.095375, "startTime": 11.875375, "word": "佛" }, { "confidence": 0.8525295, "endTime": 12.275374, "startTime": 12.095375, "word": "一" }... ] } | 字幕信息是基于原文打轴说明text字段对应于：原文words内文本字段对应于：原文第一句：{ "phonemes": [ ], "text": "2019年1月8日，软件2.0版本于格萨拉彝族乡应时而生。", "words": [ { "confidence": 0.11120544, "endTime": 0.615, "startTime": 0.585, "word": "2019" }, { "confidence": 0.8413397, "endTime": 0.845, "startTime": 0.615, "word": "年" }, { "confidence": 0.2413961, "endTime": 0.875, "startTime": 0.845, "word": "1" }, { "confidence": 0.8487973, "endTime": 1.055, "startTime": 0.875, "word": "月" }, { "confidence": 0.509697, "endTime": 1.225, "startTime": 1.165, "word": "8" }, { "confidence": 0.9516253, "endTime": 1.485, "startTime": 1.225, "word": "日，" }, ... { "confidence": 0.6933777, "endTime": 5.435, "startTime": 5.325, "word": "而" }, { "confidence": 0.921702, "endTime": 5.695, // 第一句结束时间 "startTime": 5.435, "word": "生。" } ] } 第二句：{ "phonemes": [ ], "text": "发布会当日，一场瑞雪将天地映衬得纯净无瑕。", "words": [ { "confidence": 0.7016578, "endTime": 6.3550415, "startTime": 6.2150416, // 第二句开始时间，是相对整个session的位置 "word": "发" }, { "confidence": 0.6800497, "endTime": 6.4450417, "startTime": 6.3550415, "word": "布" }, ... { "confidence": 0.8818264, "endTime": 10.145041, "startTime": 9.945042, "word": "净" }, { "confidence": 0.87248623, "endTime": 10.285042, "startTime": 10.145041, "word": "无" }, { "confidence": 0.8069703, "endTime": 10.505041, "startTime": 10.285042, "word": "瑕。" } ] } |
| 语种 | 中、英，不支持小语种、方言 | 中、英，不支持小语种、方言 |
| latex | enable_latex_tn=true，有字幕返回 | enable_latex_tn=true，无字幕返回，接口不报错 |
| ssml | req_params.ssml不为空，有字幕返回 | req_params.ssml不为空，无字幕返回，接口不报错 |

## 2.5 实例samples #

## 3.1 请求Request #

### 请求路径 #

- 服务对应的请求路径：https://openspeech.bytedance.com/api/v3/tts/unidirectional/sse
### Request Headers #

- 同2.1节中的HTTP Chunked格式接口的Request Headers中内容一样
## 3.2 请求Body #

- 同2.2节中的HTTP Chunked格式接口的Request Body的内容一样， 示例也同2.2节中的HTTP Chunked格式接口所示。
## 3.3 响应Response #

### Response Headers #

| Key | 说明 | Value示例 |
|---|---|---|
| Content-Type | 返回的数据类型，一般为event-stream | text/event-stream |
| X-Tt-Logid | 服务端返回的 logid，建议用户获取和打印方便定位问题 | 2025041513355271DF5CF1A0AE0508E78C |

## 3.4 Response Body #

- 单个返回内容同2.2节中HTTP Chunked格式接口的Response内容， 包含由code、message、data等字段组成的对象。
- 整体返回示例如下
- event 表示云端响应的事件ID。以下为常见的事件，仅供参考使用。 351 - TTSSentenceEnd （TTS 语句处理结束）352 - TTSResponse (TTS的合成内容，一般多包含二进制字符串流）151 - SessionCancel （会话被取消）152 - SessionFinish （会话结束）153 - SessionFailed （会话失败）
- 351 - TTSSentenceEnd （TTS 语句处理结束）
- 352 - TTSResponse (TTS的合成内容，一般多包含二进制字符串流）
- 151 - SessionCancel （会话被取消）
- 152 - SessionFinish （会话结束）
- 153 - SessionFailed （会话失败）
## 3.5 使用限制 #

- 目前本接口仅支持以SSE的格式返回数据，对其常规能力，如重连、断点续传等能力暂不支持。
## 3.6 示例Samples #
