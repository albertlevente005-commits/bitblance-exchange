from datetime import date

from screener.scoring import ProjectData, log_scale, red_flags, scale, score_project, weighted

W = {"usage": 30, "tokenomics": 20, "team": 20, "liquidity": 15, "red_flags": 15}
T = date(2026, 11, 4)


def test_scale_and_log_scale_clamp():
    assert scale(None, 0, 1) is None
    assert scale(-5, 0, 10) == 0.0
    assert scale(5, 0, 10) == 0.5
    assert scale(50, 0, 10) == 1.0
    assert scale(-10, -20, 0) == 0.5          # fordított tartomány is működik
    assert log_scale(0, 10, 1000) == 0.0
    assert abs(log_scale(100, 10, 1000) - 0.5) < 1e-9


def test_weighted_ignores_missing_but_reports_coverage():
    score, cov, _ = weighted([("a", 1.0, 50), ("b", None, 50)])
    assert score == 100.0 and cov == 0.5
    score, cov, _ = weighted([("a", None, 1)])
    assert score is None and cov == 0.0


def strong() -> ProjectData:
    return ProjectData(
        slug="s", tvl=5e8, tvl_change_7d=3, tvl_change_30d=12, fees_30d=4e6, fees_change_30d=10, users_24h=20000,
        price_change_30d=5, price=1, mcap=4e8, fdv=6e8, circ_supply=4e8, total_supply=6e8, max_supply=1e9,
        next_unlock_date="2026-12-20", next_unlock_amount=2e6, unlocks_per_day=100000, commits_90d=200,
        contributors_90d=12, releases_90d=3, last_push="2026-11-02T10:00:00Z", audits=3, volume_24h=3e7,
        exchanges=12, avg_spread_pct=0.3, revenue_30d=2e6, users_change_30d=12, gov_proposals_90d=5, gov_avg_voters_90d=600, today=T,
    )


def test_strong_project_scores_high_with_full_coverage():
    s = score_project(strong(), W, {})
    assert s.total >= 75 and s.coverage == 1.0 and s.flags == [] and s.red_flags == 100


def test_red_flags_and_cap():
    p = ProjectData(
        slug="b", tvl=3e6, tvl_change_7d=-40, mcap=1.5e6, price=0.1, circ_supply=1e7, total_supply=1e8, volume_24h=5e6,
        audits=0, hacks=[{"day": "2026-05-01"}], max_apy=800, commits_90d=0, today=T,
    )
    s = score_project(p, W, {})
    for f in ("no_audit", "prior_exploit", "extreme_yield", "low_float", "tvl_collapse", "wash_trade_suspect", "dev_stalled", "micro_cap"):
        assert f in s.flags
    assert s.red_flags == 0
    assert s.total <= 45  # piros zászlók miatt korlátozva


def test_unlock_shock_only_inside_horizon():
    p = strong()
    p.next_unlock_date = "2026-11-15"
    p.next_unlock_amount = 40e6  # 40M * $1 = a 400M mcap 10%-a
    rf, flags, _ = red_flags(p, {"unlock_horizon_days": 30, "unlock_pct_of_mcap": 5.0})
    assert "unlock_shock" in flags
    p.next_unlock_date = "2027-03-01"
    rf, flags, _ = red_flags(p, {"unlock_horizon_days": 30, "unlock_pct_of_mcap": 5.0})
    assert "unlock_shock" not in flags


def test_price_pumps_without_fundamentals_is_penalised():
    good = strong()
    pumped = strong()
    pumped.price_change_30d = 150
    pumped.tvl_change_30d = -10
    pumped.fees_change_30d = -20
    assert score_project(pumped, W, {}).usage < score_project(good, W, {}).usage - 15


def test_low_coverage_pulls_towards_middle_and_flags():
    p = ProjectData(slug="x", tvl=1e7, tvl_change_7d=5, today=T)
    s = score_project(p, W, {})
    assert "low_data_coverage" in s.flags
    assert 30 <= s.total <= 70


def test_manual_overrides():
    p = strong()
    p.anonymous_team = True
    p.concentrated_ownership = True
    p.audits = 0
    p.audited_override = True   # kézi: auditált
    rf, flags, _ = red_flags(p, {})
    assert "anonymous_team" in flags and "concentrated_ownership" in flags and "no_audit" not in flags
