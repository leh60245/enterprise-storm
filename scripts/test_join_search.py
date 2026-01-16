"""
FIX-Search-002 테스트: JOIN 기반 검색이 현대엔지니어링 데이터를 찾는지 확인
"""
import os
import sys
import toml

# 프로젝트 루트 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# secrets.toml 로드
secrets_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'secrets.toml')
with open(secrets_path, 'r') as f:
    secrets = toml.load(f)
for k, v in secrets.items():
    os.environ[k] = str(v)

from knowledge_storm.db import PostgresConnector

print("=" * 60)
print("FIX-Search-002 테스트: JOIN 기반 기업명 필터링")
print("=" * 60)

conn = PostgresConnector()

# Test 1: 현대엔지니어링 검색
print("\n[Test 1] 현대엔지니어링 검색 (company_filter='현대엔지니어링')")
results = conn.search('기업 개요', top_k=5, company_filter='현대엔지니어링')
print(f"  → Found {len(results)} results")
for i, r in enumerate(results[:3], 1):
    company = r.get('_company_name', 'N/A')
    title = r.get('title', 'N/A')[:40]
    score = r.get('score', 0)
    print(f"    [{i}] {title}... | Company: {company} | Score: {score:.4f}")

# Test 2: 삼성전자 검색 (비교용)
print("\n[Test 2] 삼성전자 검색 (company_filter='삼성전자')")
results2 = conn.search('재무 현황', top_k=5, company_filter='삼성전자')
print(f"  → Found {len(results2)} results")
for i, r in enumerate(results2[:3], 1):
    company = r.get('_company_name', 'N/A')
    title = r.get('title', 'N/A')[:40]
    score = r.get('score', 0)
    print(f"    [{i}] {title}... | Company: {company} | Score: {score:.4f}")

# Test 3: 필터 없이 검색
print("\n[Test 3] 필터 없이 검색 (company_filter=None)")
results3 = conn.search('사업 내용', top_k=5, company_filter=None)
print(f"  → Found {len(results3)} results")
for i, r in enumerate(results3[:3], 1):
    company = r.get('_company_name', 'N/A')
    title = r.get('title', 'N/A')[:40]
    print(f"    [{i}] {title}... | Company: {company}")

conn.close()

print("\n" + "=" * 60)
if len(results) > 0:
    print("✅ FIX-Search-002 성공: 현대엔지니어링 데이터 검색 가능!")
else:
    print("❌ FIX-Search-002 실패: 현대엔지니어링 데이터 여전히 검색 불가")
print("=" * 60)
