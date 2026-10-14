import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import _paths as P
import cite_check as C
from conftest import RECORDED


def rec(name):
    return open(os.path.join(RECORDED, name), encoding="utf-8").read()


class FakeClient:
    """녹화 응답을 돌려주는 클라이언트 — (tool, action, query/law_id/case_id, page) 로 찾는다."""

    def __init__(self, table):
        self.table = table
        self.calls = []

    def call(self, tool, args):
        self.calls.append(dict(args))
        for match, resp in self.table:
            if all(args.get(k) == v for k, v in match.items()):
                if isinstance(resp, Exception):
                    raise resp
                return resp
        raise AssertionError("녹화 응답 없음: %r" % args)


LAWS = [({"action": "search_laws", "query": "민사소송법"}, rec("search_laws_민사소송법.txt")),
        ({"action": "get_law_article_sub", "law_id": 290113, "article": "028800"}, rec("article_288.txt"))]


def chk(tmp_path, table):
    return C.Checker(str(tmp_path / "cite"), client=FakeClient(table))


def test_extract():
    md = ("## [sec:sec.header] 준비서면\n사건 2026가단512345 대여금\n"
          "## [sec:sec.law] 법리\n민사소송법 제288조, 제266조의2 및 같은 법 제150조. 증거방법 제1조. "
          "대법원 2017. 2. 21. 선고 2016다225353 판결, 대법원 2020. 1. 2. 선고 2018다1234, 1241 판결, 2018다248626 전원합의체 판결.")
    cs = C.extract(md)
    laws = [(c["law"], c["article"], c["sub"]) for c in cs if c["kind"] == "law"]
    assert laws == [("민사소송법", 288, 0), ("민사소송법", 266, 2), ("민사소송법", 150, 0)]
    cases = [(c["number"], c["court"], c["date"]) for c in cs if c["kind"] == "case"]
    assert cases == [("2016다225353", "대법원", "20170221"), ("2018다1234", "대법원", "20200102"),
                     ("2018다1241", "대법원", "20200102"), ("2018다248626", None, None)]
    assert all("2026가단512345" not in c["text"] for c in cs)  # 사건 표시의 우리 사건번호는 제외


def test_law_confirmed(tmp_path):
    r = chk(tmp_path, LAWS).check({"kind": "law", "law": "민사소송법", "article": 288, "sub": 0})
    assert r["status"] == "confirmed" and r["law_id"] == 290113 and "불요증사실" in r["excerpt"]


def test_case_exact_match_4th(tmp_path):
    """(a) 사건번호 줄이 정확히 같은 4번째 항목만 확인됨, case_id 234931."""
    table = [({"action": "search_cases", "query": "2018다248626", "page": 1}, rec("search_cases_2018다248626.txt")),
             ({"action": "get_case_detail", "case_id": 234931}, rec("case_detail_234931.txt"))]
    c = chk(tmp_path, table)
    r = c.check({"kind": "case", "number": "2018다248626", "court": None, "date": None})
    assert r["status"] == "confirmed" and r["case_id"] == 234931 and "판시사항" in r["excerpt"]
    assert c.client.calls[0]["search_type"] == "case_name" and isinstance(c.client.calls[1]["case_id"], int)


def test_case_cited_only_elsewhere(tmp_path):
    """(b) 다른 판결 본문에만 그 번호가 있는 경우 — 미확인."""
    text = rec("search_cases_2018다248626.txt")
    cut = text.index("4. [")
    trimmed = text[:cut].replace("총 4건", "총 3건")
    table = [({"action": "search_cases", "query": "2018다248626", "search_type": "case_name"}, trimmed),
             ({"action": "search_cases", "query": "2018다248626", "search_type": "full_text"}, trimmed)]
    assert chk(tmp_path, table).check({"kind": "case", "number": "2018다248626", "court": None, "date": None})["status"] == "unverified"


def test_case_zero_then_full_text(tmp_path):
    """(c) 0건 → full_text 1회 → 미확인."""
    table = [({"action": "search_cases", "query": "2099다99999"}, rec("search_cases_empty.txt"))]
    c = chk(tmp_path, table)
    r = c.check({"kind": "case", "number": "2099다99999", "court": None, "date": None})
    assert r["status"] == "unverified"
    assert [x.get("search_type") for x in c.client.calls] == ["case_name", "full_text"]


