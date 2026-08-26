from investment_os.agents.comparison import build_comparison_prompt, extract_verified_table
from types import SimpleNamespace

from investment_os.app.compare import load_complete_report, save_comparison


def test_comparison_prompt_labels_old_and_new_reports():
    prompt = build_comparison_prompt("NVDA", "旧内容", "新内容", "旧日期", "新日期")
    assert "<旧报告>\n旧内容\n</旧报告>" in prompt
    assert "<新报告>\n新内容\n</新报告>" in prompt
    assert "旧报告完成时间：旧日期" in prompt


def test_extract_verified_table():
    report = "# 报告\n\n## 系统核验数据表\n\n| 指标 | 数值 |\n|---|---:|\n| 市值 | 10 |\n\n## 执行摘要\n正文"
    table = extract_verified_table(report)
    assert "| 市值 | 10 |" in table
    assert "执行摘要" not in table


def test_prompt_makes_verified_tables_the_only_numeric_source():
    report = "## 系统核验数据表\n| 指标 | 数值 |\n|---|---:|\n| 收入 | 1 |\n\n## 正文\n内容"
    prompt = build_comparison_prompt("NVDA", report, report, "旧", "新")
    assert "以下两张表是数字比较的唯一依据" in prompt
    assert "<旧报告核验表>\n| 指标 | 数值 |" in prompt
    assert "<新报告核验表>\n| 指标 | 数值 |" in prompt


def test_save_comparison(tmp_path):
    path = save_comparison("nvda", "## 执行摘要\n发生变化。", tmp_path)
    assert path.exists()
    assert path.read_text(encoding="utf-8").startswith("# NVDA 投资研究变化报告")


def test_complete_report_prefers_final_markdown_file(tmp_path):
    report_path = tmp_path / "report.md"
    report_path.write_text("包含系统核验数据表", encoding="utf-8")
    run = SimpleNamespace(report_path=str(report_path), report="数据库中的正文")
    assert load_complete_report(run) == "包含系统核验数据表"


def test_complete_report_falls_back_to_database():
    run = SimpleNamespace(report_path="missing.md", report="数据库中的正文")
    assert load_complete_report(run) == "数据库中的正文"
