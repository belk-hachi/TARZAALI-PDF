"""
External lab results API service.

Fetches real-time lab results from the Tarzaali Online (biogroupe)
API. Treats the external service as unreliable — all errors are
caught and returned as user-friendly French messages.
"""

import logging

import requests

from .config import app_config

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15  # seconds


def fetch_online_results(liste_id, liste_date):
    """Fetch real-time lab results from the external API.

    Args:
        liste_id: The list ID (used to look up credentials).
        liste_date: Date string in DD/MM/YYYY format.

    Returns:
        Tuple of (data_dict, None) on success, or (None, error_message)
        on failure. Error messages are in French for display to the user.
    """
    # Convert DD/MM/YYYY to YYYYMMDD for the API
    try:
        date_param = (
            liste_date[6:10] + liste_date[3:5] + liste_date[0:2]
        )
    except Exception:
        return None, "Format de date invalide"

    # Load credentials from config
    config = app_config.load()
    username = config.get("online_username", "")
    password = config.get("online_password", "")
    api_key = config.get(
        "online_api_key",
        "e1cbcb83-a73d-4623-ac16-363d7724040b",
    )

    if not username or not password:
        return None, (
            "Identifiants Tarzaali Online non configurés. "
            "Veuillez les renseigner dans les Paramètres."
        )

    url = (
        f"http://biogroupe.ddns.net:8020/api/appLabo/RealTime/Labo"
        f"?patient=&urgence=ALL&etat=&codeAnalyseUnique="
        f"&codeParametreUnique="
        f"&codeEchantillon=&dateStart={date_param}"
        f"&dateEnd={date_param}"
        f"&username={username}&password={password}"
        f"&apiKey={api_key}"
    )

    try:
        resp = requests.get(url, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        return resp.json(), None
    except requests.Timeout:
        logger.warning("Online API timeout for liste %s", liste_id)
        return None, (
            "Le service en ligne ne répond pas (délai dépassé). "
            "Veuillez réessayer dans quelques instants."
        )
    except requests.ConnectionError:
        logger.warning(
            "Online API connection error for liste %s", liste_id
        )
        return None, (
            "Impossible de se connecter au service en ligne. "
            "Vérifiez votre connexion internet."
        )
    except requests.HTTPError as e:
        logger.error("Online API HTTP error: %s", e)
        return None, (
            f"Erreur du service en ligne (code {e.response.status_code})."
        )
    except Exception as e:
        logger.error("Online API unexpected error: %s", e)
        return None, f"Erreur inattendue : {str(e)}"
