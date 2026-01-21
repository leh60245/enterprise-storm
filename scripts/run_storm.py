#!/usr/bin/env python
"""
Enterprise STORM Pipeline - 기업 분석 리포트 일괄 생성

PostgreSQL 내부 DB를 활용한 기업 분석 리포트 생성 파이프라인입니다.
외부 검색 엔진 대신 PostgresRM을 사용하여 DART 보고서 데이터를 기반으로 분석합니다.

통합 아키텍처:
    - src.common.config: 통합 설정 (DB, AI, Embedding)
    - src.common.embedding: 통합 임베딩 서비스 (차원 검증 포함)
    - knowledge_storm: STORM 엔진 (PostgresRM 사용)

Required Environment Variables:
    - OPENAI_API_KEY: OpenAI API key
    - GOOGLE_API_KEY: Google Gemini API key (--model-provider gemini 사용 시)
    - EMBEDDING_PROVIDER: 'huggingface' 또는 'openai' (DB와 일치 필수!)
    - PG_HOST, PG_PORT, PG_USER, PG_PASSWORD, PG_DATABASE: PostgreSQL 접속 정보

⚠️ 중요: EMBEDDING_PROVIDER는 DB에 저장된 벡터 차원과 일치해야 합니다!
    - HuggingFace: 768차원
    - OpenAI: 1536차원

Output Structure:
    results/
        topic_name/
            conversation_log.json
            raw_search_results.json
            storm_gen_outline.txt
            url_to_info.json
            storm_gen_article.txt
            storm_gen_article_polished.txt

Usage:
    python -m scripts.run_storm --topic "삼성전자 SWOT 분석"
    python -m scripts.run_storm --batch  # 배치 모드 (ANALYSIS_TARGETS 사용)

Author: Enterprise STORM Team
Updated: 2026-01-11 - Unified Architecture with Dimension Validation
"""

import os
import sys
import re
import json
import logging
from datetime import datetime
from argparse import ArgumentParser

import psycopg2
from psycopg2.extras import Json

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.common.config import TOPICS, DB_CONFIG
from src.common.db_utils import get_available_companies

from knowledge_storm import (
    STORMWikiRunnerArguments,
    STORMWikiRunner,
    STORMWikiLMConfigs,
)
from knowledge_storm.lm import OpenAIModel, AzureOpenAIModel, GoogleModel
from knowledge_storm.rm import PostgresRM, SerperRM, HybridRM
from knowledge_storm.utils import load_api_key

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def select_company_and_topic() -> tuple[int, str, str]:
    """
    CLI 인터랙티브 모드: 기업 및 주제 선택

    DB에서 기업 목록을 조회하여 번호 메뉴로 출력하고,
    사용자가 선택한 기업명과 분석 주제를 반환합니다.

    Returns:
        tuple[int, str, str]: (기업ID, 기업명, 분석 주제)

    Raises:
        SystemExit: DB에서 기업 목록 조회 실패 시
    """
    # 1. 기업 선택
    companies = get_available_companies()
    if not companies:
        print("❌ [Error] DB에서 조회된 기업이 없습니다. DB 연결을 확인하세요.")
        sys.exit(1)

    print("\n" + "=" * 50)
    print("        [ Enterprise STORM 분석기 ]")
    print("=" * 50)
    print("\n🏢 분석할 기업을 선택하세요:")

    for company_id, company_name in companies:
        print(f"  [{company_id}] {company_name}")

    target_company = (0, "")
    while True:
        try:
            sel = input("\n👉 기업 번호 입력: ").strip()
            company_id = int(sel)
            if any(cid == company_id for cid, _ in companies):
                target_company = next((cid, name) for cid, name in companies if cid == company_id)
                break
            else:
                print("⚠️ 올바른 번호를 입력해주세요.")
        except ValueError:
            print("⚠️ 숫자를 입력해주세요.")

    # 2. 주제 선택
    topics = list()
    for topic in TOPICS:
        topics.append(topic["label"])
        
    print(f"\n📝 [{target_company[1]}] 관련 분석 주제를 선택하세요:")
    for idx, topic in enumerate(topics):
        print(f"  [{idx + 1}] {topic}")

    target_topic = ""
    while True:
        try:
            sel = input("\n👉 주제 번호 입력: ").strip()
            idx = int(sel) - 1
            if 0 <= idx < len(topics):
                if idx == len(topics) - 1:  # 자유 주제
                    target_topic = input("   ✍️  질문할 내용을 입력하세요: ").strip()
                    if not target_topic:
                        print("⚠️ 주제를 입력해주세요.")
                        continue
                else:
                    target_topic = topics[idx]
                break
            else:
                print("⚠️ 올바른 번호를 입력해주세요.")
        except ValueError:
            print("⚠️ 숫자를 입력해주세요.")

    print(f"\n✅ 분석 시작: {target_company[1]} - {target_topic}")
    return target_company[0], target_company[1], target_topic





