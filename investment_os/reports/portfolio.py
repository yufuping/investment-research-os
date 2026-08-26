from datetime import UTC, datetime
import json


def build_portfolio_report(rows: list[dict], alert_thresholds: dict[str, float] | None = None) -> str:
    thresholds = {
        "single_position": 20.0,
        "top_two": 45.0,
        "top_three": 60.0,
        "risk_theme": 50.0,
        **(alert_thresholds or {}),
    }
    total_value = sum(row["market_value"] for row in rows)
    total_cost = sum(row["cost_value"] for row in rows)
    lines = [
        "# 投资组合概览",
        "",
        f"> 更新时间（UTC）：{datetime.now(UTC).isoformat()}",
        "",
        "| 公司 | 股数 | 每股成本 | 当前/参考价格 | 价格来源 | 价格日期 | 当前持仓价值 | 浮动收益 | 组合权重 |",
        "|---|---:|---:|---:|---|---|---:|---:|---:|",
    ]
    for row in rows:
        gain = row["market_value"] - row["cost_value"]
        gain_pct = gain / row["cost_value"] * 100 if row["cost_value"] else 0.0
        weight = row["market_value"] / total_value * 100 if total_value else 0.0
        lines.append(
            f"| {row['ticker']} | {row['shares']:.4f} | {row['cost_per_share']:.2f} 美元 | "
            f"{row['current_price']:.2f} 美元 | {row['price_source']} | {row.get('price_date') or '日期缺失'} | "
            f"{row['market_value']:.2f} 美元 | "
            f"{gain:.2f} 美元（{gain_pct:.2f}%） | {weight:.2f}% |"
        )
    total_gain = total_value - total_cost
    total_gain_pct = total_gain / total_cost * 100 if total_cost else 0.0
    largest = max(rows, key=lambda row: row["market_value"], default=None)
    largest_weight = largest["market_value"] / total_value * 100 if largest and total_value else 0.0
    sorted_rows = sorted(rows, key=lambda row: row["market_value"], reverse=True)
    top_two_weight = sum(row["market_value"] for row in sorted_rows[:2]) / total_value * 100 if total_value else 0.0
    top_three_weight = sum(row["market_value"] for row in sorted_rows[:3]) / total_value * 100 if total_value else 0.0
    stale_rows = [row for row in rows if row.get("price_is_stale")]
    lines.extend([
        "",
        "## 汇总",
        "",
        f"- 总成本：{total_cost:.2f} 美元",
        f"- 当前持仓总价值：{total_value:.2f} 美元",
        f"- 浮动收益：{total_gain:.2f} 美元（{total_gain_pct:.2f}%）",
        f"- 最大持仓：{largest['ticker'] if largest else '无'}（{largest_weight:.2f}%）",
        f"- 前两大持仓集中度：{top_two_weight:.2f}%",
        f"- 前三大持仓集中度：{top_three_weight:.2f}%",
        f"- 过期或日期缺失的价格：{len(stale_rows)} 项",
        "",
        "> 组合权重只描述当前暴露，不代表建议仓位；现金和未录入资产不包含在内。",
    ])
    if stale_rows:
        lines.extend([
            "",
            "> **价格时效提醒：** " + "、".join(row["ticker"] for row in stale_rows)
            + " 使用的价格已过期或日期缺失，其市值、收益和组合权重只能作为参考。",
        ])
    tag_values: dict[str, float] = {}
    for row in rows:
        for tag in row.get("risk_tags", []):
            tag_values[tag] = tag_values.get(tag, 0.0) + row["market_value"]
    if tag_values:
        lines.extend([
            "",
            "## 风险主题暴露",
            "",
            "| 风险主题 | 涉及持仓 | 占核心个股组合 |",
            "|---|---|---:|",
        ])
        for tag, value in sorted(tag_values.items(), key=lambda item: item[1], reverse=True):
            members = "、".join(row["ticker"] for row in rows if tag in row.get("risk_tags", []))
            lines.append(f"| {tag} | {members} | {value / total_value * 100:.2f}% |")
        lines.extend([
            "",
            "> 风险主题可以重叠，所以各行权重之和可能超过100%；它用于识别共同驱动和相关性，不代表行业收入占比。",
        ])
    alerts: list[tuple[str, str, str]] = []
    for row in sorted_rows:
        weight = row["market_value"] / total_value * 100 if total_value else 0.0
        if weight >= thresholds["single_position"]:
            alerts.append(("高", "单一持仓", f"{row['ticker']} 权重 {weight:.2f}%，达到 {thresholds['single_position']:.2f}% 提醒线"))
    if top_two_weight >= thresholds["top_two"]:
        members = "、".join(row["ticker"] for row in sorted_rows[:2])
        alerts.append(("高", "集中度", f"前两大持仓 {members} 合计 {top_two_weight:.2f}%，达到 {thresholds['top_two']:.2f}% 提醒线"))
    if top_three_weight >= thresholds["top_three"]:
        members = "、".join(row["ticker"] for row in sorted_rows[:3])
        alerts.append(("中", "集中度", f"前三大持仓 {members} 合计 {top_three_weight:.2f}%，达到 {thresholds['top_three']:.2f}% 提醒线"))
    for tag, value in sorted(tag_values.items(), key=lambda item: item[1], reverse=True):
        exposure = value / total_value * 100 if total_value else 0.0
        if exposure >= thresholds["risk_theme"]:
            members = "、".join(row["ticker"] for row in rows if tag in row.get("risk_tags", []))
            alerts.append(("高", "共同风险", f"{tag} 暴露 {exposure:.2f}%（{members}），达到 {thresholds['risk_theme']:.2f}% 提醒线"))
    if stale_rows:
        alerts.append(("中", "数据质量", f"{len(stale_rows)} 项价格过期或日期缺失，组合权重可能失真"))
    lines.extend([
        "",
        "## 组合风险预警",
        "",
        "| 级别 | 类型 | 提醒事项 |",
        "|---|---|---|",
    ])
    if alerts:
        for level, category, message in alerts:
            lines.append(f"| {level} | {category} | {message} |")
    else:
        lines.append("| 正常 | — | 当前没有指标达到已配置的提醒线 |")
    lines.extend([
        "",
        "> 预警表示组合暴露需要复核，不等于建议立即买入或卖出；阈值是个人风险管理参数，不是普遍适用的安全标准。",
    ])
    covered_value = sum(row["market_value"] for row in rows if row.get("has_research"))
    coverage = covered_value / total_value * 100 if total_value else 0.0
    uncovered = sorted((row for row in rows if not row.get("has_research")), key=lambda row: row["market_value"], reverse=True)
    lines.extend([
        "",
        "## 研究覆盖率",
        "",
        f"- 已有完整研究覆盖：{coverage:.2f}%",
        f"- 尚未完整研究：{100 - coverage:.2f}%",
        "",
        "| 研究优先级 | 公司 | 当前组合权重 | 状态 |",
        "|---:|---|---:|---|",
    ])
    for index, row in enumerate(uncovered, start=1):
        weight = row["market_value"] / total_value * 100 if total_value else 0.0
        lines.append(f"| {index} | {row['ticker']} | {weight:.2f}% | 尚无完整研究 |")
    if not uncovered:
        lines.append("| — | — | — | 核心持仓均已有完整研究 |")
    lines.extend([
        "",
        "> 研究优先级只根据当前核心个股权重排列；高权重且缺少完整研究的公司优先补齐。",
    ])
    return "\n".join(lines)


