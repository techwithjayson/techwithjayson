# Deploy checklist — `techwithjayson/techwithjayson`

**Live now:** banner (both themes), contribution snake, and all four badges.
Verified on the rendered profile page, not just locally.

**Nothing outstanding.** The stats cards were removed (Phase 2) after the
METRICS_TOKEN secret was never set. They are optional and documented there if
you ever want them back.

Phases 0, 1, 3 and 4 are marked **Done** below and kept for reference.

---

## Phase 0 — The profile repo ✅ Done

**Done.** The repo exists and this whole folder is committed to
`techwithjayson/techwithjayson` on `main` — banner, README, workflow, and the
generator sources. Nothing to upload by hand.

Everything sits at the repo root, which is what matters: GitHub only renders a
profile README from a repo named exactly your username, and the raw URLs in
`README.md` point at `/main/dark.svg` and `/main/light.svg`.

The generator sources (`pipeline.py`, `build_svg.py`, `data/`, `preview/`,
`source/`) are public in that repo. That's a deliberate choice — it makes the
banner reproducible from a clean clone and shows the work. If you'd rather keep
them private, say so and I'll strip them out into a separate private repo; the
profile only needs `README.md`, `dark.svg`, `light.svg` and `.github/`.

**Test:** switch your GitHub theme (avatar → Settings → Appearance) and reload
your profile. The banner should swap between the green-on-dark and
green-on-white versions.

---

## Phase 1 — Banner ✅ Done

Live and animating on the profile. Confirmed rendering at its native
1180×610 through GitHub's `<img>` pipeline, so the SMIL animation survives.

The `<picture>` element is what makes GitHub swap by theme. Note that
**the banner SVGs cannot contain working links** — GitHub strips them. That's
why the clickable links are badges at the bottom of the README instead.

---

## Phase 2 — Stats cards ⏸️ Removed (optional)

**The stats cards are not in the README.** They were removed after the
`METRICS_TOKEN` secret was never set — the workflow's guard step confirmed the
secret was empty, so the renders could not run and the images 404'd.

Nothing is broken and nothing is outstanding. The profile is complete without
them: banner, snake, badges, and GitHub's own contribution graph.

`.github/workflows/metrics.yml` is still here but **manual-only** (the daily
cron is commented out, so it cannot fail in the background).

### To turn them on later — 3 steps

1. Add a **scope-less classic PAT** as the `METRICS_TOKEN` repository secret:
   Settings → Secrets and variables → Actions → New repository secret. The name
   must be exactly `METRICS_TOKEN`. *Generating the token is not enough — it has
   to be pasted into that field.*
2. Actions → **Generate Metrics Cards** → Run workflow
3. Put them back in the README:

```bash
python make_readme.py --cards metrics
```

Then commit `README.md`. Optionally uncomment the cron in the workflow.

### Why not the Vercel route

GitHub routes third-party README images through its **camo** proxy, which gives
up after roughly 4.3 seconds. Files committed to your own repo skip camo
entirely — which is why the banner and snake render instantly.

What I actually measured:

| Host | Measured |
|---|---|
| `github-readme-stats.vercel.app` (public) | **503 Service Unavailable** |
| `streak-stats.demolab.com` (public) | **~9.8s** — camo abandons at **~4.3s** |
| `raw.githubusercontent.com` (banner, snake) | **instant, not camo-proxied** |

To be precise about what that does and doesn't prove: I measured the **public**
instances, and both are unusable. A **self-hosted** Vercel instance is not
shared, so it would very likely answer fast enough for camo — the Vercel route
can work. I did not measure one, because you would have had to build it first.

The reason to skip it anyway is cost, not feasibility: Vercel means two
deployments to keep alive and a token with **full `repo` scope**. Generating
the cards in this repo removes the host question entirely and needs a
**scope-less** token. That's the trade — a narrower credential and one less
moving part, not a workaround for something impossible.

### Token details, if you do enable it

Create it at <https://github.com/settings/tokens> → **Tokens (classic)** →
**Generate new token (classic)**. **Tick no scopes at all** — public profile
data is all this needs.

> Even scope-less, that token is a credential tied to your account. It belongs
> in the repository-secret field and nowhere else — never in a chat, an issue,
> a commit, or a log. Anything that can show it back to you is the wrong place
> for it. If one is ever exposed, delete it at the link above and make a new
> one; the old one stays valid until you do.
>
> Optional: to include private contributions in the counts, enable *Include
> private contributions on my profile* in your account settings. Still no
> scopes required.

Six renders run one at a time (three cards × light and dark), roughly 4–6
minutes total, each committing its SVG to `main`.

### Fallback: the Vercel route

Still available if you ever want the original card style — deploy
`anuraghazra/github-readme-stats` and `DenverCoder1/github-readme-streak-stats`
with a `repo`-scoped token in `PAT_1`, then:

