"""
This is the only file in this project that was AI generated I didn't write it myself because Document Processors keep advancing at this time i found docling was the best so i just used it.
"""

import io
import logging
import re
from pathlib import Path
from typing import List, Dict, Optional

import fitz  # PyMuPDF
import numpy as np
from PIL import Image

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("document_processor")

# ---------------------------------------------------------------------------
# Optional heavy imports — guarded so the module still loads (and Docling-only
# mode still works) even if someone hasn't installed every fallback lib yet.
# ---------------------------------------------------------------------------

try:
    import cv2
    _HAS_CV2 = True
except ImportError:
    _HAS_CV2 = False
    logger.warning("opencv-python not installed — image preprocessing (deskew/denoise) disabled.")

try:
    import easyocr
    _HAS_EASYOCR = True
except ImportError:
    _HAS_EASYOCR = False
    logger.warning("easyocr not installed — standalone EasyOCR fallback (step 3) disabled.")

try:
    import pytesseract
    _HAS_TESSERACT = True
except ImportError:
    _HAS_TESSERACT = False
    logger.warning("pytesseract not installed — Tesseract fallback disabled.")

try:
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.pipeline_options import PdfPipelineOptions, EasyOcrOptions
    from docling.datamodel.base_models import InputFormat
    _HAS_DOCLING = True
except ImportError:
    _HAS_DOCLING = False
    logger.warning("docling not installed — primary conversion path disabled. Run: pip install docling")


# ---------------------------------------------------------------------------
# Config — tweak these for your corpus
# ---------------------------------------------------------------------------

OCR_LANGUAGES = ["en", "hi"]          # add Indic codes as needed: "mr", "ta", "te", "kn", "bn", ...
QUALITY_THRESHOLD = 0.45              # below this score we don't trust the output, we escalate
RENDER_DPI = 300                      # higher DPI helps OCR accuracy on small/blurry scans

_docling_converters: Dict[bool, "DocumentConverter"] = {}   # cache keyed by force_full_page_ocr
_easyocr_reader = None                                       # lazy singleton — model load is slow


# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------

def get_docling_converter(force_full_page_ocr: bool = False) -> "DocumentConverter":
    """Build (and cache) a Docling converter. force_full_page_ocr=True re-OCRs
    every page even if Docling thinks it already found a text layer — this
    fixes a common failure mode on scans with a garbage/hidden text layer."""
    if not _HAS_DOCLING:
        raise RuntimeError("docling is not installed. Run: pip install docling")

    if force_full_page_ocr in _docling_converters:
        return _docling_converters[force_full_page_ocr]

    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = True
    pipeline_options.do_table_structure = True
    pipeline_options.ocr_options = EasyOcrOptions(
        lang=OCR_LANGUAGES,
        force_full_page_ocr=force_full_page_ocr,
    )

    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
    )
    _docling_converters[force_full_page_ocr] = converter
    return converter


def get_easyocr_reader():
    """Lazy-load standalone EasyOCR reader (model download happens once)."""
    global _easyocr_reader
    if _easyocr_reader is None and _HAS_EASYOCR:
        logger.info("Loading EasyOCR model (first run downloads weights, may take a minute)...")
        _easyocr_reader = easyocr.Reader(OCR_LANGUAGES, gpu=False)
    return _easyocr_reader


# ---------------------------------------------------------------------------
# Quality scoring — decides whether to trust extracted text or escalate
# ---------------------------------------------------------------------------

def assess_text_quality(text: str) -> float:
    """
    Heuristic 0.0-1.0 quality score for extracted text.
    Catches the common OCR failure modes: near-empty output, mojibake,
    walls of symbols, garbled single-character noise.
    """
    if not text or not text.strip():
        return 0.0

    stripped = text.strip()
    total = len(stripped)

    alpha_ratio = sum(c.isalpha() or c.isspace() for c in stripped) / total

    words = re.findall(r"[A-Za-z\u0900-\u097F]+", stripped)  # latin + devanagari
    if not words:
        word_score = 0.0
    else:
        avg_word_len = sum(len(w) for w in words) / len(words)
        word_score = 1.0 if 2 <= avg_word_len <= 15 else 0.3  # real words rarely outside this range

    length_score = min(total / 200, 1.0)  # penalize suspiciously tiny output

    score = (alpha_ratio * 0.5) + (word_score * 0.3) + (length_score * 0.2)
    return round(min(max(score, 0.0), 1.0), 3)


# ---------------------------------------------------------------------------
# Image preprocessing (only used in the manual fallback path)
# ---------------------------------------------------------------------------

