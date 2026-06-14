# Metadata Text Input Examples

이 문서는 제조 작업자가 JSON 구조나 코딩을 몰라도 metadata authoring flow에 넣을 수 있는 자연어 입력 예시다.

작업자는 아래 문장을 그대로 복사해서 넣어도 되고, 자기 현장의 이름만 바꿔서 넣어도 된다. 단, 운영 화면은 세 가지로 나누어 쓰는 것을 권장한다.

- 업무 용어 등록: 공정 그룹, 제품 조건, 수량/지표/상태 용어
- 데이터셋 등록: 어떤 데이터가 어디에 있고 어떤 컬럼을 쓰는지
- 필터 등록: 질문에서 뽑아야 하는 날짜, 공정, 제품, LOT, 장비 같은 조건

한 번에 여러 항목을 넣어도 되고, 한 항목씩 넣어도 된다. 다만 서로 다른 종류를 한 입력에 섞지 않는 편이 좋다. 예를 들어 공정 그룹과 데이터 조회 SQL을 한 문장에 섞기보다, 업무 용어 등록 화면과 데이터셋 등록 화면에 나누어 넣는다.

## 작업자 입력 원칙

- 모르는 값은 만들지 않는다. 모르면 "이 값은 모름"이라고 적는다.
- 컬럼명, 공정명, 상태 코드는 들은 그대로 적는다.
- SQL이나 API 주소처럼 시스템 정보가 필요한 부분은 현장 작업자 혼자 판단하지 말고 시스템 담당자에게 받은 내용을 그대로 붙여 넣는다.
- 같은 항목을 다시 등록할 때는 기존 값을 보강할지, 바꿀지, 저장하지 않을지 선택한다.

## 업무 용어를 한 번에 등록하는 예시

아래 입력은 현재 domain metadata 전체를 한 번에 넣는 예시다.

