"""초안 인용(조문·판례)을 원격 k-data(법제처) 원문과 정확 일치로 대조한다.

모델이 검색 결과를 옮겨 적지 않는다 — 이 스크립트가 .mcp.json 과 같은 URL 로 직접 JSON-RPC 를 보낸다.
판례는 응답의 「사건번호:」 줄이 정확히 같은 항목만 「확인됨」으로 본다(다른 판결 본문에 그 번호가 인용돼
검색에 걸린 경우를 걸러낸다). 「확인됨」은 그 조문·판례가 존재한다는 뜻이며 인용의 적합성은 보증하지 않는다.

사용:
  cite_check.py ping
  cite_check.py extract <draft.md>
  cite_check.py run <draft.md> [--max-seconds 540]
"""
import argparse
import hashlib
import json
import math
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths as P  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
TIMEOUT = 20.0
PAGE_SIZE = 50
MAX_PAGES = 5


class McpUnavailable(Exception):
    """연결 실패·타임아웃·5xx·재초기화 실패."""


class ToolError(Exception):
    """result.isError — kind 는 arg_error 또는 outage."""

    def __init__(self, kind, text):
        super().__init__(text)
        self.kind = kind


def mcp_url():
    v = os.environ.get("INTENT_BRIEF_MCP_URL")  # 개발·테스트 전용(가짜 서버)
    if v:
        return v
    cfg = P.load_json(os.path.join(P.PLUGIN_ROOT, ".mcp.json"))
    return cfg["mcpServers"]["k-data"]["url"]


def parse_response_body(body, content_type):
    """kpd.py parse_response_body 와 같은 규칙 — SSE 면 마지막 data: 줄, 아니면 JSON."""
    text = body.decode("utf-8")
    if "text/event-stream" in (content_type or "").lower():
        payloads = [ln[5:].strip() for ln in text.splitlines() if ln.startswith("data:")]
        for payload in reversed(payloads):
            if payload and payload != "[DONE]":
                return json.loads(payload)
        return None
    if not text.strip():
        return None
    return json.loads(text)


