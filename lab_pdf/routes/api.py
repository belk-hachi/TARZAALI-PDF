"""
API routes: config, models, online results, backup.
"""

import json
import logging

from flask import Blueprint, request, jsonify

from ..config import app_config
from ..ai_service import ai_service
from ..online_service import fetch_online_results
from ..database import get_liste_by_id
from ..backup_service import create_backup

logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__)


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
