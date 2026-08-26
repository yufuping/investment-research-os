from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    alpha_vantage_api_key: str | None = None
    fmp_api_key: str | None = None
    sec_user_agent: str = "InvestmentResearchOS contact@example.com"
    database_path: Path = Path("database/investment.db")
    bigfish_database_url: str | None = None
    bigfish_database_path: Path = Path("database/bigfish.db")
    bigfish_environment: str = "development"
    reports_path: Path = Path("reports/generated")
    portfolio_single_position_alert_pct: float = 20.0
    portfolio_top_two_alert_pct: float = 45.0
    portfolio_top_three_alert_pct: float = 60.0
    portfolio_risk_theme_alert_pct: float = 50.0

    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env.local", PROJECT_ROOT.parent / ".env.local", PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def absolute_path(self, value: Path) -> Path:
        return value if value.is_absolute() else PROJECT_ROOT / value


@lru_cache
def get_settings() -> Settings:
    return Settings()
