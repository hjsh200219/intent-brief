"""결정 축 4개 모호도 채점과 다음 질문 선택 — 결정론(모델 점수 없음).

규칙 정본: references/scoring.md
사용:
  score.py <state.json>          점수·통과·다음 질문 키를 출력
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths as P  # noqa: E402

WEIGHTS = {"ax_intent": 0.40, "ax_stance": 0.30, "ax_evidence": 0.15, "ax_procedure": 0.15}
IN_CAP = ("intent", "issue", "procedure", "contrarian")
INTENT_PASS = 0.80


def score_intent(st):
    it = st["intent"]
    if not it.get("primary"):
        return 0.0
    full = it.get("secondaries") is not None and bool(it.get("success_sentence"))
    if it["primary"] in ("M", "S") and it.get("concession") in (None, ""):
        full = False
    return 1.0 if full else 0.5


def score_stance(issue):
    st = issue.get("stance")
    if not st:
        return 0.0
    if st == "일부 인정" and issue.get("amount") is None and not issue.get("scope"):
        return 0.5
    return 1.0


def score_evidence(issue):
    if issue.get("stance") == "유보":
        return 1.0  # 이번 서면에서 언급하지 않는 쟁점은 증거 전략이 필요 없다
    ev = issue.get("evidence") or {}
    mode = ev.get("mode")
    if not mode:
        return 0.0
    if mode == "제출" and not ev.get("items"):
        return 0.5
    if mode == "제출 요구" and not ev.get("targets"):
        return 0.5
    return 1.0


def score_procedure(st):
    pr = st["procedure"]
    n = sum(1 for k in ("brief_type", "due_date", "next_hearing") if pr.get(k))
    return 1.0 if n == 3 else (0.5 if n == 2 else 0.0)


intent_signature = P.intent_signature


def _review_due(st, sc):
    """주 의도가 정해졌는데(ax_intent 통과) 지금 의도에 대한 유불리 검토가 끝나지 않았다."""
    return sc["axes"]["ax_intent"] >= INTENT_PASS and not P.review_current(st)


REVIEW_Q = {"round_type": "intent_review", "issue_id": None, "axis": "ax_intent",
            "why": "고른 의도가 소송 전체에서 유리한지 먼저 보고 그대로 갈지 정합니다"}


def cap_for(st):
    return min(10, 6 + max(0, len(st["issues"]) - 3))


def compute(st):
    issues = st["issues"]
    per_issue = {i["id"]: {"ax_stance": score_stance(i), "ax_evidence": score_evidence(i)} for i in issues}
    axes = {
        "ax_intent": score_intent(st),
        "ax_stance": min([v["ax_stance"] for v in per_issue.values()] or [0.0]),
        "ax_evidence": min([v["ax_evidence"] for v in per_issue.values()] or [0.0]),
        "ax_procedure": score_procedure(st),
    }
    ambiguity = round(1 - sum(WEIGHTS[k] * v for k, v in axes.items()), 4)
    threshold = st.get("threshold", 0.20)
    passed = ambiguity <= threshold + 1e-9 and axes["ax_intent"] >= INTENT_PASS
    with_law = sum(1 for i in issues if i.get("law_candidates"))
    rd_law = round(with_law / len(issues), 2) if issues else 0.0
    return {"axes": axes, "per_issue": per_issue, "ambiguity": ambiguity, "threshold": threshold,
            "pass": passed, "cap": cap_for(st), "rounds_in_cap": sum(1 for r in st["rounds"] if r["round_type"] in IN_CAP),
            "readiness": {"rd_law": rd_law}}


def next_question(st, sc=None):
    """다음 질문 키 (round_type, issue_id, axis). 질문 대상은 가장 낮은 (쟁점 × 결정 축)."""
    sc = sc or compute(st)
    if not st.get("round0_done"):
        return {"round_type": "round0", "issue_id": None, "axis": None, "why": "서면 종류·당사자 지위·쟁점·기한을 먼저 확인합니다"}
    if _review_due(st, sc) and st["status"] in ("interviewing", "confirming"):
        return dict(REVIEW_Q)
    if st["intent"].get("fast_path") and st.get("design_confirm_count", 0) == 0:
        return {"round_type": "design_confirm", "issue_id": None, "axis": None, "fast": True,
                "why": "빠른 경로 — 설계 확인 표 하나로 의도·쟁점 태도를 함께 정합니다"}
    if sc["pass"]:
        if st["status"] in ("interviewing", "confirming"):
            return {"round_type": "design_confirm", "issue_id": None, "axis": None, "why": "정보가 충분합니다 — 설계를 확인합니다"}
        return {"round_type": "done", "issue_id": None, "axis": None, "why": "인터뷰 완료"}
    if sc["rounds_in_cap"] >= sc["cap"]:
        if sc["axes"]["ax_intent"] < INTENT_PASS:
            if not st.get("intent_retry_done"):
                return {"round_type": "intent", "issue_id": None, "axis": "ax_intent", "retry": True,
                        "why": "질문 상한에 도달했지만 주 의도가 없어 초안을 쓸 수 없습니다 — 한 번만 더 묻습니다"}
            return {"round_type": "stop_no_intent", "issue_id": None, "axis": None,
                    "why": "주 의도가 정해지지 않아 초안을 쓰지 않고 상태만 저장합니다"}
        return {"round_type": "design_confirm", "issue_id": None, "axis": None, "early": True,
                "why": "질문 상한 도달 — 남은 빈칸은 설계 확인 표에서 기본값으로 확인합니다"}
    if sc["rounds_in_cap"] >= 3 and not st.get("contrarian_done"):
        return {"round_type": "contrarian", "issue_id": None, "axis": None, "why": "실패 시나리오를 한 번 점검합니다"}
    cands = [(sc["axes"]["ax_intent"], 0, 0, {"round_type": "intent", "issue_id": None, "axis": "ax_intent"})]
    for iid, v in sorted(sc["per_issue"].items()):
        low = min(v["ax_stance"], v["ax_evidence"])
        axis = "ax_stance" if v["ax_stance"] <= v["ax_evidence"] else "ax_evidence"
        cands.append((low, 1, iid, {"round_type": "issue", "issue_id": iid, "axis": axis}))
    cands.append((sc["axes"]["ax_procedure"], 2, 0, {"round_type": "procedure", "issue_id": None, "axis": "ax_procedure"}))
    cands = [c for c in cands if c[0] < 1.0]
    if not cands:
        return {"round_type": "design_confirm", "issue_id": None, "axis": None, "why": "모든 축이 채워졌습니다"}
    best = sorted(cands, key=lambda c: (c[0], c[1], c[2]))[0][3]
    reasons = {"intent": "주 의도·성공 판정 문장이 없어 서면 방향을 정할 수 없습니다",
               "issue": "이 쟁점의 태도·증거 전략이 정해지지 않았습니다",
               "procedure": "제출 기한·다음 기일이 확인되지 않았습니다"}
    best["why"] = reasons[best["round_type"]]
    return best


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("state")
    a = ap.parse_args(argv)
    st = P.load_json(a.state)
    sc = compute(st)
    sc["next"] = next_question(st, sc)
    sc["ok"] = True
    return P.emit(sc)


if __name__ == "__main__":
    sys.exit(main())
