from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from functools import wraps
import hmac
import os
from pathlib import Path
import subprocess
import sys
from threading import Lock

from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, session, url_for

from investment_os.app.config import PROJECT_ROOT


class ResearchTaskManager:
    def __init__(self, project_root: Path = PROJECT_ROOT) -> None:
        self.project_root = project_root
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="daily-update")
        self.lock = Lock()
        self.state = {"status": "idle", "task_type": None, "ticker": None, "message": "尚无运行中的任务。", "report_url": None}

    def snapshot(self) -> dict:
        with self.lock:
            return dict(self.state)

    def start_daily_update(self) -> bool:
        with self.lock:
            if self.state["status"] in {"queued", "running"}:
                return False
            self.state = {"status": "queued", "task_type": "daily_update", "ticker": None, "message": "日常更新已排队。", "report_url": None}
        self.executor.submit(self._run_daily_update)
        return True

    def _run_daily_update(self) -> None:
        steps = [
            ("正在备份投资数据库。", [sys.executable, "-m", "investment_os.app.backup"]),
            ("正在刷新组合综合复核。", [sys.executable, "-m", "investment_os.app.portfolio", "review"]),
        ]
        for message, command in steps:
            with self.lock:
                self.state.update(status="running", message=message)
            result = subprocess.run(command, cwd=self.project_root, text=True, capture_output=True, timeout=3600)
            if result.returncode != 0:
                error = (result.stderr or result.stdout or "未知错误").strip().splitlines()[-1]
                with self.lock:
                    self.state.update(status="failed", message=f"日常更新失败：{error[:500]}", report_url=None)
                return
        with self.lock:
            self.state.update(status="completed", message="日常更新完成，数据库已备份并刷新组合复核。", report_url="/reports/报告中心.html")


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, template_folder="../../templates")
    app.config.update(
        SECRET_KEY=os.getenv("WEB_SECRET_KEY", ""),
        WEB_USERNAME=os.getenv("WEB_USERNAME", "admin"),
        WEB_PASSWORD=os.getenv("WEB_PASSWORD", ""),
        REPORTS_ROOT=PROJECT_ROOT / "reports",
        LOCAL_ONLY=os.getenv("WEB_LOCAL_ONLY", "").lower() in {"1", "true", "yes"},
    )
    if test_config:
        app.config.update(test_config)
    if app.config["LOCAL_ONLY"] and not app.config["SECRET_KEY"]:
        app.config["SECRET_KEY"] = "local-loopback-session"
    if not app.config.get("TESTING") and not app.config["LOCAL_ONLY"] and (not app.config["SECRET_KEY"] or not app.config["WEB_PASSWORD"]):
        raise RuntimeError("云端页面需要设置 WEB_SECRET_KEY 和 WEB_PASSWORD。")
    app.extensions["task_manager"] = ResearchTaskManager(PROJECT_ROOT)

    def login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if app.config["LOCAL_ONLY"]:
                return view(*args, **kwargs)
            if not session.get("authenticated"):
                return redirect(url_for("login", next=request.path))
            return view(*args, **kwargs)
        return wrapped

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        error = None
        if request.method == "POST":
            username_ok = hmac.compare_digest(request.form.get("username", ""), app.config["WEB_USERNAME"])
            password_ok = hmac.compare_digest(request.form.get("password", ""), app.config["WEB_PASSWORD"])
            if username_ok and password_ok:
                session.clear()
                session["authenticated"] = True
                return redirect(request.args.get("next") or url_for("dashboard"))
            error = "用户名或密码错误。"
        return render_template("login.html", error=error)

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/")
    @login_required
    def dashboard():
        return render_template("dashboard.html", task=app.extensions["task_manager"].snapshot())

    @app.post("/update/daily")
    @login_required
    def daily_update():
        if not app.extensions["task_manager"].start_daily_update():
            return render_template("dashboard.html", task=app.extensions["task_manager"].snapshot(), error="已有任务正在运行，请等待完成。"), 409
        return redirect(url_for("task_status"))

    @app.get("/task")
    @login_required
    def task_status():
        return render_template("task.html", task=app.extensions["task_manager"].snapshot())

    @app.get("/api/task")
    @login_required
    def task_api():
        return jsonify(app.extensions["task_manager"].snapshot())

    @app.get("/reports/<path:filename>")
    @login_required
    def reports(filename: str):
        return send_from_directory(app.config["REPORTS_ROOT"], filename)

    return app


app = create_app() if (os.getenv("WEB_PASSWORD") and os.getenv("WEB_SECRET_KEY")) or os.getenv("WEB_LOCAL_ONLY", "").lower() in {"1", "true", "yes"} else None


def main() -> None:
    port = int(os.getenv("PORT", "8080"))
    local_only = os.getenv("WEB_LOCAL_ONLY", "").lower() in {"1", "true", "yes"}
    create_app().run(host="127.0.0.1" if local_only else "0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    main()
