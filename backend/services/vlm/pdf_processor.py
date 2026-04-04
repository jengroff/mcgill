"""PDF processor with VLM support for McGill course guides."""

from __future__ import annotations

import logging
from typing import Any

from backend.services.vlm.claude_vision import ClaudeVisionAnalyzer
from backend.services.vlm.page_analyzer import PageAnalyzer
from backend.services.vlm.types import PageContent

logger = logging.getLogger(__name__)

VLM_CONFIDENCE_THRESHOLD = 0.3


class PDFProcessor:
    def __init__(self, pdf_bytes: bytes, file_name: str, use_vlm: bool = True):
        self.pdf_bytes = pdf_bytes
        self.file_name = file_name
        self.use_vlm = use_vlm

    def process(self) -> list[PageContent]:
        if self.use_vlm:
            return self._process_with_vlm()
        raw_pages = self._extract_pages()
        return self._analyze_pages(raw_pages)

    def _render_pages_to_images(self) -> list[tuple[int, bytes, str]]:
        import pymupdf

        _MAX_BYTES = 5 * 1024 * 1024

        doc = pymupdf.open(stream=self.pdf_bytes, filetype="pdf")
        results: list[tuple[int, bytes, str]] = []
        for page_index in range(len(doc)):
            page = doc[page_index]
            pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))
            image_bytes = pix.tobytes("png")
            media_type = "image/png"
            if len(image_bytes) > _MAX_BYTES:
                image_bytes = pix.tobytes("jpeg", jpg_quality=85)
                media_type = "image/jpeg"
            if len(image_bytes) > _MAX_BYTES:
                pix = page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5))
                image_bytes = pix.tobytes("jpeg", jpg_quality=80)
            results.append((page_index + 1, image_bytes, media_type))
        doc.close()
        return results

    def _process_with_vlm(self) -> list[PageContent]:
        try:
            page_images = self._render_pages_to_images()
            total = len(page_images)
            logger.info(
                "Rendering %d pages from %s with Claude Vision", total, self.file_name
            )
            analyzer = ClaudeVisionAnalyzer()
            pages: list[PageContent] = []
            for page_num, image_bytes, media_type in page_images:
                logger.info("Analyzing page %d/%d", page_num, total)
                page = analyzer.analyze_page_image(image_bytes, page_num, media_type)
                if page["confidence"] < VLM_CONFIDENCE_THRESHOLD:
                    logger.warning(
                        "Low confidence (%.2f) on page %d",
                        page["confidence"],
                        page_num,
                    )
                pages.append(page)
            logger.info("VLM complete — %d pages processed", total)
            return pages
        except Exception:
            logger.exception("VLM processing failed, falling back to text extraction")
            raw_pages = self._extract_pages()
            return self._analyze_pages(raw_pages)

    def _extract_pages(self) -> list[dict[str, Any]]:
        try:
            import pymupdf

            doc = pymupdf.open(stream=self.pdf_bytes, filetype="pdf")
            pages = []
            for i, page in enumerate(doc):
                pages.append(
                    {
                        "page_number": i + 1,
                        "text": page.get_text(),
                        "tables": [],
                    }
                )
            doc.close()
            return pages
        except Exception:
            logger.warning("PyMuPDF unavailable, falling back to pdfplumber")
            return self._extract_pages_pdfplumber()

    def _extract_pages_pdfplumber(self) -> list[dict[str, Any]]:
        import io
        import pdfplumber

        pages = []
        with pdfplumber.open(io.BytesIO(self.pdf_bytes)) as pdf:
            for i, page in enumerate(pdf.pages):
                pages.append(
                    {
                        "page_number": i + 1,
                        "text": page.extract_text() or "",
                        "tables": [],
                    }
                )
        return pages

    def _analyze_pages(self, raw_pages: list[dict]) -> list[PageContent]:
        analyzer = PageAnalyzer()
        return [analyzer.analyze(p) for p in raw_pages]
