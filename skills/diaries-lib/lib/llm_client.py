import json
import re
import time
import anthropic

MODEL = "claude-sonnet-4-20250514"
MAX_RETRIES = 3
BASE_DELAY = 2.0


class LLMClient:
    def __init__(self, model: str = MODEL):
        self.client = anthropic.Anthropic()
        self.model = model

    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> str:
        last_exc = None
        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                return response.content[0].text
            except anthropic.RateLimitError as e:
                last_exc = e
                time.sleep(BASE_DELAY * (2 ** attempt))
            except anthropic.APIStatusError as e:
                if e.status_code >= 500:
                    last_exc = e
                    time.sleep(BASE_DELAY * (2 ** attempt))
                else:
                    raise
        raise last_exc

    def complete_json(self, system: str, user: str, **kwargs) -> dict | list:
        text = self.complete(
            system=system + "\n\nResponde ÚNICAMENTE con JSON válido, sin texto adicional ni bloques de código.",
            user=user,
            **kwargs,
        )
        text = re.sub(r"^```json\s*", "", text.strip())
        text = re.sub(r"\s*```$", "", text)
        return json.loads(text)
