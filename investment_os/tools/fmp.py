from datetime import UTC, datetime
from typing import Any

import requests


BASE_URL = "https://financialmodelingprep.com/stable"


def _request(endpoint: str, ticker: str, api_key: str) -> list[dict[str, Any]]:
    response = requests.get(
        f"{BASE_URL}/{endpoint}",
        params={"symbol": ticker, "apikey": api_key},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict) and (payload.get("Error Message") or payload.get("error")):
        raise RuntimeError(payload.get("Error Message") or payload.get("error"))
    if not isinstance(payload, list):
        raise RuntimeError("FMP 返回格式异常")
    return payload


def _number(value: Any) -> float | int | None:
    if value in (None, "", "None", "-"):
        return None
    try:
        number = float(value)
        return int(number) if number.is_integer() else number
    except (TypeError, ValueError):
        return None


def fetch_fmp(ticker: str, api_key: str) -> dict[str, Any]:
    """从 FMP 获取报价与公司资料；任一端点成功即可返回可用字段。"""
    quote: dict[str, Any] = {}
    profile: dict[str, Any] = {}
    errors: list[str] = []
    for endpoint, target in (("quote", "quote"), ("profile", "profile")):
        try:
            rows = _request(endpoint, ticker, api_key)
            if rows:
                if target == "quote":
                    quote = rows[0]
                else:
                    profile = rows[0]
        except Exception as exc:
            errors.append(f"{endpoint}:{type(exc).__name__}")
    if not quote and not profile:
        raise RuntimeError("FMP 未返回可用数据（" + "；".join(errors) + "）")

    timestamp = quote.get("timestamp")
    price_date = None
    if isinstance(timestamp, (int, float)):
        price_date = datetime.fromtimestamp(timestamp, tz=UTC).date().isoformat()
    return {
        "公司名称": profile.get("companyName") or quote.get("name"),
        "行业板块": profile.get("sector"),
        "细分行业": profile.get("industry"),
        "所属国家": profile.get("country"),
        "公司网站": profile.get("website"),
        "公司简介": profile.get("description"),
        "交易货币": profile.get("currency") or quote.get("currency"),
        "当前价格": _number(quote.get("price") or profile.get("price")),
        "价格日期": price_date,
        "市值": _number(quote.get("marketCap") or profile.get("marketCap")),
        "滚动市盈率": _number(quote.get("pe")),
        "每股收益_TTM": _number(quote.get("eps")),
        "流通股数": _number(quote.get("sharesOutstanding")),
    }
