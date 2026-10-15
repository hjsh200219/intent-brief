#!/usr/bin/env python3
"""검토할 문서의 본문을 문단 번호와 함께 꺼내고(.docx·.md·.txt), 기계적으로 판정되는 형식 문제를 찾는다.
표준 라이브러리만, Python 3.9. 문서를 고치지 않는다(읽기만).

  text <파일>   문단 목록(JSON) — 검토 지적은 「문단 N」으로 가리킨다
  lint <파일>   겹친 낱말·공백·짝 없는 괄호·증거번호 건너뜀·[확인 필요] 남음·문체 혼용
"""
import argparse
import json
import os
import re
import sys
import zipfile
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
PAIRS = [("(", ")"), ("[", "]"), ("「", "」"), ("『", "』"), ("“", "”")]
PARTICLE_DUP = re.compile(r"(\S*?(을|를|이|가|은|는|의|에|도|와|과))\s+\2(?=\s|$)")
WORD_DUP = re.compile(r"(?<!\S)(\S{2,})\s+\1(?=\s|[.,]|$)")
MAX_XML = 50 * 2**20
EVIDENCE = re.compile(r"(갑|을|병)\s*제\s*(\d+)\s*호증")
ENDING = re.compile(r"([가-힣])다\.")


def _docx_paragraphs(path):
    with zipfile.ZipFile(path) as z:
        if z.getinfo("word/document.xml").file_size > MAX_XML:
            raise ValueError("document.xml 이 너무 큽니다(%d MB 초과)" % (MAX_XML // 2**20))
        raw = z.read("word/document.xml")
    # 정상 docx 본문에는 DTD 가 없다 — 엔티티 폭증(billion laughs) 문서를 파싱하기 전에 거부한다(표준 라이브러리만 쓰는 대신).
    if re.search(rb"<!(DOCTYPE|ENTITY)", raw[:4096] + raw[-4096:]) or b"<!ENTITY" in raw:
        raise ValueError("DTD·엔티티 선언이 든 docx 는 읽지 않습니다(정상 Word 문서가 아님)")
    root = ET.fromstring(raw)
    body = root.find(W + "body")
    out = []

    def para_text(p):
        parts = []
        for node in p.iter():
            if node.tag == W + "t":
                parts.append(node.text or "")
            elif node.tag == W + "tab":
                parts.append("\t")
            elif node.tag in (W + "br", W + "cr"):
                parts.append("\n")
        return "".join(parts).strip()

    for child in list(body) if body is not None else []:
        if child.tag == W + "p":
            out.append(para_text(child))
        elif child.tag == W + "tbl":
            for p in child.iter(W + "p"):
                out.append(para_text(p))
    return [t for t in out if t]


def read_doc(path):
    if not os.path.isfile(path):
        raise ValueError("파일이 없습니다: %s" % path)
    if path.lower().endswith(".docx"):
        paras = _docx_paragraphs(path)
    else:
        with open(path, encoding="utf-8", errors="replace") as f:
            paras = [ln.rstrip("\r\n") for ln in f if ln.strip()]
    return {"ok": True, "path": path, "chars": sum(len(p) for p in paras), "paragraphs": paras}


def _add(out, kind, n, severity, detail):
    out.append({"kind": kind, "paragraph": n, "severity": severity, "detail": detail})


def lint(path):
    paras = read_doc(path)["paragraphs"]
    out = []
    formal, plain = [], []
    first_seen = {}
    for n, p in enumerate(paras, 1):
        m = PARTICLE_DUP.search(p) or WORD_DUP.search(p)
        if m:
            _add(out, "겹친 낱말", n, "중간", m.group(0))
        if re.search(r"\S {2,}\S", p):
            _add(out, "공백", n, "낮음", "띄어쓰기 두 칸 이상")
        for a, b in PAIRS:
            if p.count(a) != p.count(b):
                _add(out, "짝 없는 괄호", n, "중간", "%s%s 짝이 맞지 않음" % (a, b))
        if "[확인 필요" in p:
            _add(out, "확인 필요 남음", n, "높음", "제출 전 채워야 할 [확인 필요] 표시")
        for side, num in EVIDENCE.findall(p):
            first_seen.setdefault((side, int(num)), n)
        for m in ENDING.finditer(p):
            (formal if p[max(0, m.start() - 1):m.start() + 1].endswith("니") or m.group(1) == "니" else plain).append(n)
    by_side = {}
    for (side, num), n in first_seen.items():
        by_side.setdefault(side, {})[num] = n
    for side, nums in sorted(by_side.items()):
        top = max(nums)
        missing = [k for k in range(1, top) if k not in nums]
        if missing:
            _add(out, "증거번호 건너뜀", nums[top], "중간",
                 "%s 제%s호증이 본문에 없음" % (side, "·".join(str(k) for k in missing)))
    minority = plain if len(formal) >= len(plain) else formal
    if formal and plain:
        style = "평서체(~다.)" if minority is plain else "경어체(~니다.)"
        for n in sorted(set(minority)):
            _add(out, "문체 혼용", n, "중간", "다른 문단과 달리 %s" % style)
    out.sort(key=lambda f: (f["paragraph"], f["kind"]))
    return {"ok": True, "path": path, "paragraphs": len(paras), "findings": out}


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="검토 문서 본문 추출·형식 점검")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("text").add_argument("path")
    sub.add_parser("lint").add_argument("path")
    a = ap.parse_args(argv)
    try:
        out = read_doc(a.path) if a.cmd == "text" else lint(a.path)
    except (ValueError, OSError, zipfile.BadZipFile, ET.ParseError) as e:
        print(json.dumps({"ok": False, "error": "bad_input", "message": str(e)}, ensure_ascii=False))
        return 3
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
