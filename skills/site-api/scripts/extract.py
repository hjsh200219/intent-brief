#!/usr/bin/env python3
"""HTML·JS 본문에서 API 후보를 뽑는다 — 표준 라이브러리만, Python 3.9. 네트워크를 쓰지 않는다(수집은 discover.py).

정적 분석이라 놓치는 것이 있다: 런타임에 조립되는 주소, 서버가 HTML 에 데이터를 심는 사이트(inline_state).
그럴 때는 discover.py --cdp 로 실제 네트워크 요청을 잡는다.
"""
import argparse
import html
import json
import re
import sys
from urllib.parse import urljoin, urlparse

KEYWORDS = re.compile(r"(?i)/(api|graphql|gql|rest|v\d+|auth|login|signin|sign-in|token|session|search|ajax|json)(/|$|\?)")
AUTH = re.compile(r"(?i)(login|signin|sign-in|auth|token|session|oauth)")
STATE_NAMES = ("__NEXT_DATA__", "__APOLLO_STATE__", "__NUXT__", "__INITIAL_STATE__", "__PRELOADED_STATE__", "__remixContext")
LITERAL = re.compile(r"""(["'`])((?:(?!\1)[^\\\n]|\\.){1,300})\1""")
CONST = re.compile(r"""(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*["'`]([^"'`\n]{1,200})["'`]""")
METHOD_BEFORE = re.compile(r"(?i)\.(get|post|put|patch|delete)\s*\(\s*$")
METHOD_AFTER = re.compile(r"""(?i)^[^;]{0,120}?method\s*:\s*["'](get|post|put|patch|delete)["']""")
GQL_OP = re.compile(r"""operationName\s*:\s*["'](\w+)["']""")
SCRIPT_SRC = re.compile(r"""(?is)<script\b[^>]*\bsrc\s*=\s*["']([^"']+)["']""")
FORM = re.compile(r"""(?is)<form\b([^>]*)>""")
ATTR = re.compile(r"""(?is)\b(action|method)\s*=\s*["']([^"']*)["']""")


def _same_host(url, base):
    u, b = urlparse(url), urlparse(base)
    return u.scheme in ("http", "https") and u.hostname == b.hostname


def script_urls(page_html, base):
    out = []
    for src in SCRIPT_SRC.findall(page_html):
        url = urljoin(base, html.unescape(src.strip()))
        if _same_host(url, base) and url not in out:
            out.append(url)
    return out


def inline_state(page_html):
    return [n for n in STATE_NAMES if re.search(r"(id=[\"']%s[\"']|window\.%s\s*=|\b%s\s*=)" % ((re.escape(n),) * 3), page_html)]


def form_actions(page_html, base):
    out = []
    for attrs in FORM.findall(page_html):
        a = {k.lower(): v for k, v in ATTR.findall(attrs)}
        if not a.get("action"):
            continue
        url = urljoin(base, html.unescape(a["action"]))
        if _same_host(url, base):
            item = {"url": url, "method": (a.get("method") or "GET").upper()}
            if item not in out:
                out.append(item)
    return out


def _consts(text):
    return {k: v for k, v in CONST.findall(text)}


def _resolve(lit, consts):
    def sub(m):
        return consts.get(m.group(1), m.group(0))
    return re.sub(r"\$\{\s*([A-Za-z_$][\w$]*)\s*\}", sub, lit)


def find_endpoints(text, base):
    consts = _consts(text)
    found, external = {}, []
    for m in LITERAL.finditer(text):
        lit = _resolve(m.group(2), consts)
        if "${" in lit or " " in lit.strip():
            continue
        if lit.startswith(("http://", "https://")):
            if not _same_host(lit, base):
                if "/api" in lit and lit not in external:
                    external.append(lit.split("?")[0])
                continue
            path = urlparse(lit).path or "/"
        elif lit.startswith("/") and not lit.startswith("//"):
            path = lit.split("?")[0].split("#")[0]
        else:
            continue
        if not KEYWORDS.search(path) or re.search(r"\.(js|css|png|jpe?g|svg|gif|woff2?|ico|map)$", path):
            continue
        before, after = text[max(0, m.start() - 40):m.start()], text[m.end():m.end() + 160]
        mb, ma = METHOD_BEFORE.search(before), METHOD_AFTER.search(after)
        method = (mb or ma).group(1).upper() if (mb or ma) else "GET"
        e = found.setdefault(path, {"path": path, "url": urljoin(base, path), "method": method, "count": 0})
        e["count"] += 1
        if method != "GET":
            e["method"] = method
    eps = sorted(found.values(), key=lambda e: (-("/api" in e["path"] or "graphql" in e["path"]), -(e["method"] != "GET"),
                                                -e["count"], e["path"]))
    return {"endpoints": eps, "external": external,
            "auth_candidates": [e["path"] for e in eps if AUTH.search(e["path"])],
            "graphql_operations": sorted(set(GQL_OP.findall(text)))}


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="HTML·JS 파일에서 API 후보 추출(오프라인)")
    ap.add_argument("base", help="원래 페이지 주소(상대 경로 해석용)")
    ap.add_argument("files", nargs="+")
    a = ap.parse_args(argv)
    text = "\n".join(open(f, encoding="utf-8", errors="replace").read() for f in a.files)
    out = find_endpoints(text, a.base)
    out.update(ok=True, scripts=script_urls(text, a.base), inline_state=inline_state(text), forms=form_actions(text, a.base))
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
