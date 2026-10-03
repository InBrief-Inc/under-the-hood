#!/usr/bin/env bash
# Where one request's time goes. curl reports every timestamp counted from the
# start of the request, so this subtracts neighbours to get the length of each
# stage. One request, no redirects, a fresh connection on every run. Anything
# after the URL goes to curl, so `01-timing-breakdown.sh https://example.com
# --tlsv1.2 --tls-max 1.2` shows what an older TLS version costs.
set -euo pipefail
url="${1:-https://example.com}"
shift $(( $# > 0 ? 1 : 0 ))

curl -sS -o /dev/null "$@" \
  -w '%{time_namelookup} %{time_connect} %{time_appconnect} %{time_starttransfer} %{time_total}\n' \
  "$url" |
awk '{
  ready = ($3 > 0) ? $3 : $2   # the last handshake to finish: TLS if there was one
  printf "dns       %5.0f ms   name to address\n", $1 * 1000
  printf "tcp       %5.0f ms   connect to the server\n", ($2 - $1) * 1000
  printf "tls       %5.0f ms   encryption handshake\n", ($3 > 0 ? $3 - $2 : 0) * 1000
  printf "wait      %5.0f ms   request sent, until the first byte comes back\n", ($4 - ready) * 1000
  printf "download  %5.0f ms   the rest of the body\n", ($5 - $4) * 1000
  printf "total     %5.0f ms\n", $5 * 1000
}'
