"""사건메모.md 연결 — 읽기(기본정보·쟁점·일정), diff 미리보기, 확인 토큰으로만 반영.

하네스(업무관리시스템) casedb.py 의 섹션 별칭·append_progress·add_todo 규약과 바이트 단위로 같게 쓴다.
쓰기 전 작업 폴더 backups/ 에 사본, 읽은 뒤 바뀐 파일은 덮지 않는다(sha256 비교).

사용:
  memo.py read    <사건폴더>
  memo.py preview <state.json> [--progress "문장"]... [--todo "문장"]...
  memo.py apply   <state.json> --confirm <preview 가 준 sha256>
"""
import argparse
import datetime
import difflib
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths as P  # noqa: E402

# casedb.py 29–34행 별칭과 같다
PROGRESS_TITLES = ("진행 경과", "진행경과")
TODO_TITLES = ("To-Do", "TODO", "할 일", "할일")
SCHEDULE_TITLES = ("주요 일정", "주요일정", "일정")
BASIC_TITLES = ("기본정보", "기본 정보")
ISSUE_TITLES = ("쟁점",)
REFERENCE_TITLES = ("참고사항", "참고 사항")
ALL_TITLES = PROGRESS_TITLES + TODO_TITLES + SCHEDULE_TITLES + BASIC_TITLES + ISSUE_TITLES + REFERENCE_TITLES

_NUM_PREFIX = re.compile(r"^\s*\d+[.)]\s*")


class MemoConflict(P.BriefError):
    pass


def find_section(md, titles):
    """casedb.find_section 과 같은 규칙 — (head_start, body_start, body_end) 또는 None."""
    for m in re.finditer(r"^(#{2,4})[ \t]*(.+?)[ \t]*$", md, re.M):
        level = len(m.group(1))
        title = _NUM_PREFIX.sub("", m.group(2).strip())
        if any(title.startswith(t) for t in titles):
            body_start = m.end()
            stop = re.compile(r"^#{1,%d}[ \t]+" % level, re.M)
            nxt = stop.search(md[body_start:])
            body_end = body_start + nxt.start() if nxt else len(md)
            return m.start(), body_start, body_end
    return None


def section_text(md, titles):
    loc = find_section(md, titles)
    return md[loc[1]:loc[2]] if loc else ""


def newline_of(text):
    return "\r\n" if "\r\n" in text else "\n"


def is_connected(md):
    """하네스 사건메모 형식인가 — 별칭 섹션 중 하나라도 있으면 연결 모드."""
    return any(find_section(md, (t,)) for t in ALL_TITLES)


def parse_basic(md):
    out = {}
    for ln in section_text(md, BASIC_TITLES).splitlines():
        s = re.sub(r"\*\*", "", ln.strip().lstrip("-* ").strip())
        if s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if len(cells) >= 2 and not all(set(c) <= set("-: ") for c in cells):
                out[cells[0]] = cells[1]
            continue
        if ":" in s:
            k, v = s.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def side_from_client(value):
    """「홍길동(원고)」 → 원고. 복합(「투자자·원고/고소인」)·없음이면 None — 묻는다."""
    if not value:
        return None
    m = re.findall(r"\(([^)]*)\)", value)
    roles = m[-1] if m else ""
    has_p, has_d = "원고" in roles, "피고" in roles and "피고인" not in roles
    if re.search(r"[·/,]", roles) or (has_p and has_d):
        return None
    if has_p:
        return "원고"
    if has_d:
        return "피고"
    return None


def parse_issues(md):
    out = []
    for ln in section_text(md, ISSUE_TITLES).splitlines():
        m = re.match(r"^\s*(?:(\d+)[.)]|[-*])\s*(.+?)\s*$", ln)
        if m and m.group(2):
            out.append({"id": int(m.group(1)) if m.group(1) else len(out) + 1, "title": m.group(2), "line": ln.strip()})
    return out


