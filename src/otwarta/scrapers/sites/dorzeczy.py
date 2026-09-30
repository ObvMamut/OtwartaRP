import re
from collections.abc import AsyncGenerator
from datetime import date, datetime, timedelta
from urllib.parse import urlsplit, urlunsplit

from bs4 import BeautifulSoup
from loguru import logger

from otwarta.scrapers.base import AsyncBaseScraper, ScrapedArticle

ARTICLE_URL_RE = re.compile(r"/\d+/.*\.html$")
ISSUE_URL_RE = re.compile(r"/archiwum/\d+/dorzeczy-(\d+)-(\d+)\.html$")

# Buffer around the date range when filtering issues by approximate week date.
# Issues publish weekly so +/-14 days ensures we never miss an edge issue.
_ISSUE_DATE_BUFFER = timedelta(days=14)


class DoRzeczyAsyncScraper(AsyncBaseScraper):
    BASE_URL = "https://dorzeczy.pl"
    ARCHIVE_BASE_URL = "https://tygodnik.dorzeczy.pl"

    def __init__(self, rate_limit_delay: float = 2.0):
        super().__init__(domain="dorzeczy.pl", rate_limit_delay=rate_limit_delay)

    @staticmethod
    def _strip_tracking(url: str) -> str:
        parts = urlsplit(url)
        return urlunsplit(parts._replace(query="", fragment=""))

    async def _get_issue_urls_for_year(self, year: int) -> list[tuple[str, date]]:
        """Return (issue_url, approx_date) pairs for all weekly issues in the given year.

        The archive page at tygodnik.dorzeczy.pl/archiwum/rok/{year} lists every
        issue as a link matching /archiwum/{id}/dorzeczy-{week}-{year}.html.
        """
        url = f"{self.ARCHIVE_BASE_URL}/archiwum/rok/{year}"
        response = await self.fetch_or_skip(url)
        if response is None:
            return []
        soup = BeautifulSoup(response.text, "html.parser")
        results: list[tuple[str, date]] = []
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = str(a["href"])
            m = ISSUE_URL_RE.search(href)
            if not m:
                continue
            if href in seen:
                continue
            seen.add(href)
            week_num, issue_year = int(m.group(1)), int(m.group(2))
            full_url = href if href.startswith("http") else f"{self.ARCHIVE_BASE_URL}{href}"
            try:
                approx_date = datetime.strptime(
                    f"{issue_year}-W{week_num:02d}-1", "%Y-W%W-%w"
                ).date()
            except ValueError:
                approx_date = date(issue_year, 1, 1)
            results.append((full_url, approx_date))
        return results

    async def _get_article_urls_for_issue(self, issue_url: str) -> list[str]:
        """Return deduplicated, tracking-stripped article URLs from a weekly issue page."""
        response = await self.fetch_or_skip(issue_url)
        if response is None:
            return []
        soup = BeautifulSoup(response.text, "html.parser")
        urls: list[str] = []
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = str(a["href"])
            # Strip tracking params before regex so ?_gl= etc. don't break the $ anchor
            bare_href = href.split("?")[0].split("#")[0]
            if not ARTICLE_URL_RE.search(bare_href):
                continue
            full_url = href if href.startswith("http") else f"{self.BASE_URL}{href}"
            clean_url = self._strip_tracking(full_url)
            if clean_url not in seen:
                seen.add(clean_url)
                urls.append(clean_url)
        return urls

    async def scrape_in_range(
        self, start_date: date, end_date: date
    ) -> AsyncGenerator[ScrapedArticle, None]:
        """Yield articles in [start_date, end_date] via the magazine archive.

        Two HTTP requests per issue (archive index + issue page) replace thousands
        of category-pagination requests — ~52 issues/year vs. 4000+ pages.
        """
        seen_urls: set[str] = set()
        for year in range(start_date.year, end_date.year + 1):
            logger.info(f"Fetching dorzeczy.pl archive for {year}...")
            issue_entries = await self._get_issue_urls_for_year(year)
            logger.info(f"  Found {len(issue_entries)} issues for {year}")
            for issue_url, approx_date in sorted(issue_entries, key=lambda x: x[1]):
                if approx_date > end_date + _ISSUE_DATE_BUFFER:
                    continue
                if approx_date < start_date - _ISSUE_DATE_BUFFER:
                    continue
                article_urls = await self._get_article_urls_for_issue(issue_url)
                logger.info(f"  Issue {issue_url}: {len(article_urls)} articles")
                for url in article_urls:
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
                    response = await self.fetch_or_skip(url)
                    if response is None:
                        continue
                    article = await self.parse_article(response.text, url)
                    if article is None:
                        continue
                    if article.publication_date:
                        pub_date = article.publication_date.date()
                        if pub_date > end_date or pub_date < start_date:
                            continue
                    yield article

    async def discover_urls_in_range(self, start_date: date, end_date: date) -> list[str]:
        """Discover all article URLs in [start_date, end_date] via the archive index."""
        all_urls: list[str] = []
        seen: set[str] = set()
        for year in range(start_date.year, end_date.year + 1):
            issue_entries = await self._get_issue_urls_for_year(year)
            for issue_url, approx_date in issue_entries:
                if approx_date > end_date + _ISSUE_DATE_BUFFER:
                    continue
                if approx_date < start_date - _ISSUE_DATE_BUFFER:
                    continue
                for url in await self._get_article_urls_for_issue(issue_url):
                    if url not in seen:
                        seen.add(url)
                        all_urls.append(url)
        return all_urls

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
