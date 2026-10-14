---
name: intent-brief
description: "변호사가 이번 민사 준비서면·답변서로 얻으려는 의도(전부 승소·손해 최소화·조정 유도·상대 입장 고정·쟁점 재구성·상소 대비 기록)를 인터뷰로 고정하고, 그 의도에 맞춘 초안 .docx 와 내부용 의도대응표 .docx 를 만든다. 조문·판례 인용은 법제처 원문과 정확 일치로 대조한다. 트리거: '준비서면', '답변서', '서면 의도', '의도 맞춰 서면', '준비서면 초안', '답변서 초안', 'intent-brief'. 소장·항소이유서·형사 의견서는 범위 밖."
---

# intent-brief — 의도 기반 민사 서면 작성

변호사는 늘 「전부 승소」만 원하지 않는다. 이 스킬은 **서면의 의도를 먼저 묻고**, 의도와 당사자 지위에 맞춰 섹션 구성·쟁점별 태도·강도·어조·분량·결론을 정한 뒤 초안을 쓴다. 사용자는 변호사다 — 실무 용어로 짧게 묻는다.

원칙
- 주 의도가 정해지지 않으면 초안을 쓰지 않는다. 「전부 승소」로 채우지 않는다.
- 사실은 자료에서 읽고 판단만 묻는다. 자료에 없는 사실은 초안에 `[확인 필요: …]` 로 남기고 묻지 않는다.
- 어떤 의도도 거부·경고하지 않는다. 이 스킬에는 검수 게이트가 없다.
- 결정(해석·채점·검사·인용 대조·사건메모 쓰기·docx)은 스크립트가 한다. 모델은 질문하고, 답을 구조화하고, 초안을 쓴다.
- 사건 폴더에는 초안 .docx 와 `내부_` 로 시작하는 대응표(·의뢰인 보고)만 만든다. 상태·중간 파일은 작업 폴더(아래)에 있다.

## 0. 런타임

