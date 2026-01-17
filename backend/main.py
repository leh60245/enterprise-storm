"""
FastAPI Backend API for Enterprise STORM Frontend Integration
Task ID: FEAT-DB-001-PostgresIntegration
Target: PostgreSQL 데이터베이스와 실제로 연동하여 살아있는 데이터 서빙

✅ 개선 사항:
- PostgreSQL 데이터베이스 연동 (backend/database.py)
- Mock 로직 제거 - 실제 DB 쿼리 실행
- 환경 변수 기반 설정 (.env 파일)
- Generated_Reports 테이블 스키마와 1:1 매칭
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid

# Database 모듈 임포트
from backend.database import (
    get_db_cursor,
    query_report_by_id,
    query_reports_with_filters,
    query_companies_from_db,
)
from src.common.config import get_topic_list_for_api, get_canonical_company_name, JOB_STATUS
from backend.storm_service import run_storm_pipeline
from psycopg2.extras import RealDictCursor
import psycopg2

# ============================================================
# FastAPI 앱 초기화
# ============================================================
app = FastAPI(
    title="Enterprise STORM API",
    description="AI-powered Corporate Report Generation API",
    version="2.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# ============================================================
# 전역 작업 상태 저장소 (Job Tracking Dictionary)
# ============================================================
# 실제 운영 환경에서는 Redis로 변경 필요
JOBS = {}

# ============================================================
# CORS 설정 (필수) - 프론트엔드(localhost:3000) 접근 허용
# ============================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Production에서는 특정 도메인으로 제한
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# Pydantic Data Models (DB Schema와 1:1 매칭)
# ============================================================

class GenerateRequest(BaseModel):
    """리포트 생성 요청 모델"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "company_name": "SK하이닉스",
                "topic": "재무 분석"
            }
        }
    )
    
    company_name: str
    topic: str = "종합 분석"


class CompanyInfo(BaseModel):
    """기업 정보 모델 (ID 포함)"""
    id: int
    name: str


class JobStatusResponse(BaseModel):
    """작업 상태 조회 응답 모델"""

    job_id: str
    status: str  # "processing" | "completed" | "failed"
    report_id: Optional[int] = None
    progress: Optional[int] = None  # 0-100
    message: Optional[str] = None