```text
업무 용어를 등록할게요.

공정 그룹은 아래처럼 봐 주세요.
DA는 D/A라고도 부르고, 실제 공정은 D/A1, D/A2, D/A3, D/A4, D/A5, D/A6입니다.
WB는 W/B라고도 부르고, 실제 공정은 W/B1, W/B2, W/B3, W/B4, W/B5, W/B6입니다.
DP는 D/P라고도 부르고, 실제 공정은 D/P1, D/P2입니다.
BG는 B/G라고도 부르고, 실제 공정은 B/G1, B/G2입니다.
WSD는 WSD라고 부르고, 실제 공정은 WSD1, WSD2입니다.
DS는 D/S라고도 부르고, 실제 공정은 D/S1, D/S2입니다.
FCB는 FCB라고 부르고, 실제 공정은 FCB1, FCB2입니다.
FCBH는 FCBH라고 부르고, 실제 공정은 FCBH1, FCBH2입니다.
BM은 B/M 또는 비엠이라고도 부르고, 실제 공정은 B/M1, B/M2입니다.

제품 조건도 등록합니다.
HBM, 3DS, TSV, HBM제품, HBM 제품은 모두 같은 제품 조건입니다.
이 제품은 TSV_DIE_TYP 값이 존재하고 비어 있지 않은 제품으로 보면 됩니다.
다만 설비 현황 데이터처럼 TSV_DIE_TYP 컬럼이 없는 equipment 계열 데이터에서는 PKG_TYPE1이 HBM인 제품으로 보면 됩니다.
LPDDR5, LPDDR5제품, LPDDR5 제품은 모두 같은 제품 조건입니다.
이 제품은 MODE 값이 LPDDR5인 제품으로 보면 됩니다.
AUTO향, 오토모티브향, 오토향은 모두 같은 제품 조건입니다.
이 제품은 MCP_NO 값이 존재하고, MCP_NO의 마지막 문자가 I, O, N, P, Q, V 중 하나인 제품으로 보면 됩니다.

수량 용어도 등록합니다.
생산량, 생산실적, 실적은 production 계열 데이터의 PRODUCTION 컬럼을 합산합니다.
재공, 재공수량, WIP, 공정 물량은 wip 계열 데이터의 WIP 컬럼을 합산합니다.
목표값, 목표, 계획, 생산계획, OUT계획, INPUT계획은 target 계열 데이터의 INPUT_PLAN, OUT_PLAN 컬럼을 합산합니다. 기본 결과 컬럼명은 OUT_PLAN으로 봅니다.
Lot 수량, LOT 수량, Lot 개수, lot count는 lot_status 데이터에서 LOT_ID를 중복 없이 세고, 결과 컬럼명은 LOT_COUNT로 봅니다.
Wafer 수량, WAFER 수량, wafer, wafer 개수, wafer 몇개는 lot_status 데이터의 WF_QTY 컬럼을 합산하고, 결과 컬럼명은 WF_QTY로 봅니다.
Die 수량, DIE 수량, die, die수량, die 개수는 lot_status 데이터의 SUB_PROD_QTY 컬럼을 합산하고, 결과 컬럼명은 DIE_QTY로 봅니다.

지표 용어도 등록합니다.
생산달성률, 달성율, 달성률은 생산량 합계를 OUT 계획 합계로 나누고 100을 곱해서 계산합니다.
이 지표를 계산하려면 생산량과 목표값이 필요하고, 결과 컬럼명은 ACHIEVEMENT_RATE로 보여 주세요.
목표 미달, 부족분은 OUT 계획 합계에서 생산량 합계를 뺀 값이며, 음수면 0으로 봅니다.
이 지표를 계산하려면 생산량과 목표값이 필요하고, 결과 컬럼명은 BALANCE로 보여 주세요.
동적TAT, dynamic TAT는 재공 합계를 생산량 합계로 나눈 값입니다.
이 지표를 계산하려면 재공과 생산량이 필요하고, 결과 컬럼명은 DYNAMIC_TAT로 보여 주세요.
이 지표들은 먼저 합산한 뒤 계산해야 합니다.

분석 질문 패턴도 등록합니다.
생산달성률, 생산달성율, 달성률, 달성율 질문은 생산량, 재공, 목표 데이터가 필요하고 분석 방식은 production_wip_target_rate입니다.
이 질문은 production, wip, target 계열 데이터를 같이 사용합니다.
결과 컬럼은 WIP, PRODUCTION, OUT_PLAN, ACHIEVEMENT_RATE로 보여 주세요.
묶는 기준은 고정하지 말고 질문에서 전체라고 하면 전체 합계, 제품별이라고 하면 제품 기준, 공정별이라고 하면 공정 기준으로 봅니다.
생산 저조, 목표값 대비, 계획 대비, INPUT계획대비, 생산량 저조, 목표 미달 질문은 생산량과 목표 데이터가 필요하고 분석 방식은 low_output_vs_target입니다.
이 질문은 production, target 계열 데이터를 같이 사용합니다.
결과 컬럼은 PRODUCTION, TARGET_QTY, ACHIEVEMENT_RATE, BALANCE, LOW_OUTPUT_FLAG로 보여 주세요.
묶는 기준은 질문에서 말한 기준을 따릅니다.
Lot, Wafer, Die 수량 요약 질문은 lot_status 데이터를 사용하고 분석 방식은 lot_quantity_summary입니다.
결과 컬럼은 LOT_COUNT, WF_QTY, DIE_QTY로 보여 주세요.
묶는 기준은 기본적으로 전체 요약으로 봅니다.

상태 용어도 등록합니다.
hold lot, hold된 lot, hold상태 lot, Hold Lot은 lot_status 데이터에서 LOT_HOLD_STAT_CD가 HOLD 또는 OnHold인 row 목록으로 봅니다.
작업대기 Lot, 작업대기 Lot 수량은 lot_status 데이터에서 LOT_STAT_CD가 WAITING인 LOT_ID를 중복 없이 센 값입니다.
작업중 Lot, 작업중 Lot 수량은 lot_status 데이터에서 LOT_STAT_CD가 RUNNING인 LOT_ID를 중복 없이 센 값입니다.

제품을 식별할 때 기본으로 쓰는 컬럼은 TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO입니다.
```

