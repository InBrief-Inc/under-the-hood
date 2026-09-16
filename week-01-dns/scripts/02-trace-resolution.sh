#!/usr/bin/env bash
# Skip your resolver's cache and walk the chain from the root, the way a
# cold lookup actually happens. A broken chain shows exactly which hop
# stopped answering.
set -euo pipefail
domain="${1:-example.com}"

dig +trace "$domain"
