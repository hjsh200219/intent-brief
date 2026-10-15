# 구현 전 점검 — 첫눈에 보이지 않는 함정

범용 코딩 상식은 적지 않는다. 이 repo 에서만 생기는 함정만 적는다.

## 구조
- 민사 서면(intent-brief)의 새 스크립트는 `skills/intent-brief/scripts/` 에 두고 `_paths` 의 저장·출력 함수(`atomic_write_*`, `emit`, `fail`)를 쓴다. 따로 만들면 원자 저장·오류 JSON 형식이 갈린다.
- SKILL.md 에 판단 규칙을 산문으로 늘리지 말고, 결정론으로 끝나는 일은 스크립트 + 테스트로 만든다(`check_draft.py` 가 선례).
- 의도·섹션 어휘는 `skills/intent-brief/references/intent-params.json` 이 정본이다(루트 `references/` 는 내장 스킬 공용 문서). 코드·SKILL.md 에 섹션 id 를 새로 박지 않는다.

## 받는 PC
- Python 3.9(`skills/intent-brief/scripts/`·`foreigncase.py`·0.6.0 스킬 스크립트(L3d) — `bigcase.py`·site-api `discover.py`·생성 클라이언트는 uv 로 3.10+·Scrapling 을 쓴다): `match`·`X | Y` 타입 같은 문법뿐 아니라 `sys.stdlib_module_names`(3.10+) 같은 API 도 없다. 테스트도 3.9 로 한 번 돌린다(Health Stack).
- Windows: 한글 경로·CRLF 사건메모·`%LOCALAPPDATA%`. 콘솔 코드 페이지가 UTF-8 이 아닐 수 있어 표준출력은 `_paths.emit` 가 UTF-8 바이트로 직접 쓴다 — 스크립트에서 `print` 로 결과를 내지 않는다. 예외는 `bigcase.py`(L3b)와 `_paths` 를 쓰지 않는 독립 스크립트(`foreigncase.py`, 0.6.0 L3d·L3e) — `main()` 이 stdout·stderr 를 UTF-8 로 `reconfigure` 한 뒤 `print` 를 쓰고, `casesearch.py` 는 하위 프로세스에 `PYTHONIOENCODING=utf-8` 을 넘긴다(cp949 콘솔에서 사건번호가 깨지던 것, 2026-10-15).

## Codex(같은 repo 를 Codex 플러그인으로도 설치 — 2026-10-16 실측: macOS codex-cli 0.162.1, Windows vm-develop 0.160.0)
- 셸 도구에는 `CLAUDE_PLUGIN_ROOT` 가 없다(훅에만 준다). `${CLAUDE_PLUGIN_ROOT}` 를 쓰는 문서에는 「Codex 에서는 셸에 …」 안내 줄을 둔다(`tests/test_codex_plugin.py` 가 검사).
- 명령(`commands/`)은 `source-command-<이름>` 스킬로 바뀌는데 `$ARGUMENTS` 를 쓰면 말없이 빠진다.
- SessionStart 훅이 일반 텍스트를 내면 「Failed」로 버린다 — `hookSpecificOutput.additionalContext` JSON 으로 낸다(Claude Code 도 받는다). Windows Codex 는 `commandWindows` 를 PowerShell 5.1 로 돌리고 `${CLAUDE_PLUGIN_ROOT}` 를 미리 경로로 바꿔 넣는다 — 한글은 JSON `\uXXXX`(ASCII)로 낸다.
- 플러그인 훅은 사용자가 신뢰를 승인해야 돈다(TUI 「Hooks need review」). 무인 시험은 격리 `CODEX_HOME` + `codex exec --dangerously-bypass-hook-trust` 로 한다.

