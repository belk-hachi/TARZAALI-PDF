"""
Lab PDF Processor — Entry Point.

This is the main script that launches the Flask application.
It works both as a Python script and when bundled by PyInstaller.

Usage:
    python app.py                  # Development mode
    FLASK_DEBUG=1 python app.py    # Debug mode
    PORT=8080 python app.py        # Custom port
"""

import os
from lab_pdf import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"

    print(f"Démarrage du processeur de PDF Labo sur http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
