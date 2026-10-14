import copy
import itertools

import pytest

import _paths as P
import intent as I
import state as S
from conftest import F1, F2, F1_BASE

KEYS = ["W", "M", "S", "P", "R", "A", "C"]
PRIMARIES = ["W", "M", "S", "P", "R", "A"]


def st_for(side="원고", primary="W", secs=(), issues=None, claim=50000000, flags=None, brief="준비서면", **extra):
    st = S.new_state(F1, brief, P.load_params())
    st["side"] = side
    st["claim_amount"] = claim
    st["issues"] = copy.deepcopy(issues if issues is not None else
                                 [{"id": 1, "title": "성립", "stance": "다툼"}, {"id": 2, "title": "변제", "stance": "다툼"}])
    st["intent"].update(primary=primary, secondaries=list(secs), success_sentence="s", concession="4,000만원")
    if flags:
        st["flags"].update(flags)
    st.update(extra)
    return st


ADMIT2 = [{"id": 1, "title": "성립", "stance": "다툼"}, {"id": 2, "title": "변제", "stance": "일부 인정", "amount": 10000000}]


@pytest.mark.parametrize("intent,err", [
    ({"primary": None}, "주 의도가 선택되지 않았습니다"),
    ({"primary": "C"}, "부 의도로만"),
    ({"primary": "W", "secondaries": ["M", "S", "A"]}, "최대 2개"),
    ({"primary": "W", "secondaries": ["M", "M"]}, "중복"),
    ({"primary": "W", "secondaries": ["W"]}, "중복"),
    ({"primary": "X"}, "목록에 없습니다"),
])
def test_validate_selection_errors(params, intent, err):
    with pytest.raises(P.BriefError, match=err):
        I.validate_selection(intent, params)


def test_no_default_primary(params):
    """주 의도 없이 해석·작성으로 가는 경로가 없다 — 「전부 승소」로 채우지 않는다."""
    st = st_for()
    st["intent"]["primary"] = None
    with pytest.raises(P.BriefError):
        I.resolve(st, params)


def test_w_plaintiff_full(params):
    d = I.resolve(st_for(), params)
    assert d["conclusion"]["text"] == "원고의 청구금액 5,000만원 전부를 인용하여 주시기 바랍니다"
    assert d["todo"] == []


def test_w_defendant(params):
    d = I.resolve(st_for(side="피고", brief="답변서"), params)
    assert d["conclusion"]["text"] == "원고의 청구를 기각하여 주시기 바랍니다"
    assert "sec.claim_answer" in [s["id"] for s in d["sections"]]


def test_m_plaintiff_deduct(params):
    d = I.resolve(st_for(primary="M", issues=ADMIT2), params)
    ids = [s["id"] for s in d["sections"]]
    assert "sec.alt_claim" not in ids
    t = d["conclusion"]["text"]
    assert "인정한 1,000만원을 공제한 나머지 4,000만원을 인용" in t
    assert "전부" not in t and "예비적" not in t
    assert [x["key"] for x in d["todo"]] == ["claim_reduction_optional"]
    assert "4,000만원으로 감축" in d["todo"][0]["text"]


def test_m_plaintiff_scope_only(params):
    issues = [{"id": 1, "title": "성립", "stance": "다툼"}, {"id": 2, "title": "변제", "stance": "일부 인정", "scope": "현금 변제분"}]
    d = I.resolve(st_for(primary="M", issues=issues), params)
    assert "인정한 부분([확인 필요: 인정액])을 공제한 나머지를 인용" in d["conclusion"]["text"]
    assert "[확인 필요: 인정액]" in d["todo"][0]["text"]


def test_m_plaintiff_no_claim_amount(params):
    d = I.resolve(st_for(primary="M", issues=ADMIT2, claim=None), params)
    assert "나머지([확인 필요: 청구금액])" in d["conclusion"]["text"]
    assert "[확인 필요: 청구금액]" in d["todo"][0]["text"]
    d2 = I.resolve(st_for(primary="W", claim=None), params)
    assert "[확인 필요: 청구금액] 전부" in d2["conclusion"]["text"]


def test_remaining_not_positive_blocks(params):
    issues = [{"id": 1, "title": "x", "stance": "인정", "amount": 50000000}]
    with pytest.raises(I.NeedInput) as e:
        I.resolve(st_for(primary="M", issues=issues), params)
    assert e.value.needs[0]["key"] == "design.amounts"


