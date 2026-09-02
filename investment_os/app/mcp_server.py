from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from threading import RLock
import time
from urllib.parse import quote
from uuid import uuid4
from decimal import Decimal
from uuid import UUID

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from starlette.requests import Request
from starlette.responses import JSONResponse

from investment_os.app.config import PROJECT_ROOT
from investment_os.knowledge.database import create_knowledge_service
from investment_os.tools.valuation import (
    calculate_cagr as calculate_cagr_value,
    calculate_required_profit_growth as calculate_required_profit_growth_value,
    scenario_analysis as run_scenario_analysis,
)


REPORTS_ROOT = (PROJECT_ROOT / "reports").resolve()
REPORT_BASE_URL = os.getenv("MCP_REPORT_BASE_URL", "http://127.0.0.1:8080/reports").rstrip("/")
_knowledge_service = None


def knowledge_service():
    global _knowledge_service
    if _knowledge_service is None:
        _knowledge_service = create_knowledge_service()
    return _knowledge_service


@dataclass
class TaskState:
    task_id: str
    task_type: str
    status: str
    message: str
    ticker: str | None = None
    report_id: str | None = None
    created_at: str = ""
    started_at: str | None = None
    heartbeat_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    request_id: str | None = None
    question_digest: str = ""
    reused: bool = False


