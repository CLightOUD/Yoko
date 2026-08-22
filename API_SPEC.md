# Yoko API 接口规范

- 版本：`0.1.0`
- 状态：MVP 开发合同
适用范围：适老陪伴、提醒、反馈记忆与效果评估

## 快速导航

- 全员先读：第 3 节通用约定、第 4 节接口总览、第 5 节公共对象。
- 队长（Agent/API）：重点阅读第 6 至 8 节、第 12 节和第 13.1 至 13.2 节。
- 队员 A（数据/记忆/提醒）：重点阅读第 8 至 11 节和第 13.3 节。
- 队员 B（前端）：重点阅读第 3.4、3.6、4 至 11 节和第 13.4 节。
- 联调与测试：使用第 14 节逐项验收，不接受只验证正常路径。

接口示例用于说明序列化格式，字段表和枚举约束具有最终解释权。

## 1. 设计目标

本规范覆盖以下核心闭环：

```text
用户输入 -> 检索记忆 -> Agent 处理 -> 调用提醒工具 -> 返回结果
   -> 用户反馈 -> 写入或更新记忆 -> 后续相似任务自动使用
```

MVP 需要同时满足：

- 支持新会话和连续会话。
- 支持无记忆、命中记忆和过滤无关记忆。
- 支持用户反馈创建、覆盖或跳过记忆。
- 支持一次性提醒和每日提醒。
- 支持前端轮询、确认提醒和防止重复确认。
- 支持用户查看、修改、停用和删除记忆。
- 返回记忆使用情况、Token 数和各阶段耗时。

## 2. MVP 边界

本阶段不实现：

- 登录、注册和多角色权限系统。
- WebSocket、SSE 流式输出。
- 向量数据库和相似度搜索。
- 通用 Cron 表达式。
- 网页关闭后的可靠系统通知。
- 文件上传、语音识别和多模态输入。
- 历史会话列表、跨设备会话恢复。

MVP 使用前端每 20 至 30 秒轮询到期提醒。网页关闭后不能保证提醒触发，演示时必须明确说明。

## 3. 通用约定

### 3.1 基础信息

```text
Base URL: http://127.0.0.1:8000
Content-Type: application/json
API prefix: /api
```

### 3.2 命名和类型

- JSON 字段统一使用 `snake_case`。
- 所有资源 ID 使用 UUID 字符串。
- 时间使用 ISO 8601，并包含时区偏移，例如 `2026-08-22T19:00:00+08:00`。
- 时区使用 IANA 名称，例如 `Asia/Shanghai`。
- 耗时统一使用整数毫秒，字段后缀为 `_ms`。
- Token 数使用非负整数；模型供应商未返回统计时允许为 `null`。
- 列表接口统一返回 `items` 和 `total`。
- 当前没有认证系统，`user_id` 由前端传入；所有读写仍必须按 `user_id` 隔离。
- 响应模型中的字段固定返回，不允许后端因值为空而临时省略字段。
- 列表没有数据时返回 `[]`，可空单值返回 `null`，不能用空字符串代替。
- 成功响应直接返回对应模型，不额外包裹 `data`；错误响应统一使用 `ErrorResponse`。

#### 3.2.1 “模型”术语说明

本文中的“模型”可能有两种含义，必须根据上下文区分：

- **LLM 大模型**：实际生成回复和选择工具的 AI，例如通过 `ChatOpenAI` 接入的一个聊天模型。MVP 只需接入一个支持工具调用的 LLM。
- **Pydantic 数据模型**：普通 Python 类，用于规定接口字段、类型、默认值和校验规则，不会生成文本，也不会产生模型调用费用。

接口章节中的 `ChatRequest`、`ReminderCreateRequest`、`MemoryView` 等全部是 Pydantic 数据模型。名称约定：

```text
*Request   JSON 请求体的数据结构
*Query     URL 查询参数的数据结构
*Response  JSON 响应体的数据结构
*View      某个资源在响应中的完整结构
```

### 3.3 HTTP 状态码

| 状态码 | 使用场景 |
| --- | --- |
| `200` | 查询、修改、删除或 Agent 请求成功 |
| `201` | 手动创建提醒成功 |
| `400` | 已通过字段校验，但仍无法执行业务的参数错误 |
| `404` | 会话、提醒、记忆或请求不存在 |
| `409` | 提醒已被修改、确认时间已失效或资源状态冲突 |
| `422` | Pydantic 字段校验失败 |
| `502` | 模型或工具故障导致无法形成有效业务响应 |
| `500` | 未处理的服务端错误 |

### 3.4 统一错误响应

```json
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "message 不能为空",
    "details": null
  },
  "request_id": "64e7398e-811a-4b2c-b301-e46ad4d180ba"
}
```

建议错误码：

```text
INVALID_REQUEST
RESOURCE_NOT_FOUND
RESOURCE_CONFLICT
MODEL_UNAVAILABLE
TOOL_EXECUTION_FAILED
INTERNAL_ERROR
```

FastAPI 的 `RequestValidationError` 需要通过异常处理器转换为上述格式，避免前端同时处理两套错误结构。

`ErrorResponse` 字段合同：

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | --- | --- |
| `error.code` | 字符串 | 否 | 稳定错误码，前端据此判断类型 |
| `error.message` | 字符串 | 否 | 可直接展示的简短中文说明 |
| `error.details` | JSON 对象、数组、字符串或 `null` | 是 | 字段错误等调试信息 |
| `request_id` | UUID 字符串 | 否 | 由请求中间件生成，用于日志关联 |

### 3.5 MVP 用户约定

- 数据库初始化时必须创建 `demo-user`，默认显示名称和时区分别为“用户”和 `Asia/Shanghai`。
- 前端 MVP 固定使用 `demo-user`；自动化测试可以预置其他用户验证数据隔离。
- 本版本没有创建用户接口。未知 `user_id` 返回 `404 RESOURCE_NOT_FOUND`，不能由查询接口隐式创建用户。
- `ChatRequest.timezone` 只影响本次自然语言时间解析，不自动修改用户资料。

### 3.6 接口错误矩阵

所有表内错误均返回 `ErrorResponse`；未列出的未处理异常统一为 `500 INTERNAL_ERROR`。

