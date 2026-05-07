import httpx
import pytest
import respx

from otwarta.scrapers.base import AsyncBaseScraper


@respx.mock
@pytest.mark.asyncio
async def test_fetch_returns_html():
    respx.get("https://example.com/article").mock(
        return_value=httpx.Response(200, text="<h1>Test</h1>")
    )
    scraper = AsyncBaseScraper(domain="example.com", rate_limit_delay=0)
    response = await scraper._fetch("https://example.com/article")
    assert response.status_code == 200
    assert "<h1>Test</h1>" in response.text


@respx.mock
@pytest.mark.asyncio
async def test_fetch_skips_on_403():
    respx.get("https://example.com/blocked").mock(return_value=httpx.Response(403))
    scraper = AsyncBaseScraper(domain="example.com", rate_limit_delay=0)
    result = await scraper.fetch_or_skip("https://example.com/blocked")
    assert result is None
