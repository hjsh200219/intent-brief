#!/usr/bin/env python3
"""계약 검토 플레이북(사무소·의뢰인별 검토 기준) 파일 관리 — 표준 라이브러리만, Python 3.9.

위치: macOS·Linux ~/.intent-brief/playbooks/, Windows %LOCALAPPDATA%\\intent-brief\\playbooks\\ (플러그인 밖 —
업데이트·삭제에도 남는다. intent-brief 작업 폴더와 같은 루트, skills/intent-brief/scripts/_paths.py work_root 와 같은 규칙).
LAWFIRM_PLAYBOOK_DIR 로 바꿀 수 있다(테스트). 의뢰인별 기준은 --profile <이름> → playbooks/<이름>/ (사무소 기준과 섞이지 않는다).
show 는 의뢰인 기준 → 사무소 기준 → 번들 기본값(references/) 순서로 있는 것을 보여 준다. init 은 덮어쓰지 않는다
(의뢰인 기준은 사무소 기준이 있으면 그것을, 없으면 번들 기본값을 복사한다).
"""
import argparse
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REFS = os.path.join(HERE, "..", "references")
KINDS = {"contract": "playbook-contract.md", "nda": "playbook-nda.md"}
SANDBOX_GUIDE = "Codex 샌드박스가 홈 폴더 쓰기를 막았습니다(%s). 권한 상승으로 같은 명령을 다시 실행하거나, config.toml 의 [sandbox_workspace_write] writable_roots 에 그 폴더를 넣으십시오."


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


BAD_PROFILE_CHARS = set('/\\:*?"<>|')


def _profile(profile):
    """의뢰인 이름은 폴더 이름 하나로만 — 경로 이동(../)·구분자·제어문자는 거부한다."""
    if profile is None:
        return None
    if (not profile or profile.strip() != profile or profile in (".", "..") or len(profile) > 80
            or any(c in BAD_PROFILE_CHARS or ord(c) < 32 for c in profile)):
        raise ValueError("의뢰인 이름은 폴더 이름 하나로 쓸 수 있어야 합니다(/ \\ : * ? \" < > | 와 . .. 제외): %r" % profile)
    return profile


def path(kind, profile=None):
    name, profile = _kind(kind), _profile(profile)
    office = os.path.join(playbook_dir(), name)
    p = os.path.join(playbook_dir(), profile, name) if profile else office
    return {"ok": True, "kind": kind, "profile": profile, "path": p, "exists": os.path.isfile(p),
            "office_path": office, "default_path": os.path.normpath(os.path.join(REFS, name))}


def show(kind, profile=None):
    info = path(kind, profile)
    if info["exists"]:
        src, info["source"] = info["path"], "profile" if profile else "office"
    elif profile and os.path.isfile(info["office_path"]):
        src, info["source"] = info["office_path"], "office"
    else:
        src, info["source"] = info["default_path"], "bundled"
    with open(src, encoding="utf-8") as f:
        info["text"] = f.read()
    info["default"] = info["source"] == "bundled"
    return info


def init(kind, profile=None):
    info = path(kind, profile)
    if info["exists"]:
        info["created"] = False
        return info
    src = info["office_path"] if profile and os.path.isfile(info["office_path"]) else info["default_path"]
    os.makedirs(os.path.dirname(info["path"]), exist_ok=True)
    shutil.copyfile(src, info["path"])
    info["created"], info["exists"], info["copied_from"] = True, True, src
    return info


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="계약 검토 플레이북")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("path", "show", "init"):
        sp = sub.add_parser(name)
        sp.add_argument("kind")
        sp.add_argument("--profile", help="의뢰인별 기준 이름(폴더 하나)")
    a = ap.parse_args(argv)
    try:
        out = {"path": path, "show": show, "init": init}[a.cmd](a.kind, a.profile)
    except PermissionError as e:
        if not os.environ.get("CODEX_SANDBOX"):
            raise
        print(json.dumps({"ok": False, "error": "sandbox_write_blocked", "path": e.filename, "guide": SANDBOX_GUIDE % playbook_dir()},
                         ensure_ascii=False))
        return 6
    except (ValueError, OSError) as e:
        print(json.dumps({"ok": False, "error": "bad_input", "message": str(e)}, ensure_ascii=False))
        return 3
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
