# Yoko
YOur Kins Online -- Agent designed for elderly people.

API contract: [API_SPEC.md](API_SPEC.md)

## Development environment

- Windows 10 or 11
- Python 3.11
- Node.js 24 LTS or another supported LTS release
- FastAPI, LangChain, React, Vite and SQLite

Activate a Python 3.11 environment, then install the dependencies from the
repository root:

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
Set-Location .\frontend
npm.cmd ci
Set-Location ..
```

## Backend

Open PowerShell in the repository root and run:

```powershell
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Keep this terminal open, then visit the API documentation:
<http://127.0.0.1:8000/docs>

The backend applies versioned SQLite migrations during application startup. A
legacy database is backed up before compatibility cleanup. Reminder,
memory, feedback, metrics and chat endpoints are listed in `API_SPEC.md` and
the generated API documentation. `/api/chat` requires `MODEL_NAME` and model
credentials; the other endpoints can run without an LLM key.

Account authentication is active in API contract version `0.5.0`. Registration
and login issue a fixed 180-day HttpOnly session cookie backed by the V3 SQLite
schema. Chat, feedback, reminder, memory, and metrics endpoints require that
session and derive ownership on the server; a client-supplied `user_id` is
ignored during the temporary frontend transition. State-changing requests also
require the configured frontend origin or the API's own origin.

`GET /api/health` is the process liveness check and `GET /api/ready` verifies
the database, migration version, and local model-client configuration without
sending a model request. Chat clients may send an `Idempotency-Key`
header and must reuse it when retrying the same request.

Each chat turn first runs a structured semantic-preprocessing model call and
then the main Agent. The resulting `SemanticFrame` marks the final operation,
self-corrections, cancellation, ambiguity, evidence message numbers and
confidence. Reminder writes are staged and execute only after the final Agent
decision agrees with that frame. The reminder mutation, memory changes,
assistant message, metrics, and idempotent response then commit in one SQLite
transaction. A deterministic guard also verifies real
message numbers, at most one mutation, list-before-update/delete and retrieved
`preferred_time` memory IDs. The original user text remains the source of truth.

Run tests:

```powershell
python -m pytest backend\tests -q
```

After configuring `.env`, run one real-model smoke test. It uses a temporary
database and does not modify `backend/data/app.db`:

```powershell
python -m backend.tests.evaluation.run_live_model_smoke
```

运行一次真实模型加必应联网的端到端冒烟测试：

```powershell
python -m backend.tests.evaluation.run_live_web_search_smoke
```

Run the strict live evaluation for typos, ambiguous requests, corrections,
prompt injection, medication safety, idempotency and memory overrides:

```powershell
python -m backend.tests.evaluation.run_live_stress_evaluation
```

Run the multi-turn high-difficulty evaluation where date, clock, recurrence
and preference fields contain realistic input errors and corrections:

```powershell
python -m backend.tests.evaluation.run_live_dialogue_evaluation
```

Run the tracked 40-turn adversarial protocol only after approving real-model
costs. It validates that each attack objective was actually materialized before
scoring and uses a temporary registered account and database:

```powershell
python -m backend.tests.evaluation.run_live_adversarial_evaluation
```

## Frontend

```powershell
Set-Location .\frontend
npm.cmd run dev
```

Frontend URL: <http://127.0.0.1:5173>

## Environment variables

The local `.env` file has been created with empty model credentials. Fill in
`MODEL_NAME`, `OPENAI_API_KEY`, and `OPENAI_BASE_URL` when required. Never
commit `.env`.

Image understanding uses the independent `VISION_MODEL_NAME`,
`VISION_API_KEY`, and `VISION_BASE_URL` settings. If the vision key or base URL
is empty, the corresponding `OPENAI_*` setting is used as a compatibility
fallback. Image requests are never sent to LangSmith tracing.

Authentication defaults are:

```text
SESSION_TTL_DAYS=180
AUTH_COOKIE_SECURE=false
AUTH_COOKIE_NAME=yoko_session
```

Production HTTPS must use `AUTH_COOKIE_SECURE=true` and the
`__Host-yoko_session` cookie name.

The backend also provides password change, JSON account export, and confirmed
account deletion endpoints. API requests include security headers and are
rate-limited in process for the current single-instance SQLite deployment. The
limits can be configured with the `RATE_LIMIT_*` variables in `.env.example`.

Create a consistent SQLite backup (and retain the newest 14 files) with:

```powershell
python -m backend.scripts.backup_database --keep 14
```

---

# 中文说明

Yoko（YOur Kins Online）是一个面向老年人的 Agent 系统。

API 接口规范：[API_SPEC.md](API_SPEC.md)

## 开发环境

- Windows 10 或 Windows 11
- Python 3.11
- Node.js 24 LTS 或其他仍受支持的 LTS 版本
- FastAPI、LangChain、React、Vite 和 SQLite

激活 Python 3.11 环境，然后在仓库根目录安装依赖：

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
Set-Location .\frontend
npm.cmd ci
Set-Location ..
```

## 后端

在仓库根目录打开 PowerShell 并运行：

```powershell
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

保持该终端运行，然后访问 API 文档：
<http://127.0.0.1:8000/docs>

后端会在应用启动时顺序执行版本化 SQLite 迁移；旧版数据库在兼容清理前会自动
生成备份。提醒、记忆、反馈、指标和聊天接口见
`API_SPEC.md` 及自动生成的 API 文档。`/api/chat` 需要配置 `MODEL_NAME` 和模型
凭据，其他接口不依赖大模型密钥即可运行。

