"""Glue: question + answer -> verdict, explanation, correction, re-check -> report.

TrustGuard's flow (Priority 1 stages kept, Priority 2 stages added):

  0. Policy validation   which policy versions are in effect on the question's date
  1. Claim extraction    split Agent 1's answer into atomic claims
  2. Evidence retrieval  per claim, search policies IN EFFECT using the claim AND the question
  3. Verification        per claim: derive what the policy requires, then compare (5 steps)
  4. Completeness        from the policy side: did the answer leave out a required step?
  5. Correction          if anything is wrong or missing: an evidence-cited suggested answer
  6. Re-verification     the suggested answer is checked by A citation, B rules table, C NLI

The UI, the tests and the evaluation script all call run_pipeline / run_two_agent, so
what the judges see is exactly what the metrics measure.
"""
import time
import uuid
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache

from modules.claim_extractor import extract_claims
from modules.claim_verifier import verify_claims
from modules.completeness import check_completeness, question_evidence
from modules.correction import correction_evidence, needs_correction, suggest_correction
from modules.document_loader import load_metadata
from modules.policy_rules import coverage_check
from modules.policy_validation import PolicyContext, PolicyRegistry
from modules.reverify import reverify
from modules.schemas import CONTRADICTED, INSUFFICIENT_EVIDENCE, SUPPORTED, CompletenessResult, Correction

MAX_ANSWER_CHARS = 4000


class InputError(ValueError):
    pass


def _n(count: int, word: str = "claim") -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


@lru_cache(maxsize=1)
def default_registry() -> PolicyRegistry:
    return PolicyRegistry(load_metadata())


@dataclass
class Report:
    question: str
    answer: str
    results: list = field(default_factory=list)
    timings: dict = field(default_factory=dict)
    coverage_warnings: list = field(default_factory=list)  # facts that may have been dropped
    handoff: object = None  # AgentHandoff from Agent 1, when the answer came from the assistant
    completeness: CompletenessResult | None = None
    correction: Correction | None = None
    as_of: date | None = None
    as_of_note: str = ""
    trustguard_model: str = ""
    input_notes: list = field(default_factory=list)  # e.g. personal data masked, translated question
    turn_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])

    @property
    def counts(self) -> dict:
        c = {SUPPORTED: 0, CONTRADICTED: 0, INSUFFICIENT_EVIDENCE: 0}
        for r in self.results:
            c[r.status] += 1
        return c

    @property
    def missing(self) -> list:
        return self.completeness.missing if self.completeness else []

    @property
    def needs_review(self) -> bool:
        return bool(self.coverage_warnings) or any(r.needs_review for r in self.results)

    @property
    def overall(self) -> tuple[str, str]:
        """(level, message) — the most severe finding decides the headline, because
        one wrong fact is enough to make an answer unsafe to act on."""
        c, missing = self.counts, self.missing
        if not self.results and not missing:
            return "info", "No checkable factual claims were found in this answer."
        if c[CONTRADICTED]:
            msg = (f"Do not rely on this answer: {_n(c[CONTRADICTED])} "
                   f"{'conflicts' if c[CONTRADICTED] == 1 else 'conflict'} with the policy in effect.")
            if missing:
                msg += f" It also leaves out {_n(len(missing), 'required step')}."
            return "error", msg
        if missing:
            return "warning", (f"Incomplete answer: it leaves out {_n(len(missing), 'required step')} "
                               "that the policy requires.")
        if c[INSUFFICIENT_EVIDENCE]:
            return "warning", (f"Use with caution: {_n(c[INSUFFICIENT_EVIDENCE])} could not be verified "
                               "against the policy in effect.")
        if self.coverage_warnings:
            return "warning", ("Use with caution: every extracted claim is supported, but part of the answer "
                               "may not have been checked.")
        return "success", "Verified: every claim is supported by the policy in effect, and nothing required is missing."

    def to_dict(self) -> dict:
        level, message = self.overall
        return {"turn_id": self.turn_id, "question": self.question, "answer": self.answer, "overall": level,
                "overall_message": message, "counts": self.counts, "needs_review": self.needs_review,
                "as_of": str(self.as_of) if self.as_of else None, "as_of_note": self.as_of_note,
                "coverage_warnings": self.coverage_warnings, "input_notes": self.input_notes,
                "results": [r.to_dict() for r in self.results],
                "completeness": self.completeness.to_dict() if self.completeness else None,
                "correction": self.correction.to_dict() if self.correction else None,
                "timings": self.timings, "trustguard_model": self.trustguard_model,
                "agent1_handoff": self.handoff.to_dict() if self.handoff else None}


def validate_inputs(question: str, answer: str) -> tuple[str, str]:
    question, answer = (question or "").strip(), (answer or "").strip()
    if not answer:
        raise InputError("Please paste the AI-generated answer to verify.")
    if not question:
        raise InputError("Please enter the question the employee asked (it gives the claims context).")
    if len(answer) > MAX_ANSWER_CHARS:
        raise InputError(f"The answer is too long for this prototype (max {MAX_ANSWER_CHARS} characters).")
    return question, answer


