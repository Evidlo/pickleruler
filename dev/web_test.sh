#!/bin/sh
# Headless Chromium test of index.html: injects web_harness.html, prints results.
# Optional: web_test.sh shot.png  also saves a screenshot.
set -e
here=$(cd "$(dirname "$0")" && pwd)
root=$(dirname "$here")
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
sed "/<\/body>/e cat $here/web_harness.html" "$root/index.html" > "$tmp/test.html"
run() { chromium --password-store=basic --headless --disable-gpu --no-sandbox --window-size=1600,1000 --virtual-time-budget=3000 "$@" "file://$tmp/test.html" 2>/dev/null; }
run --dump-dom | python3 -c "
import sys, re, html
m = re.search(r'<pre id=\"results\"[^>]*>(.*?)</pre>', sys.stdin.read(), re.S)
text = html.unescape(m.group(1)) if m else 'FAIL no results'
print(text)
sys.exit(1 if 'FAIL' in text or 'EXC' in text else 0)"
[ -n "$1" ] && run --screenshot="$(realpath "$1")" || true
