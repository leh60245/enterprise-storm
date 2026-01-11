"""
데이터 수집 패키지 (Ingestion Package)

DART API를 통한 사업보고서 수집 및 DB 적재를 담당합니다.
이 패키지는 데이터를 "집어넣는(Write)" 역할에 집중합니다.

구성:
- dart_agent: DART API 연동 및 보고서 파싱
- db_manager: DB CRUD 작업 (Source_Materials 삽입/수정)
- pipeline: 데이터 수집 오케스트레이션
- embedding_worker: 임베딩 생성 워커
"""

# DB 관련은 항상 import (의존성 적음)
from .db_manager import DBManager


# 나머지는 lazy import (무거운 의존성)
def __getattr__(name):
    if name == "DartReportAgent":
        from .dart_agent import DartReportAgent
        return DartReportAgent
    elif name == "DataPipeline":
        from .pipeline import DataPipeline
        return DataPipeline
    elif name == "ContextLookbackEmbeddingWorker":
        from .embedding_worker import ContextLookbackEmbeddingWorker
        return ContextLookbackEmbeddingWorker
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "DartReportAgent",
    "DBManager",
    "DataPipeline",
    "ContextLookbackEmbeddingWorker",
]
