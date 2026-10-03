#!/usr/bin/env bash
# Which HTTP version each curl flag actually negotiated with a site, and
# whether the site advertises HTTP/3 for next time (the alt-svc header).
set -uo pipefail
url="${1:-https://example.com}"

for flag in --http1.1 --http2 --http3; do
  if v=$(curl -sS "$flag" -o /dev/null -w '%{http_version}' "$url" 2>/dev/null); then
    printf '%-9s -> HTTP/%s\n' "$flag" "$v"
  else
    printf '%-9s -> not available (this curl build lacks it, or the request failed)\n' "$flag"
  fi
done

echo
echo "== does the server advertise HTTP/3? =="
curl -sSI "$url" | tr -d '\r' | grep -i '^alt-svc' || echo "(no alt-svc header)"
