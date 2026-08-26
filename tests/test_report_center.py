from investment_os.reports.index import build_report_center


def test_report_center_lists_latest_and_recent_reports(tmp_path):
    generated = tmp_path / "generated"
    portfolio = tmp_path / "portfolio"
    generated.mkdir()
    portfolio.mkdir()
    (generated / "NVDA-最新.html").write_text("NVDA", encoding="utf-8")
    (portfolio / "组合综合复核-最新.html").write_text("组合", encoding="utf-8")
    (generated / "NVDA-历史.html").write_text("历史", encoding="utf-8")
    path = build_report_center(tmp_path)
    content = path.read_text(encoding="utf-8")
    assert "NVDA-最新" in content
    assert "组合综合复核-最新" in content
    assert "NVDA-历史" in content
    assert "%E7%BB%84%E5%90%88" in content
    assert 'id="search"' in content
    assert 'data-filter="组合报告"' in content
    assert 'data-filter="公司研究"' in content
    assert "显示 ${visible} / ${cards.length} 份" in content
    assert '<details id="history">' in content
    assert "历史报告（最近 1 份）" in content
    assert "if(query)history.open=true" in content
