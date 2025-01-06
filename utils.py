import hashlib
from pathlib import Path

DEBUG = False
DEBUG_ATTACHMENTS = False

def debug_print(*messages: str) -> None:
    """Print debug messages if DEBUG is True"""
    if DEBUG:
        print("[DEBUG]", *messages)

def debug_attachment_print(message: str) -> None:
    """Print debug messages for attachments if DEBUG_ATTACHMENTS is True"""
    if DEBUG_ATTACHMENTS:
        print(f"[DEBUG ATTACHMENT] {message}")

def calculate_md5(file_path: str) -> str:
    """Calculate MD5 hash of a file"""
    try:
        md5_hash = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                md5_hash.update(chunk)
        return md5_hash.hexdigest()
    except Exception as e:
        debug_print(f"Error calculating MD5: {str(e)}")
        raise ValueError(f"Failed to calculate MD5 for {file_path}: {str(e)}")

def format_size(size_bytes: int) -> str:
    """Format file size in human-readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"
