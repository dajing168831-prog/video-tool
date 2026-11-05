# 素材库数据看板和告警设置

> 全部文档的索引见 [llms.txt](https://ark.volcengine.com/llms.txt)；在任一文档页面地址后追加 `.md` 可获取该页的 Markdown 版本。

<span id="intro"></span>
# 简介

素材资产库数据看板用于展示素材库资源使用情况和素材库 API 接口调用情况，帮助您了解当前账号下素材资产相关的关键数据指标。您还可以根据业务场景，按需设置告警。

通过看板可查看以下信息：
* **指标概览**：`CreateAsset` 实时 QPM、配额使用率、素材总量、素材资产上限、素材资产实时利用率等指标，便于评估素材库容量使用情况。
* **API 调用统计**：展示 `CreateAsset` 接口的调用量和配额使用率，便于监控素材上传及管理接口的运行情况。
* **稳定性**：按时间范围查看请求成功率、错误率数据。
* **用量统计**：按时间查看素材资产用量、使用率数据。

<span id="entrance"></span>
# 看板入口

点击 [素材库数据看板](https://console.volcengine.com/observe/dashboard/dashboard/2386/view?type=builtin&var-iam_account=$__all) 访问看板。

> **说明**
>
> 使用监控看板，需先开通托管 Prometheus 服务。开通方式：进入方舟控制台，选择 **在线推理** ＞ **模型推理接入点**，打开任意接入点，进入 **监控** 页面并按页面提示开通。开通后，即可访问素材库数据看板查看相关监控数据。
>
> ![开通看板功能示意图](https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/screenshot-20260713-195740.png)

# 定制告警规则

您可以使用预置模板，设置 **`CreateAsset` 接口 QPM**、**请求错误率**以及**素材库总资产数**的告警规则。

1. 打开 [告警规则模板](https://console.volcengine.com/observe/prometheus/region:prometheus+cn-beijing/alert/rule_template?category=ARK&tab=preset)。
2. 在 **火山方舟** 模板分类中，找到 **方舟素材资产库告警模板**，点击右侧的 **应用模板**，然后点击 **下一步**。
3. 按照提示设置告警规则组。

> **说明**
>
> - 在 **告警资源** > **工作区** 下，应选择与 [方舟在线推理接入点](https://ark.volcengine.com/region:cn-beijing/endpoint?config=%7B%7D) 相同的工作区。
>
>   ![告警资源工作区示意图](https://arkdocs.tos-cn-beijing.volces.com/images/video-generation/screenshot-20260713-195828.png)
>
> - 告警规则阈值为百分比。例如，当 **`CreateAsset` QPM 接近或达到账号限制** 设置为 0.95 时，表示 `CreateAsset` 接口的 QPM 达到上限值的 95%。请按实际业务需求设置。

4. 配置完成后，点击 **确定**。

有关告警规则的详细设置方式，请参考 [托管 Prometheus 产品文档](https://docs.volcengine.com/docs/6731/106503?lang=zh)。
