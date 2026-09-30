import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

PROMPTS_DIR = Path(__file__).parent / "prompts"
_MAX_RETRIES = 5
_PARSE_ERROR_RESULT: dict[str, Any] = {
    "severity_score": 0.0,
    "hateful_score": 0.0,
    "severity_label": "NONE",
    "trope_categories": [],
    "antisemitic_tropes": [],
    "evidence_sentences": [],
    "explanation": "Parse error",
    "is_antisemitic": False,
    "is_about_israel_gaza": False,
}


class OllamaAnalysisClient:
    """Async Ollama client with two-stage analysis: primary model, then secondary if score is 0."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        primary_model: str = "llama3.1",
        secondary_model: str = "mistral-nemo",
        max_concurrent: int = 4,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.primary_model = primary_model
        self.secondary_model = secondary_model
        self._sem = asyncio.Semaphore(max_concurrent)
        self._system_prompts: dict[str, str] = {}

    def _load_system_prompt(self, config_name: str) -> str:
        if config_name not in self._system_prompts:
            prompt_file = PROMPTS_DIR / f"{config_name}_system.txt"
            if not prompt_file.exists():
                prompt_file = PROMPTS_DIR / "antisemitism_system.txt"
            self._system_prompts[config_name] = prompt_file.read_text(encoding="utf-8")
        return self._system_prompts[config_name]

    async def _call_model(
        self,
        model: str,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
    ) -> dict[str, Any]:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "format": "json",
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        async with self._sem:
            for attempt in range(_MAX_RETRIES):
                try:
                    async with httpx.AsyncClient(timeout=300.0) as client:
                        response = await client.post(
                            f"{self.base_url}/api/chat",
                            json=payload,
                        )
                        response.raise_for_status()
                        raw = response.json()["message"]["content"]
                        parsed: dict[str, Any] = json.loads(raw)
                        return parsed
                except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                    if attempt < _MAX_RETRIES - 1:
                        delay = 2 ** attempt
                        logger.warning(
                            f"Ollama connection error (attempt {attempt + 1}/{_MAX_RETRIES}), "
                            f"retrying in {delay}s: {exc}"
                        )
                        await asyncio.sleep(delay)
                    else:
                        raise
                except json.JSONDecodeError as exc:
                    logger.warning(f"Failed to parse JSON from {model}: {exc}")
                    return dict(_PARSE_ERROR_RESULT)
        return dict(_PARSE_ERROR_RESULT)

    async def analyze_article(
        self,
        title: str,
        body: str,
        config_name: str = "antisemitism_oct7",
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        truncated_body = body[:16000] if len(body) > 16000 else body
        user_message = f"Article title: {title}\n\nArticle body:\n{truncated_body}"
        system_prompt = self._load_system_prompt(config_name)

        result = await self._call_model(
            self.primary_model, system_prompt, user_message, max_tokens
        )
        result.setdefault("severity_score", 0.0)
        result.setdefault("hateful_score", 0.0)
        result.setdefault("trope_categories", [])
        result["_secondary_model"] = None

        if result["severity_score"] < 2.0:
            logger.debug(
                f"Primary model gave score {result['severity_score']}; "
                f"confirming with {self.secondary_model}"
            )
            secondary = await self._call_model(
                self.secondary_model, system_prompt, user_message, max_tokens
            )
            secondary.setdefault("severity_score", 0.0)
            secondary.setdefault("hateful_score", 0.0)
            secondary.setdefault("trope_categories", [])

            result["_secondary_model"] = {
                "model": self.secondary_model,
                "score": secondary["severity_score"],
            }
            if secondary["severity_score"] > result["severity_score"]:
                # Secondary scored higher — use its (more sensitive) assessment
                result.update(secondary)
                result["_secondary_model"] = {
                    "model": self.secondary_model,
                    "score": secondary["severity_score"],
                }

        result["_tokens"] = {"input": 0, "output": 0, "cache_read": 0, "cache_created": 0}
        return result
