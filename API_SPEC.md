# Yoko API 接口规范

- 版本：`0.5.0`
- 状态：账号认证和业务接口 Session 隔离已接入
适用范围：适老陪伴、提醒、反馈记忆与效果评估

## 快速导航

- 全员先读：第 3 节通用约定、第 4 节接口总览、第 5.9 节认证合同。
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
- 支持用户名密码注册、登录、退出和固定 180 天 Session。
- 所有业务数据最终由服务端 Session 确定用户归属。

## 2. MVP 边界

本阶段不实现：

- 验证码、密码找回、修改密码和第三方登录。
- 管理员、家庭成员等多角色权限。
- WebSocket、SSE 流式输出。
- 向量数据库和相似度搜索。
- 通用 Cron 表达式。
- 网页关闭后的可靠系统通知。
- 文件上传、语音识别和多模态输入。
- 历史会话列表、跨设备会话恢复。

MVP 使用前端每 20 至 30 秒轮询到期提醒。网页关闭后不能保证提醒触发，演示时必须明确说明。

账号认证已接入 V3 数据库和真实 `AuthService`。除健康检查、就绪检查、注册和登录外，所有业务接口都要求有效 Session；客户端提交的 `user_id` 不参与资源归属判断。

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
- 用户身份由服务端 Session 确定，公开 Body 和 Query 不包含 `user_id`。
- 响应模型中的字段固定返回，不允许后端因值为空而临时省略字段。
- 列表没有数据时返回 `[]`，可空单值返回 `null`，不能用空字符串代替。
- 成功响应直接返回对应模型，不额外包裹 `data`；错误响应统一使用 `ErrorResponse`。
- `POST /api/chat` 可携带 `Idempotency-Key` 请求头；同一次业务请求重试时必须复用原键。

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
| `401` | 未登录、Session 失效或用户名密码错误 |
| `403` | 写请求缺少可信 `Origin` 或来源不受信任 |
| `404` | 会话、提醒、记忆或请求不存在 |
| `409` | 提醒已被修改、确认时间已失效或资源状态冲突 |
| `422` | Pydantic 字段校验失败 |
| `429` | 登录失败次数过多，需要暂时等待 |
| `502` | 模型或工具故障导致无法形成有效业务响应 |
| `503` | 数据库或必要运行依赖尚未就绪 |
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
AUTHENTICATION_REQUIRED
AUTHENTICATION_UNAVAILABLE
INVALID_CREDENTIALS
INVALID_REQUEST
ORIGIN_NOT_ALLOWED
RESOURCE_NOT_FOUND
RESOURCE_CONFLICT
TOO_MANY_ATTEMPTS
USERNAME_ALREADY_EXISTS
MODEL_UNAVAILABLE
TOOL_EXECUTION_FAILED
DATABASE_UNAVAILABLE
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

### 3.5 用户与认证约定

- 旧 `demo-user` 只用于保留历史本地数据，没有公开密码，不能登录。
- 注册是生产环境创建用户的唯一公开入口，查询和业务接口不得按任意 `user_id` 隐式创建用户。
- 聊天、反馈、提醒、记忆和指标接口全部从服务端 Session 取得用户 ID，HTTP 请求不接受 `user_id`。过渡期间旧客户端多传该字段时会被忽略。
- 未登录访问受保护接口返回 `401 AUTHENTICATION_REQUIRED`。
- `POST`、`PATCH` 和 `DELETE` 请求必须携带可信 `Origin`；允许配置的 `FRONTEND_ORIGIN` 和当前 API 同源，其他来源返回 `403 ORIGIN_NOT_ALLOWED`。
- Session 固定有效 180 天，普通业务请求不滑动续期；重新登录签发新的独立 Session。
- 同一账号允许多个设备分别登录；退出只撤销当前 Session。
- 原始 Session Token 只存于 `HttpOnly` Cookie，数据库只保存其 SHA-256 哈希。
- 密码只保存 Argon2id 哈希，不保存或记录明文。
- 修改密码必须验证当前密码，并撤销该账号全部旧 Session 后签发一个新 Session；Session 固定时长保持不变。
- 登录用户可以导出自己的业务数据，也可以在再次验证密码后删除账号及其全部关联数据。
- `ChatRequest.timezone` 只影响本次自然语言时间解析，不自动修改用户资料。

### 3.6 接口错误矩阵

所有表内错误均返回 `ErrorResponse`；未列出的未处理异常统一为 `500 INTERNAL_ERROR`。

