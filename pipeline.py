"""
Phase 1 / stage 1 -- portrait pipeline for the techwithjayson animated banner.

Turns one photograph into the dot data the SVG builder consumes:

  * head-and-shoulders crop -> 300x340 working grid
  * autocontrast(cutoff=1) -> Contrast(1.3x) -> UnsharpMask(r=3, 140%)
  * 1-bit Floyd-Steinberg dither, serpentine scan order
  * dark mode: background segmented out, error-diffusion bleed hard-cleared
  * light mode: background kept but tonally lifted so it reads as texture
  * three logo point clouds (Next.js / </> / Vercel) at 900 points each
  * optimal-transport matching so travellers take the shortest path
  * ~94 drift bands with per-dot noise so the dissolve is not a grid
  * ~60 interleaved intro groups scattered across the whole portrait

Everything lands in data/*.npy -- that, plus this script, is the source of
truth. The SVG is a build artifact.

Run:  python pipeline.py            (writes npy + preview PNGs + metrics)
      python pipeline.py --preview  (preview PNGs and metrics only)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps
from scipy import ndimage
from scipy.optimize import linear_sum_assignment

# --------------------------------------------------------------------------
# configuration
# --------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
PREVIEW = ROOT / "preview"

def _find_photo() -> Path:
    """Locate the source photograph.

    Prefer the copy vendored beside this script so the repo is self-contained
    and re-runnable after a plain clone; fall back to the portfolio checkout
    for when this folder still lives inside it.
    """
    candidates = [
        ROOT / "source" / "jayson-profile.jpeg",
        ROOT.parent / "client" / "public" / "img" / "profile" / "jayson-profile.jpeg",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


SOURCE_PHOTO = _find_photo()

GRID_W, GRID_H = 300, 340

# Tone controls. These are the knobs worth turning during iteration.
CONTRAST = 1.3            # the doc is emphatic: 1.3x only, 2.4x reads skull-like
AUTOCONTRAST_CUTOFF = 1
UNSHARP_RADIUS = 3
UNSHARP_PERCENT = 140

# Dark mode draws the LIT subject. Pure inversion leaves the navy suit empty and
# the face floats disembodied, so lift the floor a little to keep the shoulders.
DARK_FLOOR = 26           # 0 = pure inversion, higher = more ink in dark clothing
DARK_GAMMA = 1.5          # crushes midtones; without it the face fills in solid

# Light mode keeps the backdrop, but this photo's studio grey sits near 45% ink,
# which would render as a near-solid block. Lift it so it reads as texture.
LIGHT_GAMMA = 2.4
BG_KEEP = 0.26

SEG_THRESHOLD = 58        # RGB distance from the modelled backdrop surface
SEG_CLOSE_ITERS = 2

N_TRAVELLERS = 900
N_DRIFT_BANDS = 94
N_INTRO_GROUPS = 60
DRIFT_FRACTION = 0.42
DRIFT_NOISE_SIGMA = 2.0   # per-dot fuzz at the boundary only
DRIFT_WARP_AMP = 22.0     # breaks the quantize-a-linear-function-into-a-grid trap

SEED = 20260801

# Portrait placement inside the banner, in SVG user units.
PITCH = 1.26
PORTRAIT_X0 = 47.0
PORTRAIT_Y0 = 88.0
PORTRAIT_W = GRID_W * PITCH      # 378.0
PORTRAIT_H = GRID_H * PITCH      # 428.4

rng = np.random.default_rng(SEED)


# --------------------------------------------------------------------------
# image -> tone
# --------------------------------------------------------------------------

def load_and_crop(path: Path) -> Image.Image:
    """Head-and-shoulders crop at the working aspect ratio.

    A tight face crop reads aggressive; keep the shoulders in frame.
    """
    im = Image.open(path).convert("RGB")
    w, h = im.size
    target_aspect = GRID_W / GRID_H

    # Face sits slightly left of centre in this frame; bias the crop to match.
    cx = w * 0.485

    crop_h = h
    crop_w = crop_h * target_aspect
    if crop_w > w:
        crop_w = w
        crop_h = crop_w / target_aspect

    left = cx - crop_w / 2
    left = max(0.0, min(left, w - crop_w))
    top = 0.0

    return im.crop(
        (int(round(left)), int(round(top)),
         int(round(left + crop_w)), int(round(top + crop_h)))
    )


def to_working_gray(rgb: Image.Image) -> np.ndarray:
    """Downsample then apply the tone chain. Returns float array 0..255."""
    small = rgb.resize((GRID_W, GRID_H), Image.LANCZOS)
    gray = small.convert("L")
    gray = ImageOps.autocontrast(gray, cutoff=AUTOCONTRAST_CUTOFF)
    gray = ImageEnhance.Contrast(gray).enhance(CONTRAST)
    gray = gray.filter(
        ImageFilter.UnsharpMask(radius=UNSHARP_RADIUS, percent=UNSHARP_PERCENT, threshold=0)
    )
    return np.asarray(gray, dtype=np.float64)


# --------------------------------------------------------------------------
# background segmentation
# --------------------------------------------------------------------------

def _backdrop_model(small: np.ndarray) -> np.ndarray:
    """Fit a smooth quadratic surface to the studio backdrop, per channel.

    A single sampled colour is not enough: this backdrop is mottled and
    vignetted, so a flat threshold reads the falloff as subject. Seeding only
    from the top strip and the upper side columns keeps the fit clean, because
    the shoulders reach both side edges lower down.
    """
    h, w, _ = small.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    xn = xx / w
    yn = yy / h

    seed = np.zeros((h, w), dtype=bool)
    seed[0:int(h * 0.10), :] = True
    seed[0:int(h * 0.52), 0:int(w * 0.06)] = True
    seed[0:int(h * 0.52), w - int(w * 0.06):] = True

    basis = np.stack(
        [np.ones_like(xn), xn, yn, xn * xn, yn * yn, xn * yn], axis=-1
    )

    model = np.zeros_like(small)
    for c in range(3):
        keep = seed.copy()
        for _ in range(3):  # robust refit: drop outliers, fit again
            A = basis[keep]
            b = small[..., c][keep]
            coef, *_ = np.linalg.lstsq(A, b, rcond=None)
            fit = basis @ coef
            resid = np.abs(small[..., c] - fit)
            keep = seed & (resid < max(2.0 * resid[seed].std(), 4.0))
        model[..., c] = basis @ coef

    return model


def segment_foreground(rgb: Image.Image) -> np.ndarray:
    """Binary subject mask on the working grid.

    Threshold on colour distance from the modelled backdrop, open away speckle,
    close, fill holes, keep the largest connected component.
    """
    small = np.asarray(rgb.resize((GRID_W, GRID_H), Image.LANCZOS), dtype=np.float64)
    model = _backdrop_model(small)

    dist = np.sqrt(((small - model) ** 2).sum(axis=2))
    mask = dist > SEG_THRESHOLD

    # Open first: kill isolated backdrop speckle before it can be bridged into
    # the subject by the closing pass.
    mask = ndimage.binary_opening(mask, structure=np.ones((3, 3)), iterations=2)
    mask = ndimage.binary_closing(mask, structure=np.ones((3, 3)), iterations=SEG_CLOSE_ITERS)

    # The subject touches the bottom edge, so fill_holes alone leaves the torso
    # open. Pad a solid row underneath, fill, then drop the pad.
    padded = np.vstack([mask, np.ones((1, GRID_W), dtype=bool)])
    padded = ndimage.binary_fill_holes(padded)
    mask = padded[:-1]

    labels, n = ndimage.label(mask)
    if n > 1:
        sizes = ndimage.sum(mask, labels, range(1, n + 1))
        mask = labels == (int(np.argmax(sizes)) + 1)

    mask = ndimage.binary_closing(mask, structure=np.ones((5, 5)), iterations=1)
    return mask


# --------------------------------------------------------------------------
# dithering
# --------------------------------------------------------------------------

def floyd_steinberg(src: np.ndarray) -> np.ndarray:
    """1-bit Floyd-Steinberg with serpentine scan order.

    Input is 'ink demand' 0..255 where 255 means solid ink. Returns bool.
    """
    buf = src.astype(np.float64).copy()
    h, w = buf.shape
    out = np.zeros((h, w), dtype=bool)

    for y in range(h):
        left_to_right = (y % 2) == 0
        xs = range(w) if left_to_right else range(w - 1, -1, -1)
        step = 1 if left_to_right else -1

        for x in xs:
            old = buf[y, x]
            new = 255.0 if old >= 128.0 else 0.0
            out[y, x] = new > 0
            err = old - new

            nx = x + step
            if 0 <= nx < w:
                buf[y, nx] += err * 7.0 / 16.0
            if y + 1 < h:
                px = x - step
                if 0 <= px < w:
                    buf[y + 1, px] += err * 3.0 / 16.0
                buf[y + 1, x] += err * 5.0 / 16.0
                if 0 <= nx < w:
                    buf[y + 1, nx] += err * 1.0 / 16.0

    return out


def build_dark_dots(gray: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Dots draw the lit subject; background segmented away.

    The gamma is what stops this reading as a photo negative. Straight
    inversion puts ~50% ink everywhere the face is lit, so the face fills in
    solid and only the eye sockets survive as holes. Crushing the midtones
    leaves visible density falloff instead -- a stipple, not a slab.
    """
    lit = np.clip(gray / 255.0, 0.0, 1.0) ** DARK_GAMMA
    demand = lit * (255.0 - DARK_FLOOR) + DARK_FLOOR
    dots = floyd_steinberg(np.clip(demand, 0.0, 255.0))

    # Hard-clear error-diffusion bleed at the mask edge: erode by one cell so the
    # fringe of stray dots that FS pushes across the boundary is removed.
    inner = ndimage.binary_erosion(mask, structure=np.ones((3, 3)), iterations=1)
    return dots & inner


