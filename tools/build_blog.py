#!/usr/bin/env python3
"""Build blog.inbrief.sh from the weekXX/README.md files.

Each week folder's README.md is the single source: a small front-matter
block (title, description, date, slug) followed by the article in
markdown. This script renders every one of those into a static HTML file
under docs/, plus an index page, a sitemap and an RSS feed. Nothing here
runs on GitHub; the generated docs/ folder is committed like any other
file and GitHub Pages just serves it.

Usage: python3 tools/build_blog.py
"""
from __future__ import annotations

import datetime
import html
import pathlib
import re

import markdown

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
SITE_URL = "https://blog.inbrief.sh"
SITE_TITLE = "Under the Hood"
SITE_DESCRIPTION = "How the internet actually works, one week at a time."

FRONT_MATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)

PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — Under the Hood</title>
<meta name="description" content="{description}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="article">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:url" content="{url}">
<meta name="twitter:card" content="summary">
<link rel="alternate" type="application/rss+xml" title="{site_title}" href="{site_url}/feed.xml">
{style}
</head>
<body>
<header class="site">
<a class="home" href="/">Under the Hood</a>
<p class="tag">{site_description}</p>
</header>
<main>
<article>
<h1>{title}</h1>
<p class="meta">{date_human}</p>
{body}
</article>
</main>
<footer class="site">
<p>Written while building <a href="https://inbrief.sh/?utm_source=blog&amp;utm_medium=footer&amp;utm_campaign={slug}">InBrief</a>, a status page and monitoring tool priced per feature. Code and commands for this article are in the <a href="https://github.com/InBrief-Inc/under-the-hood/tree/main/{folder}">under-the-hood</a> repository.</p>
</footer>
</body>
</html>
"""

INDEX_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{site_title}</title>
<meta name="description" content="{site_description}">
<link rel="canonical" href="{site_url}/">
<link rel="alternate" type="application/rss+xml" title="{site_title}" href="{site_url}/feed.xml">
{style}
</head>
<body>
<header class="site">
<a class="home" href="/">Under the Hood</a>
<p class="tag">{site_description}</p>
</header>
<main>
<ul class="index">
{items}
</ul>
</main>
<footer class="site">
<p>Written while building <a href="https://inbrief.sh/?utm_source=blog&amp;utm_medium=footer&amp;utm_campaign=index">InBrief</a>, a status page and monitoring tool priced per feature.</p>
</footer>
</body>
</html>
"""

STYLE = """<style>
:root{color-scheme:light}
*{box-sizing:border-box}
body{margin:0;background:#fff;color:#111;font-family:"Noto Sans",-apple-system,Helvetica,Arial,sans-serif;line-height:1.6}
h1,h2,h3{font-family:"Noto Serif",Georgia,serif;font-weight:600;line-height:1.25}
h1{font-size:2rem;margin:0 0 .3em}
h2{font-size:1.4rem;margin:1.6em 0 .5em}
a{color:#0b5fff}
a.home{color:#111;text-decoration:none;font-family:"Noto Serif",Georgia,serif;font-weight:600;font-size:1.3rem}
header.site,footer.site,main{max-width:680px;margin:0 auto;padding:0 20px}
header.site{padding-top:40px}
.tag{color:#555;margin-top:.3em}
.meta{color:#777;font-size:.9rem;margin-top:0}
article p,article li{font-size:1.05rem}
article pre{background:#f4f4f4;border-radius:6px;padding:12px 14px;overflow-x:auto;font-family:"SFMono-Regular",Consolas,monospace;font-size:.9rem}
article code{font-family:"SFMono-Regular",Consolas,monospace;background:#f4f4f4;padding:.1em .3em;border-radius:4px}
article pre code{background:none;padding:0}
ul.index{list-style:none;margin:2em 0;padding:0}
ul.index li{margin-bottom:1.4em}
ul.index a{font-family:"Noto Serif",Georgia,serif;font-size:1.2rem;text-decoration:none}
ul.index p{margin:.2em 0 0;color:#444}
footer.site{color:#777;font-size:.9rem;margin:3em auto 3em;border-top:1px solid #eee;padding-top:1.2em}
</style>"""


def parse_article(path: pathlib.Path) -> dict:
    text = path.read_text()
    m = FRONT_MATTER_RE.match(text)
    if not m:
        raise ValueError(f"{path} has no front matter block")
    front, body_md = m.groups()
    meta = {}
    for line in front.splitlines():
        if not line.strip():
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    for required in ("title", "description", "date", "slug"):
        if required not in meta:
            raise ValueError(f"{path} is missing '{required}' in front matter")
    # title/description land in both HTML text and quoted attributes
    # (meta content=""), so escape them once here at the source.
    meta["title"] = html.escape(meta["title"])
    meta["description"] = html.escape(meta["description"])
    meta["body_html"] = markdown.markdown(
        body_md.strip(), extensions=["fenced_code", "tables"]
    )
    meta["folder"] = path.parent.name
    return meta


def build() -> None:
    articles = sorted(
        (parse_article(p) for p in ROOT.glob("week-*/README.md")),
        key=lambda a: a["date"],
    )

    articles_dir = DOCS / "articles"
    articles_dir.mkdir(parents=True, exist_ok=True)

    for art in articles:
        url = f"{SITE_URL}/articles/{art['slug']}.html"
        date_human = datetime.date.fromisoformat(art["date"]).strftime("%d %B %Y")
        html = PAGE_TEMPLATE.format(
            title=art["title"],
            description=art["description"],
            url=url,
            body=art["body_html"],
            date_human=date_human,
            folder=art["folder"],
            slug=art["slug"],
            site_title=SITE_TITLE,
            site_description=SITE_DESCRIPTION,
            site_url=SITE_URL,
            style=STYLE,
        )
        (articles_dir / f"{art['slug']}.html").write_text(html)

    items = "\n".join(
        f'<li><a href="/articles/{a["slug"]}.html">{a["title"]}</a>'
        f'<p>{a["description"]}</p></li>'
        for a in reversed(articles)
    )
    (DOCS / "index.html").write_text(
        INDEX_TEMPLATE.format(
            items=items,
            site_title=SITE_TITLE,
            site_description=SITE_DESCRIPTION,
            site_url=SITE_URL,
            style=STYLE,
        )
    )

    urls = [f"{SITE_URL}/"] + [
        f"{SITE_URL}/articles/{a['slug']}.html" for a in articles
    ]
    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"<url><loc>{u}</loc></url>\n" for u in urls)
        + "</urlset>\n"
    )
    (DOCS / "sitemap.xml").write_text(sitemap)

    rss_items = "\n".join(
        "<item>"
        f"<title>{a['title']}</title>"
        f"<link>{SITE_URL}/articles/{a['slug']}.html</link>"
        f"<guid>{SITE_URL}/articles/{a['slug']}.html</guid>"
        f"<description>{a['description']}</description>"
        f"<pubDate>{datetime.date.fromisoformat(a['date']).strftime('%a, %d %b %Y 00:00:00 +0000')}</pubDate>"
        "</item>"
        for a in reversed(articles)
    )
    rss = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>'
        f"<title>{SITE_TITLE}</title>"
        f"<link>{SITE_URL}/</link>"
        f"<description>{SITE_DESCRIPTION}</description>"
        f"{rss_items}"
        "</channel></rss>\n"
    )
    (DOCS / "feed.xml").write_text(rss)

    (DOCS / "CNAME").write_text("blog.inbrief.sh\n")
    (DOCS / ".nojekyll").write_text("")

    print(f"Built {len(articles)} article(s) into {DOCS}")


if __name__ == "__main__":
    build()