| 接口 | 可能的业务错误 |
| --- | --- |
| `GET /api/health` | 通常无业务错误 |
| `POST /api/chat` | `400 INVALID_REQUEST`、`404 RESOURCE_NOT_FOUND`、`422 INVALID_REQUEST`、`502 MODEL_UNAVAILABLE`、`502 TOOL_EXECUTION_FAILED` |
| `POST /api/feedback` | `404 RESOURCE_NOT_FOUND`、`422 INVALID_REQUEST` |
| `POST /api/reminders` | `404 RESOURCE_NOT_FOUND`、`422 INVALID_REQUEST` |
| `GET /api/reminders` | `404 RESOURCE_NOT_FOUND`、`422 INVALID_REQUEST` |
| `GET /api/reminders/due` | `404 RESOURCE_NOT_FOUND`、`422 INVALID_REQUEST` |
| `PATCH /api/reminders/{id}` | `400 INVALID_REQUEST`、`404 RESOURCE_NOT_FOUND`、`409 RESOURCE_CONFLICT`、`422 INVALID_REQUEST` |
| `DELETE /api/reminders/{id}` | `404 RESOURCE_NOT_FOUND`、`422 INVALID_REQUEST` |
| `POST /api/reminders/{id}/ack` | `404 RESOURCE_NOT_FOUND`、`409 RESOURCE_CONFLICT`、`422 INVALID_REQUEST` |
| `GET /api/memories` | `404 RESOURCE_NOT_FOUND`、`422 INVALID_REQUEST` |
| `PATCH /api/memories/{id}` | `404 RESOURCE_NOT_FOUND`、`409 RESOURCE_CONFLICT`、`422 INVALID_REQUEST` |
| `DELETE /api/memories/{id}` | `404 RESOURCE_NOT_FOUND`、`422 INVALID_REQUEST` |
| `GET /api/metrics/summary` | `400 INVALID_REQUEST`、`404 RESOURCE_NOT_FOUND`、`422 INVALID_REQUEST` |

对重复反馈、重复删除和相同 `expected_trigger_at` 的重复确认，服务端返回原成功结果，不返回冲突错误。

## 4. 接口总览

| 方法 | 路径 | 输入 | 成功状态 | 响应数据模型 |
| --- | --- | --- | --- | --- |
| `GET` | `/api/health` | 无 | `200` | `HealthResponse` |
| `POST` | `/api/chat` | Body: `ChatRequest` | `200` | `ChatResponse` |
| `POST` | `/api/feedback` | Body: `FeedbackRequest` | `200` | `FeedbackResponse` |
| `POST` | `/api/reminders` | Body: `ReminderCreateRequest` | `201` | `ReminderView` |
| `GET` | `/api/reminders` | Query: `ReminderListQuery` | `200` | `ReminderListResponse` |
| `GET` | `/api/reminders/due` | Query: `DueReminderQuery` | `200` | `ReminderListResponse` |
| `PATCH` | `/api/reminders/{id}` | Path: `id`; Body: `ReminderUpdateRequest` | `200` | `ReminderView` |
| `DELETE` | `/api/reminders/{id}` | Path: `id`; Query: `user_id` | `200` | `DeleteResponse` |
| `POST` | `/api/reminders/{id}/ack` | Path: `id`; Body: `ReminderAckRequest` | `200` | `ReminderAckResponse` |
| `GET` | `/api/memories` | Query: `MemoryListQuery` | `200` | `MemoryListResponse` |
| `PATCH` | `/api/memories/{id}` | Path: `id`; Body: `MemoryUpdateRequest` | `200` | `MemoryView` |
| `DELETE` | `/api/memories/{id}` | Path: `id`; Query: `user_id` | `200` | `DeleteResponse` |
| `GET` | `/api/metrics/summary` | Query: `MetricsSummaryQuery` | `200` | `MetricsSummaryResponse` |

表中的数据模型名称是前后端共同合同。字段调整必须先修改本文件，再同步 Pydantic 模型、前端类型和测试。

## 5. 公共对象

### 5.1 MemoryView

```json
{
  "id": "baf29d40-5e01-4be0-b7a1-553a871e5c21",
  "scope": "task",
  "task_type": "medication",
  "memory_key": "preferred_time",
  "memory_value": "19:00",
  "display_text": "服药提醒时间为晚上7点",
  "active": true,
  "source_message_id": "90264fac-c73f-45e8-8bd2-a5a5a8c66a4b",
  "created_at": "2026-08-21T15:00:00+08:00",
  "updated_at": "2026-08-21T15:00:00+08:00",
  "last_used_at": null
}
```

枚举约束：

```text
scope: global | task
task_type: global | medication | walking | appointment | other
```

同一用户的 `task_type + memory_key` 只允许存在一个有效值。新反馈覆盖旧偏好时更新原记录，并写入 `memory_events`。

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID 字符串 | 否 | 记忆 ID |
| `scope` | 枚举字符串 | 否 | `global` 或 `task` |
| `task_type` | 枚举字符串 | 否 | 任务分类 |
| `memory_key` | 字符串 | 否 | 稳定键名，长度 1 至 64 |
| `memory_value` | 字符串 | 否 | 结构化值，长度 1 至 500 |
| `display_text` | 字符串 | 否 | 面向用户的说明，长度 1 至 200 |
| `active` | 布尔值 | 否 | 是否参与检索 |
| `source_message_id` | UUID 字符串 | 是 | 来源消息；预置数据可为 `null` |
| `created_at` | ISO 8601 字符串 | 否 | 创建时间 |
| `updated_at` | ISO 8601 字符串 | 否 | 最近更新时间 |
| `last_used_at` | ISO 8601 字符串 | 是 | 从未使用时为 `null` |

### 5.2 RetrievedMemory

`POST /api/chat` 使用该对象说明记忆是否真正应用：

```json
{
  "id": "baf29d40-5e01-4be0-b7a1-553a871e5c21",
  "display_text": "服药提醒时间为晚上7点",
  "scope": "task",
  "task_type": "medication",
  "used": true
}
```

MVP 是规则检索，不返回虚构的相似度分数。`used=false` 表示记忆被检索到，但 Agent 没有将其用于最终回答或工具参数。

