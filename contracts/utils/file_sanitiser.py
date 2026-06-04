import os
import re
import logging

logger = logging.getLogger(__name__)

# Allowed MIME signatures (magic bytes)
PDF_MAGIC  = b'%PDF'
DOCX_MAGIC = b'PK\x03\x04'   # ZIP-based format

MAX_FILENAME_LENGTH = 180


def validate_file_magic(file) -> tuple[bool, str]:
    """
    Read the first 8 bytes of the uploaded file to confirm it matches
    its declared extension. Returns (is_valid, error_message).
    """
    file.seek(0)
    header = file.read(8)
    file.seek(0)

    ext = os.path.splitext(file.name)[1].lower()

    if ext == '.pdf':
        if not header.startswith(PDF_MAGIC):
            return False, 'File does not appear to be a valid PDF (magic bytes mismatch).'
    elif ext == '.docx':
        if not header.startswith(DOCX_MAGIC):
            return False, 'File does not appear to be a valid DOCX (magic bytes mismatch).'
    else:
        return False, f'Unsupported extension: {ext}'

    return True, ''


def sanitise_filename(filename: str) -> str:
    """
    Return a safe filename:
    - Strip path separators and null bytes
    - Replace non-alphanumeric chars (except . - _) with underscores
    - Truncate to MAX_FILENAME_LENGTH
    """
    # Remove path components
    filename = os.path.basename(filename)

    # Strip null bytes
    filename = filename.replace('\x00', '')

    # Keep only safe characters
    filename = re.sub(r'[^\w.\-]', '_', filename)

    # Prevent hidden files
    if filename.startswith('.'):
        filename = 'file_' + filename

    # Truncate preserving extension
    name, ext = os.path.splitext(filename)
    max_name  = MAX_FILENAME_LENGTH - len(ext)
    filename  = name[:max_name] + ext

    return filename


def check_path_traversal(base_dir: str, file_path: str) -> bool:
    """
    Return True if file_path is safely inside base_dir.
    Prevents path traversal attacks (../../etc/passwd style).
    """
    base    = os.path.realpath(base_dir)
    target  = os.path.realpath(file_path)
    return target.startswith(base + os.sep) or target == base