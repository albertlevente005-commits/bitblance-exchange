"""Webes platform: REST API + dashboard + beépített napi ütemező."""
from __future__ import annotations

import logging
import os
import secrets
import sqlite3
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from . import __version__, db
from .config import Config, load_config
from .export import dca_candidates, html_report, ranking, watchlist
from .scheduler import DailyScheduler, run_daily

log = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"


def _public_config(cfg: Config) -> dict[str, Any]:
    return {k: cfg[k] for k in ("universe", "weights", "scoring", "alerts", "dca")}


def _project_payload(conn: sqlite3.Connection, cfg: Config, slug: str) -> dict[str, Any]:
    p = db.project_by_slug(conn, slug)
    if p is None:
        raise HTTPException(404, "Nincs ilyen projekt")
    pid = p["id"]
    score = db.latest_score(conn, pid)
    snaps = conn.execute("SELECT * FROM snapshots WHERE project_id=? ORDER BY day DESC LIMIT 120", (pid,)).fetchall()
    scores = conn.execute("SELECT day, total, usage, tokenomics, team, liquidity, red_flags FROM scores WHERE project_id=? ORDER BY day DESC LIMIT 120", (pid,)).fetchall()
    dev = db.latest_dev_stats(conn, pid)
    alerts = conn.execute("SELECT kind, severity, message, created_at, sent_at FROM alerts WHERE project_id=? ORDER BY id DESC LIMIT 20", (pid,)).fetchall()
    return {
        "project": {
            **{k: p[k] for k in ("slug", "name", "symbol", "gecko_id", "category", "url", "twitter", "listed_at", "audits", "first_seen", "details_at", "dev_at")},
            "chains": db.row_json(p, "chains", []), "github": db.row_json(p, "github", []),
            "audit_links": db.row_json(p, "audit_links", []), "extra": db.row_json(p, "extra", {}),
            "override": cfg.override(slug),
        },
        "score": None if score is None else {
            **{k: score[k] for k in ("day", "total", "usage", "tokenomics", "team", "liquidity", "red_flags", "coverage")},
            "flags": db.row_json(score, "flags", []), "details": db.row_json(score, "details", {}),
        },
        "snapshots": [dict(s) for s in reversed(snaps)],
        "score_history": [dict(s) for s in reversed(scores)],
        "dev": None if dev is None else {**dict(dev), "repos": db.row_json(dev, "repos", [])},
        "hacks": [dict(h) for h in db.hacks_for(conn, slug)],
        "alerts": [dict(a) for a in alerts],
        "governance": db.latest_metrics(conn, pid, "snapshot", max_age_days=3650),
        "dune": db.latest_metrics(conn, pid, "dune", max_age_days=3650),
        "tokenterminal": db.latest_metrics(conn, pid, "tokenterminal", max_age_days=3650),
    }


