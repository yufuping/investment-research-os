from types import SimpleNamespace
from datetime import UTC, datetime

from investment_os.app.portfolio import choose_portfolio_price, load_risk_scenarios
from investment_os.reports.portfolio import build_decision_journal, build_portfolio_history, build_portfolio_report, build_portfolio_review, build_risk_suite_report, build_scenario_report, build_stress_test_report, build_transaction_report, portfolio_snapshot_values


def test_portfolio_report_calculates_return_and_weight():
    report = build_portfolio_report([
        {"ticker": "AAA", "shares": 10.0, "cost_per_share": 80.0, "current_price": 100.0, "price_source": "市场数据", "price_date": "2026-08-23", "price_is_stale": False, "cost_value": 800.0, "market_value": 1000.0, "risk_tags": ["共同风险"], "has_research": True},
        {"ticker": "BBB", "shares": 20.0, "cost_per_share": 40.0, "current_price": 50.0, "price_source": "用户截图", "price_date": "2026-08-20", "price_is_stale": True, "cost_value": 800.0, "market_value": 1000.0, "risk_tags": ["共同风险", "其他风险"], "has_research": False},
    ])
    assert "200.00 美元（25.00%）" in report
    assert report.count("| 50.00% |") >= 2
    assert "当前持仓总价值：2000.00 美元" in report
    assert "用户截图" in report
    assert "前两大持仓集中度：100.00%" in report
    assert "| 共同风险 | AAA、BBB | 100.00% |" in report
    assert "已有完整研究覆盖：50.00%" in report
    assert "| 1 | BBB | 50.00% | 尚无完整研究 |" in report
    assert "过期或日期缺失的价格：1 项" in report
    assert "BBB 使用的价格已过期" in report
    assert "## 组合风险预警" in report
    assert "前两大持仓 AAA、BBB 合计 100.00%" in report
    assert "共同风险 暴露 100.00%" in report
    assert "1 项价格过期或日期缺失" in report


def test_portfolio_snapshot_and_history():
    rows = [
        {"ticker": "AAA", "shares": 10.0, "current_price": 100.0, "cost_value": 800.0, "market_value": 1000.0},
        {"ticker": "BBB", "shares": 5.0, "current_price": 100.0, "cost_value": 400.0, "market_value": 500.0},
    ]
    values = portfolio_snapshot_values(rows)
    assert values["total_value"] == 1500.0
    assert values["top_two_weight"] == 100.0
    snapshots = [
        SimpleNamespace(created_at="新", total_cost=1200.0, total_value=1600.0, top_two_weight=90.0, positions_json='{"AAA":{"shares":12,"price":110,"weight":82.5}}'),
        SimpleNamespace(created_at="旧", total_cost=1200.0, total_value=1500.0, top_two_weight=100.0, positions_json='{"AAA":{"shares":10,"price":100,"weight":66.67}}'),
    ]
    history = build_portfolio_history(snapshots)
    assert "组合持仓总价值变化：100.00 美元" in history
    assert "前两大集中度变化：-10.00 个百分点" in history
    assert "主动调整＋价格变化" in history
    assert "+200.00 美元" in history
    assert "+100.00 美元" in history
    assert "+20.00 美元" in history


def test_theme_stress_test_only_shocks_tagged_positions():
    rows = [
        {"ticker": "AAA", "market_value": 600.0, "risk_tags": ["AI周期"]},
        {"ticker": "BBB", "market_value": 400.0, "risk_tags": ["其他"]},
    ]
    report = build_stress_test_report(rows, "AI周期", -25.0)
    assert "该主题当前暴露：60.00%" in report
    assert "组合持仓总价值：1000.00 → 850.00 美元" in report
    assert "组合影响：-150.00 美元（-15.00%）" in report
    assert "| BBB | 400.00 美元 | -25.00%（不适用） | 400.00 美元 | +0.00 美元 | 0.00% |" in report
    assert "| AAA | 600.00 美元 | -25.00% | 450.00 美元 | -150.00 美元 | 100.00% |" in report


def test_multi_factor_scenario_uses_worst_overlap_once():
    rows = [
        {"ticker": "AAA", "market_value": 600.0, "risk_tags": ["AI周期", "科技股"]},
        {"ticker": "BBB", "market_value": 400.0, "risk_tags": ["科技股"]},
    ]
    report = build_scenario_report(rows, "联合冲击", {"AI周期": -30.0, "科技股": -20.0})
    assert "AI周期(-30.0%)、科技股(-20.0%)" in report
    assert "AI周期 -30.00%" in report
    assert "组合持仓总价值：1000.00 → 740.00 美元" in report
    assert "组合影响：-260.00 美元（-26.00%）" in report
    assert "最大损失来源：AAA" in report
    assert "-180.00 美元 | 69.23% |" in report


def test_newer_user_reference_price_wins_over_older_market_close():
    reference = SimpleNamespace(price=215.38, source="用户截图", observed_date="2026-08-23", updated_at=datetime(2026, 8, 24, tzinfo=UTC))
    chosen = choose_portfolio_price(214.72, "2026-08-21", reference, datetime(2026, 8, 23, 12, tzinfo=UTC))
    assert chosen == (215.38, "用户截图", "2026-08-23", False)


