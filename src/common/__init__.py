"""
공통 모듈 (Common Module)

AI와 Ingestion 양쪽에서 공유하는 핵심 컴포넌트:
- config: 전역 설정 (API 키, DB 접속 정보, 모델 설정)
- db_connection: 통합 DB 연결 관리
- embedding: 통합 임베딩 서비스 (OpenAI/HuggingFace)
- utils: 공통 유틸리티 함수
"""

from .config import AI_CONFIG, BATCH_CONFIG, DART_CONFIG, DB_CONFIG, EMBEDDING_CONFIG
from .embedding import EmbeddingService

__all__ = [
    "DB_CONFIG",
    "EMBEDDING_CONFIG",
    "DART_CONFIG",
    "BATCH_CONFIG",
    "AI_CONFIG",
    "EmbeddingService",
]
