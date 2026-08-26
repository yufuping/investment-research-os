# Bigfish 结构化投资记忆层

本模块是新架构 Phase 1 的开发基础，与 Legacy SQLite 数据库并存，不会读取、修改或迁移现有 `database/investment.db`。

## 数据表

| 表 | 用途 |
|---|---|
| `companies` | 公司主记录 |
| `research_sessions` | 一次研究的目标、路由和证据摘要 |
| `theses` | 可追溯、可链接前一版本的投资论点 |
| `assumptions` | 高影响假设、证据和置信度 |
| `predictions` | 可证伪预测及后续验证结果 |
| `valuations` | 当时的价格、要求回报和情景假设 |
| `critical_unknowns` | 高影响但尚未解决的问题 |
| `watch_variables` | 决定公司论点的少量跟踪变量 |
| `decisions` | 经用户明确确认的真实投资决策 |
| `research_updates` | 新事实及其对假设、论点和估值的影响 |
| `skill_improvements` | 尚待 Codex 和用户审批的方法改进候选 |

## 安全边界

- 开发和生产必须使用不同的 Neon 分支或项目。
- 连接串只通过 `BIGFISH_DATABASE_URL` 提供，不写入代码或 Git。
- Alembic 没有默认数据库地址；未设置环境变量时迁移会停止。
- 应用启动不会自动对生产数据库执行 `create_all`。
- 真实决策必须通过仓库的明确确认检查；普通研究讨论不能写成交易。
- 论点按版本追加，保留旧内容并通过 `supersedes_thesis_id` 形成历史链。

## 本地验证

自动测试主要使用 SQLite 内存数据库验证跨数据库兼容性。主程序在没有配置 Neon URL 时，会把正式开发记忆持久化到独立的 `database/bigfish.db`，不会写入旧的 `database/investment.db`：

```bash
python -m pytest tests/test_knowledge_models.py -q
```

## 当前可调用的记忆能力

`KnowledgeRepository` 负责数据库读写，`KnowledgeService` 将结果转换成适合未来 MCP/HTTP 接口使用的 JSON：

- 按股票代码读取公司完整记忆；
- 跨论点、假设、预测、关键未知和跟踪变量搜索；
- 追加论点并保留版本历史；
- 保存假设、可证伪预测和关键未知；
- 新建或更新同名跟踪变量；
- 只有用户明确确认后才能保存真实投资决策。

这一层没有连接生产数据库。当前 MCP 服务已经提供：

- `get_company_memory`、`search_memory` 两个只读工具；
- `save_thesis`、`save_assumption`、`save_prediction`、`save_critical_unknown`、`save_watch_variable` 五个研究记忆写入工具。
- `calculate_cagr`、`calculate_required_profit_growth`、`valuation_scenario_analysis` 三个确定性计算工具。
- `save_valuation`、`get_valuation_history` 两个估值记忆工具；保存采用追加快照，不覆盖历史。

买卖决策写入尚未向 MCP 开放，避免把普通研究讨论误记成真实交易。

反向估值默认使用五年和13%要求年化回报率。股息率按年化回报贡献处理，属于简化模型；存在可靠逐年分红预测时，应改用逐年现金流计算。

估值接口输入的回报率使用普通百分数，例如 `13` 表示13%；数据库内部统一保存为 `0.13`。每条记录可保存当时使用的利润增长、利润率、期末P/E和其他关键假设，读取时会比较最近两次快照。

`save_valuation` 还要求显式传入 `confirm_save=true`，并写入 `recorded_via=investment_research_os_mcp` 来源标记。如果正式接口不可用，调用方必须停止并报告，不能通过其他应用、终端或直接数据库访问绕过。

## 将来的开发环境迁移

安装依赖并设置专用开发连接串后：

```bash
export BIGFISH_DATABASE_URL='postgresql+psycopg://...开发分支...'
alembic upgrade head
```

执行迁移前必须再次确认连接目标是 development，不是 production。当前阶段尚未要求配置或运行真实 Neon 迁移。
