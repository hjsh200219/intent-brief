"""해외 판례(미국 CourtListener·독일 OpenLegalData) 조회 — 네트워크 없이 응답 정규화·키 보관·오류 분류를 본다."""
import ast
import json
import os
import stat
import sys

import pytest

from conftest import ROOT

SCRIPTS = os.path.join(ROOT, "skills", "case-search", "scripts")
sys.path.insert(0, SCRIPTS)
import foreigncase as FC  # noqa: E402

US_SEARCH = {"count": 2, "next": "https://www.courtlistener.com/api/rest/v4/search/?cursor=abc123&q=x&type=o", "results": [
    {"caseName": "Alice State Bank v. Houston Pasture Co.", "court": "Supreme Court of the United States", "court_id": "scotus",
     "dateFiled": "1918-06-03", "docketNumber": "154", "citation": ["247 U.S. 240"], "cluster_id": 99188,
     "absolute_url": "/opinion/99188/alice-state-bank-v-houston-pasture-co/",
     "opinions": [{"id": 99188, "snippet": "title by <mark>adverse</mark> possession", "type": "010combined"}]}]}
US_OPINION = {"id": 99188, "type": "010combined", "author_str": "Holmes", "cluster_id": 99188, "plain_text": "",
              "html_with_citations": "<p>The <b>question</b> is &amp; was title.</p><p>Affirmed.</p>",
              "absolute_url": "/opinion/99188/alice-state-bank-v-houston-pasture-co/"}
DE_SEARCH = {"count": 863, "next": "https://de.openlegaldata.io/api/cases/search/?page=2&text=Mietminderung", "results": [
    {"id": 457081, "court": "OLGSL", "court_level_of_appeal": "Oberlandesgericht", "date": "2021-05-05", "decision_type": "Beschluss",
     "slug": "olgsl-2021-05-05-2-w-1121", "snippets": [{"text": "anzusetzenden <em>Mietminderung</em> geklärt"}]}]}
DE_CASE = {"id": 457081, "court": {"name": "Saarländisches Oberlandesgericht", "slug": "olgsl"}, "file_number": "2 W 11/21",
           "date": "2021-05-05", "ecli": "ECLI:DE:OLGSL:2021:0505.2W11.21.00", "type": "Beschluss", "slug": "olgsl-2021-05-05-2-w-1121",
           "source_url": "https://recht.saarland.de/x", "content": "<h2>Tenor</h2><p>" + "A" * 9000 + "</p>"}


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("CASE_SEARCH_HOME", str(tmp_path))
    monkeypatch.delenv("COURTLISTENER_API_TOKEN", raising=False)
    monkeypatch.delenv("OPENLEGALDATA_API_TOKEN", raising=False)
    return tmp_path


@pytest.fixture
def calls(monkeypatch):
    log = []

    def fake(url, token=None):
        log.append((url, token))
        for key, body in ROUTES.items():
            if key in url:
                if isinstance(body, Exception):
                    raise body
                return body
        raise AssertionError("예상 못 한 요청: " + url)
    monkeypatch.setattr(FC, "_fetch", fake)
    return log


ROUTES = {}


@pytest.fixture(autouse=True)
def routes():
    ROUTES.clear()
    ROUTES.update({"courtlistener.com/api/rest/v4/search/": US_SEARCH, "courtlistener.com/api/rest/v4/opinions/": US_OPINION,
                   "openlegaldata.io/api/cases/search/": DE_SEARCH, "openlegaldata.io/api/cases/457081/": DE_CASE})


def test_us_search_normalizes_and_returns_cursor(home, calls):
    out = FC.us_search("adverse possession", court="scotus", after="1900-01-01")
    hit = out["items"][0]
    assert hit == {"case_name": "Alice State Bank v. Houston Pasture Co.", "court": "Supreme Court of the United States",
                   "court_id": "scotus", "date": "1918-06-03", "docket_number": "154", "citations": ["247 U.S. 240"],
                   "cluster_id": 99188, "opinion_ids": [99188], "snippet": "title by adverse possession",
                   "url": "https://www.courtlistener.com/opinion/99188/alice-state-bank-v-houston-pasture-co/"}
    assert out["total"] == 2 and out["next_cursor"] == "abc123" and out["source"] == "CourtListener"
    url, token = calls[0]
    assert "type=o" in url and "court=scotus" in url and "filed_after=1900-01-01" in url and token is None


def test_us_opinion_needs_key(home, calls):
    with pytest.raises(FC.NoKey):
        FC.us_opinion("99188")
    assert calls == []


