from __future__ import annotations

from typing import Iterable


def calculate_cagr(begin_value: float, end_value: float, years: float) -> dict[str, float]:
    """计算只适用于正数起点和终点的复合年增长率。"""
    if begin_value <= 0 or end_value <= 0:
        raise ValueError("计算 CAGR 时，期初值和期末值必须都大于 0；跨越盈亏平衡点时 CAGR 无意义。")
    if years <= 0:
        raise ValueError("年数必须大于 0。")
    rate = (end_value / begin_value) ** (1 / years) - 1
    return {
        "begin_value": begin_value,
        "end_value": end_value,
        "years": years,
        "cagr_pct": rate * 100,
    }


def calculate_required_profit_growth(
    current_pe: float,
    terminal_pe: float,
    target_return_pct: float = 13.0,
    dividend_yield_pct: float = 0.0,
    years: int = 5,
) -> dict[str, float | str]:
    """根据 Bigfish 简化反向估值公式计算所需利润年增长率。"""
    _validate_valuation_inputs(current_pe, terminal_pe, target_return_pct, dividend_yield_pct, years)
    target_return = target_return_pct / 100
    dividend_yield = dividend_yield_pct / 100
    required_growth = (((1 + target_return) / (1 + dividend_yield)) ** years * current_pe / terminal_pe) ** (1 / years) - 1
    return {
        "years": years,
        "current_pe": current_pe,
        "terminal_pe": terminal_pe,
        "target_return_pct": target_return_pct,
        "dividend_yield_pct": dividend_yield_pct,
        "required_profit_growth_pct": required_growth * 100,
        "method": "股息作为年化总回报贡献的简化反向估值",
    }


def calculate_expected_return(
    profit_growth_pct: float,
    current_pe: float,
    terminal_pe: float,
    dividend_yield_pct: float = 0.0,
    years: int = 5,
) -> dict[str, float | str]:
    """计算给定利润增长及 P/E 回归后的简化年化总回报。"""
    _validate_valuation_inputs(current_pe, terminal_pe, 0, dividend_yield_pct, years)
    price_return_factor = (1 + profit_growth_pct / 100) * (terminal_pe / current_pe) ** (1 / years)
    annual_total_return = price_return_factor * (1 + dividend_yield_pct / 100) - 1
    return {
        "years": years,
        "profit_growth_pct": profit_growth_pct,
        "current_pe": current_pe,
        "terminal_pe": terminal_pe,
        "dividend_yield_pct": dividend_yield_pct,
        "expected_annual_return_pct": annual_total_return * 100,
        "five_year_price_multiple": (1 + profit_growth_pct / 100) ** years * terminal_pe / current_pe,
        "method": "利润增长、P/E变化与股息贡献的简化模型",
    }


def scenario_analysis(
    current_pe: float,
    scenarios: Iterable[dict[str, float | str]],
    *,
    dividend_yield_pct: float = 0.0,
    years: int = 5,
    target_return_pct: float = 13.0,
) -> dict[str, object]:
    rows = []
    for scenario in scenarios:
        name = str(scenario.get("name", "未命名情景")).strip() or "未命名情景"
        growth = float(scenario["profit_growth_pct"])
        terminal_pe = float(scenario["terminal_pe"])
        result = calculate_expected_return(growth, current_pe, terminal_pe, dividend_yield_pct, years)
        expected_return = float(result["expected_annual_return_pct"])
        rows.append({"name": name, **result, "meets_target": expected_return >= target_return_pct})
    if not rows:
        raise ValueError("至少需要一个估值情景。")
    return {
        "target_return_pct": target_return_pct,
        "years": years,
        "scenarios": rows,
        "all_scenarios_meet_target": all(bool(row["meets_target"]) for row in rows),
    }


def _validate_valuation_inputs(current_pe: float, terminal_pe: float, target_return_pct: float, dividend_yield_pct: float, years: int) -> None:
    if current_pe <= 0 or terminal_pe <= 0:
        raise ValueError("当前 P/E 和期末 P/E 必须大于 0。")
    if years <= 0 or years > 50:
        raise ValueError("估值年数必须在 1 到 50 年之间。")
    if target_return_pct <= -100:
        raise ValueError("要求回报率必须大于 -100%。")
    if dividend_yield_pct <= -100:
        raise ValueError("股息率必须大于 -100%。")
