# Hypercurve Project Instructions

This repository hosts the **Hypercurve Enterprise Analysis System**, a unified RAG-based service analyzing corporate data.
The project follows a **Monorepo** structure where a shared core (`src/common`) supports both the data ingestion pipeline (`src/ingestion`) and the AI engine (`knowledge_storm`).

## Tech Stack
- **Language:** Python 3.10+
- **AI Engine:** Knowledge Storm (Custom RAG Engine)
- **Vector Store:** ChromaDB
- **Database:** PostgreSQL
- **UI:** Streamlit & CLI (Interactive Mode)

## Repository Structure & Responsibilities
- **`scripts/`**: Entry points for execution.
    - `run_ingestion.py`: Triggers ETL pipeline (Data Write).
    - `run_storm.py`: Main application entry point (Data Read / UI).
- **`src/`**:
    - **`common/`**: **[SHARED RESOURCE]** The single source of truth.
        - `config.py`: ALL configurations (API Keys, DB URLs).
        - `db_connection.py`: Shared DB session logic.
        - `embedding.py`: Shared embedding model wrapper.
    - **`ingestion/`**: **[WRITE-ONLY]** PDF parsing, cleaning, and vector DB insertion.
- **`knowledge_storm/`**: **[READ-ONLY]** The Core AI Agent & RAG Logic.
    - `interface.py`, `lm.py`, `rm.py`: RAG components.
    - `collaborative_storm/`: Advanced agent logic.

## Critical Development Guidelines

### 1. Import Hierarchy (Dependency Rule)
- **`scripts/*.py`** can import from `knowledge_storm` and `src`.
- **`knowledge_storm`** and **`src/ingestion`** should primarily import from **`src.common`**.
- **Avoid Cross-Import:** `src/ingestion` should NOT import `knowledge_storm`, and vice versa, to maintain modularity. They meet only at `src.common` or `scripts`.

### 2. Configuration & DB
- **Do NOT** use `knowledge_storm/db/postgres_connector.py` directly if it conflicts with `src/common`.
- **Prefer** using `src.common.config` and `src.common.db_connection` to ensure both Ingestion and Retrieval use the **same database** and **same embedding model**.

### 3. Execution Context
- Always run from the **Root Directory** using module flags.
- Example: `python -m scripts.run_storm` (O)
- Example: `cd scripts && python run_storm.py` (X) - This causes `ModuleNotFoundError`.