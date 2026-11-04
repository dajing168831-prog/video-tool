# 虚拟人像库

> 全部文档的索引见 [llms.txt](https://ark.volcengine.com/llms.txt)；在任一文档页面地址后追加 `.md` 可获取该页的 Markdown 版本。

体验中心提供可用于 Doubao Seedance 2.0 和 Doubao Seedance 2.5 视频生成的可信虚拟人像库，您可在体验中心浏览和检索虚拟人像，在视频生成中使用所选人像素材，并结合模板和自有素材快速验证视频效果。
同时，体验中心还提供类型丰富的视频生成模板。您可查看模板使用的素材，并一键获取模板同款示例代码。

> Tip：您可在 [创建视频生成任务 API](/docs/create-video-generation-task-api) 中使用虚拟人像素材生成视频，具体方式请参考[使用预置虚拟人像](/docs/seedance-portrait-asset-guide#preset-avatar)。

> **注意**
>
> * 火山方舟努力为用户呈现更多元化的内容。如您对本功能有任何意见或建议，欢迎提交 [工单](https://console.volcengine.com/auth/login?redirectURI=%2Fworkorder%2Fcreate%3Fstep%3D2%26SubProductID%3DP00001166) 或联系 Support 反馈。我们将仔细阅读和评估您的反馈，并尽快处理。
> * 为确保合规使用本功能，请在使用前阅读[火山方舟体验中心服务规则和免责声明](/docs/volcengine-ark-experience-center-terms-and-disclaimer)。

<span id="901571f6"></span>
## 关于虚拟人像库

虚拟人像库提供了丰富的虚拟人像素材资源。每个虚拟形象包含一张或多张图片素材。您可以将选定的虚拟人像素材发送给模型，并结合指令生成包含该形象的视频。

![](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/06d28d889dd0494c9a1788deeb84fe1d~tplv-goo7wpa0wc-image.image)

每个虚拟人像素材对应一个资产 ID。在使用视频生成 API 时，可使用包含该 ID 的 URI 将对应素材传入模型。
平台还提供了丰富的非人像类素材，可在 **素材库** 查看其资产 ID 和 URI。

您可在体验中心检索虚拟人像，查看各人像素材的资产 ID，并将所选素材快速应用于视频生成任务。

> **说明**
>
> * 首次使用虚拟人像库时，需先同意相关协议，才可正常浏览和使用人像素材。

<span id="b2049b21"></span>
## 浏览和检索虚拟人像

1. 在浏览器中打开火山方舟 [体验中心](https://ark.volcengine.com/region:cn-beijing/experience/gen_video?model=doubao-seedance-2-0-260128)，点击输入框下方的 **虚拟人像库** 页签。
2. 检索要使用的人像，支持自然语言检索和条件筛选。

    1. 自然语言检索示例：“积极阳光的青春男大，身高 180 cm 左右”

    2. 使用右侧筛选框，以人物性别、年龄、国籍维度进行筛选。 
3. 点击一个虚拟人像，查看详情。可在右侧切换人像素材。

4. 选择所需人像素材后，点击 **使用** 图标，将该素材添加至输入框。在输入框中使用“@+素材名”格式引用素材，例如：

> ***@图片 1*** *中女主转身坐下，转镜头，女主下了一步棋子，并说“你输了”，参考* ***@图片 2*** *的分镜画面...*

> **说明**
>
> 默认单次生成 4 段视频，为节约成本，建议设置为每次生成一段视频。

5. 点击输入框右下角的发送图标，开始视频生成。

<span id="58715d25"></span>
## 快速获取模板库示例代码

Seedance 2.0 和 Seedance 2.5 体验中心提供视频生成模板库，每个模板包含完整指令和素材。您可使用模板一键生成，或基于模板，结合虚拟人像、自定义内容生成视频。
同时模板库支持查看模板的 REST API 调用示例。可直接复制示例命令进行测试。
参考以下步骤，快速查看示例代码：
1. 在 Seedance 2.0 和 Seedance 2.5 体验中心界面，点击下方的 **模板库** 页签。
2. 将鼠标悬停在模板上，点击 **查看代码** 图标，即可查看和复制命令。

**注意**：测试前需先设置 `ARK_API_KEY` 环境变量，或将 `$ARK_API_KEY` 替换为您的 API Key。

<div style="text-align: center">![](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/1344a21f888e4249b11b6c3694a094d3~tplv-goo7wpa0wc-image.image)</div>
