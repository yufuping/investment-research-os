import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import yfinance as yf

from investment_os.database.repository import ResearchRepository
from investment_os.tools.alpha_vantage import fetch_alpha_vantage
from investment_os.tools.fmp import fetch_fmp
from investment_os.tools.sec_edgar import fetch_sec_company_facts


SOURCE = "SEC EDGAR + FMP；Alpha Vantage 与 Yahoo Finance 仅作备用"
CACHE_TTL = timedelta(hours=6)
RETRY_DELAYS = (2, 5, 15)
CACHE_SCHEMA_VERSION = 4

_repository: ResearchRepository | None = None
_run_snapshots: dict[str, dict[str, Any]] = {}
_alpha_vantage_api_key: str | None = None
_fmp_api_key: str | None = None
_sec_user_agent = "InvestmentResearchOS contact@example.com"


def configure_market_data(
    repository: ResearchRepository,
    alpha_vantage_api_key: str | None = None,
    fmp_api_key: str | None = None,
    sec_user_agent: str = "InvestmentResearchOS contact@example.com",
) -> None:
    """为本次程序运行配置共享缓存。"""
    global _repository, _alpha_vantage_api_key, _fmp_api_key, _sec_user_agent
    _repository = repository
    _alpha_vantage_api_key = alpha_vantage_api_key
    _fmp_api_key = fmp_api_key
    _sec_user_agent = sec_user_agent
    _run_snapshots.clear()


