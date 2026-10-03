#!/usr/bin/env bash
# Every hop of a redirect chain: each status line and, where there is one, its
# Location. A loop or a wrong 301 shows up here long before it shows up in a
# browser, and browsers keep permanent redirects.
set -euo pipefail
url="${1:-http://github.com}"

curl -sSL --max-redirs 10 -o /dev/null -D - \
  -w 'RESULT %{num_redirects} redirect(s), ended at %{url_effective} with HTTP %{http_code}\n' \
  "$url" | tr -d '\r' | grep -iE '^(HTTP/|location:|RESULT)'
