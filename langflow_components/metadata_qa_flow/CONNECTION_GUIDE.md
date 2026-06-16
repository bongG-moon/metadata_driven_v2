# Metadata QA Flow Connection Guide

이 flow는 main flow의 `02 Metadata Context Loader` 뒤에 삽입하는 앞단 보조 flow입니다. 등록 데이터 목록, dataset 활용 예시/쿼리문, domain 등록 정보, 인사/도움말 질문을 데이터 retrieval과 pandas 실행 전에 직접 답변합니다.

## Nodes

| # | Node | Component file | Input | Output |
| --- | --- | --- | --- | --- |
| 00 | `00 Metadata Question Router` | `00_metadata_question_router.py` | `payload` | `payload_out` |
| 01 | `01 Metadata QA Response Builder` | `01_metadata_qa_response_builder.py` | `payload` | `payload_out`, `message` |

## Main Flow Insert Point

```text
02 Metadata Context Loader.payload_out
-> 00 Metadata Question Router.payload
-> 01 Metadata QA Response Builder.payload
-> 03 Intent Prompt Builder.payload

parallel payload branch:
01 Metadata QA Response Builder.payload_out
-> 04 Intent Plan Normalizer.payload
```

`01 Metadata QA Response Builder`가 직접 답변을 만들면 payload에 `direct_response_ready=true`가 들어갑니다. 이 경우 main flow의 `03`, `04`, `05`, `06`, `07`, `08`, `09`, `10`은 payload를 pass-through하며 `08 MongoDB Data Store`는 result row 저장을 하지 않습니다.

데이터 분석 질문이면 `metadata_route.route=data_analysis`로만 표시하고 원 payload를 그대로 넘깁니다.
