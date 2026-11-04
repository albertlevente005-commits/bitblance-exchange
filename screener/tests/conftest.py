"""Közös tesztsegédek: hamis HTTP-transport rögzített API-válaszokkal."""
from __future__ import annotations

import json as _json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from screener.config import Config, DEFAULTS, _merge

FIX = Path(__file__).parent / "fixtures"
TODAY = date(2026, 11, 4)


def ts(days_ago: int) -> int:
    return int((datetime(2026, 11, 4, tzinfo=timezone.utc) - timedelta(days=days_ago)).timestamp())


def iso(days_ago: int) -> str:
    return (datetime(2026, 11, 4, tzinfo=timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_fixtures() -> dict[str, object]:
    """Három projekt: egy egészséges, egy frissen listázott, egy problémás (hack, extrém APY)."""
    protocols = [
        {"id": "1", "name": "Solid Finance", "slug": "solid-finance", "symbol": "SOL1", "gecko_id": "solid-finance", "category": "Lending",
         "chains": ["Ethereum", "Arbitrum"], "url": "https://solid.example", "twitter": "solidfi", "github": ["solid-finance"],
         "governanceID": ["snapshot:solidgov.eth", "compound-governor:0xabc"],
         "listedAt": ts(900), "audits": "3", "audit_links": ["https://audit.example/solid"], "tvl": 800_000_000, "change_1d": 0.5, "change_7d": 4.0, "mcap": 500_000_000},
        {"id": "2", "name": "Fresh Protocol", "slug": "fresh-protocol", "symbol": "FRSH", "gecko_id": "fresh-protocol", "category": "Dexes",
         "chains": ["Base"], "url": "https://fresh.example", "github": ["fresh-labs/core"], "listedAt": ts(12), "audits": "1", "audit_links": [],
         "tvl": 9_000_000, "change_1d": 3.0, "change_7d": 25.0, "mcap": 30_000_000},
        {"id": "3", "name": "Rugged Yield", "slug": "rugged-yield", "symbol": "RUG", "gecko_id": "rugged-yield", "category": "Yield",
         "chains": ["BSC"], "url": "https://rug.example", "github": [], "listedAt": ts(200), "audits": "0", "audit_links": [],
         "tvl": 3_000_000, "change_1d": -18.0, "change_7d": -45.0, "mcap": 1_500_000},
        {"id": "4", "name": "Big CEX", "slug": "big-cex", "symbol": "CEX", "gecko_id": "big-cex", "category": "CEX", "chains": ["Multi"],
         "tvl": 50_000_000_000, "change_1d": 0, "change_7d": 0},
        {"id": "5", "name": "Tiny Old", "slug": "tiny-old", "symbol": "TNY", "gecko_id": None, "category": "Dexes", "chains": ["Fantom"],
         "listedAt": ts(700), "tvl": 50_000, "change_1d": 0, "change_7d": 0},
    ]
    fees = {"protocols": [
        {"defillamaId": "1", "name": "Solid Finance", "slug": "solid-finance", "total24h": 150_000, "total7d": 1_000_000, "total30d": 4_200_000, "change_1m": 12.0},
        {"defillamaId": "2", "name": "Fresh Protocol", "slug": "fresh-protocol", "total24h": 20_000, "total7d": 120_000, "total30d": 400_000, "change_1m": 80.0},
        {"defillamaId": "3", "name": "Rugged Yield", "slug": "rugged-yield", "total24h": 500, "total7d": 4_000, "total30d": 30_000, "change_1m": -60.0},
    ]}
    revenue = {"protocols": [{"defillamaId": "1", "name": "Solid Finance", "slug": "solid-finance", "total30d": 2_000_000}]}
    users = {"1": {"users": {"value": 25_000, "end": ts(0)}, "txs": {"value": 90_000}}, "2": {"users": {"value": 1_800}, "txs": {"value": 5_000}}}
    emissions = [
        {"token": "SOL1", "name": "Solid Finance", "gecko_id": "solid-finance", "circSupply": 400_000_000, "maxSupply": 1_000_000_000,
         "nextEvent": {"date": ts(-45), "toUnlock": 3_000_000}, "unlocksPerDay": 120_000},
        {"token": "FRSH", "name": "Fresh Protocol", "gecko_id": "fresh-protocol", "circSupply": 100_000_000, "maxSupply": 1_000_000_000,
         "nextEvent": {"date": ts(-7), "toUnlock": 20_000_000}, "unlocksPerDay": 500_000},
    ]
    hacks = [{"name": "Rugged Yield", "defillamaId": "3", "date": ts(120), "amount": 2_500_000, "technique": "Private key compromise"}]
    yields_ = {"data": [
        {"project": "rugged-yield", "apy": 640.0, "tvlUsd": 1_200_000, "symbol": "RUG-BNB"},
        {"project": "solid-finance", "apy": 6.5, "tvlUsd": 300_000_000, "symbol": "USDC"},
        {"project": "rugged-yield", "apy": 9999.0, "tvlUsd": 5_000, "symbol": "DUST"},
    ]}

    def tvl_hist(end_value: float, start_value: float):
        return {"tvl": [{"date": ts(d), "totalLiquidityUSD": start_value + (end_value - start_value) * (60 - d) / 60} for d in range(60, -1, -1)]}

    markets = [
        {"id": "solid-finance", "symbol": "sol1", "current_price": 1.25, "market_cap": 500_000_000, "fully_diluted_valuation": 1_250_000_000,
         "total_volume": 40_000_000, "circulating_supply": 400_000_000, "total_supply": 1_000_000_000, "max_supply": 1_000_000_000,
         "price_change_percentage_7d_in_currency": 2.0, "price_change_percentage_30d_in_currency": 8.0},
        {"id": "fresh-protocol", "symbol": "frsh", "current_price": 0.30, "market_cap": 30_000_000, "fully_diluted_valuation": 300_000_000,
         "total_volume": 6_000_000, "circulating_supply": 100_000_000, "total_supply": 1_000_000_000, "max_supply": 1_000_000_000,
         "price_change_percentage_7d_in_currency": 15.0, "price_change_percentage_30d_in_currency": 40.0},
        {"id": "rugged-yield", "symbol": "rug", "current_price": 0.015, "market_cap": 1_500_000, "fully_diluted_valuation": 15_000_000,
         "total_volume": 4_000_000, "circulating_supply": 100_000_000, "total_supply": 1_000_000_000, "max_supply": None,
         "price_change_percentage_7d_in_currency": 30.0, "price_change_percentage_30d_in_currency": 120.0},
    ]

    def detail(gid, repos, exchanges, spread):
        tickers = [{"market": {"identifier": f"ex{i}"}, "bid_ask_spread_percentage": spread, "trust_score": "green"} for i in range(exchanges)]
        return {"id": gid, "links": {"homepage": ["https://x.example"], "repos_url": {"github": repos}}, "genesis_date": "2022-01-01",
                "categories": ["DeFi"], "tickers": tickers, "developer_data": {"stars": 1200, "commit_count_4_weeks": 40, "pull_request_contributors": 9}}

    def commits(n, authors):
        return [{"sha": str(i), "author": {"login": authors[i % len(authors)]}, "commit": {"author": {"email": "x@y"}}} for i in range(n)]

    dune_rows = [
        {"protocol": "solid-finance", "active_users_30d": 180_000, "revenue_usd_30d": 2_100_000, "tx_count_30d": 950_000, "whale_share": 0.31},
        {"protocol": "fresh-protocol", "active_users_30d": 4_200, "revenue_usd_30d": 90_000, "tx_count_30d": 20_000, "whale_share": 0.7},
        {"protocol": "unknown-thing", "active_users_30d": 1, "revenue_usd_30d": 1, "tx_count_30d": 1, "whale_share": 0},
    ]
    dune_results = {"execution_id": "01X", "state": "QUERY_STATE_COMPLETED", "execution_ended_at": iso(5), "result": {"rows": dune_rows}}

    snapshot_spaces = {
        "solidgov.eth": {"id": "solidgov.eth", "name": "Solid Governance", "followersCount": 12_000, "proposalsCount": 140, "verified": True},
        "fresh-protocol.eth": {"id": "fresh-protocol.eth", "name": "Fresh", "followersCount": 300, "proposalsCount": 0, "verified": False},
        "freshdao.eth": {"id": "freshdao.eth", "name": "Fresh DAO", "followersCount": 900, "proposalsCount": 6, "verified": False},
    }
    snapshot_proposals = {
        "solidgov.eth": [{"id": f"p{i}", "title": f"SIP-{i}", "state": "closed" if i else "active", "created": ts(5 + i * 12), "end": ts(0), "votes": 800 + 50 * i, "scores_total": 1e6} for i in range(7)],
        "freshdao.eth": [{"id": "f1", "title": "FP-1", "state": "closed", "created": ts(20), "end": ts(13), "votes": 25, "scores_total": 1000}],
    }

    fx = {
        "_dune_results": dune_results,
        "_snapshot_spaces": snapshot_spaces,
        "_snapshot_proposals": snapshot_proposals,
        "https://api.llama.fi/protocols": protocols,
        "https://api.llama.fi/overview/fees": fees,
        "https://api.llama.fi/overview/fees?dataType=dailyRevenue": revenue,
        "https://api.llama.fi/activeUsers": users,
        "https://api.llama.fi/emissions": emissions,
        "https://api.llama.fi/hacks": hacks,
        "https://yields.llama.fi/pools": yields_,
        "https://api.llama.fi/protocol/solid-finance": tvl_hist(800_000_000, 700_000_000),
        "https://api.llama.fi/protocol/fresh-protocol": tvl_hist(9_000_000, 2_000_000),
        "https://api.llama.fi/protocol/rugged-yield": tvl_hist(3_000_000, 10_000_000),
        "https://api.coingecko.com/api/v3/coins/markets": markets,
        "https://api.coingecko.com/api/v3/coins/solid-finance": detail("solid-finance", ["https://github.com/solid-finance/contracts"], 14, 0.2),
        "https://api.coingecko.com/api/v3/coins/fresh-protocol": detail("fresh-protocol", ["https://github.com/fresh-labs/core"], 3, 0.8),
        "https://api.coingecko.com/api/v3/coins/rugged-yield": detail("rugged-yield", [], 1, 3.5),
        "https://api.github.com/orgs/solid-finance/repos": [{"full_name": "solid-finance/contracts", "fork": False, "archived": False}, {"full_name": "solid-finance/app", "fork": False, "archived": False}],
        "https://api.github.com/repos/solid-finance/contracts": {"stargazers_count": 900, "archived": False, "pushed_at": iso(1)},
        "https://api.github.com/repos/solid-finance/contracts/commits": commits(85, ["a", "b", "c", "d", "e", "f"]),
        "https://api.github.com/repos/solid-finance/contracts/releases": [{"published_at": iso(10)}, {"published_at": iso(50)}, {"published_at": iso(200)}],
        "https://api.github.com/repos/solid-finance/contracts/contributors": [{"login": f"u{i}"} for i in range(40)],
        "https://api.github.com/repos/solid-finance/app": {"stargazers_count": 300, "archived": False, "pushed_at": iso(3)},
        "https://api.github.com/repos/solid-finance/app/commits": commits(60, ["a", "g", "h"]),
        "https://api.github.com/repos/solid-finance/app/releases": [],
        "https://api.github.com/repos/solid-finance/app/contributors": [{"login": f"u{i}"} for i in range(12)],
        "https://api.github.com/repos/fresh-labs/core": {"stargazers_count": 40, "archived": False, "pushed_at": iso(150)},
        "https://api.github.com/repos/fresh-labs/core/commits": [],
        "https://api.github.com/repos/fresh-labs/core/releases": [],
        "https://api.github.com/repos/fresh-labs/core/contributors": [{"login": "solo"}],
    }
    return fx


class FakeTransport:
    """URL (+ opcionális dataType) alapján adja vissza a fixture-t; számolja a hívásokat."""

    def __init__(self, fixtures: dict[str, object]):
        self.fixtures = fixtures
        self.calls: list[str] = []
        self.sent: list[dict] = []

    def __call__(self, url: str, params: dict | None, headers: dict | None, method: str = "GET", json: dict | None = None):
        self.calls.append(url if method == "GET" else f"{method} {url}")
        if url.startswith("https://api.telegram.org/"):
            self.sent.append(params or {})
            return 200, {"ok": True}, {}
        if url == "https://hub.snapshot.org/graphql":
            return self._snapshot(json or {})
        if url.startswith("https://api.dune.com/"):
            if not (headers or {}).get("X-Dune-API-Key"):
                return 401, {"error": "missing key"}, {}
            if url.endswith("/execute"):
                return 200, {"execution_id": "01X", "state": "QUERY_STATE_PENDING"}, {}
            return 200, self.fixtures["_dune_results"], {}
        key = url
        if params and params.get("dataType"):
            key = f"{url}?dataType={params['dataType']}"
        if key in self.fixtures:
            body = self.fixtures[key]
            if "commits" in url and params and int(params.get("page", 1)) > 1:
                body = []
            return 200, _json.loads(_json.dumps(body)), {}
        return 404, {"message": "not found"}, {}

    def _snapshot(self, body: dict):
        q, v = body.get("query", ""), body.get("variables", {})
        spaces, props = self.fixtures["_snapshot_spaces"], self.fixtures["_snapshot_proposals"]
        if "spaces(" in q:
            return 200, {"data": {"spaces": [spaces[i] for i in v.get("ids", []) if i in spaces]}}, {}
        if "proposals(" in q:
            items = [p for p in props.get(v.get("space"), []) if p["created"] > int(v.get("since", 0))]
            return 200, {"data": {"proposals": items}}, {}
        return 200, {"errors": [{"message": "unknown query"}]}, {}


@pytest.fixture
def fixtures():
    return build_fixtures()


@pytest.fixture
def transport(fixtures):
    return FakeTransport(fixtures)


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.delenv("SCREENER_DB_PATH", raising=False)
    monkeypatch.delenv("SCREENER_OUT_DIR", raising=False)
    data = _merge(DEFAULTS, {
        "general": {"db_path": "t.db", "out_dir": "out", "defillama_min_interval": 0, "coingecko_min_interval": 0, "github_min_interval": 0},
        "universe": {"min_tvl_usd": 2_000_000, "exclude_categories": ["CEX"], "early_days": 60, "coingecko_details_limit": 10, "github_projects_limit": 10},
        "web": {"scheduler": False, "run_at": "06:00", "send_telegram": True},
        "snapshot": {"enabled": True, "projects_limit": 50, "window_days": 90, "min_interval": 0},
        "dune": {"enabled": True, "max_age_hours": 36, "execute_if_stale": False, "queries": [
            {"id": 424242, "match_by": "slug", "match_column": "protocol",
             "metrics": {"users_30d": "active_users_30d", "revenue_30d": "revenue_usd_30d", "txs_30d": "tx_count_30d", "whale_share": "whale_share"}},
        ]},
    })
    cfg = Config(data=data, base_dir=tmp_path)
    cfg.secrets.dune_api_key = "dune-test-key"
    return cfg
