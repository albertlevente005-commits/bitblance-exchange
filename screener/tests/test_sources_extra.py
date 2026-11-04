from datetime import datetime, timezone

from screener import db
from screener.pipeline import Clients, fetch_all, score_all
from screener.sources import dune, snapshot
from screener.sources.snapshot import guess_candidates, spaces_from_governance_ids

DAY = "2026-11-04"


def run(cfg, transport):
    clients = Clients(cfg, transport=transport, sleep=lambda s: None)
    conn = db.connect(cfg.db_path)
    stats = fetch_all(conn, cfg, clients, DAY)
    score_all(conn, cfg, DAY)
    return conn, clients, stats


def test_governance_id_parsing_and_guesses():
    assert spaces_from_governance_ids(["snapshot:SolidGov.eth", "compound-governor:0x1"]) == ["solidgov.eth"]
    c = guess_candidates("fresh-protocol", "Fresh Protocol", "FRSH")
    assert "fresh-protocol.eth" in c and "freshdao.eth" in c and "frsh.eth" in c and len(c) <= 35


def test_snapshot_resolution_and_stats(cfg, transport):
    conn, clients, stats = run(cfg, transport)
    solid = db.project_by_slug(conn, "solid-finance")
    fresh = db.project_by_slug(conn, "fresh-protocol")
    rug = db.project_by_slug(conn, "rugged-yield")
    assert db.row_json(solid, "extra")["snapshot_space"] == "solidgov.eth"      # governanceID-ből
    assert db.row_json(fresh, "extra")["snapshot_space"] == "freshdao.eth"      # tippből, a 0 javaslatú .eth helyett
    assert db.row_json(rug, "extra")["snapshot_space"] is None                  # nincs space
    g = db.latest_metrics(conn, solid["id"], "snapshot", DAY)
    assert g["proposals_90d"] == 7 and g["followers"] == 12000 and g["avg_voters_90d"] > 800 and g["active_proposals"] == 1
    # a feloldás cache-elve van: második futás nem kérdez újra
    before = len(transport.calls)
    fetch_all(conn, cfg, clients, DAY, skip_github=True, skip_details=True)
    assert not any("snapshot" in c for c in transport.calls[before:])


def test_snapshot_feeds_team_score(cfg, transport):
    conn, *_ = run(cfg, transport)
    pid = db.project_by_slug(conn, "solid-finance")["id"]
    details = db.row_json(db.latest_score(conn, pid), "details")
    assert details["team"]["governance_proposals_90d"] == 100.0
    assert details["team"]["governance_voters_avg"] is not None
    cfg.data["snapshot"]["enabled"] = False
    conn2_cfg = cfg
    conn2_cfg.data["general"]["db_path"] = "t2.db"
    conn2, *_ = run(conn2_cfg, transport)
    pid2 = db.project_by_slug(conn2, "solid-finance")["id"]
    assert db.row_json(db.latest_score(conn2, pid2), "details")["team"]["governance_proposals_90d"] is None


def test_dune_metrics_matched_and_used(cfg, transport):
    conn, clients, stats = run(cfg, transport)
    solid = db.project_by_slug(conn, "solid-finance")
    fresh = db.project_by_slug(conn, "fresh-protocol")
    m = db.latest_metrics(conn, solid["id"], "dune", DAY)
    assert m["users_30d"] == 180000 and m["whale_share"] == 0.31
    assert db.row_json(solid, "extra")["dune_query_id"] == 424242
    # Fresh: DefiLlama-nál van users_24h, Dune-nál users_30d is -> a 24h-s marad az elsődleges
    details = db.row_json(db.latest_score(conn, fresh["id"]), "details")
    assert "users_24h" in details["usage"] and details["usage"]["revenue_30d"] is not None
    # Rugged: nincs Dune-sor -> nincs revenue mutató
    rug = db.project_by_slug(conn, "rugged-yield")
    assert db.row_json(db.latest_score(conn, rug["id"]), "details")["usage"]["revenue_30d"] is None
    assert any("api.dune.com" in c for c in transport.calls)


def test_dune_skipped_without_key_or_disabled(cfg, transport):
    cfg.secrets.dune_api_key = ""
    conn, clients, stats = run(cfg, transport)
    assert stats["dune"] == 0 and not any("api.dune.com" in c for c in transport.calls)


def test_dune_execute_when_stale(cfg, transport):
    transport.fixtures["_dune_results"]["execution_ended_at"] = "2026-01-01T00:00:00Z"
    sleeps = []
    rows = dune.execute_and_wait(Clients(cfg, transport=transport, sleep=sleeps.append).dune, "k", 424242, sleep=sleeps.append)
    assert len(rows) == 3 and any(c.startswith("POST") and c.endswith("/execute") for c in transport.calls)
    index = {"slug": {"solid-finance": "solid-finance"}}
    out = dune.collect(Clients(cfg, transport=transport, sleep=sleeps.append).dune, "k", cfg.data["dune"]["queries"], index, max_age_hours=1, execute_if_stale=True, sleep=sleeps.append)
    assert out["solid-finance"]["users_30d"] == 180000


def test_space_stats_handles_missing_space(cfg, transport):
    http = Clients(cfg, transport=transport, sleep=lambda s: None).snapshot
    assert snapshot.space_stats(http, "nope.eth", now=datetime(2026, 11, 4, tzinfo=timezone.utc)) is None
    s = snapshot.space_stats(http, "freshdao.eth", now=datetime(2026, 11, 4, tzinfo=timezone.utc))
    assert s["proposals_90d"] == 1 and s["last_proposal_days"] == 20 and s["avg_voters_90d"] == 25
