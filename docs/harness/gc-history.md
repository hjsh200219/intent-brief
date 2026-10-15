# GC 이력

`/sh:harness-gc` 실행 결과를 최신이 위로 쌓는다. 형식은 sh 플러그인 `harness-gc` 의 「GC 히스토리 업데이트」를 따른다.

## 2026-10-15 (Run #1)
- 모드: quick(git-push 편승 — 감사 3개 병렬, 결과 통합 생략). 결함·즉시 수정 항목은 같은 push 에서 직접 고침
- 문서 신선도: 97.1%(305/314) → 즉시 수정 8건 반영
- 아키텍처 준수율: 83%(15/18) → 장애 내성 결함 F1·F2·F3·F7·F12 수정(테스트 6건 추가), 문서 F8·F9 반영
- 품질 등급: B+ (런타임 B+ · SKILL A- · 내장 스킬 C+ · 테스트 A- · 문서 B+)
- 하네스 성숙도: L3 (63.7점) — A: 7.00 / B: 6.67 / C: 6.33 / D: 5.00
- 약점 원칙: P7 (3점), P3 (6점), P6 (6점)
- Knip strict: 해당 없음(Python)
- 발견 이슈: 즉시 수정 15건 적용, 수동 검토는 tech-debt TD-007~010 로 등록
- 반복 드리프트: 없음(첫 실행)
- 예방 스크립트 생성/갱신: N (TD-010 로 verify_docs 범위 확장 예정)
- 하네스 메타 검증: 해당 없음 (3회 미만)
- 정책 스킵: 없음

## 2026-10-15 (Run #2)
- 모드: quick(git-push 편승, 범위 origin/main..HEAD 21커밋 — 0.6.0 새 스킬 6개·세션 시작 훅)
- 문서 신선도: 98% (유효 참조 163 / 166, 나머지 3건은 스킬 폴더 기준 상대 경로·작업 폴더 산출물)
- 아키텍처 준수율: 100% (최상위 import 76 / 76, 교차 의존은 L3d·L3e 허용 범위)
- 품질 등급: 평균 B (litigation-calc B+, site-api B-, 내장 문서 스킬 C+)
- 하네스 성숙도: L3 (56.6점) — A: 6.75 / B: 5.33 / C: 5.67 / D: 4.50
- 원칙별: P1 8 · P2 7 · P3 6 · P4 6 · P5 6 · P6 5 · P7 3 · P8 6 · P9 6 · P10 4 · P11 6 · P12 6 (Run #1 63.7 대비 -7.1 은 회귀가 아니라 앵커 엄격 적용 재채점 — 테스트 310 → 315 통과 유지)
- 약점 원칙: P7 (3점, GC 자동화 없음 — `/sh:harness-setup --infra` 대상), P10 (4점, lock 없음 TD-014), P6 (5점, 커버리지 게이트 없음)
- Knip strict: 해당 없음(Python)
- 발견 이슈: 18건 (즉시 수정 12: README 플레이북 파일명·AGENTS 공휴일 경로·dev 목록·harness-setup `_paths` 쓰는 곳·3.9 범위·출력 규칙 예외, verify_docs 에 새 SKILL.md 7개 추가, permissions.deny 에 `~/.intent-brief/config.json`·`~/.case-search/**`, doc_text UTF-16 DTD 우회 차단, dday 기간 줄 끝 날짜·시간 예산, discover robots 읽기 실패 시 중단·응답 파싱 실패 기록, scaffold 기본값 상수 / 수동 검토 6: work_root 복제는 L3d 독립 실행 때문에 유지하고 일치 테스트로 고정, LAWFIRM_SITE_API_DIR·LAWFIRM_SITE_HOME 분리는 의도(생성 파일 위치와 세션 위치), lock 파일 TD-014, ADR 없음, PRD 정본 repo 밖(AGENTS 명시), 내장 문서 스킬 산출 동작 테스트 없음 TD-008)
- 반복 드리프트: 문서 경로 표기(Run #1 F-series 와 같은 유형) → verify_docs 검사 대상을 넓혀 예방
- 예방 스크립트 생성/갱신: Y(`dev/verify_docs.py` DOCS 확장, `tests/test_dday.py` 작업 폴더 경로 일치·stdlib 검사)
- 하네스 메타 검증: 해당 없음 (3회 미만)
- 정책 스킵: 없음
