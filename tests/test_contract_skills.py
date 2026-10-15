"""review-contract·triage-nda — 한국법 계약 검토 절차 문서와 플레이북(검토 기준) 파일 관리."""
import ast
import json
import os
import re
import sys

import pytest

from conftest import ROOT

RC = os.path.join(ROOT, "skills", "review-contract")
NDA = os.path.join(ROOT, "skills", "triage-nda")
sys.path.insert(0, os.path.join(RC, "scripts"))
import playbook as P  # noqa: E402


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("LAWFIRM_PLAYBOOK_DIR", str(tmp_path))
    return tmp_path


def read(p):
    return open(p, encoding="utf-8").read()


def test_show_falls_back_to_bundled_default(home):
    out = P.show("contract")
    assert out["default"] is True and out["exists"] is False and "## 손해배상" in out["text"]
    assert P.show("nda")["default"] is True


def test_init_creates_once_and_never_overwrites(home):
    first = P.init("nda")
    assert first["created"] is True and os.path.isfile(first["path"]) and first["path"].startswith(str(home))
    with open(first["path"], "a", encoding="utf-8") as f:
        f.write("\n- 우리 회사 기준: 비밀유지 3년\n")
    again = P.init("nda")
    assert again["created"] is False and "비밀유지 3년" in read(first["path"])
    shown = P.show("nda")
    assert shown["default"] is False and "비밀유지 3년" in shown["text"]


def test_unknown_kind(home):
    with pytest.raises(ValueError):
        P.show("lease")


def test_default_dir_is_outside_plugin(monkeypatch):
    monkeypatch.delenv("LAWFIRM_PLAYBOOK_DIR", raising=False)
    d = P.playbook_dir()
    assert d.endswith(os.path.join("intent-brief", "playbooks")) or d.endswith(os.path.join(".intent-brief", "playbooks"))
    assert not d.startswith(ROOT)


def test_cli(home, capsys):
    assert P.main(["path", "contract"]) == 0
    assert json.loads(capsys.readouterr().out)["exists"] is False
    assert P.main(["init", "contract"]) == 0 and json.loads(capsys.readouterr().out)["created"] is True
    assert P.main(["show", "xx"]) == 3


def test_stdlib_py39():
    tree = ast.parse(read(os.path.join(RC, "scripts", "playbook.py")), feature_version=(3, 9))
    mods = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    mods |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert mods <= {"argparse", "json", "os", "shutil", "sys"}, mods


@pytest.mark.parametrize("skill,name,cites", [
    (RC, "review-contract", ["약관의 규제에 관한 법률 제6조", "약관의 규제에 관한 법률 제7조", "민법 제398조", "상법 제69조",
                             "민법 제449조", "개인정보 보호법 제26조", "민사소송법 제29조", "중재법 제8조", "국제사법 제45조",
                             "하도급거래 공정화에 관한 법률 제3조의4", "근로기준법 제20조"]),
    (NDA, "triage-nda", ["부정경쟁방지 및 영업비밀보호에 관한 법률 제2조", "민법 제398조", "근로기준법 제20조", "민사소송법 제29조"]),
])
def test_skill_docs(skill, name, cites):
    text = read(os.path.join(skill, "SKILL.md"))
    head = text.split("---")[1]
    assert re.search(r"(?m)^name:\s*%s\s*$" % name, head) and re.search(r"(?m)^description:", head)
    for c in cites:
        assert c in text, c
    for word in ("playbook.py", "GREEN", "YELLOW", "RED", "내부_", "[확인 필요"):
        assert word in text, word
    assert "AskUserQuestion" not in text and "legal.local.md" not in text
    for p in re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/([\w./-]+\.py)", text):
        assert os.path.isfile(os.path.join(ROOT, p)), p


def test_notice_lists_adapted_skills():
    notice = read(os.path.join(ROOT, "third_party", "anthropic-legal", "NOTICE.md"))
    assert "review-contract" in notice and "triage-nda" in notice


def test_client_profile_does_not_touch_office_playbook(home):
    """의뢰인별 기준은 따로 둔다 — 고쳐도 사무소 기본 플레이북에 번지지 않는다(Codex 지적 8)."""
    office = P.init("contract")
    a = P.init("contract", profile="가나상사")
    assert a["created"] is True and a["path"] != office["path"] and a["profile"] == "가나상사"
    with open(a["path"], "a", encoding="utf-8") as f:
        f.write("\n- 가나상사 기준: 책임 상한 200%\n")
    assert "가나상사 기준" not in P.show("contract")["text"]
    assert "가나상사 기준" in P.show("contract", profile="가나상사")["text"]
    assert P.show("contract", profile="다라")["default"] is False  # 의뢰인 기준이 없으면 사무소 기본값
    for bad in ("../x", "a/b", "", ".."):
        with pytest.raises(ValueError):
            P.path("contract", profile=bad)


def test_review_contract_reads_whole_contract():
    text = read(os.path.join(RC, "SKILL.md"))
    assert "핵심 조항(대금·책임·해지·분쟁)부터 보고" not in text
    assert "미검토" in text
