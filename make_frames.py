"""
Build frames.html -- a paused, seekable copy of dark.svg for verifying the
animation timeline frame by frame.

Eyeballing a 14.2s loop is not verification, and cairosvg only renders the
first SMIL frame. Inlining the SVG (rather than fetching it) sidesteps
file:// CORS entirely, and pauseAnimations() + setCurrentTime() lets each
phase boundary be checked exactly.

Run:  python make_frames.py    then open frames.html
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent
svg = (ROOT / "dark.svg").read_text(encoding="utf-8")
svg = svg.replace("<svg ", '<svg id="stage" ', 1)

LOOP_BEGIN = 3.15
PHASES = {
    "intro ~40%": 0.9,
    "intro done / portrait": 2.6,
    "portrait at rest": LOOP_BEGIN + 1.5,
    "mid dissolve": LOOP_BEGIN + 3.7,
    "logo 1 Next.js": LOOP_BEGIN + 5.3,
    "logo 2 code glyph": LOOP_BEGIN + 8.6,
    "logo 3 Vercel": LOOP_BEGIN + 11.9,
    "returning to portrait": LOOP_BEGIN + 13.6,
}

buttons = "".join(
    f'<button onclick="seek({t},this)">{label}<br><small>t={t:.2f}s</small></button>'
    for label, t in PHASES.items()
)

html = f"""<!doctype html>
<meta charset="utf-8">
<title>frame sampler</title>
<style>
  body {{ margin:0; background:#0d1117; color:#8b949e;
         font:12px ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; }}
  #bar {{ padding:10px 12px; display:flex; gap:6px; flex-wrap:wrap;
          border-bottom:1px solid #232b39; }}
  button {{ background:#161b22; color:#8b949e; border:1px solid #30363d;
            border-radius:6px; padding:6px 9px; cursor:pointer; font:inherit;
            line-height:1.35; }}
  button.on {{ border-color:#39d353; color:#39d353; }}
  small {{ opacity:.6; }}
  #wrap {{ padding:16px; }}
  svg {{ width:900px; max-width:100%; display:block; }}
</style>
<div id="bar">{buttons}<span id="now" style="align-self:center;margin-left:8px"></span></div>
<div id="wrap">{svg}</div>
<script>
  const s = document.getElementById('stage');
  s.pauseAnimations();
  function seek(t, btn) {{
    s.setCurrentTime(t);
    document.querySelectorAll('#bar button').forEach(b => b.classList.remove('on'));
    if (btn) btn.classList.add('on');
    document.getElementById('now').textContent = 't = ' + t.toFixed(2) + 's';
  }}
  seek({LOOP_BEGIN + 1.5});
</script>
"""

out = ROOT / "frames.html"
out.write_text(html, encoding="utf-8")
print(f"wrote {out} ({len(html) / 1024:.0f} KB)")
