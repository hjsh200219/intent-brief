# 구현 전 점검 — 첫눈에 보이지 않는 함정

범용 코딩 상식은 적지 않는다. 이 repo 에서만 생기는 함정만 적는다.

## 구조
- 새 스크립트는 `skills/intent-brief/scripts/` 에 두고 `_paths` 의 저장·출력 함수(`atomic_write_*`, `emit`, `fail`)를 쓴다. 따로 만들면 원자 저장·오류 JSON 형식이 갈린다.
- SKILL.md 에 판단 규칙을 산문으로 늘리지 말고, 결정론으로 끝나는 일은 스크립트 + 테스트로 만든다(`check_draft.py` 가 선례).
- 의도·섹션 어휘는 `references/intent-params.json` 이 정본이다. 코드·SKILL.md 에 섹션 id 를 새로 박지 않는다.

## 받는 PC
- Python 3.9: `match`·`X | Y` 타입 같은 문법뿐 아니라 `sys.stdlib_module_names`(3.10+) 같은 API 도 없다. 테스트도 3.9 로 한 번 돌린다(Health Stack).
- Windows: 한글 경로·CRLF 사건메모·`%LOCALAPPDATA%`. 콘솔 코드 페이지가 UTF-8 이 아닐 수 있어 표준출력은 `_paths.emit` 가 UTF-8 바이트로 직접 쓴다 — 스크립트에서 `print` 로 결과를 내지 않는다.

## 원격(k-data)
- `search_type` 은 사건번호 검색에서도 `full_text` 가 더 잘 찾는 경우가 있다(2018다248626: case_name 4건 중 4번째, full_text 8건 중 8번째). 정확 일치 대조는 결과 전체를 본다.
- 법제처 DB 에 원문이 없는 판례가 있다(2014다26187 — 인용한 하급심만 검색됨). 「없음」을 오류로 보지 않는다.

## 공유 모듈
| 모듈 | 쓰는 곳 |
|---|---|
| `_paths.py` — 경로·작업 폴더·원자 저장·금액·JSON 출력 | 모든 스크립트 |
| `state.py` — 인터뷰 상태 읽기·쓰기 | `intent`·`memo`·`check_draft`·`render_docx` |
| `check_draft` — draft.md 파싱(`parse_draft`·`split_front`) | `render_docx`(`split_front`·앵커 정규식), `dev/e2e.py` |
