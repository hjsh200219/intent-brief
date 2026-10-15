#!/usr/bin/env python3
"""법정기간 만료일 계산 — 표준 라이브러리만, Python 3.9.

민사(민사소송법 제170조 → 민법): 초일 불산입(제157조, 오전 영시 시작이면 산입), 주·월·연은 역(曆)으로(제160조),
말일이 토요일·공휴일이면 익일 만료(제161조). 형사(형사소송법 제66조): 초일 불산입, 말일이 공휴일·토요일이면 불산입.
형사 시효·구속기간: 초일을 1일로 산정하고 말일 연장 없음. 공휴일은 references/holidays.json(한국천문연구원 특일정보) + 일요일.
"""
import argparse
import calendar
import json
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
HOLIDAYS = os.path.join(HERE, "..", "references", "holidays.json")
UNITS = ("일", "주", "월", "연")
REGIMES = ("민사", "형사", "형사시효")
WEEKDAYS = "월화수목금토일"
IMMINENT_DAYS = 14

PRESETS = {
    "민사-항소": {"n": 2, "unit": "주", "regime": "민사", "from": "판결서 송달일", "law": "민사소송법 제396조", "invariable": True},
    "민사-상고": {"n": 2, "unit": "주", "regime": "민사", "from": "판결서 송달일", "law": "민사소송법 제425조(제396조 준용)", "invariable": True},
    "민사-즉시항고": {"n": 1, "unit": "주", "regime": "민사", "from": "재판 고지일", "law": "민사소송법 제444조", "invariable": True},
    "민사-답변서": {"n": 30, "unit": "일", "regime": "민사", "from": "소장 부본 송달일", "law": "민사소송법 제256조제1항", "invariable": False,
                "note": "공시송달로 받은 경우는 적용하지 않는다(같은 항 단서)."},
    "민사-항소이유서": {"n": 40, "unit": "일", "regime": "민사", "from": "제400조제3항 통지(소송기록 접수 통지)일", "law": "민사소송법 제402조의2제1항",
                  "invariable": False, "note": "신청으로 1회 1개월 연장할 수 있다(같은 조 제2항). 연장 결정이 있으면 다시 계산한다."},
    "민사-상고이유서": {"n": 20, "unit": "일", "regime": "민사", "from": "제426조 통지(소송기록 접수 통지)일", "law": "민사소송법 제427조", "invariable": False},
    "민사-지급명령이의": {"n": 2, "unit": "주", "regime": "민사", "from": "지급명령 송달일", "law": "민사소송법 제470조", "invariable": True},
    "민사-추후보완": {"n": 2, "unit": "주", "regime": "민사", "from": "책임질 수 없는 사유가 없어진 날", "law": "민사소송법 제173조제1항", "invariable": False,
                "note": "그 사유가 없어질 당시 외국에 있던 당사자는 30일. 이 기간은 늘이거나 줄일 수 없다(같은 조 제2항)."},
    "형사-항소": {"n": 7, "unit": "일", "regime": "형사", "from": "판결 선고일", "law": "형사소송법 제358조·제343조제2항", "invariable": None},
    "형사-상고": {"n": 7, "unit": "일", "regime": "형사", "from": "판결 선고일", "law": "형사소송법 제374조·제343조제2항", "invariable": None},
    "형사-즉시항고": {"n": 7, "unit": "일", "regime": "형사", "from": "재판 고지일", "law": "형사소송법 제405조·제343조제2항", "invariable": None},
    "형사-항소이유서": {"n": 20, "unit": "일", "regime": "형사", "from": "소송기록 접수 통지일", "law": "형사소송법 제361조의3제1항", "invariable": None},
    "형사-상고이유서": {"n": 20, "unit": "일", "regime": "형사", "from": "소송기록 접수 통지일", "law": "형사소송법 제379조제1항", "invariable": None},
    "행정-취소소송": {"n": 90, "unit": "일", "regime": "민사", "from": "처분 등이 있음을 안 날(행정심판을 거쳤으면 재결서 정본 송달일)",
                "law": "행정소송법 제20조제1항·제3항", "invariable": True},
    "행정-취소소송-처분일": {"n": 1, "unit": "연", "regime": "민사", "from": "처분 등이 있은 날(행정심판을 거쳤으면 재결이 있은 날)",
                    "law": "행정소송법 제20조제2항", "invariable": False, "note": "정당한 사유가 있으면 지나도 제기할 수 있다(같은 항 단서)."},
}


def _date(s, what="날짜"):
    if isinstance(s, date):
        return s
    try:
        return date.fromisoformat(str(s))
    except ValueError:
        raise ValueError("%s 형식은 YYYY-MM-DD 입니다: %s" % (what, s))


def load_holidays(path=HOLIDAYS):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    lo, hi = data["years"]
    return data["holidays"], range(lo, hi + 1)


def _add_months(d, months):
    """대응일. 그 달에 해당일이 없으면 None(민법 제160조제3항 처리는 호출자가)."""
    y, m = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m + 1
    if d.day > calendar.monthrange(y, m)[1]:
        return None, date(y, m, calendar.monthrange(y, m)[1])
    return date(y, m, d.day), None