def build_light_dots(gray: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Dots draw the dark parts of the photo; background kept as texture."""
    ink = np.clip((255.0 - gray) / 255.0, 0.0, 1.0) ** LIGHT_GAMMA
    demand = np.where(mask, ink, ink * BG_KEEP) * 255.0
    return floyd_steinberg(np.clip(demand, 0.0, 255.0))


# --------------------------------------------------------------------------
# logo point clouds
# --------------------------------------------------------------------------

SS = 3  # supersample factor for logo rasterisation


def _logo_canvas() -> tuple[Image.Image, ImageDraw.ImageDraw, float, float]:
    im = Image.new("L", (int(PORTRAIT_W * SS), int(PORTRAIT_H * SS)), 0)
    d = ImageDraw.Draw(im)
    return im, d, PORTRAIT_W * SS / 2.0, PORTRAIT_H * SS / 2.0


def logo_nextjs() -> np.ndarray:
    """Circle mark with the N: left stem, diagonal, and a right stem that stops
    short at the bottom -- the detail that makes it read as Next.js."""
    im, d, cx, cy = _logo_canvas()
    R = 132 * SS
    sw = 12 * SS
    d.ellipse([cx - R, cy - R, cx + R, cy + R], outline=255, width=int(sw))

    bw = 15 * SS          # stroke weight of the N
    half_h = 58 * SS
    x_left = cx - 44 * SS
    x_right = cx + 44 * SS

    d.line([(x_left, cy - half_h), (x_left, cy + half_h)], fill=255, width=int(bw))
    d.line([(x_left, cy - half_h), (x_right, cy + half_h)], fill=255, width=int(bw))
    # right stem: top ~62% only
    d.line([(x_right, cy - half_h), (x_right, cy - half_h + 0.62 * 2 * half_h)],
           fill=255, width=int(bw))
    return np.asarray(im) > 96


def logo_code_glyph() -> np.ndarray:
    """</> -- two chevrons and a slash."""
    im, d, cx, cy = _logo_canvas()
    sw = int(17 * SS)
    ax = 58 * SS
    bx = 116 * SS
    ay = 56 * SS

    d.line([(cx - ax, cy - ay), (cx - bx, cy), (cx - ax, cy + ay)],
           fill=255, width=sw, joint="curve")
    d.line([(cx + ax, cy - ay), (cx + bx, cy), (cx + ax, cy + ay)],
           fill=255, width=sw, joint="curve")
    d.line([(cx + 26 * SS, cy - 70 * SS), (cx - 26 * SS, cy + 70 * SS)],
           fill=255, width=sw)
    return np.asarray(im) > 96


def logo_vercel() -> np.ndarray:
    """Solid triangle, apex up."""
    im, d, cx, cy = _logo_canvas()
    d.polygon(
        [(cx, cy - 100 * SS), (cx - 116 * SS, cy + 76 * SS), (cx + 116 * SS, cy + 76 * SS)],
        fill=255,
    )
    return np.asarray(im) > 96


def _assign(pts: np.ndarray, centres: np.ndarray, chunk: int = 4000) -> np.ndarray:
    """Nearest-centre assignment, chunked so the distance matrix stays bounded."""
    out = np.empty(len(pts), dtype=np.int32)
    c2 = (centres ** 2).sum(axis=1)
    for s in range(0, len(pts), chunk):
        p = pts[s:s + chunk]
        d2 = (p ** 2).sum(axis=1)[:, None] - 2.0 * (p @ centres.T) + c2[None, :]
        out[s:s + chunk] = np.argmin(d2, axis=1)
    return out


def _lloyd(pts: np.ndarray, k: int, iters: int) -> tuple[np.ndarray, np.ndarray]:
    """Lloyd relaxation. Returns (centres, assignment)."""
    centres = pts[rng.choice(len(pts), size=k, replace=False)].copy()
    assign = np.zeros(len(pts), dtype=np.int32)

    for _ in range(iters):
        assign = _assign(pts, centres)
        counts = np.bincount(assign, minlength=k).astype(np.float64)
        sx = np.bincount(assign, weights=pts[:, 0], minlength=k)
        sy = np.bincount(assign, weights=pts[:, 1], minlength=k)
        live = counts > 0
        centres[live, 0] = sx[live] / counts[live]
        centres[live, 1] = sy[live] / counts[live]
        # Re-seed any centre that lost all its members.
        dead = np.nonzero(~live)[0]
        if len(dead):
            centres[dead] = pts[rng.integers(0, len(pts), size=len(dead))]

    return centres, assign


MAX_LLOYD_POINTS = 45000


def even_sample(mask: np.ndarray, n: int, iters: int = 12) -> np.ndarray:
    """n evenly spread points over an ink mask, in mask-pixel coordinates.

    Uniform random sampling clumps; Lloyd relaxation gives the even coverage
    that makes a 900-dot swarm read as a shape rather than a cloud. Subsampling
    the ink first costs nothing in centroid accuracy and a great deal in time.
    """
    ys, xs = np.nonzero(mask)
    pts = np.stack([xs, ys], axis=1).astype(np.float64)
    if len(pts) > MAX_LLOYD_POINTS:
        pts = pts[rng.choice(len(pts), size=MAX_LLOYD_POINTS, replace=False)]

    centres, _ = _lloyd(pts, n, iters)
    return centres


def chain_match(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Reorder b so b[i] is the optimal-transport partner of a[i]."""
    cost = ((a[:, None, :] - b[None, :, :]) ** 2).sum(axis=2)
    _, col = linear_sum_assignment(cost)
    return b[col]


# --------------------------------------------------------------------------
# grouping + metrics
# --------------------------------------------------------------------------

def kmeans(points: np.ndarray, k: int, iters: int = 18) -> np.ndarray:
    _, assign = _lloyd(points, k, iters)
    return assign


def _warp_field(amp: float, smooth: float = 7.0) -> np.ndarray:
    """Smooth 2-channel random displacement field over the working grid.

    Per-dot white noise is the wrong tool here: it makes individual dots hop
    bands without moving the boundary, so the grid survives and the run
    encoding shatters. A spatially smooth field bends the whole boundary and
    keeps neighbouring dots together.
    """
    field = rng.normal(0.0, 1.0, size=(GRID_H, GRID_W, 2))
    for c in range(2):
        field[..., c] = ndimage.gaussian_filter(field[..., c], sigma=smooth, mode="reflect")
        field[..., c] /= field[..., c].std()
    return field * amp


def build_drift_bands(dots: np.ndarray, target: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Assign every ink cell to a drift band.

    The trap: drift is a linear function of position, so quantizing it directly
    recreates a square grid and the dissolve looks blocky. The smooth warp is
    what keeps the band boundaries organic; the small white-noise term only
    softens the boundary at the per-dot scale.
    """
    ys, xs = np.nonzero(dots)
    px = PORTRAIT_X0 + (xs + 0.5) * PITCH
    py = PORTRAIT_Y0 + (ys + 0.5) * PITCH
    pos = np.stack([px, py], axis=1)

    drift = (target[None, :] - pos) * DRIFT_FRACTION

    warp = _warp_field(DRIFT_WARP_AMP)[ys, xs]
    key = drift + warp + rng.normal(0.0, DRIFT_NOISE_SIGMA, size=drift.shape)

    band = kmeans(key, N_DRIFT_BANDS)

    offsets = np.zeros((N_DRIFT_BANDS, 2), dtype=np.float64)
    for j in range(N_DRIFT_BANDS):
        sel = drift[band == j]
        if len(sel):
            offsets[j] = sel.mean(axis=0)

    return band, offsets


def straight_boundary_metric(dots: np.ndarray, band: np.ndarray, min_run: int = 6) -> float:
    """Fraction of band boundaries that sit on long straight vertical lines.

    ~0.01 organic, ~0.17 means a grid was accidentally built.
    """
    ys, xs = np.nonzero(dots)
    lab = -np.ones(dots.shape, dtype=np.int32)
    lab[ys, xs] = band

    left = lab[:, :-1]
    right = lab[:, 1:]
    boundary = (left >= 0) & (right >= 0) & (left != right)

    total = int(boundary.sum())
    if total == 0:
        return 0.0

    long_runs = 0
    for x in range(boundary.shape[1]):
        col = boundary[:, x]
        run = 0
        for v in col:
            if v:
                run += 1
            else:
                if run >= min_run:
                    long_runs += run
                run = 0
        if run >= min_run:
            long_runs += run

    return long_runs / total


def intro_evenness_metric(coords: np.ndarray, group: np.ndarray, n_groups: int) -> float:
    """Mean group-centroid displacement, normalised by the portrait's RMS radius.

    Random interleaving lands near 1/sqrt(dots per group) -- about 0.05 here.
    Grouping by spatial region pushes every centroid out toward its own patch
    and the metric climbs toward 0.7+.
    """
    centre = coords.mean(axis=0)
    radius = np.sqrt(((coords - centre) ** 2).sum(axis=1).mean())

    disp = []
    for g in range(n_groups):
        sel = coords[group == g]
        if len(sel):
            disp.append(np.linalg.norm(sel.mean(axis=0) - centre))

    return float(np.mean(disp) / radius)


# --------------------------------------------------------------------------
# run-length encoding
# --------------------------------------------------------------------------

def runs_for(dots: np.ndarray, group: np.ndarray | None = None) -> list[tuple[int, int, int, int]]:
    """Horizontal runs as (row, col_start, length, group).

    Runs stay contiguous only where neighbouring cells share a group, which is
    what keeps the emitted path data compact.
    """
    ys, xs = np.nonzero(dots)
    gmap = -np.ones(dots.shape, dtype=np.int32)
    gmap[ys, xs] = group if group is not None else 0

    out = []
    h, w = dots.shape
    for y in range(h):
        x = 0
        row = dots[y]
        grow = gmap[y]
        while x < w:
            if not row[x]:
                x += 1
                continue
            g = grow[x]
            start = x
            while x < w and row[x] and grow[x] == g:
                x += 1
            out.append((y, start, x - start, int(g)))
    return out


# --------------------------------------------------------------------------
# previews
# --------------------------------------------------------------------------

def save_preview(name: str, arr: np.ndarray, on=(255, 255, 255), off=(13, 17, 23), scale=2):
    img = np.zeros((*arr.shape, 3), dtype=np.uint8)
    img[...] = off
    img[arr] = on
    im = Image.fromarray(img).resize(
        (arr.shape[1] * scale, arr.shape[0] * scale), Image.NEAREST
    )
    im.save(PREVIEW / name)


def save_logo_preview(name: str, clouds: dict[str, np.ndarray]):
    im = Image.new("RGB", (int(PORTRAIT_W) * 3 + 40, int(PORTRAIT_H)), (13, 17, 23))
    d = ImageDraw.Draw(im)
    for i, (label, pts) in enumerate(clouds.items()):
        ox = i * (int(PORTRAIT_W) + 20)
        for x, y in pts:
            d.ellipse([ox + x - 2.1, y - 2.1, ox + x + 2.1, y + 2.1], fill=(167, 139, 250))
        d.text((ox + 8, 8), label, fill=(57, 211, 83))
    im.save(PREVIEW / name)


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true", help="previews + metrics only")
    args = ap.parse_args()

    DATA.mkdir(exist_ok=True)
    PREVIEW.mkdir(exist_ok=True)

    if not SOURCE_PHOTO.exists():
        sys.exit(f"source photo not found: {SOURCE_PHOTO}")

    rgb = load_and_crop(SOURCE_PHOTO)
    rgb.resize((GRID_W * 2, GRID_H * 2), Image.LANCZOS).save(PREVIEW / "00-crop.png")

    gray = to_working_gray(rgb)
    Image.fromarray(gray.astype(np.uint8)).resize(
        (GRID_W * 2, GRID_H * 2), Image.NEAREST
    ).save(PREVIEW / "01-tone.png")

    mask = segment_foreground(rgb)
    save_preview("02-mask.png", mask, on=(57, 211, 83))

    dark = build_dark_dots(gray, mask)
    light = build_light_dots(gray, mask)

    save_preview("03-dark.png", dark, on=(167, 139, 250), off=(13, 17, 23))
    save_preview("04-light.png", light, on=(124, 58, 237), off=(255, 255, 255))

    # --- logos -----------------------------------------------------------
    masks = {
        "next": logo_nextjs(),
        "code": logo_code_glyph(),
        "vercel": logo_vercel(),
    }
    # Logo masks are rasterised at SS x portrait size; bring every cloud into
    # the one shared SVG coordinate frame before matching, or the transport
    # cost is computed across mismatched frames and the paths are nonsense.
    shift = np.array([PORTRAIT_X0, PORTRAIT_Y0])
    clouds_raw = {k: even_sample(v, N_TRAVELLERS) / SS for k, v in masks.items()}
    save_logo_preview("05-logos.png", clouds_raw)
    clouds = {k: v + shift for k, v in clouds_raw.items()}

    # Travellers start from the portrait, so seed the chain there.
    portrait_pts = even_sample(dark, N_TRAVELLERS, iters=12) * PITCH + shift

    l1 = chain_match(portrait_pts, clouds["next"])
    l2 = chain_match(l1, clouds["code"])
    l3 = chain_match(l2, clouds["vercel"])

    target = l1.mean(axis=0)

    # --- portrait grouping ------------------------------------------------
    results = {}
    for name, dots in (("dark", dark), ("light", light)):
        band, offsets = build_drift_bands(dots, target)
        sb = straight_boundary_metric(dots, band)

        rle = runs_for(dots, band)
        # Intro groups are assigned per RUN, which keeps path data compact while
        # staying spatially uniform. Verified with the evenness metric below.
        intro = rng.integers(0, N_INTRO_GROUPS, size=len(rle))

        run_centres = np.array(
            [[PORTRAIT_X0 + (c + l / 2) * PITCH, PORTRAIT_Y0 + (r + 0.5) * PITCH]
             for r, c, l, _ in rle]
        )
        ev = intro_evenness_metric(run_centres, intro, N_INTRO_GROUPS)

        results[name] = dict(
            dots=dots, band=band, offsets=offsets, rle=rle, intro=intro,
            straight=sb, evenness=ev,
        )

    metrics = {
        "grid": [GRID_W, GRID_H],
        "dark_ink_cells": int(dark.sum()),
        "light_ink_cells": int(light.sum()),
        "dark_ink_coverage": round(float(dark.mean()), 4),
        "light_ink_coverage": round(float(light.mean()), 4),
        "mask_coverage": round(float(mask.mean()), 4),
        "dark_runs": len(results["dark"]["rle"]),
        "light_runs": len(results["light"]["rle"]),
        "drift_bands": N_DRIFT_BANDS,
        "intro_groups": N_INTRO_GROUPS,
        "straight_boundary_dark": round(results["dark"]["straight"], 4),
        "straight_boundary_light": round(results["light"]["straight"], 4),
        "intro_evenness_dark": round(results["dark"]["evenness"], 4),
        "intro_evenness_light": round(results["light"]["evenness"], 4),
    }
    print(json.dumps(metrics, indent=2))

    if args.preview:
        return

    np.save(DATA / "dark_dots.npy", dark)
    np.save(DATA / "light_dots.npy", light)
    np.save(DATA / "mask.npy", mask)
    np.save(DATA / "logo_next.npy", l1)
    np.save(DATA / "logo_code.npy", l2)
    np.save(DATA / "logo_vercel.npy", l3)
    np.save(DATA / "traveller_portrait.npy", portrait_pts)
    for name in ("dark", "light"):
        np.save(DATA / f"{name}_band.npy", results[name]["band"])
        np.save(DATA / f"{name}_offsets.npy", results[name]["offsets"])
        np.save(DATA / f"{name}_rle.npy", np.array(results[name]["rle"], dtype=np.int32))
        np.save(DATA / f"{name}_intro.npy", results[name]["intro"])
    (DATA / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(f"\nwrote {len(list(DATA.glob('*.npy')))} arrays to {DATA}")


if __name__ == "__main__":
    main()
