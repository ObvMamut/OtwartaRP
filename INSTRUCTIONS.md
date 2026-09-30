# How to Use This System

## Prerequisites

- Python ≥ 3.12 and [uv](https://docs.astral.sh/uv/)
- [Ollama](https://ollama.com/) running locally, with the scoring models pulled:
  ```bash
  ollama pull llama3.1        # primary scorer
  ollama pull mistral-nemo    # secondary "confirmation" scorer
  ```
- A few GB of disk space. A full two-year scrape takes many hours because of crawl delays
  (dorzeczy.pl requires 2 s between requests).

## Setup

```bash
uv sync
uv run playwright install chromium
cp .env.example .env     # optional — every setting has a default
uv run otwarta db init
```

### Settings (`.env` or environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./data/raw/otwarta.db` | SQLite database (WAL mode) |
| `LOG_LEVEL` | `INFO` | loguru level |
| `RATE_LIMIT_DORZECZY` | `2.0` | seconds between requests (robots.txt) |
| `RATE_LIMIT_PCH24` | `1.0` | seconds between requests |
| `MAX_ANALYSIS_WORKERS` | `4` | concurrent Ollama requests |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server |
| `PRIMARY_MODEL` | `llama3.1` | model that scores every article |
| `SECONDARY_MODEL` | `mistral-nemo` | re-scores articles the primary scores below 2; the higher score is kept |

---

## End-to-end: the Oct 7 study

```bash
# 1. Initialize DB
uv run otwarta db init

# 2. Scrape (separate terminals, run in parallel)
uv run otwarta scrape site dorzeczy --start 2022-10-07 --end 2024-10-07
uv run otwarta scrape site pch24    --start 2022-10-07 --end 2024-10-07

# 3. Monitor
uv run otwarta status

# 4. Analyze (can start while scraping is running; resumes by default)
uv run otwarta analyze run --config config/analysis/antisemitism_oct7.yaml --workers 4

# 5. Visualize
uv run otwarta visualize all --output data/processed/
uv run otwarta visualize stats
uv run python scripts/export_charts.py   # static PNGs → data/processed/charts/
uv run python scripts/export_stats.py    # aggregated CSVs → data/processed/

# Or drive everything from the browser:
uv run otwarta dashboard
```

### How each site is discovered

- **dorzeczy.pl**: walks the weekly magazine archive at `tygodnik.dorzeczy.pl/archiwum`
  (one page per issue) and collects the article links of every issue in the date range.
- **pch24.pl**: the WordPress search is JavaScript-rendered, so discovery walks the
  `articles-sitemap_N.xml` files listed in `/sitemap.xml`, newest first. Sitemap `<lastmod>`
  is a modification date, so the final date filter uses the publication date parsed from
  the article HTML.

---

## Adding a new site

Write a Python adapter in `src/otwarta/scrapers/sites/my_site.py` that subclasses
`AsyncBaseScraper` and implements the three site methods:

```python
from collections.abc import AsyncGenerator
from datetime import date

from otwarta.scrapers.base import AsyncBaseScraper, ScrapedArticle


class MySiteAsyncScraper(AsyncBaseScraper):
    def __init__(self, rate_limit_delay: float = 1.5):
        super().__init__(domain="my-site.pl", rate_limit_delay=rate_limit_delay)

    async def discover_urls_in_range(self, start_date: date, end_date: date) -> list[str]: ...

    async def scrape_in_range(
        self, start_date: date, end_date: date
    ) -> AsyncGenerator[ScrapedArticle, None]: ...

    async def parse_article(self, html: str, url: str) -> ScrapedArticle | None: ...
```

`AsyncBaseScraper` provides robots.txt handling, per-domain rate limiting, retries
(`fetch_or_skip`) and a date-parsing cascade (time tag → Polish month regex → meta → JSON-LD).
Register the class in `src/otwarta/scrapers/sites/__init__.py`:

```python
SITE_ADAPTERS = {
    "dorzeczy": DoRzeczyAsyncScraper,
    "pch24": PCH24AsyncScraper,
    "my_site": MySiteAsyncScraper,
}
```

> The YAML site configs in `config/sites/` document each site's structure, but
> `otwarta scrape generic` (fully YAML-driven scraping) is **not implemented yet**.

---

## Adding a new analysis

The analysis side *is* config-driven. Copy `config/analysis/generic_template.yaml`, describe
what to detect, the 0–10 severity rubric, few-shot examples and a keyword pre-filter, then:

```bash
uv run otwarta analyze run --config config/analysis/my_analysis.yaml
```

Results are stored per `(article, analysis_config)`, so several analyses can coexist in the
same database.

---

## Interpreting scores

| Score | Label    | Meaning |
|-------|----------|---------|
| 0     | NONE     | No antisemitic content |
| 1–2   | MINIMAL  | Neutral/mildly biased mentions |
| 3–4   | LOW      | Antisemitic tropes used rhetorically (e.g. "globalists") |
| 5–6   | MEDIUM   | Explicit conspiracy framing |
| 7–8   | HIGH     | Direct accusations, dehumanizing language |
| 9–10  | CRITICAL | Explicit slurs, calls for discrimination |

Articles whose body contains none of the configured keywords are stored with score 0 without
calling the model (in the Oct 7 study this was 77 % of the corpus).

## Statistical output

- **Mann-Whitney U** (two-sided): p < 0.05 means the pre/post distributions differ.
- **Cohen's d**: effect size (≈0.2 small, 0.5 medium, 0.8 large).
- **95 % bootstrap CI** on the post-period mean.

## Known limitations

- **Scores are LLM judgments.** An 8B local model can vary by ±1 point on the same article
  and has not been validated against human coders.
- **dorzeczy.pl paywall:** truncated article bodies may score lower.
- **Missing dates:** articles with a NULL `publication_date` are excluded from time series.