def create_app(cfg: Config | None = None, scheduler_enabled: bool = True) -> FastAPI:
    cfg = cfg or load_config(os.environ.get("SCREENER_CONFIG", "config.toml"))
    web_cfg = cfg.data.get("web", {}) or {}
    run_at = str(web_cfg.get("run_at", "06:00"))
    admin_token = os.environ.get("SCREENER_ADMIN_TOKEN", "")
    scheduler = DailyScheduler(run_at, lambda: run_daily(cfg, send=bool(web_cfg.get("send_telegram", True))))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db.connect(cfg.db_path).close()
        if scheduler_enabled and bool(web_cfg.get("scheduler", True)):
            scheduler.start()
        yield
        scheduler.stop()

    app = FastAPI(title="Kripto projekt-szűrő platform", version=__version__, lifespan=lifespan)
    app.state.cfg = cfg
    app.state.scheduler = scheduler

    def get_conn():
        conn = db.connect(cfg.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def require_admin(x_admin_token: str = Header(default="")):
        if not admin_token:
            raise HTTPException(403, "SCREENER_ADMIN_TOKEN nincs beállítva, az admin műveletek le vannak tiltva")
        if not secrets.compare_digest(x_admin_token, admin_token):
            raise HTTPException(401, "Érvénytelen admin token")

    @app.get("/api/health")
    def health(conn: sqlite3.Connection = Depends(get_conn)):
        day = db.latest_score_day(conn)
        n = conn.execute("SELECT COUNT(*) AS n FROM projects").fetchone()["n"]
        return {
            "status": "ok", "version": __version__, "latest_day": day, "projects": n,
            "scheduler": {
                "enabled": scheduler_enabled and bool(web_cfg.get("scheduler", True)), "run_at": run_at,
                "running": scheduler.running,
                "last_run": scheduler.last_run.isoformat() if scheduler.last_run else None,
                "last_result": scheduler.last_result,
                "next_run": scheduler.next_run().isoformat(),
            },
            "telegram_configured": bool(cfg.secrets.telegram_token and cfg.secrets.telegram_chat_id),
        }

    @app.get("/api/config")
    def config_view():
        return _public_config(cfg)

    @app.get("/api/days")
    def days(conn: sqlite3.Connection = Depends(get_conn)):
        return [r["day"] for r in conn.execute("SELECT DISTINCT day FROM scores ORDER BY day DESC LIMIT 400")]

    @app.get("/api/categories")
    def categories(conn: sqlite3.Connection = Depends(get_conn)):
        return [r["category"] for r in conn.execute("SELECT DISTINCT category FROM projects WHERE category IS NOT NULL ORDER BY category")]

    @app.get("/api/ranking")
    def api_ranking(
        conn: sqlite3.Connection = Depends(get_conn),
        day: str | None = None, top: int = Query(100, ge=1, le=2000), category: str | None = None,
        min_score: float = 0, q: str | None = None, flag: str | None = None,
    ):
        rows = ranking(conn, day, top=10_000, category=category)
        if q:
            ql = q.lower()
            rows = [r for r in rows if ql in r["name"].lower() or ql in (r["symbol"] or "").lower() or ql in r["slug"]]
        if flag:
            rows = [r for r in rows if flag in r["flags"]]
        rows = [r for r in rows if r["score"] >= min_score]
        return {"day": day or db.latest_score_day(conn), "count": len(rows), "items": rows[:top]}

    @app.get("/api/projects/{slug}")
    def api_project(slug: str, conn: sqlite3.Connection = Depends(get_conn)):
        return _project_payload(conn, cfg, slug)

    @app.get("/api/watchlist")
    def api_watchlist(conn: sqlite3.Connection = Depends(get_conn), min_score: float = 50, day: str | None = None):
        return {"items": watchlist(conn, cfg, day, min_score=min_score)}

    @app.get("/api/dca-candidates")
    def api_dca(conn: sqlite3.Connection = Depends(get_conn), day: str | None = None):
        return dca_candidates(conn, cfg, day)

    @app.get("/api/alerts")
    def api_alerts(conn: sqlite3.Connection = Depends(get_conn), limit: int = Query(100, ge=1, le=1000), kind: str | None = None):
        sql = "SELECT a.*, p.slug, p.name, p.symbol FROM alerts a LEFT JOIN projects p ON p.id=a.project_id"
        params: tuple = ()
        if kind:
            sql += " WHERE a.kind=?"
            params = (kind,)
        sql += " ORDER BY a.id DESC LIMIT ?"
        return {"items": [dict(r) for r in conn.execute(sql, (*params, limit))]}

    @app.post("/api/run", dependencies=[Depends(require_admin)])
    def api_run():
        if scheduler.running:
            return JSONResponse({"started": False, "reason": "már fut"}, status_code=409)
        threading.Thread(target=scheduler.run_now, name="screener-manual-run", daemon=True).start()
        return {"started": True}

    @app.get("/report", response_class=HTMLResponse)
    def report(conn: sqlite3.Connection = Depends(get_conn), day: str | None = None):
        return html_report(conn, cfg, day)

    @app.get("/", include_in_schema=False)
    @app.get("/project/{slug}", include_in_schema=False)
    def index(slug: str | None = None):
        return FileResponse(STATIC / "index.html")

    return app
