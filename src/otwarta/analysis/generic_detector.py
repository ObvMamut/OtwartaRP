"""Generic YAML-config-driven analysis detector."""
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from otwarta.analysis.gemini_client import GeminiAnalysisClient

_DEFAULT_CONFIG: dict[str, Any] = {
    "name": "antisemitism_oct7",
    "keywords": [
        "żyd", "żydzi", "izrael", "holokaust", "antysemit",
        "soros", "globalist", "hamas", "gaza", "palestyn",
        "semick", "żydokomuna",
    ],
    "prompt_file": "antisemitism_oct7_system.txt",
}


class GenericDetector:
    def __init__(self, config_path: str, api_key: str, model: str = "gemini-2.0-flash"):
        self.config = self._load_config(config_path)
        self.client = GeminiAnalysisClient(api_key=api_key, model=model)
        self._keywords: list[str] = self.config.get("keywords", [])

    def _load_config(self, config_path: str) -> dict[str, Any]:
        p = Path(config_path)
        if p.exists():
            with p.open(encoding="utf-8") as f:
                loaded: dict[str, Any] = yaml.safe_load(f) or {}
            logger.info(f"Loaded analysis config: {config_path}")
            return loaded
        logger.warning(
            f"Analysis config not found: {config_path!r}. Using default antisemitism config."
        )
        return dict(_DEFAULT_CONFIG)

    def passes_keyword_filter(self, body: str) -> bool:
        if not self._keywords:
            return True
        body_lower = body.lower()
        return any(kw in body_lower for kw in self._keywords)

    async def analyze(self, title: str, body: str) -> dict[str, Any]:
        if not self.passes_keyword_filter(body):
            return {
                "severity_score": 0.0,
                "severity_label": "NONE",
                "antisemitic_tropes": [],
                "evidence_sentences": [],
                "explanation": "Filtered: no relevant keywords",
                "is_antisemitic": False,
                "is_about_israel_gaza": False,
                "_tokens": {"input": 0, "output": 0, "cache_read": 0, "cache_created": 0},
            }
        config_name = self.config.get("name", "antisemitism_oct7")
        return await self.client.analyze_article(title=title, body=body, config_name=config_name)
