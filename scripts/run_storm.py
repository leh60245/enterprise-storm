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

from src.common.db_utils import get_available_companies

from knowledge_storm import (
    STORMWikiRunnerArguments,
    STORMWikiRunner,
    STORMWikiLMConfigs,
)
from knowledge_storm.lm import OpenAIModel, AzureOpenAIModel, GoogleModel
from knowledge_storm.rm import PostgresRM
from knowledge_storm.utils import load_api_key

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ============================================================
# 분석 타겟 리스트 (Batch Processing Targets)
# ============================================================
ANALYSIS_TARGETS = [
    "삼성전자 기업 개요 및 주요 사업의 내용"
    # "삼성전자 최근 3개년 요약 재무제표 및 재무 상태 분석"
    # "삼성전자 SWOT 분석 (강점, 약점, 기회, 위협)"
    # "삼성전자 3C 분석 (자사, 경쟁사, 고객)"
    # "삼성전자 채용 공고 및 인재상 분석"
]


def select_company_and_topic() -> tuple[str, str]:
    """
    CLI 인터랙티브 모드: 기업 및 주제 선택

    DB에서 기업 목록을 조회하여 번호 메뉴로 출력하고,
    사용자가 선택한 기업명과 분석 주제를 반환합니다.

    Returns:
        tuple[str, str]: (기업명, 분석 주제)

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

    for idx, name in enumerate(companies):
        print(f"  [{idx + 1}] {name}")

    target_company = ""
    while True:
        try:
            sel = input("\n👉 기업 번호 입력: ").strip()
            idx = int(sel) - 1
            if 0 <= idx < len(companies):
                target_company = companies[idx]
                break
            else:
                print("⚠️ 올바른 번호를 입력해주세요.")
        except ValueError:
            print("⚠️ 숫자를 입력해주세요.")

    # 2. 주제 선택
    topics = [
        "기업 개요 및 주요 사업 내용",
        "최근 3개년 재무제표 및 재무 상태 분석",
        "SWOT 분석 (강점, 약점, 기회, 위협)",
        "3C 분석 (자사, 경쟁사, 고객)",
        "채용 공고 및 인재상 분석",
        "자유 주제 (직접 입력)"
    ]

    print(f"\n📝 [{target_company}] 관련 분석 주제를 선택하세요:")
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

    print(f"\n✅ 분석 시작: {target_company} - {target_topic}")
    return target_company, target_topic


def _extract_company_from_topic(topic: str, default_company: str = None) -> str:
    """
    토픽 문자열에서 기업명을 추출

    COMPANY_ALIASES를 활용하여 토픽에서 언급된 기업명을 찾아
    정규화된 기업명으로 반환합니다.

    Args:
        topic: 분석 토픽 (예: "삼성전자 SWOT 분석")
        default_company: 기본 기업명 (토픽에서 찾지 못한 경우 사용)

    Returns:
        정규화된 기업명 또는 None

    Example:
        >>> _extract_company_from_topic("삼전 재무 분석")
        "삼성전자"
        >>> _extract_company_from_topic("SK Hynix 개요")
        "SK하이닉스"
    """
    try:
        # 로컬 import: 스크립트 실행 환경에서만 필요하며, 실패해도 기본값으로 폴백합니다.
        from src.common.config import extract_companies_from_query  # type: ignore

        companies = extract_companies_from_query(topic)
        if companies:
            return companies[0]
    except Exception as e:
        # ImportError뿐 아니라 설정/alias 로딩 문제 등도 여기서 로깅 후 폴백
        logger.warning(f"Could not extract company from topic (fallback to default): {e}")

    return default_company


def create_topic_dir_name(topic: str) -> str:
    """
    토픽명을 파일시스템 호환 디렉토리명으로 변환

    규칙:
    1. 공백은 언더스코어(_)로 변환
    2. 윈도우 파일 시스템 금지 문자(/:*?"<>|)만 제거/변환
    3. 괄호(), 쉼표, 등은 유지 (STORM이 유지하기 때문)

    Args:
        topic: 원본 토픽명

    Returns:
        언더스코어로 연결된 디렉토리명
    """
    # 1. 공백을 언더스코어로 변환
    dir_name = topic.replace(' ', '_')

    # 2. 파일 시스템 금지 문자만 제거 또는 변환 (/:*?"<>|)
    # STORM은 보통 /만 _로 바꾸고 나머지는 그대로 두거나 제거함
    dir_name = dir_name.replace('/', '_').replace('\\', '_')
    dir_name = re.sub(r'[:*?"<>|]', '', dir_name)
    return dir_name


def _safe_dir_component(name: str, fallback: str = "unknown") -> str:
    """디렉토리 경로 컴포넌트로 안전하게 변환합니다 (Windows 금지문자 제거, 공백->언더스코어)."""
    if not name:
        return fallback
    safe = name.replace(" ", "_")
    safe = safe.replace("/", "_").replace("\\", "_")
    safe = re.sub(r'[:*?"<>|]', "", safe)
    safe = safe.strip(". ")
    return safe or fallback


def build_run_output_dir(base_output_dir: str, company_name: str, topic: str) -> str:
    """실행별 결과 폴더를 `base/company/topic/YYYYMMDD_HHMMSS` 형태로 생성합니다."""
    company_dir = _safe_dir_component(company_name, fallback="unknown_company")
    # topic은 이미 파일시스템 호환 변환 로직이 있으니 재사용
    topic_dir = create_topic_dir_name(topic)
    topic_dir = _safe_dir_component(topic_dir, fallback="unknown_topic")

    # 구분 가능한 타임스탬프 (초 단위)
    timestamp_dir = datetime.now().strftime("%Y%m%d_%H%M%S")

    run_dir = os.path.join(base_output_dir, company_dir, topic_dir, timestamp_dir)

    # 같은 초에 재실행/병렬 실행 시 충돌 방지
    suffix = 1
    candidate = run_dir
    while os.path.exists(candidate):
        suffix += 1
        candidate = f"{run_dir}_{suffix}"

    os.makedirs(candidate, exist_ok=True)
    return candidate


def write_run_args_json(run_output_dir: str, *, topic: str, company_filter: str | None, args, model_name: str):
    """실행 폴더에 스크립트 레벨 설정을 JSON으로 기록합니다."""
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "topic": topic,
        "company_filter": company_filter,
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


def save_report_to_db(topic: str, output_dir: str, secrets_path: str, model_name: str = "gpt-4o") -> bool:
    """
    STORM 실행 결과를 PostgreSQL의 Generated_Reports 테이블에 적재합니다.

    Args:
        topic: 분석 주제
        output_dir: STORM 결과 저장 디렉토리
        secrets_path: secrets.toml 파일 경로
        model_name: 사용된 LLM 모델명

    Returns:
        bool: 성공 여부
    """
    # 토픽별 결과 디렉토리 경로 생성
    topic_dir_name = create_topic_dir_name(topic)
    topic_output_dir = os.path.join(output_dir, topic_dir_name)

    # ========================================
    # Step 1: 필수 파일 읽기
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
    # Step 4: company_name 추출
    # ========================================
    company_name = topic.split()[0] if topic else "Unknown"

    # ========================================
    # Step 5: DB INSERT
    # ========================================
    try:
        # DB 접속 정보 로드
        conn = psycopg2.connect(
            host=os.getenv("PG_HOST"),
            port=os.getenv("PG_PORT", "5432"),
            user=os.getenv("PG_USER"),
            password=os.getenv("PG_PASSWORD"),
            database=os.getenv("PG_DATABASE")
        )

        cursor = conn.cursor()

        insert_query = """
        INSERT INTO "Generated_Reports"
        (company_name, topic, report_content, toc_text, references_data, conversation_log, meta_info, model_name)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """

        cursor.execute(insert_query, (
            company_name,
            topic,
            report_content,
            toc_text,
            Json(references_data) if references_data else None,
            Json(conversation_log) if conversation_log else None,
            Json(meta_info),
            model_name
        ))

        conn.commit()
        cursor.close()
        conn.close()

        logger.info(f"✓ Report saved to DB: {topic}")
        return True

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

        # 각 컴포넌트별 LM 설정
        # - conv_simulator_lm, question_asker_lm: 빠른 모델 (대화 시뮬레이션)
        # - outline_gen_lm, article_gen_lm, article_polish_lm: 강력한 모델 (콘텐츠 생성)
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
        gpt_35_model_name = "gpt-3.5-turbo" if api_type == "openai" else "gpt-35-turbo"
        gpt_4_model_name = "gpt-4o"

        # Azure 설정 (필요시)
        if api_type == "azure":
            openai_kwargs["api_base"] = os.getenv("AZURE_API_BASE")
            openai_kwargs["api_version"] = os.getenv("AZURE_API_VERSION")

        # 각 컴포넌트별 LM 설정
        # - conv_simulator_lm, question_asker_lm: 저렴한 모델 (대화 시뮬레이션)
        # - outline_gen_lm, article_gen_lm, article_polish_lm: 강력한 모델 (콘텐츠 생성)
        conv_simulator_lm = ModelClass(
            model=gpt_35_model_name, max_tokens=500, **openai_kwargs
        )
        question_asker_lm = ModelClass(
            model=gpt_35_model_name, max_tokens=500, **openai_kwargs
        )
        outline_gen_lm = ModelClass(
            model=gpt_4_model_name, max_tokens=400, **openai_kwargs
        )
        article_gen_lm = ModelClass(
            model=gpt_4_model_name, max_tokens=700, **openai_kwargs
        )
        article_polish_lm = ModelClass(
            model=gpt_4_model_name, max_tokens=4000, **openai_kwargs
        )

        logger.info(f"✓ Using OpenAI models: {gpt_35_model_name} (fast), {gpt_4_model_name} (pro)")

    lm_configs.set_conv_simulator_lm(conv_simulator_lm)
    lm_configs.set_question_asker_lm(question_asker_lm)
    lm_configs.set_outline_gen_lm(outline_gen_lm)
    lm_configs.set_article_gen_lm(article_gen_lm)
    lm_configs.set_article_polish_lm(article_polish_lm)

    return lm_configs


def fix_topic_json_encoding(topic: str, output_dir: str):
    """
    방금 생성된 특정 토픽의 결과 폴더 내 JSON 파일들만 인코딩을 보정합니다.
    (전체 디렉토리를 스캔하지 않아 효율적입니다.)

    Args:
        topic: 분석 주제 (폴더명 생성용)
        output_dir: 전체 결과 저장 루트 경로
    """
    # 1. save_report_to_db와 동일한 로직으로 타겟 폴더 경로 생성
    topic_dir_name = create_topic_dir_name(topic)
    target_dir = os.path.join(output_dir, topic_dir_name)

    if not os.path.exists(target_dir):
        logger.warning(f"Target directory not found for encoding fix: {target_dir}")
        return

    logger.info(f"Fixing JSON encoding in specific folder: {target_dir}")

    # 2. 해당 폴더 내의 파일만 순회
    for file in os.listdir(target_dir):
        if file.endswith(".json"):
            file_path = os.path.join(target_dir, file)
            try:
                # 읽기
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # 다시 쓰기 (ensure_ascii=False)
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
            except Exception as e:
                logger.warning(f"Failed to fix encoding for {file}: {e}")


def run_batch_analysis(args):
    """
    배치 분석을 실행합니다.

    Args:
        args: ArgumentParser에서 파싱된 인자
    """
    # secrets.toml 로드
    secrets_path = os.path.join(os.path.dirname(__file__), "..", "secrets.toml")
    if os.path.exists(secrets_path):
        load_api_key(toml_file_path=secrets_path)
        logger.info(f"✓ Loaded secrets from: {secrets_path}")
    else:
        # 현재 디렉토리에서도 찾기
        if os.path.exists("secrets.toml"):
            load_api_key(toml_file_path="secrets.toml")
            logger.info("✓ Loaded secrets from: secrets.toml")
        else:
            logger.error("✗ secrets.toml not found!")
            logger.error("  Please create secrets.toml with required API keys and DB credentials.")
            sys.exit(1)

    # LM 설정 초기화
    logger.info("Initializing LM configurations...")
    lm_configs = setup_lm_configs(args.model_provider)

    # 모델명 결정 (DB 저장용)
    if args.model_provider == "gemini":
        current_model_name = "gemini"
    else:
        current_model_name = "gpt-4o"

    # PostgresRM 초기화 (내부 DB 검색)
    # company_filter는 각 토픽 처리 시 동적으로 설정됨
    logger.info("Initializing PostgresRM (Internal DB Search)...")
    rm = PostgresRM(k=args.search_top_k, min_score=args.min_score)
    logger.info(f"✓ PostgresRM initialized with k={args.search_top_k}, min_score={args.min_score}")

    # 분석 대상 리스트 결정
    if args.topics:
        # 커맨드라인에서 지정된 토픽 사용
        analysis_targets = args.topics
    else:
        # 기본 분석 타겟 사용
        analysis_targets = ANALYSIS_TARGETS

    # company_name이 전달된 경우 (인터랙티브 모드에서 호출)
    # args.company_name이 있으면 그 값을 사용
    default_company_filter = getattr(args, 'company_name', None)

    total_topics = len(analysis_targets)
    successful = 0
    failed = 0

    logger.info("=" * 60)
    logger.info(f"Starting Enterprise STORM Batch Analysis")
    logger.info(f"Model provider: {args.model_provider} ({current_model_name})")
    logger.info(f"Total topics to process: {total_topics}")
    logger.info(f"Output directory: {args.output_dir}")
    if default_company_filter:
        logger.info(f"Default company filter: {default_company_filter}")
    logger.info("=" * 60)

    for idx, topic in enumerate(analysis_targets, 1):
        topic_start_time = datetime.now()
        logger.info("")
        logger.info(f"[{idx}/{total_topics}] Processing: '{topic}'")
        logger.info("-" * 50)

        try:
            # 토픽에서 기업명 추출하여 company_filter 설정
            company_filter = _extract_company_from_topic(topic, default_company_filter)
            rm.set_company_filter(company_filter)
            if company_filter:
                logger.info(f"📌 Company filter set to: {company_filter}")

            # 실행별로 별도 폴더 구성: base/company/topic/timestamp
            run_output_dir = build_run_output_dir(args.output_dir, company_filter or default_company_filter, topic)
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
                topic=topic,
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
                topic=topic,
                company_filter=company_filter,
                args=args,
                model_name=current_model_name,
            )

            # DB 저장 전에 '방금 만든 폴더'만 인코딩 보정 수행
            fix_topic_json_encoding(topic, run_output_dir)

            # DB에 결과 저장 (run_output_dir 기준)
            save_report_to_db(topic, run_output_dir, secrets_path, model_name=current_model_name)

            elapsed = datetime.now() - topic_start_time
            logger.info(f"✓ Completed '{topic}' in {elapsed.total_seconds():.1f}s")
            successful += 1

        except Exception as e:
            elapsed = datetime.now() - topic_start_time
            logger.error(f"✗ Failed '{topic}' after {elapsed.total_seconds():.1f}s")
            logger.error(f"  Error: {e}")
            failed += 1

            if args.stop_on_error:
                logger.error("Stopping due to --stop-on-error flag")
                break

    # PostgresRM 연결 종료
    rm.close()

    # 최종 요약
    logger.info("")
    logger.info("=" * 60)
    logger.info("Batch Analysis Complete!")
    logger.info(f"  Successful: {successful}/{total_topics}")
    logger.info(f"  Failed: {failed}/{total_topics}")
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

    # 토픽 설정 (선택적)
    parser.add_argument(
        "--topics",
        type=str,
        nargs="+",
        default=None,
        help="분석할 토픽 리스트 (미지정시 기본 리스트 사용)",
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

    # 실행 모드 분기
    if args.batch:
        # 배치 모드: 기존 ANALYSIS_TARGETS 리스트 일괄 처리
        # company_name은 토픽에서 자동 추출됨
        args.company_name = None
        run_batch_analysis(args)
    else:
        # 인터랙티브 모드: CLI에서 기업/주제 선택 후 단건 실행
        company_name, topic = select_company_and_topic()
        # 쿼리 조합: "{기업명} {주제}" 형식
        final_topic = f"{company_name} {topic}"
        # args.topics에 단건 할당하여 기존 run_batch_analysis 로직 재사용
        args.topics = [final_topic]
        # 선택된 기업명을 args에 추가 (company_filter 기본값으로 사용)
        args.company_name = company_name
        run_batch_analysis(args)


if __name__ == "__main__":
    main()

