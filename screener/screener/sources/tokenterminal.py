"""Token Terminal: szabványosított pénzügyi és használati mutatók (díj, bevétel, DAU/MAU, tranzakciók...).

API v2 (kulcs kell, Bearer): https://tokenterminal.com/docs/api-reference
- GET /v2/projects                         projektlista (project_id, name, symbol, ...)
- GET /v2/metrics                          elérhető metrikák listája
- GET /v2/metrics/{metric_id}?project_ids=all&start_date=&end_date=   egy metrika sok projektre
- GET /v2/projects/{id}/metrics?metric_ids=&start_date=&end_date=     egy projekt több metrikája

A metrika-azonosítók a config [tokenterminal.metrics] alatt felülírhatók; futáskor a /v2/metrics
listával ellenőrizzük őket, és a hiányzókra figyelmeztetünk.
"""
from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import Any, Iterable

from ..http import Http

log = logging.getLogger(__name__)

API = "https://api.tokenterminal.com/v2"

# belső név -> Token Terminal metric_id (alapértelmezés; config-ból felülírható)
DEFAULT_METRICS: dict[str, str] = {
    "fees": "fees",
    "revenue": "revenue",
    "earnings": "earnings",
    "users_daily": "active_users_daily",
    "users_monthly": "active_users_monthly",
    "transactions": "transaction_count",
    "token_holders": "token_holders",
    "tvl": "tvl",
    "active_developers": "active_developers",
    "code_commits": "code_commits",
}
# összesítés módja a 30 napos ablakban: sum (áramlás) vagy last/mean (állomány)
AGG = {
    "fees": "sum", "revenue": "sum", "earnings": "sum", "transactions": "sum", "code_commits": "sum",
    "users_daily": "mean", "users_monthly": "last", "token_holders": "last", "tvl": "last", "active_developers": "last",
}


def _headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _rows(raw: Any) -> list[dict[str, Any]]:
    """A válasz sorai, akár {"data": [...]} akár csupasz lista."""
    if isinstance(raw, dict):
        for key in ("data", "results", "rows"):
            if isinstance(raw.get(key), list):
                return raw[key]
        return []
    return raw if isinstance(raw, list) else []