- 스크립트 위치: 이 SKILL.md 가 있는 폴더(스킬을 불러올 때 표시되는 기준 경로) 아래 `scripts/`. 아래에서 `$S` 는 그 `scripts` 폴더의 절대경로다. 플러그인으로 설치됐다면 `${CLAUDE_PLUGIN_ROOT}/skills/intent-brief/scripts` 와 같다.
- Python 3.9 이상이 필요하다(외부 패키지 없음). 처음에 `python3 --version` → `python --version` → `py -3 --version` 순서로 3.9+ 인 것을 찾아 `$PY` 로 쓴다. Windows 의 Microsoft Store 별칭은 버전을 출력하지 못하므로 자연히 걸러진다. 하나도 없으면 「Python 3.9 이상을 설치해 주십시오(Windows: https://www.python.org/downloads/ 또는 `winget install Python.Python.3.12`)」라고 안내하고 멈춘다.
- 모든 스크립트는 JSON 을 출력한다. `"ok": false` 면 `error` 를 변호사에게 그대로 알리고, 추측으로 넘어가지 않는다.
- 작업 폴더: macOS `~/.intent-brief/cases/<사건 키>/`, Windows `%LOCALAPPDATA%\intent-brief\cases\<사건 키>\`. 플러그인을 지워도 남는다. 지우려면 `"$PY" "$S/state.py" purge <사건폴더>` (전부는 `--all`).
- 인용 대조 연결 확인: `"$PY" "$S/cite_check.py" ping` — 실패해도 계속한다(인용 대조만 장애 태그).

## 1. 시작

1. 사건 폴더를 받는다(없으면 묻는다). 서면 종류를 정한다: `준비서면` 또는 `답변서`(피고만).
2. `"$PY" "$S/state.py" init "<사건폴더>" --brief 준비서면` → `state`(상태 파일 경로)를 기억한다.
   - `resumed: true` 면 이어 간다. `changes.memo_changed` 나 `attachments_changed` 가 있으면 무엇이 바뀌었는지 보여 주고 Round 0 를 다시 확인받는다. `params_changed` 면 설계 확인 라운드를 다시 한다.
3. 자료를 읽는다: 사건 폴더의 사건메모·상대방 서면·첨부(텍스트로 읽을 수 있는 것). `"$PY" "$S/memo.py" read "<사건폴더>"` 가 사건메모의 의뢰인 지위·청구금액·지연손해금 여부·쟁점·일정을 미리 뽑아 준다. 일정이 오늘보다 지났으면 실제 기한·기일을 묻는다(`connected: false` 면 사건메모 없는 경로 — 기록 단계 생략).

## 2. 인터뷰

매 라운드: `"$PY" "$S/score.py" "<state>"` → `next.round_type`·`issue_id`·`why` 에 따라 **한 번에 한 문항**을 묻는다. AskUserQuestion 도구를 쓰지 않고 일반 텍스트로 묻는다. 답을 받으면 구조화 필드로 바꿔 `"$PY" "$S/state.py" apply "<state>" --json '<JSON>'` 로 저장한다(라운드 기록 `round` 포함). 점수는 스크립트가 계산한다 — 모델이 점수를 매기지 않는다.

질문 형식(예):
```
Round 2 | issue | 쟁점2(변제 항변) | 이유: 태도·증거가 없어 인정 범위를 정할 수 없습니다 | 모호도 41%
근거: 사건메모 「2. 변제 항변 — 피고 주장 1,000만원 변제의 입증책임(피고)」
(가) 태도: 1) 다툼  2) 일부 인정(금액)  3) 인정  4) 유보(이번 서면에서 언급 안 함)
(나) 증거: 1) 제출(번호)  2) 유보  3) 상대에 제출 요구(문서)
예: 「가2 1,000만원, 나2」
```

라운드 종류
- `round0` — 서면 종류·당사자 지위(원고/피고)·청구금액과 지연손해금 청구 여부(`claim_amount`·`claim_interest`)·쟁점 목록·제출 기한·다음 기일. 사건메모가 있으면 미리 채운 표를 보여 주고 「맞습니까」 한 번만 묻는다. 의뢰인 괄호가 복합(예: 「원고/고소인」)이면 지위를 묻는다. 첫 질문에 「빠르게(설계 표 하나로 정하기)」 선택지를 둔다 — 고르면 `intent.fast_path: true`.
- `intent` — 주 의도 1개(필수)와 부 의도 0–2개(순위), 「이 서면이 성공했다면 다음 기일에 무엇이 달라져 있어야 합니까」 한 문장, 주 의도가 M·S 면 양보선(금액). 목록: W 전부 승소 · M 손해 최소화 · S 조정·화해 유도 · P 상대 입장 고정·증거 제출 압박 · R 쟁점 재구성 · A 상소 대비 기록 · C 의뢰인 보고(부 의도 전용). 정의는 `references/intents.md`.
- `issue` — 쟁점 하나의 태도(다툼·일부 인정·인정·유보)와 증거(제출·유보·제출 요구)를 한 문항으로. 일부 인정이면 금액(원 단위 정수) 또는 범위.
- `procedure` — 제출 기한·다음 기일.
- `contrarian` — 「이 서면이 실패한다면 어떤 모습입니까」 한 번(3라운드 이후).
- `conflict` — `intent.py resolve` 가 `needs` 로 요구할 때만(최대 2회).
- `design_confirm` — 아래 3.
- `stop_no_intent` — 주 의도를 끝내 정하지 못함: 초안을 쓰지 않고 「상태를 저장했습니다. 의도를 정하시면 이어서 작성합니다」로 끝낸다(`state.py set-status <state> stopped`).

`state.py apply` JSON 필드(필요한 것만):
```json
{"side": "원고", "claim_amount": 50000000, "claim_interest": true,
 "issues": [{"id": 2, "title": "변제 항변", "stance": "일부 인정", "amount": 10000000,
             "evidence": {"mode": "유보", "items": [], "targets": []}}],
 "intent": {"primary": "S", "secondaries": ["M"], "success_sentence": "…", "concession": "4,000만원", "fast_path": false},
 "procedure": {"due_date": "2026-10-13", "next_hearing": "2026-09-22"},
 "flags": {"settle_will": true, "doc_targets": [], "alt_cause": null, "reduction_reasons": [], "procedural_issue": null},
 "conflict_answers": {},
 "round": {"round_type": "issue", "issue_id": 2, "axis": "ax_stance", "question": "…", "options": ["…"],
           "answer": "가2 1,000만원, 나2", "evidence_quote": "사건메모 「2. 변제 항변 …」", "why": "…"}}
