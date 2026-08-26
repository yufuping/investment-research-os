# Bigfish / Investment Research OS

Bigfish 是一个单用户、私有、长期投资研究操作系统。当前仓库包含一套已经可以运行的 Legacy MVP，以及正在按新架构演进的 Bigfish Skill 与工具服务。

## 本地一键启动

macOS 上双击项目根目录的 `启动投资研究系统.command`，会检查并启动浏览器网页、ChatGPT MCP 和 OpenAI 安全隧道。重复双击不会重复启动已在运行的服务。

命令行也可以使用：

```bash
.venv/bin/python tools/local_services.py start
.venv/bin/python tools/local_services.py status
.venv/bin/python tools/local_services.py stop
```

运行日志保存在 `.runtime/logs/`，该目录不会提交到 Git。

> **架构来源：**新开发必须以 [docs/architecture.md](docs/architecture.md) 为准。下方基于 OpenAI Agents SDK、SQLite、Chroma 和本地报告生成的说明记录的是当前 Legacy MVP，不再代表长期目标架构。

长期目标由 ChatGPT 负责公共信息研究和推理，`$bigfish` Skill 负责投资方法与研究编排，Cloud Run 提供轻量确定性工具和记忆接口，Neon PostgreSQL 保存正式的长期投资知识。现有功能会分阶段迁移，不在一次改动中全部移除。

新结构化记忆层的表设计、安全边界和迁移说明见 [docs/knowledge-schema.md](docs/knowledge-schema.md)。

## MVP 功能

- 首席投资官 Agent 统筹商业、财务、估值和风险四名专业分析 Agent。
- 默认使用混合模型：商业、财务和估值使用 `gpt-4.1-mini`，风险分析与最终 CIO 综合使用 `gpt-5.6-sol`。
- SEC EDGAR 获取公司官方申报财务数据，无需 API Key。
- Alpha Vantage 获取最近交易日股价、公司资料和估值指标。
- Yahoo Finance 仅在主要数据源失败时作为备用。
- 同一只股票每次研究只抓取一次市场数据，所有 Agent 共用快照。
- 市场数据写入 SQLite 缓存；遇到限流时自动重试，并可回退到旧缓存。
- SQLite 保存研究任务、执行状态和报告路径。
- Chroma 保存历史投资逻辑并支持语义检索。
- 研究结果以 Markdown 报告保存到 `reports/generated/`。
- 保存前自动检查章节完整性、日期可信度、金额单位、SEC 来源、风险传导和估值纪律；严重错误会阻止报告入库。
- 每份报告生成公司特定的持续跟踪清单，分为季度观察、年度重估和立即复核触发器。

本项目仅用于投资研究和学习，不构成投资建议。

## 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

程序从 `.env.local` 读取密钥。请在其中配置 `OPENAI_API_KEY`；其他可选设置可参考 `.env.example`。

模型分工可以分别配置：`OPENAI_MODEL` 控制商业、财务和估值 Agent，
`OPENAI_RISK_MODEL` 控制风险 Agent，`OPENAI_CIO_MODEL` 控制最终综合 Agent。

Chroma 第一次保存研究记忆时，可能会下载一次本地语义模型。

市场数据缓存默认有效期为 6 小时。报告会注明数据获取时间、价格日期、SEC 申报日期、缓存状态和实际数据源；如果主要数据源失败且没有缓存，Agent 必须明确报告数据缺口，不能猜测当前数字或日期。

## 运行

分析 NVIDIA：

```bash
python -m investment_os.app.main NVDA
```

指定研究重点：

```bash
python -m investment_os.app.main AAPL --question "重点分析服务业务和估值风险"
```

也可以在生成报告时调整五年估值情景。增长率填写百分数，市盈率填写倍数：

```bash
python -m investment_os.app.main NVDA \
  --bear-growth 5 --bear-pe 16 \
  --base-growth 18 --base-pe 24 \
  --bull-growth 28 --bull-pe 32
```

如果不填写这些参数，系统默认使用 `10%/18倍`、`20%/25倍`、`30%/32倍` 三组示例假设。

报告还会进行反向估值：根据当前股价、基准情景期末市盈率和要求回报率，反推出未来五年需要实现的 EPS 增长率。
默认要求年化回报率为 12%，可以通过 `--required-return 15` 等参数修改。
报告同时生成反向估值矩阵，交叉展示不同要求回报率和期末市盈率所对应的必要 EPS 增长率。
每个估值情景还会计算满足要求回报率时的最高可接受买入价，并显示当前价格相对该价格的溢价或折价。
系统会进一步标明当前价格处于悲观、基准或乐观假设对应的条件估值区间，但不会据此给出买卖指令。

## 比较历史研究

同一家公司至少生成两份报告后，可以比较最近两次研究：

```bash
python -m investment_os.app.compare NVDA
```

系统会生成中文变化报告，分别说明数据、估值、投资逻辑、风险和失效条件的变化，并保存到 `reports/comparisons/`。

## 快速复核

不调用大模型，只刷新 SEC 和市场数据，并与最近一次完整报告比较：

```bash
python -m investment_os.app.monitor NVDA
```

