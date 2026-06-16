# Data Analysis Flow Connection Guide

`data_analysis_flow`는 실제 데이터 조회, pandas 분석, 결과 저장, 최종 답변 생성을 담당하는 순수 분석 flow입니다. Metadata/help/catalog 질문은 이 flow로 들어오지 않고 `router_flow`에서 `metadata_qa_flow`로 분기되어야 합니다.

## Sequence

```text
Backend orchestrator
-> 00 Analysis Request Loader
-> 01 Metadata Context Loader
-> 02 Intent Prompt Builder
-> Intent LLM
-> 03 Intent Plan Normalizer
-> 04 Previous Result Restore Router
```

이후에는 이전 결과 전체 row 복원이 필요한지에 따라 MongoDB loader를 조건부로 실행합니다.

```text
04 Previous Result Restore Router.payload_out
  -> 06 Previous Result Restore Merger.main_payload

04 Previous Result Restore Router.restore_payload
  -> 05 MongoDB Data Loader (only when previous_result_restore.required=true)
  -> 06 Previous Result Restore Merger.restored_payload

06 Previous Result Restore Merger.payload_out
-> 07/08/09/10/11 source retrievers
-> 12 Source Retrieval Merger
-> 13 Retrieval Payload Adapter
-> 14 Pandas Prompt Builder
-> Pandas Code LLM
-> 15 Pandas Code Executor
-> 16 MongoDB Data Store
-> 17 Answer Prompt Builder
-> Answer LLM
-> 18 Answer Response Builder
-> 19 Answer Message Adapter
-> Chat Output

parallel:
18 Answer Response Builder -> 20 API Response Builder -> API/Data Output
```

## Previous Result Restore

기본 정책은 flow 초반에는 이전 데이터를 전부 불러오지 않는 것입니다. `state.current_data`에는 `data_ref`, `row_count`, `columns`, preview rows, 제품 key summary 정도만 들고 갑니다.

`05 MongoDB Data Loader`는 `Restore Mode=auto`로 두는 것을 권장합니다. `auto`는 `03 Intent Plan Normalizer`가 `requires_full_state_hydrate=true` 또는 `state_hydrate_mode=full`을 설정한 경우에만 full restore로 바뀝니다. 그 외에는 preview/summary 상태를 유지합니다.

full restore가 실행되면 loader는 두 종류를 복원합니다.

- 이전 분석 결과: `state.current_data.data_ref`를 읽어 `state.current_data.rows`를 전체 row로 복원합니다.
- 이전 조회 원본: `state.followup_source_results[*].data_ref` 또는 `state.runtime_source_refs`를 읽어 `runtime_sources[source_alias]`로 전체 원본 row를 복원합니다.

따라서 후속 질문이 이전 결과 자체를 재정렬, 재집계, 필터링하거나 이전 질문에 사용된 원본 데이터 전체를 다시 분석해야 하는 경우에도 5행 preview에 막히지 않습니다.

## Example Cases

### Summary만 필요한 후속 질문

예:

- “현재 DA공정에서 재공이 가장 많은 제품 알려줘”
- “이 제품의 이 공정에 할당된 장비 대수를 알려줘”

이 경우에는 이전 결과 전체 row가 아니라 이전 결과에서 식별된 제품 key만 필요합니다. Normalizer는 `state_hydrate_mode=summary`를 유지하고, router는 `previous_result_restore.required=false`를 냅니다. 이후 retriever가 `equipment_assign` 같은 필요한 source만 새로 조회합니다.

### Full restore가 필요한 후속 질문

예:

- “방금 결과를 WIP 기준으로 다시 정렬해줘”
- “방금 조회한 전체 상세 row를 다시 보여줘”
- “이전 결과 중 WIP가 100 이상인 것만 필터링해줘”
- “방금 분석에 사용된 원본 재공 데이터를 제품별로 다시 집계해줘”

이 경우에는 preview rows만으로 부족합니다. Normalizer가 `state_hydrate_mode=full`을 설정하고, router가 `previous_result_restore.required=true`를 냅니다. 조건부 branch에서 `05 MongoDB Data Loader`가 이전 결과와 이전 원본 refs를 MongoDB에서 전체 복원한 뒤 pandas 단계로 넘깁니다.

## Branch Decision Contract

`04 Previous Result Restore Router.restore_decision` 예시:

```json
{
  "required": true,
  "branch": "restore_full_previous_rows",
  "restore_mode": "full",
  "loader_mode": "full",
  "requested_mode": "full",
  "reason": "후속 분석에서 이전 결과와 이전 조회 원본 전체 row가 필요하므로 MongoDB data_ref를 전체 복원합니다.",
  "data_ref": {"store": "mongodb", "ref_id": "..."},
  "source_ref_count": 2,
  "restore_ref_count": 3,
  "row_count": 250,
  "preview_row_count": 5
}
```

`required=false`이면 loader를 실행하지 않고 `main_payload`만 `06 Previous Result Restore Merger`로 연결합니다. `required=true`이면 `restore_payload -> 05 MongoDB Data Loader -> 06.restored_payload` 경로를 실행합니다.

## Result Store

`16 MongoDB Data Store`는 pandas 실행 직후에 둡니다. 저장 대상은 분석에 사용된 원본 `runtime_sources`와 pandas 결과 `analysis.rows`입니다. 최종 답변 생성 이후가 아니라 pandas 결과가 만들어진 즉시 저장해야 payload 축소 목적에 맞습니다.

`18 Answer Response Builder`는 다음 턴을 위해 큰 rows는 제거하고 `state.current_data.data_ref`, `state.followup_source_results[*].data_ref`, `state.runtime_source_refs`를 남깁니다. 이 ref들이 다음 턴 full restore의 기준점입니다.

## Naming Note

이 구간의 표준 표현은 `Previous Result Restore` 또는 “이전 결과 복원”입니다. MongoDB loader 내부 입력 이름인 `hydrate_mode`는 기존 loader 호환을 위해 유지하지만, Langflow 화면 표시명은 `Restore Mode`로 둡니다.
