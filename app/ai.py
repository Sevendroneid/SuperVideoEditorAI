from typing import Any

import httpx


class AIProviderError(RuntimeError):
    pass


class AIProvider:
    def __init__(self, provider: str, base_url: str | None, api_key: str | None, model: str | None) -> None:
        self.provider = provider
        self.base_url = base_url.rstrip("/") if base_url else None
        self.api_key = api_key
        self.model = model

    @property
    def enabled(self) -> bool:
        return self.provider != "disabled" and bool(self.base_url and self.api_key and self.model)

    async def generate_story_direction(self, evidence: list[dict[str, Any]], instruction: str) -> dict[str, Any]:
        if not self.enabled:
            return {
                "provider": "disabled",
                "mode": "deterministic",
                "instruction": instruction,
                "decision": "AI provider disabled; deterministic baseline retained.",
                "evidence_count": len(evidence),
            }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a video editing director. Return JSON only. Never invent footage."},
                {"role": "user", "content": f"Instruction: {instruction}\nVerified clip evidence: {evidence}"},
            ],
            "temperature": 0.2,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(self.base_url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AIProviderError(f"AI provider request failed: {exc}") from exc
        return {"provider": self.provider, "response": data}
