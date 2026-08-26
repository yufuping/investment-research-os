from datetime import UTC, datetime
import json
from pathlib import Path

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session

from investment_os.database.models import Base, InvestmentDecision, MarketDataCache, PortfolioPosition, PortfolioReferencePrice, PortfolioSnapshot, PortfolioTransaction, PositionRiskTag, ResearchRun, ValuationWatch


class ResearchRepository:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{path}")
        Base.metadata.create_all(self.engine)
        columns = {column["name"] for column in inspect(self.engine).get_columns("portfolio_reference_prices")}
        if "observed_date" not in columns:
            with self.engine.begin() as connection:
                connection.execute(text("ALTER TABLE portfolio_reference_prices ADD COLUMN observed_date VARCHAR(10)"))

    def start_run(self, ticker: str, question: str) -> int:
        with Session(self.engine) as session:
            run = ResearchRun(ticker=ticker, question=question)
            session.add(run)
            session.commit()
            session.refresh(run)
            return run.id

    def get_market_cache(self, ticker: str) -> MarketDataCache | None:
        with Session(self.engine) as session:
            cached = session.get(MarketDataCache, ticker.upper())
            if cached is None:
                return None
            session.expunge(cached)
            return cached

    def save_market_cache(
        self,
        ticker: str,
        payload: str,
        source: str,
        retrieved_at: datetime,
    ) -> None:
        with Session(self.engine) as session:
            cached = session.get(MarketDataCache, ticker.upper())
            if cached is None:
                cached = MarketDataCache(
                    ticker=ticker.upper(),
                    payload=payload,
                    source=source,
                    retrieved_at=retrieved_at,
                )
                session.add(cached)
            else:
                cached.payload = payload
                cached.source = source
                cached.retrieved_at = retrieved_at
            session.commit()

    def complete_run(self, run_id: int, report: str, report_path: str) -> None:
        with Session(self.engine) as session:
            run = session.get(ResearchRun, run_id)
            if run is None:
                raise LookupError(f"找不到研究任务 {run_id}")
            run.status = "completed"
            run.report = report
            run.report_path = report_path
            run.completed_at = datetime.now(UTC)
            session.commit()

    def get_completed_runs(self, ticker: str, limit: int = 2) -> list[ResearchRun]:
        """按完成时间倒序读取指定公司的历史研究。"""
        with Session(self.engine) as session:
            runs = list(session.scalars(
                select(ResearchRun)
                .where(ResearchRun.ticker == ticker.upper(), ResearchRun.status == "completed")
                .order_by(ResearchRun.completed_at.desc(), ResearchRun.id.desc())
                .limit(limit)
            ))
            for run in runs:
                session.expunge(run)
            return runs

    def save_valuation_watch(
        self,
        ticker: str,
        required_return: float,
        scenarios_json: str,
        acceptable_prices_json: str,
        reference_price: float | None,
        reference_eps: float | None,
    ) -> None:
        with Session(self.engine) as session:
            watch = session.get(ValuationWatch, ticker.upper())
            if watch is None:
                watch = ValuationWatch(ticker=ticker.upper())
                session.add(watch)
            watch.required_return = required_return
            watch.scenarios_json = scenarios_json
            watch.acceptable_prices_json = acceptable_prices_json
            watch.reference_price = reference_price
            watch.reference_eps = reference_eps
            watch.updated_at = datetime.now(UTC)
            session.commit()

    def get_valuation_watch(self, ticker: str) -> ValuationWatch | None:
        with Session(self.engine) as session:
            watch = session.get(ValuationWatch, ticker.upper())
            if watch is not None:
                session.expunge(watch)
            return watch

    def list_valuation_watches(self) -> list[ValuationWatch]:
        with Session(self.engine) as session:
            watches = list(session.scalars(select(ValuationWatch).order_by(ValuationWatch.ticker)))
            for watch in watches:
                session.expunge(watch)
            return watches

    def save_position(self, ticker: str, shares: float, cost_per_share: float) -> None:
        with Session(self.engine) as session:
            position = session.get(PortfolioPosition, ticker.upper())
            if position is None:
                position = PortfolioPosition(ticker=ticker.upper())
                session.add(position)
            position.shares = shares
            position.cost_per_share = cost_per_share
            position.updated_at = datetime.now(UTC)
            session.commit()

    def list_positions(self) -> list[PortfolioPosition]:
        with Session(self.engine) as session:
            positions = list(session.scalars(select(PortfolioPosition).order_by(PortfolioPosition.ticker)))
            for position in positions:
                session.expunge(position)
            return positions

    def delete_position(self, ticker: str) -> bool:
        with Session(self.engine) as session:
            position = session.get(PortfolioPosition, ticker.upper())
            if position is None:
                return False
            session.delete(position)
            session.commit()
            return True

    def save_reference_price(self, ticker: str, price: float, source: str = "人工录入", observed_date: str | None = None) -> None:
        with Session(self.engine) as session:
            reference = session.get(PortfolioReferencePrice, ticker.upper())
            if reference is None:
                reference = PortfolioReferencePrice(ticker=ticker.upper())
                session.add(reference)
            reference.price = price
            reference.source = source
            reference.observed_date = observed_date or datetime.now(UTC).date().isoformat()
            reference.updated_at = datetime.now(UTC)
            session.commit()

    def get_reference_price(self, ticker: str) -> PortfolioReferencePrice | None:
        with Session(self.engine) as session:
            reference = session.get(PortfolioReferencePrice, ticker.upper())
            if reference is not None:
                session.expunge(reference)
            return reference

    def replace_position_tags(self, ticker: str, tags: list[str]) -> None:
        normalized = sorted({tag.strip() for tag in tags if tag.strip()})
        with Session(self.engine) as session:
            existing = list(session.scalars(select(PositionRiskTag).where(PositionRiskTag.ticker == ticker.upper())))
            for item in existing:
                session.delete(item)
            for tag in normalized:
                session.add(PositionRiskTag(ticker=ticker.upper(), tag=tag))
            session.commit()

    def get_position_tags(self, ticker: str) -> list[str]:
        with Session(self.engine) as session:
            return list(session.scalars(
                select(PositionRiskTag.tag)
                .where(PositionRiskTag.ticker == ticker.upper())
                .order_by(PositionRiskTag.tag)
            ))

    def save_portfolio_snapshot(
        self,
        total_cost: float,
        total_value: float,
        top_two_weight: float,
        positions_json: str,
    ) -> int:
        with Session(self.engine) as session:
            snapshot = PortfolioSnapshot(
                total_cost=total_cost,
                total_value=total_value,
                top_two_weight=top_two_weight,
                positions_json=positions_json,
            )
            session.add(snapshot)
            session.commit()
            session.refresh(snapshot)
            return snapshot.id

    def save_portfolio_snapshot_if_changed(
        self,
        total_cost: float,
        total_value: float,
        top_two_weight: float,
        positions_json: str,
    ) -> int | None:
        """仅在组合数据发生可显示变化时保存，避免刷新操作制造重复历史。"""
        with Session(self.engine) as session:
            latest = session.scalar(
                select(PortfolioSnapshot)
                .order_by(PortfolioSnapshot.created_at.desc(), PortfolioSnapshot.id.desc())
                .limit(1)
            )
            if latest is not None:
                old_positions = json.loads(latest.positions_json)
                new_positions = json.loads(positions_json)
                same_positions = set(old_positions) == set(new_positions)
                if same_positions:
                    for ticker in old_positions:
                        old = old_positions[ticker]
                        new = new_positions[ticker]
                        if abs(old.get("shares", 0.0) - new.get("shares", 0.0)) > 1e-9 or abs(old.get("price", 0.0) - new.get("price", 0.0)) > 0.005:
                            same_positions = False
                            break
                if same_positions and abs(latest.total_cost - total_cost) < 0.01 and abs(latest.total_value - total_value) < 0.01:
                    return None
            snapshot = PortfolioSnapshot(
                total_cost=total_cost,
                total_value=total_value,
                top_two_weight=top_two_weight,
                positions_json=positions_json,
            )
            session.add(snapshot)
            session.commit()
            session.refresh(snapshot)
            return snapshot.id

    def list_portfolio_snapshots(self, limit: int = 12) -> list[PortfolioSnapshot]:
        with Session(self.engine) as session:
            snapshots = list(session.scalars(
                select(PortfolioSnapshot)
                .order_by(PortfolioSnapshot.created_at.desc(), PortfolioSnapshot.id.desc())
                .limit(limit)
            ))
            for snapshot in snapshots:
                session.expunge(snapshot)
            return snapshots

    def record_trade(
        self,
        ticker: str,
        transaction_type: str,
        shares: float,
        price: float,
        fee: float = 0.0,
        note: str = "",
    ) -> int:
        ticker = ticker.upper()
        if transaction_type not in {"buy", "sell"}:
            raise ValueError("交易类型必须是 buy 或 sell")
        if shares <= 0 or price <= 0 or fee < 0:
            raise ValueError("股数和价格必须大于0，手续费不能为负数")
        with Session(self.engine) as session:
            position = session.get(PortfolioPosition, ticker)
            realized_pnl = None
            if transaction_type == "buy":
                old_shares = position.shares if position else 0.0
                old_cost = position.cost_per_share if position else 0.0
                new_shares = old_shares + shares
                new_cost = (old_shares * old_cost + shares * price + fee) / new_shares
                if position is None:
                    position = PortfolioPosition(ticker=ticker)
                    session.add(position)
                position.shares = new_shares
                position.cost_per_share = new_cost
                position.updated_at = datetime.now(UTC)
            else:
                if position is None or shares > position.shares + 1e-9:
                    raise ValueError(f"{ticker} 可卖股数不足")
                realized_pnl = (price - position.cost_per_share) * shares - fee
                position.shares -= shares
                position.updated_at = datetime.now(UTC)
                if position.shares <= 1e-9:
                    session.delete(position)
            transaction = PortfolioTransaction(
                ticker=ticker,
                transaction_type=transaction_type,
                shares=shares,
                price=price,
                fee=fee,
                realized_pnl=realized_pnl,
                note=note,
            )
            session.add(transaction)
            session.commit()
            session.refresh(transaction)
            return transaction.id

    def list_transactions(self, limit: int = 100) -> list[PortfolioTransaction]:
        with Session(self.engine) as session:
            transactions = list(session.scalars(
                select(PortfolioTransaction)
                .order_by(PortfolioTransaction.created_at.desc(), PortfolioTransaction.id.desc())
                .limit(limit)
            ))
            for transaction in transactions:
                session.expunge(transaction)
            return transactions

    def save_decision(
        self,
        ticker: str,
        action: str,
        thesis: str,
        reference_price: float | None = None,
        valuation_basis: str = "",
        invalidation_condition: str = "",
        next_check: str = "",
    ) -> int:
        allowed = {"观察", "买入", "持有", "减仓", "退出", "重新评估"}
        if action not in allowed:
            raise ValueError("不支持的决策类型")
        if not thesis.strip():
            raise ValueError("核心理由不能为空")
        with Session(self.engine) as session:
            decision = InvestmentDecision(
                ticker=ticker.upper(),
                action=action,
                reference_price=reference_price,
                thesis=thesis.strip(),
                valuation_basis=valuation_basis.strip(),
                invalidation_condition=invalidation_condition.strip(),
                next_check=next_check.strip(),
            )
            session.add(decision)
            session.commit()
            session.refresh(decision)
            return decision.id

    def list_decisions(self, ticker: str | None = None, limit: int = 100) -> list[InvestmentDecision]:
        with Session(self.engine) as session:
            statement = select(InvestmentDecision)
            if ticker:
                statement = statement.where(InvestmentDecision.ticker == ticker.upper())
            decisions = list(session.scalars(
                statement.order_by(InvestmentDecision.created_at.desc(), InvestmentDecision.id.desc()).limit(limit)
            ))
            for decision in decisions:
                session.expunge(decision)
            return decisions

    def fail_run(self, run_id: int, error: str) -> None:
        with Session(self.engine) as session:
            run = session.get(ResearchRun, run_id)
            if run is None:
                raise LookupError(f"找不到研究任务 {run_id}")
            run.status = "failed"
            run.error = error
            run.completed_at = datetime.now(UTC)
            session.commit()
