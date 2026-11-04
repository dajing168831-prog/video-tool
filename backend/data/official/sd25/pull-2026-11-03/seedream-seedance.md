# Seedream 4.0 助力 Seedance 生视频最佳实践

> 全部文档的索引见 [llms.txt](https://ark.volcengine.com/llms.txt)；在任一文档页面地址后追加 `.md` 可获取该页的 Markdown 版本。

本文介绍如何利用 Doubao Seedream 4.0 精准控制图片（关键帧）的内容，辅助与优化 Seedance 的视频生成流程，为您生成理想视频提供关键助力。

<span id="b27a21f5"></span>
# 助力首帧生视频

Seedream 4.0具备强大的多图融合能力，能够将多张不同风格、不同主题的图片进行有效融合，生成具有独特视觉效果且符合特定需求的图像，为视频制作提供多样化的素材。 

|参考图 |使用 Seedream 4.0 的 多图融合 能力制作首帧 |首帧生视频效果 |
|---|---|---|
|![](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/655a21d997f74182aff261e2ae386dd2~tplv-goo7wpa0wc-image.image) |![](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/32403c7297c0499689f066b32199dd4d~tplv-goo7wpa0wc-image.image) |[视频](https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/7ec686cd8a4e4a47961d3f6012db4a46) | \
| | | | \
| |> 女子和男子御剑飞行。白衣古风女子身姿轻盈地立于长剑之上御剑凌空，图右边男子在她身后紧张地扶着她的腰，脸上满是慌张。 |> 女子和男子御剑飞行。白衣古风女子身姿轻盈地立于长剑之上御剑凌空，图右边男子在她身后紧张地扶着她的腰，脸上满是慌张。长剑载着二人在云雾缭绕的天际疾飞，云海翻涌如浪，剑光闪烁间，女子从容淡定，男子慌张。 |
|![](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/7aeaec785b59417881fff70cbb40b798~tplv-goo7wpa0wc-image.image) |![](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/4c5fc210bca04ad9ae9f855075067eb0~tplv-goo7wpa0wc-image.image) |[视频](https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/9b1ba4129c034085b408c8c37ad21d57) | \
| | | | \
| |> 女人站在莲蓬头下，侧脸对着镜头，镜头显示头部特写，女人自在地洗头，双手缓慢地搓着头发，头发上大量洗发水白色泡沫，莲蓬头的水从高处淋下，水量非常大，背景是放置在身后墙角托盘上的一瓶洗发水，洗发水的正面对着镜头。 |> 女人站在莲蓬头下，侧脸对着镜头，镜头显示头部特写，女人自在地洗头，双手缓慢地搓着头发，头发上大量洗发水白色泡沫，莲蓬头的水从高处淋下，水量非常大，背景是放置在身后墙角托盘上的一瓶洗发水，洗发水的正面对着镜头。生成视频中的主体必须与参考图中的主体完全一致。 | \
|![](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/4c897f539323441f892d3422c8dfb807~tplv-goo7wpa0wc-image.image) | | |

Seedream 4.0具备强大的语意理解能力，能够根据提示词精准地生成与之匹配的图像，为您提供更贴合需求的图像素材，进一步提升视频制作的效率和质量。 

|使用 Seedream 4.0 的 文生图 能力制作首帧 |首帧生视频效果 |
|---|---|
|![](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/70b8ab4a7f7d4a6794de18dd950f6b9c~tplv-goo7wpa0wc-image.image) |[视频](https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/ac439104ef1d4df6a1429cfc272558fd) | \
| | | \
|> 深夜，黑白红外线摄像头，2只土拨鼠在户外院子里的蹦床上蹦跳，蹦床占画面下侧，土拨鼠比较小，低画质有噪点。 |> 深夜，黑白红外线摄像头，2只土拨鼠在户外院子里的蹦床上快乐蹦跳。 |
|![](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/b6fde2866de344888d0112694630ce20~tplv-goo7wpa0wc-image.image) |[视频](https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/b8a27a358d6e455d925e5086dfd6943e) | \
| | | \
|> 真实夜间摄像头的红外黑白视角镜头，月球表面场景中远处有人在行走，低分辨率噪点，黑白灰度，红外热感成像，远处人物轮廓模糊，月球表面岩石纹理，荒凉氛围。 |> 固定镜头，噪波抖动，月球表面场景中远处有人在行走。 |
|![](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/609fe311886f45d687741fcc597a4e7a~tplv-goo7wpa0wc-image.image) |[视频](https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/eed705156ff84128a7916d4974d1e783) | \
| | | \
|> 鱼眼广角摄像头监控画面，一只狗熊偷吃家门口的糖果被万圣节装饰物：一个巫师假人吓到。监控画质，低清。 |> 低清画质。巫师突然把手伸直，眼睛的红色灯泡亮起。狗熊吓得高高跳起，嘴里的糖果掉出来，狗熊连连后退。 |

<span id="c498b819"></span>
# 助力首尾帧生视频

在「首尾帧生视频」的制作流程中，生成符合预期的首尾帧画面是输出高质量视频的关键。借助「Seedream 4.0」强大的图像生成与控制能力，您可以高效构建高质量的首尾帧内容，从而实现更好地控制视频生成效果。
该方案具有以下核心优势：
* **出色的主体一致性**：能够确保视频在首帧与尾帧之间，主体（如人物）的样貌、服饰、妆造等细节高度统一，有效维持视觉叙事的连贯性与专业性。
* **灵活的画面控制力**：即使首尾帧在服饰、场景、景别或视角上存在较大差异，Seedream 4.0 也具备充分的画面编辑与细节刻画能力，助您精准实现跨越式的画面转换，完成符合剧情或创意需求的首尾帧设计。
* **多样的风格化支持**：在各类风格化影视制作中，Seedream 4.0 都能生成相应风格的首尾帧画面，满足多样化项目的视觉创作需求。

<span id="61012397"></span>
## 生动运动

> **说明**
>
> **人物动作类** **Prompt** **= 主体 + 主体从首帧到尾帧的详细动作变化描述 + 运镜**

|首帧 |使用 Seedream 4.0 制作尾帧 |首尾帧生视频效果 |
|---|---|---|
|![](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/763a3d54edf64a66a340d054789e203c~tplv-goo7wpa0wc-image.image) |![](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f932ffcf34d045168749f14048bb2203~tplv-goo7wpa0wc-image.image) |[视频](https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/fe5443800b60497bb85eee3f3b4dfbdd) | \
| | | | \
| |> 女生带着滑板跳到栏杆上，背面中景视角。 |> 女生在滑滑板，她跳到栏杆上，镜头跟随转到她背后。 |
|![](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/74fda8d1bdb449318fe204244c499818~tplv-goo7wpa0wc-image.image) |![](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/a586e97f1da24c90bb16eff389691529~tplv-goo7wpa0wc-image.image) |[视频](https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/28ebb030f8034676a7802b51795f845c) | \
| | | | \
| |> 生成这个人物10s后的滑雪画面，广角镜头。 |> 滑雪运动员在雪山上滑雪，速度飞快，镜头跟随人物运动到侧面俯视视角。 |

<span id="d8885182"></span>
## 角色变装

> **说明**
>
> **Prompt中可以加入首帧和尾帧的主体妆造，以及场景的变化。或者通过，「360度环绕运镜」「主体原地转身」、「走出/入画面」这样的衔接词语，来让视频的过渡更自然**。

|首帧 |使用 Seedream 4.0 制作尾帧 |首尾帧生视频效果 |
|---|---|---|
|![](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/0bc3df12e80c4772aa626b1a91a6da24~tplv-goo7wpa0wc-image.image) |![](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/3f70661893d44ff0987129a9d290a80f~tplv-goo7wpa0wc-image.image) |[视频](https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/8e1eafc90dd6448f89f0cd4f41b16ce1) | \
| | | | \
| |> 保持3D卡通画风，棕色的小豚鼠穿着白色的厨师服，站在厨房里面炒菜。 |> 3D卡通画风，一只棕色的小豚鼠原地向前跑出画面，后穿着白色的厨师服又走入画面，在厨房里面炒菜。 |
|![](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ea6292db97e946fda6d18a1a0a3f5141~tplv-goo7wpa0wc-image.image) |![](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/8acfdbab83a6435e9db845261b38aae5~tplv-goo7wpa0wc-image.image) |[视频](https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/c44cc99e61f94ccd9151afe6669ef817) | \
| | | | \
| |> 保持镜头视角，背景切换为傍晚的富士山，女生穿着和服在镜头前摆剪刀手自拍。 |> 360度环绕运镜。 |

<span id="d1c38484"></span>
## 影视级运镜

> **说明**
>
> **Seedance 能够提供非常流畅的首尾帧间的过渡效果，对于运镜，仅需简要描述所需运镜效果即可**。

|首帧 |使用 Seedream 4.0 制作尾帧 |首尾帧生视频效果 |
|---|---|---|
|![](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/cd014efa8ba944a581f984a6808e318d~tplv-goo7wpa0wc-image.image) |![](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/70525b3b28fb40c7be40c3a5ab1726d5~tplv-goo7wpa0wc-image.image) |[视频](https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/624cbf6ec9c247698c8b56258c5b0631) | \
| | | | \
| |> 图片拉近到后方建筑的阁楼，一个穿着白衣的女子，推开了阁楼的门，中景视角。 |> 镜头环绕推进，聚焦画面后方的建筑，一个穿着一身白衣的女生，推开了阁楼的门。 |
|![](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/8b5db28646044a40bee9470d81eb160a~tplv-goo7wpa0wc-image.image) |![](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ec7de93162ea4ca1901196e95c6422a3~tplv-goo7wpa0wc-image.image) |[视频](https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/dce1ef2883f04aa687de9db4088ad2a4) | \
| | | | \
| |> 镜头拉近到近景，男人抬起了头，正面面对镜头，紧皱眉头。 |> 镜头推进，男人缓缓抬头。 |

<span id="2d9cf6f1"></span>
## 商品展示

> **说明**
>
> **结合 Seedream 4.0 ，首尾帧能够很好的保持商品的细节，保证在广告素材的生产中的高可用性。此外，还可以完成商品不同状态的展示，比如下文所展示的商品开箱**。

|首帧 |使用 Seedream 4.0 制作尾帧 |首尾帧生视频效果 |
|---|---|---|
|![](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/7e710f71b6c44413a13e5a2f723207f5~tplv-goo7wpa0wc-image.image) |![](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/c9028bcb303045b6b3701a4bbd9d53b5~tplv-goo7wpa0wc-image.image) |[视频](https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/5d1fd88457e34f5daae94fed478a8e5f) | \
| | | | \
| |> 俯视视角，从上往下拍摄，洗发露平放在水面中，周围布满白色的花瓣。 |> 镜头转换为俯视视角拍摄洗发露，洗发露瓶子自然下落到水面上，溅起一圈圈波纹，周围缓慢掉落白色花瓣，散落在瓶子周围。 |
|![](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ed8ff74d88a7468a8d629bed9acf336f~tplv-goo7wpa0wc-image.image) |![](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/41ee7bd2568a4eed8fea56756dc0d61d~tplv-goo7wpa0wc-image.image) |[视频](https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/122b4e4f50804a19867ad2e35152a3c3) | \
| | | | \
| |> 去掉礼盒封面的图案，礼盒打开，保持其尺寸不变，画面聚焦展示礼盒内整齐摆放的各种月饼、点心。 |> 一只手伸入画面打开礼盒，展示礼盒里面的点心。 |

<span id="d31b8648"></span>
## 风格化创意视频

> **说明**
>
> 对于各类风格化视频，「首尾帧生视频」相较于「图生视频」能够更好的控制画面的风格保持一致

|首帧 |使用 Seedream 4.0 制作尾帧 |首尾帧生视频效果 |
|---|---|---|
|![](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/4f850b61c60c4568886bfe569167e504~tplv-goo7wpa0wc-image.image) |![](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/8b398ce150d44be19237ae36dc103ad9~tplv-goo7wpa0wc-image.image) |[视频](https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/624b1978e7e3430aa79915e5b34e5553) | \
| | | | \
| |> 极繁主义，复古插画，时尚插画，丛林中飞翔在空中的蓝白色雄鹰，特写，白色的天空，橙色的丛林，盛开的奇花异草。梦幻般的风格。 |> 一只猎豹360度原地转身，之后变身成一只在天空中飞翔的鹰，画面过渡流畅自然。 |
|![](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/d2088dc775a142488e8c669aba1f4ccb~tplv-goo7wpa0wc-image.image) |![](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/6d06e5345f8c4e42ac3334ddb933b542~tplv-goo7wpa0wc-image.image) |[视频](https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/dc1a32af5d79499eb2ec5328033441f1) | \
| | | | \
| |> 肆意泼墨风格，一朵朵红色花瓣四散纷飞，落在水面上，背景大面积留白。 |> 画面风格保持一致，女子渐渐消逝在画面中，化为一朵朵红色花。 |

<span id="2cb74c01"></span>
# 助力多参考图生视频

Seedream 4.0具备强大的组图生成能力，对同一个主体可支持多个分镜的图像生成，且生成的图像能在风格、色调等方面保持高度一致，有效满足多参考图生视频的需求。 

|参考图 |使用 Seedream 4.0 生成 组图 |多参考图生视频效果 |
|---|---|---|
|![](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/c7ddd4cfe9e240be823489edb3a5763f~tplv-goo7wpa0wc-image.image) |![](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/23f3b13d9c9e4c1cab8a7dfc1714d1c8~tplv-goo7wpa0wc-image.image) |[视频](https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/e32b52bdd8844609b7cfdb4276e0c3d9) | \
| | | | \
| | |> 镜头急速前冲贴近吉他手拨弦的手指 ， 镜头切换到这个人正在打架子鼓，镜头切换到这个人正在弹键盘。 | \
| |![](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/029a0b9ac37c4e4f893ea81146af3b72~tplv-goo7wpa0wc-image.image) | | \
| | | | \
| | | | \
| |![](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/74ff4543184c4c1a9776d38c541273be~tplv-goo7wpa0wc-image.image) | | \
| | | | \
| |> 生成这个人物在打架子鼓、弹键盘、弹吉他 | |

<span id="ad15766e"></span>
# 注意事项

在使用 Seedream 4.0 辅助生成视频时，需注意以下几点，以确保最终视频效果符合预期：
1. **宽高比匹配**

> Seedream 4.0支持生成的图像尺寸信息，详见[图片生成 API](/docs/image-generation-api)

> Seedance支持生成的视频尺寸信息，详见 [创建视频生成任务 API](/docs/create-video-generation-task-api)

在使用 Seedream 4.0 生成用于生视频的图片时，需注意图片宽高比与最终视频所需的宽高比之间的差异，避免因宽高比差异过大导致视频画面裁剪或变形等问题。 
2. **理解创作意图**

Seedream 4.0 具备深度理解能力，可基于线稿图、轮廓图、深度图等输入素材进行延伸创作，准确响应画面生成需求。
3. **提示词建议**

在生成图片的提示词中，可明确加入“视频静帧画面”等说明，以引导模型生成更适配视频生成的图像内容。
4. **视频时长与帧数控制**
* 视频生成的帧数可通过 `frames` 参数灵活控制，当前可支持 2–12 秒的视频生成。具体可参考 [创建视频生成任务 API](/docs/create-video-generation-task-api)。
* 结合 Seedream 生成的关键帧与 Seedance 的精准时长控制，可实现对视频内容与节奏的精细化把控。
