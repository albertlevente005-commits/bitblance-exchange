import json
from datetime import date, timedelta

from screener import db
from screener.alerts import generate_alerts, store_alerts
from screener.export import dca_candidates, html_report, ranking, watchlist
from screener.pipeline import Clients, fetch_all, score_all, select_universe
from screener.sources.defillama import fetch_protocols
from screener.telegram import send_pending_alerts

DAY = "2026-11-04"


def run(cfg, transport):
    clients = Clients(cfg, transport=transport, sleep=lambda s: None)
    conn = db.connect(cfg.db_path)
    stats = fetch_all(conn, cfg, clients, DAY)
    scored = score_all(conn, cfg, DAY)
    return conn, clients, stats, scored


def test_universe_selection(cfg, transport):
    clients = Clients(cfg, transport=transport)
    protocols = fetch_protocols(clients.llama)
    slugs = {p["slug"] for p in select_universe(protocols, cfg)}
    assert slugs == {"solid-finance", "fresh-protocol", "rugged-yield"}  # CEX és a pici régi kimarad


def test_fetch_and_score_end_to_end(cfg, transport):
    conn, clients, stats, scored = run(cfg, transport)
    assert stats["projects"] == 3 and stats["markets"] == 3 and stats["hacks"] == 1
    assert stats["details"] == 3 and stats["github"] == 2
    assert stats["dune"] == 2 and stats["snapshot"] == 3 and stats["tokenterminal"] == 2 and stats["defisafety"] == 3
    assert scored == 3

    rows = {r["slug"]: r for r in ranking(conn, DAY)}
    solid, fresh, rug = rows["solid-finance"], rows["fresh-protocol"], rows["rugged-yield"]
    assert solid["score"] > fresh["score"] > rug["score"]
    assert solid["flags"] == []
    assert "prior_exploit" in rug["flags"] and "extreme_yield" in rug["flags"] and "no_audit" in rug["flags"]
    assert "dev_stalled" in fresh["flags"] and "unlock_shock" in fresh["flags"]
    # 30 napos TVL-trend a DefiLlama-történetből
    assert solid["tvl_change_30d"] is not None and solid["tvl_change_30d"] > 0
    assert rug["tvl_change_30d"] < 0
    # GitHub összesítés két repóból
    dev = db.latest_dev_stats(conn, db.project_by_slug(conn, "solid-finance")["id"])
    assert dev["commits_90d"] == 145 and dev["contributors_90d"] == 8 and dev["releases_90d"] == 2
    # a /protocol/{slug} történet csak a keretig fut, a részletek csak egyszer frissülnek
    first_calls = len(transport.calls)
    fetch_all(conn, cfg, clients, DAY)
    assert not any("coins/solid-finance" in c for c in transport.calls[first_calls:])
    assert not any("api.github.com" in c for c in transport.calls[first_calls:])


def test_alerts_dedup_and_telegram(cfg, transport):
    conn, clients, *_ = run(cfg, transport)
    alerts = generate_alerts(conn, cfg, DAY)
    kinds = {(a.kind, a.key.split(":")[1]) for a in alerts}
    assert ("unlock", "fresh-protocol") in kinds
    assert ("tvl_drop", "rugged-yield") in kinds
    assert ("dev_stalled", "fresh-protocol") in kinds
    # a friss projekt a zászlói miatt a 60-as küszöb alatt van -> nem "ígéretes"
    assert ("new_project", "fresh-protocol") not in kinds
    fresh_score = db.latest_score(conn, db.project_by_slug(conn, "fresh-protocol")["id"])["total"]
    cfg.data["alerts"]["new_project_min_score"] = fresh_score - 1
    alerts = generate_alerts(conn, cfg, DAY)
    assert ("new_project", "fresh-protocol") in {(a.kind, a.key.split(":")[1]) for a in alerts}
    assert store_alerts(conn, alerts) == len(alerts)
    assert store_alerts(conn, generate_alerts(conn, cfg, DAY)) == 0  # ugyanaz másodszor nem dupláz

    sent = send_pending_alerts(conn, clients.telegram, "tok", "123")
    assert sent == len(alerts) and transport.sent and "Fresh Protocol" in transport.sent[0]["text"]
    assert db.unsent_alerts(conn) == []
    assert send_pending_alerts(conn, clients.telegram, "", "") == 0


def test_score_jump_alert_uses_previous_day(cfg, transport):
    conn, clients, *_ = run(cfg, transport)
    pid = db.project_by_slug(conn, "solid-finance")["id"]
    prev = (date.fromisoformat(DAY) - timedelta(days=1)).isoformat()
    db.upsert_score(conn, pid, prev, {"total": 20, "usage": None, "tokenomics": None, "team": None, "liquidity": None, "red_flags": 100, "coverage": 1, "flags": [], "details": {}})
    kinds = {a.kind for a in generate_alerts(conn, cfg, DAY) if a.project_id == pid}
    assert "score_jump" in kinds


def test_watchlist_dca_and_report(cfg, transport):
    conn, *_ = run(cfg, transport)
    wl = watchlist(conn, cfg, DAY, min_score=0)
    assert [w["slug"] for w in wl] == ["fresh-protocol"]      # friss listázás, nincs kritikus zászló
    cfg.data["dca"]["min_score"] = 60
    dca = dca_candidates(conn, cfg, DAY)
    assert [c["symbol"] for c in dca["candidates"]] == ["SOL1"]  # csak a teljes szűrőn átment
    assert "nem pénzügyi tanács" in dca["disclaimer"]
    html = html_report(conn, cfg, DAY)
    assert "Solid Finance" in html and "Rugged Yield" in html and "<table>" in html


def test_tvl_30d_from_own_history_when_available(cfg, transport):
    conn, clients, *_ = run(cfg, transport)
    pid = db.project_by_slug(conn, "solid-finance")["id"]
    old = (date.fromisoformat(DAY) - timedelta(days=30)).isoformat()
    db.upsert_snapshot(conn, pid, old, {"tvl": 400_000_000})
    before = len(transport.calls)
    fetch_all(conn, cfg, clients, DAY, skip_github=True, skip_details=True)
    snap = db.latest_snapshot(conn, pid)
    assert abs(snap["tvl_change_30d"] - 100.0) < 1e-6
    assert not any("protocol/solid-finance" in c for c in transport.calls[before:])


def test_exclude_override(cfg, transport):
    cfg.data["overrides"] = {"rugged-yield": {"exclude": True}}
    conn, *_ = run(cfg, transport)
    assert "rugged-yield" not in {r["slug"] for r in ranking(conn, DAY)}
