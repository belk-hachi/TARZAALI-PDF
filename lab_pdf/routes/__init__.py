"""
Blueprint registration for all route modules.
"""

from .main import main_bp
from .upload import upload_bp
from .dashboard import dashboard_bp
from .patient import patient_bp
from .api import api_bp


def register_blueprints(app):
    """Register all application blueprints."""
    app.register_blueprint(main_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(patient_bp)
    app.register_blueprint(api_bp)
