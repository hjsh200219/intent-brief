# ARCHITECTURE — intent-brief

## 흐름

```
변호사 요청 → SKILL.md(모델) ─┬─ state.py   인터뷰 상태 저장·재개·purge
                              ├─ score.py   결정 축 4개 모호도 채점 → 다음 질문
                              ├─ intent.py  의도 검증·resolve → design.json · stats
                              ├─ memo.py    사건메모 읽기·diff 미리보기·확인 토큰 반영
                              ├─ (모델이 draft.md 작성)
                              ├─ check_draft.py  design.json 준수 검사
                              ├─ cite_check.py   조문·판례를 k-data 원문과 정확 일치 대조
                              └─ render_docx.py  초안·의도대응표 .docx
```

모델이 판단할 일(인터뷰 문장, 초안 본문)과 결정론으로 끝낼 일(채점, 설계 해석, 준수 검사, 인용 대조, 렌더)을 나눈다. 결정론 쪽은 전부 스크립트이고 테스트가 있다.

## 레이어

| 레이어 | 위치 | 의존해도 되는 것 |
|---|---|---|
| L0 매니페스트 | `.claude-plugin/`, `.mcp.json` | 없음 |
| L1 데이터 | `skills/intent-brief/references/` | 없음 |
| L2 절차 | `skills/intent-brief/SKILL.md` | L1, L3(명령으로 호출), L0의 MCP |
| L3 런타임 | `skills/intent-brief/scripts/` | 표준 라이브러리, L1, L0(`.mcp.json` URL), 같은 레이어 |
| L4 개발 | `dev/`, `tests/` | 전부 |

L3 안의 방향: `_paths` ← `state` ← `intent`·`memo`·`check_draft` ← `render_docx`(`state` 는 각 파일 함수 안에서 지연 import). `score`·`cite_check` 는 `_paths` 만 쓴다. L3 는 L4 를 import 하지 않는다. 이 표는 `tests/test_params.py` 의 `test_runtime_import_direction` 이 강제한다.

## 교차 관심사

- **경로·저장**: `_paths.py` 하나 — 작업 폴더·사건 키 결정, 원자 저장(임시 파일 → 교체), 해시, 금액 표기·파싱, JSON 출력. 원격 URL 은 `cite_check.py` 가 `.mcp.json` 에서 읽는다.
- **재현성**: `INTENT_BRIEF_TODAY`(`_paths.today()` 의 「오늘」 고정 — 테스트·재생), `INTENT_BRIEF_MCP_URL`(가짜 서버, 개발·테스트 전용).
- **원격 장애**: `cite_check.py` 가 인자 오류와 서버 장애를 나눈다(한글 「파라미터가 필요합니다」는 인자 오류). 장애여도 초안 작성은 계속한다.
- **개인정보**: 사건 자료는 작업 폴더와 사건 폴더에만 남는다. `state.py purge` 로 지운다.
