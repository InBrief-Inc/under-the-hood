#!/usr/bin/env bash
# The request curl sent and the response it got, as they crossed the wire.
# HTTP/1.1 is forced because it is plain text; lines starting ">" went out,
# lines starting "<" came back.
set -euo pipefail
url="${1:-https://example.com}"

curl -sS --http1.1 -o /dev/null -v "$url" 2>&1 | tr -d '\r' | grep -E '^[<>]'
