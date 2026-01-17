# 🚨 Critical Bug Fixes & Schema Improvements

**Status**: Production Bug Tracking (P0/P1 only)  
**Purpose**: Record bugs that were deployed and fixed  
**See also**: [CLAUDE.md](../CLAUDE.md) for learning patterns & rules

---

## Overview

이 문서는 **배포된 P0/P1 버그만 기록**합니다 (데이터 무결성, 프로덕션 장애).

자세한 학습 내용과 규칙은 [CLAUDE.md](../CLAUDE.md)를 참조하세요.

---

## Fixed Issues

### 1. Silent Failure in Batch Insert (P0)

#### Problem
`DBManager.insert_materials_batch()` 메서드가 loop 처리 중 일부 블록 저장 실패 시 **조용히 스킵**하는 버그가 있었습니다.

```python
# 🔴 BEFORE (BUG):
def insert_materials_batch(self, report_id, blocks):
    count = 0
    for block in blocks:
        if self.insert_source_material(...):  # 실패 시 조용히 넘어감
            count += 1
    return count
# 결과: 콘솔에는 "2087개 블록 저장 완료"로 보이지만, 
#       실제 DB에는 1번 Report만 저장되고 2번부터는 0개
```

#### Impact
- Report ID 1번: 정상 저장
- Report ID 2번 이상: **0개 블록 저장** (데이터 유실)
- 사용자는 "등록 완료" 로그를 보고 정상이라고 착각

#### Fix
```python
# ✅ AFTER (FIXED):
def insert_materials_batch(self, report_id, blocks):
    count = 0
    for idx, block in enumerate(blocks):
        success = self.insert_source_material(...)
        if not success:
            error_msg = f"블록 저장 실패 (report_id={report_id}, block_idx={idx})"
            print(f"❌ {error_msg}")
            raise Exception(error_msg)  # 즉시 예외 전파
        count += 1
    return count
```

#### Files Changed
- `src/ingestion/db_manager.py` (Line 331-369)

#### Verification
```bash
python -m scripts.run_ingestion --test
python -m verify.verify_fix_ingest_loop
```

Expected Result:
```
✅ Report ID 1 (삼성전자): 2,087개 블록
✅ Report ID 2 (SK하이닉스): 2,259개 블록
✅ Report ID 3 (NAVER): 2,505개 블록
```

---

### 2. Schema Normalization - FK Addition (P0)

#### Problem
`Generated_Reports` 테이블이 `company_name` 문자열로만 기업을 식별하여:
- 조인 성능 저하 (인덱스 비효율)
- 데이터 무결성 미보장 (오타 시 orphan data)
- RDB의 장점 미활용

```sql
-- 🔴 BEFORE (문제):
CREATE TABLE "Generated_Reports" (
    id SERIAL PRIMARY KEY,
    company_name VARCHAR(100) NOT NULL,  -- FK 없음!
    ...
);
```

#### Fix
```sql
-- ✅ AFTER (개선):
CREATE TABLE "Generated_Reports" (
    id SERIAL PRIMARY KEY,
    company_name VARCHAR(100) NOT NULL,  -- 하위 호환성 유지
    company_id INTEGER REFERENCES "Companies"(id) ON DELETE CASCADE,  -- NEW!
    ...
);

CREATE INDEX idx_generated_reports_company_id 
ON "Generated_Reports"(company_id);
```

#### Files Changed
- `src/ingestion/db_manager.py` (Line 130-157): `init_db()` 스키마 수정
- `src/ingestion/db_manager.py` (Line 400-459): `insert_generated_report()` 시그니처 변경
- `scripts/run_storm.py` (Line 368-384): `save_report_to_db()` 로직 업데이트

#### Migration Strategy
```python
# db_manager.py의 insert_generated_report()
def insert_generated_report(self, company_name, ..., company_id=None):
    # company_id가 없으면 company_name으로 자동 조회
    if company_id is None:
        company = self.get_company_by_name(company_name)
        if company:
            company_id = company['id']
    
    # 양쪽 모두 저장 (하위 호환성)
    sql = """
        INSERT INTO "Generated_Reports" 
        (company_name, company_id, ...) 
        VALUES (%s, %s, ...)
    """
```

#### Verification
```bash
# DB 재생성 (테이블 DROP 후 새 스키마로 생성)
python -m scripts.run_ingestion --test

# 스키마 확인
python -m verify.verify_fix_ingest_loop
```

Expected Output:
```
✅ company_id 컬럼 존재 확인 (타입: integer)
✅ FK 제약조건 'fk_company' 존재
```

