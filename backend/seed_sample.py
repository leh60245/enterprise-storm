"""
Seed a sample report row into Generated_Reports for testing.
Run: python -m backend.seed_sample
"""

from datetime import datetime
import json
from backend.database import get_db_cursor
from psycopg2.extras import RealDictCursor

SAMPLE = {
    "company_name": "SK하이닉스",
    "topic": "종합 분석",
    "report_content": "# 샘플 리포트\n\n이것은 DB에서 불러온 샘플 리포트입니다.",
    "toc_text": "1. 개요\n2. 재무 분석\n3. 전망",
    "references_data": [
        {"source": "DART 샘플", "content": "샘플 데이터"}
    ],
    "meta_info": {
        "seed": True,
        "generator": "seed_sample.py"
    },
    "model_name": "gpt-4o"
}

def main():
    with get_db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO "Generated_Reports" (company_name, topic, report_content,
                toc_text, references_data, meta_info, model_name, created_at)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, NOW())
            RETURNING id
            """,
            (
                SAMPLE["company_name"],
                SAMPLE["topic"],
                SAMPLE["report_content"],
                SAMPLE["toc_text"],
                json.dumps(SAMPLE["references_data"], ensure_ascii=False),
                json.dumps(SAMPLE["meta_info"], ensure_ascii=False),
                SAMPLE["model_name"],
            ),
        )
        new_id = cur.fetchone()[0]
        print(f"✅ Seeded sample report with id={new_id}")

if __name__ == "__main__":
    main()
