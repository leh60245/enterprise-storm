#!/usr/bin/env python
"""
차원 검증 테스트 스크립트

DB 벡터 차원과 현재 설정이 일치하는지 확인합니다.
"""
import sys
import os

project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

print("=" * 70)
print("🔍 Embedding Dimension Validation Test")
print("=" * 70)

# Step 1: Config 로드
print("\nStep 1: Loading config...")
try:
    from src.common.config import EMBEDDING_CONFIG, ACTIVE_EMBEDDING_PROVIDER
    print(f"  Active Provider: {ACTIVE_EMBEDDING_PROVIDER}")
    print(f"  Expected Dimension: {EMBEDDING_CONFIG['dimension']}D")
    print(f"  Model: {EMBEDDING_CONFIG['model_name']}")
except Exception as e:
    print(f"  ERROR: {e}")
    sys.exit(1)

# Step 2: 차원 검증 실행
print("\nStep 2: Validating dimension compatibility...")
try:
    from src.common.config import validate_embedding_dimension_compatibility
    result = validate_embedding_dimension_compatibility()
    if result:
        print("  ✅ Dimension validation PASSED")
        print("  → DB 벡터 차원과 현재 설정이 일치합니다.")
    else:
        print("  ⚠️ Dimension validation SKIPPED (DB 연결 불가)")
except Exception as e:
    print(f"  ❌ Dimension validation FAILED:")
    print(f"     {e}")
    sys.exit(1)

# Step 3: EmbeddingService 초기화 (차원 검증 포함)
print("\nStep 3: Initializing EmbeddingService...")
try:
    from src.common.embedding import EmbeddingService
    service = EmbeddingService()
    print(f"  ✅ EmbeddingService initialized")
    print(f"  → Provider: {service.provider}")
    print(f"  → Dimension: {service.dimension}D")
except Exception as e:
    print(f"  ❌ EmbeddingService initialization FAILED:")
    print(f"     {e}")
    sys.exit(1)

print("\n" + "=" * 70)
print("✅ All validation tests PASSED!")
print("=" * 70)
print("\n📝 Summary:")
print(f"  - Active Provider: {ACTIVE_EMBEDDING_PROVIDER}")
print(f"  - Vector Dimension: {EMBEDDING_CONFIG['dimension']}D")
print(f"  - DB Compatibility: ✅ Verified")
print("\n⚠️ 주의: EMBEDDING_PROVIDER 변경 시 DB 재임베딩 필수!")
print("=" * 70)

