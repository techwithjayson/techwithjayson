"""
Assemble README.md for techwithjayson/techwithjayson.

Generated rather than hand-written for two reasons: the themed LinkedIn badge
is a ~930 character data-URI that is miserable to edit by hand, and the stats
cards need your Vercel instance host substituted in four places.

Once Vercel gives you a host (Phase 2 of SETUP.md):

    python make_readme.py --instance techwithjayson-stats.vercel.app

Run with no arguments and it emits the placeholder form.
"""

from __future__ import annotations

import argparse
import base64
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent

USER = "techwithjayson"
BRANCH = "main"
RAW = f"https://raw.githubusercontent.com/{USER}/{USER}"

LINKEDIN_URL = "https://www.linkedin.com/in/jayson-peralta-574282173/"
EMAIL = "techwithjayson@gmail.com"
PORTFOLIO = "https://techwithjayson.com"
NPM_PKG = "https://www.npmjs.com/package/@rx-ventures/medusa-flow-builder-plugin"

# Measured 2026-08-01: this shared instance answers in ~9.8s regardless of
# parameters, while GitHub's camo image proxy abandons the fetch at ~4.3s. The
# card is therefore permanently broken on a profile page, however correct the
# URL is. Self-hosting is the only fix.
PUBLIC_STREAK = "streak-stats.demolab.com"

# All-green palette. `portrait` is the badge glyph colour here -- kept as the
# same mid-green the banner portrait uses so badges and banner read as one set.
D = dict(bg="0d1117", chrome="7ee787", portrait="39d353", accent="56d364",
         text="8b949e", bright="e6edf3", dates="6e7681")
L = dict(bg="ffffff", chrome="116329", portrait="1a7f37", accent="1a7f37",
         text="57606a", bright="1f2328", dates="6e7681")

LINKEDIN_PATH = (
    "M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 "
    "1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 "
    "3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 "
    "0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 "
    "2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11"
    ".452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 "
    "24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.225 0z"
)


def linkedin_logo(colour: str) -> str:
    """LinkedIn's glyph as a percent-encoded data-URI.

    shields.io silently drops the named `logo=linkedin` glyph on any custom
    colour -- verified, you get the bare word. Embedding the path keeps the
    badge on-palette. The `+`, `/` and `=` in base64 all have meaning in a
    query string, so the whole payload must be percent-encoded.
    """
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'fill="#{colour}"><path d="{LINKEDIN_PATH}"/></svg>'
    )
    b64 = base64.b64encode(svg.encode()).decode()
    return "data%3Aimage%2Fsvg%2Bxml%3Bbase64%2C" + urllib.parse.quote(b64, safe="")


def badge(label: str, t: dict, logo: str | None = None, colour: str | None = None) -> str:
    q = [f"style=for-the-badge", f"labelColor={t['bg']}"]
    if logo:
        q.append(f"logo={logo}")
    if colour:
        q.append(f"logoColor={colour}")
    return f"https://img.shields.io/badge/{label}-{t['bg']}?" + "&".join(q)


def streak(host: str, t: dict) -> str:
    return (
        f"https://{host}/?"
        f"user={USER}&hide_border=true&background={t['bg']}&stroke={t['chrome']}"
        f"&ring={t['portrait']}&fire={t['accent']}&currStreakLabel={t['chrome']}"
        f"&sideLabels={t['text']}&currStreakNum={t['bright']}&sideNums={t['bright']}"
        f"&dates={t['dates']}&titleColor={t['chrome']}&card_width=1180"
    )


def stats(host: str, t: dict) -> str:
    return (
        f"https://{host}/api?username={USER}&show_icons=true&count_private=true"
        f"&include_all_commits=true&hide_rank=true&hide_border=true"
        f"&title_color={t['chrome']}&icon_color={t['portrait']}&text_color={t['text']}"
        f"&bg_color={t['bg']}&card_width=500"
    )


def langs(host: str, t: dict) -> str:
    return (
        f"https://{host}/api/top-langs/?username={USER}&layout=compact&langs_count=8"
        f"&hide_border=true&title_color={t['chrome']}&text_color={t['text']}"
        f"&bg_color={t['bg']}&card_width=500"
    )


def a(url: str) -> str:
    """Escape a URL for use inside an HTML attribute.

    Bare `&` mostly works in READMEs, but it is not valid HTML and it puts every
    query parameter one legacy-entity name away from being silently mangled.
    """
    return url.replace("&", "&amp;")


def metrics_card(name: str) -> tuple[str, str]:
    """A metrics render committed into this repo, dark and light.

    Served from raw.githubusercontent.com, which GitHub does NOT route through
    the camo image proxy -- the same path as the banner and snake, both of
    which render instantly. That is the entire reason these replaced the
    Vercel-hosted cards.
    """
    return (f"{RAW}/{BRANCH}/metrics-{name}-dark.svg",
            f"{RAW}/{BRANCH}/metrics-{name}-light.svg")


def pic(dark: str, light: str, alt: str, width: str) -> str:
    return (
        "  <picture>\n"
        f'    <source media="(prefers-color-scheme: dark)" srcset="{a(dark)}" />\n'
        f'    <source media="(prefers-color-scheme: light)" srcset="{a(light)}" />\n'
        f'    <img width="{width}" alt="{alt}" src="{a(light)}" />\n'
        "  </picture>"
    )


