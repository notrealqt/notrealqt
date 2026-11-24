"""Regenerate the repo sections of README.md from repos.txt and the GitHub API.

Only repos listed in repos.txt are shown. Runs daily in GitHub Actions and
rewrites the text between the ACTIVE:START/END and REPOS:START/END markers.
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
LIST_FILE = ROOT / "repos.txt"

# section keyword in repos.txt -> heading, in display order
SECTIONS = {
    "research": "Research",
    "networking": "Networking & Infrastructure",
    "website": "Website",
    "coursework": "Coursework",
    "other": "Other Projects",
}


def api_get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


def load_list():
    """Read repos.txt and fetch each listed repo's details from GitHub."""
    repos = []
    for line in LIST_FILE.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        name, *rest = line.split()
        section = rest[0].lower() if rest else "other"
        if section not in SECTIONS:
            print(f"Unknown section '{section}' for {name}; using 'other'")
            section = "other"
        full_name = name if "/" in name else f"{USER}/{name}"
        try:
            r = api_get(f"https://api.github.com/repos/{full_name}")
        except Exception as e:  # private, renamed or deleted: skip it, keep going
            print(f"Skipping {full_name}: {e}")
            continue
        # your own repos show as just the name; others as owner/repo
        r["display"] = r["name"] if r["owner"]["login"].lower() == USER.lower() else r["full_name"]
        r["section"] = section
        r["active"] = "active" in (x.lower() for x in rest[1:])
        repos.append(r)
    return repos


def escape(text):
    return (text or "").replace("|", "\\|").replace("\n", " ").strip()


def build_active(repos):
    picks = [r for r in repos if r["active"]]
    if not picks:
        return "_Nothing here yet._"
    return "\n".join(
        f"- [**{r['display']}**]({r['html_url']})"
        + (f": {escape(r['description'])}" if r["description"] else "")
        for r in picks
    )


def build_section(title, repos):
    lines = [f"### {title}", "", "| Repository | Description | Language | Updated |", "|---|---|---|---|"]
    for r in sorted(repos, key=lambda r: r["pushed_at"], reverse=True):
        stars = f" ⭐ {r['stargazers_count']}" if r.get("stargazers_count") else ""
        homepage = f" · [demo]({r['homepage']})" if r.get("homepage") else ""
        lines.append(
            f"| [**{r['display']}**]({r['html_url']}){stars} "
            f"| {escape(r['description']) or '—'}{homepage} "
            f"| {r['language'] or '—'} | {r['pushed_at'][:10]} |"
        )
    return "\n".join(lines)


def build_index(repos):
    parts = []
    for key, title in SECTIONS.items():
        group = [r for r in repos if r["section"] == key]
        if group:
            parts.append(build_section(title, group))
    if not parts:
        parts.append("_No repositories listed yet._")
    parts.append(f"<sub>Last updated: {datetime.now(timezone.utc):%Y-%m-%d}</sub>")
    return "\n\n".join(parts)


def main():
    text = README.read_text(encoding="utf-8")
    repos = load_list()
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