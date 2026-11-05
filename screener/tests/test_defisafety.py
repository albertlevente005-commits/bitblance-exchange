from screener import db
from screener.pipeline import Clients, fetch_all, score_all
from screener.sources import defisafety as ds

DAY = "2026-11-04"


def run(cfg, transport):
    clients = Clients(cfg, transport=transport, sleep=lambda s: None)
    conn = db.connect(cfg.db_path)
    stats = fetch_all(conn, cfg, clients, DAY)
    score_all(conn, cfg, DAY)
    return conn, clients, stats


def test_norm_name_and_matching_prefers_latest_review():
    assert ds.norm_name("AAVE V2 (Ethereum)") == "aave" and ds.norm_name("Balancer Finance V2") == "balancer"
    reviews = [ds.parse_review(i) for i in [
        {"id": 1, "title": "Solid Finance", "score": 71, "date": "2024-02-01"},
        {"id": 2, "title": "Solid Finance V2", "score": 88, "date": "2026-06-10"},
    ]]
    m = ds.match_reviews(reviews, [{"slug": "solid-finance", "name": "Solid Finance"}, {"slug": "x", "name": "Nope"}])
    assert m["solid-finance"]["id"] == 2 and "x" not in m


def test_parse_review_tolerates_shapes():
    r = ds.parse_review({"pqrId": "9", "protocolName": "Foo", "finalScore": "82%", "result": "pass", "reviewDate": "March 3, 2026"})
    assert r["id"] == 9 and r["score"] == 82.0 and r["pass"] is True and r["date"] == "2026-03-03"
    r = ds.parse_review({"id": 3, "name": "Bar", "score": 0.42})
    assert r["score"] == 42.0 and r["pass"] is False
    assert ds.parse_review({"id": 4, "title": "No score"}) is None


def test_parse_report_html():
    html = "<title>Fresh Protocol - detailed report</title><p>Process Quality Review (0.9)</p><b>Final score:</b> 64% <i>FAIL</i> Date 2026-08-15"
    r = ds.parse_report_html(html, 612)
    assert r == {"id": 612, "title": "Fresh Protocol", "score": 64.0, "pass": False, "date": "2026-08-15", "version": "0.9", "chain": None, "url": "https://defisafety.com/app/pqrs/612"}
    assert ds.parse_report_html("<html>nothing here</html>", 1) is None


def test_end_to_end_list_and_html_fallback_and_scoring(cfg, transport):
    conn, clients, stats = run(cfg, transport)
    solid = db.project_by_slug(conn, "solid-finance")
    fresh = db.project_by_slug(conn, "fresh-protocol")
    rug = db.project_by_slug(conn, "rugged-yield")
    ms = db.latest_metrics(conn, solid["id"], "defisafety", DAY)
    assert ms["pqr_score"] == 88 and ms["pqr_pass"] == 1 and ms["pqr_id"] == 415 and ms["pqr_version"] == "0.9"
    mf = db.latest_metrics(conn, fresh["id"], "defisafety", DAY)        # nincs a listában -> riportoldal az id-térképből
    assert mf["pqr_score"] == 64 and mf["pqr_pass"] == 0 and mf["pqr_url"].endswith("/612")
    mr = db.latest_metrics(conn, rug["id"], "defisafety", DAY)          # "Rugged Yield (BSC)" + 0.42 -> 42%
    assert mr["pqr_score"] == 42 and mr["pqr_pass"] == 0
    # pontozás: PQR a csapat-kategóriában, FAIL piros zászló
    d_solid = db.row_json(db.latest_score(conn, solid["id"]), "details")
    assert d_solid["team"]["defisafety_pqr"] is not None and "defisafety_fail" not in db.row_json(db.latest_score(conn, solid["id"]), "flags")
    assert "defisafety_fail" in db.row_json(db.latest_score(conn, fresh["id"]), "flags")
    assert db.row_json(db.latest_score(conn, rug["id"]), "details")["red_flags"]["penalties"]["defisafety_fail"] == 25
    # a riportoldal 7 napig cache-elve: második futás nem kéri újra
    before = len(transport.calls)
    fetch_all(conn, cfg, clients, DAY, skip_github=True, skip_details=True)
    assert not any("app/pqrs/612" in c for c in transport.calls[before:])


def test_list_endpoint_down_falls_back_to_html_only(cfg, transport):
    transport.fixtures["_ds_list"] = None
    conn, clients, stats = run(cfg, transport)
    assert stats["defisafety"] == 1
    assert db.latest_metrics(conn, db.project_by_slug(conn, "fresh-protocol")["id"], "defisafety", DAY)["pqr_score"] == 64
    assert db.latest_metrics(conn, db.project_by_slug(conn, "solid-finance")["id"], "defisafety", DAY) == {}


def test_manual_override_score_and_disabled(cfg, transport):
    cfg.data["overrides"] = {"solid-finance": {"defisafety_score": 55}}
    conn, *_ = run(cfg, transport)
    assert "defisafety_fail" in db.row_json(db.latest_score(conn, db.project_by_slug(conn, "solid-finance")["id"]), "flags")
    cfg.data["defisafety"]["enabled"] = False
    cfg.data["overrides"] = {}
    cfg.data["general"]["db_path"] = "t2.db"
    conn2, clients2, stats2 = run(cfg, transport)
    assert stats2["defisafety"] == 0 and not any("defisafety.com" in c for c in transport.calls[-30:])