def stats_block(cards: str, host: str, streak_host: str) -> str:
    if cards == "none":
        return ""
    if cards == "metrics":
        cal_d, cal_l = metrics_card("calendar")
        st_d, st_l = metrics_card("stats")
        lg_d, lg_l = metrics_card("languages")
        return (
            pic(cal_d, cal_l, "Contribution calendar", "100%") + "\n\n"
            + pic(st_d, st_l, "GitHub stats", "49%") + "\n"
            + pic(lg_d, lg_l, "Top languages", "49%")
        )
    return (
        pic(streak(streak_host, D), streak(streak_host, L), "Contribution streak", "100%")
        + "\n\n"
        + pic(stats(host, D), stats(host, L), "GitHub stats", "49%") + "\n"
        + pic(langs(host, D), langs(host, L), "Top languages", "49%")
    )


def build(cards: str, host: str, streak_host: str) -> str:
    ld, ll = linkedin_logo(D["portrait"]), linkedin_logo(L["portrait"])

    badges = [
        (LINKEDIN_URL, "LinkedIn",
         badge("LinkedIn", D, ld), badge("LinkedIn", L, ll)),
        (PORTFOLIO, "Portfolio",
         badge("Portfolio", D, "vercel", D["portrait"]),
         badge("Portfolio", L, "vercel", L["portrait"])),
        (NPM_PKG, "npm",
         badge("npm", D, "npm", D["chrome"]), badge("npm", L, "npm", L["chrome"])),
        (f"mailto:{EMAIL}", "Email",
         badge("Email", D, "gmail", D["accent"]), badge("Email", L, "gmail", L["accent"])),
    ]

    badge_html = "\n  &nbsp;&nbsp;\n".join(
        f'  <a href="{href}">\n'
        f'    <picture>\n'
        f'      <source media="(prefers-color-scheme: dark)" srcset="{a(dk)}" />\n'
        f'      <source media="(prefers-color-scheme: light)" srcset="{a(lt)}" />\n'
        f'      <img alt="{alt}" src="{a(lt)}" />\n'
        f'    </picture>\n'
        f'  </a>'
        for href, alt, dk, lt in badges
    )

    block = stats_block(cards, host, streak_host)
    stats_section = "" if not block else f"""
<!-- ------------------------------------------------------------------ -->
<!-- STATS  --  see SETUP.md Phase 2                                     -->
<!-- ------------------------------------------------------------------ -->
<div align="center">

{block}

</div>
"""

    return f"""<!-- ------------------------------------------------------------------ -->
<!-- BANNER  --  dark.svg / light.svg live in the root of this repo        -->
<!-- ------------------------------------------------------------------ -->
<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="{RAW}/{BRANCH}/dark.svg" />
    <source media="(prefers-color-scheme: light)" srcset="{RAW}/{BRANCH}/light.svg" />
    <img alt="Jayson Peralta -- Full-Stack Developer" src="{RAW}/{BRANCH}/light.svg" />
  </picture>
</div>
{stats_section}
<!-- ------------------------------------------------------------------ -->
<!-- SNAKE  --  only works AFTER the Action has run green once           -->
<!-- ------------------------------------------------------------------ -->
<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="{RAW}/output/github-snake-dark.svg" />
    <source media="(prefers-color-scheme: light)" srcset="{RAW}/output/github-snake.svg" />
    <img alt="Snake eating my contributions" src="{RAW}/output/github-snake.svg" />
  </picture>
</div>

<!-- ------------------------------------------------------------------ -->
<!-- BADGES                                                              -->
<!-- ------------------------------------------------------------------ -->
<div align="center">

{badge_html}

</div>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--instance", default="YOUR-INSTANCE.vercel.app",
        help="your github-readme-stats Vercel host, e.g. jp-stats.vercel.app",
    )
    ap.add_argument(
        "--streak-instance", default=PUBLIC_STREAK,
        help=(
            "your github-readme-streak-stats Vercel host. The public instance "
            f"({PUBLIC_STREAK}) takes ~9.8s to respond and GitHub's camo proxy "
            "gives up at ~4.3s, so the card never renders -- self-host it."
        ),
    )
    ap.add_argument(
        "--cards", choices=("none", "metrics", "vercel"), default="none",
        help=(
            "none (default): no stats cards at all. "
            "metrics: SVGs generated by .github/workflows/metrics.yml and served "
            "from this repo -- needs the METRICS_TOKEN secret. "
            "vercel: the github-readme-stats / streak-stats cards."
        ),
    )
    args = ap.parse_args()

    out = ROOT / "README.md"
    out.write_text(
        build(args.cards, args.instance, args.streak_instance), encoding="utf-8"
    )

    if args.cards == "none":
        print("wrote README.md with no stats cards.")
        print("To bring them back: set the METRICS_TOKEN secret, then")
        print("  python make_readme.py --cards metrics")
        return

    if args.cards == "metrics":
        print("wrote README.md using in-repo metrics renders (no third-party host).")
        print("These 404 until 'Generate Metrics Cards' has run green at least once.")
        return

    if "YOUR-INSTANCE" in args.instance:
        print("wrote README.md with a PLACEHOLDER stats host.")
        print("Re-run with --instance <host>.vercel.app after deploying (SETUP.md Phase 2).")
    else:
        print(f"wrote README.md pointing stats at {args.instance}")

    if args.streak_instance == PUBLIC_STREAK:
        print(f"WARNING: streak card still points at {PUBLIC_STREAK}.")
        print("         Measured ~9.8s response vs camo's ~4.3s timeout -- it will")
        print("         render as a broken image. Self-host it and pass")
        print("         --streak-instance <host>.vercel.app (SETUP.md Phase 2d).")


if __name__ == "__main__":
    main()
