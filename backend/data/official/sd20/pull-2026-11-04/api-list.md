# 查询视频生成任务列表

> 全部文档的索引见 [llms.txt](https://ark.volcengine.com/llms.txt)；在任一文档页面地址后追加 `.md` 可获取该页的 Markdown 版本。

`GET https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks`

通过传入筛选参数，查询符合条件的视频生成任务。

> **说明**
>
> * 视频任务 ID 存在有效期（从 `created_at` 时间戳开始计算），超时后将自动失效。
>     * **Draft 视频任务 ID**：2026 年 10 月 28 日 10:00（UTC+8）及之后创建的 Draft 视频任务 ID 有效期为 14 天，此前创建的 Draft 视频任务 ID 有效期仍为 7 天。超出有效期后，无法使用该 Draft 视频生成正式视频。
>     * **其他视频任务 ID**：有效期均为 7 天。
> * 视频 URL 有效期为 24 小时，请及时下载或转存。
> * Seedance 2.5 模型生成的产物 URL 下载次数上限为 100 次。

## 鉴权

本接口支持鉴权方式如下，详情请参见 [Base URL 及鉴权](/docs/base-url-and-authentication)。

* API Key 鉴权，请在 [API Key 管理](https://ark.volcengine.com/region:cn-beijing/apiKey) 页面，获取长效 API Key。

---

<span id="request-parameters"></span>
## 请求参数

### Query 参数

> 在 URL Query String 中传入。

**filter** `object` | 筛选条件

用于筛选任务的参数。

**model** `string` | 推理接入点 ID 筛选

`filter.model`

任务使用的推理接入点（Endpoint）ID，精确搜索。可在控制台 [在线推理] → [自定义推理接入点] 页面复制推理接入点 ID (格式为 `ep-` 开头的字符串), 或通过创建推理接入点接口获取。

**service_tier** `string` `默认值 default` | 服务等级筛选

`filter.service_tier`

处理任务使用的服务等级。

* `default`：在线推理模式。
* `flex`：离线推理模式。

**status** `string` | 任务状态筛选

`filter.status`

过滤参数，查询某个任务状态。任务状态，以及相关的信息：

* `queued`：任务排队中。
* `running`：任务运行中。
* `cancelled`：任务已取消。取消状态 24h 自动删除（只支持 `queued` 状态的任务被取消）。
* `succeeded`：任务成功。
* `failed`：任务失败。
* `expired`：任务超时。

**task_ids** `string[]` | 任务 ID 筛选

`filter.task_ids`

视频生成任务 ID，精确搜索，支持同时搜索多个任务 ID。需通过重复参数名的方式传递，示例：`filter.task_ids=id1&filter.task_ids=id2`

**page_num** `integer` `默认值 1` | 页码

返回结果的页码。

**取值范围**：`[1, 500]`

**page_size** `integer` `默认值 20` | 每页数量

每页显示的结果数量。

**取值范围**：`[1, 500]`

## 响应参数

**items** `object[]` | 任务列表

查询到的视频生成任务列表

**id** `string` | 任务 ID

`items.id`

视频生成任务 ID

**model** `string` | 模型名称与版本

`items.model`

任务使用的模型名称和版本，格式为 `模型名称-版本`

**status** `string` | 任务状态

`items.status`

任务状态，以及相关的信息：

* `queued`：任务排队中。
* `running`：任务运行中。
* `cancelled`：任务已取消。取消状态 24h 自动删除（只支持 `queued` 状态的任务被取消）。
* `succeeded`：任务成功。
* `failed`：任务失败。
* `expired`：任务超时。

**content** `object` | 输出内容

`items.content`

视频生成任务完成时返回的输出内容，包含生成视频下载的 URL

**last_frame_url** `string` | 尾帧图像 URL

`items.content.last_frame_url`

视频的尾帧图像 URL。有效期为 24 小时，请及时下载或转存。 Seedance 2.5 模型生成的视频 URL 下载次数上限为 100 次。

说明：[创建视频生成任务](/docs/create-video-generation-task-api) 时设置 `"return_last_frame": true` 时，会返回该参数。

**video_url** `string` | 视频 URL

`items.content.video_url`

生成视频的 URL。有效期为 24 小时，请及时下载或转存。 Seedance 2.5 模型生成的视频 URL 下载次数上限为 100 次。

推荐配置火山引擎 TOS 提供的数据订阅功能，将您的模型推理产物自动转存到自己的 TOS 桶中，便于长期备份或二次加工。详细介绍请参见 [TOS 数据订阅](https://docs.volcengine.com/docs/torch-object-storage/data-subscription?lang=zh)。

**created_at** `integer` | 创建时间

`items.created_at`

任务创建时间的 Unix 时间戳（秒）

**draft** `boolean` | 是否为 Draft 视频

`items.draft`

生成的视频是否为 Draft 视频。`true` 表示 Draft 视频，`false` 表示正式视频。

**模型支持**：

* `Seedance 2.5`

**duration** `integer` | 视频时长（秒）

`items.duration`

生成视频的时长，单位：秒。

说明：**`duration` 和 `frames` 参数只会返回一个**。创建视频生成任务时未指定 `frames`，会返回 `duration`。

**error** `object` | 错误信息

`items.error`

错误提示信息。任务成功时返回 `null`，任务失败时返回错误数据，错误信息具体参见 [错误处理](/docs/error-codes#common-error-codes-agent)。

> **注意**
>
> Seedance 2.5 模型在特定的任务类型中，需排队等待到任务被消费时，才会返回报错信息。详情参考 [报错机制](/docs/seedance-2-5#2.5_error_handling)。

**code** `string` | 错误码

`items.error.code`

**message** `string` | 错误提示信息

`items.error.message`

**execution_expires_after** `integer` | 任务超时阈值（秒）

`items.execution_expires_after`

任务提交后的过期时间。任务超过该时间未完成会被自动终止，并标记为 `expired` 状态。

**frames** `integer` | 视频帧数

`items.frames`

生成视频的帧数。

说明：**`duration` 和 `frames` 参数只会返回一个**。创建视频生成任务时指定了 `frames`，会返回 `frames`。

**framespersecond** `integer` | 视频帧率

`items.framespersecond`

生成视频的帧率

**generate_audio** `boolean` | 是否生成同步音频

`items.generate_audio`

生成的视频是否包含与画面同步的声音。

* `true`：模型输出的视频包含同步音频。
* `false`：模型输出的视频为无声视频。

**模型支持**：

* `Seedance 2.5`
* `Seedance 2.0 系列`

**output_format** `string` | 输出格式

`items.output_format`

实际生成视频的封装容器格式（`mp4`或`mov`）。

**模型支持**：

* `Seedance 2.5`

**priority** `integer` | 执行优先级

`items.priority`

当前任务的执行优先级，与创建任务时设置的 `priority` 一致。取值范围为 0～9，数值越大，优先级越高。

**模型支持**：

* `Seedance 2.5`
* `Seedance 2.0 系列`

**ratio** `string` | 宽高比

`items.ratio`

生成视频的宽高比

**resolution** `string` | 分辨率

`items.resolution`

生成视频的分辨率

**safety_identifier** `string` | 终端用户标识

`items.safety_identifier`

终端用户的唯一标识符。若创建视频生成任务时设置了该参数，接口会原样返回此信息

**seed** `integer` | 随机种子

`items.seed`

本次请求使用的种子整数值

**service_tier** `string` | 服务等级

`items.service_tier`

实际处理任务使用的服务等级

**tools** `object[]` | 实际使用的工具

`items.tools`

本次请求模型实际使用的工具。未使用工具时不返回

**模型支持**：

* `Seedance 2.5`
* `Seedance 2.0 系列`

**type** `string` | 工具类型

`items.tools.type`

实际使用的工具类型。

* `web_search`：联网搜索工具

**updated_at** `integer` | 更新时间

`items.updated_at`

任务当前状态更新时间的 Unix 时间戳（秒）

**usage** `object` | token 用量

`items.usage`

本次请求的 token 用量

**completion_tokens** `integer` | 生成视频消耗的 token 数

`items.usage.completion_tokens`

模型生成视频消耗的 token 数量，可作为计费对账依据。

> **注意**
>
> `Seedance 2.0 系列`模型存在最低 token 用量限制，如果实际 token 用量 ＜ 最低 token 用量，本字段会返回最低 token 用量，平台按最低 token 用量计费。

**total_tokens** `integer` | 总 token 数

`items.usage.total_tokens`

本次请求消耗的总 token 数量。视频生成模型不统计输入 token，输入 token 为 0，故 `total_tokens` = `completion_tokens`

**tool_usage** `object` | 工具用量

`items.usage.tool_usage`

使用工具的用量信息

**web_search** `integer` | 联网搜索调用次数

`items.usage.tool_usage.web_search`

实际调用联网搜索工具的次数，仅开启联网搜索时返回

**total** `integer` | 任务总数

符合筛选条件的任务数量


## 代码示例

## 默认

### cURL


#### Request

```bash
curl https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks?page_size=2&filter.status=succeeded& \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_API_KEY"
```
#### Response

```
{
    "total": 30,
    "items": [
        {
            "id": "cgt-2026****-****",
            "model": "doubao-seedance-2-0-260128",
            "status": "succeeded",
            "content": {
                "video_url": "https://ark-acg-cn-beijing.tos-cn-beijing.volces.com/xxx"
            },
            "usage": {
                "completion_tokens": 109586,
                "total_tokens": 109586
            },
            "created_at": 1779354227,
            "updated_at": 1779354426,
            "seed": 70172,
            "resolution": "720p",
            "ratio": "4:3",
            "duration": 5,
            "framespersecond": 24,
            "service_tier": "default",
            "execution_expires_after": 172800,
            "generate_audio": true,
            "draft": false,
            "priority": 0
        },
        {
            "id": "cgt-2026****-****",
            "model": "doubao-seedance-2-0-260128",
            "status": "succeeded",
            "content": {
                "video_url": "https://ark-acg-cn-beijing.tos-cn-beijing.volces.com/xxx"
            },
            "usage": {
                "completion_tokens": 49761,
                "total_tokens": 49761
            },
            "created_at": 1779353985,
            "updated_at": 1779354268,
            "seed": 68292,
            "resolution": "480p",
            "ratio": "3:4",
            "duration": 5,
            "framespersecond": 24,
            "service_tier": "default",
            "execution_expires_after": 172800,
            "generate_audio": true,
            "draft": false,
            "priority": 0
        },
        {
            "id": "cgt-2026****-****",
            "model": "doubao-seedance-2-0-260128",
            "status": "succeeded",
            "content": {
                "video_url": "https://ark-acg-cn-beijing.tos-cn-beijing.volces.com/doubao-seedance-2-0/xxx"
            },
            "usage": {
                "completion_tokens": 109586,
                "total_tokens": 109586
            },
            "created_at": 1779353885,
            "updated_at": 1779354215,
            "seed": 39832,
            "resolution": "720p",
            "ratio": "3:4",
            "duration": 5,
            "framespersecond": 24,
            "service_tier": "default",
            "execution_expires_after": 172800,
            "generate_audio": true,
            "draft": false,
            "priority": 0
        }
    ]
}
```

### Python


#### Request

```python
import os
from arkruntime import Ark

client = Ark(
    api_key=os.environ.get("ARK_API_KEY"),
    base_url="https://ark.cn-beijing.volces.com/api/v3",
)

if __name__ == "__main__":
    resp = client.content_generation.tasks.list(
        page_size=3,
        status="succeeded",
    )
    print(resp)
```
#### Response

```
{
    "total": 30,
    "items": [
        {
            "id": "cgt-2026****-****",
            "model": "doubao-seedance-2-0-260128",
            "status": "succeeded",
            "content": {
                "video_url": "https://ark-acg-cn-beijing.tos-cn-beijing.volces.com/xxx"
            },
            "usage": {
                "completion_tokens": 109586,
                "total_tokens": 109586
            },
            "created_at": 1779354227,
            "updated_at": 1779354426,
            "seed": 70172,
            "resolution": "720p",
            "ratio": "4:3",
            "duration": 5,
            "framespersecond": 24,
            "service_tier": "default",
            "execution_expires_after": 172800,
            "generate_audio": true,
            "draft": false,
            "priority": 0
        },
        {
            "id": "cgt-2026****-****",
            "model": "doubao-seedance-2-0-260128",
            "status": "succeeded",
            "content": {
                "video_url": "https://ark-acg-cn-beijing.tos-cn-beijing.volces.com/xxx"
            },
            "usage": {
                "completion_tokens": 49761,
                "total_tokens": 49761
            },
            "created_at": 1779353985,
            "updated_at": 1779354268,
            "seed": 68292,
            "resolution": "480p",
            "ratio": "3:4",
            "duration": 5,
            "framespersecond": 24,
            "service_tier": "default",
            "execution_expires_after": 172800,
            "generate_audio": true,
            "draft": false,
            "priority": 0
        },
        {
            "id": "cgt-2026****-****",
            "model": "doubao-seedance-2-0-260128",
            "status": "succeeded",
            "content": {
                "video_url": "https://ark-acg-cn-beijing.tos-cn-beijing.volces.com/doubao-seedance-2-0/xxx"
            },
            "usage": {
                "completion_tokens": 109586,
                "total_tokens": 109586
            },
            "created_at": 1779353885,
            "updated_at": 1779354215,
            "seed": 39832,
            "resolution": "720p",
            "ratio": "3:4",
            "duration": 5,
            "framespersecond": 24,
            "service_tier": "default",
            "execution_expires_after": 172800,
            "generate_audio": true,
            "draft": false,
            "priority": 0
        }
    ]
}
```

### Go


#### Request

```go
package main

import (
    "context"
    "fmt"
    "os"

    "github.com/volcengine/ark-runtime-go/arkruntime"
    model "github.com/volcengine/ark-runtime-go/arkruntime/model/contentgeneration"
)

func main() {
        client := arkruntime.NewClientWithApiKey(
        os.Getenv("ARK_API_KEY"),
        arkruntime.WithBaseUrl("https://ark.cn-beijing.volces.com/api/v3"),
    )
        ctx := context.Background()

        req := &arkruntime.ListContentGenerationTasksRequest{
                PageSize: int32Pointer(3),
                Status: taskStatusPointer(model.TaskStatus("succeeded")),
        }

        resp, err := client.ListContentGenerationTasks(ctx, req)
        if err != nil {
                fmt.Printf("failed to list content generation tasks: %v\n", err)
                return
        }
        fmt.Printf("%+v\n", resp)
}

func int32Pointer(value int32) *int32 { return &value }
func taskStatusPointer(value model.TaskStatus) *model.TaskStatus { return &value }
```

#### Response

```
{
    "total": 30,
    "items": [
        {
            "id": "cgt-2026****-****",
            "model": "doubao-seedance-2-0-260128",
            "status": "succeeded",
            "content": {
                "video_url": "https://ark-acg-cn-beijing.tos-cn-beijing.volces.com/xxx"
            },
            "usage": {
                "completion_tokens": 109586,
                "total_tokens": 109586
            },
            "created_at": 1779354227,
            "updated_at": 1779354426,
            "seed": 70172,
            "resolution": "720p",
            "ratio": "4:3",
            "duration": 5,
            "framespersecond": 24,
            "service_tier": "default",
            "execution_expires_after": 172800,
            "generate_audio": true,
            "draft": false,
            "priority": 0
        },
        {
            "id": "cgt-2026****-****",
            "model": "doubao-seedance-2-0-260128",
            "status": "succeeded",
            "content": {
                "video_url": "https://ark-acg-cn-beijing.tos-cn-beijing.volces.com/xxx"
            },
            "usage": {
                "completion_tokens": 49761,
                "total_tokens": 49761
            },
            "created_at": 1779353985,
            "updated_at": 1779354268,
            "seed": 68292,
            "resolution": "480p",
            "ratio": "3:4",
            "duration": 5,
            "framespersecond": 24,
            "service_tier": "default",
            "execution_expires_after": 172800,
            "generate_audio": true,
            "draft": false,
            "priority": 0
        },
        {
            "id": "cgt-2026****-****",
            "model": "doubao-seedance-2-0-260128",
            "status": "succeeded",
            "content": {
                "video_url": "https://ark-acg-cn-beijing.tos-cn-beijing.volces.com/doubao-seedance-2-0/xxx"
            },
            "usage": {
                "completion_tokens": 109586,
                "total_tokens": 109586
            },
            "created_at": 1779353885,
            "updated_at": 1779354215,
            "seed": 39832,
            "resolution": "720p",
            "ratio": "3:4",
            "duration": 5,
            "framespersecond": 24,
            "service_tier": "default",
            "execution_expires_after": 172800,
            "generate_audio": true,
            "draft": false,
            "priority": 0
        }
    ]
}
```

### Java


#### Request

```java
package com.ark.sample;

import com.volcengine.ark.runtime.models.content_generation.*;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.volcengine.ark.runtime.service.ArkService;
import java.util.concurrent.TimeUnit;
import okhttp3.ConnectionPool;
import okhttp3.Dispatcher;

public class Sample {

    static String apiKey = System.getenv("ARK_API_KEY");

    static ConnectionPool connectionPool = new ConnectionPool(5, 1, TimeUnit.SECONDS);
    static Dispatcher dispatcher = new Dispatcher();
    static ArkService service =
            ArkService.builder()
                    .dispatcher(dispatcher)
                    .connectionPool(connectionPool)
                    .apiKey(apiKey)
                    .baseUrl("https://ark.cn-beijing.volces.com/api/v3")
                    .build();

    public static void main(String[] args) throws JsonProcessingException {

        ListContentGenerationTasksRequest req =
                ListContentGenerationTasksRequest.builder().pageNum(1).pageSize(3).filterStatus(TaskStatus.SUCCEEDED).build();

        System.out.println(service.listContentGenerationTasks(req));

        // shutdown service after all requests is finished
        service.shutdownExecutor();
    }
}
```

#### Response

```
{
    "total": 30,
    "items": [
        {
            "id": "cgt-2026****-****",
            "model": "doubao-seedance-2-0-260128",
            "status": "succeeded",
            "content": {
                "video_url": "https://ark-acg-cn-beijing.tos-cn-beijing.volces.com/xxx"
            },
            "usage": {
                "completion_tokens": 109586,
                "total_tokens": 109586
            },
            "created_at": 1779354227,
            "updated_at": 1779354426,
            "seed": 70172,
            "resolution": "720p",
            "ratio": "4:3",
            "duration": 5,
            "framespersecond": 24,
            "service_tier": "default",
            "execution_expires_after": 172800,
            "generate_audio": true,
            "draft": false,
            "priority": 0
        },
        {
            "id": "cgt-2026****-****",
            "model": "doubao-seedance-2-0-260128",
            "status": "succeeded",
            "content": {
                "video_url": "https://ark-acg-cn-beijing.tos-cn-beijing.volces.com/xxx"
            },
            "usage": {
                "completion_tokens": 49761,
                "total_tokens": 49761
            },
            "created_at": 1779353985,
            "updated_at": 1779354268,
            "seed": 68292,
            "resolution": "480p",
            "ratio": "3:4",
            "duration": 5,
            "framespersecond": 24,
            "service_tier": "default",
            "execution_expires_after": 172800,
            "generate_audio": true,
            "draft": false,
            "priority": 0
        },
        {
            "id": "cgt-2026****-****",
            "model": "doubao-seedance-2-0-260128",
            "status": "succeeded",
            "content": {
                "video_url": "https://ark-acg-cn-beijing.tos-cn-beijing.volces.com/doubao-seedance-2-0/xxx"
            },
            "usage": {
                "completion_tokens": 109586,
                "total_tokens": 109586
            },
            "created_at": 1779353885,
            "updated_at": 1779354215,
            "seed": 39832,
            "resolution": "720p",
            "ratio": "3:4",
            "duration": 5,
            "framespersecond": 24,
            "service_tier": "default",
            "execution_expires_after": 172800,
            "generate_audio": true,
            "draft": false,
            "priority": 0
        }
    ]
}
```

## 搜索多个任务 ID


#### Request

```bash
curl -X GET "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks?filter.task_ids=cgt-20250730114109-xtv7k&filter.task_ids=cgt-20250730114109-jfd6d" \
--header "Content-Type: application/json" \
--header "Authorization: Bearer $ARK_API_KEY"
```
#### Response

```
// 假设所查询的任务 ID 仍在对应有效期内
{
    "total": 2,
    "items": [
        {
            "id": "cgt-20260521165358-c9fpl",
            "model": "doubao-seedance-2-0-260128",
            "status": "succeeded",
            "content": {
                "video_url": "https://ark-acg-cn-beijing.tos-cn-beijing.volces.com/xxx"
            },
            "usage": {
                "completion_tokens": 173700,
                "total_tokens": 173700
            },
            "created_at": 1779353641,
            "updated_at": 1779353917,
            "seed": 83959,
            "resolution": "720p",
            "ratio": "16:9",
            "duration": 8,
            "framespersecond": 24,
            "service_tier": "default",
            "execution_expires_after": 172800,
            "generate_audio": true,
            "draft": false,
            "priority": 0
        },
        {
            "id": "cgt-20260521165055-pxg74",
            "model": "doubao-seedance-2-0-260128",
            "status": "succeeded",
            "content": {
                "video_url": "https://ark-acg-cn-beijing.tos-cn-beijing.volces.com/xxx"
            },
            "usage": {
                "completion_tokens": 108900,
                "total_tokens": 108900
            },
            "created_at": 1779353462,
            "updated_at": 1779353752,
            "seed": 14512,
            "resolution": "720p",
            "ratio": "16:9",
            "duration": 5,
            "framespersecond": 24,
            "service_tier": "default",
            "execution_expires_after": 172800,
            "generate_audio": true,
            "draft": false,
            "priority": 0
        }
    ]
}
```
