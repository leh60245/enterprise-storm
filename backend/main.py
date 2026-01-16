"""
FastAPI Mock Server for Enterprise STORM Frontend Integration
Task ID: FEAT-API-001-MockServer
Target: 프론트엔드 연동을 위한 DB 스키마 기반 Mock 데이터 서빙

⚠️ 주의사항:
- 실제 DB 연결 코드는 포함하지 않음 (차후 작업)
- backend/assets/sample_report.md 파일을 읽어서 Mock 데이터 제공
- Generated_Reports 테이블 스키마와 1:1 매칭되는 Pydantic 모델 사용
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
import os
from datetime import datetime

# ============================================================
# FastAPI 앱 초기화
# ============================================================
app = FastAPI(
    title="Enterprise STORM API",
    description="AI-powered Corporate Report Generation API (Mock Server)",
    version="1.0.0"
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
    references_data: Optional[List[Dict[str, Any]]] = None
    meta_info: Optional[Dict[str, Any]] = None
    model_name: Optional[str] = "gpt-4o"
    created_at: Optional[str] = None
    status: str = "completed"
    


class ReportListResponse(BaseModel):
    """리포트 목록 조회 응답 모델"""
    total: int
    reports: List[Dict[str, Any]]


# ============================================================
# Mock 데이터 로더 (파일 기반)
# ============================================================

def load_sample_report() -> str:
    """
    backend/assets/sample_report.md 파일 로드
    실제 DB 연동 전까지 Mock 데이터로 사용
    """
    file_path = os.path.join("backend", "assets", "sample_report.md")
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return content
    except FileNotFoundError:
        return """# Error: Sample Report Not Found

**해결 방법**: 
1. `backend/assets/sample_report.md` 파일이 존재하는지 확인
2. 프로젝트 루트에서 서버를 실행했는지 확인 (`uvicorn backend.main:app`)
"""
    except Exception as e:
        return f"# Error Loading Report\n\n{str(e)}"


# ============================================================
# API Endpoints
# ============================================================

@app.get("/")
async def root():
    """Health Check 엔드포인트"""
    return {
        "service": "Enterprise STORM API",
        "version": "1.0.0",
        "status": "operational",
        "mode": "mock",
        "timestamp": datetime.now().isoformat()
    }


@app.post("/api/generate", response_model=JobStatusResponse)
async def generate_report(request: GenerateRequest):
    """
    [POST] 리포트 생성 요청 (Mock)
    
    실제 동작 (차후 구현):
    1. PostgresRM으로 관련 문서 검색
    2. STORM 엔진으로 리포트 생성
    3. Generated_Reports 테이블에 저장
    
    현재 동작 (Mock):
    - 요청을 받으면 무조건 성공 응답 반환
    - 고정된 job_id 발급
    """
    return JobStatusResponse(
        job_id="mock-job-001",
        status="processing",
        progress=0,
        message=f"{request.company_name}에 대한 '{request.topic}' 리포트 생성을 시작합니다."
    )


@app.get("/api/status/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """
    [GET] 작업 상태 조회 (Mock)
    
    실제 동작 (차후 구현):
    - Redis/DB에서 job_id 기반 상태 조회
    - Celery 등 비동기 작업 큐 상태 확인
    
    현재 동작 (Mock):
    - 모든 job_id에 대해 "completed" 반환
    """
    # Mock: 항상 완료 상태 반환
    return JobStatusResponse(
        job_id=job_id,
        status="completed",
        progress=100,
        message="리포트 생성이 완료되었습니다. /api/report/1 로 조회하세요."
    )


@app.get("/api/report/{id}", response_model=ReportResponse)
async def get_report(id: int):
    """
    [GET] 리포트 조회 (핵심 엔드포인트)
    
    실제 동작 (차후 구현):
    ```python
    from src.common.db_connection import get_db_session
    
    with get_db_session() as session:
        result = session.execute(
            text("SELECT * FROM \"Generated_Reports\" WHERE id = :id"),
            {"id": id}
        ).fetchone()
        
        if not result:
            raise HTTPException(status_code=404, detail="Report not found")
        
        return ReportResponse(
            id=result.id,
            company_name=result.company_name,
            topic=result.topic,
            report_content=result.report_content,
            toc_text=result.toc_text,
            references_data=result.references_data,
            meta_info=result.meta_info,
            model_name=result.model_name,
            created_at=result.created_at.isoformat(),
            status=result.status
        )
    ```
    
    현재 동작 (Mock):
    - backend/assets/sample_report.md 파일을 읽어서 반환
    - DB 조회 시뮬레이션
    """
    # Mock: 파일 기반 데이터 로드
    report_content = load_sample_report()
    
    # Mock: TOC 추출 (실제로는 STORM 엔진이 생성)
    toc_text = """1. 기업 개요
