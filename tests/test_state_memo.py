import hashlib
import importlib.util
import json
import os
import shutil
import sys
import unicodedata

import pytest

import _paths as P
import memo as M
import state as S
from conftest import F1, F2, F3, F1_BASE, make_state

DEMO = "/Users/edb_development/workspace/ProjectLawFirm/agent-lawfirm/docs/references/업무관리시스템_데모"


# ── 작업 폴더·상태 ─────────────────────────────────────────────
def test_work_dir_outside_case(home, case):
    c = case(F1)
    path, _ = make_state(c)
    assert path.startswith(str(home))
    assert not os.path.commonpath([path, c]) == c
    assert os.listdir(c) == os.listdir(F1)  # 사건 폴더에 새 파일·폴더 0


def test_work_root_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(P.os, "name", "nt")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LA"))
    assert P.work_root() == os.path.join(str(tmp_path / "LA"), "intent-brief")


def test_plugin_data_env_ignored(home, case, monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "plugdata"))
    path, _ = make_state(case(F1))
    assert "plugdata" not in path


def test_case_key_nfc_nfd(tmp_path):
    nfc = tmp_path / unicodedata.normalize("NFC", "대여금 청구")
    nfd = str(tmp_path) + os.sep + unicodedata.normalize("NFD", "대여금 청구")
    assert P.case_key(str(nfc)) == P.case_key(nfd)


def test_atomic_save_keeps_old_on_error(home, case, monkeypatch):
    path, st = make_state(case(F1))
    before = open(path, "rb").read()

    def boom(*a, **k):
        raise RuntimeError("중간 실패")
    monkeypatch.setattr(P.json, "dumps", boom)
    with pytest.raises(RuntimeError):
        S.save(path, st)
    monkeypatch.undo()
    assert open(path, "rb").read() == before
    assert not [n for n in os.listdir(os.path.dirname(path)) if n.endswith(".tmp")]


def test_status_transitions():
    st = {"status": "interviewing"}
    with pytest.raises(P.BriefError):
        S.set_status(st, "designed")  # 설계 확인을 건너뛸 수 없다
    S.set_status(st, "confirming")
    S.set_status(st, "designed")
    S.set_status(st, "drafted")
    S.set_status(st, "recorded")


def test_apply_validation(home, case, params):
    path, st = make_state(case(F1))
    with pytest.raises(P.BriefError):
        S.apply_update(st, {"issues": [{"id": 1, "stance": "반쯤"}]}, params)
    with pytest.raises(P.BriefError):
        S.apply_update(st, {"issues": [{"id": 1, "amount": "천만원"}]}, params)
    with pytest.raises(P.BriefError):
        S.apply_update(st, {"bogus": 1}, params)
    with pytest.raises(P.BriefError):
        S.apply_update(st, {"round": {"round_type": "issue"}}, params)  # question 없음
    S.apply_update(st, dict(F1_BASE, round={"round_type": "round0", "question": "q", "answer": "a"}), params)
    assert st["round0_done"] and len(st["rounds"]) == 1


def test_resume_detects_changes(home, case, params):
    c = case(F1)
    path, st = make_state(c)
    assert S.check_changes(P.load_json(path), params) == {"memo_changed": False, "attachments_changed": [], "params_changed": False}
    with open(os.path.join(c, "사건메모.md"), "a", encoding="utf-8") as f:
        f.write("\n- 다른 접점에서 추가\n")
    with open(os.path.join(c, "피고_준비서면_요지.md"), "a", encoding="utf-8") as f:
        f.write("추가")
    ch = S.check_changes(P.load_json(path), params)
    assert ch["memo_changed"] and ch["attachments_changed"] == ["피고_준비서면_요지.md"]


def test_own_outputs_not_attachments(home, case, params):
    c = case(F1)
    path, _ = make_state(c)
    open(os.path.join(c, "260915_대여금_준비서면_v1.docx"), "wb").write(b"x")
    open(os.path.join(c, "내부_260915_대여금_준비서면_v1_의도대응표.docx"), "wb").write(b"x")
    assert S.check_changes(P.load_json(path), params)["attachments_changed"] == []


def test_purge(home, case):
    c = case(F1)
    path, _ = make_state(c)
    S.main(["purge", c])
    assert not os.path.exists(os.path.dirname(path))
    assert os.path.exists(os.path.join(c, "사건메모.md"))


