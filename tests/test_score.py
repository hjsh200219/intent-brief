import _paths as P
import score as SC
import state as S
from conftest import F1


def blank(n_issues=2):
    st = S.new_state(F1, "준비서면", P.load_params())
    st["issues"] = [{"id": i + 1, "title": "t%d" % i} for i in range(n_issues)]
    st["round0_done"] = True
    return st


def test_weights_and_ambiguity():
    st = blank()
    sc = SC.compute(st)
    assert sc["axes"] == {"ax_intent": 0.0, "ax_stance": 0.0, "ax_evidence": 0.0, "ax_procedure": 0.0}  # brief_type 하나뿐
    st["procedure"].update(due_date="2026-10-13")
    assert SC.compute(st)["axes"]["ax_procedure"] == 0.5
    st["procedure"].update(next_hearing="2026-09-22")
    assert SC.compute(st)["axes"]["ax_procedure"] == 1.0


def test_intent_axis():
    st = blank()
    st["intent"]["primary"] = "W"
    assert SC.score_intent(st) == 0.5
    st["intent"].update(secondaries=[], success_sentence="s")
    assert SC.score_intent(st) == 1.0
    st["intent"]["primary"] = "M"
    assert SC.score_intent(st) == 0.5  # M·S 는 양보선 필요
    st["intent"]["concession"] = "4,000만원"
    assert SC.score_intent(st) == 1.0


def test_pass_requires_intent_080():
    """ax_intent 0.7 수준(0.5)·모호도 0.15 이하라도 의도 축이 낮으면 불통과."""
    st = blank()
    st["intent"].update(primary="W")  # 0.5
    for i in st["issues"]:
        i.update(stance="다툼", evidence={"mode": "유보"})
    st["procedure"].update(due_date="x", next_hearing="y")
    sc = SC.compute(st)
    assert sc["ambiguity"] == 0.2 and sc["pass"] is False


def test_issue_scores():
    assert SC.score_stance({"stance": "일부 인정"}) == 0.5
    assert SC.score_stance({"stance": "일부 인정", "amount": 1}) == 1.0
    assert SC.score_stance({"stance": "일부 인정", "scope": "현금분"}) == 1.0
    assert SC.score_evidence({"stance": "다툼", "evidence": {"mode": "제출"}}) == 0.5
    assert SC.score_evidence({"stance": "다툼", "evidence": {"mode": "제출", "items": ["갑1"]}}) == 1.0
    assert SC.score_evidence({"stance": "유보"}) == 1.0


def test_cap():
    assert SC.cap_for(blank(2)) == 6
    assert SC.cap_for(blank(5)) == 8
    assert SC.cap_for(blank(12)) == 10


def test_next_order_and_outside_cap_rounds():
    st = blank()
    st["round0_done"] = False
    assert SC.next_question(st)["round_type"] == "round0"
    st["round0_done"] = True
    assert SC.next_question(st)["round_type"] == "intent"
    # round0·conflict·design_confirm 은 상한 밖
    st["rounds"] = [{"round_type": t} for t in ("round0", "conflict", "conflict", "design_confirm")]
    assert SC.compute(st)["rounds_in_cap"] == 0


def test_contrarian_after_three():
    st = blank()
    st["intent"].update(primary="W", secondaries=[], success_sentence="s")
    st["rounds"] = [{"round_type": "intent"}, {"round_type": "issue"}, {"round_type": "issue"}]
    reviewed(st)
    assert SC.next_question(st)["round_type"] == "contrarian"


def test_cap_reached_without_intent_then_stop():
    st = blank()
    st["rounds"] = [{"round_type": "issue"}] * 6
    st["contrarian_done"] = True
    n = SC.next_question(st)
    assert n["round_type"] == "intent" and n.get("retry")
    st["intent_retry_done"] = True
    assert SC.next_question(st)["round_type"] == "stop_no_intent"


def test_pass_goes_to_design_confirm_then_done():
    st = blank()
    st["intent"].update(primary="W", secondaries=[], success_sentence="s")
    for i in st["issues"]:
        i.update(stance="다툼", evidence={"mode": "유보"})
    st["procedure"].update(due_date="x", next_hearing="y")
    reviewed(st)
    assert SC.next_question(st)["round_type"] == "design_confirm"
    st["status"] = "designed"
    assert SC.next_question(st)["round_type"] == "done"


def test_fast_path():
    st = blank()
    st["intent"]["fast_path"] = True
    assert SC.next_question(st)["round_type"] == "design_confirm"


def test_weakest_issue_chosen():
    st = blank(3)
    st["intent"].update(primary="W", secondaries=[], success_sentence="s")
    st["issues"][0].update(stance="다툼", evidence={"mode": "유보"})
    st["issues"][1].update(stance="다툼")
    reviewed(st)
    n = SC.next_question(st)
    assert (n["round_type"], n["issue_id"], n["axis"]) == ("issue", 2, "ax_evidence")


# ── 의도 유불리 검토 (intent_review) ─────────────────────────
def reviewed(st, decision="진행"):
    st["intent_review"] = {"for": SC.intent_signature(st["intent"]), "verdict": "조건부",
                           "gains": ["g"], "forgoes": ["f"], "alternatives": [], "decision": decision}
    return st


def full(st):
    st["intent"].update(primary="W", secondaries=[], success_sentence="s")
    for i in st["issues"]:
        i.update(stance="다툼", evidence={"mode": "유보"})
    st["procedure"].update(due_date="x", next_hearing="y")
    return st


def test_review_fires_right_after_intent_fixed():
    st = blank()
    st["intent"].update(primary="W", secondaries=[], success_sentence="s")
    n = SC.next_question(st)
    assert n["round_type"] == "intent_review"
    reviewed(st)
    assert SC.next_question(st)["round_type"] == "issue"


def test_review_not_before_intent():
    st = blank()
    st["intent"]["primary"] = "W"  # 부 의도·성공 문장 없음 → ax_intent 0.5
    assert SC.next_question(st)["round_type"] != "intent_review"


def test_review_before_design_confirm_and_once():
    st = full(blank())
    assert SC.next_question(st)["round_type"] == "intent_review"
    reviewed(st)
    assert SC.next_question(st)["round_type"] == "design_confirm"


def test_review_again_when_intent_changed():
    st = reviewed(full(blank()))
    st["intent"]["primary"] = "S"
    st["intent"]["concession"] = "1,000만원"
    assert SC.next_question(st)["round_type"] == "intent_review"


def test_review_decision_change_is_not_done():
    st = reviewed(full(blank()), decision="변경")
    assert SC.next_question(st)["round_type"] == "intent_review"


def test_review_on_cap_early_exit():
    st = blank()
    st["intent"].update(primary="W", secondaries=[], success_sentence="s")
    st["rounds"] = [{"round_type": "issue"}] * SC.cap_for(st)
    st["contrarian_done"] = True
    assert SC.next_question(st)["round_type"] == "intent_review"
    reviewed(st)
    assert SC.next_question(st)["round_type"] == "design_confirm"


def test_review_on_fast_path():
    st = blank()
    st["intent"]["fast_path"] = True
    assert SC.next_question(st)["round_type"] == "design_confirm"  # 의도가 없으면 표에서 먼저 정한다
    st["intent"].update(primary="W", secondaries=[], success_sentence="s")
    assert SC.next_question(st)["round_type"] == "intent_review"
    st["design_confirm_count"] = 1
    st["status"] = "confirming"
    full(st)
    reviewed(st)
    assert SC.next_question(st)["round_type"] == "design_confirm"
