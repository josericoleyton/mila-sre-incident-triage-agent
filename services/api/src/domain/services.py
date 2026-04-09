import os

ALLOWED_EXTENSIONS = {".log", ".txt"}
ALLOWED_MIME_PREFIXES = ("image/", "video/")
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024


class ValidationError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def validate_incident(
    title: str,
    file_content_type: str | None = None,
    file_size: int | None = None,
    file_name: str | None = None,
) -> None:
    """Validate incident submission fields. Raises ValidationError on failure."""
    if not title or not title.strip():
        raise ValidationError("Title is required")

    if file_content_type is not None:
        _validate_file_type(file_content_type, file_name)

    if file_size is not None and file_size > MAX_FILE_SIZE_BYTES:
        raise ValidationError(f"File size exceeds maximum of 50MB")


def _validate_file_type(content_type: str, file_name: str | None = None) -> None:
    if any(content_type.startswith(prefix) for prefix in ALLOWED_MIME_PREFIXES):
        return
    if file_name:
        _, ext = os.path.splitext(file_name)
        if ext.lower() in ALLOWED_EXTENSIONS:
            return
    raise ValidationError(f"File type '{content_type}' is not allowed")