def test_date_and_supreme_filter(tmp_path):
    """(f) 선고일이 있으면 date_from=date_to, 대법원이면 court=supreme."""
    page = ("## 판례 검색 결과\n\n총 1건 (1페이지)\n\n1. [184487] 공유물분할등\n   사건번호: 2016다225353\n"
            "   법원: 대법원 | 선고일: 2017.02.21 | 선고: 선고\n")
    table = [({"action": "search_cases", "query": "2016다225353"}, page),
             ({"action": "get_case_detail", "case_id": 184487}, "### 판시사항\n\n[1] 예비적 청구\n\n### 판결요지\n\n[1] 흡수\n")]
    c = chk(tmp_path, table)
    r = c.check({"kind": "case", "number": "2016다225353", "court": "대법원", "date": "20170221"})
    assert r["status"] == "confirmed"
    a = c.client.calls[0]
    assert a["court"] == "supreme" and a["date_from"] == a["date_to"] == "20170221" and "search_type" not in a


def test_date_mismatch_unverified(tmp_path):
    page = "총 1건\n\n1. [1] x\n   사건번호: 2016다225353\n   법원: 대법원 | 선고일: 2017.02.21\n"
    table = [({"action": "search_cases"}, page), ({"action": "get_case_detail"}, "")]
    r = chk(tmp_path, table).check({"kind": "case", "number": "2016다225353", "court": "대법원", "date": "20170222"})
    assert r["status"] == "unverified" and "선고일" in r["detail"]


def _page(total, numbers):
    body = "".join("%d. [%d] 사건\n   사건번호: %s\n   법원: 대법원 | 선고일: 2000.01.01\n" % (i + 1, 1000 + i, n) for i, n in enumerate(numbers))
    return "## 판례 검색 결과\n\n총 %d건 (1페이지)\n\n%s" % (total, body)


def test_reverse_paging(tmp_path):
    """(g) 선고일 없음·총 180건 → 1쪽 다음 4쪽부터 역순."""
    table = [({"page": 1}, _page(180, ["2020다1"] * 50)), ({"page": 4}, _page(180, ["2020다2"] * 30)),
             ({"page": 3}, _page(180, ["2020다3", "2000다777"])), ({"action": "get_case_detail"}, "")]
    c = chk(tmp_path, table)
    r = c.check({"kind": "case", "number": "2000다777", "court": None, "date": None})
    assert r["status"] == "confirmed" and [x.get("page") for x in c.client.calls if x["action"] == "search_cases"] == [1, 4, 3]


def test_search_limit(tmp_path):
    """(h) 5쪽 소진 → 탐색 상한 도달(미확인과 구분)."""
    table = [({"action": "search_cases"}, _page(400, ["1999다1"]))]
    r = chk(tmp_path, table).check({"kind": "case", "number": "2000다777", "court": None, "date": None})
    assert r["status"] == "search_limit"


def test_tool_errors(tmp_path):
    arg = json.loads(rec("iserror_arg.json"))["result"]["content"][0]["text"]
    miss = json.loads(rec("iserror_missing.json"))["result"]["content"][0]["text"]
    t1 = [({"action": "search_laws"}, C.ToolError("arg_error", arg))]
    assert chk(tmp_path, t1).check({"kind": "law", "law": "민법", "article": 1, "sub": 0})["status"] == "arg_error"
    t2 = [({"action": "search_laws"}, C.McpUnavailable("timeout"))]
    assert chk(tmp_path, t2).check({"kind": "law", "law": "민법", "article": 1, "sub": 0})["status"] == "outage"
    t3 = [({"action": "search_cases"}, "알 수 없는 형식")]
    assert chk(tmp_path, t3).check({"kind": "case", "number": "2000다1", "court": None, "date": None})["status"] == "format_changed"
    assert "파라미터" in miss


def test_cache_hit_no_call(tmp_path):
    c = chk(tmp_path, LAWS)
    c.check({"kind": "law", "law": "민사소송법", "article": 288, "sub": 0})
    c2 = C.Checker(str(tmp_path / "cite"), client=FakeClient([]))
    assert c2.check({"kind": "law", "law": "민사소송법", "article": 288, "sub": 0})["status"] == "confirmed"
    assert c2.client.calls == []


