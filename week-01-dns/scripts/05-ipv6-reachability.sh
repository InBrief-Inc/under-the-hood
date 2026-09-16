#!/usr/bin/env bash
# A resolver answer and a working connection are two different facts.
# This checks both address families actually accept a connection,
# not just that a record exists for them.
set -euo pipefail
domain="${1:-example.com}"

echo "== IPv4 =="
curl -4 -sS -o /dev/null -w 'remote_ip=%{remote_ip} http_code=%{http_code} time=%{time_total}s\n' "https://$domain" || echo "IPv4 connection failed"

echo
echo "== IPv6 =="
curl -6 -sS -o /dev/null -w 'remote_ip=%{remote_ip} http_code=%{http_code} time=%{time_total}s\n' "https://$domain" || echo "IPv6 connection failed (no AAAA, or nothing listening on it)"
