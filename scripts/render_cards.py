#!/usr/bin/env python3
"""Render the profile README cards into cards/ as animated, self-contained SVGs.

Designed for <img> embedding, so it only uses what works there:
  * an inline <style> block with CSS keyframes
  * SMIL <animate> elements (decorative loops only, see below)
  * per-card fonts subset with pyftsubset, embedded as base64 WOFF data URIs

Usage
  python scripts/render_cards.py            # animated cards
  STATIC=1 python scripts/render_cards.py   # final frame, no animation (for screenshots)
  SAMPLE=1 python scripts/render_cards.py   # fake data, to preview before the Action has run

Reduced motion
  CSS animations are written as "from" keyframes only, so with animation: none the
  element simply sits in its final state. SMIL can't be switched off from CSS, so it is
  used only for decorative loops (caret, pulses) inside <g class="smil">, which the
  prefers-reduced-motion block hides. Nothing the card needs to be readable depends on SMIL.

Needs: fonttools (provides pyftsubset), optional Pillow (to shrink the portrait).
"""
from __future__ import annotations

import base64
import datetime as dt
import json
import math
import os
import random
import subprocess
import sys
import tempfile
import textwrap
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape

from fontTools.ttLib import TTFont

# --------------------------------------------------------------------------- config
LOGIN = "noman-h"
NAME = "Noman H"
TAGLINE = "MERN full stack developer building with Next.js and SQL"
FEATURED = ["CheckinnPro", "CrowdSight"]
TILES = [  # glyph, title, subtitle, filename
    ("in", "LinkedIn", "in/noman-h", "tile-linkedin.svg"),
    ("X", "X", "@Nomaan_21", "tile-x.svg"),
    ("</>", "GitHub", "All repositories", "tile-github.svg"),
]

DATA = Path(os.environ.get("DATA", "data/github.json"))
OUT = Path(os.environ.get("OUT", "cards"))
FONT_SRC = Path(os.environ.get("FONT_SRC", "fonts/FiraCode-VF.ttf"))
PORTRAIT_CANDIDATES = [Path(f"assets/portrait.{e}") for e in ("png", "jpg", "jpeg", "webp")]

STATIC = os.environ.get("STATIC") == "1"
SAMPLE = os.environ.get("SAMPLE") == "1"

# Colours and font are taken from the current README (Tailwind sky-300 / slate, Fira Code).
BG = "#0f172a"      # card surface
EMPTY = "#1e293b"   # empty graph cells, icon wells
EDGE = "#334155"    # hairlines
TEXT = "#e2e8f0"
SOFT = "#cbd5e1"
MUTED = "#94a3b8"
ACCENT = "#7dd3fc"  # brand colour
FONT_FAMILY = "Fira Code"
FALLBACK = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"

# Seconds from page load. Cards are staggered so the page plays top to bottom.
SCHED = dict(hero=0.0, tiles=1.4, tile_step=0.12, activity=1.9, repo=2.8, repo_step=0.35, graph=3.7)

W = 830  # card width in px; GitHub's README column is about this wide
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

LANG_COLORS = {
    "JavaScript": "#f1e05a", "TypeScript": "#3178c6", "Python": "#3572a5", "C++": "#f34b7d",
    "C": "#555555", "HTML": "#e34c26", "CSS": "#563d7c", "Java": "#b07219", "Go": "#00add8",
    "Rust": "#dea584", "PHP": "#4f5d95", "Shell": "#89e051", "SCSS": "#c6538c", "Vue": "#41b883",
}

if not FONT_SRC.exists():
    sys.exit(f"Font not found: {FONT_SRC}\n  curl -fsSL -o {FONT_SRC} --create-dirs "
             '"https://raw.githubusercontent.com/google/fonts/main/ofl/firacode/FiraCode%5Bwght%5D.ttf"')

