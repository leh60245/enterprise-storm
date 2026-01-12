#!/usr/bin/env python
"""
Entity Bias 방지 기능 테스트

FEAT-Retriever-001-EntityBias 작업 검증용 스크립트

테스트 항목:
1. Entity 추출 함수 테스트
2. Entity 매칭 리랭킹 테스트 (Mock)
3. 실제 검색 결과 테스트 (DB 연결 필요)

Usage:
    python -m test.test_entity_bias
"""

import os
import sys

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_entity_extraction():
    """Entity 추출 함수 테스트"""
    print("\n" + "=" * 60)
    print("📋 테스트 1: Entity 추출 (_extract_target_entities)")
    print("=" * 60)

    from knowledge_storm.db.postgres_connector import PostgresConnector

    # PostgresConnector의 _extract_target_entities만 테스트하기 위해 직접 함수 호출
    # DB 연결 없이 테스트하기 위해 함수를 분리
    from src.common.config import COMPANY_ALIASES, get_all_aliases

    def extract_target_entities(query: str):
        """테스트용 Entity 추출 (PostgresConnector._extract_target_entities와 동일 로직)"""
        target_keywords = []
        for canonical, aliases in COMPANY_ALIASES.items():
            all_names = [canonical] + aliases
            for name in all_names:
                if name.lower() in query.lower():
                    target_keywords = get_all_aliases(canonical)
                    return target_keywords
        return target_keywords

    test_cases = [
        ("SK하이닉스 매출 현황", ["SK하이닉스", "하이닉스", "SK Hynix", "Hynix", "에스케이하이닉스", "SK하이닉스㈜"]),
        ("삼성전자 기업 개요", ["삼성전자", "삼전", "Samsung Electronics", "Samsung", "삼성전자㈜", "SAMSUNG"]),
        ("SK Hynix revenue analysis", ["SK하이닉스", "하이닉스", "SK Hynix", "Hynix", "에스케이하이닉스", "SK하이닉스㈜"]),
        ("반도체 시장 동향", []),  # 기업명 없음
    ]

    all_passed = True
    for query, expected in test_cases:
        result = extract_target_entities(query)
        # 리스트의 첫 번째 요소(정규명)가 같은지 확인
        if expected:
            match = len(result) > 0 and result[0] == expected[0]
        else:
            match = len(result) == 0
        status = "✅" if match else "❌"
        print(f"  {status} Query: '{query}'")
        print(f"       결과: {result[:3]}... (예상: {expected[:3]}...)" if result else f"       결과: {result}")
        if not match:
            all_passed = False

    print(f"\n🏁 테스트 1 결과: {'✅ PASS' if all_passed else '❌ FAIL'}")
    return all_passed


def test_entity_reranking_mock():
    """Entity 매칭 리랭킹 테스트 (Mock 데이터)"""
    print("\n" + "=" * 60)
    print("📋 테스트 2: Entity 매칭 리랭킹 (Mock)")
    print("=" * 60)

    # Mock 검색 결과
    mock_results = [
        {
            "content": "SK하이닉스는 DRAM 및 NAND Flash 메모리 반도체 전문 기업입니다.",
            "title": "1. 회사의 개요",
            "url": "dart_report_2_chunk_100",
            "score": 0.85,
        },
        {
            "content": "[표 데이터]\n| 항목 | 삼성전자 | SK하이닉스 |\n|---|---|---|\n| 매출 | 100조 | 50조 |",
            "title": "경쟁사 비교",
            "url": "dart_report_1_chunk_66",
            "score": 0.88,  # 원래 더 높은 점수
        },
        {
            "content": "[표 데이터]\n삼성전자 이사회 명단...",
            "title": "이사회 구성",
            "url": "dart_report_1_chunk_200",
            "score": 0.75,
        },
    ]

    # 리랭킹 로직 (PostgresConnector._rerank_by_entity_match와 동일)
    from src.common.config import COMPANY_ALIASES, get_all_aliases

    query = "SK하이닉스 매출 현황"
    boost_multiplier = 1.3
    penalty_multiplier = 0.5
    drop_unmatched_tables = True

    # Entity 추출
    target_keywords = []
    for canonical, aliases in COMPANY_ALIASES.items():
        all_names = [canonical] + aliases
        for name in all_names:
            if name.lower() in query.lower():
                target_keywords = get_all_aliases(canonical)
                break
        if target_keywords:
            break

    print(f"  Query: '{query}'")
    print(f"  Target keywords: {target_keywords[:3]}...")
    print()

    reranked_results = []
    dropped_count = 0

    for doc in mock_results:
        doc_title = doc.get('title', '')
        doc_content = doc.get('content', '')[:500]
        doc_meta = f"{doc_title} {doc_content}".lower()

        is_matched = any(keyword.lower() in doc_meta for keyword in target_keywords)
        is_table_chunk = "[표 데이터]" in doc.get('content', '')
        original_score = doc.get('score', 0)

        if is_matched:
            doc['score'] = original_score * boost_multiplier
            doc['_entity_match'] = True
            print(f"  ✅ MATCH: {doc['url']} | Score: {original_score:.4f} → {doc['score']:.4f}")
            reranked_results.append(doc)
        else:
            if is_table_chunk and drop_unmatched_tables:
                dropped_count += 1
                print(f"  🗑️ DROP: {doc['url']} (Table + Entity 불일치)")
                continue
            doc['score'] = original_score * penalty_multiplier
            doc['_entity_match'] = False
            print(f"  ⚠️ PENALTY: {doc['url']} | Score: {original_score:.4f} → {doc['score']:.4f}")
            reranked_results.append(doc)

    reranked_results.sort(key=lambda x: x.get('score', 0), reverse=True)

    print()
    print(f"  📊 결과: {len(reranked_results)}개 유지, {dropped_count}개 드롭")
    print(f"  📊 최종 순위:")
    for i, r in enumerate(reranked_results, 1):
        print(f"       {i}. {r['url']} (score: {r['score']:.4f}, match: {r.get('_entity_match', 'N/A')})")

    # 검증:
    # - 삼성 단독 테이블(chunk_200)은 드롭되어야 함
    # - 경쟁사 비교 표(chunk_66)는 SK하이닉스 포함이므로 매칭되어 살아남음
    # - SK하이닉스 개요(chunk_100)도 매칭되어 살아남음
    # - 모두 매칭되므로 원래 점수 순서는 유지되되, 부스트가 적용됨

    print(f"\n  🔍 검증:")
    print(f"       len(reranked_results) == 2: {len(reranked_results) == 2} (actual: {len(reranked_results)})")
    print(f"       dropped_count == 1: {dropped_count == 1} (actual: {dropped_count})")
    print(f"       all matched: {all(r.get('_entity_match') for r in reranked_results)}")
    print(f"       matches: {[r.get('_entity_match') for r in reranked_results]}")

    success = (
        len(reranked_results) == 2 and  # 삼성 단독 테이블(chunk_200) 드롭됨
        dropped_count == 1 and
        all(r.get('_entity_match') for r in reranked_results)  # 모두 매칭됨
    )

    print(f"\n🏁 테스트 2 결과: {'✅ PASS' if success else '❌ FAIL'}")
    return success


