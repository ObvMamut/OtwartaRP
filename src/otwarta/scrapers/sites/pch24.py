import re
from datetime import date
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from loguru import logger

from otwarta.scrapers.base import AsyncBaseScraper, ScrapedArticle

SEARCH_KEYWORDS = [
    "żydzi", "izrael", "holokaust", "antysemityzm", "Hamas", "Gaza", "Palestyna",
    "Soros", "globaliści", "żydokomuna",
]

URL_BLOCKLIST = re.compile(
    r'/\?s=|/tag/|/autor/|/autor-|/kategori|/page/|/reklama|/regulamin|/kontakt|/o-nas|/feed'
)


class PCH24AsyncScraper(AsyncBaseScraper):
    BASE_URL = "https://pch24.pl"

    def __init__(self, rate_limit_delay: float = 1.0):
        super().__init__(domain="pch24.pl", rate_limit_delay=rate_limit_delay)

    def _is_article_url(self, url: str) -> bool:
        if not url.startswith(self.BASE_URL):
            return False
        if URL_BLOCKLIST.search(url):
            return False
        parsed = urlparse(url)
        segments = [s for s in parsed.path.split("/") if s]
        return len(segments) >= 1 and not parsed.query

    async def get_article_urls_for_keyword_page(self, keyword: str, page: int) -> list[str]:
        url = f"{self.BASE_URL}/?s={keyword}&paged={page}"
        response = await self.fetch_or_skip(url)
        if response is None:
            return []
        soup = BeautifulSoup(response.text, "html.parser")
        urls = []
        for a in soup.find_all("a", href=True):
            full_url = urljoin(self.BASE_URL, str(a["href"]))
            if self._is_article_url(full_url):
                urls.append(full_url)
        return list(set(urls))

    async def discover_urls_in_range(self, start_date: date, end_date: date) -> list[str]:
        all_urls: list[str] = []
        for keyword in SEARCH_KEYWORDS:
            logger.info(f"Searching pch24.pl for: {keyword}")
            for page in range(1, 101):
                urls = await self.get_article_urls_for_keyword_page(keyword, page)
                if not urls:
                    logger.info(f"  Stopped at page {page} (empty) for keyword '{keyword}'")
                    break
                all_urls.extend(urls)
                logger.debug(f"  Page {page}: {len(urls)} URLs")
        return list(set(all_urls))

    async def parse_article(self, html: str, url: str) -> ScrapedArticle | None:
        soup = BeautifulSoup(html, "html.parser")
        title_tag = (
            soup.find("h1", class_=re.compile(r"entry-title|article-title", re.I)) or
            soup.find("h1")
        )
        title = title_tag.get_text(strip=True) if title_tag else None
        author_tag = (
            soup.find(class_=re.compile(r"author|autor|byline|reporter|entry-author", re.I)) or
            soup.find("span", itemprop="author") or
            soup.find("a", rel="author") or
            soup.find("meta", attrs={"name": "author"}) or
            soup.find("meta", property="article:author")
        )
        if author_tag:
            author = (
                author_tag.get("content", "")
                if author_tag.name == "meta"
                else author_tag.get_text(strip=True)
            )
        else:
            author = None
        body_pattern = re.compile(r"entry[_-]content|post[_-]content|article[_-]body", re.I)
        body_tag = (
            soup.find(class_=body_pattern) or
            soup.find("article") or
            soup.find(class_=re.compile(r"content|article|tekst", re.I))
        )
        body = body_tag.get_text(separator=" ", strip=True) if body_tag else None
        pub_date = self._parse_date(soup)
        return ScrapedArticle(url=url, site="pch24", title=title, author=author,
                              publication_date=pub_date, body=body)