def _clean(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and value != value:
        return None
    return value


def _cached_age(retrieved_at: datetime, now: datetime) -> timedelta:
    if retrieved_at.tzinfo is None:
        retrieved_at = retrieved_at.replace(tzinfo=UTC)
    return now - retrieved_at


def _format_snapshot(
    ticker: str,
    data: dict[str, Any],
    retrieved_at: datetime,
    cache_status: str,
    warning: str | None = None,
) -> dict[str, Any]:
    return {
        "股票代码": ticker,
        "状态": "成功" if data else "失败",
        "数据来源": SOURCE,
        "数据获取时间_UTC": retrieved_at.isoformat(),
        "缓存状态": cache_status,
        "警告": warning,
        "数据": {key: _clean(value) for key, value in data.items()},
    }


def _fetch_from_yahoo(ticker: str) -> dict[str, Any]:
    """只调用一次重型 info 接口，返回所有 Agent 共用的数据。"""
    info = yf.Ticker(ticker).get_info()
    return {
        "公司名称": info.get("longName"),
        "行业板块": info.get("sector"),
        "细分行业": info.get("industry"),
        "所属国家": info.get("country"),
        "公司网站": info.get("website"),
        "公司简介": info.get("longBusinessSummary"),
        "交易货币": info.get("currency"),
        "当前价格": info.get("currentPrice"),
        "市值": info.get("marketCap"),
        "滚动市盈率": info.get("trailingPE"),
        "预期市盈率": info.get("forwardPE"),
        "市销率": info.get("priceToSalesTrailing12Months"),
        "企业价值倍数_EV_EBITDA": info.get("enterpriseToEbitda"),
        "过去十二个月收入": info.get("totalRevenue"),
        "收入增长率": info.get("revenueGrowth"),
        "毛利率": info.get("grossMargins"),
        "营业利润率": info.get("operatingMargins"),
        "过去十二个月归母净利润": info.get("netIncomeToCommon"),
        "自由现金流": info.get("freeCashflow"),
        "现金总额": info.get("totalCash"),
        "债务总额": info.get("totalDebt"),
    }


def _fetch_from_primary_sources(ticker: str) -> dict[str, Any]:
    """合并 SEC 财报与 FMP 行情，缺失时依次尝试 Alpha Vantage、Yahoo。"""
    data: dict[str, Any] = {}
    sources: list[str] = []
    warnings: list[str] = []

    try:
        sec_data = fetch_sec_company_facts(ticker, _sec_user_agent)
        core_fields = ("最新申报收入", "最新申报净利润", "资产总额", "年度财务趋势", "季度财务趋势")
        if not any(sec_data.get(key) not in (None, [], {}) for key in core_fields):
            raise LookupError("SEC Company Facts 未包含可用核心财务字段")
        data.update(sec_data)
        sources.append("SEC EDGAR Company Facts")
    except Exception as exc:
        warnings.append(f"SEC 获取失败：{type(exc).__name__}")

    if _fmp_api_key:
        try:
            fmp_data = fetch_fmp(ticker, _fmp_api_key)
            data.update({key: value for key, value in fmp_data.items() if value is not None})
            sources.append("Financial Modeling Prep")
        except Exception as exc:
            warnings.append(f"FMP 获取失败：{type(exc).__name__}")
    else:
        warnings.append("未配置 FMP API Key")

    if data.get("当前价格") is None:
        if _alpha_vantage_api_key:
            try:
                alpha_data = fetch_alpha_vantage(ticker, _alpha_vantage_api_key)
                data.update({key: value for key, value in alpha_data.items() if value is not None})
                sources.append("Alpha Vantage")
            except Exception as exc:
                warnings.append(f"Alpha Vantage 获取失败：{type(exc).__name__}")
        else:
            warnings.append("未配置 Alpha Vantage API Key")

    if data.get("当前价格") is None:
        try:
            yahoo_data = _fetch_from_yahoo(ticker)
            for key, value in yahoo_data.items():
                if value is not None and data.get(key) is None:
                    data[key] = value
            sources.append("Yahoo Finance 备用")
        except Exception as exc:
            warnings.append(f"Yahoo 备用获取失败：{type(exc).__name__}")

    if not data:
        raise RuntimeError("所有数据源均未返回可用数据：" + "；".join(warnings))
    for raw_key, display_key in (
        ("市值", "市值_十亿美元"),
        ("最新申报收入", "最新申报收入_十亿美元"),
        ("最新申报净利润", "最新申报净利润_十亿美元"),
        ("最新申报经营现金流", "最新申报经营现金流_十亿美元"),
        ("最新申报资本开支", "最新申报资本开支_十亿美元"),
        ("计算自由现金流", "计算自由现金流_十亿美元"),
        ("上年同期收入", "上年同期收入_十亿美元"),
        ("上年同期净利润", "上年同期净利润_十亿美元"),
        ("上年同期经营现金流", "上年同期经营现金流_十亿美元"),
        ("上年同期资本开支", "上年同期资本开支_十亿美元"),
        ("上年同期自由现金流", "上年同期自由现金流_十亿美元"),
    ):
        value = data.get(raw_key)
        if isinstance(value, (int, float)):
            data[display_key] = round(value / 1_000_000_000, 3)
    data["本次实际数据来源"] = "；".join(sources)
    data["数据源警告"] = "；".join(warnings) if warnings else None
    data["缓存架构版本"] = CACHE_SCHEMA_VERSION
    return data


def prepare_market_snapshot(ticker: str, force_refresh: bool = False) -> dict[str, Any]:
    """准备本次研究共用的数据快照；成功后不再重复访问 Yahoo。"""
    ticker = ticker.upper().strip()
    if ticker in _run_snapshots and not force_refresh:
        return _run_snapshots[ticker]
    if _repository is None:
        raise RuntimeError("市场数据缓存尚未配置")

    now = datetime.now(UTC)
    cached = _repository.get_market_cache(ticker)
    cached_payload = json.loads(cached.payload) if cached is not None else None
    cache_is_current = cached_payload and cached_payload.get("缓存架构版本") == CACHE_SCHEMA_VERSION
    if not force_refresh and cached is not None and cache_is_current and _cached_age(cached.retrieved_at, now) <= CACHE_TTL:
        snapshot = _format_snapshot(
            ticker,
            cached_payload,
            cached.retrieved_at.replace(tzinfo=UTC) if cached.retrieved_at.tzinfo is None else cached.retrieved_at,
            "有效缓存",
        )
        _run_snapshots[ticker] = snapshot
        return snapshot

    last_error: Exception | None = None
    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            data = _fetch_from_primary_sources(ticker)
            if cached_payload:
                restored_keys = []
                for key, value in cached_payload.items():
                    if key in {"数据源警告", "本次实际数据来源", "缓存架构版本"}:
                        continue
                    if data.get(key) is None and value is not None:
                        data[key] = value
                        restored_keys.append(key)
                if restored_keys:
                    existing_warning = data.get("数据源警告")
                    fallback_warning = "部分缺失字段使用上次缓存补齐"
                    data["数据源警告"] = "；".join(filter(None, (existing_warning, fallback_warning)))
            retrieved_at = datetime.now(UTC)
            _repository.save_market_cache(
                ticker=ticker,
                payload=json.dumps(data, ensure_ascii=False),
                source=SOURCE,
                retrieved_at=retrieved_at,
            )
            snapshot = _format_snapshot(ticker, data, retrieved_at, "新数据")
            _run_snapshots[ticker] = snapshot
            return snapshot
        except Exception as exc:
            last_error = exc
            if attempt < len(RETRY_DELAYS):
                time.sleep(RETRY_DELAYS[attempt])

    warning = f"实时数据获取失败：{type(last_error).__name__}。"
    if cached is not None:
        retrieved_at = cached.retrieved_at.replace(tzinfo=UTC) if cached.retrieved_at.tzinfo is None else cached.retrieved_at
        snapshot = _format_snapshot(
            ticker,
            json.loads(cached.payload),
            retrieved_at,
            "过期缓存回退",
            warning + "报告必须明确标注正在使用过期缓存。",
        )
    else:
        snapshot = _format_snapshot(
            ticker,
            {},
            now,
            "无可用缓存",
            warning + "禁止猜测任何当前价格、财务数字或数据日期。",
        )
    _run_snapshots[ticker] = snapshot
    return snapshot
