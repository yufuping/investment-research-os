from investment_os.reports.html import markdown_to_html, save_html_report


def test_markdown_to_html_renders_chinese_table_and_escapes_input():
    markdown = "# 标题\n\n| 公司 | 权重 |\n|---|---:|\n| NVDA | 25% |\n\n> **提醒** <script>"
    html = markdown_to_html(markdown, "组合报告")
    assert '<html lang="zh-CN">' in html
    assert "<table>" in html
    assert "<td>NVDA</td>" in html
    assert "<strong>提醒</strong>" in html
    assert "&lt;script&gt;" in html
    assert "<script>alert(1)</script>" not in html


def test_html_adds_percentage_bars_and_risk_badges():
    markdown = "| 公司 | 组合权重 |\n|---|---:|\n| NVDA | 25.01% |\n\n| 级别 | 提醒 |\n|---|---|\n| 高 | 集中度 |"
    html = markdown_to_html(markdown, "组合报告")
    assert 'class="metric positive"' in html
    assert 'style="width:25.01%"' in html
    assert 'class="badge high">高</span>' in html


def test_html_adds_navigation_and_summary_cards():
    markdown = "# 组合报告\n\n## 汇总\n\n- 持仓总价值：1000 美元\n- 浮动收益：20%\n\n## 风险预警\n\n无"
    html = markdown_to_html(markdown, "组合报告")
    assert '<a href="#section-1">汇总</a>' in html
    assert '<a href="#section-2">风险预警</a>' in html
    assert '<h2 id="section-1">汇总</h2>' in html
    assert '<ul class="summary-cards">' in html


def test_html_inserts_navigation_only_once_with_multiple_h1_headings():
    markdown = "# 主报告\n\n## 摘要\n内容\n\n# 附录\n\n## 数据\n内容"
    html = markdown_to_html(markdown, "报告")
    assert html.count("<nav>") == 1
    assert html.count("快速导航") == 1


def test_html_adds_allocation_donut_only_for_position_weights():
    markdown = "| 公司 | 组合权重 |\n|---|---:|\n| NVDA | 60% |\n| AMZN | 40% |"
    html = markdown_to_html(markdown, "组合报告")
    assert 'class="donut"' in html
    assert "#2f6fed 0.00% 60.00%" in html
    assert "#23a48b 60.00% 100.00%" in html
    assert "核心个股组合权重" in html


def test_html_adds_trend_chart_for_multiple_snapshots():
    markdown = "| 复核时间（UTC） | 持仓总价值 | 前两大集中度 |\n|---|---:|---:|\n| 旧 | 1000.00 美元 | 50% |\n| 新 | 1200.00 美元 | 52% |"
    html = markdown_to_html(markdown, "组合报告")
    assert 'class="trend"' in html
    assert "<polyline" in html
    assert "最高 1,200 美元" in html


def test_html_links_only_companies_with_existing_reports():
    markdown = "| 公司 | 组合权重 |\n|---|---:|\n| NVDA | 60% |\n| TSM | 40% |"
    html = markdown_to_html(markdown, "组合报告", {"NVDA": "../generated/NVDA-%E6%9C%80%E6%96%B0.html"})
    assert 'class="company-link" href="../generated/NVDA-%E6%9C%80%E6%96%B0.html">NVDA</a>' in html
    assert '<td>TSM</td>' in html


def test_html_adds_optional_report_center_link():
    html = markdown_to_html("# 报告", "报告", home_link="../%E6%8A%A5%E5%91%8A%E4%B8%AD%E5%BF%83.html")
    assert "← 返回报告中心" in html
    assert 'href="../%E6%8A%A5%E5%91%8A%E4%B8%AD%E5%BF%83.html"' in html


def test_html_adds_safe_chatgpt_discussion_actions():
    html = markdown_to_html("# 报告\n<script>alert(1)</script>", "报告")
    assert "与 ChatGPT 讨论" in html
    assert "复制报告全文" in html
    assert 'window.open("https://chatgpt.com/"' in html
    assert "请阅读以下投资研究报告" in html
    assert "<script>alert(1)</script>" not in html


def test_saved_monitoring_html_auto_links_existing_company_report(tmp_path):
    reports = tmp_path / "reports"
    generated = reports / "generated"
    monitoring = reports / "monitoring"
    generated.mkdir(parents=True)
    monitoring.mkdir()
    (generated / "NVDA-最新.html").write_text("完整研报", encoding="utf-8")
    markdown = monitoring / "全部观察.md"
    markdown.write_text("| 公司 | 动作 |\n|---|---|\n| NVDA | 继续观察 |\n| TSM | 继续观察 |", encoding="utf-8")
    html_path = save_html_report(markdown, "全部观察")
    html = html_path.read_text(encoding="utf-8")
    assert 'href="../generated/NVDA-%E6%9C%80%E6%96%B0.html">NVDA</a>' in html
    assert "<td>TSM</td>" in html
