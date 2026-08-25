# Yoko Sealos DevBox 部署指南

更新时间：2026-08-23

适用项目：Yoko 适老陪伴与提醒 Agent

部署目标：使用 Sealos DevBox 从 GitHub 获取、构建和验证代码，发布为 OCI 镜像，再通过 Sealos 应用管理以单实例方式长期运行。前端和后端使用同一个 HTTPS 地址，SQLite 保存到持久卷。

## 1. 最终架构

```text
用户浏览器
    |
    | HTTPS
    v
Sealos 自动生成的 HTTPS 地址
    |
    v
Yoko 单容器、单实例
    ├── /              React 静态文件
    ├── /api/*         FastAPI 接口
    └── /api/ready     就绪检查
            |
            v
        /data/app.db   SQLite 持久卷
```

部署后只保留一个公开地址，例如：

```text
https://yoko-xxxxx.sealos.app/
```

实际域名以后续 Sealos 控制台分配结果为准。

## 2. DevBox、镜像和应用管理的职责

| 组件 | 用途 | 是否长期运行 |
| --- | --- | --- |
| GitHub 仓库 | 保存代码和版本历史 | 是 |
| DevBox | 拉取、构建、测试和发布代码 | 否，发布后暂停 |
| OCI 镜像 | 保存一次可部署版本 | 是 |
| 应用管理 | 运行正式应用 | 是 |
| 持久卷 | 保存 SQLite 数据 | 是 |

DevBox 是开发和构建环境，不作为正式服务器使用。正式访问地址由应用管理提供。

## 3. 当前部署前置状态

开始部署前必须确认：

- 账号注册、登录、退出和 Session 已合入 `main`。
- 后端完整测试通过。
- 前端 lint 和生产构建通过。
- `main` 没有未解决的合并冲突。
- `.env`、数据库和真实密钥没有提交。
- `API_SPEC.md` 与最终接口一致。
- 已选择云端可以访问的模型服务。

当前仓库还需要补齐以下部署能力：

1. FastAPI 提供 `frontend/dist` 静态文件。
2. 前端生产环境使用同源 `/api`。
3. 仓库根目录增加 `entrypoint.sh`。
4. 数据库路径支持 `/data/app.db`。
5. 账号功能完成后增加生产 Cookie 环境变量。

以上事项应在本地或 DevBox 中完成并通过测试后再发布。

## 4. 部署前代码改造

### 4.1 前端生产环境使用同源 API

当前前端默认访问：

```text
http://127.0.0.1:8000
```

生产环境不能继续使用该地址。建议在 `frontend/src/api/client.js` 中区分开发和生产：

```javascript
const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  (import.meta.env.DEV ? 'http://127.0.0.1:8000' : '')
```

生产构建时不设置 `VITE_API_BASE_URL`，请求将使用当前 HTTPS 站点下的 `/api/*`。

账号功能完成后，所有需要 Session 的请求还必须包含：

```javascript
credentials: 'include'
```

### 4.2 FastAPI 提供前端构建结果

在所有 API 路由注册完成后，判断 `frontend/dist` 是否存在，并最后挂载静态目录。

参考实现：

```python
from pathlib import Path

from fastapi.staticfiles import StaticFiles


frontend_dist = Path("frontend/dist")
if frontend_dist.is_dir():
    application.mount(
        "/",
        StaticFiles(directory=frontend_dist, html=True),
        name="frontend",
    )
```

要求：

- 静态挂载必须放在 API 路由之后。
- 本地没有 `frontend/dist` 时，后端仍能单独启动。
- `/api/health`、`/api/ready` 和 `/docs` 不能被静态页面覆盖。
- 修改后增加测试，确认 API 路由仍然优先匹配。

当前前端没有 React Router 路径，因此 `StaticFiles(html=True)` 足以覆盖当前页面。以后增加前端路由时再补 SPA fallback。

### 4.3 增加生产启动文件

在仓库根目录创建 `entrypoint.sh`：

```bash
#!/bin/bash
set -e

exec python -m uvicorn backend.app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}"
```

要求：

- 文件使用 LF 换行，不能使用 Windows CRLF。
- 文件需要可执行权限。
- 启动文件只启动应用，不安装依赖、不构建前端。
- Uvicorn 必须监听 `0.0.0.0`。
- 不使用 `--reload`。

在 Git 中记录可执行权限：

