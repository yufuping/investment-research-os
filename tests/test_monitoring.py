from investment_os.reports.monitoring import build_monitoring_report, parse_verified_table, valuation_zone


def test_parse_verified_table():
    report = """## 系统核验数据表
| 指标 | 数值 | 单位 | 数据期间/日期 |
|---|---:|---|---|
| 最近交易日股价 | 100 | 美元 | 2026-01-01 |
| 最新申报收入 | 10 | 十亿美元 | 2025-01-01 至 2025-03-31 |
# 执行摘要
"""
    rows = parse_verified_table(report)
    assert rows["最近交易日股价"]["数值"] == "100"
    assert rows["最新申报收入"]["期间"] == "2025-01-01 至 2025-03-31"


def test_monitoring_report_detects_new_financial_period():
    previous = """## 系统核验数据表
| 指标 | 数值 | 单位 | 数据期间/日期 |
|---|---:|---|---|
| 最新申报收入 | 10 | 十亿美元 | 旧期间 |
# 执行摘要
"""
    snapshot = {"数据": {
        "最新申报收入_十亿美元": 12,
        "收入期间开始日": "新",
        "收入报告期结束日": "期间",
        "当前价格": 100.0,
        "每股收益_TTM": 5.0,
    }}
    report = build_monitoring_report("NVDA", previous, snapshot)
    assert "检测到新的财务申报期间" in report
    assert "建议运行完整研究并重新估值" in report
    assert "## 当前估值快速更新" in report
    assert "### 反向估值矩阵" in report
    assert "### 最高可接受买入价" in report


def test_valuation_zone_classifies_scenario_band():
    prices = {"悲观": 100.0, "基准": 200.0, "乐观": 300.0}
    assert valuation_zone(90.0, prices) == "不高于悲观情景"
    assert valuation_zone(150.0, prices) == "悲观与基准之间"
    assert valuation_zone(250.0, prices) == "基准与乐观之间"
    assert valuation_zone(350.0, prices) == "高于乐观情景"
