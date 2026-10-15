# lawfirm — 한국 변호사용 법률 업무 플러그인 (Claude Code)

민사 서면 초안, 법률 문서 초안, 판례 검색을 한 플러그인에서 합니다. `lyn-lawfirm`·`case-search`·`intent-brief` 플러그인을 0.4.0 에서 하나로 합쳤습니다(아래 「옛 플러그인에서 옮기기」).

- **의도 기반 민사 서면(`intent-brief` 스킬)**: 변호사가 이번 서면으로 얻으려는 **의도**를 먼저 정하면, 그 의도와 당사자 지위에 맞춰 민사 준비서면·답변서 초안(.docx)과 내부용 의도대응표(.docx)를 만듭니다.
  - 의도 목록: 전부 승소(W) · 손해 최소화(M) · 조정·화해 유도(S) · 상대 입장 고정·증거 제출 압박(P) · 쟁점 재구성(R) · 상소 대비 기록(A) · 의뢰인 보고(C, 부 의도 전용)
  - 결정 축 4개(의도·쟁점 태도·증거 전략·절차) 모호도 인터뷰 → 고른 의도의 소송 전체 기준 유불리 검토(그대로 갈지 변호사가 결정) → 설계 확인 표(변호사가 어느 칸이든 덮어쓰기) → 초안 → 설계 준수 검사 → 조문·판례 정확 일치 대조 → .docx
  - 어떤 의도도 거부하지 않습니다. 다만 그 의도로 소송 전체에서 놓칠 수 있는 것(예: 항소심 청구취지 확장)을 먼저 보여 드리고, 그대로 진행하시면 할 일과 의도대응표에 남깁니다. 자료에 없는 사실은 `[확인 필요: …]` 로 남깁니다.
- **법률 문서 스킬 6종**: 내용증명·고소장·형사합의서·사실확인서·형사절차 시뮬레이터·양형 예측.
- **판례·법령 검색(`case-search` 스킬)**: 세 원천을 한곳에서 찾습니다.
  - 법제처(공식 원문): 법령·조문·판례·헌재결정·법령해석례·행정규칙·법령용어
  - 빅케이스(bigcase.ai, 계정이 있을 때): 판결문 전문(하급심 포함)·유사 판례·사실관계 서술 검색·결정례·행정심판. 계정이 없으면 법제처·해외 판례만 씁니다.
  - 해외 판례: 미국(CourtListener)·독일(OpenLegalData) 검색과 판결문 본문(원문 언어)
  민사 서면의 인용 대조에도 법제처·빅케이스가 자동으로 쓰입니다.

> AI는 실수할 수 있습니다. 인용 대조의 「확인됨」은 그 조문·판례가 법제처 원문에 존재한다는 뜻이며 적합성은 보증하지 않습니다. 최종 검토와 제출 판단은 사용 변호사의 책임입니다.

## 설치

필요: Claude Code, **Python 3.9 이상**(외부 패키지 없음).

```
/plugin marketplace add hjsh200219/lawfirm
/plugin install lawfirm@lawfirm
```

Claude Code 2.1.275 이상이면 한 줄로도 됩니다: `/plugin install lawfirm --marketplace hjsh200219/lawfirm`. repo 폴더를 받아 두었다면 `claude plugin marketplace add <폴더 경로>` → `claude plugin install lawfirm@lawfirm`.

쓰는 기능에 따라 더 필요한 것:

| 기능 | 필요한 것 |
|---|---|
| 조문·판례 인용 대조, 법령·판례 조회 | 법제처 Open API 키(OC) → `/lawfirm:law-key-setup`(입력 창) — 아래 「원격 서버 의존」 |
| 빅케이스 판례 검색(선택) | [uv](https://docs.astral.sh/uv/)(macOS `curl -LsSf https://astral.sh/uv/install.sh \| sh`) + 본인 빅케이스 계정 → `/lawfirm:case-search-setup` |
| 미국 판결문 본문(선택) | CourtListener 무료 계정 API 토큰 → `/lawfirm:law-key-setup us`(검색은 토큰 없이 됩니다) |
| 형사합의서 | Node 와 `docx` 패키지(`npm install -g docx`) |

업데이트는 `/plugin` → Marketplaces → lawfirm → Update marketplace(또는 Enable auto-update). 제3자 마켓플레이스는 자동 업데이트가 기본으로 꺼져 있습니다.

## 사용

- 「이 사건 준비서면 의도부터 정해서 써 줘」 → `intent-brief` 스킬
- 「피해자에게 보낼 내용증명 써 줘」, 「사기죄 양형 예측해 줘」 → 법률 문서 스킬
- 「민법 제750조 보여 줘」, 「2016다225353 판결 전문 읽어줘」, 「부당해고 판례 찾아줘」, 「이런 사실관계와 비슷한 판례 찾아줘: …」, 「미국 adverse possession 판례」, 「독일 BGH Mietminderung 판결」 → `case-search` 스킬

## 스킬

| 스킬 | 하는 일 |
|---|---|
| `intent-brief` | 의도 기반 민사 준비서면·답변서 초안 + 의도대응표 |
| `case-search` | 판례·법령 검색 — 법제처(법령·조문·판례·헌재·법령해석례), 빅케이스(전문·유사 판례·서술문 검색·결정례/행정심판), 미국·독일 판례 |
| `certified-letter` | 내용증명 초안(.docx) |
| `complaint-drafter` | 형사 고소장 초안(.docx) |
| `criminal-settlement` | 형사 합의서(.docx, Node `docx` 패키지) |
| `fact-confirmation` | 사실확인서(.docx) |
| `criminal-procedure-simulator` | 형사절차 단계별 안내·시각화 |
| `sentencing-predictor` | 양형기준 기반 양형 예측 |

명령(키·비밀번호는 모두 입력 창으로 받고 채팅으로 받지 않습니다):
- `/lawfirm:law-key-setup` — 법제처 OC 키(인자 `us` 면 CourtListener 토큰도)
- `/lawfirm:case-search-setup` — 빅케이스 이메일·비밀번호(OS 키체인)

법률 문서 스킬 6종은 thechain.lawyer(이영남 변호사 사무소)가 배포하던 lyn-lawfirm 플러그인 스킬입니다(lyn-lawfirm `9d620a9`, MIT). 법령·판례 조회는 모두 이 플러그인의 법제처 직접 호출로 바꿨고(`references/law-lookup.md`), 산출물 끝의 변호사 안내(CTA)는 `references/cta-config.md` 를 따릅니다.

## 옛 플러그인에서 옮기기

옛 저장소(`hjsh200219/lyn-lawfirm`·`hjsh200219/case-search`)는 이전 안내만 남기고 보관(archive)했습니다. 이미 설치하신 분은 두 단계면 됩니다.

1. `/plugin` → Marketplaces → 쓰던 마켓플레이스(`lyn-lawfirm`·`case-search`·`intent-brief`) → **Update marketplace**
2. `/plugin install lawfirm@<그 마켓플레이스 이름>` — 옛 플러그인이 lawfirm 으로 바뀝니다(2026-10-15 세 경로 모두 GitHub 에서 실측)

| 쓰던 플러그인 | 이어지는 것 · 바뀌는 것 |
|---|---|
| `lyn-lawfirm` | 법률 문서 스킬 6종은 그대로 들어 있습니다. 옛 k-data MCP 법령 검색은 없어지고 법제처 직접 조회(본인 OC 키 — 처음 쓸 때 안내)로 바뀝니다. 옛 설치 명령 `install lyn-lawfirm@lyn-lawfirm` 은 이제 동작하지 않습니다. |
| `case-search` | 빅케이스 자격증명(키체인 `case-search-bigcase`, `~/.case-search/`)을 그대로 쓰므로 다시 등록하지 않아도 됩니다. 설정 명령은 `/case-search:setup` → `/lawfirm:case-search-setup` 으로 바뀌었습니다. |
| `intent-brief` | 옛 주소 `hjsh200219/intent-brief` 는 이 저장소로 연결됩니다. 작업 폴더(`~/.intent-brief/`)와 법제처 키를 그대로 씁니다. |

옛 플러그인을 둘 이상 쓰셨다면 위 2단계를 한 번만 하고, 나머지 옛 플러그인은 `/plugin uninstall <이름>@<마켓플레이스>` 로 지우십시오 — lawfirm 이 두 번 설치되면 같은 스킬이 겹칩니다. 새로 시작하려면 옛 것을 모두 지우고 위 「설치」를 따르면 됩니다.

## 지원 범위 (0.5.0)

- `intent-brief` 서면: 민사 준비서면(원고·피고), 답변서(피고). 소장·항소이유서·가사·행정은 범위 밖(형사 문서는 위 법률 문서 스킬).
- `case-search`: 법제처·빅케이스·미국·독일. LBOX 는 준비 중(정찰 자료 `docs/case-search/lbox/`).
- 환경: Claude Code on macOS·Windows. Cowork 는 아직 지원하지 않습니다.

## 데이터 위치

- 초안·대응표: 사건 폴더(지정한 폴더)에 `YYMMDD_<약칭>_<서면>_vN.docx`, `내부_…_의도대응표.docx`. 기존 파일은 덮어쓰지 않습니다.
- 인터뷰 상태·중간 초안·인용 응답·사건메모 사본: 작업 폴더 — macOS `~/.intent-brief/`, Windows `%LOCALAPPDATA%\intent-brief\`. 의뢰인 정보가 들어 있으니 끝난 사건은 지우십시오:
  `python <플러그인>/skills/intent-brief/scripts/state.py purge <사건폴더>` (전부: `--all`). 플러그인을 지워도 이 폴더는 남습니다.
- 사건 폴더에 `사건메모.md`(업무관리 하네스 형식)가 있으면 진행 경과·할 일을 diff 확인 후 기록합니다. 없으면 기록하지 않습니다.
- 빅케이스: 이메일 `~/.case-search/bigcase/config.json`(0600) · 비밀번호 OS 키체인(서비스 `case-search-bigcase`) · 토큰 `~/.case-search/bigcase/session.json`(0600). 환경변수 `BIGCASE_ID`/`BIGCASE_PW` 가 있으면 키체인보다 우선하고, `CASE_SEARCH_HOME` 으로 보관 폴더를 바꿉니다. 지우기: `uv run <플러그인>/skills/case-search/scripts/bigcase.py forget`.
- 해외 판례 토큰: `~/.case-search/foreign.json`(0600). 환경변수 `COURTLISTENER_API_TOKEN` 이 있으면 먼저 씁니다. 지우기: `python <플러그인>/skills/case-search/scripts/foreigncase.py key clear us`.

## 원격 서버 의존

조문·판례 대조는 **법제처 Open API 를 직접** 부릅니다(중계 서버·MCP 없음). 각자 자기 키(OC)가 필요합니다 — https://open.law.go.kr 에서 회원가입 → OPEN API 사용 신청(법령·판례)을 하고 받은 OC 값을 `/lawfirm:law-key-setup` 이 띄우는 입력 창에 넣으면 판례 1건으로 확인한 뒤 작업 폴더의 config.json(본인만 읽기)에 저장합니다(채팅에 적지 않습니다). 신청 때 이 PC 의 IP 주소 등록을 요구할 수 있습니다. 환경변수 `INTENT_BRIEF_LAW_OC`·`LAW_API_OC` 가 있으면 그 값을 먼저 씁니다. 법제처가 응답하지 않으면 초안 작성은 계속되고 인용에 `[법제처 장애 — 미확인]` 이 붙습니다.

**빅케이스 자동 연결**: `/lawfirm:case-search-setup` 으로 빅케이스에 로그인해 두면 민사 서면 인용 대조에도 따로 설정 없이 연결됩니다. 법제처에 원문이 없는 판례(예: 2014다26187)는 빅케이스에서 같은 사건번호를 한 번 찾아 「빅케이스 확인」으로 표시하고(「확인됨」과 구분), 쟁점 정리 때 판례 후보 검색에도 씁니다.

**해외 판례**: 미국 CourtListener(Free Law Project)·독일 OpenLegalData 공개 API 를 직접 부릅니다. 검색은 둘 다 익명으로 되고, 미국 판결문 본문만 CourtListener 토큰이 필요합니다. 본문은 번역 없이 원문 언어로 8,000자씩 이어 읽습니다.

**빅케이스 이용 범위**: 본인 빅케이스 계정으로, 사람이 화면에서 찾는 정도의 빈도로만 씁니다. 로그인 토큰은 `https://bigcase.ai` 로만 보내고 다른 주소로 가는 요청은 거부합니다. 대량 수집·페이지 끝까지 넘기기·재배포는 하지 않습니다. 로그인하지 않으면 하급심 판결은 이유가 앞부분만 오고(`restricted`), 주석서 본문·양형 통계는 계정 권한이 없으면 403 이라 명령을 두지 않았습니다.

## 개발

```
uv run --no-project --with pytest --with python-docx==1.2.0 pytest tests/
uv run --no-project --with "scrapling[fetchers]>=0.4.11" --with keyring --with pytest --with python-docx==1.2.0 pytest tests/case_search -q
```
민사 서면 런타임 스크립트(`skills/intent-brief/scripts/`)는 표준 라이브러리만 씁니다(테스트로 확인). 빅케이스 스크립트(`skills/case-search/scripts/bigcase.py`)는 uv inline 의존성(Scrapling·keyring)을 씁니다. API 형식 근거·실측 기록은 `docs/case-search/bigcase-api.md`. `dev/` 는 개발 전용입니다. 개발 지도·불변 조건은 [AGENTS.md](AGENTS.md).

## 변경 이력

- **0.5.0 (2026-10-15)** — case-search 에 법제처 조회(법령·조문·판례·헌재결정·법령해석례·행정규칙·용어)와 해외 판례(미국 CourtListener·독일 OpenLegalData)를 넣었습니다. 빅케이스 계정이 없으면 법제처·해외 판례만 씁니다. 법제처 키·CourtListener 토큰을 `/lawfirm:law-key-setup` 입력 창으로 받아 저장합니다(명령행 인자로 받던 경로는 없앴습니다).
- **0.4.0 (2026-10-15)** — 이름을 intent-brief 에서 lawfirm 으로 바꾸고 case-search(빅케이스 판례 검색)를 합쳤습니다. 옛 lyn-lawfirm·case-search·intent-brief 설치본은 마켓플레이스 업데이트로 옮겨 옵니다. 빅케이스 토큰을 bigcase.ai 밖으로 보내지 않게 막았고, 한국어 Windows 콘솔(cp949)에서 판례 조회 결과가 깨지던 문제를 고쳤습니다.
- **0.3.0 (2026-10-15, 중간판 0.2.0 과 함께 공개)** — 의도 유불리 검토 라운드(0.2.0), 법제처 Open API 직접 호출(k-data MCP 폐지), 빅케이스 자동 연결, 법률 문서 스킬 6종 내장.
- **0.1.0 (2026-10-14)** — 의도 기반 민사 준비서면·답변서 첫 공개.

## 라이선스

MIT