class PluginTaskManager:
    """管理不调用大模型的后台维护任务。"""

    def __init__(self, project_root: Path = PROJECT_ROOT, max_workers: int = 3, state_path: Path | None = None) -> None:
        self.project_root = project_root
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="mcp-investment")
        self.lock = RLock()
        self.tasks: dict[str, TaskState] = {}
        self.processes: dict[str, subprocess.Popen[str]] = {}
        self.state_path = state_path or project_root / "database" / "plugin_tasks.json"
        self._load_and_recover()

    @staticmethod
    def _digest(question: str) -> str:
        return hashlib.sha256(question.strip().encode("utf-8")).hexdigest()

    def _persist_locked(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps([asdict(task) for task in self.tasks.values()], ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.state_path)

    def _load_and_recover(self) -> None:
        if not self.state_path.is_file():
            return
        try:
            records = json.loads(self.state_path.read_text(encoding="utf-8"))
            for record in records:
                task = TaskState(**record)
                if task.status in {"queued", "running"}:
                    task.status = "failed"
                    task.error = "服务重启时发现未完成任务，已标记为失效，请重新发起。"
                    task.message = task.error
                    task.completed_at = datetime.now(UTC).isoformat()
                self.tasks[task.task_id] = task
            self._persist_locked()
        except (OSError, ValueError, TypeError):
            self.tasks = {}

    def _create(self, task_type: str, message: str, ticker: str | None = None, question: str = "", request_id: str | None = None) -> TaskState:
        task = TaskState(
            task_id=uuid4().hex,
            task_type=task_type,
            status="queued",
            message=message,
            ticker=ticker,
            created_at=datetime.now(UTC).isoformat(),
            heartbeat_at=datetime.now(UTC).isoformat(),
            request_id=request_id,
            question_digest=self._digest(question),
        )
        with self.lock:
            self.tasks[task.task_id] = task
            self._persist_locked()
        return TaskState(**asdict(task))

    def _recover_stale_locked(self, stale_after_seconds: int = 120) -> None:
        now = datetime.now(UTC)
        changed = False
        for task in self.tasks.values():
            if task.status != "running" or not task.heartbeat_at:
                continue
            heartbeat = datetime.fromisoformat(task.heartbeat_at)
            if (now - heartbeat).total_seconds() <= stale_after_seconds:
                continue
            process = self.processes.get(task.task_id)
            if process is not None and process.poll() is None:
                continue
            task.status = "failed"
            task.error = "任务心跳超时，worker可能已经退出。"
            task.message = task.error
            task.completed_at = now.isoformat()
            changed = True
        if changed:
            self._persist_locked()

    def list(self, limit: int = 20) -> list[TaskState]:
        with self.lock:
            self._recover_stale_locked()
            tasks = sorted(self.tasks.values(), key=lambda task: task.created_at, reverse=True)
            return [TaskState(**asdict(task)) for task in tasks[:limit]]

    def cancel(self, task_id: str) -> TaskState:
        with self.lock:
            task = self.tasks.get(task_id)
            if task is None:
                raise LookupError("找不到该任务；MCP 服务重启后，内存中的任务状态会被清空。")
            if task.status not in {"queued", "running"}:
                return TaskState(**asdict(task))
            task.status = "cancelled"
            task.message = "任务已取消。"
            task.completed_at = datetime.now(UTC).isoformat()
            process = self.processes.get(task_id)
            if process is not None and process.poll() is None:
                process.terminate()
            self._persist_locked()
            return TaskState(**asdict(task))

    def start_daily_update(self) -> TaskState:
        with self.lock:
            active = next((task for task in self.tasks.values() if task.task_type == "daily_update" and task.status in {"queued", "running"}), None)
            if active is not None:
                attached = TaskState(**asdict(active))
                attached.reused = True
                return attached
        task = self._create("daily_update", "日常更新已排队。")
        self.executor.submit(self._run_daily_update, task.task_id)
        return task

    def get(self, task_id: str) -> TaskState:
        with self.lock:
            self._recover_stale_locked()
            task = self.tasks.get(task_id)
            if task is None:
                raise LookupError("找不到该任务；MCP 服务重启后，内存中的任务状态会被清空。")
            return TaskState(**asdict(task))

    def _update(self, task_id: str, **values: object) -> None:
        with self.lock:
            task = self.tasks[task_id]
            for key, value in values.items():
                setattr(task, key, value)
            self._persist_locked()

    def _run_command(self, task_id: str, command: list[str], timeout: int = 3600) -> subprocess.CompletedProcess[str]:
        process = subprocess.Popen(command, cwd=self.project_root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        with self.lock:
            self.processes[task_id] = process
        deadline = time.monotonic() + timeout
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    process.terminate()
                    try:
                        stdout, stderr = process.communicate(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        stdout, stderr = process.communicate()
                    raise TimeoutError(f"任务运行超过 {timeout // 60} 分钟，已自动终止。")
                try:
                    stdout, stderr = process.communicate(timeout=min(5, remaining))
                    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
                except subprocess.TimeoutExpired:
                    self._update(task_id, heartbeat_at=datetime.now(UTC).isoformat())
        finally:
            with self.lock:
                self.processes.pop(task_id, None)

    def _run_daily_update(self, task_id: str) -> None:
        steps = [
            ("正在备份投资数据库。", [sys.executable, "-m", "investment_os.app.backup"]),
            ("正在刷新组合综合复核。", [sys.executable, "-m", "investment_os.app.portfolio", "review"]),
        ]
        try:
            for message, command in steps:
                if self.get(task_id).status == "cancelled":
                    return
                self._update(task_id, status="running", message=message)
                result = self._run_command(task_id, command)
                if self.get(task_id).status == "cancelled":
                    return
                if result.returncode != 0:
                    error = (result.stderr or result.stdout or "未知错误").strip().splitlines()[-1]
                    self._update(task_id, status="failed", message=f"日常更新失败：{error[:500]}", completed_at=datetime.now(UTC).isoformat())
                    return
            self._update(
                task_id,
                status="completed",
                message="日常更新完成，数据库已备份并刷新组合复核。",
                report_id="报告中心.html",
                completed_at=datetime.now(UTC).isoformat(),
            )
        except Exception as exc:
            if self.get(task_id).status != "cancelled":
                self._update(task_id, status="failed", message=f"日常更新失败：{str(exc)[:500]}", completed_at=datetime.now(UTC).isoformat())


def _report_files() -> list[Path]:
    return sorted(
        (path for path in REPORTS_ROOT.rglob("*.md") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def _safe_report_path(report_id: str) -> Path:
    candidate = (REPORTS_ROOT / report_id).resolve()
    if REPORTS_ROOT not in candidate.parents or candidate.suffix.lower() != ".md" or not candidate.is_file():
        raise LookupError("找不到指定报告。")
    return candidate


def _report_url(report_id: str) -> str:
    html_id = str(Path(report_id).with_suffix(".html"))
    return f"{REPORT_BASE_URL}/{quote(html_id, safe='/')}"


task_manager = PluginTaskManager()
mcp = MCPServer(
    name="investment-research-os",
    title="个人投资研究系统",
    version="0.6.0",
    instructions=(
        "用于 Bigfish 长期投资研究的确定性计算、结构化记忆、正式研报保存和已有报告读取。"
        "后台不调用大模型，也不生成研报；完整研究与写作由当前 ChatGPT 按 Bigfish 方法完成。读取已有文件报告时先 search 再 fetch。"
        "fetch 会按安全长度分段返回；只要 has_more=true，就继续用 next_offset 调用 fetch，直到取得全部正文，再在对话中连续输出。"
        "开始新研究或复核投资逻辑前，优先调用 get_company_memory；上市公司提供股票代码，未上市公司留空股票代码并提供稳定的公司名称；只有用户明确要求记住或正式记录时，才调用 save_* 研究记忆工具。"
        "CAGR、隐含利润增长和估值情景必须调用确定性计算工具，不要让语言模型自行心算。"
        "只有用户明确要求保存或记住估值时才调用 save_valuation；比较当前与上次估值时先调用 get_valuation_history。"
        "只有用户明确表示交易已经发生并要求正式记录时，才调用 save_confirmed_decision；讨论、计划、建议、估值和假设情景绝不等于成交。"
        "保存交易前必须复述公司、动作、数量及理由并取得确认；数量和仓位是不同字段，不得互相推断。查询历史交易使用 get_decision_history。"
        "用户要求总结并保存公司讨论时（包括 DeepSeek 等未上市公司），先由 ChatGPT 生成结构化纪要并展示给用户；只有用户确认该摘要后才调用 save_discussion_summary。"
        "讨论纪要不等于正式研报、投资论点或真实交易，不得自动升级为这些记录；历史纪要使用 get_discussion_history 查询。"
        "完整研报由当前 ChatGPT 按 Bigfish 方法生成；用户确认保存后依次调用 create_report_draft、append_report_section 和 finalize_research_report。"
        "后台只保存和读取，不调用模型生成研报。长研报必须分章节保存；读取时使用 get_saved_research_report 并按 next_offset 取完全文。"
        "如果所需写入工具不存在、不可见或调用失败，必须如实说明并停止；绝对禁止改用其他应用、终端、文件工具或直接数据库写入绕过本服务接口。"
        "研究观点不等于真实交易，当前记忆工具不得据此推断买入、卖出、加仓或减仓。"
    ),
)


@mcp.tool(
    name="search",
    title="搜索投资研究报告",
    description="Use this when the user wants to find existing company, monitoring, comparison, or portfolio reports before reading one.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    structured_output=False,
)
def search(query: str) -> str:
    normalized = query.strip().lower()
    results = []
    for path in _report_files():
        report_id = str(path.relative_to(REPORTS_ROOT))
        title = path.stem
        if normalized:
            haystack = f"{report_id} {title}".lower()
            if normalized not in haystack:
                try:
                    preview = path.read_text(encoding="utf-8")[:4000].lower()
                except OSError:
                    continue
                if normalized not in preview:
                    continue
        results.append({"id": report_id, "title": title, "url": _report_url(report_id)})
        if len(results) >= 20:
            break
    return json.dumps({"results": results}, ensure_ascii=False)


@mcp.tool(
    name="fetch",
    title="读取投资研究报告",
    description="Use this when the user wants the full text of a report returned by search so it can be summarized, challenged, or discussed.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    structured_output=False,
)
def fetch(id: str, offset: int = 0, max_chars: int = 12000) -> str:
    path = _safe_report_path(id)
    if offset < 0:
        raise ValueError("offset 不能小于 0。")
    max_chars = min(max(max_chars, 1000), 16000)
    full_text = path.read_text(encoding="utf-8")
    text_chunk = full_text[offset:offset + max_chars]
    next_offset = offset + len(text_chunk)
    payload = {
        "id": id,
        "title": path.stem,
        "text": text_chunk,
        "offset": offset,
        "next_offset": next_offset if next_offset < len(full_text) else None,
        "has_more": next_offset < len(full_text),
        "total_chars": len(full_text),
        "url": _report_url(id),
        "metadata": {"modified_at": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()},
    }
    return json.dumps(payload, ensure_ascii=False)


def _private_entity_key(company_name: str) -> str:
    normalized = " ".join(company_name.casefold().split())
    return f"PRIVATE-{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:12].upper()}"


def _memory_identity(ticker: str | None, company_name: str, *, listed_only: bool = False) -> tuple[str, str]:
    name = company_name.strip()
    raw_ticker = (ticker or "").strip()
    if raw_ticker:
        symbol = raw_ticker.upper()
        if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", symbol):
            raise ValueError("请输入有效的股票代码，例如 NVDA；未上市公司请留空股票代码并填写公司名称。")
    else:
        if listed_only:
            raise ValueError("该工具只适用于上市公司，请提供股票代码。")
        if not name:
            raise ValueError("公司名称不能为空；上市公司还可以同时提供股票代码。")
        symbol = _private_entity_key(name)
    if not name:
        raise ValueError("公司名称不能为空。")
    return symbol, name


def _lookup_identity(ticker: str | None, company_name: str | None = None) -> str:
    symbol, _ = _memory_identity(ticker, company_name or (ticker or ""))
    return symbol


@mcp.tool(
    name="get_company_memory",
    title="读取公司投资记忆",
    description="Use this before new research or an investment-logic review. For a listed company provide ticker; for an unlisted company such as DeepSeek leave ticker empty and provide company_name.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
def get_company_memory(ticker: str | None = None, company_name: str | None = None) -> dict[str, object]:
    symbol = _lookup_identity(ticker, company_name)
    return knowledge_service().get_company_memory(symbol)


@mcp.tool(
    name="search_memory",
    title="搜索历史投资记忆",
    description="Use this to search saved theses, assumptions, predictions, critical unknowns, and watch variables by keyword, optionally within one ticker.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
def search_memory(query: str, ticker: str | None = None, limit: int = 20, company_name: str | None = None) -> dict[str, object]:
    symbol = _lookup_identity(ticker, company_name) if ticker or company_name else None
    return knowledge_service().search_memory(query, ticker=symbol, limit=limit)


def _confidence(value: float | None) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def _parse_optional_date(value: str | None, field_name: str) -> date | None:
    if value is None or not str(value).strip():
        return None
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"{field_name} 必须是 YYYY-MM-DD 格式的日期。") from exc


@mcp.tool(
    name="save_thesis",
    title="保存投资论点",
    description="Save a formal, versioned investment thesis only when the user asks to remember or formally record the discussed thesis. This does not record a trade.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
)
def save_thesis(
    ticker: str | None = None,
    company_name: str = "",
    thesis: str = "",
    confidence: float | None = None,
    supersedes_thesis_id: str | None = None,
) -> dict[str, object]:
    symbol, name = _memory_identity(ticker, company_name)
    previous_id = UUID(supersedes_thesis_id) if supersedes_thesis_id else None
    return knowledge_service().save_thesis(
        symbol,
        name,
        thesis,
        confidence=_confidence(confidence),
        supersedes_thesis_id=previous_id,
    )


@mcp.tool(
    name="save_assumption",
    title="保存关键投资假设",
    description="Save a high-impact assumption after the user asks to remember or formally record it. Use confidence from 0 to 1.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
)
def save_assumption(ticker: str | None = None, company_name: str = "", description: str = "", impact: str = "", confidence: float | None = None) -> dict[str, object]:
    symbol, name = _memory_identity(ticker, company_name)
    return knowledge_service().save_assumption(symbol, name, description, impact, confidence=_confidence(confidence))


@mcp.tool(
    name="save_prediction",
    title="保存可验证预测",
    description="Save a meaningful falsifiable prediction when the user asks to remember or track it. Include expected_verification_date (YYYY-MM-DD) when the prediction can be checked on a specific date. Do not store vague opinions as predictions.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
)
def save_prediction(
    ticker: str | None = None,
    company_name: str = "",
    prediction: str = "",
    confidence: float | None = None,
    expected_verification_date: str | None = None,
) -> dict[str, object]:
    symbol, name = _memory_identity(ticker, company_name)
    return knowledge_service().save_prediction(
        symbol,
        name,
        prediction,
        confidence=_confidence(confidence),
        expected_verification_date=_parse_optional_date(expected_verification_date, "expected_verification_date"),
    )


@mcp.tool(
    name="get_prediction_history",
    title="读取预测历史",
    description="Use this to review saved predictions for a company. Optionally filter by outcome: pending, correct, wrong, or partially_correct.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
def get_prediction_history(
    ticker: str | None = None,
    company_name: str | None = None,
    outcome: str | None = None,
    limit: int = 20,
) -> dict[str, object]:
    symbol = _lookup_identity(ticker, company_name)
    normalized_outcome = outcome.strip().lower() if outcome else None
    if normalized_outcome == "pending":
        pass
    elif normalized_outcome in {"correct", "wrong", "partially_correct"}:
        pass
    elif normalized_outcome is not None:
        raise ValueError("outcome 必须是 pending、correct、wrong 或 partially_correct")
    return knowledge_service().get_prediction_history(symbol, outcome=normalized_outcome, limit=limit)


@mcp.tool(
    name="list_pending_predictions",
    title="列出待复盘预测",
    description="List predictions that are still pending review. Optionally filter to one ticker or to predictions due on or before due_by (YYYY-MM-DD).",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
def list_pending_predictions(
    ticker: str | None = None,
    company_name: str | None = None,
    due_by: str | None = None,
    limit: int = 50,
) -> dict[str, object]:
    symbol = _lookup_identity(ticker, company_name) if ticker or company_name else None
    return knowledge_service().list_pending_predictions(
        ticker=symbol,
        due_by=_parse_optional_date(due_by, "due_by"),
        limit=limit,
    )


@mcp.tool(
    name="record_prediction_result",
    title="记录预测复盘结果",
    description="Record the actual outcome after a falsifiable prediction can be verified. Requires confirm_review=true and explicit user confirmation that the review is accurate. Outcome must be correct, wrong, or partially_correct.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
)
def record_prediction_result(
    prediction_id: str,
    actual_result: str,
    outcome: str,
    error_reason: str | None = None,
    confirm_review: bool = False,
) -> dict[str, object]:
    if not confirm_review:
        raise PermissionError("必须设置 confirm_review=true，并在用户确认复盘结论准确后才能记录预测结果。")
    return knowledge_service().record_prediction_result(
        UUID(prediction_id),
        actual_result,
        outcome,
        error_reason=error_reason,
        explicit_user_confirmation=True,
    )


@mcp.tool(
    name="save_critical_unknown",
    title="保存关键未知",
    description="Save an unresolved, high-impact question that could change the investment conclusion.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
)
def save_critical_unknown(ticker: str | None = None, company_name: str = "", description: str = "", impact: str = "", confidence: float | None = None) -> dict[str, object]:
    symbol, name = _memory_identity(ticker, company_name)
    return knowledge_service().save_critical_unknown(symbol, name, description, impact, confidence=_confidence(confidence))


@mcp.tool(
    name="save_watch_variable",
    title="保存或更新跟踪变量",
    description="Save or update one of the small number of variables that determine a company's long-term thesis.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
def save_watch_variable(
    ticker: str | None = None,
    company_name: str = "",
    name: str = "",
    rationale: str = "",
    current_assessment: str | None = None,
) -> dict[str, object]:
    symbol, company = _memory_identity(ticker, company_name)
    return knowledge_service().save_watch_variable(
        symbol,
        company,
        name,
        rationale,
        current_assessment=current_assessment,
    )


@mcp.tool(
    name="calculate_cagr",
    title="计算复合年增长率",
    description="Use this deterministic calculator for revenue, operating profit, EPS, or other positive beginning and ending values. Do not use it across losses or zero values.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
def calculate_cagr(begin_value: float, end_value: float, years: float) -> dict[str, float]:
    return calculate_cagr_value(begin_value, end_value, years)


@mcp.tool(
    name="calculate_required_profit_growth",
    title="计算五年隐含利润增长率",
    description="Use this for Bigfish reverse valuation: calculate the annual profit growth required by current P/E, terminal P/E, target return, dividend yield, and holding period.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
def calculate_required_profit_growth(
    current_pe: float,
    terminal_pe: float,
    target_return_pct: float = 13.0,
    dividend_yield_pct: float = 0.0,
    years: int = 5,
) -> dict[str, float | str]:
    return calculate_required_profit_growth_value(current_pe, terminal_pe, target_return_pct, dividend_yield_pct, years)


@mcp.tool(
    name="valuation_scenario_analysis",
    title="五年估值情景分析",
    description="Compare bear, base, and bull profit-growth and terminal-P/E assumptions using deterministic arithmetic and show whether each meets the target return.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
def valuation_scenario_analysis(
    current_pe: float,
    scenarios: list[dict[str, float | str]],
    dividend_yield_pct: float = 0.0,
    years: int = 5,
    target_return_pct: float = 13.0,
) -> dict[str, object]:
    return run_scenario_analysis(
        current_pe,
        scenarios,
        dividend_yield_pct=dividend_yield_pct,
        years=years,
        target_return_pct=target_return_pct,
    )


@mcp.tool(
    name="save_valuation",
    title="保存正式估值记录",
    description="Save a formal valuation snapshot only when the user explicitly asks to save or remember the valuation. Percent inputs use ordinary percentage points, for example 13 means 13%.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
)
def save_valuation(
    ticker: str,
    company_name: str,
    reference_price: float,
    currency: str = "USD",
    target_return_pct: float = 13.0,
    bear_expected_return_pct: float | None = None,
    base_expected_return_pct: float | None = None,
    bull_expected_return_pct: float | None = None,
    assumptions: dict[str, object] | None = None,
    scenarios: dict[str, object] | None = None,
    confirm_save: bool = False,
) -> dict[str, object]:
    if not confirm_save:
        raise ValueError("保存正式估值会修改投资记忆库；只有用户明确要求保存时，才能将 confirm_save 设为 true。")
    symbol, name = _memory_identity(ticker, company_name, listed_only=True)
    return knowledge_service().save_valuation(
        symbol,
        name,
        reference_price=Decimal(str(reference_price)),
        currency=currency,
        target_return_pct=_confidence(target_return_pct),
        bear_expected_return_pct=_confidence(bear_expected_return_pct),
        base_expected_return_pct=_confidence(base_expected_return_pct),
        bull_expected_return_pct=_confidence(bull_expected_return_pct),
        assumptions=assumptions,
        scenarios=scenarios,
    )


@mcp.tool(
    name="get_valuation_history",
    title="读取估值历史",
    description="Read a company's saved valuation snapshots and compare the latest two records. Use this to answer how valuation has changed since the previous review.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
def get_valuation_history(ticker: str, limit: int = 20) -> dict[str, object]:
    symbol = ticker.upper().strip()
    if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", symbol):
        raise ValueError("请输入有效的股票代码，例如 NVDA。")
    return knowledge_service().get_valuation_history(symbol, limit=limit)


@mcp.tool(
    name="save_confirmed_decision",
    title="保存已确认的真实投资决策",
    description=(
        "Use this only after the user explicitly says a real transaction or portfolio action has already occurred, asks to formally record it, "
        "and confirms the exact company, action, quantity or position weight, and rationale. Never use for hypothetical trades, recommendations, plans, valuation notes, or inferred actions."
    ),
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
)
def save_confirmed_decision(
    ticker: str,
    company_name: str,
    action: str,
    core_thesis: str,
    confirm_transaction: bool = False,
    quantity: float | None = None,
    quantity_unit: str | None = None,
    price: float | None = None,
    currency: str | None = None,
    position_weight_pct: float | None = None,
    target_return_pct: float | None = None,
    decision_type: str | None = None,
    expected_returns: dict[str, object] | None = None,
    critical_assumptions: list[str] | None = None,
    major_risks: list[str] | None = None,
    buy_more_conditions: list[str] | None = None,
    sell_conditions: list[str] | None = None,
    confidence: float | None = None,
    notes: str | None = None,
) -> dict[str, object]:
    if not confirm_transaction:
        raise ValueError("这会写入真实投资决策；必须先向用户复述交易细节并取得明确确认，然后才能将 confirm_transaction 设为 true。")
    symbol, name = _memory_identity(ticker, company_name, listed_only=True)
    if quantity is None and position_weight_pct is None:
        raise ValueError("必须至少提供真实成交数量或确认后的组合仓位比例；不得从讨论内容推断。")
    return knowledge_service().save_confirmed_decision(
        symbol,
        name,
        action,
        core_thesis,
        explicit_user_confirmation=True,
        price=Decimal(str(price)) if price is not None else None,
        currency=currency,
        quantity=Decimal(str(quantity)) if quantity is not None else None,
        quantity_unit=quantity_unit,
        position_weight_pct=_confidence(position_weight_pct),
        target_return_pct=_confidence(target_return_pct),
        decision_type=decision_type,
        expected_returns=expected_returns,
        critical_assumptions=critical_assumptions,
        major_risks=major_risks,
        buy_more_conditions=buy_more_conditions,
        sell_conditions=sell_conditions,
        confidence=_confidence(confidence),
        notes=notes,
    )


@mcp.tool(
    name="get_decision_history",
    title="读取真实投资决策历史",
    description="Use this when the user wants to review confirmed buy, sell, add, reduce, hold, or observation-position decisions saved for a company.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
def get_decision_history(ticker: str, limit: int = 20) -> dict[str, object]:
    symbol = ticker.upper().strip()
    if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", symbol):
        raise ValueError("请输入有效的股票代码，例如 CRCL。")
    return knowledge_service().get_decision_history(symbol, limit=limit)


@mcp.tool(
    name="save_discussion_summary",
    title="保存已确认的公司讨论纪要",
    description=(
        "Use this when the user asks to preserve a company discussion, including an unlisted company. First summarize the current conversation, show the complete structured summary, "
        "and obtain explicit confirmation. Save only the distilled summary, not a raw chat transcript. This does not record a trade or replace a formal thesis."
    ),
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
)
def save_discussion_summary(
    ticker: str | None = None,
    company_name: str = "",
    title: str = "",
    summary: str = "",
    confirm_save: bool = False,
    key_points: list[str] | None = None,
    changed_views: list[str] | None = None,
    conclusions: list[str] | None = None,
    unresolved_questions: list[str] | None = None,
    follow_up_items: list[str] | None = None,
    source_chat_reference: str | None = None,
    related_report_id: str | None = None,
) -> dict[str, object]:
    if not confirm_save:
        raise ValueError("必须先向用户展示完整讨论纪要并取得明确确认，才能将 confirm_save 设为 true。")
    symbol, name = _memory_identity(ticker, company_name)
    return knowledge_service().save_discussion_summary(
        symbol,
        name,
        title,
        summary,
        explicit_user_confirmation=True,
        key_points=key_points,
        changed_views=changed_views,
        conclusions=conclusions,
        unresolved_questions=unresolved_questions,
        follow_up_items=follow_up_items,
        source_chat_reference=source_chat_reference,
        related_report_id=related_report_id,
    )


@mcp.tool(
    name="get_discussion_history",
    title="读取公司讨论历史",
    description="Use this when the user wants to find or review previously confirmed discussion summaries for a company before continuing research or conducting a retrospective.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
def get_discussion_history(ticker: str | None = None, limit: int = 20, company_name: str | None = None) -> dict[str, object]:
    symbol = _lookup_identity(ticker, company_name)
    return knowledge_service().get_discussion_history(symbol, limit=limit)


@mcp.tool(
    name="create_report_draft",
    title="创建正式研报草稿",
    description="Use this after ChatGPT has generated a report and the user explicitly confirms it should be saved. Creates a new versioned draft; the backend does not generate report content.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
)
def create_report_draft(
    ticker: str | None = None,
    company_name: str = "",
    title: str = "",
    summary: str | None = None,
    confirm_save: bool = False,
) -> dict[str, object]:
    if not confirm_save:
        raise ValueError("必须先展示完整研报并取得用户确认，才能创建正式研报草稿。")
    symbol, name = _memory_identity(ticker, company_name)
    return knowledge_service().create_report_draft(
        symbol,
        name,
        title,
        summary=summary,
        explicit_user_confirmation=True,
    )


@mcp.tool(
    name="append_report_section",
    title="写入或更新研报章节",
    description="Use this to save one section of a user-approved report draft. Calls with the same report_id and section_order replace that section, making retries safe.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
def append_report_section(report_id: str, section_order: int, heading: str, content: str) -> dict[str, object]:
    if len(content) > 12000:
        raise ValueError("单个章节不能超过 12000 个字符，请拆成多个章节保存。")
    return knowledge_service().append_report_section(UUID(report_id), section_order, heading, content)


@mcp.tool(
    name="finalize_research_report",
    title="确认并定稿研报",
    description="Use this only after all sections of a saved draft have been checked and the user explicitly confirms finalization. Finalized versions are immutable.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
def finalize_research_report(
    report_id: str,
    confirm_finalize: bool = False,
    change_summary: list[str] | None = None,
) -> dict[str, object]:
    if not confirm_finalize:
        raise ValueError("必须取得用户明确确认，才能将研报定稿。")
    return knowledge_service().finalize_report(
        UUID(report_id),
        explicit_user_confirmation=True,
        change_summary=change_summary,
    )


@mcp.tool(
    name="get_saved_research_report",
    title="读取已保存研报",
    description="Use this to read a report saved by ChatGPT. Continue with next_offset while has_more is true so the complete Markdown is retrieved.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
def get_saved_research_report(report_id: str, offset: int = 0, max_chars: int = 12000) -> dict[str, object]:
    if offset < 0:
        raise ValueError("offset 不能小于 0。")
    max_chars = min(max(max_chars, 1000), 16000)
    result = knowledge_service().get_saved_report(UUID(report_id))
    if not result.get("found"):
        return result
    markdown = str(result.pop("markdown"))
    sections = result.pop("sections", [])
    section_index = [
        {"section_order": item["section_order"], "heading": item["heading"]}
        for item in sections
    ]
    chunk = markdown[offset:offset + max_chars]
    next_offset = offset + len(chunk)
    return {
        **result,
        "section_index": section_index,
        "text": chunk,
        "offset": offset,
        "next_offset": next_offset if next_offset < len(markdown) else None,
        "has_more": next_offset < len(markdown),
        "total_chars": len(markdown),
    }


@mcp.tool(
    name="get_saved_report_history",
    title="读取正式研报版本历史",
    description="Use this to list ChatGPT-authored saved report versions for a company, including draft/finalized status and links to the previous version.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
def get_saved_report_history(ticker: str | None = None, limit: int = 20, company_name: str | None = None) -> dict[str, object]:
    symbol = _lookup_identity(ticker, company_name)
    return knowledge_service().get_saved_report_history(symbol, limit=limit)


@mcp.tool(
    name="get_task_status",
    title="查询后台维护任务状态",
    description="Use this when the user wants to know whether a previously started daily-update task has completed.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
def get_task_status(task_id: str) -> dict[str, object]:
    return asdict(task_manager.get(task_id))


@mcp.tool(
    name="list_tasks",
    title="列出后台维护任务",
    description="Use this to inspect recent daily-update tasks, especially when the service reports that another task is already running.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
def list_tasks(limit: int = 20) -> dict[str, object]:
    safe_limit = max(1, min(limit, 100))
    return {"tasks": [asdict(task) for task in task_manager.list(safe_limit)]}


@mcp.tool(
    name="cancel_task",
    title="取消后台维护任务",
    description="Use this when the user explicitly asks to cancel a queued or running daily-update task.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False),
)
def cancel_task(task_id: str) -> dict[str, object]:
    return asdict(task_manager.cancel(task_id))


@mcp.tool(
    name="start_daily_update",
    title="更新全部日常报告",
    description="Use this when the user asks to back up the database and refresh the portfolio review without running any AI research.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True),
)
def start_daily_update() -> dict[str, object]:
    return asdict(task_manager.start_daily_update())


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "investment-research-os-mcp"})


def main() -> None:
    host = os.getenv("MCP_HOST", "127.0.0.1")
    port = int(os.getenv("MCP_PORT", "8090"))
    mcp.run(
        transport="streamable-http",
        host=host,
        port=port,
        streamable_http_path="/mcp",
        stateless_http=True,
    )


if __name__ == "__main__":
    main()
