from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from investment_os.knowledge.repository import KnowledgeRepository
from investment_os.knowledge.service import KnowledgeService


@pytest.fixture
def service() -> KnowledgeService:
    from sqlalchemy import create_engine

    repository = KnowledgeRepository.from_engine(create_engine("sqlite+pysqlite:///:memory:"), create_schema=True)
    return KnowledgeService(repository)


def test_save_prediction_with_expected_verification_date(service):
    saved = service.save_prediction(
        "META",
        "Meta Platforms",
        "2027 CapEx 将超过 1500 亿美元",
        confidence=Decimal("0.70"),
        expected_verification_date=date(2027, 12, 31),
    )
    assert saved["prediction"]["expected_verification_date"] == "2027-12-31"
    assert saved["prediction"]["outcome"] == "pending"


def test_record_prediction_result_requires_confirmation(service):
    saved = service.save_prediction("META", "Meta Platforms", "广告收入保持两位数增长")
    prediction_id = UUID(saved["prediction"]["id"])

    with pytest.raises(PermissionError, match="明确确认"):
        service.repository.record_prediction_result(
            prediction_id,
            "2026 年广告收入同比增长 11%",
            "correct",
            explicit_user_confirmation=False,
        )


def test_record_prediction_result_updates_pending_prediction(service):
    saved = service.save_prediction(
        "META",
        "Meta Platforms",
        "2027 CapEx 将超过 1500 亿美元",
        expected_verification_date=date(2027, 12, 31),
    )
    prediction_id = UUID(saved["prediction"]["id"])

    reviewed = service.record_prediction_result(
        prediction_id,
        "2027 全年 CapEx 约 720 亿美元，未超过 1500 亿",
        "wrong",
        error_reason="模型错误：低估了管理层资本纪律与 ROI 约束",
        explicit_user_confirmation=True,
    )

    assert reviewed["reviewed"] is True
    assert reviewed["ticker"] == "META"
    assert reviewed["prediction"]["outcome"] == "wrong"
    assert reviewed["prediction"]["actual_result"].startswith("2027")
    assert reviewed["prediction"]["reviewed_at"] is not None

    history = service.get_prediction_history("META")
    assert history["count"] == 1
    assert history["pending_count"] == 0
    assert history["reviewed_count"] == 1


def test_record_prediction_result_rejects_duplicate_review(service):
    saved = service.save_prediction("NVDA", "NVIDIA", "数据中心收入继续加速")
    prediction_id = UUID(saved["prediction"]["id"])
    service.record_prediction_result(
        prediction_id,
        "增速放缓",
        "partially_correct",
        explicit_user_confirmation=True,
    )

    with pytest.raises(ValueError, match="已经复盘"):
        service.record_prediction_result(
            prediction_id,
            "再次修改",
            "wrong",
            explicit_user_confirmation=True,
        )


def test_get_prediction_history_filters_by_outcome(service):
    service.save_prediction("AMZN", "Amazon", "AWS 经营利润继续增长")
    reviewed = service.save_prediction("AMZN", "Amazon", "Prime 会员数突破 3 亿")
    service.record_prediction_result(
        UUID(reviewed["prediction"]["id"]),
        "Prime 会员约 2.2 亿",
        "wrong",
        explicit_user_confirmation=True,
    )

    pending = service.get_prediction_history("AMZN", outcome="pending")
    reviewed_only = service.get_prediction_history("AMZN", outcome="wrong")

    assert pending["count"] == 1
    assert pending["predictions"][0]["prediction"].startswith("AWS")
    assert reviewed_only["count"] == 1
    assert reviewed_only["predictions"][0]["outcome"] == "wrong"


def test_list_pending_predictions_and_due_filter(service):
    today = date.today()
    service.save_prediction("GOOGL", "Alphabet", "搜索广告份额稳定", expected_verification_date=today - timedelta(days=1))
    service.save_prediction("GOOGL", "Alphabet", "Gemini 货币化超预期", expected_verification_date=today + timedelta(days=30))
    service.save_prediction("META", "Meta Platforms", "Reels 变现继续提升")

    all_pending = service.list_pending_predictions()
    assert all_pending["count"] == 3

    due = service.list_pending_predictions(due_by=today)
    assert due["count"] == 1
    assert due["predictions"][0]["ticker"] == "GOOGL"
    assert due["predictions"][0]["prediction"].startswith("搜索广告")

    scoped = service.list_pending_predictions(ticker="META")
    assert scoped["count"] == 1
    assert scoped["predictions"][0]["company_name"] == "Meta Platforms"


def test_record_prediction_result_validates_outcome(service):
    saved = service.save_prediction("TSM", "Taiwan Semiconductor", "先进制程需求保持强劲")
    prediction_id = UUID(saved["prediction"]["id"])

    with pytest.raises(ValueError, match="correct"):
        service.record_prediction_result(
            prediction_id,
            "需求符合预期",
            "maybe",
            explicit_user_confirmation=True,
        )