_tt = TTFont(str(FONT_SRC))
ADV = _tt["hmtx"][_tt.getBestCmap()[ord("0")]][0] / _tt["head"].unitsPerEm  # monospace advance in em
_IS_VARIABLE = "fvar" in _tt


def adv(size: float) -> float:
    return ADV * size


# --------------------------------------------------------------------------- font
_BASE_FONT: Path | None = None


def base_font() -> Path:
    """Trim a variable font to the two weights used (400-700) once, before per-card subsetting."""
    global _BASE_FONT
    if _BASE_FONT:
        return _BASE_FONT
    if not _IS_VARIABLE:
        _BASE_FONT = FONT_SRC
        return _BASE_FONT
    out = Path(tempfile.mkdtemp()) / "base.ttf"
    subprocess.run([sys.executable, "-m", "fontTools.varLib.instancer", str(FONT_SRC),
                    "wght=400:700", "-o", str(out), "-q"], check=True)
    _BASE_FONT = out
    return out


def font_face(chars: set[str]) -> str:
    """Subset the font to exactly the glyphs this card draws and return an @font-face rule."""
    with tempfile.TemporaryDirectory() as td:
        txt, out = Path(td, "chars.txt"), Path(td, "f.woff")
        txt.write_text("".join(sorted(chars | {" "})), encoding="utf-8")
        subprocess.run(["pyftsubset", str(base_font()), f"--text-file={txt}", "--flavor=woff",
                        f"--output-file={out}", "--layout-features=", "--no-hinting",
                        "--drop-tables+=DSIG", "--name-IDs="], check=True)
        b64 = base64.b64encode(out.read_bytes()).decode()
    weight = "400 700" if _IS_VARIABLE else "400"
    return (f"@font-face{{font-family:'{FONT_FAMILY}';font-weight:{weight};"
            f"src:url(data:font/woff;base64,{b64}) format('woff')}}")


# --------------------------------------------------------------------------- svg helpers
def css() -> str:
    c = (f"text{{font-family:'{FONT_FAMILY}',{FALLBACK}}}"
         f".t{{fill:{TEXT}}}.s{{fill:{SOFT}}}.m{{fill:{MUTED}}}.a{{fill:{ACCENT}}}"
         ".b{font-weight:600}.n{font-weight:400}")
    if STATIC:
        return c
    return c + (
        "@keyframes fade{from{opacity:0}}"
        "@keyframes grow{from{transform:scaleY(0)}}"
        "@keyframes draw{from{stroke-dashoffset:1}}"
        ".fade{animation:fade .6s ease-out both}"
        ".type{animation:fade .01s steps(1,end) both}"
        ".grow{transform-box:fill-box;transform-origin:50% 100%;"
        "animation:grow .8s cubic-bezier(.2,.8,.2,1) both}"
        ".draw{stroke-dasharray:1;animation:draw 1.1s cubic-bezier(.4,0,.2,1) both}"
        "@media (prefers-reduced-motion:reduce){"
        "*{animation:none!important}.draw{stroke-dasharray:none}.smil{display:none}}"
    )


def D(t: float) -> str:
    return "" if STATIC else f' style="animation-delay:{t:.2f}s"'


def smil(inner: str) -> str:
    return "" if STATIC else f'<g class="smil">{inner}</g>'


def text(x, y, s, size, cls="t", delay=None, anchor=None, kind="fade") -> str:
    a = f' text-anchor="{anchor}"' if anchor else ""
    c = f"{cls} {kind}" if delay is not None else cls
    d = D(delay) if delay is not None else ""
    return f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" class="{c}"{a}{d}>{escape(s)}</text>'


def panel(w, h, t0, r=16, edge_opacity=0.3) -> str:
    return (f'<rect class="fade" width="{w}" height="{h}" rx="{r}" fill="{BG}"{D(t0)}/>'
            f'<rect class="draw" x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="{r - 0.5}" '
            f'fill="none" stroke="{ACCENT}" stroke-opacity="{edge_opacity}" pathLength="1"{D(t0)}/>')


