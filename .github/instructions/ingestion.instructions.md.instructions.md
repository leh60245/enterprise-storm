---
applyTo: "src/ingestion/**/*.py"
---

# Data Ingestion Guidelines

When working on `src/ingestion/`:

1. **One-Way Data Flow**
   - This module's ONLY job is to write to PostgreSQL and ChromaDB.
   - It should NOT depend on `knowledge_storm` logic.

2. **Noise Merging Strategy**
   - **Merged Meta:** Small tables/legends must be merged into the *previous* text chunk.
   - **Flag:** Mark merged chunks as `noise_merged` in the DB so the Retriever (in `knowledge_storm`) knows to skip them.

3. **Metadata Enforcement**
   - Ensure `company_name` is present in every chunk's metadata. This is crucial for the filtering logic in `knowledge_storm`.