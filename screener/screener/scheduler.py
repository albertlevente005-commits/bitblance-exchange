"""Napi futtatás: egyszeri 'run-daily' lépéssor és háttérszálas ütemező a webes platformhoz."""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Callable

from . import db
from .alerts import generate_alerts, store_alerts
from .config import Config
from .export import dca_candidates, html_report, write_json
from .pipeline import Clients, fetch_all, score_all
from .telegram import send_pending_alerts

log = logging.getLogger(__name__)


def run_daily(cfg: Config, clients: Clients | None = None, send: bool = True, skip_github: bool = False, skip_details: bool = False) -> dict[str, Any]:
    """Teljes napi kör: lekérés -> pontozás -> riasztások -> exportok -> Telegram."""
    clients = clients or Clients(cfg)
    conn = db.connect(cfg.db_path)
    try:
        day = db.today()
        stats = fetch_all(conn, cfg, clients, day, skip_github=skip_github, skip_details=skip_details)
        scored = score_all(conn, cfg, day)
        new_alerts = store_alerts(conn, generate_alerts(conn, cfg, day))
        out = cfg.out_dir
        write_json(out / "dca_candidates.json", dca_candidates(conn, cfg, day))
        (out / "report.html").write_text(html_report(conn, cfg, day), encoding="utf-8")
        sent = 0
        if send:
            sent = send_pending_alerts(
                conn, clients.telegram, cfg.secrets.telegram_token, cfg.secrets.telegram_chat_id,
                int(cfg["alerts"].get("max_alerts_per_run", 25)),
            )
        result = {"day": day, **stats, "scored": scored, "new_alerts": new_alerts, "sent": sent}
        log.info("Napi futás kész: %s", result)
        return result
    finally:
        conn.close()


class DailyScheduler:
    """Egyszerű háttérszál: minden nap a megadott időpontban (HH:MM, helyi idő) lefuttatja a job-ot."""

    def __init__(self, run_at: str, job: Callable[[], Any], tick: float = 30.0):
        self.run_at = run_at
        self.job = job
        self.tick = tick
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_run: datetime | None = None
        self.last_result: Any = None
        self.running = False

    def next_run(self, now: datetime | None = None) -> datetime:
        now = now or datetime.now()
        hh, mm = (int(x) for x in self.run_at.split(":"))
        nxt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if nxt <= now:
            nxt += timedelta(days=1)
        return nxt

    def run_now(self) -> Any:
        if self.running:
            return {"error": "már fut"}
        self.running = True
        try:
            self.last_result = self.job()
            self.last_run = datetime.now()
            return self.last_result
        except Exception as exc:  # a platform ne álljon le egy hibás futás miatt
            log.exception("Ütemezett futás hiba")
            self.last_result = {"error": str(exc)}
            return self.last_result
        finally:
            self.running = False

    def _loop(self) -> None:
        target = self.next_run()
        log.info("Ütemező indul, következő futás: %s", target)
        while not self._stop.is_set():
            if datetime.now() >= target:
                self.run_now()
                target = self.next_run()
                log.info("Következő futás: %s", target)
            self._stop.wait(self.tick)

    def start(self) -> None:
        if self._thread:
            return
        self._thread = threading.Thread(target=self._loop, name="screener-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()


def wait_loop(cfg: Config, run_at: str, send: bool = True) -> None:
    """CLI 'daemon' mód: blokkoló ütemező."""
    sched = DailyScheduler(run_at, lambda: run_daily(cfg, send=send))
    sched.start()
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        sched.stop()
