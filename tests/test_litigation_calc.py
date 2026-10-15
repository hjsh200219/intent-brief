"""법정기간 만료일·소송비용 계산기 — 민법 제157·160·161조, 형사소송법 제66조, 민사소송 등 인지법 제2·3·7·16조."""
import ast
import json
import os
import sys
from datetime import date

import pytest

from conftest import ROOT

SCRIPTS = os.path.join(ROOT, "skills", "litigation-calc", "scripts")
sys.path.insert(0, SCRIPTS)
import costs as C  # noqa: E402
import deadline as D  # noqa: E402


# ---- 기간 ----

def test_civil_appeal_two_weeks_no_shift():
    """판결서 송달 2026-10-15(목) → 초일 불산입 2주 → 10-29(목)."""
    r = D.compute("2026-10-15", preset="민사-항소")
    assert r["expires"] == "2026-10-29" and r["raw_end"] == "2026-10-29" and r["shifted"] == []
    assert r["invariable"] is True and "제396조" in r["law"] and r["regime"] == "민사"


def test_saturday_then_sunday_moves_to_monday():
    """말일 10-31(토) → 민법 제161조 익일, 11-01(일)도 공휴일 → 11-02(월)."""
    r = D.compute("2026-10-17", preset="민사-항소")
    assert r["raw_end"] == "2026-10-31" and r["expires"] == "2026-11-02"
    assert [s["reason"] for s in r["shifted"]] == ["토요일", "일요일"]


def test_holiday_chain_from_table():
    """2026-09-23 + 1일 → 09-24 추석 → 25·26(토)·27(일) 지나 09-28(월)."""
    r = D.compute("2026-09-23", n=1, unit="일")
    assert r["expires"] == "2026-09-28"
    assert [s["date"] for s in r["shifted"]] == ["2026-09-24", "2026-09-25", "2026-09-26", "2026-09-27"]
    assert r["shifted"][0]["reason"] == "추석"


def test_month_clamps_to_month_end_then_shifts():
    """2027-01-31 + 1개월 → 민법 제160조제3항 2월 말일 02-28(일) → 03-01 삼일절 → 03-02."""
    r = D.compute("2027-01-31", n=1, unit="월")
    assert r["raw_end"] == "2027-02-28" and r["expires"] == "2027-03-02"


def test_month_corresponding_day():
    assert D.compute("2026-01-15", n=1, unit="월")["raw_end"] == "2026-02-15"
    assert D.compute("2026-03-10", n=1, unit="연")["raw_end"] == "2027-03-10"


def test_criminal_appeal_seven_days():
    r = D.compute("2026-10-15", preset="형사-항소")
    assert r["expires"] == "2026-10-22" and r["regime"] == "형사" and "제358조" in r["law"]


def test_criminal_prescription_counts_first_day_and_no_shift():
    """형사소송법 제66조 — 시효·구속기간은 초일을 1일로 산정하고 말일이 토요일이어도 늘지 않는다."""
    r = D.compute("2026-10-25", n=7, unit="일", regime="형사시효")
    assert r["raw_end"] == "2026-10-31" and r["expires"] == "2026-10-31" and r["shifted"] == []
    assert r["first_day_included"] is True


def test_civil_from_midnight_counts_first_day():
    """민법 제157조 단서 — 오전 영시부터 시작하면 초일 산입."""
    assert D.compute("2026-10-15", n=14, unit="일", include_first=True)["raw_end"] == "2026-10-28"
    assert D.compute("2026-01-15", n=1, unit="월", include_first=True)["raw_end"] == "2026-02-14"
    assert D.compute("2027-01-31", n=1, unit="월", include_first=True)["raw_end"] == "2027-02-28"


def test_extra_holiday_and_out_of_table_warning():
    r = D.compute("2026-10-15", preset="민사-항소", extra_holidays=["2026-10-29"])
    assert r["expires"] == "2026-10-30" and r["shifted"][0]["reason"] == "추가 공휴일"
    far = D.compute("2027-12-25", preset="민사-항소")
    assert far["expires"] == "2028-01-10" and any("공휴일 표 범위 밖" in w and "2028" in w for w in far["warnings"])
    assert D.compute("2026-10-15", preset="민사-항소")["warnings"] == []


def test_d_day_and_imminent():
    r = D.compute("2026-10-15", preset="민사-항소", today="2026-10-20")
    assert r["d_day"] == 9 and r["imminent"] is True
    assert D.compute("2026-10-15", preset="민사-답변서", today="2026-10-15")["imminent"] is False