def _safe_dir_component(name: str, fallback: str = "unknown") -> str:
    """디렉토리 경로 컴포넌트로 안전하게 변환합니다 (Windows 금지문자 제거, 공백->언더스코어)."""
    if not name:
        return fallback
    safe = name.replace(" ", "_")
    safe = safe.replace("/", "_").replace("\\", "_")
    safe = re.sub(r'[:*?"<>|]', "", safe)
    safe = safe.strip(". ")
    return safe or fallback


def build_run_output_dir(base_output_dir: str, company_id: int, company_name: str = None) -> str:
    """
    실행별 결과 폴더를 `base/YYYYMMDD_HHMMSS_company_id/` 형태로 생성합니다.
    
    Flat structure로 타임스탬프 + company_id로 고유성을 보장합니다.
    이를 통해 경로 길이 제한 문제를 회피하고 디버깅을 용이하게 합니다.
    
    Args:
        base_output_dir: 기본 출력 디렉토리
        company_id: 기업 ID (고유성 보장용)
        company_name: 기업명 (디렉토리 명에 포함할 수 있음, 선택사항)
    
    Returns:
        생성된 결과 폴더 경로
    """
    # 타임스탬프 (초 단위)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # company_name이 있으면 안전하게 변환하여 접미사로 추가
    if company_name:
        company_suffix = _safe_dir_component(company_name, fallback="company")
        dir_name = f"{timestamp}_{company_id}_{company_suffix}"
    else:
        dir_name = f"{timestamp}_{company_id}"
    
    run_dir = os.path.join(base_output_dir, dir_name)
    
    # 같은 초에 재실행/병렬 실행 시 충돌 방지
    suffix = 1
    candidate = run_dir
    while os.path.exists(candidate):
        suffix += 1
        candidate = f"{run_dir}_{suffix}"
    
    os.makedirs(candidate, exist_ok=True)
    return candidate


