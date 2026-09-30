import json

import httpx
import pytest
import respx

from otwarta.analysis.ollama_client import OllamaAnalysisClient

_BASE = "http://localhost:11434"
_CHAT_URL = f"{_BASE}/api/chat"

_ANTISEMITIC_JSON = {
    "severity_score": 6.5,
    "hateful_score": 2.0,
    "severity_label": "MEDIUM",
    "trope_categories": ["conspiracy"],
    "antisemitic_tropes": ["globalist conspiracy"],
    "evidence_sentences": ["Żydowskie elity rządzą mediami"],
    "explanation": "Classic conspiracy framing.",
    "is_antisemitic": True,
    "is_about_israel_gaza": False,
}

_ZERO_JSON = {
    "severity_score": 0,
    "hateful_score": 0.0,
    "severity_label": "NONE",
    "trope_categories": [],
    "antisemitic_tropes": [],
    "evidence_sentences": [],
    "explanation": "No antisemitic content found.",
    "is_antisemitic": False,
    "is_about_israel_gaza": False,
}

_SECONDARY_FINDS_JSON = {
    "severity_score": 3.0,
    "hateful_score": 1.0,
    "severity_label": "LOW",
    "trope_categories": ["economic"],
    "antisemitic_tropes": ["banking conspiracy"],
    "evidence_sentences": ["example"],
    "explanation": "Subtle economic trope.",
    "is_antisemitic": True,
    "is_about_israel_gaza": False,
}


def _chat_response(payload: dict) -> dict:
    return {"message": {"content": json.dumps(payload)}}


@pytest.mark.asyncio
@respx.mock
async def test_analyze_returns_score_no_second_call():
    """Primary model returns non-zero score; secondary model is NOT called."""
    respx.post(_CHAT_URL).mock(
        return_value=httpx.Response(200, json=_chat_response(_ANTISEMITIC_JSON))
    )

    client = OllamaAnalysisClient(base_url=_BASE)
    result = await client.analyze_article(title="Test", body="Żydowskie elity rządzą mediami.")

    assert result["severity_score"] == 6.5
    assert result["hateful_score"] == 2.0
    assert result["trope_categories"] == ["conspiracy"]
    assert result["_secondary_model"] is None
    # Only one call was made (to the primary model)
    assert respx.calls.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_two_stage_triggers_when_primary_score_is_zero():
    """Primary returns 0; secondary is called and its score is used."""
    call_count = 0

    def _side_effect(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        payload = _chat_response(_ZERO_JSON if call_count == 1 else _SECONDARY_FINDS_JSON)
        return httpx.Response(200, json=payload)

    respx.post(_CHAT_URL).mock(side_effect=_side_effect)

    client = OllamaAnalysisClient(base_url=_BASE)
    result = await client.analyze_article(title="Test", body="Artykuł o finansjerze i banksterach.")

    assert call_count == 2
    assert result["severity_score"] == 3.0
    assert result["_secondary_model"] == {"model": "mistral-nemo", "score": 3.0}


@pytest.mark.asyncio
@respx.mock
async def test_both_models_agree_on_zero():
    """Primary and secondary both return 0; final score stays 0."""
    respx.post(_CHAT_URL).mock(
        return_value=httpx.Response(200, json=_chat_response(_ZERO_JSON))
    )

    client = OllamaAnalysisClient(base_url=_BASE)
    result = await client.analyze_article(title="Neutralny artykuł", body="Dobra pogoda dziś.")

    assert result["severity_score"] == 0
    assert result["_secondary_model"] == {"model": "mistral-nemo", "score": 0}
    assert respx.calls.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_json_parse_error_returns_fallback():
    """Malformed JSON from Ollama yields parse-error fallback dict."""
    respx.post(_CHAT_URL).mock(
        return_value=httpx.Response(200, json={"message": {"content": "not json at all"}})
    )

    client = OllamaAnalysisClient(base_url=_BASE)
    result = await client.analyze_article(title="T", body="B")

    assert result["severity_score"] == 0.0
    assert result["explanation"] == "Parse error"


@pytest.mark.asyncio
@respx.mock
async def test_retries_on_connection_error():
    """ConnectError triggers retries; success on 3rd attempt."""
    respx.post(_CHAT_URL).mock(
        side_effect=[
            httpx.ConnectError("refused"),
            httpx.ConnectError("refused"),
            httpx.Response(200, json=_chat_response(_ANTISEMITIC_JSON)),
        ]
    )

    client = OllamaAnalysisClient(base_url=_BASE)
    result = await client.analyze_article(title="T", body="B")

    assert respx.calls.call_count == 3
    assert result["severity_score"] == 6.5
