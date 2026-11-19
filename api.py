"""TrustGuard API: the front door other AI assistants use to have their answers checked.

TrustGuard is a layer, not a chatbot. Any assistant (the bank's existing staff chatbot, a vendor
tool, our demo Agent 1) sends the employee's question and the answer it is about to show; TrustGuard
runs the SAME checks as the demo app (modules/pipeline.run_pipeline) and returns a verdict, what is
wrong, what is missing and a suggested correction, as JSON.

    Run:   uvicorn api:app --port 8000
    Open:  http://localhost:8000        test page ("another assistant" calling TrustGuard)
           http://localhost:8000/docs   interactive API documentation

Security for the prototype:
  - Binds to localhost by default (uvicorn's default host is 127.0.0.1).
  - If TRUSTGUARD_API_KEY is set in .env, every /verify call must send it in the X-API-Key header.
  - Same input protection as the chat: length limits, prompt-injection check on the question AND
    the answer, personal data masked before anything reaches the LLM or the logs, rate limit per caller.
  - Errors never return stack traces.
Every call is logged like a chat check (mode "api"), so it feeds the review queue and Improvements page.
In production this would sit behind the bank's API gateway and single sign-on instead.
"""
from __future__ import annotations

import hmac
import os
import re
from datetime import date
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

import config
from modules import event_log
from modules.document_loader import load_knowledge_base
from modules.evidence_retriever import EvidenceRetriever, make_embedder
from modules.input_guard import INJECTION_PATTERNS, RateLimiter, mask_pii, screen
from modules.llm_client import LLMError, get_client
from modules.nli import NLIChecker
from modules.pipeline import MAX_ANSWER_CHARS, InputError, Report, default_registry, run_pipeline
from modules.policy_validation import PolicyContext
from modules.schemas import CONTRADICTED, INSUFFICIENT_EVIDENCE

app = FastAPI(
    title="TrustGuard API",
    version="1.0",
    description="Send an employee's question and an AI assistant's answer; get back whether the answer matches "
                "the SOP version in effect, what is wrong or missing, and a suggested correction. "
                "All policy documents are synthetic (Northbridge Bank), not OCBC policy.",
)


# ---------- the request and the response ----------
class VerifyRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=config.MAX_QUESTION_CHARS,
                          description="What the employee asked.",
                          examples=["A customer wants to withdraw $80,000 in cash today. Who needs to approve it?"])
    answer: str = Field(..., min_length=1, max_length=MAX_ANSWER_CHARS,
                        description="The answer the assistant is about to show the employee.",
                        examples=["Withdrawals above $30,000 require Branch Manager approval."])
    assistant: str = Field("external assistant", max_length=60,
                           description="Name of the calling assistant, for the audit log.")
    as_of: date | None = Field(None, description="Check against the SOPs in effect on this date (default: today, "
                                                 "or a date mentioned in the question).")


class Statement(BaseModel):
    statement: str
    status: str = Field(description="matches | does_not_match | cannot_confirm")
    sop: str = Field(description="SOP document, version and section used")
    sop_says: str
    why: str
    likely_cause: str = ""


class VerifyResponse(BaseModel):
    check_id: str
    verdict: str = Field(description="matches_sop | use_with_care | incomplete | do_not_use | nothing_to_check")
    headline: str
    safe_to_use: bool = Field(description="True only when every statement matches and nothing required is missing")
    needs_human_review: bool
    statements: list[Statement]
    missing_steps: list[str]
    suggested_answer: str | None
    suggested_answer_rechecked: str = Field(description="confirmed | partially_confirmed | not_confirmed | ''")
    policy_date: str | None
    checked_in_seconds: float


STATUS = {"SUPPORTED": "matches", CONTRADICTED: "does_not_match", INSUFFICIENT_EVIDENCE: "cannot_confirm"}
HEADLINES = {"do_not_use": "Don't use this answer", "incomplete": "Incomplete answer", "use_with_care": "Use with care",
             "matches_sop": "Matches the current SOP", "nothing_to_check": "Nothing to check"}


def verdict_of(report: Report) -> str:
    """Same severity order as the chat: the most serious finding decides."""
    level, _ = report.overall
    if level == "info":
        return "nothing_to_check"
    if report.counts[CONTRADICTED]:
        return "do_not_use"
    if report.missing:
        return "incomplete"
    if level == "warning" or report.needs_review:
        return "use_with_care"
    return "matches_sop"


