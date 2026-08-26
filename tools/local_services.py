#!/usr/bin/env python3
"""Investment Research OS 本地服务的一键启动、状态检查和停止。"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

from dotenv import dotenv_values


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = PROJECT_ROOT / ".runtime"
LOG_DIR = RUNTIME_DIR / "logs"
STATE_PATH = RUNTIME_DIR / "local-services.json"
PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"
TUNNEL = PROJECT_ROOT / "tools" / "bin" / "tunnel-client"
ENV_FILE = PROJECT_ROOT.parent / ".env.local"
TUNNEL_HEALTH_FILE = Path.home() / "Library" / "Application Support" / "tunnel-client" / "health" / "investment-research-os.url"

SERVICES = {
    "web": {
        "label": "浏览器网页",
        "command": [str(PYTHON), "-m", "investment_os.app.web"],
        "port": 8080,
        "health": "http://127.0.0.1:8080/health",
        "marker": "investment_os.app.web",
    },
    "mcp": {
        "label": "ChatGPT MCP",
        "command": [str(PYTHON), "-m", "investment_os.app.mcp_server"],
        "port": 8090,
        "health": "http://127.0.0.1:8090/health",
        "marker": "investment_os.app.mcp_server",
    },
    "tunnel": {
        "label": "OpenAI 安全隧道",
        "command": [
            str(TUNNEL),
            "run",
            "--profile-dir",
            str(PROJECT_ROOT / "config" / "tunnel"),
            "--profile",
            "investment-research-os",
            "--control-plane.http-proxy",
            "http://127.0.0.1:7890",
        ],
        "port": None,
        "health": None,
        "marker": "tunnel-client run --profile-dir",
    },
}


def load_state() -> dict[str, int]:
    try:
        return {key: int(value) for key, value in json.loads(STATE_PATH.read_text()).items()}
    except (FileNotFoundError, ValueError, TypeError, json.JSONDecodeError):
        return {}


def save_state(state: dict[str, int]) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def port_open(port: int | None) -> bool:
    if port is None:
        return False
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            return True
    except OSError:
        return False


def health_ok(url: str | None) -> bool:
    if not url:
        return False
    try:
        with urlopen(url, timeout=1.5) as response:
            return 200 <= response.status < 300
    except Exception:
        return False


def discover_pid(marker: str) -> int | None:
    try:
        result = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True, check=False)
    except (OSError, PermissionError):
        return None
    for line in result.stdout.splitlines():
        if marker in line and "local_services.py" not in line:
            try:
                return int(line.strip().split(maxsplit=1)[0])
            except (ValueError, IndexError):
                continue
    return None


def tunnel_health_ok() -> bool:
    try:
        url = TUNNEL_HEALTH_FILE.read_text(encoding="utf-8").strip().rstrip("/") + "/"
    except OSError:
        return False
    return health_ok(url)


def runtime_env() -> dict[str, str]:
    env = os.environ.copy()
    if ENV_FILE.exists():
        env.update({key: value for key, value in dotenv_values(ENV_FILE).items() if value is not None})
    api_key = env.get("OPENAI_API_KEY")
    if api_key:
        env["CONTROL_PLANE_API_KEY"] = api_key
    # 该入口只用于本机回环地址，不对外网开放网页服务。
    env["WEB_LOCAL_ONLY"] = "true"
    return env


def start() -> int:
    if not PYTHON.exists():
        print("❌ 找不到 Python 虚拟环，请先安装项目依赖。")
        return 1
    if not TUNNEL.exists():
        print("❌ 找不到 OpenAI 安全隧道程序。")
        return 1

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()
    env = runtime_env()
    for name, config in SERVICES.items():
        pid = state.get(name)
        if not pid_alive(pid):
            pid = discover_pid(str(config["marker"]))
        already_running = pid_alive(pid) or (config["port"] and port_open(int(config["port"])))
        if name == "tunnel":
            already_running = already_running or tunnel_health_ok()
        if already_running:
            if pid:
                state[name] = pid
            print(f"✅ {config['label']}已在运行")
            continue
        if name == "tunnel" and not env.get("CONTROL_PLANE_API_KEY"):
            print("❌ .env.local 中缺少 OPENAI_API_KEY，无法启动安全隧道。")
            continue
        log_path = LOG_DIR / f"{name}.log"
        log_file = log_path.open("ab")
        process = subprocess.Popen(
            config["command"],
            cwd=PROJECT_ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        log_file.close()
        state[name] = process.pid
        print(f"▶️ 正在启动{config['label']}……")

    save_state(state)
    time.sleep(2)
    return show_status(state)


def show_status(state: dict[str, int] | None = None) -> int:
    state = state or load_state()
    all_ready = True
    print("\nInvestment Research OS 状态：")
    for name, config in SERVICES.items():
        pid = state.get(name)
        if not pid_alive(pid):
            pid = discover_pid(str(config["marker"]))
        if name == "tunnel":
            ready = pid_alive(pid) or tunnel_health_ok()
        else:
            ready = pid_alive(pid) and (health_ok(str(config["health"])) or port_open(int(config["port"])))
        all_ready = all_ready and ready
        print(f"  {'✅' if ready else '❌'} {config['label']}" + (f" (PID {pid})" if pid else ""))
    if all_ready:
        print("\n✅ 全部服务已就绪，现在可以在 ChatGPT 中使用 Investment Research OS。")
        print("浏览器入口：http://127.0.0.1:8080")
        return 0
    print(f"\n⚠️ 有服务未就绪，请查看日志：{LOG_DIR}")
    return 1


def stop() -> int:
    state = load_state()
    for name, config in reversed(list(SERVICES.items())):
        pid = state.get(name)
        if not pid_alive(pid):
            pid = discover_pid(str(config["marker"]))
        if not pid_alive(pid):
            print(f"○ {config['label']}未运行")
            continue
        os.kill(pid, signal.SIGTERM)
        print(f"⏹️ 已停止{config['label']}")
    save_state({})
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Investment Research OS 本地服务管理")
    parser.add_argument("action", nargs="?", choices=("start", "status", "stop"), default="start")
    args = parser.parse_args()
    return {"start": start, "status": show_status, "stop": stop}[args.action]()


if __name__ == "__main__":
    sys.exit(main())
