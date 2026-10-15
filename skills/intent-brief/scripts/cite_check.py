"""초안 인용(조문·판례)을 법제처 Open API 원문과 정확 일치로 대조한다.

모델이 검색 결과를 옮겨 적지 않는다 — 이 스크립트가 lawapi.py 로 법제처 DRF 를 직접 부른다(MCP 없음).
판례는 사건번호 검색(nb) 결과의 사건번호가 정확히 같은 항목만 「확인됨」으로 본다. 「확인됨」은 그 조문·판례가
존재한다는 뜻이며 인용의 적합성은 보증하지 않는다. 키(OC)가 없으면 대조하지 않고 멈춘다(태그도 붙이지 않는다).

사용:
  cite_check.py ping
  cite_check.py extract <draft.md>
  cite_check.py run <draft.md> [--max-seconds 540]
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths as P  # noqa: E402
import lawapi as L  # noqa: E402


# ── 추출 ──────────────────────────────────────────────────────
LAW_NAMES = ["민사소송법", "민사조정법", "민사집행법", "민법", "상법", "이자제한법", "소송촉진 등에 관한 특례법",
             "가사소송법", "행정소송법", "헌법", "주택임대차보호법", "상가건물 임대차보호법", "근로기준법"]
_LAW_STOP = {"방법", "증거방법", "위법", "적법", "불법", "편법", "입법", "사법", "해석법", "문법", "수법", "필법", "기법", "작법"}
_TOKEN = re.compile(r"(?P<law>%s|같은 법|동법|[가-힣]{2,15}법)|(?P<art>제\s*(?P<n>\d+)\s*조(?:\s*의\s*(?P<m>\d+))?)"
                    % "|".join(re.escape(x) for x in LAW_NAMES))
_CASE_FULL = re.compile(r"(?P<court>대법원|[가-힣]+(?:고등|지방)법원)\s*(?P<y>\d{4})\.\s*(?P<mo>\d{1,2})\.\s*(?P<d>\d{1,2})\.\s*"
                        r"(?:선고|자)\s*(?P<nums>\d{2,4}[가-힣]{1,4}\d+(?:\s*,\s*\d+)*)\s*(?:전원합의체\s*)?(?:판결|결정)")
_CASE_BARE = re.compile(r"(?P<nums>\d{4}[가-힣]{1,4}\d{1,7})\s*(?:전원합의체\s*)?(?:판결|결정)")


def _strip_header(md):
    """사건 표시(sec.header) 구간의 우리 사건번호는 대조 대상이 아니다."""
    m = re.search(r"^##\s*\[sec:sec\.header\].*?(?=^##\s|\Z)", md, re.M | re.S)
    if not m:
        return md
    return md[:m.start()] + " " * (m.end() - m.start()) + md[m.end():]


def extract(md):
    text = _strip_header(md)
    laws, cases, seen = [], [], set()
    cur, last_end = None, -999
    for m in _TOKEN.finditer(text):
        if m.group("law"):
            name = m.group("law")
            if name in ("같은 법", "동법"):
                last_end = m.end()
                continue
            if name in _LAW_STOP or name.endswith("방법"):
                cur = None
                continue
            cur, last_end = name, m.end()
        elif m.group("art") and cur and m.start() - last_end <= 25:
            n, sub = int(m.group("n")), int(m.group("m")) if m.group("m") else 0
            key = ("law", cur, n, sub)
            if key not in seen:
                seen.add(key)
                laws.append({"kind": "law", "law": cur, "article": n, "sub": sub, "text": "%s 제%d조%s" % (cur, n, "의%d" % sub if sub else ""),
                             "pos": m.start()})
            last_end = m.end()
    covered = []
    for m in _CASE_FULL.finditer(text):
        covered.append((m.start(), m.end()))
        first = m.group("nums").split(",")[0].strip()
        prefix = re.match(r"(\d{2,4}[가-힣]{1,4})", first).group(1)
        date = "%04d%02d%02d" % (int(m.group("y")), int(m.group("mo")), int(m.group("d")))
        for i, part in enumerate(m.group("nums").split(",")):
            part = part.strip()
            num = part if i == 0 else prefix + part
            key = ("case", num, date)  # 선고일이 다르면 따로 대조 — 틀린 날짜 인용이 묻히지 않게
            if key not in seen:
                seen.add(key)
                cases.append({"kind": "case", "number": num, "court": m.group("court"), "date": date, "text": m.group(0), "pos": m.start()})
    for m in _CASE_BARE.finditer(text):
        if any(a <= m.start() < b for a, b in covered):
            continue
        num = m.group("nums")
        key = ("case", num, None)
        if key not in seen and not any(k[:2] == ("case", num) for k in seen):
            seen.add(key)
            cases.append({"kind": "case", "number": num, "court": None, "date": None, "text": m.group(0), "pos": m.start()})
    return laws + cases


# ── 대조 ──────────────────────────────────────────────────────
class CachedClient:
    """같은 요청은 작업 폴더 캐시에서 — 다시 실행하면 이어 간다. 캐시에는 키(OC)를 남기지 않는다."""

    def __init__(self, inner, cache_dir, deadline=None):
        self.inner = inner
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.deadline = deadline
        self.calls = 0

    def get(self, path, **params):
        key = hashlib.sha256(json.dumps([path, params], sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:24]
        fp = os.path.join(self.cache_dir, key + ".json")
        if os.path.exists(fp):
            return P.load_json(fp)
        if self.deadline and time.time() > self.deadline:
            raise TimeoutError("시간 상한")
        obj = self.inner.get(path, **params)
        self.calls += 1
        P.atomic_write_text(fp, L._mask(json.dumps(obj, ensure_ascii=False)))
        P.atomic_write_json(fp[:-5] + ".req.json", {"path": path, "params": params})
        return obj


def _norm_no(s):
    return re.sub(r"\s+", "", s or "")


def _excerpt_case(d):
    out = []
    for label, k in (("판시사항", "holdings"), ("판결요지", "summary")):
        if d.get(k):
            out.append("%s: %s" % (label, re.sub(r"\s+", " ", d[k]).strip()[:300]))
    return " / ".join(out)


class Checker:
    def __init__(self, cache_dir, client=None, deadline=None):
        self.client = CachedClient(client or L.Client(), cache_dir, deadline)

    @property
    def calls(self):
        return self.client.calls

    def check_law(self, c):
        law = L.search_law(self.client, c["law"])
        if not law:
            return {"status": "unverified", "detail": "법령명 정확 일치 없음"}
        art = L.get_article(self.client, law["law_id"], c["article"], c["sub"])
        if not art:
            return {"status": "unverified", "detail": "조문 본문 없음", "law_id": law["law_id"]}
        body = " ".join([art["text"]] + art["paragraphs"][:1])
        return {"status": "confirmed", "law_id": law["law_id"], "excerpt": re.sub(r"\s+", " ", body)[:200]}

    def check_case(self, c):
        hits = L.find_prec_exact(self.client, c["number"])
        if c.get("court"):
            same = [h for h in hits if _norm_no(h["court"]) == _norm_no(c["court"])]
            hits = same or hits
        if hits:
            hit = next((h for h in hits if c.get("date") and h["date"] == c["date"]), hits[0])
            if c.get("date") and hit["date"] and hit["date"] != c["date"]:
                return {"status": "unverified", "detail": "선고일 불일치(원문 %s)" % hit["date"], "prec_id": hit["prec_id"]}
            d = L.get_prec(self.client, hit["prec_id"])
            return {"status": "confirmed", "prec_id": hit["prec_id"], "title": hit["title"], "date": hit["date"],
                    "excerpt": _excerpt_case(d) if d else ""}
        cited_by, _ = L.search_prec(self.client, query=c["number"], fulltext=True, display=1)
        detail = "사건번호 정확 일치 없음(법제처 원문 없음)"
        if cited_by:
            detail += " · 이 번호를 인용한 다른 판결 %d건 검색됨 — 원문은 변호사가 확인" % cited_by
        return {"status": "unverified", "detail": detail, "cited_by": cited_by}

    def check(self, c):
        try:
            return self.check_law(c) if c["kind"] == "law" else self.check_case(c)
        except L.KeyInvalid as e:
            return {"status": "key_invalid", "detail": str(e)[:200]}
        except L.Unavailable as e:
            return {"status": "outage", "detail": str(e)[:200]}
        except L.FormatChanged as e:
            return {"status": "format_changed", "detail": str(e)[:200]}
        except TimeoutError:
            return {"status": "pending", "detail": "시간 상한 — 다시 실행하면 캐시에서 이어 갑니다"}


TAG_FOR = {"unverified": "unverified", "outage": "outage", "format_changed": "format_changed", "key_invalid": "key_invalid"}


def tag_draft(md, results, phrases):
    """확인되지 않은 인용 뒤에 태그를 한 번 붙인다(이미 붙어 있으면 그대로)."""
    for r in sorted(results, key=lambda x: -x["pos"]):
        key = TAG_FOR.get(r["status"])
        if not key:
            continue
        tag = phrases["tag"][key]
        idx = md.find(r["text"])
        if idx < 0:
            continue
        end = idx + len(r["text"])
        if md[end:end + len(tag) + 1].strip().startswith(tag):
            continue
        md = md[:end] + " " + tag + md[end:]
    return md


def run(draft_path, max_seconds=540, client=None):
    md = P.read_text(draft_path)
    work = os.path.dirname(os.path.abspath(draft_path))
    cites = extract(md)
    chk = Checker(os.path.join(work, "cite"), client=client, deadline=time.time() + max_seconds)
    results = []
    for c in cites:
        r = dict(c)
        r.update(chk.check(c))
        results.append(r)
    complete = all(r["status"] != "pending" for r in results)
    if complete:
        P.atomic_write_text(draft_path, tag_draft(md, results, P.load_phrases()))
    summary = {}
    for r in results:
        summary[r["status"]] = summary.get(r["status"], 0) + 1
    out = {"complete": complete, "calls": chk.calls, "summary": summary, "results": results}
    P.atomic_write_json(os.path.join(work, "cite_results.json"), out)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ping")
    s = sub.add_parser("extract"); s.add_argument("draft")
    s = sub.add_parser("run"); s.add_argument("draft"); s.add_argument("--max-seconds", type=float, default=540)
    a = ap.parse_args(argv)
    if a.cmd == "ping":
        oc, src = L.find_key()
        if not oc:
            return P.emit({"ok": False, "error": "no_key", "guide": L.KEY_GUIDE})
        try:
            L.find_prec_exact(L.Client(oc=oc), "2016다225353")
            return P.emit({"ok": True, "key_source": src})
        except L.KeyInvalid as e:
            return P.emit({"ok": False, "error": "key_invalid", "detail": str(e), "guide": L.KEY_GUIDE})
        except (L.Unavailable, L.FormatChanged) as e:
            return P.emit({"ok": False, "error": "outage", "detail": str(e), "note": "인용 대조만 장애 태그로 표시하고 계속합니다"})
    if a.cmd == "extract":
        return P.emit({"ok": True, "citations": extract(P.read_text(a.draft))})
    if a.cmd == "run":
        try:
            return P.emit(dict(ok=True, **run(a.draft, a.max_seconds)))
        except L.NoKey as e:
            return P.emit({"ok": False, "error": "no_key", "guide": str(e)}, 4)


if __name__ == "__main__":
    sys.exit(main())
