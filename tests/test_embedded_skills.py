"""lyn-lawfirm(thechain.lawyer)에서 내장한 스킬 6개 — MCP 의존이 다시 들어오지 않고, 안내한 명령이 실제로 있는지."""
import os
import re

import pytest

from conftest import ROOT

EMBEDDED = ["certified-letter", "complaint-drafter", "criminal-procedure-simulator", "criminal-settlement",
            "fact-confirmation", "sentencing-predictor"]
SKILLS = os.path.join(ROOT, "skills")
LOOKUP = os.path.join(ROOT, "references", "law-lookup.md")
FORBIDDEN = re.compile(r"k-data|korean-law|legal_research|case_research|search_cases|get_case_detail|search_laws|get_law_detail|"
                       r"get_law_article_sub|search_constitutional|search_interpretations|suggest_connectors|search_mcp_registry|"
                       r"claude mcp add|/sessions/|mnt/outputs|/mnt/|/home/claude|computer://|request_cowork_directory|AskUserQuestion")


def read(p):
    return open(p, encoding="utf-8").read()


def skill_texts():
    for name in EMBEDDED:
        d = os.path.join(SKILLS, name)
        for root, _, files in os.walk(d):
            for f in files:
                if f.endswith((".md", ".js")):
                    yield name, os.path.join(root, f)


def test_all_present_with_frontmatter():
    assert sorted(n for n in os.listdir(SKILLS) if os.path.isdir(os.path.join(SKILLS, n))) == sorted(EMBEDDED + ["intent-brief"])
    for name in EMBEDDED:
        head = read(os.path.join(SKILLS, name, "SKILL.md")).split("---")[1]
        assert re.search(r"(?m)^name:\s*%s\s*$" % re.escape(name), head)
        assert re.search(r"(?m)^description:", head)


@pytest.mark.parametrize("name,path", list(skill_texts()))
def test_no_mcp_or_sandbox_leftovers(name, path):
    text = read(path)
    m = FORBIDDEN.search(text)
    assert not m, "%s: %r" % (os.path.relpath(path, ROOT), m.group(0))
    for ln in text.splitlines():
        if "MCP" in ln:
            assert "MCP 를 쓰지 않" in ln, ln[:120]


def test_relative_references_resolve():
    for name, path in skill_texts():
        for ref in re.findall(r"`(\.\./\.\./[^`]+)`", read(path)):
            assert os.path.exists(os.path.normpath(os.path.join(os.path.dirname(path), ref))), (path, ref)


def _subcommands(script):
    src = read(os.path.join(SKILLS, "intent-brief", "scripts", script))
    return set(re.findall(r'add_parser\("([a-z-]+)"\)', src))


def test_documented_commands_exist():
    subs = {"lawapi.py": _subcommands("lawapi.py"), "casesearch.py": _subcommands("casesearch.py")}
    texts = [read(LOOKUP)] + [read(p) for _, p in skill_texts()] + [read(os.path.join(SKILLS, "intent-brief", "SKILL.md"))]
    seen = 0
    for t in texts:
        for script, sub in re.findall(r"(lawapi\.py|casesearch\.py)\"? (?:\"?)([a-z][a-z-]+)", t):
            assert sub in subs[script], (script, sub)
            seen += 1
    assert seen >= 20


def test_skills_point_to_lookup():
    for name in ("certified-letter", "complaint-drafter", "criminal-procedure-simulator", "sentencing-predictor"):
        assert "../../references/law-lookup.md" in read(os.path.join(SKILLS, name, "SKILL.md")), name


def test_no_inline_json_in_shell():
    """사용자 입력이 든 JSON 을 셸 인자에 따옴표로 넣지 않는다(이름에 ' 가 있으면 명령 주입) — 파일로 넘긴다."""
    for name, path in skill_texts():
        assert not re.search(r"--data\s+'<", read(path)), path


def test_cta_shared_file_present():
    assert os.path.exists(os.path.join(ROOT, "references", "cta-config.md"))
