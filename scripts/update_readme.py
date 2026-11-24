"""Regenerate the repo sections of README.md from the GitHub API.

Runs daily in GitHub Actions. Rewrites the text between the
ACTIVE:START/END and REPOS:START/END markers in README.md.
"""

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

USER = os.environ.get("GITHUB_REPOSITORY_OWNER", "notrealqt")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
EXTRA_FILE = ROOT / "extra-repos.txt"

# topic -> section title, in display order
SECTIONS = {
    "research": "Research",
    "networking": "Networking & Infrastructure",
    "website": "Website",
    "coursework": "Coursework",
}
OTHER = "Other Projects"


def api_get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


def fetch_own():
    """All public repos you own, minus forks, archived repos and this profile repo."""
    repos, page = [], 1
    while True:
        batch = api_get(f"https://api.github.com/users/{USER}/repos?per_page=100&page={page}&type=owner")
        if not batch:
            break
        repos.extend(batch)
        page += 1
    return [r for r in repos if not (r["fork"] or r["archived"] or r["name"].lower() == USER.lower())]


def fetch_extra():
    """Repos from other accounts listed in extra-repos.txt as `owner/repo [topic]`."""
    if not EXTRA_FILE.exists():
        return []
    repos = []
    for line in EXTRA_FILE.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        full_name, *topic = line.split()
        try:
            r = api_get(f"https://api.github.com/repos/{full_name}")
        except Exception as e:  # private, renamed or deleted: skip it, keep going
            print(f"Skipping {full_name}: {e}")
            continue
        r["name"] = r["full_name"]  # show owner/repo so it's clear it isn't yours
        if topic:
            r["topics"] = [topic[0]]
        repos.append(r)
    return repos


def escape(text):
    return (text or "").replace("|", "\\|").replace("\n", " ").strip()


def build_active(repos, limit=4):
    """Repos tagged `active`; if none are tagged, the most recently pushed ones."""
    tagged = [r for r in repos if "active" in r.get("topics", [])]
    picks = tagged or sorted(repos, key=lambda r: r["pushed_at"], reverse=True)[:limit]
    if not picks:
        return "_Nothing here yet._"
    return "\n".join(
        f"- [**{r['name']}**]({r['html_url']}): {escape(r['description']) or 'No description yet'}"
        for r in picks
    )


def build_section(title, repos):
    lines = [f"### {title}", "", "| Repository | Description | Language | Updated |", "|---|---|---|---|"]
    for r in sorted(repos, key=lambda r: r["pushed_at"], reverse=True):
        stars = f" ⭐ {r['stargazers_count']}" if r.get("stargazers_count") else ""
        homepage = f" · [demo]({r['homepage']})" if r.get("homepage") else ""
        lines.append(
            f"| [**{r['name']}**]({r['html_url']}){stars} "
            f"| {escape(r['description']) or '—'}{homepage} "
            f"| {r['language'] or '—'} | {r['pushed_at'][:10]} |"
        )
    return "\n".join(lines)


def build_index(repos):
    groups = {title: [] for title in [*SECTIONS.values(), OTHER]}
    for r in repos:
        topics = r.get("topics", [])
        title = next((t for topic, t in SECTIONS.items() if topic in topics), OTHER)
        groups[title].append(r)
    parts = [build_section(t, rs) for t, rs in groups.items() if rs]
    parts.append(f"<sub>Last updated: {datetime.now(timezone.utc):%Y-%m-%d}</sub>")
    return "\n\n".join(parts)


def main():
    text = README.read_text(encoding="utf-8")
    repos = fetch_own() + fetch_extra()
    for name, body in {"ACTIVE": build_active(repos), "REPOS": build_index(repos)}.items():
        start, end = f"<!-- {name}:START -->", f"<!-- {name}:END -->"
        if start not in text or end not in text:
            sys.exit(f"README.md is missing the {start} / {end} markers")
        text = re.sub(
            re.escape(start) + r".*?" + re.escape(end),
            lambda _: f"{start}\n{body}\n{end}",
            text,
            flags=re.S,
        )
    README.write_text(text, encoding="utf-8")
    print("README updated.")


if __name__ == "__main__":
    main()