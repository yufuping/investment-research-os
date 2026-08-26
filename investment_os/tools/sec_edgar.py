from typing import Any
from datetime import date, timedelta
import re
import warnings

import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning


TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
# `Revenues` represents the consolidated top line when an issuer also reports
# component revenue concepts.  Keep it ahead of contract revenue so companies
# such as Circle are not reduced to their small fee-revenue component while
# reserve income is omitted.
REVENUE_TAGS = ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "Revenue")
NET_INCOME_TAGS = ("NetIncomeLoss", "ProfitLoss")
OPERATING_CASH_TAGS = ("NetCashProvidedByUsedInOperatingActivities", "CashFlowsFromUsedInOperatingActivities")
CAPEX_TAGS = ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets", "PurchaseOfPropertyPlantAndEquipment")
SOFTWARE_CAPEX_TAGS = ("PaymentsToDevelopSoftware",)
ANNUAL_FORMS = ("10-K", "20-F", "S-1", "S-1/A")
INTERIM_FORMS = ("10-Q", "6-K", "S-1", "S-1/A")
SUPPORTED_FORMS = set(ANNUAL_FORMS + INTERIM_FORMS)


def _get_json(url: str, user_agent: str) -> dict[str, Any]:
    response = requests.get(
        url,
        headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _get_text(url: str, user_agent: str) -> str:
    response = requests.get(url, headers={"User-Agent": user_agent}, timeout=30)
    response.raise_for_status()
    return response.text


def _extract_filing_item(text: str, start_pattern: str, end_pattern: str, limit: int = 45_000) -> str | None:
    candidates: list[str] = []
    for start in re.finditer(start_pattern, text, flags=re.I):
        end = re.search(end_pattern, text[start.end():], flags=re.I)
        if end:
            section = text[start.start():start.end() + end.start()].strip()
            if len(section) >= 500:
                candidates.append(section)
    return max(candidates, key=len)[:limit] if candidates else None


def parse_10k_sections(html: str) -> dict[str, str | None]:
    """从 10-K HTML 中提取 Item 1 与 Item 1A 的可读文本。"""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
        text = " ".join(BeautifulSoup(html, "lxml").get_text(" ").split())
    business = _extract_filing_item(text, r"item\s+1[.\s:-]+business", r"item\s+1a[.\s:-]+risk\s+factors")
    risks = _extract_filing_item(text, r"item\s+1a[.\s:-]+risk\s+factors", r"item\s+1b[.\s:-]+")
    return {"业务披露节选": business, "风险因素节选": risks}


def parse_filing_sections(html: str, form: str) -> dict[str, str | None]:
    """提取 10-K、20-F 和 S-1 中可识别的业务及风险章节。"""
    if form == "10-K":
        return parse_10k_sections(html)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
        text = " ".join(BeautifulSoup(html, "lxml").get_text(" ").split())
    if form == "20-F":
        business = _extract_filing_item(text, r"item\s+4[.\s:-]+information\s+on\s+the\s+company", r"item\s+4a[.\s:-]+")
        risks = _extract_filing_item(text, r"item\s+3[.\s:-]+key\s+information", r"item\s+4[.\s:-]+information\s+on\s+the\s+company")
    else:
        business = _extract_filing_item(text, r"(?:our\s+)?business", r"risk\s+factors")
        risks = _extract_filing_item(text, r"risk\s+factors", r"use\s+of\s+proceeds|dividend\s+policy|capitalization")
    return {"业务披露节选": business, "风险因素节选": risks}


def fetch_latest_10k_context(ticker: str, user_agent: str) -> dict[str, Any]:
    """获取最新年度报告或上市招股书的业务与风险因素章节。"""
    cik, company_name = _find_company(ticker, user_agent)
    submissions = _get_json(SUBMISSIONS_URL.format(cik=cik), user_agent)
    recent = submissions.get("filings", {}).get("recent", {})
    for index, form in enumerate(recent.get("form", [])):
        if form not in ANNUAL_FORMS:
            continue
        accession = recent["accessionNumber"][index]
        primary_document = recent["primaryDocument"][index]
        url = (
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
            f"{accession.replace('-', '')}/{primary_document}"
        )
        return {
            "公司名称": company_name,
            "SEC_CIK": cik,
            "SEC最新申报表类型": form,
            "SEC最新10K申报日期": recent["filingDate"][index],
            "SEC最新10K报告期": recent["reportDate"][index],
            "SEC最新10K链接": url,
            **parse_filing_sections(_get_text(url, user_agent), form),
        }
    raise LookupError(f"SEC submissions 中找不到 {ticker} 的年度报告或 S-1")


def _find_company(ticker: str, user_agent: str) -> tuple[str, str]:
    companies = _get_json(TICKERS_URL, user_agent)
    for item in companies.values():
        if item.get("ticker", "").upper() == ticker.upper():
            return str(item["cik_str"]).zfill(10), item.get("title", ticker)
    raise LookupError(f"SEC 公司列表中找不到股票代码 {ticker}")


def _fact_candidates(
    facts: dict[str, Any],
    tags: tuple[str, ...],
    units: tuple[str, ...] = ("USD", "shares"),
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    namespaces = facts.get("facts", {})
    for namespace_name in ("us-gaap", "ifrs-full"):
        namespace = namespaces.get(namespace_name, {})
        for tag in tags:
            concept = namespace.get(tag, {})
            available_units = units if units else tuple(concept.get("units", {}))
            for unit in available_units:
                if unit == "shares" and "Share" not in tag:
                    continue
                for item in concept.get("units", {}).get(unit, []):
                    if item.get("form") in SUPPORTED_FORMS and item.get("filed"):
                        candidates.append({**item, "tag": tag, "unit": unit, "namespace": namespace_name})
    return candidates


def _reporting_currency(facts: dict[str, Any]) -> str:
    """选择收入事实中出现次数最多的申报货币，避免混用 ADR 美元与本币。"""
    counts: dict[str, int] = {}
    for item in _fact_candidates(facts, REVENUE_TAGS, units=()):
        unit = item.get("unit")
        if unit and unit != "shares":
            counts[unit] = counts.get(unit, 0) + 1
    return max(counts, key=counts.get) if counts else "USD"


def _latest_fact(
    facts: dict[str, Any],
    tags: tuple[str, ...],
    units: tuple[str, ...] = ("USD", "shares"),
) -> dict[str, Any] | None:
    candidates = _fact_candidates(facts, tags, units)
    return max(candidates, key=lambda item: (item.get("filed", ""), item.get("end", "")), default=None)


def _previous_year_fact(
    facts: dict[str, Any],
    tags: tuple[str, ...],
    latest: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """匹配持续时间相近、结束日约早一年的上年同期事实。"""
    if not latest or not latest.get("start") or not latest.get("end"):
        return None
    latest_start = date.fromisoformat(latest["start"])
    latest_end = date.fromisoformat(latest["end"])
    latest_days = (latest_end - latest_start).days
    matches: list[tuple[int, dict[str, Any]]] = []
    for candidate in _fact_candidates(facts, tags, units=(latest.get("unit", "USD"),)):
        if not candidate.get("start") or not candidate.get("end"):
            continue
        start = date.fromisoformat(candidate["start"])
        end = date.fromisoformat(candidate["end"])
        year_gap = (latest_end - end).days
        duration_gap = abs((end - start).days - latest_days)
        if 330 <= year_gap <= 400 and duration_gap <= 14:
            matches.append((abs(year_gap - 365) + duration_gap * 3, candidate))
    return min(matches, key=lambda item: item[0], default=(0, None))[1]


def _growth(current: Any, previous: Any) -> float | None:
    if (
        not isinstance(current, (int, float))
        or not isinstance(previous, (int, float))
        or previous <= 0
        or current < 0
    ):
        return None
    return round((current / previous - 1) * 100, 2)


def _period_series(
    facts: dict[str, Any],
    tags: tuple[str, ...],
    minimum_days: int,
    maximum_days: int,
    forms: tuple[str, ...] | None = None,
    currency: str = "USD",
) -> dict[tuple[str, str], dict[str, Any]]:
    """按开始日和结束日去重，并筛选指定持续时间的财务事实。"""
    periods: dict[tuple[str, str], dict[str, Any]] = {}
    for item in _fact_candidates(facts, tags, units=(currency,)):
        if forms is not None and item.get("form") not in forms:
            continue
        if not item.get("start") or not item.get("end"):
            continue
        start = date.fromisoformat(item["start"])
        end = date.fromisoformat(item["end"])
        duration = (end - start).days
        if not minimum_days <= duration <= maximum_days:
            continue
        key = (item["start"], item["end"])
        existing = periods.get(key)
        item_priority = tags.index(item["tag"]) if item.get("tag") in tags else len(tags)
        existing_priority = tags.index(existing["tag"]) if existing and existing.get("tag") in tags else len(tags)
        if (
            existing is None
            or item.get("filed", "") > existing.get("filed", "")
            or (item.get("filed", "") == existing.get("filed", "") and item_priority < existing_priority)
        ):
            periods[key] = item
    return periods


def _combined_capex_series(
    facts: dict[str, Any],
    minimum_days: int,
    maximum_days: int,
    forms: tuple[str, ...] | None = None,
    currency: str = "USD",
) -> dict[tuple[str, str], dict[str, Any]]:
    """合并有形资产与资本化软件投入，避免把软件型公司的 CapEx 严重低估。"""
    tangible = _period_series(facts, CAPEX_TAGS, minimum_days, maximum_days, forms=forms, currency=currency)
    software = _period_series(facts, SOFTWARE_CAPEX_TAGS, minimum_days, maximum_days, forms=forms, currency=currency)
    combined: dict[tuple[str, str], dict[str, Any]] = {}
    for key in set(tangible) | set(software):
        components = [item for item in (tangible.get(key), software.get(key)) if item is not None]
        values = [_value(item) for item in components]
        numeric = [value for value in values if isinstance(value, (int, float))]
        if numeric:
            combined[key] = {
                "val": sum(numeric),
                "filed": max((item.get("filed", "") for item in components), default=""),
                "components": [item.get("tag") for item in components],
            }
    return combined


def _discrete_cash_flow_series(
    facts: dict[str, Any],
    tags: tuple[str, ...],
    currency: str = "USD",
    combine_capex: bool = False,
) -> dict[tuple[str, str], dict[str, Any]]:
    """把财年累计现金流拆分为单季度现金流。"""
    cumulative = (
        _combined_capex_series(facts, 70, 400, currency=currency)
        if combine_capex
        else _period_series(facts, tags, 70, 400, currency=currency)
    )
    by_start: dict[str, list[tuple[tuple[str, str], dict[str, Any]]]] = {}
    for key, item in cumulative.items():
        by_start.setdefault(key[0], []).append((key, item))
    discrete: dict[tuple[str, str], dict[str, Any]] = {}
    for periods in by_start.values():
        periods.sort(key=lambda entry: entry[0][1])
        previous_key: tuple[str, str] | None = None
        previous_value: Any = None
        previous_item: dict[str, Any] | None = None
        for key, item in periods:
            value = _value(item)
            duration = (date.fromisoformat(key[1]) - date.fromisoformat(key[0])).days
            if 70 <= duration <= 110 and isinstance(value, (int, float)):
                discrete[key] = {**item, "derived": False, "source_periods": [key]}
            elif previous_key and isinstance(value, (int, float)) and isinstance(previous_value, (int, float)):
                gap = (date.fromisoformat(key[1]) - date.fromisoformat(previous_key[1])).days
                if 70 <= gap <= 110:
                    quarter_key = ((date.fromisoformat(previous_key[1]) + timedelta(days=1)).isoformat(), key[1])
                    discrete[quarter_key] = {
                        "val": value - previous_value,
                        "derived": True,
                        "source_periods": [previous_key, key],
                        "components": sorted(set(item.get("components", [])) | set((previous_item or {}).get("components", []))),
                    }
            previous_key, previous_value, previous_item = key, value, item
    return discrete


def _build_trend(
    facts: dict[str, Any],
    minimum_days: int,
    maximum_days: int,
    limit: int,
    currency: str = "USD",
) -> list[dict[str, Any]]:
    forms = INTERIM_FORMS if maximum_days <= 110 else ANNUAL_FORMS
    revenue = _period_series(facts, REVENUE_TAGS, minimum_days, maximum_days, forms=forms, currency=currency)
    net_income = _period_series(facts, NET_INCOME_TAGS, minimum_days, maximum_days, forms=forms, currency=currency)
    operating_cash = _period_series(facts, OPERATING_CASH_TAGS, minimum_days, maximum_days, currency=currency)
    capex = _combined_capex_series(facts, minimum_days, maximum_days, currency=currency)
    if maximum_days <= 110:
        operating_cash = _discrete_cash_flow_series(facts, OPERATING_CASH_TAGS, currency)
        capex = _discrete_cash_flow_series(facts, CAPEX_TAGS, currency, combine_capex=True)
        # SEC 的 10-K 通常只披露全年累计值。用全年减去前三季度累计值，
        # 确定性补出第四季度，保证季度趋势连续。
        annual_series = {
            "revenue": _period_series(facts, REVENUE_TAGS, 330, 400, forms=ANNUAL_FORMS, currency=currency),
            "net_income": _period_series(facts, NET_INCOME_TAGS, 330, 400, forms=ANNUAL_FORMS, currency=currency),
            "operating_cash": _period_series(facts, OPERATING_CASH_TAGS, 330, 400, currency=currency),
            "capex": _combined_capex_series(facts, 330, 400, currency=currency),
        }
        year_to_date_series = {
            "revenue": _period_series(facts, REVENUE_TAGS, 240, 310, forms=INTERIM_FORMS, currency=currency),
            "net_income": _period_series(facts, NET_INCOME_TAGS, 240, 310, forms=INTERIM_FORMS, currency=currency),
            "operating_cash": _period_series(facts, OPERATING_CASH_TAGS, 240, 310, currency=currency),
            "capex": _combined_capex_series(facts, 240, 310, currency=currency),
        }
        targets = {
            "revenue": revenue,
            "net_income": net_income,
            "operating_cash": operating_cash,
            "capex": capex,
        }
        for annual_key in set(annual_series["revenue"]) | set(annual_series["net_income"]):
            annual_start, annual_end = annual_key
            matching_ytd_keys = [
                key for key in set(year_to_date_series["revenue"]) | set(year_to_date_series["net_income"])
                if key[0] == annual_start
                and 70 <= (date.fromisoformat(annual_end) - date.fromisoformat(key[1])).days <= 110
            ]
            if not matching_ytd_keys:
                continue
            ytd_key = max(matching_ytd_keys, key=lambda key: key[1])
            quarter_key = ((date.fromisoformat(ytd_key[1]) + timedelta(days=1)).isoformat(), annual_end)
            for metric, target in targets.items():
                annual_value = _value(annual_series[metric].get(annual_key))
                ytd_value = _value(year_to_date_series[metric].get(ytd_key))
                if isinstance(annual_value, (int, float)) and isinstance(ytd_value, (int, float)):
                    target[quarter_key] = {"val": annual_value - ytd_value, "derived": True}
    period_keys = sorted(set(revenue) | set(net_income), key=lambda key: key[1], reverse=True)[:limit]
    rows: list[dict[str, Any]] = []
    for start, end in period_keys:
        revenue_value = _value(revenue.get((start, end)))
        net_income_value = _value(net_income.get((start, end)))
        operating_cash_value = _value(operating_cash.get((start, end)))
        capex_value = _value(capex.get((start, end)))
        free_cash_flow = (
            operating_cash_value - capex_value
            if isinstance(operating_cash_value, (int, float)) and isinstance(capex_value, (int, float))
            else None
        )
        rows.append({
            "开始日": start,
            "结束日": end,
            "收入": revenue_value,
            "净利润": net_income_value,
            "经营现金流": operating_cash_value,
            "资本开支": capex_value,
            "自由现金流": free_cash_flow,
            "经营现金流口径": "单季度派生（累计值相减）" if (operating_cash.get((start, end)) or {}).get("derived") else "单季度直接披露",
            "资本开支口径": "单季度派生（累计值相减）" if (capex.get((start, end)) or {}).get("derived") else "单季度直接披露",
            "资本开支组成": (capex.get((start, end)) or {}).get("components", []),
        })
    for row in rows:
        end_date = date.fromisoformat(row["结束日"])
        comparable = next(
            (
                other for other in rows
                if 330 <= (end_date - date.fromisoformat(other["结束日"])).days <= 400
            ),
            None,
        )
        row["收入同比增长率"] = _growth(row["收入"], comparable["收入"] if comparable else None)
        row["净利润同比增长率"] = _growth(row["净利润"], comparable["净利润"] if comparable else None)
        row["自由现金流同比增长率"] = _growth(row["自由现金流"], comparable["自由现金流"] if comparable else None)
    return rows


def _value(fact: dict[str, Any] | None) -> Any:
    return None if fact is None else fact.get("val")


def fetch_sec_company_facts(ticker: str, user_agent: str) -> dict[str, Any]:
    """从 SEC Company Facts 获取公司最新已申报的标准化财务事实。"""
    cik, company_name = _find_company(ticker, user_agent)
    facts = _get_json(COMPANY_FACTS_URL.format(cik=cik), user_agent)
    currency = _reporting_currency(facts)

    revenue = _latest_fact(facts, REVENUE_TAGS, units=(currency,))
    net_income = _latest_fact(facts, NET_INCOME_TAGS, units=(currency,))
    operating_cash = _latest_fact(facts, OPERATING_CASH_TAGS, units=(currency,))
    capex = _latest_fact(facts, CAPEX_TAGS, units=(currency,))
    previous_revenue = _previous_year_fact(facts, REVENUE_TAGS, revenue)
    previous_net_income = _previous_year_fact(facts, NET_INCOME_TAGS, net_income)
    previous_operating_cash = _previous_year_fact(facts, OPERATING_CASH_TAGS, operating_cash)
    previous_capex = _previous_year_fact(facts, CAPEX_TAGS, capex)
    cash = _latest_fact(facts, ("CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "CashAndCashEquivalents"), units=(currency,))
    assets = _latest_fact(facts, ("Assets",), units=(currency,))
    liabilities = _latest_fact(facts, ("Liabilities",), units=(currency,))
    shares = _latest_fact(facts, ("EntityCommonStockSharesOutstanding",), units=("shares",))

    operating_cash_value = _value(operating_cash)
    capex_value = _value(capex)
    free_cash_flow = (
        operating_cash_value - capex_value
        if isinstance(operating_cash_value, (int, float)) and isinstance(capex_value, (int, float))
        else None
    )
    previous_operating_cash_value = _value(previous_operating_cash)
    previous_capex_value = _value(previous_capex)
    previous_free_cash_flow = (
        previous_operating_cash_value - previous_capex_value
        if isinstance(previous_operating_cash_value, (int, float)) and isinstance(previous_capex_value, (int, float))
        else None
    )
    filed_dates = [
        fact.get("filed")
        for fact in (revenue, net_income, operating_cash, cash, assets, liabilities, shares)
        if fact and fact.get("filed")
    ]
    annual_trend = _build_trend(facts, 330, 400, 6, currency)
    quarterly_trend = _build_trend(facts, 70, 110, 12, currency)
    latest_quarter = quarterly_trend[0] if quarterly_trend else {}
    latest_quarter_end = latest_quarter.get("结束日")
    previous_quarter = next(
        (
            row for row in quarterly_trend[1:]
            if latest_quarter_end
            and 330 <= (date.fromisoformat(latest_quarter_end) - date.fromisoformat(row["结束日"])).days <= 400
        ),
        {},
    )
    quarter_start = latest_quarter.get("开始日")
    quarter_end = latest_quarter.get("结束日")
    return {
        "公司名称": facts.get("entityName") or company_name,
        "SEC_CIK": cik,
        "财务货币": currency,
        "最新申报收入": latest_quarter.get("收入", _value(revenue)),
        "上年同期收入": previous_quarter.get("收入", _value(previous_revenue)),
        "收入同比增长率": latest_quarter.get("收入同比增长率"),
        "收入申报表类型": "季度口径（SEC 10-Q/10-K派生）",
        "收入期间开始日": quarter_start,
        "收入报告期结束日": quarter_end,
        "最新申报净利润": latest_quarter.get("净利润", _value(net_income)),
        "上年同期净利润": previous_quarter.get("净利润", _value(previous_net_income)),
        "净利润同比增长率": latest_quarter.get("净利润同比增长率"),
        "净利润申报表类型": "季度口径（SEC 10-Q/10-K派生）",
        "净利润期间开始日": quarter_start,
        "净利润报告期结束日": quarter_end,
        "最新申报经营现金流": latest_quarter.get("经营现金流", operating_cash_value),
        "上年同期经营现金流": previous_quarter.get("经营现金流", previous_operating_cash_value),
        "经营现金流同比增长率": _growth(latest_quarter.get("经营现金流"), previous_quarter.get("经营现金流")),
        "最新申报资本开支": latest_quarter.get("资本开支", capex_value),
        "上年同期资本开支": previous_quarter.get("资本开支", previous_capex_value),
        "资本开支同比增长率": _growth(latest_quarter.get("资本开支"), previous_quarter.get("资本开支")),
        "计算自由现金流": latest_quarter.get("自由现金流", free_cash_flow),
        "上年同期自由现金流": previous_quarter.get("自由现金流", previous_free_cash_flow),
        "自由现金流同比增长率": latest_quarter.get("自由现金流同比增长率"),
        "上年同期期间开始日": previous_quarter.get("开始日"),
        "上年同期期间结束日": previous_quarter.get("结束日"),
        "现金流期间开始日": quarter_start,
        "现金流期间结束日": quarter_end,
        "经营现金流口径": latest_quarter.get("经营现金流口径"),
        "资本开支口径": latest_quarter.get("资本开支口径"),
        "资本开支组成": latest_quarter.get("资本开支组成"),
        "现金总额": _value(cash),
        "资产总额": _value(assets),
        "负债总额": _value(liabilities),
        "流通股数": _value(shares),
        "SEC最新申报日期": max(filed_dates) if filed_dates else None,
        "年度财务趋势": annual_trend[:5],
        "季度财务趋势": quarterly_trend[:8],
    }
