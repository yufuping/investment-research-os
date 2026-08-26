from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import create_engine, inspect

from investment_os.knowledge.models import KnowledgeBase
from investment_os.knowledge.repository import KnowledgeRepository
from investment_os.knowledge.service import KnowledgeService


EXPECTED_TABLES = {
    "assumptions",
    "companies",
    "critical_unknowns",
    "decisions",
    "discussion_summaries",
    "predictions",
    "research_sessions",
    "research_updates",
    "saved_research_report_sections",
    "saved_research_reports",
    "skill_improvements",
    "theses",
    "valuations",
    "watch_variables",
}


@pytest.fixture
def repository() -> KnowledgeRepository:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    return KnowledgeRepository.from_engine(engine, create_schema=True)


def test_knowledge_schema_is_isolated_and_complete(repository):
    assert set(inspect(repository.engine).get_table_names()) == EXPECTED_TABLES
    assert "research_runs" not in KnowledgeBase.metadata.tables


def test_company_creation_is_idempotent(repository):
    first = repository.get_or_create_company("meta", "Meta Platforms", "NASDAQ")
    second = repository.get_or_create_company("META", "Meta Platforms", "NASDAQ")

    assert first.id == second.id
    assert second.ticker == "META"


def test_thesis_history_preserves_versions(repository):
    company = repository.get_or_create_company("NVDA", "NVIDIA")
    first = repository.append_thesis(company.id, "CUDA 护城河仍然稳固", confidence=Decimal("0.75"))
    second = repository.append_thesis(
        company.id,
        "CUDA 仍强，但 ASIC 与软件抽象层正在降低切换成本",
        confidence=Decimal("0.65"),
        supersedes_thesis_id=first.id,
        contrary_evidence=[{"type": "事实", "text": "大型客户持续开发自研芯片"}],
    )

    history = repository.list_thesis_history(company.id)
    assert [item.id for item in history] == [first.id, second.id]
    assert history[0].status == "superseded"
    assert history[1].supersedes_thesis_id == first.id
    assert history[1].contrary_evidence[0]["type"] == "事实"


def test_thesis_cannot_supersede_another_company(repository):
    nvda = repository.get_or_create_company("NVDA", "NVIDIA")
    meta = repository.get_or_create_company("META", "Meta Platforms")
    old = repository.append_thesis(nvda.id, "旧论点")

    with pytest.raises(ValueError, match="同一公司"):
        repository.append_thesis(meta.id, "错误关联", supersedes_thesis_id=old.id)


def test_real_decision_requires_explicit_user_confirmation(repository):
    company = repository.get_or_create_company("CRCL", "Circle Internet Group")

    with pytest.raises(PermissionError, match="明确确认"):
        repository.save_confirmed_decision(
            company.id,
            "卖出",
            "风险补偿不足",
            explicit_user_confirmation=False,
        )

    decision = repository.save_confirmed_decision(
        company.id,
        "卖出",
        "风险补偿不足",
        explicit_user_confirmation=True,
        price=Decimal("87.98"),
        position_size=Decimal("0.001"),
        target_return=Decimal("0.20"),
    )
    assert decision.explicit_user_confirmation is True
    assert decision.action == "卖出"


def test_confirmed_decision_preserves_quantity_and_position_weight_separately(repository):
    service = KnowledgeService(repository)
    saved = service.save_confirmed_decision(
        "CRCL",
        "Circle Internet Group",
        "卖出",
        "USDC 增长不足以补偿利率周期与估值风险",
        explicit_user_confirmation=True,
        quantity=Decimal("3"),
        quantity_unit="股",
        price=Decimal("87.98"),
        currency="USD",
        decision_type="投资逻辑被证伪",
        major_risks=["收入高度依赖储备利息"],
        notes="观察仓复盘",
    )

    assert saved["decision"]["quantity"] == "3.000000"
    assert saved["decision"]["quantity_unit"] == "股"
    assert saved["decision"]["position_size"] is None
    assert saved["decision"]["recorded_via"] == "investment_research_os_mcp"

    history = service.get_decision_history("CRCL")
    assert history["count"] == 1
    assert history["decisions"][0]["decision_type"] == "投资逻辑被证伪"


