"""DeFiSafety Process Quality Review (PQR) pontszámok.

A DeFiSafety-nek nincs dokumentált nyilvános JSON API-ja. Három réteg, csökkenő sorrendben:
1. a webalkalmazás által használt lista-végpont (alapból https://api.defisafety.com/api/pqrs,
   lapozva), toleráns mezőfelismeréssel;
2. a riportoldalak (https://defisafety.com/app/pqrs/{id}) szövegének értelmezése a
   config [defisafety.ids] slug -> id térkép alapján;
3. kézi érték: [overrides.slug] defisafety_score = 85.

A pontszám 0-100 (%), 70 felett PASS. Metodika: https://defisafety.com/documentation-09/
"""
from __future__ import annotations

import html as html_mod
import logging
import re
from datetime import datetime
from typing import Any, Iterable

from ..http import Http

log = logging.getLogger(__name__)

DEFAULT_API = "https://api.defisafety.com/api/pqrs"
REPORT_URL = "https://defisafety.com/app/pqrs/{id}"
PASS_THRESHOLD = 70.0

_VERSION_RE = re.compile(r"\b(v\d+(?:\.\d+)?|version\s*\d+)\b", re.I)
_PAREN_RE = re.compile(r"\s*\([^)]*\)")


def _num(v: Any) -> float | None:
    if isinstance(v, str):
        v = v.strip().rstrip("%")
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _pct(v: Any) -> float | None:
    """Pontszám %-ban; a 0..1 skálát is felismeri."""
    f = _num(v)
    if f is None:
        return None
    return f * 100 if 0 < f <= 1.0 else f