```bash
git update-index --chmod=+x entrypoint.sh
```

### 4.4 数据库路径

生产环境统一配置：

```text
DATABASE_PATH=/data/app.db
```

`/data` 必须由 Sealos 持久卷提供。不要把数据库保存在 `/app`、仓库目录或容器临时文件系统中。

### 4.5 更新环境变量样例

账号功能完成后，`.env.example` 至少应包含：

```text
SESSION_TTL_DAYS=180
AUTH_COOKIE_SECURE=false
AUTH_COOKIE_NAME=yoko_session
```

`.env.example` 只写无敏感信息的示例值，不能写模型密钥或测试账号真实密码。

## 5. 本地发布前验证

在仓库根目录执行后端测试：

```powershell
python -m pytest backend\tests -q
```

构建前端：

```powershell
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run build
```

生产模式本地启动：

```powershell
$env:DATABASE_PATH = "backend/data/deploy-test.db"
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

验证：

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/api/health
http://127.0.0.1:8000/api/ready
http://127.0.0.1:8000/docs
```

检查浏览器 Network：前端请求应发往当前站点的 `/api/*`，不能再访问前端用户电脑上的 `127.0.0.1:8000`。

验证结束后关闭服务。测试数据库属于本地运行数据，不提交。

## 6. 创建 Sealos DevBox

### 6.1 创建工作空间

1. 注册并登录 Sealos。
2. 创建独立工作空间，例如 `yoko-demo`。
3. 选择广东或北京可用区。
4. 为工作空间设置合理余额和资源配额。

不要与其他不相关项目共用工作空间，方便查看账单和删除资源。

### 6.2 创建 DevBox

建议配置：

```text
名称：yoko-build
运行环境：Python 3.11
CPU：2 核
内存：4 GB
公网端口：8000
附加调试端口：5173，可选
```

DevBox 只在构建和测试期间运行。发布成功后应暂停。

### 6.3 检查运行时

进入 DevBox 终端：

```bash
python --version
node --version
npm --version
git --version
```

要求：

```text
Python：3.11.x
Node.js：受 Vite 8 支持的 LTS 版本，推荐 24.x
npm：能够读取 package-lock.json
```

如果 Node.js 缺失或版本过低，先通过 DevBox 的运行时管理或终端升级，然后重新执行版本检查。不要在版本不满足要求时继续安装前端依赖。

## 7. 在 DevBox 导入项目

### 7.1 拉取代码

公开仓库：

```bash
git clone https://github.com/CLightOUD/Yoko.git
cd Yoko
git status
git log -1 --oneline
```

如果仓库是私有的，使用 GitHub 授权或只读 Token。不要把 Token 写入仓库文件或命令脚本。

### 7.2 安装 Python 依赖

