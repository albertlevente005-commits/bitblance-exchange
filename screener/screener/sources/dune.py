"""Dune Analytics: mentett lekérdezések eredményeinek bekötése projektekhez.

A Dune-on nincs "általános" protokoll-API: a felhasználó saját (vagy közösségi) mentett
lekérdezéseket ad meg a config.toml [[dune.queries]] blokkjaiban. Minden lekérdezés
eredménytáblájából egy oszlop azonosítja a projektet (slug / symbol / gecko_id / name),
a többi oszlopot pedig mutatókra képezzük (pl. users_30d, revenue_30d).

API: https://docs.dune.com/api-reference  (X-Dune-API-Key fejléc)
- GET  /api/v1/query/{id}/results          a legutóbbi futás eredménye (olcsó)
- POST /api/v1/query/{id}/execute          új futtatás (kreditet fogyaszt)
- GET  /api/v1/execution/{id}/results      futtatás eredménye/állapota
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from ..http import Http

log = logging.getLogger(__name__)

API = "https://api.dune.com/api/v1"
STANDARD_METRICS = {"users_24h", "users_30d", "txs_30d", "revenue_30d", "fees_30d", "volume_30d", "holders"}


def _headers(api_key: str) -> dict:
    return {"X-Dune-API-Key": api_key}


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _parse_ts(v: Any) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


def fetch_results(http: Http, api_key: str, query_id: int, limit: int = 5000) -> tuple[list[dict[str, Any]], datetime | None]:
    """A lekérdezés legutóbbi eredménye: (sorok, mikor futott)."""
    raw = http.try_get_json(f"{API}/query/{query_id}/results", params={"limit": limit}, headers=_headers(api_key))
    if not raw:
        return [], None
    rows = ((raw.get("result") or {}).get("rows")) or []
    return rows, _parse_ts(raw.get("execution_ended_at"))


def execute_and_wait(http: Http, api_key: str, query_id: int, timeout_s: float = 300, poll_s: float = 10, sleep: Callable[[float], None] | None = None) -> list[dict[str, Any]]:
    """Új futtatás és várakozás az eredményre (kreditet fogyaszt)."""
    sleep = sleep or http.sleep
    started = http.try_post_json(f"{API}/query/{query_id}/execute", json={"performance": "medium"}, headers=_headers(api_key))
    exec_id = (started or {}).get("execution_id")
    if not exec_id:
        return []
    waited = 0.0
    while waited <= timeout_s:
        res = http.try_get_json(f"{API}/execution/{exec_id}/results", headers=_headers(api_key)) or {}
        state = res.get("state", "")
        if state == "QUERY_STATE_COMPLETED":
            return ((res.get("result") or {}).get("rows")) or []
        if state in ("QUERY_STATE_FAILED", "QUERY_STATE_CANCELLED", "QUERY_STATE_EXPIRED"):
            log.warning("dune: a(z) %s futtatás állapota %s", query_id, state)
            return []
        sleep(poll_s)
        waited += poll_s
    log.warning("dune: időtúllépés a(z) %s lekérdezésnél", query_id)
    return []


def match_key(value: Any, match_by: str) -> str:
    return str(value or "").strip().lower()


def collect(
    http: Http, api_key: str, queries: list[dict[str, Any]], index: dict[str, dict[str, str]],
    max_age_hours: float = 36, execute_if_stale: bool = False, sleep: Callable[[float], None] | None = None,
) -> dict[str, dict[str, Any]]:
    """Minden konfigurált lekérdezés -> {slug: {metric: érték}}.

    index: {"slug": {slug_lower: slug}, "symbol": {symbol_lower: slug}, "gecko_id": {...}, "name": {...}}
    """
    out: dict[str, dict[str, Any]] = {}
    if not api_key:
        if queries:
            log.warning("dune: DUNE_API_KEY hiányzik, a Dune-lekérdezések kimaradnak")
        return out
    now = datetime.now(timezone.utc)
    for q in queries:
        qid = int(q["id"])
        match_by = str(q.get("match_by", "slug")).lower()
        match_col = str(q.get("match_column", match_by))
        metrics: dict[str, str] = dict(q.get("metrics") or {})
        rows, ended = fetch_results(http, api_key, qid)
        stale = ended is None or (now - ended) > timedelta(hours=float(max_age_hours))
        if stale and execute_if_stale:
            fresh = execute_and_wait(http, api_key, qid, sleep=sleep)
            if fresh:
                rows = fresh
        lookup = index.get(match_by, {})
        matched = 0
        for row in rows:
            slug = lookup.get(match_key(row.get(match_col), match_by))
            if not slug:
                continue
            rec = out.setdefault(slug, {})
            for metric, col in metrics.items():
                val = row.get(col)
                num = _num(val)
                rec[metric] = num if num is not None else val
            rec["_query_id"] = qid
            rec["_executed_at"] = ended.isoformat() if ended else None
            matched += 1
        log.info("dune: %s -> %d sor, %d projekthez illesztve", qid, len(rows), matched)
    return out
