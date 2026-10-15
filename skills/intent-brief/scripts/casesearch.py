"""case-search 플러그인(빅케이스 판례 검색)이 설치·로그인돼 있으면 연결한다 — 없으면 조용히 빠진다.

case-search 는 Python 3.10+ 와 외부 패키지가 필요해 import 하지 않고 `uv run <installPath>/scripts/bigcase.py` 로 부른다.
변호사 본인의 빅케이스 계정(OS 키체인)을 쓴다 — 토큰이 만료돼 있으면 case-search 가 키체인 비밀번호로 다시 로그인한다.
이용 범위(case-search 안내): 본인 계정으로, 사람이 화면에서 찾는 정도의 빈도로만. 대량 수집·페이지 끝까지 넘기기 금지.
그래서 인용 대조는 법제처에 원문이 없는 판례 한 건당 한 번만 부른다. 토큰·비밀번호는 출력하지 않는다.

사용:
  casesearch.py status                 설치·로그인 여부(네트워크 없음)
  casesearch.py search <검색어> [--page 1]
  casesearch.py case <법원> <사건번호>
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths as P  # noqa: E402

PLUGIN_KEY = "case-search@case-search"
STATUS_TIMEOUT = 180  # 첫 실행은 uv 가 의존성을 받느라 오래 걸린다
CALL_TIMEOUT = 90


class SearchError(Exception):
    """case-search 호출 실패(없음과 구분)."""


def _config_dirs():
    out = []
    if os.environ.get("CLAUDE_CONFIG_DIR"):
        out.append(os.environ["CLAUDE_CONFIG_DIR"])
    out.append(os.path.join(os.path.expanduser("~"), ".claude"))
    return out


def find_script():
    for d in _config_dirs():
        p = os.path.join(d, "plugins", "installed_plugins.json")
        if not os.path.exists(p):
            continue
        try:
            entries = (P.load_json(p).get("plugins") or {}).get(PLUGIN_KEY) or []
        except (ValueError, OSError):
            continue
        for e in entries:
            script = os.path.join(e.get("installPath") or "", "scripts", "bigcase.py")
            if os.path.isfile(script):
                return script
    return None


def find_uv():
    v = os.environ.get("INTENT_BRIEF_UV")
    if v:
        return v if os.path.isfile(v) else None
    found = shutil.which("uv")
    if found:
        return found
    home = os.path.expanduser("~")
    for c in (os.path.join(home, ".local", "bin", "uv"), os.path.join(home, ".cargo", "bin", "uv"),
              os.path.join(home, ".local", "bin", "uv.exe")):
        if os.path.isfile(c):
            return c
    return None


def _run(uv, script, args, timeout):
    try:
        p = subprocess.run([uv, "run", "-q", script] + list(args), capture_output=True, timeout=timeout,
                           cwd=os.path.dirname(script))
    except (OSError, subprocess.TimeoutExpired) as e:
        raise SearchError("case-search 실행 실패: %s" % e.__class__.__name__)
    out = p.stdout.decode("utf-8", "replace")
    err = p.stderr.decode("utf-8", "replace")
    if p.returncode != 0:
        if re.search(r"HTTP 404", err):
            return None
        raise SearchError(err.strip().splitlines()[-1][:200] if err.strip() else "종료 코드 %d" % p.returncode)
    try:
        return json.loads(out)
    except ValueError:
        raise SearchError("case-search 응답을 해석하지 못했습니다")


def detect():
    """{available, logged_in, reason} — 설치·uv·로그인 셋 중 하나라도 없으면 available False."""
    if os.environ.get("INTENT_BRIEF_NO_CASESEARCH"):
        return {"available": False, "reason": "INTENT_BRIEF_NO_CASESEARCH 로 꺼 둠"}
    script = find_script()
    if not script:
        return {"available": False, "reason": "case-search 플러그인이 설치돼 있지 않음"}
    uv = find_uv()
    if not uv:
        return {"available": False, "reason": "case-search 실행에 필요한 uv 가 없음"}
    try:
        st = _run(uv, script, ["status"], STATUS_TIMEOUT) or {}
    except SearchError as e:
        return {"available": False, "reason": str(e)}
    logged = bool(st.get("email")) and bool(st.get("password_saved"))
    if not logged:
        return {"available": False, "logged_in": False, "reason": "빅케이스 로그인 정보 없음(case-search 의 setup 필요)"}
    return {"available": True, "logged_in": True, "script": script}


def _date(s):
    return re.sub(r"\D", "", s or "")[:8] or None


def _hit(o):
    return {"number": o.get("case_number"), "court": o.get("court"), "date": _date(o.get("judgment_date")),
            "expression": o.get("case_expression"), "outcome": o.get("outcome"), "restricted": bool(o.get("restricted"))}


class Client:
    def __init__(self, script, uv):
        self.script = script
        self.uv = uv

    def case(self, court, number):
        o = _run(self.uv, self.script, ["case", court, number, "--raw"], CALL_TIMEOUT)
        return _hit(o) if o else None

    def search(self, query, page=1):
        return _run(self.uv, self.script, ["search", query, "--page", str(page)], CALL_TIMEOUT) or {"total": 0, "results": []}

    def find_exact(self, number, court=None):
        """사건번호 정확 일치 1건 — 법원을 알면 case 1회, 모르면 search 1쪽 1회."""
        want = re.sub(r"\s+", "", number)
        if court:
            hit = self.case(court, number)
            return hit if hit and re.sub(r"\s+", "", hit["number"] or "") == want else None
        for r in self.search(number).get("results") or []:
            if re.sub(r"\s+", "", r.get("case_number") or "") == want:
                m = re.search(r"(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.", r.get("case_expression") or "")
                return {"number": r.get("case_number"), "court": r.get("court"),
                        "date": "%s%02d%02d" % (m.group(1), int(m.group(2)), int(m.group(3))) if m else None,
                        "expression": r.get("case_expression"), "outcome": r.get("outcome"), "restricted": None}
        return None


def client():
    st = detect()
    if not st["available"]:
        return None
    return Client(st["script"], find_uv())


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    s = sub.add_parser("search"); s.add_argument("query"); s.add_argument("--page", type=int, default=1)
    s = sub.add_parser("case"); s.add_argument("court"); s.add_argument("number")
    a = ap.parse_args(argv)
    if a.cmd == "status":
        st = detect()
        st.pop("script", None)
        return P.emit(dict(ok=True, **st))
    c = client()
    if not c:
        return P.emit({"ok": False, "error": "unavailable", "reason": detect()["reason"]}, 4)
    try:
        if a.cmd == "search":
            return P.emit(dict(ok=True, **c.search(a.query, a.page)))
        hit = c.case(a.court, a.number)
        return P.emit({"ok": True, "found": bool(hit), "case": hit})
    except SearchError as e:
        return P.emit({"ok": False, "error": "search_error", "detail": str(e)}, 5)


if __name__ == "__main__":
    sys.exit(main())