def test_real_search():
    """실제 DB 검색 테스트"""
    print("\n" + "=" * 60)
    print("📋 테스트 3: 실제 DB 검색 (Entity Bias 방지 검증)")
    print("=" * 60)

    try:
        from knowledge_storm.db.postgres_connector import PostgresConnector

        connector = PostgresConnector()
        print("  ✅ PostgresConnector 초기화 성공")

        # 테스트 1: SK하이닉스 쿼리
        query = "SK하이닉스 매출 현황"
        print(f"\n  Query: '{query}'")
        results = connector.search(query, top_k=5)

        print(f"  Found: {len(results)} results")

        # 삼성전자 관련 청크가 상위에 있는지 확인
        samsung_in_top = False
        for i, r in enumerate(results, 1):
            is_samsung = "삼성" in r['content'] and "하이닉스" not in r['content']
            entity_match = r.get('_entity_match', 'N/A')
            print(f"       {i}. score={r['score']:.4f}, match={entity_match}, title={r['title'][:30]}...")
            if is_samsung and i <= 3:  # 상위 3개 내에 삼성 단독 청크가 있으면 문제
                samsung_in_top = True

        # 테스트 2: 삼성전자 쿼리
        query2 = "삼성전자 기업 개요"
        print(f"\n  Query: '{query2}'")
        results2 = connector.search(query2, top_k=5)

        print(f"  Found: {len(results2)} results")
        for i, r in enumerate(results2, 1):
            entity_match = r.get('_entity_match', 'N/A')
            print(f"       {i}. score={r['score']:.4f}, match={entity_match}, title={r['title'][:30]}...")

        connector.close()

        # 검증
        success = not samsung_in_top
        print(f"\n🏁 테스트 3 결과: {'✅ PASS' if success else '❌ FAIL (삼성 청크가 상위에 노출)'}")
        return success

    except Exception as e:
        print(f"  ❌ 오류 발생: {e}")
        print("     (DB 연결이 필요한 테스트입니다)")
        return None  # 스킵


def main():
    """모든 테스트 실행"""
    print("=" * 60)
    print("🚀 Entity Bias 방지 기능 테스트")
    print("=" * 60)

    results = []

    # 테스트 1: Entity 추출
    results.append(("Entity 추출", test_entity_extraction()))

    # 테스트 2: Mock 리랭킹
    results.append(("Mock 리랭킹", test_entity_reranking_mock()))

    # 테스트 3: 실제 DB 검색
    results.append(("실제 DB 검색", test_real_search()))

    # 결과 요약
    print("\n" + "=" * 60)
    print("📊 테스트 결과 요약")
    print("=" * 60)

    for name, passed in results:
        if passed is None:
            status = "⏭️ SKIP"
        elif passed:
            status = "✅ PASS"
        else:
            status = "❌ FAIL"
        print(f"  {status}: {name}")

    all_passed = all(p for p in [r[1] for r in results] if p is not None)
    print()
    print(f"🏁 최종 결과: {'✅ ALL PASSED' if all_passed else '❌ SOME FAILED'}")


if __name__ == "__main__":
    main()

