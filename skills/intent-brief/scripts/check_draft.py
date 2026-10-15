"""초안(draft.md)이 design.json 을 지켰는지 결정론으로 검사한다.

검사: 앵커 문법, 설계 섹션 존재, 설계 밖 섹션 없음, 쟁점별 태도 표지, 강도 표현 수, 분량, 결론 문장 그대로.
표지 문구(references/phrases.json)는 검사기 전용이다 — 작성 단계에는 주지 않는다.

사용:
  check_draft.py check <draft.md> <design.json> [--state <state.json> --record first|final]
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths as P  # noqa: E402

_SEC = re.compile(r"^##\s+\[sec:(?P<id>[a-z_.]+)\]\s*(?P<title>.*)$")
_ISS = re.compile(r"^###\s+\[issue:(?P<id>\d+)\]\s*(?P<title>.*)$")
NON_BODY = ("sec.header", "sec.evidence_list")


def split_front(md):
    front = {}
    if md.startswith("---"):
        end = md.find("\n---", 3)
        if end > 0:
            for ln in md[3:end].splitlines():
                if ":" in ln:
                    k, v = ln.split(":", 1)
                    front[k.strip()] = v.strip()
            nl = md.find("\n", end + 4)
            md = md[nl + 1:] if nl > 0 else ""
    return front, md


def parse_draft(md, section_ids=None):
    front, body = split_front(md.replace("\r\n", "\n"))
    sections, errors = [], []
    cur, cur_issue = None, None
    for n, ln in enumerate(body.split("\n"), 1):
        if ln.startswith("## ") or ln.startswith("##\t"):
            m = _SEC.match(ln)
            if not m:
                errors.append("%d행: 앵커 없는 ## 제목 — 「## [sec:<섹션 ID>] 제목」 형식이어야 합니다" % n)
                continue
            if section_ids is not None and m.group("id") not in section_ids:
                errors.append("%d행: 섹션 ID %s 는 어휘에 없습니다" % (n, m.group("id")))
            cur = {"id": m.group("id"), "title": m.group("title").strip(), "lines": [], "issues": []}
            cur_issue = None
            sections.append(cur)
            continue
        if ln.startswith("### "):
            m = _ISS.match(ln)
            if not m:
                errors.append("%d행: 앵커 없는 ### 제목 — 「### [issue:<번호>] 제목」 형식이어야 합니다" % n)
                continue
            if cur is None:
                errors.append("%d행: 섹션 밖의 쟁점 제목" % n)
                continue
            cur_issue = {"id": int(m.group("id")), "title": m.group("title").strip(), "lines": []}
            cur["issues"].append(cur_issue)
            continue
        if cur is None:
            if ln.strip():
                errors.append("%d행: 첫 섹션 앞의 본문" % n)
            continue
        cur["lines"].append(ln)
        if cur_issue is not None:
            cur_issue["lines"].append(ln)
    for s in sections:
        s["body"] = "\n".join(s["lines"]).strip()
        for i in s["issues"]:
            i["body"] = "\n".join(i["lines"]).strip()
    return {"front": front, "sections": sections, "errors": errors}


def _count(text, words):
    return sum(text.count(w) for w in words)


def _norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


def check(md, design, params=None, phrases=None):
    params = params or P.load_params()
    phrases = phrases or P.load_phrases()
    parsed = parse_draft(md, set(params["sections"]))
    checks = []

    def add(cid, ok, detail=""):
        checks.append({"id": cid, "ok": bool(ok), "detail": detail})

    add("anchors", not parsed["errors"], "; ".join(parsed["errors"][:5]))
    present = [s["id"] for s in parsed["sections"]]
    want = [s["id"] for s in design["sections"]]
    for sid in want:
        add("section:%s" % sid, sid in present, "" if sid in present else "섹션 누락")
    extra = [s for s in present if s not in want]
    add("no_extra_sections", not extra, ", ".join(extra))

    issues_in_draft = {}
    for s in parsed["sections"]:
        for i in s["issues"]:
            issues_in_draft.setdefault(i["id"], []).append(i["body"])
    deny, admit = phrases["stance_markers"]["deny"], phrases["stance_markers"]["admit"]
    for it in design["issues"]:
        iid, stance = it["id"], it["stance"]
        bodies = issues_in_draft.get(iid)
        text = "\n".join(bodies or [])
        if stance == "유보":
            add("stance:%d" % iid, not bodies, "유보 쟁점은 이번 서면에 쓰지 않습니다" if bodies else "")
            continue
        if not bodies:
            add("stance:%d" % iid, False, "쟁점 %d 의 [issue:%d] 소제목이 없습니다" % (iid, iid))
            continue
        nd, na = _count(text, deny), _count(text, admit)
        if stance == "다툼":
            add("stance:%d" % iid, nd >= 1 and na == 0, "부인 표지 %d · 인정 표지 %d" % (nd, na))
        else:
            ok = na >= 1
            detail = "인정 표지 %d" % na
            if stance == "일부 인정" and it.get("amount") is not None:
                amt = P.fmt_won(it["amount"])
                ok = ok and amt in text
                detail += " · 금액 「%s」 %s" % (amt, "있음" if amt in text else "없음")
            add("stance:%d" % iid, ok, detail)

    body_text = "\n".join(s["body"] for s in parsed["sections"] if s["id"] not in NON_BODY)
    n_assert = _count(body_text, phrases["strength_markers"]["assertive"])
    level = design["strength"]["level"]
    if level == "단정":
        add("strength", n_assert >= 3, "단정형 표현 %d개(기준 ≥3)" % n_assert)
    elif level == "중":
        add("strength", n_assert <= 1, "단정형 표현 %d개(기준 ≤1)" % n_assert)
    lo, hi = design["length"]["chars"]
    n_chars = len(re.sub(r"\s+", "", body_text))
    add("length", lo * 0.7 <= n_chars <= hi * 1.3, "본문 %d자(기준 %d–%d, 허용 ±30%%)" % (n_chars, lo, hi))

    concl = next((s["body"] for s in parsed["sections"] if s["id"] == "sec.conclusion"), "")
    want_c = _norm(design["conclusion"]["text"])
    add("conclusion", want_c in _norm(concl), "설계 결론 문장을 그대로 써야 합니다" if want_c not in _norm(concl) else "")

    passed = sum(1 for c in checks if c["ok"])
    return {"rate": round(passed / len(checks), 3), "passed": passed, "total": len(checks),
            "failures": [c for c in checks if not c["ok"]], "checks": checks,
            "metrics": {"assertive": n_assert, "chars": n_chars,
                        "check_tags": len(re.findall(r"\[확인 필요", md)), "law_api_tags": len(re.findall(r"\[법제처", md))}}


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("check")
    s.add_argument("draft"); s.add_argument("design")
    s.add_argument("--state"); s.add_argument("--record", choices=["first", "final"])
    a = ap.parse_args(argv)
    res = check(P.read_text(a.draft), P.load_json(a.design))
    if a.state and a.record:
        import state as S
        st = P.load_json(a.state)
        st["compliance"][a.record] = {"rate": res["rate"], "failures": [f["id"] for f in res["failures"]]}
        st["draft_path"] = os.path.abspath(a.draft)
        S.save(a.state, st)
    res["ok"] = True
    return P.emit(res)


if __name__ == "__main__":
    sys.exit(main())
