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
_stop_event = threading.Event()
_keyword_matched_total: int | None = None

KEYWORD_GROUPS: dict[str, list[str]] = {
    "Jewish identity": [
        "żyd", "żydzi", "żydowsk", "żydokomuna", "judeobolszew",
        "antysemit", "semick", "holokaust", "szoah",
    ],
    "Israel / Middle East": [
        "izrael", "izraelski", "izraelczyk", "palestyn", "zachodni brzeg",
        "hamas", "hezbollah", "fatah", "netanjahu", "netanyahu", "likud",
        "mossad", "idf", "tsahal", "intifada", "al-aksa", "kibuc", "dżihad", "gaza",
    ],
    "Conspiracy": [
        "soros", "rothschild", "rockefeller", "globalist", "finansjera",
        "kosmopolit", "bankster", "masoneri", "wielki reset", "schwab",
        "davos", "nowy porządek", "syjonist", "syjonizm",
    ],
    "Historical": [
        "pogrom", "getto", "majdanek", "auschwitz", "treblinka", "rewizjonizm",
    ],
    "Polish-Jewish relations": [
        "polin", "antypolonizm", "restytucj", "ustawa 447",
    ],
    "Religious": [
        "talmud", "synagog", "rabin", "kabał",
    ],
}

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


def _start_analyze_task(fn: Any, *args: Any) -> None:
    _stop_event.clear()
    _start_task("analyze", fn, *args)


class ScrapeRequest(BaseModel):
    site: str
    start: str = "2022-10-07"
    end: str = "2024-10-07"


class AnalyzeRequest(BaseModel):
    workers: int = 2
    resume: bool = True


class VisualizeRequest(BaseModel):
    output: str = "data/processed"
    cutoff: str = "2023-10-07"


