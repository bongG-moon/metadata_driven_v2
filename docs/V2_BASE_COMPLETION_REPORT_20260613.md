# V2 Base Completion Report

작성일: 2026-06-13 KST

대상 폴더: `C:\Users\qkekt\Desktop\metadata_driven_v2`

## 완료한 보강

### 1. Intent normalizer production fallback

파일: `langflow_components/main_flow/03_intent_plan_normalizer.py`

보강 내용:

- LLM intent JSON에 `retrieval_jobs`가 없거나 비어 있어도 `analysis_kind`, `datasets`, metadata, 질문 문맥, 이전 state를 기반으로 fallback retrieval job을 생성한다.
- `production_wip_target_rate`, `rank_wip_then_join_production`, `aggregate_wip_total`, `low_output_vs_target`, `date_split_production_plan_gap`, `equipment_for_previous_products` 등 주요 16개 regression 범위의 `analysis_kind`에 대해 기본 dataset/alias/step plan을 복구한다.
- LLM이 준 `target_column`, `top_n`, `threshold`, `scope_label`, `state_product_keys` 같은 실행 파라미터를 normalized plan에 보존한다.
- follow-up 장비 질문에서 이전 `state.current_data.rows`의 product grain을 `state_product_keys`로 복구한다.
- fallback이 동작하면 `normalizer_notes`와 payload warning에 근거를 남긴다.

효과:

- production Langflow path가 validation harness의 deterministic planner에만 의존하지 않도록 보강했다.
- LLM이 intent 분류와 dataset은 맞혔지만 retrieval job 생성을 누락하는 경우에도 flow가 빈 retrieval로 무너질 가능성을 줄였다.

### 2. Pandas executor result column normalization

파일: `langflow_components/main_flow/06_pandas_code_executor.py`

보강 내용:

- LLM pandas code 실행 후 `result_df` 컬럼명을 표준 contract로 정규화한다.
- `PRODUCTION_sum`, `WIP_sum`, `OUT_PLAN_sum`, `PRODUCTION_total`, lowercase `rank` 같은 흔한 임시 컬럼명을 표준명으로 바꾼다.
- `생산량`, `재공 수량`, `목표값`, `달성률`, `부족수량` 같은 한국어 measure label도 표준 컬럼명으로 바꾼다.
- `analysis_kind`별 선호 컬럼 순서를 적용한다.

효과:

- LLM-generated pandas code가 계산은 맞게 했지만 결과 컬럼명이 흔들리는 경우를 production executor가 흡수한다.
- v3 validation script에만 있던 방어 아이디어를 실제 Langflow component 실행 경로로 이식했다.

### 3. Pandas prompt contract 강화

파일: `langflow_components/main_flow/05_pandas_prompt_builder.py`

보강 내용:

- pandas LLM prompt에 "final result columns must use standard contract names" 규칙을 추가했다.
- rank + production join 케이스에서 `RANK_GROUP`, `WIP_RANK`, product grain, `WIP`, `PRODUCTION` 컬럼명을 명시했다.

### 4. LLM validation script parity 보강

파일: `tools/validate_llm_in_loop.py`

보강 내용:

- production pandas executor와 같은 결과 컬럼 표준화 규칙을 validation script에도 반영했다.
- prompt contract도 production `05_pandas_prompt_builder.py`와 같은 방향으로 맞췄다.

### 5. 테스트 추가

파일:

- `tests/test_langflow_llm_node_flow.py`
- `tests/test_llm_validation_script.py`

추가 검증:

- LLM이 `retrieval_jobs`를 누락해도 `03 Intent Plan Normalizer`가 fallback jobs와 step plan을 생성하는지 확인.
- `06 Pandas Code Executor`가 `rank`, `WIP_sum`, `PRODUCTION_sum`을 `WIP_RANK`, `WIP`, `PRODUCTION`으로 표준화하는지 확인.
- `tools/validate_llm_in_loop.py`도 같은 컬럼 표준화 규칙을 적용하는지 확인.

### 6. Langflow canvas wiring guide 추가

파일: `docs/V2_LANGFLOW_CANVAS_WIRING_GUIDE.md`

포함 내용:

- main query/analysis flow의 node output -> input 연결표
- dummy retrieval 연결 방식
- Oracle/H-API/Datalake/Goodocs source별 retrieval + merger 연결 방식
- follow-up state 저장/재주입 방식
- domain/table catalog/main flow filter authoring flow 연결표
- 구현 후 검증 순서

관련 index 업데이트:

- `docs/LANGFLOW_NODE_CONNECTION_GUIDE.md`
- `README.md`

## 검증 결과

실행 위치:

```powershell
cd C:\Users\qkekt\Desktop\metadata_driven_v2
```

통과한 명령:

| Gate | Command | Result |
| --- | --- | --- |
| Python compile | `python -m compileall -q reference_runtime langflow_components tools tests` | PASS |
| Unit/contract tests | `python -m pytest tests -q` | PASS, 34 passed |
| Deterministic regression | `python tools\validate_regression.py` | PASS, 16/16 |
| MongoDB dry-run | `python tools\upload_json_to_mongodb.py --dry-run` | PASS, domain 21 docs, table catalog 9 docs, main flow filters 18 docs |
| LLM smoke | `python tools\validate_llm_in_loop.py --limit 1` | PASS, 1/1 |

생성된 최신 evidence:

- Deterministic regression report: `validation_runs\20260613_210756\REPORT.md`
- LLM smoke report: `validation_runs\20260613_210820_llm\REPORT.md`

## Base 선정 상태

`metadata_driven_v2`를 base flow로 사용하는 것을 권장한다.

현재 보강 후 기준:

- v2의 납품/문서 구조 유지
- v3의 pandas 컬럼 표준화 아이디어 production 이식
- intent normalizer fallback 추가
- Langflow canvas wiring guide 추가
- test count 30 -> 34로 증가
- deterministic regression 16/16 유지

## 남은 운영 확인 항목

- 실제 Langflow Desktop canvas에서 custom component를 붙여 넣고 end-to-end run 확인
- 운영 Oracle/H-API/Datalake/Goodocs connector를 dummy boundary 대신 연결
- `RUN_LIVE_SOURCE_RETRIEVAL=true` 또는 실제 Langflow source component로 live source smoke test
- authoring flow의 실제 LLM review + MongoDB write end-to-end test
- `.env`, cache, pyc, `validation_runs/*/results.json`를 commit 대상에서 제외