def write_run_args_json(run_output_dir: str, *, topic: str, company_id: int, company_name: str, args, model_name: str):
    """실행 폴더에 스크립트 레벨 설정을 JSON으로 기록합니다."""
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "topic": topic,
        "company_id": company_id,
        "company_name": company_name,
        "model_provider": getattr(args, "model_provider", None),
        "model_name": model_name,
        "output_dir": run_output_dir,
        "storm_args": {
            "max_conv_turn": getattr(args, "max_conv_turn", None),
            "max_perspective": getattr(args, "max_perspective", None),
            "search_top_k": getattr(args, "search_top_k", None),
            "min_score": getattr(args, "min_score", None),
            "max_thread_num": getattr(args, "max_thread_num", None),
            "do_research": getattr(args, "do_research", None),
            "do_generate_outline": getattr(args, "do_generate_outline", None),
            "do_generate_article": getattr(args, "do_generate_article", None),
            "do_polish_article": getattr(args, "do_polish_article", None),
        },
        "env": {
            "OPENAI_API_TYPE": os.getenv("OPENAI_API_TYPE"),
            "EMBEDDING_PROVIDER": os.getenv("EMBEDDING_PROVIDER"),
            "PG_HOST": os.getenv("PG_HOST"),
            "PG_PORT": os.getenv("PG_PORT"),
            "PG_DATABASE": os.getenv("PG_DATABASE"),
        },
    }

    path = os.path.join(run_output_dir, "run_args.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def save_report_to_db(ai_query: str, output_dir: str, secrets_path: str, model_name: str, company_id: int, company_name: str, analysis_topic: str) -> bool:
    """
    ✅ [REFACTOR] Uses centralized DBManager.insert_generated_report()
    
    STORM 실행 결과를 PostgreSQL의 Generated_Reports 테이블에 적재합니다.
    
    폴더 구조:
        base/YYYYMMDD_HHMMSS_company_id_company_name/
            {ai_query}/  ← STORM runner가 생성하는 폴더
                conversation_log.json
                storm_gen_outline.txt
                storm_gen_article_polished.txt
                url_to_info.json
                raw_search_results.json
                ...

    Args:
        ai_query: LLM에게 입력된 실제 질문/프롬프트 (폴더명으로도 사용됨)
        output_dir: STORM 실행 결과 기본 디렉토리 (= run_output_dir)
        secrets_path: 비밀 정보 파일 경로
        model_name: 사용한 모델명 ('openai' 또는 'gemini')
        company_id: Companies table의 ID (필수, FK)
        company_name: 기업명
        analysis_topic: 분석 주제 (DB에 저장할 topic 필드)

    Returns:
        bool: 저장 성공 여부
    """
    
    # ========================================
    # Step 1: 파일 경로 구성
    # ========================================
    # STORM runner는 {ai_query}를 파일시스템 안전 디렉토리명으로 변환하여 파일 생성
    # 공백 → 언더바(_), 금지문자 제거
    safe_topic_dir = _safe_dir_component(ai_query)
    topic_output_dir = os.path.join(output_dir, safe_topic_dir)
    
    logger.info(f"Reading STORM output from: {topic_output_dir}")
    
    # ========================================
    # Step 2: 필수 파일 읽기
    # ========================================
    # storm_gen_article_polished.txt (필수)
    polished_article_path = os.path.join(topic_output_dir, "storm_gen_article_polished.txt")
    if not os.path.exists(polished_article_path):
        logger.error(f"Required file not found: {polished_article_path}")
        return False

    with open(polished_article_path, "r", encoding="utf-8") as f:
        report_content = f.read()

    # url_to_info.json (필수)
    url_to_info_path = os.path.join(topic_output_dir, "url_to_info.json")
    if not os.path.exists(url_to_info_path):
        logger.error(f"Required file not found: {url_to_info_path}")
        return False

    with open(url_to_info_path, "r", encoding="utf-8") as f:
        references_data = json.load(f)

    # ========================================
    # Step 2: 선택 파일 읽기
    # ========================================
    # storm_gen_outline.txt (선택)
    toc_text = None
    outline_path = os.path.join(topic_output_dir, "storm_gen_outline.txt")
    if os.path.exists(outline_path):
        with open(outline_path, "r", encoding="utf-8") as f:
            toc_text = f.read()

    # conversation_log.json (선택)
    conversation_log = None
    conv_log_path = os.path.join(topic_output_dir, "conversation_log.json")
    if os.path.exists(conv_log_path):
        with open(conv_log_path, "r", encoding="utf-8") as f:
            conversation_log = json.load(f)

    # run_config.json (선택)
    run_config_data = None
    config_path = os.path.join(topic_output_dir, "run_config.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            run_config_data = json.load(f)

    # raw_search_results.json (선택)
    raw_search_results_data = None
    search_results_path = os.path.join(topic_output_dir, "raw_search_results.json")
    if os.path.exists(search_results_path):
        with open(search_results_path, "r", encoding="utf-8") as f:
            raw_search_results_data = json.load(f)

    # ========================================
    # Step 3: meta_info 생성
    # ========================================
    meta_info = {
        "config": run_config_data,
        "search_results": raw_search_results_data
    }

    # ========================================
    # Step 4: DB에 저장 (✅ REFACTOR: Use DBManager)
    # ========================================
    try:
        from src.ingestion.db_manager import DBManager
        
        with DBManager() as db:
            report_id = db.insert_generated_report(
                company_name=company_name,
                topic=analysis_topic,
                report_content=report_content,
                toc_text=toc_text,
                references_data=references_data or {},
                conversation_log=conversation_log or {},
                meta_info=meta_info or {},
                model_name=model_name,
                company_id=company_id
            )
        
        if report_id:
            logger.info(f"✓ Report saved to DB: {analysis_topic} (report_id={report_id}, company_id={company_id}, company_name={company_name})")
            return True
        else:
            logger.error(f"✗ Failed to save report to DB (no ID returned)")
            return False

    except Exception as e:
        logger.error(f"✗ Failed to save report to DB: {e}")
        return False


def setup_lm_configs(provider: str = "openai") -> STORMWikiLMConfigs:
    """
    LLM 설정을 초기화합니다.

    Args:
        provider: LLM 공급자 ('openai' 또는 'gemini')

    Returns:
        STORMWikiLMConfigs: 설정된 LM 구성 객체
    """
    lm_configs = STORMWikiLMConfigs()

    if provider == "gemini":
        # Google Gemini 모델 설정
        gemini_kwargs = {
            "temperature": 1.0,
            "top_p": 0.9,
        }

        # Gemini 모델명 설정 (2026년 최신 형식: models/ 접두사 없이 사용)
        gemini_flash_model = "gemini-2.0-flash"
        gemini_pro_model = "gemini-2.0-flash"

        
        conv_simulator_lm = GoogleModel(
            model=gemini_flash_model, max_tokens=2048, **gemini_kwargs  # 토큰 수 약간 상향
        )
        question_asker_lm = GoogleModel(
            model=gemini_flash_model, max_tokens=2048, **gemini_kwargs
        )
        outline_gen_lm = GoogleModel(
            model=gemini_pro_model, max_tokens=4096, **gemini_kwargs
        )
        article_gen_lm = GoogleModel(
            model=gemini_pro_model, max_tokens=8192, **gemini_kwargs
        )
        article_polish_lm = GoogleModel(
            model=gemini_pro_model, max_tokens=8192, **gemini_kwargs
        )

        logger.info(f"✓ Using Gemini models: {gemini_flash_model} (fast), {gemini_pro_model} (pro)")

    else:
        # OpenAI 모델 설정 (기본값)
        openai_kwargs = {
            "api_key": os.getenv("OPENAI_API_KEY"),
            "temperature": 1.0,
            "top_p": 0.9,
        }

        # API 타입에 따른 모델 클래스 선택
        api_type = os.getenv("OPENAI_API_TYPE", "openai")
        ModelClass = OpenAIModel if api_type == "openai" else AzureOpenAIModel

        # 모델명 설정
        gpt_large_model = "gpt-4o-mini" 
        gpt_fast_model = "gpt-4o"

        # Azure 설정 (필요시)
        if api_type == "azure":
            openai_kwargs["api_base"] = os.getenv("AZURE_API_BASE")
            openai_kwargs["api_version"] = os.getenv("AZURE_API_VERSION")

        conv_simulator_lm = ModelClass(
            model=gpt_large_model, max_tokens=500, **openai_kwargs
        )
        question_asker_lm = ModelClass(
            model=gpt_large_model, max_tokens=500, **openai_kwargs
        )
        outline_gen_lm = ModelClass(
            model=gpt_fast_model, max_tokens=400, **openai_kwargs
        )
        article_gen_lm = ModelClass(
            model=gpt_fast_model, max_tokens=700, **openai_kwargs
        )
        article_polish_lm = ModelClass(
            model=gpt_fast_model, max_tokens=4000, **openai_kwargs
        )

        logger.info(f"✓ Using OpenAI models: {gpt_large_model} (fast), {gpt_fast_model} (pro)")

    # 각 컴포넌트별 LM 설정
    # - conv_simulator_lm, question_asker_lm: 빠른 모델 (대화 시뮬레이션)
    # - outline_gen_lm, article_gen_lm, article_polish_lm: 강력한 모델 (콘텐츠 생성)
    lm_configs.set_conv_simulator_lm(conv_simulator_lm)
    lm_configs.set_question_asker_lm(question_asker_lm)
    lm_configs.set_outline_gen_lm(outline_gen_lm)
    lm_configs.set_article_gen_lm(article_gen_lm)
    lm_configs.set_article_polish_lm(article_polish_lm)

    return lm_configs


def fix_topic_json_encoding(ai_query: str, output_dir: str):
    """
    생성된 결과 폴더 내 JSON 파일들의 인코딩을 보정합니다.
    STORM이 생성한 ai_query 기반 하위 폴더 내의 JSON 파일들을 처리합니다.

    Args:
        ai_query: LLM에게 입력된 질문 (STORM이 폴더명으로 사용)
        output_dir: STORM 실행 결과 기본 디렉토리 (= run_output_dir)
    """
    # STORM이 생성한 실제 폴더 경로 구성 (공백→언더바 변환)
    safe_topic_dir = _safe_dir_component(ai_query)
    topic_output_dir = os.path.join(output_dir, safe_topic_dir)
    
    if not os.path.exists(topic_output_dir):
        logger.warning(f"Output directory not found for encoding fix: {topic_output_dir}")
        return

    logger.info(f"Fixing JSON encoding in: {topic_output_dir}")

    # topic_output_dir 내의 JSON 파일만 순회하여 인코딩 보정
    try:
        for file in os.listdir(topic_output_dir):
            if file.endswith(".json"):
                file_path = os.path.join(topic_output_dir, file)
                try:
                    # 읽기
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    # 다시 쓰기 (ensure_ascii=False)
                    with open(file_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=4, ensure_ascii=False)
                    logger.info(f"  ✓ Fixed: {file}")
                except Exception as e:
                    logger.warning(f"  ⚠️ Failed to fix encoding for {file}: {e}")
    except Exception as e:
        logger.error(f"Error accessing output directory: {e}")


def run_batch_analysis(args):
    """
    배치 분석을 실행합니다.

    Args:
        args: ArgumentParser에서 파싱된 인자
    """
    
    # .env 파일로 환경변수 로드
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_path):
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=env_path)
        logger.info(f"✓ Loaded environment variables from: {env_path}")
        

    # LM 설정 초기화
    logger.info("Initializing LM configurations...")
    lm_configs = setup_lm_configs(args.model_provider)

    # 모델명 결정 (DB 저장용)
    if args.model_provider == "gemini":
        current_model_name = "gemini"
    else:
        current_model_name = "openai"

    # HybridRM 초기화 (내부 DB + 외부 검색 혼합)
    logger.info("Initializing HybridRM (Internal DB + External Search)...")
    
    # 내부 검색: PostgresRM (DART 보고서)
    internal_rm = PostgresRM(k=args.search_top_k, min_score=args.min_score)
    logger.info(f"✓ Internal RM (PostgresRM) initialized with k={args.search_top_k}")
    
    # 외부 검색: SerperRM (Google Search)
    serper_api_key = os.getenv("SERPER_API_KEY")
    if not serper_api_key:
        logger.warning("⚠️ SERPER_API_KEY not found. External search will be disabled.")
        logger.warning("   Set SERPER_API_KEY to enable hybrid search.")
        return  # 외부 검색 키 없으면 배치 중단
    else:
        external_rm = SerperRM(serper_search_api_key=serper_api_key, k=args.search_top_k)
        logger.info(f"✓ External RM (SerperRM) initialized with k={args.search_top_k}")
        
        # HybridRM 조합 (3:7 비율)
        rm = HybridRM(internal_rm, external_rm, internal_k=3, external_k=7)
        logger.info("✓ HybridRM initialized with internal_k=3, external_k=7 (3:7 ratio)")

    # 커맨드라인에서 지정된 정보 사용
    company_id = args.company_id
    company_name = args.company_name
    analysis_topic = args.analysis_topic  # UI에서 선택된 분석 주제 카테고리
    ai_query = f"{company_name} {analysis_topic}"  # LLM에게 입력되는 실제 질문
 

    logger.info("=" * 60)
    logger.info(f"Starting Enterprise STORM Batch Analysis")
    logger.info(f"Model provider: {args.model_provider} ({current_model_name})")
    logger.info(f"Total report titles to process: 1")
    logger.info(f"Output directory: {args.output_dir}")
    logger.info(f"Company: {company_name} (ID: {company_id})")
    logger.info("=" * 60)
    
    successful = True

    topic_start_time = datetime.now()
    logger.info("-" * 50)

    try:
        # 기업 정보 검증
        if not company_id or not company_name:
            logger.error("❌ company_id and company_name are required")
            raise ValueError("Company ID and name are required")

        # 실행별로 별도 폴더 구성: base/YYYYMMDD_HHMMSS_company_id_company_name/
        run_output_dir = build_run_output_dir(args.output_dir, company_id, company_name)
        logger.info(f"📁 Run output directory: {run_output_dir}")

        # Engine Arguments 설정 (output_dir을 run_output_dir로 지정)
        engine_args = STORMWikiRunnerArguments(
            output_dir=run_output_dir,
            max_conv_turn=args.max_conv_turn,
            max_perspective=args.max_perspective,
            search_top_k=args.search_top_k,
            max_thread_num=args.max_thread_num,
        )

        # Runner 생성
        runner = STORMWikiRunner(engine_args, lm_configs, rm)

        # STORM 파이프라인 실행
        runner.run(
            topic=ai_query,
            do_research=args.do_research,
            do_generate_outline=args.do_generate_outline,
            do_generate_article=args.do_generate_article,
            do_polish_article=args.do_polish_article,
        )
        runner.post_run()
        runner.summary()

        # 스크립트 레벨 실행 설정 저장
        write_run_args_json(
            run_output_dir,
            topic=analysis_topic,
            company_id=company_id,
            company_name=company_name,
            args=args,
            model_name=current_model_name,
        )

        # DB 저장 전에 '방금 만든 폴더'만 인코딩 보정 수행
        fix_topic_json_encoding(ai_query, run_output_dir)

        # DB에 결과 저장
        save_report_to_db(ai_query, run_output_dir, "secrets_path", model_name=current_model_name, company_id=company_id, company_name=company_name, analysis_topic=analysis_topic)
        elapsed = datetime.now() - topic_start_time
        logger.info(f"✓ Completed '{ai_query}' in {elapsed.total_seconds():.1f}s")

    except Exception as e:
        elapsed = datetime.now() - topic_start_time
        logger.error(f"✗ Failed '{ai_query}' after {elapsed.total_seconds():.1f}s")
        logger.error(f"  Error: {e}")
        
        # 디버깅을 위한 상세 스택 트레이스 출력
        import traceback
        logger.error("  Full traceback:")
        logger.error(traceback.format_exc())
        
        successful = False

        if args.stop_on_error:
            logger.error("Stopping due to --stop-on-error flag")
            raise

    finally:
        # PostgresRM 연결 종료
        rm.close()

    # 최종 요약
    logger.info("")
    logger.info("=" * 60)
    logger.info("Batch Analysis Complete!")
    if successful:
        logger.info(f"  Successful!")
    else:
        logger.info(f"  Failed...")
    logger.info(f"  Output directory: {args.output_dir}")
    logger.info("=" * 60)


