# Operations Diagnosis Flow Connection Guide

`operations_diagnosis_flow`는 병목, 이상 징후, 목표 미달, 장비 이슈 같은 운영 진단 요청을 별도 분기로 받기 위한 확장 flow입니다. 현재는 질문과 이전 분석 state에서 신호를 수집하고, 후속 조회/조치 추천을 만드는 구조입니다.

## Sequence

```text
Backend orchestrator
-> 00 Diagnosis Request Loader
-> 01 Diagnosis Signal Collector
-> 02 Diagnosis Rule Evaluator
-> 03 Diagnosis Response Builder
-> Chat Output / API Output
```

## Extension Point

`01 Diagnosis Signal Collector` 뒤에 실제 source 조회나 `data_analysis_flow` Run Flow 호출을 붙일 수 있습니다.

예:

- WIP 증가 신호가 있으면 공정별 WIP/생산량 조회를 요청
- 목표 미달 신호가 있으면 target/production 달성률 분석을 요청
- 장비 이슈 신호가 있으면 장비 현황 detail과 장비 대수 분석을 분리 호출