def visible_chars(body: str) -> set[str]:
    root = ET.fromstring(f'<r xmlns:xlink="http://www.w3.org/1999/xlink">{body}</r>')
    return {ch for s in root.itertext() for ch in s if not ch.isspace()}


def svg_doc(w, h, title, desc, body) -> str:
    style = font_face(visible_chars(body)) + css()
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-labelledby="t d">'
            f"<title id=\"t\">{escape(title)}</title><desc id=\"d\">{escape(desc)}</desc>"
            f"<style>{style}</style>{body}</svg>\n")


def mix(a: str, b: str, t: float) -> str:
    pa, pb = [int(a[i:i + 2], 16) for i in (1, 3, 5)], [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(pa, pb))


def fmt_date(d: dt.date) -> str:
    return f"{MONTHS[d.month - 1]} {d.day}, {d.year}"


# --------------------------------------------------------------------------- data
def sample_data() -> dict:
    rnd = random.Random(7)
    end = dt.date.today()
    days = []
    for i in range(364, -1, -1):
        d = end - dt.timedelta(days=i)
        quiet = d.weekday() >= 5 and rnd.random() < 0.6
        n = 0 if quiet else rnd.choice([0, 0, 1, 2, 3, 5, 8, 13, 21])
        days.append({"date": d.isoformat(), "count": n})
    repos = [{"name": n, "description": "Sample description for this repository, shown when no data file exists yet.",
              "stars": 12 * (i + 1), "forks": 3 * (i + 1), "language": "JavaScript",
              "url": f"https://github.com/{LOGIN}/{n}"} for i, n in enumerate(FEATURED)]
    return {"login": LOGIN, "days": days, "repos": repos}


def load_data() -> dict:
    if SAMPLE:
        print("SAMPLE=1: using fake data", file=sys.stderr)
        return sample_data()
    if not DATA.exists():
        sys.exit(f"{DATA} not found. Run the 'Refresh profile cards' workflow first, or use SAMPLE=1 to preview.")
    return json.loads(DATA.read_text(encoding="utf-8"))


def portrait_uri() -> str | None:
    path = next((p for p in PORTRAIT_CANDIDATES if p.exists()), None)
    if not path:
        return None
    try:
        from PIL import Image  # optional: keeps the SVG small
        import io
        im = Image.open(path).convert("RGB")
        s = min(im.size)
        l, t = (im.width - s) // 2, (im.height - s) // 2
        im = im.crop((l, t, l + s, t + s)).resize((320, 320))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=86)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except ImportError:
        mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}[path.suffix[1:]]
        return f"data:image/{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def stats(days: list[dict]) -> dict:
    days = sorted(days, key=lambda d: d["date"])
    counts = [d["count"] for d in days]
    cur = 0
    seq = counts[:-1] if counts and counts[-1] == 0 else counts  # today may still be empty
    for c in reversed(seq):
        if c <= 0:
            break
        cur += 1
    longest = run = 0
    for c in counts:
        run = run + 1 if c > 0 else 0
        longest = max(longest, run)
    best = max(days, key=lambda d: d["count"])
    return dict(total=sum(counts), active=sum(1 for c in counts if c > 0), span=len(days),
                current=cur, longest=longest, best=best["count"],
                best_date=dt.date.fromisoformat(best["date"]),
                first=dt.date.fromisoformat(days[0]["date"]), last=dt.date.fromisoformat(days[-1]["date"]))


