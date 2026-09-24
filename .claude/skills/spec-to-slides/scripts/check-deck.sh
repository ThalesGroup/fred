#!/usr/bin/env bash
# Render a deck headless at 1280x720 and report slides whose content is clipped or autofit-scaled below 0.85, plus contact sheets.
# Works on any deck whose slides are <section class="slide"> — the check script is injected here.
# usage: check-deck.sh <deck.html> [outdir]
set -euo pipefail
deck=$(realpath "$1"); out=${2:-$(dirname "$deck")/check}; mkdir -p "$out"
chrome=$(command -v google-chrome || command -v chromium || command -v chromium-browser || true)
[ -n "$chrome" ] || { echo "no chrome/chromium found — open $deck and look for clipped content by hand"; exit 2; }
n=$(grep -o '<section class="slide' "$deck" | wc -l)
check='<script>window.addEventListener("load",()=>{setTimeout(()=>{document.querySelectorAll("section.slide").forEach((s,i)=>{const c=el=>el.scrollHeight>el.clientHeight+6||el.scrollWidth>el.clientWidth+6;if(s.dataset.fit){if(+s.dataset.fit<0.85)s.dataset.clip=(i+1)+" scaled to "+s.dataset.fit+" — too much content, split it";return;}const bad=c(s)?s:[...s.children,...s.querySelectorAll(":scope > * > *")].find(c);if(bad){s.dataset.clip=(i+1)+" "+(bad.className||bad.tagName)+" "+bad.scrollWidth+"x"+bad.scrollHeight+" in "+bad.clientWidth+"x"+bad.clientHeight;}});},2500);});</script>'
tmp="$out/deck-check.html"
{ echo '<!doctype html><html><head><meta charset="utf-8">'; cat "$deck"; echo "$check"; echo '</head></html>'; } > "$tmp"
"$chrome" --headless=new --no-sandbox --disable-gpu --hide-scrollbars --window-size=1280,720 --virtual-time-budget=12000 \
  --dump-dom "file://$tmp" 2>/dev/null > "$out/dom.html" || true
over=$( (grep -o 'data-clip="[^"]*"' "$out/dom.html" || true) | sed 's/data-clip=//;s/"//g;s/^/  slide /')
sed 's#</style>#.slide{height:720px!important}</style>#' "$tmp" > "$out/deck-sheet.html"
"$chrome" --headless=new --no-sandbox --disable-gpu --hide-scrollbars --window-size=1280,$((n*720)) --virtual-time-budget=15000 \
  --screenshot="$out/full.png" "file://$out/deck-sheet.html" >/dev/null 2>&1 || true
if [ -s "$out/full.png" ]; then
python3 - "$out" "$n" <<'PY'
import sys
try:
    from PIL import Image
except ImportError:
    print("pillow not installed — contact sheets skipped (clip report below still valid)")
    raise SystemExit(0)
out, n = sys.argv[1], int(sys.argv[2])
im = Image.open(f"{out}/full.png")
for p in range(0, n, 8):
    sheet = Image.new("RGB", (1280, 1440), "white")
    for k, i in enumerate(range(p, min(n, p + 8))):
        sheet.paste(im.crop((0, i * 720, 1280, (i + 1) * 720)).resize((640, 360)), ((k % 2) * 640, (k // 2) * 360))
    sheet.save(f"{out}/sheet-{p // 8}.png")
print(f"contact sheets: {out}/sheet-*.png")
PY
else
  echo "chrome produced no screenshot — contact sheets skipped (clip report below still valid)"
fi
[ -n "$over" ] && echo "$over"
cnt=$( (printf "%s\n" "$over" | grep -c "slide ") || true)
echo "slides: $n · clipped: $cnt"
[ "$cnt" = "0" ]
