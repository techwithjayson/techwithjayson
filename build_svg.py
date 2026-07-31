"""
Phase 1 / stage 2 -- emit dark.svg and light.svg from the pipeline's .npy data.

Layout is a single 1180x610 terminal window:
  left  ~38%  portrait frame labelled VISUAL.MAP
  right       SYSTEM.INFO readout, dotted leaders, pulsing LIVE badge, handle pill

Animation is two independent layers over one clip:
  intro (~3.2s, once)  60 interleaved random groups fade in, scattered everywhere
  loop  (14.2s)        94 drift bands dissolve toward the first logo's centroid
                       900 travellers morph between the three logo point clouds

The intro needs its own duplicate copy of the portrait because its grouping
(random, for shimmer) is incompatible with the loop's grouping (spatial, for
drift). Merging them into one layer breaks the intro.

Run:  python build_svg.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

PITCH = 1.26
PORTRAIT_X0 = 47.0
PORTRAIT_Y0 = 88.0
GRID_W, GRID_H = 300, 340
PORTRAIT_W = GRID_W * PITCH
PORTRAIT_H = GRID_H * PITCH

W, H = 1180, 610

# --- timing ---------------------------------------------------------------
INTRO_SPAN = 2.0          # groups begin across this window
INTRO_FADE = 0.55         # each group's own fade duration
LOOP_BEGIN = 3.15         # loop layer switches on slightly early (no flicker)
INTRO_END = 3.2
LOOP_DUR = 14.2

# phase boundaries in seconds within the loop
PHASES = [0.0, 3.0, 4.3, 6.3, 7.6, 9.6, 10.9, 12.9, 14.2]
KEYTIMES = ";".join(f"{t / LOOP_DUR:.4f}".rstrip("0").rstrip(".") for t in PHASES)

TRAVELLER_R = 2.1

# --- type -----------------------------------------------------------------
MONO = "ui-monospace,SFMono-Regular,SF Mono,Menlo,Consolas,Liberation Mono,monospace"
FS_ROW = 14
FS_HEAD = 13
FS_LIVE = 12
FS_PILL = 14
ADV = 0.6                 # monospace advance ratio; textLength locks it anyway

ROW_X = 482.0
ROW_END = 1138.0
ROW_STEP = 23.0
SECTION_GAP = 14.0
ROW_TOP = 142.0

# All-green palette.
#
# The original spec kept the portrait a different HUE from the UI chrome so the
# face would not blend into its own frame. Going all-green removes that hue gap,
# so the separation is carried by LIGHTNESS instead: a mid-green portrait against
# pale-mint chrome. `frame` is deliberately desaturated -- the corner marks touch
# the dot field, and at the portrait's own green they merged into it.
THEMES = {
    "dark": dict(
        bg="#0d1117", panel="#11161f", panel_stroke="#232b39", titlebar="#161b22",
        portrait="#39d353", chrome="#7ee787", accent="#56d364", frame="#2f6f43",
        muted="#8b949e", bright="#e6edf3", live="#f85149", leader="#2d3343",
        pill_op="0.14",
    ),
    "light": dict(
        bg="#ffffff", panel="#f6f8fa", panel_stroke="#d0d7de", titlebar="#eaeef2",
        portrait="#1a7f37", chrome="#116329", accent="#1a7f37", frame="#a3c9ae",
        muted="#57606a", bright="#1f2328", live="#cf222e", leader="#d0d7de",
        pill_op="0.12",
    ),
}

SECTIONS = [
    [
        ("Subject", "Jayson Peralta"),
        ("Role", "Full-Stack Developer"),
        ("Origin", "Makati City, Philippines"),
        ("Education", "B.S. Computer Science · Cum Laude"),
        ("Status", "Building + Learning + Shipping"),
        ("ToolChain", "VS Code · Git · Docker · Figma"),
    ],
    [
        ("Core.Lang", "JavaScript · TypeScript · Python · SQL"),
        ("Core.Frontend", "React · Next.js · Tailwind · shadcn/ui"),
        ("Core.Backend", "Node.js · Express · FastAPI · Medusa"),
        ("Core.Database", "PostgreSQL · Supabase · MongoDB · MSSQL"),
        ("Core.Infra", "Docker · AWS · Vercel · DigitalOcean"),
    ],
    [
        ("Grid.Mail", "techwithjayson@gmail.com"),
        ("Grid.Portfolio", "techwithjayson.com"),
        ("Grid.LinkedIn", "/in/jayson-peralta"),
        ("Grid.GitHub", "@techwithjayson"),
        ("Grid.NPM", "@rx-ventures/medusa-flow-builder-plugin"),
    ],
]

HANDLE = "@techwithjayson"


def f(v: float) -> str:
    """Compact number formatting -- this runs ~30k times per file."""
    s = f"{v:.1f}"
    return s[:-2] if s.endswith(".0") else s


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, s, fill, size, anchor="start", weight=None, op=None) -> str:
    """Text with its advance width locked.

    textLength + lengthAdjust="spacingAndGlyphs" is what keeps values
    right-aligned when the viewer's monospace fallback differs from mine.
    """
    tl = len(s) * size * ADV
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    fw = f' font-weight="{weight}"' if weight else ""
    o = f' opacity="{op}"' if op else ""
    return (
        f'<text x="{f(x)}" y="{f(y)}" font-family="{MONO}" font-size="{size}"'
        f' fill="{fill}"{a}{fw}{o} textLength="{f(tl)}"'
        f' lengthAdjust="spacingAndGlyphs">{esc(s)}</text>'
    )


def adv(s: str, size: float) -> float:
    return len(s) * size * ADV


# --------------------------------------------------------------------------
# portrait layers
# --------------------------------------------------------------------------

def run_path(rle_rows: np.ndarray) -> str:
    """Encode runs as one path of horizontal segments.

    Stroked segments, not filled rects: half the bytes for the same pixels,
    and shape-rendering="crispEdges" keeps the lattice sharp.
    """
    parts = []
    for row, col, length, _ in rle_rows:
        x = PORTRAIT_X0 + col * PITCH
        y = PORTRAIT_Y0 + (row + 0.5) * PITCH
        parts.append(f"M{f(x)} {f(y)}h{f(length * PITCH)}")
    return "".join(parts)


def intro_layer(rle: np.ndarray, intro: np.ndarray, colour: str, n_groups: int) -> str:
    out = [f'<g id="intro" fill="none" stroke="{colour}" stroke-width="{f(PITCH)}"'
           f' shape-rendering="crispEdges">']
    for g in range(n_groups):
        sel = rle[intro == g]
        if not len(sel):
            continue
        begin = (g / n_groups) * INTRO_SPAN
        out.append(
            f'<g opacity="0"><animate attributeName="opacity" values="0;1"'
            f' dur="{INTRO_FADE}s" begin="{begin:.2f}s" fill="freeze"/>'
            f'<path d="{run_path(sel)}"/></g>'
        )
    out.append(
        f'<set attributeName="opacity" to="0" begin="{INTRO_END}s" fill="freeze"/>'
    )
    out.append("</g>")
    return "".join(out)


def loop_layer(rle: np.ndarray, band: np.ndarray, offsets: np.ndarray, colour: str) -> str:
    """94 drift bands. Each translates ~42% toward the first logo's centroid
    while fading, then returns."""
    out = [f'<g id="loop" opacity="0" fill="none" stroke="{colour}"'
           f' stroke-width="{f(PITCH)}" shape-rendering="crispEdges">',
           f'<set attributeName="opacity" to="1" begin="{LOOP_BEGIN}s" fill="freeze"/>']

    op_vals = "1;1;0;0;0;0;0;0;1"
    for b in range(len(offsets)):
        sel = rle[rle[:, 3] == b]
        if not len(sel):
            continue
        dx, dy = offsets[b]
        d = f"{f(dx)} {f(dy)}"
        tr = f"0 0;0 0;{d};{d};{d};{d};{d};{d};0 0"
        out.append(
            f'<g><animateTransform attributeName="transform" type="translate"'
            f' values="{tr}" keyTimes="{KEYTIMES}" dur="{LOOP_DUR}s"'
            f' begin="{LOOP_BEGIN}s" repeatCount="indefinite"/>'
            f'<animate attributeName="opacity" values="{op_vals}"'
            f' keyTimes="{KEYTIMES}" dur="{LOOP_DUR}s" begin="{LOOP_BEGIN}s"'
            f' repeatCount="indefinite"/>'
            f'<path d="{run_path(sel)}"/></g>'
        )
    out.append("</g>")
    return "".join(out)


def traveller_layer(P, L1, L2, L3, colour: str) -> str:
    """~900 dots morphing between logos, matched by optimal transport.

    Hidden during the portrait phase -- their thicker dots would otherwise
    crowd the fine dither.
    """
    out = [f'<g id="trav" opacity="0" fill="{colour}">',
           f'<animate attributeName="opacity" values="0;0;1;1;1;1;1;1;0"'
           f' keyTimes="{KEYTIMES}" dur="{LOOP_DUR}s" begin="{LOOP_BEGIN}s"'
           f' repeatCount="indefinite"/>']
    for i in range(len(P)):
        seq = [P[i], P[i], L1[i], L1[i], L2[i], L2[i], L3[i], L3[i], P[i]]
        vals = ";".join(f"{f(p[0])} {f(p[1])}" for p in seq)
        out.append(
            f'<circle r="{TRAVELLER_R}">'
            f'<animateTransform attributeName="transform" type="translate"'
            f' values="{vals}" keyTimes="{KEYTIMES}" dur="{LOOP_DUR}s"'
            f' begin="{LOOP_BEGIN}s" repeatCount="indefinite"/></circle>'
        )
    out.append("</g>")
    return "".join(out)


# --------------------------------------------------------------------------
# chrome
# --------------------------------------------------------------------------

def info_rows(t: dict) -> str:
    out = []
    y = ROW_TOP
    for si, section in enumerate(SECTIONS):
        for label, value in section:
            lw = adv(label, FS_ROW)
            vw = adv(value, FS_ROW)
            out.append(text(ROW_X, y, label, t["muted"], FS_ROW))
            out.append(text(ROW_END, y, value, t["bright"], FS_ROW, anchor="end"))

            x1 = ROW_X + lw + 8
            x2 = ROW_END - vw - 8
            if x2 > x1 + 6:
                out.append(
                    f'<line x1="{f(x1)}" y1="{f(y - 4)}" x2="{f(x2)}" y2="{f(y - 4)}"'
                    f' stroke="{t["leader"]}" stroke-width="1"'
                    f' stroke-dasharray="1.5 4.5" stroke-linecap="round"/>'
                )
            y += ROW_STEP
        if si < len(SECTIONS) - 1:
            out.append(
                f'<line x1="{f(ROW_X)}" y1="{f(y - 12)}" x2="{f(ROW_END)}" y2="{f(y - 12)}"'
                f' stroke="{t["panel_stroke"]}" stroke-width="1" opacity="0.7"/>'
            )
            y += SECTION_GAP
    return "".join(out)


def corner_marks(t: dict) -> str:
    """Four corner ticks around the portrait -- terminal framing, no grid lines.

    Uses `frame`, not `chrome`: these sit right against the dot field, and in an
    all-green palette a chrome-coloured tick reads as part of the portrait.
    """
    x0, y0 = PORTRAIT_X0 - 10, PORTRAIT_Y0 - 10
    x1, y1 = PORTRAIT_X0 + PORTRAIT_W + 10, PORTRAIT_Y0 + PORTRAIT_H + 10
    L = 14
    c = t["frame"]
    segs = [
        (x0, y0 + L, x0, y0, x0 + L, y0),
        (x1 - L, y0, x1, y0, x1, y0 + L),
        (x0, y1 - L, x0, y1, x0 + L, y1),
        (x1 - L, y1, x1, y1, x1, y1 - L),
    ]
    return "".join(
        f'<path d="M{f(a)} {f(b)}L{f(cx)} {f(cy)}L{f(dx)} {f(dy)}" fill="none"'
        f' stroke="{c}" stroke-width="1.4" opacity="0.55"/>'
        for a, b, cx, cy, dx, dy in segs
    )


def build(theme: str, metrics: dict) -> str:
    t = THEMES[theme]
    suffix = "dark" if theme == "dark" else "light"

    rle = np.load(DATA / f"{suffix}_rle.npy")
    band = np.load(DATA / f"{suffix}_band.npy")
    offsets = np.load(DATA / f"{suffix}_offsets.npy")
    intro = np.load(DATA / f"{suffix}_intro.npy")

    Pp = np.load(DATA / "traveller_portrait.npy")
    L1 = np.load(DATA / "logo_next.npy")
    L2 = np.load(DATA / "logo_code.npy")
    L3 = np.load(DATA / "logo_vercel.npy")

    ink = int(metrics[f"{suffix}_ink_cells"])
    n_intro = int(metrics["intro_groups"])

    s = []
    s.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}"'
        f' height="{H}" role="img" aria-label="Jayson Peralta, Full-Stack Developer'
        f' -- animated terminal profile banner">'
    )
    s.append(
        f'<defs><clipPath id="pclip"><rect x="{f(PORTRAIT_X0 - 2)}"'
        f' y="{f(PORTRAIT_Y0 - 2)}" width="{f(PORTRAIT_W + 4)}"'
        f' height="{f(PORTRAIT_H + 4)}"/></clipPath></defs>'
    )

    # window + title bar
    s.append(f'<rect width="{W}" height="{H}" rx="14" fill="{t["bg"]}"/>')
    s.append(
        f'<path d="M0 14a14 14 0 0 1 14-14h{W - 28}a14 14 0 0 1 14 14v26H0z"'
        f' fill="{t["titlebar"]}"/>'
    )
    s.append(f'<line x1="0" y1="40" x2="{W}" y2="40" stroke="{t["panel_stroke"]}" stroke-width="1"/>')
    for i, col in enumerate(("#ff5f57", "#febc2e", "#28c840")):
        s.append(f'<circle cx="{22 + i * 20}" cy="20" r="5.5" fill="{col}"/>')
    s.append(text(W / 2 - adv("profile.sh --live", 12.5) / 2, 25, "profile.sh --live",
                  t["muted"], 12.5))
    s.append(f'<rect width="{W - 1}" height="{H - 1}" x="0.5" y="0.5" rx="14"'
             f' fill="none" stroke="{t["panel_stroke"]}" stroke-width="1"/>')

    # portrait panel
    s.append(f'<rect x="24" y="56" width="424" height="530" rx="10"'
             f' fill="{t["panel"]}" stroke="{t["panel_stroke"]}" stroke-width="1"/>')
    s.append(text(40, 79, "VISUAL.MAP", t["chrome"], 11))
    s.append(text(408 - adv("300x340", 11), 79, "300x340", t["muted"], 11))
    s.append(corner_marks(t))

    s.append('<g clip-path="url(#pclip)">')
    s.append(intro_layer(rle, intro, t["portrait"], n_intro))
    s.append(loop_layer(rle, band, offsets, t["portrait"]))
    s.append(traveller_layer(Pp, L1, L2, L3, t["portrait"]))
    s.append("</g>")

    s.append(f'<line x1="47" y1="534" x2="425" y2="534" stroke="{t["panel_stroke"]}"'
             f' stroke-width="1"/>')
    s.append(text(47, 552, "DITHER  FLOYD-STEINBERG 1-BIT", t["muted"], 10.5))
    s.append(text(47, 569, f"DOTS {ink:,}  BANDS 94  TRAVELLERS 900", t["muted"], 10.5))

    # info panel
    s.append(f'<rect x="464" y="56" width="692" height="530" rx="10"'
             f' fill="{t["panel"]}" stroke="{t["panel_stroke"]}" stroke-width="1"/>')

    pill_w = adv(HANDLE, FS_PILL) + 26
    s.append(f'<rect x="{f(ROW_X)}" y="76" width="{f(pill_w)}" height="26" rx="13"'
             f' fill="{t["chrome"]}" fill-opacity="{t["pill_op"]}"'
             f' stroke="{t["chrome"]}" stroke-opacity="0.45" stroke-width="1"/>')
    s.append(text(ROW_X + 13, 94, HANDLE, t["chrome"], FS_PILL, weight="600"))
    s.append(text(ROW_X + pill_w + 18, 94, "SYSTEM.INFO", t["muted"], FS_HEAD))

    lx = ROW_END - adv("LIVE", FS_LIVE)
    s.append(f'<circle cx="{f(lx - 16)}" cy="90" r="4" fill="{t["live"]}">'
             f'<animate attributeName="opacity" values="1;0.25;1" dur="1.6s"'
             f' repeatCount="indefinite"/></circle>')
    s.append(f'<circle cx="{f(lx - 16)}" cy="90" r="4" fill="none"'
             f' stroke="{t["live"]}" stroke-width="1.2">'
             f'<animate attributeName="r" values="4;10" dur="1.6s" repeatCount="indefinite"/>'
             f'<animate attributeName="opacity" values="0.7;0" dur="1.6s"'
             f' repeatCount="indefinite"/></circle>')
    s.append(text(lx, 94, "LIVE", t["live"], FS_LIVE, weight="600"))

    s.append(f'<line x1="{f(ROW_X)}" y1="118" x2="{f(ROW_END)}" y2="118"'
             f' stroke="{t["panel_stroke"]}" stroke-width="1"/>')
    s.append(info_rows(t))

    s.append(f'<line x1="{f(ROW_X)}" y1="540" x2="{f(ROW_END)}" y2="540"'
             f' stroke="{t["panel_stroke"]}" stroke-width="1" opacity="0.7"/>')
    s.append(text(ROW_X, 562, "$ open techwithjayson.com", t["accent"], 12))
    s.append(text(ROW_END - adv("5+ YRS  ·  SHIPPING", 11), 562,
                  "5+ YRS  ·  SHIPPING", t["muted"], 11))

    s.append("</svg>")
    return "".join(s)


def main():
    metrics = json.loads((DATA / "metrics.json").read_text())
    for theme in ("dark", "light"):
        svg = build(theme, metrics)
        out = ROOT / f"{theme}.svg"
        out.write_text(svg, encoding="utf-8")
        print(f"{out.name:10s} {len(svg.encode('utf-8')) / 1024:8.1f} KB")


if __name__ == "__main__":
    main()
