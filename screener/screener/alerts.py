"""Riasztási szabályok: unlock közeleg, TVL zuhan, fejlesztés leáll, új ígéretes projekt, pontszám-ugrás."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta

from . import db
from .config import Config
from .scoring import days_between


@dataclass
class Alert:
    key: str
    kind: str
    project_id: int | None
    severity: str  # info | warn | crit
    message: str


def _fmt_usd(v: float | None) -> str:
    if v is None:
        return "n/a"
    if v >= 1e9:
        return f"${v/1e9:.2f}B"
    if v >= 1e6:
        return f"${v/1e6:.1f}M"
    if v >= 1e3:
        return f"${v/1e3:.0f}k"
    return f"${v:.0f}"


def generate_alerts(conn: sqlite3.Connection, cfg: Config, day: str | None = None) -> list[Alert]:
    day = day or db.latest_score_day(conn) or db.today()
    a = cfg["alerts"]
    today = date.fromisoformat(day)
    out: list[Alert] = []
    for row in db.scores_on(conn, day):
        pid, slug, name = row["project_id"], row["slug"], row["name"]
        label = f"{name} ({row['symbol']})" if row["symbol"] else name
        snap = conn.execute("SELECT * FROM snapshots WHERE project_id=? AND day=?", (pid, day)).fetchone()
        if snap is None:
            continue
        flags = db.row_json(row, "flags", []) or []

        # 1) nagy unlock közeleg
        d = days_between(snap["next_unlock_date"], today)
        if d is not None and 0 <= d <= int(a["unlock_days_ahead"]) and snap["next_unlock_amount"] and snap["price"] and snap["mcap"]:
            pct = snap["next_unlock_amount"] * snap["price"] / snap["mcap"] * 100
            if pct >= float(cfg["scoring"]["unlock_pct_of_mcap"]):
                out.append(Alert(
                    f"unlock:{slug}:{snap['next_unlock_date']}", "unlock", pid, "warn",
                    f"🔓 <b>{label}</b>: unlock {d} nap múlva ({snap['next_unlock_date']}), "
                    f"{_fmt_usd(snap['next_unlock_amount'] * snap['price'])} ≈ a kapitalizáció {pct:.1f}%-a.",
                ))

        # 2) TVL zuhan
        if snap["tvl_change_7d"] is not None and snap["tvl_change_7d"] <= float(a["tvl_drop_7d_pct"]):
            out.append(Alert(
                f"tvl_drop:{slug}:{day}", "tvl_drop", pid, "crit",
                f"📉 <b>{label}</b>: TVL 7 nap alatt {snap['tvl_change_7d']:+.1f}% (most {_fmt_usd(snap['tvl'])}).",
            ))
        elif snap["tvl_change_1d"] is not None and snap["tvl_change_1d"] <= float(a["tvl_drop_1d_pct"]):
            out.append(Alert(
                f"tvl_drop:{slug}:{day}", "tvl_drop", pid, "warn",
                f"📉 <b>{label}</b>: TVL 1 nap alatt {snap['tvl_change_1d']:+.1f}% (most {_fmt_usd(snap['tvl'])}).",
            ))

        # 3) fejlesztés leállt (havonta egyszer emlékeztet)
        if "dev_stalled" in flags:
            dev = db.latest_dev_stats(conn, pid)
            since = dev["last_push"][:10] if dev and dev["last_push"] else "ismeretlen"
            out.append(Alert(
                f"dev_stalled:{slug}:{day[:7]}", "dev_stalled", pid, "warn",
                f"🛑 <b>{label}</b>: a fejlesztés leállni látszik (utolsó push: {since}, commit 90 nap: {dev['commits_90d'] if dev else 'n/a'}).",
            ))

        # 4) új, ígéretes projekt
        early_cut = (today - timedelta(days=int(cfg["universe"]["early_days"]))).isoformat()
        listed = row["listed_at"] or row["first_seen"][:10]
        if listed and listed >= early_cut and row["total"] >= float(a["new_project_min_score"]):
            out.append(Alert(
                f"new:{slug}", "new_project", pid, "info",
                f"🆕 <b>{label}</b>: friss listázás ({listed}), pontszám {row['total']:.0f}/100, "
                f"TVL {_fmt_usd(snap['tvl'])}, zászlók: {', '.join(flags) or 'nincs'}.",
            ))

        # 5) nagy pontszám-változás az előző értékeléshez képest
        prev = db.latest_score(conn, pid, before=day)
        if prev is not None and abs(row["total"] - prev["total"]) >= float(a["score_jump_points"]):
            direction = "⬆️" if row["total"] > prev["total"] else "⬇️"
            out.append(Alert(
                f"score_jump:{slug}:{day}", "score_jump", pid, "info",
                f"{direction} <b>{label}</b>: pontszám {prev['total']:.0f} → {row['total']:.0f} ({prev['day']} → {day}).",
            ))
    return out


def store_alerts(conn: sqlite3.Connection, alerts: list[Alert]) -> int:
    """Új (még nem látott kulcsú) riasztások mentése. Visszaadja az újak számát."""
    n = 0
    for al in alerts:
        if db.add_alert(conn, al.key, al.kind, al.project_id, al.severity, al.message):
            n += 1
    conn.commit()
    return n
