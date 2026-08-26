from datetime import UTC, datetime
from pathlib import Path
import re
from urllib.parse import urlencode

from investment_os.reports.html import save_html_report
from investment_os.reports.index import build_report_center


DEFAULT_VALUATION_SCENARIOS = (
    ("悲观", 10.0, 18.0),
    ("基准", 20.0, 25.0),
    ("乐观", 30.0, 32.0),
)


def calculate_acceptable_prices(eps: float, scenarios, required_return: float = 12.0) -> dict[str, float]:
    """计算各情景满足要求回报率时的当前可接受价格。"""
    return {
        name: eps * (1 + growth / 100) ** 5 * exit_pe / (1 + required_return / 100) ** 5
        for name, growth, exit_pe in scenarios
    }


def _raw_usd_to_hundred_million(value) -> str:
    """把 SEC 原始美元数值换算为亿美元。"""
    if not isinstance(value, (int, float)):
        return "—"
    return f"{value / 100_000_000:.2f}"


def _percentage(value) -> str:
    return "—" if not isinstance(value, (int, float)) else f"{value:.2f}%"


def _currency_name(code: str | None) -> str:
    return {"USD": "美元", "TWD": "新台币", "CNY": "人民币", "EUR": "欧元", "JPY": "日元"}.get(code or "USD", code or "美元")


def _period(start, end) -> str:
    return f"{start} 至 {end}" if start and end else "数据缺失"


def _ratio(numerator, denominator) -> float | None:
    if not isinstance(numerator, (int, float)) or not isinstance(denominator, (int, float)) or denominator == 0:
        return None
    return numerator / denominator * 100


def build_trend_interpretation(data: dict) -> str:
    """基于已核验数据生成可复算的趋势解读，不引入模型猜测。"""
    annual = data.get("年度财务趋势") or []
    quarterly = data.get("季度财务趋势") or []
    lines = ["## 趋势解读", ""]

    if len(annual) >= 2:
        newest, oldest = annual[0], annual[-1]
        years = len(annual) - 1
        revenue_cagr = None
        income_cagr = None
        if isinstance(newest.get("收入"), (int, float)) and isinstance(oldest.get("收入"), (int, float)) and oldest["收入"] > 0:
            revenue_cagr = ((newest["收入"] / oldest["收入"]) ** (1 / years) - 1) * 100
        if (
            isinstance(newest.get("净利润"), (int, float))
            and isinstance(oldest.get("净利润"), (int, float))
            and newest["净利润"] > 0
            and oldest["净利润"] > 0
        ):
            income_cagr = ((newest["净利润"] / oldest["净利润"]) ** (1 / years) - 1) * 100
        if revenue_cagr is not None:
            lines.append(
                f"- **长期增长：** 从财年结束日 {oldest.get('结束日')} 到 {newest.get('结束日')}，"
                f"营业收入复合年增长率约为 {revenue_cagr:.2f}%"
                + (f"，净利润复合年增长率约为 {income_cagr:.2f}%。" if income_cagr is not None else "。")
            )
        if (
            isinstance(newest.get("净利润"), (int, float))
            and isinstance(oldest.get("净利润"), (int, float))
            and newest["净利润"] * oldest["净利润"] <= 0
        ):
            lines.append("- **长期盈利变化：** 起止年度净利润跨越盈亏平衡点，净利润 CAGR 在数学上无意义，因此不予计算。")

    if quarterly:
        newest = quarterly[0]
        latest_growth = newest.get("收入同比增长率")
        previous_growth = quarterly[1].get("收入同比增长率") if len(quarterly) > 1 else None
        if isinstance(latest_growth, (int, float)) and isinstance(previous_growth, (int, float)):
            change = latest_growth - previous_growth
            direction = "加快" if change > 0 else "放缓" if change < 0 else "持平"
            lines.append(
                f"- **增长动能：** 最新季度收入同比增长 {latest_growth:.2f}%，"
                f"上一季度为 {previous_growth:.2f}%，同比增速{direction} {abs(change):.2f} 个百分点。"
            )

        oldest = quarterly[-1]
        latest_net_margin = _ratio(newest.get("净利润"), newest.get("收入"))
        oldest_net_margin = _ratio(oldest.get("净利润"), oldest.get("收入"))
        if latest_net_margin is not None and oldest_net_margin is not None:
            margin_change = latest_net_margin - oldest_net_margin
            direction = "提高" if margin_change > 0 else "下降" if margin_change < 0 else "持平"
            lines.append(
                f"- **盈利能力：** 最新季度净利率约为 {latest_net_margin:.2f}%，"
                f"八季度表中最早季度为 {oldest_net_margin:.2f}%，{direction} {abs(margin_change):.2f} 个百分点。"
            )

        latest_fcf_margin = _ratio(newest.get("自由现金流"), newest.get("收入"))
        latest_fcf_conversion = _ratio(newest.get("自由现金流"), newest.get("净利润"))
        if latest_fcf_margin is not None and latest_fcf_conversion is not None:
            lines.append(
                f"- **现金流质量：** 最新季度自由现金流率约为 {latest_fcf_margin:.2f}%，"
                f"自由现金流相当于净利润的 {latest_fcf_conversion:.2f}%。"
            )

        available_growth = [row.get("收入同比增长率") for row in quarterly if isinstance(row.get("收入同比增长率"), (int, float))]
        if available_growth:
            positive = sum(value > 0 for value in available_growth)
            lines.append(f"- **增长持续性：** 可比的 {len(available_growth)} 个季度中，有 {positive} 个季度实现收入同比正增长。")

    if len(lines) == 2:
        lines.append("- 历史数据不足，暂时无法形成可靠的趋势判断。")
    lines.extend([
        "",
        "> 上述结论仅描述已申报历史数据的变化，不代表未来增长率，也不构成投资建议。",
    ])
    return "\n".join(lines)


