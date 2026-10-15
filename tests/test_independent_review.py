"""independent-review — 고치지 않고 지적만 하는 독립 검토자. 본문 추출(docx·md)과 기계적 형식 점검."""
import ast
import json
import os
import re
import sys

import pytest

from conftest import ROOT

SKILL = os.path.join(ROOT, "skills", "independent-review")
sys.path.insert(0, os.path.join(SKILL, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "skills", "intent-brief", "scripts"))
import doc_text as T  # noqa: E402

DRAFT = """# 준비서면

1. 원고는 피고에게 2026. 1. 5. 금 5,000만원을 대여하였습니다.
2. 피고는 이를 를 변제하지  아니하였다.
3. 「대여 사실은 갑 제1호증, 갑 제3호증으로 입증합니다.
4. (증거 설명 [확인 필요: 이체 일자]
"""


def test_markdown_paragraphs(tmp_path):
    p = tmp_path / "d.md"
    p.write_text(DRAFT, encoding="utf-8")
    out = T.read_doc(str(p))
    assert out["paragraphs"][0] == "# 준비서면" and len(out["paragraphs"]) == 5


def test_docx_paragraphs_and_tables(tmp_path):
    import render_docx as R
    body = ('<w:p><w:r><w:t>첫 문단</w:t></w:r><w:r><w:t xml:space="preserve"> 이어짐</w:t></w:r></w:p>'
            '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>표 칸</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
            '<w:p><w:r><w:t>끝 문단</w:t></w:r></w:p>')
    path = str(tmp_path / "x.docx")
    R.write_docx(path, body)
    out = T.read_doc(path)
    assert out["paragraphs"] == ["첫 문단 이어짐", "표 칸", "끝 문단"]


def test_lint_finds_mechanical_issues(tmp_path):
    p = tmp_path / "d.md"
    p.write_text(DRAFT, encoding="utf-8")
    found = T.lint(str(p))["findings"]
    kinds = {(f["kind"], f["paragraph"]) for f in found}
    assert ("겹친 낱말", 3) in kinds and ("공백", 3) in kinds
    assert ("짝 없는 괄호", 4) in kinds and ("짝 없는 괄호", 5) in kinds
    assert ("증거번호 건너뜀", 4) in kinds
    assert ("확인 필요 남음", 5) in kinds
    style = [f for f in found if f["kind"] == "문체 혼용"]
    assert style and style[0]["paragraph"] == 3
    assert all(f["severity"] in ("높음", "중간", "낮음") for f in found)


def test_lint_clean_text(tmp_path):
    p = tmp_path / "ok.md"
    p.write_text("원고는 대여 사실을 갑 제1호증으로 입증합니다.\n피고의 주장은 이유 없습니다.\n", encoding="utf-8")
    assert T.lint(str(p))["findings"] == []


def test_cli(tmp_path, capsys):
    p = tmp_path / "d.md"
    p.write_text(DRAFT, encoding="utf-8")
    assert T.main(["text", str(p)]) == 0
    assert json.loads(capsys.readouterr().out)["paragraphs"][1].startswith("1.")
    assert T.main(["lint", str(tmp_path / "없음.md")]) == 3


def test_stdlib_py39():
    tree = ast.parse(open(os.path.join(SKILL, "scripts", "doc_text.py"), encoding="utf-8").read(), feature_version=(3, 9))
    mods = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    mods |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert mods <= {"argparse", "json", "os", "re", "sys", "zipfile", "xml"}, mods


def test_skill_contract():
    text = open(os.path.join(SKILL, "SKILL.md"), encoding="utf-8").read()
    head = text.split("---")[1]
    assert re.search(r"(?m)^name:\s*independent-review\s*$", head)
    allowed = re.search(r"(?m)^allowed-tools:(.*)$", head).group(1)
    assert "Edit" not in allowed and "Write" not in allowed
    for area in ("오탈자", "설득력", "문체", "체계", "누락", "형식"):
        assert area in text, area
    for word in ("[높음]", "[중간]", "[낮음]", "판정", "고치지 않", "doc_text.py"):
        assert word in text, word
    assert "AskUserQuestion" not in text
    for p in re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/([\w./-]+\.py)", text):
        assert os.path.isfile(os.path.join(ROOT, p)), p


def test_docx_with_entities_rejected(tmp_path):
    import zipfile
    path = str(tmp_path / "bomb.docx")
    xml = ('<?xml version="1.0"?><!DOCTYPE w [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>&b;</w:t></w:r></w:p></w:body></w:document>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", xml)
    with pytest.raises(ValueError):
        T.read_doc(path)


def test_docx_utf16_entities_rejected(tmp_path):
    """UTF-16 으로 인코딩해 바이트 검사를 피한 엔티티 선언도 거부한다(GC Run #2 지적)."""
    import zipfile
    path = str(tmp_path / "bomb16.docx")
    xml = ('<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE w [<!ENTITY a "x">]>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>&a;</w:t></w:r></w:p></w:body></w:document>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", xml.encode("utf-16"))
    with pytest.raises(ValueError):
        T.read_doc(path)
