---
name: case-search
description: 판례 검색 서비스에 브라우저 없이 로그인하고(Scrapling) 판례를 검색한다. 지금은 빅케이스(bigcase.ai) — 로그인·토큰 재사용·판례 검색·판결문 전문·유사 판례·서술문 검색·결정례/법령해석/행정심판·인증 API 호출. LBOX 는 준비 중. 트리거 — "/lawfirm:case-search", "빅케이스", "bigcase", "빅케이스 로그인", "판례 검색", "판례 찾아줘", "사건번호 찾아줘", "판결문 전문", "판결 전문 읽어줘", "판결 이유", "유사 판례", "비슷한 판례", "행정심판", "법령해석", "결정례", "빅케이스 토큰". 자격증명이 없으면 그 자리에서 setup 을 실행한다.
argument-hint: "[search <검색어>|case <법원> <사건번호>|similar|brief|decisions|status|login|token|get|post|setup|forget]"
allowed-tools: Bash(uv run:*)
---

# case-search — 판례 검색 로그인·검색

빅케이스 명령은 `uv run "${CLAUDE_PLUGIN_ROOT}/skills/case-search/scripts/bigcase.py" <명령>` 이다(Windows 도 같음). 아래에서는 `BC` 로 줄여 쓴다.

| 명령 | 하는 일 | 네트워크 |
|---|---|---|
| `BC status` | 등록 상태(이메일·비밀번호 저장 여부·토큰 남은 시간). 값은 출력 안 함 | 없음 |
| `BC setup [--email E] [--force]` | 자격증명 등록 — 로그인 1회로 확인한 뒤에만 키체인에 저장 | 로그인 |
| `BC login` | 저장 토큰을 무시하고 새로 로그인, 계정 요약(토큰 제외) | 로그인 |
| `BC search <검색어> [--page N] [--raw]` | 판례 검색 — `{total, results[10]}`(사건 표시·사건번호·법원·종류·결과·화면 URL). `--raw` 는 응답 원본(본문 발췌 `paragraph` 포함) | POST |
| `BC case <법원> <사건번호>` · `BC case <판례 URL>` | 판결문 전문 Markdown — 판시사항·판결요지·참조조문·당사자·주문·이유·판사·첨부 목록·심급. `--raw` 는 응답 원본 JSON. 법원명에 공백이 있어도 마지막 인자를 사건번호로 본다 | GET |
| `BC similar <법원> <사건번호> [--limit N]` | 유사 판례(빅케이스가 고른 최대 50건 중 상위 N, `ranking` 포함) | GET |
| `BC brief <사건 서술문> [--laws]` · `echo … \| BC brief -` | 사실관계 서술로 비슷한 판례 찾기(화면의 「문서로 검색」). `--laws` 는 관련 법령 조문 | POST |
| `BC decisions <결정례\|법령해석\|행정심판> <검색어>` · `BC decision <종류> <id>` | 위원회 결정례·부처 법령해석·행정심판 재결 검색(제목·날짜·기관·요지 발췌) / 원문 PDF 주소 | POST·GET |
| `BC get <경로>` · `BC post <경로> --json '{...}'` | `/api/v1` 아래 인증 요청(API 탐색용) | GET·POST |
| `BC token` | 유효한 accessToken 만 출력 | 필요 시 갱신 |
| `BC forget` | 키체인 항목·설정·토큰 파일 삭제 | 없음 |

## 절차

1. 처음이거나 `✗ 등록된 빅케이스 계정이 없습니다` 가 나오면 `/lawfirm:case-search-setup` 절차(`commands/case-search-setup.md`)를 그대로 따른다. **비밀번호를 채팅으로 받지 않는다.**
2. 판결 전문·이유·판시사항 요청이면 `BC case <법원> <사건번호>` 로 받는다(검색 결과의 `court`·`case_number` 를 그대로 쓴다). 출력이 길면 파일로 저장해 필요한 절만 읽는다. stderr 에 `restricted=true` 가 나오면 본문이 잘린 것이니 그대로 알린다. 첨부(별지·증거목록)는 이미지라 받지 않는다.
3. 사실관계를 주고 비슷한 판례를 찾으라면 `BC brief` 를, 특정 판례와 비슷한 판례면 `BC similar` 를 쓴다. 행정심판·법령해석·위원회 결정례는 `BC decisions`.
4. 검색 요청이면 `BC search <검색어>` 를 실행하고 결과를 표로 요약한다(사건 표시·결과·URL). 총 건수를 함께 적는다. 다음 페이지는 `--page`.
5. 토큰은 `~/.case-search/bigcase/session.json` 에 저장돼 재사용된다. 만료 60초 전이면 갱신, 갱신 실패면 재로그인, 401 이면 1회 재시도한다 — 직접 다시 로그인시키지 않는다.
6. `token` 출력값은 비밀이다. 사용자가 요청할 때만 실행하고, 대화·파일·커밋에 옮겨 적지 않는다.

## 주의

- 각자 자기 빅케이스 계정으로만 쓴다. 대량 수집·재배포·다른 서비스의 데이터 소스로 쓰지 않는다(약관·저작권법 §93 DB제작자 권리).
- 검색은 사람이 화면에서 하는 정도의 빈도로만 부른다. 페이지를 반복문으로 끝까지 넘기지 않는다.
- API 형식 근거와 미실측 경로는 `${CLAUDE_PLUGIN_ROOT}/docs/case-search/bigcase-api.md`. LBOX 정찰 자료는 `docs/case-search/lbox/`.
