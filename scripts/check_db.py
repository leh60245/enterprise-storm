"""
DB 검증 및 통계 조회 스크립트
"""
import sys
from pathlib import Path

import os

# 프로젝트 루트를 Python 경로에 추가
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# [통합 아키텍처] src.ingestion 사용
from src.ingestion import DBManager
import json

with DBManager() as db:
    # 저장된 데이터 샘플 조회
    db.cursor.execute('''
        SELECT id, report_id, chunk_type, section_path, sequence_order, 
               LENGTH(raw_content) as content_len
        FROM "Source_Materials" 
        WHERE report_id = 1
        ORDER BY report_id, sequence_order
        LIMIT 15
    ''')
    rows = db.cursor.fetchall()
    
    print('=' * 100)
    print('DB에 저장된 데이터 샘플 (상위 15건)')
    print('=' * 100)
    print(f'{"ID":<5} {"Chapter":<20} {"Section":<25} {"Sub-Section":<20} {"Idx":<5} {"Len":<8} {"Tables"}')
    print('-' * 100)
    for row in rows:
        chapter = (row[1] or '')[:18]
        section = (row[2] or '')[:23]
        sub_section = (row[3] or '')[:18]
        print(f'{row[0]:<5} {chapter:<20} {section:<25} {sub_section:<20} {row[4]:<5} {row[5]:<8} {row[6]}')
    
    print('\n' + '=' * 100)
    print('섹션별 통계')
    print('=' * 100)
    db.cursor.execute('''
        SELECT chapter, COUNT(*) as chunk_count, 
               SUM(CASE WHEN tables_json IS NOT NULL THEN 1 ELSE 0 END) as with_tables
        FROM "Source_Materials" 
        WHERE report_id = 1
        GROUP BY chapter
    ''')
    for row in db.cursor.fetchall():
        print(f'{row[0]}: {row[1]}개 청크, {row[2]}개에 테이블 포함')

    # 테이블 데이터 샘플 확인
    print('\n' + '=' * 100)
    print('테이블 데이터 샘플')
    print('=' * 100)
    db.cursor.execute('''
        SELECT id, section_name, tables_json
        FROM "Source_Materials" 
        WHERE report_id = 1 AND tables_json IS NOT NULL
        LIMIT 1
    ''')
    row = db.cursor.fetchone()
    if row:
        print(f'ID: {row[0]}, Section: {row[1]}')
        tables = row[2]
        if tables and len(tables) > 0:
            print(f'테이블 수: {len(tables)}')
            print(f'첫 번째 테이블 샘플:')
            first_table = tables[0]
            print(json.dumps(first_table, indent=2, ensure_ascii=False)[:500] + '...')

    # 텍스트 내용 샘플 확인
    print('\n' + '=' * 100)
    print('텍스트 내용 샘플 (사업의 개요)')
    print('=' * 100)
    db.cursor.execute('''
        SELECT raw_content
        FROM "Source_Materials" 
        WHERE report_id = 1 AND section_name LIKE '%사업의 개요%'
        LIMIT 1
    ''')
    row = db.cursor.fetchone()
    if row:
        print(row[0][:800] + '...')
