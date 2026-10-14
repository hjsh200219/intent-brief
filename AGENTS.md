# AGENTS.md — intent-brief

변호사가 서면의 의도를 고르면 그 의도에 맞춘 민사 준비서면·답변서 초안(.docx)과 내부용 의도대응표를 만드는 Claude Code 플러그인. 스킬 1개(`intent-brief`) + 원격 MCP 1개(`k-data`). 서버·DB·빌드 없음.

## 지도

| 무엇 | 어디 |
|---|---|
| 매니페스트 | `.claude-plugin/plugin.json`·`marketplace.json`(버전 둘 다 맞춘다) · `.mcp.json` |
| 스킬 절차(모델이 읽는 정본) | `skills/intent-brief/SKILL.md` |
| 의도·채점·문구 데이터 | `skills/intent-brief/references/` — `intent-params.json`(섹션 어휘·충돌표), `intents.md`, `scoring.md`, `phrases.json`, `brief-types/` |
| 런타임 스크립트 | `skills/intent-brief/scripts/` — 역할·의존 방향은 [ARCHITECTURE.md](ARCHITECTURE.md) |
| 테스트 | `tests/` — 픽스처 F1(하네스 데모 사본)·F2·F3(합성), `recorded/`(녹화 응답), `e2e/`(답 파일) |
| 개발 전용 도구 | `dev/` — `replay.py`(무인 재생)·`e2e.py`(E1–E8 판정)·`smoke.py`(받는 PC 실기 점검)·`verify_docs.py` |
| 품질 기준·부채 | [docs/QUALITY.md](docs/QUALITY.md) · [docs/exec-plans/tech-debt-tracker.md](docs/exec-plans/tech-debt-tracker.md) |
| 구현 전 함정 목록 | [docs/harness/harness-setup.md](docs/harness/harness-setup.md) |
| 하네스 채점 | [원칙](docs/harness/principles.md) · [성숙도](docs/harness/maturity-framework.md) · [개선 카탈로그](docs/harness/fix-catalog.md) · [GC 이력](docs/harness/gc-history.md) |

## Health Stack

```
uv run --no-project --with pytest --with python-docx==1.2.0 pytest tests/            # 전체(문서 검사 포함)
uv run --no-project --python 3.9 --with pytest --with python-docx==1.2.0 pytest tests/  # 받는 PC 최저 버전
claude plugin validate --strict .                                                     # 매니페스트·.mcp.json
python3 dev/verify_docs.py                                                             # 문서 링크·버전·줄 수
```

`python-docx` 는 테스트에서 생성 docx 를 읽어 보는 데만 쓴다. 런타임 의존이 아니다.

## 불변 조건 (어기면 받는 PC 에서 깨진다)

1. 런타임 스크립트는 **표준 라이브러리만, Python 3.9 문법**. `tests/test_params.py` 가 import·문법을 검사한다.
2. 작업 폴더는 플러그인 밖 — macOS `~/.intent-brief/`, Windows `%LOCALAPPDATA%\intent-brief\`. `CLAUDE_PLUGIN_DATA` 는 uninstall 때 지워지므로 쓰지 않는다.
3. 사건 폴더의 `사건메모.md` 는 `memo.py apply` 의 확인 토큰으로만 쓴다. 줄바꿈(CRLF)을 보존하고, 사본에 먼저 적용해 성공했을 때만 바꾼다.
4. `.mcp.json` 서버 `type` 은 `"http"`. `"url"` 이면 로드 때 서버가 조용히 빠진다. 대조 스크립트도 이 파일의 URL 을 읽는다.
5. 인용 「확인됨」은 법제처 원문 **정확 일치**일 때만. 못 찾으면 `[확인 필요]`, 서버 장애면 `[k-law 장애 — 미확인]`.
6. 어떤 의도도 거부·경고하지 않는다. 자료에 없는 사실은 지어내지 않고 `[확인 필요: …]` 로 둔다.

## 개발 규칙

- 새 로직은 테스트를 먼저 쓴다(Red 확인 → Green). 커밋 본문에 Red/Green 을 적는다.
- 하네스 데모 트리(`agent-lawfirm/docs/references/업무관리시스템_데모/`)는 읽기만 한다. 그 안에서 Python 을 import·실행하지 않는다(바이트코드가 생긴다). casedb 계약 테스트는 경로가 있을 때만 돈다.
- `dev/replay.py`·`dev/e2e.py` 는 `claude -p` 를 여러 번 부른다(비용 발생). 판정 기준은 `dev/e2e.py` 의 `judge_run`. 선택 환경변수: `INTENT_BRIEF_TOKEN_FILE`(무인 실행 토큰 파일), `JEV_DIR`(블라인드 판별용 Jev 클라이언트), `INTENT_BRIEF_DEMO_DIR`(casedb 계약 테스트의 데모 원본).
- 공개 repo 다. 픽스처의 인명·사건번호는 가명이며 실제 의뢰인 자료를 넣지 않는다.
- 의도 목록·기본값 개정은 사용 통계(`intent.py stats`)를 근거로 한다.

## 문서

- 사용자 안내: [README.md](README.md)
- 구조·의존 방향: [ARCHITECTURE.md](ARCHITECTURE.md)
- 요구사항 정본(PRD)은 이 repo 밖, 개발 PC workspace 의 `.omc/plans/lawyer-intent-brief-skill.md` 에 있다(로컬 전용). 구현 결과·편차는 그 문서 §10에 있다.
