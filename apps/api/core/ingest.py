"""
Document Ingestion, Validation, Parsing, and Classification Engine (PRD Sections 7.2, 7.3 & FR-3).

Features:
- MIME & Magic bytes validation (rejects disguised binaries, executables, scripts).
- Zip bomb & path traversal detection.
- Multi-format text extraction with page numbers and character offsets (PyMuPDF, python-docx, openpyxl, csv).
- OCR fallback handling for pages with no text layer.
- Ephemeral processing: files processed in memory / temporary directories and immediately deleted.
- 1-hour temp directory sweeper.
- Filename and keyword heuristics classification (low confidence = "unclassified").
- Privacy & logging: strictly logs IDs and status only, never document text or numerical values.
"""
import io
import os
import re
import time
import shutil
import zipfile
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger("ledgerlight.ingest")

# Allowed extensions per PRD 7.2
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".csv", ".txt", ".zip"}

# Forbidden executable/script extensions
DISALLOWED_EXTENSIONS = {
    ".exe", ".dll", ".bat", ".cmd", ".sh", ".ps1", ".vbs", ".elf",
    ".com", ".scr", ".msi", ".jar", ".bin", ".py", ".rb", ".php"
}

# Known executable magic signatures
FORBIDDEN_MAGIC_SIGNATURES = [
    (b"MZ", "Windows PE executable or DLL (MZ header)"),
    (b"\x7fELF", "Linux ELF executable"),
    (b"\xca\xfe\xba\xbe", "Java Class or Mach-O binary"),
    (b"#!", "Executable script shebang"),
]

# Configurable size limits (PRD 7.2)
DEFAULT_MAX_FILE_SIZE_MB = int(os.environ.get("MAX_FILE_SIZE_MB", "50"))
DEFAULT_MAX_ZIP_SIZE_MB = int(os.environ.get("MAX_ZIP_SIZE_MB", "500"))
DEFAULT_MAX_ZIP_FILES = int(os.environ.get("MAX_ZIP_FILES", "500"))
DEFAULT_MAX_ZIP_RATIO = float(os.environ.get("MAX_ZIP_RATIO", "100.0"))


@dataclass
class ParsedPage:
    page_number: int
    text: str
    char_count: int
    tables: List[List[List[Any]]] = field(default_factory=list)
    has_text_layer: bool = True


@dataclass
class ParsedDocument:
    filename: str
    file_type: str
    sha256: str
    mime_type: str
    page_count: int
    pages: List[ParsedPage]
    file_size: int


class IngestSecurityError(ValueError):
    """Raised when an uploaded file violates security or format policies."""
    pass


def compute_sha256(content: bytes) -> str:
    """Computes SHA-256 hex digest of file bytes."""
    h = hashlib.sha256()
    h.update(content)
    return h.hexdigest()


