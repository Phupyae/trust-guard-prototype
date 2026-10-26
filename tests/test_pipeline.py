"""Fast offline tests (no API key, no internet). Run: pytest -q"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules import policy_rules  # noqa: E402
from modules.document_loader import load_knowledge_base  # noqa: E402
from modules.evidence_retriever import EvidenceRetriever, TfidfEmbedder  # noqa: E402
from modules.llm_client import MockClient  # noqa: E402
from modules.pipeline import InputError, run_pipeline  # noqa: E402
from modules.schemas import CONTRADICTED, INSUFFICIENT_EVIDENCE, SUPPORTED, Claim, Evidence  # noqa: E402
from modules.claim_verifier import verify_claim  # noqa: E402


@pytest.fixture(scope="module")
def chunks():
    return load_knowledge_base()


@pytest.fixture(scope="module")
def retriever(chunks):
    return EvidenceRetriever(chunks, TfidfEmbedder())


# --- loader ---
def test_pdf_and_markdown_give_same_sections(chunks):
    md = load_knowledge_base(prefer="md")
    assert [(c.chunk_id, c.text) for c in chunks] == [(c.chunk_id, c.text) for c in md]


def test_section_42_is_parsed_with_citation(chunks):
    c = next(c for c in chunks if c.chunk_id == "TRAVEL_POLICY_V2::4.2")
    assert c.section_title == "Daily Allowance" and "$150 per day" in c.text


def test_superseded_policy_not_searchable(retriever):
    assert all(c.status == "Approved" for c in retriever.chunks)
    assert retriever.excluded > 0


# --- rules ---
def test_numeric_mismatch():
    result, msg = policy_rules.numeric_check("up to $200 per day", "up to $150 per day")
    assert result == "mismatch" and "$200" in msg and "$150" in msg


def test_numeric_match_and_units_kept_apart():
    assert policy_rules.numeric_check("within 30 days", "within 30 calendar days")[0] == "match"
    # "10 working days" must not be compared as plain days
    assert policy_rules.numeric_check("within 10 days", "within 10 working days")[0] == "n/a"


def test_requirement_conflict_and_double_negative():
    ev = "All claims require manager approval."
    assert policy_rules.requirement_check("All claims are automatically approved.", ev)[0] == "mismatch"
    assert policy_rules.requirement_check("No claim is approved automatically.", ev)[0] == "n/a"
    assert policy_rules.requirement_check("Receipts are not required.",
                                          "Receipts must be attached for every expense above $25.")[0] == "mismatch"


def test_quote_check():
    assert policy_rules.quote_in_passage("claim up to $150 per day", "Employees may claim up to $150 per day.")
    assert not policy_rules.quote_in_passage("claim up to $200 per day", "Employees may claim up to $150 per day.")


# --- verifier safety behaviour ---
class FixedLLM:
    def __init__(self, verdict):
        self.verdict = verdict

    def structured(self, *a, **k):
        return self.verdict


def test_rule_downgrades_wrong_supported_verdict(retriever):
    claim = Claim(1, "Employees can claim up to $200 per day for overseas travel.")
    ev = retriever.search(claim.claim)
    llm = FixedLLM({"status": SUPPORTED, "evidence_passage": 1, "evidence_quote": "", "explanation": "Looks fine."})
    r = verify_claim(claim, "q", ev, retriever.relevant(ev), llm)
    assert r.status == INSUFFICIENT_EVIDENCE and r.needs_review


def test_no_relevant_evidence_skips_llm(retriever):
    class Boom:
        def structured(self, *a, **k):
            raise AssertionError("LLM should not be called")
    claim = Claim(1, "zzz qqq")
    r = verify_claim(claim, "q", [], [], Boom())
    assert r.status == INSUFFICIENT_EVIDENCE


def test_invented_quote_is_replaced(retriever):
    claim = Claim(1, "Hotels are reimbursed up to $250 per night.")
    ev = retriever.search(claim.claim)
    llm = FixedLLM({"status": SUPPORTED, "evidence_passage": 1,
                    "evidence_quote": "This sentence does not exist.", "explanation": "ok"})
    r = verify_claim(claim, "q", ev, retriever.relevant(ev), llm)
    assert r.evidence == retriever.relevant(ev)[0].chunk.text and r.needs_review


# --- end to end (mock LLM) ---
def test_demo_scenario_end_to_end(retriever):
    # The mock extractor only splits sentences; it can't make claims self-contained
    # the way the real Claude prompt does, so the test sentence carries its own context.
    report = run_pipeline("What are the reimbursement rules for overseas business travel?",
                          "Employees can claim up to $200 per day for overseas travel. "
                          "All claims are automatically approved.",
                          retriever, MockClient())
    assert [r.status for r in report.results] == [CONTRADICTED, CONTRADICTED]
    assert report.results[0].section == "4.2"
    assert report.overall[0] == "error"


def test_gemini_client_parses_json_and_maps_errors(monkeypatch):
    """Checks our Gemini wrapper without network: the SDK call is replaced by a fake."""
    from modules.llm_client import GeminiClient, LLMError
    from google.genai import errors

    client = GeminiClient(api_key="test-key", model="test-model")
    captured = {}

    class FakeResponse:
        text = '{"claims": [{"claim": "Employees may claim up to $150 per day."}]}'

    def fake_generate(model, contents, config):
        captured["schema"] = config.response_json_schema
        captured["mime"] = config.response_mime_type
        return FakeResponse()

    monkeypatch.setattr(client.client.models, "generate_content", fake_generate)
    out = client.structured("sys", "user", "record_claims", {"type": "object"})
    assert out["claims"][0]["claim"].startswith("Employees")
    assert captured == {"schema": {"type": "object"}, "mime": "application/json"}

    def bad_key(model, contents, config):
        raise errors.ClientError(403, {"error": {"message": "API key not valid", "status": "PERMISSION_DENIED"}})

    monkeypatch.setattr(client.client.models, "generate_content", bad_key)
    with pytest.raises(LLMError, match="rejected"):
        client.structured("sys", "user", "record_claims", {"type": "object"})


# --- extraction guard ---
def test_extraction_check_numbers():
    answer = "Employees can claim up to $1,500 per trip. Claims are due within 30 days."
    assert policy_rules.extraction_check("Employees can claim up to $1,500 per trip.", answer) == []
    assert policy_rules.extraction_check("Employees can claim up to $150 per trip.", answer)  # altered
    assert policy_rules.coverage_check(["Employees can claim up to $1,500 per trip."], answer)  # 30 dropped
    assert policy_rules.coverage_check(["up to $1,500 per trip", "due within 30 days"], answer) == []


class AlteringExtractor:
    """Simulates an extractor that 'corrects' $200 to $150 and drops the deadline,
    while the judge happily agrees with the altered claim."""
    def structured(self, system, user, tool_name, schema, context=None, max_tokens=0):
        if tool_name == "record_claims":
            return {"claims": [{"claim": "Employees can claim up to $150 per day for overseas travel."}]}
        return {"status": SUPPORTED, "evidence_passage": 1, "explanation": "Matches the policy.",
                "evidence_quote": "Employees may claim up to $150 per day for eligible overseas business travel expenses."}


def test_altered_claim_cannot_be_supported(retriever):
    report = run_pipeline("What is the travel allowance?",
                          "You can claim up to $200 per day. Submit within 30 days.",
                          retriever, AlteringExtractor())
    r = report.results[0]
    assert r.status == INSUFFICIENT_EVIDENCE and r.needs_review
    assert any("Extraction check" in c and "150" in c for c in r.rule_checks)
    assert report.coverage_warnings and "200" in report.coverage_warnings[0]
    assert report.overall[0] != "success"


def test_empty_answer_rejected(retriever):
    with pytest.raises(InputError):
        run_pipeline("q", "   ", retriever, MockClient())