def parse_schedule(md):
    due, hearing = None, None
    for ln in section_text(md, SCHEDULE_TITLES).splitlines():
        m = re.search(r"(20\d{2})\s*[.\-]\s*(\d{1,2})\s*[.\-]\s*(\d{1,2})", ln)
        if not m:
            continue
        d = "%04d-%02d-%02d" % (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if re.search(r"기한|제출", ln) and not due:
            due = d
        elif re.search(r"기일", ln) and not hearing:
            hearing = d
    return {"due_date": due, "next_hearing": hearing}


def read_case(case_dir):
    path = P.find_memo(case_dir)
    if not path:
        return {"connected": False, "path": None}
    md = P.read_text(path)
    basic = parse_basic(md)
    client = basic.get("의뢰인")
    claim_line = basic.get("청구취지 요지") or basic.get("청구취지") or ""
    return {
        "connected": is_connected(md),
        "path": path,
        "sha256": P.sha256_bytes(md.encode("utf-8")),
        "basic": basic,
        "side_guess": side_from_client(client),
        "claim_amount_guess": P.parse_won(claim_line),
        "issues": parse_issues(md),
        "schedule": parse_schedule(md),
        "newline": "CRLF" if "\r\n" in md else "LF",
    }


# ── 쓰기(casedb append_progress·add_todo 와 같은 결과) ─────────────────
def apply_progress(md, text, when):
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        raise P.BriefError("내용이 비어 있습니다.")
    nl = newline_of(md)
    line = "- %s: %s" % (when, text)
    loc = find_section(md, PROGRESS_TITLES)
    if loc is None:
        return md.rstrip() + nl + nl + "## 진행 경과 (최신이 위)" + nl + line + nl
    _, body_start, _ = loc
    rest = md[body_start:]
    lead = re.match(r"(?:\r?\n)+", rest)
    off = lead.end() if lead else 0
    return md[:body_start + off] + line + nl + md[body_start + off:]


def apply_todo(md, text):
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        raise P.BriefError("내용이 비어 있습니다.")
    nl = newline_of(md)
    line = "- [ ] %s" % text
    loc = find_section(md, TODO_TITLES)
    if loc is None:
        return md.rstrip() + nl + nl + "## To-Do" + nl + line + nl
    _, body_start, body_end = loc
    seg = md[body_start:body_end]
    stripped = seg.rstrip()
    insert_at = body_start + (len(stripped) if stripped else 0)
    return md[:insert_at] + nl + line + md[insert_at:]


def build(md, progress, todos, when):
    new = md
    for p in progress:
        new = apply_progress(new, p, when)
    for t in todos:
        new = apply_todo(new, t)
    return new


def make_diff(old, new, name):
    d = "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), "a/" + name, "b/" + name, n=1))
    return d


def token_of(diff, base_sha):
    return P.sha256_bytes((base_sha + "\n" + diff).encode("utf-8"))


def _pending_path(state_path):
    return os.path.join(os.path.dirname(state_path), "memo_pending.json")


def preview(state_path, progress, todos):
    st = P.load_json(state_path)
    path = P.find_memo(st["case_dir"])
    if not path:
        raise P.BriefError("사건메모.md 가 없습니다 — 사건메모 없는 경로에서는 기록하지 않습니다")
    md = P.read_text(path)
    base_sha = P.sha256_bytes(md.encode("utf-8"))
    if st["memo"]["sha256"] and base_sha != st["memo"]["sha256"]:
        raise MemoConflict("사건메모가 읽은 뒤 다른 곳에서 수정되었습니다 — 다시 읽고 Round 0 차이부터 확인하십시오")
    when = P.today().isoformat()
    new = build(md, progress, todos, when)
    diff = make_diff(md, new, P.MEMO_NAME)
    tok = token_of(diff, base_sha)
    P.atomic_write_json(_pending_path(state_path), {"base_sha": base_sha, "progress": progress, "todos": todos,
                                                    "when": when, "token": tok})
    return {"diff": diff, "token": tok}


def apply(state_path, confirm, auto_confirm=False):
    """확인 토큰이 맞을 때만 쓴다. auto_confirm 은 dev/replay.py 전용 — 런타임 CLI 에는 없다."""
    import state as S
    st = P.load_json(state_path)
    pend_path = _pending_path(state_path)
    if not os.path.exists(pend_path):
        raise P.BriefError("먼저 memo.py preview 로 diff 를 보여 주어야 합니다")
    pend = P.load_json(pend_path)
    path = P.find_memo(st["case_dir"])
    md = P.read_text(path)
    base_sha = P.sha256_bytes(md.encode("utf-8"))
    if base_sha != pend["base_sha"]:
        raise MemoConflict("미리보기 뒤 사건메모가 바뀌었습니다 — 쓰지 않았습니다. 다시 미리보기 하십시오")
    new = build(md, pend["progress"], pend["todos"], pend["when"])
    tok = token_of(make_diff(md, new, P.MEMO_NAME), base_sha)
    if not auto_confirm and (not confirm or confirm != tok):
        raise P.BriefError("확인 토큰이 맞지 않습니다 — 보여 준 diff 와 다른 내용은 쓰지 않습니다")
    wd = os.path.dirname(state_path)
    bdir = os.path.join(wd, "backups")
    os.makedirs(bdir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S%f")[:-3]
    backup = os.path.join(bdir, "사건메모.%s.md" % stamp)
    shutil.copy2(path, backup)
    P.atomic_write_text(path, new)
    os.remove(pend_path)
    S.refresh_memo_hash(st)
    st.setdefault("memo_writes", []).append({"when": pend["when"], "progress": pend["progress"], "todos": pend["todos"],
                                             "backup": backup})
    S.save(state_path, st)
    return {"written": path, "backup": backup}


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("read"); s.add_argument("case_dir")
    s = sub.add_parser("preview"); s.add_argument("state")
    s.add_argument("--progress", action="append", default=[]); s.add_argument("--todo", action="append", default=[])
    s = sub.add_parser("apply"); s.add_argument("state"); s.add_argument("--confirm", required=True)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "read":
            return P.emit(dict(ok=True, **read_case(a.case_dir)))
        if a.cmd == "preview":
            return P.emit(dict(ok=True, **preview(a.state, a.progress, a.todo)))
        if a.cmd == "apply":
            return P.emit(dict(ok=True, **apply(a.state, a.confirm)))
    except P.BriefError as e:
        return P.fail(str(e))


if __name__ == "__main__":
    sys.exit(main())