def _deskew(gray: np.ndarray) -> np.ndarray:
    if not _HAS_CV2:
        return gray
    coords = np.column_stack(np.where(gray < 250))
    if coords.shape[0] < 50:
        return gray
    angle = cv2.minAreaRect(coords)[-1]
    angle = -(90 + angle) if angle < -45 else -angle
    if abs(angle) < 0.1:
        return gray
    (h, w) = gray.shape
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    return cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def preprocess_image(pil_image: Image.Image) -> np.ndarray:
    """Grayscale -> denoise -> deskew -> adaptive threshold. Best-effort: never raises."""
    img = np.array(pil_image.convert("RGB"))
    if not _HAS_CV2:
        return img  # return as-is, OCR engines can still handle raw images

    try:
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        gray = cv2.fastNlMeansDenoising(gray, h=15)
        gray = _deskew(gray)
        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15
        )
        return thresh
    except Exception as e:
        logger.warning(f"Preprocessing step failed ({e}), using raw grayscale image instead.")
        return img


def render_pdf_page(pdf_path: str, page_num: int, dpi: int = RENDER_DPI) -> Image.Image:
    doc = fitz.open(pdf_path)
    page = doc[page_num]
    pix = page.get_pixmap(dpi=dpi)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    doc.close()
    return img


# ---------------------------------------------------------------------------
# Detection helper (handy if you want to route/skip work upstream, e.g. to
# decide whether to bother trying step 1 at all — optional, not required)
# ---------------------------------------------------------------------------

def is_scanned_pdf(pdf_path: str, sample_pages: int = 3, min_chars: int = 40) -> bool:
    """Cheap check: does the PDF already have a real text layer, or is it just images?"""
    try:
        doc = fitz.open(pdf_path)
        n = min(sample_pages, len(doc))
        if n == 0:
            return True
        avg_chars = sum(len(doc[i].get_text()) for i in range(n)) / n
        doc.close()
        return avg_chars < min_chars
    except Exception as e:
        logger.warning(f"Could not inspect {pdf_path} ({e}) — assuming scanned to be safe.")
        return True


# ---------------------------------------------------------------------------
# Fallback OCR engines (used only in the manual, page-by-page path)
# ---------------------------------------------------------------------------

def ocr_with_easyocr(image: np.ndarray) -> str:
    reader = get_easyocr_reader()
    if reader is None:
        raise RuntimeError("EasyOCR unavailable")
    results = reader.readtext(image, detail=1, paragraph=True)
    results.sort(key=lambda r: (r[0][0][1], r[0][0][0]))  # rough top-to-bottom, left-to-right
    return "\n".join(r[1] for r in results)


def ocr_with_tesseract(image: np.ndarray) -> str:
    if not _HAS_TESSERACT:
        raise RuntimeError("pytesseract unavailable")
    lang_map = {"en": "eng", "hi": "hin"}
    tess_langs = "+".join(lang_map.get(l, l) for l in OCR_LANGUAGES)
    return pytesseract.image_to_string(image, lang=tess_langs)


def manual_ocr_fallback(pdf_path: str) -> Dict:
    """
    Page-by-page render -> preprocess -> OCR (EasyOCR, then Tesseract as a
    second opinion). Used only when both Docling attempts fail the quality
    check. Never raises — returns whatever it could get, plus a warnings list.
    """
    doc = fitz.open(pdf_path)
    num_pages = len(doc)
    doc.close()

    page_texts = []
    warnings = []

    for i in range(num_pages):
        page_text = ""
        try:
            pil_img = render_pdf_page(pdf_path, i)
            processed = preprocess_image(pil_img)

            if _HAS_EASYOCR:
                try:
                    page_text = ocr_with_easyocr(processed)
                except Exception as e:
                    warnings.append(f"page {i+1}: EasyOCR failed ({e}), trying Tesseract")

            if assess_text_quality(page_text) < QUALITY_THRESHOLD and _HAS_TESSERACT:
                try:
                    tess_text = ocr_with_tesseract(processed)
                    if assess_text_quality(tess_text) > assess_text_quality(page_text):
                        page_text = tess_text
                except Exception as e:
                    warnings.append(f"page {i+1}: Tesseract failed ({e})")

            if not page_text.strip():
                warnings.append(f"page {i+1}: no OCR engine available or all failed — page is empty")

        except Exception as e:
            warnings.append(f"page {i+1}: render/preprocess failed ({e}) — page skipped")

        page_texts.append(f"## Page {i+1}\n\n{page_text.strip()}")

    markdown = "\n\n".join(page_texts)
    return {"markdown": markdown, "warnings": warnings, "num_pages": num_pages}


