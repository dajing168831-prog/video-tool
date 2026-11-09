*基于 WebSocket 协议的单向流式合成接口，一次性输入文本，流式返回音频，支持中、英、日、西等多语种及多种方言口音。
*
*运行依赖文件
* 
* 
*WSSwss://openspeech.bytedance.com/api/v3/tts/unidirectional/stream
* 
* 
* 
*
*
*

*"context_texts":[ "你可以用特别特别痛心的语气说话吗?"]

*explicit_dialect string
*指定方言。
*beijing：北京话
*dongbei：东北话
*henan：河南话
*shaanxi：陕西话
*shanghai：上海话
*sichuan：四川话
*tianjin：天津话
*yue：粤语
*说明
*使用该参数时，speaker需要设置支持方言的音色。音色的详细情况请参见：音色列表

*confidence float
*时间戳置信度，范围 0~1

*响应
* 
* 
* 
* 
* 
* 

*audio_params object  
*音频参数
* 
* 
* 
* 
* 
* 

*disable_emoji_filter bool
*Emoji解析过滤参数，默认值为false
*true：启用后，系统会解析并去除文本中的Emoji符号
*false：停用后，系统会保留文本中的Emoji符号

*req_params object  
* 
* 
* 
* 
* 
* 

*max_length_to_filter_parenthesis int
*指定过滤括号内文本的长度，单位为字符，默认为0（即不过滤），推荐取值范围0~100
*说明
*该参数用于过滤文本中括号内的注释、补充说明等无需朗读的内容
*当括号内文本字符数超过设定值时，该括号的过滤功能将失效，括号内内容会被正常朗读。若存在较长的括号文本需要过滤，建议客户端在送入合成前自行完成前置过滤，以避免过滤失效及不必要的时延

*tone_fidelity bool
*开启还原模式，开启后模型将尽可能还原送入的prompt音频音色和说话风格（情感、韵律、口音等）
*默认值：false
*说明
*仅适用于豆包声音复刻大模型2.0音色
*仅支持合成和上传音频同语种的文本，不支持跨语种合成，不支持双向流合成接口

*section_id string
*配置段落标识，可用于保持跨包语义
*说明
*该参数仅豆包语音合成模型2.0音色、豆包声音复刻大模型2.0音色支持

* "req_params": {
*    "text": "我在北京说 omg",
*    "speaker": "zh_female_vv_uranus_bigtts",
*    "audio_params": {
*      "format": "mp3",
*      "sample_rate": 24000
*    },
*    "additions": "{\"pronunciation_dict\":{\"tone\":[\"北京/(bei3)(jing1)\",\"omg/oh my god\"]}}" 
*  }

*PayloadSize int
*返回的音频片段大小，单位是字节

*请求头
* 
* 
* 
* 

*X-Api-Resource-Id string  
*请求的模型版本，可选值：
*seed-tts-2.0:豆包语音合成大模型2.0，支持使用豆包语音合成模型2.0音色
*seed-icl-2.0:豆包声音复刻大模型2.0，支持使用声音复刻接口克隆的音色，具体音色详见控制台>音色库

*enable_auto_language_recognitionbool
*开启自动多语种识别，默认为false，开启后，系统将根据首句文本自动识别语种，并使用对应语种进行朗读
*说明
*指定语种的优先级高于自动多语种识别，当同时指定了explicit_language时，自动多语种识别不生效
*支持的语种与 explicit_language 一致（pt与es-es除外）
*自动识别语种时，葡萄牙语文本默认输出 pt-br（巴西口音），西班牙语文本默认输出 es-mx（墨西哥口音）。如需使用欧洲葡萄牙语pt或西班牙西班牙语es-es，须通过 explicit_language 参数显式指定
*中英模型（中文、英文）与小语种模型（日、韩、法语、西语等小语种）相互独立，各自仅对对应语种合成效果最佳

*format string
*指定音频格式，默认值为mp3，支持 mp3 / pcm / ogg_opus / wav
*说明
*流式场景推荐使用pcm，不建议使用wav

*content_propagator string
*指定内容传播服务提供者的名称或编码

*toneobject
*配置发音规则数组，支持发音修正与文本转写两类规则
*发音修正：原词/(拼音音节)，用于指定词汇的具体发音
*文本转写：原词/目标文本，用于将原词替换为目标文本后再合成
* 示例：
* 
*说明
*tone 中每条规则采用 原词/修正内容 格式，以/分隔。服务端按文本从左到右进行贪心最长匹配，存在多个可匹配词条时，优先匹配更长的原词
*最多支持配置 5000 个词条；每个原词长度不超过 9 个字符，不能为空、不能包含空格、不可重复
*仅豆包语音合成大模型2.0、豆包语音复刻大模型2.0对应的中英文音色支持
*命中发音字典规则的文本片段不支持 SSML 标签，同时使用时 SSML 标签将失效，建议二者择一

*MsgType string
*消息类型。响应消息类型有以下两种
*FullServerResponse：全量服务端响应
*AudioOnlyServer：仅音频服务端响应

**

*usage object
*本次请求的资源消耗统计
* 

*endTime float
*结束时间（秒）

*enable bool
*启用meta隐式水印，默认值：false

*silence_duration int
*配置文本末尾的静音时长，单位 ms，默认值为0，取值范围为[0,30000]

* 

*sample_rate int
*指定输出音频的采样率，单位为Hz，不同音频格式支持的采样率不同，详细如下：
*wav/pcm/mp3默认值为24000，取值范围为[8000,16000,22050，24000,32000,44100,48000]
*ogg_opus仅支持48000

