"""법제처 Open API(DRF) 직접 호출 — 법령·조문·판례·법령용어. 키(OC)는 변호사에게 받아 작업 폴더에 저장한다.

MCP 를 거치지 않는다. 표준 라이브러리만 쓴다.
키 찾는 순서: 환경변수 INTENT_BRIEF_LAW_OC → LAW_API_OC → 작업 폴더 config.json 의 law_oc.
키 값은 어떤 출력에도 쓰지 않는다(URL 이 오류에 섞이면 OC=*** 로 가린다).

사용:
  lawapi.py key status                       키 등록 여부·출처(값은 출력하지 않음)
  lawapi.py key set (<OC> | --stdin) [--no-check]   키 저장(기본: 판례 1건 조회로 검증 뒤 저장)
  lawapi.py key clear
  lawapi.py law <법령명> [--article 288 | 266-2]
  lawapi.py prec-search <검색어> [--nb | --fulltext] [--court 대법원] [--display 20] [--page 1]
  lawapi.py prec <판례일련번호>
  lawapi.py term <법령용어>
  lawapi.py search <target> <검색어> [--display 20] [--page 1] [--fulltext]   expc(법령해석례)·detc(헌재결정) 등
  lawapi.py detail <target> <ID>
"""
import argparse
import getpass
import http.client
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths as P  # noqa: E402

BASE_URL = "https://www.law.go.kr/DRF"
TIMEOUT = 20.0
MIN_INTERVAL = 1.0  # 요청 간 최소 간격(초) — 짧으면 빈 응답(요청 제한)이 온다
RETRIES = 2
KEY_GUIDE = ("법제처 Open API 키(OC)가 필요합니다. https://open.law.go.kr 에서 회원가입 → OPEN API 사용 신청"
             "(법령·판례) 후 받은 OC 값을 `/lawfirm:law-key-setup` 의 입력 창에 넣으면 저장합니다(채팅에 적지 않습니다). "
             "신청 때 이 PC 의 IP 주소 등록을 요구할 수 있습니다.")


def _osascript_dialog(message, title, hidden):
    esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')
    script = ('display dialog "%s" default answer "" %swith title "%s" '
              'buttons {"취소", "확인"} default button "확인" cancel button "취소"\n'
              "text returned of result") % (esc(message), "with hidden answer " if hidden else "", esc(title))
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=600, check=False)
    if r.returncode != 0:
        raise P.BriefError("입력을 취소했습니다")
    return r.stdout.rstrip("\n")


def _windows_dialog(message, title, hidden):
    msg, ttl = message.replace("'", "''"), title.replace("'", "''")
    if hidden:
        ps = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
              "$c=Get-Credential -UserName '%s' -Message '%s';"
              "if(-not $c){exit 1};[Console]::Out.Write($c.GetNetworkCredential().Password)") % (ttl, msg)
    else:
        ps = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8;Add-Type -AssemblyName Microsoft.VisualBasic;"
              "$v=[Microsoft.VisualBasic.Interaction]::InputBox('%s','%s');"
              "if(-not $v){exit 1};[Console]::Out.Write($v)") % (msg, ttl)
    r = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps], capture_output=True, timeout=600, check=False)
    if r.returncode != 0:
        raise P.BriefError("입력을 취소했습니다")
    return r.stdout.decode("utf-8", "replace")


def _ask(message, title, hidden):
    """사람에게 값을 받는다 — 터미널이면 프롬프트, 아니면 OS 입력 창(macOS·Windows). 채팅·명령행 인자는 쓰지 않는다."""
    if sys.stdin is not None and sys.stdin.isatty():
        return getpass.getpass(message + ": ") if hidden else input(message + ": ")
    if sys.platform == "darwin":
        return _osascript_dialog(message, title, hidden)
    if os.name == "nt":
        return _windows_dialog(message, title, hidden)
    raise P.BriefError("입력 창을 띄울 수 없습니다 — 자기 터미널에서 같은 명령을 직접 실행하십시오")


def ask(message, title):
    """법제처 키(OC)는 비밀번호가 아니라 가입 아이디라 보이게 받는다."""
    return _ask(message, title, hidden=False)


class NoKey(Exception):
    """키가 없다 — 변호사에게 받아야 한다."""


class KeyInvalid(Exception):
    """법제처가 사용자 검증 실패를 돌려줬다(키 오류 또는 IP·도메인 미등록)."""


class Unavailable(Exception):
    """연결 실패·타임아웃·5xx·빈 응답."""


class FormatChanged(Exception):
    """응답을 해석하지 못했다."""


