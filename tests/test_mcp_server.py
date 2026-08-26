import json
from pathlib import Path
import subprocess
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from investment_os.app import mcp_server


def test_search_and_fetch_use_standard_report_shape(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    generated = reports / "generated"
    generated.mkdir(parents=True)
    report = generated / "NVDA-最新.md"
    report.write_text("# NVDA 长期投资研究报告\n\nCUDA 护城河", encoding="utf-8")
    monkeypatch.setattr(mcp_server, "REPORTS_ROOT", reports.resolve())

    found = json.loads(mcp_server.search("NVDA"))
    assert found["results"][0]["id"] == "generated/NVDA-最新.md"
    assert set(found["results"][0]) == {"id", "title", "url"}

    fetched = json.loads(mcp_server.fetch("generated/NVDA-最新.md"))
    assert fetched["id"] == "generated/NVDA-最新.md"
    assert "CUDA 护城河" in fetched["text"]
    assert {"id", "title", "text", "url"}.issubset(fetched)
    assert fetched["has_more"] is False


def test_fetch_supports_bounded_chunks(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    generated = reports / "generated"
    generated.mkdir(parents=True)
    report = generated / "CRCL.md"
    report.write_text("A" * 18000, encoding="utf-8")
    monkeypatch.setattr(mcp_server, "REPORTS_ROOT", reports.resolve())

    first = json.loads(mcp_server.fetch("generated/CRCL.md", max_chars=12000))
    second = json.loads(mcp_server.fetch("generated/CRCL.md", offset=first["next_offset"], max_chars=12000))

    assert len(first["text"]) == 12000
    assert first["has_more"] is True
    assert second["has_more"] is False
    assert first["text"] + second["text"] == "A" * 18000


def test_fetch_rejects_paths_outside_reports(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    reports.mkdir()
    monkeypatch.setattr(mcp_server, "REPORTS_ROOT", reports.resolve())
    with pytest.raises(LookupError):
        mcp_server.fetch("../secret.md")


def test_start_research_async_requires_explicit_cost_confirmation(monkeypatch):
    with pytest.raises(ValueError, match="API 费用"):
        mcp_server.start_research_async("NVDA", confirm_api_cost=False)

    class FakeManager:
        def start_research(self, ticker, question):
            return mcp_server.TaskState("task-1", "research", "queued", "已排队", ticker=ticker)

    monkeypatch.setattr(mcp_server, "task_manager", FakeManager())
    result = mcp_server.start_research_async("nvda", "ASIC", confirm_api_cost=True)
    assert result["task_id"] == "task-1"
    assert result["ticker"] == "NVDA"


def test_task_manager_can_start_without_deadlocking(tmp_path, monkeypatch):
    manager = mcp_server.PluginTaskManager(tmp_path)
    monkeypatch.setattr(manager.executor, "submit", lambda *args, **kwargs: None)

    task = manager.start_research("META", "")

    assert task.status == "queued"
    assert manager.list()[0].task_id == task.task_id


def test_failed_worker_releases_active_task(tmp_path, monkeypatch):
    manager = mcp_server.PluginTaskManager(tmp_path)
    monkeypatch.setattr(
        manager,
        "_run_command",
        lambda *args, **kwargs: subprocess.CompletedProcess([], 1, "", "模拟失败"),
    )

    first = manager.start_research("META", "")
    manager.executor.shutdown(wait=True)

    assert manager.get(first.task_id).status == "failed"
    replacement_manager = mcp_server.PluginTaskManager(tmp_path)
    replacement_manager.tasks = manager.tasks
    monkeypatch.setattr(replacement_manager.executor, "submit", lambda *args, **kwargs: None)
    assert replacement_manager.start_research("NVDA", "").status == "queued"


def test_cancel_task_releases_queue(tmp_path, monkeypatch):
    manager = mcp_server.PluginTaskManager(tmp_path)
    monkeypatch.setattr(manager.executor, "submit", lambda *args, **kwargs: None)
    task = manager.start_research("META", "")

    cancelled = manager.cancel(task.task_id)

    assert cancelled.status == "cancelled"
    assert manager.start_daily_update().status == "queued"


def test_generate_research_report_waits_and_fetches_full_report(monkeypatch):
    class FakeManager:
        def start_research(self, ticker, question):
            return mcp_server.TaskState("task-meta", "research", "running", "运行中", ticker=ticker)

        def wait(self, task_id, timeout):
            return mcp_server.TaskState(
                task_id,
                "research",
                "completed",
                "完成",
                ticker="META",
                report_id="generated/META-最新.md",
            )

    monkeypatch.setattr(mcp_server, "task_manager", FakeManager())
    monkeypatch.setattr(
        mcp_server,
        "fetch",
        lambda report_id: json.dumps({"id": report_id, "title": "META完整研报", "text": "# META\n\n## 财务质量\n\nRevenue与FCF"}, ensure_ascii=False),
    )

    result = mcp_server.generate_research_report("meta", confirm_api_cost=True, max_wait_seconds=30)

    assert result["status"] == "completed"
    assert "财务质量" in result["report"]["text"]
    assert result["report_id"] == "generated/META-最新.md"


def test_generate_research_report_returns_failure_without_waiting_forever(monkeypatch):
    class FakeManager:
        def start_research(self, ticker, question):
            return mcp_server.TaskState("task-meta", "research", "running", "运行中", ticker=ticker)

        def wait(self, task_id, timeout):
            return mcp_server.TaskState(task_id, "research", "failed", "研究失败", ticker="META", error="模型调用失败")

    monkeypatch.setattr(mcp_server, "task_manager", FakeManager())
    with pytest.raises(RuntimeError, match="模型调用失败"):
        mcp_server.generate_research_report("META", confirm_api_cost=True, max_wait_seconds=30)


def test_stale_running_task_is_recovered_and_allows_retry(tmp_path, monkeypatch):
    manager = mcp_server.PluginTaskManager(tmp_path)
    stale = mcp_server.TaskState(
        "stale-meta",
        "research",
        "running",
        "运行中",
        ticker="META",
        created_at=(datetime.now(UTC) - timedelta(minutes=10)).isoformat(),
        heartbeat_at=(datetime.now(UTC) - timedelta(minutes=10)).isoformat(),
    )
    manager.tasks[stale.task_id] = stale
    monkeypatch.setattr(manager.executor, "submit", lambda *args, **kwargs: None)

    replacement = manager.start_research("META", "")

    assert manager.get(stale.task_id).status == "failed"
    assert replacement.task_id != stale.task_id


def test_duplicate_same_ticker_request_reuses_active_task(tmp_path, monkeypatch):
    manager = mcp_server.PluginTaskManager(tmp_path)
    monkeypatch.setattr(manager.executor, "submit", lambda *args, **kwargs: None)

    first = manager.start_research("META", "AI资本开支")
    second = manager.start_research("META", "AI资本开支")

    assert second.task_id == first.task_id
    assert second.reused is True


def test_different_tickers_do_not_block_each_other(tmp_path, monkeypatch):
    manager = mcp_server.PluginTaskManager(tmp_path)
    monkeypatch.setattr(manager.executor, "submit", lambda *args, **kwargs: None)

    meta = manager.start_research("META", "")
    nvda = manager.start_research("NVDA", "")

    assert meta.task_id != nvda.task_id
    assert {task.ticker for task in manager.list() if task.status == "queued"} == {"META", "NVDA"}


def test_latest_report_falls_back_to_timestamped_markdown(tmp_path, monkeypatch):
    generated = tmp_path / "generated"
    generated.mkdir()
    report = generated / "META-20260824T061111Z.md"
    report.write_text("# META完整研报", encoding="utf-8")
    monkeypatch.setattr(mcp_server, "REPORTS_ROOT", tmp_path.resolve())

    assert mcp_server.latest_report_id("META") == "generated/META-20260824T061111Z.md"


def test_cached_start_research_name_uses_waiting_tool(monkeypatch):
    monkeypatch.setattr(
        mcp_server,
        "generate_research_report",
        lambda ticker, question, confirm, wait: {"status": "completed", "ticker": ticker, "report": {"text": "完整正文"}},
    )

    result = mcp_server.start_research("META", "", True)

    assert result["status"] == "completed"
    assert result["report"]["text"] == "完整正文"
def test_company_memory_tools_use_json_service(monkeypatch):
    class FakeKnowledgeService:
        def get_company_memory(self, ticker):
            return {"found": True, "company": {"ticker": ticker}}

        def search_memory(self, query, *, ticker=None, limit=20):
            return {"query": query, "ticker": ticker, "count": 1, "limit": limit}

    monkeypatch.setattr(mcp_server, "_knowledge_service", FakeKnowledgeService())

    assert mcp_server.get_company_memory("nvda")["company"]["ticker"] == "NVDA"
    result = mcp_server.search_memory("CUDA", ticker="nvda", limit=5)
    assert result == {"query": "CUDA", "ticker": "NVDA", "count": 1, "limit": 5}


def test_memory_write_tools_normalize_inputs(monkeypatch):
    calls = []

    class FakeKnowledgeService:
        def save_thesis(self, ticker, company_name, thesis, **kwargs):
            calls.append((ticker, company_name, thesis, kwargs))
            return {"saved": True}

        def save_watch_variable(self, ticker, company_name, name, rationale, **kwargs):
            calls.append((ticker, company_name, name, rationale, kwargs))
            return {"saved": True}

    monkeypatch.setattr(mcp_server, "_knowledge_service", FakeKnowledgeService())

    assert mcp_server.save_thesis("nvda", " NVIDIA ", "CUDA 护城河", confidence=0.7)["saved"]
    assert calls[0][0:3] == ("NVDA", "NVIDIA", "CUDA 护城河")
    assert calls[0][3]["confidence"] == Decimal("0.7")

    assert mcp_server.save_watch_variable("nvda", "NVIDIA", "毛利率", "验证定价权", "高位")["saved"]
    assert calls[1][-1]["current_assessment"] == "高位"


def test_save_valuation_requires_explicit_confirmation(monkeypatch):
    class FakeKnowledgeService:
        def save_valuation(self, *args, **kwargs):
            return {"saved": True}

    monkeypatch.setattr(mcp_server, "_knowledge_service", FakeKnowledgeService())

    with pytest.raises(ValueError, match="明确要求保存"):
        mcp_server.save_valuation("NVDA", "NVIDIA", 200, confirm_save=False)
    assert mcp_server.save_valuation("NVDA", "NVIDIA", 200, confirm_save=True)["saved"] is True


def test_save_confirmed_decision_requires_confirmation_and_real_size(monkeypatch):
    calls = []

    class FakeKnowledgeService:
        def save_confirmed_decision(self, *args, **kwargs):
            calls.append((args, kwargs))
            return {"saved": True}

        def get_decision_history(self, ticker, limit=20):
            return {"found": True, "ticker": ticker, "count": 0, "decisions": []}

    monkeypatch.setattr(mcp_server, "_knowledge_service", FakeKnowledgeService())

    with pytest.raises(ValueError, match="明确确认"):
        mcp_server.save_confirmed_decision("CRCL", "Circle", "卖出", "风险补偿不足", quantity=3)
    with pytest.raises(ValueError, match="至少提供"):
        mcp_server.save_confirmed_decision("CRCL", "Circle", "卖出", "风险补偿不足", confirm_transaction=True)

    result = mcp_server.save_confirmed_decision(
        "crcl",
        "Circle Internet Group",
        "卖出",
        "风险补偿不足",
        confirm_transaction=True,
        quantity=3,
        quantity_unit="股",
    )
    assert result["saved"] is True
    assert calls[0][0][0] == "CRCL"
    assert calls[0][1]["explicit_user_confirmation"] is True
    assert calls[0][1]["quantity"] == Decimal("3")
    assert mcp_server.get_decision_history("crcl")["ticker"] == "CRCL"


def test_save_discussion_summary_requires_preview_confirmation(monkeypatch):
    calls = []

    class FakeKnowledgeService:
        def save_discussion_summary(self, *args, **kwargs):
            calls.append((args, kwargs))
            return {"saved": True}

        def get_discussion_history(self, ticker, limit=20):
            return {"found": True, "ticker": ticker, "count": 0, "discussion_summaries": []}

    monkeypatch.setattr(mcp_server, "_knowledge_service", FakeKnowledgeService())

    with pytest.raises(ValueError, match="展示完整讨论纪要"):
        mcp_server.save_discussion_summary(
            "BABA", "Alibaba Group", "阿里巴巴讨论", "关于电商和云业务的讨论。"
        )

    result = mcp_server.save_discussion_summary(
        "baba",
        "Alibaba Group",
        "阿里巴巴讨论",
        "关于电商和云业务的讨论。",
        confirm_save=True,
        changed_views=["低估值不是充分条件"],
    )
    assert result["saved"] is True
    assert calls[0][0][0] == "BABA"
    assert calls[0][1]["explicit_user_confirmation"] is True
    assert mcp_server.get_discussion_history("baba")["ticker"] == "BABA"


def test_saved_report_workflow_requires_confirmation_and_chunks_reads(monkeypatch):
    calls = []

    class FakeKnowledgeService:
        def create_report_draft(self, *args, **kwargs):
            calls.append(("create", args, kwargs))
            return {"saved": True, "report": {"id": "00000000-0000-0000-0000-000000000001"}}

        def append_report_section(self, *args, **kwargs):
            calls.append(("append", args, kwargs))
            return {"saved": True}

        def finalize_report(self, *args, **kwargs):
            calls.append(("finalize", args, kwargs))
            return {"saved": True}

        def get_saved_report(self, report_id):
            return {"found": True, "report": {"id": str(report_id)}, "sections": [], "markdown": "A" * 2500}

        def get_saved_report_history(self, ticker, limit=20):
            return {"found": True, "ticker": ticker, "count": 0, "reports": []}

    monkeypatch.setattr(mcp_server, "_knowledge_service", FakeKnowledgeService())
    with pytest.raises(ValueError, match="展示完整研报"):
        mcp_server.create_report_draft("BABA", "Alibaba", "研报")

    draft = mcp_server.create_report_draft("baba", "Alibaba", "研报", confirm_save=True)
    report_id = draft["report"]["id"]
    assert mcp_server.append_report_section(report_id, 1, "结论", "正文")["saved"] is True
    with pytest.raises(ValueError, match="明确确认"):
        mcp_server.finalize_research_report(report_id)
    assert mcp_server.finalize_research_report(report_id, confirm_finalize=True)["saved"] is True
    first = mcp_server.get_saved_research_report(report_id, max_chars=1000)
    assert first["has_more"] is True
    assert first["next_offset"] == 1000
    assert mcp_server.get_saved_report_history("baba")["ticker"] == "BABA"
