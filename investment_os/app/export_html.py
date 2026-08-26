import argparse
from pathlib import Path

from investment_os.reports.html import save_html_report
from investment_os.reports.index import build_report_center


def main() -> None:
    parser = argparse.ArgumentParser(description="把已有 Markdown 报告转换成浏览器版 HTML")
    parser.add_argument("path", type=Path, help="Markdown 报告路径")
    parser.add_argument("--title", default="投资研究报告", help="浏览器页面标题")
    parser.add_argument("--latest-name", help="可选：同时更新固定名称，例如 NVDA-最新.html")
    args = parser.parse_args()
    if not args.path.exists() or args.path.suffix.lower() != ".md":
        raise SystemExit("请输入存在的 .md 报告文件。")
    html_path = save_html_report(args.path, args.title, args.latest_name)
    reports_root = next((parent for parent in args.path.parents if parent.name == "reports"), args.path.parent)
    center_path = build_report_center(reports_root)
    print(f"浏览器报告已保存：{html_path}")
    print(f"报告中心已更新：{center_path}")


if __name__ == "__main__":
    main()
