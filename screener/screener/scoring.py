"""Pontozási modell: valós használat, tokenomika, csapat/fejlesztés, likviditás, piros zászlók.

Minden kategória 0–100 pont. Egy kategórián belül az elérhető mutatók súlyozott átlaga
számít; a hiányzó adat nem büntet, de csökkenti a lefedettséget (coverage), amit
külön jelzünk. Az összpontszám a kategóriák súlyozott átlaga, a piros-zászló
kategória alacsony értéke esetén felülről korlátozva.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class ProjectData:
    """Minden, amit a pontozás a projektről tud. A None = nincs adat."""
    slug: str
    name: str = ""
    # használat
    tvl: float | None = None
    tvl_change_7d: float | None = None
    tvl_change_30d: float | None = None
    fees_30d: float | None = None
    fees_change_30d: float | None = None
    revenue_30d: float | None = None
    users_24h: float | None = None
    users_30d: float | None = None
    users_change_30d: float | None = None
    price_change_30d: float | None = None
    # tokenomika
    price: float | None = None
    mcap: float | None = None
    fdv: float | None = None
    circ_supply: float | None = None
    total_supply: float | None = None
    max_supply: float | None = None
    next_unlock_date: str | None = None
    next_unlock_amount: float | None = None
    unlocks_per_day: float | None = None
    # csapat / fejlesztés
    commits_90d: int | None = None
    contributors_90d: int | None = None
    releases_90d: int | None = None
    last_push: str | None = None
    audits: int | None = None
    defisafety_score: float | None = None  # PQR 0-100 %, 70 felett PASS
    # governance (Snapshot)
    gov_proposals_90d: int | None = None
    gov_avg_voters_90d: float | None = None
    gov_last_proposal_days: int | None = None
    # likviditás
    volume_24h: float | None = None
    exchanges: int | None = None
    avg_spread_pct: float | None = None
    # piros zászlók
    hacks: list[dict[str, Any]] = field(default_factory=list)  # {"day": ISO, "amount_usd": float}
    max_apy: float | None = None
    anonymous_team: bool | None = None
    concentrated_ownership: bool | None = None
    audited_override: bool | None = None
    today: date = field(default_factory=date.today)


@dataclass
class Score:
    total: float
    usage: float | None
    tokenomics: float | None
    team: float | None
    liquidity: float | None
    red_flags: float
    coverage: float
    flags: list[str]
    details: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": round(self.total, 1),
            "usage": None if self.usage is None else round(self.usage, 1),
            "tokenomics": None if self.tokenomics is None else round(self.tokenomics, 1),
            "team": None if self.team is None else round(self.team, 1),
            "liquidity": None if self.liquidity is None else round(self.liquidity, 1),
            "red_flags": round(self.red_flags, 1),
            "coverage": round(self.coverage, 2),
            "flags": self.flags,
            "details": self.details,
        }


# ---------- segédfüggvények ----------

def scale(x: float | None, lo: float, hi: float) -> float | None:
    """Lineáris leképezés [lo, hi] -> [0, 1], levágva. lo > hi esetén fordított irány."""
    if x is None:
        return None
    if lo == hi:
        return 1.0 if x >= hi else 0.0
    t = (x - lo) / (hi - lo)
    return max(0.0, min(1.0, t))


def log_scale(x: float | None, lo: float, hi: float) -> float | None:
    """Logaritmikus leképezés pozitív mennyiségekre (pl. forgalom, díjbevétel)."""
    if x is None:
        return None
    if x <= 0:
        return 0.0
    return scale(math.log10(x), math.log10(lo), math.log10(hi))


def weighted(parts: list[tuple[str, float | None, float]]) -> tuple[float | None, float, dict[str, float | None]]:
    """(név, 0..1 érték vagy None, súly) -> (0..100 pont, lefedettség, részletek)."""
    total_w = sum(w for _, _, w in parts)
    avail = [(n, v, w) for n, v, w in parts if v is not None]
    detail = {n: (None if v is None else round(v * 100, 1)) for n, v, _ in parts}
    if not avail:
        return None, 0.0, detail
    w_sum = sum(w for _, _, w in avail)
    score = sum(v * w for _, v, w in avail) / w_sum * 100.0
    return score, (w_sum / total_w if total_w else 0.0), detail


def days_between(day: str | None, ref: date) -> int | None:
    if not day:
        return None
    try:
        d = datetime.fromisoformat(day.replace("Z", "+00:00")).date() if "T" in day else date.fromisoformat(day[:10])
    except ValueError:
        return None
    return (d - ref).days


# ---------- kategóriák ----------

def score_usage(p: ProjectData) -> tuple[float | None, float, dict]:
    fee_yield = None
    if p.fees_30d is not None and p.tvl:
        fee_yield = p.fees_30d * 12 / p.tvl  # éves díj / TVL
    divergence = None
    fund = [v for v in (p.tvl_change_30d, p.fees_change_30d) if v is not None]
    if fund and p.price_change_30d is not None:
        divergence = sum(fund) / len(fund) - p.price_change_30d
    parts = [
        ("tvl_trend_30d", scale(p.tvl_change_30d, -30, 50), 25),
        ("tvl_trend_7d", scale(p.tvl_change_7d, -20, 20), 10),
        ("fees_30d", log_scale(p.fees_30d, 10_000, 10_000_000), 20),
        ("fees_trend_30d", scale(p.fees_change_30d, -40, 60), 15),
        ("fee_yield_on_tvl", scale(fee_yield, 0.0, 0.2), 10),
        ("users_24h", log_scale(p.users_24h, 100, 100_000), 10)
        if p.users_24h is not None or p.users_30d is None
        else ("users_30d", log_scale(p.users_30d, 1_000, 1_000_000), 10),
        ("revenue_30d", log_scale(p.revenue_30d, 10_000, 5_000_000), 5),
        ("users_trend_30d", scale(p.users_change_30d, -40, 60), 8),
        ("fundamentals_vs_price", scale(divergence, -80, 40), 10),
    ]
    return weighted(parts)


def circ_ratio(p: ProjectData) -> float | None:
    denom = p.max_supply or p.total_supply
    if p.circ_supply and denom:
        return p.circ_supply / denom
    if p.mcap and p.fdv:
        return p.mcap / p.fdv
    return None


def unlock_pct_of_mcap(p: ProjectData) -> tuple[float | None, int | None]:
    """(unlock értéke a mcap %-ában, napok a következő unlockig)."""
    days = days_between(p.next_unlock_date, p.today)
    if p.next_unlock_amount is None or not p.price or not p.mcap:
        return None, days
    return p.next_unlock_amount * p.price / p.mcap * 100.0, days


def score_tokenomics(p: ProjectData, horizon_days: int = 30) -> tuple[float | None, float, dict]:
    ratio = circ_ratio(p)
    pct, days = unlock_pct_of_mcap(p)
    unlock_score = None
    if pct is not None and days is not None:
        if days <= horizon_days:
            unlock_score = scale(-pct, -10, 0)  # 0% -> 1, >=10% -> 0
        else:
            unlock_score = 1.0 - 0.3 * scale(pct, 2, 10) * (1 - scale(days, horizon_days, 120))
    inflation = None
    if p.unlocks_per_day is not None and p.circ_supply:
        inflation = p.unlocks_per_day * 365 / p.circ_supply
    parts = [
        ("circulating_ratio", scale(ratio, 0.15, 0.9), 35),
        ("next_unlock", unlock_score, 30),
        ("annual_inflation", scale(-inflation if inflation is not None else None, -0.5, -0.02), 20),
        ("supply_cap", (1.0 if p.max_supply else 0.4) if (p.max_supply is not None or p.total_supply) else None, 15),
    ]
    return weighted(parts)


def score_team(p: ProjectData) -> tuple[float | None, float, dict]:
    push_age = days_between(p.last_push, p.today)
    audits = p.audits
    if p.audited_override is True and not audits:
        audits = 1
    parts = [
        ("commits_90d", log_scale(float(p.commits_90d) if p.commits_90d is not None else None, 5, 300), 30),
        ("active_contributors_90d", scale(p.contributors_90d, 1, 15), 25),
        ("last_push_recency", scale(push_age, -120, -7) if push_age is not None else None, 20),
        ("releases_90d", scale(p.releases_90d, 0, 4), 10),
        ("audits", scale(audits, 0, 2), 15),
        ("defisafety_pqr", scale(p.defisafety_score, 30, 95), 12),
        ("governance_proposals_90d", scale(p.gov_proposals_90d, 0, 6), 8),
        ("governance_voters_avg", log_scale(p.gov_avg_voters_90d, 10, 2_000) if p.gov_avg_voters_90d is not None else None, 7),
    ]
    return weighted(parts)


def score_liquidity(p: ProjectData) -> tuple[float | None, float, dict]:
    vol_ratio = (p.volume_24h / p.mcap) if (p.volume_24h is not None and p.mcap) else None
    parts = [
        ("volume_to_mcap", scale(vol_ratio, 0.005, 0.10), 35),
        ("volume_24h", log_scale(p.volume_24h, 100_000, 50_000_000), 30),
        ("market_cap", log_scale(p.mcap, 5_000_000, 1_000_000_000), 20),
        ("exchanges", scale(p.exchanges, 1, 10), 10),
        ("spread", scale(-p.avg_spread_pct, -2.0, -0.1) if p.avg_spread_pct is not None else None, 5),
    ]
    return weighted(parts)


def red_flags(p: ProjectData, cfg: dict[str, Any]) -> tuple[float, list[str], dict]:
    """Büntetőpontok 100-ból. Visszaadja a pontot, a zászlókat és a részleteket."""
    penalties: dict[str, int] = {}
    audited = (p.audits or 0) > 0 or p.audited_override is True
    if p.audited_override is False or (p.audits is not None and not audited):
        penalties["no_audit"] = 30
    elif p.audits is None and not audited:
        penalties["audit_unknown"] = 10
    if p.hacks:
        latest = max(h.get("day") or "" for h in p.hacks)
        age = days_between(latest, p.today)
        penalties["prior_exploit"] = 35 if (age is not None and age > -365) else 25
    pct, days = unlock_pct_of_mcap(p)
    if pct is not None and days is not None and 0 <= days <= cfg.get("unlock_horizon_days", 30) and pct >= cfg.get("unlock_pct_of_mcap", 5.0):
        penalties["unlock_shock"] = 20
    ratio = circ_ratio(p)
    if ratio is not None and ratio < 0.2:
        penalties["low_float"] = 15
    push_age = days_between(p.last_push, p.today)
    if (push_age is not None and -push_age > cfg.get("dev_stalled_days", 90)) or (p.commits_90d == 0):
        penalties["dev_stalled"] = 20
    if p.max_apy is not None and p.max_apy >= cfg.get("extreme_apy", 100.0):
        penalties["extreme_yield"] = 25 if p.max_apy >= 5 * cfg.get("extreme_apy", 100.0) else 15
    if p.volume_24h is not None and p.mcap and p.volume_24h / p.mcap > 1.5:
        penalties["wash_trade_suspect"] = 10
    if p.tvl_change_7d is not None and p.tvl_change_7d <= -30:
        penalties["tvl_collapse"] = 15
    if p.defisafety_score is not None and p.defisafety_score < cfg.get("defisafety_fail_below", 70.0):
        penalties["defisafety_fail"] = 15 if p.defisafety_score >= 50 else 25
    if p.anonymous_team:
        penalties["anonymous_team"] = 20
    if p.concentrated_ownership:
        penalties["concentrated_ownership"] = 20
    if p.mcap is not None and p.mcap < 2_000_000:
        penalties["micro_cap"] = 10
    score = max(0.0, 100.0 - sum(penalties.values()))
    return score, sorted(penalties), {"penalties": penalties}


# ---------- összesítés ----------

def score_project(p: ProjectData, weights: dict[str, float], scoring_cfg: dict[str, Any]) -> Score:
    usage, cov_u, d_u = score_usage(p)
    tok, cov_t, d_t = score_tokenomics(p, int(scoring_cfg.get("unlock_horizon_days", 30)))
    team, cov_m, d_m = score_team(p)
    liq, cov_l, d_l = score_liquidity(p)
    rf, flags, d_r = red_flags(p, scoring_cfg)

    cats = [
        ("usage", usage, cov_u, float(weights.get("usage", 30))),
        ("tokenomics", tok, cov_t, float(weights.get("tokenomics", 20))),
        ("team", team, cov_m, float(weights.get("team", 20))),
        ("liquidity", liq, cov_l, float(weights.get("liquidity", 15))),
        ("red_flags", rf, 1.0, float(weights.get("red_flags", 15))),
    ]
    avail = [(s, w) for _, s, _, w in cats if s is not None]
    total = sum(s * w for s, w in avail) / sum(w for _, w in avail) if avail else 0.0
    total_w = sum(w for *_, w in cats)
    coverage = sum(c * w for _, _, c, w in cats) / total_w if total_w else 0.0

    capped = False
    if rf < float(scoring_cfg.get("red_flag_floor", 30)):
        cap = float(scoring_cfg.get("red_flag_cap_total", 45))
        if total > cap:
            total, capped = cap, True
    # kevés adat -> ne tűnjön magabiztosnak: 40% lefedettség alatt arányosan húzzuk a középhez
    if coverage < 0.4:
        total = 50 + (total - 50) * max(0.0, coverage / 0.4)
        flags = [*flags, "low_data_coverage"]

    details = {
        "usage": d_u, "tokenomics": d_t, "team": d_m, "liquidity": d_l, "red_flags": d_r,
        "capped_by_red_flags": capped,
        "coverage": {"usage": round(cov_u, 2), "tokenomics": round(cov_t, 2), "team": round(cov_m, 2), "liquidity": round(cov_l, 2)},
    }
    return Score(total, usage, tok, team, liq, rf, coverage, flags, details)