def test_confirmed_decision_validates_action_quantity_and_unit(repository):
    company = repository.get_or_create_company("CRCL", "Circle Internet Group")
    with pytest.raises(ValueError, match="决策动作"):
        repository.save_confirmed_decision(
            company.id, "考虑卖出", "尚未成交", explicit_user_confirmation=True, quantity=Decimal("3"), quantity_unit="股"
        )
    with pytest.raises(ValueError, match="同时提供"):
        repository.save_confirmed_decision(
            company.id, "卖出", "风险补偿不足", explicit_user_confirmation=True, quantity=Decimal("3")
        )


def test_discussion_summary_requires_confirmation_and_is_queryable(repository):
    service = KnowledgeService(repository)
    company = repository.get_or_create_company("BABA", "Alibaba Group")

    with pytest.raises(PermissionError, match="明确确认"):
        repository.save_discussion_summary(
            company.id,
            "阿里巴巴长期竞争力讨论",
            "讨论了电商份额、云业务和资本配置。",
            explicit_user_confirmation=False,
        )

    result = service.save_discussion_summary(
        "BABA",
        "Alibaba Group",
        "阿里巴巴长期竞争力讨论",
        "讨论了电商份额、云业务、资本配置以及估值修复的条件。",
        explicit_user_confirmation=True,
        key_points=["国内电商份额仍需持续跟踪", "云业务是潜在第二增长曲线"],
        changed_views=["低估值本身不足以构成买入理由"],
        conclusions=["保持观察，等待经营改善证据"],
        unresolved_questions=["AI 云收入能否转化为持续利润"],
        follow_up_items=["下季度复核云业务增速与利润率"],
    )
    assert result["saved"] is True
    assert result["discussion_summary"]["explicit_user_confirmation"] is True
    assert result["discussion_summary"]["recorded_via"] == "investment_research_os_mcp"

    history = service.get_discussion_history("BABA")
    assert history["count"] == 1
    assert history["discussion_summaries"][0]["title"] == "阿里巴巴长期竞争力讨论"
    assert history["discussion_summaries"][0]["changed_views"] == ["低估值本身不足以构成买入理由"]


def test_chatgpt_report_is_saved_in_versioned_sections(repository):
    service = KnowledgeService(repository)
    with pytest.raises(PermissionError, match="明确确认"):
        service.create_report_draft(
            "BABA", "Alibaba Group", "阿里巴巴长期投资研报", explicit_user_confirmation=False
        )

    draft = service.create_report_draft(
        "BABA", "Alibaba Group", "阿里巴巴长期投资研报", explicit_user_confirmation=True, summary="Bigfish 五年研究"
    )
    report_id = draft["report"]["id"]
    service.append_report_section(UUID(report_id), 1, "投资结论", "保持观察，等待经营改善证据。")
    service.append_report_section(UUID(report_id), 2, "主要风险", "国内电商份额及云业务资本回报仍需验证。")
    service.append_report_section(UUID(report_id), 2, "主要风险", "电商竞争、云业务回报和资本配置需要持续复核。")
    finalized = service.finalize_report(
        UUID(report_id), explicit_user_confirmation=True, change_summary=["首次正式保存"]
    )
    assert finalized["report"]["status"] == "finalized"

    saved = service.get_saved_report(UUID(report_id))
    assert saved["found"] is True
    assert saved["markdown"].count("## 主要风险") == 1
    assert "资本配置" in saved["markdown"]

    second = service.create_report_draft(
        "BABA", "Alibaba Group", "阿里巴巴长期投资研报更新", explicit_user_confirmation=True
    )
    assert second["report"]["version"] == 2
    assert second["report"]["previous_report_id"] == report_id
    assert service.get_saved_report_history("BABA")["count"] == 2


