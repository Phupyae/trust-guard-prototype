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
    # live run, 20 Nov: the statement quoted the whole section, the missing step one sentence of it
    comp = CompletenessResult(checked=True, elements=[_el("3.2", APPROVAL_32)])
    reconcile(comp, [_res(_C, "3.2", claim="The provided documents do not specify the approval requirements.",
                          evidence=APPROVAL_32 + " The customer may collect the cash on the same day.")])
    assert comp.missing == []


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


def test_unnamed_approver_counts_as_missing_even_if_llm_said_wrong_value():
    # 20 Nov evaluation, case G: "above $30,000: Branch Manager" vs the rule naming two approvers
    rule = ("Withdrawals above $50,000 require approval from both the Branch Manager and the Branch "
            "Operations Head.")
    comp = CompletenessResult(checked=True, elements=[_el("3.3", rule, coverage="different")])
    reconcile(comp, [_res(_C, "3.3")], answer="Withdrawals above $30,000 require Branch Manager approval.")
    assert len(comp.missing) == 1 and "Branch Operations Head" in comp.missing[0].note


def test_named_approvers_with_a_wrong_amount_stay_a_wrong_value():
    rule = ("Withdrawals above $50,000 require approval from both the Branch Manager and the Branch "
            "Operations Head.")
    comp = CompletenessResult(checked=True, elements=[_el("3.3", rule, coverage="different")])
    reconcile(comp, [_res(_C, "3.3")], answer="Above $30,000 the Branch Manager and the Branch Operations Head approve.")
    assert comp.missing == []


# ---------- approver rule on cases it was not written for ----------
EXP_71 = ("Claims of up to $2,000 per trip require approval from the employee's direct manager. Claims above "
          "$2,000 per trip additionally require approval from the Department Head.")


def _el_doc(doc, section, quote, coverage="different"):
    return RequiredElement(element=quote, covered=False, coverage=coverage, source_id=doc, section=section,
                           quote=quote, essential=True)


def _res_doc(doc, status, section):
    return VerificationResult(claim_id=1, claim="x", status=status, explanation="", source_id=doc, section=section)


CASH_33 = ("Withdrawals above $50,000 require approval from both the Branch Manager and the Branch Operations "
           "Head.")


def test_other_name_for_the_operations_head_counts_as_named():
    comp = CompletenessResult(checked=True, elements=[_el("3.3", CASH_33, coverage="different")])
    reconcile(comp, [_res(_C, "3.3")], answer="Above $30,000 the Branch Manager and the Ops Head must approve.")
    assert comp.missing == []


def test_amount_dependent_approver_is_never_flagged():
    # a $500 travel claim needs only the direct manager; the section is not marked all-required
    comp = CompletenessResult(checked=True, elements=[_el_doc("TRAVEL_POLICY_V2", "7.1", EXP_71)])
    reconcile(comp, [_res_doc("TRAVEL_POLICY_V2", _C, "7.1")], answer="A $500 claim needs your line manager's approval.")
    assert comp.missing == []


def test_single_approver_section_is_never_flagged():
    comp = CompletenessResult(checked=True, elements=[_el_doc(
        "SOP_OPS_047", "3.3", "Waivers above $500 per customer require approval from the Regional Head of Branch Banking.")])
    reconcile(comp, [_res_doc("SOP_OPS_047", _C, "3.3")], answer="The Branch Manager can approve a $700 waiver.")
    assert comp.missing == []


def test_answer_naming_no_required_approver_misses_both():
    comp = CompletenessResult(checked=True, elements=[_el("3.3", CASH_33, coverage="different")])
    reconcile(comp, [_res(_C, "3.3")], answer="A supervisor must approve withdrawals above $50,000.")
    assert len(comp.missing) == 1 and "Branch Manager" in comp.missing[0].note and "Branch Operations Head" in comp.missing[0].note


def test_non_approver_sentence_in_an_all_required_section_is_not_flagged():
    notice = "The customer must give 1 business day of advance notice so that the branch can arrange the cash."
    comp = CompletenessResult(checked=True, elements=[_el("3.3", notice, coverage="different")])
    reconcile(comp, [_res(_C, "3.3")], answer="The customer can collect the cash on the same day.")
    assert comp.missing == [] and comp.wrong_values  # stays a wrong value, as before


def test_covered_answers_are_never_touched():
    comp = CompletenessResult(checked=True, elements=[_el("3.3", CASH_33, coverage="covered")])
    reconcile(comp, [_res(_C, "3.3")], answer="Something unrelated.")
    assert comp.missing == []


# ---------- a requirement and its exemption in one sentence ----------
RECEIPTS_52 = ("Original or digital receipts must be attached for every individual expense above $25. "
               "The daily allowance does not require receipts.")


def test_exemption_in_the_second_half_of_a_sentence_is_respected():
    s = ("Receipts must be attached for every individual expense above $25, but the daily allowance "
         "does not require receipts.")
    assert policy_rules.requirement_check(s, RECEIPTS_52, ["daily allowance"])[0] == "n/a"


def test_saying_no_receipts_for_any_expense_is_still_caught():
    for s in ("You don't need receipts for any expense, including the daily allowance.",
              "Receipts are not required for hotel stays, but the daily allowance does not need them either."):
        assert policy_rules.requirement_check(s, RECEIPTS_52, ["daily allowance"])[0] == "mismatch", s


def test_recheck_b_passes_the_20_nov_receipts_correction():
    from modules.reverify import check_rules, load_rules
    from modules.schemas import CorrectionSentence
    ok = CorrectionSentence(text="Receipts must be attached for every individual expense above $25, but the daily "
                                 "allowance does not require receipts.", source_id="TRAVEL_POLICY_V2", section="5.2")
    bad = CorrectionSentence(text="You don't need receipts for any expense.", source_id="TRAVEL_POLICY_V2", section="5.2")
    q = "When do I need to submit my travel claim and do I need receipts?"
    assert check_rules(ok, load_rules(), q)["result"] == "pass"
    assert check_rules(bad, load_rules(), q)["result"] == "fail"
