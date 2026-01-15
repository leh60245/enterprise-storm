#!/usr/bin/env python
"""
Entity Bias 방지 실전 검증 스크립트

실제 검색 결과를 출력하여 Entity Bias가 제거되었는지 확인
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from knowledge_storm.db.postgres_connector import PostgresConnector


def main():
    print("=" * 80)
    print("🔍 Entity Bias 방지 실전 검증")
    print("=" * 80)

    connector = PostgresConnector()

    # 테스트 케이스 1: SK하이닉스 검색
    print("\n[테스트 1] Query: 'SK하이닉스 기업 개요'")
    print("-" * 80)

    results = connector.search("SK하이닉스 기업 개요", top_k=10)

    print(f"총 {len(results)}개 결과:\n")

    for i, r in enumerate(results, 1):
        score = r.get('score', 0)
        title = r.get('title', 'N/A')
        url = r.get('url', 'N/A')
        entity_match = r.get('_entity_match', 'N/A')

        # 내용 미리보기 (첫 100자)
        content_preview = r.get('content', '')[:100].replace('\n', ' ')

        # 삼성전자 단독 청크 감지
        is_samsung_only = '삼성' in content_preview and 'SK' not in content_preview and '하이닉스' not in content_preview

        flag = "🚨" if is_samsung_only else "✅"

        print(f"{flag} [{i}] score={score:.4f} | match={entity_match}")
        print(f"     title: {title[:60]}")
        print(f"     url: {url}")
        print(f"     preview: {content_preview}...")
        print()

    # 삼성 단독 청크가 상위 5개에 있는지 확인
    top5_samsung_only = []
    for i, r in enumerate(results[:5], 1):
        content = r.get('content', '')
        if '삼성' in content and 'SK' not in content and '하이닉스' not in content:
            top5_samsung_only.append((i, r))

    print("=" * 80)
    if top5_samsung_only:
        print(f"❌ FAIL: 삼성전자 단독 청크가 Top 5에 {len(top5_samsung_only)}개 발견됨")
        for i, r in top5_samsung_only:
            print(f"   - Rank {i}: {r.get('url', 'N/A')}")
    else:
        print("✅ SUCCESS: Top 5에 삼성전자 단독 청크 없음 (Entity Bias 제거 성공)")

    # 테스트 케이스 2: 삼성전자 검색
    print("\n" + "=" * 80)
    print("[테스트 2] Query: '삼성전자 기업 개요'")
    print("-" * 80)

    results2 = connector.search("삼성전자 기업 개요", top_k=5)

    print(f"총 {len(results2)}개 결과:\n")

    for i, r in enumerate(results2, 1):
        score = r.get('score', 0)
        title = r.get('title', 'N/A')
        entity_match = r.get('_entity_match', 'N/A')
        content_preview = r.get('content', '')[:80].replace('\n', ' ')

        print(f"✅ [{i}] score={score:.4f} | match={entity_match}")
        print(f"     title: {title[:60]}")
        print(f"     preview: {content_preview}...")
        print()

    connector.close()

    print("=" * 80)
    print("🏁 검증 완료")


if __name__ == "__main__":
    main()

