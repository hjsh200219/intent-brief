"""개발 전용 e2e — 같은 사건·다른 의도 초안을 여러 번 만들고 E1–E8 을 판정한다(PRD §5.3).

사용:
  e2e.py run   --out <폴더> [--runs 3] [--jobs 4]     replay.py 를 병렬로 돌린다
  e2e.py judge --out <폴더> [--no-jev]               E1–E8 판정표(JSON)
"""
import argparse
import concurrent.futures as cf
import json
import os
import re
import statistics
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "skills", "intent-brief", "scripts"))
import check_draft as CD  # noqa: E402
import _paths as P  # noqa: E402

FX = os.path.join(REPO, "tests", "fixtures")
ANS = os.path.join(REPO, "tests", "e2e")
COMBOS = {
    "F1A": ("F1/260901_대여금 청구(홍길동)", "answers_F1A.json", "준비서면", "W"),
    "F1B": ("F1/260901_대여금 청구(홍길동)", "answers_F1B.json", "준비서면", "S"),
    "F2A": ("F2/260915_대여금(김대출) 피고측", "answers_F2A.json", "답변서", "W"),
    "F2B": ("F2/260915_대여금(김대출) 피고측", "answers_F2B.json", "답변서", "M"),
    "F3": ("F3/260901_대여금 청구(홍길동) 메모없음", "answers_F1B.json", "준비서면", "S"),
}


def run_one(out, combo, i):
    fx, ans, brief, _ = COMBOS[combo]
    rd = os.path.join(out, "%s_r%d" % (combo, i))
    if os.path.exists(os.path.join(rd, "report.json")):
        return combo, i, json.load(open(os.path.join(rd, "report.json"), encoding="utf-8")).get("ok")
    p = subprocess.run([sys.executable, "-I", os.path.join(REPO, "dev", "replay.py"), os.path.join(FX, fx), os.path.join(ANS, ans),
                        "--run-dir", rd, "--brief", brief, "--name", "대여금"], capture_output=True)
    return combo, i, p.returncode == 0


def cmd_run(a):
    os.makedirs(a.out, exist_ok=True)
    jobs = [(c, i) for c in (a.only or list(COMBOS)) for i in range(1, a.runs + 1)]
    with cf.ThreadPoolExecutor(max_workers=a.jobs) as ex:
        for combo, i, ok in ex.map(lambda x: run_one(a.out, *x), jobs):
            print("%s r%d %s" % (combo, i, "ok" if ok else "FAIL"), flush=True)


def load_run(rd):
    rep = json.load(open(os.path.join(rd, "report.json"), encoding="utf-8"))
    if not rep.get("ok"):
        return rep, None, None, None
    md = P.read_text(rep["draft"])
    design = P.load_json(rep["design"])
    parsed = CD.parse_draft(md)
    return rep, md, design, parsed


def sec(parsed, sid):
    return next((s for s in parsed["sections"] if s["id"] == sid), None)


def issue_text(parsed, iid):
    return "\n".join(i["body"] for s in parsed["sections"] for i in s["issues"] if i["id"] == iid)


def body_only(md):
    """블라인드 판별용 — 앵커·front matter·결론·태그 제거(의도 이름이 드러나는 구조 표지를 지운다)."""
    _, b = CD.split_front(md.replace("\r\n", "\n"))
    b = re.sub(r"^##\s+\[sec:[^\]]+\]\s*", "## ", b, flags=re.M)
    b = re.sub(r"^###\s+\[issue:\d+\]\s*", "### ", b, flags=re.M)
    return b


def judge_run(combo, parsed, md, design, ph):
    deny, admit = ph["stance_markers"]["deny"], ph["stance_markers"]["admit"]
    cnt = lambda t, ws: sum(t.count(w) for w in ws)  # noqa: E731
    concl = (sec(parsed, "sec.conclusion") or {}).get("body", "")
    has = lambda sid: sec(parsed, sid) is not None  # noqa: E731
    body = "\n".join(s["body"] for s in parsed["sections"] if s["id"] not in CD.NON_BODY)
    n_assert = cnt(body, ph["strength_markers"]["assertive"])
    r = {"chars": len(re.sub(r"\s+", "", body)), "assertive": n_assert}
    if combo == "F1A":
        t = issue_text(parsed, 2)
        r.update(E1=not has("sec.settle_opinion"), E2=cnt(t, deny) >= 1 and cnt(t, admit) == 0, E3=n_assert >= 3,
                 E4=not has("sec.alt_claim"), E5=all(x in concl for x in ("5,000만원", "전부", "인용")))
    elif combo in ("F1B", "F3"):
        t = issue_text(parsed, 2)
        r.update(E1=has("sec.settle_opinion"), E2=cnt(t, admit) >= 1 and "1,000만" in t, E3=n_assert <= 1,
                 E4=not has("sec.alt_claim"),
                 E5=all(x in concl for x in ("조정", "조정이 성립하지 않을 경우", "1,000만원을 공제한 나머지 4,000만원"))
                 and not any(x in concl for x in ("전부", "모두", "예비적")))
    elif combo == "F2A":
        t = issue_text(parsed, 1)
        r.update(E1=not has("sec.settle_opinion"), E2=cnt(t, deny) >= 1 and cnt(t, admit) == 0, E3=n_assert >= 3,
                 E4=not has("sec.alt_claim"), E5="원고의 청구를 기각" in concl)
    elif combo == "F2B":
        t = issue_text(parsed, 1)
        alt = (sec(parsed, "sec.alt_claim") or {}).get("body", "")
        r.update(E1=True, E2=cnt(t, admit) >= 1, E3=n_assert <= 1, E4=bool(alt) and "공제" in alt,
                 E5=all(x in concl for x in ("주위적", "청구를 기각", "예비적", "일부 기각")))
    return r


