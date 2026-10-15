#!/usr/bin/env python3
"""심각도 × 가능성 위험 점수표 — 표준 라이브러리만, Python 3.9.

틀은 Anthropic knowledge-work-plugins legal/legal-risk-assessment(Apache-2.0)의 5×5 행렬과 구간(1–4·5–9·10–15·16–25)을
한국 소송 실무 문구로 옮겼다. 고지는 third_party/anthropic-legal/NOTICE.md.
"""
import argparse
import json
import sys

SEVERITY = {1: "경미", 2: "낮음", 3: "중간", 4: "높음", 5: "치명"}
LIKELIHOOD = {1: "희박", 2: "낮음", 3: "있음", 4: "높음", 5: "거의 확실"}
LEVELS = [  # (상한, 등급, 이름, 조치)
    (4, "GREEN", "낮은 위험", "받아들이고 기록. 정기 점검 때 다시 본다."),
    (9, "YELLOW", "중간 위험", "보완책(증거 보강·주장 정리)을 정하고 담당을 둔다. 상황이 바뀌면 다시 매긴다."),
    (15, "ORANGE", "높은 위험", "담당 변호사가 직접 대응 계획을 세우고 의뢰인에게 설명한다. 기일·기한마다 다시 본다."),
    (25, "RED", "치명 위험", "즉시 대표·담당 변호사 협의. 증거 보전, 화해·조정 등 대안 검토, 의뢰인 서면 보고."),
]
ORDER = ["RED", "ORANGE", "YELLOW", "GREEN"]


def _level(v, name):
    if isinstance(v, bool) or not isinstance(v, int):
        try:
            v = int(str(v))
        except ValueError:
            raise ValueError("%s 는 1–5 정수입니다: %r" % (name, v))
    if not 1 <= v <= 5:
        raise ValueError("%s 는 1–5 정수입니다: %r" % (name, v))
    return v


def score(severity, likelihood):
    s, l = _level(severity, "심각도"), _level(likelihood, "가능성")
    total = s * l
    for top, level, label, actions in LEVELS:
        if total <= top:
            return {"ok": True, "severity": s, "severity_label": SEVERITY[s], "likelihood": l,
                    "likelihood_label": LIKELIHOOD[l], "score": total, "level": level, "label": label, "actions": actions}
    raise AssertionError(total)


def table(path):
    with open(path, encoding="utf-8") as f:
        items = json.load(f)
    rows = []
    for it in items:
        r = score(it["severity"], it["likelihood"])
        rows.append(dict(r, id=str(it["id"]), title=it["title"], basis=it.get("basis") or ""))
    rows.sort(key=lambda r: (-r["score"], -r["severity"], r["id"]))
    counts = {k: sum(1 for r in rows if r["level"] == k) for k in ORDER}
    md = ["| 순위 | ID | 위험 | 심각도 | 가능성 | 점수 | 등급 | 근거 |", "|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        md.append("| %d | %s | %s | %d | %d | %d | %s | %s |" % (i, r["id"], r["title"], r["severity"], r["likelihood"],
                                                               r["score"], r["level"], r["basis"].replace("|", "/")))
    return {"ok": True, "rows": rows, "counts": counts, "markdown": "\n".join(md)}


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="심각도×가능성 위험 점수")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sc = sub.add_parser("score")
    sc.add_argument("severity")
    sc.add_argument("likelihood")
    tb = sub.add_parser("table")
    tb.add_argument("path", help='[{"id","title","severity","likelihood","basis"}] JSON 파일')
    a = ap.parse_args(argv)
    try:
        out = score(a.severity, a.likelihood) if a.cmd == "score" else table(a.path)
    except (ValueError, KeyError, OSError) as e:
        print(json.dumps({"ok": False, "error": "bad_input", "message": str(e)}, ensure_ascii=False))
        return 3
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
