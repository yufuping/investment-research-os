#!/bin/zsh
set -u

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR" || exit 1
.venv/bin/python tools/local_services.py start

echo
echo "按回车键关闭本窗口（服务会继续运行）。"
read -r
