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
