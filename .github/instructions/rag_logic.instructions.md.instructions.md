---
applyTo: ["knowledge_storm/**/*.py", "src/common/embedding.py"]
---

# RAG & Retrieval Engine Guidelines

When modifying the AI Engine (`knowledge_storm`) or Embedding Logic:

1. **Metadata Filtering (Strict Requirement)**
   - When calling `rm.py` (Retrieval Model) or Vector Stores, **ALWAYS** apply a metadata filter.
   - **Pattern:** `filter={"company_name": target_company}`
   - The `target_company` must be obtained via explicit user selection (not free text generation).

2. **Embedding Consistency**
   - Ensure that `knowledge_storm` uses the **same embedding model configuration** as defined in `src/common/embedding.py`.
   - If the ingestion pipeline uses "OpenAI-Small", the retriever MUST use "OpenAI-Small".

3. **Window Retrieval Implementation**
   - In `rm.py` or retrieval logic: If a chunk is retrieved, check its `sequence_order` from the DB.
   - Fetch adjacent chunks (Context Expansion) to provide better context to the LLM.

4. **Stateless Web Search**
   - If implementing external search (Google/Tavily) in `knowledge_storm`, do NOT save results to the DB.
   - Use them as temporary context for the current session only.