## 업무 용어를 하나씩 등록하는 예시

```text
DA 공정 그룹을 등록할게요.
DA는 D/A라고도 부르고, 실제 공정은 D/A1, D/A2, D/A3, D/A4, D/A5, D/A6입니다.
```

```text
HBM 제품 조건을 등록할게요.
HBM, 3DS, TSV, HBM제품, HBM 제품은 같은 말입니다.
이 제품은 TSV_DIE_TYP 값이 있고 비어 있지 않은 제품입니다.
다만 equipment 계열 데이터에서는 PKG_TYPE1 값이 HBM인 제품으로 보면 됩니다.
```

```text
LPDDR5 제품 조건을 등록할게요.
LPDDR5, LPDDR5제품, LPDDR5 제품은 같은 말입니다.
이 제품은 MODE 값이 LPDDR5인 제품입니다.
```

```text
Lot 수량이라는 용어를 등록할게요.
Lot 수량, LOT 수량, Lot 개수, lot count는 lot_status 데이터에서 LOT_ID를 중복 없이 세는 값입니다.
결과 컬럼명은 LOT_COUNT로 보여 주세요.
```

```text
Wafer와 Die 수량 용어를 등록할게요.
Wafer 수량, WAFER 수량, wafer, wafer 개수는 lot_status 데이터의 WF_QTY 컬럼을 합산한 값입니다.
Die 수량, DIE 수량, die, die수량은 lot_status 데이터의 SUB_PROD_QTY 컬럼을 합산한 값입니다.
결과 컬럼명은 각각 WF_QTY, DIE_QTY로 보여 주세요.
```

```text
생산달성률 질문 패턴을 등록할게요.
생산달성률, 생산달성율, 달성률, 달성율은 같은 질문 표현입니다.
이 질문은 생산량, 재공, 목표 데이터가 필요하고, production, wip, target 계열 데이터를 같이 사용합니다.
분석 방식은 production_wip_target_rate로 보면 됩니다.
결과 컬럼은 WIP, PRODUCTION, OUT_PLAN, ACHIEVEMENT_RATE로 보여 주세요.
묶는 기준은 질문에 따라 달라집니다. 전체라고 하면 전체 합계, 제품별이라고 하면 제품 기준, 공정별이라고 하면 공정 기준으로 봅니다.
```

```text
Lot, Wafer, Die 수량 요약 질문 패턴을 등록할게요.
작업자가 lot, wafer, die 수량을 같이 물어보면 lot_status 데이터를 사용합니다.
분석 방식은 lot_quantity_summary로 보면 됩니다.
결과 컬럼은 LOT_COUNT, WF_QTY, DIE_QTY로 보여 주세요.
기본은 전체 요약으로 봅니다.
```

## 데이터셋을 한 번에 등록하는 예시

아래 입력은 현재 table catalog metadata 전체를 한 번에 넣는 예시다.
이 입력에는 시스템 조회 정보가 포함되어 있으므로, 현장 작업자는 시스템 담당자에게 받은 내용을 그대로 붙여 넣는 방식으로 운영한다.

