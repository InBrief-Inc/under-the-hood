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
import shutil

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
<link rel="icon" href="/favicon.ico" sizes="any">
<meta name="theme-color" content="#eef2f3" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0d1419" media="(prefers-color-scheme: dark)">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans:wght@400;500;600&family=Noto+Serif:wght@600;700&display=swap" rel="stylesheet">
{style}
</head>
<body>
<header class="site">
<a class="home" href="/">Under the Hood</a>
<p class="tag">{site_description}</p>
</header>
<main>
<article>
<a class="back" href="/">&larr; All articles</a>
<h1>{title}</h1>
<p class="meta">{date_human}<span class="dot">&middot;</span>{reading_min} min read</p>
{body}
</article>
</main>
<footer class="site">
<p>Written while building <a href="https://inbrief.sh/?utm_source=blog&amp;utm_medium=footer&amp;utm_campaign={slug}">InBrief</a>, a status page and monitoring tool priced per feature. Code and commands for this article are in the <a href="https://github.com/InBrief-Inc/under-the-hood/tree/main/{folder}">under-the-hood</a> repository.</p>
{proof}
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
<link rel="icon" href="/favicon.ico" sizes="any">
<meta name="theme-color" content="#eef2f3" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0d1419" media="(prefers-color-scheme: dark)">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans:wght@400;500;600&family=Noto+Serif:wght@600;700&display=swap" rel="stylesheet">
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
{proof}
</footer>
</body>
</html>
"""

# The widget and badge are the product's own renders (see under-the-hood's
# blog-design notes), embedded as static same-origin assets so nothing here
# depends on a live account. utm_campaign is filled in per page.
PROOF_TEMPLATE = """<div class="proof">
<div class="proof-embed">
<iframe class="ib-embed light" src="/assets/widget-light.html" title="InBrief status widget" loading="lazy" scrolling="no" width="300" height="150"></iframe>
<iframe class="ib-embed dark" src="/assets/widget-dark.html" title="InBrief status widget" loading="lazy" scrolling="no" width="300" height="150"></iframe>
</div>
<div class="proof-embed">
<img class="ib-embed light" src="/assets/badges/badge-light.svg" alt="InBrief status badge: all systems operational" width="202" height="40" loading="lazy">
<img class="ib-embed dark" src="/assets/badges/badge-dark.svg" alt="InBrief status badge: all systems operational" width="202" height="40" loading="lazy">
</div>
<p class="proof-caption">InBrief's status widget and badge, the same ones a status page embeds on its own site. <a href="https://demo.inbrief.sh/?utm_source=blog&amp;utm_medium=footer&amp;utm_campaign={campaign}">See the live public demo</a>.</p>
</div>"""

STYLE = """<style>
:root{color-scheme:light dark}
*,*::before,*::after{box-sizing:border-box}