账号认证已在接口合同 `0.5.0` 中启用。注册和登录使用 V3 SQLite 数据结构签发
固定 180 天的 HttpOnly Session Cookie。聊天、反馈、提醒、记忆和指标接口都要求
有效 Session，资源归属由后端确定；前端过渡期间多传的 `user_id` 会被忽略。
所有写请求还必须来自配置的前端 Origin 或 API 同源页面。

`GET /api/health` 用于进程存活检查，`GET /api/ready` 检查数据库连接、迁移版本和
本地模型客户端配置；该检查不会发送真实模型请求。
聊天客户端可以发送 `Idempotency-Key` 请求头；重试同一请求时必须复用原值。

每轮聊天先调用一次结构化语义预处理模型生成 `SemanticFrame`，再运行主 Agent。
语义帧标记最终操作、改口、撤销、歧义、用户消息证据编号和置信度；用户原文仍是
最终事实来源。只有主 Agent 明确调用工具形成计划，且最终决定与语义帧一致时才会
写入。提醒变更、记忆变更、助手消息、指标和幂等响应会在同一 SQLite 事务提交。
`preferred_time` 可以补全缺失钟点，但关键词、正则和固定错别字替换不会直接
创建提醒；长期偏好候选由主 Agent 的结构化结果返回。

当用户明确要求查询公开网络信息，或问题依赖会变化的外部事实时，语义预处理模型会
生成独立、去隐私化的搜索词，由后端抓取必应前 5 条自然搜索结果。搜索使用现有
`httpx` 与标准库解析器，不需要额外搜索 API 密钥。原始结果会先经过独立的结构化模型
相关性门禁，只有能直接支持当前问题的证据才会交给主 Agent，并通过 `sources` 返回
标题、链接和摘要。第一次结果全部无关时，门禁可以生成一个更宽但仍聚焦的检索词，
最多额外搜索并筛选一次。搜索超时、限流、验证码、页面结构变化，或两次结果仍与问题
没有直接关系时，聊天接口返回 `partial` 并明确说明无法核实，不会用模型旧知识冒充
实时结果。

Agent 内部提供提醒查询、创建、修改和删除工具。核对、修改或删除前会先读取真实
提醒状态；只读查询不出现在公共 `tool_calls` 中。创建和改时间还会校验明确钟点或
实际使用的时间记忆，并核对落库后的本地钟点与用户原话一致，不能把“早上”“晚上”
等范围自行换成 8 点。每周提醒必须明确星期几，不能自行猜成当天或周日。

提醒写操作采用语义门禁和确定性结构校验：模型同一轮提出多个创建、修改、删除时会
在执行前整批拦截；单个写计划必须提交真实存在的用户消息编号，普通写操作必须包含
当前消息。修改和删除前必须先查询真实提醒；使用时间记忆时必须引用本轮检索到且时间
一致的记忆 ID。用户最终撤销、语义仍有歧义或计划与语义帧不一致时不会写入，并返回
自然澄清说明。该策略不改变 REST API 字段。

运行后端测试：

```powershell
python -m pytest backend\tests -q
```

配置 `.env` 后，可运行一次真实模型冒烟测试。该命令使用临时数据库，不会修改
`backend/data/app.db`：

```powershell
python -m backend.tests.evaluation.run_live_model_smoke
```

运行包含错别字、模糊请求、前后修正、提示注入、用药安全、幂等和记忆覆盖的
真实模型严苛评测：

```powershell
python -m backend.tests.evaluation.run_live_stress_evaluation
```

运行多轮高难度真实模型评测。该评测会在日期、钟点、周期和偏好等关键字段中
加入合理的输入错误、逐步补充和前后修正：

```powershell
python -m backend.tests.evaluation.run_live_dialogue_evaluation
```

完整 40 轮攻击协议已经纳入版本控制，并会在计分前检查“重复创建”等目标是否真的
出现在合成用户消息中。该命令会产生真实模型费用，必须在确认费用后运行；评测使用
临时注册账号和临时数据库：

```powershell
python -m backend.tests.evaluation.run_live_adversarial_evaluation
```

## 前端

```powershell
Set-Location .\frontend
npm.cmd run dev
```

前端地址：<http://127.0.0.1:5173>

## 环境变量

本地 `.env` 文件由 `.env.example` 创建，模型凭据默认为空。需要调用模型时，
请填写 `MODEL_NAME`、`OPENAI_API_KEY` 和 `OPENAI_BASE_URL`。不要提交 `.env`。

图片理解使用独立的 `VISION_MODEL_NAME`、`VISION_API_KEY` 和
`VISION_BASE_URL`。视觉 Key 或地址留空时，会兼容回退到对应的 `OPENAI_*`
配置。图片请求不会发送到 LangSmith 链路追踪。

认证配置默认值：

```text
SESSION_TTL_DAYS=180
AUTH_COOKIE_SECURE=false
AUTH_COOKIE_NAME=yoko_session
```

生产 HTTPS 环境必须使用 `AUTH_COOKIE_SECURE=true` 和
`__Host-yoko_session` Cookie 名称。

后端同时提供修改密码、JSON 账号数据导出和密码确认后的账号删除接口。API 默认附加
安全响应头，并按 `.env.example` 中的 `RATE_LIMIT_*` 配置执行进程内限流；该实现适配
当前单实例 SQLite 部署，多实例部署应改用网关或 Redis 共享限流。

生成一致性 SQLite 备份并仅保留最新 14 份：

```powershell
python -m backend.scripts.backup_database --keep 14
```
