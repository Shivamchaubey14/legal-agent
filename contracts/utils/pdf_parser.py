import os
import fitz          # PyMuPDF
import pdfplumber
import pytesseract
from PIL import Image
from docx import Document
import io
import logging

logger = logging.getLogger(__name__)

# ── Tesseract path (Windows) ─────────────────────────────────
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


class ContractParser:
    """
    Parses PDF and DOCX contracts into clean text.
    Strategy:
      1. Try PyMuPDF (fast, text-based PDFs)
      2. Fall back to pdfplumber
      3. Fall back to Tesseract OCR (scanned PDFs)
    """

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.ext       = os.path.splitext(file_path)[1].lower()

    def parse(self) -> dict:
        """
        Returns:
            {
                'text':       str,   # full extracted text
                'page_count': int,
                'method':     str,   # 'pymupdf' | 'pdfplumber' | 'ocr' | 'docx'
                'error':      str | None
            }
        """
        try:
            if self.ext == '.docx':
                return self._parse_docx()
            elif self.ext == '.pdf':
                return self._parse_pdf()
            else:
                return self._error(f'Unsupported file type: {self.ext}')
        except Exception as e:
            logger.error(f'ContractParser error for {self.file_path}: {e}')
            return self._error(str(e))

    # ── PDF ──────────────────────────────────────────────────
    def _parse_pdf(self) -> dict:
        # Step 1: PyMuPDF
        result = self._try_pymupdf()
        if result and self._is_usable(result['text']):
            return result

        # Step 2: pdfplumber
        result = self._try_pdfplumber()
        if result and self._is_usable(result['text']):
            return result

        # Step 3: OCR fallback
        return self._try_ocr()

    def _try_pymupdf(self) -> dict | None:
        try:
            doc        = fitz.open(self.file_path)
            pages      = []
            page_count = len(doc)

            for page in doc:
                text = page.get_text('text')
                pages.append(text)

            doc.close()
            full_text = '\n\n'.join(pages).strip()

            return {
                'text':       full_text,
                'page_count': page_count,
                'method':     'pymupdf',
                'error':      None,
            }
        except Exception as e:
            logger.warning(f'PyMuPDF failed: {e}')
            return None

    def _try_pdfplumber(self) -> dict | None:
        try:
            pages = []
            with pdfplumber.open(self.file_path) as pdf:
                page_count = len(pdf.pages)
                for page in pdf.pages:
                    text = page.extract_text() or ''
                    pages.append(text)

            full_text = '\n\n'.join(pages).strip()
            return {
                'text':       full_text,
                'page_count': page_count,
                'method':     'pdfplumber',
                'error':      None,
            }
        except Exception as e:
            logger.warning(f'pdfplumber failed: {e}')
            return None

    def _try_ocr(self) -> dict:
        try:
            doc        = fitz.open(self.file_path)
            page_count = len(doc)
            pages      = []

            for page_num, page in enumerate(doc):
                # Render page to image at 300 DPI
                mat  = fitz.Matrix(300 / 72, 300 / 72)
                pix  = page.get_pixmap(matrix=mat)
                img  = Image.open(io.BytesIO(pix.tobytes('png')))

                # OCR the image
                text = pytesseract.image_to_string(img, lang='eng')
                pages.append(text)
                logger.info(f'OCR page {page_num + 1}/{page_count}')

            doc.close()
            full_text = '\n\n'.join(pages).strip()

            return {
                'text':       full_text,
                'page_count': page_count,
                'method':     'ocr',
                'error':      None,
            }
        except Exception as e:
            logger.error(f'OCR failed: {e}')
            return self._error(f'OCR failed: {e}')

    # ── DOCX ─────────────────────────────────────────────────
    def _parse_docx(self) -> dict:
        try:
            doc        = Document(self.file_path)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]

            # Also extract text from tables
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        if cell.text.strip():
                            paragraphs.append(cell.text.strip())

            full_text  = '\n\n'.join(paragraphs).strip()
            page_count = max(1, len(full_text) // 3000)  # Estimate

            return {
                'text':       full_text,
                'page_count': page_count,
                'method':     'docx',
                'error':      None,
            }
        except Exception as e:
            logger.error(f'DOCX parsing failed: {e}')
            return self._error(str(e))

    # ── Helpers ──────────────────────────────────────────────
    @staticmethod
    def _is_usable(text: str, min_chars: int = 100) -> bool:
        """Check if extracted text is actually useful."""
        if not text:
            return False
        clean = text.replace('\n', '').replace(' ', '')
        return len(clean) >= min_chars

    @staticmethod
    def _error(msg: str) -> dict:
        return {
            'text':       '',
            'page_count': 0,
            'method':     'failed',
            'error':      msg,
        }


def parse_contract_file(file_path: str) -> dict:
    """Convenience function — call this from views/tasks."""
    parser = ContractParser(file_path)
    return parser.parse()  