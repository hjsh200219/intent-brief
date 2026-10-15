"""해외 판례 조회 — 미국(CourtListener)·독일(OpenLegalData) 원천 API 를 직접 부른다. 표준 라이브러리만, Python 3.9.

사용:
  foreigncase.py us-search <검색어> [--court scotus] [--after YYYY-MM-DD] [--before YYYY-MM-DD] [--cursor C]
  foreigncase.py us-opinion <opinion_id> [--offset 0]       미국 판결문 본문 — CourtListener 토큰 필요
  foreigncase.py de-search <검색어> [--court BGH] [--level Bundesgericht] [--page 1]
  foreigncase.py de-case <id> [--offset 0]                  독일 판결문 본문
  foreigncase.py key status | key set us|de --prompt | key clear us|de

미국 검색·독일 검색·독일 본문은 익명으로 된다(2026-10-15 실측). 미국 본문(/opinions/<id>/)은 토큰이 없으면 401 —
https://www.courtlistener.com 에서 무료 가입 → 프로필의 API 토큰을 `key set us --prompt`(입력 창)로 저장한다.
토큰은 $CASE_SEARCH_HOME/foreign.json(기본 ~/.case-search, 0600)에 두고 출력하지 않는다. 환경변수
COURTLISTENER_API_TOKEN·OPENLEGALDATA_API_TOKEN 이 있으면 그 값이 먼저다. 토큰은 아래 두 고정 호스트로만 보낸다.
본문은 원문 언어 그대로(번역 없음) WINDOW 자씩 잘라 주고, 이어 읽을 위치(next_offset)를 함께 준다.
"""
import argparse
import getpass
import html
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

US_API = "https://www.courtlistener.com/api/rest/v4"
US_SITE = "https://www.courtlistener.com"
DE_API = "https://de.openlegaldata.io/api"
DE_SITE = "https://de.openlegaldata.io"
WINDOW = 8000
TIMEOUT = 30
USER_AGENT = "lawfirm-case-search (+https://github.com/hjsh200219/lawfirm)"
ENV = {"us": "COURTLISTENER_API_TOKEN", "de": "OPENLEGALDATA_API_TOKEN"}
KEY_GUIDE = ("미국 판결문 본문은 CourtListener API 토큰이 필요합니다. https://www.courtlistener.com 에서 무료 가입 → "
             "프로필의 API 토큰을 `/lawfirm:law-key-setup us` 의 입력 창에 넣으면 저장합니다(검색은 토큰 없이도 됩니다).")


class ForeignError(Exception):
    code = "error"


class NoKey(ForeignError):
    code = "no_key"


class KeyInvalid(ForeignError):
    code = "key_invalid"


class RateLimited(ForeignError):
    code = "rate_limited"


class NotFound(ForeignError):
    code = "not_found"


class Outage(ForeignError):
    code = "outage"


class BadRequest(ForeignError):
    code = "bad_request"


class NetworkBlocked(ForeignError):
    code = "network_blocked"


DIALOG_FAIL = "입력 창을 띄우지 못했습니다(%s) — Codex 샌드박스라면 권한 상승으로 다시 실행하거나, 자기 터미널에서 같은 명령을 직접 실행하십시오"


def http_error(status, detail=""):
    """HTTP 상태 → 오류 분류(테스트도 이 함수로 만든다)."""
    if status in (401, 403):
        return KeyInvalid("인증 실패(HTTP %d) — 토큰이 틀렸거나 만료됐습니다" % status)
    if status == 429:
        return RateLimited("요청이 너무 잦습니다(HTTP 429) — 잠시 뒤 다시 하십시오")
    if status == 404:
        return NotFound("찾을 수 없습니다(HTTP 404)")
    if status >= 500:
        return Outage("서버 장애(HTTP %d)" % status)
    return BadRequest(("요청 오류(HTTP %d) %s" % (status, detail)).strip())


def _osascript_dialog(message, title, hidden):
    esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')
    script = ('display dialog "%s" default answer "" %swith title "%s" '
              'buttons {"취소", "확인"} default button "확인" cancel button "취소"\n'
              "text returned of result") % (esc(message), "with hidden answer " if hidden else "", esc(title))
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=600, check=False)
    if r.returncode != 0:
        if "-128" in (r.stderr or ""):  # 사람이 「취소」를 누름
            raise BadRequest("입력을 취소했습니다")
        raise BadRequest(DIALOG_FAIL % ((r.stderr or "").strip()[:120] or "osascript 종료 %d" % r.returncode))
    return r.stdout.rstrip("\n")


