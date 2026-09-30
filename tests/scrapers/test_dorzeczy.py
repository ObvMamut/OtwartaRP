
import httpx
import pytest
import respx

from otwarta.scrapers.sites.dorzeczy import DoRzeczyAsyncScraper

SAMPLE_ARCHIVE_YEAR_HTML = """
<html><body>
  <a href="/archiwum/558/dorzeczy-51-2023.html">Do Rzeczy 51/2023</a>
  <a href="/archiwum/557/dorzeczy-50-2023.html">Do Rzeczy 50/2023</a>
  <a href="/archiwum/">Not an issue</a>
  <a href="/archiwum/558/dorzeczy-51-2023.html">Duplicate link</a>
</body></html>
"""

SAMPLE_ISSUE_HTML = """
<html><body>
  <a href="https://dorzeczy.pl/opinie/525852/lisicki-manifest.html?_gl=tracking">Article 1</a>
  <a href="https://dorzeczy.pl/kraj/525853/another-article.html">Article 2</a>
  <a href="https://dorzeczy.pl/">Not an article</a>
</body></html>
"""

SAMPLE_ARTICLE_HTML = """
<html><head>
  <meta property="article:published_time" content="2023-10-08T10:00:00+02:00">
</head><body>
  <h1 class="art-title">Test Article</h1>
  <div class="art-content">Article body text here.</div>
</body></html>
"""


@respx.mock
@pytest.mark.asyncio
async def test_get_issue_urls_for_year():
    respx.get("https://tygodnik.dorzeczy.pl/archiwum/rok/2023").mock(
        return_value=httpx.Response(200, text=SAMPLE_ARCHIVE_YEAR_HTML)
    )
    scraper = DoRzeczyAsyncScraper(rate_limit_delay=0)
    results = await scraper._get_issue_urls_for_year(2023)
    urls = [u for u, _ in results]
    # Deduplication: duplicate link should yield only one entry
    assert len(results) == 2
    assert "https://tygodnik.dorzeczy.pl/archiwum/558/dorzeczy-51-2023.html" in urls
    assert "https://tygodnik.dorzeczy.pl/archiwum/557/dorzeczy-50-2023.html" in urls
    # Approximate date for week 51 of 2023 is in December
    week51_date = next(d for u, d in results if "51" in u)
    assert week51_date.year == 2023
    assert week51_date.month == 12


@respx.mock
@pytest.mark.asyncio
async def test_get_article_urls_for_issue():
    issue_url = "https://tygodnik.dorzeczy.pl/archiwum/558/dorzeczy-51-2023.html"
    respx.get(issue_url).mock(return_value=httpx.Response(200, text=SAMPLE_ISSUE_HTML))
    scraper = DoRzeczyAsyncScraper(rate_limit_delay=0)
    urls = await scraper._get_article_urls_for_issue(issue_url)
    assert "https://dorzeczy.pl/opinie/525852/lisicki-manifest.html" in urls
    assert "https://dorzeczy.pl/kraj/525853/another-article.html" in urls
    # Non-article link excluded
    assert "https://dorzeczy.pl/" not in urls
    # Tracking params stripped
    assert all("?" not in u for u in urls)


def test_strip_tracking_removes_query_and_fragment():
    scraper = DoRzeczyAsyncScraper(rate_limit_delay=0)
    raw = "https://dorzeczy.pl/opinie/525852/slug.html?_gl=abc&_ga=xyz#section"
    assert scraper._strip_tracking(raw) == "https://dorzeczy.pl/opinie/525852/slug.html"


@respx.mock
@pytest.mark.asyncio
async def test_parses_article():
    scraper = DoRzeczyAsyncScraper(rate_limit_delay=0)
    article = await scraper.parse_article(
        SAMPLE_ARTICLE_HTML, "https://dorzeczy.pl/kraj/123/test.html"
    )
    assert article is not None
    assert article.title == "Test Article"
    assert "Article body text" in (article.body or "")
    assert article.publication_date is not None