| 接口 | 可能的业务错误 |
| --- | --- |
| `GET /api/health` | 通常无业务错误 |
| `GET /api/ready` | `503 DATABASE_UNAVAILABLE`、`503 MODEL_UNAVAILABLE` |
| `POST /api/auth/register` | `403 ORIGIN_NOT_ALLOWED`、`409 USERNAME_ALREADY_EXISTS`、`422 INVALID_REQUEST` |
| `POST /api/auth/login` | `401 INVALID_CREDENTIALS`、`403 ORIGIN_NOT_ALLOWED`、`422 INVALID_REQUEST` |
| `GET /api/auth/me` | `401 AUTHENTICATION_REQUIRED` |
| `POST /api/auth/logout` | `403 ORIGIN_NOT_ALLOWED`；无有效 Session 时仍幂等成功 |
| `POST /api/auth/password` | `400 INVALID_REQUEST`、`401 INVALID_CREDENTIALS`、`403 ORIGIN_NOT_ALLOWED`、`422 INVALID_REQUEST` |
| `GET /api/account/export` | `401 AUTHENTICATION_REQUIRED`、`404 RESOURCE_NOT_FOUND` |
| `DELETE /api/account` | `401 INVALID_CREDENTIALS`、`403 ORIGIN_NOT_ALLOWED`、`404 RESOURCE_NOT_FOUND`、`422 INVALID_REQUEST` |
| `POST /api/chat` | `400 INVALID_REQUEST`、`401 AUTHENTICATION_REQUIRED`、`403 ORIGIN_NOT_ALLOWED`、`404 RESOURCE_NOT_FOUND`、`409 RESOURCE_CONFLICT`、`422 INVALID_REQUEST`、`502 MODEL_UNAVAILABLE`、`502 TOOL_EXECUTION_FAILED` |
| `GET /api/chat/requests/{idempotency_key}` | `401 AUTHENTICATION_REQUIRED`、`404 RESOURCE_NOT_FOUND`、`422 INVALID_REQUEST` |
| `POST /api/feedback` | `401 AUTHENTICATION_REQUIRED`、`403 ORIGIN_NOT_ALLOWED`、`404 RESOURCE_NOT_FOUND`、`422 INVALID_REQUEST` |
| `POST /api/reminders` | `401 AUTHENTICATION_REQUIRED`、`403 ORIGIN_NOT_ALLOWED`、`404 RESOURCE_NOT_FOUND`、`422 INVALID_REQUEST` |
| `GET /api/reminders` | `401 AUTHENTICATION_REQUIRED`、`404 RESOURCE_NOT_FOUND`、`422 INVALID_REQUEST` |
| `GET /api/reminders/due` | `401 AUTHENTICATION_REQUIRED`、`404 RESOURCE_NOT_FOUND`、`422 INVALID_REQUEST` |
| `PATCH /api/reminders/{id}` | `400 INVALID_REQUEST`、`401 AUTHENTICATION_REQUIRED`、`403 ORIGIN_NOT_ALLOWED`、`404 RESOURCE_NOT_FOUND`、`409 RESOURCE_CONFLICT`、`422 INVALID_REQUEST` |
| `DELETE /api/reminders/{id}` | `401 AUTHENTICATION_REQUIRED`、`403 ORIGIN_NOT_ALLOWED`、`404 RESOURCE_NOT_FOUND`、`422 INVALID_REQUEST` |
| `POST /api/reminders/{id}/ack` | `401 AUTHENTICATION_REQUIRED`、`403 ORIGIN_NOT_ALLOWED`、`404 RESOURCE_NOT_FOUND`、`409 RESOURCE_CONFLICT`、`422 INVALID_REQUEST` |
| `GET /api/memories` | `401 AUTHENTICATION_REQUIRED`、`404 RESOURCE_NOT_FOUND`、`422 INVALID_REQUEST` |
| `PATCH /api/memories/{id}` | `401 AUTHENTICATION_REQUIRED`、`403 ORIGIN_NOT_ALLOWED`、`404 RESOURCE_NOT_FOUND`、`409 RESOURCE_CONFLICT`、`422 INVALID_REQUEST` |
| `DELETE /api/memories/{id}` | `401 AUTHENTICATION_REQUIRED`、`403 ORIGIN_NOT_ALLOWED`、`404 RESOURCE_NOT_FOUND`、`422 INVALID_REQUEST` |
| `GET /api/metrics/summary` | `400 INVALID_REQUEST`、`401 AUTHENTICATION_REQUIRED`、`404 RESOURCE_NOT_FOUND`、`422 INVALID_REQUEST` |

对重复反馈、重复删除和相同 `expected_trigger_at` 的重复确认，服务端返回原成功结果，不返回冲突错误。

除健康与就绪探针外，API 还执行可配置的进程内限流；超过通用、认证或聊天窗口时返回 `429 TOO_MANY_ATTEMPTS`，并携带 `Retry-After`。所有 API 响应均使用 `Cache-Control: no-store`、`X-Content-Type-Options: nosniff`、点击劫持限制、Referrer/Permissions Policy 和 CSP；HTTPS 响应额外携带 HSTS。当前限流状态仅适用于单进程部署，多实例必须改用共享限流设施。

## 4. 接口总览

| 方法 | 路径 | 输入 | 成功状态 | 响应数据模型 |
| --- | --- | --- | --- | --- |
| `GET` | `/api/health` | 无 | `200` | `HealthResponse` |
| `GET` | `/api/ready` | 无 | `200` | `ReadinessResponse` |
| `POST` | `/api/auth/register` | Body: `RegisterRequest` | `201` | `AuthResponse` |
| `POST` | `/api/auth/login` | Body: `LoginRequest` | `200` | `AuthResponse` |
| `GET` | `/api/auth/me` | Cookie: Session | `200` | `AuthResponse` |
| `POST` | `/api/auth/logout` | Cookie: 可选 Session | `200` | `LogoutResponse` |
| `POST` | `/api/auth/password` | Cookie: Session; Body: `ChangePasswordRequest` | `200` | `AuthResponse` |
| `GET` | `/api/account/export` | Cookie: Session | `200` | `AccountExportResponse` |
| `DELETE` | `/api/account` | Cookie: Session; Body: `AccountDeleteRequest` | `200` | `AccountDeleteResponse` |
| `POST` | `/api/chat` | Header: 可选 `Idempotency-Key`; Body: `ChatRequestBody` | `200` | `ChatResponse` |
| `GET` | `/api/chat/requests/{idempotency_key}` | Cookie: Session; Path: `idempotency_key` | `200` | `ChatRequestStatusResponse` |
| `POST` | `/api/feedback` | Body: `FeedbackRequestBody` | `200` | `FeedbackResponse` |
| `POST` | `/api/reminders` | Body: `ReminderCreateBody` | `201` | `ReminderView` |
| `GET` | `/api/reminders` | Query: `ReminderListParams` | `200` | `ReminderListResponse` |
| `GET` | `/api/reminders/due` | Query: `DueReminderParams` | `200` | `ReminderListResponse` |
| `PATCH` | `/api/reminders/{id}` | Path: `id`; Body: `ReminderUpdateBody` | `200` | `ReminderView` |
| `DELETE` | `/api/reminders/{id}` | Path: `id` | `200` | `DeleteResponse` |
| `POST` | `/api/reminders/{id}/ack` | Path: `id`; Body: `ReminderAckBody` | `200` | `ReminderAckResponse` |
| `GET` | `/api/memories` | Query: `MemoryListParams` | `200` | `MemoryListResponse` |
| `PATCH` | `/api/memories/{id}` | Path: `id`; Body: `MemoryUpdateBody` | `200` | `MemoryView` |
| `DELETE` | `/api/memories/{id}` | Path: `id` | `200` | `DeleteResponse` |
| `GET` | `/api/metrics/summary` | Query: `MetricsSummaryParams` | `200` | `MetricsSummaryResponse` |

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
  "model_call_count": 2,
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