若检测到新的财务申报期间，系统会提示重新运行完整研究；只有价格变化时，不会把它误判为投资逻辑变化。
快速复核会使用最新股价和 TTM EPS，重新计算五年估值情景、反向估值矩阵和最高可接受买入价。
结果保存到 `reports/monitoring/`。

一键复核 SQLite 中的全部观察公司：

```bash
python -m investment_os.app.monitor_all
```

系统会生成一张总览，区分“继续观察”“复核估值假设”和“运行完整研究”。

## 投资组合

录入或更新持仓（不会连接券商，也不会执行交易）：

```bash
python -m investment_os.app.portfolio add NVDA --shares 10 --cost 150
```

刷新市场价格并生成组合概览：

```bash
python -m investment_os.app.portfolio show
```

组合报告会自动检查单一持仓、前两大/前三大集中度、共同风险主题暴露和价格时效。默认提醒线可在 `.env.local` 中调整：

```text
PORTFOLIO_SINGLE_POSITION_ALERT_PCT=20
PORTFOLIO_TOP_TWO_ALERT_PCT=45
PORTFOLIO_TOP_THREE_ALERT_PCT=60
PORTFOLIO_RISK_THEME_ALERT_PCT=50
```

预警只表示需要复核风险，并不自动生成买卖建议。

按风险主题执行静态压力测试，例如假设“AI资本开支周期”相关持仓同时下跌 30%：

```bash
python -m investment_os.app.portfolio stress --theme AI资本开支周期 --shock -30
```

结果会显示受影响持仓、组合持仓价值变化、压力后的权重和每只持仓的损失贡献度。它是敏感性测试，不是股价预测。

组合估值会比较价格日期：如果用户截图/对账单的参考价格比市场收盘价更新，则采用较新的人工价格；同一日期优先采用市场数据。

人工价格应明确记录它实际对应的日期，而不是依赖文件录入时间：

```bash
python -m investment_os.app.portfolio price NVDA --price 215.38 --date 2026-08-23 --source 用户截图
```

也可以把多个主题组合成一个情景；重叠持仓只采用最不利冲击，不会重复扣减：

```bash
python -m investment_os.app.portfolio scenario --name AI投资降温 \
  --shock AI资本开支周期=-30 \
  --shock 美国大型科技=-20 \
  --shock 半导体=-35
```

一次运行四个内置情景并比较结果：

```bash
python -m investment_os.app.portfolio risk-suite
```

内置跌幅只是可重复使用的压力假设，不代表预测或发生概率。

生成一份包含持仓概览、集中度预警、价格时效和全部风险情景的综合复核报告：

```bash
python -m investment_os.app.portfolio review
```

从第二次综合复核开始，报告还会自动比较上次快照，显示组合持仓总价值、前两大集中度，以及每只股票的股数、价格和权重变化。

每次还会更新固定文件 `reports/portfolio/组合综合复核-最新.md`；带时间戳的历史版本仍会保留。没有实际变化时，报告会省略全为零的明细表。
只有股数、价格或组合数据实际变化时才新增历史快照；单纯刷新报告不会制造重复记录。

同时会生成 `reports/portfolio/组合综合复核-最新.html`，可以直接用浏览器打开、缩放或打印，不需要安装额外软件。
浏览器版会用比例条展示组合权重、风险主题暴露、情景影响和损失贡献，并用颜色区分预警级别。
长报告顶部提供章节导航，汇总数字使用卡片展示；点击导航即可跳转到对应部分。
持仓表下方还会生成核心个股权重环形图；风险主题因存在重叠，仍使用比例条而不是饼图。
综合复核还会展示最近 12 次有效快照，并在浏览器版绘制持仓总价值趋势线。

新生成的公司研究报告也会同时保存时间戳 HTML 和固定的 `股票代码-最新.html`。已有 Markdown 报告可手动转换：

```bash
python -m investment_os.app.export_html reports/generated/NVDA-时间戳.md --title "NVDA 长期投资研究报告"
```

`reports/报告中心.html` 会集中列出固定最新版和最近生成的浏览器报告，生成公司研报或组合综合复核时自动更新。
报告中心支持按股票代码/名称搜索，并可筛选组合报告或公司研究。
历史版本默认折叠；搜索时会自动展开历史区域。
组合浏览器报告中的股票代码会链接到已经存在的该公司最新研报；没有完整研报的持仓不会生成无效链接。
公司研报和组合报告顶部都有“返回报告中心”链接，便于在各报告之间切换。
公司变化报告、快速复核和全部观察汇总也会同步生成 HTML、固定最新版，并自动加入报告中心。
观察清单和快速复核中的股票代码会自动链接到已有的完整公司研报。

macOS 用户可以直接双击 `scripts/更新全部报告.command`。它会依次更新组合综合复核和全部观察清单，然后自动打开报告中心；无需手动输入终端命令。运行窗口会保留结果，按回车后关闭。
一键更新会先使用 SQLite 的安全备份机制，把数据库保存到 `backups/`；备份不包含 `.env.local` 或 API Key。也可以单独运行 `python -m investment_os.app.backup`。
每份备份会自动执行 SQLite 完整性检查，并生成同名 `.sha256` 校验文件。可用 `python -m investment_os.app.backup --verify backups/备份文件.db` 再次校验。