# ── 키 ────────────────────────────────────────────────────────
def config_path():
    return os.path.join(P.work_root(), "config.json")


def _load_config():
    p = config_path()
    return P.load_json(p) if os.path.exists(p) else {}


def find_key():
    """(키, 출처) — 없으면 (None, None)."""
    for env in ("INTENT_BRIEF_LAW_OC", "LAW_API_OC"):
        v = (os.environ.get(env) or "").strip()
        if v:
            return v, "env:%s" % env
    v = (_load_config().get("law_oc") or "").strip()
    return (v, "config") if v else (None, None)


def save_key(oc):
    oc = (oc or "").strip()
    if not oc or re.search(r"\s", oc):
        raise P.BriefError("키(OC) 형식이 올바르지 않습니다")
    cfg = _load_config()
    cfg["law_oc"] = oc
    path = config_path()
    P.atomic_write_json(path, cfg)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def clear_key():
    cfg = _load_config()
    had = cfg.pop("law_oc", None) is not None
    if had:
        P.atomic_write_json(config_path(), cfg)
    return had


# ── HTTP ──────────────────────────────────────────────────────
def base_url():
    return os.environ.get("INTENT_BRIEF_LAW_URL") or BASE_URL  # 개발·테스트 전용(가짜 서버)


def _mask(s):
    return re.sub(r"OC=[^&\s\"']+", "OC=***", str(s))


class Client:
    def __init__(self, oc=None, timeout=TIMEOUT, interval=MIN_INTERVAL, backoff=1.5):
        if oc is None:
            oc, _ = find_key()
        if not oc:
            raise NoKey(KEY_GUIDE)
        self.oc = oc
        self.timeout = timeout
        self.interval = interval
        self.backoff = backoff
        self._last = 0.0
        self.calls = 0

    def get(self, path, **params):
        q = dict(params, OC=self.oc, type="JSON")
        url = "%s/%s?%s" % (base_url(), path, urllib.parse.urlencode(q))
        err = None
        for attempt in range(RETRIES + 1):
            wait = self.interval - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
            try:
                with urllib.request.urlopen(url, timeout=self.timeout) as r:
                    body = r.read().decode("utf-8")
                self.calls += 1
            except UnicodeDecodeError:
                raise Unavailable("응답을 UTF-8 로 읽지 못했습니다")
            except urllib.error.HTTPError as e:
                err = Unavailable("HTTP %s" % e.code)
                if e.code >= 500 or e.code == 429:
                    time.sleep(self.backoff * (attempt + 1))
                    continue
                raise err
            except (urllib.error.URLError, http.client.HTTPException, TimeoutError, socket.timeout, OSError) as e:
                err = Unavailable("연결 실패 또는 타임아웃: %s" % _mask(e))
                time.sleep(self.backoff * (attempt + 1))
                continue
            if not body.strip():
                err = Unavailable("빈 응답(요청 제한일 수 있음)")
                time.sleep(self.backoff * (attempt + 1))
                continue
            try:
                obj = json.loads(body)
            except ValueError:
                raise FormatChanged("JSON 이 아닌 응답: %s" % _mask(body[:120]))
            if isinstance(obj, dict) and "사용자 정보 검증" in str(obj.get("result", "")):
                raise KeyInvalid("법제처 사용자 검증 실패 — 키(OC)가 틀렸거나 이 PC 의 IP·도메인이 등록되지 않았습니다")
            return obj
        raise err


def _list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _nows(s):
    return re.sub(r"\s+", "", s or "")


# ── 법령·조문 ─────────────────────────────────────────────────
def search_law(client, name):
    """법령명(또는 약칭) 정확 일치 → {law_id, name, mst, effective} 또는 None."""
    obj = client.get("lawSearch.do", target="law", query=name, display=20)
    root = obj.get("LawSearch")
    if not isinstance(root, dict):
        raise FormatChanged("LawSearch 없음")
    want = _nows(name)
    for it in _list(root.get("law")):
        if want in (_nows(it.get("법령명한글")), _nows(it.get("법령약칭명"))) and it.get("현행연혁코드", "현행") == "현행":
            return {"law_id": it.get("법령ID"), "name": it.get("법령명한글"), "mst": it.get("법령일련번호"),
                    "effective": it.get("시행일자")}
    return None


