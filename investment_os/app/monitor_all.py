from datetime import UTC, datetime
import json
from pathlib import Path

from investment_os.app.compare import load_complete_report
from investment_os.app.config import get_settings
from investment_os.database.repository import ResearchRepository
from investment_os.reports.markdown import build_verified_data_table, calculate_acceptable_prices
from investment_os.reports.monitoring import build_monitoring_report, parse_verified_table, valuation_zone
from investment_os.reports.watchlist import build_watchlist_summary
from investment_os.reports.html import save_html_report
from investment_os.reports.index import build_report_center
from investment_os.tools.market import configure_market_data, prepare_market_snapshot


def main() -> None:
    settings = get_settings()
    repository = ResearchRepository(settings.absolute_path(settings.database_path))
    configure_market_data(
        repository,
        fmp_api_key=settings.fmp_api_key,
        alpha_vantage_api_key=settings.alpha_vantage_api_key,
        sec_user_agent=settings.sec_user_agent,
    )
    watches = repository.list_valuation_watches()
    if not watches:
        raise SystemExit("观察清单为空，请先为至少一家公司运行完整研究。")

    output_dir = settings.absolute_path(Path("reports/monitoring"))
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    summary_rows = []

    for watch in watches:
        runs = repository.get_completed_runs(watch.ticker, limit=1)
        if not runs:
            continue
        previous_report = load_complete_report(runs[0])
        snapshot = prepare_market_snapshot(watch.ticker)
        scenarios = json.loads(watch.scenarios_json)
        saved_prices = json.loads(watch.acceptable_prices_json)
        data = snapshot.get("数据") or {}
        current_eps = data.get("每股收益_TTM")
        current_price = data.get("当前价格")
        current_prices = (
            calculate_acceptable_prices(current_eps, scenarios, watch.required_return)
            if isinstance(current_eps, (int, float))
            else {}
        )
        previous_zone = valuation_zone(watch.reference_price, saved_prices) if watch.reference_price is not None else "数据不足"
        current_zone = valuation_zone(current_price, current_prices) if isinstance(current_price, (int, float)) else "数据不足"
        old_period = (parse_verified_table(previous_report).get("最新申报收入") or {}).get("期间")
        current_table = parse_verified_table(build_verified_data_table(snapshot) + "\n# 正文")
        new_period = (current_table.get("最新申报收入") or {}).get("期间")
        new_filing = old_period != new_period
        action = "运行完整研究" if new_filing else "复核估值假设" if current_zone != previous_zone else "继续观察"

        detail = build_monitoring_report(
            watch.ticker,
            previous_report,
            snapshot,
            scenarios=scenarios,
            required_return=watch.required_return,
            saved_acceptable_prices=saved_prices,
            reference_price=watch.reference_price,
            reference_eps=watch.reference_eps,
        )
        detail_path = output_dir / f"{watch.ticker}-快速复核-{timestamp}.md"
        detail_path.write_text(detail + "\n", encoding="utf-8")
        save_html_report(detail_path, f"{watch.ticker} 快速复核", f"{watch.ticker}-快速复核-最新.html")
        summary_rows.append({
            "ticker": watch.ticker,
            "price": f"{current_price:.2f} 美元" if isinstance(current_price, (int, float)) else "数据缺失",
            "current_zone": current_zone,
            "previous_zone": previous_zone,
            "new_filing": new_filing,
            "action": action,
        })

    summary = build_watchlist_summary(summary_rows)
    path = output_dir / f"全部观察-{timestamp}.md"
    path.write_text(summary + "\n", encoding="utf-8")
    save_html_report(path, "全部观察清单复核", "全部观察-最新.html")
    center_path = build_report_center(output_dir.parent)
    print(summary)
    print(f"\n观察清单复核已保存：{path}")
    print(f"浏览器版本：{path.with_suffix('.html')}")
    print(f"报告中心：{center_path}")


if __name__ == "__main__":
    main()
