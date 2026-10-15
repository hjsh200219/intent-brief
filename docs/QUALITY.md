# 품질 기준

| 영역 | 기준 | 검사 |
|---|---|---|
| 결정론 스크립트 | 공개 함수·하위 명령마다 테스트, 잘못된 입력은 상태를 바꾸지 않고 오류 JSON | `pytest tests/` |
| 받는 PC 호환 | 표준 라이브러리만, Python 3.9 문법, 한글·CRLF 경로 | `tests/test_params.py` · 3.9 로 `pytest` · `dev/smoke.py`(Windows 실기) |
| 의도 반영 | 같은 사건·다른 의도 초안이 E1–E8 을 통과(PRD §5.3) | `dev/e2e.py run` → `judge` |
| 인용 | 「확인됨」은 법제처 원문 정확 일치만(빅케이스에서만 찾은 것은 `external`), 미확인 판례에는 인용 판결 수 안내, 키 값은 출력·캐시에 남기지 않음 | `tests/test_cite.py` · `tests/test_lawapi.py` · `tests/test_casesearch.py` |
| 내장 스킬 | MCP·Cowork 경로·AskUserQuestion 없음, 안내한 명령 실존, 사용자 입력 JSON 을 셸 인자에 넣지 않음 | `tests/test_embedded_skills.py` |
| 사건메모 | 확인 토큰 없이는 쓰지 않음, CRLF 보존, casedb 형식 바이트 일치 | `tests/test_state_memo.py`(바이트 일치 계약은 데모 원본이 있는 PC 에서만 — `INTENT_BRIEF_DEMO_DIR`) |
| 매니페스트 | `validate --strict` 통과, 두 매니페스트 버전 일치 | `claude plugin validate --strict .` · `dev/verify_docs.py` |
| 문서 | 링크 유효, AGENTS.md 120줄 이하 | `dev/verify_docs.py`(pytest 가 함께 돌린다) |

e2e 판정 기준값(E3 강한 표현 수, E6 길이비 1.3 등)은 `dev/e2e.py` 의 `judge_run`·`cmd_judge` 가 정본이다.