```
- 부 의도가 없다고 답하면 `"secondaries": []`(빈 목록 = 확정). 모르면 넣지 않는다.
- `evidence_quote` 는 근거로 보여 준 사건메모·자료의 실제 문장만. 없으면 null(지어내지 않는다).
- `flags.alt_cause`: 원고가 청구원인이 다른 예비적 청구(예: 「부당이득반환」)를 원할 때만. `reduction_reasons`: 피고의 감액·공제 사유.

## 3. 설계 확인 (= 빠른 경로 = 덮어쓰기)

`score.py` 가 `design_confirm` 을 내면 `"$PY" "$S/intent.py" resolve "<state>"` 로 설계안을 받고 `state.py set-status <state> confirming` 후 표로 보여 준다.
```
설계 확인 | 원고 · 준비서면 · 주: 조정·화해(S) / 부1: 손해 최소화(M)
 [1] 쟁점1 대여 vs 증여        태도: 다툼                  증거: 갑1·갑2 제출
 [2] 쟁점2 변제 1,000만원      태도: 일부 인정(1,000만원)  증거: 유보
 [3] 강도: 중   [4] 어조: 협조적 경어   [5] 분량: 짧음(2,500–6,000자)
 [6] 섹션: 분쟁 경위 · 인정하는 사실 · 핵심 쟁점에 대한 반박 · 조정·화해에 관한 의견 …  (생략: …)
 [7] 결론: <design.conclusion.text 그대로>
 [8] 부 의도 문장: <design.addenda 또는 없음>
 [9] 할 일: <design.todo 또는 없음>
바꿀 번호와 값을 적어 주십시오(예: 「3=강, 9=삭제」). 그대로면 「확정」.
```
- `needs` 가 오면(`ok: false`) 그 `why` 로 conflict 질문을 한다.
- 바꾼 칸은 `overrides` 로 저장한다: `{"overrides": [{"cell": "strength", "value": "강"}], "round": {"round_type": "design_confirm", …}}`. 칸 이름: `strength`·`tone`·`length`·`evidence_strategy`·`sections.add`·`sections.remove`(섹션 ID 목록)·`addenda`(「삭제」)·`todo`(「삭제」)·`conclusion`(문장). 쟁점 태도를 바꾸면 `issues` 로 저장한다.
- 「확정」이면 `"$PY" "$S/intent.py" resolve "<state>" --write` → design.json 고정(`design_path`).

## 4. 사건메모 기록 ① (사건메모가 있을 때만)

`"$PY" "$S/memo.py" preview "<state>" --progress "준비서면 의도 확정 — 주: 조정·화해 유도 / 부: 손해 최소화 · 쟁점2 일부 인정(1,000만원) · 모호도 0.00"` → `diff` 를 그대로 보여 주고 「반영할까요?」. **변호사가 「반영」이라고 답한 뒤에만** `"$PY" "$S/memo.py" apply "<state>" --confirm <preview 의 token>`. 거절하면 쓰지 않는다. 토큰이 맞지 않거나 사건메모가 바뀌었으면 쓰지 않고 다시 읽는다.

## 5. 초안 작성

입력은 **원자료(사건메모·상대방 서면·첨부) + design.json** 이다. `references/phrases.json` 은 읽지 않는다(검사기 전용).
작업 폴더에 `<서면>_draft.md` 를 쓴다(`design_path` 와 같은 폴더). 형식:
```markdown
---
design: 준비서면_design.json
side: 원고
brief_type: 준비서면
---
## [sec:sec.header] 준비서면
사건  2026가단512345 대여금
원고  홍길동
피고  김대출
위 사건에 관하여 원고 소송대리인은 다음과 같이 변론을 준비합니다.
## [sec:sec.rebuttal_core] 핵심 쟁점에 대한 반박
### [issue:1] 금전소비대차의 성립
…
## [sec:sec.conclusion] 결론
<design.conclusion.text 를 한 글자도 바꾸지 않고 그대로>
## [sec:sec.evidence_list] 증거방법
1. 갑 제1호증 계좌이체내역
…
0000. 00. 00.
원고 소송대리인 변호사 ○○○ (인)
서울중앙지방법원 귀중
```
규칙
- 섹션은 `design.sections` 의 것만, 그 순서대로, `## [sec:<ID>] <제목>` 앵커로 쓴다. `##`·`###` 제목은 모두 앵커가 있어야 한다.
- 쟁점은 태도가 `유보` 가 아닌 것만 반박·인정 섹션 안에 `### [issue:<번호>] <제목>` 으로 쓴다. `유보` 쟁점은 어디에도 쓰지 않는다.
- 태도대로 쓴다: `다툼` 은 명시적으로 부인한다(예: 「부인합니다」), `일부 인정`·`인정` 은 인정 범위와 금액을 숫자로 적고 「인정합니다」라고 쓴다.
- 강도는 `design.strength.desc`, 어조는 `design.tone`, 분량은 `design.length.chars`(공백 제외 글자 수, 본문 기준)를 따른다. 제출 서면은 경어체.
- 결론 섹션에는 `design.conclusion.text` 를 그대로 쓴다.
- 증거 번호는 원고 「갑 제N호증」, 피고 「을 제N호증」.
- 자료에 없는 사실·날짜·금액·증거는 지어내지 않고 `[확인 필요: 무엇]` 으로 쓴다.
- 조문·판례는 근거가 분명할 때만 「민사소송법 제288조」「대법원 2017. 2. 21. 선고 2016다225353 판결」 형식으로 쓴다(뒤 단계에서 원문 대조).
- `design.withheld_evidence` 가 있으면 그 증거는 이번 서면에 내지 않는다.

