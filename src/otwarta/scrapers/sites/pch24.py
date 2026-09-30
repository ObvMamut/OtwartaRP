import re
import warnings
from collections.abc import AsyncGenerator
from datetime import date, datetime
from urllib.parse import urlparse

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from loguru import logger

from otwarta.scrapers.base import AsyncBaseScraper, ScrapedArticle

# Blocks non-article pages: tag/author/category pages, static pages, feeds
URL_BLOCKLIST = re.compile(
    r'/\?s=|/tag/|/autor/|/autor-|/kategori|/page/|/reklama|/regulamin|/kontakt|/o-nas|/feed|/saints'
)

SITEMAP_INDEX_URL = "https://pch24.pl/sitemap.xml"
# Match only articles sitemaps, not tags/pages/saints sitemaps
_ARTICLE_SITEMAP_RE = re.compile(r"articles-sitemap_(\d+)\.xml$")


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

    async def _iter_sitemap_article_urls(
        self, start_date: date, end_date: date
    ) -> AsyncGenerator[tuple[str, date | None], None]:
        """Yield (article_url, lastmod_date) from PCH24's article sitemaps within date range.

        PCH24's search endpoint is JavaScript-rendered and returns the homepage for
        plain HTTP requests. The sitemap at /sitemap.xml lists ~120 articles-sitemap_N.xml
        files, each with 1000 article URLs and <lastmod> dates — no JS needed.

        Processes sitemaps in descending numerical order (newest first) and stops as
        soon as all articles in a sitemap predate start_date.

        NOTE: <lastmod> reflects the last *modification* date, not the original publication
        date. A 2022 article edited in 2025 keeps its sitemap position but has a 2025
        lastmod. We therefore:
          - Skip entire sitemaps where sitemap_min > end_date (all articles created after range)
          - Only filter per-article on lastmod < start_date (safe proxy for "too old")
          - Let scrape_in_range do the final check on the HTML-parsed publication date
        """
        index_response = await self.fetch_or_skip(SITEMAP_INDEX_URL)
        if index_response is None:
            logger.warning("PCH24: could not fetch sitemap index")
            return

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
            soup = BeautifulSoup(index_response.text, "html.parser")
        sitemap_locs = [
            loc.get_text().strip()
            for loc in soup.find_all("loc")
            if _ARTICLE_SITEMAP_RE.search(loc.get_text())
        ]

        def _sitemap_num(url: str) -> int:
            m = _ARTICLE_SITEMAP_RE.search(url)
            return int(m.group(1)) if m else 0

        # Newest sitemaps first so we stop early when we've passed start_date
        sitemap_locs.sort(key=_sitemap_num, reverse=True)
        logger.info(f"PCH24: found {len(sitemap_locs)} article sitemap files")

        for sitemap_url in sitemap_locs:
            sitemap_resp = await self.fetch_or_skip(sitemap_url)
            if sitemap_resp is None:
                continue

            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
                soup2 = BeautifulSoup(sitemap_resp.text, "html.parser")

            # Two-pass: collect all candidates + dates before deciding what to yield.
            # This lets us skip an entire sitemap if it's entirely outside the range.
            candidates: list[tuple[str, date | None]] = []
            sitemap_dates: list[date] = []

            for url_tag in soup2.find_all("url"):
                loc_tag = url_tag.find("loc")
                lastmod_tag = url_tag.find("lastmod")
                if loc_tag is None:
                    continue

                url = loc_tag.get_text().strip()
                if not self._is_article_url(url):
                    continue

                pub_date: date | None = None
                if lastmod_tag:
                    try:
                        pub_date = datetime.fromisoformat(
                            lastmod_tag.get_text().strip().replace("Z", "+00:00")
                        ).date()
                        sitemap_dates.append(pub_date)
                    except (ValueError, TypeError):
                        pass

                candidates.append((url, pub_date))

            if not sitemap_dates:
                continue

            sitemap_max = max(sitemap_dates)
            sitemap_min = min(sitemap_dates)
            logger.info(
                f"  {sitemap_url.split('/')[-1]}: "
                f"{sitemap_min} – {sitemap_max}"
            )

            # All articles in this sitemap predate start_date → nothing older will be in range
            if sitemap_max < start_date:
                logger.info(
                    f"PCH24: sitemap max date {sitemap_max} < {start_date}, "
                    f"stopping sitemap scan"
                )
                return

            # All articles in this sitemap are newer than end_date by their lastmod.
            # Since sitemaps are filled in publication order (not modified order), this
            # means the articles were actually created after end_date — safely skip.
            if sitemap_min > end_date:
                continue

            # Yield candidates, filtering only on lastmod < start_date (safe proxy for
            # "published before range"). Do NOT filter on lastmod > end_date here — an
            # old article edited after end_date would be wrongly excluded. scrape_in_range
            # applies the final date check using the HTML-parsed publication date.
            for url, pub_date in candidates:
                if pub_date is not None and pub_date < start_date:
                    continue
                yield url, pub_date

    async def scrape_in_range(
        self, start_date: date, end_date: date
    ) -> AsyncGenerator[ScrapedArticle, None]:
        """Yield scraped articles in [start_date, end_date] via sitemap discovery.

        PCH24's /?s= search endpoint returns homepage HTML (JS-rendered), so we use
        the sitemap index instead. Each articles-sitemap_N.xml has 1000 article URLs
        with <lastmod> dates for efficient date-range filtering without extra fetches.
        """
        seen_urls: set[str] = set()
        logger.info(f"PCH24: discovering articles via sitemap ({start_date} – {end_date})...")

        async for url, _lastmod in self._iter_sitemap_article_urls(start_date, end_date):
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
        """Discover candidate article URLs in [start_date, end_date] via the sitemaps.

        Candidates are filtered on <lastmod> only; callers must check the parsed
        publication date.
        """
        urls: list[str] = []
        seen: set[str] = set()
        async for url, _lastmod in self._iter_sitemap_article_urls(start_date, end_date):
            if url not in seen:
                seen.add(url)
                urls.append(url)
        return urls

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
                str(author_tag.get("content", ""))
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
