#!/usr/bin/env python3
"""
Builds the profile dashboard: README.md plus the SVG cards in assets/.

Inputs
  - status.js in Divide317/cv-site (projects, skills, learning, about). Edit that file.
  - The public GitHub API (last push per repository, merged pull requests elsewhere).

Run locally with:  python3 build.py
Set STATUS_FILE to a local copy of status.js to build without fetching it.
Only the Python standard library is used.
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
CACHE = ROOT / "data" / "live.json"
STATUS_URL = "https://raw.githubusercontent.com/Divide317/cv-site/main/status.js"

GREEN, DEEP, CHALK, YELLOW, RED, ALU = "#12382B", "#0B271E", "#F1EEE3", "#F4C430", "#D63A2B", "#B7C1BB"
LINE = "rgba(241,238,227,0.2)"
FONT = "'Segoe UI', 'Helvetica Neue', Helvetica, Arial, sans-serif"


# ---------------------------------------------------------------- data

def http_json(url):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "profile-dashboard"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_status():
    local = os.environ.get("STATUS_FILE")
    if local:
        text = Path(local).read_text(encoding="utf-8")
    else:
        req = urllib.request.Request(STATUS_URL, headers={"User-Agent": "profile-dashboard"})
        with urllib.request.urlopen(req, timeout=25) as resp:
            text = resp.read().decode("utf-8")
    start = text.index("{", text.index("window.STATUS"))
    return json.loads(text[start:text.rindex("}") + 1])


def load_live(status):
    """Last push per repository and merged pull requests elsewhere.
    Anything that cannot be fetched keeps its previous value from data/live.json."""
    try:
        live = json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:
        live = {}
    live.setdefault("pushed", {})
    live.setdefault("merged", [])
    user = status.get("github", "")

    for project in status.get("projects", []):
        repo = project.get("repo")
        if not repo:
            continue
        try:
            info = http_json("https://api.github.com/repos/" + repo)
            if info.get("pushed_at") and not info.get("private"):
                live["pushed"][repo.lower()] = info["pushed_at"][:10]
        except Exception as err:  # keep the cached value
            print("note: could not read", repo, "-", err, file=sys.stderr)

    if user:
        try:
            query = "type:pr is:merged author:%s -user:%s" % (user, user)
            res = http_json("https://api.github.com/search/issues?per_page=8&sort=updated&q=" + urllib.parse.quote(query))
            live["merged"] = [
                {
                    "title": item["title"],
                    "url": item["html_url"],
                    "repo": item["repository_url"].split("/repos/")[-1],
                    "date": (item.get("closed_at") or "")[:10],
                }
                for item in res.get("items", [])
            ]
        except Exception as err:
            print("note: could not search pull requests -", err, file=sys.stderr)

    wanted = {p["repo"].lower() for p in status.get("projects", []) if p.get("repo")}
    live["pushed"] = {k: v for k, v in live["pushed"].items() if k in wanted}
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(live, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return live


# ---------------------------------------------------------------- drawing helpers

def nice_date(iso):
    try:
        d = datetime.strptime(iso, "%Y-%m-%d")
        return "%d %s %d" % (d.day, d.strftime("%b"), d.year)
    except Exception:
        return iso


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def text_width(s, size, bold=False):
    """Rough width of a string in pixels. Good enough to place chips and wrap lines."""
    total = 0.0
    for ch in s:
        if ch in "iljtf.,:;'|! ()":
            total += 0.30
        elif ch in "mwMW@":
            total += 0.86
        elif ch.isupper() or ch.isdigit():
            total += 0.64
        else:
            total += 0.53
    return total * size * (1.06 if bold else 1.0)


def wrap(s, size, max_width):
    lines, current = [], ""
    for word in s.split():
        trial = (current + " " + word).strip()
        if current and text_width(trial, size) > max_width:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    return lines


def text(x, y, s, size, fill=CHALK, weight=400, anchor="start", extra=""):
    return '<text x="%s" y="%s" font-size="%s" font-weight="%s" fill="%s" text-anchor="%s"%s>%s</text>' % (
        x, y, size, weight, fill, anchor, extra, escape(s))


def svg(width, height, body, label, style=""):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" role="img" aria-label="%s" font-family="%s">\n'
        '<title>%s</title>\n%s%s\n</svg>\n'
    ) % (width, height, width, height, escape(label, quote=True), FONT, escape(label),
         ("<style>%s</style>\n" % style) if style else "", body)


def panel(width, height):
    return '<rect x="0.5" y="0.5" width="%s" height="%s" rx="14" fill="%s" stroke="%s"/>' % (width - 1, height - 1, GREEN, LINE)


def gauge(x, y, pct, width=170):
    pct = max(0, min(100, pct))
    parts = ['<rect x="%s" y="%s" width="%s" height="10" rx="2" fill="rgba(241,238,227,0.14)"/>' % (x, y, width),
             '<rect x="%s" y="%s" width="%.1f" height="10" rx="2" fill="%s"/>' % (x, y, width * pct / 100.0, YELLOW)]
    for i in range(1, 10):  # tick marks every tenth, like a fuel gauge
        parts.append('<rect x="%.1f" y="%s" width="2" height="10" fill="%s"/>' % (x + width * i / 10.0 - 1, y, GREEN))
    return "".join(parts)


# ---------------------------------------------------------------- cards

def hero_card(status):
    import math
    W, H = 1000, 290
    name = status.get("name", "").upper()
    headline = wrap(status.get("headline", ""), 23, 600)

    # rev counter, drawn in its own 320 x 320 viewport
    dial = ['<circle cx="160" cy="160" r="156" fill="url(#bezel)"/>',
            '<circle cx="160" cy="160" r="143" fill="%s"/>' % DEEP,
            '<circle cx="160" cy="160" r="139" fill="url(#face)"/>']

    def point(v, r):
        a = math.radians(-135 + v / 8.0 * 270)
        return 160 + r * math.sin(a), 160 - r * math.cos(a)

    for i in range(17):
        v = i / 2.0
        major = i % 2 == 0
        x1, y1 = point(v, 133)
        x2, y2 = point(v, 113 if major else 122)
        dial.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="%d"/>' % (
            x1, y1, x2, y2, RED if v >= 6.5 else DEEP, 4 if major else 2))
        if major:
            tx, ty = point(v, 93)
            dial.append('<text x="%.1f" y="%.1f" font-size="30" font-weight="700" fill="%s" text-anchor="middle" dominant-baseline="central">%d</text>' % (tx, ty, DEEP, v))
    ax, ay = point(6.5, 133.5)
    bx, by = point(8, 133.5)
    dial.append('<path d="M%.1f %.1f A133.5 133.5 0 0 1 %.1f %.1f" fill="none" stroke="%s" stroke-width="9"/>' % (ax, ay, bx, by, RED))
    dial.append('<text x="160" y="226" font-size="13" font-weight="700" fill="%s" text-anchor="middle" letter-spacing="1.5">RPM x1000</text>' % DEEP)
    dial.append('<g class="needle"><path d="M156.5 188 L159.2 46 L160.8 46 L163.5 188 Z" fill="%s"/></g>' % RED)
    dial.append('<circle cx="160" cy="160" r="17" fill="%s"/><circle cx="160" cy="160" r="5" fill="#8f9b95"/>' % DEEP)

    body = [
        '<defs>'
        '<clipPath id="card"><rect width="%d" height="%d" rx="18"/></clipPath>'
        '<linearGradient id="bezel" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#eef1ee"/><stop offset="0.5" stop-color="#8f9b95"/><stop offset="1" stop-color="#d5dbd7"/></linearGradient>'
        '<radialGradient id="face" cx="0.5" cy="0.4" r="0.7"><stop offset="0" stop-color="#fbf9f1"/><stop offset="1" stop-color="#e4e0d2"/></radialGradient>'
        '</defs>' % (W, H),
        '<g clip-path="url(#card)">',
        '<rect width="%d" height="%d" fill="%s"/>' % (W, H, GREEN),
        '<rect x="24" width="4" height="%d" fill="%s"/><rect x="33" width="4" height="%d" fill="%s"/>' % (H, YELLOW, H, YELLOW),
        '</g>',
        text(68, 104, name, 46, weight=800, extra=' letter-spacing="0.5"'),
    ]
    y = 152
    for line in headline:
        body.append(text(68, y, line, 23, weight=500))
        y += 32
    role = "Computer science undergraduate, VIT Chennai. Security and systems."
    body.append(text(68, y + 14, role, 16, fill=ALU))
    body.append('<svg x="742" y="35" width="220" height="220" viewBox="0 0 320 320">%s</svg>' % "".join(dial))

    style = (
        ".needle{transform-origin:160px 160px;transform:rotate(-104.5deg);"
        "animation:sweep 2.6s cubic-bezier(.3,.1,.2,1) .4s both,idle 2.4s ease-in-out 3.2s infinite}"
        "@keyframes sweep{0%{transform:rotate(-135deg)}42%{transform:rotate(122deg)}100%{transform:rotate(-104.5deg)}}"
        "@keyframes idle{0%,100%{transform:rotate(-104.5deg)}50%{transform:rotate(-100.5deg)}}"
        "@media (prefers-reduced-motion:reduce){.needle{animation:none}}"
    )
    return svg(W, H, "\n".join(body), "%s. %s" % (status.get("name", ""), status.get("headline", "")), style)


def project_card(project, pushed):
    W = 490
    body = []
    stage = project.get("stage", "")
    chip_w = text_width(stage, 13) + 24
    solid = bool(project.get("finished"))
    body.append('<rect x="%.1f" y="22" width="%.1f" height="26" rx="13" fill="%s" stroke="%s" stroke-width="1.5"/>' % (
        W - 22 - chip_w, chip_w, YELLOW if solid else "none", YELLOW))
    body.append(text(W - 22 - chip_w / 2, 40, stage, 13, fill=DEEP if solid else YELLOW, weight=600, anchor="middle"))
    body.append(text(24, 46, project["name"], 25, weight=700))
    y = 74
    for line in wrap(project.get("tagline", ""), 15, W - 48):
        body.append(text(24, y, line, 15, fill=ALU))
        y += 21
    y += 8
    if isinstance(project.get("progress"), (int, float)):
        body.append(gauge(24, y - 9, project["progress"]))
        body.append(text(206, y, "%d%% built" % project["progress"], 14, weight=600))
        y += 28
    if pushed:
        body.append('<circle cx="29" cy="%d" r="4.5" fill="#4ade80"/>' % (y - 5))
        body.append(text(42, y, "Last push " + nice_date(pushed), 14, fill=ALU))
        y += 28
    for line in wrap(project.get("stack", ""), 14, W - 48):
        body.append(text(24, y, line, 14))
        y += 20
    H = 196
    label = "%s: %s. %s." % (project["name"], project.get("tagline", ""), stage)
    return svg(W, H, panel(W, H) + "\n" + "\n".join(body), label)


def skills_card(groups):
    W = 1000
    body, y = [], 40
    for g in groups:
        title = g["group"] + (" (" + g["note"] + ")" if g.get("note") else "")
        body.append(text(28, y, title, 15, fill=ALU))
        y += 16
        x = 28
        for item in g.get("items", []):
            w = text_width(item, 16, bold=True) + 28
            if x + w > W - 28:
                x = 28
                y += 42
            body.append('<rect x="%.1f" y="%d" width="%.1f" height="32" rx="16" fill="%s" stroke="%s"/>' % (x, y, w, DEEP, LINE))
            body.append(text(x + w / 2, y + 21.5, item, 16, weight=600, anchor="middle"))
            x += w + 10
        y += 32 + 38
    H = y - 14
    return svg(W, H, panel(W, H) + "\n" + "\n".join(body), "Skills: " + "; ".join(g["group"] + ": " + ", ".join(g["items"]) for g in groups))


def learning_card(items):
    W = 1000
    body, y = [], 20
    for n, c in enumerate(items):
        if n:
            body.append('<line x1="28" y1="%d" x2="%d" y2="%d" stroke="%s"/>' % (y, W - 28, y, LINE))
        state = c.get("state", "")
        if isinstance(c.get("done"), int) and isinstance(c.get("total"), int):
            state += ", %d of %d courses" % (c["done"], c["total"])
            body.append(gauge(W - 28 - 170, y + 52, 100.0 * c["done"] / max(1, c["total"])))
        body.append(text(28, y + 36, c["name"], 21, weight=700))
        body.append(text(W - 28, y + 36, state, 15, fill=YELLOW, weight=600, anchor="end"))
        body.append(text(28, y + 60, c.get("provider", ""), 14, fill=ALU))
        yy = y + 84
        for line in wrap("Covers " + c["covers"] + "." if c.get("covers") else "", 14, W - 260):
            body.append(text(28, yy, line, 14, fill=ALU))
            yy += 20
        y = yy + 6
    H = y + 6
    return svg(W, H, panel(W, H) + "\n" + "\n".join(body), "Currently learning: " + "; ".join(c["name"] + " (" + c.get("state", "") + ")" for c in items))


def activity_card(rows):
    """rows: (primary, secondary, date) tuples, newest first."""
    W = 1000
    body, y = [], 14
    for n, (primary, secondary, date) in enumerate(rows):
        if n:
            body.append('<line x1="28" y1="%d" x2="%d" y2="%d" stroke="%s"/>' % (y, W - 28, y, LINE))
        body.append(text(28, y + 31, primary, 17, weight=600))
        body.append(text(28 + text_width(primary, 17, bold=True) + 14, y + 31, secondary, 15, fill=ALU))
        body.append(text(W - 28, y + 31, nice_date(date), 15, fill=ALU, anchor="end"))
        y += 48
    H = y + 12
    return svg(W, H, panel(W, H) + "\n" + "\n".join(body), "Recent work: " + "; ".join("%s %s, %s" % r for r in rows))


# ---------------------------------------------------------------- README

def build():
    status = load_status()
    live = load_live(status)
    ASSETS.mkdir(exist_ok=True)
    for old in ASSETS.glob("*.svg"):
        old.unlink()

    (ASSETS / "hero.svg").write_text(hero_card(status), encoding="utf-8")

    cards = []
    for p in status.get("projects", []):
        pushed = live["pushed"].get((p.get("repo") or "").lower())
        name = "project-%s.svg" % slug(p["name"])
        (ASSETS / name).write_text(project_card(p, pushed), encoding="utf-8")
        img = '<img src="assets/%s" width="49%%" alt="%s: %s. %s.">' % (
            name, escape(p["name"], quote=True), escape(p.get("tagline", ""), quote=True), escape(p.get("stage", ""), quote=True))
        cards.append('<a href="https://github.com/%s">%s</a>' % (p["repo"], img) if p.get("repo") else img)

    rows = []
    by_repo = {(p.get("repo") or "").lower(): p for p in status.get("projects", [])}
    for repo, date in live["pushed"].items():
        if repo in by_repo:
            rows.append((by_repo[repo]["name"], "pushed new work", date))
    for pr in live["merged"]:
        rows.append((pr["repo"], "pull request merged: " + pr["title"][:60], pr["date"]))
    rows.sort(key=lambda r: r[2], reverse=True)
    rows = rows[:6]
    if rows:
        (ASSETS / "activity.svg").write_text(activity_card(rows), encoding="utf-8")

    (ASSETS / "skills.svg").write_text(skills_card(status.get("skills", [])), encoding="utf-8")
    if status.get("learning"):
        (ASSETS / "learning.svg").write_text(learning_card(status["learning"]), encoding="utf-8")

    out = []
    out.append('<p align="center"><img src="assets/hero.svg" width="100%%" alt="%s. %s"></p>\n' % (
        escape(status.get("name", ""), quote=True), escape(status.get("headline", ""), quote=True)))
    out.append("### About me\n")
    out.append(status.get("about", "") + "\n")
    if status.get("links"):
        out.append(" · ".join("[%s](%s)" % (l["label"], l["url"]) for l in status["links"]) + "\n")
    out.append("### Projects\n")
    lines = []
    for i in range(0, len(cards), 2):
        lines.append("<p>" + " ".join(cards[i:i + 2]) + "</p>")
    out.append("\n".join(lines) + "\n")
    if rows:
        out.append("### Contributions and recent work\n")
        out.append('<p><img src="assets/activity.svg" width="100%" alt="Most recent pushes and merged pull requests"></p>\n')
        if live["merged"]:
            out.append("Merged pull requests to other projects:\n")
            out.append("\n".join("- [%s](%s) in `%s`" % (pr["title"], pr["url"], pr["repo"]) for pr in live["merged"]) + "\n")
    out.append("### Skills\n")
    out.append('<p><img src="assets/skills.svg" width="100%%" alt="%s"></p>\n' % escape(
        "; ".join(g["group"] + ": " + ", ".join(g["items"]) for g in status.get("skills", [])), quote=True))
    if status.get("learning"):
        out.append("### Currently learning\n")
        out.append('<p><img src="assets/learning.svg" width="100%%" alt="%s"></p>\n' % escape(
            "; ".join(c["name"] + ", " + c.get("state", "") for c in status["learning"]), quote=True))
    out.append("<sub>This page rebuilds itself every few hours from "
               "<a href=\"https://github.com/Divide317/cv-site/blob/main/status.js\">status.js</a> and the GitHub API.</sub>\n")
    (ROOT / "README.md").write_text("\n".join(out), encoding="utf-8")
    print("built: %d project cards, %d activity rows, %d merged pull requests" % (len(cards), len(rows), len(live["merged"])))


if __name__ == "__main__":
    build()
