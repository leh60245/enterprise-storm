"""
다중 기업 데이터 격리 검증 스크립트

Task 014: 메타데이터 기반 기업별 데이터 격리 검증
- Source_Materials 테이블의 metadata->>'company_name' 기준 통계
- NULL company_name 존재 여부 확인
- 기업별 데이터 분포 리포트

사용법:
    python scripts/verify_company_isolation.py
"""
import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# [통합 아키텍처] src.ingestion 사용
from src.ingestion import DBManager


def verify_company_isolation():
    """기업별 데이터 격리 상태 검증"""

    print("\n" + "=" * 70)
    print("🔍 다중 기업 데이터 격리 검증 (Task 014)")
    print("=" * 70)

    with DBManager() as db:
        # 1. 기업별 데이터 개수 조회
        print("\n📊 1. 기업별 Source_Materials 데이터 개수")
        print("-" * 70)

        sql_company_stats = """
            SELECT 
                metadata->>'company_name' as company_name,
                COUNT(*) as total_count,
                SUM(CASE WHEN chunk_type = 'text' THEN 1 ELSE 0 END) as text_count,
                SUM(CASE WHEN chunk_type = 'table' THEN 1 ELSE 0 END) as table_count,
                SUM(CASE WHEN embedding IS NOT NULL THEN 1 ELSE 0 END) as embedded_count
            FROM "Source_Materials"
            GROUP BY metadata->>'company_name'
            ORDER BY total_count DESC;
        """
        db.cursor.execute(sql_company_stats)
        rows = db.cursor.fetchall()

        print(f"{'기업명':<20} {'전체':<10} {'텍스트':<10} {'테이블':<10} {'임베딩완료':<12}")
        print("-" * 70)

        total_all = 0
        null_count = 0
        company_count = 0

        for row in rows:
            company = row[0] if row[0] else "(NULL - 미지정)"
            total = row[1]
            text = row[2]
            table = row[3]
            embedded = row[4]

            total_all += total
            if row[0] is None:
                null_count = total
            else:
                company_count += 1

            print(f"{company:<20} {total:<10} {text:<10} {table:<10} {embedded:<12}")

        print("-" * 70)
        print(f"{'합계':<20} {total_all:<10}")

        # 2. NULL company_name 검사
        print("\n📊 2. 데이터 정합성 검사")
        print("-" * 70)

        if null_count > 0:
            print(f"⚠️  경고: company_name이 NULL인 레코드 {null_count}개 발견")
            print("   → 해결 방안: DB 리셋 후 재적재 또는 마이그레이션 스크립트 실행")

            # NULL 레코드의 report_id 샘플 조회
            sql_null_sample = """
                SELECT DISTINCT sm.report_id, ar.title, c.company_name
                FROM "Source_Materials" sm
                LEFT JOIN "Analysis_Reports" ar ON sm.report_id = ar.id
                LEFT JOIN "Companies" c ON ar.company_id = c.id
                WHERE sm.metadata->>'company_name' IS NULL
                LIMIT 5;
            """
            db.cursor.execute(sql_null_sample)
            null_samples = db.cursor.fetchall()

            if null_samples:
                print("\n   NULL 레코드 샘플 (report_id 기준):")
                for sample in null_samples:
                    inferred_company = sample[2] or "알 수 없음"
                    print(f"   - Report ID: {sample[0]}, Title: {sample[1][:40]}..., 추론 기업: {inferred_company}")
        else:
            print("✅ 모든 레코드에 company_name이 정상적으로 포함되어 있습니다.")

        # 3. 성공 기준 검증
        print("\n📊 3. 성공 기준 검증")
        print("-" * 70)

        target_companies = ["삼성전자", "SK하이닉스", "현대자동차"]
        found_companies = [row[0] for row in rows if row[0]]

        all_found = True
        for company in target_companies:
            if company in found_companies:
                print(f"✅ {company}: 데이터 존재")
            else:
                print(f"❌ {company}: 데이터 없음")
                all_found = False

        # 4. 최종 결과
        print("\n" + "=" * 70)
        print("📋 최종 검증 결과")
        print("=" * 70)

        if null_count == 0 and all_found:
            print("✅ SUCCESS: 모든 검증 조건 충족")
            print(f"   - 등록된 기업 수: {company_count}")
            print(f"   - 전체 데이터 수: {total_all}")
            print(f"   - NULL company_name: 0건")
        else:
            print("⚠️  PENDING: 일부 조건 미충족")
            if null_count > 0:
                print(f"   - NULL company_name: {null_count}건 (수정 필요)")
            if not all_found:
                missing = [c for c in target_companies if c not in found_companies]
                print(f"   - 미적재 기업: {', '.join(missing)}")
                print("\n   💡 비교군 적재 명령어:")
                print("   python main.py --codes 000660 005380 --reset")
                print("   (000660: SK하이닉스, 005380: 현대자동차)")

        print("=" * 70 + "\n")


def migrate_null_company_names():
    """
    기존 레코드의 NULL company_name을 Companies 테이블에서 역추적하여 채우기
    (선택적 마이그레이션)
    """
    print("\n🔧 NULL company_name 마이그레이션")
    print("-" * 70)

    with DBManager() as db:
        sql_update = """
            UPDATE "Source_Materials" sm
            SET metadata = jsonb_set(
                COALESCE(sm.metadata, '{}'),
                '{company_name}',
                to_jsonb(c.company_name)
            )
            FROM "Analysis_Reports" ar
            JOIN "Companies" c ON ar.company_id = c.id
            WHERE sm.report_id = ar.id
              AND sm.metadata->>'company_name' IS NULL;
        """
        db.cursor.execute(sql_update)
        updated_count = db.cursor.rowcount
        db.conn.commit()

        print(f"✅ {updated_count}개 레코드의 company_name 업데이트 완료")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="다중 기업 데이터 격리 검증")
    parser.add_argument('--migrate', action='store_true',
                        help='NULL company_name 레코드 마이그레이션 실행')

    args = parser.parse_args()

    if args.migrate:
        migrate_null_company_names()

    verify_company_isolation()