def _norm(s: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def fetch_projects(http: Http, api_key: str) -> list[dict[str, Any]]:
    raw = http.try_get_json(f"{API}/projects", headers=_headers(api_key))
    out = []
    for p in _rows(raw):
        pid = p.get("project_id") or p.get("id")
        if not pid:
            continue
        out.append({
            "project_id": str(pid),
            "name": p.get("name") or p.get("project_name") or "",
            "symbol": (p.get("symbol") or "").upper(),
            "gecko_id": p.get("coingecko_id") or p.get("gecko_id") or p.get("coingecko") or None,
            "sector": p.get("market_sector") or p.get("sector"),
        })
    return out


def fetch_metric_ids(http: Http, api_key: str) -> set[str]:
    raw = http.try_get_json(f"{API}/metrics", headers=_headers(api_key))
    ids = set()
    for m in _rows(raw):
        mid = m.get("metric_id") or m.get("id")
        if mid:
            ids.add(str(mid))
    return ids


def validate_metrics(configured: dict[str, str], available: set[str]) -> dict[str, str]:
    """Csak a létező metrika-azonosítók maradnak; a hiányzókra figyelmeztetés hasonló nevekkel."""
    if not available:
        return dict(configured)  # nem tudtuk lekérni a listát: próbáljuk úgy, ahogy van
    ok: dict[str, str] = {}
    for key, mid in configured.items():
        if mid in available:
            ok[key] = mid
        else:
            stem = re.split(r"[_-]", mid)[0]
            similar = sorted(a for a in available if stem and stem in a)[:5]
            log.warning("tokenterminal: a(z) '%s' metrika (%s) nem létezik; hasonlók: %s", mid, key, ", ".join(similar) or "-")
    return ok


def match_projects(tt_projects: list[dict[str, Any]], ours: Iterable[dict[str, Any]], overrides: dict[str, str] | None = None) -> dict[str, str]:
    """{saját slug -> Token Terminal project_id}. Sorrend: kézi, gecko_id, slug==project_id, név, egyedi szimbólum."""
    overrides = overrides or {}
    by_gecko = {p["gecko_id"].lower(): p["project_id"] for p in tt_projects if p.get("gecko_id")}
    by_id = {p["project_id"].lower(): p["project_id"] for p in tt_projects}
    by_name = {_norm(p["name"]): p["project_id"] for p in tt_projects if p.get("name")}
    sym_count: dict[str, int] = {}
    for p in tt_projects:
        if p.get("symbol"):
            sym_count[p["symbol"]] = sym_count.get(p["symbol"], 0) + 1
    by_symbol = {p["symbol"]: p["project_id"] for p in tt_projects if p.get("symbol") and sym_count[p["symbol"]] == 1}
    out: dict[str, str] = {}
    for o in ours:
        slug = o["slug"]
        tid = (
            overrides.get(slug)
            or by_gecko.get((o.get("gecko_id") or "").lower())
            or by_id.get(slug.lower())
            or by_id.get(_norm(slug))
            or by_name.get(_norm(o.get("name")))
            or by_symbol.get((o.get("symbol") or "").upper())
        )
        if tid:
            out[slug] = tid
    return out


def _aggregate(series: dict[str, list[tuple[str, float]]], window_days: int, end: date) -> dict[str, Any]:
    """Metrikánként (belső név) az ablakra összesített érték és az előző ablakhoz képesti változás %."""
    cut = (end - timedelta(days=window_days)).isoformat()
    prev_cut = (end - timedelta(days=2 * window_days)).isoformat()
    out: dict[str, Any] = {}
    for key, points in series.items():
        points = sorted(points)
        cur = [v for d, v in points if d > cut]
        prev = [v for d, v in points if prev_cut < d <= cut]
        agg = AGG.get(key, "last")
        if not cur:
            continue
        if agg == "sum":
            cur_v, prev_v = sum(cur), (sum(prev) if prev else None)
        elif agg == "mean":
            cur_v, prev_v = sum(cur) / len(cur), (sum(prev) / len(prev) if prev else None)
        else:
            cur_v, prev_v = cur[-1], (prev[-1] if prev else None)
        suffix = {"sum": f"_{window_days}d", "mean": f"_avg_{window_days}d", "last": ""}[agg]
        out[f"{key}{suffix}"] = cur_v
        if prev_v:
            out[f"{key}_change_{window_days}d"] = (cur_v / prev_v - 1) * 100
    return out


def _day(ts: Any) -> str | None:
    s = str(ts or "")
    return s[:10] if len(s) >= 10 else None


def fetch_bulk(http: Http, api_key: str, metrics: dict[str, str], project_ids: set[str], window_days: int, end: date | None = None) -> dict[str, dict[str, Any]]:
    """Metrikánként egy hívás az összes projektre -> {tt_project_id: {mutató: érték}}."""
    end = end or date.today()
    start = (end - timedelta(days=2 * window_days + 1)).isoformat()
    series: dict[str, dict[str, list[tuple[str, float]]]] = {}
    for key, mid in metrics.items():
        raw = http.try_get_json(
            f"{API}/metrics/{mid}",
            params={"project_ids": "all", "start_date": start, "end_date": end.isoformat()},
            headers=_headers(api_key),
        )
        n = 0
        for row in _rows(raw):
            pid = str(row.get("project_id") or "")
            if pid not in project_ids:
                continue
            d, v = _day(row.get("timestamp") or row.get("date")), _num(row.get("value") if "value" in row else row.get(mid))
            if d is None or v is None:
                continue
            series.setdefault(pid, {}).setdefault(key, []).append((d, v))
            n += 1
        log.info("tokenterminal: %s -> %d adatpont a figyelt projektekre", mid, n)
    return {pid: _aggregate(s, window_days, end) for pid, s in series.items()}


def fetch_project(http: Http, api_key: str, project_id: str, metrics: dict[str, str], window_days: int, end: date | None = None) -> dict[str, Any]:
    """Egy projekt több metrikája egy hívással (széles vagy hosszú formátumot is kezel)."""
    end = end or date.today()
    start = (end - timedelta(days=2 * window_days + 1)).isoformat()
    raw = http.try_get_json(
        f"{API}/projects/{project_id}/metrics",
        params={"metric_ids": ",".join(metrics.values()), "start_date": start, "end_date": end.isoformat()},
        headers=_headers(api_key),
    )
    by_mid = {mid: key for key, mid in metrics.items()}
    series: dict[str, list[tuple[str, float]]] = {}
    for row in _rows(raw):
        d = _day(row.get("timestamp") or row.get("date"))
        if d is None:
            continue
        if row.get("metric_id") in by_mid and "value" in row:          # hosszú formátum
            v = _num(row.get("value"))
            if v is not None:
                series.setdefault(by_mid[row["metric_id"]], []).append((d, v))
            continue
        for mid, key in by_mid.items():                                  # széles formátum
            v = _num(row.get(mid))
            if v is not None:
                series.setdefault(key, []).append((d, v))
    return _aggregate(series, window_days, end)
