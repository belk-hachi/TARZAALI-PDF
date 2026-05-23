"""
Upload route: PDF upload → AI extraction → database save → redirect.
"""

import os
import re
import uuid
import json
import logging

from flask import Blueprint, request, jsonify, render_template, redirect, url_for

from ..config import app_config, UPLOAD_DIR
from ..database import save_extraction_result
from ..ai_service import ai_service
from ..helpers import get_patient_status_summary, get_patient_status_details, get_cijoint_pages

logger = logging.getLogger(__name__)

upload_bp = Blueprint("upload", __name__)


@upload_bp.route("/upload", methods=["POST"])
def upload():
    """Upload PDF → AI extracts data → save to DB → redirect to dashboard."""
    if "pdf_file" not in request.files:
        return jsonify({"error": "Aucun fichier téléchargé"}), 400

    file = request.files["pdf_file"]
    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Seuls les fichiers PDF sont autorisés"}), 400

    # Save uploaded file
    session_id = str(uuid.uuid4())[:8]
    pdf_filename = f"{session_id}_{file.filename}"
    pdf_path = os.path.join(UPLOAD_DIR, pdf_filename)
    file.save(pdf_path)

    try:
        # Get model from config
        config = app_config.load()
        model = config.get("model", "gemini-2.5-flash")

        # Call AI for extraction
        prompt = app_config.load_prompt()
        extraction_result = ai_service.extract_from_pdf(
            pdf_path, prompt, model_name=model
        )

        # Persist to SQLite (this is the primary storage — no JSON sessions)
        liste_id = None
        try:
            liste_id = save_extraction_result(
                extraction_result, original_filename=pdf_filename
            )
        except Exception as db_err:
            logger.error("Error saving to database: %s", db_err)

        # Redirect to Dashboard filtered by the new list ID
        if liste_id:
            return redirect(url_for("dashboard.dashboard", liste_id=liste_id))
        else:
            return redirect(url_for("dashboard.dashboard"))

    except json.JSONDecodeError as e:
        return render_template(
            "upload.html",
            error=f"L'IA a retourné un JSON invalide : {str(e)}",
        )
    except Exception as e:
        error_msg = str(e)
        friendly_error = _classify_ai_error(error_msg)
        return render_template("upload.html", error=friendly_error)


def _classify_ai_error(error_msg):
    """Convert raw AI error messages into user-friendly French text."""
    if ("RESOURCE_EXHAUSTED" in error_msg
            or "429" in error_msg
            or "quota" in error_msg.lower()):
        return (
            "Limite de quota (version gratuite) atteinte. "
            "Veuillez patienter environ 30 secondes à 1 minute "
            "avant de réessayer."
        )
    if "503" in error_msg or "UNAVAILABLE" in error_msg:
        return (
            "Le service IA est temporairement surchargé. "
            "Veuillez réessayer dans quelques instants."
        )
    if "getaddrinfo" in error_msg or "Errno 11001" in error_msg:
        return (
            "Erreur de connexion : Impossible d'atteindre le service IA. "
            "Veuillez vérifier votre connexion internet."
        )
    return f"Erreur de traitement : {error_msg}"
