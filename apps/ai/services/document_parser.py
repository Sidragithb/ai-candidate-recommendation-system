from io import BytesIO
from pathlib import Path

from docx import Document
from pypdf import PdfReader


class DocumentParserService:
    def extract_text(self, filename: str, content: bytes) -> str:
        suffix = Path(filename).suffix.lower()
        if suffix == ".pdf":
            return self._extract_pdf_text(content)
        if suffix == ".docx":
            return self._extract_docx_text(content)
        return content.decode("utf-8", errors="ignore").strip()

    def _extract_pdf_text(self, content: bytes) -> str:
        reader = PdfReader(BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(page.strip() for page in pages if page.strip())

    def _extract_docx_text(self, content: bytes) -> str:
        document = Document(BytesIO(content))
        paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
        return "\n".join(paragraphs)
