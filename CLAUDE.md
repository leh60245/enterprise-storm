클로드 코드가 실수를 할 때마다 규칙을 추가하는 파일
- 목표: 작업을 진행하며 코딩 스타일과 아키텍처 규칙을 자체적으로 학습하고 개선해 스스로 오류를 수정하도록 함

---

## 오류 기록

### [2026-01-08] Task 001: 모듈 경로 충돌 오류

**오류 상황:**
- DEV_GUIDELINES.md에서 명시한 `storm/utils/postgres_connector.py` 경로 대신 `knowledge_storm/utils/postgres_connector.py`를 생성하려 함
- 그러나 `knowledge_storm/utils.py` 파일이 이미 존재하는 상태에서 `knowledge_storm/utils/` 폴더를 생성
- Python이 폴더를 모듈로 인식하여 기존 `utils.py`의 클래스들(`ArticleTextProcessing` 등)을 임포트할 수 없게 됨

**원인:**
- Python에서 `package/module.py`와 `package/module/` 폴더가 동시에 존재할 경우, 폴더가 우선권을 가짐
- 기존 코드베이스의 여러 파일들이 `from .utils import ArticleTextProcessing` 형태로 임포트하고 있었음

**해결 방안:**
- `knowledge_storm/utils/` 폴더 이름을 `knowledge_storm/db/`로 변경
- PostgresConnector는 `knowledge_storm.db.PostgresConnector`로 임포트

**교훈 (규칙 추가):**
1. **새 모듈 생성 전 기존 모듈명 확인 필수**: 같은 이름의 `.py` 파일이 존재하는지 반드시 확인할 것
2. **기존 임포트 패턴 분석**: `grep_search`로 해당 모듈을 임포트하는 코드를 먼저 검색할 것
3. **폴더 생성 시 대안 이름 고려**: `utils/` 대신 목적에 맞는 이름 사용 (예: `db/`, `connectors/`, `adapters/`)

### [2026-01-10] Gemini 모델명 404 오류

**오류 상황:**
```
404 models/gemini-1.5-flash is not found for API version v1beta, or is not supported for generateContent.
```

**원인:**
- Google Gemini API에서 모델명 형식이 `models/gemini-1.5-flash` 형태를 요구함
- 코드에서 `gemini-1.5-flash`로 전달하면 API에서 인식하지 못함
- 반대로 `models/` 접두사를 포함해서 전달해도 일부 버전에서 문제 발생 가능

**해결 방안:**
- `knowledge_storm/lm.py`의 `GoogleModel.__init__`에서 모델명 정규화 로직 추가
- 모델명에 `models/` 접두사가 없으면 자동으로 추가:
  ```python
  if not model.startswith("models/"):
      model = f"models/{model}"
  ```

**교훈 (규칙 추가):**
1. **외부 API 모델명 형식 확인**: API 버전에 따라 모델명 형식이 다를 수 있음
2. **방어적 코딩**: 모델명 정규화 로직을 추가하여 다양한 입력 형식 지원

### [2026-01-10] Gemini 응답 `list index out of range` 오류

**오류 상황:**
```
Error: list index out of range
```

**원인:**
- `GoogleModel.__call__`에서 `response.parts[0].text`에 접근할 때 발생
- Gemini API가 안전 필터(safety filter)로 응답을 차단하거나 빈 응답을 반환할 경우 `response.parts`가 빈 리스트
- 빈 리스트에 `[0]` 인덱스로 접근하면 `IndexError: list index out of range` 발생

**해결 방안:**
- `knowledge_storm/lm.py`의 `GoogleModel.__call__` 메서드에 방어적 코드 추가:
  ```python
  if response.parts and len(response.parts) > 0:
      completions.append(response.parts[0].text)
  elif response.candidates and len(response.candidates) > 0:
      # candidates에서 텍스트 추출 시도
      ...
  else:
      logging.warning("Gemini returned empty response")
      completions.append("")
  ```

**교훈 (규칙 추가):**
1. **외부 API 응답 검증 필수**: 리스트/배열 접근 전 길이 확인
2. **안전 필터 고려**: LLM API는 콘텐츠 정책 위반 시 빈 응답 반환 가능

### [2026-01-10] Gemini Rate Limit (429) 및 Safety Filter 오류

**오류 상황:**
```
Gemini response blocked or empty. Finish reason: 2
429 You exceeded your current quota... limit: 5, model: gemini-2.5-flash
Giving up request(...) after 1 tries
```

**원인:**
1. **Safety Filter (Finish reason: 2)**: Gemini가 콘텐츠를 안전하지 않다고 판단하여 응답 차단
2. **Rate Limit (429)**: 무료 티어 분당 5회 제한 초과
3. **즉시 포기**: `giveup_hdlr`가 429 에러에서도 재시도를 포기함

