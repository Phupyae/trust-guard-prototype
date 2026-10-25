"""One small interface for "ask the LLM, get JSON back", with swappable backends.

Why structured output via tool use? If you just ask an LLM to "reply in JSON" it
sometimes adds prose, markdown fences, or a missing field, and json.loads() crashes
mid-demo. Instead we define a "tool" with a JSON schema and FORCE the model to call
it. The API then returns arguments that already match the schema, so parsing can't
fail on formatting.

Why an interface? Extraction and verification only call `structured(...)`. Swapping
Claude for another provider (or the offline mock) means writing one new class here;
nothing else changes.
"""
import re

import config


class LLMError(RuntimeError):
    """Raised with a human-readable message the UI can show directly."""


class ClaudeClient:
    name = "claude"

    def __init__(self, api_key: str = config.ANTHROPIC_API_KEY, model: str = config.CLAUDE_MODEL):
        if not api_key:
            raise LLMError("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key.")
        import anthropic
        self._anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=api_key, max_retries=2, timeout=60)
        self.model = model

    def structured(self, system: str, user: str, tool_name: str, schema: dict,
                   context: dict | None = None, max_tokens: int = 1500) -> dict:
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=0,  # same input -> (nearly) same output; important for a verifier
                system=system,
                messages=[{"role": "user", "content": user}],
                tools=[{"name": tool_name, "description": f"Record the {tool_name} result.",
                        "input_schema": schema}],
                tool_choice={"type": "tool", "name": tool_name},
            )
        except self._anthropic.AuthenticationError as e:
            raise LLMError("The Anthropic API key was rejected. Check ANTHROPIC_API_KEY.") from e
        except self._anthropic.RateLimitError as e:
            raise LLMError("Rate limited by the Anthropic API. Wait a few seconds and retry.") from e
        except self._anthropic.APIConnectionError as e:
            raise LLMError("Could not reach the Anthropic API. Check your internet connection.") from e
        except self._anthropic.APIStatusError as e:
            raise LLMError(f"Anthropic API error ({e.status_code}): {e.message}") from e

        for block in response.content:
            if block.type == "tool_use":
                return block.input
        raise LLMError("The model did not return a structured result.")


class GeminiClient:
    """Google Gemini backend (has a free tier). Same idea as ClaudeClient: we hand
    the API our JSON schema and it constrains the output to match it, here via
    response_json_schema instead of a forced tool call."""
    name = "gemini"

    def __init__(self, api_key: str = config.GEMINI_API_KEY, model: str = config.GEMINI_MODEL):
        if not api_key:
            raise LLMError("GEMINI_API_KEY is not set. Get a free key at aistudio.google.com and add it to .env.")
        from google import genai
        from google.genai import errors, types
        self._errors, self._types = errors, types
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def structured(self, system: str, user: str, tool_name: str, schema: dict,
                   context: dict | None = None, max_tokens: int = 1500) -> dict:
        import json
        import time
        cfg = self._types.GenerateContentConfig(
            system_instruction=system,
            temperature=0,
            max_output_tokens=max_tokens,
            response_mime_type="application/json",
            response_json_schema=schema,
        )
        for attempt in range(3):
            try:
                response = self.client.models.generate_content(model=self.model, contents=user, config=cfg)
                break
            except self._errors.ClientError as e:
                # Free tier has a low requests-per-minute cap; parallel claim checks can hit it.
                if e.code == 429 and attempt < 2:
                    time.sleep(5 * (attempt + 1))
                    continue
                if e.code == 429:
                    raise LLMError("Gemini free-tier rate limit reached. Wait a minute, or the daily "
                                   "quota may be used up.") from e
                if e.code in (401, 403) or "API key" in str(e):
                    raise LLMError("The Gemini API key was rejected. Check GEMINI_API_KEY.") from e
                raise LLMError(f"Gemini API error ({e.code}): {e.message}") from e
            except self._errors.ServerError as e:
                if attempt < 2:
                    time.sleep(3)
                    continue
                raise LLMError(f"Gemini server error ({e.code}). Try again shortly.") from e
            except Exception as e:
                raise LLMError(f"Could not reach the Gemini API: {type(e).__name__}") from e
        try:
            return json.loads(response.text)
        except (TypeError, ValueError) as e:
            raise LLMError("Gemini returned output that was not valid JSON.") from e


class MockClient:
    """Offline stand-in used ONLY for development and automated tests.

    It uses crude keyword/number heuristics, not real language understanding.
    The UI shows a loud warning whenever it is active. Never demo with it."""
    name = "mock"

    def structured(self, system: str, user: str, tool_name: str, schema: dict,
                   context: dict | None = None, max_tokens: int = 0) -> dict:
        context = context or {}
        if tool_name == "record_claims":
            sentences = re.split(r"(?<=[.!?])\s+", context["answer"].strip())
            return {"claims": [{"claim": s.strip()} for s in sentences if len(s.split()) >= 3]}
        if tool_name == "record_verdict":
            return self._verdict(context["claim"], context["passages"])
        raise LLMError(f"Mock has no handler for {tool_name}")

    @staticmethod
    def _verdict(claim: str, passages: list[str]) -> dict:
        from modules.policy_rules import numeric_check, requirement_check
        claim_l = claim.lower()
        words = lambda t: set(re.findall(r"[a-z]{4,}", t)) - {"employees", "claim", "claims", "with", "that"}
        for i, passage in enumerate(passages):
            if len(words(claim_l) & words(passage.lower())) < 2:
                continue
            first_sentence = re.split(r"(?<=[.!?])\s+", passage)[0]
            verdict = lambda s, why: {"status": s, "evidence_passage": i + 1,
                                      "evidence_quote": first_sentence, "explanation": f"[mock] {why}"}
            if requirement_check(claim, passage)[0] == "mismatch":
                return verdict("CONTRADICTED", "Policy requires a step the claim says is not needed.")
            num = numeric_check(claim, passage)[0]
            if num == "mismatch":
                return verdict("CONTRADICTED", "Numbers differ.")
            if num == "match":
                return verdict("SUPPORTED", "Numbers match.")
            return verdict("SUPPORTED", "Wording overlaps.")
        return {"status": "INSUFFICIENT_EVIDENCE", "evidence_passage": 0,
                "evidence_quote": "", "explanation": "[mock] No passage addresses this claim."}


def get_client(provider: str = config.LLM_PROVIDER):
    if provider == "mock":
        return MockClient()
    if provider == "claude":
        return ClaudeClient()
    if provider == "gemini":
        return GeminiClient()
    raise LLMError(f"Unknown LLM_PROVIDER '{provider}'. Use 'claude', 'gemini' or 'mock'.")