```text
데이터셋 정보를 등록할게요.

production_today는 오늘 생산 실적 데이터입니다.
데이터 계열은 production이고, 날짜 범위는 current_day입니다.
source는 oracle이고 DB key는 PNT_RPT입니다.
조회문은 SELECT WORK_DT, OPER_NAME, TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, TSV_DIE_TYP, PRODUCTION FROM PKG_PRODUCTION_TODAY WHERE WORK_DT = {DATE} 입니다.
필수 입력값은 DATE이고, DATE는 WORK_DT 컬럼에 매핑합니다.
주요 수량 컬럼은 PRODUCTION입니다.
필터 매핑은 DATE=WORK_DT, OPER_NAME=OPER_NAME, MODE=MODE, TECH=TECH, DEN=DEN, PKG_TYPE1=PKG_TYPE1, PKG_TYPE2=PKG_TYPE2, LEAD=LEAD, MCP_NO=MCP_NO, TSV_DIE_TYP=TSV_DIE_TYP입니다.
컬럼은 WORK_DT, OPER_NAME, TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, TSV_DIE_TYP, PRODUCTION입니다.

production은 과거 생산 실적 데이터입니다.
데이터 계열은 production이고, 날짜 범위는 history입니다.
source는 oracle이고 DB key는 PNT_RPT입니다.
조회문은 SELECT WORK_DT, OPER_NAME, TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, TSV_DIE_TYP, PRODUCTION FROM PKG_PRODUCTION_HISTORY 입니다.
필수 입력값은 없습니다.
주요 수량 컬럼은 PRODUCTION입니다.
필터 매핑은 DATE=WORK_DT, OPER_NAME=OPER_NAME, MODE=MODE, TECH=TECH, DEN=DEN, PKG_TYPE1=PKG_TYPE1, PKG_TYPE2=PKG_TYPE2, LEAD=LEAD, MCP_NO=MCP_NO, TSV_DIE_TYP=TSV_DIE_TYP입니다.
컬럼은 WORK_DT, OPER_NAME, TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, TSV_DIE_TYP, PRODUCTION입니다.

wip_today는 오늘 재공 데이터입니다.
데이터 계열은 wip이고, 날짜 범위는 current_day입니다.
source는 oracle이고 DB key는 PNT_RPT입니다.
조회문은 SELECT WORK_DT, OPER_NAME, TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, TSV_DIE_TYP, WIP FROM PKG_WIP_TODAY WHERE WORK_DT = {DATE} 입니다.
필수 입력값은 DATE이고, DATE는 WORK_DT 컬럼에 매핑합니다.
주요 수량 컬럼은 WIP입니다.
필터 매핑은 DATE=WORK_DT, OPER_NAME=OPER_NAME, MODE=MODE, TECH=TECH, DEN=DEN, PKG_TYPE1=PKG_TYPE1, PKG_TYPE2=PKG_TYPE2, LEAD=LEAD, MCP_NO=MCP_NO, TSV_DIE_TYP=TSV_DIE_TYP입니다.
컬럼은 WORK_DT, OPER_NAME, TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, TSV_DIE_TYP, WIP입니다.

wip은 과거 재공 snapshot 데이터입니다.
데이터 계열은 wip이고, 날짜 범위는 history입니다.
source는 oracle이고 DB key는 PNT_RPT입니다.
조회문은 SELECT WORK_DT, OPER_NAME, TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, TSV_DIE_TYP, WIP FROM PKG_WIP_HISTORY 입니다.
필수 입력값은 없습니다.
주요 수량 컬럼은 WIP입니다.
필터 매핑은 DATE=WORK_DT, OPER_NAME=OPER_NAME, MODE=MODE, TECH=TECH, DEN=DEN, PKG_TYPE1=PKG_TYPE1, PKG_TYPE2=PKG_TYPE2, LEAD=LEAD, MCP_NO=MCP_NO, TSV_DIE_TYP=TSV_DIE_TYP입니다.
컬럼은 WORK_DT, OPER_NAME, TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, TSV_DIE_TYP, WIP입니다.

target은 생산 계획 데이터입니다.
데이터 계열은 target입니다.
source는 goodocs이고 문서 ID는 GOODOCS_TARGET_PLAN_DOCUMENT_ID, sheet 이름은 daily_target입니다.
필수 입력값은 없습니다.
날짜 형식은 YYYY-MM-DD입니다.
주요 계획 컬럼은 INPUT_PLAN, OUT_PLAN입니다.
필터 매핑은 DATE=DATE, MODE=MODE, TECH=TECH, DEN=DEN, PKG_TYPE1=PKG_TYPE1, PKG_TYPE2=PKG_TYPE2, LEAD=LEAD, MCP_NO=MCP_NO입니다.
컬럼은 DATE, TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, INPUT_PLAN, OUT_PLAN입니다.

lot_status는 현재 LOT 상태 데이터입니다.
데이터 계열은 lot입니다.
source는 oracle이고 DB key는 PNT_RPT입니다.
조회문은 SELECT LOT_ID, OPER_SHORT_DESC, LOT_STAT_CD, LOT_HOLD_STAT_CD, TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, SUB_PROD_QTY, WF_QTY, IN_TAT, CUM_TAT FROM PKG_LOT_STATUS 입니다.
필수 입력값은 없습니다.
주요 수량 컬럼은 SUB_PROD_QTY, WF_QTY, IN_TAT, CUM_TAT입니다.
필터 매핑은 LOT_ID=LOT_ID, OPER_NAME=OPER_SHORT_DESC, LOT_STAT_CD=LOT_STAT_CD, LOT_HOLD_STAT_CD=LOT_HOLD_STAT_CD, MODE=MODE, TECH=TECH, DEN=DEN, PKG_TYPE1=PKG_TYPE1, PKG_TYPE2=PKG_TYPE2, LEAD=LEAD, MCP_NO=MCP_NO입니다.
상세 목록 기본 컬럼은 LOT_ID, OPER_SHORT_DESC, LOT_STAT_CD, LOT_HOLD_STAT_CD, SUB_PROD_QTY, WF_QTY, IN_TAT, CUM_TAT입니다.
컬럼은 LOT_ID, OPER_SHORT_DESC, LOT_STAT_CD, LOT_HOLD_STAT_CD, TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, SUB_PROD_QTY, WF_QTY, IN_TAT, CUM_TAT입니다.

hold_history는 LOT HOLD 이력 데이터입니다.
데이터 계열은 hold입니다.
source는 h_api이고 API 주소는 https://h-api.example.invalid/lot/hold-history 입니다.
응답 row 위치는 data.rows입니다.
필수 입력값은 LOT_ID이고, LOT_ID는 LOT_ID 컬럼에 매핑합니다.
필터 매핑은 LOT_ID=LOT_ID입니다.
상세 목록 기본 컬럼은 LOT_ID, HOLD_TM, HOLD_CD, HOLD_DESC, HOLD_USER_ID, EVENT_CD입니다.
컬럼은 LOT_ID, HOLD_TM, HOLD_CD, HOLD_DESC, HOLD_USER_ID, EVENT_CD입니다.

equipment_status는 장비 현황 데이터입니다.
데이터 계열은 equipment입니다.
source는 oracle이고 DB key는 PNT_RPT입니다.
조회문은 SELECT EQPID, EQP_MODEL, PRESS_CNT, MODE, TECH, DEN, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, LOT_ID, RECIPE_ID FROM PKG_EQUIPMENT_STATUS 입니다.
필수 입력값은 없습니다.
주요 수량 컬럼은 PRESS_CNT입니다.
필터 매핑은 MODE=MODE, TECH=TECH, DEN=DEN, PKG_TYPE1=PKG_TYPE1, PKG_TYPE2=PKG_TYPE2, LEAD=LEAD, MCP_NO=MCP_NO, EQP_ID=EQPID 또는 EQP_ID, EQP_MODEL=EQP_MODEL, LOT_ID=LOT_ID, RECIPE_ID=RECIPE_ID입니다.
상세 목록 기본 컬럼은 EQPID, EQP_MODEL, PRESS_CNT, MODE, TECH, DEN, MCP_NO, RECIPE_ID입니다.
컬럼은 EQPID, EQP_MODEL, PRESS_CNT, MODE, TECH, DEN, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, LOT_ID, RECIPE_ID입니다.

capacity는 장비 capacity와 UPH 데이터입니다.
데이터 계열은 capacity입니다.
source는 datalake입니다.
조회문은 SELECT BASE_DT, EQPID, EQP_MODEL, RECIPE_ID, AVG_UPH_VAL, MODE, TECH, DEN, MCP_NO FROM LAKEHOUSE_CAPACITY WHERE BASE_DT = {DATE} 입니다.
필수 입력값은 없습니다.
주요 수량 컬럼은 AVG_UPH_VAL입니다.
필터 매핑은 DATE=BASE_DT, EQP_ID=EQPID 또는 EQP_ID, EQP_MODEL=EQP_MODEL, RECIPE_ID=RECIPE_ID, MODE=MODE, TECH=TECH, DEN=DEN, MCP_NO=MCP_NO입니다.
상세 목록 기본 컬럼은 BASE_DT, EQPID, EQP_MODEL, RECIPE_ID, AVG_UPH_VAL, MODE, TECH, DEN, MCP_NO입니다.
컬럼은 BASE_DT, EQPID, EQP_MODEL, RECIPE_ID, AVG_UPH_VAL, MODE, TECH, DEN, MCP_NO입니다.
```

