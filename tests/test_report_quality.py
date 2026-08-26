from investment_os.reports.quality import audit_report


GOOD_REPORT = """
# 执行摘要
程序估值口径：统一假设。安全边际需要验证。
# 公司与商业模式
https://www.sec.gov/Archives/edgar/data/1/report.htm
## 财务质量
## 估值分析
不能据此声称存在安全边际。
# 主要风险
终端市场、公司份额和利润率需要分别分析。传导路径与领先指标如下。
# 乐观/基准/悲观情景
# 投资结论
# 投资逻辑失效条件
# 持续跟踪清单
## 季度观察
## 年度重估
## 立即复核触发器
# 数据缺口
"""


def test_good_report_passes_quality_gate():
    result = audit_report(GOOD_REPORT, {"数据": {"市值_十亿美元": 5200.733}})
    assert result.passed
    assert result.score == 100


def test_quality_gate_rejects_runtime_date_denial_and_wrong_market_cap_unit():
    bad = GOOD_REPORT.replace("# 执行摘要", "# 执行摘要\n数据属于当前不可验证的未来日期。市值5,200.733亿美元。")
    result = audit_report(bad, {"数据": {"市值_十亿美元": 5200.733}})
    assert not result.passed
    assert len(result.errors) == 2


def test_quality_gate_reports_missing_sections():
    result = audit_report("# 执行摘要", {"数据": {}})
    assert not result.passed
    assert "缺少必需章节" in result.errors[0]


def test_quality_gate_rejects_complex_cagr():
    result = audit_report(GOOD_REPORT + "\n净利润 CAGR 为 -100.00+50.97j%。", {"数据": {}})
    assert not result.passed
    assert any("复数增长率" in error for error in result.errors)


def test_quality_gate_rejects_mixed_periods_and_undisclosed_derived_cash_flow():
    snapshot = {"数据": {
        "收入期间开始日": "2026-04-01",
        "收入报告期结束日": "2026-06-30",
        "净利润期间开始日": "2026-04-01",
        "净利润报告期结束日": "2026-06-30",
        "现金流期间开始日": "2026-01-01",
        "现金流期间结束日": "2026-06-30",
        "经营现金流口径": "单季度派生（累计值相减）",
    }}
    result = audit_report(GOOD_REPORT, snapshot)
    assert not result.passed
    assert any("期间不一致" in error for error in result.errors)
    assert any("未披露" in error for error in result.errors)
