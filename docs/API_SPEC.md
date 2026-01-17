# Enterprise STORM API Specification

**Version:** 2.0.0  
**Base URL:** `http://localhost:8000`  
**Description:** AI 기반 기업 분석 리포트 생성 및 조회를 위한 Backend API (PostgreSQL 연동)

---

## id 명명 규칙 정의

- `report_id`: Generated_Reports 테이블의 PK (AI가 생성한 최종 결과). API 응답의 핵심 ID입니다.
- `company_id`: Companies 테이블의 PK. (기업 고유 번호)
- `job_id`: 리포트 생성 작업의 비동기 Task ID (String, 예: "job-uuid").
- `doc_id`: Analysis_Reports 테이블의 PK. (DART 원문 메타데이터).
- `status` (String):
  - `processing`: 작업 진행 중
  - `completed`: 작업 완료 (성공)
  - `failed`: 작업 실패 (에러)

---

## 1. 헬스 체크 (Health Check)

서버 상태 및 버전 정보를 확인합니다.

- **URL:** `GET /`
- **Request:** 없음
- **Response:**

  ```json
  {
    "service": "Enterprise STORM API",
    "version": "2.0.0",
    "status": "operational",
    "mode": "production",
    "database": "PostgreSQL",
    "timestamp": "2026-01-17T10:00:00.123456"
  }
  ```

- **특징:**
  - 서버 구동 상태 및 DB 연결 모드 확인용 엔드포인트

---

## 2. 기업 목록 조회

데이터베이스에 저장된 기업 목록을 반환합니다.

- **URL:** `GET /api/companies`
- **Request:** 없음
- **Response:**
  
  ```json
    [
    "LG전자",
    "NAVER",
    "SK하이닉스",
    "삼성전자",
    "현대엔지니어링"
    ]
  ```

- **특징:**
  - `Gneerated_Reports` 테이블이 아닌 `Companies` 테이블(또는 `Source_Materials`가 존재하는 기업)을 조회합니다.
  - 리포트 생성 이력이 없더라도 데이터가 적재된 기업이라면 목록에 표시합니다.
  - DB 조회 실패 시 Fallback(샘플) 데이터 반환

---

## 3. 분석 주제(Topic) 목록 조회

리포트 생성 시 선택할 수 있는 분석 주제 목록을 반환합니다.

- **URL:** `GET /api/topics`
- **Request:** 없음
- **Response:**
  
  ```json
  [
    {
      "id": "T01",
      "label": "기업 개요 및 주요 사업 내용"
    },
    {
      "id": "T02",
      "label": "재무 분석 및 실적 전망"
    },
    {
      "id": "custom",
      "label": "직접 입력"
    }
  ]
  ```

- **특징:**
  - 기업명과 무관하게 공통으로 사용되는 주제 리스트
  - Frontend Dropdown 구성을 위한 데이터
  - `id: "custom"`은 사용자 정의 입력을 활성화하는 플래그로 사용

---

## 4. 리포트 생성 요청

특정 기업과 주제에 대한 AI 리포트 생성을 요청합니다.

- **URL:** `POST /api/generate`
- **Request:** `Content-Type: application/json`

  ```json
  {
  "company_name": "SK하이닉스",
  "topic": "종합 분석"
  }
  
  ```

- **Response:**

  ```json
  {
    "job_id": "job-42",
    "status": "processing | completed",
    "report_id": 42  // [NEW] 생성된 리포트의 DB PK (Integer)
  }
  
  ```

- **특징:**
  - 내부적으로 LLM 쿼리 시에는 기업명과 주제를 합쳐서 처리
  - 비동기 작업 처리를 위한 `job_id` 발급
  - `status: completed`일 경우 반드시 `report_id`에 유효한 정수값이 포함되어야 합니다.
  - 프론트엔드는 이 `report_id`를 사용하여 상세 조회 API를 호출합니다.

---

## 5. 작업 상태 조회

리포트 생성 작업의 진행 상태를 조회합니다.

- **URL:** `GET /api/status/{job_id}`
- **Request:** URL Path Parameter (예: `job-550e8400-e29b`)
- **Response (진행 중):**

  ```json
  {
    "job_id": "job-550e8400-e29b",
    "status": "processing",
    "report_id": null
  }
  ```

- **Response (완료):**

  ```json
  {
    "job_id": "job-550e8400-e29b",
    "status": "completed",
    "report_id": 42  // [NEW] 생성된 리포트의 DB PK (Integer)
  }
  ```

- **특징:**
  - `status: completed`일 경우 반드시 `report_id`에 유효한 정수값이 포함되어야 합니다.
  - 프론트엔드는 이 `report_id`를 사용하여 상세 조회 API를 호출합니다.

---

## 6. 리포트 상세 조회 (단건)

생성 완료된 리포트의 상세 내용을 조회합니다.

- **URL:** `GET /api/report/{report_id}`
- **Request:** URL Path Parameter (예: `42`)
- **Response:**
  
  ```json
  {
    "report_id": 42,            // [Modified] id -> report_id
    "company_name": "SK하이닉스",
    "topic": "종합 분석",
    "report_content": "# 마크다운 원문...",
    "toc_text": "...",
    "references": [             // [Modified] analysis_reports -> references
      { 
        "doc_id": 101,          // DART 문서 ID (Analysis_Reports PK)
        "source": "2023 사업보고서", 
        "content": "..." 
      }
    ],
    "meta_info": { ... },
    "created_at": "2026-01-17T10:30:00",
    "status": "completed"
  }
  
  ```

- **특징:**
  - **DB 연동:** `Generated_Reports` 테이블의 데이터를 조회하여 반환
  - **용어 분리**: DART 원문 정보를 담은 필드명을 analysis_reports에서 **references**로 변경하여 Generated Report와 구분
  - `references`: AI가 리포트 생성에 사용한 근거 자료(Source Context) 목록.
  - ID가 존재하지 않을 경우 `404 Not Found` 반환

---

## 7. 리포트 목록 조회 (전체)

생성된 모든 리포트의 목록을 조회합니다 (페이지네이션).

- **URL:** `GET /api/reports`
- **Request Parameters (Query String):**
  - `company_name`: (Optional) 특정 기업 필터링 (예: ?company_name=SK하이닉스)
  - `topic`: (Optional) 특정 주제 필터링
  - `sort_by`: (Optional, Default=created_at) 정렬 기준 컬럼 (created_at, company_name)
  - `order`: (Optional, Default=desc) 정렬 순서 (asc, desc)
  - `limit`: (Optional, Default=10)
  - `offset`: (Optional, Default=0)

- **Response:**

  ```json
  {
    "total": 15,
    "reports": [
      {
        "report_id": 42,
        "company_name": "SK하이닉스",
        "topic": "종합 분석",
        "created_at": "2026-01-17T12:00:00",
        "status": "completed",
        "model_name": "gpt-4o"
      },
      {
        "report_id": 41,
        "company_name": "삼성전자",
        ...
      }
    ]
  }
  ```

- **특징:**
  - **'대시보드(Table)'** UI 구성을 위해 검색(Filtering) 및 정렬(Sorting) 기능을   백엔드에서 처리하도록 개선했습니다.
  - **Server-side Sorting**: 기본적으로 최신순(`created_at desc`)으로 정렬되어 반환됩니다.
  - **Lightweight**: 목록 조회 시에는 report_content나 references 같은 무거운 텍스트 데이터는 제외하고, 테이블 표시에 필요한 메타데이터만 반환합니다.