def build_valuation_scenarios(data: dict, scenarios=None, required_return: float = 12.0) -> str:
    """生成透明、可复算的五年 EPS 估值敏感性分析。"""
    price = data.get("当前价格")
    trailing_pe = data.get("滚动市盈率")
    normalized_pe = data.get("规范化市盈率")
    eps = data.get("每股收益_TTM")
    eps_source = "Alpha Vantage 的 TTM 摊薄每股收益"
    if isinstance(normalized_pe, (int, float)) and normalized_pe > 0 and isinstance(price, (int, float)):
        eps = price / normalized_pe
        eps_source = "当前股价÷基准规范化市盈率的反推值"
    elif not isinstance(eps, (int, float)) and isinstance(price, (int, float)) and isinstance(trailing_pe, (int, float)) and trailing_pe:
        eps = price / trailing_pe
        eps_source = "当前股价÷滚动市盈率的反推值"

    lines = [
        "### 五年估值情景（示例假设）",
        "",
        "> 这是一张估值敏感性表，不是目标价预测。默认假设用于建立模型骨架，后续应根据公司研究调整。",
        "",
    ]
    if not isinstance(price, (int, float)) or not isinstance(eps, (int, float)) or eps <= 0:
        lines.append("当前股价或 TTM 每股收益缺失，暂时无法计算五年估值情景。")
        return "\n".join(lines)

    scenarios = scenarios or DEFAULT_VALUATION_SCENARIOS
    lines.extend([
        f"计算起点：当前股价 {price:.2f} 美元；TTM 每股收益 {eps:.2f} 美元（{eps_source}）。",
        "假设持有期为五年，不计股息、税费、汇率和股份稀释影响。",
        "",
        "| 情景 | EPS 年增长假设 | 五年后 EPS | 期末市盈率 | 五年后价格 | 隐含年化回报 |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for name, growth, exit_pe in scenarios:
        future_eps = eps * (1 + growth / 100) ** 5
        future_price = future_eps * exit_pe
        annual_return = (future_price / price) ** (1 / 5) - 1
        lines.append(
            f"| {name} | {growth:.0f}% | {future_eps:.2f} 美元 | {exit_pe:.0f} 倍 | "
            f"{future_price:.2f} 美元 | {annual_return * 100:.2f}% |"
        )

    current_pe = normalized_pe if isinstance(normalized_pe, (int, float)) and normalized_pe > 0 else trailing_pe
    current_pe = current_pe if isinstance(current_pe, (int, float)) and current_pe > 0 else price / eps
    base_scenario = next((scenario for scenario in scenarios if scenario[0] == "基准"), scenarios[len(scenarios) // 2])
    calculator_query = urlencode({
        "currentPE": f"{current_pe:.2f}",
        "futurePE": f"{float(base_scenario[2]):.2f}",
        "returnRate": f"{required_return:.2f}",
        "expectedGrowth": f"{float(base_scenario[1]):.2f}",
    })
    lines.extend([
        "",
        f"[打开五年投资收益计算器（已带入当前 PE {current_pe:.2f} 倍）]"
        f"(../%E4%BA%94%E5%B9%B4%E9%9A%90%E5%90%AB%E5%A2%9E%E9%95%BF%E7%8E%87%E8%AE%A1%E7%AE%97%E5%99%A8.html?{calculator_query})",
        "",
        "公式：五年后 EPS = 当前 TTM EPS × (1 + EPS 年增长率)⁵；五年后价格 = 五年后 EPS × 期末市盈率。",
    ])

    reverse_exit_pe = base_scenario[2]
    required_future_price = price * (1 + required_return / 100) ** 5
    required_future_eps = required_future_price / reverse_exit_pe
    implied_growth = (required_future_eps / eps) ** (1 / 5) - 1
    lines.extend([
        "",
        "### 反向估值：当前价格要求什么增长",
        "",
        f"如果投资者要求未来五年获得 {required_return:.2f}% 的年化回报，并假设第五年末市盈率为 "
        f"{reverse_exit_pe:.2f} 倍，则第五年股价需要达到 {required_future_price:.2f} 美元，"
        f"对应第五年 EPS 为 {required_future_eps:.2f} 美元。",
        f"由当前 TTM EPS {eps:.2f} 美元反推，未来五年 EPS 需要实现约 **{implied_growth * 100:.2f}%** 的年复合增长。",
        "",
        "> 反向估值不是盈利预测。它把当前价格转化为需要持续验证的增长假设；若长期份额或利润率下降，收入增长未必能转化为同等 EPS 增长。",
    ])

    exit_pes = sorted({float(scenario[2]) for scenario in scenarios})
    required_returns = sorted({10.0, float(required_return), 15.0})
    lines.extend([
        "",
        "### 反向估值矩阵：所需五年 EPS 年复合增长",
        "",
        "每个格子表示：在对应要求回报率和第五年末市盈率下，当前价格所要求的未来五年 EPS 年复合增长率。",
        "",
        "| 要求年化回报率 / 第五年末市盈率 | " + " | ".join(f"{pe:g} 倍" for pe in exit_pes) + " |",
        "|---|" + "---:|" * len(exit_pes),
    ])
    for target_return in required_returns:
        cells = []
        for exit_pe in exit_pes:
            future_price = price * (1 + target_return / 100) ** 5
            future_eps = future_price / exit_pe
            growth = (future_eps / eps) ** (1 / 5) - 1
            cells.append(f"{growth * 100:.2f}%")
        lines.append(f"| {target_return:g}% | " + " | ".join(cells) + " |")
    lines.extend([
        "",
        "> 读表方法：所需 EPS 增速越高，当前价格对未来经营表现的要求越苛刻；期末市盈率假设越高，结果越依赖市场继续给予高估值。",
    ])

    lines.extend([
        "",
        "### 最高可接受买入价（基于情景假设）",
        "",
        f"下表按照 {required_return:.2f}% 的要求年化回报率，将各情景的第五年价格折现回今天。",
        "",
        "| 情景 | EPS 年增长假设 | 第五年末市盈率 | 第五年价格 | 最高可接受买入价 | 当前价格相对可接受价 |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    acceptable_prices = calculate_acceptable_prices(eps, scenarios, required_return)
    for name, growth, exit_pe in scenarios:
        future_eps = eps * (1 + growth / 100) ** 5
        future_price = future_eps * exit_pe
        acceptable_price = future_price / (1 + required_return / 100) ** 5
        premium = (price / acceptable_price - 1) * 100
        relative_label = f"溢价 {premium:.2f}%" if premium > 0 else f"折价 {abs(premium):.2f}%"
        lines.append(
            f"| {name} | {growth:.2f}% | {exit_pe:.2f} 倍 | {future_price:.2f} 美元 | "
            f"{acceptable_price:.2f} 美元 | {relative_label} |"
        )
    lines.extend([
        "",
        "> “最高可接受买入价”只在对应增长率、期末市盈率、持有五年和要求回报率全部成立时有效，"
        "不是独立于假设的内在价值，也没有计入股息、税费、汇率和股份稀释。",
    ])

    prices = acceptable_prices
    bear_price = prices.get("悲观")
    base_price = prices.get("基准")
    bull_price = prices.get("乐观")
    if all(isinstance(value, (int, float)) for value in (bear_price, base_price, bull_price)):
        if price <= bear_price:
            zone = "当前价格不高于悲观情景可接受价；在三组条件中，对增长和期末估值的依赖最低。"
        elif price <= base_price:
            zone = "当前价格高于悲观情景、但不高于基准情景可接受价；需要基准或更好的经营结果才能达到要求回报。"
        elif price <= bull_price:
            zone = "当前价格高于基准情景可接受价；需要偏乐观的增长与期末估值组合才能达到要求回报。"
        else:
            zone = "当前价格高于乐观情景可接受价；即使乐观假设成立，也可能无法达到设定的要求回报。"
        lines.extend([
            "",
            "### 条件估值位置",
            "",
            f"**{zone}**",
            "",
            "> 这是基于当前三组假设的条件判断，不是“便宜/昂贵”的绝对结论，也不是交易建议。",
        ])
    return "\n".join(lines)


def build_financial_trend_sections(data: dict) -> str:
    """用 SEC 原始期间数据生成年度与季度趋势表。"""
    sections: list[str] = []
    currency_name = _currency_name(data.get("财务货币"))
    specifications = (
        ("五年财务趋势", "年度财务趋势", "财年结束日"),
        ("最近八个季度趋势", "季度财务趋势", "季度结束日"),
    )
    for title, key, period_label in specifications:
        rows = data.get(key) or []
        sections.extend([
            f"## {title}",
            "",
            f"数据来源：SEC EDGAR；金额单位为亿{currency_name}。同比增长按可比上年同期计算。",
            "",
            f"| {period_label} | 营业收入 | 收入同比 | 净利润 | 净利润同比 | 自由现金流 | 自由现金流同比 |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ])
        if rows:
            for row in rows:
                sections.append(
                    "| {period} | {revenue} | {revenue_growth} | {net_income} | "
                    "{net_income_growth} | {fcf} | {fcf_growth} |".format(
                        period=row.get("结束日") or "—",
                        revenue=_raw_usd_to_hundred_million(row.get("收入")),
                        revenue_growth=_percentage(row.get("收入同比增长率")),
                        net_income=_raw_usd_to_hundred_million(row.get("净利润")),
                        net_income_growth=_percentage(row.get("净利润同比增长率")),
                        fcf=_raw_usd_to_hundred_million(row.get("自由现金流")),
                        fcf_growth=_percentage(row.get("自由现金流同比增长率")),
                    )
                )
        else:
            sections.append("| 暂无可用数据 | — | — | — | — | — | — |")
        sections.extend(["", "> “—”表示 SEC 在该精确期间下没有可直接匹配的数据。", ""])
    sections.extend(["", build_trend_interpretation(data)])
    return "\n".join(sections).rstrip()


def build_verified_data_table(snapshot: dict) -> str:
    """用程序确定性生成关键数据表，避免模型发生单位换算错误。"""
    data = snapshot.get("数据", {})
    assets = data.get("资产总额")
    liabilities = data.get("负债总额")
    debt_ratio = (
        round(liabilities / assets * 100, 2)
        if isinstance(assets, (int, float)) and assets and isinstance(liabilities, (int, float))
        else None
    )
    financial_unit = f"十亿{_currency_name(data.get('财务货币'))}"
    rows = [
        ("最近交易日股价", data.get("当前价格"), "美元", data.get("价格日期")),
        ("市值", data.get("市值_十亿美元"), "十亿美元", data.get("价格日期")),
        ("最新申报收入", data.get("最新申报收入_十亿美元"), financial_unit, _period(data.get("收入期间开始日"), data.get("收入报告期结束日"))),
        ("最新申报净利润", data.get("最新申报净利润_十亿美元"), financial_unit, _period(data.get("净利润期间开始日"), data.get("净利润报告期结束日"))),
        ("经营现金流（含派生值）", data.get("最新申报经营现金流_十亿美元"), financial_unit, _period(data.get("现金流期间开始日"), data.get("现金流期间结束日"))),
        ("资本开支", data.get("最新申报资本开支_十亿美元"), financial_unit, _period(data.get("现金流期间开始日"), data.get("现金流期间结束日"))),
        ("报告口径自由现金流（未规范化）", data.get("计算自由现金流_十亿美元"), financial_unit, _period(data.get("现金流期间开始日"), data.get("现金流期间结束日"))),
        ("负债/资产", debt_ratio, "%", data.get("SEC最新申报日期")),
        ("滚动市盈率", data.get("滚动市盈率"), "倍", data.get("价格日期")),
        ("预期市盈率", data.get("预期市盈率"), "倍", data.get("价格日期")),
        ("市销率", data.get("市销率"), "倍", data.get("价格日期")),
        ("EV/EBITDA", data.get("企业价值倍数_EV_EBITDA"), "倍", data.get("价格日期")),
    ]
    lines = [
        "## 系统核验数据表",
        "",
        "> 本表由程序直接根据 SEC 与 Alpha Vantage 数据生成，金额单位已经确定性换算；如正文与本表冲突，以本表为准。",
        "",
        "| 指标 | 数值 | 单位 | 数据期间/日期 |",
        "|---|---:|---|---|",
    ]
    for name, value, unit, period in rows:
        display = "数据缺失" if value is None else str(value)
        lines.append(f"| {name} | {display} | {unit} | {period or '数据缺失'} |")
    lines.extend([
        "",
        f"实际数据来源：{data.get('本次实际数据来源') or snapshot.get('数据来源')}  ",
        f"SEC 最新申报日期：{data.get('SEC最新申报日期') or '数据缺失'}  ",
        f"缓存状态：{snapshot.get('缓存状态')}；抓取时间（UTC）：{snapshot.get('数据获取时间_UTC')}",
        "",
    ])
    return "\n".join(lines)


def replace_quantitative_sections(
    content: str,
    snapshot: dict,
    valuation_scenarios=None,
    required_return: float = 12.0,
) -> str:
    """用确定性模板替换模型生成的财务与估值段落。"""
    # 最终报告的核验表由 save_report 统一前置；禁止保留模型自行生成、可能单位错误的同名表。
    content = re.sub(
        r"\n(?:---\s*\n)?#{1,3} (?:数据表（已程序核验）|参考数据).*\Z",
        "",
        content,
        flags=re.S,
    ).rstrip()
    data = snapshot.get("数据", {})
    scenarios = valuation_scenarios or DEFAULT_VALUATION_SCENARIOS
    price = data.get("当前价格")
    eps = data.get("每股收益_TTM")
    trailing_pe = data.get("滚动市盈率")
    if not isinstance(eps, (int, float)) and isinstance(price, (int, float)) and isinstance(trailing_pe, (int, float)) and trailing_pe:
        eps = price / trailing_pe
    base_scenario = next((scenario for scenario in scenarios if scenario[0] == "基准"), scenarios[len(scenarios) // 2])
    if isinstance(price, (int, float)) and isinstance(eps, (int, float)) and eps > 0:
        base_exit_pe = base_scenario[2]
        required_future_price = price * (1 + required_return / 100) ** 5
        implied_eps = required_future_price / base_exit_pe
        implied_growth = ((implied_eps / eps) ** (1 / 5) - 1) * 100
        # 删除模型在执行摘要中自行采用的估值参数，改由程序写入唯一口径。
        content = re.sub(
            r"(?m)^[-*]\s+.*(?:目标回报率|要求回报率|终值市盈率|期末市盈率).*?$\n?",
            "",
            content,
        )
        content = re.sub(
            r"(?m)^.*(?:目标回报率.*终值市盈率|当前价格.*要求约.*五年EPS|EPS实现约.*五年复合增长).*$\n?",
            "",
            content,
        )
        deterministic_summary = (
            f"- **程序估值口径：**当前股价 {price:.2f} 美元、TTM EPS {eps:.2f} 美元；"
            f"要求五年年化回报 {required_return:.2f}%，基准期末市盈率 {base_exit_pe:.2f} 倍，"
            f"反推未来五年 EPS 需要实现约 {implied_growth:.2f}% 的年复合增长。"
        )
        content, summary_insertions = re.subn(
            r"(?m)^(#{1,3}\s+[^\n]*执行摘要[^\n]*)$",
            rf"\1\n\n{deterministic_summary}",
            content,
            count=1,
        )
        if summary_insertions == 0:
            content = f"# 执行摘要\n\n{deterministic_summary}\n\n{content}"
    else:
        missing_summary = "- **程序估值口径：**当前股价或TTM EPS缺失，无法进行五年反向估值；不得据此判断安全边际。"
        content, summary_insertions = re.subn(
            r"(?m)^(#{1,3}\s+[^\n]*执行摘要[^\n]*)$",
            rf"\1\n\n{missing_summary}",
            content,
            count=1,
        )
        if summary_insertions == 0:
            content = f"# 执行摘要\n\n{missing_summary}\n\n{content}"
    aligned_periods = {
        (data.get("收入期间开始日"), data.get("收入报告期结束日")),
        (data.get("净利润期间开始日"), data.get("净利润报告期结束日")),
        (data.get("现金流期间开始日"), data.get("现金流期间结束日")),
    }
    if len(aligned_periods) == 1 and None not in next(iter(aligned_periods)):
        content = re.sub(
            r"(?m)^.*运行时.*(?:口径异常|内部矛盾).*$\n?",
            "",
            content,
        )
    revenue = data.get("最新申报收入_十亿美元")
    net_income = data.get("最新申报净利润_十亿美元")
    operating_cash = data.get("最新申报经营现金流_十亿美元")
    capex = data.get("最新申报资本开支_十亿美元")
    free_cash_flow = data.get("计算自由现金流_十亿美元")
    previous_revenue = data.get("上年同期收入_十亿美元")
    previous_net_income = data.get("上年同期净利润_十亿美元")
    previous_operating_cash = data.get("上年同期经营现金流_十亿美元")
    previous_capex = data.get("上年同期资本开支_十亿美元")
    previous_free_cash_flow = data.get("上年同期自由现金流_十亿美元")
    market_cap = data.get("市值_十亿美元")
    market_cap_trillion = round(market_cap / 1000, 3) if isinstance(market_cap, (int, float)) else None
    assets = data.get("资产总额")
    liabilities = data.get("负债总额")
    debt_ratio = round(liabilities / assets * 100, 2) if isinstance(assets, (int, float)) and assets and isinstance(liabilities, (int, float)) else None

    # 模型偶尔会把工具的“十亿美元”原值误标为“亿美元”。对当前市值做确定性纠错。
    if isinstance(market_cap, (int, float)):
        correct_hundred_million = market_cap * 10
        corrected = f"{correct_hundred_million:,.2f}亿美元（约{market_cap / 1000:.3f}万亿美元）"
        raw_variants = {str(market_cap), f"{market_cap:g}", f"{market_cap:,}", f"{market_cap:,.3f}"}
        for raw_value in raw_variants:
            content = content.replace(f"{raw_value}亿美元", corrected)

    def to_hundred_million(value):
        return round(value * 10, 2) if isinstance(value, (int, float)) else "数据缺失"

    financial_currency_name = _currency_name(data.get("财务货币"))
    current_period = _period(data.get('收入期间开始日'), data.get('收入报告期结束日'))
    prior_period = _period(data.get('上年同期期间开始日'), data.get('上年同期期间结束日'))

    financial = f"""## 财务质量

数据来源：SEC EDGAR  
报告期间：{current_period}  
数据口径：最新申报期间，金额单位为亿{financial_currency_name}

上年同期：{prior_period}

| 财务指标 | 本期 | 上年同期 | 同比增长 |
|---|---:|---:|---:|
| 营业收入 | {to_hundred_million(revenue)} 亿{financial_currency_name} | {to_hundred_million(previous_revenue)} 亿{financial_currency_name} | {_percentage(data.get('收入同比增长率'))} |
| 净利润 | {to_hundred_million(net_income)} 亿{financial_currency_name} | {to_hundred_million(previous_net_income)} 亿{financial_currency_name} | {_percentage(data.get('净利润同比增长率'))} |
| 经营现金流 | {to_hundred_million(operating_cash)} 亿{financial_currency_name} | {to_hundred_million(previous_operating_cash)} 亿{financial_currency_name} | {_percentage(data.get('经营现金流同比增长率'))} |
| 资本开支 | {to_hundred_million(capex)} 亿{financial_currency_name} | {to_hundred_million(previous_capex)} 亿{financial_currency_name} | {_percentage(data.get('资本开支同比增长率'))} |
| 自由现金流 | {to_hundred_million(free_cash_flow)} 亿{financial_currency_name} | {to_hundred_million(previous_free_cash_flow)} 亿{financial_currency_name} | {_percentage(data.get('自由现金流同比增长率'))} |
| 负债占资产比例 | {f'{debt_ratio}%' if debt_ratio is not None else '数据缺失'} | — | — |

以上数据不是过去十二个月口径；长期变化请结合下方年度与季度趋势表判断。

现金流口径：{data.get('经营现金流口径') or '来源口径未识别'}；资本开支口径：{data.get('资本开支口径') or '来源口径未识别'}。  
此处“自由现金流”仅为报告口径 OCF 减已识别资本开支，**尚未剔除递延收入、异常营运资金、资产出售等一次性因素，不等同于规范化 FCF 或 owner earnings**。

{build_financial_trend_sections(data)}
"""
    valuation = f"""## 估值分析

数据来源：Alpha Vantage  
价格日期：{data.get('价格日期')}  
货币单位：美元

| 估值指标 | 数值 | 说明 |
|---|---:|---|
| 股价 | {data.get('当前价格') if data.get('当前价格') is not None else '数据缺失'} 美元 | 最近交易日收盘价 |
| 总市值 | {market_cap_trillion if market_cap_trillion is not None else '数据缺失'} 万亿美元 | 约 {round(market_cap * 10, 2) if isinstance(market_cap, (int, float)) else '数据缺失'} 亿美元 |
| 滚动市盈率 | {data.get('滚动市盈率') if data.get('滚动市盈率') is not None else '数据缺失'} 倍 | 基于过去十二个月盈利 |
| 预期市盈率 | {data.get('预期市盈率') if data.get('预期市盈率') is not None else '数据缺失'} 倍 | 基于市场盈利预期 |
| 市销率 | {data.get('市销率') if data.get('市销率') is not None else '数据缺失'} 倍 | 市值相对收入水平 |
| EV/EBITDA | {data.get('企业价值倍数_EV_EBITDA') if data.get('企业价值倍数_EV_EBITDA') is not None else '数据缺失'} 倍 | 企业价值相对 EBITDA |

当前估值包含较高的增长预期。以下情景仅用于观察不同增长率和期末估值倍数对回报的影响，不能据此声称存在安全边际。

{build_valuation_scenarios(data, scenarios, required_return=required_return)}
"""
    heading_prefix = r"#{1,3}\s+(?:[一二三四五六七八九十]+[、.．]\s*)?"
    content = re.sub(
        rf"(?m)^{heading_prefix}财务质量\s*$.*?(?=^{heading_prefix}估值分析\s*$)",
        financial.rstrip() + "\n",
        content,
        count=1,
        flags=re.S,
    )
    content = re.sub(
        rf"(?m)^{heading_prefix}估值分析\s*$.*?(?=^{heading_prefix}主要风险\s*$)",
        valuation.rstrip() + "\n",
        content,
        count=1,
        flags=re.S,
    )
    return content


def save_report(
    ticker: str,
    content: str,
    output_dir: Path,
    verified_data: str = "",
    model_summary: str = "",
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"{ticker.upper()}-{timestamp}.md"
    header = f"# {ticker.upper()} 长期投资研究报告\n\n"
    if model_summary:
        header += f"> 模型分工：{model_summary}\n\n"
    path.write_text(f"{header}{verified_data.strip()}\n\n{content.strip()}\n", encoding="utf-8")
    save_html_report(path, f"{ticker.upper()} 长期投资研究报告", f"{ticker.upper()}-最新.html")
    build_report_center(output_dir.parent)
    return path
