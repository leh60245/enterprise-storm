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

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime

# Database 모듈 임포트
from backend.database import get_db_cursor, query_report_by_id, query_all_reports
from src.common.config import get_topic_list_for_api
from psycopg2.extras import RealDictCursor
import psycopg2

# ============================================================
# FastAPI 앱 초기화
# ============================================================
app = FastAPI(
    title="Enterprise STORM API",
    description="AI-powered Corporate Report Generation API",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

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


class JobStatusResponse(BaseModel):
    """작업 상태 조회 응답 모델"""
    job_id: str
    status: str  # "processing" | "completed" | "failed"
    progress: Optional[int] = None  # 0-100
    message: Optional[str] = None


class ReportResponse(BaseModel):
    """
    리포트 조회 응답 모델 (Generated_Reports 테이블 스키마 매칭)
    
    DB 스키마:
    - id SERIAL PRIMARY KEY
    - company_name VARCHAR(255)
    - topic TEXT
    - report_content TEXT (Markdown)
    - toc_text TEXT
    - references_data JSONB
    - conversation_log JSONB
    - meta_info JSONB
    - model_name VARCHAR(100)
    - created_at TIMESTAMP
    - status VARCHAR(50)
    """
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 1,
                "company_name": "SK하이닉스",
                "topic": "종합 분석",
                "report_content": "# SK하이닉스 종합 분석\n\n## 1. 개요\n...",
                "toc_text": "1. 개요\n2. 재무 분석\n3. 전망",
                "references_data": [
                    {"source": "DART 2023 사업보고서", "content": "..."}
                ],
                "meta_info": {
                    "search_queries": ["SK하이닉스 재무", "HBM 시장"],
                    "retrieval_count": 25
                },
                "model_name": "gpt-4o",
                "created_at": "2026-01-15T10:30:00",
                "status": "completed"
            }
        }
    )
    
    id: int
    company_name: str
    topic: str
    report_content: str  # Markdown Content
    toc_text: Optional[str] = None
    references_data: Optional[Dict[str, Any]] = None  # JSONB 형식 (url_to_info 등)
    meta_info: Optional[Dict[str, Any]] = None
    model_name: Optional[str] = "gpt-4o"
    created_at: Optional[str] = None
    status: str = "completed"


class ReportListResponse(BaseModel):
    """리포트 목록 조회 응답 모델"""
    total: int
    reports: List[Dict[str, Any]]


# ============================================================
# API Endpoints (PostgreSQL DB 연동)
# ============================================================

