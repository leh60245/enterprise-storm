#!/usr/bin/env python
"""
데이터 수집 파이프라인 실행 스크립트 (run_ingestion.py)

DART 사업보고서 데이터를 수집하여 PostgreSQL DB에 적재합니다.

사용법:
    # 테스트 모드 (3개 기업)
    python -m scripts.run_ingestion --test

    # 효율 모드 (사업보고서가 있는 기업만)
    python -m scripts.run_ingestion --efficient

    # 특정 종목코드 처리
    python -m scripts.run_ingestion --codes 005930,000660

    # 임베딩 생성
    python -m scripts.run_ingestion --embed

    # DB 통계 조회
    python -m scripts.run_ingestion --stats
"""
import sys
import os
import argparse

# 프로젝트 루트를 path에 추가
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


def run_test_mode():
    """테스트 모드: 삼성전자, SK하이닉스, NAVER 3개 기업"""
    from src.ingestion import DataPipeline

    pipeline = DataPipeline()
    pipeline.run_test()


def run_efficient_mode(reset_db: bool = False, limit: int = None, bgn_de: str = None, end_de: str = None):
    """효율 모드: 사업보고서가 있는 기업만 처리"""
    from src.ingestion import DataPipeline

    pipeline = DataPipeline()
    pipeline.run_efficient(bgn_de=bgn_de, end_de=end_de, reset_db=reset_db, limit=limit)


def run_custom_mode(stock_codes: list, reset_db: bool = False):
    """커스텀 모드: 특정 종목코드 리스트 처리"""
    from src.ingestion import DataPipeline

    pipeline = DataPipeline()
    pipeline.run(stock_codes=stock_codes, reset_db=reset_db)


def run_embed_mode(batch_size: int = 32, limit: int = None, force: bool = False):
    """임베딩 생성 모드 (Context Look-back 방식)"""
    from src.ingestion import ContextLookbackEmbeddingWorker

    worker = ContextLookbackEmbeddingWorker(batch_size=batch_size)
    worker.run(limit=limit, force=force)


def run_stats_mode():
    """DB 통계 조회"""
    from src.ingestion import DBManager

    print("\n[STATS] DB Statistics")
    print("=" * 40)

    with DBManager() as db:
        stats = db.get_stats()
        print(f"   Companies: {stats['companies']}")
        print(f"   Reports: {stats['reports']}")
        print(f"   Source Materials: {stats['materials']}")
        print(f"   Embedded: {stats['embedded_materials']}")
        print(f"   Generated Reports: {stats['generated_reports']}")

        if stats['materials'] > 0:
            embed_rate = (stats['embedded_materials'] / stats['materials']) * 100
            print(f"   Embedding Rate: {embed_rate:.1f}%")

    print("=" * 40)


def main():
    parser = argparse.ArgumentParser(
        description="DART Data Ingestion Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Test mode (Samsung, SK Hynix, NAVER)
    python -m scripts.run_ingestion --test
    
    # Efficient mode (companies with annual reports)
    python -m scripts.run_ingestion --efficient
    
    # Specific companies
    python -m scripts.run_ingestion --codes 005930,000660,035420
    
    # Generate embeddings
    python -m scripts.run_ingestion --embed --batch-size 64
    
    # DB statistics
    python -m scripts.run_ingestion --stats
"""
    )

    # 실행 모드 (상호 배타적)
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument('--test', action='store_true', help='Test mode (3 companies)')
    mode_group.add_argument('--efficient', action='store_true', help='Efficient mode (companies with reports)')
    mode_group.add_argument('--codes', type=str, help='Stock codes (comma separated)')
    mode_group.add_argument('--embed', action='store_true', help='Embedding generation mode')
    mode_group.add_argument('--stats', action='store_true', help='DB statistics')

    # 공통 옵션
    parser.add_argument('--reset-db', action='store_true', help='Reset DB before execution')
    parser.add_argument('--limit', type=int, help='Max companies to process')
    parser.add_argument('--bgn-de', type=str, help='Search start date (YYYYMMDD)')
    parser.add_argument('--end-de', type=str, help='Search end date (YYYYMMDD)')

    # 임베딩 옵션
    parser.add_argument('--batch-size', type=int, default=32, help='Embedding batch size')
    parser.add_argument('--force', action='store_true', help='Regenerate existing embeddings')

    args = parser.parse_args()

    if args.test:
        run_test_mode()
    elif args.efficient:
        run_efficient_mode(
            reset_db=args.reset_db,
            limit=args.limit,
            bgn_de=args.bgn_de,
            end_de=args.end_de
        )
    elif args.codes:
        stock_codes = [code.strip() for code in args.codes.split(',')]
        run_custom_mode(stock_codes, reset_db=args.reset_db)
    elif args.embed:
        run_embed_mode(
            batch_size=args.batch_size,
            limit=args.limit,
            force=args.force
        )
    elif args.stats:
        run_stats_mode()


if __name__ == "__main__":
    main()

