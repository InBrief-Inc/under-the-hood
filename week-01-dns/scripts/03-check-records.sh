#!/usr/bin/env bash
# A, AAAA and the CNAME chain in one pass. A stray or missing AAAA
# passes every IPv4 check, so check it on its own, not as an afterthought.
set -euo pipefail
domain="${1:-example.com}"

echo "== A (IPv4) =="
dig "$domain" A +short

echo
echo "== AAAA (IPv6) =="
dig "$domain" AAAA +short || echo "(none)"

echo
echo "== full chain, including any CNAME hops =="
dig "$domain" +short