# ---------------------------------------------------------------------------
# Main per-file orchestration — the three-tier fallback chain
# ---------------------------------------------------------------------------

def convert_single_pdf(pdf_path: str) -> Dict:
    """
    Convert one PDF to markdown using the best available method, escalating
    through fallbacks as needed. Always returns a result dict — never raises.
    """
    path = Path(pdf_path)
    result = {
        "filename": path.name,
        "success": False,
        "markdown": "",
        "method": None,
        "quality_score": 0.0,
        "num_pages": None,
        "warnings": [],
        "error": None,
    }

    if not path.exists():
        result["error"] = "file not found"
        return result

    best_text, best_score, best_method = "", 0.0, None

    # --- Tier 1: Docling, standard OCR mode ---
    if _HAS_DOCLING:
        try:
            conv = get_docling_converter(force_full_page_ocr=False)
            doc = conv.convert(str(path)).document
            text = doc.export_to_markdown()
            score = assess_text_quality(text)
            result["num_pages"] = getattr(doc, "num_pages", None)
            logger.info(f"[{path.name}] Tier 1 (Docling standard) quality: {score}")
            if score > best_score:
                best_text, best_score, best_method = text, score, "docling_standard"
        except Exception as e:
            result["warnings"].append(f"Tier 1 (Docling standard) failed: {e}")
            logger.warning(f"[{path.name}] Tier 1 failed: {e}")

    # --- Tier 2: Docling, forced full-page OCR (only if tier 1 wasn't good enough) ---
    if best_score < QUALITY_THRESHOLD and _HAS_DOCLING:
        try:
            conv = get_docling_converter(force_full_page_ocr=True)
            doc = conv.convert(str(path)).document
            text = doc.export_to_markdown()
            score = assess_text_quality(text)
            result["num_pages"] = result["num_pages"] or getattr(doc, "num_pages", None)
            logger.info(f"[{path.name}] Tier 2 (Docling forced OCR) quality: {score}")
            if score > best_score:
                best_text, best_score, best_method = text, score, "docling_forced_ocr"
        except Exception as e:
            result["warnings"].append(f"Tier 2 (Docling forced OCR) failed: {e}")
            logger.warning(f"[{path.name}] Tier 2 failed: {e}")

    # --- Tier 3: manual page-by-page OCR (only if tiers 1-2 still weren't good enough) ---
    if best_score < QUALITY_THRESHOLD:
        logger.info(f"[{path.name}] Docling tiers below threshold — running manual OCR fallback.")
        try:
            fallback = manual_ocr_fallback(str(path))
            score = assess_text_quality(fallback["markdown"])
            result["warnings"].extend(fallback["warnings"])
            result["num_pages"] = result["num_pages"] or fallback["num_pages"]
            logger.info(f"[{path.name}] Tier 3 (manual OCR) quality: {score}")
            if score > best_score:
                best_text, best_score, best_method = fallback["markdown"], score, "manual_ocr_fallback"
        except Exception as e:
            result["warnings"].append(f"Tier 3 (manual OCR) crashed: {e}")
            logger.error(f"[{path.name}] Tier 3 crashed: {e}")

    # --- Final decision ---
    if best_text.strip():
        result.update({
            "success": True,
            "markdown": best_text,
            "method": best_method if best_score >= QUALITY_THRESHOLD else f"{best_method} (low confidence)",
            "quality_score": best_score,
        })
    else:
        result["error"] = "all extraction methods failed or produced empty/garbage output"

    return result


# ---------------------------------------------------------------------------
# Batch entry point — this is what you call from main.py
# ---------------------------------------------------------------------------

def process_uploaded_files(file_paths: List[str]) -> List[Dict]:
    """
    Process a list of uploaded PDF paths. One bad file never stops the batch —
    every file gets its own try/except and its own result entry.
    """
    results = []

    for fp in file_paths:
        logger.info(f"Processing: {fp}")
        try:
            r = convert_single_pdf(fp)
        except Exception as e:
            # absolute last-resort catch — should basically never hit this
            logger.error(f"Unexpected top-level failure on {fp}: {e}")
            r = {
                "filename": Path(fp).name,
                "success": False,
                "markdown": "",
                "method": None,
                "quality_score": 0.0,
                "num_pages": None,
                "warnings": [],
                "error": str(e),
            }
        results.append(r)

    ok = sum(1 for r in results if r["success"])
    logger.info(f"Batch complete: {ok}/{len(results)} files processed successfully.")
    return results