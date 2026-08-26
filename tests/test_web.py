from investment_os.app.web import create_app, resolve_ticker


class FakeTaskManager:
    def __init__(self):
        self.started = None
    def snapshot(self):
        return {"status": "idle", "ticker": None, "message": "空闲", "report_url": None}
    def start(self, ticker, question):
        self.started = (ticker, question)
        return True
    def start_daily_update(self):
        self.started = ("daily_update", None)
        return True


def client():
    app = create_app({"TESTING": True, "SECRET_KEY": "test", "WEB_USERNAME": "jeff", "WEB_PASSWORD": "secret"})
    fake = FakeTaskManager()
    app.extensions["task_manager"] = fake
    return app.test_client(), fake


def login(web):
    return web.post("/login", data={"username": "jeff", "password": "secret"})


def test_resolve_known_company_names_and_tickers():
    assert resolve_ticker("英伟达")[0] == "NVDA"
    assert resolve_ticker("amazon")[0] == "AMZN"
    assert resolve_ticker("tsm")[0] == "TSM"
    assert resolve_ticker("Cerebras")[0] == "CBRS"


def test_login_required_and_valid_login():
    web, _ = client()
    assert web.get("/").status_code == 302
    response = login(web)
    assert response.status_code == 302
    assert web.get("/").status_code == 200
    assert "生成公司研究报告" in web.get("/").get_data(as_text=True)


def test_research_requires_cost_confirmation_then_starts():
    web, fake = client()
    login(web)
    confirmation = web.post("/research/resolve", data={"company": "英伟达", "question": "ASIC竞争"})
    assert confirmation.status_code == 200
    assert "NVDA" in confirmation.get_data(as_text=True)
    rejected = web.post("/research/start", data={"ticker": "NVDA", "question": "ASIC竞争"})
    assert rejected.status_code == 400
    accepted = web.post("/research/start", data={"ticker": "NVDA", "question": "ASIC竞争", "confirm_cost": "yes"})
    assert accepted.status_code == 302
    assert fake.started == ("NVDA", "ASIC竞争")


def test_health_does_not_require_login():
    web, _ = client()
    assert web.get("/health").json == {"status": "ok"}


def test_local_only_mode_skips_login():
    app = create_app({"TESTING": True, "SECRET_KEY": "", "WEB_PASSWORD": "", "LOCAL_ONLY": True})
    response = app.test_client().get("/")
    assert response.status_code == 200
    assert "生成公司研究报告" in response.get_data(as_text=True)


def test_daily_update_can_be_started_from_web():
    web, fake = client()
    login(web)
    dashboard = web.get("/").get_data(as_text=True)
    assert "更新全部日常报告" in dashboard
    response = web.post("/update/daily")
    assert response.status_code == 302
    assert fake.started == ("daily_update", None)
