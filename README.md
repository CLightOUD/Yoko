# Yoko：具备反馈记忆能力的适老陪伴 Agent

Yoko（YOur Kins Online）是一个面向老年人的轻量 Agent 系统。它以“反馈记忆”为核心：理解用户的任务与自然语言表达，规划并调用提醒、联网查询等工具；当用户明确表达长期偏好、补充个人事实或修正结果后，系统会沉淀可管理的记忆，并在后续相似任务中自动检索和使用。

本项目对应的真实场景是适老陪伴与生活提醒。老年用户可以用口语、错别字和多轮补充表达需求，Yoko 负责澄清关键歧义、创建或修改提醒，并逐渐记住回答风格、常用提醒时间、提前量和人物关系等信息。

## 赛题对应关系

| 赛题要求 | Yoko 的实现 |
| --- | --- |
| 基础 Agent 流程 | 语义预处理、任务规划、工具调用、结果生成和事务提交 |
| 从反馈持续改进 | 聊天中的明确长期偏好和 `/api/feedback` 修正均可生成记忆 |
| 自动检索相关记忆 | 每轮聊天从当前用户的有效记忆中构造最多 10 条候选，再由模型选择实际使用项 |
| 在结果中体现记忆 | 使用过的记忆 ID 会进入 `used_memory_ids`，影响回复风格或提醒参数，并在响应中标记 `used=true` |
| 真实应用场景 | 适老陪伴、服药/散步/预约提醒、联网查资料、图片理解 |
| 记忆成本 | 单独记录 `memory_tokens`、检索耗时、检索数量和实际使用数量 |
| 对话速度 | 记录模型、工具、检索和总耗时；限制历史、候选记忆和并发数量 |
| 记忆效果 | 返回检索记忆、实际使用记忆与记忆变更，可通过指标接口和真实模型评测核对 |

## 核心闭环

```text
用户输入
  -> 读取最近对话和最多 10 条候选记忆
  -> 结构化语义预处理（意图、歧义、撤销、安全、联网需求）
  -> 主 Agent 规划并调用工具
  -> 生成回复和结构化记忆候选
  -> 校验记忆是否有用户原文依据
  -> 在同一 SQLite 事务中提交提醒、记忆、消息、指标和幂等响应
  -> 后续相似任务自动检索并使用相关记忆
```

系统坚持三个原则：

1. 用户原文是事实来源，关键词本身不能直接触发提醒写入。
2. “检索到”不等于“使用过”，只有实际影响回复或工具参数的记忆才会标记为已使用。
3. 临时要求、否定表达、无明确长期意义的评分不会被强行保存。

## 记忆设计

### 记忆类型

- 全局记忆：回答风格、默认语言等跨任务偏好。
- 任务记忆：服药、散步、预约等场景的常用时间或提前量。
- 其他事实：用户明确要求记住的人物关系、称呼和普通个人事实。

每条记忆包含作用域、任务类型、键、值、展示文本、来源消息、启用状态、创建/更新时间和最后使用时间。用户可以在网页中停用、重新启用、修改或永久删除记忆。

### 记忆产生

记忆有两个入口：

1. 聊天入口：主 Agent 从明确的长期表达中生成结构化候选，例如“记住，以后回答简洁一点”。候选必须能被近期用户原文支持。
2. 反馈入口：用户对某次回答提交文字反馈或修正结果。明确长期偏好由确定性提取器处理，不额外调用模型；重复反馈通过摘要键去重。

### 记忆检索与使用

每轮只读取当前账号的有效记忆，并将候选池限制为最多 10 条。候选池会保留任务多样性，并优先保留当前输入中明确提及人物的相关事实。主 Agent 只能返回真正影响本轮结果的记忆 ID；系统再校验 ID 是否来自本轮候选池。

这一设计不依赖向量数据库，适合黑客松规模和单用户少量偏好：部署简单、检索时间稳定、没有额外嵌入费用。数据规模扩大后，可将候选检索替换为 SQLite FTS 或向量检索，而不改变 API。

## 真实使用示例

```text
用户：记住，我以后散步一般都在晚上七点。
Yoko：已记住散步提醒时间偏好为 19:00。

几天后
用户：提醒我明天去散步。
Yoko：检索到散步时间偏好，并按明天 19:00 准备提醒。

用户：以后回复短一点，这次说得太长了。
Yoko：保存“回答风格偏好为简短清晰”，后续回答自动采用更简洁的表达。
```

