"""Konfiguráció betöltése: config.toml + .env (titkok)."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    "general": {
        "db_path": "screener.db",
        "out_dir": "out",
        "defillama_min_interval": 0.25,
        "coingecko_min_interval": 2.5,
        "github_min_interval": 0.5,
    },
    "universe": {
        "min_tvl_usd": 2_000_000,
        "top_n_by_tvl": 300,
        "exclude_categories": ["CEX", "Chain"],
        "early_days": 60,
        "coingecko_details_limit": 40,
        "details_refresh_days": 7,
        "github_projects_limit": 30,
        "github_repos_per_project": 3,
        "tvl_history_limit": 150,
        "always_include": [],
    },
    "weights": {"usage": 30, "tokenomics": 20, "team": 20, "liquidity": 15, "red_flags": 15},
    "scoring": {
        "red_flag_floor": 30,
        "red_flag_cap_total": 45,
        "unlock_horizon_days": 30,
        "unlock_pct_of_mcap": 5.0,
        "dev_stalled_days": 90,
        "extreme_apy": 100.0,
        "extreme_apy_min_pool_tvl": 100_000,
        "defisafety_fail_below": 70.0,
    },
    "alerts": {
        "tvl_drop_7d_pct": -25.0,
        "tvl_drop_1d_pct": -15.0,
        "unlock_days_ahead": 14,
        "new_project_min_score": 60,
        "score_jump_points": 15,
        "max_alerts_per_run": 25,
    },
    "dca": {
        "min_score": 70,
        "min_liquidity_score": 50,
        "min_red_flag_score": 60,
        "min_mcap_usd": 20_000_000,
        "max_candidates": 15,
    },
    "dune": {"enabled": False, "max_age_hours": 36, "execute_if_stale": False, "queries": []},
    "snapshot": {"enabled": True, "projects_limit": 80, "window_days": 90, "min_interval": 1.0},
    "defisafety": {"enabled": True, "api_url": "https://api.defisafety.com/api/pqrs", "page_size": 100, "max_pages": 10, "html_fallback": True, "min_interval": 1.0, "ids": {}},
    "tokenterminal": {"enabled": False, "mode": "bulk", "window_days": 30, "projects_limit": 100, "min_interval": 0.5, "metrics": {}, "project_ids": {}},
    "overrides": {},
}


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_dotenv(path: Path) -> None:
    """Egyszerű .env betöltő, külső függőség nélkül. Nem írja felül a meglévő env-et."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


@dataclass
class Secrets:
    telegram_token: str = ""
    telegram_chat_id: str = ""
    coingecko_api_key: str = ""
    github_token: str = ""
    dune_api_key: str = ""
    tokenterminal_api_key: str = ""

    @classmethod
    def from_env(cls) -> "Secrets":
        return cls(
            telegram_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
            coingecko_api_key=os.environ.get("COINGECKO_API_KEY", ""),
            github_token=os.environ.get("GITHUB_TOKEN", ""),
            dune_api_key=os.environ.get("DUNE_API_KEY", ""),
            tokenterminal_api_key=os.environ.get("TOKENTERMINAL_API_KEY", ""),
        )


@dataclass
class Config:
    data: dict[str, Any]
    base_dir: Path
    secrets: Secrets = field(default_factory=Secrets)

    def __getitem__(self, section: str) -> dict[str, Any]:
        return self.data[section]

    @property
    def db_path(self) -> Path:
        p = Path(self.data["general"]["db_path"])
        return p if p.is_absolute() else self.base_dir / p

    @property
    def out_dir(self) -> Path:
        p = Path(self.data["general"]["out_dir"])
        return p if p.is_absolute() else self.base_dir / p

    def override(self, slug: str) -> dict[str, Any]:
        return self.data.get("overrides", {}).get(slug, {}) or {}


def load_config(path: str | Path | None = None, env_file: str | Path | None = None) -> Config:
    cfg_path = Path(path) if path else Path("config.toml")
    base_dir = cfg_path.parent.resolve() if cfg_path.exists() else Path.cwd()
    data = _merge(DEFAULTS, {})
    if cfg_path.exists():
        with open(cfg_path, "rb") as fh:
            data = _merge(DEFAULTS, tomllib.load(fh))
    load_dotenv(Path(env_file) if env_file else base_dir / ".env")
    # Környezeti felülírások (Docker/compose): SCREENER_DB_PATH, SCREENER_OUT_DIR
    if os.environ.get("SCREENER_DB_PATH"):
        data["general"]["db_path"] = os.environ["SCREENER_DB_PATH"]
    if os.environ.get("SCREENER_OUT_DIR"):
        data["general"]["out_dir"] = os.environ["SCREENER_OUT_DIR"]
    return Config(data=data, base_dir=base_dir, secrets=Secrets.from_env())
