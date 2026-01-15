#!/usr/bin/env python
"""
FEAT-002 실전 검증 스크립트

Dual Filtering과 Source Tagging이 실제로 작동하는지 확인
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from knowledge_storm.db.postgres_connector import PostgresConnector


def main():
    print("=" * 80)
    print("🔍 FEAT-002: Source Tagging + Dual Filtering 실전 검증")
    print("=" * 80)

    connector = PostgresConnector()

    # Test 1: Factoid 질문
    print("\n[테스트 1] Factoid 질문: 'SK하이닉스 회사의 개요'")
    print("-" * 80)

    results1 = connector.search("SK하이닉스 회사의 개요", top_k=5)

    print(f"총 {len(results1)}개 결과:\n")

    for i, r in enumerate(results1, 1):
        score = r.get('score', 0)
        title = r.get('title', 'N/A')[:50]
        content = r.get('content', '')

        # 출처 태그 확인
        lines = content.split('\n')
        source_line = lines[0] if lines else ''

        # 회사 확인
        if "SK하이닉스" in content or "하이닉스" in content:
            company_flag = "✅ SK"
        elif "삼성" in content:
            company_flag = "🚨 삼성"
        else:
            company_flag = "❓ 기타"

        print(f"{company_flag} [{i}] score={score:.4f}")
        print(f"     title: {title}")
        print(f"     source: {source_line[:70]}...")
        print()

    # Test 2: Analytical 질문 (기업 명시)
    print("=" * 80)
    print("[테스트 2] Analytical 질문: 'SK하이닉스 반도체 시장 점유율 분석'")
    print("-" * 80)

    results2 = connector.search("SK하이닉스 반도체 시장 점유율 분석", top_k=5)

    print(f"총 {len(results2)}개 결과:\n")

    for i, r in enumerate(results2, 1):
        score = r.get('score', 0)
        content = r.get('content', '')
        source_line = content.split('\n')[0] if content else ''

        if "SK하이닉스" in content or "하이닉스" in content:
            company_flag = "✅ SK"
        elif "삼성" in content:
            company_flag = "⚠️ 삼성"  # Analytical이므로 경고만
        else:
            company_flag = "❓ 기타"

        print(f"{company_flag} [{i}] score={score:.4f}")
        print(f"     source: {source_line[:70]}...")
        print()

    # Test 3: Analytical 질문 (기업 명시 없음)
    print("=" * 80)
    print("[테스트 3] Analytical 질문 (기업 미명시): '반도체 시장 동향'")
    print("-" * 80)

    results3 = connector.search("반도체 시장 동향", top_k=5)

    print(f"총 {len(results3)}개 결과:\n")

    for i, r in enumerate(results3, 1):
        content = r.get('content', '')
        source_line = content.split('\n')[0] if content else ''
        print(f"  [{i}] {source_line[:70]}...")

    connector.close()

    # 검증
    print("\n" + "=" * 80)
    print("📊 검증 결과")
    print("=" * 80)

    # 테스트 1: Factoid - 삼성 청크 없어야 함
    samsung_in_factoid = any("삼성" in r['content'] and "SK" not in r['content'] for r in results1)
    all_tagged_1 = all("[[출처:" in r['content'] for r in results1)

    # 테스트 2 & 3: Source Tag 적용 확인
    all_tagged_2 = all("[[출처:" in r['content'] for r in results2)
    all_tagged_3 = all("[[출처:" in r['content'] for r in results3)

    print(f"  Factoid 질문:")
    print(f"    - 삼성 단독 청크 제거: {'✅ PASS' if not samsung_in_factoid else '❌ FAIL'}")
    print(f"    - Source Tag 적용: {'✅ PASS' if all_tagged_1 else '❌ FAIL'}")
    print(f"  Analytical 질문 (기업 명시):")
    print(f"    - Source Tag 적용: {'✅ PASS' if all_tagged_2 else '❌ FAIL'}")
    print(f"  Analytical 질문 (기업 미명시):")
    print(f"    - Source Tag 적용: {'✅ PASS' if all_tagged_3 else '❌ FAIL'}")

    all_pass = not samsung_in_factoid and all_tagged_1 and all_tagged_2 and all_tagged_3

    print(f"\n🏁 최종 결과: {'✅ ALL PASSED' if all_pass else '❌ SOME FAILED'}")


if __name__ == "__main__":
    main()

