"""Network and input-size safety helpers."""

from __future__ import annotations

from http.client import HTTPResponse
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener


MAX_REMOTE_RESPONSE_BYTES = 10 * 1024 * 1024
MAX_PRESET_BYTES = 1 * 1024 * 1024
MAX_LOCAL_FILE_BYTES = 10 * 1024 * 1024
MAX_RECORDS_PER_SOURCE = 5000


class ResponseTooLargeError(Exception):
    """Raised when a response or file exceeds a configured safety limit."""


class RedirectBlockedError(Exception):
    """Raised when a request attempts to follow an HTTP redirect."""

    def __init__(self, location: str):
        super().__init__(location)
        self.location = location


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        return None


_NO_REDIRECT_OPENER = build_opener(_NoRedirectHandler)


def open_without_redirects(request: Request, timeout_seconds: int) -> HTTPResponse:
    """Open a URL without following redirects."""
    try:
        return _NO_REDIRECT_OPENER.open(request, timeout=timeout_seconds)
    except HTTPError as exc:
        if 300 <= exc.code < 400:
            raise RedirectBlockedError(exc.headers.get("Location", "")) from exc
        raise


def read_response_limited(response: object, max_bytes: int, label: str) -> bytes:
    """Read a response body after enforcing a byte limit."""
    content_length = _content_length(response)
    if content_length is not None and content_length > max_bytes:
        raise ResponseTooLargeError(
            f"{label} is larger than the {max_bytes} byte limit "
            f"({content_length} bytes)."
        )

    data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ResponseTooLargeError(f"{label} is larger than the {max_bytes} byte limit.")
    return data


def _content_length(response: object) -> int | None:
    headers = getattr(response, "headers", None)
    value = None
    if headers is not None:
        value = headers.get("Content-Length")
    if value is None and hasattr(response, "getheader"):
        value = response.getheader("Content-Length")
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
