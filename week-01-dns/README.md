---
title: DNS without the confusion
description: What happens, step by step, between typing a name and getting a byte back, the three record types that carry the web, why a DNS change never really "propagates", and five real outages that show where each piece breaks.
date: 2026-09-23
slug: dns-without-the-confusion
---

A domain name passes through four separate businesses before a browser gets a single byte back: the registrar, the DNS provider, the host, and often a CDN in front of the host. Most of the time all four are the same company, so nobody notices the seams. On the day one of them fails, the seams are the whole incident.

Here is what happens, in order, between typing a name and getting an answer, the three record types that carry almost everything on the web, why a DNS change never really "propagates", and five outages where each of those pieces broke in public. The commands in this article are runnable scripts in [`scripts/`](https://github.com/InBrief-Inc/under-the-hood/tree/main/week-01-dns/scripts), not just examples to read.

## Four companies, one page

A registrar records, in the registry for that top-level domain, that a name belongs to you for a year. That is the whole job: a land registry. It does not answer DNS queries and does not host a byte of your site.

A DNS provider runs the nameservers that answer "where is this name?" with an address. It is often the same company as the registrar, which is why people merge the two in their heads, but it is a separate service you can move on its own.

The host owns the machine that address points at. A CDN, if there is one, sits in front of the host: browsers talk to the CDN, and the CDN talks to your origin.

Four contracts, four ways to be down. The registrar lapses and the name stops resolving anywhere within a day or two. The nameservers go down and nobody can find the address, while the server behind it stays perfectly healthy. The host goes down and the name resolves but the connection fails. The CDN goes down and the name resolves, the edge answers with a 5xx, and the origin sits idle the whole time. A server-is-up check only ever covers one of those four.

## What actually happens when you type a name

The library call inside your application is a stub resolver. It sends one question to whatever address is configured, usually your router or ISP, with the "recursion desired" bit set: do the whole job, I'll wait. It has no idea where the root servers are, and it doesn't need to.

The recursive resolver on the other end does the walking, and it works iteratively: every server it asks either answers or points somewhere closer. A cold lookup for `yourapp.com` looks like this:

```
resolver → root:        "yourapp.com?"
root     → resolver:    "not mine, ask the .com servers"
resolver → .com:        "yourapp.com?"
.com     → resolver:    "not mine, ask ns1.yourapp.com, here's its address"
resolver → ns1:         "yourapp.com?"
ns1      → resolver:    "203.0.113.7, keep it 300 seconds" (authoritative)
```

Recursion is the contract the stub resolver signs. Iteration is how the recursive resolver honors it, and only one of those two questions ever leaves your machine.

The `.com` server handed over ns1's address, not just its name, for a specific reason: ns1 lives inside `yourapp.com`, so to find it the resolver would otherwise have to ask the very server it is looking for. The parent zone breaks that loop by storing the address itself. That record is called glue, and it lives at your registrar, not in your own zone file. Move the nameserver and forget to update the glue, and the world keeps knocking on the old door.

Every one of those referrals gets cached for its own TTL, so a warm lookup skips straight to the last line. That's also why the root servers barely notice most traffic: there are only 13 root server names (`a.root-servers.net` through `m.root-servers.net`, a limit left over from a 512-byte answer cap written into the DNS spec in 1987), each one anycast across more than 1,500 physical machines, and the `.com` referral alone can be cached for two full days.

## The three records that carry the web

`A` maps a name to an IPv4 address. `AAAA` does the same for IPv6, four A's because the address is four times longer: 128 bits against 32. `CNAME` maps nothing on its own; it says "this name is really that other name, ask again."

The apex of a zone, the bare domain with no subdomain, can hold an `A` record or an `ALIAS`-style record, but never a plain `CNAME`. The rule dates to 1987 (RFC 1034): a name with a CNAME may carry no other record, and the apex must carry the zone's `SOA` and `NS` records. A provider that refuses a `CNAME` at the apex is following the spec. One that silently accepts it will redirect your mail lookups too, and email stops.

That single rule is why the industry ended up with three separate workarounds. `ALIAS`, `ANAME`, and CNAME flattening are one trick under three names: the DNS provider chases the real target at query time and hands out plain `A` and `AAAA` records instead. Cloudflare has done this since 2014. The standards-track fix arrived later and is legal at the apex because it's a distinct record type: the `HTTPS` record, type 65, from RFC 9460 in 2023. Browsers already query for it alongside `A` and `AAAA`.

The failure shape that catches the most people is a wrong or missing `AAAA` record. It passes every IPv4 check, so a health check and a QA pass both go green, while the address goes to a machine where nothing listens on port 443. Only networks that prefer IPv6 notice, and Google puts more than 40% of its own traffic on IPv6 now. Browsers hide the symptom because of Happy Eyeballs (RFC 8305): they give the IPv6 attempt about 250 milliseconds, then fall back. A command-line tool without that fallback just hangs for a full connection timeout, which is why the bug report so often reads "works on my phone, fails in the CI pipeline" instead of "DNS is broken."

## Caches, leases, and the myth of propagation

Nothing gets pushed when you change a DNS record. Your nameserver doesn't notify anyone; every resolver that already asked is holding a lease, in seconds, called the TTL, and it will keep serving that answer until the lease runs out.

Say the TTL is 3,600 seconds and you change the record at noon. A resolver that asked at 11:59 keeps the old answer until 12:59. One that asked at 11:10 keeps it until 12:10. One that has never asked gets the new answer immediately. Three resolvers, three different answers, at the same instant, and none of them are wrong. That is why "wait for it to propagate" is the wrong mental model: nothing is spreading anywhere. You are waiting for leases to expire, and every lease started at a different time.

Resolvers cache the absence of an answer too. A name that doesn't exist gets `NXDOMAIN`; one that exists but lacks the record type you asked for gets an empty `NODATA`. Both get cached, for a length set by the last field of the zone's `SOA` record, repurposed for exactly this by RFC 2308. Ask for a record a minute before you create it, and the resolver can hold "does not exist" for the whole of that negative TTL. In practice this is usually your own health check asking first.

The runbook for a migration has a clock built into it, and the step almost everyone skips is the last one:

1. Lower the TTL (say, to 300) a full day before the move. Change nothing else yet.
2. Wait one old TTL, so every existing lease has expired under the new, shorter one.
3. Change the record. Most of the world sees it within minutes.
4. A day or two later, raise the TTL back to something like 3,600.

Skip step four and every resolver on the internet starts asking your nameservers twelve times more often than before, indefinitely, for no reason once the migration is done.

## Reading DNS from a terminal

Five short scripts live in this folder, and each answers one question you'd otherwise guess at:

- [`01-find-your-nameservers.sh`](https://github.com/InBrief-Inc/under-the-hood/blob/main/week-01-dns/scripts/01-find-your-nameservers.sh) runs `whois` and `dig NS` to show who actually controls a domain, which is a guess more often than people admit.
- [`02-trace-resolution.sh`](https://github.com/InBrief-Inc/under-the-hood/blob/main/week-01-dns/scripts/02-trace-resolution.sh) runs `dig +trace`, which skips your resolver's cache entirely and prints every referral from the root down, so a broken chain shows you exactly which hop stopped answering.
- [`03-check-records.sh`](https://github.com/InBrief-Inc/under-the-hood/blob/main/week-01-dns/scripts/03-check-records.sh) prints the `A`, `AAAA`, and `CNAME` chain for a name in one pass, so a missing or stray `AAAA` doesn't hide behind a passing `A` record.
- [`04-cache-vs-authority.sh`](https://github.com/InBrief-Inc/under-the-hood/blob/main/week-01-dns/scripts/04-cache-vs-authority.sh) queries a public resolver and the domain's own authoritative server side by side. The `aa` flag in the response tells you which one you're actually looking at, and the two TTL values tell you how far apart they are.
- [`05-ipv6-reachability.sh`](https://github.com/InBrief-Inc/under-the-hood/blob/main/week-01-dns/scripts/05-ipv6-reachability.sh) runs `curl -6` and `curl -4` against the same name, because a resolver answer and a working connection are two different facts.

Each takes a domain as its only argument, defaults to `example.com` if you don't pass one, and needs nothing beyond `dig`, `whois`, and `curl`.

## Five times this broke, in public

**Dyn, 21 October 2016.** A DDoS attack hit Dyn's authoritative nameservers, and Twitter, GitHub, and Reddit went offline for much of a day while every one of their own servers stayed healthy. Nothing was wrong with the sites; the phone book stopped answering. It's the reason "use two DNS providers" became standard advice: your authoritative side is a specific, nameable target, and it can be worth attacking on its own.

**Route 53, 22 October 2019.** AWS's authoritative DNS came under a DDoS for the better part of a working day. The mitigation dropped attack traffic and, by AWS's own account, caught some legitimate queries in the process, so lookups for names like S3 failed intermittently. The root servers were fine, the `.com` servers were fine, and any zone hosted elsewhere was fine. Only the lookups that walked through that one authoritative hop failed, and only some of the time, which is close to the worst kind of failure to reproduce: a retry often just worked.

**Azure DNS, 1 April 2021.** For 39 minutes, some resolvers hitting Azure's DNS service got timeouts under load rather than a clean answer or a clean failure. A timeout is its own failure class, distinct from "no such name" and distinct from a refused connection, and it points a debugging session in a different direction than either of those.

**Slack, 30 September 2021.** Slack was finishing a DNSSEC rollout and published the DS record for its main domain at the registry, the record that tells validating resolvers to start checking signatures. Because of how the zone's wildcard records interacted with the signed proof of non-existence, some resolvers began reporting that real subdomains didn't exist. Slack pulled the DS record back quickly. That fixed nothing for any resolver that had already fetched it: a DS record lives in the parent zone with a TTL measured in hours, and every resolver holding it kept failing until its own lease ran out or someone flushed it by hand. The rollback was correct. The caches didn't care.

**Facebook, 4 October 2021.** A backbone configuration change during routine maintenance withdrew the routes to Facebook's own network, including the routers announcing its authoritative DNS servers. With no path to those addresses, resolvers everywhere got no response at all, which most software reports as a hang rather than a clean error, and Facebook, Instagram, and WhatsApp were unreachable for about six hours. The DNS protocol never broke; nothing was misconfigured in a zone file. The nameservers themselves simply stopped being reachable, which is a reminder that your authoritative DNS depends on the same network as everything else you run, including, in that case, the badge readers the on-site engineers needed to get into the building.

## What this changes about how you monitor it

Those five outages are not one failure repeated five times. A name that doesn't exist, a resolver that times out, an authoritative side that's unreachable at the network layer, a cache that outlives your fix by hours: each of those needs a different first responder, and none of them look alike from the outside. A generic "request failed" log line erases the difference on purpose.

That distinction is why, while building InBrief, DNS ended up as its own monitor type sitting next to HTTP and TCP rather than a checkbox on an HTTP check. It picks a record type, can carry an expected answer so a correct-looking response to the wrong question still fails the check, and can be pointed at a specific resolver, because a green answer from one resolver says very little about what a resolver on the other side of the world believes. Certificate expiry is checked separately, as part of the HTTP, TCP, SMTP, and WebSocket monitors, since a certificate problem and a DNS problem are never the same call to make at 3 a.m.

A forgotten CNAME pointing at an already shut-down product surfaced here in a search-indexing audit on 11 September, months after the project behind it had closed, still resolving, still answering with whatever the old host serves for an unclaimed name. Nothing paged anyone. The record was still valid DNS; it just pointed at a promise nobody was keeping anymore.

That's the pattern underneath all five outages above, and the one from this September too: the record was never the hard part. Knowing what's behind it, and who else is depending on it staying true, is the whole job.

InBrief itself is priced per feature, from $1 a month: [inbrief.sh](https://inbrief.sh/?utm_source=blog&utm_medium=article&utm_campaign=dns-without-the-confusion).