def validate_file_security(
    filename: str,
    content: bytes,
    max_size_mb: int = DEFAULT_MAX_FILE_SIZE_MB
) -> str:
    """
    Validates MIME type, extension, magic bytes, size limits, and non-executable status.
    Returns detected sanitized MIME type or raises IngestSecurityError.
    """
    base_name = os.path.basename(filename)
    _, ext = os.path.splitext(base_name.lower())

    if not ext or ext not in ALLOWED_EXTENSIONS:
        raise IngestSecurityError(
            f"Unsupported file extension '{ext}'. Allowed extensions: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    if ext in DISALLOWED_EXTENSIONS:
        raise IngestSecurityError(f"Executable file types are strictly prohibited: '{base_name}'")

    # Size limit
    max_bytes = max_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise IngestSecurityError(
            f"File size ({len(content)} bytes) exceeds the allowed limit of {max_size_mb} MB"
        )

    if len(content) == 0:
        raise IngestSecurityError("File is empty (0 bytes)")

    # Check for binary executable magic signatures
    for sig, desc in FORBIDDEN_MAGIC_SIGNATURES:
        if content.startswith(sig):
            raise IngestSecurityError(f"Rejected disguised executable or binary: {desc}")

    # Extension-specific magic bytes validation
    if ext == ".pdf":
        if not content.startswith(b"%PDF-"):
            raise IngestSecurityError("Invalid PDF file: Missing %PDF- magic signature header")
        return "application/pdf"

    elif ext in (".docx", ".xlsx", ".zip"):
        # PKZip header
        if not content.startswith(b"PK\x03\x04"):
            raise IngestSecurityError(f"Invalid ZIP container header for {ext}: Missing PK zip magic bytes")
        
        # Verify valid zip container
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                bad_file = zf.testzip()
                if bad_file:
                    raise IngestSecurityError(f"Corrupted archive entry: {bad_file}")
                
                namelist = zf.namelist()
                if ext == ".docx":
                    if not any("word/document.xml" in name for name in namelist):
                        raise IngestSecurityError("Invalid DOCX: Missing word/document.xml package structure")
                    return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                elif ext == ".xlsx":
                    if not any("xl/workbook.xml" in name for name in namelist):
                        raise IngestSecurityError("Invalid XLSX: Missing xl/workbook.xml package structure")
                    return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                else:
                    return "application/zip"
        except zipfile.BadZipFile:
            raise IngestSecurityError(f"Corrupted or invalid {ext} package format")

    elif ext == ".csv":
        # Check text validity
        try:
            sample = content[:4096].decode("utf-8")
        except UnicodeDecodeError:
            try:
                sample = content[:4096].decode("latin-1")
            except Exception:
                raise IngestSecurityError("Invalid CSV encoding: Content must be valid UTF-8/Latin text")
        
        if "\x00" in sample:
            raise IngestSecurityError("Binary null byte detected in CSV file")
        return "text/csv"

    elif ext == ".txt":
        try:
            sample = content[:4096].decode("utf-8")
        except UnicodeDecodeError:
            try:
                sample = content[:4096].decode("latin-1")
            except Exception:
                raise IngestSecurityError("Invalid text encoding: Content must be valid UTF-8/Latin text")
        
        if "\x00" in sample:
            raise IngestSecurityError("Binary null byte detected in text file")
        return "text/plain"

    return "application/octet-stream"


def validate_and_extract_zip(
    zip_bytes: bytes,
    max_total_mb: int = DEFAULT_MAX_ZIP_SIZE_MB,
    max_files: int = DEFAULT_MAX_ZIP_FILES,
    max_ratio: float = DEFAULT_MAX_ZIP_RATIO
) -> List[Tuple[str, bytes]]:
    """
    Validates zip against path traversal and zip bombs, then extracts allowable files in-memory.
    Returns list of (clean_filename, content_bytes).
    """
    extracted_files: List[Tuple[str, bytes]] = []
    max_total_bytes = max_total_mb * 1024 * 1024
    cumulative_uncompressed_bytes = 0

    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            infolist = zf.infolist()
            
            if len(infolist) > max_files:
                raise IngestSecurityError(
                    f"ZIP archive contains {len(infolist)} files, exceeding limit of {max_files}"
                )

            for info in infolist:
                if info.is_dir():
                    continue

                raw_name = info.filename
                # Path traversal checks
                if raw_name.startswith(("/", "\\")):
                    raise IngestSecurityError(f"Path traversal attempt in ZIP entry: '{raw_name}' (absolute path)")
                
                parts = raw_name.replace("\\", "/").split("/")
                if ".." in parts:
                    raise IngestSecurityError(f"Path traversal attempt in ZIP entry: '{raw_name}' ('..' detected)")
                
                if re.match(r"^[a-zA-Z]:", raw_name):
                    raise IngestSecurityError(f"Path traversal attempt in ZIP entry: '{raw_name}' (drive letter)")

                # Zip bomb checks
                compressed_size = max(info.compress_size, 1)
                uncompressed_size = info.file_size
                ratio = uncompressed_size / compressed_size

                if ratio > max_ratio and uncompressed_size > 1024 * 1024:
                    raise IngestSecurityError(
                        f"Zip bomb detected in entry '{raw_name}' (compression ratio {ratio:.1f}x > {max_ratio}x)"
                    )

                cumulative_uncompressed_bytes += uncompressed_size
                if cumulative_uncompressed_bytes > max_total_bytes:
                    raise IngestSecurityError(
                        f"ZIP cumulative uncompressed size exceeds safety ceiling of {max_total_mb} MB"
                    )

                clean_filename = os.path.basename(raw_name)
                _, ext = os.path.splitext(clean_filename.lower())
                
                if ext not in ALLOWED_EXTENSIONS or ext == ".zip":
                    # Ignore unsupported or nested archives
                    continue

                content = zf.read(info)
                # Run security validation on inner file
                validate_file_security(clean_filename, content)
                extracted_files.append((clean_filename, content))

    except zipfile.BadZipFile:
        raise IngestSecurityError("Corrupted or malformed ZIP archive")

    if not extracted_files:
        raise IngestSecurityError("No valid supported documents found in ZIP archive")

    return extracted_files


def parse_pdf_document(content: bytes) -> List[ParsedPage]:
    """Extracts text from PDF page by page using PyMuPDF."""
    pages: List[ParsedPage] = []
    try:
        import pymupdf  # PyMuPDF
        doc = pymupdf.open(stream=content, filetype="pdf")
        for pno in range(len(doc)):
            page = doc[pno]
            text = page.get_text("text") or ""
            has_text = len(text.strip()) > 0
            
            # If no text layer, try OCR if pytesseract is available
            if not has_text:
                try:
                    import pytesseract
                    from PIL import Image
                    pix = page.get_pixmap()
                    img = Image.open(io.BytesIO(pix.tobytes("png")))
                    text = pytesseract.image_to_string(img) or ""
                    has_text = len(text.strip()) > 0
                except Exception:
                    # OCR not installed or unavailable; keep empty text gracefully
                    has_text = False

            pages.append(ParsedPage(
                page_number=pno + 1,
                text=text,
                char_count=len(text),
                has_text_layer=has_text
            ))
        doc.close()
    except Exception as e:
        logger.warning(f"PyMuPDF parse error: {str(e)}")
        # Fallback to plain string extraction if possible
        raw_text = content.decode("latin-1", errors="ignore")
        pages.append(ParsedPage(page_number=1, text=raw_text[:2000], char_count=min(len(raw_text), 2000)))
    
    return pages or [ParsedPage(page_number=1, text="", char_count=0, has_text_layer=False)]


def parse_docx_document(content: bytes) -> List[ParsedPage]:
    """Extracts text and tables from DOCX using python-docx."""
    pages: List[ParsedPage] = []
    try:
        import docx
        doc = docx.Document(io.BytesIO(content))
        lines: List[str] = []
        tables_data: List[List[List[Any]]] = []

        for p in doc.paragraphs:
            if p.text.strip():
                lines.append(p.text.strip())

        for tbl in doc.tables:
            table_rows = []
            for row in tbl.rows:
                table_rows.append([cell.text.strip() for cell in row.cells])
            if table_rows:
                tables_data.append(table_rows)

        full_text = "\n".join(lines)
        # Approximate 3000 chars per page for DOCX
        chunk_size = 3000
        if len(full_text) <= chunk_size:
            pages.append(ParsedPage(page_number=1, text=full_text, char_count=len(full_text), tables=tables_data))
        else:
            pno = 1
            for i in range(0, len(full_text), chunk_size):
                chunk = full_text[i:i + chunk_size]
                pages.append(ParsedPage(page_number=pno, text=chunk, char_count=len(chunk), tables=tables_data if pno == 1 else []))
                pno += 1
    except Exception as e:
        logger.warning(f"DOCX parse error: {str(e)}")
        pages.append(ParsedPage(page_number=1, text="", char_count=0))

    return pages or [ParsedPage(page_number=1, text="", char_count=0)]


def parse_xlsx_document(content: bytes) -> List[ParsedPage]:
    """Extracts sheets and structured table data from XLSX using openpyxl."""
    pages: List[ParsedPage] = []
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
        pno = 1
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            sheet_rows: List[List[Any]] = []
            text_lines = [f"--- Sheet: {sheet_name} ---"]
            
            for row in ws.iter_rows(values_only=True):
                if any(v is not None and str(v).strip() != "" for v in row):
                    clean_row = [v if v is not None else "" for v in row]
                    sheet_rows.append(clean_row)
                    row_str = " | ".join(str(c) for c in clean_row if str(c).strip())
                    if row_str:
                        text_lines.append(row_str)

            sheet_text = "\n".join(text_lines)
            pages.append(ParsedPage(
                page_number=pno,
                text=sheet_text,
                char_count=len(sheet_text),
                tables=[sheet_rows] if sheet_rows else []
            ))
            pno += 1
    except Exception as e:
        logger.warning(f"XLSX parse error: {str(e)}")
        pages.append(ParsedPage(page_number=1, text="", char_count=0))

    return pages or [ParsedPage(page_number=1, text="", char_count=0)]


def parse_csv_document(content: bytes) -> List[ParsedPage]:
    """Extracts structured rows and text from CSV."""
    import csv
    text_content = content.decode("utf-8", errors="ignore")
    lines = text_content.splitlines()
    rows: List[List[Any]] = []
    reader = csv.reader(lines)
    for r in reader:
        if any(c.strip() for c in r):
            rows.append(r)

    return [ParsedPage(
        page_number=1,
        text=text_content,
        char_count=len(text_content),
        tables=[rows] if rows else []
    )]


def parse_txt_document(content: bytes) -> List[ParsedPage]:
    """Extracts text from TXT file."""
    text_content = content.decode("utf-8", errors="ignore")
    return [ParsedPage(
        page_number=1,
        text=text_content,
        char_count=len(text_content)
    )]


def parse_document(filename: str, content: bytes) -> ParsedDocument:
    """
    Parses document safely into structured pages and tables.
    Raw content is processed in memory and not written to disk.
    """
    mime_type = validate_file_security(filename, content)
    sha256 = compute_sha256(content)
    base_name = os.path.basename(filename)
    _, ext = os.path.splitext(base_name.lower())

    if ext == ".pdf":
        pages = parse_pdf_document(content)
    elif ext == ".docx":
        pages = parse_docx_document(content)
    elif ext == ".xlsx":
        pages = parse_xlsx_document(content)
    elif ext == ".csv":
        pages = parse_csv_document(content)
    elif ext == ".txt":
        pages = parse_txt_document(content)
    else:
        pages = [ParsedPage(page_number=1, text="", char_count=0)]

    file_type = classify_document(base_name, pages)

    return ParsedDocument(
        filename=base_name,
        file_type=file_type,
        sha256=sha256,
        mime_type=mime_type,
        page_count=len(pages),
        pages=pages,
        file_size=len(content)
    )


def classify_document(filename: str, pages: List[ParsedPage]) -> str:
    """
    Classifies document by filename and keyword heuristics (PRD 7.3).
    Returns one of:
      - financial_statement
      - cap_table
      - bank_statement
      - customer_contract
      - employment_ip_agreement
      - board_minutes
      - policy
      - certificate_or_report
      - other / unclassified
    Low confidence returns 'unclassified'.
    """
    fn = filename.lower()
    combined_sample = " ".join(p.text[:1500].lower() for p in pages[:5])

    # 1. Cap table
    if any(k in fn for k in ["cap_table", "captable", "capitalization", "share_registry", "equity_summary"]):
        return "cap_table"
    if "fully diluted" in combined_sample and ("common stock" in combined_sample or "options granted" in combined_sample):
        return "cap_table"

    # 2. Bank statement
    if any(k in fn for k in ["bank_statement", "account_statement", "checking_statement", "wire_confirmation"]):
        return "bank_statement"
    if ("bank" in combined_sample or "svb" in combined_sample or "jpmorgan" in combined_sample or "chase" in combined_sample) and ("ending balance" in combined_sample or "beginning balance" in combined_sample):
        return "bank_statement"

    # 3. Financial statement (P&L, Balance Sheet, Budget)
    if any(k in fn for k in ["p&l", "income_statement", "balance_sheet", "financial_statements", "budget", "10-k", "10-q", "trial_balance"]):
        return "financial_statement"
    if ("revenue" in combined_sample or "gross margin" in combined_sample or "ebitda" in combined_sample) and ("operating expenses" in combined_sample or "net income" in combined_sample or "cost of goods" in combined_sample):
        return "financial_statement"

    # 4. Certificate or Audit Report (SOC 2, ISO 9001, FDA, PCI-DSS)
    if any(k in fn for k in ["soc2", "soc_2", "iso9001", "iso_9001", "iso27001", "fda_510k", "pci_dss", "audit_report", "certificate"]):
        return "certificate_or_report"
    if ("soc 2" in combined_sample or "type ii" in combined_sample or "service organization control" in combined_sample or "iso 9001" in combined_sample or "fda establishment registration" in combined_sample):
        return "certificate_or_report"

    # 5. Policies (BCP/DR, Incident Response, InfoSec, Data Privacy)
    if any(k in fn for k in ["policy", "procedure", "plan", "handbook", "sop"]):
        return "policy"
    if ("business continuity" in combined_sample or "disaster recovery" in combined_sample or "incident response" in combined_sample or "information security policy" in combined_sample or "privacy policy" in combined_sample):
        return "policy"

    # 6. Customer Contract
    if any(k in fn for k in ["msa", "master_services", "customer_contract", "sow", "service_agreement", "order_form"]):
        return "customer_contract"
    if ("master services agreement" in combined_sample or "statement of work" in combined_sample or ("service level agreement" in combined_sample and "uptime" in combined_sample)):
        return "customer_contract"

    # 7. Employment / IP agreement
    if any(k in fn for k in ["piia", "invention_assignment", "offer_letter", "employment_agreement", "nda", "non_disclosure"]):
        return "employment_ip_agreement"
    if "proprietary information" in combined_sample and "inventions agreement" in combined_sample:
        return "employment_ip_agreement"

    # 8. Board Minutes
    if any(k in fn for k in ["board_minutes", "unanimous_consent", "resolutions"]):
        return "board_minutes"
    if "minutes of" in combined_sample and "board of directors" in combined_sample:
        return "board_minutes"

    # Low confidence -> unclassified (PRD 7.3: do not guess)
    return "unclassified"


# Ephemeral temporary directory root for ingestion
TEMP_DIR = os.path.abspath(
    os.environ.get("INGEST_TEMP_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "..", ".temp_ingest"))
)
os.makedirs(TEMP_DIR, exist_ok=True)


def sweep_temp_files(temp_root: Optional[str] = None, max_age_seconds: int = 3600) -> int:
    """
    Deletes any temporary directories or files older than max_age_seconds (default 1 hour).
    Returns count of cleaned entries.
    """
    target_root = temp_root or TEMP_DIR
    cleaned = 0
    now = time.time()
    if not os.path.exists(target_root):
        return 0

    for item in os.listdir(target_root):
        item_path = os.path.join(target_root, item)
        try:
            mtime = os.path.getmtime(item_path)
            if (now - mtime) > max_age_seconds:
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path, ignore_errors=True)
                else:
                    os.remove(item_path)
                cleaned += 1
        except Exception:
            pass

    return cleaned

