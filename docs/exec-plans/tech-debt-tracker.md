# 기술 부채

| ID | 내용 | 영향 | 해소 조건 |
|---|---|---|---|
| TD-001 | 생성 docx 를 Word·한글로 연 확인이 없다(LibreOffice → PDF 렌더로만 확인, 2026-10-14) | 서식이 Word·한글에서 다르게 보일 수 있음 | Word 또는 한글이 있는 PC 에서 F1 산출물을 열어 확인 |
| TD-002 | e2e F2·F3 판정은 결함 수정 전 코드로 돌린 결과다(수정 뒤에는 F1×6 + 단위 테스트로 재확인) | F2·F3 경로 회귀를 e2e 로는 못 봤음 | `dev/e2e.py run --only F2A F2B F3` 재실행 후 `judge` |
| TD-003 | 재생 기록(`replay.py`)의 질문 `options` 가 빈 배열이다(재생은 답 파일로 진행하므로 구조상 비어 있음) | 선택지 품질은 실제 대화 기록으로만 볼 수 있음 | 실제 대화 기록을 재생 입력으로 쓰는 경로가 생기면 |
| TD-005 | 기본값·의도 목록은 사용 통계 없이 정했다 | 실제 사무소 사용과 어긋날 수 있음 | 공개(2026-10-14) 4주 뒤인 2026-11-11 이후 `intent.py stats` 로 판단(PRD 의 4주 점검 결정) |
| TD-006 | Cowork 미지원 | Cowork 사용자는 쓸 수 없음 | 작업 폴더·스크립트 실행 경로를 Cowork 에서 확인 |
| TD-007 | e2e(E1–E8)를 0.3.0 변경(의도 유불리 검토·법제처 직접 호출·빅케이스 연결) 뒤 다시 돌리지 않았다 — `claude -p` 15회 과금이라 사용자 승인 대기 | 검토 라운드가 낀 실제 대화 흐름의 회귀를 e2e 로는 못 봤음(단위·smoke 로만) | 승인 뒤 `dev/e2e.py run` → `judge` |
| TD-008 | 내장 스킬 3개(certified-letter·complaint-drafter·fact-confirmation)가 외부 「docx 스킬」·`npm install -g docx` 를 전제하고, `generate.js` 에 테스트가 없다(2026-10-15 GC) | Node·docx 가 없는 PC 에서 문서 생성 실패 | intent-brief `render_docx.py` 로 옮기거나 Node 의존을 설치 안내·실행 테스트로 묶는다 |
| TD-009 | 공백 정규화(`_nows`·`_norm_no`·casesearch 인라인)와 키 검증 사건번호·오류 매핑이 모듈마다 중복(2026-10-15 GC F4·F5) | 규칙이 한쪽만 바뀔 수 있음 | `_paths` 로 모으고 `lawapi` 의 검증 함수 하나를 `cite_check ping` 이 쓰게 |
| TD-010 | `dev/verify_docs.py` 가 루트 `references/`·`skills/*/SKILL.md` 의 경로를 검사하지 않는다(2026-10-15 GC) | 내장 스킬 문서의 낡은 경로를 테스트가 못 잡음 | 검사 대상에 추가 |
