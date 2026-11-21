"""Extract selectable text from PDF bytes using PyMuPDF."""

from dataclasses import dataclass

import fitz


class PDFExtractionError(ValueError):
    """Raised when a PDF is invalid, too large, or has no selectable text."""


@dataclass
class ExtractedPage:
    page_number: int
    text: str


def extract_pdf_text(
    pdf_bytes: bytes, *, max_bytes: int = 10 * 1024 * 1024, max_pages: int = 5
) -> list[ExtractedPage]:
    """Return non-empty page text. Scanned PDFs require OCR and are unsupported."""
    if not pdf_bytes:
        raise PDFExtractionError("The uploaded PDF is empty.")
    if len(pdf_bytes) > max_bytes:
        raise PDFExtractionError("The PDF exceeds the 10 MB size limit.")
    if not pdf_bytes.startswith(b"%PDF-"):
        raise PDFExtractionError("The uploaded file is not a valid PDF.")

    try:
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise PDFExtractionError("The PDF could not be opened.") from exc

    try:
        if document.page_count == 0:
            raise PDFExtractionError("The PDF contains no pages.")
        if document.page_count > max_pages:
            raise PDFExtractionError("The PDF exceeds the 5 page limit.")

        pages = [
            ExtractedPage(page_number=index + 1, text=page.get_text("text").strip())
            for index, page in enumerate(document)
        ]
    finally:
        document.close()

    if not any(page.text for page in pages):
        raise PDFExtractionError(
            "No selectable text was found. Scanned or image-only PDFs are not supported."
        )
    return pages
