"""Snapshot governance: javaslatok, szavazók, követők egy space-hez.

Hub API (GraphQL, kulcs nélkül): https://hub.snapshot.org/graphql
Space-feloldás sorrendje: kézi felülírás -> DefiLlama governanceID ("snapshot:xyz.eth")
-> tippek a slug/név/szimbólum alapján (xyz.eth, xyzdao.eth, gov.xyz.eth ...).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from ..http import Http

log = logging.getLogger(__name__)

HUB = "https://hub.snapshot.org/graphql"

SPACES_QUERY = """query Spaces($ids: [String]) {
  spaces(first: 20, where: { id_in: $ids }) { id name followersCount proposalsCount verified }
}"""

PROPOSALS_QUERY = """query Proposals($space: String, $since: Int) {
  proposals(first: 100, skip: 0, where: { space: $space, created_gt: $since }, orderBy: "created", orderDirection: desc) {
    id title state created end votes scores_total
  }
}"""


def _gql(http: Http, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    raw = http.try_post_json(HUB, json={"query": query, "variables": variables})
    if not raw or raw.get("errors"):
        if raw and raw.get("errors"):
            log.warning("snapshot: %s", raw["errors"][:1])
        return {}
    return raw.get("data") or {}


def spaces_from_governance_ids(gov_ids: list[str] | None) -> list[str]:
    """DefiLlama governanceID mezőből a snapshot space-ek."""
    out = []
    for g in gov_ids or []:
        if isinstance(g, str) and g.lower().startswith("snapshot:"):
            out.append(g.split(":", 1)[1].strip().lower())
    return out


def guess_candidates(slug: str, name: str | None, symbol: str | None) -> list[str]:
    """Space-tippek prioritási sorrendben: slug, név, a név/slug első szava, szimbólum."""
    bases: list[str] = []

    def add(v: str | None) -> None:
        v = re.sub(r"[^a-z0-9-]", "", (v or "").lower()).strip("-")
        if len(v) >= 3 and v not in bases:
            bases.append(v)

    add(slug)
    if name:
        add(name.lower().replace(" ", "-"))
        add(re.sub(r"\s+", "", name.lower()))
    add((slug or "").split("-")[0])
    if name:
        add(name.lower().split()[0] if name.split() else None)
    add(symbol)
    out: list[str] = []
    for b in bases:
        for pat in ("{}.eth", "{}dao.eth", "{}-dao.eth", "gov.{}.eth", "{}gov.eth", "{}governance.eth", "vote.{}.eth"):
            cand = pat.format(b)
            if cand not in out:
                out.append(cand)
    return out[:35]


def resolve_space(http: Http, candidates: list[str]) -> dict[str, Any] | None:
    """A jelöltek közül a legtöbb javaslattal bíró létező space."""
    if not candidates:
        return None
    data = _gql(http, SPACES_QUERY, {"ids": candidates})
    spaces = [s for s in data.get("spaces", []) if s and s.get("id")]
    if not spaces:
        return None
    spaces.sort(key=lambda s: (int(s.get("proposalsCount") or 0), int(s.get("followersCount") or 0)), reverse=True)
    best = spaces[0]
    if int(best.get("proposalsCount") or 0) == 0:
        return None
    return best


def space_stats(http: Http, space_id: str, days: int = 90, now: datetime | None = None) -> dict[str, Any] | None:
    """Governance-aktivitás az elmúlt `days` napban."""
    now = now or datetime.now(timezone.utc)
    since = int((now - timedelta(days=days)).timestamp())
    meta = _gql(http, SPACES_QUERY, {"ids": [space_id]}).get("spaces") or []
    props = _gql(http, PROPOSALS_QUERY, {"space": space_id, "since": since}).get("proposals") or []
    if not meta and not props:
        return None
    votes = [int(p.get("votes") or 0) for p in props]
    last_created = max((int(p.get("created") or 0) for p in props), default=0)
    space = meta[0] if meta else {}
    return {
        "space": space_id,
        "space_name": space.get("name"),
        "followers": int(space.get("followersCount") or 0) if space else None,
        "proposals_total": int(space.get("proposalsCount") or 0) if space else None,
        "proposals_90d": len(props),
        "avg_voters_90d": (sum(votes) / len(votes)) if votes else 0.0,
        "max_voters_90d": max(votes) if votes else 0,
        "active_proposals": sum(1 for p in props if p.get("state") == "active"),
        "last_proposal_days": (int((now.timestamp() - last_created) // 86400) if last_created else None),
    }
