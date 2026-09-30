import asyncio
import json
import logging
import re
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx
from bs4 import BeautifulSoup
from loguru import logger
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


@dataclass
class ScrapedArticle:
    url: str
    site: str
    title: str | None
    author: str | None
    publication_date: datetime | None
    body: str | None


class AsyncBaseScraper:
    POLISH_MONTHS = {
        "stycznia": 1, "lutego": 2, "marca": 3, "kwietnia": 4,
        "maja": 5, "czerwca": 6, "lipca": 7, "sierpnia": 8,
        "września": 9, "października": 10, "listopada": 11, "grudnia": 12,
    }

    def __init__(
        self, domain: str, rate_limit_delay: float = 1.0, user_agent: str = "OtwartaResearch/1.0"
    ):
        self.domain = domain
        self.rate_limit_delay = rate_limit_delay
        self._semaphore = asyncio.Semaphore(1)
        self._client = httpx.AsyncClient(
            headers={"User-Agent": user_agent},
            timeout=30.0,
            follow_redirects=True,
        )

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type(httpx.TimeoutException),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    async def _fetch(self, url: str) -> httpx.Response:
        async with self._semaphore:
            response = await self._client.get(url)
            response.raise_for_status()
            await asyncio.sleep(self.rate_limit_delay)
            return response

    async def fetch_or_skip(self, url: str) -> httpx.Response | None:
        try:
            return await self._fetch(url)
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (403, 404):
                logger.debug(f"Skipping {url}: HTTP {e.response.status_code}")
                return None
            raise

    def _parse_date(self, soup: BeautifulSoup) -> datetime | None:
        # Method 1: <time datetime="...">
        time_tag = soup.find("time", attrs={"datetime": True})
        if time_tag:
            try:
                return datetime.fromisoformat(str(time_tag["datetime"]).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass
        # Method 2: <meta property="article:published_time">
        meta = soup.find("meta", attrs={"property": "article:published_time"})
        if meta and meta.get("content"):
            try:
                return datetime.fromisoformat(str(meta["content"]).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass
        # Method 3: JSON-LD datePublished
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(str(script.string))
                if isinstance(data, dict) and "datePublished" in data:
                    return datetime.fromisoformat(data["datePublished"].replace("Z", "+00:00"))
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
        # Method 4: Polish month name regex
        text = soup.get_text()
        pattern = r"(\d{1,2})\s+(" + "|".join(self.POLISH_MONTHS.keys()) + r")\s+(\d{4})"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            day, month_name, year = match.groups()
            month = self.POLISH_MONTHS.get(month_name.lower())
            if month:
                try:
                    return datetime(int(year), month, int(day), tzinfo=UTC)
                except ValueError:
                    pass
        return None

    # Site adapters implement these; the CLI and dashboard call them.
    async def discover_urls_in_range(self, start_date: date, end_date: date) -> list[str]:
        raise NotImplementedError

    def scrape_in_range(
        self, start_date: date, end_date: date
    ) -> AsyncGenerator[ScrapedArticle, None]:
        raise NotImplementedError

    async def parse_article(self, html: str, url: str) -> ScrapedArticle | None:
        raise NotImplementedError

    async def __aenter__(self) -> "AsyncBaseScraper":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self._client.aclose()
