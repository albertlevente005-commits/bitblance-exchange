"""DefiLlama: TVL, díjak, bevétel, felhasználók, unlockok, hackek, hozamok."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ..http import Http

log = logging.getLogger(__name__)

API = "https://api.llama.fi"
YIELDS = "https://yields.llama.fi"


def _ts_to_day(ts: Any) -> str | None:
    try:
        return datetime.fromtimestamp(int(float(ts)), tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # NaN kiszűrése


def _parse_audits(v: Any) -> int | None:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def fetch_protocols(http: Http) -> list[dict[str, Any]]:
    """Normalizált protokoll-lista a /protocols végpontról."""
    raw = http.get_json(f"{API}/protocols") or []
    out = []
    for p in raw:
        slug = p.get("slug") or (p.get("name") or "").lower().replace(" ", "-")
        if not slug:
            continue
        gh = p.get("github")
        if isinstance(gh, str):
            gh = [gh]
        gov = p.get("governanceID")
        if isinstance(gov, str):
            gov = [gov]
        out.append(
            {
                "slug": slug,
                "llama_id": str(p.get("id")) if p.get("id") is not None else None,
                "name": p.get("name") or slug,
                "symbol": (p.get("symbol") or "").upper() or None if p.get("symbol") not in (None, "-") else None,
                "gecko_id": p.get("gecko_id") or None,
                "category": p.get("category"),
                "chains": p.get("chains") or [],
                "url": p.get("url"),
                "twitter": p.get("twitter"),
                "github": gh or [],
                "governance": gov or [],
                "listed_at": _ts_to_day(p.get("listedAt")) if p.get("listedAt") else None,
                "audits": _parse_audits(p.get("audits")),
                "audit_links": p.get("audit_links") or [],
                "tvl": _num(p.get("tvl")),
                "tvl_change_1d": _num(p.get("change_1d")),
                "tvl_change_7d": _num(p.get("change_7d")),
                "mcap": _num(p.get("mcap")),
                "parent": (p.get("parentProtocol") or None),
            }
        )
    return out


def _overview(http: Http, data_type: str | None) -> dict[str, dict[str, Any]]:
    params = {"excludeTotalDataChart": "true", "excludeTotalDataChartBreakdown": "true"}
    if data_type:
        params["dataType"] = data_type
    raw = http.try_get_json(f"{API}/overview/fees", params=params) or {}
    out: dict[str, dict[str, Any]] = {}
    for p in raw.get("protocols", []) or []:
        rec = {
            "total24h": _num(p.get("total24h")),
            "total7d": _num(p.get("total7d")),
            "total30d": _num(p.get("total30d")),
            "change_1m": _num(p.get("change_1m")),
        }
        for key in (p.get("defillamaId"), p.get("slug"), p.get("module"), (p.get("name") or "").lower()):
            if key:
                out.setdefault(str(key), rec)
    return out


def fetch_fees(http: Http) -> dict[str, dict[str, Any]]:
    """Díjbevétel: kulcs = defillamaId / slug / név (kisbetűs)."""
    return _overview(http, None)


def fetch_revenue(http: Http) -> dict[str, dict[str, Any]]:
    return _overview(http, "dailyRevenue")


def lookup(table: dict[str, Any], *keys: Any) -> Any | None:
    for k in keys:
        if k is None:
            continue
        v = table.get(str(k))
        if v is not None:
            return v
    return None


def fetch_active_users(http: Http) -> dict[str, dict[str, Any]]:
    """Aktív felhasználók (best-effort, nem minden protokollra van)."""
    raw = http.try_get_json(f"{API}/activeUsers") or {}
    out = {}
    if not isinstance(raw, dict):
        return out
    for pid, rec in raw.items():
        if not isinstance(rec, dict):
            continue
        users = rec.get("users") or {}
        txs = rec.get("txs") or {}
        out[str(pid)] = {
            "users_24h": _num(users.get("value")) if isinstance(users, dict) else _num(users),
            "txs_24h": _num(txs.get("value")) if isinstance(txs, dict) else _num(txs),
        }
    return out


def fetch_emissions(http: Http) -> dict[str, dict[str, Any]]:
    """Token-unlock ütemezés: kulcs = gecko_id (és token név kisbetűs)."""
    raw = http.try_get_json(f"{API}/emissions") or []
    out: dict[str, dict[str, Any]] = {}
    for e in raw if isinstance(raw, list) else []:
        nxt = e.get("nextEvent") or {}
        rec = {
            "circ_supply": _num(e.get("circSupply")),
            "max_supply": _num(e.get("maxSupply")),
            "total_locked": _num(e.get("totalLocked")),
            "next_unlock_date": _ts_to_day(nxt.get("date")) if nxt.get("date") else None,
            "next_unlock_amount": _num(nxt.get("toUnlock")),
            "unlocks_per_day": _num(e.get("unlocksPerDay")),
        }
        for key in (e.get("gecko_id"), (e.get("token") or "").lower(), (e.get("name") or "").lower()):
            if key:
                out.setdefault(str(key), rec)
    return out


def fetch_hacks(http: Http) -> list[dict[str, Any]]:
    """Ismert exploitok listája (DefiLlama hacks, Rekt-jellegű forrás)."""
    raw = http.try_get_json(f"{API}/hacks") or []
    out = []
    for h in raw if isinstance(raw, list) else []:
        day = _ts_to_day(h.get("date"))
        if not day:
            continue
        out.append(
            {
                "name": h.get("name") or "",
                "llama_id": str(h.get("defillamaId")) if h.get("defillamaId") else None,
                "day": day,
                "amount_usd": _num(h.get("amount")),
                "technique": h.get("technique") or h.get("classification"),
            }
        )
    return out


def fetch_max_apy(http: Http, min_pool_tvl: float) -> dict[str, float]:
    """Projektenként a legmagasabb APY (csak értelmes méretű poolok)."""
    raw = http.try_get_json(f"{YIELDS}/pools") or {}
    out: dict[str, float] = {}
    for pool in raw.get("data", []) if isinstance(raw, dict) else []:
        apy, tvl, proj = _num(pool.get("apy")), _num(pool.get("tvlUsd")), pool.get("project")
        if not proj or apy is None or tvl is None or tvl < min_pool_tvl:
            continue
        out[proj] = max(out.get(proj, 0.0), apy)
    return out


def fetch_tvl_change_30d(http: Http, slug: str) -> float | None:
    """30 napos TVL-változás %-ban a /protocol/{slug} történetből."""
    raw = http.try_get_json(f"{API}/protocol/{slug}")
    if not raw:
        return None
    hist = raw.get("tvl") or []
    if len(hist) < 2:
        return None
    try:
        last_ts = int(hist[-1]["date"])
        last = float(hist[-1]["totalLiquidityUSD"])
    except (KeyError, TypeError, ValueError):
        return None
    target = last_ts - 30 * 86400
    base = None
    for pt in hist:
        try:
            if int(pt["date"]) >= target:
                base = float(pt["totalLiquidityUSD"])
                break
        except (KeyError, TypeError, ValueError):
            continue
    if base is None or base <= 0:
        return None
    return (last / base - 1.0) * 100.0
