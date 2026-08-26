from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import quote


def build_report_center(reports_root: Path) -> Path:
    reports_root.mkdir(parents=True, exist_ok=True)
    html_files = [path for path in reports_root.rglob("*.html") if path.name != "报告中心.html"]
    latest = sorted((path for path in html_files if "最新" in path.stem), key=lambda path: path.name)
    history = sorted((path for path in html_files if path not in latest), key=lambda path: path.stat().st_mtime, reverse=True)[:20]

    def card(path: Path) -> str:
        relative = path.relative_to(reports_root)
        href = "/".join(quote(part) for part in relative.parts)
        updated = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        category = "投资工具" if "计算器" in path.stem else "组合报告" if "portfolio" in relative.parts else "公司研究"
        return f'<a class="card" data-category="{category}" data-search="{escape(path.stem.lower())}" href="{href}"><span>{category}</span><strong>{escape(path.stem)}</strong><small>更新：{updated}</small></a>'

    latest_cards = "".join(card(path) for path in latest) or "<p>尚无固定最新版报告。</p>"
    history_cards = "".join(card(path) for path in history) or "<p>尚无历史报告。</p>"
    content = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Investment Research OS 报告中心</title><style>
body{{font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif;background:#f4f7fb;color:#172033;margin:0;padding:30px}}main{{max-width:1050px;margin:auto}}h1{{margin-bottom:6px}}.sub{{color:#637089;margin-top:0}}.toolbar{{display:flex;gap:10px;flex-wrap:wrap;align-items:center;background:white;padding:14px;border:1px solid #dce6f2;border-radius:12px;margin:24px 0}}input{{flex:1;min-width:220px;padding:10px 12px;border:1px solid #bdcbe0;border-radius:8px;font-size:15px}}button{{border:1px solid #bdcbe0;background:#f7f9fc;padding:9px 12px;border-radius:8px;cursor:pointer}}button.active{{background:#2f6fed;color:white;border-color:#2f6fed}}#count{{color:#637089;margin-left:auto}}h2{{margin-top:34px}}details{{margin-top:36px}}summary{{font-size:22px;font-weight:700;cursor:pointer;padding:12px 0;border-bottom:2px solid #dce6f2}}details .grid{{margin-top:18px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(245px,1fr));gap:14px}}.card{{display:flex;flex-direction:column;gap:8px;padding:18px;background:white;border:1px solid #dce6f2;border-radius:12px;box-shadow:0 3px 12px #18243b10;text-decoration:none;color:inherit;transition:.15s}}.card:hover{{transform:translateY(-2px);border-color:#7da5d5;box-shadow:0 6px 18px #18243b1c}}.card span{{font-size:12px;color:#2f6fed;background:#eaf2ff;border-radius:999px;padding:3px 8px;align-self:flex-start}}.card strong{{font-size:17px}}.card small{{color:#738096}}.card.hidden{{display:none}}@media(max-width:600px){{body{{padding:14px}}#count{{width:100%;margin-left:0}}}}
</style></head><body><main><h1>Investment Research OS 报告中心</h1><p class="sub">集中打开最新组合复核、公司研究和投资工具</p><div class="toolbar"><input id="search" type="search" placeholder="搜索股票代码或报告名称"><button class="active" data-filter="全部">全部</button><button data-filter="组合报告">组合报告</button><button data-filter="公司研究">公司研究</button><button data-filter="投资工具">投资工具</button><span id="count"></span></div><h2>最新报告</h2><div class="grid">{latest_cards}</div><details id="history"><summary>历史报告（最近 {len(history)} 份）</summary><div class="grid">{history_cards}</div></details></main><script>
const cards=[...document.querySelectorAll('.card')],search=document.querySelector('#search'),count=document.querySelector('#count'),history=document.querySelector('#history');let filter='全部';function apply(){{const query=search.value.trim().toLowerCase();let visible=0;cards.forEach(card=>{{const show=(filter==='全部'||card.dataset.category===filter)&&card.dataset.search.includes(query);card.classList.toggle('hidden',!show);if(show)visible++}});if(query)history.open=true;count.textContent=`显示 ${{visible}} / ${{cards.length}} 份`}}document.querySelectorAll('button[data-filter]').forEach(button=>button.addEventListener('click',()=>{{filter=button.dataset.filter;document.querySelectorAll('button[data-filter]').forEach(item=>item.classList.toggle('active',item===button));apply()}}));search.addEventListener('input',apply);apply();
</script></body></html>"""
    path = reports_root / "报告中心.html"
    path.write_text(content, encoding="utf-8")
    return path
