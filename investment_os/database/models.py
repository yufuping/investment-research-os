from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ResearchRun(Base):
    __tablename__ = "research_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(20), index=True)
    question: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="running")
    report: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MarketDataCache(Base):
    """保存一次完整市场数据快照，供所有分析 Agent 共用。"""

    __tablename__ = "market_data_cache"

    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    payload: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(100))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ValuationWatch(Base):
    """保存完整研究采用的五年估值假设和观察价格。"""

    __tablename__ = "valuation_watch"

    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    required_return: Mapped[float] = mapped_column(Float)
    scenarios_json: Mapped[str] = mapped_column(Text)
    acceptable_prices_json: Mapped[str] = mapped_column(Text)
    reference_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    reference_eps: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class PortfolioPosition(Base):
    """个人组合持仓；成本按每股成本记录。"""

    __tablename__ = "portfolio_positions"

    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    shares: Mapped[float] = mapped_column(Float)
    cost_per_share: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class PortfolioReferencePrice(Base):
    """市场接口不可用时使用的人工参考价格。"""

    __tablename__ = "portfolio_reference_prices"

    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    price: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(100), default="人工录入")
    observed_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class PositionRiskTag(Base):
    """用户可编辑的持仓风险主题；同一持仓可有多个标签。"""

    __tablename__ = "position_risk_tags"

    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    tag: Mapped[str] = mapped_column(String(100), primary_key=True)


class PortfolioSnapshot(Base):
    """保存每次组合复核的汇总和持仓明细。"""

    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    total_cost: Mapped[float] = mapped_column(Float)
    total_value: Mapped[float] = mapped_column(Float)
    top_two_weight: Mapped[float] = mapped_column(Float)
    positions_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)


class PortfolioTransaction(Base):
    """本地交易流水，不连接券商。"""

    __tablename__ = "portfolio_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(20), index=True)
    transaction_type: Mapped[str] = mapped_column(String(20))
    shares: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    fee: Mapped[float] = mapped_column(Float, default=0.0)
    realized_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)


class InvestmentDecision(Base):
    """保存当时的决策理由和未来验证条件。"""

    __tablename__ = "investment_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(20), index=True)
    action: Mapped[str] = mapped_column(String(20))
    reference_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    thesis: Mapped[str] = mapped_column(Text)
    valuation_basis: Mapped[str] = mapped_column(Text, default="")
    invalidation_condition: Mapped[str] = mapped_column(Text, default="")
    next_check: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)
