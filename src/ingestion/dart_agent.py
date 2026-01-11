"""
DART 보고서 에이전트 모듈 - DART API를 통한 사업보고서 수집 및 파싱
순차적 블록 처리(Sequential Block Processing) 지원
"""
import dart_fss as dart
from bs4 import BeautifulSoup, NavigableString, Tag
import re
import json
import time
from datetime import datetime, timedelta
import pandas as pd
from io import StringIO
from typing import Optional, List, Dict, Tuple

# [통합 아키텍처] 공통 모듈에서 설정 가져오기
from src.common.config import DART_CONFIG, CHUNK_CONFIG, TARGET_SECTIONS

# 레거시 호환 변수
DART_API_KEY = DART_CONFIG.get("api_key")
REPORT_SEARCH_CONFIG = {
    "bgn_de": DART_CONFIG.get("search_start_date", "20240101"),
    "pblntf_detail_ty": DART_CONFIG.get("report_type_code", "a001"),
    "page_count": DART_CONFIG.get("page_count", 100),
    "page_delay_sec": DART_CONFIG.get("page_delay_sec", 0.5),
    "max_search_days": DART_CONFIG.get("max_search_days", 90),
}


class DartReportAgent:
    """
    DART API를 사용하여 사업보고서를 수집하고 파싱하는 에이전트
    """

    def __init__(self):
        """에이전트 초기화 및 DART API 설정"""
        dart.set_api_key(api_key=DART_API_KEY)
        print("🔄 기업 리스트 로딩 중...")
        self._corp_list = None

    @property
    def corp_list(self):
        """기업 리스트 (lazy loading)"""
        if self._corp_list is None:
            self._corp_list = dart.get_corp_list()
            print(f"✅ 기업 리스트 로드 완료: {len(self._corp_list)}개 기업")
        return self._corp_list

    # ==================== 기업 조회 ====================

    def get_corp_by_stock_code(self, stock_code: str):
        """종목코드로 기업 정보 조회"""
        for corp in self.corp_list:
            if corp.stock_code == stock_code:
                return corp
        return None

    def get_corp_by_corp_code(self, corp_code: str):
        """법인코드로 기업 정보 조회"""
        for corp in self.corp_list:
            if corp.corp_code == corp_code:
                return corp
        return None

    def get_listed_corps(self) -> List:
        """상장 기업만 필터링 (사업보고서 존재 가능성 높음)"""
        return [c for c in self.corp_list if c.stock_code]

    def search_all_reports(
        self,
        bgn_de: str = None,
        end_de: str = None,
        corp_code: str = None
    ) -> List[Dict]:
        """
        기간 내 모든 사업보고서를 일괄 검색 (효율적인 방식)

        corp_code가 없으면 검색 기간은 최대 3개월(90일)로 제한됩니다.

        Args:
            bgn_de: 검색 시작일 (YYYYMMDD), 기본값은 config에서 가져옴
            end_de: 검색 종료일 (YYYYMMDD), 기본값은 오늘
            corp_code: 특정 기업만 검색할 경우 법인코드 지정

        Returns:
            List[Dict]: 보고서 정보 딕셔너리 리스트
                - corp_code, corp_name, stock_code, rcept_no, rcept_dt, report_nm 등
        """
        # 기본값 설정
        if end_de is None:
            end_de = datetime.now().strftime("%Y%m%d")
        if bgn_de is None:
            bgn_de = REPORT_SEARCH_CONFIG['bgn_de']

        # corp_code가 없으면 검색 기간을 최대 90일(3개월)로 제한
        if corp_code is None:
            max_days = REPORT_SEARCH_CONFIG.get('max_search_days', 90)
            bgn_date = datetime.strptime(bgn_de, "%Y%m%d")
            end_date = datetime.strptime(end_de, "%Y%m%d")

            if (end_date - bgn_date).days > max_days:
                bgn_date = end_date - timedelta(days=max_days)
                bgn_de = bgn_date.strftime("%Y%m%d")
                print(f"⚠️ corp_code 미지정: 검색 기간을 최대 {max_days}일로 제한 ({bgn_de} ~ {end_de})")

        all_reports = []
        page_no = 1
        page_count = REPORT_SEARCH_CONFIG.get('page_count', 100)
        page_delay = REPORT_SEARCH_CONFIG.get('page_delay_sec', 0.5)

        print(f"📋 사업보고서 검색 시작: {bgn_de} ~ {end_de}")
        if corp_code:
            print(f"   대상 기업: {corp_code}")

        while True:
            try:
                # dart.filings.search 사용 (기간 내 모든 사업보고서 검색)
                search_kwargs = {
                    'bgn_de': bgn_de,
                    'end_de': end_de,
                    'pblntf_detail_ty': REPORT_SEARCH_CONFIG['pblntf_detail_ty'],
                    'page_count': page_count,
                    'page_no': page_no
                }

                # corp_code가 있으면 특정 기업만 검색
                if corp_code:
                    search_kwargs['corp_code'] = corp_code

                search_result = dart.filings.search(**search_kwargs)

                # 결과 추출 (SearchResults 객체는 속성으로 접근)
                report_list = getattr(search_result, 'report_list', []) or []
                if not report_list:
                    break

                all_reports.extend(report_list)

                total_page = getattr(search_result, 'total_page', 1) or 1
                total_count = getattr(search_result, 'total_count', 0) or 0

                print(f"   📄 Page {page_no}/{total_page}: {len(report_list)}건 (누적 {len(all_reports)}/{total_count})")

                # 마지막 페이지면 종료
                if page_no >= total_page:
                    break

                page_no += 1
                time.sleep(page_delay)  # Rate Limiting

            except Exception as e:
                print(f"⚠️ 보고서 검색 오류 (page={page_no}): {e}")
                break

        print(f"✅ 검색 완료: 총 {len(all_reports)}건의 사업보고서")
        return all_reports

    def get_corps_with_reports(
        self,
        bgn_de: str = None,
        end_de: str = None,
        deduplicate: bool = True
    ) -> List[Tuple]:
        """
        사업보고서가 있는 기업 목록 반환 (효율적인 일괄 검색 방식)

        기존 방식: 전체 상장사 순회하며 개별 API 호출 (비효율)
        새로운 방식: dart.filings.search로 기간 내 사업보고서 일괄 검색 (효율)

        Args:
            bgn_de: 검색 시작일 (YYYYMMDD)
            end_de: 검색 종료일 (YYYYMMDD)
            deduplicate: True면 기업당 최신 보고서 1건만 반환 (기본값)

        Returns:
            List[Tuple]: (corp 객체, report 딕셔너리) 튜플 리스트
        """
        # 일괄 검색으로 사업보고서 목록 가져오기
        all_reports = self.search_all_reports(bgn_de=bgn_de, end_de=end_de)

        if not all_reports:
            return []

        # 기업별 최신 보고서만 남기기 (중복 제거)
        if deduplicate:
            corp_latest = {}
            for report in all_reports:
                # Report 객체는 속성으로 접근 (딕셔너리가 아님)
                corp_code = getattr(report, 'corp_code', None)
                rcept_dt = getattr(report, 'rcept_dt', '')

                if corp_code not in corp_latest:
                    corp_latest[corp_code] = report
                else:
                    # 더 최신 보고서로 교체
                    if rcept_dt > getattr(corp_latest[corp_code], 'rcept_dt', ''):
                        corp_latest[corp_code] = report

            reports_to_process = list(corp_latest.values())
            print(f"📌 중복 제거 후: {len(reports_to_process)}개 기업")
        else:
            reports_to_process = all_reports

        # (corp 객체, report 객체) 튜플 리스트 생성
        corps_with_reports = []
        for report in reports_to_process:
            corp_code = getattr(report, 'corp_code', None)
            corp = self.get_corp_by_corp_code(corp_code)

            if corp:
                corps_with_reports.append((corp, report))
            else:
                # corp_list에 없는 경우 (비상장사 등)
                corp_name = getattr(report, 'corp_name', 'Unknown')
                print(f"   ⚠️ 기업 정보 없음: {corp_name} ({corp_code})")

        return corps_with_reports

    # ==================== 보고서 검색 ====================

    def get_annual_report(self, corp_code: str, bgn_de: str = None):
        """
        사업보고서 검색 (가장 최근 1건)

        Args:
            corp_code: 법인코드
            bgn_de: 검색 시작일 (YYYYMMDD)

        Returns:
            Report 객체 또는 None
        """
        bgn_de = bgn_de or REPORT_SEARCH_CONFIG['bgn_de']

        try:
            search_results = dart.search(
                corp_code=corp_code,
                bgn_de=bgn_de,
                pblntf_detail_ty=REPORT_SEARCH_CONFIG['pblntf_detail_ty']
            )
            return search_results[0] if search_results else None
        except Exception as e:
            print(f"⚠️ 보고서 검색 오류 (corp_code={corp_code}): {e}")
            return None

    def get_report_info(self, report) -> Dict:
        """보고서 메타정보 추출"""
        return {
            "title": report.report_nm,
            "rcept_no": report.rcept_no,
            "rcept_dt": report.rcept_dt,
            "corp_code": report.corp_code,
            "corp_name": report.corp_name,
            "report_type": "annual"
        }

    # ==================== 섹션 추출 ====================

    def get_all_sections(self, report) -> List[Dict]:
        """
        보고서의 모든 섹션 목록 조회

        Returns:
            List[Dict]: 섹션 정보 리스트
        """
        try:
            all_pages = report.find_all()
            pages = all_pages.get('pages', [])

            sections = []
            for i, page in enumerate(pages):
                sections.append({
                    "index": i,
                    "title": getattr(page, 'title', f'Page_{i}'),
                    "type": type(page).__name__
                })
            return sections
        except Exception as e:
            print(f"⚠️ 섹션 목록 조회 실패: {e}")
            return []

    def extract_section(self, report, section_keyword: str) -> Optional[Dict]:
        """
        특정 키워드를 포함하는 섹션 추출

        Args:
            report: DART 보고서 객체
            section_keyword: 섹션 검색 키워드

        Returns:
            Dict: {"section_name": str, "text": str, "tables": list, "page_count": int}
        """
        try:
            result = report.find_all(includes=section_keyword)
            pages = result.get('pages', [])

            if not pages:
                return None

            # 모든 페이지 텍스트 병합
            full_text = ""
            tables = []

            for page in pages:
                soup = BeautifulSoup(page.html, 'html.parser')

                # 테이블 추출
                for table in soup.find_all('table'):
                    table_data = self._parse_table(table)
                    if table_data:
                        tables.append(table_data)

                # 텍스트 추출 (테이블 포함)
                text = soup.get_text(separator='\n').strip()
                text = self._clean_text(text)
                full_text += text + "\n\n"

            return {
                "section_name": section_keyword,
                "text": full_text.strip(),
                "tables": tables,
                "page_count": len(pages)
            }

        except Exception as e:
            print(f"⚠️ 섹션 추출 실패 ({section_keyword}): {e}")
            return None

    def extract_target_sections(self, report) -> List[Dict]:
        """
        핵심 섹션들 추출 (config.py의 TARGET_SECTIONS 기준)

        Returns:
            List[Dict]: 추출된 섹션 정보 리스트
        """
        extracted = []

        for section_name in TARGET_SECTIONS:
            section_data = self.extract_section(report, section_name)
            if section_data:
                extracted.append(section_data)
                print(f"   ✅ '{section_name}' 추출 완료 ({section_data['page_count']}페이지)")
            else:
                print(f"   ⚠️ '{section_name}' 섹션 없음")

        return extracted

    # ==================== 고급 추출 (테이블/텍스트 분리) ====================

    def extract_page_data_with_tables(self, page) -> Dict:
        """
        DART 페이지에서 텍스트와 테이블을 분리 추출

        테이블은 tables_json에 저장하고, content_text에는 테이블이 제외된 순수 텍스트만 저장

        Args:
            page: DART 페이지 객체

        Returns:
            Dict: {"title": str, "content_text": str, "tables": list}
        """
        html = page.html
        soup = BeautifulSoup(html, 'html.parser')

        # 1. 먼저 테이블 데이터 추출 (JSON 직렬화 가능한 형태로)
        tables_json = []
        try:
            html_io = StringIO(str(soup))
            dfs = pd.read_html(html_io, flavor='bs4')

            for idx, df in enumerate(dfs):
                # NaN -> 빈 문자열
                df_clean = df.where(pd.notnull(df), "")
                # DataFrame -> JSON -> Dict 변환 (Numpy 타입 해결)
                json_str = df_clean.to_json(orient='records', force_ascii=False)
                table_data = json.loads(json_str)

                tables_json.append({
                    "table_index": idx,
                    "data": table_data
                })
        except ValueError:
            pass  # 테이블 없음
        except Exception as e:
            print(f"   ⚠️ 테이블 파싱 중 오류: {e}")

        # 2. HTML에서 테이블 요소 제거 후 텍스트 추출
        # 복사본에서 작업
        soup_for_text = BeautifulSoup(html, 'html.parser')

        # 모든 <table> 태그와 그 내용을 제거
        for table in soup_for_text.find_all('table'):
            # 테이블 위치에 마커 추가
            table.replace_with('[TABLE]')

        # 테이블 제거 후 텍스트 추출
        content_text = soup_for_text.get_text(separator='\n').strip()
        content_text = self._clean_text(content_text)

        # [TABLE] 마커 정리 (연속된 마커 제거 및 안내문 변환)
        content_text = re.sub(r'\[TABLE\]\s*(\[TABLE\]\s*)+', '[TABLE]\n', content_text)
        content_text = re.sub(r'\[TABLE\]\s*', '\n[테이블 참조]\n', content_text)

        return {
            "title": getattr(page, 'title', 'Unknown'),
            "content_text": content_text,
            "tables": tables_json
        }

    def parse_hierarchical_content(self, page_title: str, text: str) -> List[Dict]:
        """
        텍스트를 계층적으로 파싱 (chapter/section/sub_section)

        Args:
            page_title: 상위 챕터명 (예: "II. 사업의 내용")
            text: 파싱할 텍스트

        Returns:
            List[Dict]: 파싱된 섹션 리스트
        """
        # 중단원 패턴 (1. 사업의 개요)
        main_pattern = re.compile(r'\n(\d+\.\s+[^\n]+)')
        # 소단원 패턴 (가. 업계의 현황)
        sub_pattern = re.compile(r'\n([가-하]\.\s+[^\n]+)')

        main_matches = list(main_pattern.finditer(text))
        parsed_data = []

        # 중단원이 없는 경우 전체를 하나의 섹션으로 처리
        if not main_matches:
            parsed_data.append({
                'chapter': page_title,
                'section': page_title,
                'sub_section': None,
                'content': text.strip()
            })
            return parsed_data

        for i in range(len(main_matches)):
            m_start = main_matches[i].start()
            m_title = main_matches[i].group(1).strip()

            if i < len(main_matches) - 1:
                m_end = main_matches[i + 1].start()
            else:
                m_end = len(text)

            m_content = text[m_start + len(m_title) + 1: m_end]

            # 소단원으로 재분할
            sub_matches = list(sub_pattern.finditer(m_content))

            if not sub_matches:
                # 소단원이 없으면 중단원 전체를 저장
                parsed_data.append({
                    'chapter': page_title,
                    'section': m_title,
                    'sub_section': None,
                    'content': m_content.strip()
                })
            else:
                for j in range(len(sub_matches)):
                    s_start = sub_matches[j].start()
                    s_title = sub_matches[j].group(1).strip()

                    if j < len(sub_matches) - 1:
                        s_end = sub_matches[j + 1].start()
                    else:
                        s_end = len(m_content)

                    s_content = m_content[s_start + len(s_title) + 1: s_end]

                    parsed_data.append({
                        'chapter': page_title,
                        'section': m_title,
                        'sub_section': s_title,
                        'content': s_content.strip()
                    })

        return parsed_data

    def extract_section_advanced(self, report, section_keyword: str) -> Optional[Dict]:
        """
        고급 섹션 추출 - 페이지별로 텍스트와 테이블 동기화

        각 페이지의 텍스트와 테이블을 개별적으로 처리하여 동기화 보장

        Args:
            report: DART 보고서 객체
            section_keyword: 섹션 검색 키워드

        Returns:
            Dict: {"chapter": str, "pages_data": list, "page_count": int}
        """
        try:
            result = report.find_all(includes=section_keyword)
            pages = result.get('pages', [])

            if not pages:
                return None

            # 페이지별로 처리하여 텍스트-테이블 동기화
            pages_data = []

            for page in pages:
                page_data = self.extract_page_data_with_tables(page)
                page_title = page_data['title']  # 실제 페이지 제목 사용
                content_text = page_data['content_text']
                tables = page_data['tables']

                # 이 페이지의 텍스트를 계층적으로 파싱
                parsed_sections = self.parse_hierarchical_content(page_title, content_text)

                # [테이블 참조] 마커가 있는 섹션에 해당 테이블 연결
                table_idx = 0
                for parsed in parsed_sections:
                    content = parsed.get('content', '')
                    marker_count = content.count('[테이블 참조]')

                    if marker_count > 0 and table_idx < len(tables):
                        # 마커 개수만큼 테이블 할당
                        parsed['tables'] = tables[table_idx:table_idx + marker_count]
                        table_idx += marker_count
                    else:
                        parsed['tables'] = []

                pages_data.append({
                    'page_title': page_title,
                    'sections': parsed_sections,
                    'tables_in_page': len(tables)
                })

            return {
                "chapter": section_keyword,
                "pages_data": pages_data,
                "page_count": len(pages)
            }

        except Exception as e:
            print(f"⚠️ 고급 섹션 추출 실패 ({section_keyword}): {e}")
            import traceback
            traceback.print_exc()
            return None

    def extract_target_sections_advanced(self, report) -> List[Dict]:
        """
        핵심 섹션들 고급 추출 (테이블/텍스트 분리, 페이지별 동기화)

        Returns:
            List[Dict]: 추출된 섹션 정보 리스트
        """
        extracted = []

        for section_name in TARGET_SECTIONS:
            section_data = self.extract_section_advanced(report, section_name)
            if section_data:
                extracted.append(section_data)
                page_count = section_data['page_count']
                total_sections = sum(len(p['sections']) for p in section_data['pages_data'])
                total_tables = sum(p['tables_in_page'] for p in section_data['pages_data'])
                print(f"   ✅ '{section_name}' 추출 완료 "
                      f"({page_count}페이지, {total_sections}개 섹션, {total_tables}개 테이블)")
            else:
                print(f"   ⚠️ '{section_name}' 섹션 없음")

        return extracted

    # ==================== 청킹 ====================

    def chunk_text(
        self,
        text: str,
        chunk_size: int = None,
        overlap: int = None
    ) -> List[str]:
        """
        텍스트를 청크로 분할

        Args:
            text: 분할할 텍스트
            chunk_size: 청크 최대 크기
            overlap: 청크 간 오버랩

        Returns:
            List[str]: 청크 리스트
        """
        chunk_size = chunk_size or CHUNK_CONFIG['max_chunk_size']
        overlap = overlap or CHUNK_CONFIG['overlap']
        min_size = CHUNK_CONFIG['min_chunk_size']

        if len(text) <= chunk_size:
            return [text] if len(text) >= min_size else []

        chunks = []
        start = 0

        while start < len(text):
            end = start + chunk_size

            # 문장 경계에서 자르기 시도
            if end < len(text):
                # 마침표, 줄바꿈 등에서 자르기
                for sep in ['\n\n', '\n', '. ', '다. ', '요. ']:
                    last_sep = text[start:end].rfind(sep)
                    if last_sep > chunk_size // 2:  # 최소 절반 이상일 때만
                        end = start + last_sep + len(sep)
                        break

            chunk = text[start:end].strip()

            if len(chunk) >= min_size:
                chunks.append(chunk)
            elif chunks:
                # 너무 작으면 이전 청크에 병합
                chunks[-1] += " " + chunk

            start = end - overlap

            # 무한 루프 방지
            if start >= len(text) - min_size:
                break

        return chunks

    def chunk_section(self, section_data: Dict) -> List[Dict]:
        """
        섹션 데이터를 청크로 분할

        Args:
            section_data: extract_section()의 반환값

        Returns:
            List[Dict]: 청크 정보 리스트
        """
        text = section_data.get('text', '')
        section_name = section_data.get('section_name', 'Unknown')
        tables = section_data.get('tables', [])

        chunks = self.chunk_text(text)

        result = []
        for idx, chunk in enumerate(chunks):
            result.append({
                "section_name": section_name,
                "chunk_index": idx,
                "content": chunk,
                "metadata": {
                    "total_chunks": len(chunks),
                    "has_tables": len(tables) > 0,
                    "tables": tables if idx == 0 else []  # 첫 청크에만 테이블 포함
                }
            })

        return result

    def chunk_section_advanced(self, section_data: Dict) -> List[Dict]:
        """
        고급 섹션 청킹 - 페이지별 데이터에서 청크 생성

        각 페이지의 섹션과 테이블이 이미 동기화되어 있음

        Args:
            section_data: extract_section_advanced()의 반환값

        Returns:
            List[Dict]: 청크 정보 리스트 (chapter, section_name, sub_section, content, tables 포함)
        """
        search_keyword = section_data.get('chapter', 'Unknown')
        pages_data = section_data.get('pages_data', [])

        result = []
        global_chunk_idx = 0

        for page_info in pages_data:
            page_title = page_info.get('page_title', search_keyword)
            sections = page_info.get('sections', [])

            for parsed in sections:
                # 페이지 제목을 chapter로 사용 (실제 DART 페이지 제목)
                chapter = parsed.get('chapter', page_title)
                section_name = parsed.get('section', page_title)
                sub_section = parsed.get('sub_section')
                content = parsed.get('content', '')
                tables = parsed.get('tables', [])  # 이미 동기화된 테이블

                if not content or len(content.strip()) < CHUNK_CONFIG['min_chunk_size']:
                    continue

                # 콘텐츠가 청크 크기보다 크면 분할
                chunks = self.chunk_text(content)

                for idx, chunk in enumerate(chunks):
                    # 첫 번째 청크에만 해당 섹션의 테이블 연결
                    chunk_tables = tables if idx == 0 and tables else None

                    result.append({
                        "chapter": chapter,
                        "section_name": section_name,
                        "sub_section": sub_section,
                        "chunk_index": global_chunk_idx,
                        "content": chunk,
                        "tables": chunk_tables,
                        "metadata": {
                            "local_chunk_index": idx,
                            "total_local_chunks": len(chunks),
                            "has_tables": chunk_tables is not None and len(chunk_tables) > 0,
                            "table_count": len(chunk_tables) if chunk_tables else 0,
                            "page_title": page_title
                        }
                    })
                    global_chunk_idx += 1

        return result

    # ==================== 유틸리티 ====================

    def _clean_text(self, text: str) -> str:
        """텍스트 정제"""
        # 연속 공백/줄바꿈 정리
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)
        text = re.sub(r'\t+', ' ', text)

        # 불필요한 문자 제거
        text = text.replace('\xa0', ' ')
        text = text.replace('\r', '')

        return text.strip()

    def _parse_table(self, table_element) -> Optional[List[Dict]]:
        """HTML 테이블을 딕셔너리 리스트로 파싱"""
        try:
            rows = table_element.find_all('tr')
            if not rows:
                return None

            # 헤더 추출
            header_row = rows[0]
            headers = []
            for th in header_row.find_all(['th', 'td']):
                headers.append(th.get_text(strip=True))

            if not headers:
                return None

            # 데이터 행 추출
            data = []
            for row in rows[1:]:
                cells = row.find_all(['td', 'th'])
                if len(cells) == len(headers):
                    row_data = {}
                    for i, cell in enumerate(cells):
                        row_data[headers[i]] = cell.get_text(strip=True)
                    data.append(row_data)

            return data if data else None

        except Exception:
            return None

    # ==================== 순차적 블록 처리 (Sequential Block Processing) ====================

    def convert_table_to_markdown(self, table_element) -> Tuple[str, Dict]:
        """
        HTML 테이블을 Markdown 형식으로 변환

        Args:
            table_element: BeautifulSoup table 요소

        Returns:
            Tuple[str, Dict]: (Markdown 테이블 문자열, 메타데이터)
        """
        try:
            # pandas로 테이블 파싱
            html_str = str(table_element)
            dfs = pd.read_html(StringIO(html_str), flavor='bs4')

            if not dfs:
                return "", {}

            df = dfs[0]

            # NaN 처리
            df = df.fillna('')

            # 메타데이터 추출
            metadata = {
                "rows": len(df),
                "cols": len(df.columns),
                "columns": [str(col) for col in df.columns.tolist()]
            }

            # 테이블 제목 추출 시도 (caption 또는 첫 번째 행)
            caption = table_element.find('caption')
            if caption:
                metadata["title"] = caption.get_text(strip=True)

            # Markdown 테이블 생성
            markdown_lines = []

            # 헤더 행 - 셀 내용 정리
            headers = []
            for col in df.columns:
                header_text = str(col).replace("|", "｜").replace("\n", " ").strip()
                headers.append(header_text)

            markdown_lines.append("| " + " | ".join(headers) + " |")
            markdown_lines.append("|" + "|".join(["---"] * len(headers)) + "|")

            # 데이터 행
            for _, row in df.iterrows():
                cells = []
                for val in row:
                    cell_text = str(val).replace("|", "｜").replace("\n", " ").strip()
                    cells.append(cell_text)
                markdown_lines.append("| " + " | ".join(cells) + " |")

            return "\n".join(markdown_lines), metadata

        except Exception as e:
            # 파싱 실패 시 텍스트로 추출
            text = table_element.get_text(separator=' ', strip=True)
            return f"[표 데이터]\n{text}", {"error": str(e)}

    def extract_section_sequential(self, report, section_keyword: str) -> Optional[Dict]:
        """
        순차적 블록 처리 방식으로 섹션 추출

        HTML을 위에서 아래로 읽으며 만나는 순서대로 블록 수집

        Args:
            report: DART 보고서 객체
            section_keyword: 섹션 검색 키워드

        Returns:
            Dict: {"chapter": str, "blocks": list, "page_count": int}
        """
        try:
            result = report.find_all(includes=section_keyword)
            pages = result.get('pages', [])

            if not pages:
                return None

            all_blocks = []
            global_sequence = 0

            for page in pages:
                soup = BeautifulSoup(page.html, 'html.parser')
                page_title = getattr(page, 'title', section_keyword)

                # 현재 섹션 경로 초기화
                current_path = page_title

                # 페이지의 블록들을 순차적으로 처리
                blocks, global_sequence = self._parse_sequential_blocks(
                    soup.body if soup.body else soup,
                    current_path,
                    global_sequence
                )
                all_blocks.extend(blocks)

            return {
                "chapter": section_keyword,
                "blocks": all_blocks,
                "page_count": len(pages)
            }

        except Exception as e:
            print(f"⚠️ 순차적 섹션 추출 실패 ({section_keyword}): {e}")
            import traceback
            traceback.print_exc()
            return None

    def _parse_sequential_blocks(
        self,
        container,
        current_path: str,
        start_sequence: int
    ) -> Tuple[List[Dict], int]:
        """
        컨테이너 내의 요소들을 순차적으로 파싱

        Args:
            container: BeautifulSoup 요소 (body 또는 div)
            current_path: 현재 섹션 경로
            start_sequence: 시작 시퀀스 번호

        Returns:
            Tuple[List[Dict], int]: (블록 리스트, 다음 시퀀스 번호)
        """
        blocks = []
        sequence = start_sequence
        text_buffer = []  # 텍스트 누적 버퍼

        # 헤더 태그 패턴
        header_tags = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']

        def flush_text_buffer():
            """누적된 텍스트를 블록으로 저장"""
            nonlocal sequence
            if text_buffer:
                combined_text = '\n'.join(text_buffer).strip()
                combined_text = self._clean_text(combined_text)

                if len(combined_text) >= CHUNK_CONFIG['min_chunk_size']:
                    # 청크 크기가 크면 분할
                    chunks = self.chunk_text(combined_text)
                    for chunk in chunks:
                        blocks.append({
                            "chunk_type": "text",
                            "section_path": current_path,
                            "content": chunk,
                            "sequence_order": sequence,
                            "table_metadata": None
                        })
                        sequence += 1
                text_buffer.clear()

        def process_element(element):
            """단일 요소 처리"""
            nonlocal current_path, sequence

            if isinstance(element, NavigableString):
                text = str(element).strip()
                if text:
                    text_buffer.append(text)
                return

            if not isinstance(element, Tag):
                return

            tag_name = element.name

            # 1. 헤더 태그 -> 경로 업데이트
            if tag_name in header_tags:
                flush_text_buffer()
                header_text = element.get_text(strip=True)
                if header_text:
                    current_path = self._update_section_path(current_path, header_text, tag_name)
                return

            # 2. 테이블 -> 'table' 타입으로 저장
            if tag_name == 'table':
                flush_text_buffer()
                markdown_table, table_meta = self.convert_table_to_markdown(element)
                if markdown_table:
                    blocks.append({
                        "chunk_type": "table",
                        "section_path": current_path,
                        "content": markdown_table,
                        "sequence_order": sequence,
                        "table_metadata": table_meta
                    })
                    sequence += 1
                return

            # 3. 텍스트를 포함하는 블록 요소 (p, div, span 등)
            if tag_name in ['p', 'li', 'span', 'td', 'th']:
                text = element.get_text(strip=True)
                if text:
                    text_buffer.append(text)
                return

            # 4. 컨테이너 요소는 자식 순회
            if tag_name in ['div', 'section', 'article', 'body', 'tr', 'tbody', 'thead']:
                for child in element.children:
                    process_element(child)
                return

            # 5. 기타 태그는 텍스트 추출
            text = element.get_text(strip=True)
            if text:
                text_buffer.append(text)

        # 컨테이너의 직계 자식들 순회
        for child in container.children:
            process_element(child)

        # 남은 텍스트 버퍼 처리
        flush_text_buffer()

        return blocks, sequence

    def _update_section_path(self, current_path: str, header_text: str, tag_name: str) -> str:
        """
        헤더를 만났을 때 섹션 경로 업데이트

        Args:
            current_path: 현재 경로
            header_text: 헤더 텍스트
            tag_name: 헤더 태그명 (h1, h2, ...)

        Returns:
            str: 업데이트된 경로
        """
        # 헤더 레벨 추출 (h1=1, h2=2, ...)
        level = int(tag_name[1])

        # 경로를 ' > '로 분할
        path_parts = current_path.split(' > ') if current_path else []

        # 현재 레벨에 맞게 경로 조정
        # h1은 루트, h2는 첫 번째 하위, ...
        if level <= len(path_parts):
            path_parts = path_parts[:level-1]

        path_parts.append(header_text)

        return ' > '.join(path_parts)

    def extract_target_sections_sequential(self, report) -> List[Dict]:
        """
        핵심 섹션들을 순차적 블록 처리 방식으로 추출

        Returns:
            List[Dict]: 추출된 섹션 정보 리스트
        """
        extracted = []
        global_sequence = 0  # 전체 문서에서 연속되는 시퀀스 번호

        for section_name in TARGET_SECTIONS:
            section_data = self.extract_section_sequential(report, section_name)
            if section_data:
                # 시퀀스 번호를 전역적으로 재조정
                blocks = section_data.get('blocks', [])
                for block in blocks:
                    block['sequence_order'] = global_sequence
                    global_sequence += 1

                extracted.append(section_data)
                block_count = len(blocks)
                text_blocks = sum(1 for b in blocks if b['chunk_type'] == 'text')
                table_blocks = sum(1 for b in blocks if b['chunk_type'] == 'table')
                print(f"   ✅ '{section_name}' 추출 완료 "
                      f"({section_data['page_count']}페이지, {block_count}블록: 텍스트 {text_blocks}, 테이블 {table_blocks})")
            else:
                print(f"   ⚠️ '{section_name}' 섹션 없음")

        return extracted