---

## Testing Checklist

모든 ingestion 코드 수정 후 다음을 실행해야 합니다:

```bash
# 1. Test Mode 실행 (3개 기업, DB 초기화 포함)
python -m scripts.run_ingestion --test

# 2. 검증 스크립트 실행
python -m verify.verify_fix_ingest_loop

# 3. DB 통계 확인
python -m scripts.run_ingestion --stats
```

**Pass Criteria:**
- [ ] 3개 기업 모두 Source_Materials에 블록 저장 (6,851개 이상)
- [ ] Report ID 2번, 3번도 블록 개수 > 0
- [ ] Generated_Reports 테이블에 company_id 컬럼 존재
- [ ] FK 제약조건 'fk_company' 존재
- [ ] 성공률 100% (실패 0개)

---

## Best Practices (Learned from This Bug)

### 1. Error Handling in Loops
**NEVER silently skip errors in batch operations.**

```python
# ❌ BAD
for item in items:
    if process(item):  # 실패 시 조용히 스킵
        count += 1

# ✅ GOOD
for item in items:
    if not process(item):
        raise Exception(f"Failed: {item}")
    count += 1
```

### 2. FK vs String Matching
**Always use FK for entity relationships.**

```python
# ❌ BAD
INSERT INTO reports (company_name) VALUES ('삼성전자')
SELECT * FROM reports WHERE company_name = '삼성전자'  # 느림, 오타 위험

# ✅ GOOD
INSERT INTO reports (company_id) VALUES (1)
SELECT * FROM reports r 
JOIN companies c ON r.company_id = c.id  # 빠름, 안전
```

### 3. DB Schema Migration
**When changing init_db(), always provide migration path.**

```python
# Option 1: Reset DB (dev/test)
python -m scripts.run_ingestion --test

# Option 2: Migration script (production)
# scripts/migrate_add_company_id_fk.py
```

### 4. Verification After Every Change
**No code change is complete without verification.**

```bash
# Always run these 3 commands:
1. python -m scripts.run_ingestion --test
2. python -m verify.verify_fix_ingest_loop
3. python -m scripts.run_ingestion --stats
```

---

## Related Documents
- [Data Ingestion Guidelines](.github/instructions/ingestion.instructions.md)
- [DB Schema Documentation](docs/FEAT-001-EntityBias-Report.md)
- [CLAUDE.md](CLAUDE.md) - Full error history and solutions

---

## Approval Log
- **Identified by**: Tech Leader (2026-01-16 14:30)
- **Fixed by**: AI Developer (2026-01-16 14:30-15:00)
- **Verified by**: Automated Test Suite (2026-01-16 15:00)
- **Status**: ✅ Deployed to `main` branch
---

### 3. Search Invisibility for Efficient Mode Data (P0)

#### Problem
`--efficient` 모드로 적재된 데이터(34,393건)가 검색에서 전혀 표시되지 않는 심각한 버그.

```python
# 🔴 BEFORE (BUG):
# postgres_connector.py search() 함수
company_condition = "AND metadata->>'company_name' = %s"

# 문제: efficient 모드 데이터는 metadata에 company_name 키가 없음!
# 결과: WHERE 조건에서 0건 반환 → 빈 배열 → Reranker 크래시
```

**증상:**
```
Error: Expected 2D array, got 1D array instead: array=[]
```

#### Impact
- `--efficient` 모드로 적재된 34,393건 데이터가 **완전 검색 불가**
- 현대엔지니어링, 삼양식품 등 실제 기업 분석 불가
- 시스템이 "데이터 없음"으로 크래시

#### Root Cause
| 적재 방식 | metadata에 company_name | 검색 가능? |
|---------|------------------------|-----------|
| `--test` 모드 | ✅ 있음 | ✅ 가능 |
| `--efficient` 모드 | ❌ 없음 | ❌ **불가** |

#### Fix
**메타데이터 대신 FK 체인을 통해 기업명 조회:**

```sql
-- 🔴 BEFORE:
SELECT * FROM "Source_Materials"
WHERE metadata->>'company_name' = '현대엔지니어링'

-- ✅ AFTER:
SELECT sm.*, c.company_name as resolved_company_name
FROM "Source_Materials" sm
JOIN "Analysis_Reports" ar ON sm.report_id = ar.id
JOIN "Companies" c ON ar.company_id = c.id
WHERE c.company_name = '현대엔지니어링'
```

