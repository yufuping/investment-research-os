from html import escape
import json
from pathlib import Path
import re
from urllib.parse import quote


def _inline(text: str) -> str:
    safe = escape(text.strip())
    safe = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', safe)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", safe)


def _table_cell(text: str, header: str, company_links: dict[str, str] | None = None) -> str:
    rendered = _inline(text)
    if header == "公司" and company_links and text.strip().upper() in company_links:
        ticker = text.strip().upper()
        return f'<a class="company-link" href="{escape(company_links[ticker], quote=True)}">{rendered}</a>'
    if header in {"组合权重", "占核心个股组合", "压力后权重", "损失贡献", "影响比例"}:
        match = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)%", text.strip())
        if match:
            value = float(match.group(1))
            width = min(abs(value), 100.0)
            tone = "negative" if value < 0 else "positive"
            return f'<div class="metric {tone}"><span style="width:{width:.2f}%"></span><b>{rendered}</b></div>'
    if header == "级别" and text.strip() in {"高", "中", "低", "正常"}:
        level_class = {"高": "high", "中": "medium", "低": "low", "正常": "normal"}[text.strip()]
        return f'<span class="badge {level_class}">{rendered}</span>'
    return rendered


def _allocation_chart(headers: list[str], rows: list[list[str]]) -> str:
    if "公司" not in headers or "组合权重" not in headers:
        return ""
    ticker_index = headers.index("公司")
    weight_index = headers.index("组合权重")
    colors = ["#2f6fed", "#23a48b", "#f29e4c", "#8b6bd6", "#e25b6a", "#53a7d8", "#82934b", "#b66b3d"]
    segments = []
    legend = []
    start = 0.0
    for position, row in enumerate(rows):
        if ticker_index >= len(row) or weight_index >= len(row):
            continue
        match = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)%", row[weight_index].strip())
        if not match:
            continue
        weight = max(float(match.group(1)), 0.0)
        end = min(start + weight, 100.0)
        color = colors[position % len(colors)]
        segments.append(f"{color} {start:.2f}% {end:.2f}%")
        legend.append(f'<li><i style="background:{color}"></i><span>{_inline(row[ticker_index])}</span><b>{weight:.2f}%</b></li>')
        start = end
    if not segments:
        return ""
    return '<section class="allocation"><h3>核心个股组合权重</h3><div class="allocation-grid"><div class="donut" style="background:conic-gradient(' + ",".join(segments) + ')"><span>组合<br>权重</span></div><ul>' + "".join(legend) + "</ul></div></section>"


def _trend_chart(headers: list[str], rows: list[list[str]]) -> str:
    if "复核时间（UTC）" not in headers or "持仓总价值" not in headers or len(rows) < 2:
        return ""
    value_index = headers.index("持仓总价值")
    values = []
    for row in rows:
        if value_index >= len(row):
            continue
        match = re.search(r"-?\d+(?:\.\d+)?", row[value_index].replace(",", ""))
        if match:
            values.append(float(match.group()))
    if len(values) < 2:
        return ""
    width, height, padding = 720, 220, 34
    low, high = min(values), max(values)
    spread = high - low or max(abs(high) * 0.02, 1.0)
    points = []
    for position, value in enumerate(values):
        x = padding + position * (width - padding * 2) / (len(values) - 1)
        y = height - padding - (value - low) / spread * (height - padding * 2)
        points.append(f"{x:.1f},{y:.1f}")
    return f'<section class="trend"><h3>持仓总价值趋势</h3><svg viewBox="0 0 {width} {height}" role="img" aria-label="最近有效快照的持仓总价值趋势"><line x1="{padding}" y1="{height-padding}" x2="{width-padding}" y2="{height-padding}"/><polyline points="{" ".join(points)}"/><text x="{padding}" y="20">最高 {high:,.0f} 美元</text><text x="{padding}" y="{height-8}">最低 {low:,.0f} 美元</text></svg></section>'


