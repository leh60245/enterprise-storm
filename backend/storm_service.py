"""
STORM Engine Wrapper Service for Backend API Integration

Task ID: FEAT-Core-001-EngineIntegration
Task ID: FIX-Core-002-SaveLogic & Encoding (Post-Processing Bridge)
Purpose: FastAPI와 knowledge_storm 라이브러리를 연결하는 Wrapper Service

Architecture:
    - scripts/run_storm.py의 메인 로직을 함수 형태로 변환
    - argparse 의존성 제거 → 함수 파라미터로 입력 받음
    - BackgroundTasks와 연동하여 비동기 실행 가능
    - ✅ Post-Processing Bridge: 파일 읽기 → DB 저장

Key Fix:
    - STORMWikiRunner.run()은 파일만 생성 (DB 저장 안 함)
    - 수정: runner.run() 후 파일을 읽어 DB에 INSERT (RETURNING id)
    - 한글 인코딩: 모든 파일 읽기에 encoding='utf-8' 명시

Usage:
    from backend.storm_service import run_storm_pipeline
    
    background_tasks.add_task(
        run_storm_pipeline,
        job_id="job-123",
        company_name="삼성전자",
        topic="기업 개요",
        jobs_dict=JOBS
    )

Author: Backend Development Team
Created: 2026-01-17
Updated: 2026-01-17 (Post-Processing Bridge Implementation)
"""

import os
import sys
import json
import glob
import time
from datetime import datetime
from pathlib import Path

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from knowledge_storm import (
    STORMWikiRunnerArguments,
    STORMWikiRunner,
    STORMWikiLMConfigs,
)
from knowledge_storm.lm import OpenAIModel, GoogleModel
from knowledge_storm.rm import PostgresRM
from knowledge_storm.utils import load_api_key

from src.common.config import extract_companies_from_query
from src.common.constants import (
    STORM_MAX_THREAD_LIMIT,
    STORM_DEFAULT_THREAD_COUNT,
    STORM_MAX_CONV_TURN,
    STORM_MAX_PERSPECTIVE,
    FILE_OPERATION_MAX_RETRIES,
    FILE_CHECK_WAIT_SECONDS,
    STORM_RUN_MAX_RETRIES,
    RATE_LIMIT_BASE_WAIT_SECONDS,
    PROGRESS_AFTER_RM_INIT,
    PROGRESS_STORM_RUNNING,
    PROGRESS_STORM_COMPLETED,
)
from src.common.logger import get_logger
from backend.database import get_db_cursor, get_db_connection
from psycopg2.extras import RealDictCursor, Json
import psycopg2
import psycopg2.extras

# ✅ [REFACTOR] Use centralized logger
logger = get_logger(__name__)


def _is_rate_limit_error(exc: Exception) -> bool:
    """
    Rate Limit 에러 또는 API 빈 응답으로 인한 IndexError를 감지합니다.
    
    dspy 라이브러리가 빈 completions 리스트를 받으면 IndexError가 발생하는데,
    이는 보통 Rate Limit(429)로 인한 빈 응답 때문입니다.
    """
    msg = str(exc).lower()
    return (
        "rate limit" in msg
        or "429" in msg
        or "please try again" in msg
        or "list index out of range" in msg  # dspy가 빈 응답을 받을 때
        or isinstance(exc, IndexError)       # IndexError 타입 직접 감지
    )


# ============================================================
# Post-Processing Bridge Functions (FIX-Core-002)
# ============================================================
# 라이브러리(run())는 '작가'일 뿐, 원고를 서고(DB)에 꽂는 것은 '사서(Developer)'가 직접 해야 합니다.

