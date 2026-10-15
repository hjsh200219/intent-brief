"""Codex 에서도 같은 repo 를 플러그인으로 설치한다 — `codex plugin marketplace add hjsh200219/lawfirm` → `codex plugin add lawfirm@lawfirm`.

Codex 는 `.codex-plugin/plugin.json`·`.agents/plugins/marketplace.json` 을 먼저 읽는다(없으면 `.claude-plugin/` 을 읽는다 — codex-cli 0.162.1 실측).
스킬·명령·훅 파일은 Claude 와 같은 것을 쓴다. 훅 출력은 두 쪽이 다 받는 JSON(hookSpecificOutput.additionalContext)이어야 한다 —
Codex 는 일반 텍스트 출력을 「SessionStart Failed」로 버린다(같은 실측).
"""
import json
import os

from conftest import ROOT


def _load(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return json.load(f)


def test_codex_manifest_matches_claude():
    claude, codex = _load(".claude-plugin", "plugin.json"), _load(".codex-plugin", "plugin.json")
    assert codex["name"] == claude["name"] == "lawfirm"
    assert codex["version"] == claude["version"]
    assert codex["skills"] == "./skills/" and os.path.isdir(os.path.join(ROOT, "skills"))
    assert codex["hooks"] == "./hooks/hooks.json" and os.path.isfile(os.path.join(ROOT, "hooks", "hooks.json"))
    ui = codex["interface"]
    for key in ("displayName", "shortDescription", "longDescription", "developerName", "category", "defaultPrompt"):
        assert ui.get(key), key
    assert "AI" in ui["longDescription"] and "책임" in ui["longDescription"]


def test_codex_marketplace():
    m = _load(".agents", "plugins", "marketplace.json")
    assert m["name"] == "lawfirm"  # Claude 마켓플레이스 이름과 같게 — 설치 명령이 lawfirm@lawfirm 으로 같다
    (p,) = m["plugins"]
    assert p["name"] == "lawfirm" and p["source"] == {"source": "local", "path": "./"}
    assert p["policy"]["installation"] == "AVAILABLE"


def test_all_manifest_versions_agree():
    v = _load(".claude-plugin", "plugin.json")["version"]
    assert [x["version"] for x in _load(".claude-plugin", "marketplace.json")["plugins"]] == [v]
    assert _load(".codex-plugin", "plugin.json")["version"] == v


def test_verify_docs_checks_codex_manifest():
    src = open(os.path.join(ROOT, "dev", "verify_docs.py"), encoding="utf-8").read()
    assert ".codex-plugin" in src


ROOT_NOTE = "Codex 에서는 셸에 `${CLAUDE_PLUGIN_ROOT}` 가 없다"


def _model_docs():
    for d in ("skills", "commands", "references"):
        for base, _dirs, files in os.walk(os.path.join(ROOT, d)):
            for f in files:
                if f.endswith(".md"):
                    yield os.path.join(base, f)


def test_plugin_root_placeholder_has_codex_note():
    """Codex 는 훅에만 CLAUDE_PLUGIN_ROOT 를 넘기고 셸 도구에는 넘기지 않는다(실측: echo 결과 빈 값) — 문서가 대신 알려 준다."""
    using = [p for p in _model_docs() if "${CLAUDE_PLUGIN_ROOT}" in open(p, encoding="utf-8").read()]
    assert len(using) >= 10
    for p in using:
        assert ROOT_NOTE in open(p, encoding="utf-8").read(), os.path.relpath(p, ROOT)


def test_commands_avoid_arguments_placeholder():
    """Codex 는 $ARGUMENTS 를 쓰는 명령을 스킬로 옮기지 않고 빠뜨린다(실측: case-search-setup 누락)."""
    for f in os.listdir(os.path.join(ROOT, "commands")):
        assert "$ARGUMENTS" not in open(os.path.join(ROOT, "commands", f), encoding="utf-8").read(), f