## 6. 검사 → 1회 고쳐 쓰기

`"$PY" "$S/check_draft.py" check "<draft.md>" "<design.json>" --state "<state>" --record first` → `failures` 가 있으면 그 항목만 고쳐 draft.md 를 다시 쓰고 `--record final` 로 다시 검사한다. 두 번째도 불일치면 고치지 말고 실패 목록을 변호사에게 보여 준다.

## 7. 인용 대조

`"$PY" "$S/cite_check.py" run "<draft.md>"` — Bash timeout 을 600000 으로 준다. 호출 1회 약 3초라 인용이 많으면 오래 걸린다. `complete: false` 면 같은 명령을 다시 실행한다(캐시로 이어 간다). 판례 검색 기본은 `search_type=case_name`(그 번호의 판결 자체를 찾음), 0건이면 `full_text`(그 번호를 인용한 판결까지 찾음)로 한 번 더 — 2026-10-14 실측: `2018다248626` 은 case_name 4건 중 4번째·full_text 8건 중 8번째, `2014다26187` 은 case_name 0건·full_text 5건(모두 그 번호를 인용한 하급심, 원문은 법제처 DB 에 없음). 선고일이 적혀 있으면 그 날짜로 좁혀 찾고, 없으면 날짜 없이 다시 찾아 「선고일 불일치」나 「인용한 다른 판결 N건」을 알려 준다. 확인되지 않은 인용 뒤에는 스크립트가 태그를 붙인다: `[확인 필요: k-law 미확인]`·`[확인 필요: k-law 탐색 상한 도달]`·`[k-law 장애 — 미확인]` 등. 「확인됨」은 존재 확인일 뿐 적합성은 변호사가 본다.

## 8. 렌더·저장

- `C`(의뢰인 보고)를 골랐으면 먼저 작업 폴더에 `client_report.md`(1쪽, 비전문가용 — 이번 서면의 목표·인정한 것·기대 결과·남은 위험)를 쓴다.
- `"$PY" "$S/render_docx.py" all "<state>" --name "<사건약칭>"` → 사건 폴더에 `YYMMDD_<약칭>_<서면>_vN.docx` 와 `내부_…_vN_의도대응표.docx`. 기존 파일은 덮지 않고 N 을 올린다.

## 9. 사건메모 기록 ② (사건메모가 있을 때만)

4 와 같은 절차로 진행 경과 「<서면> 초안 vN 작성 — <파일명> · [확인 필요] N건」과, `design.todo` 의 각 `text` 를 **한 글자도 줄이지 말고 그대로**(법적 근거가 담긴 정본 문구다), 초안의 `[확인 필요]` 항목을 `--todo` 로 넣어 preview → 「반영」 → apply.

## 10. 끝맺음

변호사에게: 만든 파일 경로, 설계 준수율(1차·최종), 인용 대조 요약(확인됨·미확인·장애 수), `[확인 필요]` 건수, 할 일. 「AI는 실수할 수 있습니다. 제출 전 원문 대조와 최종 검토는 변호사님 판단입니다.」 한 줄.