def get_article(client, law_id, article, sub=0):
    """조문 본문 — 제목 줄(편·장)이 아니라 조문여부 「조문」인 항목. 없으면 None."""
    jo = "%04d%02d" % (int(article), int(sub))
    obj = client.get("lawService.do", target="law", ID=law_id, JO=jo)
    law = obj.get("법령")
    if not isinstance(law, dict):
        raise FormatChanged("법령 없음")
    units = _list((law.get("조문") or {}).get("조문단위"))
    head = "제%d조%s" % (int(article), "의%d" % int(sub) if sub else "")
    for u in units:
        text = (u.get("조문내용") or "").strip()
        if u.get("조문여부") == "조문" and re.match(re.escape(head) + r"\s*\(", text):
            paras = []
            for h in _list(u.get("항")):
                c = h.get("항내용") if isinstance(h, dict) else None
                if c:
                    paras.append(c if isinstance(c, str) else " ".join(c))
            return {"head": head, "title": u.get("조문제목"), "text": text, "paragraphs": paras,
                    "effective": u.get("조문시행일자")}
    return None


# ── 판례 ──────────────────────────────────────────────────────
def _prec_item(it):
    return {"prec_id": it.get("판례일련번호"), "number": it.get("사건번호"), "court": it.get("법원명"),
            "date": (it.get("선고일자") or "").replace(".", ""), "title": it.get("사건명"),
            "kind": it.get("판결유형"), "type": it.get("사건종류명")}


def search_prec(client, query=None, nb=None, display=20, page=1, fulltext=False, court=None):
    """판례 목록. nb 는 사건번호 검색(정확 일치 후보), query 는 사건명(기본)·본문(fulltext) 검색."""
    params = {"target": "prec", "display": display, "page": page}
    if nb:
        params["nb"] = nb
    else:
        params["query"] = query
        if fulltext:
            params["search"] = 2
    if court:
        params["curt"] = court
    obj = client.get("lawSearch.do", **params)
    root = obj.get("PrecSearch")
    if not isinstance(root, dict):
        raise FormatChanged("PrecSearch 없음")
    try:
        total = int(root.get("totalCnt") or 0)
    except ValueError:
        raise FormatChanged("totalCnt 해석 실패")
    return total, [_prec_item(it) for it in _list(root.get("prec"))]


_BR = re.compile(r"<br\s*/?>", re.I)
_TAGS = re.compile(r"<[^>]+>")


def clean(s):
    return re.sub(r"[ \t]+", " ", _TAGS.sub("", _BR.sub("\n", s or ""))).strip()


def get_prec(client, prec_id):
    obj = client.get("lawService.do", target="prec", ID=prec_id)
    ps = obj.get("PrecService")
    if not isinstance(ps, dict):
        return None  # 법제처가 본문을 주지 않는 판례(목록에만 있음)
    return {"prec_id": str(prec_id), "number": ps.get("사건번호"), "court": ps.get("법원명"),
            "date": (ps.get("선고일자") or "").replace(".", ""), "title": ps.get("사건명"), "kind": ps.get("판결유형"),
            "holdings": clean(ps.get("판시사항")), "summary": clean(ps.get("판결요지")),
            "ref_articles": clean(ps.get("참조조문")), "ref_cases": clean(ps.get("참조판례")),
            "body": clean(ps.get("판례내용"))}


def find_prec_exact(client, number):
    """사건번호 정확 일치 판례 목록(같은 번호의 여러 판결이 있을 수 있다)."""
    want = _nows(number)
    _, items = search_prec(client, nb=number, display=20)
    return [it for it in items if _nows(it["number"]) == want]


# ── 법령용어 ──────────────────────────────────────────────────
def search_term(client, term):
    obj = client.get("lawSearch.do", target="lstrm", query=term, display=10)
    root = obj.get("LsTrmSearch") or obj.get("lstrmSearch") or {}
    items = _list(root.get("lstrm"))
    return [{"term": it.get("법령용어명"), "id": it.get("법령용어ID") or it.get("법령용어 일련번호"),
             "link": _mask(it.get("법령용어상세링크") or "")} for it in items]


# ── 그 밖의 목록 — 법령해석례(expc)·헌재결정(detc)·행정규칙(admrul) 등 ─────────
TARGETS = {"law", "prec", "expc", "detc", "admrul", "lstrm", "ordin", "trty"}


def _target(t):
    if t not in TARGETS:
        raise P.BriefError("target 은 %s 중 하나입니다" % "·".join(sorted(TARGETS)))
    return t


def search(client, target, query, display=20, page=1, fulltext=False):
    """원 응답(JSON) 그대로 — 목록 키는 target 마다 다르다(예: expc → Expc, detc → Detc)."""
    params = {"target": _target(target), "query": query, "display": display, "page": page}
    if fulltext:
        params["search"] = 2
    return client.get("lawSearch.do", **params)


def detail(client, target, item_id):
    return client.get("lawService.do", target=_target(target), ID=item_id)