**해결 방안:**
1. **Safety Settings 완화** (`knowledge_storm/lm.py` GoogleModel):
   ```python
   from google.generativeai.types import HarmCategory, HarmBlockThreshold
   self.safety_settings = {
       HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
       HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
       ...
   }
   ```

2. **Rate Limit 재시도 설정**:
   ```python
   @backoff.on_exception(
       backoff.expo,
       (Exception,),
       max_time=300,  # 최대 5분 대기
       max_tries=5,
       factor=10,  # 10초부터 지수 백오프
       giveup=lambda e: False,  # 429에서도 재시도
   )
   def request(self, prompt: str, **kwargs):
   ```

**교훈 (규칙 추가):**
1. **무료 API 할당량 주의**: Gemini 무료 티어는 분당 5회 제한
2. **Safety Settings 명시적 설정**: 기업 분석 등 안전한 데이터는 필터 완화 필요
3. **Rate Limit 재시도 필수**: 429 에러는 대기 후 재시도로 해결 가능

### [2026-01-10] UTF-8 디코딩 오류 및 출처 인덱스 중복 문제

**오류 상황:**
```
Error: 'utf-8' codec can't decode byte 0xbb in position 13: invalid start byte
```
- 추가로, 생성된 리포트에서 모든 출처 번호가 `[1]`로만 표시됨

**원인:**
1. **UTF-8 오류**: `FileIOHelper.write_str()` 및 `load_str()`에서 `encoding="utf-8"` 미지정
   - Windows 기본 인코딩(cp949)으로 파일 저장/읽기 시도하여 한글 깨짐
2. **출처 인덱스 중복**: PostgresConnector에서 URL을 `dart_report_{report_id}` 형식으로 생성
   - 같은 report_id의 모든 청크가 동일한 URL → STORM이 동일 출처로 인식 → 인덱스 1로 통합

**해결 방안:**
1. **UTF-8 인코딩 명시** (`knowledge_storm/utils.py`):
   ```python
   @staticmethod
   def write_str(s, path):
       with open(path, "w", encoding="utf-8") as f:
           f.write(s)
   ```

2. **고유 URL 생성** (`knowledge_storm/db/postgres_connector.py`):
   ```python
   # 기존: dart_report_{report_id}
   # 수정: dart_report_{report_id}_chunk_{id}
   unique_url = f"dart_report_{row['report_id']}_chunk_{row['id']}"
   ```
   - SQL 쿼리에 `id` 컬럼 추가

**교훈 (규칙 추가):**
1. **Windows에서 파일 I/O 시 인코딩 명시 필수**: `encoding="utf-8"` 항상 지정
2. **STORM 출처 인덱스는 URL 기반**: 각 검색 결과는 고유한 URL을 가져야 별도 출처로 인식됨

### [2026-01-10] metadata JSON 필드 구조 오류

**오류 상황:**
- `postgres_connector.py`에서 `has_merged_meta`와 `is_noise_dropped`를 별도 컬럼으로 가정하고 SQL 작성
- 실제로는 `metadata` JSONB 컬럼 내부의 키로 존재

**원인:**
- DB 스키마 확인 시 `metadata` JSON 구조를 상세히 파악하지 못함
- 사용자가 예시 JSON 제공 전까지 컬럼 구조를 잘못 이해

**해결 방안:**
- SQL 쿼리 수정:
  ```sql
  -- 기존 (잘못됨)
  COALESCE(has_merged_meta, false) as has_merged_meta
  
  -- 수정 (올바름)
  COALESCE((metadata->>'has_merged_meta')::boolean, false) as has_merged_meta
  ```
- WHERE 절 수정: `WHERE chunk_type != 'noise_merged'` (is_noise_dropped는 별도 필터링 불필요)
- DEV_GUIDELINES.md에 metadata JSON 구조 상세 문서화

**교훈 (규칙 추가):**
1. **JSON/JSONB 컬럼 구조 확인 필수**: PostgreSQL의 JSON 타입은 `->>` 연산자로 키 추출
2. **실제 데이터 예시 요청**: 스키마만으로 불명확할 경우 실제 데이터 샘플을 요청
3. **타입 캐스팅 주의**: JSON에서 추출한 값은 text 타입이므로 `::boolean`, `::integer` 등으로 캐스팅 필요

---

## 완료된 작업

### [2026-01-08] Task 001: PostgresConnector 구현 ✓
- **파일**: `knowledge_storm/db/postgres_connector.py`
- **기능**: PostgreSQL DB 벡터 유사도 검색, Context Look-back 로직
- **임포트**: `from knowledge_storm.db import PostgresConnector`

### [2026-01-08] Task 002: PostgresRM 구현 ✓
- **파일**: `knowledge_storm/rm.py` (클래스 추가)
- **기능**: STORM 엔진 호환 `dspy.Retrieve` 래퍼 클래스
- **임포트**: `from knowledge_storm.rm import PostgresRM`
- **주요 메서드**:
  - `forward(query_or_queries, exclude_urls=[], k=None)` → `dspy.Prediction` 반환
  - `get_usage_and_reset()` → 사용량 추적
  - `close()` → 연결 종료
