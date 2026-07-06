"""
config.py
---------
Centralized application configuration.

Using a class-based config (instead of scattering constants across the
codebase) is a standard Flask best practice: it makes it trivial to add
a TestingConfig or ProductionConfig later without touching business logic.
"""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    """Base configuration shared by all environments."""

    # --- Paths -------------------------------------------------------
    BASE_DIR = BASE_DIR
    DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
    LOG_DIR = os.path.join(BASE_DIR, "logs")

    # --- Flask ---------------------------------------------------------
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    DEBUG = os.environ.get("FLASK_DEBUG", "1") == "1"
    JSON_SORT_KEYS = False

    # --- Application behaviour -----------------------------------------
    # Maximum age (in seconds) a completed download is kept on disk before
    # the background cleanup task removes it. Prevents unbounded disk usage.
    FILE_RETENTION_SECONDS = int(os.environ.get("FILE_RETENTION_SECONDS", 3600))

    # How often (seconds) the cleanup task sweeps the downloads directory.
    CLEANUP_INTERVAL_SECONDS = int(os.environ.get("CLEANUP_INTERVAL_SECONDS", 900))

    # Default output container for merged video+audio streams.
    OUTPUT_FORMAT = "mp4"

    # Maximum length (chars) allowed for a sanitized output filename.
    MAX_FILENAME_LENGTH = 150

    # Host/port used by run.py
    HOST = os.environ.get("HOST", "127.0.0.1")
    PORT = int(os.environ.get("PORT", 5000))


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    # In production this MUST be overridden via the SECRET_KEY env var.
    SECRET_KEY = os.environ.get("SECRET_KEY", Config.SECRET_KEY)


class TestingConfig(Config):
    TESTING = True
    DEBUG = True
    DOWNLOAD_DIR = os.path.join(BASE_DIR, "tests", "tmp_downloads")


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def get_config():
    """Return the config class selected by the FLASK_ENV environment variable."""
    env = os.environ.get("FLASK_ENV", "development")
    return CONFIG_MAP.get(env, DevelopmentConfig)
