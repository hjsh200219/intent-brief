import json
import os

import pytest

import _paths as P
import cite_check as C
import lawapi as L
from conftest import RECORDED


def rec(name):
    return json.loads(open(os.path.join(RECORDED, name), encoding="utf-8").read())


class FakeLaw:
    """lawapi.Client 흉내 — (path, target, 키=값) 로 녹화 응답을 찾는다."""

    def __init__(self, table):
        self.table = table
        self.calls = []

    def get(self, path, **params):
        self.calls.append(dict(params, _path=path))
        for match, resp in self.table:
            if all(params.get(k) == v for k, v in match.items() if k != "_path") and match.get("_path", path) == path:
                if isinstance(resp, Exception):
                    raise resp
                return resp
        raise AssertionError("녹화 응답 없음: %s %r" % (path, params))


EMPTY_PREC = {"PrecSearch": {"totalCnt": "0"}}
LAWS = [({"_path": "lawSearch.do", "target": "law", "query": "민사소송법"}, rec("drf_law_search_민사소송법.json")),
        ({"_path": "lawService.do", "target": "law", "ID": "001700", "JO": "028800"}, rec("drf_article_001700_028800.json"))]
P2016 = [({"_path": "lawSearch.do", "nb": "2016다225353"}, rec("drf_prec_nb_2016다225353.json")),
         ({"_path": "lawService.do", "target": "prec", "ID": "184487"}, rec("drf_prec_184487.json"))]
LAW288 = {"kind": "law", "law": "민사소송법", "article": 288, "sub": 0}


def chk(tmp_path, table):
    return C.Checker(str(tmp_path / "cite"), client=FakeLaw(table))


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


def test_extract_same_number_different_dates():
    """같은 사건번호를 다른 선고일로 두 번 인용하면 둘 다 대조한다(틀린 쪽이 묻히지 않게)."""
    md = "대법원 2017. 2. 21. 선고 2016다225353 판결, 대법원 2017. 2. 22. 선고 2016다225353 판결, 2016다225353 판결."
    cases = [(c["number"], c["date"]) for c in C.extract(md) if c["kind"] == "case"]
    assert cases == [("2016다225353", "20170221"), ("2016다225353", "20170222")]


def test_law_confirmed(tmp_path):
    r = chk(tmp_path, LAWS).check(LAW288)
    assert r["status"] == "confirmed" and r["law_id"] == "001700" and "불요증사실" in r["excerpt"]


def test_law_alias(tmp_path):
    table = [({"query": "소송촉진법"}, rec("drf_law_search_소송촉진법.json")),
             ({"ID": "001215", "JO": "000300"}, {"법령": {"조문": {"조문단위": [
                 {"조문여부": "조문", "조문내용": "제3조(법정이율) ①금전채무의 …", "조문번호": "3"}]}}})]
    r = chk(tmp_path, table).check({"kind": "law", "law": "소송촉진법", "article": 3, "sub": 0})
    assert r["status"] == "confirmed" and r["law_id"] == "001215"


def test_law_name_or_article_missing(tmp_path):
    t = [({"query": "없는법"}, {"LawSearch": {"totalCnt": "0"}})]
    assert chk(tmp_path, t).check({"kind": "law", "law": "없는법", "article": 1, "sub": 0})["status"] == "unverified"
    t = [LAWS[0], ({"JO": "999900"}, {"법령": {"조문": {"조문단위": []}}})]
    r = chk(tmp_path, t).check({"kind": "law", "law": "민사소송법", "article": 9999, "sub": 0})
    assert r["status"] == "unverified" and "조문" in r["detail"]


def test_case_confirmed_with_date(tmp_path):
    c = chk(tmp_path, P2016)
    r = c.check({"kind": "case", "number": "2016다225353", "court": "대법원", "date": "20170221"})
    assert r["status"] == "confirmed" and r["prec_id"] == "184487" and "판결요지" in r["excerpt"]
    assert c.client.inner.calls[0]["nb"] == "2016다225353"


def test_case_date_mismatch(tmp_path):
    r = chk(tmp_path, P2016).check({"kind": "case", "number": "2016다225353", "court": "대법원", "date": "20170222"})
    assert r["status"] == "unverified" and "선고일 불일치(원문 20170221)" in r["detail"]