#### Files Changed
- `knowledge_storm/db/postgres_connector.py` (Line 580-630): SQL JOIN 쿼리 수정
- `knowledge_storm/db/postgres_connector.py` (Line 690-710): `resolved_company_name` 사용

#### Code Changes
```python
# postgres_connector.py search()
sql = f"""
    SELECT 
        sm.id,
        sm.raw_content, 
        sm.section_path, 
        sm.chunk_type, 
        sm.report_id, 
        sm.sequence_order,
        sm.metadata,
        c.company_name as resolved_company_name,  -- JOIN에서 가져옴
        ...
    FROM "Source_Materials" sm
    JOIN "Analysis_Reports" ar ON sm.report_id = ar.id
    JOIN "Companies" c ON ar.company_id = c.id
    WHERE sm.chunk_type != 'noise_merged'
    {company_condition}  -- c.company_name = %s
    ...
"""

# Source Tagging에서 resolved_company_name 우선 사용
company_name = row.get('resolved_company_name') or \
               chunk_metadata.get('company_name', 'Unknown Company')
```

#### Verification
```bash
# 1. JOIN 검색 테스트
python scripts/test_join_search.py

# 2. 현대엔지니어링 STORM 분석
python -m scripts.run_storm --topic "현대엔지니어링 기업 개요"
```

**Expected Result:**
```
✅ FIX-Search-002 성공: 현대엔지니어링 데이터 검색 가능!
Found 10 results for query: 현대엔지니어링 기업 개요
Successful: 1/1
```

#### Diagnosis Script
`scripts/diagnose_metadata.py`로 메타데이터 상태 확인:
```bash
python scripts/diagnose_metadata.py
```

Output:
```
=== 전체 Source_Materials 메타데이터 통계 ===
총 레코드: 41,244
company_name 있음: 6,851 (test mode only)
company_name 없음: 34,393 (efficient mode)
```

---

## Approval Log (FIX-Search-002)
- **Identified by**: Tech Leader (2026-01-16 17:00)
- **Fixed by**: AI Developer (2026-01-16 17:00-18:00)
- **Verified by**: Manual Test - 현대엔지니어링 분석 성공 (2026-01-16 18:00)
- **Commit**: `15250d6` 
- **Status**: ✅ Deployed to `main` branch

---

### 3. API v2.1 Schema Mismatch Fixes (P1)

#### Problem 3.1: Companies 테이블 컬럼명 오류

**Issue:** Companies 테이블의 실제 컬럼명이 `name`이 아닌 `company_name`

```python
# 🔴 BEFORE (쿼리 실패):
cur.execute("""
    SELECT DISTINCT name AS company_name 
    FROM "Companies" 
    ORDER BY name ASC
""")
# Error: column "name" does not exist
```

**Fix:**
```python
# ✅ AFTER (수정):
cur.execute("""
    SELECT DISTINCT company_name 
    FROM "Companies" 
    ORDER BY company_name ASC
""")
```

**Files Changed:**
- `backend/database.py` (Line 196-207): `query_companies_from_db()` 쿼리 수정

#### Problem 3.2: Generated_Reports.status 컬럼 부재

**Issue:** DB 스키마에 status 컬럼이 없는데도 쿼리 시 조회하려는 버그

```python
# 🔴 BEFORE (쿼리 실패):
cur.execute("""
    SELECT id AS report_id, ..., status  -- ❌ status 없음
    FROM "Generated_Reports"
""")
# Error: column "status" does not exist
```

**실제 스키마 (2026-01-17 확인):**
```
Columns in Generated_Reports:
  - id: integer
  - company_name: character varying
  - company_id: integer
  - topic: text
  - report_content: text
  - toc_text: text
  - references_data: jsonb
  - conversation_log: jsonb
  - meta_info: jsonb
  - model_name: character varying
  - created_at: timestamp without time zone
  ← status 컬럼 없음
```

**Fix:**
```python
# ✅ AFTER (status 제거):
cur.execute("""
    SELECT id AS report_id, company_name, topic, model_name, created_at
    FROM "Generated_Reports"
""")
# API 응답: status는 항상 "completed" 기본값 사용
```

**Files Changed:**
- `backend/database.py` (Line 114-119, 178-185): status 제거
- `backend/main.py` (Line 370-375, 437-439): status는 기본값 "completed" 사용

#### Problem 3.3: references_data 타입 검증 실패

**Issue:** API 응답에서 references가 딕셔너리 구조인데 List로 정의

