#!/usr/bin/env python3
"""ASCII Repo Galaxy — GitHub profile card generator.

Renders assets/repo-galaxy-dark.svg and assets/repo-galaxy-light.svg:
an about-me panel on the left and a procedural ASCII spiral galaxy on the
right, where every orange ✦ is one of your repositories.

Standard library only. Usage:
    python galaxy/generate.py                      # live data from the GitHub API
    python galaxy/generate.py --snapshot data.json # offline, from a saved repo list

Env: GITHUB_TOKEN (optional, raises the API rate limit), GALAXY_USER (overrides config).
Edit galaxy/config.json to change the text, links or repo filters.
"""
import argparse, datetime, html, json, math, os, random, re, sys, urllib.request, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# ----------------------------------------------------------------- look
THEMES = {  # GitHub Primer colours + orange accents
    "dark": dict(bg="#0d1117", border="#3d444d", fg="#f0f6fc", muted="#9198a1", rule="#3d444d",
                 tiers=["#3d444d", "#656c76", "#9198a1", "#d1d7e0"],
                 orange="#ff8c1a", orange2="#e8590c", chip="#1e2327"),
    "light": dict(bg="#ffffff", border="#d1d9e0", fg="#1f2328", muted="#59636e", rule="#d1d9e0",
                  tiers=["#d1d9e0", "#9ea7b3", "#59636e", "#25292e"],
                  orange="#e8590c", orange2="#bc4c00", chip="#1e2327"),
}
MONO = "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,'Liberation Mono',monospace"
SANS = ("-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans',Helvetica,Arial,sans-serif,"
        "'Apple Color Emoji','Segoe UI Emoji','Noto Color Emoji'")
RAMP = " .·:-=+*%#@"

# card geometry
W = 900
PAD = 32
LEFT_W = 336          # text column width (px)
WRAP = 46             # characters per wrapped line in the text column
COLS, ROWS = 64, 28   # galaxy grid
CW, LH, FS = 7.6, 13.0, 12   # cell width, line height, font size
GX = 392              # galaxy x
ARMS, WIND = 2, 0.32


# ----------------------------------------------------------------- data
def fetch_repos(user, token):
    repos, page = [], 1
    while True:
        url = f"https://api.github.com/users/{user}/repos?per_page=100&type=owner&page={page}"
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                                   "User-Agent": "repo-galaxy"})
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(req, timeout=30) as r:
            batch = json.load(r)
        repos += batch
        if len(batch) < 100:
            return repos
        page += 1


def select_repos(repos, cfg, user):
    excl = {n.lower() for n in cfg.get("exclude_repos", [])} | {user.lower()}
    keep = [r for r in repos
            if r["name"].lower() not in excl
            and not (cfg.get("exclude_forks", True) and r.get("fork"))
            and not (cfg.get("exclude_archived", False) and r.get("archived"))]
    # brightest first: most stars, then most recently pushed
    keep.sort(key=lambda r: r.get("pushed_at") or "", reverse=True)
    keep.sort(key=lambda r: r.get("stargazers_count", 0), reverse=True)
    return keep


# ----------------------------------------------------------------- galaxy
def arm_theta(r, k):
    return k * 2 * math.pi / ARMS + math.log(max(r, 0.04) / 0.08) / WIND


