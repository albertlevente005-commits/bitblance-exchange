"""Telegram Bot API: üzenetküldés darabolással."""
from __future__ import annotations

import logging
import sqlite3

from . import db
from .http import Http, HttpError

log = logging.getLogger(__name__)
MAX_LEN = 3900


def send_message(http: Http, token: str, chat_id: str, text: str) -> bool:
    if not token or not chat_id:
        log.warning("Telegram: hiányzik a TELEGRAM_BOT_TOKEN vagy TELEGRAM_CHAT_ID, nem küldök.")
        return False
    ok = True
    for chunk in _chunks(text):
        try:
            http.get_json(
                f"https://api.telegram.org/bot{token}/sendMessage",
                params={"chat_id": chat_id, "text": chunk, "parse_mode": "HTML", "disable_web_page_preview": "true"},
            )
        except HttpError as exc:
            log.error("Telegram küldés sikertelen: %s %s", exc, exc.body)
            ok = False
    return ok


def _chunks(text: str) -> list[str]:
    out, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > MAX_LEN and cur:
            out.append(cur)
            cur = ""
        cur += (line + "\n")
    if cur.strip():
        out.append(cur)
    return out or [text[:MAX_LEN]]


def send_pending_alerts(conn: sqlite3.Connection, http: Http, token: str, chat_id: str, max_alerts: int = 25) -> int:
    rows = db.unsent_alerts(conn)
    if not rows:
        return 0
    rows = rows[:max_alerts]
    order = {"crit": 0, "warn": 1, "info": 2}
    rows = sorted(rows, key=lambda r: order.get(r["severity"], 9))
    text = "<b>Kripto szűrő – riasztások</b>\n\n" + "\n".join(r["message"] for r in rows)
    text += "\n\n<i>Döntéstámogatás, nem pénzügyi tanács. Kis projekteknél a teljes veszteség is lehetséges.</i>"
    if send_message(http, token, chat_id, text):
        db.mark_alerts_sent(conn, [r["id"] for r in rows])
        conn.commit()
        return len(rows)
    return 0
