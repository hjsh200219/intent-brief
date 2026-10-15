#!/usr/bin/env python3
"""계약 검토 플레이북(사무소·의뢰인별 검토 기준) 파일 관리 — 표준 라이브러리만, Python 3.9.

위치: macOS·Linux ~/.intent-brief/playbooks/, Windows %LOCALAPPDATA%\\intent-brief\\playbooks\\ (플러그인 밖 —
업데이트·삭제에도 남는다. intent-brief 작업 폴더와 같은 루트, skills/intent-brief/scripts/_paths.py work_root 와 같은 규칙).
LAWFIRM_PLAYBOOK_DIR 로 바꿀 수 있다(테스트). 파일이 없으면 번들 기본값(references/)을 보여 준다. init 은 덮어쓰지 않는다.
"""
import argparse
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REFS = os.path.join(HERE, "..", "references")
KINDS = {"contract": "playbook-contract.md", "nda": "playbook-nda.md"}


def playbook_dir():
    env = os.environ.get("LAWFIRM_PLAYBOOK_DIR")
    if env:
        return env
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
        return os.path.join(base, "intent-brief", "playbooks")
    return os.path.join(os.path.expanduser("~"), ".intent-brief", "playbooks")


def _kind(kind):
    if kind not in KINDS:
        raise ValueError("플레이북 종류는 %s 중 하나입니다: %s" % ("·".join(KINDS), kind))
    return KINDS[kind]


def path(kind):
    name = _kind(kind)
    p = os.path.join(playbook_dir(), name)
    return {"ok": True, "kind": kind, "path": p, "exists": os.path.isfile(p),
            "default_path": os.path.normpath(os.path.join(REFS, name))}


def show(kind):
    info = path(kind)
    src = info["path"] if info["exists"] else info["default_path"]
    with open(src, encoding="utf-8") as f:
        info["text"] = f.read()
    info["default"] = not info["exists"]
    return info


def init(kind):
    info = path(kind)
    if info["exists"]:
        info["created"] = False
        return info
    os.makedirs(os.path.dirname(info["path"]), exist_ok=True)
    shutil.copyfile(info["default_path"], info["path"])
    info["created"], info["exists"] = True, True
    return info


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="계약 검토 플레이북")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("path", "show", "init"):
        sub.add_parser(name).add_argument("kind")
    a = ap.parse_args(argv)
    try:
        out = {"path": path, "show": show, "init": init}[a.cmd](a.kind)
    except (ValueError, OSError) as e:
        print(json.dumps({"ok": False, "error": "bad_input", "message": str(e)}, ensure_ascii=False))
        return 3
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
