# FEAT-v2.1: Dashboard Revolution (2026-01-17)

**Status:** Completed ✅  
**Milestone:** Enterprise STORM v2.1  
**Target:** Backend & Frontend API 표준화, 테이블 기반 대시보드 구현

---

## 📋 개요

Enterprise STORM Backend/Frontend를 API v2.1 명세에 맞춰 전면 개편했습니다. 기존의 폼 기반 인터페이스를 테이블 기반 대시보드로 전환하고, 필터/정렬/페이지네이션 기능을 추가했습니다.

---

## 🎯 구현 내용

### 1. Backend API v2.1 표준화

#### 1.1 설정 중앙화 (src/common/config.py)
```python
# JOB_STATUS Enum 추가
class JOB_STATUS(Enum):
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

# TOPICS 리스트 간소화 (API v2.1 기준)
TOPICS = [
    {"id": "T01", "label": "기업 개요 및 주요 사업 내용", "value": "..."},
    {"id": "T02", "label": "재무 분석 및 실적 전망", "value": "..."},
    {"id": "custom", "label": "직접 입력", "value": None},
]
```

#### 1.2 기업 목록 조회 개선 (GET /api/companies)
- Companies 테이블 우선 조회 (Generated_Reports 폴백)
- 리포트 생성 이력이 없어도 데이터 적재된 기업은 목록에 표시

#### 1.3 리포트 목록 조회 필터링/정렬 (GET /api/reports)
**Query Parameters 추가:**
- `company_name`: 특정 기업 필터링
- `topic`: 주제 필터링 (부분 일치)
- `sort_by`: 정렬 기준 (created_at, company_name, topic, model_name)
- `order`: 정렬 순서 (asc, desc)
- `limit`, `offset`: 페이지네이션

**기본 동작:**
- 최신순 정렬 (created_at DESC)
- 경량화된 응답 (report_content 제외)

#### 1.4 리포트 생성 데이터 정제 (POST /api/generate)
```
입력:  { "company_name": "SK하이닉스", "topic": "SK하이닉스 재무 분석" }
        ↓
정제:  topic에서 company_name 제거 → "재무 분석"
        ↓
DB 저장: topic = "재무 분석" (순수 주제만)
LLM 호출: query = "SK하이닉스 재무 분석" (합쳐서 사용)
```

#### 1.5 상태 응답 개선 (GET /api/status/{job_id})
```json
{
  "job_id": "job-42",
  "status": "completed",
  "report_id": 42,  // [NEW] 프론트에서 바로 상세조회 가능
  "progress": 100
}
```

#### 1.6 필드명 변경
- ID 명명: `id` → `report_id` (명확성)
- 참고자료: `analysis_reports` → `references` (DART 원문과 구분)

### 2. Frontend 대시보드 전면 개편

#### 2.1 Dashboard 컴포넌트 → 테이블 기반 UI
**기존:** 폼 입력 → 단순 생성 흐름
**신규:** 테이블 + 필터 + 모달 팝업 구조

**구성 요소:**
1. **필터 바** (상단)
   - 기업 필터 Select
   - 주제 필터 Select
   - 새로고침 버튼

2. **리포트 테이블** (메인)
   - 컬럼: ID, 기업명, 분석 주제, 모델, 생성 일시, 상태, Action
   - 최신순 정렬 표시
   - 상태별 Chip 색상 (success/warning/error)
   - Action: 보기 버튼 (report_id 기반 상세조회)

3. **생성 모달** (팝업)
   - 기업 선택 (API: GET /api/companies)
   - 주제 선택 (API: GET /api/topics)
   - 직접 입력 옵션 (custom 선택 시 TextField 노출)
   - 생성 버튼 클릭 시 Optimistic Row 추가

#### 2.2 ReportViewer 개선
- Direct report_id 지원 (테이블 "보기" 클릭 시)
- Status 폴링 시 report_id 추출 (기존: message 파싱)
- References 딕셔너리 렌더링 (url_to_info 구조)

#### 2.3 App 라우팅 개선
```jsx
// 대시보드 → 리포트 보기 흐름
Dashboard → ReportViewer(reportId 직접 전달)

// 생성 흐름
Generate → ReportViewer(jobId로 폴링) → reportId 획득 후 조회
```

### 3. API 서비스 계층 동기화

#### 3.1 fetchReports 함수 추가
```javascript
export const fetchReports = async (params = {}) => {
  // company_name, topic, sort_by, order, limit, offset 지원
  return apiClient.get('/api/reports', { params });
};
```

#### 3.2 폴링 개선
- status 응답에서 report_id 직접 추출
- message 파싱 대신 report_id 필드 사용

---

## 🐛 버그 수정 로그