def main():
    parser = ArgumentParser(
        description="Enterprise STORM - 기업 분석 리포트 생성 도구"
    )

    # 실행 모드
    parser.add_argument(
        "--batch",
        action="store_true",
        help="배치 모드로 실행 (ANALYSIS_TARGETS 리스트 일괄 처리). 미지정 시 인터랙티브 모드.",
    )

    # 출력 설정
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./results/enterprise",
        help="결과물 저장 디렉토리 (기본값: ./results/enterprise)",
    )

    # 모델 공급자 선택
    parser.add_argument(
        "--model-provider",
        type=str,
        choices=["openai", "gemini"],
        default="openai",
        help="사용할 LLM 공급자 선택 (openai 또는 gemini, 기본값: openai)",
    )

    # PostgresRM 설정
    parser.add_argument(
        "--search-top-k",
        type=int,
        default=10,
        help="검색 결과 상위 k개 (기본값: 10)",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.5,
        help="최소 유사도 점수 임계값 (기본값: 0.5)",
    )

    # STORM 엔진 설정
    parser.add_argument(
        "--max-conv-turn",
        type=int,
        default=3,
        help="최대 대화 턴 수 (기본값: 3)",
    )
    parser.add_argument(
        "--max-perspective",
        type=int,
        default=3,
        help="최대 관점 수 (기본값: 3)",
    )
    parser.add_argument(
        "--max-thread-num",
        type=int,
        default=3,
        help="최대 스레드 수 (기본값: 3)",
    )

    # 파이프라인 단계 설정
    parser.add_argument(
        "--do-research",
        action="store_true",
        default=True,
        help="리서치 단계 실행 (기본값: True)",
    )
    parser.add_argument(
        "--do-generate-outline",
        action="store_true",
        default=True,
        help="아웃라인 생성 단계 실행 (기본값: True)",
    )
    parser.add_argument(
        "--do-generate-article",
        action="store_true",
        default=True,
        help="아티클 생성 단계 실행 (기본값: True)",
    )
    parser.add_argument(
        "--do-polish-article",
        action="store_true",
        default=True,
        help="아티클 다듬기 단계 실행 (기본값: True)",
    )

    # 에러 처리
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="에러 발생 시 배치 처리 중단",
    )

    args = parser.parse_args()

    # action="store_true"와 default=True가 함께 사용되면 항상 True가 되므로
    # 기본값이 True인 플래그들은 명시적으로 설정
    if not any([args.do_research, args.do_generate_outline,
                args.do_generate_article, args.do_polish_article]):
        args.do_research = True
        args.do_generate_outline = True
        args.do_generate_article = True
        args.do_polish_article = True

    # CLI에서 기업/주제 선택 후 단건 실행
    args.company_id, args.company_name, args.analysis_topic = select_company_and_topic()
        
    # 배치 분석 실행
    run_batch_analysis(args)


if __name__ == "__main__":
    main()

