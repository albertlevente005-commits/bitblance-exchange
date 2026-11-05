import os

from fastapi.testclient import TestClient

from screener import db
from screener.pipeline import Clients, fetch_all, score_all
from screener.web import create_app

DAY = "2026-11-04"


def prepared(cfg, transport):
    clients = Clients(cfg, transport=transport, sleep=lambda s: None)
    conn = db.connect(cfg.db_path)
    fetch_all(conn, cfg, clients, DAY)
    score_all(conn, cfg, DAY)
    conn.close()
    return TestClient(create_app(cfg, scheduler_enabled=False))


def test_api_endpoints(cfg, transport):
    with prepared(cfg, transport) as c:
        h = c.get("/api/health").json()
        assert h["status"] == "ok" and h["latest_day"] == DAY and h["projects"] == 3 and h["scheduler"]["enabled"] is False
        r = c.get("/api/ranking", params={"min_score": 0}).json()
        assert r["count"] == 3 and r["items"][0]["slug"] == "solid-finance"
        assert c.get("/api/ranking", params={"q": "rug"}).json()["count"] == 1
        assert c.get("/api/ranking", params={"flag": "prior_exploit"}).json()["items"][0]["slug"] == "rugged-yield"
        assert c.get("/api/ranking", params={"category": "Lending"}).json()["count"] == 1
        p = c.get("/api/projects/solid-finance").json()
        assert p["score"]["total"] > 70 and p["dev"]["commits_90d"] == 145 and len(p["snapshots"]) == 1
        assert p["governance"]["space"] == "solidgov.eth" and p["dune"]["users_30d"] == 180000
        assert p["defisafety"]["pqr_score"] == 88
        assert c.get("/api/projects/nope").status_code == 404
        assert c.get("/api/watchlist", params={"min_score": 0}).json()["items"][0]["slug"] == "fresh-protocol"
        assert "candidates" in c.get("/api/dca-candidates").json()
        assert c.get("/api/categories").json() == ["Dexes", "Lending", "Yield"]
        assert c.get("/api/days").json() == [DAY]
        assert "Kripto" in c.get("/").text and "Kripto" in c.get("/project/solid-finance").text
        assert "<table>" in c.get("/report").text


def test_admin_run_requires_token(cfg, transport, monkeypatch):
    monkeypatch.delenv("SCREENER_ADMIN_TOKEN", raising=False)
    with prepared(cfg, transport) as c:
        assert c.post("/api/run").status_code == 403
    monkeypatch.setenv("SCREENER_ADMIN_TOKEN", "s3cret")
    with prepared(cfg, transport) as c:
        assert c.post("/api/run", headers={"X-Admin-Token": "wrong"}).status_code == 401
        assert c.post("/api/run", headers={"X-Admin-Token": "s3cret"}).json()["started"] is True