def test_m_plaintiff_alt_cause(params):
    d = I.resolve(st_for(primary="M", issues=ADMIT2, flags={"alt_cause": "부당이득반환"}), params)
    assert "sec.alt_claim" in [s["id"] for s in d["sections"]]
    keys = [x["key"] for x in d["todo"]]
    assert keys == ["claim_reduction_optional", "claim_change_required"]
    assert "부당이득반환" in d["todo"][1]["text"]


def test_w_plaintiff_alt_cause_omitted(params):
    d = I.resolve(st_for(primary="W", flags={"alt_cause": "부당이득반환"}), params)
    assert "sec.alt_claim" not in [s["id"] for s in d["sections"]]
    assert any(o["id"] == "sec.alt_claim" for o in d["omitted"])


def test_m_defendant(params):
    d = I.resolve(st_for(side="피고", primary="M", issues=ADMIT2, flags={"reduction_reasons": ["변제 1,000만원 공제"]}), params)
    ids = [s["id"] for s in d["sections"]]
    assert "sec.alt_claim" in ids and "sec.admitted_facts" in ids
    t = d["conclusion"]["text"]
    for tok in ("주위적", "청구를 기각", "예비적", "일부 기각"):
        assert tok in t


def test_s_plus_m_plaintiff_e5(params):
    """E5 F1-B 와 같은 문자열 경로."""
    d = I.resolve(st_for(primary="S", secs=["M"], issues=ADMIT2, flags={"settle_will": True}), params)
    t = d["conclusion"]["text"]
    assert t.startswith("이 사건을 조정에 회부하거나 화해권고결정을 하여 주실 것을 희망하며, 조정이 성립하지 않을 경우 ")
    assert "인정한 1,000만원을 공제한 나머지 4,000만원을 인용" in t
    for bad in ("전부", "모두", "예비적"):
        assert bad not in t
    ids = [s["id"] for s in d["sections"]]
    assert "sec.settle_opinion" in ids and "sec.admitted_facts" in ids and "sec.rebuttal_all" not in ids
    assert [x["key"] for x in d["todo"]] == ["claim_reduction_optional"]


def test_s_defendant(params):
    d = I.resolve(st_for(side="피고", primary="S", flags={"settle_will": True}), params)
    assert d["conclusion"]["text"].endswith("조정이 성립하지 않을 경우 원고의 청구를 기각하여 주시기 바랍니다")


def test_w_plaintiff_with_admission_uses_deduct(params):
    """금액 수정자 — 주 의도가 W 라도 일부 인정이 있으면 공제 문구(자백과 결론의 모순 방지)."""
    d = I.resolve(st_for(primary="W", issues=ADMIT2), params)
    assert "공제한 나머지 4,000만원" in d["conclusion"]["text"]


def test_w_plus_m_requires_all_stances(params):
    issues = [{"id": 1, "title": "x", "stance": "다툼"}, {"id": 2, "title": "y"}]
    with pytest.raises(I.NeedInput) as e:
        I.resolve(st_for(primary="W", secs=["M"], issues=issues), params)
    assert e.value.needs[0]["key"] == "conflict.W+M"


def test_w_plus_s_addendum_only(params):
    d = I.resolve(st_for(primary="W", secs=["S"], flags={"settle_will": True}), params)
    ids = [s["id"] for s in d["sections"]]
    assert "sec.settle_opinion" not in ids
    assert d["addenda"] and "조정" in d["conclusion"]["text"]


def test_w_plus_a(params):
    d = I.resolve(st_for(primary="W", secs=["A"]), params)
    ids = [s["id"] for s in d["sections"]]
    assert "sec.alt_claim" not in ids and "sec.procedural_objection" not in ids  # 절차 이의는 근거(procedural_issue) 있을 때만
    d2 = I.resolve(st_for(primary="W", secs=["A"], flags={"procedural_issue": "기일 통지 누락"}), params)
    assert "sec.procedural_objection" in [s["id"] for s in d2["sections"]]
    assert "원용" in d2["conclusion"]["text"]


def test_a_plus_m_no_admission_omits_admitted_facts(params):
    d = I.resolve(st_for(primary="A", secs=["M"]), params)
    assert "sec.admitted_facts" not in [s["id"] for s in d["sections"]]
    assert any(o["id"] == "sec.admitted_facts" and "근거 없음" in o["reason"] for o in d["omitted"])


def test_a_plus_s_without_settle_will(params):
    st = st_for(primary="A", secs=["S"])
    st["intent"]["concession"] = None
    d = I.resolve(st, params)
    assert "sec.settle_opinion" not in [s["id"] for s in d["sections"]]


