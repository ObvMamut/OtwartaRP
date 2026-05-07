from datetime import datetime, timedelta
from typing import Any
from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from otwarta.storage.models import Article, AnalysisResult


def get_or_create_article(session: Session, url: str, site: str, **kwargs: Any) -> Article:
    stmt = sqlite_insert(Article).values(url=url, site=site, **kwargs).on_conflict_do_nothing(index_elements=["url"])
    session.execute(stmt)
    return session.query(Article).filter_by(url=url).one()


def claim_batch(session: Session, worker_id: str, batch_size: int = 10, stale_minutes: int = 30) -> list[Article]:
    stale_cutoff = datetime.utcnow() - timedelta(minutes=stale_minutes)
    unclaimed = (
        session.query(Article)
        .filter(
            Article.analysis_completed_at.is_(None),
            (Article.analysis_claimed_at.is_(None)) | (Article.analysis_claimed_at < stale_cutoff),
        )
        .limit(batch_size)
        .all()
    )
    for article in unclaimed:
        article.analysis_claimed_at = datetime.utcnow()
        article.analysis_worker_id = worker_id
    session.commit()
    return unclaimed


def save_analysis(
    session: Session,
    article_id: int,
    config: str,
    model_id: str,
    severity_score: float,
    result_json: dict[str, Any],
    prompt_tokens: int,
    completion_tokens: int,
    cache_read_tokens: int,
) -> None:
    result = AnalysisResult(
        article_id=article_id,
        analysis_config=config,
        model_id=model_id,
        severity_score=severity_score,
        result_json=result_json,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cache_read_tokens=cache_read_tokens,
    )
    session.add(result)
    article = session.get(Article, article_id)
    if article:
        article.analysis_completed_at = datetime.utcnow()
    session.commit()
