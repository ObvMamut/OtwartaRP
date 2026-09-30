import httpx
import pytest
import respx

from otwarta.scrapers.sites.pch24 import SITEMAP_INDEX_URL, PCH24AsyncScraper

SAMPLE_SITEMAP_INDEX = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap>
    <loc>https://pch24.pl/sitemap/articles-sitemap_1.xml</loc>
    <lastmod>2024-10-01T00:00:00+00:00</lastmod>
  </sitemap>
  <sitemap>
    <loc>https://pch24.pl/sitemap/tags-sitemap_1.xml</loc>
    <lastmod>2024-10-01T00:00:00+00:00</lastmod>
  </sitemap>
</sitemapindex>
"""

SAMPLE_ARTICLES_SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://pch24.pl/wiadomosci/izrael-i-hamas-walka-o-przyszlosc</loc>
    <lastmod>2023-11-01T12:00:00+00:00</lastmod>
  </url>
  <url>
    <loc>https://pch24.pl/wiadomosci/inny-artykul-z-2023</loc>
    <lastmod>2023-10-15T10:00:00+00:00</lastmod>
  </url>
  <url>
    <loc>https://pch24.pl/wiadomosci/stary-artykul-edytowany-po-end-date</loc>
    <lastmod>2025-03-01T10:00:00+00:00</lastmod>
  </url>
  <url>
    <loc>https://pch24.pl/tag/izrael/</loc>
    <lastmod>2023-10-15T10:00:00+00:00</lastmod>
  </url>
  <url>
    <loc>https://pch24.pl/regulamin/regulamin,1</loc>
    <lastmod>2023-10-15T10:00:00+00:00</lastmod>
  </url>
</urlset>
"""

# Sitemap where every article has lastmod > end_date (sitemaps 107-122 pattern)
SAMPLE_SITEMAP_ALL_TOO_NEW = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://pch24.pl/wiadomosci/nowy-artykul-1</loc>
    <lastmod>2025-01-10T10:00:00+00:00</lastmod>
  </url>
  <url>
    <loc>https://pch24.pl/wiadomosci/nowy-artykul-2</loc>
    <lastmod>2024-11-15T10:00:00+00:00</lastmod>
  </url>
</urlset>
"""

SAMPLE_ARTICLE_HTML = """
<html><head>
  <meta property="article:published_time" content="2023-11-01T12:00:00+01:00">
</head><body>
  <h1 class="entry-title">Artykuł o Izraelu</h1>
  <div class="entry-content"><p>Treść artykułu.</p></div>
  <a rel="author">Jan Kowalski</a>
</body></html>
"""


@respx.mock
@pytest.mark.asyncio
async def test_discovers_article_urls_from_sitemap():
    from datetime import date

    respx.get(SITEMAP_INDEX_URL).mock(
        return_value=httpx.Response(200, text=SAMPLE_SITEMAP_INDEX)
    )
    respx.get("https://pch24.pl/sitemap/articles-sitemap_1.xml").mock(
        return_value=httpx.Response(200, text=SAMPLE_ARTICLES_SITEMAP)
    )

    scraper = PCH24AsyncScraper(rate_limit_delay=0)
    start = date(2022, 10, 7)
    end = date(2024, 10, 7)

    urls = [url async for url, _ in scraper._iter_sitemap_article_urls(start, end)]

    # Article URLs in range pass the filter
    assert any("izrael-i-hamas" in u for u in urls)
    assert any("inny-artykul" in u for u in urls)
    # Old article with lastmod AFTER end_date must also be yielded (bug fix: lastmod ≠ pub date)
    assert any("stary-artykul-edytowany-po-end-date" in u for u in urls)
    # Tag and static pages are filtered out
    assert not any("tag/izrael" in u for u in urls)
    assert not any("regulamin" in u for u in urls)


@respx.mock
@pytest.mark.asyncio
async def test_discover_urls_in_range_returns_unique_sitemap_urls():
    """The dashboard scrape endpoint calls discover_urls_in_range on every site adapter."""
    from datetime import date

    respx.get(SITEMAP_INDEX_URL).mock(
        return_value=httpx.Response(200, text=SAMPLE_SITEMAP_INDEX)
    )
    respx.get("https://pch24.pl/sitemap/articles-sitemap_1.xml").mock(
        return_value=httpx.Response(200, text=SAMPLE_ARTICLES_SITEMAP)
    )

    scraper = PCH24AsyncScraper(rate_limit_delay=0)
    urls = await scraper.discover_urls_in_range(date(2022, 10, 7), date(2024, 10, 7))

    assert len(urls) == len(set(urls)) == 3
    assert "https://pch24.pl/wiadomosci/izrael-i-hamas-walka-o-przyszlosc" in urls


SAMPLE_SITEMAP_INDEX_TWO = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap>
    <loc>https://pch24.pl/sitemap/articles-sitemap_2.xml</loc>
  </sitemap>
  <sitemap>
    <loc>https://pch24.pl/sitemap/articles-sitemap_1.xml</loc>
  </sitemap>
</sitemapindex>
"""


@respx.mock
@pytest.mark.asyncio
async def test_skips_entirely_too_new_sitemaps():
    """Sitemaps where every lastmod > end_date are skipped without yielding any URLs."""
    from datetime import date

    respx.get(SITEMAP_INDEX_URL).mock(
        return_value=httpx.Response(200, text=SAMPLE_SITEMAP_INDEX_TWO)
    )
    # sitemap_2 = all articles newer than end_date (sitemap 107-122 pattern)
    respx.get("https://pch24.pl/sitemap/articles-sitemap_2.xml").mock(
        return_value=httpx.Response(200, text=SAMPLE_SITEMAP_ALL_TOO_NEW)
    )
    # sitemap_1 = normal mixed sitemap
    respx.get("https://pch24.pl/sitemap/articles-sitemap_1.xml").mock(
        return_value=httpx.Response(200, text=SAMPLE_ARTICLES_SITEMAP)
    )

    scraper = PCH24AsyncScraper(rate_limit_delay=0)
    start = date(2022, 10, 7)
    end = date(2024, 10, 7)

    urls = [url async for url, _ in scraper._iter_sitemap_article_urls(start, end)]

    # sitemap_2 URLs must not appear (all too new)
    assert not any("nowy-artykul" in u for u in urls)
    # sitemap_1 URLs must appear
    assert any("izrael-i-hamas" in u for u in urls)
    # Old article with recent lastmod from sitemap_1 must appear (bug fix)
    assert any("stary-artykul-edytowany-po-end-date" in u for u in urls)


@pytest.mark.asyncio
async def test_parses_pch24_article():
    scraper = PCH24AsyncScraper(rate_limit_delay=0)
    article = await scraper.parse_article(SAMPLE_ARTICLE_HTML, "https://pch24.pl/artykul/")
    assert article is not None
    assert article.title == "Artykuł o Izraelu"
    assert article.publication_date is not None
    assert article.author == "Jan Kowalski"