def _find_report_file(output_dir: str, max_retries: int = 10) -> str | None:
    """
    임시 폴더에서 생성된 리포트 파일을 **결정론적(Deterministic)**으로 찾습니다.
    
    전략: "격리 후 전수 조사 (Isolate & Capture)"
    1. 파일명을 추측하지 않음
    2. Glob으로 .txt 패턴 전수 조사
    3. Retry 로직으로 파일 시스템 지연 대응
    
    Args:
        output_dir: runner가 작업한 임시 폴더 (예: ./results/temp/job-xyz)
        max_retries: 최대 재시도 횟수 (기본값: 10초)
    
    Returns:
        파일 경로 (문자열) 또는 None
    
    Example:
        file_path = _find_report_file("./results/temp/job-abc123")
        # → "./results/temp/job-abc123/storm_gen_article_polished.txt"
    """
    if not os.path.exists(output_dir):
        logger.error(f"Output directory not found: {output_dir}")
        return None
    
    logger.info(f"Searching for report file in: {output_dir}")
    
    # ============================================================
    # Retry 로직: 파일 시스템 쓰기 지연 대응 (최대 10초)
    # ============================================================
    target_file = None
    
    for attempt in range(max_retries):
        # 1. Glob으로 모든 .txt 파일 탐색 (recursive)
        all_txt_files = glob.glob(os.path.join(output_dir, "**/*.txt"), recursive=True)
        
        if not all_txt_files:
            logger.debug(f"  [{attempt+1}/{max_retries}] No .txt files found yet, waiting...")
            time.sleep(FILE_CHECK_WAIT_SECONDS)
            continue
        
        # 2. 우선순위: "article" 또는 "polished" 키워드 포함
        priority_keywords = ["polished", "article"]
        candidates = []
        
        for keyword in priority_keywords:
            matches = [f for f in all_txt_files if keyword in os.path.basename(f).lower()]
            if matches:
                candidates.extend(matches)
        
        # 3. 후보가 없으면 가장 큰 파일 선택 (보통 최종 리포트가 가장 큼)
        if not candidates:
            candidates = sorted(all_txt_files, key=lambda f: os.path.getsize(f), reverse=True)
        
        # 4. 첫 번째 후보 선택
        if candidates:
            target_file = candidates[0]
            logger.info(f"✓ Found report file: {os.path.basename(target_file)} (attempt {attempt+1})")
            break
        
        time.sleep(FILE_CHECK_WAIT_SECONDS)
    
    # ============================================================
    # 디버깅: 파일을 찾지 못한 경우 폴더 내용 출력
    # ============================================================
    if not target_file:
        try:
            all_files = os.listdir(output_dir)
            logger.error(f"❌ Report file not found after {max_retries} retries")
            logger.error(f"   Directory: {output_dir}")
            logger.error(f"   Existing files: {all_files}")
        except Exception as e:
            logger.error(f"❌ Failed to list directory: {e}")
        return None
    
    return target_file


