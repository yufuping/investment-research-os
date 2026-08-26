import argparse
from datetime import UTC, datetime
import json
from pathlib import Path

from investment_os.app.compare import load_complete_report
from investment_os.app.config import get_settings
from investment_os.database.repository import ResearchRepository
from investment_os.reports.markdown import DEFAULT_VALUATION_SCENARIOS, calculate_acceptable_prices
from investment_os.reports.monitoring import build_monitoring_report
from investment_os.reports.html import save_html_report
from investment_os.reports.index import build_report_center
from investment_os.tools.market import configure_market_data, prepare_market_snapshot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="快速复核最新市场和财务数据，不调用大模型")
    parser.add_argument("ticker", help="股票代码，例如 NVDA")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ticker = args.ticker.upper().strip()
    settings = get_settings()
    repository = ResearchRepository(settings.absolute_path(settings.database_path))
    configure_market_data(
        repository,
        fmp_api_key=settings.fmp_api_key,
        alpha_vantage_api_key=settings.alpha_vantage_api_key,
        sec_user_agent=settings.sec_user_agent,
    )
    runs = repository.get_completed_runs(ticker, limit=1)
    if not runs:
        raise SystemExit(f"{ticker} 尚无完整研究报告，请先运行完整分析。")

    snapshot = prepare_market_snapshot(ticker)
    watch = repository.get_valuation_watch(ticker)
    if watch is None:
        data = snapshot.get("数据") or {}
        eps = data.get("每股收益_TTM")
        acceptable = calculate_acceptable_prices(eps, DEFAULT_VALUATION_SCENARIOS) if isinstance(eps, (int, float)) else {}
        repository.save_valuation_watch(
            ticker=ticker,
            required_return=12.0,
            scenarios_json=json.dumps(DEFAULT_VALUATION_SCENARIOS, ensure_ascii=False),
            acceptable_prices_json=json.dumps(acceptable, ensure_ascii=False),
            reference_price=data.get("当前价格"),
            reference_eps=eps,
        )
        watch = repository.get_valuation_watch(ticker)
    report = build_monitoring_report(
        ticker,
        load_complete_report(runs[0]),
        snapshot,
        scenarios=json.loads(watch.scenarios_json) if watch else None,
        required_return=watch.required_return if watch else 12.0,
        saved_acceptable_prices=json.loads(watch.acceptable_prices_json) if watch else None,
        reference_price=watch.reference_price if watch else None,
        reference_eps=watch.reference_eps if watch else None,
    )
    output_dir = settings.absolute_path(Path("reports/monitoring"))
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"{ticker}-快速复核-{timestamp}.md"
    path.write_text(report + "\n", encoding="utf-8")
    save_html_report(path, f"{ticker} 快速复核", f"{ticker}-快速复核-最新.html")
    build_report_center(output_dir.parent)
    print(report)
    print(f"\n快速复核已保存：{path}")
    print(f"浏览器版本：{path.with_suffix('.html')}")


if __name__ == "__main__":
    main()