# --------------------------------------------------------------------------- cards
def hero() -> str:
    H = 260
    uri = portrait_uri()
    nsize = 64
    namew = len(NAME) * adv(nsize)
    if uri:
        x0, avail = 56, 560
        tsize = min(20, avail / (ADV * len(TAGLINE)))
        tx = x0
    else:
        avail = W - 96
        tsize = min(20, avail / (ADV * len(TAGLINE)))
        x0 = (W - namew) / 2
        tx = (W - len(TAGLINE) * adv(tsize)) / 2
    y_name, y_tag, y_line = 126, 170, 192
    t0 = SCHED["hero"]
    char_t, step = t0 + 0.45, 0.08

    b = ['<defs><radialGradient id="g" cx="15%" cy="0%" r="75%">'
         f'<stop offset="0" stop-color="{ACCENT}" stop-opacity=".16"/>'
         f'<stop offset="1" stop-color="{ACCENT}" stop-opacity="0"/></radialGradient></defs>',
         panel(W, H, t0, edge_opacity=0.4),
         f'<rect class="fade" width="{W}" height="{H}" rx="16" fill="url(#g)"{D(t0 + 0.2)}/>']
    for i, ch in enumerate(NAME):
        if ch != " ":
            b.append(text(x0 + i * adv(nsize), y_name, ch, nsize, "t b", char_t + i * step, kind="type"))
    end_t = char_t + len(NAME) * step
    b.append(text(tx, y_tag, TAGLINE, round(tsize, 1), "s", end_t + 0.15))
    b.append(f'<line class="draw" x1="{x0:.1f}" y1="{y_line}" x2="{x0 + namew:.1f}" y2="{y_line}" '
             f'stroke="{ACCENT}" stroke-width="3" stroke-linecap="round" pathLength="1"{D(end_t + 0.35)}/>')
    b.append(smil(
        f'<rect x="{x0 + namew + 6:.1f}" y="{y_name - nsize * 0.74:.1f}" width="{nsize * 0.09:.1f}" '
        f'height="{nsize * 0.9:.1f}" fill="{ACCENT}" opacity="0">'
        f'<animate attributeName="opacity" values="1;0" keyTimes="0;.5" calcMode="discrete" '
        f'dur="1.1s" begin="{end_t:.2f}s" repeatCount="indefinite"/></rect>'))
    if uri:
        cx, cy, r = 690, 130, 80
        b.append(f'<clipPath id="pc"><circle cx="{cx}" cy="{cy}" r="{r}"/></clipPath>'
                 f'<image class="fade" href="{uri}" xlink:href="{uri}" x="{cx - r}" y="{cy - r}" '
                 f'width="{2 * r}" height="{2 * r}" preserveAspectRatio="xMidYMid slice" '
                 f'clip-path="url(#pc)"{D(t0 + 0.5)}/>'
                 f'<circle class="draw" cx="{cx}" cy="{cy}" r="{r + 10}" fill="none" stroke="{ACCENT}" '
                 f'stroke-width="2.5" stroke-linecap="round" pathLength="1" '
                 f'transform="rotate(-90 {cx} {cy})"{D(t0 + 0.6)}/>')
    return svg_doc(W, H, NAME, f"{NAME}. {TAGLINE}.", "".join(b))


def tile(i: int, glyph: str, title: str, sub: str) -> str:
    w, h = 270, 120
    t0 = SCHED["tiles"] + i * SCHED["tile_step"]
    gs = 15 if len(glyph) > 2 else 20
    b = [panel(w, h, t0, r=14),
         f'<rect class="fade" x="22" y="38" width="44" height="44" rx="11" fill="{EMPTY}" '
         f'stroke="{ACCENT}" stroke-opacity=".35"{D(t0 + 0.3)}/>',
         text(44, 60 + gs * 0.35, glyph, gs, "a b", t0 + 0.4, anchor="middle"),
         text(82, 57, title, 17, "t b", t0 + 0.45),
         text(82, 77, sub, 12, "m", t0 + 0.55)]
    return svg_doc(w, h, title, f"{title}: {sub}", "".join(b))


