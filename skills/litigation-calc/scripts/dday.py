#!/usr/bin/env python3
"""기한·기일 D-day 점검 — 표준 라이브러리만, Python 3.9.

사건 출처: ① 등록한 사건 루트 폴더의 바로 아래 폴더(사건메모.md 가 있는 것) ② intent-brief 작업 폴더의 상태 파일(case_dir).
각 사건메모 「주요 일정」 절의 날짜 줄을 모아 오늘부터 N일(기본 14일) 안의 것을 알린다. 지운 줄(~~…~~)·완료 표시 줄은 뺀다.
항소·상고·항고·이의·추후보완·재심·제소·시효·제척·불변 이 들어간 줄은 불변기간·시효로 강조한다.

  scan [--days N]            JSON
  hook                       세션 시작 훅용 — 다가오는 것이 없으면 아무것도 출력하지 않는다. 어떤 오류에도 exit 0
  roots add|remove <폴더> · roots list
"""
import argparse
import glob
import json
import os
import re
import sys
import time
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "intent-brief", "scripts"))
import _paths as P  # noqa: E402
import memo as M  # noqa: E402
from deadline import IMMINENT_DAYS, WEEKDAYS  # noqa: E402

DATE = re.compile(r"(20\d{2})\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{1,2})")
CRITICAL = re.compile(r"항소|상고|항고|이의|추후보완|재심|제소|소\s*제기|시효|제척|불변")
# 완료 「표시」만 — 「미완료」·「완료 예정」 줄을 빼면 있는 기한을 숨기게 된다
DONE = re.compile(r"~~.+~~|\[[xX]\]|[(\[]\s*완료\s*[)\]]|(?<![미불])완료\s*$")
MAX_DIRS = 500
TIME_BUDGET = 4.0
MAX_LINES = 10


def config_path():
    return os.path.join(P.work_root(), "dday.json")


def _load():
    try:
        with open(config_path(), encoding="utf-8") as f:
            data = json.load(f)
        return {"roots": [r for r in data.get("roots", []) if isinstance(r, str)]}
    except (OSError, ValueError):
        return {"roots": []}


def _save(cfg):
    os.makedirs(P.work_root(), exist_ok=True)
    with open(config_path(), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)


def roots_add(folder):
    path = P.nfc(os.path.abspath(folder))
    if not os.path.isdir(path):
        raise ValueError("폴더가 없습니다: %s" % folder)
    cfg = _load()
    if path not in cfg["roots"]:
        cfg["roots"].append(path)
        _save(cfg)
    return {"ok": True, "roots": cfg["roots"]}


def roots_remove(folder):
    path = P.nfc(os.path.abspath(folder))
    cfg = _load()
    cfg["roots"] = [r for r in cfg["roots"] if r != path]
    _save(cfg)
    return {"ok": True, "roots": cfg["roots"]}


def roots_list():
    return {"ok": True, "roots": _load()["roots"]}


def case_dirs():
    seen, out, started = set(), [], time.time()

    def add(d):
        key = P.nfc(os.path.abspath(d))
        if key not in seen and P.find_memo(key):
            seen.add(key)
            out.append(key)

    for root in _load()["roots"]:
        try:
            names = sorted(os.listdir(root))[:MAX_DIRS]
        except OSError:
            continue
        add(root)
        for n in names:
            if time.time() - started > TIME_BUDGET:
                return out
            full = os.path.join(root, n)
            if os.path.isdir(full):
                add(full)
    for st in glob.glob(os.path.join(P.work_root(), "cases", "*", "*_state.json")):
        try:
            with open(st, encoding="utf-8") as f:
                d = json.load(f).get("case_dir")
        except (OSError, ValueError):
            continue
        if isinstance(d, str) and os.path.isdir(d):
            add(d)
    return out


def _kind(text):
    if re.search(r"기한|제출|마감", text):
        return "기한"
    if "기일" in text:
        return "기일"
    return "기타"


def schedule_items(case_dir, today):
    path = P.find_memo(case_dir)
    if not path:
        return []
    md = P.read_text(path)
    items = []
    for ln in M.section_text(md, M.SCHEDULE_TITLES).splitlines():
        m = DATE.search(ln)
        if not m or DONE.search(ln):
            continue
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue
        text = (ln[:m.start()] + ln[m.end():]).strip(" -*\t")
        text = re.sub(r"^\d{1,2}:\d{2}\s*", "", text).strip()
        items.append({"case": os.path.basename(case_dir.rstrip("\\/")), "case_dir": case_dir, "date": d.isoformat(),
                      "d_day": (d - today).days, "text": text, "kind": _kind(text), "critical": bool(CRITICAL.search(text))})
    return items


def scan(days=IMMINENT_DAYS, today=None):
    today = today or P.today()
    items = []
    for d in case_dirs():
        items += [i for i in schedule_items(d, today) if 0 <= i["d_day"] <= days]
    items.sort(key=lambda i: (i["date"], not i["critical"], i["case"]))
    return {"ok": True, "today": today.isoformat(), "days": days, "items": items}


def hook_text(result):
    items = result["items"]
    if not items:
        return ""
    lines = ["[lawfirm] %d일 안에 다가오는 기한·기일 %d건 — 사건메모 「주요 일정」 기준" % (result["days"], len(items))]
    for i in items[:MAX_LINES]:
        d = date.fromisoformat(i["date"])
        tag = " [불변기간·시효 — 날짜 재확인]" if i["critical"] else ""
        dd = "D-day" if i["d_day"] == 0 else "D-%d" % i["d_day"]
        lines.append("- %s %s(%s) %s: %s%s" % (dd, i["date"], WEEKDAYS[d.weekday()], i["case"], i["text"], tag))
    if len(items) > MAX_LINES:
        lines.append("- … 외 %d건" % (len(items) - MAX_LINES))
    return "\n".join(lines) + "\n"


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="기한·기일 D-day 점검")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan").add_argument("--days", type=int, default=IMMINENT_DAYS)
    sub.add_parser("hook")
    r = sub.add_parser("roots")
    r.add_argument("action", choices=("add", "remove", "list"))
    r.add_argument("folder", nargs="?")
    a = ap.parse_args(argv)
    if a.cmd == "hook":
        try:
            sys.stdout.write(hook_text(scan()))
        except Exception:  # noqa: BLE001 — 훅은 세션 시작을 막지 않는다
            pass
        return 0
    try:
        if a.cmd == "scan":
            out = scan(days=a.days)
        elif a.action == "list":
            out = roots_list()
        else:
            if not a.folder:
                raise ValueError("폴더를 주십시오")
            out = roots_add(a.folder) if a.action == "add" else roots_remove(a.folder)
    except (ValueError, OSError) as e:
        print(json.dumps({"ok": False, "error": "bad_input", "message": str(e)}, ensure_ascii=False))
        return 3
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
