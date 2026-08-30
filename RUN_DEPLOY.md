# Yoko 运行说明

本文只说明如何在本地安装、启动和验证 Yoko。环境变量的含义见 [ENVIRONMENT.md](ENVIRONMENT.md)。

## 1. 首次安装

推荐使用 Windows 10/11、Python 3.11 和 Node.js LTS。

在仓库根目录执行：

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
npm.cmd --prefix frontend ci
```

然后在 `.env` 中填写主模型配置：

```dotenv
MODEL_NAME=<模型名称>
OPENAI_API_KEY=<模型服务密钥>
OPENAI_BASE_URL=<OpenAI兼容接口地址>
```

需要测试联网查询时，还要填写 `BOCHA_API_KEY`。

只测试健康检查、账号和普通提醒接口时，可以暂时不填写模型凭据。

## 2. 开发模式运行

后端和前端需要分别启动。

在仓库根目录打开第一个 PowerShell：

```powershell
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

在仓库根目录打开第二个 PowerShell：

```powershell
npm.cmd --prefix frontend run dev
```

访问地址：

```text
网页        http://127.0.0.1:5173
API 文档   http://127.0.0.1:8000/docs
存活检查   http://127.0.0.1:8000/api/health
就绪检查   http://127.0.0.1:8000/api/ready
```

开发模式下，Vite 会把前端的 `/api` 请求代理到后端端口 `8000`。

## 3. 单进程运行

需要由后端同时提供前端页面时，先构建前端：

```powershell
npm.cmd --prefix frontend run build
```

然后在仓库根目录启动后端：

```powershell
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

访问 <http://127.0.0.1:8000/>。当 `frontend/dist/index.html` 存在时，FastAPI 会自动提供构建后的前端文件。

前端代码发生变化后必须重新执行构建命令，否则页面仍会显示上一次生成的版本。

Linux 环境也可以使用仓库根目录的启动脚本：

```bash
./entrypoint.sh
```

该脚本只负责启动后端，不会安装依赖或构建前端。

## 4. 测试

后端测试：

```powershell
python -m pytest backend\tests -q
```

前端测试、静态检查和生产构建：

```powershell
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run build
```

依赖检查：

```powershell
python -m pip check
npm.cmd --prefix frontend audit --omit=dev
```

## 5. 真实模型验证

配置 `.env` 后，可以运行真实模型冒烟测试：

```powershell
python -m backend.tests.evaluation.run_live_model_smoke
python -m backend.tests.evaluation.run_live_web_search_smoke
```

这些脚本使用临时数据库，不会修改正式数据库，但会产生模型调用费用。

高难度对话和攻击评测仅在确认预算后运行：

```powershell
python -m backend.tests.evaluation.run_live_stress_evaluation
python -m backend.tests.evaluation.run_live_dialogue_evaluation
python -m backend.tests.evaluation.run_live_adversarial_evaluation
```