def test_tag_draft_once(phrases):
    md = "본문 2099다99999 판결 참조."
    res = [{"text": "2099다99999 판결", "pos": 3, "status": "unverified"}]
    once = C.tag_draft(md, res, phrases)
    assert once == "본문 2099다99999 판결 [확인 필요: k-law 미확인] 참조."
    assert C.tag_draft(once, res, phrases) == once


def test_url_from_mcp_json(monkeypatch):
    monkeypatch.delenv("INTENT_BRIEF_MCP_URL", raising=False)
    assert C.mcp_url() == "https://public-data.up.railway.app/mcp"


# ── 실서버 규약을 흉내 낸 가짜 HTTP 서버 ───────────────────────────
class FakeMcp(BaseHTTPRequestHandler):
    sessions = set()
    mode = {}
    log = []

    def log_message(self, *a):
        pass

    def _send(self, code, obj, sse=True, sid=None):
        body = ("event: message\ndata: %s\n\n" % json.dumps(obj, ensure_ascii=False)) if sse else json.dumps(obj, ensure_ascii=False)
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/event-stream" if sse else "application/json")
        if sid:
            self.send_header("Mcp-Session-Id", sid)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeMcp.log.append(req.get("method"))
        sid = self.headers.get("Mcp-Session-Id")
        m = req.get("method")
        if m == "initialize":
            if FakeMcp.mode.get("init_fail"):
                return self._send(500, {"jsonrpc": "2.0", "id": req["id"], "error": {"code": -1, "message": "x"}}, sse=False)
            new = "s%d" % (len(FakeMcp.sessions) + 1)
            FakeMcp.sessions.add(new)
            return self._send(200, {"jsonrpc": "2.0", "id": req["id"], "result": {"protocolVersion": "2025-06-18"}}, sid=new)
        if m == "notifications/initialized":
            self.send_response(202)
            self.end_headers()
            return
        if sid not in FakeMcp.sessions:
            return self._send(400, {"jsonrpc": "2.0", "error": {"code": -32000, "message": "Bad Request: Server not initialized"}, "id": None}, sse=False)
        if FakeMcp.mode.get("drop_session_once"):
            FakeMcp.mode["drop_session_once"] = False
            FakeMcp.sessions.discard(sid)
            return self._send(400, {"jsonrpc": "2.0", "error": {"code": -32000, "message": "Bad Request: Server not initialized"}, "id": None}, sse=False)
        if FakeMcp.mode.get("slow"):
            time.sleep(2)
        if FakeMcp.mode.get("http500"):
            return self._send(502, {"error": "bad gateway"}, sse=False)
        args = req["params"]["arguments"]
        if FakeMcp.mode.get("arg_error"):
            text = json.loads(rec("iserror_arg.json"))["result"]["content"][0]["text"]
            return self._send(200, {"jsonrpc": "2.0", "id": req["id"], "result": {"content": [{"type": "text", "text": text}], "isError": True}})
        if FakeMcp.mode.get("korean_error"):
            text = json.loads(rec("iserror_missing.json"))["result"]["content"][0]["text"]
            return self._send(200, {"jsonrpc": "2.0", "id": req["id"], "result": {"content": [{"type": "text", "text": text}], "isError": True}})
        text = rec("search_laws_민사소송법.txt") if args.get("action") == "search_laws" else rec("article_288.txt")
        res = {"content": [{"type": "text", "text": text}], "structuredContent": {"content": [{"type": "text", "text": text}]}}
        return self._send(200, {"jsonrpc": "2.0", "id": req["id"], "result": res})


@pytest.fixture
def fake_server():
    FakeMcp.sessions = set()
    FakeMcp.mode = {}
    FakeMcp.log = []
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeMcp)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield "http://127.0.0.1:%d/mcp" % srv.server_address[1]
    srv.shutdown()


LAW288 = {"kind": "law", "law": "민사소송법", "article": 288, "sub": 0}


def test_client_session_sse(tmp_path, fake_server):
    c = C.Checker(str(tmp_path / "c"), client=C.McpClient(fake_server))
    assert c.check(LAW288)["status"] == "confirmed"
    assert FakeMcp.log[:2] == ["initialize", "notifications/initialized"]
    assert c.client.session_id == "s1"


