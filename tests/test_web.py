from investment_os.app.web import create_app


class FakeTaskManager:
    def __init__(self):
        self.started = None
    def snapshot(self):
        return {"status": "idle", "ticker": None, "message": "空闲", "report_url": None}
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


def test_login_required_and_valid_login():
    web, _ = client()
    assert web.get("/").status_code == 302
    response = login(web)
    assert response.status_code == 302
    assert web.get("/").status_code == 200
    assert "Bigfish 投资研究后台" in web.get("/").get_data(as_text=True)
    assert "不再调用后台大模型" in web.get("/").get_data(as_text=True)


def test_health_does_not_require_login():
    web, _ = client()
    assert web.get("/health").json == {"status": "ok"}


def test_local_only_mode_skips_login():
    app = create_app({"TESTING": True, "SECRET_KEY": "", "WEB_PASSWORD": "", "LOCAL_ONLY": True})
    response = app.test_client().get("/")
    assert response.status_code == 200
    assert "Bigfish 投资研究后台" in response.get_data(as_text=True)


def test_daily_update_can_be_started_from_web():
    web, fake = client()
    login(web)
    dashboard = web.get("/").get_data(as_text=True)
    assert "备份并更新组合报告" in dashboard
    response = web.post("/update/daily")
    assert response.status_code == 302
    assert fake.started == ("daily_update", None)
