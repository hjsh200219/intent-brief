import json
import os
import stat
import sys

import pytest

import casesearch as CS

FAKE_BIGCASE = r'''
import json, sys
args = sys.argv[1:]
mode = open(__file__ + ".mode").read().strip() if __import__("os").path.exists(__file__ + ".mode") else "ok"
log = open(__file__ + ".log", "a"); log.write(json.dumps(args, ensure_ascii=False) + "\n"); log.close()
if args[0] == "status":
    print(json.dumps({"email": "" if mode == "nologin" else "a@b.c", "password_saved": mode != "nologin",
                      "access_token_valid_for_sec": 0}))
elif args[0] == "case":
    if mode == "fail" or args[2] == "2099다99999":
        sys.stderr.write("✗ GET /esapi/cases/match_view HTTP 404 ESAPI 응답 데이터가 유효하지 않습니다.\n" if mode != "fail" else "✗ 연결 실패\n")
        sys.exit(1)
    print(json.dumps({"case_id": 1594404, "case_number": args[2], "court": args[1], "judgment_date": "2014-07-10",
                      "case_expression": "대법원 2014. 7. 10. 선고 %s 판결 대여금" % args[2], "outcome": "상고기각",
                      "restricted": False, "fulltext": {"reasoning": "상고이유를 판단한다."}}, ensure_ascii=False))
elif args[0] == "search":
    print(json.dumps({"query": args[1], "page": 1, "total": 2, "results": [
        {"case_number": "2014다1", "court": "대법원", "case_expression": "대법원 2014. 1. 1. 선고 2014다1 판결"},
        {"case_number": args[1], "court": "대법원", "case_expression": "대법원 2014. 7. 10. 선고 %s 판결 대여금" % args[1]}]},
        ensure_ascii=False))
'''

FAKE_UV = "#!%s\nimport subprocess, sys\na = sys.argv[1:]\nassert a[0] == 'run'\na = [x for x in a[1:] if x != '-q']\n" \
          "sys.exit(subprocess.call([%r] + a))\n" % (sys.executable, sys.executable)


@pytest.fixture
def plugin(tmp_path, monkeypatch):
    """가짜 Claude 설정 폴더에 case-search 설치 기록 + 가짜 uv."""
    cfg = tmp_path / "claude"
    inst = tmp_path / "cache" / "case-search" / "0.3.1"
    (inst / "scripts").mkdir(parents=True)
    script = inst / "scripts" / "bigcase.py"
    script.write_text(FAKE_BIGCASE, encoding="utf-8")
    (cfg / "plugins").mkdir(parents=True)
    (cfg / "plugins" / "installed_plugins.json").write_text(json.dumps(
        {"version": 2, "plugins": {"case-search@case-search": [{"scope": "user", "installPath": str(inst), "version": "0.3.1"}]}}),
        encoding="utf-8")
    uv = tmp_path / "uv"
    uv.write_text(FAKE_UV, encoding="utf-8")
    uv.chmod(uv.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(cfg))
    monkeypatch.setenv("INTENT_BRIEF_UV", str(uv))
    monkeypatch.delenv("INTENT_BRIEF_NO_CASESEARCH", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    class Ctl:
        def mode(self, m):
            (inst / "scripts" / "bigcase.py.mode").write_text(m)

        def calls(self):
            p = inst / "scripts" / "bigcase.py.log"
            return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []
    return Ctl()


def test_not_installed(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "none"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("INTENT_BRIEF_NO_CASESEARCH", raising=False)
    st = CS.detect()
    assert st["available"] is False and "설치" in st["reason"]
    assert CS.client() is None


def test_detect_and_status(plugin):
    st = CS.detect()
    assert st["available"] is True and st["logged_in"] is True
    assert plugin.calls() == [["status"]]  # 상태 확인은 status 하나(네트워크 없음)


def test_not_logged_in(plugin):
    plugin.mode("nologin")
    st = CS.detect()
    assert st["available"] is False and "로그인" in st["reason"] and CS.client() is None


def test_disabled_by_env(plugin, monkeypatch):
    monkeypatch.setenv("INTENT_BRIEF_NO_CASESEARCH", "1")
    assert CS.detect()["available"] is False and plugin.calls() == []


def test_no_uv(plugin, monkeypatch, tmp_path):
    monkeypatch.setenv("INTENT_BRIEF_UV", str(tmp_path / "nouv"))
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    st = CS.detect()
    assert st["available"] is False and "uv" in st["reason"]


def test_case_found_and_missing(plugin):
    c = CS.client()
    hit = c.case("대법원", "2014다26187")
    assert hit == {"number": "2014다26187", "court": "대법원", "date": "20140710",
                   "expression": "대법원 2014. 7. 10. 선고 2014다26187 판결 대여금", "outcome": "상고기각", "restricted": False}
    assert c.case("대법원", "2099다99999") is None  # 404 = 없음
    plugin.mode("fail")
    with pytest.raises(CS.SearchError):
        c.case("대법원", "2014다26187")


def test_find_exact_by_search_when_court_unknown(plugin):
    c = CS.client()
    hit = c.find_exact("2014다26187", court=None)
    assert hit["number"] == "2014다26187" and plugin.calls()[-1][0] == "search"
    c.find_exact("2014다26187", court="대법원")
    assert plugin.calls()[-1][:2] == ["case", "대법원"]


def test_non_dict_json_is_search_error(plugin, tmp_path):
    import casesearch as CS2
    c = CS.client()
    p = [x for x in (tmp_path / "cache").rglob("bigcase.py")][0]
    p.write_text("import json; print(json.dumps([1, 2]))\n", encoding="utf-8")
    with pytest.raises(CS2.SearchError):
        c.case("대법원", "2014다26187")


def test_error_masks_email(plugin, tmp_path):
    p = [x for x in (tmp_path / "cache").rglob("bigcase.py")][0]
    p.write_text("import sys; sys.stderr.write('✗ lawyer@firm.kr 로그인 실패\\n'); sys.exit(1)\n", encoding="utf-8")
    c = CS.Client(str(p), CS.find_uv())
    with pytest.raises(CS.SearchError) as e:
        c.case("대법원", "2014다26187")
    assert "lawyer@firm.kr" not in str(e.value)