def activity(st: dict, days: list[dict]) -> str:
    H = 344
    t0 = SCHED["activity"]
    # contributions per calendar month across the data window
    by_month: dict[tuple[int, int], int] = {}
    for d in days:
        dd = dt.date.fromisoformat(d["date"])
        by_month[(dd.year, dd.month)] = by_month.get((dd.year, dd.month), 0) + d["count"]
    keys = sorted(by_month)
    vals = [by_month[k] for k in keys]
    vmax = max(vals + [1])
    base_y, max_h = 292, 150
    area_x, area_w = 32, 528
    pitch = area_w / len(keys)
    bw = pitch * 0.62

    total_s = f"{st['total']:,}"
    b = [panel(W, H, t0),
         text(32, 66, total_s, 34, "a b", t0 + 0.3),
         text(32 + len(total_s) * adv(34) + 12, 66, "contributions in the last year", 15, "s", t0 + 0.35),
         f'<line x1="{area_x}" y1="{base_y}" x2="{area_x + area_w}" y2="{base_y}" stroke="{EDGE}"/>']
    peak = vals.index(max(vals))
    for i, ((y, m), v) in enumerate(zip(keys, vals)):
        x = area_x + i * pitch + (pitch - bw) / 2
        h = max(2.0, v / vmax * max_h)
        op = 1 if i == peak else 0.42
        dl = t0 + 0.5 + i * 0.05
        b.append(f'<rect class="grow" x="{x:.1f}" y="{base_y - h:.1f}" width="{bw:.1f}" height="{h:.1f}" '
                 f'rx="3" fill="{ACCENT}" fill-opacity="{op}"{D(dl)}/>')
        b.append(text(x + bw / 2, base_y - h - 8, f"{v:,}", 11, "s" if i == peak else "m", dl + 0.5, "middle"))
        b.append(text(x + bw / 2, base_y + 22, MONTHS[m - 1], 11, "m", t0 + 0.4, "middle"))

    b.append(f'<line x1="592" y1="96" x2="592" y2="322" stroke="{EDGE}" stroke-opacity=".7"/>')
    sx = 616
    blocks = [
        ("Current streak", str(st["current"]), " day" + ("" if st["current"] == 1 else "s"),
         f"Longest: {st['longest']} day" + ("" if st["longest"] == 1 else "s")),
        ("Active days", str(st["active"]), f" / {st['span']}", f"{st['active'] / st['span']:.0%} of days"),
        ("Busiest day", str(st["best"]), " contributions", fmt_date(st["best_date"])),
    ]
    for k, (label, val, unit, sub) in enumerate(blocks):
        y0 = 104 + k * 80
        dl = t0 + 0.6 + k * 0.2
        b.append(text(sx, y0, label, 13, "m", dl))
        b.append(f'<text x="{sx}" y="{y0 + 34}" font-size="30" class="t b fade"{D(dl + 0.1)}>{escape(val)}'
                 f'<tspan font-size="14" class="m n">{escape(unit)}</tspan></text>')
        b.append(text(sx, y0 + 54, sub, 12, "m", dl + 0.15))
    if st["current"] > 0:
        dx, dy = sx + len("Current streak") * adv(13) + 12, 100
        b.append(f'<circle class="fade" cx="{dx:.1f}" cy="{dy}" r="4" fill="{ACCENT}"{D(t0 + 0.8)}/>')
        b.append(smil(f'<circle cx="{dx:.1f}" cy="{dy}" r="4" fill="none" stroke="{ACCENT}" stroke-opacity="0">'
                      f'<animate attributeName="r" values="4;11" dur="2.2s" begin="{t0 + 1.2:.2f}s" repeatCount="indefinite"/>'
                      f'<animate attributeName="stroke-opacity" values=".8;0" dur="2.2s" begin="{t0 + 1.2:.2f}s" '
                      f'repeatCount="indefinite"/></circle>'))
    desc = (f"{st['total']:,} contributions in the last year. Current streak {st['current']} days, "
            f"{st['active']} active days, busiest day {st['best']} contributions on {fmt_date(st['best_date'])}.")
    return svg_doc(W, H, "Contributions per month", desc, "".join(b))


