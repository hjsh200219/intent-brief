import json
import os
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import _paths as P
import lawapi as L
from conftest import RECORDED


def rec(name):
    return open(os.path.join(RECORDED, name), encoding="utf-8").read()


# ── 키 ────────────────────────────────────────────────────────
@pytest.fixture
def nokey(home, monkeypatch):
    for k in ("INTENT_BRIEF_LAW_OC", "LAW_API_OC"):
        monkeypatch.delenv(k, raising=False)
    return home


def test_key_order_and_storage(nokey, monkeypatch):
    assert L.find_key() == (None, None)
    with pytest.raises(L.NoKey):
        L.Client()
    path = L.save_key("  abc123 ")
    assert path.startswith(P.work_root()) and L.find_key() == ("abc123", "config")
    if os.name != "nt":  # Windows 는 chmod 권한 비트가 없다
        assert oct(os.stat(path).st_mode & 0o777) == "0o600"
    monkeypatch.setenv("LAW_API_OC", "envkey")
    assert L.find_key() == ("envkey", "env:LAW_API_OC")
    monkeypatch.setenv("INTENT_BRIEF_LAW_OC", "first")
    assert L.find_key() == ("first", "env:INTENT_BRIEF_LAW_OC")
    monkeypatch.delenv("INTENT_BRIEF_LAW_OC")
    monkeypatch.delenv("LAW_API_OC")
    assert L.clear_key() and L.find_key() == (None, None)
    for bad in ("", "a b"):
        with pytest.raises(P.BriefError):
            L.save_key(bad)


def test_key_status_never_prints_value(nokey, capsys):
    L.save_key("secretvalue")
    assert L.main(["key", "status"]) == 0
    out = capsys.readouterr().out
    assert "secretvalue" not in out and json.loads(out)["configured"] is True


def test_key_set_stdin(nokey, monkeypatch, capsys):
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO("fromstdin\n"))
    assert L.main(["key", "set", "--stdin", "--no-check"]) == 0
    assert "fromstdin" not in capsys.readouterr().out and L.find_key()[0] == "fromstdin"


def test_mask():
    assert L._mask("http://x/DRF/lawSearch.do?OC=abc&target=law") == "http://x/DRF/lawSearch.do?OC=***&target=law"


# ── 가짜 DRF 서버 ─────────────────────────────────────────────
ROUTES = {
    ("lawSearch.do", "law", "query", "민사소송법"): "drf_law_search_민사소송법.json",
    ("lawSearch.do", "law", "query", "소송촉진법"): "drf_law_search_소송촉진법.json",
    ("lawService.do", "law", "JO", "028800"): "drf_article_001700_028800.json",
    ("lawService.do", "law", "JO", "045100"): "drf_article_001700_045100.json",
    ("lawService.do", "law", "ID", "003984"): "drf_law_003984.json",  # 뒤 항목이 이긴다 — JO 요청은 아래 항목
    ("lawService.do", "law", "JO", "000100"): "drf_article_003984_000100.json",
    ("lawSearch.do", "prec", "nb", "2016다225353"): "drf_prec_nb_2016다225353.json",
    ("lawSearch.do", "prec", "nb", "2018다248626"): "drf_prec_nb_2018다248626.json",
    ("lawSearch.do", "prec", "nb", "2014다26187"): "drf_prec_nb_empty.json",
    ("lawService.do", "prec", "ID", "184487"): "drf_prec_184487.json",
}


class Handler(BaseHTTPRequestHandler):
    seen = []
    mode = "ok"

    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        Handler.seen.append(q)
        name = u.path.rsplit("/", 1)[-1]
        if Handler.mode == "badkey" or q.get("OC") == "bad":
            body = rec("drf_bad_key.json")
        elif Handler.mode == "500":
            self.send_response(500)
            self.end_headers()
            return
        elif Handler.mode == "html":
            body = "<html>점검 중</html>"
        else:
            body = None
            for (path, target, k, v), f in ROUTES.items():
                if name == path and q.get("target") == target and q.get(k) == v:
                    body = rec(f)
            if body is None:
                body = json.dumps({"PrecSearch": {"totalCnt": "0"}} if q.get("target") == "prec" else {"LawSearch": {"totalCnt": "0"}})
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def drf(monkeypatch):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    Handler.seen, Handler.mode = [], "ok"
    monkeypatch.setenv("INTENT_BRIEF_LAW_URL", "http://127.0.0.1:%d/DRF" % srv.server_port)
    yield Handler
    srv.shutdown()