def test_case_listed_but_no_body_still_exists(tmp_path):
    t = [P2016[0], ({"_path": "lawService.do", "ID": "184487"}, {"Law": "일치하는 판례가 없습니다"})]
    r = chk(tmp_path, t).check({"kind": "case", "number": "2016다225353", "court": None, "date": None})
    assert r["status"] == "confirmed" and r["excerpt"] == ""


def test_case_missing_reports_cited_by(tmp_path):
    t = [({"nb": "2014다26187"}, rec("drf_prec_nb_empty.json")),
         ({"query": "2014다26187", "search": 2}, {"PrecSearch": {"totalCnt": "5", "prec": []}})]
    r = chk(tmp_path, t).check({"kind": "case", "number": "2014다26187", "court": "대법원", "date": "20140710"})
    assert r["status"] == "unverified" and r["cited_by"] == 5 and "인용한 다른 판결 5건" in r["detail"]


def test_errors_map_to_status(tmp_path):
    for exc, want in ((L.Unavailable("x"), "outage"), (L.FormatChanged("x"), "format_changed"), (L.KeyInvalid("x"), "key_invalid")):
        assert chk(tmp_path, [({"query": "민법"}, exc)]).check({"kind": "law", "law": "민법", "article": 1, "sub": 0})["status"] == want


def test_cache_hit_no_call(tmp_path):
    chk(tmp_path, LAWS).check(LAW288)
    c2 = C.Checker(str(tmp_path / "cite"), client=FakeLaw([]))
    assert c2.check(LAW288)["status"] == "confirmed" and c2.client.inner.calls == [] and c2.calls == 0


def test_cache_masks_key(tmp_path):
    leak = {"LawSearch": {"law": {"법령명한글": "민사소송법", "법령ID": "001700",
                                  "법령상세링크": "/DRF/lawService.do?OC=realkey&target=law"}}}
    chk(tmp_path, [({"query": "민사소송법"}, leak), LAWS[1]]).check(LAW288)
    for n in os.listdir(tmp_path / "cite"):
        assert "realkey" not in open(os.path.join(tmp_path, "cite", n), encoding="utf-8").read()


def test_tag_draft_once(phrases):
    md = "본문 2099다99999 판결 참조."
    res = [{"text": "2099다99999 판결", "pos": 3, "status": "unverified"}]
    once = C.tag_draft(md, res, phrases)
    assert once == "본문 2099다99999 판결 [확인 필요: 법제처 미확인] 참조."
    assert C.tag_draft(once, res, phrases) == once


def test_run_without_key_stops(tmp_path, home, monkeypatch, capsys):
    for k in ("INTENT_BRIEF_LAW_OC", "LAW_API_OC"):
        monkeypatch.delenv(k, raising=False)
    draft = tmp_path / "draft.md"
    draft.write_text("민사소송법 제288조\n", encoding="utf-8")
    assert C.main(["run", str(draft)]) == 4
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["error"] == "no_key"
    assert draft.read_text(encoding="utf-8") == "민사소송법 제288조\n"  # 태그를 붙이지 않는다


def test_run_end_to_end(tmp_path):
    d = tmp_path / "w"
    d.mkdir()
    draft = d / "draft.md"
    draft.write_text("## [sec:sec.law] 법리\n민사소송법 제288조와 대법원 2017. 2. 21. 선고 2016다225353 판결, "
                     "2014다26187 판결 참조.\n", encoding="utf-8")
    table = LAWS + P2016 + [({"nb": "2014다26187"}, rec("drf_prec_nb_empty.json")),
                            ({"query": "2014다26187"}, {"PrecSearch": {"totalCnt": "0"}})]
    out = C.run(str(draft), client=FakeLaw(table))
    assert out["complete"] and out["summary"] == {"confirmed": 2, "unverified": 1}
    text = draft.read_text(encoding="utf-8")
    assert "2014다26187 판결 [확인 필요: 법제처 미확인]" in text and text.count("[확인 필요") == 1
    assert (d / "cite_results.json").exists()
