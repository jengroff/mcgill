"""PDF extraction service — structured text from PDF bytes."""

from __future__ import annotations

import re


class PDFExtractor:
    def extract_text(self, pdf_bytes: bytes) -> str:
        """Extract raw text from PDF. Uses pymupdf, falls back to pdfplumber."""
        text = self._extract_with_pymupdf(pdf_bytes)
        if len(text.strip()) < 100:
            text = self._extract_with_pdfplumber(pdf_bytes)
        return text

    def extract_structured(self, pdf_bytes: bytes) -> dict:
        """Extract structured sections from PDF.

        Returns {"title": str, "sections": [{"heading": str, "text": str}]}
        """
        text = self.extract_text(pdf_bytes)
        lines = text.split("\n")

        title = ""
        sections: list[dict] = []
        current_heading = "Introduction"
        current_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Heuristic: ALL CAPS line or short bold-like line = heading
            if self._is_heading(stripped):
                if not title:
                    title = stripped
                else:
                    if current_lines:
                        sections.append(
                            {
                                "heading": current_heading,
                                "text": "\n".join(current_lines),
                            }
                        )
                        current_lines = []
                    current_heading = stripped
            else:
                current_lines.append(stripped)

        # Flush last section
        if current_lines:
            sections.append(
                {
                    "heading": current_heading,
                    "text": "\n".join(current_lines),
                }
            )

        return {"title": title, "sections": sections}

    def _is_heading(self, line: str) -> bool:
        """Detect heading lines using heuristics."""
        # ALL CAPS, at least 3 chars, no period at end
        if (
            len(line) >= 3
            and line == line.upper()
            and not line.endswith(".")
            and re.match(r"^[A-Z\s\-:&/]+$", line)
        ):
            return True
        # Short line (< 80 chars) that looks like a title
        if (
            len(line) < 80
            and line[0].isupper()
            and not line.endswith(".")
            and line.count(" ") < 10
        ):
            return False  # Too ambiguous — only trust ALL CAPS
        return False

    def _extract_with_pymupdf(self, pdf_bytes: bytes) -> str:
        import pymupdf

        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        text_parts = []
        for page in doc:  # type: ignore[attr-defined]
            text_parts.append(page.get_text())
        doc.close()
        return "\n".join(text_parts)

    def _extract_with_pdfplumber(self, pdf_bytes: bytes) -> str:
        import io
        import pdfplumber

        text_parts = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
        return "\n".join(text_parts)
