from investment_os.tools.sec_edgar import parse_10k_sections


def test_parse_10k_sections_extracts_business_and_risks():
    html = """
    <html><body>
    <h1>Item 1. Business</h1><p>{business}</p>
    <h1>Item 1A. Risk Factors</h1><p>{risks}</p>
    <h1>Item 1B. Unresolved Staff Comments</h1>
    </body></html>
    """.format(business="业务内容 " * 100, risks="风险内容 " * 100)
    result = parse_10k_sections(html)
    assert "业务内容" in result["业务披露节选"]
    assert "风险内容" in result["风险因素节选"]
    assert "Unresolved Staff Comments" not in result["风险因素节选"]
