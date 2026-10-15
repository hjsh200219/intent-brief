# LBOX 정찰 (2026-09-28, 공개 로그인 페이지 JS 번들 정적 분석 — 로그인 요청은 아직 안 보냄)

## 로그인 (이메일)
```
POST https://lbox.kr/user/login?deviceId=<deviceId>
Content-Type: application/json
X-Device-Fingerprint: <base64 스냅샷>   # 선택 — 스냅샷이 있을 때만
X-Legacy-Device-Id: <옛 id>             # 선택
{"email": "...", "password": "..."}
```
- 캡차 없음. 응답 쿠키 `lboxToken`(LBOX_TOKEN_COOKIE_KEY) + `XSRF-TOKEN` → 이후 요청에 `X-XSRF-TOKEN`
- `400` = 이메일/비번 불일치(`isInvalidCredentialsError`)
- `409` = 기기 한도 초과, 본문이 기존 기기 목록 → 기기 교체는 별도 인증 흐름(`Device replace verify flow`)
- 응답의 `deviceReconcile.effectiveDeviceId` 가 오면 그 값을 새 deviceId 로 저장(axios 인터셉터가 하는 일)

## deviceId 결정 (`getCandidateDeviceId`)
1. 저장된 id 가 `lbox_v1_` 또는 `lbox_install_` 로 시작하면 그대로
2. 아니면 브라우저 핑거프린트 스냅샷 → `POST /api/devices/fingerprint/sync` (헤더 `X-Device-Fingerprint`) → `internalDeviceId`
3. 실패 시 `lbox_install_<uuid>`
- CLI 는 `lbox_install_<uuid>` 를 한 번 만들어 `state/` 에 고정 저장 → 매번 같은 기기 1대로 잡힌다
- 핑거프린트 헤더 없이도 로그인되는지는 실측 필요(미검증)

## SNS 로그인
- 카카오·구글·네이버·애플 → 각 OAuth 로 받은 토큰을 `POST /snsAuth/startWithSns` (`snsType`, `snsToken`)
- CLI 는 이메일 로그인만 지원. SNS 로만 가입한 계정은 LBOX 에서 비밀번호를 먼저 설정해야 한다
- 로그아웃 `/user/logout`

## 캡차
- reCAPTCHA v2(site key 는 번들 공개값)는 로그인이 아니라 **문서 열람** 쪽: `/recaptcha?docType=CASE&from=...`
- 열람 빈도가 높으면 걸리는 것으로 추정(미검증) — 걸리면 브라우저에서 사람이 풀고 쿠키 재사용

## 호스트
- 본 API `lbox.kr` · 채팅 `chat.lbox.kr` · 리서치 `research.lbox.kr` · 스콜라 `scholar.lbox.kr`
- 판례 뷰어 경로 `/case/{court}/{caseNo}` · 검색 `/search/case`