def test_r_plus_a_substitute(params):
    d = I.resolve(st_for(primary="R", secs=["A"]), params)
    ids = [s["id"] for s in d["sections"]]
    assert "sec.rebuttal_all" not in ids and "sec.other_claims" in ids


def test_p_plus_a_asks_withheld(params):
    with pytest.raises(I.NeedInput) as e:
        I.resolve(st_for(primary="P", secs=["A"]), params)
    assert "withheld_evidence" in e.value.needs[0]["key"]
    st = st_for(primary="P", secs=["A"])
    st["conflict_answers"]["withheld_evidence"] = ["갑3"]
    assert I.resolve(st, params)["withheld_evidence"] == ["갑3"]


def test_s_plus_w_core_strength(params):
    d = I.resolve(st_for(primary="S", secs=["W"], flags={"settle_will": True}), params)
    assert d["strength"]["level"] == "핵심 쟁점만 단정" and d["strength"]["source"] == "conflict_rule"


def test_overrides(params):
    st = st_for(primary="S", flags={"settle_will": True})
    st["overrides"] = [{"cell": "strength", "value": "강"}, {"cell": "sections.add", "value": ["sec.law"]},
                       {"cell": "addenda", "value": "삭제"}]
    d = I.resolve(st, params)
    assert d["strength"] == {"level": "강", "desc": params["strength_levels"]["강"], "source": "override"}
    assert any(s["id"] == "sec.law" and s["source"] == "override" for s in d["sections"])
    with pytest.raises(P.BriefError):
        st["overrides"] = [{"cell": "sections.remove", "value": ["sec.conclusion"]}]
        I.resolve(st, params)


def test_client_report_secondary(params):
    d = I.resolve(st_for(primary="W", secs=["C"]), params)
    assert d["client_report"] is True


def test_answer_brief_only_defendant(params):
    with pytest.raises(P.BriefError):
        I.resolve(st_for(side="원고", brief="답변서"), params)


def _all_pairs():
    for p in PRIMARIES:
        for s in KEYS:
            if s != p:
                yield p, s


@pytest.mark.parametrize("side", ["원고", "피고"])
@pytest.mark.parametrize("basis", [True, False])
def test_no_empty_sections_all_pairs(params, side, basis):
    """36 순서쌍 × side × 근거 유무 — 결과 섹션은 고정·주 의도·근거 충족 출신뿐(빈 섹션 0), 결론 = 주 결론 + 부 addendum."""
    for p, s in _all_pairs():
        issues = ADMIT2 if basis else [{"id": 1, "title": "성립", "stance": "다툼"}, {"id": 2, "title": "변제", "stance": "다툼"}]
        flags = {"settle_will": True, "doc_targets": ["통장"], "alt_cause": None,
                 "reduction_reasons": ["공제"], "procedural_issue": "x"} if basis else {}
        st = st_for(side=side, primary=p, secs=[s], issues=issues, flags=flags)
        if not basis:
            st["intent"]["concession"] = None
        st["conflict_answers"]["withheld_evidence"] = []
        d = I.resolve(st, params)
        for sec in d["sections"]:
            src = sec["source"]
            if src.startswith("secondary:"):
                b = I.section_basis(sec["id"], side, params)
                assert I.basis_ok(b, st), (p, s, side, sec)
        base_t = params["defaults"]["%s|%s" % (p, side)]["conclusion_template"].split("{")[0]
        assert d["conclusion"]["text"].startswith(base_t), (p, s)
        for a in d["addenda"]:
            assert d["conclusion"]["text"].endswith(a["text"]) or a["text"] in d["conclusion"]["text"]


def test_write_design_and_status(home, case, params):
    c = case(F1)
    path, st = __import__("conftest").make_state(c, **F1_BASE)
    st = P.load_json(path)
    st["intent"].update(primary="W", secondaries=[], success_sentence="s")
    st["issues"] = [{"id": 1, "title": "a", "stance": "다툼"}, {"id": 2, "title": "b", "stance": "다툼"}]
    S.save(path, st)
    assert I.main(["resolve", path, "--write"]) == 2  # interviewing → designed 직행 금지
    st = P.load_json(path)
    S.set_status(st, "confirming")
    S.save(path, st)
    assert I.main(["resolve", path, "--write"]) == 0
    st = P.load_json(path)
    assert st["status"] == "designed" and st["design_path"].endswith("준비서면_design.json")