# ── 사건메모 읽기 ──────────────────────────────────────────────
def test_read_case_f1():
    r = M.read_case(F1)
    assert r["connected"] and r["side_guess"] == "원고" and r["claim_amount_guess"] == 50000000
    assert r["claim_interest_guess"] is True
    assert [i["id"] for i in r["issues"]] == [1, 2]
    assert r["schedule"] == {"due_date": "2026-10-13", "next_hearing": "2026-09-22"}


def test_read_case_f2_f3():
    r = M.read_case(F2)
    assert r["side_guess"] == "피고" and r["schedule"]["due_date"] == "2026-10-20"
    assert M.read_case(F3) == {"connected": False, "path": None}


@pytest.mark.parametrize("v,want", [("홍길동(원고)", "원고"), ("김대출(피고)", "피고"), ("정대표(투자자·원고/고소인)", None),
                                    ("김영수(피고인)", None), ("최민준(상속인)", None), (None, None)])
def test_side_from_client(v, want):
    assert M.side_from_client(v) == want


@pytest.mark.parametrize("title", ["진행 경과", "진행경과", "5. 진행 경과 (최신이 위)"])
def test_progress_aliases(title):
    md = "# x\n\n## %s\n\n- 2026-01-01: 옛 줄\n\n## To-Do\n- [ ] a\n" % title
    new = M.apply_progress(md, "새 줄", "2026-09-15")
    assert new.index("- 2026-09-15: 새 줄") < new.index("- 2026-01-01: 옛 줄")
    assert "- 2026-01-01: 옛 줄" in new


@pytest.mark.parametrize("title", ["To-Do", "TODO", "할 일", "할일"])
def test_todo_aliases(title):
    md = "## %s\n- [ ] a\n\n## 참고사항\n- b\n" % title
    new = M.apply_todo(md, "새 할 일")
    assert new.index("- [ ] 새 할 일") < new.index("## 참고사항")


def test_missing_sections_created_and_crlf_kept():
    md = "# 메모\r\n\r\n## 기본정보\r\n- 의뢰인: 갑(원고)\r\n"
    new = M.build(md, ["의도 확정"], ["할 일"], "2026-09-15")
    assert "## 진행 경과 (최신이 위)\r\n- 2026-09-15: 의도 확정\r\n" in new
    assert "## To-Do\r\n- [ ] 할 일\r\n" in new
    assert "\n" not in new.replace("\r\n", "")


def test_unknown_sections_preserved():
    md = "## 기본정보\n- a: b\n\n## 완료\n- [x] 끝\n\n## 사용자정의\n내용\n\n## 진행 경과\n- 2026-01-01: x\n"
    new = M.apply_progress(md, "y", "2026-09-15")
    assert "## 완료\n- [x] 끝\n" in new and "## 사용자정의\n내용\n" in new


# ── 미리보기·확인 토큰·사본 ─────────────────────────────────────
def _prep(home, case):
    c = case(F1)
    path, _ = make_state(c, **F1_BASE)
    return c, path


def test_preview_apply_with_token(home, case):
    c, path = _prep(home, case)
    before = set(os.listdir(c))
    pv = M.preview(path, ["준비서면 의도 확정 — 주: 조정·화해 유도"], ["(선택) 청구취지를 4,000만원으로 감축"])
    assert "+- 2026-09-15: 준비서면 의도 확정" in pv["diff"]
    res = M.apply(path, pv["token"])
    md = open(os.path.join(c, "사건메모.md"), encoding="utf-8").read()
    assert "- 2026-09-15: 준비서면 의도 확정 — 주: 조정·화해 유도\n- 2026-09-13: 소장 접수" in md
    assert "- [ ] (선택) 청구취지를 4,000만원으로 감축" in md
    assert set(os.listdir(c)) == before  # 사건 폴더에 사본·임시 파일 없음
    assert os.path.dirname(res["backup"]) == os.path.join(os.path.dirname(path), "backups")
    st = P.load_json(path)
    assert st["memo"]["sha256"] == P.sha256_file(os.path.join(c, "사건메모.md"))  # 자기 쓰기 뒤 해시 갱신
    assert S.check_changes(st, P.load_params())["memo_changed"] is False