def client():
    return L.Client(oc="k", interval=0, timeout=2, backoff=0)


def test_search_law_and_article(drf):
    c = client()
    law = L.search_law(c, "민사소송법")
    assert law["law_id"] == "001700" and law["name"] == "민사소송법"
    assert L.search_law(c, "소송촉진법")["name"] == "소송촉진 등에 관한 특례법"  # 약칭으로도 찾는다
    art = L.get_article(c, "001700", 288)
    assert art["head"] == "제288조" and "불요증사실" in art["text"]  # 편·장 제목 줄이 아니라 조문 항목
    q = drf.seen[-1]
    assert q["JO"] == "028800" and q["type"] == "JSON" and q["OC"] == "k"


def test_article_keeps_items_under_paragraphs(drf):
    """항 아래 호(1. 2. …)·목까지 본문에 담는다 — 제451조 재심사유 11개 호가 빠지면 조문을 잘못 읽는다(2026-10-15 발견)."""
    art = L.get_article(client(), "001700", 451)
    first = art["paragraphs"][0]
    assert "다음 각호" in first and "1. 법률에 따라 판결법원을 구성하지 아니한 때" in first
    assert "11. " in first and len(art["paragraphs"]) == 3
    assert "1. 법률에 따라 판결법원을" in art["full_text"] and art["full_text"].startswith("제451조(재심사유)")


def test_single_provision_law_without_article_number(drf):
    """조 번호 없이 한 문장뿐인 대통령령(소송촉진법 법정이율 규정, 조문번호 0·조문여부 전문)도 제1조로 읽는다."""
    art = L.get_article(client(), "003984", 1)
    assert art and "연 100분의 12" in art["full_text"] and art["head"] == "본문" and art["single_provision"] is True
    assert L.get_article(client(), "003984", 2) is None


def test_prec_exact_and_detail(drf):
    c = client()
    hits = L.find_prec_exact(c, "2016다225353")
    assert [(h["prec_id"], h["date"], h["court"]) for h in hits] == [("184487", "20170221", "대법원")]
    assert L.find_prec_exact(c, "2014다26187") == []
    d = L.get_prec(c, "184487")
    assert d["number"] == "2016다225353" and "주위적 청구에 흡수" in d["summary"] and "<br" not in d["summary"]


def test_errors(drf):
    drf.mode = "badkey"
    with pytest.raises(L.KeyInvalid):
        L.search_law(client(), "민법")
    drf.mode = "html"
    with pytest.raises(L.FormatChanged):
        L.search_law(client(), "민법")
    drf.mode = "500"
    with pytest.raises(L.Unavailable):
        L.search_law(client(), "민법")


def test_unreachable(monkeypatch):
    monkeypatch.setenv("INTENT_BRIEF_LAW_URL", "http://127.0.0.1:9/DRF")
    with pytest.raises(L.Unavailable) as e:
        L.search_law(L.Client(oc="secret", interval=0, timeout=1, backoff=0), "민법")
    assert "secret" not in str(e.value)


def test_generic_search_detail(drf):
    c = client()
    L.search(c, "expc", "임대차", display=3)
    assert drf.seen[-1]["target"] == "expc" and drf.seen[-1]["query"] == "임대차"
    L.detail(c, "detc", "123")
    assert drf.seen[-1]["target"] == "detc" and drf.seen[-1]["ID"] == "123"
    with pytest.raises(P.BriefError):
        L.search(c, "evil&x=1", "q")


def test_cli_no_key(nokey, capsys):
    assert L.main(["law", "민법"]) == 4
    out = json.loads(capsys.readouterr().out)
    assert out["error"] == "no_key" and "open.law.go.kr" in out["guide"]


