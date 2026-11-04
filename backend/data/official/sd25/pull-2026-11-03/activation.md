# Seedance 2.5 与 Seedance 2.0 系列模型开通、使用与退订说明

> 全部文档的索引见 [llms.txt](https://ark.volcengine.com/llms.txt)；在任一文档页面地址后追加 `.md` 可获取该页的 Markdown 版本。

本文介绍 Seedance 2.5、Seedance 2.0、Seedance 2.0 mini 与 Seedance 2.0 fast 模型的开通条件、计费方式、抵扣顺序及退订规则。

# 开通模型

## 满足开通门槛

满足以下任意一项，即可开通 Seedance 2.5、Seedance 2.0、Seedance 2.0 mini 与 Seedance 2.0 fast 模型。

| 开通方式 | 门槛条件 | 有效期 | 适用范围 | 充值或购买入口 |
| --- | --- | --- | --- | --- |
| 账户余额（推荐） | 账户可用余额达到 **200 元** | 无限制 | 余额可抵扣火山引擎产品 | [账户充值](https://console.volcengine.com/finance/fund/recharge) |
| 节省计划（推荐） | 购买 **200 元**及以上规格的专属递减型节省计划，且当前有余额 | * 200 元专属递减型节省计划有效期为 30 天<br>* 500 元、1000 元专属递减型节省计划有效期为 90 天 | 抵扣火山方舟全部模型，包括 Seedance 全系列及语言、图像、语音模型 | * [购买节省计划](https://console.volcengine.com/common-buy/AI-SavingsPlans%7C%7Cd682ppeeq1mp7kd5q0e0)<br>* [更高规格节省计划购买](https://www.volcengine.com/product/ai-savingsplans) |
| 资源包 | 购买 **200 元**及以上的模型资源包，且当前有余量 | 90 天 | 仅抵扣对应的单一模型 | [资源包规则](/docs/seedance-2-0-model-resource-pack-rules) |

## 开通模型

1. 前往 [开通管理](https://ark.volcengine.com/region:cn-beijing/openManagement?LLM=%7B%7D&advancedActiveKey=model&tab=ComputerVision)，开通对应模型。
2. 前往 [API Key 管理](https://ark.volcengine.com/region:cn-beijing/apiKey?apikey=%7B%7D)获取 API Key，发起在线推理请求。

# 计费与使用

开通后即开启模型按 token 付费使用：每次调用按该次实际调用的模型及 token 用量结算，并按固定顺序自动抵扣。

## 抵扣顺序

调用产生的费用，按以下顺序自动抵扣：
1. 资源包：若该模型有对应资源包且有 tokens 余量，优先抵扣。
2. 节省计划：若已购买节省计划且有余额，那么节省计划余额可抵扣按量后付费账单。
3. 账户余额（即按量后付费）：按实际 token 用量出账，实时扣除账号余额。

## 对比付费方式

| 付费方式 | token 用量统计 | 余量管理与监控 |
| --- | --- | --- |
| 资源包 | 前往 [用量统计](https://ark.volcengine.com/region:cn-beijing/usageTracking?usageTrackingTab=model)，查看当前模型的 token 用量 | 前往 [资源包管理](https://console.volcengine.com/finance/resource-package)，查看资源包实例的余量、有效期等状态 |
| 节省计划 | ^^ | 前往 [节省计划](https://console.volcengine.com/finance/saving-plan)，查看节省计划余额、有效期等状态 |
| 账户余额 | ^^ | 前往 [账号总览](https://console.volcengine.com/finance/account-overview)，查看当前账户余额 |

## 模型相关文档引导

了解更多模型使用详情，请参考以下官方文档：

- [模型计费信息](/docs/model-pricing#02affcb8)：查看 token 计费与估算方式，方便您直观了解不同规格的视频成本。
- [Video Generation API](/docs/create-video-generation-task-api)：获取接口接入指南及技术开发文档。
- [Doubao Seedance 2.5 教程](/docs/seedance-2-5)：介绍 Seedance 2.5 模型的特色能力与使用方法，帮助您快速实现 Video Generation API 调用。
- [Doubao Seedance 2.5 提示词指南](/docs/seedance-2-5-prompt-guide)：介绍 Seedance 2.5 的提示词使用方法和相关技巧，帮助您更高效地利用该模型生成符合需求的优质视频作品。
- [Doubao Seedance 2.0 系列教程](/docs/seedance-2-0)：介绍 Seedance 2.0 系列模型的专属能力，帮助您快速实现 Video Generation API 调用。
- [Doubao Seedance 2.0 系列提示词指南](/docs/seedance-2-0-prompt-guide)：介绍 Seedance 2.0 的提示词使用方法和相关技巧，帮助您更高效地利用该模型生成符合需求的优质视频作品。

# 退订与提现

| 类型 | 退订或提现规则 |
| --- | --- |
| 账户余额 | 模型实例处于开通状态时，账户余额中不超过 200 元的部分不可提现，超过 200 元的部分可正常提现。关闭模型实例后，被锁定的不超过 200 元部分也可提现。<blockquote>前往 [开通管理](https://ark.volcengine.com/region:cn-beijing/openManagement?LLM=%7B%7D&advancedActiveKey=model&tab=ComputerVision)关闭模型实例。</blockquote> |
| 节省计划 | 购买超过 7 天或一经使用，即不可退订 |
| 资源包 | 购买超过 7 天或一经使用，即不可退订 |
