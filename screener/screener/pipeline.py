"""Adatgyűjtés és pontozás összefűzése: fetch -> DB -> score."""
from __future__ import annotations

import logging
import sqlite3
from datetime import date, timedelta
from typing import Any

from . import db
from .config import Config
from .http import Http
from .scoring import ProjectData, score_project
from .sources import coingecko, defillama, dune, github, snapshot

log = logging.getLogger(__name__)


class Clients:
    """A három HTTP-kliens; tesztben kicserélhető transporttal."""

    def __init__(self, cfg: Config, transport=None, sleep=None):
        g = cfg["general"]
        kw: dict[str, Any] = {}
        if transport:
            kw["transport"] = transport
        if sleep:
            kw["sleep"] = sleep
        self.llama = Http("defillama", min_interval=float(g["defillama_min_interval"]), **kw)
        self.gecko = Http("coingecko", min_interval=float(g["coingecko_min_interval"]), **kw)
        self.github = Http("github", min_interval=float(g["github_min_interval"]), **kw)
        self.telegram = Http("telegram", min_interval=0.5, **kw)
        self.dune = Http("dune", min_interval=1.0, **kw)
        self.snapshot = Http("snapshot", min_interval=float((cfg.data.get("snapshot") or {}).get("min_interval", 1.0)), **kw)


def select_universe(protocols: list[dict[str, Any]], cfg: Config) -> list[dict[str, Any]]:
    u = cfg["universe"]
    excl = {c.lower() for c in u.get("exclude_categories", [])}
    always = set(u.get("always_include", []))
    early_cut = (date.today() - timedelta(days=int(u.get("early_days", 60)))).isoformat()
    min_tvl = float(u.get("min_tvl_usd", 0))

    def ok(p: dict) -> bool:
        if p["slug"] in always:
            return True
        if (p.get("category") or "").lower() in excl:
            return False
        if p.get("parent") and (p.get("tvl") or 0) < min_tvl:
            return False  # al-protokollok csak ha nagyok
        tvl = p.get("tvl") or 0
        if tvl >= min_tvl:
            return True
        # korai projekt: kisebb küszöb, de kell gecko_id (különben nem is pontozható rendesen)
        return bool(p.get("listed_at") and p["listed_at"] >= early_cut and p.get("gecko_id") and tvl >= min_tvl / 10)

    chosen = [p for p in protocols if ok(p)]
    chosen.sort(key=lambda p: p.get("tvl") or 0, reverse=True)
    top_n = int(u.get("top_n_by_tvl", 300))
    head = chosen[:top_n]
    tail = [p for p in chosen[top_n:] if p["slug"] in always or (p.get("listed_at") and p["listed_at"] >= early_cut)]
    return head + tail


