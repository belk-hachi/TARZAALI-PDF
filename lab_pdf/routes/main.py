"""
Main routes: index, upload page, static file serving.
"""

from flask import Blueprint, redirect, url_for, send_file, render_template

from ..config import LOGO_PATH, GENERATED_DIR, UPLOAD_DIR
from ..helpers import validate_filename

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    """Redirect root to dashboard."""
    return redirect(url_for("dashboard.dashboard"))


@main_bp.route("/upload-page")
def upload_page():
    """Show the upload form."""
    return render_template("upload.html")


@main_bp.route("/pdf/<filename>")
def serve_pdf(filename):
    """Serve a generated PDF file for in-browser rendering."""
    if not validate_filename(filename):
        return "Invalid filename", 400
    # Only serve .pdf files
    if not filename.lower().endswith(".pdf"):
        return "Invalid file type", 400
    pdf_path = GENERATED_DIR / filename if hasattr(GENERATED_DIR, '__truediv__') else f"{GENERATED_DIR}/{filename}"
    import os
    if not os.path.exists(pdf_path):
        return "PDF not found", 404
    return send_file(pdf_path, mimetype="application/pdf")


@main_bp.route("/source-pdf/<filename>")
def serve_source_pdf(filename):
    """Serve an original uploaded PDF file."""
    if not validate_filename(filename):
        return "Invalid filename", 400
    if not filename.lower().endswith(".pdf"):
        return "Invalid file type", 400
    import os
    pdf_path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(pdf_path):
        return "Original PDF not found", 404
    return send_file(pdf_path, mimetype="application/pdf")


@main_bp.route("/logo.jpg")
def serve_logo():
    """Serve the laboratory logo."""
    return send_file(LOGO_PATH, mimetype="image/jpeg")
