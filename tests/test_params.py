import ast
import importlib.util
import itertools
import os
import re
import sys
import sysconfig

from conftest import SCRIPTS, ROOT

KEYS = ["W", "M", "S", "P", "R", "A", "C"]
PRIMARIES = ["W", "M", "S", "P", "R", "A"]


def test_intents_schema(params):
    assert list(params["intents"]) == KEYS
    assert params["intents"]["C"]["primary_allowed"] is False
    assert all(params["intents"][k]["primary_allowed"] for k in PRIMARIES)
    assert {v["layer"] for v in params["intents"].values()} <= {"goal", "tactic", "framing", "audience"}


def test_defaults_cover_all_intent_side(params):
    want = {"%s|%s" % (k, s) for k in KEYS for s in params["sides"]}
    assert set(params["defaults"]) == want  # 7 × 2 = 14
    assert params["defaults"]["C|원고"] is None and params["defaults"]["C|피고"] is None
    assert set(params["addenda"]) == want


def test_section_ids_in_vocabulary(params):
    vocab = set(params["sections"])
    assert set(params["section_order"]) == vocab
    for key, d in params["defaults"].items():
        if d is None:
            continue
        for s in d["must_include"] + d["must_omit"]:
            assert s in vocab, (key, s)
    for bt in params["brief_types"].values():
        assert set(bt["fixed_sections"]) <= vocab


def test_section_basis_covers_secondary_sections(params):
    for key, d in params["defaults"].items():
        if d is None:
            continue
        side = key.split("|")[1]
        for s in d["must_include"]:
            assert ("%s@%s" % (s, side)) in params["section_basis"] or s in params["section_basis"], (key, s)


def test_legal_basis_present(params):
    """PM6 — 결론부가 있는 행마다 법적 근거가 비어 있지 않다."""
    for key, d in params["defaults"].items():
        if d is None:
            continue
        assert d["conclusion_template"]
        assert d["legal_basis"], key
        for b in d["legal_basis"]:
            assert b["kind"] in ("조문", "판례", "해석")


def test_conclusion_templates_use_placeholders(params):
    """원고 결론 템플릿에 「인용」 리터럴 없음(자리표시자만), 피고 W·S·R 은 {relief_defendant}, M·A 피고만 리터럴."""
    for key, d in params["defaults"].items():
        if d is None:
            continue
        intent, side = key.split("|")
        t = d["conclusion_template"]
        if side == "원고" and intent not in ("P",):
            assert "{relief_plaintiff}" in t, key
            assert "인용" not in t.replace("{relief_plaintiff}", ""), key
        if side == "피고" and intent in ("W", "S", "R"):
            assert "{relief_defendant}" in t, key
        assert "예비적 판결" not in t


def test_conflict_coverage_36_pairs(params):
    """주 6 × 부 6(자기 제외, C 포함) = 36 순서쌍 — 충돌표 등재 또는 합성 가능(같은 goal 이 아님)."""
    ints = params["intents"]
    n = 0
    for p in PRIMARIES:
        for s in KEYS:
            if s == p:
                continue
            n += 1
            pair = "%s+%s" % (p, s)
            both_goal = ints[p]["layer"] == "goal" and ints[s]["layer"] == "goal"
            assert pair in params["conflicts"] or not both_goal, pair
    assert n == 36


def test_intents_md_matches_json(params):
    md = open(os.path.join(ROOT, "skills", "intent-brief", "references", "intents.md"), encoding="utf-8").read()
    rows = re.findall(r"^\|\s*([A-Z])\s*\|\s*([^|]+?)\s*\|", md, re.M)
    assert [(k, params["intents"][k]["name"]) for k in KEYS] == [(k, v) for k, v in rows]


def test_phrases_tags(phrases):
    for k in ("claim_reduction_optional", "claim_change_required", "unverified", "search_limit", "outage", "format_changed", "arg_error"):
        assert k in phrases["tag"]
    assert "예비적" not in phrases["tag"]["claim_reduction_optional"]
    assert "{remaining}" in phrases["tag"]["claim_reduction_optional"]


def test_runtime_scripts_stdlib_only():
    """런타임 스크립트는 표준 라이브러리와 서로만 import 한다(받는 PC 에 설치 요구 없음)."""
    local = {os.path.splitext(n)[0] for n in os.listdir(SCRIPTS) if n.endswith(".py")}
    std_root = os.path.realpath(sysconfig.get_paths()["stdlib"])

    def is_std(m):
        if hasattr(sys, "stdlib_module_names"):  # 3.10+
            return m in sys.stdlib_module_names
        if m in sys.builtin_module_names:  # 3.9 — 설치 위치로 판정
            return True
        spec = importlib.util.find_spec(m)
        origin = os.path.realpath(spec.origin) if spec and spec.origin else ""
        return origin.startswith(std_root) and "site-packages" not in origin

    for n in os.listdir(SCRIPTS):
        if not n.endswith(".py"):
            continue
        tree = ast.parse(open(os.path.join(SCRIPTS, n), encoding="utf-8").read())
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module.split(".")[0]]
            for m in mods:
                assert m in local or is_std(m), (n, m)


def test_python39_syntax():
    """받는 PC 최저 3.9 — 3.10+ 문법(match, X | Y 타입 등)을 쓰지 않는다."""
    for n in os.listdir(SCRIPTS):
        if n.endswith(".py"):
            src = open(os.path.join(SCRIPTS, n), encoding="utf-8").read()
            ast.parse(src, feature_version=(3, 9))


# ARCHITECTURE.md 「L3 안의 방향」 — 함수 안 지연 import 까지 본다.
ALLOWED_LOCAL = {
    "_paths": set(),
    "state": {"_paths"},
    "score": {"_paths"},
    "cite_check": {"_paths"},
    "intent": {"_paths", "state"},
    "memo": {"_paths", "state"},
    "check_draft": {"_paths", "state"},
    "render_docx": {"_paths", "state", "check_draft"},
}


def test_runtime_import_direction():
    local = {os.path.splitext(n)[0] for n in os.listdir(SCRIPTS) if n.endswith(".py")}
    assert local == set(ALLOWED_LOCAL), "새 스크립트는 ARCHITECTURE.md 와 ALLOWED_LOCAL 에 방향을 적는다"
    for mod in sorted(local):
        tree = ast.parse(open(os.path.join(SCRIPTS, mod + ".py"), encoding="utf-8").read())
        used = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                used |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                used.add(node.module.split(".")[0])
        assert used & local <= ALLOWED_LOCAL[mod], (mod, sorted(used & local - ALLOWED_LOCAL[mod]))
