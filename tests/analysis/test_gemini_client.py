import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from otwarta.analysis.gemini_client import GeminiAnalysisClient

_MOCK_JSON = {
    "severity_score": 6.5,
    "severity_label": "MEDIUM",
    "antisemitic_tropes": ["conspiracy theory"],
    "evidence_sentences": ["Żydowskie elity rządzą mediami"],
    "explanation": "Classic conspiracy framing.",
    "is_antisemitic": True,
    "is_about_israel_gaza": False,
}


def _mock_response(text: str, prompt_tokens: int = 1500, output_tokens: int = 120) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    resp.usage_metadata = MagicMock()
    resp.usage_metadata.prompt_token_count = prompt_tokens
    resp.usage_metadata.candidates_token_count = output_tokens
    return resp


@pytest.mark.asyncio
async def test_analyze_article_returns_score():
    mock_resp = _mock_response(json.dumps(_MOCK_JSON))

    with patch("google.generativeai.configure"), \
         patch("google.generativeai.GenerativeModel") as MockModel:
        mock_instance = MagicMock()
        mock_instance.generate_content_async = AsyncMock(return_value=mock_resp)
        MockModel.return_value = mock_instance

        client = GeminiAnalysisClient(api_key="test-key")
        result = await client.analyze_article(
            title="Test",
            body="Żydowskie elity rządzą mediami i kontrolują rząd.",
            config_name="antisemitism_oct7",
        )

    assert result["severity_score"] == 6.5
    assert result["is_antisemitic"] is True
    assert result["_tokens"]["input"] == 1500
    assert result["_tokens"]["output"] == 120
    assert result["_tokens"]["cache_read"] == 0


@pytest.mark.asyncio
async def test_analyze_article_handles_json_parse_error():
    mock_resp = _mock_response("not valid json at all")

    with patch("google.generativeai.configure"), \
         patch("google.generativeai.GenerativeModel") as MockModel:
        mock_instance = MagicMock()
        mock_instance.generate_content_async = AsyncMock(return_value=mock_resp)
        MockModel.return_value = mock_instance

        client = GeminiAnalysisClient(api_key="test-key")
        result = await client.analyze_article(title="T", body="B")

    assert result["severity_score"] == 0.0
    assert result["explanation"] == "Parse error"
    assert result["_tokens"]["input"] == 1500


@pytest.mark.asyncio
async def test_analyze_article_truncates_long_body():
    mock_resp = _mock_response(json.dumps(_MOCK_JSON))
    long_body = "x" * 20000

    with patch("google.generativeai.configure"), \
         patch("google.generativeai.GenerativeModel") as MockModel:
        mock_instance = MagicMock()
        mock_instance.generate_content_async = AsyncMock(return_value=mock_resp)
        MockModel.return_value = mock_instance

        client = GeminiAnalysisClient(api_key="test-key")
        await client.analyze_article(title="T", body=long_body)

        call_args = mock_instance.generate_content_async.call_args
        contents = call_args.kwargs.get("contents") or call_args.args[0]
        assert len(contents) < 17000  # 16000 body + title overhead


def test_keyword_filter_passes():
    from otwarta.analysis.antisemitism_detector import AntisemitismDetector
    with patch("google.generativeai.configure"):
        detector = AntisemitismDetector(api_key="test-key")
    assert detector.passes_keyword_filter("artykuł o żydach w Polsce") is True
    assert detector.passes_keyword_filter("artykuł o pogodzie") is False