## 원격(법제처 Open API, `lawapi.py`)
- 판례 정확 일치는 사건번호 파라미터 `nb` 로 찾는다(2026-10-15 실측: 2016다225353·2018다248626 모두 1건). `query` 는 사건명 검색이라 번호로는 안 걸리고, 본문 검색은 `search=2`.
- 결과가 1건이면 목록이 배열이 아니라 객체로 온다 — `lawapi._list` 로 감싼다.
- 조문 조회(`JO=XXXXYY`)는 편·장·절 제목 줄도 같은 조문번호로 함께 온다. `조문여부 == "조문"` 이고 「제N조(」로 시작하는 항목만 본문이다.
- 잘못된 키·IP 미등록은 HTTP 200 + `{"result": "사용자 정보 검증에 실패하였습니다."}` 로 온다(오류 코드 없음). 요청이 잦으면 빈 본문이 온다 — 간격 1초.
- 법제처 DB 에 원문이 없는 판례가 있다(2014다26187 — 사건번호 검색 0건). 「없음」을 오류로 보지 않는다.

## 원격(빅케이스, `bigcase.py`)
- Bearer 토큰은 `https://bigcase.ai` 로만 보낸다 — `_api_url` 이 다른 호스트·평문 http 절대 주소를 요청 전에 거부한다(2026-10-15). 새 API 를 붙일 때도 `request()` 를 거친다.
- 경로에 넣는 값(문서 id 등)은 `quote(..., safe='')` 로 인코딩한다 — 그대로 넣으면 `../` 로 다른 API 경로로 빠진다.
- 판례 검색 본문 키는 `q`(`query` 는 400), 결정례·법령해석·행정심판 검색은 `query`. 근거는 `docs/case-search/bigcase-api.md`.
- 키체인 서비스 `case-search-bigcase`·보관 폴더 `~/.case-search/` 는 이름을 바꾸지 않는다(옛 case-search 사용자 자격증명이 이어진다).
- 실제 빅케이스는 테스트에서 부르지 않는다(가짜 HTTP). 이용 범위상 사람이 찾는 빈도로만 부른다.

## 원격(해외 판례, `foreigncase.py`)
- 독일 OpenLegalData 의 `/api/cases/?search=` 는 검색어를 무시하고 전체(425,071건)를 돌려준다 — 본문 검색은 `/api/cases/search/?text=`(2026-10-15 실측). 법원 필터는 코드(`BGH`·`OLGSL`) 또는 `court_level_of_appeal=Bundesgericht`.
- 미국 CourtListener 는 검색(`/search/?type=o`)이 익명으로 되고 본문(`/opinions/<id>/`)은 토큰이 없으면 401. `plain_text` 가 비어 있는 판결이 많아 `html_with_citations` 등을 순서대로 본다.
- 토큰은 두 고정 호스트로만 보낸다 — 주소를 인자로 받는 명령을 만들지 않는다.
- 키·토큰은 `--prompt`(입력 창) 또는 `--stdin` 으로만 받는다. 명령행 인자 자리를 두지 않는다(셸 기록·대화 기록에 남는다).

## 공유 모듈
| 모듈 | 쓰는 곳 |
|---|---|
| `_paths.py` — 경로·작업 폴더·원자 저장·금액·JSON 출력 | `skills/intent-brief/scripts/` 전부, `dday.py` (0.6.0 의 다른 스킬 스크립트·`foreigncase.py`·`bigcase.py`·site-api 는 쓰지 않고 독립 실행) |
| `state.py` — 인터뷰 상태 읽기·쓰기 | `intent`·`memo`·`check_draft`·`render_docx` |
| `check_draft` — draft.md 파싱(`parse_draft`·`split_front`) | `render_docx`(`split_front`·앵커 정규식), `dev/e2e.py` |
| `lawapi.py` — 법제처 Open API 호출·키(OC) 보관·오류 분류 | `cite_check`, SKILL.md·내장 스킬(`references/law-lookup.md` 명령) |
| `casesearch.py` — 빅케이스 감지·호출(같은 플러그인의 `bigcase.py` 를 `uv run` 으로) | `cite_check`, SKILL.md·내장 스킬 |
| `skills/case-search/scripts/foreigncase.py` — 해외 판례(미국·독일) 검색·본문·토큰 보관 | `skills/case-search/SKILL.md`, `commands/law-key-setup.md` |
| `skills/case-search/scripts/bigcase.py` — 빅케이스 로그인·토큰·검색·전문(uv inline 의존성) | `casesearch.py`, `skills/case-search/SKILL.md`, `commands/case-search-setup.md` |
| `skills/litigation-calc/scripts/deadline.py` — 기간 만료일(민법 제157·160·161조·형소법 제66조)·`IMMINENT_DAYS`·공휴일 표 | `dday.py`, litigation-calc·brainstorming-lawfirm SKILL.md |
| `skills/litigation-calc/scripts/costs.py` — 인지액·송달료 회분·지연손해금 | litigation-calc·brainstorming-lawfirm SKILL.md |
| `skills/brainstorming-lawfirm/scripts/risk.py` — 심각도×가능성 점수·정렬 표 | brainstorming-lawfirm SKILL.md |
| `skills/review-contract/scripts/playbook.py` — 사무소 플레이북 위치·기본값·init(덮지 않음) | review-contract·triage-nda SKILL.md |
| `skills/site-api/scripts/extract.py`·`scaffold.py` — API 후보 추출·클라이언트 생성(한 번 치환, 호스트 고정) | `discover.py`, site-api SKILL.md |
