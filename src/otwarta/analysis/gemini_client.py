import json
from pathlib import Path
from typing import Any

import google.generativeai as genai
from loguru import logger

PROMPTS_DIR = Path(__file__).parent / "prompts"


class GeminiAnalysisClient:
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        genai.configure(api_key=api_key)
        self.model = model
        self._system_prompts: dict[str, str] = {}
        self._models: dict[str, genai.GenerativeModel] = {}

    def _load_system_prompt(self, config_name: str) -> str:
        if config_name not in self._system_prompts:
            prompt_file = PROMPTS_DIR / f"{config_name}_system.txt"
            if not prompt_file.exists():
                prompt_file = PROMPTS_DIR / "antisemitism_system.txt"
            self._system_prompts[config_name] = prompt_file.read_text(encoding="utf-8")
        return self._system_prompts[config_name]

    def _get_model(self, config_name: str) -> genai.GenerativeModel:
        if config_name not in self._models:
            system_prompt = self._load_system_prompt(config_name)
            self._models[config_name] = genai.GenerativeModel(
                model_name=self.model,
                system_instruction=system_prompt,
            )
        return self._models[config_name]

    async def analyze_article(
        self,
        title: str,
        body: str,
        config_name: str = "antisemitism_oct7",
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        truncated_body = body[:16000] if len(body) > 16000 else body
        prompt = f"Article title: {title}\n\nArticle body:\n{truncated_body}"

        model = self._get_model(config_name)
        response = await model.generate_content_async(
            contents=prompt,
            generation_config={"max_output_tokens": max_tokens},
        )

        try:
            raw_text = response.text or "{}"
        except ValueError:
            raw_text = "{}"
        usage = response.usage_metadata

        try:
            result = json.loads(raw_text)
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