def test_token_mismatch_or_missing_refused(home, case):
    c, path = _prep(home, case)
    pv = M.preview(path, ["x"], [])
    with pytest.raises(P.BriefError, match="확인 토큰"):
        M.apply(path, "0" * 64)
    with pytest.raises(P.BriefError, match="확인 토큰"):
        M.apply(path, "")
    assert M.apply(path, pv["token"])["written"]


def test_apply_without_preview_refused(home, case):
    c, path = _prep(home, case)
    with pytest.raises(P.BriefError, match="preview"):
        M.apply(path, "x")


def test_changed_after_preview_refused(home, case):
    c, path = _prep(home, case)
    pv = M.preview(path, ["x"], [])
    with open(os.path.join(c, "사건메모.md"), "a", encoding="utf-8") as f:
        f.write("- 다른 곳 수정\n")
    with pytest.raises(M.MemoConflict):
        M.apply(path, pv["token"])


def test_changed_after_read_refused(home, case):
    c, path = _prep(home, case)
    with open(os.path.join(c, "사건메모.md"), "a", encoding="utf-8") as f:
        f.write("- 다른 곳 수정\n")
    with pytest.raises(M.MemoConflict):
        M.preview(path, ["x"], [])


def test_auto_confirm_not_in_runtime_cli():
    src = open(os.path.join(os.path.dirname(M.__file__), "memo.py"), encoding="utf-8").read()
    assert "--auto-confirm" not in src
    with pytest.raises(SystemExit):
        M.main(["apply", "s.json"])  # --confirm 필수


def test_no_memo_path(home, case):
    c = case(F3)
    path, _ = make_state(c)
    with pytest.raises(P.BriefError, match="사건메모"):
        M.preview(path, ["x"], [])


# ── casedb 계약(하네스와 바이트 단위로 같은 결과) ───────────────────
def _tree_hash(root):
    h = hashlib.sha256()
    for r, ds, fs in sorted(os.walk(root)):
        ds.sort()
        for f in sorted(fs):
            p = os.path.join(r, f)
            h.update(p.encode("utf-8"))
            h.update(open(p, "rb").read())
    return h.hexdigest()


def _find(root, rel_parts):
    for r, ds, fs in os.walk(root):
        for f in fs:
            full = unicodedata.normalize("NFC", os.path.join(r, f))
            if all(p in full for p in rel_parts):
                return os.path.join(r, f)
    return None


@pytest.mark.skipif(not os.path.isdir(DEMO), reason="하네스 데모 경로 없음")
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_casedb_contract(tmp_path, monkeypatch, newline):
    demo_hash = _tree_hash(DEMO)
    harness = tmp_path / "harness" / ".claude"
    for sub, name in (("case_manager", "casedb.py"), ("daily_check", "scan_cases.py")):
        src = _find(os.path.join(DEMO, ".claude"), [sub, name])
        (harness / sub).mkdir(parents=True)
        shutil.copyfile(src, harness / sub / name)
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    monkeypatch.syspath_prepend(str(harness / "daily_check"))
    spec = importlib.util.spec_from_file_location("casedb_copy", str(harness / "case_manager" / "casedb.py"))
    casedb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(casedb)
    root = tmp_path / "root"
    (root / "case").mkdir(parents=True)
    monkeypatch.setattr(casedb, "ROOT", str(root))
    monkeypatch.setattr(casedb, "BACKUP_DIR", str(tmp_path / "cb_backups"))
    casedb._SEEN_MTIME.clear()
    original = open(os.path.join(F1, "사건메모.md"), encoding="utf-8").read().replace("\n", newline)
    for variant, text in (("full", original),
                          ("noprog", original.split("## 진행 경과")[0]),
                          ("notodo", original.split("## To-Do")[0])):
        memo = root / "case" / ("%s.md" % variant)
        with open(memo, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        casedb.append_progress("case/%s.md" % variant, "준비서면 의도  확정 — 주: S", when="2026-09-15")
        casedb.add_todo("case/%s.md" % variant, "(선택) 청구취지를 4,000만원으로   감축")
        theirs = open(memo, "rb").read()
        ours = M.build(text, ["준비서면 의도  확정 — 주: S"], ["(선택) 청구취지를 4,000만원으로   감축"], "2026-09-15")
        assert ours.encode("utf-8") == theirs, variant
    assert _tree_hash(DEMO) == demo_hash  # 원본 데모 트리(__pycache__ 포함) 불변
