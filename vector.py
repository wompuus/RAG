import io
import os
import re
import shutil
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Optional OCR
try:
    import pytesseract
except ImportError:
    pytesseract = None


# ----------------------------
# Paths / Config
# ----------------------------
BASE_DIR = Path(__file__).resolve().parent
DB_DIR = BASE_DIR / "chroma_langchain_db"
MANUALS_DIR = BASE_DIR / "Manuals"

EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "mxbai-embed-large")
FORCE_REINDEX = os.getenv("FORCE_REINDEX", "0") == "1"


# ----------------------------
# OCR helpers
# ----------------------------
def configure_tesseract():
    if pytesseract is None:
        return

    possible_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]

    env_path = os.getenv("TESSERACT_CMD")
    if env_path:
        possible_paths.insert(0, env_path)

    for path in possible_paths:
        if path and Path(path).exists():
            pytesseract.pytesseract.tesseract_cmd = path
            return


def ocr_page(page):
    if pytesseract is None:
        return ""

    try:
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))
        return pytesseract.image_to_string(img).strip()
    except Exception:
        return ""


# ----------------------------
# Parsing helpers
# ----------------------------
def detect_section(text, current_section):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    top = " ".join(lines[:12]).upper()

    keywords = [
        "TROUBLESHOOTING",
        "ALARMS",
        "SETUP",
        "INSTALLATION",
        "MAINTENANCE",
        "GENERAL DESCRIPTION",
        "SCREEN DESCRIPTIONS",
        "SAFETY",
        "THEORY OF OPERATION",
    ]

    for kw in keywords:
        if kw in top:
            return kw.title()

    return current_section


def extract_display_page(text, fallback_num):
    candidates = []

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    candidates.extend(lines[:15])
    candidates.extend(lines[-15:])

    joined = "\n".join(candidates)

    patterns = [
        r"\bPage\s+([A-Za-z0-9-]+)\b",
        r"\bPg\.?\s*([A-Za-z0-9-]+)\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, joined, flags=re.IGNORECASE)
        if match:
            return match.group(1)

    return str(fallback_num)


def get_pdf_files():
    pdfs = []

    if MANUALS_DIR.exists():
        pdfs.extend(sorted(MANUALS_DIR.glob("*.pdf")))

    # Fallback: also allow PDFs in the same directory as the script
    pdfs.extend(sorted(BASE_DIR.glob("*.pdf")))

    # De-dupe by resolved path
    deduped = []
    seen = set()
    for pdf in pdfs:
        resolved = str(pdf.resolve())
        if resolved not in seen:
            seen.add(resolved)
            deduped.append(pdf)

    return deduped


def build_documents_from_pdf(pdf_path: Path, text_splitter):
    documents = []
    ids = []

    doc = fitz.open(pdf_path)
    manual_name = pdf_path.stem
    current_section = "Unknown"

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)

        text = page.get_text("text")

        # OCR fallback only for pages with little/no extractable text
        if len(text.strip()) < 100:
            ocr_text = ocr_page(page)
            if ocr_text:
                text = f"{text}\n\nOCR Text:\n{ocr_text}".strip()

        if not text.strip():
            continue

        current_section = detect_section(text, current_section)
        display_page = extract_display_page(text, page_num + 1)

        chunks = text_splitter.split_text(text)

        for chunk_idx, chunk in enumerate(chunks):
            enriched_chunk = (
                f"Manual: {manual_name}\n"
                f"Section: {current_section}\n"
                f"Page: {display_page}\n\n"
                f"{chunk}"
            )

            documents.append(
                Document(
                    page_content=enriched_chunk,
                    metadata={
                        "source": pdf_path.name,
                        "manual": manual_name,
                        "section": current_section,
                        "page": page_num + 1,           # absolute PDF page number
                        "display_page": display_page,   # printed/manual page label
                        "chunk": chunk_idx,
                    },
                )
            )

            ids.append(f"{pdf_path.name}_page_{page_num + 1}_chunk_{chunk_idx}")

    doc.close()
    return documents, ids


# ----------------------------
# Vector store setup
# ----------------------------
configure_tesseract()

if FORCE_REINDEX and DB_DIR.exists():
    shutil.rmtree(DB_DIR)

embeddings = OllamaEmbeddings(model=EMBED_MODEL)

vector_store = Chroma(
    collection_name="equipment_manuals",
    persist_directory=str(DB_DIR),
    embedding_function=embeddings,
)

# Only build the DB if it does not exist yet
if not DB_DIR.exists():
    pdf_files = get_pdf_files()

    if not pdf_files:
        raise FileNotFoundError(
            "No PDF manuals found. Put PDFs in a 'Manuals' folder next to vector.py "
            "or in the same directory as vector.py."
        )

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=900,
        chunk_overlap=150,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    all_documents = []
    all_ids = []

    for pdf_file in pdf_files:
        documents, ids = build_documents_from_pdf(pdf_file, text_splitter)
        all_documents.extend(documents)
        all_ids.extend(ids)

    if not all_documents:
        raise ValueError("No text could be extracted from the PDF manuals.")

    vector_store.add_documents(documents=all_documents, ids=all_ids)

retriever = vector_store.as_retriever(search_kwargs={"k": 15})