*startTime float
*开始时间（秒）

*context_texts array
*配置语音指令
*示例：
* 
*说明
*仅speaker参数设置为豆包语音合成模型2.0音色时，支持使用语音指令
*该字段文字不参与计费

*additions string 
* 
* 
* 
* 
* 
* 
* 
* 
* 
* 
* 
* 
* 
* 
* 

*phonemes object
*音素相关时间戳

*propagate_id string
*指定自定义的内容传播编号

*model string
*指定模型版本，默认值为seed-tts-2.0-standard
*说明
*仅当speaker参数为复刻音色时需指定此参数，且指定后不支持使用语音指令context_texts

*post_process object
*后处理相关配置
* 

*SessionId string
*会话 ID，用于标识一次合成会话

*disable_markdown_filter bool
*Markdown解析过滤参数，默认值为false
*true：启用后，系统会解析并去除Markdown语法，例如" **你好** "朗读为 "你好"
*false：停用后，系统会保留原始字符，例如 " **你好** " 朗读为 "星星你好星星"

*latex_parser string
*启用Latex文本朗读能力功能。可取值：v2
*说明
*该参数适用于教育场景，启用后，会增加一定的时延。
*启用该参数时，需同时将disable_markdown_filter设置为true

*aigc_watermark bool
*启用AIGC生成标识，默认值：false。开启后，将在音频合成结尾添加节奏标识。

*aigc_metadata object
*在合成音频中添加meta水印，支持音频格式 mp3 / wav / ogg_opus
* 
* 
* 
* 
* 

*produce_id string
*指定自定义的内容制作编号

*text string  
*输入待合成的文本

*EventType string
*响应事件类型。包含以下几种事件：
*TTSSentenceStart：开始合成音频
*TTSResponse：音频合成内容
*TTSSentenceEnd：音频合成结束
*TTSSubtitle：返回音频合成字幕
*SessionFinished：会话结束

*X-Control-Require-Usage-Tokens-Return string
*若设置为*，将返回计费的字符数

*ssml string
*SSML标记文本，启用后将按SSML规则解析 text。SSML规则请参考：SSML标记语言
*说明
*目前仅中英文音色支持ssml，音色详情请参考：豆包语音合成模型2.0音色
*启用后需将disable_markdown_filter设置为false，否则此参数不生效

* 

*speech_rate int
*指定音频的语速，默认值为0，取值范围 [-50, 100]。其中，取值100代表2.0倍速，-50代表0.5倍速

*pronunciation_dictobject
*配置发音词典，修正指定文本的发音
* 

* 
*word string
*字

*loudness_rate int
*指定音频的音量，默认值为0，取值范围 [-50, 100]。其中，取值100代表2.0倍音量，-50代表0.5倍音量

*speaker string  
*指定音色 ID，具体的音色ID可从控制台 > 音色库获取

*bit_rate int
*指定音频比特率，单位 bps，不同音频格式对比特率支持的情况不同，详细如下：
*mp3：默认为64000 ，可选值[64000,160000]
*ogg_opus：可选值[64000,160000]
*wav/pcm：不支持指定比特率
*说明
*当设置disable_default_bit_rate为true后，可选值[16000,32000,64000,160000]

*X-Tt-Logid string
*服务端返回的 logid，用于在咨询或者反馈时定位问题

*content_producer string
*指定合成服务提供者的名称或编码

*text string
*合成音频文本

*explicit_language string
*指定朗读语种。开启后，仅朗读指定语种的文本，其他语种的内容会被跳过或合成失败，支持的语种如下：
*zh-cn：中文为主，支持中英混读
*en：英语
*ja：日语
*es-mx：墨西哥西语
*id：印度尼西亚语
*pt-br：巴西葡萄牙语
*pt：葡萄牙语
*ko：韩语
*it：意大利语
*de：德语
*fr：法语
*th：泰语
*vi：越南语
*ru：俄语
*fil：菲律宾语
*ms：马来语
*ar：阿拉伯语
*pl：波兰语
*tr：土耳其语
*sv：瑞典语
*nl: 荷兰语
*no: 挪威
*uk: 乌克兰语
*fi: 芬兰
*da: 丹麦
*cs: 捷克
*hu: 匈牙利
*el: 希腊
*ro: 罗马尼亚
*hi: 印度
*es-es: 西班牙西语
*说明
*输入文本语种须与 explicit_language 指定的语种一致，不一致时合成效果不予保证
*豆包语音合成模型 2.0 音色列表中，仅命名为zh_xxx_xxxx_uranus_bigtts的音色支持nl、no、uk、fi、da、cs、hu、el、ro、hi、es-es等语种

*Payload object
*当前事件携带的响应内容
* 
* 
* 
* 
*

*X-Api-Key string  
*API Key 可从 控制台>API Key管理 获取
*说明
*同时支持旧版控制台的鉴权方式，详见旧版控制台鉴权参考

*请求体
* 

*X-Api-Request-Id string  
*标识客户端请求ID，uuid随机字符串

*text_words int
*本次请求计费的文本字数（含标点）

*words object
*字级时间戳列表
* 
* 
* 
* 

*enable_subtitle bool
*启用字幕服务，开启后将返回字级别的时间戳，默认值为false
*说明
*仅支持中文和英文语种

*pitch int
*指定音调，默认值为0，默认不调整音调，取值范围：[-12,12]
*取值越大，音调越高（声音越尖锐、越明亮）；取值越小，音调越低（声音越低沉，越厚重）
