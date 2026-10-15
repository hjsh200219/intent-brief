# intent-brief — 의도 기반 민사 서면 작성 (Claude Code 플러그인)

변호사가 이번 서면으로 얻으려는 **의도**를 먼저 정하면, 그 의도와 당사자 지위에 맞춰 민사 준비서면·답변서 초안(.docx)과 내부용 의도대응표(.docx)를 만듭니다.

- 의도 목록: 전부 승소(W) · 손해 최소화(M) · 조정·화해 유도(S) · 상대 입장 고정·증거 제출 압박(P) · 쟁점 재구성(R) · 상소 대비 기록(A) · 의뢰인 보고(C, 부 의도 전용)
- 결정 축 4개(의도·쟁점 태도·증거 전략·절차) 모호도 인터뷰 → 고른 의도의 소송 전체 기준 유불리 검토(그대로 갈지 변호사가 결정) → 설계 확인 표(변호사가 어느 칸이든 덮어쓰기) → 초안 → 설계 준수 검사 → 조문·판례 정확 일치 대조 → .docx
- 어떤 의도도 거부하지 않습니다. 다만 그 의도로 소송 전체에서 놓칠 수 있는 것(예: 항소심 청구취지 확장)을 먼저 보여 드리고, 그대로 진행하시면 할 일과 의도대응표에 남깁니다. 자료에 없는 사실은 `[확인 필요: …]` 로 남깁니다.

> AI는 실수할 수 있습니다. 인용 대조의 「확인됨」은 그 조문·판례가 법제처 원문에 존재한다는 뜻이며 적합성은 보증하지 않습니다. 최종 검토와 제출 판단은 사용 변호사의 책임입니다.

## 설치

필요: Claude Code, **Python 3.9 이상**(외부 패키지 없음). 형사합의서 스킬은 Node 와 `docx` 패키지(`npm install -g docx`)도 필요합니다.

```
/plugin marketplace add hjsh200219/intent-brief
/plugin install intent-brief@intent-brief
```

repo 폴더를 받아 두었다면 로컬 경로로도 설치할 수 있습니다: `claude plugin marketplace add <폴더 경로>` → `claude plugin install intent-brief@intent-brief`.

사용: 「이 사건 준비서면 의도부터 정해서 써 줘」처럼 요청하면 `intent-brief` 스킬이 시작됩니다.

## 스킬

| 스킬 | 하는 일 |
|---|---|
| `intent-brief` | 의도 기반 민사 준비서면·답변서 초안 + 의도대응표 |
| `certified-letter` | 내용증명 초안(.docx) |
| `complaint-drafter` | 형사 고소장 초안(.docx) |
| `criminal-settlement` | 형사 합의서(.docx, Node `docx` 패키지) |
| `fact-confirmation` | 사실확인서(.docx) |
| `criminal-procedure-simulator` | 형사절차 단계별 안내·시각화 |
| `sentencing-predictor` | 양형기준 기반 양형 예측 |

`intent-brief` 밖의 6개는 thechain.lawyer(이영남 변호사 사무소)가 배포하던 lyn-lawfirm 플러그인 스킬을 내장한 것입니다(lyn-lawfirm `9d620a9`, MIT). 법령·판례 조회는 모두 이 플러그인의 법제처 직접 호출로 바꿨고(`references/law-lookup.md`), 산출물 끝의 변호사 안내(CTA)는 `references/cta-config.md` 를 따릅니다.

## 지원 범위 (0.3.0)

- `intent-brief` 서면: 민사 준비서면(원고·피고), 답변서(피고). 소장·항소이유서·가사·행정은 범위 밖(형사 문서는 위 내장 스킬).
- 환경: Claude Code on macOS·Windows. Cowork 는 아직 지원하지 않습니다.

## 데이터 위치

- 초안·대응표: 사건 폴더(지정한 폴더)에 `YYMMDD_<약칭>_<서면>_vN.docx`, `내부_…_의도대응표.docx`. 기존 파일은 덮어쓰지 않습니다.
- 인터뷰 상태·중간 초안·인용 응답·사건메모 사본: 작업 폴더 — macOS `~/.intent-brief/`, Windows `%LOCALAPPDATA%\intent-brief\`. 의뢰인 정보가 들어 있으니 끝난 사건은 지우십시오:
  `python <플러그인>/skills/intent-brief/scripts/state.py purge <사건폴더>` (전부: `--all`). 플러그인을 지워도 이 폴더는 남습니다.
- 사건 폴더에 `사건메모.md`(업무관리 하네스 형식)가 있으면 진행 경과·할 일을 diff 확인 후 기록합니다. 없으면 기록하지 않습니다.

## 원격 서버 의존

조문·판례 대조는 **법제처 Open API 를 직접** 부릅니다(중계 서버·MCP 없음). 각자 자기 키(OC)가 필요합니다 — https://open.law.go.kr 에서 회원가입 → OPEN API 사용 신청(법령·판례)을 하고 받은 OC 값을 처음 실행 때 알려 주시면 작업 폴더의 config.json(본인만 읽기)에 저장합니다. 신청 때 이 PC 의 IP 주소 등록을 요구할 수 있습니다. 환경변수 `INTENT_BRIEF_LAW_OC`·`LAW_API_OC` 가 있으면 그 값을 먼저 씁니다. 법제처가 응답하지 않으면 초안 작성은 계속되고 인용에 `[법제처 장애 — 미확인]` 이 붙습니다.

**case-search(빅케이스) 자동 연결**: case-search 플러그인이 설치되고 빅케이스에 로그인돼 있으면 따로 설정하지 않아도 연결됩니다. 법제처에 원문이 없는 판례(예: 2014다26187)는 빅케이스에서 같은 사건번호를 한 번 찾아 「빅케이스 확인」으로 표시하고(「확인됨」과 구분), 쟁점 정리 때 판례 후보 검색에도 씁니다. 본인 빅케이스 계정으로만, 사람이 찾는 정도의 빈도로 부릅니다. 실행에는 `uv` 가 필요합니다(case-search 와 같음).

## 개발

```
uv run --no-project --with pytest --with python-docx==1.2.0 pytest tests/
```
런타임 스크립트(`skills/intent-brief/scripts/`)는 표준 라이브러리만 씁니다(테스트로 확인). `dev/` 는 개발 전용입니다. 개발 지도·불변 조건은 [AGENTS.md](AGENTS.md).

## 라이선스

MIT