## 데이터셋을 하나씩 등록하는 예시

```text
wip_today 데이터셋을 등록할게요.
이 데이터는 오늘 재공 데이터이고, 데이터 계열은 wip, 날짜 범위는 current_day입니다.
source는 oracle이고 DB key는 PNT_RPT입니다.
조회문은 SELECT WORK_DT, OPER_NAME, TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, TSV_DIE_TYP, WIP FROM PKG_WIP_TODAY WHERE WORK_DT = {DATE} 입니다.
필수 입력값은 DATE이고, DATE는 WORK_DT에 매핑합니다.
주요 수량 컬럼은 WIP입니다.
필터는 DATE=WORK_DT, OPER_NAME=OPER_NAME, MODE=MODE, TECH=TECH, DEN=DEN, PKG_TYPE1=PKG_TYPE1, PKG_TYPE2=PKG_TYPE2, LEAD=LEAD, MCP_NO=MCP_NO, TSV_DIE_TYP=TSV_DIE_TYP입니다.
컬럼은 WORK_DT, OPER_NAME, TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, TSV_DIE_TYP, WIP입니다.
```

```text
hold_history 데이터셋을 등록할게요.
이 데이터는 LOT HOLD 이력이고, 데이터 계열은 hold입니다.
source는 h_api이고 API 주소는 https://h-api.example.invalid/lot/hold-history 입니다.
응답 row 위치는 data.rows입니다.
LOT_ID가 필수 입력값이고 LOT_ID 컬럼에 매핑합니다.
필터도 LOT_ID=LOT_ID만 쓰면 됩니다.
상세 목록 기본 컬럼은 LOT_ID, HOLD_TM, HOLD_CD, HOLD_DESC, HOLD_USER_ID, EVENT_CD입니다.
컬럼도 LOT_ID, HOLD_TM, HOLD_CD, HOLD_DESC, HOLD_USER_ID, EVENT_CD입니다.
```

