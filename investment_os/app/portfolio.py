import argparse
import json
from urllib.parse import quote
from datetime import UTC, datetime, timedelta
from pathlib import Path

from investment_os.app.config import get_settings
from investment_os.database.repository import ResearchRepository
from investment_os.reports.portfolio import build_decision_journal, build_portfolio_history, build_portfolio_report, build_portfolio_review, build_risk_suite_report, build_scenario_report, build_stress_test_report, build_transaction_report, portfolio_snapshot_values
from investment_os.reports.html import markdown_to_html
from investment_os.reports.index import build_report_center
from investment_os.tools.market import configure_market_data, prepare_market_snapshot


def positive(value: str) -> float:
    number = float(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("必须输入大于0的数字")
    return number


def load_risk_scenarios(path: Path) -> dict[str, dict[str, float]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取风险情景配置 {path}：{exc}") from exc
    if not isinstance(payload, dict) or not payload:
        raise ValueError("风险情景配置必须是非空对象。")
    scenarios = {}
    for name, shocks in payload.items():
        if not isinstance(name, str) or not name.strip() or not isinstance(shocks, dict) or not shocks:
            raise ValueError("每个情景必须有名称和至少一个风险主题。")
        normalized = {}
        for theme, shock in shocks.items():
            if not isinstance(theme, str) or not theme.strip() or not isinstance(shock, (int, float)) or shock <= -100:
                raise ValueError(f"情景“{name}”包含无效主题或跌幅。")
            normalized[theme.strip()] = float(shock)
        scenarios[name.strip()] = normalized
    return scenarios


def choose_portfolio_price(market_price, market_date, reference, now: datetime | None = None) -> tuple[float, str, str, bool]:
    """选择日期更新的可用价格；同日仍优先市场数据。"""
    current_time = now or datetime.now(UTC)
    reference_time = None
    reference_date = None
    if reference is not None:
        reference_time = reference.updated_at
        if reference_time.tzinfo is None:
            reference_time = reference_time.replace(tzinfo=UTC)
        reference_date = getattr(reference, "observed_date", None) or reference_time.date().isoformat()
    market_is_valid = isinstance(market_price, (int, float))
    reference_is_newer = bool(reference_date and (not market_date or reference_date > market_date))
    if reference is not None and (not market_is_valid or reference_is_newer):
        return reference.price, reference.source, reference_date, current_time - reference_time > timedelta(days=1)
    if market_is_valid:
        return market_price, "市场数据", market_date, market_date is None
    raise RuntimeError("缺少市场价格和人工参考价格")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="管理个人投资组合")
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add", help="新增或更新持仓")
    add.add_argument("ticker")
    add.add_argument("--shares", type=positive, required=True, help="持股数量")
    add.add_argument("--cost", type=positive, required=True, help="每股成本（美元）")
    add.add_argument("--price", type=positive, help="可选：截图或对账单中的参考价格（美元）")
    price_command = commands.add_parser("price", help="录入截图或券商对账单中的参考价格")
    price_command.add_argument("ticker")
    price_command.add_argument("--price", type=positive, required=True, help="每股价格（美元）")
    price_command.add_argument("--date", required=True, help="价格观察日期，格式 YYYY-MM-DD")
    price_command.add_argument("--source", default="人工录入", help="价格来源，例如 用户截图、券商对账单")
    remove = commands.add_parser("remove", help="删除持仓")
    remove.add_argument("ticker")
    commands.add_parser("show", help="刷新价格并显示组合")
    commands.add_parser("review", help="生成组合概览、预警和风险情景合并报告")
    commands.add_parser("risk-suite", help="运行一组预设的组合风险情景")
    stress = commands.add_parser("stress", help="按共同风险主题执行组合压力测试")
    stress.add_argument("--theme", required=True, help="已经设置的风险主题，例如 AI资本开支周期")
    stress.add_argument("--shock", type=float, default=-30.0, help="价格冲击百分比，默认 -30")
    scenario = commands.add_parser("scenario", help="执行多个风险主题组成的组合情景测试")
    scenario.add_argument("--name", default="自定义情景", help="情景名称")
    scenario.add_argument("--shock", action="append", required=True, metavar="主题=百分比", help="可重复，例如 --shock AI资本开支周期=-30")
    commands.add_parser("history", help="查看组合历史快照")
    for trade_type in ("buy", "sell"):
        trade = commands.add_parser(trade_type, help="记录买入" if trade_type == "buy" else "记录卖出")
        trade.add_argument("ticker")
        trade.add_argument("--shares", type=positive, required=True)
        trade.add_argument("--price", type=positive, required=True)
        trade.add_argument("--fee", type=float, default=0.0)
        trade.add_argument("--note", default="")
    commands.add_parser("transactions", help="查看交易流水")
    decision = commands.add_parser("decision", help="记录投资决策")
    decision.add_argument("ticker")
    decision.add_argument("--action", required=True, choices=["观察", "买入", "持有", "减仓", "退出", "重新评估"])
    decision.add_argument("--thesis", required=True, help="核心理由")
    decision.add_argument("--price", type=positive, help="参考价格")
    decision.add_argument("--valuation", default="", help="估值依据")
    decision.add_argument("--invalidation", default="", help="投资逻辑失效条件")
    decision.add_argument("--next-check", default="", help="下次检查事项或时间")
    journal = commands.add_parser("journal", help="查看投资决策日志")
    journal.add_argument("ticker", nargs="?")
    tag = commands.add_parser("tag", help="设置持仓风险标签")
    tag.add_argument("ticker")
    tag.add_argument("--tags", nargs="+", required=True, help="一个或多个风险标签")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = get_settings()
    repository = ResearchRepository(settings.absolute_path(settings.database_path))
    if args.command == "add":
        repository.save_position(args.ticker, args.shares, args.cost)
        if args.price is not None:
            repository.save_reference_price(args.ticker, args.price, source="用户截图")
        print(f"已保存持仓：{args.ticker.upper()}，{args.shares} 股，每股成本 {args.cost:.2f} 美元")
        return
    if args.command == "price":
        try:
            datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            raise SystemExit("价格日期格式错误，请使用 YYYY-MM-DD，例如 2026-08-23。")
        repository.save_reference_price(args.ticker, args.price, source=args.source, observed_date=args.date)
        print(f"已保存 {args.ticker.upper()} 参考价格：{args.price:.2f} 美元，观察日期 {args.date}，来源：{args.source}")
        return
    if args.command == "remove":
        removed = repository.delete_position(args.ticker)
        print("持仓已删除" if removed else "未找到该持仓")
        return
    if args.command == "tag":
        repository.replace_position_tags(args.ticker, args.tags)
        print(f"已保存 {args.ticker.upper()} 风险标签：{'、'.join(args.tags)}")
        return
    if args.command == "history":
        snapshots = repository.list_portfolio_snapshots()
        if not snapshots:
            raise SystemExit("尚无组合历史快照，请先运行 show。")
        report = build_portfolio_history(snapshots)
        output_dir = settings.absolute_path(Path("reports/portfolio"))
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        path = output_dir / f"组合历史-{timestamp}.md"
        path.write_text(report + "\n", encoding="utf-8")
        print(report)
        print(f"\n组合历史已保存：{path}")
        return
    if args.command in {"buy", "sell"}:
        transaction_id = repository.record_trade(
            args.ticker,
            args.command,
            args.shares,
            args.price,
            fee=args.fee,
            note=args.note,
        )
        print(f"交易已记录，本地流水编号：{transaction_id}")
        return
    if args.command == "transactions":
        transactions = repository.list_transactions()
        if not transactions:
            raise SystemExit("尚无交易流水。首次导入的持仓不自动伪造成历史交易。")
        report = build_transaction_report(transactions)
        output_dir = settings.absolute_path(Path("reports/portfolio"))
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        path = output_dir / f"交易流水-{timestamp}.md"
        path.write_text(report + "\n", encoding="utf-8")
        print(report)
        print(f"\n交易流水已保存：{path}")
        return
    if args.command == "decision":
        decision_id = repository.save_decision(
            args.ticker,
            args.action,
            args.thesis,
            reference_price=args.price,
            valuation_basis=args.valuation,
            invalidation_condition=args.invalidation,
            next_check=args.next_check,
        )
        print(f"投资决策已记录，本地日志编号：{decision_id}")
        return
    if args.command == "journal":
        decisions = repository.list_decisions(args.ticker)
        if not decisions:
            raise SystemExit("尚无符合条件的投资决策日志。")
        report = build_decision_journal(decisions)
        output_dir = settings.absolute_path(Path("reports/portfolio"))
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        label = args.ticker.upper() if args.ticker else "全部"
        path = output_dir / f"决策日志-{label}-{timestamp}.md"
        path.write_text(report + "\n", encoding="utf-8")
        print(report)
        print(f"\n决策日志已保存：{path}")
        return

    positions = repository.list_positions()
    if not positions:
        raise SystemExit("组合中尚无持仓，请先使用 add 命令录入。")
    configure_market_data(
        repository,
        fmp_api_key=settings.fmp_api_key,
        alpha_vantage_api_key=settings.alpha_vantage_api_key,
        sec_user_agent=settings.sec_user_agent,
    )
    rows = []
    for position in positions:
        data = {}
        try:
            data = prepare_market_snapshot(position.ticker).get("数据") or {}
            price = data.get("当前价格")
        except Exception:
            price = None
        market_date = data.get("价格日期") if isinstance(price, (int, float)) else None
        reference = repository.get_reference_price(position.ticker)
        try:
            price, price_source, price_date, price_is_stale = choose_portfolio_price(price, market_date, reference)
        except RuntimeError:
            raise RuntimeError(f"{position.ticker} 缺少市场价格和人工参考价格，组合报告已停止，避免遗漏持仓。")
        rows.append({
            "ticker": position.ticker,
            "shares": position.shares,
            "cost_per_share": position.cost_per_share,
            "current_price": price,
            "price_source": price_source,
            "price_date": price_date,
            "price_is_stale": price_is_stale,
            "risk_tags": repository.get_position_tags(position.ticker),
            "has_research": bool(repository.get_completed_runs(position.ticker, limit=1)),
            "cost_value": position.shares * position.cost_per_share,
            "market_value": position.shares * price,
        })
    if args.command == "stress":
        if args.shock <= -100:
            raise SystemExit("压力幅度必须大于 -100%。")
        known_themes = {tag for row in rows for tag in row.get("risk_tags", [])}
        if args.theme not in known_themes:
            raise SystemExit(f"未找到风险主题：{args.theme}。可用主题：{'、'.join(sorted(known_themes))}")
        report = build_stress_test_report(rows, args.theme, args.shock)
        output_dir = settings.absolute_path(Path("reports/portfolio"))
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        path = output_dir / f"压力测试-{args.theme}-{timestamp}.md"
        path.write_text(report + "\n", encoding="utf-8")
        print(report)
        print(f"\n压力测试报告已保存：{path}")
        return
    if args.command == "scenario":
        shocks = {}
        for raw in args.shock:
            try:
                theme, value = raw.rsplit("=", 1)
                shock = float(value)
            except ValueError:
                raise SystemExit(f"情景参数格式错误：{raw}；正确示例：AI资本开支周期=-30")
            if not theme.strip() or shock <= -100:
                raise SystemExit(f"情景参数无效：{raw}；主题不能为空，跌幅必须大于 -100%。")
            shocks[theme.strip()] = shock
        known_themes = {tag for row in rows for tag in row.get("risk_tags", [])}
        unknown = sorted(set(shocks) - known_themes)
        if unknown:
            raise SystemExit(f"未找到风险主题：{'、'.join(unknown)}。可用主题：{'、'.join(sorted(known_themes))}")
        report = build_scenario_report(rows, args.name, shocks)
        output_dir = settings.absolute_path(Path("reports/portfolio"))
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        safe_name = "".join(char for char in args.name if char.isalnum() or char in "-_ ").strip() or "自定义情景"
        path = output_dir / f"多因素情景-{safe_name}-{timestamp}.md"
        path.write_text(report + "\n", encoding="utf-8")
        print(report)
        print(f"\n多因素情景报告已保存：{path}")
        return
    if args.command == "risk-suite":
        try:
            scenarios = load_risk_scenarios(settings.absolute_path(Path("config/risk_scenarios.json")))
        except ValueError as exc:
            raise SystemExit(str(exc))
        report = build_risk_suite_report(rows, scenarios)
        output_dir = settings.absolute_path(Path("reports/portfolio"))
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        path = output_dir / f"风险情景组-{timestamp}.md"
        path.write_text(report + "\n", encoding="utf-8")
        print(report)
        print(f"\n风险情景组报告已保存：{path}")
        return

    alert_thresholds = {
        "single_position": settings.portfolio_single_position_alert_pct,
        "top_two": settings.portfolio_top_two_alert_pct,
        "top_three": settings.portfolio_top_three_alert_pct,
        "risk_theme": settings.portfolio_risk_theme_alert_pct,
    }
    if args.command == "review":
        try:
            scenarios = load_risk_scenarios(settings.absolute_path(Path("config/risk_scenarios.json")))
        except ValueError as exc:
            raise SystemExit(str(exc))
        previous = repository.list_portfolio_snapshots(limit=1)
        snapshot_id = repository.save_portfolio_snapshot_if_changed(**portfolio_snapshot_values(rows))
        snapshots = repository.list_portfolio_snapshots(limit=12)
        report = build_portfolio_review(rows, scenarios, alert_thresholds, previous[0] if previous else None, snapshots)
        output_dir = settings.absolute_path(Path("reports/portfolio"))
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        path = output_dir / f"组合综合复核-{timestamp}.md"
        path.write_text(report + "\n", encoding="utf-8")
        latest_path = output_dir / "组合综合复核-最新.md"
        latest_path.write_text(report + "\n", encoding="utf-8")
        html_path = output_dir / "组合综合复核-最新.html"
        generated_dir = output_dir.parent / "generated"
        company_links = {
            path.stem.removesuffix("-最新").upper(): f"../generated/{quote(path.name)}"
            for path in generated_dir.glob("*-最新.html")
        }
        html_path.write_text(markdown_to_html(report, "投资组合综合复核", company_links, "../%E6%8A%A5%E5%91%8A%E4%B8%AD%E5%BF%83.html"), encoding="utf-8")
        center_path = build_report_center(output_dir.parent)
        print(report)
        print(f"\n组合综合复核已保存：{path}")
        print(f"固定最新版本：{latest_path}")
        print(f"浏览器版本：{html_path}")
        print(f"报告中心：{center_path}")
        print("历史快照：" + (f"已新增 #{snapshot_id}" if snapshot_id is not None else "组合无变化，未重复保存"))
        return

    report = build_portfolio_report(rows, alert_thresholds)
    snapshot_values = portfolio_snapshot_values(rows)
    repository.save_portfolio_snapshot_if_changed(**snapshot_values)
    output_dir = settings.absolute_path(Path("reports/portfolio"))
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"组合概览-{timestamp}.md"
    path.write_text(report + "\n", encoding="utf-8")
    print(report)
    print(f"\n组合报告已保存：{path}")


if __name__ == "__main__":
    main()
