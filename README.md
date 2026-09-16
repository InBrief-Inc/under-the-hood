# Under the Hood

How the internet actually works, one week at a time: DNS, HTTP, TCP/IP, TLS,
logs, observability, deploys, databases, and the production failures that
teach you all of it faster than a tutorial does.

Each folder is one week: an article and a handful of small, runnable shell
scripts that do exactly what the article describes. No installs beyond
`dig`, `whois`, and `curl`, which most systems already have.

- [`week-01-dns/`](week-01-dns/) — DNS: resolution, record types, TTLs and
  caching, and five real outages that show where each piece breaks.

The same articles are published, one HTML page each, at
[blog.inbrief.sh](https://blog.inbrief.sh).

## Building the blog

The `docs/` folder is what GitHub Pages serves. It's generated, not
hand-edited: every `week-*/README.md` is the single source for both the
GitHub page you're reading and its blog copy.

```bash
pip install -r requirements.txt
python3 tools/build_blog.py
```

That rewrites `docs/index.html`, `docs/articles/*.html`, `docs/sitemap.xml`,
and `docs/feed.xml` from the current articles. Commit the result along with
whatever `week-*/README.md` you changed.

## Written by

[Milad Fahmy](https://github.com/miladezzat), while building
[InBrief](https://inbrief.sh?utm_source=github&utm_medium=readme&utm_campaign=under-the-hood),
a status page and monitoring tool priced per feature.
