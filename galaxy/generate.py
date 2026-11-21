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


def _hash(ix, iy, seed):
    h = (ix * 374761393 + iy * 668265263 + seed * 2147483647) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFF) / 0xFFFF


def _noise(x, y, seed):
    """Bilinear value noise: the texture is pinned to the disc, so it turns
    with the galaxy instead of flickering from frame to frame."""
    x0, y0 = math.floor(x), math.floor(y)
    fx, fy = x - x0, y - y0
    a, b = _hash(x0, y0, seed), _hash(x0 + 1, y0, seed)
    c, d = _hash(x0, y0 + 1, seed), _hash(x0 + 1, y0 + 1, seed)
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def galaxy_frame(seed, angle, field):
    """One rendering of the disc rotated by `angle` (radians, in the disc plane).
    Returns a ROWS x COLS grid of [char, class]."""
    cx, cy = (COLS - 1) / 2, (ROWS - 1) / 2
    sx, sy = COLS / 2.05, ROWS / 2.05
    ca, sa = math.cos(-angle), math.sin(-angle)
    grid = []
    for y in range(ROWS):
        row = []
        for x in range(COLS):
            u0, v0 = (x - cx) / sx, (y - cy) / sy
            u, v = u0 * ca - v0 * sa, u0 * sa + v0 * ca      # back into the disc's own frame
            r, th = math.hypot(u, v), math.atan2(v, u)
            d = min(min((th - arm_theta(r, k)) % (2 * math.pi), 2 * math.pi - (th - arm_theta(r, k)) % (2 * math.pi))
                    for k in range(ARMS))
            width = 0.38 + 0.30 * r
            I = (math.exp(-(d / width) ** 2) * 1.35 * max(0, 1.05 - 0.8 * r)
                 + math.exp(-(r / 0.16) ** 2) * 1.6
                 + 0.22 * max(0, 1 - r) ** 1.5)
            I *= 0.55 + 0.9 * _noise(u * sx * 0.9, v * sx * 0.9, seed)
            if I < 0.16 or r > 1.02:
                row.append([" ", None]); continue
            lvl = max(1, min(len(RAMP) - 1, int(I * 7)))
            if r < 0.07:
                cls = "c"
            elif r < 0.17 and I > 0.8:
                cls = "o"
            else:
                cls = "g%d" % min(4, 1 + (lvl - 1) // 3 + (1 if lvl >= 8 else 0))
            row.append([RAMP[lvl], cls])
        grid.append(row)
    # field stars live in the disc frame too, so they orbit with everything else
    c2, s2 = math.cos(angle), math.sin(angle)
    for (u, v, b) in field:
        x = int(round(cx + (u * c2 - v * s2) * sx))
        y = int(round(cy + (u * s2 + v * c2) * sy))
        if 0 <= y < ROWS and 0 <= x < COLS and grid[y][x][0] in " .":
            grid[y][x] = ["·" if b < 0.6 else "+", "g2" if b < 0.6 else "g3"]
    grid[int(round(cy))][int(round(cx))] = ["@", "c"]
    return grid


def place_repos(repos, max_repos):
    """Fixed overlay: orange ✦ per repo on the frame-0 arms, plus its label.
    Returns {(row, col): [char, class, star_index]} and the masked cells."""
    cx, cy = (COLS - 1) / 2, (ROWS - 1) / 2
    sx, sy = COLS / 2.05, ROWS / 2.05
    shown = repos[:max_repos]
    n = max(1, len(shown) - 1)
    used_rows, placed, overlay, mask = set(), [], {}, set()
    for i, repo in enumerate(shown):
        target = 0.38 + 0.55 * i / n
        suffix = f" ★{repo.get('stargazers_count', 0)}"
        spot = None
        full = min(20, len(repo["name"])) + len(suffix)
        for need, k in [(full, i % ARMS), (full, (i + 1) % ARMS),
                        (10 + len(suffix), i % ARMS), (10 + len(suffix), (i + 1) % ARMS)]:
            for r in sorted((round(0.30 + j * 0.01, 2) for j in range(68)), key=lambda r: abs(r - target)):
                th = arm_theta(r, k)
                ix = int(round(cx + r * math.cos(th) * sx))
                iy = int(round(cy + r * math.sin(th) * sy))
                if not (1 <= iy < ROWS - 1 and 1 <= ix < COLS - 1):
                    continue
                if any(abs(iy - u) < 2 for u in used_rows):
                    continue
                room = {True: COLS - ix - 3, False: ix - 2}          # right?, left?
                for s in (True, False):                              # never write over the core
                    span = range(ix + 2, COLS) if s else range(ix - 1, -1, -1)
                    for n_ok, xx in enumerate(span):
                        if math.hypot((xx - cx) / sx, (iy - cy) / sy) < 0.24:
                            room[s] = min(room[s], n_ok - 1)
                            break
                outward = ix >= cx
                if room[outward] >= need:
                    side = outward
                elif room[not outward] >= need:
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
        overlay[(iy, ix)] = ["✦", "star", len(placed)]
        for j, ch in enumerate(label):
            overlay[(iy, start + j)] = [ch, "lbl" if j < len(name) else "lblm"]
        lo, hi = min(start, ix) - 1, max(start + len(label), ix + 1)
        mask.update((iy, xx) for xx in range(max(0, lo), min(COLS, hi + 1)))
        used_rows.add(iy)
        placed.append(repo["name"])
    return overlay, mask, placed


def rows_svg(grid, x0, y0, skip_blank=False):
    """Each row is one <text> pinned to an exact width with textLength, so the
    grid stays aligned whatever monospace font the viewer's system substitutes."""
    out = []
    for i, row in enumerate(grid):
        if skip_blank and all(c[0] == " " for c in row):
            continue
        spans, cur, buf = [], None, ""
        for cell in row:
            ch, cls = cell[0], cell[1]
            key = (cls, cell[2]) if cls == "star" else (cls if ch != " " else None, None)
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
        out.append(f'<text x="{x0}" y="{y0 + i * LH:.1f}" textLength="{COLS * CW:.1f}" lengthAdjust="spacing" xml:space="preserve">{inner}</text>')
    return "".join(out)


def galaxy_svg(repos, seed, cfg, x0, y0):
    """Rotating dust as flip-book frames under a fixed layer of repo stars."""
    rnd = random.Random(seed)
    field = [(rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.random()) for _ in range(int(COLS * ROWS * 0.012))]
    overlay, mask, placed = place_repos(repos, cfg.get("max_repos", 10))
    spin = cfg.get("spin", True) and cfg.get("animate", True)
    frames = int(cfg.get("spin_frames", 36)) if spin else 1
    period = 2 * math.pi / ARMS          # the disc looks identical after a 1/ARMS turn
    layers = []
    for f in range(frames):
        g = galaxy_frame(seed, -f * period / frames, field)   # negative: arms trail the spin
        for (y, x) in mask:
            g[y][x] = [" ", None]
        layers.append(f'<g class="fr" style="animation-delay:-{((frames - f) % frames) * cfg.get("spin_frame_seconds", 0.8):.2f}s">'
                      f'{rows_svg(g, x0, y0)}</g>' if frames > 1 else rows_svg(g, x0, y0))
    top = [[[" ", None] for _ in range(COLS)] for _ in range(ROWS)]
    for (y, x), cell in overlay.items():
        top[y][x] = cell
    return "\n    ".join(layers) + "\n    " + rows_svg(top, x0, y0, skip_blank=True), placed, frames


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
    gal, placed, frames = galaxy_svg(repos, zlib.crc32(user.encode()), cfg, GX, gy)
    ty = (H - 22 - block_h) / 2 - top  # centre the text column above the footer line
    body = [f'<g transform="translate(0 {ty:.1f})">'] + body + ['</g>']

    footer = f"✦ each star is a repository · updated {updated}"
    desc = " ".join(re.sub(r"\*\*", "", a["text"]) for a in cfg["about"])
    links = " · ".join(f'{l["label"].title()}: {l["url"]}' for l in cfg.get("links", []))
    anim = cfg.get("animate", True)
    css = f"""
    .fg{{fill:{T['fg']}}} .mu{{fill:{T['muted']}}} .or{{fill:{T['orange']}}} .rule{{stroke:{T['rule']}}}
    .g1{{fill:{T['tiers'][0]}}} .g2{{fill:{T['tiers'][1]}}} .g3{{fill:{T['tiers'][2]}}} .g4{{fill:{T['tiers'][3]}}}
    .c{{fill:{T['orange']};font-weight:700}} .o{{fill:{T['orange2']}}}
    .star{{fill:{T['orange']};font-weight:700}} .lbl{{fill:{T['fg']};font-weight:700}} .lblm{{fill:{T['muted']}}}
    .gal{{font-family:{MONO};font-size:{FS}px}}
    .fr{{visibility:hidden}} .fr:first-child{{visibility:visible}}"""
    if anim:
        fs = cfg.get("spin_frame_seconds", 0.8)
        css += f"""
    @media (prefers-reduced-motion: no-preference) {{
      .star{{animation:twinkle 3.6s ease-in-out infinite}}
      .c{{animation:pulse 5s ease-in-out infinite}}
      .fr{{animation:spin {frames * fs:.2f}s linear infinite}}
    }}
    @keyframes twinkle{{0%,100%{{fill-opacity:1}}50%{{fill-opacity:.3}}}}
    @keyframes pulse{{0%,100%{{fill-opacity:1}}50%{{fill-opacity:.55}}}}
    @keyframes spin{{0%{{visibility:visible}}{100 / max(frames, 1):.4f}%,100%{{visibility:hidden}}}}"""

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="t d">
  <title id="t">{html.escape(cfg["title"])} — @{html.escape(user)}</title>
  <desc id="d">{html.escape(desc)} {html.escape(links)}. Repositories: {html.escape(", ".join(placed))}.</desc>
  <style>{css}
  </style>
  <rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="12" fill="{T['bg']}" stroke="{T['border']}"/>
  {chr(10).join('  ' + b for b in body).strip()}
  <g class="gal">
    {gal}
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
