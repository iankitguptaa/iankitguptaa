"""Refreshes the live numbers in the profile SVGs from the GitHub API.

Run by .github/workflows/update-stats.yml; only the standard library is needed.
Usage: python scripts/update_stats.py [--root PATH]   (env: GITHUB_USER, GITHUB_TOKEN)
"""
import argparse, json, os, pathlib, re, urllib.request
from datetime import datetime, timezone
from html import escape

BLUE, CRIMSON, OFF, MUTED = "#247bff", "#ff354f", "#f3efe6", "#9aa4bd"
PX = 440  # left edge of the credentials panel in id-dashboard.svg


# ---------------------------------------------------------------- markup (also used by tools/build2.py)
def _wrap(name, inner):
    return f"<!--DYN:{name}-->{inner}<!--/DYN:{name}-->"


def date_svg(label, px=PX):
    return _wrap("date", f'<text class="mb" x="{px + 24}" y="128" font-size="10.5" fill="{MUTED}" letter-spacing="1.5">PUBLIC SNAPSHOT / {escape(label)}</text>')


def tiles_svg(repos, stars, followers, px=PX):
    out = ""
    for i, (lab, val, col) in enumerate([("PUBLIC REPOS", repos, CRIMSON), ("STARS EARNED", stars, "#8fb8ff"), ("FOLLOWERS", followers, "#8fb8ff")]):
        tx = px + 24 + i * 138
        out += (
            f'<g class="fu" style="animation-delay:{.5 + i * .1:.1f}s"><rect x="{tx}" y="146" width="128" height="86" rx="12" fill="#0f1c42" stroke="{BLUE}" stroke-opacity=".5"/>'
            f'<text class="bc" x="{tx + 14}" y="196" font-size="52" fill="{col}">{val:,}</text>'
            f'<text class="mb" x="{tx + 14}" y="220" font-size="9.5" fill="{MUTED}" letter-spacing="1.5">{lab}</text></g>'
        )
    return _wrap("tiles", out)


def langs_svg(rows, px=PX):
    out, top = "", max([c for _, c in rows] + [1])
    for i, (lang, cnt) in enumerate(rows):
        y = 284 + i * 30
        out += (
            f'<text class="m" x="{px + 24}" y="{y + 12}" font-size="12.5" fill="{OFF}">{escape(lang)}</text>'
            f'<rect x="{px + 120}" y="{y + 2}" width="250" height="10" rx="5" fill="#fff" opacity=".08"/>'
            f'<rect class="bar" style="animation-delay:{.9 + i * .15:.2f}s" x="{px + 120}" y="{y + 2}" width="{250 * cnt / top:.0f}" height="10" rx="5" fill="{BLUE if i != 1 else CRIMSON}"/>'
            f'<text class="mb" x="{px + 412}" y="{y + 12}" font-size="12.5" fill="{MUTED}" text-anchor="end">{cnt}</text>'
        )
    return _wrap("langs", out)


def pushes_svg(rows, px=PX):
    out = ""
    for i, (name, date) in enumerate(rows):
        y = 422 + i * 28
        name = name if len(name) <= 30 else name[:29] + "…"
        out += (
            f'<circle cx="{px + 30}" cy="{y - 4}" r="3.5" fill="{CRIMSON if i == 0 else BLUE}"/>'
            f'<text class="m" x="{px + 46}" y="{y}" font-size="12.5" fill="{OFF}">{escape(name)}</text>'
            f'<text class="m" x="{px + 412}" y="{y}" font-size="11.5" fill="{MUTED}" text-anchor="end">{escape(date)}</text>'
            f'<path d="M{px + 24} {y + 10}H{px + 412}" stroke="#fff" stroke-opacity=".06"/>'
        )
    return _wrap("pushes", out)


# ---------------------------------------------------------------- data
def api(path, token):
    req = urllib.request.Request("https://api.github.com" + path, headers={"Accept": "application/vnd.github+json", "User-Agent": "profile-stats"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def fetch(user, token):
    u = api(f"/users/{user}", token)
    repos, page = [], 1
    while True:
        chunk = api(f"/users/{user}/repos?per_page=100&page={page}&type=owner", token)
        repos += chunk
        if len(chunk) < 100:
            break
        page += 1
    own = [r for r in repos if not r["fork"]]
    langs = {}
    for r in own:
        if r["language"]:
            langs[r["language"]] = langs.get(r["language"], 0) + 1
    top_langs = sorted(langs.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    # the profile repo itself is pushed by this very workflow, so leave it out of "latest pushes"
    recent = sorted((r for r in own if r["name"].lower() != user.lower()), key=lambda r: r["pushed_at"], reverse=True)[:3]
    fmt = lambda iso: datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%d %b %Y").lstrip("0")
    return {
        "repos": u["public_repos"],
        "followers": u["followers"],
        "stars": sum(r["stargazers_count"] for r in repos),
        "langs": top_langs,
        "pushes": [(r["name"], fmt(r["pushed_at"])) for r in recent],
    }


# ---------------------------------------------------------------- rewrite
def swap(text, name, new):
    pat = re.compile(rf"<!--DYN:{name}-->.*?<!--/DYN:{name}-->", re.S)
    if not pat.search(text):
        raise SystemExit(f"marker {name} not found")
    return pat.sub(lambda _: new, text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(pathlib.Path(__file__).resolve().parent.parent))
    root = pathlib.Path(ap.parse_args().root)
    user = os.environ.get("GITHUB_USER", "iankitguptaa")
    d = fetch(user, os.environ.get("GITHUB_TOKEN"))
    print("fetched", d)

    idp, hero = root / "assets" / "id-dashboard.svg", root / "assets" / "hero.svg"
    id_old, hero_old = idp.read_text(encoding="utf-8"), hero.read_text(encoding="utf-8")
    id_new = swap(id_old, "tiles", tiles_svg(d["repos"], d["stars"], d["followers"]))
    id_new = swap(id_new, "langs", langs_svg(d["langs"]))
    id_new = swap(id_new, "pushes", pushes_svg(d["pushes"]))
    star_word = "star" if d["stars"] == 1 else "stars"
    hero_new = re.sub(r">[\d,]+ stars?<", f">{d['stars']:,} {star_word}<", hero_old)
    hero_new = re.sub(r">[\d,]+ repos?<", f">{d['repos']:,} repo{'' if d['repos'] == 1 else 's'}<", hero_new)
    if id_new == id_old and hero_new == hero_old:
        print("no change")
        return
    today = datetime.now(timezone.utc)
    id_new = swap(id_new, "date", date_svg(today.strftime("%d %b %Y").upper()))
    idp.write_text(id_new, encoding="utf-8")
    hero.write_text(hero_new, encoding="utf-8")

    # new ?v= value so GitHub's image cache fetches the fresh SVGs
    readme = root / "README.md"
    if readme.exists():
        txt = readme.read_text(encoding="utf-8")
        stamp = today.strftime("%Y%m%d")
        txt = re.sub(r"(\./assets/(?:hero|id-dashboard)\.svg\?v=)[^)\s]+", rf"\g<1>{stamp}", txt)
        readme.write_text(txt, encoding="utf-8")
    print("updated")


if __name__ == "__main__":
    main()
