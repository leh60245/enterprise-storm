"""
Context Look-back 임베딩 워커

표(Table) 데이터의 임베딩 품질을 높이기 위해 직전 텍스트 문맥을 포함하여
임베딩을 생성하고 DB를 업데이트하는 스크립트입니다.

핵심 로직:
- 표(table) 데이터는 그 자체만으로는 단위(Unit)나 기준 날짜 정보가 부족함
- 보통 표 바로 위에 설명 텍스트가 존재하므로, 이를 합쳐서 벡터화
- 'previous_row'를 캐싱하며 순차적으로 처리

사용법:
    python -m scripts.run_ingestion --embed --batch-size 32
    python -m scripts.run_ingestion --embed --limit 100  # 테스트용
    python -m scripts.run_ingestion --embed --force      # 기존 임베딩 재생성
"""
import sys
import os
import re
import time
import argparse
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from tqdm import tqdm

# [통합 아키텍처] 공통 모듈 및 같은 패키지 모듈 import
from src.common.embedding import EmbeddingService
from src.common.config import CHUNK_CONFIG
from .db_manager import DBManager


@dataclass
class MaterialRow:
    """Source_Materials 테이블의 행을 나타내는 데이터 클래스"""
    id: int
    report_id: int
    chunk_type: str
    section_path: Optional[str]
    sequence_order: int
    raw_content: str


