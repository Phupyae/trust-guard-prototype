"""Glue: question + answer -> claims -> evidence -> verdicts -> report.

The UI talks only to this module. That keeps app.py about presentation, and lets
tests (and a future API for OCBC's agents) run the exact same pipeline the demo runs.
"""
import time
from dataclasses import dataclass, field

from modules.claim_extractor import extract_claims
from modules.claim_verifier import verify_claims
from modules.policy_rules import coverage_check
from modules.schemas import CONTRADICTED, INSUFFICIENT_EVIDENCE, SUPPORTED

MAX_ANSWER_CHARS = 4000


class InputError(ValueError):
    pass


@dataclass
class Report:
    question: str
    answer: str
    results: list = field(default_factory=list)
    timings: dict = field(default_factory=dict)
    coverage_warnings: list = field(default_factory=list)  # facts that may have been dropped

    @property
    def counts(self) -> dict:
        c = {SUPPORTED: 0, CONTRADICTED: 0, INSUFFICIENT_EVIDENCE: 0}
        for r in self.results:
            c[r.status] += 1
        return c

    @property
    def needs_review(self) -> bool:
        return bool(self.coverage_warnings) or any(r.needs_review for r in self.results)

    @property
    def overall(self) -> tuple[str, str]:
        """(level, message) — the most severe finding decides the headline, because
        one wrong fact is enough to make an answer unsafe to act on."""
        c = self.counts
        if not self.results:
            return "info", "No checkable factual claims were found in this answer."
        if c[CONTRADICTED]:
            return "error", f"Do not rely on this answer: {c[CONTRADICTED]} claim(s) conflict with approved policy."
        if c[INSUFFICIENT_EVIDENCE]:
            return "warning", f"Use with caution: {c[INSUFFICIENT_EVIDENCE]} claim(s) could not be verified."
        if self.coverage_warnings:
            return "warning", "Use with caution: every extracted claim is supported, but part of the answer may not have been checked."
        return "success", "All claims are supported by approved policy evidence."

    def to_dict(self) -> dict:
        level, message = self.overall
        return {"question": self.question, "answer": self.answer, "overall": level,
                "overall_message": message, "counts": self.counts, "needs_review": self.needs_review,
                "coverage_warnings": self.coverage_warnings,
                "results": [r.to_dict() for r in self.results], "timings": self.timings}


def validate_inputs(question: str, answer: str) -> tuple[str, str]:
    question, answer = (question or "").strip(), (answer or "").strip()
    if not answer:
        raise InputError("Please paste the AI-generated answer to verify.")
    if not question:
        raise InputError("Please enter the question the employee asked (it gives the claims context).")
    if len(answer) > MAX_ANSWER_CHARS:
        raise InputError(f"The answer is too long for this prototype (max {MAX_ANSWER_CHARS} characters).")
    return question, answer


def run_pipeline(question: str, answer: str, retriever, llm) -> Report:
    question, answer = validate_inputs(question, answer)
    report = Report(question=question, answer=answer)
    t0 = time.perf_counter()
    claims = extract_claims(question, answer, llm)
    report.coverage_warnings = coverage_check([c.claim for c in claims], answer)
    t1 = time.perf_counter()
    report.results = verify_claims(claims, question, retriever, llm) if claims else []
    t2 = time.perf_counter()
    report.timings = {"extraction_s": round(t1 - t0, 2), "verification_s": round(t2 - t1, 2)}
    return report