`RetrievedMemory` 的五个字段全部必填且不可空。`id` 对应 `MemoryView.id`，其余展示字段是本次请求发生时的快照。

### 5.3 ReminderView

```json
{
  "id": "9e9c66dc-0928-42da-83f2-ec2ec66a433a",
  "user_id": "demo-user",
  "title": "服用降压药",
  "next_trigger_at": "2026-08-22T19:00:00+08:00",
  "timezone": "Asia/Shanghai",
  "repeat_type": "daily",
  "status": "active",
  "last_triggered_at": null,
  "created_at": "2026-08-21T15:00:00+08:00",
  "updated_at": "2026-08-21T15:00:00+08:00"
}
```

枚举约束：

```text
repeat_type: none | daily | weekly
status: active | completed | deleted
```

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID 字符串 | 否 | 提醒 ID |
| `user_id` | 字符串 | 否 | 资源所属用户 |
| `title` | 字符串 | 否 | 手动输入长度 1 至 200；合并后的响应最长 4000 |
| `next_trigger_at` | ISO 8601 字符串 | 否 | 下一次触发时间 |
| `timezone` | IANA 时区字符串 | 否 | 例如 `Asia/Shanghai` |
| `repeat_type` | 枚举字符串 | 否 | `none`、`daily` 或 `weekly` |
| `status` | 枚举字符串 | 否 | `active`、`completed` 或 `deleted` |
| `last_triggered_at` | ISO 8601 字符串 | 是 | 最近一次已确认的计划触发时间；从未确认时为 `null` |
| `created_at` | ISO 8601 字符串 | 否 | 创建时间 |
| `updated_at` | ISO 8601 字符串 | 否 | 最近更新时间 |

### 5.4 RequestMetrics

```json
{
  "model_call_count": 1,
  "input_tokens": 640,
  "output_tokens": 48,
  "memory_tokens": 24,
  "retrieved_memory_count": 2,
  "used_memory_count": 1,
  "retrieval_ms": 8,
  "model_ms": 920,
  "tool_ms": 12,
  "total_ms": 978
}
```

`memory_tokens` 是注入模型上下文的记忆 Token 数，用于直接衡量记忆成本。`total_ms` 应包含检索、模型和工具执行时间。

`RequestMetrics` 的计数与耗时字段全部返回。`input_tokens`、`output_tokens` 在供应商不提供统计时为 `null`；其余字段不可空，未发生对应操作时返回 `0`。

### 5.5 ToolCallView

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | --- | --- |
| `tool_name` | 字符串 | 否 | 稳定工具名，例如 `create_reminder` |
| `status` | 枚举字符串 | 否 | `success` 或 `failed` |
| `summary` | 字符串 | 否 | 可展示摘要，不包含隐藏推理或敏感参数 |
| `latency_ms` | 非负整数 | 否 | 单次工具耗时 |

### 5.6 MemoryChange

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | --- | --- |
| `action` | 枚举字符串 | 否 | `created`、`updated` 或 `skipped` |
| `memory` | `MemoryView` | 是 | `skipped` 时为 `null`，其他情况不可空 |
| `reason` | 字符串 | 否 | 创建、更新或跳过的简短原因 |

### 5.7 FeedbackMetrics

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | --- | --- |
| `model_call_count` | 非负整数 | 否 | 没有调用模型时为 `0` |
| `input_tokens` | 非负整数 | 是 | 供应商未返回时为 `null` |
| `output_tokens` | 非负整数 | 是 | 供应商未返回时为 `null` |
| `total_ms` | 非负整数 | 否 | 反馈处理总耗时 |

### 5.8 DeleteResponse

提醒和记忆删除接口共用该模型：

```json
{
  "id": "9e9c66dc-0928-42da-83f2-ec2ec66a433a",
  "deleted": true
}
```

两个字段都必填且不可空。删除使用软删除，成功和重复删除都返回 `deleted=true`，不返回 `204 No Content`。

## 6. 健康检查

### `GET /api/health`

输入：无 Path、Query 或 Body 参数。

成功响应：`200 OK`，模型为 `HealthResponse`。

```json
{
  "status": "ok"
}
```

## 7. Agent 对话

### `POST /api/chat`

请求体数据模型（Pydantic）：`ChatRequest`

```json
{
  "user_id": "demo-user",
  "conversation_id": null,
  "message": "明天提醒我吃降压药",
  "timezone": "Asia/Shanghai"
}
```

字段规则：

| 字段 | 类型 | 必填 | 默认值 | 规则 |
| --- | --- | --- | --- | --- |
| `user_id` | 字符串 | 是 | 无 | 1 至 64 个字符 |
| `conversation_id` | UUID 字符串或 `null` | 否 | `null` | 为空时创建新会话；非空时必须属于该用户 |
| `message` | 字符串 | 是 | 无 | 去除首尾空格后长度为 1 至 2000 |
| `timezone` | IANA 时区字符串或 `null` | 否 | `null` | 为空时读取用户设置，再回退到 `Asia/Shanghai` |

成功响应：`200 OK`，模型为 `ChatResponse`。下列字段始终返回：

```text
request_id: UUID
conversation_id: UUID
user_message_id: UUID
assistant_message_id: UUID
status: completed | needs_clarification | partial
reply: string
retrieved_memories: RetrievedMemory[]
tool_calls: ToolCallView[]
memory_changes: MemoryChange[]
metrics: RequestMetrics
```

```json
{
  "request_id": "64e7398e-811a-4b2c-b301-e46ad4d180ba",
  "conversation_id": "95c37021-cbaa-45cb-92c5-d60390f88c95",
  "user_message_id": "90264fac-c73f-45e8-8bd2-a5a5a8c66a4b",
  "assistant_message_id": "59f973db-9a78-4520-a5e9-31c732459cd2",
  "status": "completed",
  "reply": "已设置明天晚上7点的服药提醒。",
  "retrieved_memories": [
    {
      "id": "baf29d40-5e01-4be0-b7a1-553a871e5c21",
      "display_text": "服药提醒时间为晚上7点",
      "scope": "task",
      "task_type": "medication",
      "used": true
    }
  ],
  "tool_calls": [
    {
      "tool_name": "create_reminder",
      "status": "success",
      "summary": "创建每日19:00服药提醒",
      "latency_ms": 12
    }
  ],
  "memory_changes": [],
  "metrics": {
    "model_call_count": 1,
    "input_tokens": 640,
    "output_tokens": 48,
    "memory_tokens": 24,
    "retrieved_memory_count": 1,
    "used_memory_count": 1,
    "retrieval_ms": 8,
    "model_ms": 920,
    "tool_ms": 12,
    "total_ms": 978
  }
}
```

