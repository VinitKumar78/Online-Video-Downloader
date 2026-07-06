"""
run.py
------
Application entry point. Run with:

    python run.py

This is the ONLY file you invoke directly. Everything else is imported by
the app factory in app/__init__.py.
"""

from app import create_app
from config import get_config

app = create_app()

if __name__ == "__main__":
    cfg = get_config()
    app.run(host=cfg.HOST, port=cfg.PORT, debug=cfg.DEBUG)
