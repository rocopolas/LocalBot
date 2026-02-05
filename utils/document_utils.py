"""Document utilities for extracting text from PDFs and Office documents."""
import os
import asyncio
import logging

logger = logging.getLogger(__name__)


def _extract_text_from_pdf_sync(file_path: str) -> str:
    """Synchronous PDF text extraction."""
    try:
        import pymupdf  # PyMuPDF
        text_parts = []
        with pymupdf.open(file_path) as doc:
            for page in doc:
                text_parts.append(page.get_text())
        return "\n".join(text_parts).strip()
    except ImportError:
        return "[Error: pymupdf no instalado. Ejecuta: pip install pymupdf]"
    except Exception as e:
        return f"[Error leyendo PDF: {str(e)}]"


def _extract_text_from_docx_sync(file_path: str) -> str:
    """Synchronous DOCX text extraction."""
    try:
        from docx import Document
        doc = Document(file_path)
        text_parts = []
        for para in doc.paragraphs:
            text_parts.append(para.text)
        return "\n".join(text_parts).strip()
    except ImportError:
        return "[Error: python-docx no instalado. Ejecuta: pip install python-docx]"
    except Exception as e:
        return f"[Error leyendo DOCX: {str(e)}]"


def _extract_text_from_txt_sync(file_path: str) -> str:
    """Synchronous TXT text extraction."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception as e:
        return f"[Error leyendo archivo: {str(e)}]"


async def extract_text_from_pdf(file_path: str) -> str:
    """Extracts text from a PDF file (async wrapper)."""
    return await asyncio.to_thread(_extract_text_from_pdf_sync, file_path)


async def extract_text_from_docx(file_path: str) -> str:
    """Extracts text from a Word document (async wrapper)."""
    return await asyncio.to_thread(_extract_text_from_docx_sync, file_path)


async def extract_text_from_document(file_path: str, file_name: str) -> tuple[str, str]:
    """
    Extracts text from a document based on its extension.
    Runs extraction in thread pool to avoid blocking.
    
    Args:
        file_path: Path to the document file
        file_name: Original file name for type detection
        
    Returns:
        Tuple of (text, doc_type)
    """
    name_lower = file_name.lower()
    
    if name_lower.endswith(".pdf"):
        text = await extract_text_from_pdf(file_path)
        return text, "PDF"
    elif name_lower.endswith(".docx"):
        text = await extract_text_from_docx(file_path)
        return text, "Word"
    elif name_lower.endswith(".txt") or name_lower.endswith(".md"):
        text = await asyncio.to_thread(_extract_text_from_txt_sync, file_path)
        return text, "Texto"
    else:
        return "[Formato no soportado. Formatos válidos: PDF, DOCX, TXT, MD]", "Desconocido"


def is_supported_document(file_name: str) -> bool:
    """Check if the file is a supported document type."""
    name_lower = file_name.lower()
    return any(name_lower.endswith(ext) for ext in [".pdf", ".docx", ".txt", ".md"])
