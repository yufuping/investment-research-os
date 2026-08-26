from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy.inspection import inspect

from investment_os.knowledge.repository import KnowledgeRepository


def serialize(value: Any) -> Any:
    """把 ORM 结果转换为适合 MCP/HTTP 返回的纯 JSON 数据。"""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (UUID, Decimal, date, datetime, Enum)):
        return str(value)
    if isinstance(value, list):
        return [serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: serialize(item) for key, item in value.items()}
    mapper = inspect(value, raiseerr=False)
    if mapper is not None and hasattr(mapper, "mapper"):
        return {column.key: serialize(getattr(value, column.key)) for column in mapper.mapper.column_attrs}
    raise TypeError(f"不支持序列化的类型：{type(value).__name__}")


class KnowledgeService:
    """面向 ChatGPT 工具层的窄接口，不向调用方暴露 SQLAlchemy 对象。"""

    def __init__(self, repository: KnowledgeRepository) -> None:
        self.repository = repository

    def get_company_memory(self, ticker: str) -> dict[str, Any]:
        memory = self.repository.get_company_memory(ticker)
        if memory is None:
            return {"found": False, "ticker": ticker.upper().strip()}
        return {"found": True, **serialize(memory)}

    def search_memory(self, query: str, *, ticker: str | None = None, limit: int = 20) -> dict[str, Any]:
        results = self.repository.search_memory(query, ticker=ticker, limit=limit)
        return {"query": query, "count": len(results), "results": serialize(results)}

    def save_thesis(
        self,
        ticker: str,
        company_name: str,
        thesis: str,
        *,
        confidence: Decimal | None = None,
        supersedes_thesis_id: UUID | None = None,
        supporting_evidence: list[dict] | None = None,
        contrary_evidence: list[dict] | None = None,
    ) -> dict[str, Any]:
        company = self.repository.get_or_create_company(ticker, company_name)
        item = self.repository.append_thesis(
            company.id,
            thesis,
            confidence=confidence,
            supersedes_thesis_id=supersedes_thesis_id,
            supporting_evidence=supporting_evidence,
            contrary_evidence=contrary_evidence,
        )
        return {"saved": True, "ticker": company.ticker, "thesis": serialize(item)}

    def save_assumption(self, ticker: str, company_name: str, description: str, impact: str, *, confidence: Decimal | None = None) -> dict[str, Any]:
        company = self.repository.get_or_create_company(ticker, company_name)
        item = self.repository.save_assumption(company.id, description, impact, confidence=confidence)
        return {"saved": True, "ticker": company.ticker, "assumption": serialize(item)}

    def save_prediction(self, ticker: str, company_name: str, prediction: str, *, confidence: Decimal | None = None) -> dict[str, Any]:
        company = self.repository.get_or_create_company(ticker, company_name)
        item = self.repository.save_prediction(company.id, prediction, confidence=confidence)
        return {"saved": True, "ticker": company.ticker, "prediction": serialize(item)}

    def save_critical_unknown(self, ticker: str, company_name: str, description: str, impact: str, *, confidence: Decimal | None = None) -> dict[str, Any]:
        company = self.repository.get_or_create_company(ticker, company_name)
        item = self.repository.save_critical_unknown(company.id, description, impact, confidence=confidence)
        return {"saved": True, "ticker": company.ticker, "critical_unknown": serialize(item)}

    def save_watch_variable(
        self,
        ticker: str,
        company_name: str,
        name: str,
        rationale: str,
        *,
        current_assessment: str | None = None,
    ) -> dict[str, Any]:
        company = self.repository.get_or_create_company(ticker, company_name)
        item = self.repository.save_watch_variable(
            company.id,
            name,
            rationale,
            current_assessment=current_assessment,
        )
        return {"saved": True, "ticker": company.ticker, "watch_variable": serialize(item)}

    def save_valuation(
        self,
        ticker: str,
        company_name: str,
        *,
        reference_price: Decimal | None,
        currency: str = "USD",
        target_return_pct: Decimal | None = None,
        bear_expected_return_pct: Decimal | None = None,
        base_expected_return_pct: Decimal | None = None,
        bull_expected_return_pct: Decimal | None = None,
        assumptions: dict[str, Any] | None = None,
        scenarios: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        company = self.repository.get_or_create_company(ticker, company_name)
        recorded_assumptions = dict(assumptions or {})
        recorded_assumptions["recorded_via"] = "investment_research_os_mcp"
        item = self.repository.save_valuation(
            company.id,
            reference_price=reference_price,
            currency=currency,
            target_return=_pct_to_fraction(target_return_pct),
            bear_expected_return=_pct_to_fraction(bear_expected_return_pct),
            base_expected_return=_pct_to_fraction(base_expected_return_pct),
            bull_expected_return=_pct_to_fraction(bull_expected_return_pct),
            assumptions=recorded_assumptions,
            scenarios=scenarios,
        )
        return {"saved": True, "ticker": company.ticker, "valuation": serialize(item)}

    def get_valuation_history(self, ticker: str, *, limit: int = 20) -> dict[str, Any]:
        company = self.repository.get_company(ticker)
        if company is None:
            return {"found": False, "ticker": ticker.upper().strip(), "valuations": []}
        items = self.repository.list_valuation_history(company.id, limit=limit)
        serialized = serialize(items)
        result: dict[str, Any] = {
            "found": True,
            "ticker": company.ticker,
            "count": len(items),
            "valuations": serialized,
        }
        if len(items) >= 2:
            result["latest_change"] = _valuation_change(serialized[0], serialized[1])
        return result

    def save_confirmed_decision(
        self,
        ticker: str,
        company_name: str,
        action: str,
        core_thesis: str,
        *,
        explicit_user_confirmation: bool,
        price: Decimal | None = None,
        currency: str | None = None,
        quantity: Decimal | None = None,
        quantity_unit: str | None = None,
        position_weight_pct: Decimal | None = None,
        target_return_pct: Decimal | None = None,
        decision_type: str | None = None,
        expected_returns: dict[str, Any] | None = None,
        critical_assumptions: list[str] | None = None,
        major_risks: list[str] | None = None,
        buy_more_conditions: list[str] | None = None,
        sell_conditions: list[str] | None = None,
        confidence: Decimal | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        company = self.repository.get_or_create_company(ticker, company_name)
        item = self.repository.save_confirmed_decision(
            company.id,
            action,
            core_thesis,
            explicit_user_confirmation=explicit_user_confirmation,
            price=price,
            currency=currency,
            quantity=quantity,
            quantity_unit=quantity_unit,
            position_size=_pct_to_fraction(position_weight_pct),
            target_return=_pct_to_fraction(target_return_pct),
            decision_type=decision_type,
            expected_returns=expected_returns,
            critical_assumptions=critical_assumptions,
            major_risks=major_risks,
            buy_more_conditions=buy_more_conditions,
            sell_conditions=sell_conditions,
            confidence=confidence,
            notes=notes,
            recorded_via="investment_research_os_mcp",
        )
        return {"saved": True, "ticker": company.ticker, "decision": serialize(item)}

    def get_decision_history(self, ticker: str, *, limit: int = 20) -> dict[str, Any]:
        company = self.repository.get_company(ticker)
        if company is None:
            return {"found": False, "ticker": ticker.upper().strip(), "count": 0, "decisions": []}
        items = self.repository.list_decision_history(company.id, limit=limit)
        return {
            "found": True,
            "ticker": company.ticker,
            "count": len(items),
            "decisions": serialize(items),
        }

    def save_discussion_summary(
        self,
        ticker: str,
        company_name: str,
        title: str,
        summary: str,
        *,
        explicit_user_confirmation: bool,
        key_points: list[str] | None = None,
        changed_views: list[str] | None = None,
        conclusions: list[str] | None = None,
        unresolved_questions: list[str] | None = None,
        follow_up_items: list[str] | None = None,
        source_chat_reference: str | None = None,
        related_report_id: str | None = None,
    ) -> dict[str, Any]:
        company = self.repository.get_or_create_company(ticker, company_name)
        item = self.repository.save_discussion_summary(
            company.id,
            title,
            summary,
            explicit_user_confirmation=explicit_user_confirmation,
            key_points=key_points,
            changed_views=changed_views,
            conclusions=conclusions,
            unresolved_questions=unresolved_questions,
            follow_up_items=follow_up_items,
            source_chat_reference=source_chat_reference,
            related_report_id=related_report_id,
            recorded_via="investment_research_os_mcp",
        )
        return {"saved": True, "ticker": company.ticker, "discussion_summary": serialize(item)}

    def get_discussion_history(self, ticker: str, *, limit: int = 20) -> dict[str, Any]:
        company = self.repository.get_company(ticker)
        if company is None:
            return {"found": False, "ticker": ticker.upper().strip(), "count": 0, "discussion_summaries": []}
        items = self.repository.list_discussion_history(company.id, limit=limit)
        return {
            "found": True,
            "ticker": company.ticker,
            "count": len(items),
            "discussion_summaries": serialize(items),
        }

    def create_report_draft(
        self,
        ticker: str,
        company_name: str,
        title: str,
        *,
        explicit_user_confirmation: bool,
        summary: str | None = None,
    ) -> dict[str, Any]:
        company = self.repository.get_or_create_company(ticker, company_name)
        item = self.repository.create_report_draft(
            company.id,
            title,
            explicit_user_confirmation=explicit_user_confirmation,
            summary=summary,
        )
        return {"saved": True, "ticker": company.ticker, "report": serialize(item)}

    def append_report_section(self, report_id: UUID, section_order: int, heading: str, content: str) -> dict[str, Any]:
        item = self.repository.append_report_section(report_id, section_order, heading, content)
        return {"saved": True, "section": serialize(item)}

    def finalize_report(
        self,
        report_id: UUID,
        *,
        explicit_user_confirmation: bool,
        change_summary: list[str] | None = None,
    ) -> dict[str, Any]:
        item = self.repository.finalize_report(
            report_id,
            explicit_user_confirmation=explicit_user_confirmation,
            change_summary=change_summary,
        )
        return {"saved": True, "report": serialize(item)}

    def get_saved_report(self, report_id: UUID) -> dict[str, Any]:
        result = self.repository.get_saved_report(report_id)
        if result is None:
            return {"found": False, "report_id": str(report_id)}
        serialized = serialize(result)
        markdown = "\n\n".join(
            f"## {section['heading']}\n\n{section['content']}" for section in serialized["sections"]
        )
        return {"found": True, **serialized, "markdown": markdown}

    def get_saved_report_history(self, ticker: str, *, limit: int = 20) -> dict[str, Any]:
        company = self.repository.get_company(ticker)
        if company is None:
            return {"found": False, "ticker": ticker.upper().strip(), "count": 0, "reports": []}
        items = self.repository.list_saved_report_history(company.id, limit=limit)
        return {"found": True, "ticker": company.ticker, "count": len(items), "reports": serialize(items)}


def _pct_to_fraction(value: Decimal | None) -> Decimal | None:
    return value / Decimal("100") if value is not None else None


def _valuation_change(latest: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    fields = ("reference_price", "target_return", "bear_expected_return", "base_expected_return", "bull_expected_return")
    changes: dict[str, Any] = {
        "latest_valuation_id": latest["id"],
        "previous_valuation_id": previous["id"],
    }
    for field in fields:
        current = Decimal(latest[field]) if latest.get(field) is not None else None
        prior = Decimal(previous[field]) if previous.get(field) is not None else None
        changes[f"{field}_change"] = str(current - prior) if current is not None and prior is not None else None
    return changes
