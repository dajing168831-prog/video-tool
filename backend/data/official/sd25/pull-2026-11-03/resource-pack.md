# Seedance 2.0-2.5 模型资源包使用规则

> 全部文档的索引见 [llms.txt](https://ark.volcengine.com/llms.txt)；在任一文档页面地址后追加 `.md` 可获取该页的 Markdown 版本。

本文档介绍了 Doubao Seedance 2.5、Doubao Seedance 2.0 系列模型资源包的购买规则、抵扣逻辑及注意事项。资源包采用**预付费**模式，仅用于抵扣在线推理产生的 Token 消耗。您可前往 [Seedance 系列资源包](https://console.volcengine.com/common-buy/ark_bd%7C%7Cd9li7rchmjlhari755h0) 进行选购。

> **注意**
>
> 1. 资源包自购买起 7 天内且额度未使用可申请全额退款；一经使用或超过 7 天，则不支持退订。请结合实际业务规模，选择匹配的规格。
> 2. 如果资源包全部到期或额度全部抵扣完后，若仍有超出部分，自动转为按量后付费。请在使用之前合理预估您的资源包与账号余额。
> 3. 为保障调用体验，部分资源包有起售个数限制，若您购买的是 700万 tokens 资源包，即购买了 7 个 100万 tokens 资源包；如需更高额度，您可叠加不同规格的 Tokens 资源包。

<span id="18df758c"></span>
# 规格选择

| | | | | | |
|模型 |资源包规格 |刊例价 |购买数量 |有效期 |抵扣范围 |
|---|---|---|---|---|---|
| | | | | | |
|Doubao Seedance 2.5 | 500万 Tokens |210元 |无限制 |90天 |可用于抵扣模型在线推理产生的 tokens 消耗 |
|^^| | | |^^|^^| \
| | 1000万 Tokens |420元 |无限制 | | |
|^^| | | |^^|^^| \
| | 1亿 Tokens |4200元 |无限制 | | |
|Doubao Seedance 2.0 | 100万 Tokens |28元 |为保障调用体验，7个起售 |90天 |可用于抵扣模型在线推理产生的 tokens 消耗 |
|^^| | | |^^|^^| \
| | 1000万 Tokens |280元 |无限制 | | |
|^^| | | |^^|^^| \
| | 1亿 Tokens |2800元 |无限制 | | |
|Doubao Seedance 2.0 fast | 100万 tokens  |22元  |为保障调用体验，9个起售  |90天 |可用于抵扣模型在线推理产生的 tokens 消耗 |
|^^| | | |^^|^^| \
| | 1000万 tokens  |220元  |无限制  | | |
|^^| | | |^^|^^| \
| | 1亿 tokens  |2200元  |无限制  | | |
|Doubao Seedance 2.0 mini | 1400万 tokens |196元 |无限制 |90天 |可用于抵扣模型在线推理产生的 tokens 消耗 |
|^^| | | |^^|^^| \
| | 1000万 tokens |140元 |为保障调用体验，2个起售 | | |
|^^| | | |^^|^^| \
| | 1亿 tokens |1400元 |无限制 | | |

<span id="4edd4c0b"></span>
# Tokens 抵扣规则

资源包用于直接抵扣模型产生的 Tokens 消耗。由于 Seedance 系列模型包含不同的输入场景（如含视频输入、无视频输入）且各场景的 Tokens 单价不同，因此抵扣比例也会进行相应的换算。
为了方便理解，资源包统一以单价较低的‘含视频输入’场景作为 1:1 抵扣标准。也就是说，当您在单价更高的‘无视频输入’场景下创作时，实际消耗 1 Token，将会按单价比例自动折算，扣除多于 1 资源包 Tokens。

| | | | | | |
|模型资源包 |创作场景 |视频分辨率 |Tokens 单价 |抵扣比例 |抵扣说明 |
|---|---|---|---|---|---|
| | | | | | |
|Doubao Seedance 2.5 资源包 |含视频输入 |480P/720P |0.042 元 / 千 Tokens |1 : 1  |消耗 1 Token = 消耗 1 资源包额度 |
|^^| | | | | | \
| |无视频输入 |480P/720P |0.070 元 / 千 Tokens |1 : 1.6667  |消耗 1 Token ≈ 消耗 1.6667 资源包额度 |
|^^| | | | | | \
| |含视频输入 |1080P |0.046 元 / 千 Tokens |1 : 1.0952 |消耗 1 Token = 消耗 1.0952 资源包额度 |
|^^| | | | | | \
| |无视频输入 |1080P |0.077 元 / 千 Tokens |1 : 1.8333 |消耗 1 Token ≈ 消耗 1.8333 资源包额度 |
|Doubao Seedance 2.0 资源包 |含视频输入 |480P/720P |0.028 元 / 千 Tokens |1 : 1  |消耗 1 Token = 消耗 1 资源包额度 |
|^^| | | | | | \
| |无视频输入 |480P/720P |0.046 元 / 千 Tokens |1 : 1.6429  |消耗 1 Token ≈ 消耗 1.6429 资源包额度 |
|^^| | | | | | \
| |含视频输入 |1080P |0.031 元 / 千 Tokens |1 : 1.1071 |消耗 1 Token ≈ 消耗 1.1071 资源包额度 |
|^^| | | | | | \
| |无视频输入 |1080P |0.051 元 / 千 Tokens |1 : 1.8214 |消耗 1 Token ≈ 消耗 1.8214 资源包额度 |
|^^| | | | | | \
| |含视频输入 |4K |0.016 元 / 千 Tokens |1 : 0.5714 |消耗 1 Token ≈ 消耗 0.5714 资源包额度 |
|^^| | | | | | \
| |无视频输入 |4K |0.026 元 / 千 Tokens |1 : 0.9286 |消耗 1 Token ≈ 消耗 0.9286 资源包额度 |
|Doubao Seedance 2.0 fast 资源包 |含视频输入 |480P/720P |0.022 元 / 千 Tokens |1 : 1  |消耗 1 Token = 消耗 1 资源包额度 |
|^^| | | | | | \
| |无视频输入 |480P/720P |0.037 元 / 千 Tokens |1 : 1.6819  |消耗 1 Token ≈ 消耗 1.6819 资源包额度 |
|Doubao Seedance 2.0 mini 资源包 |含视频输入 |480P/720P |0.014 元 / 千 Tokens |1 : 1 |消耗 1 Token = 消耗 1 资源包额度 |
|^^| | | | | | \
| |无视频输入 |480P/720P |0.023 元 / 千 Tokens |1 : 1.6429 |消耗 1 Token ≈ 消耗 1.6429 资源包额度 |

# 模型开通、使用与资源包购买关系说明

## Seedance 2.5 与 Seedance 2.0 系列模型开通
满足以下 **任意一项**，即可开通 Seedance 2.0 系列模型与 Seedance 2.5 模型：

1. 账户余额 > 200 元 ([充值入口](https://console.volcengine.com/finance/fund/recharge))
2. 购买了 Seedance 2.5 资源包，且**当前有余量** ([资源包购买入口](https://console.volcengine.com/common-buy/ark_bd%7C%7Cd9li7rchmjlhari755h0))
3. 购买了 Seedance 2.0 资源包，且**当前有余量** ([资源包购买入口](https://console.volcengine.com/common-buy/ark_bd%7C%7Cd9li7rchmjlhari755h0))
4. 购买了 Seedance 2.0 Fast 资源包，且**当前有余量** ([资源包购买入口](https://console.volcengine.com/common-buy/ark_bd%7C%7Cd9li7rchmjlhari755h0))
5. 购买了 Seedance 2.0 Mini 资源包，且**当前有余量** ([资源包购买入口](https://console.volcengine.com/common-buy/ark_bd%7C%7Cd9li7rchmjlhari755h0))

开通后，即开启该系列模型的**后付费**使用。

## Seedance 2.0 与 2.5 系列模型调用

开通之后，每次调用按**调用的具体模型**结算，资源包仅支持**抵扣对应的模型**：

| 调用的模型 | 可用扣费来源 |
|---|---|
| Seedance 2.5 | Seedance 2.5 资源包余量 / 账户余额 |
| Seedance 2.0 | Seedance 2.0 资源包余量 / 账户余额 |
| Seedance 2.0 Fast | Seedance 2.0 Fast 资源包余量 / 账户余额 |
| Seedance 2.0 Mini | Seedance 2.0 Mini 资源包余量 / 账户余额 |

<span id="c6b8968b"></span>
# 使用说明

1. **生效时间**：资源包购买后立即生效，无需手动“激活”或“绑定”。有效期90天，超出有效期后，资源包中剩余的Tokens，自动作废。
2. **结算说明**：资源包不支持叠加使用代金券结算。页面价格仅供参考，请以结算时的最终成交价格为准。
3. **退订说明**：资源包属于七天无理由退款商品。在新购7天内且未使用，可前往 [退订管理](https://console.volcengine.com/finance/unsubscribe/) 申请无理由全额退款，已使用资源包不支持退订，购买超过7天资源包不支持退订。
4. **扣费顺序**： 付费资源包 > 按 token 后付费。若您存在多个同类型的资源包：优先抵扣先到期的资源包。若到期时间相同，则优先抵扣先购买的资源包。
5. **用量超出说明**：如果资源包全部到期或额度全部抵扣完后，若仍有超出部分，自动转为按量付费。

<span id="9cba0781"></span>
# 使用指南

<span id="994b8220"></span>
## 1. 开通模型

购买成功后，按照以下步骤操作：
* **开通模型**：前往 [火山方舟-开通管理](https://ark.volcengine.com/region:cn-beijing/openManagement?LLM=%7B%7D&advancedActiveKey=model&tab=ComputerVision) 开通对应模型
* **接入调用**：[获取 API Key ](https://ark.volcengine.com/region:cn-beijing/apiKey?apikey=%7B%7D) 后即可发起在线推理请求
* **抵扣逻辑**：您购买的资源包将**自动抵扣对应模型**产生的在线推理消耗

<span id="92ee8753"></span>
## 2. 管理与监控

您可以实时掌握使用进度：
* **路径**：前往 [费用中心->资源包管理](https://console.volcengine.com/finance/resource-package) 。
* **功能**：查看当前资源包实例的余量等状态信息。

<span id="da927ad8"></span>
## 3. 相关文档引导

了解更多模型使用详情，请参考以下官方文档：
* [**模型计费信息**](/docs/model-pricing#02affcb8)：查看 Token 计费与估算方式，方便您直观了解不同规格的视频成本。
* [创建视频生成任务](/docs/create-video-generation-task-api)：获取接口接入指南及技术开发文档。
* [**Seedance 2.5 教程**](/docs/seedance-2-5)：介绍 Seedance 2.5 模型的特色能力与使用方法，帮助您快速实现 [Video Generation API](/docs/create-video-generation-task-api) 调用。
* [**Seedance 2.5 系列提示词指南**](/docs/seedance-2-5-prompt-guide)：介绍 Seedance 2.5 的提示词使用方法和相关技巧，帮助您更高效地利用该模型生成符合需求的优质视频作品。
* [**Seedance 2.0 系列教程**](/docs/seedance-2-0)：介绍 Seedance 2.0 系列模型的专属能力，帮助您快速实现 [Video Generation API](/docs/create-video-generation-task-api) 调用。
* [**Seedance 2.0 系列提示词指南**](/docs/seedance-2-0-prompt-guide)：介绍 Seedance 2.0 的提示词使用方法和相关技巧，帮助您更高效地利用该模型生成符合需求的优质视频作品。

# 常见问题

## 为什么购买了资源包，但没有抵扣？

资源包的抵扣需要满足特定条件，常见原因如下：

1. 模型不匹配：您调用的模型与购买的资源包不一致。例如，购买 Seedance 2.0 资源包却调用了 Seedance 2.5 模型。
2. 使用了不支持的功能：资源包仅支持抵扣在线推理的 tokens 消耗。

**特别说明**： 
1. 多个账户通过同一手机号、同一证件号、同一账号ID，或其他经火山引擎排查多个账户为同一实际控制主体的，均视为“同一用户”。 
2. 对恶意抢占活动资源、批量刷单及其他任何采用非常规手段影响活动公平性的行为，火山引擎有权取消从事违法违规行为的用户活动资格并回收实例资源，必要时追究违规用户的法律责任。 
3. 用户不得将火山引擎云产品和服务用于任何违法违规或侵犯第三方合法权益的用途，如因此产生的法律责任，由用户自行承担责任，与火山引擎无关。 
4. 火山引擎可以根据运营情况对活动进行变更或调整，包括不限于活动规则、商品价格、商品数量等，请以页面最新内容为准。用户在活动规则变更或调整前已经获得的权益不受影响。