`tool_calls[].status` 可为 `success` 或 `failed`。不得把失败的提醒工具描述为创建成功。

用户也可能直接在聊天框输入“以后都在晚上7点提醒”等反馈。此时 `/api/chat` 仍正常处理该消息，并通过 `memory_changes` 返回与 `/api/feedback` 相同的 `MemoryChange` 对象。普通任务返回空数组。

当提醒请求已经包含明确日期，仅缺少钟点，且检索到的 `preferred_time` 记忆能够唯一补全该参数时，Agent 可以走确定性记忆快速路径，直接调用 `ReminderService`。此时仍应返回 `used=true` 和成功的 `tool_calls`，但由于没有调用大模型，`model_call_count=0`、`input_tokens=null`、`output_tokens=null`、`memory_tokens=0`。其他开放式任务继续通过 LangChain Agent 处理。

当消息明确要求提醒，但只给出“上午”“下午”“晚上”“过会儿”等时间范围，或完全没有钟点，并且没有可用的 `preferred_time` 记忆时，Agent 必须直接返回 `needs_clarification`，不得让模型猜测默认钟点或调用工具。该确定性门禁同样可以减少不必要的模型请求。

多轮对话中，如果上一轮正在追问提醒钟点，下一轮只补充“下礼拜二上午”等片段，仍应继承提醒语境并继续追问具体钟点。用户询问、复述或确认刚创建的提醒时，只返回现有提醒信息，不得再次调用创建工具。复述日期应同时包含公历日期、星期和钟点，便于老年用户核对。

对高频且无歧义的输入错误可在规则层保守归一化，例如“晚丄→晚上”“7典→7点”“提酲→提醒”。归一化必须发生在任务分类和偏好提取之前；不得把药名、剂量或医疗事项按猜测改写。若本轮已经明确给出钟点，`preferred_time` 不得标记为已使用，也不得被本次值覆盖。

`status` 枚举：

```text
completed | needs_clarification | partial
```

状态语义：

- `completed`：回答和需要执行的工具均成功。
- `needs_clarification`：信息不足，未执行会产生副作用的工具。
- `partial`：已经生成可展示回答，但至少一个必要工具失败；`reply` 必须明确说明未完成事项，失败工具的 `status` 为 `failed`。

当时间、对象或动作不足以安全创建提醒时，不调用工具，返回：

```json
{
  "request_id": "64e7398e-811a-4b2c-b301-e46ad4d180ba",
  "conversation_id": "95c37021-cbaa-45cb-92c5-d60390f88c95",
  "user_message_id": "90264fac-c73f-45e8-8bd2-a5a5a8c66a4b",
  "assistant_message_id": "59f973db-9a78-4520-a5e9-31c732459cd2",
  "status": "needs_clarification",
  "reply": "您希望我几点提醒您吃药？",
  "retrieved_memories": [],
  "tool_calls": [],
  "memory_changes": [],
  "metrics": {
    "model_call_count": 1,
    "input_tokens": 260,
    "output_tokens": 18,
    "memory_tokens": 0,
    "retrieved_memory_count": 0,
    "used_memory_count": 0,
    "retrieval_ms": 3,
    "model_ms": 460,
    "tool_ms": 0,
    "total_ms": 478
  }
}
```

模型不可用或系统故障导致无法生成有效 `ChatResponse` 时返回 `502`。能够生成解释性回答的工具失败返回 `200 + status=partial`，不使用不存在的 `status=failed`。

## 8. 用户反馈

### `POST /api/feedback`

该接口用于点赞、点踩、编辑 Agent 结果等结构化反馈。用户在聊天框中直接表达的自然语言反馈仍发送到 `/api/chat`。

请求体数据模型（Pydantic）：`FeedbackRequest`

```json
{
  "user_id": "demo-user",
  "request_id": "64e7398e-811a-4b2c-b301-e46ad4d180ba",
  "feedback_text": "太晚了，以后服药都在晚上7点提醒",
  "corrected_reply": "已改为晚上7点提醒您服药。",
  "rating": "down"
}
```

字段规则：

| 字段 | 类型 | 必填 | 默认值 | 规则 |
| --- | --- | --- | --- | --- |
| `user_id` | 字符串 | 是 | 无 | 1 至 64 个字符 |
| `request_id` | UUID 字符串 | 是 | 无 | 必须对应同一用户的一次 `/api/chat` 请求 |
| `feedback_text` | 字符串或 `null` | 否 | `null` | 非空时去除首尾空格，最长 2000 |
| `corrected_reply` | 字符串或 `null` | 否 | `null` | 用户修正后的结果，最长 4000 |
| `rating` | 枚举字符串或 `null` | 否 | `null` | `up` 或 `down` |

`feedback_text`、`corrected_reply` 和 `rating` 至少提供一项，否则 Pydantic 校验返回 `422 INVALID_REQUEST`。
- 只有明确的长期表达才自动写入记忆；临时状态、推测偏好和未确认医疗信息必须跳过。
- 同一反馈同时包含临时描述和“以后”等长期表达时，只从长期语句片段提取偏好，不能被前面的临时时间干扰。
- 反馈按逗号、句号、分号和常见连接词拆分长期语句；一条反馈可以写入多个不同 `task_type + memory_key` 的偏好。
- 包含“不要”“不再”或“别”等否定表达的子句暂不自动写入记忆，但不影响同一反馈中其他明确的长期偏好。
- 同一反馈被重复提交时不得产生重复有效记忆。

成功响应：`200 OK`，模型为 `FeedbackResponse`：

```text
feedback_id: UUID
feedback_message_id: UUID
status: processed
memory_changes: MemoryChange[]
metrics: FeedbackMetrics
```