## 필터를 한 번에 등록하는 예시

아래 입력은 현재 main flow filter metadata 전체를 한 번에 넣는 예시다.

```text
질문에서 뽑아야 하는 필터 정보를 등록할게요.

DATE는 기준일, 일자, 날짜, 오늘, 어제, 작업일을 뜻합니다. 후보 컬럼은 WORK_DT, DATE, BASE_DT이고 역할은 date입니다. 값은 날짜 하나로 받습니다.
OPER_NAME은 공정명, 공정, 오퍼명을 뜻합니다. 후보 컬럼은 OPER_NAME, OPER_DESC, OPER_ID, OPER_SHORT_DESC이고 역할은 process입니다.
TECH는 제품 기술을 뜻합니다. 후보 컬럼은 TECH이고 역할은 product_attribute입니다.
DEN은 제품 용량을 뜻합니다. 후보 컬럼은 DEN이고 역할은 product_attribute입니다.
MODE는 제품 모드를 뜻합니다. 후보 컬럼은 MODE이고 역할은 product_attribute입니다.
PKG_TYPE1은 패키지 타입1을 뜻합니다. 후보 컬럼은 PKG_TYPE1이고 역할은 package_attribute입니다.
PKG_TYPE2는 패키지 타입2를 뜻합니다. 후보 컬럼은 PKG_TYPE2이고 역할은 package_attribute입니다.
LEAD는 Lead를 뜻합니다. 후보 컬럼은 LEAD이고 역할은 product_attribute입니다.
MCP_NO는 제품 코드, MCP 번호, MCP NO를 뜻합니다. 후보 컬럼은 MCP_NO, MCP NO, MCP_SALE_CD, MCPSALENO이고 역할은 product_code입니다.
DEVICE_DESC는 device, device code, DEVICE_DESC를 직접 언급했을 때만 쓰는 device 계열입니다. 후보 컬럼은 DEVICE_DESC, DEVICE, DEVICE_CODE이고 역할은 device입니다.
TSV_DIE_TYP는 HBM, 3DS, TSV 제품을 판별하는 컬럼입니다. 후보 컬럼은 TSV_DIE_TYP, TSV_DIE_TYPE이고 역할은 product_condition입니다.
OPER_NUM은 공정 번호를 뜻합니다. 후보 컬럼은 OPER_NUM, OPER_NO이고 역할은 process_number입니다.
LOT_ID는 Lot ID, LOT 번호를 뜻합니다. 후보 컬럼은 LOT_ID이고 역할은 lot_id입니다.
LOT_STAT_CD는 Lot 작업 상태를 뜻합니다. 후보 컬럼은 LOT_STAT_CD이고 역할은 lot_status입니다.
LOT_HOLD_STAT_CD는 Lot hold 상태를 뜻합니다. 후보 컬럼은 LOT_HOLD_STAT_CD이고 역할은 hold_status입니다.
EQP_ID는 장비 ID, 장비 번호를 뜻합니다. 후보 컬럼은 EQP_ID, EQPID이고 역할은 equipment_id입니다.
EQP_MODEL은 장비 모델을 뜻합니다. 후보 컬럼은 EQP_MODEL이고 역할은 equipment_model입니다.
RECIPE_ID는 Recipe ID, 레시피를 뜻합니다. 후보 컬럼은 RECIPE_ID이고 역할은 recipe_id입니다.
```

