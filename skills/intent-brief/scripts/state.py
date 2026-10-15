"""인터뷰 상태 — 라운드마다 원자 저장, 재개, 해시 비교, purge.

사용:
  state.py init  <사건폴더> --brief 준비서면|답변서
  state.py show  <state.json>
  state.py apply <state.json> (--json '<JSON>' | --json-file <파일>)
  state.py set-status <state.json> <status>
  state.py purge <사건폴더> | --all
"""
import argparse
import copy
import datetime
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths as P  # noqa: E402

STATUSES = ["interviewing", "confirming", "designed", "drafted", "recorded", "stopped"]
# 허용 전이 — interviewing → designed 직행은 없다(설계 확인 라운드를 반드시 거친다)
TRANSITIONS = {
    "interviewing": {"confirming", "stopped"},
    "confirming": {"interviewing", "designed", "stopped"},
    "designed": {"confirming", "drafted"},
    "drafted": {"drafted", "recorded", "confirming"},
    "recorded": {"drafted", "confirming"},
    "stopped": {"interviewing"},
}
ROUND_TYPES = ["round0", "intent", "intent_review", "issue", "procedure", "contrarian", "conflict", "design_confirm"]
INSTANCES = ["1심", "항소심"]
REVIEW_VERDICTS = ["유리", "조건부", "불리"]
REVIEW_DECISIONS = ["진행", "변경"]
REVIEW_LISTS = ("gains", "forgoes", "alternatives")
EVIDENCE_MODES = ["제출", "유보", "제출 요구"]


def state_path(case_dir, brief_type):
    d = P.case_work_dir(case_dir)
    return os.path.join(d, "%s_state.json" % brief_type)


_OWN_OUTPUT = re.compile(r"(^내부_|_v\d+\.docx$)")


def _attachments(case_dir):
    """사건 폴더의 첨부 해시 — 사건메모와 이 스킬이 만든 초안·대응표는 뺀다."""
    out = {}
    for n in sorted(os.listdir(case_dir)):
        full = os.path.join(case_dir, n)
        name = P.nfc(n)
        if (os.path.isfile(full) and not n.startswith((".", "~$")) and name != P.MEMO_NAME
                and not _OWN_OUTPUT.search(name)):
            out[name] = P.sha256_file(full)
    return out


def new_state(case_dir, brief_type, params):
    memo = P.find_memo(case_dir)
    return {
        "schema": 1,
        "params_version": params["params_version"],
        "case_dir": P.nfc(os.path.abspath(case_dir)),
        "case_key": P.case_key(case_dir),
        "brief_type": brief_type,
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
        "status": "interviewing",
        "memo": {"path": P.nfc(memo) if memo else None, "sha256": P.sha256_file(memo) if memo else None},
        "attachments": _attachments(case_dir),
        "side": None,
        "instance": None,
        "claim_amount": None,
        "claim_interest": None,
        "issues": [],
        "intent": {"primary": None, "secondaries": None, "success_sentence": None, "concession": None, "fast_path": False},
        "procedure": {"brief_type": brief_type, "due_date": None, "next_hearing": None},
        "flags": {"settle_will": None, "doc_targets": [], "alt_cause": None, "reduction_reasons": [],
                  "procedural_issue": None, "withheld_evidence": None},
        "conflict_answers": {},
        "intent_review": None,
        "rounds": [],
        "round0_done": False,
        "contrarian_done": False,
        "intent_retry_done": False,
        "design_confirm_count": 0,
        "threshold": 0.20,
        "threshold_source": "default",
        "overrides": [],
        "design_path": None,
        "draft_path": None,
        "compliance": {"first": None, "final": None},
        "cite": None,
        "outputs": [],
        "memo_writes": [],
    }


def load(path):
    return P.load_json(path)


def save(path, st):
    st["updated"] = datetime.datetime.now().isoformat(timespec="seconds")
    P.atomic_write_json(path, st)


def check_changes(st, params):
    """재개 때 바뀐 것 — 사건메모·첨부 해시, params_version."""
    case_dir = st["case_dir"]
    memo = P.find_memo(case_dir)
    memo_sha = P.sha256_file(memo) if memo else None
    att = _attachments(case_dir) if os.path.isdir(case_dir) else {}
    return {
        "memo_changed": memo_sha != st["memo"]["sha256"],
        "attachments_changed": sorted(k for k in set(att) | set(st["attachments"]) if att.get(k) != st["attachments"].get(k)),
        "params_changed": params["params_version"] != st["params_version"],
    }


