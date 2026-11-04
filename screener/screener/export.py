"""Rangsor, figyelőlista, DCA-jelöltek és HTML-jelentés."""
from __future__ import annotations

import html
import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from . import db
from .config import Config

CRITICAL_FLAGS = {"prior_exploit", "extreme_yield", "anonymous_team", "concentrated_ownership"}


def _row_dict(conn: sqlite3.Connection, r: sqlite3.Row, day: str) -> dict[str, Any]:
    snap = conn.execute("SELECT * FROM snapshots WHERE project_id=? AND day=?", (r["project_id"], day)).fetchone()
    return {
        "slug": r["slug"], "name": r["name"], "symbol": r["symbol"], "gecko_id": r["gecko_id"],
        "category": r["category"], "listed_at": r["listed_at"],
        "score": r["total"], "usage": r["usage"], "tokenomics": r["tokenomics"], "team": r["team"],
        "liquidity": r["liquidity"], "red_flags": r["red_flags"], "coverage": r["coverage"],
        "flags": db.row_json(r, "flags", []) or [],
        "tvl": snap["tvl"] if snap else None, "mcap": snap["mcap"] if snap else None,
        "volume_24h": snap["volume_24h"] if snap else None,
        "tvl_change_7d": snap["tvl_change_7d"] if snap else None,
        "tvl_change_30d": snap["tvl_change_30d"] if snap else None,
        "fees_30d": snap["fees_30d"] if snap else None,
        "next_unlock_date": snap["next_unlock_date"] if snap else None,
    }


def ranking(conn: sqlite3.Connection, day: str | None = None, top: int = 50, category: str | None = None) -> list[dict[str, Any]]:
    day = day or db.latest_score_day(conn)
    if not day:
        return []
    rows = db.scores_on(conn, day)
    out = [_row_dict(conn, r, day) for r in rows if not category or (r["category"] or "").lower() == category.lower()]
    return out[:top]


def watchlist(conn: sqlite3.Connection, cfg: Config, day: str | None = None, min_score: float = 50) -> list[dict[str, Any]]:
    """Korai projektek: friss listázás, elfogadható pontszám, kritikus zászló nélkül."""
    day = day or db.latest_score_day(conn)
    if not day:
        return []
    cut = (date.fromisoformat(day) - timedelta(days=int(cfg["universe"]["early_days"]))).isoformat()
    out = []
    for r in db.scores_on(conn, day):
        listed = r["listed_at"] or r["first_seen"][:10]
        if not listed or listed < cut:
            continue
        d = _row_dict(conn, r, day)
        if d["score"] < min_score or CRITICAL_FLAGS & set(d["flags"]):
            continue
        out.append(d)
    return out


def dca_candidates(conn: sqlite3.Connection, cfg: Config, day: str | None = None) -> dict[str, Any]:
    """Az OKX DCA bot számára: csak a teljes szűrőn átment érmék."""
    d = cfg["dca"]
    day = day or db.latest_score_day(conn)
    cands = []
    for r in ranking(conn, day, top=10_000):
        if r["score"] < float(d["min_score"]):
            continue
        if (r["liquidity"] or 0) < float(d["min_liquidity_score"]) or (r["red_flags"] or 0) < float(d["min_red_flag_score"]):
            continue
        if (r["mcap"] or 0) < float(d["min_mcap_usd"]) or not r["symbol"]:
            continue
        if CRITICAL_FLAGS & set(r["flags"]):
            continue
        cands.append({k: r[k] for k in ("symbol", "name", "slug", "gecko_id", "score", "liquidity", "red_flags", "mcap", "flags")})
    return {
        "generated_at": datetime.now().replace(microsecond=0).isoformat(),
        "day": day,
        "filter": dict(d),
        "disclaimer": "Döntéstámogatás, nem pénzügyi tanács és nem automatikus vételi jel.",
        "candidates": cands[: int(d["max_candidates"])],
    }


def write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _usd(v: float | None) -> str:
    if v is None:
        return "–"
    if abs(v) >= 1e9:
        return f"${v/1e9:.2f}B"
    if abs(v) >= 1e6:
        return f"${v/1e6:.1f}M"
    return f"${v/1e3:.0f}k"


def _pct(v: float | None) -> str:
    return "–" if v is None else f"{v:+.1f}%"


