"""SQLite séma és segédfüggvények."""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id            INTEGER PRIMARY KEY,
    slug          TEXT UNIQUE NOT NULL,
    llama_id      TEXT,
    name          TEXT NOT NULL,
    symbol        TEXT,
    gecko_id      TEXT,
    category      TEXT,
    chains        TEXT,
    url           TEXT,
    twitter       TEXT,
    github        TEXT,          -- JSON lista: org vagy owner/repo
    listed_at     TEXT,          -- DefiLlama listázás napja (ISO)
    audits        INTEGER,
    audit_links   TEXT,          -- JSON lista
    first_seen    TEXT NOT NULL, -- mikor láttuk először mi
    last_seen     TEXT NOT NULL,
    details_at    TEXT,          -- CoinGecko részlet utolsó frissítése
    dev_at        TEXT,          -- GitHub statisztika utolsó frissítése
    extra         TEXT           -- JSON: repos, exchanges, genesis_date, stb.
);

CREATE TABLE IF NOT EXISTS snapshots (
    project_id      INTEGER NOT NULL REFERENCES projects(id),
    day             TEXT NOT NULL,
    tvl             REAL,
    tvl_change_1d   REAL,
    tvl_change_7d   REAL,
    tvl_change_30d  REAL,
    fees_24h        REAL,
    fees_7d         REAL,
    fees_30d        REAL,
    fees_change_30d REAL,
    revenue_30d     REAL,
    users_24h       REAL,
    txs_24h         REAL,
    price           REAL,
    price_change_7d REAL,
    price_change_30d REAL,
    mcap            REAL,
    fdv             REAL,
    volume_24h      REAL,
    circ_supply     REAL,
    total_supply    REAL,
    max_supply      REAL,
    next_unlock_date   TEXT,
    next_unlock_amount REAL,
    unlocks_per_day    REAL,
    max_apy         REAL,
    PRIMARY KEY (project_id, day)
);

CREATE TABLE IF NOT EXISTS dev_stats (
    project_id      INTEGER NOT NULL REFERENCES projects(id),
    day             TEXT NOT NULL,
    source          TEXT,
    repos           TEXT,     -- JSON lista
    stars           INTEGER,
    commits_90d     INTEGER,
    contributors_90d INTEGER,
    contributors_total INTEGER,
    releases_90d    INTEGER,
    last_push       TEXT,
    PRIMARY KEY (project_id, day)
);

CREATE TABLE IF NOT EXISTS hacks (
    project_slug  TEXT NOT NULL,
    day           TEXT NOT NULL,
    amount_usd    REAL,
    technique     TEXT,
    source        TEXT,
    PRIMARY KEY (project_slug, day)
);

CREATE TABLE IF NOT EXISTS scores (
    project_id   INTEGER NOT NULL REFERENCES projects(id),
    day          TEXT NOT NULL,
    total        REAL NOT NULL,
    usage        REAL,
    tokenomics   REAL,
    team         REAL,
    liquidity    REAL,
    red_flags    REAL,
    coverage     REAL,
    flags        TEXT,   -- JSON lista
    details      TEXT,   -- JSON
    PRIMARY KEY (project_id, day)
);

CREATE TABLE IF NOT EXISTS alerts (
    id          INTEGER PRIMARY KEY,
    key         TEXT UNIQUE NOT NULL,
    kind        TEXT NOT NULL,
    project_id  INTEGER REFERENCES projects(id),
    severity    TEXT NOT NULL,
    message     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    sent_at     TEXT
);