当日期、星期、上午/下午等关键信息仍有歧义时，系统会优先澄清，不会为了体现记忆而猜测。

## Agent 与工具

- 提醒工具：查询、创建、修改、删除提醒；支持单次、每日和每周周期。
- 联网查询：通过博查 Web Search API 获取结构化网页结果和摘要，再经过相关性与证据门禁。
- 图片理解：独立视觉模型提取图片观察，再由主 Agent 结合用户文字处理；图片中的指令不视为用户授权。
- Web Push：可选的到期提醒推送，支持浏览器订阅、失效端点停用和重试。

提醒写操作采用延迟提交：Agent 先形成计划，系统校验用户证据、时间、操作数量和当前数据库状态，最后才在事务中落库。相同聊天请求使用 `Idempotency-Key` 去重，避免网络重试造成重复提醒。

## 成本、速度与效果指标

每次聊天响应包含：

- `model_call_count`
- `input_tokens` / `output_tokens`
- `memory_tokens`
- `retrieved_memory_count` / `used_memory_count`
- `retrieval_ms` / `model_ms` / `tool_ms` / `total_ms`

`GET /api/metrics/summary` 可按时间范围汇总请求数、模型调用数、Token、记忆 Token、平均检索耗时、平均模型耗时和记忆命中情况。

为了控制成本和延迟，当前实现限制最近对话长度、记忆候选数量、搜索结果与重试次数、单实例并发聊天数和账号请求频率。

## 项目结构

```text
Yoko/
├── backend/
│   ├── app/
│   │   ├── agent/          # 语义预处理、Agent、工具与记忆决策
│   │   ├── api/            # FastAPI 路由
│   │   ├── repositories/   # SQLite 数据访问
│   │   ├── schemas/        # Pydantic 输入输出模型
│   │   └── services/       # 聊天、反馈、记忆、提醒、搜索等服务
│   └── tests/              # 单元、接口和真实模型评测
├── frontend/               # React + Vite 适老网页
├── TECH_STACK.md           # 技术栈与选择依据
├── ENVIRONMENT.md          # 环境与变量配置
├── RUN_DEPLOY.md           # 本地运行与验证
├── requirements.txt
└── entrypoint.sh
```

## 快速开始

推荐环境：Windows 10/11、Python 3.11、Node.js LTS、npm。

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
npm.cmd --prefix frontend ci
```

填写 `.env` 中的模型名称、API Key 和兼容 OpenAI 的 Base URL，然后分别启动：

```powershell
# 终端 1：仓库根目录
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000

# 终端 2：仓库根目录
npm.cmd --prefix frontend run dev
```

访问：

- 网页：<http://127.0.0.1:5173>
- API 文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/api/health>
- 就绪检查：<http://127.0.0.1:8000/api/ready>

接口结构以 Pydantic 模型和 FastAPI 自动生成的 `/openapi.json` 为准。

完整配置见 [ENVIRONMENT.md](ENVIRONMENT.md)，运行与测试方式见 [RUN_DEPLOY.md](RUN_DEPLOY.md)。

## 测试

```powershell
python -m pytest backend\tests -q
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run build
```

配置真实模型后，可运行使用临时数据库的冒烟测试：

```powershell
python -m backend.tests.evaluation.run_live_model_smoke
python -m backend.tests.evaluation.run_live_web_search_smoke
```

高难度对话和攻击评测会产生真实模型费用，仅在确认预算后运行：

```powershell
python -m backend.tests.evaluation.run_live_stress_evaluation
python -m backend.tests.evaluation.run_live_dialogue_evaluation
python -m backend.tests.evaluation.run_live_adversarial_evaluation
```

## 文档

- [技术栈与选型](TECH_STACK.md)
- [环境配置](ENVIRONMENT.md)
- [运行与测试](RUN_DEPLOY.md)

## 当前边界

- 当前部署目标是单实例 FastAPI + SQLite，不支持多个应用实例同时写同一数据库。
- 联网查询依赖博查 API 的额度和可用性；接口失败或证据不足时，系统会拒绝编造答案。
- 记忆检索面向轻量规模设计；记忆数量很大时应升级全文或向量检索。
- 本项目提供生活辅助，不替代医生诊断、紧急服务或专业医疗建议。
