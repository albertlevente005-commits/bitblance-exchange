from datetime import datetime

from screener.config import load_config
from screener.http import Http, HttpError
from screener.scheduler import DailyScheduler
from screener.sources.coingecko import parse_github_urls
from screener.telegram import _chunks


def test_http_retries_on_429_then_succeeds():
    seq = [(429, None, {"Retry-After": "1"}), (200, {"ok": 1}, {})]
    waits = []
    h = Http("t", transport=lambda u, p, hd: seq.pop(0), sleep=waits.append)
    assert h.get_json("https://x") == {"ok": 1} and waits == [1.0]


def test_http_raises_on_404_and_try_get_returns_none():
    h = Http("t", transport=lambda u, p, hd: (404, None, {}), sleep=lambda s: None)
    try:
        h.get_json("https://x")
        assert False
    except HttpError as e:
        assert e.status == 404
    assert h.try_get_json("https://x") is None


def test_parse_github_urls():
    assert parse_github_urls(["https://github.com/org/repo.git", "https://github.com/org", "https://gitlab.com/x", "https://github.com/org/repo"]) == ["org/repo", "org"]


def test_telegram_chunks_respect_limit():
    text = "\n".join("x" * 100 for _ in range(100))
    chunks = _chunks(text)
    assert len(chunks) > 1 and all(len(c) <= 3901 for c in chunks)


def test_scheduler_next_run():
    s = DailyScheduler("06:30", lambda: None)
    assert s.next_run(datetime(2026, 11, 4, 5, 0)) == datetime(2026, 11, 4, 6, 30)
    assert s.next_run(datetime(2026, 11, 4, 7, 0)) == datetime(2026, 11, 5, 6, 30)
    s.run_now()
    assert s.last_run is not None


def test_load_config_and_dotenv(tmp_path, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    (tmp_path / "config.toml").write_text('[weights]\nusage = 50\n[overrides.foo]\nexclude = true\n', encoding="utf-8")
    (tmp_path / ".env").write_text('TELEGRAM_BOT_TOKEN="abc"\n# comment\n', encoding="utf-8")
    cfg = load_config(tmp_path / "config.toml")
    assert cfg["weights"]["usage"] == 50 and cfg["weights"]["team"] == 20
    assert cfg.override("foo")["exclude"] is True and cfg.secrets.telegram_token == "abc"
    assert cfg.db_path == tmp_path / "screener.db"
