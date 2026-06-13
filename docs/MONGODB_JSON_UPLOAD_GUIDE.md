# MongoDB JSON Upload Guide

`tools/upload_json_to_mongodb.py`는 기본적으로 agent 운영에 필요한 core metadata JSON 3종만 MongoDB seed collection으로 올린다.

스크립트는 실행 시 프로젝트 루트의 `.env`를 자동으로 읽는다.

## Default Upload

기본 업로드 대상은 아래 3개 collection이다.

- `agent_v2_domain_items`
- `agent_v2_table_catalog_items`
- `agent_v2_main_flow_filters`

먼저 실제 접속 없이 업로드될 collection과 doc 수를 확인한다.

```powershell
cd C:\Users\qkekt\Desktop\metadata_driven_v2
python tools\upload_json_to_mongodb.py --dry-run
```

실제 업로드:

```powershell
python tools\upload_json_to_mongodb.py
```

## Optional Uploads

회귀 질문까지 같이 올리고 싶을 때만:

```powershell
python tools\upload_json_to_mongodb.py --dry-run --include-regression
python tools\upload_json_to_mongodb.py --include-regression
```

sample data까지 같이 올리고 싶을 때만:

```powershell
python tools\upload_json_to_mongodb.py --dry-run --include-regression --include-sample-data
python tools\upload_json_to_mongodb.py --include-regression --include-sample-data
```

## Upload Options

```powershell
$env:MONGODB_URI="mongodb://user:password@host:27017"
python tools\upload_json_to_mongodb.py --database datagov --collection-prefix agent_v2
```

`--mode upsert`가 기본값이다. deterministic `_id` 기준으로 같은 문서는 갱신된다.

전체 target collection을 지우고 다시 넣고 싶을 때만 `--mode replace`를 사용한다.

```powershell
python tools\upload_json_to_mongodb.py --database datagov --collection-prefix agent_v2 --mode replace
```

## If Extra Collections Were Already Uploaded

이미 sample/regression collection을 올렸고 지우고 싶다면 MongoDB에서 아래 collection들을 drop하면 된다. 삭제 작업이므로 실행 전에 대상 DB와 prefix를 반드시 확인한다.

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

운영 구조에서는 Langflow metadata loader가 core 3개 collection에서 domain/table/filter metadata를 읽고, retrieval executor가 source 결과를 별도 result store에 저장한 뒤 `data_ref`만 payload에 남기도록 확장하면 된다.
