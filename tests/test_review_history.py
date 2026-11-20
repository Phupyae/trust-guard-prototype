"""Chat history (save / reopen) and showing an earlier review decision, on temporary log folders."""
from modules import chat_history, review_queue
from modules.pipeline import Report, report_from_dict
from modules.schemas import (CompletenessResult, Correction, CorrectionSentence, RequiredElement,
                             VerificationResult)


def _report(status="CONTRADICTED", cause="This claim matches X version 2.1 ... most likely used an outdated version"):
    r = Report(question="Who approves an $80,000 withdrawal?", answer="The Branch Manager.")
    r.results = [VerificationResult(claim_id=1, claim="The Branch Manager approves.", status=status,
                                    explanation="", source_title="Cash Withdrawal SOP", section="3.3",
                                    version="3.0", root_cause=cause)]
    r.completeness = CompletenessResult(checked=True, elements=[RequiredElement(element="Operations Head sign-off",
                                                                                 covered=False, coverage="absent")])
    r.correction = Correction(status="suggested", sentences=[CorrectionSentence(text="Manager and Ops Head.")])
    return r


def test_report_round_trip_keeps_verdict():
    r = _report()
    back = report_from_dict(r.to_dict())
    assert back.overall == r.overall and back.turn_id == r.turn_id
    assert back.results[0].source_title == "Cash Withdrawal SOP" and back.missing[0].element == "Operations Head sign-off"
    assert back.correction.text == "Manager and Ops Head."


def test_chat_is_saved_and_reopened(tmp_path):
    cid = chat_history.new_id()
    turns = [{"kind": "report", "question": "Q1", "report": _report()},
             {"kind": "reply", "question": "hi", "reply": "Hello", "guard": False, "note": ""}]
    chat_history.save(cid, turns, tmp_path)
    listed = chat_history.list_chats(tmp_path)
    assert listed[0]["id"] == cid and listed[0]["questions"] == 2 and listed[0]["title"] == "Q1"
    back = chat_history.load(cid, tmp_path)
    assert back[0]["report"].overall == turns[0]["report"].overall and back[1]["reply"] == "Hello"


def test_chat_id_cannot_escape_the_folder(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        chat_history.load("../../config", tmp_path)


def test_same_question_later_sees_the_earlier_decision(tmp_path):
    r = _report()
    case = review_queue.request(r, "error", tmp_path)
    review_queue.decide(case, "corrected", answer="Manager and Ops Head.", log_dir=tmp_path)
    later = review_queue.earlier_decision("who approves an $80,000 withdrawal", "other-turn", tmp_path)
    assert later and later["case_id"] == case
    assert review_queue.earlier_decision("Who approves a $5,000 withdrawal?", "other-turn", tmp_path) is None


# ---------- missing steps: rule-based clean-up (completeness.reconcile) ----------
from modules.completeness import reconcile
from modules.schemas import SUPPORTED, CONTRADICTED as _C

SOP = "SOP_OPS_021_V3_0"
APPROVAL_32 = "Withdrawals above $20,000 and up to $50,000 require Branch Manager approval."


def _el(section, quote, coverage="absent", essential=True):
    return RequiredElement(element=quote, covered=coverage == "covered", coverage=coverage, source_id=SOP,
                           section=section, quote=quote, essential=essential)


def _res(status, section, claim="x", evidence=""):
    return VerificationResult(claim_id=1, claim=claim, status=status, explanation="", source_id=SOP,
                              section=section, evidence=evidence)


def test_step_from_another_chapter_is_extra_detail_not_a_warning():
    # "Who approves $80,000?" -> answer checked against 3.3 (approval limits); 4.2 is purpose recording
    comp = CompletenessResult(checked=True, elements=[
        _el("3.3", "The customer must give 1 business day of advance notice."),
        _el("4.2", "For withdrawals above $20,000, the teller must ask for and record the purpose.")])
    reconcile(comp, [_res(SUPPORTED, "3.3")])
    assert [e.section for e in comp.missing] == ["3.3"]          # notice still flagged
    assert not comp.elements[1].essential                         # paperwork step kept as detail


def test_neighbouring_section_in_same_chapter_still_counts():
    # fee waiver: answer cites 3.1 (CSO), the missing Branch Manager rule is 3.2 -> still missing
    comp = CompletenessResult(checked=True, elements=[_el("3.2", "Waivers above $50 require Branch Manager approval.")])
    reconcile(comp, [_res(_C, "3.1")])
    assert len(comp.missing) == 1


def test_denied_rule_is_not_counted_twice():
    comp = CompletenessResult(checked=True, elements=[_el("3.2", APPROVAL_32)])
    reconcile(comp, [_res(_C, "3.2", claim="The documents do not specify the approval requirements for "
                                            "withdrawals between $20,001 and $50,000.", evidence=APPROVAL_32)])
    assert comp.missing == [] and comp.elements[0].coverage == "different"


def test_no_cited_section_keeps_the_llm_judgement():
    comp = CompletenessResult(checked=True, elements=[_el("4.2", "Record the purpose.")])
    reconcile(comp, [VerificationResult(claim_id=1, claim="x", status="INSUFFICIENT_EVIDENCE", explanation="")])
    assert len(comp.missing) == 1


def test_denial_answer_always_becomes_a_statement():
    from modules.pipeline import with_denial_claims
    ans = ("The provided documents do not specify the approval requirements for withdrawals between $20,001 "
           "and $50,000. You should consult your branch supervisor for guidance on transactions in this range.")
    claims = with_denial_claims([], ans)
    assert len(claims) == 1 and claims[0].claim.startswith("The provided documents do not specify")
    # already extracted -> not added twice
    assert len(with_denial_claims(claims, ans)) == 1
    # ordinary answers are untouched
    assert with_denial_claims([], "Withdrawals above $50,000 need two approvals.") == []


# ---------- "cannot" + an amount above the limit agrees with the policy ----------
from modules import policy_rules

FEE_31 = "A Customer Service Officer may waive fees of up to $50 per customer in any 12-month period."
Q300 = "Can a Customer Service Officer waive a $300 fee for a customer?"


def test_cannot_waive_amount_above_limit_is_not_a_number_conflict():
    ignore = policy_rules.negated_amounts_outside_band(Q300, "A Customer Service Officer cannot waive a $300 fee.", FEE_31)
    assert ignore == {"money": {300.0}}
    result, _ = policy_rules.numeric_check("A Customer Service Officer cannot waive a $300 fee.", FEE_31, ignore=ignore)
    assert result != "mismatch"


def test_can_waive_amount_above_limit_is_still_a_conflict():
    claim = "A Customer Service Officer can waive a $300 fee."
    assert policy_rules.negated_amounts_outside_band(Q300, claim, FEE_31) == {}
    assert policy_rules.numeric_check(claim, FEE_31, ignore={})[0] == "mismatch"


def test_cannot_with_amount_inside_limit_is_still_compared():
    # $30 is inside "up to $50", so "cannot waive $30" is wrong and must not be waved through
    q = "Can a Customer Service Officer waive a $30 fee?"
    assert policy_rules.negated_amounts_outside_band(q, "A CSO cannot waive a $30 fee.", FEE_31) == {}
