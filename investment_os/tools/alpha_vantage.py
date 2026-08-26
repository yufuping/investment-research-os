from typing import Any
import time

import requests


BASE_URL = "https://www.alphavantage.co/query"


def _request(api_key: str, function: str, ticker: str) -> dict[str, Any]:
    response = requests.get(
        BASE_URL,
        params={"function": function, "symbol": ticker, "apikey": api_key},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if "Error Message" in payload or "Information" in payload or "Note" in payload:
        message = payload.get("Error Message") or payload.get("Information") or payload.get("Note")
        raise RuntimeError(f"Alpha Vantage 返回限制或错误：{message}")
    return payload


def _number(value: Any) -> float | int | None:
    if value in (None, "", "None", "-"):
        return None
    try:
        number = float(value)
        return int(number) if number.is_integer() else number
    except (TypeError, ValueError):
        return None


def fetch_alpha_vantage(ticker: str, api_key: str) -> dict[str, Any]:
    """获取收盘报价和公司估值概览。免费报价通常为最近交易日收盘数据。"""
    quote = _request(api_key, "GLOBAL_QUOTE", ticker).get("Global Quote", {})
    # 免费密钥限制突发请求频率；两个端点之间主动间隔，避免每秒限制。
    time.sleep(1.2)
    overview = _request(api_key, "OVERVIEW", ticker)
    if not quote and not overview:
        raise RuntimeError("Alpha Vantage 未返回可用数据")
    return {
        "公司名称": overview.get("Name"),
        "行业板块": overview.get("Sector"),
        "细分行业": overview.get("Industry"),
        "所属国家": overview.get("Country"),
        "公司简介": overview.get("Description"),
        "交易货币": overview.get("Currency"),
        "当前价格": _number(quote.get("05. price")),
        "价格日期": quote.get("07. latest trading day"),
        "市值": _number(overview.get("MarketCapitalization")),
        "滚动市盈率": _number(overview.get("PERatio")),
        "预期市盈率": _number(overview.get("ForwardPE")),
        "每股收益_TTM": _number(overview.get("DilutedEPSTTM")),
        "市销率": _number(overview.get("PriceToSalesRatioTTM")),
        "企业价值倍数_EV_EBITDA": _number(overview.get("EVToEBITDA")),
        "Alpha_Vantage_最近季度": overview.get("LatestQuarter"),
    }
