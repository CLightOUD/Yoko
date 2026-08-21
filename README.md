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

Run tests:

```powershell
python -m pytest backend\tests -q
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

运行后端测试：

```powershell
python -m pytest backend\tests -q
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
