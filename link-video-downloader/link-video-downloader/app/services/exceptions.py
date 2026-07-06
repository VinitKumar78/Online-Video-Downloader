"""
app/services/exceptions.py
---------------------------
Custom exception hierarchy for the download service.

Defining specific exceptions (instead of raising generic Exception or
returning error strings) lets route handlers catch precisely what they
expect and map each case to the correct HTTP status code.
"""


class DownloadServiceError(Exception):
    """Base class for all service-layer errors."""


class InvalidURLError(DownloadServiceError):
    """Raised when the supplied URL is empty, malformed, or unsupported."""


class ExtractionError(DownloadServiceError):
    """Raised when yt-dlp fails to extract metadata or formats for a URL."""


class JobNotFoundError(DownloadServiceError):
    """Raised when a job_id does not correspond to any known job."""


class FileNotReadyError(DownloadServiceError):
    """Raised when a file is requested before its job has finished."""
