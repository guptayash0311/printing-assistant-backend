import hashlib
import io
import re

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.core.errors import DomainError

PDF = "application/pdf"
JPEG = "image/jpeg"
PNG = "image/png"
ALLOWED = {PDF, JPEG, PNG}


def detect_mime(data: bytes) -> str:
    if data.startswith(b"%PDF"):
        return PDF
    if data.startswith(b"\xff\xd8\xff"):
        return JPEG
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    raise DomainError("INVALID_FILE_TYPE", "Only PDF, JPEG, and PNG files are accepted.", 400)


def page_count_for(data: bytes, mime: str) -> int:
    if mime in {JPEG, PNG}:
        return 1
    try:
        reader = PdfReader(io.BytesIO(data))
        count = len(reader.pages)
    except PdfReadError as exc:
        raise DomainError("INVALID_FILE", "The PDF could not be read.", 400) from exc
    if count < 1:
        raise DomainError("INVALID_FILE", "The PDF has no pages.", 400)
    return count


def checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_phone(phone: str) -> str:
    cleaned = re.sub(r"[^\d+]", "", phone.strip())
    digits = re.sub(r"\D", "", cleaned)
    if len(digits) < 8 or len(digits) > 15:
        raise DomainError("INVALID_CONTACT", "Enter a valid phone number.", 400)
    return cleaned


_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_HTTPS = re.compile(r"^https://[^\s]+$")


def require_color(value: str) -> str:
    if not _COLOR.match(value):
        raise DomainError("INVALID_COLOR", "Color must be a hex value like #1f4b3a.", 400)
    return value.lower()


def require_slug(value: str) -> str:
    if not _SLUG.match(value):
        raise DomainError("INVALID_SLUG", "Slug must use lowercase letters, numbers, and hyphens.", 400)
    return value


def clean_logo_url(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    if not _HTTPS.match(value):
        raise DomainError("INVALID_LOGO", "Logo must be an https URL.", 400)
    return value
