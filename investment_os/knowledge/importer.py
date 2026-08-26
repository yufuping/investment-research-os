from decimal import Decimal
from typing import Any

from investment_os.knowledge.repository import KnowledgeRepository


def import_company_baseline(repository: KnowledgeRepository, payload: dict[str, Any]) -> dict[str, int | str]:
    """从人工复核过的结构化数据导入公司基线；按内容去重，可安全重复执行。"""
    ticker = str(payload.get("ticker", "")).upper().strip()
    company_name = str(payload.get("company_name", "")).strip()
    if not ticker or not company_name:
        raise ValueError("基线必须包含 ticker 和 company_name")

    company = repository.get_or_create_company(ticker, company_name, payload.get("exchange"))
    memory = repository.get_company_memory(ticker) or {}
    counts = {"theses": 0, "assumptions": 0, "critical_unknowns": 0, "watch_variables": 0}

    existing_theses = {item.thesis for item in memory.get("theses", [])}
    thesis = payload.get("thesis")
    if thesis and thesis["text"].strip() not in existing_theses:
        repository.append_thesis(
            company.id,
            thesis["text"],
            confidence=_decimal(thesis.get("confidence")),
            supporting_evidence=thesis.get("supporting_evidence", []),
            contrary_evidence=thesis.get("contrary_evidence", []),
        )
        counts["theses"] += 1

    existing_assumptions = {item.description for item in memory.get("assumptions", [])}
    for item in payload.get("assumptions", []):
        if item["description"].strip() in existing_assumptions:
            continue
        repository.save_assumption(
            company.id,
            item["description"],
            item["impact"],
            confidence=_decimal(item.get("confidence")),
            evidence=item.get("evidence", []),
        )
        counts["assumptions"] += 1

    existing_unknowns = {item.description for item in memory.get("critical_unknowns", [])}
    for item in payload.get("critical_unknowns", []):
        if item["description"].strip() in existing_unknowns:
            continue
        repository.save_critical_unknown(
            company.id,
            item["description"],
            item["impact"],
            confidence=_decimal(item.get("confidence")),
            evidence_status=item.get("evidence_status", "insufficient"),
        )
        counts["critical_unknowns"] += 1

    for item in payload.get("watch_variables", []):
        before = {variable.name for variable in (repository.get_company_memory(ticker) or {}).get("watch_variables", [])}
        repository.save_watch_variable(
            company.id,
            item["name"],
            item["rationale"],
            current_assessment=item.get("current_assessment"),
        )
        if item["name"].strip() not in before:
            counts["watch_variables"] += 1

    return {"ticker": ticker, **counts}


def _decimal(value: Any) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None
