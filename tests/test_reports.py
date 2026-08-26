from investment_os.reports.html import markdown_to_html
from investment_os.reports.markdown import (
    build_financial_trend_sections,
    build_trend_interpretation,
    build_valuation_scenarios,
    build_verified_data_table,
    replace_quantitative_sections,
    save_report,
)


def test_save_report(tmp_path):
    path = save_report("nvda", "## 摘要\n优质企业。", tmp_path)
    assert path.exists()
    assert path.read_text(encoding="utf-8").startswith("# NVDA 长期投资研究报告")
    assert path.with_suffix(".html").exists()
    assert (tmp_path / "NVDA-最新.html").exists()
    assert "NVDA 长期投资研究报告" in path.with_suffix(".html").read_text(encoding="utf-8")


def test_verified_data_table_uses_deterministic_units():
    table = build_verified_data_table({
        "缓存状态": "新数据",
        "数据获取时间_UTC": "2026-08-22T00:00:00+00:00",
        "数据": {
            "市值_十亿美元": 5200.733,
            "资产总额": 259_474_000_000,
            "负债总额": 64_000_000_000,
        },
    })
    assert "5200.733 | 十亿美元" in table
    assert "24.67 | %" in table


def test_quantitative_sections_are_replaced():
    snapshot = {"数据": {
        "最新申报收入_十亿美元": 81.615,
        "市值_十亿美元": 5200.733,
        "资产总额": 259_474_000_000,
        "负债总额": 64_000_000_000,
        "上年同期收入_十亿美元": 50.0,
        "收入同比增长率": 63.23,
        "年度财务趋势": [{
            "结束日": "2026-01-25",
            "收入": 130_000_000_000,
            "收入同比增长率": 25.0,
            "净利润": 70_000_000_000,
            "净利润同比增长率": 30.0,
            "自由现金流": 65_000_000_000,
            "自由现金流同比增长率": 28.0,
        }],
        "季度财务趋势": [{
            "结束日": "2026-04-26",
            "收入": 81_615_000_000,
            "收入同比增长率": 85.23,
            "净利润": 58_321_000_000,
            "净利润同比增长率": 210.63,
            "自由现金流": None,
            "自由现金流同比增长率": None,
        }],
    }}
    content = "## 财务质量\n错误数字\n\n## 估值分析\n错误市值\n\n## 主要风险\n风险"
    result = replace_quantitative_sections(content, snapshot)
    assert "错误数字" not in result
    assert "5.201 万亿美元" in result
    assert "24.67%" in result
    assert "816.15 亿美元" in result
    assert "| 财务指标 | 本期 | 上年同期 | 同比增长 |" in result
    assert "500.0 亿美元 | 63.23%" in result
    assert "| 总市值 | 5.201 万亿美元 | 约 52007.33 亿美元 |" in result
    assert "| 估值指标 | 数值 | 说明 |" in result
    assert "## 五年财务趋势" in result
    assert "| 2026-01-25 | 1300.00 | 25.00% | 700.00 | 30.00% | 650.00 | 28.00% |" in result
    assert "## 最近八个季度趋势" in result
    assert "| 2026-04-26 | 816.15 | 85.23% | 583.21 | 210.63% | — | — |" in result


def test_quantitative_sections_accept_numbered_and_level_one_headings():
    snapshot = {"数据": {}}
    numbered = "## 三、财务质量\n错误财务\n## 四、估值分析\n错误估值\n## 五、主要风险\n保留风险"
    level_one = "# 财务质量\n错误财务\n# 估值分析\n错误估值\n# 主要风险\n保留风险"

    for content in (numbered, level_one):
        result = replace_quantitative_sections(content, snapshot)
        assert "错误财务" not in result
        assert "错误估值" not in result
        assert "## 财务质量" in result
        assert "## 估值分析" in result
        assert "保留风险" in result


def test_market_cap_unit_is_corrected_outside_valuation_section():
    snapshot = {"数据": {"市值_十亿美元": 5200.733}}
    content = (
        "# 执行摘要\n市值为5,200.733亿美元。\n"
        "# 财务质量\n错误财务\n# 估值分析\n错误估值\n# 主要风险\n风险"
    )
    result = replace_quantitative_sections(content, snapshot)
    assert "5,200.733亿美元" not in result
    assert "52,007.33亿美元（约5.201万亿美元）" in result


