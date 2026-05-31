"""
Dashboard routes: main dashboard view, patient CRUD operations
(mark printed, notes, delete, edit), and liste management.
"""

import logging

from flask import (
    Blueprint, render_template, request, jsonify, redirect, url_for,
)

from ..database import (
    get_all_listes, get_dashboard_stats, get_patients, count_patients,
    mark_patient_printed, unmark_patient_printed, update_patient_notes,
    update_patient_identity, delete_patient, delete_liste_if_empty,
    get_liste_by_id,
)

logger = logging.getLogger(__name__)

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard")
def dashboard():
    """Main dashboard showing listes and patients with pagination."""
    liste_id = request.args.get("liste_id", type=int)
    search_query = request.args.get("q", "")
    status_filter = request.args.get("status", "")
    page = request.args.get("page", 1, type=int)
    per_page = 25

    listes = get_all_listes()
    stats = get_dashboard_stats(liste_id=liste_id)
    total_count = count_patients(
        liste_id=liste_id,
        search_query=search_query,
        status_filter=status_filter,
    )

    offset = (page - 1) * per_page
    patients = get_patients(
        liste_id=liste_id,
        search_query=search_query,
        status_filter=status_filter,
        limit=per_page,
        offset=offset,
    )

    total_pages = (total_count + per_page - 1) // per_page
    selected_liste = (
        next((l for l in listes if l['id'] == liste_id), None)
        if liste_id else None
    )

    return render_template(
        "dashboard.html",
        listes=listes,
        patients=patients,
        selected_liste_id=liste_id,
        selected_liste=selected_liste,
        search_query=search_query,
        status_filter=status_filter,
        page=page,
        total_pages=total_pages,
        total_count=total_count,
        stats=stats,
    )


@dashboard_bp.route("/mark-printed/<int:patient_id>", methods=["POST"])
def mark_printed(patient_id):
    """Mark a patient as delivered in the database."""
    mark_patient_printed(patient_id)
    return jsonify({"success": True})


@dashboard_bp.route("/unmark-printed/<int:patient_id>", methods=["POST"])
def unmark_printed(patient_id):
    """Unmark a patient as delivered in the database."""
    unmark_patient_printed(patient_id)
    return jsonify({"success": True})


@dashboard_bp.route("/update-notes/<int:patient_id>", methods=["POST"])
def update_notes(patient_id):
    """Update a patient's notes in the database."""
    data = request.json
    notes = data.get("notes", "")
    update_patient_notes(patient_id, notes)
    return jsonify({"success": True})


@dashboard_bp.route("/update-patient", methods=["POST"])
def update_patient_route():
    """Update patient information (name, DOB) in DB with conflict resolution.

    This is the most complex route — it updates identity across both
    the patients and patient_metadata tables, merging metadata if the
    new identity already exists.
    """
    data = request.json
    patient_id = data.get("patient_id")
    new_last_name = data.get("last_name")
    new_first_name = data.get("first_name")
    new_dob = data.get("date_of_birth")
    status = data.get("status")

    if not patient_id or not new_last_name or not new_first_name:
        return jsonify({
            "success": False,
            "error": "Champs obligatoires manquants",
        }), 400

    success, error = update_patient_identity(
        patient_id, new_last_name, new_first_name, new_dob, status=status
    )

    if success:
        return jsonify({"success": True})
    else:
        status_code = 404 if "introuvable" in (error or "").lower() else 500
        return jsonify({"success": False, "error": error}), status_code


@dashboard_bp.route("/delete-patient/<int:patient_id>", methods=["POST"])
def delete_patient_route(patient_id):
    """Delete a patient record from DB."""
    delete_patient(patient_id)
    return redirect(url_for("dashboard.dashboard", **request.args))


@dashboard_bp.route("/delete-liste/<int:liste_id>", methods=["POST"])
def delete_liste_route(liste_id):
    """Delete an entire list ONLY if it has no patients."""
    delete_liste_if_empty(liste_id)
    return redirect(url_for("dashboard.dashboard"))


@dashboard_bp.route("/view-source/<int:liste_id>")
def view_source_pdf(liste_id):
    """Show the original uploaded PDF in the viewer."""
    row = get_liste_by_id(liste_id)

    if not row or not row['original_filename']:
        return (
            "Fichier original introuvable ou non enregistré pour "
            "cette liste.", 404
        )

    return render_template(
        "viewer.html",
        session_id="source",
        patient_index=liste_id,
        patient_name=row['list_number'],
        pdf_filename=row['original_filename'],
        is_source=True,
    )