def repo_card(idx: int, r: dict) -> str:
    H = 150
    t0 = SCHED["repo"] + idx * SCHED["repo_step"]
    owner = LOGIN
    name = r["name"]
    desc = r.get("description") or "No description yet."
    lines = textwrap.wrap(desc, width=int((W - 64) / adv(14)))[:2]
    if len(textwrap.wrap(desc, width=int((W - 64) / adv(14)))) > 2:
        lines[1] = lines[1][:-1].rstrip() + "…"
    b = [panel(W, H, t0),
         f'<text x="32" y="48" font-size="20" class="t b fade"{D(t0 + 0.3)}>'
         f'<tspan class="m n">{escape(owner)}/</tspan><tspan class="a">{escape(name)}</tspan></text>']
    for i, ln in enumerate(lines):
        b.append(text(32, 78 + i * 22, ln, 14, "s", t0 + 0.45 + i * 0.1))
    cy, x = 124, 32
    lang = r.get("language")
    if lang:
        col = r.get("languageColor") or LANG_COLORS.get(lang, ACCENT)
        b.append(f'<circle class="fade" cx="{x + 5}" cy="{cy - 4}" r="5" fill="{col}"{D(t0 + 0.7)}/>')
        b.append(text(x + 18, cy, lang, 13, "m", t0 + 0.7))
        x += 18 + len(lang) * adv(13) + 28
    stars, forks = f"{r.get('stars', 0):,}", f"{r.get('forks', 0):,}"
    # star icon
    pts = " ".join(f"{x + 7 + (7 if k % 2 == 0 else 3.2) * math.sin(k * math.pi / 5):.1f},"
                   f"{cy - 5 - (7 if k % 2 == 0 else 3.2) * math.cos(k * math.pi / 5):.1f}" for k in range(10))
    b.append(f'<polygon class="fade" points="{pts}" fill="none" stroke="{MUTED}" stroke-width="1.4" '
             f'stroke-linejoin="round"{D(t0 + 0.8)}/>')
    b.append(text(x + 20, cy, stars, 13, "m", t0 + 0.8))
    x += 20 + len(stars) * adv(13) + 24
    # fork icon
    b.append(f'<g class="fade" fill="none" stroke="{MUTED}" stroke-width="1.4" stroke-linecap="round"{D(t0 + 0.9)}>'
             f'<circle cx="{x + 3}" cy="{cy - 11}" r="2"/><circle cx="{x + 11}" cy="{cy - 11}" r="2"/>'
             f'<circle cx="{x + 7}" cy="{cy - 1}" r="2"/>'
             f'<path d="M{x + 3},{cy - 9} v2 q0,2 2,2 h4 q2,0 2,-2 v-2 M{x + 7},{cy - 5} v2"/></g>')
    b.append(text(x + 20, cy, forks, 13, "m", t0 + 0.9))
    return svg_doc(W, H, f"{owner}/{name}", f"{name}: {desc}", "".join(b))