def test_same_day_market_price_wins_over_reference():
    reference = SimpleNamespace(price=215.38, source="用户截图", observed_date="2026-08-23", updated_at=datetime(2026, 8, 23, tzinfo=UTC))
    chosen = choose_portfolio_price(216.0, "2026-08-23", reference, datetime(2026, 8, 23, 12, tzinfo=UTC))
    assert chosen == (216.0, "市场数据", "2026-08-23", False)


def test_risk_suite_identifies_worst_scenario():
    rows = [
        {"ticker": "AAA", "market_value": 600.0, "risk_tags": ["AI"]},
        {"ticker": "BBB", "market_value": 400.0, "risk_tags": ["中国"]},
    ]
    report = build_risk_suite_report(rows, {"AI降温": {"AI": -30.0}, "中国风险": {"中国": -20.0}})
    assert "| AI降温 | AI -30% | -180.00 美元 | -18.00% | AAA |" in report
    assert "影响最大的预设情景：AI降温" in report


def test_load_risk_scenarios_from_json(tmp_path):
    path = tmp_path / "scenarios.json"
    path.write_text('{"测试情景":{"共同风险":-25}}', encoding="utf-8")
    assert load_risk_scenarios(path) == {"测试情景": {"共同风险": -25.0}}


def test_load_risk_scenarios_rejects_invalid_shock(tmp_path):
    path = tmp_path / "scenarios.json"
    path.write_text('{"错误情景":{"共同风险":-100}}', encoding="utf-8")
    try:
        load_risk_scenarios(path)
    except ValueError as exc:
        assert "无效主题或跌幅" in str(exc)
    else:
        raise AssertionError("无效跌幅应被拒绝")


def test_comprehensive_review_combines_overview_and_scenarios():
    rows = [{
        "ticker": "AAA", "shares": 10.0, "cost_per_share": 80.0, "current_price": 100.0,
        "price_source": "市场数据", "price_date": "2026-08-23", "price_is_stale": False,
        "cost_value": 800.0, "market_value": 1000.0, "risk_tags": ["共同风险"], "has_research": True,
    }]
    report = build_portfolio_review(rows, {"测试情景": {"共同风险": -20.0}})
    assert report.startswith("# 投资组合综合复核")
    assert "## 投资组合概览" in report
    assert "## 组合风险预警" in report
    assert "## 组合风险情景组" in report
    assert "## 历史趋势" in report
    assert "尚无上次复核快照" in report
    assert "| 测试情景 | 共同风险 -20% | -200.00 美元 | -20.00% | AAA |" in report


def test_comprehensive_review_compares_previous_snapshot():
    rows = [{
        "ticker": "AAA", "shares": 11.0, "cost_per_share": 80.0, "current_price": 110.0,
        "price_source": "市场数据", "price_date": "2026-08-23", "price_is_stale": False,
        "cost_value": 880.0, "market_value": 1210.0, "risk_tags": [], "has_research": True,
    }]
    previous = SimpleNamespace(
        created_at="上次", total_value=1000.0, top_two_weight=100.0,
        positions_json='{"AAA":{"shares":10,"price":100,"market_value":1000,"weight":100}}',
    )
    report = build_portfolio_review(rows, {"测试": {"其他": -20.0}}, previous_snapshot=previous)
    assert "组合持仓总价值变化：+210.00 美元（+21.00%）" in report
    assert "| AAA | +1.0000 | +10.00 美元 | +0.00 个百分点 |" in report


def test_review_hides_unchanged_position_rows():
    rows = [{
        "ticker": "AAA", "shares": 10.0, "cost_per_share": 80.0, "current_price": 100.0,
        "price_source": "市场数据", "price_date": "2026-08-23", "price_is_stale": False,
        "cost_value": 800.0, "market_value": 1000.0, "risk_tags": [], "has_research": True,
    }]
    previous = SimpleNamespace(
        created_at="上次", total_value=1000.0, top_two_weight=100.0,
        positions_json='{"AAA":{"shares":10,"price":100,"market_value":1000,"weight":100}}',
    )
    report = build_portfolio_review(rows, {"测试": {"其他": -20.0}}, previous_snapshot=previous)
    assert "没有达到显示精度的持仓、价格或权重变化" in report
    comparison = report.split("## 与上次复核对比", 1)[1].split("---", 1)[0]
    assert "| AAA |" not in comparison


def test_transaction_report_sums_realized_pnl():
    transactions = [
        SimpleNamespace(created_at="时间", ticker="AAA", transaction_type="buy", shares=10.0, price=100.0, fee=1.0, realized_pnl=None, note=""),
        SimpleNamespace(created_at="时间", ticker="AAA", transaction_type="sell", shares=2.0, price=120.0, fee=1.0, realized_pnl=39.0, note="减仓"),
    ]
    report = build_transaction_report(transactions)
    assert "累计已实现盈亏：39.00 美元" in report
    assert "| AAA | 卖出 |" in report


def test_decision_journal_preserves_reason_and_invalidation():
    decisions = [SimpleNamespace(
        created_at="时间", ticker="AAA", action="持有", reference_price=100.0,
        thesis="护城河仍然有效", valuation_basis="反向估值", invalidation_condition="份额持续下降", next_check="下季财报",
    )]
    report = build_decision_journal(decisions)
    assert "护城河仍然有效" in report
    assert "份额持续下降" in report
    assert "下季财报" in report
