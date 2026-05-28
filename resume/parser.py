"""Resume parser — extracts raw text from PDF (PyMuPDF) and DOCX (python-docx)."""

from pathlib import Path
from typing import Optional
import fitz  # PyMuPDF

from utils.logger import logger


def parse_pdf(path: str) -> str:
    """Extract raw text from a PDF file using PyMuPDF."""
    doc: Optional[fitz.Document] = None
    try:
        doc = fitz.open(path)
        pages_text = [page.get_text() for page in doc]
        text = "".join(pages_text).strip()
        logger.info(f"ResumeParser PDF parsed: {len(text)} chars from {path}")
        return text
    except FileNotFoundError:
        logger.warning(f"ResumeParser PDF not found: {path}")
        return ""
    except Exception as e:
        logger.error(f"ResumeParser PDF parse error ({path}): {e}")
        return ""
    finally:
        if doc:
            doc.close()


def parse_docx(path: str) -> str:
    """Extract raw text from a DOCX file using python-docx."""
    try:
        from docx import Document
        doc = Document(path)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        text = "\n".join(paragraphs).strip()
        logger.info(f"ResumeParser DOCX parsed: {len(text)} chars from {path}")
        return text
    except FileNotFoundError:
        logger.warning(f"ResumeParser DOCX not found: {path}")
        return ""
    except Exception as e:
        logger.error(f"ResumeParser DOCX parse error ({path}): {e}")
        return ""


def get_resume_text(pdf_path: str, docx_path: str) -> str:
    """Get resume text, trying PDF first then DOCX as fallback.

    Raises:
        FileNotFoundError: If neither PDF nor DOCX files contain usable text.
    """
    if Path(pdf_path).exists():
        text = parse_pdf(pdf_path)
        if text:
            return text
        logger.warning(f"ResumeParser PDF exists but returned empty text: {pdf_path}")

    if Path(docx_path).exists():
        text = parse_docx(docx_path)
        if text:
            return text
        logger.warning(f"ResumeParser DOCX exists but returned empty text: {docx_path}")

    raise FileNotFoundError(
        f"No resume found or both files returned empty text.\n"
        f"  PDF path:  {pdf_path}\n"
        f"  DOCX path: {docx_path}\n"
        f"  Fix: Place resume.pdf or resume.docx in the resume/uploads/ folder."
    )