def fetch_all(conn: sqlite3.Connection, cfg: Config, clients: Clients, day: str | None = None, skip_github: bool = False, skip_details: bool = False) -> dict[str, int]:
    """Minden forrás lekérése és mentése a mai pillanatképbe."""
    day = day or db.today()
    u = cfg["universe"]
    stats = {"projects": 0, "markets": 0, "details": 0, "github": 0, "hacks": 0, "dune": 0, "snapshot": 0}

    protocols = defillama.fetch_protocols(clients.llama)
    universe = select_universe(protocols, cfg)
    log.info("DefiLlama: %d protokoll, figyelt kör: %d", len(protocols), len(universe))

    fees = defillama.fetch_fees(clients.llama)
    revenue = defillama.fetch_revenue(clients.llama)
    users = defillama.fetch_active_users(clients.llama)
    emissions = defillama.fetch_emissions(clients.llama)
    apy = defillama.fetch_max_apy(clients.llama, float(cfg["scoring"].get("extreme_apy_min_pool_tvl", 100_000)))

    # hackek: slug/név/llama_id szerint
    hacks = defillama.fetch_hacks(clients.llama)
    by_id = {p["llama_id"]: p["slug"] for p in protocols if p.get("llama_id")}
    by_name = {p["name"].lower(): p["slug"] for p in protocols}
    for h in hacks:
        slug = by_id.get(h["llama_id"]) or by_name.get(h["name"].lower())
        if not slug:
            # "Name (chain)" vagy "Name v2" formák: első szó próbája
            slug = by_name.get(h["name"].split("(")[0].strip().lower())
        if slug:
            db.upsert_hack(conn, slug, h["day"], h["amount_usd"], h["technique"], "defillama")
            stats["hacks"] += 1

    ids: dict[int, dict] = {}
    for p in universe:
        pid = db.upsert_project(conn, p)
        ids[pid] = p
        if p.get("governance"):
            db.update_project_extra(conn, pid, {"governance": p["governance"]})
        f = defillama.lookup(fees, p["llama_id"], p["slug"], p["name"].lower()) or {}
        r = defillama.lookup(revenue, p["llama_id"], p["slug"], p["name"].lower()) or {}
        us = defillama.lookup(users, p["llama_id"]) or {}
        em = defillama.lookup(emissions, p["gecko_id"], (p.get("symbol") or "").lower(), p["name"].lower()) or {}
        db.upsert_snapshot(
            conn, pid, day,
            {
                "tvl": p["tvl"], "tvl_change_1d": p["tvl_change_1d"], "tvl_change_7d": p["tvl_change_7d"],
                "fees_24h": f.get("total24h"), "fees_7d": f.get("total7d"), "fees_30d": f.get("total30d"),
                "fees_change_30d": f.get("change_1m"), "revenue_30d": r.get("total30d"),
                "users_24h": us.get("users_24h"), "txs_24h": us.get("txs_24h"),
                "mcap": p.get("mcap"),
                "next_unlock_date": em.get("next_unlock_date"), "next_unlock_amount": em.get("next_unlock_amount"),
                "unlocks_per_day": em.get("unlocks_per_day"), "max_apy": apy.get(p["slug"]),
            },
        )
        stats["projects"] += 1
    conn.commit()

    # 30 napos TVL-változás: saját történetből, ha van, különben DefiLlama-történet (limitált)
    hist_budget = int(u.get("tvl_history_limit", 150))
    for pid, p in ids.items():
        old = db.snapshot_days_ago(conn, pid, 30, day)
        cur = db.latest_snapshot(conn, pid)
        if old and old["tvl"] and cur and cur["tvl"] is not None:
            db.upsert_snapshot(conn, pid, day, {"tvl_change_30d": (cur["tvl"] / old["tvl"] - 1) * 100})
        elif hist_budget > 0:
            hist_budget -= 1
            ch = defillama.fetch_tvl_change_30d(clients.llama, p["slug"])
            if ch is not None:
                db.upsert_snapshot(conn, pid, day, {"tvl_change_30d": ch})
    conn.commit()

    # CoinGecko piaci adatok
    gecko_ids = [p["gecko_id"] for p in ids.values() if p.get("gecko_id")]
    markets = coingecko.fetch_markets(clients.gecko, gecko_ids, cfg.secrets.coingecko_api_key)
    for pid, p in ids.items():
        m = markets.get(p.get("gecko_id") or "")
        if not m:
            continue
        db.upsert_snapshot(conn, pid, day, {k: v for k, v in m.items() if k != "symbol"})
        if m.get("symbol") and not p.get("symbol"):
            conn.execute("UPDATE projects SET symbol=? WHERE id=?", (m["symbol"], pid))
        stats["markets"] += 1
    conn.commit()

    # CoinGecko részletek (repók, tőzsdeszám) – korlátozott számban, elavulás szerint
    if not skip_details:
        refresh_days = int(u.get("details_refresh_days", 7))
        stale_cut = (date.fromisoformat(day) - timedelta(days=refresh_days)).isoformat()
        rows = conn.execute(
            """SELECT p.id, p.gecko_id FROM projects p JOIN snapshots s ON s.project_id=p.id AND s.day=?
               WHERE p.gecko_id IS NOT NULL AND (p.details_at IS NULL OR p.details_at < ?)
               ORDER BY (p.details_at IS NULL) DESC, s.tvl DESC LIMIT ?""",
            (day, stale_cut, int(u.get("coingecko_details_limit", 40))),
        ).fetchall()
        for row in rows:
            d = coingecko.fetch_coin_detail(clients.gecko, row["gecko_id"], cfg.secrets.coingecko_api_key)
            if not d:
                continue
            gh_from_cg = d.pop("github", [])
            db.update_project_extra(conn, row["id"], d, details_at=day)
            if gh_from_cg:
                proj = conn.execute("SELECT github FROM projects WHERE id=?", (row["id"],)).fetchone()
                existing = db.row_json(proj, "github", []) or []
                merged = existing + [g for g in gh_from_cg if g not in existing]
                conn.execute("UPDATE projects SET github=? WHERE id=?", (db._j(merged), row["id"]))
            stats["details"] += 1
            conn.commit()

    # GitHub fejlesztői aktivitás – korlátozott számban
    if not skip_github:
        refresh_days = int(u.get("details_refresh_days", 7))
        stale_cut = (date.fromisoformat(day) - timedelta(days=refresh_days)).isoformat()
        rows = conn.execute(
            """SELECT p.id, p.github FROM projects p JOIN snapshots s ON s.project_id=p.id AND s.day=?
               WHERE p.github IS NOT NULL AND p.github != '[]' AND (p.dev_at IS NULL OR p.dev_at < ?)
               ORDER BY (p.dev_at IS NULL) DESC, s.tvl DESC LIMIT ?""",
            (day, stale_cut, int(u.get("github_projects_limit", 30))),
        ).fetchall()
        for row in rows:
            refs = db.row_json(row, "github", []) or []
            ds = github.project_dev_stats(clients.github, refs, cfg.secrets.github_token, int(u.get("github_repos_per_project", 3)))
            if ds:
                db.upsert_dev_stats(conn, row["id"], day, ds)
                stats["github"] += 1
                conn.commit()

    stats["dune"] = fetch_dune(conn, cfg, clients, ids, day)
    stats["snapshot"] = fetch_snapshot(conn, cfg, clients, day)
    return stats