def test_memory_writes_and_company_snapshot(repository):
    company = repository.get_or_create_company("AMZN", "Amazon")
    repository.append_thesis(company.id, "AWS 与零售效率共同驱动长期利润")
    repository.save_assumption(company.id, "AWS 长期保持两位数增长", "高", confidence=Decimal("0.60"))
    repository.save_prediction(company.id, "未来两年 AWS 经营利润继续增长")
    repository.save_critical_unknown(company.id, "AI 资本开支回报能否覆盖折旧增长", "极高")
    first = repository.save_watch_variable(company.id, "AWS经营利润率", "衡量云业务单位经济性")
    second = repository.save_watch_variable(
        company.id,
        "AWS经营利润率",
        "衡量云业务单位经济性",
        current_assessment="保持强劲",
    )

    snapshot = repository.get_company_memory("amzn")
    assert snapshot is not None
    assert snapshot["company"].ticker == "AMZN"
    assert len(snapshot["theses"]) == 1
    assert len(snapshot["assumptions"]) == 1
    assert len(snapshot["predictions"]) == 1
    assert len(snapshot["critical_unknowns"]) == 1
    assert len(snapshot["watch_variables"]) == 1
    assert first.id == second.id
    assert snapshot["watch_variables"][0].current_assessment == "保持强劲"


def test_search_memory_and_json_service(repository):
    nvda = repository.get_or_create_company("NVDA", "NVIDIA")
    meta = repository.get_or_create_company("META", "Meta Platforms")
    repository.append_thesis(nvda.id, "CUDA 生态仍是主要护城河")
    repository.save_critical_unknown(nvda.id, "CUDA 抽象层是否降低迁移成本", "高")
    repository.append_thesis(meta.id, "广告推荐算法驱动变现")

    matches = repository.search_memory("CUDA")
    assert {match["type"] for match in matches} == {"thesis", "critical_unknown"}
    assert {match["ticker"] for match in matches} == {"NVDA"}

    service = KnowledgeService(repository)
    result = service.get_company_memory("NVDA")
    assert result["found"] is True
    assert result["company"]["ticker"] == "NVDA"
    assert isinstance(result["company"]["id"], str)
    assert service.get_company_memory("MISSING") == {"found": False, "ticker": "MISSING"}


def test_memory_input_validation(repository):
    company = repository.get_or_create_company("TSM", "Taiwan Semiconductor")
    with pytest.raises(ValueError, match="0 到 1"):
        repository.save_assumption(company.id, "先进制程份额稳定", "高", confidence=Decimal("1.2"))
    with pytest.raises(ValueError, match="关键词"):
        repository.search_memory(" ")


def test_valuation_history_preserves_snapshots(repository):
    company = repository.get_or_create_company("NVDA", "NVIDIA")
    repository.save_valuation(
        company.id,
        reference_price=Decimal("200"),
        target_return=Decimal("0.13"),
        base_expected_return=Decimal("0.15"),
        assumptions={"profit_growth_pct": 20, "terminal_pe": 25},
    )
    repository.save_valuation(
        company.id,
        reference_price=Decimal("220"),
        target_return=Decimal("0.13"),
        base_expected_return=Decimal("0.12"),
        assumptions={"profit_growth_pct": 18, "terminal_pe": 23},
    )

    history = repository.list_valuation_history(company.id)
    assert len(history) == 2
    assert history[0].reference_price == Decimal("220")
    assert history[1].reference_price == Decimal("200")
    assert history[0].assumptions["terminal_pe"] == 23


def test_valuation_service_reports_latest_change(repository):
    service = KnowledgeService(repository)
    service.save_valuation(
        "META",
        "Meta Platforms",
        reference_price=Decimal("500"),
        target_return_pct=Decimal("13"),
        base_expected_return_pct=Decimal("16"),
    )
    service.save_valuation(
        "META",
        "Meta Platforms",
        reference_price=Decimal("550"),
        target_return_pct=Decimal("13"),
        base_expected_return_pct=Decimal("14"),
    )

    result = service.get_valuation_history("META")
    assert result["count"] == 2
    assert result["valuations"][0]["target_return"] == "0.1300"
    assert result["latest_change"]["reference_price_change"] == "50.000000"
    assert result["latest_change"]["base_expected_return_change"] == "-0.0200"
    assert result["valuations"][0]["assumptions"]["recorded_via"] == "investment_research_os_mcp"
