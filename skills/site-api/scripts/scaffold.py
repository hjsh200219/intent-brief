#!/usr/bin/env python3
"""발굴한 API 스펙으로 클라이언트 파일을 만든다 — 표준 라이브러리만, Python 3.9.

템플릿은 ../templates/client.py.tmpl(bigcase.py 와 같은 틀: 키체인 자격증명·세션 재사용·API 호스트 고정·요청 간격).
만든 파일은 플러그인 밖(작업 폴더 site-api/)에 둔다 — 플러그인 업데이트로 지워지지 않게. 같은 이름이 있으면 덮지 않고 _2, _3.
"""
import argparse
import json
import os
import re
import shlex
import sys
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "..", "templates", "client.py.tmpl")
AUTH_MODES = ("bearer-login", "cookie-login", "none")
SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{1,30}$")
FIELD_RE = re.compile(r"^[A-Za-z_][\w.-]{0,63}$")
PATH_RE = re.compile(r"^/[\w./~%-]{0,200}$")
PLACEHOLDER = re.compile(r"\{\{([A-Z_]+)\}\}")
DEFAULTS = {"auth": "bearer-login", "login_path": "/auth/login", "id_field": "email", "pw_field": "password",
            "token_field": "accessToken"}


def default_out_dir():
    env = os.environ.get("LAWFIRM_SITE_API_DIR")
    if env:
        return env
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
        return os.path.join(base, "intent-brief", "site-api")
    return os.path.join(os.path.expanduser("~"), ".intent-brief", "site-api")


def _check_base(base):
    u = urlparse(base.strip())
    if u.scheme != "https" or not u.hostname:
        raise ValueError("API 주소는 https:// 로 시작해야 합니다: %s" % base)
    if u.username or u.password:
        raise ValueError("API 주소에 계정 정보를 넣지 않습니다")
    if u.query or u.fragment:
        raise ValueError("API 주소에는 경로까지만 넣습니다(쿼리 없이)")
    return base.strip().rstrip("/")


def scaffold(slug, base, auth=DEFAULTS["auth"], login_path=DEFAULTS["login_path"], id_field=DEFAULTS["id_field"],
             pw_field=DEFAULTS["pw_field"], token_field=DEFAULTS["token_field"], title=None, out_dir=None):
    if not SLUG_RE.match(slug or ""):
        raise ValueError("이름은 영문 소문자로 시작하는 2–31자(소문자·숫자·-)입니다: %r" % slug)
    if auth not in AUTH_MODES:
        raise ValueError("인증 방식은 %s 중 하나입니다: %s" % ("·".join(AUTH_MODES), auth))
    api = _check_base(base)
    if not PATH_RE.match(login_path or ""):
        raise ValueError("로그인 경로는 / 로 시작하는 API 아래 경로(영문·숫자·./-_~%%)입니다: %r" % login_path)
    for name, v in (("아이디 필드", id_field), ("비밀번호 필드", pw_field), ("토큰 위치", token_field)):
        if not FIELD_RE.match(v or ""):
            raise ValueError("%s 이름은 영문·숫자·_.- 64자 이내입니다: %r" % (name, v))
    title = title or slug
    if len(title) > 60 or any(ord(ch) < 32 for ch in title):
        raise ValueError("제목은 줄바꿈·제어문자 없이 60자 이내입니다")
    values = {"SLUG": slug, "TITLE": title, "API": api, "AUTH": auth, "LOGIN_PATH": login_path,
              "ID_FIELD": id_field, "PW_FIELD": pw_field, "TOKEN_FIELD": token_field, "KEYRING": "site-api-" + slug}
    with open(TEMPLATE, encoding="utf-8") as f:
        src = f.read()
    missing = sorted(set(PLACEHOLDER.findall(src)) - set(values))
    if missing:
        raise ValueError("채우지 못한 자리: %s" % ", ".join(missing))
    # 한 번에 치환한다 — 넣은 값 안의 {{자리}} 를 다시 치환하면 문자열 밖으로 코드가 들어갈 수 있다.
    src = PLACEHOLDER.sub(lambda m: json.dumps(values[m.group(1)], ensure_ascii=False), src)
    out_dir = out_dir or default_out_dir()
    os.makedirs(out_dir, exist_ok=True)
    stem = slug.replace("-", "_")
    path, n = os.path.join(out_dir, stem + ".py"), 1
    while os.path.exists(path):
        n += 1
        path = os.path.join(out_dir, "%s_%d.py" % (stem, n))
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    q = shlex.quote(path)
    return {"ok": True, "path": path, "slug": slug, "api": api, "auth": auth,
            "next": ["uv run %s status" % q, "uv run %s setup" % q if auth != "none" else None,
                     "uv run %s get <경로>" % q]}


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="사이트 API 클라이언트 만들기")
    ap.add_argument("slug")
    ap.add_argument("base", help="API 기준 주소(https://호스트/경로)")
    ap.add_argument("--auth", default=DEFAULTS["auth"], choices=AUTH_MODES)
    ap.add_argument("--login-path", default=DEFAULTS["login_path"])
    ap.add_argument("--id-field", default=DEFAULTS["id_field"])
    ap.add_argument("--pw-field", default=DEFAULTS["pw_field"])
    ap.add_argument("--token-field", default=DEFAULTS["token_field"])
    ap.add_argument("--title")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    try:
        out = scaffold(a.slug, a.base, a.auth, a.login_path, a.id_field, a.pw_field, a.token_field, a.title, a.out)
    except (ValueError, OSError) as e:
        print(json.dumps({"ok": False, "error": "bad_input", "message": str(e)}, ensure_ascii=False))
        return 3
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
