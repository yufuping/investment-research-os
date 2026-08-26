from pathlib import Path

from sqlalchemy import inspect, text

from investment_os.app.config import PROJECT_ROOT, Settings, get_settings
from investment_os.knowledge.repository import KnowledgeRepository
from investment_os.knowledge.service import KnowledgeService


def create_knowledge_repository(settings: Settings | None = None) -> KnowledgeRepository:
    """本地默认持久化到独立 SQLite；配置 URL 后交由 Alembic 管理远端结构。"""
    config = settings or get_settings()
    if config.bigfish_database_url:
        return KnowledgeRepository(config.bigfish_database_url, create_schema=False)

    path = config.absolute_path(config.bigfish_database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    repository = KnowledgeRepository(f"sqlite+pysqlite:///{path}", create_schema=True)
    _upgrade_local_sqlite_schema(repository)
    return repository


def _upgrade_local_sqlite_schema(repository: KnowledgeRepository) -> None:
    """为本地开发库执行向后兼容的小型迁移，保留已有投资记忆。"""
    existing = {column["name"] for column in inspect(repository.engine).get_columns("decisions")}
    additions = {
        "currency": "VARCHAR(8)",
        "quantity": "NUMERIC(20, 6)",
        "quantity_unit": "VARCHAR(32)",
        "decision_type": "VARCHAR(64)",
        "notes": "TEXT",
        "recorded_via": "VARCHAR(64)",
    }
    with repository.engine.begin() as connection:
        for name, sql_type in additions.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE decisions ADD COLUMN {name} {sql_type}"))


def create_knowledge_service(settings: Settings | None = None) -> KnowledgeService:
    return KnowledgeService(create_knowledge_repository(settings))
