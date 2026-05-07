import re
from datetime import date

from bs4 import BeautifulSoup
from loguru import logger

from otwarta.scrapers.base import AsyncBaseScraper, ScrapedArticle

ARTICLE_URL_RE = re.compile(r"/\d+/.*\.html$")
CATEGORIES = ["kraj", "swiat", "opinie", "historia", "rozrywka", "ekonomia"]


class DoRzeczyAsyncScraper(AsyncBaseScraper):
    BASE_URL = "https://dorzeczy.pl"

    def __init__(self, rate_limit_delay: float = 2.0):
        super().__init__(domain="dorzeczy.pl", rate_limit_delay=rate_limit_delay)

    async def get_article_urls_for_page(self, page: int, category: str = "kraj") -> list[str]:
        url = f"{self.BASE_URL}/{category}/{page}"
        response = await self.fetch_or_skip(url)
        if response is None:
            return []
        soup = BeautifulSoup(response.text, "html.parser")
        urls = []
        for a in soup.find_all("a", href=True):
            href = str(a["href"])
            if ARTICLE_URL_RE.search(href):
                full_url = href if href.startswith("http") else f"{self.BASE_URL}{href}"
                urls.append(full_url)
        return list(set(urls))

    async def discover_urls_in_range(self, start_date: date, end_date: date) -> list[str]:
        all_urls: list[str] = []
        for category in CATEGORIES:
            logger.info(f"Discovering dorzeczy.pl/{category}...")
            for page in range(1, 2001):
                urls = await self.get_article_urls_for_page(page, category)
                if not urls:
                    logger.info(f"  Stopped at page {page} (empty)")
                    break
                all_urls.extend(urls)
                logger.debug(f"  Page {page}: {len(urls)} URLs")
        return list(set(all_urls))

    async def parse_article(self, html: str, url: str) -> ScrapedArticle | None:
        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find("h1", class_="art-title") or soup.find("h1")
        title = title_tag.get_text(strip=True) if title_tag else None
        author_tag = soup.find(class_="art-author") or soup.find(rel="author")
        author = author_tag.get_text(strip=True) if author_tag else None
        body_tag = soup.find(class_="art-content") or soup.find("article")
        body = body_tag.get_text(separator=" ", strip=True) if body_tag else None
        pub_date = self._parse_date(soup)
        return ScrapedArticle(url=url, site="dorzeczy", title=title, author=author,
                              publication_date=pub_date, body=body)