优先使用锁定文件：

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements-lock.txt
python -m pip check
```

账号系统合入后，锁定文件必须已经包含密码哈希依赖。

### 7.3 安装前端依赖并构建

```bash
cd frontend
npm ci
npm run lint
npm run build
cd ..
```

确认构建结果存在：

```bash
test -f frontend/dist/index.html
```

`frontend/dist` 被 Git 忽略是正常的，但发布 OCI 版本时必须包含已经构建好的目录。

### 7.4 运行后端测试

```bash
python -m pytest backend/tests -q
```

测试数量可能因账号功能增加而上升。以全部通过为标准，不固定要求仍为原来的 132 项。

### 7.5 配置 DevBox 测试变量

通过 DevBox 环境变量界面设置，不创建含真实密钥的 `.env`：

```text
APP_ENV=development
APP_HOST=0.0.0.0
APP_PORT=8000
APP_TIMEZONE=Asia/Shanghai
DATABASE_PATH=/tmp/yoko-devbox.db
MODEL_PROVIDER=openai
MODEL_NAME=实际模型
OPENAI_API_KEY=实际密钥
OPENAI_BASE_URL=实际地址
FRONTEND_ORIGIN=DevBox 预览地址
AUTH_COOKIE_SECURE=true
AUTH_COOKIE_NAME=__Host-yoko_session
SESSION_TTL_DAYS=180
LANGSMITH_TRACING=false
LOG_LEVEL=INFO
```

DevBox 预览使用 HTTPS 时，Cookie 可以设置 `Secure=true`。如果实际预览环境或账号实现有不同要求，以浏览器 Cookie 检查结果为准。

### 7.6 启动预览

```bash
chmod +x entrypoint.sh
./entrypoint.sh
```

打开 DevBox 提供的 8000 端口外网地址，依次检查：

1. 首页可以打开。
2. `/api/ready` 返回 `status=ok`。
3. 注册和登录可用。
4. Agent 可以调用真实模型。
5. 提醒、记忆、反馈和指标页面可用。
6. 日志中没有密钥、密码和 Session Token。

不要把 DevBox 的 `/tmp/yoko-devbox.db` 当作正式数据。

## 8. 发布 OCI 版本

### 8.1 发布前清理

执行：

```bash
git status --short
find . -name ".env" -o -name "*.db" -o -name "*.db-wal" -o -name "*.db-shm"
```

确认发布内容不包含：

- `.env`。
- 模型密钥。
- GitHub Token。
- 测试账号真实密码。
- 本地或 DevBox 测试数据库。
- 私人聊天记录和日志。

不要删除 `frontend/dist`，它是正式前端构建结果。

### 8.2 记录发布版本

获取当前提交：

```bash
git rev-parse --short HEAD
```

建议版本名：

```text
demo-<提交号>
```

例如：

```text
demo-a1b2c3d
```

不要使用无法追溯内容的 `latest` 作为唯一版本。

### 8.3 在 DevBox 发布

1. 打开 DevBox 项目详情。
2. 进入“版本历史”。
3. 点击“发布版本”。
4. 输入版本名和说明。
5. 确认入口文件为仓库根目录的 `entrypoint.sh`。
6. 等待 OCI 镜像构建完成。
7. 记录生成的镜像版本和当前 Git 提交号。

发布失败时先查看构建日志，不要反复创建同名版本覆盖问题。

## 9. 部署到应用管理

### 9.1 创建正式应用

进入 Sealos“应用管理”，创建应用：

```text
应用名称：yoko
镜像：DevBox 刚发布的 demo-<提交号>
部署模式：固定实例
实例数量：1
CPU：1 核
内存：1 GB
容器端口：8000
公网访问：https
```

如果模型初始化或依赖导致内存不足，可提升到 `2 GB`。不要通过增加实例数解决 SQLite 问题。

### 9.2 配置持久卷

添加存储卷：

```text
容量：至少 1 GB
挂载路径：/data
访问应用：yoko
```

设置：

```text
DATABASE_PATH=/data/app.db
```

必须保持一个实例。SQLite 不适合多个应用副本同时写入同一个数据库文件。

### 9.3 配置生产环境变量

```text
APP_ENV=production
APP_HOST=0.0.0.0
APP_PORT=8000
APP_TIMEZONE=Asia/Shanghai
PORT=8000

DATABASE_PATH=/data/app.db

MODEL_PROVIDER=openai
MODEL_NAME=实际模型
OPENAI_API_KEY=实际密钥
OPENAI_BASE_URL=实际地址

FRONTEND_ORIGIN=https://Sealos 分配的正式地址
AUTH_COOKIE_SECURE=true
AUTH_COOKIE_NAME=__Host-yoko_session
SESSION_TTL_DAYS=180

