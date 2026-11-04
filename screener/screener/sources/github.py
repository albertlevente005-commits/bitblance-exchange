"""GitHub: commitok, kontribútorok, release-ek, utolsó push."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from ..http import Http, HttpError

log = logging.getLogger(__name__)

API = "https://api.github.com"


def _headers(token: str) -> dict:
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _since(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_repos(http: Http, refs: list[str], token: str = "", per_project: int = 3) -> list[str]:
    """'owner' hivatkozásokból a legutóbb pusholt repók; 'owner/repo' változatlanul marad."""
    repos: list[str] = []
    for ref in refs:
        if "/" in ref:
            if ref not in repos:
                repos.append(ref)
            continue
        for url in (f"{API}/orgs/{ref}/repos", f"{API}/users/{ref}/repos"):
            data = None
            try:
                data = http.get_json(url, params={"sort": "pushed", "per_page": per_project, "type": "public"}, headers=_headers(token))
            except HttpError as exc:
                if exc.status == 404:
                    continue
                log.warning("github: %s -> %s", url, exc)
                break
            for r in data or []:
                full = r.get("full_name")
                if full and not r.get("fork") and not r.get("archived") and full not in repos:
                    repos.append(full)
            break
        if len(repos) >= per_project * max(1, len(refs)):
            break
    return repos[: per_project * max(1, len(refs))]


def repo_stats(http: Http, full_name: str, token: str = "", window_days: int = 90) -> dict[str, Any] | None:
    hdr = _headers(token)
    meta = http.try_get_json(f"{API}/repos/{full_name}", headers=hdr)
    if not meta:
        return None
    since = _since(window_days)
    commits: list[dict] = []
    for page in (1, 2, 3):
        batch = http.try_get_json(
            f"{API}/repos/{full_name}/commits",
            params={"since": since, "per_page": 100, "page": page},
            headers=hdr,
        )
        if not batch:
            break
        commits.extend(batch)
        if len(batch) < 100:
            break
    authors = set()
    for c in commits:
        a = (c.get("author") or {}).get("login") or ((c.get("commit") or {}).get("author") or {}).get("email")
        if a:
            authors.add(a)
    releases = http.try_get_json(f"{API}/repos/{full_name}/releases", params={"per_page": 30}, headers=hdr) or []
    rel_90 = sum(1 for r in releases if (r.get("published_at") or "") >= since)
    contributors = http.try_get_json(f"{API}/repos/{full_name}/contributors", params={"per_page": 100}, headers=hdr) or []
    return {
        "repo": full_name,
        "stars": meta.get("stargazers_count"),
        "archived": bool(meta.get("archived")),
        "last_push": meta.get("pushed_at"),
        "commits_90d": len(commits),
        "authors_90d": authors,
        "contributors_total": len(contributors) if isinstance(contributors, list) else None,
        "releases_90d": rel_90,
    }


def project_dev_stats(http: Http, refs: list[str], token: str = "", per_project: int = 3) -> dict[str, Any] | None:
    """Projektszintű összesítés több repóból."""
    repos = resolve_repos(http, refs, token, per_project)
    if not repos:
        return None
    stats = [s for s in (repo_stats(http, r, token) for r in repos) if s]
    if not stats:
        return None
    authors: set = set()
    for s in stats:
        authors |= s["authors_90d"]
    last_push = max((s["last_push"] or "" for s in stats), default=None) or None
    return {
        "source": "github",
        "repos": [s["repo"] for s in stats],
        "stars": sum(s["stars"] or 0 for s in stats),
        "commits_90d": sum(s["commits_90d"] for s in stats),
        "contributors_90d": len(authors),
        "contributors_total": max((s["contributors_total"] or 0) for s in stats),
        "releases_90d": sum(s["releases_90d"] for s in stats),
        "last_push": last_push,
        "all_archived": all(s["archived"] for s in stats),
    }