def test_execution_summary_uses_deterministic_valuation_assumptions():
    snapshot = {"数据": {"当前价格": 100.0, "每股收益_TTM": 5.0}}
    content = (
        "# 执行摘要\n- 在五年目标回报率8%、终值市盈率20倍下，需要增长。\n"
        "# 公司与商业模式\n业务\n# 财务质量\n旧财务\n# 估值分析\n旧估值\n# 主要风险\n风险"
    )
    result = replace_quantitative_sections(content, snapshot, required_return=12.0)
    assert "目标回报率8%" not in result
    assert "程序估值口径" in result
    assert "要求五年年化回报 12.00%" in result
    assert "基准期末市盈率 25.00 倍" in result
    assert "年复合增长" in result


def test_deterministic_summary_accepts_decorated_heading():
    snapshot = {"数据": {"当前价格": 100.0, "每股收益_TTM": 5.0}}
    content = "# 第一部分：执行摘要（长期视角）\n原摘要\n# 财务质量\n旧\n# 估值分析\n旧\n# 主要风险\n风险"
    result = replace_quantitative_sections(content, snapshot)
    assert result.count("程序估值口径") == 1
    assert "第一部分：执行摘要（长期视角）" in result


def test_aligned_periods_remove_false_anomaly_and_conflicting_valuation():
    snapshot = {"数据": {
        "当前价格": 100.0,
        "每股收益_TTM": 5.0,
        "收入期间开始日": "2026-01-01",
        "收入报告期结束日": "2026-03-31",
        "净利润期间开始日": "2026-01-01",
        "净利润报告期结束日": "2026-03-31",
        "现金流期间开始日": "2026-01-01",
        "现金流期间结束日": "2026-03-31",
    }}
    content = (
        "# 执行摘要\n> 运行时数据存在明显口径异常和内部矛盾。\n"
        "估值模型显示，在12%目标回报率和第五年15倍终值市盈率下增长。\n"
        "# 财务质量\n旧\n# 估值分析\n旧\n# 主要风险\n风险"
    )
    result = replace_quantitative_sections(content, snapshot)
    assert "口径异常" not in result
    assert "15倍终值市盈率" not in result
    assert "程序估值口径" in result


def test_financial_trends_show_missing_data_explicitly():
    result = build_financial_trend_sections({})
    assert result.count("| 暂无可用数据 | — | — | — | — | — | — |") == 2


def test_missing_values_do_not_render_python_none():
    content = "## 财务质量\n旧\n## 估值分析\n旧\n## 主要风险\n风险"
    result = replace_quantitative_sections(content, {"数据": {}})
    assert "None 至 None" not in result
    assert "None%" not in result
    assert "| 股价 | 数据缺失 美元 |" in result


def test_trend_interpretation_is_calculated_from_verified_rows():
    result = build_trend_interpretation({
        "年度财务趋势": [
            {"结束日": "2026-01-25", "收入": 400.0, "净利润": 160.0},
            {"结束日": "2025-01-26", "收入": 300.0, "净利润": 100.0},
            {"结束日": "2024-01-28", "收入": 100.0, "净利润": 40.0},
        ],
        "季度财务趋势": [
            {"结束日": "2026-04-26", "收入": 200.0, "净利润": 80.0, "自由现金流": 60.0, "收入同比增长率": 50.0},
            {"结束日": "2026-01-25", "收入": 160.0, "净利润": 60.0, "自由现金流": 50.0, "收入同比增长率": 40.0},
            {"结束日": "2024-07-28", "收入": 100.0, "净利润": 30.0, "自由现金流": 20.0, "收入同比增长率": 20.0},
        ],
    })
    assert "营业收入复合年增长率约为 100.00%" in result
    assert "同比增速加快 10.00 个百分点" in result
    assert "最新季度净利率约为 40.00%" in result
    assert "自由现金流相当于净利润的 75.00%" in result


def test_trend_interpretation_does_not_compute_complex_profit_cagr():
    result = build_trend_interpretation({
        "年度财务趋势": [
            {"结束日": "2025-12-31", "收入": 200.0, "净利润": -10.0},
            {"结束日": "2024-12-31", "收入": 100.0, "净利润": 20.0},
        ],
        "季度财务趋势": [],
    })

    assert "j%" not in result
    assert "跨越盈亏平衡点" in result