2. 사업 현황 및 전략
3. 재무 성과 분석
4. 기술 경쟁력 및 R&D
5. 시장 환경 및 경쟁사 비교
6. 리스크 및 기회 요인
7. 종합 평가 및 전망"""
    
    # Mock: References (실제로는 PostgresRM이 반환한 검색 결과)
    references_data = [
        {
            "source": "DART 2024년 3분기 사업보고서",
            "content": "SK하이닉스의 2024년 3분기 매출액은 17.5조 원으로 전년 동기 대비 94.2% 증가...",
            "relevance_score": 0.95
        },
        {
            "source": "Gartner Semiconductor Market Forecast",
            "content": "메모리 반도체 시장은 2024년부터 AI 데이터센터 수요 증가로 연평균 12.8% 성장 전망...",
            "relevance_score": 0.89
        },
        {
            "source": "TechInsights HBM Market Analysis",
            "content": "SK하이닉스의 HBM3E는 NVIDIA H100/H200 GPU에 독점 공급되며, 2025년까지 공급 물량 완판...",
            "relevance_score": 0.92
        }
    ]
    
    # Mock: Meta Info (실제로는 STORM 실행 로그)
    meta_info = {
        "search_queries": [
            "SK하이닉스 재무 현황",
            "HBM 시장 전망",
            "메모리 반도체 경쟁 구도"
        ],
        "retrieval_count": 25,
        "generation_config": {
            "model": "gpt-4o",
            "temperature": 1.0,
            "max_conv_turn": 3,
            "max_perspective": 5
        },
        "execution_time_seconds": 127.5
    }
    
    return ReportResponse(
        id=id,
        company_name="SK하이닉스",
        topic="종합 분석",
        report_content=report_content,
        toc_text=toc_text,
        references_data=references_data,
        meta_info=meta_info,
        model_name="gpt-4o",
        created_at=datetime.now().isoformat(),
        status="completed"
    )


@app.get("/api/reports", response_model=ReportListResponse)
async def list_reports(limit: int = 10, offset: int = 0):
    """
    [GET] 리포트 목록 조회 (Mock)
    
    실제 동작 (차후 구현):
    - Generated_Reports 테이블에서 최신순 정렬 조회
    - Pagination 지원
    
    현재 동작 (Mock):
    - 하드코딩된 샘플 데이터 반환
    """
    # Mock: 샘플 리포트 목록
    mock_reports = [
        {
            "id": 1,
            "company_name": "SK하이닉스",
            "topic": "종합 분석",
            "created_at": "2026-01-15T10:30:00",
            "status": "completed"
        },
        {
            "id": 2,
            "company_name": "삼성전자",
            "topic": "반도체 사업 분석",
            "created_at": "2026-01-14T15:20:00",
            "status": "completed"
        },
        {
            "id": 3,
            "company_name": "NAVER",
            "topic": "AI 기술 현황",
            "created_at": "2026-01-13T09:45:00",
            "status": "completed"
        }
    ]
    
    return ReportListResponse(
        total=len(mock_reports),
        reports=mock_reports[offset:offset+limit]
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
   uvicorn backend.main:app --reload --port 8000
   
   # 프로덕션 모드
   uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 4

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
- [ ] src/common/db_connection.py 연동
- [ ] PostgresRM 기반 실제 검색 구현
- [ ] STORM 엔진 통합
- [ ] 비동기 작업 큐 (Celery/Redis)
- [ ] 인증/권한 관리 (JWT)
"""
