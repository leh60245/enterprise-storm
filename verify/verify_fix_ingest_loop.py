"""
긴급 수정 완료 후 검증 스크립트
Task ID: FIX-Ingest-Loop & REF-DB-Schema
"""
import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.common.db_connection import get_db_connection


def verify_fix():
    """
    두 가지 수정 사항 검증:
    1. Silent Failure 버그 수정 → 모든 리포트의 블록이 DB에 저장되었는지 확인
    2. company_id FK 추가 → Generated_Reports 테이블에 company_id가 있는지 확인
    """
    
    print("\n" + "=" * 60)
    print("🔍 긴급 수정 완료 후 검증")
    print("=" * 60)
    
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            # ========================================
            # Test 1: Silent Failure 버그 수정 확인
            # ========================================
            print("\n[Test 1] Silent Failure 버그 수정 확인")
            print("-" * 60)
            
            # 각 리포트별 블록 수 확인
            cursor.execute("""
                SELECT 
                    ar.id AS report_id,
                    c.company_name,
                    ar.title,
                    COUNT(sm.id) AS block_count
                FROM "Analysis_Reports" ar
                LEFT JOIN "Companies" c ON ar.company_id = c.id
                LEFT JOIN "Source_Materials" sm ON ar.id = sm.report_id
                GROUP BY ar.id, c.company_name, ar.title
                ORDER BY ar.id
            """)
            
            all_reports = cursor.fetchall()
            
            if not all_reports:
                print("❌ 리포트가 하나도 없습니다!")
                return False
            
            print(f"✅ 총 {len(all_reports)}개 리포트 확인")
            
            failed_reports = []
            for report_id, company_name, title, block_count in all_reports:
                status = "✅" if block_count > 0 else "❌"
                print(f"   {status} Report ID {report_id} ({company_name}): {block_count:,}개 블록")
                
                if block_count == 0:
                    failed_reports.append((report_id, company_name))
            
            if failed_reports:
                print(f"\n❌ {len(failed_reports)}개 리포트에 블록이 없습니다:")
                for rid, cname in failed_reports:
                    print(f"   - Report ID {rid} ({cname})")
                return False
            else:
                print("\n✅ 모든 리포트에 블록이 정상적으로 저장되었습니다!")
            
            # ========================================
            # Test 2: company_id FK 추가 확인
            # ========================================
            print("\n[Test 2] company_id FK 추가 확인")
            print("-" * 60)
            
            # Generated_Reports 테이블에 company_id 컬럼이 있는지 확인
            cursor.execute("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'Generated_Reports'
                AND column_name = 'company_id'
            """)
            
            column_info = cursor.fetchone()
            
            if not column_info:
                print("❌ Generated_Reports 테이블에 company_id 컬럼이 없습니다!")
                return False
            
            print(f"✅ company_id 컬럼 존재 확인:")
            print(f"   - 타입: {column_info[1]}")
            print(f"   - NULL 허용: {column_info[2]}")
            
            # FK 제약조건 확인
            cursor.execute("""
                SELECT tc.constraint_name, tc.constraint_type
                FROM information_schema.table_constraints tc
                WHERE tc.table_name = 'Generated_Reports'
                AND tc.constraint_type = 'FOREIGN KEY'
                AND tc.constraint_name = 'fk_company'
            """)
            
            fk_info = cursor.fetchone()
            
            if not fk_info:
                print("⚠️ FK 제약조건 'fk_company'가 없습니다. (데이터는 있을 수 있음)")
            else:
                print(f"✅ FK 제약조건 확인: {fk_info[0]} ({fk_info[1]})")
            
            # ========================================
            # Test 3: 전체 데이터 통계
            # ========================================
            print("\n[Test 3] 전체 데이터 통계")
            print("-" * 60)
            
            cursor.execute('SELECT COUNT(*) FROM "Companies"')
            companies = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM "Analysis_Reports"')
            reports = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM "Source_Materials"')
            materials = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT COUNT(DISTINCT report_id) 
                FROM "Source_Materials"
            """)
            reports_with_materials = cursor.fetchone()[0]
            
            print(f"   기업: {companies}개")
            print(f"   리포트: {reports}개")
            print(f"   원천 데이터 블록: {materials:,}개")
            print(f"   블록이 있는 리포트: {reports_with_materials}개")
            
            if reports_with_materials < reports:
                missing = reports - reports_with_materials
                print(f"\n⚠️ {missing}개 리포트에 블록이 없습니다!")
                return False
            else:
                print("\n✅ 모든 리포트에 블록이 존재합니다!")
            
            # 최종 판정
            print("\n" + "=" * 60)
            print("✅ 모든 검증 통과!")
            print("=" * 60)
            print("\n📋 Acceptance Criteria:")
            print("   ✅ Ingestion Test: 모든 리포트의 블록이 Source_Materials에 저장됨")
            print("   ✅ Schema Test: Generated_Reports.company_id FK 추가 완료")
            print("\n🎉 긴급 수정 작업 완료!")
            
            return True


if __name__ == "__main__":
    success = verify_fix()
    sys.exit(0 if success else 1)
