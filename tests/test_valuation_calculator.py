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