LANGSMITH_TRACING=false
LOG_LEVEL=INFO
```

账号功能最终变量名以合入后的 `.env.example` 为准。不要在变量名不一致时自行猜测。

### 9.4 配置健康检查

```text
协议：HTTP
端口：8000
路径：/api/ready
成功状态：200
初始延迟：建议 10～30 秒
周期：建议 30 秒
```

`/api/health` 只检查进程；`/api/ready` 还检查数据库和迁移，更适合部署就绪检查。

### 9.5 第一次发布

1. 创建应用并等待实例变为运行状态。
2. 打开日志，确认数据库迁移成功。
3. 复制 Sealos 分配的正式 HTTPS 地址。
4. 如果此前不知道正式地址，更新 `FRONTEND_ORIGIN` 后重新部署。
5. 打开 `/api/ready`，确认数据库状态正常。
6. 打开首页，确认静态文件和 API 使用同一个来源。

## 10. 上线后验收

### 10.1 基础验收

```text
GET /api/health  → 200
GET /api/ready   → 200
GET /             → React 页面
GET /docs         → FastAPI 文档
```

### 10.2 账号验收

1. 注册账号 A，确认自动登录。
2. 刷新页面，确认登录状态保留。
3. 退出账号 A，确认业务接口变为未登录状态。
4. 注册账号 B，确认看不到账号 A 的任何数据。
5. 登录账号 A，确认只能看到账号 A 的数据。
6. 检查 Cookie：必须具有 `HttpOnly`、`Secure`、`SameSite=Lax` 和 `Path=/`。
7. 浏览器 JavaScript 不应能够读取 Session Cookie。

### 10.3 业务验收

1. 对话写入长期偏好。
2. 后续任务自动检索并正确使用偏好。
3. 创建一次性、每日和每周提醒。
4. 修改、删除和确认提醒。
5. 提交反馈并检查记忆变化。
6. 查看指标中的耗时和 Token。
7. 测试模糊时间、错别字和最终撤销。

### 10.4 持久化验收

1. 创建测试账号、提醒和记忆。
2. 在 Sealos 控制台重启应用实例。
3. 等待 `/api/ready` 恢复。
4. 重新登录。
5. 确认账号、提醒和记忆仍然存在。

如果重启后数据消失，立即检查 `DATABASE_PATH` 和 `/data` 持久卷，不继续录入数据。

### 10.5 模型网络验收

在云端执行一次最小真实模型请求，检查：

- 模型域名可以从所选国内区域访问。
- API Key 有效。
- Base URL 正确。
- 请求没有被供应商 IP 白名单拒绝。
- 响应时间能够接受。

只运行必要用例，避免在排障时反复消耗模型费用。

## 11. 数据备份

### 11.1 首次账号迁移前备份

账号系统数据库迁移前，必须备份现有 `/data/app.db`。如果正式数据库尚未创建，可以跳过。

### 11.2 在线备份命令

进入正式应用终端，使用 Python 的 SQLite backup API：

```bash
python - <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

source_path = Path('/data/app.db')
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
target_path = Path(f'/data/app-{stamp}.bak')

with sqlite3.connect(source_path) as source:
    with sqlite3.connect(target_path) as target:
        source.backup(target)