`memory_tokens` 是注入模型上下文的记忆 Token 数，用于直接衡量记忆成本。`total_ms` 应包含检索、模型和工具执行时间。聊天请求的模型指标合并语义预处理、联网证据筛选（仅联网轮次）和主 Agent 阶段；常规请求至少包含预处理与主 Agent 两个模型调用，联网请求至少再增加一次证据筛选调用。若第一次结果全部无关，允许重写检索词并再筛选一次，因此最多再增加一次模型调用；工具循环或纠错也可能继续增加调用次数。

`RequestMetrics` 的计数与耗时字段全部返回。`input_tokens`、`output_tokens` 在供应商不提供统计时为 `null`；其余字段不可空，未发生对应操作时返回 `0`。

### 5.5 ToolCallView

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | --- | --- |
| `tool_name` | 字符串 | 否 | 稳定的写操作工具名：`create_reminder`、`update_reminder` 或 `delete_reminder` |
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

### 5.9 账号与 Session 对象

#### RegisterRequest

```json
{
  "username": "alice_01",
  "password": "correct-horse-2026",
  "display_name": "李阿姨",
  "timezone": "Asia/Shanghai"
}
```

| 字段 | 类型 | 必填 | 默认值 | 规则 |
| --- | --- | --- | --- | --- |
| `username` | 字符串 | 是 | 无 | 去除首尾空格后 3～32 位，只允许 ASCII 字母、数字和下划线 |
| `password` | 字符串 | 是 | 无 | 8～128 个字符，Pydantic 使用 `SecretStr`，不得回显或进入日志 |
| `display_name` | 字符串 | 是 | 无 | 去除首尾空格后 1～32 个字符，可使用中文 |
| `timezone` | IANA 时区字符串 | 否 | `Asia/Shanghai` | 必须可由 `zoneinfo.ZoneInfo` 解析 |

用户名唯一性使用 `username_normalized = username.strip().casefold()` 判断。服务端保留用户输入的展示用户名，同时以规范化值建立唯一索引。

#### LoginRequest

```json
{
  "username": "alice_01",
  "password": "correct-horse-2026"
}
```

字段规则与 `RegisterRequest` 相同。用户名不存在和密码错误统一返回 `401 INVALID_CREDENTIALS`，消息统一为“用户名或密码错误”，不得泄露账号是否存在。

#### UserView 与 AuthResponse

`UserView` 不包含密码哈希、失败次数、锁定时间或 Session Token：

```text
id: UUID
username: string
display_name: string
timezone: IANA timezone string
```

注册、登录和当前用户接口共用 `AuthResponse`：

```json
{
  "user": {
    "id": "64e7398e-811a-4b2c-b301-e46ad4d180ba",
    "username": "alice_01",
    "display_name": "李阿姨",
    "timezone": "Asia/Shanghai"
  },
  "session_expires_at": "2027-02-19T08:00:00Z"
}
```

`session_expires_at` 必须包含时区。原始 Session Token 只通过 `Set-Cookie` 返回，不进入 JSON。

#### LogoutResponse

```json
{
  "logged_out": true
}
```

退出必须幂等：有效 Session 立即撤销；Cookie 缺失、无效、已过期或已撤销时仍返回 `200` 和相同响应，同时删除浏览器 Cookie。

#### 账号数据管理对象

- `ChangePasswordRequest` 包含 `current_password` 和 `new_password`，均为 8～128 个字符且二者必须不同。成功后撤销全部旧 Session，并用 `AuthResponse` 签发新的当前 Session。
- `AccountDeleteRequest` 只包含再次确认用的 `password`；成功响应为 `AccountDeleteResponse`，固定返回 `deleted=true` 并删除 Cookie。
- `AccountExportResponse` 包含导出时间、无密码字段的账号资料，以及当前账号的消息、提醒、记忆与事件、请求指标和反馈。响应不包含密码哈希、Session、Token 或内部聊天租约记录。

#### 认证接口

##### `POST /api/auth/register`

- 输入：`RegisterRequest`。
- 成功：`201 AuthResponse`，同时签发 Session Cookie。
- 用户名已存在：`409 USERNAME_ALREADY_EXISTS`。
- 写请求必须携带可信 `Origin`。

##### `POST /api/auth/login`

- 输入：`LoginRequest`。
- 成功：`200 AuthResponse`，同时签发新的独立 Session Cookie。
- 用户名不存在、密码错误、账号禁用或账号处于临时锁定状态都返回相同的 `401 INVALID_CREDENTIALS`，不得据此判断账号是否存在。
- 已存在账号连续失败 5 次后暂停登录 15 分钟；锁定期间仍返回通用 `401`，成功登录后清零失败状态。
- 写请求必须携带可信 `Origin`。

##### `GET /api/auth/me`

- 输入：Session Cookie。
- 成功：`200 AuthResponse`。
- Cookie 缺失、Session 不存在、过期或撤销：`401 AUTHENTICATION_REQUIRED`。

##### `POST /api/auth/logout`

- 输入：可选 Session Cookie，无 JSON Body。
- 成功：`200 LogoutResponse`，撤销当前 Session 并删除 Cookie。
- 不因 Cookie 缺失或 Session 已失效返回 `401`。
- 写请求必须携带可信 `Origin`。

#### Session Cookie

