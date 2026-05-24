"""
Configuration management for the Lab PDF Processor.

Handles:
- Path resolution for both development and PyInstaller EXE modes
- Loading/saving config.json with backward-compatible keys
- Password obfuscation (Base64 — NOT encryption, just obscurement)
- External file initialization (config.json, prompt.md)
"""

import os
import sys
import json
import base64
import logging

logger = logging.getLogger(__name__)

# ─── Path Resolution ────────────────────────────────────────────────────────

def resource_path(relative_path):
    """Get absolute path to a bundled resource.

    Works in development (relative to project root) and when frozen
    by PyInstaller (relative to sys._MEIPASS temp directory).
    """
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        # In development, project root is one level up from this package
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


# For writable data (DB, uploads, logs, backups) — always next to the EXE/script
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Writable directories
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
GENERATED_DIR = os.path.join(BASE_DIR, "generated")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")

# Read-only assets (bundled inside the EXE via PyInstaller)
LOGO_PATH = resource_path("logo.jpg")

# External files (writable, next to the EXE)
KEY_FILE_PATH = os.path.join(BASE_DIR, "gemini_key.txt")
PROMPT_PATH = os.path.join(BASE_DIR, "prompt.md")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
DB_PATH = os.path.join(BASE_DIR, "lab.db")


# ─── Password Obfuscation ──────────────────────────────────────────────────

def obscure_password(password):
    """Simple Base64 obfuscation for config file storage.

    NOTE: This is NOT encryption — it only prevents casual plaintext
    reading of the password in config.json. The config file should still
    be protected by OS-level file permissions.
    """
    if not password:
        return ""
    return base64.b64encode(password.encode()).decode()


def deobscure_password(obscured):
    """Decode Base64-obscured password from config file."""
    if not obscured:
        return ""
    try:
        return base64.b64decode(obscured.encode()).decode()
    except Exception:
        return ""


# ─── Config Class ───────────────────────────────────────────────────────────

class Config:
    """Application configuration manager with simple in-memory caching.

    The cache is invalidated on every save() call. On first load(),
    the config is read from disk and cached for the lifetime of the
    process (or until save() is called).
    """

    # Default values — keys must match existing config.json names for
    # backward compatibility with deployed installations.
    DEFAULTS = {
        "api_key": "",
        "model": "gemini-2.5-flash",
        "online_username": "",
        "online_password": "",
        "online_api_key": "e1cbcb83-a73d-4623-ac16-363d7724040b",
        "lab_dr_name": "IBN SINA. Dr N.KACI",
        "lab_addr_l1": "Boulevard Amir Abdelkader, Cité nouvelle",
        "lab_addr_l2": "mosquée 205 N°1 et 2. DJELFA",
        "lab_tel": "027902479",
        "lab_fax": "027902479",
        "lab_mobile": "0671013704",
        "backup_dir": "",
        "max_backups": 10,
        "email_imap_server": "ssl0.ovh.net",
        "email_user": "",
        "email_pass": "",
        "email_folder": "INBOX",
        "email_sender_filter": "labo.ibnsina17@gmail.com",
        "email_subject_filter": "Compte Rendu",
        "email_fetch_interval": 60,
    }

    def __init__(self):
        self._cache = None

    def load(self, force_reload=False):
        """Load configuration from config.json with fallback to gemini_key.txt.

        Returns a dict with all config keys. Passwords are de-obscured
        before returning so callers never need to handle obfuscation.
        """
        if self._cache is not None and not force_reload:
            return self._cache

        config = dict(self.DEFAULTS)

        # 1. Load from config.json if it exists
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # De-obscure passwords before returning to app
                    if data.get("online_password"):
                        data["online_password"] = deobscure_password(
                            data["online_password"]
                        )
                    if data.get("email_pass"):
                        data["email_pass"] = deobscure_password(
                            data["email_pass"]
                        )
                    # Ensure online_api_key has a default if missing from old configs
                    if "online_api_key" not in data:
                        data["online_api_key"] = self.DEFAULTS["online_api_key"]
                    config.update(data)
            except Exception as e:
                logger.error("Error loading config.json: %s", e)

        # 2. Fallback: read API key from gemini_key.txt
        if not config.get("api_key") and os.path.exists(KEY_FILE_PATH):
            try:
                with open(KEY_FILE_PATH, "r", encoding="utf-8") as f:
                    key = f.read().strip()
                    if key:
                        config["api_key"] = key
            except Exception as e:
                logger.error("Error loading gemini_key.txt: %s", e)

        self._cache = config
        return config

    def save(self, config):
        """Save configuration to config.json with password obfuscation.

        Invalidates the in-memory cache so the next load() reads
        from disk.
        """
        to_save = config.copy()
        if to_save.get("online_password"):
            to_save["online_password"] = obscure_password(
                to_save["online_password"]
            )
        if to_save.get("email_pass"):
            to_save["email_pass"] = obscure_password(
                to_save["email_pass"]
            )

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(to_save, f, indent=2)

        self._cache = None  # Invalidate cache

    def get_api_key(self):
        """Shortcut to read the Gemini API key."""
        return self.load().get("api_key", "")

    def get_lab_config(self):
        """Extract lab-specific config keys as a dict for PDF generation.

        This dict is passed directly into generate_pdf() — do NOT rename
        these keys as they are used by generate_pdf.py's rendering logic.
        """
        config = self.load()
        return {
            "lab_dr_name": config.get("lab_dr_name"),
            "lab_addr_l1": config.get("lab_addr_l1"),
            "lab_addr_l2": config.get("lab_addr_l2"),
            "lab_tel": config.get("lab_tel"),
            "lab_fax": config.get("lab_fax"),
            "lab_mobile": config.get("lab_mobile"),
            "email": config.get("email", "info.tarzaali@gmail.com"),
            "lab_name": config.get(
                "lab_name",
                "LABORATOIRE D'ANALYSES DE BIOLOGIE MEDICALE",
            ),
            "prof_name": config.get(
                "prof_name", "Professeur Abdelaziz TARZAALI"
            ),
        }

    def init_external_files(self):
        """Ensure config.json and prompt.md exist next to the EXE.

        Creates them with sensible defaults if missing. This is safe to
        call on every startup — it only writes when files are absent.
        """
        # 1. Handle config.json
        if not os.path.exists(CONFIG_FILE):
            initial_config = self.load()
            self.save(initial_config)
            logger.info("Created %s", CONFIG_FILE)

        # 2. Handle prompt.md
        if not os.path.exists(PROMPT_PATH):
            bundled_prompt_path = resource_path("prompt.md")
            content = ""

            if os.path.exists(bundled_prompt_path):
                with open(bundled_prompt_path, "r", encoding="utf-8") as f:
                    content = f.read()

            if not content.strip():
                # Minimal fallback — the real prompt is in the bundled prompt.md
                content = (
                    "# Data extraction assistant for a medical laboratory.\n"
                    "Extract patient and test result data from the PDF and "
                    "return it as a single valid JSON object.\n"
                )

            with open(PROMPT_PATH, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info("Created %s", PROMPT_PATH)

    def load_prompt(self):
        """Load the AI extraction prompt from prompt.md."""
        with open(PROMPT_PATH, "r", encoding="utf-8") as f:
            return f.read()


# Module-level singleton — shared across the entire application
app_config = Config()


def ensure_directories():
    """Create writable directories if they don't exist."""
    for directory in (UPLOAD_DIR, GENERATED_DIR, LOGS_DIR, BACKUP_DIR):
        os.makedirs(directory, exist_ok=True)
