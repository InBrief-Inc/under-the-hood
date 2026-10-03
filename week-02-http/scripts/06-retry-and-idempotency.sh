#!/usr/bin/env bash
# Why a retry needs a rule. A stub "payments" server on localhost does the work
# for every POST /charge, then answers 504 twice, the way a proxy gives up
# after the app has already finished. curl --retry sends the same POST again
# each time. With no Idempotency-Key the work runs three times; with one the
# stub recognises the repeat and it runs once. Needs python3 and curl only.
set -euo pipefail
port="${PORT:-8765}"

STUB='
import http.server, sys

charges, attempts, done = 0, 0, set()

class Stub(http.server.BaseHTTPRequestHandler):
    def reply(self, code, text=""):
        body = text.encode()
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):                    # GET /charges: how often the work really ran
        self.reply(200, str(charges))

    def do_POST(self):
        global charges, attempts
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        attempts += 1
        key = self.headers.get("Idempotency-Key")
        if key in done:                  # a repeat of a request already finished
            return self.reply(200, "already done")
        charges += 1                     # the work happens here
        if key:
            done.add(key)
        self.reply(504 if attempts <= 2 else 200)   # the proxy gives up twice

    def log_message(self, *args):
        pass

http.server.HTTPServer(("127.0.0.1", int(sys.argv[1])), Stub).serve_forever()
'

run_case() {  # run_case <title> [extra curl args...]
  local title="$1"; shift
  python3 -c "$STUB" "$port" &
  local pid=$!
  trap 'kill "$pid" 2>/dev/null || true' RETURN
  until curl -s -o /dev/null "http://127.0.0.1:$port/charges"; do sleep 0.1; done

  echo "== $title =="
  curl --no-progress-meter --retry 3 --retry-delay 1 -X POST -d 'amount=10' "$@" \
    -o /dev/null -w 'final answer: HTTP %{http_code}\n' "http://127.0.0.1:$port/charge"
  echo "the work ran $(curl -s "http://127.0.0.1:$port/charges") time(s)"
  echo
}

run_case "no Idempotency-Key: every retry repeats the charge"
run_case "same retries, with Idempotency-Key: demo-1" -H 'Idempotency-Key: demo-1'
