#!/usr/bin/env bash
# Who actually controls a domain: the registrar's record, and the
# nameservers that answer for it. Run before touching any DNS.
set -euo pipefail
domain="${1:-example.com}"

echo "== whois: registrar and expiry =="
whois "$domain" | grep -iE 'registrar:|expir|creation date' || true

echo
echo "== nameservers answering for $domain =="
dig NS "$domain" +short
