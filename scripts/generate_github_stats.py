#!/usr/bin/env python3
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.sax.saxutils as xml


USERNAME = os.getenv("GITHUB_USERNAME", "michaeld3n")
TOKEN = os.getenv("GH_STATS_TOKEN") or os.getenv("GITHUB_TOKEN")
OUT_DIR = os.getenv("GITHUB_STATS_OUT_DIR", "assets")
API_VERSION = "2022-11-28"

BG = "#0d1117"
PANEL = "#161b22"
BORDER = "#30363d"
TEXT = "#c9d1d9"
MUTED = "#8b949e"
BLUE = "#58a6ff"
GREEN = "#3fb950"
ORANGE = "#d29922"
PURPLE = "#bc8cff"


def request_json(url, method="GET", data=None):
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": f"{USERNAME}-profile-stats",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API error {err.code} for {url}: {detail}") from err


def graphql(query, variables):
    return request_json(
        "https://api.github.com/graphql",
        method="POST",
        data={"query": query, "variables": variables},
    )


def esc(value):
    return xml.escape(str(value), {'"': "&quot;"})


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        file.write(content)


def svg_shell(width, height, title, body):
    return f"""<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="title desc">
  <title id="title">{esc(title)}</title>
  <desc id="desc">Auto-generated GitHub profile statistics for {esc(USERNAME)}.</desc>
  <style>
    .title {{ fill: {TEXT}; font: 600 18px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .label {{ fill: {MUTED}; font: 500 12px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .value {{ fill: {TEXT}; font: 700 24px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .small {{ fill: {MUTED}; font: 500 11px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
  </style>
  <rect width="{width}" height="{height}" rx="8" fill="{BG}"/>
  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="7.5" stroke="{BORDER}"/>
  <text x="24" y="34" class="title">{esc(title)}</text>
{body}
</svg>
"""


def placeholder_cards(message):
    body = f'  <text x="24" y="78" class="label">{esc(message)}</text>'
    write(f"{OUT_DIR}/github-stats.svg", svg_shell(700, 180, "GitHub Stats", body))
    write(f"{OUT_DIR}/github-languages.svg", svg_shell(700, 220, "Top Languages", body))
    write(f"{OUT_DIR}/github-contributions.svg", svg_shell(700, 160, "Contributions", body))


