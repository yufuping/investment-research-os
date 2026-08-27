from pathlib import Path


def test_standalone_valuation_calculator_contains_required_inputs_and_formula():
    path = Path(__file__).parents[1] / "reports" / "五年隐含增长率计算器.html"
    html = path.read_text(encoding="utf-8")
    assert 'id="returnRate"' in html
    assert 'id="dividendYield"' in html
    assert 'id="currentPE"' in html
    assert 'id="futurePE"' in html
    assert 'id="expectedGrowth"' in html
    assert "((1+requiredReturn)/(1+dividendYield))*Math.pow(currentPE/futurePE,1/years)-1" in html
    assert "(1+expectedGrowth)*Math.pow(futurePE/currentPE,1/years)*(1+dividendYield)-1" in html
    assert "股息再投资贡献" in html
    assert "未来五年预期年化总回报" in html
    assert "五年后 PE 敏感性" in html
    assert "viewport" in html


def test_stock_return_calculator_is_a_stock_total_return_tool():
    path = Path(__file__).parents[1] / "reports" / "股票投资收益计算器.html"
    html = path.read_text(encoding="utf-8")
    for field in ("initialAmount", "buyPrice", "sellPrice", "years", "dividendYield"):
        assert f'id="{field}"' in html
    assert "股票投资收益计算器" in html
    assert "priceMultiple=sell/buy" in html
    assert "totalMultiple=priceMultiple*dividendMultiple" in html
    assert "年化总回报" in html
    assert "不是存款或债券利息" in html


def test_bigfish_trend_table_requires_operating_profit_growth_and_margin_check():
    path = Path(__file__).parents[1] / "skills" / "bigfish" / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    assert "五年经营趋势表硬性合同" in text
    assert "经营利润同比增长" in text
    assert "经营利润率 = 经营利润 ÷ 营业收入" in text
    assert "差异超过 0.2 个百分点" in text


def test_bigfish_trend_table_includes_net_profit_and_investment_income():
    path = Path(__file__).parents[1] / "skills" / "bigfish" / "references" / "methodology.md"
    text = path.read_text(encoding="utf-8")
    assert "净利润同比增长" in text
    assert "投资收益" in text
    assert "投资收益占净利润" in text
    assert "投资收益与净利润质量" in text


def test_bigfish_return_attribution_has_gaap_and_normalized_bridges():
    path = Path(__file__).parents[1] / "skills" / "bigfish" / "references" / "return-attribution.md"
    text = path.read_text(encoding="utf-8")
    assert "规范化分析法" in text
    assert "GAAP/报告口径分析法" in text
    assert "规范化总回报倍数" in text
    assert "报告口径总回报倍数" in text
