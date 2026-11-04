"""Parancssori felület."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from . import db
from .alerts import generate_alerts, store_alerts
from .config import load_config
from .export import dca_candidates, html_report, ranking, watchlist, write_json
from .pipeline import Clients, fetch_all, score_all
from .scheduler import run_daily, wait_loop
from .telegram import send_message, send_pending_alerts


def _fmt_usd(v):
    if v is None:
        return "–"
    return f"${v/1e9:.2f}B" if v >= 1e9 else (f"${v/1e6:.1f}M" if v >= 1e6 else f"${v/1e3:.0f}k")


def _print_table(rows: list[dict]) -> None:
    if not rows:
        print("Nincs adat. Futtasd előbb: screener fetch && screener score")
        return
    print(f"{'#':>3} {'Projekt':<28} {'Szimb':<7} {'Pont':>5} {'Haszn':>5} {'Tok':>5} {'Csap':>5} {'Likv':>5} {'Zászl':>5} {'TVL':>9} {'Mcap':>9} {'Lefed':>5}  Zászlók")
    for i, r in enumerate(rows, 1):
        def n(v):
            return "–" if v is None else f"{v:.0f}"
        print(
            f"{i:>3} {r['name'][:28]:<28} {(r['symbol'] or '')[:7]:<7} {r['score']:>5.0f} {n(r['usage']):>5} {n(r['tokenomics']):>5} "
            f"{n(r['team']):>5} {n(r['liquidity']):>5} {n(r['red_flags']):>5} {_fmt_usd(r['tvl']):>9} {_fmt_usd(r['mcap']):>9} "
            f"{(r['coverage'] or 0)*100:>4.0f}%  {', '.join(r['flags'])}"
        )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="screener", description="Adatvezérelt kripto projekt-szűrő és -figyelő")
    ap.add_argument("-c", "--config", default="config.toml", help="config.toml útvonala")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="Adatbázis és kimeneti mappa létrehozása")
    f = sub.add_parser("fetch", help="Adatok lekérése (DefiLlama, CoinGecko, GitHub)")
    f.add_argument("--skip-github", action="store_true")
    f.add_argument("--skip-details", action="store_true", help="CoinGecko részletlekérések kihagyása")
    sub.add_parser("score", help="Pontozás a mai pillanatképből")
    r = sub.add_parser("rank", help="Rangsor kiírása")
    r.add_argument("--top", type=int, default=25)
    r.add_argument("--category")
    r.add_argument("--json", action="store_true")
    w = sub.add_parser("watchlist", help="Korai projektek figyelőlistája")
    w.add_argument("--min-score", type=float, default=50)
    w.add_argument("--json", action="store_true")
    a = sub.add_parser("alerts", help="Riasztások generálása (és küldése)")
    a.add_argument("--send", action="store_true", help="Küldés Telegramra")
    e = sub.add_parser("export-dca", help="DCA-jelöltek JSON exportja az OKX bot számára")
    e.add_argument("--out", help="Fájl (alapért.: out/dca_candidates.json)")
    rp = sub.add_parser("report", help="HTML-jelentés generálása")
    rp.add_argument("--out", help="Fájl (alapért.: out/report.html)")
    rd = sub.add_parser("run-daily", help="Teljes napi kör: fetch, score, alerts, export, Telegram")
    rd.add_argument("--no-send", action="store_true")
    rd.add_argument("--skip-github", action="store_true")
    rd.add_argument("--skip-details", action="store_true")
    dm = sub.add_parser("daemon", help="Minden nap adott időpontban futtatja a napi kört")
    dm.add_argument("--at", default="06:00", help="HH:MM helyi idő")
    dm.add_argument("--no-send", action="store_true")
    t = sub.add_parser("telegram-test", help="Teszüzenet küldése")
    t.add_argument("--text", default="✅ Kripto szűrő: a Telegram-kapcsolat működik.")
    sv = sub.add_parser("serve", help="Webes platform (API + dashboard) indítása")
    sv.add_argument("--host", default="0.0.0.0")
    sv.add_argument("--port", type=int, default=8080)
    sv.add_argument("--no-scheduler", action="store_true", help="Ne induljon a napi ütemező a szerverrel")

    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stderr)
    cfg = load_config(args.config)

    if args.cmd == "init":
        db.connect(cfg.db_path).close()
        cfg.out_dir.mkdir(parents=True, exist_ok=True)
        print(f"Adatbázis: {cfg.db_path}\nKimenet: {cfg.out_dir}")
        return 0

    if args.cmd == "serve":
        import uvicorn
        from .web import create_app
        app = create_app(cfg, scheduler_enabled=not args.no_scheduler)
        uvicorn.run(app, host=args.host, port=args.port, log_level="debug" if args.verbose else "info")
        return 0

    if args.cmd == "run-daily":
        res = run_daily(cfg, send=not args.no_send, skip_github=args.skip_github, skip_details=args.skip_details)
        print(json.dumps(res, ensure_ascii=False))
        return 0

    if args.cmd == "daemon":
        wait_loop(cfg, args.at, send=not args.no_send)
        return 0

    clients = Clients(cfg)
    conn = db.connect(cfg.db_path)
    try:
        if args.cmd == "fetch":
            print(json.dumps(fetch_all(conn, cfg, clients, skip_github=args.skip_github, skip_details=args.skip_details), ensure_ascii=False))
        elif args.cmd == "score":
            print(f"Pontozva: {score_all(conn, cfg)} projekt")
        elif args.cmd == "rank":
            rows = ranking(conn, top=args.top, category=args.category)
            print(json.dumps(rows, ensure_ascii=False, indent=2)) if args.json else _print_table(rows)
        elif args.cmd == "watchlist":
            rows = watchlist(conn, cfg, min_score=args.min_score)
            print(json.dumps(rows, ensure_ascii=False, indent=2)) if args.json else _print_table(rows)
        elif args.cmd == "alerts":
            new = store_alerts(conn, generate_alerts(conn, cfg))
            pending = db.unsent_alerts(conn)
            print(f"Új riasztás: {new}, küldetlen: {len(pending)}")
            for row in pending:
                print(f"  [{row['severity']}] {row['message']}")
            if args.send:
                print(f"Elküldve: {send_pending_alerts(conn, clients.telegram, cfg.secrets.telegram_token, cfg.secrets.telegram_chat_id)}")
        elif args.cmd == "export-dca":
            path = Path(args.out) if args.out else cfg.out_dir / "dca_candidates.json"
            data = dca_candidates(conn, cfg)
            write_json(path, data)
            print(f"{len(data['candidates'])} jelölt -> {path}")
        elif args.cmd == "report":
            path = Path(args.out) if args.out else cfg.out_dir / "report.html"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(html_report(conn, cfg), encoding="utf-8")
            print(f"Jelentés -> {path}")
        elif args.cmd == "telegram-test":
            ok = send_message(clients.telegram, cfg.secrets.telegram_token, cfg.secrets.telegram_chat_id, args.text)
            print("OK" if ok else "Sikertelen (lásd a logot)")
            return 0 if ok else 1
    finally:
        conn.close()
    return 0
