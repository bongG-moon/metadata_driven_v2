# Report Generation Flow Connection Guide

`report_generation_flow`는 리포트 생성 요청을 별도 분기로 받기 위한 확장 flow입니다. 현재는 이전 분석 결과와 router payload를 기반으로 리포트 초안 계획을 만들고, 이후 PPTX/Excel/Markdown 렌더러를 붙일 수 있는 구조입니다.

## Sequence

```text
Backend orchestrator
-> 00 Report Request Loader
-> 01 Report Outline Builder
-> 02 Report Data Selector
-> 03 Report Response Builder
-> Chat Output / API Output
```

## Inputs

| Input | Value |
| --- | --- |
| `question` | 리포트 생성 요청 |
| `session_id` | 현재 세션 |
| `state` | 이전 분석 state |
| `router_payload` | router_flow route decision |

이 flow는 data_analysis_flow를 대신 실행하지 않습니다. 리포트에 필요한 데이터가 없으면 먼저 분석 flow를 실행해 결과와 `data_ref`를 만든 뒤 다시 호출하는 방식으로 확장합니다.
