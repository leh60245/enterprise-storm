# Hypercurve Enterprise STORM - AI Coding Guide

**Enterprise Analysis System** using RAG (Knowledge STORM) to generate corporate reports from DART financial filings.

## Architecture Overview

This is a **bidirectional monorepo** with strict separation between data ingestion (write) and AI retrieval (read):

```
scripts/              # Entry points (ONLY place that imports both sides)
├── run_ingestion.py  # Data pipeline: DART → PostgreSQL → Embeddings
└── run_storm.py      # AI engine: Query → Retrieve → Generate report

src/common/           # [SHARED CORE] - Single source of truth
├── config.py         # Unified config (DB, embeddings, company aliases)
├── embedding.py      # Embedding service (HuggingFace/OpenAI)
└── db_connection.py  # Database session management

src/ingestion/        # [WRITE-ONLY] - Data ETL pipeline
├── pipeline.py       # DART API → Parse → Clean → DB
└── embedding_worker.py  # Generate embeddings with context lookback

knowledge_storm/      # [READ-ONLY] - RAG engine (external dependency)
├── rm.py             # PostgresRM - vector similarity retrieval
├── db/postgres_connector.py  # Low-level DB queries + entity reranking
└── storm_wiki/       # Report generation orchestration
```

**Key Principle**: `src/ingestion` and `knowledge_storm` **never import each other**. They only share `src/common`.

## Critical Workflows

### Running the System
Always execute from **project root** using module syntax to avoid import errors:
```bash
# ✅ Correct
python -m scripts.run_ingestion --test
python -m scripts.run_storm --topic "삼성전자 기업 개요"

# ❌ Wrong (causes ModuleNotFoundError)
cd scripts && python run_storm.py
```

### Data Ingestion Pipeline
```bash
# Test mode: 3 companies (삼성전자, SK하이닉스, NAVER)
python -m scripts.run_ingestion --test

# Production: Process companies with actual reports
python -m scripts.run_ingestion --efficient --limit 10

# Generate embeddings (context-aware with ±1 chunk window)
python -m scripts.run_ingestion --embed --batch-size 32
```

### AI Report Generation
```bash
# Single analysis
python -m scripts.run_storm --topic "SK하이닉스 재무 분석"

# Batch processing with custom model
python -m scripts.run_storm --batch --model-provider gemini

# Output: results/{topic}/storm_gen_article_polished.txt
```

### Testing & Verification
```bash
# Entity bias fix verification
python -m test.verify_entity_bias_fix

# Company filter logic
python -m test.test_company_filter

# DB connectivity
python -m test.test_connection_with_remote
```

## Embedding Architecture (CRITICAL!)

**⚠️ The embedding provider MUST match between ingestion and retrieval, or the system breaks.**

### Provider Configuration
```python
# .env file
EMBEDDING_PROVIDER=huggingface  # or 'openai'
```

- **HuggingFace** (default): 768 dimensions, multilingual, free
- **OpenAI**: 1536 dimensions, higher quality, paid

### Changing Providers (Requires Full Reset)
If you switch providers, you MUST:
1. Delete all existing embeddings: `UPDATE "Source_Materials" SET embedding = NULL`
2. Rebuild pgvector index
3. Re-embed all data: `python -m scripts.run_ingestion --embed --force`

**Why**: Vector dimensions must match. A 768D query cannot search 1536D vectors.

## RAG Retrieval Logic (PostgresRM)

### Entity-Aware Filtering
**Problem**: Querying "SK하이닉스" returns Samsung reports that mention SK Hynix (cross-reference noise).

**Solution**: Entity matching reranker in [postgres_connector.py](knowledge_storm/db/postgres_connector.py):
```python
# Query routing: detect comparison queries
query = "삼성전자와 SK하이닉스 비교"
# → Expands filter to both companies

query = "SK하이닉스 매출"
# → Filters to SK하이닉스 ONLY
# → Drops Samsung tables that mention "SK하이닉스"
```

### Company Alias Resolution
Defined in [src/common/config.py](src/common/config.py):
```python
COMPANY_ALIASES = {
    "삼성전자": ["삼성", "Samsung Electronics", "Samsung", "삼전"],
    "SK하이닉스": ["하이닉스", "SK Hynix", "Hynix"],
    # ... more companies
}
```

**Usage pattern**: Always use `get_canonical_company_name()` to normalize user input before filtering.

### Context Window Retrieval
Tables often need surrounding context. When a Table chunk is retrieved:
- Fetch `sequence_order ± 1` adjacent chunks
- Format as: `[Previous Context] → [Table] → [Next Context]`
- If chunk has `has_merged_meta: true`, inject prompt: `"[참고: 병합된 메타 정보 포함...]"`

## Code Conventions

### Import Rules (Strict Hierarchy)
```python
# ✅ Allowed
from src.common.config import COMPANY_ALIASES, DB_CONFIG
from src.common.embedding import EmbeddingService

# ✅ Scripts can import everything
from src.ingestion import DataPipeline
from knowledge_storm import PostgresRM

# ❌ FORBIDDEN (breaks modularity)
# In src/ingestion/*.py:
from knowledge_storm import STORMWikiRunner  # NO!

# In knowledge_storm/**/*.py:
from src.ingestion import DataPipeline  # NO!
```