def to_response(report: Report) -> VerifyResponse:
    v = verdict_of(report)
    corr = report.correction
    suggested = corr.text if corr and corr.status == "suggested" and corr.text else None
    return VerifyResponse(
        check_id=report.turn_id, verdict=v, headline=HEADLINES[v], safe_to_use=v == "matches_sop",
        needs_human_review=report.needs_review or v != "matches_sop" and v != "nothing_to_check",
        statements=[Statement(statement=r.claim, status=STATUS.get(r.status, r.status),
                              sop=f"{r.source_title} v{r.version} §{r.section}".strip() if r.source_title else "",
                              sop_says=r.evidence, why=r.explanation, likely_cause=r.root_cause)
                    for r in report.results],
        missing_steps=[e.element for e in report.missing],
        suggested_answer=suggested,
        suggested_answer_rechecked=(corr.reverification if suggested else "") or "",
        policy_date=str(report.as_of) if report.as_of else None,
        checked_in_seconds=report.timings.get("trustguard_total_s", 0.0),
    )


# ---------- TrustGuard's parts, loaded once ----------
class Engine:
    def __init__(self, retriever, llm, nli=None):
        self.retriever, self.llm, self.nli = retriever, llm, nli

    def check(self, question: str, answer: str, as_of: date | None) -> Report:
        ctx = PolicyContext.for_question(default_registry(), question, today=as_of)
        return run_pipeline(question, answer, self.retriever, self.llm, ctx=ctx, nli=self.nli)


@lru_cache(maxsize=1)
def engine() -> Engine:
    embedder, _ = make_embedder()
    return Engine(EvidenceRetriever(load_knowledge_base(), embedder), get_client(), NLIChecker())


# ---------- security ----------
_limiters: dict[str, RateLimiter] = {}


def caller(request: Request, x_api_key: str | None = Header(None, description="Required if TRUSTGUARD_API_KEY is set")) -> str:
    expected = os.getenv("TRUSTGUARD_API_KEY", "")
    if expected and not (x_api_key and hmac.compare_digest(x_api_key, expected)):
        raise HTTPException(401, "Missing or wrong API key (X-API-Key header).")
    return "key" if expected else (request.client.host if request.client else "local")


def _injection(text: str) -> bool:
    return any(re.search(p, text, re.I) for p in INJECTION_PATTERNS)


# ---------- endpoints ----------
@app.get("/health", summary="Is TrustGuard up?")
def health() -> dict:
    return {"status": "ok", "llm_provider": config.LLM_PROVIDER}


@app.post("/verify", response_model=VerifyResponse, summary="Check an assistant's answer against the SOP in effect",
          responses={401: {"description": "Wrong API key"}, 422: {"description": "Input rejected"},
                     429: {"description": "Too many requests"}, 503: {"description": "Model unavailable"}})
def verify(req: VerifyRequest, who: str = Depends(caller), eng: Engine = Depends(engine)) -> VerifyResponse:
    q = screen(req.question)
    if not q.ok:
        raise HTTPException(422, q.message)
    if _injection(req.answer):
        raise HTTPException(422, "The answer contains text that tries to change how TrustGuard works, so it was "
                                 "not checked.")
    answer, _ = mask_pii(req.answer)
    limited = _limiters.setdefault(who, RateLimiter()).check(q.text + answer)
    if limited:
        raise HTTPException(429, limited.message)
    try:
        report = eng.check(q.text, answer, req.as_of)
    except InputError as e:
        raise HTTPException(422, str(e)) from e
    except LLMError as e:
        event_log.log_error("api", e, q.text)
        raise HTTPException(503, f"Verification unavailable: {e} Don't rely on the answer.") from e
    except Exception as e:  # never leak a traceback to the caller
        event_log.log_error("api", e, q.text)
        raise HTTPException(500, "TrustGuard couldn't check this answer. Don't rely on it.") from e
    report.input_notes = [q.message] if q.message else []
    event_log.log_report(report, mode=f"api:{req.assistant}")
    return to_response(report)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def test_page() -> str:
    return (Path(__file__).parent / "docs" / "api_test_page.html").read_text(encoding="utf-8")
