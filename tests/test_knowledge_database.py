from pathlib import Path

from investment_os.app.config import Settings
from investment_os.knowledge.database import create_knowledge_repository


def test_local_knowledge_database_persists_between_repositories(tmp_path: Path):
    settings = Settings(
        openai_api_key="test",
        bigfish_database_path=tmp_path / "bigfish.db",
    )
    first = create_knowledge_repository(settings)
    company = first.get_or_create_company("NVDA", "NVIDIA")
    first.append_thesis(company.id, "CUDA 与全栈平台构成主要护城河")

    second = create_knowledge_repository(settings)
    memory = second.get_company_memory("NVDA")

    assert (tmp_path / "bigfish.db").is_file()
    assert memory is not None
    assert memory["theses"][0].thesis == "CUDA 与全栈平台构成主要护城河"


def test_remote_database_does_not_auto_create_schema(monkeypatch, tmp_path: Path):
    remote_file = tmp_path / "remote-simulation.db"
    settings = Settings(
        openai_api_key="test",
        bigfish_database_url=f"sqlite+pysqlite:///{remote_file}",
    )
    repository = create_knowledge_repository(settings)

    assert repository.engine.url.database == str(remote_file)
    assert not remote_file.exists()
