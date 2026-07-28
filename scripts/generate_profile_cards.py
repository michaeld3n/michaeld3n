#!/usr/bin/env python3
import datetime as dt
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import xml.sax.saxutils as xml


USERNAME = os.getenv("GITHUB_USERNAME", "michaeld3n")
TOKEN = os.getenv("GH_STATS_TOKEN") or os.getenv("GITHUB_TOKEN")
OUT_DIR = "assets"
API_VERSION = "2022-11-28"

BG = "#ffffff"
BORDER = "#d0d7de"
TEXT = "#24292f"
MUTED = "#57606a"
BLUE = "#0969da"
GREEN = "#1a7f37"
ORANGE = "#bc4c00"


def request_json(url):
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": f"{USERNAME}-profile-cards",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as res:
        return json.loads(res.read().decode("utf-8"))


def esc(value):
    return xml.escape(str(value), {'"': "&quot;"})


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        file.write(content)


def card(width, height, title, body):
    return f"""<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="title desc">
  <title id="title">{esc(title)}</title>
  <desc id="desc">Auto-generated GitHub profile card for {esc(USERNAME)}.</desc>
  <style>
    .title {{ fill: {TEXT}; font: 600 16px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .label {{ fill: {TEXT}; font: 500 12px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .muted {{ fill: {MUTED}; font: 500 11px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .value {{ fill: {TEXT}; font: 700 20px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
  </style>
  <rect width="{width}" height="{height}" rx="6" fill="{BG}"/>
  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="5.5" stroke="{BORDER}"/>
  <text x="18" y="28" class="title">{esc(title)}</text>
{body}
</svg>
"""


def shorten(text, limit):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else f"{text[:limit - 1]}..."


def event_label(event):
    event_type = event.get("type", "")
    repo = event.get("repo", {}).get("name", "").split("/")[-1]
    payload = event.get("payload", {})
    if event_type == "PushEvent":
        commits = len(payload.get("commits", []))
        return f"Pushed {commits} commit{'s' if commits != 1 else ''} to {repo}"
    if event_type == "PullRequestEvent":
        return f"{payload.get('action', 'Updated').title()} PR in {repo}"
    if event_type == "IssuesEvent":
        return f"{payload.get('action', 'Updated').title()} issue in {repo}"
    if event_type == "CreateEvent":
        ref_type = payload.get("ref_type", "ref")
        return f"Created {ref_type} in {repo}"
    if event_type == "ReleaseEvent":
        return f"{payload.get('action', 'Updated').title()} release in {repo}"
    if event_type == "ForkEvent":
        return f"Forked {repo}"
    return f"{event_type.replace('Event', '')} in {repo}"


def render_activity():
    try:
        events = request_json(f"https://api.github.com/users/{USERNAME}/events?per_page=30")
    except urllib.error.HTTPError:
        events = []
    rows = []
    filtered = [
        event for event in events
        if event.get("type") in {"PushEvent", "PullRequestEvent", "IssuesEvent", "CreateEvent", "ReleaseEvent", "ForkEvent"}
    ][:5]
    if not filtered:
        rows.append(f'  <text x="18" y="62" class="muted">No recent public activity found.</text>')
    for idx, event in enumerate(filtered):
        y = 58 + idx * 24
        created = event.get("created_at", "")[:10]
        rows.append(f'  <circle cx="22" cy="{y - 4}" r="4" fill="{BLUE}"/>')
        rows.append(f'  <text x="36" y="{y}" class="label">{esc(shorten(event_label(event), 48))}</text>')
        rows.append(f'  <text x="350" y="{y}" class="muted">{esc(created)}</text>')
    height = max(100, 52 + max(1, len(filtered)) * 24)
    write(f"{OUT_DIR}/metrics-activity.svg", card(480, height, "Recent Activity", "\n".join(rows)))


def fetch_repositories():
    repos = []
    page = 1
    while page <= 3:
        params = urllib.parse.urlencode({
            "visibility": "all",
            "affiliation": "owner,collaborator,organization_member",
            "per_page": "100",
            "page": str(page),
            "sort": "updated",
        })
        batch = request_json(f"https://api.github.com/user/repos?{params}") if TOKEN else request_json(f"https://api.github.com/users/{USERNAME}/repos?per_page=100&page={page}&sort=updated")
        if not batch:
            break
        repos.extend(batch)
        page += 1
    return repos


def render_habits():
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)).isoformat()
    repos = fetch_repositories()
    hours = [0] * 24
    weekdays = [0] * 7
    commits_seen = 0
    for repo in repos[:60]:
        if repo.get("fork"):
            continue
        params = urllib.parse.urlencode({"author": USERNAME, "since": since, "per_page": "30"})
        try:
            commits = request_json(f"{repo['commits_url'].split('{')[0]}?{params}")
        except urllib.error.HTTPError:
            continue
        for commit in commits:
            date_text = commit.get("commit", {}).get("author", {}).get("date")
            if not date_text:
                continue
            when = dt.datetime.fromisoformat(date_text.replace("Z", "+00:00")).astimezone(dt.timezone(dt.timedelta(hours=10)))
            hours[when.hour] += 1
            weekdays[when.weekday()] += 1
            commits_seen += 1
    peak_hour = max(range(24), key=lambda hour: hours[hour]) if commits_seen else None
    peak_day = max(range(7), key=lambda day: weekdays[day]) if commits_seen else None
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    body = []
    body.append(f'  <text x="18" y="64" class="value">{commits_seen}</text>')
    body.append(f'  <text x="18" y="84" class="muted">commits sampled from the last 30 days</text>')
    if commits_seen:
        body.append(f'  <text x="250" y="58" class="label">Most active hour</text>')
        body.append(f'  <text x="250" y="82" class="value">{peak_hour:02d}:00</text>')
        body.append(f'  <text x="250" y="114" class="label">Most active day</text>')
        body.append(f'  <text x="250" y="138" class="value">{day_names[peak_day]}</text>')
    else:
        body.append(f'  <text x="250" y="70" class="muted">No recent commits found.</text>')
    write(f"{OUT_DIR}/metrics-habits.svg", card(480, 160, "Coding Habits", "\n".join(body)))


render_activity()
render_habits()
