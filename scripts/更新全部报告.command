#!/bin/zsh

set -u

SCRIPT_DIR=${0:A:h}
PROJECT_DIR=${SCRIPT_DIR:h}
cd "$PROJECT_DIR" || exit 1

echo "Investment Research OS｜开始更新"
echo ""

if [[ ! -x ".venv/bin/python" ]]; then
  echo "未找到项目运行环境：.venv/bin/python"
  echo "请先完成项目安装。"
  read "?按回车键关闭窗口..."
  exit 1
fi

echo "① 备份本地投资数据库"
.venv/bin/python -m investment_os.app.backup
backup_status=$?
echo ""

echo "② 更新组合综合复核"
.venv/bin/python -m investment_os.app.portfolio review
portfolio_status=$?
echo ""

if (( portfolio_status == 0 )); then
  echo "③ 打开报告中心"
  open "reports/报告中心.html"
fi

if (( backup_status == 0 && portfolio_status == 0 )); then
  echo ""
  echo "全部更新完成。"
else
  echo ""
  echo "部分更新未完成，请查看上方提示；已经成功的报告仍然保留。"
fi

read "?按回车键关闭窗口..."
