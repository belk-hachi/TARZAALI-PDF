"""
Patient routes: view, download, generate partial PDFs for DB-stored patients.
"""

import os
import uuid
import json
import logging

from flask import (
    Blueprint, render_template, request, jsonify, redirect, url_for,
    send_file,
)

from ..database import get_patient_with_liste
from ..config import GENERATED_DIR, UPLOAD_DIR
from ..helpers import (
    get_cijoint_pages, make_patient_filename, validate_filename,
)
from ..pdf_service import generate_patient_pdf, resolve_source_pdf

logger = logging.getLogger(__name__)

patient_bp = Blueprint("patient", __name__)


@patient_bp.route("/view-db/<int:patient_id>")
def view_patient_db(patient_id):
    """Generate PDF for a patient from DB and show it in the viewer."""
    row = get_patient_with_liste(patient_id)
    if not row:
        return redirect(url_for("dashboard.dashboard"))

    patient = json.loads(row['patient_json'])
    # Apply any identity corrections from the DB
    patient['lastName'] = row['last_name']
    patient['firstName'] = row['first_name']
    patient['dateOfBirth'] = row['date_of_birth']

    list_info = {
        "listNumber": row['list_number'],
        "listeDate": row['liste_date'],
        "printDate": row['print_date'],
    }

    source_pdf_path = resolve_source_pdf(row['original_filename'])
    cijoint_pages = (
        get_cijoint_pages(patient) if source_pdf_path else []
    )

    pdf_filename = generate_patient_pdf(
        patient, list_info, source_pdf_path, cijoint_pages
    )
    patient_name = f"{row['last_name']} {row['first_name']}"

    return render_template(
        "viewer.html",
        session_id="db",
        patient_index=patient_id,
        patient_name=patient_name,
        pdf_filename=pdf_filename,
    )


@patient_bp.route("/download-db/<int:patient_id>")
def download_patient_db(patient_id):
    """Download the generated patient PDF from DB record."""
    row = get_patient_with_liste(patient_id)
    if not row:
        return redirect(url_for("dashboard.dashboard"))

    patient = json.loads(row['patient_json'])
    patient['lastName'] = row['last_name']
    patient['firstName'] = row['first_name']
    patient['dateOfBirth'] = row['date_of_birth']

    last_name = row['last_name']
    first_name = row['first_name']

    list_info = {
        "listNumber": row['list_number'],
        "listeDate": row['liste_date'],
        "printDate": row['print_date'],
    }

    source_pdf_path = resolve_source_pdf(row['original_filename'])
    cijoint_pages = (
        get_cijoint_pages(patient) if source_pdf_path else []
    )

    # Always re-generate to pick up identity corrections
    pdf_filename = generate_patient_pdf(
        patient, list_info, source_pdf_path, cijoint_pages
    )
    pdf_path = os.path.join(GENERATED_DIR, pdf_filename)
    download_name = f"{last_name}_{first_name}_results.pdf"

    return send_file(
        pdf_path,
        as_attachment=True,
        download_name=download_name,
        mimetype="application/pdf",
    )


@patient_bp.route("/generate-partial/<int:patient_id>", methods=["POST"])
def generate_partial_pdf_route(patient_id):
    """Generate a PDF for a patient with only selected tests."""
    data = request.json
    selected_indices = data.get("test_indices", [])

    if not selected_indices:
        return jsonify({"error": "Aucun test sélectionné"}), 400

    row = get_patient_with_liste(patient_id)
    if not row:
        return jsonify({"error": "Patient introuvable"}), 404

    patient = json.loads(row['patient_json'])

    # Filter tests by selected indices
    all_tests = patient.get("tests", [])
    filtered_tests = [
        all_tests[i] for i in selected_indices
        if 0 <= i < len(all_tests)
    ]

    if not filtered_tests:
        return jsonify({"error": "Sélection de tests invalide"}), 400

    # Build partial patient object
    partial_patient = patient.copy()
    partial_patient["tests"] = filtered_tests

    list_info = {
        "listNumber": row['list_number'],
        "listeDate": row['liste_date'],
        "printDate": row['print_date'],
    }

    source_pdf_path = resolve_source_pdf(row['original_filename'])
    cijoint_pages = (
        get_cijoint_pages(partial_patient) if source_pdf_path else []
    )

    # Generate with a unique filename to avoid collisions
    unique_id = str(uuid.uuid4())[:4]
    custom_filename = make_patient_filename(partial_patient, suffix=f"PARTIAL_{unique_id}")

    pdf_filename = generate_patient_pdf(
        partial_patient, list_info, source_pdf_path,
        cijoint_pages, custom_filename=custom_filename,
    )

    last_name = row['last_name']
    first_name = row['first_name']

    return jsonify({
        "success": True,
        "pdf_url": url_for(
            'patient.view_partial_pdf',
            filename=pdf_filename,
            patient_name=f"{last_name} {first_name}",
        ),
    })


@patient_bp.route("/view-partial/<filename>")
def view_partial_pdf(filename):
    """View a partially generated PDF."""
    if not validate_filename(filename):
        return "Invalid filename", 400
    patient_name = request.args.get("patient_name", "Patient")
    return render_template(
        "viewer.html",
        session_id="partial",
        patient_index=0,
        patient_name=patient_name,
        pdf_filename=filename,
    )


@patient_bp.route("/download-partial/<filename>")
def download_partial_pdf(filename):
    """Download a partially generated PDF."""
    if not validate_filename(filename):
        return "Invalid filename", 400
    pdf_path = os.path.join(GENERATED_DIR, filename)
    if not os.path.exists(pdf_path):
        return jsonify({"error": "PDF introuvable"}), 404

    return send_file(
        pdf_path,
        as_attachment=True,
        download_name="selection_analyses.pdf",
        mimetype="application/pdf",
    )
