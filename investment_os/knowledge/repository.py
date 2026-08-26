from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Engine, create_engine, func, or_, select
from sqlalchemy.orm import Session

from investment_os.knowledge.models import (
    Assumption,
    Company,
    CriticalUnknown,
    Decision,
    DiscussionSummary,
    KnowledgeBase,
    Prediction,
    SavedResearchReport,
    SavedResearchReportSection,
    Thesis,
    Valuation,
    WatchVariable,
)


class KnowledgeRepository:
    """面向 Neon/PostgreSQL 的结构化记忆仓库；不会自动创建生产表。"""

    def __init__(self, database_url: str, *, create_schema: bool = False) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)
        if create_schema:
            KnowledgeBase.metadata.create_all(self.engine)

    @classmethod
    def from_engine(cls, engine: Engine, *, create_schema: bool = False) -> "KnowledgeRepository":
        repository = cls.__new__(cls)
        repository.engine = engine
        if create_schema:
            KnowledgeBase.metadata.create_all(engine)
        return repository

    def get_or_create_company(self, ticker: str, name: str, exchange: str | None = None) -> Company:
        normalized = ticker.upper().strip()
        if not normalized or not name.strip():
            raise ValueError("股票代码和公司名称不能为空")
        with Session(self.engine) as session:
            company = session.scalar(select(Company).where(Company.ticker == normalized))
            if company is None:
                company = Company(ticker=normalized, name=name.strip(), exchange=exchange)
                session.add(company)
                session.commit()
                session.refresh(company)
            session.expunge(company)
            return company

    def get_company(self, ticker: str) -> Company | None:
        normalized = ticker.upper().strip()
        with Session(self.engine) as session:
            company = session.scalar(select(Company).where(Company.ticker == normalized))
            if company is not None:
                session.expunge(company)
            return company

    def append_thesis(
        self,
        company_id: UUID,
        thesis: str,
        *,
        confidence: Decimal | None = None,
        supersedes_thesis_id: UUID | None = None,
        supporting_evidence: list[dict] | None = None,
        contrary_evidence: list[dict] | None = None,
    ) -> Thesis:
        if not thesis.strip():
            raise ValueError("投资论点不能为空")
        if confidence is not None and not Decimal("0") <= confidence <= Decimal("1"):
            raise ValueError("置信度必须在 0 到 1 之间")
        with Session(self.engine) as session:
            if session.get(Company, company_id) is None:
                raise LookupError("找不到对应公司")
            if supersedes_thesis_id is not None:
                previous = session.get(Thesis, supersedes_thesis_id)
                if previous is None or previous.company_id != company_id:
                    raise ValueError("被替代论点必须属于同一公司")
                previous.status = "superseded"
            item = Thesis(
                company_id=company_id,
                supersedes_thesis_id=supersedes_thesis_id,
                thesis=thesis.strip(),
                confidence=confidence,
                supporting_evidence=supporting_evidence or [],
                contrary_evidence=contrary_evidence or [],
            )
            session.add(item)
            session.commit()
            session.refresh(item)
            session.expunge(item)
            return item

    def list_thesis_history(self, company_id: UUID) -> list[Thesis]:
        with Session(self.engine) as session:
            items = list(session.scalars(
                select(Thesis)
                .where(Thesis.company_id == company_id)
                .order_by(Thesis.created_at, Thesis.id)
            ))
            for item in items:
                session.expunge(item)
            return items

    def save_assumption(
        self,
        company_id: UUID,
        description: str,
        impact: str,
        *,
        confidence: Decimal | None = None,
        evidence: list[dict] | None = None,
    ) -> Assumption:
        return self._save_company_item(
            Assumption,
            company_id,
            description=description.strip(),
            impact=impact.strip(),
            confidence=self._validate_confidence(confidence),
            evidence=evidence or [],
        )

    def save_prediction(
        self,
        company_id: UUID,
        prediction: str,
        *,
        confidence: Decimal | None = None,
        expected_verification_date=None,
    ) -> Prediction:
        return self._save_company_item(
            Prediction,
            company_id,
            prediction=prediction.strip(),
            confidence=self._validate_confidence(confidence),
            expected_verification_date=expected_verification_date,
        )

    def save_critical_unknown(
        self,
        company_id: UUID,
        description: str,
        impact: str,
        *,
        confidence: Decimal | None = None,
        evidence_status: str = "insufficient",
    ) -> CriticalUnknown:
        return self._save_company_item(
            CriticalUnknown,
            company_id,
            description=description.strip(),
            impact=impact.strip(),
            confidence=self._validate_confidence(confidence),
            evidence_status=evidence_status.strip(),
        )

    def save_watch_variable(
        self,
        company_id: UUID,
        name: str,
        rationale: str,
        *,
        current_assessment: str | None = None,
    ) -> WatchVariable:
        if not name.strip() or not rationale.strip():
            raise ValueError("跟踪变量名称和原因不能为空")
        with Session(self.engine) as session:
            self._require_company(session, company_id)
            item = session.scalar(
                select(WatchVariable).where(
                    WatchVariable.company_id == company_id,
                    WatchVariable.name == name.strip(),
                )
            )
            if item is None:
                item = WatchVariable(
                    company_id=company_id,
                    name=name.strip(),
                    rationale=rationale.strip(),
                    current_assessment=current_assessment,
                )
                session.add(item)
            else:
                item.rationale = rationale.strip()
                item.current_assessment = current_assessment
            session.commit()
            session.refresh(item)
            session.expunge(item)
            return item

    def get_company_memory(self, ticker: str) -> dict[str, object] | None:
        company = self.get_company(ticker)
        if company is None:
            return None
        model_groups = {
            "theses": Thesis,
            "assumptions": Assumption,
            "predictions": Prediction,
            "critical_unknowns": CriticalUnknown,
            "watch_variables": WatchVariable,
            "decisions": Decision,
            "discussion_summaries": DiscussionSummary,
            "saved_research_reports": SavedResearchReport,
            "valuations": Valuation,
        }
        result: dict[str, object] = {"company": company}
        with Session(self.engine) as session:
            for key, model in model_groups.items():
                items = list(
                    session.scalars(
                        select(model)
                        .where(model.company_id == company.id)
                        .order_by(model.created_at.desc())
                    )
                )
                for item in items:
                    session.expunge(item)
                result[key] = items
        return result

    def search_memory(self, query: str, *, ticker: str | None = None, limit: int = 20) -> list[dict[str, object]]:
        term = query.strip()
        if not term:
            raise ValueError("检索关键词不能为空")
        if not 1 <= limit <= 100:
            raise ValueError("limit 必须在 1 到 100 之间")
        pattern = f"%{term}%"
        searchable = (
            ("thesis", Thesis, (Thesis.thesis,)),
            ("assumption", Assumption, (Assumption.description,)),
            ("prediction", Prediction, (Prediction.prediction, Prediction.actual_result)),
            ("critical_unknown", CriticalUnknown, (CriticalUnknown.description, CriticalUnknown.resolution)),
            ("watch_variable", WatchVariable, (WatchVariable.name, WatchVariable.rationale, WatchVariable.current_assessment)),
            ("discussion_summary", DiscussionSummary, (DiscussionSummary.title, DiscussionSummary.summary)),
        )
        results: list[dict[str, object]] = []
        with Session(self.engine) as session:
            for memory_type, model, columns in searchable:
                statement = select(model, Company.ticker).join(Company, model.company_id == Company.id)
                statement = statement.where(or_(*(column.ilike(pattern) for column in columns)))
                if ticker:
                    statement = statement.where(Company.ticker == ticker.upper().strip())
                for item, company_ticker in session.execute(statement.limit(limit)):
                    results.append({"type": memory_type, "ticker": company_ticker, "item": item})
                    if len(results) >= limit:
                        return results
        return results

    def save_valuation(
        self,
        company_id: UUID,
        *,
        reference_price: Decimal | None,
        currency: str = "USD",
        target_return: Decimal | None = None,
        base_expected_return: Decimal | None = None,
        bear_expected_return: Decimal | None = None,
        bull_expected_return: Decimal | None = None,
        assumptions: dict | None = None,
        scenarios: dict | None = None,
    ) -> Valuation:
        if reference_price is not None and reference_price <= 0:
            raise ValueError("参考价格必须大于 0")
        if not currency.strip():
            raise ValueError("货币不能为空")
        return self._save_company_item(
            Valuation,
            company_id,
            reference_price=reference_price,
            currency=currency.upper().strip(),
            target_return=target_return,
            base_expected_return=base_expected_return,
            bear_expected_return=bear_expected_return,
            bull_expected_return=bull_expected_return,
            assumptions=assumptions or {},
            scenarios=scenarios or {},
        )

    def list_valuation_history(self, company_id: UUID, *, limit: int = 20) -> list[Valuation]:
        if not 1 <= limit <= 100:
            raise ValueError("limit 必须在 1 到 100 之间")
        with Session(self.engine) as session:
            items = list(
                session.scalars(
                    select(Valuation)
                    .where(Valuation.company_id == company_id)
                    .order_by(Valuation.valuation_date.desc(), Valuation.created_at.desc())
                    .limit(limit)
                )
            )
            for item in items:
                session.expunge(item)
            return items

    @staticmethod
    def _validate_confidence(confidence: Decimal | None) -> Decimal | None:
        if confidence is not None and not Decimal("0") <= confidence <= Decimal("1"):
            raise ValueError("置信度必须在 0 到 1 之间")
        return confidence

    @staticmethod
    def _require_company(session: Session, company_id: UUID) -> None:
        if session.get(Company, company_id) is None:
            raise LookupError("找不到对应公司")

    def _save_company_item(self, model, company_id: UUID, **values):
        text_values = [value for value in values.values() if isinstance(value, str)]
        if any(not value for value in text_values):
            raise ValueError("必填文本字段不能为空")
        with Session(self.engine) as session:
            self._require_company(session, company_id)
            item = model(company_id=company_id, **values)
            session.add(item)
            session.commit()
            session.refresh(item)
            session.expunge(item)
            return item

    def save_confirmed_decision(
        self,
        company_id: UUID,
        action: str,
        core_thesis: str,
        *,
        explicit_user_confirmation: bool,
        price: Decimal | None = None,
        currency: str | None = None,
        quantity: Decimal | None = None,
        quantity_unit: str | None = None,
        position_size: Decimal | None = None,
        target_return: Decimal | None = None,
        decision_type: str | None = None,
        expected_returns: dict | None = None,
        critical_assumptions: list[str] | None = None,
        major_risks: list[str] | None = None,
        buy_more_conditions: list[str] | None = None,
        sell_conditions: list[str] | None = None,
        confidence: Decimal | None = None,
        notes: str | None = None,
        recorded_via: str | None = None,
    ) -> Decision:
        if not explicit_user_confirmation:
            raise PermissionError("没有用户明确确认，不得保存真实投资决策")
        if not action.strip() or not core_thesis.strip():
            raise ValueError("决策类型和核心论点不能为空")
        allowed_actions = {"买入", "卖出", "加仓", "减仓", "持有", "清仓", "建立观察仓", "退出观察仓"}
        normalized_action = action.strip()
        if normalized_action not in allowed_actions:
            raise ValueError(f"决策动作必须是：{'、'.join(sorted(allowed_actions))}")
        if price is not None and price <= 0:
            raise ValueError("成交价格必须大于 0")
        if quantity is not None and quantity <= 0:
            raise ValueError("成交数量必须大于 0")
        if (quantity is None) != (not quantity_unit or not quantity_unit.strip()):
            raise ValueError("成交数量和数量单位必须同时提供，例如 3 股")
        if position_size is not None and not Decimal("0") <= position_size <= Decimal("1"):
            raise ValueError("组合仓位必须在 0 到 1 之间")
        validated_confidence = self._validate_confidence(confidence)
        with Session(self.engine) as session:
            if session.get(Company, company_id) is None:
                raise LookupError("找不到对应公司")
            decision = Decision(
                company_id=company_id,
                action=normalized_action,
                core_thesis=core_thesis.strip(),
                explicit_user_confirmation=True,
                price=price,
                currency=currency.upper().strip() if currency else None,
                quantity=quantity,
                quantity_unit=quantity_unit.strip() if quantity_unit else None,
                position_size=position_size,
                target_return=target_return,
                decision_type=decision_type.strip() if decision_type else None,
                expected_returns=expected_returns or {},
                critical_assumptions=critical_assumptions or [],
                major_risks=major_risks or [],
                buy_more_conditions=buy_more_conditions or [],
                sell_conditions=sell_conditions or [],
                confidence=validated_confidence,
                notes=notes.strip() if notes else None,
                recorded_via=recorded_via,
            )
            session.add(decision)
            session.commit()
            session.refresh(decision)
            session.expunge(decision)
            return decision

    def list_decision_history(self, company_id: UUID, *, limit: int = 20) -> list[Decision]:
        if not 1 <= limit <= 100:
            raise ValueError("limit 必须在 1 到 100 之间")
        with Session(self.engine) as session:
            items = list(
                session.scalars(
                    select(Decision)
                    .where(Decision.company_id == company_id)
                    .order_by(Decision.decision_date.desc(), Decision.created_at.desc())
                    .limit(limit)
                )
            )
            for item in items:
                session.expunge(item)
            return items

    def save_discussion_summary(
        self,
        company_id: UUID,
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
        recorded_via: str | None = None,
    ) -> DiscussionSummary:
        if not explicit_user_confirmation:
            raise PermissionError("没有用户明确确认，不得保存对话纪要")
        if not title.strip() or not summary.strip():
            raise ValueError("讨论标题和摘要不能为空")
        with Session(self.engine) as session:
            self._require_company(session, company_id)
            item = DiscussionSummary(
                company_id=company_id,
                title=title.strip(),
                summary=summary.strip(),
                key_points=key_points or [],
                changed_views=changed_views or [],
                conclusions=conclusions or [],
                unresolved_questions=unresolved_questions or [],
                follow_up_items=follow_up_items or [],
                source_chat_reference=source_chat_reference.strip() if source_chat_reference else None,
                related_report_id=related_report_id.strip() if related_report_id else None,
                explicit_user_confirmation=True,
                recorded_via=recorded_via,
            )
            session.add(item)
            session.commit()
            session.refresh(item)
            session.expunge(item)
            return item

    def list_discussion_history(self, company_id: UUID, *, limit: int = 20) -> list[DiscussionSummary]:
        if not 1 <= limit <= 100:
            raise ValueError("limit 必须在 1 到 100 之间")
        with Session(self.engine) as session:
            items = list(
                session.scalars(
                    select(DiscussionSummary)
                    .where(DiscussionSummary.company_id == company_id)
                    .order_by(DiscussionSummary.discussion_date.desc(), DiscussionSummary.created_at.desc())
                    .limit(limit)
                )
            )
            for item in items:
                session.expunge(item)
            return items

    def create_report_draft(
        self,
        company_id: UUID,
        title: str,
        *,
        explicit_user_confirmation: bool,
        summary: str | None = None,
    ) -> SavedResearchReport:
        if not explicit_user_confirmation:
            raise PermissionError("没有用户明确确认，不得创建正式研报草稿")
        if not title.strip():
            raise ValueError("研报标题不能为空")
        with Session(self.engine) as session:
            self._require_company(session, company_id)
            latest_version = session.scalar(
                select(func.max(SavedResearchReport.version)).where(SavedResearchReport.company_id == company_id)
            ) or 0
            previous = session.scalar(
                select(SavedResearchReport)
                .where(SavedResearchReport.company_id == company_id, SavedResearchReport.status == "finalized")
                .order_by(SavedResearchReport.version.desc())
                .limit(1)
            )
            item = SavedResearchReport(
                company_id=company_id,
                previous_report_id=previous.id if previous else None,
                version=latest_version + 1,
                title=title.strip(),
                summary=summary.strip() if summary else None,
                explicit_user_confirmation=True,
                generated_by="chatgpt_frontend",
            )
            session.add(item)
            session.commit()
            session.refresh(item)
            session.expunge(item)
            return item

    def append_report_section(
        self,
        report_id: UUID,
        section_order: int,
        heading: str,
        content: str,
    ) -> SavedResearchReportSection:
        if section_order < 1:
            raise ValueError("章节序号必须大于等于 1")
        if not heading.strip() or not content.strip():
            raise ValueError("章节标题和内容不能为空")
        with Session(self.engine) as session:
            report = session.get(SavedResearchReport, report_id)
            if report is None:
                raise LookupError("找不到研报草稿")
            if report.status != "draft":
                raise ValueError("正式研报已经定稿，不能继续修改")
            item = session.scalar(
                select(SavedResearchReportSection).where(
                    SavedResearchReportSection.report_id == report_id,
                    SavedResearchReportSection.section_order == section_order,
                )
            )
            if item is None:
                item = SavedResearchReportSection(
                    report_id=report_id,
                    section_order=section_order,
                    heading=heading.strip(),
                    content=content.strip(),
                )
                session.add(item)
            else:
                item.heading = heading.strip()
                item.content = content.strip()
            session.commit()
            session.refresh(item)
            session.expunge(item)
            return item

    def finalize_report(
        self,
        report_id: UUID,
        *,
        explicit_user_confirmation: bool,
        change_summary: list[str] | None = None,
    ) -> SavedResearchReport:
        if not explicit_user_confirmation:
            raise PermissionError("没有用户明确确认，不得将研报定稿")
        with Session(self.engine) as session:
            report = session.get(SavedResearchReport, report_id)
            if report is None:
                raise LookupError("找不到研报草稿")
            if report.status == "finalized":
                session.expunge(report)
                return report
            section_count = session.scalar(
                select(func.count()).select_from(SavedResearchReportSection).where(SavedResearchReportSection.report_id == report_id)
            )
            if not section_count:
                raise ValueError("研报没有任何章节，不能定稿")
            report.status = "finalized"
            report.change_summary = change_summary or []
            report.finalized_at = datetime.now(UTC)
            session.commit()
            session.refresh(report)
            session.expunge(report)
            return report

    def get_saved_report(self, report_id: UUID) -> dict[str, object] | None:
        with Session(self.engine) as session:
            report = session.get(SavedResearchReport, report_id)
            if report is None:
                return None
            sections = list(session.scalars(
                select(SavedResearchReportSection)
                .where(SavedResearchReportSection.report_id == report_id)
                .order_by(SavedResearchReportSection.section_order)
            ))
            session.expunge(report)
            for section in sections:
                session.expunge(section)
            return {"report": report, "sections": sections}

    def list_saved_report_history(self, company_id: UUID, *, limit: int = 20) -> list[SavedResearchReport]:
        if not 1 <= limit <= 100:
            raise ValueError("limit 必须在 1 到 100 之间")
        with Session(self.engine) as session:
            items = list(session.scalars(
                select(SavedResearchReport)
                .where(SavedResearchReport.company_id == company_id)
                .order_by(SavedResearchReport.version.desc())
                .limit(limit)
            ))
            for item in items:
                session.expunge(item)
            return items