def test_read_errors_become_unavailable(monkeypatch):
    """응답 읽기·디코딩 중 오류도 장애로 — 대조가 중간에 죽지 않게."""
    import http.client
    import urllib.request

    class Resp:
        def __init__(self, exc):
            self.exc = exc

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            raise self.exc
    for exc in (http.client.IncompleteRead(b"x"), UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad")):
        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: Resp(exc))
        with pytest.raises(L.Unavailable):
            L.Client(oc="k", interval=0, backoff=0).get("lawSearch.do", target="law", query="민법")


def test_key_set_prompt_uses_input_window(nokey, monkeypatch, capsys):
    """키는 사용자가 입력 창(터미널이면 프롬프트)에 직접 넣는다 — 채팅·명령행 인자로 받지 않는다."""
    asked = []
    monkeypatch.setattr(L, "ask", lambda message, title: asked.append((message, title)) or "  fromwindow ")
    assert L.main(["key", "set", "--prompt", "--no-check"]) == 0
    out = capsys.readouterr().out
    assert "fromwindow" not in out and L.find_key()[0] == "fromwindow"
    assert asked and "open.law.go.kr" in asked[0][0] and asked[0][1] == "법제처 Open API"


def test_key_set_prompt_cancel_saves_nothing(nokey, monkeypatch, capsys):
    def cancel(message, title):
        raise P.BriefError("입력을 취소했습니다")
    monkeypatch.setattr(L, "ask", cancel)
    assert L.main(["key", "set", "--prompt", "--no-check"]) != 0
    assert L.find_key() == (None, None)


def test_key_set_rejects_value_on_command_line(nokey):
    """명령행 인자로 키를 받으면 셸 기록·대화 기록에 남는다 — 인자 자리를 두지 않는다."""
    with pytest.raises(SystemExit):
        L.main(["key", "set", "abc123", "--no-check"])
    assert L.find_key() == (None, None)


def test_ask_uses_osascript_when_no_terminal(monkeypatch):
    import subprocess
    import types
    monkeypatch.setattr("sys.stdin.isatty", lambda: False, raising=False)
    monkeypatch.setattr(L.sys, "platform", "darwin")
    seen = {}

    def run(cmd, **kw):
        seen["cmd"] = cmd
        return types.SimpleNamespace(returncode=0, stdout="oc-from-dialog\n")
    monkeypatch.setattr(subprocess, "run", run)
    assert L.ask("키를 넣으십시오", "법제처 Open API") == "oc-from-dialog"
    assert seen["cmd"][0] == "osascript" and "법제처 Open API" in seen["cmd"][2]


def test_search_law_pages_until_exact_name():
    """짧은 법령명(「상법」)은 결과가 많아 첫 20건 밖에 있다(2026-10-15 실측: 56건 중 34번째) — 다음 쪽까지 본다."""
    names = ["법%d" % i for i in range(33)] + ["상법"] + ["상법 시행령%d" % i for i in range(22)]

    class Fake:
        def __init__(self):
            self.calls = []

        def get(self, path, **kw):
            self.calls.append(kw)
            d, p = kw["display"], kw.get("page", 1)
            chunk = names[(p - 1) * d:p * d]
            return {"LawSearch": {"totalCnt": str(len(names)), "law": [
                {"법령명한글": n, "법령ID": "00%d" % i, "법령일련번호": "m", "시행일자": "20260101"} for i, n in enumerate(chunk)]}}
    f = Fake()
    hit = L.search_law(f, "상법")
    assert hit and hit["name"] == "상법"
    assert all(c["display"] >= 20 for c in f.calls)
    assert L.search_law(f, "없는법") is None and len(f.calls) <= 6


