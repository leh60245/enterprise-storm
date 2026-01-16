"""DB 메타데이터 정합성 진단 스크립트"""
import psycopg2
from psycopg2.extras import RealDictCursor
import json

conn = psycopg2.connect(host='localhost', port=5432, database='postgres', user='postgres', password='1234')
cur = conn.cursor(cursor_factory=RealDictCursor)

# 1. 현대엔지니어링 데이터 메타데이터 확인
print('=== 현대엔지니어링 메타데이터 확인 ===')
cur.execute("""
    SELECT id, metadata, LENGTH(raw_content) as content_len 
    FROM "Source_Materials" 
    WHERE raw_content LIKE '%현대엔지니어링%' 
    LIMIT 5;
""")
rows = cur.fetchall()
if rows:
    for r in rows:
        print(f'ID: {r["id"]}, content_len: {r["content_len"]}')
        meta = r["metadata"]
        print(f'  metadata: {json.dumps(meta, ensure_ascii=False, indent=2) if meta else "NULL"}')
else:
    print('현대엔지니어링 관련 데이터 없음!')

# 2. 전체 메타데이터에서 company_name 유무 통계
print()
print('=== 전체 Source_Materials 메타데이터 통계 ===')
cur.execute('SELECT COUNT(*) FROM "Source_Materials"')
total = cur.fetchone()['count']

cur.execute('SELECT COUNT(*) FROM "Source_Materials" WHERE metadata IS NULL')
null_meta = cur.fetchone()['count']

cur.execute("SELECT COUNT(*) FROM \"Source_Materials\" WHERE metadata->>'company_name' IS NOT NULL")
has_company = cur.fetchone()['count']

cur.execute('SELECT COUNT(*) FROM "Source_Materials" WHERE embedding IS NOT NULL')
has_embed = cur.fetchone()['count']

print(f'총 레코드: {total}')
print(f'metadata=NULL: {null_meta}')
print(f'company_name 있음: {has_company}')
print(f'embedding 있음: {has_embed}')

# 3. company_name 값 분포 (distinct)
print()
print('=== company_name 값 분포 (상위 20개) ===')
cur.execute("""
    SELECT metadata->>'company_name' as company, COUNT(*) as cnt 
    FROM "Source_Materials" 
    WHERE metadata->>'company_name' IS NOT NULL 
    GROUP BY metadata->>'company_name' 
    ORDER BY cnt DESC 
    LIMIT 20;
""")
for r in cur.fetchall():
    print(f'  {r["company"]}: {r["cnt"]}개')

# 4. embedding이 NULL인 레코드 수
print()
print('=== 임베딩 상태 ===')
cur.execute('SELECT COUNT(*) FROM "Source_Materials" WHERE embedding IS NULL')
no_embed = cur.fetchone()['count']
print(f'embedding=NULL: {no_embed}개')
print(f'embedding 비율: {(has_embed/total*100) if total > 0 else 0:.1f}%')

conn.close()