def html_report(conn: sqlite3.Connection, cfg: Config, day: str | None = None, top: int = 100) -> str:
    day = day or db.latest_score_day(conn) or db.today()
    rows = ranking(conn, day, top=top)
    wl = watchlist(conn, cfg, day)
    dca = dca_candidates(conn, cfg, day)

    def table(items: list[dict[str, Any]]) -> str:
        if not items:
            return "<p class='muted'>Nincs találat.</p>"
        head = "<tr><th>#</th><th>Projekt</th><th>Kat.</th><th>Pont</th><th>Haszn.</th><th>Token.</th><th>Csapat</th><th>Likv.</th><th>Zászló</th><th>TVL</th><th>TVL 7n</th><th>TVL 30n</th><th>Díj 30n</th><th>Mcap</th><th>Lefed.</th><th>Zászlók</th></tr>"
        body = []
        for i, r in enumerate(items, 1):
            cls = "good" if r["score"] >= 70 else ("mid" if r["score"] >= 50 else "bad")
            body.append(
                f"<tr><td>{i}</td><td><b>{html.escape(r['name'])}</b> <span class='muted'>{html.escape(r['symbol'] or '')}</span></td>"
                f"<td>{html.escape(r['category'] or '')}</td><td class='{cls}'><b>{r['score']:.0f}</b></td>"
                f"<td>{_n(r['usage'])}</td><td>{_n(r['tokenomics'])}</td><td>{_n(r['team'])}</td><td>{_n(r['liquidity'])}</td><td>{_n(r['red_flags'])}</td>"
                f"<td>{_usd(r['tvl'])}</td><td>{_pct(r['tvl_change_7d'])}</td><td>{_pct(r['tvl_change_30d'])}</td><td>{_usd(r['fees_30d'])}</td><td>{_usd(r['mcap'])}</td>"
                f"<td>{(r['coverage'] or 0)*100:.0f}%</td><td class='flags'>{html.escape(', '.join(r['flags']))}</td></tr>"
            )
        return f"<table>{head}{''.join(body)}</table>"

    dca_html = "<p class='muted'>Nincs jelölt.</p>"
    if dca["candidates"]:
        dca_html = "<ul>" + "".join(
            f"<li><b>{html.escape(c['symbol'])}</b> – {html.escape(c['name'])}: {c['score']:.0f} pont, mcap {_usd(c['mcap'])}</li>" for c in dca["candidates"]
        ) + "</ul>"

    return f"""<!doctype html><html lang="hu"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kripto szűrő – {day}</title>
<style>
:root{{--bg:#fff;--fg:#1a1a1a;--muted:#6b7280;--line:#e5e7eb;--good:#15803d;--mid:#b45309;--bad:#b91c1c}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0f1115;--fg:#e5e7eb;--muted:#9ca3af;--line:#262a33;--good:#4ade80;--mid:#fbbf24;--bad:#f87171}}}}
body{{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif}}
h1,h2{{margin:0 0 8px}} .muted{{color:var(--muted)}} .good{{color:var(--good)}} .mid{{color:var(--mid)}} .bad{{color:var(--bad)}}
.wrap{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;font-size:13px}} th,td{{padding:6px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}}
th:nth-child(2),td:nth-child(2),th:nth-child(3),td:nth-child(3),td.flags,th:last-child{{text-align:left}} td.flags{{white-space:normal;max-width:320px;color:var(--muted)}}
section{{margin:24px 0}} .note{{border:1px solid var(--line);padding:10px 12px;border-radius:8px}}
</style></head><body>
<h1>Kripto projekt-szűrő</h1>
<p class="muted">Értékelés napja: {day} · Figyelt projektek: {len(rows)} · Súlyok: {html.escape(json.dumps(cfg['weights']))}</p>
<div class="note">Döntéstámogató eszköz. A pontszám a kockázatot szűri, nyereséget nem garantál, nem pénzügyi tanács. Kis kapitalizációjú projekteknél a teljes veszteség is lehetséges.</div>
<section><h2>DCA-jelöltek (OKX bot szűrő)</h2>{dca_html}</section>
<section><h2>Figyelőlista – korai projektek</h2><div class="wrap">{table(wl)}</div></section>
<section><h2>Rangsor</h2><div class="wrap">{table(rows)}</div></section>
</body></html>"""


def _n(v: float | None) -> str:
    return "–" if v is None else f"{v:.0f}"