### Issue 1: Companies 테이블 컬럼 명칭 오류
**문제:** 
```sql
SELECT DISTINCT name AS company_name FROM "Companies"  -- ❌ 'name' 없음
```

**원인:** DB 실제 스키마에는 `company_name` 컬럼만 존재

**해결:** 
```sql
SELECT DISTINCT company_name FROM "Companies"  -- ✅
```

**파일:** [backend/database.py](../backend/database.py#L196)

---

### Issue 2: Generated_Reports.status 컬럼 부재
**문제:**
```sql
SELECT id, company_name, ..., status FROM "Generated_Reports"  -- ❌ status 없음
```

**원인:** DB 스키마에 status 컬럼이 존재하지 않음 (현재는 모두 completed로 관리)

**실제 스키마:**
```
- id (integer)
- company_name (varchar)
- company_id (integer)
- topic (text)
- report_content (text)
- toc_text (text)
- references_data (jsonb)
- conversation_log (jsonb)
- meta_info (jsonb)
- model_name (varchar)
- created_at (timestamp)
← status 컬럼 없음
```

**해결:** 
- DB 쿼리에서 status 제거
- API 응답은 항상 `"completed"` 기본값 사용
- 향후 status 컬럼 추가 시 수정 예정

**파일:** [backend/database.py](../backend/database.py), [backend/main.py](../backend/main.py)

---

### Issue 3: references_data 타입 불일치
**문제:**
```python
references: Optional[List[Dict[str, Any]]] = None  # ❌ 기대: 리스트
# 실제 DB 구조: {"url_to_info": {"url1": {...}, "url2": {...}}}
```

**Validation Error:**
```
Input should be a valid list [type=list_type, input_value={'url_to_info': {...}}]
```

**해결:**
```python
references: Optional[Dict[str, Any]] = None  # ✅ 딕셔너리
```

**프론트엔드 렌더링:**
```javascript
// url_to_info 구조로 매핑
report.references.url_to_info.forEach(([url, info]) => {
  // title, snippet, url 렌더링
})
```

**파일:** [backend/main.py](../backend/main.py), [frontend/react-app/src/components/ReportViewer.jsx](../frontend/react-app/src/components/ReportViewer.jsx)

---

## 📊 테스트 검증

### ✅ Backend Endpoints
1. `GET /` → Health Check
2. `GET /api/companies` → 기업 목록 (Companies 테이블 기반)
3. `GET /api/topics` → 주제 목록 (config.TOPICS)
4. `POST /api/generate` → 리포트 생성 (topic 정제)
5. `GET /api/status/{job_id}` → 상태 조회 (report_id 포함)
6. `GET /api/report/{report_id}` → 상세조회 (references Dict 반환)
7. `GET /api/reports` → 목록 조회 (필터/정렬/페이지네이션)

### ✅ Frontend Flows
1. 대시보드 접속 → 테이블 표시 (필터링, 정렬 작동)
2. 새 리포트 생성 → 모달 팝업 → 기업/주제 선택 → 생성
3. Optimistic Row 추가 (status: "processing")
4. 상태 폴링 → report_id 획득
5. 리포트 상세조회 → Markdown + 참고 문헌 렌더링
6. 테이블 "보기" 버튼 → 직접 report_id로 조회

---

## 📦 변경 파일 목록

### Backend
- `src/common/config.py` - JOB_STATUS Enum, TOPICS 간소화
- `backend/database.py` - 쿼리 수정 (company_name, status 제거)
- `backend/main.py` - 엔드포인트 전면 개선, 필터/정렬/페이지네이션

### Frontend
- `frontend/react-app/src/services/apiService.js` - fetchReports 추가
- `frontend/react-app/src/components/Dashboard.jsx` - 테이블 + 필터 + 모달 전면 개편
- `frontend/react-app/src/components/ReportViewer.jsx` - reportId 지원, references 렌더링 개선
- `frontend/react-app/src/App.jsx` - 라우팅 개선 (viewReport 핸들러)

---

## 🔗 Related Issues

- [API Spec v2.1 업데이트](../docs/API_SPEC.md)
- [Backend Integration Task](../backend/main.py)

---

## ✨ 다음 작업 (Future)

1. [ ] Status 컬럼 DB 추가 (현재는 항상 completed)
2. [ ] 비동기 작업 큐 (Celery/Redis) - 실제 처리 상황 추적
3. [ ] 인증/권한 관리 (JWT)
4. [ ] 리포트 다운로드 기능
5. [ ] 배치 생성 지원
6. [ ] 생성 히스토리 조회

---

**작성자:** Copilot  
**작성일:** 2026-01-17  
**버전:** v2.1.0