def graph(st: dict, days: list[dict]) -> str:
    days = sorted(days, key=lambda d: d["date"])
    t0 = SCHED["graph"]
    first = dt.date.fromisoformat(days[0]["date"])
    offset = (first.weekday() + 1) % 7  # weeks start on Sunday, like GitHub
    cols = math.ceil((offset + len(days)) / 7)
    gx, gy = 64, 96
    pitch = (W - 32 - gx) / cols
    cell = pitch * 0.78
    H = int(gy + 7 * pitch + 66)

    nz = sorted(d["count"] for d in days if d["count"] > 0)
    q = [nz[int(len(nz) * p)] for p in (0.25, 0.5, 0.75)] if nz else [1, 2, 3]
    shades = [mix(EMPTY, ACCENT, t) for t in (0, 0.3, 0.55, 0.78, 1.0)]

    def level(c: int) -> int:
        return 0 if c <= 0 else 1 + sum(c > v for v in q)

    grid: dict[tuple[int, int], dict] = {}
    for i, d in enumerate(days):
        grid[((offset + i) // 7, (offset + i) % 7)] = d

    b = [panel(W, H, t0),
         text(32, 44, "Daily activity", 15, "t b", t0 + 0.3),
         text(W - 32, 44, f"{fmt_date(st['first'])} to {fmt_date(st['last'])}", 12, "m", t0 + 0.35, "end")]
    # month labels: the column holding the 1st of each month
    marks = [(c, MONTHS[dt.date.fromisoformat(grid[(c, r)]["date"]).month - 1])
             for c in range(cols) for r in range(7)
             if (c, r) in grid and dt.date.fromisoformat(grid[(c, r)]["date"]).day == 1]
    if marks and marks[0][0] >= 3:
        marks.insert(0, (0, MONTHS[first.month - 1]))
    for c, m in marks:
        b.append(text(gx + c * pitch, gy - 12, m, 11, "m", t0 + 0.4))
    for r, lab in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        b.append(text(32, gy + r * pitch + cell * 0.8, lab, 10, "m", t0 + 0.4))
    for c in range(cols):
        cells = []
        for r in range(7):
            d = grid.get((c, r))
            if d:
                cells.append(f'<rect x="{gx + c * pitch:.1f}" y="{gy + r * pitch:.1f}" width="{cell:.1f}" '
                             f'height="{cell:.1f}" rx="2.5" fill="{shades[level(d["count"])]}"/>')
        b.append(f'<g class="fade"{D(t0 + 0.5 + c * 0.014)}>{"".join(cells)}</g>')
    lc, lr = max((c, r) for (c, r) in grid)
    b.append(smil(f'<rect x="{gx + lc * pitch - 1.5:.1f}" y="{gy + lr * pitch - 1.5:.1f}" width="{cell + 3:.1f}" '
                  f'height="{cell + 3:.1f}" rx="4" fill="none" stroke="{ACCENT}" stroke-opacity="0">'
                  f'<animate attributeName="stroke-opacity" values="0;.9;0" dur="2.4s" '
                  f'begin="{t0 + 1.6:.2f}s" repeatCount="indefinite"/></rect>'))
    # legend, laid out from the right edge
    ly, x = H - 28, W - 32
    x -= 4 * adv(11)
    b.append(text(x, ly + 9, "More", 11, "m", t0 + 1.2))
    x -= 5
    for s in reversed(shades):
        x -= 14
        b.append(f'<rect class="fade" x="{x:.1f}" y="{ly}" width="11" height="11" rx="2.5" fill="{s}"{D(t0 + 1.2)}/>')
    x -= 5 + 4 * adv(11)
    b.append(text(x, ly + 9, "Less", 11, "m", t0 + 1.2))
    return svg_doc(W, H, "Contribution graph", f"Daily contributions from {fmt_date(st['first'])} to {fmt_date(st['last'])}.",
                   "".join(b))


# --------------------------------------------------------------------------- main
def main() -> None:
    data = load_data()
    days = data["days"]
    if not days:
        sys.exit("No contribution days in the data file.")
    st = stats(days)
    repos = {r["name"]: r for r in data.get("repos", [])}
    OUT.mkdir(parents=True, exist_ok=True)

    cards = {"hero.svg": hero()}
    for i, (g, t, s, fn) in enumerate(TILES):
        cards[fn] = tile(i, g, t, s)
    cards["activity.svg"] = activity(st, days)
    for i, name in enumerate(FEATURED):
        cards[f"repo-{name.lower()}.svg"] = repo_card(i, repos.get(name, {"name": name}))
    cards["graph.svg"] = graph(st, days)

    for fn, svg in cards.items():
        (OUT / fn).write_text(svg, encoding="utf-8")
        print(f"{OUT / fn}  {len(svg) / 1024:.1f} KB")
    print("static final frame" if STATIC else "animated")


if __name__ == "__main__":
    main()
