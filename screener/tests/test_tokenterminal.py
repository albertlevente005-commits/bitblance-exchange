from datetime import date

from screener import db
from screener.pipeline import Clients, fetch_all, score_all
from screener.sources import tokenterminal as tt

DAY = "2026-11-04"


def run(cfg, transport):
    clients = Clients(cfg, transport=transport, sleep=lambda s: None)
    conn = db.connect(cfg.db_path)
    stats = fetch_all(conn, cfg, clients, DAY)
    score_all(conn, cfg, DAY)
    return conn, clients, stats


def test_match_projects_priority_and_ambiguous_symbol():
    tt_projects = [
        {"project_id": "solid-finance", "name": "Solid Finance", "symbol": "SOL1", "gecko_id": "solid-finance"},
        {"project_id": "fresh", "name": "Fresh Protocol", "symbol": "FRSH"},
        {"project_id": "a", "name": "A", "symbol": "RUG"}, {"project_id": "b", "name": "B", "symbol": "RUG"},
    ]
    ours = [
        {"slug": "solid-finance", "name": "Solid", "symbol": "X", "gecko_id": "solid-finance"},
        {"slug": "fresh-protocol", "name": "Fresh Protocol", "symbol": "FRSH"},
        {"slug": "rugged-yield", "name": "Rugged Yield", "symbol": "RUG"},
        {"slug": "manual", "name": "Manual", "symbol": "M"},
    ]
    m = tt.match_projects(tt_projects, ours, overrides={"manual": "b"})
    assert m == {"solid-finance": "solid-finance", "fresh-protocol": "fresh", "manual": "b"}  # kétértelmű szimbólum kimarad


def test_validate_metrics_drops_unknown_and_keeps_all_when_list_unavailable():
    ok = tt.validate_metrics({"fees": "fees", "users_daily": "nope_daily"}, {"fees", "user_dau"})
    assert ok == {"fees": "fees"}
    assert tt.validate_metrics({"fees": "fees"}, set()) == {"fees": "fees"}


def test_aggregate_sum_mean_last_and_change():
    end = date(2026, 11, 4)
    series = {
        "fees": [((end.fromordinal(end.toordinal() - d)).isoformat(), 100.0 if d < 30 else 50.0) for d in range(60)],
        "users_daily": [((end.fromordinal(end.toordinal() - d)).isoformat(), 10.0) for d in range(60)],
        "token_holders": [((end.fromordinal(end.toordinal() - d)).isoformat(), 1000.0 + (60 - d)) for d in range(60)],
    }
    out = tt._aggregate(series, 30, end)
    assert out["fees_30d"] == 3000.0 and abs(out["fees_change_30d"] - 100.0) < 1e-9
    assert out["users_daily_avg_30d"] == 10.0 and abs(out["users_daily_change_30d"]) < 1e-9
    assert out["token_holders"] == 1060.0 and out["token_holders_change_30d"] > 0


def test_bulk_mode_end_to_end_fills_gaps_and_feeds_scoring(cfg, transport):
    conn, clients, stats = run(cfg, transport)
    solid = db.project_by_slug(conn, "solid-finance")
    fresh = db.project_by_slug(conn, "fresh-protocol")
    rug = db.project_by_slug(conn, "rugged-yield")
    assert db.row_json(solid, "extra")["tt_project_id"] == "solid-finance"
    assert db.row_json(fresh, "extra")["tt_project_id"] == "fresh"          # név alapján
    assert db.row_json(rug, "extra")["tt_project_id"] is None               # kétértelmű szimbólum -> nincs illesztés
    m = db.latest_metrics(conn, solid["id"], "tokenterminal", DAY)
    assert abs(m["fees_30d"] - 150_000 * 1.2 * 30) < 1 and abs(m["fees_change_30d"] - 20) < 1e-6
    assert m["token_holders"] == 51_000 and m["transactions_30d"] == 90_000
    # a használat-pontszámba a DAU-trend beépül (Fresh: DefiLlama-nál nincs 30 napos felhasználói történet)
    details = db.row_json(db.latest_score(conn, fresh["id"]), "details")
    assert abs(details["usage"]["users_trend_30d"] - 90.0) < 1e-6        # +50% -> scale(-40..60) = 0.9
    assert details["usage"]["fees_30d"] is not None
    # az illesztés cache-elve: második futás nem kéri újra a projektlistát
    before = len(transport.calls)
    fetch_all(conn, cfg, clients, DAY, skip_github=True, skip_details=True)
    assert "https://api.tokenterminal.com/v2/projects" not in transport.calls[before:]


def test_per_project_mode_and_limit(cfg, transport):
    cfg.data["tokenterminal"]["mode"] = "per_project"
    cfg.data["tokenterminal"]["projects_limit"] = 1          # csak a legnagyobb TVL-ű (Solid) -> üres válasz
    conn, clients, stats = run(cfg, transport)
    assert stats["tokenterminal"] == 0
    cfg.data["tokenterminal"]["projects_limit"] = 5
    cfg.data["general"]["db_path"] = "t2.db"
    conn2, clients2, stats2 = run(cfg, transport)
    assert stats2["tokenterminal"] == 1
    fresh = db.project_by_slug(conn2, "fresh-protocol")
    m = db.latest_metrics(conn2, fresh["id"], "tokenterminal", DAY)
    assert abs(m["fees_change_30d"] - 100) < 1e-6 and abs(m["users_daily_avg_30d"] - 2250) < 1e-6


def test_disabled_or_missing_key(cfg, transport):
    cfg.secrets.tokenterminal_api_key = ""
    conn, clients, stats = run(cfg, transport)
    assert stats["tokenterminal"] == 0 and not any("tokenterminal.com" in c for c in transport.calls)
    cfg.secrets.tokenterminal_api_key = "tt-test-key"
    cfg.data["tokenterminal"]["enabled"] = False
    cfg.data["general"]["db_path"] = "t3.db"
    conn, clients, stats = run(cfg, transport)
    assert stats["tokenterminal"] == 0


def test_metric_override_unknown_is_skipped_with_warning(cfg, transport, caplog):
    cfg.data["tokenterminal"]["metrics"] = {"users_daily": "does_not_exist", "earnings": False}
    conn, clients, stats = run(cfg, transport)
    assert "does_not_exist" in caplog.text
    solid = db.project_by_slug(conn, "solid-finance")
    m = db.latest_metrics(conn, solid["id"], "tokenterminal", DAY)
    assert "users_daily_avg_30d" not in m and "fees_30d" in m
    assert not any(c.endswith("/v2/metrics/earnings") for c in transport.calls)   # earnings = false -> nincs hívás
