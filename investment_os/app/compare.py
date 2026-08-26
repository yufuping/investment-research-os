import argparse
from datetime import UTC, datetime
from pathlib import Path

from agents import Runner, set_default_openai_key

from investment_os.agents.comparison import build_comparison_agent, build_comparison_prompt
from investment_os.app.config import get_settings
from investment_os.database.repository import ResearchRepository
from investment_os.reports.html import save_html_report
from investment_os.reports.index import build_report_center


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="比较同一家公司最近两次投资研究")
    parser.add_argument("ticker", help="股票代码，例如 NVDA")
    return parser.parse_args()


def save_comparison(ticker: str, content: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"{ticker.upper()}-变化报告-{timestamp}.md"
    path.write_text(f"# {ticker.upper()} 投资研究变化报告\n\n{content.strip()}\n", encoding="utf-8")
    save_html_report(path, f"{ticker.upper()} 投资研究变化报告", f"{ticker.upper()}-变化报告-最新.html")
    build_report_center(output_dir.parent)
    return path


def load_complete_report(run) -> str:
    """优先读取包含系统核验表的最终报告文件。"""
    if run.report_path:
        path = Path(run.report_path)
        if path.is_file():
            return path.read_text(encoding="utf-8")
    return run.report or ""


def main() -> None:
    args = parse_args()
    ticker = args.ticker.upper().strip()
    settings = get_settings()
    repository = ResearchRepository(settings.absolute_path(settings.database_path))
    runs = repository.get_completed_runs(ticker, limit=2)
    if len(runs) < 2:
        raise SystemExit(f"{ticker} 目前只有 {len(runs)} 份已完成研究；至少需要两份才能比较。请先再次生成报告。")

    newer, older = runs[0], runs[1]
    set_default_openai_key(settings.openai_api_key)
    prompt = build_comparison_prompt(
        ticker=ticker,
        older_report=load_complete_report(older),
        newer_report=load_complete_report(newer),
        older_date=str(older.completed_at),
        newer_date=str(newer.completed_at),
    )
    result = Runner.run_sync(build_comparison_agent(settings.openai_model), prompt)
    output_dir = settings.absolute_path(settings.reports_path).parent / "comparisons"
    path = save_comparison(ticker, str(result.final_output), output_dir)
    print(result.final_output)
    print(f"\n变化报告已保存：{path}")
    print(f"浏览器版本：{path.with_suffix('.html')}")


if __name__ == "__main__":
    main()