```python
# 🔴 BEFORE (Validation Error):
references: Optional[List[Dict[str, Any]]] = None
# 실제 DB 구조: {"url_to_info": {"dart_report_3_chunk_6044": {...}}}
# Error: Input should be a valid list [type=list_type, input_value={'url_to_info': {...}}]
```

**DB 실제 구조:**
```json
{
  "url_to_info": {
    "dart_report_3_chunk_6044": {
      "title": "...",
      "snippet": "...",
      "url": "..."
    },
    ...
  }
}
```

**Fix:**
```python
# ✅ AFTER (Dict로 변경):
references: Optional[Dict[str, Any]] = None

# 프론트엔드 렌더링:
Object.entries(report.references.url_to_info).map(([url, info]) => {
  // url: "dart_report_3_chunk_6044"
  // info: {title, snippet, url}
})
```

**Files Changed:**
- `backend/main.py` (Line 98): `ReportResponse.references` 타입 변경
- `frontend/react-app/src/components/ReportViewer.jsx` (Line ~304-334): url_to_info 구조 렌더링

#### Verification

```bash
# 1. 스키마 확인
python -m backend.check_schema

# 2. 엔드포인트 테스트
curl http://localhost:8000/api/companies
curl http://localhost:8000/api/reports?sort_by=created_at&order=desc
curl http://localhost:8000/api/report/3

# 3. Frontend 테스트
# - 대시보드 접속 → 기업 목록 로드
# - 리포트 테이블 표시
# - "보기" 버튼 → 참고 문헌 렌더링
```

**Expected Result:**
```
✅ companies 엔드포인트: 기업 목록 정상 조회
✅ reports 엔드포인트: 리포트 목록 필터/정렬 작동
✅ report 엔드포인트: references dict 정상 반환
✅ Frontend: 모든 테이블/모달/뷰어 정상 작동
```

#### Approval Log (FIX-v2.1-Schema)
- **Identified by**: Frontend testing (2026-01-17 09:00)
- **Fixed by**: AI Developer (2026-01-17 09:00-10:30)
- **Root Cause**: API v2.1 구현 시 실제 DB 스키마 무시
- **Impact**: 백엔드 대시보드 대시보드 엔드포인트 전체 비작동
- **Status**: ✅ Fixed and tested
- **Files**: 3개 (database.py, main.py, ReportViewer.jsx)

---

### 4. STORM Engine DB Save Logic Missing (P0)

#### Problem
Post /api/generate 호출 후 STORM 엔진은 정상 작동하여 파일을 생성했으나, 결과물이 **DB에 저장되지 않아** report_id가 None으로 반환되는 버그가 있었습니다.

#### Impact
```
❌ STORMWikiRunner.run()은 파일 시스템에만 저장 (DB 저장 안 함)
❌ report_id = None 반환
❌ 프론트엔드 무한 대기 (상태: "processing" → never "completed")
❌ 사용자 화면에 리포트 뷰어 전환 불가능
```

**Symptom in Logs:**
```
Querying latest report ID from database...
PostgreSQL connection closed
[job-400f9ace-9e61-...] ✅ Pipeline completed successfully
  Report ID: None  ❌
GET /api/status/job-400f9ace-9e61-... HTTP/1.1" 200 OK (무한 반복)
```

#### Root Cause Analysis
1. **파일 생성**: STORM 엔진이 `./results/temp/job-uuid/` 폴더에 파일 생성 ✓
2. **DB 저장 누락**: STORMWikiRunner는 설계 상 DB 저장 기능이 없음
3. **상태 조회**: 마지막 쿼리에서 해당 company_name+topic 조합이 없어 None 반환
4. **무한 대기**: Report ID 부재로 프론트엔드가 폴링 계속

#### Solution: Post-Processing Bridge

**구현 내용** (backend/storm_service.py):

1. **File Discovery** (_find_report_file)
   - 임시 폴더에서 `storm_gen_article_polished.txt` 탐색
   ```python
   report_file = _find_report_file(output_dir)
   # → ./results/temp/job-xyz/storm_gen_article_polished.txt
   ```

2. **UTF-8 Encoding** (_read_report_content)
   - **중요**: `encoding='utf-8'` 명시적 선언
   - Windows 기본 인코딩(cp949)으로 한글이 깨지는 문제 방지
   ```python
   # ✅ AFTER (FIXED):
   with open(file_path, "r", encoding="utf-8") as f:
       content = f.read()
   # 한글 완벽 보존 ✓
   ```

