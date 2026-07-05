"""
app/__init__.py
----------------
Application factory.

Using the "app factory" pattern (create_app()) instead of a bare module-level
Flask() instance is a widely recommended practice: it allows multiple
configurations (development/testing/production), avoids circular imports,
and makes the app testable (tests can spin up isolated instances).
"""

import logging
import os
from logging.handlers import RotatingFileHandler

from flask import Flask

from config import get_config


def create_app(config_object=None):
    """Application factory.

    Args:
        config_object: Optional config class to override the environment-based
            default (mainly used by the test suite).

    Returns:
        A fully configured Flask application instance.
    """
    app = Flask(__name__)
    app.config.from_object(config_object or get_config())

    _ensure_directories(app)
    _configure_logging(app)

    # Blueprints are registered here rather than importing routes at module
    # scope, which keeps import order safe and makes the factory the single
    # source of truth for what the app contains.
    from app.routes import main_bp
    app.register_blueprint(main_bp)

    from app.services.cleanup import start_cleanup_thread
    if not app.config.get("TESTING"):
        start_cleanup_thread(app)

    app.logger.info("Application initialized (env=%s, debug=%s)",
                     os.environ.get("FLASK_ENV", "development"), app.config["DEBUG"])
    return app


def _ensure_directories(app):
    os.makedirs(app.config["DOWNLOAD_DIR"], exist_ok=True)
    os.makedirs(app.config["LOG_DIR"], exist_ok=True)


def _configure_logging(app):
    """Configure rotating file + console logging.

    Rotating handlers cap log file size instead of growing forever, which
    matters for anything meant to run unattended for a while.
    """
    log_path = os.path.join(app.config["LOG_DIR"], "app.log")
    file_handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=3)
    file_handler.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)s in %(module)s: %(message)s"
    ))
    file_handler.setLevel(logging.INFO)

    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO if not app.config["DEBUG"] else logging.DEBUG)