def _windows_dialog(message, title, hidden):
    msg, ttl = message.replace("'", "''"), title.replace("'", "''")
    if hidden:
        ps = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
              "$c=Get-Credential -UserName '%s' -Message '%s';"
              "if(-not $c){exit 3};[Console]::Out.Write($c.GetNetworkCredential().Password)") % (ttl, msg)
    else:
        ps = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8;Add-Type -AssemblyName Microsoft.VisualBasic;"
              "$v=[Microsoft.VisualBasic.Interaction]::InputBox('%s','%s');"
              "if(-not $v){exit 3};[Console]::Out.Write($v)") % (msg, ttl)
    r = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps], capture_output=True, timeout=600, check=False)
    if r.returncode == 3:  # 우리 스크립트의 취소 코드
        raise BadRequest("입력을 취소했습니다")
    if r.returncode != 0:
        raise BadRequest(DIALOG_FAIL % ((r.stderr or b"").decode("utf-8", "replace").strip()[:120] or "PowerShell 종료 %d" % r.returncode))
    return r.stdout.decode("utf-8", "replace")


def _ask(message, title, hidden):
    """사람에게 값을 받는다 — 터미널이면 프롬프트, 아니면 OS 입력 창(macOS·Windows). 채팅·명령행 인자는 쓰지 않는다."""
    if sys.stdin is not None and sys.stdin.isatty():
        return getpass.getpass(message + ": ") if hidden else input(message + ": ")
    if sys.platform == "darwin":
        return _osascript_dialog(message, title, hidden)
    if os.name == "nt":
        return _windows_dialog(message, title, hidden)
    raise BadRequest("입력 창을 띄울 수 없습니다 — 자기 터미널에서 같은 명령을 직접 실행하십시오")


def ask(message, title, hidden):
    return _ask(message, title, hidden)


# ── 토큰 보관 ──────────────────────────────────────────────────────────────

def _home():
    return os.environ.get("CASE_SEARCH_HOME") or os.path.join(os.path.expanduser("~"), ".case-search")


def _key_path():
    return os.path.join(_home(), "foreign.json")


