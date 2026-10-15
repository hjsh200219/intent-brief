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