def _noop(stage: str, data=None) -> None:
    pass


def run_pipeline(question: str, answer: str, retriever, llm, ctx: PolicyContext | None = None,
                 nli=None, on_stage=_noop, completeness: bool = True, correct: bool = True) -> Report:
    """on_stage(stage_name, data) is called as each stage finishes, so the UI can show
    live progress. Stages: policy, claims, verified, completeness, correction, reverified."""
    question, answer = validate_inputs(question, answer)
    ctx = ctx or PolicyContext.for_question(default_registry(), question)
    report = Report(question=question, answer=answer, as_of=ctx.as_of, as_of_note=ctx.as_of_note,
                    trustguard_model=getattr(llm, "model", getattr(llm, "name", "")))
    on_stage("policy", ctx)
    t = {"start": time.perf_counter()}

    claims = extract_claims(question, answer, llm)
    report.coverage_warnings = coverage_check([c.claim for c in claims], answer)
    t["extracted"] = time.perf_counter()
    on_stage("claims", claims)

    report.results = verify_claims(claims, question, retriever, llm, ctx, answer=answer) if claims else []
    t["verified"] = time.perf_counter()
    on_stage("verified", report.results)

    q_evidence = question_evidence(question, retriever, ctx)
    if completeness:
        report.completeness = check_completeness(question, answer, q_evidence, llm)
        on_stage("completeness", report.completeness)
    t["completeness"] = time.perf_counter()

    if correct and needs_correction(report.results, report.completeness):
        chunks = correction_evidence(question, report.results, q_evidence, retriever, ctx)
        report.correction = suggest_correction(question, answer, report.results, report.completeness, chunks, llm)
        t["corrected"] = time.perf_counter()
        on_stage("correction", report.correction)
        report.correction = reverify(report.correction, {c.chunk_id: c for c in retriever.chunks}, ctx, nli,
                                     question=question)
        on_stage("reverified", report.correction)
    else:
        report.correction = Correction(status="not_needed")
    t["end"] = time.perf_counter()

    report.timings = {
        "extraction_s": round(t["extracted"] - t["start"], 2),
        "verification_s": round(t["verified"] - t["extracted"], 2),
        "completeness_s": round(t["completeness"] - t["verified"], 2),
        "correction_s": round(t.get("corrected", t["completeness"]) - t["completeness"], 2),
        "reverification_s": round(t["end"] - t.get("corrected", t["end"]), 2),
        "trustguard_total_s": round(t["end"] - t["start"], 2),
    }
    return report


def run_two_agent(question: str, assistant, retriever, llm, ctx: PolicyContext | None = None,
                  nli=None, **kwargs) -> Report:
    """The full two-agent flow: employee question -> Agent 1 answers -> TrustGuard
    intercepts and verifies -> one report. TrustGuard receives only question + answer."""
    handoff = assistant.answer(question)
    if not handoff.answer:
        raise InputError("The assistant returned an empty answer. Try asking again.")
    report = run_pipeline(handoff.question, handoff.answer, retriever, llm, ctx=ctx, nli=nli, **kwargs)
    report.handoff = handoff
    report.timings = {"agent1_s": handoff.latency_s, **report.timings}
    return report


def report_from_dict(d: dict) -> Report:
    """Rebuilds a Report from Report.to_dict(), so a saved chat can be reopened. Unknown keys are
    ignored, so older saved chats still open after a field is added."""
    from dataclasses import fields as _fields

    from modules.schemas import (AgentHandoff, CompletenessResult, Correction, CorrectionSentence,
                                 RequiredElement, VerificationResult)

    def build(cls, data):
        names = {f.name for f in _fields(cls)}
        return cls(**{k: v for k, v in (data or {}).items() if k in names})

    comp = d.get("completeness")
    corr = d.get("correction")
    report = Report(
        question=d.get("question", ""), answer=d.get("answer", ""),
        results=[build(VerificationResult, r) for r in d.get("results") or []],
        timings=d.get("timings") or {}, coverage_warnings=d.get("coverage_warnings") or [],
        handoff=build(AgentHandoff, d["agent1_handoff"]) if d.get("agent1_handoff") else None,
        completeness=(CompletenessResult(checked=comp.get("checked", False), dropped=comp.get("dropped") or [],
                                         elements=[build(RequiredElement, e) for e in comp.get("elements") or []])
                      if comp else None),
        correction=(Correction(status=corr.get("status", ""), message=corr.get("message", ""),
                               reverification=corr.get("reverification", ""),
                               reverification_note=corr.get("reverification_note", ""),
                               sentences=[build(CorrectionSentence, s) for s in corr.get("sentences") or []])
                    if corr else None),
        as_of=date.fromisoformat(d["as_of"]) if d.get("as_of") else None,
        as_of_note=d.get("as_of_note", ""), trustguard_model=d.get("trustguard_model", ""),
        input_notes=d.get("input_notes") or [],
    )
    if d.get("turn_id"):
        report.turn_id = d["turn_id"]
    return report
