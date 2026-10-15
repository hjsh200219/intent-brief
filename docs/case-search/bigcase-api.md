# 빅케이스(bigcase.ai) API

2026-10-15 bigcase.ai Next.js 번들(`_app-*.js` · `pages/login-*.js`)에서 발굴하고 실계정으로 실측했다.
번들이 바뀌면 `_next/static/chunks/pages/_app-*.js` 에서 `unified-signin`·`/auth/renew`·`/esapi/cases/search` 를 다시 찾는다.

- API 기준 주소: `https://bigcase.ai/api/v1` (axios `baseURL:"/api/v1"`, `withCredentials`)
- 인증 헤더: `Authorization: Bearer <accessToken>` (accessToken 은 JWT, `exp` 로 만료 판정)

## 로그인

```
POST /api/v1/auth/unified-signin
{"email": "...", "password": "..."}
```
- 200 `{signInStatus, accountType, user, accessToken, refreshToken}` · 쿠키 `sid`
- `signInStatus` 값: `normal`·`exist-intg`·`early-bird`·`not-exist-intg`·`integrated`·`not-intg-exist`·`not-intg-no-exist`·`same-email-exist`.
  프론트는 `normal`·`not-exist-intg`·`integrated` 일 때만 로그인 성공으로 보고 나머지는 계정 통합 화면으로 보낸다.
- 캡차 없음.

## 갱신

```
POST /api/v1/auth/renew
{"refreshToken": "..."}
```
- 200 `{accessToken, refreshToken}` · 틀린 refreshToken 은 401(실측).

## 판례 검색

```
POST /api/v1/esapi/cases/search
{"q": "사기", "page": 1, "complete": "1"}
```
- 200 `{complete, result_count, results[10], keywords, cluster_keywords, direct_count, direct_results}`
- `results[]` 필드: `case_id, case_expression, case_number, court, case_type, outcome, level, paragraph(<KEYWORD> 강조), flag, opened, isExistAiSummary, ai_brief_summary_md, myDocuments`
- 검색어 키는 `q` 다(`query` 는 400 「검색어를 입력해주세요」). 기간을 주면 프론트는 `s_date`·`e_date` 와 `period: 4` 를 함께 보낸다.
- 판례 화면: `https://bigcase.ai/cases/<법원>/<사건번호>` (URL 인코딩, 200 실측)

## 판례 상세(전문)

```
GET /api/v1/esapi/cases/match_view?case_number=2022고합240&court=수원지방법원 성남지원
```
- 번들 `_app-*.js` 의 판례 화면 호출. 프론트는 `from`·`fromSimilar` 도 보내지만 없어도 된다(2026-10-15 실측 200).
- 200 `{case_expression, outcome, judgment_date, pub_info, holdings, summary, ref_laws, ref_cases, fulltext{body_court, body_infos[{item,content}], disposition, claim[], reasoning, judges, comments[]}, history_cases[], following_cases[], attached[{title, files[]}], attached_text, literature_info[], restricted, ai_summary, ...}`
- `ref_laws`·`ref_cases` 에는 `<law_cite ref=...>`·`<case_cite ref=...>` 태그가 섞여 온다. `attached` 는 별지·증거목록 이미지 파일 이름뿐이다.
- 비로그인이면 하급심은 `restricted: true` 이고 `reasoning` 이 앞부분(약 350자)만 온다. 대법원 공개 판결은 비로그인도 전문(2026-10-15 실측: 수원지법 성남지원 2022고합240 로그인 6,803자 / 비로그인 350자).
- 화면 SSR(`/cases/<법원>/<사건번호>` 의 `__NEXT_DATA__.props.pageProps.caseDetail`)도 같은 값이다. SSR 은 Bearer 헤더가 아니라 `accessToken` 쿠키로 로그인을 판정한다.

## 유사 판례·서술문 검색·결정례 (2026-10-15 실측)

```
GET  /api/v1/esapi/cases/similar/search/v2?case_number=&court=     → {results[50]} (ranking, paragraph 포함)
POST /api/v1/esapi/brief/search/v2 {text, type:"cases"|"laws", page, itemsperpage:10, index:"cases_small_avg", model:"lawbert_small"}
     → {user_text, type, result_count, results[10], activityId}
POST /api/v1/{decision-cases|regulation-interpretations|administrative-appeals}/searchList {query, page}
     → {total_count, datas[10]{id, title, i_code, highlight, date, organizationName}}
GET  /api/v1/<같은 종류>/view/<id> → {id, title, date, organizationName, filepath(원문 PDF, cdn.lawcompany.co.kr)}
```
- similar 응답은 호출마다 두 가지 중 하나다(2026-10-15 99도4797 로 8회: 4회씩). 한쪽에만 사건 하나(2014고정1781)가 1위로 끼고 나머지 49건은 같다 — 서버 쪽 변동으로 보이며 `ranking` 은 각 응답 안에서 1부터 이어진다. 순위 1~2위가 바뀔 수 있음을 감안해 읽는다.
- brief 는 화면의 「문서로 검색」이다. 프론트는 Plus 구독·인증 회원에게만 버튼을 열지만 API 는 멤버십 없는 계정(`/users/valid-memberships` → hasMembership false)에서도 200 이었다. 서술문으로 수원지법 성남지원 2022고합240 을 1위로 찾았다.
- `type:"laws"` 결과는 `section`(조문 XML 태그 포함)·`law_name`·`section_name` 이다.
- 결정례 계열 검색 키는 `query` 다(`q` 는 400). `total_count` 는 300 에서 멈춘다(상한으로 보임).
- searchList 는 결정례·법령해석·행정심판만 실측했다. 번들의 `{e}s/searchList` 형식이라 다른 종류도 있을 수 있다.

## 그 밖에 번들에 보이는 경로

2026-10-15 전체 청크(112개)에서 API 호출 170건을 뽑았다. 읽기 전용으로 실측한 것:
- 200: `/esapi/cases/cluster/search?q=`(쟁점 묶음, 키워드 품질 낮음) · `/esapi/cases/ai_summary?case_number=&court=&type=` · `/esapi/cases/literature/view?case_number=&court=`(판례 관련 문헌, match_view 의 literature_info 와 같음) · `POST /esapi/law/search {q,page}` · `/esapi/law/match_view?law_name=&section_num=제347조`(조문·개정이유) · `/esapi/law/view_law_history?law_id=&sort_type=1` · `POST /commentaries/search {q,page}`(주석서 목차·발췌) · `/literatures/search?q=&page=`(논문 서지, 원문 링크는 DBpia·`price` 필드 있음) · `/legal-forms`(서식 3,831건) · `/esapi/main/input?q=`(자동완성)
- 403: `/sentencing-statistics/*`(양형 통계, 권한 `sentencing-statistics:read` 없음) · `/commentaries/<id>`·`/commentaries/<id>/viewer`(주석서 본문, 권한 `commentary:read` 없음 — 라이브러리 구독 계정에서만 열릴 것으로 보임)
- `/my-documents/folders`(GET) 200.
- 쓰기·결제·계정 경로(`/court-dates/*` 기일 관리, `/my-documents`, `/highlights`, `/subscriptions/*` 등)는 호출하지 않았다.