print(target_path)
PY
```

备份后检查文件存在且大小大于 0。重要演示前应将备份下载到安全位置，不能只保留在同一持久卷中。

## 12. 更新发布流程

每次更新按以下顺序：

1. 三人完成代码并依次推送 `main`。
2. 队长确认远端 `main` 的提交号。
3. DevBox 执行 `git pull --ff-only`。
4. 安装更新后的依赖。
5. 运行后端完整测试。
6. 运行前端 lint 和生产构建。
7. 在 DevBox 预览地址完成冒烟测试。
8. 数据库迁移前备份正式数据库。
9. 发布新的 `demo-<提交号>` OCI 版本。
10. 应用管理切换到新版本。
11. 检查 `/api/ready`、注册登录、Agent 和记忆提醒。
12. 稳定后暂停 DevBox。

不要在正式应用容器里执行 `git pull` 或直接编辑代码。正式应用只运行已发布版本。

## 13. 回滚规则

### 13.1 没有数据库迁移

如果新版本只修改前端、Prompt 或普通业务代码，可以在应用管理中切换回前一个 OCI 版本。

### 13.2 包含数据库迁移

当前数据库会拒绝低版本应用读取更高版本 Schema。包含数据库迁移时，不能只回滚代码。

正确顺序：

1. 停止正式应用写入。
2. 保存当前故障数据库副本。
3. 恢复迁移前数据库备份。
4. 切换到旧 OCI 版本。
5. 启动并检查 `/api/ready`。

不要修改已经发布过的迁移内容。修复迁移只能新增更高版本迁移。

## 14. 常见问题排查

### 14.1 首页返回 404

检查：

```bash
ls -la frontend/dist
test -f frontend/dist/index.html
```

确认前端已构建，且 FastAPI 在 API 路由之后挂载静态目录。

### 14.2 前端请求 127.0.0.1

原因：生产构建仍写入了本地 API 地址。

处理：检查 `VITE_API_BASE_URL` 和 `frontend/src/api/client.js`，重新构建并发布 OCI 版本。

### 14.3 Sealos 显示 Connection Refused

检查：

- Uvicorn 是否监听 `0.0.0.0`。
- 应用端口是否为 `8000`。
- `entrypoint.sh` 是否有执行权限。
- 日志中是否存在依赖或环境变量错误。

### 14.4 重启后账号和提醒消失

检查：

```text
DATABASE_PATH=/data/app.db
持久卷挂载路径=/data
实例数量=1
```

容器内其他目录的数据不保证持久化。

### 14.5 登录后仍然返回 401

检查：

- 请求是否带 `credentials: 'include'`。
- Cookie 是否成功写入。
- `Secure=true` 时页面是否使用 HTTPS。
- `FRONTEND_ORIGIN` 是否与实际地址完全一致。
- Cookie 名、`Path=/` 和 `SameSite` 是否符合后端实现。
- `/api/auth/me` 是否能够读取当前 Session。

### 14.6 Cookie 无法设置

`__Host-` 前缀 Cookie 必须满足：

```text
Secure=true
Path=/
不设置 Domain
```

本地 HTTP 开发使用不带 `__Host-` 前缀的 `yoko_session`。

### 14.7 模型返回 502

检查：

- `MODEL_NAME`。
- `OPENAI_API_KEY`。
- `OPENAI_BASE_URL`。
- 云端到模型服务的网络连通性。
- 模型供应商是否要求 IP 白名单。

不要把底层错误或完整密钥发到群聊和公开 Issue。

### 14.8 应用频繁重启

优先查看日志和事件：

- 内存不足时从 `1 GB` 调整为 `2 GB`。
- 启动超时时增加健康检查初始延迟。
- 数据库迁移失败时停止反复重启，先恢复备份并检查 Schema。
- 不通过增加实例数解决内存或 SQLite 问题。

## 15. 费用控制

- DevBox 构建完成后立即暂停。
- 正式应用保持一个实例。
- 初始资源使用 `1 CPU / 1 GB`，确认不足后再增加。
- 持久卷初始使用 `1 GB`。
- 在 Sealos 账单中按工作空间查看 CPU、内存、存储和流量。
- 删除不用的旧 DevBox 和预览应用。
- 不删除正式持久卷，除非已经下载并验证备份。

按 Sealos 北京区公开单价估算，`1 CPU + 1 GB 内存 + 1 GB 存储` 持续运行约 19 元/月，不包含公网端口和流量，实际费用以控制台为准。

## 16. 安全检查

- `.env` 未进入 Git 和 OCI 镜像。
- 数据库和备份未进入 Git。
- 模型密钥只存在于 Sealos 环境变量。
- 密码只保存 Argon2id 哈希。
- 数据库只保存 Session Token 哈希。
- 生产 Cookie 启用 `HttpOnly`、`Secure` 和 `SameSite=Lax`。
- 所有业务 API 从 Session 获取用户 ID。
- 两个账号之间的数据完全隔离。
- 日志不记录密码、Session、模型密钥或完整请求正文。
- 正式环境只开放 HTTPS 地址。

## 17. 最终检查清单

```text
[ ] main 已同步并冻结
[ ] 后端完整测试通过
[ ] 前端 lint 通过
[ ] 前端生产构建通过
[ ] frontend/dist 已生成
[ ] entrypoint.sh 可执行
[ ] FastAPI 可以提供前端页面
[ ] 前端使用同源 /api
[ ] DevBox 预览通过
[ ] OCI 版本包含 Git 提交号
[ ] 正式应用固定单实例
[ ] /data 持久卷已挂载
[ ] DATABASE_PATH=/data/app.db
[ ] 生产环境变量已配置
[ ] Sealos HTTPS 地址可以访问
[ ] /api/ready 返回 200
[ ] 注册、登录、退出通过
[ ] 两账号数据隔离通过
[ ] Agent 真实模型调用通过
[ ] 提醒、记忆、反馈和指标通过
[ ] 应用重启后数据仍存在
[ ] Cookie 安全属性正确
[ ] 正式数据库备份已完成
[ ] DevBox 已暂停
```

## 18. 官方参考

- [Sealos DevBox 使用指南](https://sealos.run/en/docs/guides/devbox)
- [Sealos 导入代码仓库](https://sealos.run/en/docs/guides/devbox/code-server)
- [Sealos 应用启动配置](https://sealos.run/docs/guides/devbox/entrypoint-sh)
- [Sealos 应用管理](https://sealos.run/docs/guides/app-management)
- [Sealos 部署 Docker 镜像](https://sealos.run/en/docs/getting-started/deploy-docker-image)
- [Sealos 计价标准](https://sealos.run/en/docs/billing)
