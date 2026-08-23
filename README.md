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

`GET /api/health` is the process liveness check and `GET /api/ready` verifies
the database and migration version. Chat clients may send an `Idempotency-Key`
header and must reuse it when retrying the same request.

For a reminder whose missing time can be filled unambiguously from a retrieved
`preferred_time` memory, the Agent uses a deterministic fast path and calls the
reminder service without an LLM request. This behavior reduces latency and
token cost while still reporting the retrieved and used memory.

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

`GET /api/health` 用于进程存活检查，`GET /api/ready` 检查数据库连接和迁移版本。
聊天客户端可以发送 `Idempotency-Key` 请求头；重试同一请求时必须复用原值。

当提醒请求缺少的时间可以由检索到的 `preferred_time` 记忆唯一补全时，Agent
会走确定性快速路径，直接调用提醒 Service，不产生大模型请求。响应仍会记录检索
及实际使用的记忆，从而同时降低延迟和 Token 成本。

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