def _read_report_content(file_path: str) -> str | None:
    """
    마크다운 리포트 파일을 UTF-8로 읽어 메모리에 로드합니다.
    
    ⚠️ 중요: encoding='utf-8' 명시적 선언으로 한글 인코딩 깨짐 방지
    
    Args:
        file_path: 리포트 파일 경로
    
    Returns:
        파일 내용 (문자열) 또는 None (읽기 실패 시)
    
    Example:
        content = _read_report_content("./results/temp/job-abc123/storm_gen_article_polished.txt")
        # → "# 삼성전자 기업 개요\n\n## 1. 개요\n..."
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        logger.info(f"✓ Read report file ({len(content)} bytes)")
        return content
    except UnicodeDecodeError as e:
        logger.error(f"❌ UTF-8 Encoding error: {e}")
        logger.warning("Retrying with fallback encoding (cp949)...")
        try:
            with open(file_path, "r", encoding="cp949") as f:
                content = f.read()
            logger.warning(f"⚠️  Fallback encoding used (cp949)")
            return content
        except Exception as e2:
            logger.error(f"❌ Fallback encoding also failed: {e2}")
            return None
    except Exception as e:
        logger.error(f"❌ Failed to read report file: {e}")
        return None


def _save_report_to_db(
    company_name: str,
    topic: str,
    report_content: str,
    toc_text: str | None = None,
    references_data: dict | None = None,
    conversation_log: dict | None = None,
    meta_info: dict | None = None,
    model_name: str = "gpt-4o"
) -> int | None:
    """
    리포트를 DB의 Generated_Reports 테이블에 **모든 컬럼**을 포함하여 저장합니다.
    
    ✅ RETURNING id 구문으로 즉시 primary key 획득
    ✅ company_id 자동 조회 (Companies 테이블에서)
    ✅ JSONB 컬럼 저장 (references_data, conversation_log, meta_info)
    
    Args:
        company_name: 기업명 (예: "삼성전자")
        topic: 순수 주제 (기업명 제거됨, 예: "기업 개요")
        report_content: 마크다운 리포트 내용
        toc_text: 목차(Table of Contents) 텍스트 (선택)
        references_data: 참조 정보 딕셔너리 (url_to_info.json)
        conversation_log: 대화 로그 딕셔너리
        meta_info: 메타 정보 딕셔너리 (실행 설정 등)
        model_name: 사용된 LLM 모델명 (기본값: gpt-4o)
    
    Returns:
        생성된 report_id (정수) 또는 None (저장 실패 시)
    
    Example:
        report_id = _save_report_to_db(
            company_name="삼성전자",
            topic="기업 개요",
            report_content="# 삼성전자 기업 개요\n...",
            toc_text="1. 개요\n2. 사업내용",
            references_data={...},
            model_name="gpt-4o"
        )
        # → 42 (생성된 ID)
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # ============================================================
        # Step 1: company_id 조회 (Companies 테이블에서)
        # ============================================================
        company_id = None
        try:
            cur.execute(
                'SELECT id FROM "Companies" WHERE company_name = %s',
                (company_name,)
            )
            result = cur.fetchone()
            if result:
                company_id = result['id']
                logger.info(f"✓ Found company_id: {company_id} for '{company_name}'")
            else:
                logger.warning(f"⚠️  Company '{company_name}' not found in Companies table")
        except Exception as e:
            logger.warning(f"⚠️  Failed to query company_id: {e}")
        
        # ============================================================
        # Step 2: INSERT with all columns + RETURNING id
        # ============================================================
        sql = """
            INSERT INTO "Generated_Reports" 
            (company_name, company_id, topic, report_content, toc_text, 
             references_data, conversation_log, meta_info, model_name, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            RETURNING id
        """
        
        cur.execute(sql, (
            company_name,
            company_id,
            topic,
            report_content,
            toc_text,
            Json(references_data) if references_data else None,
            Json(conversation_log) if conversation_log else None,
            Json(meta_info) if meta_info else None,
            model_name
        ))
        
        result = cur.fetchone()
        report_id = result['id'] if result else None
        
        conn.commit()
        cur.close()
        conn.close()
        
        logger.info(f"✓ Saved to DB - Report ID: {report_id}")
        logger.info(f"  - company_id: {company_id}")
        logger.info(f"  - toc_text: {'Yes' if toc_text else 'No'}")
        logger.info(f"  - references_data: {'Yes' if references_data else 'No'}")
        logger.info(f"  - conversation_log: {'Yes' if conversation_log else 'No'}")
        logger.info(f"  - meta_info: {'Yes' if meta_info else 'No'}")
        
        return report_id
        
    except psycopg2.Error as e:
        logger.error(f"❌ DB Error: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        return None


def _load_and_save_report_bridge(
    output_dir: str,
    company_name: str,
    topic: str,
    jobs_dict: dict,
    job_id: str,
    model_name: str = "gpt-4o"
) -> int | None:
    """
    Post-Processing Bridge: 파일 시스템 → DB
    
    이 함수는 다음을 순차적으로 수행합니다:
    1. 파일 탐색 (File Discovery)
    2. 파일 읽기 (Read to Memory) - UTF-8 명시
    3. DB INSERT (Save to DB) - RETURNING id
    4. 상태 동기화 (Update Status) - jobs_dict 업데이트
    
    Args:
        output_dir: runner가 작업한 임시 폴더 경로
        company_name: 기업명
        topic: 순수 주제
        jobs_dict: 메모리 작업 상태 딕셔너리
        job_id: 작업 ID
        model_name: LLM 모델명
    
    Returns:
        저장된 report_id (정수) 또는 None
    """
    logger.info(f"[{job_id}] Starting Post-Processing Bridge...")
    
    # ============================================================
    # Step 1: File Discovery - 리포트 파일 찾기
    # ============================================================
    report_file = _find_report_file(output_dir)
    if not report_file:
        logger.error(f"❌ Report file not found in {output_dir}")
        jobs_dict[job_id]["message"] = "리포트 파일을 찾을 수 없습니다."
        return None
    
    # ============================================================
    # Step 2: Read to Memory - UTF-8로 파일 읽기
    # ============================================================
    report_content = _read_report_content(report_file)
    if not report_content:
        logger.error(f"❌ Failed to read report content")
        jobs_dict[job_id]["message"] = "리포트 내용을 읽을 수 없습니다."
        return None
    
    # ============================================================
    # Step 2.5: Read Additional Files (TOC, References, Logs)
    # ============================================================
    # TOC (Table of Contents)
    toc_text = None
    toc_file = os.path.join(output_dir, "storm_gen_outline.txt")
    logger.info(f"Looking for TOC file: {toc_file}")
    if os.path.exists(toc_file):
        try:
            with open(toc_file, "r", encoding="utf-8") as f:
                toc_text = f.read()
            logger.info(f"✓ Read TOC file ({len(toc_text)} bytes)")
        except Exception as e:
            logger.warning(f"⚠️  Failed to read TOC: {e}")
    else:
        logger.warning(f"⚠️  TOC file not found: {toc_file}")
    
    # References Data (url_to_info.json)
    references_data = None
    ref_file = os.path.join(output_dir, "url_to_info.json")
    logger.info(f"Looking for references file: {ref_file}")
    if os.path.exists(ref_file):
        try:
            with open(ref_file, "r", encoding="utf-8") as f:
                references_data = json.load(f)
            logger.info(f"✓ Read references data ({len(references_data)} items)")
        except Exception as e:
            logger.warning(f"⚠️  Failed to read references: {e}")
    else:
        logger.warning(f"⚠️  References file not found: {ref_file}")
    
    # Conversation Log (conversation_log.json)
    conversation_log = None
    conv_file = os.path.join(output_dir, "conversation_log.json")
    logger.info(f"Looking for conversation log: {conv_file}")
    if os.path.exists(conv_file):
        try:
            with open(conv_file, "r", encoding="utf-8") as f:
                conversation_log = json.load(f)
            logger.info(f"✓ Read conversation log")
        except Exception as e:
            logger.warning(f"⚠️  Failed to read conversation log: {e}")
    else:
        logger.warning(f"⚠️  Conversation log not found: {conv_file}")
    
    # 디버깅: 폴더 내 모든 파일 출력
    try:
        all_files = os.listdir(output_dir)
        logger.info(f"📁 Files in output_dir: {all_files}")
    except Exception as e:
        logger.warning(f"Failed to list directory: {e}")
    
    # Meta Info (run configuration)
    meta_info = {
        "output_dir": output_dir,
        "job_id": job_id,
        "timestamp": datetime.now().isoformat(),
        "model_name": model_name
    }
    
    # ============================================================
    # Step 3: Save to DB - INSERT with ALL columns + RETURNING id
    # ============================================================
    report_id = _save_report_to_db(
        company_name=company_name,
        topic=topic,
        report_content=report_content,
        toc_text=toc_text,
        references_data=references_data,
        conversation_log=conversation_log,
        meta_info=meta_info,
        model_name=model_name
    )
    
    if report_id is None:
        logger.error(f"❌ Failed to save report to DB")
        jobs_dict[job_id]["message"] = "DB 저장 중 오류가 발생했습니다."
        return None
    
    # ============================================================
    # Step 4: Update Status - 메모리 상태 동기화
    # ============================================================
    jobs_dict[job_id]["report_id"] = report_id
    jobs_dict[job_id]["message"] = f"리포트 생성이 완료되었습니다. (Report ID: {report_id})"
    
    logger.info(f"✅ Bridge completed: report_id={report_id}")
    return report_id


def _setup_lm_configs(model_provider: str = "openai") -> STORMWikiLMConfigs:
    """
    LLM Configuration 설정
    
    Args:
        model_provider: "openai" 또는 "gemini"
    
    Returns:
        STORMWikiLMConfigs: 설정된 LM Config 객체
    """
    lm_configs = STORMWikiLMConfigs()

    if model_provider == "gemini":
        # Gemini 모델 설정
        gemini_kwargs = {
            "api_key": os.getenv("GOOGLE_API_KEY"),
            "temperature": 1.0,
            "top_p": 0.9,
        }

        gemini_flash_model = "gemini-2.0-flash-exp"
        gemini_pro_model = "gemini-2.0-flash"

        conv_simulator_lm = GoogleModel(
            model=gemini_flash_model, max_tokens=2048, **gemini_kwargs
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

        gpt_35_model_name = "gpt-4o-mini"
        gpt_4_model_name = "gpt-4o"

        conv_simulator_lm = OpenAIModel(
            model=gpt_35_model_name, max_tokens=500, **openai_kwargs
        )
        question_asker_lm = OpenAIModel(
            model=gpt_35_model_name, max_tokens=500, **openai_kwargs
        )
        outline_gen_lm = OpenAIModel(
            model=gpt_4_model_name, max_tokens=400, **openai_kwargs
        )
        article_gen_lm = OpenAIModel(
            model=gpt_35_model_name, max_tokens=3000, **openai_kwargs  # 700 → 3000, 여기서 30k tpm 한도를 100% 초과한다고 함. mini는 한도가 넉넉하다고 한다. (한글 생성 충분)
        )
        article_polish_lm = OpenAIModel(
            model=gpt_4_model_name, max_tokens=4000, **openai_kwargs  # 누락되었던 큰 값 추가
        )

        logger.info(f"✓ Using OpenAI models: {gpt_35_model_name} (fast), {gpt_4_model_name} (pro)")

    lm_configs.set_conv_simulator_lm(conv_simulator_lm)
    lm_configs.set_question_asker_lm(question_asker_lm)
    lm_configs.set_outline_gen_lm(outline_gen_lm)
    lm_configs.set_article_gen_lm(article_gen_lm)
    lm_configs.set_article_polish_lm(article_polish_lm)

    return lm_configs


def run_storm_pipeline(
    job_id: str,
    company_name: str,
    topic: str,
    jobs_dict: dict,
    model_provider: str = "openai"
):
    """
    STORM 엔진 실행 메인 함수 (Background Task용)
    
    Args:
        job_id: 작업 추적용 고유 ID (예: "job-123")
        company_name: 기업명 (예: "삼성전자")
        topic: 순수 주제 (기업명 제거된 상태, 예: "기업 개요")
        jobs_dict: 작업 상태 저장용 In-memory Dictionary
        model_provider: LLM 프로바이더 ("openai" 또는 "gemini")
    
    Flow:
        1. Status Update → processing
        2. STORM 엔진 설정 및 실행
        3. DB에 결과 저장 (STORMWikiRunner가 자동 저장)
        4. 최신 report_id 조회
        5. Status Update → completed
    
    Exception Handling:
        - 실행 중 예외 발생 시 status를 "failed"로 변경하고 에러 메시지 저장
    """
    try:
        logger.info(f"[{job_id}] Starting STORM Pipeline")
        logger.info(f"  Company: {company_name}")
        logger.info(f"  Topic: {topic}")
        logger.info(f"  Model Provider: {model_provider}")

        # ============================================================
        # Step 1: Update Status → Processing
        # ============================================================
        jobs_dict[job_id]["status"] = "processing"
        jobs_dict[job_id]["progress"] = 10
        
        # ============================================================
        # Step 2: Load API Keys (환경변수에서 자동 로드)
        # ============================================================
        # secrets.toml이 있으면 로드 (선택사항)
        secrets_path = os.path.join(os.path.dirname(__file__), "..", "secrets.toml")
        if os.path.exists(secrets_path):
            load_api_key(toml_file_path=secrets_path)
            logger.info(f"✓ Loaded secrets from: {secrets_path}")
        
        # ============================================================
        # Step 3: Topic 전처리 (중요!)
        # ============================================================
        # API에서는 이미 clean_topic을 받지만, 혹시 모를 중복 제거
        clean_topic = topic.replace(company_name, "").strip()
        clean_topic = " ".join(clean_topic.split())  # 다중 공백 정규화
        
        # LLM에는 "{company_name} {topic}" 형식으로 전달
        full_topic_for_llm = f"{company_name} {clean_topic}".strip()
        
        logger.info(f"  Clean Topic: {clean_topic}")
        logger.info(f"  Full Topic for LLM: {full_topic_for_llm}")
        
        # ============================================================
        # Step 4: LM Configurations 초기화
        # ============================================================
        jobs_dict[job_id]["progress"] = 20
        logger.info("Initializing LM configurations...")
        lm_configs = _setup_lm_configs(model_provider)
        
        # ============================================================
        # Step 5: PostgresRM 초기화 (내부 DB 검색)
        # ============================================================
        jobs_dict[job_id]["progress"] = 30
        logger.info("Initializing PostgresRM...")
        
        # MVP 최적화 설정 (속도 우선)
        search_top_k = 10
        min_score = 0.5
        
        rm = PostgresRM(k=search_top_k, min_score=min_score)
        rm.set_company_filter(company_name)
        
        logger.info(f"✓ PostgresRM initialized with k={search_top_k}, company_filter={company_name}")
        
        # ============================================================
        # Step 6: STORM Engine Arguments 설정
        # ============================================================
        jobs_dict[job_id]["progress"] = 40
        
        # 격리된 임시 저장소 (Clean Room) - 절대 경로 사용
        output_dir = os.path.abspath(os.path.join("results", "temp", job_id))
        os.makedirs(output_dir, exist_ok=True)
        
        logger.info(f"✓ Clean room created: {output_dir}")
        
        # ============================================================
        # 동시성 제어 (Concurrency Control)
        # OpenAI Tier 1 한도(30k TPM) 보호를 위해 최대 스레드를 제한
        # ============================================================
        max_thread_num_env = os.getenv("STORM_MAX_THREAD_NUM")
        default_threads = STORM_DEFAULT_THREAD_COUNT  # ✅ [REFACTOR] Use constant
        
        if max_thread_num_env:
            # 환경 변수가 있어도 STORM_MAX_THREAD_LIMIT를 넘지 않도록 제한 (안전장치)
            max_thread_num = min(int(max_thread_num_env), STORM_MAX_THREAD_LIMIT)
        else:
            max_thread_num = default_threads
        
        logger.info(f"ℹ️  Thread count set to: {max_thread_num} (Safe limit applied)")

        engine_args = STORMWikiRunnerArguments(
            output_dir=output_dir,
            max_conv_turn=STORM_MAX_CONV_TURN,         # ✅ [REFACTOR] Use constant
            max_perspective=STORM_MAX_PERSPECTIVE,       # ✅ [REFACTOR] Use constant
            search_top_k=search_top_k,
            max_thread_num=max_thread_num,
        )
        
        logger.info(f"✓ Engine arguments configured")
        
        # ============================================================
        # Step 7: STORM Runner 실행 (Long-running process!)
        # ============================================================
        jobs_dict[job_id]["progress"] = PROGRESS_STORM_RUNNING  # ✅ [REFACTOR] Use constant
        logger.info("Starting STORM Runner...")
        
        runner = STORMWikiRunner(engine_args, lm_configs, rm)
        
        # 실제 생성 실행 (1~2분 소요) with simple rate-limit retry
        max_run_retries = STORM_RUN_MAX_RETRIES  # ✅ [REFACTOR] Use constant
        for attempt in range(max_run_retries):
            try:
                runner.run(
                    topic=full_topic_for_llm,
                    do_research=True,
                    do_generate_outline=True,
                    do_generate_article=True,
                    do_polish_article=True
                )
                break
            except Exception as run_err:
                is_rate = _is_rate_limit_error(run_err)
                if is_rate and attempt < max_run_retries - 1:
                    wait_s = RATE_LIMIT_BASE_WAIT_SECONDS * (attempt + 1)  # ✅ [REFACTOR] Use constant
                    logger.warning(
                        f"Rate limit detected; retrying in {wait_s}s (attempt {attempt+1}/{max_run_retries})"
                    )
                    time.sleep(wait_s)
                    continue
                # Re-raise for outer handler
                raise
        
        jobs_dict[job_id]["progress"] = 80
        logger.info("✓ STORM Runner completed successfully")
        
        # ============================================================
        # Step 8: Post-Processing Bridge (FIX-Core-003!)
        # ============================================================
        # ⚠️ 중요: post_run()과 summary() 전에 파일을 먼저 읽어야 함!
        # 이유: post_run()이 추가 파일 작업을 할 수 있기 때문
        # ✅ 파일 읽기 → DB 저장 → Report ID 획득
        jobs_dict[job_id]["progress"] = 85
        logger.info("Starting Post-Processing Bridge...")
        
        report_id = _load_and_save_report_bridge(
            output_dir=output_dir,
            company_name=company_name,
            topic=clean_topic,
            jobs_dict=jobs_dict,
            job_id=job_id,
            model_name="gpt-4o"  # 차후 파라미터로 변경 가능
        )
        
        if report_id is None:
            raise Exception("Post-Processing Bridge failed: Report ID is None")
        
        # Post-processing (선택적 - 로그 생성 등)
        try:
            runner.post_run()
            runner.summary()
        except Exception as e:
            logger.warning(f"Post-run processing warning: {e}")
        
        # ============================================================
        # Step 9: Update Status → Completed
        # ============================================================
        jobs_dict[job_id]["status"] = "completed"
        jobs_dict[job_id]["report_id"] = report_id
        jobs_dict[job_id]["progress"] = 100
        jobs_dict[job_id]["message"] = f"리포트 생성이 완료되었습니다. (Report ID: {report_id})"
        
        logger.info(f"[{job_id}] ✅ Pipeline completed successfully")
        logger.info(f"  Report ID: {report_id}")
        
    except Exception as e:
        # ============================================================
        # Error Handling
        # ============================================================
        logger.error(f"[{job_id}] ❌ Pipeline failed: {e}")
        logger.exception("Full traceback:")
        
        jobs_dict[job_id]["status"] = "failed"
        if _is_rate_limit_error(e):
            jobs_dict[job_id]["message"] = "LLM rate limit에 도달했습니다. 잠시 후 다시 시도해주세요."
        elif isinstance(e, IndexError):
            jobs_dict[job_id]["message"] = "LLM 응답이 비어 있습니다 (가능한 rate limit)."
        else:
            jobs_dict[job_id]["message"] = f"리포트 생성 중 오류 발생: {str(e)}"
        jobs_dict[job_id]["progress"] = 0
        
        # RM이 초기화되었다면 연결 종료
        try:
            if 'rm' in locals():
                rm.close()
        except:
            pass


# ============================================================
# 모듈 테스트 (옵션)
# ============================================================
if __name__ == "__main__":
    print("STORM Service module loaded successfully")