3. **DB INSERT with RETURNING** (_save_report_to_db)
   - PostgreSQL RETURNING 구문으로 생성된 ID 즉시 획득
   ```sql
   INSERT INTO "Generated_Reports" 
   (company_name, topic, report_content, model_name, created_at)
   VALUES (%s, %s, %s, %s, NOW())
   RETURNING id  -- 즉시 반환받음
   ```

4. **Status Sync** (_load_and_save_report_bridge)
   - 획득한 report_id를 `jobs_dict[job_id]['report_id']`에 할당
   - /api/status 응답에 report_id 포함
   ```python
   jobs_dict[job_id]["report_id"] = report_id
   jobs_dict[job_id]["status"] = "completed"
   ```

#### Before & After

**BEFORE (무한 대기):**
```
runner.run() 
  ↓ (파일 생성만, DB 저장 안 함)
query Latest report_id 
  ↓
report_id = None ❌
  ↓
프론트엔드: status=processing (계속 폴링)
```

**AFTER (정상 완료):**
```
runner.run()
  ↓ (파일 생성)
Bridge: 파일 읽기 (UTF-8)
  ↓
Bridge: DB INSERT (RETURNING id)
  ↓
report_id = 42 ✅
  ↓
프론트엔드: status=completed, report_id=42 → 뷰어 전환
```

#### Files Changed
- `backend/storm_service.py` (New functions + run_storm_pipeline 수정)
  - `_find_report_file()` (32줄)
  - `_read_report_content()` (42줄, **encoding='utf-8' 명시**)
  - `_save_report_to_db()` (42줄, **RETURNING id**)
  - `_load_and_save_report_bridge()` (56줄, Bridge 통합)
  - `run_storm_pipeline()` (Step 8 Bridge 호출 추가)

#### Verification (Test Suite: test/test_bridge.py)

```bash
# Test 1: UTF-8 인코딩
✅ 한글 내용 완벽 읽기
✅ 시스템 기본값(cp949) 무시하고 UTF-8 명시

# Test 2: 파일 탐색
✅ storm_gen_article_polished.txt 정상 발견

# Test 3: DB RETURNING
✅ 저장된 report_id 즉시 획득 (42)

# Test 4: Full Bridge
✅ 파일 → DB 저장 → report_id 반환 (5)
✅ jobs_dict 상태 동기화 완료
```

Expected Output:
```
🎉 All tests passed! Bridge is working correctly.

✅ Verification Checklist:
  [x] UTF-8 인코딩 (한글 보존)
  [x] 파일 탐색 로직
  [x] DB RETURNING id 획득
  [x] Full Bridge 통합 동작
```

#### Scenario Testing

**시나리오: 신규 리포트 생성**

1. Frontend: [+ 새 리포트 생성] 클릭
2. Backend: POST /api/generate
   - job_id 생성, status="processing" 즉시 반환
   - BackgroundTasks로 run_storm_pipeline 실행

3. STORM 엔진 (1~2분):
   - 검색 → 아웃라인 → 기사 생성 → 다듬기
   - 파일 저장: `results/temp/job-uuid/`

4. **Post-Processing Bridge** (새로 추가됨):
   - ✓ 파일 탐색 (storm_gen_article_polished.txt)
   - ✓ UTF-8 읽기 (한글 보존)
   - ✓ DB INSERT (RETURNING id)
   - ✓ 상태 동기화 (report_id 설정)

5. Frontend 폴링:
   - GET /api/status/{job_id}
   - **BEFORE**: report_id=None, status="processing" (무한)
   - **AFTER**: report_id=42, status="completed" ✓

6. 자동 전환:
   - ReportViewer 화면 표시
   - GET /api/report/42
   - 마크다운 렌더링 (한글 포함) ✓

#### Approval Log (FIX-Core-002-SaveLogic)
- **Identified by**: Production (Backend Engineer 리포트, 2026-01-17 11:00)
- **Fixed by**: AI Developer (2026-01-17 11:00-12:30)
- **Root Cause**: STORM 엔진은 파일 저장만 지원, DB 저장은 개발자 책임
- **Impact**: 프론트엔드 무한 대기, 리포트 생성 기능 불가능 (Showstopper)
- **Status**: ✅ Fixed, tested (4/4 bridge tests passed)
- **Files**: 2개 (backend/storm_service.py +270줄, test/test_bridge.py +156줄)
- **Tech Lead Approval**: "라이브러리(run())는 '작가'일 뿐, 원고를 서고(DB)에 꽂는 것은 '사서(Developer)'가 직접 해야 합니다."
````