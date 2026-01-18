# FEAT-Core-002: HybridRM 구현 완료 보고서

**Task ID**: FEAT-Core-002-HybridRM-Library  
**Priority**: P0 (Critical)  
**Status**: ✅ Completed  
**Date**: 2026-01-18  

---

## 📋 작업 개요

기존 DART 내부 검색(PostgresRM)과 Google 외부 검색(SerperRM)을 **3:7 비율**로 혼합하여, **Fact(과거 데이터)**와 **Trend(최신 뉴스)**를 동시에 확보하는 **HybridRM** 클래스를 구현했습니다.

### 구현 위치

- **Core Engine**: `knowledge_storm/rm.py` (엔진 라이브러리 내부)
- **CLI Script**: `scripts/run_storm.py` (테스트용 스크립트)

---

## 🎯 구현 내용

### 1. HybridRM 클래스 구현 ([knowledge_storm/rm.py](knowledge_storm/rm.py))

#### 설계 패턴

- **Composition (조립)**: PostgresRM과 SerperRM 인스턴스를 내부적으로 보유
- **코드 재사용**: 기존 RM 클래스의 코드를 복사하지 않고 인스턴스 조합

#### 주요 기능

- **초기화**

  ```python
  HybridRM(
      internal_rm: PostgresRM,      # DART 내부 검색
      external_rm: SerperRM,        # Google 외부 검색
      internal_k: int = 3,          # 내부 검색 결과 개수
      external_k: int = 7           # 외부 검색 결과 개수
  )
  ```

- **검색 프로세스**
  1. **내부 검색** (PostgresRM): DART 보고서에서 `internal_k`개 검색
  2. **외부 검색** (SerperRM): Google에서 `external_k`개 검색
  3. **결과 병합**: URL 기준 중복 제거 후 통합
  4. **Source 태그**: 각 결과에 `'source': 'internal'` 또는 `'external'` 추가

- **Fallback 처리**
  - 내부/외부 검색 실패 시 에러 로그 출력 후 빈 리스트로 처리
  - 한쪽이 실패해도 다른 쪽 결과는 반환

- **주요 메서드**
  - `forward(query)`: 하이브리드 검색 수행
  - `set_company_filter(company_name)`: 내부 RM의 기업 필터 설정
  - `get_usage_and_reset()`: 사용량 통계 조회 (내부/외부 합산)
  - `close()`: 연결 종료

---

### 2. scripts/run_storm.py 수정

#### Import 추가

```python
from knowledge_storm.rm import PostgresRM, SerperRM, HybridRM
```

#### 초기화 로직 변경

```python
# 기존 코드
# rm = PostgresRM(k=args.search_top_k, min_score=args.min_score)

# 수정 코드
internal_rm = PostgresRM(k=args.search_top_k, min_score=args.min_score)
external_rm = SerperRM(serper_search_api_key=os.getenv("SERPER_API_KEY"), k=args.search_top_k)
rm = HybridRM(internal_rm, external_rm, internal_k=3, external_k=7)
```

---

## ✅ 검증 방법

### 1. 검증 스크립트 실행

```bash
python -m verify.verify_hybrid_rm
```

**Expected Output:**

```bash
[1] Initializing Internal RM (PostgresRM)...
✓ PostgresRM initialized

[2] Initializing External RM (SerperRM)...
✓ SerperRM initialized

[3] Initializing HybridRM...
✓ HybridRM initialized with 3:7 ratio

[4] Testing hybrid search with query: 'HBM 시장 전망'
✓ Total passages returned: 10

--- Source Distribution ---
  Internal (DART): 3 passages
  External (Google): 7 passages
  Total: 10 passages

--- Verification Results ---
  ✓ Passages returned (> 0)
  ✓ Internal sources found (3)
  ✓ External sources found (7)
  ✓ All passages have 'source' tag

✅ HybridRM verification PASSED!
```

---

### 2. CLI 테스트 (실제 리포트 생성)

```bash
# 환경 변수 설정 확인
echo $env:SERPER_API_KEY  # Windows PowerShell

# HybridRM을 사용한 리포트 생성
python -m scripts.run_storm 
```

**성공 기준:**

1. **콘솔 로그에서 확인**
   - ✅ `[HybridRM] Internal search (k=3)...`
   - ✅ `[HybridRM] External search (k=7)...`
   - ✅ Serper API 호출 로그 (`SerperRM` 관련 메시지)

2. **생성된 리포트 확인**

   ```bash
   # 출력 경로 확인
   # results/enterprise/YYYYMMDD_HHMMSS_{company_id}_{company_name}/{ai_query}/storm_gen_article_polished.txt
   ```

---

## 🔧 설정 요구사항

### 환경 변수

```bash
# .env 파일에 추가
SERPER_API_KEY=your_serper_api_key_here

# 기존 환경 변수 (필수)
OPENAI_API_KEY=...
PG_HOST=...
PG_PASSWORD=...
EMBEDDING_PROVIDER=huggingface  # 또는 openai
```

### Serper API Key 발급

1. <https://serper.dev/> 접속
2. 가입 후 API Key 발급 (무료 플랜: 2,500 queries/month)
3. `.env` 파일에 `SERPER_API_KEY` 추가

---

## 📊 성능 특성

### 검색 비율: Internal(3) : External(7)

**내부 검색 (DART)**

- ✅ 높은 신뢰도 (공식 재무제표, 사업보고서)
- ✅ 구조화된 데이터 (표, 재무 수치)
- ❌ 최신 뉴스 부족 (보고서는 분기별 발행)

**외부 검색 (Google)**

- ✅ 최신 시장 동향 (실시간 뉴스)
- ✅ 산업 분석 기사, 전문가 의견
- ❌ 신뢰도 검증 필요 (출처 다양)

**하이브리드 효과**

- 📈 **과거**: DART 보고서 → 재무 실적, 사업 현황
- 🚀 **현재**: Google 뉴스 → 최신 기술 동향, 시장 전망
- 🎯 **균형**: 3:7 비율로 신뢰도와 최신성 동시 확보

---

## 🚨 주의사항

### 1. API 비용

- **Serper API**: 무료 플랜 2,500 queries/month 초과 시 유료 전환
- **사용량 추적**: `hybrid_rm.get_usage_and_reset()` 메서드로 모니터링

### 2. 검색 품질

- **중복 제거**: URL 기준으로 중복 제거 (동일 출처 여러 번 검색 방지)
- **순서 보장**: 내부 결과 → 외부 결과 순으로 병합 (신뢰도 우선)
