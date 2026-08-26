from investment_os.reports.watchlist import build_watchlist_summary


def test_watchlist_summary_counts_actions():
    report = build_watchlist_summary([
        {"ticker": "AAA", "price": "10 美元", "current_zone": "基准与乐观之间", "previous_zone": "悲观与基准之间", "new_filing": False, "action": "复核估值假设"},
        {"ticker": "BBB", "price": "20 美元", "current_zone": "悲观与基准之间", "previous_zone": "悲观与基准之间", "new_filing": True, "action": "运行完整研究"},
        {"ticker": "CCC", "price": "30 美元", "current_zone": "悲观与基准之间", "previous_zone": "悲观与基准之间", "new_filing": False, "action": "继续观察"},
    ])
    assert "需要完整研究：1 家" in report
    assert "需要复核估值假设：1 家" in report
    assert "继续观察：1 家" in report
