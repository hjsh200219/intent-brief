"""brainstorming-lawfirm — IRAC·레드팀 절차 문서와 심각도×가능성 점수표(risk.py)."""
import ast
import json
import os
import re
import sys

import pytest

from conftest import ROOT

SKILL_DIR = os.path.join(ROOT, "skills", "brainstorming-lawfirm")
sys.path.insert(0, os.path.join(SKILL_DIR, "scripts"))
import risk as R  # noqa: E402


@pytest.mark.parametrize("sev,lik,level", [(1, 1, "GREEN"), (2, 2, "GREEN"), (1, 5, "YELLOW"), (3, 3, "YELLOW"),
                                           (2, 5, "ORANGE"), (5, 3, "ORANGE"), (4, 4, "RED"), (5, 5, "RED")])
def test_score_levels(sev, lik, level):
    r = R.score(sev, lik)
    assert r["score"] == sev * lik and r["level"] == level and r["label"] and r["actions"]


@pytest.mark.parametrize("sev,lik", [(0, 3), (6, 1), (3, "x")])
def test_score_rejects_out_of_range(sev, lik):
    with pytest.raises(ValueError):
        R.score(sev, lik)


def test_table_sorts_and_counts(tmp_path):
    items = [{"id": "A", "title": "소멸시효 항변", "severity": 4, "likelihood": 2, "basis": "민법 제162조"},
             {"id": "B", "title": "변제 입증 부족", "severity": 5, "likelihood": 4, "basis": "을2 영수증 없음"},
             {"id": "C", "title": "관할", "severity": 1, "likelihood": 1, "basis": ""}]
    p = tmp_path / "r.json"
    p.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    out = R.table(str(p))
    assert [r["id"] for r in out["rows"]] == ["B", "A", "C"]
    assert out["counts"] == {"RED": 1, "ORANGE": 0, "YELLOW": 1, "GREEN": 1}
    lines = out["markdown"].splitlines()
    assert lines[0].startswith("| 순위 |") and "| 1 | B | 변제 입증 부족 | 5 | 4 | 20 | RED" in lines[2]


def test_cli(capsys, tmp_path):
    assert R.main(["score", "4", "3"]) == 0
    assert json.loads(capsys.readouterr().out)["level"] == "ORANGE"
    assert R.main(["score", "9", "3"]) == 3
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_stdlib_py39():
    src = open(os.path.join(SKILL_DIR, "scripts", "risk.py"), encoding="utf-8").read()
    tree = ast.parse(src, feature_version=(3, 9))
    mods = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    mods |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert mods <= {"argparse", "json", "sys"}, mods


def test_skill_procedure():
    text = open(os.path.join(SKILL_DIR, "SKILL.md"), encoding="utf-8").read()
    head = text.split("---")[1]
    assert re.search(r"(?m)^name:\s*brainstorming-lawfirm\s*$", head) and "IRAC" in head and "레드팀" in head
    for word in ("쟁점(Issue)", "규범(Rule)", "포섭(Application)", "결론(Conclusion)", "레드팀", "재반박", "risk.py",
                 "deadline.py", "costs.py", "[확인 필요", "내부_", "변호사법 제109조"):
        assert word in text, word
    assert "AskUserQuestion" not in text
    for p in re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/([\w./-]+\.py)", text):
        assert os.path.isfile(os.path.join(ROOT, p)), p


def test_apache_notice_for_adapted_framework():
    notice = open(os.path.join(ROOT, "third_party", "anthropic-legal", "NOTICE.md"), encoding="utf-8").read()
    assert "legal-risk-assessment" in notice and "Apache License" in notice
    assert os.path.isfile(os.path.join(ROOT, "third_party", "anthropic-legal", "LICENSE"))