```text
本地开发名称：yoko_session
生产环境名称：__Host-yoko_session
HttpOnly=true
SameSite=Lax
Path=/
Max-Age=15552000
Secure=false（仅本地 HTTP）
Secure=true（生产 HTTPS）
Domain 不设置
```

`15552000` 秒等于 180 天。若 Cookie 名以 `__Host-` 开头，必须同时满足 `Secure=true`、`Path=/` 和不设置 `Domain`。

#### 内部 Service 合同

`backend/app/services/auth_service.py` 的公开方法签名冻结为：

```python
AuthService(database: Database)

register(request: RegisterRequest) -> IssuedSession
login(request: LoginRequest) -> IssuedSession
resolve_session(session_token: str | None) -> AuthResponse
logout(session_token: str | None) -> None

IssuedSession
  token: str
  response: AuthResponse
```

`IssuedSession.token` 是只供路由设置 Cookie 的原始值，不得进入 Pydantic 响应、日志、异常消息或数据库。`AuthService` 的多表写操作必须使用数据库事务。

#### 内部 Repository 合同

队员 A 按以下语义实现，参数可以保持关键字参数和可选 `connection` 的现有风格：

```python
UserRepository.create_account(
    *, user_id, username, username_normalized, password_hash,
    display_name, timezone, connection=None
) -> dict

UserRepository.get_by_normalized_username(
    username_normalized, *, connection=None
) -> dict | None

UserRepository.update_login_state(
    user_id, *, failed_login_count, login_blocked_until,
    last_login_at=None, connection=None
) -> dict

AuthSessionRepository.create(
    *, session_id, user_id, token_hash, created_at, expires_at,
    connection=None
) -> dict

AuthSessionRepository.get_active_by_token_hash(
    token_hash, *, now, connection=None
) -> dict | None

AuthSessionRepository.revoke_by_token_hash(
    token_hash, *, revoked_at, connection=None
) -> bool

AuthSessionRepository.delete_expired(
    *, now, connection=None
) -> int
```

Repository 只接收 Session Token 哈希，不接收或保存原始 Token。`get_active_by_token_hash` 只返回未撤销且 `expires_at > now` 的记录。

#### V3 数据合同

扩展 `users`：

```text
username TEXT NULL
username_normalized TEXT NULL
password_hash TEXT NULL
disabled INTEGER NOT NULL DEFAULT 0
last_login_at TEXT NULL
failed_login_count INTEGER NOT NULL DEFAULT 0
login_blocked_until TEXT NULL
```

旧 `demo-user` 的账号字段保持 `NULL`，因此不能通过固定公开密码登录。对 `username_normalized IS NOT NULL` 建立唯一索引。

新增 `auth_sessions`：

```text
id TEXT PRIMARY KEY
user_id TEXT NOT NULL REFERENCES users(id)
token_hash TEXT UNIQUE NOT NULL
created_at TEXT NOT NULL
expires_at TEXT NOT NULL
revoked_at TEXT NULL
```

建立 `(user_id, expires_at)` 和 `(expires_at, revoked_at)` 索引。V3 迁移不得删除或改变现有消息、提醒、记忆、反馈和指标归属。

## 6. 健康检查

### `GET /api/health`

输入：无 Path、Query 或 Body 参数。

成功响应：`200 OK`，模型为 `HealthResponse`。

```json
{
  "status": "ok"
}
```

`GET /api/health` 只表示进程可响应，不访问数据库。

### `GET /api/ready`

输入：无 Path、Query 或 Body 参数。该接口检查 SQLite 可连接、必需表存在、数据库迁移版本与应用一致，并验证本地模型客户端配置可构造；不会向模型供应商发送请求。成功返回 `200 ReadinessResponse`，包含 `status=ok`、`database=ok`、`model=ok` 和当前 `schema_version`。数据库失败返回 `503 DATABASE_UNAVAILABLE`，模型配置失败返回 `503 MODEL_UNAVAILABLE`；两者都不向客户端暴露底层异常。

## 7. Agent 对话

### `POST /api/chat`

公开请求体数据模型（Pydantic）：`ChatRequestBody`。服务端通过 Session 注入用户 ID 后再构造内部 `ChatRequest`。

可选请求头：

| 请求头 | 类型 | 规则 |
| --- | --- | --- |
| `Idempotency-Key` | 字符串 | 8 至 128 个字符，只允许字母、数字、点、下划线、冒号和连字符；网络重试必须复用原值 |

```json
{
  "conversation_id": null,
  "message": "明天提醒我吃降压药",
  "timezone": "Asia/Shanghai"
}
```

字段规则：

| 字段 | 类型 | 必填 | 默认值 | 规则 |
| --- | --- | --- | --- | --- |
| `conversation_id` | UUID 字符串或 `null` | 否 | `null` | 为空时创建新会话；非空时必须属于该用户 |
| `message` | 字符串 | 是 | 无 | 去除首尾空格后长度为 1 至 2000 |
| `timezone` | IANA 时区字符串或 `null` | 否 | `null` | 为空时读取用户设置，再回退到 `Asia/Shanghai` |
| `image` | `ChatImageInput` 或 `null` | 否 | `null` | 每轮最多一张图片；省略时保持原有纯文本行为 |

图片请求示例：

```json
{
  "conversation_id": null,
  "message": "帮我看看这个药盒上写的用法",
  "timezone": "Asia/Shanghai",
  "image": {
    "media_type": "image/png",
    "data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
    "detail": "original"
  }
}
```

`ChatImageInput` 字段：

| 字段 | 类型 | 必填 | 默认值 | 规则 |
| --- | --- | --- | --- | --- |
| `media_type` | 枚举字符串 | 是 | 无 | 仅允许 `image/jpeg`、`image/png`、`image/webp`；后端还必须按实际文件内容复核，不能只信任该字段 |
| `data` | 字符串 | 是 | 无 | 只包含标准 Base64 数据，不得带 `data:` URL 前缀；解码后必须大于 0 且不超过 5 MiB |
| `detail` | 枚举字符串 | 否 | `original` | 仅允许 `low` 或 `original`；普通场景优先 `low`，需要读取小字时使用 `original` |