class ReportResponse(BaseModel):
    """리포트 조회 응답 모델 (API v2.1)"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "report_id": 1,
                "company_name": "SK하이닉스",
                "topic": "종합 분석",
                "report_content": "# SK하이닉스 종합 분석\n\n## 1. 개요\n...",
                "toc_text": "1. 개요\n2. 재무 분석\n3. 전망",
                "references": [
                    {"doc_id": 101, "source": "DART 2023 사업보고서", "content": "..."}
                ],
                "meta_info": {"search_queries": ["SK하이닉스 재무", "HBM 시장"]},
                "model_name": "gpt-4o",
                "created_at": "2026-01-15T10:30:00",
                "status": "completed",
            }
        }
    )

    report_id: int
    company_name: str
    topic: str
    report_content: str  # Markdown Content
    toc_text: Optional[str] = None
    references: Optional[Dict[str, Any]] = None  # JSONB: url_to_info structure
    meta_info: Optional[Dict[str, Any]] = None
    model_name: Optional[str] = "gpt-4o"
    created_at: Optional[str] = None
    status: str = JOB_STATUS.COMPLETED.value


class ReportSummary(BaseModel):
    """리포트 목록 아이템 모델 (company_id 포함)"""
    report_id: int
    company_id: Optional[int] = None
    company_name: str
    topic: str
    model_name: Optional[str]
    created_at: Optional[str]
    status: str


class ReportListResponse(BaseModel):
    """리포트 목록 조회 응답 모델"""
    total: int
    reports: List[ReportSummary]


# ============================================================
# API Endpoints (PostgreSQL DB 연동)
# ============================================================

@app.get("/")
async def root():
    """Health Check 엔드포인트"""
    return {
        "service": "Enterprise STORM API",
        "version": "2.1.0",
        "status": "operational",
        "mode": "production",
        "database": "PostgreSQL",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/companies", response_model=List[CompanyInfo])
async def get_companies():
    """
    [GET] 기업 목록 조회 (ID 포함)
    
    Returns:
        [
            { "id": 1, "name": "삼성전자" },
            { "id": 2, "name": "SK하이닉스" }
        ]
    """
    try:
        # database.py의 함수가 [{'id': 1, 'company_name': '삼성전자'}, ...] 형태 반환
        raw_data = query_companies_from_db()
        
        # DB 컬럼명(company_name)을 API 모델(name)로 매핑
        return [
            CompanyInfo(id=row['id'], name=row['company_name']) 
            for row in raw_data
        ]
    except Exception as e:
        print(f"❌ Error fetching companies: {e}")
        # Fallback for dev
        return []


@app.get("/api/topics")
async def get_topics():
    """
    [GET] 분석 주제(Topic) 목록 조회
    
    Returns:
        List[Dict]: 주제 리스트
        [
            {
                "id": "T01",
                "label": "기업 개요 및 주요 사업 내용"
            },
            ...
        ]
    
    특징:
    - 기업명과 무관하게 전체 공통 주제 반환
    - Frontend에서 Dropdown 구성 시 사용
    - "custom" 주제는 사용자 정의 입력 활성화 플래그
    """
    return get_topic_list_for_api()


@app.post("/api/generate", response_model=JobStatusResponse)
async def generate_report(request: GenerateRequest, background_tasks: BackgroundTasks):
    """
    [POST] 리포트 생성 요청 (비동기 처리)
    
    데이터 정제 로직 (중요):
    - 입력: company_name과 topic을 분리해서 받음
    - DB 저장: topic 컬럼에는 순수한 주제 텍스트만 저장
    - LLM 쿼리: 내부적으로만 f"{company_name} {topic}"으로 합쳐서 사용
    
    흐름:
    1. Frontend에서 { "company_name": "SK하이닉스", "topic": "기업 개요..." } 수신
    2. job_id 생성 → JOBS 딕셔너리에 초기 상태 저장
    3. BackgroundTasks에 run_storm_pipeline 등록 (비동기 실행)
    4. job_id 즉시 반환 → Frontend는 polling 시작
    5. BackgroundTasks가 실행되며 JOBS[job_id] 상태 업데이트
    6. 완료 시 JOBS[job_id]["report_id"] 설정
    
    개선사항 (FIX-Core-002):
    - ✅ BackgroundTasks로 비동기 처리
    - ✅ STORM 엔진의 파일 생성 후 DB에 저장 (Post-Processing Bridge)
    - ✅ 한글 인코딩 명시적 처리 (UTF-8)
    """
    try:
        company_name = get_canonical_company_name(request.company_name.strip())
        raw_topic = request.topic.strip()

        clean_topic = raw_topic.replace(company_name, "").strip()
        clean_topic = " ".join(clean_topic.split())  # normalize spaces
        if not clean_topic:
            clean_topic = raw_topic

        # 새로운 job_id 생성
        job_id = f"job-{uuid.uuid4()}"
        
        # JOBS 딕셔너리에 초기 상태 저장
        JOBS[job_id] = {
            "status": JOB_STATUS.PROCESSING.value,
            "company_name": company_name,
            "topic": clean_topic,
            "report_id": None,
            "progress": 0,
            "created_at": datetime.now().isoformat(),
        }
        
        # BackgroundTasks에 STORM 파이프라인 등록 (즉시 반환, 백그라운드 실행)
        background_tasks.add_task(
            run_storm_pipeline,
            job_id=job_id,
            company_name=company_name,
            topic=clean_topic,
            jobs_dict=JOBS,
        )
        
        # 즉시 job_id 반환 (Frontend는 이 job_id로 polling 시작)
        return JobStatusResponse(
            job_id=job_id,
            status=JOB_STATUS.PROCESSING.value,
            progress=0,
            message=f"{company_name}에 대한 '{clean_topic}' 리포트 생성을 시작합니다.",
        )
        
    except Exception as e:
        print(f"❌ Error in generate_report: {e}")
        import traceback
        traceback.print_exc()
        
        # 에러 발생 시에도 job_id는 반환 (Frontend에서 status 확인 시 에러 감지)
        job_id = f"job-{uuid.uuid4()}"
        JOBS[job_id] = {
            "status": JOB_STATUS.FAILED.value,
            "message": str(e),
        }
        
        return JobStatusResponse(
            job_id=job_id,
            status=JOB_STATUS.FAILED.value,
            progress=0,
            message=f"에러 발생: {str(e)}"
        )


@app.get("/api/status/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """
    [GET] 작업 상태 조회 (JOBS 딕셔너리에서 실시간 조회)
    
    실제 동작:
    1. JOBS 딕셔너리에서 job_id 조회
    2. 현재 상태, 진행률, report_id 반환
    3. status = "completed"이면 report_id도 포함 (Frontend가 리포트 조회)
    
    상태 흐름:
    - "processing" → 백그라운드 작업 진행 중
    - "completed" → report_id가 설정됨 (DB에 저장 완료)
    - "failed" → 에러 발생
    
    차후 개선:
    - Redis로 분산 환경 대응
    - 데이터베이스 상태 관리
    """
    if job_id not in JOBS:
        # Job이 없으면 Not Found
        return JobStatusResponse(
            job_id=job_id,
            status="not_found",
            progress=0,
            message="작업을 찾을 수 없습니다."
        )
    
    job_info = JOBS[job_id]
    
    return JobStatusResponse(
        job_id=job_id,
        status=job_info.get("status", JOB_STATUS.PROCESSING.value),
        progress=job_info.get("progress", 0),
        report_id=job_info.get("report_id"),
        message=job_info.get("message", "작업 진행 중...")
    )


@app.get("/api/report/{report_id}", response_model=ReportResponse)
async def get_report(report_id: int):
    """
    [GET] 리포트 조회 (핵심 엔드포인트 - DB 연동)
    
    ✅ 실제 동작 (PostgreSQL DB):
    1. database.query_report_by_id()를 사용해 DB에서 조회
    2. RealDictCursor로 받은 딕셔너리를 Pydantic 모델로 자동 매핑
    3. 없으면 404 에러 반환
    
    DB Schema (Generated_Reports):
    - id SERIAL PRIMARY KEY
    - company_name VARCHAR(255)
    - topic TEXT
    - report_content TEXT (Markdown)
    - toc_text TEXT
    - references_data JSONB
    - meta_info JSONB
    - model_name VARCHAR(100)
    - created_at TIMESTAMP
    - status VARCHAR(50)
    """
    try:
        # 데이터베이스에서 리포트 조회
        result = query_report_by_id(report_id)
        
        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Report with ID {report_id} not found in database"
            )
        
        # RealDictCursor 결과를 Pydantic 모델로 변환
        # JSONB 필드(references_data, meta_info)는 자동으로 딕셔너리로 파싱됨
        return ReportResponse(
            report_id=result['id'],
            company_name=result['company_name'],
            topic=result['topic'],
            report_content=result['report_content'],
            toc_text=result.get('toc_text'),
            references=result.get('references_data'),
            meta_info=result.get('meta_info'),
            model_name=result.get('model_name', 'unknown'),
            created_at=result['created_at'].isoformat() if result.get('created_at') else None,
            status=JOB_STATUS.COMPLETED.value,
        )
        
    except psycopg2.Error as e:
        # DB 연결 에러
        print(f"❌ Database error fetching report {report_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )
    except Exception as e:
        # 기타 예외
        print(f"❌ Error fetching report {report_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@app.get("/api/reports", response_model=ReportListResponse)
async def list_reports(
    company_name: Optional[str] = None,
    topic: Optional[str] = None,
    sort_by: str = "created_at",
    order: str = "desc",
    limit: int = 10,
    offset: int = 0,
):
    """[GET] 리포트 목록 조회 (필터/정렬 지원)"""

    try:
        result = query_reports_with_filters(
            company_name=company_name,
            topic=topic,
            sort_by=sort_by,
            order=order,
            limit=limit,
            offset=offset,
        )

        reports = [
            ReportSummary(
                report_id=row.get("report_id") or row.get("id"),
                company_id=row.get("company_id"),
                company_name=row.get("company_name"),
                topic=row.get("topic"),
                model_name=row.get("model_name"),
                created_at=row["created_at"].isoformat() if row.get("created_at") else None,
                status=JOB_STATUS.COMPLETED.value,
            )
            for row in result.get("reports", [])
        ]

        return ReportListResponse(
            total=result.get("total", 0),
            reports=reports,
        )

    except Exception as e:
        print(f"❌ Error querying reports: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )


# ============================================================
# 에러 핸들러 (옵션)
# ============================================================

@app.exception_handler(404)
async def not_found_handler(request, exc):
    return {
        "error": "Not Found",
        "message": "요청한 리소스를 찾을 수 없습니다.",
        "path": str(request.url)
    }


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    return {
        "error": "Internal Server Error",
        "message": "서버 내부 오류가 발생했습니다. 관리자에게 문의하세요.",
        "detail": str(exc)
    }


# ============================================================
# 서버 실행 가이드
# ============================================================
"""
[실행 방법]
1. 프로젝트 루트 디렉토리로 이동
2. 터미널에서 실행:
   
   # 개발 모드 (자동 리로드)
   python -m uvicorn backend.main:app --reload --port 8000
   
   # 프로덕션 모드
   python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 4

[검증 명령어]
1. Health Check:
   curl http://localhost:8000/

2. 리포트 조회 (핵심):
   curl http://localhost:8000/api/report/1
   
3. 리포트 생성 요청:
   curl -X POST http://localhost:8000/api/generate \
     -H "Content-Type: application/json" \
     -d '{"company_name": "SK하이닉스", "topic": "재무 분석"}'

4. 작업 상태 조회:
   curl http://localhost:8000/api/status/mock-job-001

5. 리포트 목록:
   curl http://localhost:8000/api/reports

[브라우저 API 문서]
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

[다음 작업 (차후)]
- [ ] src/common/db_connection.py와 통합
- [ ] PostgresRM 기반 실제 검색 구현
- [ ] STORM 엔진 통합
- [ ] 비동기 작업 큐 (Celery/Redis)
- [ ] 인증/권한 관리 (JWT)
"""