def _merge_issue(st, upd):
    if "id" not in upd:
        raise P.BriefError("issues 항목에 id 가 없습니다")
    for it in st["issues"]:
        if it["id"] == upd["id"]:
            for k, v in upd.items():
                if k == "evidence" and isinstance(v, dict):
                    it.setdefault("evidence", {}).update(v)
                else:
                    it[k] = v
            return
    st["issues"].append(dict(upd))
    st["issues"].sort(key=lambda x: x["id"])


def validate_fields(st, params):
    stances = params["stances"]
    for it in st["issues"]:
        if it.get("stance") not in (None,) + tuple(stances):
            raise P.BriefError("쟁점 %s 태도 %r 는 목록(%s)에 없습니다" % (it["id"], it.get("stance"), "·".join(stances)))
        ev = it.get("evidence") or {}
        if ev.get("mode") not in (None,) + tuple(EVIDENCE_MODES):
            raise P.BriefError("쟁점 %s 증거 방식 %r 는 목록(%s)에 없습니다" % (it["id"], ev.get("mode"), "·".join(EVIDENCE_MODES)))
        if it.get("amount") is not None and not isinstance(it["amount"], int):
            raise P.BriefError("쟁점 %s amount 는 원 단위 정수여야 합니다" % it["id"])
    if st.get("side") not in (None, "원고", "피고"):
        raise P.BriefError("side 는 원고·피고 중 하나입니다")
    if st.get("claim_amount") is not None and not isinstance(st["claim_amount"], int):
        raise P.BriefError("claim_amount 는 원 단위 정수여야 합니다")
    if st.get("instance") not in (None,) + tuple(INSTANCES):
        raise P.BriefError("instance(심급)는 %s 중 하나입니다" % "·".join(INSTANCES))
    rv = st.get("intent_review")
    if rv is not None:
        if rv.get("verdict") not in REVIEW_VERDICTS:
            raise P.BriefError("intent_review.verdict 는 %s 중 하나입니다" % "·".join(REVIEW_VERDICTS))
        if rv.get("decision") not in REVIEW_DECISIONS:
            raise P.BriefError("intent_review.decision 은 %s 중 하나입니다" % "·".join(REVIEW_DECISIONS))
        for k in REVIEW_LISTS:
            if not isinstance(rv.get(k, []), list):
                raise P.BriefError("intent_review.%s 는 목록이어야 합니다" % k)


def apply_update(st, upd, params):
    """구조화 답을 상태에 합친다. upd 의 round 키가 있으면 라운드 기록 1건을 남긴다.
    사본에 적용해 검증이 통과한 뒤에만 반영한다(잘못된 답이 상태를 반쯤 바꾸지 않게)."""
    work = copy.deepcopy(st)
    _apply(work, upd, params)
    st.clear()
    st.update(work)
    return st


def _apply(st, upd, params):
    upd = dict(upd)
    rnd = upd.pop("round", None)
    for k, v in upd.items():
        if k == "issues":
            for it in v:
                _merge_issue(st, it)
        elif k in ("intent", "procedure", "flags", "conflict_answers") and isinstance(v, dict):
            st[k].update(v)
        elif k == "overrides":
            st["overrides"].extend(v)
        elif k == "intent_review" and isinstance(v, dict):
            st["intent_review"] = dict(v)  # 검토는 통째로 바꾼다 — 옛 판단이 섞이지 않게
        elif k in ("side", "instance", "claim_amount", "claim_interest", "round0_done", "contrarian_done", "intent_retry_done",
                   "threshold", "threshold_source", "design_confirm_count"):
            st[k] = v
        else:
            raise P.BriefError("알 수 없는 필드: %s" % k)
    if "intent_review" in upd and st.get("intent_review") is not None:
        st["intent_review"]["for"] = P.intent_signature(st["intent"])  # 같은 apply 의 의도 변경까지 반영한 뒤 서명
    validate_fields(st, params)
    if rnd is not None:
        rt = rnd.get("round_type")
        if rt not in ROUND_TYPES:
            raise P.BriefError("round_type %r 는 %s 중 하나여야 합니다" % (rt, ROUND_TYPES))
        if not rnd.get("question"):
            raise P.BriefError("라운드 기록에 question 이 없습니다")
        rec = {k: rnd.get(k) for k in ("round_type", "issue_id", "axis", "question", "options", "answer", "evidence_quote", "why")}
        rec["ts"] = datetime.datetime.now().isoformat(timespec="seconds")
        st["rounds"].append(rec)
        if rt == "round0":
            st["round0_done"] = True
        elif rt == "contrarian":
            st["contrarian_done"] = True
        elif rt == "design_confirm":
            st["design_confirm_count"] = st.get("design_confirm_count", 0) + 1
    return st