def test_us_opinion_body_from_html_when_plain_text_empty(home, calls, monkeypatch):
    monkeypatch.setenv("COURTLISTENER_API_TOKEN", "tok-env")
    out = FC.us_opinion("99188")
    assert out["language"] == "영어" and out["body"] == "The question is & was title.\n\nAffirmed."
    assert out["url"].startswith("https://www.courtlistener.com/opinion/99188/")
    assert calls[0][1] == "tok-env" and out["has_more"] is False


def test_de_search_uses_fulltext_endpoint(home, calls):
    """/api/cases/?search= 는 검색어를 무시한다(2026-10-15 실측: 무의미 검색어도 425,071건) — /cases/search/?text= 를 쓴다."""
    out = FC.de_search("Mietminderung", level="Bundesgericht", page=2)
    url = calls[0][0]
    assert "/api/cases/search/?" in url and "text=Mietminderung" in url and "court_level_of_appeal=Bundesgericht" in url
    assert "page=2" in url and "search=" not in url.split("?")[1].replace("cases/search", "")
    hit = out["items"][0]
    assert hit["snippet"] == "anzusetzenden Mietminderung geklärt" and hit["url"] == "https://de.openlegaldata.io/case/olgsl-2021-05-05-2-w-1121/"
    assert out["total"] == 863 and out["next_page"] == 2 and out["source"] == "OpenLegalData"


def test_de_case_window_and_offset(home, calls):
    first = FC.de_case("457081")
    assert first["language"] == "독일어" and first["file_number"] == "2 W 11/21" and first["court"] == "Saarländisches Oberlandesgericht"
    assert len(first["body"]) == FC.WINDOW and first["has_more"] is True and first["next_offset"] == FC.WINDOW
    rest = FC.de_case("457081", offset=first["next_offset"])
    assert rest["has_more"] is False and first["body"].startswith("Tenor")
    assert first["total_chars"] == len(first["body"]) + len(rest["body"])


@pytest.mark.parametrize("status,err", [(401, FC.KeyInvalid), (403, FC.KeyInvalid), (429, FC.RateLimited), (404, FC.NotFound),
                                        (500, FC.Outage), (503, FC.Outage)])
def test_http_errors_are_classified(home, calls, status, err):
    ROUTES["openlegaldata.io/api/cases/search/"] = FC.http_error(status, "x")
    with pytest.raises(err):
        FC.de_search("x")


def test_key_set_stores_0600_and_env_wins(home, monkeypatch):
    FC.key_set("us", "tok-file")
    p = os.path.join(str(home), "foreign.json")
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o600
    assert FC.token("us") == "tok-file"
    monkeypatch.setenv("COURTLISTENER_API_TOKEN", "tok-env")
    assert FC.token("us") == "tok-env"
    st = FC.key_status()
    assert st["us"] == {"configured": True, "source": "env"} and st["de"]["configured"] is False
    assert "tok" not in json.dumps(st)
    FC.key_clear("us")
    monkeypatch.delenv("COURTLISTENER_API_TOKEN")
    assert FC.token("us") is None


def test_cli_outputs_json_and_masks_errors(home, calls, capsys):
    assert FC.main(["us-opinion", "99188"]) == 4
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["error"] == "no_key" and "courtlistener.com" in out["guide"]
    assert FC.main(["de-search", "Mietminderung"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_only_fixed_hosts_receive_tokens():
    """토큰은 고정된 두 호스트로만 — 다른 주소를 받는 인자가 없다."""
    src = open(os.path.join(SCRIPTS, "foreigncase.py"), encoding="utf-8").read()
    hosts = {h for h in __import__("re").findall(r"https://([\w.-]+)/api", src)}
    assert hosts == {"www.courtlistener.com", "de.openlegaldata.io"}


def test_stdlib_only_and_py39_syntax():
    src = open(os.path.join(SCRIPTS, "foreigncase.py"), encoding="utf-8").read()
    tree = ast.parse(src, feature_version=(3, 9))
    mods = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    mods |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    allowed = {"argparse", "getpass", "html", "json", "os", "re", "socket", "subprocess", "sys", "tempfile", "urllib"}
    assert mods <= allowed, mods - allowed


def test_key_set_prompt_hidden_window(home, monkeypatch, capsys):
    asked = []
    monkeypatch.setattr(FC, "ask", lambda message, title, hidden: asked.append((title, hidden)) or "tok-window\n")
    assert FC.main(["key", "set", "us", "--prompt"]) == 0
    assert "tok-window" not in capsys.readouterr().out and FC.token("us") == "tok-window"
    assert asked == [("CourtListener", True)]


def test_key_set_needs_prompt_or_stdin(home, capsys):
    assert FC.main(["key", "set", "us"]) == 3
    assert FC.token("us") is None
