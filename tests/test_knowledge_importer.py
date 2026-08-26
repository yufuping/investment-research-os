from sqlalchemy import create_engine

from investment_os.knowledge.importer import import_company_baseline
from investment_os.knowledge.repository import KnowledgeRepository


def test_baseline_import_is_idempotent():
    repository = KnowledgeRepository.from_engine(create_engine("sqlite+pysqlite:///:memory:"), create_schema=True)
    payload = {
        "ticker": "NVDA",
        "company_name": "NVIDIA",
        "thesis": {"text": "AI增长与利润份额共同决定价值", "confidence": 0.7},
        "assumptions": [{"description": "CUDA迁移成本仍高", "impact": "高", "confidence": 0.6}],
        "critical_unknowns": [{"description": "ASIC部署比例", "impact": "极高"}],
        "watch_variables": [{"name": "毛利率", "rationale": "验证定价权"}],
    }

    first = import_company_baseline(repository, payload)
    second = import_company_baseline(repository, payload)
    memory = repository.get_company_memory("NVDA")

    assert first == {"ticker": "NVDA", "theses": 1, "assumptions": 1, "critical_unknowns": 1, "watch_variables": 1}
    assert second == {"ticker": "NVDA", "theses": 0, "assumptions": 0, "critical_unknowns": 0, "watch_variables": 0}
    assert memory is not None
    assert len(memory["theses"]) == 1
    assert len(memory["assumptions"]) == 1
    assert len(memory["critical_unknowns"]) == 1
    assert len(memory["watch_variables"]) == 1