def test_presets_have_basis():
    for key, p in D.PRESETS.items():
        assert p["law"] and p["from"] and p["n"] > 0 and p["unit"] in D.UNITS, key
        assert p["regime"] in D.REGIMES, key
    for need in ("민사-항소", "민사-상고", "민사-즉시항고", "민사-답변서", "민사-항소이유서", "민사-상고이유서", "민사-지급명령이의",
                 "민사-추후보완", "형사-항소", "형사-상고", "형사-즉시항고", "형사-항소이유서", "형사-상고이유서",
                 "행정-취소소송", "행정-취소소송-처분일"):
        assert need in D.PRESETS, need


def test_bad_input_raises():
    with pytest.raises(ValueError):
        D.compute("2026-13-01", preset="민사-항소")
    with pytest.raises(ValueError):
        D.compute("2026-10-15", preset="없는것")
    with pytest.raises(ValueError):
        D.compute("2026-10-15", n=3, unit="시간")


def test_deadline_cli(capsys):
    assert D.main(["calc", "2026-10-17", "--preset", "민사-항소", "--today", "2026-10-20"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True and out["expires"] == "2026-11-02" and out["weekday"] == "월"
    assert D.main(["presets"]) == 0
    assert "민사-항소" in json.loads(capsys.readouterr().out)["presets"]
    assert D.main(["calc", "2026-10-17", "--preset", "없는것"]) == 3
    assert json.loads(capsys.readouterr().out)["ok"] is False


# ---- 비용 ----

@pytest.mark.parametrize("value,stamp", [(100000, 1000), (5000000, 25000), (30000000, 140000),
                                         (123456789, 548800), (2000000000, 7555000), (9999999, 49900)])
def test_stamp_first_instance(value, stamp):
    assert C.stamp(value)["amount"] == stamp


def test_stamp_appeal_and_electronic():
    assert C.stamp(30000000, doc="항소장")["amount"] == 210000
    assert C.stamp(30000000, doc="상고장")["amount"] == 280000
    assert C.stamp(30000000, electronic=True)["amount"] == 126000
    assert C.stamp(30000000, doc="항소장", electronic=True)["amount"] == 189000
    assert C.stamp(30000000, doc="지급명령")["amount"] == 14000
    r = C.stamp(30000000, doc="항소장")
    assert "제3조" in r["law"] and r["base"] == 140000


def test_service_fee_needs_unit():
    r = C.service("민사단독", parties=2)
    assert r["rounds"] == 30 and r["amount"] is None and "단가" in r["note"]
    r = C.service("민사소액", parties=3, unit=5500)
    assert r["rounds"] == 30 and r["amount"] == 165000
    with pytest.raises(ValueError):
        C.service("없는사건", parties=2)


def test_interest_segments_inclusive_days():
    """2026-01-01 ~ 2026-12-31 = 365일. 1,000만원 × 5% = 500,000원. 원 미만 버림."""
    r = C.interest(10000000, [("2026-01-01", "2026-12-31", 0.05)])
    assert r["segments"][0]["days"] == 365 and r["total"] == 500000
    r = C.interest(10000000, [("2026-01-01", "2026-03-15", "민사"), ("2026-03-16", "2026-04-15", "소촉법")])
    assert [s["days"] for s in r["segments"]] == [74, 31]
    assert [s["amount"] for s in r["segments"]] == [101369, 101917] and r["total"] == 203286
    assert float(C.RATES["상사"]) == 0.06
    with pytest.raises(ValueError):
        C.interest(1000, [("2026-02-01", "2026-01-01", 0.05)])


def test_costs_cli(capsys):
    assert C.main(["stamp", "30000000", "--doc", "항소장"]) == 0
    assert json.loads(capsys.readouterr().out)["amount"] == 210000
    assert C.main(["interest", "10000000", "--segment", "2026-01-01:2026-12-31:민사"]) == 0
    assert json.loads(capsys.readouterr().out)["total"] == 500000
    assert C.main(["service", "민사단독", "--parties", "2"]) == 0
    assert json.loads(capsys.readouterr().out)["rounds"] == 30


# ---- 공통 ----

@pytest.mark.parametrize("name", ["deadline.py", "costs.py"])
def test_stdlib_only_and_py39(name):
    src = open(os.path.join(SCRIPTS, name), encoding="utf-8").read()
    tree = ast.parse(src, feature_version=(3, 9))
    mods = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    mods |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert mods <= {"argparse", "calendar", "datetime", "fractions", "json", "math", "os", "sys"}, mods


def test_holiday_table_shape():
    h = json.load(open(os.path.join(ROOT, "skills", "litigation-calc", "references", "holidays.json"), encoding="utf-8"))
    assert h["years"] == [2024, 2027] and h["source"]
    assert all(date.fromisoformat(k).year in range(2024, 2028) for k in h["holidays"])
    assert h["holidays"]["2026-05-01"] == "노동절"
