import pytest

from investment_os.app import mcp_server
from investment_os.tools.valuation import calculate_cagr, calculate_expected_return, calculate_required_profit_growth, scenario_analysis


def test_cagr_uses_actual_interval_count():
    result = calculate_cagr(100, 146.41, 4)
    assert result["cagr_pct"] == pytest.approx(10.0)


def test_cagr_rejects_loss_or_zero_crossing():
    with pytest.raises(ValueError, match="CAGR 无意义"):
        calculate_cagr(-10, 20, 5)


def test_catl_example_requires_about_18_5_percent_growth():
    result = calculate_required_profit_growth(
        current_pe=21,
        terminal_pe=15,
        target_return_pct=13,
        dividend_yield_pct=2,
        years=5,
    )
    assert result["required_profit_growth_pct"] == pytest.approx(18.49, abs=0.02)


def test_forward_return_inverts_reverse_valuation():
    required = calculate_required_profit_growth(21, 15, 13, 2, 5)
    result = calculate_expected_return(required["required_profit_growth_pct"], 21, 15, 2, 5)
    assert result["expected_annual_return_pct"] == pytest.approx(13.0)


def test_scenarios_show_target_result():
    result = scenario_analysis(
        30,
        [
            {"name": "悲观", "profit_growth_pct": 8, "terminal_pe": 18},
            {"name": "基准", "profit_growth_pct": 20, "terminal_pe": 25},
        ],
        target_return_pct=13,
    )
    assert result["scenarios"][0]["meets_target"] is False
    assert result["scenarios"][1]["meets_target"] is True
    assert result["all_scenarios_meet_target"] is False


def test_mcp_calculation_wrapper_uses_default_bigfish_horizon():
    result = mcp_server.calculate_required_profit_growth(21, 15, dividend_yield_pct=2)
    assert result["years"] == 5
    assert result["target_return_pct"] == 13.0