def _day(v: Any) -> str | None:
    if not v:
        return None
    s = str(v)
    m = re.search(r"\d{4}-\d{2}-\d{2}", s)
    if m:
        return m.group(0)
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def norm_name(name: str | None) -> str:
    """'AAVE V2 (Ethereum)' -> 'aave'; verzió és zárójel nélkül, csak betű-szám."""
    s = _PAREN_RE.sub("", (name or "").lower())
    s = _VERSION_RE.sub("", s)
    s = re.sub(r"\b(finance|protocol|network|dao|labs?)\b", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


def _items(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [r for r in raw if isinstance(r, dict)]
    if isinstance(raw, dict):
        for key in ("data", "items", "results", "pqrs", "rows"):
            v = raw.get(key)
            if isinstance(v, list):
                return [r for r in v if isinstance(r, dict)]
            if isinstance(v, dict):
                inner = _items(v)
                if inner:
                    return inner
    return []


def _get(d: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def parse_review(item: dict[str, Any]) -> dict[str, Any] | None:
    """Egy lista-elem normalizálása. None, ha nincs benne értelmezhető pontszám."""
    score = _pct(_get(item, "score", "finalScore", "final_score", "totalScore", "total_score", "percentage"))
    if score is None:
        return None
    rid = _get(item, "id", "pqrId", "pqr_id", "_id")
    title = _get(item, "title", "name", "protocol", "protocolName", "project") or ""
    status = str(_get(item, "status", "result", "passFail", "verdict") or "").lower()
    passed = ("pass" in status and "fail" not in status) if status else score >= PASS_THRESHOLD
    return {
        "id": int(rid) if isinstance(rid, (int, float)) or (isinstance(rid, str) and rid.isdigit()) else rid,
        "title": str(title),
        "score": round(score, 1),
        "pass": passed,
        "date": _day(_get(item, "date", "reviewDate", "review_date", "publishedAt", "updatedAt", "updated_at", "createdAt", "created_at")),
        "version": str(_get(item, "processVersion", "process_version", "version", "auditProcess") or "") or None,
        "chain": str(_get(item, "chain", "network", "blockchain") or "") or None,
        "url": REPORT_URL.format(id=rid) if rid is not None else None,
    }


def fetch_reviews(http: Http, api_url: str = DEFAULT_API, page_size: int = 100, max_pages: int = 10) -> list[dict[str, Any]]:
    """Az összes PQR a lista-végpontról (lapozva). Üres lista, ha a végpont nem elérhető."""
    out: list[dict[str, Any]] = []
    seen: set = set()
    for page in range(1, max_pages + 1):
        raw = http.try_get_json(api_url, params={"page": page, "limit": page_size})
        items = _items(raw)
        if not items:
            break
        new = 0
        for it in items:
            r = parse_review(it)
            if r and r["id"] not in seen:
                seen.add(r["id"])
                out.append(r)
                new += 1
        if new == 0 or len(items) < page_size:
            break
    if out:
        log.info("defisafety: %d review a lista-végpontról", len(out))
    return out


_SCORE_RE = re.compile(r"final\s*score\s*[:\s]*\s*(\d{1,3})\s*%", re.I)
_PASSFAIL_RE = re.compile(r"\b(PASS|FAIL)\b")
_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2}|[A-Z][a-z]+ \d{1,2}, \d{4})\b")
_VERSION_PAGE_RE = re.compile(r"process\s+quality\s+review\s*\(?\s*(\d\.\d)", re.I)
_TITLE_RE = re.compile(r"<title>\s*(.*?)\s*(?:-|–|\|)\s*(?:detailed report|defisafety).*?</title>", re.I | re.S)


def parse_report_html(text: str, rid: int | str) -> dict[str, Any] | None:
    """Riportoldal szövegéből: végső pontszám, PASS/FAIL, dátum, folyamatverzió, cím."""
    if not text:
        return None
    plain = html_mod.unescape(re.sub(r"<[^>]+>", " ", text))
    m = _SCORE_RE.search(plain)
    if not m:
        return None
    score = float(m.group(1))
    pf = _PASSFAIL_RE.search(plain[m.start(): m.start() + 300])
    title_m = _TITLE_RE.search(text)
    date_m = _DATE_RE.search(plain)
    ver_m = _VERSION_PAGE_RE.search(plain)
    return {
        "id": rid, "title": html_mod.unescape(title_m.group(1)).strip() if title_m else "",
        "score": score, "pass": (pf.group(1) == "PASS") if pf else score >= PASS_THRESHOLD,
        "date": _day(date_m.group(1)) if date_m else None,
        "version": ver_m.group(1) if ver_m else None, "chain": None, "url": REPORT_URL.format(id=rid),
    }


def fetch_report(http: Http, rid: int | str) -> dict[str, Any] | None:
    """Egy riportoldal lekérése és értelmezése (HTML, nem JSON)."""
    url = REPORT_URL.format(id=rid)
    text = http.try_get_text(url, headers={"Accept": "text/html"})
    return parse_report_html(text or "", rid)


def match_reviews(reviews: Iterable[dict[str, Any]], ours: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """{saját slug -> legfrissebb review} név alapján (verzió- és zárójel-független)."""
    by_name: dict[str, list[dict[str, Any]]] = {}
    for r in reviews:
        key = norm_name(r.get("title"))
        if key:
            by_name.setdefault(key, []).append(r)
    out: dict[str, dict[str, Any]] = {}
    for o in ours:
        cands = by_name.get(norm_name(o.get("name"))) or by_name.get(norm_name(o["slug"].replace("-", " ")))
        if not cands:
            continue
        best = sorted(cands, key=lambda r: (r.get("date") or "", r.get("score") or 0), reverse=True)[0]
        out[o["slug"]] = best
    return out


def as_metrics(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "pqr_score": r["score"], "pqr_pass": 1.0 if r.get("pass") else 0.0, "pqr_date": r.get("date"),
        "pqr_version": r.get("version"), "pqr_title": r.get("title"), "pqr_url": r.get("url"),
        "pqr_id": r.get("id") if isinstance(r.get("id"), (int, float)) else None,
    }