```json
{
  "feedback_id": "6098b877-8a80-4ad4-b6a1-2066e06c1c17",
  "feedback_message_id": "a2959b99-9655-40c4-9f45-5395810178f4",
  "status": "processed",
  "memory_changes": [
    {
      "action": "updated",
      "memory": {
        "id": "baf29d40-5e01-4be0-b7a1-553a871e5c21",
        "scope": "task",
        "task_type": "medication",
        "memory_key": "preferred_time",
        "memory_value": "19:00",
        "display_text": "服药提醒时间为晚上7点",
        "active": true,
        "source_message_id": "a2959b99-9655-40c4-9f45-5395810178f4",
        "created_at": "2026-08-20T15:00:00+08:00",
        "updated_at": "2026-08-21T15:00:00+08:00",
        "last_used_at": null
      },
      "reason": "明确表达了后续持续适用的服药提醒时间"
    }
  ],
  "metrics": {
    "model_call_count": 0,
    "input_tokens": null,
    "output_tokens": null,
    "total_ms": 3
  }
}
```

后端应把结构化反馈保存为一条用户消息，并通过 `feedback_message_id` 返回其 ID，使记忆来源可以追溯。

为保存评分、修正结果并支持重复提交去重，数据层需要增加最小 `feedbacks` 表：

```text
id, user_id, request_id, feedback_message_id,
feedback_text, corrected_reply, rating, dedup_key, created_at
```

`dedup_key` 可以由 `user_id + request_id + 规范化后的反馈内容` 计算。同一 `dedup_key` 重试时返回已有结果，不再次写入记忆。

`action` 枚举：

```text
created | updated | skipped
```

普通评价不应强行生成记忆。此时 `memory_changes` 可以包含一条 `skipped` 记录，其中 `memory` 为 `null`，并给出 `reason`。

## 9. 提醒接口

FastAPI 注册路由时，应在动态路由 `/api/reminders/{id}` 之前注册静态路由 `/api/reminders/due`，避免将 `due` 误解析为资源 ID。

### 9.1 创建提醒

### `POST /api/reminders`

用于前端手动创建提醒；Agent 内部工具调用相同的 `ReminderService`，不通过 HTTP 回调自身。

Path 参数：无。Query 参数：无。请求体数据模型（Pydantic）：`ReminderCreateRequest`。

```json
{
  "user_id": "demo-user",
  "title": "服用降压药",
  "next_trigger_at": "2026-08-22T19:00:00+08:00",
  "timezone": "Asia/Shanghai",
  "repeat_type": "daily"
}
```

| 字段 | 类型 | 必填 | 默认值 | 规则 |
| --- | --- | --- | --- | --- |
| `user_id` | 字符串 | 是 | 无 | 1 至 64 个字符 |
| `title` | 字符串 | 是 | 无 | 去除首尾空格后长度为 1 至 200 |
| `next_trigger_at` | ISO 8601 字符串 | 是 | 无 | 必须包含时区且晚于当前时间 |
| `timezone` | IANA 时区字符串 | 否 | `Asia/Shanghai` | 必须与用户期望时区一致 |
| `repeat_type` | 枚举字符串 | 否 | `none` | `none`、`daily` 或 `weekly` |

成功响应：`201 Created`，模型为 `ReminderView`，字段格式与 5.3 节完全一致。

活动提醒按 `user_id + next_trigger_at + timezone + repeat_type` 保证唯一：

- 相同日程和相同内容被重复创建时，返回原提醒，`id` 和 `created_at` 不变。
- 高置信度同义内容按同一事项处理，例如“吃降压药”与“服用降压药”、“去遛弯”与“散步”；不使用模型猜测药品或医疗事项是否等价。
- 相同日程但内容不同且周期规则相同时，将标题用中文分号合并到原提醒中，不新建第二条活动提醒。
- 相同日程和相同内容但周期规则不同时，按 `daily > weekly > none` 保留覆盖范围更大的提醒；弱周期提醒不会重复触发。
- 相同日程但内容和周期规则都不同时保持独立，避免把一次性内容错误地变成每日或每周事项。
- `completed` 或 `deleted` 提醒不参与创建去重。

过去时间、无效时区或无效枚举均由 Pydantic 校验返回 `422 INVALID_REQUEST`。

### 9.2 查询提醒

### `GET /api/reminders`

Path 参数：无。Body：无。查询参数数据模型（Pydantic）：`ReminderListQuery`。

| Query 字段 | 类型 | 必填 | 默认值 | 规则 |
| --- | --- | --- | --- | --- |
| `user_id` | 字符串 | 是 | 无 | 1 至 64 个字符 |
| `status` | 枚举字符串 | 否 | `active` | `active`、`completed`、`deleted` 或查询专用值 `all` |
| `limit` | 整数 | 否 | `50` | 1 至 100 |
| `offset` | 整数 | 否 | `0` | 大于等于 0 |

成功响应：`200 OK`，模型为 `ReminderListResponse`。

```json
{
  "items": [],
  "total": 0
}
```

`items` 类型为 `ReminderView[]`，即使没有数据也返回空数组。`total` 是忽略 `limit/offset` 后符合筛选条件的总数。`status=all` 时不按状态过滤。默认按 `next_trigger_at` 升序、`id` 升序返回。

### 9.3 查询到期提醒

### `GET /api/reminders/due`

Path 参数：无。Body：无。查询参数数据模型（Pydantic）：`DueReminderQuery`。

| Query 字段 | 类型 | 必填 | 默认值 | 规则 |
| --- | --- | --- | --- | --- |
| `user_id` | 字符串 | 是 | 无 | 1 至 64 个字符 |
| `limit` | 整数 | 否 | `20` | 1 至 50 |

返回条件：

```text
status = active
next_trigger_at <= 服务端当前时间
```

成功响应：`200 OK`，模型为 `ReminderListResponse`。

```json
{
  "items": [],
  "total": 0
}
```

`items` 类型为 `ReminderView[]`，按 `next_trigger_at` 升序、`id` 升序返回。这里的 `total` 是当前全部到期且未确认的数量，可能大于本次 `limit`。

同一提醒在确认前可以被多次轮询到，前端应按 `id + next_trigger_at` 去重展示。