def set_status(st, new):
    if new not in STATUSES:
        raise P.BriefError("status %r 는 %s 중 하나입니다" % (new, STATUSES))
    cur = st["status"]
    if new != cur and new not in TRANSITIONS[cur]:
        raise P.BriefError("상태 전이 %s → %s 는 허용되지 않습니다" % (cur, new))
    st["status"] = new
    return st


def refresh_memo_hash(st):
    """스킬이 사건메모에 직접 쓴 뒤 — 재개 때 자기 쓰기로 Round 0 diff 가 뜨지 않게."""
    memo = P.find_memo(st["case_dir"])
    st["memo"] = {"path": P.nfc(memo) if memo else None, "sha256": P.sha256_file(memo) if memo else None}
    return st


def purge(case_dir=None, all_cases=False):
    root = os.path.join(P.work_root(), "cases")
    if all_cases:
        targets = [os.path.join(root, n) for n in os.listdir(root)] if os.path.isdir(root) else []
    else:
        targets = [P.case_work_dir(case_dir, create=False)]
    removed = []
    for t in targets:
        if os.path.isdir(t):
            shutil.rmtree(t)
            removed.append(t)
    return removed


def _read_json_arg(a):
    if a.json_file:
        return P.load_json(a.json_file)
    return json.loads(a.json)


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init"); s.add_argument("case_dir"); s.add_argument("--brief", required=True)
    s = sub.add_parser("show"); s.add_argument("state")
    s = sub.add_parser("apply"); s.add_argument("state"); s.add_argument("--json"); s.add_argument("--json-file")
    s = sub.add_parser("set-status"); s.add_argument("state"); s.add_argument("status")
    s = sub.add_parser("purge"); s.add_argument("case_dir", nargs="?"); s.add_argument("--all", action="store_true")
    a = ap.parse_args(argv)
    params = P.load_params()
    try:
        if a.cmd == "init":
            if a.brief not in params["brief_types"]:
                raise P.BriefError("서면 종류는 %s 중 하나입니다(1차 범위)" % "·".join(params["brief_types"]))
            if not os.path.isdir(a.case_dir):
                raise P.BriefError("사건 폴더가 없습니다: %s" % a.case_dir)
            path = state_path(a.case_dir, a.brief)
            if os.path.exists(path):
                st = load(path)
                return P.emit({"ok": True, "resumed": True, "state": path, "work_dir": os.path.dirname(path),
                               "status": st["status"], "changes": check_changes(st, params)})
            st = new_state(a.case_dir, a.brief, params)
            save(path, st)
            return P.emit({"ok": True, "resumed": False, "state": path, "work_dir": os.path.dirname(path),
                           "memo_connected": bool(st["memo"]["path"])})
        if a.cmd == "show":
            return P.emit(load(a.state))
        if a.cmd == "apply":
            st = load(a.state)
            apply_update(st, _read_json_arg(a), params)
            save(a.state, st)
            return P.emit({"ok": True, "rounds": len(st["rounds"])})
        if a.cmd == "set-status":
            st = load(a.state)
            set_status(st, a.status)
            save(a.state, st)
            return P.emit({"ok": True, "status": st["status"]})
        if a.cmd == "purge":
            if not a.all and not a.case_dir:
                raise P.BriefError("사건 폴더 또는 --all 을 지정하십시오")
            return P.emit({"ok": True, "removed": purge(a.case_dir, a.all)})
    except P.BriefError as e:
        return P.fail(str(e))


if __name__ == "__main__":
    sys.exit(main())
