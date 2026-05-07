from typing import Any

from otwarta.analysis.llm_client import LLMAnalysisClient


class AntisemitismDetector:
    KEYWORDS = [
        "żyd", "żydzi", "izrael", "holokaust", "antysemit",
        "soros", "globalist", "hamas", "gaza", "palestyn",
        "semick", "żydokomuna",
    ]

    def __init__(self, api_key: str):
        self.client = LLMAnalysisClient(api_key=api_key)

    def passes_keyword_filter(self, body: str) -> bool:
        body_lower = body.lower()
        return any(kw in body_lower for kw in self.KEYWORDS)

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
        return await self.client.analyze_article(title=title, body=body)
