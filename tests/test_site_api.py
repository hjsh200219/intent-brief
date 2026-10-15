"""site-api — URL 에서 API 후보를 찾고(extract), bigcase.py 와 같은 틀의 클라이언트를 만든다(scaffold)."""
import ast
import importlib.util
import os
import re
import sys

import pytest

from conftest import ROOT

SKILL = os.path.join(ROOT, "skills", "site-api")
sys.path.insert(0, os.path.join(SKILL, "scripts"))
import extract as X  # noqa: E402
import scaffold as S  # noqa: E402

BASE = "https://law.example.kr/search"
HTML = """<html><head>
<script src="/static/js/main.3f2a.js"></script>
<script src="https://cdn.other.net/lib.js"></script>
<script src="chunk/12.js"></script>
<script id="__NEXT_DATA__" type="application/json">{"props":{}}</script>
</head><body><form action="/auth/login" method="post"></form></body></html>"""
JS = """
const API = "/api/v2";
fetch("/api/v2/cases/search?q=" + q, {method: "POST"});
axios.post(`${API}/auth/signin`, body);
axios.get('/api/v2/cases/' + id);
$.ajax({url: "https://law.example.kr/api/v2/statutes"});
fetch("https://tracker.ads.net/api/collect");
const gql = "/graphql"; client.query({operationName: "CaseList"});
"""


def test_script_urls_same_origin_only():
    urls = X.script_urls(HTML, BASE)
    assert urls == ["https://law.example.kr/static/js/main.3f2a.js", "https://law.example.kr/chunk/12.js"]


def test_find_endpoints_ranks_same_host_and_flags_external():
    found = X.find_endpoints(JS, BASE)
    paths = [e["path"] for e in found["endpoints"]]
    assert "/api/v2/cases/search" in paths and "/api/v2/statutes" in paths and "/graphql" in paths
    assert "/api/v2/cases/" in paths
    assert all(e["url"].startswith("https://law.example.kr/") for e in found["endpoints"])
    assert found["external"] == ["https://tracker.ads.net/api/collect"]
    search = next(e for e in found["endpoints"] if e["path"] == "/api/v2/cases/search")
    assert search["method"] == "POST"
    assert any("signin" in p for p in found["auth_candidates"])
    assert "CaseList" in found["graphql_operations"]


def test_inline_state_and_forms():
    assert X.inline_state(HTML) == ["__NEXT_DATA__"]
    assert X.inline_state("<script>window.__APOLLO_STATE__ = {}</script>") == ["__APOLLO_STATE__"]
    assert X.form_actions(HTML, BASE) == [{"url": "https://law.example.kr/auth/login", "method": "POST"}]


def test_scaffold_renders_valid_pinned_client(tmp_path):
    out = S.scaffold("lawex", "https://law.example.kr/api/v2", auth="bearer-login", login_path="/auth/signin",
                     id_field="email", pw_field="password", token_field="accessToken", out_dir=str(tmp_path))
    src = open(out["path"], encoding="utf-8").read()
    ast.parse(src, feature_version=(3, 10))
    assert not re.search(r"\{\{[A-Z_]+\}\}", src) and 'API = "https://law.example.kr/api/v2"' in src
    assert 'KEYRING_SERVICE = "site-api-lawex"' in src and "# dependencies" in src
    spec = importlib.util.spec_from_file_location("lawex_client", out["path"])
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod._api_url("/cases/search") == "https://law.example.kr/api/v2/cases/search"
    assert mod._api_url("https://law.example.kr/api/v2/x?a=1") == "https://law.example.kr/api/v2/x?a=1"
    for bad in ("https://evil.example.com/api/v2/x", "http://law.example.kr/api/v2/x", "https://user@law.example.kr/x",
                "https://law.example.kr:8443/x"):
        with pytest.raises(mod.SiteError):
            mod._api_url(bad)


def test_scaffold_never_overwrites_and_validates(tmp_path):
    a = S.scaffold("lawex", "https://law.example.kr/api", out_dir=str(tmp_path))
    b = S.scaffold("lawex", "https://law.example.kr/api", out_dir=str(tmp_path))
    assert a["path"] != b["path"] and b["path"].endswith("lawex_2.py")
    for slug, base in (("Bad Slug", "https://x.kr"), ("ok", "http://x.kr"), ("ok", "https://u:p@x.kr"), ("ok", "ftp://x.kr")):
        with pytest.raises(ValueError):
            S.scaffold(slug, base, out_dir=str(tmp_path))
    with pytest.raises(ValueError):
        S.scaffold("ok", "https://x.kr", auth="oauth", out_dir=str(tmp_path))


