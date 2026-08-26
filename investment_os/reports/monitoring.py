from datetime import UTC, datetime
import re

from investment_os.reports.markdown import (
    DEFAULT_VALUATION_SCENARIOS,
    build_valuation_scenarios,
    build_verified_data_table,
    calculate_acceptable_prices,
)


def parse_verified_table(report: str) -> dict[str, dict[str, str]]:
    """读取报告中由程序生成的核验表。"""
    match = re.search(r"## 系统核验数据表\s*(.*?)(?=\n#)", report, flags=re.S)
    if not match:
        return {}
    rows: dict[str, dict[str, str]] = {}
    for line in match.group(1).splitlines():
        if not line.startswith("|") or line.startswith("|---") or "指标 | 数值" in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) == 4:
            rows[cells[0]] = {"数值": cells[1], "单位": cells[2], "期间": cells[3]}
    return rows


def valuation_zone(price: float, acceptable_prices: dict[str, float]) -> str:
    bear = acceptable_prices.get("悲观")
    base = acceptable_prices.get("基准")
    bull = acceptable_prices.get("乐观")
    if not all(isinstance(value, (int, float)) for value in (bear, base, bull)):
        return "数据不足"
    if price <= bear:
        return "不高于悲观情景"
    if price <= base:
        return "悲观与基准之间"
    if price <= bull:
        return "基准与乐观之间"
    return "高于乐观情景"


def build_monitoring_report(
    ticker: str,
    previous_report: str,
    snapshot: dict,
    scenarios=None,
    required_return: float = 12.0,
    saved_acceptable_prices: dict[str, float] | None = None,
    reference_price: float | None = None,
    reference_eps: float | None = None,
) -> str:
    previous = parse_verified_table(previous_report)
    current_table = build_verified_data_table(snapshot)
    current = parse_verified_table(current_table + "\n# 正文")
    tracked = (
        "最近交易日股价",
        "市值",
        "最新申报收入",
        "最新申报净利润",
        "经营现金流",
        "自由现金流",
        "滚动市盈率",
        "预期市盈率",
    )

    lines = [
        f"# {ticker.upper()} 快速复核报告",
        "",
        f"> 复核时间（UTC）：{datetime.now(UTC).isoformat()}",
        "",
        "## 核心结论",
        "",
    ]
    if not previous:
        lines.append("未找到上一份报告的系统核验数据表，建议重新运行完整研究。")
    else:
        old_period = (previous.get("最新申报收入") or {}).get("期间")
        new_period = (current.get("最新申报收入") or {}).get("期间")
        if old_period != new_period:
            lines.append(f"检测到新的财务申报期间：`{old_period}` → `{new_period}`。建议运行完整研究并重新估值。")
        else:
            lines.append("未检测到新的财务申报期间；本次仅属于数据和估值快速复核，不代表投资逻辑已经改变。")

    lines.extend([
        "",
        "## 关键数据变化",
        "",
        "| 指标 | 上次报告 | 当前数据 | 期间变化 |",
        "|---|---:|---:|---|",
    ])
    changed = 0
    for name in tracked:
        old = previous.get(name, {})
        new = current.get(name, {})
        old_display = f"{old.get('数值', '缺失')} {old.get('单位', '')}".strip()
        new_display = f"{new.get('数值', '缺失')} {new.get('单位', '')}".strip()
        period_changed = old.get("期间") != new.get("期间")
        value_changed = old_display != new_display
        if value_changed or period_changed:
            changed += 1
        lines.append(f"| {name} | {old_display} | {new_display} | {'是' if period_changed else '否'} |")

    scenarios = scenarios or DEFAULT_VALUATION_SCENARIOS
    data = snapshot.get("数据") or {}
    current_price = data.get("当前价格")
    current_eps = data.get("每股收益_TTM")
    current_acceptable = (
        calculate_acceptable_prices(current_eps, scenarios, required_return)
        if isinstance(current_eps, (int, float))
        else {}
    )
    lines.extend([
        "",
        "## 当前估值快速更新",
        "",
        build_valuation_scenarios(data, scenarios=scenarios, required_return=required_return),
        "",
        "## 观察价格状态",
        "",
    ])
    if isinstance(current_price, (int, float)) and current_acceptable:
        current_zone = valuation_zone(current_price, current_acceptable)
        previous_zone = (
            valuation_zone(reference_price, saved_acceptable_prices)
            if isinstance(reference_price, (int, float)) and saved_acceptable_prices
            else "未保存"
        )
        price_change = (
            (current_price / reference_price - 1) * 100
            if isinstance(reference_price, (int, float)) and reference_price
            else None
        )
        eps_change = (
            (current_eps / reference_eps - 1) * 100
            if isinstance(current_eps, (int, float)) and isinstance(reference_eps, (int, float)) and reference_eps
            else None
        )
        lines.extend([
            f"- 上次完整研究区间：**{previous_zone}**",
            f"- 当前区间：**{current_zone}**",
            f"- 当前股价相对完整研究时变化：{'数据不足' if price_change is None else f'{price_change:.2f}%'}",
            f"- 当前 TTM EPS 相对完整研究时变化：{'数据不足' if eps_change is None else f'{eps_change:.2f}%'}",
            f"- 当前观察价格：悲观 {current_acceptable.get('悲观', 0):.2f} 美元；"
            f"基准 {current_acceptable.get('基准', 0):.2f} 美元；乐观 {current_acceptable.get('乐观', 0):.2f} 美元。",
        ])
        if previous_zone != "未保存" and previous_zone != current_zone:
            lines.append("- **区间发生变化：**需要区分这是股价变化、EPS变化，还是两者共同造成；该变化触发估值复核，但不自动代表投资逻辑改变。")
        else:
            lines.append("- 条件估值区间没有变化。")
    else:
        lines.append("当前股价或 EPS 数据不足，无法更新观察价格区间。")
    lines.extend([
        "",
        "## 下一步",
        "",
        "- 出现新财报期间：重新运行完整混合模型研究，更新五年估值和持续跟踪清单。",
        "- 只有价格或估值倍数变化：重新查看反向估值，不据此直接改变长期判断。",
        "- 核心风险领先指标发生变化：在完整研究时重点验证风险是否兑现。",
        "",
        f"> 本次共有 {changed} 项数据或期间发生变化。快速复核不替代完整投资研究。",
    ])
    return "\n".join(lines)
