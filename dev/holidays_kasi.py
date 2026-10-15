"""개발 전용 — 한국천문연구원 특일정보(공공데이터포털 15012690) 공휴일을 받아 litigation-calc 공휴일 표를 만든다.

  KASI_SERVICE_KEY=<공공데이터포털 일반 인증키> python3 dev/holidays_kasi.py 2024 2028

키는 환경변수로만 받고 출력하지 않는다(없으면 DATA_GO_KR_API_KEY). 결과는
skills/litigation-calc/references/holidays.json — 런타임(deadline.py)은 이 표만 읽고 네트워크를 쓰지 않는다.
표 범위 밖 연도의 만료일은 deadline.py 가 「공휴일 표 범위 밖」으로 표시한다.
"""
import json
import os
import sys
import urllib.parse
import urllib.request

URL = "https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills", "litigation-calc", "references", "holidays.json")


def fetch(year, key):
    days = {}
    for month in range(1, 13):
        q = "serviceKey=%s&%s" % (key if "%" in key else urllib.parse.quote(key, safe=""),
                                  urllib.parse.urlencode({"solYear": year, "solMonth": "%02d" % month, "_type": "json", "numOfRows": 50}))
        with urllib.request.urlopen(URL + "?" + q, timeout=30) as r:
            body = json.loads(r.read().decode("utf-8"))
        header = body["response"]["header"]
        if header.get("resultCode") != "00":
            raise SystemExit("특일정보 오류: %s" % header.get("resultMsg"))
        items = (body["response"]["body"].get("items") or {}) or {}
        items = items.get("item") if isinstance(items, dict) else []
        for it in ([items] if isinstance(items, dict) else items or []):
            if it.get("isHoliday") == "Y":
                d = str(it["locdate"])
                days["%s-%s-%s" % (d[:4], d[4:6], d[6:])] = it.get("dateName")
    return days


def main():
    key = os.environ.get("KASI_SERVICE_KEY") or os.environ.get("DATA_GO_KR_API_KEY")
    if not key:
        raise SystemExit("KASI_SERVICE_KEY 환경변수가 필요합니다")
    first, last = int(sys.argv[1]), int(sys.argv[2])
    days = {}
    for y in range(first, last + 1):
        days.update(fetch(y, key.strip().strip('"')))
    out = {"source": "한국천문연구원 특일정보(공공데이터포털 15012690) getRestDeInfo isHoliday=Y",
           "years": [first, last], "note": "일요일은 표에 없어도 공휴일로 본다(관공서의 공휴일에 관한 규정 제2조 제1호). "
           "임시공휴일은 지정 뒤 이 표를 다시 만들거나 deadline.py --holiday 로 더한다.",
           "holidays": dict(sorted(days.items()))}
    with open(os.path.normpath(OUT), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("공휴일 %d일 (%d–%d) → %s" % (len(days), first, last, os.path.normpath(OUT)))


if __name__ == "__main__":
    main()
