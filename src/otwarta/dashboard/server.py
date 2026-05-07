import asyncio
import threading
from collections import deque
from collections.abc import AsyncGenerator
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from loguru import logger
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

_log_queue: Queue[str] = Queue()
_log_history: deque[str] = deque(maxlen=500)
_task: dict[str, Any] = {
    "name": "",
    "status": "idle",
    "started_at": None,
    "message": "",
}
_task_lock = threading.Lock()
_sink_registered = False


def _add_loguru_sink() -> None:
    global _sink_registered
    if not _sink_registered:
        logger.add(_loguru_sink, format="{time:HH:mm:ss} | {level} | {message}")
        _sink_registered = True


def _loguru_sink(message: Any) -> None:
    line = str(message).strip()
    _log_history.append(line)
    _log_queue.put_nowait(line)


def _start_task(name: str, fn: Any, *args: Any) -> None:
    with _task_lock:
        if _task["status"] == "running":
            raise HTTPException(status_code=409, detail="A task is already running")
        _task.update({
            "name": name,
            "status": "running",
            "started_at": datetime.now().isoformat(),
            "message": "",
        })

    def run() -> None:
        try:
            fn(*args)
            with _task_lock:
                _task["status"] = "done"
        except Exception as exc:
            with _task_lock:
                _task.update({"status": "error", "message": str(exc)})
            logger.error(f"Task {name} failed: {exc}")

    threading.Thread(target=run, daemon=True).start()


class ScrapeRequest(BaseModel):
    site: str
    start: str = "2022-10-07"
    end: str = "2024-10-07"


class AnalyzeRequest(BaseModel):
    workers: int = 8
    resume: bool = True


class VisualizeRequest(BaseModel):
    output: str = "data/processed"
    cutoff: str = "2023-10-07"


def create_app(db_url: str | None = None, api_key: str | None = None) -> FastAPI:
    from otwarta.storage.database import get_session, init_db
    from otwarta.storage.models import AnalysisResult, Article

    if db_url is None or api_key is None:
        from otwarta.config.settings import Settings
        settings = Settings()
        db_url = db_url or str(settings.database_url)
        api_key = api_key or settings.gemini_api_key.get_secret_value()

    _add_loguru_sink()
    engine = init_db(db_url)
    static_dir = Path(__file__).parent / "static"

    app = FastAPI(title="otwarta dashboard")

    @app.get("/")
    async def index() -> HTMLResponse:
        return HTMLResponse((static_dir / "index.html").read_text(encoding="utf-8"))

    @app.get("/api/status")
    async def status() -> dict[str, Any]:
        with get_session(engine) as session:
            total = session.query(Article).count()
            analyzed = session.query(AnalysisResult).count()
        pct = round(100 * analyzed / total, 1) if total else 0.0
        return {"articles_scraped": total, "articles_analyzed": analyzed, "percent": pct}

    @app.post("/api/db/init")
    async def db_init() -> dict[str, Any]:
        init_db(db_url)
        logger.info("Database initialized")
        return {"ok": True}

    @app.get("/api/task")
    async def task_state() -> dict[str, Any]:
        return dict(_task)

    @app.post("/api/scrape")
    async def scrape(req: ScrapeRequest) -> dict[str, Any]:
        from otwarta.scrapers.sites import SITE_ADAPTERS

        if req.site not in SITE_ADAPTERS:
            raise HTTPException(status_code=400, detail=f"Unknown site: {req.site}. Use: {list(SITE_ADAPTERS.keys())}")

        def run_scrape() -> None:
            from datetime import date as date_cls
            from otwarta.storage.repository import get_or_create_article

            start_date = date_cls.fromisoformat(req.start)
            end_date = date_cls.fromisoformat(req.end)
            scraper_cls = SITE_ADAPTERS[req.site]

            async def _inner() -> None:
                scrape_engine = init_db(db_url)
                async with scraper_cls() as scraper:  # type: ignore[attr-defined]
                    urls = await scraper.discover_urls_in_range(start_date, end_date)
                    logger.info(f"Discovered {len(urls)} URLs for {req.site}")
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
                        with get_session(scrape_engine) as session:
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
                            logger.info(f"Scraped {scraped} articles from {req.site}")
                    logger.info(f"Done. Scraped {scraped} articles from {req.site}.")

            asyncio.run(_inner())

        _start_task(f"scrape:{req.site}", run_scrape)
        return {"ok": True, "task": f"scrape:{req.site}"}

    @app.post("/api/analyze")
    async def analyze(req: AnalyzeRequest) -> dict[str, Any]:
        def run_analyze() -> None:
            from otwarta.analysis.generic_detector import GenericDetector
            from otwarta.storage.models import Article as ArticleModel
            from otwarta.storage.repository import save_analysis

            detector = GenericDetector(
                config_path="config/analysis/antisemitism_oct7.yaml",
                api_key=api_key,
            )

            async def _inner() -> None:
                analyze_engine = init_db(db_url)
                with get_session(analyze_engine) as session:
                    query = session.query(ArticleModel).filter(
                        ArticleModel.body_clean.isnot(None)
                    )
                    if req.resume:
                        query = query.filter(ArticleModel.analysis_completed_at.is_(None))
                    articles = query.all()

                logger.info(f"Analyzing {len(articles)} articles with {req.workers} workers")
                sem = asyncio.Semaphore(req.workers)

                async def analyze_one(article: ArticleModel) -> None:
                    async with sem:
                        result = await detector.analyze(
                            title=article.title or "",
                            body=article.body_clean or "",
                        )
                        with get_session(analyze_engine) as session:
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
                logger.info("Analysis complete.")

            asyncio.run(_inner())

        _start_task("analyze", run_analyze)
        return {"ok": True, "task": "analyze"}

    @app.post("/api/visualize")
    async def visualize(req: VisualizeRequest) -> dict[str, Any]:
        def run_visualize() -> None:
            import pandas as pd
            from datetime import datetime as dt
            from otwarta.storage.models import AnalysisResult as AR, Article as Art
            from otwarta.visualization.reports import generate_report

            viz_engine = init_db(db_url)
            cutoff_dt = dt.fromisoformat(req.cutoff)
            with get_session(viz_engine) as session:
                rows = (
                    session.query(Art.url, Art.site, Art.publication_date, AR.severity_score)
                    .join(AR)
                    .filter(Art.publication_date.isnot(None))
                    .all()
                )
            df = pd.DataFrame(rows, columns=["url", "site", "publication_date", "severity_score"])
            if df.empty:
                logger.warning("No analyzed articles found. Run analysis first.")
                return
            report_path = generate_report(df, output_dir=req.output, cutoff=cutoff_dt)
            logger.info(f"Report generated: {report_path}")

        _start_task("visualize", run_visualize)
        return {"ok": True, "task": "visualize"}

    @app.get("/api/logs")
    async def logs(request: Request) -> EventSourceResponse:
        async def generate() -> AsyncGenerator[dict[str, str], None]:
            for line in list(_log_history):
                yield {"data": line}
            while True:
                if await request.is_disconnected():
                    break
                try:
                    line = _log_queue.get_nowait()
                    yield {"data": line}
                except Empty:
                    await asyncio.sleep(0.1)

        return EventSourceResponse(generate())

    return app