def fetch_contributions():
    to_date = dt.datetime.now(dt.timezone.utc)
    from_date = to_date - dt.timedelta(days=365)
    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          totalCommitContributions
          totalIssueContributions
          totalPullRequestContributions
          totalPullRequestReviewContributions
          restrictedContributionsCount
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                date
                contributionCount
              }
            }
          }
        }
      }
    }
    """
    data = graphql(
        query,
        {
            "login": USERNAME,
            "from": from_date.isoformat(),
            "to": to_date.isoformat(),
        },
    )
    if data.get("errors"):
        raise RuntimeError(json.dumps(data["errors"], indent=2))
    collection = data["data"]["user"]["contributionsCollection"]
    return collection, from_date.date(), to_date.date()


def fetch_repositories():
    repos = []
    page = 1
    while True:
        params = urllib.parse.urlencode(
            {
                "visibility": "all",
                "affiliation": "owner,collaborator,organization_member",
                "per_page": "100",
                "page": str(page),
                "sort": "updated",
            }
        )
        batch = request_json(f"https://api.github.com/user/repos?{params}")
        if not batch:
            break
        repos.extend(batch)
        page += 1
    return repos


def fetch_languages(repos):
    totals = {}
    for repo in repos:
        if repo.get("size", 0) == 0:
            continue
        langs = request_json(repo["languages_url"])
        for name, size in langs.items():
            totals[name] = totals.get(name, 0) + int(size)
    return totals


def render_stats(repos, contributions, from_date, to_date):
    public_count = sum(1 for repo in repos if not repo.get("private"))
    private_count = sum(1 for repo in repos if repo.get("private"))
    stars = sum(int(repo.get("stargazers_count", 0)) for repo in repos)
    forks = sum(int(repo.get("forks_count", 0)) for repo in repos)
    calendar_total = contributions["contributionCalendar"]["totalContributions"]
    restricted = contributions["restrictedContributionsCount"]
    stat_items = [
        ("Repositories", len(repos), BLUE),
        ("Public / Private", f"{public_count} / {private_count}", PURPLE),
        ("Contributions", calendar_total, GREEN),
        ("Stars", stars, ORANGE),
        ("Forks", forks, BLUE),
        ("Private count", restricted, PURPLE),
    ]
    cells = []
    for idx, (label, value, color) in enumerate(stat_items):
        x = 24 + (idx % 3) * 220
        y = 70 + (idx // 3) * 62
        cells.append(f'  <circle cx="{x}" cy="{y - 7}" r="4" fill="{color}"/>')
        cells.append(f'  <text x="{x + 14}" y="{y}" class="label">{esc(label)}</text>')
        cells.append(f'  <text x="{x}" y="{y + 30}" class="value">{esc(value)}</text>')
    cells.append(f'  <text x="24" y="164" class="small">Past 12 months: {from_date} to {to_date}. Includes repositories visible to the supplied token.</text>')
    write(f"{OUT_DIR}/github-stats.svg", svg_shell(700, 180, "GitHub Stats", "\n".join(cells)))


def render_languages(languages):
    total = sum(languages.values())
    if total == 0:
        body = '  <text x="24" y="78" class="label">No language data found.</text>'
        write(f"{OUT_DIR}/github-languages.svg", svg_shell(700, 220, "Top Languages", body))
        return
    colors = ["#58a6ff", "#3fb950", "#d29922", "#bc8cff", "#f85149", "#39c5cf", "#a5d6ff", "#ff7b72"]
    top = sorted(languages.items(), key=lambda item: item[1], reverse=True)[:8]
    x = 24
    y = 62
    bar_width = 652
    segments = []
    offset = x
    for idx, (_, size) in enumerate(top):
        width = max(1, round(bar_width * size / total))
        segments.append(f'  <rect x="{offset}" y="{y}" width="{width}" height="12" fill="{colors[idx % len(colors)]}"/>')
        offset += width
    rows = []
    for idx, (name, size) in enumerate(top):
        row_x = 24 + (idx % 2) * 330
        row_y = 104 + (idx // 2) * 28
        pct = size / total * 100
        rows.append(f'  <circle cx="{row_x}" cy="{row_y - 4}" r="5" fill="{colors[idx % len(colors)]}"/>')
        rows.append(f'  <text x="{row_x + 14}" y="{row_y}" class="label">{esc(name)}</text>')
        rows.append(f'  <text x="{row_x + 210}" y="{row_y}" class="small">{pct:.1f}%</text>')
    body = "\n".join(segments + rows)
    write(f"{OUT_DIR}/github-languages.svg", svg_shell(700, 220, "Top Languages", body))


def render_contributions(contributions):
    days = [
        day
        for week in contributions["contributionCalendar"]["weeks"]
        for day in week["contributionDays"]
    ][-365:]
    max_count = max([day["contributionCount"] for day in days] or [0])
    colors = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]
    cells = []
    cell = 9
    gap = 3
    start_x = 24
    start_y = 58
    for idx, day in enumerate(days):
        week = idx // 7
        dow = idx % 7
        count = day["contributionCount"]
        if count == 0 or max_count == 0:
            color = colors[0]
        elif count <= max_count * 0.25:
            color = colors[1]
        elif count <= max_count * 0.5:
            color = colors[2]
        elif count <= max_count * 0.75:
            color = colors[3]
        else:
            color = colors[4]
        x = start_x + week * (cell + gap)
        y = start_y + dow * (cell + gap)
        cells.append(f'  <rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{color}"><title>{esc(day["date"])}: {count} contributions</title></rect>')
    total = contributions["contributionCalendar"]["totalContributions"]
    body = "\n".join(cells)
    body += f'\n  <text x="24" y="148" class="small">{total} contributions in the past 12 months</text>'
    write(f"{OUT_DIR}/github-contributions.svg", svg_shell(700, 160, "Contributions", body))


def main():
    if not TOKEN:
        placeholder_cards("Set GH_STATS_TOKEN to generate public and private GitHub stats.")
        print("No token found; wrote placeholder cards.")
        return
    contributions, from_date, to_date = fetch_contributions()
    repos = fetch_repositories()
    languages = fetch_languages(repos)
    render_stats(repos, contributions, from_date, to_date)
    render_languages(languages)
    render_contributions(contributions)
    print(f"Generated stats for {USERNAME}: {len(repos)} repos, {len(languages)} languages.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Failed to generate GitHub stats: {exc}", file=sys.stderr)
        sys.exit(1)
