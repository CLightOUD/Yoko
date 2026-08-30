# Yoko 技术栈与选型

## 1. 选型目标

Yoko 的技术栈围绕四个目标选择：快速完成反馈记忆闭环、控制依赖与模型费用、让记忆效果可观测、支持 Windows 开发和单实例云端部署。

## 2. 总体架构

```text
React 网页
   |
   | Cookie Session + JSON API
   v
FastAPI
   ├── ChatService
   │     ├── MemoryService
   │     ├── LangChainAgent
   │     ├── ReminderService
   │     ├── WebSearchService
   │     └── MetricsService
   ├── SQLite repositories
   └── React production files
```

生产环境中，FastAPI 同时提供 `/api/*` 和 `frontend/dist`，前后端共用一个 HTTPS 域名。

## 3. 后端

| 技术 | 用途 | 选择原因 |
| --- | --- | --- |
| Python 3.11 | 后端运行时 | 生态成熟，与当前依赖兼容，Windows 和 Linux 部署稳定 |
| FastAPI | REST API、认证依赖、中间件、OpenAPI | 类型明确、开发速度快，可自动生成 `/docs` |
| Pydantic 2 | 请求、响应和模型结构化输出校验 | 统一字段合同，也可约束模型输出 |
| Uvicorn | ASGI 服务 | 轻量，适合单进程部署 |
| SQLite | 用户、会话、消息、记忆、提醒、指标 | 无独立数据库成本，适合单实例黑客松项目 |
| pwdlib + Argon2 | 密码哈希 | 不保存明文密码 |
| httpx | 模型兼容接口、搜索和网页正文请求 | 用一个 HTTP 客户端覆盖主要网络需求 |
| pywebpush | 浏览器 Web Push | 支持网页关闭后的到期提醒 |

当前没有引入 Redis、PostgreSQL、Celery、向量数据库或独立消息队列。这些组件会增加部署与合并成本，在当前规模下不会直接提高记忆效果。

## 4. Agent

| 技术 | 用途 | 选择原因 |
| --- | --- | --- |
| LangChain 1.x | 模型封装、结构化输出、Agent 与工具协议 | 避免从零实现工具调用和模型适配 |
| langchain-openai | OpenAI 兼容接口 | 可接入兼容 OpenAI 协议的模型服务 |
| LangGraph 组件 | LangChain Agent 的执行依赖 | 不额外搭建复杂工作流平台 |
| tiktoken | Token 估算 | 统计输入与记忆上下文成本 |

Yoko 没有把全部逻辑交给通用 Agent 自由执行：模型负责语义理解、规划、相关性判断和自然回复；Pydantic 负责结构边界；服务层负责权限、幂等、事务和数据归属；确定性门禁负责提醒写入、记忆依据、时间和安全校验。

这种设计比纯关键词规则更能理解口语，也比完全自由的 Agent 更容易测试。

## 5. 反馈记忆

记忆保存在 SQLite 中，每轮构造最多 10 条有任务多样性的候选，主 Agent 再判断哪些记忆实际相关。

不使用向量数据库的原因：

- 个人偏好数量较少；
- 不产生 Embedding API 费用；
- 查询和部署简单；
- 可以明确返回候选记忆与实际使用记忆，便于评测；
- 后续可替换为 FTS 或向量检索，不改变公开 API。

记忆写入保留来源消息并记录事件。用户可以停用、修改、重新启用或永久删除记忆，避免“模型记住后无法纠正”。

## 6. 前端

| 技术 | 用途 | 选择原因 |
| --- | --- | --- |
| React 19 | 聊天、提醒、记忆和账号页面 | 组件化，适合并行开发 |
| Vite 8 | 开发服务器和生产构建 | 启动、构建快，配置较少 |
| lucide-react | 操作图标 | 图标语义统一 |
| react-markdown + remark-gfm | Agent 回复 Markdown | 支持列表、链接和表格 |
| 原生 Web API | Cookie、Service Worker、Notification | 不额外引入状态管理或推送框架 |

前端采用适老设计：较大字号、清晰状态、显式确认、较少层级和可管理的记忆列表。

## 7. 联网与视觉

- 联网查询使用标准库 HTML 解析器和 httpx，不需要搜索 API Key。
- 搜索结果经过独立证据门禁；未找到可靠证据时返回 `partial`，不允许模型用旧知识伪装成实时结果。
- 图片先由独立视觉模型生成不可信观察，再由主 Agent 结合用户文字判断；图片中的提示词不能直接触发工具。

联网查询使用博查 Web Search API 返回的结构化网页结果和摘要，避免直接解析搜索引擎 HTML。
其稳定性和额度取决于外部服务，接口失败时系统不会使用无来源内容补全答案。

## 8. 测试与质量

| 工具 | 范围 |
| --- | --- |
| pytest | 服务、数据库、Agent 门禁、API、认证、提醒、记忆和搜索 |
| Node test runner | 前端提醒声音、会话历史和图片处理逻辑 |
| oxlint | 前端静态检查 |
| Vite build | 生产包验证 |
| 真实模型评测脚本 | 错别字、长对话、提示注入、联网、记忆和幂等 |

依赖范围写在 `requirements.txt`，当前可复现版本写在 `requirements-lock.txt`；前端使用 `package-lock.json` 和 `npm ci`。

## 9. 部署边界

推荐一个容器、一个应用实例和一个持久卷。若扩展为多实例，需要将 SQLite、进程内限流、聊天执行租约和 Push 调度迁移到共享数据库、Redis 或网关方案。