def build_grid(repos, seed, max_repos):
    """Analytic two-arm log spiral -> character grid of (char, css-class, extra)."""
    rnd = random.Random(seed)
    cx, cy = (COLS - 1) / 2, (ROWS - 1) / 2
    sx, sy = COLS / 2.05, ROWS / 2.05
    grid = []
    for y in range(ROWS):
        row = []
        for x in range(COLS):
            u, v = (x - cx) / sx, (y - cy) / sy
            r, th = math.hypot(u, v), math.atan2(v, u)
            d = min(min((th - arm_theta(r, k)) % (2 * math.pi), 2 * math.pi - (th - arm_theta(r, k)) % (2 * math.pi))
                    for k in range(ARMS))
            width = 0.38 + 0.30 * r
            I = (math.exp(-(d / width) ** 2) * 1.35 * max(0, 1.05 - 0.8 * r)
                 + math.exp(-(r / 0.16) ** 2) * 1.6
                 + 0.22 * max(0, 1 - r) ** 1.5)
            I *= 0.65 + 0.7 * rnd.random()
            if rnd.random() < 0.012:
                I = max(I, 0.25 + rnd.random() * 0.3)
            if I < 0.16 or r > 1.02:
                row.append([" ", None]); continue
            lvl = max(1, min(len(RAMP) - 1, int(I * 7)))
            if r < 0.07:
                cls = "core"
            elif r < 0.17 and I > 0.8:
                cls = "o2"
            else:
                cls = "g%d" % min(4, 1 + (lvl - 1) // 3 + (1 if lvl >= 8 else 0))
            row.append([RAMP[lvl], cls])
        grid.append(row)
    grid[int(round(cy))][int(round(cx))] = ["@", "core"]

    # place repositories on the arms, brightest nearest the core
    shown = repos[:max_repos]
    n = max(1, len(shown) - 1)
    used_rows, placed = set(), []
    for i, repo in enumerate(shown):
        target = 0.38 + 0.55 * i / n
        stars = repo.get("stargazers_count", 0)
        suffix = f" ★{stars}"
        spot = None
        full = min(20, len(repo["name"])) + len(suffix)
        for need, k in [(full, i % ARMS), (full, (i + 1) % ARMS),
                        (10 + len(suffix), i % ARMS), (10 + len(suffix), (i + 1) % ARMS)]:
            cands = sorted((round(0.30 + j * 0.01, 2) for j in range(68)), key=lambda r: abs(r - target))
            for r in cands:
                th = arm_theta(r, k)
                ix = int(round(cx + r * math.cos(th) * sx))
                iy = int(round(cy + r * math.sin(th) * sy))
                if not (1 <= iy < ROWS - 1 and 1 <= ix < COLS - 1):
                    continue
                if any(abs(iy - u) < 2 for u in used_rows):
                    continue
                # room for the label: prefer pointing away from the core
                room = {True: COLS - ix - 3, False: ix - 2}          # right?, left?
                for s in (True, False):                              # never write over the core
                    span = range(ix + 2, COLS) if s else range(ix - 1, -1, -1)
                    for n_ok, xx in enumerate(span):
                        if math.hypot((xx - cx) / sx, (iy - cy) / sy) < 0.24:
                            room[s] = min(room[s], n_ok - 1)
                            break
                want = min(20, len(repo["name"])) + len(suffix)
                outward = ix >= cx
                if room[outward] >= want:
                    side = outward
                elif room[not outward] >= want:
                    side = not outward
                else:
                    side = max((True, False), key=lambda s: room[s])
                if room[side] < need:
                    continue
                spot = (ix, iy, side, room[side])
                break
            if spot:
                break
        if not spot:
            continue
        ix, iy, right, room = spot
        name = repo["name"]
        maxlen = min(20, room - len(suffix))
        if len(name) > maxlen:
            name = name[: maxlen - 1] + "…"
        label = name + suffix
        start = ix + 2 if right else ix - 1 - len(label)
        grid[iy][ix] = ["✦", "star", len(placed)]
        for j, c in enumerate(label):
            grid[iy][start + j] = [c, "lbl" if j < len(name) else "lblm"]
        for xx in (start - 1, start + len(label)):
            if 0 <= xx < COLS and xx != ix:
                grid[iy][xx] = [" ", None]
        used_rows.add(iy)
        placed.append(repo["name"])
    return grid, placed


def grid_svg(grid, x0, y0):
    out = []
    for i, row in enumerate(grid):
        spans, cur, buf = [], None, ""
        for cell in row:
            ch, cls = cell[0], cell[1]
            key = (cls, cell[2]) if cls == "star" else (cls, None)
            if key != cur and buf:
                spans.append((cur, buf)); buf = ""
            cur = key; buf += ch
        if buf:
            spans.append((cur, buf))
        inner = ""
        for (cls, idx), b in spans:
            t = html.escape(b)
            if cls is None:
                inner += t
            elif cls == "star":
                inner += f'<tspan class="star" style="animation-delay:-{(idx * 1.37) % 3.6:.2f}s">{t}</tspan>'
            else:
                inner += f'<tspan class="{cls}">{t}</tspan>'
        # textLength pins every row to the same width, so the grid stays
        # aligned whatever monospace font the viewer's system substitutes
        out.append(f'<text x="{x0}" y="{y0 + i * LH:.1f}" textLength="{COLS * CW:.1f}" lengthAdjust="spacing" '
                   f'xml:space="preserve">{inner}</text>')
    return "\n    ".join(out)


# ----------------------------------------------------------------- text column
def rich_chars(text):
    """'**bold**' markup -> list of (char, is_bold)."""
    out, bold = [], False
    for part in re.split(r"(\*\*)", text):
        if part == "**":
            bold = not bold
        else:
            out += [(c, bold) for c in part]
    return out


def wrap_rich(chars, width):
    words, cur = [], []
    for c in chars:
        if c[0] == " ":
            if cur: words.append(cur); cur = []
        else:
            cur.append(c)
    if cur: words.append(cur)
    lines, line = [], []
    for w in words:
        if line and len(line) + 1 + len(w) > width:
            lines.append(line); line = []
        line = line + [(" ", False)] + w if line else list(w)
    if line: lines.append(line)
    return lines


def rich_svg(line):
    out, buf, bold = "", "", None
    for c, b in line + [("", None)]:
        if b != bold and buf:
            t = html.escape(buf)
            out += f'<tspan font-weight="700">{t}</tspan>' if bold else t
            buf = ""
        bold = b; buf += c
    return out


# ----------------------------------------------------------------- card
def render(theme, cfg, user, repos, updated):
    T = THEMES[theme]
    grid, placed = build_grid(repos, zlib.crc32(user.encode()), cfg.get("max_repos", 10))
    total_stars = sum(r.get("stargazers_count", 0) for r in repos)

    # text column, laid out from y=0 and then centred vertically in the card
    body, y = [], 0
    if cfg.get("eyebrow"):
        body.append(f'<text x="{PAD}" y="{y}" font-family="{MONO}" font-size="11" font-weight="700" letter-spacing="2.2" class="or">{html.escape(cfg["eyebrow"])}</text>')
        y += 34
    else:
        y += 18
    top = y - 18                      # cap height of the title
    body.append(f'<text x="{PAD}" y="{y}" font-family="{SANS}" font-size="24" font-weight="700" class="fg">{html.escape(cfg["title"])}</text>')
    y += 24
    body.append(f'<text x="{PAD}" y="{y}" font-family="{MONO}" font-size="12.5" class="mu">@{html.escape(user)} · {total_stars}★ · '
                f'{len(repos)} repositor{"y" if len(repos) == 1 else "ies"}</text>')
    y += 18
    body.append(f'<line x1="{PAD}" x2="{PAD + LEFT_W}" y1="{y}" y2="{y}" class="rule"/>')
    y += 24
    body.append(f'<text x="{PAD}" y="{y}" font-family="{MONO}" font-size="10" font-weight="700" letter-spacing="2" class="mu">{html.escape(cfg["about_heading"])}</text>')
    y += 24
    for item in cfg["about"]:
        for j, ln in enumerate(wrap_rich(rich_chars(item["text"]), WRAP)):
            if j == 0 and item.get("icon"):
                body.append(f'<text x="{PAD}" y="{y}" font-family="{SANS}" font-size="12.5">{html.escape(item["icon"])}</text>')
            body.append(f'<text x="{PAD + 22}" y="{y}" font-family="{SANS}" font-size="12.5" class="fg">{rich_svg(ln)}</text>')
            y += 17
        y += 6
    bottom = y - 17 - 6 + 4           # baseline of the last line + descenders
    if cfg.get("show_link_chips", False):
        y += 8
        x = PAD
        for ln in cfg.get("links", []):
            lw, vw = len(ln["label"]) * 7.4 + 24, len(ln["value"]) * 7.4 + 24
            body.append(f'<g transform="translate({x:.0f} {y})">'
                        f'<rect width="{lw + vw:.0f}" height="26" rx="4" fill="{T["chip"]}"/>'
                        f'<path d="M{lw:.0f} 0 H{lw + vw - 4:.0f} a4 4 0 0 1 4 4 V22 a4 4 0 0 1 -4 4 H{lw:.0f} Z" fill="{html.escape(ln["color"])}"/>'
                        f'<text x="{lw / 2:.0f}" y="17" text-anchor="middle" font-family="{SANS}" font-size="10" font-weight="700" letter-spacing="1" fill="#fff">{html.escape(ln["label"])}</text>'
                        f'<text x="{lw + vw / 2:.0f}" y="17" text-anchor="middle" font-family="{SANS}" font-size="10" font-weight="700" letter-spacing="1" fill="#fff">{html.escape(ln["value"])}</text></g>')
            x += lw + vw + 10
        bottom = y + 26
    block_h = bottom - top

    galaxy_h = ROWS * LH
    H = int(max(block_h + 2 * 44 + 22, galaxy_h + 40 + 36))
    gy = (H - 22 - galaxy_h) / 2 + 9  # baseline of first row, centred above the footer
    ty = (H - 22 - block_h) / 2 - top  # centre the text column above the footer line
    body = [f'<g transform="translate(0 {ty:.1f})">'] + body + ['</g>']

    footer = f"✦ each star is a repository · updated {updated}"
    desc = " ".join(re.sub(r"\*\*", "", a["text"]) for a in cfg["about"])
    links = " · ".join(f'{l["label"].title()}: {l["url"]}' for l in cfg.get("links", []))
    anim = cfg.get("animate", True)
    css = f"""
    .fg{{fill:{T['fg']}}} .mu{{fill:{T['muted']}}} .or{{fill:{T['orange']}}} .rule{{stroke:{T['rule']}}}
    .g1{{fill:{T['tiers'][0]}}} .g2{{fill:{T['tiers'][1]}}} .g3{{fill:{T['tiers'][2]}}} .g4{{fill:{T['tiers'][3]}}}
    .core{{fill:{T['orange']};font-weight:700}} .o2{{fill:{T['orange2']}}}
    .star{{fill:{T['orange']};font-weight:700}} .lbl{{fill:{T['fg']};font-weight:700}} .lblm{{fill:{T['muted']}}}
    .gal{{font-family:{MONO};font-size:{FS}px}}"""
    if anim:
        css += """
    @media (prefers-reduced-motion: no-preference) {
      .star{animation:twinkle 3.6s ease-in-out infinite}
      .core{animation:pulse 5s ease-in-out infinite}
    }
    @keyframes twinkle{0%,100%{fill-opacity:1}50%{fill-opacity:.3}}
    @keyframes pulse{0%,100%{fill-opacity:1}50%{fill-opacity:.55}}"""

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="t d">
  <title id="t">{html.escape(cfg["title"])} — @{html.escape(user)}</title>
  <desc id="d">{html.escape(desc)} {html.escape(links)}. Repositories: {html.escape(", ".join(placed))}.</desc>
  <style>{css}
  </style>
  <rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="12" fill="{T['bg']}" stroke="{T['border']}"/>
  {chr(10).join('  ' + b for b in body).strip()}
  <g class="gal">
    {grid_svg(grid, GX, gy)}
  </g>
  <text x="{W - 20}" y="{H - 14}" text-anchor="end" font-family="{MONO}" font-size="10" class="mu" fill-opacity=".7">{html.escape(footer)}</text>
</svg>
"""
    return svg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", help="read repos from a JSON file instead of the API")
    ap.add_argument("--out", default=os.path.join(ROOT, "assets"))
    a = ap.parse_args()
    cfg = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
    user = os.environ.get("GALAXY_USER") or cfg["username"]
    raw = json.load(open(a.snapshot, encoding="utf-8")) if a.snapshot else fetch_repos(user, os.environ.get("GITHUB_TOKEN"))
    repos = select_repos(raw, cfg, user)
    updated = datetime.date.today().isoformat()
    os.makedirs(a.out, exist_ok=True)
    for theme in THEMES:
        path = os.path.join(a.out, f"repo-galaxy-{theme}.svg")
        with open(path, "w", encoding="utf-8") as f:
            f.write(render(theme, cfg, user, repos, updated))
        print("wrote", os.path.relpath(path, ROOT))
    print(f"{len(repos)} repositories")


if __name__ == "__main__":
    sys.exit(main())
