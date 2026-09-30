import asyncio
import json
import re
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types
from loguru import logger

_RETRY_DELAY_RE = re.compile(r"retry in (\d+(?:\.\d+)?)s", re.IGNORECASE)
_MAX_RETRIES = 8


def _is_rate_limit(exc: Exception) -> bool:
    s = str(exc).lower()
    return "429" in s or "quota" in s or "rate_limit" in s or "resource_exhausted" in s


def _retry_delay(exc: Exception, attempt: int) -> float:
    m = _RETRY_DELAY_RE.search(str(exc))
    suggested = float(m.group(1)) if m else 0.0
    # Respect the API's suggested delay; never wait less than exponential floor
    backoff: float = min(30 * (2 ** attempt), 300)
    return max(suggested + 2, backoff)

PROMPTS_DIR = Path(__file__).parent / "prompts"


class GeminiAnalysisClient:
    def __init__(
        self, api_key: str, model: str = "gemini-2.0-flash", requests_per_minute: int = 14
    ):
        self._client = genai.Client(api_key=api_key)
        self.model = model
        self._system_prompts: dict[str, str] = {}
        self._min_interval = 60.0 / requests_per_minute
        self._last_call_time: float = 0.0
        self._rate_lock = asyncio.Lock()

    async def _wait_for_rate_limit(self) -> None:
        async with self._rate_lock:
            now = asyncio.get_event_loop().time()
            wait = self._min_interval - (now - self._last_call_time)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call_time = asyncio.get_event_loop().time()

    def _load_system_prompt(self, config_name: str) -> str:
        if config_name not in self._system_prompts:
            prompt_file = PROMPTS_DIR / f"{config_name}_system.txt"
            if not prompt_file.exists():
                prompt_file = PROMPTS_DIR / "antisemitism_system.txt"
            self._system_prompts[config_name] = prompt_file.read_text(encoding="utf-8")
        return self._system_prompts[config_name]

    async def analyze_article(
        self,
        title: str,
        body: str,
        config_name: str = "antisemitism_oct7",
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        truncated_body = body[:16000] if len(body) > 16000 else body
        prompt = f"Article title: {title}\n\nArticle body:\n{truncated_body}"
        system_prompt = self._load_system_prompt(config_name)

        await self._wait_for_rate_limit()
        for attempt in range(_MAX_RETRIES):
            try:
                response = await self._client.aio.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        max_output_tokens=max_tokens,
                    ),
                )
                break
            except Exception as exc:
                if _is_rate_limit(exc) and attempt < _MAX_RETRIES - 1:
                    delay = _retry_delay(exc, attempt)
                    logger.warning(
                        f"Rate limited (attempt {attempt + 1}/{_MAX_RETRIES}), "
                        f"waiting {delay:.0f}s before retry… error: {exc}"
                    )
                    await asyncio.sleep(delay)
                else:
                    raise

        try:
            raw_text = response.text or "{}"
        except ValueError:
            raw_text = "{}"
        usage = response.usage_metadata

        try:
            result: dict[str, Any] = json.loads(raw_text)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse JSON response: {raw_text[:200]}")
            result = {
                "severity_score": 0.0,
                "severity_label": "NONE",
                "antisemitic_tropes": [],
                "evidence_sentences": [],
                "explanation": "Parse error",
                "is_antisemitic": False,
                "is_about_israel_gaza": False,
            }

        result["_tokens"] = {
            "input": usage.prompt_token_count if usage else 0,
            "output": usage.candidates_token_count if usage else 0,
            "cache_read": 0,
            "cache_created": 0,
        }
        return result
