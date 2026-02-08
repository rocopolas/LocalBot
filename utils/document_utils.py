"""Document utilities for extracting text from PDFs and Office documents."""
import os
import asyncio
import logging

logger = logging.getLogger(__name__)


def _extract_text_from_pdf_sync(file_path: str) -> tuple[str, int]:
    """Synchronous PDF text extraction. Returns (text, page_count)."""
    try:
        import pymupdf  # PyMuPDF
        text_parts = []
        page_count = 0
        with pymupdf.open(file_path) as doc:
            page_count = len(doc)
            for page in doc:
                text_parts.append(page.get_text())
        return "\n".join(text_parts).strip(), page_count
    except ImportError:
        return "[Error: pymupdf no instalado. Ejecuta: pip install pymupdf]", 0
    except Exception as e:
        return f"[Error leyendo PDF: {str(e)}]", 0


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


async def extract_text_from_pdf(file_path: str) -> tuple[str, int]:
    """Extracts text from a PDF file (async wrapper). Returns (text, page_count)."""
    return await asyncio.to_thread(_extract_text_from_pdf_sync, file_path)


async def extract_text_from_docx(file_path: str) -> str:
    """Extracts text from a Word document (async wrapper)."""
    return await asyncio.to_thread(_extract_text_from_docx_sync, file_path)





def convert_pdf_to_images(file_path: str, max_pages: int = None) -> list[str]:
    """
    Convert PDF pages to base64 encoded images.
    
    Args:
        file_path: Path to PDF file
        max_pages: Maximum number of pages to convert. None for all (warning: slow).
        
    Returns:
        List of base64 strings
    """
    import base64
    try:
        import pymupdf
        images_b64 = []
        with pymupdf.open(file_path) as doc:
            for i, page in enumerate(doc):
                if max_pages and i >= max_pages:
                    break
                
                # Render page to image
                pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))  # 2x zoom for better OCR
                img_bytes = pix.tobytes("png")
                
                # Convert to base64
                img_b64 = base64.b64encode(img_bytes).decode("utf-8")
                images_b64.append(img_b64)
                
        return images_b64
    except Exception as e:
        logger.error(f"Error converting PDF to images: {e}")
        return []


async def extract_text_from_document(file_path: str, file_name: str) -> tuple[str, str, bool]:
    """
    Extracts text from a document based on its extension.
    
    Args:
        file_path: Path to the document file
        file_name: Original file name for type detection
        
    Returns:
        Tuple of (text, doc_type, needs_ocr)
    """
    name_lower = file_name.lower()
    
    if name_lower.endswith(".pdf"):
        text, page_count = await extract_text_from_pdf(file_path)
        
        # Check for scanned document (low text density)
        # Threshold: < 15 words per page average
        needs_ocr = False
        if page_count > 0:
            word_count = len(text.split())
            avg_words = word_count / page_count
            if avg_words < 15:
                needs_ocr = True
                logger.info(f"Low text density detected ({avg_words:.1f} words/page). Triggering OCR.")
        
        return text, "PDF", needs_ocr
        
    elif name_lower.endswith(".docx"):
        text = await extract_text_from_docx(file_path)
        return text, "Word", False
        
    elif name_lower.endswith(".txt") or name_lower.endswith(".md"):
        text = await asyncio.to_thread(_extract_text_from_txt_sync, file_path)
        return text, "Texto", False
        
    else:
        return "[Formato no soportado]", "Desconocido", False


def is_supported_document(file_name: str) -> bool:
    """Check if the file is a supported document type."""
    name_lower = file_name.lower()
    return any(name_lower.endswith(ext) for ext in [".pdf", ".docx", ".txt", ".md"])
