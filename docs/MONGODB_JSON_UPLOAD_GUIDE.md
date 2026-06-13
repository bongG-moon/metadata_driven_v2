# MongoDB JSON Upload Guide

`tools/upload_json_to_mongodb.py`는 운영에 필요한 core metadata JSON 3종을 MongoDB seed collection으로 올리는 스크립트입니다.
질의 중 생성되는 source/result row는 이 스크립트가 아니라 main flow의 `05 MongoDB Data Store`가 별도 result collection에 저장합니다.

## Default Upload

기본 업로드 대상은 아래 3개 metadata collection입니다.

- `agent_v2_domain_items`
- `agent_v2_table_catalog_items`
- `agent_v2_main_flow_filters`

먼저 실제 접속 없이 대상 collection과 document count를 확인합니다.

```powershell
cd C:\Users\qkekt\Desktop\metadata_driven_v2
python tools\upload_json_to_mongodb.py --dry-run
```

실제 업로드:

```powershell
python tools\upload_json_to_mongodb.py
```

## Upload Options

metadata collection은 prefix 조합이 아니라 full collection name을 직접 입력합니다.

```powershell
$env:MONGODB_URI="mongodb://user:password@host:27017"
python tools\upload_json_to_mongodb.py --database datagov `
  --domain-collection agent_v2_domain_items `
  --table-catalog-collection agent_v2_table_catalog_items `
  --main-flow-filter-collection agent_v2_main_flow_filters
```

`--mode upsert`가 기본값이며 deterministic `_id` 기준으로 같은 문서를 갱신합니다.
전체 target collection을 비우고 다시 넣고 싶을 때만 `--mode replace`를 사용합니다.

```powershell
python tools\upload_json_to_mongodb.py --database datagov `
  --domain-collection agent_v2_domain_items `
  --table-catalog-collection agent_v2_table_catalog_items `
  --main-flow-filter-collection agent_v2_main_flow_filters `
  --mode replace
```

## Optional Uploads

regression 질문까지 같이 올릴 때:

```powershell
python tools\upload_json_to_mongodb.py --dry-run --include-regression
python tools\upload_json_to_mongodb.py --include-regression
```

sample data까지 같이 올릴 때:

```powershell
python tools\upload_json_to_mongodb.py --dry-run --include-regression --include-sample-data
python tools\upload_json_to_mongodb.py --include-regression --include-sample-data
```

## If Extra Collections Were Already Uploaded

sample/regression collection을 지우고 싶다면 MongoDB에서 아래 collection을 drop합니다. 삭제 전 대상 DB를 반드시 확인하세요.

```javascript
db.agent_v2_regression_questions.drop()
db.agent_v2_sample_capacity.drop()
db.agent_v2_sample_equipment_status.drop()
db.agent_v2_sample_hold_history.drop()
db.agent_v2_sample_lot_status.drop()
db.agent_v2_sample_production.drop()
db.agent_v2_sample_production_today.drop()
db.agent_v2_sample_target.drop()
db.agent_v2_sample_wip.drop()
db.agent_v2_sample_wip_today.drop()
```

## Main Flow Result Store

metadata collection 3개와 result store collection은 목적이 다릅니다.

| Collection type | 기본 full collection name | 저장 내용 |
| --- | --- | --- |
| Domain metadata | `agent_v2_domain_items` | 업무 용어, 공정/제품/수량 기준 |
| Table catalog metadata | `agent_v2_table_catalog_items` | dataset, source type, column/param/filter 매핑 |
| Main flow filter metadata | `agent_v2_main_flow_filters` | DATE, LOT_ID 같은 필터/파라미터 정의 |
| Main flow result store | `agent_v2_result_store` | 질의 실행 중 발생한 source rows, final rows, follow-up rows |

운영 main flow에서는 `05 MongoDB Data Store`와 `06 MongoDB Data Loader`가 result store를 사용합니다.

- 환경변수: `MONGODB_RESULT_COLLECTION`
- Langflow 입력명: `result_collection_name`
- 저장 대상: `runtime_sources`, 최종 `data.rows`, 후속 질문용 `state.current_data.rows`
- payload에는 preview rows와 MongoDB `data_ref`만 남깁니다.

즉 `upload_json_to_mongodb.py`는 metadata seed용이고, 실제 질의 결과 payload 절감은 Langflow main flow 안의 MongoDB result store 노드가 담당합니다.