需要恢复时，可运行 `python -m investment_os.app.restore backups/备份文件.db --confirm RESTORE`。恢复工具会先验证备份、再把当前数据库保存到 `backups/before-restore/`，最后原子替换数据库。不要在程序正在写入数据库时执行恢复。

## 单用户 Web 管理页

设置 `WEB_USERNAME`、`WEB_PASSWORD` 和随机的 `WEB_SECRET_KEY` 后运行：

```bash
python -m investment_os.app.web
```

打开 `http://127.0.0.1:8080`，登录后可以输入公司名或股票代码，确认 API 费用后在后台生成完整研究报告。`/health` 用于云服务器健康检查。生产环境应使用单个 Gunicorn worker，避免 SQLite 并发写入。

首页的“更新全部日常报告”会先备份数据库，再刷新组合综合复核和全部观察清单；该流程不调用完整研究模型。任务完成后可直接打开报告中心，不需要运行终端命令。

只在本机使用时可以设置 `WEB_LOCAL_ONLY=true`。服务将只监听 `127.0.0.1` 且不要求登录；不要在云服务器或需要局域网访问时启用该选项。

## ChatGPT 私人研报插件（MCP）

启动 MCP 服务：

```bash
python -m investment_os.app.mcp_server
```

服务默认位于 `http://127.0.0.1:8090/mcp`，健康检查为 `http://127.0.0.1:8090/health`。它提供标准报告搜索与读取、完整研究生成、任务状态查询、任务列表、任务取消和日常更新工具。完整研究工具必须显式确认 API 费用；运行异常或超时的任务会自动结束并释放任务锁。

ChatGPT 正常生成研报时应调用高级工具 `generate_research_report`。该工具会在内部启动或复用后台任务，按 2、3、5 秒退避等待，完成后直接返回完整 Markdown 正文。`start_research` 与 `get_task_status` 仅保留给诊断流程。同一股票、同一问题的重复请求会连接到已有任务，不会重复生成；不同股票最多三个并行运行。任务状态持久化在 `database/plugin_tasks.json`，服务重启时会自动清理无法恢复的旧任务。

本地 MCP 地址不能由 ChatGPT 直接访问。测试私人插件时，应使用安全 HTTPS 隧道映射 8090 端口，再在 ChatGPT 开发者模式中添加隧道地址加 `/mcp`。正式部署时应使用稳定的 HTTPS 地址，并设置 `MCP_REPORT_BASE_URL` 为云端网页报告目录。

情景保存在 `config/risk_scenarios.json`。可以直接用中文增加、删除或调整情景，无需修改 Python 代码。每个主题的数字代表假设价格变动百分比，并且必须大于 `-100`。

删除本地持仓记录：

```bash
python -m investment_os.app.portfolio remove NVDA
```

为持仓设置可重叠的风险主题：

```bash
python -m investment_os.app.portfolio tag NVDA --tags 半导体 AI基础设施 AI资本开支周期
```

组合报告还会计算完整研究覆盖率，并按照未研究持仓的当前权重排列下一步研究优先级。
每个价格都会显示来源和日期；人工参考价格超过一天或市场价格缺少日期时，报告会明确标记为过期。

每次运行 `portfolio show` 都会保存一份组合快照。查看历史变化：

```bash
python -m investment_os.app.portfolio history
```

历史报告会把每只持仓的持仓价值变化分解为股数变化、价格变化和交互项，并区分主动调整与市场自然漂移。

首次导入后，未来买卖应使用交易流水命令，系统会自动更新持仓和移动加权平均成本：

```bash
python -m investment_os.app.portfolio buy NVDA --shares 10 --price 200 --fee 1
python -m investment_os.app.portfolio sell NVDA --shares 5 --price 230 --fee 1
python -m investment_os.app.portfolio transactions
```

记录并查看投资决策理由：

```bash
python -m investment_os.app.portfolio decision NVDA --action 持有 \
  --thesis "AI利润池继续扩大，但需验证长期份额和利润率" \
  --price 214.72 --valuation "五年反向估值" \
  --invalidation "份额和利润率同时持续下降" --next-check "下一次财报"
python -m investment_os.app.portfolio journal NVDA
```

## 测试

```bash
pytest
```

## 项目结构

```text
investment-research-os/
├── investment_os/          Python 程序源码
│   ├── agents/             投资研究 Agent
│   ├── tools/              市场数据工具
│   ├── database/           SQLite 操作代码
│   ├── memory/             Chroma 操作代码
│   ├── reports/            报告生成代码
│   └── app/                命令行入口和配置
├── database/               运行后生成的 SQLite 数据
├── memory/                 运行后生成的 Chroma 数据
├── reports/generated/      生成的投资研究报告
└── tests/                  自动测试
```

## 工作流程

```text
用户输入股票代码
        ↓
首席投资官 Agent
        ↓
商业 / 财务 / 估值 / 风险 Agent
        ↓
市场数据 + SQLite + Chroma
        ↓
中文 Markdown 投资研究报告
```
