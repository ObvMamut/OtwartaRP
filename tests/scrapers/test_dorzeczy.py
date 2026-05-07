import pytest
import respx
import httpx
from otwarta.scrapers.sites.dorzeczy import DoRzeczyAsyncScraper

SAMPLE_CATEGORY_HTML = """
<html><body>
  <a href="/kraj/123456/test-article.html">Article 1</a>
  <a href="/kraj/123457/another-article.html">Article 2</a>
  <a href="/kraj/">Not an article</a>
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
async def test_discovers_article_urls():
    respx.get("https://dorzeczy.pl/kraj/1").mock(return_value=httpx.Response(200, text=SAMPLE_CATEGORY_HTML))
    scraper = DoRzeczyAsyncScraper(rate_limit_delay=0)
    urls = await scraper.get_article_urls_for_page(1)
    assert "https://dorzeczy.pl/kraj/123456/test-article.html" in urls
    assert "https://dorzeczy.pl/kraj/" not in urls


@respx.mock
@pytest.mark.asyncio
async def test_parses_article():
    scraper = DoRzeczyAsyncScraper(rate_limit_delay=0)
    article = await scraper.parse_article(SAMPLE_ARTICLE_HTML, "https://dorzeczy.pl/kraj/123/test.html")
    assert article is not None
    assert article.title == "Test Article"
    assert "Article body text" in (article.body or "")
    assert article.publication_date is not None