## 필터를 하나씩 등록하는 예시

```text
EQP_MODEL 필터를 등록할게요.
EQP_MODEL은 장비 모델을 뜻하고, 작업자가 장비 모델이라고 말하면 이 필터로 보면 됩니다.
후보 컬럼은 EQP_MODEL이고 역할은 equipment_model입니다.
```

```text
LOT_ID 필터를 등록할게요.
LOT_ID는 Lot ID, LOT 번호를 뜻합니다.
후보 컬럼은 LOT_ID이고 역할은 lot_id입니다.
```

## 검증 방법

이 문서의 예시는 아래 테스트로 고정한다.

```powershell
python -m pytest tests\test_metadata_authoring_flows.py tests\test_metadata_text_input_examples.py -q
```

검증은 실제 외부 MongoDB를 쓰지 않고 fake MongoDB client를 사용한다. 그래서 테스트는 데이터를 운영 DB에 저장하지 않으면서도 `07 Review Writer`가 실제 저장 성공 상태까지 가는지 확인한다.

검증 관점:

- 여러 항목을 한 번에 넣어도 전체 item 수가 맞는지
- 한 항목씩 넣어도 같은 writer 경로로 저장되는지
- JSON seed를 직접 올리지 않고, 작업자용 text input이 authoring payload의 원문으로 유지되는지
- normalizer가 저장 가능한 shape로 바꾸는지
- review가 통과하면 writer가 upsert 가능한 문서를 만드는지