### 9.4 修改提醒

### `PATCH /api/reminders/{id}`

Path 参数 `id` 为必填 UUID。Query 参数：无。请求体数据模型（Pydantic）：`ReminderUpdateRequest`。

```json
{
  "user_id": "demo-user",
  "title": "服用降压药",
  "next_trigger_at": "2026-08-22T18:30:00+08:00",
  "timezone": "Asia/Shanghai",
  "repeat_type": "daily",
  "status": "active"
}
```

| Body 字段 | 类型 | 必填 | 默认值 | 规则 |
| --- | --- | --- | --- | --- |
| `user_id` | 字符串 | 是 | 无 | 用于资源归属校验，不能修改所属用户 |
| `title` | 字符串 | 否 | 省略 | 提供时长度为 1 至 200；不可为 `null` |
| `next_trigger_at` | ISO 8601 字符串 | 否 | 省略 | 提供时必须包含时区且晚于当前时间；不可为 `null` |
| `timezone` | IANA 时区字符串 | 否 | 省略 | 提供时必须有效；不可为 `null` |
| `repeat_type` | 枚举字符串 | 否 | 省略 | `none`、`daily` 或 `weekly`；不可为 `null` |
| `status` | 枚举字符串 | 否 | 省略 | 仅允许 `active` 或 `completed`；删除使用 DELETE |

除 `user_id` 外至少提供一个修改字段。JSON 中显式传入 `null` 不表示清空，应按无效参数返回 `422`；未修改字段应直接省略。

成功响应：`200 OK`，模型为更新后的 `ReminderView`。资源不存在或不属于该用户时返回 `404 RESOURCE_NOT_FOUND`。若修改后的日程和内容已被更强周期的提醒覆盖，当前弱提醒会被软删除，响应返回实际存活的提醒，因此响应中的 `id` 可能与 Path 参数不同，调用方应以响应 `id` 为准。

### 9.5 删除提醒

### `DELETE /api/reminders/{id}`

Path 参数 `id` 为必填 UUID；Query 参数 `user_id` 为必填字符串；Body：无。

执行软删除，将 `status` 设置为 `deleted`。

成功响应：`200 OK`，模型为 `DeleteResponse`。

```json
{
  "id": "9e9c66dc-0928-42da-83f2-ec2ec66a433a",
  "deleted": true
}
```

重复删除返回同样结果，保证幂等。

### 9.6 确认提醒

### `POST /api/reminders/{id}/ack`

Path 参数 `id` 为必填 UUID。Query 参数：无。请求体数据模型（Pydantic）：`ReminderAckRequest`。

```json
{
  "user_id": "demo-user",
  "expected_trigger_at": "2026-08-22T19:00:00+08:00"
}
```

| Body 字段 | 类型 | 必填 | 默认值 | 规则 |
| --- | --- | --- | --- | --- |
| `user_id` | 字符串 | 是 | 无 | 用于资源归属校验 |
| `expected_trigger_at` | ISO 8601 字符串 | 是 | 无 | 必须等于前端本次展示的触发时间 |

`expected_trigger_at` 必须等于前端实际展示的 `next_trigger_at`：

- 若 `expected_trigger_at == last_triggered_at`，说明同一计划时刻已经确认，直接返回当前结果和 `already_acknowledged=true`。
- 否则 `expected_trigger_at` 必须等于当前 `next_trigger_at`，不相等时返回 `409 RESOURCE_CONFLICT`。
- 一次性提醒：将 `last_triggered_at` 设置为 `expected_trigger_at`，并将状态改为 `completed`。
- 每日提醒：将 `last_triggered_at` 设置为 `expected_trigger_at`，并将 `next_trigger_at` 推进到下一天。
- 每周提醒：将 `last_triggered_at` 设置为 `expected_trigger_at`，并将 `next_trigger_at` 推进到下一周同一天。
- 如果用户延迟确认周期提醒，应继续按本地自然日期推进，直到 `next_trigger_at` 晚于服务端当前时间，不能让确认后的提醒仍处于到期状态。
- 周期推进后的落点必须重新执行同周期内容合并和 `daily > weekly > none` 覆盖规则，避免唯一索引冲突或同一时刻重复提醒。
- 如果周期提醒在推进落点已被更强周期的同内容提醒覆盖，将当前弱提醒标记为 `completed`；更强提醒继续保持活动，重复确认仍返回同一弱提醒的幂等结果。
- 重复提交相同确认不得再次推进日期。
- 提醒已被其他请求修改：返回 `409 RESOURCE_CONFLICT`。

每日和每周提醒必须按 `timezone` 的本地自然日期计算相同钟点，不能简单增加固定小时数，否则夏令时地区会产生偏移。

成功响应：`200 OK`，模型为 `ReminderAckResponse`。

```json
{
  "reminder": {
    "id": "9e9c66dc-0928-42da-83f2-ec2ec66a433a",
    "user_id": "demo-user",
    "title": "服用降压药",
    "next_trigger_at": "2026-08-23T19:00:00+08:00",
    "timezone": "Asia/Shanghai",
    "repeat_type": "daily",
    "status": "active",
    "last_triggered_at": "2026-08-22T19:00:00+08:00",
    "created_at": "2026-08-21T15:00:00+08:00",
    "updated_at": "2026-08-22T19:00:05+08:00"
  },
  "already_acknowledged": false
}
```

## 10. 记忆接口

### 10.1 查询记忆

### `GET /api/memories`

Path 参数：无。Body：无。查询参数数据模型（Pydantic）：`MemoryListQuery`。

| Query 字段 | 类型 | 必填 | 默认值 | 规则 |
| --- | --- | --- | --- | --- |
| `user_id` | 字符串 | 是 | 无 | 1 至 64 个字符 |
| `active` | 布尔值或 `null` | 否 | `true` | 传 `false` 查询停用记忆；省略时只查有效记忆 |
| `task_type` | 枚举字符串或 `null` | 否 | `null` | `global`、`medication`、`walking`、`appointment` 或 `other` |
| `limit` | 整数 | 否 | `50` | 1 至 100 |
| `offset` | 整数 | 否 | `0` | 大于等于 0 |

成功响应：`200 OK`，模型为 `MemoryListResponse`。

