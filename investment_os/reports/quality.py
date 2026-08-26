from dataclasses import dataclass
import re


REQUIRED_SECTIONS = (
    "执行摘要",
    "公司与商业模式",
    "财务质量",
    "估值分析",
    "主要风险",
    "乐观/基准/悲观情景",
    "投资结论",
    "投资逻辑失效条件",
    "持续跟踪清单",
    "数据缺口",
)


@dataclass(frozen=True)
class QualityResult:
    score: int
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.errors

    def to_markdown(self) -> str:
        status = "通过" if self.passed else "未通过"
        lines = ["## 自动质量检查", "", f"- 状态：**{status}**", f"- 质量分：**{self.score}/100**"]
        if self.errors:
            lines.append("- 严重问题：" + "；".join(self.errors))
        if self.warnings:
            lines.append("- 提醒：" + "；".join(self.warnings))
        if self.passed and not self.warnings:
            lines.append("- 已检查：章节完整性、数据日期、金额单位、SEC 来源、风险传导、情景分析和估值纪律。")
        return "\n".join(lines)


def _has_heading(content: str, title: str) -> bool:
    escaped = re.escape(title).replace(r"/", r"\s*/\s*")
    pattern = rf"(?m)^#{{1,3}}\s+(?:[一二三四五六七八九十]+[、.．]\s*)?{escaped}\s*$"
    return re.search(pattern, content) is not None


def audit_report(content: str, snapshot: dict) -> QualityResult:
    """对最终正文做确定性质量检查，不使用模型主观评分。"""
    errors: list[str] = []
    warnings: list[str] = []

    missing = [section for section in REQUIRED_SECTIONS if not _has_heading(content, section)]
    if missing:
        errors.append("缺少必需章节：" + "、".join(missing))

    forbidden_time_claims = ("属于当前不可验证的未来日期", "所谓 FY2026 10-K", "不应视为已确认的一手证据")
    if any(claim in content for claim in forbidden_time_claims):
        errors.append("错误否定了运行时工具日期或 SEC 证据")

    market_cap = (snapshot.get("数据") or {}).get("市值_十亿美元")
    data = snapshot.get("数据") or {}
    periods = {
        (data.get("收入期间开始日"), data.get("收入报告期结束日")),
        (data.get("净利润期间开始日"), data.get("净利润报告期结束日")),
        (data.get("现金流期间开始日"), data.get("现金流期间结束日")),
    }
    complete_periods = {period for period in periods if None not in period}
    if len(complete_periods) > 1:
        errors.append("损益表与现金流量表期间不一致")
    if "派生" in str(data.get("经营现金流口径")) and "累计值相减" not in content:
        errors.append("单季度现金流为累计值相减派生，但报告未披露该口径")
    if "自由现金流" in content and "未规范化" not in content:
        warnings.append("自由现金流未明确区分报告口径与规范化 owner earnings")
    if isinstance(market_cap, (int, float)):
        raw_variants = {str(market_cap), f"{market_cap:g}", f"{market_cap:,}", f"{market_cap:,.3f}"}
        if any(f"{value}亿美元" in content for value in raw_variants):
            errors.append("市值的十亿美元原值被错误标成亿美元")

    if "sec.gov/Archives/edgar/data/" not in content:
        warnings.append("正文缺少 SEC 原始申报链接")
    if "传导路径" not in content or "领先指标" not in content:
        warnings.append("风险章节缺少传导路径或领先指标")
    if not all(term in content for term in ("终端市场", "公司份额", "利润率")):
        warnings.append("价值获取分析未完整区分市场、份额和利润率")
    if not all(term in content for term in ("乐观", "基准", "悲观")):
        warnings.append("三情景分析不完整")
    if "安全边际" not in content:
        warnings.append("估值结论没有明确说明安全边际")
    if "程序估值口径" not in content:
        errors.append("执行摘要缺少程序统一生成的估值口径")
    if re.search(r"[+-]\d+(?:\.\d+)?j%", content):
        errors.append("报告包含复数增长率；跨越盈亏平衡点时不得计算 CAGR")
    if not all(term in content for term in ("季度观察", "年度重估", "立即复核触发器")):
        warnings.append("持续跟踪清单未完整覆盖季度、年度和立即复核三个层级")

    score = max(0, 100 - len(errors) * 25 - len(warnings) * 5)
    return QualityResult(score=score, errors=tuple(errors), warnings=tuple(warnings))