def markdown_to_html(markdown: str, title: str, company_links: dict[str, str] | None = None, home_link: str | None = None) -> str:
    """将本项目生成的有限 Markdown 转为无需外部依赖的独立 HTML。"""
    source = markdown.splitlines()
    body: list[str] = []
    navigation = []
    for line in source:
        if line.startswith("## "):
            navigation.append(line[3:].strip())
    index = 0
    list_open = False
    current_heading = ""
    heading_index = 0
    navigation_inserted = False
    while index < len(source):
        line = source[index]
        if list_open and not line.startswith("- "):
            body.append("</ul>")
            list_open = False
        if line.startswith("|") and index + 1 < len(source) and source[index + 1].startswith("|---"):
            headers = [cell.strip() for cell in line.strip("|").split("|")]
            body.append("<div class=\"table-wrap\"><table><thead><tr>" + "".join(f"<th>{_inline(cell)}</th>" for cell in headers) + "</tr></thead><tbody>")
            index += 2
            table_rows = []
            while index < len(source) and source[index].startswith("|"):
                cells = [cell.strip() for cell in source[index].strip("|").split("|")]
                table_rows.append(cells)
                body.append("<tr>" + "".join(f"<td>{_table_cell(cell, headers[position] if position < len(headers) else '', company_links)}</td>" for position, cell in enumerate(cells)) + "</tr>")
                index += 1
            body.append("</tbody></table></div>")
            body.append(_allocation_chart(headers, table_rows))
            body.append(_trend_chart(headers, table_rows))
            continue
        if line.startswith("#"):
            level = min(len(line) - len(line.lstrip("#")), 4)
            current_heading = line[level:].strip()
            if level == 2:
                heading_index += 1
                body.append(f'<h{level} id="section-{heading_index}">{_inline(current_heading)}</h{level}>')
            else:
                body.append(f"<h{level}>{_inline(current_heading)}</h{level}>")
            if level == 1 and navigation and not navigation_inserted:
                links = "".join(f'<a href="#section-{position}">{_inline(label)}</a>' for position, label in enumerate(navigation, start=1))
                body.append(f'<nav><span>快速导航</span>{links}</nav>')
                navigation_inserted = True
        elif line.startswith("> "):
            body.append(f"<blockquote>{_inline(line[2:])}</blockquote>")
        elif line.startswith("- "):
            if not list_open:
                css_class = ' class="summary-cards"' if current_heading in {"汇总", "汇总结论", "情景结果"} else ""
                body.append(f"<ul{css_class}>")
                list_open = True
            body.append(f"<li>{_inline(line[2:])}</li>")
        elif line.strip() == "---":
            body.append("<hr>")
        elif line.strip():
            body.append(f"<p>{_inline(line)}</p>")
        index += 1
    if list_open:
        body.append("</ul>")
    css = """
body{font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif;max-width:1180px;margin:0 auto;padding:32px;color:#172033;background:#f4f7fb;line-height:1.65}.home-link{display:inline-block;margin-bottom:14px;color:#285c98;text-decoration:none;font-weight:700}.home-link:hover{text-decoration:underline}
main{background:white;padding:36px;border-radius:14px;box-shadow:0 4px 20px #18243b16}h1{margin-top:0;color:#12213a}h2{margin-top:36px;border-bottom:2px solid #e7edf5;padding-bottom:8px;scroll-margin-top:16px}h3{color:#263b5c}nav{display:flex;gap:8px;align-items:center;flex-wrap:wrap;background:#f0f5fb;padding:12px 14px;border-radius:9px;margin:18px 0 26px}nav span{font-weight:700;margin-right:4px}nav a{color:#285c98;text-decoration:none;background:white;border:1px solid #ccdaeb;padding:4px 9px;border-radius:6px}nav a:hover{background:#dceafb}.summary-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px;padding:0;list-style:none}.summary-cards li{background:#f6f9fd;border:1px solid #dce6f2;border-radius:9px;padding:12px 14px;font-variant-numeric:tabular-nums}.allocation,.trend{margin:8px 0 28px;padding:18px;background:#f8fbff;border:1px solid #dce6f2;border-radius:12px}.allocation h3,.trend h3{margin:0 0 14px}.allocation-grid{display:flex;align-items:center;gap:28px;flex-wrap:wrap}.donut{width:190px;height:190px;border-radius:50%;display:grid;place-items:center;flex:none}.donut:before{content:"";position:absolute}.donut span{width:104px;height:104px;border-radius:50%;background:white;display:grid;place-items:center;text-align:center;font-weight:700;color:#40516d}.allocation ul{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(2,minmax(140px,1fr));gap:7px 18px;flex:1}.allocation li{display:grid;grid-template-columns:12px 1fr auto;align-items:center;gap:8px}.allocation i{width:10px;height:10px;border-radius:3px}.trend svg{width:100%;height:auto;max-height:230px}.trend line{stroke:#c8d4e4;stroke-width:1}.trend polyline{fill:none;stroke:#2f6fed;stroke-width:4;stroke-linecap:round;stroke-linejoin:round}.trend text{font-size:13px;fill:#53657f}blockquote{margin:16px 0;padding:12px 16px;background:#f0f5fb;border-left:4px solid #4778b8}.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;margin:14px 0 24px;font-size:14px}th{background:#eaf1fa;text-align:left;position:sticky;top:0}th,td{border:1px solid #dce4ef;padding:9px 11px;white-space:nowrap}tr:nth-child(even){background:#fafcff}td:nth-last-child(-n+4){font-variant-numeric:tabular-nums}.metric{position:relative;min-width:86px;padding:2px 5px;border-radius:4px;overflow:hidden}.metric span{position:absolute;inset:0 auto 0 0;background:#cfe3fa;opacity:.75}.metric.negative span{background:#f5c7c7}.metric b{position:relative;font-weight:600}.badge{display:inline-block;padding:2px 9px;border-radius:999px;font-weight:700}.badge.high{background:#fde2e2;color:#a61b1b}.badge.medium{background:#fff1c2;color:#835d00}.badge.low,.badge.normal{background:#dff4e5;color:#176b34}hr{border:0;border-top:1px solid #dce4ef;margin:36px 0}strong{color:#9b2c2c}@media(max-width:700px){body{padding:8px}main{padding:16px}table{font-size:12px}nav{position:static}.allocation-grid{justify-content:center}.allocation ul{grid-template-columns:1fr;width:100%}}@media print{body{background:white;padding:0}main{box-shadow:none;padding:0}.metric span{opacity:.35}nav{display:none}}
"""
    css += """
.report-actions{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin-bottom:14px}.report-actions .home-link{margin-bottom:0}.action-button{color:#285c98;font-weight:700;background:white;border:1px solid #cbd9ea;padding:7px 11px;border-radius:7px;cursor:pointer}.action-button:hover{background:#edf4fc}.share-status{font-size:13px;color:#52708f}@media print{.report-actions{display:none}}
"""
    home = f'<a class="home-link" href="{escape(home_link, quote=True)}">← 返回报告中心</a>' if home_link else ""
    share_payload = (
        "请阅读以下投资研究报告，并与我讨论。请优先检查：事实与推论是否分开、数据是否一致、"
        "核心投资逻辑、五年估值假设、主要风险、可能遗漏的反方证据。不要把报告结论当作投资建议。\n\n"
        + markdown
    )
    payload_json = json.dumps(share_payload, ensure_ascii=False).replace("<", "\\u003c")
    actions = (
        '<div class="report-actions">' + home
        + '<button class="action-button" id="copy-report" type="button">复制报告全文</button>'
        + '<button class="action-button" id="discuss-chatgpt" type="button">与 ChatGPT 讨论</button>'
        + '<span class="share-status" id="share-status" aria-live="polite"></span></div>'
    )
    script = f'''<script>
const reportForDiscussion={payload_json};
const statusNode=document.getElementById("share-status");
async function copyReport(){{try{{await navigator.clipboard.writeText(reportForDiscussion);statusNode.textContent="已复制，可粘贴到对话中";return true;}}catch(error){{statusNode.textContent="复制失败，请手动复制报告";return false;}}}}
document.getElementById("copy-report").addEventListener("click",copyReport);
document.getElementById("discuss-chatgpt").addEventListener("click",async()=>{{const target=window.open("https://chatgpt.com/","_blank","noopener");const copied=await copyReport();if(!target&&copied)statusNode.textContent="已复制；请手动打开 ChatGPT 并粘贴";}});
</script>'''
    return f"<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>{escape(title)}</title><style>{css}</style></head><body><main>{actions}{''.join(body)}</main>{script}</body></html>"


def save_html_report(markdown_path: Path, title: str, latest_name: str | None = None) -> Path:
    content = markdown_path.read_text(encoding="utf-8")
    reports_root = next((parent for parent in markdown_path.parents if parent.name == "reports"), None)
    home_link = None
    company_links = {}
    if reports_root is not None:
        depth = len(markdown_path.parent.relative_to(reports_root).parts)
        prefix = "../" * depth
        home_link = prefix + "%E6%8A%A5%E5%91%8A%E4%B8%AD%E5%BF%83.html"
        generated_dir = reports_root / "generated"
        for company_path in generated_dir.glob("*-最新.html"):
            ticker = company_path.stem.removesuffix("-最新").upper()
            if markdown_path.parent == generated_dir:
                href = quote(company_path.name)
            else:
                href = prefix + "generated/" + quote(company_path.name)
            company_links[ticker] = href
    html = markdown_to_html(content, title, company_links, home_link)
    html_path = markdown_path.with_suffix(".html")
    html_path.write_text(html, encoding="utf-8")
    if latest_name:
        (markdown_path.parent / latest_name).write_text(html, encoding="utf-8")
    return html_path
