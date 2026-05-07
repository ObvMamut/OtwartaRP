import pytest
from datetime import datetime
from otwarta.storage.database import init_db, get_session
from otwarta.storage.repository import get_or_create_article, save_analysis, claim_batch
from otwarta.storage.models import Article, AnalysisResult


@pytest.fixture
def db_session(tmp_path):
    db_url = f"sqlite:///{tmp_path}/test.db"
    engine = init_db(db_url)
    with get_session(engine) as session:
        yield session


def test_get_or_create_article_creates_new(db_session):
    article = get_or_create_article(db_session, url="https://example.com/article-1", site="dorzeczy")
    assert article.id is not None
    assert article.url == "https://example.com/article-1"


def test_get_or_create_article_returns_existing(db_session):
    a1 = get_or_create_article(db_session, url="https://example.com/a", site="dorzeczy")
    a2 = get_or_create_article(db_session, url="https://example.com/a", site="dorzeczy")
    assert a1.id == a2.id


def test_claim_batch_returns_unclaimed(db_session):
    for i in range(5):
        get_or_create_article(db_session, url=f"https://example.com/{i}", site="dorzeczy")
    db_session.commit()
    claimed = claim_batch(db_session, worker_id="w1", batch_size=3)
    assert len(claimed) == 3


def test_save_analysis_writes_result(db_session):
    article = get_or_create_article(db_session, url="https://example.com/art", site="pch24")
    db_session.commit()
    save_analysis(db_session, article_id=article.id, config="antisemitism_oct7",
                  model_id="llm-model", severity_score=7.5,
                  result_json={"severity_score": 7.5, "explanation": "test"},
                  prompt_tokens=100, completion_tokens=50, cache_read_tokens=80)
    db_session.commit()
    result = db_session.query(AnalysisResult).filter_by(article_id=article.id).one()
    assert result.severity_score == 7.5
