"""
API routes: config, models, online results, backup.
"""

import json
import logging
import os

from flask import Blueprint, request, jsonify

from ..config import app_config, LOGS_DIR
from ..ai_service import ai_service
from ..online_service import fetch_online_results
from ..database import get_liste_by_id
from ..backup_service import create_backup

logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__)


@api_bp.route("/api/email-activity", methods=["GET"])
def get_email_activity():
    """Reads the last 50 lines of activity.log."""
    log_path = os.path.join(LOGS_DIR, "activity.log")
    if not os.path.exists(log_path):
        return jsonify({"lines": ["Aucune activité enregistrée."]})
    
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            # Return last 50 lines, stripped of trailing newlines
            last_lines = [line.strip() for line in lines[-50:]]
            return jsonify({"lines": last_lines})
    except Exception as e:
        logger.error(f"Error reading activity log: {e}")
        return jsonify({"lines": [f"Erreur lors de la lecture des logs: {e}"]})


@api_bp.route("/api/config", methods=["GET", "POST"])
def config_endpoint():
    """Get or update application configuration.

    GET: Returns current config (passwords de-obscured).
    POST: Updates config fields. Accepted fields match the keys in
          config.json — these names are backward-compatible and must
          not be renamed.
    """
    if request.method == "POST":
        data = request.json
        config = app_config.load()
        fields = [
            "api_key", "model", "online_username", "online_password",
            "online_api_key", "lab_dr_name", "lab_addr_l1",
            "lab_addr_l2", "lab_tel", "lab_fax", "lab_mobile",
            "backup_dir", "max_backups",
            "email_imap_server", "email_user", "email_pass",
            "email_folder", "email_sender_filter", "email_subject_filter",
            "email_main_pdf_keyword", "email_fetch_interval",
            "delete_after_fetch"
        ]
        for f in fields:
            if f in data:
                config[f] = data[f]

        app_config.save(config)
        return jsonify({"success": True})

    return jsonify(app_config.load())


@api_bp.route("/api/models")
def get_available_models():
    """Fetch available Gemini models filtered for preferred versions."""
    api_key = app_config.get_api_key()
    if not api_key:
        return jsonify({"error": "API key missing"}), 400

    try:
        models = ai_service.list_models(api_key)
        return jsonify(models)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/api/notifications")
def get_notifications():
    """Get all unread notifications."""
    from ..database import get_unread_notifications
    rows = get_unread_notifications()
    notifications = [dict(row) for row in rows]
    return jsonify(notifications)


@api_bp.route("/api/notifications/read", methods=["POST"])
def mark_read():
    """Mark all notifications as read."""
    from ..database import mark_notifications_read
    mark_notifications_read()
    return jsonify({"success": True})


@api_bp.route("/api/online-results/<int:liste_id>")
def online_results(liste_id):
    """Fetch real-time lab results from external API for a specific list date."""
    row = get_liste_by_id(liste_id)
    if not row:
        return jsonify({"error": "Liste introuvable"}), 404

    data, error = fetch_online_results(liste_id, row['liste_date'])
    if error:
        return jsonify({"error": error}), 502

    return jsonify(data)


@api_bp.route("/api/test-backup-dir", methods=["POST"])
def test_backup_dir():
    """Verify that a directory is accessible and writable.

    This is used to test network paths or custom local folders
    before saving the configuration.
    """
    import os
    data = request.json
    path = data.get("path")

    if not path:
        return jsonify({"success": True, "message": "Le dossier par défaut sera utilisé."})

    try:
        # Check if exists (or can be created)
        if not os.path.exists(path):
            try:
                os.makedirs(path, exist_ok=True)
            except Exception:
                return jsonify({"error": f"Le dossier n'existe pas et ne peut pas être créé."}), 400

        # Check writability by creating a temporary file
        test_file = os.path.join(path, ".write_test")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)

        return jsonify({"success": True, "message": "Connexion réussie ! Le dossier est accessible et scriptable."})
    except Exception as e:
        logger.error("Backup directory test failed: %s", e)
        return jsonify({"error": f"Erreur d'accès : {str(e)}"}), 500


@api_bp.route("/api/trigger-email-fetch", methods=["POST"])
def trigger_email_fetch():
    """Manually trigger the email fetching process.

    This runs the fetcher in the current thread and returns
    the count of emails found.
    """
    from ..email_service import fetch_and_process_emails
    try:
        count = fetch_and_process_emails()
        return jsonify({"success": True, "count": count})
    except Exception as e:
        logger.error("Manual email fetch failed: %s", e)
        return jsonify({"error": str(e)}), 500


@api_bp.route("/api/backup", methods=["POST"])
def trigger_backup():
    """Manually trigger a backup.

    Returns the backup directory path on success, or an error on failure.
    """
    result = create_backup()
    if result:
        return jsonify({"success": True, "backup_dir": result})
    else:
        return jsonify({"error": "La sauvegarde a échoué"}), 500
