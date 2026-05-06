# INSTRUCTIONS.md — How to Use This System

## Prerequisites

- Python 3.14 (system: `/usr/bin/python3`)
- uv (`~/.local/bin/uv`)
- LLM API key (required for analysis phase only)
- ~5GB disk space
- ~24–48h runtime for full scrape + analysis of 2 years

## Setup

```bash
cd /home/mamut/all/programming/otwarta-pre-post-7oct
uv sync
uv run playwright install chromium
cp .env.example .env
# Edit .env: add LLM_API_KEY=...
uv run otwarta db init
```

---

## End-to-End: Oct 7 Research

**Estimated timeline:** 10min setup · 24–48h scraping · 4–8h analysis · 5min visualization

```bash
# 1. Initialize DB
uv run otwarta db init

# 2. Scrape (separate terminals, run in parallel)
# Terminal 1:
uv run otwarta scrape site dorzeczy --start 2022-10-07 --end 2024-10-07

# Terminal 2:
uv run otwarta scrape site pch24 --start 2022-10-07 --end 2024-10-07

# 3. Monitor
uv run otwarta status

# 4. Analyze (can start while scraping is running)
uv run otwarta analyze run \
    --config config/analysis/antisemitism_oct7.yaml \
    --workers 8 \
    --resume

# 5. Visualize
uv run otwarta visualize all --output data/processed/

# 6. Open report
xdg-open data/processed/report.html
```

---

## Adding a New Site

### Step 1: Create YAML config at `config/sites/my_site.yaml`

```yaml
name: my_site
base_url: https://my-site.pl
encoding: utf-8

discovery:
  strategy: pagination               # pagination | sitemap | search
  pagination:
    url_template: "https://my-site.pl/news/{page}"
    start_page: 1
    max_pages: 500
    articles_per_page: 15
    empty_page_selector: ".no-results"

article_url_pattern: "/\\d{4}/\\d{2}/\\d{2}/"   # regex to identify article URLs

rate_limit:
  delay_seconds: 1.5
  respect_robots_txt: true
  user_agent: "OtwartaResearch/1.0"

selectors:
  title: "h1.article-title, h1"
  author: ".author-name, [rel='author'], meta[name='author']"
  date: "time[datetime], meta[property='article:published_time']"
  body: ".article-content, .entry-content, article"
  body_remove: ["script", "style", ".advertisement"]

date:
  methods:
    - type: html_tag
      selector: "time"
      attribute: datetime
    - type: meta_tag
      property: "article:published_time"
    - type: json_ld
    - type: regex
      pattern: '(\d{1,2}\s+(?:stycznia|lutego|marca|kwietnia|maja|czerwca|lipca|sierpnia|września|października|listopada|grudnia)\s+\d{4})'
  timezone: Europe/Warsaw

playwright:
  enabled: false
  wait_for_selector: ".article-content"
  headless: true
```

### Step 2: (Optional) Python adapter for non-standard sites

Create `src/otwarta/scrapers/sites/my_site.py`:
```python
from otwarta.scrapers.base import AsyncBaseScraper
from otwarta.scrapers.engine import ScrapedArticle

class MySiteAdapter(AsyncBaseScraper):
    async def parse_article(self, html: str, url: str) -> ScrapedArticle | None:
        ...  # custom parsing

    async def get_article_urls_for_page(self, page: int) -> list[str]:
        ...  # custom pagination
```

Register in `src/otwarta/scrapers/sites/__init__.py`:
```python
SITE_ADAPTERS = {
    "dorzeczy": DoRzeczyAsyncScraper,
    "pch24": PCH24AsyncScraper,
    "my_site": MySiteAdapter,  # add here
}
```

---

## Adding a New Analysis Config

The following example shows how to configure the engine for a **different analysis** (anti-Ukrainian sentiment). For the antisemitism research, use the ready-made `config/analysis/antisemitism_oct7.yaml`.

Create `config/analysis/my_analysis.yaml`:
```yaml
name: my_analysis
model: llm-model
max_tokens: 1024

what_to_detect: |
  Detect and score anti-Ukrainian sentiment in Polish news articles.

severity_criteria:
  0: "No anti-Ukrainian sentiment detected"
  1-2: "Mildly critical of Ukrainian policy, no dehumanization"
  3-4: "Uses loaded historical references rhetorically"
  5-6: "Dehumanizing metaphors, blames civilian Ukrainians"
  7-8: "Explicit calls to restrict Ukrainian refugees"
  9-10: "Explicit dehumanization or calls for expulsion"

few_shot_examples:
  - article: "Ukraińcy muszą wrócić do domu i walczyć."
    score: 4
    explanation: "Frames war service as obligation but not dehumanizing"

output_format:
  severity_score: float
  severity_label: string
  detected_patterns: list[str]
  evidence_sentences: list[str]
  explanation: string
  is_relevant: bool

filter:
  keyword_filter:
    enabled: true
    keywords: ["ukrainiec", "ukraińc", "wołyń", "banderowiec"]
    min_matches: 1
```

---

## Interpreting Scores

| Score | Label    | Meaning |
|-------|----------|---------|
| 0     | NONE     | No antisemitic content |
| 1–2   | MINIMAL  | Neutral/mildly biased mentions |
| 3–4   | LOW      | Antisemitic tropes used rhetorically (e.g. "globalists") |
| 5–6   | MEDIUM   | Explicit conspiracy framing |
| 7–8   | HIGH     | Direct accusations, dehumanizing language |
| 9–10  | CRITICAL | Explicit slurs, calls for discrimination |

## Statistical Output

- **Mann-Whitney U test**: p < 0.05 = significant shift in distributions pre/post Oct 7
- **Cohen's d**: effect size (small <0.2, medium 0.5, large >0.8)
- **95% Bootstrap CI**: confidence interval on mean score difference
- **Monthly rolling average**: 30-day rolling mean severity with 95% CI band

## Known Limitations

- **dorzeczy.pl paywall**: truncated articles may score lower (filter by `body_clean` length)
- **pch24.pl category 403**: discovery uses search + sitemap; some articles may be missed
- **Date parsing failures**: articles with NULL `publication_date` excluded from time-series
- **LLM scoring variance**: same article may vary ±1 point; system prompt includes "when uncertain, score lower"
- **Memory for 100k articles**: use `yield_per()` for bulk reads to avoid OOM

## Validate Scores Before Trusting at Scale

```bash
# Export 50 random articles for manual review
uv run otwarta analyze export --sample 50 --output data/validation_sample.csv

# Manually score each (add a manual_score column to the CSV)
# Then compare:
uv run otwarta analyze validate --sample data/validation_sample.csv

# Re-analyze sample with adjusted few-shots:
uv run otwarta analyze run --force --ids-from data/validation_sample.csv
```
