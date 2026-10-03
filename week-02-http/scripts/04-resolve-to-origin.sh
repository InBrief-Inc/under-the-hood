#!/usr/bin/env bash
# Ask one specific server for a site, skipping DNS. --resolve pins the name to
# the address you give it and still sends the right Host header and TLS name,
# so you can test a new server before the DNS record points at it.
set -euo pipefail
host="${1:?usage: $0 <hostname> <ipv4-address>}"
ip="${2:?usage: $0 <hostname> <ipv4-address>}"

curl -sSI --resolve "$host:443:$ip" \
  -w '\nasked %{remote_ip} for %{url_effective}\n' \
  "https://$host/" | tr -d '\r' | grep -iE '^(HTTP/|server:|via:|age:|asked)'
