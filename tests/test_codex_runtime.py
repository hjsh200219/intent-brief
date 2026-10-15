"""Codex 기본 샌드박스(workspace-write)에서 실제로 막히는 것을 사람이 알아볼 수 있게 — 2026-10-16 macOS codex-cli 0.162.1 실측.

- 네트워크: 막히면 DNS 실패(gaierror)로 보여 법제처 장애와 구별되지 않는다. Codex 는 CODEX_SANDBOX_NETWORK_DISABLED=1 을 준다.
- 작업 폴더(~/.intent-brief) 쓰기: PermissionError. Codex 는 CODEX_SANDBOX=seatbelt 를 준다.
- 입력 창: 실패를 「취소」로 보면 등록 절차가 끝나 버린다 — osascript 취소는 -128, 우리 PowerShell 창의 취소는 종료 코드 3.
"""
import importlib.util
import json
import os
import socket
import subprocess
import sys
import types
import urllib.error

import pytest

from conftest import ROOT

sys.path.insert(0, os.path.join(ROOT, "skills", "intent-brief", "scripts"))
sys.path.insert(0, os.path.join(ROOT, "skills", "case-search", "scripts"))
sys.path.insert(0, os.path.join(ROOT, "skills", "litigation-calc", "scripts"))
import _paths as P  # noqa: E402
import cite_check as CC  # noqa: E402
import dday as DD  # noqa: E402
import foreigncase as FC  # noqa: E402
import lawapi as L  # noqa: E402


def _dns_fail(*a, **k):
    raise urllib.error.URLError(socket.gaierror(8, "nodename nor servname provided, or not known"))


def test_lawapi_reports_sandbox_network_block(monkeypatch, capsys):
    monkeypatch.setenv("CODEX_SANDBOX_NETWORK_DISABLED", "1")
    monkeypatch.setattr(L.urllib.request, "urlopen", _dns_fail)
    monkeypatch.setattr(L.time, "sleep", lambda s: None)
    with pytest.raises(L.NetworkBlocked):
        L.Client(oc="x", interval=0).get("lawSearch.do", target="law", query="민법")
    monkeypatch.setattr(L, "find_key", lambda: ("x", "test"))
    code = L.main(["law", "민법"])
    out = json.loads(capsys.readouterr().out)
    assert code == 7 and out["error"] == "network_blocked" and "장애가 아닙니다" in out["detail"]


def test_lawapi_without_sandbox_is_still_outage(monkeypatch):
    monkeypatch.delenv("CODEX_SANDBOX_NETWORK_DISABLED", raising=False)
    monkeypatch.setattr(L.urllib.request, "urlopen", _dns_fail)
    monkeypatch.setattr(L.time, "sleep", lambda s: None)
    with pytest.raises(L.Unavailable) as e:
        L.Client(oc="x", interval=0).get("lawSearch.do")
    assert not isinstance(e.value, L.NetworkBlocked)


def test_cite_check_stops_instead_of_tagging_outage(monkeypatch, capsys):
    monkeypatch.setenv("CODEX_SANDBOX_NETWORK_DISABLED", "1")
    monkeypatch.setattr(L.urllib.request, "urlopen", _dns_fail)
    monkeypatch.setattr(L, "find_key", lambda: ("x", "test"))
    assert CC.main(["ping"]) == 7
    assert json.loads(capsys.readouterr().out)["error"] == "network_blocked"
    checker = types.SimpleNamespace(client=types.SimpleNamespace(written=[]))
    checker.check_law = lambda c: (_ for _ in ()).throw(L.NetworkBlocked("x"))
    with pytest.raises(L.NetworkBlocked):
        CC.Checker.check(checker, {"kind": "law"})


def test_foreigncase_reports_sandbox_network_block(monkeypatch):
    monkeypatch.setenv("CODEX_SANDBOX_NETWORK_DISABLED", "1")
    monkeypatch.setattr(FC.urllib.request, "urlopen", _dns_fail)
    with pytest.raises(FC.ForeignError) as e:
        FC._fetch("https://www.courtlistener.com/api/rest/v4/search/?q=x")
    assert e.value.code == "network_blocked"


def test_paths_sandbox_write_block_is_explained(monkeypatch, capsys):
    monkeypatch.setenv("CODEX_SANDBOX", "seatbelt")
    err = PermissionError(1, "Operation not permitted", os.path.expanduser("~/.intent-brief/cases"))
    P._excepthook(PermissionError, err, None)
    out = json.loads(capsys.readouterr().out)
    assert out["error"] == "sandbox_write_blocked" and "writable_roots" in out["guide"]


