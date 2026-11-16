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
        try:
            import anthropic
        except ImportError as e:
            raise LLMError("The anthropic package is not installed in this Python environment. "
                           "Activate .venv and run: pip install -r requirements.txt") from e
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
        try:
            from google import genai
            from google.genai import errors, types
        except ImportError as e:
            raise LLMError("The google-genai package is not installed in this Python environment. "
                           "Activate .venv and run: pip install -r requirements.txt") from e
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
            # Generous cap: newer Gemini models may "think" before answering and those tokens
            # count towards the limit, which would cut the JSON off mid-way.
            max_output_tokens=max(max_tokens, config.GEMINI_MAX_OUTPUT_TOKENS),
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
            reason = ""
            try:
                reason = str(response.candidates[0].finish_reason)
            except Exception:
                pass
            if "MAX_TOKENS" in reason:
                raise LLMError("Gemini ran out of output tokens before finishing. Raise GEMINI_MAX_OUTPUT_TOKENS "
                               "in .env.") from e
            raise LLMError("Gemini returned output that was not valid JSON." + (f" ({reason})" if reason else "")) from e


class MockClient:
    """Offline stand-in used ONLY for development and automated tests.

    It uses crude keyword/number heuristics, not real language understanding.
    The UI shows a loud warning whenever it is active. Never demo with it."""
    name = "mock"
    model = "offline mock"

    def __init__(self, model: str | None = None):
        if model:
            self.model = f"offline mock ({model})"

    def structured(self, system: str, user: str, tool_name: str, schema: dict,
                   context: dict | None = None, max_tokens: int = 0) -> dict:
        context = context or {}
        if tool_name == "record_claims":
            sentences = re.split(r"(?<=[.!?])\s+", context["answer"].strip())
            return {"claims": [{"claim": s.strip()} for s in sentences if len(s.split()) >= 3]}
        if tool_name == "record_verdict":
            return self._verdict(context["claim"], context["passages"])
        if tool_name == "record_answer":
            # Agent 1 stand-in: repeat the first sentence of the top two passages.
            passages = context.get("passages", [])
            if not passages:
                return {"answer": "I could not find this in the documents available to me.", "passages_used": []}
            firsts = [re.split(r"(?<=[.!?])\s+", p)[0] for p in passages[:2]]
            return {"answer": "[mock] " + " ".join(firsts), "passages_used": [1, 2][:len(firsts)]}
        if tool_name == "record_intent":
            return self._intent(context.get("message", ""))
        if tool_name == "record_completeness":
            return self._completeness(context.get("answer", ""), context.get("passages", []))
        if tool_name == "record_correction":
            passages = context.get("passages", [])[:2]
            firsts = [re.split(r"(?<=[.!?])\s+", p)[0] for p in passages]
            return {"sentences": [{"text": s, "passage": i + 1, "quote": s} for i, s in enumerate(firsts)]}
        raise LLMError(f"Mock has no handler for {tool_name}")

    @staticmethod
    def _intent(message: str) -> dict:
        m = message.lower()
        out = {"category": "in_scope", "english_question": message, "language": "English",
               "clarifying_question": "", "reply": ""}
        if any(w in m for w in ("weather", "python", "joke", "stock price", "recipe")):
            out["category"] = "off_topic"
        elif re.search(r"\b(?:please |can you |could you )?(?:approve|process|waive|transfer)\b.*\b(?:for me|now|this|my)\b", m):
            out["category"] = "action_request"
        elif len(m.split()) <= 4 and not re.search(r"\d", m):
            out["category"], out["clarifying_question"] = "unclear", "[mock] Could you give more detail?"
        return out

    @staticmethod
    def _completeness(answer: str, passages: list[str]) -> dict:
        from modules.policy_rules import numbers_in
        if not passages:
            return {"required_elements": []}
        first = re.split(r"(?<=[.!?])\s+", passages[0])[0]
        covered = bool(numbers_in(first)) and numbers_in(first) <= numbers_in(answer) or \
            (not numbers_in(first) and len(set(first.lower().split()) & set(answer.lower().split())) >= 4)
        return {"required_elements": [{"element": first, "passage": 1, "quote": first, "covered": covered,
                                       "note": "[mock] number/word overlap"}]}

    @staticmethod
    def _verdict(claim: str, passages: list[str]) -> dict:
        from modules.policy_rules import numeric_check, requirement_check
        claim_l = claim.lower()
        words = lambda t: set(re.findall(r"[a-z]{4,}", t)) - {"employees", "claim", "claims", "with", "that"}
        for i, passage in enumerate(passages):
            if len(words(claim_l) & words(passage.lower())) < 2:
                continue
            first_sentence = re.split(r"(?<=[.!?])\s+", passage)[0]
            verdict = lambda s, why: {"status": s, "evidence_passage": i + 1, "evidence_quote": first_sentence,
                                      "explanation": f"[mock] {why}", "applicability": "[mock] assumed to apply.",
                                      "policy_requirement": f"[mock] {first_sentence}"}
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


def get_client(provider: str = config.LLM_PROVIDER, model: str | None = None):
    """model=None gives TrustGuard's (stronger) model. Agent 1 passes config.AGENT1_MODEL,
    so the assistant and the verifier run on different tiers of the same provider."""
    if provider == "mock":
        return MockClient(model)
    if provider == "claude":
        return ClaudeClient(model=model or config.CLAUDE_MODEL)
    if provider == "gemini":
        return GeminiClient(model=model or config.GEMINI_MODEL)
    raise LLMError(f"Unknown LLM_PROVIDER '{provider}'. Use 'claude', 'gemini' or 'mock'.")
