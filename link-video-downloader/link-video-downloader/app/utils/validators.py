"""
app/utils/validators.py
-------------------------
Input validation helpers.

Keeping validation separate from route handlers and services makes the
rules unit-testable in isolation and reusable wherever a URL needs checking.
"""

import re
from urllib.parse import urlparse

_URL_PATTERN = re.compile(r"^https?://", re.IGNORECASE)


def is_valid_url(url: str) -> bool:
    """Basic structural validation: non-empty, http(s) scheme, has a host."""
    if not url or not isinstance(url, str):
        return False
    if not _URL_PATTERN.match(url.strip()):
        return False
    parsed = urlparse(url.strip())
    return bool(parsed.netloc)


def sanitize_filename(name: str, max_length: int = 150) -> str:
    """Strip filesystem-unsafe characters and cap length.

    Applied to titles pulled from third-party metadata before they are used
    as part of a filename, since that metadata is untrusted input.
    """
    if not name:
        return "video"
    cleaned = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    return cleaned[:max_length] or "video"
