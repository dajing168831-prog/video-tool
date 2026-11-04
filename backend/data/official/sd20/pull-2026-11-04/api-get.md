# 查询视频生成任务

> 全部文档的索引见 [llms.txt](https://ark.volcengine.com/llms.txt)；在任一文档页面地址后追加 `.md` 可获取该页的 Markdown 版本。

`GET https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks/{id}`

查询视频生成任务的状态。

> **说明**
>
> * 视频任务 ID 存在有效期（从 `created_at` 时间戳开始计算），超时后将自动失效。
>     * **Draft 视频任务 ID**：2026 年 10 月 28 日 10:00（UTC+8）及之后创建的 Draft 视频任务 ID 有效期为 14 天，此前创建的 Draft 视频任务 ID 有效期仍为 7 天。超出有效期后，无法使用该 Draft 视频生成正式视频。
>     * **其他视频任务 ID**：有效期均为 7 天。
> * 视频 URL 有效期为 24 小时，请及时下载或转存。
> * Seedance 2.5 模型生成的视频 URL 下载次数上限为 100 次。

## 鉴权

本接口支持鉴权方式如下，详情请参见 [Base URL 及鉴权](/docs/base-url-and-authentication)。

* API Key 鉴权，请在 [API Key 管理](https://ark.volcengine.com/region:cn-beijing/apiKey) 页面，获取长效 API Key。

---

<span id="request-parameters"></span>
## 请求参数

### Path 参数

**id** `string` `必选` | 任务 ID

您需要查询的视频生成任务的 ID

## 响应参数

**id** `string` | 任务 ID

视频生成任务 ID

**model** `string` | 模型名称与版本

任务使用的模型名称和版本，格式为 `模型名称-版本`

**status** `string` | 任务状态

任务状态，以及相关的信息：

* `queued`：任务排队中。
* `running`：任务运行中。
* `cancelled`：任务已取消。取消状态 24h 自动删除（只支持 `queued` 状态的任务被取消）。
* `succeeded`：任务成功。
* `failed`：任务失败。
* `expired`：任务超时。

**content** `object` | 输出内容

视频生成任务的输出内容

**last_frame_url** `string` | 尾帧图像 URL

`content.last_frame_url`

视频的尾帧图像 URL。有效期为 24 小时，请及时下载或转存。 Seedance 2.5 模型生成的视频 URL 下载次数上限为 100 次。

说明：[创建视频生成任务](/docs/create-video-generation-task-api) 时设置 `"return_last_frame": true` 时，会返回该参数。

**video_url** `string` | 视频 URL

`content.video_url`

生成视频的 URL。有效期为 24 小时，请及时下载或转存。 Seedance 2.5 模型生成的视频 URL 下载次数上限为 100 次。

推荐配置火山引擎 TOS 提供的数据订阅功能，将您的模型推理产物自动转存到自己的 TOS 桶中，便于长期备份或二次加工。详细介绍请参见 [TOS 数据订阅](https://docs.volcengine.com/docs/torch-object-storage/data-subscription?lang=zh)。

**created_at** `integer` | 创建时间

任务创建时间的 Unix 时间戳（秒）

**draft** `boolean` | 是否为 Draft 视频

生成的视频是否为 Draft 视频。`true` 表示 Draft 视频，`false` 表示正式视频。

**模型支持**：

* `Seedance 2.5`

**duration** `integer` | 视频时长（秒）

生成视频的时长，单位：秒。

说明：**`duration` 和 `frames` 参数只会返回一个**。创建视频生成任务时未指定 `frames`，会返回 `duration`。

**error** `object` | 错误信息

错误提示信息。任务成功时返回 `null`，任务失败时返回错误数据，错误信息具体参见 [错误处理](/docs/error-codes#common-error-codes-agent)。

> **注意**
>
> Seedance 2.5 模型在特定的任务类型中，需排队等待到任务被消费时，才会返回报错信息。详情参考 [报错机制](/docs/seedance-2-5#2.5_error_handling)。

**code** `string` | 错误码

`error.code`

**message** `string` | 错误提示信息

`error.message`

**execution_expires_after** `integer` | 任务超时阈值（秒）

任务提交后的过期时间。任务超过该时间未完成会被自动终止，并标记为 `expired` 状态。

**frames** `integer` | 视频帧数

生成视频的帧数。

说明：**`duration` 和 `frames` 参数只会返回一个**。创建视频生成任务时指定了 `frames`，会返回 `frames`。

**framespersecond** `integer` | 视频帧率

生成视频的帧率

**generate_audio** `boolean` | 是否生成同步音频

生成的视频是否包含与画面同步的声音。

* `true`：模型输出的视频包含同步音频。
* `false`：模型输出的视频为无声视频。

**模型支持**：

* `Seedance 2.5`
* `Seedance 2.0 系列`

**output_format** `string` | 输出格式

实际生成视频的格式（`mp4`或`mov`）。

**模型支持**：

* `Seedance 2.5`

**priority** `integer` | 执行优先级

当前任务的执行优先级，与创建任务时设置的 `priority` 一致。取值范围为 0～9，数值越大，优先级越高。

**模型支持**：

* `Seedance 2.5`
* `Seedance 2.0 系列`

**ratio** `string` | 宽高比

生成视频的宽高比

**resolution** `string` | 分辨率

生成视频的分辨率

**safety_identifier** `string` | 终端用户标识

终端用户的唯一标识符。若创建任务时设置了该参数，接口会原样返回此信息

**seed** `integer` | 随机种子

本次请求使用的种子整数值

**service_tier** `string` | 服务等级

实际处理任务使用的服务等级

**tools** `object[]` | 实际使用的工具

本次请求模型实际使用的工具。未使用工具时不返回

**模型支持**：

* `Seedance 2.5`
* `Seedance 2.0 系列`

**type** `string` | 工具类型

`tools.type`

实际使用的工具类型。

* `web_search`：联网搜索工具

**updated_at** `integer` | 更新时间

任务当前状态更新时间的 Unix 时间戳（秒）

**usage** `object` | token 用量

本次请求的 token 用量

**completion_tokens** `integer` | 生成视频消耗的 token 数

`usage.completion_tokens`

模型生成视频消耗的 token 数量，可作为计费对账依据。

> **注意**
>
> `Seedance 2.0 系列`模型存在最低 token 用量限制，如果实际 token 用量 ＜ 最低 token 用量，本字段会返回最低 token 用量，平台按最低 token 用量计费。

**total_tokens** `integer` | 总 token 数

`usage.total_tokens`

本次请求消耗的总 token 数量。视频生成模型不统计输入 token，输入 token 为 0，故 `total_tokens` = `completion_tokens`

**tool_usage** `object` | 工具用量

`usage.tool_usage`

使用工具的用量信息

**web_search** `integer` | 联网搜索调用次数

`usage.tool_usage.web_search`

实际调用联网搜索工具的次数，仅开启联网搜索时返回


## 代码示例

## 默认

### cURL


#### Request

```bash
TASK_ID="your_task_id"
curl -X GET "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks/$TASK_ID" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_API_KEY"
```
#### Response

```
{
    "id": "cgt-2026****-****",
    "model": "doubao-seedance-2-0-260128",
    "status": "succeeded",
    "content": {
        "video_url": "https://ark-content-generation-cn-beijing.tos-cn-beijing.volces.com/xxx"
    },
    "usage": {
        "completion_tokens": 108900,
        "total_tokens": 108900
    },
    "created_at": 1779348818,
    "updated_at": 1779348874,
    "seed": 78674,
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
    resp = client.content_generation.tasks.get(
        task_id="cgt-2025****",
    )
    print(resp)
```
#### Response

```
{
    "id": "cgt-2026****-****",
    "model": "doubao-seedance-2-0-260128",
    "status": "succeeded",
    "content": {
        "video_url": "https://ark-content-generation-cn-beijing.tos-cn-beijing.volces.com/xxx"
    },
    "usage": {
        "completion_tokens": 108900,
        "total_tokens": 108900
    },
    "created_at": 1779348818,
    "updated_at": 1779348874,
    "seed": 78674,
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
)


func main() {
        client := arkruntime.NewClientWithApiKey(
        os.Getenv("ARK_API_KEY"),
        arkruntime.WithBaseUrl("https://ark.cn-beijing.volces.com/api/v3"),
    )
        ctx := context.Background()

        req := "<TASK_ID>"
        resp, err := client.GetContentGenerationTask(ctx, req)
        if err != nil {
                fmt.Printf("get content generation task error: %v\n", err)
                return
        }
        fmt.Printf("%+v\n", resp)
}
```

#### Response

```
{
    "id": "cgt-2026****-****",
    "model": "doubao-seedance-2-0-260128",
    "status": "succeeded",
    "content": {
        "video_url": "https://ark-content-generation-cn-beijing.tos-cn-beijing.volces.com/xxx"
    },
    "usage": {
        "completion_tokens": 108900,
        "total_tokens": 108900
    },
    "created_at": 1779348818,
    "updated_at": 1779348874,
    "seed": 78674,
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
        String taskId = "<TASK_ID>";

        String req = taskId;


        service.getContentGenerationTask(req).toString();
        System.out.println(service.getContentGenerationTask(req));

        service.shutdownExecutor();
    }
}
```

#### Response

```
{
    "id": "cgt-2026****-****",
    "model": "doubao-seedance-2-0-260128",
    "status": "succeeded",
    "content": {
        "video_url": "https://ark-content-generation-cn-beijing.tos-cn-beijing.volces.com/xxx"
    },
    "usage": {
        "completion_tokens": 108900,
        "total_tokens": 108900
    },
    "created_at": 1779348818,
    "updated_at": 1779348874,
    "seed": 78674,
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
```