CREATE INDEX IF NOT EXISTS idx_snapshots_day ON snapshots(day);
CREATE INDEX IF NOT EXISTS idx_scores_day ON scores(day);
"""


def today() -> str:
    return date.today().isoformat()


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def connect(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    return conn


def _j(v: Any) -> str | None:
    return None if v is None else json.dumps(v, ensure_ascii=False)


def _lj(v: str | None, default: Any = None) -> Any:
    if not v:
        return default
    try:
        return json.loads(v)
    except ValueError:
        return default


def upsert_project(conn: sqlite3.Connection, p: dict[str, Any]) -> int:
    """Projekt beszúrása/frissítése slug alapján. Visszaadja az id-t."""
    ts = now_iso()
    row = conn.execute("SELECT id FROM projects WHERE slug=?", (p["slug"],)).fetchone()
    fields = {
        "llama_id": p.get("llama_id"),
        "name": p["name"],
        "symbol": p.get("symbol"),
        "gecko_id": p.get("gecko_id"),
        "category": p.get("category"),
        "chains": _j(p.get("chains")),
        "url": p.get("url"),
        "twitter": p.get("twitter"),
        "github": _j(p.get("github")),
        "listed_at": p.get("listed_at"),
        "audits": p.get("audits"),
        "audit_links": _j(p.get("audit_links")),
        "last_seen": ts,
    }
    if row:
        sets = ", ".join(f"{k}=?" for k in fields)
        conn.execute(f"UPDATE projects SET {sets} WHERE id=?", (*fields.values(), row["id"]))
        return int(row["id"])
    fields["slug"] = p["slug"]
    fields["first_seen"] = ts
    cols = ", ".join(fields)
    qs = ", ".join("?" for _ in fields)
    cur = conn.execute(f"INSERT INTO projects ({cols}) VALUES ({qs})", tuple(fields.values()))
    return int(cur.lastrowid)


def update_project_extra(conn: sqlite3.Connection, project_id: int, extra: dict[str, Any], details_at: str | None = None) -> None:
    row = conn.execute("SELECT extra FROM projects WHERE id=?", (project_id,)).fetchone()
    merged = {**(_lj(row["extra"], {}) if row else {}), **extra}
    if details_at:
        conn.execute("UPDATE projects SET extra=?, details_at=? WHERE id=?", (_j(merged), details_at, project_id))
    else:
        conn.execute("UPDATE projects SET extra=? WHERE id=?", (_j(merged), project_id))


SNAPSHOT_COLS = [
    "tvl", "tvl_change_1d", "tvl_change_7d", "tvl_change_30d", "fees_24h", "fees_7d", "fees_30d",
    "fees_change_30d", "revenue_30d", "users_24h", "txs_24h", "price", "price_change_7d",
    "price_change_30d", "mcap", "fdv", "volume_24h", "circ_supply", "total_supply", "max_supply",
    "next_unlock_date", "next_unlock_amount", "unlocks_per_day", "max_apy",
]


def upsert_snapshot(conn: sqlite3.Connection, project_id: int, day: str, data: dict[str, Any]) -> None:
    """Napi pillanatkép. Csak a megadott (nem None) mezőket írja felül, így több forrás is bővítheti."""
    existing = conn.execute("SELECT * FROM snapshots WHERE project_id=? AND day=?", (project_id, day)).fetchone()
    merged = {c: (existing[c] if existing else None) for c in SNAPSHOT_COLS}
    for k, v in data.items():
        if k in merged and v is not None:
            merged[k] = v
    cols = ", ".join(["project_id", "day", *SNAPSHOT_COLS])
    qs = ", ".join("?" for _ in range(len(SNAPSHOT_COLS) + 2))
    conn.execute(
        f"INSERT OR REPLACE INTO snapshots ({cols}) VALUES ({qs})",
        (project_id, day, *[merged[c] for c in SNAPSHOT_COLS]),
    )


def upsert_dev_stats(conn: sqlite3.Connection, project_id: int, day: str, data: dict[str, Any]) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO dev_stats
           (project_id, day, source, repos, stars, commits_90d, contributors_90d, contributors_total, releases_90d, last_push)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            project_id, day, data.get("source"), _j(data.get("repos")), data.get("stars"),
            data.get("commits_90d"), data.get("contributors_90d"), data.get("contributors_total"),
            data.get("releases_90d"), data.get("last_push"),
        ),
    )
    conn.execute("UPDATE projects SET dev_at=? WHERE id=?", (day, project_id))


def upsert_hack(conn: sqlite3.Connection, slug: str, day: str, amount: float | None, technique: str | None, source: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO hacks (project_slug, day, amount_usd, technique, source) VALUES (?,?,?,?,?)",
        (slug, day, amount, technique, source),
    )


def upsert_score(conn: sqlite3.Connection, project_id: int, day: str, s: dict[str, Any]) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO scores
           (project_id, day, total, usage, tokenomics, team, liquidity, red_flags, coverage, flags, details)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            project_id, day, s["total"], s["usage"], s["tokenomics"], s["team"], s["liquidity"],
            s["red_flags"], s["coverage"], _j(s["flags"]), _j(s["details"]),
        ),
    )


def latest_snapshot(conn: sqlite3.Connection, project_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM snapshots WHERE project_id=? ORDER BY day DESC LIMIT 1", (project_id,)
    ).fetchone()


def snapshot_days_ago(conn: sqlite3.Connection, project_id: int, days: int, on: str | None = None) -> sqlite3.Row | None:
    """A legközelebbi pillanatkép `days` nappal ezelőttről (±3 nap tűrés)."""
    ref = date.fromisoformat(on) if on else date.today()
    target = ref - timedelta(days=days)
    lo, hi = (target - timedelta(days=3)).isoformat(), (target + timedelta(days=3)).isoformat()
    return conn.execute(
        "SELECT * FROM snapshots WHERE project_id=? AND day BETWEEN ? AND ? ORDER BY ABS(julianday(day)-julianday(?)) LIMIT 1",
        (project_id, lo, hi, target.isoformat()),
    ).fetchone()


def latest_dev_stats(conn: sqlite3.Connection, project_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM dev_stats WHERE project_id=? ORDER BY day DESC LIMIT 1", (project_id,)
    ).fetchone()


def latest_score(conn: sqlite3.Connection, project_id: int, before: str | None = None) -> sqlite3.Row | None:
    if before:
        return conn.execute(
            "SELECT * FROM scores WHERE project_id=? AND day<? ORDER BY day DESC LIMIT 1", (project_id, before)
        ).fetchone()
    return conn.execute("SELECT * FROM scores WHERE project_id=? ORDER BY day DESC LIMIT 1", (project_id,)).fetchone()


def hacks_for(conn: sqlite3.Connection, slug: str) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM hacks WHERE project_slug=? ORDER BY day DESC", (slug,)).fetchall()


def all_projects(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM projects ORDER BY name").fetchall()


def project_by_slug(conn: sqlite3.Connection, slug: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM projects WHERE slug=?", (slug,)).fetchone()


def scores_on(conn: sqlite3.Connection, day: str) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT s.*, p.slug, p.name, p.symbol, p.gecko_id, p.category, p.listed_at, p.first_seen
           FROM scores s JOIN projects p ON p.id = s.project_id
           WHERE s.day=? ORDER BY s.total DESC""",
        (day,),
    ).fetchall()


def latest_score_day(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT MAX(day) AS d FROM scores").fetchone()
    return row["d"] if row else None


def add_alert(conn: sqlite3.Connection, key: str, kind: str, project_id: int | None, severity: str, message: str) -> bool:
    """True, ha új riasztás (még nem létezett ez a kulcs)."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO alerts (key, kind, project_id, severity, message, created_at) VALUES (?,?,?,?,?,?)",
        (key, kind, project_id, severity, message, now_iso()),
    )
    return cur.rowcount == 1


def unsent_alerts(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM alerts WHERE sent_at IS NULL ORDER BY id").fetchall()


def mark_alerts_sent(conn: sqlite3.Connection, ids: Iterable[int]) -> None:
    ts = now_iso()
    conn.executemany("UPDATE alerts SET sent_at=? WHERE id=?", [(ts, i) for i in ids])


def row_json(row: sqlite3.Row | None, col: str, default: Any = None) -> Any:
    if row is None:
        return default
    return _lj(row[col], default)
