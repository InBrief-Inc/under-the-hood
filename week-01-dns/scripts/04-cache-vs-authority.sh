#!/usr/bin/env bash
# A public resolver's cache versus the domain's own authoritative
# answer, side by side. The "aa" flag says which one you're reading;
# the two TTLs say how far apart they are, in seconds left on the lease.
set -euo pipefail
domain="${1:-example.com}"

authority=$(dig NS "$domain" +short | head -1 | sed 's/\.$//')
if [ -z "$authority" ]; then
  echo "Could not find an authoritative nameserver for $domain" >&2
  exit 1
fi

echo "== public resolver (1.1.1.1), cached answer =="
dig "$domain" @1.1.1.1 +noall +answer

echo
echo "== authoritative server ($authority), the real value =="
dig "$domain" "@$authority" +noall +answer
