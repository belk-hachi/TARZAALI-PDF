"""
PDF generation orchestration service.

Coordinates ReportLab PDF generation and ci-joint page merging.
Does NOT contain any ReportLab rendering logic — that lives in
generate_pdf.py and must not be changed.
"""

import os
import re
import logging
from io import BytesIO

from pypdf import PdfReader, PdfWriter

from .config import app_config, GENERATED_DIR, LOGO_PATH, UPLOAD_DIR
from .helpers import get_cijoint_pages, make_patient_filename

logger = logging.getLogger(__name__)


def generate_patient_pdf(patient, list_info, source_pdf_path=None,
                         cijoint_pages=None, custom_filename=None):
    """Generate a PDF report for a single patient.

    Steps:
    1. Build lab_config from app config.
    2. Call generate_pdf() to produce the ReportLab PDF.
    3. Merge ci-joint (annex) pages from the source PDF if any.
    4. Save the final PDF to the generated/ directory.

    Args:
        patient: Patient dict with tests/subtests.
        list_info: Dict with listNumber, listeDate, printDate.
        source_pdf_path: Path to original uploaded PDF (for ci-joint merge).
        cijoint_pages: List of 1-based page numbers to merge.
        custom_filename: Override the auto-generated filename.

    Returns:
        The filename (not path) of the generated PDF.
    """
    # Lazy import to avoid circular dependency at module level
    from .generate_pdf import generate_pdf

    lab_config = app_config.get_lab_config()

    # Step 1: Generate the ReportLab PDF
    report_bytes = generate_pdf(
        patient, list_info, logo_path=LOGO_PATH, lab_config=lab_config
    )

    # Step 2: Merge ci-joint pages if needed
    if cijoint_pages and source_pdf_path and os.path.exists(source_pdf_path):
        try:
            writer = PdfWriter()
            report_bytes.seek(0)
            reader_report = PdfReader(report_bytes)
            for page in reader_report.pages:
                writer.add_page(page)

            reader_source = PdfReader(source_pdf_path)
            total_source_pages = len(reader_source.pages)

            for page_num in cijoint_pages:
                idx = page_num - 1
                if 0 <= idx < total_source_pages:
                    writer.add_page(reader_source.pages[idx])

            merged = BytesIO()
            writer.write(merged)
            merged.seek(0)
            final_bytes = merged
        except Exception as e:
            logger.error("Error merging ci-joint pages: %s", e)
            report_bytes.seek(0)
            final_bytes = report_bytes
    else:
        report_bytes.seek(0)
        final_bytes = report_bytes

    # Step 3: Save final PDF
    if custom_filename:
        filename = custom_filename
    else:
        filename = make_patient_filename(patient)

    filepath = os.path.join(GENERATED_DIR, filename)

    with open(filepath, "wb") as f:
        f.write(final_bytes.read())

    return filename


def resolve_source_pdf(original_filename):
    """Resolve a source PDF path from the original filename stored in DB.

    Returns the full path if the file exists, or None if not found.
    """
    if not original_filename:
        return None
    path = os.path.join(UPLOAD_DIR, original_filename)
    if os.path.exists(path):
        return path
    return None