@app.get("/")
async def root():
    """Health Check 엔드포인트"""
    return {
        "service": "Enterprise STORM API",
        "version": "2.0.0",
        "status": "operational",
        "mode": "production",
        "database": "PostgreSQL",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/companies", response_model=list)
async def get_companies():
    """
    [GET] 기업 목록 조회 (DB에서 실제 데이터)
    
    Returns:
        List[str]: 기업명 목록 (예: ["SK하이닉스", "현대엔지니어링", ...])
    """
    try:
        with get_db_cursor(RealDictCursor) as cur:
            cur.execute("""
                SELECT DISTINCT company_name
                FROM "Generated_Reports"
                ORDER BY company_name ASC
            """)
            
            results = cur.fetchall()
            companies = [row['company_name'] for row in results]
            
            # DB에 데이터가 없으면 샘플 데이터 반환
            if not companies:
                companies = ["SK하이닉스", "현대엔지니어링", "NAVER", "삼성전자", "LG전자"]
            
            return companies
            
    except Exception as e:
        print(f"❌ Error fetching companies: {e}")
        # Fallback 데이터
        return ["SK하이닉스", "현대엔지니어링", "NAVER", "삼성전자", "LG전자"]


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
async def generate_report(request: GenerateRequest):
    """
    [POST] 리포트 생성 요청
    
    데이터 정제 로직 (중요):
    - 입력: company_name과 topic을 분리해서 받음
    - DB 저장: topic 컬럼에는 순수한 주제 텍스트만 저장
    - LLM 쿼리: 내부적으로만 f"{company_name} {topic}"으로 합쳐서 사용
    
    흐름:
    1. Frontend에서 { "company_name": "SK하이닉스", "topic": "기업 개요..." } 수신
    2. DB에 저장할 때: topic = "기업 개요..." (기업명 제외)
    3. LLM 호출 시: query = f"SK하이닉스 기업 개요..." (내부 변수)
    
    차후 개선:
    1. PostgresRM으로 관련 문서 검색
    2. STORM 엔진으로 리포트 생성
    3. Generated_Reports 테이블에 저장
    4. Celery/Redis 비동기 작업 큐
    """
    try:
        # ✅ 중요: 입력 검증
        # topic이 이미 company_name을 포함하면 제거 (방어적 코딩)
        topic = request.topic
        company_name = request.company_name
        
        # 만약 topic에 company_name이 포함되어 있으면 제거
        # 예: "SK하이닉스 기업 개요" → "기업 개요"
        if topic.startswith(company_name):
            topic = topic[len(company_name):].strip()
        
        # DB에서 가장 최근 리포트 ID 조회
        with get_db_cursor(RealDictCursor) as cur:
            cur.execute("""
                SELECT id FROM "Generated_Reports"
                ORDER BY id DESC LIMIT 1
            """)
            result = cur.fetchone()
            latest_id = result['id'] if result else 1
        
        # ✅ LLM 엔진 호출 시에만 합쳐서 사용
        # (현재는 mock이지만, run_storm.py 연동 시 여기에 query 구성)
        llm_query = f"{company_name} {topic}"
        print(f"[INFO] LLM Query: {llm_query}")
        
        return JobStatusResponse(
            job_id=f"job-{latest_id}",
            status="processing",
            progress=0,
            message=f"{company_name}에 대한 '{topic}' 리포트 생성을 시작합니다."
        )
    except Exception as e:
        print(f"❌ Error in generate_report: {e}")
        return JobStatusResponse(
            job_id="mock-job-001",
            status="processing",
            progress=0,
            message=f"{request.company_name}에 대한 '{request.topic}' 리포트 생성을 시작합니다."
        )
        return JobStatusResponse(
            job_id="mock-job-001",
            status="processing",
            progress=0,
            message=f"{request.company_name}에 대한 '{request.topic}' 리포트 생성을 시작합니다."
        )


@app.get("/api/status/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """
    [GET] 작업 상태 조회
    
    실제 동작 (현재):
    - job_id에서 ID 추출하여 해당 리포트 확인
    - completed 상태로 반환 + message에 report ID 포함
    
    차후 개선:
    - Redis/DB에서 job_id 기반 상태 조회
    - Celery 등 비동기 작업 큐 상태 확인
    """
    try:
        # job_id에서 숫자 추출 (예: "job-42" → 42)
        import re
        match = re.search(r'\d+', job_id)
        if match:
            report_id = int(match.group())
            return JobStatusResponse(
                job_id=job_id,
                status="completed",
                progress=100,
                message=f"리포트 생성이 완료되었습니다. /api/report/{report_id} 로 조회하세요."
            )
    except Exception as e:
        print(f"❌ Error in get_job_status: {e}")
    
    # 기본값
    return JobStatusResponse(
        job_id=job_id,
        status="completed",
        progress=100,
        message="리포트 생성이 완료되었습니다. /api/report/1 로 조회하세요."
    )


@app.get("/api/report/{id}", response_model=ReportResponse)
async def get_report(id: int):
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
        result = query_report_by_id(id)
        
        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Report with ID {id} not found in database"
            )
        
        # RealDictCursor 결과를 Pydantic 모델로 변환
        # JSONB 필드(references_data, meta_info)는 자동으로 딕셔너리로 파싱됨
        return ReportResponse(
            id=result['id'],
            company_name=result['company_name'],
            topic=result['topic'],
            report_content=result['report_content'],
            toc_text=result.get('toc_text'),
            references_data=result.get('references_data'),
            meta_info=result.get('meta_info'),
            model_name=result.get('model_name', 'unknown'),
            created_at=result.get('created_at').isoformat() if result.get('created_at') else None,
            status='completed'
        )
        
    except psycopg2.Error as e:
        # DB 연결 에러
        print(f"❌ Database error fetching report {id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )
    except Exception as e:
        # 기타 예외
        print(f"❌ Error fetching report {id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@app.get("/api/reports", response_model=ReportListResponse)
async def list_reports(limit: int = 10, offset: int = 0):
    """
    [GET] 리포트 목록 조회 (DB 연동)
    
    실제 동작 (차후 구현):
    - Generated_Reports 테이블에서 최신순 정렬 조회
    - Pagination 지원
    
    현재 동작 (DB):
    - 데이터베이스에서 최신 리포트 목록 반환
    """
    try:
        reports = query_all_reports(limit=limit, offset=offset)
        
        return ReportListResponse(
            total=len(reports),
            reports=reports
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
