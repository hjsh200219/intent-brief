#!/usr/bin/env python3
"""소송비용 계산 — 인지액·송달료 회분·지연손해금. 표준 라이브러리만, Python 3.9.

인지액: 민사소송 등 인지법 제2조(소장, 1천원 미만은 1천원·100원 미만 버림), 제3조(항소장 1.5배·상고장 2배),
제7조(화해신청서 5분의 1·지급명령신청서 10분의 1), 제16조(전자소송 10분의 9). 배수 적용 뒤의 끝수 처리 규정은
법·「민사소송 등 인지규칙」에서 찾지 못했다(2026-10-15 조문 대조) — 원 미만만 버린다.
송달료: 「송달료규칙의 시행에 따른 업무처리요령」(재일 87-4) 별표 1의 당사자 1인당 회분. 1회분 금액은 그 예규에 없어 입력받는다.
지연손해금: 기간 양 끝 포함 일수 × 연 이율 ÷ 365, 원 미만 버림.
"""
import argparse
import json
import math
import sys
from datetime import date
from fractions import Fraction

STAMP_DOCS = {
    "소장": (Fraction(1), "민사소송 등 인지법 제2조"),
    "반소장": (Fraction(1), "민사소송 등 인지법 제4조제1항(제1심)"),
    "항소장": (Fraction(3, 2), "민사소송 등 인지법 제3조"),
    "상고장": (Fraction(2), "민사소송 등 인지법 제3조"),
    "화해신청서": (Fraction(1, 5), "민사소송 등 인지법 제7조제1항"),
    "지급명령": (Fraction(1, 10), "민사소송 등 인지법 제7조제2항"),
}

# 재일 87-4 별표 1(2026-03-01 시행본) — 당사자 1인당 송달료 납부 회분
SERVICE_ROUNDS = {
    "민사합의": 15, "민사단독": 15, "민사소액": 10, "민사항소": 12, "민사상고": 8, "민사항고": 5, "민사재항고": 5,
    "가압류": 3, "가처분": 3, "임시지위가처분": 8, "독촉": 6, "민사조정": 5,
    "행정1심": 10, "행정항소": 10, "행정상고": 8, "가사1심": 15, "가사항소": 12, "가사상고": 8,
}

RATES = {"민사": Fraction(5, 100), "상사": Fraction(6, 100), "소촉법": Fraction(12, 100)}
RATE_LAW = {"민사": "민법 제379조(연 5%)", "상사": "상법 제54조(연 6%)",
            "소촉법": "소송촉진 등에 관한 특례법 제3조제1항 및 같은 조항 법정이율 규정(연 12%, 2019.6.1. 시행)"}