def jev_blind(texts):
    sys.path.insert(0, os.environ.get("JEV_DIR") or os.path.expanduser("~/workspace/shared"))  # Jev 클라이언트 jev.py 위치
    import jev
    crit = {"W": "전부 승소 — 상대 주장 전부를 다투고 청구 전부 인용·전부 기각을 구한다",
            "M": "손해 최소화 — 일부를 인정하고 공제·감액으로 확실한 부분을 지킨다",
            "S": "조정·화해 유도 — 판결보다 조정·화해로 끝내도록 재판부·상대방을 움직인다",
            "P": "상대 입장 고정·증거 제출 압박 — 석명 요청·문서제출신청으로 상대가 주장을 특정하고 자료를 내게 한다",
            "R": "쟁점 재구성 — 사건의 핵심 틀을 다시 짜서 재판부가 보는 쟁점을 바꾼다",
            "A": "상소 대비 기록 — 결과와 무관하게 주장·증거신청·이의를 빠짐없이 기록에 남긴다"}
    qs = {"q%d" % i: jev.choice("이 민사 서면 본문을 쓴 변호사의 주된 의도(서면 전체가 가장 강하게 노리는 결과) 하나를 고르라.", crit)
          for i in range(len(texts))}
    out = {}
    for i, t in enumerate(texts):
        ans = jev.ask({"서면 본문": t}, {"q%d" % i: qs["q%d" % i]})
        out[i] = jev.choice_of(ans, "q%d" % i)
    return out


def cmd_judge(a):
    ph = P.load_phrases()
    table, blind_items = {}, []
    for combo in COMBOS:
        runs = sorted(d for d in os.listdir(a.out) if d.startswith(combo + "_r"))
        table[combo] = []
        for d in runs:
            rep, md, design, parsed = load_run(os.path.join(a.out, d))
            if md is None:
                table[combo].append({"run": d, "error": rep.get("error")})
                continue
            st = P.load_json(rep["state"])
            j = judge_run(combo, parsed, md, design, ph)
            j.update(run=d, first=st["compliance"].get("first"), final=st["compliance"].get("final"),
                     cite=P.load_json(os.path.join(os.path.dirname(rep["state"]), "cite_results.json"))["summary"],
                     check_tags=md.count("[확인 필요"), memo_writes=len(st.get("memo_writes") or []))
            if combo == "F1B":
                memo = P.read_text(os.path.join(rep["case_dir"], "사건메모.md"))
                j["E8"] = bool(re.search(r"- \[ \] \(선택\) 청구취지를 4,000만원으로 감축", memo))
            if combo == "F3":
                names = sorted(os.listdir(rep["case_dir"]))
                j["case_files"] = names
                j["no_extra_files"] = sorted(set(names) - {"피고_준비서면_요지.md", "사건_개요.txt"}) == sorted(
                    os.path.basename(p) for p in rep["outputs"].values())
            table[combo].append(j)
            if combo in ("F1A", "F1B", "F2A", "F2B"):
                blind_items.append((combo, d, COMBOS[combo][3], body_only(md)))
    summary = {}
    for combo, rows in table.items():
        ok_rows = [r for r in rows if "error" not in r]
        s = {}
        for e in ("E1", "E2", "E3", "E4", "E5", "E8"):
            vals = [r[e] for r in ok_rows if e in r]
            if vals:
                need = 2 if e == "E3" else len(vals)
                s[e] = "%d/%d %s" % (sum(vals), len(vals), "통과" if sum(vals) >= need and len(vals) == len(rows) else "실패")
        s["chars_median"] = statistics.median([r["chars"] for r in ok_rows]) if ok_rows else None
        summary[combo] = s
    for f in ("F1", "F2"):
        ma, mb = summary.get(f + "A", {}).get("chars_median"), summary.get(f + "B", {}).get("chars_median")
        if ma and mb:
            summary[f + "_E6"] = "A/B = %.2f %s" % (ma / mb, ("통과" if ma / mb >= 1.3 else "실패") if f == "F1" else "(기록만)")
    if not a.no_jev and blind_items:
        res = jev_blind([b[3] for b in blind_items])
        blind = [{"combo": c, "run": d, "truth": t, "pred": res[i][0], "conf": round(res[i][1], 2)} for i, (c, d, t, _) in enumerate(blind_items)]
        for f in ("F1", "F2"):
            rows = [b for b in blind if b["combo"].startswith(f)]
            n = sum(1 for b in rows if b["pred"] == b["truth"])
            summary[f + "_E7"] = "%d/%d %s" % (n, len(rows), "통과" if n >= 5 else "실패")
        summary["E7_detail"] = blind
    out = {"summary": summary, "runs": table}
    json.dump(out, open(os.path.join(a.out, "judge.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("run"); s.add_argument("--out", required=True); s.add_argument("--runs", type=int, default=3); s.add_argument("--jobs", type=int, default=4); s.add_argument("--only", nargs="*")
    s = sub.add_parser("judge"); s.add_argument("--out", required=True); s.add_argument("--no-jev", action="store_true")
    a = ap.parse_args()
    {"run": cmd_run, "judge": cmd_judge}[a.cmd](a)


if __name__ == "__main__":
    main()
