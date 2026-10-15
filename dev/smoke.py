"""개발 전용 실기 점검(Windows·macOS) — 표준 라이브러리만. 공개 전에 받는 PC 와 같은 환경에서 돌린다.

점검: Python 버전 · 한글 사건 경로 · CRLF 사건메모 · 작업 폴더 기본 경로(LOCALAPPDATA/HOME) · 인터뷰 상태·채점·해석 ·
확인 토큰 사건메모 쓰기(CRLF 보존·사본 위치) · 설계 준수 검사 · docx 생성 · 법제처 인용 대조 1건(LAW_API_OC 필요).

사용: python dev/smoke.py [--keep]
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "skills", "intent-brief", "scripts")
F1 = os.path.join(REPO, "tests", "fixtures", "F1", "260901_대여금 청구(홍길동)")
results = []


def check(name, ok, detail=""):
    results.append({"check": name, "ok": bool(ok), "detail": str(detail)[:300]})
    return ok


def run(env, name, *args):
    p = subprocess.run([sys.executable, os.path.join(SCRIPTS, name)] + list(args), env=env, capture_output=True)
    try:
        return p.returncode, json.loads(p.stdout.decode("utf-8"))
    except ValueError:
        return p.returncode, {"raw": p.stdout.decode("utf-8", "replace")[:300], "err": p.stderr.decode("utf-8", "replace")[-500:]}


def main():
    keep = "--keep" in sys.argv
    check("python>=3.9", sys.version_info >= (3, 9), sys.version.split()[0] + " " + sys.executable)
    tmp = tempfile.mkdtemp(prefix="intent-brief-smoke-")
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = ""  # 스크립트가 UTF-8 바이트로 직접 쓰는지 본다
    env["INTENT_BRIEF_TODAY"] = "2026-09-15"
    if os.name == "nt":
        env["LOCALAPPDATA"] = os.path.join(tmp, "LocalAppData")
        want_root = os.path.join(env["LOCALAPPDATA"], "intent-brief")
    else:
        env["HOME"] = os.path.join(tmp, "home")
        os.makedirs(env["HOME"])
        want_root = os.path.join(env["HOME"], ".intent-brief")
    case = os.path.join(tmp, "사건", "260901_대여금 청구(홍길동)")
    shutil.copytree(F1, case)
    memo = os.path.join(case, "사건메모.md")
    raw = open(memo, encoding="utf-8").read().replace("\r\n", "\n").replace("\n", "\r\n")
    open(memo, "w", encoding="utf-8", newline="").write(raw)
    before = sorted(os.listdir(case))

    rc, o = run(env, "state.py", "init", case, "--brief", "준비서면")
    check("state init", rc == 0 and o.get("ok"), o)
    state = o.get("state", "")
    check("작업 폴더 기본 경로", os.path.normcase(state).startswith(os.path.normcase(want_root)), state)
    rc, o = run(env, "memo.py", "read", case)
    check("사건메모 파싱(한글 경로·CRLF)", o.get("side_guess") == "원고" and o.get("claim_amount_guess") == 50000000
          and o.get("newline") == "CRLF", {k: o.get(k) for k in ("side_guess", "claim_amount_guess", "newline")})
    upd = {"side": "원고", "claim_amount": 50000000, "procedure": {"due_date": "2026-10-13", "next_hearing": "2026-09-22"},
           "issues": [{"id": 1, "title": "금전소비대차의 성립", "stance": "다툼", "evidence": {"mode": "제출", "items": ["갑 제1호증"]}},
                      {"id": 2, "title": "변제 항변", "stance": "일부 인정", "amount": 10000000, "evidence": {"mode": "유보"}}],
           "intent": {"primary": "S", "secondaries": ["M"], "success_sentence": "조정 회부", "concession": "4,000만원"},
           "flags": {"settle_will": True}, "round": {"round_type": "round0", "question": "smoke", "answer": "확인"}}
    rc, o = run(env, "state.py", "apply", state, "--json", json.dumps(upd, ensure_ascii=False))
    check("state apply(한글 JSON 인자)", rc == 0 and o.get("ok"), o)
    rc, o = run(env, "score.py", state)
    check("score 통과·다음=의도 유불리 검토", o.get("pass") and o.get("next", {}).get("round_type") == "intent_review", o.get("next"))
    rv = {"intent_review": {"verdict": "조건부", "gains": ["조정 종결"], "forgoes": ["smoke 놓치는 것"], "alternatives": [],
                            "decision": "진행"}, "round": {"round_type": "intent_review", "question": "smoke", "answer": "1"}}
    run(env, "state.py", "apply", state, "--json", json.dumps(rv, ensure_ascii=False))
    rc, o = run(env, "score.py", state)
    check("검토 뒤 다음=설계 확인", o.get("next", {}).get("round_type") == "design_confirm", o.get("next"))
    run(env, "state.py", "set-status", state, "confirming")
    rc, o = run(env, "intent.py", "resolve", state, "--write")
    design = o.get("design_path", "")
    concl = (o.get("design") or {}).get("conclusion", {}).get("text", "")
    check("resolve 결론 공제 문구", "인정한 1,000만원을 공제한 나머지 4,000만원을 인용" in concl, concl)
    rc, o = run(env, "memo.py", "preview", state, "--progress", "준비서면 의도 확정 — smoke", "--todo", "smoke 할 일")
    tok = o.get("token")
    rc2, o2 = run(env, "memo.py", "apply", state, "--confirm", "0" * 64)
    check("토큰 불일치 거부", rc2 != 0 and not o2.get("ok"), o2)
    rc, o = run(env, "memo.py", "apply", state, "--confirm", tok or "")
    new = open(memo, "rb").read().decode("utf-8")
    check("사건메모 쓰기·CRLF 보존", rc == 0 and "- 2026-09-15: 준비서면 의도 확정 — smoke\r\n" in new
          and "\n" not in new.replace("\r\n", ""), o)
    check("사본은 작업 폴더에만", os.path.normcase(o.get("backup", "")).startswith(os.path.normcase(want_root)), o.get("backup"))
    d = json.load(open(design, encoding="utf-8"))
    wd = os.path.dirname(state)
    draft = os.path.join(wd, "준비서면_draft.md")
    parts = ["## [sec:sec.header] 준비서면", "사건 2026가단512345 대여금"]
    for s in d["sections"][1:]:
        parts.append("## [sec:%s] %s" % (s["id"], s["title"]))
        if s["id"] == "sec.rebuttal_core":
            parts += ["### [issue:1] 성립", "증여 주장은 사실이 아닙니다. 원고는 이를 부인합니다.",
                      "### [issue:2] 변제", "원고는 1,000만원 변제 사실을 인정합니다. 민사소송법 제288조 참조."]
        elif s["id"] == "sec.conclusion":
            parts.append(d["conclusion"]["text"])
        else:
            parts.append("원고는 원만한 해결을 바랍니다. " * 40)
    open(draft, "w", encoding="utf-8", newline="").write("\r\n".join(parts) + "\r\n")
    rc, o = run(env, "check_draft.py", "check", draft, design, "--state", state, "--record", "first")
    check("설계 준수 검사(CRLF 초안)", rc == 0 and o.get("rate") == 1.0, o.get("failures"))
    rc, o = run(env, "cite_check.py", "run", draft, "--max-seconds", "120")
    if o.get("error") == "no_key":
        check("법제처 인용 대조(제288조)", False, "키 없음 — 환경변수 LAW_API_OC 로 법제처 OC 를 주고 다시 실행")
    else:
        check("법제처 인용 대조(제288조)", o.get("summary", {}).get("confirmed") == 1, o.get("summary") or o)
    run(env, "state.py", "set-status", state, "designed") if json.load(open(state, encoding="utf-8"))["status"] != "designed" else None
    rc, o = run(env, "render_docx.py", "all", state, "--name", "대여금")
    paths = (o.get("paths") or {})
    ok = rc == 0 and all(os.path.exists(p) for p in paths.values())
    for p in paths.values():
        try:
            zipfile.ZipFile(p).testzip()
        except Exception as e:
            ok = False
            paths["zip_error"] = str(e)
    check("docx 생성(한글 파일명)", ok, paths)
    after = sorted(os.listdir(case))
    extra = sorted(set(after) - set(before))
    check("사건 폴더 생성물 = 초안·대응표만", len(extra) == 2 and all(n.endswith(".docx") for n in extra), extra)
    out = {"ok": all(r["ok"] for r in results), "platform": sys.platform, "tmp": tmp, "results": results}
    sys.stdout.flush()
    sys.stdout.buffer.write((json.dumps(out, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    if not keep:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