def raw_end(start, n, unit, include_first):
    if unit not in UNITS:
        raise ValueError("기간 단위는 %s 중 하나입니다: %s" % ("·".join(UNITS), unit))
    if n <= 0:
        raise ValueError("기간은 1 이상입니다")
    if unit in ("일", "주"):
        days = n * (7 if unit == "주" else 1)
        return start + timedelta(days=days - 1 if include_first else days)
    months = n * (12 if unit == "연" else 1)
    if include_first:
        # 기산일이 시작일 — 최후의 월에서 기산일에 해당한 날의 전일(제160조제2항), 해당일이 없으면 그 월 말일(제3항).
        same, month_end = _add_months(start, months)
        return same - timedelta(days=1) if same else month_end
    # 초일 불산입 — 기산일(다음 날)에 해당한 날의 전일 = 시작일의 대응일. 없으면 그 월 말일.
    same, month_end = _add_months(start, months)
    return same or month_end


def compute(start, preset=None, n=None, unit=None, regime="민사", include_first=False, extra_holidays=(), today=None):
    start = _date(start, "기산 기준일")
    spec = {}
    if preset:
        if preset not in PRESETS:
            raise ValueError("모르는 기간 종류입니다: %s (presets 로 목록 확인)" % preset)
        spec = PRESETS[preset]
        n, unit, regime = spec["n"], spec["unit"], spec["regime"]
    if n is None or unit is None:
        raise ValueError("preset 또는 n·unit 이 필요합니다")
    if regime not in REGIMES:
        raise ValueError("계산 체계는 %s 중 하나입니다: %s" % ("·".join(REGIMES), regime))
    if regime == "형사시효":
        include_first = True
    elif regime == "형사":
        include_first = False
    table, years = load_holidays()
    extra = {_date(x, "추가 공휴일").isoformat() for x in extra_holidays}
    end = raw_end(start, int(n), unit, include_first)
    warnings, shifted, expires = [], [], end
    seen_years = set()

    def holiday_reason(d):
        iso = d.isoformat()
        if iso in extra:
            return "추가 공휴일"
        if d.weekday() == 6:
            return "일요일"
        if d.year not in years:
            seen_years.add(d.year)
        elif iso in table:
            return table[iso]
        if d.weekday() == 5:
            return "토요일"
        return None

    if regime != "형사시효":
        reason = holiday_reason(expires)
        while reason:
            shifted.append({"date": expires.isoformat(), "reason": reason})
            expires += timedelta(days=1)
            reason = holiday_reason(expires)
    elif end.year not in years:
        seen_years.add(end.year)
    if seen_years and regime != "형사시효":
        warnings.append("공휴일 표 범위 밖(%s년) — 토·일만 반영했습니다. 그해 공휴일을 확인해 --holiday 로 더하십시오."
                        % ",".join(str(y) for y in sorted(seen_years)))
    out = {"ok": True, "start": start.isoformat(), "period": "%d%s" % (int(n), unit), "regime": regime,
           "first_day_included": include_first, "raw_end": end.isoformat(), "shifted": shifted,
           "expires": expires.isoformat(), "weekday": WEEKDAYS[expires.weekday()], "warnings": warnings,
           "preset": preset, "law": spec.get("law"), "from": spec.get("from"), "invariable": spec.get("invariable"),
           "note": spec.get("note"), "basis": _basis(regime)}
    if today is not None:
        d = (expires - _date(today, "오늘")).days
        out["d_day"] = d
        out["imminent"] = 0 <= d <= IMMINENT_DAYS
        out["passed"] = d < 0
    return out


def _basis(regime):
    if regime == "민사":
        return "민법 제157조(초일 불산입)·제160조(역에 의한 계산)·제161조(토요일·공휴일이면 익일 만료), 민사소송법 제170조"
    if regime == "형사":
        return "형사소송법 제66조제1항(초일 불산입)·제2항·제3항(말일이 공휴일·토요일이면 불산입)"
    return "형사소송법 제66조제1항 단서(시효·구속기간 초일 산입)·제3항 단서(말일 연장 없음)"


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="법정기간 만료일 계산")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("calc")
    c.add_argument("start", help="송달일·고지일·선고일 등 기산 기준일(YYYY-MM-DD)")
    c.add_argument("--preset")
    c.add_argument("--n", type=int)
    c.add_argument("--unit", choices=UNITS)
    c.add_argument("--regime", choices=REGIMES, default="민사")
    c.add_argument("--from-midnight", action="store_true", help="민법 제157조 단서 — 오전 영시부터 시작(초일 산입)")
    c.add_argument("--holiday", action="append", default=[], help="표에 없는 임시공휴일(YYYY-MM-DD, 여러 번)")
    c.add_argument("--today")
    sub.add_parser("presets")
    a = ap.parse_args(argv)
    if a.cmd == "presets":
        print(json.dumps({"ok": True, "presets": PRESETS}, ensure_ascii=False, indent=1))
        return 0
    try:
        out = compute(a.start, preset=a.preset, n=a.n, unit=a.unit, regime=a.regime, include_first=a.from_midnight,
                      extra_holidays=a.holiday, today=a.today or date.today().isoformat())
    except ValueError as e:
        print(json.dumps({"ok": False, "error": "bad_input", "message": str(e)}, ensure_ascii=False))
        return 3
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