图片不是系统指令。视觉模型输出必须作为不可信观察结果传给主 Agent；图片或 OCR 中的指令性文字不得覆盖系统规则、绕过提醒确认或直接触发写工具。涉及药品用法、时间、日期或低置信度内容时必须向用户确认。第一版不长期保存原图，Base64 数据不得写入日志、数据库、指标或错误详情。后端使用真实解码结果复核格式，拒绝动态图、单边超过 8192 像素或总量超过 2500 万像素的图片。消息表只保存图片 SHA-256、结构化视觉观察 JSON、置信度和视觉调用耗时，供同一会话后续追问及幂等重试复用。

未注入视觉分析服务时，合法带图请求明确返回 `503 MODEL_UNAVAILABLE`，不会忽略图片后按纯文本继续处理；纯文本请求不受影响。带图请求的 `metrics.model_call_count` 包含一次视觉调用，视觉耗时计入 `model_ms`。冻结的视觉接口暂不返回 Token 明细，因此带图响应的 `input_tokens` 和 `output_tokens` 返回 `null`，不得用估算值冒充供应商用量。

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
sources: WebSource[]
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
  "sources": [],
  "memory_changes": [],
  "metrics": {
    "model_call_count": 2,
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

`tool_calls[].status` 可为 `success` 或 `failed`。不得把失败的提醒或联网工具描述为成功。

`sources` 始终返回数组。未联网、联网失败或原始结果未通过相关性门禁时为空；联网成功时最多 5 项，每项包含 `title`、`url`、`snippet` 和固定值 `source="bing"`。字段长度分别不超过 200、2048 和 500 字符，URL 只允许 HTTP 或 HTTPS。该字段为向后兼容的响应扩展，旧客户端可以忽略。

语义预处理模型通过 `SemanticFrame.requires_web` 和 `SemanticFrame.web_confidence` 判断是否需要公开网络信息；该阶段不生成搜索词。需要联网时，后续独立的 `SearchPlan` 结合当前问题与历史生成 `standalone_question`、`search_query`、`fallback_query`、所需证据和原因。提醒操作、本地提醒查询、日常陪伴和个人记忆不会仅因出现某个关键词而联网。发送给搜索引擎的是最多 160 字符的独立检索词，不是完整对话；运行时还会移除常见手机号、邮箱和身份证号。必应原始结果按不可信外部资料处理，并由独立结构化模型按当前问题筛选；仅共享地名、机构名或宽泛关键词的页面不得进入 `sources`。第一次结果全部无关时，筛选模型可以给出一个更宽但不改变主题的检索词，后端最多重试一次。没有直接相关证据时 `web_search` 标记为 `failed`、响应 `status=partial`，运行时用固定的自然失败回复覆盖主 Agent 可能补充的未接地细节。结果中的指令不能被执行或覆盖系统规则。

Agent 内部还可以调用只读的 `list_reminders` 获取真实状态。该调用计入 `tool_ms`，但不放入公共 `tool_calls`，因此 Agent 查询后仍可返回 `needs_clarification`，不改变现有响应校验规则。

用户也可能直接在聊天框输入“以后都在晚上7点提醒”等反馈。语义预处理阶段只生成 `SemanticFrame`，不写记忆；主 Agent 在自己的结构化结果中返回经过语义理解的记忆候选，`/api/chat` 校验并写入后，通过 `memory_changes` 返回与 `/api/feedback` 相同的 `MemoryChange` 对象。普通任务、临时状态和不明确偏好返回空数组。

每次 `/api/chat` 都先由独立的结构化模型调用结合最近历史和候选记忆生成 `SemanticFrame`，再由主 LangChain Agent 同时阅读用户原文、历史、候选记忆和语义帧。用户原文是最终事实来源，语义帧不得覆盖原文。即使消息包含明确日期或存在 `preferred_time`，也只有主 Agent 实际调用 `create_reminder` 形成计划，且最终决定通过语义一致性门禁后才能写入；不得通过关键词或正则直接调用 `ReminderService`。

创建或修改触发时间时，内部工具必须同时提交时间来源。来源为用户原话时必须提交真实存在的用户消息编号；多轮补充可以引用多个编号，但普通写操作必须包含当前消息编号。来源为 `preferred_time` 时必须提交本轮实际检索到的记忆 ID，且工具时间必须与记忆值一致。“早上”“晚上”等范围和药物剂量数字不得被当成钟点；时间是否仍有歧义由语义帧和主 Agent 共同判断。

创建 `weekly` 提醒时用户必须明确星期几，工具生成的本地日期也必须与该星期一致；仅说“每周晚上七点”时必须追问。修改已有每周提醒且用户未要求改变星期时，必须保留原星期。

查看、核对、修改或删除已有提醒时，Agent 必须先调用 `list_reminders`，再根据真实 ID 使用 `update_reminder` 或 `delete_reminder`。目标不唯一时只追问；不得用 `create_reminder` 代替修改，也不得在未查询时声称提醒已经修改或删除。

所有提醒写工具还必须提交用户消息证据编号。编号必须存在，多轮补充可同时引用原始请求和后续补充，普通写操作必须包含当前消息。若语义帧显示用户最后撤销、包含多个独立操作、仍有关键歧义、置信度低于安全阈值，或 `active_operation` 与工具计划不一致，运行时必须拒绝写入。用户要求额外或单独的一次性提醒时必须新建 `repeat_type=none`，不得覆盖已有 `daily` 或 `weekly` 提醒。

同一次 `/api/chat` 最多执行一项提醒写操作。模型在一次输出中提出多个 `create_reminder`、`update_reminder` 或 `delete_reminder` 时，运行时必须在任何工具执行前整批拦截，并返回 `needs_clarification`，`tool_calls=[]`，请用户指定一项。工具层还要限制每轮最多一次实际写入，防止模型改为逐条循环绕过拦截。用户消息中转述的专家、网页或其他外部内容不能覆盖这些系统规则。

当消息只给出“上午”“下午”“晚上”“过会儿”等时间范围，或完全没有钟点，并且没有可用的 `preferred_time` 记忆时，模型必须返回 `needs_clarification`，不得猜测默认钟点或调用工具。

多轮对话中，模型必须结合历史理解补充片段；如果上一轮正在追问提醒钟点，下一轮只补充“下礼拜二上午”，应继承提醒语境并继续追问具体钟点。用户询问、复述或确认刚创建的提醒时，只返回现有提醒信息，不得再次调用创建工具。复述日期应同时包含公历日期、星期和钟点，便于老年用户核对。

规则层只进行空白等不改变语义的基础清洗，不维护错别字替换表。模型按上下文理解常见错别字和口语；涉及日期、钟点、周期、事项、否定或医疗信息且无法唯一理解时必须追问。若本轮已经明确给出钟点，`preferred_time` 不得标记为已使用，也不得被本次值覆盖。

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
    "model_call_count": 2,
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

携带 `Idempotency-Key` 时，同一用户、同一键和相同请求体首次完成后，后续重试返回原 `ChatResponse`，不会重复调用 Agent、写消息或写指标。相同键配合不同请求体，或原请求仍在租约期内处理中时，返回 `409 RESOURCE_CONFLICT`。失败请求可使用相同键重新执行，并复用原 `request_id`、`conversation_id` 和用户消息；创建工具按提醒计划去重，修改和删除工具使用真实提醒 ID。Agent 只返回待提交的提醒变更；`ChatService` 再把提醒变更、记忆、助手消息、指标和缓存响应放入同一事务。任何收尾步骤失败都会回滚提醒变更，同键重试不会重复产生提醒副作用。

### `GET /api/chat/requests/{idempotency_key}`

用于客户端在 `POST /api/chat` 等待超时后查询同一业务请求的最终状态。路径参数规则与 `Idempotency-Key` 请求头一致，且请求必须属于当前 Session 用户；未知或其他用户的键统一返回 `404 RESOURCE_NOT_FOUND`。

成功响应模型为 `ChatRequestStatusResponse`：`request_id` 为原请求 UUID，`status` 为 `pending | completed | failed`。仅当状态为 `completed` 时 `response` 包含完整且已提交的 `ChatResponse`；其他状态下 `response=null`。该接口只读，不重新执行 Agent，也不会修改租约或产生提醒副作用。

## 8. 用户反馈

### `POST /api/feedback`

该接口用于点赞、点踩、编辑 Agent 结果等结构化反馈。用户在聊天框中直接表达的自然语言反馈仍发送到 `/api/chat`。

公开请求体数据模型（Pydantic）：`FeedbackRequestBody`。服务端通过 Session 注入用户 ID 后再构造内部 `FeedbackRequest`。

```json
{
  "request_id": "64e7398e-811a-4b2c-b301-e46ad4d180ba",
  "feedback_text": "太晚了，以后服药都在晚上7点提醒",
  "corrected_reply": "已改为晚上7点提醒您服药。",
  "rating": "down"
}
```

字段规则：

| 字段 | 类型 | 必填 | 默认值 | 规则 |
| --- | --- | --- | --- | --- |
| `request_id` | UUID 字符串 | 是 | 无 | 必须对应同一用户一次已生成 Agent 回复的 `/api/chat` 请求；失败且没有回复的请求不可反馈 |
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

用于前端手动创建提醒；Agent 的创建、查询、修改和删除工具直接调用相同的 `ReminderService`，不通过 HTTP 回调自身。

Path 参数：无。Query 参数：无。公开请求体数据模型（Pydantic）：`ReminderCreateBody`。

```json
{
  "title": "服用降压药",
  "next_trigger_at": "2026-08-22T19:00:00+08:00",
  "timezone": "Asia/Shanghai",
  "repeat_type": "daily"
}
```

| 字段 | 类型 | 必填 | 默认值 | 规则 |
| --- | --- | --- | --- | --- |
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
- 相同触发时刻但内容和周期规则都不同时返回 `409 RESOURCE_CONFLICT`，要求用户调整时间；不得创建会同时触发的第二条活动提醒，也不得把一次性内容错误地升级为每日或每周事项。
- 已有周期提醒覆盖未来同义的一次性事项时，返回原周期提醒，不新建第二条活动提醒。
- `completed` 或 `deleted` 提醒不参与创建去重。

过去时间、无效时区或无效枚举均由 Pydantic 校验返回 `422 INVALID_REQUEST`。

### 9.2 查询提醒

### `GET /api/reminders`

Path 参数：无。Body：无。公开查询参数数据模型（Pydantic）：`ReminderListParams`。

| Query 字段 | 类型 | 必填 | 默认值 | 规则 |
| --- | --- | --- | --- | --- |
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

Path 参数：无。Body：无。公开查询参数数据模型（Pydantic）：`DueReminderParams`。

| Query 字段 | 类型 | 必填 | 默认值 | 规则 |
| --- | --- | --- | --- | --- |
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

Path 参数 `id` 为必填 UUID。Query 参数：无。公开请求体数据模型（Pydantic）：`ReminderUpdateBody`。

```json
{
  "title": "服用降压药",
  "next_trigger_at": "2026-08-22T18:30:00+08:00",
  "timezone": "Asia/Shanghai",
  "repeat_type": "daily",
  "status": "active"
}
```

| Body 字段 | 类型 | 必填 | 默认值 | 规则 |
| --- | --- | --- | --- | --- |
| `title` | 字符串 | 否 | 省略 | 提供时长度为 1 至 200；不可为 `null` |
| `next_trigger_at` | ISO 8601 字符串 | 否 | 省略 | 提供时必须包含时区且晚于当前时间；不可为 `null` |
| `timezone` | IANA 时区字符串 | 否 | 省略 | 提供时必须有效；不可为 `null` |
| `repeat_type` | 枚举字符串 | 否 | 省略 | `none`、`daily` 或 `weekly`；不可为 `null` |
| `status` | 枚举字符串 | 否 | 省略 | 仅允许 `active` 或 `completed`；删除使用 DELETE |

至少提供一个修改字段。JSON 中显式传入 `null` 不表示清空，应按无效参数返回 `422`；未修改字段应直接省略。

成功响应：`200 OK`，模型为更新后的 `ReminderView`。资源不存在或不属于该用户时返回 `404 RESOURCE_NOT_FOUND`。若修改后的日程和内容已被更强周期的提醒覆盖，当前弱提醒会被软删除，响应返回实际存活的提醒，因此响应中的 `id` 可能与 Path 参数不同，调用方应以响应 `id` 为准。

### 9.5 删除提醒

### `DELETE /api/reminders/{id}`

Path 参数 `id` 为必填 UUID；Query 参数和 Body 均为空。资源归属由 Session 用户确定。

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

Path 参数 `id` 为必填 UUID。Query 参数：无。公开请求体数据模型（Pydantic）：`ReminderAckBody`。

```json
{
  "expected_trigger_at": "2026-08-22T19:00:00+08:00"
}
```

| Body 字段 | 类型 | 必填 | 默认值 | 规则 |
| --- | --- | --- | --- | --- |
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

Path 参数：无。Body：无。公开查询参数数据模型（Pydantic）：`MemoryListParams`。

| Query 字段 | 类型 | 必填 | 默认值 | 规则 |
| --- | --- | --- | --- | --- |
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

Path 参数 `id` 为必填 UUID。Query 参数：无。公开请求体数据模型（Pydantic）：`MemoryUpdateBody`。

```json
{
  "memory_value": "18:30",
  "display_text": "服药提醒时间为晚上6点半",
  "active": true
}
```

| Body 字段 | 类型 | 必填 | 默认值 | 规则 |
| --- | --- | --- | --- | --- |
| `memory_value` | 字符串 | 否 | 省略 | 提供时长度为 1 至 500；不可为 `null` |
| `display_text` | 字符串 | 否 | 省略 | 提供时长度为 1 至 200；不可为 `null` |
| `active` | 布尔值 | 否 | 省略 | 用于启用或停用记忆；不可为 `null` |

规则：

- 全部字段均为可选，但至少提供一个修改字段。
- 修改前后值必须写入 `memory_events`。
- 修改不能产生两个相同 `task_type + memory_key` 的有效记忆。
- 用户手动修改的值优先于模型推断值。
- JSON 中显式传入 `null` 不表示清空，应返回 `422`；未修改字段应省略。

成功响应：`200 OK`，响应体为更新后的 `MemoryView`。

资源不存在或不属于该用户时返回 `404 RESOURCE_NOT_FOUND`；重新启用会造成唯一键冲突时返回 `409 RESOURCE_CONFLICT`。

### 10.3 删除记忆

### `DELETE /api/memories/{id}`

Path 参数 `id` 为必填 UUID；Query 参数和 Body 均为空。资源归属由 Session 用户确定。

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

Path 参数：无。Body：无。公开查询参数数据模型（Pydantic）：`MetricsSummaryParams`。

| Query 字段 | 类型 | 必填 | 默认值 | 规则 |
| --- | --- | --- | --- | --- |
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
  ReadinessResponse
  DeleteResponse

auth.py
  RegisterRequest
  LoginRequest
  UserView
  AuthResponse
  LogoutResponse

chat.py
  ChatImageInput
  ChatRequestBody
  ChatRequest
  ChatResponse
  RetrievedMemory
  ToolCallView
  RequestMetrics

services/vision_contract.py（内部契约，不是公开 API 模型）
  VisionObservation
  VisionAnalyzer

feedback.py
  FeedbackRequestBody
  FeedbackRequest
  FeedbackResponse
  FeedbackMetrics

memory.py
  MemoryView
  MemoryChange
  MemoryListParams
  MemoryListQuery
  MemoryListResponse
  MemoryUpdateBody
  MemoryUpdateRequest

reminder.py
  ReminderCreateBody
  ReminderCreateRequest
  ReminderUpdateBody
  ReminderUpdateRequest
  ReminderAckBody
  ReminderAckRequest
  ReminderAckResponse
  ReminderView
  ReminderListParams
  ReminderListQuery
  DueReminderParams
  DueReminderQuery
  ReminderListResponse

metrics.py
  MetricsSummaryParams
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
- 认证路由只通过 `AuthService` 读写账号和 Session；原始 Token 只用于设置或读取 Cookie。
- 受保护路由必须使用 `get_current_user`，公开输入不得决定资源所属用户。
- 所有写路由必须使用 `require_trusted_origin`；跨用户资源统一按不存在处理。

### 13.2 Agent 层

- `/api/chat` 负责串联最多 10 条有界候选记忆、结构化语义预处理、主 Agent 判断和工具调用。候选池先为每个实际存在的任务类型保留一个最新槽位，再按更新时间补满；这可以避免近期无关任务完全挤掉较旧的相关偏好，同时保持 Token 上限。
- 语义预处理只生成 `SemanticFrame`，不能调用工具；主 Agent 写工具只暂存计划，最终通过语义帧、结构化决定和确定性校验后执行。
- `model_call_count`、`input_tokens`、`output_tokens` 和 `model_ms` 合并预处理、联网证据筛选（联网轮次一至两次）与主 Agent 阶段；当前 API 不单独返回各阶段指标。
- 候选记忆不再由关键词任务分类硬过滤；Agent 结合完整语义判断相关性并仅标记实际使用项。
- 创建提醒必须由模型明确调用工具触发，关键词、正则或错别字替换不得直接产生写操作。
- Agent 只返回简短结果、工具摘要和记忆使用标记，不暴露隐藏推理过程。
- Agent 内部调用 `ReminderService`，不得通过 HTTP 请求本项目自己的提醒接口。
- Agent 必须区分“检索到的记忆”和“最终实际使用的记忆”。

### 13.3 Service 与数据层

- `MemoryService` 负责检索、唯一有效偏好、反馈覆盖、停用和事件日志。
- `ReminderService` 负责创建、查询、修改、软删除和幂等确认。
- `MetricsService` 负责写入单次请求指标并计算汇总，不允许前端自行猜测缺失指标。
- 数据库结构通过 `schema_migrations` 顺序升级；旧版无迁移记录的数据库在执行兼容清理前必须生成 SQLite 备份。
- `ChatService` 使用 `chat_requests` 记录执行状态和幂等结果；模型调用期间不得持有长事务。
- Chat 收尾阶段的提醒变更、记忆使用、偏好更新、助手消息、指标和最终响应必须在同一事务中完成。
- 反馈记录、记忆修改与 `memory_events` 应在同一事务中完成。
- 提醒确认时比较 `expected_trigger_at`，读取、校验和更新应在同一事务中完成。
- `AuthService` 负责用户名规范化、Argon2id 密码验证、登录失败限制、Session 签发、解析和撤销。
- `AuthService` 同时负责修改密码、账号数据导出和账号删除；导出不得包含认证密钥材料，删除必须在单一事务中清理全部关联表。
- `AuthSessionRepository` 只保存随机 Session Token 的 SHA-256 哈希；原始 Token 不得离开 API 进程内存。
- SQLite 使用 WAL 与 `synchronous=NORMAL`；运维备份通过 `python -m backend.scripts.backup_database` 调用 SQLite 在线备份 API，调度频率由部署平台负责。

### 13.4 前端

- 只依赖本文件列出的响应模型，不读取未声明字段。
- 列表始终按 `items` 和 `total` 处理；空列表不是错误。
- 请求进行中禁用重复提交按钮；到期提醒按 `id + next_trigger_at` 去重。
- 遇到非 `2xx` 响应时统一读取 `ErrorResponse`。
- 页面显示 `retrieved_memories` 中 `used=true` 的项目以及 `metrics`，用于演示记忆效果和成本。
- 账号接入后所有请求使用 `credentials: include`，启动时通过 `/api/auth/me` 恢复登录状态。
- 前端不保存密码和 Session Token；表单只使用标准 `autocomplete` 配合浏览器密码管理器。

## 14. 基本情况覆盖检查

| 情况 | 接口行为 | 是否覆盖 |
| --- | --- | --- |
| 首次对话 | `conversation_id=null`，服务端创建会话 | 是 |
| 注册新账号 | 创建用户、签发 180 天 Session，不返回密码 | 是 |
| 重复用户名 | 大小写无关比较，返回 `409` | 是 |
| 错误密码或锁定账号 | 统一返回 `401 INVALID_CREDENTIALS` | 是 |
| 登录失败过多 | 第 5 次失败后暂停 15 分钟，外部响应不暴露账号状态 | 是 |
| 刷新恢复登录 | `/api/auth/me` 返回当前用户和到期时间 | 是 |
| Session 过期 | 返回 `401`，要求重新登录 | 是 |
| 重复退出 | 始终返回 `logged_out=true` | 是 |
| 账号数据隔离 | 业务路由只采用 Session 用户 ID | 是 |
| 不可信写请求来源 | 返回 `403 ORIGIN_NOT_ALLOWED` | 是 |
| 连续对话 | 校验会话属于当前 `user_id` | 是 |
| 输入为空 | 返回 `422` 或统一 `400` | 是 |
| 信息不足 | `status=needs_clarification`，不执行写操作，公共 `tool_calls=[]` | 是 |
| 无效时区或过去时间 | 返回 `422` 或 `400 INVALID_REQUEST` | 是 |
| 没有相关记忆 | `retrieved_memories=[]` | 是 |
| 找到并使用记忆 | `used=true`，记录 Token 和耗时 | 是 |
| 找到但未使用记忆 | `used=false`，便于评估误检 | 是 |
| 无关记忆 | 最多提供 3 条候选，由模型判断相关性，未使用项标记 `used=false` | 是 |
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
5. 认证 Schema、内部签名和真实 Session 接入。

### 第二批：完成主链路

1. `/api/chat`。
2. `/api/feedback`。
3. 记忆查询、修改和删除。
4. 提醒创建、查询和修改。

### 第三批：完成演示能力

1. 到期提醒轮询和确认。
2. 指标汇总。
3. 重复反馈、重复确认和跨用户测试。

### 第四批：账号与云端部署

1. V3 账号和 Session 数据迁移。
2. Argon2id 注册登录与 180 天 Session。
3. 全部业务 API 改用服务端 Session 用户。
4. 前端登录状态、账号切换和本地历史隔离。
5. HTTPS、持久化 SQLite 和双账号端到端测试。

## 16. 合理性结论

该接口集合可以覆盖黑客松 MVP 的所有基本情况，同时保持实现规模可控：

- Agent 只有一个同步入口，不引入任务队列或流式协议。
- 反馈独立建模，可以可靠关联原请求并展示记忆变化。
- 记忆使用过程可见，能够验证“检索到”和“实际使用”的区别。
- 提醒支持一次性、每日和每周重复，不引入通用 Cron 调度系统。
- 幂等删除和带期望时间的确认可以处理前端重复点击与轮询。
- 指标直接对应记忆成本、对话速度和记忆效果三个考查点。
- 服务端 Session 保持实现轻量，同时可以立即撤销并隔离用户数据。

后续若增加密码找回、多角色权限、可靠通知或向量检索，应新增版本或扩展字段，不修改当前字段语义。