def fetch_dune(conn: sqlite3.Connection, cfg: Config, clients: Clients, ids: dict[int, dict], day: str) -> int:
    """Konfigurált Dune-lekérdezések eredményeinek illesztése a figyelt projektekhez."""
    dcfg = cfg.data.get("dune") or {}
    queries = list(dcfg.get("queries") or [])
    if not dcfg.get("enabled") or not queries:
        return 0
    index: dict[str, dict[str, str]] = {"slug": {}, "symbol": {}, "gecko_id": {}, "name": {}}
    slug_to_id: dict[str, int] = {}
    for pid, p in ids.items():
        slug_to_id[p["slug"]] = pid
        index["slug"][p["slug"].lower()] = p["slug"]
        if p.get("symbol"):
            index["symbol"].setdefault(p["symbol"].lower(), p["slug"])
        if p.get("gecko_id"):
            index["gecko_id"][p["gecko_id"].lower()] = p["slug"]
        index["name"][p["name"].lower()] = p["slug"]
    results = dune.collect(
        clients.dune, cfg.secrets.dune_api_key, queries, index,
        max_age_hours=float(dcfg.get("max_age_hours", 36)), execute_if_stale=bool(dcfg.get("execute_if_stale", False)),
    )
    n = 0
    for slug, metrics in results.items():
        pid = slug_to_id.get(slug)
        if pid is None:
            continue
        db.upsert_metrics(conn, pid, day, "dune", {k: v for k, v in metrics.items() if not k.startswith("_")})
        db.update_project_extra(conn, pid, {"dune_query_id": metrics.get("_query_id"), "dune_executed_at": metrics.get("_executed_at")})
        n += 1
    conn.commit()
    return n


def fetch_snapshot(conn: sqlite3.Connection, cfg: Config, clients: Clients, day: str) -> int:
    """Snapshot governance-aktivitás: space-feloldás (cache-elve) és statisztika, korlátozott számban."""
    scfg = cfg.data.get("snapshot") or {}
    if not scfg.get("enabled", True):
        return 0
    refresh_days = int(cfg["universe"].get("details_refresh_days", 7))
    stale_cut = (date.fromisoformat(day) - timedelta(days=refresh_days)).isoformat()
    recheck_cut = (date.fromisoformat(day) - timedelta(days=30)).isoformat()
    rows = conn.execute(
        """SELECT p.* FROM projects p JOIN snapshots s ON s.project_id=p.id AND s.day=?
           ORDER BY s.tvl DESC""",
        (day,),
    ).fetchall()
    limit = int(scfg.get("projects_limit", 80))
    window = int(scfg.get("window_days", 90))
    n = 0
    for row in rows:
        if n >= limit:
            break
        extra = db.row_json(row, "extra", {}) or {}
        ov = cfg.override(row["slug"])
        checked = extra.get("snapshot_checked_at") or ""
        space = ov.get("snapshot_space") or extra.get("snapshot_space")
        if space and checked >= stale_cut:
            continue  # friss adat van
        if not space and checked and checked >= recheck_cut and not ov.get("snapshot_space"):
            continue  # nemrég nem találtunk space-t, ne próbálgassuk minden nap
        if not space:
            candidates = snapshot.spaces_from_governance_ids(extra.get("governance"))
            if not candidates:
                candidates = snapshot.guess_candidates(row["slug"], row["name"], row["symbol"])
            found = snapshot.resolve_space(clients.snapshot, candidates)
            space = found["id"] if found else None
        n += 1
        if not space:
            db.update_project_extra(conn, row["id"], {"snapshot_checked_at": day, "snapshot_space": None})
            conn.commit()
            continue
        stats = snapshot.space_stats(clients.snapshot, space, days=window)
        db.update_project_extra(conn, row["id"], {"snapshot_space": space, "snapshot_checked_at": day})
        if stats:
            db.upsert_metrics(conn, row["id"], day, "snapshot", stats)
        conn.commit()
    return n