def test_default_output_outside_plugin(monkeypatch):
    monkeypatch.delenv("LAWFIRM_SITE_API_DIR", raising=False)
    d = S.default_out_dir()
    assert not d.startswith(ROOT) and d.endswith("site-api")


@pytest.mark.parametrize("name,allowed", [("extract.py", {"html", "json", "re", "sys", "urllib", "argparse"}),
                                          ("scaffold.py", {"argparse", "json", "os", "re", "shlex", "sys", "urllib"})])
def test_stdlib_scripts(name, allowed):
    tree = ast.parse(open(os.path.join(SKILL, "scripts", name), encoding="utf-8").read(), feature_version=(3, 9))
    mods = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    mods |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert mods <= allowed, mods - allowed


def test_discover_has_inline_deps_and_robots_check():
    src = open(os.path.join(SKILL, "scripts", "discover.py"), encoding="utf-8").read()
    ast.parse(src, feature_version=(3, 10))
    assert "# /// script" in src and "scrapling" in src and "robots.txt" in src
    assert "import extract" in src or "from extract import" in src


def test_skill_doc():
    text = open(os.path.join(SKILL, "SKILL.md"), encoding="utf-8").read()
    head = text.split("---")[1]
    assert re.search(r"(?m)^name:\s*site-api\s*$", head)
    for word in ("robots.txt", "이용약관", "scrapling install", "discover.py", "scaffold.py", "키체인", "--prompt", "사람"):
        assert word in text, word
    assert "AskUserQuestion" not in text
    for p in re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/([\w./-]+\.py)", text):
        assert os.path.isfile(os.path.join(ROOT, p)), p


def test_scaffold_single_pass_no_code_injection(tmp_path):
    """값 안의 {{자리}} 를 다시 치환하지 않는다 — 제목에 자리표시자, 필드에 코드를 넣어도 생성 파일에 코드가 생기지 않는다."""
    out = S.scaffold("inj", "https://x.example.kr/api", title="{{ID_FIELD}}", out_dir=str(tmp_path))
    src = open(out["path"], encoding="utf-8").read()
    assert 'TITLE = "{{ID_FIELD}}"' in src
    for field in ("+exec(chr(111))+", "a b", 'x"y', ""):
        with pytest.raises(ValueError):
            S.scaffold("inj", "https://x.example.kr/api", id_field=field, out_dir=str(tmp_path))
    for lp in ("/login;rm", "login", "/a b"):
        with pytest.raises(ValueError):
            S.scaffold("inj", "https://x.example.kr/api", login_path=lp, out_dir=str(tmp_path))
    with pytest.raises(ValueError):
        S.scaffold("inj", "https://x.example.kr/api", title="a\nb", out_dir=str(tmp_path))


def test_scaffold_next_commands_are_quoted(tmp_path):
    d = tmp_path / "a b;echo hi"
    out = S.scaffold("qq", "https://x.example.kr/api", out_dir=str(d))
    assert all(("'" + out["path"] + "'") in c for c in out["next"] if c)


def test_discover_keeps_query_names_only():
    sys.path.insert(0, os.path.join(SKILL, "scripts"))
    import discover as DV
    assert DV.query_names("q=%ED%99%8D&token=abc123&page=2") == ["page", "q", "token"]
    assert DV.query_names("") == []


def test_robots_honors_claude_user_rules():
    """사람 요청으로 Claude 가 부르는 도구다 — `*` 규칙과 함께 `Claude-User` 규칙도 지킨다(casenote.kr 2026-10-15 형태)."""
    sys.path.insert(0, os.path.join(SKILL, "scripts"))
    import discover as DV
    text = "User-agent: *\nDisallow: /search/\nDisallow: /login/\n\nUser-agent: Claude-User\nDisallow: /\n"
    ok, blocked = DV.robots_decision(text, "https://casenote.kr/")
    assert ok is False and blocked == ["Claude-User"]
    only_star = "User-agent: *\nDisallow: /search/\n"
    assert DV.robots_decision(only_star, "https://x.kr/")[0] is True
    assert DV.robots_decision(only_star, "https://x.kr/search/?q=a") == (False, ["Claude-User", "*"])
    assert DV.robots_decision("", "https://x.kr/search/")[0] is True
