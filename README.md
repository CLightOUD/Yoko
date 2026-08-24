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

Account authentication is active in API contract version `0.4.0`. Registration
and login issue a fixed 180-day HttpOnly session cookie backed by the V3 SQLite
schema. Chat, feedback, reminder, memory, and metrics endpoints require that
session and derive ownership on the server; a client-supplied `user_id` is
ignored during the temporary frontend transition. State-changing requests also
require the configured frontend origin or the API's own origin.

`GET /api/health` is the process liveness check and `GET /api/ready` verifies
the database and migration version. Chat clients may send an `Idempotency-Key`
header and must reuse it when retrying the same request.

Reminder intent and retrieved `preferred_time` memories are interpreted by the
Agent model before any write tool can run. A mutation guard blocks multiple
create, update, or delete calls in one request before execution, and each write
tool verifies a verbatim user-intent quote. Batch changes are handled one item
at a time to limit accidental or prompt-injected writes.

Run tests:

```powershell
python -m pytest backend\tests -q
```

After configuring `.env`, run one real-model smoke test. It uses a temporary
database and does not modify `backend/data/app.db`:

```powershell
python -m backend.tests.evaluation.run_live_model_smoke
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

Authentication defaults are:

```text
SESSION_TTL_DAYS=180
AUTH_COOKIE_SECURE=false
AUTH_COOKIE_NAME=yoko_session
```

Production HTTPS must use `AUTH_COOKIE_SECURE=true` and the
`__Host-yoko_session` cookie name.

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

账号认证已在接口合同 `0.4.0` 中启用。注册和登录使用 V3 SQLite 数据结构签发
固定 180 天的 HttpOnly Session Cookie。聊天、反馈、提醒、记忆和指标接口都要求
有效 Session，资源归属由后端确定；前端过渡期间多传的 `user_id` 会被忽略。
所有写请求还必须来自配置的前端 Origin 或 API 同源页面。

`GET /api/health` 用于进程存活检查，`GET /api/ready` 检查数据库连接和迁移版本。
聊天客户端可以发送 `Idempotency-Key` 请求头；重试同一请求时必须复用原值。

提醒创建采用模型语义门禁：Agent 先结合当前消息、历史和最多 3 条候选记忆判断
完整意图，只有模型明确调用工具后才写入。`preferred_time` 可以补全缺失钟点，但
关键词、正则和固定错别字替换不会直接创建提醒；聊天中的长期偏好候选也由同一次
模型调用进行语义提取，响应仍区分检索到与实际使用的记忆。

Agent 内部提供提醒查询、创建、修改和删除工具。核对、修改或删除前会先读取真实
提醒状态；只读查询不出现在公共 `tool_calls` 中。创建和改时间还会校验明确钟点或
实际使用的时间记忆，并核对落库后的本地钟点与用户原话一致，不能把“早上”“晚上”
等范围自行换成 8 点。每周提醒必须明确星期几，不能自行猜成当天或周日。

提醒写操作采用双层安全保护：消息要求绕过规则，或模型同一轮提出多个创建、修改、删除时，
都会在工具执行前整批拦截并要求用户重新逐条确认；单个工具还必须提交可核对的用户操作原话。用户最终撤销、
否定操作，或要求一次性提醒却试图覆盖周期提醒时，工具层会拒绝写入。该策略不改变
REST API 字段，但一句话批量改动会返回 `needs_clarification`。

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

## 前端

```powershell
Set-Location .\frontend
npm.cmd run dev
```

前端地址：<http://127.0.0.1:5173>

## 环境变量

本地 `.env` 文件由 `.env.example` 创建，模型凭据默认为空。需要调用模型时，
请填写 `MODEL_NAME`、`OPENAI_API_KEY` 和 `OPENAI_BASE_URL`。不要提交 `.env`。

认证配置默认值：

```text
SESSION_TTL_DAYS=180
AUTH_COOKIE_SECURE=false
AUTH_COOKIE_NAME=yoko_session
```

生产 HTTPS 环境必须使用 `AUTH_COOKIE_SECURE=true` 和
`__Host-yoko_session` Cookie 名称。
