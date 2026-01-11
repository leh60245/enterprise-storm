# 📘 Enterprise-STORM Project Guidelines
> 이 문서는 STORM 오픈소스를 커스터마이징하여 '기업 분석 전용 RAG 시스템'을 구축하기 위한 통합 개발 지침서입니다. 모든 개발 작업(Coding Task)은 이 문서를 기준으로 수행되어야 합니다.

## 1. 프로젝트 목표 (Project Goal)
* **목표:** 스탠포드 STORM 프레임워크를 기반으로, DART(전자공시시스템) 데이터를 최우선으로 참조하는 고품질 기업 분석 리포트 생성 시스템 구축.
* **핵심 철학:** **Internal Data First.** (내부 DB에 정보가 있으면 외부 검색을 하지 않거나 가중치를 낮춘다.)
* **타겟:** 1월 23일 시연을 위한 MVP (안정성과 정해진 포맷의 리포트 생성이 최우선).

## 2. 시스템 아키텍처 (Architecture)
* **기반 프레임워크:** STORM (Knowledge Curation), dspy
* **언어:** Python 3.10+
* **Database:** PostgreSQL (with `pgvector` extension)
* **Retrieval Flow:**
    1. **User Query** (e.g., "삼성전자 재무 분석")
    2. **Internal Search:** `PostgresConnector`를 통해 내부 DB 검색 (Vector Similarity).
    3. **External Search (Fallback):** 내부 데이터 점수가 낮거나(Threshold < 0.6), 정보가 부족할 때만 외부 검색(Serper/You.com) 실행.
    4. **Generation:** 수집된 정보를 바탕으로 LLM이 섹션별 리포트 작성.

## 3. 데이터베이스 스키마 (Database Schema) ⭐ 중요
모든 SQL 쿼리는 아래 스키마를 엄격히 따라야 한다.

### Table: `Source_Materials` (핵심 데이터)
| 컬럼명 | 타입 | 설명 |
| :--- | :--- | :--- |
| `id` | Integer (PK) | 고유 식별자 |
| `report_id` | Integer (FK) | 보고서 ID (`Analysis_Reports` 테이블 참조) |
| `chunk_type` | VARCHAR | `'text'`, `'table'`, `'noise_merged'` (데이터 처리 분기점) |
| `section_path` | TEXT | 문서 내 경로 (예: "II. 사업의 내용 > 1. 개요") |
| `sequence_order` | INTEGER | 문서 내 등장 순서 (문맥 파악용) |
| `raw_content` | TEXT | 본문 텍스트 또는 Markdown 변환된 표 |
| `embedding` | vector(768) | `ko-sbert` 기반 임베딩 벡터 |
| `metadata` | JSONB | 메타데이터 (예: `{"has_merged_meta": false, "is_noise_dropped": true, "length": 160}`) |

#### `metadata` JSON 필드 구조:
- `has_merged_meta` (boolean): 병합된 메타 정보(단위, 범례 등) 포함 여부 (기본값: false)
- `is_noise_dropped` (boolean): 노이즈로 판단되어 검색 제외된 청크 (chunk_type='noise_merged'일 때만 존재)
- `has_embedding` (boolean): 임베딩 벡터 생성 여부
- `context_injected` (boolean): 문맥 주입 여부
- `length` (integer): 청크 길이

> **Note (2026-01-10 업데이트):** DB 파트의 선행 작업으로 '단위 표', '별첨' 등 노이즈 청크는 Vector DB에 임베딩되지 않고(`chunk_type='noise_merged'`), 직전 텍스트 청크에 병합되어 `metadata.has_merged_meta: true`로 표시됩니다.

## 4. 핵심 개발 규칙 (Development Rules)

### 4.1. 검색 로직 (Retrieval Logic)
* **Connector 분리:** DB 연결 로직은 `knowledge_storm/db/postgres_connector.py`에 독립적으로 구현한다.
* **Noise 필터링:** `chunk_type = 'noise_merged'`인 청크는 검색 결과에 포함되지 않도록 WHERE 절로 필터링. `metadata.is_noise_dropped = true`인 행이 검색 결과에 나타나면 즉시 리포트할 것.
* **표(Table) 처리 알고리즘 - Sliding Window Retrieval:**
    * `chunk_type = 'table'`인 데이터를 조회할 경우, 단독으로 사용하지 않는다.
    * **Sliding Window Context:** `sequence_order ± 1`을 확인하여 **앞뒤 인접 청크**를 함께 가져와 하나의 Context Block으로 구성한다.
    * LLM 제공 포맷: `[이전 문맥]\n{prev_text}\n\n[표 데이터]\n{table_content}\n\n[이후 문맥]\n{next_text}`
* **Merged Meta 활용:**
    * `metadata.has_merged_meta = true`인 청크에는 문단 끝에 병합된 메타 정보(단위, 범례, 기준일자 등)가 포함됨.
    * LLM에게 이를 인지시키는 안내 문구가 자동으로 추가됨: `[참고: 이 문단 끝에 병합된 메타 정보가 포함되어 있습니다...]`

### 4.2. STORM 연동 규격
* 커스텀 검색 모듈(`PostgresRM`)은 STORM의 `dspy.Retrieve` 인터페이스를 준수해야 한다.
* 반환 데이터 형식(List of Dict)을 엄수할 것:
    ```python
    {
        "content": "검색된 본문 내용",
        "title": "섹션 경로 (section_path)",
        "url": "보고서ID (report_id)",  # 가상의 URL로 대체
        "score": 0.85  # 유사도 점수
    }
    ```

### 4.3. 배치 처리 (Batch Processing)
* 실시간 생성보다는 **미리 정의된 주제 리스트**를 순차적으로 처리하는 구조를 지향한다.
* `topics = ["삼성전자 SWOT", "삼성전자 재무"]` 리스트를 받아 루프를 도는 구조로 Runner를 수정한다.

## 5. 환경 변수 및 보안
* DB 접속 정보 및 API 키는 코드에 하드코딩하지 않고 `secrets.toml` 또는 환경 변수에서 로드한다.
* 라이브러리: `psycopg2`, `sentence_transformers`, `numpy` 필수 사용.