```bash
python make_readme.py --cards vercel --instance HOST.vercel.app --streak-instance STREAK.vercel.app
```

Note this needs a **full `repo` scope** token, versus none for the metrics
route.

---

## Phase 3 — Contribution snake ✅ Done

The workflow ran **green on the first push** and created the `output` branch —
your repo already had Read-and-write workflow permissions, so the usual
Settings → Actions → General step was not needed. Both SVGs are live and the
snake renders on the profile.

> If a future run ever fails with a permissions error, that's the setting to
> check: repo **Settings** → **Actions** → **General** → **Workflow
> permissions** → **Read and write**. It's the **repo's** Settings tab, not your
> account settings.

It regenerates every 12 hours. To force it: **Actions → Generate Snake
Animation → Run workflow**.

**The colour rule that matters:** the first colour in `color_dots` is the empty
cell. The dark snake uses `#2d3343` — a visible slate. Against GitHub's
`#0d1117` canvas, a near-black empty cell disappears and the grid looks broken.

---

## Phase 4 — Social badges ✅ Done

All four render on the live profile — LinkedIn (green glyph), Portfolio, npm,
Email. Two things worth knowing:

**The LinkedIn bug is real — I tested it.** Passing `logo=linkedin` with any
custom colour renders the word "LINKEDIN" with **no glyph at all**. Your badge
works around this by embedding the glyph as a base64 data-URI, which is why that
one URL is ~930 characters. The alternative is accepting brand blue `#0A66C2`.
Instagram, Gmail, npm, Vercel and GitHub logos all recolour normally.

**No GitHub badge** — it's circular on your own profile. The slots went to
Portfolio and your npm package instead.

**Facebook and Instagram are missing on purpose.** Your site's `layoutData.js`
has them as `'#'` placeholders, so I had nothing real to link. Send me the
handles and I'll add them — or add them yourself in `make_readme.py`, in the
`badges` list.

---

## Troubleshooting

### "I changed it but nothing happened"

This will happen, and it's almost always caching. Diagnose in this order:

1. **Check the file itself.** Open
   `https://raw.githubusercontent.com/techwithjayson/techwithjayson/main/dark.svg?v=999`
   — the `?v=` bypasses the CDN. Ctrl+U, then Ctrl+F for the hex colour you
   expect. If it's there, generation worked and only the display is stale.
2. **Check your theme.** Dark assets only render in dark mode. In light mode
   you are looking at a different file entirely.
3. **Check the Action ran.** Actions tab — is the newest run green and stamped
   *after* your edit?
4. **Then wait.** GitHub's CDN expires on its own, minutes to a few hours.
   Ctrl+Shift+R clears your browser, not their servers.

| Symptom | Cause |
|---|---|
| Card shows "API rate limit exceeded" | Using the public instance — self-host (Phase 2) |
| Stats cards are broken images | `METRICS_TOKEN` secret missing, or the metrics workflow has not run yet (Phase 2) |
| Snake image broken | `output` branch doesn't exist yet — run the Action |
| Snake grid invisible in dark mode | Empty-cell colour too close to `#0d1117` |
| LinkedIn badge has no logo | shields.io bug — needs `#0A66C2` or base64 |
| Action fails, mentions `maxDuration` | Vercel free-tier limit — set it to 10 in `vercel.json` |
| Colour change invisible | CDN cache, or you're in the other theme |
| Banner animates once then freezes | Expected — the intro plays once; the 14.2s loop continues |

### Good to know

- **Scheduled Actions pause after ~60 days of repo inactivity.** If you go
  quiet the snake freezes until you push or click "Enable workflow".
- **Stats totals won't match GitHub's exactly.** Different date windows and
  cache lag — a gap of a few contributions is normal.
- **Top-languages reflects code volume, not skill.** A template's CSS can
  dominate. Exclude repos if it misrepresents you.

---

## What to keep

`pipeline.py`, `build_svg.py` and `data/*.npy` are **the source of truth** — not
the SVGs. If you ever want to change the crop, contrast, palette, or timing,
edit the config block at the top of `pipeline.py` and re-run:

```bash
python pipeline.py && python build_svg.py
```

You need Python with Pillow, NumPy and SciPy:

```bash
pip install pillow numpy scipy
```

The source photograph is vendored at `source/jayson-profile.jpeg`, so a plain
clone of this repo rebuilds without needing the portfolio checkout. To use a
different photo, drop it in at that path (or edit `_find_photo()`), then re-run
both scripts.

`preview.html` renders both banners through `<img>` — the same way GitHub does,
so SMIL animation is actually exercised. `make_frames.py` builds `frames.html`,
a paused, seekable copy for checking any single moment of the loop.

Regenerating is deterministic: `SEED = 20260801` in `pipeline.py` means you get
byte-identical output unless you change a parameter.