def _load_keys():
    try:
        with open(_key_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_keys(data):
    os.makedirs(_home(), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=_home(), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.chmod(tmp, 0o600)
        os.replace(tmp, _key_path())
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _which(site):
    if site not in ENV:
        raise BadRequest("us 또는 de 중 하나입니다")
    return site


def token(site):
    v = os.environ.get(ENV[_which(site)])
    if v and v.strip():
        return v.strip()
    return _load_keys().get(site) or None


def key_status():
    out = {}
    for site in ENV:
        if os.environ.get(ENV[site], "").strip():
            out[site] = {"configured": True, "source": "env"}
        else:
            out[site] = {"configured": bool(_load_keys().get(site)), "source": "config" if _load_keys().get(site) else None}
    return out


def key_set(site, value):
    value = (value or "").strip()
    if not value:
        raise BadRequest("빈 토큰은 저장하지 않습니다")
    data = _load_keys()
    data[_which(site)] = value
    _save_keys(data)


def key_clear(site):
    data = _load_keys()
    data.pop(_which(site), None)
    _save_keys(data)


# ── HTTP ──────────────────────────────────────────────────────────────────

def _fetch(url, token=None):
    """GET → JSON. url 은 이 파일의 고정 호스트로만 만든다."""
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = "Token " + token
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        detail = e.read()[:200].decode("utf-8", "replace")
        raise http_error(e.code, detail)
    except (urllib.error.URLError, socket.timeout, ConnectionError) as e:
        if os.environ.get("CODEX_SANDBOX_NETWORK_DISABLED") == "1":
            raise NetworkBlocked("Codex 샌드박스가 네트워크를 막았습니다(서버 장애가 아닙니다) — 네트워크 허용(권한 상승)으로 다시 실행하십시오")
        raise Outage("연결 실패: %s" % e.__class__.__name__)
    try:
        return json.loads(body.decode("utf-8"))
    except ValueError:
        raise Outage("응답을 해석하지 못했습니다")


def _url(base, path, params):
    q = urllib.parse.urlencode([(k, v) for k, v in params if v not in (None, "")])
    return "%s/%s%s" % (base, path, ("?" + q) if q else "")


# ── 본문 정리 ─────────────────────────────────────────────────────────────

class _Text(HTMLParser):
    BLOCK = {"p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "blockquote", "pre"}

    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in self.BLOCK:
            self.parts.append("\n\n")

    def handle_endtag(self, tag):
        if tag in self.BLOCK:
            self.parts.append("\n\n")

    def handle_data(self, data):
        self.parts.append(data)


def html_to_text(s):
    if not s:
        return ""
    p = _Text()
    p.feed(s)
    p.close()
    text = "".join(p.parts)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _strip_marks(s):
    return html.unescape(re.sub(r"</?(mark|em)>", "", s or "")).strip()


def _window(text, offset):
    offset = max(0, int(offset or 0))
    part = text[offset:offset + WINDOW]
    end = offset + len(part)
    return {"body": part, "offset": offset, "total_chars": len(text), "has_more": end < len(text),
            "next_offset": end if end < len(text) else None}


def _param(url, name):
    if not url:
        return None
    v = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get(name)
    return v[0] if v else None


# ── 미국(CourtListener) ───────────────────────────────────────────────────

def us_search(query, court=None, after=None, before=None, cursor=None):
    data = _fetch(_url(US_API, "search/", [("type", "o"), ("q", query), ("court", court), ("filed_after", after),
                                           ("filed_before", before), ("cursor", cursor)]), token("us"))
    items = []
    for r in data.get("results") or []:
        ops = r.get("opinions") or []
        items.append({"case_name": r.get("caseName"), "court": r.get("court"), "court_id": r.get("court_id"),
                      "date": r.get("dateFiled"), "docket_number": r.get("docketNumber"), "citations": r.get("citation") or [],
                      "cluster_id": r.get("cluster_id"), "opinion_ids": [o.get("id") for o in ops if o.get("id")],
                      "snippet": _strip_marks(next((o.get("snippet") for o in ops if o.get("snippet")), "")),
                      "url": US_SITE + r["absolute_url"] if r.get("absolute_url") else None})
    return {"source": "CourtListener", "query": query, "total": data.get("count"), "items": items,
            "next_cursor": _param(data.get("next"), "cursor")}


def us_opinion(opinion_id, offset=0):
    tok = token("us")
    if not tok:
        raise NoKey(KEY_GUIDE)
    oid = str(int(str(opinion_id).strip()))  # 숫자만 — 경로를 벗어나지 않게
    d = _fetch("%s/opinions/%s/" % (US_API, oid), tok)
    for field in ("plain_text", "html_with_citations", "html", "html_lawbox", "html_columbia", "xml_harvard"):
        raw = d.get(field) or ""
        if raw.strip():
            text = raw.strip() if field == "plain_text" else html_to_text(raw)
            break
    else:
        field, text = None, ""
    out = {"source": "CourtListener", "opinion_id": d.get("id"), "type": d.get("type"), "author": d.get("author_str") or None,
           "cluster_id": d.get("cluster_id"), "language": "영어", "body_field": field,
           "url": US_SITE + d["absolute_url"] if d.get("absolute_url") else None}
    out.update(_window(text, offset))
    return out


# ── 독일(OpenLegalData) ───────────────────────────────────────────────────

def de_search(query, court=None, level=None, page=1):
    # /cases/?search= 는 검색어를 무시하고 전체를 돌려준다(2026-10-15 실측) — 본문 검색 경로 /cases/search/?text= 를 쓴다
    data = _fetch(_url(DE_API, "cases/search/", [("text", query), ("court", court), ("court_level_of_appeal", level),
                                                ("page", page if page and int(page) > 1 else None)]), token("de"))
    items = []
    for r in data.get("results") or []:
        snips = r.get("snippets") or []
        items.append({"id": r.get("id"), "court": r.get("court"), "level": r.get("court_level_of_appeal"), "date": r.get("date"),
                      "decision_type": r.get("decision_type"),
                      "snippet": _strip_marks(snips[0].get("text") if snips and isinstance(snips[0], dict) else ""),
                      "url": "%s/case/%s/" % (DE_SITE, r["slug"]) if r.get("slug") else None})
    nxt = _param(data.get("next"), "page")
    return {"source": "OpenLegalData", "query": query, "total": data.get("count"), "items": items,
            "next_page": int(nxt) if nxt else None}


def de_case(case_id, offset=0):
    cid = str(int(str(case_id).strip()))
    d = _fetch("%s/cases/%s/" % (DE_API, cid), token("de"))
    court = d.get("court")
    out = {"source": "OpenLegalData", "id": d.get("id"), "court": court.get("name") if isinstance(court, dict) else court,
           "file_number": d.get("file_number"), "date": d.get("date"), "ecli": d.get("ecli"), "type": d.get("type"),
           "language": "독일어", "url": "%s/case/%s/" % (DE_SITE, d["slug"]) if d.get("slug") else None,
           "source_url": d.get("source_url")}
    out.update(_window(html_to_text(d.get("content") or ""), offset))
    return out


# ── CLI ───────────────────────────────────────────────────────────────────

def _emit(obj, code=0):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, indent=1) + "\n")
    sys.stdout.flush()
    return code


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):  # 한국어 Windows 콘솔(cp949)에서도 UTF-8
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="foreigncase", description="해외 판례 조회(미국 CourtListener·독일 OpenLegalData)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("us-search"); s.add_argument("query"); s.add_argument("--court"); s.add_argument("--after")
    s.add_argument("--before"); s.add_argument("--cursor")
    s = sub.add_parser("us-opinion"); s.add_argument("opinion_id"); s.add_argument("--offset", type=int, default=0)
    s = sub.add_parser("de-search"); s.add_argument("query"); s.add_argument("--court"); s.add_argument("--level")
    s.add_argument("--page", type=int, default=1)
    s = sub.add_parser("de-case"); s.add_argument("case_id"); s.add_argument("--offset", type=int, default=0)
    k = sub.add_parser("key"); ks = k.add_subparsers(dest="kcmd", required=True)
    ks.add_parser("status")
    s = ks.add_parser("set"); s.add_argument("site", choices=sorted(ENV)); s.add_argument("--prompt", action="store_true")
    s.add_argument("--stdin", action="store_true")
    s = ks.add_parser("clear"); s.add_argument("site", choices=sorted(ENV))
    a = ap.parse_args(argv)
    try:
        if a.cmd == "us-search":
            out = us_search(a.query, a.court, a.after, a.before, a.cursor)
        elif a.cmd == "us-opinion":
            out = us_opinion(a.opinion_id, a.offset)
        elif a.cmd == "de-search":
            out = de_search(a.query, a.court, a.level, a.page)
        elif a.cmd == "de-case":
            out = de_case(a.case_id, a.offset)
        elif a.kcmd == "status":
            out = {"keys": key_status(), "guide": KEY_GUIDE}
        elif a.kcmd == "set":
            if a.prompt:
                name = "CourtListener" if a.site == "us" else "OpenLegalData"
                value = ask("%s API 토큰을 입력하십시오(가입 후 프로필에서 확인)" % name, name, True)
            elif a.stdin:
                value = sys.stdin.readline()
            else:
                raise BadRequest("토큰은 --prompt(입력 창) 또는 --stdin 으로만 받습니다 — 명령행에 남기지 않습니다")
            key_set(a.site, value)
            out = {"saved": a.site, "keys": key_status()}
        else:
            key_clear(a.site)
            out = {"cleared": a.site, "keys": key_status()}
    except (ValueError, ForeignError) as e:
        err = e if isinstance(e, ForeignError) else BadRequest("숫자 id 가 필요합니다")
        res = {"ok": False, "error": err.code, "detail": str(err)}
        if err.code in ("no_key", "key_invalid"):
            res["guide"] = KEY_GUIDE
        return _emit(res, 4 if err.code in ("no_key", "key_invalid") else 3)
    out = dict(out)
    out["ok"] = True
    return _emit(out)


if __name__ == "__main__":
    sys.exit(main())
