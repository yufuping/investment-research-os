import argparse
from datetime import UTC, datetime
import json

from agents import Runner, set_default_openai_key

from investment_os.agents.cio import build_cio_agent
from investment_os.app.config import get_settings
from investment_os.database.repository import ResearchRepository
from investment_os.memory.chroma_store import ThesisMemory
from investment_os.reports.markdown import calculate_acceptable_prices, build_verified_data_table, replace_quantitative_sections, save_report
from investment_os.reports.quality import audit_report
from investment_os.tools.market import configure_market_data, prepare_market_snapshot


def growth_rate(value: str) -> float:
    number = float(value)
    if number <= -100:
        raise argparse.ArgumentTypeError("EPS 增长率必须大于 -100%")
    return number


def positive_multiple(value: str) -> float:
    number = float(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("期末市盈率必须大于 0")
    return number


def required_return(value: str) -> float:
    number = float(value)
    if number <= -100 or number > 100:
        raise argparse.ArgumentTypeError("要求回报率必须大于 -100% 且不超过 100%")
    return number


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成上市公司投资研究报告")
    parser.add_argument("ticker", help="股票代码，例如 NVDA")
    parser.add_argument("--question", default="", help="可选：需要重点研究的问题")
    parser.add_argument("--bear-growth", type=growth_rate, default=10.0, help="悲观情景 EPS 年增长率，默认 10")
    parser.add_argument("--bear-pe", type=positive_multiple, default=18.0, help="悲观情景期末市盈率，默认 18")
    parser.add_argument("--base-growth", type=growth_rate, default=20.0, help="基准情景 EPS 年增长率，默认 20")
    parser.add_argument("--base-pe", type=positive_multiple, default=25.0, help="基准情景期末市盈率，默认 25")
    parser.add_argument("--bull-growth", type=growth_rate, default=30.0, help="乐观情景 EPS 年增长率，默认 30")
    parser.add_argument("--bull-pe", type=positive_multiple, default=32.0, help="乐观情景期末市盈率，默认 32")
    parser.add_argument("--required-return", type=required_return, default=12.0, help="反向估值要求年化回报率，默认 12")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ticker = args.ticker.upper().strip()
    settings = get_settings()
    set_default_openai_key(settings.openai_api_key)
    repository = ResearchRepository(settings.absolute_path(settings.database_path))
    configure_market_data(
        repository,
        fmp_api_key=settings.fmp_api_key,
        alpha_vantage_api_key=settings.alpha_vantage_api_key,
        sec_user_agent=settings.sec_user_agent,
    )
    run_id = repository.start_run(ticker, args.question)
    runtime_date = datetime.now(UTC).date().isoformat()

    prompt = (
        f"请从长期投资角度分析 {ticker}。"
        f"本次程序运行日期为 {runtime_date}（UTC）。"
        "凡日期不晚于本次运行日期，不得仅因其晚于模型知识截止时间而称为未来日期。"
        "本地工具是在运行时访问 SEC、市场数据服务或有效缓存的可信数据通道；"
        "工具明确返回成功、来源链接、申报日期或抓取时间时，应作为本次报告可引用的运行时证据。"
        "必须调用所有专业分析 Agent 和可用的市场数据工具。"
        "全文使用简体中文，清楚区分事实、估算、假设、风险和缺失数据。"
        f"用户要求重点研究的问题：{args.question or '无额外要求'}。"
    )
    try:
        market_snapshot = prepare_market_snapshot(ticker)
        result = Runner.run_sync(
            build_cio_agent(
                settings.openai_cio_model,
                specialist_model=settings.openai_model,
                risk_model=settings.openai_risk_model,
            ),
            prompt,
        )
        valuation_scenarios = (
            ("悲观", args.bear_growth, args.bear_pe),
            ("基准", args.base_growth, args.base_pe),
            ("乐观", args.bull_growth, args.bull_pe),
        )
        report = replace_quantitative_sections(
            str(result.final_output),
            market_snapshot,
            valuation_scenarios=valuation_scenarios,
            required_return=args.required_return,
        )
        quality = audit_report(report, market_snapshot)
        if not quality.passed:
            draft_path = save_report(
                ticker=f"{ticker}-草稿",
                content=f"{report.rstrip()}\n\n{quality.to_markdown()}",
                output_dir=settings.absolute_path(settings.reports_path).parent / "drafts",
                verified_data=build_verified_data_table(market_snapshot),
                model_summary=(
                    f"CIO：{settings.openai_cio_model}；风险：{settings.openai_risk_model}；"
                    f"商业/财务/估值：{settings.openai_model}"
                ),
            )
            raise ValueError("报告未通过自动质量检查：" + "；".join(quality.errors) + f"；草稿已保存：{draft_path}")
        report = f"{report.rstrip()}\n\n{quality.to_markdown()}"
        report_path = save_report(
            ticker=ticker,
            content=report,
            output_dir=settings.absolute_path(settings.reports_path),
            verified_data=build_verified_data_table(market_snapshot),
            model_summary=(
                f"CIO：{settings.openai_cio_model}；风险：{settings.openai_risk_model}；"
                f"商业/财务/估值：{settings.openai_model}"
            ),
        )
        ThesisMemory(settings.absolute_path(settings.chroma_path)).remember(
            memory_id=f"research-run-{run_id}",
            ticker=ticker,
            text=report,
        )
        repository.complete_run(run_id, report, str(report_path))
        data = market_snapshot.get("数据") or {}
        eps = data.get("每股收益_TTM")
        acceptable_prices = calculate_acceptable_prices(eps, valuation_scenarios, args.required_return) if isinstance(eps, (int, float)) else {}
        repository.save_valuation_watch(
            ticker=ticker,
            required_return=args.required_return,
            scenarios_json=json.dumps(valuation_scenarios, ensure_ascii=False),
            acceptable_prices_json=json.dumps(acceptable_prices, ensure_ascii=False),
            reference_price=data.get("当前价格"),
            reference_eps=eps,
        )
    except Exception as exc:
        repository.fail_run(run_id, str(exc))
        raise

    print(report)
    print(f"\n报告已保存：{report_path}")
    print(f"浏览器版本：{report_path.with_suffix('.html')}")
    print(f"固定最新版本：{report_path.parent / (ticker + '-最新.html')}")


if __name__ == "__main__":
    main()