def _base_stamp(value):
    v = Fraction(int(value))
    if v < 0:
        raise ValueError("소송목적의 값은 0 이상입니다")
    if v < 10000000:
        amt = v * Fraction(50, 10000)
    elif v < 100000000:
        amt = v * Fraction(45, 10000) + 5000
    elif v < 1000000000:
        amt = v * Fraction(40, 10000) + 55000
    else:
        amt = v * Fraction(35, 10000) + 555000
    if amt < 1000:
        return 1000
    return int(amt // 100 * 100)


def stamp(value, doc="소장", electronic=False):
    if doc not in STAMP_DOCS:
        raise ValueError("서류는 %s 중 하나입니다: %s" % ("·".join(STAMP_DOCS), doc))
    mult, law = STAMP_DOCS[doc]
    base = _base_stamp(value)
    amt = base * mult
    laws = [law] if doc == "소장" else ["민사소송 등 인지법 제2조", law]
    if electronic:
        amt *= Fraction(9, 10)
        laws.append("민사소송 등 인지법 제16조(전자소송 10분의 9)")
    return {"ok": True, "value": int(value), "doc": doc, "electronic": electronic, "base": base,
            "amount": int(math.floor(amt)), "law": " · ".join(laws),
            "note": "소송목적의 값(소가) 산정은 민사소송 등 인지규칙을 따른다 — 이 계산은 입력한 소가를 그대로 쓴다."}


def service(case_type, parties, unit=None):
    if case_type not in SERVICE_ROUNDS:
        raise ValueError("사건 종류는 %s 중 하나입니다: %s" % ("·".join(SERVICE_ROUNDS), case_type))
    if parties < 1:
        raise ValueError("당사자 수는 1 이상입니다")
    rounds = SERVICE_ROUNDS[case_type] * parties
    out = {"ok": True, "case_type": case_type, "parties": parties, "per_party": SERVICE_ROUNDS[case_type], "rounds": rounds,
           "unit": unit, "amount": rounds * unit if unit else None,
           "law": "송달료규칙의 시행에 따른 업무처리요령(재일 87-4) 별표 1"}
    out["note"] = ("1회분 금액 %s원 기준." % format(unit, ",")) if unit else \
        "1회분 송달료 단가는 예규에 없습니다 — 대법원 공고 단가를 확인해 --unit 으로 넣으십시오(단가 확인 필요)."
    return out


def _rate(r):
    if isinstance(r, str) and r in RATES:
        return RATES[r], RATE_LAW[r]
    try:
        f = Fraction(str(r))
    except ValueError:
        raise ValueError("이율은 %s 또는 소수(예: 0.05)입니다: %s" % ("·".join(RATES), r))
    if not 0 < f < 1:
        raise ValueError("이율은 0과 1 사이의 연 이율입니다: %s" % r)
    return f, "약정·기타 연 %s%%" % (float(f) * 100)


def interest(principal, segments):
    rows, total, spans = [], 0, []
    for start, end, r in segments:
        s, e = date.fromisoformat(str(start)), date.fromisoformat(str(end))
        if e < s:
            raise ValueError("구간 끝이 시작보다 앞입니다: %s ~ %s" % (start, end))
        spans.append((s, e, r))
    spans.sort(key=lambda x: x[0])
    for (s0, e0, _), (s1, _e1, _r) in zip(spans, spans[1:]):
        if s1 <= e0:  # 양 끝을 포함해 세므로 경계일을 두 구간에 넣으면 하루치 이자가 겹친다
            raise ValueError("구간이 겹칩니다: %s ~ %s 와 %s ~ — 이율이 바뀌는 날은 한 구간에만 넣으십시오" % (s0, e0, s1))
    for s, e, r in spans:
        rate, law = _rate(r)
        days = (e - s).days + 1
        amt = int(math.floor(Fraction(int(principal)) * rate * days / 365))
        rows.append({"from": s.isoformat(), "to": e.isoformat(), "days": days, "rate": float(rate), "law": law, "amount": amt})
        total += amt
    return {"ok": True, "principal": int(principal), "segments": rows, "total": total,
            "note": "일수는 구간 양 끝 포함, 연 365일 기준·원 미만 버림. 소촉법 이율은 소장 부본 송달 다음 날부터 적용된다(같은 법 제3조제1항)."}


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="소송비용 계산")
    sub = ap.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("stamp")
    st.add_argument("value", type=int, help="소송목적의 값(원)")
    st.add_argument("--doc", default="소장", choices=list(STAMP_DOCS))
    st.add_argument("--electronic", action="store_true")
    sv = sub.add_parser("service")
    sv.add_argument("case_type", choices=list(SERVICE_ROUNDS))
    sv.add_argument("--parties", type=int, required=True)
    sv.add_argument("--unit", type=int, help="1회분 송달료(원)")
    it = sub.add_parser("interest")
    it.add_argument("principal", type=int)
    it.add_argument("--segment", action="append", required=True, help="시작:끝:이율 — 이율은 민사·상사·소촉법 또는 0.15")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "stamp":
            out = stamp(a.value, a.doc, a.electronic)
        elif a.cmd == "service":
            out = service(a.case_type, a.parties, a.unit)
        else:
            segs = []
            for seg in a.segment:
                parts = seg.split(":")
                if len(parts) != 3:
                    raise ValueError("구간은 시작:끝:이율 형식입니다: %s" % seg)
                segs.append(tuple(parts))
            out = interest(a.principal, segs)
    except ValueError as e:
        print(json.dumps({"ok": False, "error": "bad_input", "message": str(e)}, ensure_ascii=False))
        return 3
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