def _run(rc, stdout="", stderr=""):
    return lambda *a, **k: types.SimpleNamespace(returncode=rc, stdout=stdout, stderr=stderr)


@pytest.mark.parametrize("mod,err", [(L, P.BriefError), (FC, FC.ForeignError)])
def test_dialog_cancel_vs_failure(monkeypatch, mod, err):
    monkeypatch.setattr(mod.subprocess, "run", _run(1, "", "execution error: User canceled. (-128)"))
    with pytest.raises(err) as e:
        mod._osascript_dialog("m", "t", True)
    assert "취소" in str(e.value)
    monkeypatch.setattr(mod.subprocess, "run", _run(1, "", "Operation not permitted"))
    with pytest.raises(err) as e:
        mod._osascript_dialog("m", "t", True)
    assert "띄우지 못했습니다" in str(e.value) and "터미널" in str(e.value)
    monkeypatch.setattr(mod.subprocess, "run", _run(3, b"", b""))
    with pytest.raises(err) as e:
        mod._windows_dialog("m", "t", True)
    assert "취소" in str(e.value)
    monkeypatch.setattr(mod.subprocess, "run", _run(1, b"", b"Access denied"))
    with pytest.raises(err) as e:
        mod._windows_dialog("m", "t", True)
    assert "띄우지 못했습니다" in str(e.value)


def test_site_api_client_dialog_cancel_vs_failure(tmp_path, monkeypatch):
    sys.path.insert(0, os.path.join(ROOT, "skills", "site-api", "scripts"))
    import scaffold as S
    out = S.scaffold("dlg", "https://law.example.kr/api", out_dir=str(tmp_path))
    spec = importlib.util.spec_from_file_location("dlg_client", out["path"])
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod.sys, "stdin", types.SimpleNamespace(isatty=lambda: False))
    monkeypatch.setattr(mod.sys, "platform", "darwin")
    monkeypatch.setattr(mod.subprocess, "run", _run(1, "", "Operation not permitted"))
    with pytest.raises(mod.SiteError) as e:
        mod.ask("비밀번호", hidden=True)
    assert "띄우지 못했습니다" in str(e.value)
    monkeypatch.setattr(mod.subprocess, "run", _run(1, "", "User canceled. (-128)"))
    with pytest.raises(mod.SiteError) as e:
        mod.ask("비밀번호", hidden=True)
    assert "취소" in str(e.value)


def test_windows_dialog_scripts_use_cancel_code_3():
    for rel in ("skills/intent-brief/scripts/lawapi.py", "skills/case-search/scripts/foreigncase.py",
                "skills/case-search/scripts/bigcase.py", "skills/site-api/templates/client.py.tmpl"):
        src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        assert "{exit 3}" in src and "{exit 1}" not in src, rel


def test_dday_hook_reports_its_own_failure(home, monkeypatch, capsys):
    monkeypatch.setattr(DD, "scan", lambda **k: (_ for _ in ()).throw(PermissionError(1, "Operation not permitted")))
    assert DD.main(["hook"]) == 0
    ctx = json.loads(capsys.readouterr().out)["hookSpecificOutput"]["additionalContext"]
    assert "점검하지 못했습니다" in ctx and "PermissionError" in ctx


def test_windows_hook_tries_python3_too():
    with open(os.path.join(ROOT, "hooks", "hooks.json"), encoding="utf-8") as f:
        win = json.load(f)["hooks"]["SessionStart"][0]["hooks"][0]["commandWindows"]
    assert win.index("py -3") < win.index("python3 ") < win.index("python \"")


def test_docs_for_codex_shells():
    site = open(os.path.join(ROOT, "skills", "site-api", "SKILL.md"), encoding="utf-8").read()
    assert "chrome.exe" in site  # Windows 에서도 원격 디버깅 Chrome 을 띄울 수 있어야 한다
    for rel in ("skills/intent-brief/SKILL.md", "commands/law-key-setup.md"):
        text = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        assert "따옴표로 묶지 않고" in text, rel  # "$PY" 에 "py -3" 을 넣으면 실행되지 않는다
        assert "network_blocked" in text, rel
    readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    assert "writable_roots" in readme and "network_access" in readme
