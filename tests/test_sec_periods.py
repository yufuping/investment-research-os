import pytest

from investment_os.tools.sec_edgar import _build_trend, _growth, _reporting_currency


def _item(form: str, start: str, end: str, value: float, filed: str) -> dict:
    return {"form": form, "start": start, "end": end, "val": value, "filed": filed}


def test_annual_trend_excludes_ttm_facts_filed_in_10q():
    revenue_items = [
        _item("10-K", "2024-01-01", "2024-12-31", 100.0, "2025-02-01"),
        _item("10-Q", "2025-07-01", "2026-06-30", 150.0, "2026-07-31"),
        _item("10-Q", "2026-04-01", "2026-06-30", 40.0, "2026-07-31"),
    ]
    facts = {"facts": {"us-gaap": {
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": revenue_items}},
        "NetIncomeLoss": {"units": {"USD": [
            _item("10-K", "2024-01-01", "2024-12-31", 10.0, "2025-02-01"),
            _item("10-Q", "2025-07-01", "2026-06-30", 20.0, "2026-07-31"),
            _item("10-Q", "2026-04-01", "2026-06-30", 6.0, "2026-07-31"),
        ]}},
    }}}

    annual = _build_trend(facts, 330, 400, 6)
    quarterly = _build_trend(facts, 70, 110, 12)

    assert [row["结束日"] for row in annual] == ["2024-12-31"]
    assert quarterly[0]["结束日"] == "2026-06-30"
    assert quarterly[0]["收入"] == 40.0


def test_ifrs_20f_uses_native_reporting_currency():
    facts = {"facts": {"ifrs-full": {
        "Revenue": {"units": {"TWD": [
            _item("20-F", "2024-01-01", "2024-12-31", 1000.0, "2025-04-01"),
            _item("20-F", "2025-01-01", "2025-12-31", 1200.0, "2026-04-01"),
        ]}},
        "ProfitLoss": {"units": {"TWD": [
            _item("20-F", "2024-01-01", "2024-12-31", 200.0, "2025-04-01"),
            _item("20-F", "2025-01-01", "2025-12-31", 260.0, "2026-04-01"),
        ]}},
    }}}
    assert _reporting_currency(facts) == "TWD"
    rows = _build_trend(facts, 330, 400, 6, "TWD")
    assert rows[0]["收入"] == 1200.0
    assert rows[0]["收入同比增长率"] == 20.0


def test_consolidated_revenues_win_over_component_revenue_for_same_period():
    facts = {"facts": {"us-gaap": {
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
            _item("10-Q", "2026-04-01", "2026-06-30", 34.0, "2026-08-05"),
        ]}},
        "Revenues": {"units": {"USD": [
            _item("10-Q", "2026-04-01", "2026-06-30", 701.0, "2026-08-05"),
        ]}},
        "NetIncomeLoss": {"units": {"USD": [
            _item("10-Q", "2026-04-01", "2026-06-30", 48.0, "2026-08-05"),
        ]}},
    }}}

    rows = _build_trend(facts, 70, 110, 12)

    assert rows[0]["收入"] == 701.0


def test_growth_is_omitted_when_metric_crosses_profitability_boundary():
    assert _growth(48.0, -482.0) is None
    assert _growth(-70.0, 156.0) is None
    assert _growth(110.0, 100.0) == 10.0


def test_quarterly_capex_combines_tangible_assets_and_capitalized_software():
    facts = {"facts": {"us-gaap": {
        "Revenues": {"units": {"USD": [
            _item("10-Q", "2026-04-01", "2026-06-30", 701.0, "2026-08-05"),
        ]}},
        "NetIncomeLoss": {"units": {"USD": [
            _item("10-Q", "2026-04-01", "2026-06-30", 48.0, "2026-08-05"),
        ]}},
        "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [
            _item("10-Q", "2026-01-01", "2026-03-31", 21.0, "2026-05-11"),
            _item("10-Q", "2026-01-01", "2026-06-30", 539.0, "2026-08-05"),
        ]}},
        "PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"USD": [
            _item("10-Q", "2026-01-01", "2026-03-31", 9.4, "2026-05-11"),
            _item("10-Q", "2026-01-01", "2026-06-30", 10.4, "2026-08-05"),
        ]}},
        "PaymentsToDevelopSoftware": {"units": {"USD": [
            _item("10-Q", "2026-01-01", "2026-03-31", 15.6, "2026-05-11"),
            _item("10-Q", "2026-01-01", "2026-06-30", 35.8, "2026-08-05"),
        ]}},
    }}}

    row = _build_trend(facts, 70, 110, 12)[0]

    assert row["经营现金流"] == 518.0
    assert row["资本开支"] == pytest.approx(21.2)
    assert row["自由现金流"] == pytest.approx(496.8)
    assert row["经营现金流口径"] == "单季度派生（累计值相减）"
    assert "PaymentsToDevelopSoftware" in row["资本开支组成"]
