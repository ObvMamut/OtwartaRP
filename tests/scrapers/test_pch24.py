import pytest
import respx
import httpx
from otwarta.scrapers.sites.pch24 import PCH24AsyncScraper

SAMPLE_SEARCH_HTML = """
<html><body>
  <a href="https://pch24.pl/izrael-i-hamas-walka-o-przyszlosc/">Izrael i Hamas</a>
  <a href="https://pch24.pl/tag/izrael/">Tag page - skip</a>
  <a href="https://pch24.pl/?s=izrael&paged=2">Search page - skip</a>
</body></html>
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
async def test_discovers_article_urls_from_search():
    respx.get("https://pch24.pl/?s=żydzi&paged=1").mock(
        return_value=httpx.Response(200, text=SAMPLE_SEARCH_HTML)
    )
    scraper = PCH24AsyncScraper(rate_limit_delay=0)
    urls = await scraper.get_article_urls_for_keyword_page("żydzi", 1)
    assert any("izrael-i-hamas" in u for u in urls)
    assert not any("tag/izrael" in u for u in urls)


@pytest.mark.asyncio
async def test_parses_pch24_article():
    scraper = PCH24AsyncScraper(rate_limit_delay=0)
    article = await scraper.parse_article(SAMPLE_ARTICLE_HTML, "https://pch24.pl/artykul/")
    assert article is not None
    assert article.title == "Artykuł o Izraelu"
    assert article.publication_date is not None
    assert article.author == "Jan Kowalski"
