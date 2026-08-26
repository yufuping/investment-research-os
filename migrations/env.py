from logging.config import fileConfig
import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from investment_os.knowledge.models import KnowledgeBase


config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

database_url = os.getenv("BIGFISH_DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

target_metadata = KnowledgeBase.metadata


def require_database_url() -> None:
    if not config.get_main_option("sqlalchemy.url"):
        raise RuntimeError("请先设置 BIGFISH_DATABASE_URL；禁止默认连接生产数据库。")


def run_migrations_offline() -> None:
    require_database_url()
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    require_database_url()
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