### File I/O (Windows Encoding)
**Always specify UTF-8** on Windows (default is cp949):
```python
# ✅ Correct
with open(path, "w", encoding="utf-8") as f:
    f.write(content)

# ❌ Wrong (causes UnicodeDecodeError)
with open(path, "w") as f:
    f.write(content)
```

### PostgreSQL JSON Extraction
Metadata is stored as JSONB. Extract keys with `->>`:
```sql
-- ✅ Correct
SELECT (metadata->>'has_merged_meta')::boolean
WHERE (metadata->>'company_name') = '삼성전자'

-- ❌ Wrong (treats as column)
SELECT has_merged_meta
```

### LLM API Error Handling
Common issues documented in [CLAUDE.md](CLAUDE.md):
- **Gemini 404**: Model names need `models/` prefix → auto-normalized in [lm.py](knowledge_storm/lm.py)
- **Rate limits (429)**: Backoff with exponential retry (max 5 minutes)
- **Empty responses**: Safety filters may block output → check `response.parts` before accessing

## Data Model & DB Schema

### Source_Materials Table
```sql
id SERIAL PRIMARY KEY,
report_id INTEGER REFERENCES "DART_Reports"(id),
content TEXT,                    -- Actual text chunk
embedding VECTOR(768),           -- pgvector (dimension = EMBEDDING_PROVIDER)
chunk_type VARCHAR(50),          -- 'text' | 'table' | 'meta'
sequence_order INTEGER,          -- For context window retrieval
metadata JSONB                   -- {company_name, has_merged_meta, section, ...}
```

### Generated_Reports Table
Output of STORM runs:
```sql
company_name VARCHAR(255),
company_id INTEGER REFERENCES "Companies"(id) ON DELETE CASCADE,  -- ✅ FK (2026-01-16)
topic TEXT,
report_content TEXT,             -- Polished article
toc_text TEXT,                   -- Table of contents
references_data JSONB,           -- url_to_info.json
conversation_log JSONB,          -- Full agent dialogue
meta_info JSONB,                 -- {config, search_results}
model_name VARCHAR(100)          -- 'gpt-4o' | 'gemini-1.5-pro'
```

**Important**: `company_id`는 `company_name`으로 자동 조회되므로 선택적 파라미터입니다 (하위 호환성).

## Testing Philosophy

Each feature has **3 verification layers**:
1. **Unit tests**: Mock data tests (e.g., `test_entity_bias.py`)
2. **Integration tests**: Real DB queries with sample data
3. **Verification scripts**: End-to-end validation (e.g., `verify_entity_bias_fix.py`)

### Example Test Pattern
```python
# test/test_company_filter.py
def test_postgres_rm_query_routing():
    """Verify comparison query expansion"""
    rm = PostgresRM(k=5, company_filter="삼성전자")
    
    # Normal query → single company filter
    result = rm.forward("재무 현황")
    assert all("삼성전자" in r['company'] for r in result.passages)
    
    # Comparison query → multi-company expansion
    result = rm.forward("삼성전자와 SK하이닉스 비교")
    companies = {r['company'] for r in result.passages}
    assert "삼성전자" in companies and "SK하이닉스" in companies
```

## Common Pitfalls (Learned from CLAUDE.md)

1. **Silent Failure in Loops**: NEVER use `if success:` pattern in batch operations - always raise exception on failure (Fixed: 2026-01-16)
2. **String-based FK**: Always use integer FK instead of string matching for entity relationships (Fixed: 2026-01-16)
3. **Module vs Folder Name Conflicts**: Never create `package/utils/` if `package/utils.py` exists (Python prioritizes folder)
4. **Metadata Structure Mismatch**: Check if fields are JSONB keys or real columns before writing SQL
5. **STORM Output URLs Must Be Unique**: Each chunk needs unique URL (e.g., `dart_report_{report_id}_chunk_{chunk_id}`) or all references collapse to `[1]`
6. **Embedding Dimension Validation**: Run `validate_embedding_dimension_compatibility()` on startup to catch mismatches early
7. **Rate Limit Backoff**: Don't give up on 429 errors - exponentially back off up to 5 minutes

## Documentation Strategy

When implementing new features:
1. Add technical details to [CLAUDE.md](CLAUDE.md) (error log format)
2. Create feature report in `docs/FEAT-XXX-*.md` (executive summary)
3. Update relevant instruction files (`.github/instructions/*.instructions.md`)
4. Write verification test in `verify/verify_*.py`
5. **[NEW]** Document critical bugs in [.github/CRITICAL_FIXES.md](.github/CRITICAL_FIXES.md)

---

**Need more context?** Check:
- [CLAUDE.md](CLAUDE.md) - Error history and solutions
- [.github/CRITICAL_FIXES.md](.github/CRITICAL_FIXES.md) - P0/P1 bug fixes
- [docs/](docs/) - Feature implementation reports
- [.github/instructions/](instructions/) - Domain-specific rules