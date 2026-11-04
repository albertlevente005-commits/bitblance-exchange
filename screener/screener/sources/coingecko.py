"""CoinGecko: ár, forgalom, kapitalizáció, kínálat, fejlesztői adatok, tőzsdék."""
from __future__ import annotations

import logging
import re
from typing import Any, Iterable

from ..http import Http

log = logging.getLogger(__name__)

API = "https://api.coingecko.com/api/v3"


def _headers(api_key: str) -> dict:
    return {"x-cg-demo-api-key": api_key} if api_key else {}


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def chunked(items: list, n: int) -> Iterable[list]:
    for i in range(0, len(items), n):
        yield items[i : i + n]


def fetch_markets(http: Http, gecko_ids: list[str], api_key: str = "") -> dict[str, dict[str, Any]]:
    """Piaci adatok tömegesen (250/kérés). Kulcs: gecko_id."""
    out: dict[str, dict[str, Any]] = {}
    for chunk in chunked(sorted(set(i for i in gecko_ids if i)), 250):
        raw = http.try_get_json(
            f"{API}/coins/markets",
            params={
                "vs_currency": "usd",
                "ids": ",".join(chunk),
                "per_page": 250,
                "page": 1,
                "sparkline": "false",
                "price_change_percentage": "7d,30d",
            },
            headers=_headers(api_key),
        )
        for c in raw or []:
            out[c["id"]] = {
                "price": _num(c.get("current_price")),
                "mcap": _num(c.get("market_cap")),
                "fdv": _num(c.get("fully_diluted_valuation")),
                "volume_24h": _num(c.get("total_volume")),
                "circ_supply": _num(c.get("circulating_supply")),
                "total_supply": _num(c.get("total_supply")),
                "max_supply": _num(c.get("max_supply")),
                "price_change_7d": _num(c.get("price_change_percentage_7d_in_currency")),
                "price_change_30d": _num(c.get("price_change_percentage_30d_in_currency")),
                "symbol": (c.get("symbol") or "").upper() or None,
            }
    return out


_GH_RE = re.compile(r"github\.com/([A-Za-z0-9_.-]+)(?:/([A-Za-z0-9_.-]+))?")


def parse_github_urls(urls: Iterable[str]) -> list[str]:
    """GitHub URL-ekből 'owner' vagy 'owner/repo' alak."""
    out: list[str] = []
    for u in urls or []:
        m = _GH_RE.search(u or "")
        if not m:
            continue
        owner, repo = m.group(1), m.group(2)
        if repo:
            repo = repo.removesuffix(".git")
            val = f"{owner}/{repo}"
        else:
            val = owner
        if val not in out:
            out.append(val)
    return out


def fetch_coin_detail(http: Http, gecko_id: str, api_key: str = "") -> dict[str, Any] | None:
    """Részletek: repók, fejlesztői metrikák, tőzsdeszám, spread, genezis."""
    raw = http.try_get_json(
        f"{API}/coins/{gecko_id}",
        params={
            "localization": "false",
            "tickers": "true",
            "market_data": "false",
            "community_data": "false",
            "developer_data": "true",
            "sparkline": "false",
        },
        headers=_headers(api_key),
    )
    if not raw:
        return None
    links = raw.get("links") or {}
    repos = (links.get("repos_url") or {}).get("github") or []
    dev = raw.get("developer_data") or {}
    tickers = raw.get("tickers") or []
    exchanges = {t.get("market", {}).get("identifier") for t in tickers if t.get("market")}
    exchanges.discard(None)
    spreads = [_num(t.get("bid_ask_spread_percentage")) for t in tickers[:20]]
    spreads = [s for s in spreads if s is not None]
    green = [t for t in tickers if t.get("trust_score") == "green"]
    return {
        "github": parse_github_urls(repos),
        "homepage": next((h for h in (links.get("homepage") or []) if h), None),
        "genesis_date": raw.get("genesis_date"),
        "categories": raw.get("categories") or [],
        "exchanges": len(exchanges),
        "trusted_tickers": len(green),
        "avg_spread_pct": (sum(spreads) / len(spreads)) if spreads else None,
        "cg_stars": _num(dev.get("stars")),
        "cg_commits_4w": _num(dev.get("commit_count_4_weeks")),
        "cg_contributors": _num(dev.get("pull_request_contributors")),
    }