def build_project_data(conn: sqlite3.Connection, cfg: Config, project: sqlite3.Row, day: str) -> ProjectData | None:
    snap = conn.execute("SELECT * FROM snapshots WHERE project_id=? AND day=?", (project["id"], day)).fetchone()
    if snap is None:
        return None
    dev = db.latest_dev_stats(conn, project["id"])
    extra = db.row_json(project, "extra", {}) or {}
    ov = cfg.override(project["slug"])
    old_users = db.snapshot_days_ago(conn, project["id"], 30, day)
    users_change = None
    if old_users and old_users["users_24h"] and snap["users_24h"] is not None:
        users_change = (snap["users_24h"] / old_users["users_24h"] - 1) * 100
    hacks = [{"day": h["day"], "amount_usd": h["amount_usd"]} for h in db.hacks_for(conn, project["slug"])]
    dune_m = db.latest_metrics(conn, project["id"], "dune", day, max_age_days=int((cfg.data.get("dune") or {}).get("max_age_hours", 36) / 24) + 7)
    gov = db.latest_metrics(conn, project["id"], "snapshot", day, max_age_days=30)

    def num(v: Any) -> float | None:
        return v if isinstance(v, (int, float)) else None

    users_24h = snap["users_24h"] if snap["users_24h"] is not None else num(dune_m.get("users_24h"))
    revenue_30d = snap["revenue_30d"] if snap["revenue_30d"] is not None else num(dune_m.get("revenue_30d"))
    fees_30d = snap["fees_30d"] if snap["fees_30d"] is not None else num(dune_m.get("fees_30d"))
    commits = dev["commits_90d"] if dev else None
    contributors = dev["contributors_90d"] if dev else None
    last_push = dev["last_push"] if dev else None
    if dev is None and extra.get("cg_commits_4w") is not None:
        # CoinGecko fejlesztői adat, ha nincs GitHub-lekérés
        commits = int(extra["cg_commits_4w"] * 3)
        contributors = int(extra["cg_contributors"]) if extra.get("cg_contributors") is not None else None
    return ProjectData(
        slug=project["slug"], name=project["name"],
        tvl=snap["tvl"], tvl_change_7d=snap["tvl_change_7d"], tvl_change_30d=snap["tvl_change_30d"],
        fees_30d=fees_30d, fees_change_30d=snap["fees_change_30d"], revenue_30d=revenue_30d,
        users_24h=users_24h, users_30d=num(dune_m.get("users_30d")), users_change_30d=users_change,
        price_change_30d=snap["price_change_30d"],
        gov_proposals_90d=int(gov["proposals_90d"]) if num(gov.get("proposals_90d")) is not None else None,
        gov_avg_voters_90d=num(gov.get("avg_voters_90d")),
        gov_last_proposal_days=int(gov["last_proposal_days"]) if num(gov.get("last_proposal_days")) is not None else None,
        price=snap["price"], mcap=snap["mcap"], fdv=snap["fdv"], circ_supply=snap["circ_supply"],
        total_supply=snap["total_supply"], max_supply=snap["max_supply"],
        next_unlock_date=snap["next_unlock_date"], next_unlock_amount=snap["next_unlock_amount"],
        unlocks_per_day=snap["unlocks_per_day"],
        commits_90d=commits, contributors_90d=contributors, releases_90d=dev["releases_90d"] if dev else None,
        last_push=last_push, audits=project["audits"],
        volume_24h=snap["volume_24h"], exchanges=extra.get("exchanges"), avg_spread_pct=extra.get("avg_spread_pct"),
        hacks=hacks, max_apy=snap["max_apy"],
        anonymous_team=ov.get("anonymous_team"), concentrated_ownership=ov.get("concentrated_ownership"),
        audited_override=ov.get("audited"), today=date.fromisoformat(day),
    )


def score_all(conn: sqlite3.Connection, cfg: Config, day: str | None = None) -> int:
    day = day or db.today()
    n = 0
    for project in db.all_projects(conn):
        if cfg.override(project["slug"]).get("exclude"):
            continue
        pdata = build_project_data(conn, cfg, project, day)
        if pdata is None:
            continue
        s = score_project(pdata, cfg["weights"], cfg["scoring"])
        db.upsert_score(conn, project["id"], day, s.as_dict())
        n += 1
    conn.commit()
    return n
