from datetime import date
from typing import Optional

import typer
from loguru import logger

app = typer.Typer(name="otwarta", help="Polish news antisemitism research tool")


@app.command()
def status() -> None:
    """Show scraping and analysis progress."""
    from otwarta.storage.database import init_db, get_session
    from otwarta.storage.models import Article, AnalysisResult
    from otwarta.config.settings import Settings

    settings = Settings()
    engine = init_db(str(settings.database_url))
    with get_session(engine) as session:
        total = session.query(Article).count()
        analyzed = session.query(AnalysisResult).count()
        if total:
            typer.echo(f"Articles scraped:  {total}")
            typer.echo(f"Articles analyzed: {analyzed} ({100 * analyzed / total:.1f}%)")
        else:
            typer.echo(
                "No articles yet. Run: otwarta scrape site dorzeczy --start 2022-10-07 --end 2024-10-07"
            )


@app.command("db")
def db_cmd(action: str = typer.Argument(..., help="Action: init")) -> None:
    """Database commands. Use 'init' to create tables."""
    if action == "init":
        from otwarta.storage.database import init_db
        from otwarta.config.settings import Settings

        settings = Settings()
        db_url = str(settings.database_url)
        init_db(db_url)
        typer.echo(f"Database initialized at {db_url}")
    else:
        typer.echo(f"Unknown action: {action}. Available: init", err=True)
        raise typer.Exit(1)


# Sub-apps
scrape_app = typer.Typer(help="Scraping commands")
analyze_app = typer.Typer(help="Analysis commands")
visualize_app = typer.Typer(help="Visualization commands")

app.add_typer(scrape_app, name="scrape")
app.add_typer(analyze_app, name="analyze")
app.add_typer(visualize_app, name="visualize")


# --- Scrape subcommands ---


@scrape_app.command("site")
def scrape_site(
    site_name: str = typer.Argument(..., help="Site to scrape: dorzeczy or pch24"),
    start: str = typer.Option("2022-10-07", help="Start date YYYY-MM-DD"),
    end: str = typer.Option("2024-10-07", help="End date YYYY-MM-DD"),
    max_pages: Optional[int] = typer.Option(None, help="Max pages to scrape (for testing)"),
) -> None:
    """Scrape a specific site for articles in date range."""
    import asyncio
    from otwarta.scrapers.sites import SITE_ADAPTERS

    if site_name not in SITE_ADAPTERS:
        typer.echo(
            f"Unknown site: {site_name}. Available: {list(SITE_ADAPTERS.keys())}", err=True
        )
        raise typer.Exit(1)

    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)

    typer.echo(f"Scraping {site_name} from {start} to {end}...")

    async def run() -> None:
        from otwarta.storage.database import init_db, get_session
        from otwarta.storage.repository import get_or_create_article
        from otwarta.config.settings import Settings

        settings = Settings()
        engine = init_db(str(settings.database_url))
        scraper_cls = SITE_ADAPTERS[site_name]

        async with scraper_cls() as scraper:  # type: ignore[attr-defined]
            urls = await scraper.discover_urls_in_range(start_date, end_date)
            if max_pages:
                urls = urls[: max_pages * 20]
            typer.echo(f"  Discovered {len(urls)} URLs")
            scraped = 0
            for url in urls:
                response = await scraper.fetch_or_skip(url)
                if response is None:
                    continue
                article = await scraper.parse_article(response.text, url)
                if article is None:
                    continue
                if article.publication_date and not (
                    start_date <= article.publication_date.date() <= end_date
                ):
                    continue
                with get_session(engine) as session:
                    get_or_create_article(
                        session,
                        url=article.url,
                        site=article.site,
                        title=article.title,
                        author=article.author,
                        publication_date=article.publication_date,
                        body_clean=article.body,
                    )
                    session.commit()
                scraped += 1
                if scraped % 100 == 0:
                    typer.echo(f"  Scraped {scraped} articles so far...")

        typer.echo(f"Done. Scraped {scraped} articles from {site_name}.")

    asyncio.run(run())


@scrape_app.command("generic")
def scrape_generic(
    config: str = typer.Option(..., help="Path to site YAML config"),
    start: str = typer.Option("2022-10-07", help="Start date YYYY-MM-DD"),
    end: str = typer.Option("2024-10-07", help="End date YYYY-MM-DD"),
    max_pages: Optional[int] = typer.Option(None, help="Max pages to scrape (for testing)"),
) -> None:
    """Scrape using a generic YAML-driven site config."""
    typer.echo(f"Generic scraper with config {config} from {start} to {end}...")
    typer.echo("(Generic YAML-driven scraping not yet implemented — use 'scrape site' instead.)")