def test_valuation_scenarios_are_reproducible():
    result = build_valuation_scenarios({
        "当前价格": 100.0,
        "每股收益_TTM": 5.0,
        "滚动市盈率": 20.0,
    })
    assert "TTM 每股收益 5.00 美元" in result
    assert "| 悲观 | 10% | 8.05 美元 | 18 倍 | 144.95 美元 | 7.71% |" in result
    assert "| 基准 | 20% | 12.44 美元 | 25 倍 | 311.04 美元 | 25.48% |" in result
    assert "### 反向估值：当前价格要求什么增长" in result
    assert "未来五年 EPS 需要实现约 **7.11%** 的年复合增长" in result
    assert "currentPE=20.00" in result
    assert "futurePE=25.00" in result
    assert "returnRate=12.00" in result
    assert "expectedGrowth=20.00" in result


def test_valuation_calculator_link_renders_as_clickable_html():
    markdown = build_valuation_scenarios({"当前价格": 78.0, "每股收益_TTM": 5.0, "滚动市盈率": 15.6})
    html = markdown_to_html(markdown, "估值测试")
    assert '<a href="../%E4%BA%94%E5%B9%B4' in html
    assert "currentPE=15.60" in html


def test_valuation_calculator_prefers_normalized_pe_when_available():
    result = build_valuation_scenarios({
        "当前价格": 78.0,
        "每股收益_TTM": 5.0,
        "滚动市盈率": 15.6,
        "规范化市盈率": 16.6,
    })
    assert "currentPE=16.60" in result
    assert "当前股价÷基准规范化市盈率的反推值" in result


def test_valuation_scenarios_can_infer_eps():
    result = build_valuation_scenarios({"当前价格": 100.0, "滚动市盈率": 20.0})
    assert "TTM 每股收益 5.00 美元" in result
    assert "当前股价÷滚动市盈率的反推值" in result


def test_valuation_scenarios_accept_custom_assumptions():
    result = build_valuation_scenarios(
        {"当前价格": 100.0, "每股收益_TTM": 5.0},
        (("悲观", 0.0, 10.0), ("基准", 5.0, 15.0), ("乐观", 10.0, 20.0)),
    )
    assert "| 悲观 | 0% | 5.00 美元 | 10 倍 | 50.00 美元 | -12.94% |" in result
    assert "| 乐观 | 10% | 8.05 美元 | 20 倍 | 161.05 美元 | 10.00% |" in result


def test_reverse_valuation_uses_required_return_and_base_exit_pe():
    result = build_valuation_scenarios(
        {"当前价格": 100.0, "每股收益_TTM": 5.0},
        (("悲观", 0.0, 10.0), ("基准", 5.0, 20.0), ("乐观", 10.0, 30.0)),
        required_return=10.0,
    )
    assert "要求未来五年获得 10.00% 的年化回报" in result
    assert "第五年末市盈率为 20.00 倍" in result
    assert "未来五年 EPS 需要实现约 **10.00%** 的年复合增长" in result
    assert "### 反向估值矩阵：所需五年 EPS 年复合增长" in result
    assert "| 要求年化回报率 / 第五年末市盈率 | 10 倍 | 20 倍 | 30 倍 |" in result
    assert "| 10% |" in result
    assert "| 15% |" in result
    assert "### 最高可接受买入价（基于情景假设）" in result
    assert "| 基准 | 5.00% | 20.00 倍 | 127.63 美元 | 79.25 美元 | 溢价 26.19% |" in result
    assert "### 条件估值位置" in result
    assert "需要偏乐观的增长与期末估值组合" in result


def test_model_generated_verified_table_is_removed():
    content = (
        "## 财务质量\n旧财务\n\n## 估值分析\n旧估值\n\n## 主要风险\n核心风险\n"
        "\n---\n\n# 数据表（已程序核验）\n\n| 错误数据 | 100 |\n\n---\n\n（全文完）"
    )
    result = replace_quantitative_sections(content, {"数据": {}})
    assert "核心风险" in result
    assert "错误数据" not in result
    assert "# 数据表（已程序核验）" not in result


def test_model_generated_reference_data_is_removed():
    content = "## 财务质量\n旧财务\n\n## 估值分析\n旧估值\n\n## 主要风险\n风险\n\n# 参考数据\n| 错误 | 100 |"
    result = replace_quantitative_sections(content, {"数据": {}})
    assert "## 主要风险\n风险" in result
    assert "# 参考数据" not in result
