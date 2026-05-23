"""
Lab PDF Processor — Flask Application Factory.

Creates and configures the Flask application with:
- Database initialization (explicit, not import-time side effect)
- Blueprint registration for all route modules
- Request-scoped database connections via Flask's g
- Jinja template filters
- Backup scheduler startup
- Directory creation for writable data
"""

import json
import os
import logging

from flask import Flask

from .config import (
    resource_path, app_config, ensure_directories,
)
from .database import init_db, get_db, teardown_db
from .backup_service import backup_scheduler, create_backup


def create_app():
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        template_folder=resource_path("templates"),
        static_folder=resource_path("static"),
    )

    # Secret key — in production, set SECRET_KEY env variable
    app.secret_key = os.environ.get(
        "SECRET_KEY", "lab-pdf-secret-key-change-me"
    )

    # ─── Logging ────────────────────────────────────────────────────────
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # ─── Ensure directories exist ───────────────────────────────────────
    ensure_directories()

    # ─── Initialize external files (config.json, prompt.md) ─────────────
    app_config.init_external_files()

    # ─── Initialize database (explicit call, not import side-effect) ────
    init_db()

    # ─── Request-scoped database connections ────────────────────────────
    app.before_request(lambda: None)  # Placeholder if needed later
    app.teardown_appcontext(teardown_db)

    # ─── Jinja filters ──────────────────────────────────────────────────
    @app.template_filter('from_json')
    def from_json_filter(s):
        """Parse a JSON string in a Jinja template."""
        return json.loads(s)

    # ─── Register blueprints ────────────────────────────────────────────
    from .routes import register_blueprints
    register_blueprints(app)

    # ─── Startup backup ─────────────────────────────────────────────────
    try:
        backup_path = create_backup()
        if backup_path:
            app.logger.info("Startup backup created: %s", backup_path)
    except Exception as e:
        app.logger.error("Startup backup failed: %s", e)

    # Start periodic backup scheduler
    backup_scheduler.start()

    return app