# ── CLI ───────────────────────────────────────────────────────
def _art(s):
    m = re.fullmatch(r"(\d+)(?:-(\d+))?", s or "")
    if not m:
        raise P.BriefError("--article 은 288 또는 266-2 형식입니다")
    return int(m.group(1)), int(m.group(2) or 0)


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("key"); ks = k.add_subparsers(dest="kcmd", required=True)
    ks.add_parser("status")
    s = ks.add_parser("set"); s.add_argument("--prompt", action="store_true"); s.add_argument("--stdin", action="store_true")
    s.add_argument("--no-check", action="store_true")
    ks.add_parser("clear")
    s = sub.add_parser("law"); s.add_argument("name"); s.add_argument("--article")
    s = sub.add_parser("prec-search"); s.add_argument("query"); s.add_argument("--nb", action="store_true")
    s.add_argument("--fulltext", action="store_true"); s.add_argument("--court")
    s.add_argument("--display", type=int, default=20); s.add_argument("--page", type=int, default=1)
    s = sub.add_parser("prec"); s.add_argument("prec_id")
    s = sub.add_parser("term"); s.add_argument("term")
    s = sub.add_parser("search"); s.add_argument("target"); s.add_argument("query")
    s.add_argument("--display", type=int, default=20); s.add_argument("--page", type=int, default=1)
    s.add_argument("--fulltext", action="store_true")
    s = sub.add_parser("detail"); s.add_argument("target"); s.add_argument("item_id")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "key":
            if a.kcmd == "status":
                oc, src = find_key()
                return P.emit({"ok": True, "configured": bool(oc), "source": src, "config": config_path(),
                               "guide": None if oc else KEY_GUIDE})
            if a.kcmd == "set":
                if a.prompt:
                    oc = ask("법제처 Open API 키(OC)를 입력하십시오. https://open.law.go.kr → OPEN API 사용 신청에서 받은 값입니다",
                             "법제처 Open API")
                elif a.stdin:
                    oc = sys.stdin.readline()
                else:
                    raise P.BriefError("키(OC)는 --prompt(입력 창) 또는 --stdin 으로만 받습니다 — 명령행에 남기지 않습니다")
                oc = (oc or "").strip()
                if not oc:
                    raise P.BriefError("빈 키는 저장하지 않습니다")
                if not a.no_check:
                    find_prec_exact(Client(oc=oc), "2016다225353")  # 키·IP 검증(실패면 저장하지 않음)
                return P.emit({"ok": True, "saved": save_key(oc), "checked": not a.no_check})
            return P.emit({"ok": True, "cleared": clear_key()})
        c = Client()
        if a.cmd == "law":
            law = search_law(c, a.name)
            if not law:
                return P.emit({"ok": True, "found": False, "detail": "법령명 정확 일치 없음"})
            out = {"ok": True, "found": True, "law": law}
            if a.article:
                n, m = _art(a.article)
                out["article"] = get_article(c, law["law_id"], n, m)
            return P.emit(out)
        if a.cmd == "prec-search":
            total, items = search_prec(c, nb=a.query if a.nb else None, query=None if a.nb else a.query,
                                       display=a.display, page=a.page, fulltext=a.fulltext, court=a.court)
            return P.emit({"ok": True, "total": total, "page": a.page, "items": items})
        if a.cmd == "prec":
            d = get_prec(c, a.prec_id)
            return P.emit({"ok": True, "found": bool(d), "prec": d})
        if a.cmd == "term":
            return P.emit({"ok": True, "items": search_term(c, a.term)})
        if a.cmd == "search":
            return P.emit({"ok": True, "result": json.loads(_mask(json.dumps(
                search(c, a.target, a.query, a.display, a.page, a.fulltext), ensure_ascii=False)))})
        if a.cmd == "detail":
            return P.emit({"ok": True, "result": json.loads(_mask(json.dumps(detail(c, a.target, a.item_id), ensure_ascii=False)))})
    except NoKey as e:
        return P.emit({"ok": False, "error": "no_key", "guide": str(e)}, 4)
    except KeyInvalid as e:
        return P.emit({"ok": False, "error": "key_invalid", "detail": str(e), "guide": KEY_GUIDE}, 4)
    except Unavailable as e:
        return P.emit({"ok": False, "error": "outage", "detail": str(e)}, 5)
    except FormatChanged as e:
        return P.emit({"ok": False, "error": "format_changed", "detail": str(e)}, 5)
    except P.BriefError as e:
        return P.fail(str(e))


if __name__ == "__main__":
    sys.exit(main())