def portfolio_snapshot_values(rows: list[dict]) -> dict:
    total_cost = sum(row["cost_value"] for row in rows)
    total_value = sum(row["market_value"] for row in rows)
    sorted_rows = sorted(rows, key=lambda row: row["market_value"], reverse=True)
    top_two_weight = sum(row["market_value"] for row in sorted_rows[:2]) / total_value * 100 if total_value else 0.0
    positions = {
        row["ticker"]: {
            "shares": row["shares"],
            "price": row["current_price"],
            "market_value": row["market_value"],
            "weight": row["market_value"] / total_value * 100 if total_value else 0.0,
        }
        for row in rows
    }
    return {
        "total_cost": total_cost,
        "total_value": total_value,
        "top_two_weight": top_two_weight,
        "positions_json": json.dumps(positions, ensure_ascii=False),
    }


def build_stress_test_report(rows: list[dict], theme: str, shock_pct: float) -> str:
    """按风险标签做静态价格冲击；不推演基本面、相关性或二阶影响。"""
    total_before = sum(row["market_value"] for row in rows)
    affected = [row for row in rows if theme in row.get("risk_tags", [])]
    affected_value = sum(row["market_value"] for row in affected)
    loss = affected_value * shock_pct / 100
    total_after = total_before + loss
    lines = [
        f"# 组合压力测试：{theme}",
        "",
        f"> 假设情景：所有带有“{theme}”标签的持仓价格同时变动 {shock_pct:+.2f}%",
        "",
        "| 公司 | 当前持仓价值 | 假设变动 | 压力后持仓价值 | 对组合影响 | 损失贡献 | 压力后权重 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in sorted(rows, key=lambda item: item["market_value"], reverse=True):
        is_affected = row in affected
        position_change = row["market_value"] * shock_pct / 100 if is_affected else 0.0
        stressed_value = row["market_value"] + position_change
        stressed_weight = stressed_value / total_after * 100 if total_after else 0.0
        loss_contribution = position_change / loss * 100 if loss < 0 and position_change < 0 else 0.0
        lines.append(
            f"| {row['ticker']} | {row['market_value']:.2f} 美元 | "
            f"{shock_pct:+.2f}%" + (" | " if is_affected else "（不适用） | ")
            + f"{stressed_value:.2f} 美元 | {position_change:+.2f} 美元 | {loss_contribution:.2f}% | {stressed_weight:.2f}% |"
        )
    portfolio_change_pct = loss / total_before * 100 if total_before else 0.0
    exposure = affected_value / total_before * 100 if total_before else 0.0
    lines.extend([
        "",
        "## 情景结果",
        "",
        f"- 受影响持仓：{'、'.join(row['ticker'] for row in affected) if affected else '无'}",
        f"- 该主题当前暴露：{exposure:.2f}%",
        f"- 组合持仓总价值：{total_before:.2f} → {total_after:.2f} 美元",
        f"- 组合影响：{loss:+.2f} 美元（{portfolio_change_pct:+.2f}%）",
        "",
        "> 这是单因素静态敏感性测试，不是市场预测。它没有考虑持仓间不同敏感度、汇率、税务、基本面变化和风险主题之间的连锁反应。",
    ])
    return "\n".join(lines)


def build_scenario_report(rows: list[dict], name: str, shocks: dict[str, float]) -> str:
    """多主题静态情景；重叠持仓采用最不利冲击，避免重复计算。"""
    total_before = sum(row["market_value"] for row in rows)
    results = []
    for row in rows:
        matches = [(tag, shocks[tag]) for tag in row.get("risk_tags", []) if tag in shocks]
        if matches:
            applied_theme, applied_shock = min(matches, key=lambda item: item[1])
            matched_themes = "、".join(f"{tag}({shock:+.1f}%)" for tag, shock in matches)
        else:
            applied_theme, applied_shock, matched_themes = "—", 0.0, "—"
        change = row["market_value"] * applied_shock / 100
        results.append({**row, "matched": matched_themes, "applied_theme": applied_theme, "shock": applied_shock, "change": change, "stressed_value": row["market_value"] + change})
    total_change = sum(item["change"] for item in results)
    total_after = total_before + total_change
    lines = [
        f"# 组合多因素情景：{name}",
        "",
        "## 情景假设",
        "",
    ]
    lines.extend(f"- {theme}：{shock:+.2f}%" for theme, shock in shocks.items())
    lines.extend([
        "",
        "| 公司 | 命中主题 | 实际采用 | 当前持仓价值 | 压力后持仓价值 | 对组合影响 | 损失贡献 |",
        "|---|---|---|---:|---:|---:|---:|",
    ])
    for item in sorted(results, key=lambda value: value["market_value"], reverse=True):
        applied = "不受影响" if item["shock"] == 0 else f"{item['applied_theme']} {item['shock']:+.2f}%"
        loss_contribution = item["change"] / total_change * 100 if total_change < 0 and item["change"] < 0 else 0.0
        lines.append(
            f"| {item['ticker']} | {item['matched']} | {applied} | {item['market_value']:.2f} 美元 | "
            f"{item['stressed_value']:.2f} 美元 | {item['change']:+.2f} 美元 | {loss_contribution:.2f}% |"
        )
    change_pct = total_change / total_before * 100 if total_before else 0.0
    lines.extend([
        "",
        "## 情景结果",
        "",
        f"- 组合持仓总价值：{total_before:.2f} → {total_after:.2f} 美元",
        f"- 组合影响：{total_change:+.2f} 美元（{change_pct:+.2f}%）",
        f"- 最大损失来源：{min(results, key=lambda item: item['change'])['ticker'] if total_change < 0 else '无'}",
        "",
        "> 同一持仓命中多个主题时采用最不利的一项，不重复相加。这仍是静态敏感性测试，不是概率预测，也未模拟风险之间的二阶影响。",
    ])
    return "\n".join(lines)


def scenario_impact(rows: list[dict], shocks: dict[str, float]) -> tuple[float, float, str]:
    total = sum(row["market_value"] for row in rows)
    changes = []
    for row in rows:
        matched = [shocks[tag] for tag in row.get("risk_tags", []) if tag in shocks]
        shock = min(matched) if matched else 0.0
        changes.append((row["ticker"], row["market_value"] * shock / 100))
    total_change = sum(change for _, change in changes)
    change_pct = total_change / total * 100 if total else 0.0
    largest = min(changes, key=lambda item: item[1])[0] if changes and total_change < 0 else "无"
    return total_change, change_pct, largest


def build_risk_suite_report(rows: list[dict], scenarios: dict[str, dict[str, float]]) -> str:
    lines = [
        "# 组合风险情景组",
        "",
        "| 情景 | 主要假设 | 组合影响 | 影响比例 | 最大损失来源 |",
        "|---|---|---:|---:|---|",
    ]
    outcomes = []
    for name, shocks in scenarios.items():
        change, change_pct, largest = scenario_impact(rows, shocks)
        assumptions = "；".join(f"{theme} {shock:+.0f}%" for theme, shock in shocks.items())
        outcomes.append((name, change, change_pct, largest))
        lines.append(f"| {name} | {assumptions} | {change:+.2f} 美元 | {change_pct:+.2f}% | {largest} |")
    worst = min(outcomes, key=lambda item: item[1]) if outcomes else None
    lines.extend([
        "",
        "## 汇总结论",
        "",
        f"- 影响最大的预设情景：{worst[0] if worst else '无'}",
        f"- 对组合持仓总价值的影响：{worst[1]:+.2f} 美元（{worst[2]:+.2f}%）" if worst else "- 暂无结果",
        "",
        "> 情景跌幅是用于风险敏感性分析的假设，不代表发生概率或目标价格。同一持仓命中多个主题时采用最不利的一项，不重复相加。",
    ])
    return "\n".join(lines)


def build_review_change_section(rows: list[dict], previous_snapshot) -> str:
    if previous_snapshot is None:
        return "## 与上次复核对比\n\n> 尚无上次复核快照；本次将作为后续比较基准。"
    current = portfolio_snapshot_values(rows)
    previous_positions = json.loads(previous_snapshot.positions_json)
    current_positions = json.loads(current["positions_json"])
    value_change = current["total_value"] - previous_snapshot.total_value
    value_change_pct = value_change / previous_snapshot.total_value * 100 if previous_snapshot.total_value else 0.0
    concentration_change = current["top_two_weight"] - previous_snapshot.top_two_weight
    changes = []
    for ticker in sorted(set(previous_positions) | set(current_positions)):
        old = previous_positions.get(ticker, {"shares": 0.0, "price": 0.0, "weight": 0.0})
        new = current_positions.get(ticker, {"shares": 0.0, "price": 0.0, "weight": 0.0})
        share_change = new["shares"] - old["shares"]
        price_change = new["price"] - old["price"]
        weight_change = new["weight"] - old.get("weight", 0.0)
        if abs(share_change) > 1e-9 or abs(price_change) > 0.005 or abs(weight_change) > 0.005:
            changes.append((ticker, share_change, price_change, weight_change))
    lines = [
        "## 与上次复核对比",
        "",
        f"- 上次复核时间（UTC）：{previous_snapshot.created_at}",
        f"- 组合持仓总价值变化：{value_change:+.2f} 美元（{value_change_pct:+.2f}%）",
        f"- 前两大集中度变化：{concentration_change:+.2f} 个百分点",
    ]
    if changes:
        lines.extend(["", "| 公司 | 股数变化 | 价格变化 | 权重变化 |", "|---|---:|---:|---:|"])
        for ticker, share_change, price_change, weight_change in changes:
            lines.append(f"| {ticker} | {share_change:+.4f} | {price_change:+.2f} 美元 | {weight_change:+.2f} 个百分点 |")
    else:
        lines.extend(["", "> 自上次复核以来，没有达到显示精度的持仓、价格或权重变化。"])
    lines.extend(["", "> 变化可能来自价格、交易或录入范围调整；不能只凭总价值变化判断投资表现。"])
    return "\n".join(lines)


def build_review_trend_section(snapshots: list) -> str:
    if not snapshots:
        return "## 历史趋势\n\n> 尚无有效历史快照。"
    lines = [
        "## 历史趋势",
        "",
        "| 复核时间（UTC） | 持仓总价值 | 前两大集中度 |",
        "|---|---:|---:|",
    ]
    for snapshot in reversed(snapshots):
        lines.append(f"| {snapshot.created_at} | {snapshot.total_value:.2f} 美元 | {snapshot.top_two_weight:.2f}% |")
    lines.extend(["", "> 仅记录发生实际数据变化的快照；持仓总价值变化同时受交易和价格影响，不等同于投资收益率。"])
    return "\n".join(lines)


def build_portfolio_review(rows: list[dict], scenarios: dict[str, dict[str, float]], alert_thresholds: dict[str, float] | None = None, previous_snapshot=None, snapshots: list | None = None) -> str:
    overview = build_portfolio_report(rows, alert_thresholds)
    risk_suite = build_risk_suite_report(rows, scenarios)
    risk_suite = risk_suite.replace("# 组合风险情景组", "## 组合风险情景组", 1)
    return "\n".join([
        "# 投资组合综合复核",
        "",
        overview.replace("# 投资组合概览", "## 投资组合概览", 1),
        "",
        "---",
        "",
        build_review_change_section(rows, previous_snapshot),
        "",
        "---",
        "",
        build_review_trend_section(snapshots or []),
        "",
        "---",
        "",
        risk_suite,
        "",
        "## 使用边界",
        "",
        "> 本报告是持仓记录、暴露识别和静态敏感性分析工具，不包含现金及未录入资产，也不构成自动买卖建议。",
    ])


def build_portfolio_history(snapshots: list) -> str:
    lines = [
        "# 投资组合历史变化",
        "",
        "| 时间（UTC） | 总成本 | 总市值 | 浮动收益 | 前两大集中度 |",
        "|---|---:|---:|---:|---:|",
    ]
    for snapshot in reversed(snapshots):
        gain = snapshot.total_value - snapshot.total_cost
        lines.append(
            f"| {snapshot.created_at} | {snapshot.total_cost:.2f} 美元 | {snapshot.total_value:.2f} 美元 | "
            f"{gain:.2f} 美元 | {snapshot.top_two_weight:.2f}% |"
        )
    if len(snapshots) >= 2:
        newest, oldest = snapshots[0], snapshots[-1]
        value_change = newest.total_value - oldest.total_value
        concentration_change = newest.top_two_weight - oldest.top_two_weight
        lines.extend([
            "",
            "## 期间变化",
            "",
            f"- 组合持仓总价值变化：{value_change:.2f} 美元",
            f"- 前两大集中度变化：{concentration_change:+.2f} 个百分点",
            "",
            "> 持仓总价值变化同时受到股价、持股数量和录入范围影响；本报告不将其自动解释为投资收益。",
        ])
        old_positions = json.loads(oldest.positions_json)
        new_positions = json.loads(newest.positions_json)
        lines.extend([
            "",
            "## 持仓变化归因",
            "",
            "| 公司 | 股数变化 | 价格变化 | 股数效应 | 价格效应 | 交互项 | 权重变化 | 主要来源 |",
            "|---|---:|---:|---:|---:|---:|---:|---|",
        ])
        for ticker in sorted(set(old_positions) | set(new_positions)):
            old = old_positions.get(ticker, {"shares": 0.0, "price": 0.0, "weight": 0.0})
            new = new_positions.get(ticker, {"shares": 0.0, "price": 0.0, "weight": 0.0})
            share_change = new["shares"] - old["shares"]
            price_change = new["price"] - old["price"]
            quantity_effect = share_change * old["price"]
            price_effect = old["shares"] * price_change
            interaction = share_change * price_change
            weight_change = new.get("weight", 0.0) - old.get("weight", 0.0)
            if abs(share_change) > 1e-9 and abs(price_change) > 1e-9:
                source = "主动调整＋价格变化"
            elif abs(share_change) > 1e-9:
                source = "主动调整"
            elif abs(price_change) > 1e-9:
                source = "市场自然漂移"
            else:
                source = "无变化"
            lines.append(
                f"| {ticker} | {share_change:+.4f} | {price_change:+.2f} 美元 | "
                f"{quantity_effect:+.2f} 美元 | {price_effect:+.2f} 美元 | {interaction:+.2f} 美元 | "
                f"{weight_change:+.2f} 个百分点 | {source} |"
            )
        lines.extend([
            "",
            "> 归因恒等式：持仓价值变化 = 股数变化×旧价格 + 旧股数×价格变化 + 股数变化×价格变化。",
        ])
    else:
        lines.extend(["", "> 当前只有一份快照；至少保存两次后才能分析变化。"])
    return "\n".join(lines)


def build_transaction_report(transactions: list) -> str:
    lines = [
        "# 组合交易流水",
        "",
        "| 时间（UTC） | 公司 | 类型 | 股数 | 成交价 | 手续费 | 已实现盈亏 | 备注 |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    total_realized = 0.0
    for item in reversed(transactions):
        transaction_name = "买入" if item.transaction_type == "buy" else "卖出"
        realized = "—" if item.realized_pnl is None else f"{item.realized_pnl:.2f} 美元"
        if item.realized_pnl is not None:
            total_realized += item.realized_pnl
        lines.append(
            f"| {item.created_at} | {item.ticker} | {transaction_name} | {item.shares:.4f} | "
            f"{item.price:.2f} 美元 | {item.fee:.2f} 美元 | {realized} | {item.note or '—'} |"
        )
    lines.extend([
        "",
        f"- 已记录卖出交易的累计已实现盈亏：{total_realized:.2f} 美元",
        "",
        "> 已实现盈亏采用移动加权平均成本计算，不包含税务批次、汇率和券商账单调整。",
    ])
    return "\n".join(lines)


def build_decision_journal(decisions: list) -> str:
    lines = ["# 投资决策日志", ""]
    for item in reversed(decisions):
        price = "未记录" if item.reference_price is None else f"{item.reference_price:.2f} 美元"
        lines.extend([
            f"## {item.created_at}｜{item.ticker}｜{item.action}",
            "",
            f"- 参考价格：{price}",
            f"- 核心理由：{item.thesis}",
            f"- 估值依据：{item.valuation_basis or '未记录'}",
            f"- 失效条件：{item.invalidation_condition or '未记录'}",
            f"- 下次检查：{item.next_check or '未记录'}",
            "",
        ])
    lines.append("> 日志记录的是当时信息和判断，后续结果不能反向改变当时的决策依据。")
    return "\n".join(lines)