# --- Analyze subcommands ---


@analyze_app.command("run")
def analyze_run(
    config: str = typer.Option(
        "config/analysis/antisemitism_oct7.yaml", help="Analysis config YAML"
    ),
    workers: int = typer.Option(4, help="Number of concurrent workers"),
    resume: bool = typer.Option(True, help="Skip already-analyzed articles"),
) -> None:
    """Run analysis on scraped articles."""
    import asyncio
    from otwarta.analysis.generic_detector import GenericDetector
    from otwarta.storage.database import init_db, get_session
    from otwarta.storage.models import Article
    from otwarta.storage.repository import save_analysis
    from otwarta.config.settings import Settings

    settings = Settings()
    engine = init_db(str(settings.database_url))
    detector = GenericDetector(
        config_path=config, api_key=settings.llm_api_key.get_secret_value()
    )

    async def run() -> None:
        with get_session(engine) as session:
            query = session.query(Article).filter(Article.body_clean.isnot(None))
            if resume:
                query = query.filter(Article.analysis_completed_at.is_(None))
            articles = query.all()

        typer.echo(f"Analyzing {len(articles)} articles with {workers} workers...")

        sem = asyncio.Semaphore(workers)

        async def analyze_one(article: Article) -> None:
            async with sem:
                result = await detector.analyze(
                    title=article.title or "",
                    body=article.body_clean or "",
                )
                with get_session(engine) as session:
                    save_analysis(
                        session,
                        article_id=article.id,
                        config=detector.config["name"],
                        model_id=detector.client.model,
                        severity_score=result.get("severity_score", 0.0),
                        result_json=result,
                        prompt_tokens=result.get("_tokens", {}).get("input", 0),
                        completion_tokens=result.get("_tokens", {}).get("output", 0),
                        cache_read_tokens=result.get("_tokens", {}).get("cache_read", 0),
                    )

        await asyncio.gather(*[analyze_one(a) for a in articles])
        typer.echo("Analysis complete.")

    asyncio.run(run())


# --- Visualize subcommands ---


@visualize_app.command("all")
def visualize_all(
    output: str = typer.Option("data/processed", help="Output directory"),
    cutoff: str = typer.Option("2023-10-07", help="Cutoff date for pre/post split"),
) -> None:
    """Generate all charts and report."""
    from datetime import datetime

    import pandas as pd

    from otwarta.storage.database import init_db, get_session
    from otwarta.storage.models import Article, AnalysisResult
    from otwarta.visualization.reports import generate_report
    from otwarta.config.settings import Settings

    settings = Settings()
    engine = init_db(str(settings.database_url))
    cutoff_dt = datetime.fromisoformat(cutoff)

    with get_session(engine) as session:
        rows = (
            session.query(
                Article.url,
                Article.site,
                Article.publication_date,
                AnalysisResult.severity_score,
            )
            .join(AnalysisResult)
            .filter(Article.publication_date.isnot(None))
            .all()
        )

    df = pd.DataFrame(rows, columns=["url", "site", "publication_date", "severity_score"])
    if df.empty:
        typer.echo("No analyzed articles found. Run 'otwarta analyze run' first.")
        return

    report_path = generate_report(df, output_dir=output, cutoff=cutoff_dt)
    typer.echo(f"Report generated: {report_path}")


@visualize_app.command("time-series")
def visualize_time_series(
    site: Optional[str] = typer.Option(None, help="Filter by site name"),
    output: str = typer.Option("data/processed", help="Output directory"),
) -> None:
    """Generate time-series chart of severity scores."""
    typer.echo("Use 'otwarta visualize all' to generate all charts including time-series.")


@visualize_app.command("comparison")
def visualize_comparison(
    cutoff: str = typer.Option("2023-10-07", help="Cutoff date for pre/post split"),
    output: str = typer.Option("data/processed", help="Output directory"),
) -> None:
    """Generate pre/post comparison chart."""
    typer.echo("Use 'otwarta visualize all' to generate all charts including comparison.")


@visualize_app.command("stats")
def visualize_stats() -> None:
    """Print statistical summary (Mann-Whitney U, Cohen's d)."""
    typer.echo("Use 'otwarta visualize all' to generate full statistical report.")
