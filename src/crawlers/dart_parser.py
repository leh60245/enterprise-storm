"""
DART Report Parser (Crawler Layer)

Role:
- Fetch corporate info via DART API
- Download annual reports
- Parse HTML content into structured chunks (Text/Table)
- Returns raw data (List[Dict]) for IngestionService

Path: src/crawlers/dart_parser.py
"""

import logging
import re
from datetime import datetime, timedelta
from io import StringIO
from typing import Any

import dart_fss as dart
import pandas as pd
from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString

from src.common.config import CHUNK_CONFIG, DART_CONFIG, TARGET_SECTIONS

logger = logging.getLogger(__name__)

# Config Defaults
DART_API_KEY = DART_CONFIG.get("api_key")
REPORT_SEARCH_CONFIG = {
    "bgn_de": DART_CONFIG.get("search_start_date", (datetime.now() - timedelta(days=90)).strftime("%Y%m%d")),
    "pblntf_detail_ty": DART_CONFIG.get("report_type_code", "a001"),
    "page_count": DART_CONFIG.get("page_count", 100),
    "page_delay_sec": DART_CONFIG.get("page_delay_sec", 0.5),
    "max_search_days": DART_CONFIG.get("max_search_days", 90),
}

class DartReportParser:
    """
    Handles DART API interactions and HTML parsing.
    Output: Structured list of dictionaries (ready for ingestion).
    """

    def __init__(self):
        """Initialize DART API connection."""
        if not DART_API_KEY:
            logger.warning("⚠️ DART_API_KEY is missing in configuration.")
        else:
            dart.set_api_key(api_key=DART_API_KEY)

        self._corp_list = None

    @property
    def corp_list(self):
        """Lazy load corporation list."""
        if self._corp_list is None:
            logger.info("🔄 Loading DART Corp List...")
            try:
                self._corp_list = dart.get_corp_list()
                logger.info(f"✅ Loaded {len(self._corp_list)} corporations.")
            except Exception as e:
                logger.error(f"Failed to load corp list: {e}")
                self._corp_list = []
        return self._corp_list

    # ==================== 1. Fetching Logic (DART API) ====================

    def get_corp_code_by_name(self, name: str) -> str | None:
        """Find corporation code by name."""
        try:
            # find_by_corp_name returns a list, take the first one
            corps = self.corp_list.find_by_corp_name(name, exactly=True)
            if corps:
                return corps[0].corp_code
        except Exception:
            pass
        return None

    def search_reports(
        self,
        corp_code: str,
        bgn_de: str = None,
        end_de: str = None
    ) -> list[Any]:
        """Search for reports within a date range."""
        if not bgn_de:
            bgn_de = REPORT_SEARCH_CONFIG["bgn_de"]
        if not end_de:
            end_de = datetime.now().strftime("%Y%m%d")

        logger.info(f"📋 Searching DART reports for {corp_code} ({bgn_de}~{end_de})")

        try:
            results = dart.search(
                corp_code=corp_code,
                bgn_de=bgn_de,
                end_de=end_de,
                pblntf_detail_ty=REPORT_SEARCH_CONFIG["pblntf_detail_ty"]
            )
            return results if results else []
        except Exception as e:
            logger.error(f"Failed to search reports: {e}")
            return []

    def get_report_meta(self, report) -> dict[str, Any]:
        """Extract metadata for DB storage."""
        return {
            "title": report.report_nm,
            "rcept_no": report.rcept_no,
            "rcept_dt": report.rcept_dt,
            "corp_code": report.corp_code,
            "corp_name": report.corp_name,
            "report_type": "annual",
        }

    # ==================== 2. Parsing Logic (Sequential Block) ====================

    def parse_report(self, report) -> list[dict[str, Any]]:
        """
        Main Parsing Method: Extracts text and tables sequentially.
        """
        extracted_chunks = []
        global_sequence = 0

        # DART FSS library downloads HTML on demand here
        for section_name in TARGET_SECTIONS:
            logger.debug(f"   Scanning section: {section_name}...")
            section_data = self._extract_section_content(report, section_name)

            if section_data:
                blocks = section_data.get("blocks", [])
                for block in blocks:
                    # Assign global sequence order across sections
                    block["sequence_order"] = global_sequence
                    global_sequence += 1

                    # Add to final list (Flattened structure)
                    extracted_chunks.append(block)

                logger.info(f"   ✅ Parsed '{section_name}': {len(blocks)} blocks")

        return extracted_chunks

    def _extract_section_content(self, report, section_keyword: str) -> dict | None:
        try:
            # dart-fss specific method to find sub-pages
            result = report.find_all(includes=section_keyword)
            pages = result.get("pages", [])
            if not pages:
                return None

            all_blocks = []
            for page in pages:
                soup = BeautifulSoup(page.html, "html.parser")
                page_title = getattr(page, "title", section_keyword)

                # Recursive parsing starting from body
                blocks = self._parse_dom_tree(
                    soup.body if soup.body else soup,
                    current_path=page_title,
                    start_sequence=0 # Will be re-indexed later
                )
                all_blocks.extend(blocks)

            return {"blocks": all_blocks}
        except Exception as e:
            logger.warning(f"Parsing skipped for '{section_keyword}': {e}")
            return None

    def _parse_dom_tree(
        self, container, current_path: str, start_sequence: int
    ) -> list[dict]:
        """Traverse DOM tree to extract chunks."""
        blocks = []
        sequence = start_sequence
        text_buffer = []
        header_tags = ["h1", "h2", "h3", "h4", "h5", "h6"]

        def flush_buffer():
            nonlocal sequence
            if not text_buffer: return 

            combined = self._clean_text("\n".join(text_buffer))
            if len(combined) >= CHUNK_CONFIG["min_chunk_size"]:
                chunks = self._chunk_text_algorithm(combined)
                for c in chunks:
                    blocks.append({
                        "chunk_type": "text",
                        "section_path": current_path,
                        "content": c,
                        "raw_content": c,
                        "sequence_order": sequence, # Local seq
                        "table_metadata": None
                    })
                    sequence += 1
            text_buffer.clear()

        def visit(element):
            nonlocal current_path, sequence

            if isinstance(element, NavigableString):
                text = str(element).strip()
                if text: text_buffer.append(text)
                return

            if not isinstance(element, Tag): return
            tag = element.name

            # Case 1: Header -> Flush & Update Path
            if tag in header_tags:
                flush_buffer()
                header_text = element.get_text(strip=True)
                if header_text:
                    current_path = self._update_path_string(current_path, header_text, tag)
                return

            # Case 2: Table -> Flush & Convert
            if tag == "table":
                flush_buffer()
                md, meta = self._table_to_markdown(element)
                if md:
                    blocks.append({
                        "chunk_type": "table",
                        "section_path": current_path,
                        "content": md,
                        "raw_content": md,
                        "sequence_order": sequence,
                        "table_metadata": meta
                    })
                    sequence += 1
                return

            # Case 3: Recursion
            # Traverse children for container tags
            if tag in ["div", "section", "article", "body", "tr", "tbody", "thead", "p", "li", "span"]:
                for child in element.children:
                    visit(child)
                return

            # Fallback for other tags
            t = element.get_text(strip=True)
            if t: text_buffer.append(t)

        for child in container.children:
            visit(child)

        flush_buffer()
        return blocks

    # ==================== Helpers ====================

    def _update_path_string(self, current: str, header: str, tag: str) -> str:
        level = int(tag[1]) # h1 -> 1
        parts = current.split(" > ") if current else []
        if level <= len(parts):
            parts = parts[:level-1]
        parts.append(header)
        return " > ".join(parts)

    def _clean_text(self, text: str) -> str:
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)
        return text.replace("\xa0", " ").strip()

    def _chunk_text_algorithm(self, text: str) -> list[str]:
        chunk_size = CHUNK_CONFIG["max_chunk_size"]
        overlap = CHUNK_CONFIG["overlap"]
        min_size = CHUNK_CONFIG["min_chunk_size"]

        if len(text) <= chunk_size:
            return [text] if len(text) >= min_size else []

        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            if end < len(text):
                # Try to break at logical separators
                for sep in ["\n\n", "\n", ". "]:
                    idx = text[start:end].rfind(sep)
                    if idx > chunk_size // 2:
                        end = start + idx + len(sep)
                        break

            chunk = text[start:end].strip()
            if len(chunk) >= min_size:
                chunks.append(chunk)
            elif chunks:
                chunks[-1] += " " + chunk # Merge if too small

            start = end - overlap
        return chunks

    def _table_to_markdown(self, table_tag) -> tuple[str, dict]:
        try:
            dfs = pd.read_html(StringIO(str(table_tag)), flavor="bs4")
            if not dfs: return "", {}
            df = dfs[0].fillna("")

            meta = {
                "rows": len(df),
                "cols": len(df.columns),
                "columns": [str(c) for c in df.columns]
            }
            return df.to_markdown(index=False), meta
        except Exception:
            return "", {}
