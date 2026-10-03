---
title: HTTP without the guesswork
description: One page load as six clocks, what a request and a response really contain, the status codes that mislead, the headers that matter in production, what HTTP/2 and HTTP/3 changed, why retries need rules, and five real outages that show where each piece breaks.
date: 2026-10-03
slug: http-without-the-guesswork
---

Last week's article ended with an address. The browser now holds a number like `203.0.113.7` and nothing else, and a page still needs five more things to go right before anything appears: a connection, encryption, a request that reaches the right server, an application that answers, and usually a database behind it. Each one is a separate clock that starts when the last one stops, and each fails in its own way. "The site is slow" names none of them.

This article follows one request through all six, shows what is inside an HTTP request and response, and explains why a status code is not always telling the truth. It covers the five headers behind most production surprises, what HTTP/2 and HTTP/3 changed, and the rules that make a retry safe. Five real outages show each piece breaking. The commands are runnable scripts in [`scripts/`](https://github.com/InBrief-Inc/under-the-hood/tree/main/week-02-http/scripts), not examples to read.

## Six clocks, one page

A cold page load is six stages in a row.

1. **DNS** turns the name into an address. That was last week.
2. **TCP** opens a connection to the address: a three-way handshake, one round trip.
3. **TLS** agrees on keys so nobody in between can read the traffic: usually one more round trip with TLS 1.3, two with TLS 1.2.
4. **The proxy** receives the HTTP request, usually a load balancer or a reverse proxy, and picks a server.
5. **The app** runs its code.
6. **The database** answers whatever the app asked, while the app waits.

![Six stages of one page load, each with its own way to fail: DNS, TCP, TLS, proxy, app and database](/assets/http-without-the-guesswork/six-clocks.png)

Every stage has its own clock and its own failure words, and the visitor sees the same thing for all of them. A name that does not resolve, a server that refuses the connection, a certificate that expired yesterday and a query that takes 30 seconds all end as a spinner, and each one belongs to someone different.

"Cold" is the word that matters. A visitor who has never been here pays for stages 1 to 3 before the request even leaves. A visitor reusing an open connection pays for none of them, which is why the first request of a session is the slow one and why HTTP keeps connections open. Counted in round trips, a cold HTTPS request costs four before the first byte of the page arrives, assuming the resolver already has the answer: one to the resolver, one for TCP, one for TLS 1.3 and one for the request itself. With TLS 1.2 it is five.

curl will time the first three stages for you, plus the total. Every timestamp it reports is counted from the start of the request, so the length of a stage is the difference between neighbours, and [`01-timing-breakdown.sh`](https://github.com/InBrief-Inc/under-the-hood/blob/main/week-02-http/scripts/01-timing-breakdown.sh) does the subtraction. One run from Cairo against `example.com`:

```
dns           3 ms   name to address
tcp          63 ms   connect to the server
tls         102 ms   encryption handshake
wait         80 ms   request sent, until the first byte comes back
download      0 ms   the rest of the body
total       248 ms
```

On this run the two handshakes cost 165 ms, more than twice the 80 ms between sending the request and the first byte coming back. That 80 ms is `wait`. It is stages 4 to 6 added together plus one more trip across the network, and curl cannot split them. (At the time of this run `example.com` was answered from a CDN's cache, so its `wait` measures an edge, not an origin.) Splitting the server's share takes the server's help: an application can report its own clocks in a `Server-Timing` response header, and browsers show them in their developer tools.

The TLS line is where the version shows. In twelve runs against `example.com`, the fastest TCP connect took 64 ms, which is one round trip. The fastest TLS 1.3 handshake took 72 ms and the fastest TLS 1.2 handshake took 124 ms, about one round trip and about two. The script passes anything after the URL on to curl, so `01-timing-breakdown.sh https://example.com --tlsv1.2 --tls-max 1.2` forces the older version.

The failure words are just as measurable. This is what curl 8.7 says, and the exit code it returns, when each early stage breaks:

| Stage | What curl says | Exit code |
|---|---|---|
| DNS | `Could not resolve host` | 6 |
| TCP, nothing listening | `Couldn't connect to server` | 7 |
| TCP, packets dropped | `Timeout was reached` | 28 |
| TLS, certificate expired | `SSL certificate problem: certificate has expired` | 60 |
| TLS, wrong hostname | `no alternative certificate subject name matches target host name` | 60 |

The wording comes from the macOS system curl and changes with the TLS library. The exit codes are documented and stay put.

Stages 4 to 6 speak in HTTP status codes, and those are the least trustworthy words in the stack.

## What is in a request and a response

HTTP/1.1 is plain text with a strict shape. This is the exchange from [`02-read-the-exchange.sh`](https://github.com/InBrief-Inc/under-the-hood/blob/main/week-02-http/scripts/02-read-the-exchange.sh), trimmed. Lines starting with `>` went out and lines starting with `<` came back.

```
> GET / HTTP/1.1
> Host: example.com
> User-Agent: curl/8.7.1
> Accept: */*
>
< HTTP/1.1 200 OK
< Date: Sat, 03 Oct 2026 17:27:58 GMT
< Content-Type: text/html; charset=utf-8
< Server: cloudflare
< Age: 4570
< alt-svc: h3=":443"; ma=86400
<
```

A request is a start line (method, target, version), then headers written as `Name: value`, a blank line, and sometimes a body. A response is a status line (version, status code, reason), then headers, a blank line and the body. HTTP/2 and HTTP/3 carry the same fields in a binary encoding. What a method, a status code or a header means is the same in all three versions.

The method says what the client wants: GET reads, POST submits, PUT replaces, PATCH changes part of something, DELETE removes it. Methods come back in the retry section, because each one carries a promise about what happens if the same request arrives twice.

## Status codes that lie

The first digit is the contract: 2xx worked, 3xx look elsewhere, 4xx the client seems to have erred, 5xx the server failed. Three kinds of lie live inside that contract.

**A 200 that carries an error.** Some applications answer 200 to everything and put the failure in the body, as `{"ok": false, "error": "database timeout"}`. Anything that reads only the status line, such as a load balancer's health check or a basic uptime monitor, calls that healthy, and a cache may store it like any other success. The fix has two halves: the application should send a status that matches what happened, and any check that matters should read the body too.

**A 5xx from the wrong place.** A 500 means the application broke while handling a request that reached it. 502 and 504 are different: RFC 9110 defines them as what a gateway or proxy says about the server behind it. 503 is a server saying it cannot take the request right now, and a proxy with nothing healthy to send the request to often says it on the application's behalf.

- **502 Bad Gateway:** the proxy got an invalid response from the server behind it.
- **503 Service Unavailable:** the server cannot handle the request right now, because of overload or maintenance, and may say when to come back.
- **504 Gateway Timeout:** the proxy waited for the server behind it and gave up.

![Who usually answers: 4xx means the client erred, 500 comes from the app, 502, 503 and 504 usually come from the proxy in front of it](/assets/http-without-the-guesswork/who-answered.png)

The practical consequence is where to look. For a 502 or a 504 the application often never produced an error of its own, so its logs can be empty, and the engineer who opens them first concludes that nothing happened. Start with the proxy's logs and the proxy's connection to the app.

**A 4xx that means "slow down".** 429 Too Many Requests is rate limiting. The server may add a `Retry-After` header saying how long to wait, and a client that answers a 429 with an immediate retry is making the problem it was just told about worse.

## Headers that matter in production

Five headers explain most of the surprises.

**`Host`** says which site the request is for. A DNS name resolves to an address, and one address can serve many sites, so without a name the server has nothing to choose with. HTTP/1.1 requires the header, and a conforming server answers 400 to a request that lacks it, repeats it or sends an invalid value. HTTP/2 and HTTP/3 usually carry the same information in a pseudo-header called `:authority`. A request that names a site the server does not know often lands on the server's default site, which is how a new domain ends up showing somebody else's page. [`04-resolve-to-origin.sh`](https://github.com/InBrief-Inc/under-the-hood/blob/main/week-02-http/scripts/04-resolve-to-origin.sh) uses curl's `--resolve` to pin a name to an address while keeping the right Host header and TLS name, which is how you test a new server before the DNS change in last week's migration runbook.

**`Content-Type`** says how to read the body. The classic failure is a JSON client that receives an HTML error page from a proxy and reports `Unexpected token '<', "<!DOCTYPE "... is not valid JSON` (the wording of V8, Chrome's JavaScript engine). That `<` is the first character of the page. The response said `Content-Type: text/html` all along and the client never looked. Check the header before parsing, and when a body fails to parse, log the status and its first few hundred bytes.

**`Cache-Control`** says how long a response may be reused without asking again. `max-age=300` makes it fresh for 300 seconds, `s-maxage` sets the lifetime for shared caches such as a CDN, and `private` keeps the response out of shared caches. Two directives are routinely misread: `no-store` means do not keep a copy anywhere, while `no-cache` means a copy may be kept but must be revalidated before every reuse. A response with personal data that a shared cache is allowed to store is the expensive version of this bug.

**`X-Forwarded-For`** carries the visitor's address. Behind a proxy, the connection the application sees comes from the proxy, so the real address travels in this header. It is a de facto header, with `Forwarded` (RFC 7239) as the standard form, and a typical proxy appends the address it received the request from. The client can send an `X-Forwarded-For` of its own, so the leftmost entries can be forged. Read the list from the right: with one proxy you control, the visitor is the rightmost entry, with two it is the second from the right, and so on. A rate limit or allow-list keyed on the leftmost entry can be bypassed with one curl flag: `-H 'X-Forwarded-For: 1.2.3.4'`.

**`Retry-After`** says when to come back, as a number of seconds or a date. It can accompany a 429, a 503 and some redirects. A well-behaved client treats it as a minimum wait.

## HTTP/1.1, HTTP/2 and HTTP/3: what changed on the connection

HTTP/1.1 keeps one request in flight per connection, so a slow response blocks everything queued behind it. (The spec allows pipelining, sending several requests before the first answer arrives, but browsers do not use it by default.) Browsers work around the blocking by opening several connections to the same host at once, commonly six per origin.

HTTP/2 (RFC 9113) opens one connection and interleaves many requests on it as separate streams, with the headers compressed. That removes the blocking at the HTTP level and pushes it one layer down, because every stream now shares a single TCP connection: one lost packet holds up all of them until it is retransmitted. TCP gets its own week later in this series.

HTTP/3 (RFC 9114) runs over QUIC (RFC 9000), which is built on UDP and delivers each stream independently, so a lost packet delays only the streams that had data in it. QUIC also builds TLS 1.3 into its own handshake (RFC 9001), so a new connection usually needs one round trip where TCP plus TLS needs two.

A browser learns that a site speaks HTTP/3 in one of two ways. The server can say so on an earlier response, in an `Alt-Svc` header (RFC 7838), or the site can publish it in DNS, in the `HTTPS` record type (RFC 9460) from last week's article, which can list `h3` before the first connection is made. [`05-which-http-version.sh`](https://github.com/InBrief-Inc/under-the-hood/blob/main/week-02-http/scripts/05-which-http-version.sh) shows what each curl flag negotiated and whether the server advertises HTTP/3:

```
--http1.1 -> HTTP/1.1
--http2   -> HTTP/2
--http3   -> not available (this curl build lacks it, or the request failed)

== does the server advertise HTTP/3? ==
alt-svc: h3=":443"; ma=86400
```

The macOS system curl has no HTTP/3, and the script says so instead of pretending. The `alt-svc` line shows that the server advertises it. None of this changes what a request means: a GET is still a GET and a 503 is still a 503. What changes is how many round trips a cold connection costs and how far one lost packet spreads.

## Retries, idempotency and caching

Network calls fail halfway. A client sends a request, the connection dies before the answer arrives, and now it cannot know whether the server did the work. Retrying is safe only when doing the work twice is the same as doing it once, and HTTP has a word for that property: idempotent. RFC 9110 defines PUT, DELETE and the read-only methods (GET, HEAD, OPTIONS and TRACE) as idempotent. POST is not defined that way, and neither is PATCH, which RFC 5789 calls neither safe nor idempotent, although one particular PATCH can be written to be. RFC 9110 tells a client not to retry a request like that automatically unless it knows repeating it is safe, and it forbids a proxy from doing so.

[`06-retry-and-idempotency.sh`](https://github.com/InBrief-Inc/under-the-hood/blob/main/week-02-http/scripts/06-retry-and-idempotency.sh) starts a stub payments server on localhost. For every `POST /charge` the stub does the work, then answers 504 twice, the way a proxy gives up after the application has already finished. curl's `--retry` sends the same POST again each time. It does not check the method, so asking for it is the caller deciding that repeating is safe:

```
== no Idempotency-Key: every retry repeats the charge ==
Warning: Problem : HTTP error. Will retry in 1 seconds. 3 retries left.
Warning: Problem : HTTP error. Will retry in 1 seconds. 2 retries left.
final answer: HTTP 200
the work ran 3 time(s)

== same retries, with Idempotency-Key: demo-1 ==
Warning: Problem : HTTP error. Will retry in 1 seconds. 3 retries left.
final answer: HTTP 200
the work ran 1 time(s)
```

The client got the answer it wanted both times, and the first run did the work three times, which for a payment is three charges. The fix is an idempotency key: the client generates a unique value for each intended action and sends it in a header, usually named `Idempotency-Key`, which is a convention rather than a standard. The server remembers the keys it has finished, so a repeat gets an answer without the work running again.

Five rules make a retry safe:

- Retry only what is safe to repeat: idempotent methods, or requests that carry an idempotency key.
- Retry only failures that might pass: connection resets, timeouts, 502, 503, 504, and 429 after the wait. A 400 is wrong now and will be wrong again in a second.
- Wait, then spread out. Exponential backoff with jitter sleeps a random time between zero and the smaller of a cap and a base delay that doubles each attempt. AWS's Architecture Blog calls this variant full jitter and writes it as `sleep = random_between(0, min(cap, base * 2 ** attempt))`.
- Honour `Retry-After` when the server sends it.
- Cap the attempts, and retry in one layer. Retries multiply across layers.

![One click becomes 3, 9 and then 27 queries when three layers each make three attempts](/assets/http-without-the-guesswork/retry-multiplication.png)

The last rule is the arithmetic in the picture. If the browser, the API and the service each make three attempts, one failing click becomes 27 queries at the database, aimed at the one component that was already struggling. It is an example, not a measurement. AWS's [Builders' Library](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/) works the same sum for a stack five layers deep with three attempts at each layer, gets 243 times the load on the database, and for cheap operations recommends retrying at a single point in the stack.

Caching is the mirror image: not repeating the work when the answer has not changed. A client holding a response with an `ETag` can ask "has this changed?" with `If-None-Match`, and an unchanged resource comes back as a `304 Not Modified` with no body. The surprise is that some answers are cached when nobody meant them to be. RFC 9110 calls a 301 heuristically cacheable, which means a cache may keep it even when the server said nothing about freshness. A 302 or 307 gets no such treatment, so a wrong permanent redirect can outlive its fix. Use a 302 or 307 while testing, and a 301 or 308 only once you are sure.

## Reading HTTP from a terminal

Six short scripts live in this folder, and each answers one question you would otherwise guess at:

- [`01-timing-breakdown.sh`](https://github.com/InBrief-Inc/under-the-hood/blob/main/week-02-http/scripts/01-timing-breakdown.sh) turns curl's cumulative timestamps into the length of each stage, so "slow" gets a stage.
- [`02-read-the-exchange.sh`](https://github.com/InBrief-Inc/under-the-hood/blob/main/week-02-http/scripts/02-read-the-exchange.sh) prints the request and response exactly as they crossed the wire.
- [`03-follow-redirects.sh`](https://github.com/InBrief-Inc/under-the-hood/blob/main/week-02-http/scripts/03-follow-redirects.sh) lists every hop of a redirect chain, status and `Location`, and stops a loop after ten.
- [`04-resolve-to-origin.sh`](https://github.com/InBrief-Inc/under-the-hood/blob/main/week-02-http/scripts/04-resolve-to-origin.sh) asks one specific server for a site without touching DNS.
- [`05-which-http-version.sh`](https://github.com/InBrief-Inc/under-the-hood/blob/main/week-02-http/scripts/05-which-http-version.sh) reports the version each curl flag negotiated and whether HTTP/3 is advertised.
- [`06-retry-and-idempotency.sh`](https://github.com/InBrief-Inc/under-the-hood/blob/main/week-02-http/scripts/06-retry-and-idempotency.sh) shows a retry repeating a charge, and an idempotency key stopping it.

Most take a URL and default to a public example. The fourth takes a hostname and an address, and the sixth takes nothing. All of them need only `curl` and standard shell tools, and the sixth also needs `python3` for its stub server.

## Five times this broke, in public

**AWS S3, 28 February 2017.** An engineer following a playbook ran a command to take a few servers out of one S3 subsystem, and one input was entered incorrectly, so a larger set came out than intended. Two other subsystems ran on those servers, the index that knows where every object lives and the one that places new objects, and both had to restart. Until they did, S3 in US-EAST-1 could not serve requests. AWS says it had not completely restarted either subsystem in its larger regions for many years, and after that growth the restart and its safety checks took longer than expected. GET, LIST and DELETE came back at 12:26 PM PST and S3 was operating normally at 1:54 PM. The status side suffered too: AWS's Service Health Dashboard could not update individual services' status until 11:37 AM, because its administration console depended on S3, so AWS posted on Twitter and in a banner meanwhile. The tool that reports an outage shared a dependency with the thing that was out. ([AWS's summary](https://aws.amazon.com/message/41926/))

**Cloudflare, 2 July 2019.** A new rule for Cloudflare's web application firewall was deployed worldwide in one push. It was meant to run in "simulate" mode, where traffic passes through a rule and nothing is blocked, but a rule that only observes still has to execute, and one of its regular expressions backtracked so badly that the processors serving web traffic climbed to nearly 100% across the network. For 27 minutes, visitors to any site behind Cloudflare got a 502 error page. The 502s came from Cloudflare's own front-line servers, which still had processor cores free but could not reach the processes that serve HTTP and HTTPS traffic. The layer that answered was healthy and the layer behind it was not, which is the case where a status code points at the wrong place. The first speculation was an attack of a kind nobody had seen. At 14:00 UTC the firewall was identified as the cause, and at 14:07 it was switched off worldwide. ([Cloudflare's write-up](https://blog.cloudflare.com/details-of-the-cloudflare-outage-on-july-2-2019/))

**Fastly, 8 June 2021.** A software deployment that began on 12 May had introduced a bug that a specific customer configuration could trigger. On 8 June a customer pushed a valid configuration change that did, and 85% of Fastly's network began returning errors. Fastly's monitoring flagged it a minute after it began at 09:47 UTC and most services had recovered by 11:00, but Fastly marked the incident mitigated only at 12:35. Its write-up names no status code, only errors. Visitors reach a site through that one layer, so a check that skips it and goes straight to the origin can stay green while the people using the site see failures. ([Fastly's summary](https://www.fastly.com/blog/summary-of-june-8-outage))

**AWS, 7 December 2021.** An automated scaling task for one AWS service triggered unexpected behaviour from a large number of clients on AWS's internal network. The surge of connection attempts overwhelmed the devices linking that network to the main one, and the delays and errors that followed caused even more connection attempts and retries. AWS says its networking clients have well-tested back-off behaviour, but a latent issue stopped them from backing off adequately that day. Real-time monitoring data became unavailable to AWS's own operators at the same time, so they worked from logs. The network devices were fully recovered by 2:22 PM PST, almost seven hours after the 7:30 AM start, and one service was still working through its backlog at 6:40 PM. Running instances kept running. What failed were control planes, such as the APIs that launch instances, console sign-in and Route 53 record changes. ([AWS's summary](https://aws.amazon.com/message/12721/))

**Google Cloud, 12 June 2025.** At about 10:45 PDT a policy change containing unintended blank fields was inserted into the quota and policy tables behind Google's API management, and because quota data is global it reached every region within seconds. The service that checks each API request against those policies hit a null pointer in code added on 29 May, which had no error handling and no feature flag, and it went into a crash loop worldwide. Google's incident summary counts three hours in which external API requests to many Google Cloud and Google Workspace products were rejected with 503 errors, while existing streaming and infrastructure-as-a-service resources were not affected. Recovery was slowest in us-central1, where restarting tasks overloaded the database they depend on, and Google says the service lacked the randomized exponential backoff needed to avoid that. ([Google Cloud's incident report](https://status.cloud.google.com/incidents/ow5i3PPK96RduMcb1SsW))

## What this changes about how you monitor it

Those five outages are not one failure repeated five times. A status tool that shares a dependency with what it reports on, a 502 from a healthy edge, a bug in a layer every site went through, a back-off that did not back off and a 503 from a front door each need a different first responder, and a check that records "failed" for all of them throws that difference away.

That is why, while building InBrief, the HTTP monitor asks for more than a status code. A monitor has an expected status range, and it can also check the response body for a piece of text or a JSON value, so a 200 that carries an error does not pass. The body is read to run that check, up to 64 KiB, and never stored. When a connection fails before any response exists, the check says which cause it was: connection refused, timed out after 10 seconds, no such host, TLS handshake failed, certificate expired, certificate does not match the hostname, or certificate not trusted. When a response does arrive, the status is named for the suspect it points to: 429 as rate-limited, 401 and 403 as blocked, the edge codes that mean nothing is listening behind the proxy as host unreachable, and any other 5xx as a server error.

Both rules came from a failure. An earlier version of the HTTP check caught every thrown error and recorded nothing, so an expired certificate, a wrong hostname on a certificate, a self-signed chain, a refused port, a name that would not resolve and the ten-second timeout all read as "no response": six causes, six different people to call, one sentence. The rate-limit rule has its own story. A monitor pointed at a large search engine's homepage collected 117 consecutive 429s, because the engine was refusing an automated client from a datacentre address while the page itself was healthy, and the dashboard showed the same flat "down" it shows for a real outage. The owner found the cause by trial and error.

The pattern under all five outages is the same one the six clocks showed at the start: the error a visitor sees comes from the layer that answered, and the fault can sit in another. Working out which layer answered is most of the diagnosis.

InBrief itself is priced per feature, and one status page with three monitors is free: [inbrief.sh](https://inbrief.sh/?utm_source=blog&utm_medium=article&utm_campaign=http-without-the-guesswork).