class ContextLookbackEmbeddingWorker:
    """
    Context Look-back 방식으로 임베딩을 생성하는 워커 클래스

    표(table) 데이터의 경우, 같은 섹션 내 직전 텍스트 블록의 내용을
    문맥으로 포함하여 임베딩 품질을 향상시킵니다.

    노이즈 테이블(단위, 범례 등)은 직전 청크에 병합하여 검색 정확도를 높입니다.
    """

    # 노이즈 테이블 감지를 위한 키워드
    NOISE_KEYWORDS = ['단위', 'Unit', '범례', '참조', '※', '주)', '(주)',
                      '원', '천원', '백만원', '억원', '주1)', '주2)', '(단위']

    # 노이즈 테이블 최대 행 수 (Markdown 테이블 기준)
    NOISE_TABLE_MAX_ROWS = 2

    # 노이즈 테이블 최대 텍스트 길이 (문자 수)
    NOISE_TABLE_MAX_LENGTH = 150

    def __init__(self, batch_size: int = 32):
        self.batch_size = batch_size
        self._embedding_service: Optional[EmbeddingService] = None
        self.stats = {
            "total": 0,
            "processed": 0,
            "text_count": 0,
            "table_count": 0,
            "table_with_context": 0,  # 문맥이 주입된 테이블 수
            "noise_tables_merged": 0,  # 노이즈 테이블로 병합된 수
            "noise_tables_skipped": 0,  # 병합 대상 없어 스킵된 노이즈 테이블 수
            "failed": 0,
            "start_time": None,
            "end_time": None
        }

    def _init_generator(self):
        """임베딩 서비스 초기화 (lazy loading)"""
        if self._embedding_service is None:
            self._embedding_service = EmbeddingService()
            print(f"   임베딩 프로바이더: {self._embedding_service.provider}")
            print(f"   임베딩 차원: {self._embedding_service.dimension}")

    # ==================== 노이즈 테이블 감지 ====================

    def _is_noise_table(self, table_content: str) -> bool:
        """
        테이블이 노이즈 데이터(단위, 범례 등)인지 판단

        Heuristic 판단 로직:
        - 조건 A: 테이블의 행(Row) 수가 2줄 이하이고 키워드 포함
        - 조건 B: 키워드 포함 비율이 50% 이상 (단어 기준)

        Args:
            table_content: Markdown 형식의 테이블 콘텐츠

        Returns:
            bool: 노이즈 테이블이면 True, 아니면 False
        """
        if not table_content:
            return False

        # Markdown 테이블 행 파싱 (| 로 시작하는 줄)
        lines = table_content.strip().split('\n')
        table_rows = [line for line in lines if line.strip().startswith('|')]

        # 헤더 구분선 제거 (|---|---| 형태)
        data_rows = [row for row in table_rows if not re.match(r'^\|[\s\-:]+\|$', row.strip())]

        # 조건 A: 행 수가 2줄 이하이고 키워드 포함
        row_count = len(data_rows)
        if row_count <= self.NOISE_TABLE_MAX_ROWS:
            for keyword in self.NOISE_KEYWORDS:
                if keyword in table_content:
                    return True

        # 조건 B: 키워드 포함 비율 50% 이상 (단어 기준)
        content_text = re.sub(r'[|\-:]+', ' ', table_content)
        words = [w.strip() for w in content_text.split() if len(w.strip()) > 0]

        if len(words) == 0:
            return False

        # 키워드를 포함하는 단어 수 계산
        keyword_word_count = 0
        for word in words:
            for keyword in self.NOISE_KEYWORDS:
                if keyword in word:
                    keyword_word_count += 1
                    break

        keyword_ratio = keyword_word_count / len(words)
        if keyword_ratio >= 0.5:
            return True

        return False

    # ==================== 데이터 조회 ====================

    def fetch_pending_materials(
        self,
        db: DBManager,
        limit: Optional[int] = None,
        force: bool = False
    ) -> List[MaterialRow]:
        """
        임베딩이 없는(또는 force=True면 전체) Source_Materials 조회

        Args:
            db: DBManager 인스턴스
            limit: 최대 조회 개수 (테스트용)
            force: True면 기존 임베딩이 있어도 재처리

        Returns:
            List[MaterialRow]: id 오름차순으로 정렬된 데이터 리스트

        Note:
            - 반드시 id 오름차순으로 정렬해야 문맥 파악이 가능
            - report_id, sequence_order 기준으로도 정렬하여 문서 내 순서 유지
        """
        if force:
            # 전체 데이터 조회 (재처리)
            sql = """
                SELECT id, report_id, chunk_type, section_path, 
                       sequence_order, raw_content
                FROM "Source_Materials"
                ORDER BY report_id, sequence_order, id
            """
        else:
            # 임베딩이 없는 데이터만 조회
            sql = """
                SELECT id, report_id, chunk_type, section_path, 
                       sequence_order, raw_content
                FROM "Source_Materials"
                WHERE embedding IS NULL
                ORDER BY report_id, sequence_order, id
            """

        if limit is not None:
            sql = sql.rstrip() + f" LIMIT {limit}"

        db.cursor.execute(sql)
        rows = db.cursor.fetchall()

        return [
            MaterialRow(
                id=row[0],
                report_id=row[1],
                chunk_type=row[2],
                section_path=row[3],
                sequence_order=row[4],
                raw_content=row[5]
            )
            for row in rows
        ]

    def fetch_previous_row(self, db: DBManager, current: MaterialRow) -> Optional[MaterialRow]:
        """
        현재 행의 직전 행을 조회 (같은 report_id 내에서)

        배치 처리 시 직전 행이 배치에 포함되지 않은 경우를 대비하여
        DB에서 직접 조회합니다.

        Args:
            db: DBManager 인스턴스
            current: 현재 처리 중인 행

        Returns:
            직전 행 (없으면 None)
        """
        sql = """
            SELECT id, report_id, chunk_type, section_path, 
                   sequence_order, raw_content
            FROM "Source_Materials"
            WHERE report_id = %s 
              AND sequence_order < %s
            ORDER BY sequence_order DESC
            LIMIT 1
        """
        db.cursor.execute(sql, (current.report_id, current.sequence_order))
        row = db.cursor.fetchone()

        if row:
            return MaterialRow(
                id=row[0],
                report_id=row[1],
                chunk_type=row[2],
                section_path=row[3],
                sequence_order=row[4],
                raw_content=row[5]
            )
        return None

    # ==================== 문맥 주입 전처리 ====================

    # Note: build_embedding_text는 레거시 메서드입니다.
    # 실제 처리는 process_batch에서 _build_normal_embedding_text를 사용합니다.

    def _build_normal_embedding_text(
        self,
        current: MaterialRow,
        previous: Optional[MaterialRow]
    ) -> Tuple[str, bool]:
        """
        일반 블록(노이즈가 아닌)의 임베딩 텍스트를 구성

        Args:
            current: 현재 처리 중인 행
            previous: 직전 행 (없을 수 있음)

        Returns:
            Tuple[str, bool]: (임베딩용 텍스트, 문맥 주입 여부)
        """
        section_path = current.section_path or "알 수 없음"
        raw_content = current.raw_content or ""

        # Case A: 표(table)에 직전 텍스트 문맥 주입
        if (
            current.chunk_type == 'table'
            and previous is not None
            and previous.chunk_type == 'text'
            and previous.section_path == current.section_path
        ):
            context_text = previous.raw_content or ""
            max_context_len = 500
            if len(context_text) > max_context_len:
                context_text = context_text[:max_context_len] + "..."

            embedding_text = (
                f"문서 경로: {section_path}\n"
                f"[문맥 설명: {context_text}]\n"
                f"[표 데이터]\n"
                f"{raw_content}"
            )
            return embedding_text, True

        # Case B: 일반 텍스트 또는 문맥 없는 표
        embedding_text = f"문서 경로: {section_path}\n{raw_content}"
        return embedding_text, False

    # ==================== 임베딩 생성 및 DB 업데이트 ====================

    def update_embedding(
        self,
        db: DBManager,
        material_id: int,
        embedding: List[float],
        has_context: bool = False,
        has_merged_meta: bool = False
    ):
        """
        Source_Materials 테이블에 임베딩 업데이트

        Args:
            db: DBManager 인스턴스
            material_id: Source_Materials.id
            embedding: 임베딩 벡터
            has_context: 문맥이 주입되었는지 여부 (메타데이터에 기록)
            has_merged_meta: 노이즈 테이블이 병합되었는지 여부 (메타데이터에 기록)
        """
        sql = """
            UPDATE "Source_Materials"
            SET embedding = %s,
                metadata = jsonb_set(
                    jsonb_set(
                        jsonb_set(
                            COALESCE(metadata, '{}'), 
                            '{has_embedding}', 
                            'true'
                        ),
                        '{context_injected}',
                        %s
                    ),
                    '{has_merged_meta}',
                    %s
                )
            WHERE id = %s
        """
        db.cursor.execute(sql, (
            embedding,
            'true' if has_context else 'false',
            'true' if has_merged_meta else 'false',
            material_id
        ))

    def _merge_noise_to_previous(self, db: DBManager, prev_id: int, noise_table_content: str):
        """
        직전 청크(Previous)에 노이즈 테이블 내용을 영구적으로 병합

        Args:
            db: DBManager 인스턴스
            prev_id: 직전 청크의 ID
            noise_table_content: 노이즈 테이블 내용 (Markdown)
        """
        sql = """
            UPDATE "Source_Materials"
            SET raw_content = raw_content || E'\n\n[참조 정보]\n' || %s,
                metadata = jsonb_set(COALESCE(metadata, '{}'), '{has_merged_meta}', 'true'),
                embedding = NULL
            WHERE id = %s
        """
        db.cursor.execute(sql, (noise_table_content, prev_id))

    def _mark_as_noise_merged(self, db: DBManager, current_id: int):
        """
        현재 노이즈 테이블을 Drop 처리 (chunk_type 변경, 임베딩 제거)

        Args:
            db: DBManager 인스턴스
            current_id: 노이즈 테이블의 ID
        """
        sql = """
            UPDATE "Source_Materials"
            SET chunk_type = 'noise_merged',
                embedding = NULL,
                metadata = jsonb_set(COALESCE(metadata, '{}'), '{is_noise_dropped}', 'true')
            WHERE id = %s
        """
        db.cursor.execute(sql, (current_id,))

    def process_batch(
        self,
        db: DBManager,
        batch: List[MaterialRow],
        previous_cache: Dict[int, MaterialRow]
    ) -> Dict[int, MaterialRow]:
        """
        배치 단위로 임베딩 생성 및 업데이트

        노이즈 테이블 병합 로직:
        - 노이즈 테이블 감지 시 → Previous에 내용 Append, Current는 Drop
        - Previous의 임베딩을 재생성해야 하므로, 해당 Previous를 임베딩 대상에 추가

        Args:
            db: DBManager 인스턴스
            batch: 처리할 MaterialRow 리스트
            previous_cache: report_id별 마지막 처리 행 캐시

        Returns:
            업데이트된 previous_cache
        """
        embedding_inputs = []  # (material_id, embedding_text, has_context, has_merged_meta)
        ids_to_skip = set()  # Drop 처리할 노이즈 테이블 ID
        prev_ids_to_reembed = {}  # 재임베딩이 필요한 Previous: {prev_id: merged_content}

        for current in batch:
            # 직전 행 조회: 캐시에서 먼저 확인, 없으면 DB 조회
            previous = previous_cache.get(current.report_id)

            # 캐시된 previous가 현재 행의 직전이 아닐 수 있음 (sequence_order 체크)
            if previous is not None:
                if previous.sequence_order != current.sequence_order - 1:
                    previous = self.fetch_previous_row(db, current)
            else:
                previous = self.fetch_previous_row(db, current)

            # --- 노이즈 테이블 감지 및 병합 처리 ---
            if (
                current.chunk_type == 'table'
                and self._is_noise_table(current.raw_content)
                and previous is not None
            ):
                # 1. Previous에 Current 내용 Append (DB 업데이트)
                self._merge_noise_to_previous(db, previous.id, current.raw_content)

                # 2. Current를 Drop 처리 (DB 업데이트)
                self._mark_as_noise_merged(db, current.id)
                ids_to_skip.add(current.id)

                # 3. Previous의 병합된 내용을 기록 (나중에 임베딩 재생성)
                merged_content = (previous.raw_content or "") + "\n\n[참조 정보]\n" + (current.raw_content or "")
                prev_ids_to_reembed[previous.id] = {
                    "content": merged_content,
                    "section_path": previous.section_path
                }

                # 4. 캐시 업데이트: Previous의 내용이 변경되었으므로 갱신
                previous.raw_content = merged_content
                previous_cache[current.report_id] = previous

                # 5. 통계 업데이트
                self.stats["table_count"] += 1
                self.stats["noise_tables_merged"] += 1
                continue  # Current는 임베딩 대상에서 제외

            # --- 일반 처리 (노이즈가 아닌 경우) ---
            embedding_text, has_context = self._build_normal_embedding_text(current, previous)
            embedding_inputs.append((current.id, embedding_text, has_context, False))

            # 통계 업데이트
            if current.chunk_type == 'text':
                self.stats["text_count"] += 1
            else:
                self.stats["table_count"] += 1
                if has_context:
                    self.stats["table_with_context"] += 1

            # 캐시 업데이트
            previous_cache[current.report_id] = current

        # Previous 재임베딩 대상 추가
        for prev_id, data in prev_ids_to_reembed.items():
            section_path = data["section_path"] or "알 수 없음"
            embedding_text = f"문서 경로: {section_path}\n{data['content']}"
            # has_merged_meta=True로 표시
            embedding_inputs.append((prev_id, embedding_text, False, True))

        # 배치 임베딩 생성
        if not embedding_inputs:
            db.conn.commit()
            return previous_cache

        texts = [item[1] for item in embedding_inputs]
        try:
            embeddings = self._embedding_service.embed_texts(texts)

            # DB 업데이트
            for (material_id, _, has_context, has_merged_meta), embedding in zip(embedding_inputs, embeddings):
                self.update_embedding(db, material_id, embedding, has_context, has_merged_meta)

            db.conn.commit()
            self.stats["processed"] += len(batch) - len(ids_to_skip)

        except Exception as e:
            db.conn.rollback()
            print(f"\n⚠️ 배치 처리 실패: {e}")
            self.stats["failed"] += len(batch)

        return previous_cache

    # ==================== 메인 실행 ====================

    def run(
        self,
        limit: Optional[int] = None,
        force: bool = False
    ):
        """
        Context Look-back 임베딩 파이프라인 실행

        Args:
            limit: 최대 처리 개수 (테스트용)
            force: True면 기존 임베딩이 있어도 재처리
        """
        self.stats["start_time"] = datetime.now()

        print("\n" + "=" * 70)
        print("🧠 Context Look-back 임베딩 워커 시작")
        print("=" * 70)
        print(f"   시작 시간: {self.stats['start_time'].strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   배치 크기: {self.batch_size}")
        print(f"   강제 재생성: {'예' if force else '아니오'}")

        # 1. 임베딩 생성기 초기화
        self._init_generator()

        # 2. 처리 대상 데이터 조회
        with DBManager() as db:
            pending_materials = self.fetch_pending_materials(db, limit, force)

        self.stats["total"] = len(pending_materials)
        print(f"\n📋 처리 대상: {self.stats['total']}개 청크")

        if self.stats["total"] == 0:
            print("✅ 처리할 데이터가 없습니다.")
            return self.stats

        # 3. 배치 분할
        batches = [
            pending_materials[i:i + self.batch_size]
            for i in range(0, len(pending_materials), self.batch_size)
        ]
        print(f"📦 배치 수: {len(batches)}")

        # 4. 배치 처리
        # previous_cache: report_id → 마지막 처리된 MaterialRow
        # 이를 통해 배치 간에도 직전 행 정보를 유지
        previous_cache: Dict[int, MaterialRow] = {}

        with DBManager() as db:
            for batch in tqdm(batches, desc="임베딩 생성"):
                previous_cache = self.process_batch(db, batch, previous_cache)

                # 메모리 관리를 위한 짧은 딜레이
                time.sleep(0.05)

        # 5. 결과 요약
        self.stats["end_time"] = datetime.now()
        self._print_summary()

        return self.stats

    def _print_summary(self):
        """실행 결과 요약 출력"""
        duration = self.stats["end_time"] - self.stats["start_time"]

        print("\n" + "=" * 70)
        print("📊 Context Look-back 임베딩 결과")
        print("=" * 70)
        print(f"   시작 시간: {self.stats['start_time'].strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   종료 시간: {self.stats['end_time'].strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   소요 시간: {duration}")

        print(f"\n   📈 처리 통계:")
        print(f"      - 전체 대상: {self.stats['total']}")
        print(f"      - 성공: {self.stats['processed']}")
        print(f"      - 실패: {self.stats['failed']}")

        print(f"\n   📝 타입별 통계:")
        print(f"      - 텍스트 블록: {self.stats['text_count']}")
        print(f"      - 테이블 블록: {self.stats['table_count']}")
        print(f"      - 문맥 주입된 테이블: {self.stats['table_with_context']}")
        print(f"      - 노이즈 테이블 병합: {self.stats['noise_tables_merged']}")

        if self.stats['table_count'] > 0:
            context_rate = (self.stats['table_with_context'] / self.stats['table_count']) * 100
            noise_rate = (self.stats['noise_tables_merged'] / self.stats['table_count']) * 100
            print(f"      - 테이블 문맥 주입률: {context_rate:.1f}%")
            print(f"      - 노이즈 테이블 병합률: {noise_rate:.1f}%")

        if self.stats['total'] > 0:
            success_rate = (self.stats['processed'] / self.stats['total']) * 100
            print(f"\n      - 전체 성공률: {success_rate:.1f}%")

            # 처리 속도
            seconds = duration.total_seconds()
            if seconds > 0:
                rate = self.stats['processed'] / seconds
                print(f"      - 처리 속도: {rate:.1f} 청크/초")

        # DB 현황
        with DBManager() as db:
            stats = db.get_stats()
            print(f"\n   📦 DB 현황:")
            print(f"      - 전체 원천 데이터: {stats['materials']}")
            print(f"      - 임베딩 완료: {stats['embedded_materials']}")

            if stats['materials'] > 0:
                embed_rate = (stats['embedded_materials'] / stats['materials']) * 100
                print(f"      - 임베딩 비율: {embed_rate:.1f}%")

        print("=" * 70)


def main():
    """CLI 엔트리포인트"""
    parser = argparse.ArgumentParser(
        description="Context Look-back 임베딩 워커 - 표 데이터에 직전 텍스트 문맥을 주입하여 임베딩 생성"
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=32,
        help='한 번에 처리할 청크 수 (기본: 32)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='최대 처리 개수 (테스트용)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='기존 임베딩이 있어도 재생성'
    )

    args = parser.parse_args()

    worker = ContextLookbackEmbeddingWorker(batch_size=args.batch_size)
    worker.run(limit=args.limit, force=args.force)


if __name__ == "__main__":
    main()

