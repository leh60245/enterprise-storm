"""
STORM Engine DB Adapter
엔진의 실행 결과를 DB에 저장하기 위한 어댑터입니다.
GenerationService를 사용하여 ORM 저장을 수행합니다.
"""

import logging
from typing import Any

from src.database import AsyncDatabaseEngine
from src.database.repositories import CompanyRepository, GeneratedReportRepository
from src.engine.io import find_topic_directory, load_storm_output_files
from src.services import GenerationService

logger = logging.getLogger(__name__)


async def save_storm_result_to_db(
    company_name: str,
    topic: str,
    output_dir: str,
    model_name: str,
    meta_info: dict[str, Any] = None, # type: ignore
) -> int | None:
    """
    STORM 결과 디렉토리를 읽어 DB에 저장합니다.

    Args:
        company_name: 기업명
        topic: 분석 주제
        output_dir: STORM 실행 루트 디렉토리 (타임스탬프 폴더)
        model_name: 사용된 모델명
        meta_info: 추가 메타정보 (job_id 등)

    Returns:
        saved_report_id (int) 또는 None
    """
    # 1. 실제 결과 데이터가 있는 하위 폴더 찾기
    topic_dir = find_topic_directory(output_dir)
    if not topic_dir:
        logger.error(f"Cannot find topic directory in {output_dir}")
        return None

    logger.info(f"Reading results from: {topic_dir}")

    # 2. 파일 로드 (IO 모듈 사용)
    data = load_storm_output_files(topic_dir)

    if not data["report_content"]:
        logger.error("Report content not found. Skipping DB save.")
        return None

    # 3. 메타데이터 병합
    final_meta = meta_info or {}
    final_meta.update(
        {
            "config": data["run_config"],
            "search_results_summary": f"Found {len(data['search_results'] or [])} results",
        }
    )

    # 4. DB 저장 (Async)
    # Adapter는 독립적인 세션 사이클을 가집니다.
    db_engine = AsyncDatabaseEngine()

    try:
        async with db_engine.get_session() as session:
            # 의존성 주입
            gen_repo = GeneratedReportRepository(session)
            comp_repo = CompanyRepository(session)
            service = GenerationService(gen_repo, comp_repo)

            # 4-1. Company ID 조회
            company = await comp_repo.get_by_name(company_name)
            if not company:
                logger.error(f"Company '{company_name}' not found in DB.")
                return None

            # 4-2. 리포트 저장
            report = await service.save_generated_report(
                company_name=company_name,
                company_id=company.id,
                topic=topic,
                report_content=data["report_content"],
                model_name=model_name,
                toc_text=data["toc_text"],
                references_data=data["references"],
                conversation_log=data["logs"],
                meta_info=final_meta,
            )

            logger.info(f"✅ Report saved to DB: ID {report.id} ({company_name})")
            return report.id

    except Exception as e:
        logger.error(f"❌ Failed to save report to DB: {e}")
        import traceback

        traceback.print_exc()
        return None
