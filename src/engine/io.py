"""
STORM Engine I/O Module
파일 시스템 경로 관리, 안전한 디렉토리 생성, JSON/Text 파일 입출력을 담당합니다.
"""

import json
import logging
import os
import re
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


def get_safe_dir_name(name: str, fallback: str = "unknown") -> str:
    """Windows/Linux 호환 가능한 안전한 디렉토리명 생성"""
    if not name:
        return fallback
    # 공백 -> 언더스코어, 경로 구분자 -> 언더스코어
    safe = name.replace(" ", "_").replace("/", "_").replace("\\", "_")
    # 특수문자 제거
    safe = re.sub(r'[:*?"<>|]', "", safe)
    # 앞뒤 점/공백 제거
    return safe.strip(". ") or fallback


def create_run_directory(
    base_dir: str, company_id: int, company_name: str, job_id: str = None
) -> str:
    """
    실행 결과를 저장할 타임스탬프 기반 디렉토리를 생성합니다.
    형식: {base_dir}/YYYYMMDD_HHMMSS_{company_name}_{job_id_suffix}
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_company = get_safe_dir_name(company_name, fallback=f"comp_{company_id}")

    # Job ID가 있으면 짧게 접미사로 사용
    suffix = f"_{job_id[:8]}" if job_id else ""
    dir_name = f"{timestamp}_{safe_company}{suffix}"

    full_path = os.path.abspath(os.path.join(base_dir, dir_name))

    # 중복 시 순번 붙임
    if os.path.exists(full_path):
        counter = 1
        while os.path.exists(f"{full_path}_{counter}"):
            counter += 1
        full_path = f"{full_path}_{counter}"

    os.makedirs(full_path, exist_ok=True)
    logger.info(f"Created run directory: {full_path}")
    return full_path


def load_storm_output_files(topic_dir: str) -> dict[str, Any]:
    """
    STORM이 생성한 결과 파일들을 읽어 딕셔너리로 반환합니다.
    (Article, Outline, References, Logs, Search Results)
    """
    result = {
        "report_content": None,
        "toc_text": None,
        "references": None,
        "logs": None,
        "search_results": None,
        "run_config": None,
    }

    if not os.path.exists(topic_dir):
        logger.error(f"Topic directory not found: {topic_dir}")
        return result

    # 1. Report Content (Polished > Raw)
    polished_path = os.path.join(topic_dir, "storm_gen_article_polished.txt")
    raw_path = os.path.join(topic_dir, "storm_gen_article.txt")

    if os.path.exists(polished_path):
        result["report_content"] = _safe_read_text(polished_path)
    elif os.path.exists(raw_path):
        result["report_content"] = _safe_read_text(raw_path)

    # 2. Other Metadata
    result["toc_text"] = _safe_read_text(
        os.path.join(topic_dir, "storm_gen_outline.txt")
    )
    result["references"] = _safe_read_json(os.path.join(topic_dir, "url_to_info.json"))
    result["logs"] = _safe_read_json(os.path.join(topic_dir, "conversation_log.json"))
    result["search_results"] = _safe_read_json(
        os.path.join(topic_dir, "raw_search_results.json")
    )
    result["run_config"] = _safe_read_json(os.path.join(topic_dir, "run_config.json"))

    return result


def find_topic_directory(base_output_dir: str) -> str | None:
    """
    STORM 실행 결과 폴더 내에서 실제 토픽(결과물이 있는) 폴더를 찾습니다.
    """
    # 1. 하위 디렉토리 목록 조회
    subdirs = [
        os.path.join(base_output_dir, d)
        for d in os.listdir(base_output_dir)
        if os.path.isdir(os.path.join(base_output_dir, d))
    ]

    # 2. 결과 파일이 존재하는 디렉토리 찾기
    for subdir in subdirs:
        if os.path.exists(os.path.join(subdir, "url_to_info.json")):
            return subdir

    return None


def write_run_metadata(output_dir: str, metadata: dict[str, Any]):
    """실행 메타데이터를 run_meta.json으로 저장합니다."""
    path = os.path.join(output_dir, "run_meta.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Failed to write run metadata: {e}")


# Internal Helpers
def _safe_read_text(path: str) -> str | None:
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return f.read()
        except Exception:
            return None
    return None


def _safe_read_json(path: str) -> Any | None:
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None
