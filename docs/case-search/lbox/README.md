# LBOX (준비 중)

LBOX(lbox.kr) 판례 조회를 `scripts/lbox.py` 로 붙일 예정이다. 2026-09-28 `ProjectLawFirm/lbox` 에서 시작한 정찰 자료를 2026-10-15 이 repo 로 합쳤다.

- 로그인: 빅케이스와 같이 사용자마다 자기 LBOX 계정 — 비밀번호는 OS 키체인(서비스 `case-search-lbox`), 환경변수 `LBOX_ID`·`LBOX_PW` 가 있으면 우선
- 방식: Scrapling HTTP 로 `POST /user/login` 재현 → 쿠키 `lboxToken`·`XSRF-TOKEN` 재사용(정찰 결과 [recon.md](recon.md)). 로그인 실측 전이다
- 범위: 각자 본인 조회만. 대량 수집·재배포·다른 서비스의 데이터 소스로 쓰지 않는다 — LBOX 약관·저작권법 §93(DB제작자 권리)
- 쿠키·캡처(`state/`·`captures/`)는 git 에 넣지 않는다
