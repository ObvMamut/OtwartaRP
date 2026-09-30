from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    site: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str | None] = mapped_column(String)
    author: Mapped[str | None] = mapped_column(String)
    publication_date: Mapped[datetime | None] = mapped_column(DateTime)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    body_raw: Mapped[str | None] = mapped_column(String)
    body_clean: Mapped[str | None] = mapped_column(String)
    analysis_claimed_at: Mapped[datetime | None] = mapped_column(DateTime)
    analysis_worker_id: Mapped[str | None] = mapped_column(String)
    analysis_completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    analysis_results: Mapped[list["AnalysisResult"]] = relationship(back_populates="article")


class AnalysisResult(Base):
    __tablename__ = "analysis_results"
    __table_args__ = (UniqueConstraint("article_id", "analysis_config"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), nullable=False)
    analysis_config: Mapped[str] = mapped_column(String, nullable=False)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    model_id: Mapped[str] = mapped_column(String, nullable=False)
    severity_score: Mapped[float | None] = mapped_column(Float)
    hateful_score: Mapped[float | None] = mapped_column(Float)
    secondary_model_id: Mapped[str | None] = mapped_column(String)
    secondary_model_score: Mapped[float | None] = mapped_column(Float)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)

    article: Mapped["Article"] = relationship(back_populates="analysis_results")


class ScrapingJob(Base):
    __tablename__ = "scraping_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    site: Mapped[str] = mapped_column(String, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String, default="running")
    articles_discovered: Mapped[int] = mapped_column(Integer, default=0)
    articles_scraped: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