```json
{
  "items": [],
  "total": 0
}
```

`items` 类型为 `MemoryView[]`，即使没有数据也返回空数组。`total` 是忽略 `limit/offset` 后符合筛选条件的总数。默认按 `updated_at` 降序、`id` 升序返回。

### 10.2 修改或停用记忆

### `PATCH /api/memories/{id}`

Path 参数 `id` 为必填 UUID。Query 参数：无。请求体数据模型（Pydantic）：`MemoryUpdateRequest`。

```json
{
  "user_id": "demo-user",
  "memory_value": "18:30",
  "display_text": "服药提醒时间为晚上6点半",
  "active": true
}
```

| Body 字段 | 类型 | 必填 | 默认值 | 规则 |
| --- | --- | --- | --- | --- |
| `user_id` | 字符串 | 是 | 无 | 用于资源归属校验，不能修改所属用户 |
| `memory_value` | 字符串 | 否 | 省略 | 提供时长度为 1 至 500；不可为 `null` |
| `display_text` | 字符串 | 否 | 省略 | 提供时长度为 1 至 200；不可为 `null` |
| `active` | 布尔值 | 否 | 省略 | 用于启用或停用记忆；不可为 `null` |

规则：

- 除 `user_id` 外全部为可选字段，但至少提供一个修改字段。
- 修改前后值必须写入 `memory_events`。
- 修改不能产生两个相同 `task_type + memory_key` 的有效记忆。
- 用户手动修改的值优先于模型推断值。
- JSON 中显式传入 `null` 不表示清空，应返回 `422`；未修改字段应省略。

成功响应：`200 OK`，响应体为更新后的 `MemoryView`。

资源不存在或不属于该用户时返回 `404 RESOURCE_NOT_FOUND`；重新启用会造成唯一键冲突时返回 `409 RESOURCE_CONFLICT`。

### 10.3 删除记忆

### `DELETE /api/memories/{id}`

Path 参数 `id` 为必填 UUID；Query 参数 `user_id` 为必填字符串；Body：无。

执行软删除，即设置 `active=false` 并记录 `memory_events`。

成功响应：`200 OK`，模型为 `DeleteResponse`。

```json
{
  "id": "baf29d40-5e01-4be0-b7a1-553a871e5c21",
  "deleted": true
}
```

重复删除返回同样结果，保证幂等。

## 11. 指标接口

### `GET /api/metrics/summary`

Path 参数：无。Body：无。查询参数数据模型（Pydantic）：`MetricsSummaryQuery`。

| Query 字段 | 类型 | 必填 | 默认值 | 规则 |
| --- | --- | --- | --- | --- |
| `user_id` | 字符串 | 是 | 无 | 1 至 64 个字符 |
| `from` | ISO 8601 字符串或 `null` | 否 | 最早记录时间 | 必须包含时区 |
| `to` | ISO 8601 字符串或 `null` | 否 | 服务端当前时间 | 必须包含时区且不早于 `from` |

Python 中 `from` 是保留字。FastAPI/Pydantic 内部字段使用 `from_`，并通过别名 `alias="from"` 保持 HTTP Query 名称为 `from`。

成功响应：`200 OK`，模型为 `MetricsSummaryResponse`。

```json
{
  "request_count": 20,
  "model_call_count": 22,
  "input_tokens": 12800,
  "output_tokens": 940,
  "memory_tokens": 510,
  "requests_with_retrieved_memory": 9,
  "requests_with_used_memory": 7,
  "token_metrics_complete": true,
  "average_retrieval_ms": 7.2,
  "average_model_ms": 880.5,
  "average_total_ms": 934.1,
  "from": "2026-08-01T00:00:00+08:00",
  "to": "2026-08-31T23:59:59+08:00"
}
```

`MetricsSummaryResponse` 字段类型：

```text
request_count: int >= 0
model_call_count: int >= 0
input_tokens: int >= 0
output_tokens: int >= 0
memory_tokens: int >= 0
requests_with_retrieved_memory: int >= 0
requests_with_used_memory: int >= 0
token_metrics_complete: bool
average_retrieval_ms: float >= 0
average_model_ms: float >= 0
average_total_ms: float >= 0
from: ISO 8601 | null
to: ISO 8601
```

`token_metrics_complete=false` 表示至少一次模型调用没有返回 Token 数据；Token 汇总只累计已知值，前端必须同时显示“不完整”，不能把它当作完整成本。

前端可以计算：

```text
记忆检索命中率 = requests_with_retrieved_memory / request_count
记忆实际使用率 = requests_with_used_memory / request_count
记忆 Token 占比 = memory_tokens / input_tokens
```

“记忆应用准确率”和“错误使用率”需要固定评测集判断，不能只根据线上计数自动得出。

查询范围内没有请求时，所有计数字段返回 `0`，平均耗时返回 `0.0`，前端不得执行除零运算。

## 12. Pydantic 模型清单

建议在 `backend/app/schemas/` 中建立：

```text
common.py
  ErrorDetail
  ErrorResponse
  HealthResponse
  DeleteResponse

chat.py
  ChatRequest
  ChatResponse
  RetrievedMemory
  ToolCallView
  RequestMetrics

feedback.py
  FeedbackRequest
  FeedbackResponse
  FeedbackMetrics

memory.py
  MemoryView
  MemoryChange
  MemoryListQuery
  MemoryListResponse
  MemoryUpdateRequest

reminder.py
  ReminderCreateRequest
  ReminderUpdateRequest
  ReminderAckRequest
  ReminderAckResponse
  ReminderView
  ReminderListQuery
  DueReminderQuery
  ReminderListResponse

metrics.py
  MetricsSummaryQuery
  MetricsSummaryResponse
```

## 13. 交接与实现边界

在 Pydantic 模型落地前，本文件是接口合同；模型落地后，`/openapi.json` 必须与本文件一致。任何字段、枚举、状态码或默认值变更，都应由队长先修改合同并通知两名队员，不能只改某一端代码。

交付顺序：

1. 队长先提交 `schemas/`、空路由和固定 Mock 响应。
2. 队员 A 按相同模型实现 Service 和数据库，不修改外部字段名。
3. 队员 B 根据 OpenAPI/本文件建立前端类型并接入 Mock。
4. 替换真实 Service 后运行合同测试，确认响应仍通过相同 Pydantic 模型。

