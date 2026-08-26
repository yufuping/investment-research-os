from datetime import UTC, datetime


def build_watchlist_summary(rows: list[dict]) -> str:
    lines = [
        "# 投资观察清单快速复核",
        "",
        f"> 复核时间（UTC）：{datetime.now(UTC).isoformat()}",
        "",
        "| 公司 | 当前价格 | 当前估值区间 | 上次估值区间 | 新财报 | 建议动作 |",
        "|---|---:|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['ticker']} | {row.get('price', '数据缺失')} | {row.get('current_zone', '数据不足')} | "
            f"{row.get('previous_zone', '数据不足')} | {'是' if row.get('new_filing') else '否'} | {row.get('action')} |"
        )
    full_reviews = sum(row.get("action") == "运行完整研究" for row in rows)
    valuation_reviews = sum(row.get("action") == "复核估值假设" for row in rows)
    lines.extend([
        "",
        "## 汇总",
        "",
        f"- 观察公司：{len(rows)} 家",
        f"- 需要完整研究：{full_reviews} 家",
        f"- 需要复核估值假设：{valuation_reviews} 家",
        f"- 继续观察：{len(rows) - full_reviews - valuation_reviews} 家",
        "",
        "> 本清单只负责发现变化和安排研究优先级，不提供自动买卖指令。",
    ])
    return "\n".join(lines)