# ── 별표·서식 ─────────────────────────────────────────────────
LICBYL = {"licBylSearch": {"totalCnt": "1", "licbyl": {
    "관련법령명": "농어업고용인력 지원 특별법 시행규칙", "소관부처명": "농림축산식품부", "별표종류": "서식", "별표번호": "000300",
    "별표명": "표준 계절근로계약서(농업, 어업 분야)", "별표일련번호": "17979509", "공포일자": "20260213",
    "별표서식파일링크": "/LSW/flDownload.do?flSeq=161650125", "별표서식PDF파일링크": "/LSW/flDownload.do?flSeq=161650127",
    "별표법령상세링크": "/DRF/lawService.do?OC=secret&target=licbyl&ID=17979509"}}}
ADMBYL = {"admRulBylSearch": {"totalCnt": "1", "admrulbyl": [{
    "관련행정규칙명": "기간제 및 공무직 근로자 관리규정", "소관부처명": "대법원", "행정규칙종류": "행정예규", "별표종류": "서식",
    "별표번호": "000300", "별표명": "[ 별지 제3호 서식 ] 공무직 및 기간제 근로자 표준 근로계약서", "별표일련번호": "3282097",
    "발령일자": "20260728", "별표서식파일링크": "/LSW/flDownload.do?flSeq=167837705"}]}}


class FakeByl:
    def __init__(self, body):
        self.body, self.calls = body, []

    def get(self, path, **kw):
        self.calls.append((path, kw))
        return self.body


def test_form_search_law_forms_normalized():
    f = FakeByl(LICBYL)
    out = L.search_forms(f, "근로계약서", kind="서식")
    assert f.calls[0] == ("lawSearch.do", {"target": "licbyl", "query": "근로계약서", "display": 20, "page": 1, "knd": 2})
    it = out["items"][0]
    assert it == {"id": "17979509", "name": "표준 계절근로계약서(농업, 어업 분야)", "kind": "서식", "number": "별지 제3호",
                  "source": "농어업고용인력 지원 특별법 시행규칙", "ministry": "농림축산식품부", "date": "20260213",
                  "hwp": "161650125", "pdf": "161650127"}
    assert out["total"] == 1 and "secret" not in json.dumps(out, ensure_ascii=False)


def test_form_search_admin_and_by_law_name():
    f = FakeByl(ADMBYL)
    out = L.search_forms(f, "기간제 및 공무직 근로자 관리규정", admin=True, by_law=True, kind="별표")
    path, kw = f.calls[0]
    assert kw["target"] == "admbyl" and kw["search"] == 2 and kw["knd"] == 1
    it = out["items"][0]
    assert it["source"] == "기간제 및 공무직 근로자 관리규정" and it["hwp"] == "167837705" and it["pdf"] is None and it["number"] == "별지 제3호"


def test_form_number_formats():
    assert L._form_number("000300", "서식") == "별지 제3호"
    assert L._form_number("000102", "별표") == "별표 1의2"
    assert L._form_number("", "서식") is None


def test_form_get_saves_without_overwrite(tmp_path, monkeypatch):
    seen = []

    def fake(seq):
        seen.append(seq)
        return "[별지 제3호서식] 표준 계약서.hwp", "application/hwp", b"HWP"
    monkeypatch.setattr(L, "_download_form", fake)
    a = L.get_form("161650125", str(tmp_path))
    b = L.get_form("161650125", str(tmp_path))
    assert os.path.basename(a["path"]) == "[별지 제3호서식] 표준 계약서.hwp" and a["bytes"] == 3
    assert b["path"] != a["path"] and b["path"].endswith("_2.hwp")
    with pytest.raises(P.BriefError):
        L.get_form("../etc", str(tmp_path))
    assert seen == ["161650125", "161650125"]


def test_form_filename_sanitized(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "_download_form", lambda seq: ("../../evil:name?.pdf", "application/pdf", b"%PDF"))
    out = L.get_form("1", str(tmp_path))
    assert os.path.dirname(out["path"]) == str(tmp_path) and "/" not in os.path.basename(out["path"]).replace(os.sep, "")
    assert out["path"].endswith(".pdf") and ":" not in os.path.basename(out["path"])


def test_form_download_host_is_fixed():
    src = open(L.__file__, encoding="utf-8").read()
    assert 'FORM_URL = "https://www.law.go.kr/LSW/flDownload.do?flSeq="' in src
