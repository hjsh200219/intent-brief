import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skills", "intent-brief", "scripts")
FIXTURES = os.path.join(ROOT, "tests", "fixtures")
RECORDED = os.path.join(ROOT, "tests", "recorded")
sys.path.insert(0, SCRIPTS)
sys.dont_write_bytecode = True

F1 = os.path.join(FIXTURES, "F1", "260901_대여금 청구(홍길동)")
F2 = os.path.join(FIXTURES, "F2", "260915_대여금(김대출) 피고측")
F3 = os.path.join(FIXTURES, "F3", "260901_대여금 청구(홍길동) 메모없음")


@pytest.fixture(autouse=True)
def _no_real_casesearch(monkeypatch):
    """테스트가 이 PC 에 설치된 실제 case-search(빅케이스 로그인)를 부르지 않게 — 필요한 테스트만 지운다."""
    monkeypatch.setenv("INTENT_BRIEF_NO_CASESEARCH", "1")


@pytest.fixture
def home(tmp_path, monkeypatch):
    """작업 폴더를 임시 HOME 으로 — 런타임 기본 경로 로직을 그대로 쓴다."""
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    monkeypatch.setenv("LOCALAPPDATA", str(h / "AppData" / "Local"))
    monkeypatch.setenv("INTENT_BRIEF_TODAY", "2026-09-15")
    return h


@pytest.fixture
def case(tmp_path):
    """픽스처 사건 폴더를 임시로 복사(원본 픽스처는 바꾸지 않는다)."""
    def _copy(src):
        dst = tmp_path / "cases" / os.path.basename(src)
        shutil.copytree(src, dst)
        return str(dst)
    return _copy


@pytest.fixture
def params():
    import _paths as P
    return P.load_params()


@pytest.fixture
def phrases():
    import _paths as P
    return P.load_phrases()


def make_state(case_dir, brief="준비서면", **kw):
    """상태를 만들고 kw 를 apply — 테스트 도우미."""
    import _paths as P
    import state as S
    path = S.state_path(case_dir, brief)
    st = S.new_state(case_dir, brief, P.load_params())
    if kw:
        S.apply_update(st, kw, P.load_params())
    S.save(path, st)
    return path, st


F1_BASE = {"side": "원고", "claim_amount": 50000000,
           "issues": [{"id": 1, "title": "금전소비대차의 성립"}, {"id": 2, "title": "변제 항변"}],
           "procedure": {"due_date": "2026-10-13", "next_hearing": "2026-09-22"}}