- **특징**: `min_score` 임계값 미만 결과에 대한 경고 로그 (하이브리드 검색 준비)

### [2026-01-08] Task 003: Enterprise STORM Runner 구현 ✓
- **파일**: `examples/run_enterprise_storm.py` (신규 생성)
- **기능**: PostgresRM을 사용한 기업 분석 리포트 일괄 생성
- **실행**: `python examples/run_enterprise_storm.py [options]`
- **주요 기능**:
  - 5개 기본 분석 주제 배치 처리 (ANALYSIS_TARGETS)
  - PostgresRM(k=10, min_score=0.5) 기본 설정
  - 진행 상황 로그 출력 `[1/5] Processing: '...'`
  - 토픽별 출력 디렉토리 자동 생성 (덮어쓰기 방지)
  - CLI 옵션: `--topics`, `--search-top-k`, `--min-score`, `--max-conv-turn` 등

### [2026-01-10] Task: 결과 적재 로직 구현 ✓
- **파일**: `examples/run_enterprise_storm.py` (수정)
- **기능**: STORM 실행 완료 후 결과를 PostgreSQL `Generated_Reports` 테이블에 INSERT
- **함수**: `save_report_to_db(topic, output_dir, secrets_path, model_name="gpt-4o")`
- **주요 로직**:
  - **필수 파일 읽기**: `storm_gen_article_polished.txt`, `url_to_info.json`
  - **선택 파일 읽기**: `storm_gen_outline.txt`, `conversation_log.json`, `run_config.json`, `raw_search_results.json`
  - **meta_info 생성**: `{"config": run_config_data, "search_results": raw_search_results_data}`
  - **company_name 추출**: `topic.split()[0]` (첫 단어)
  - **DB INSERT**: 8개 컬럼 (company_name, topic, report_content, toc_text, references_data, conversation_log, meta_info, model_name)
- **호출 위치**: `run_batch_analysis()` 함수 내 `runner.summary()` 후 호출

### [2026-01-10] Task: LLM 모델 선택 옵션 구현 ✓
- **파일**: `examples/run_enterprise_storm.py` (수정), `requirements.txt` (수정)
- **기능**: `--model-provider` 인자로 OpenAI 또는 Gemini 모델 선택 가능
- **주요 변경사항**:
  - **Import 추가**: `GoogleModel` 임포트
  - **CLI 인자 추가**: `--model-provider` (choices: `openai`, `gemini`, default: `openai`)
  - **`setup_lm_configs(provider)` 리팩토링**: provider에 따라 분기 처리
    - `openai`: GPT-3.5-turbo (fast) + GPT-4o (pro)
    - `gemini`: gemini-1.5-flash (fast) + gemini-1.5-pro (pro)
  - **DB 저장 시 모델명 동적 결정**: `current_model_name` 변수로 관리
  - **requirements.txt**: `google-generativeai` 추가
- **실행 예시**:
  - OpenAI: `python examples/run_enterprise_storm.py`
  - Gemini: `python examples/run_enterprise_storm.py --model-provider gemini`

### [2026-01-10] Task: RAG Context 고도화 - Sliding Window Retrieval & Merged Meta Prompting ✓
- **파일들**:
  - `knowledge_storm/db/postgres_connector.py` (주요 수정)
  - `knowledge_storm/storm_wiki/modules/article_generation.py` (Signature 수정)
  - `knowledge_storm/storm_wiki/modules/knowledge_curation.py` (Signature 수정)
  - `DEV_GUIDELINES.md` (스키마 및 규칙 업데이트)
- **기능**:
  - **Sliding Window Retrieval**: Table 타입 청크에 대해 `sequence_order ± 1` 인접 청크를 함께 조회하여 Context Block 구성
  - **Merged Meta Prompting**: `has_merged_meta: true`인 청크에 LLM 안내 문구 자동 삽입
  - **Noise 필터링**: `is_noise_dropped: true` 청크는 검색에서 자동 제외 + 검증 로직
- **주요 변경사항**:
  - `_fetch_context_for_tables()` → `_fetch_window_context(window_size)` 리팩토링
  - SQL 쿼리에 `has_merged_meta`, `is_noise_dropped` 컬럼 추가
  - WHERE 절에 `is_noise_dropped = false` 필터 추가
  - `WriteSection`, `AnswerQuestion` Signature에 메타 정보 확인 지침 추가
  - Content 포맷 변경: `[이전 문맥] → [표 데이터] → [이후 문맥]`
  - `has_merged_meta` 시 `[참고: 병합된 메타 정보 포함...]` 안내 삽입
- **API 변경**: `connector.search(query, top_k, window_size=1)` - window_size 파라미터 추가
