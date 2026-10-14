# 채점 규칙 (결정론, score.py 가 계산)

모델은 점수를 내지 않는다. 답을 아래 필드로 구조화해 상태 파일에 쓰면 `score.py` 가 계산한다.

| 축 | 가중치 | 1.0 | 0.5 | 0 |
|----|--------|-----|-----|---|
| ax_intent | 0.40 | primary + secondaries 순위 확정(빈 목록도 확정으로 본다) + success_sentence + (주 의도가 M·S 이면 concession) | primary 만 | primary 없음 |
| ax_stance (쟁점 최솟값) | 0.30 | stance + (일부 인정이면 amount 또는 scope) | stance 만(일부 인정인데 범위 없음) | stance 없음 |
| ax_evidence (쟁점 최솟값) | 0.15 | evidence.mode + (제출이면 items, 요구면 targets) | mode 만 | 없음 |
| ax_procedure | 0.15 | brief_type + due_date + next_hearing 셋 | 셋 중 둘 | 하나 이하 |

- 모호도 = 1 − Σ(가중치 × 점수). 통과 = 모호도 ≤ 0.20 그리고 ax_intent ≥ 0.80.
- 통과 판정은 정보 충분성만 본다. 어떤 의도를 골라도 통과할 수 있다.
- 상한(상한 안 라운드 수) = 6 + max(0, 쟁점 수 − 3), 최대 10. round0·conflict·design_confirm 은 상한 밖.
- 준비도 rd_law(보고만) = 근거 조문·판례 후보가 1개 이상인 쟁점 비율.
- 라운드 종류: round0 · intent · issue(쟁점 1개의 태도+증거) · procedure · contrarian(3라운드 이후 1회) · conflict(최대 2) · design_confirm(1회 + 수정 1회).
