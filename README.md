# otwarta-pre-post-7oct

Academic research tool measuring antisemitic content in Polish right-wing media
before and after the Hamas attack on Israel on October 7, 2023.

## Research Context

On October 7, 2023, Hamas carried out a large-scale attack on Israel. This project
investigates whether two prominent Polish right-wing news sites — pch24.pl and
dorzeczy.pl — became measurably more antisemitic in the aftermath.

**Research question:** Did antisemitism (0–10 severity, scored by an LLM)
increase significantly in the 12 months following October 7, 2023?

**Methodology:**
1. Scrape all articles from both sites (Oct 7, 2022 → Oct 7, 2024)
2. Score each article 0–10 for antisemitic content using an LLM
   with prompt caching (see AGENTS.md for cost-efficiency details)
3. Compare pre/post distributions: Mann-Whitney U test, Cohen's d, bootstrap CI
4. Visualize monthly rolling average severity with 95% CI band

## Results

*(Results will be added after analysis is complete.)*

## Quick Start

```bash
git clone ...
cd otwarta-pre-post-7oct
uv sync && uv run playwright install chromium
cp .env.example .env          # add LLM_API_KEY
uv run otwarta db init
# Run scrapers in parallel (separate terminals):
uv run otwarta scrape site dorzeczy --start 2022-10-07 --end 2024-10-07
uv run otwarta scrape site pch24 --start 2022-10-07 --end 2024-10-07
# Analyze:
uv run otwarta analyze run --workers 8 --resume
# Visualize:
uv run otwarta visualize all
```

See [INSTRUCTIONS.md](INSTRUCTIONS.md) for full walkthrough and troubleshooting.

## Generic Engine

This project is also a reusable detection engine. Provide a YAML site config and
YAML analysis config, then run the same CLI commands. See INSTRUCTIONS.md.

## Tech Stack

httpx · BeautifulSoup4 · Playwright · SQLAlchemy 2.0 · Alembic · LLM SDK ·
Pydantic v2 · pandas · scipy · plotly · matplotlib · typer · uv

## Ethics & Disclaimer

Conducted for academic research only. Scraping respects robots.txt and crawl delays.
Antisemitism scores are probabilistic AI assessments, not legal determinations.
Identified antisemitic content is not endorsed or amplified — it is quantified.
Data stored locally and not shared publicly without institutional review.

## License

MIT License.

## Sister Projects

- [otwarta-scraper](../otwarta-scraper) — base scraper patterns, keyword lexicon
- [otwarta-article-scraper](../otwarta-article-scraper) — site-specific scrapers (ported into this project)
