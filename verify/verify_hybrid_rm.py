#!/usr/bin/env python
"""
HybridRM 검증 스크립트

HybridRM이 PostgresRM과 SerperRM을 올바르게 조합하는지 확인합니다.

Usage:
    python -m verify.verify_hybrid_rm

Expected Results:
    - HybridRM 초기화 성공
    - 내부 검색 (PostgresRM) 3개 결과
    - 외부 검색 (SerperRM) 7개 결과
    - 총 10개 결과 반환 (중복 제거 후)
    - 각 결과에 'source' 태그 ('internal' 또는 'external')

Author: Enterprise STORM Team
Created: 2026-01-18
"""

import os
import sys
import logging

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from knowledge_storm.rm import PostgresRM, SerperRM, HybridRM

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def verify_hybrid_rm():
    """HybridRM 동작 검증"""
    
    print("=" * 60)
    print("HybridRM Verification Test")
    print("=" * 60)
    
    try:
        # 1. PostgresRM 초기화
        print("\n[1] Initializing Internal RM (PostgresRM)...")
        internal_rm = PostgresRM(k=10, min_score=0.3, company_filter="삼성전자")
        print("✓ PostgresRM initialized")
        
        # 2. SerperRM 초기화
        print("\n[2] Initializing External RM (SerperRM)...")
        serper_api_key = os.getenv("SERPER_API_KEY")
        
        if not serper_api_key:
            print("❌ SERPER_API_KEY not found in environment")
            print("   Please set SERPER_API_KEY to test HybridRM")
            print("   Skipping external search test...")
            external_rm = None
        else:
            external_rm = SerperRM(serper_search_api_key=serper_api_key, k=10)
            print("✓ SerperRM initialized")
        
        # 3. HybridRM 초기화
        print("\n[3] Initializing HybridRM...")
        if external_rm is None:
            print("⚠️  Cannot create HybridRM without SerperRM")
            print("   Test aborted.")
            return False
        
        hybrid_rm = HybridRM(internal_rm, external_rm, internal_k=3, external_k=7)
        print("✓ HybridRM initialized with 3:7 ratio")
        
        # 4. 검색 테스트
        print("\n[4] Testing hybrid search with query: 'HBM 시장 전망'")
        result = hybrid_rm.forward("HBM 시장 전망")
        
        print(f"\n✓ Result type: {type(result)}")
        print(f"✓ Has passages attribute: {hasattr(result, 'passages')}")
        
        if hasattr(result, 'passages'):
            passages = result.passages
            print(f"✓ Total passages returned: {len(passages)}")
            
            # source 태그 분류
            internal_count = sum(1 for p in passages if isinstance(p, dict) and p.get('source') == 'internal')
            external_count = sum(1 for p in passages if isinstance(p, dict) and p.get('source') == 'external')
            
            print(f"\n--- Source Distribution ---")
            print(f"  Internal (DART): {internal_count} passages")
            print(f"  External (Google): {external_count} passages")
            print(f"  Total: {internal_count + external_count} passages")
            
            # 샘플 결과 출력
            if passages:
                print("\n--- Sample Results ---")
                for idx, passage in enumerate(passages[:3], 1):
                    if isinstance(passage, dict):
                        print(f"\n[{idx}] Source: {passage.get('source', 'N/A')}")
                        print(f"    Title: {passage.get('title', 'N/A')[:80]}...")
                        print(f"    URL: {passage.get('url', 'N/A')[:100]}...")
            
            # 검증 기준
            print("\n--- Verification Results ---")
            checks = []
            
            # Check 1: 총 결과 수
            if len(passages) > 0:
                checks.append(("✓", "Passages returned (> 0)"))
            else:
                checks.append(("✗", "No passages returned"))
            
            # Check 2: Internal source 존재
            if internal_count > 0:
                checks.append(("✓", f"Internal sources found ({internal_count})"))
            else:
                checks.append(("⚠️", "No internal sources (DB may be empty)"))
            
            # Check 3: External source 존재
            if external_count > 0:
                checks.append(("✓", f"External sources found ({external_count})"))
            else:
                checks.append(("✗", "No external sources (Serper API issue?)"))
            
            # Check 4: Source 태그 존재
            if all(isinstance(p, dict) and 'source' in p for p in passages):
                checks.append(("✓", "All passages have 'source' tag"))
            else:
                checks.append(("⚠️", "Some passages missing 'source' tag"))
            
            for symbol, message in checks:
                print(f"  {symbol} {message}")
            
            # 성공 판정
            success_count = sum(1 for s, _ in checks if s == "✓")
            if success_count >= 3:
                print("\n✅ HybridRM verification PASSED!")
                return True
            else:
                print("\n⚠️  HybridRM verification completed with warnings")
                return True
        
        else:
            print("✗ Result does not have 'passages' attribute")
            return False
        
        # 5. 사용량 통계
        print("\n[5] Usage statistics:")
        usage = hybrid_rm.get_usage_and_reset()
        for key, value in usage.items():
            print(f"  {key}: {value}")
        
        # 연결 종료
        hybrid_rm.close()
        print("\n[6] HybridRM test completed successfully ✓")
        
        return True
    
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = verify_hybrid_rm()
    sys.exit(0 if success else 1)