def create_app(db_url: str | None = None) -> FastAPI:
    from otwarta.config.settings import Settings
    from otwarta.storage.database import get_session, init_db
    from otwarta.storage.models import AnalysisResult, Article
    settings = Settings()
    db_url = db_url or str(settings.database_url)

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

    @app.get("/api/analyze-progress")
    async def analyze_progress() -> dict[str, Any]:
        global _keyword_matched_total
        from sqlalchemy import func, or_
        from sqlalchemy import text as sa_text

        with get_session(engine) as session:
            if _keyword_matched_total is None:
                all_keywords = [
                    "żyd", "żydzi", "żydowsk", "żydokomuna", "judeobolszew",
                    "antysemit", "semick", "holokaust", "szoah",
                    "izrael", "izraelski", "izraelczyk", "palestyn", "zachodni brzeg",
                    "hamas", "hezbollah", "fatah", "netanjahu", "netanyahu", "likud",
                    "mossad", "idf", "tsahal", "intifada", "al-aksa", "kibuc", "dżihad", "gaza",
                    "soros", "rothschild", "rockefeller", "globalist", "finansjera",
                    "kosmopolit", "bankster", "masoneri", "wielki reset", "schwab",
                    "davos", "nowy porządek", "syjonist", "syjonizm",
                    "pogrom", "getto", "majdanek", "auschwitz", "treblinka", "rewizjonizm",
                    "polin", "antypolonizm", "restytucj", "ustawa 447",
                    "talmud", "synagog", "rabin", "kabał",
                    "ukraina", "ukraiński", "ukraińcy", "uchodźca", "uchodźcy", "uchodźstwo",
                    "migrant", "migracja", "imigracja", "imigrant", "obcokrajowiec", "cudzoziemiec",
                    "muzułman", "muzułmanie", "muzułmański", "islamist", "islamizacja",
                    "romowie", "cyganie", "cygan",
                    "lgbt", "gender", "transpłciow", "homoseksual",
                ]
                filters = [Article.body_clean.ilike(f"%{kw}%") for kw in all_keywords]
                _keyword_matched_total = (
                    session.query(func.count(Article.id))
                    .filter(or_(*filters))
                    .scalar()
                ) or 0

            ai_analyzed = session.execute(
                sa_text(
                    "SELECT COUNT(*) FROM analysis_results "
                    "WHERE result_json NOT LIKE '%Filtered: no relevant keywords%'"
                )
            ).scalar() or 0

        total = _keyword_matched_total
        pct = round(100 * ai_analyzed / total, 1) if total else 0.0
        return {
            "keyword_matched": total,
            "ai_analyzed": ai_analyzed,
            "pct": pct,
        }

    @app.post("/api/analyze/stop")
    async def analyze_stop() -> dict[str, Any]:
        _stop_event.set()
        logger.info("Stop requested — analysis will halt after current batch.")
        return {"ok": True}

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
            raise HTTPException(
                status_code=400,
                detail=f"Unknown site: {req.site}. Use: {list(SITE_ADAPTERS.keys())}",
            )

        def run_scrape() -> None:
            from datetime import date as date_cls

            from otwarta.storage.repository import get_or_create_article

            start_date = date_cls.fromisoformat(req.start)
            end_date = date_cls.fromisoformat(req.end)
            scraper_cls = SITE_ADAPTERS[req.site]

            async def _inner() -> None:
                scrape_engine = init_db(db_url)
                async with scraper_cls() as scraper:
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
            from otwarta.analysis.ollama_client import OllamaAnalysisClient
            from otwarta.storage.models import Article as ArticleModel
            from otwarta.storage.repository import save_analysis

            client = OllamaAnalysisClient(
                base_url=settings.ollama_base_url,
                primary_model=settings.primary_model,
                secondary_model=settings.secondary_model,
                max_concurrent=req.workers,
            )
            detector = GenericDetector(
                config_path="config/analysis/antisemitism_oct7.yaml",
                client=client,
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

                keyword_count = len(detector._keywords)
                logger.info(
                    f"Analyzing {len(articles)} articles "
                    f"({keyword_count} keywords) with {req.workers} workers"
                )
                sem = asyncio.Semaphore(req.workers)

                async def analyze_one(article: ArticleModel) -> None:
                    async with sem:
                        result = await detector.analyze(
                            title=article.title or "",
                            body=article.body_clean or "",
                        )
                        secondary = result.get("_secondary_model") or {}
                        with get_session(analyze_engine) as session:
                            save_analysis(
                                session,
                                article_id=article.id,
                                config=detector.config["name"],
                                model_id=settings.primary_model,
                                severity_score=result.get("severity_score", 0.0),
                                result_json=result,
                                prompt_tokens=result.get("_tokens", {}).get("input", 0),
                                completion_tokens=result.get("_tokens", {}).get("output", 0),
                                cache_read_tokens=result.get("_tokens", {}).get("cache_read", 0),
                                hateful_score=result.get("hateful_score"),
                                secondary_model_id=secondary.get("model"),
                                secondary_model_score=secondary.get("score"),
                            )

                batch_size = req.workers
                for i in range(0, len(articles), batch_size):
                    if _stop_event.is_set():
                        logger.info("Analysis stopped by user request.")
                        break
                    batch = articles[i:i + batch_size]
                    await asyncio.gather(*[analyze_one(a) for a in batch])
                    done = min(i + batch_size, len(articles))
                    logger.info(f"Progress: {done}/{len(articles)} articles processed")
                else:
                    logger.info("Analysis complete.")

            asyncio.run(_inner())

        _start_analyze_task(run_analyze)
        return {"ok": True, "task": "analyze"}

    @app.post("/api/visualize")
    async def visualize(req: VisualizeRequest) -> dict[str, Any]:
        def run_visualize() -> None:
            from datetime import datetime as dt

            import pandas as pd

            from otwarta.storage.models import AnalysisResult as AR
            from otwarta.storage.models import Article as Art
            from otwarta.visualization.reports import generate_report

            viz_engine = init_db(db_url)
            cutoff_dt = dt.fromisoformat(req.cutoff)
            with get_session(viz_engine) as session:
                rows = (
                    session.query(
                        Art.url, Art.site, Art.title, Art.publication_date,
                        AR.severity_score, AR.hateful_score, AR.result_json,
                    )
                    .join(AR)
                    .filter(Art.publication_date.isnot(None))
                    .all()
                )
            df = pd.DataFrame(
                rows,
                columns=[
                    "url", "site", "title", "publication_date",
                    "severity_score", "hateful_score", "result_json",
                ],
            )
            if df.empty:
                logger.warning("No analyzed articles found. Run analysis first.")
                return
            report_path = generate_report(df, output_dir=req.output, cutoff=cutoff_dt)
            logger.info(f"Report generated: {report_path}")

        _start_task("visualize", run_visualize)
        return {"ok": True, "task": "visualize"}

    @app.get("/api/keyword-filter")
    async def keyword_filter(keywords: str = "") -> dict[str, Any]:
        """Return per-keyword hit counts and total distinct matching articles.

        Pass ?keywords=word1,word2,... to override the default list.
        All matches are case-insensitive against body_clean.
        """
        from sqlalchemy import func, or_

        default_keywords = [
            # Jewish identity / direct antisemitic terms
            "żyd", "żydzi", "żydowsk", "żydokomuna", "judeobolszew",
            "antysemit", "semick", "holokaust", "szoah",
            # Israel / Middle East conflict
            "izrael", "izraelski", "izraelczyk",
            "palestyn", "zachodni brzeg",
            "hamas", "hezbollah", "fatah",
            "netanjahu", "netanyahu", "likud",
            "mossad", "idf", "tsahal",
            "intifada", "al-aksa", "kibuc", "dżihad", "gaza",
            # Conspiracy / coded language
            "soros", "rothschild", "rockefeller",
            "globalist", "finansjera", "kosmopolit",
            "bankster", "masoneri",
            "wielki reset", "schwab", "davos", "nowy porządek",
            "syjonist", "syjonizm",
            # Historical
            "pogrom", "getto", "majdanek", "auschwitz", "treblinka", "rewizjonizm",
            # Polish-Jewish relations
            "polin", "antypolonizm", "restytucj", "ustawa 447",
            # Religious
            "talmud", "synagog", "rabin", "kabał",
        ]
        kw_list = [k.strip().lower() for k in keywords.split(",") if k.strip()] or default_keywords

        with get_session(engine) as session:
            total = session.query(Article).filter(Article.body_clean.isnot(None)).count()

            per_keyword: list[dict[str, Any]] = []
            for kw in kw_list:
                count = (
                    session.query(func.count(Article.id))
                    .filter(Article.body_clean.ilike(f"%{kw}%"))
                    .scalar()
                ) or 0
                per_keyword.append({"keyword": kw, "count": count})

            per_keyword.sort(key=lambda x: x["count"], reverse=True)

            # Total distinct articles matching ANY keyword
            filters = [Article.body_clean.ilike(f"%{kw}%") for kw in kw_list]
            total_matches = (
                session.query(func.count(Article.id))
                .filter(or_(*filters))
                .scalar()
            ) or 0

        return {
            "total_articles": total,
            "total_matches": total_matches,
            "match_pct": round(100 * total_matches / total, 1) if total else 0.0,
            "per_keyword": per_keyword,
        }

    @app.get("/api/articles")
    async def articles_list(
        page: int = 1,
        per_page: int = 20,
        site: str = "",
        q: str = "",
    ) -> dict[str, Any]:
        with get_session(engine) as session:
            query = session.query(Article)
            if site:
                query = query.filter(Article.site == site)
            if q:
                query = query.filter(
                    Article.title.contains(q) | Article.body_clean.contains(q)
                )
            total = query.count()
            rows = (
                query.order_by(Article.publication_date.desc())
                .offset((page - 1) * per_page)
                .limit(per_page)
                .all()
            )
        return {
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": max(1, (total + per_page - 1) // per_page),
            "articles": [
                {
                    "id": a.id,
                    "site": a.site,
                    "title": a.title,
                    "author": a.author,
                    "publication_date": (
                        a.publication_date.isoformat() if a.publication_date else None
                    ),
                    "url": a.url,
                }
                for a in rows
            ],
        }

    @app.get("/api/articles/{article_id}")
    async def article_detail(article_id: int) -> dict[str, Any]:
        with get_session(engine) as session:
            a = session.get(Article, article_id)
            if a is None:
                raise HTTPException(status_code=404, detail="Article not found")
            return {
                "id": a.id,
                "site": a.site,
                "title": a.title,
                "author": a.author,
                "publication_date": a.publication_date.isoformat() if a.publication_date else None,
                "url": a.url,
                "body": a.body_clean or a.body_raw or "",
            }

    @app.get("/api/keyword-groups")
    async def keyword_groups() -> dict[str, Any]:
        return {"groups": KEYWORD_GROUPS}

    @app.get("/api/keyword-frequency")
    def keyword_frequency(
        granularity: str = "month",
        site: str = "all",
        groups: str = "",
    ) -> dict[str, Any]:
        from collections import defaultdict
        from datetime import datetime as dt

        group_list = [g.strip() for g in groups.split(",") if g.strip()]
        keywords: list[str] = []
        if group_list:
            for g in group_list:
                keywords.extend(KEYWORD_GROUPS.get(g, []))
        else:
            for kws in KEYWORD_GROUPS.values():
                keywords.extend(kws)
        keywords = list(dict.fromkeys(keywords))  # deduplicate, preserve order

        with get_session(engine) as session:
            query = session.query(
                Article.publication_date, Article.site, Article.body_clean
            ).filter(
                Article.body_clean.isnot(None),
                Article.publication_date.isnot(None),
            )
            if site != "all":
                query = query.filter(Article.site == site)
            rows = query.all()

        period_article_ids: dict[str, set[int]] = defaultdict(set)
        period_hits: dict[str, int] = defaultdict(int)
        kw_period: dict[str, dict[str, int]] = {kw: defaultdict(int) for kw in keywords}

        for i, (pub_date, _site, body) in enumerate(rows):
            if isinstance(pub_date, str):
                pub_date = dt.fromisoformat(pub_date)
            if granularity == "week":
                iso = pub_date.isocalendar()
                from datetime import datetime as _dt
                period = _dt.fromisocalendar(iso.year, iso.week, 1).strftime("%Y-%m-%d")
            else:
                period = pub_date.strftime("%Y-%m-01")

            body_lower = body.lower()
            for kw in keywords:
                count = body_lower.count(kw)
                if count:
                    period_hits[period] += count
                    kw_period[kw][period] += 1
                    period_article_ids[period].add(i)

        all_periods = sorted(set(period_hits) | set(period_article_ids))
        return {
            "periods": all_periods,
            "articles_with_match": [len(period_article_ids.get(p, set())) for p in all_periods],
            "total_hits": [period_hits.get(p, 0) for p in all_periods],
            "per_keyword": {
                kw: [kw_period[kw].get(p, 0) for p in all_periods]
                for kw in keywords
            },
        }

    @app.get("/api/analysis-data")
    def analysis_data_endpoint(site: str = "all", cutoff: str = "2023-10-07") -> dict[str, Any]:
        from datetime import datetime as dt

        import pandas as pd

        from otwarta.storage.models import AnalysisResult as AR
        from otwarta.storage.models import Article as Art
        from otwarta.visualization.comparison import create_comparison_chart
        from otwarta.visualization.mention_frequency import (
            create_frequency_vs_score_chart,
            create_mention_frequency_chart,
        )
        from otwarta.visualization.score_scatter import create_score_scatter_chart
        from otwarta.visualization.site_comparison import create_site_comparison_chart
        from otwarta.visualization.stats import bootstrap_ci, cohens_d, mann_whitney_u
        from otwarta.visualization.time_series import create_time_series_chart
        from otwarta.visualization.trope_evolution import create_trope_stacked_area

        cutoff_dt = dt.fromisoformat(cutoff)
        with get_session(engine) as session:
            query = (
                session.query(Art.url, Art.site, Art.title, Art.publication_date,
                              AR.severity_score, AR.hateful_score, AR.result_json)
                .join(AR)
                .filter(Art.publication_date.isnot(None))
            )
            if site != "all":
                query = query.filter(Art.site == site)
            rows = query.all()

        if not rows:
            return {"error": "No analyzed articles found.", "time_series": None,
                    "comparison": None, "scatter": None, "stats": {}}

        df = pd.DataFrame(rows, columns=["url", "site", "title", "publication_date",
                                         "severity_score", "hateful_score", "result_json"])
        df = df.dropna(subset=["publication_date", "severity_score"])
        df["publication_date"] = pd.to_datetime(df["publication_date"])

        pre = df[df["publication_date"] < cutoff_dt]["severity_score"].tolist()
        post = df[df["publication_date"] >= cutoff_dt]["severity_score"].tolist()

        stats_result: dict[str, Any] = {}
        if pre and post:
            mw = mann_whitney_u(pre, post)
            d = cohens_d(pre, post)
            ci_lo, ci_hi = bootstrap_ci(post)
            stats_result = {
                "p_value": mw["p_value"],
                "significant": mw["significant"],
                "cohens_d": d,
                "ci_lo": ci_lo,
                "ci_hi": ci_hi,
                "n_pre": len(pre),
                "n_post": len(post),
                "mean_pre": float(sum(pre) / len(pre)),
                "mean_post": float(sum(post) / len(post)),
            }

        # Hateful score stats (separate from antisemitism)
        hate_stats_result: dict[str, Any] = {}
        if "hateful_score" in df.columns:
            hate_df = df.dropna(subset=["hateful_score"])
            hate_pre  = hate_df[hate_df["publication_date"] < cutoff_dt]["hateful_score"].tolist()
            hate_post = hate_df[hate_df["publication_date"] >= cutoff_dt]["hateful_score"].tolist()
            if hate_pre and hate_post:
                hmw = mann_whitney_u(hate_pre, hate_post)
                hd  = cohens_d(hate_pre, hate_post)
                hci_lo, hci_hi = bootstrap_ci(hate_post)
                hate_stats_result = {
                    "p_value": hmw["p_value"],
                    "significant": hmw["significant"],
                    "cohens_d": hd,
                    "ci_lo": hci_lo,
                    "ci_hi": hci_hi,
                    "mean_pre": float(sum(hate_pre) / len(hate_pre)),
                    "mean_post": float(sum(hate_post) / len(hate_post)),
                }

        site_arg = None if site == "all" else site
        ts_fig = create_time_series_chart(df, site=site_arg)
        comp_fig = create_comparison_chart(df, cutoff=cutoff_dt)
        scatter_fig = create_score_scatter_chart(df)
        site_cmp_fig = create_site_comparison_chart(df)
        trope_fig = create_trope_stacked_area(df)
        freq_fig = create_mention_frequency_chart(df)
        freq_score_fig = create_frequency_vs_score_chart(df)

        return {
            "time_series": ts_fig.to_json(),
            "comparison": comp_fig.to_json(),
            "scatter": scatter_fig.to_json(),
            "site_comparison": site_cmp_fig.to_json(),
            "trope_evolution": trope_fig.to_json(),
            "mention_frequency": freq_fig.to_json(),
            "frequency_vs_score": freq_score_fig.to_json(),
            "stats": stats_result,
            "hate_stats": hate_stats_result,
        }

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
