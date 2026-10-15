#!/usr/bin/env python3
"""발굴한 API 스펙으로 클라이언트 파일을 만든다 — 표준 라이브러리만, Python 3.9.

템플릿은 ../templates/client.py.tmpl(bigcase.py 와 같은 틀: 키체인 자격증명·세션 재사용·API 호스트 고정·요청 간격).
만든 파일은 플러그인 밖(작업 폴더 site-api/)에 둔다 — 플러그인 업데이트로 지워지지 않게. 같은 이름이 있으면 덮지 않고 _2, _3.
"""
import argparse
import json
import os
import re
import sys
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "..", "templates", "client.py.tmpl")
AUTH_MODES = ("bearer-login", "cookie-login", "none")
SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{1,30}$")


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


def scaffold(slug, base, auth="bearer-login", login_path="/auth/login", id_field="email", pw_field="password",
             token_field="accessToken", title=None, out_dir=None):
    if not SLUG_RE.match(slug or ""):
        raise ValueError("이름은 영문 소문자로 시작하는 2–31자(소문자·숫자·-)입니다: %r" % slug)
    if auth not in AUTH_MODES:
        raise ValueError("인증 방식은 %s 중 하나입니다: %s" % ("·".join(AUTH_MODES), auth))
    api = _check_base(base)
    if not login_path.startswith("/"):
        raise ValueError("로그인 경로는 / 로 시작하는 API 아래 경로입니다: %s" % login_path)
    values = {"SLUG": slug, "TITLE": title or slug, "API": api, "AUTH": auth, "LOGIN_PATH": login_path,
              "ID_FIELD": id_field, "PW_FIELD": pw_field, "TOKEN_FIELD": token_field, "KEYRING": "site-api-" + slug}
    with open(TEMPLATE, encoding="utf-8") as f:
        src = f.read()
    for k, v in values.items():
        src = src.replace("{{%s}}" % k, json.dumps(v, ensure_ascii=False))
    left = re.findall(r"\{\{[A-Z_]+\}\}", src)
    if left:
        raise ValueError("채우지 못한 자리: %s" % ", ".join(sorted(set(left))))
    out_dir = out_dir or default_out_dir()
    os.makedirs(out_dir, exist_ok=True)
    stem = slug.replace("-", "_")
    path, n = os.path.join(out_dir, stem + ".py"), 1
    while os.path.exists(path):
        n += 1
        path = os.path.join(out_dir, "%s_%d.py" % (stem, n))
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    return {"ok": True, "path": path, "slug": slug, "api": api, "auth": auth,
            "next": ["uv run %s status" % path, "uv run %s setup" % path if auth != "none" else None,
                     "uv run %s get <경로>" % path]}


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="사이트 API 클라이언트 만들기")
    ap.add_argument("slug")
    ap.add_argument("base", help="API 기준 주소(https://호스트/경로)")
    ap.add_argument("--auth", default="bearer-login", choices=AUTH_MODES)
    ap.add_argument("--login-path", default="/auth/login")
    ap.add_argument("--id-field", default="email")
    ap.add_argument("--pw-field", default="password")
    ap.add_argument("--token-field", default="accessToken")
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
