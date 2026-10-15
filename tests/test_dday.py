"""기한·기일 D-day 점검 — 사건메모 「주요 일정」을 모아 14일 이내를 알린다. 세션 시작 훅은 없으면 아무것도 출력하지 않는다."""
import json
import os
import subprocess
import sys

import pytest

from conftest import ROOT

SCRIPTS = os.path.join(ROOT, "skills", "litigation-calc", "scripts")
DDAY = os.path.join(SCRIPTS, "dday.py")
sys.path.insert(0, SCRIPTS)
import dday as DD  # noqa: E402

MEMO = """# 손해배상(가명) — 사건메모

## 기본정보
- 의뢰인: 가명갑(원고)

## 주요 일정
- 2026-09-18 항소 기한 (판결서 송달 09-04)
- 2026.09.22 14:00 제2회 변론기일
- 2026-09-25 준비서면 제출기한
- ~~2026-09-16 증거신청 기한~~
- 2026-09-17 감정서 제출 (완료)
- 2026-10-30 소멸시효 만료 예정
- 2026-09-10 지난 기일

## 진행 경과
- 2026-09-01: 상담
"""


def _case(root, name, memo=MEMO):
    d = root / name
    d.mkdir(parents=True)
    (d / "사건메모.md").write_text(memo, encoding="utf-8")
    return d


def test_scan_root_collects_upcoming_and_flags_critical(home, tmp_path):
    root = tmp_path / "사건"
    _case(root, "260901_손해배상(가명갑)")
    DD.roots_add(str(root))
    out = DD.scan(days=14)
    got = [(i["date"], i["d_day"], i["kind"], i["critical"]) for i in out["items"]]
    assert got == [("2026-09-18", 3, "기한", True), ("2026-09-22", 7, "기일", False), ("2026-09-25", 10, "기한", False)]
    assert out["items"][0]["case"] == "260901_손해배상(가명갑)"
    wide = DD.scan(days=60)
    assert any(i["date"] == "2026-10-30" and i["critical"] for i in wide["items"])


def test_cases_from_intent_brief_state(home, tmp_path):
    case_dir = _case(tmp_path / "elsewhere", "260915_대여금(가명을)")
    sys.path.insert(0, os.path.join(ROOT, "skills", "intent-brief", "scripts"))
    import _paths as P
    sd = P.case_work_dir(str(case_dir))
    with open(os.path.join(sd, "준비서면_state.json"), "w", encoding="utf-8") as f:
        json.dump({"case_dir": str(case_dir)}, f, ensure_ascii=False)
    items = DD.scan(days=14)["items"]
    assert {i["case"] for i in items} == {"260915_대여금(가명을)"} and len(items) == 3


def test_hook_prints_nothing_without_cases(home, capsys):
    assert DD.main(["hook"]) == 0
    assert capsys.readouterr().out == ""


def test_hook_lines(home, tmp_path, capsys):
    root = tmp_path / "사건"
    _case(root, "260901_손해배상(가명갑)")
    DD.roots_add(str(root))
    assert DD.main(["hook"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0].startswith("[lawfirm]") and "3건" in lines[0]
    assert lines[1].startswith("- D-3 2026-09-18(금) 260901_손해배상(가명갑): 항소 기한") and "불변기간·시효" in lines[1]
    assert len(lines) == 4


def test_hook_never_fails(home, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(DD, "scan", lambda **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert DD.main(["hook"]) == 0
    assert capsys.readouterr().out == ""


def test_roots_add_list_remove(home, tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    DD.roots_add(str(root))
    DD.roots_add(str(root))
    assert DD.roots_list()["roots"] == [str(root)]
    DD.roots_remove(str(root))
    assert DD.roots_list()["roots"] == []
    with pytest.raises(ValueError):
        DD.roots_add(str(tmp_path / "없는폴더"))


def test_hook_subprocess_exit_zero_on_empty_home(home):
    env = dict(os.environ)
    r = subprocess.run([sys.executable, DDAY, "hook"], capture_output=True, text=True, env=env, timeout=30)
    assert r.returncode == 0 and r.stdout == ""


def test_plugin_hooks_json():
    with open(os.path.join(ROOT, "hooks", "hooks.json"), encoding="utf-8") as f:
        h = json.load(f)
    entries = h["hooks"]["SessionStart"]
    assert len(entries) == 1 and entries[0]["matcher"] == "startup|resume"
    hook = entries[0]["hooks"][0]
    assert hook["type"] == "command" and hook["timeout"] <= 15
    cmd = hook["command"]
    assert "${CLAUDE_PLUGIN_ROOT}/skills/litigation-calc/scripts/dday.py" in cmd and cmd.rstrip().endswith("|| true")
    assert "python3" in cmd and "py -3" in cmd
    assert os.path.isfile(DDAY)


def test_not_done_lines_are_kept(home, tmp_path):
    """「미완료」·「완료 예정」은 완료 표시가 아니다 — 기한을 숨기면 안 된다."""
    memo = ("## 주요 일정\n- 2026-09-20 답변서 제출 미완료\n- 2026-09-21 증거설명서 제출 완료 예정\n"
            "- 2026-09-22 감정서 제출 (완료)\n- 2026-09-23 [완료] 보정서 제출\n- [x] 2026-09-24 송달료 납부\n")
    root = tmp_path / "사건"
    _case(root, "261002_가명정", memo)
    DD.roots_add(str(root))
    assert [i["date"] for i in DD.scan(days=14)["items"]] == ["2026-09-20", "2026-09-21"]
