# 개선 액션 카탈로그

| 원칙 | 증상 | 조치 |
|---|---|---|
| P1 | 진입 문서 낡음 | AGENTS.md 지도·불변 조건 갱신. Claude Code 연결은 `.claude/CLAUDE.md`=`@../AGENTS.md` — 루트 `CLAUDE.md` 는 `plugin validate --strict` 경고(플러그인 루트 CLAUDE.md 는 로드 안 됨)로 실패한다 |
| P2 | 깨진 링크·고아 문서·없는 파일명 | `python3 dev/verify_docs.py`(pytest 가 함께 돈다) |
| P3 | 규칙이 문서에만 있음 | `tests/` 의 검사로 옮기고 문서에서는 링크만 남긴다(예: 표준 라이브러리·3.9 문법 검사) |
| P6 | L3 가 L4 를 import, 순환 | ARCHITECTURE.md 레이어 표를 고치고 `test_runtime_import_direction` 의 허용 표를 같이 고친다 |
| P8 | 원격 실패가 삼켜짐 | `lawapi.py`·`casesearch.py` 가 `no_key`·`key_invalid`·`outage`·`format_changed`(빅케이스는 `SearchError`)로 나누고 `cite_check.py` 결과에 남긴다 |
| P10 | 「오늘」·원격 응답에 따라 테스트가 흔들림 | `INTENT_BRIEF_TODAY` 고정, `tests/recorded/` 녹화 응답 |
| P11 | SKILL.md 가 결정론 판단을 직접 함 | 스크립트로 옮기고 SKILL.md 는 명령 호출만 |
