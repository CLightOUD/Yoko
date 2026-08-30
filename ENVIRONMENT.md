# Yoko 环境与配置说明

## 1. 必要软件

- Windows 10/11；云端使用 Linux。
- Python 3.11 64 位。
- Node.js 当前受支持的 LTS 版本，推荐 Node.js 24 LTS。
- npm 和 Git。

Python 3.14 不作为当前定稿环境。部分三方库可能尚未完整支持，比赛期间不建议承担升级风险。

```powershell
git --version
python --version
python -m pip --version
node --version
npm.cmd --version
```

## 2. Python 与前端依赖

使用已有 Python 3.11 环境，或新建虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
npm.cmd --prefix frontend ci
```

严格复现当前版本时使用：

```powershell
python -m pip install -r requirements-lock.txt
```

确认解释器与依赖：

```powershell
python -c "import sys; print(sys.executable)"
python -m pip check
```

PowerShell 若禁止执行 `npm.ps1`，使用 `npm.cmd`，不需要修改系统执行策略。

## 3. 创建配置

```powershell
Copy-Item .env.example .env
```

`.env` 已被 Git 忽略，不能提交。只测试健康检查、账号和普通提醒接口时，空模型凭据也能启动；使用聊天 Agent 至少填写：

```dotenv
MODEL_NAME=<模型名称>
OPENAI_API_KEY=<模型服务密钥>
OPENAI_BASE_URL=<OpenAI兼容接口地址>
```

`MODEL_PROVIDER=openai` 表示使用 OpenAI 兼容协议，不代表必须使用 OpenAI 官方模型。

## 4. 环境变量

### 应用与数据库

| 变量 | 开发默认值 | 说明 |
| --- | --- | --- |
| `APP_ENV` | `development` | 运行环境标识 |
| `APP_HOST` | `127.0.0.1` | 云端设置 `0.0.0.0` |
| `APP_PORT` | `8000` | 平台提供 `PORT` 时优先使用平台端口 |
| `APP_TIMEZONE` | `Asia/Shanghai` | 默认时区 |
| `DATABASE_PATH` | `backend/data/app.db` | 云端应使用持久卷路径 `/data/app.db` |
| `MAX_REQUEST_BODY_BYTES` | `8388608` | 最大请求体，默认 8 MiB |

### 模型与视觉

| 变量 | 必需 | 说明 |
| --- | --- | --- |
| `MODEL_NAME` | 聊天必需 | 主 Agent 和语义处理模型 |
| `OPENAI_API_KEY` | 聊天必需 | 主模型密钥 |
| `OPENAI_BASE_URL` | 视提供方而定 | OpenAI 兼容 Base URL |
| `VISION_MODEL_NAME` | 图片功能必需 | 支持图像输入的模型 |
| `VISION_API_KEY` | 可选 | 留空时回退到主模型 Key |
| `VISION_BASE_URL` | 可选 | 留空时回退到主模型 Base URL |

主模型名称不需要改成视觉模型。文本与图片使用独立配置，便于排错和控制费用。

### 前端与认证

| 变量 | 开发默认值 | 生产要求 |
| --- | --- | --- |
| `FRONTEND_ORIGIN` | `http://127.0.0.1:5173` | 改为正式 HTTPS 地址，不带末尾 `/` |
| `SESSION_TTL_DAYS` | `180` | 登录有效期六个月 |
| `AUTH_COOKIE_SECURE` | `false` | HTTPS 生产环境必须为 `true` |
| `AUTH_COOKIE_NAME` | `yoko_session` | 生产推荐 `__Host-yoko_session` |

### 限流与并发

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `RATE_LIMIT_ENABLED` | `true` | 进程内限流 |
| `RATE_LIMIT_GENERAL_PER_MINUTE` | `300` | 普通请求每分钟限制 |
| `RATE_LIMIT_AUTH_PER_MINUTE` | `30` | 登录注册每分钟限制 |
| `RATE_LIMIT_CHAT_PER_MINUTE` | `12` | 单账号聊天每分钟限制 |
| `RATE_LIMIT_CHAT_PER_HOUR` | `120` | 单账号聊天每小时限制 |
| `MAX_CONCURRENT_CHAT_REQUESTS` | `4` | 同时执行的聊天数 |

这些限制不支持多实例共享计数。

### 联网查询

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `WEB_SEARCH_360_ENABLED` | `true` | 360 国内备用搜索 |
| `WEB_SEARCH_DDG_ENABLED` | `true` | DuckDuckGo 备用搜索 |

必应为首轮来源，无需 API Key。免费网页搜索可能受网络、验证码和页面变化影响。

### Web Push

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PUSH_ENABLED` | `false` | 是否启动到期推送循环 |
| `PUSH_POLL_SECONDS` | `15` | 到期扫描间隔 |
| `VAPID_PUBLIC_KEY` | 空 | 浏览器订阅公钥 |
| `VAPID_PRIVATE_KEY` | 空 | 只能放在部署 Secret 中 |
| `VAPID_SUBJECT` | 示例邮箱 | 管理员联系 URI |

本地不测试 Push 时保持关闭。HTTPS 生产环境才能完整验证移动浏览器推送。

### 日志与追踪

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `LANGSMITH_TRACING` | `false` | 是否发送模型链路到 LangSmith |
| `LOG_LEVEL` | `INFO` | 应用日志级别 |

## 5. 开发配置示例

```dotenv
APP_ENV=development
APP_HOST=127.0.0.1
APP_PORT=8000
DATABASE_PATH=backend/data/app.db
FRONTEND_ORIGIN=http://127.0.0.1:5173
AUTH_COOKIE_SECURE=false
AUTH_COOKIE_NAME=yoko_session
PUSH_ENABLED=false
```

## 6. 生产配置示例

```dotenv
APP_ENV=production
APP_HOST=0.0.0.0
DATABASE_PATH=/data/app.db
FRONTEND_ORIGIN=https://<平台分配域名>
AUTH_COOKIE_SECURE=true
AUTH_COOKIE_NAME=__Host-yoko_session
PUSH_ENABLED=false
LANGSMITH_TRACING=false
LOG_LEVEL=INFO
```

模型 Key、视觉 Key 和 VAPID 私钥通过云平台 Secret 注入，不要写进镜像、启动脚本、截图或 Git。

## 7. 配置验证

启动后访问：

```text
GET /api/health
GET /api/ready
```

`/api/health` 表示进程存活；`/api/ready` 检查数据库、迁移和模型客户端配置，但不发送真实模型请求。

```powershell
python -m backend.tests.evaluation.run_live_model_smoke
```
