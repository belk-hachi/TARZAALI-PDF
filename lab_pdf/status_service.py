import json
import logging
import threading
from datetime import datetime

from .config import app_config
from .database import (
    get_db_connection, create_notification, get_patients
)
from .online_service import fetch_online_results

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL = 1800  # 30 minutes in seconds


def poll_pending_status():
    """Check online API for all patients with 'pending' status and update DB."""
    conn = get_db_connection()
    try:
        # 1. Find all pending patients
        # We use a broad search first
        pending_patients = get_patients(status_filter='pending', conn=conn)
        if not pending_patients:
            return

        # 2. Group by date to minimize API calls
        by_date = {}
        for p in pending_patients:
            date = p['liste_date']
            if date not in by_date:
                by_date[date] = []
            by_date[date].append(p)

        for liste_date, patients in by_date.items():
            # 3. Fetch online results for this date
            # Note: liste_id=0 because it's not used by fetch_online_results for credentials
            data, error = fetch_online_results(0, liste_date)
            if error or not data:
                continue

            # 4. Compare and update
            for p in patients:
                # Find patient in API results
                # Normalize name for comparison (same as frontend logic)
                db_full_name = f"{p['last_name']} {p['first_name']}".upper()
                
                api_patient = None
                for item in data:
                    api_full_name = (item.get('Nom', '').strip() + " " + item.get('Prenom', '').strip()).upper()
                    if api_full_name == db_full_name:
                        api_patient = item
                        break
                
                if api_patient:
                    # Check if all tests are finished
                    # In the API, "Terminé" or "Validé" means finished
                    all_finished = True
                    for analyse in api_patient.get('ListAnalyses', []):
                        for param in analyse.get('ListParametres', []):
                            etat = param.get('EtatDescription', '').upper()
                            if "EN COURS" in etat or "ATTENTE" in etat:
                                all_finished = False
                                break
                        if not all_finished: break
                    
                    if all_finished:
                        # Update DB status to 'completed'
                        cursor = conn.cursor()
                        cursor.execute(
                            "UPDATE patients SET status = 'completed' WHERE id = ?",
                            (p['id'],)
                        )
                        conn.commit()
                        
                        # Create notification
                        create_notification(
                            "status_changed",
                            f"resultat de {p['last_name']} {p['first_name']} est termine",
                            patient_id=p['id'],
                            conn=conn
                        )
                        logger.info(f"Status updated to completed for patient {p['id']}")

    except Exception as e:
        logger.error(f"Status poller failed: {e}")
    finally:
        conn.close()


class StatusPollerScheduler:
    """Background thread that periodically checks pending patient status."""

    def __init__(self):
        self._timer = None
        self._running = False

    def start(self):
        if self._running:
            return
        self._running = True
        self._schedule_next()
        logger.info("Status poller scheduler started")

    def stop(self):
        self._running = False
        if self._timer:
            self._timer.cancel()
            self._timer = None
        logger.info("Status poller scheduler stopped")

    def _schedule_next(self):
        if not self._running:
            return
        
        # Poll every 30 minutes
        self._timer = threading.Timer(DEFAULT_POLL_INTERVAL, self._run_poll)
        self._timer.daemon = True
        self._timer.start()

    def _run_poll(self):
        try:
            poll_pending_status()
        except Exception as e:
            logger.error("Scheduled status poll failed: %s", e)
        finally:
            self._schedule_next()


# Module-level singleton
status_poller_scheduler = StatusPollerScheduler()
