import json
from datetime import UTC, datetime

from investment_os.database.repository import ResearchRepository
from investment_os.tools.market import CACHE_SCHEMA_VERSION, configure_market_data, prepare_market_snapshot


def test_research_run_lifecycle(tmp_path):
    repository = ResearchRepository(tmp_path / "test.db")
    run_id = repository.start_run("NVDA", "test question")
    repository.complete_run(run_id, "report", "report.md")
    assert run_id == 1
    runs = repository.get_completed_runs("nvda")
    assert len(runs) == 1
    assert runs[0].report == "report"


def test_completed_runs_are_newest_first(tmp_path):
    repository = ResearchRepository(tmp_path / "test.db")
    first = repository.start_run("NVDA", "first")
    repository.complete_run(first, "older", "older.md")
    second = repository.start_run("NVDA", "second")
    repository.complete_run(second, "newer", "newer.md")
    assert [run.report for run in repository.get_completed_runs("NVDA")] == ["newer", "older"]


def test_valuation_watch_is_saved_and_updated(tmp_path):
    repository = ResearchRepository(tmp_path / "test.db")
    repository.save_valuation_watch("nvda", 12.0, '[["基准", 20, 25]]', '{"基准": 200}', 180.0, 6.0)
    watch = repository.get_valuation_watch("NVDA")
    assert watch is not None
    assert watch.required_return == 12.0
    assert watch.reference_price == 180.0
    repository.save_valuation_watch("NVDA", 15.0, '[["基准", 15, 20]]', '{"基准": 150}', 170.0, 6.5)
    assert repository.get_valuation_watch("NVDA").required_return == 15.0
    assert [watch.ticker for watch in repository.list_valuation_watches()] == ["NVDA"]


def test_portfolio_position_lifecycle(tmp_path):
    repository = ResearchRepository(tmp_path / "test.db")
    repository.save_position("nvda", 10.0, 150.0)
    position = repository.list_positions()[0]
    assert position.ticker == "NVDA"
    assert position.shares == 10.0
    repository.save_position("NVDA", 12.0, 155.0)
    assert repository.list_positions()[0].shares == 12.0
    assert repository.delete_position("NVDA")
    assert repository.list_positions() == []
    repository.save_reference_price("NVDA", 200.0, "测试截图", "2026-08-20")
    reference = repository.get_reference_price("nvda")
    assert reference.price == 200.0
    assert reference.source == "测试截图"
    assert reference.observed_date == "2026-08-20"
    repository.replace_position_tags("NVDA", ["AI", "半导体", "AI"])
    assert repository.get_position_tags("nvda") == ["AI", "半导体"]
    snapshot_id = repository.save_portfolio_snapshot(100.0, 120.0, 80.0, "{}")
    assert snapshot_id == 1
    assert repository.list_portfolio_snapshots()[0].total_value == 120.0


def test_snapshot_deduplication_ignores_identical_refresh(tmp_path):
    repository = ResearchRepository(tmp_path / "test.db")
    positions = '{"AAA":{"shares":10,"price":100,"weight":100}}'
    first = repository.save_portfolio_snapshot_if_changed(800.0, 1000.0, 100.0, positions)
    duplicate = repository.save_portfolio_snapshot_if_changed(800.0, 1000.0, 100.0, positions)
    changed = repository.save_portfolio_snapshot_if_changed(800.0, 1010.0, 100.0, '{"AAA":{"shares":10,"price":101,"weight":100}}')
    assert first == 1
    assert duplicate is None
    assert changed == 2
    assert len(repository.list_portfolio_snapshots()) == 2


def test_trade_updates_weighted_cost_and_realized_pnl(tmp_path):
    repository = ResearchRepository(tmp_path / "test.db")
    repository.save_position("AAA", 10.0, 100.0)
    repository.record_trade("AAA", "buy", 10.0, 120.0, fee=10.0)
    position = repository.list_positions()[0]
    assert position.shares == 20.0
    assert position.cost_per_share == 110.5
    repository.record_trade("AAA", "sell", 5.0, 130.0, fee=2.0)
    transaction = repository.list_transactions()[0]
    assert transaction.realized_pnl == 95.5
    assert repository.list_positions()[0].shares == 15.0


def test_investment_decision_journal(tmp_path):
    repository = ResearchRepository(tmp_path / "test.db")
    decision_id = repository.save_decision(
        "nvda", "持有", "AI利润池继续扩大", reference_price=200.0,
        valuation_basis="五年反向估值", invalidation_condition="份额与利润率同时下降", next_check="下季财报",
    )
    assert decision_id == 1
    decision = repository.list_decisions("NVDA")[0]
    assert decision.action == "持有"
    assert decision.reference_price == 200.0


def test_market_snapshot_uses_fresh_sqlite_cache(tmp_path):
    repository = ResearchRepository(tmp_path / "test.db")
    repository.save_market_cache(
        ticker="NVDA",
        payload=json.dumps({"公司名称": "NVIDIA Corporation", "缓存架构版本": CACHE_SCHEMA_VERSION}, ensure_ascii=False),
        source="测试数据源",
        retrieved_at=datetime.now(UTC),
    )
    configure_market_data(repository)

    snapshot = prepare_market_snapshot("nvda")

    assert snapshot["缓存状态"] == "有效缓存"
    assert snapshot["数据"]["公司名称"] == "NVIDIA Corporation"
