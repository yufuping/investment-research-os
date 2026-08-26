# Bigfish / Investment Research OS

Bigfish 是一个单用户、私有数据优先的长期投资研究系统。

系统采用清晰的职责分工：

- **ChatGPT + Bigfish Skill：**负责公共信息研究、推理、反方验证和研报写作；
- **Investment Research OS：**只负责确定性计算、结构化记忆、正式研报保存、组合管理和备份恢复；
- **SQLite：**保存本地投资记忆和组合数据；当前阶段不需要云数据库；
- **Web 页面：**提供估值计算器、组合报告、报告浏览和手动日常更新。

后台不再调用大模型，也不再维护另一套自动研报 Agent。这样可以避免 ChatGPT 与后台模型产生两套互相冲突的投资方法。

## 当前能力

### Bigfish 研究方法

`skills/bigfish/` 保存五年长期投资方法，包括：

- 公司质地优先；
- 五年反向估值；
- 规范化利润和规范化 P/E；
- 过去五年营收与经营利润趋势；
- 利润异常波动和利润桥；
- 风险机制、领先指标和失效阈值；
- 公司发展阶段与隐含增长合理性验证；
- 13% 默认要求年化回报；
- 股息、股份稀释、回购和净现金分析。

### ChatGPT 插件工具

MCP 服务提供：

- 读取和搜索已有文件报告；
- 读取和保存投资论点、假设、预测、关键未知与跟踪变量；
- 保存估值快照并读取估值历史；
- 保存经用户明确确认的真实交易记录；
- 保存经用户确认的讨论纪要；
- 分章保存、定稿和读取 ChatGPT 撰写的正式研报；
- CAGR、隐含利润增长和情景回报等确定性计算；
- 后台维护任务的状态、取消和清理。

正式研报由当前 ChatGPT 按 Bigfish 方法生成。用户确认后，后台只负责保存，不会调用另一个模型重写。

### 本地投资功能

- SQLite 市场数据缓存；
- SEC EDGAR 公司财务数据；
- FMP、Alpha Vantage 和 Yahoo Finance 行情备用链；
- 持仓、交易流水、成本和风险标签；
- 组合集中度、风险主题和压力测试；
- Markdown/HTML 组合报告；
- SQLite 安全备份、校验和恢复；
- 五年隐含增长率计算器。

## 安装

需要 Python 3.11 或更高版本：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

复制环境变量示例：

```bash
cp .env.example .env.local
```

本地 Web、SQLite 和计算工具本身不需要 `OPENAI_API_KEY`。如果要通过 OpenAI 安全隧道连接 ChatGPT 私人应用，则仍需填写该项；后台不会用它调用大模型。可选市场数据 Key 和 Web 设置见 `.env.example`。

## 启动本地服务

macOS 可以双击：

```text
启动投资研究系统.command
```

也可以运行：

```bash
.venv/bin/python tools/local_services.py start
.venv/bin/python tools/local_services.py status
.venv/bin/python tools/local_services.py stop
```

服务包括：

- Web 页面：`http://127.0.0.1:8080`
- MCP 服务：`http://127.0.0.1:8090/mcp`
- OpenAI 安全隧道（仅在本机已配置时启动）

## 组合管理

录入或更新持仓：

```bash
python -m investment_os.app.portfolio add NVDA --shares 10 --cost 150
```

记录真实交易流水：

```bash
python -m investment_os.app.portfolio buy NVDA --shares 2 --price 180 --note "长期持仓"
```

生成组合综合复核：

```bash
python -m investment_os.app.portfolio review
```

运行内置压力情景：

```bash
python -m investment_os.app.portfolio risk-suite
```

这些功能不连接券商，也不会执行真实交易。

## 备份与恢复

创建数据库备份：

```bash
python -m investment_os.app.backup
```

验证备份：

```bash
python -m investment_os.app.backup --verify backups/备份文件.db
```

恢复前必须明确确认：

```bash
python -m investment_os.app.restore backups/备份文件.db --confirm RESTORE
```

恢复工具会先备份当前数据库，再原子替换目标文件。

## 测试

```bash
.venv/bin/python -m pytest -q
```

## 数据与隐私

以下内容不会提交到 GitHub：

- `.env.local` 和 API Key；
- SQLite 数据库；
- 数据库备份；
- Chroma 旧数据；
- 生成的公司、组合和监控报告；
- 本机 Tunnel 配置、日志和下载的二进制程序。

公开仓库只包含代码、测试、方法文档和无敏感信息的示例配置。

## 架构文档

- [目标架构](docs/architecture.md)
- [结构化记忆模型](docs/knowledge-schema.md)

本项目只用于个人投资研究与学习，不构成投资建议。