class McpClient:
    """kpd.py McpClient 이식 + HTTPError 본문 분류 + 세션 유실 시 재초기화 1회."""

    def __init__(self, url, timeout=TIMEOUT):
        self.url = url
        self.timeout = timeout
        self.session_id = None
        self.next_id = 1
        self.initialized = False

    def _request(self, body):
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self.url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json, text/event-stream")
        if self.session_id:
            req.add_header("Mcp-Session-Id", self.session_id)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                sid = resp.getheader("Mcp-Session-Id") or resp.getheader("mcp-session-id")
                if sid:
                    self.session_id = sid
                return resp.status, parse_response_body(resp.read(), resp.getheader("content-type", "application/json"))
        except urllib.error.HTTPError as exc:
            raw = b""
            try:
                raw = exc.read()
            except Exception:
                pass
            try:
                obj = parse_response_body(raw, exc.headers.get("content-type", "application/json")) if raw else None
            except (ValueError, UnicodeDecodeError):
                obj = None
            return exc.code, obj
        except (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError) as exc:
            raise McpUnavailable("연결 실패 또는 타임아웃: %s" % exc)
        except (ValueError, UnicodeDecodeError) as exc:
            raise McpUnavailable("응답을 해석하지 못했습니다: %s" % exc)

    def _rpc(self, method, params):
        rid = self.next_id
        self.next_id += 1
        payload = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            payload["params"] = params
        return self._request(payload)

    def initialize(self):
        self.session_id = None
        code, resp = self._rpc("initialize", {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                                              "clientInfo": {"name": "intent-brief", "version": "0.1.0"}})
        if code >= 400 or not resp or resp.get("error"):
            raise McpUnavailable("initialize 실패(HTTP %s)" % code)
        self._request({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.initialized = True

    def call(self, tool, args):
        if not self.initialized:
            self.initialize()
        code, resp = self._rpc("tools/call", {"name": tool, "arguments": args})
        err = resp.get("error") if isinstance(resp, dict) else None
        if code == 400 or (isinstance(err, dict) and err.get("code") == -32000):
            # 서버 재기동 등으로 세션이 사라졌다 — 재초기화 1회
            self.initialize()
            code, resp = self._rpc("tools/call", {"name": tool, "arguments": args})
        if code >= 500 or code == 400:
            raise McpUnavailable("HTTP %s" % code)
        if not isinstance(resp, dict):
            raise McpUnavailable("빈 응답")
        if resp.get("error"):
            e = resp["error"]
            raise McpUnavailable("JSON-RPC 오류: %s" % (e.get("message") if isinstance(e, dict) else e))
        result = resp.get("result") or {}
        content = result.get("content") or []
        text = content[0].get("text", "") if content else ""
        if result.get("isError"):
            kind = "arg_error" if re.search(r"-32602|Invalid arguments|파라미터|인자", text) else "outage"
            raise ToolError(kind, text)
        return text


# ── 추출 ──────────────────────────────────────────────────────
LAW_NAMES = ["민사소송법", "민사조정법", "민사집행법", "민법", "상법", "이자제한법", "소송촉진 등에 관한 특례법",
             "가사소송법", "행정소송법", "헌법", "주택임대차보호법", "상가건물 임대차보호법", "근로기준법"]
_LAW_STOP = {"방법", "증거방법", "위법", "적법", "불법", "편법", "입법", "사법", "해석법", "문법", "수법", "필법", "기법", "작법"}
_TOKEN = re.compile(r"(?P<law>%s|같은 법|동법|[가-힣]{2,15}법)|(?P<art>제\s*(?P<n>\d+)\s*조(?:\s*의\s*(?P<m>\d+))?)"
                    % "|".join(re.escape(x) for x in LAW_NAMES))
_CASE_FULL = re.compile(r"(?P<court>대법원|[가-힣]+(?:고등|지방)법원)\s*(?P<y>\d{4})\.\s*(?P<mo>\d{1,2})\.\s*(?P<d>\d{1,2})\.\s*"
                        r"(?:선고|자)\s*(?P<nums>\d{2,4}[가-힣]{1,4}\d+(?:\s*,\s*\d+)*)\s*(?:전원합의체\s*)?(?:판결|결정)")
_CASE_BARE = re.compile(r"(?P<nums>\d{4}[가-힣]{1,4}\d{1,7})\s*(?:전원합의체\s*)?(?:판결|결정)")


def _strip_header(md):
    """사건 표시(sec.header) 구간의 우리 사건번호는 대조 대상이 아니다."""
    m = re.search(r"^##\s*\[sec:sec\.header\].*?(?=^##\s|\Z)", md, re.M | re.S)
    if not m:
        return md
    return md[:m.start()] + " " * (m.end() - m.start()) + md[m.end():]


def extract(md):
    text = _strip_header(md)
    laws, cases, seen = [], [], set()
    cur, last_end = None, -999
    for m in _TOKEN.finditer(text):
        if m.group("law"):
            name = m.group("law")
            if name in ("같은 법", "동법"):
                last_end = m.end()
                continue
            if name in _LAW_STOP or name.endswith("방법"):
                cur = None
                continue
            cur, last_end = name, m.end()
        elif m.group("art") and cur and m.start() - last_end <= 25:
            n, sub = int(m.group("n")), int(m.group("m")) if m.group("m") else 0
            key = ("law", cur, n, sub)
            if key not in seen:
                seen.add(key)
                laws.append({"kind": "law", "law": cur, "article": n, "sub": sub, "text": "%s 제%d조%s" % (cur, n, "의%d" % sub if sub else ""),
                             "pos": m.start()})
            last_end = m.end()
    covered = []
    for m in _CASE_FULL.finditer(text):
        covered.append((m.start(), m.end()))
        first = m.group("nums").split(",")[0].strip()
        prefix = re.match(r"(\d{2,4}[가-힣]{1,4})", first).group(1)
        date = "%04d%02d%02d" % (int(m.group("y")), int(m.group("mo")), int(m.group("d")))
        for i, part in enumerate(m.group("nums").split(",")):
            part = part.strip()
            num = part if i == 0 else prefix + part
            key = ("case", num)
            if key not in seen:
                seen.add(key)
                cases.append({"kind": "case", "number": num, "court": m.group("court"), "date": date, "text": m.group(0), "pos": m.start()})
    for m in _CASE_BARE.finditer(text):
        if any(a <= m.start() < b for a, b in covered):
            continue
        num = m.group("nums")
        key = ("case", num)
        if key not in seen:
            seen.add(key)
            cases.append({"kind": "case", "number": num, "court": None, "date": None, "text": m.group(0), "pos": m.start()})
    return laws + cases


# ── 응답 해석 ─────────────────────────────────────────────────
_ITEM = re.compile(r"^\s*\d+\.\s*\[(\d+)\]\s*(.+?)\s*$", re.M)


_EMPTY = re.compile(r"검색 결과가 없습니다")


def parse_law_search(text, name):
    if _EMPTY.search(text):
        return None
    if "검색 결과" not in text and "총" not in text:
        raise ValueError("format")
    want = re.sub(r"\s+", "", name)
    for m in _ITEM.finditer(text):
        got = re.sub(r"\s*\([^)]*\)\s*$", "", m.group(2))  # 「… 특례법 (소송촉진법)」의 약칭 괄호
        if re.sub(r"\s+", "", got) == want:
            return int(m.group(1))
    return None


def parse_case_search(text):
    if _EMPTY.search(text):
        return 0, []
    m = re.search(r"총\s*(\d+)\s*건", text)
    if not m:
        raise ValueError("format")
    total = int(m.group(1))
    items = []
    blocks = re.split(r"(?m)^\s*\d+\.\s*(?=\[\d+\])", text)
    for b in blocks[1:]:
        mid = re.match(r"\[(\d+)\]\s*(.*)", b)
        num = re.search(r"사건번호:\s*([^\n]+)", b)
        date = re.search(r"선고일:\s*([\d.]+)", b)
        court = re.search(r"법원:\s*([^|\n]+)", b)
        if mid and num:
            items.append({"case_id": int(mid.group(1)), "title": mid.group(2).strip(),
                          "number": num.group(1).strip(), "date": date.group(1).replace(".", "") if date else None,
                          "court": court.group(1).strip() if court else None})
    return total, items


def _norm_no(s):
    return re.sub(r"\s+", "", s or "")


def _excerpt_case(text):
    out = []
    for label in ("판시사항", "판결요지"):
        m = re.search(label + r"\s*\n+(.+?)(?:\n#{2,3}\s|\Z)", text, re.S)
        if m:
            out.append("%s: %s" % (label, re.sub(r"\s+", " ", m.group(1)).strip()[:300]))
    return " / ".join(out)


class Checker:
    def __init__(self, cache_dir, client=None, deadline=None):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.client = client or McpClient(mcp_url())
        self.deadline = deadline
        self.calls = 0

    def _call(self, tool, args):
        key = hashlib.sha256(json.dumps([tool, args], sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:24]
        path = os.path.join(self.cache_dir, key + ".txt")
        if os.path.exists(path):
            return P.read_text(path)
        if self.deadline and time.time() > self.deadline:
            raise TimeoutError("시간 상한")
        text = self.client.call(tool, args)
        self.calls += 1
        P.atomic_write_text(path, text)
        P.atomic_write_json(path[:-4] + ".req.json", {"tool": tool, "args": args})
        return text

    def check_law(self, c):
        lid = parse_law_search(self._call("legal_research", {"action": "search_laws", "query": c["law"]}), c["law"])
        if lid is None:
            return {"status": "unverified", "detail": "법령명 정확 일치 없음"}
        art = "%04d%02d" % (c["article"], c["sub"])
        text = self._call("legal_research", {"action": "get_law_article_sub", "law_id": lid, "article": art})
        head = "제%d조%s" % (c["article"], "의%d" % c["sub"] if c["sub"] else "")
        m = re.search(r"#{2,4}\s*" + re.escape(head) + r"\b.*", text)
        if not m or not re.search(re.escape(head) + r"\s*\(", text):
            return {"status": "unverified", "detail": "조문 본문 없음", "law_id": lid}
        body = text[m.start():]
        return {"status": "confirmed", "law_id": lid, "excerpt": re.sub(r"\s+", " ", body)[:200]}

    def check_case(self, c):
        target = _norm_no(c["number"])
        base = {"action": "search_cases", "query": c["number"], "display": PAGE_SIZE}
        if c.get("court") == "대법원":
            base["court"] = "supreme"
        if c.get("date"):
            base.update(date_from=c["date"], date_to=c["date"])
        attempts = [dict(base)] if c.get("date") else [dict(base, search_type="case_name")]
        cited_by = 0
        for args in attempts:
            total, items = parse_case_search(self._call("case_research", dict(args, page=1)))
            cited_by = max(cited_by, total)
            hit = next((it for it in items if _norm_no(it["number"]) == target), None)
            pages_seen = 1
            if not hit and total > PAGE_SIZE:
                last = math.ceil(total / PAGE_SIZE)
                for page in range(last, 1, -1):
                    if pages_seen >= MAX_PAGES:
                        return {"status": "search_limit", "detail": "총 %d건 중 %d쪽까지 확인" % (total, pages_seen)}
                    _, items = parse_case_search(self._call("case_research", dict(args, page=page)))
                    pages_seen += 1
                    hit = next((it for it in items if _norm_no(it["number"]) == target), None)
                    if hit:
                        break
            if hit:
                detail = self._call("case_research", {"action": "get_case_detail", "case_id": hit["case_id"]})
                res = {"status": "confirmed", "case_id": hit["case_id"], "title": hit["title"], "date": hit["date"],
                       "excerpt": _excerpt_case(detail), "pages": pages_seen}
                if c.get("date") and hit["date"] and hit["date"] != c["date"]:
                    res = {"status": "unverified", "detail": "선고일 불일치(원문 %s)" % hit["date"], "case_id": hit["case_id"]}
                return res
            if total == 0 and not c.get("date") and args.get("search_type") == "case_name":
                attempts.append(dict(base, search_type="full_text"))
        if c.get("date"):
            # 선고일로 좁힌 검색에 없으면 날짜 없이 한 번 더 — 선고일만 틀린 인용과 인용 건수를 가린다
            loose = {"action": "search_cases", "query": c["number"], "display": PAGE_SIZE, "search_type": "full_text", "page": 1}
            total, items = parse_case_search(self._call("case_research", loose))
            cited_by = max(cited_by, total)
            hit = next((it for it in items if _norm_no(it["number"]) == target), None)
            if hit:
                return {"status": "unverified", "detail": "선고일 불일치(원문 %s)" % hit["date"], "case_id": hit["case_id"]}
        detail = "사건번호 정확 일치 없음(법제처 원문 없음)"
        if cited_by:
            detail += " · 이 번호를 인용한 다른 판결 %d건 검색됨 — 원문은 변호사가 확인" % cited_by
        return {"status": "unverified", "detail": detail, "cited_by": cited_by}

    def check(self, c):
        try:
            return self.check_law(c) if c["kind"] == "law" else self.check_case(c)
        except ToolError as e:
            return {"status": e.kind, "detail": str(e)[:200]}
        except McpUnavailable as e:
            return {"status": "outage", "detail": str(e)[:200]}
        except TimeoutError:
            return {"status": "pending", "detail": "시간 상한 — 다시 실행하면 캐시에서 이어 갑니다"}
        except ValueError:
            return {"status": "format_changed", "detail": "응답 형식을 해석하지 못했습니다"}


TAG_FOR = {"unverified": "unverified", "search_limit": "search_limit", "outage": "outage",
           "format_changed": "format_changed", "arg_error": "arg_error"}


def tag_draft(md, results, phrases):
    """확인되지 않은 인용 뒤에 태그를 한 번 붙인다(이미 붙어 있으면 그대로)."""
    for r in sorted(results, key=lambda x: -x["pos"]):
        key = TAG_FOR.get(r["status"])
        if not key:
            continue
        tag = phrases["tag"][key]
        idx = md.find(r["text"])
        if idx < 0:
            continue
        end = idx + len(r["text"])
        if md[end:end + len(tag) + 1].strip().startswith(tag):
            continue
        md = md[:end] + " " + tag + md[end:]
    return md


def run(draft_path, max_seconds=540, client=None):
    md = P.read_text(draft_path)
    work = os.path.dirname(os.path.abspath(draft_path))
    cites = extract(md)
    chk = Checker(os.path.join(work, "cite"), client=client, deadline=time.time() + max_seconds)
    results = []
    for c in cites:
        r = dict(c)
        r.update(chk.check(c))
        results.append(r)
    complete = all(r["status"] != "pending" for r in results)
    if complete:
        P.atomic_write_text(draft_path, tag_draft(md, results, P.load_phrases()))
    summary = {}
    for r in results:
        summary[r["status"]] = summary.get(r["status"], 0) + 1
    out = {"complete": complete, "calls": chk.calls, "summary": summary, "results": results}
    P.atomic_write_json(os.path.join(work, "cite_results.json"), out)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ping")
    s = sub.add_parser("extract"); s.add_argument("draft")
    s = sub.add_parser("run"); s.add_argument("draft"); s.add_argument("--max-seconds", type=float, default=540)
    a = ap.parse_args(argv)
    if a.cmd == "ping":
        try:
            c = McpClient(mcp_url())
            c.initialize()
            return P.emit({"ok": True, "url": c.url})
        except McpUnavailable as e:
            return P.emit({"ok": False, "error": str(e), "note": "인용 대조만 장애 태그로 표시하고 계속합니다"})
    if a.cmd == "extract":
        return P.emit({"ok": True, "citations": extract(P.read_text(a.draft))})
    if a.cmd == "run":
        return P.emit(dict(ok=True, **run(a.draft, a.max_seconds)))


if __name__ == "__main__":
    sys.exit(main())
