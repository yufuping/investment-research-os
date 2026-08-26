from investment_os.agents.cio import build_cio_agent
from investment_os.agents.specialists import RISK_ANALYSIS_INSTRUCTIONS, build_specialists


def test_risk_prompt_uses_general_value_driver_framework():
    assert "价值驱动反向分析" in RISK_ANALYSIS_INSTRUCTIONS
    assert "最重要的利润池、增长引擎" in RISK_ANALYSIS_INSTRUCTIONS
    assert "绕开、替代或削弱该护城河" in RISK_ANALYSIS_INSTRUCTIONS
    assert "真正的集中暴露" in RISK_ANALYSIS_INSTRUCTIONS
    assert "不得按固定风险类别排序" in RISK_ANALYSIS_INSTRUCTIONS
    assert "核心护城河失效" in RISK_ANALYSIS_INSTRUCTIONS
    assert "替代与绕行路径" in RISK_ANALYSIS_INSTRUCTIONS
    assert "主要利润池集中" in RISK_ANALYSIS_INSTRUCTIONS
    assert "不能预设它们的最终排名" in RISK_ANALYSIS_INSTRUCTIONS
    assert "对长期利润的预期损害动态排序" in RISK_ANALYSIS_INSTRUCTIONS
    assert "不得用供应商集中替代客户/需求/利润池集中" in RISK_ANALYSIS_INSTRUCTIONS
    assert "终端市场或利润池规模 × 公司长期份额 × 单位经济性/经营利润率" in RISK_ANALYSIS_INSTRUCTIONS
    assert "不能把行业增长等同于公司利润增长" in RISK_ANALYSIS_INSTRUCTIONS
    assert "最大客户是否同时具备自建" in RISK_ANALYSIS_INSTRUCTIONS
    assert "联合压力情景" in RISK_ANALYSIS_INSTRUCTIONS


def test_cio_requires_share_margin_and_joint_stress_analysis():
    instructions = str(build_cio_agent("gpt-5-mini").instructions)
    assert "市场增长、份额和利润率必须分别分析" in instructions
    assert "不得只看份额而忽略定价、成本和利润率" in instructions
    assert "悲观情景必须是联合压力测试" in instructions
    assert "不得声称当前估值合理、具有安全边际" in instructions
    assert "不能以模型知识截止时间为准" in instructions
    assert "不得仅因数据晚于模型知识截止时间" in instructions
    assert "持续跟踪清单" in instructions
    assert "季度观察" in instructions
    assert "年度重估" in instructions
    assert "立即复核触发器" in instructions
    assert "单季波动" in instructions


def test_risk_agent_requires_causal_chain_and_indicators():
    risk_agent = build_specialists("gpt-5-mini")[-1]
    instructions = str(risk_agent.instructions)
    assert "传导路径" in instructions
    assert "领先指标" in instructions
    assert "按对长期内在价值的潜在破坏程度排序" in instructions
    assert "证据状态" in instructions
    assert "失效证据" in instructions
    assert "价值获取拆解" in instructions
    assert "份额下降与利润率压缩必须作为两个独立变量" in instructions
    assert "必须调用 SEC 年报工具" in instructions
    assert any(getattr(tool, "name", "") == "get_sec_filing_context" for tool in risk_agent.tools)


def test_hybrid_model_routing():
    specialists = build_specialists("gpt-4.1-mini", risk_model="gpt-5.6-sol")
    assert [agent.model for agent in specialists] == [
        "gpt-4.1-mini",
        "gpt-4.1-mini",
        "gpt-4.1-mini",
        "gpt-5.6-sol",
    ]
    assert build_cio_agent("gpt-5.6-sol").model == "gpt-5.6-sol"


def test_specialists_trust_runtime_tool_dates():
    instructions = str(build_specialists("gpt-4.1-mini")[0].instructions)
    assert "不得以模型知识截止时间否定工具数据" in instructions
    assert "不得把不晚于工具抓取时间的数据误称为未来数据" in instructions


def test_cio_preserves_company_specific_risk_ranking():
    cio = build_cio_agent("gpt-5-mini")
    instructions = str(cio.instructions)
    assert "不得改写成通用风险清单" in instructions
    assert "主要利润池、增长引擎和核心护城河反向推导" in instructions
    assert "不得根据固定行业模板或公司名称套用预设风险" in instructions
    assert "最终顺序按长期利润的预期损害动态决定" in instructions


def test_risk_prompts_do_not_hardcode_a_company():
    combined = RISK_ANALYSIS_INSTRUCTIONS + str(build_cio_agent("gpt-5-mini").instructions)
    for company_specific_term in ("NVDA", "NVIDIA", "CUDA", "ASIC", "游戏业务"):
        assert company_specific_term not in combined