def test_client_reinit_once(tmp_path, fake_server):
    FakeMcp.mode["drop_session_once"] = True
    c = C.Checker(str(tmp_path / "c"), client=C.McpClient(fake_server))
    assert c.check(LAW288)["status"] == "confirmed"
    assert FakeMcp.log.count("initialize") == 2


def test_client_init_fail_outage(tmp_path, fake_server):
    FakeMcp.mode["init_fail"] = True
    c = C.Checker(str(tmp_path / "c"), client=C.McpClient(fake_server))
    assert c.check(LAW288)["status"] == "outage"


@pytest.mark.parametrize("mode,want", [("arg_error", "arg_error"), ("korean_error", "arg_error"), ("http500", "outage")])
def test_client_error_kinds(tmp_path, fake_server, mode, want):
    FakeMcp.mode[mode] = True
    c = C.Checker(str(tmp_path / "c"), client=C.McpClient(fake_server))
    assert c.check(LAW288)["status"] == want


def test_client_timeout(tmp_path, fake_server):
    FakeMcp.mode["slow"] = True
    c = C.Checker(str(tmp_path / "c"), client=C.McpClient(fake_server, timeout=0.5))
    assert c.check(LAW288)["status"] == "outage"


def test_unreachable(tmp_path):
    c = C.Checker(str(tmp_path / "c"), client=C.McpClient("http://127.0.0.1:9/mcp", timeout=1))
    assert c.check(LAW288)["status"] == "outage"


def test_run_end_to_end_with_fake(tmp_path, fake_server, monkeypatch):
    monkeypatch.setenv("INTENT_BRIEF_MCP_URL", fake_server)
    d = tmp_path / "w"
    d.mkdir()
    draft = d / "draft.md"
    draft.write_text("## [sec:sec.law] 법리\n민사소송법 제288조에 따라 자백한 사실은 증명이 필요 없습니다.\n", encoding="utf-8")
    out = C.run(str(draft))
    assert out["complete"] and out["summary"] == {"confirmed": 1}
    assert (d / "cite_results.json").exists()
    assert os.listdir(d / "cite")


def test_law_alias_parenthesis(tmp_path):
    """「소송촉진 등에 관한 특례법 (소송촉진법)」처럼 약칭 괄호가 붙어도 정확 일치(e2e 에서 오탐으로 드러남)."""
    search = ("## 법령 검색 결과\n\n총 3건 (1페이지)\n\n1. [288353] 소송촉진 등에 관한 특례규칙\n"
              "2. [286417] 소송촉진 등에 관한 특례법 (소송촉진법)\n3. [208701] 소송촉진 등에 관한 특례법 제3조제1항 본문의 법정이율에 관한 규정\n")
    art = "### 제3조 (법정이율)\n\n제3조(법정이율) ①금전채무의 전부 또는 일부의 이행을 명하는 판결…"
    table = [({"action": "search_laws"}, search), ({"action": "get_law_article_sub", "law_id": 286417, "article": "000300"}, art)]
    r = chk(tmp_path, table).check({"kind": "law", "law": "소송촉진 등에 관한 특례법", "article": 3, "sub": 0})
    assert r["status"] == "confirmed" and r["law_id"] == 286417


def test_unverified_reports_cited_by(tmp_path):
    """원문은 없고 그 번호를 인용한 다른 판결만 있을 때 — 미확인이되 인용 건수를 알려 준다."""
    page = _page(5, ["2021나10058", "2021가합10042", "2020나26340", "2019가1", "2018가2"])
    table = [({"action": "search_cases", "date_from": "20140710"}, "\"2014다26187\" 판례 검색 결과가 없습니다."),
             ({"action": "search_cases"}, page)]
    r = chk(tmp_path, table).check({"kind": "case", "number": "2014다26187", "court": "대법원", "date": "20140710"})
    assert r["status"] == "unverified" and r["cited_by"] == 5 and "인용한 다른 판결 5건" in r["detail"]


def test_date_wrong_but_number_exists(tmp_path):
    page = _page(1, ["2016다225353"])
    table = [({"action": "search_cases", "date_from": "20170222"}, "검색 결과가 없습니다."), ({"action": "search_cases"}, page)]
    r = chk(tmp_path, table).check({"kind": "case", "number": "2016다225353", "court": "대법원", "date": "20170222"})
    assert r["status"] == "unverified" and "선고일 불일치" in r["detail"]