:root{
  --bg: light-dark(#eef2f3,#0d1419);
  --surface: light-dark(#ffffff,#151e25);
  --text: light-dark(#121a20,#e9eef1);
  --muted: light-dark(#52616b,#9eacb6);
  --faint: light-dark(#5c6c76,#8093a0);
  --line: light-dark(#d8e0e4,#283640);
  --line-strong: light-dark(#bdc9cf,#394b57);
  --brand: light-dark(#1b7a4f,#4fc292);
  --brand-soft: light-dark(#e4efe9,#15261f);
  --code-bg: light-dark(#f1f4f5,#111820);
  --shadow: light-dark(0 1px 2px rgba(19,26,32,.06), 0 1px 3px rgba(0,0,0,.4));
}

html{-webkit-text-size-adjust:100%}
body{
  margin:0;background:var(--bg);color:var(--text);
  font-family:"Noto Sans",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  line-height:1.65;-webkit-font-smoothing:antialiased;
}
h1,h2,h3{font-family:"Noto Serif",Georgia,serif;font-weight:600;line-height:1.2;letter-spacing:-.01em;color:var(--text)}
h1{font-size:2.25rem;margin:.2em 0 .4em}
h2{font-size:1.5rem;margin:1.8em 0 .6em;padding-top:.7em;border-top:1px solid var(--line)}
h3{font-size:1.15rem;margin:1.4em 0 .4em}

a{color:var(--brand);text-decoration:underline;text-underline-offset:2px;text-decoration-color:color-mix(in srgb, var(--brand) 40%, transparent)}
a:hover{text-decoration-color:currentColor}
a:focus-visible{outline:2px solid var(--brand);outline-offset:2px;border-radius:2px}

header.site,footer.site,main{max-width:700px;margin:0 auto;padding-left:20px;padding-right:20px}
header.site{padding-top:48px;padding-bottom:28px;border-bottom:1px solid var(--line)}
a.home{display:inline-block;color:var(--text);text-decoration:none;font-family:"Noto Serif",Georgia,serif;font-weight:700;font-size:1.4rem;letter-spacing:-.01em}
a.home:hover{color:var(--brand)}
.tag{color:var(--muted);margin:.4em 0 0;font-size:1.02rem}

main{padding-top:40px;padding-bottom:20px}

a.back{display:inline-block;color:var(--muted);text-decoration:none;font-size:.9rem;margin-bottom:1.8em}
a.back:hover{color:var(--brand)}

.meta{color:var(--faint);font-size:.9rem;margin:0 0 2em;display:flex;gap:.5em;align-items:center}
.meta .dot{opacity:.6}

article p,article li{font-size:1.08rem;color:var(--text)}
article ul,article ol{padding-left:1.3em}
article li{margin:.3em 0}
article strong{font-weight:650}

article pre{background:var(--code-bg);border:1px solid var(--line);border-radius:8px;padding:14px 16px;overflow-x:auto;font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;font-size:.88rem;line-height:1.55}
article code{font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;background:var(--code-bg);padding:.15em .4em;border-radius:4px;font-size:.9em}
article pre code{background:none;padding:0;font-size:1em}

article blockquote{margin:1.4em 0;padding:.2em 1.2em;border-left:3px solid var(--brand);color:var(--muted)}

article img{max-width:100%;height:auto;display:block;margin:1.6em 0;border:1px solid var(--line);border-radius:10px}

article table{width:100%;border-collapse:collapse;margin:1.4em 0;font-size:.95rem}
article th,article td{border:1px solid var(--line);padding:.5em .7em;text-align:left}
article th{background:var(--brand-soft);font-family:"Noto Serif",Georgia,serif}

article hr{border:none;border-top:1px solid var(--line);margin:2.2em 0}

ul.index{list-style:none;margin:2em 0;padding:0;display:flex;flex-direction:column;gap:14px}
a.card{display:block;border:1px solid var(--line);background:var(--surface);border-radius:10px;padding:22px 24px;text-decoration:none;box-shadow:var(--shadow);transition:border-color .15s ease, transform .15s ease}
a.card:hover{border-color:var(--brand);transform:translateY(-1px)}
a.card:focus-visible{outline:2px solid var(--brand);outline-offset:2px}
.idate{display:block;color:var(--faint);font-size:.85rem;margin-bottom:.35em}
.ititle{display:block;font-family:"Noto Serif",Georgia,serif;font-size:1.25rem;font-weight:600;color:var(--text)}
a.card:hover .ititle{color:var(--brand)}
.idesc{display:block;color:var(--muted);font-size:1rem;line-height:1.55;margin-top:.45em}

footer.site{color:var(--faint);font-size:.9rem;margin-top:3em;border-top:1px solid var(--line);padding-top:24px;padding-bottom:48px}
footer.site a{color:var(--muted);text-decoration:underline;text-decoration-color:var(--line-strong)}
footer.site a:hover{color:var(--brand)}

.proof{margin-top:1.4em;padding-top:1.3em;border-top:1px solid var(--line);display:flex;flex-wrap:wrap;align-items:center;gap:14px 20px}
.proof-embed{flex:0 0 auto;line-height:0}
.proof-embed iframe{border:0}
.proof-embed img{display:block;height:40px;width:auto}
.proof .dark{display:none}
@media (prefers-color-scheme:dark){.proof .light{display:none}.proof .dark{display:block}}
.proof-caption{flex-basis:100%;margin:0;color:var(--faint);font-size:.85rem;line-height:1.5}
.proof-caption a{color:var(--muted);text-decoration-color:var(--line-strong)}
.proof-caption a:hover{color:var(--brand)}

@media (max-width:600px){
  h1{font-size:1.7rem}
  header.site{padding-top:32px;padding-bottom:22px}
  main{padding-top:28px}
  a.card{padding:18px}
}
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
    meta["reading_min"] = max(1, round(len(body_md.split()) / 220))
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
        art["date_human"] = datetime.date.fromisoformat(art["date"]).strftime("%d %B %Y")
        html = PAGE_TEMPLATE.format(
            title=art["title"],
            description=art["description"],
            url=url,
            body=art["body_html"],
            date_human=art["date_human"],
            reading_min=art["reading_min"],
            folder=art["folder"],
            slug=art["slug"],
            site_title=SITE_TITLE,
            site_description=SITE_DESCRIPTION,
            site_url=SITE_URL,
            style=STYLE,
            proof=PROOF_TEMPLATE.format(campaign=art["slug"]),
        )
        (articles_dir / f"{art['slug']}.html").write_text(html)

        src_assets = ROOT / art["folder"] / "assets"
        if src_assets.is_dir():
            dest_assets = DOCS / "assets" / art["slug"]
            shutil.rmtree(dest_assets, ignore_errors=True)
            shutil.copytree(src_assets, dest_assets)

    items = "\n".join(
        f'<li><a class="card" href="/articles/{a["slug"]}.html">'
        f'<span class="idate">{a["date_human"]} &middot; {a["reading_min"]} min read</span>'
        f'<span class="ititle">{a["title"]}</span>'
        f'<span class="idesc">{a["description"]}</span></a></li>'
        for a in reversed(articles)
    )
    (DOCS / "index.html").write_text(
        INDEX_TEMPLATE.format(
            items=items,
            site_title=SITE_TITLE,
            site_description=SITE_DESCRIPTION,
            site_url=SITE_URL,
            style=STYLE,
            proof=PROOF_TEMPLATE.format(campaign="index"),
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
