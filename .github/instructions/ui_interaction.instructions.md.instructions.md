---
applyTo: ["scripts/**/*.py"]
---

# UI & Execution Guidelines

1. **Interactive Selection (CLI)**
   - In `run_storm.py`, use `src.common.utils` (or similar) to fetch the list of available companies from the DB.
   - Present this list to the user and capture the **Index (Number)**.
   - Pass the **exact string** (e.g., "Samsung Electronics") to the `knowledge_storm` engine.

2. **Module Execution**
   - Ensure standard output (print) is clean and readable in CLI mode.
   - Use logging for debug info, `print()` for user interaction.