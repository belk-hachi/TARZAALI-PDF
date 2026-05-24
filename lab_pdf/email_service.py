import os
import imaplib
import email
import logging
import threading
import uuid
from datetime import datetime
from email.header import decode_header
from pypdf import PdfWriter

from .config import app_config, UPLOAD_DIR
from .database import save_extraction_result
from .ai_service import ai_service

logger = logging.getLogger(__name__)

DEFAULT_FETCH_INTERVAL = 3600  # 1 hour in seconds


def fetch_and_process_emails():
    """Fetch PDFs from email, merge them, and process with IA."""
    config = app_config.load()
    
    imap_server = config.get("email_imap_server")
    email_user = config.get("email_user")
    email_pass = config.get("email_pass")
    
    if not email_user or not email_pass:
        logger.info("Email credentials not configured. Skipping email fetch.")
        return

    folder = config.get("email_folder", "INBOX")
    sender_filter = config.get("email_sender_filter", "")
    subject_filter = config.get("email_subject_filter", "Compte Rendu")
    
    # Build search criteria
    criteria = '(UNSEEN'
    if sender_filter:
        criteria += f' FROM "{sender_filter}"'
    if subject_filter:
        criteria += f' SUBJECT "{subject_filter}"'
    criteria += ')'

    temp_dir = os.path.join(UPLOAD_DIR, f"tmp_email_{uuid.uuid4().hex[:8]}")
    os.makedirs(temp_dir, exist_ok=True)

    try:
        # 1. Connect and Fetch
        mail = imaplib.IMAP4_SSL(imap_server)
        mail.login(email_user, email_pass)
        mail.select(folder)

        status, messages = mail.search(None, criteria)
        if status != "OK" or not messages[0]:
            logger.info("No new emails found matching criteria.")
            mail.logout()
            return 0

        email_ids = messages[0].split()
        processed_count = len(email_ids)
        logger.info(f"Found {processed_count} new emails. Processing...")

        for e_id in email_ids:
            downloaded_files = []
            res, msg_data = mail.fetch(e_id, "(RFC822)")
            
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    for part in msg.walk():
                        if part.get_content_maintype() == "multipart":
                            continue
                        if part.get("Content-Disposition") is None:
                            continue

                        filename = part.get_filename()
                        if filename:
                            decoded_name = decode_header(filename)[0][0]
                            if isinstance(decoded_name, bytes):
                                filename = decoded_name.decode()
                            
                            if filename.lower().endswith(".pdf"):
                                filepath = os.path.join(temp_dir, filename)
                                with open(filepath, "wb") as f:
                                    f.write(part.get_payload(decode=True))
                                downloaded_files.append(filepath)

            if downloaded_files:
                # 2. Merge PDFs
                downloaded_files.sort(key=lambda x: ("-mail" not in x.lower(), x.lower()))
                
                first_file_name = os.path.basename(downloaded_files[0])
                session_id = str(uuid.uuid4())[:8]
                final_filename = f"{session_id}_{first_file_name}"
                if not final_filename.lower().endswith(".pdf"):
                    final_filename += ".pdf"
                
                final_path = os.path.join(UPLOAD_DIR, final_filename)
                
                merger = PdfWriter()
                for pdf in downloaded_files:
                    merger.append(pdf)
                merger.write(final_path)
                merger.close()
                
                logger.info(f"Merged PDF created from email: {final_filename}")

                # 3. Process with AI
                try:
                    model = config.get("model", "gemini-2.5-flash")
                    prompt = app_config.load_prompt()
                    extraction_result = ai_service.extract_from_pdf(
                        final_path, prompt, model_name=model
                    )
                    
                    save_extraction_result(
                        extraction_result, original_filename=final_filename
                    )
                    logger.info(f"Successfully processed email result: {final_filename}")
                except Exception as e:
                    logger.error(f"AI Processing failed for email PDF {final_filename}: {e}")

            # Cleanup temp files for this email
            for f in downloaded_files:
                try:
                    os.remove(f)
                except:
                    pass

        mail.logout()
        return processed_count

    except Exception as e:
        logger.error(f"Email fetch service failed: {e}")
    finally:
        if os.path.exists(temp_dir):
            try:
                import shutil
                shutil.rmtree(temp_dir)
            except:
                pass


class EmailFetcherScheduler:
    """Background thread that periodically fetches PDFs from email."""

    def __init__(self):
        self._timer = None
        self._running = False

    def start(self):
        if self._running:
            return
        self._running = True
        self._schedule_next()
        logger.info("Email fetcher scheduler started")

    def stop(self):
        self._running = False
        if self._timer:
            self._timer.cancel()
            self._timer = None
        logger.info("Email fetcher scheduler stopped")

    def _schedule_next(self):
        if not self._running:
            return
        
        # Get interval from config (convert minutes to seconds)
        config = app_config.load()
        interval_minutes = config.get("email_fetch_interval", 60)
        interval_seconds = max(60, interval_minutes * 60)  # Min 1 minute
        
        self._timer = threading.Timer(interval_seconds, self._run_fetch)
        self._timer.daemon = True
        self._timer.start()

    def _run_fetch(self):
        try:
            fetch_and_process_emails()
        except Exception as e:
            logger.error("Scheduled email fetch failed: %s", e)
        finally:
            self._schedule_next()


# Module-level singleton
email_fetcher_scheduler = EmailFetcherScheduler()