### 13.1 API 层

- 只负责解析 Path、Query 和 Body，执行 Pydantic 校验并转换统一错误响应。
- 所有路由必须声明 `response_model`，不得直接返回未经约束的字典。
- 资源不存在和资源属于其他用户都返回 `404`，避免泄露其他用户数据。
- 不在路由函数中直接写 SQL，也不在路由中拼接模型 Prompt。

### 13.2 Agent 层

- `/api/chat` 负责串联任务分类、最多 3 条记忆检索、模型调用和工具调用。
- Agent 只返回简短结果、工具摘要和记忆使用标记，不暴露隐藏推理过程。
- Agent 内部调用 `ReminderService`，不得通过 HTTP 请求本项目自己的提醒接口。
- Agent 必须区分“检索到的记忆”和“最终实际使用的记忆”。

### 13.3 Service 与数据层

- `MemoryService` 负责检索、唯一有效偏好、反馈覆盖、停用和事件日志。
- `ReminderService` 负责创建、查询、修改、软删除和幂等确认。
- `MetricsService` 负责写入单次请求指标并计算汇总，不允许前端自行猜测缺失指标。
- 反馈记录、记忆修改与 `memory_events` 应在同一事务中完成。
- 提醒确认时比较 `expected_trigger_at`，读取、校验和更新应在同一事务中完成。

### 13.4 前端

- 只依赖本文件列出的响应模型，不读取未声明字段。
- 列表始终按 `items` 和 `total` 处理；空列表不是错误。
- 请求进行中禁用重复提交按钮；到期提醒按 `id + next_trigger_at` 去重。
- 遇到非 `2xx` 响应时统一读取 `ErrorResponse`。
- 页面显示 `retrieved_memories` 中 `used=true` 的项目以及 `metrics`，用于演示记忆效果和成本。

## 14. 基本情况覆盖检查

| 情况 | 接口行为 | 是否覆盖 |
| --- | --- | --- |
| 首次对话 | `conversation_id=null`，服务端创建会话 | 是 |
| 连续对话 | 校验会话属于当前 `user_id` | 是 |
| 输入为空 | 返回 `422` 或统一 `400` | 是 |
| 信息不足 | `status=needs_clarification`，不调用提醒工具 | 是 |
| 无效时区或过去时间 | 返回 `422` 或 `400 INVALID_REQUEST` | 是 |
| 没有相关记忆 | `retrieved_memories=[]` | 是 |
| 找到并使用记忆 | `used=true`，记录 Token 和耗时 | 是 |
| 找到但未使用记忆 | `used=false`，便于评估误检 | 是 |
| 无关记忆 | 按 `task_type` 过滤，最多检索 3 条 | 是 |
| 明确长期反馈 | 创建或更新记忆 | 是 |
| 聊天框中的自然语言反馈 | `/api/chat` 返回 `memory_changes` | 是 |
| 点赞、点踩或编辑结果 | `/api/feedback` 关联原请求 | 是 |
| 临时状态或普通评价 | `action=skipped` 并说明原因 | 是 |
| 重复反馈 | 不创建重复有效记忆 | 是 |
| 冲突偏好 | 更新原记忆并记录事件 | 是 |
| 用户纠正错误记忆 | `PATCH /api/memories/{id}` | 是 |
| 用户撤销记忆 | PATCH 停用或 DELETE 软删除 | 是 |
| 一次性提醒 | `repeat_type=none` | 是 |
| 每日提醒 | `repeat_type=daily` | 是 |
| 每周提醒 | `repeat_type=weekly`，确认后推进 7 个本地自然日 | 是 |
| 重复创建相同提醒 | 返回原提醒，不产生新 ID | 是 |
| 同时刻的不同提醒内容 | 周期规则相同时合并到一条提醒 | 是 |
| 到期提醒轮询 | `/api/reminders/due` | 是 |
| 重复轮询 | 前端按 `id + next_trigger_at` 去重 | 是 |
| 重复确认 | `expected_trigger_at` 防止日期重复推进 | 是 |
| 修改或删除提醒 | PATCH 和 DELETE | 是 |
| 模型失败 | 返回 `502 MODEL_UNAVAILABLE` | 是 |
| 工具失败但仍可解释 | 返回 `200 + status=partial`，工具标为 `failed` | 是 |
| 故障导致无法形成有效响应 | 返回 `502 MODEL_UNAVAILABLE` 或 `TOOL_EXECUTION_FAILED` | 是 |
| 跨用户访问资源 | 返回 `404`，不泄露资源是否存在 | 是 |
| 记忆成本评估 | 返回 `memory_tokens` 和 `retrieval_ms` | 是 |
| 对话速度评估 | 返回 `model_ms`、`tool_ms`、`total_ms` | 是 |

## 15. 实现优先级

### 第一批：先冻结并提供 Mock

1. `ChatRequest`、`ChatResponse`。
2. `FeedbackRequest`、`FeedbackResponse`。
3. `MemoryView`、`ReminderView`、`RequestMetrics`。
4. 统一错误响应。

### 第二批：完成主链路

1. `/api/chat`。
2. `/api/feedback`。
3. 记忆查询、修改和删除。
4. 提醒创建、查询和修改。

### 第三批：完成演示能力

1. 到期提醒轮询和确认。
2. 指标汇总。
3. 重复反馈、重复确认和跨用户测试。

## 16. 合理性结论

该接口集合可以覆盖黑客松 MVP 的所有基本情况，同时保持实现规模可控：

- Agent 只有一个同步入口，不引入任务队列或流式协议。
- 反馈独立建模，可以可靠关联原请求并展示记忆变化。
- 记忆使用过程可见，能够验证“检索到”和“实际使用”的区别。
- 提醒支持一次性、每日和每周重复，不引入通用 Cron 调度系统。
- 幂等删除和带期望时间的确认可以处理前端重复点击与轮询。
- 指标直接对应记忆成本、对话速度和记忆效果三个考查点。

后续若增加登录、可靠通知或向量检索，应新增版本或扩展字段，不修改当前字段语义。
